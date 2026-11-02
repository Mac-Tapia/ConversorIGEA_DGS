"""Spec 063: informe de factibilidad en un paso, para cualquier alimentador.

El caso real es la ampliación de INKA'S BERRIES S.A.C. en SM218 (2026-11-01): el estado actual
ya violaba límites (un cuello de botella al 131 %) y con la carga el punto de diseño bajaba a
0,934 p.u. Aquí las medidas se sortean (``CSG_SCALE_SEED``): ningún alimentador ni valor fijo.
"""
from __future__ import annotations

import os
import random

import pytest

from convertersmartgrid.estudios_pf import Limites
from convertersmartgrid.informes import (TRIFASICA, Caso, Extremo, Potencia,
                                         conclusion_factibilidad)

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
LIM = Limites(0.95, 1.05, 100.0)


def test_documentos_de_casos_no_mezclan_proyectos_ni_omiten_ramas(tmp_path):
    """063:RF-6, 063:RF-12: el generador rechaza otro proyecto o cobertura incompleta."""
    import json
    from apoyo import cargar_herramienta

    herramienta = cargar_herramienta('informe_casos_guardados.py', 'informe_casos_063')
    ruta = tmp_path / 'caso.json'
    datos = {'project': 'OTRO', 'caso': 'Sin proyecto', 'estudio': 'flujo',
             'red_proyecto': {'cobertura_completa': True, 'balance_completo': True}}
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(ValueError, match='proyecto'):
        herramienta.leer_caso(ruta, 'P', 'Sin proyecto')
    datos['project'] = 'P'
    datos['red_proyecto']['cobertura_completa'] = False
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(ValueError, match='cobertura'):
        herramienta.leer_caso(ruta, 'P', 'Sin proyecto')


def _caso(rng, nombre, *, cumple: bool, converge: bool = True) -> Caso:
    if not converge:
        return Caso(nombre, False)
    nodo, tramo = f'N{rng.randrange(10_000)}', f'L{rng.randrange(10_000)}'
    if cumple:
        u, carga = rng.uniform(0.951, 0.999), rng.uniform(5.0, 99.0)
    elif rng.random() < 0.5:
        u, carga = rng.uniform(0.80, 0.949), rng.uniform(5.0, 99.0)
    else:
        u, carga = rng.uniform(0.951, 0.999), rng.uniform(101.0, 250.0)
    return Caso(nombre, True, fuente=Potencia(rng.uniform(100, 20_000), rng.uniform(0, 5_000)),
                tension_min={TRIFASICA: Extremo(u, nodo)}, tension_max=Extremo(1.0, 'CAB'),
                cargabilidad_max=Extremo(carga, tramo), tramos_sobre=int(carga > 100.0),
                nodos_fuera=int(u < 0.95))


def test_conclusion_sin_problemas_no_propone_obras():
    """063:RF-8 — estado actual y con la carga dentro de límites: factible sin obras."""
    rng = random.Random(SEMILLA)
    for _ in range(50):
        c = conclusion_factibilidad(_caso(rng, 'actual', cumple=True), _caso(rng, 'carga', cumple=True),
                                    None, LIM)
        assert c.factible and c.clave == 'sin_obras' and not c.violaciones and not c.elementos, SEMILLA


def test_conclusion_con_problemas_y_sin_obras_pide_refuerzo():
    """063:RF-9, 063:RF-10 — una violación en el estado actual o con la carga y ninguna obra: no
    es factible sin refuerzo; se listan las violaciones y los elementos que lo requieren."""
    rng = random.Random(SEMILLA + 1)
    for _ in range(50):
        actual_cumple = rng.random() < 0.5
        actual = _caso(rng, 'actual', cumple=actual_cumple)
        carga = _caso(rng, 'carga', cumple=False)
        c = conclusion_factibilidad(actual, carga, None, LIM)
        assert not c.factible and c.clave == 'requiere_refuerzo', SEMILLA
        assert c.violaciones and c.elementos, SEMILLA
        peor = carga.minima.donde if carga.minima.valor < 0.95 else carga.cargabilidad_max.donde
        assert peor in c.elementos, SEMILLA


def test_conclusion_juzga_con_proyecto_con_obras():
    """063:RF-7, 063:RF-9 — con violaciones y obras, «Con proyecto» decide: factible si cumple;
    si no, las obras no bastan."""
    rng = random.Random(SEMILLA + 2)
    for _ in range(50):
        actual, carga = _caso(rng, 'actual', cumple=False), _caso(rng, 'carga', cumple=False)
        bien = conclusion_factibilidad(actual, carga, _caso(rng, 'con', cumple=True), LIM)
        assert bien.factible and bien.clave == 'con_obras' and bien.violaciones, SEMILLA
        mal = conclusion_factibilidad(actual, carga, _caso(rng, 'con', cumple=False), LIM)
        assert not mal.factible and mal.clave == 'obras_insuficientes' and mal.elementos, SEMILLA


@pytest.mark.parametrize('cual', ['actual', 'carga', 'con'])
def test_conclusion_sin_convergencia_no_es_factible(cual):
    """063:RF-11 — un caso que no converge impide concluir que es factible, y se dice cuál."""
    rng = random.Random(SEMILLA + 3)
    casos = {k: _caso(rng, k, cumple=k != 'actual', converge=k != cual) for k in ('actual', 'carga', 'con')}
    c = conclusion_factibilidad(casos['actual'], casos['carga'], casos['con'], LIM)
    assert not c.factible and c.clave == 'no_converge' and cual in ' '.join(c.violaciones)


