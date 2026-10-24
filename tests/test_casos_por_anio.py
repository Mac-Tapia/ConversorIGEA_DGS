"""Spec 025, T6: «Sin proyecto <año>» y «Con proyecto <año>» en el mismo proyecto de DIgSILENT.

El usuario (2026-10-23): «la recalibración con el modelo de año 2025 debe ser aparte de 2026,
cada uno debe hacerse de forma individual, no deben mezclarse». Los casos sin año en el
nombre son los que ya existen (los de 2026); otro año tiene los suyos, copia del «Caso base».
Con el doble ``fake_pf``; el año se sortea.
"""
from __future__ import annotations

import random

import pytest

from test_casos_pf import (  # noqa: F401 - el fixture autouse también vale aquí
    _activas_en, _caso, _plan_ajuste, _red_calibrada, _sin_activar_proyecto, ajuste_pf, casos_pf)

ANIO = random.Random().randint(2015, 2035)


def _nombres(app):
    return sorted(c.loc_name for c in app.carpetas['study'].GetContents('*.IntCase'))


def test_nombre_del_caso_por_anio():
    """025:RF-14, RF-17 — con año, «Sin proyecto <año>»; sin año, los nombres de siempre."""
    assert casos_pf.nombre_caso('sin', ANIO) == f'Sin proyecto {ANIO}'
    assert casos_pf.nombre_caso('con', ANIO) == f'Con proyecto {ANIO}'
    assert casos_pf.nombre_caso('base', ANIO) == 'Caso base'
    assert [casos_pf.nombre_caso(r) for r in ('base', 'sin', 'con')] == list(casos_pf.NOMBRES.values())


def test_sin_proyecto_del_anio_junto_a_los_actuales():
    """025:RF-14, RF-15, RF-17 — se crea «Sin proyecto <año>», copia del «Caso base» y con su
    escenario; los casos sin año siguen siendo los mismos objetos."""
    app, _base = _red_calibrada(escenario=True)
    antes = {r: c for r, c in casos_pf.casos_del_proyecto(app).items()}
    informe, rc = casos_pf.preparar_sin(app, {'project': 'P', 'feeders': ['F1'],
                                              'caso_base_sin_verificar': {}, 'anio_casos': ANIO})
    assert rc == 0, informe
    assert _nombres(app) == sorted(['Caso base', 'Sin proyecto', 'Con proyecto',
                                    f'Sin proyecto {ANIO}'])
    assert casos_pf.casos_del_proyecto(app) == antes
    del_anio = casos_pf.casos_del_proyecto(app, ANIO)
    assert set(del_anio) == {'base', 'sin'} and del_anio['base'] is antes['base']
    assert casos_pf.rol_de(del_anio['sin']) == f'sin@{ANIO}'
    assert informe['casos']['sin']['nombre'] == f'Sin proyecto {ANIO}'
    assert _activas_en(app, del_anio['sin'])[1].loc_name == f'Sin proyecto {ANIO}'


def test_el_anio_parte_del_caso_base_y_no_de_la_otra_calibracion():
    """025:RF-15, 025:RF-19 — calibrado «Sin proyecto» (2026), «Sin proyecto <año>» tiene la
    demanda del «Caso base»: los sin medición de ese año quedan con la del archivo."""
    app, _base = _red_calibrada(manda=True)
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste())
    assert rc == 0, informe
    carga = next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == 'F1_S1')

    def p_en(caso):
        previo = app.caso
        caso.Activate()
        valor = carga.plini
        previo.Activate()
        return valor

    casos = casos_pf.casos_del_proyecto(app)
    assert p_en(casos['sin']) != pytest.approx(p_en(casos['base']))       # 2026 calibró
    casos_pf.preparar_sin(app, {'project': 'P', 'feeders': ['F1'],
                                'caso_base_sin_verificar': {}, 'anio_casos': ANIO})
    del_anio = casos_pf.casos_del_proyecto(app, ANIO)
    assert p_en(del_anio['sin']) == pytest.approx(p_en(casos['base']))


def test_con_proyecto_del_anio_es_copia_de_su_sin_proyecto():
    """025:RF-16 — «Con proyecto <año>» sale de «Sin proyecto <año>», con su escenario."""
    app, base = _red_calibrada(escenario=True)
    informe, rc = casos_pf.preparar(app, {'project': 'P', 'feeders': ['F1'], 'base': base,
                                          'caso_base_sin_verificar': {}, 'anio_casos': ANIO})
    assert rc == 0, informe
    del_anio = casos_pf.casos_del_proyecto(app, ANIO)
    assert set(del_anio) == {'base', 'sin', 'con'}
    assert del_anio['con'].loc_name == f'Con proyecto {ANIO}'
    assert casos_pf.rol_de(del_anio['con']) == f'con@{ANIO}'
    assert _activas_en(app, del_anio['con'])[1].loc_name == f'Con proyecto {ANIO}'
    assert len(_nombres(app)) == 5


def test_el_ajuste_del_anio_solo_escribe_en_sus_casos():
    """025:RF-18 — la calibración de un año va a sus escenarios; los de otro año, intactos."""
    app, _base = _red_calibrada()
    plan = {**_plan_ajuste(), 'anio_casos': ANIO}
    informe, rc = ajuste_pf.ejecutar(app, plan)
    assert rc == 0, informe
    assert informe['caso'] == f'Sin proyecto {ANIO}'
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod'
                and e[1] != 'i_scale']
    assert escritas and {e[4].loc_name for e in escritas} <= {f'Sin proyecto {ANIO}',
                                                             f'Con proyecto {ANIO}'}


