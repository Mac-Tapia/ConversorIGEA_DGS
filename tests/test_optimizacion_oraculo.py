"""Spec 052: optimización de «Con proyecto» con el oráculo, en redes sintéticas cuya respuesta
se conoce (sin DIgSILENT).

La red: una fuente S a 10 kV, la troncal S–A–B y una carga nueva en B. Cada obra se compara con
el flujo del mismo grafo cambiado a mano: «mueve la tensión como su flujo exacto» (052 T2).
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip('scipy')

from convertersmartgrid import optimizacion_oraculo as oo
from convertersmartgrid.digital_twin.oraculo import muestra, sistema_de
from convertersmartgrid.escalera_optima import Parametros

PREFIJO = 'Red:\\Proy\\'


def _id(nombre: str, clase: str) -> str:
    return f'{clase}:{PREFIJO}{nombre}.{clase}'


def _grafo(*, r=2.0, x=1.5, carga_b_mw=0.3, nueva_mw=1.0):
    """Grafo leído con la carga nueva activa en B (RF-1): su demanda ya está en el nodo."""
    nodos = {_id('S', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': True, 'v_pu': 1.0},
             _id('A', 'ElmTerm'): {'kv': 10.0, 'p_mw': 0.2, 'q_mvar': 0.05, 'fuente': False},
             _id('B', 'ElmTerm'): {'kv': 10.0, 'p_mw': carga_b_mw + nueva_mw,
                                   'q_mvar': 0.1 + nueva_mw * 0.2, 'fuente': False}}
    ramas = [{'id': _id('T1', 'ElmLne'), 'desde': _id('S', 'ElmTerm'), 'hasta': _id('A', 'ElmTerm'),
              'r_ohm': r, 'x_ohm': x, 'inom_ka': 0.2, 'largo_km': 2.0, 'cerrada': True},
             {'id': _id('T2', 'ElmLne'), 'desde': _id('A', 'ElmTerm'), 'hasta': _id('B', 'ElmTerm'),
              'r_ohm': r, 'x_ohm': x, 'inom_ka': 0.2, 'largo_km': 2.0, 'cerrada': True}]
    return {'nodos': nodos, 'ramas': ramas}


NUEVA = {'variacion': 'Carga_X', 'nodo': _id('B', 'ElmTerm'), 'p_mw': 1.0, 'q_mvar': 0.2}
TIPOS = {'AA120': {'rline': 0.3, 'xline': 0.35, 'sline': 0.4}}


def _p(**kw) -> Parametros:
    base = dict(cumplimiento=0.95, sorteos=4, semilla=7, tolerancia_pu=0.001, tolerancia_carga_pct=1.0,
                max_variantes=40, tasa=0.12, vida=20, tension_min_pu=0.95, tension_max_pu=1.05,
                cargabilidad_max_pct=100.0)
    base.update(kw)
    return Parametros(**base)


def _exacto(grafo, nodo, extra_q_mvar=0.0):
    """Tensión de ``nodo`` resolviendo el grafo tal cual, con un banco opcional en él."""
    g = {'nodos': {n: dict(d) for n, d in grafo['nodos'].items()}, 'ramas': grafo['ramas']}
    g['nodos'][nodo]['q_mvar'] -= extra_q_mvar
    m = muestra(g)
    sol = sistema_de(m).resolver(m.s_carga)
    return float(sol.v[m.ids.index(nodo)])


def test_la_carga_nueva_y_cada_obra_como_su_flujo_exacto():
    """052:RF-2, 052:RF-3 — sin la nueva, con ella, con terna, con banco y con sección: la tensión
    de B es la del flujo del grafo cambiado a mano."""
    g = _grafo()
    ora = oo.Oraculo(g, [NUEVA], tipos=TIPOS)
    b = _id('B', 'ElmTerm')
    assert ora.medir([], 0).u['B'] == pytest.approx(_exacto(_grafo(nueva_mw=0.0), b), abs=1e-9)
    assert ora.medir([], 1).u['B'] == pytest.approx(_exacto(g, b), abs=1e-9)
    terna = ora.medir([{'clase': 'terna', 'tramos': ['T1', 'T2']}], 1).u['B']
    assert terna == pytest.approx(_exacto(_grafo(r=1.0, x=0.75), b), abs=1e-9)
    banco = ora.medir([{'clase': 'condensador', 'barra': 'B', 'q_kvar': 450.0}], 1).u['B']
    assert banco == pytest.approx(_exacto(g, b, extra_q_mvar=0.45), abs=1e-9)
    seccion = ora.medir([{'clase': 'seccion', 'tramos': ['T1', 'T2'], 'tipo': {'nombre': 'AA120'}}], 1).u['B']
    assert seccion == pytest.approx(_exacto(_grafo(r=0.6, x=0.7), b), abs=1e-9)
    assert terna > ora.medir([], 1).u['B'] and banco > ora.medir([], 1).u['B']


def test_regulador_lleva_aguas_abajo_a_su_consigna_y_lo_dice():
    """052:RF-2 — el regulador sube lo que cuelga de su tramo hasta la consigna, dentro del rango,
    y la medida queda marcada como aproximada (la confirma DIgSILENT, RF-5)."""
    ora = oo.Oraculo(_grafo(), [NUEVA])
    m = ora.medir([{'clase': 'regulador', 'tramo': 'T2', 'consigna_pu': 1.0, 'rango_pct': 10.0}], 1)
    assert m.aproximada
    assert m.u['B'] == pytest.approx(1.0, abs=1e-9)
    assert m.u['A'] == pytest.approx(ora.medir([], 1).u['A'], abs=1e-12)


def test_criterio_con_k_cargas_maxima_y_sorteos():
    """052:RF-3, 052:RF-9 — con la carga nueva B baja de 0,95 p.u. y no cumple; con terna, sí, en
    la máxima y en todos los sorteos; los límites salen de los parámetros, no del código."""
    ora = oo.Oraculo(_grafo(r=2.5, x=1.875), [NUEVA])
    p = _p()
    sin_obra = ora.evaluar([], 1, p, factores=[0.5, 0.8])
    assert not sin_obra['maxima'] and any('B' in m for m in sin_obra['motivos'])
    con_terna = ora.evaluar([{'clase': 'terna', 'tramos': ['T1', 'T2']}], 1, p, factores=[0.5, 0.8])
    assert con_terna['maxima'] and con_terna['fraccion'] == 1.0
    assert ora.evaluar([], 1, _p(tension_min_pu=0.80))['maxima']


def test_sorteos_de_markov_reproducen_la_cadena():
    """052:RF-14 — una curva que alterna bajo y alto da la transición 0↔1 y estacionaria ½–½; con
    la misma semilla, los mismos sorteos y en la forma de la escalera."""
    curva = [(t, {'F1': 50.0 if t % 2 else 100.0}) for t in range(40)]
    r = oo.sorteos_markov(curva, {'F1': 100.0}, n=10, semilla=3, niveles=2)
    assert r['transicion'] == [[0.0, 1.0], [1.0, 0.0]]
    assert r['estacionaria'] == pytest.approx([0.5, 0.5])
    niveles = [s['nivel'] for s in r['sorteos']]
    assert all(a != b for a, b in zip(niveles, niveles[1:]))
    assert r == oo.sorteos_markov(curva, {'F1': 100.0}, n=10, semilla=3, niveles=2)
    assert set(r['sorteos'][0]['factores']) == {'F1'}


def test_shapley_reparte_la_obra_entre_quien_la_necesita():
    """052:RF-15, 052:RF-16 — si solo A necesita la obra (100), A paga 100 y B nada; el total es el
    costo del grupo; con muchas cargas, por permutaciones sorteadas, y dice cuántas usó."""
    r = oo.reparto_shapley(['A', 'B'], lambda g: 100.0 if 'A' in g else 0.0, semilla=1)
    assert r['exacto'] and r['reparto'] == {'A': 100.0, 'B': 0.0}
    assert sum(r['reparto'].values()) == pytest.approx(r['costo_total'])
    muchas = [f'C{i}' for i in range(9)]
    r = oo.reparto_shapley(muchas, lambda g: 10.0 * len(g), semilla=1, permutaciones=12)
    assert not r['exacto'] and r['permutaciones'] == 12
    assert all(v == pytest.approx(10.0) for v in r['reparto'].values())
    nada = oo.reparto_shapley(['A'], lambda g: None, semilla=1)
    assert nada['reparto'] == {} and 'aviso' in nada


def _espacio():
    return oo.Espacio('F1', barras=['B'], banco_kvar=150.0, modulos_max=4,
                      tramos=[{'nombre': 'T1', 'largo_m': 2000.0}, {'nombre': 'T2', 'largo_m': 2000.0}],
                      secciones=[{'nombre': 'AA120', 'origen': 'proyecto', 'proyecto': ''}])


def test_busqueda_bayesiana_da_la_combinacion_mas_barata_que_cumple():
    """052:RF-11, 052:RF-12, 052:RF-16 — con un oráculo real, la búsqueda bayesiana halla la obra
    más barata que deja B en límites, y dice cuántas evaluaciones usó."""
    pytest.importorskip('optuna')
    ora = oo.Oraculo(_grafo(r=4.0, x=3.0), [NUEVA], tipos=TIPOS)
    p = _p()
    precio = {'bancos': 1.0, 'terna': 50.0, 'seccion': 40.0}

    def valorar(v):
        e = ora.evaluar(v.obras, 1, p)
        return sum(precio[k] * c for k, c in v.cantidades.items()), e['maxima'], e

    r = oo.buscar_combinacion(_espacio(), valorar, evaluaciones=60, semilla=0)
    assert r['variante'] is not None and r['evaluaciones'] == 60 and r['agotado']
    esp = _espacio()
    opciones = esp.opciones_tramo()
    mejor = min(c for n in range(5) for t1 in opciones for t2 in opciones
                for c, ok, _ in [valorar(esp.obras([n], [t1, t2]))] if ok)
    assert r['costo_anual'] == pytest.approx(mejor)


def test_frente_de_pareto_con_el_nsga2_del_gemelo():
    """052:RF-13 — el frente solo trae combinaciones que cumplen, ordenadas por costo, con sus
    pérdidas y su tensión mínima."""
    ora = oo.Oraculo(_grafo(r=4.0, x=3.0), [NUEVA], tipos=TIPOS)
    p = _p()

    def medir(v):
        e = ora.evaluar(v.obras, 1, p)
        return float(len(v.obras)), e['perdidas_kw'], e['v_min'], e['maxima']

    r = oo.frente_pareto(_espacio(), medir, semilla=0, poblacion=12, generaciones=6)
    assert r['frente'] and r['evaluaciones'] > 0
    assert [f['costo_anual'] for f in r['frente']] == sorted(f['costo_anual'] for f in r['frente'])
    assert all(f['v_min'] >= p.tension_min_pu - 1e-9 for f in r['frente'])


def test_lectura_unica_del_grafo_y_de_las_cargas_nuevas_con_el_doble():
    """052:RF-1 — en «Con proyecto», con las variaciones de las cargas nuevas activas, una lectura
    da el grafo del gemelo (con el largo de cada tramo) y, por carga nueva, su nodo en el grafo y
    su P y Q; las variaciones quedan como estaban."""
    import random

    from apoyo import cargar_herramienta
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas
    from test_casos_pf import cargas_guion
    from test_obras_pf_guion import CON, _activas, _calibrada_con_escenario, _plan

    guion = cargar_herramienta('obras_pf.py', 'obras_052', tools_en_path=True)
    app, alims = _calibrada_con_escenario(random.Random(23))
    f = alims[0]
    nuevas = [_nueva('N1', barra=f'{f}_B1', tension_bt_kv=0.38)]
    base = {'variaciones': [], 'feeders': list(alims), 'excluidos': [],
            'ajustes': [{'feeder': a, 'cuadrado': True} for a in alims]}
    hecho, rc = cargas_guion.ejecutar(app, {**_plan_cargas(list(alims), nuevas=nuevas), 'base': base},
                                      simular=False)
    assert rc == 0, hecho
    carga = hecho['cargas'][0]
    antes = _activas(app, CON)
    plan = _plan(alims, barras={f: [carga['barra']]})
    plan['nuevas'] = [{'sed': 'N1', 'variacion': carga['variacion'], 'barra': carga['barra']}]
    informe, codigo = guion.datos_oraculo(app, plan)
    assert codigo == 0, informe
    assert informe['modo'] == 'datos_oraculo' and informe['grafo']['nodos']
    (nueva,) = informe['nuevas']
    assert nueva['nodo'] in informe['grafo']['nodos'] and nueva['p_mw'] > 0
    assert any('largo_km' in r for r in informe['grafo']['ramas'])
    assert _activas(app, CON) == antes


def _dos_cargas():
    g = _grafo(r=2.5, x=1.875, nueva_mw=1.1)
    nuevas = [{'variacion': 'Carga_G', 'nodo': _id('B', 'ElmTerm'), 'p_mw': 1.0, 'q_mvar': 0.2,
               'alimentador': 'F1', 'barra': 'B'},
              {'variacion': 'Carga_P', 'nodo': _id('B', 'ElmTerm'), 'p_mw': 0.1, 'q_mvar': 0.02,
               'alimentador': 'F1', 'barra': 'B'}]
    return oo.Oraculo(g, nuevas, tipos=TIPOS)


def _alimentador(espacio=None):
    from convertersmartgrid.escalera_optima import Variante

    terna = Variante('terna', ('terna',), [{'clase': 'terna', 'tramos': ['T1', 'T2']}], {'terna': 4.0})
    banco = Variante('banco', ('bancos',), [{'clase': 'condensador', 'barra': 'B', 'q_kvar': 150.0}], {'bancos': 1.0})
    precio = {'bancos': 1.0, 'terna': 50.0, 'seccion': 40.0}
    return oo.Alimentador('F1', [terna, banco], lambda v, _perd: sum(precio[k] * c for k, c in v.cantidades.items()),
                          espacio)


def test_buscar_k_y_elegir_con_el_oraculo():
    """052:RF-4 — el mayor k que cabe con obra (galope y bisección de la 042) y, para él, la
    variante de menor costo entre las que cumplen; las que no, detrás, por cercanía."""
    ora = _dos_cargas()
    p = _p()
    a = _alimentador()
    k, pruebas = oo.buscar_k(ora, [a], p)
    assert k == 2 and pruebas
    eleccion = oo.elegir_para_k(ora, [a], k, p, evaluaciones_bayes=0, pareto=False)['F1']
    assert eleccion['elegida'] == 'terna'
    assert [v.nombre for v in eleccion['orden']][0] == 'terna'
    assert eleccion['shapley']['reparto'] and sum(eleccion['shapley']['reparto'].values()) == pytest.approx(
        eleccion['shapley']['costo_total'])


def test_la_bayesiana_va_primera_si_cumple_y_cuesta_menos():
    """052:RF-12, 052:RF-13 — si la bayesiana halla una combinación que cumple y cuesta menos que
    la mejor de la escalera, encabeza el orden que confirma DIgSILENT; el frente marca la elegida."""
    pytest.importorskip('optuna')
    ora = _dos_cargas()
    p = _p()
    a = _alimentador(_espacio())
    eleccion = oo.elegir_para_k(ora, [a], 2, p, evaluaciones_bayes=40, semilla=0)['F1']
    primera = eleccion['tabla'][0]
    assert primera['cumple'] and primera['costo_anual'] <= 50.0 * 4.0
    assert eleccion['bayesiana']['evaluaciones'] == 40
    assert eleccion['pareto'] is not None


def test_digsilent_confirma_y_si_discrepa_manda_el(monkeypatch, tmp_path):
    """052:RF-5, 052:RF-6, 052:RF-7, 052:RF-10 — el oráculo da 2 cargas; un DIgSILENT doble solo
    confirma 1: se baja k, se anota la discrepancia, se aplica con 1 y se dicen los tiempos."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    ora = _dos_cargas()
    nuevas = [{**c, 'sed': c['variacion'][6:], 'kw': c['p_mw'] * 1000} for c in ora.nuevas]
    llamadas = []

    def obras_escalera(ws, ctx, project, feeders, *, cargas_activas=None, aplicar=True, solo_comun=False,
                       variantes_de=None, **kw):
        if solo_comun:
            curva = [(t, 900.0 if t % 2 else 1000.0) for t in range(12)]
            return {'p': _p(), 'perfil': {}, 'anio_casos': None, 'objetivos': {'F1': {'kw': 1000.0}},
                    'curvas': {'F1': curva}, 'sorteos': [], 'perdidas': {'F1': None}, 'costos': {},
                    'kvar': {}, 'lectura': {'tipos': [], 'alimentadores': {'F1': {'kv': 10.0}}}}
        llamadas.append((len(cargas_activas), aplicar, {f: [v.nombre for v in vs] for f, vs in variantes_de.items()}))
        cabe = len(cargas_activas) <= 1
        return {'alimentadores': [{'alimentador': 'F1', 'elegida': 'terna' if cabe else None,
                                   'tabla': [{'nombre': 'terna', 'maxima': cabe, 'fraccion': 1.0 if cabe else None}]}]}

    datos = {'grafo': _grafo(r=2.5, x=1.875, nueva_mw=1.1), 'nuevas': nuevas,
             'alimentadores': {'F1': {'troncal': [{'nombre': 'T1', 'largo_m': 2000.0, 'corriente_a': 60.0},
                                                  {'nombre': 'T2', 'largo_m': 2000.0, 'corriente_a': 60.0}],
                                      'indices': {'B': 1}, 'existen': ['B'], 'media': {}, 'fuera_desde': None}}}
    monkeypatch.setattr(services, 'obras_escalera', obras_escalera)
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, datos, None))
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [
        {'sed': c['sed'], 'variacion': c['variacion'], 'alimentador': 'F1', 'barra': 'B', 'kw': c['kw']}
        for c in nuevas])
    monkeypatch.setattr(services, 'native_action_context', lambda *a, **k: {})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'X')
    ws = SimpleNamespace(out_dir=tmp_path)
    ctx = SimpleNamespace(log=lambda *_: None, check_cancel=lambda: None)
    r = services.optimizar_con_proyecto(ws, ctx, 'P', ['F1'])
    assert r['caben'] == 1
    assert r['oraculo']['discrepancias'] == [{'cargas': 2, 'oraculo': 'cabe', 'digsilent': 'no cabe'}]
    assert llamadas[-1][0] == 1 and llamadas[-1][1] is True                    # se aplica con 1
    assert r['oraculo']['comparacion'] and set(r['oraculo']['tiempos']) >= {'oraculo_s', 'digsilent_s'}
    assert list(tmp_path.glob('oraculo_con_proyecto_*.json'))
    assert [c['sed'] for c in r['a_set_nueva']] == ['P']


