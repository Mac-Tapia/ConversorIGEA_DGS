"""Spec 045, T3: ablaciones sobre las mismas particiones y dominio antes de inferir, sin GPU.

Lo que aquí entrena es un doble: comprueba el contrato (mismos identificadores, mismo presupuesto), no mide
ninguna mejora. La ablación real, en CUDA y con artefactos reabiertos, está en ``tests_ml/test_benchmark_pinn_cuda.py``.
"""
from __future__ import annotations

import copy
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from apoyo import contrato_fisico
from test_digital_twin_episode import _payload

from convertersmartgrid.digital_twin import benchmark_fisico as bf
from convertersmartgrid.digital_twin import oraculo as orc
from convertersmartgrid.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.digital_twin.contratos_fisicos import VERSION_GRAFO
from convertersmartgrid.digital_twin.episode import leer_episodio
from convertersmartgrid.digital_twin.evolutivo import verificar_top_k
from convertersmartgrid.evaluacion_modelos import Particiones
from convertersmartgrid.experimentos import ContextoExperimento, ExperimentoSpec

H = 'a' * 64
RAIZ = Path(__file__).resolve().parents[1]


def _red(rnd: random.Random, n: int, red: int) -> dict:
    nodos = {f'R{red}N{i}': {'kv': 10.0, 'p_mw': 0.0 if i == 0 else rnd.uniform(0.05, 0.25),
                             'q_mvar': 0.0 if i == 0 else rnd.uniform(0.01, 0.08), 'fuente': i == 0,
                             'v_pu': 1.0 if i == 0 else None} for i in range(n)}
    ramas = [{'id': f'R{red}L{i}', 'desde': f'R{red}N{rnd.randrange(max(0, i - 3), i)}', 'hasta': f'R{red}N{i}', 'cerrada': True,
              'r_ohm': rnd.uniform(0.2, 0.8), 'x_ohm': rnd.uniform(0.2, 0.6), 'inom_ka': 0.2} for i in range(1, n)]
    return {'version': VERSION_GRAFO, **contrato_fisico(), 'nodos': nodos, 'ramas': ramas}


def _episodio(grafo: dict, familia: int):
    p = orc.ModeloMallado().predecir(grafo)
    payload = _payload(clase='counterfactual')
    payload['nativo']['feeders'] = [f'A{familia % 5}']
    payload['accion']['escenario'] = {'factor_carga': 1.0, 'tramos_abiertos': [f'T{familia}']}
    payload['topologia'] = {'grafo': grafo}
    payload['flujo']['tensiones'] = {'unidad': 'p.u.', 'valores': dict(zip(p['ids'], map(float, p['v']), strict=True))}
    return leer_episodio(payload)


@pytest.fixture(scope='module')
def bufer(tmp_path_factory):
    rnd = random.Random(31)
    b = BuferEpisodios(tmp_path_factory.mktemp('gemelo'))
    for r in range(rnd.randint(3, 4)):
        base = _red(rnd, rnd.randint(6, 12), r)
        for k in range(12):
            g = copy.deepcopy(base)
            f = rnd.uniform(0.7, 1.3)
            g['nodos'] = {n: orc.escalar_nodo(d, f) for n, d in g['nodos'].items()}
            b.guardar(_episodio(g, r * 100 + k))
    return b


def _experimento() -> ExperimentoSpec:
    contexto = ContextoExperimento('r', 'txt', H, 'P', ('A1',), 'IntCase:x', 'sin_proyecto', None, '2026-07', 'no_aplica',
                                   H, H, H, H)
    return ExperimentoSpec(contexto, 'pinn_gnn', (11, 23), {'modo': 'generalizacion'}, 'revision')


class _RedDoble:
    """Hace de red entrenada para probar el contrato: reproduce la física. No mide nada."""
    nombre = 'doble'

    def __init__(self, exponente):
        self.modelo = orc.ModeloMallado(exponente=exponente)

    def predecir(self, grafo):
        return self.modelo.predecir(grafo)


def _ajustador(llamadas: list):
    def ajustar(grupos, cfg, semillas, dominio, log):
        llamadas.append({'ids': {k: [orc.red_de(m) + m.familia for m in v] for k, v in grupos.items()}, 'cfg': cfg,
                         'semillas': tuple(semillas), 'dominio': dominio})
        return _RedDoble(cfg.exponente_carga), [[{'epoca': 0, 'datos': 0.0, 'fisica': 0.0, 'fronteras': 0.0}]]
    return ajustar


