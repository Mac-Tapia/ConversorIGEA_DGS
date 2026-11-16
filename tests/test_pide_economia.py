"""Spec 024, T14: evaluación económica y priorización del PIDE, sin DIgSILENT."""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from convertersmartgrid import pide_economia as ec
from convertersmartgrid.perfil_empresa import carpeta_perfiles

PLAN = {'tasa_regulada': 0.12, 'tasa_privada': 0.12, 'vida_util_anios': 30, 'horizonte_anios': 20,
        'tarifas': {'MT3': {'energia_punta_kwh': 0.3226, 'energia_fuera_punta_kwh': 0.2842,
                            'potencia_generacion_kw_mes': 51.61, 'potencia_distribucion_kw_mes': 17.95},
                    'BT5B': {'energia_kwh': 0.7185}}}
CONFIG = {'hoja': '3_Crec_Dem', 'fila_cabecera_contiene': 'Costo  Unitario',
          'columnas': {'nombre': 'Proyecto', 'descripcion': 'Descripción', 'objetivo': 'Objetivo',
                       'unidad': 'Und', 'cantidad': 'Cantidad', 'costo_unitario': 'Costo  Unitario',
                       'inversion': 'INVERSIÓN TOTAL', 'zona': 'Zona'}}


def _capex(tmp_path):
    libro = Workbook()
    hoja = libro.active
    hoja.title = '3_Crec_Dem'
    hoja.append(['CRECIMIENTO POR DEMANDA'])
    hoja.append(['', 'Proyecto', 'Zona', 'Objetivo', 'Descripción', 'INVERSIÓN TOTAL', 'Cantidad',
                 'Und', 'Costo  Unitario', 'Responsable_Proy'])
    hoja.append(['', 'Banco de condensadores 300 kvar', 'Ica', 'Calidad', '', 6000, 2, 'Und', 3000, 'Persona X'])
    hoja.append(['', 'Cambio de sección AAAC 120', 'Pisco', 'Reforzamiento', '', 50000, 2, 'km', 25000, 'Persona Y'])
    hoja.append(['', 'Banco de condensadores 450 kvar', 'Nasca', 'Calidad', '', 8000, 2, 'Und', 4000, 'Persona Z'])
    hoja.append(['', 'Nueva SED 250 kVA', 'Ica', 'Ampliación', '', 30000, 1, 'Und', 30000, None])
    ruta = tmp_path / 'capex.xlsx'
    libro.save(ruta)
    return ruta


def test_capex_por_nombres_del_perfil_sin_datos_personales(tmp_path):
    """024:RF-54 / 024:RF-55 / 024:RF-56 — obras del CAPEX con su alternativa y costo, por
    los nombres del perfil; los responsables no se leen; se avisa de lo que no hay."""
    obras, avisos = ec.leer_capex(_capex(tmp_path), CONFIG)
    assert [o.alternativa for o in obras] == ['bancos', 'cambio_seccion', 'bancos', 'nueva_sed']
    assert not any('Persona' in str(v) for o in obras for v in o.__dict__.values())
    assert any('nueva_set' in a for a in avisos)
    costos = ec.costos_por_alternativa(obras)
    assert costos['bancos']['costo_unitario'] == 3500 and costos['bancos']['obras'] == 2
    assert costos['cambio_seccion']['unidad'] == 'km'


def test_capex_sin_la_hoja_del_perfil(tmp_path):
    """024:RF-55 — una hoja que el libro no tiene es un error que la nombra."""
    with pytest.raises(ec.EconomiaPideError, match='Otra'):
        ec.leer_capex(_capex(tmp_path), {**CONFIG, 'hoja': 'Otra'})


@pytest.mark.parametrize(('texto', 'alternativa'), [
    ('Transformador de potencia 60/22,9/10 kV', 'nueva_set'),
    ('Repotenciación del troncal', 'cambio_seccion'),
    ('Instalación de regulador de tensión', 'reguladores'),
    ('Segunda terna del alimentador', 'nueva_terna'),
    ('Enlace entre alimentadores', 'refuerzo_red'),
    ('Pintado de postes', None),
])
def test_denominaciones_a_alternativas(texto, alternativa):
    """024:RF-54 — la denominación del CAPEX dice la alternativa del PIDE."""
    assert ec.alternativa_de(texto) == alternativa


def test_anualidad_y_costo_anual_del_art_14():
    """024:RF-57 / 024:RF-58 — anualidad a 30 años y 12 %; costo anual = anualidad + COyM + CP."""
    assert ec.frc(0.12, 30) == pytest.approx(0.124144, abs=1e-6)
    r = ec.costo_anual(100_000, 2_000, 1_000, tasa=0.12, vida=30)
    assert r['costo_anual'] == pytest.approx(100_000 * ec.frc(0.12, 30) + 3_000)
    assert ec.costo_anual(100_000, None, 1_000, tasa=0.12, vida=30)['completo'] is False


