"""Spec 042 en la web: escalera carga a carga y SET nueva para las que no caben.

La escalera de la 025 se sustituye por un doble que dice si caben las cargas activas por su
suma de kW; las cargas, por las aplicadas de un espacio sorteado (``IGEA_SCALE_SEED``).
"""
from __future__ import annotations

import os
import random

import pytest

from igea_dgs.web import services

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


class _Ctx:
    def __init__(self):
        self.lineas = []

    def log(self, texto):
        self.lineas.append(texto)

    def check_cancel(self):
        pass


def _cargas(rng, n):
    return [{'sed': f'C{i}', 'alimentador': rng.choice(['NA203', 'NA205']), 'kw': rng.uniform(100, 2500),
             'kvar': 0.0, 'barra': f'B{i}', 'variacion': f'Carga_C{i}_X'} for i in range(n)]


def test_escalera_carga_a_carga_aplica_las_que_caben(monkeypatch):
    """042:RF-1, 042:RF-2, 042:RF-3, 042:RF-4 — de mayor a menor kW, caben las k mayores cuya suma
    no pasa del límite; se mide sin aplicar y al final se aplica la escalera solo de esas k; las
    demás van a la SET nueva."""
    rng = random.Random(SEMILLA)
    cargas = _cargas(rng, rng.randint(1, 40))
    limite = rng.uniform(0, sum(c['kw'] for c in cargas))
    llamadas = []

    def escalera(ws, ctx, project, feeders, *, cargas_activas, aplicar, **_kw):
        llamadas.append((list(cargas_activas), aplicar))
        suma = sum(c['kw'] for c in cargas if c['variacion'] in cargas_activas)
        ok = suma <= limite
        return {'alimentadores': [{'alimentador': 'NA203', 'elegida': 'v' if ok else None}]}

    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: cargas)
    monkeypatch.setattr(services, 'obras_escalera', escalera)
    r = services.optimizar_con_proyecto(None, _Ctx(), 'P', ['NA203', 'NA205'])

    orden = sorted(cargas, key=lambda c: (-c['kw'], c['sed']))
    k, suma = 0, 0.0
    while k < len(orden) and suma + orden[k]['kw'] <= limite:
        suma += orden[k]['kw']
        k += 1
    assert r['caben'] == k, SEMILLA
    assert [c['sed'] for c in r['a_set_nueva']] == [c['sed'] for c in orden[k:]], SEMILLA
    aplicadas = [a for a, aplicar in llamadas if aplicar]
    assert aplicadas == ([[c['variacion'] for c in orden[:k]]] if k else []), SEMILLA
    assert len(llamadas) - len(aplicadas) <= len(cargas).bit_length() + 1, SEMILLA


def test_sin_cargas_aplicadas_se_dice(monkeypatch):
    """042:RF-1 — sin cargas nuevas aplicadas en los alimentadores marcados no hay nada que optimizar."""
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [])
    with pytest.raises(services.UserError, match='cargas nuevas'):
        services.optimizar_con_proyecto(None, _Ctx(), 'P', ['NA203'])


# =========================================================================== RF-5 a RF-13
def _red_sintetica():
    """F1: H - A - B - C, B - D; las cargas nuevas N1 y N2 cuelgan de C y D."""
    barras = [{'nombre': n, 'kv': 22.9, 'gps': [-14.95 - 0.002 * i, -74.98]} for i, n in enumerate('HABCD')]
    tramos = [{'nombre': f'L_{a}{b}', 'desde': a, 'hasta': b, 'largo_m': 200.0, 'cerrado': True}
              for a, b in ('HA', 'AB', 'BC', 'BD')]
    cargas = [{'nombre': 'S_A', 'barra': 'A', 'kw': 800.0, 'kvar': 200.0},
              {'nombre': 'S_C', 'barra': 'C', 'kw': 300.0, 'kvar': 100.0},
              {'nombre': 'N1', 'barra': 'C', 'kw': 2000.0, 'kvar': 400.0},
              {'nombre': 'N2', 'barra': 'D', 'kw': 1500.0, 'kvar': 300.0}]
    return {'alimentadores': {'F1': {'cabecera': 'H', 'kv': 22.9, 'barras': barras, 'tramos': tramos,
                                     'cargas': cargas}}}


