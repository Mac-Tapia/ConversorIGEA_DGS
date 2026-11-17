"""Pruebas del motor base de conversión.

Spec 034: 034:RF-4, 034:RF-12. Spec 080: 080:RF-53 a RF-55 y 080:RF-58 (aéreo o cable, el tipo
VNR en el resolvedor, el estado del tramo y la capacitancia de los cables).
"""
from pathlib import Path

import pytest


def test_vnr_bridge_preserves_capacitor_source_fields():
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.models import Capacitor, CanonicalModel, ConductorType, Load, Node, Section, Source

    model = CanonicalModel(
        metadata={'working_crs_is_projected': True},
        nodes=[Node('N1', 0, 0), Node('N2', 100, 0)],
        sections=[Section('S1', 'N1', 'N2', conductor_code='AA', phases='ABC',
                          length_m=100, feeder_id='CA101')],
        sources=[Source('SRC', 'N1', nominal_kv=10, feeder_id='CA101')],
        loads=[Load('L1', 'N2', kw=10, kvar=2, phases='ABC', feeder_id='CA101')],
        conductor_types=[ConductorType('AA', r1_ohm_km=.2, x1_ohm_km=.3,
                                       r0_ohm_km=.4, x0_ohm_km=.5, ampacity_a=200)],
        capacitors=[Capacitor('BC1', 'N2', kvar=450, feeder_id='CA101',
                              phases='ABC', steps=3, nominal_kv=10, status='in_service')],
    )

    result = canonical_to_cymdist(model, source_path=Path('fuente.gpkg'))
    row = result.dataset.capacitor_settings[0]

    assert row['DeviceNumber'] == 'BC1'
    assert row['NetworkID'] == 'CA101'
    assert row['NodeID'] == 'N2'
    assert row['TotalKVAR'] == '450'
    assert row['NumberOfSteps'] == '3'
    assert row['Phase'] == 'ABC'


def test_vnr_bridge_retains_capacitor_without_capacity_for_audit():
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.models import Capacitor, CanonicalModel

    result = canonical_to_cymdist(
        CanonicalModel(capacitors=[Capacitor('BC_SIN_Q', 'N0', kvar=0)]),
        source_path=Path('fuente.json'),
    )

    assert len(result.dataset.capacitor_settings) == 1
    assert result.dataset.capacitor_settings[0]['TotalKVAR'] == ''


#: Dos códigos de empresa sintéticos: el medio del tramo no depende del código de la empresa.
EMPRESAS_VNR = ('EMPA', 'EMPB')


def _vnr_con_cable_y_tramo_fuera(*, interruptor_propio: bool = False, alimentador: str = 'F1',
                                 empresa: str = ''):
    """Un alimentador VNR: un tramo de cable (capa subterránea), uno aéreo y uno fuera de servicio."""
    from convertersmartgrid.adaptadores.entrada.vnr.models import (
        CanonicalModel, ConductorType, Load, Node, Section, Source, Switch)

    model = CanonicalModel(
        metadata={'working_crs_is_projected': True, 'company': empresa},
        nodes=[Node('N1', 0, 0, nominal_kv=10), Node('N2', 100, 0, nominal_kv=10),
               Node('N3', 200, 0, nominal_kv=10), Node('N4', 300, 0, nominal_kv=10)],
        sections=[
            Section('S_CABLE', 'N1', 'N2', conductor_code='N2070', phases='ABC', nominal_kv=10,
                    length_m=100, source_layer='Tramo_MT_Subterraneo', feeder_id=alimentador),
            Section('S_AEREO', 'N2', 'N3', conductor_code='AA070', phases='ABC', nominal_kv=10,
                    length_m=100, source_layer='Tramo_MT', feeder_id=alimentador),
            Section('S_FUERA', 'N3', 'N4', conductor_code='AA070', phases='ABC', nominal_kv=10,
                    length_m=100, source_layer='Tramo_MT', feeder_id=alimentador, status='out_of_service'),
        ],
        sources=[Source('SRC', 'N1', nominal_kv=10, feeder_id=alimentador)],
        loads=[Load('L1', 'N2', kw=100, kvar=30, phases='ABC', feeder_id=alimentador),
               Load('L2', 'N4', kw=50, kvar=10, phases='ABC', feeder_id=alimentador)],
        conductor_types=[
            ConductorType('N2070', r1_ohm_km=.34, x1_ohm_km=.12, r0_ohm_km=1.2, x0_ohm_km=.25,
                          ampacity_a=250, section_mm2=70),
            ConductorType('AA070', r1_ohm_km=.5, x1_ohm_km=.45, r0_ohm_km=.7, x0_ohm_km=1.5,
                          ampacity_a=220),
        ],
    )
    if interruptor_propio:
        model.switches = [Switch('SW1', 'N4', kind='SWITCH', on_off=1, section_id='S_FUERA',
                                 location='L')]
    return model


