"""Spec 011, T4 y T5: los tres casos de estudio en DIgSILENT (``tools/casos_pf.py``).

Con el doble ``fake_pf``, en el que las variaciones activas y el escenario son de cada
caso (T2). El número de alimentadores, los que se marcan y los que tienen cargas nuevas
se sortean.
"""
from __future__ import annotations

import random

import pytest

import fake_pf
from apoyo import cargar_herramienta

casos_pf = cargar_herramienta('casos_pf.py', tools_en_path=True)

SEMILLAS = (3, 17, 42, 88)
STAMP = '20261011_100000'


def _variacion(app, nombre):
    """Variación con su etapa, como la dejan las specs 006 y 007 (activa en el caso activo)."""
    v = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    v.NewStage(f'Etapa_{nombre}', 0, 1)
    app.grabando = None
    return v


def _escenario_red(rng, *, escenario=False, cargas=True, anteriores=False):
    """Proyecto calibrado: un ajuste por alimentador marcado, demandas y cargas nuevas.

    Lo deja como lo dejan las specs 006 a 008: todo activo en el caso en que se trabajó.
    """
    n = rng.randint(1, 5)
    alims = tuple(sorted({f'AL{rng.randint(100, 999)}' for _ in range(n)}))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=2, escenario=escenario)
    viejos = {}
    if anteriores:
        for f in alims:
            viejos[f] = _variacion(app, f'Ajuste_{f}_20260901_080000')
    ajustes = [{'feeder': f, 'variacion': _variacion(app, f'Ajuste_{f}_{STAMP}').loc_name,
                'cuadrado': True, 'desvio': {'kw': 0.002, 'kvar': -0.004}} for f in alims]
    demandas = _variacion(app, f'Demandas_{STAMP}')
    con_cargas = [f for f in alims if cargas and rng.random() < 0.7] or ([alims[0]] if cargas else [])
    cargas_v = [_variacion(app, f'Carga_S{i}_{f}_{STAMP}') for i, f in enumerate(con_cargas)]
    base = {'variaciones': [a['variacion'] for a in ajustes], 'feeders': list(alims),
            'ajustes': ajustes, 'excluidos': []}
    plan = {'project': 'P', 'folder': None, 'feeders': list(alims), 'base': base,
            'variacion_demandas': demandas.loc_name}
    return app, plan, {'demandas': demandas, 'cargas': cargas_v, 'viejos': viejos}


@pytest.fixture(autouse=True)
def _sin_activar_proyecto(monkeypatch):
    """El doble ya tiene el proyecto activo: no hay carpeta de usuario que recorrer."""
    monkeypatch.setattr(casos_pf, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)


def _caso(app, nombre):
    return next((c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre), None)


def _activas_en(app, caso):
    previo = app.caso
    caso.Activate()
    nombres = sorted(v.loc_name for v in app.GetActiveNetworkVariations())
    escenario = app.GetActiveScenario()
    previo.Activate()
    return nombres, escenario


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tres_casos_con_sus_variaciones(semilla):
    """011:RF-1, 011:RF-2, 011:RF-3, 011:RF-4, 011:RF-5, 011:RF-7, 011:RF-8 — el original pasa
    a «Caso base» sin calibrar; «Sin proyecto» con el ajuste y las demandas; «Con
    proyecto» además con todas las cargas nuevas."""
    app, plan, v = _escenario_red(random.Random(semilla))
    original = app.caso
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0, informe
    base, sin, con = (_caso(app, n) for n in casos_pf.NOMBRES.values())
    assert base is original and None not in (sin, con)
    assert len(app.carpetas['study'].GetContents('*.IntCase')) == 3
    calibrada = sorted(plan['base']['variaciones'] + [v['demandas'].loc_name])
    assert _activas_en(app, base)[0] == []
    assert _activas_en(app, sin)[0] == calibrada
    assert _activas_en(app, con)[0] == sorted(calibrada + [c.loc_name for c in v['cargas']])
    assert informe['casos']['con']['estudiable'] is True


def test_reutiliza_los_casos_y_suma_las_cargas_nuevas():
    """011:RF-6 — la segunda vez no crea casos: solo cambia qué variaciones tienen activas."""
    app, plan, _v = _escenario_red(random.Random(5))
    casos_pf.preparar(app, plan)
    antes = {c.loc_name: c for c in app.carpetas['study'].GetContents('*.IntCase')}
    nueva = _variacion(app, f"Carga_SX_{plan['feeders'][0]}_{STAMP}")
    nueva.Deactivate()
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0
    despues = {c.loc_name: c for c in app.carpetas['study'].GetContents('*.IntCase')}
    assert despues == antes
    assert informe['casos']['sin']['creado'] is False and informe['casos']['con']['creado'] is False
    assert nueva.loc_name in _activas_en(app, despues['Con proyecto'])[0]
    assert nueva.loc_name not in _activas_en(app, despues['Sin proyecto'])[0]