def test_conclusion_usa_los_limites_que_recibe():
    """063:RF-13 — la misma medida cumple o no según la banda del perfil (rural ±7,5 %)."""
    rng = random.Random(SEMILLA + 4)
    actual = _caso(rng, 'actual', cumple=True)
    carga = Caso('carga', True, fuente=Potencia(1000, 200), tension_min={TRIFASICA: Extremo(0.934, 'P')},
                 tension_max=Extremo(1.0, 'CAB'), cargabilidad_max=Extremo(60.0, 'L1'), nodos_fuera=0)
    assert not conclusion_factibilidad(actual, carga, None, LIM).factible
    assert conclusion_factibilidad(actual, carga, None, Limites(0.925, 1.075, 100.0)).factible


def test_optimiza_solo_con_las_cargas_pedidas(monkeypatch, tmp_path):
    """063:RF-23, 063:RF-24 — SM218 (2026-11-01): con INKA y tres cargas del bloque aplicadas, la
    optimización de «Con proyecto» para INKA cuenta solo INKA; un nombre que no está se rechaza."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.services import UserError

    rng = random.Random(SEMILLA + 5)
    feeders = [f'AL{rng.randrange(100, 999)}' for _ in range(rng.randint(1, 3))]
    aplicadas = [{'sed': f'Cliente {i}', 'alimentador': rng.choice(feeders), 'kw': rng.uniform(50, 2000),
                  'kvar': 0.0, 'barra': f'N{i}', 'variacion': f'Carga_{i}', 'sola': i == 0}
                 for i in range(rng.randint(2, 8))]
    pedida = rng.choice(aplicadas)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    vistas = {}

    def oraculo(ws, ctx, project, feeders_, orden, opciones, memo):
        vistas['orden'] = [c['sed'] for c in orden]
        return {'caben': len(orden)}
    monkeypatch.setattr(services, '_optimizar_con_oraculo', oraculo)
    r = services.optimizar_con_proyecto(None, None, 'P', feeders, cargas=[pedida['sed']])
    assert vistas['orden'] == [pedida['sed']] and r['caben'] == 1, SEMILLA
    with pytest.raises(UserError, match='No existe'):
        services.optimizar_con_proyecto(None, None, 'P', feeders, cargas=['No existe'])


def test_banco_en_la_barra_existente_de_la_troncal():
    """063:RF-25 — INKA en SM218 (2026-11-01): su barra NODE_T_ la crea su variación; el banco va
    en la barra existente del tramo que partió, y la carga sigue con su tramo de la troncal. Una
    barra que existe sin la carga se queda; una sin barra existente cercana no da banco."""
    from convertersmartgrid.web.services import _carga_para_escalera

    rng = random.Random(SEMILLA + 6)
    for _ in range(30):
        i = rng.randrange(50)
        nodo, aguas_arriba = f'NODE_T_C{i}', f'B{i}'
        datos = {'indices': {nodo: i, aguas_arriba: i}, 'banco_en': {nodo: aguas_arriba}}
        c = _carga_para_escalera(nodo, {aguas_arriba}, datos)
        assert c == {'barra': aguas_arriba, 'existe': True, 'indice_troncal': i, 'barra_carga': nodo, 'camino': []}
        assert _carga_para_escalera(aguas_arriba, {aguas_arriba}, datos)['barra'] == aguas_arriba
        assert _carga_para_escalera(f'NODE_T_X{i}', set(), {'indices': {}})['existe'] is False


@pytest.mark.parametrize('encima', [True, False])
def test_umbral_de_carga_nueva_lleva_a_set_nueva(monkeypatch, encima):
    """063:RF-34 — NA203 + NA205 (2026-11-01): con cargas nuevas que suman más que el umbral del
    perfil (10 MW en Electro Dunas) la solución es una SET nueva directa; por debajo, la escalera."""
    from convertersmartgrid.web import services

    rng = random.Random(SEMILLA + 7 + int(encima))
    umbral = rng.uniform(5_000, 20_000)
    objetivo = umbral * (1.3 if encima else 0.7)
    n = rng.randint(2, 12)
    pesos = [rng.random() for _ in range(n)]
    aplicadas = [{'sed': f'C{i}', 'alimentador': 'AL1', 'kw': objetivo * w / sum(pesos), 'kvar': 0.0,
                  'barra': f'N{i}', 'variacion': f'Carga_{i}', 'sola': False} for i, w in enumerate(pesos)]
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: list(aplicadas))
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil',
                        lambda: {'planificacion': {'set_nueva_desde_kw': umbral}})
    vistos = {}
    monkeypatch.setattr(services, 'optimizar_con_proyecto',
                        lambda *a, **k: vistos.setdefault('escalera', {'caben': 0, 'a_set_nueva': []}))

    def set_nueva(ws, ctx, project, feeders, a_set_nueva, **k):
        vistos['a_set'] = len(a_set_nueva)
        return {'avisos': []}
    monkeypatch.setattr(services, 'set_nueva_proponer', set_nueva)

    class Ctx:
        def log(self, *_a, **_k):
            pass
    try:
        services.con_proyecto_optimizar(None, Ctx(), 'P', ['AL1'])
    except Exception:  # noqa: BLE001 - lo que sigue a la SET nueva no interesa aquí
        pass
    if encima:
        assert vistos.get('a_set') == n and 'escalera' not in vistos, SEMILLA
    else:
        assert 'escalera' in vistos, SEMILLA
