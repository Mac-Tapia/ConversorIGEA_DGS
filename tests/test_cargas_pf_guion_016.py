"""Spec 016, T10: las cargas nuevas se conectan en el punto más cercano de la troncal."""

from __future__ import annotations

import pytest

from apoyo import cargar_herramienta
from test_cargas_pf_guion import _nueva, _plan
from test_cargas_pf_guion_007 import _app, _barra

LAT, LON0 = -14.0, -75.7                     # F1 en el doble: barras F1_Bi en LON0 + 0,001·i


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_guion_016', tools_en_path=True)


def _lineas(app, f='F1'):
    elm = next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == f)
    return {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}


def _centro_de_l2(dlat=0.0005):
    """Frente al centro de F1_L2 (de F1_B1 a F1_B2), a unos 55 m."""
    return {'lat': LAT + dlat, 'lon': LON0 + 0.0015}


def _ver(app, variacion):
    """Activa la variación de la carga para mirar lo que creó."""
    v = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme') if v.loc_name == variacion)
    v.Activate()
    return v


def test_la_carga_parte_el_tramo_de_la_troncal_en_su_variacion(guion):
    """016:RF-45, 016:RF-46 — una carga frente al centro de un tramo de la troncal lo parte
    con una barra nueva, dentro de su variación, y se engancha allí con su línea; sin la
    variación el tramo vuelve a estar entero."""
    app = _app(alimentadores=('F1',))
    plan = _plan(['F1'], nuevas=[_nueva('N1', alimentador='F1', **_centro_de_l2())])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0 and not informe['no_creadas'], informe
    (creada,) = informe['feeders'][0]['creadas']
    assert creada['tramo_partido'] == {'tramo': 'F1_L2', 'fraccion': pytest.approx(0.5, abs=1e-3)}
    assert creada['barra'] == 'NODE_T_N1' and creada['criterio'] == 'punto de la troncal más cercano'
    assert creada['distancia_m'] == pytest.approx(55.3, abs=0.5)
    assert creada['tipo_linea'] == 'AAAC_F1' and creada['origen_tipo_linea'] == 'del tramo que se parte'
    v = _ver(app, creada['variacion'])
    lineas = _lineas(app)
    assert lineas['F1_L2'].dline == pytest.approx(0.5) and 'F1_L2(1)' in lineas
    assert (_barra(app, 'NODE_T_N1').GPSlat, _barra(app, 'NODE_T_N1').GPSlon) == pytest.approx(
        (LAT, LON0 + 0.0015))
    v.Deactivate()
    assert _lineas(app)['F1_L2'].dline == pytest.approx(1.0) and 'F1_L2(1)' not in _lineas(app)


@pytest.mark.parametrize('minima, parte', [(None, True), (2.0, True), (5.0, False)])
def test_distancia_minima_a_una_barra(guion, minima, parte):
    """016:RF-20, 016:RF-67, 016:RF-73 — a unos 3,3 m de F1_B1 sobre la troncal: con distancia
    mínima de 5 m se engancha en la barra; con 2 m o sin ella, parte el tramo."""
    app = _app(alimentadores=('F1',))
    fila = _nueva('N1', alimentador='F1', lat=LAT + 0.0003, lon=LON0 + 0.001 + 0.00003)
    plan = {**_plan(['F1'], nuevas=[fila]), 'minima_m': minima}
    informe, rc = guion.ejecutar(app, plan, simular=True)
    assert rc == 0, informe
    (r,) = informe['feeders'][0]['crearian']
    assert r['parte'] is parte
    assert (r['tramo'] == 'F1_L2') if parte else (r['barra'] == 'F1_B1' and r['tramo'] is None)


def test_en_la_derivacion_mas_cercana_a_sus_coordenadas(guion):
    """016:RF-78 — la carga se conecta en el tramo de media más cercano a sus coordenadas,
    también en una derivación, no solo en la troncal (cambia RF-45)."""
    app = _app(alimentadores=('F1',))
    b1 = _barra(app, 'F1_B1')
    red = b1.GetParent()
    bd = red.CreateObject('ElmTerm', 'F1_BD')
    bd.uknom, bd.GPSlat, bd.GPSlon = 10.0, LAT + 0.004, LON0 + 0.0015
    ld = red.CreateObject('ElmLne', 'F1_LD')
    ld.typ_id, ld.nlnum, ld.outserv, ld.dline = _lineas(app)['F1_L1'].typ_id, 1, 0, 0.5
    ld.GPScoords = [[b1.GPSlat, b1.GPSlon], [bd.GPSlat, bd.GPSlon]]
    for lado, b in ((0, b1), (1, bd)):
        cub = b.CreateObject('StaCubic', f'c{lado}_F1_LD')
        cub.obj_id, cub.obj_bus = ld, lado
    elm = next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == 'F1')
    elm._objs.extend([bd, ld])
    app.creados.clear()
    fila = _nueva('N1', alimentador='F1', lat=LAT + 0.0035, lon=LON0 + 0.0015)
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[fila]), simular=True)
    (r,) = informe['feeders'][0]['crearian']
    assert rc == 0 and r['tramo'] == 'F1_LD'


