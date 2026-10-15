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


def test_calibracion_con_cargas_dependientes_de_la_tension_se_revierte(guion):
    """015:RF-47 / 015:RF-49 / 015:RF-51 — CA101 en DIgSILENT, 2026-10-15: las cargas
    consumían lo escrito por u² con ``iopt_lev=1`` y la calibración quedaba «válida».
    Ahora no lo es: no se graba, las cargas vuelven a como estaban y el aviso nombra la
    fija que no consume lo suyo y el ajuste del flujo."""
    app = _app()
    object.__setattr__(app.ldf, 'iopt_lev', 1)
    antes = {o.loc_name: (o.plini, o.scale0) for o in app.proyecto.GetContents('*.ElmLod', 1)}
    for obj in app.proyecto.GetContents('*.ElmLod', 1):
        object.__setattr__(obj, 'consumo_relativo', 0.9)
    clientes = [{'codigo': 'CI-1', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25}]

    informe, rc = guion.ejecutar(app, _plan(clientes=clientes))

    assert rc == 2
    assert informe['status'] == 'FALLO_VALIDACION_NATIVA' and not informe['cuadrado']
    assert informe['calibracion_revertida'] is True
    assert 'escenarios' not in informe
    aviso = next(a for a in informe['avisos'] if a.startswith('VALIDACION_FISICA'))
    assert 'F1_S2' in aviso and 'iopt_lev=1' in aviso
    balance = informe['validacion_posterior_nativa']['balance']
    assert balance['fijas_consumida_kw'] == pytest.approx(0.9 * balance['fijas_escrita_kw'])
    assert {o.loc_name: (o.plini, o.scale0)
            for o in app.proyecto.GetContents('*.ElmLod', 1)} == pytest.approx(antes)


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
