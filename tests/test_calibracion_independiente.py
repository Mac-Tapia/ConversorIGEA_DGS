"""044:RF-3, RF-4, RF-5 y RF-8 — la PINN calibra aparte, responde por familia y publica sus denominadores.

Sin GPU: ``entrenar`` corre entero con un doble en lugar del ajuste, porque aquí se comprueba qué datos
ve cada paso y qué decide con los errores. Que el modelo real aprenda lo prueba ``test_digital_twin_oraculo``.
"""
from __future__ import annotations

import json
import random

import numpy as np
import pytest

from convertersmartgrid.digital_twin import hiperparametros as hp
from convertersmartgrid.digital_twin import oraculo as orc
from convertersmartgrid.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.evaluacion_modelos import PoliticaDeError, evaluar_candidato

SEMILLA = random.randrange(1_000_000)


def _red(prefijo: str, n: int, demanda: float, tension: float) -> tuple[dict, dict]:
    nodos = {f'{prefijo}{i}': {'kv': 10.0, 'p_mw': 0.0 if i == 0 else 0.1 * demanda, 'q_mvar': 0.0,
                               'fuente': i == 0, 'v_pu': 1.0 if i == 0 else None} for i in range(n)}
    ramas = [{'id': f'{prefijo}L{i}', 'desde': f'{prefijo}{i}', 'hasta': f'{prefijo}{i + 1}', 'cerrada': True,
              'r_ohm': 0.3, 'x_ohm': 0.2, 'inom_ka': 0.2} for i in range(n - 1)]
    return {'nodos': nodos, 'ramas': ramas, 'version': orc.VERSION_GRAFO}, {f'{prefijo}{i}': tension for i in range(n)}


def _conjunto(rng: random.Random):
    """Una red de ajuste con familias de sobra y otra de prueba: un sistema fuera, tamaños sorteados."""
    muestras, ids = [], []
    # El hash fijo de cada familia decide su partición: se buscan las que caen en cada lado sin suponerlo.
    for r, (prefijo, familias) in enumerate((('A', rng.randint(40, 70)), ('B', rng.randint(12, 20)))):
        for f in range(familias):
            grafo, tens = _red(prefijo, rng.randint(4, 4), rng.uniform(0.7, 1.3), 1.0)
            muestras.append(orc.muestra(grafo, tens, f'fam-{prefijo}-{f}'))
            ids.append(f'ep-{r}-{f}')
    return muestras, ids


