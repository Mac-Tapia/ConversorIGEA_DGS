"""Spec 042 en la web: escalera carga a carga y SET nueva para las que no caben.

La escalera de la 025 se sustituye por un doble que dice si caben las cargas activas por su
suma de kW; las cargas, por las aplicadas de un espacio sorteado (``CSG_SCALE_SEED``).
"""
from __future__ import annotations

import os
import random

import pytest

from convertersmartgrid.web import services

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))


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

    pedidos, memos = [], []

    def escalera(ws, ctx, project, feeders, *, cargas_activas, aplicar, **_kw):
        llamadas.append((list(cargas_activas), aplicar))
        pedidos.append({'aplicar': aplicar, **_kw})
        memos.append(_kw.get('memo'))
        suma = sum(c['kw'] for c in cargas if c['variacion'] in cargas_activas)
        ok = suma <= limite
        return {'alimentadores': [{'alimentador': 'NA203', 'elegida': 'v' if ok else None}]}

    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: cargas)
    monkeypatch.setattr(services, 'obras_escalera', escalera)
    # La búsqueda en DIgSILENT es la de respaldo cuando el oráculo no puede (052:RF-8).
    monkeypatch.setattr(services, '_optimizar_con_oraculo',
                        lambda *a, **k: (_ for _ in ()).throw(services._SinOraculo('prueba de la 042')))
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
    # Galopando desde abajo y afinando por bisección (042:RF-2): unas 2·log2(k) pruebas.
    assert len(llamadas) - len(aplicadas) <= 2 * (k + 1).bit_length() + 1, SEMILLA
    assert all(kw.get('basta_una') and kw.get('memo') is memos[0] for kw in pedidos if not kw['aplicar']), SEMILLA


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
    nueva; la potencia de diseño es (S_C × (1 + g)^30 + N1 + N2) × 1,25 y la cubre el módulo de
    SET de 25 MVA del libro; la obra lleva la rama, la potencia y la tensión de alta del módulo,
    y el informe da el punto en UTM y GPS."""
    from convertersmartgrid import perfil_empresa
    from test_set_nueva import CFG_PIT, _libro

    perfil = {'crs_origen': 'EPSG:32718', 'escalera': {'sorteos': 20, 'semilla': 1},
              'planificacion': {'vida_util_anios': 30, 'factor_seguridad_set': 1.25, 'modulos_pit': CFG_PIT}}
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: perfil)
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, _red_sintetica(), None))
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [{'sed': 'N1'}, {'sed': 'N2'}])
    pedidas = []
    monkeypatch.setattr(services, '_crecimiento_de_la_cabecera',
                        lambda ws, ctx, project, feeders, avisos, **kw: pedidas.append(kw) or {'F1': {'tasa': 0.02}})
    monkeypatch.setattr(services, 'native_action_context', lambda *a, **k: {})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'C')
    creadas = []
    monkeypatch.setattr(services, 'obra_anadir', lambda ws, obra: creadas.append(obra) or {'id': 'x'})
    monkeypatch.setattr(services, 'obras_ejecutar', lambda *a, **k: {'informe': {'obras': [
        {'set_nueva': {'lat': -14.951, 'lon': -74.98, 'cumple': True, 'intentos': [{}],
                       'flujos_en_punto': {'lat': -14.951, 'lon': -74.98}}}]}})
    a_set = [{'sed': 'N1', 'alimentador': 'F1', 'kw': 2000.0, 'kvar': 400.0},
             {'sed': 'N2', 'alimentador': 'F1', 'kw': 1500.0, 'kvar': 300.0}]
    r = services.set_nueva_proponer(None, _Ctx(), 'P', ['F1'], a_set, capex=str(_libro(tmp_path)),
                                    alimentadores_nuevos=1)

    (rama,) = r['ramas']
    assert (rama['nodo'], rama['entrada']) == ('B', 'L_AB') and rama['destino'] == ['C', 'D']
    d = r['diseno']
    base = (300.0 ** 2 + 100.0 ** 2) ** 0.5 + (3500.0 ** 2 + 700.0 ** 2) ** 0.5
    assert d['kva_base'] == pytest.approx(base)
    assert d['kva_diseno'] == pytest.approx(((300.0 ** 2 + 100.0 ** 2) ** 0.5 * 1.02 ** 30
                                             + (3500.0 ** 2 + 700.0 ** 2) ** 0.5) * 1.25)
    assert r['modulo']['tipo'] == 'set' and r['modulo']['mva'] == 25.0
    (obra,) = creadas
    assert obra['clase'] == 'set_nueva' and obra['ramas'] == ['F1/B'] and obra['mva'] == 25.0
    assert obra['kv_alta'] == 60.0 and obra['casos'] == ['Con proyecto']
    assert r['ubicacion_final']['cumple']
    assert pedidas == [{'todos': True}]          # también un proyecto que no es de un sistema entero
    if r['ubicacion']['utm'] is not None:
        assert r['ubicacion']['utm']['crs'] == 'EPSG:32718' and r['ubicacion']['utm']['norte'] > 8_000_000


def test_set_nueva_toma_la_barra_de_una_carga_apartada(monkeypatch, tmp_path):
    """042:RF-6 — una carga apartada por la escalera no está activa en «Con proyecto» ni sale entre
    sus cargas: entra en la SET nueva por la barra que dio la escalera, llevada a media."""
    from convertersmartgrid import perfil_empresa
    from test_set_nueva import CFG_PIT, _libro

    perfil = {'crs_origen': 'EPSG:32718', 'escalera': {'sorteos': 20, 'semilla': 1},
              'planificacion': {'vida_util_anios': 30, 'factor_seguridad_set': 1.25, 'modulos_pit': CFG_PIT}}
    red = _red_sintetica()
    f1 = red['alimentadores']['F1']
    f1['cargas'] = [c for c in f1['cargas'] if c['nombre'] not in ('N1', 'N2')]   # apartadas
    f1['media'] = {'N1_BT': 'C', 'N2_BT': 'D'}
    planes = []
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: perfil)
    monkeypatch.setattr(services, '_guion_pf', lambda ws, ctx, guion, plan, **k: planes.append(plan) or (0, red, None))
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [{'sed': 'N1'}, {'sed': 'N2'}])
    monkeypatch.setattr(services, '_crecimiento_de_la_cabecera', lambda *a, **kw: {'F1': {'tasa': 0.02}})
    monkeypatch.setattr(services, 'native_action_context', lambda *a, **k: {})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'C')
    monkeypatch.setattr(services, 'obra_anadir', lambda ws, obra: {'id': 'x'})
    monkeypatch.setattr(services, 'obras_ejecutar', lambda *a, **k: {'informe': {'obras': [
        {'set_nueva': {'lat': -14.951, 'lon': -74.98, 'cumple': True, 'intentos': [{}],
                       'flujos_en_punto': {'lat': -14.951, 'lon': -74.98}}}]}})
    a_set = [{'sed': 'N1', 'alimentador': 'F1', 'kw': 2000.0, 'kvar': 400.0, 'barra': 'N1_BT'},
             {'sed': 'N2', 'alimentador': 'F1', 'kw': 1500.0, 'kvar': 300.0, 'barra': 'N2_BT'}]
    r = services.set_nueva_proponer(None, _Ctx(), 'P', ['F1'], a_set, capex=str(_libro(tmp_path)),
                                    alimentadores_nuevos=1)
    assert planes[0]['barras'] == {'F1': ['N1_BT', 'N2_BT']}
    (rama,) = r['ramas']
    assert rama['destino'] == ['C', 'D'] and not any('N1' in a or 'N2' in a for a in r['avisos'])


def test_sin_libro_capex_la_set_se_dimensiona_igual(tmp_path):
    """042:RF-33 — sin libro, o con uno que no se lee, no hay módulos pero tampoco error: se dice y se sigue."""
    from convertersmartgrid import set_nueva as sn

    assert sn.modulos_del_libro('', {})[0] == [] and 'CAPEX' in sn.modulos_del_libro('', {})[1][0]
    assert sn.modulos_del_libro(str(tmp_path / 'no.xlsx'), {'hoja': 'x'})[0] == []


def test_la_web_ofrece_la_optimizacion_de_con_proyecto():
    """042:RF-13 — la ruta del paso de obras, como trabajo del carril de DIgSILENT."""
    from convertersmartgrid.web.app import create_app

    rutas = {getattr(r, 'path', '') for r in create_app().routes}
    assert '/api/workspaces/{wid}/pf/obras/con-proyecto' in rutas


def test_sin_dato_de_la_set_nueva_se_conserva_la_escalera(monkeypatch):
    """042:RF-8, 042:RF-12 — si a la SET nueva le falta un dato, se dice en su informe y el trabajo
    conserva lo que midió la escalera."""
    monkeypatch.setattr(services, 'optimizar_con_proyecto', lambda *a, **k: {'caben': 3, 'a_set_nueva': [{'sed': 'N'}]})
    # 063:RF-34: la optimización suma las cargas aplicadas para el umbral de la SET nueva. 086:RF-76: con ninguna
    # aplicada el trabajo corrige el estado actual y no optimiza cargas; el doble devolvía [] y a la vez esperaba que la
    # optimización hallara 3 que caben, un mundo que no puede darse. Una carga aplicada en NA203 lo hace coherente.
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas',
                        lambda ws, project: [{'sed': 'N', 'alimentador': 'NA203', 'kw': 100.0, 'variacion': 'Carga_N'}])

    def falta(*_a, **_k):
        raise services.UserError('sin tasa de crecimiento de la spec 029 para NA203 (042:RF-8).')

    monkeypatch.setattr(services, 'set_nueva_proponer', falta)
    r = services.con_proyecto_optimizar(None, _Ctx(), 'P', ['NA203'])
    assert r['escalera_por_cargas']['caben'] == 3 and 'NA203' in r['set_nueva']['avisos'][0]


def test_cargas_aplicadas_de_todas_las_ejecuciones(tmp_path):
    """042:RF-1, 040:RF-6, 040:RF-11 — las cargas nuevas aplicadas salen de los informes de todas
    las ejecuciones del espacio, por fecha: una creada antes en otra ejecución y reutilizada hoy
    sigue, con su variación renombrada; la eliminada y la duplicada, no."""
    import json
    import os
    from types import SimpleNamespace

    raiz = tmp_path / 'ws'
    vieja, nueva = raiz / 'runs' / 'a' / 'salida', raiz / 'runs' / 'b' / 'salida'
    for d in (vieja, nueva, raiz / 'planes'):
        d.mkdir(parents=True)
    carga = lambda sed, var: {'sed': sed, 'alimentador': 'NA203', 'barra': 'B', 'variacion': var}  # noqa: E731
    (vieja / 'cargas_pf_aplicacion_t1.json').write_text(json.dumps({'project': 'P', 'cargas': [
        carga('UNO', 'Carga_UNO_LARGA_SIN_ALIM'), carga('DOS', 'Carga_DOS_X'), carga('TRES', 'Carga_TRES_X')]}))
    (nueva / 'cargas_pf_aplicacion_t2.json').write_text(json.dumps({
        'project': 'P', 'cargas': [carga('CUATRO', 'Carga_CUATRO_NA203_2')],
        'reutilizadas': [{'sed': 'UNO', 'alimentador': 'NA203', 'variacion': 'Carga_UNO_NA203_2'}],
        'eliminadas': [{'variacion': 'Carga_DOS_X', 'eliminada': True}],
        'duplicadas': [{'sed': 'TRES', 'duplicada_de': 'UNO'}]}))
    os.utime(vieja / 'cargas_pf_aplicacion_t1.json', (1, 1))
    ws = SimpleNamespace(root=raiz, out_dir=nueva, plans_dir=raiz / 'planes')
    cargas = {c['sed']: c['variacion'] for c in services._cargas_nuevas_aplicadas(ws, 'P')}
    assert cargas == {'UNO': 'Carga_UNO_NA203_2', 'CUATRO': 'Carga_CUATRO_NA203_2'}


def test_si_caben_basta_una_obra_y_las_lecturas_comunes_van_una_vez(tmp_path, monkeypatch):
    """042:RF-2 — para saber si caben, la evaluación pide «basta_una» al guion y para en el primer
    alimentador sin obra (F2 no se mide); la curva, el CAPEX y los tipos se leen una vez en todo el
    trabajo aunque la escalera se llame varias veces (NA203 + NA205, 2026-11-01: cada prueba
    releía los tipos en 2 min 14 s y medía NA205 tras fallar NA203, unos 40 min más)."""
    from test_casos_por_anio import ANIO, _escalera_falsa

    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': False, 'fraccion': None, 'perdidas_kw': None,
                'motivos': ['no converge']}

    services_, ws, ctx, planes, aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'nueva_terna': 40000}, alimentadores=('F1', 'F2'))
    lecturas = {'tipos': 0, 'curva': 0}
    tipos, curva = services_.obras_bibliotecas, services_._curva_del_anio

    def contar(clave, f):
        def g(*a, **k):
            lecturas[clave] += 1
            return f(*a, **k)
        return g

    monkeypatch.setattr(services_, 'obras_bibliotecas', contar('tipos', tipos))
    monkeypatch.setattr(services_, '_curva_del_anio', contar('curva', curva))
    memo: dict = {}
    for _ in range(3):
        r = services_.obras_escalera(ws, ctx, 'P', ['F1', 'F2'], anio_casos=ANIO, aplicar=False,
                                     basta_una=True, memo=memo)
        assert [f['alimentador'] for f in r['alimentadores']] == ['F1']
        assert r['alimentadores'][0]['elegida'] is None
    evaluados = [p for a, p in planes if '--evaluar' in a]
    assert evaluados and all(p['basta_una'] and p['feeders'] == ['F1'] for p in evaluados)
    assert lecturas == {'tipos': 1, 'curva': 1} and aplicadas == []
    # Sin «basta_una» se miden los dos, como siempre, y el guion no recibe la marca.
    planes.clear()
    r = services_.obras_escalera(ws, ctx, 'P', ['F1', 'F2'], anio_casos=ANIO, aplicar=False)
    assert [f['alimentador'] for f in r['alimentadores']] == ['F1', 'F2']
    assert all('basta_una' not in p for a, p in planes if '--evaluar' in a)


def test_la_carga_que_parte_un_tramo_entra_en_la_set_nueva():
    """042:RF-18 — Pisco: su nodo solo existe en su variación; va por el extremo más cercano del tramo."""
    from convertersmartgrid.web.services import barra_del_tramo_partido

    tramos = [{'nombre': 'T1', 'desde': 'A', 'hasta': 'B'}]
    assert barra_del_tramo_partido({'tramo_partido': {'tramo': 'T1', 'fraccion': 0.2}}, tramos, {}) == 'A'
    assert barra_del_tramo_partido({'tramo_partido': {'tramo': 'T1', 'fraccion': 0.8}}, tramos, {'B': 'B_MT'}) == 'B_MT'
    assert barra_del_tramo_partido({'tramo_partido': {'tramo': 'T9', 'fraccion': 0.8}}, tramos, {}) is None
    assert barra_del_tramo_partido({}, tramos, {}) is None


def test_el_resultado_directo_a_set_nueva_tiene_la_forma_de_los_demas():
    """042:RF-80 — con proyecto, orden y pruebas: sin ellos la web lo descartaba y el operador no veía su SET nueva."""
    from pathlib import Path

    from convertersmartgrid.web import services

    fuente = Path(services.__file__).read_text(encoding='utf-8')
    tramo = fuente.split('if directo_set_nueva:', 1)[1].split('elif escalera_primero', 1)[0]
    for clave in ("'project'", "'orden'", "'pruebas'", "'escalera'", "'a_set_nueva'"):
        assert clave in tramo


def test_la_web_no_queda_en_blanco_ni_esconde_resultados():
    """042:RF-79, 042:RF-81, 042:RF-82, 042:RF-83, 042:RF-84 — comprobado además en el navegador."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    assert 'SinPantallaEnBlanco' in (raiz / 'app' / 'main.tsx').read_text(encoding='utf-8')
    cargas = (raiz / 'features' / 'powerfactory' / 'CargasTab.tsx').read_text(encoding='utf-8')
    assert '{!simular && (' in cargas and 'a.ya_cumple ?' in cargas and 's.zonas' in cargas and 's.obra.error' in cargas
    assert 'job.result?.enlace' in (raiz / 'features' / 'asistente' / 'Asistente.tsx').read_text(encoding='utf-8')
    assert 'transmision: transmision.trim()' in (raiz / 'features' / 'powerfactory' / 'InformesPF.tsx').read_text(encoding='utf-8')