def _lectura(ora, obras, rol, *, perdidas_kw=None, variaciones=(), quitar=()):
    """La lectura de ``digital_twin_snapshot_pf.py`` tras reabrir, con el flujo que da el oráculo para ``obras``."""
    from convertersmartgrid.digital_twin.evolutivo import nombre_corto

    m = ora.medir(obras, len(ora.nuevas))
    grafo = ora.grafo
    flujo = {'tensiones': {'unidad': 'p.u.', 'valores': {n: m.u[nombre_corto(n)] for n in grafo['nodos']
                                                         if nombre_corto(n) in m.u}},
             'perdidas': {'unidad': 'kW', 'valores': {'total': m.perdidas_kw if perdidas_kw is None else perdidas_kw}},
             'cargabilidad': {'unidad': '%', 'valores': {'lineas': dict(m.carga)}}}
    for bloque in quitar:
        flujo.pop(bloque)
    return {'project': 'P', 'feeders': ['F1'], 'reopen_verified': True, 'flujo': flujo,
            'caso_nativo': {'rol': rol, 'nombre': rol, 'id': f'IntCase:{rol}'},
            'contexto': {'year': None, 'period': '2026-07', 'criterio_fijas': 'coincidente'},
            'topologia': {'grafo': grafo, 'variaciones_activas': list(variaciones),
                          'barras': {n: {'nombre': n, 'kv': d['kv']} for n, d in grafo['nodos'].items()}}}