@pytest.mark.parametrize('empresa', EMPRESAS_VNR)
def test_vnr_tramo_de_cable_no_sale_aereo_y_se_anota(empresa):
    """080:RF-53 — la capa subterránea hace cable el tramo; el aéreo sin indicio, aéreo; los dos se anotan.

    Igual para dos distribuidoras: nada depende del código de la empresa.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.model import build_feeder_model

    alimentador = f'{empresa}-MT01'
    result = canonical_to_cymdist(_vnr_con_cable_y_tramo_fuera(alimentador=alimentador, empresa=empresa),
                                  source_path=Path('VNR.zip'))
    lc = result.dataset.line_configurations

    assert lc['S_CABLE']['Overhead'] == '0'
    assert lc['S_AEREO']['Overhead'] == '1' and lc['S_FUERA']['Overhead'] == '1'
    tablas = result.dataset.equipment_tables
    assert [r['ID'] for r in tablas['CONCENTRIC NEUTRAL CABLE']] == ['N2070']
    assert [r['ID'] for r in tablas['LINE']] == ['AA070']
    deducidos = {(i['code'], i['source_id'], i['metodo'], i['tramos']) for i in result.issues
                 if i['code'] in ('CABLE_DEDUCED', 'OVERHEAD_DEDUCED')}
    assert deducidos == {('CABLE_DEDUCED', 'N2070', 'SOURCE_LAYER', 1),
                         ('OVERHEAD_DEDUCED', 'AA070', 'DEFAULT_OVERHEAD', 2)}
    lineas = {l.section_id: l for l in build_feeder_model(result.dataset, alimentador).lines}
    assert lineas['S_CABLE'].overhead is False and lineas['S_CABLE'].type_key == 'CABLE:N2070'
    assert lineas['S_AEREO'].overhead is True and lineas['S_AEREO'].type_key == 'LINE:AA070'


def test_vnr_medio_por_prioridad_fuente_perfil_capa_y_norma():
    """080:RF-53 — la fuente manda; luego la regla del perfil, la capa, la norma y, sin nada, aéreo."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import (
        canonical_to_cymdist, deducir_medio)
    from convertersmartgrid.adaptadores.entrada.vnr.models import ConductorType, Section

    def tramo(**kw):
        return Section('S', 'A', 'B', **{'conductor_code': 'CU035', 'source_layer': 'mtTramo', **kw})

    autoportante = ConductorType('CU035', description='CABLE AUTOPORTANTE CAAI 3X35MM2 XLPE')
    seco = ConductorType('CU035', description='CABLE SECO N2XSY 3-1X35MM2 18/30 KV')
    assert deducir_medio(tramo(overhead=False), autoportante) == (False, 'SOURCE')
    assert deducir_medio(tramo(), ConductorType('CU035', overhead=True), r'^CU') == (True, 'SOURCE')
    assert deducir_medio(tramo(), None, r'^CU0') == (False, 'PROFILE_RULE')
    assert deducir_medio(tramo(source_layer='Red_Aerea_MT'), seco) == (True, 'SOURCE_LAYER')
    assert deducir_medio(tramo(), autoportante) == (True, 'CONDUCTOR_TYPE')
    assert deducir_medio(tramo(), seco) == (False, 'CONDUCTOR_TYPE')
    assert deducir_medio(tramo(), None) == (True, 'DEFAULT_OVERHEAD')
    # Una regla del perfil mal escrita no impide convertir: se ignora y se deduce lo demás.
    assert deducir_medio(tramo(), seco, '([') == (False, 'CONDUCTOR_TYPE')

    model = _vnr_con_cable_y_tramo_fuera()
    model.sections[0].source_layer = 'Tramo_MT'
    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'), patron_cable=r'^N2')
    assert result.dataset.line_configurations['S_CABLE']['Overhead'] == '0'
    assert any(i['code'] == 'CABLE_DEDUCED' and i['metodo'] == 'PROFILE_RULE' for i in result.issues)


