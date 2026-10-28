"""Spec 021, RF-54 a RF-60: el ajuste de los alimentadores de un proyecto a la vez, en
``fake_pf``.

DIgSILENT no se ejecuta en la suite (P11). El usuario, el 2026-10-17, al ir a aplicar NA203
y después NA205: «la calibración se debe hacer por proyecto en DIgSILENT; si es un
alimentador se hace de ese y dos o más se hacen de todas según el proyecto, no de forma
independiente».
"""
from __future__ import annotations

import copy

import pytest
from apoyo import cargar_herramienta, contexto_nativo
from test_ajuste_cabecera_guion import _app, _carga, _plan
from test_ajuste_central_guion import _plan as _plan_central


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_proyecto_guion',
                              tools_en_path=True)


def _de(plan, feeder, kw):
    p = copy.deepcopy(plan)
    p['feeder'] = feeder
    p['objetivo'].update(kw=kw, medidor=f'M_{feeder}', alimentador=feeder)
    p['native_action_context'] = contexto_nativo('P', [feeder], 'ajuste')
    return p


def test_dos_alimentadores_en_los_mismos_flujos(guion):
    """021:RF-54, 021:RF-55, 021:RF-59 — una sola calibración: los dos cuadran en el mismo
    flujo final, con un factor cada uno, y cada informe dice con quién se calibró."""
    app = _app(escenario=True)
    (f1, rc1), (f2, rc2) = guion.ejecutar_proyecto(
        app, [_de(_plan(), 'F1', 300.0), _de(_plan(), 'F2', 220.0)])
    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['cuadrado'] and f2['cuadrado']
    assert f1['calibrado_con'] == ['F2'] and f2['calibrado_con'] == ['F1']
    assert abs(f1['desvio']['kw']) <= 0.01 and abs(f2['desvio']['kw']) <= 0.01
    assert f1['cabecera']['kw'] == pytest.approx(300.0, rel=0.01)
    assert f2['cabecera']['kw'] == pytest.approx(220.0, rel=0.01)
    assert f1['flujos'] == f2['flujos'] and f1['historial'] is f2['historial']
    assert set(f1['historial'][0]['a']) == {'F1', 'F2'}
    assert f1['validacion_posterior_nativa']['status'] == 'VALIDO'
    assert f2['resultado_carga_nativa']['status'] == 'APLICADO_Y_VALIDADO'
    assert f1['escenario'] == 'Sin proyecto' and f1['escenarios'][0]['escenario'] == 'Sin proyecto'
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == []


def test_un_plan_es_el_ajuste_de_siempre(guion):
    """021:RF-60 — con un alimentador, el ajuste de siempre, sin calibración conjunta."""
    a, b = _app(escenario=True), _app(escenario=True)
    [(solo, rc)] = guion.ejecutar_proyecto(a, [_plan()])
    igual, rc_igual = guion.ejecutar(b, _plan())
    assert rc == rc_igual == 0
    assert 'calibrado_con' not in solo
    assert solo['cabecera'] == igual['cabecera'] and solo['flujos'] == igual['flujos']


def test_con_central_y_sin_ella_a_la_vez(guion):
    """021:RF-54, 021:RF-55 — F1 con central cuadra sus dos zonas y F2 su cabecera, todo en
    los mismos flujos; la central queda creada en «Sin proyecto»."""
    app = _app(escenario=True)
    central = _plan_central()
    resultados = guion.ejecutar_proyecto(app, [central, _de(_plan(), 'F2', 220.0)])
    (f1, rc1), (f2, rc2) = resultados
    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['criterio_cuadre'] == 'ZONAS_DE_LA_CENTRAL' and f1['central']['creado']
    z = f1['zonas']
    assert z['arriba_kw'] == pytest.approx(150.0, rel=0.01)
    assert z['abajo_kw'] == pytest.approx(900.0, rel=0.01)
    assert f2['cabecera']['kw'] == pytest.approx(220.0, rel=0.01)
    assert set(f1['historial'][0]['a']) == {'F1|arriba', 'F1|abajo', 'F2'}


def test_el_que_no_se_prepara_queda_fuera(guion):
    """021:RF-57 — un alimentador sin cabecera en el proyecto se dice en su informe y los
    demás se calibran juntos."""
    app = _app(escenario=True)
    (f9, rc9), (f1, rc1) = guion.ejecutar_proyecto(
        app, [_de(_plan(), 'F9', 100.0), _de(_plan(), 'F1', 300.0)])
    assert rc9 == 2 and 'ElmFeeder' in f9['error']
    assert rc1 == 0 and f1['cuadrado']
    assert any('F9' in a and '021:RF-57' in a for a in f1['avisos'])


