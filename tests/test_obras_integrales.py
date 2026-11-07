"""Transferir, trasladar, alimentador nuevo con su celda, costos del libro y área (spec 087, RF-31 a RF-41)."""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta

from convertersmartgrid import escalera_optima as eo
from convertersmartgrid import obras_integrales as oi
from convertersmartgrid import optimizacion_oraculo as oo
from convertersmartgrid.web import services

PERFIL = {'escalera': {'cumplimiento': 0.95, 'sorteos': 200, 'semilla': 7, 'tolerancia_pu': 0.005,
                       'tolerancia_carga_pct': 1.0},
          'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
          'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
P = eo.parametros(PERFIL)
TIPOS = [{'nombre': f'AA{s}_{kv:g}', 'clase': 'TypLne', 'datos': {'uline': kv, 'sline': s / 1000 * 3, 'cohl_': 1}}
         for kv in (10.0, 22.9) for s in (50, 120, 240)]
TRONCAL = {'T1', 'T2', 'T3'}
# 098:RF-11: cada tramo con su seccionador, para que haya dónde transferir y trasladar.
SW = {'clase': 'StaSwitch', 'nombre': 'SW'}
CAMINO = [{'nombre': 'T1', 'desde': 'CAB', 'hasta': 'B1', 'largo_m': 1000, 'u': {'B1': 0.99}, 'corriente_a': 100, 'maniobra': SW},
          {'nombre': 'T2', 'desde': 'B1', 'hasta': 'B2', 'largo_m': 1000, 'u': {'B2': 0.96}, 'corriente_a': 90, 'maniobra': SW},
          {'nombre': 'T3', 'desde': 'B2', 'hasta': 'B3', 'largo_m': 1000, 'u': {'B3': 0.94}, 'corriente_a': 80, 'maniobra': SW},
          {'nombre': 'R1', 'desde': 'B3', 'hasta': 'R1B', 'largo_m': 500, 'u': {'R1B': 0.93}, 'corriente_a': 40, 'maniobra': SW},
          {'nombre': 'R2', 'desde': 'R1B', 'hasta': 'CARGA', 'largo_m': 500, 'u': {'CARGA': 0.92}, 'corriente_a': 40}]


def _vecino(nombre, d, u=0.99, carga=50.0, kv=10.0):
    return {'alimentador': nombre, 'distancia_m': d, 'u_min': u, 'carga_max_pct': carga, 'kv': kv, 'barra': 'X'}


def test_la_transferencia_lleva_la_cola_desde_donde_sale_de_limites():
    """087:RF-32 — el nodo es la barra de la troncal donde la tensión baja del límite; el traslado, la rama."""
    assert oi.nodo_de_transferencia(CAMINO, TRONCAL, 0.95) == 'B3'
    assert oi.nodo_de_rama(CAMINO, TRONCAL, 'CARGA') == 'R1B'
    assert oi.nodo_de_rama(CAMINO[:3], TRONCAL, 'B3') == 'B3'          # cuelga de la troncal: la propia barra
    assert oi.candidatos_de_transferencia(CAMINO, TRONCAL, 0.95) == ['B3']          # 087:RF-52
    # Sin barra fuera de límites, la de 2/3 de la troncal (042:RF-37).
    sanos = [{**t, 'u': {t['hasta']: 0.99}} for t in CAMINO]
    assert oi.nodo_de_transferencia(sanos, TRONCAL, 0.95) == 'B2'


def test_solo_vecinos_con_margen_y_los_mas_cercanos():
    """087:RF-32 — sin margen de tensión o de carga, o sin flujo, no recibe; como mucho dos, el más cercano primero."""
    vecinos = [_vecino('LEJOS', 9000), _vecino('BAJO', 100, u=0.955), _vecino('LLENO', 200, carga=95.0),
               _vecino('CERCA', 800), _vecino('MEDIO', 3000), {**_vecino('SINFLUJO', 50), 'u_min': None}]
    assert [v['alimentador'] for v in oi.vecinos_con_margen(vecinos, P)] == ['CERCA', 'MEDIO']


def test_primero_transferir_luego_trasladar_con_enlace_y_migracion():
    """087:RF-31, 087:RF-33 — por vecino útil, la transferencia y después el traslado; a otra tensión, la migración cambia de nivel."""
    vecinos = {'B3': [_vecino('V1', 1000)], 'R1B': [_vecino('V2', 500, kv=22.9)]}
    vs, avisos = oi.variantes('F1', 10.0, CAMINO, TRONCAL, 'CARGA', vecinos, TIPOS, P)
    assert not avisos and [v.escalones for v in vs] == [('transferencia',), ('traslado',)]
    enlace, migracion = vs[1].obras
    assert enlace == {**enlace, 'clase': 'enlace', 'alimentador': 'V2', 'cede': 'F1', 'destino': 'R1B'}
    assert enlace['tipo']['nombre'].endswith('22.9') and migracion['kv_destino'] == 22.9 and migracion['nodo'] == 'R1B'
    assert '22.9 kV' in vs[1].nombre and vs[0].cantidades['transferencia'] == pytest.approx(1.0 * oi.FACTOR_RUTA)
    _, avisos = oi.variantes('F1', 10.0, CAMINO, TRONCAL, 'CARGA', {}, TIPOS, P)
    assert len(avisos) == 2 and all('087:RF-32' in a for a in avisos)


def test_el_area_del_alimentador_nuevo():
    """087:RF-34, 087:RF-38 — centro de carga, demanda presente y a horizonte, contorno y barras que pasan."""
    nuevas = [{'sed': 'N1', 'kw': 300.0, 'lat': -13.70, 'lon': -76.20}, {'sed': 'N2', 'kw': 100.0, 'lat': -13.72, 'lon': -76.22}]
    ramas = [{'barras': ['A', 'B'], 'kw_existente': 200.0}]
    a = oi.area_propuesta('EXP 1', nuevas, ramas, {'A': [-13.69, -76.19], 'B': [-13.73, -76.25]}, 200.0, 2.0, 30)
    assert a['centro']['lat'] == pytest.approx(-13.705) and a['kw_presente'] == 600.0 and a['kw_horizonte'] == 800.0
    assert a['barras'] == ['A', 'B'] and a['contorno']['lon_min'] == -76.25 and a['anios'] == 30


def test_celda_y_km_del_libro_o_su_referencia_citada():
    """087:RF-36, 087:RF-37 — el libro manda y cita sus filas; sin él, el km de la terna y la celda de Osinergmin, por confirmar."""
    costos = eo.costos_de_alternativas({}, P)
    assert costos['celda']['costo_unitario'] == 58699.52 and 'Osinergmin' in costos['celda']['origen']
    sin_alim = eo.costos_de_alternativas({'nueva_terna': {'costo_unitario': 40.0, 'unidad': 'km'}},
                                         eo.parametros({**PERFIL, 'escalera': {**PERFIL['escalera'], 'escala_capex': 1000}}))
    assert sin_alim['nuevo_alimentador']['costo_unitario'] == 40000.0 and 'por confirmar' in sin_alim['nuevo_alimentador']['origen']
    from convertersmartgrid.pide_economia import ObraCapex, costos_por_alternativa

    libro = costos_por_alternativa([ObraCapex('P27320019', 'Pisco', 'Ampl.', 'Nuevo alimentador PO201', 'km', 5.0, 69.3, 346.5,
                                              'nuevo_alimentador')])
    assert libro['nuevo_alimentador']['proyectos'] == ['P27320019 (Pisco): Nuevo alimentador PO201']


def test_el_oraculo_no_descarta_lo_que_no_sabe_calcular():
    """087:RF-41 — el paso a 22,9 kV no lo modela el oráculo: lo mide DIgSILENT antes de transferir."""
    terna = eo.Variante('terna', ('terna',), [{'clase': 'terna'}], {})
    nivel = eo.Variante('paso a 22.9 kV', ('nivel',), [{'clase': 'migracion', 'kv_destino': 22.9}], {})
    assert oo.modelable(terna) and not oo.modelable(nivel)


class _Ctx:
    def __init__(self):
        self.textos = []

    def log(self, texto='', *_a, **_k):
        self.textos.append(texto)

    def check_cancel(self):
        pass


def test_tras_la_escalera_transferir_y_trasladar_antes_que_el_nivel(monkeypatch, tmp_path):
    """087:RF-31, 098:RF-23 — oráculo sin obra; transferir o trasladar se mide antes que el paso a 22,9 kV, cumple y se aplica: el nivel ya no se mide."""
    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas',
                        lambda ws, project: [{'sed': 'A', 'alimentador': 'F1', 'kw': 100.0, 'variacion': 'Carga_A'}])
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    v = eo.Variante('bancos', ('bancos',), [{'clase': 'condensador'}], {})
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {
        'alimentadores': {'F1': {'orden': [v], 'tabla': [{'nombre': 'bancos', 'cumple': False}], 'ya_cumple': False}},
        'tanda': 3})
    llamadas = []

    def escalera(ws, ctx, project, feeders, *, aplicar=False, traspaso=False, sin_oraculo=False, solo=None, **k):
        llamadas.append(('aplica' if aplicar else 'mide', 'traspaso' if traspaso else 'nivel' if sin_oraculo else 'oraculo'))
        elegida = 'traslado' if traspaso else None
        return {'alimentadores': [{'alimentador': 'F1', 'elegida': elegida, 'tabla': []}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    monkeypatch.setattr(services, 'confirmar_conjunto', lambda *a, **k: {'cumple': True})
    ctx = _Ctx()
    r = services.escalera_por_alimentador(object(), ctx, 'P', ['F1'])
    assert llamadas == [('mide', 'oraculo')] * 3 + [('mide', 'traspaso'), ('mide', 'nivel'), ('aplica', 'traspaso')]   # 098:RF-45, RF-46
    assert r['por_alimentador']['F1']['cumple'] and not r['a_set_nueva']
    assert any('087:RF-31' in t for t in ctx.textos)


def test_los_vecinos_se_leen_de_una_pasada_con_su_margen(monkeypatch):
    """087:RF-32 — en DIgSILENT: la barra más cercana de cada otro alimentador, a menos del radio, con su tensión y su carga."""
    guion = cargar_herramienta('obras_pf.py', 'obras_rf32', tools_en_path=True)

    class Obj:
        def __init__(self, nombre, gps=None, u=None, carga=None, kv=10.0):
            self.loc_name, self._gps, self._u, self._carga, self.uknom = nombre, gps, u, carga, kv

        def HasResults(self, _):
            return True

        def GetAttribute(self, a):
            return self._u if a == 'm:u' else self._carga

    class Feeder:
        def __init__(self, nombre, barras, lineas):
            self.loc_name, self._b, self._l = nombre, barras, lineas

        def GetObjs(self, clase):
            return self._b if clase == 'ElmTerm' else self._l

    feeders = [Feeder('F1', [Obj('N', (-13.70, -76.20), 0.93)], [Obj('L', carga=80)]),
               Feeder('V1', [Obj('V1a', (-13.701, -76.201), 0.99), Obj('V1b', (-13.80, -76.30), 0.98)], [Obj('L1', carga=40)]),
               Feeder('LEJOS', [Obj('Z', (-14.5, -76.9), 0.99)], [Obj('L2', carga=10)])]

    class Caso:
        def Activate(self):
            pass

    class App:
        def GetCalcRelevantObjects(self, _):
            return feeders

        def GetActiveStudyCase(self):
            return None

    monkeypatch.setattr(guion, 'activar_proyecto', lambda *a: object())
    monkeypatch.setattr(guion, 'casos_del_proyecto', lambda app, anio: {'con': Caso()})
    monkeypatch.setattr(guion, 'flujo_de_carga', lambda app: {'converged': True})
    monkeypatch.setattr(guion, 'cabecera_de', lambda elm: Obj('CAB', kv=10.0))
    monkeypatch.setattr(guion, 'gps_de', lambda b: b._gps)
    informe, rc = guion.datos_vecinos(App(), {'project': 'P', 'nodos': {'F1': ['N']}})
    assert rc == 0, informe
    filas = informe['vecinos']['F1']['N']
    assert [f['alimentador'] for f in filas] == ['V1'] and filas[0]['barra'] == 'V1a'
    assert filas[0]['u_min'] == 0.98 and filas[0]['carga_max_pct'] == 40 and filas[0]['distancia_m'] < 200


def test_la_celda_del_expreso_y_su_trazado_en_el_guion():
    """087:RF-35, 087:RF-34 — el expreso crea su interruptor en la salida y deja salida, llegada y trazado."""
    import inspect

    fuente = inspect.getsource(cargar_herramienta('obras_pf.py', 'obras_rf35', tools_en_path=True).construir_expreso)
    assert "CreateObject('StaSwitch'" in fuente and "'cbk'" in fuente
    assert "'salida_gps'" in fuente and "'llegada_gps'" in fuente and "'trazado'" in fuente


def test_a_la_misma_tension_la_migracion_solo_cambia_de_alimentador():
    """087:RF-32 — sin retipar tramos ni SED, y el enlace en servicio con su seccionador abierto también se cierra."""
    import inspect

    fuente = inspect.getsource(cargar_herramienta('obras_pf.py', 'obras_rf32m', tools_en_path=True).construir_migracion)
    assert 'misma = math.isclose(origen, destino' in fuente and 'if linea is None or misma:' in fuente
    assert "(int(getattr(linea, 'outserv', 0)) or abierto)" in fuente


def test_ninguna_variante_deja_barras_aisladas():
    """087:RF-42 — una barra que queda sin servicio con la obra no cumple; la que ya lo estaba no se le culpa."""
    sin = {'converge': True, 'u': {'B': 1.0}, 'carga': {}, 'aisladas': ['VIEJA']}
    bien, motivos = eo.cumple(sin, {**sin, 'aisladas': ['VIEJA', 'R1B', 'CARGA']}, [], P)
    assert not bien and 'aisladas' in motivos[0] and 'CARGA, R1B' in motivos[0]
    assert eo.cumple(sin, dict(sin), [], P)[0]
    import inspect

    fuente = inspect.getsource(cargar_herramienta('obras_pf.py', 'obras_rf42', tools_en_path=True).medida_para_criterio)
    assert 'IsEnergized()' in fuente and "out['aisladas']" in fuente


def test_el_oraculo_no_guarda_mas_redes_que_su_tope(monkeypatch):
    """087:RF-43 — con muchas combinaciones de obras, solo las más recientes; la que se vuelve a usar no se pierde."""
    from test_optimizacion_oraculo import NUEVA, TIPOS as TIPOS_ORACULO, _grafo

    monkeypatch.setattr(oo, 'MAX_SISTEMAS', 3)
    ora = oo.Oraculo(_grafo(r=0.1, x=0.1), [{**NUEVA, 'alimentador': 'F1', 'barra': 'B'}], tipos=TIPOS_ORACULO)
    tramos = [str(r['id']) for r in ora.grafo['ramas']]
    combinaciones = [[{'clase': 'terna', 'tramos': tramos[:i]}] for i in range(1, len(tramos) + 1)] + [[]]
    for obras in combinaciones:
        ora._sistema(obras, [])
        ora._sistema([], [])                       # la de sin obras se usa siempre: se queda
    assert len(ora._sistemas) <= 3 and () in ora._sistemas


def test_la_obra_elegida_se_aplica_sin_el_atajo_de_ya_cumple():
    """087:RF-44 — sin sorteos al aplicar, el atajo daba 100 % y no aplicaba nada; con la marca del plan no se toma."""
    import inspect

    fuente = inspect.getsource(cargar_herramienta('obras_pf.py', 'obras_rf44', tools_en_path=True).evaluar)
    assert "if not plan.get('aplicando_elegida') and cumple(sin_max, con_actual, barras, p)[0]:" in fuente
    assert "**({'aplicando_elegida': True} if solo and f in solo else {})" in inspect.getsource(services.obras_escalera)


def test_la_regla_de_la_maxima_solo_cerca_del_criterio():
    """087:RF-49 — con el 60 % de los sorteos (CHI201) no se elige; con el 94,5 % (SM218, 063:RF-33) sí, con aviso."""
    def fila(nombre, fraccion):
        return {'nombre': nombre, 'maxima': True, 'fraccion': fraccion, 'valle': True, 'motivos': [],
                'costo': {'costo_anual': 100.0, 'inversion': 1.0}, 'escalones': ('seccion',)}

    lejos = eo.elegir([fila('seccion', 0.6)], P)
    assert lejos['elegida'] is None and lejos['mas_cercana'] == 'seccion'
    cerca = eo.elegir([fila('seccion', 0.945)], P)
    assert cerca['elegida'] == 'seccion' and cerca['sin_confirmar_sorteos'] is True


def test_traslado_a_un_vecino_de_la_misma_tension(monkeypatch):
    """087:RF-33 — con el enlace llegando a la parte que pasa, la migración a la misma tensión solo abre su entrada; sin
    él, se rechaza como siempre (016:RF-65)."""
    from convertersmartgrid import obras_pf as op
    from convertersmartgrid.troncal import Barra, Tramo, red_de

    barras = ['C', 'A', 'B', 'D']
    topo = red_de([Barra(b) for b in barras], [Tramo('L1', 'C', 'A', 10), Tramo('L2', 'A', 'B', 10),
                                              Tramo('L3', 'C', 'D', 10)])
    red = op.RedAlimentador('CHI201', 22.9, {b: 22.9 for b in barras},
                            {n: op.Tramo(n, 'AAAC_70') for n in ('L1', 'L2', 'L3')}, topologia=topo, cabecera='C')
    obra = op.validar_obra({'clase': 'migracion', 'alimentador': 'CHI201', 'nodo': 'A', 'kv_destino': 22.9,
                            'casos': ['Con proyecto']})
    (con_enlace,) = op.plan_simulacion([obra], {'CHI201': red}, [], destinos_enlace={'CHI201': 'B'})
    assert not con_enlace['error'], con_enlace
    assert {e['clase'] for e in con_enlace['elementos']} == {'ElmLne'}
    assert any(e['elemento'] == 'L1' and 'se abre' in e['cambio'] for e in con_enlace['elementos'])
    (sin_enlace,) = op.plan_simulacion([obra], {'CHI201': red}, [])
    assert 'ya está' in sin_enlace['error'] and 'traslado' in sin_enlace['error']


def test_no_se_reutiliza_lo_medido_con_otro_codigo_ni_con_errores(tmp_path):
    """087:RF-50 — 025:RF-73 reutiliza una evaluación del mismo plan; no si dio error ni si el código que mide cambió."""
    import json

    class Ws:
        plans_dir, out_dir = tmp_path / 'planes', tmp_path / 'salida'

    Ws.plans_dir.mkdir(); Ws.out_dir.mkdir()
    plan = {'project': 'P', 'variantes': [{'nombre': 'v'}], 'revision_codigo': services.revision_de_la_escalera()}

    def guarda(nombre, plan_, informe):
        (Ws.plans_dir / nombre).write_text(json.dumps(plan_), encoding='utf-8')
        (Ws.out_dir / nombre).write_text(json.dumps(informe), encoding='utf-8')

    guarda('escalera_evaluar_a.json', plan, {'variantes': [{'nombre': 'v', 'error': 'ya está a 22.9 kV'}]})
    assert services._evaluacion_hecha(Ws(), plan) is None
    guarda('escalera_evaluar_b.json', {**plan, 'revision_codigo': 'otra'}, {'variantes': [{'nombre': 'v', 'maxima': True}]})
    assert services._evaluacion_hecha(Ws(), plan) is None
    guarda('escalera_evaluar_c.json', plan, {'variantes': [{'nombre': 'v', 'maxima': True}]})
    assert services._evaluacion_hecha(Ws(), plan)['variantes'][0]['maxima'] is True
    assert len(services.revision_de_la_escalera()) == 16


def test_tras_una_transferencia_cada_carga_cuenta_una_vez_y_la_red_se_relee(monkeypatch):
    """087:RF-51 — pérdidas de dos alimentadores con una carga en los dos; error no elegible; flujo tras borrar la variante."""
    import inspect

    guion = cargar_herramienta('obras_pf.py', 'obras_rf51', tools_en_path=True)

    class Carga:
        def __init__(self, nombre, p):
            self.nombre, self.p = nombre, p

        def GetFullName(self):
            return self.nombre

    class Cab:
        converge, kw = True, 1000.0

    class Alims:
        elm = {'F1': None, 'F2': None}

        def objetos(self, f, clase):
            return []

    comun = Carga('PARTE', 0.3)
    cargas = {'F1': [Carga('A', 0.4), comun], 'F2': [Carga('B', 0.2), comun]}
    monkeypatch.setattr(guion, '_cargas_de', lambda alims, f: cargas[f])
    monkeypatch.setattr(guion, 'leer_cabecera', lambda elm: Cab())
    monkeypatch.setattr(guion, '_resultado', lambda c, attr: c.p)
    monkeypatch.setattr(guion, 'flujo_de_carga', lambda app, **k: {'converged': True})
    monkeypatch.setattr(guion, 'cabecera_de', lambda elm: None)

    class App:
        def GetCalcRelevantObjects(self, _):
            return []

    alims = Alims()
    alims.elm = {'F1': object(), 'F2': object()}
    out = guion.medida_para_criterio(App(), alims, ['F1', 'F2'])
    assert out['perdidas_kw'] == pytest.approx(2000.0 - 1000 * (0.4 + 0.2 + 0.3))
    fila = {'nombre': 't', 'maxima': True, 'fraccion': None, 'valle': True, 'error': 'no tiene camino', 'motivos': [],
            'costo': {'costo_anual': 1.0, 'inversion': 1.0}, 'escalones': ('transferencia',)}
    assert eo.elegir([fila], P)['elegida'] is None
    assert 'TOPOLOGIA' in inspect.getsource(guion.evaluar) and 'migracion' in guion.TOPOLOGIA


def test_el_costo_y_el_area_del_expreso():
    """087:RF-36, 087:RF-38 — sin largo medido, la recta por el factor de las vías; celda por alimentador y área."""
    datos = {'alimentadores': {'F1': {'cabecera': 'CAB', 'barras': [{'nombre': 'CAB', 'gps': [-13.70, -76.20]},
                                                                   {'nombre': 'N', 'gps': [-13.71, -76.20]}]}}}
    ramas = [{'alimentador': 'F1', 'nodo': 'N', 'barras': ['N'], 'kw_existente': 100.0}]
    avisos: list[str] = []
    r = services._expreso_costo_y_area(PERFIL, None, ramas, datos, [{'sed': 'S', 'kw': 50.0, 'barra': 'N'}], [], 'EXP', avisos)
    assert r['costo']['celdas'] == 1 and r['costo']['km'] == pytest.approx(1.112 * oi.FACTOR_RUTA, rel=0.01)
    assert 'Osinergmin' in str(r['costo']['fuente_celda']) and r['area']['kw_presente'] == 150.0


def test_la_confirmacion_conjunta_mide_todo_el_sistema_sin_apartar_nada(monkeypatch):
    """087:RF-45 — todos los alimentadores, todas las cargas nuevas activas, sorteos y valle, en un solo plan de DIgSILENT."""
    prep = {'p': P, 'anio_casos': 2026, 'sorteos': [{'factores': {}}] * 3, 'perfil': PERFIL, 'valle': {'puntos': []}}
    monkeypatch.setattr(services, 'obras_escalera', lambda *a, **k: prep if k.get('solo_comun') else {})
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [
        {'sed': 'A', 'alimentador': 'F1', 'barra': 'S1', 'variacion': 'Carga_A'},
        {'sed': 'B', 'alimentador': 'F2', 'barra': 'S2', 'variacion': 'Carga_B'}])
    monkeypatch.setattr(services, 'carpeta_de', lambda *a: 'C')
    monkeypatch.setattr(services, 'native_action_context', lambda ws, project, feeders, accion: {'feeders': list(feeders)})
    planes = []

    def guion(ws, ctx, guion_py, plan, **k):
        planes.append((k['nombre'], plan))
        if k['nombre'] == 'conjunto_datos':
            return 0, {'alimentadores': {'F1': {'media': {'S1': 'M1'}}, 'F2': {'media': {'S2': 'M2'}}}}, None
        return 0, {'conjunto': {'cumple': True, 'fraccion': 1.0}}, None

    monkeypatch.setattr(services, '_guion_pf', guion)
    ctx = _Ctx()
    c = services.confirmar_conjunto(object(), ctx, 'P', ['F1', 'F2', 'F3'], memo={})
    plan = planes[-1][1]
    assert c['cumple'] and plan['solo_confirmar'] and plan['feeders'] == ['F1', 'F2', 'F3']
    assert plan['apartar_cargas_de'] == [] and plan['apartar_variaciones'] == [] and plan['barras_cargas'] == ['M1', 'M2']
    assert len(plan['sorteos']) == 3 and plan['native_action_context']['feeders'] == ['F1', 'F2', 'F3']
    assert any('087:RF-45' in t for t in ctx.textos)


def test_si_el_conjunto_no_cumple_se_rehace_solo_el_afectado_y_no_se_insiste(monkeypatch, tmp_path):
    """087:RF-46, 087:RF-47 — se rehace la obra del alimentador culpable, con las demás cargas activas, y como mucho dos veces."""
    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_seleccion_por_oraculo', lambda *a, **k: {})
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [
        {'sed': f'S{f}', 'alimentador': f, 'kw': 10.0, 'variacion': f'Carga_{f}'} for f in ('F1', 'F2')])
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: None)
    hechos = []
    monkeypatch.setattr(services, '_retirar_obras', lambda ws, ctx, project, feeders, anio: hechos.append(('retira', feeders[0])))

    def escalera(ws, ctx, project, feeders, *, aplicar=False, cargas_activas=None, **k):
        hechos.append(('aplica' if aplicar else 'evalua', feeders[0], cargas_activas is None))
        return {'alimentadores': [{'alimentador': feeders[0], 'elegida': f'obra de {feeders[0]}', 'aplicada': ['Obra']}]}

    monkeypatch.setattr(services, 'obras_escalera', escalera)
    monkeypatch.setattr(services, 'confirmar_conjunto',
                        lambda *a, **k: {'cumple': False, 'por_alimentador': {'F2': ['F2X pasa al 120 %'], 'VECINO': ['x']}})
    r = services.escalera_por_alimentador(object(), _Ctx(), 'P', ['F1', 'F2'])
    # 098:RF-36: la ronda no retira antes: aplica la nueva con la vieja apartada y la borra solo si la nueva queda.
    assert hechos.count(('aplica', 'F2', True)) == services.RONDAS_CONJUNTO
    assert not [h for h in hechos if h[0] == 'retira'] and ('aplica', 'F1', True) not in hechos
    assert not r['conjunto']['cumple']
    assert r['por_alimentador']['F2']['conjunto']['ronda'] == services.RONDAS_CONJUNTO