def _optimizar_con_aceptacion(monkeypatch, tmp_path, lecturas):
    """La optimización de la 052 con un DIgSILENT doble que confirma una carga, aplica la terna y, al releer,
    da ``lecturas[caso]`` (o lanza si es una excepción)."""
    from types import SimpleNamespace

    from convertersmartgrid import perfil_empresa
    from convertersmartgrid.native_action import build_native_action_context
    from convertersmartgrid.web import services

    ora = _dos_cargas()
    nuevas = [{**c, 'sed': c['variacion'][6:], 'kw': c['p_mw'] * 1000} for c in ora.nuevas]
    perfil = {'informes': {'norma': 'Norma'},
              'estudios': {'tension_min_pu': 0.5, 'tension_max_pu': 1.5, 'cargabilidad_max_pct': 1000.0}}

    def obras_escalera(ws, ctx, project, feeders, *, cargas_activas=None, aplicar=True, solo_comun=False,
                       variantes_de=None, **kw):
        if solo_comun:
            curva = [(t, 900.0 if t % 2 else 1000.0) for t in range(12)]
            return {'p': _p(), 'perfil': perfil, 'anio_casos': None, 'objetivos': {'F1': {'kw': 1000.0}},
                    'curvas': {'F1': curva}, 'sorteos': [], 'perdidas': {'F1': None}, 'costos': {},
                    'kvar': {}, 'lectura': {'tipos': [], 'alimentadores': {'F1': {'kv': 10.0}}}}
        cabe = len(cargas_activas) <= 1
        elegida = variantes_de['F1'][0] if cabe else None
        if aplicar and cabe:
            aplicadas.extend(elegida.obras)
        return {'alimentadores': [{'alimentador': 'F1', 'elegida': elegida.nombre if cabe else None,
                                   'aplicada': ['Obra_F1'] if aplicar and cabe else None,
                                   'tabla': [{'nombre': v.nombre, 'maxima': cabe, 'fraccion': 1.0 if cabe else None}
                                             for v in variantes_de['F1'][:1]]}]}

    datos = {'grafo': _grafo(r=2.5, x=1.875, nueva_mw=1.1), 'nuevas': nuevas,
             'alimentadores': {'F1': {'troncal': [{'nombre': 'T1', 'largo_m': 2000.0, 'corriente_a': 60.0},
                                                  {'nombre': 'T2', 'largo_m': 2000.0, 'corriente_a': 60.0}],
                                      'indices': {'B': 1}, 'existen': ['B'], 'media': {}, 'fuera_desde': None}}}
    planes, aplicadas = [], []

    def guion_pf(ws, ctx, script, plan, *, nombre, **kw):
        if script == 'digital_twin_snapshot_pf.py':
            planes.append(plan)
            lectura = lecturas[plan['case']]
            if isinstance(lectura, Exception):
                raise lectura
            return 0, lectura(aplicadas), None
        return 0, datos, None

    accion = build_native_action_context({'source_run_id': 'r1', 'source_mode': 'txt', 'source_fingerprint': 'a' * 64},
                                         'P', ['F1'], 'obras')
    monkeypatch.setattr(services, 'obras_escalera', obras_escalera)
    monkeypatch.setattr(services, '_guion_pf', guion_pf)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [
        {'sed': c['sed'], 'variacion': c['variacion'], 'alimentador': 'F1', 'barra': 'B', 'kw': c['kw']}
        for c in nuevas])
    monkeypatch.setattr(services, 'native_action_context', lambda *a, **k: accion)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *a, **k: {'informes': [{'criterio_fijas': 'coincidente'}]})
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'X')
    monkeypatch.setattr(perfil_empresa, 'estructura_empresa', lambda: None)
    vistos = []
    ws = SimpleNamespace(out_dir=tmp_path, criterio_cabecera={'j': {'periodo': '2026-07'}})
    ctx = SimpleNamespace(log=vistos.append, check_cancel=lambda: None)
    return services.optimizar_con_proyecto(ws, ctx, 'P', ['F1']), planes, vistos, ora


