"""Tramos puente DEFAULT: se funden sin perder ningún elemento de la base.

Red de prueba, con la forma medida en 260924.mdb:

    FUENTE ─L1(AA)─ A ─P1(DEFAULT, seccionador)─ B ─L2(AA)─ C ─P2(DEFAULT, carga)─ D
                                                             └─P3(DEFAULT, nada)── E ─L3─ F
"""

from __future__ import annotations

import pytest

from igea_dgs.catalog import leer_trafos, tablas_equipo_desde_catalogo
from igea_dgs.combine import combine_models, unsupplied_nodes
from igea_dgs.model import FeederModel, Line, LineType, Load, Node, Sed, SwitchingDevice
from igea_dgs.puentes import fundir_puentes


def _linea(sid, a, b, code='AA05003D', m=100.0, overhead=True):
    key = f'LINE:{code}' if overhead else f'CABLE:{code}'
    return Line(sid, a, b, 'ABC', key, code, m, overhead)


def _modelo(nombre='F1', prefijo='') -> FeederModel:
    n = lambda x: f'{prefijo}{x}'  # noqa: E731
    nodos = {n(k): Node(n(k), float(i * 10), 0.0) for i, k in enumerate('SABCDEF')}
    lineas = [
        _linea(n('L1'), n('S'), n('A')),
        _linea(n('P1'), n('A'), n('B'), 'DEFAULT', 2.0),
        _linea(n('L2'), n('B'), n('C')),
        _linea(n('P2'), n('C'), n('D'), 'DEFAULT', 0.3, overhead=False),
        _linea(n('P3'), n('C'), n('E'), 'DEFAULT', 2.0),
        _linea(n('L3'), n('E'), n('F')),
    ]
    tipo = LineType('LINE:AA05003D', 'AA05003D', 'LINE', 0.6755, 0.6755, 0.47, 1.4, 3.1, 0, 195)
    defecto = LineType('LINE:DEFAULT', 'DEFAULT', 'LINE', 0.4, 0.4, 0.4, 1.4, 0, 0, 400)
    carga = Load(n('P2'), n('D1'), 'C1', '1', n('D'), 0.05, 0.01, 0.98, 100, 0, 'ABC',
                 sed_code='SE1')
    sed = Sed('SE1', 'SE1', n('D'), 100.0, n('P2'), n('D1'), (n('P2'), n('D1')))
    secc = SwitchingDevice('sectionalizer', n('P1'), 'S', 0, n('A'), 'SF01', n('SW1'),
                           'ABC', 1, 0, 0)
    m = FeederModel(
        name=nombre, network_id=f'NET_{nombre}', nominal_kv=10.0, source_node=n('S'),
        nodes=nodos, lines=lineas, loads=[carga], devices=[secc],
        line_types={t.key: t for t in (tipo, defecto)}, seds=[sed],
    )
    m.section_by_id = {ln.section_id: ln for ln in lineas}
    return m


def test_ningun_tramo_default_llega_al_modelo():
    m = _modelo()
    informe = fundir_puentes(m)
    assert informe.tramos == 3
    assert {ln.source_type_code for ln in m.lines} == {'AA05003D'}
    assert 'LINE:DEFAULT' not in m.line_types, 'un TypLne sin líneas no se escribe'


def test_el_seccionador_pasa_a_interruptor_entre_sus_dos_barras():
    m = _modelo()
    fundir_puentes(m)
    assert m.devices == []
    [c] = m.couplers
    assert (c.node_a, c.node_b, c.on_off, c.eq_number) == ('A', 'B', 1, 'SW1')


def test_la_sed_y_su_carga_quedan_en_la_barra_fundida():
    m = _modelo()
    informe = fundir_puentes(m)
    assert 'D' not in m.nodes and 'E' not in m.nodes
    assert m.loads[0].node_id == 'C' and m.seds[0].node_id == 'C'
    assert informe.cargas_reubicadas == 1 and informe.seds_reubicadas == 1
    # El tramo que colgaba del puente puro sigue conectado, ahora desde C.
    l3 = next(ln for ln in m.lines if ln.section_id == 'L3')
    assert (l3.from_node, l3.to_node) == ('C', 'F')


def test_nada_queda_sin_camino_a_la_fuente():
    m = _modelo()
    fundir_puentes(m)
    assert unsupplied_nodes(m, [m.source_node]) == set(), (
        'los interruptores sin tramo deben contar como conexión')


def test_la_barra_de_la_fuente_nunca_desaparece():
    m = _modelo()
    m.lines.insert(0, _linea('P0', 'A', 'S', 'DEFAULT', 1.0))
    fundir_puentes(m)
    assert m.source_node == 'S' and 'S' in m.nodes


def test_dos_equipos_en_un_puente_van_en_serie():
    m = _modelo()
    m.devices.append(SwitchingDevice('switch', 'P1', 'L', 1, 'B', 'SW', 'SW2', 'ABC', 0, 0, 0))
    fundir_puentes(m)
    assert len(m.couplers) == 2
    a, b = m.couplers
    assert a.node_a == 'A' and a.node_b == b.node_a and b.node_b == 'B'
    assert b.node_a in m.nodes


def test_la_red_unida_conserva_los_interruptores(tmp_path):
    m1, m2 = _modelo('F1', 'x'), _modelo('F2', 'y')
    fundir_puentes(m1)
    fundir_puentes(m2)
    unido, _ = combine_models([m1, m2], name='G')
    assert len(unido.couplers) == 2
    assert unido.combined.de_energised == set()


