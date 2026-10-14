"""Equipos del archivo original frente a los leídos en DIgSILENT (spec 015, T2)."""

from __future__ import annotations

import random

from igea_dgs.capacidades import Linea, Trafo, comparar_equipos, equipos_de_dgs
from igea_dgs.validate import parse_dgs

_CAB = {
    'TypTr2': 'FID(a:40);OP(a:1);loc_name(a:40);nt2ph(i);strn(r);frnom(r);utrn_h(r);utrn_l(r);'
              'uktr(r);pcutr(r);uk0tr(r);ur0tr(r);tr2cn_h(a:2);tr2cn_l(a:2);nt2ag(r)',
    'ElmTr2': 'FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);typ_id(p);ntnum(i);outserv(i)',
    'TypLne': 'FID(a:40);OP(a:1);loc_name(a:40);uline(r);sline(r);InomAir(r)',
    'ElmLne': 'FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);typ_id(p);dline(r);fline(r);'
              'GPScoords:MATRIX;nlnum(i);inAir(i)',
}


def _dgs(tmp_path, trafos, lineas, nombre='x.dgs'):
    """DGS mínimo: ``trafos`` = [(nombre, kva, kv_baja, grupo, unidades)], ``lineas`` =
    [(nombre, ka, ka_aire, unidades, en_aire)]."""
    filas = {k: [] for k in _CAB}
    for i, (n, kva, ul, (h, l, ag), u) in enumerate(trafos):
        filas['TypTr2'].append(f'T{i};C;TR_{n};3;{kva / 1000};60;10;{ul};4;0;4;0;{h};{l};{ag}')
        filas['ElmTr2'].append(f'E{i};C;{n};S{i};T{i};{u};0')
    for i, (n, ka, aire, u, en_aire) in enumerate(lineas):
        filas['TypLne'].append(f'L{i};C;C_{n};10;{ka};{aire}')
        filas['ElmLne'].append(f'N{i};C;{n};G;L{i};0.1;1;;{u};{en_aire}')
    texto = []
    for tabla, cab in _CAB.items():
        texto.append(f'$${tabla};{cab}')
        texto += [f'  {f}' for f in filas[tabla]]
    ruta = tmp_path / nombre
    ruta.write_text('\n'.join(texto) + '\n', encoding='utf-8')
    return parse_dgs(ruta)


def _leidos(trafos, lineas):
    return {
        'transformadores': {n: Trafo(kva / 1000, ul, g, u) for n, kva, ul, g, u in trafos},
        'lineas': {n: Linea(ka, u) for n, ka, _aire, u, _en in lineas},
    }


def test_capacidad_por_unidades_en_paralelo(tmp_path):
    """015:RF-7 — la capacidad es la del tipo por las unidades en paralelo."""
    eq = equipos_de_dgs(_dgs(tmp_path, [('TR_A', 250, 0.38, ('D', 'YN', 5), 2)],
                             [('SEC_1', 0.142, 0, 3, 1), ('SEC_2', 0.142, 0.2, 1, 1)]))
    assert eq['transformadores']['TR_A'].mva == 0.5
    assert eq['transformadores']['TR_A'].kv_baja == 0.38
    assert eq['transformadores']['TR_A'].grupo == ('D', 'YN', 5)
    assert abs(eq['lineas']['SEC_1'].ka - 0.426) < 1e-12
    # Al aire con InomAir definido manda InomAir; a 0, ``sline`` (CA101: InomAir=0).
    assert abs(eq['lineas']['SEC_2'].ka - 0.2) < 1e-12


def test_iguales_no_dan_nada(tmp_path):
    """015:RF-6 — un modelo igual al archivo original pasa sin avisos."""
    rnd = random.Random(15)
    trafos = [(f'TR_{i}', rnd.choice([50, 100, 250]), rnd.choice([0.22, 0.38]),
               ('D', 'YN', 5), 1) for i in range(rnd.randint(3, 12))]
    lineas = [(f'SEC_{i}', rnd.choice([0.142, 0.169]), 0, 1, 1) for i in range(rnd.randint(3, 12))]
    res = comparar_equipos(equipos_de_dgs(_dgs(tmp_path, trafos, lineas)), _leidos(trafos, lineas))
    assert res['sin_capacidad'] == []
    assert res['capacidad_distinta'] == []
    assert res['a_corregir'] == []