def test_ablaciones_comparten_ids(bufer, monkeypatch):
    """045:RF-8 — todos los brazos con red, con las mismas particiones, semillas y presupuesto; solo cambia lo ablacionado."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: None)
    particiones = orc.particiones_del_bufer(bufer)
    llamadas: list = []
    r = bf.comparar_fisicas(_experimento(), particiones, bufer=bufer, cfg=orc.Entrenamiento(epocas=7), ajustar=_ajustador(llamadas))
    assert len(llamadas) == 3
    primero = llamadas[0]
    for otra in llamadas[1:]:
        assert otra['ids'] == primero['ids'] and otra['semillas'] == primero['semillas'] == (11, 23)
        assert otra['dominio'] == primero['dominio']
        for campo in ('epocas', 'paciencia', 'cada', 'ocultas', 'pasos', 'lr', 'exponente_carga'):
            assert getattr(otra['cfg'], campo) == getattr(primero['cfg'], campo), campo
    assert [c['cfg'].peso_fisico for c in llamadas] == [0.0, orc.Entrenamiento().peso_fisico, orc.Entrenamiento().peso_fisico]
    assert [c['cfg'].arquitectura for c in llamadas] == ['csg', 'csg', 'powerflownet']
    assert r['particiones_ids']['prueba'] == list(particiones.prueba) and r['particiones_ids']['validacion'] == list(particiones.seleccion)
    assert r['presupuesto']['epocas'] == 7 and r['presupuesto']['semillas'] == [11, 23]
    assert set(r['brazos']) == {'fisica_pura', 'red_sin_fisica', 'hibrido_vigente', 'powerflownet'}
    for b in r['brazos'].values():
        assert b['estado'] == 'evaluado' and b['ids_evaluados'] == [list(particiones.prueba)]
        assert b['mae_v'] is not None and b['por_familia'] and 'veredicto' in b
        assert b['latencia_s_por_red'] >= 0 and 'vram_mb' in b
    assert r['completo'] is True and r['version_grafo'] == VERSION_GRAFO
    assert r['denominadores']['prueba']['ejemplos'] == len(particiones.prueba)


def test_las_puertas_de_044_no_se_bajan_en_las_ablaciones(bufer, monkeypatch):
    """045:RF-8 — cada brazo pasa las puertas de la 044: un doble que iguala a la física no se presenta como mejora."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: 'sin PyG')
    r = bf.comparar_fisicas(_experimento(), orc.particiones_del_bufer(bufer), bufer=bufer, ajustar=_ajustador([]))
    v = r['brazos']['hibrido_vigente']['veredicto']
    assert 'politica_hash' in v and v['alcance']['modo'] == 'generalizacion'
    assert [list(t) for t in r['politica']['topes']] == [['mae_v', orc.Puertas().mae_v_max], ['residuo', orc.Puertas().residuo_max]]


def test_pyg_ausente_no_rompe_base(bufer, monkeypatch):
    """045:RF-8 — sin PyG o su clon, el candidato queda no disponible con su motivo y la referencia sigue."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: 'PowerFlowNet no disponible: sin torch_geometric')
    llamadas: list = []
    r = bf.comparar_fisicas(_experimento(), orc.particiones_del_bufer(bufer), bufer=bufer, ajustar=_ajustador(llamadas))
    assert r['brazos']['powerflownet'] == {'estado': 'no_disponible', 'brazo': 'powerflownet',
                                           'motivo': 'PowerFlowNet no disponible: sin torch_geometric'}
    assert len(llamadas) == 2 and r['completo'] is True
    assert r['brazos']['hibrido_vigente']['estado'] == 'evaluado'


def test_el_nucleo_no_necesita_pyg_ni_torch():
    """045:RF-8 — importar el gemelo y sus ablaciones no carga PyTorch ni PyG."""
    programa = ('import sys\nimport convertersmartgrid.digital_twin.benchmark_fisico\n'
                "assert not ({'torch', 'torch_geometric'} & sys.modules.keys())\n")
    r = subprocess.run([sys.executable, '-c', programa], capture_output=True, text=True, timeout=120,
                       env={**__import__('os').environ, 'PYTHONPATH': str(RAIZ / 'src')})
    assert r.returncode == 0, r.stderr


def test_el_artefacto_del_brazo_se_reabre_sin_promover(bufer, monkeypatch):
    """045:RF-8 — un brazo real se reabre de disco y, si falla, el informe no queda completo ni se promueve."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: 'sin PyG')
    guardados = []

    class Oraculo(bf.OraculoPINN):
        def __init__(self):
            pass

        def predecir(self, grafo):
            return orc.ModeloMallado().predecir(grafo)

    def reabrir(modelo, _bufer, meta, sonda):
        guardados.append(meta)
        assert sonda.mascara.any()
        return {'ok': meta['ablacion'] != 'hibrido_vigente', 'proceso_nuevo': True, 'version': 'v'}

    monkeypatch.setattr(bf, 'guardar_y_reabrir', reabrir)
    r = bf.comparar_fisicas(_experimento(), orc.particiones_del_bufer(bufer), bufer=bufer,
                            ajustar=lambda *_a: (Oraculo(), [[]]))
    assert [m['ablacion'] for m in guardados] == ['red_sin_fisica', 'hibrido_vigente']
    assert r['brazos']['red_sin_fisica']['reapertura']['ok'] is True
    assert r['completo'] is False, 'con un artefacto que no se reabre, el informe no se da por bueno'
    assert not (bufer.raiz / 'modelos' / 'promovido.json').exists()


