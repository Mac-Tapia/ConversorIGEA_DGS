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
