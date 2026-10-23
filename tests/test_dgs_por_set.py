"""Spec 022, T6: el DGS de la red unida por zonal y SET."""
from __future__ import annotations

import os
import random
from dataclasses import replace

from igea_dgs.combine import combine_models, estructurar
from igea_dgs.dgs import write_dgs
from igea_dgs.enlaces import abrir_caminos_cerrados
from igea_dgs.estructura import estructura_de_dict
from igea_dgs.validate import parse_dgs
from test_combine import _alimentador

E = estructura_de_dict({'zonales': [
    {'nombre': 'Norte', 'sets': [{'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': [
        {'codigo': 'A', 'sistema': 'SE01'}, {'codigo': 'B', 'sistema': 'SE02'}]}]},
    {'nombre': 'Sur', 'sets': [{'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': [
        {'codigo': 'C', 'sistema': 'SE01'}]}]}],
    'sistemas': {'SE01': {'nombre': 'Urbano', 'sector': '2', 'norma': 'NTCSE'},
                 'SE02': {'nombre': 'Rural', 'sector': '3', 'norma': 'NTCSER'}}})


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


def test_una_zona_por_sistema_electrico(tmp_path):
    """022:RF-15, 022:RF-16 — una zona por sistema eléctrico con su sector típico y su norma;
    cada barra de un alimentador en la zona de su sistema; las barras de SET, sin zona."""
    _out, t = _tablas(tmp_path, _red())
    zonas = {r['loc_name']: r for r in t['ElmZone']}
    assert set(zonas) == {'SE01 Urbano', 'SE02 Rural'}
    assert 'NTCSER' in zonas['SE02 Rural']['desc'] and 'sector típico 3' in zonas['SE02 Rural']['desc']
    terms = {r['loc_name']: r for r in t['ElmTerm']}
    assert terms['A_H']['cpZone'] == terms['C_H']['cpZone'] == zonas['SE01 Urbano']['FID']
    assert terms['B_H']['cpZone'] == zonas['SE02 Rural']['FID']
    assert all(r['cpZone'] == '' for n, r in terms.items() if n.startswith('B_SET') or n.startswith('X'))


def test_la_carga_sin_sed_en_la_red_de_su_zonal(tmp_path):
    """022:RF-8 — una carga sin SED va en la red del zonal de su nodo, no en la primera (en
    la entrega completa, CUST_2010_330303_SEPALMAR de Nasca quedaba en Chincha)."""
    from igea_dgs.model import Load

    red = _red()
    red.loads.append(Load('C_LIBRE', 'D9', 'C9', '1', 'C_H', 0.01, 0.002, 0.98, 10.0, 0.0, 'ABC'))
    _out, t = _tablas(tmp_path, red)
    redes = {r['loc_name']: r['FID'] for r in t['ElmNet']}
    libre = next(r for r in t['ElmLod'] if r['loc_name'] == 'C9')
    assert libre['fold_id'] == redes['Sur']


def test_los_nombres_con_tilde_llegan_a_digsilent(tmp_path):
    """022:RF-9, 022:RF-15 — el DGS va en la página de códigos de DIgSILENT (cp1252): «SET 46
    Señor de Luren» y «Huaytará» no llegan como «SeÃ±or»; con nombres ASCII, el mismo
    fichero de siempre."""
    from igea_dgs.estructura import estructura_de_dict

    e = estructura_de_dict({'zonales': [{'nombre': 'Ica', 'sets': [
        {'codigo': 'SET 46', 'nombre': 'Señor de Luren', 'alimentadores': [{'codigo': 'A', 'sistema': 'SE0051'}]}]}],
        'sistemas': {'SE0051': {'nombre': 'Huaytará - Chocorvos', 'sector': '4', 'norma': 'NTCSER'}}})
    red, _ = combine_models([_alimentador('A', 10.0, ['A_H', 'A_1'], con_carga='A_1')])
    estructurar(red, e)
    out, t = _tablas(tmp_path, red)
    assert 'SET 46 Señor de Luren' in {r['loc_name'] for r in t['ElmSubstat']}
    assert 'SE0051 Huaytará - Chocorvos' in {r['loc_name'] for r in t['ElmZone']}
    assert 'Señor'.encode('cp1252') in out.read_bytes()


