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
            'native_action_context': contexto_nativo('P', ['F1'], 'ajuste'),
            # 015:RF-13: la web solo manda a calibrar alimentadores con el base verificado.
            'caso_base_sin_verificar': {}}


def _carga(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == nombre)


def _sed(informe, sed):
    return next(x for x in informe['sed'] if x['sed'] == sed)


def _caso(app, nombre):
    """Uno de los tres casos de la 011, que el ajuste prepara si faltan (014:RF-5)."""
    return next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre)


def test_cuadra_la_cabecera_en_el_escenario_de_sin_proyecto(guion):
    """006:RF-4 / 006:RF-11 / 006:RF-21 / 006:RF-40 / 015:RF-20 / 015:RF-26 — solo el
    alimentador elegido, en el escenario de «Sin proyecto» y sin crear ninguna variación;
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
    # «error» es solo para fallos: la web lo toma por uno y paraba un ajuste que cuadró.
    assert 'error' not in informe and 'variacion' not in informe
    assert informe['perdidas']['kw'] > 0 and 1 <= informe['flujos'] < 20
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == []
    assert informe['caso'] == 'Sin proyecto' and informe['escenario'] == 'Sin proyecto'
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    # Todo con el escenario de «Sin proyecto» activo y ninguna etapa grabando.
    assert escritas and all(e[3] is None and e[4] is not None and e[4].loc_name == 'Sin proyecto'
                            for e in escritas)
    assert app.escenario is not None, 'el caso del operador vuelve con su escenario'
    assert _carga(app, 'F2_S1').plini == otra
    fila = _sed(informe, 'F1_S3')
    assert fila['antes']['kw'] == pytest.approx(50.0) and fila['kva_de'] == 'pf'


def test_sin_caso_base_verificado_no_se_calibra(guion):
    """015:RF-13, 015:RF-17 — sin «Sin proyecto» y sin el «Caso base» verificado no se crea
    nada ni se escribe: el informe dice por qué."""
    app = _app()
    for estado in ({'F1': ['flujo']}, None):
        plan = _plan()
        if estado is None:
            del plan['caso_base_sin_verificar']
        else:
            plan['caso_base_sin_verificar'] = estado
        informe, rc = guion.ejecutar(app, plan)
        assert rc == 2 and 'no está verificado' in informe['error']
    assert not app.escrituras
    assert [c.loc_name for c in app.carpetas['study'].GetContents('*.IntCase')] == ['Caso']


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


def test_estado_manual_correcto_se_adopta_sin_recibo(guion):
    """006:RF-41 — la prueba física basta: no se exige que la calibración la haya hecho
    esta aplicación, ni que deje variación."""
    app = _app()
    plan = _plan(clientes=[
        {'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25},
    ])
    aplicado, rc = guion.ejecutar(app, plan)
    assert rc == 0, aplicado
    app.escrituras.clear()

    adoptado, rc = guion.ejecutar(app, plan)

    assert rc == 0, adoptado
    assert adoptado['decision_carga_nativa']['status'] == 'YA_CARGADO_VALIDADO'
    assert 'variacion' not in adoptado
    assert app.escrituras == []
    assert app.carpetas['scheme'].GetContents('*.IntScheme') == []


def test_un_factor_de_escala_distinto_obliga_a_recalibrar(guion):
    """006:RF-41 / 015:RF-44 — si una escalada no lleva el factor de las demás, el estado
    no es el calibrado y se vuelve a cuadrar."""
    app = _app()
    plan = _plan()
    aplicado, rc = guion.ejecutar(app, plan)
    assert rc == 0, aplicado
    _caso(app, 'Sin proyecto').Activate()
    otra = next(x['sed'] for x in aplicado['sed'] if x['origen'] == 'escala')
    _carga(app, otra).scale0 = 2.0 * _carga(app, otra).scale0

    corregido, rc = guion.ejecutar(app, plan)

    assert rc == 0, corregido
    assert corregido['decision_carga_nativa']['status'] == 'REQUIERE_DISTRIBUCION'
    assert any(f['tipo'] == 'REPARTO_P_NO_PROPORCIONAL'
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
    """015:RF-23 / 006:RF-8 / 015:RF-44 — usuario, 2026-10-15: las escaladas se reparten por la
    potencia instalada de su SED; P base = kVA × FP en ``plini`` y un mismo ``scale0`` en
    todas, que es la fracción de carga de sus transformadores."""
    rnd = random.Random(SEMILLA)
    tamanos = {i: rnd.choice([25.0, 50.0, 100.0, 160.0, 250.0]) for i in range(1, 30)}
    app = _app(n=rnd.randint(5, 25), kva=lambda f, i: tamanos[i])
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 0, (SEMILLA, informe)
    fp = 900.0 / math.hypot(900.0, 250.0)
    factores = set()
    for x in informe['sed']:
        carga = _carga(app, x['sed'])
        assert carga.plini * 1000.0 == pytest.approx(x['kva'] * fp), SEMILLA
        assert x['despues']['kw'] / x['kva'] == pytest.approx(fp * carga.scale0)
        factores.add(round(carga.scale0, 9))
    assert len(factores) == 1, SEMILLA
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


def _reparto_de(app, consumo_relativo, *, fija=None):
    """Dos cargas de F1 con su consumo en el flujo: lo escrito por ``consumo_relativo``.

    ``fija``: el nombre de la que queda fija (sin base), con 500 kW y 100 kVAR escritos.
    """
    objetos = [o for o in app.proyecto.GetContents('*.ElmLod', 1)
               if o.loc_name.startswith('F1_')]
    cargas = {o.loc_name: o for o in objetos}
    demandas, base = {}, {}
    for i, obj in enumerate(objetos, 1):
        es_fija = obj.loc_name == fija
        p, q = (0.5, 0.1) if es_fija else (float(i), i / 10.0)
        obj.plini, obj.qlini, obj.i_scale, obj.scale0 = p, q, 0 if es_fija else 1, 1.0
        object.__setattr__(obj, 'm:Psum:bus1', p * consumo_relativo)
        object.__setattr__(obj, 'm:Qsum:bus1', q * consumo_relativo)
        demandas[obj.loc_name] = SimpleNamespace(kw=1000.0 * p, kvar=1000.0 * q)
        if not es_fija:
            base[obj.loc_name] = (1000.0 * p, 1000.0 * q)
    reparto = SimpleNamespace(
        demandas=demandas, base=base, solo_kw=False, a=1.0, b=1.0,
        con_factores=lambda _a, _b: object(),
    )
    return cargas, reparto


def test_validacion_de_perdidas_usa_consumo_efectivo_no_plini(guion):
    """006:RF-11 / 015:RF-50 — las pérdidas, la cabecera menos lo que consumen las cargas.

    Con las cargas consumiendo lo escrito, el balance cuadra: cabecera = fijas +
    escaladas + pérdidas.
    """
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app(n=2)
    cargas, reparto = _reparto_de(app, 1.0, fija='F1_S1')

    validacion, reconstruido = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 2600.0, 260.0),
        Objetivo(2600.0, 260.0, 'M1', 'F1'), 0.01, ajustes_flujo={'iopt_lev': 0},
    )

    assert validacion['correcta'] is True, validacion['fallos']
    assert validacion['consumo_cargas_efectivo']['kw'] == pytest.approx(2500.0)
    assert validacion['consumo_cargas_efectivo']['origen'] == 'RESULTADOS_CARGAS_NATIVAS'
    balance = validacion['balance']
    assert balance['fijas_consumida_kw'] == pytest.approx(500.0)
    assert balance['escaladas_consumida_kw'] == pytest.approx(2000.0)
    assert balance['escrita_kw'] == pytest.approx(2500.0)
    assert balance['perdidas_kw'] == pytest.approx(100.0)
    assert balance['cabecera_kw'] == pytest.approx(
        balance['fijas_consumida_kw'] + balance['escaladas_consumida_kw']
        + balance['perdidas_kw'])
    assert reconstruido is not None


def test_carga_que_consume_menos_de_lo_escrito_no_es_valida(guion):
    """015:RF-47 / 015:RF-48 / 015:RF-49 / 015:RF-51 — CA101, 2026-10-15: con la adaptación
    automática del modelo las cargas consumían lo escrito por u² y la relectura de lo
    escrito daba «válido». Ahora la fija y la escalada que no consumen lo suyo se nombran,
    con lo escrito, lo consumido y el ajuste del flujo como causa."""
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app(n=2)
    cargas, reparto = _reparto_de(app, 0.73, fija='F1_S1')

    validacion, reconstruido = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 2000.0, 200.0),
        Objetivo(2000.0, 200.0, 'M1', 'F1'), 0.01,
        ajustes_flujo={'iopt_lev': 1, 'iopt_pq': 0},
    )

    assert validacion['correcta'] is False and reconstruido is None
    fallo = next(f for f in validacion['fallos']
                 if f['tipo'] == 'CONSUMO_DISTINTO_DE_LO_ESCRITO')
    assert fallo['cantidad'] == 2 and fallo['fijas'] == 1
    assert 'iopt_lev=1' in fallo['causa_probable'] and 'iopt_pq' not in fallo['causa_probable']
    fija = next(c for c in fallo['cargas'] if c['sed'] == 'F1_S1')
    assert fija['p_escrita_kw'] == pytest.approx(500.0)
    assert fija['p_consumida_kw'] == pytest.approx(365.0)
    assert validacion['balance']['fijas_consumida_kw'] == pytest.approx(365.0)
    assert validacion['balance']['causa_probable'] == fallo['causa_probable']
    detalle = next(d for d in validacion['cargas'] if d['sed'] == 'F1_S1')
    assert not detalle['correcta'] and any('consume P=' in e for e in detalle['errores'])
    aviso = guion.aviso_consumo_fisico(validacion)
    assert aviso.startswith('VALIDACION_FISICA') and 'F1_S1' in aviso and 'iopt_lev' in aviso

    # 015:RF-59 — PA217, 2026-10-16: sin la adaptación no convergía ni con las escaladas
    # casi en cero; el aviso nombra a la fija que pide más que su transformador.
    historial = [{'a': 0.08, 'converge': False}, {'a': 0.005, 'converge': False},
                 {'a': 0.08, 'converge': True}]
    sobre = [{'sed': 'F1_S1', 'kva_carga': 3818.0, 'kva': 400.0, 'carga_pct': 954.5}]
    aviso = guion.aviso_consumo_fisico(validacion, historial, sobre)
    assert 'ni con las escaladas al 0.5%' in aviso
    assert 'F1_S1 3,818 kVA en 400 kVA (954 %)' in aviso and '015:RF-59' in aviso
    assert guion.aviso_consumo_fisico(validacion, historial[2:]).count(';') == aviso.count(';') - 2


def test_toda_sed_no_fija_escalada_y_participando(guion):
    """015:RF-68 — el informe cuenta, carga por carga, las escaladas con su factor, con su
    potencia instalada y con consumo en el flujo, y nombra la que no tiene potencia instalada
    (en Chincha, 2026-10-28, las cargas de un trafomix M… y de un regulador)."""
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app(n=3)
    cargas, reparto = _reparto_de(app, 1.0, fija='F1_S1')
    validacion, _ = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 5600.0, 560.0),
        Objetivo(5600.0, 560.0, 'M1', 'F1'), 0.01)
    assert validacion['correcta'] is True, validacion['fallos']
    part = validacion['participacion']
    assert (part['fijas'], part['escaladas'], part['con_escala'], part['con_potencia'],
            part['consumen']) == (1, 2, 2, 2, 2)
    assert part['factor_comun'] == pytest.approx(1.0) and part['sin_potencia_instalada'] == []

    # Una escalada sin potencia instalada: queda en cero, sin consumo, y se nombra.
    sin = 'F1_S3'
    cargas[sin].plini = cargas[sin].qlini = 0.0
    object.__setattr__(cargas[sin], 'm:Psum:bus1', 0.0)
    object.__setattr__(cargas[sin], 'm:Qsum:bus1', 0.0)
    reparto.base[sin] = (0.0, 0.0)
    reparto.demandas[sin] = SimpleNamespace(kw=0.0, kvar=0.0)
    validacion, _ = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 2600.0, 260.0),
        Objetivo(2600.0, 260.0, 'M1', 'F1'), 0.01)
    part = validacion['participacion']
    assert (part['escaladas'], part['con_escala'], part['con_potencia'], part['consumen']) == (2, 2, 1, 1)
    assert part['sin_potencia_instalada'] == [sin]


def test_fija_con_su_p_pero_otra_q_en_el_flujo_no_es_valida(guion):
    """015:RF-47 — la Q de una fija también se compara con lo que consume."""
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app(n=2)
    cargas, reparto = _reparto_de(app, 1.0, fija='F1_S1')
    object.__setattr__(cargas['F1_S1'], 'm:Qsum:bus1', 0.05)

    validacion, _ = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 2600.0, 260.0),
        Objetivo(2600.0, 260.0, 'M1', 'F1'), 0.01,
    )

    fallo = next(f for f in validacion['fallos']
                 if f['tipo'] == 'CONSUMO_DISTINTO_DE_LO_ESCRITO')
    assert [c['sed'] for c in fallo['cargas']] == ['F1_S1']
    assert fallo['causa_probable'] is None


def test_carga_sin_resultado_del_flujo_no_queda_verificada(guion):
    """015:RF-52 — tras un flujo convergente, una carga sin P consumida no se da por buena."""
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app(n=2)
    cargas, reparto = _reparto_de(app, 1.0, fija='F1_S1')
    object.__delattr__(cargas['F1_S2'], 'm:Psum:bus1')

    validacion, reconstruido = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 2600.0, 260.0),
        Objetivo(2600.0, 260.0, 'M1', 'F1'), 0.01,
    )

    assert validacion['correcta'] is False and reconstruido is None
    fallo = next(f for f in validacion['fallos']
                 if f['tipo'] == 'CARGAS_SIN_RESULTADO_DEL_FLUJO')
    assert fallo['sed'] == ['F1_S2']
    assert validacion['balance']['escaladas_consumida_kw'] is None
    assert validacion['balance']['perdidas_kw'] is None


def test_no_redistribuir_informa_perdidas_con_consumo_efectivo(guion):
    """006:RF-11 / 006:RF-41 / 015:RF-50 — la rama NO_REDISTRIBUIR mide pérdidas como la
    validación.

    En CA101 reabierto (168 cargas, ``_6`` reutilizada) el informe restaba la ``plini``
    escrita a la cabecera y daba -846 kW de pérdidas, mientras el flujo aplicado sobre el
    mismo estado daba +499,8 kW.
    """
    app = _app()
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    efectivo = sum(1000.0 * o.plini * o.scale0 for o in app.proyecto.GetContents('*.ElmLod', 1)
                   if o.loc_name.startswith('F1_'))

    segundo, rc = guion.ejecutar(app, _plan())

    assert rc == 0, segundo
    assert segundo['decision_carga_nativa']['accion'] == 'NO_REDISTRIBUIR'
    consumo = segundo['validacion_previa_nativa']['consumo_cargas_efectivo']
    assert consumo['origen'] == 'RESULTADOS_CARGAS_NATIVAS'
    assert consumo['kw'] == pytest.approx(efectivo)
    assert segundo['consumo_cargas_efectivo']['kw'] == pytest.approx(efectivo)
    assert segundo['perdidas_de'] == 'RESULTADOS_CARGAS_NATIVAS'
    assert segundo['perdidas']['kw'] == pytest.approx(segundo['cabecera']['kw'] - efectivo)
    balance = segundo['validacion_previa_nativa']['balance']
    assert balance['perdidas_kw'] == pytest.approx(segundo['perdidas']['kw'])


def test_calibracion_con_cargas_dependientes_de_la_tension_no_es_valida(guion):
    """015:RF-47 / 015:RF-49 / 015:RF-51 / 015:RF-69 — CA101 en DIgSILENT, 2026-10-15: las
    cargas consumían lo escrito por u² con ``iopt_lev=1`` y la calibración quedaba «válida».
    Ahora no lo es y el aviso nombra la fija que no consume lo suyo y el ajuste del flujo;
    el reparto que cuadró queda grabado y ninguna escalada vuelve a cero (SL144 + SM117)."""
    app = _app()
    object.__setattr__(app.ldf, 'iopt_lev', 1)
    antes = {o.loc_name: (o.plini, o.scale0) for o in app.proyecto.GetContents('*.ElmLod', 1)}
    for obj in app.proyecto.GetContents('*.ElmLod', 1):
        object.__setattr__(obj, 'consumo_relativo', 0.9)
    clientes = [{'codigo': 'CI-1', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]

    informe, rc = guion.ejecutar(app, _plan(clientes=clientes))

    assert rc == 2
    assert informe['status'] == 'FALLO_VALIDACION_NATIVA' and not informe['cuadrado']
    assert 'calibracion_revertida' not in informe and informe['calibracion_sin_validar'] is True
    assert informe['escenarios'], 'el reparto que cuadró se graba'
    aviso = next(a for a in informe['avisos'] if a.startswith('VALIDACION_FISICA'))
    assert 'F1_S2' in aviso and 'iopt_lev=1' in aviso
    balance = informe['validacion_posterior_nativa']['balance']
    assert balance['fijas_consumida_kw'] == pytest.approx(0.9 * balance['fijas_escrita_kw'])
    escaladas = {d['sed'] for d in informe['validacion_posterior_nativa']['cargas']
                 if d['clase'] == 'ESCALABLE'}
    despues = {o.loc_name: (o.plini, o.scale0) for o in app.proyecto.GetContents('*.ElmLod', 1)}
    assert escaladas and despues != antes
    assert all(despues[s][0] * despues[s][1] > 0 for s in escaladas)


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
        p_total = sum(float(c.plini or 0.0) * c.scale0 for c in activas)
        q_total = sum(float(c.qlini or 0.0) * c.scale0 for c in activas)
        s2 = p_total * p_total + q_total * q_total
        perdida_p, perdida_q = 0.02 * s2, 0.04 * s2
        p_1 = sum(float(c.plini or 0.0) * c.scale0 for c in elm.GetObjs('ElmLod'))
        q_1 = sum(float(c.qlini or 0.0) * c.scale0 for c in elm.GetObjs('ElmLod'))
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
        # Lo que consume cada carga, como DIgSILENT tras el flujo (015:RF-47, RF-52).
        for c in activas:
            object.__setattr__(c, 'm_Psum:bus1', float(c.plini or 0.0) * c.scale0)
            object.__setattr__(c, 'm_Qsum:bus1', float(c.qlini or 0.0) * c.scale0)
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
    assert all(x['origen'] == 'escala' for x in informe['sed'] if x['sed'] != 'F1_S4')
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
    """006:RF-26 / 015:RF-20 — la SED cuyos clientes están todos desmarcados queda fuera de
    servicio en el escenario de «Sin proyecto» y sin reparto; la que conserva un cliente
    sigue con la potencia de él."""
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
    assert any(e[2] == 1 and e[3] is None and e[4].loc_name == 'Sin proyecto' for e in apagada)
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


def test_sin_kva_en_ningun_sitio_se_calibra_igual(guion):
    """006:RF-24 (cambiado por 015:RF-44) — el factor de escala no necesita el kVA: una SED
    sin kVA ni en DIgSILENT ni en la entrada no impide calibrar."""
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=3, bt=True, flujo=True,
                           con_trafos=False)
    informe, rc = guion.ejecutar(app, _plan(kva_entrada={'F1_S1': 100.0}))
    assert rc == 0 and informe['cuadrado'], informe
    assert not app.carpetas['scheme'].GetContents('*.IntScheme')


def test_simular_no_escribe(guion):
    """006:RF-20 — el reparto sin pérdidas por SED, sin variación ni escrituras."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(), simular=True)
    assert rc == 0 and informe['modo'] == 'simular'
    assert informe['totales_sin_perdidas']['kw'] == pytest.approx(300.0)
    assert not app.escrituras and app.ldf.ejecuciones == 0


