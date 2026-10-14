"""Spec 006: ``tools/ajuste_cabecera_pf.py`` contra un DIgSILENT simulado (``fake_pf``).

DIgSILENT no se ejecuta en la suite (P11): el doble calcula lo que entra por la cabecera
con pérdidas cuadráticas y deja de converger por encima de un límite. La prueba real, con
el signo y el lado de la cabecera, la hace el usuario (T8).
"""
from __future__ import annotations

import copy
import math
import os
import random
from types import SimpleNamespace

import fake_pf
import pytest
from apoyo import cargar_herramienta, contexto_nativo

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_cabecera_pf_guion',
                              tools_en_path=True)


def _app(n=6, **kw):
    kw.setdefault('kva', lambda f, i: 50.0 * i)
    return fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=n, bt=True, flujo=True,
                            **kw)


def _plan(kw=300.0, kvar=90.0, clientes=(), kva_entrada=None, tolerancia=0.01, max_flujos=None):
    return {'project': 'P', 'feeder': 'F1', 'stamp': '20261009_120000',
            'variacion': 'Ajuste_F1_20261009_120000',
            'objetivo': {'kw': kw, 'kvar': kvar, 'medidor': 'M1', 'alimentador': 'F1',
                         'fecha': '2026-03-03 10:00:00'},
            'clientes': list(clientes), 'kva_entrada': kva_entrada or {},
            'tolerancia': tolerancia, 'max_flujos': max_flujos,
            'project_binding': {'native_reread': {
                'status': 'VERIFICADO_PERSISTENCIA',
                'capacitor_reread': {'status': 'VERIFICADO_PERSISTENCIA', 'expected': 3},
            }},
            'native_action_context': contexto_nativo('P', ['F1'], 'ajuste')}


def _carga(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == nombre)


def _sed(informe, sed):
    return next(x for x in informe['sed'] if x['sed'] == sed)


def test_cuadra_la_cabecera_en_una_variacion_nueva(guion):
    """006:RF-4 / 006:RF-11 / 006:RF-19 / 006:RF-21 / 006:RF-40 — solo el alimentador elegido, en su variación, y
    el informe con objetivo, cabecera, pérdidas, error y flujos."""
    app = _app(escenario=True)
    otra = _carga(app, 'F2_S1').plini
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert informe['cuadrado'] and abs(informe['desvio']['kw']) <= 0.01
    assert informe['status'] == 'AVISO_KVAR'
    assert informe['decision_carga_nativa']['status'] == 'REQUIERE_DISTRIBUCION'
    assert informe['resultado_carga_nativa'] == {
        'status': 'APLICADO_Y_VALIDADO',
        'bloquea': False,
    }
    assert informe['validacion_posterior_nativa']['status'] == 'VALIDO'
    assert informe['kvar_no_bloqueante']['bloquea'] is False
    assert informe['kvar_no_bloqueante']['supera_tolerancia']
    reread = informe['relectura_cargas_nativas']
    assert reread['status'] == 'VERIFICADO_PERSISTENCIA'
    assert reread['cantidad'] == len(informe['sed'])
    assert all({'p_kw', 'q_kvar', 'fp', 'outserv', 'i_scale', 'full_name'} <= set(x)
               for x in reread['despues'])
    assert informe['relectura_bancos']['expected'] == 3
    # «error» es solo para fallos: la web lo toma por uno y paraba un ajuste que cuadró.
    assert 'error' not in informe
    assert informe['perdidas']['kw'] > 0 and 1 <= informe['flujos'] < 20
    assert [v.loc_name for v in app.carpetas['scheme'].GetContents('*.IntScheme')] == [informe['variacion']]
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    # Los flujos del cuadre, en la etapa y con el escenario apagado; el resultado, además,
    # en el escenario (RF-27).
    en_variacion = [e for e in escritas if e[4] is None]
    assert en_variacion and all(e[3] is not None for e in en_variacion), \
        'el cuadre, en la etapa que graba y con el escenario apagado'
    assert all(e[4] is app.escenario for e in escritas if e[4] is not None)
    assert app.escenario is not None, 'el escenario del operador vuelve a estar activo'
    assert _carga(app, 'F2_S1').plini == otra
    fila = _sed(informe, 'F1_S3')
    assert fila['antes']['kw'] == pytest.approx(50.0) and fila['kva_de'] == 'pf'


def test_segunda_carga_validada_no_redistribuye_ni_crea_variacion(guion):
    """006:RF-41 / 006:RF-43 — si la nativa ya conserva fijas, escalables y cabecera,
    repetir es solo relectura.

    La mutación que esta prueba detecta es volver a crear una variación o escribir ElmLod
    sin comprobar primero el estado efectivo de PowerFactory.
    """
    app = _app()
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    variaciones_antes = list(app.carpetas['scheme'].GetContents('*.IntScheme'))
    escrituras_antes = len([e for e in app.escrituras
                            if getattr(e[0], '_clase', '') == 'ElmLod'])

    segundo, rc = guion.ejecutar(app, _plan())

    assert rc == 0, segundo
    assert segundo['decision_carga_nativa'] == {
        'status': 'YA_CARGADO_VALIDADO',
        'accion': 'NO_REDISTRIBUIR',
        'bloquea': False,
        'origen': 'ESTADO_EFECTIVO',
    }
    assert segundo['cuadrado'] is True
    assert segundo['relectura_cargas_nativas']['status'] == 'VERIFICADO_PERSISTENCIA'
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == variaciones_antes
    assert len([e for e in app.escrituras
                if getattr(e[0], '_clase', '') == 'ElmLod']) == escrituras_antes


