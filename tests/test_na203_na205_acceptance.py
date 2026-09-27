from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from igea_dgs.batch import convert_group
from igea_dgs.dataset import CymdistDataset
from igea_dgs.naming import feeder_short_name
from synthetic_export import ExportSpec, write_export


def _load_verifier():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'verify_na203_na205.py'
    spec = importlib.util.spec_from_file_location('verify_na203_na205', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def group_artifacts(tmp_path):
    red, loads, equipment = write_export(ExportSpec(feeders=2), tmp_path / 'source')
    ds = CymdistDataset.from_files(red, loads, equipment)
    networks = list(ds.feeders)[:2]
    feeders = tuple(feeder_short_name(network) for network in networks)
    out = tmp_path / 'out'
    result = convert_group(ds, feeders, out, name='_'.join(feeders), source_crs='EPSG:32718')
    assert result['status'] == 'ok', result
    stem = result['name']
    return {
        'feeders': feeders,
        'dgs': out / f'{stem}.dgs',
        'manifest': out / f'{stem}_manifest.json',
        'metadata': out / f'{stem}_feeder_metadata.json',
        'validation': out / f'{stem}_validation.json',
    }


def test_verifier_accepts_complete_adaptive_two_feeder_artifacts(group_artifacts):
    mod = _load_verifier()
    a = group_artifacts

    report = mod.verify_artifacts(
        dgs=a['dgs'], manifest=a['manifest'], feeder_metadata=a['metadata'],
        validation=a['validation'], expected_feeders=a['feeders'], expected_trafomix=0,
    )

    assert report['ok'] is True, report['errors']
    assert report['checks']['metadata']['ElmLod']['matches_dgs'] is True
    assert report['checks']['metadata']['ElmXnet']['assignments'] == 2
    assert set(report['checks']['metadata']['feeders']) == set(a['feeders'])
    assert report['checks']['sed_internal_topology']['complete'] is True
    assert report['checks']['switch_reconciliation']['ok'] is True
    assert report['checks']['diagram']['adaptive'] is True
    assert report['checks']['diagram']['scale_units_per_m'] == pytest.approx(2.08, rel=0.05)
    assert report['checks']['validation_errors_total'] == 0


@pytest.mark.parametrize(
    ('target', 'mutate', 'message'),
    [
        ('validation', lambda data: data.update(errors_total=1), 'validación'),
        ('manifest', lambda data: data.update(hoja={'formato': 'A0'}), 'adaptativo'),
        ('manifest', lambda data: data['completitud']['fallos'].append('maniobras perdidas'), 'maniobras'),
    ],
)
def test_verifier_fails_closed_and_writes_diagnostics(
    group_artifacts, tmp_path, target, mutate, message,
):
    mod = _load_verifier()
    a = group_artifacts
    path = a[target]
    data = json.loads(path.read_text(encoding='utf-8'))
    mutate(data)
    path.write_text(json.dumps(data), encoding='utf-8')
    output_json = tmp_path / 'acceptance.json'
    output_txt = tmp_path / 'acceptance.txt'

    report = mod.verify_and_write(
        dgs=a['dgs'], manifest=a['manifest'], feeder_metadata=a['metadata'],
        validation=a['validation'], output_json=output_json, output_txt=output_txt,
        expected_feeders=a['feeders'], expected_trafomix=0,
    )

    assert report['ok'] is False
    assert any(message.lower() in error.lower() for error in report['errors'])
    assert output_json.is_file() and output_txt.is_file()
    assert 'FAIL' in output_txt.read_text(encoding='utf-8')


def test_verifier_rejects_missing_load_assignment(group_artifacts):
    mod = _load_verifier()
    a = group_artifacts
    metadata = json.loads(a['metadata'].read_text(encoding='utf-8'))
    index = next(i for i, row in enumerate(metadata['assignments']) if row['class_name'] == 'ElmLod')
    metadata['assignments'].pop(index)
    a['metadata'].write_text(json.dumps(metadata), encoding='utf-8')

    report = mod.verify_artifacts(
        dgs=a['dgs'], manifest=a['manifest'], feeder_metadata=a['metadata'],
        validation=a['validation'], expected_feeders=a['feeders'], expected_trafomix=0,
    )

    assert report['ok'] is False
    assert any('ElmLod' in error for error in report['errors'])


@pytest.mark.real_na203_na205
def test_real_na203_na205_artifacts_when_explicitly_available():
    folder_value = os.environ.get('IGEA_NA203_NA205_ACCEPTANCE', '').strip()
    if not folder_value:
        pytest.skip(
            'NO ACEPTADO EN VIVO: defina IGEA_NA203_NA205_ACCEPTANCE con la carpeta '
            'de artefactos reales regenerados'
        )
    folder = Path(folder_value)
    stem = 'NA203_NA205'
    mod = _load_verifier()
    report = mod.verify_artifacts(
        dgs=folder / f'{stem}.dgs',
        manifest=folder / f'{stem}_manifest.json',
        feeder_metadata=folder / f'{stem}_feeder_metadata.json',
        validation=folder / f'{stem}_validation.json',
    )
    assert report['ok'] is True, report