def test_el_guion_confirma_el_conjunto_y_reparte_los_motivos():
    """087:RF-45, 087:RF-46 — sin variantes: mide lo que hay, con sorteos y valle, y culpa a cada alimentador por sus nombres."""
    import inspect

    fuente = inspect.getsource(cargar_herramienta('obras_pf.py', 'obras_rf45', tools_en_path=True).evaluar)
    assert "if plan.get('solo_confirmar'):" in fuente and 'confirmar_conjunto(con_actual)' in fuente
    assert "fila['por_alimentador'] = por_alimentador" in fuente and 'por_etapas()' in fuente and 'medir_valle()' in fuente


def test_el_deficit_previo_pasa_por_el_oraculo(monkeypatch):
    """087:RF-48 — solo las buenas del oráculo, una tanda de cercanas y las que no calcula; el orden, el de la escalera."""
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, {'grafo': {'nodos': {}, 'ramas': []}}, None))
    tension = {'bancos': 0.93, 'regulador': 0.94, 'seccion': 0.96, 'terna': 0.97, 'bancos2': 0.92, 'bancos3': 0.91,
               'bancos4': 0.90}

    class Medida:
        def __init__(self, u):
            self.converge, self.u = True, {'BAJA': u}

    class Oraculo:
        def __init__(self, *a, **k):
            pass

        def medir(self, obras, k):
            return Medida(tension[obras[0]['clase']])

    monkeypatch.setattr(oo, 'Oraculo', Oraculo)
    monkeypatch.setattr(oo, 'MODELADAS', frozenset(tension))
    vs = [eo.Variante(n, (n,), [{'clase': n}], {}) for n in tension]
    vs.append(eo.Variante('paso a 22.9 kV', ('nivel',), [{'clase': 'migracion'}], {}))
    ctx = _Ctx()
    elegidas = services._previas_con_oraculo(object(), ctx, {}, 'F1', vs, ['BAJA'], [], P)
    assert [v.nombre for v in elegidas] == ['bancos', 'regulador', 'seccion', 'terna', 'bancos2', 'paso a 22.9 kV']
    assert any('087:RF-48' in t and 'mide 6 de 8' in t for t in ctx.textos)