def test_un_caso_del_anio_que_no_creo_el_sistema_no_se_toca():
    """025:RF-21 — un «Sin proyecto <año>» del operador: no se toca y se pide renombrarlo."""
    app, _base = _red_calibrada()
    ajeno = app.carpetas['study'].CreateObject('IntCase', f'Sin proyecto {ANIO}')
    informe, rc = casos_pf.preparar_sin(app, {'project': 'P', 'feeders': ['F1'],
                                              'caso_base_sin_verificar': {}, 'anio_casos': ANIO})
    assert rc == 2 and f'Sin proyecto {ANIO}' in informe['error'] and 'renómbrelo' in informe['error']
    assert casos_pf.rol_de(ajeno) is None
    assert casos_pf.casos_del_proyecto(app, ANIO).get('sin') is None


def test_el_proyecto_entero_se_calibra_en_los_casos_del_anio():
    """025:RF-18 (021:RF-54) — un sistema entero, todos sus alimentadores en «Sin proyecto
    <año>»; «Sin proyecto» sin año no se crea ni se toca."""
    from test_ajuste_cabecera_guion import _app
    from test_ajuste_proyecto_guion import _de

    app = _app(escenario=True)
    planes = [{**_de(_plan_ajuste(), 'F1', 300.0), 'anio_casos': ANIO},
              {**_de(_plan_ajuste(), 'F2', 220.0), 'anio_casos': ANIO}]
    (f1, rc1), (f2, rc2) = ajuste_pf.ejecutar_proyecto(app, planes)
    assert (rc1, rc2) == (0, 0), (f1, f2)
    assert f1['caso'] == f2['caso'] == f'Sin proyecto {ANIO}'
    assert f1['escenarios'][0]['escenario'] == f'Sin proyecto {ANIO}'
    assert 'Sin proyecto' not in _nombres(app)


def test_planes_de_anios_distintos_no_se_calibran_juntos():
    """025:RF-18 — un año cada vez: dos planes de años distintos no se mezclan en un ajuste."""
    from test_ajuste_cabecera_guion import _app
    from test_ajuste_proyecto_guion import _de

    app = _app(escenario=True)
    planes = [{**_de(_plan_ajuste(), 'F1', 300.0), 'anio_casos': ANIO},
              {**_de(_plan_ajuste(), 'F2', 220.0), 'anio_casos': None}]
    resultados = ajuste_pf.ejecutar_proyecto(app, planes)
    assert all(rc == 2 and 'años distintos' in inf['error'] for inf, rc in resultados)
    assert casos_pf.casos_del_proyecto(app, ANIO) == {}


# =========================================================================== T7: plan y registro
def _ws(tmp_path, monkeypatch, *, calibrado: bool, anios=(2025, 2026)):
    from test_client_period_contract import _workspace
    from igea_dgs.web import services

    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'Conversor IGEA-DGS')
    ws = _workspace(tmp_path, with_client_book=False)
    ws.demanda['cabecera'] = {'path': str(tmp_path), 'anios': list(anios)}
    if calibrado:                     # calibrado antes de la spec 025: sin el año guardado
        ws.calibraciones['P'] = {'A1': {'sed': {'S1': [10.0, 2.0]}, 'nombre': 'la anterior'}}
    return ws, services


def _maxima_de(anio):
    from test_client_period_contract import _maxima
    return _maxima(f'{anio}-07-16 11:00:00')


def test_plan_de_otro_anio_va_a_sus_casos(tmp_path, monkeypatch):
    """025:RF-14, RF-17, RF-24 — un proyecto ya calibrado: su año sin sufijo es el de la
    cabecera más reciente (y se dice); 2025 va a «Sin proyecto 2025», 2026 a los de siempre."""
    ws, services = _ws(tmp_path, monkeypatch, calibrado=True)
    plan = services.ajuste_plan(ws, 'P', _maxima_de(2025), '', .01)
    assert (plan['anio_medicion'], plan['anio_casos'], plan['caso']) == (2025, 2025, 'Sin proyecto 2025')
    assert any('2026' in a and '025:RF-17' in a for a in plan['avisos'])
    datos = __import__('json').loads(
        __import__('pathlib').Path(ws.cargas_planes[plan['token']]['path']).read_text(encoding='utf-8'))
    assert datos['anio_casos'] == 2025 and datos['caso'] == 'Sin proyecto 2025'
    assert datos['ultima_calibracion'] is None            # la de 2026 no es de este año
    plan = services.ajuste_plan(ws, 'P', _maxima_de(2026), '', .01)
    assert (plan['anio_casos'], plan['caso']) == (None, 'Sin proyecto')