def test_reapertura_reactiva_variacion_valida_sin_redistribuir(guion):
    """Una variacion persistida pero inactiva se valida y reutiliza al reabrir."""
    app = _app()
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    variacion = next(v for v in app.carpetas['scheme'].GetContents('*.IntScheme')
                     if v.loc_name == primero['variacion'])
    cambios = []
    for fila in primero['sed']:
        obj = _carga(app, fila['sed'])
        antes, despues = fila['antes'], fila['despues']
        fp_antes = abs(antes['kw']) / math.hypot(antes['kw'], antes['kvar'])
        fp_despues = abs(despues['kw']) / math.hypot(despues['kw'], despues['kvar'])
        cambios.extend([
            (obj, '_p', antes['kw'] / 1000.0, despues['kw'] / 1000.0),
            (obj, '_cos', fp_antes, fp_despues),
            (obj, 'i_scale', 0, obj.i_scale),
        ])
    object.__setattr__(variacion, '_cambios', cambios)
    variacion.Deactivate()
    variaciones_antes = list(app.carpetas['scheme'].GetContents('*.IntScheme'))
    escrituras_antes = len([e for e in app.escrituras
                            if getattr(e[0], '_clase', '') == 'ElmLod'])

    reabierto, rc = guion.ejecutar(app, _plan())

    assert rc == 0, reabierto
    assert reabierto['decision_carga_nativa'] == {
        'status': 'YA_CARGADO_VALIDADO',
        'accion': 'NO_REDISTRIBUIR',
        'bloquea': False,
        'origen': 'VARIACION_EXISTENTE_REACTIVADA',
    }
    assert reabierto['variacion_reutilizada'] == primero['variacion']
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == variaciones_antes
    assert len([e for e in app.escrituras
                if getattr(e[0], '_clase', '') == 'ElmLod']) == escrituras_antes