def test_no_converge_remedios_y_ajustes_restituidos(guion):
    """006:RF-15 / 006:RF-16 / 006:RF-17 / 015:RF-46 — remedios por orden, el informe dice qué
    cambió, y en «Sin proyecto» se quedan si cuadra."""
    app = _app()
    # MW de carga de F1: con 900 kW hacen falta dos remedios (F2 tiene 0,3 MW y converge).
    app.ldf.limite, app.ldf.por_ajuste = 0.6, 0.2
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 0 and informe['cuadrado'], informe
    nombres = [r['remedio'] for r in informe['remedios']]
    assert nombres[:3] == ['acercarse en pasos', 'más iteraciones', 'paso automático']
    assert any('itrlx: 25 → 75' in c for r in informe['remedios'] for c in r['cambios'])
    # 015:RF-46: cuadró en «Sin proyecto», caso del sistema: los ajustes se quedan para que
    # el caso siga convergiendo, y se dicen.
    assert app.ldf.itrlx == 75 and app.ldf.iStepAdapt == 1
    assert informe['ajustes_del_flujo_conservados'] == {'itrlx': 75, 'iStepAdapt': 1}
    assert 'ajustes_restituidos' not in informe
    assert any('015:RF-46' in a for a in informe['avisos'])
    assert 'sed_por_encima_de_su_transformador' in informe['diagnostico']


