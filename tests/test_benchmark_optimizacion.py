"""Spec 048, T2: benchmark de los optimizadores con el mismo presupuesto de evaluaciones.

El benchmark anterior (``tools/evaluar_evolutivos.py``) daba a cada algoritmo sus propias
generaciones: el que tenía más población gastaba más evaluaciones y «ganaba» por eso. Aquí el
presupuesto son evaluaciones reales del evaluador, las semillas son las mismas para todos y la
reparación de los genes es una sola. Los problemas son analíticos y su tamaño se sortea.
"""
from __future__ import annotations

import random
from dataclasses import replace

import numpy as np
import pytest

from convertersmartgrid.digital_twin import adaptador_pymoo
from convertersmartgrid.digital_twin import benchmark_optimizacion as bo
from convertersmartgrid.digital_twin import problema_optimizacion as po

SEMILLAS = tuple(range(20))
CONTEXTO = po.ContextoSintetico('benchmark_analitico_no_red_electrica', 'pruebas de la spec 048')


def esfera_entera(n: int, llamadas: list | None = None, coste: bool = True) -> po.ProblemaOptimizacion:
    """Distancia al cuadrado a un objetivo entero dentro de [0, 20]^n: el óptimo es 0."""
    objetivo = [(3 * i + 5) % 21 for i in range(n)]

    def evaluador(v):
        if llamadas is not None:
            llamadas.append(dict(v))
        d = sum((v[f'x{i}'] - objetivo[i]) ** 2 for i in range(n))
        return {'convergio': True, 'objetivos': {'distancia': float(d)}, 'violaciones': {},
                'demanda_referencia_kw': 1.0, 'demanda_atendida_kw': 1.0}

    variables = tuple(po.Variable(f'x{i}', 'entera', 'módulos', inferior=0, superior=20, origen='prueba',
                                  coste=1.0 if coste else None, origen_coste='prueba' if coste else None)
                      for i in range(n))
    return po.ProblemaOptimizacion(
        nombre=f'esfera_entera_{n}', variables=variables, restricciones=(),
        objetivos=(po.Objetivo('distancia', 'módulos²'),), contexto=CONTEXTO, modelo_id='analitico@1',
        evaluador=evaluador, normalizacion={'distancia': (0.0, 400.0 * n)})


def schaffer_restringido() -> po.ProblemaOptimizacion:
    """Schaffer N.1 con x ≥ 0,5 como restricción: el frente es x ∈ [0,5, 2]."""
    def evaluador(v):
        x = v['x']
        return {'convergio': True, 'objetivos': {'f1': x * x, 'f2': (x - 2) ** 2},
                'violaciones': {'x_min': max(0.5 - x, 0.0)}, 'demanda_referencia_kw': 1.0,
                'demanda_atendida_kw': 1.0}

    return po.ProblemaOptimizacion(
        nombre='schaffer', variables=(po.Variable('x', 'continua', 'p.u.', inferior=-5, superior=5, origen='prueba'),),
        restricciones=(po.Restriccion('x_min', 'p.u.', 'x no baja de 0,5'),),
        objetivos=(po.Objetivo('f1', 'p.u.²'), po.Objetivo('f2', 'p.u.²')), contexto=CONTEXTO,
        modelo_id='analitico@1', evaluador=evaluador, normalizacion={'f1': (0.0, 4.0), 'f2': (0.0, 4.0)})


def ejecuciones(resultado, problema=None):
    for p in resultado['problemas']:
        if problema is None or p['nombre'] == problema:
            for nombre, a in p['algoritmos'].items():
                for e in a['ejecuciones']:
                    yield p['nombre'], nombre, e


# ------------------------------------------------------------------ RF-3
def test_presupuesto_es_evaluaciones():
    """048:RF-3 — con poblaciones muy distintas, todos gastan el mismo máximo de evaluaciones reales."""
    rng = random.Random(4802)
    n = rng.randint(4, 7)
    presupuesto = rng.randint(40, 70)
    llamadas: list = []
    problema = esfera_entera(n, llamadas)
    poblaciones = {'genetico': 8, 'nsga2': 30, 'evolucion_diferencial': 50,
                   'pymoo_ga': 12, 'pymoo_nsga2': 24, 'pymoo_de': 40}
    r = bo.comparar_optimizadores([problema], semillas=SEMILLAS, presupuesto=presupuesto,
                                  cancelado=lambda: False, poblaciones=poblaciones)
    assert r['estado'] == 'completo'
    vistos = set()
    for _p, nombre, e in ejecuciones(r):
        vistos.add(nombre)
        assert e['evaluaciones_reales'] == presupuesto, (nombre, e)
        assert e['estado'] == 'presupuesto_agotado'
    esperados = {'genetico', 'nsga2', 'evolucion_diferencial'}
    if adaptador_pymoo.disponible():
        esperados |= set(adaptador_pymoo.ALGORITMOS)
    assert vistos == esperados
    # Lo que se cuenta es lo que llega al evaluador: ni una llamada de más.
    assert len(llamadas) == sum(e['evaluaciones_reales'] for *_x, e in ejecuciones(r))
    assert r['metodo']['presupuesto'] == presupuesto and 'reales' in r['metodo']['unidad_presupuesto']
    assert r['metodo']['criterio_reparacion'] == po.CRITERIO_REPARACION