def test_la_alternativa_aplicada_se_acepta_con_su_medicion_nativa_completa(monkeypatch, tmp_path):
    """044:RF-6, 044:RF-7, 044:RF-9, 052:RF-5 — lo que confirma la 052 se acepta solo tras releer «Con proyecto» con la
    obra y «Sin proyecto» de referencia, y comparar con el oráculo; la lectura de «Con proyecto» pide tras reabrir las
    variaciones aplicadas. Con un DIgSILENT doble: la persistencia en el motor real es de la T4."""
    ora = _dos_cargas()
    lecturas = {'con_proyecto': lambda obras: _lectura(ora, obras, 'con_proyecto', variaciones=['Obra_F1']),
                # La referencia sin obras ni cargas nuevas pierde más que con ellas (024:RF-31).
                'sin_proyecto': lambda obras: _lectura(ora, obras, 'sin_proyecto', perdidas_kw=1e6)}
    r, planes, vistos, _ora = _optimizar_con_aceptacion(monkeypatch, tmp_path, lecturas)
    aceptacion = r['oraculo']['aceptacion_nativa']
    assert aceptacion['aceptada'] is True and aceptacion['verificada'] is True, aceptacion['motivos']
    assert aceptacion['evaluacion']['clase'] == 'accepted' and aceptacion['validacion']['valida']
    assert [p['case'] for p in planes] == ['con_proyecto', 'sin_proyecto']
    assert planes[0]['variaciones_esperadas'] == ['Obra_F1'] and planes[0]['native_action_context']
    assert any('044:RF-7' in t and 'Aceptada' in t for t in vistos)
    guardado = json.loads(next(tmp_path.glob('oraculo_con_proyecto_*.json')).read_text(encoding='utf-8'))
    assert guardado['aceptacion_nativa']['aceptada'] is True


