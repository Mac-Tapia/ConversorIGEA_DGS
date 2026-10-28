"""Spec 024, T13: ``tools/pide_pf.py`` contra ``fake_pf`` (cada año del horizonte escalado)."""
from __future__ import annotations

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo

LIM = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100,
       'transformador_max_pct': 80}


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('pide_pf.py', 'pide_pf_guion', tools_en_path=True)


def _app():
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True)
    app.carpetas['study'].CreateObject('IntCase', 'Sin proyecto')
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    app.creados.clear()
    return app


def _plan(**extra):
    plan = {'project': 'P', 'feeders': ['F1'], 'case': 'sin_proyecto', 'tasa': 0.05,
            'anios': [0, 4, 8, 20], 'limites': LIM,
            'native_action_context': contexto_nativo('P', ['F1'], 'pide')}
    plan.update(extra)
    return plan


def test_cada_anio_con_la_demanda_escalada(guion):
    """024:RF-53 — cada año del horizonte se calcula en DIgSILENT con la demanda de ese año,
    y el factor de escala vuelve a su valor."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert [a['anio'] for a in informe['anios']] == [0, 4, 8, 20]
    assert informe['anios'][3]['factor'] == pytest.approx(1.05 ** 20)
    minimas = [a['vm_min'] for a in informe['anios']]
    assert minimas == sorted(minimas, reverse=True)
    assert app.ldf.scLoadFac == 100.0 and app.creados == []


def test_sin_tasa_no_se_supone(guion):
    """024:RF-51 — sin tasa de crecimiento no se inventa una: código 2 y el motivo."""
    informe, rc = guion.ejecutar(_app(), _plan(tasa=None))
    assert rc == 2 and 'tasa' in informe['error']


def test_el_anio_que_no_converge_se_dice(guion):
    """024:RF-53 — si con la demanda de un año no converge, ese año lo dice y se sigue."""
    app = _app()
    app.ldf.limite = 0.2
    informe, rc = guion.ejecutar(app, _plan(anios=[0, 20]))
    assert rc == 0
    assert informe['anios'][0]['converge'] and not informe['anios'][1]['converge']
    assert app.ldf.scLoadFac == 100.0


def test_tasa_por_alimentador_y_cargas_restituidas(guion):
    """029:RF-4 — cada alimentador escala sus cargas con su propia tasa en cada año y, al
    terminar, cada carga vuelve a su factor; el del flujo no se toca."""
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=3, bt=True, flujo=True)
    app.carpetas['study'].CreateObject('IntCase', 'Sin proyecto')
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    elms = {f.loc_name: f for f in app.proyecto.GetContents('*.ElmFeeder', 1)}
    for c in elms['F1'].GetObjs('ElmLod'):
        c.scale0 = 0.8
    vistos = []
    original = app.ldf.Execute

    def medir():
        vistos.append({a: [round(c.scale0, 6) for c in e.GetObjs('ElmLod')] for a, e in elms.items()})
        return original()

    object.__setattr__(app.ldf, 'Execute', medir)
    informe, rc = guion.ejecutar(app, _plan(feeders=['F1', 'F2'], anios=[0, 4],
                                            tasa_por_alimentador={'F1': 0.10, 'F2': 0.0}))
    assert rc == 0, informe
    ultimo = vistos[-1]
    assert ultimo['F1'] == [pytest.approx(0.8 * 1.1 ** 4)] * 3 and ultimo['F2'] == [1.0] * 3
    assert all(c.scale0 == pytest.approx(0.8) for c in elms['F1'].GetObjs('ElmLod'))
    assert app.ldf.scLoadFac == 100.0 and informe['tasa_por_alimentador'] == {'F1': 0.10, 'F2': 0.0}


def test_anios_en_carpetas_con_sus_casos_y_escenarios(guion, monkeypatch):
    """030:RF-1 / 030:RF-2 / 030:RF-3 / 030:RF-4 / 030:RF-5 / 030:RF-6 / 030:RF-7 / 030:RF-8 —
    «PIDE/Año NN» con «Sin proyecto» y «Con proyecto» copiados (sin «Cargas nuevas», que no hay),
    cada uno con su escenario y la demanda del año; renovar no duplica y los casos del proyecto
    quedan como estaban."""
    casos_pf = cargar_herramienta('casos_pf.py', tools_en_path=True)
    monkeypatch.setattr(casos_pf, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=2, bt=True, flujo=True, escenario=True)
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    base = {'variaciones': [], 'feeders': ['F1', 'F2'], 'ajustes': [], 'excluidos': []}
    plan_casos = {'project': 'P', 'folder': None, 'feeders': ['F1', 'F2'], 'base': base, 'caso_base_sin_verificar': {}}
    assert casos_pf.preparar_sin(app, plan_casos)[1] == 0 and casos_pf.preparar_con(app, plan_casos)[1] == 0
    sin = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Sin proyecto')
    sin.Activate()
    elms = {f.loc_name: f for f in app.proyecto.GetContents('*.ElmFeeder', 1)}
    antes = [c.scale0 for c in elms['F1'].GetObjs('ElmLod')]
    plan = _plan(feeders=['F1', 'F2'], anios=[0, 4], casos_por_anio=True, tasa_por_alimentador={'F1': 0.10})
    for _ in range(2):                                                    # RF-5: dos corridas
        informe, rc = guion.ejecutar(app, plan)
        assert rc == 0, informe
    carpeta = next(x for x in app.carpetas['study'].GetContents('*.IntFolder') if x.loc_name == 'PIDE')
    anios = {x.loc_name: x for x in carpeta.GetContents('*.IntFolder')}
    assert set(anios) == {'Año 00', 'Año 04'}
    assert sorted(c.loc_name for c in anios['Año 04'].GetContents('*.IntCase')) == ['Con proyecto', 'Sin proyecto']
    esc = next(x for x in app.carpetas['scen'].GetContents('*.IntFolder') if x.loc_name == 'PIDE')
    assert sorted(e.loc_name for e in next(x for x in esc.GetContents('*.IntFolder') if x.loc_name == 'Año 04')
                  .GetContents('*.IntScenario')) == ['Con proyecto', 'Sin proyecto']
    assert informe['anios'][1]['casos']['sin'] == {'caso': 'PIDE/Año 04/Sin proyecto',
                                                  'escenario': 'PIDE/Año 04/Sin proyecto'}
    assert casos_pf.rol_de(anios['Año 04'].GetContents('*.IntCase')[0]).startswith('pide_04_')
    assert app.GetActiveStudyCase() is sin
    assert [c.scale0 for c in elms['F1'].GetObjs('ElmLod')] == pytest.approx(antes)
    assert len(casos_pf.casos_del_proyecto(app)) == 3, 'los casos del proyecto siguen siendo los suyos'
    # La demanda del año 04 se escribió en el escenario del año, no en el del proyecto.
    esc_04 = {id(e) for x in esc.GetContents('*.IntFolder') if x.loc_name == 'Año 04' for e in x.GetContents('*.IntScenario')}
    escritas = [(v, id(s)) for o, attr, v, _etapa, s in app.escrituras if attr == 'scale0' and s is not None]
    assert any(v == pytest.approx(1.1 ** 4) and s in esc_04 for v, s in escritas)


class _Envoltorio:
    """Como la API de DIgSILENT 2024: un objeto de Python nuevo en cada acceso al mismo elemento
    (``clave_pf`` lo documenta); ``id()`` no lo reconoce y Python reutiliza los identificadores."""

    def __init__(self, obj):
        object.__setattr__(self, '_o', obj)

    def __getattr__(self, k):
        return getattr(self._o, k)

    def __setattr__(self, k, v):
        setattr(self._o, k, v)


def test_restituye_cada_carga_aunque_la_api_de_objetos_nuevos(guion, monkeypatch):
    """029:RF-4 / 030:RF-6 — con un objeto nuevo por acceso, como en DIgSILENT, cada carga vuelve a
    su factor: con ``id()`` se mezclaban y «Sin proyecto» de Chincha quedó alterado (2026-10-28)."""
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=3, bt=True, flujo=True)
    app.carpetas['study'].CreateObject('IntCase', 'Sin proyecto')
    object.__setattr__(app.ldf, 'scLoadFac', 100.0)
    elms = {f.loc_name: f for f in app.proyecto.GetContents('*.ElmFeeder', 1)}
    for i, c in enumerate(c for e in elms.values() for c in e.GetObjs('ElmLod')):
        c.scale0 = 0.1 * (i + 1)
    antes = {c.loc_name: c.scale0 for e in elms.values() for c in e.GetObjs('ElmLod')}
    for e in elms.values():
        original = e.GetObjs
        object.__setattr__(e, 'GetObjs', lambda clase, o=original: [_Envoltorio(x) for x in o(clase)])
    informe, rc = guion.ejecutar(app, _plan(feeders=['F1', 'F2'], anios=[0, 4, 8],
                                            tasa_por_alimentador={'F1': 0.10}))
    assert rc == 0, informe
    assert {c.loc_name: c.scale0 for e in elms.values() for c in e.GetObjs('ElmLod')} == pytest.approx(antes)


def test_fraccion_acumulada_por_anio(guion):
    """030:RF-9 / 030:RF-11 / 030:RF-15 — la carga nueva lleva lo acumulado de sus partes hasta cada
    año, 0 antes de la primera, y el total desde la última, sin crecer."""
    perfil = [[4, 1 / 3], [8, 2 / 3], [12, 1.0]]
    assert [round(guion.fraccion_en(perfil, a), 4) for a in (0, 4, 6, 8, 12, 20)] == [0, 0.3333, 0.3333, 0.6667, 1, 1]
    assert guion.fraccion_en(None, 0) == 1.0 and guion.fraccion_en([[8, 1.0]], 4) == 0.0
