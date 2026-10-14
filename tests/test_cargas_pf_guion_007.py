"""Spec 007: cargas nuevas sobre el alimentador ajustado, una variación por carga.

``tools/cargas_pf.py`` contra el DIgSILENT simulado (``fake_pf``): lo creado con la
etapa de una variación inactiva sale de la red, así que el flujo de la carga *i* solo ve
la base y esa carga. La prueba real, con SI213, la hace el usuario (T11).
"""
from __future__ import annotations

import os
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta
from test_cargas_pf_guion import _carga, _demanda, _nueva, _plan

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))
STAMP = '20261008_120000'


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_guion_007', tools_en_path=True)


def _app(alimentadores=('F1', 'F2'), n=4, **kw):
    kw.setdefault('bt', True)
    kw.setdefault('flujo', True)
    return fake_pf.proyecto(alimentadores=alimentadores, cargas_por_alim=n, **kw)


def _ajuste(app, nombre='Ajuste_F1_20261009_120000'):
    """Una variación del ajuste, ya creada y desactivada, como si el operador la apagara."""
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage('Etapa_ajuste', 0, 1)
    v.Deactivate()
    app.creados.clear()
    app.escrituras.clear()
    return v


def _base(nombres=('Ajuste_F1_20261009_120000',), sed=None):
    return {'job_id': 'j', 'feeders': ['F1'], 'variaciones': list(nombres),
            'ajustes': [{'feeder': 'F1', 'variacion': n, 'cuadrado': True} for n in nombres],
            'sed': sed or {}, 'excluidos': []}


def _barra(app, nombre):
    return next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == nombre)


def _cerca(app, barra, dlat=0.0003):
    b = _barra(app, barra)
    return {'lat': b.GPSlat + dlat, 'lon': b.GPSlon}


def _variaciones(app):
    return {v.loc_name: v for v in app.carpetas['scheme'].GetContents('*.IntScheme')}


def _activas_en(app, nombre):
    """Variaciones activas en uno de los tres casos, que la inserción prepara (014:RF-19)."""
    previo = app.caso
    next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre).Activate()
    out = sorted(v.loc_name for v in app.GetActiveNetworkVariations())
    previo.Activate()
    return out


# =========================================================================== base
def test_base_se_activa_antes_de_crear_nada(guion):
    """007:RF-6 / 007:RF-8 — la variación base se activa antes de crear ninguna, y el informe
    lista las activas al empezar y al terminar."""
    app = _app()
    base = _ajuste(app)
    orden = []
    original = base.Activate
    object.__setattr__(base, 'Activate', lambda *a: (orden.append(len(_variaciones(app))), original())[1])
    plan = {**_plan(['F1'], [_demanda('F1_S1', 10, 1)], [_nueva('N1', barra='F1_B2')]), 'base': _base()}
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    # Solo cuenta la primera: después ``crear_variacion`` la aparta y la reactiva para que
    # grabe la etapa nueva, que es de la misma fecha (manual de PF 2024, 16.5).
    assert orden[0] == 1, 'la base se activó con otras variaciones ya creadas'
    assert informe['base_activada'] == ['Ajuste_F1_20261009_120000']
    assert informe['variaciones_activas_inicio'] == []
    # 014:RF-19 / 015:RF-27: sin los tres casos se preparan; las demandas quedan en el
    # escenario de «Sin proyecto», sin variación, y el caso del principio, ya «Caso base»,
    # sin ninguna. La base de antes de la 015 sigue activa en «Sin proyecto».
    assert informe['casos_preparados']
    assert informe['demandas_en'] == 'Sin proyecto'
    assert _activas_en(app, 'Sin proyecto') == ['Ajuste_F1_20261009_120000']
    assert informe['variaciones_activas_fin'] == []


