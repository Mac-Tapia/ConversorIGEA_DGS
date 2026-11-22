"""Spec 045, RF-15 a RF-17: el híbrido física + red no empeora a la física, sin entrenar ni construir la red.

La ablación del 2026-11-21 dejó el híbrido en 5,25·10⁻⁴ p.u. frente a 2,07·10⁻⁴ de la física, con residuo 0,073 sobre
el tope 0,05 en cuatro de cinco familias. Aquí, con numpy y dobles: la regla de elección de época, la guarda de la
predicción, la retirada del modelo en uso y la elección de la ablación. La red se prueba en
``test_gemelo_hibrido_acotado_red.py``, y la medida con datos reales es la 045 T6.
"""
from __future__ import annotations

import json
import random

import numpy as np
import pytest
from test_benchmark_pinn import (  # noqa: F401 - fixture del módulo vecino
    _ajustador,
    _experimento,
    bufer,
)
from test_benchmark_pinn import _red as red_radial

from convertersmartgrid.adaptadores.digital_twin import benchmark_fisico as bf
from convertersmartgrid.adaptadores.digital_twin import oraculo as orc
from convertersmartgrid.adaptadores.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.aplicacion import conjuntos_aprendizaje as ca
from convertersmartgrid.dominio.contratos_aprendizaje import CicloBloqueado

TOPE = orc.Puertas().residuo_max


def _muestra(semilla: int = 3, n: int = 12) -> orc.Muestra:
    g = red_radial(random.Random(semilla), n, semilla)
    p = orc.ModeloMallado().predecir(g)
    return orc.muestra(g, dict(zip(p['ids'], map(float, p['v']), strict=True)))


def test_una_epoca_solo_sustituye_si_mejora_sin_pasar_el_tope():
    """045:RF-15 — menor error no basta: con el residuo sobre el tope de 044 la época no se elige."""
    fn = getattr(orc, 'mejora_admisible', None)
    assert fn is not None, 'la época se elige solo por el error de tensión'
    assert fn(1.0e-4, 0.01, 2.0e-4, TOPE)
    assert not fn(1.0e-4, 0.073, 2.0e-4, TOPE)
    assert not fn(2.0e-4, 0.0, 2.0e-4, TOPE)
    assert not fn(3.0e-4, 0.0, 2.0e-4, TOPE)


def test_la_guarda_nunca_empeora_una_fisica_que_ya_pasa_el_tope():
    """045:RF-16 — si la base ya pasa del tope (no converge), el listón es su residuo: la corrección no lo empeora."""
    fn = getattr(orc, 'acotar_correccion', None)
    assert fn is not None, 'ninguna guarda acota la corrección al predecir'
    m = _muestra(6)
    p = orc.ModeloMallado().predecir_muestra(m)
    libres = ~m.fuente
    base = np.stack([p['v'] - 0.05 * libres, p['theta']], axis=1)       # una base mala, con residuo alto
    r_base = float(np.mean(orc.residuo(m, *orc.imponer_fronteras(m, base[:, 0], base[:, 1]))))
    assert r_base > TOPE
    _v, _th, escala, r = fn(m, base[:, 0] - 0.08 * libres, base[:, 1], base, TOPE)
    assert float(np.mean(r)) <= r_base + 1e-12 and escala < 1.0
    v2, _th2, escala2, _r2 = fn(m, p['v'], p['theta'], base, TOPE)
    assert escala2 == 1.0 and np.array_equal(v2, p['v'])


class _EnUso:
    """Un modelo en uso que se aparta de la física un ``desvio`` fijo en las barras libres."""

    version = 'v-en-uso'

    def __init__(self, desvio: float, fuera: bool = False):
        self.desvio, self.fuera = desvio, fuera

    def fuera_de_dominio(self, _m):
        return ['otra red'] if self.fuera else []

    def predecir(self, grafo):
        p = orc.ModeloMallado().predecir(grafo)
        return {**p, 'v': np.where(p['v'] > 0, p['v'] + self.desvio, p['v'])}


def _puntero(bufer_: BuferEpisodios, version: str = 'v-en-uso') -> None:
    raiz = bufer_.raiz / 'modelos'
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / 'promovido.json').write_text(json.dumps({'version': version}), encoding='utf-8')