def test_dgs_con_interruptores_valida_sin_errores(tmp_path):
    pytest.importorskip('pyproj')
    from igea_dgs.dgs import write_dgs
    from igea_dgs.validate import parse_dgs, validate_dgs

    m = _modelo()
    fundir_puentes(m)
    out = tmp_path / 'F1.dgs'
    write_dgs(m, out)
    rep = validate_dgs(m, out)
    assert rep['errors_total'] == 0, rep
    tablas = parse_dgs(out)
    coups = tablas['ElmCoup']['rows_dict']
    assert len(coups) == len(m.seds) + len(m.couplers)


# ---------------------------------------------------------------------------
# Catálogo Excel como fuente de equipos
# ---------------------------------------------------------------------------

def _catalogo(tmp_path):
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'conductores_aereos'
    ws.append(['codigo', 'R1_modelo_ohm_km', 'X1_modelo_ohm_km', 'R0_modelo_ohm_km',
               'X0_modelo_ohm_km', 'B1_modelo_uS_km', 'ampacidad_modelo_A', 'estado'])
    ws.append(['AA05003D', 0.6755, 0.47, 0.8, 1.4, 3.1, 195, 'por_confirmar'])
    ws.append(['AA05002D', 0.6755, 0.41, 0.8, 1.4, 3.9, 201, 'por_confirmar'])
    tr = wb.create_sheet('transformadores_sed')
    tr.append(['kVA', 'uk_pct', 'Pk_W', 'Po_W', 'io_pct', 'estado'])
    tr.append([25, 4, 600, 63, None, 'referencia'])
    tr.append([5, None, None, None, None, 'por_confirmar'])
    ruta = tmp_path / 'catalogo.xlsx'
    wb.save(ruta)
    return ruta


def test_equipos_desde_el_catalogo_con_sus_valores(tmp_path):
    info = tablas_equipo_desde_catalogo(_catalogo(tmp_path))
    fila = next(f for f in info.tablas['LINE'] if f['ID'] == 'AA05003D')
    assert float(fila['R1']) == 0.6755 and float(fila['Amps']) == 195


def test_codigo_ausente_se_completa_por_material_y_seccion(tmp_path):
    info = tablas_equipo_desde_catalogo(
        _catalogo(tmp_path), codigos_en_red=[('AA05001D', True)])
    assert info.completados == {'AA05001D': 'AA05003D'}, 'prefiere el trifásico'
    assert any(f['ID'] == 'AA05001D' for f in info.tablas['LINE'])


def test_codigo_sin_pariente_no_se_inventa(tmp_path):
    info = tablas_equipo_desde_catalogo(
        _catalogo(tmp_path), codigos_en_red=[('CU07003D', True)])
    assert info.sin_resolver == ['CU07003D']


def test_trafos_solo_con_datos_completos(tmp_path):
    assert leer_trafos(_catalogo(tmp_path)) == {
        25.0: {'uk_pct': 4.0, 'Pk_W': 600.0, 'Po_W': 63.0, 'io_pct': 0.0}}


# ---------------------------------------------------------------------------
# SED con más carga que potencia instalada
# ---------------------------------------------------------------------------

def test_solo_se_redimensiona_la_sed_que_no_puede_con_su_carga():
    from dataclasses import replace

    from igea_dgs.sed_potencia import redimensionar_sobrecargadas

    m = _modelo()
    m.loads = [replace(m.loads[0], p_mw=0.388, q_mvar=0.097)]   # 400 kVA
    m.seds = [replace(m.seds[0], design_kva=50.0)]
    [cambio] = redimensionar_sobrecargadas(m)
    # 388 kW + 97 kvar = 399,9 kVA: el menor normalizado que la cubre es 400.
    assert (cambio.kva_base, cambio.kva_nuevo) == (50.0, 400.0)
    assert m.seds[0].design_kva == 400.0

    m2 = _modelo()   # 50 kW sobre 100 kVA: no se toca
    assert redimensionar_sobrecargadas(m2) == []
    assert m2.seds[0].design_kva == 100.0


# ---------------------------------------------------------------------------
# Trafomix: medición MT registrada como SED «M…»
# ---------------------------------------------------------------------------

def test_trafomix_sin_carga_se_excluye_entero():
    from dataclasses import replace

    from igea_dgs.trafomix import excluir_trafomix

    m = _modelo()
    m.seds = [replace(m.seds[0], code='M41608', loc_name='M41608')]
    m.loads = [replace(m.loads[0], p_mw=0.0, q_mvar=0.0, sed_code='M41608')]
    inf = excluir_trafomix(m)
    assert (inf.excluidos, inf.cargas_nulas_quitadas) == (1, 1)
    assert m.seds == [] and m.loads == []
    assert len(m.lines) == 6, 'el tramo de red del trafomix se conserva'


def test_trafomix_con_carga_la_conserva_en_media_tension():
    from dataclasses import replace

    from igea_dgs.trafomix import excluir_trafomix

    m = _modelo()
    m.seds = [replace(m.seds[0], code='M50099')]
    inf = excluir_trafomix(m)
    assert m.seds == [] and len(m.loads) == 1
    assert inf.cargas_conservadas_mt


@pytest.mark.parametrize('codigo', ['SE41608', 'SA50425', 'MI-1157078'])
def test_solo_los_codigos_m_con_cifras_son_trafomix(codigo):
    from igea_dgs.trafomix import es_trafomix

    assert not es_trafomix(codigo)
    assert es_trafomix('M41608') and es_trafomix('m50174') and es_trafomix('M20730-2')