def test_base_que_no_existe_no_aplica_nada(guion):
    """007:RF-7 — si la variación base ya no está, no se aplica nada y se dice su nombre."""
    app = _app()
    plan = {**_plan(['F1'], [_demanda('F1_S1', 10, 1)]), 'base': _base(['Ajuste_BORRADO'])}
    for simular in (True, False):
        informe, rc = guion.ejecutar(app, plan, simular=simular)
        assert rc == 2 and 'Ajuste_BORRADO' in informe['error']
    assert not app.escrituras and not app.creados


def test_base_que_no_cuadro_se_avisa_en_el_informe(guion):
    """007:RF-34 — el aviso del plan sobre una base que no cuadró llega al informe."""
    app = _app()
    _ajuste(app)
    aviso = 'El ajuste de F1 no cuadró (error en la cabecera +3.10%): se usa igual como base (RF-34).'
    plan = {**_plan(['F1'], [_demanda('F1_S1', 10, 1)]), 'base': _base(), 'avisos': [aviso]}
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0 and aviso in informe['avisos']


def test_sin_base_se_aplica_sobre_lo_activo(guion):
    """007:RF-5 — sin base se aplica con lo que esté activo, y el aviso del plan lo dice."""
    app = _app()
    otra = _ajuste(app, 'A_mano')
    otra.Activate()
    aviso = 'Sin base del ajuste: se aplica sobre las variaciones que estén activas en el proyecto (spec 007, RF-5).'
    plan = {**_plan(['F1'], [_demanda('F1_S1', 10, 1)]), 'avisos': [aviso]}
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0 and aviso in informe['avisos']
    assert informe['variaciones_activas_inicio'] == ['A_mano']
    assert 'A_mano' in informe['variaciones_activas_fin']


# =========================================================================== alimentador activo
def test_activo_solo_sus_barras_sin_umbral(guion):
    """007:RF-24 / 007:RF-25 / 007:RF-31 — por coordenadas, la barra más cercana del alimentador
    activo aunque otra de otro alimentador esté más cerca, y sin umbral de distancia."""
    app = _app()
    lejos = _cerca(app, 'F2_B3', dlat=0.0001)
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', **lejos)]), simular=False)
    assert rc == 0, informe
    creada = informe['feeders'][0]['creadas'][0]
    assert creada['alimentador'] == 'F1' and creada['barra'].startswith('F1_')
    assert creada['distancia_m'] > 1000, 'se conectó aunque está a más de un km'


def test_activo_barra_indicada_como_alternativa(guion):
    """007:RF-26 / 007:RF-27 — la barra indicada si es del activo; si no, no se conecta y se nombra."""
    app = _app()
    plan = _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B2'), _nueva('N2', barra='F2_B1')])
    informe, _rc = guion.ejecutar(app, plan, simular=False)
    assert [(c['sed'], c['criterio']) for c in informe['feeders'][0]['creadas']] == [('N1', 'barra indicada')]
    assert informe['no_creadas'][0]['sed'] == 'N2' and 'F2_B1' in informe['no_creadas'][0]['motivo']


def test_activo_sin_gps_se_dice_una_vez(guion):
    """007:RF-28 — sin barras con coordenadas en el activo, ninguna carga por coordenadas, y
    se dice una vez con el alimentador."""
    app = _app(con_gps=False)
    plan = _plan(['F1'], nuevas=[_nueva('N1', lat=-14.0, lon=-75.7), _nueva('N2', lat=-14.0, lon=-75.69)])
    informe, _rc = guion.ejecutar(app, plan, simular=False)
    assert {n['sed'] for n in informe['no_creadas']} == {'N1', 'N2'}
    avisos = [a for a in informe['avisos'] if 'coordenadas' in a]
    assert len(avisos) == 1 and 'F1' in avisos[0]