def test_relectura_reconoce_juntas_cargas_fijas_y_escaladas(guion):
    """006:RF-42 — la decisión idempotente valida por separado ambos grupos."""
    app = _app()
    plan = _plan(clientes=[
        {'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25},
    ])
    primero, rc = guion.ejecutar(app, plan)
    assert rc == 0, primero
    escrituras_antes = len(app.escrituras)

    segundo, rc = guion.ejecutar(app, plan)

    assert rc == 0, segundo
    assert segundo['decision_carga_nativa']['status'] == 'YA_CARGADO_VALIDADO'
    clases = {fila['sed']: fila['clase']
              for fila in segundo['validacion_previa_nativa']['cargas']}
    assert clases['F1_S2'] == 'FIJA'
    assert {clase for sed, clase in clases.items() if sed != 'F1_S2'} == {'ESCALABLE'}
    assert len(app.escrituras) == escrituras_antes


def test_estado_manual_correcto_se_adopta_sin_recibo_ni_variacion_previa(guion):
    """La prueba física basta: no se exige que el ajuste lo haya creado esta aplicación."""
    app = _app()
    plan = _plan(clientes=[
        {'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25},
    ])
    aplicado, rc = guion.ejecutar(app, plan)
    assert rc == 0, aplicado
    # Imita valores correctos dejados directamente en el modelo por el operador: no queda
    # una variación/recibo de la aplicación, pero P/Q/i_scale y cabecera siguen efectivos.
    for variacion in list(app.carpetas['scheme'].GetContents('*.IntScheme')):
        variacion.Delete()
    app.escrituras.clear()

    adoptado, rc = guion.ejecutar(app, plan)

    assert rc == 0, adoptado
    assert adoptado['decision_carga_nativa']['status'] == 'YA_CARGADO_VALIDADO'
    assert adoptado['variacion'] is None
    assert app.escrituras == []
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == []


def test_q_proporcional_pero_distinta_a_la_calculada_obliga_a_recalibrar(guion):
    """Q uniforme pero equivocada no convierte un estado modificado en ya validado."""
    app = _app()
    plan = _plan()
    aplicado, rc = guion.ejecutar(app, plan)
    assert rc == 0, aplicado
    for fila in aplicado['sed']:
        obj = _carga(app, fila['sed'])
        guion.escribir_carga(
            obj, fila['despues']['kw'] / 1000.0, 2.0 * fila['despues']['kvar'] / 1000.0,
        )

    corregido, rc = guion.ejecutar(app, plan)

    assert rc == 0, corregido
    assert corregido['decision_carga_nativa']['status'] == 'REQUIERE_DISTRIBUCION'
    assert any(f['tipo'] == 'FACTOR_Q_INCORRECTO'
               for f in corregido['validacion_previa_nativa']['fallos'])
    assert corregido['resultado_carga_nativa']['status'] == 'APLICADO_Y_VALIDADO'


def test_relectura_posterior_invalida_no_deja_variacion_aceptada(guion):
    """006:RF-44 — una marca que PowerFactory no conserva invalida y revierte la
    aplicación nueva.

    La mutación que detecta es aceptar el cuadre de cabecera aunque una carga escalable
    reaparezca con ``i_scale=0`` en la relectura efectiva.
    """
    app = _app()
    carga = _carga(app, 'F1_S1')
    ejecutar_flujo = app.ldf.Execute

    def flujo_que_no_conserva_la_marca():
        rc = ejecutar_flujo()
        object.__setattr__(carga, 'i_scale', 0)
        return rc

    object.__setattr__(app.ldf, 'Execute', flujo_que_no_conserva_la_marca)

    informe, rc = guion.ejecutar(app, _plan())

    assert rc == 2
    assert informe['resultado_carga_nativa'] == {
        'status': 'FALLO_VALIDACION_NATIVA',
        'bloquea': True,
    }
    assert informe['validacion_posterior_nativa']['status'] == 'REQUIERE_DISTRIBUCION'
    assert informe['relectura_cargas_nativas']['status'] == 'FALLO_VALIDACION_NATIVA'
    assert any(f['tipo'] == 'CARGA_INCORRECTA' and f['sed'] == 'F1_S1'
               for f in informe['validacion_posterior_nativa']['fallos'])
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == []


def test_kva_de_los_transformadores_y_reparto_proporcional(guion):
    """006:RF-8 — kW por kVA igual en todas las repartidas; kVA del transformador en PF."""
    rnd = random.Random(SEMILLA)
    tamanos = {i: rnd.choice([25.0, 50.0, 100.0, 160.0, 250.0]) for i in range(1, 30)}
    app = _app(n=rnd.randint(5, 25), kva=lambda f, i: tamanos[i])
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 0, (SEMILLA, informe)
    ratios = {round(x['despues']['kw'] / x['kva'], 9) for x in informe['sed']}
    assert len(ratios) == 1, SEMILLA
    assert {x['kva'] for x in informe['sed']} <= set(tamanos.values())


def test_sed_con_clientes_lleva_su_demanda(guion):
    """006:RF-5 / 006:RF-9 — la SED del cliente con su Pot, fija; la que no está, omitida."""
    app = _app()
    clientes = [{'codigo': '11', 'sed': 'f1_s2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25},
                {'codigo': '12', 'sed': 'ZZ9', 'pot': 10.0, 'ea': 1.0, 'eri': 0.1}]
    informe, rc = guion.ejecutar(app, _plan(clientes=clientes))
    assert rc == 0, informe
    fila = _sed(informe, 'F1_S2')
    assert fila['origen'] == 'cliente' and fila['clientes'] == ['11']
    assert fila['despues']['kw'] == pytest.approx(40.0)
    assert fila['despues']['kvar'] == pytest.approx(10.0)
    assert fila['despues']['fp'] == pytest.approx(1 / (1 + 0.25**2) ** 0.5)
    assert fila['derivaciones'] == [{
        'cliente': '11', 'p_kw': 40.0, 'q_kvar': 10.0,
        'fp': pytest.approx(1 / (1 + 0.25**2) ** 0.5),
        'metodo': 'ERI/EA', 'ea': 1.0, 'eri': 0.25,
    }]
    assert _carga(app, 'F1_S2').plini == pytest.approx(0.040)
    assert _carga(app, 'F1_S2').qlini == pytest.approx(0.010)
    assert _carga(app, 'F1_S2').coslini == pytest.approx(1 / (1 + 0.25**2) ** 0.5)
    assert _carga(app, 'F1_S2').i_scale == 0
    assert [o['sed'] for o in informe['omitidas']] == ['ZZ9']


def test_si_las_fijas_superan_objetivo_todas_quedan_marcadas_escalables(guion):
    """006:RF-13 — cuando se escala todo, incluso la SED de cliente lleva i_scale=1.

    Detecta clasificar por el origen histórico ``cliente`` en vez de por la participación
    efectiva en el reparto escalado.
    """
    app = _app()
    clientes = [{'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]

    informe, rc = guion.ejecutar(app, _plan(kw=30.0, kvar=9.0, clientes=clientes))

    assert rc == 0, informe
    assert informe['todo_escala'] is True
    assert informe['resultado_carga_nativa']['status'] == 'APLICADO_Y_VALIDADO'
    assert all(_carga(app, fila['sed']).i_scale == 1 for fila in informe['sed'])


def test_cargas_sed_une_topologia_con_etiqueta_alimentador(guion):
    """006:RF-8 — ``ElmFeeder.GetObjs`` puede omitir cargas que siguen perteneciendo al
    alimentador según la columna nativa ``p:alimentador``; ninguna queda fuera del ajuste.
    """
    app = _app()
    extra = app.proyecto.CreateObject('ElmLod', 'F1_S99')
    # PowerFactory 2024 relee la propiedad definida por DGS como una lista, incluso con
    # un solo valor (CA101 real: ``['CA101']``).
    extra.SetAttribute('p:alimentador', ['F1'])
    extra.outserv = 0
    original = _carga(app, 'F1_S1')
    original.SetAttribute('p:alimentador', ['F1'])
    globales = list(app.GetCalcRelevantObjects('*.ElmLod'))
    # La API real entrega wrappers Python distintos para un mismo objeto según la consulta.
    app.GetCalcRelevantObjects = lambda _patron: globales + [copy.copy(original)]
    alims = guion.Alimentadores(app, app.proyecto, ['F1'])

    assert extra not in alims.objetos('F1', 'ElmLod'), 'precondición: la topología lo omite'
    audit = {}
    cargas, ambiguas = guion.cargas_sed(alims, 'F1', audit=audit)

    assert not ambiguas
    assert cargas['F1_S99'] is extra
    assert cargas['F1_S1'] is original
    assert len(cargas) == 7
    assert audit['algoritmo'] == 'UNION_TOPOLOGIA_Y_P_ALIMENTADOR'
    assert audit['duplicados_colapsados'] >= 1
    assert audit['union_objetos'] == 7


def test_medidor_unico_mide_la_suma_de_dos_troncales(guion):
    """006:RF-4 — un medidor en la fuente mide juntas las dos salidas de CA101.

    La rama a la que apunta ``ElmFeeder`` representa solo una troncal (4 MW); el
    ``ElmXnet`` conectado a la misma barra registra los 6 MW de ambas troncales.
    """
    app = _app(n=2)
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1)
               if f.loc_name == 'F1')
    cub_troncal = elm.obj_id
    barra_fuente = cub_troncal.GetParent()
    red = elm.GetParent()
    troncal_2 = red.CreateObject('ElmLne', 'F1_TRONCAL_2')
    cub_troncal_2 = barra_fuente.CreateObject('StaCubic', 'Cub F1 troncal 2')
    cub_troncal_2.obj_id, cub_troncal_2.obj_bus = troncal_2, 0
    fuente = red.CreateObject('ElmXnet', 'Fuente F1')
    cub_fuente = barra_fuente.CreateObject('StaCubic', 'Cub Fuente F1')
    cub_fuente.obj_id, cub_fuente.obj_bus = fuente, 0
    object.__setattr__(cub_troncal.obj_id, 'm_Psum:bus1', 4.0)
    object.__setattr__(cub_troncal.obj_id, 'm_Qsum:bus1', 0.8)
    object.__setattr__(troncal_2, 'm_Psum:bus1', 2.0)
    object.__setattr__(troncal_2, 'm_Qsum:bus1', 0.4)
    # PowerFactory 2024 en CA101 entrega la inyeccion del ElmXnet positiva, igual que
    # la suma de los flujos que salen por las dos troncales.
    object.__setattr__(fuente, 'm_Psum:bus1', 6.0)
    object.__setattr__(fuente, 'm_Qsum:bus1', 1.2)
    app.ldf = fake_pf.Orden(app, 'ComLdf')
    app.ldf_valido = True

    medida = guion.medir_cabecera(app, elm)

    assert medida.converge
    assert medida.kw == pytest.approx(6000.0)
    assert medida.kvar == pytest.approx(1200.0)


def test_medidor_unico_mide_la_suma_de_tres_troncales(guion):
    """006:RF-4 — la regla multitroncal no está limitada al caso particular CA101."""
    app = _app(n=2)
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1)
               if f.loc_name == 'F1')
    cub_troncal_1 = elm.obj_id
    barra_fuente = cub_troncal_1.GetParent()
    red = elm.GetParent()
    troncales = [cub_troncal_1.obj_id]
    for numero in (2, 3):
        troncal = red.CreateObject('ElmLne', f'F1_TRONCAL_{numero}')
        cub = barra_fuente.CreateObject('StaCubic', f'Cub F1 troncal {numero}')
        cub.obj_id, cub.obj_bus = troncal, 0
        troncales.append(troncal)
    fuente = red.CreateObject('ElmXnet', 'Fuente F1')
    cub_fuente = barra_fuente.CreateObject('StaCubic', 'Cub Fuente F1')
    cub_fuente.obj_id, cub_fuente.obj_bus = fuente, 0
    for troncal, p, q in zip(troncales, (1.0, 2.0, 3.0), (0.2, 0.4, 0.6), strict=True):
        object.__setattr__(troncal, 'm_Psum:bus1', p)
        object.__setattr__(troncal, 'm_Qsum:bus1', q)
    object.__setattr__(fuente, 'm_Psum:bus1', -6.0)
    object.__setattr__(fuente, 'm_Qsum:bus1', -1.2)
    app.ldf = fake_pf.Orden(app, 'ComLdf')
    app.ldf_valido = True

    medida = guion.medir_cabecera(app, elm)
    detalle = guion.detalle_cabecera(elm)

    assert medida.converge and medida.kw == pytest.approx(6000.0)
    assert detalle['cantidad_troncales'] == 3
    assert sum(t['kw'] for t in detalle['troncales']) == pytest.approx(6000.0)


def test_una_troncal_con_fuente_conserva_la_medicion_del_elmfeeder(guion):
    """006:RF-4 — el modo de medidor común se activa sólo con dos o más troncales."""
    app = _app(n=2)
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1)
               if f.loc_name == 'F1')
    cub_troncal = elm.obj_id
    barra_fuente = cub_troncal.GetParent()
    fuente = elm.GetParent().CreateObject('ElmXnet', 'Fuente F1')
    cub_fuente = barra_fuente.CreateObject('StaCubic', 'Cub Fuente F1')
    cub_fuente.obj_id, cub_fuente.obj_bus = fuente, 0
    object.__setattr__(cub_troncal.obj_id, 'm_Psum:bus1', 4.0)
    object.__setattr__(cub_troncal.obj_id, 'm_Qsum:bus1', 0.8)
    object.__setattr__(fuente, 'm_Psum:bus1', 6.0)
    object.__setattr__(fuente, 'm_Qsum:bus1', 1.2)
    app.ldf = fake_pf.Orden(app, 'ComLdf')
    app.ldf_valido = True

    medida = guion.medir_cabecera(app, elm)
    detalle = guion.detalle_cabecera(elm)

    assert medida.converge and medida.kw == pytest.approx(4000.0)
    assert detalle['metodo'] == 'RAMA_ELMFEEDER'