def test_guardar_y_reabrir_deja_la_sonda_sin_tocar_el_puntero(bufer, tmp_path):
    """045:RF-8 — el artefacto lleva lo que se comprueba al reabrir; el modelo en uso no cambia."""
    pytest.importorskip('torch')
    import json as _json

    from convertersmartgrid.digital_twin.buffer import BuferEpisodios as Bufer

    destino = Bufer(tmp_path / 'b')
    muestras, _ids = orc._muestras(bufer, orc.Consulta())

    class Candidato(orc.OraculoPINN):
        def predecir(self, grafo):
            return orc.ModeloMallado().predecir(grafo)

    candidato = Candidato([], orc.Entrenamiento(), {})
    vistos = []
    r = orc.guardar_y_reabrir(candidato, destino, {'ablacion': 'x'}, muestras[0],
                              reabrir=lambda c: vistos.append(c) or {'ok': True})
    assert r['ok'] is True and r['version'] == vistos[0].name
    prueba = _json.loads((vistos[0] / 'readback.json').read_text(encoding='utf-8'))
    assert prueba['grafo']['version'] == VERSION_GRAFO and len(prueba['v']) == len(muestras[0].ids)
    assert not (destino.raiz / 'modelos' / 'promovido.json').exists()


def test_sin_gpu_el_brazo_no_cae_a_la_cpu(bufer, monkeypatch):
    """045:RF-8 — sin CUDA, los brazos con red no se miden y el informe queda incompleto: nunca un OK falso."""
    monkeypatch.setattr(bf, '_powerflownet_disponible', lambda: None)

    def sin_gpu(*_a):
        raise orc.SinGPU('No hay GPU CUDA')

    r = bf.comparar_fisicas(_experimento(), orc.particiones_del_bufer(bufer), bufer=bufer, ajustar=sin_gpu)
    assert r['completo'] is False
    assert r['brazos']['fisica_pura']['estado'] == 'evaluado'
    assert r['brazos']['hibrido_vigente'] == {'estado': 'no_disponible', 'brazo': 'hibrido_vigente', 'motivo': 'No hay GPU CUDA'}


def test_un_episodio_que_no_ensena_bloquea_la_comparacion(bufer):
    """045:RF-8 — si falta un ejemplo declarado no se compara con menos: no serían las mismas particiones."""
    particiones = orc.particiones_del_bufer(bufer)
    viejo = _payload(clase='counterfactual')
    viejo['topologia'] = {'grafo': {'version': 2, 'nodos': {'S': {'kv': 10.0, 'fuente': True}}, 'ramas': []}}
    viejo['flujo']['tensiones'] = {'unidad': 'p.u.', 'valores': {'S': 1.0}}
    e = leer_episodio(viejo)
    bufer.guardar(e)
    mezcla = Particiones(particiones.entrenamiento, particiones.seleccion, particiones.calibracion,
                         (*particiones.prueba, e.episode_id), particiones.politica_hash)
    r = bf.comparar_fisicas(_experimento(), mezcla, bufer=bufer, ajustar=_ajustador([]))
    assert r['status'] == 'BLOQUEADO_POR_DATOS' and r['completo'] is False and r['episodios_fuera'] == [e.episode_id]


def test_grafos_viejos_no_entran_en_las_particiones(tmp_path):
    """045:RF-8 — un búfer solo con grafos anteriores no da particiones: se dice, no se compara con ellos."""
    b = BuferEpisodios(tmp_path)
    viejo = _payload(clase='counterfactual')
    viejo['topologia'] = {'grafo': {'version': 2, 'nodos': {'S': {'kv': 10.0, 'fuente': True}}, 'ramas': []}}
    viejo['flujo']['tensiones'] = {'unidad': 'p.u.', 'valores': {'S': 1.0}}
    b.guardar(leer_episodio(viejo))
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        orc.particiones_del_bufer(b)
    r = orc.entrenar(b)
    assert r['entrenado'] is False and 'versión 2' in r['motivo'] and r['excluidos']


