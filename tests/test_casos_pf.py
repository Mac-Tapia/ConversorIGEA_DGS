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
    """Proyecto con el «Caso base» verificado y calibrado (spec 015): la calibración está en
    el escenario, no en variaciones; hay cargas nuevas de la spec 007 y, si se pide, ajustes
    de antes de la spec 015 (variaciones ``Ajuste_…`` que solo cambian cargas)."""
    n = rng.randint(1, 5)
    alims = tuple(sorted({f'AL{rng.randint(100, 999)}' for _ in range(n)}))
    app = fake_pf.proyecto(alimentadores=alims, cargas_por_alim=2, escenario=escenario)
    viejos = {}
    if anteriores:
        for f in alims:
            viejos[f] = _variacion(app, f'Ajuste_{f}_20260901_080000')
    ajustes = [{'feeder': f, 'cuadrado': True, 'desvio': {'kw': 0.002, 'kvar': -0.004}}
               for f in alims]
    con_cargas = [f for f in alims if cargas and rng.random() < 0.7] or ([alims[0]] if cargas else [])
    cargas_v = [_variacion(app, f'Carga_S{i}_{f}_{STAMP}') for i, f in enumerate(con_cargas)]
    base = {'variaciones': [], 'feeders': list(alims), 'ajustes': ajustes, 'excluidos': []}
    plan = {'project': 'P', 'folder': None, 'feeders': list(alims), 'base': base,
            'caso_base_sin_verificar': {}}
    return app, plan, {'cargas': cargas_v, 'viejos': viejos}


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
    """011:RF-1, 011:RF-2, 011:RF-3, 011:RF-4, 011:RF-5, 011:RF-8 / 015:RF-16, 015:RF-18, 015:RF-27,
    015:RF-29 — el original pasa a «Caso base»; «Sin proyecto» es su copia, sin ninguna
    variación activa; «Con proyecto», la copia de «Sin proyecto» con las cargas nuevas."""
    app, plan, v = _escenario_red(random.Random(semilla))
    original = app.caso
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0, informe
    base, sin, con = (_caso(app, n) for n in casos_pf.NOMBRES.values())
    assert base is original and None not in (sin, con)
    assert len(app.carpetas['study'].GetContents('*.IntCase')) == 3
    assert _activas_en(app, base)[0] == []
    assert _activas_en(app, sin)[0] == []
    assert _activas_en(app, con)[0] == sorted(c.loc_name for c in v['cargas'])
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


def test_con_obras_y_sin_cargas_nuevas_se_estudia_con_proyecto():
    """017:RF-30 — un estudio sin cliente nuevo: las obras de «Con proyecto» bastan para estudiarlo."""
    app, plan, _v = _escenario_red(random.Random(11), cargas=False)
    casos_pf.preparar(app, plan)
    _caso(app, 'Con proyecto').Activate()
    _variacion(app, 'Obra_condensador_N7')
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0
    assert informe['casos']['con']['estudiable'] is True
    assert 'Obra_condensador_N7' in informe['casos']['con']['variaciones']


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


def test_sin_calibrar_no_se_prepara():
    """011:RF-13 (con la 015:RF-26) — sin ningún alimentador calibrado no hay casos que
    estudiar; la calibración ya no se busca en una variación."""
    app, plan, _v = _escenario_red(random.Random(12))
    for base in (None, {'ajustes': []}):
        informe, codigo = casos_pf.preparar(app, {**plan, 'base': base})
        assert codigo == 2 and 'calibr' in informe['error']
    assert _caso(app, 'Sin proyecto') is None and app.caso.loc_name == 'Caso'


def test_alimentador_sin_calibrar_o_sin_cuadrar():
    """011:RF-14, 011:RF-15 — el que no está calibrado queda fuera; el que no cuadró, con aviso."""
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