def test_activo_otro_alimentador_no_se_crea(guion):
    """007:RF-29 — una carga del libro con otro alimentador no se crea, aunque esté junto a
    una barra del activo; la del activo sí, escrita como la escriba el libro."""
    app = _app()
    plan = _plan(['F1'], nuevas=[_nueva('N1', alimentador='F2', **_cerca(app, 'F1_B2')),
                                 _nueva('N2', alimentador=' f1 ', **_cerca(app, 'F1_B3'))])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    assert [c['sed'] for c in informe['cargas']] == ['N2']
    assert informe['no_creadas'][0]['sed'] == 'N1' and 'F2' in informe['no_creadas'][0]['motivo']
    assert any('F2 (1)' in a for a in informe['avisos'])


def test_activo_ninguna_del_libro_ninguna_creada(guion):
    """007:RF-29 — si ninguna fila es de un alimentador marcado, no se crea ninguna."""
    app = _app()
    plan = _plan(['F1'], nuevas=[_nueva('N1', alimentador='F2', **_cerca(app, 'F1_B1')),
                                 _nueva('N2', alimentador='F9', **_cerca(app, 'F1_B2'))])
    informe, _rc = guion.ejecutar(app, plan, simular=False)
    assert informe['cargas'] == [] and not any(f['creadas'] for f in informe['feeders'])
    assert {n['sed'] for n in informe['no_creadas']} == {'N1', 'N2'}
    assert not _variaciones(app)


def test_barra_sin_linea_toma_el_tipo_del_alimentador(guion):
    """007:RF-39 — la barra más cercana no tiene línea (el nodo de una SED): la línea de
    enlace toma el tipo más usado del alimentador, y se dice de dónde sale."""
    app = _app()
    alim = next(a for a in app.proyecto.GetContents('*.ElmFeeder', 1) if a.loc_name == 'F1')
    junto = _barra(app, 'F1_B2')
    suelta = junto.GetParent().CreateObject('ElmTerm', 'F1_SED_SIN_LINEA')
    suelta.uknom, suelta.iUsage = 10.0, 1
    suelta.GPSlat, suelta.GPSlon = junto.GPSlat - 0.002, junto.GPSlon
    alim._objs.append(suelta)
    app.creados.clear()
    plan = _plan(['F1'], nuevas=[_nueva('N1', alimentador='F1', lat=suelta.GPSlat - 0.0003,
                                        lon=suelta.GPSlon)])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0 and not informe['no_creadas'], informe['no_creadas']
    creada = informe['feeders'][0]['creadas'][0]
    assert creada['barra'] == 'F1_SED_SIN_LINEA'
    assert creada['tipo_linea'] and creada['origen_tipo_linea'] == 'el más usado del alimentador'


def test_deshacer_borra_lo_creado(guion):
    """007:RF-38 — deshacer con el informe borra las variaciones de las cargas creadas y
    nada más; simulando, solo las lista."""
    app = _app()
    previa = _ajuste(app, 'Ajuste_F1')
    plan = _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1'), _nueva('N2', barra='F1_B2')])
    aplicado, rc = guion.ejecutar(app, plan, simular=False)
    cargas = lambda: sorted(n for n in _variaciones(app) if n.startswith('Carga_'))
    assert rc == 0 and len(cargas()) == 2
    simulado, _rc = guion.deshacer(app, plan, aplicado, simular=True)
    assert len(simulado['variaciones']) == 2 and len(cargas()) == 2
    informe, rc = guion.deshacer(app, plan, aplicado, simular=False)
    assert rc == 0 and sorted(informe['variaciones']) == sorted(c['variacion'] for c in aplicado['cargas'])
    assert cargas() == []
    assert previa in app.GetProjectFolder('scheme').GetContents('*.IntScheme', 1)
    otro, rc = guion.deshacer(app, plan, {**aplicado, 'project': 'Otro'}, simular=False)
    assert rc == 2 and 'Otro' in otro['error']