def test_vnr_parametros_del_tipo_y_tension_llegan_al_resolvedor():
    """080:RF-54 — R, X, amperios y tensión del tipo VNR llegan al resolvedor; lo que falta, de cable."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.catalog_resolution import resolve_dataset_equipment
    from convertersmartgrid.reconstruction import ReconstructionPolicy, reconstruct_dataset

    model = _vnr_con_cable_y_tramo_fuera()
    cable = model.conductor_types[0]
    cable.r0_ohm_km = cable.x0_ohm_km = cable.ampacity_a = None   # el tipo llega a medias
    bridge = canonical_to_cymdist(model, source_path=Path('VNR.zip'))
    config = bridge.dataset.line_configurations['S_CABLE']
    assert config['NominalKV'] == '10'
    assert float(config['R1']) == pytest.approx(.34) and float(config['X1']) == pytest.approx(.12)

    result = reconstruct_dataset(bridge.dataset, ReconstructionPolicy(), [])
    resolved = resolve_dataset_equipment(result, [])

    [fila] = result.dataset.equipment_tables['CONCENTRIC NEUTRAL CABLE']
    assert fila['ID'] == 'N2070'
    assert float(fila['R1']) == pytest.approx(.34) and float(fila['X1']) == pytest.approx(.12)
    assert float(fila['R0']) == pytest.approx(.34)       # de la R1 de la fuente, no un genérico
    assert float(fila['X0']) == pytest.approx(.3)        # el de un cable, no el aéreo de 1,2
    assert resolved['N2070'].rule == 'PHYSICAL_DERIVATION'
    assert all(r['ID'] != 'N2070' for r in result.dataset.equipment_tables.get('LINE', ()))


@pytest.mark.parametrize('interruptor_propio', [False, True])
def test_vnr_tramo_fuera_de_servicio_no_entra_energizado(interruptor_propio):
    """080:RF-55 — abierto por sus dos extremos, con su maniobra si la tiene; se conserva y se anota."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.model import build_feeder_model

    result = canonical_to_cymdist(_vnr_con_cable_y_tramo_fuera(interruptor_propio=interruptor_propio),
                                  source_path=Path('VNR.zip'))

    assert 'S_FUERA' in result.dataset.sections                       # no se borra de la red
    filas = [r for r in result.dataset.switch_settings if r['SectionID'] == 'S_FUERA']
    assert {r['Location'] for r in filas} == {'S', 'L'}
    assert all(r['Status'] == '0' for r in filas)
    if interruptor_propio:
        assert [r['EqNumber'] for r in filas if r['Location'] == 'L'] == ['SW1']
    assert not [r for r in result.dataset.switch_settings
                if r['SectionID'] != 'S_FUERA' and r['Status'] == '0']
    assert [i['source_id'] for i in result.issues if i['code'] == 'SECTION_OUT_OF_SERVICE'] == ['S_FUERA']
    modelo = build_feeder_model(result.dataset, 'F1')
    lados = {d.terminal_side: d.on_off for d in modelo.devices if d.section_id == 'S_FUERA'}
    assert lados == {0: 0, 1: 0}


def test_vnr_cable_sin_capacitancia_toma_la_de_su_ficha():
    """080:RF-58 — un cable VNR sin B sale con la de su ficha (B1 = B0 > 0) y se anota; el aéreo no cambia."""
    import math

    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    model = _vnr_con_cable_y_tramo_fuera()
    for tramo in model.sections:
        tramo.nominal_kv = 13.2
    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    [cable] = result.dataset.equipment_tables['CONCENTRIC NEUTRAL CABLE']
    # 70 mm², red de 13,2 kV (Um 17,5): cable 8,7/15 kV; ficha HES Kablo N2XSYR(A)Y, 0,229 µF/km.
    esperado = 2 * math.pi * 60 * 0.229
    assert float(cable['B1']) == pytest.approx(esperado, rel=1e-6) and cable['B0'] == cable['B1']
    [linea] = result.dataset.equipment_tables['LINE']
    assert linea['B1'] == '0'
    [nota] = [i for i in result.issues if i['code'] == 'CAPACITANCIA_DEDUCIDA']
    assert nota['source_id'] == 'N2070' and nota['metodo'] == 'FICHA' and 'HES Kablo' in nota['detalle']