@pytest.mark.parametrize('estado', [{'AL_X': ['flujo']}, None])
def test_sin_caso_base_verificado_no_se_crean_los_casos(estado):
    """015:RF-16, 015:RF-17 — con el «Caso base» sin verificar no se crean «Sin proyecto» ni
    «Con proyecto», y se dice; un plan sin el estado (de antes de la 015) tampoco vale."""
    app, plan, _v = _escenario_red(random.Random(17))
    plan['feeders'] = plan['feeders'] + ['AL_X']
    plan['base']['ajustes'].append({'feeder': 'AL_X', 'cuadrado': True})
    if estado is None:
        del plan['caso_base_sin_verificar']
    else:
        plan['caso_base_sin_verificar'] = estado
    for preparar in (casos_pf.preparar, casos_pf.preparar_sin, casos_pf.preparar_con):
        informe, codigo = preparar(app, plan)
        assert codigo == 2 and 'no está verificado' in informe['error']
    assert _caso(app, 'Sin proyecto') is None and _caso(app, 'Con proyecto') is None
    assert app.caso.loc_name == 'Caso'


def test_preparar_sin_no_crea_con_proyecto():
    """015:RF-16, 015:RF-28 — «Sin proyecto» puede existir solo; «Con proyecto» se crea
    cuando hace falta, antes de insertar cargas."""
    app, plan, _v = _escenario_red(random.Random(18))
    informe, codigo = casos_pf.preparar_sin(app, plan)
    assert codigo == 0, informe
    assert _caso(app, 'Sin proyecto') is not None and _caso(app, 'Con proyecto') is None
    informe, codigo = casos_pf.preparar_con(app, plan)
    assert codigo == 0 and informe['casos']['con']['creado'] is True


def test_una_vez_copiado_el_caso_base_no_se_toca():
    """015:RF-19, 015:RF-31 — con «Sin proyecto» creado, volver a preparar no cambia nada del
    «Caso base»; una variación que el operador dejó activa en él se avisa y no se toca."""
    app, plan, v = _escenario_red(random.Random(19), escenario=True)
    del_operador = fake_pf.variacion_del_operador(app, 'Refuerzo_operador', [])
    casos_pf.preparar(app, plan)
    base = _caso(app, 'Caso base')
    antes = _activas_en(app, base)
    for c in v['cargas']:
        base.Activate()
        c.Activate()               # el operador activa a mano una carga nueva en el base
    app.caso.Activate()
    tras_operador = _activas_en(app, base)
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0
    assert _activas_en(app, base) == tras_operador != antes
    assert del_operador.loc_name in antes[0]
    assert any('Refuerzo_operador' in a for a in informe['avisos'])


def test_un_escenario_por_caso():
    """011:RF-46, 011:RF-47 / 015:RF-18 — cada caso con su escenario; las copias, copia del de
    su origen."""
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


def test_los_ajustes_de_antes_se_desactivan_en_con_proyecto_sin_borrar():
    """011:RF-50 (con la 015:RF-26) — un ajuste de antes de la spec 015 no se activa en «Con
    proyecto» y sigue en el proyecto."""
    app, plan, v = _escenario_red(random.Random(50), anteriores=True)
    casos_pf.preparar(app, plan)
    activas = _activas_en(app, _caso(app, 'Con proyecto'))[0]
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

