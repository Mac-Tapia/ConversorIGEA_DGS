"""Spec 022, T4: puntos de enlace y caminos cerrados de la red unida."""
from __future__ import annotations

from igea_dgs import enlaces as en
from igea_dgs.combine import combine_models, estructurar
from igea_dgs.estructura import estructura_de_dict
from igea_dgs.model import Line, SwitchingDevice
from test_combine import _alimentador, _tipo

E = estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [
    {'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': ['A', 'B']},
    {'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': ['C']}]}]})


def _red(*extra_lineas, maniobra=None, enlace=False):
    a = _alimentador('A', 10.0, ['A_H', 'A_1', 'A_2', 'A_3'] + (['COMUN'] if enlace else []))
    b = _alimentador('B', 10.0, ['B_H', 'B_1', 'B_2'] + (['COMUN'] if enlace else []))
    c = _alimentador('C', 10.0, ['C_H', 'C_1', 'C_2'])
    red, _ = combine_models([a, b, c])
    estructurar(red, E)
    t = _tipo()
    for i, (x, y) in enumerate(extra_lineas):
        red.lines.append(Line(f'EXTRA{i}', x, y, 'ABC', t.key, t.code, 50.0, True))
    if maniobra:
        red.devices.append(SwitchingDevice('seccionador', maniobra, '', 0, '', 'SW1', 'SW1',
                                           'ABC', 1, 0, 0))
    return red


def _radial(red) -> bool:
    aristas = en._aristas(red)
    dist, _p, _r, arbol = en._arbol(aristas, sorted(en.fuentes_de(red)))
    cerradas = [i for i, x in enumerate(aristas) if not x[5] and x[2] != x[3]]
    return all(i in arbol for i in cerradas) and set(red.nodes) <= set(dist)


def test_un_anillo_dentro_de_un_alimentador_se_abre():
    """022:RF-29, 022:RF-30, 022:RF-31, 022:RF-34 — un anillo de A se abre en el tramo más
    lejano de su SET, con un punto abierto; la red queda radial y todo sigue alimentado."""
    red = _red(('A_3', 'A_1'))
    [ap] = en.abrir_caminos_cerrados(red)
    assert ap.motivo == 'anillo' and ap.alimentadores == ('A',) and ap.clase == 'tramo'
    # A_1 a 100 m, A_3 a 150 m (por el tramo añadido) y A_2 a 200 m: el más lejano es A_SEC2.
    assert ap.elemento == 'A_SEC2'
    punto = next(d for d in red.devices if d.section_id == 'A_SEC2')
    assert punto.on_off == 0 and punto.kind == 'punto_abierto'
    assert _radial(red) and '022:RF-30' in ap.texto()


def test_un_camino_entre_dos_set_y_entre_dos_alimentadores():
    """022:RF-30 — un tramo cerrado entre A (SET 1) y C (SET 2) es un camino entre SET; uno
    entre A y B, de la misma SET, entre alimentadores. Los dos se abren."""
    red = _red(('A_3', 'C_2'), ('A_2', 'B_2'))
    aps = en.abrir_caminos_cerrados(red)
    motivos = sorted(a.motivo for a in aps)
    assert motivos == ['entre_alimentadores', 'entre_set']
    entre_set = next(a for a in aps if a.motivo == 'entre_set')
    assert entre_set.sets == ('SET 1', 'SET 2')
    assert _radial(red)


def test_se_abre_la_maniobra_antes_que_un_tramo():
    """022:RF-31 — si el camino tiene una maniobra cerrada, se abre ella y no un tramo; nunca
    el interruptor de cabecera."""
    red = _red(('A_3', 'A_1'), maniobra='A_SEC1')
    [ap] = en.abrir_caminos_cerrados(red)
    assert ap.clase == 'maniobra' and ap.elemento == 'A_SEC1'
    assert next(d for d in red.devices if d.section_id == 'A_SEC1').on_off == 0
    assert all(c.on_off == 1 for c in red.couplers if c.name.startswith('CAB_'))


def test_los_puntos_de_enlace_con_sus_set():
    """022:RF-26, 022:RF-27 — el nodo que comparten A y B es un enlace abierto, con sus dos
    alimentadores y sus dos SET; la red ya es radial y no se abre nada más."""
    red = _red(enlace=True)
    [e] = en.enlaces(red)
    assert e['alimentadores'] == ('A', 'B') and e['sets'] == ('SET 1', 'SET 1')
    assert en.abrir_caminos_cerrados(red) == []


def test_determinista():
    """022:RF-31 — la misma red abre lo mismo."""
    uno = en.abrir_caminos_cerrados(_red(('A_3', 'C_2'), ('A_3', 'A_1')))
    dos = en.abrir_caminos_cerrados(_red(('A_3', 'C_2'), ('A_3', 'A_1')))
    assert uno == dos


