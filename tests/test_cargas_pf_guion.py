"""Spec 004: ``tools/cargas_pf.py`` contra un DIgSILENT simulado (``fake_pf``).

DIgSILENT no se puede ejecutar en la suite (P11): estas pruebas comprueban la lógica del
guion —qué coincide, dónde se conecta, qué se escribe y en qué etapa— con objetos que
imitan la API. La prueba real la hace el usuario.
"""
from __future__ import annotations

import json
import math
import random
import os

import pytest

import fake_pf
from apoyo import cargar_herramienta

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_guion', tools_en_path=True)


def _demanda(sed, kw, kvar, hoja=''):
    return {'sed': sed, 'hoja': hoja, 'kw': kw, 'kvar': kvar, 'fp': 0.0,
            'plini_mw': kw / 1000.0, 'qlini_mvar': kvar / 1000.0}


def _nueva(sed, **extra):
    fila = {'sed': sed, 'hoja': '', 'alimentador': '', 'barra': '', 'lat': None, 'lon': None,
            'kva_instalado': 160.0, 'kw': 80.0, 'kvar': 30.0, 'fp': 0.0, 'tipo_linea': '',
            'tension_bt_kv': None}
    fila.update(extra)
    fila.update(plini_mw=fila['kw'] / 1000.0, qlini_mvar=fila['kvar'] / 1000.0)
    return fila


def _plan(feeders, demandas=(), nuevas=(), variacion='Cargas_20261008_120000'):
    return {'project': 'P', 'feeders': list(feeders), 'stamp': '20261008_120000',
            'variacion': variacion, 'demandas': list(demandas), 'nuevas': list(nuevas)}


def _carga(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == nombre)


# =========================================================================== variación
def _ver_cargas(app):
    """Activa las variaciones de las cargas nuevas para inspeccionar lo que crearon: el
    guion las deja desactivadas al terminar (007:RF-17)."""
    for v in app.carpetas['scheme'].GetContents('*.IntScheme'):
        if v.loc_name.startswith('Carga_'):
            v.Activate()


def test_todo_se_escribe_en_la_etapa_de_una_variacion_nueva(guion):
    """004:RF-3 / 007:RF-9 / 007:RF-19 — las demandas van a su variación y cada carga nueva
    a la suya, todas grabando; con el escenario del operador apagado mientras se escribe
    y encendido al terminar."""
    app = fake_pf.proyecto(escenario=True)
    plan = _plan(['F1', 'F2'], [_demanda('F1_S1', 120, 40), _demanda('F2_S2', 90, 10)],
                 [_nueva('N1', barra='F1_B2')])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    variaciones = {v.loc_name: v for v in app.carpetas['scheme'].GetContents('*.IntScheme')}
    assert set(variaciones) == {informe['variacion_demandas'], 'Carga_N1_F1_20261008_120000'}
    etapa_dem = variaciones[informe['variacion_demandas']].GetContents('*.IntSstage')[0]
    etapa_n1 = variaciones['Carga_N1_F1_20261008_120000'].GetContents('*.IntSstage')[0]
    escritas = [e for e in app.escrituras if e[0].GetClassName() in ('ElmLod', 'ElmTerm', 'ElmLne')]
    demandas = [e for e in escritas if e[0].loc_name in ('F1_S1', 'F2_S2')]
    nuevas = [e for e in escritas if 'N1' in e[0].loc_name]
    assert demandas and all(e[3] is etapa_dem for e in demandas)
    assert nuevas and all(e[3] is etapa_n1 for e in nuevas)
    assert all(e[4] is None for e in escritas), 'se escribió con el escenario activo'
    assert app.escenario is not None and app.escenario.loc_name == 'Operador'