def test_van_tir_y_retorno():
    """024:RF-58 / 024:RF-58d — VAN, TIR y período de recuperación."""
    flujos = [-1000] + [300] * 5
    assert ec.van(flujos, 0.0) == 500
    assert ec.van(flujos, ec.tir(flujos)) == pytest.approx(0, abs=1e-6)
    assert ec.retorno(flujos) == pytest.approx(3 + 1 / 3)
    assert ec.tir([-1, -1]) is None


def test_flujo_privado_con_tarifas_y_tasa_privada():
    """024:RF-58c / 024:RF-58d — ingresos de la energía y la potencia nuevas con el pliego,
    20 años, tasa privada; VAN, TIR, beneficio/costo y retorno."""
    e = ec.evaluar(200_000, kw_nuevos=500, usuarios=10, km=2, coym_anual=4_000, cp_anual=2_000,
                   plan=PLAN, factor_carga=0.6, precio_compra_kwh=0.20, opcion='MT3')
    assert len(e.privada['flujos']) == 21 and e.privada['flujos'][0] == -200_000
    assert e.privada['van'] > 0 and e.privada['tir'] > 0.12 and e.privada['retorno_anios'] < 20
    assert e.indicadores['costo_kw'] == 400 and e.indicadores['costo_km'] == 100_000
    assert ec.ingreso_anual_kw(1, PLAN['tarifas']['BT5B'], factor_carga=1, fraccion_punta=0) == \
        pytest.approx(8760 * 0.7185)


def test_sin_datos_no_hay_evaluacion_privada():
    """024:RF-58e — sin precio de compra o factor de carga no se inventa: solo la regulada."""
    e = ec.evaluar(1000, kw_nuevos=10, usuarios=1, km=0, coym_anual=None, cp_anual=None, plan=PLAN,
                   factor_carga=None, precio_compra_kwh=None, opcion='MT3')
    assert e.privada is None and any('evaluación privada sin hacer' in a for a in e.avisos)
    assert e.regulada['anualidad'] > 0


PLAN_PEN = {**PLAN, 'tarifas': {**PLAN['tarifas'], 'moneda': 'PEN'}, 'precio_compra_kwh': 0.20}


def test_van_no_mezcla_tarifas_en_soles_con_capex_en_dolares():
    """024:RF-58 / 025:RF-77 (H4, 2026-11-14): con las tarifas en PEN y el CAPEX en USD, ``evaluar`` no resta
    dólares de soles: sin pasar el plan a la moneda de trabajo, la evaluación privada no se hace y se dice."""
    e = ec.evaluar(200_000, kw_nuevos=500, usuarios=10, km=2, coym_anual=4_000, cp_anual=2_000,
                   plan={**PLAN_PEN, 'moneda_trabajo': 'USD'}, factor_carga=0.6, precio_compra_kwh=0.20,
                   opcion='MT3')
    assert e.privada is None
    assert any('PEN' in a and 'USD' in a for a in e.avisos)
    assert e.regulada['anualidad'] > 0


def test_plan_en_moneda_de_trabajo_con_el_tipo_de_cambio_del_operador():
    """025:RF-67 / 025:RF-77 (H4): tarifas y precio de compra en PEN, trabajo en USD, 3,5 PEN por USD: todo se
    divide por 3,5 una vez, y la VAN privada es la de soles pasada a dólares."""
    plan, avisos = ec.plan_en_moneda_de_trabajo(PLAN_PEN, moneda_trabajo='USD', tipo_cambio=3.5)
    assert not avisos
    assert plan['tarifas']['moneda'] == 'USD' and plan['tarifas']['tipo_cambio_aplicado'] == 3.5
    assert plan['tarifas']['MT3']['energia_punta_kwh'] == pytest.approx(0.3226 / 3.5)
    assert plan['precio_compra_kwh'] == pytest.approx(0.20 / 3.5)
    assert PLAN_PEN['tarifas']['MT3']['energia_punta_kwh'] == 0.3226            # el del perfil no cambia
    otra, _ = ec.plan_en_moneda_de_trabajo(plan, moneda_trabajo='USD', tipo_cambio=3.5)
    assert otra['tarifas']['MT3'] == plan['tarifas']['MT3']                      # ya en USD: no se divide dos veces
    kw = dict(kw_nuevos=500, usuarios=10, km=2, coym_anual=None, cp_anual=None, factor_carga=0.6, opcion='MT3')
    en_soles = ec.evaluar(0, plan=PLAN, precio_compra_kwh=0.20, **kw)
    en_dolares = ec.evaluar(0, plan=plan, precio_compra_kwh=plan['precio_compra_kwh'], **kw)
    assert en_dolares.privada is not None
    assert en_dolares.privada['flujos'][1:] == pytest.approx([f / 3.5 for f in en_soles.privada['flujos'][1:]])