def test_sin_capacidad_bloquea(tmp_path):
    """015:RF-6 — un transformador o una línea sin capacidad en DIgSILENT es un fallo."""
    trafos = [('TR_A', 100, 0.22, ('D', 'YN', 5), 1)]
    lineas = [('SEC_1', 0.142, 0, 1, 1)]
    leidos = _leidos(trafos, lineas)
    leidos['transformadores']['TR_A'] = Trafo(None, 0.22, ('D', 'YN', 5), 1)
    leidos['lineas']['SEC_1'] = Linea(0.0, 1)
    res = comparar_equipos(equipos_de_dgs(_dgs(tmp_path, trafos, lineas)), leidos)
    assert {(x['clase'], x['nombre']) for x in res['sin_capacidad']} == {
        ('ElmTr2', 'TR_A'), ('ElmLne', 'SEC_1')}


def test_capacidad_distinta_solo_avisa(tmp_path):
    """015:RF-11 — una capacidad distinta se avisa con los dos valores; no se corrige."""
    trafos = [('TR_SE20701', 200, 0.22, ('D', 'YN', 5), 1)]
    leidos = _leidos([('TR_SE20701', 250, 0.22, ('D', 'YN', 5), 1)], [])
    res = comparar_equipos(equipos_de_dgs(_dgs(tmp_path, trafos, [])), leidos)
    assert res['capacidad_distinta'] == [{
        'clase': 'ElmTr2', 'nombre': 'TR_SE20701', 'magnitud': 'MVA',
        'digsilent': 0.25, 'archivo': 0.2}]
    assert res['a_corregir'] == [] and res['sin_capacidad'] == []


def test_tension_de_baja_distinta_se_corrige(tmp_path):
    """015:RF-33, 015:RF-34 — 380 V leído como 220 V: se corrige con el valor del archivo."""
    trafos = [('TR_A', 100, 0.38, ('D', 'YN', 5), 1)]
    leidos = _leidos([('TR_A', 100, 0.22, ('D', 'YN', 5), 1)], [])
    res = comparar_equipos(equipos_de_dgs(_dgs(tmp_path, trafos, [])), leidos)
    assert res['a_corregir'] == [{
        'nombre': 'TR_A', 'kv_baja': {'digsilent': 0.22, 'archivo': 0.38}}]


def test_grupo_distinto_o_ausente_se_corrige(tmp_path):
    """015:RF-32, 015:RF-34 — otro grupo de conexión, o ninguno, se corrige; no bloquea."""
    trafos = [('TR_A', 100, 0.22, ('D', 'YN', 5), 1), ('TR_B', 50, 0.38, ('D', 'YN', 5), 1)]
    leidos = _leidos([('TR_A', 100, 0.22, ('Y', 'YN', 0), 1),
                      ('TR_B', 50, 0.38, (None, None, None), 1)], [])
    res = comparar_equipos(equipos_de_dgs(_dgs(tmp_path, trafos, [])), leidos)
    assert [x['nombre'] for x in res['a_corregir']] == ['TR_A', 'TR_B']
    assert res['a_corregir'][0]['grupo'] == {'digsilent': ('Y', 'YN', 0), 'archivo': ('D', 'YN', 5)}
    assert res['sin_capacidad'] == []


def test_lo_que_no_esta_en_el_archivo_no_se_compara(tmp_path):
    """015:RF-7 — un equipo añadido por el operador no tiene con qué compararse."""
    res = comparar_equipos(equipos_de_dgs(_dgs(tmp_path, [], [])),
                           _leidos([('TR_NUEVO', 100, 0.22, ('D', 'YN', 5), 1)], []))
    assert res['no_en_archivo'] == [{'clase': 'ElmTr2', 'nombre': 'TR_NUEVO'}]
    assert res['a_corregir'] == [] and res['capacidad_distinta'] == []