def test_la_transferencia_sale_de_la_barra_mas_cercana_a_cada_vecino():
    """087:RF-52 — de varias barras de la troncal, la del enlace más corto con cada vecino."""
    camino = [{'nombre': f'T{i}', 'desde': f'B{i - 1}', 'hasta': f'B{i}', 'largo_m': 1000, 'u': {f'B{i}': 0.94},
               'corriente_a': 50, 'maniobra': SW} for i in range(1, 5)] + [
              {'nombre': 'R1', 'desde': 'B4', 'hasta': 'RAMA', 'largo_m': 500, 'u': {'RAMA': 0.93}, 'corriente_a': 20,
               'maniobra': SW}]
    troncal = {'T1', 'T2', 'T3', 'T4'}
    assert oi.candidatos_de_transferencia(camino, troncal, 0.95) == ['B1', 'B2', 'B3', 'B4']
    vecinos = {'B1': [_vecino('V', 3000)], 'B2': [_vecino('V', 190)], 'B3': [_vecino('V', 900), _vecino('W', 400)],
               'B4': [_vecino('W', 2500)], 'RAMA': [_vecino('V', 5000)]}
    vs, _av = oi.variantes('F1', 10.0, camino, troncal, 'RAMA', vecinos, TIPOS, P)
    transferencias = [(v.obras[1]['nodo'], v.obras[0]['alimentador']) for v in vs if v.escalones == ('transferencia',)]
    assert transferencias == [('B2', 'V'), ('B3', 'W')]
    assert [v.obras[1]['nodo'] for v in vs if v.escalones == ('traslado',)] == ['RAMA']