CLIENTES = [{'codigo': '11', 'sed': 'f1_s2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]


def _red_calibrada(*, escenario=False, preparar=True, manda=False):
    """F1 y F2 con barras de baja y flujo, el «Caso base» verificado y, si se pide, los tres
    casos hechos (F1 calibrado).

    ``manda``: el escenario del original guarda las demandas importadas y manda, como en
    DIgSILENT (006:RF-27); «Sin proyecto» y «Con proyecto» salen con copias de él.
    """
    app = fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True,
                           escenario=escenario or manda)
    if manda:
        app.escenario_manda = True
        app.escenario.fotografiar()
    base = {'variaciones': [], 'feeders': ['F1'], 'excluidos': [],
            'ajustes': [{'feeder': 'F1', 'cuadrado': True}]}
    if preparar:
        informe, codigo = casos_pf.preparar(app, {'project': 'P', 'feeders': ['F1'], 'base': base,
                                                  'caso_base_sin_verificar': {}})
        assert codigo == 0, informe
    app.escrituras.clear()
    return app, base


def _carga_de(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == nombre)


def test_el_ajuste_marca_fijas_y_escalables_en_la_red():
    """011:RF-18, 011:RF-19 / 015:RF-37 — clientes importantes no escalan; las repartidas, sí.
    La marca va a la red, sin etapa: DIgSILENT no la guarda en el escenario (sonda T1)."""
    app, _base = _red_calibrada(preparar=False)
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste(clientes=CLIENTES))
    assert rc == 0, informe
    marcas = {o.loc_name: o.i_scale for o in app.proyecto.GetContents('*.ElmLod', 1)
              if hasattr(o, 'i_scale')}
    assert marcas.pop('F1_S2') == 0
    assert marcas and set(marcas.values()) == {1} and all(n.startswith('F1_') for n in marcas)
    escritas = [e for e in app.escrituras if e[1] == 'i_scale']
    assert escritas and all(e[3] is None for e in escritas)


def test_con_tres_casos_el_ajuste_va_a_sin_y_con_y_no_crea_variaciones():
    """011:RF-51, 011:RF-53 / 014:RF-4 / 015:RF-19 / 015:RF-26 — con los tres casos, el ajuste
    escribe en los escenarios de «Sin proyecto» y de «Con proyecto», no crea ninguna
    variación y deja el «Caso base» como estaba."""
    app, _base = _red_calibrada()
    caso_base = _caso(app, 'Caso base')
    caso_base.Activate()
    antes_variaciones = list(app.carpetas['scheme'].GetContents('*.IntScheme'))
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste())
    assert rc == 0, informe
    assert informe['caso'] == 'Sin proyecto' and app.caso is caso_base
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == antes_variaciones
    for n in ('Caso base', 'Sin proyecto', 'Con proyecto'):
        assert _activas_en(app, _caso(app, n))[0] == [], n
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod'
                and e[1] != 'i_scale']
    assert escritas and all(e[3] is None and e[4] is not None for e in escritas)
    assert {e[4].loc_name for e in escritas} == {'Sin proyecto', 'Con proyecto'}


def test_con_tres_casos_demandas_en_sin_y_cargas_en_con():
    """011:RF-52, 011:RF-53 / 015:RF-27, 015:RF-29 — demandas en el escenario de «Sin
    proyecto» (y de «Con proyecto»), sin variación; la carga nueva, en su variación y solo
    en «Con proyecto»; el «Caso base», intacto."""
    app, base = _red_calibrada(escenario=True)
    caso_base = _caso(app, 'Caso base')
    plan = {**_plan_cargas(['F1'], demandas=[_demanda('F1_S1', 30.0, 10.0)],
                           nuevas=[_nueva('N1', barra='F1_B2', tension_bt_kv=0.38)]), 'base': base}
    informe, rc = cargas_guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    carga = informe['cargas'][0]['variacion']
    sin, esc_sin = _activas_en(app, _caso(app, 'Sin proyecto'))
    con, esc_con = _activas_en(app, _caso(app, 'Con proyecto'))
    assert sin == [] and con == [carga]
    assert [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')] == [carga]
    assert _activas_en(app, caso_base)[0] == []
    assert esc_sin.loc_name == 'Sin proyecto' and esc_con.loc_name == 'Con proyecto'
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod'
                and e[0].loc_name == 'F1_S1']
    assert escritas and all(e[3] is None for e in escritas)
    assert {e[4] for e in escritas} == {esc_sin, esc_con}
    assert informe['casos'] == {'demandas': 'Sin proyecto', 'cargas': 'Con proyecto'}
    assert app.caso is caso_base