def test_sin_cuadrar_queda_el_ultimo_que_convergio(guion):
    """006:RF-18 — agotados los remedios: variación con el último reparto bueno, marcada."""
    app = _app(kva=lambda f, i: 100.0)
    app.ldf.limite = 0.5
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 2 and not informe['cuadrado']
    assert any('NO cumple' in a for a in informe['avisos'])
    # Lo que consumen: la base por el factor de escala (015:RF-44).
    total = sum(_carga(app, f'F1_S{i}').plini * _carga(app, f'F1_S{i}').scale0
                for i in range(1, 7))
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


def test_ajustes_de_antes_de_la_015_no_se_tocan(guion):
    """014:RF-3 / 015:RF-26 — los ajustes de antes de la spec 015 activos donde se calibra
    no se apagan ni se borran, y se dicen; la calibración nueva no crea ninguna variación.

    SI213 (2026-10-12): tres ajustes activos con etapas de la misma fecha y la etapa del
    cuarto no quedó grabando; desde la 015 ya no hay etapa que grabar."""
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
    assert informe['variaciones_de_ajustes_previos'] == [v.loc_name for v in anteriores]
    assert any('antes de la spec 015' in a for a in informe['avisos'])
    assert sorted(app.carpetas['scheme'].GetContents('*.IntScheme'), key=lambda v: v.loc_name) == anteriores
    escritas = [e for e in app.escrituras if getattr(e[0], '_clase', '') == 'ElmLod']
    assert escritas and all(e[3] is None for e in escritas)


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


def test_etapa_que_no_graba_nombra_las_variaciones(guion, monkeypatch):
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
    # Con fechas escalonadas ya no empatan; se fuerza el empate para probar el error.
    monkeypatch.setattr(cargas_pf, 'fecha_de_etapa_nueva', lambda *_a: 0)
    with pytest.raises(RuntimeError, match='Ajuste_F1_20261009_160119') as exc:
        cargas_pf.crear_variacion(app, 'Carga_N1_F1', 'n1')
    assert 'no quedó grabando' in str(exc.value)
    assert [v.loc_name for v in app.variaciones_activas] == ['Ajuste_F1_20261009_160119']


def test_etapas_nuevas_con_fecha_propia_antes_del_estudio(guion):
    """016:RF-74 — cada etapa nueva toma la siguiente fecha libre antes de la del estudio.

    IN111 + TA225 (2026-10-15): con tres o más etapas activas de la misma fecha DIgSILENT
    no aplica ninguna; con fechas propias entran todas y la más nueva se aplica la última.
    """
    import cargas_pf

    app = _app()
    app.caso.iStudyTime = 5_000_000
    etapas = [cargas_pf.crear_variacion(app, f'Carga_N{i}_F1', f'n{i}')[1] for i in range(4)]
    fechas = [e.tAcTime for e in etapas]
    assert fechas == sorted(set(fechas)) and fechas[-1] < 5_000_000
    assert fechas[0] == 5_000_000 - cargas_pf.VENTANA_ETAPAS_S
    assert app.GetRecordingStage() is etapas[-1]
    # NewStage lleva la hora del caso a la de la etapa: se devuelve, o las anteriores
    # quedarían después de la hora del estudio, inactivas.
    assert app.caso.iStudyTime == 5_000_000


def _con_escenario_que_manda(**kw):
    """Proyecto con el escenario del operador guardando las demandas importadas, como el
    «Operation Scenario» de SI213: con él activo manda su potencia, no la de la variación."""
    app = _app(escenario=True, **kw)
    app.escenario_manda = True
    app.escenario.fotografiar()
    return app