# --------------------------------------------------------------- 022:RF-64 a RF-70
SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _dividida(rng):
    """Un zonal «Norte» dividido por SET, con un número sorteado de SET y alimentadores,
    y otro «Sur» sin dividir con dos SET. Devuelve la estructura y los alimentadores por SET."""
    por_set = {f'SET {i}': [f'N{i}{j}' for j in range(rng.randint(1, 3))]
               for i in range(1, rng.randint(2, 5) + 1)}
    por_set.update({'SET 8': ['S1'], 'SET 9': ['S2']})
    e = estructura_de_dict({'zonales': [
        {'nombre': 'Norte', 'dividir_por_set': True, 'sets': [
            {'codigo': s, 'nombre': f'Nombre{s[-1]}', 'alimentadores': [{'codigo': a} for a in alims]}
            for s, alims in por_set.items() if s not in ('SET 8', 'SET 9')]},
        {'nombre': 'Sur', 'sets': [
            {'codigo': s, 'nombre': '', 'alimentadores': [{'codigo': a} for a in por_set[s]]}
            for s in ('SET 8', 'SET 9')]}]})
    return e, por_set


def _geografia(red):
    """El mapa de la red unida, de las coordenadas de sus nodos: hace falta para escribir
    los diagramas."""
    from igea_dgs.geography import GeoLine, GeoPoint, GeographyManifest

    def punto(n):
        nodo = red.nodes[n]
        return GeoPoint(-13.0 + nodo.y / 1e5, -76.0 + nodo.x / 1e5, nodo.x, nodo.y)

    nodos = {n: punto(n) for n in red.nodes}
    lineas = {ln.section_id: GeoLine(ln.section_id, ln.from_node, ln.to_node,
                                     (nodos[ln.from_node], nodos[ln.to_node])) for ln in red.lines}
    lat = [p.lat for p in nodos.values()]
    lon = [p.lon for p in nodos.values()]
    return GeographyManifest(red.name, red.network_id, red.source_node, 'EPSG:32718', 'EPSG:4326',
                             nodos, lineas, (0, 0, 0, 0), (min(lon), min(lat), max(lon), max(lat)), 0, 0)


def _red_dividida(rng):
    e, por_set = _dividida(rng)
    modelos = []
    for k, a in enumerate(a for alims in por_set.values() for a in alims):
        # Cada alimentador lejos de los demás: el diagrama de cada SET tiene su recuadro.
        m = _alimentador(a, 10.0, [f'{a}_H', f'{a}_1'], con_carga=f'{a}_1')
        # Con su alimentador en la carga y la SED, como los deja el lector: la metadata lo exige.
        de = {'feeder': a, 'network_id': m.network_id}
        modelos.append(replace(m, nodes={i: replace(n, y=10_000.0 * k) for i, n in m.nodes.items()},
                               loads=[replace(x, **de) for x in m.loads],
                               seds=[replace(x, **de) for x in m.seds]))
    red, _ = combine_models(modelos)
    estructurar(red, e)
    abrir_caminos_cerrados(red)
    return red, por_set


def _nombre_red(s):
    return 'Sur' if s in ('SET 8', 'SET 9') else f'Norte {s} Nombre{s[-1]}'


def test_un_zonal_dividido_tiene_una_red_por_set(tmp_path):
    """022:RF-64, 022:RF-66, 022:RF-67 — el zonal marcado tiene una red por SET, con su zonal y
    su SET en el nombre; el que no, una sola; cada SET y cada alimentador, en la suya."""
    red, por_set = _red_dividida(random.Random(SEMILLA))
    _out, t = _tablas(tmp_path, red)
    redes = {r['loc_name']: r['FID'] for r in t['ElmNet']}
    assert set(redes) == {_nombre_red(s) for s in por_set}, f'semilla {SEMILLA}'
    sets = {r['loc_name']: r for r in t['ElmSubstat'] if r['loc_name'].startswith('SET')}
    terms = {r['loc_name']: r for r in t['ElmTerm']}
    for s, alims in por_set.items():
        rotulo = s if s in ('SET 8', 'SET 9') else f'{s} Nombre{s[-1]}'
        assert sets[rotulo]['fold_id'] == redes[_nombre_red(s)]
        for a in alims:
            assert terms[f'{a}_H']['fold_id'] == redes[_nombre_red(s)], (a, f'semilla {SEMILLA}')