def test_cancelar_deja_el_ultimo_reparto_comun(guion):
    """021:RF-58 — cancelar termina el flujo en curso y los dos quedan cancelados con el
    último reparto común que convergió."""
    app = _app(escenario=True)
    flujos = []
    antes = app.ldf.Execute

    def contar():
        flujos.append(1)
        return antes()

    app.ldf.Execute = contar
    (f1, _), (f2, _) = guion.ejecutar_proyecto(
        app, [_de(_plan(), 'F1', 300.0), _de(_plan(kw=600.0), 'F2', 600.0)],
        cancelado=lambda: len(flujos) >= 1)
    assert f1['cancelado'] and f2['cancelado'] and not f1['cuadrado']
    assert _carga(app, 'F2_S1').plini > 0


def test_proyectos_distintos_no_se_mezclan(guion):
    """021:RF-54 — se calibra un proyecto cada vez."""
    otro = _de(_plan(), 'F2', 200.0)
    otro['project'] = 'Q'
    res = guion.ejecutar_proyecto(_app(escenario=True), [_plan(), otro])
    assert all(rc == 2 and 'un mismo proyecto' in i['error'] for i, rc in res)


def test_aviso_fisico_con_el_historial_del_proyecto(guion):
    """021:RF-55 — el historial del proyecto lleva un factor por alimentador; el aviso de
    015:RF-51 toma el de su alimentador (NA203 + NA205, 2026-10-17: ``TypeError``)."""
    historial = [{'a': {'F1': 0.8, 'F2': 0.5}, 'converge': False},
                 {'a': {'F1': 0.4, 'F2': 0.7}, 'converge': False},
                 {'a': {'F1': 0.6, 'F2': 0.6}, 'converge': True}]
    assert guion._factor_minimo_sin_converger(historial, 'F1') == 0.4
    assert guion._factor_minimo_sin_converger(historial, 'F2') == 0.5
    assert guion._factor_minimo_sin_converger([{'a': 0.3, 'converge': False}]) == 0.3


def test_consigna_de_la_fuente_en_los_dos_casos(guion):
    """021:RF-61, 021:RF-62, 022:RF-24 — la tensión en la fuente va a cada red externa (una por
    barra de SET en la red unida) en «Sin
    proyecto» y «Con proyecto», se guarda su escenario, vuelve el primero activo y sale en
    la tabla de cambios con la original y la nueva; si ya la tiene, no es un cambio."""
    from types import SimpleNamespace

    class Caso(SimpleNamespace):
        def Activate(self):
            app.activo = self

    class Esc:
        guardado = 0

        def Save(self):
            self.guardado += 1

    xnet = {'sin': SimpleNamespace(loc_name='Red_SET', usetp=1.0),
            'con': SimpleNamespace(loc_name='Red_SET', usetp=1.0)}
    esc = {'sin': Esc(), 'con': Esc()}
    sin, con = Caso(rol='sin'), Caso(rol='con')
    app = SimpleNamespace(activo=None)
    app.GetCalcRelevantObjects = lambda _f: [xnet[app.activo.rol]]
    app.GetActiveScenario = lambda: esc[app.activo.rol]
    cambios = guion.fijar_consigna_de_la_fuente(app, 1.05, [sin, con])
    assert xnet['sin'].usetp == xnet['con'].usetp == 1.05
    assert esc['sin'].guardado == esc['con'].guardado == 1 and app.activo is sin
    assert cambios == [{'fuente': 'Red_SET', 'barra': None, 'antes': 1.0, 'despues': 1.05}]
    [fila] = guion.cambios_en_la_red({'consigna_fuente': cambios})
    assert fila['clase'] == 'fuente' and fila['original']['potencia'] == 1.0
    assert fila['nuevo']['potencia'] == 1.05 and fila['nuevo']['unidad'] == 'pu'
    assert guion.fijar_consigna_de_la_fuente(app, 1.05, [sin, None]) == []