def test_el_escenario_lleva_el_ajuste(guion, monkeypatch):
    """006:RF-27 / 006:RF-29 / 014:RF-4 / 015:RF-19 / 015:RF-26 / 015:RF-37 — la demanda
    calibrada queda en el escenario de «Sin proyecto» y, si existe, en el de «Con
    proyecto»; el «Caso base» conserva su demanda y su escenario, y ve la marca fija o
    escalable, que DIgSILENT guarda en la red (sonda T1 de la 015).

    SI213 (2026-10-12): cuadró a 1.621,8 kW con el escenario apagado y, con el
    «Operation Scenario» activo, la verificación medía 229,2 kW; ahora se mide con él.
    """
    monkeypatch.setattr(guion, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    rnd = random.Random(SEMILLA)
    app = _con_escenario_que_manda(n=rnd.randint(3, 12))
    objetivo = rnd.uniform(400.0, 900.0)
    sys_casos = __import__('sys').modules['casos_pf']
    monkeypatch.setattr(sys_casos, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    sys_casos.preparar_sin(app, {'project': 'P', 'feeders': ['F1'], 'caso_base_sin_verificar': {}})
    _con_proyecto(app)
    operador = app.escenario
    antes_base = {c.loc_name: c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)}
    informe, rc = guion.ejecutar(app, _plan(kw=objetivo, kvar=objetivo * 0.3))
    assert rc == 0, (SEMILLA, informe)
    assert [g['escenario'] for g in informe['escenarios']] == ['Sin proyecto', 'Con proyecto']
    assert operador.loc_name == 'Operador' and operador.guardados == 0
    for nombre in ('Sin proyecto', 'Con proyecto'):
        _caso(app, nombre).Activate()
        assert app.GetActiveScenario().loc_name == nombre
        for x in informe['sed']:
            carga = _carga(app, x['sed'])
            assert carga.plini * carga.scale0 * 1000.0 == pytest.approx(x['despues']['kw']), nombre
    _caso(app, 'Caso base').Activate()
    assert app.GetActiveScenario() is operador
    assert {c.loc_name: c.plini for c in app.proyecto.GetContents('*.ElmLod', 1)} == antes_base
    marcas = {x['sed']: _carga(app, x['sed']).i_scale for x in informe['sed']}
    assert set(marcas.values()) <= {0, 1} and 1 in marcas.values()


def test_sed_desconectada_tambien_en_con_proyecto(guion, monkeypatch):
    """006:RF-27 / 014:RF-4 — la SED de RF-26 queda fuera de servicio en el escenario de
    «Sin proyecto» y en el de «Con proyecto»; nada fuera de un escenario."""
    app = _con_escenario_que_manda()
    sys_casos = __import__('sys').modules['casos_pf']
    monkeypatch.setattr(sys_casos, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    _con_proyecto(app)
    plan = _plan()
    plan['desconectados'] = [{'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]
    informe, rc = guion.ejecutar(app, plan)
    assert rc == 0, informe
    assert [d['sed'] for d in informe['desconectadas']] == ['F1_S2']
    apagadas = [e for e in app.escrituras if e[1] == 'outserv' and e[0].loc_name == 'F1_S2']
    assert apagadas and all(e[4] is not None for e in apagadas)
    assert {e[4].loc_name for e in apagadas} == {'Sin proyecto', 'Con proyecto'}


def _con_proyecto(app):
    """«Con proyecto» copia de «Sin proyecto», como lo deja la inserción de cargas (015:RF-28)."""
    import sys

    informe, rc = sys.modules['casos_pf'].preparar_con(
        app, {'project': 'P', 'feeders': ['F1'], 'caso_base_sin_verificar': {}})
    assert rc == 0, informe


# =========================================================================== spec 014
def _trafo(app, nombre='TR_F1_S1'):
    return next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == nombre)


def _activas(app, nombre):
    previo = app.caso
    _caso(app, nombre).Activate()
    out = [v.loc_name for v in app.GetActiveNetworkVariations()]
    esc = app.GetActiveScenario()
    previo.Activate()
    return out, esc


def test_el_ajuste_conserva_las_variaciones_del_operador(guion, monkeypatch):
    """014:RF-1, 014:RF-2, 014:RF-3, 014:RF-14, 014:RF-15, 014:RF-20 / 015:RF-25, 015:RF-26 — un ajuste
    de antes de la 015 con cambios del operador (CA101 ``_3``: cargas y un ElmTr2) sigue
    activo en «Sin» y «Con», y se mide con él; cada caso termina con su escenario."""
    app = _app(escenario=True)
    sys_casos = __import__('sys').modules['casos_pf']
    monkeypatch.setattr(sys_casos, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    _caso(app, 'Sin proyecto').Activate()
    tipo = app.carpetas['equip'].CreateObject('TypTr2', 'TR_2000kVA')
    tipo.strn = 2.0
    operador = fake_pf.variacion_del_operador(
        app, 'Ajuste_F1_20261009_120000_3',
        [(_carga(app, 'F1_S1'), 'plini', 0.07), (_trafo(app), 'typ_id', tipo)])
    _caso(app, 'Caso base').Activate()
    _con_proyecto(app)
    medidas = []
    original = guion.medir_cabecera

    def medir(app_, elm):
        medidas.append((app_.caso.loc_name, [v.loc_name for v in app_.GetActiveNetworkVariations()]))
        return original(app_, elm)

    monkeypatch.setattr(guion, 'medir_cabecera', medir)
    segundo, rc = guion.ejecutar(app, _plan(kw=360.0, kvar=100.0))
    assert rc == 0, segundo
    assert segundo['caso'] == 'Sin proyecto'
    assert segundo['variaciones_de_ajustes_previos'] == [operador.loc_name]
    assert medidas and all(caso == 'Sin proyecto' and operador.loc_name in activas
                           for caso, activas in medidas)
    for nombre in ('Sin proyecto', 'Con proyecto'):
        activas, esc = _activas(app, nombre)
        assert operador.loc_name in activas, nombre
        assert esc is not None and esc.loc_name == nombre
    activas_base, esc_base = _activas(app, 'Caso base')
    assert operador.loc_name not in activas_base and esc_base.loc_name == 'Operador'
    assert _trafo(app).typ_id is tipo


@pytest.mark.parametrize('como', ['termina', 'cancela', 'falla'])
def test_cargas_nuevas_fuera_del_ajuste_y_de_vuelta(guion, monkeypatch, como):
    """014:RF-6, 014:RF-7, 014:RF-8, 014:RF-9 — una variación de carga nueva activa donde se
    mide queda fuera mientras se ajusta y vuelve al terminar, también si se cancela o falla;
    la demanda de la carga nueva no cambia."""
    app = _app(escenario=True)
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    _caso(app, 'Sin proyecto').Activate()
    nueva_var = app.carpetas['scheme'].CreateObject('IntScheme', 'Carga_N1_F1_20261014_100000')
    nueva_var.NewStage('Etapa_N1', 0, 1)
    app.grabando = nueva_var.GetContents('*.IntSstage')[0]
    sub = _carga(app, 'F1_S1').GetParent()
    nueva = sub.CreateObject('ElmLod', 'N1')
    nueva.plini, nueva.coslini = 0.3, 0.9
    app.grabando = None
    _caso(app, 'Caso base').Activate()
    vistas = []
    original = guion.medir_cabecera

    def medir(app_, elm):
        vistas.append([v.loc_name for v in app_.GetActiveNetworkVariations()])
        return original(app_, elm)

    monkeypatch.setattr(guion, 'medir_cabecera', medir)
    if como == 'falla':
        def revienta(*_a, **_k):
            raise RuntimeError('ComLdf sin configurar')

        monkeypatch.setattr(guion, 'Remedios', revienta)
        with pytest.raises(RuntimeError):
            guion.ejecutar(app, _plan(kw=360.0, kvar=100.0))
    else:
        informe, _rc = guion.ejecutar(app, _plan(kw=360.0, kvar=100.0),
                                      cancelado=(lambda: True) if como == 'cancela' else (lambda: False))
        assert informe['cargas_nuevas_apartadas'] == [nueva_var.loc_name]
        assert all(nueva_var.loc_name not in activas for activas in vistas)
        assert 'N1' not in {x['sed'] for x in informe.get('sed') or []}
    assert nueva_var.loc_name in _activas(app, 'Sin proyecto')[0]
    assert nueva.plini == pytest.approx(0.3) and nueva.coslini == pytest.approx(0.9)


def _ultima(informe, nombre='la calibración del 2026-10-14'):
    """Lo que la web guarda de una calibración aplicada (015, T8)."""
    return {'nombre': nombre, 'sed': {x['sed']: [x['despues']['kw'], x['despues']['kvar']]
                                      for x in informe['sed']}}


def test_gana_el_cambio_manual_de_demanda(guion, monkeypatch):
    """014:RF-10, 014:RF-11, 014:RF-12, 014:RF-13 — una demanda cambiada a mano en «Sin
    proyecto» queda fija con su valor, no se escribe en ningún escenario y se avisa; sin
    una calibración anterior no se buscan cambios manuales."""
    app = _con_escenario_que_manda()
    sys_casos = __import__('sys').modules['casos_pf']
    monkeypatch.setattr(sys_casos, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    assert 'cargas_manuales' not in primero
    _con_proyecto(app)
    _caso(app, 'Con proyecto').Activate()
    en_con = _carga(app, 'F1_S2').plini
    _caso(app, 'Sin proyecto').Activate()
    # El operador, a mano y con su escenario, deja 123 kW efectivos (P × factor de escala).
    escala = _carga(app, 'F1_S2').scale0
    _carga(app, 'F1_S2').plini = 0.123 / escala
    _caso(app, 'Caso base').Activate()
    marca = len(app.escrituras)

    segundo, rc = guion.ejecutar(app, {**_plan(kw=360.0, kvar=100.0),
                                       'ultima_calibracion': _ultima(primero)})

    assert rc == 0, segundo
    (manual,) = segundo['cargas_manuales']
    assert manual['sed'] == 'F1_S2' and manual['manual']['kw'] == pytest.approx(123.0)
    assert manual['calibracion'] == 'la calibración del 2026-10-14'
    assert _sed(segundo, 'F1_S2')['despues']['kw'] == pytest.approx(123.0)
    assert any('cambiada a mano' in a and 'F1_S2' in a for a in segundo['avisos'])
    en_escenario = [e for e in app.escrituras[marca:]
                    if e[0] is _carga(app, 'F1_S2') and e[1] == 'plini']
    assert en_escenario == []
    _caso(app, 'Sin proyecto').Activate()
    assert _carga(app, 'F1_S2').plini == pytest.approx(0.123 / escala)
    _caso(app, 'Con proyecto').Activate()
    assert _carga(app, 'F1_S2').plini == pytest.approx(en_con)


def test_el_ajuste_no_comprueba_la_red(guion):
    """015:RF-17, 015:RF-21 — el ajuste no relee ni compara la red: no trae la relectura del
    vínculo ni de los bancos, y calibra igual con un transformador sin capacidad, porque eso
    es de la verificación del «Caso base»."""
    import inspect

    fuente = inspect.getsource(guion)
    for comprobacion in ('reread_capacitors', 'compare_line_gps', 'native_inventory',
                         'relectura_proyecto_vinculado', 'relectura_bancos'):
        assert comprobacion not in fuente, comprobacion
    app = _app()
    for tr in app.proyecto.GetContents('*.ElmTr2', 1):
        if tr.loc_name.startswith('F2'):
            tr.typ_id = None                  # F2 no se calibra: su red no se mira
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert 'relectura_bancos' not in informe and 'relectura_proyecto_vinculado' not in informe


def test_la_cabecera_se_mide_con_el_escenario_de_sin_proyecto(guion, monkeypatch):
    """006:RF-29, 006:RF-30 (con la 015:RF-26) — cada medida de la cabecera, la del cuadre y la
    del informe, se hace con el escenario de «Sin proyecto» activo: no queda otra cabecera
    «con el escenario» que pueda diferir de la ajustada, como en SI213 (2026-10-12)."""
    app = _con_escenario_que_manda()
    escenarios = []
    original = guion.medir_cabecera

    def medir(app_, elm):
        escenarios.append(app_.GetActiveScenario().loc_name)
        return original(app_, elm)

    monkeypatch.setattr(guion, 'medir_cabecera', medir)
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 0, informe
    assert escenarios and set(escenarios) == {'Sin proyecto'}
    _caso(app, 'Sin proyecto').Activate()
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1) if f.loc_name == 'F1')
    assert original(app, elm).kw == pytest.approx(informe['cabecera']['kw'], rel=1e-9)


def test_si_no_cuadra_los_ajustes_del_flujo_se_restituyen(guion):
    """006:RF-16 / 015:RF-46 — sin cuadre, los remedios no se quedan en «Sin proyecto»."""
    app = _app(kva=lambda f, i: 100.0)
    app.ldf.limite = 0.5
    informe, rc = guion.ejecutar(app, _plan(kw=900.0, kvar=250.0))
    assert rc == 2 and not informe['cuadrado']
    assert app.ldf.itrlx == 25 and app.ldf.iStepAdapt == 0
    assert 'ajustes_del_flujo_conservados' not in informe and informe['ajustes_restituidos']


def test_escaladas_a_fp_del_perfil_y_fijas_con_su_ea_eri(guion):
    """015:RF-53 / 015:RF-54 / 015:RF-56 — CA101, 2026-10-15: las escaladas con el factor de
    potencia del perfil (0,98) y las fijas con el de su EA/ERI; el informe dice de dónde
    sale cada uno."""
    app = _app()
    clientes = [{'codigo': 'CI-1', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.5}]
    plan = {**_plan(clientes=clientes), 'factor_potencia_cargas': 0.98}

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    assert informe['factor_potencia_cargas'] == {
        'fijas': 'EA/ERI del libro de clientes', 'escaladas': 0.98,
        'escaladas_origen': 'perfil de empresa',
        'escaladas_reparto': 'potencia instalada (kVA) de cada SED'}
    for x in informe['sed']:
        fp = x['despues']['fp']
        if x['sed'] == 'F1_S2':
            assert x['origen'] == 'cliente' and fp == pytest.approx(1 / math.hypot(1, 0.5))
        else:
            assert x['origen'] == 'escala' and fp == pytest.approx(0.98)


def _banco(app, feeder, nombre, kvar):
    """Un banco instalado en la primera barra del alimentador, etiquetado con él."""
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1) if f.loc_name == feeder)
    barra = elm.GetObjs('ElmTerm')[0]
    sh = barra.GetParent().CreateObject('ElmShnt', nombre)
    cub = barra.CreateObject('StaCubic', f'c_{nombre}')
    cub.obj_id = sh
    sh.bus1 = cub
    sh.qcapn, sh.ncapx, sh.ncapa, sh.outserv = kvar / 1000.0, 1, 1, 0
    sh.SetAttribute('p:alimentador', [feeder])
    elm._objs.append(sh)        # en el ElmFeeder, como lo dejaría DIgSILENT
    return sh


def test_lista_los_bancos_instalados_del_alimentador_y_no_otros(guion):
    """015:RF-60 / 015:RF-61 — usuario, 2026-10-15: los bancos del proyecto que se analiza ya
    están instalados; el informe los lista con barra, kvar y estado, no crea ninguno y no
    toma los de otro alimentador."""
    app = _app()
    _banco(app, 'F1', 'Banco F1', 300.0)
    _banco(app, 'F2', 'Banco F2', 450.0)
    antes = len(list(app.proyecto.GetContents('*.ElmShnt', 1)))

    informe, rc = guion.ejecutar(app, _plan())

    assert rc == 0, informe
    assert [b['banco'] for b in informe['bancos']] == ['Banco F1']
    banco = informe['bancos'][0]
    assert banco['q_nominal_kvar'] == pytest.approx(300.0) and banco['en_servicio']
    assert banco['barra'] and banco['q_flujo_kvar'] is not None
    assert len(list(app.proyecto.GetContents('*.ElmShnt', 1))) == antes, 'no se crea ninguno'


def test_cliente_que_pide_mas_que_su_transformador_se_avisa(guion):
    """015:RF-59 — CA101, 2026-10-15: un cliente pedía 248 kW en SE20859, de
    50 kVA (496 %). Se nombra la SED con su cliente, kVA y porcentaje, y se calibra igual."""
    app = _app(kva=lambda f, i: 50.0)
    clientes = [{'codigo': 'CI-9', 'sed': 'F1_S2', 'pot': 200.0, 'ea': 1.0, 'eri': 0.2}]

    informe, rc = guion.ejecutar(app, _plan(kw=600.0, kvar=150.0, clientes=clientes))

    assert rc == 0, informe
    (sobre,) = informe['fijas_sobre_su_transformador']
    assert sobre['sed'] == 'F1_S2' and sobre['clientes'] == ['CI-9']
    assert sobre['kva'] == pytest.approx(50.0)
    assert sobre['carga_pct'] == pytest.approx(100.0 * math.hypot(200.0, 40.0) / 50.0)
    assert any('F1_S2' in a and 'CI-9' in a and 'potencia instalada' in a
               for a in informe['avisos'])


def test_clientes_compensados_por_su_banco_propio_en_el_informe(guion):
    """015:RF-62 / 015:RF-63 — la fija con FP 0,447 en su EA/ERI se escribe a 0,98 y el informe
    lo dice por cliente, con su FP y su Q antes y después."""
    app = _app()
    clientes = [{'codigo': 'CI-7', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 2.0}]
    plan = {**_plan(clientes=clientes), 'factor_potencia_minimo_fijas': 0.98}

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    (c,) = informe['fijas_compensadas']
    assert (c['sed'], c['cliente']) == ('F1_S2', 'CI-7')
    assert c['fp_ea_eri'] == pytest.approx(1 / math.sqrt(5)) and c['fp_escrito'] == 0.98
    assert c['q_ea_eri_kvar'] == pytest.approx(80.0)
    assert _sed(informe, 'F1_S2')['despues']['fp'] == pytest.approx(0.98)
    assert any('banco propio' in a and 'F1_S2' in a for a in informe['avisos'])
    assert 'banco propio' in informe['factor_potencia_cargas']['fijas']


def test_bancos_existentes_a_su_maxima_capacidad(guion):
    """015:RF-66 — usuario, 2026-10-15: los bancos existentes trabajan a su máxima capacidad;
    el que tenía escalones sin conectar o estaba fuera de servicio queda con todos y en
    servicio, y el informe lo dice."""
    app = _app()
    banco = _banco(app, 'F1', 'Banco F1', 100.0)
    banco.ncapx, banco.ncapa, banco.outserv = 3, 1, 1
    lleno = _banco(app, 'F1', 'Banco lleno', 300.0)

    informe, rc = guion.ejecutar(app, _plan())

    assert rc == 0, informe
    assert (banco.ncapa, banco.outserv) == (3, 0)
    (cambio,) = informe['bancos_puestos_a_maxima']
    assert cambio['banco'] == 'Banco F1'
    assert cambio['antes'] == {'escalones': 1, 'en_servicio': False}
    assert cambio['despues'] == {'escalones': 3, 'en_servicio': True}
    assert (lleno.ncapa, lleno.outserv) == (1, 0)
    assert any('máxima capacidad' in a and 'Banco F1' in a for a in informe['avisos'])
    fila = next(b for b in informe['bancos'] if b['banco'] == 'Banco F1')
    assert fila['escalones'] == '3 de 3' and fila['q_nominal_kvar'] == pytest.approx(300.0)


def test_toda_escalada_con_el_fp_del_perfil(guion):
    """015:RF-67 — usuario, 2026-10-15: «todas las escaladas con factor de potencia 0,98».
    Calibrada, cada escalada lo tiene; una que en DIgSILENT consume con otro FP hace que la
    validación no pase y se nombra."""
    from igea_dgs.ajuste_cabecera import Medida, Objetivo

    app = _app()
    informe, rc = guion.ejecutar(app, {**_plan(), 'factor_potencia_cargas': 0.98})
    assert rc == 0, informe
    assert informe['validacion_posterior_nativa']['fp_escaladas'] == {'esperado': 0.98,
                                                                      'distintas': 0}
    assert all(x['despues']['fp'] == pytest.approx(0.98) for x in informe['sed']
               if x['origen'] == 'escala')

    cargas, reparto = _reparto_de(_app(n=2), 1.0, fija='F1_S1')
    object.__setattr__(cargas['F1_S2'], 'm:Qsum:bus1', cargas['F1_S2'].plini * 0.9)
    validacion, _ = guion.validar_cargas_nativas(
        cargas, reparto, Medida(True, 2600.0, 260.0), Objetivo(2600.0, 260.0, 'M1', 'F1'), 0.01,
        fp_escaladas=1 / math.hypot(1, 0.1))
    fallo = next(f for f in validacion['fallos'] if f['tipo'] == 'FP_ESCALADAS_DISTINTO')
    assert [s['sed'] for s in fallo['sed']] == ['F1_S2'] and not validacion['correcta']


def test_con_proyecto_recibe_la_demanda_aunque_sin_proyecto_ya_este_calibrado(guion, monkeypatch):
    """014:RF-4 — CA101, 2026-10-15, en DIgSILENT: «Sin proyecto» estaba calibrado y la
    calibración salía por «ya cargado y válido», pero «Con proyecto» conservaba en su
    escenario la demanda del archivo (3861 kW frente a 5264). Ahora se compara y se le
    escribe lo que falte, y el informe lo dice."""
    app = _con_escenario_que_manda()
    sys_casos = __import__('sys').modules['casos_pf']
    monkeypatch.setattr(sys_casos, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    primero, rc = guion.ejecutar(app, _plan())
    assert rc == 0, primero
    _con_proyecto(app)
    _caso(app, 'Sin proyecto').Activate()
    en_sin = _carga(app, 'F1_S2').plini
    _caso(app, 'Con proyecto').Activate()
    _carga(app, 'F1_S2').plini = en_sin / 3.0              # la demanda vieja del escenario
    _caso(app, 'Caso base').Activate()

    segundo, rc = guion.ejecutar(app, {**_plan(), 'ultima_calibracion': _ultima(primero)})

    assert rc == 0, segundo
    assert segundo['decision_carga_nativa']['accion'] == 'NO_REDISTRIBUIR'
    assert segundo['con_proyecto']['corregidas'] == 1 and not segundo['con_proyecto']['fallos']
    assert any('Con proyecto' in a and '014:RF-4' in a for a in segundo['avisos'])
    _caso(app, 'Con proyecto').Activate()
    assert _carga(app, 'F1_S2').plini == pytest.approx(en_sin)


def test_kva_de_la_sed_cuenta_las_unidades_en_paralelo(guion):
    """015:RF-59 / 015:RF-44 — PA217, 2026-10-16: SE30940 quedó con 8 × 630 kVA (``ntnum``)
    y el ajuste la veía con 630 kVA al 606 %; un ElmTr2 con ``ntnum`` unidades cuenta todas."""
    app = _app(n=2)
    carga = next(c for c in app.proyecto.GetContents('*.ElmLod', 1)
                 if guion.kva_en_pf(c))
    una = guion.kva_en_pf(carga)
    tr = next(e for e in carga.bus1.cterm.GetConnectedElements()
              if e.GetClassName() == 'ElmTr2')
    tr.ntnum = 8
    assert guion.kva_en_pf(carga) == pytest.approx(8 * una)


# --------------------------------------------------------------------------- spec 020
def _fichas_plan():
    """La sección del perfil de Electro Dunas, como la manda la web en el plan."""
    import json
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'config' / 'perfiles'
    datos = json.loads((raiz / 'electro_dunas.json').read_text(encoding='utf-8'))
    return datos['calibracion']['transformadores_sed']


def _sobrecargada(app):
    """F1_S2 con un cliente de 300 kW sobre su transformador de 100 kVA a 10 kV (306 %)."""
    tr = next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == 'TR_F1_S2')
    t = tr.typ_id
    t.utrn_h, t.utrn_l, t.tr2cn_h, t.tr2cn_l, t.nt2ag = 10.0, 0.38, 'D', 'YN', 11
    return [{'codigo': 'CI-9', 'sed': 'F1_S2', 'pot': 300.0, 'ea': 1.0, 'eri': 0.2}]


def test_sed_sobrecargada_con_su_transformador_y_la_propuesta(guion):
    """020:RF-1 / 020:RF-6 / 020:RF-8 / 020:RF-9 / 020:RF-5 — la fija que pasa del 100 % sale con su
    transformador (tipo, kVA, tensiones, grupo, unidades) y la propuesta de la Tabla 6 (10 kV):
    306 kVA al 80 % piden 400 kVA. La calibración sigue."""
    app = _app(n=3)
    plan = {**_plan(kw=600.0, kvar=150.0, clientes=_sobrecargada(app)),
            'transformadores_sed': _fichas_plan()}

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    (x,) = informe['fijas_sobre_su_transformador']
    (tr,) = x['transformadores']
    assert tr['transformador'] == 'TR_F1_S2' and tr['tipo'] == 'TR2_F1'
    assert tr['kva'] == pytest.approx(100.0) and tr['unidades'] == 1
    assert tr['kv_at'] == pytest.approx(10.0) and tr['v_bt'] == pytest.approx(380.0)
    assert tr['grupo'] == 'DYN11'
    p = x['propuesta']
    assert (p['kva'], p['unidades']) == (400, 1) and 'Tabla 6' in p['norma']
    assert (p['po_w'], p['pc_w'], p['io_pct'], p['uk_pct']) == (968, 5550, 1.84, 4)
    assert p['carga_pct_prevista'] == pytest.approx(100 * x['kva_carga'] / 400)
    assert p['tipo_nuevo'] == 'TR_400kVA_NTP370400_10-380V_DYN11'
    assert informe['fichas_transformador_sed']['umbral_carga_pct'] == 80
    assert len(informe['fichas_transformador_sed']['normas']) == 2


def test_sin_fichas_en_el_plan_se_avisa_sin_propuesta(guion):
    """020:RF-10 — sin tablas del perfil, la SED se lista igual, sin propuesta y con el motivo."""
    app = _app(n=3)
    informe, rc = guion.ejecutar(app, _plan(kw=600.0, kvar=150.0, clientes=_sobrecargada(app)))

    assert rc == 0, informe
    (x,) = informe['fijas_sobre_su_transformador']
    assert x['propuesta']['kva'] is None and 'perfil' in x['propuesta']['motivo']
    assert 'perfil' in informe['fichas_transformador_sed']['falta']


def test_sed_con_dos_transformadores_sin_propuesta(guion):
    """020:RF-12 — con dos transformadores en la SED no se adivina cuál cambiar."""
    app = _app(n=3)
    sub = next(o for o in app.proyecto.GetContents('*.ElmSubstat', 1) if o.loc_name == 'F1_S2')
    primero = next(o for o in sub.GetContents('*.ElmTr2'))
    otro = sub.CreateObject('ElmTr2', 'TR_F1_S2_b')
    otro.typ_id = primero.typ_id
    baja = next(o for o in sub.GetContents('*.ElmTerm'))
    baja.CreateObject('StaCubic', 'lv_b').obj_id = otro
    plan = {**_plan(kw=600.0, kvar=150.0, clientes=_sobrecargada(app)),
            'transformadores_sed': _fichas_plan()}

    informe, rc = guion.ejecutar(app, plan)

    sobre = informe.get('fijas_sobre_su_transformador') or []
    # Con 200 kVA instalados el cliente de 306 kVA sigue por encima del 100 % (020:RF-2).
    (x,) = sobre
    assert x['kva'] == pytest.approx(200.0) and len(x['transformadores']) == 2
    assert x['propuesta']['kva'] is None and '2 transformadores' in x['propuesta']['motivo']


def test_fichas_imposibles_en_el_plan_se_dicen(guion):
    """020:RF-31 — un umbral imposible en el perfil no rompe la calibración: se dice por qué
    no hay propuesta."""
    app = _app(n=3)
    plan = {**_plan(kw=600.0, kvar=150.0, clientes=_sobrecargada(app)),
            'transformadores_sed': {'umbral_carga_pct': 0, 'tablas': []}}

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    (x,) = informe['fijas_sobre_su_transformador']
    assert 'umbral_carga_pct' in x['propuesta']['motivo']


def test_aviso_de_sobrecarga_como_causa_probable(guion):
    """020:RF-4 — el aviso nombra las SED y remite a la propuesta, o dice que no la hay."""
    sobre = [{'sed': 'SE30940', 'carga_pct': 954.5, 'propuesta': {'kva': 630}},
             {'sed': 'SE30424', 'carga_pct': 118.7, 'propuesta': {'kva': None}}]
    aviso = guion.aviso_sobrecarga(sobre)
    assert aviso.startswith('SOBRECARGA') and 'SE30940 (954 %)' in aviso
    assert 'propuesta de transformadores nuevos para 1' in aviso and '020:RF-6' in aviso
    assert 'Sin propuesta' in guion.aviso_sobrecarga(sobre[1:])


def _tr(app, nombre):
    return next(o for o in app.proyecto.GetContents('*.ElmTr2', 1) if o.loc_name == nombre)


def _con_propuesta(guion, app, clientes, kw=600.0):
    """El plan de implementar: la propuesta que dio la simulación, como la manda la web."""
    plan = {**_plan(kw=kw, kvar=kw / 4, clientes=clientes),
            'transformadores_sed': _fichas_plan()}
    simulado, rc = guion.ejecutar(app, plan, simular=True)
    assert rc == 0, simulado
    cambios = [{'sed': x['sed'], 'transformador': x['transformadores'][0]['transformador'],
                'propuesta': x['propuesta']} for x in simulado['fijas_sobre_su_transformador']]
    return {**plan, 'transformadores': cambios}


def test_implementar_cambia_el_transformador_con_un_tipo_propio(guion):
    """020:RF-16 / 020:RF-19 / 020:RF-20 / 020:RF-23 / 020:RF-24 / 020:RF-25 — en «Sin proyecto», en la
    red: tipo propio de 400 kVA con la ficha, copiado del actual; el tipo de antes queda igual;
    el informe dice antes y después y la calibración ya cuenta los 400 kVA."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    viejo = _tr(app, 'TR_F1_S2').typ_id
    assert not app.variaciones_activas

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    tr = _tr(app, 'TR_F1_S2')
    nuevo = tr.typ_id
    assert nuevo.loc_name == 'TR_400kVA_NTP370400_10-380V_DYN11' and nuevo is not viejo
    assert (nuevo.strn, nuevo.pfe, nuevo.pcutr, nuevo.curmg, nuevo.uktr, nuevo.uk0tr) == \
        pytest.approx((0.4, 0.968, 5.55, 1.84, 4.0, 4.0))
    assert (nuevo.utrn_h, nuevo.utrn_l, nuevo.tr2cn_h, nuevo.tr2cn_l, nuevo.nt2ag) == \
        (10.0, 0.38, 'D', 'YN', 11)
    assert tr.ntnum == 1 and viejo.strn == pytest.approx(0.1) and viejo.loc_name == 'TR2_F1'
    (h,) = informe['transformadores_implementados']['cambios']
    assert h['antes'] == {'tipo': 'TR2_F1', 'kva': pytest.approx(100.0), 'unidades': 1}
    assert h['despues']['tipo'] == nuevo.loc_name and h['despues']['kva'] == 400
    assert 'fijas_sobre_su_transformador' not in informe
    assert any('020:RF-24' in a for a in informe['avisos'])


def test_implementar_unidades_en_paralelo(guion):
    """020:RF-7 / 020:RF-23 — 2000 kW (2040 kVA) sobre 100 kVA: 5 unidades de 630 kVA en paralelo
    (``ntnum``), las menos que lo dejan en el 80 % (4 darían el 81 %)."""
    app = _app(n=3)
    clientes = [{**_sobrecargada(app)[0], 'pot': 2000.0}]
    plan = _con_propuesta(guion, app, clientes, kw=2300.0)
    p = plan['transformadores'][0]['propuesta']
    assert (p['kva'], p['unidades']) == (630, 5)

    guion.ejecutar(app, plan)

    tr = _tr(app, 'TR_F1_S2')
    assert tr.ntnum == 5 and tr.typ_id.strn == pytest.approx(0.63)
    assert guion.kva_en_pf(_carga(app, 'F1_S2')) == pytest.approx(5 * 630)


def test_solo_cambian_las_sed_marcadas(guion):
    """020:RF-18 — la SED que el operador desmarcó no se toca."""
    app = _app(n=3)
    t1 = _tr(app, 'TR_F1_S1').typ_id
    t1.utrn_h, t1.utrn_l, t1.tr2cn_h, t1.tr2cn_l, t1.nt2ag = 10.0, 0.38, 'D', 'YN', 11
    clientes = _sobrecargada(app) + [{'codigo': 'CI-8', 'sed': 'F1_S1', 'pot': 300.0,
                                      'ea': 1.0, 'eri': 0.2}]
    plan = _con_propuesta(guion, app, clientes, kw=900.0)
    assert {c['sed'] for c in plan['transformadores']} == {'F1_S1', 'F1_S2'}
    plan['transformadores'] = [c for c in plan['transformadores'] if c['sed'] == 'F1_S2']

    guion.ejecutar(app, plan)

    assert _tr(app, 'TR_F1_S1').typ_id is t1
    assert _tr(app, 'TR_F1_S2').typ_id.loc_name.startswith('TR_400kVA')


def test_con_una_etapa_grabando_no_se_cambia_nada(guion):
    """020:RF-17 — con una etapa grabando en «Sin proyecto», nada cambia y se nombra."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    viejo = _tr(app, 'TR_F1_S2').typ_id
    # El estado de la etapa es de cada caso, y el guion activa «Sin proyecto»: se simula
    # lo que DIgSILENT devuelve en él.
    app.GetRecordingStage = lambda: SimpleNamespace(loc_name='Etapa_del_operador')

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 2 and 'Etapa_del_operador' in informe['error'] and '020:RF-17' in informe['error']
    assert _tr(app, 'TR_F1_S2').typ_id is viejo


def test_el_tipo_propio_se_reutiliza(guion):
    """020:RF-21 — un tipo propio con la misma ficha, de un cambio anterior, se reutiliza."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    equip = app.GetProjectFolder('equip')
    previo = equip.AddCopy(_tr(app, 'TR_F1_S2').typ_id, 'TR_400kVA_NTP370400_10-380V_DYN11')
    previo.strn, previo.pfe, previo.pcutr = 0.4, 0.968, 5.55
    previo.curmg, previo.uktr, previo.uk0tr = 1.84, 4.0, 4.0

    guion.ejecutar(app, plan)

    assert _tr(app, 'TR_F1_S2').typ_id is previo
    assert len([t for t in equip.GetContents('*.TypTr2', 1)
                if t.loc_name == previo.loc_name]) == 1


def test_el_tipo_propio_con_otra_ficha_no_se_toca(guion):
    """020:RF-22 / 020:RF-20 — con otra ficha, la SED no cambia y se nombra el dato."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    viejo = _tr(app, 'TR_F1_S2').typ_id
    otro = app.GetProjectFolder('equip').AddCopy(viejo, 'TR_400kVA_NTP370400_10-380V_DYN11')
    otro.strn = 0.4

    informe, _ = guion.ejecutar(app, plan)

    assert _tr(app, 'TR_F1_S2').typ_id is viejo and otro.strn == pytest.approx(0.4)
    (o,) = informe['transformadores_implementados']['omitidas']
    assert 'ya existe el tipo' in o['motivo'] and '020:RF-22' in o['motivo']


def test_cancelar_tras_el_cambio_deja_los_transformadores(guion):
    """020:RF-27 — cancelado entre el cambio y la calibración: quedan y se dice que falta calibrar."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))

    informe, rc = guion.ejecutar(app, plan, cancelado=lambda: True)

    assert rc == 0 and informe['cancelado'] and 'sed' not in informe
    assert _tr(app, 'TR_F1_S2').typ_id.loc_name.startswith('TR_400kVA')
    assert any('falta calibrar' in a for a in informe['avisos'])


def test_simular_no_cambia_transformadores(guion):
    """020:RF-16 — simular no escribe: el plan con transformadores solo se aplica."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    viejo = _tr(app, 'TR_F1_S2').typ_id

    informe, rc = guion.ejecutar(app, plan, simular=True)

    assert rc == 0 and _tr(app, 'TR_F1_S2').typ_id is viejo
    assert 'transformadores_implementados' not in informe


def test_tras_implementar_la_calibracion_sale_valida(guion):
    """020:RF-26 — con el transformador nuevo ninguna fija queda sobre su potencia, la cambiada
    queda en el umbral y la calibración es válida (PA217, 2026-10-16)."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    r = informe['resultado_transformadores']
    assert r['status'] == 'VALIDO' and r['calibracion_valida'], r
    assert r['sobrecargadas'] == [] and r['sobre_umbral'] == [] and r['aviso'] is None
    assert informe['resultado_carga_nativa']['status'] == 'APLICADO_Y_VALIDADO'


def test_si_tras_implementar_no_es_valida_es_un_fallo_con_lo_que_sigue_fallando(guion):
    """020:RF-32 — calibración no válida tras el cambio: fallo, los transformadores se quedan
    y se dice qué sigue (cargas que no consumen lo escrito, remedio del flujo)."""
    from igea_dgs.ajuste_cabecera import Fija

    cambiados = [{'sed': 'S1'}]
    validacion = {'fallos': [{'tipo': 'CONSUMO_DISTINTO_DE_LO_ESCRITO', 'cantidad': 12}]}
    r = guion.resultado_transformadores(
        cambiados, [], {'S1': Fija('S1', 100.0, 20.0)}, {}, {'umbral_carga_pct': 80},
        calibracion_valida=False, validacion=validacion,
        remedios=[{'remedio': 'más iteraciones', 'cambios': []},
                  {'remedio': 'adaptación automática del modelo', 'cambios': ['iopt_lev: 0 → 1']}],
        motivo=None)
    assert r['status'] == 'FALLO' and not r['calibracion_valida']
    assert any('12 cargas no consumen' in m for m in r['motivos'])
    assert any('adaptación automática' in m and 'iteraciones' not in m for m in r['motivos'])
    assert 'se quedan' in r['aviso'] and 'ya no es la causa' in r['aviso']


def test_la_sed_cambiada_por_encima_del_umbral_se_nombra(guion):
    """020:RF-26 — una SED cambiada que queda sobre el umbral (o una fija que sigue sobre su
    potencia) hace fallar la comprobación aunque la calibración valga."""
    from igea_dgs.ajuste_cabecera import Fija

    app = _app(n=3)
    carga = _carga(app, 'F1_S2')                 # 100 kVA en el doble
    r = guion.resultado_transformadores(
        [{'sed': 'F1_S2'}], [{'sed': 'F1_S3', 'carga_pct': 130.0}],
        {'F1_S2': Fija('F1_S2', 90.0, 0.0)}, {'F1_S2': carga}, {'umbral_carga_pct': 80},
        calibracion_valida=True, validacion=None, remedios=[], motivo=None)
    assert r['status'] == 'FALLO' and r['calibracion_valida']
    assert [x['sed'] for x in r['sobre_umbral']] == ['F1_S2']
    assert r['sobre_umbral'][0]['carga_pct'] == pytest.approx(90.0)
    assert r['sobrecargadas'] == ['F1_S3'] and 'la comprobación no pasa' in r['aviso']


def test_la_variacion_de_una_central_no_bloquea_los_transformadores(guion):
    """020:RF-17, 021:RF-37 — la variación de la central (del conversor) se apaga mientras se
    escriben los transformadores y se vuelve a encender; la de otro, sí bloquea. En NA203 +
    NA205 (2026-10-17) la central de NA205 bloqueaba los transformadores de NA203."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    activas = []

    class Var(SimpleNamespace):
        def Deactivate(self):
            activas.remove(self)

        def Activate(self):
            activas.append(self)

    central = Var(loc_name='Central_F2')
    activas.append(central)
    app.GetActiveNetworkVariations = lambda: list(activas)
    hecho = guion.implementar_transformadores(app, {'F1_S2': _carga(app, 'F1_S2')},
                                              plan['transformadores'])
    assert 'error' not in hecho and [h['sed'] for h in hecho['cambios']] == ['F1_S2']
    assert central in activas, 'la central vuelve a quedar activa'
    # 032:RF-12 (cambia 020:RF-17): los transformadores van en su variación, así que solo
    # bloquea una variación del operador que esté grabando, y se nombra.
    # ``Obra_`` es prefijo del conversor (011, 016): la del operador se llama de otro modo.
    obra = Var(loc_name='Refuerzo_del_operador')
    activas.append(obra)
    app.GetRecordingStage = lambda: SimpleNamespace(loc_name='Etapa', GetParent=lambda: obra)
    hecho = guion.implementar_transformadores(app, {'F1_S2': _carga(app, 'F1_S2')},
                                              plan['transformadores'], 'P')
    assert 'Refuerzo_del_operador' in hecho['error'] and 'Central_F2' not in hecho['error']
    assert '032:RF-12' in hecho['error']


def test_cambios_en_la_red_original_y_nuevo(guion):
    """020:RF-60, 020:RF-61 — cada transformador cambiado con su SED, lo original
    (unidades × kVA y su total) y lo nuevo; cada banco puesto a su máxima, con escalones ×
    kvar por escalón (fuera de servicio, 0 kvar)."""
    app = _app(n=3)
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    informe, _rc = guion.ejecutar(app, plan)
    [t] = [c for c in informe['cambios_en_la_red'] if c['clase'] == 'transformador']
    h = informe['transformadores_implementados']['cambios'][0]
    assert t['sed'] == h['sed'] == 'F1_S2' and t['elemento'] == h['transformador']
    assert t['original']['potencia'] == h['antes']['unidades'] * h['antes']['kva']
    assert t['nuevo']['potencia'] == h['despues']['unidades'] * h['despues']['kva']
    assert t['original']['unidad'] == t['nuevo']['unidad'] == 'kVA'
    assert f"{h['despues']['unidades']} × " in t['nuevo']['descripcion']
    filas = guion.cambios_en_la_red({'bancos_puestos_a_maxima': [
        {'banco': 'BC1', 'barra': 'B7', 'sed': 'SE1', 'kvar_escalon': 150.0,
         'antes': {'escalones': 1.0, 'en_servicio': True}, 'despues': {'escalones': 3.0, 'en_servicio': True}},
        {'banco': 'BC2', 'barra': 'B8', 'sed': None, 'kvar_escalon': 300.0,
         'antes': {'escalones': 1.0, 'en_servicio': False}, 'despues': {'escalones': 1.0, 'en_servicio': True}}]})
    assert [(f['sed'], f['original']['potencia'], f['nuevo']['potencia']) for f in filas] == [
        ('SE1', 150.0, 450.0), ('B8', 0.0, 300.0)]
    assert all(f['clase'] == 'banco' and f['nuevo']['unidad'] == 'kvar' for f in filas)
    assert guion.cambios_en_la_red({}) == []


def test_la_cambiada_a_mano_no_entra_en_el_factor_comun(guion):
    """014:RF-10 / 015:RF-47 — una escalada cambiada a mano conserva su demanda y no lleva el
    factor común: no hace «no proporcionales» a las demás (SE20027 de TM104 en Chincha,
    2026-10-18, con su transformador nuevo, era la primera de la lista)."""
    from types import SimpleNamespace as N

    class Carga(N):
        def GetAttribute(self, nombre):
            return {'plini': self.plini, 'qlini': self.qlini}.get(nombre)

    def carga(p):
        return Carga(loc_name='x', plini=p / 1000, qlini=p / 5000, scale0=0.5, i_scale=1,
                     outserv=0, mode_inp='PQ')

    cargas = {'MANUAL': carga(100.0), 'A': carga(200.0), 'B': carga(300.0)}
    cargas['MANUAL'].scale0 = 1.0
    base = {s: (c.plini * 1000, c.qlini * 1000) for s, c in cargas.items()}
    reparto = N(demandas={s: N(kw=v[0] * 0.5, kvar=v[1] * 0.5) for s, v in base.items()},
                base=base, todo_escala=True, a=0.5, b=0.5, solo_kw=False,
                con_factores=lambda a, b: None)
    medida = N(converge=True, kw=None, kvar=None, motivo='', carga_kw=None, carga_kvar=None)
    objetivo = N(kw=300.0, kvar=60.0, fp=0.98)
    sin, _ = guion.validar_cargas_nativas(cargas, reparto, medida, objetivo, 0.01)
    con, _ = guion.validar_cargas_nativas(cargas, reparto, medida, objetivo, 0.01,
                                          manuales={'MANUAL'})
    assert any(f['tipo'] == 'REPARTO_P_NO_PROPORCIONAL' for f in sin['fallos'])
    assert not any(f['tipo'].startswith('REPARTO_') for f in con['fallos'])


# --------------------------------------------------------------------------- spec 032
_FICHA_F1 = {'AAAC_F1': {'valores': {'r1_ohm_km': 0.9, 'ampacity_a': 300.0},
                         'fuente': 'ficha del fabricante X'}}


def _lineas(app, f='F1'):
    return [o for o in app.proyecto.GetContents('*.ElmLne', 1) if o.loc_name.startswith(f + '_')]


def _tipo(app, nombre):
    return next((t for t in app.carpetas['equip'].GetContents('*.TypLne', 1)
                 if t.loc_name == nombre), None)


def _variaciones(app, prefijo):
    return [v for v in app.carpetas['scheme'].GetContents('*.IntScheme', 1)
            if v.loc_name.startswith(prefijo)]


def test_codigo_del_tipo_de_linea():
    """032:RF-14 — la ficha se busca por el código del conductor, sin la tensión ni el (n)."""
    from igea_dgs.naming import codigo_de_tipo_linea

    assert codigo_de_tipo_linea('AA12003D_22_9kV') == 'AA12003D'
    assert codigo_de_tipo_linea('NK12003D_10kV(1)') == 'NK12003D'
    assert codigo_de_tipo_linea('AAAC_F1') == 'AAAC_F1'


def test_conductores_con_su_ficha_en_su_variacion(guion):
    """032:RF-8, 032:RF-9, 032:RF-14, 032:RF-15, 032:RF-27 — en «Sin proyecto» las líneas pasan a una copia del
    tipo con la ficha, reasignadas en la variación ``Fichas_<proyecto>``; el tipo del archivo no
    cambia, la longitud y el tramo tampoco, y sin la variación (el «Caso base») vuelven al tipo
    del archivo. En la etapa solo están las líneas: la marca fija o escalable va a la red."""
    app = _app(n=3)
    app.atributos_en_variacion = True
    original = _tipo(app, 'AAAC_F1')
    longitudes = {ln.loc_name: ln.dline for ln in _lineas(app)}

    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=90.0),
                                       'fichas_conductores': _FICHA_F1})

    assert rc == 0, informe
    (var,) = _variaciones(app, 'Fichas_')
    assert var.loc_name == 'Fichas_P' and informe['conductores_ficha']['variacion'] == 'Fichas_P'
    nuevo = _tipo(app, 'AAAC_F1_FICHA')
    assert nuevo is not None and nuevo.rline == pytest.approx(0.9)
    assert nuevo.sline == pytest.approx(0.3) and nuevo.xline == pytest.approx(0.4)
    assert (original.rline, original.xline) == (0.5, 0.4)                       # RF-9
    _caso(app, 'Sin proyecto').Activate()
    assert all(ln.typ_id is nuevo for ln in _lineas(app))
    assert {ln.loc_name: ln.dline for ln in _lineas(app)} == longitudes          # RF-15
    etapa = next(iter(var.GetContents('*.IntSstage')))
    assert {o.GetClassName() for o in etapa.GetContents('*', 1)} == {'ElmLne'}
    _caso(app, 'Caso base').Activate()                                          # RF-27
    assert all(ln.typ_id is original for ln in _lineas(app))