@pytest.fixture
def sin_conjunto(monkeypatch):
    monkeypatch.setattr(ca, 'exigir_sin_conjunto', lambda **_k: None)
    monkeypatch.setattr(ca, 'miembro_en_uso', lambda *_a, **_k: None)


def test_peor_que_la_fisica_lo_dice_con_su_motivo():
    """045:RF-17 — el modelo en uso deja de opinar si no mejora a la física o deja el residuo sobre el tope."""
    fn = getattr(orc, 'en_uso_peor_que_fisica', None)
    assert fn is not None, 'nada compara el modelo en uso con la física tras un candidato rechazado'
    puertas = orc.Puertas()
    assert fn(1.0e-4, 2.0e-4, 0.01, puertas) == []
    assert any('no mejora al flujo físico' in x for x in fn(5.25e-4, 2.07e-4, 0.01, puertas))
    assert any('residuo' in x for x in fn(1.0e-4, 2.0e-4, 0.073, puertas))
    assert fn(None, 2.0e-4, None, puertas) == []


def test_el_modelo_en_uso_peor_que_la_fisica_se_retira(tmp_path, sin_conjunto):
    """045:RF-17 — en el ciclo continuo, un modelo en uso peor que la física se retira y decide la física."""
    fn = getattr(orc, 'retirar_si_peor_que_fisica', None)
    assert fn is not None, 'el modelo en uso sigue decidiendo aunque sea peor que la física'
    b = BuferEpisodios(tmp_path / 'twin')
    _puntero(b)
    prueba = [_muestra(s) for s in (7, 8)]
    r = fn(b, _EnUso(0.01), prueba, orc.ModeloMallado(), orc.Puertas())
    assert r and r['retirado'] is True and r['motivos']
    assert orc.cargar(b) is None
    fila = json.loads((b.raiz / 'modelos' / 'historial.jsonl').read_text(encoding='utf-8').splitlines()[-1])
    assert fila['version'] is None and fila['anterior'] == 'v-en-uso' and fila['motivo'].startswith('retirado:')


def test_fuera_de_su_dominio_o_con_un_conjunto_no_se_retira_aqui(tmp_path, sin_conjunto, monkeypatch):
    """045:RF-17 — solo cuentan las redes en que opina; con un conjunto activo, la retirada es del conjunto."""
    fn = getattr(orc, 'retirar_si_peor_que_fisica', None)
    assert fn is not None, 'el modelo en uso sigue decidiendo aunque sea peor que la física'
    b = BuferEpisodios(tmp_path / 'twin')
    _puntero(b)
    prueba = [_muestra(9)]
    assert fn(b, _EnUso(0.01, fuera=True), prueba, orc.ModeloMallado(), orc.Puertas()) is None
    assert (b.raiz / 'modelos' / 'promovido.json').is_file()

    def bloqueado(**_k):
        raise CicloBloqueado('Hay un conjunto activo')

    monkeypatch.setattr(ca, 'exigir_sin_conjunto', bloqueado)
    r = fn(b, _EnUso(0.01), prueba, orc.ModeloMallado(), orc.Puertas())
    assert r['retirado'] is False and 'conjunto' in r['pendiente']
    assert (b.raiz / 'modelos' / 'promovido.json').is_file()


def test_la_ablacion_dice_que_decide_la_fisica_si_el_hibrido_no_pasa():
    """045:RF-17 — con los números del 2026-11-21, el brazo en uso es la física; con un híbrido que pasa, el híbrido."""
    fn = getattr(bf, 'eleccion_en_uso', None)
    assert fn is not None, 'la ablación no dice qué brazo quedaría en uso'
    brazos = {'fisica_pura': {'estado': 'evaluado', 'mae_v': 2.07e-4, 'veredicto': {'approved': True}},
              'red_sin_fisica': {'estado': 'evaluado', 'mae_v': 3.12e-4, 'veredicto': {'approved': False}},
              'hibrido_vigente': {'estado': 'evaluado', 'mae_v': 5.25e-4, 'veredicto': {'approved': False}},
              'powerflownet': {'estado': 'no_disponible'}}
    e = fn(brazos)
    assert e['brazo'] == 'fisica_pura' and e['rechazados'] == ['hibrido_vigente', 'red_sin_fisica']
    brazos['hibrido_vigente'] = {'estado': 'evaluado', 'mae_v': 1.5e-4, 'veredicto': {'approved': True}}
    assert fn(brazos)['brazo'] == 'hibrido_vigente'
    brazos['hibrido_vigente']['mae_v'] = 2.07e-4                         # empate: la física, que no corrige
    assert fn(brazos)['brazo'] == 'fisica_pura'