def test_multitroncal_sin_medidor_unico_no_calibra_una_rama_parcial(guion):
    """006:RF-4 — sin una única frontera común, el ajuste falla de forma cerrada."""
    app = _app(n=2)
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1)
               if f.loc_name == 'F1')
    cub_troncal_1 = elm.obj_id
    barra_fuente = cub_troncal_1.GetParent()
    troncal_2 = elm.GetParent().CreateObject('ElmLne', 'F1_TRONCAL_2')
    cub_troncal_2 = barra_fuente.CreateObject('StaCubic', 'Cub F1 troncal 2')
    cub_troncal_2.obj_id, cub_troncal_2.obj_bus = troncal_2, 0
    object.__setattr__(cub_troncal_1.obj_id, 'm_Psum:bus1', 4.0)
    object.__setattr__(cub_troncal_1.obj_id, 'm_Qsum:bus1', 0.8)
    object.__setattr__(troncal_2, 'm_Psum:bus1', 2.0)
    object.__setattr__(troncal_2, 'm_Qsum:bus1', 0.4)
    app.ldf = fake_pf.Orden(app, 'ComLdf')
    app.ldf_valido = True

    medida = guion.medir_cabecera(app, elm)
    detalle = guion.detalle_cabecera(elm)

    assert not medida.converge
    assert '2 troncales' in medida.motivo and 'medidor' in medida.motivo
    assert detalle['metodo'] == 'MULTITRONCAL_SIN_MEDIDOR_UNICO'
    assert detalle['cantidad_fuentes'] == 0


