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


def test_el_seccionador_pasa_al_cubiculo_de_la_linea_vecina():
    """021:RF-1, RF-2, RF-3, RF-5 — el seccionador del puente va como StaSwitch en el
    extremo de L1 (aguas arriba; B también valdría con L2), y A y B quedan en una barra."""
    m = _modelo()
    informe = fundir_puentes(m)
    assert m.couplers == [] and informe.plegados == 1 and informe.interruptores == 0
    [d] = m.devices
    assert (d.section_id, d.terminal_side, d.node_id) == ('L1', 1, 'A')
    assert (d.kind, d.on_off, d.eq_number, d.eq_id) == ('sectionalizer', 1, 'SW1', 'SF01')
    assert 'B' not in m.nodes
    l2 = next(ln for ln in m.lines if ln.section_id == 'L2')
    assert (l2.from_node, l2.to_node) == ('A', 'C')


def _derivacion(con_carga_en_x1: bool = False) -> FeederModel:
    """La derivación de EQ_1080_320414/15/16 (NA205): un nudo J del que salen tres
    puentes con fusible, dos hacia líneas y uno hacia la barra T de un trafomix.

        S ─LA─ X1 ─P1(f1)─ J ─P2(f2)─ X2 ─LB─ F
                           └─P3(f3)─ T (SED M…)
    """
    nodos = {k: Node(k, float(i), 0.0) for i, k in enumerate(['S', 'X1', 'J', 'X2', 'F', 'T'])}
    lineas = [
        _linea('LA', 'S', 'X1'),
        _linea('P1', 'J', 'X1', 'DEFAULT', 2.0),
        _linea('P2', 'J', 'X2', 'DEFAULT', 2.0),
        _linea('LB', 'X2', 'F'),
        _linea('P3', 'J', 'T', 'DEFAULT', 2.0),
    ]
    fus = [SwitchingDevice('fuse', f'P{i}', 'S', 0, 'J', f'F{i}', f'f{i}', 'ABC', 1, 0, 0)
           for i in (1, 2, 3)]
    sed = Sed('M50226', 'M50226', 'T', 100.0, 'P3', 'D1', ('P3', 'D1'))
    cargas = []
    if con_carga_en_x1:
        cargas.append(Load('LA', 'DX', 'CX', '1', 'X1', 0.05, 0.01, 0.98, 100, 0, 'ABC'))
    m = FeederModel(name='F1', network_id='NET_F1', nominal_kv=22.9, source_node='S',
                    nodes=nodos, lines=lineas, loads=cargas, devices=fus,
                    line_types={'LINE:AA05003D': LineType('LINE:AA05003D', 'AA05003D', 'LINE',
                                                          0.6755, 0.6755, 0.47, 1.4, 3.1, 0, 195)},
                    seds=[sed])
    m.section_by_id = {ln.section_id: ln for ln in lineas}
    return m


def test_la_derivacion_con_fusibles_queda_en_un_solo_punto():
    """021:RF-6 — X1, J y X2 eran tres barras en menos de 1 m; quedan una, con f1 y f2 en
    los extremos de LA y LB. f3 no tiene línea a ningún lado: sigue como ElmCoup."""
    m = _derivacion()
    informe = fundir_puentes(m)
    assert informe.plegados == 2
    por = {d.eq_number: d for d in m.devices}
    assert (por['f1'].section_id, por['f1'].terminal_side) == ('LA', 1)
    assert (por['f2'].section_id, por['f2'].terminal_side) == ('LB', 0)
    la = m.section_by_id['LA']
    lb = m.section_by_id['LB']
    assert la.to_node == lb.from_node, 'el cable queda corrido por un solo punto'
    [c] = m.couplers
    assert c.eq_number == 'f3' and {c.node_a, c.node_b} == {la.to_node, 'T'}
    assert set(m.nodes) == {'S', la.to_node, 'F', 'T'}
    assert unsupplied_nodes(m, [m.source_node]) == set()


def test_cubiculo_ocupado_por_un_lado_pliega_por_el_otro():
    """021:RF-4 — L1 ya lleva un equipo en su extremo de A: el seccionador va a L2, por B."""
    m = _modelo()
    m.devices.append(SwitchingDevice('breaker', 'L1', 'L', 1, 'A', 'BR', 'BR1', 'ABC', 1, 0, 0))
    informe = fundir_puentes(m)
    assert informe.plegados == 1 and m.couplers == []
    sw = next(d for d in m.devices if d.eq_number == 'SW1')
    assert (sw.section_id, sw.terminal_side) == ('L2', 0)
    br = next(d for d in m.devices if d.eq_number == 'BR1')
    assert (br.section_id, br.terminal_side) == ('L1', 1), 'el equipo de la base no se mueve'


