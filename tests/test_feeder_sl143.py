"""Caso de aceptación por alimentador: SL143, por las dos alternativas de entrada.

SL143 complementa a PA217 porque expone algo que aquél no tiene: **una isla
eléctrica**. El tramo ``SEC_1091_975575`` (nodos 5605→5606, 69,3 m) no está conectado
al SOURCE por ningún camino, y sus dos nodos no aparecen en ningún otro tramo: es un
fragmento flotante.

Eso lo convierte en el caso de referencia para una debilidad conocida: hoy la isla se
reporta solo como **aviso**, y la conversión termina con ``errors_total = 0``. En el
lote de referencia hay **10 de 93 alimentadores con isla**, 22 tramos y 20 cargas
desconectados del SOURCE. Estas pruebas fijan el comportamiento actual y, sobre todo,
dejan constancia de que la isla se detecta y se comunica — para que un cambio futuro de
política (convertirla en error en modo estricto) rompa aquí y sea una decisión
consciente, no un efecto colateral.

Otras diferencias con PA217: 10 kV en lugar de 22,9; todo trifásico; y mezcla real de
aéreo (797) y subterráneo (239).

Requisitos: ``IGEA_RED``/``IGEA_LOADS``/``IGEA_EQUIPMENT`` para la vía TXT, ``IGEA_MDB``
para la vía Access. Cada bloque hace *skip* limpio si falta su entrada.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from igea_dgs.batch import convert_selection
from igea_dgs.model import build_feeder_model
from igea_dgs.validate import parse_dgs

FEEDER = 'SL143'
ISLAND_SECTION = 'SEC_1091_975575'
MDB = os.environ.get('IGEA_MDB', '').strip()


@pytest.fixture(scope='module')
def txt_dataset(igea_paths):
    from igea_dgs.dataset import CymdistDataset

    red, loads, equip = igea_paths
    return CymdistDataset.from_files(red, loads, equip)


@pytest.fixture(scope='module')
def mdb_dataset():
    if not MDB or not Path(MDB).is_file():
        pytest.skip('Defina IGEA_MDB con la ruta de una base de red CYMDIST (.mdb)')
    pytest.importorskip('pyodbc')
    from igea_dgs.access import AccessReadError, read_access_dataset

    try:
        return read_access_dataset(MDB, equipment_db=os.environ.get('IGEA_EQUIPMENT_MDB') or None)
    except AccessReadError as exc:
        pytest.skip(f'No se pudo leer {MDB}: {exc}')


@pytest.fixture(params=['txt', 'mdb'])
def dataset_for(request, txt_dataset, mdb_dataset):
    ds = txt_dataset if request.param == 'txt' else mdb_dataset
    try:
        ds.resolve_feeder(FEEDER)
    except KeyError:
        pytest.skip(f'{FEEDER} no está en la entrada «{request.param}»')
    return request.param, ds


def _convert(ds, out_dir):
    manifest = convert_selection(
        ds, [FEEDER], out_dir, include_geography=True,
        source_crs='EPSG:32718', strict=True,
    )
    return manifest, manifest['feeders'][0]


class TestSl143ConvertsFromBothInputs:
    def test_conversion_succeeds(self, dataset_for, tmp_path):
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        assert item['status'] == 'ok', item.get('error')
        assert item['errors_total'] == 0
        assert Path(item['dgs']).is_file()

    def test_element_counts_match_the_source(self, dataset_for, tmp_path):
        source, ds = dataset_for
        network_id = ds.resolve_feeder(FEEDER)
        sections = len(ds.feeders[network_id])
        loads = sum(1 for key in ds.customer_loads if ds.section_owner.get(key[0]) == network_id)

        _manifest, item = _convert(ds, tmp_path / source)
        tables = parse_dgs(item['dgs'])
        assert len(tables['ElmLne']['rows']) == sections
        assert len(tables['ElmLod']['rows']) == loads
        assert len(tables['ElmXnet']['rows']) == 1

    def test_nominal_voltage_is_10_kv(self, dataset_for):
        """SL143 es de 10 kV; en Access la nominal se reconstruye desde la fase-neutro."""
        _source, ds = dataset_for
        network_id = ds.resolve_feeder(FEEDER)
        assert abs(float(ds.sources[network_id]['DesiredVoltage']) - 10.0) < 1e-6

    def test_mixed_overhead_and_underground(self, dataset_for):
        """Mezcla real de medio: el DGS debe distinguir aéreo de subterráneo."""
        _source, ds = dataset_for
        sections = ds.feeders[ds.resolve_feeder(FEEDER)]
        media = {ds.line_configurations[s]['Overhead'] for s in sections}
        assert media == {'0', '1'}, f'se esperaba mezcla aéreo/subterráneo, hay {media}'

    def test_underground_sections_keep_inair_zero(self, dataset_for, tmp_path):
        source, ds = dataset_for
        network_id = ds.resolve_feeder(FEEDER)
        underground = {
            s for s in ds.feeders[network_id]
            if ds.line_configurations[s]['Overhead'] == '0'
        }
        _manifest, item = _convert(ds, tmp_path / source)
        tables = parse_dgs(item['dgs'])
        name_i = tables['ElmLne']['fields'].index('loc_name')
        air_i = tables['ElmLne']['fields'].index('inAir')
        for row in tables['ElmLne']['rows']:
            expected = '0' if row[name_i] in underground else '1'
            assert row[air_i] == expected, row[name_i]

    def test_geography_is_complete(self, dataset_for, tmp_path):
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        assert item['geography_coverage']['nodes_pct'] == 100.0
        assert item['geography_coverage']['lines_pct'] == 100.0


class TestSl143IslandIsDetectedAndReported:
    """La debilidad que SL143 expone: la isla se avisa, pero no bloquea.

    Si alguien decide que una isla deba ser error en modo estricto, estas pruebas
    fallarán — y eso es lo que se busca: que sea un cambio deliberado.
    """

    def test_the_island_section_is_present_and_floating(self, dataset_for):
        from igea_dgs.model import _reachable_from_source

        _source, ds = dataset_for
        model = build_feeder_model(ds, FEEDER, strict=True)
        reachable = _reachable_from_source(model.source_node, model.lines)
        islands = [
            line for line in model.lines
            if line.from_node not in reachable or line.to_node not in reachable
        ]
        assert islands, 'se esperaba al menos una isla en SL143'
        ids = {line.section_id for line in islands}
        assert ISLAND_SECTION in ids, f'islas encontradas: {sorted(ids)}'

        island = next(line for line in islands if line.section_id == ISLAND_SECTION)
        # Fragmento realmente flotante: sus nodos no aparecen en ningún otro tramo.
        others = [
            line for line in model.lines
            if line is not island
            and {line.from_node, line.to_node} & {island.from_node, island.to_node}
        ]
        assert not others, f'{ISLAND_SECTION} no está aislado: comparte nodo con {others[:2]}'

    def test_the_island_is_reported_as_a_warning(self, dataset_for):
        _source, ds = dataset_for
        model = build_feeder_model(ds, FEEDER, strict=True)
        island_warnings = [w for w in model.warnings if 'desconectados del SOURCE' in w]
        assert island_warnings, f'la isla debe avisarse; avisos: {model.warnings}'
        text = island_warnings[0]
        assert FEEDER in text
        assert model.source_node in text

    def test_the_warning_reaches_the_manifest(self, dataset_for, tmp_path):
        """Un aviso que no llega al manifiesto es un aviso que nadie lee."""
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        assert any('desconectados del SOURCE' in w for w in item['warnings'])

    def test_conversion_still_succeeds_today(self, dataset_for, tmp_path):
        """Comportamiento actual: la isla NO bloquea ni en modo estricto.

        Queda fijado a propósito. Convertirlo en error es una decisión de producto
        (ver plan de mejora), no un efecto colateral de otro cambio.
        """
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        assert item['status'] == 'ok'
        assert item['errors_total'] == 0

    def test_island_elements_still_reach_the_dgs(self, dataset_for, tmp_path):
        """El tramo aislado se escribe: el DGS refleja el TXT, no lo corrige."""
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        tables = parse_dgs(item['dgs'])
        idx = tables['ElmLne']['fields'].index('loc_name')
        names = {row[idx] for row in tables['ElmLne']['rows']}
        assert ISLAND_SECTION in names


class TestSl143IsTheSameNetworkFromBothInputs:
    @pytest.fixture
    def both(self, txt_dataset, mdb_dataset):
        for ds in (txt_dataset, mdb_dataset):
            try:
                ds.resolve_feeder(FEEDER)
            except KeyError:
                pytest.skip(f'{FEEDER} no está en las dos entradas')
        return txt_dataset, mdb_dataset

    def test_same_topology_and_phases(self, both):
        txt, mdb = both
        for section_id in txt.feeders[txt.resolve_feeder(FEEDER)]:
            a, b = txt.sections[section_id], mdb.sections[section_id]
            assert (a['FromNodeID'], a['ToNodeID'], a['Phase']) == \
                   (b['FromNodeID'], b['ToNodeID'], b['Phase']), section_id

    def test_same_lengths_and_medium(self, both):
        txt, mdb = both
        for section_id in txt.feeders[txt.resolve_feeder(FEEDER)]:
            a, b = txt.line_configurations[section_id], mdb.line_configurations[section_id]
            assert abs(float(a['Length'] or 0) - float(b['Length'] or 0)) < 1e-3, section_id
            assert a['Overhead'] == b['Overhead'], section_id

    def test_same_dgs_structure(self, both, tmp_path):
        txt, mdb = both
        _m1, a = _convert(txt, tmp_path / 'txt')
        _m2, b = _convert(mdb, tmp_path / 'mdb')
        ta, tb = parse_dgs(a['dgs']), parse_dgs(b['dgs'])
        for table in ('ElmTerm', 'ElmLne', 'ElmLod', 'StaSwitch', 'StaCubic',
                      'ElmTr2', 'ElmSubstat', 'IntGrf'):
            na = len(ta.get(table, {'rows': []})['rows'])
            nb = len(tb.get(table, {'rows': []})['rows'])
            assert na == nb, f'{table}: TXT={na} ACCESS={nb}'

    def test_both_detect_the_same_island(self, both):
        from igea_dgs.model import _reachable_from_source

        islands = []
        for ds in both:
            model = build_feeder_model(ds, FEEDER, strict=True)
            reachable = _reachable_from_source(model.source_node, model.lines)
            islands.append({
                line.section_id for line in model.lines
                if line.from_node not in reachable or line.to_node not in reachable
            })
        assert islands[0] == islands[1], f'islas distintas: {islands}'

    def test_access_recovers_conductors_lost_in_the_txt(self, both):
        txt, mdb = both
        sections = txt.feeders[txt.resolve_feeder(FEEDER)]
        txt_default = {s for s in sections if txt.line_configurations[s]['LineCableID'] == 'DEFAULT'}
        mdb_default = {s for s in sections if mdb.line_configurations[s]['LineCableID'] == 'DEFAULT'}
        assert mdb_default <= txt_default
        assert len(txt_default) - len(mdb_default) > 0