def test_semillas_comunes():
    """048:RF-3 — mismas semillas y mismos problemas para todos; menos de veinte no compara."""
    problemas = [esfera_entera(3), schaffer_restringido()]
    r = bo.comparar_optimizadores(problemas, semillas=SEMILLAS, presupuesto=30, cancelado=lambda: False)
    assert [p['nombre'] for p in r['problemas']] == ['esfera_entera_3', 'schaffer']
    assert [p['huella'] for p in r['problemas']] == [po.huella_problema(p) for p in problemas]
    for p in r['problemas']:
        for nombre, a in p['algoritmos'].items():
            if a['estado'] == 'no_compatible':
                continue
            assert [e['semilla'] for e in a['ejecuciones']] == list(SEMILLAS), nombre
            assert not [e['error'] for e in a['ejecuciones'] if e['estado'] == 'error'], nombre
    # Determinista con sus semillas (salvo el tiempo de reloj).
    otra = bo.comparar_optimizadores(problemas, semillas=SEMILLAS, presupuesto=30, cancelado=lambda: False)
    quitar = lambda r: [(p, n, {k: v for k, v in e.items() if k != 'tiempo_s'}) for p, n, e in ejecuciones(r)]
    assert quitar(r) == quitar(otra)
    with pytest.raises(ValueError, match='veinte'):
        bo.comparar_optimizadores(problemas, semillas=tuple(range(19)), presupuesto=30, cancelado=lambda: False)
    with pytest.raises(ValueError, match='repetid'):
        bo.comparar_optimizadores(problemas, semillas=(0,) * 20, presupuesto=30, cancelado=lambda: False)
    with pytest.raises(ValueError, match='presupuesto'):
        bo.comparar_optimizadores(problemas, semillas=SEMILLAS, presupuesto=0, cancelado=lambda: False)
    sin_normalizar = replace(esfera_entera(2), normalizacion=None)
    with pytest.raises(ValueError, match='normalizacion'):
        bo.comparar_optimizadores([sin_normalizar], semillas=SEMILLAS, presupuesto=30, cancelado=lambda: False)


# ------------------------------------------------------------------ RF-6
def test_frente_informa_factibilidad_objetivos_tiempo_y_evaluaciones():
    """048:RF-6 — cada frente dice factibles, objetivos, hipervolumen, tiempo y evaluaciones, con el mismo método."""
    r = bo.comparar_optimizadores([schaffer_restringido()], semillas=SEMILLAS, presupuesto=60,
                                  cancelado=lambda: False)
    p = r['problemas'][0]
    # Un algoritmo de un solo objetivo no se compara en un problema de dos: se dice, no se escalariza.
    assert p['algoritmos']['genetico']['estado'] == 'no_compatible'
    assert p['algoritmos']['evolucion_diferencial']['estado'] == 'no_compatible'
    a = p['algoritmos']['nsga2']
    for e in a['ejecuciones']:
        assert {'factibles', 'frente', 'hipervolumen', 'tiempo_s', 'evaluaciones_reales',
                'consultas_cacheadas', 'estado'} <= set(e)
        assert e['factibles'] > 0 and e['frente']
        assert all(x['vector']['x'] >= 0.5 for x in e['frente'])     # solo factibles en el frente
        assert set(e['frente'][0]['objetivos']) == {'f1', 'f2'}
        assert 0 < e['hipervolumen'] <= 1.1 ** 2
    resumen = a['resumen']
    assert resumen['semillas'] == len(SEMILLAS)
    assert resumen['hipervolumen']['ic95'][0] <= resumen['hipervolumen']['media'] <= resumen['hipervolumen']['ic95'][1]
    assert resumen['tasa_con_factible'] == 1.0
    assert r['metodo']['referencia_hipervolumen'] == [1.1, 1.1] or r['metodo']['referencia_hipervolumen'] == 1.1
    assert r['metodo']['normalizacion']['schaffer'] == {'f1': [0.0, 4.0], 'f2': [0.0, 4.0]}


def test_hipervolumen_de_un_frente_conocido():
    """048:RF-6 — el hipervolumen normalizado se calcula con el punto de referencia declarado."""
    assert bo.hipervolumen(np.array([[0.2, 0.6], [0.6, 0.2]]), 1.1) == pytest.approx(0.65)
    assert bo.hipervolumen(np.array([[0.2, 0.6], [0.6, 0.2], [0.7, 0.7]]), 1.1) == pytest.approx(0.65)
    assert bo.hipervolumen(np.array([[0.25]]), 1.1) == pytest.approx(0.85)
    assert bo.hipervolumen(np.zeros((0, 2)), 1.1) == 0.0
    assert bo.hipervolumen(np.array([[1.2, 0.0]]), 1.1) == 0.0


