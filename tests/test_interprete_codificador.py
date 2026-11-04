"""069 — intérprete sobre un codificador preentrenado con clase «ninguna».

Todo con un codificador falso inyectado, sobre la CPU y sin descargar nada; ningún texto real del operador (P9).
La medida de verdad es la ejecución única de ``tools/asistente_entrenar.py --integral``.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

torch = pytest.importorskip('torch')

from convertersmartgrid.asistente import codificador_ordenes as co                  # noqa: E402
from convertersmartgrid.asistente import destilacion_integral as di                 # noqa: E402
from convertersmartgrid.asistente import transformer as tr                          # noqa: E402
from convertersmartgrid.asistente.interprete import Interpretacion, interpretar     # noqa: E402
from convertersmartgrid.asistente.maestro_real import CALIDAD, NINGUNA, leer_ninguna  # noqa: E402
from convertersmartgrid.asistente.sinteticos import Ejemplo                         # noqa: E402
from convertersmartgrid.asistente.tareas import TAREAS                              # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CPU = torch.device('cpu')
PERFECTO = {'ejemplos': 200, 'acierto_tarea': 1., 'f1_datos': 1.}
RECHAZO_BUENO = {'ejemplos': 200, 'rechazada': .95, 'se_cuela': .01}


class CodificadorFalso:
    """Una pieza por palabra, con un vector que sale del hash de la palabra: determinista y sin red."""
    dim = 24

    def __init__(self, *_a):
        self.llamadas = 0

    def _vector(self, palabra: str):
        semilla = int(hashlib.sha256(palabra.casefold().encode('utf-8')).hexdigest()[:8], 16)
        return torch.randn(self.dim, generator=torch.Generator().manual_seed(semilla))

    def __call__(self, textos):
        import re
        self.llamadas += 1
        tokens, tramos, oraciones = [], [], []
        for t in textos:
            piezas = list(re.finditer(r'\S+', t))
            v = [self._vector(m.group()) for m in piezas] or [torch.zeros(self.dim)]
            tokens.append(torch.stack(v)[:len(piezas)])
            tramos.append([m.span() for m in piezas])
            oraciones.append(torch.nn.functional.normalize(torch.stack(v).mean(0), dim=-1))
        return co.Codificado(torch.stack(oraciones), tokens, tramos)


@pytest.fixture
def falso(monkeypatch, tmp_path):
    """Codificador falso, «GPU» en la CPU y un almacén vacío."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    monkeypatch.setattr(co, 'FABRICA', CodificadorFalso)
    monkeypatch.setattr(co, '_abiertos', {})
    monkeypatch.setattr(tr, 'dispositivo_de_calculo', lambda: CPU)
    monkeypatch.setattr(tr, 'liberar_gpu', lambda: None)
    monkeypatch.setattr(tr, '_cache', {})
    return tmp_path


def _pequeno():
    """Dos tareas y charla; con códigos para que la cabeza de datos tenga qué aprender."""
    filas = []
    for codigo in ('AB101', 'CD202', 'EF303', 'GH404', 'IJ505', 'KL606'):
        filas.append(Ejemplo(f'convierte {codigo}', 'convertir', [(10, 15, 'alimentadores')]))
        filas.append(Ejemplo(f'flujo de {codigo}', 'flujo', [(9, 14, 'alimentadores')]))
    filas += [Ejemplo('que hay cargado', 'estado', []), Ejemplo('dime el estado', 'estado', [])]
    filas += [Ejemplo(t, NINGUNA, []) for t in ('me parece bien', 'sigue asi nomas', 'gracias por todo')]
    return filas


def _entrenado(epocas=150, **kw):
    cod = CodificadorFalso()
    cfg = co.Configuracion(epocas=epocas, lote_tarea=8, lote_etiquetas=8, oculta_tarea=32, oculta_etiquetas=16, **kw)
    return co.entrenar(_pequeno(), cfg, cache=co.CacheCodificada(cod), dispositivo=CPU)


def _etiquetas(almacen: Path, filas) -> None:
    ruta = almacen / 'maestro_real' / 'etiquetas.jsonl'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in filas), encoding='utf-8')


def _charla(n: int):
    return [{'texto': f'mensaje de charla numero {i} sin orden', 'tarea': NINGUNA, 'datos': {}, 'confianza': .9,
             'quality': CALIDAD, 'maestro': 'claude', 'id': str(i)} for i in range(n)]


# ------------------------------------------------------------------ modelo