def test_cada_red_por_set_con_su_diagrama(tmp_path):
    """022:RF-65 — cada red tiene su diagrama, y cada cabecera se dibuja en el de su red:
    DIgSILENT dimensiona cada hoja con el recuadro de sus gráficos, a la medida de su SET."""
    red, _por_set = _red_dividida(random.Random(SEMILLA))
    out = tmp_path / 'g.dgs'
    write_dgs(red, out, geography=_geografia(red))
    t = {k: v['rows_dict'] for k, v in parse_dgs(out).items()}
    redes = {r['FID']: r for r in t['ElmNet']}
    diagramas = {r['FID']: r for r in t['IntGrfnet']}
    assert len(diagramas) == len(redes)
    assert {r['pDiagram'] for r in redes.values()} == set(diagramas)
    assert {d['pDataFolder'] for d in diagramas.values()} == set(redes)
    terms = {r['FID']: r for r in t['ElmTerm']}
    for g in t['IntGrf']:
        term = terms.get(g['pDataObj'])
        if term is not None and term['loc_name'].endswith('_H'):
            assert diagramas[g['fold_id']]['pDataFolder'] == term['fold_id'], f'semilla {SEMILLA}'


def test_el_enlace_entre_dos_set_va_en_la_de_menor_codigo(tmp_path):
    """022:RF-68 — un enlace entre alimentadores de dos SET de un zonal dividido va abierto en
    la red de la SET de menor código y en su diagrama, sea cual sea el orden de la unión."""
    e = estructura_de_dict({'zonales': [{'nombre': 'Norte', 'dividir_por_set': True, 'sets': [
        {'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': [{'codigo': 'A'}]},
        {'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': [{'codigo': 'B'}]}]}]})
    for orden in (['B', 'A'], ['A', 'B']):
        modelos = {'A': _alimentador('A', 10.0, ['A_H', 'A_1', 'T']),
                   'B': _alimentador('B', 10.0, ['B_H', 'B_1', 'T'])}
        red, _ = combine_models([modelos[a] for a in orden])
        estructurar(red, e)
        abrir_caminos_cerrados(red)
        assert red.combined.ties, 'el nodo compartido es un punto de enlace'
        out = tmp_path / f'{"".join(orden)}.dgs'
        write_dgs(red, out, geography=_geografia(red))
        t = {k: v['rows_dict'] for k, v in parse_dgs(out).items()}
        redes = {r['loc_name']: r['FID'] for r in t['ElmNet']}
        assert set(redes) == {'Norte SET 1 Uno', 'Norte SET 2 Dos'}
        enlace = next(r for r in t['ElmCoup'] if r['loc_name'] == red.combined.ties[0].name)
        assert enlace['fold_id'] == redes['Norte SET 1 Uno'] and enlace['on_off'] == '0', orden
        diag = {r['FID']: r['pDataFolder'] for r in t['IntGrfnet']}
        g = next(r for r in t['IntGrf'] if r['pDataObj'] == enlace['FID'])
        assert diag[g['fold_id']] == redes['Norte SET 1 Uno'], orden


def test_la_metadata_y_el_manifiesto_nombran_la_red_de_su_set(tmp_path):
    """022:RF-69 — la importación, la verificación y la calibración buscan las redes por el
    manifiesto y cada objeto por la red de su metadata: los dos nombran la red de su SET."""
    from igea_dgs.feeder_metadata import assignments_from_model
    from igea_dgs.geography import geography_to_dict

    red, por_set = _red_dividida(random.Random(SEMILLA))
    out = tmp_path / 'm.dgs'
    geo = _geografia(red)
    manifiesto = write_dgs(red, out, geography=geo)
    redes = {r['loc_name'] for r in parse_dgs(out)['ElmNet']['rows_dict']}
    assert set(geography_to_dict(geo, red)['redes']) == redes
    grid = {a.feeder: a.grid for a in assignments_from_model(red, manifiesto) if a.class_name == 'ElmLod'}
    for s, alims in por_set.items():
        for a in alims:
            assert grid[a] == _nombre_red(s), (a, f'semilla {SEMILLA}')