def test_la_ablacion_usa_el_tope_de_sus_puertas_y_lo_informa(bufer, monkeypatch):  # noqa: F811
    """045:RF-15, 045:RF-17 — cada brazo con red se elige con el tope de residuo de sus puertas y el informe dice el brazo."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: 'sin PyG')
    monkeypatch.setattr(orc, 'dispositivo', lambda *_a: 'cpu')   # este módulo no lleva la marca gpu (106:RF-9): la ablación corre en CPU
    llamadas: list = []
    puertas = orc.Puertas(residuo_max=0.04)
    r = bf.comparar_fisicas(_experimento(), orc.particiones_del_bufer(bufer), bufer=bufer, puertas=puertas,
                            ajustar=_ajustador(llamadas))
    assert llamadas and all(getattr(c['cfg'], 'residuo_tope', None) == 0.04 for c in llamadas)
    assert r.get('eleccion', {}).get('brazo') == 'fisica_pura'


class _OraculoDoble:
    """Un oráculo que, con la carga alta, recorta la corrección (dentro de su dominio) o sale más lejos de lo aprendido
    (fuera de él). La dispersión de los miembros es la misma en las dos cargas, casi nula, como en la T6."""

    def __init__(self, fuera: bool):
        self.fuera = fuera

    def predecir(self, grafo):
        carga = sum(float(d.get('p_mw') or 0.0) for d in grafo['nodos'].values())
        alta = carga > 10.0
        n = len(grafo['nodos'])
        return {'incertidumbre': np.full(n, 2e-8), 'fuera_de_dominio': self.fuera,
                'escala_correccion': 0.0 if alta or self.fuera else 1.0,
                'fraccion_fuera_de_dominio': (0.9 if alta else 0.0) if self.fuera else 0.0}


@pytest.mark.parametrize('fuera', [False, True])
def test_la_incertidumbre_distingue_la_carga_aunque_la_guarda_recorte(monkeypatch, fuera):
    """045:RF-16 — el aprendizaje activo sigue distinguiendo la carga: una corrección recortada por la guarda y una red
    más lejos de lo aprendido suman, no se esconden. En la T6, f(1,0) = 1,00000002 y f(30) = 1,0 (MEJ30, 2026-11-21)."""
    from convertersmartgrid.adaptadores.digital_twin.escenarios import Escenario

    monkeypatch.setattr(orc, 'cargar', lambda _b=None, *_a, **_k: _OraculoDoble(fuera))
    g = red_radial(random.Random(4), 12, 4)
    f = orc.incertidumbre_de_escenarios(g, BuferEpisodios.__new__(BuferEpisodios))
    assert f(Escenario(1.0)) >= 0 and f(Escenario(30.0)) > f(Escenario(1.0)), (f(Escenario(1.0)), f(Escenario(30.0)))


def test_la_fraccion_fuera_de_rango_crece_con_la_carga():
    """045:RF-9, 045:RF-16 — cuánto se sale una red de lo aprendido, de 0 a 1: 0 en su rango y más con más carga."""
    fn = getattr(orc, 'fraccion_fuera_de_rango', None)
    assert fn is not None, 'solo se sabe si una red está fuera, no cuánto'
    m = _muestra(10)
    dominio = {'x_min': m.x.min(axis=0).tolist(), 'x_max': m.x.max(axis=0).tolist()}
    assert fn(m, dominio) == 0.0
    g = red_radial(random.Random(10), 12, 10)
    g['nodos'] = {n: orc.escalar_nodo(d, 30.0) for n, d in g['nodos'].items()}
    lejos = fn(orc.muestra(g), dominio)
    assert 0.0 < lejos <= 1.0


def test_la_ablacion_dice_cuanto_queda_fuera_de_dominio(bufer, monkeypatch):  # noqa: F811
    """045:RF-9, 045:RF-17 — la ablación mide el brazo como se usaría y dice cuántos ejemplos de prueba quedaron fuera de
    su dominio: en la T6 la red de prueba (30 nodos) estaba fuera de los cinco candidatos (169–5 147 aprendidos)."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: 'sin PyG')
    r = bf.comparar_fisicas(_experimento(), orc.particiones_del_bufer(bufer), bufer=bufer, ajustar=_ajustador([]))
    for nombre in ('fisica_pura', 'hibrido_vigente', 'red_sin_fisica'):
        assert 'ejemplos_fuera_de_dominio' in r['brazos'][nombre], nombre