class _Doble:
    """El ajuste real pide CUDA; aquí cuentan las muestras que recibe y lo que se decide después."""

    def __init__(self, estados, cfg, dominio, version='', cuantil=None, cobertura_justificada=False):
        self.estados, self.cfg, self.dominio, self.version = estados, cfg, dominio, version
        self.cuantil, self.cobertura_justificada = cuantil, cobertura_justificada

    def predecir(self, grafo):
        n = len(grafo['nodos'])
        return {'ids': sorted(grafo['nodos']), 'v': np.full(n, 1.001), 'incertidumbre': np.full(n, 0.01),
                'intervalo_pu': None, 'residuo': np.zeros(n), 'theta': np.zeros(n)}


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    """``entrenar`` con el doble: ``errores`` da el MAE por tipo de modelo y familia."""
    muestras, ids = _conjunto(random.Random(SEMILLA))
    registro = {'calibrados': [], 'ajuste': [], 'seleccion': [], 'promovidos': [], 'exponente': [], 'modelo_json': None}
    errores = {'candidato': lambda fam: 0.002, 'fisica': lambda fam: 0.003, 'activo': lambda fam: 0.002}

    def tipo(modelo):
        if isinstance(modelo, orc.ModeloMallado):
            return 'fisica'
        return 'activo' if modelo.version == 'v0' else 'candidato'

    def mae(modelo, ms):
        ms = list(ms)
        return float(np.mean([errores[tipo(modelo)](m.familia) for m in ms])) if ms else None

    def miembro(ms, cfg, inicial=None, log=None, validacion=(), historial=None, al_validar=None):
        registro['ajuste'].append(list(ms))
        registro['seleccion'].append(list(validacion))
        return {'peso': 0}

    def guardar(oraculo, bufer, meta):
        oraculo.version = 'v1'
        carpeta = bufer.raiz / 'modelos' / 'v1'
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / 'modelo.json').write_text(json.dumps(meta), encoding='utf-8')
        registro['modelo_json'] = carpeta / 'modelo.json'
        return carpeta

    calibrar = orc.calibrar_conforme

    def espia_calibrar(oraculo, calibracion):
        registro['calibrados'].append(list(calibracion))
        return calibrar(oraculo, calibracion)

    exponente = orc.elegir_exponente

    def espia_exponente(ms, *a, **k):
        registro['exponente'].append(list(ms))
        return exponente(ms, *a, **k)

    monkeypatch.setattr(orc, '_muestras', lambda *_a: (muestras, ids))
    monkeypatch.setattr(orc, 'OraculoPINN', _Doble)
    monkeypatch.setattr(orc, 'entrenar_miembro', miembro)
    monkeypatch.setattr(orc, 'dispositivo', lambda: 'doble')
    monkeypatch.setattr(orc, 'manifiesto', lambda *_a: {})
    monkeypatch.setattr(orc, 'guardar', guardar)
    monkeypatch.setattr(orc, 'cargar', lambda *_a: None)
    monkeypatch.setattr(orc, 'mae', mae)
    monkeypatch.setattr(orc, 'calibrar_conforme', espia_calibrar)
    monkeypatch.setattr(orc, 'elegir_exponente', espia_exponente)
    monkeypatch.setattr(orc, 'promover', lambda _b, version, _m: registro['promovidos'].append(version))
    bufer = BuferEpisodios(tmp_path)

    def correr(**kw):
        return orc.entrenar(bufer, reabrir=lambda _c: {'ok': True}, **kw)

    return {'correr': correr, 'registro': registro, 'errores': errores, 'muestras': muestras, 'ids': ids, 'bufer': bufer}


def _ids(ms):
    return {id(m) for m in ms}


def test_calibrador_no_ve_seleccion_ni_prueba(banco):
    """044:RF-4 — el cuantil sale solo de calibración, que ni ajusta, ni selecciona, ni mide."""
    r = banco['correr']()
    assert r['entrenado'], (SEMILLA, r)
    reg = banco['registro']
    calibrados = _ids(reg['calibrados'][0])
    assert len(reg['calibrados']) == 1 and calibrados
    ids_por_objeto = dict(zip(map(id, banco['muestras']), banco['ids'], strict=True))
    guardado = json.loads(reg['modelo_json'].read_text(encoding='utf-8'))['particiones_ids']
    assert {ids_por_objeto[i] for i in calibrados} == set(guardado['calibracion'])
    assert not calibrados & _ids(reg['seleccion'][0]) and not calibrados & _ids(reg['ajuste'][0])
    assert not set(guardado['calibracion']) & set(guardado['prueba'])


def test_ajuste_no_usa_la_prueba_sellada(banco):
    """044:RF-3 — miembros, parada temprana y modelo de carga no tocan calibración ni prueba."""
    r = banco['correr']()
    reg = banco['registro']
    ids_por_objeto = dict(zip(map(id, banco['muestras']), banco['ids'], strict=True))
    guardado = json.loads(reg['modelo_json'].read_text(encoding='utf-8'))['particiones_ids']
    apartados = set(guardado['prueba']) | set(guardado['calibracion'])
    vistos = _ids(reg['ajuste'][0]) | _ids(reg['seleccion'][0]) | _ids(reg['exponente'][0])
    assert r['entrenado'] and apartados and not {ids_por_objeto[i] for i in vistos} & apartados, SEMILLA
    assert _ids(reg['exponente'][0]) == _ids(reg['ajuste'][0])