def test_informe_de_conductores_con_su_ficha(guion):
    """032:RF-16, 032:RF-17 — por código, el parámetro, el valor del archivo y el de la ficha, la
    variación en %, tramos, km y la fuente; y un aviso en el resultado del ajuste."""
    app = _app(n=3)
    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=90.0),
                                       'fichas_conductores': _FICHA_F1})

    assert rc == 0, informe
    por = {c['parametro']: c for c in informe['conductores_ficha']['cambios']}
    r = por['rline']
    assert (r['codigo'], r['archivo'], r['ficha'], r['tramos'], r['km']) == (
        'AAAC_F1', 0.5, 0.9, 3, 3.0)
    assert r['variacion_pct'] == pytest.approx(80.0) and r['fuente'] == 'ficha del fabricante X'
    assert (por['sline']['unidad'], por['sline']['ficha']) == ('A', 300.0)
    assert any('032:RF-14' in a and 'AAAC_F1' in a for a in informe['avisos'])


def test_recalibrar_reutiliza_la_variacion_y_el_tipo(guion):
    """032:RF-13, 032:RF-10 — otra calibración no crea otra variación ni otro tipo, ni reescribe."""
    app = _app(n=3)
    plan = {**_plan(kw=300.0, kvar=90.0), 'fichas_conductores': _FICHA_F1}
    guion.ejecutar(app, plan)
    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    assert len(_variaciones(app, 'Fichas_')) == 1
    assert [t.loc_name for t in app.carpetas['equip'].GetContents('*.TypLne', 1)
            ].count('AAAC_F1_FICHA') == 1
    assert informe['conductores_ficha']['tramos_reasignados'] == 0
    assert informe['conductores_ficha']['cambios']