def test_modelo_contrato_de_predecir():
    """069:RF-1 / 069:RF-2 — mismos campos que ``ModeloOrdenes.predecir``, con la tarea aprendida y su dato."""
    m = _entrenado()
    p = m.predecir('convierte AB101')
    assert set(p) == {'tarea', 'confianza', 'alternativas', 'datos', 'modelo', 'version'}
    assert p['tarea'] == 'convertir' and 0 <= p['confianza'] <= 1 and p['modelo'] == 'transformer'
    assert [d['valor'] for d in p['datos']['alimentadores']] == ['AB101']
    assert all(len(a) == 2 and a[0] in TAREAS for a in p['alternativas'])


def test_modelo_no_da_datos_que_la_tarea_no_admite():
    """069:RF-3 — con una tarea sin datos, lo que marque la cabeza no se devuelve."""
    m = _entrenado()
    cod = m.codificador(['que hay AB101'])
    assert m._datos('que hay AB101', 'estado', cod) == {}


def test_modelo_pregunta_es_el_mensaje_entero():
    """069:RF-30 — no se marca un trozo, y el plan usa el mensaje entero."""
    m = _entrenado()
    assert m._datos('como se calibra AB101', 'pregunta', m.codificador(['como se calibra AB101'])) == {}
    from convertersmartgrid.asistente.plan import resolver
    plan = resolver(Interpretacion('como se calibra AB101', 'pregunta', 1., 'ensayo', {}), {})
    assert plan.datos['texto'] == 'como se calibra AB101'


def test_modelo_no_recorta_palabras_de_union():
    """069:RF-31 — el dato sale con todas sus palabras; el modelo heredado sigue recortando."""
    import numpy as np
    texto = 'convierte todos los alimentadores'
    p = np.zeros((len(texto), len(tr.ETIQUETAS)))
    p[:, 0] = 1
    i = tr.ETIQUETAS.index('I-alimentadores')
    p[10:, 0], p[10:, i] = 0, 1
    assert co.marcar_datos(texto, p, co._sin_signos)['alimentadores'][0]['valor'] == 'todos los alimentadores'
    assert tr._spans(texto, p)['alimentadores'][0]['valor'] == 'todos'


def test_modelo_todos_los_alimentadores_en_el_plan():
    """069:RF-32 — el plan lo toma por todos, no por un alimentador desconocido."""
    from convertersmartgrid.asistente.plan import resolver
    i = Interpretacion('convierte todos los alimentadores', 'convertir', 1., 'ensayo',
                       {'alimentadores': [{'valor': 'todos los alimentadores'}]})
    plan = resolver(i, {'alimentadores': ['AB101', 'CD202']})
    assert plan.datos['alimentadores'] == ['AB101', 'CD202'] and not plan.dudas


def test_modelo_artefactos_solo_cabezas_y_codificador_por_revision(falso):
    """069:RF-4 — ni un peso del codificador en el artefacto; su nombre y su revisión, en los metadatos."""
    m = _entrenado()
    di._guardar_alumno(m, falso / 'alumno', {'version': 'alumno'})
    pesos = torch.load(falso / 'alumno' / 'pesos.pt', weights_only=True)
    meta = json.loads((falso / 'alumno' / 'modelo.json').read_text(encoding='utf-8'))
    assert meta['codificador']['nombre'] == co.NOMBRE_CODIFICADOR
    assert meta['codificador']['revision'] == co.REVISION_CODIFICADOR and len(co.REVISION_CODIFICADOR) == 40
    assert {k.split('.')[0] for k in pesos} == {'tarea', 'reduce', 'secuencia', 'etiquetas'}
    assert NINGUNA in meta['tareas'] and meta['simbolos'] == {}


def test_modelo_codificador_solo_de_la_cache_local(monkeypatch):
    """069:RF-5 — se pide sin red; si no está, el error nombra el codificador."""
    import types
    pedidos = []

    def fallar(nombre, **kw):
        pedidos.append((nombre, kw))
        raise OSError('no está en la caché')
    falsa = types.SimpleNamespace(AutoModel=types.SimpleNamespace(from_pretrained=fallar),
                                  AutoTokenizer=types.SimpleNamespace(from_pretrained=fallar))
    monkeypatch.setitem(sys.modules, 'transformers', falsa)
    with pytest.raises(RuntimeError, match='intfloat/multilingual-e5-base'):
        co.CodificadorPreentrenado(co.NOMBRE_CODIFICADOR, co.REVISION_CODIFICADOR, CPU)
    assert pedidos[0][1] == {'revision': co.REVISION_CODIFICADOR, 'local_files_only': True}