def test_solo_reciben_carga_los_vecinos_que_operan(monkeypatch):
    """087:RF-53 — un vecino sin demanda medida en su calibración (SC215 ya no opera) no se propone, y se dice."""
    camino = [{'nombre': 'T1', 'desde': 'CAB', 'hasta': 'B1', 'largo_m': 1000, 'u': {'B1': 0.94}, 'corriente_a': 50,
               'maniobra': SW},
              {'nombre': 'R1', 'desde': 'B1', 'hasta': 'RAMA', 'largo_m': 500, 'u': {'RAMA': 0.93}, 'corriente_a': 20,
               'maniobra': SW}]
    d = {'caminos': {'RAMA': camino}, 'troncal': [{'nombre': 'T1'}]}
    leidos = {'vecinos': {'F1': {'B1': [_vecino('SC215', 190), _vecino('PA108', 900)], 'RAMA': [_vecino('SC215', 300)]}}}
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, leidos, None))
    objetivos = {'PA108': {'kw': 2396.0}, 'SC215': {}, 'SI114': {'kw': 0}}
    vs, vecinos, avisos = services._variantes_de_traspaso(object(), _Ctx(), {}, 'F1', d, ['RAMA'], 10.0, TIPOS, P, objetivos)
    assert vecinos == ['PA108'] and all(o['alimentador'] != 'SC215' for v in vs for o in v.obras if o['clase'] == 'enlace')
    assert any('SC215' in a and '087:RF-53' in a for a in avisos)