def test_cubiculos_ocupados_a_los_dos_lados_queda_elmcoup():
    """021:RF-4 — sin cubículo libre a ningún lado, el seccionador sigue como ElmCoup."""
    m = _modelo()
    m.devices += [
        SwitchingDevice('breaker', 'L1', 'L', 1, 'A', 'BR', 'BR1', 'ABC', 1, 0, 0),
        SwitchingDevice('breaker', 'L2', 'S', 0, 'B', 'BR', 'BR2', 'ABC', 1, 0, 0),
    ]
    informe = fundir_puentes(m)
    assert informe.plegados == 0 and informe.interruptores == 1
    [c] = m.couplers
    assert (c.node_a, c.node_b, c.eq_number) == ('A', 'B', 'SW1')
    assert {d.eq_number for d in m.devices} == {'BR1', 'BR2'}


def test_el_puente_de_la_fuente_pliega_sin_fundir_la_fuente():
    """021:RF-1, RF-2 — un interruptor de cabecera en un puente S─A pasa a L1 en la barra
    de la fuente; la fuente conserva su nombre y A desaparece."""
    nodos = {k: Node(k, float(i), 0.0) for i, k in enumerate('SAB')}
    lineas = [_linea('P0', 'S', 'A', 'DEFAULT', 2.0), _linea('L1', 'A', 'B')]
    cab = SwitchingDevice('breaker', 'P0', 'S', 0, 'S', 'BR', 'CAB', 'ABC', 1, 0, 0)
    m = FeederModel(name='F1', network_id='NET_F1', nominal_kv=10.0, source_node='S',
                    nodes=nodos, lines=lineas, loads=[], devices=[cab],
                    line_types={'LINE:AA05003D': LineType('LINE:AA05003D', 'AA05003D', 'LINE',
                                                          0.6755, 0.6755, 0.47, 1.4, 3.1, 0, 195)})
    m.section_by_id = {ln.section_id: ln for ln in lineas}
    fundir_puentes(m)
    assert m.source_node == 'S' and set(m.nodes) == {'S', 'B'}
    [d] = m.devices
    assert (d.eq_number, d.section_id, d.terminal_side, d.node_id) == ('CAB', 'L1', 0, 'S')
    assert (m.section_by_id['L1'].from_node, m.section_by_id['L1'].to_node) == ('S', 'B')


def test_plegar_no_depende_del_orden_de_los_tramos():
    """021:RF-6 — misma red con los tramos y equipos en otro orden: mismo resultado."""
    a, b = _derivacion(), _derivacion()
    b.lines = list(reversed(b.lines))
    b.devices = list(reversed(b.devices))
    fundir_puentes(a)
    fundir_puentes(b)
    clave = lambda m: (sorted((d.eq_number, d.section_id, d.terminal_side, d.node_id)  # noqa: E731
                              for d in m.devices),
                       sorted((c.eq_number, c.node_a, c.node_b) for c in m.couplers),
                       sorted(m.nodes))
    assert clave(a) == clave(b)


def test_una_barra_con_carga_no_pliega_el_fusible():
    """021:RF-1 — si X1 lleva una carga, plegar f1 en LA la pondría detrás del fusible:
    abrirlo la desconectaría. X1 no es «una barra a la que solo llega otra línea»."""
    m = _derivacion(con_carga_en_x1=True)
    fundir_puentes(m)
    assert 'f1' in {c.eq_number for c in m.couplers}
    assert 'f2' in {d.eq_number for d in m.devices}


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
    # 021:RF-10 — plegados en su línea, siguen en la red unida como StaSwitch.
    assert sorted(d.eq_number for d in unido.devices) == ['xSW1', 'ySW1']
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
    # 021:RF-3 — el seccionador plegado sale en el cubículo de L1 con su nombre y estado.
    [sw] = [r for r in tablas['StaSwitch']['rows_dict'] if r['loc_name'] == 'SW1']
    assert int(float(sw['on_off'])) == 1


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
# Trafomix: medición MT registrada como SED «M…» (patrón del perfil de Electro Dunas)
# ---------------------------------------------------------------------------

def _patron_ed() -> str:
    from igea_dgs.perfil_empresa import perfil_con_nombre

    return perfil_con_nombre('electro_dunas').patron_sed_medicion