def test_nombre_de_variacion_libre_si_ya_existe(guion):
    """004:RF-4 — si el nombre ya existe en el proyecto se usa otro, sin pasar de 40."""
    app = fake_pf.proyecto()
    base = 'X' * 40
    app.carpetas['scheme'].CreateObject('IntScheme', base)
    app.carpetas['scheme'].CreateObject('IntScheme', base[:38] + '_2')
    informe, _rc = guion.ejecutar(app, _plan(['F1'], [_demanda('F1_S1', 1, 0)], variacion=base),
                                  simular=False)
    assert informe['variacion'] == base[:38] + '_3'
    assert len(informe['variacion']) <= 40


def test_un_alimentador_es_un_lote_de_uno(guion):
    """004:RF-5 — el mismo guion y el mismo informe para uno que para varios."""
    rng = random.Random(SEMILLA)
    alims = [f'A{i}' for i in range(rng.randint(2, 7))]
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=rng.randint(1, 5))
    uno, _ = guion.ejecutar(app, _plan(alims[:1], [_demanda(f'{alims[0]}_S1', 5, 1)]), simular=False)
    app = fake_pf.proyecto(alimentadores=alims)
    todos, _ = guion.ejecutar(app, _plan(alims, [_demanda(f'{a}_S1', 5, 1) for a in alims]),
                              simular=False)
    assert [f['feeder'] for f in uno['feeders']] == alims[:1]
    assert [f['feeder'] for f in todos['feeders']] == alims, f'semilla {SEMILLA}'
    assert set(uno['feeders'][0]) == set(todos['feeders'][0])


# =========================================================================== demandas
def test_demanda_que_coincide_se_actualiza(guion):
    """004:RF-6 — la carga de la SED en el alimentador elegido toma la demanda pedida."""
    app = fake_pf.proyecto()
    informe, rc = guion.ejecutar(app, _plan(['F1'], [_demanda('F1_S2', 250, 80)]), simular=False)
    carga = _carga(app, 'F1_S2')
    assert rc == 0
    assert carga.plini == pytest.approx(0.25)
    assert carga.qlini == pytest.approx(0.08)
    assert [a['sed'] for a in informe['feeders'][0]['actualizadas']] == ['F1_S2']


def test_demanda_sin_coincidencia_se_omite_y_sigue(guion):
    """004:RF-7 — una SED que no está en el alimentador se omite, se lista y no para nada."""
    app = fake_pf.proyecto()
    plan = _plan(['F1'], [_demanda('NO_EXISTE', 1, 0), _demanda('F2_S1', 1, 0),
                          _demanda('F1_S1', 7, 2)])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0
    assert {o['sed'] for o in informe['sin_alimentador']} == {'NO_EXISTE', 'F2_S1'}
    assert _carga(app, 'F1_S1').plini == pytest.approx(0.007)


def test_demanda_ambigua_no_se_escribe(guion):
    """004:RF-8 — dos cargas con el mismo nombre en el alimentador: ambigua, sin tocar."""
    app = fake_pf.proyecto(alimentadores=('F1',))
    alim = app.proyecto.GetContents('*.ElmFeeder', 1)[0]
    otra = alim.GetParent().CreateObject('ElmLod', 'F1_S1')
    alim._objs.append(otra)
    app.escrituras.clear()
    informe, _rc = guion.ejecutar(app, _plan(['F1'], [_demanda('F1_S1', 99, 9)]), simular=False)
    assert [a['sed'] for a in informe['ambiguas']] == ['F1_S1']
    assert not [e for e in app.escrituras if e[0].GetClassName() == 'ElmLod']


@pytest.mark.parametrize('modo', ['PC', 'PQ'])
def test_escritura_por_modo_con_signo_de_q_y_relectura(guion, modo):
    """004:RF-9 — solo las entradas del modo, Q capacitiva con su signo, y releída.

    En el simulado, escribir S en modo P–cos φ recalcula P: si el guion escribiera los
    cuatro valores, la relectura daría otra P y la prueba fallaría.
    """
    app = fake_pf.proyecto(alimentadores=('F1',))
    carga = _carga(app, 'F1_S1')
    object.__setattr__(carga, 'mode_inp', modo)
    informe, rc = guion.ejecutar(app, _plan(['F1'], [_demanda('F1_S1', 300, -100)]), simular=False)
    assert rc == 0, informe
    assert carga.plini == pytest.approx(0.3)
    assert carga.qlini == pytest.approx(-0.1)
    escritos = {e[1] for e in app.escrituras if e[0] is carga}
    assert 'slini' not in escritos
    if modo == 'PC':
        assert carga.pf_recap == 1