def test_una_zona_pequena_sola_va_al_alimentador_nuevo(monkeypatch):
    """087:RF-54 — CHI201 sola con 0,66 MW: alimentador expreso, no SET nueva; y la orden directa, sin escalera."""
    import inspect

    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil',
                        lambda: {'planificacion': {'set_nueva_desde_kw': 10000, 'radio_zona_set_km': 10}})
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda ws, project: [
        {'sed': 'SALUD', 'alimentador': 'CHI201', 'kw': 660.0, 'variacion': 'Carga_SALUD', 'lat': -13.7, 'lon': -75.9}])
    monkeypatch.setattr(services, 'optimizar_con_proyecto', lambda *a, **k: (_ for _ in ()).throw(AssertionError('escalera')))
    monkeypatch.setattr(services, 'escalera_por_alimentador', lambda *a, **k: (_ for _ in ()).throw(AssertionError('escalera')))
    vistos = {}

    def set_nueva(ws, ctx, project, feeders, zona, **k):
        vistos['expreso'] = k.get('expreso')
        return {'avisos': []}

    monkeypatch.setattr(services, 'set_nueva_proponer', set_nueva)
    monkeypatch.setattr(services, '_registrar_corrida', lambda *a, **k: None)
    monkeypatch.setattr(services, '_reponer_cargas_nuevas', lambda *a, **k: vistos.setdefault('repone', a[-1]))
    r = services.con_proyecto_optimizar(None, _Ctx(), 'P', ['CHI201'], directo_set_nueva=True)
    assert vistos['repone'] == ['Carga_SALUD']                                   # antes de la zona
    assert vistos['expreso'] is True and r['set_nueva']['solucion'] == 'expreso'
    guion = cargar_herramienta('sistema_web.py', 'sistema_rf54', tools_en_path=True)
    assert "'directo_set_nueva': True} if obra_integral" in inspect.getsource(guion.con_proyecto)