def test_activo_con_varios_marcados(guion):
    """007:RF-36 — con varios marcados: el de su columna si está marcado; sin columna, el de
    la barra más cercana entre los marcados; con uno no marcado, no se crea (RF-29)."""
    app = _app()
    plan = _plan(['F1', 'F2'], nuevas=[
        _nueva('N1', alimentador='F2', **_cerca(app, 'F1_B1')),      # su columna manda
        _nueva('N2', **_cerca(app, 'F1_B3')),                        # sin columna: la más cercana
        _nueva('N3', alimentador='F9', **_cerca(app, 'F2_B2')),      # F9 no marcado: no se crea
    ])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    donde = {c['sed']: c['alimentador'] for c in informe['cargas']}
    assert donde == {'N1': 'F2', 'N2': 'F1'}
    assert [n['sed'] for n in informe['no_creadas']] == ['N3']


# =========================================================================== una variación por carga
def test_una_variacion_por_carga_con_solo_sus_objetos(guion):
    """007:RF-9 / 007:RF-10 / 007:RF-11 / 007:RF-17 — cada carga en su variación, con su SED y
    su alimentador en el nombre, solo con sus objetos, y desactivada al terminar."""
    rng = random.Random(SEMILLA)
    n = rng.randint(2, 6)
    app = _app(n=n + 1)
    nuevas = [_nueva(f'N{i}', barra=f'F1_B{i}') for i in range(1, n + 1)]
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=False)
    assert rc == 0, f'semilla {SEMILLA}: {informe}'
    vs = _variaciones(app)
    assert sorted(vs) == sorted(f'Carga_N{i}_F1_{STAMP}' for i in range(1, n + 1))
    for i in range(1, n + 1):
        etapa = vs[f'Carga_N{i}_F1_{STAMP}'].GetContents('*.IntSstage')[0]
        creados = [o for o in app.creados if o.etapa_creacion is etapa and o._clase.startswith('Elm')]
        assert creados and all(f'N{i}' in o.loc_name for o in creados), f'semilla {SEMILLA}'
    assert not [v for v in informe['variaciones_activas_fin'] if v.startswith('Carga_')]


def test_nombre_de_variacion_sin_repetir(guion):
    """007:RF-10 — si ya hay una variación con ese nombre, la de la carga lleva sufijo."""
    app = _app()
    app.carpetas['scheme'].CreateObject('IntScheme', f'Carga_N1_F1_{STAMP}')
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1')]), simular=False)
    assert rc == 0 and informe['cargas'][0]['variacion'] == f'Carga_N1_F1_{STAMP}_2'


def test_cada_carga_se_mide_sin_las_anteriores(guion):
    """007:RF-12 / 007:RF-13 / 007:RF-32 / 007:RF-33 — sin proyecto se mide una vez; cada carga,
    con la base y solo ella: su diferencia es la suya, no la suma con las anteriores."""
    app = _app()
    nuevas = [_nueva(f'N{i}', barra=f'F1_B{i}', kw=80.0, kvar=30.0) for i in (1, 2, 3)]
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=nuevas), simular=False)
    assert rc == 0, informe
    sin = informe['sin_proyecto']['feeders']['F1']
    assert sin['cabecera'] is not None and sin['perdidas_kw'] > 0
    deltas = [c['delta'] for c in informe['cargas']]
    for d in deltas:
        assert 80.0 < d['kw'] < 120.0, 'la carga vio a las anteriores'
        assert d['perdidas_kw'] > 0 and d['kvar'] > 0 and d['vm_min'] is not None
    con = informe['cargas'][0]['con_proyecto']
    assert con['converged'] and con['feeders']['F1']['cabecera']['kw'] > sin['cabecera']['kw']
    # Un flujo sin proyecto, uno por carga y el final con la base sola.
    assert app.ldf.ejecuciones == 1 + len(nuevas) + 1


def test_no_se_reajusta_tras_conectar(guion):
    """007:RF-14 — conectar cargas no cambia las demandas de las cargas existentes."""
    app = _app()
    antes = {o.loc_name: o.plini for o in app.proyecto.GetContents('*.ElmLod', 1)}
    guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1')]), simular=False)
    despues = {o.loc_name: o.plini for o in app.proyecto.GetContents('*.ElmLod', 1)}
    assert despues == antes