def test_sin_proyecto_lo_crea_el_ajuste_desde_el_caso_base():
    """014:RF-1, 014:RF-5 / 015:RF-16, 015:RF-28 — sin casos, el ajuste crea «Sin proyecto»
    como copia del «Caso base» verificado y calibra en él; «Con proyecto» no se crea hasta
    insertar cargas. Al simular no se crea ningún caso."""
    app, _base = _red_calibrada(preparar=False)
    original = app.caso
    simulado, rc = ajuste_pf.ejecutar(app, _plan_ajuste(), simular=True)
    assert rc == 0 and casos_pf.casos_del_proyecto(app) == {} and 'caso' not in simulado
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste())
    assert rc == 0, informe
    assert informe['caso'] == 'Sin proyecto' and informe['casos_preparados']
    assert app.caso is original and original.loc_name == 'Caso base'
    assert set(casos_pf.casos_del_proyecto(app)) == {'base', 'sin'}


def _cabecera_en(app, caso, feeder='F1'):
    """Lo que entra por la cabecera en ``caso``, con su escenario activo."""
    previo = app.caso
    caso.Activate()
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1) if f.loc_name == feeder)
    medida = ajuste_pf.medir_cabecera(app, elm)
    previo.Activate()
    return medida


def test_con_tres_casos_el_ajuste_va_a_sin_y_con_y_no_al_base():
    """006:RF-28 (cambiado por 014:RF-4) / 011:RF-53 / 015:RF-19 — con los tres casos, la cabecera ajustada se ve en
    «Sin proyecto» y en «Con proyecto» con su escenario activo; el «Caso base» no cambia."""
    app, _base = _red_calibrada(manda=True)
    caso_base = _caso(app, 'Caso base')
    caso_base.Activate()
    antes_base = _cabecera_en(app, caso_base)
    informe, rc = ajuste_pf.ejecutar(app, _plan_ajuste())
    assert rc == 0, informe
    assert sorted(g['escenario'] for g in informe['escenarios']) == ['Con proyecto', 'Sin proyecto']
    for n in ('Sin proyecto', 'Con proyecto'):
        medida = _cabecera_en(app, _caso(app, n))
        assert medida.converge, n
        assert medida.kw == pytest.approx(informe['cabecera']['kw'], rel=1e-6), n
        assert medida.kvar == pytest.approx(informe['cabecera']['kvar'], rel=1e-6), n
    assert _cabecera_en(app, caso_base).kw == pytest.approx(antes_base.kw, rel=1e-9)
    assert _activas_en(app, caso_base)[0] == []
    assert app.caso is caso_base


def test_con_tres_casos_las_demandas_van_a_sin_y_con_no_al_base():
    """004:RF-54 / 004:RF-55 — la demanda en bloque se ve con el escenario de «Sin proyecto» y
    de «Con proyecto»; el del «Caso base» guarda el ajuste y no cambia."""
    app, base = _red_calibrada(manda=True)
    caso_base = _caso(app, 'Caso base')
    caso_base.Activate()
    antes = _carga_de(app, 'F1_S1').plini
    plan = {**_plan_cargas(['F1'], demandas=[_demanda('F1_S1', 30.0, 10.0)]), 'base': base}
    informe, rc = cargas_guion.ejecutar(app, plan, simular=False)
    assert rc == 0, informe
    assert sorted(g['escenario'] for g in informe['escenarios']) == ['Con proyecto', 'Sin proyecto']
    for n in ('Sin proyecto', 'Con proyecto'):
        _caso(app, n).Activate()
        assert app.GetActiveScenario().loc_name == n
        assert _carga_de(app, 'F1_S1').plini == pytest.approx(0.030), n
    caso_base.Activate()
    assert _carga_de(app, 'F1_S1').plini == pytest.approx(antes)


# =========================================================================== spec 014
def _carga_y_trafo(app, feeder):
    carga = next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name.startswith(feeder))
    trafo = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if feeder in o.loc_name)
    return carga, trafo


