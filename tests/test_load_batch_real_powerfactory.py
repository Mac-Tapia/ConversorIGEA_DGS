"""Aceptación real opt-in sobre los proyectos dedicados AL209/IN111.

Las entradas se reconstruyen desde las rutas solicitadas por el operador. Los DGS ya
deben haberse importado en ``IGEA_DGS_CONVERTER_AL209`` e
``IGEA_DGS_CONVERTER_IN111`` mediante la interfaz del mismo conversor.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.real_load_batch,
    pytest.mark.skipif(
        os.environ.get('IGEA_RUN_REAL_PF') != '1',
        reason='Defina IGEA_RUN_REAL_PF=1 para modificar y restaurar proyectos dedicados.',
    ),
]

ROOT = Path(__file__).parents[1]
MDB = Path(os.environ.get(
    'IGEA_AL209_MDB', r'D:\BaseDatosElectroDunas\260919BaseDatos\202603\260924.mdb',
))
EQUIPMENT_MDB = Path(os.environ.get(
    'IGEA_AL209_EQUIPMENT_MDB',
    r'D:\BaseDatosElectroDunas\260919BaseDatos\202603\BASE JUL25 1.mdb',
))
TXT_ROOT = Path(os.environ.get(
    'IGEA_IN111_TXT_ROOT', r'D:\BaseDatosElectroDunas\260919BaseDatos\importarTXT',
))


def _feeder_payload(model, project: str) -> dict:
    from igea_dgs.loads import model_sed_loads

    current = next((row for row in model_sed_loads(model) if abs(row.kw) + abs(row.kvar) > 0), None)
    assert current is not None, f'{model.name} no tiene una carga no nula para la aceptación.'
    factor = 1.001
    p = current.p_mw * factor
    q = current.q_mvar * factor
    s = (p * p + q * q) ** 0.5
    return {
        'feeder': model.name,
        'network_id': model.network_id,
        'project_name': project,
        'updates': [{
            'sed_code': current.sed_code,
            'feeder': model.name,
            'network_id': model.network_id,
            'plini_mw': p,
            'qlini_mvar': q,
            'slini_mva': s,
            'coslini': abs(p) / s if s else 1.0,
        }],
    }


@pytest.fixture(scope='module')
def real_plans(tmp_path_factory):
    pytest.importorskip('pyodbc')
    from igea_dgs.access import list_networks, read_access_dataset
    from igea_dgs.dataset import CymdistDataset
    from igea_dgs.model import build_feeder_model

    assert MDB.is_file(), MDB
    assert EQUIPMENT_MDB.is_file(), EQUIPMENT_MDB
    txt = {
        'red': TXT_ROOT / '260927_Red.txt',
        'loads': TXT_ROOT / '260927_Carga.txt',
        'equipment': TXT_ROOT / '260927_Equipo.txt',
    }
    assert all(path.is_file() for path in txt.values()), txt
    al_network = next(name for name in list_networks(MDB) if 'AL209' in name.upper())
    al_dataset = read_access_dataset(MDB, equipment_db=EQUIPMENT_MDB, networks=[al_network])
    in_dataset = CymdistDataset.from_files(txt['red'], txt['loads'], txt['equipment'])
    al_model = build_feeder_model(al_dataset, 'AL209', strict=False, include_geography=False)
    in_model = build_feeder_model(in_dataset, 'IN111', strict=False, include_geography=False)
    feeders = [
        _feeder_payload(al_model, 'IGEA_DGS_CONVERTER_AL209'),
        _feeder_payload(in_model, 'IGEA_DGS_CONVERTER_IN111'),
    ]
    folder = tmp_path_factory.mktemp('real_load_batch')
    paths = {}
    for name, selected in (
        ('al209', feeders[:1]), ('in111', feeders[1:]), ('combined', feeders),
    ):
        path = folder / f'{name}.json'
        path.write_text(json.dumps({'batch_id': name, 'feeders': selected}), encoding='utf-8')
        paths[name] = path
    return paths


@pytest.fixture(scope='module')
def real_report(real_plans, tmp_path_factory):
    from igea_dgs.powerfactory_env import pf_python_dir, pf_subprocess_env, python_for_pf

    api_dir = pf_python_dir()
    interpreter, why = python_for_pf(api_dir)
    assert interpreter is not None, why
    output = tmp_path_factory.mktemp('real_load_batch_report') / 'combined_acceptance.json'
    completed = subprocess.run(
        [str(interpreter), str(ROOT / 'tools' / 'load_batch_acceptance.py'),
         '--plan', str(real_plans['combined']), '--output-json', str(output)],
        cwd=ROOT,
        env=pf_subprocess_env(api_dir),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=900,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + '\n' + completed.stderr
    return json.loads(output.read_text(encoding='utf-8'))


def _assert_restored(report):
    assert report['status'] == 'PASS', report
    assert all(item['status'] == 'PASS' for item in report['application']['feeders'])
    assert all(item['restored'] for item in report['restoration']['feeders'])
    assert all(item['load_flow']['return_code'] == 0 for item in report['restoration']['feeders'])
    assert all(item['load_flow']['ldf_valid'] is True for item in report['restoration']['feeders'])


def test_real_al209_mdb_load_batch_restores_originals(real_report):
    _assert_restored(real_report)
    assert next(
        item for item in real_report['restoration']['feeders'] if item['feeder'] == 'AL209'
    )['restored'] is True


def test_real_in111_txt_load_batch_restores_originals(real_report):
    _assert_restored(real_report)
    assert next(
        item for item in real_report['restoration']['feeders'] if item['feeder'] == 'IN111'
    )['restored'] is True


def test_real_combined_batch_reuses_one_application_session(real_report):
    _assert_restored(real_report)
    assert real_report['application_sessions'] == 1