def test_escritura_por_modo_sin_simulado(guion):
    """004:RF-9 — en SC, SP y QC se escriben solo sus dos entradas."""
    class Carga:
        i_sym = 0
        pf_recap = 0

    for modo, esperados in (('SC', {'slini', 'coslini', 'pf_recap'}), ('SP', {'slini', 'plini'}),
                            ('QC', {'qlini', 'coslini', 'pf_recap'})):
        c = Carga()
        c.mode_inp = modo
        guion.escribir_carga(c, 0.3, -0.1)
        assert set(vars(c)) - {'mode_inp'} == esperados, modo
        if 'slini' in esperados:
            assert c.slini == pytest.approx(math.hypot(0.3, 0.1))


# =========================================================================== cargas nuevas
def test_carga_nueva_en_la_barra_indicada(guion):
    """004:RF-10 — con barra en la fila, se conecta a ella sin línea de enlace si no hay GPS."""
    app = fake_pf.proyecto()
    informe, rc = guion.ejecutar(app, _plan(['F1', 'F2'], nuevas=[_nueva('N1', barra='F2_B3')]),
                                 simular=False)
    assert rc == 0, informe
    creada = informe['feeders'][1]['creadas'][0]
    assert (creada['alimentador'], creada['barra'], creada['criterio']) == ('F2', 'F2_B3', 'barra indicada')
    assert not app.proyecto.GetContents('*.ElmLne', 1)[-1].loc_name.startswith('LNE_')


def test_carga_nueva_en_la_barra_mas_cercana_por_gps(guion):
    """004:RF-11 — sin barra, la más cercana a sus coordenadas, con línea de esa longitud."""
    app = fake_pf.proyecto(cargas_por_alim=4)
    destino = next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == 'F2_B3')
    lat, lon = destino.GPSlat + 0.0003, destino.GPSlon
    informe, rc = guion.ejecutar(app, _plan(['F1', 'F2'], nuevas=[_nueva('N1', lat=lat, lon=lon)]),
                                 simular=False)
    assert rc == 0, informe
    creada = informe['feeders'][1]['creadas'][0]
    assert creada['barra'] == 'F2_B3' and creada['criterio'] == 'barra más cercana por GPS'
    assert creada['distancia_m'] == pytest.approx(33.4, abs=0.5)
    _ver_cargas(app)
    linea = next(o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name == 'LNE_N1')
    assert linea.dline == pytest.approx(creada['distancia_m'] / 1000.0)


def test_tipo_de_linea_de_la_fila_o_de_la_red(guion):
    """004:RF-12 — el tipo de la fila si existe en el proyecto; si no, el de una línea de
    la barra. Nunca un tipo nuevo con R y X a cero."""
    app = fake_pf.proyecto()
    b = next(x for x in app.proyecto.GetContents('*.ElmTerm', 1) if x.loc_name == 'F1_B1')
    cerca = dict(lat=b.GPSlat + 0.0002, lon=b.GPSlon)
    plan = _plan(['F1'], nuevas=[_nueva('N1', tipo_linea='AAAC_F2', **cerca),
                                 _nueva('N2', tipo_linea='NO_EXISTE', **cerca)])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    tipos = {c['sed']: (c['tipo_linea'], c['origen_tipo_linea']) for c in informe['feeders'][0]['creadas']}
    assert tipos == {'N1': ('AAAC_F2', 'de la fila'), 'N2': ('AAAC_F1', 'de la red')}
    assert len(app.proyecto.GetContents('*.TypLne', 1)) == 2