def test_consumo_nativo_suma_resultados_de_todas_las_sed(guion):
    """006:RF-11 — las pérdidas usan consumo efectivo, nunca una suma parcial."""
    app = _app(n=3)
    cargas = {c.loc_name: c for c in app.proyecto.GetContents('*.ElmLod', 1)
              if c.loc_name.startswith('F1_')}
    for i, carga in enumerate(cargas.values(), 1):
        object.__setattr__(carga, 'm_Psum:bus1', i / 100.0)
        object.__setattr__(carga, 'm_Qsum:bus1', i / 200.0)

    assert guion.consumo_nativo(cargas) == pytest.approx((60.0, 30.0))

    delattr(next(iter(cargas.values())), 'm_Psum:bus1')
    assert guion.consumo_nativo(cargas) == (None, None)


def test_validacion_de_perdidas_usa_consumo_efectivo_no_plini(guion):
    """La tension puede reducir el consumo terminal respecto de ``plini``.

    La cabecera debe compararse con ``m:Psum``: sumar las potencias escritas produciria
    aqui una perdida activa negativa falsa (1 250 - 3 000 kW).
    """
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app(n=2)
    objetos = [o for o in app.proyecto.GetContents('*.ElmLod', 1)
               if o.loc_name.startswith('F1_')]
    cargas = {o.loc_name: o for o in objetos}
    demandas = {}
    base = {}
    for i, obj in enumerate(objetos, 1):
        obj.plini, obj.qlini, obj.i_scale = float(i), i / 10.0, 1
        object.__setattr__(obj, 'm:Psum:bus1', 0.4 * i)
        object.__setattr__(obj, 'm:Qsum:bus1', 0.04 * i)
        demandas[obj.loc_name] = SimpleNamespace(kw=1000.0 * i, kvar=100.0 * i)
        base[obj.loc_name] = (1000.0 * i, 100.0 * i)
    reparto = SimpleNamespace(
        demandas=demandas, base=base, solo_kw=False, a=1.0, b=1.0,
        con_factores=lambda _a, _b: object(),
    )

    validacion, reconstruido = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 1250.0, 125.0),
        Objetivo(1250.0, 125.0, 'M1', 'F1'), 0.01,
    )

    assert validacion['correcta'] is True
    assert validacion['consumo_cargas_efectivo']['kw'] == pytest.approx(1200.0)
    assert validacion['consumo_cargas_efectivo']['kvar'] == pytest.approx(120.0)
    assert validacion['consumo_cargas_efectivo']['origen'] == 'RESULTADOS_CARGAS_NATIVAS'
    assert reconstruido is not None


