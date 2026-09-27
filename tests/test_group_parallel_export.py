from __future__ import annotations

import csv
import hashlib
import json

import pytest

from synthetic_export import ExportSpec, load_export
from igea_dgs.batch import convert_group
from igea_dgs.cli import _parser
from igea_dgs.naming import feeder_short_name


pytest.importorskip('pyproj')


def _dataset(tmp_path):
    return load_export(
        ExportSpec(
            feeders=3,
            sections_per_feeder=6,
            loads_per_feeder=3,
            switches_per_feeder=2,
            intermediate_per_section=1,
            layout='completo',
        ),
        tmp_path / 'source',
    )


def _portable_hashes(folder):
    ignored = {'DOS_manifest.json', 'DOS_electrical_export_manifest.json'}
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob('*'))
        if path.is_file() and path.name not in ignored
    }


def test_group_parallel_output_is_identical_to_serial(tmp_path):
    dataset = _dataset(tmp_path)
    feeders = [feeder_short_name(network) for network in dataset.feeder_ids()[:2]]

    serial = convert_group(
        dataset, feeders, tmp_path / 'serial', name='DOS', workers=1,
        export_electrical=True,
    )
    parallel = convert_group(
        dataset, feeders, tmp_path / 'parallel', name='DOS', workers=2,
        export_electrical=True,
    )

    assert serial['status'] == parallel['status'] == 'ok'
    assert serial['workers'] == 1
    assert parallel['workers'] == 2
    assert _portable_hashes(tmp_path / 'serial') == _portable_hashes(tmp_path / 'parallel')


def test_group_electrical_export_reconciles_complete_selected_source(tmp_path):
    dataset = _dataset(tmp_path)
    networks = dataset.feeder_ids()[:2]
    feeders = [feeder_short_name(network) for network in networks]
    out = tmp_path / 'out'

    manifest = convert_group(
        dataset, feeders, out, name='DOS', workers=2, export_electrical=True,
    )

    export_dir = out / 'DOS_electrical_tables'
    assert manifest['electrical_tables'] == str(export_dir)
    assert manifest['electrical_export_manifest'] == str(
        out / 'DOS_electrical_export_manifest.json'
    )
    expected_files = {
        'resumen.csv', 'redes.csv', 'nodos.csv', 'tramos.csv', 'tipos_linea.csv',
        'cargas.csv', 'sed.csv', 'maniobras.csv', 'fuentes.csv', 'auditoria.csv',
    }
    assert {path.name for path in export_dir.glob('*.csv')} == expected_files

    def rows(name):
        with (export_dir / name).open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))

    source_sections = sum(len(dataset.feeders[network]) for network in networks)
    source_loads = sum(len(dataset.customer_loads_by_feeder.get(network, ())) for network in networks)
    assert len(rows('tramos.csv')) == source_sections
    assert len(rows('cargas.csv')) == source_loads
    assert {row['Alimentador'] for row in rows('cargas.csv')} == set(feeders)
    assert all(row['Name'] and row['NetworkID'] for row in rows('cargas.csv'))

    sed_rows = rows('sed.csv')
    assert sed_rows
    required_sed_fields = {
        'Name', 'Alimentador', 'NetworkID', 'Potencia_kVA', 'Tension_MT_kV',
        'Tension_BT_kV', 'Uk_pct', 'Perdidas_Cobre_kW', 'Perdidas_Hierro_kW',
        'Corriente_Vacio_pct', 'Conexion_MT', 'Conexion_BT', 'Grupo_Vectorial',
    }
    assert required_sed_fields <= set(sed_rows[0])
    assert all(row['Uk_pct'] and row['Perdidas_Cobre_kW'] for row in sed_rows)
    assert any(field.startswith('Fuente_CUSTOMER_') for field in sed_rows[0])
    assert any(field.startswith('Fuente_LOADS_') for field in sed_rows[0])

    audit = {row['Metrica']: row for row in rows('auditoria.csv')}
    assert audit['tramos']['Estado'] == 'OK'
    assert audit['cargas']['Estado'] == 'OK'
    assert audit['sed_modeladas']['Estado'] == 'OK'

    export_manifest = json.loads(
        (out / 'DOS_electrical_export_manifest.json').read_text(encoding='utf-8')
    )
    assert export_manifest['feeders'] == feeders
    assert export_manifest['network_ids'] == list(networks)
    assert export_manifest['checks']['ok'] is True
    assert set(export_manifest['files']) == expected_files
    assert all(
        {'path', 'sha256', 'size'} <= set(info)
        for info in export_manifest['source_files'].values()
        if info is not None
    )


def test_group_without_electrical_export_keeps_optional_artifacts_absent(tmp_path):
    dataset = _dataset(tmp_path)
    feeders = [feeder_short_name(network) for network in dataset.feeder_ids()[:2]]

    manifest = convert_group(dataset, feeders, tmp_path / 'out', name='DOS', workers=2)

    assert manifest['status'] == 'ok'
    assert manifest['electrical_tables'] is None
    assert manifest['electrical_export_manifest'] is None
    assert not (tmp_path / 'out' / 'DOS_electrical_tables').exists()


def test_cli_exposes_complete_group_export_and_parallel_workers():
    args = _parser().parse_args([
        'convert', '--red', 'RED.txt', '--loads', 'CARGA.txt',
        '--equipment', 'BD_Equipo.txt', '--feeder', 'CA101', '--feeder', 'PE104',
        '--unir', 'CA101_PE104', '--out-dir', 'out', '--workers', '2',
        '--export-electrical',
    ])

    assert args.unir == 'CA101_PE104'
    assert args.workers == 2
    assert args.export_electrical is True
