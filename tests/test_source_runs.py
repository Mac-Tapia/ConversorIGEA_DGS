"""Pruebas del motor base de conversión.

Spec 034: 034:RF-20.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _txt_workspace(tmp_path):
    from convertersmartgrid.web.workspace import Workspace

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
    from convertersmartgrid.web.source_runs import create_source_run

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
    from convertersmartgrid.web.source_runs import create_source_run

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
    from convertersmartgrid.web.source_runs import create_source_run

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
    from convertersmartgrid.web.source_runs import create_source_run

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


@pytest.mark.parametrize('change', ['run_id', 'version', 'fingerprint', 'duplicate', 'foreign_slot',
                                  'escape', 'size_type', 'name_type', 'created_at'])
def test_run_rechaza_manifiesto_de_otra_identidad_sin_borrar_historial(tmp_path, change):
    """034:RF-20 — la identidad persistida no se acepta por parecer de la misma fuente."""
    from convertersmartgrid.web.source_runs import create_source_run, load_source_run

    ws, _ = _txt_workspace(tmp_path)
    snapshot = create_source_run(ws)
    path = snapshot.root / 'source_manifest.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    if change == 'run_id':
        payload['run_id'] = '20261108T000000-000000000000'
    elif change == 'version':
        payload['version'] = 999
    elif change == 'fingerprint':
        payload['fingerprint'] = '0' * 64
    elif change == 'duplicate':
        payload['files'].append(payload['files'][0])
    elif change == 'foreign_slot':
        payload['files'][0]['slot'] = 'mdb'
    elif change == 'escape':
        payload['files'][0]['path'] = '../../otro-run/original.txt'
    elif change == 'size_type':
        payload['files'][0]['size'] = str(payload['files'][0]['size'])
    elif change == 'name_type':
        payload['files'][0]['name'] = 123
        from convertersmartgrid.sources.snapshot import SourceFile, fingerprint
        payload['fingerprint'] = fingerprint(snapshot.mode, [
            SourceFile(slot=f['slot'], name=str(f['name']), path=Path(f['path']), size=f['size'],
                       sha256=f['sha256'], origin=f['origin'], source_path=f['source_path'])
            for f in payload['files']])
    else:
        payload['created_at'] = float('nan')
    path.write_text(json.dumps(payload), encoding='utf-8')

    with pytest.raises(ValueError):
        load_source_run(ws, snapshot.run_id)
    assert path.is_file()
    assert all(item.path.is_file() for item in snapshot.files.values())


@pytest.mark.parametrize('change', ['missing', 'same_size_changed_hash'])
def test_preparacion_rechaza_original_custodiado_ausente_o_modificado(tmp_path, change):
    """034:RF-20 — la preparación verifica bytes sin regenerar la referencia custodiada."""
    from convertersmartgrid.web.source_runs import create_source_run, load_source_run

    ws, originals = _txt_workspace(tmp_path)
    snapshot = create_source_run(ws)
    manifest = snapshot.root / 'source_manifest.json'
    before = manifest.read_bytes()
    original = snapshot.files['red'].path
    if change == 'missing':
        original.unlink()
    else:
        stat = original.stat()
        original.write_bytes(b'X' * original.stat().st_size)
        os.utime(original, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert (original.stat().st_size, original.stat().st_mtime_ns) == (stat.st_size, stat.st_mtime_ns)

    with pytest.raises(ValueError, match='custodiad|huella|ausente'):
        load_source_run(ws, snapshot.run_id, verify_files=True)
    assert manifest.read_bytes() == before
    assert all(path.is_file() for path in originals.values())


def test_relectura_ligera_no_lee_bytes_y_preparacion_verifica_hashes(tmp_path, monkeypatch):
    """034:RF-20; 065:RF-18 — consultas ligeras y preparación con integridad completa."""
    from convertersmartgrid.web.source_runs import create_source_run, load_source_run

    ws, _ = _txt_workspace(tmp_path)
    snapshot = create_source_run(ws)
    real_open = Path.open
    reads = []

    def traced_open(path, *args, **kwargs):
        if path in [item.path for item in snapshot.files.values()]:
            reads.append(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', traced_open)
    assert load_source_run(ws, snapshot.run_id).fingerprint == snapshot.fingerprint
    assert reads == []
    verified = load_source_run(ws, snapshot.run_id, verify_files=True)
    assert verified.fingerprint == snapshot.fingerprint
    assert set(reads) == {item.path for item in snapshot.files.values()}