def test_tipo_propio_con_otros_datos_no_se_toca(guion):
    """032:RF-11 — un ``<tipo>_FICHA`` ya existente con otros datos no se cambia: sus líneas se
    quedan como estaban y se nombra el tipo y el dato."""
    app = _app(n=3)
    otro = app.carpetas['equip'].AddCopy(_tipo(app, 'AAAC_F1'), 'AAAC_F1_FICHA')
    otro.rline = 1.7
    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=90.0),
                                       'fichas_conductores': _FICHA_F1})

    assert rc == 0, informe
    (om,) = informe['conductores_ficha']['omitidos']
    assert om['tipo'] == 'AAAC_F1_FICHA' and 'rline' in om['motivo']
    assert otro.rline == 1.7
    assert all(ln.typ_id.loc_name == 'AAAC_F1' for ln in _lineas(app))


def test_con_otra_variacion_grabando_no_se_cambia_nada(guion):
    """032:RF-12 — si graba una variación del operador, no se cambia ningún conductor y se nombra."""
    app = _app(n=3)
    guion.preparar_sin(app, {'project': 'P', 'feeders': ['F1'], 'caso_base_sin_verificar': {}})
    _caso(app, 'Sin proyecto').Activate()
    var = app.carpetas['scheme'].CreateObject('IntScheme', 'Mi_obra')
    var.NewStage('Etapa', 1_760_000_000, 1)
    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=90.0),
                                       'fichas_conductores': _FICHA_F1})

    assert 'Mi_obra' in (informe['conductores_ficha'].get('error') or '')
    assert _tipo(app, 'AAAC_F1_FICHA') is None and not _variaciones(app, 'Fichas_')