def test_primer_anio_que_se_calibra_toma_los_casos_sin_anio(tmp_path, monkeypatch):
    """025:RF-17, RF-20 — en un proyecto nuevo, el primer año va a «Sin proyecto»; queda
    registrado y el siguiente año va a los suyos."""
    ws, services = _ws(tmp_path, monkeypatch, calibrado=False)
    plan = services.ajuste_plan(ws, 'P', _maxima_de(2025), '', .01)
    assert plan['anio_casos'] is None
    informe = {'sed': [{'sed': 'S1', 'despues': {'kw': 5.0, 'kvar': 1.0}}],
               'escenarios': [{}], 'cuadrado': True, 'caso': 'Sin proyecto'}
    services._guardar_calibracion(ws, 'P', 'A1', informe, anio_casos=None, anio_medicion=2025)
    assert ws.anios_casos == {'P': 2025} and ws.calibraciones['P']['A1']['anio'] == 2025
    plan = services.ajuste_plan(ws, 'P', _maxima_de(2026), '', .01)
    assert (plan['anio_casos'], plan['caso']) == (2026, 'Sin proyecto 2026')


def test_la_calibracion_de_cada_anio_se_guarda_aparte(tmp_path, monkeypatch):
    """025:RF-20 — la de 2025 en su clave; la de 2026 no cambia y no se compara con ella."""
    ws, services = _ws(tmp_path, monkeypatch, calibrado=True)
    antes = dict(ws.calibraciones['P'])
    informe = {'sed': [{'sed': 'S1', 'despues': {'kw': 7.0, 'kvar': 1.0}}],
               'escenarios': [{}], 'cuadrado': True, 'caso': 'Sin proyecto 2025'}
    services._guardar_calibracion(ws, 'P', 'A1', informe, anio_casos=2025, anio_medicion=2025)
    assert ws.calibraciones['P'] == antes
    assert ws.calibraciones['P@2025']['A1']['sed'] == {'S1': [7.0, 1.0]}
    assert 'P' not in ws.anios_casos
    datos = __import__('json').loads(__import__('pathlib').Path(ws.cargas_planes[
        services.ajuste_plan(ws, 'P', _maxima_de(2025), '', .01)['token']]['path']).read_text(encoding='utf-8'))
    assert datos['ultima_calibracion']['sed'] == {'S1': [7.0, 1.0]}


def test_maximas_de_dos_anios_no_se_calibran_juntas(tmp_path, monkeypatch):
    """025:RF-18 — un año cada vez."""
    ws, services = _ws(tmp_path, monkeypatch, calibrado=True)
    filas = _maxima_de(2025) + [{**_maxima_de(2026)[0], 'medidor': 'L-A2', 'alimentador': 'A2'}]
    with pytest.raises(services.UserError, match='años distintos'):
        services.ajuste_plan(ws, 'P', filas, '', .01)


# =========================================================================== T13: cargas
def test_cargas_y_demandas_van_a_los_casos_del_anio():
    """025:RF-36, 025:RF-38 — con la base calibrada en un año, las demandas en «Sin proyecto
    <año>» y la carga nueva en «Con proyecto <año>»; los casos sin año, intactos."""
    from test_casos_pf import CLIENTES  # noqa: F401 - mismo proyecto de prueba
    from test_casos_pf import cargas_guion
    from test_cargas_pf_guion import _demanda, _nueva, _plan as _plan_cargas

    app, base = _red_calibrada(escenario=True)
    sin_2026, con_2026 = casos_pf.caso(app, 'sin'), casos_pf.caso(app, 'con')
    antes_2026 = (_activas_en(app, sin_2026)[0], _activas_en(app, con_2026)[0])
    plan = {**_plan_cargas(['F1'], demandas=[_demanda('F1_S1', 30.0, 10.0)],
                           nuevas=[_nueva('N1', barra='F1_B2', tension_bt_kv=0.38)]),
            'base': base, 'anio_casos': ANIO}
    informe, rc = cargas_guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    assert informe['casos'] == {'demandas': f'Sin proyecto {ANIO}', 'cargas': f'Con proyecto {ANIO}'}
    carga = informe['cargas'][0]['variacion']
    del_anio = casos_pf.casos_del_proyecto(app, ANIO)
    assert _activas_en(app, del_anio['con'])[0] == [carga]
    assert _activas_en(app, del_anio['sin'])[0] == []
    assert (_activas_en(app, sin_2026)[0], _activas_en(app, con_2026)[0]) == antes_2026
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod'
                and e[0].loc_name == 'F1_S1']
    assert escritas and {e[4].loc_name for e in escritas} <= {f'Sin proyecto {ANIO}',
                                                             f'Con proyecto {ANIO}'}


def test_el_anio_de_las_cargas_sale_de_su_base():
    """025:RF-37 — el año de los casos, del caso en que se grabó la calibración base."""
    from igea_dgs.web import services

    def ajuste(caso):
        return {'project': 'P', 'informes': [{'feeder': 'A1', 'caso': caso, 'cuadrado': True,
                                              'sed': []}]}

    assert services.base_del_ajuste(ajuste(f'Sin proyecto {ANIO}'), 'P')['anio_casos'] == ANIO
    assert services.base_del_ajuste(ajuste('Sin proyecto'), 'P')['anio_casos'] is None


def _activas_por_nombre(app, nombre):
    caso = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre)
    return set(_activas_en(app, caso)[0])