def test_busqueda_de_hiperparametros_no_ve_la_prueba(monkeypatch):
    """044:RF-3 — la búsqueda se para en entrenamiento y selección: la prueba no entra ni apartada."""
    pytest.importorskip('optuna')
    muestras, _ids_ep = _conjunto(random.Random(SEMILLA))
    llamadas = []

    def detener(ms, cfg, inicial, validacion, **_k):
        llamadas.append((list(ms), list(validacion)))
        raise ValueError('fin del contrato antes de CUDA')

    monkeypatch.setattr(hp, 'entrenar_miembro', detener)
    with pytest.raises(ValueError, match='fin del contrato'):
        hp.buscar(muestras, ensayos=1)
    ajuste, seleccion = llamadas[0]
    grupos = orc.separar_calibracion(orc.particionar(muestras))
    assert _ids(ajuste) == _ids(grupos['entrenamiento']) and _ids(seleccion) == _ids(grupos['validacion'])
    assert not (_ids(ajuste) | _ids(seleccion)) & (_ids(grupos['prueba']) | _ids(grupos['calibracion']))


def test_regresion_familia_rechaza(banco):
    """044:RF-5 — buena media, una familia fuera de puerta: no se promueve y sigue el modelo en uso."""
    r = banco['correr']()
    assert r['promovido'] and banco['registro']['promovidos'] == ['v1'], (SEMILLA, r.get('fallos'))
    meta = json.loads(banco['registro']['modelo_json'].read_text(encoding='utf-8'))
    familias = sorted(meta['evaluacion']['veredicto']['familias'])
    assert len(familias) > 1
    mala = familias[0]
    banco['registro']['promovidos'].clear()
    # La media sigue por debajo de 0,005 p.u. y mejora la física: solo la familia lo delata.
    banco['errores']['candidato'] = lambda fam: 0.0051 if fam == mala else 0.001
    banco['errores']['fisica'] = lambda fam: 0.01
    r = banco['correr']()
    assert r['mae_v'] < 0.005, (SEMILLA, r['mae_v'])
    assert not r['promovido'] and banco['registro']['promovidos'] == []
    assert any(f'familia {mala}' in f and 'mae_v' in f for f in r['fallos']), r['fallos']


@pytest.mark.parametrize('referencia', ['fisica', 'activo'])
def test_familia_peor_que_su_referencia_rechaza(referencia):
    """044:RF-5 — dentro de 0,005 p.u., pero peor que la física o el activo en esa familia, más allá de 1,05."""
    politica = PoliticaDeError(topes=(('mae_v', .005), ('residuo', .05)))
    bien = {'ejemplos': 3, 'mae_v': .001, 'residuo': .01, 'mae_fisica': .002, 'mae_activo': .001}
    mala = {**bien, 'mae_v': .003}
    metricas = {'global': bien, 'familias': {'a': bien, 'b': {**mala, f'mae_{referencia}': .002}}}
    if referencia == 'fisica':
        metricas['familias']['b']['mae_activo'] = .003
    else:
        metricas['familias']['b']['mae_fisica'] = .004
    v = evaluar_candidato(metricas, politica)
    assert not v['approved'] and v['gates']['familias'] == {'a': True, 'b': False}
    assert any(f'peor que mae_{referencia}' in b for b in v['bloqueos'])


def test_sin_medida_o_sin_denominador_no_se_aprueba():
    """044:RF-5, 044:RF-8 — lo que falta no se da por bueno: ni física, ni NaN, ni familias, ni n."""
    politica = PoliticaDeError(topes=(('mae_v', .005),))
    bien = {'ejemplos': 3, 'mae_v': .001, 'mae_fisica': .002}
    assert evaluar_candidato({'global': bien, 'familias': {'a': bien}}, politica)['approved']
    for familia in ({**bien, 'mae_fisica': None}, {**bien, 'mae_v': float('nan')}, {**bien, 'ejemplos': 0}):
        assert not evaluar_candidato({'global': bien, 'familias': {'a': familia}}, politica)['approved'], familia
    assert not evaluar_candidato({'global': bien, 'familias': {}}, politica)['approved']
    assert not evaluar_candidato({'global': bien, 'familias': {'a': bien}, 'esperadas': ['a', 'b']}, politica)['approved']