def test_trafomix_sin_carga_se_excluye_entero():
    from dataclasses import replace

    from igea_dgs.trafomix import excluir_trafomix

    m = _modelo()
    m.seds = [replace(m.seds[0], code='M41608', loc_name='M41608')]
    m.loads = [replace(m.loads[0], p_mw=0.0, q_mvar=0.0, sed_code='M41608')]
    inf = excluir_trafomix(m, _patron_ed())
    assert (inf.excluidos, inf.cargas_nulas_quitadas) == (1, 1)
    assert m.seds == [] and m.loads == []
    assert len(m.lines) == 6, 'el tramo de red del trafomix se conserva'


def test_trafomix_con_carga_la_conserva_en_media_tension():
    from dataclasses import replace

    from igea_dgs.trafomix import excluir_trafomix

    m = _modelo()
    m.seds = [replace(m.seds[0], code='M50099')]
    inf = excluir_trafomix(m, _patron_ed())
    assert m.seds == [] and len(m.loads) == 1
    assert inf.cargas_conservadas_mt


def test_el_fusible_del_trafomix_excluido_se_quita_con_su_barra():
    """021:RF-7, RF-8 — f3 llevaba a la barra del trafomix M50226; excluido, la barra se
    queda sin nada y no se escriben ni ella ni f3. El informe lo nombra."""
    from igea_dgs.trafomix import excluir_trafomix

    m = _derivacion()
    fundir_puentes(m)
    inf = excluir_trafomix(m, _patron_ed())
    assert inf.excluidos == 1 and inf.maniobras_quitadas == ['f3']
    assert m.couplers == [] and 'T' not in m.nodes
    assert 'f3' in inf.texto()
    assert unsupplied_nodes(m, [m.source_node]) == set()


def test_el_fusible_del_trafomix_con_carga_se_conserva():
    """021:RF-7 — si el trafomix traía carga, queda como carga de MT en su barra: el
    fusible sigue llevando a algo y se conserva."""
    from igea_dgs.trafomix import excluir_trafomix

    m = _derivacion()
    m.loads.append(Load('P3', 'D1', 'CM', '1', 'T', 0.2, 0.05, 0.97, 100, 0, 'ABC',
                        sed_code='M50226'))
    fundir_puentes(m)
    inf = excluir_trafomix(m, _patron_ed())
    assert inf.maniobras_quitadas == [] and inf.cargas_conservadas_mt
    assert [c.eq_number for c in m.couplers] == ['f3'] and 'T' in m.nodes


def test_las_reglas_pliegan_y_quitan_en_toda_conversion():
    """021:RF-10 — plegado y quitado del trafomix van dentro de ``aplicar_reglas``."""
    from igea_dgs.reglas import Reglas, aplicar_reglas

    m = _derivacion()
    inf = aplicar_reglas(m, Reglas(patron_sed_medicion=_patron_ed(), hoja=None))
    assert inf['puentes']['plegados'] == 2
    assert inf['trafomix']['maniobras_quitadas'] == 1
    assert m.couplers == []


def test_sin_reglas_los_puentes_quedan_como_estaban():
    """021:RF-11 — ``SIN_REGLAS`` no funde ni pliega: los fusibles siguen en sus puentes."""
    from igea_dgs.reglas import SIN_REGLAS, aplicar_reglas

    m = _derivacion()
    aplicar_reglas(m, SIN_REGLAS)
    assert m.couplers == [] and len(m.lines) == 5
    assert sorted(d.section_id for d in m.devices) == ['P1', 'P2', 'P3']


def _auditar(m, informe, *, statswitch, elmcoup_red):
    from types import SimpleNamespace

    from igea_dgs.reglas import auditar_completitud

    ds = SimpleNamespace(feeders={'N': {'LA', 'LB', 'P1', 'P2', 'P3'}},
                         customer_loads_by_feeder={}, load_placements={},
                         switching_by_feeder={'N': ['f1', 'f2', 'f3']})
    filas = lambda n: {'rows_dict': [{} for _ in range(n)]}  # noqa: E731
    tablas = {'ElmLne': filas(len(m.lines)), 'StaSwitch': filas(statswitch),
              'ElmSubstat': filas(len(m.seds)), 'ElmCoup': filas(len(m.seds) + elmcoup_red)}
    return auditar_completitud(ds, ['N'], m, tablas, [informe])


