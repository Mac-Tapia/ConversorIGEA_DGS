from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _txt_workspace(tmp_path):
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='source-run-tests', root=tmp_path / 'workspace')
    ws.options['input_mode'] = 'txt'
    originals = {
        'red': _write(tmp_path / 'server' / 'RED original.txt', b'RED\r\ncontenido\r\n'),
        'loads': _write(tmp_path / 'server' / 'CARGA original.txt', b'CARGA\r\n10;20\r\n'),
        'equipment': _write(tmp_path / 'server' / 'BD Equipo.txt', b'EQUIPOS\r\nAAAC\r\n'),
    }
    for slot, path in originals.items():
        ws.set_input(slot, path, origin='server')
    return ws, originals


def test_source_run_custodia_originales_y_hashes(tmp_path):
    from igea_dgs.web.source_runs import create_source_run

    ws, originals = _txt_workspace(tmp_path)

    snapshot = create_source_run(ws)

    assert ws.active_run_id == snapshot.run_id
    assert snapshot.mode == 'txt'
    assert set(snapshot.files) == set(originals)
    for slot, original in originals.items():
        custody = snapshot.files[slot]
        assert custody.path != original
        assert custody.path.read_bytes() == original.read_bytes()
        assert custody.sha256 == hashlib.sha256(original.read_bytes()).hexdigest()
        assert custody.size == original.stat().st_size
        parts = custody.path.parts
        start = parts.index('originales')
        assert parts[start:start + 3] == ('originales', 'txt', slot)

    manifest_path = ws.root / 'runs' / snapshot.run_id / 'source_manifest.json'
    persisted = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert persisted['run_id'] == snapshot.run_id
    assert persisted['mode'] == 'txt'
    assert persisted['fingerprint'] == snapshot.fingerprint
    assert {item['slot'] for item in persisted['files']} == set(originals)


def test_run_txt_no_incluye_slots_mdb_o_vnr(tmp_path):
    from igea_dgs.web.source_runs import create_source_run

    ws, _originals = _txt_workspace(tmp_path)
    ws.set_input('mdb', _write(tmp_path / 'server' / 'red.mdb', b'MDB'), origin='server')
    ws.set_input(
        'vnr_package', _write(tmp_path / 'server' / 'vnr.zip', b'PK\x03\x04VNR'),
        origin='server',
    )
    ws.options['input_mode'] = 'txt'

    snapshot = create_source_run(ws)

    assert set(snapshot.files) == {'red', 'loads', 'equipment'}
    assert not (ws.root / 'runs' / snapshot.run_id / 'originales' / 'mdb').exists()
    assert not (ws.root / 'runs' / snapshot.run_id / 'originales' / 'vnr').exists()


def test_cambiar_archivo_invalida_run_sin_borrar_historial(tmp_path):
    from igea_dgs.web.source_runs import create_source_run

    ws, _originals = _txt_workspace(tmp_path)
    snapshot = create_source_run(ws)
    run_dir = ws.root / 'runs' / snapshot.run_id

    ws.set_input('red', _write(tmp_path / 'server' / 'RED nuevo.txt', b'RED NUEVO'), origin='server')

    assert ws.active_run_id is None
    assert ws.active_run() is None
    assert run_dir.is_dir()
    assert (run_dir / 'source_manifest.json').is_file()
    persisted = json.loads((ws.root / 'workspace.json').read_text(encoding='utf-8'))
    assert persisted['active_run_id'] is None


def test_ruta_servidor_mutada_no_cambia_snapshot(tmp_path):
    from igea_dgs.web.source_runs import create_source_run

    ws, originals = _txt_workspace(tmp_path)
    snapshot = create_source_run(ws)
    custody_path = snapshot.files['red'].path
    before = custody_path.read_bytes()
    before_hash = snapshot.files['red'].sha256

    originals['red'].write_bytes(b'contenido cambiado fuera del workspace')
    restored = ws.active_run()

    assert restored is not None
    assert restored.files['red'].path.read_bytes() == before
    assert restored.files['red'].sha256 == before_hash
    assert hashlib.sha256(restored.files['red'].path.read_bytes()).hexdigest() == before_hash
