"""Entradas defectuosas: fallar claro, nunca fingir éxito.

El export que traiga un cliente puede venir truncado, incompleto o no ser el fichero
que cree. Lo peligroso no es que falle, es que **parezca que funcionó**: antes, un RED
vacío o truncado producía un lote «completado» con 0 convertidos y ni un solo error, y
un CARGA vacío generaba DGS sin ninguna carga cuyo flujo converge trivialmente.

Aquí se fija el contrato: o el lote produce lo que debe, o dice exactamente qué falta
y dónde.
"""

from __future__ import annotations

import json

import pytest

from igea_dgs.batch import convert_selection
from igea_dgs.dataset import CymdistDataset
from synthetic_export import ExportSpec, write_export

SPEC = ExportSpec(feeders=3, sections_per_feeder=4, loads_per_feeder=2)


@pytest.fixture
def export(tmp_path):
    return write_export(SPEC, tmp_path / 'src')


def _load(paths):
    return CymdistDataset.from_files(*paths)


class TestUnusableInputFailsLoudly:
    """Nada de «completado con 0 convertidos»."""

    def test_empty_red_is_rejected(self, export, tmp_path):
        red, carga, equipo = export
        red.write_text('', encoding='utf-8')
        with pytest.raises(ValueError, match='no contiene filas'):
            _load(export)

    def test_truncated_red_is_rejected(self, export, tmp_path):
        red, carga, equipo = export
        text = red.read_text(encoding='utf-8')
        red.write_text(text[: len(text) // 3], encoding='utf-8')
        with pytest.raises(ValueError) as excinfo:
            _load(export)
        # Truncado antes de [SECTION]: no hay ninguna cabecera FEEDER=.
        assert 'FEEDER=' in str(excinfo.value) or 'no contiene filas' in str(excinfo.value)
        assert red.name in str(excinfo.value)

    def test_missing_node_table_is_named_in_the_error(self, export):
        red, _carga, _equipo = export
        kept = [
            line for line in red.read_text(encoding='utf-8').split('\n')
            if line != '[NODE]' and not line.startswith('FORMAT_NODE') and not line.startswith('N1_')
        ]
        red.write_text('\n'.join(kept), encoding='utf-8')
        with pytest.raises(ValueError, match=r'\[NODE\]'):
            _load(export)

    def test_wrong_file_passed_as_red_is_rejected(self, export):
        """Pasar el CARGA donde va el RED debe decirlo, no dar un lote vacío."""
        red, carga, equipo = export
        with pytest.raises(ValueError, match='no contiene filas'):
            CymdistDataset.from_files(carga, carga, equipo)


class TestErrorsCarryTheirLocation:
    def test_duplicate_section_id_reports_file_and_line(self, export):
        red, _carga, _equipo = export
        red.write_text(
            red.read_text(encoding='utf-8').replace('SEC_1_1,N1_1,N1_2', 'SEC_1_0,N1_1,N1_2'),
            encoding='utf-8',
        )
        with pytest.raises(ValueError) as excinfo:
            _load(export)
        message = str(excinfo.value)
        assert 'SEC_1_0' in message
        assert f'{red.name}:' in message, 'el error debe indicar fichero y línea'
        line_ref = message.split(f'{red.name}:')[1].split(':')[0]
        assert line_ref.isdigit(), message


class TestSuspiciousButValidInputIsFlagged:
    """Legítimo pero sospechoso: se convierte, y queda registrado."""

    def test_empty_customer_loads_is_warned_in_the_manifest(self, export, tmp_path):
        _red, carga, _equipo = export
        carga.write_text(
            '[LOADS]\nFORMAT_LOADS=SectionID,DeviceNumber,LoadType,Connection,Location\n',
            encoding='utf-8',
        )
        manifest = convert_selection(
            _load(export), None, tmp_path / 'out', all_feeders=True, include_geography=False,
        )
        assert manifest['summary']['ok'] == SPEC.feeders
        assert manifest['inputs']['customer_loads_read'] == 0
        warnings = ' '.join(manifest['input_warnings'])
        assert 'CUSTOMER LOADS' in warnings
        assert 'convergerá trivialmente' in warnings

    def test_absent_switch_tables_are_warned(self, tmp_path):
        spec = ExportSpec(feeders=2, sections_per_feeder=3, with_switch_table=False)
        paths = write_export(spec, tmp_path / 'src')
        manifest = convert_selection(
            _load(paths), None, tmp_path / 'out', all_feeders=True, include_geography=False,
        )
        assert manifest['summary']['ok'] == 2
        assert any('maniobras' in w for w in manifest['input_warnings'])

    def test_clean_export_has_no_input_warnings(self, export, tmp_path):
        manifest = convert_selection(
            _load(export), None, tmp_path / 'out', all_feeders=True, include_geography=False,
        )
        assert manifest['input_warnings'] == []
        assert manifest['inputs']['feeders_read'] == SPEC.feeders
        assert manifest['inputs']['sections_read'] == SPEC.total_sections


class TestBadRowsIsolateToTheirFeeder:
    """Un dato malo tumba su alimentador, no el lote (regla de dominio 3)."""

    def _convert(self, paths, tmp_path):
        return convert_selection(
            _load(paths), None, tmp_path / 'out', all_feeders=True,
            include_geography=True, source_crs='EPSG:32718', strict=True,
        )

    def test_missing_node_reference_fails_only_its_feeder(self, export, tmp_path):
        red, _carga, _equipo = export
        red.write_text(
            red.read_text(encoding='utf-8').replace('SEC_1_2,N1_2,N1_3', 'SEC_1_2,N1_2,N_FANTASMA'),
            encoding='utf-8',
        )
        manifest = self._convert(export, tmp_path)
        assert manifest['summary']['ok'] == SPEC.feeders - 1
        assert manifest['summary']['failed'] == 1
        failed = [it for it in manifest['feeders'] if it['status'] == 'failed'][0]
        assert 'missing node' in failed['error']
        assert failed['dgs_published'] is False

    def test_non_numeric_length_fails_only_its_feeder(self, export, tmp_path):
        red, _carga, _equipo = export
        red.write_text(
            red.read_text(encoding='utf-8').replace('SEC_1_0,DEFAULT,40.0', 'SEC_1_0,DEFAULT,ABC'),
            encoding='utf-8',
        )
        manifest = self._convert(export, tmp_path)
        assert manifest['summary']['ok'] == SPEC.feeders - 1
        assert manifest['summary']['failed'] == 1

    def test_zero_nominal_voltage_is_rejected(self, export, tmp_path):
        red, _carga, _equipo = export
        red.write_text(red.read_text(encoding='utf-8').replace(',13.2', ',0'), encoding='utf-8')
        manifest = self._convert(export, tmp_path)
        assert manifest['summary']['ok'] == 0
        assert all('DesiredVoltage' in it['error'] for it in manifest['feeders'])


class TestFormatVariantsAreTolerated:
    """Variaciones inocuas del fichero no deben romper la lectura."""

    def test_crlf_line_endings(self, export, tmp_path):
        red, _carga, _equipo = export
        red.write_bytes(red.read_bytes().replace(b'\n', b'\r\n'))
        manifest = convert_selection(
            _load(export), None, tmp_path / 'out', all_feeders=True, include_geography=False,
        )
        assert manifest['summary']['ok'] == SPEC.feeders

    def test_extra_columns_are_ignored(self, export, tmp_path):
        red, _carga, _equipo = export
        red.write_text(
            red.read_text(encoding='utf-8').replace(
                'SEC_1_0,N1_0,N1_1,ABC', 'SEC_1_0,N1_0,N1_1,ABC,EXTRA1,EXTRA2,EXTRA3',
            ),
            encoding='utf-8',
        )
        manifest = convert_selection(
            _load(export), None, tmp_path / 'out', all_feeders=True, include_geography=False,
        )
        assert manifest['summary']['ok'] == SPEC.feeders

    def test_manifest_is_valid_json_with_the_input_summary(self, export, tmp_path):
        out = tmp_path / 'out'
        convert_selection(_load(export), None, out, all_feeders=True, include_geography=False)
        data = json.loads((out / 'batch_manifest.json').read_text(encoding='utf-8'))
        for key in ('feeders_read', 'nodes_read', 'sections_read', 'customer_loads_read'):
            assert key in data['inputs']
