"""Spec 022, T6: el DGS de la red unida por zonal y SET."""
from __future__ import annotations

from igea_dgs.combine import combine_models, estructurar
from igea_dgs.dgs import write_dgs
from igea_dgs.enlaces import abrir_caminos_cerrados
from igea_dgs.estructura import estructura_de_dict
from igea_dgs.validate import parse_dgs
from test_combine import _alimentador

E = estructura_de_dict({'zonales': [
    {'nombre': 'Norte', 'sets': [{'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': ['A', 'B']}]},
    {'nombre': 'Sur', 'sets': [{'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': ['C']}]}]})


def _red():
    modelos = [_alimentador('A', 10.0, ['A_H', 'A_1'], con_carga='A_1'),
               _alimentador('B', 22.9, ['B_H', 'B_1'], con_carga='B_1'),
               _alimentador('C', 10.0, ['C_H', 'C_1'], con_carga='C_1'),
               _alimentador('X', 10.0, ['X_H', 'X_1'], con_carga='X_1')]
    red, _ = combine_models(modelos)
    estructurar(red, E)
    abrir_caminos_cerrados(red)
    return red


def _tablas(tmp_path, red, nombre='r.dgs'):
    out = tmp_path / nombre
    write_dgs(red, out)
    t = parse_dgs(out)
    return out, {k: v['rows_dict'] for k, v in t.items()}


def test_una_red_por_zonal_y_la_set_con_sus_barras(tmp_path):
    """022:RF-7, 022:RF-8, 022:RF-9, 022:RF-10, 022:RF-19 — un DGS con una red por zonal y
    otra «Sin SET»; cada SET una subestación con sus barras de media dentro; cada elemento
    en la red de su zonal."""
    _out, t = _tablas(tmp_path, _red())
    redes = {r['loc_name']: r['FID'] for r in t['ElmNet']}
    assert set(redes) == {'Norte', 'Sur', 'Sin SET'}
    sets = {r['loc_name']: r for r in t['ElmSubstat'] if r['loc_name'].startswith('SET')}
    assert set(sets) == {'SET 1 Uno', 'SET 2 Dos'}
    assert sets['SET 1 Uno']['fold_id'] == redes['Norte'] and sets['SET 2 Dos']['fold_id'] == redes['Sur']
    terms = {r['loc_name']: r for r in t['ElmTerm']}
    barras = {n: r for n, r in terms.items() if n.startswith('B_SET')}
    assert {r['fold_id'] for n, r in barras.items() if 'SET1' in n} == {sets['SET 1 Uno']['FID']}
    assert len(barras) == 3, 'SET 1 a 10 y 22,9 kV; SET 2 a 10 kV'
    assert terms['C_H']['fold_id'] == redes['Sur'] and terms['A_H']['fold_id'] == redes['Norte']
    assert terms['X_H']['fold_id'] == redes['Sin SET']


def test_una_fuente_por_barra_y_el_feeder_en_su_cabecera(tmp_path):
    """022:RF-11, 022:RF-12, 022:RF-13, 022:RF-14 — una red externa por barra de SET y otra
    para el «Sin SET»; cada alimentador con su interruptor de cabecera cerrado, y su
    ElmFeeder en el cubículo de ese interruptor del lado de la barra."""
    _out, t = _tablas(tmp_path, _red())
    xnets = sorted(r['loc_name'] for r in t['ElmXnet'])
    assert len(xnets) == 4 and 'External Grid X' in xnets
    assert all(any(s in x for s in ('SET 1', 'SET 2', ' X')) for x in xnets)
    cab = {r['loc_name']: r for r in t['ElmCoup'] if r['loc_name'].startswith('CAB_')}
    assert set(cab) == {'CAB_A', 'CAB_B', 'CAB_C'} and {r['on_off'] for r in cab.values()} == {'1'}
    cubs = {r['FID']: r for r in t['StaCubic']}
    terms = {r['FID']: r['loc_name'] for r in t['ElmTerm']}
    feeders = {r['loc_name']: r for r in t['ElmFeeder']}
    assert set(feeders) == {'A', 'B', 'C', 'X'}
    for f in ('A', 'B', 'C'):
        cub = cubs[feeders[f]['obj_id']]
        assert cub['obj_id'] == cab[f'CAB_{f}']['FID'] and terms[cub['fold_id']].startswith('B_SET')


def test_sin_estructura_como_antes_y_determinista(tmp_path):
    """022:RF-6 — sin estructura, una sola red y una fuente por alimentador; con ella, el DGS
    es el mismo byte a byte en dos escrituras."""
    red, _ = combine_models([_alimentador('A', 10.0, ['A_H', 'A_1']),
                             _alimentador('C', 10.0, ['C_H', 'C_1'])])
    _out, t = _tablas(tmp_path, red, 's.dgs')
    assert len(t['ElmNet']) == 1 and len(t['ElmXnet']) == 2
    a, _ = _tablas(tmp_path, _red(), 'a.dgs')
    b, _ = _tablas(tmp_path, _red(), 'b.dgs')
    assert a.read_bytes() == b.read_bytes()