def test_las_obras_del_anio_van_a_sus_casos(monkeypatch):
    """025:RF-41 — con un año, la obra en «Sin proyecto <año>» y en «Con proyecto <año>», que
    se crea como su copia después de la obra; los casos sin año no la tienen."""
    from test_obras_pf_guion import _calibrada, _obra_terna, _plan as _plan_obras, _terna
    from test_obras_pf_guion import guion as obras_guion

    app, alims = _calibrada(random.Random(4))
    monkeypatch.setitem(obras_guion.CONSTRUCTORES, 'terna', _terna)
    assert casos_pf.preparar_sin(app, {'project': 'P', 'feeders': alims, 'anio_casos': ANIO,
                                       'caso_base_sin_verificar': {}})[1] == 0
    plan = {**_plan_obras(alims, obras=[_obra_terna(alims[0], ['Sin proyecto', 'Con proyecto'])]),
            'anio_casos': ANIO}
    informe, rc = obras_guion.aplicar(app, plan)
    assert rc == 0, informe
    obra = informe['obras'][0]['variacion']
    assert obra in _activas_por_nombre(app, f'Sin proyecto {ANIO}')
    assert obra in _activas_por_nombre(app, f'Con proyecto {ANIO}')
    assert casos_pf.rol_de(casos_pf.caso(app, 'con', ANIO)) == f'con@{ANIO}'
    for caso in ('Sin proyecto', 'Con proyecto', 'Caso base'):
        assert obra not in _activas_por_nombre(app, caso), caso


def test_las_cargas_reutilizadas_traen_sus_obras():
    """025:RF-42 — una carga de los casos sin año reutilizada en «Con proyecto <año>» activa
    allí también las obras sobre las que se creó, sin duplicarlas."""
    from test_casos_pf import _variacion, cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, base = _red_calibrada(escenario=True)
    casos_pf.caso(app, 'con').Activate()
    obra = _variacion(app, 'Obra_enlace_F1_F2')                  # activa en «Con proyecto»
    nueva = [_nueva('N1', barra='F1_B2', tension_bt_kv=0.38)]
    primera, rc = cargas_guion.ejecutar(app, {**_plan_cargas(['F1'], nuevas=nueva), 'base': base},
                                        simular=False)
    assert rc == 0, primera
    antes = set(app.carpetas['scheme'].GetContents('*.IntScheme'))
    informe, rc = cargas_guion.ejecutar(
        app, {**_plan_cargas(['F1'], nuevas=nueva), 'base': base, 'anio_casos': ANIO}, simular=False)
    assert rc == 0, informe
    assert informe['reutilizadas'] and informe['obras_activadas'] == [obra.loc_name]
    activas = _activas_por_nombre(app, f'Con proyecto {ANIO}')
    assert obra.loc_name in activas and primera['cargas'][0]['variacion'] in activas
    assert set(app.carpetas['scheme'].GetContents('*.IntScheme')) == antes   # nada duplicado
    assert 'operacion_de_las_obras' in informe                   # 025:RF-42b, también aquí


def test_las_obras_traen_su_operacion_al_caso_del_anio(monkeypatch):
    """025:RF-42b — IN111 + TA225 (2026-10-23): el enlace activo en «Con proyecto <año>» pero
    fuera de servicio en su escenario. Lo que las obras cambiaron en «Con proyecto» respecto de
    «Sin proyecto» se escribe en el escenario del año; lo que el año ya cambió por su cuenta se
    deja y se avisa; lo que no cambiaron las obras no se toca; vuelve el caso del principio."""
    from test_casos_pf import _Caso, _Esc, _Obj

    class App:
        def __init__(self):
            self.escenario = _Esc()
            self.casos = {r: _Caso(self, r) for r in ('sin0', 'con0', 'sin', 'con')}
            self.casos['con'].loc_name = f'Con proyecto {ANIO}'
            self.activo = self.casos['sin']

        def GetActiveStudyCase(self):
            return self.activo

        def GetActiveScenario(self):
            return self.escenario

    app = App()
    enlace, tramo, propio, quieto = _Obj('Enlace'), _Obj('SEC_1'), _Obj('SW_1'), _Obj('SW_2')
    R = 'P/Red/'
    fotos = {
        'sin0': {R + 'SEC_1': (tramo, {'outserv': 0}), R + 'SW_1': (propio, {'on_off': 1}),
                 R + 'SW_2': (quieto, {'on_off': 1})},
        'con0': {R + 'Enlace': (enlace, {'outserv': 0}), R + 'SEC_1': (tramo, {'outserv': 1}),
                 R + 'SW_1': (propio, {'on_off': 0}), R + 'SW_2': (quieto, {'on_off': 1}),
                 R + 'Nuevo': (_Obj('Nuevo'), {'outserv': 0})},
        'sin': {R + 'SEC_1': (tramo, {'outserv': 0}), R + 'SW_1': (propio, {'on_off': 1}),
                R + 'SW_2': (quieto, {'on_off': 1})},
        'con': {R + 'Enlace': (enlace, {'outserv': 1}), R + 'SEC_1': (tramo, {'outserv': 0}),
                R + 'SW_1': (propio, {'on_off': 2}), R + 'SW_2': (quieto, {'on_off': 1})},
    }
    monkeypatch.setattr(casos_pf, '_foto_operacion', lambda a: fotos[a.activo.rol])
    monkeypatch.setattr(casos_pf, 'caso', lambda a, rol, anio=None: a.casos[rol + '0'])
    inicial = app.activo

    out = casos_pf.operacion_de_las_obras(app, {'sin': app.casos['sin'], 'con': app.casos['con']})

    assert enlace.escrito == {'outserv': 0} and tramo.escrito == {'outserv': 1}
    assert propio.escrito == {} and out['conflictos'] == [
        {'objeto': 'SW_1', 'dato': 'on_off', 'con': 0, 'anio': 2}]
    assert quieto.escrito == {} and out['faltan'] == ['Nuevo']
    assert app.escenario.guardado == 1 and app.activo is inicial
    assert all('025:RF-42b' in a for a in out['avisos']) and len(out['avisos']) == 3