def _donante_y_receptor(y_receptor=50.0):
    """D: cabecera y cuatro SED de 100 kVA en línea; R: dos nodos, el último a ``y`` del
    final de D (TM106 y TM104 en Chincha, 2026-10-18)."""
    from dataclasses import replace

    from igea_dgs.model import Load, Node, Sed

    d = _alimentador('D', 10.0, ['D_H', 'D_1', 'D_2', 'D_3', 'D_4'])
    for i, n in enumerate(['D_1', 'D_2', 'D_3', 'D_4'], start=1):
        d.loads.append(Load(f'D_SECL{i}', f'X{i}', 'C', '1', n, 0.05, 0.01, 0.95, 100.0, 0.0,
                            'ABC', sed_code=f'SE_D{i}', display_name=f'SE_D{i}', feeder='D',
                            network_id='NET_D'))
        d.seds.append(Sed(f'SE_D{i}', f'SE_D{i}', n, 100.0, f'D_SECL{i}', f'X{i}',
                          (f'D_SECL{i}', f'X{i}'), feeder='D', network_id='NET_D'))
    r = _alimentador('R', 10.0, ['R_H', 'R_1'])
    r.nodes['R_H'] = Node('R_H', 0.0, 2000.0)
    r.nodes['R_1'] = Node('R_1', 400.0, y_receptor)
    e = estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': ['D', 'R']}]}]})
    red, _ = combine_models([d, r])
    estructurar(red, e)
    return red, replace


def test_reconstruye_por_medida_y_pasa_la_parte_que_toca():
    """022:RF-57 / 022:RF-58 — el tramo que falta entre R y la red de D, y abierto el punto
    que deja aguas abajo la parte del kVA de D en la proporción de las medidas (300 y 100
    kW de 400 kVA: 300 kVA, tres SED); la red sigue radial y las cargas pasan a R."""
    red, _ = _donante_y_receptor()
    hechas, avisos = en.reconstruir_por_medida(red, {'R': 300.0}, {'D': 100.0})
    assert not avisos and len(hechas) == 1
    h = hechas[0]
    assert (h.alimentador, h.donante, h.nodo, h.nodo_donante) == ('R', 'D', 'R_1', 'D_4')
    assert h.distancia_m == 50.0 and h.cargas_pasadas == 3 and h.kva_pasado == 300.0
    assert any(ln.section_id == h.tramo and {ln.from_node, ln.to_node} == {'R_1', 'D_4'}
               for ln in red.lines)
    assert sorted(ld.node_id for ld in red.loads if ld.feeder == 'R') == ['D_2', 'D_3', 'D_4']
    assert en.abrir_caminos_cerrados(red) == [], 'ya es radial'
    assert _radial(red)
    assert 'RF-58' in h.texto() and 'abierto D_SEC1' in h.texto()


def test_sin_medida_queda_activado_y_abierto():
    """022:RF-59 — con medida cero (barra menos los demás), el tramo nuevo queda abierto y
    no se pasa carga: el alimentador queda activado."""
    red, _ = _donante_y_receptor()
    hechas, _ = en.reconstruir_por_medida(red, {'R': -66.0}, {'D': 100.0})
    h = hechas[0]
    assert h.cargas_pasadas == 0 and h.abierto == h.tramo
    assert all(ld.feeder == 'D' for ld in red.loads)
    assert any(getattr(d, 'section_id', '') == h.tramo and int(d.on_off) == 0 for d in red.devices)
    assert _radial(red)


def test_sin_red_cerca_se_dice_y_queda_como_esta():
    """022:RF-60 — sin nodo de otro alimentador a menos de 100 m, se avisa y no se toca."""
    red, _ = _donante_y_receptor(y_receptor=500.0)
    lineas = len(red.lines)
    hechas, avisos = en.reconstruir_por_medida(red, {'R': 300.0}, {'D': 100.0})
    assert not hechas and len(red.lines) == lineas
    assert avisos and '022:RF-60' in avisos[0]


def test_el_donante_con_medida_no_se_queda_sin_red():
    """022:RF-58b — con casi toda la medida en el reconstruido (3 133 frente a 31 kW, TM106 y
    TM104 en Chincha), el donante que mide algo conserva parte de su red: no se le pasa
    toda; solo sin medida se abre su cabecera entera."""
    red, _ = _donante_y_receptor()
    hechas, _ = en.reconstruir_por_medida(red, {'R': 3133.0}, {'D': 31.0})
    h = hechas[0]
    assert h.cargas_pasadas == 3 and h.kva_pasado == 300.0
    assert [ld.node_id for ld in red.loads if ld.feeder == 'D'] == ['D_1']
    assert _radial(red)
    red, _ = _donante_y_receptor()
    hechas, _ = en.reconstruir_por_medida(red, {'R': 3133.0}, {'D': 0.0})
    assert hechas[0].abierto.startswith('CAB_') and hechas[0].cargas_pasadas == 4