def test_codigo_sin_ficha_queda_como_en_el_archivo(guion):
    """032:RF-18 — un conductor sin ficha conserva sus valores y se lista «sin ficha»."""
    app = _app(n=3)
    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=90.0),
                                       'fichas_conductores': {'OTRO': {'valores': {'r1_ohm_km': 1.0}}}})

    assert rc == 0, informe
    assert informe['conductores_ficha']['sin_ficha'] == ['AAAC_F1']
    assert not _variaciones(app, 'Fichas_')
    assert all(ln.typ_id.loc_name == 'AAAC_F1' for ln in _lineas(app))


def test_transformadores_en_su_variacion_y_el_caso_base_intacto(guion):
    """032:RF-8, 032:RF-23, 032:RF-24, 032:RF-27 (cambia 020:RF-16) — los transformadores
    implementados van en
    ``SED_NTP_<proyecto>``: «Sin proyecto» ve el tipo nuevo y el «Caso base» conserva el del
    archivo. Una variación del operador activa sin grabar no lo impide."""
    app = _app(n=3)
    app.atributos_en_variacion = True
    plan = _con_propuesta(guion, app, _sobrecargada(app))
    viejo = _tr(app, 'TR_F1_S2').typ_id

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    assert informe['transformadores_implementados']['variacion'] == 'SED_NTP_P'
    assert [v.loc_name for v in _variaciones(app, 'SED_NTP_')] == ['SED_NTP_P']
    _caso(app, 'Sin proyecto').Activate()
    assert _tr(app, 'TR_F1_S2').typ_id.loc_name.startswith('TR_400kVA')
    _caso(app, 'Caso base').Activate()
    assert _tr(app, 'TR_F1_S2').typ_id is viejo and _tr(app, 'TR_F1_S2').ntnum in (None, 1)
    # RF-24: en la tabla de cambios, lo original del archivo (100 kVA) y lo nuevo (400 kVA).
    [c] = [x for x in informe['cambios_en_la_red'] if x['clase'] == 'transformador']
    assert (c['sed'], c['original']['potencia'], c['nuevo']['potencia']) == ('F1_S2', 100.0, 400.0)