def test_sin_coste_no_entra_en_el_frente():
    """048:RF-6 — una solución sin objetivo calculable no es factible para comparar ni candidata."""
    r = bo.comparar_optimizadores([esfera_entera(2, coste=False)], semillas=SEMILLAS, presupuesto=20,
                                  cancelado=lambda: False, algoritmos=('genetico',))
    e = next(e for *_x, e in ejecuciones(r))
    assert e['factibles'] > 0      # la distancia sí se calcula: aquí el coste no es objetivo
    con_inversion = replace(
        esfera_entera(2, coste=False),
        objetivos=(po.Objetivo('inversion', 'coste', origen='coste'), po.Objetivo('distancia', 'módulos²')),
        normalizacion={'inversion': (0.0, 40.0), 'distancia': (0.0, 800.0)})
    r = bo.comparar_optimizadores([con_inversion], semillas=SEMILLAS, presupuesto=20, cancelado=lambda: False,
                                  algoritmos=('nsga2',))
    for *_x, e in ejecuciones(r):
        assert all(x['objetivos']['inversion'] is not None for x in e['frente'])
        assert e['no_comparables'] > 0
    assert all(c['objetivos']['inversion'] is not None for c in r['problemas'][0]['candidatos'])


def test_sin_pymoo_no_bloquea_los_vigentes(monkeypatch):
    """048:RF-3 — sin el adaptador opcional se comparan los vigentes y se dice por qué falta pymoo."""
    monkeypatch.setattr(adaptador_pymoo, 'disponible', lambda: False)
    r = bo.comparar_optimizadores([esfera_entera(2)], semillas=SEMILLAS, presupuesto=15, cancelado=lambda: False)
    assert set(r['problemas'][0]['algoritmos']) == {'genetico', 'nsga2', 'evolucion_diferencial'}
    assert any('pymoo' in a for a in r['avisos'])


# ------------------------------------------------------------------ RF-8
def test_cancelacion_no_publica_optimo():
    """048:RF-8 — al cancelar se conserva lo evaluado y no se publica ningún óptimo ni candidato."""
    llamadas: list = []
    corte = random.Random(4803).randint(30, 90)
    r = bo.comparar_optimizadores([esfera_entera(3, llamadas)], semillas=SEMILLAS, presupuesto=25,
                                  cancelado=lambda: len(llamadas) >= corte)
    assert r['estado'] == 'cancelado'
    assert r['optimo_aceptado'] is None and r['publicable'] is False
    assert r['problemas'][0]['candidatos'] == []
    hechas = list(ejecuciones(r))
    assert sum(e['evaluaciones_reales'] for *_x, e in hechas) == len(llamadas) == corte
    assert hechas[-1][2]['estado'] == 'cancelado'
    assert hechas[-1][2]['mejor'] is not None or hechas[-1][2]['evaluaciones_reales'] == 0


def test_completo_propone_candidatos_sin_aceptarlos():
    """048:RF-8 — aun completo, el benchmark propone candidatos para verificar; no acepta ninguno."""
    r = bo.comparar_optimizadores([esfera_entera(2)], semillas=SEMILLAS, presupuesto=40, cancelado=lambda: False)
    assert r['estado'] == 'completo' and r['publicable'] is True and r['optimo_aceptado'] is None
    candidatos = r['problemas'][0]['candidatos']
    assert candidatos and all(c['requiere_verificacion_nativa'] for c in candidatos)
    assert candidatos[0]['objetivos']['distancia'] == min(c['objetivos']['distancia'] for c in candidatos)
    assert len({tuple(sorted(c['vector'].items())) for c in candidatos}) == len(candidatos)


def test_etapa_evolutivos_usa_el_mismo_presupuesto(tmp_path):
    """048:RF-3, 048:RF-6 — la etapa «evolutivos» del reentreno compara con el benchmark de la 048."""
    import importlib.util
    import json
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / 'tools' / 'evaluar_evolutivos.py'
    spec = importlib.util.spec_from_file_location('evaluar_evolutivos_048', ruta)
    assert spec and spec.loader
    herramienta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(herramienta)
    informe = tmp_path / 'evolutivos.json'
    assert herramienta.main(['--seeds', '30', '--presupuesto', '20', '--report', str(informe)]) == 0
    r = json.loads(informe.read_text(encoding='utf-8'))
    assert r['status'] == 'RECHAZADO' and r['promovido'] is False and r['training_completed'] is False
    assert r['evaluation_completed'] is True and r['dominio'] == 'benchmark_analitico_no_red_electrica'
    assert r['metodo']['presupuesto'] == 20 and len(r['metodo']['semillas']) == 30
    for p in r['comparacion']['problemas']:
        for a in p['algoritmos'].values():
            assert all(e['evaluaciones_reales'] <= 20 for e in a['ejecuciones'])
    assert herramienta.main(['--seeds', '29', '--report', str(tmp_path / 'otro.json')]) == 2
