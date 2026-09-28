"""Caso de aceptación por alimentador: PA217, por las dos alternativas de entrada.

PA217 es un buen caso de referencia: 1.324 tramos, 253 cargas con SED, 22,9 kV, y
mezcla de fases (ABC y AB). Estas pruebas exigen que **las dos vías de entrada**
—tres TXT y base Access— produzcan el mismo modelo eléctrico.

Se ejecutan solo con los datos disponibles, y hacen *skip* limpio si faltan:

    set IGEA_RED / IGEA_LOADS / IGEA_EQUIPMENT   → alternativa 1 (TXT)
    set IGEA_MDB  (+ IGEA_EQUIPMENT_MDB)         → alternativa 2 (Access)

Lo que **no** se exige es igualdad byte a byte del ``.dgs``: las dos vías difieren
legítimamente porque la base conserva el código de conductor real allí donde el export
TXT escribe ``DEFAULT``. Esa diferencia se comprueba de forma explícita en
``TestPa217ConductorRecovery``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from igea_dgs.batch import convert_selection
from igea_dgs.validate import parse_dgs

FEEDER = 'PA217'
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
    """Parametriza cada prueba sobre las dos alternativas de entrada."""
    ds = txt_dataset if request.param == 'txt' else mdb_dataset
    try:
        ds.resolve_feeder(FEEDER)
    except KeyError:
        pytest.skip(f'{FEEDER} no está en la entrada «{request.param}»')
    return request.param, ds


def _convert(ds, out_dir):
    manifest = convert_selection(
        ds, [FEEDER], out_dir, include_geography=True,
        source_crs='EPSG:32718', strict=True, export_tsv=True,
    )
    return manifest, manifest['feeders'][0]


class TestPa217ConvertsFromBothInputs:
    def test_conversion_succeeds_without_errors(self, dataset_for, tmp_path):
        source, ds = dataset_for
        manifest, item = _convert(ds, tmp_path / source)
        assert item['status'] == 'ok', item.get('error')
        assert item['errors_total'] == 0
        assert manifest['summary']['failed'] == 0
        assert Path(item['dgs']).is_file()

    def test_element_counts_match_the_source(self, dataset_for, tmp_path):
        """Cada SECTION se reconcilia como línea o puente según las reglas activas."""
        source, ds = dataset_for
        network_id = ds.resolve_feeder(FEEDER)
        sections = len(ds.feeders[network_id])
        loads = sum(1 for key in ds.customer_loads if ds.section_owner.get(key[0]) == network_id)

        _manifest, item = _convert(ds, tmp_path / source)
        tables = parse_dgs(item['dgs'])
        completeness = item['completitud']
        bridges = item['reglas']['puentes']['tramos']
        trafomix = item['reglas']['trafomix']['excluidos']
        assert completeness['fallos'] == []
        assert completeness['entrada']['tramos'] == sections
        assert len(tables['ElmLne']['rows']) + bridges == sections
        assert completeness['entrada']['cargas'] == loads
        assert len(tables['ElmLod']['rows']) + trafomix == loads
        # Una SED y un transformador por carga con código de equipo.
        assert len(tables['ElmSubstat']['rows']) == len(tables['ElmTr2']['rows'])
        assert len(tables['ElmXnet']['rows']) == 1

    def test_geography_is_complete(self, dataset_for, tmp_path):
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        assert item['geography_coverage']['nodes_pct'] == 100.0
        assert item['geography_coverage']['lines_pct'] == 100.0
        assert Path(item['geography']).is_file()

    def test_nominal_voltage_is_22_9_kv(self, dataset_for, tmp_path):
        """La tensión viene de la entrada; en Access se reconstruye ×√3."""
        source, ds = dataset_for
        network_id = ds.resolve_feeder(FEEDER)
        assert abs(float(ds.sources[network_id]['DesiredVoltage']) - 22.9) < 1e-6

        _manifest, item = _convert(ds, tmp_path / source)
        tables = parse_dgs(item['dgs'])
        idx = tables['ElmTerm']['fields'].index('uknom')
        voltages = {row[idx] for row in tables['ElmTerm']['rows']}
        # Barras del alimentador a 22,9 kV; las barras BT internas de SED, a la BT.
        assert '22.9' in voltages

    def test_no_unresolved_line_types(self, dataset_for, tmp_path):
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        assert item['unresolved_line_types'] == []

    def test_tsv_export_is_written(self, dataset_for, tmp_path):
        source, ds = dataset_for
        _manifest, item = _convert(ds, tmp_path / source)
        tsv_dir = Path(item['tsv_dir'])
        assert tsv_dir.is_dir()
        assert (tsv_dir / 'ElmLne.tsv').is_file()
        assert (tsv_dir / 'ElmTerm.tsv').is_file()

    def test_output_is_published_atomically(self, dataset_for, tmp_path):
        from igea_dgs.batch import STAGE_PREFIX

        source, ds = dataset_for
        out = tmp_path / source
        _convert(ds, out)
        assert not [p for p in out.iterdir() if p.name.startswith(STAGE_PREFIX)]


class TestPa217IsTheSameNetworkFromBothInputs:
    """Las dos vías deben describir el mismo alimentador."""

    @pytest.fixture
    def both(self, txt_dataset, mdb_dataset):
        for ds in (txt_dataset, mdb_dataset):
            try:
                ds.resolve_feeder(FEEDER)
            except KeyError:
                pytest.skip(f'{FEEDER} no está en las dos entradas')
        # Solo tiene sentido comparar tramo a tramo la MISMA exportación. CYMDIST renumera
        # nodos entre entregas: con TXT y base de fechas distintas, esto daba 10 fallos
        # que no eran del lector. El criterio mira los ID de NODE y SECTION, no los
        # extremos de cada tramo, así que un fallo real de mapeo sigue detectándose.
        from igea_dgs.huella import comparar

        huella = comparar(txt_dataset, mdb_dataset)
        if not huella.misma_foto:
            pytest.skip(huella.motivo())
        return txt_dataset, mdb_dataset

    def test_same_network_id_and_sections(self, both):
        txt, mdb = both
        network_id = txt.resolve_feeder(FEEDER)
        assert mdb.resolve_feeder(FEEDER) == network_id
        assert set(txt.feeders[network_id]) == set(mdb.feeders[network_id])

    def test_same_topology_per_section(self, both):
        txt, mdb = both
        for section_id in txt.feeders[txt.resolve_feeder(FEEDER)]:
            a, b = txt.sections[section_id], mdb.sections[section_id]
            assert a['FromNodeID'] == b['FromNodeID'], section_id
            assert a['ToNodeID'] == b['ToNodeID'], section_id
            assert a['Phase'] == b['Phase'], f'{section_id}: fase {a["Phase"]} vs {b["Phase"]}'

    def test_same_lengths_and_medium(self, both):
        txt, mdb = both
        for section_id in txt.feeders[txt.resolve_feeder(FEEDER)]:
            a, b = txt.line_configurations[section_id], mdb.line_configurations[section_id]
            assert abs(float(a['Length'] or 0) - float(b['Length'] or 0)) < 1e-3, section_id
            assert a['Overhead'] == b['Overhead'], section_id

    def test_same_nominal_voltage(self, both):
        txt, mdb = both
        network_id = txt.resolve_feeder(FEEDER)
        a = float(txt.sources[network_id]['DesiredVoltage'])
        b = float(mdb.sources[network_id]['DesiredVoltage'])
        assert abs(a - b) < 1e-6

    def test_same_dgs_structure(self, both, tmp_path):
        """Mismos conteos en todas las tablas del DGS, por ambas vías."""
        txt, mdb = both
        _m1, a = _convert(txt, tmp_path / 'txt')
        _m2, b = _convert(mdb, tmp_path / 'mdb')
        ta, tb = parse_dgs(a['dgs']), parse_dgs(b['dgs'])
        for table in ('ElmTerm', 'ElmLne', 'ElmLod', 'StaSwitch', 'StaCubic',
                      'ElmTr2', 'ElmSubstat', 'ElmCoup', 'IntGrf', 'IntGrfcon'):
            na = len(ta.get(table, {'rows': []})['rows'])
            nb = len(tb.get(table, {'rows': []})['rows'])
            assert na == nb, f'{table}: TXT={na} ACCESS={nb}'


class TestPa217ConductorRecovery:
    """La base conserva el conductor real donde el export TXT escribe DEFAULT.

    Es la diferencia legítima entre las dos vías, y la razón por la que no se exige
    igualdad byte a byte del .dgs.
    """

    @pytest.fixture
    def both(self, txt_dataset, mdb_dataset):
        for ds in (txt_dataset, mdb_dataset):
            try:
                ds.resolve_feeder(FEEDER)
            except KeyError:
                pytest.skip(f'{FEEDER} no está en las dos entradas')
        # Solo tiene sentido comparar tramo a tramo la MISMA exportación. CYMDIST renumera
        # nodos entre entregas: con TXT y base de fechas distintas, esto daba 10 fallos
        # que no eran del lector. El criterio mira los ID de NODE y SECTION, no los
        # extremos de cada tramo, así que un fallo real de mapeo sigue detectándose.
        from igea_dgs.huella import comparar

        huella = comparar(txt_dataset, mdb_dataset)
        if not huella.misma_foto:
            pytest.skip(huella.motivo())
        return txt_dataset, mdb_dataset

    def test_access_has_fewer_default_sections(self, both):
        txt, mdb = both
        sections = txt.feeders[txt.resolve_feeder(FEEDER)]
        txt_default = {s for s in sections if txt.line_configurations[s]['LineCableID'] == 'DEFAULT'}
        mdb_default = {s for s in sections if mdb.line_configurations[s]['LineCableID'] == 'DEFAULT'}
        assert mdb_default <= txt_default, (
            'la base no puede tener DEFAULT donde el TXT trae un código real: '
            'sería pérdida de información del lector'
        )
        assert len(mdb_default) < len(txt_default), (
            'se esperaba que la base recuperase conductores que el TXT perdió'
        )

    def test_recovered_codes_exist_or_are_reported(self, both):
        """Cada código recuperado debe estar en el catálogo, o quedar registrado."""
        txt, mdb = both
        sections = txt.feeders[txt.resolve_feeder(FEEDER)]
        catalog = {r['ID'] for r in mdb.equipment_tables.get('LINE', ())}
        catalog |= {r['ID'] for r in mdb.equipment_tables.get('CONCENTRIC NEUTRAL CABLE', ())}
        recovered = {
            mdb.line_configurations[s]['LineCableID']
            for s in sections
            if txt.line_configurations[s]['LineCableID'] == 'DEFAULT'
            and mdb.line_configurations[s]['LineCableID'] != 'DEFAULT'
        }
        assert recovered, 'no se recuperó ningún conductor'
        # Los que falten en el catálogo se resuelven por alias/vecino y se registran.
        assert len(recovered - catalog) <= 3, sorted(recovered - catalog)