def test_operador_por_lo_que_graba_no_por_el_nombre():
    """014:RF-3, 014:RF-15, 014:RF-20 — un ``Ajuste_…`` que también grabó un ElmTr2 es del
    operador, como ``_3`` de CA101; uno que solo cambió cargas es un ajuste anterior."""
    app = fake_pf.proyecto(alimentadores=('AL1',), cargas_por_alim=2)
    carga, trafo = _carga_y_trafo(app, 'AL1')
    tipo = app.carpetas['equip'].CreateObject('TypTr2', 'TR_250kVA')
    puro = fake_pf.variacion_del_operador(app, 'Ajuste_AL1_20261013_203247', [(carga, 'plini', 0.2)])
    mixto = fake_pf.variacion_del_operador(app, 'Ajuste_AL1_20261013_203247_3',
                                           [(carga, 'plini', 0.3), (trafo, 'typ_id', tipo)])
    mia = fake_pf.variacion_del_operador(app, 'Refuerzo_TR', [(trafo, 'typ_id', tipo)])
    nueva = _variacion(app, f'Carga_S9_AL1_{STAMP}')

    assert casos_pf.objetos_de_variacion(mixto) == [('ElmLod', carga.loc_name),
                                                    ('ElmTr2', trafo.loc_name)]
    assert casos_pf.es_ajuste_puro(puro) and not casos_pf.es_ajuste_puro(mixto)
    assert [casos_pf.es_del_operador(v) for v in (puro, mixto, mia, nueva)] == [False, True, True, False]
    grupos = casos_pf.clasificar([puro, mixto, mia, nueva], ['AL1'], [], None)
    assert grupos['anteriores'] == [puro] and grupos['cargas'] == [nueva]
    assert [v.loc_name for v in grupos['operador']] == [mixto.loc_name, mia.loc_name]


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_preparar_conserva_al_operador_y_lo_lleva_a_con_proyecto(semilla):
    """014:RF-15, 014:RF-16, 014:RF-18, 014:RF-20, 014:RF-21, 014:RF-22 — las variaciones del
    operador no se apagan en ningún caso; las activas en «Sin proyecto» pasan a «Con
    proyecto» y se dicen; ninguna carga nueva queda activa en «Caso base» ni en «Sin»."""
    rng = random.Random(semilla)
    app, plan, v = _escenario_red(rng, anteriores=True)
    f = plan['feeders'][0]
    carga, trafo = _carga_y_trafo(app, f)
    tipo = app.carpetas['equip'].CreateObject('TypTr2', 'TR_2000kVA')
    previa = fake_pf.variacion_del_operador(app, f'Ajuste_{f}_20261013_203247_3',
                                            [(carga, 'plini', 0.4), (trafo, 'typ_id', tipo)])
    apagada = fake_pf.variacion_del_operador(app, 'Prueba_del_operador', [(trafo, 'outserv', 1)])
    apagada.Deactivate()

    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0, informe
    for nombre in ('Caso base', 'Sin proyecto', 'Con proyecto'):
        activas, _ = _activas_en(app, _caso(app, nombre))
        assert previa.loc_name in activas and apagada.loc_name not in activas
        if nombre != 'Con proyecto':
            assert not [x for x in activas if x.startswith('Carga_')]
    # 015:RF-31: activa en el «Caso base», se avisa y no se toca.
    assert any(previa.loc_name in a and '«Caso base»' in a for a in informe['avisos'])

    # El operador graba después otro cambio en «Sin proyecto»: al volver a preparar, «Con
    # proyecto» lo activa también, y lo dice; la que el operador tiene apagada sigue igual.
    _caso(app, 'Sin proyecto').Activate()
    otra = fake_pf.variacion_del_operador(app, 'Cambio_posterior', [(trafo, 'typ_id', tipo)])
    _caso(app, 'Caso base').Activate()
    informe, codigo = casos_pf.preparar(app, plan)
    assert codigo == 0, informe
    assert informe['casos']['con']['variaciones_operador_activadas'] == [otra.loc_name]
    activas_con, _ = _activas_en(app, _caso(app, 'Con proyecto'))
    assert otra.loc_name in activas_con and apagada.loc_name not in activas_con
    activas_base, _ = _activas_en(app, _caso(app, 'Caso base'))
    assert otra.loc_name not in activas_base