def test_ajuste_suma_dos_troncales_y_conserva_clientes_fijos(guion):
    """006:RF-4 / 006:RF-5 / 006:RF-8 — las dos troncales suman un solo objetivo.

    Una carga de la segunda troncal queda fija por pertenecer a clientes importantes;
    las cargas restantes de ambas troncales comparten el escalado por kVA.
    """
    app = _app(n=4)
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1)
               if f.loc_name == 'F1')
    cub_troncal_1 = elm.obj_id
    barra_fuente = cub_troncal_1.GetParent()
    red = elm.GetParent()
    troncal_2 = red.CreateObject('ElmLne', 'F1_TRONCAL_2')
    cub_troncal_2 = barra_fuente.CreateObject('StaCubic', 'Cub F1 troncal 2')
    cub_troncal_2.obj_id, cub_troncal_2.obj_bus = troncal_2, 0
    fuente = red.CreateObject('ElmXnet', 'Fuente F1')
    cub_fuente = barra_fuente.CreateObject('StaCubic', 'Cub Fuente F1')
    cub_fuente.obj_id, cub_fuente.obj_bus = fuente, 0

    cargas = [o for o in app.proyecto.GetContents('*.ElmLod', 1)
              if o.loc_name.startswith('F1_')]
    for carga in cargas:
        carga.SetAttribute('p:alimentador', ['F1'])
    carga_fija = _carga(app, 'F1_S4')
    elm._objs.remove(carga_fija)  # la segunda troncal queda fuera de ElmFeeder.GetObjs

    def ejecutar_flujo_dos_troncales():
        object.__setattr__(app.ldf, 'ejecuciones', app.ldf.ejecuciones + 1)
        activas = [c for c in cargas if not int(getattr(c, 'outserv', 0) or 0)]
        p_total = sum(float(c.plini or 0.0) for c in activas)
        q_total = sum(float(c.qlini or 0.0) for c in activas)
        s2 = p_total * p_total + q_total * q_total
        perdida_p, perdida_q = 0.02 * s2, 0.04 * s2
        p_1 = sum(float(c.plini or 0.0) for c in elm.GetObjs('ElmLod'))
        q_1 = sum(float(c.qlini or 0.0) for c in elm.GetObjs('ElmLod'))
        fraccion_1 = p_1 / p_total if p_total else 0.5
        object.__setattr__(cub_troncal_1.obj_id, 'm_Psum:bus1',
                           p_1 + perdida_p * fraccion_1)
        object.__setattr__(cub_troncal_1.obj_id, 'm_Qsum:bus1',
                           q_1 + perdida_q * fraccion_1)
        object.__setattr__(troncal_2, 'm_Psum:bus1',
                           p_total - p_1 + perdida_p * (1.0 - fraccion_1))
        object.__setattr__(troncal_2, 'm_Qsum:bus1',
                           q_total - q_1 + perdida_q * (1.0 - fraccion_1))
        object.__setattr__(fuente, 'm_Psum:bus1', -(p_total + perdida_p))
        object.__setattr__(fuente, 'm_Qsum:bus1', -(q_total + perdida_q))
        app.ldf_valido = True
        return 0

    object.__setattr__(app.ldf, 'Execute', ejecutar_flujo_dos_troncales)
    clientes = [{'codigo': 'CI-2', 'sed': 'F1_S4', 'pot': 40.0,
                 'ea': 1.0, 'eri': 0.25}]

    informe, rc = guion.ejecutar(app, _plan(kw=300.0, kvar=90.0, clientes=clientes))

    assert rc == 0, informe
    assert informe['cuadrado'] and informe['cabecera']['kw'] == pytest.approx(300.0, rel=0.01)
    assert informe['perdidas']['kw'] > 0
    fija = _sed(informe, 'F1_S4')
    assert fija['origen'] == 'cliente' and fija['despues']['kw'] == pytest.approx(40.0)
    assert all(x['origen'] == 'kva' for x in informe['sed'] if x['sed'] != 'F1_S4')
    medicion = informe['medicion_cabecera']
    assert medicion['metodo'] == 'FUENTE_UNICA'
    assert medicion['cantidad_troncales'] == 2
    assert sum(t['kw'] for t in medicion['troncales']) == pytest.approx(
        informe['cabecera']['kw'])


def test_diferencia_kvar_nativa_es_informativa_y_no_bloquea(guion):
    """006:RF-14 — si EA/ERI de los clientes exige más Q que la cabecera, se cuadra kW,
    se conserva el kVAR del flujo nativo y su diferencia se comunica sin volverla fallo.
    """
    app = _app()
    clientes = [{'codigo': '11', 'sed': 'F1_S2', 'pot': 100.0, 'ea': 1.0, 'eri': 2.0}]

    informe, rc = guion.ejecutar(app, _plan(kw=300.0, kvar=90.0, clientes=clientes))

    assert rc == 0, informe
    assert informe['cuadrado'] and informe['solo_kw']
    diferencia = informe['kvar_no_bloqueante']
    assert informe['status'] == 'AVISO_KVAR'
    assert diferencia['objetivo_kvar'] == pytest.approx(90.0)
    assert diferencia['red_nativa_kvar'] == pytest.approx(informe['cabecera']['kvar'])
    assert diferencia['diferencia_kvar'] == pytest.approx(informe['cabecera']['kvar'] - 90.0)
    assert diferencia['diferencia_relativa'] == pytest.approx(
        diferencia['diferencia_kvar'] / 90.0)
    assert diferencia['tolerancia'] == 0.01 and diferencia['supera_tolerancia']
    assert diferencia['bloquea'] is False
    assert any('red nativa' in a and 'no bloquea' in a for a in informe['avisos'])


def test_cliente_desmarcado_desconecta_su_sed(guion):
    """006:RF-26 — la SED cuyos clientes están todos desmarcados queda fuera de servicio en
    la variación y sin reparto; la que conserva un cliente sigue con la potencia de él."""
    app = _app()
    plan = _plan(clientes=[{'codigo': '13', 'sed': 'F1_S3', 'pot': 30.0, 'ea': 1.0, 'eri': 0.2}])
    plan['desconectados'] = [
        {'codigo': '11', 'sed': 'f1_s2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25},
        {'codigo': '14', 'sed': 'F1_S3', 'pot': 99.0, 'ea': 1.0, 'eri': 0.25},
        {'codigo': '12', 'sed': 'ZZ9', 'pot': 10.0, 'ea': 1.0, 'eri': 0.1}]
    informe, rc = guion.ejecutar(app, plan)
    assert rc == 0, informe
    assert informe['desconectadas'] == [{'sed': 'F1_S2', 'clientes': ['11']}]
    assert 'F1_S2' not in {x['sed'] for x in informe['sed']}
    apagada = [e for e in app.escrituras if e[0] is _carga(app, 'F1_S2') and e[1] == 'outserv']
    assert apagada and apagada[-1][2] == 1 and apagada[-1][3] is not None, 'en la variación'
    assert _sed(informe, 'F1_S3')['despues']['kw'] == pytest.approx(30.0)
    assert any('ZZ9' in a for a in informe['avisos'])
    simulado, _ = guion.ejecutar(_app(), plan, simular=True)
    assert simulado['desconectadas'] == informe['desconectadas']


def test_kva_de_la_entrada_original(guion):
    """006:RF-10 — sin transformador en DIgSILENT, el kVA de la entrada original, y se dice."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True,
                           con_trafos=False)
    informe, rc = guion.ejecutar(app, _plan(kva_entrada={'F1_S1': 100.0, 'F1_S2': 100.0,
                                                         'f1 s3': 200.0}))
    assert rc == 0, informe
    assert {x['kva_de'] for x in informe['sed']} == {'entrada'}
    assert _sed(informe, 'F1_S3')['kva'] == 200.0
    assert any('entrada original' in a for a in informe['avisos'])


def test_sin_kva_en_ningun_sitio_no_se_escribe(guion):
    """006:RF-24 — una SED sin kVA ni en DIgSILENT ni en la entrada: error y nada escrito."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True,
                           con_trafos=False)
    informe, rc = guion.ejecutar(app, _plan(kva_entrada={'F1_S1': 100.0}))
    assert rc == 2 and 'F1_S2' in informe['error']
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')


