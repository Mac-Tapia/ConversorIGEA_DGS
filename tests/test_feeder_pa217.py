"""Caso de aceptación por alimentador: PA217, por las dos alternativas de entrada.

PA217 es un buen caso de referencia: 1.324 tramos, 253 cargas con SED, 22,9 kV, y
mezcla de fases (ABC y AB). Cada prueba se ejecuta por separado con cada vía de entrada
—tres TXT y base Access—: cada fuente es independiente y se valida por sí misma, sin
compararla con la otra.

Se ejecutan solo con los datos disponibles, y hacen *skip* limpio si faltan:

    set IGEA_RED / IGEA_LOADS / IGEA_EQUIPMENT   → alternativa 1 (TXT)
    set IGEA_MDB  (+ IGEA_EQUIPMENT_MDB)         → alternativa 2 (Access)
"""

from __future__ import annotations

from pathlib import Path


from igea_dgs.batch import convert_selection
from igea_dgs.reglas import SIN_REGLAS
from igea_dgs.validate import parse_dgs

FEEDER = 'PA217'

def _convert(ds, out_dir, **kw):
    manifest = convert_selection(
        ds, [FEEDER], out_dir, include_geography=True, **kw,
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
        """Lo que sale en el DGS es lo que la entrada contiene, no una aproximación."""
        source, ds = dataset_for
        network_id = ds.resolve_feeder(FEEDER)
        sections = len(ds.feeders[network_id])
        loads = sum(1 for key in ds.customer_loads if ds.section_owner.get(key[0]) == network_id)

        # Sin las reglas del proyecto: con ellas los puentes DEFAULT de 10 m o menos se
        # funden en acopladores (en PA217, 784 de 1.324 tramos) y la cuenta deja de ser
        # una línea por tramo. Esta prueba mide la fidelidad literal a la entrada; que las
        # reglas no pierdan nada lo vigila auditar_completitud.
        _manifest, item = _convert(ds, tmp_path / source, reglas=SIN_REGLAS)
        tables = parse_dgs(item['dgs'])
        assert len(tables['ElmLne']['rows']) == sections
        assert len(tables['ElmLod']['rows']) == loads
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