def test_sin_epoca_admisible_ni_estado_nulo_no_se_queda_con_la_ultima():
    """045:RF-15 — sin la física como época de partida (otra arquitectura) y sin época dentro del tope, el miembro se
    queda con la de menor error, no con la última: PowerFlowNet daba «la mejor fue la −1 (inf p.u.)» en la T6."""
    fn = getattr(orc, 'elegir_respaldo', None)
    assert fn is not None, 'sin época admisible el miembro se queda con la última que entrenó'
    # La física (corrección nula) va antes que una época de menor error pero fuera del tope.
    assert fn(None, (3.0e-3, 'fisica'), (2.8e-3, 'e20')) == (3.0e-3, 'fisica')
    assert fn((2.7e-3, 'admisible'), (3.0e-3, 'fisica'), (2.8e-3, 'e20')) == (2.7e-3, 'admisible')
    assert fn(None, None, (2.9e-3, 'e1')) == (2.9e-3, 'e1')
    assert fn(None, None, None) is None


def _con_parametro(fn, nombre: str) -> bool:
    import inspect

    return nombre in inspect.signature(fn).parameters


def test_el_contrato_declara_las_redes_de_prueba_sin_tocar_el_perfil(bufer):  # noqa: F811
    """045:RF-18 — las redes de prueba de una ablación se declaran en su contrato (``politica.redes_de_prueba``, por el
    prefijo de su huella) y entran en la huella del experimento; el perfil de la empresa no se toca."""
    assert _con_parametro(orc.particionar, 'redes_de_prueba'), 'la prueba solo se declara en el perfil de la empresa'
    fn = getattr(bf, 'particiones_del_contrato', None)
    assert fn is not None, 'el contrato de la ablación no puede declarar sus redes de prueba'
    muestras, ids = orc._muestras(bufer, orc.Consulta())
    redes = sorted({orc.red_de(m) for m in muestras})
    elegida = redes[-1]
    base = _experimento()
    contrato = bf.ExperimentoSpec(base.contexto, base.algoritmo, base.semillas,
                                  {**base.politica, 'redes_de_prueba': [elegida[:16]]}, base.revision)
    assert contrato.huella != base.huella
    particiones = fn(contrato, bufer)
    de_la_elegida = {i for m, i in zip(muestras, ids, strict=True) if orc.red_de(m) == elegida}
    assert set(particiones.prueba) == de_la_elegida
    for parte in (particiones.entrenamiento, particiones.seleccion, particiones.calibracion):
        assert not set(parte) & de_la_elegida
    assert set(fn(base, bufer).prueba) == set(orc.particiones_del_bufer(bufer).prueba)


def test_una_declaracion_que_no_se_puede_cumplir_se_rechaza(bufer):  # noqa: F811
    """045:RF-18 — un prefijo que no es de ninguna red, que es de varias o que deja todas a prueba no cae en silencio
    al reparto por huella: se rechaza con su motivo."""
    assert _con_parametro(orc.particionar, 'redes_de_prueba'), 'la prueba solo se declara en el perfil de la empresa'
    muestras, _ids = orc._muestras(bufer, orc.Consulta())
    redes = sorted({orc.red_de(m) for m in muestras})
    with pytest.raises(ValueError, match='ninguna red'):
        orc.particionar(muestras, redes_de_prueba=['f' * 64 + 'x'])
    with pytest.raises(ValueError, match='todas las redes'):
        orc.particionar(muestras, redes_de_prueba=redes)
    with pytest.raises(ValueError, match='varias redes'):
        orc.particionar(muestras, redes_de_prueba=[''])