def test_vnr_cable_sin_ficha_deriva_la_capacitancia_de_su_geometria():
    """080:RF-58 — sin ficha (22,9 kV, sin sección), C = εr/(18·ln(Di/dc)), nunca 0, con sus referencias."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    model = _vnr_con_cable_y_tramo_fuera()
    for nodo in model.nodes:
        nodo.nominal_kv = 22.9
    for tramo in model.sections:
        tramo.nominal_kv = 22.9
    model.sources[0].nominal_kv = 22.9
    model.conductor_types[0].section_mm2 = None
    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    [cable] = result.dataset.equipment_tables['CONCENTRIC NEUTRAL CABLE']
    assert float(cable['B1']) > 0 and cable['B0'] == cable['B1']
    [nota] = [i for i in result.issues if i['code'] == 'CAPACITANCIA_DEDUCIDA']
    assert nota['metodo'] == 'FORMULA'
    assert all(ref in nota['detalle'] for ref in ('IEC 60287-1-1', 'IEC 60502-2', '18/30 kV', 'supuesta'))


#: Fichas de fabricante leídas (µF/km, «Operation Capacitance»), cable unipolar Cu/XLPE:
#: 8,7/15 kV, HES Kablo N2XSYR(A)Y (IEC 60502-2): https://www.hes.com.tr/assets/doc/urunler-pdf/en/441.pdf
#: 18/30 kV, HES Kablo N2XSY (VDE 0276-620): https://www.hes.com.tr/assets/doc/urunler-pdf/en/604.pdf
FICHA_8_7_15 = ((35, 0.181), (70, 0.229), (120, 0.278), (240, 0.363))
FICHA_18_30 = ((50, 0.135), (70, 0.151), (120, 0.180), (240, 0.229))


@pytest.mark.parametrize('kv, ficha', [(13.2, FICHA_8_7_15), (22.9, FICHA_18_30)])
def test_la_formula_del_cable_reproduce_la_ficha_del_fabricante(kv, ficha):
    """080:RF-58 — la geometría da la capacitancia de la ficha del fabricante con menos del 5 % de error.

    13,2 kV (Um 17,5) lleva cable 8,7/15 kV y 22,9 kV (Um 36), 18/30 kV; los dos con ficha.
    """
    from convertersmartgrid.catalog import capacitancia_cable, capacitancia_formula_uf_km

    for seccion, valor in ficha:
        assert capacitancia_formula_uf_km(seccion, kv) == pytest.approx(valor, rel=0.05)
        c, metodo, detalle = capacitancia_cable(seccion, kv)
        assert (c, metodo) == (valor, 'FICHA') and 'https://www.hes.com.tr/' in detalle
    # El EPR (εr 3,0) da más capacitancia que el XLPE (2,5) con la misma geometría.
    assert capacitancia_formula_uf_km(70, 10.0, 'EPR') == pytest.approx(
        capacitancia_formula_uf_km(70, 10.0) * 3.0 / 2.5)


@pytest.mark.parametrize('kv, aislante', [(6.0, 'XLPE'), (3.3, 'XLPE'), (13.2, 'EPR')])
def test_cable_sin_ficha_va_por_la_formula_marcada_supuesta(kv, aislante):
    """080:RF-58 — 6/10 kV, 3,6/6 kV y el EPR no tienen ficha: fórmula, «supuesta», con la cita de εr."""
    from convertersmartgrid.catalog import capacitancia_cable

    c, metodo, detalle = capacitancia_cable(70, kv, aislante)
    assert c > 0 and metodo == 'FORMULA' and 'supuesta' in detalle
    cita = ('IEC 60287-1-1, tabla 3, según quickfield.com' if aislante == 'XLPE'
            else 'εr 3,0 del EPR: supuesta')
    assert cita in detalle


def test_vnr_cable_de_22_9_kv_toma_la_ficha_de_18_30():
    """080:RF-58 — un cable VNR de 70 mm² en una red de 22,9 kV: ficha de 18/30 kV, 0,151 µF/km."""
    import math

    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    model = _vnr_con_cable_y_tramo_fuera()
    for tramo in model.sections:
        tramo.nominal_kv = 22.9
    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    [cable] = result.dataset.equipment_tables['CONCENTRIC NEUTRAL CABLE']
    assert float(cable['B1']) == pytest.approx(2 * math.pi * 60 * 0.151, rel=1e-6)
    [nota] = [i for i in result.issues if i['code'] == 'CAPACITANCIA_DEDUCIDA']
    assert nota['metodo'] == 'FICHA' and '18/30 kV' in nota['detalle'] and '604.pdf' in nota['detalle']


def _cable_de_10_kv(**tipo):
    """El VNR de prueba con su cable de 70 mm² en una red de 10 kV (Um 12: 6/10 kV por la norma)."""
    model = _vnr_con_cable_y_tramo_fuera()
    for campo, valor in tipo.items():
        setattr(model.conductor_types[0], campo, valor)
    return model


def _nota_de_capacitancia(model, **kw):
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'), **kw)
    [nota] = [i for i in result.issues if i['code'] == 'CAPACITANCIA_DEDUCIDA']
    [cable] = result.dataset.equipment_tables['CONCENTRIC NEUTRAL CABLE']
    return nota, float(cable['B1'])


def test_clase_paso_1_la_de_la_designacion_de_la_fuente():
    """080:RF-58 — la designación del tipo («… 18/30 kV») manda, aunque la red sea de 10 kV."""
    nota, _b = _nota_de_capacitancia(_cable_de_10_kv(description='CABLE N2XSY 3-1x70 mm2 18/30 kV',
                                                     clase_cable_rx='8,7/15 kV'))
    assert (nota['clase'], nota['metodo_clase'], nota['c_uf_km']) == ('18/30 kV', 'CLASE_DE_LA_FUENTE', 0.151)


def test_cable_de_10_kv_con_r_y_x_de_8_7_15_toma_la_c_de_8_7_15(tmp_path):
    """080:RF-58 — coherencia: la R y la X salen de la ficha Indeco N2XSY 8,7/15 kV de la semilla del
    catálogo; la C es la del mismo cable (8,7/15 kV, 0,229 µF/km), no la de 6/10 kV de la norma."""
    from convertersmartgrid.catalog import asegurar_catalogo_empresa
    from convertersmartgrid.sources.vnr import fichas_del_catalogo

    model = _vnr_con_cable_y_tramo_fuera()
    model.sections[0].conductor_code = 'N207003D'
    tipo = model.conductor_types[0]
    tipo.conductor_code = 'N207003D'
    tipo.r1_ohm_km = tipo.x1_ohm_km = tipo.r0_ohm_km = tipo.x0_ohm_km = tipo.ampacity_a = None

    fichas_del_catalogo(model, asegurar_catalogo_empresa(tmp_path / 'catalogo_parametros.xlsx'))

    assert tipo.r1_ohm_km == pytest.approx(0.268) and tipo.clase_cable_rx == '8,7/15 kV'
    nota, b = _nota_de_capacitancia(model)
    assert (nota['clase'], nota['metodo_clase'], nota['c_uf_km']) == (
        '8,7/15 kV', 'CLASE_COHERENTE_CON_RX', 0.229)


@pytest.mark.parametrize('texto, clase', [
    ('CABLE N2XSY 8,7/15 kV', '8,7/15 kV'), ('N2XSY 8.7/15', '8,7/15 kV'), ('18/30 (36) kV', '18/30 kV'),
    ('12/20 kV', '12/20 kV'), ('6/10kV', '6/10 kV'), ('3.6/6', '3,6/6 kV'), ('cable de 15 kV', '8,7/15 kV'),
    ('cable 30 kV', '18/30 kV'), ('RED SUBTERRANEA CABLE N2XSY 3-1x120 mm2', None), ('red de 22,9 kV', None),
])
def test_clase_de_la_designacion(texto, clase):
    """080:RF-58 — una sola regla: la U de la designación es la de la clase; una U que no es de clase, nada."""
    from convertersmartgrid.catalog import clase_de_designacion

    assert clase_de_designacion(texto) == clase


@pytest.mark.parametrize('kv, clase, regla', [
    (10.0, '8,7/15 kV', 'FASE'), (13.2, '8,7/15 kV', 'FASE'), (22.9, '18/30 kV', 'FASE'),
    (33.0, '18/30 kV', 'TABLA_1'), (6.0, '6/10 kV', 'FASE'), (20.0, '18/30 kV', 'FASE'),
])
def test_clase_del_cable_por_la_tension_de_fase(kv, clase, regla):
    """080:RF-58 — la menor clase de IEC 60502-2 con U0 ≥ kV/√3·1,05 y Um ≥ kV·1,05.

    10 kV: 5,77·1,05 = 6,06 > 6 → 8,7/15 kV (el usuario, 2026-11-14: «sus cables de 10 kV son N2XSY
    8,7/15 kV»). 33 kV: 20,0 > 18 no cabe en ninguna; la tabla 1 de IEC 60502-2 da 18/30 para Um 36.
    """
    from convertersmartgrid.catalog import clase_de_cable, regla_de_clase

    assert regla_de_clase(kv) == (clase, regla)
    assert clase_de_cable(kv)[0] == clase


def test_cable_de_10_kv_toma_la_ficha_de_8_7_15_sin_suponer():
    """080:RF-58 — 10 kV ya no da 6/10 por la norma A/B: da 8,7/15 kV con su ficha, sin «supuesta»."""
    from convertersmartgrid.catalog import capacitancia_cable

    c, metodo, detalle = capacitancia_cable(70, 10.0)
    assert (c, metodo) == (0.229, 'FICHA') and 'supuesta' not in detalle


def test_clase_paso_2_coherente_con_la_ficha_de_r_y_x():
    """080:RF-58 — sin designación, la clase de la ficha que dio R y X manda sobre la de la tensión."""
    nota, _b = _nota_de_capacitancia(_cable_de_10_kv(clase_cable_rx='18/30 kV'))
    assert (nota['clase'], nota['metodo_clase'], nota['c_uf_km']) == (
        '18/30 kV', 'CLASE_COHERENTE_CON_RX', 0.151)


def test_clase_paso_3_la_tension_de_fase_de_la_red():
    """080:RF-58 — sin designación ni ficha, la tensión de fase: 10 kV → 8,7/15 kV, con su ficha."""
    nota, _b = _nota_de_capacitancia(_cable_de_10_kv())
    assert (nota['clase'], nota['metodo_clase'], nota['regla_clase'], nota['metodo'], nota['c_uf_km']) == (
        '8,7/15 kV', 'CLASE_POR_TENSION_DE_FASE', 'FASE', 'FICHA', 0.229)


@pytest.mark.parametrize('kv, regla', [(20.0, 'FASE'), (33.0, 'TABLA_1')])
def test_clase_paso_3_en_20_y_33_kv_con_su_metodo(kv, regla):
    """080:RF-58 — paso (3): criterio de fase del usuario con margen; si ninguna clase cumple, tabla 1 por Um.

    20 kV da 18/30 kV por el criterio de fase (conservador: la tabla 1 daría 12/20 para Um 24);
    33 kV no cabe en ninguna con margen y la tabla 1 da 18/30 para Um 36.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import PASO_3_CLASE

    model = _cable_de_10_kv()
    for tramo in model.sections:
        tramo.nominal_kv = kv
    nota, b = _nota_de_capacitancia(model)
    assert (nota['clase'], nota['metodo_clase'], nota['regla_clase']) == (
        '18/30 kV', 'CLASE_POR_TENSION_DE_FASE', regla)
    assert nota['criterio_clase'] == PASO_3_CLASE and b > 0


def test_perfil_ilegible_deja_constancia_y_no_bloquea(monkeypatch, caplog):
    """080:RF-53 — un perfil que no se puede leer no impide convertir (reconstruir, no bloquear), pero ya no se calla:
    queda el aviso PERFIL_ILEGIBLE con su causa y el medio se deduce de la fuente."""
    import logging

    from convertersmartgrid import perfil_empresa
    from convertersmartgrid.adaptadores.entrada.vnr.application import cymdist_bridge

    def perfil_roto():
        raise ValueError('perfil dañado de prueba')

    monkeypatch.setattr(perfil_empresa, 'datos_perfil', perfil_roto)
    with caplog.at_level(logging.WARNING, logger='convertersmartgrid'):
        assert cymdist_bridge.patron_cable_del_perfil() is None
    avisos = [r for r in caplog.records if 'PERFIL_ILEGIBLE' in r.getMessage()]
    assert avisos and 'perfil dañado de prueba' in avisos[0].getMessage()