def test_carga_no_conectable_no_crea_variacion(guion):
    """007:RF-15 — sin barra ni coordenadas no se crea su variación; se lista y se sigue."""
    app = _app()
    plan = _plan(['F1'], nuevas=[_nueva('N1'), _nueva('N2', barra='F1_B1')])
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0
    assert [n['sed'] for n in informe['no_creadas']] == ['N1']
    assert list(_variaciones(app)) == [f'Carga_N2_F1_{STAMP}']


def test_cancelar_entre_cargas(guion):
    """007:RF-16 / 007:RF-17 — cancelar termina la carga en curso, no empieza otra, conserva
    las creadas y deja activa solo la base."""
    app = _app()
    _ajuste(app)
    vistos = []

    def cancelado():
        vistos.append(1)
        return len(vistos) > 2            # F1 empieza, N1 se crea; antes de N2, cancelan

    plan = {**_plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1'), _nueva('N2', barra='F1_B2')]), 'base': _base()}
    informe, _rc = guion.ejecutar(app, plan, simular=False, cancelado=cancelado)
    assert informe['cancelado'] is True
    assert [c['sed'] for c in informe['cargas']] == ['N1']
    assert f'Carga_N1_F1_{STAMP}' in _variaciones(app)
    assert _activas_en(app, 'Sin proyecto') == ['Ajuste_F1_20261009_120000']


def test_simular_dice_la_variacion_de_cada_carga(guion):
    """007:RF-18 / 007:RF-30 — al simular, por carga la barra, el criterio, la distancia y el
    nombre de la variación que crearía, sin escribir nada."""
    app = _app()
    plan = _plan(['F1'], nuevas=[_nueva('N1', **_cerca(app, 'F1_B2')), _nueva('N2', barra='F1_B3')])
    informe, rc = guion.ejecutar(app, plan, simular=True)
    assert rc == 0 and not app.creados and not app.escrituras
    crearian = informe['feeders'][0]['crearian']
    assert [c['variacion'] for c in crearian] == [f'Carga_N1_F1_{STAMP}', f'Carga_N2_F1_{STAMP}']
    assert crearian[0]['barra'] == 'F1_B2' and crearian[0]['distancia_m'] == pytest.approx(33.4, abs=0.5)
    assert crearian[1]['criterio'] == 'barra indicada'


def test_demandas_en_el_escenario_de_sin_proyecto_antes_que_las_cargas(guion):
    """007:RF-19 / 007:RF-35 / 015:RF-27 — las demandas van al escenario de «Sin proyecto»,
    antes que las cargas, y entran en el estado sin proyecto; no crean variación."""
    app = _app()
    plan = _plan(['F1'], [_demanda('F1_S1', 300, 50)], [_nueva('N1', barra='F1_B2')])
    sin_demanda = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True)
    ref, _ = guion.ejecutar(sin_demanda, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B2')]), simular=False)
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    nombres = [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')]
    assert nombres == [f'Carga_N1_F1_{STAMP}']
    assert informe['demandas_en'] == 'Sin proyecto'
    sin = informe['sin_proyecto']['feeders']['F1']['cabecera']['kw']
    assert sin > ref['sin_proyecto']['feeders']['F1']['cabecera']['kw'] + 200, 'la demanda no entró sin proyecto'
    assert _activas_en(app, 'Sin proyecto') == []


def test_el_libro_manda_sobre_la_calibrada(guion):
    """007:RF-20 / 007:RF-21 — una SED calibrada que el libro cambia toma el valor del libro, y
    el informe lo lista."""
    app = _app()
    _ajuste(app)
    cambiadas = [{'sed': 'F1_S1', 'feeder': 'F1', 'calibrada': {'kw': 50.0, 'kvar': 10.0},
                  'libro': {'kw': 75.0, 'kvar': 12.0}}]
    plan = {**_plan(['F1'], [_demanda('F1_S1', 75, 12)]), 'base': _base(sed={'F1_S1': {'kw': 50.0}}),
            'calibradas_cambiadas': cambiadas}
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0
    assert _carga(app, 'F1_S1').plini == pytest.approx(0.075)
    assert informe['calibradas_cambiadas'] == cambiadas


# =========================================================================== técnico-económica
class _Tececo:
    def __init__(self, app):
        self.app, self.activas = app, []

    def SetAttribute(self, *_a):
        pass

    def Execute(self):
        self.activas.append(sorted(v.loc_name for v in self.app.variaciones_activas))
        return 0


class _Ventana:
    def Clear(self):
        pass

    def GetContent(self):
        return ['Net Present Value: 1234']


def test_tececo_por_carga_con_su_etapa(guion, monkeypatch):
    """007:RF-22 / 007:RF-23 — la evaluación se hace por carga, con la base y solo esa carga
    activas, sus datos económicos en su etapa, y su resultado aparte en el informe."""
    app = _app()
    _ajuste(app)
    orden = _Tececo(app)
    ldf = app.ldf
    monkeypatch.setattr(app, 'GetFromStudyCase', lambda n: ldf if n == 'ComLdf' else orden, raising=False)
    monkeypatch.setattr(app, 'GetOutputWindow', lambda: _Ventana(), raising=False)
    costos = {'sed_fijo_usd': 1000.0, 'trafo_usd_por_kva': 10.0, 'linea_usd_por_km': 0.0}
    plan = {**_plan(['F1'], nuevas=[_nueva('N1', barra='F1_B1', kva_instalado=100.0),
                                    _nueva('N2', barra='F1_B2', kva_instalado=250.0)]),
            'base': _base(), 'costos': costos, 'tec': {'parametros': {'inicio': 2026}, 'comtececo': {}}}
    informe, rc = guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    assert orden.activas == [sorted(['Ajuste_F1_20261009_120000', f'Carga_N1_F1_{STAMP}']),
                             sorted(['Ajuste_F1_20261009_120000', f'Carga_N2_F1_{STAMP}'])]
    por_sed = {c['sed']: c for c in informe['cargas']}
    assert por_sed['N1']['economia']['InvCosts'] == pytest.approx(2.0)     # 1000 + 10·100 US$
    assert por_sed['N2']['economia']['InvCosts'] == pytest.approx(3.5)
    assert all(c['tecnico_economico']['ok'] for c in informe['cargas'])
    etapa_n2 = _variaciones(app)[f'Carga_N2_F1_{STAMP}'].GetContents('*.IntSstage')[0]
    assert etapa_n2.InvCosts == pytest.approx(3.5)


# =========================================================================== spec 014
def _caso(app, nombre):
    return next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre)


def test_repetir_la_insercion_reutiliza_la_variacion(guion):
    """014:RF-19, 014:RF-23, 014:RF-24, 014:RF-27, 014:RF-28 — la primera inserción prepara
    los casos y deja la carga solo en «Con proyecto»; repetirla, con la variación apagada y
    otra potencia y otro punto en el libro, no crea otra: reutiliza la variación, la deja
    activa en «Con proyecto» y avisa de las diferencias."""
    app = _app()
    primero, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', **_cerca(app, 'F1_B2'))]),
                                 simular=False)
    assert rc == 0, primero
    var = f'Carga_N1_F1_{STAMP}'
    assert primero['casos_preparados']
    assert var in _activas_en(app, 'Con proyecto')
    assert var not in _activas_en(app, 'Sin proyecto') and var not in _activas_en(app, 'Caso base')
    _caso(app, 'Con proyecto').Activate()
    _variaciones(app)[var].Deactivate()
    _caso(app, 'Caso base').Activate()

    otra = _nueva('N1', kw=95.0, **_cerca(app, 'F1_B2', dlat=0.001))
    segundo, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[otra]), simular=False)

    assert rc == 0, segundo
    assert sorted(_variaciones(app)) == [var] and segundo['cargas'] == []
    (reuso,) = segundo['reutilizadas']
    assert reuso['variacion'] == var and '014:RF-24' in reuso['motivo']
    assert any('80.0 kW' in a and '95.0 kW' in a for a in segundo['avisos'])
    assert any('libro la da en' in a for a in segundo['avisos'])
    assert var in _activas_en(app, 'Con proyecto')