def test_escaladas_y_fijas_sobre_el_umbral_con_propuesta(guion):
    """032:RF-20, 032:RF-21, 032:RF-28 — tras calibrar, las SED fijas y escaladas por encima del umbral
    del perfil, con su nivel, su tipo y la propuesta de la ficha."""
    app = _app(n=3)
    plan = {**_plan(kw=600.0, kvar=150.0, clientes=_sobrecargada(app)),
            'transformadores_sed': _fichas_plan()}

    informe, rc = guion.ejecutar(app, plan)

    assert rc == 0, informe
    sobre = informe['sed_sobre_umbral']
    assert sobre['umbral_carga_pct'] == 80
    por = {x['sed']: x for x in sobre['sed']}
    fija = por['F1_S2']
    assert (fija['tipo'], fija['nivel']) == ('fija', 'sobre_100') and fija['clientes'] == ['CI-9']
    assert fija['propuesta']['kva'] is not None
    assert all(x['carga_pct'] > 80 for x in sobre['sed'])
    assert {x['nivel'] for x in sobre['sed']} <= {'sobre_100', 'sobre_umbral'}
    escaladas = [x for x in sobre['sed'] if x['tipo'] == 'escalada']
    assert all(x['clientes'] == [] for x in escaladas)


def test_sin_perfil_las_sed_sobre_el_100_sin_propuesta(guion):
    """032:RF-25 — sin tablas en el perfil, umbral del 100 % y la lista sin propuesta."""
    app = _app(n=3)
    informe, rc = guion.ejecutar(app, _plan(kw=600.0, kvar=150.0, clientes=_sobrecargada(app)))

    assert rc == 0, informe
    sobre = informe['sed_sobre_umbral']
    assert sobre['umbral_carga_pct'] == 100.0
    assert sobre['sed'] and all(x['propuesta']['kva'] is None for x in sobre['sed'])


def test_variaciones_del_catalogo_en_sin_y_con_proyecto_y_no_en_el_caso_base(guion, monkeypatch):
    """032:RF-27 — con «Con proyecto» ya creado, calibrar deja ``Fichas_<proyecto>`` activa en
    «Sin proyecto» y en «Con proyecto», y nunca en el «Caso base»; las del catálogo no se
    cuentan como del operador."""
    import sys

    app = _con_escenario_que_manda()
    app.atributos_en_variacion = True
    casos = sys.modules['casos_pf']
    monkeypatch.setattr(casos, 'activar_proyecto', lambda app, ruta, carpeta=None: app.proyecto)
    guion.ejecutar(app, _plan())
    _con_proyecto(app)
    _caso(app, 'Caso base').Activate()

    informe, rc = guion.ejecutar(app, {**_plan(), 'fichas_conductores': _FICHA_F1})

    assert rc == 0, informe
    for nombre, esperado in (('Sin proyecto', True), ('Con proyecto', True), ('Caso base', False)):
        _caso(app, nombre).Activate()
        activas = {v.loc_name for v in app.GetActiveNetworkVariations()}
        assert ('Fichas_P' in activas) is esperado, (nombre, activas)
        assert all((ln.typ_id.loc_name == 'AAAC_F1_FICHA') is esperado for ln in _lineas(app))
    (var,) = _variaciones(app, 'Fichas_')
    assert casos.es_del_catalogo(var) and not casos.es_del_operador(var)
    assert any('032:RF-27' in a for a in informe['avisos'])