def test_dice_que_cargas_no_convergen_juntas(monkeypatch):
    """025:RF-43, 025:RF-48 — si «Con proyecto <año>» no converge con sus cargas nuevas, dice que
    cada una sola sí y cuál basta quitar, probándolas con las demás inactivas; al terminar
    todas siguen activas."""
    from test_casos_pf import cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, base = _red_calibrada(escenario=True)
    real = cargas_guion.flujo_de_carga

    def flujo(app_, *a, **k):
        activas = {v.loc_name for v in (app_.GetActiveNetworkVariations() or [])}
        dos = sum(n.startswith(('Carga_N1_', 'Carga_N2_')) for n in activas)
        return {**real(app_, *a, **k), 'converged': dos < 2}

    monkeypatch.setattr(cargas_guion, 'flujo_de_carga', flujo)
    nuevas = [_nueva('N1', barra='F1_B2', tension_bt_kv=0.38),
              _nueva('N2', barra='F1_B3', tension_bt_kv=0.38)]
    informe, rc = cargas_guion.ejecutar(
        app, {**_plan_cargas(['F1'], nuevas=nuevas), 'base': base, 'anio_casos': ANIO}, simular=False)
    j = informe['no_convergen_juntas']
    assert j['caso'] == f'Con proyecto {ANIO}' and j['solas_que_no_convergen'] == []
    assert len(j['basta_quitar_una_de']) == 2 and len(j['cargas']) == 2
    assert any('cada una sola, sí' in a and '025:RF-44' in a for a in informe['avisos'])
    assert set(j['cargas']) <= _activas_por_nombre(app, f'Con proyecto {ANIO}')


# =========================================================================== T23: «Cargas nuevas»
def _caso_por_nombre(app, nombre):
    return next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre)


def test_cargas_nuevas_es_copia_del_sin_proyecto_con_sus_cargas():
    """025:RF-61, 025:RF-62, 025:RF-63, 025:RF-64 — «Cargas nuevas <año>», copia de «Sin
    proyecto <año>» con un escenario propio copia del suyo y con las variaciones de las cargas
    nuevas, cada una la suya, sin ninguna obra; converge."""
    from test_casos_pf import cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, base = _red_calibrada(escenario=True)
    nuevas = [_nueva('N1', barra='F1_B2', tension_bt_kv=0.38),
              _nueva('N2', barra='F1_B3', tension_bt_kv=0.38)]
    informe, rc = cargas_guion.ejecutar(
        app, {**_plan_cargas(['F1'], nuevas=nuevas), 'base': base, 'anio_casos': ANIO}, simular=False)
    assert rc == 0, informe
    nombre = f'Cargas nuevas {ANIO}'
    caso = _caso_por_nombre(app, nombre)
    assert casos_pf.rol_de(caso) == f'cargas@{ANIO}'
    propias = [c['variacion'] for c in informe['cargas']]
    activas, escenario = _activas_en(app, caso)
    assert sorted(propias) == activas and not any(v.startswith('Obra_') for v in activas)
    sin = casos_pf.caso(app, 'sin', ANIO)
    assert escenario.loc_name == nombre and escenario is not _activas_en(app, sin)[1]
    assert _activas_en(app, sin)[0] == []
    assert informe['cargas_nuevas']['converge'] and informe['cargas_nuevas']['activas'] == propias
    assert len(casos_pf.casos_del_proyecto(app, ANIO)) == 3          # los de la 011, aparte


def test_cargas_nuevas_una_a_una_hasta_donde_converge(monkeypatch):
    """025:RF-65, 025:RF-66 — la carga que ya no deja converger queda inactiva en «Cargas nuevas
    <año>» con su motivo para la web, la siguiente se sigue probando y el caso queda
    convergido; «Con proyecto <año>» sigue con todas."""
    from test_casos_pf import cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, base = _red_calibrada(escenario=True)
    real = cargas_guion.flujo_de_carga

    def flujo(app_, *a, **k):
        activas = {v.loc_name for v in (app_.GetActiveNetworkVariations() or [])}
        n2 = any(n.startswith('Carga_N2_') for n in activas)
        otras = any(n.startswith(('Carga_N1_', 'Carga_N3_')) for n in activas)
        return {**real(app_, *a, **k), 'converged': not (n2 and otras)}

    monkeypatch.setattr(cargas_guion, 'flujo_de_carga', flujo)
    nuevas = [_nueva(f'N{i}', barra=f'F1_B{i + 1}', tension_bt_kv=0.38) for i in (1, 2, 3)]
    informe, rc = cargas_guion.ejecutar(
        app, {**_plan_cargas(['F1'], nuevas=nuevas), 'base': base, 'anio_casos': ANIO}, simular=False)
    d = informe['cargas_nuevas']
    var = {c['sed']: c['variacion'] for c in informe['cargas']}
    assert d['activas'] == [var['N1'], var['N3']] and d['converge'] is True
    (fuera,) = d['no_convergen']
    assert fuera['variacion'] == var['N2'] and fuera['sed'] == 'N2'
    assert 'N2' in fuera['texto'] and 'ya no converge' in fuera['texto']
    assert any('025:RF-66' in a and 'N2' in a for a in informe['avisos'])
    assert _activas_en(app, _caso_por_nombre(app, f'Cargas nuevas {ANIO}'))[0] == sorted([var['N1'], var['N3']])
    assert set(var.values()) <= _activas_por_nombre(app, f'Con proyecto {ANIO}')