def test_modelo_codificador_quita_el_prefijo_y_congela():
    """069:RF-1 — el prefijo de e5 no es de la orden: las posiciones son las del texto, y nada se entrena."""
    class Tok(dict):
        pass

    class Tokenizador:
        def __call__(self, textos, **_k):
            assert textos == ['query: corre AB101']
            n = 5
            return Tok(input_ids=torch.ones((1, n), dtype=torch.long), attention_mask=torch.ones((1, n), dtype=torch.long),
                       offset_mapping=torch.tensor([[(0, 0), (0, 6), (6, 12), (12, 18), (0, 0)]]))

    class Red(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.capa = torch.nn.Linear(2, 2)
            self.config = type('C', (), {'hidden_size': 4})

        def forward(self, input_ids, attention_mask):
            return type('S', (), {'last_hidden_state': torch.ones((*input_ids.shape, 4))})

    cod = object.__new__(co.CodificadorPreentrenado)
    cod.tokenizador, cod.red, cod.dispositivo, cod.dim = Tokenizador(), Red(), CPU, 4
    r = cod(['corre AB101'])
    assert r.tramos == [[(0, 5), (5, 11)]]
    assert r.tokens[0].shape == (2, 4) and abs(float(r.oraciones.norm()) - 1) < 1e-5


def test_modelo_sin_gpu_el_error_de_siempre(falso, monkeypatch):
    """069:RF-6 — ni entrenar ni reabrir ni cargar el modelo en uso caen a la CPU."""
    m = _entrenado()
    di._guardar_alumno(m, falso / 'alumno', {'version': 'alumno'})
    filas, meta = di.preparar_corpus({}, _humanas(), por_familia=1)
    di.guardar_corpus(falso / 'corpus', filas, meta)
    from convertersmartgrid.asistente import almacen
    carpeta = tr.raiz_modelos() / 'v1'
    carpeta.mkdir(parents=True)
    for n in ('pesos.pt', 'modelo.json'):
        (carpeta / n).write_bytes((falso / 'alumno' / n).read_bytes())
    tr.promover('v1', 'prueba')
    assert almacen.raiz().is_dir()

    def sin_gpu():
        raise RuntimeError('No hay GPU con CUDA')
    monkeypatch.setattr(tr, 'dispositivo_de_calculo', sin_gpu)
    monkeypatch.setattr(co, 'FABRICA', lambda *_a: pytest.fail('no debe abrir el codificador'))
    monkeypatch.setattr(co, '_abiertos', {})
    with pytest.raises(RuntimeError, match='CUDA'):
        di.entrenar_destilacion(falso / 'corpus', falso / 'run', semillas=(11,), log=lambda *_a, **_k: None)
    with pytest.raises(RuntimeError, match='CUDA'):
        di.cargar_alumno(falso / 'alumno')
    with pytest.raises(RuntimeError, match='CUDA'):
        tr.cargar()


def test_modelo_heredado_y_nuevo_cargan_por_el_mismo_puntero(falso):
    """069:RF-7 / 069:RF-8 — el puntero decide; cada uno se abre con su arquitectura."""
    cfg = tr.Configuracion(dim=8, capas=1, cabezas=2, epocas=1)
    red = tr.construir_red(4, {'tarea': len(TAREAS)}, cfg, len(tr.ETIQUETAS))
    version = tr.guardar(tr.ModeloOrdenes(red, {'a': 3}, sorted(TAREAS), cfg), {})
    tr.promover(version, 'heredado')
    assert isinstance(tr.cargar(), tr.ModeloOrdenes)

    from convertersmartgrid.asistente import almacen, modelos_en_uso
    from convertersmartgrid.model_registry import RegistroModelo
    nuevo = _entrenado()
    nuevo.umbral = .75
    di._guardar_alumno(nuevo, falso / 'alumno', {'version': 'alumno'})
    registro = RegistroModelo(almacen.raiz() / 'model_registry')
    c = registro.registrar_candidato(
        'transformer', model_manifest={'algorithm': 'x'}, dataset_manifest={}, metrics={},
        decision={'status': 'PROMOVIDO', 'gates': {'approved': True}, 'fallos': []}, smoke_reload={'ok': True},
        artifacts=[falso / 'alumno' / 'pesos.pt', falso / 'alumno' / 'modelo.json'])
    r = modelos_en_uso.aplicar_decision('transformer', c)
    assert r['promovido'] and tr.version_promovida() == r['version']
    cargado = tr.cargar()
    assert isinstance(cargado, co.ModeloCodificador) and cargado.umbral == .75
    assert cargado.predecir('convierte AB101')['tarea'] == nuevo.predecir('convierte AB101')['tarea']
    assert modelos_en_uso.volver_al_anterior('transformer') == version
    assert isinstance(tr.cargar(), tr.ModeloOrdenes)


def test_modelo_reabierto_predice_igual(falso):
    """069:RF-9 — la comprobación de reapertura vale con el modelo nuevo y con otras predicciones falla."""
    m = _entrenado()
    di._guardar_alumno(m, falso / 'alumno', {'version': 'alumno'})
    textos = ['convierte AB101', 'que hay cargado']
    ruta = falso / 'alumno' / 'readback.json'
    ruta.write_text(json.dumps({'textos': textos, 'predicciones': [m.predecir(t) for t in textos]}), encoding='utf-8')
    assert di.verificar_reapertura(falso / 'alumno')['ok']
    prueba = json.loads(ruta.read_text(encoding='utf-8'))
    prueba['predicciones'][0]['tarea'] = 'flujo'
    ruta.write_text(json.dumps(prueba), encoding='utf-8')
    assert not di.verificar_reapertura(falso / 'alumno')['ok']


def test_modelo_reapertura_aguanta_la_salida_del_codificador():
    """069:RF-9 — la barra de carga escribe bytes que cp1252 no lee: la primera ejecución real se cayó ahí."""
    from convertersmartgrid.model_registry import reabrir_en_subproceso
    codigo = ('import sys; sys.stderr.buffer.write(bytes([0x8f, 0xe2, 0x96, 0x88])); sys.stderr.flush(); '
              'print(\'{"ok": true}\')')
    r = reabrir_en_subproceso([sys.executable, '-c', codigo])
    assert r['ok'] and isinstance(r['stderr'], str)


def test_modelo_codifica_cada_frase_una_vez():
    """069:RF-28 — los candidatos comparten frases: no se repite el codificador."""
    cod = CodificadorFalso()
    cache = co.CacheCodificada(cod)
    cache.asegurar(['a b', 'c d', 'a b'])
    n = cod.llamadas
    cache.asegurar(['a b', 'c d'])
    assert cod.llamadas == n and cache.filas['a b'][1].dtype == torch.float16


def test_modelo_etiquetas_por_token_en_varias_piezas():
    """069:RF-1 — un dato partido en piezas es B- y luego I-, y lo demás es O."""
    e = Ejemplo('corre AB101 ya', 'flujo', [(6, 11, 'alimentadores')])
    etq = co.etiquetas_por_token(e, [(0, 5), (5, 8), (8, 11), (11, 14)])
    assert [tr.ETIQUETAS[i] for i in etq] == ['O', 'B-alimentadores', 'I-alimentadores', 'O']


# ------------------------------------------------------------------ ninguna

def test_ninguna_reparto_por_hash(tmp_path):
    """069:RF-11 — determinista, en torno al 30 %, y dos formas del mismo mensaje caen del mismo lado."""
    filas = _charla(400)
    _etiquetas(tmp_path, [*filas, {**filas[0], 'texto': filas[0]['texto'].upper() + '!'}])
    entrenar, reservados = leer_ninguna(tmp_path)
    assert len(entrenar) + len(reservados) == 400 and .22 < len(reservados) / 400 < .38
    assert not set(entrenar) & set(reservados)
    assert (entrenar, reservados) == leer_ninguna(tmp_path)
    _etiquetas(tmp_path, list(reversed(filas)))
    assert leer_ninguna(tmp_path)[1] == reservados


def test_ninguna_no_admite_otra_calidad(tmp_path):
    """069:RF-10 — este fichero es plata del maestro: una fila de otra calidad no entra."""
    _etiquetas(tmp_path, [{**_charla(1)[0], 'quality': 'gold_human'}])
    assert leer_ninguna(tmp_path) == ([], [])


def test_ninguna_solo_en_entrenamiento_como_plata():
    """069:RF-10 / 069:RF-11 — plata del maestro en el ajuste; los reservados, en ninguna fila."""
    entrenar, reservar = ['esto es una charla cualquiera', 'otra charla mas'], ['charla reservada aparte']
    filas, meta = di.preparar_corpus({}, [], por_familia=1, ninguna=entrenar, ninguna_reservada=reservar)
    n = [r for r in filas if r['tarea'] == NINGUNA]
    assert {r['texto'] for r in n} == set(entrenar)
    assert all(r['particion'] == 'entrenamiento' and r['quality'] == CALIDAD and r['del_maestro'] for r in n)
    assert not [r for r in filas if r['texto'] in reservar]
    assert meta['ninguna']['filas'] == 2 and meta['rechazo_reservado']['ejemplos'] == 1
    assert meta['denominadores']['entrenamiento'][CALIDAD] == 2


def test_ninguna_sin_fuga_hacia_lo_sellado():
    """069:RF-12 — lo que coincide con prueba, selección u orden humana no entrena, con signos o mayúsculas."""
    base, _ = di.preparar_corpus({}, [], por_familia=2)
    prueba = next(r for r in base if r['particion'] == 'prueba' and not r['datos'])['texto']
    seleccion = next(r for r in base if r['particion'] == 'seleccion' and not r['datos'])['texto']
    humanas = [{'texto': 'Carga la fuente', 'tarea': 'cargar_fuente', 'datos': [], 'origen': 'confirmado'}]
    filas, meta = di.preparar_corpus({}, humanas, por_familia=2, ninguna=[prueba.upper() + '?', seleccion + ' !', 'carga la fuente'])
    assert not [r for r in filas if r['tarea'] == NINGUNA]
    assert meta['ninguna']['excluidos_por_fuga'] == 3


def test_ninguna_deja_identico_lo_sellado():
    """069:RF-13 — las filas de selección, calibración y prueba, y las fijas, no cambian."""
    from convertersmartgrid.asistente import ordenes_fijas as of
    from convertersmartgrid.evaluacion_modelos import huella
    vocab = {'alimentadores': ['AB101'], 'proyecto': ['Proyecto X']}
    sin, _ = di.preparar_corpus(vocab, [], por_familia=3, ampliar=False)
    con, _ = di.preparar_corpus(vocab, [], por_familia=3, ninguna=['charla de mas'], ninguna_reservada=['otra charla'])
    sellado = lambda filas: {r['record_id']: r for r in filas if r['particion'] != 'entrenamiento'}   # noqa: E731
    assert sellado(sin) == sellado(con)
    assert of.huella(of.generar({})) == '41f7ab110ac35c0b'
    assert huella(sorted(r['record_id'] for r in di.preparar_corpus({}, [], por_familia=5, ninguna=['charla de mas'])[0]
                         if di.es_historica(r))) == '415e425a481ddfb0bd3af7bdeb042cf82fa3f23fda1ef97f95b8b2f955d502f3'


def test_ninguna_no_cuenta_como_humana():
    """069:RF-14 — ni como orden humana independiente ni en la prueba."""
    filas, meta = di.preparar_corpus({}, [], por_familia=1, ninguna=['charla de mas'])
    assert meta['ordenes_humanas_independientes'] == 0 and 'gold_human' not in meta['calidades']
    assert CALIDAD not in meta['denominadores']['prueba']


def test_ninguna_guardada_y_releida_con_custodia(tmp_path):
    """069:RF-10 / 069:RF-11 — el corpus se relee; un reservado alterado no se acepta."""
    filas, meta = di.preparar_corpus({}, [], por_familia=1, ninguna=['charla de mas'], ninguna_reservada=['b', 'a'])
    di.guardar_corpus(tmp_path, filas, meta, ['b', 'a'])
    releidas, m = di.leer_corpus(tmp_path)
    assert di.leer_reservados(tmp_path, m) == ['a', 'b'] and any(r['tarea'] == NINGUNA for r in releidas)
    assert 'a' not in json.dumps(m['rechazo_reservado']['ejemplos'])
    (tmp_path / di.ARCHIVO_RESERVADOS).write_text('["otra"]', encoding='utf-8')
    with pytest.raises(ValueError, match='integridad'):
        di.leer_reservados(tmp_path, m)


def test_ninguna_fuera_del_entrenamiento_no_se_acepta(tmp_path):
    """069:RF-10 — un corpus con «ninguna» en la prueba no se relee."""
    from convertersmartgrid.evaluacion_modelos import huella
    filas, meta = di.preparar_corpus({}, [], por_familia=1, ninguna=['charla de mas'])
    fila = next(r for r in filas if r['tarea'] == NINGUNA)
    fila['particion'] = 'prueba'
    fila['record_id'] = huella({k: v for k, v in fila.items() if k != 'record_id'})
    meta['dataset_hash'] = huella(filas)
    di.guardar_corpus(tmp_path, filas, meta)
    with pytest.raises(ValueError, match='calidad no admitida'):
        di.leer_corpus(tmp_path)


class Respuesta:
    """Un modelo que siempre dice lo mismo."""

    def __init__(self, tarea, confianza=.99, umbral=None, datos=None):
        self.tarea, self.confianza, self.datos, self.version, self.tareas = tarea, confianza, datos or {}, 'v', co.tareas_del_modelo()
        if umbral is not None:
            self.umbral = umbral

    def predecir(self, _texto):
        return {'tarea': self.tarea, 'confianza': self.confianza, 'alternativas': [('estado', .01)],
                'datos': self.datos, 'modelo': 'transformer', 'version': self.version}


def test_ninguna_deja_la_orden_sin_tarea_y_no_pregunta_a_otro():
    """069:RF-15 — no se adivina ni se consulta a Ollama: el plan le pregunta al operador."""
    class Ollama:
        modelo = 'x'

        def interpretar(self, *_a, **_k):
            pytest.fail('con «ninguna» no se consulta a otro modelo')
    i = interpretar('me parece bien', transformer=Respuesta(NINGUNA), ollama=Ollama())
    assert i.tarea is None and i.datos == {} and i.modelo == 'ninguno' and i.razon
    from convertersmartgrid.asistente.plan import resolver
    plan = resolver(i, {})
    assert plan.tarea is None and not plan.listo and not plan.escribe


def test_ninguna_no_se_ofrece_como_alternativa():
    """069:RF-16 — las alternativas son tareas que se pueden elegir."""
    m = _entrenado()
    for texto in ('convierte AB101', 'me parece bien', 'palabras nunca vistas'):
        assert all(a[0] in TAREAS for a in m.predecir(texto)['alternativas'])


# ------------------------------------------------------------------ rechazo

def _familias():
    return {t: dict(PERFECTO) for t in TAREAS}


def test_rechazo_aprueba_con_las_dos_tasas_en_regla():
    """069:RF-17 / 069:RF-18 — con todo en regla, el candidato pasa."""
    f = _familias()
    assert di.decidir_promocion(PERFECTO, PERFECTO, f, f, RECHAZO_BUENO)['status'] == 'PROMOVIDO'


@pytest.mark.parametrize('malo, frase', [({'rechazada': .89}, 'ninguna recoge'), ({'se_cuela': .03}, 'se cuela')])
def test_rechazo_cada_tasa_es_puerta(malo, frase):
    """069:RF-17 / 069:RF-18 — una tasa mala rechaza aunque el resto sea perfecto."""
    f = _familias()
    r = di.decidir_promocion(PERFECTO, PERFECTO, f, f, {**RECHAZO_BUENO, **malo})
    assert r['status'] == 'RECHAZADO' and not r['gates']['approved'] and any(frase in x for x in r['fallos'])


@pytest.mark.parametrize('rechazo', [None, {**RECHAZO_BUENO, 'ejemplos': 99}])
def test_rechazo_sin_medir_o_con_pocos_no_aprueba(rechazo):
    """069:RF-19 — sin medida o con menos de 100 mensajes no se aprueba."""
    f = _familias()
    assert di.decidir_promocion(PERFECTO, PERFECTO, f, f, rechazo)['status'] == 'RECHAZADO'


def test_rechazo_medido_sin_guardar_texto():
    """069:RF-20 / 069:RF-21 — tasas y denominador; ni rastro del mensaje."""
    r = di.medir_rechazo(Respuesta('flujo', .9, umbral=.85), ['mensaje privado uno', 'mensaje privado dos'])
    assert r['ejemplos'] == 2 and r['rechazada'] == 0 and r['se_cuela'] == 1 and r['umbral'] == .85
    assert 'privado' not in json.dumps(r)
    assert di.medir_rechazo(Respuesta(NINGUNA), ['a'])['rechazada'] == 1
    assert di.medir_rechazo(Respuesta('flujo', .8), ['a'])['se_cuela'] == 0     # bajo el 0,85 del heredado
    with pytest.raises(ValueError):
        di.medir_rechazo(Respuesta('flujo'), [])


def test_rechazo_no_relaja_las_puertas_de_antes():
    """069:RF-22 — con el rechazo perfecto, las puertas existentes siguen mandando; la política no cambia."""
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion
    f = _familias()
    bueno = {'ejemplos': 200, 'rechazada': 1., 'se_cuela': 0.}
    assert di.decidir_promocion(PERFECTO, PERFECTO, {**f, 'flujo': {**PERFECTO, 'acierto_tarea': .94}}, f, bueno)['status'] == 'RECHAZADO'
    assert di.decidir_promocion(PERFECTO, PERFECTO, {**f, 'flujo': {**PERFECTO, 'f1_datos': .84}}, f, bueno)['status'] == 'RECHAZADO'
    assert di.decidir_promocion(PERFECTO, {**PERFECTO, 'acierto_tarea': .97}, f, f, bueno)['status'] == 'RECHAZADO'
    assert di.decidir_promocion(PERFECTO, {**PERFECTO, 'f1_datos': .94}, f, f, bueno)['status'] == 'RECHAZADO'
    p = PoliticaEvaluacion(modo='agente')
    assert dict(p.puertas_por_familia) == {'acierto_tarea': .95, 'f1_datos': .85}
    assert p.hash == 'd996a254903807e96892d08469947dc43b7be10124a8653cb17ff960ea47e894'


# ------------------------------------------------------------------ calibración

def test_calibra_temperatura_solo_con_calibracion():
    """069:RF-23 — otra partición no vale; con la suya, el modelo nuevo se calibra."""
    m = _entrenado()
    fila = {'texto': 'convierte AB101', 'tarea': 'convertir', 'particion': 'calibracion', 'record_id': 'x'}
    with pytest.raises(ValueError, match='calibración'):
        di.calibrar_temperatura(m, [{**fila, 'particion': 'prueba'}])
    r = di.calibrar_temperatura(m, [fila])
    assert m.temperatura == r['temperatura'] > 0


def _calibracion(n_ok, n_mal):
    return ([{'texto': 'x', 'tarea': 'flujo', 'particion': 'calibracion'}] * n_ok +
            [{'texto': 'x', 'tarea': 'estado', 'particion': 'calibracion'}] * n_mal)


class Variable:
    """Una respuesta por llamada: así se prueba el umbral sin un modelo."""

    def __init__(self, confianzas):
        self.confianzas, self.i, self.umbral = confianzas, 0, .85

    def predecir(self, _t):
        c = self.confianzas[self.i]
        self.i += 1
        return {'tarea': 'flujo', 'confianza': c, 'datos': {}, 'alternativas': []}


def test_calibra_umbral_el_menor_que_acierta_el_98():
    """069:RF-24 — los errores están en confianza baja: el umbral sube hasta dejarlos fuera."""
    filas = _calibracion(99, 3)
    m = Variable([.99] * 99 + [.87] * 3)
    r = di.calibrar_umbral(m, filas)
    assert r['umbral'] == .9 and m.umbral == .9
    assert r['por_umbral']['0.85']['acierto'] < .98 <= r['por_umbral']['0.9']['acierto']
    assert di.calibrar_umbral(Variable([.99] * 99), _calibracion(99, 0))['umbral'] == .85    # nunca por debajo


def test_calibra_umbral_si_ninguno_llega_el_mas_alto():
    """069:RF-25 — si ningún umbral acierta el 98 %, el más exigente."""
    m = Variable([.99] * 10 + [.99] * 10)
    assert di.calibrar_umbral(m, _calibracion(10, 10))['umbral'] == .95
    with pytest.raises(ValueError, match='calibración'):
        di.calibrar_umbral(m, [{'texto': 'x', 'tarea': 'flujo', 'particion': 'prueba'}])


def test_calibra_el_interprete_usa_el_umbral_del_modelo():
    """069:RF-26 — .75 pasa con umbral .70 y no pasa con el fijo de los heredados."""
    assert interpretar('x', transformer=Respuesta('estado', .75, umbral=.70)).tarea == 'estado'
    assert interpretar('x', transformer=Respuesta('estado', .75)).tarea is None
    assert interpretar('x', transformer=Respuesta('estado', .75, umbral=.70), umbral=.9).tarea is None


def test_calibra_cobertura_por_umbral():
    """069:RF-27 — cuánto cubre y cuánto acierta; «ninguna» no cubre."""
    filas = [{'texto': 'x', 'tarea': 'flujo'}] * 2
    c = di.cobertura_por_umbral(Respuesta('flujo', .8), filas, (.5, .9))
    assert c['0.5'] == {'cobertura': 1., 'acierto': 1., 'cubiertos': 2} and c['0.9']['cubiertos'] == 0
    assert di.cobertura_por_umbral(Respuesta(NINGUNA), filas, (.5,))['0.5']['cubiertos'] == 0


# ------------------------------------------------------------------ integral

def _humanas():
    return [{'texto': 'carga la fuente', 'tarea': 'cargar_fuente', 'datos': [], 'origen': 'confirmado'}]


def test_integral_de_punta_a_punta_con_codificador_falso(falso, monkeypatch):
    """069:RF-1 / 069:RF-20 / 069:RF-21 / 069:RF-27 / 069:RF-28 — el protocolo real, con todas sus medidas y sin textos reservados."""
    import convertersmartgrid.model_registry as mr
    monkeypatch.setattr(mr, 'reabrir_en_subproceso', lambda *_a, **_k: {'ok': True})
    reservados = [f'secreto reservado {i}' for i in range(120)]
    filas, meta = di.preparar_corpus({}, _humanas(), por_familia=1, ninguna=['charla uno de mas', 'charla dos de mas'],
                                     ninguna_reservada=reservados)
    di.guardar_corpus(falso / 'corpus', filas, meta, reservados)
    cfg = co.Configuracion(epocas=3, lote_tarea=64, lote_etiquetas=64, oculta_tarea=16, oculta_etiquetas=8)
    r = di.entrenar_destilacion(falso / 'corpus', falso / 'run', cfg=cfg, semillas=(11,), registro=falso / 'reg', log=lambda *_a, **_k: None)
    assert r['training_completed'] and r['rechazo']['ejemplos'] == 120 and r['candidato']['status'] in {'RECHAZADO', 'PROMOVIDO'}
    assert set(r['cobertura']) >= {'0.85'} and 'umbral' in r['calibracion']
    assert r['denominadores']['entrenamiento'][CALIDAD] >= 2
    salida = json.dumps(r, ensure_ascii=False, default=str)
    assert 'secreto' not in salida
    registrados = ''.join(p.read_text(encoding='utf-8') for p in (falso / 'reg').rglob('*.json'))
    assert 'secreto' not in registrados
    meta_alumno = json.loads((falso / 'run' / 'alumno' / 'modelo.json').read_text(encoding='utf-8'))
    assert meta_alumno['arquitectura'] == co.ARQUITECTURA and meta_alumno['umbral'] == r['calibracion']['umbral']


def test_integral_compara_con_el_modelo_en_uso(falso):
    """069:RF-20 / 069:RF-27 — el heredado da las mismas medidas; un fallo se dice, no se oculta."""
    cfg = tr.Configuracion(dim=8, capas=1, cabezas=2, epocas=1)
    red = tr.construir_red(4, {'tarea': len(TAREAS)}, cfg, len(tr.ETIQUETAS))
    tr.promover(tr.guardar(tr.ModeloOrdenes(red, {'a': 3}, sorted(TAREAS), cfg), {}), 'heredado')
    filas = [{'texto': 'convierte AB101', 'tarea': 'convertir', 'datos': []}]
    r = di._medir_en_uso(filas, filas, ['charla'])
    assert r['rechazo']['ejemplos'] == 1 and r['rechazo']['rechazada'] == 0
    assert r['sinteticas']['ejemplos'] == 1 and '0.85' in r['cobertura']


def test_integral_herramientas_leen_los_mensajes_ninguna(tmp_path):
    """069:RF-28 — ``preparar`` usa el almacén; la herramienta web, también."""
    import os
    datos = tmp_path / 'datos'
    _etiquetas(datos, _charla(50))
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'CSG_ASISTENTE_DATA': str(datos), 'PYTHONPATH': str(RAIZ / 'src')}
    r = subprocess.run([sys.executable, str(RAIZ / 'tools/asistente_destilar.py'), 'preparar', '--destino', str(tmp_path / 'c'),
                        '--por-familia', '1'], env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert r.returncode == 0, r.stderr + r.stdout
    salida = json.loads(r.stdout.splitlines()[-1])
    assert salida['ninguna']['leidos'] + salida['rechazo_reservado']['ejemplos'] == 50
    assert (tmp_path / 'c' / di.ARCHIVO_RESERVADOS).is_file()
    fuente = (RAIZ / 'tools/asistente_entrenar.py').read_text(encoding='utf-8')
    assert 'ninguna_reservada=' in fuente and 'codificador_ordenes.Configuracion' in fuente


def test_integral_frases_de_tareas_flojas_solo_entrenan():
    """069:RF-29 — las tareas flojas tienen más frases, y estas solo van al ajuste."""
    from convertersmartgrid.asistente.curriculo_maestro import ESTILO_REAL
    for tarea in TAREAS_FLOJAS:
        assert len(ESTILO_REAL[tarea]) >= 20
    filas, _ = di.preparar_corpus({}, [], por_familia=2)
    estilo = [r for r in filas if r.get('origen_curriculo') == 'estilo_real']
    assert {r['tarea'] for r in estilo} >= set(TAREAS_FLOJAS)
    assert {r['particion'] for r in estilo} == {'entrenamiento'}


TAREAS_FLOJAS = ('flujo', 'episodios', 'estado', 'evaluar_gemelo', 'gemelo_entrenar')


def test_integral_interpretacion_sigue_igual_para_el_plan():
    """069:RF-2 — el plan recibe la misma ``Interpretacion`` con un modelo nuevo."""
    m = _entrenado()
    m.umbral = .5
    i = interpretar('convierte AB101', transformer=m)
    assert isinstance(i, Interpretacion) and i.tarea == 'convertir' and i.modelo == 'transformer'