def test_la_barra_indicada_no_parte_nada(guion):
    """016:RF-48 — con barra en la fila, se conecta a ella, sin partir ningún tramo."""
    app = _app(alimentadores=('F1',))
    fila = _nueva('N1', alimentador='F1', barra='F1_B3', **_centro_de_l2())
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[fila]), simular=True)
    (r,) = informe['feeders'][0]['crearian']
    assert rc == 0 and r['barra'] == 'F1_B3' and not r['parte'] and r['tramo'] is None


def test_la_simulacion_dice_tramo_parte_y_distancia(guion):
    """016:RF-49 — la simulación dice el tramo elegido, si se parte y la distancia en metros
    del punto del libro al punto de conexión, sin crear nada."""
    app = _app(alimentadores=('F1',))
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', alimentador='F1',
                                                                    **_centro_de_l2())]), simular=True)
    (r,) = informe['feeders'][0]['crearian']
    assert rc == 0 and r['tramo'] == 'F1_L2' and r['parte'] and r['fraccion'] == pytest.approx(0.5, abs=1e-3)
    assert r['distancia_m'] == pytest.approx(55.3, abs=0.5)
    assert app.creados == []


def test_troncal_sin_coordenadas(guion):
    """016:RF-50 — si ningún tramo de la troncal tiene coordenadas, no se conecta ninguna
    carga por coordenadas y se dice una vez, con el alimentador."""
    app = _app(alimentadores=('F1',))
    for b in app.proyecto.GetContents('*.ElmTerm', 1):
        b.GPSlat, b.GPSlon = 0.0, 0.0
    for ln in _lineas(app).values():
        ln.GPScoords = []
    app.creados.clear()
    nuevas = [_nueva(f'N{i}', alimentador='F1', **_centro_de_l2()) for i in range(3)]
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=True)
    assert len(informe['no_creadas']) == 3
    assert sum('016:RF-50' in a and 'F1' in a for a in informe['avisos']) == 1


def test_dos_cargas_en_el_mismo_tramo(guion):
    """016:RF-47, 016:RF-77 — dos cargas en el mismo tramo: la primera lo parte y la segunda se
    conecta en su nodo, con su propia línea, sin partir otra vez, y se dice."""
    app = _app(alimentadores=('F1',))
    nuevas = [_nueva('N1', alimentador='F1', lat=LAT + 0.0005, lon=LON0 + 0.0013),
              _nueva('N2', alimentador='F1', lat=LAT + 0.0005, lon=LON0 + 0.0017)]
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=False)
    assert rc == 0, informe
    creadas = informe['feeders'][0]['creadas']
    assert creadas[0]['tramo_partido']['tramo'] == 'F1_L2'
    assert creadas[0]['tramo_partido']['fraccion'] == pytest.approx(0.3, abs=1e-3)
    assert creadas[1]['tramo_partido'] is None and creadas[1]['barra'] == creadas[0]['barra']
    assert any('N1, N2' in a and 'F1_L2' in a for a in informe['avisos'])
    assert creadas[0]['nota'] is None and 'Carga_N1_F1' in creadas[1]['nota']


def test_el_plan_lleva_la_distancia_minima():
    """016:RF-73 — el plan de cargas lleva la distancia mínima que da el operador; una
    negativa se rechaza."""
    from igea_dgs.cargas_pf import LoadTemplateError, armar_plan, leer_hoja_nuevas

    filas, _ = leer_hoja_nuevas(['SED', 'Kw', 'barra'], [['N1', 50, 'B1']], 'A', avisos=[])
    nuevas = type('L', (), {'filas': filas, 'errores': [], 'avisos': []})()
    assert armar_plan(project='P', feeders=['A'], demandas=None, nuevas=nuevas)['minima_m'] is None
    assert armar_plan(project='P', feeders=['A'], demandas=None, nuevas=nuevas,
                      minima_m=5.0)['minima_m'] == 5.0
    with pytest.raises(LoadTemplateError, match='distancia mínima'):
        armar_plan(project='P', feeders=['A'], demandas=None, nuevas=nuevas, minima_m=-1)


def test_las_cargas_se_miden_con_el_escenario_encendido(guion, monkeypatch):
    """016:RF-79 — las cargas se escriben con el escenario apagado, pero cada medida (la
    referencia, la de cada carga y el flujo final) se hace con el escenario del caso
    encendido, que guarda las demandas calibradas; al terminar vuelve a estar activo."""
    import fake_pf

    app = fake_pf.proyecto(escenario=True)
    medidas, flujos = [], []
    medir, fluir = guion.medir_estado, guion.flujo_de_carga

    def medir_con_registro(*a, **k):
        medidas.append(getattr(app.GetActiveScenario(), 'loc_name', None))
        return medir(*a, **k)

    def fluir_con_registro(*a, **k):
        flujos.append(getattr(app.GetActiveScenario(), 'loc_name', None))
        return fluir(*a, **k)

    monkeypatch.setattr(guion, 'medir_estado', medir_con_registro)
    monkeypatch.setattr(guion, 'flujo_de_carga', fluir_con_registro)
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B2')]),
                                 simular=False)
    assert rc == 0, informe
    assert len(medidas) == 2 and medidas == ['Con proyecto', 'Con proyecto']
    assert flujos and flujos[-1] == 'Con proyecto'
    assert app.GetActiveScenario() is not None