def test_plan_en_otra_moneda_sin_tipo_de_cambio_avisa_y_no_calcula():
    """025:RF-68 / 025:RF-77 (H4): sin el tipo de cambio no se supone 1: sin tarifas ni precio de compra en la
    moneda de trabajo, la evaluación privada y el valor de las pérdidas no se calculan, y se dice."""
    plan, avisos = ec.plan_en_moneda_de_trabajo(PLAN_PEN, moneda_trabajo='USD', tipo_cambio=None)
    assert any('tipo de cambio' in a for a in avisos)
    assert plan.get('precio_compra_kwh') is None
    e = ec.evaluar(1000, kw_nuevos=10, usuarios=1, km=0, coym_anual=None, cp_anual=None, plan=plan,
                   factor_carga=0.6, precio_compra_kwh=plan.get('precio_compra_kwh'), opcion='MT3')
    assert e.privada is None
    misma, sin_aviso = ec.plan_en_moneda_de_trabajo({**PLAN_PEN, 'tarifas': {**PLAN_PEN['tarifas'], 'moneda': 'USD'}},
                                                    moneda_trabajo='USD', tipo_cambio=None)
    assert not sin_aviso and misma['precio_compra_kwh'] == 0.20                  # misma moneda: nada que pasar


def _cand(codigo, alt, problema, ci, cumple=True, van=10.0, criterios=None):
    ev = ec.Evaluacion(ci, {}, {'van': van}, {'costo_kw': ci / 100, 'costo_kwh': None,
                                              'costo_usuario': ci / 10, 'costo_km': None})
    return ec.Candidata(codigo, alt, problema, cumple, ev, criterios or {})


def test_priorizacion_del_art_15():
    """024:RF-33 / 024:RF-34 / 024:RF-58b — fuera las que no cumplen o no rinden; antes la de
    menor costo unitario; para el mismo problema, la más cara que también cumple queda como
    sobredimensionada; los criterios del 15.3 suman con sus pesos."""
    c = [_cand('A', 'bancos', 'P1', 1000), _cand('B', 'cambio_seccion', 'P1', 5000),
         _cand('C', 'nueva_terna', 'P2', 3000, cumple=False), _cand('D', 'nueva_sed', 'P3', 2000, van=-1),
         _cand('E', 'nueva_sed', 'P4', 2000, criterios={'crecimiento_demanda': 1.0})]
    orden = ec.priorizar(c, {'crecimiento_demanda': 1})
    assert [x.codigo for x in orden][:3] == ['A', 'E', 'B']
    assert next(x for x in orden if x.codigo == 'B').sobredimensionada
    assert next(x for x in orden if x.codigo == 'C').descartada == 'no cumple la norma'
    assert 'VAN' in next(x for x in orden if x.codigo == 'D').descartada
    assert next(x for x in orden if x.codigo == 'A').rubro == 'mejoramiento'



def test_una_obra_sin_costo_no_gana_a_otra_con_costo():
    """024:RF-33 / 072:RF-16 (H5, auditor b4) — sin CAPEX no hay costo 0: ``evaluar`` deja la inversión, la anualidad, los
    indicadores y la evaluación privada vacíos, y ``priorizar`` pone la obra sin costo tras la que lo tiene, con su aviso,
    aunque sus criterios del art. 15.3 sumen más. Tampoco marca sobredimensionada a la que sí tiene costo."""
    kw = dict(kw_nuevos=0, usuarios=0, km=0, coym_anual=None, cp_anual=None, plan=PLAN, factor_carga=0.6,
              precio_compra_kwh=0.2, opcion='MT3')
    sin_costo = ec.evaluar(None, **kw)
    assert sin_costo.ci is None and sin_costo.privada is None
    assert sin_costo.regulada['anualidad'] is None and sin_costo.regulada['costo_anual'] is None
    assert sin_costo.regulada['completo'] is False and sin_costo.regulada['van_costos'] is None
    assert all(v is None for v in sin_costo.indicadores.values())
    assert any('sin costo' in a for a in sin_costo.avisos)
    con = ec.Candidata('A', 'bancos', 'P1', True, ec.evaluar(1000.0, **kw), {})
    sin = ec.Candidata('B', 'cambio_seccion', 'P1', True, sin_costo, {'subsanacion_calidad': 1.0})
    orden = ec.priorizar([sin, con], {'subsanacion_calidad': 1})
    assert [c.codigo for c in orden] == ['A', 'B']
    assert not con.sobredimensionada and not sin.sobredimensionada
    assert any('sin costo' in a and 'prioriza' in a for a in sin.evaluacion.avisos)