@pytest.mark.parametrize('caso', ['sin_perdidas', 'otra_obra', 'sin_digsilent', 'difiere'])
def test_la_alternativa_que_no_pasa_se_avisa_y_la_corrida_sigue(monkeypatch, tmp_path, caso):
    """044:RF-6, 044:RF-7, 044:RF-9 — una medición incompleta, una obra que ya no está activa tras reabrir, DIgSILENT sin
    responder o lo medido lejos de lo predicho: no se acepta, el aviso dice el motivo y la corrida termina con lo
    de la SET nueva."""
    from convertersmartgrid.web.services import UserError

    ora = _dos_cargas()

    def con(obras):
        lectura = _lectura(ora, obras, 'con_proyecto', variaciones=[] if caso == 'otra_obra' else ['Obra_F1'],
                           quitar=('perdidas',) if caso == 'sin_perdidas' else ())
        if caso == 'difiere':
            lectura['flujo']['perdidas']['valores']['total'] *= 3
        return lectura

    lecturas = {'con_proyecto': UserError('No se pudo conectar con DIgSILENT.') if caso == 'sin_digsilent' else con,
                'sin_proyecto': lambda obras: _lectura(ora, obras, 'sin_proyecto', perdidas_kw=1e6)}
    r, _planes, vistos, _ora = _optimizar_con_aceptacion(monkeypatch, tmp_path, lecturas)
    aceptacion = r['oraculo']['aceptacion_nativa']
    assert aceptacion['aceptada'] is False and aceptacion['motivos'], aceptacion
    esperado = {'sin_perdidas': 'perdidas', 'otra_obra': 'siga aplicada', 'sin_digsilent': 'No se pudo conectar',
                'difiere': 'del gemelo'}[caso]
    assert any(esperado in m for m in aceptacion['motivos']), aceptacion['motivos']
    assert not any('no converge' in m for m in aceptacion['motivos'])
    assert any(t.startswith('AVISO: no se acepta') and esperado in t for t in vistos)
    assert r['caben'] == 1 and [c['sed'] for c in r['a_set_nueva']] == ['P']