def test_simular_no_escribe(guion):
    """006:RF-20 — el reparto sin pérdidas por SED, sin variación ni escrituras."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(), simular=True)
    assert rc == 0 and informe['modo'] == 'simular'
    assert informe['totales_sin_perdidas']['kw'] == pytest.approx(300.0)
    assert not app.escrituras and app.ldf.ejecuciones == 0


def test_no_converge_remedios_y_ajustes_restituidos(guion):
    """006:RF-15 / 006:RF-16 / 006:RF-17 — remedios por orden, el informe dice qué cambió, y el
    ComLdf del operador queda como estaba."""
    app = _app()
    # MW de carga de F1: con 900 kW hacen falta dos remedios (F2 tiene 0,3 MW y converge).
    app.ldf.limite, app.ldf.por_ajuste = 0.6, 0.2
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 0 and informe['cuadrado'], informe
    nombres = [r['remedio'] for r in informe['remedios']]
    assert nombres[:3] == ['acercarse en pasos', 'más iteraciones', 'paso automático']
    assert any('itrlx: 25 → 75' in c for r in informe['remedios'] for c in r['cambios'])
    assert app.ldf.itrlx == 25 and app.ldf.iStepAdapt == 0
    assert informe['ajustes_restituidos'] == {'itrlx': 25, 'iStepAdapt': 0}
    assert 'sed_por_encima_de_su_transformador' in informe['diagnostico']


def test_sin_cuadrar_queda_el_ultimo_que_convergio(guion):
    """006:RF-18 — agotados los remedios: variación con el último reparto bueno, marcada."""
    app = _app(kva=lambda f, i: 100.0)
    app.ldf.limite = 0.5
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 2 and not informe['cuadrado']
    assert any('NO cumple' in a for a in informe['avisos'])
    total = sum(_carga(app, f'F1_S{i}').plini for i in range(1, 7))
    assert total <= 0.5 + 1e-9
    # 900 kW entre 6 SED de 100 kVA: cada una pedía más que su transformador.
    assert len(informe['diagnostico']['sed_por_encima_de_su_transformador']) == 6
    assert informe['cabecera'] is not None
    assert informe['diagnostico']['tension_minima']['barra'].startswith('F1_')


def test_cancelar(guion):
    """006:RF-22 — cancelar termina el flujo en curso y deja el último reparto que convergió."""
    app = _app()
    llamadas = []

    def cancelado():
        llamadas.append(1)
        return len(llamadas) > 1

    informe, _rc = guion.ejecutar(app, _plan(tolerancia=0.001), cancelado=cancelado)
    assert informe['cancelado'] and informe['flujos'] == 1
    assert any('Cancelado' in a for a in informe['avisos'])


def test_sin_cabecera_no_se_ajusta(guion):
    """006:RF-4 — un alimentador sin ElmFeeder con cabecera no se puede medir."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=2, flujo=True)
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 2 and 'cabecera' in informe['error']


def test_error_inesperado_deja_informe(guion, tmp_path, monkeypatch):
    """008:RF-17 — si ``ejecutar`` revienta, ``main`` escribe el informe con el error y su tipo."""
    import json
    import sys
    import types

    app = _app()
    monkeypatch.setitem(sys.modules, 'powerfactory', types.SimpleNamespace(GetApplicationExt=lambda: app))

    def revienta(*_a, **_k):
        raise AttributeError("'NoneType' object has no attribute 'obj_id'")

    monkeypatch.setattr(guion, 'ejecutar', revienta)
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps(_plan()), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    rc = guion.main(['--plan', str(plan), '--output-json', str(salida)])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert rc == 1
    assert 'AttributeError' in informe['error'] and 'obj_id' in informe['error']
    assert informe['feeder'] == 'F1' and informe['modo'] == 'aplicar'


def test_ajustes_anteriores_activos_sin_los_tres_casos(guion):
    """006:RF-19 / 011:RF-50 — con un solo caso de estudio y ajustes anteriores del mismo
    alimentador activos, con etapas de la misma fecha, el ajuste nuevo graba en su etapa.

    SI213 (2026-10-12): tres ajustes activos y la etapa del cuarto no quedó grabando
    (manual de PF 2024, 16.5); el guion paraba sin escribir nada.
    """
    app = _app()
    instante = int(getattr(app.GetActiveStudyCase(), 'iStudyTime', 0) or 0)
    anteriores = []
    for stamp in ('20261009_154733', '20261009_160119', '20261010_054313'):
        v = app.carpetas['scheme'].CreateObject('IntScheme', f'Ajuste_F1_{stamp}')
        v.NewStage(f'Etapa_{stamp}', instante, 1)
        anteriores.append(v)
    app.grabando = None
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert informe['variacion'] not in [v.loc_name for v in anteriores]
    assert all(v not in app.variaciones_activas for v in anteriores)
    assert any('Ajustes anteriores desactivados' in a for a in informe['avisos'])
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    assert escritas and all(e[3] is not None and e[3]._padre.loc_name == informe['variacion']
                            for e in escritas)


