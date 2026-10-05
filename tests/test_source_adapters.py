from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from synthetic_export import ExportSpec, write_export


def _ctx():
    return SimpleNamespace(
        log=lambda _message: None,
        check_cancel=lambda: None,
        progress=lambda *_args: None,
        cancel=threading.Event(),
    )


def _txt_workspace(tmp_path, *, feeders: int = 2):
    from igea_dgs.web.workspace import Workspace

    red, loads, equipment = write_export(ExportSpec(feeders=feeders), tmp_path / 'export')
    ws = Workspace(id='adapter-tests', root=tmp_path / 'workspace')
    ws.options.update({'input_mode': 'txt', 'include_geography': False})
    for slot, path in (('red', red), ('loads', loads), ('equipment', equipment)):
        ws.set_input(slot, path, origin='server')
    return ws, (red, loads, equipment)


def test_txt_adapter_paridad_con_lector_actual(tmp_path):
    from igea_dgs.dataset import CymdistDataset
    from igea_dgs.web.source_runs import create_source_run
    from igea_dgs.web.sources import adapter_for

    ws, originals = _txt_workspace(tmp_path)
    expected = CymdistDataset.from_files(*originals)
    snapshot = create_source_run(ws)

    result = adapter_for('txt').load(snapshot, aliases={})

    assert result.dataset.feeder_ids() == expected.feeder_ids()
    assert len(result.dataset.nodes) == len(expected.nodes)
    assert len(result.dataset.sections) == len(expected.sections)
    assert result.provenance['source_run_id'] == snapshot.run_id
    assert result.provenance['source_mode'] == 'txt'
    assert Path(result.dataset.red_path).resolve() == snapshot.files['red'].path.resolve()


def test_mdb_adapter_paridad_con_lector_actual(tmp_path, monkeypatch):
    from igea_dgs.web.source_runs import create_source_run
    from igea_dgs.web.sources import adapter_for
    from igea_dgs.web.workspace import Workspace

    mdb = tmp_path / 'red.mdb'
    mdb.write_bytes(b'base access de prueba')
    ws = Workspace(id='mdb-adapter', root=tmp_path / 'workspace')
    ws.options['input_mode'] = 'mdb'
    ws.set_input('mdb', mdb, origin='server')
    snapshot = create_source_run(ws)
    expected = object()
    called = {}

    def fake_reader(path, *, equipment_db=None, networks=None):
        called.update(path=path, equipment_db=equipment_db, networks=networks)
        return expected

    monkeypatch.setattr('igea_dgs.access.read_access_dataset', fake_reader)

    result = adapter_for('mdb').load(snapshot, aliases={})

    assert result.dataset is expected
    assert Path(called['path']).resolve() == snapshot.files['mdb'].path.resolve()
    assert called['equipment_db'] is None and called['networks'] is None
    assert result.provenance['source_mode'] == 'mdb'


def test_adapter_rechaza_slot_de_otro_modo(tmp_path):
    from igea_dgs.web.source_runs import SourceFile, SourceSnapshot
    from igea_dgs.web.sources import SourceModeError, adapter_for

    foreign = tmp_path / 'red.mdb'
    foreign.write_bytes(b'mdb')
    source_file = SourceFile(
        slot='mdb', name=foreign.name, path=foreign, size=3, sha256='0' * 64,
        origin='server', source_path=str(foreign),
    )
    snapshot = SourceSnapshot(
        run_id='run-foreign', mode='txt', root=tmp_path, fingerprint='f' * 64,
        created_at=0.0, files={'mdb': source_file},
    )

    with pytest.raises(SourceModeError, match='no pertenece al modo txt'):
        adapter_for('txt').load(snapshot, aliases={})


def test_load_crea_run_antes_de_leer_y_usa_su_salida(tmp_path):
    from igea_dgs.web import services

    ws, originals = _txt_workspace(tmp_path)

    result = services.load_dataset(ws, _ctx())

    snapshot = ws.active_run()
    assert snapshot is not None
    assert ws.loaded_run_id == snapshot.run_id
    assert ws.out_dir == snapshot.root / 'salida'
    assert result['source_run_id'] == snapshot.run_id
    assert result['source_mode'] == 'txt'
    assert Path(ws.dataset.red_path).resolve() != originals[0].resolve()
    assert Path(ws.dataset.red_path).resolve() == snapshot.files['red'].path.resolve()


def test_convert_rechaza_source_run_mismatch(tmp_path):
    from igea_dgs.web import services
    from igea_dgs.web.source_runs import create_source_run

    ws, _originals = _txt_workspace(tmp_path)
    services.load_dataset(ws, _ctx())
    loaded_run_id = ws.loaded_run_id
    replacement = create_source_run(ws)
    assert replacement.run_id != loaded_run_id

    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.convert(ws, _ctx(), feeders=[], all_feeders=False)


def test_conversion_estampa_run_en_manifiesto_y_metadata(tmp_path):
    import json

    from igea_dgs.web import services

    ws, _originals = _txt_workspace(tmp_path, feeders=1)
    services.load_dataset(ws, _ctx())
    row = services.feeder_rows(ws)[0]

    result = services.convert(ws, _ctx(), feeders=[row['feeder']], all_feeders=False)

    assert result['summary']['ok'] == 1
    manifest = json.loads((ws.out_dir / 'batch_manifest.json').read_text(encoding='utf-8'))
    item = manifest['feeders'][0]
    assert manifest['source_run_id'] == ws.active_run_id
    assert manifest['source_mode'] == 'txt'
    assert item['source_run_id'] == ws.active_run_id
    metadata = json.loads(Path(item['feeder_metadata']).read_text(encoding='utf-8'))
    assert metadata['source_run_id'] == ws.active_run_id
    assert metadata['source_fingerprint'] == manifest['source_fingerprint']


def test_conversion_unida_estampa_el_mismo_run(tmp_path):
    import json

    from igea_dgs.web import services

    ws, _originals = _txt_workspace(tmp_path, feeders=2)
    services.load_dataset(ws, _ctx())
    feeders = [row['feeder'] for row in services.feeder_rows(ws)]

    result = services.convert_group(
        ws, _ctx(), feeders, 'RED_AISLADA', requested_feeders=feeders,
    )

    assert result['status'] == 'ok'
    assert ws.groups['RED_AISLADA']['source_run_id'] == ws.active_run_id
    manifest = json.loads(
        (ws.out_dir / 'RED_AISLADA_manifest.json').read_text(encoding='utf-8')
    )
    metadata = json.loads(
        (ws.out_dir / 'RED_AISLADA_feeder_metadata.json').read_text(encoding='utf-8')
    )
    assert manifest['source_run_id'] == ws.active_run_id
    assert metadata['source_run_id'] == ws.active_run_id


def test_conversion_unida_rechaza_source_run_mismatch(tmp_path):
    from igea_dgs.web import services
    from igea_dgs.web.source_runs import create_source_run

    ws, _originals = _txt_workspace(tmp_path, feeders=2)
    services.load_dataset(ws, _ctx())
    feeders = [row['feeder'] for row in services.feeder_rows(ws)]
    create_source_run(ws)

    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.convert_group(ws, _ctx(), feeders, 'NO_MEZCLAR')
