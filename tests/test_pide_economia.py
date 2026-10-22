"""Spec 024, T14: evaluación económica y priorización del PIDE, sin DIgSILENT."""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from igea_dgs import pide_economia as ec
from igea_dgs.perfil_empresa import carpeta_perfiles

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
    assert e.privada is None and any('RF-58e' in a for a in e.avisos)
    assert e.regulada['anualidad'] > 0


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


def test_el_perfil_de_electro_dunas_trae_lo_que_pide_la_evaluacion():
    """024:RF-31 / 024:RF-58c — tolerancia NTCSER, tasas, vida útil, horizonte y tarifas en el
    perfil, con su fuente."""
    import json

    datos = json.loads((carpeta_perfiles() / 'electro_dunas.json').read_text(encoding='utf-8'))
    assert datos['normas']['NTCSER']['tension_min_pu'] == 0.94
    plan = datos['planificacion']
    assert plan['tasa_privada'] == 0.12 and plan['vida_util_anios'] == 30
    assert plan['tarifas']['MT3']['energia_punta_kwh'] == 0.3226