def _manifiesto(grafo: dict) -> dict:
    m = orc.muestra(grafo)
    return {'dominio': {'x_min': (m.x.min(axis=0) - 0.5).tolist(), 'x_max': (m.x.max(axis=0) + 0.5).tolist(),
                        'nodos': [len(m.ids), len(m.ids)], 'redes': [orc.red_de(m)], 'version_grafo': VERSION_GRAFO}}


def test_fuera_dominio_no_se_acepta():
    """045:RF-9 — un cambio no soportado saca la red del dominio, y lo fuera de dominio no se da por diseño."""
    g = _red(random.Random(3), 8, 0)
    man = _manifiesto(g)
    assert bf.comprobar_dominio(g, man) == {'dentro': True, 'bloqueos': [], 'confirmar_en_pf': True}
    regulador = copy.deepcopy(g)
    regulador['alcance_fisico']['no_representados']['ElmVoltreg'] = ['R1']
    d = bf.comprobar_dominio(regulador, man)
    assert d['dentro'] is False and any('ElmVoltreg' in b for b in d['bloqueos']) and d['confirmar_en_pf'] is True
    medidos = []

    def medir(alternativa):
        medidos.append(alternativa)
        return {'converge': True}

    r = verificar_top_k([{'codigo': 'A', 'fuera_de_dominio': True}], medir, tolerancia_v_pu=0.01)
    assert r['elegida'] is None and r['verificada'] is False and not medidos
    assert 'dominio' in r['descartadas'][0]['motivo']


def test_red_nueva_con_intervalo_estrecho_no_entra():
    """045:RF-9 — una red de tamaño y rangos parecidos pero distinta sigue fuera: lo validado es esa red."""
    rnd = random.Random(4)
    g = _red(rnd, 8, 0)
    man = _manifiesto(g)
    otra = copy.deepcopy(g)
    otra['nodos'] = {n.replace('R0', 'R9'): d for n, d in otra['nodos'].items()}
    otra['ramas'] = [{**r, 'desde': r['desde'].replace('R0', 'R9'), 'hasta': r['hasta'].replace('R0', 'R9')} for r in otra['ramas']]
    d = bf.comprobar_dominio(otra, man)
    assert not d['dentro'] and any('red distinta' in b for b in d['bloqueos'])
    alta = copy.deepcopy(g)
    for n in alta['nodos'].values():
        n['p_mw'] = (n['p_mw'] or 0) * 500
    assert any('fuera de lo aprendido' in b for b in bf.comprobar_dominio(alta, man)['bloqueos'])


def test_un_modelo_sin_dominio_o_de_otro_grafo_no_opina():
    """045:RF-9, 045:RF-2 — un modelo anterior al contrato no dice en qué física aprendió: fuera, con el motivo."""
    g = _red(random.Random(6), 8, 0)
    assert not bf.comprobar_dominio(g, {})['dentro']
    man = _manifiesto(g)
    man['dominio'].pop('version_grafo')
    d = bf.comprobar_dominio(g, man)
    assert not d['dentro'] and any('versión None' in b for b in d['bloqueos'])
    assert np.array(man['dominio']['x_min']).size == 5


def test_ordenar_candidatos_dice_fuera_de_dominio():
    """045:RF-9 — un candidato sobre una red no soportada queda detrás y marcado, y no se da sin confirmar."""
    g = _red(random.Random(8), 8, 0)
    malo = copy.deepcopy(g)
    malo['alcance_fisico']['no_representados']['ElmTr3'] = ['T3']
    candidatos = [{'codigo': 'B', 'nodo': 'R0N3', 'q_mvar': 0.1}]
    assert orc.ordenar_candidatos(orc.ModeloMallado(), g, candidatos, 0.9)[0]['fuera_de_dominio'] is False
    fila = orc.ordenar_candidatos(orc.ModeloMallado(), malo, candidatos, 0.9)[0]
    assert fila['fuera_de_dominio'] is True and fila['confirmar_en_pf'] is True


def test_alcance_de_las_ablaciones():
    """045:RF-8 — la misma red en ajuste y en prueba no se presenta como generalización a otra red."""
    rnd = random.Random(9)
    uno, otro = (orc.muestra(_red(rnd, 6, r)) for r in (0, 1))
    assert bf.alcance_general({'entrenamiento': [uno], 'validacion': [], 'calibracion': [], 'prueba': [otro]})
    assert not bf.alcance_general({'entrenamiento': [uno], 'validacion': [], 'calibracion': [], 'prueba': [uno]})