def test_evaluar_candidato_respeta_las_politicas_de_minimos():
    """044:RF-5 — con una política de mínimos, como la del asistente, decide ``verificar_familias``."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion

    politica = PoliticaEvaluacion(modo='agente', puertas_por_familia=(('acierto', .9),))
    v = evaluar_candidato({'familias': {'a': {'ejemplos': 5, 'acierto': .95}, 'b': {'ejemplos': 5, 'acierto': .5}}}, politica)
    assert not v['approved'] and v['gates']['familias'] == {'a': True, 'b': False}
    assert v['politica_hash'] == politica.hash and v['alcance']['generaliza_a_otros_sistemas'] is False


def test_las_politicas_selladas_conservan_su_huella():
    """044:RF-3 — añadir las puertas de error no cambia lo ya sellado por el asistente y el pronóstico."""
    from dataclasses import fields

    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion

    assert {f.name for f in fields(PoliticaEvaluacion)} == {
        'modo', 'schema_version', 'min_calibracion_grupos', 'cobertura_objetivo', 'puertas_por_familia', 'semillas', 'minimos'}
    assert PoliticaDeError(topes=(('mae_v', .005),)).hash != PoliticaDeError(topes=(('mae_v', .004),)).hash


def test_intervalos_reportan_denominador(banco):
    """044:RF-4, 044:RF-8 — la cobertura lleva sus denominadores, su agrupación y la política con su huella."""
    r = banco['correr']()
    meta = json.loads(banco['registro']['modelo_json'].read_text(encoding='utf-8'))
    conforme = meta['conforme']
    assert conforme['cobertura_objetivo'] == .9 and 'correlacionados' in conforme['garantia']
    d = conforme['denominadores']
    assert d['calibracion']['grupos'] >= 1 and d['calibracion']['barras'] > 0 and d['prueba']['barras'] > 0
    assert 'familia' in conforme['agrupacion']
    ev = meta['evaluacion']
    assert ev['unidades']['mae_v'] == 'p.u.' and set(ev['denominadores']) == {'entrenamiento', 'validacion', 'calibracion', 'prueba'}
    assert ev['politica_hash'] == r['evaluacion']['politica_hash'] and ev['politica']['topes'] == [['mae_v', .005], ['residuo', .05]]
    assert ev['alcance']['generaliza_a_otros_sistemas'] is True
    assert all(v['ejemplos'] >= 1 and v['barras'] >= 1 for v in ev['veredicto']['familias'].values())
    assert all(meta['particiones_ids'][k] for k in ('entrenamiento', 'validacion', 'calibracion', 'prueba'))


def _oraculo_conforme(cuantil):
    return _Doble([], orc.Entrenamiento(), {}, cuantil=cuantil)


def _familias(n, prefijo='F'):
    salida = []
    for f in range(n):
        grafo, tens = _red(prefijo, 3, 1.0, 1.0)
        salida.append(orc.muestra(grafo, tens, f'{prefijo}{f}'))
    return salida


def test_pocas_familias_no_publican_cobertura():
    """044:RF-8 — con menos familias que las que pide el 90 %, se mide pero no se afirma."""
    r = orc.informe_conforme(_oraculo_conforme(1.0), _familias(8), _familias(4, 'P'))
    assert r['publicable'] is False and r['cobertura'] is None and '8 familia' in r['motivo']
    assert r['cobertura_empirica'] is not None
    r = orc.informe_conforme(_oraculo_conforme(1.0), _familias(9), _familias(4, 'P'))
    assert r['publicable'] is True and r['cobertura'] == .9 and r['motivo'] is None


def test_sin_cuantil_no_hay_cobertura_ni_empirica():
    """044:RF-8 — sin intervalo no se publica ninguna cifra de cobertura."""
    r = orc.informe_conforme(_oraculo_conforme(None), [], _familias(4, 'P'))
    assert r['publicable'] is False and r['cobertura'] is None and r['cobertura_empirica'] is None


def test_cobertura_empirica_es_la_de_la_prueba():
    """044:RF-8 — la cifra sale de las barras de prueba: |1,001 − 1,0| = 0,001 frente al semiancho."""
    prueba = _familias(4, 'P')
    cubre = orc.informe_conforme(_oraculo_conforme(1.0), _familias(9), prueba)     # semiancho 0,0101
    no_cubre = orc.informe_conforme(_oraculo_conforme(0.01), _familias(9), prueba)  # semiancho 0,000101
    assert cubre['cobertura_empirica'] == 1.0 and no_cubre['cobertura_empirica'] == 0.0
    assert cubre['denominadores']['prueba']['barras'] == sum(len(m.ids) for m in prueba)


def test_la_prediccion_no_afirma_cobertura_sin_justificar():
    """044:RF-8 — el intervalo sirve para negar (027:RF-13); el 90 % solo se dice si está sostenido."""
    from convertersmartgrid.digital_twin.oraculo import OraculoPINN

    assert OraculoPINN([], orc.Entrenamiento(), {}).cobertura_justificada is False


def test_evaluar_usa_las_particiones_del_modelo(tmp_path, monkeypatch):
    """044:RF-8 — el informe dice las particiones con que se midió, no las que saldrían hoy."""
    muestras, ids = _conjunto(random.Random(SEMILLA))
    bufer = BuferEpisodios(tmp_path)
    carpeta = bufer.raiz / 'modelos' / 'v1'
    carpeta.mkdir(parents=True)
    guardadas = {'entrenamiento': ids[:2], 'validacion': ids[2:4], 'calibracion': ids[4:6], 'prueba': ids[6:8]}
    (carpeta / 'modelo.json').write_text(json.dumps({'particiones_ids': guardadas,
        'evaluacion': {'politica_hash': 'h'}}), encoding='utf-8')
    monkeypatch.setattr(orc, '_muestras', lambda *_a: (muestras, ids))
    monkeypatch.setattr(orc, 'cargar', lambda *_a: _Doble([], orc.Entrenamiento(), {}, version='v1'))
    monkeypatch.setattr(orc, 'mae', lambda _m, _ms: 0.001)
    e = orc.evaluar(bufer)
    partes = {f['episodio']: f['particion'] for f in e['episodios']}
    assert [partes[i] for i in ids[:8]] == ['entrenamiento'] * 2 + ['validacion'] * 2 + ['calibracion'] * 2 + ['prueba'] * 2
    assert partes[ids[8]] == 'sin_asignar' and e['por_particion']['calibracion']['episodios'] == 2
    assert e['politica_hash'] == 'h' and e['unidades']['mae_modelo'] == 'p.u.' and 'guardado' in e['reparto']


def _hermanos(familias: int, variantes: int):
    """Variantes de demanda de cada familia, como las que genera la matriz de escenarios."""
    muestras, ids = [], []
    for f in range(familias):
        for v in range(variantes):
            grafo, tens = _red('S', 4, 0.7 + 0.1 * v, 1.0)
            muestras.append(orc.muestra(grafo, tens, f'fam-{f}'))
            ids.append(f'ep-{f}-{v}')
    return muestras, ids


def test_con_sistema_los_hermanos_no_cruzan_particiones():
    """044:RF-1 — por la huella de cada episodio, las variantes de una familia caían a los dos lados."""
    from convertersmartgrid.digital_twin.curva import reparto_del_sistema

    muestras, ids = _hermanos(30, 6)
    por_episodio = reparto_del_sistema(ids)
    familias_por_parte = [{muestras[i].familia for i in v} for v in por_episodio.values()]
    # El reproductor del fallo: sin familias, alguna cae en dos particiones.
    assert sum(len(f) for f in familias_por_parte) > 30
    grupos = orc._grupos(muestras, ids, 'sistema')
    familias = [{m.familia for m in ms} for ms in grupos.values()]
    assert sum(len(f) for f in familias) == 30 and sum(len(ms) for ms in grupos.values()) == len(muestras)


def test_entrenar_con_sistema_ya_no_choca_con_sus_hermanos(tmp_path, monkeypatch):
    """044:RF-1, 044:RF-2 — con ``sistema`` el motivo son las cuotas que faltan, no una familia cruzada."""
    muestras, ids = _hermanos(30, 6)
    monkeypatch.setattr(orc, '_muestras', lambda *_a: (muestras, ids))
    monkeypatch.setattr(orc, 'cargar', lambda *_a: pytest.fail('abrió el modelo sin cuotas'))
    r = orc.entrenar(BuferEpisodios(tmp_path), sistema=orc.red_de(muestras[0])[:12])
    assert not r['entrenado'] and r['status'] == 'BLOQUEADO_POR_DATOS'
    assert not any('familia compartida' in f for f in r['fallos']), r['fallos']