def test_set_nueva_se_disena_situa_y_crea(monkeypatch, tmp_path):
    """042:RF-5, 042:RF-6, 042:RF-7, 042:RF-9, 042:RF-11, 042:RF-12 — la rama de B pasa a la SET
    nueva; la potencia de diseño es (S_C + N1 + N2) × (1 + g)^30 × 1,25 y la cubre el módulo de
    SET de 25 MVA del libro; la obra lleva la rama, la potencia y la tensión de alta del módulo,
    y el informe da el punto en UTM y GPS."""
    from igea_dgs import perfil_empresa
    from test_set_nueva import CFG_PIT, _libro

    perfil = {'crs_origen': 'EPSG:32718', 'escalera': {'sorteos': 20, 'semilla': 1},
              'planificacion': {'vida_util_anios': 30, 'factor_seguridad_set': 1.25, 'modulos_pit': CFG_PIT}}
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: perfil)
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, _red_sintetica(), None))
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [{'sed': 'N1'}, {'sed': 'N2'}])
    monkeypatch.setattr(services, '_crecimiento_de_la_cabecera',
                        lambda ws, ctx, project, feeders, avisos: {'F1': {'tasa': 0.02}})
    monkeypatch.setattr(services, 'native_action_context', lambda *a, **k: {})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'C')
    creadas = []
    monkeypatch.setattr(services, 'obra_anadir', lambda ws, obra: creadas.append(obra) or {'id': 'x'})
    monkeypatch.setattr(services, 'obras_ejecutar', lambda *a, **k: {'informe': {'obras': [
        {'set_nueva': {'lat': -14.951, 'lon': -74.98, 'cumple': True, 'intentos': [{}]}}]}})
    a_set = [{'sed': 'N1', 'alimentador': 'F1', 'kw': 2000.0, 'kvar': 400.0},
             {'sed': 'N2', 'alimentador': 'F1', 'kw': 1500.0, 'kvar': 300.0}]
    r = services.set_nueva_proponer(None, _Ctx(), 'P', ['F1'], a_set, capex=str(_libro(tmp_path)),
                                    alimentadores_nuevos=1)

    (rama,) = r['ramas']
    assert (rama['nodo'], rama['entrada']) == ('B', 'L_AB') and rama['destino'] == ['C', 'D']
    d = r['diseno']
    base = (300.0 ** 2 + 100.0 ** 2) ** 0.5 + (3500.0 ** 2 + 700.0 ** 2) ** 0.5
    assert d['kva_base'] == pytest.approx(base)
    assert d['kva_diseno'] == pytest.approx(base * 1.02 ** 30 * 1.25)
    assert r['modulo']['tipo'] == 'set' and r['modulo']['mva'] == 25.0
    (obra,) = creadas
    assert obra['clase'] == 'set_nueva' and obra['ramas'] == ['F1/B'] and obra['mva'] == 25.0
    assert obra['kv_alta'] == 60.0 and obra['casos'] == ['Con proyecto']
    assert r['ubicacion_final']['cumple']
    if r['ubicacion']['utm'] is not None:
        assert r['ubicacion']['utm']['crs'] == 'EPSG:32718' and r['ubicacion']['utm']['norte'] > 8_000_000


def test_sin_libro_capex_no_se_elige_modulo(monkeypatch):
    """042:RF-8 — sin el libro CAPEX no hay módulos PIT entre los que elegir: se dice."""
    with pytest.raises(services.UserError, match='CAPEX'):
        services.set_nueva_proponer(None, _Ctx(), 'P', ['F1'], [{'sed': 'N1'}], capex='',
                                    alimentadores_nuevos=2)


def test_la_web_ofrece_la_optimizacion_de_con_proyecto():
    """042:RF-13 — la ruta del paso de obras, como trabajo del carril de DIgSILENT."""
    from igea_dgs.web.app import create_app

    rutas = {getattr(r, 'path', '') for r in create_app().routes}
    assert '/api/workspaces/{wid}/pf/obras/con-proyecto' in rutas