def test_pone_los_bancos_que_faltan_y_recalibra(guion, monkeypatch):
    """021:RF-64, 021:RF-65, 021:RF-66, 021:RF-67, 021:RF-68, 021:RF-69 — tras una primera pasada sin guardar, los bancos del tamaño del
    perfil en la troncal, en servicio en «Sin proyecto» y «Con proyecto» y fuera en el
    «Caso base»; se recalibra y salen en la tabla de cambios."""
    app = _app(escenario=True)
    plan = {**_de(_plan(kvar=10.0), 'F1', 300.0), 'completar_bancos': True,
            'bancos_kvar_por_tension': {'10': 2.0}}            # la red da 13,6 de 10 kVAR
    pasadas = []
    original = guion._ejecutar_proyecto

    def contar(*a, **kw):
        pasadas.append(kw.get('solo_medir', False))
        return original(*a, **kw)

    monkeypatch.setattr(guion, '_ejecutar_proyecto', contar)
    [(inf, rc)] = guion.ejecutar_proyecto(app, [plan])
    assert pasadas == [True, False]
    assert inf['bancos_nuevos'], inf['avisos']
    nombres = {b['banco'] for b in inf['bancos_nuevos']}
    assert len(nombres) == 2 and all(b['kvar'] == 2.0 and b['feeder'] == 'F1' for b in inf['bancos_nuevos'])
    # El doble no separa el ``outserv`` por escenario: se mira qué se escribió en cada uno.
    escrito = {}
    for o, attr, valor, etapa, escenario in app.escrituras:
        if attr == 'outserv' and getattr(o, 'loc_name', '') in nombres and escenario is not None:
            assert etapa is None, 'en la red, sin variación'
            escrito.setdefault(escenario.loc_name, set()).add(valor)
    assert escrito['Operador'] == {1}, 'fuera de servicio en el escenario del «Caso base»'
    assert escrito['Sin proyecto'] == {0}
    assert all(o.etapa_creacion is None for o in app.creados if o.loc_name in nombres)
    filas = [c for c in inf['cambios_en_la_red'] if c['elemento'] in nombres]
    assert filas and all(c['original']['potencia'] == 0.0 and c['nuevo']['potencia'] == 2.0
                         for c in filas)
    assert any('021:RF-64' in a for a in inf['avisos'])


def test_una_segunda_calibracion_no_repite_los_bancos(guion):
    """028:RF-14 — con los bancos de la calibración ya puestos, la siguiente no pone más y lo
    dice (Nasca, 2026-10-28: 8 bancos acumulados en NA205)."""
    app = _app(escenario=True)
    plan = {**_de(_plan(kvar=10.0), 'F1', 300.0), 'completar_bancos': True,
            'bancos_kvar_por_tension': {'10': 2.0}}
    [(primera, _rc)] = guion.ejecutar_proyecto(app, [plan])
    assert primera['bancos_nuevos']
    [(segunda, _rc)] = guion.ejecutar_proyecto(app, [plan])
    assert segunda['bancos_nuevos'] == []
    assert any('028:RF-14' in a for a in segunda['avisos']), segunda['avisos']


def test_barras_de_los_bancos_en_la_troncal(guion):
    """021:RF-66 — las barras de la troncal más cercanas a 2k/(2n+1) de su largo, sin
    repetir."""
    from igea_dgs.troncal import Barra, Red, Tramo

    barras = {f'B{i}': Barra(f'B{i}') for i in range(7)}
    tramos = [Tramo(f'L{i}', f'B{i}', f'B{i + 1}', 1000.0) for i in range(6)]
    red = Red(barras, tramos)
    assert guion.barras_para_bancos(red, 'B0', 1) == ['B4']
    assert guion.barras_para_bancos(red, 'B0', 2) == ['B2', 'B5']


def test_con_central_tambien_avisa_la_fija_sobre_su_transformador(guion):
    """020:RF-1, 015:RF-59 — un alimentador con central también avisa de la fija que pide más
    que su transformador, con su propuesta: en NA205 (2026-10-17) SE50293 pedía 1 392 kW en
    125 kVA, el flujo no convergía y no se decía."""
    from test_ajuste_cabecera_guion import _fichas_plan, _sobrecargada

    app = _app(escenario=True)
    plan = {**_plan_central(clientes=_sobrecargada(app)), 'transformadores_sed': _fichas_plan()}
    informe, _rc = guion.ejecutar(app, plan, simular=True)
    [x] = informe['fijas_sobre_su_transformador']
    assert x['sed'] == 'F1_S2' and x['carga_pct'] > 100 and x['propuesta']['kva']