def test_la_cabecera_del_donante_se_parte_y_conserva_sus_ramas():
    """022:RF-58b — la unión cuelga de una rama de la cabecera del donante (como TM104): el
    donante conserva con su interruptor la rama más cercana a su parte y el reconstruido
    recibe las demás por la cabecera de siempre; la red sigue radial."""
    from igea_dgs.model import Line, Load, Node, Sed

    red, _ = _donante_y_receptor()
    t = _tipo()
    # Dos ramas más en la cabecera D_H: P (50 kVA) y Q (300 kVA).
    for rama, kva, x in (('P', 50.0, -100.0), ('Q', 300.0, -200.0)):
        nodo = f'D_{rama}'
        red.nodes[nodo] = Node(nodo, x, -100.0)
        red.combined.feeder_of_node[nodo] = ['D']
        red.combined.node_kv[nodo] = 10.0
        red.lines.append(Line(f'D_SEC_{rama}', 'D_H', nodo, 'ABC', t.key, t.code, 100.0, True))
        red.loads.append(Load(f'D_SECL_{rama}', f'X{rama}', 'C', '1', nodo, 0.05, 0.01, 0.95,
                              kva, 0.0, 'ABC', sed_code=f'SE_{rama}', feeder='D',
                              network_id='NET_D'))
        red.seds.append(Sed(f'SE_{rama}', f'SE_{rama}', nodo, kva, f'D_SECL_{rama}', f'X{rama}',
                            (f'D_SECL_{rama}', f'X{rama}'), feeder='D', network_id='NET_D'))
    # 750 kVA en total; la medida 3 133 frente a 31 kW deja al donante ~7 kVA: la rama P.
    hechas, _ = en.reconstruir_por_medida(red, {'R': 3133.0}, {'D': 31.0})
    h = hechas[0]
    assert h.abierto == 'cabecera de D partida'
    assert sorted(ld.node_id for ld in red.loads if ld.feeder == 'D') == ['D_P']
    cab = next(c for c in red.combined.cabeceras if c.feeder == 'D')
    assert cab.node_cabecera != 'D_H' and red.nodes[cab.node_cabecera].x == red.nodes['D_H'].x
    assert any(ln.section_id == 'D_SEC_P' and cab.node_cabecera in (ln.from_node, ln.to_node)
               for ln in red.lines)
    assert en.abrir_caminos_cerrados(red) == []
    assert _radial(red)


def test_el_donante_conserva_una_rama_junto_a_su_cabecera():
    """022:RF-58b — la cabecera tiene la rama de la unión y una rama grande; junto a ella
    (a menos de 100 m) sale una sub-rama: el donante conserva la sub-rama que le basta para
    su medida y el reconstruido recibe el resto, también la rama grande (TM104 conserva la
    de 1 015 kVA a 44 m y TM106 recibe 8 400 kVA)."""
    from igea_dgs.model import Line, Load, Node, Sed

    red, _ = _donante_y_receptor()
    t = _tipo()
    # D_H → D_G (a 40 m) → D_G1 (600 kVA) y D_G2 (60 kVA).
    nuevos = (('D_G', -40.0, None, 'D_H'), ('D_G1', -300.0, 600.0, 'D_G'),
              ('D_G2', -300.0, 60.0, 'D_G'))
    for nodo, x, kva, padre in nuevos:
        red.nodes[nodo] = Node(nodo, x, -10.0)
        red.combined.feeder_of_node[nodo] = ['D']
        red.combined.node_kv[nodo] = 10.0
        largo = 40.0 if padre == 'D_H' else 300.0
        red.lines.append(Line(f'L_{nodo}', padre, nodo, 'ABC', t.key, t.code, largo, True))
        if kva:
            red.loads.append(Load(f'S_{nodo}', f'X{nodo}', 'C', '1', nodo, 0.05, 0.01, 0.95,
                                  kva, 0.0, 'ABC', sed_code=f'SE_{nodo}', feeder='D',
                                  network_id='NET_D'))
            red.seds.append(Sed(f'SE_{nodo}', f'SE_{nodo}', nodo, kva, f'S_{nodo}', f'X{nodo}',
                                (f'S_{nodo}', f'X{nodo}'), feeder='D', network_id='NET_D'))
    # D: 400 (cadena con la unión) + 660 = 1 060 kVA; R mide 900 y D 50.
    hechas, _ = en.reconstruir_por_medida(red, {'R': 900.0}, {'D': 50.0})
    assert hechas[0].abierto == 'cabecera de D partida'
    assert sorted(ld.node_id for ld in red.loads if ld.feeder == 'D') == ['D_G2']
    assert any(ln.section_id == 'L_D_G2' and ln.from_node.endswith('_D') for ln in red.lines)
    assert en.abrir_caminos_cerrados(red) == []
    assert _radial(red)