def test_tensiones_y_frecuencia_del_proyecto(guion):
    """004:RF-13 — MT de la barra, BT de la fila o de los trafos del alimentador, Hz de la red."""
    app = fake_pf.proyecto(frnom=50.0)
    plan = _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1', kva_instalado=630),
                                 _nueva('N2', barra='F1_B2', tension_bt_kv=0.23)])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    por_sed = {c['sed']: c for c in informe['feeders'][0]['creadas']}
    assert (por_sed['N1']['tension_mt_kv'], por_sed['N1']['tension_bt_kv']) == (10.0, 0.38)
    assert por_sed['N2']['tension_bt_kv'] == 0.23
    nuevo = next(t for t in app.proyecto.GetContents('*.TypTr2', 1) if t.loc_name.startswith('TR_630'))
    assert nuevo.frnom == 50.0


def test_sin_tension_de_baja_no_se_crea(guion):
    """004:RF-13 / RF-16 — sin BT en la fila ni trafos en el alimentador, no se inventa."""
    app = fake_pf.proyecto(con_trafos=False)
    informe, _rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1')]),
                                  simular=False)
    assert [n['sed'] for n in informe['no_creadas']] == ['N1']
    assert 'tensión de baja' in informe['no_creadas'][0]['motivo']


def test_carga_nueva_escrita_como_demanda_y_dibujada(guion):
    """004:RF-14 — P y cos φ de entrada (modo PC), releída, y en el diagrama de su barra."""
    app = fake_pf.proyecto()
    b = next(x for x in app.proyecto.GetContents('*.ElmTerm', 1) if x.loc_name == 'F1_B2')
    plan = _plan(['F1'], nuevas=[_nueva('N1', kw=120, kvar=-40, lat=b.GPSlat + 0.0002, lon=b.GPSlon)])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    _ver_cargas(app)
    carga = _carga(app, 'N1')
    assert carga.plini == pytest.approx(0.12) and carga.qlini == pytest.approx(-0.04)
    assert 'slini' not in {e[1] for e in app.escrituras if e[0] is carga}
    creada = informe['feeders'][0]['creadas'][0]
    assert creada['error_relectura'] is None
    assert creada['dibujo']['dibujada'] is True
    simbolos = {g.sSymNam for g in app.proyecto.GetContents('*.IntGrf', 1)
                if getattr(g, 'pDataObj', None) is not None and 'N1' in g.pDataObj.loc_name}
    assert {'PointTerm', 'd_lin', 'SecSubProd'} <= simbolos


def test_carga_nueva_que_ya_existe_no_se_crea(guion):
    """004:RF-15 — una SED que ya está en el alimentador no se duplica."""
    app = fake_pf.proyecto()
    informe, _rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('F1_S1', barra='F1_B1')]),
                                  simular=False)
    assert informe['no_creadas'] == [{'sed': 'F1_S1', 'motivo': 'ya existe en el alimentador (RF-15)'}]
    assert len([o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == 'F1_S1']) == 1


def test_carga_no_conectable_se_omite_y_siguen_las_demas(guion):
    """004:RF-16 — sin GPS en las barras, la carga sin barra se omite con motivo; las demás siguen."""
    app = fake_pf.proyecto(con_gps=False)
    plan = _plan(['F1'], nuevas=[_nueva('N1', lat=-14.0, lon=-75.7), _nueva('N2', barra='F1_B1'),
                                 _nueva('N3', barra='NO_ESTA')])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0
    motivos = {n['sed']: n['motivo'] for n in informe['no_creadas']}
    assert set(motivos) == {'N1', 'N3'}
    assert 'GPS' in motivos['N1'] and 'NO_ESTA' in motivos['N3']
    assert [c['sed'] for c in informe['feeders'][0]['creadas']] == ['N2']