def test_cabecera_en_el_interruptor_de_una_barra_de_set(guion):
    """022:RF-22, 022:RF-23 — con el ElmFeeder en el interruptor de cabecera (barra de SET
    compartida con una sola red externa), se mide ese interruptor y no la red externa, que
    sumaría todos los alimentadores de la barra."""
    from types import SimpleNamespace

    class O(SimpleNamespace):
        def GetClassName(self):
            return self.clase

        def GetParent(self):
            return self.padre

        def GetContents(self, _f):
            return self.hijos

    barra = O(clase='ElmTerm', loc_name='B_SET51_22p9kV', hijos=[])
    cab_a = O(clase='ElmCoup', loc_name='CAB_NA203', outserv=0,
              **{'m:Psum:bus1': 9.19, 'm:Qsum:bus1': 1.75})
    cab_b = O(clase='ElmCoup', loc_name='CAB_NA205', outserv=0,
              **{'m:Psum:bus1': -1.57, 'm:Qsum:bus1': 3.1})
    xnet = O(clase='ElmXnet', loc_name='External Grid SET 51', outserv=0,
             **{'m:Psum:bus1': -7.62, 'm:Qsum:bus1': -4.85})
    cubs = [O(clase='StaCubic', loc_name=f'Cub1_{o.loc_name}', obj_id=o, obj_bus=0, padre=barra)
            for o in (cab_a, cab_b, xnet)]
    barra.hijos = cubs
    elm = O(clase='ElmFeeder', obj_id=cubs[0], iorient=0)
    m = guion.leer_cabecera(elm)
    assert m.converge and m.kw == pytest.approx(9190.0) and m.kvar == pytest.approx(1750.0)
    assert guion.detalle_cabecera(elm)['metodo'] == 'INTERRUPTOR_DE_CABECERA'


def test_barra_de_set_central_y_medidor(guion):
    """022:RF-41b, 022:RF-44 — con la máxima de la barra: la central de la barra en su barra
    de SET con su P y Q de ese registro, y el informe compara lo que dan las cabeceras de la
    barra (menos la central) con el medidor de barra."""
    app = _app(escenario=True)
    barra_pf = next(o for o in app.proyecto.GetContents('*.ElmTerm', 1) if o.loc_name == 'F1_B0')
    object.__setattr__(barra_pf, 'loc_name', 'B_SET1_10kV')
    barra = {'clave': 'SET 1 10 kV', 'set': 'SET 1', 'kv': 10.0, 'suelta': False, 'kw': 480.0,
             'kvar': 100.0, 'fecha': '2026-07-23 10:00:00', 'alimentadores': ['F1', 'F2'],
             'centrales': [{'medidor': 'CT_X', 'kw': 1.0, 'kvar': 0.0}]}
    # En el doble la «barra de SET» es la cabecera de F1, aguas abajo de su medida: la
    # central se queda pequeña para no tapar sus pérdidas (en la red va aguas arriba).
    planes = [{**_de(_plan(), 'F1', 300.0), 'barra_set': barra},
              {**_de(_plan(), 'F2', 220.0), 'barra_set': barra}]
    (f1, rc1), (f2, rc2) = guion.ejecutar_proyecto(app, planes)
    assert (rc1, rc2) == (0, 0), (f1, f2)
    [c] = f1['centrales_de_barra']
    assert c['medidor'] == 'CT_X' and c['creado']
    gen = next(o for o in app.creados if o._clase == 'ElmGenstat')
    assert gen.bus1.cterm.loc_name == 'B_SET1_10kV' and gen.pgini == pytest.approx(0.001)
    b = f1['barra_set']
    assert b['calibrados'] == ['F1', 'F2'] and b['central_kw'] == 1.0
    assert b['cabeceras_kw'] == pytest.approx(f1['cabecera']['kw'] + f2['cabecera']['kw'])
    assert b['desvio'] == pytest.approx((b['cabeceras_kw'] - 1.0 - 480.0) / 480.0)
    assert any('022:RF-41b' in a for a in f2['avisos'])


def test_sin_cuadrar_en_kw_no_se_ponen_bancos(guion):
    """021:RF-64 — los bancos que faltan solo se calculan con el alimentador en su objetivo
    de kW tras la primera pasada (NA205 del TXT, 2026-10-18: sin cuadrar puso 10)."""
    plan = {'tolerancia': 0.01}
    assert guion._cuadro_en_kw({'desvio': {'kw': 0.004}}, plan)
    assert not guion._cuadro_en_kw({'desvio': {'kw': 0.2}}, plan)
    assert not guion._cuadro_en_kw({'desvio': None}, plan)
    central = {**plan, 'central': {'nodo': '1720'}}
    assert guion._cuadro_en_kw({'zonas': {'arriba_kw': 100.0, 'arriba_objetivo_kw': 100.5,
                                          'abajo_kw': 500.0, 'abajo_objetivo_kw': 501.0}}, central)
    assert not guion._cuadro_en_kw({'zonas': {'arriba_kw': 100.0, 'arriba_objetivo_kw': 100.5,
                                              'abajo_kw': 300.0, 'abajo_objetivo_kw': 7177.9}}, central)


