"""Spec 045, T3: ablación real en CUDA, con el MPN de PowerFlowNet clonado y los artefactos reabiertos.

Ocupa la GPU: no se ejecuta con la suite de ``tests/``. Sin CUDA falla, no se omite: el cierre de la tarea
pide esta medición real. Las redes de aquí prueban que el camino funciona; la mejora se mide con los
episodios de la red real (``tools/digital_twin_entrenar.py --ablaciones``), no con estas.
"""
from __future__ import annotations

import copy
import random

from convertersmartgrid.digital_twin import benchmark_fisico as bf
from convertersmartgrid.digital_twin import oraculo as orc
from convertersmartgrid.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.digital_twin.contratos_fisicos import CONTROLES_LDF, REPRESENTACION, VERSION_GRAFO
from convertersmartgrid.digital_twin.episode import ESQUEMA, leer_episodio
from convertersmartgrid.experimentos import ContextoExperimento, ExperimentoSpec
from convertersmartgrid.trabajadores_ml import turno_gpu

H = 'a' * 64


def _red(rnd: random.Random, n: int, red: int) -> dict:
    nodos = {f'R{red}N{i}': {'kv': 10.0, 'p_mw': 0.0 if i == 0 else rnd.uniform(0.05, 0.25),
                             'q_mvar': 0.0 if i == 0 else rnd.uniform(0.01, 0.08), 'fuente': i == 0,
                             'v_pu': 1.0 if i == 0 else None} for i in range(n)}
    ramas = [{'id': f'R{red}L{i}', 'desde': f'R{red}N{rnd.randrange(max(0, i - 3), i)}', 'hasta': f'R{red}N{i}', 'cerrada': True,
              'r_ohm': rnd.uniform(0.2, 0.8), 'x_ohm': rnd.uniform(0.2, 0.6), 'inom_ka': 0.2} for i in range(1, n)]
    return {'version': VERSION_GRAFO, 'alcance_fisico': {'representacion': REPRESENTACION, 'no_representados': {}},
            'controles': {'comldf': dict.fromkeys(CONTROLES_LDF, 0)}, 'nodos': nodos, 'ramas': ramas}


def _episodio(grafo: dict, familia: int):
    p = orc.ModeloMallado().predecir(grafo)
    return leer_episodio({
        'schema': ESQUEMA, 'clase': 'counterfactual', 'caso': 'sin_proyecto', 'creado': '2026-11-03T10:00:00+00:00',
        'fuente': {'source_run_id': 'r', 'source_mode': 'txt', 'source_fingerprint': H},
        'nativo': {'project': 'P', 'feeders': [f'A{familia % 5}'], 'reopen_verified': True},
        'accion': {'tipo': 'gemelo_escenarios', 'escenario': {'factor_carga': 1.0, 'tramos_abiertos': [f'T{familia}']}},
        'topologia': {'grafo': grafo}, 'aceptacion': {}, 'obras': [], 'artefactos': [],
        'flujo': {'balance': {'ausente': 'x'}, 'perdidas': {'ausente': 'x'}, 'cargabilidad': {'ausente': 'x'},
                  'confiabilidad': {'ausente': 'x'},
                  'tensiones': {'unidad': 'p.u.', 'valores': dict(zip(p['ids'], map(float, p['v']), strict=True))}},
        'contexto_fisico': {'case_role': 'sin_proyecto', 'case_id': 'IntCase:x', 'topology_hash': H, 'controls_hash': H,
                            'scenario_hash': H}})


def test_ablacion_real_en_cuda(tmp_path):
    """045:RF-8 — los brazos entrenan en la GPU con las mismas particiones, con términos por época, latencia y VRAM."""
    rnd = random.Random(41)
    bufer = BuferEpisodios(tmp_path)
    for r in range(4):
        base = _red(rnd, 8 + 2 * r, r)
        for k in range(12):
            g = copy.deepcopy(base)
            f = rnd.uniform(0.7, 1.3)
            g['nodos'] = {n: orc.escalar_nodo(d, f) for n, d in g['nodos'].items()}
            bufer.guardar(_episodio(g, r * 100 + k))
    experimento = ExperimentoSpec(ContextoExperimento('r', 'txt', H, 'P', ('A1',), 'IntCase:x', 'sin_proyecto', None, '2026-07',
                                                      'no_aplica', H, H, H, H), 'pinn_gnn', (11, 23), {'modo': 'generalizacion'}, 'r')
    with turno_gpu('pinn-ablacion-prueba'):
        r = bf.comparar_fisicas(experimento, orc.particiones_del_bufer(bufer), bufer=bufer,
                                cfg=orc.Entrenamiento(epocas=10, ocultas=16, pasos=3, paciencia=5, cada=2))
    assert r['completo'] is True, r['brazos']
    for nombre in ('red_sin_fisica', 'hibrido_vigente'):
        b = r['brazos'][nombre]
        assert b['estado'] == 'evaluado' and b['vram_mb'] > 0
        assert b['reapertura']['ok'] is True and b['reapertura']['payload']['proceso_nuevo'] is True
        assert len(b['terminos_por_epoca']) == 2 and b['terminos_por_epoca'][0][0]['fisica'] >= 0
    assert r['brazos']['powerflownet']['estado'] in ('evaluado', 'no_disponible')