def test_sin_cargas_nuevas_no_se_estudia_con_proyecto():
    """011:RF-9 — sin ninguna carga nueva, «Con proyecto» no se estudia y se dice."""
    app, plan, _v = _escenario_red(random.Random(9), cargas=False)
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0
    assert informe['casos']['con']['estudiable'] is False
    assert any('cargas nuevas' in a for a in informe['avisos'])


def test_un_caso_ajeno_con_el_mismo_nombre_no_se_toca():
    """011:RF-10 — un «Sin proyecto» que no creó el sistema: no se toca nada y se pide renombrarlo."""
    app, plan, _v = _escenario_red(random.Random(10))
    ajeno = app.carpetas['study'].CreateObject('IntCase', 'Sin proyecto')
    original = app.caso
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 2 and 'Sin proyecto' in informe['error'] and 'renómbrelo' in informe['error']
    assert original.loc_name == 'Caso' and _caso(app, 'Con proyecto') is None
    assert ajeno.loc_name == 'Sin proyecto'


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_deja_activo_el_caso_del_principio(semilla):
    """011:RF-11 — al terminar, el caso activo es el que lo era al empezar."""
    app, plan, _v = _escenario_red(random.Random(semilla))
    casos_pf.preparar(app, plan)
    sin = _caso(app, 'Sin proyecto')
    sin.Activate()
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0 and app.caso is sin


def test_sin_ajuste_no_se_prepara():
    """011:RF-12, 011:RF-13 — sin un ajuste aplicado no hay base: primero hay que calibrar."""
    app, plan, _v = _escenario_red(random.Random(12))
    for base in (None, {'variaciones': []}):
        informe, codigo = casos_pf.preparar(app, {**plan, 'base': base})
        assert codigo == 2 and 'calibr' in informe['error']
    assert _caso(app, 'Sin proyecto') is None and app.caso.loc_name == 'Caso'


def test_alimentador_sin_ajuste_o_sin_cuadrar():
    """011:RF-14, 011:RF-15 — el que no tiene ajuste queda fuera; el que no cuadró, con aviso."""
    app, plan, _v = _escenario_red(random.Random(14))
    plan['feeders'] = plan['feeders'] + ['AL_SIN_AJUSTE']
    plan['base']['ajustes'][0]['cuadrado'] = False
    plan['base']['ajustes'][0]['desvio'] = {'kw': 0.031, 'kvar': -0.02}
    plan['base']['excluidos'] = [{'feeder': 'AL_FALLO', 'motivo': 'el flujo no converge'}]
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0
    fuera = {x['feeder']: x['motivo'] for x in informe['excluidos']}
    assert 'AL_SIN_AJUSTE' in fuera and fuera['AL_FALLO'] == 'el flujo no converge'
    primero = plan['base']['ajustes'][0]['feeder']
    assert any(primero in a and '3,1 %' in a for a in informe['avisos'])
    assert primero in informe['feeders']


def test_variacion_de_la_base_borrada():
    """011:RF-16 — si una variación de la base ya no está, no se prepara nada y se nombra."""
    app, plan, v = _escenario_red(random.Random(16))
    v['demandas'].Delete()
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 2 and v['demandas'].loc_name in informe['error']
    assert _caso(app, 'Sin proyecto') is None


def test_un_escenario_por_caso():
    """011:RF-46, 011:RF-47 — cada caso con su escenario; las copias, copia del de su origen."""
    app, plan, _v = _escenario_red(random.Random(46), escenario=True)
    original = app.GetActiveScenario()
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0
    esc = {n: _activas_en(app, _caso(app, n))[1] for n in casos_pf.NOMBRES.values()}
    assert esc['Caso base'] is original
    assert esc['Sin proyecto'].loc_name == 'Sin proyecto' and esc['Con proyecto'].loc_name == 'Con proyecto'
    assert len({id(e) for e in esc.values()}) == 3
    assert informe['casos']['sin']['escenario'] == 'Sin proyecto'


def test_sin_escenario_se_crea_uno_por_caso():
    """011:RF-48 — si el original no tiene escenario, cada caso recibe uno con su nombre."""
    app, plan, _v = _escenario_red(random.Random(48))
    casos_pf.preparar(app, plan)
    for n in casos_pf.NOMBRES.values():
        assert _activas_en(app, _caso(app, n))[1].loc_name == n


def test_los_ajustes_anteriores_se_desactivan_sin_borrar():
    """011:RF-50 — solo el último ajuste de cada alimentador queda activo; los demás, guardados."""
    app, plan, v = _escenario_red(random.Random(50), anteriores=True)
    casos_pf.preparar(app, plan)
    for n in ('Sin proyecto', 'Con proyecto'):
        activas = _activas_en(app, _caso(app, n))[0]
        assert not any(viejo.loc_name in activas for viejo in v['viejos'].values())
    todas = {x.loc_name for x in app.carpetas['scheme'].GetContents('*.IntScheme')}
    assert {viejo.loc_name for viejo in v['viejos'].values()} <= todas