# =========================================================================== ejecución
def test_simular_no_escribe(guion):
    """004:RF-17 — simular informa coincidencias, omitidas y conexión sin tocar el proyecto."""
    app = fake_pf.proyecto(escenario=True)
    plan = _plan(['F1'], [_demanda('F1_S1', 10, 1), _demanda('X', 1, 0)],
                 [_nueva('N1', barra='F1_B1')])
    informe, rc = guion.ejecutar(app, plan, simular=True)
    assert rc == 0 and informe['modo'] == 'simular'
    assert not app.escrituras and not app.creados
    f1 = informe['feeders'][0]
    assert [a['sed'] for a in f1['actualizarian']] == ['F1_S1']
    assert [c['barra'] for c in f1['crearian']] == ['F1_B1']
    assert [o['sed'] for o in informe['sin_alimentador']] == ['X']


def test_flujo_final_con_tensiones_extremas(guion):
    """004:RF-18 — tras aplicar, ComLdf con la variación activa; converge y tensiones."""
    app = fake_pf.proyecto()
    for i, b in enumerate(app.proyecto.GetContents('*.ElmTerm', 1)):
        object.__setattr__(b, 'm_u', 0.95 + 0.01 * i)
    informe, _rc = guion.ejecutar(app, _plan(['F1'], [_demanda('F1_S1', 1, 0)]), simular=False)
    flujo = informe['flujo']
    assert flujo['converged'] is True
    assert flujo['vm_min'] == pytest.approx(0.95) and flujo['vm_min_bus'] == 'F1_B0'
    assert flujo['vm_max'] > flujo['vm_min']
    assert app.variaciones_activas, 'el flujo se lanzó sin la variación activa'


def test_flujo_que_no_converge_se_informa(guion):
    """004:RF-18 — un ComLdf que falla queda en el informe como no convergente."""
    app = fake_pf.proyecto()
    object.__setattr__(app.ldf, 'rc', 1)
    informe, _rc = guion.ejecutar(app, _plan(['F1'], [_demanda('F1_S1', 1, 0)]), simular=False)
    assert informe['flujo']['converged'] is False


def test_cancelar_termina_el_alimentador_en_curso(guion):
    """004:RF-19 — al cancelar no se empieza otro alimentador; el de curso termina entero."""
    app = fake_pf.proyecto(alimentadores=('F1', 'F2', 'F3'))
    vistos = []

    def cancelado():
        vistos.append(1)
        return len(vistos) > 1          # cancelan mientras se aplica F1

    plan = _plan(['F1', 'F2', 'F3'], [_demanda(f'{f}_S{i}', 1, 0) for f in ('F1', 'F2', 'F3')
                                      for i in (1, 2, 3)])
    informe, _rc = guion.ejecutar(app, plan, simular=False, cancelado=cancelado)
    assert informe['cancelado'] is True
    assert [f['feeder'] for f in informe['feeders']] == ['F1']
    assert len(informe['feeders'][0]['actualizadas']) == 3


def test_cancelar_por_fichero_desde_main(guion, tmp_path, monkeypatch):
    """004:RF-19 — ``--cancel-file`` presente: el guion no empieza ningún alimentador."""
    app = fake_pf.proyecto()
    import sys
    import types

    monkeypatch.setitem(sys.modules, 'powerfactory', types.SimpleNamespace(GetApplicationExt=lambda: app))
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(_plan(['F1', 'F2'], [_demanda('F1_S1', 1, 0)])), encoding='utf-8')
    flag = tmp_path / 'cancelar.flag'
    flag.write_text('1')
    salida = tmp_path / 'informe.json'
    rc = guion.main(['--plan', str(plan), '--output-json', str(salida), '--cancel-file', str(flag)])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert rc == 0 and informe['cancelado'] is True and informe['feeders'] == []