def test_sin_grafo_se_busca_en_digsilent(monkeypatch):
    """052:RF-8 — si el oráculo no puede leer el grafo, se dice y se busca en DIgSILENT."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    vistos = []
    monkeypatch.setattr(services, '_optimizar_con_oraculo',
                        lambda *a, **k: (_ for _ in ()).throw(services._SinOraculo('sin grafo')))
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [
        {'sed': 'G', 'variacion': 'Carga_G', 'alimentador': 'F1', 'barra': 'B', 'kw': 1.0}])
    monkeypatch.setattr(services, 'obras_escalera', lambda *a, **k: {'alimentadores': [{'elegida': 'x'}]})
    ctx = SimpleNamespace(log=vistos.append, check_cancel=lambda: None)
    r = services.optimizar_con_proyecto(SimpleNamespace(), ctx, 'P', ['F1'])
    assert r['caben'] == 1 and any('052:RF-8' in t for t in vistos)


def test_pinn_como_segundo_oraculo_dentro_de_su_dominio():
    """052:RF-17 — con un PINN en su dominio, su tensión decide y la medida lo dice; fuera de su
    dominio, decide el flujo físico."""
    class Pinn:
        def __init__(self, fuera):
            self.fuera = fuera

        def predecir(self, grafo):
            ids = sorted(grafo['nodos'])
            return {'ids': ids, 'v': [0.99] * len(ids), 'fuera_de_dominio': self.fuera}

    dentro = oo.Oraculo(_grafo(), [NUEVA], pinn=Pinn(False)).medir([], 1)
    assert dentro.oraculo == 'pinn' and dentro.u['B'] == pytest.approx(0.99)
    fuera = oo.Oraculo(_grafo(), [NUEVA], pinn=Pinn(True)).medir([], 1)
    assert fuera.oraculo == 'fisica' and fuera.u['B'] == pytest.approx(oo.Oraculo(_grafo(), [NUEVA]).medir([], 1).u['B'])


def test_set_nueva_comprobada_con_el_oraculo_y_con_su_nombre():
    """052:RF-18, 052:RF-19 — una carga que la red existente no puede (B a 0,84 p.u.) cumple con la
    SET nueva: el tramo de entrada abierto y B alimentada desde la SET por una línea corta; la obra
    de la SET nueva lleva el nombre que da el operador."""
    from convertersmartgrid.obras_pf import validar_obra

    ora = oo.Oraculo(_grafo(r=4.0, x=3.0), [{**NUEVA, 'alimentador': 'F1', 'barra': 'B'}])
    p = _p()
    assert not ora.evaluar([], 1, p)['maxima']
    con_set = ora.con_set_nueva([{'entrada': 'T2', 'nodo': 'B', 'distancia_km': 0.5,
                                  'r_ohm_km': 0.3, 'x_ohm_km': 0.35, 'inom_ka': 0.4}], kv=10.0)
    e = con_set.evaluar([], 1, p)
    assert e['maxima'], e['motivos']
    obra = validar_obra({'clase': 'set_nueva', 'alimentador': 'NA203', 'casos': ['Con proyecto'],
                         'destino': '-14.8, -74.9', 'ramas': ['NA203/N1'], 'mva': 25, 'kv_alta': 60,
                         'nombre_set': 'SET COPARA'})
    assert obra.nombre_set == 'SET COPARA'