# =========================================================================== T5
# El ajuste y las cargas, una vez que existen los tres casos (RF-51 a RF-55), y la marca
# de fijas y escaladas del ajuste (RF-18, RF-19).
from test_ajuste_cabecera_guion import _plan as _plan_ajuste  # noqa: E402
from test_cargas_pf_guion import _demanda, _nueva, _plan as _plan_cargas  # noqa: E402

ajuste_pf = cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_011', tools_en_path=True)
cargas_guion = cargar_herramienta('cargas_pf.py', 'cargas_011', tools_en_path=True)

AJUSTE_VIEJO = 'Ajuste_F1_20261001_080000'
CLIENTES = [{'codigo': '11', 'sed': 'f1_s2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]


def _red_calibrada(*, escenario=False, preparar=True):
    """F1 y F2 con barras de baja y flujo; F1 ya ajustado una vez y los tres casos hechos."""
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True,
                           escenario=escenario)
    _variacion(app, AJUSTE_VIEJO)
    base = {'variaciones': [AJUSTE_VIEJO], 'feeders': ['F1'], 'excluidos': [],
            'ajustes': [{'feeder': 'F1', 'variacion': AJUSTE_VIEJO, 'cuadrado': True}]}
    if preparar:
        informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': ['F1'], 'base': base})
        assert codigo == 0, informe
    app.escrituras.clear()
    return app, base


def _carga_de(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == nombre)


def test_el_ajuste_marca_fijas_y_escalables_en_su_variacion():
    """011:RF-18, 011:RF-19 — clientes importantes no escalan; las repartidas, sí; en la variación."""
    app, _base = _red_calibrada(preparar=False)
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste(clientes=CLIENTES))
    assert rc == 0, informe
    marcas = {o.loc_name: o.i_scale for o in app.proyecto.GetContents('*.ElmLod', 1)
              if hasattr(o, 'i_scale')}
    assert marcas.pop('F1_S2') == 0
    assert marcas and set(marcas.values()) == {1} and all(n.startswith('F1_') for n in marcas)
    escritas = [e for e in app.escrituras if e[1] == 'i_scale']
    assert escritas and all(e[3] is not None and e[3]._padre.loc_name == informe['variacion']
                            for e in escritas)


def test_con_tres_casos_el_ajuste_va_a_sin_proyecto():
    """011:RF-51, 011:RF-53, 011:RF-54 — el ajuste nuevo, en «Sin proyecto» y activo también en
    «Con proyecto»; el anterior, apagado en los dos; el «Caso base», intacto."""
    app, _base = _red_calibrada()
    caso_base = _caso(app, 'Caso base')
    caso_base.Activate()
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste())
    assert rc == 0, informe
    nuevo = informe['variacion']
    assert informe['caso'] == 'Sin proyecto' and app.caso is caso_base
    for n in ('Sin proyecto', 'Con proyecto'):
        activas = _activas_en(app, _caso(app, n))[0]
        assert nuevo in activas and AJUSTE_VIEJO not in activas, n
    assert _activas_en(app, caso_base)[0] == []
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    assert escritas and all(e[3]._padre.loc_name == nuevo for e in escritas)


def test_con_tres_casos_demandas_en_sin_y_cargas_en_con():
    """011:RF-52, 011:RF-53, 011:RF-54, 011:RF-55 — demandas en «Sin proyecto» (y activas en
    «Con proyecto»), la carga nueva solo en «Con proyecto», todo con el escenario de su caso
    apagado mientras se escribe y vuelto a encender; el «Caso base», intacto."""
    app, base = _red_calibrada(escenario=True)
    caso_base = _caso(app, 'Caso base')
    plan = {**_plan_cargas(['F1'], demandas=[_demanda('F1_S1', 30.0, 10.0)],
                           nuevas=[_nueva('N1', barra='F1_B2', tension_bt_kv=0.38)]), 'base': base}
    informe, rc = cargas_guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    demandas = informe['variacion_demandas']
    carga = informe['cargas'][0]['variacion']
    sin, esc_sin = _activas_en(app, _caso(app, 'Sin proyecto'))
    con, esc_con = _activas_en(app, _caso(app, 'Con proyecto'))
    assert demandas in sin and carga not in sin
    assert demandas in con and carga in con
    assert _activas_en(app, caso_base)[0] == []
    assert esc_sin.loc_name == 'Sin proyecto' and esc_con.loc_name == 'Con proyecto'
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    assert escritas and all(e[3] is not None and e[4] is None for e in escritas)
    assert informe['casos'] == {'demandas': 'Sin proyecto', 'cargas': 'Con proyecto'}
    assert app.caso is caso_base


def test_sin_los_tres_casos_todo_sigue_como_antes():
    """011:RF-51 — sin los tres casos, el ajuste trabaja en el caso activo, como en la spec 006."""
    app, _base = _red_calibrada(preparar=False)
    original = app.caso
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste())
    assert rc == 0 and 'caso' not in informe and app.caso is original
    assert informe['variacion'] in [v.loc_name for v in app.GetActiveNetworkVariations()]