def test_etapa_empatada_graba_con_las_demas_activas(guion):
    """006:RF-19 — si otra variación activa tiene una etapa de la misma fecha, la nueva graba
    igual y la otra sigue activa (las cargas de la spec 007 van sobre el ajuste activo)."""
    import cargas_pf

    app = _app()
    base = app.carpetas['scheme'].CreateObject('IntScheme', 'Ajuste_F1_20261009_120000')
    base.NewStage('Etapa_base', 0, 1)
    app.caso.iStudyTime = 0
    variacion, etapa = cargas_pf.crear_variacion(app, 'Carga_N1_F1', 'n1')
    assert app.GetRecordingStage() is etapa
    assert base in app.variaciones_activas and variacion in app.variaciones_activas


def test_etapa_que_no_graba_nombra_las_variaciones(guion):
    """006:RF-19 — si DIgSILENT sigue sin dejar grabar la etapa nueva, no se escribe nada, la
    variación vacía no se queda activa y el error nombra las variaciones con las que choca.

    En una copia de SI213 (2026-10-12) la etapa nueva grababa hasta reactivar el cuarto
    ajuste: esa variación se modela aquí quitando la grabación al activarse.
    """
    import cargas_pf

    app = _app()
    rebelde = app.carpetas['scheme'].CreateObject('IntScheme', 'Ajuste_F1_20261009_160119')
    rebelde.NewStage('Etapa_rebelde', 0, 1)
    app.caso.iStudyTime = 0
    original = rebelde.Activate

    def activa(*a):
        r = original(*a)
        app.grabando = None
        return r

    object.__setattr__(rebelde, 'Activate', activa)
    with pytest.raises(RuntimeError, match='Ajuste_F1_20261009_160119') as exc:
        cargas_pf.crear_variacion(app, 'Carga_N1_F1', 'n1')
    assert 'no quedó grabando' in str(exc.value)
    assert [v.loc_name for v in app.variaciones_activas] == ['Ajuste_F1_20261009_160119']


def _con_escenario_que_manda(**kw):
    """Proyecto con el escenario del operador guardando las demandas importadas, como el
    «Operation Scenario» de SI213: con él activo manda su potencia, no la de la variación."""
    app = _app(escenario=True, **kw)
    app.escenario_manda = True
    app.escenario.fotografiar()
    return app


def test_el_escenario_lleva_el_ajuste(guion):
    """006:RF-27 / 006:RF-29 — con el escenario restaurado la cabecera es la ajustada, no la
    de las demandas que guardaba el escenario.

    SI213 (2026-10-12): cuadró a 1.621,8 kW y, con el «Operation Scenario» activo, la
    verificación medía 229,2 kW.
    """
    rnd = random.Random(SEMILLA)
    app = _con_escenario_que_manda(n=rnd.randint(3, 12))
    objetivo = rnd.uniform(400.0, 900.0)
    informe, rc = guion.ejecutar(app, _plan(kw=objetivo, kvar=objetivo * 0.3))
    assert rc == 0, (SEMILLA, informe)
    assert app.GetActiveScenario() is not None
    medida, con_esc = informe['cabecera'], informe['cabecera_con_escenario']
    assert con_esc['kw'] == pytest.approx(medida['kw'], rel=1e-6), SEMILLA
    assert con_esc['kvar'] == pytest.approx(medida['kvar'], rel=1e-6), SEMILLA
    assert [g['escenario'] for g in informe['escenarios']] == ['Operador']
    assert app.escenario.guardados >= 1
    for x in informe['sed']:
        assert _carga(app, x['sed']).plini * 1000.0 == pytest.approx(x['despues']['kw'])
    assert not any('no tomó' in a for a in informe['avisos'])


def test_cabecera_con_escenario_distinta_se_avisa(guion, monkeypatch):
    """006:RF-30 — si el escenario no toma las demandas, el aviso da las dos cabeceras."""
    app = _con_escenario_que_manda()
    monkeypatch.setattr(guion, 'grabar_en_escenario',
                        lambda app, filas, apagar=(): {'escenario': 'Operador', 'cargas': 0,
                                                       'fallos': []})
    informe, _rc = guion.ejecutar(app, _plan())
    assert informe['cuadrado'], informe
    aviso = next(a for a in informe['avisos'] if 'no tomó' in a)
    assert f"{informe['cabecera']['kw']:.1f} kW" in aviso
    assert f"{informe['cabecera_con_escenario']['kw']:.1f} kW" in aviso


def test_sed_desconectada_tambien_en_el_escenario(guion):
    """006:RF-27 — la SED de RF-26 queda fuera de servicio también con el escenario activo."""
    app = _con_escenario_que_manda()
    plan = _plan()
    plan['desconectados'] = [{'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]
    informe, rc = guion.ejecutar(app, plan)
    assert rc == 0, informe
    assert [d['sed'] for d in informe['desconectadas']] == ['F1_S2']
    apagadas = [e for e in app.escrituras if e[1] == 'outserv' and e[0].loc_name == 'F1_S2']
    assert any(e[4] is None for e in apagadas) and any(e[4] is app.escenario for e in apagadas)