def test_la_completitud_cuenta_los_quitados_y_los_elmcoup_escritos():
    """021:RF-9 — maniobras de entrada = StaSwitch + ElmCoup de red del DGS + quitados por
    el trafomix. Un ElmCoup que no llega al DGS es una pérdida y se dice."""
    from igea_dgs.reglas import Reglas, aplicar_reglas

    m = _derivacion()
    inf = aplicar_reglas(m, Reglas(patron_sed_medicion=_patron_ed(), hoja=None))
    bien = _auditar(m, inf, statswitch=2, elmcoup_red=0)
    assert bien['fallos'] == [], bien
    mal = _auditar(m, inf, statswitch=1, elmcoup_red=0)
    assert any('maniobras' in f for f in mal['fallos'])


def test_el_seccionador_plegado_sigue_siendo_punto_de_maniobra(tmp_path):
    """021:RF-15 — plegado en el cubículo de L1, el seccionador del export sale como
    StaSwitch con uso ``dct``, y la transferencia lo cuenta como seccionador."""
    from dataclasses import replace

    pytest.importorskip('pyproj')
    from apoyo import cargar_herramienta
    from igea_dgs.dgs import write_dgs
    from igea_dgs.validate import parse_dgs

    m = _modelo()
    m.devices = [replace(m.devices[0], kind='SWITCH')]
    fundir_puentes(m)
    out = tmp_path / 'F1.dgs'
    write_dgs(m, out)
    tablas = parse_dgs(out)
    [sw] = [r for r in tablas['StaSwitch']['rows_dict'] if r['loc_name'] == 'SW1']
    assert sw['aUsage'] == 'dct'
    cubiculo = next(r for r in tablas['StaCubic']['rows_dict'] if r['FID'] == sw['fold_id'])
    linea = next(r for r in tablas['ElmLne']['rows_dict'] if r['FID'] == cubiculo['obj_id'])
    assert linea['loc_name'] == 'L1'
    guion = cargar_herramienta('transferencia_pf.py', 'transferencia_021', tools_en_path=True)

    class Sw:
        loc_name, aUsage = 'SW1', 'dct'
    assert guion.es_seccionador(Sw(), set())


def test_el_oraculo_abre_el_seccionador_plegado_en_su_linea():
    """021:RF-16 — el oráculo pone el seccionador plegado en el extremo de L1: abierto,
    deja sin tensión lo que hay detrás, como el ElmCoup de antes."""
    from dataclasses import replace

    pp = pytest.importorskip('pandapower')
    from igea_dgs.oraculo import red_pandapower

    m = _modelo()
    m.devices = [replace(m.devices[0], on_off=0)]
    fundir_puentes(m)
    net, _barra, _inf = red_pandapower(m)
    fila = net.switch[net.switch.name == 'SW1']
    assert list(fila.et) == ['l'] and not bool(fila.closed.iloc[0])
    pp.runpp(net)
    assert net.res_bus.vm_pu.isna().sum() > 0, 'lo que cuelga detrás queda sin tensión'


def test_el_trecho_del_conductor_sigue_corrido_sin_acoples():
    """021:RF-16 — con el seccionador en el cubículo ya no hay acople entre tramos: dos
    tramos que comparten barra son un solo trecho para el informe de estudio (017)."""
    from igea_dgs.informes import trechos_de_conductor

    tramos = [['L1', [[-14.0, -75.7], [-14.001, -75.7]], 50.0, 'CAB', 'N1', 'AA35', 0.1],
              ['L2', [[-14.001, -75.7], [-14.002, -75.7]], 50.0, 'N1', 'N2', 'AA35', 0.1]]
    geo = {'cabecera': 'CAB', 'tramos': tramos, 'acoples': [],
           'barras': [['CAB', -14.0, -75.7, 1, 10], ['N2', -14.002, -75.7, 1, 10]]}
    trechos = trechos_de_conductor(geo, ['L1', 'L2'], geo)
    assert [(t.desde, t.hasta, t.tramos) for t in trechos] == [('CAB', 'N2', ('L1', 'L2'))]


@pytest.mark.parametrize('codigo', ['SE41608', 'SA50425', 'MI-1157078'])
def test_solo_los_codigos_m_con_cifras_son_trafomix(codigo):
    from igea_dgs.trafomix import es_trafomix

    patron = _patron_ed()
    assert not es_trafomix(codigo, patron)
    assert es_trafomix('M41608', patron) and es_trafomix('m50174', patron)
    assert es_trafomix('M20730-2', patron)