# --------------------------------------------------------------- 014:RF-31 a RF-34
class _Obj:
    def __init__(self, nombre):
        self.loc_name, self.escrito = nombre, {}

    def SetAttribute(self, attr, valor):
        self.escrito[attr] = valor


class _Esc:
    guardado = 0

    def Save(self):
        self.guardado += 1


class _Caso:
    def __init__(self, app, rol):
        self.app, self.rol = app, rol

    def Activate(self):
        self.app.activo = self


class _App:
    def __init__(self):
        self.escenario = _Esc()
        self.casos = {r: _Caso(self, r) for r in ('base', 'sin', 'con')}
        self.activo = self.casos['base']

    def GetActiveStudyCase(self):
        return self.activo

    def GetActiveScenario(self):
        return self.escenario


def test_lo_hecho_a_mano_en_sin_proyecto_pasa_a_con_proyecto(monkeypatch):
    """014:RF-31, 014:RF-32, 014:RF-33, 014:RF-34 — PN107 (2026-10-16): un banco creado a
    mano en «Sin proyecto» no estaba en «Con proyecto». Se activan las variaciones del
    operador; un dato de operación que solo cambió «Sin proyecto» se copia al escenario de
    «Con proyecto»; uno que cambió también «Con proyecto» (una obra) se deja y se avisa; lo
    que falta en «Con proyecto» se lista; nada más se toca y vuelve el caso del principio."""
    app = _App()
    banco, sw, obra, igual = _Obj('BC_1'), _Obj('SW_1'), _Obj('SW_2'), _Obj('SW_3')
    R = 'P/Red/'                   # la ruta solo sirve de clave; el nombre va tras la última
    fotos = {
        'base': {R + 'BC_1': (banco, {'outserv': 1, 'ncapa': 0}), R + 'SW_1': (sw, {'on_off': 1}),
                 R + 'SW_2': (obra, {'on_off': 1}), R + 'SW_3': (igual, {'on_off': 1})},
        'sin': {R + 'BC_1': (banco, {'outserv': 0, 'ncapa': 3}), R + 'SW_1': (sw, {'on_off': 0}),
                R + 'SW_2': (obra, {'on_off': 0}), R + 'SW_3': (igual, {'on_off': 1}),
                R + 'BC_2': (_Obj('BC_2'), {'outserv': 0})},
        'con': {R + 'BC_1': (banco, {'outserv': 1, 'ncapa': 0}), R + 'SW_1': (sw, {'on_off': 1}),
                R + 'SW_2': (obra, {'on_off': 2}), R + 'SW_3': (igual, {'on_off': 1})},
    }
    monkeypatch.setattr(casos_pf, '_foto_operacion', lambda a: fotos[a.activo.rol])
    monkeypatch.setattr(casos_pf, 'operador_a_con_proyecto', lambda a, c: ['Banco_del_operador'])
    inicial = app.casos['sin']
    inicial.Activate()

    out = casos_pf.sin_a_con_proyecto(app, app.casos)

    assert out['variaciones'] == ['Banco_del_operador']
    assert banco.escrito == {'outserv': 0, 'ncapa': 3} and sw.escrito == {'on_off': 0}
    assert {(c['objeto'], c['dato']) for c in out['copiados']} == {
        ('BC_1', 'outserv'), ('BC_1', 'ncapa'), ('SW_1', 'on_off')}
    assert obra.escrito == {} and out['conflictos'] == [
        {'objeto': 'SW_2', 'dato': 'on_off', 'sin': 0, 'con': 2}]
    assert igual.escrito == {} and out['faltan'] == ['BC_2']
    assert app.escenario.guardado == 1 and app.activo is inicial
    assert any('014:RF-32' in a for a in out['avisos']) and any('014:RF-34' in a for a in out['avisos'])