def test_carga_en_dos_variaciones_no_se_crea_ni_se_toca(guion):
    """014:RF-26 — una carga que ya está en dos variaciones no se crea otra vez, ninguna de
    las dos cambia de estado en «Con proyecto» y se avisa; las demás cargas sí se crean."""
    app = _app()
    primero, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B2')]),
                                 simular=False)
    assert rc == 0, primero
    _caso(app, 'Con proyecto').Activate()
    copia = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_N1_F1_20261001_000000')
    copia.NewStage('Etapa_copia', 1, 1)
    app.grabando = copia.GetContents('*.IntSstage')[0]
    _carga(app, 'F1_S1').GetParent().CreateObject('ElmLod', 'N1')
    app.grabando = None
    copia.Deactivate()
    antes = _activas_en(app, 'Con proyecto')
    _caso(app, 'Caso base').Activate()

    segundo, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B2'),
                                                           _nueva('N2', barra='F1_B3')]),
                                 simular=False)

    assert rc == 0, segundo
    assert [c['sed'] for c in segundo['cargas']] == ['N2']
    n1 = next(x for x in segundo['no_creadas'] if x['sed'] == 'N1')
    assert n1['variaciones'] == sorted([copia.loc_name, f'Carga_N1_F1_{STAMP}'])
    assert any('014:RF-26' in a for a in segundo['avisos'])
    despues = _activas_en(app, 'Con proyecto')
    assert copia.loc_name not in despues and f'Carga_N1_F1_{STAMP}' in despues
    assert set(antes) <= set(despues)