def test_cargas_nuevas_sin_las_obras_de_con_proyecto():
    """025:RF-64 — las obras que «Con proyecto <año>» activa para las cargas reutilizadas
    (RF-42) no pasan a «Cargas nuevas <año>»."""
    from test_casos_pf import _variacion, cargas_guion
    from test_cargas_pf_guion import _nueva, _plan as _plan_cargas

    app, base = _red_calibrada(escenario=True)
    casos_pf.caso(app, 'con').Activate()
    obra = _variacion(app, 'Obra_enlace_F1_F2')
    nueva = [_nueva('N1', barra='F1_B2', tension_bt_kv=0.38)]
    assert cargas_guion.ejecutar(app, {**_plan_cargas(['F1'], nuevas=nueva), 'base': base},
                                 simular=False)[1] == 0
    informe, rc = cargas_guion.ejecutar(
        app, {**_plan_cargas(['F1'], nuevas=nueva), 'base': base, 'anio_casos': ANIO}, simular=False)
    assert rc == 0, informe
    assert obra.loc_name in _activas_por_nombre(app, f'Con proyecto {ANIO}')
    activas = _activas_por_nombre(app, f'Cargas nuevas {ANIO}')
    assert obra.loc_name not in activas and informe['reutilizadas'][0]['variacion'] in activas


# =========================================================================== T15: escalera
def _tipo_linea(nombre, kv, ka, aereo=True, origen='proyecto'):
    return {'nombre': nombre, 'clase': 'TypLne', 'origen': origen, 'proyecto': '',
            'datos': {'uline': kv, 'sline': ka, 'cohl_': 1 if aereo else 0}}


def _perfil_escalera(costos):
    return {'escalera': {'cumplimiento': 0.95, 'sorteos': 20, 'semilla': 1, 'tolerancia_pu': 0.005,
                         'tolerancia_carga_pct': 1, 'max_variantes': 100, 'costos_unitarios': costos},
            'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
            'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}


def _escalera_falsa(tmp_path, monkeypatch, evaluar, costos, *, alimentadores=('F1',), activa=True):
    """El servicio de la escalera con DIgSILENT, los libros y el perfil sustituidos."""
    from datetime import datetime, timedelta

    from igea_dgs import perfil_empresa
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    monkeypatch.setattr(perfil_empresa, 'datos_perfil', lambda: _perfil_escalera(costos))
    monkeypatch.setattr(perfil_empresa, 'bancos_kvar_por_tension', lambda _d: {10.0: 300})
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: {'informes': [
        {'feeder': f, 'caso': f'Sin proyecto {ANIO}', 'objetivo': {'kw': 1000.0, 'medidor': 'M1'}}
        for f in alimentadores]})
    t0 = datetime(ANIO, 1, 1)
    monkeypatch.setattr(services, '_curva_del_anio', lambda *_a, **_k: {
        f: [(t0 + timedelta(hours=h), 500.0 + (h % 24) * 20) for h in range(24 * 30)] for f in alimentadores})
    monkeypatch.setattr(services, 'obras_bibliotecas', lambda *a, **k: {'informe': {
        'alimentadores': {f: {'kv': 10.0} for f in alimentadores}, 'tipos': [_tipo_linea('AAAC 240', 10, 0.55)]}})
    monkeypatch.setattr(services, '_cargas_nuevas_aplicadas', lambda *_a: [
        {'sed': f'Q{f}', 'alimentador': f, 'barra': f'{f}_B4', 'criterio': 'barra de la troncal más cercana'}
        for f in alimentadores])
    # El contexto firmado lleva los alimentadores del plan, uno por alimentador.
    monkeypatch.setattr(services, 'native_action_context', lambda ws_, p_, feeders, accion: {'feeders': list(feeders)})
    planes = []

    def guion(ws_, ctx, script, plan, *, nombre, args=(), **_k):
        assert plan['native_action_context']['feeders'] == plan['feeders'], 'contexto de otro alimentador'
        planes.append((args, plan))
        if '--escalera-datos' in args:
            (f,) = plan['feeders']
            return 0, {'alimentadores': {f: {
                'troncal': [{'nombre': f'T{i}', 'largo_m': 1000.0, 'corriente_a': 100.0} for i in range(3)],
                'fuera_desde': None, 'indices': {f'{f}_B4': 2}}}}, None
        return 0, {'variantes': [evaluar(v['nombre']) for v in plan['variantes']]}, None

    monkeypatch.setattr(services, '_guion_pf', guion)
    aplicadas = []

    def ejecutar(ws_, ctx, project, feeders, ids, otro, *, simular, anio_casos=None, apartar_cargas_de=None):
        aplicadas.append(([o['clase'] for o in ws_.obras if o['id'] in ids], otro, anio_casos))
        ejecutar.apartadas.append(list(apartar_cargas_de or []))
        return {'informe': {'obras': [{'variacion': 'Obra_x',
                                       'casos_activos': [f'Con proyecto {ANIO}'] if activa else []}]}}

    ejecutar.apartadas = []

    monkeypatch.setattr(services, 'obras_ejecutar', ejecutar)

    class Ctx:
        def log(self, *_a):
            pass

        def check_cancel(self):
            pass

    return services, ws, Ctx(), planes, aplicadas, ejecutar.apartadas