def test_el_costo_anual_incompleto_no_se_suma_a_medias():
    """024:RF-58 / 072:RF-16 (H5) — sin COyM o sin CP, el costo anual no vale anualidad + lo que haya: queda vacío, con lo
    que falta, y el valor actual de los costos tampoco se da."""
    r = ec.costo_anual(100_000, 2_000, None, tasa=0.12, vida=30)
    assert r['anualidad'] == pytest.approx(100_000 * ec.frc(0.12, 30))
    assert r['costo_anual'] is None and r['completo'] is False and r['falta'] == ['pérdidas']
    e = ec.evaluar(100_000, kw_nuevos=0, usuarios=0, km=0, coym_anual=2_000, cp_anual=None, plan=PLAN,
                   factor_carga=None, precio_compra_kwh=None, opcion='MT3')
    assert e.regulada['van_costos'] is None and any('pérdidas' in a for a in e.avisos)


def test_el_flujo_privado_sin_coym_ni_cp_lleva_su_marca():
    """072:RF-16 (H5) — el flujo privado sin COyM o sin CP no se presenta como completo: ``completo`` False y ``falta`` dice
    qué no lleva; la cifra se conserva (los costos que faltan solo la bajarían) y el aviso lo dice."""
    e = ec.evaluar(200_000, kw_nuevos=500, usuarios=10, km=2, coym_anual=None, cp_anual=None, plan=PLAN,
                   factor_carga=0.6, precio_compra_kwh=0.20, opcion='MT3')
    assert e.privada is not None and e.privada['completo'] is False and e.privada['falta'] == ['COyM', 'pérdidas']
    assert any('por encima' in a for a in e.avisos)
    completa = ec.evaluar(200_000, kw_nuevos=500, usuarios=10, km=2, coym_anual=4_000, cp_anual=2_000, plan=PLAN,
                          factor_carga=0.6, precio_compra_kwh=0.20, opcion='MT3')
    assert completa.privada['completo'] is True and completa.privada['falta'] == []
    assert completa.regulada['van_costos'] is not None


def test_sin_tipo_de_cambio_la_evaluacion_lo_marca():
    """025:RF-68 (H4 y H5) — sin tipo de cambio, la evaluación lo marca para que F09 y F10 lo digan en vez de un 0."""
    plan, _ = ec.plan_en_moneda_de_trabajo(PLAN_PEN, moneda_trabajo='USD', tipo_cambio=None)
    e = ec.evaluar(1000, kw_nuevos=10, usuarios=1, km=0, coym_anual=None, cp_anual=None, plan=plan,
                   factor_carga=0.6, precio_compra_kwh=plan.get('precio_compra_kwh'), opcion='MT3')
    assert e.privada is None and e.sin_tipo_de_cambio is True
    con_tc, _ = ec.plan_en_moneda_de_trabajo(PLAN_PEN, moneda_trabajo='USD', tipo_cambio=3.5)
    assert ec.evaluar(1000, kw_nuevos=10, usuarios=1, km=0, coym_anual=None, cp_anual=None, plan=con_tc,
                      factor_carga=0.6, precio_compra_kwh=con_tc['precio_compra_kwh'],
                      opcion='MT3').sin_tipo_de_cambio is False


def test_con_y_sin_no_suma_la_cartera_a_medias():
    """072:RF-14 / 072:RF-16 (H5) — si una obra aplicada no tiene costo, la inversión de la cartera no se toma como la de
    las otras: queda el hueco, no una VAN con una obra gratuita."""
    anios = [{'anio': 0, 'perdidas_kw': 100.0, 'con_proyecto': {'perdidas_kw': 90.0}}]
    obras = [{'anio': 4, 'ci': 1000.0, 'variacion_autonoma': 'V1'}, {'anio': 4, 'ci': None, 'variacion_autonoma': 'V2'}]
    r = ec.con_y_sin_de_las_aplicadas(obras, anios, PLAN, factor_carga=0.5, precio_compra_kwh=0.1)
    assert 'van' not in r and 'costo' in r['hueco']

def test_el_perfil_de_electro_dunas_trae_lo_que_pide_la_evaluacion():
    """024:RF-31 / 024:RF-58c — tolerancia NTCSER, tasas, vida útil, horizonte y tarifas en el
    perfil, con su fuente."""
    import json

    datos = json.loads((carpeta_perfiles() / 'electro_dunas.json').read_text(encoding='utf-8'))
    assert datos['normas']['NTCSER']['tension_min_pu'] == 0.94
    plan = datos['planificacion']
    assert plan['tasa_privada'] == 0.12 and plan['vida_util_anios'] == 30
    assert plan['tarifas']['MT3']['energia_punta_kwh'] == 0.3226