def test_informe_por_alimentador(guion):
    """004:RF-20 — antes y después de cada demanda, omitidas, ambiguas, creadas y no creadas."""
    app = fake_pf.proyecto()
    plan = _plan(['F1', 'F2'], [_demanda('F1_S1', 40, 5), _demanda('Z', 1, 0)],
                 [_nueva('N1', barra='F2_B1'), _nueva('N2')])
    informe, _rc = guion.ejecutar(app, plan, simular=False)
    f1, f2 = informe['feeders']
    act = f1['actualizadas'][0]
    assert act['antes']['plini'] == pytest.approx(0.05) and act['despues']['plini'] == pytest.approx(0.04)
    assert [c['sed'] for c in f2['creadas']] == ['N1']
    assert [n['sed'] for n in informe['no_creadas']] == ['N2']
    assert [o['sed'] for o in informe['sin_alimentador']] == ['Z']
    assert 'ambiguas' in informe


def test_un_alimentador_que_falla_no_para_los_demas(guion):
    """004:RF-21 — un fallo al escribir en F1 se informa y F2 se aplica igual."""
    app = fake_pf.proyecto()
    carga = _carga(app, 'F1_S1')
    object.__setattr__(carga, 'mode_inp', None)

    class Rota(type(carga)):
        def __setattr__(self, name, value):
            if name == 'plini':
                raise RuntimeError('objeto bloqueado')
            super().__setattr__(name, value)

    object.__setattr__(carga, '__class__', Rota)
    object.__setattr__(carga, 'mode_inp', 'PC')
    plan = _plan(['F1', 'F2'], [_demanda('F1_S1', 1, 0), _demanda('F2_S1', 2, 0)])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 2
    f1, f2 = informe['feeders']
    assert f1['fallos'] and 'bloqueado' in f1['fallos'][0]['error']
    assert [a['sed'] for a in f2['actualizadas']] == ['F2_S1']


# =========================================================================== spec 005
def test_proyecto_por_su_ruta_en_la_carpeta(guion):
    """005:RF-16 — el guion abre el proyecto de la ruta en la carpeta, no otro de la raíz
    que se llame igual."""
    app = fake_pf.proyecto()
    elegido = app.proyecto
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    carpeta.CreateObject('IntFolder', 'Oct').Move(elegido)
    otro = fake_pf.nuevo_proyecto(app, app.usuario, 'P', alimentadores=('F1',))
    app.creados.clear()
    app.escrituras.clear()
    plan = {**_plan(['F1'], [_demanda('F1_S1', 120, 40)]), 'project': 'Oct/P', 'folder': 'Red'}
    informe, rc = guion.ejecutar(app, plan, simular=True)
    assert rc == 0, informe
    assert app.GetActiveProject() is elegido and app.GetActiveProject() is not otro
    assert informe['project_path'] == 'Oct/P'


def test_ruta_que_no_existe_en_la_carpeta(guion):
    """005:RF-16 — una ruta que no está en la carpeta es un error que la nombra."""
    app = fake_pf.proyecto()
    app.usuario.CreateObject('IntFolder', 'Red')
    plan = {**_plan(['F1'], [_demanda('F1_S1', 1, 1)]), 'project': 'Oct/P', 'folder': 'Red'}
    informe, rc = guion.ejecutar(app, plan, simular=True)
    assert rc == 2 and 'Oct/P' in informe['error']


def test_error_inesperado_deja_informe(guion, tmp_path, monkeypatch):
    """008:RF-17 — si ``ejecutar`` revienta, ``main`` escribe el informe con el error y su tipo."""
    import sys
    import types

    app = fake_pf.proyecto()
    monkeypatch.setitem(sys.modules, 'powerfactory', types.SimpleNamespace(GetApplicationExt=lambda: app))

    def revienta(*_a, **_k):
        raise RuntimeError('la etapa de Cargas_F1 no quedó grabando')

    monkeypatch.setattr(guion, 'ejecutar', revienta)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(_plan(['F1'], [_demanda('F1_S1', 1, 0)])), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    rc = guion.main(['--plan', str(plan), '--output-json', str(salida), '--simular'])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert rc == 1 and informe['modo'] == 'simular'
    assert informe['error'] == 'error inesperado del guion: RuntimeError: la etapa de Cargas_F1 no quedó grabando'