def test_la_escalera_elige_la_mas_barata_que_cumple_y_aplica_solo_esa(tmp_path, monkeypatch):
    """025:RF-49, 025:RF-53, 025:RF-54, 025:RF-55, 025:RF-52b — se miden todas las variantes con los
    sorteos de la curva del año; gana la de menor costo anual entre las que cumplen y solo esa se
    aplica, en «Con proyecto» del año; la que cumple sin costo y la que no cumple dicen por qué."""
    def evaluar(nombre):
        cumple = not nombre.startswith('bancos') and '+' not in nombre
        return {'nombre': nombre, 'maxima': cumple, 'fraccion': 1.0 if cumple else None,
                'perdidas_kw': 10.0, 'motivos': [] if cumple else ['no converge']}

    services, ws, ctx, planes, aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'bancos': 9000, 'nueva_terna': 40000, 'cambio_seccion': 30000})
    r = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO)
    assert all(p['apartar_cargas_de'] == [] for _a, p in planes)        # 025:RF-69, solo F1
    (f1,) = r['alimentadores']
    assert f1['elegida'].startswith('sección') and r['sorteos'] == 20
    assert aplicadas == [(['seccion'], 'IGEA_Biblioteca_tipos', ANIO)]
    (_args, ev), = [x for x in planes if '--evaluar' in x[0]]
    assert len(ev['sorteos']) == 20 and ev['anio_casos'] == ANIO and ev['barras_cargas'] == ['F1_B4']
    motivos = {t['nombre']: t['motivo'] for t in f1['tabla']}
    assert any(n.startswith('regulador') and 'sin costo' in m for n, m in motivos.items())
    assert any(n.startswith('bancos') and 'no cumple con la máxima' in m for n, m in motivos.items())
    assert any(n.startswith('terna') and 'cuesta más' in m for n, m in motivos.items())


def test_la_escalera_sin_ninguna_que_cumpla_no_aplica_nada(tmp_path, monkeypatch):
    """025:RF-56 — si ninguna variante cumple, no se aplica ninguna y se dice la más cercana."""
    def evaluar(nombre):
        return {'nombre': nombre, 'maxima': nombre.startswith('terna'), 'fraccion': 0.5,
                'perdidas_kw': None, 'motivos': ['no converge']}

    services, ws, ctx, _planes, aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'nueva_terna': 40000})
    (f1,) = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO)['alimentadores']
    assert f1['elegida'] is None and f1['mas_cercana'].startswith('terna') and aplicadas == []
    assert any('025:RF-56' in a for a in f1['avisos'])


def test_la_evaluacion_terminada_con_el_mismo_plan_se_reutiliza(tmp_path):
    """025:RF-73 — una evaluación terminada con el mismo plan (salvo el contexto firmado) se
    reutiliza; con otros sorteos, con error o de hace más de 24 h, no."""
    import json
    import os
    import time

    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    plan = {'project': 'P', 'feeders': ['F1'], 'sorteos': [{'F1': 0.5}], 'apartar_cargas_de': ['F2'],
            'native_action_context': {'firma': 'a'}}
    informe = {'variantes': [{'nombre': 'terna', 'maxima': True}]}

    def guardar(nombre, p, datos, edad_s=0.0):
        (ws.plans_dir / nombre).write_text(json.dumps(p), encoding='utf-8')
        ruta = ws.out_dir / nombre
        ruta.write_text(json.dumps(datos), encoding='utf-8')
        os.utime(ruta, (time.time() - edad_s, time.time() - edad_s))

    guardar('escalera_evaluar_a.json', plan, informe)
    assert services._evaluacion_hecha(ws, {**plan, 'native_action_context': {'firma': 'b'}}) == informe
    assert services._evaluacion_hecha(ws, {**plan, 'sorteos': [{'F1': 0.6}]}) is None
    assert services._evaluacion_hecha(ws, {**plan, 'apartar_cargas_de': []}) is None
    guardar('escalera_evaluar_a.json', plan, {'error': 'no converge', 'variantes': []})
    assert services._evaluacion_hecha(ws, plan) is None
    guardar('escalera_evaluar_a.json', plan, informe, edad_s=services.VIGENCIA_EVALUACION_S + 60)
    assert services._evaluacion_hecha(ws, plan) is None


def test_la_escalera_no_vuelve_a_medir_lo_ya_evaluado(tmp_path, monkeypatch):
    """025:RF-73 — con la evaluación de F1 ya hecha, el servicio no llama al guion para medirla."""
    def evaluar(nombre):
        cumple = nombre.startswith('terna') and '+' not in nombre
        return {'nombre': nombre, 'maxima': cumple, 'fraccion': 1.0 if cumple else None,
                'perdidas_kw': 10.0, 'motivos': [] if cumple else ['no converge']}

    services, ws, ctx, planes, aplicadas, _apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'nueva_terna': 40000})
    monkeypatch.setattr(services, '_evaluacion_hecha',
                        lambda ws_, plan: {'variantes': [evaluar(v['nombre']) for v in plan['variantes']]})
    (f1,) = services.obras_escalera(ws, ctx, 'P', ['F1'], anio_casos=ANIO)['alimentadores']
    assert not [a for a, _p in planes if '--evaluar' in a]
    assert f1['elegida'].startswith('terna') and len(aplicadas) == 1