@pytest.mark.parametrize('con_q', [True, False])
def test_con_remedios_los_bancos_salen_de_la_q_escrita(guion, monkeypatch, con_q):
    """021:RF-70 — si la primera pasada necesitó remedios del flujo, el kVAR de la red no
    vale (Chincha, 2026-10-18: 36 bancos sin converger): los bancos salen de la Q escrita de
    las cargas frente a la medida (CA101: 13 kVAR medidos y ningún banco en la base); sin Q
    escrita, no se calculan y se dice."""
    app = _app(escenario=True)
    plan = {**_de(_plan(kvar=10.0), 'F1', 300.0), 'completar_bancos': True,
            'bancos_kvar_por_tension': {'10': 2.0}}
    original = guion._ejecutar_proyecto

    def con_remedios(*a, **kw):
        res = original(*a, **kw)
        if kw.get('solo_medir'):
            for inf, _rc in res:
                inf['remedios'] = [{'remedio': 'adaptación automática del modelo'}]
                inf['sed'] = ([{'sed': 'S1', 'despues': {'kw': 200.0, 'kvar': 14.0}},
                               {'sed': 'S2', 'despues': {'kw': 100.0, 'kvar': 0.5}}]
                              if con_q else [])
        return res

    pedidos = []
    monkeypatch.setattr(guion, '_ejecutar_proyecto', con_remedios)
    monkeypatch.setattr(guion, 'poner_bancos', lambda *a: pedidos.append(a[-1]) or [])
    [(inf, _rc)] = guion.ejecutar_proyecto(app, [plan])
    if con_q:
        assert pedidos == [{'F1': (2, 2.0)}], '14,5 escritos frente a 10 medidos: dos de 2'
        assert any('Q escrita' in a and '021:RF-70' in a for a in inf['avisos'])
    else:
        assert not pedidos and not inf['bancos_nuevos']
        assert any('021:RF-70' in a for a in inf['avisos'])


def test_fichas_de_todo_el_proyecto_en_una_variacion(guion):
    """032:RF-8, 032:RF-13, 032:RF-14 — calibrando el proyecto, los conductores de todos sus
    alimentadores con su ficha, en una sola variación ``Fichas_<proyecto>``, y el mismo informe
    en cada alimentador; un código sin ficha, «sin ficha». La calibración sigue cuadrando."""
    app = _app(escenario=True)
    fichas = {'AAAC_F1': {'valores': {'r1_ohm_km': 0.9}, 'fuente': 'f'}}
    planes = [{**_de(_plan(), f, kw), 'fichas_conductores': fichas}
              for f, kw in (('F1', 300.0), ('F2', 220.0))]
    (f1, rc1), (f2, rc2) = guion.ejecutar_proyecto(app, planes)

    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['cuadrado'] and f2['cuadrado']
    assert [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')] == ['Fichas_P']
    assert f1['conductores_ficha'] is f2['conductores_ficha']
    assert f1['conductores_ficha']['sin_ficha'] == ['AAAC_F2']
    assert {c['codigo'] for c in f1['conductores_ficha']['cambios']} == {'AAAC_F1'}


def test_bancos_que_faltan_con_la_variacion_de_las_fichas(guion):
    """032:RF-8 — CA101 desde cero (2026-10-28): con ``Fichas_<proyecto>`` activa, poner los
    bancos que faltan se negaba (««Sin proyecto» tiene variaciones activas») y fallaba la
    calibración entera. Ahora se aparta como la de una central: los bancos van a la red, no a
    la etapa de las fichas, y la variación sigue activa en «Sin proyecto»."""
    app = _app(escenario=True)
    plan = {**_de(_plan(kvar=10.0), 'F1', 300.0), 'completar_bancos': True,
            'bancos_kvar_por_tension': {'10': 2.0},
            'fichas_conductores': {'AAAC_F1': {'valores': {'r1_ohm_km': 0.9}, 'fuente': 'f'}}}

    [(inf, rc)] = guion.ejecutar_proyecto(app, [plan])

    assert inf['bancos_nuevos'], (inf.get('error'), inf['avisos'])
    nombres = {b['banco'] for b in inf['bancos_nuevos']}
    assert all(o.etapa_creacion is None for o in app.creados if o.loc_name in nombres)
    assert inf['conductores_ficha']['variacion'] == 'Fichas_P'
    sin = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Sin proyecto')
    sin.Activate()
    assert 'Fichas_P' in {v.loc_name for v in app.GetActiveNetworkVariations()}