def test_ya_creada_en_la_red_de_con_proyecto_o_en_el_libro(guion):
    """014:RF-25, 014:RF-27 — por su nombre en su alimentador: en la red de «Con proyecto»
    fuera de una variación de carga nueva no se crea; repetida en el libro, tampoco."""
    fila = _nueva('N7', barra='F1_B2')
    no_creada, avisos = guion.ya_creada(fila, ['F1'], set(), {'indice': {}, 'red': {'N7'}})
    assert '014:RF-25' in no_creada['motivo'] and avisos == []
    no_creada, _ = guion.ya_creada(fila, ['F1'], {'N7'}, {'indice': {}, 'red': set()})
    assert 'RF-15' in no_creada['motivo']
    assert guion.ya_creada(fila, ['F1'], set(), {'indice': {('F2', 'N7'): {'variaciones': ['x']}},
                                                  'red': set()}) is None


def test_con_proyecto_recibe_lo_del_operador_en_sin_proyecto(guion):
    """014:RF-21, 014:RF-22 — antes de insertar, lo que el operador tiene activo en «Sin
    proyecto» se activa en «Con proyecto» y se dice en el informe."""
    app = _app()
    primero, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N1', barra='F1_B2')]),
                                 simular=False)
    assert rc == 0, primero
    _caso(app, 'Sin proyecto').Activate()
    trafo = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_F1_S2')
    operador = fake_pf.variacion_del_operador(app, 'Refuerzo_TR_F1_S2', [(trafo, 'ntnum', 2)])
    _caso(app, 'Caso base').Activate()

    segundo, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[_nueva('N2', barra='F1_B3')]),
                                 simular=False)

    assert rc == 0, segundo
    assert segundo['variaciones_operador_activadas'] == [operador.loc_name]
    assert operador.loc_name in _activas_en(app, 'Con proyecto')
    assert operador.loc_name in _activas_en(app, 'Sin proyecto')
    assert any(operador.loc_name in a and 'Activadas en «Con proyecto»' in a for a in segundo['avisos'])