@pytest.mark.parametrize('activa', [True, False])
def test_la_elegida_se_aplica_con_las_mismas_cargas_apartadas_y_solo_activa_resuelve(
        tmp_path, monkeypatch, activa):
    """025:RF-69 — la elegida de F1 se aplica con las cargas nuevas de F2 apartadas, como se
    evaluó; F1 cuenta como resuelto para F2 solo si su obra quedó activa en «Con proyecto»
    (Pisco, 2026-10-24: la de SI213 quedó inactiva y PA217 se evaluó como si estuviera resuelto)."""
    def evaluar(nombre):
        cumple = nombre.startswith('terna') and '+' not in nombre
        return {'nombre': nombre, 'maxima': cumple, 'fraccion': 1.0 if cumple else None,
                'perdidas_kw': 10.0, 'motivos': [] if cumple else ['no converge']}

    services, ws, ctx, planes, _aplicadas, apartadas = _escalera_falsa(
        tmp_path, monkeypatch, evaluar, {'nueva_terna': 40000}, alimentadores=('F1', 'F2'), activa=activa)
    r = services.obras_escalera(ws, ctx, 'P', ['F1', 'F2'], anio_casos=ANIO)
    assert apartadas[0] == ['F2']
    de_f2 = [p for _a, p in planes if p['feeders'] == ['F2']]
    assert all(p['apartar_cargas_de'] == ([] if activa else ['F1']) for p in de_f2)
    f1 = r['alimentadores'][0]
    assert any('025:RF-69' in a for a in f1['avisos']) is (not activa)

def test_la_base_de_las_cargas_se_encuentra_en_otra_ejecucion(tmp_path):
    """025:RF-37 (007:RF-40) — la calibración de 2025 quedó en la ejecución anterior; al
    volver a cargar la fuente hay otra, y la base pedida por su token se sigue encontrando.
    Sin token también (2026-10-24: tras reiniciar la web, el paso de cargas de Pisco no
    encontraba su base); si la ejecución activa tiene una del proyecto, manda esa."""
    import json
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    vieja = tmp_path / 'runs' / 'r1' / 'salida'
    vieja.mkdir(parents=True)
    (vieja / 'ajuste_cabecera_aplicacion_tok123_1.json').write_text(json.dumps(
        {'project': 'P', 'feeder': 'A1', 'caso': f'Sin proyecto {ANIO}'}), encoding='utf-8')
    ws.active_run_id = 'r2'
    (tmp_path / 'runs' / 'r2' / 'salida').mkdir(parents=True)
    hallado = services.ajuste_aplicado_en_disco(ws, None, 'tok123')
    assert hallado and hallado['id'] == 'disco:tok123' and hallado['feeders'] == ['A1']
    assert services.ajuste_aplicado_en_disco(ws, 'P')['id'] == 'disco:tok123'
    assert services.ajuste_aplicado_en_disco(ws, 'OTRO') is None
    (tmp_path / 'runs' / 'r2' / 'salida' / 'ajuste_cabecera_aplicacion_nuevo_1.json').write_text(
        json.dumps({'project': 'P', 'feeder': 'A1', 'caso': 'Sin proyecto'}), encoding='utf-8')
    assert services.ajuste_aplicado_en_disco(ws, 'P')['id'] == 'disco:nuevo'


def test_la_base_de_un_solo_alimentador_se_encuentra_por_su_token(tmp_path):
    """025:RF-37 (007:RF-40) — la calibración de un proyecto de un solo alimentador deja su
    informe sin ``_n`` (``…_<token>.json``); pedida por su token, en la ejecución activa o en
    otra, se encuentra igual (CA101, 2026-10-24: «No se encuentra el ajuste de la base»)."""
    import json
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    activa = tmp_path / 'runs' / 'r1' / 'salida'
    activa.mkdir(parents=True)
    ws.active_run_id = 'r1'
    (activa / 'ajuste_cabecera_aplicacion_tok1.json').write_text(json.dumps(
        {'project': 'P', 'feeder': 'CA101', 'caso': 'Sin proyecto'}), encoding='utf-8')
    (activa / 'ajuste_cabecera_aplicacion_tok10_1.json').write_text(json.dumps(
        {'project': 'P', 'feeder': 'OTRO', 'caso': 'Sin proyecto'}), encoding='utf-8')
    hallado = services.ajuste_aplicado_en_disco(ws, None, 'tok1')
    assert hallado and hallado['id'] == 'disco:tok1' and hallado['feeders'] == ['CA101']
    ws.active_run_id = 'r2'
    (tmp_path / 'runs' / 'r2' / 'salida').mkdir(parents=True)
    hallado = services.ajuste_aplicado_en_disco(ws, None, 'tok1')
    assert hallado and hallado['feeders'] == ['CA101']


def test_volver_a_calibrar_el_anio_reutiliza_sus_casos():
    """025:RF-18 (011:RF-6) — la segunda calibración del año no crea casos nuevos."""
    app, _base = _red_calibrada()
    plan = {**_plan_ajuste(), 'anio_casos': ANIO}
    assert ajuste_pf.ejecutar(app, plan)[1] == 0
    antes = _nombres(app)
    assert ajuste_pf.ejecutar(app, plan)[1] == 0
    assert _nombres(app) == antes
