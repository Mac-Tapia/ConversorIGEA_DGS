"""Pruebas del motor base de conversión.

Spec 034: 034:RF-20.
"""
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
    from convertersmartgrid.web.workspace import Workspace

    red, loads, equipment = write_export(ExportSpec(feeders=feeders), tmp_path / 'export')
    ws = Workspace(id='adapter-tests', root=tmp_path / 'workspace')
    ws.options.update({'input_mode': 'txt', 'include_geography': False})
    for slot, path in (('red', red), ('loads', loads), ('equipment', equipment)):
        ws.set_input(slot, path, origin='server')
    return ws, (red, loads, equipment)


def test_txt_adapter_paridad_con_lector_actual(tmp_path):
    from convertersmartgrid.dataset import CymdistDataset
    from convertersmartgrid.web.source_runs import create_source_run
    from convertersmartgrid.web.sources import adapter_for

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
    from convertersmartgrid.web.source_runs import create_source_run
    from convertersmartgrid.web.sources import adapter_for
    from convertersmartgrid.web.workspace import Workspace

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

    monkeypatch.setattr('convertersmartgrid.access.read_access_dataset', fake_reader)

    result = adapter_for('mdb').load(snapshot, aliases={})

    assert result.dataset is expected
    assert Path(called['path']).resolve() == snapshot.files['mdb'].path.resolve()
    assert called['equipment_db'] is None and called['networks'] is None
    assert result.provenance['source_mode'] == 'mdb'


def test_adapter_rechaza_slot_de_otro_modo(tmp_path):
    from convertersmartgrid.web.source_runs import SourceFile, SourceSnapshot
    from convertersmartgrid.web.sources import SourceModeError, adapter_for

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
    from convertersmartgrid.web import services

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


def test_reinicio_sin_dataset_pide_cargar_sin_inventar_cambio_de_seleccion(tmp_path):
    """034:RF-20: reabrir una fuente intacta no equivale a cambiar sus entradas."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.requisitos import require_active_source_run
    from convertersmartgrid.web.workspace import Workspace

    ws, _ = _txt_workspace(tmp_path)
    services.load_dataset(ws, _ctx())
    reopened = Workspace.load(ws.root)
    assert reopened.dataset is None and reopened.loaded_run_id is None
    assert reopened.loaded_selection_token is None
    assert reopened.active_run().selection_token == reopened.source_selection_token()
    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH.*no está cargada'):
        require_active_source_run(reopened)


@pytest.mark.parametrize('change', ['mode', 'generation', 'loaded_token'])
def test_reinicio_guardas_de_una_red_cargada_siguen_vigentes(tmp_path, change):
    """034:RF-20: disponer del dataset no permite saltarse modo o tokens."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.requisitos import require_active_source_run

    ws, _ = _txt_workspace(tmp_path)
    services.load_dataset(ws, _ctx())
    if change == 'mode':
        ws.options['input_mode'] = 'mdb'
    elif change == 'generation':
        ws.source_generation += 1
    else:
        ws.loaded_selection_token = {**ws.loaded_selection_token, 'generation': -1}
    with pytest.raises(services.UserError, match='SOURCE_SELECTION_CHANGED'):
        require_active_source_run(ws)


@pytest.mark.parametrize('change', ['mode', 'generation'])
def test_reinicio_con_seleccion_realmente_distinta_sigue_bloqueado(tmp_path, change):
    """034:RF-20: no tener dataset tampoco oculta una modificación de selección."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.requisitos import require_active_source_run
    from convertersmartgrid.web.workspace import Workspace

    ws, _ = _txt_workspace(tmp_path)
    services.load_dataset(ws, _ctx())
    reopened = Workspace.load(ws.root)
    if change == 'mode':
        reopened.options['input_mode'] = 'mdb'
    else:
        reopened.source_generation += 1
    with pytest.raises(services.UserError, match='SOURCE_SELECTION_CHANGED'):
        require_active_source_run(reopened)


@pytest.mark.parametrize(('field', 'value'), [('version', 2), ('fingerprint', '0' * 64)])
def test_reinicio_con_manifiesto_invalido_nunca_habilita_una_fuente(tmp_path, field, value):
    """034:RF-20: un manifiesto inválido conserva el rechazo sin fuente cargada."""
    import json
    from convertersmartgrid.web import services
    from convertersmartgrid.web.requisitos import require_active_source_run
    from convertersmartgrid.web.workspace import Workspace

    ws, _ = _txt_workspace(tmp_path)
    services.load_dataset(ws, _ctx())
    manifest = ws.active_run().root / 'source_manifest.json'
    raw = json.loads(manifest.read_text(encoding='utf-8'))
    raw[field] = value
    manifest.write_text(json.dumps(raw), encoding='utf-8')
    reopened = Workspace.load(ws.root)
    assert reopened.active_run() is None
    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        require_active_source_run(reopened)


def test_convert_rechaza_source_run_mismatch(tmp_path):
    from convertersmartgrid.web import services
    from convertersmartgrid.web.source_runs import create_source_run

    ws, _originals = _txt_workspace(tmp_path)
    services.load_dataset(ws, _ctx())
    loaded_run_id = ws.loaded_run_id
    replacement = create_source_run(ws)
    assert replacement.run_id != loaded_run_id

    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.convert(ws, _ctx(), feeders=[], all_feeders=False)


def test_conversion_estampa_run_en_manifiesto_y_metadata(tmp_path):
    import json

    from convertersmartgrid.web import services

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

    from convertersmartgrid.web import services

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
    from convertersmartgrid.web import services
    from convertersmartgrid.web.source_runs import create_source_run

    ws, _originals = _txt_workspace(tmp_path, feeders=2)
    services.load_dataset(ws, _ctx())
    feeders = [row['feeder'] for row in services.feeder_rows(ws)]
    create_source_run(ws)

    with pytest.raises(services.UserError, match='SOURCE_RUN_MISMATCH'):
        services.convert_group(ws, _ctx(), feeders, 'NO_MEZCLAR')


@pytest.mark.parametrize('group', [False, True])
@pytest.mark.parametrize('slot', ['red', 'equipment'])
def test_conversion_revalida_bytes_custodiados_antes_del_dataset_cached_y_escritor(tmp_path, monkeypatch, group, slot):
    """034:RF-20 — mismo tamaño/mtime no conserva identidad si cambiaron los bytes."""
    import copy
    import os
    from convertersmartgrid.web import services

    ws, originals = _txt_workspace(tmp_path, feeders=1)
    services.load_dataset(ws, _ctx())
    snapshot = ws.active_run()
    path = snapshot.files[slot].path
    manifest = snapshot.root / 'source_manifest.json'
    baseline = manifest.read_bytes()
    inventory = copy.deepcopy(ws.inventory)
    stat = path.stat()
    path.write_bytes(b'X' * stat.st_size)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert (path.stat().st_size, path.stat().st_mtime_ns) == (stat.st_size, stat.st_mtime_ns)
    called = []
    monkeypatch.setattr('convertersmartgrid.batch.convert_selection', lambda *a, **k: called.append('individual'))
    monkeypatch.setattr('convertersmartgrid.batch.convert_group', lambda *a, **k: called.append('unida'))
    feeders = [row['feeder'] for row in services.feeder_rows(ws)]
    with pytest.raises(services.UserError, match='SOURCE_RUN_INTEGRITY.*huella'):
        if group:
            services.convert_group(ws, _ctx(), feeders, 'NO_ESCRIBIR')
        else:
            services.convert(ws, _ctx(), feeders, False)
    assert not called
    assert not list(ws.out_dir.glob('*.dgs'))
    assert ws.inventory == inventory
    assert manifest.read_bytes() == baseline
    assert all(path.is_file() for path in originals)


def test_carga_verifica_custodia_persistida_antes_del_lector(tmp_path, monkeypatch):
    """034:RF-20 — la carga valida la copia y su manifiesto antes de invocar adaptadores."""
    from convertersmartgrid.web import services, source_runs

    ws, originals = _txt_workspace(tmp_path, feeders=1)
    create = source_runs.create_source_run
    called = []

    def capture_and_tamper(workspace):
        snapshot = create(workspace)
        path = snapshot.files['red'].path
        path.write_bytes(b'X' * path.stat().st_size)
        return snapshot

    monkeypatch.setattr(source_runs, 'create_source_run', capture_and_tamper)
    monkeypatch.setattr('convertersmartgrid.sources.adapter_for', lambda *a, **k: called.append('lector'))
    with pytest.raises(services.UserError, match='SOURCE_RUN_INTEGRITY.*huella'):
        services.load_dataset(ws, _ctx())
    assert not called
    assert ws.dataset is None
    assert not ws.out_dir.exists()
    assert all(path.is_file() for path in originals)


@pytest.mark.parametrize('moment', ['copy', 'reader'])
def test_carga_obsoleta_no_reactiva_run_ni_publica_dataset_al_cambiar_modalidad(tmp_path, monkeypatch, moment):
    """034:RF-20 — un PUT de modalidad durante el trabajo conserva la decisión nueva."""
    from convertersmartgrid import sources
    from convertersmartgrid.web import services, source_runs

    ws, _ = _txt_workspace(tmp_path, feeders=1)
    mdb = tmp_path / 'solo-existencia.mdb'
    mdb.write_bytes(b'fixture de existencia; no es Access aceptado')
    ws.set_input('mdb', mdb, origin='server')
    ws.options['input_mode'] = 'txt'
    changed = []

    def change_mode():
        if not changed:
            with ws.lock:
                ws.invalidate()
                ws.options.update(input_mode='mdb')
                ws.save()
            changed.append(True)

    if moment == 'copy':
        real = source_runs._sha256_copy
        def copying(*args):
            value = real(*args)
            change_mode()
            return value
        monkeypatch.setattr(source_runs, '_sha256_copy', copying)
    else:
        factory = sources.adapter_for
        def adapter(*args, **kwargs):
            real = factory(*args, **kwargs)
            class Reader:
                def load(self, *args, **kwargs):
                    value = real.load(*args, **kwargs)
                    change_mode()
                    return value
            return Reader()
        monkeypatch.setattr(sources, 'adapter_for', adapter)
    with pytest.raises(ValueError, match='SOURCE_SELECTION_CHANGED'):
        services.load_dataset(ws, _ctx())
    assert ws.options['input_mode'] == 'mdb'
    assert ws.dataset is None and ws.loaded_run_id is None
    assert ws.active_run_id is None
    assert list((ws.root / 'runs').glob('*/source_manifest.json'))


def test_lector_real_no_puede_consumir_ABA_y_recibo_coincide_con_dgs_control(tmp_path, monkeypatch):
    """034:RF-20 — SHA y lector usan fuente excluida de escritores, no hash antes/después."""
    import hashlib
    from convertersmartgrid import sources
    from convertersmartgrid.web import services

    ws, _ = _txt_workspace(tmp_path / 'protected', feeders=1)
    factory = sources.adapter_for
    rejected = []
    def adapter(*args, **kwargs):
        real = factory(*args, **kwargs)
        class Reader:
            def load(self, snapshot, **kwargs):
                path = snapshot.files['loads'].path
                before = path.read_bytes()
                altered = before.replace(b'12.5', b'22.5')
                assert altered != before
                try:
                    path.write_bytes(altered)
                except OSError:
                    rejected.append(True)
                try:
                    return real.load(snapshot, **kwargs)
                finally:
                    if not rejected:
                        path.write_bytes(before)
        return Reader()
    with monkeypatch.context() as patch:
        patch.setattr(sources, 'adapter_for', adapter)
        services.load_dataset(ws, _ctx())
    assert rejected == [True]
    assert {r['Value1'] for r in ws.dataset.customer_loads.values()} == {'12.5'}
    result = services.convert(ws, _ctx(), None, True)
    control, _ = _txt_workspace(tmp_path / 'control', feeders=1)
    services.load_dataset(control, _ctx())
    services.convert(control, _ctx(), None, True)
    actual = next(ws.out_dir.glob('*.dgs')).read_bytes()
    assert actual == next(control.out_dir.glob('*.dgs')).read_bytes()
    assert ws.loaded_source_fingerprint == control.loaded_source_fingerprint
    assert ws.loaded_source_receipt['files']['loads']['sha256'] == ws.active_run().files['loads'].sha256
    assert hashlib.sha256(actual).hexdigest()


@pytest.mark.parametrize('group', [False, True])
def test_cambio_de_run_al_adquirir_guarda_no_convierte_otro_dataset(tmp_path, monkeypatch, group):
    """034:RF-20 — la guarda y el cuerpo consumen una captura única, aunque termine otra carga."""
    from contextlib import contextmanager
    from convertersmartgrid.web import services, source_runs

    ws, _ = _txt_workspace(tmp_path, feeders=1)
    services.load_dataset(ws, _ctx())
    old = ws.active_run()
    guard = source_runs.guarded_source_run
    changed = []
    @contextmanager
    def interleave(snapshot):
        with guard(snapshot) as held:
            if snapshot.run_id == old.run_id and not changed:
                changed.append(True)
                services.load_dataset(ws, _ctx())
                new = ws.active_run()
                path = new.files['loads'].path
                before = path.read_bytes()
                path.write_bytes(before.replace(b'12.5', b'22.5'))
            yield held
    monkeypatch.setattr(source_runs, 'guarded_source_run', interleave)
    with pytest.raises(services.UserError, match='SOURCE_SELECTION_CHANGED|SOURCE_RUN_MISMATCH'):
        if group:
            services.convert_group(ws, _ctx(), [services.feeder_rows(ws)[0]['feeder']], 'NO_PUBLICAR')
        else:
            services.convert(ws, _ctx(), None, True)
    assert ws.active_run_id != old.run_id
    assert not list(ws.out_dir.glob('*.dgs'))
    assert not list(ws.out_dir.glob('*manifest.json'))


@pytest.mark.parametrize('group', [False, True])
def test_cambio_justo_antes_publicar_no_escribe_en_run_nuevo_ni_repuebla_estado(tmp_path, monkeypatch, group):
    """034:RF-20 — el commit de publicación valida y actualiza bajo una exclusión breve."""
    from convertersmartgrid.web import services, source_runs

    ws, _ = _txt_workspace(tmp_path, feeders=1)
    mdb = tmp_path / 'existencia.mdb'
    mdb.write_bytes(b'solo existencia, no se abre Access')
    ws.set_input('mdb', mdb, origin='server')
    ws.options['input_mode'] = 'txt'
    services.load_dataset(ws, _ctx())
    old = ws.active_run()
    # Frontera equivalente al último require de c144; no sustituye escritor/lector.
    real = services._stamp_source_manifest if not group else services._informe_por_set
    changed = []
    def boundary(*args, **kwargs):
        if not changed:
            with ws.lock:
                ws.invalidate(); ws.options['input_mode'] = 'mdb'; ws.save()
            changed.append(source_runs.create_source_run(ws))
        return real(*args, **kwargs)
    monkeypatch.setattr(services, '_stamp_source_manifest' if not group else '_informe_por_set', boundary)
    with pytest.raises(services.UserError, match='SOURCE_SELECTION_CHANGED|SOURCE_RUN_MISMATCH'):
        if group:
            services.convert_group(ws, _ctx(), [services.feeder_rows(ws)[0]['feeder']], 'NO_DESVIAR')
        else:
            services.convert(ws, _ctx(), None, True)
    new = ws.active_run()
    assert new.mode == 'mdb' and new.run_id != old.run_id
    assert ws.dataset is None and not ws.conversions and not ws.groups
    assert not list((new.root / 'salida').glob('*'))
    assert list((old.root / 'salida').glob('*.dgs'))


def test_publicacion_breve_excluye_cambio_concurrente_y_conserva_recibo_capturado(tmp_path, monkeypatch):
    """034:RF-20 — otra petición espera solo al commit, sin desviar identidad ni destino."""
    import json
    import threading
    from convertersmartgrid.web import services, source_runs

    ws, _ = _txt_workspace(tmp_path, feeders=1)
    mdb = tmp_path / 'existencia.mdb'
    mdb.write_bytes(b'solo existencia')
    ws.set_input('mdb', mdb, origin='server')
    ws.options['input_mode'] = 'txt'
    services.load_dataset(ws, _ctx())
    old = ws.active_run()
    receipt = json.loads(json.dumps(ws.loaded_source_receipt))
    attempted, done = threading.Event(), threading.Event()
    actors, errors = [], []
    real = services._stamp_source_manifest

    def change():
        try:
            attempted.set()
            with ws.lock:
                ws.invalidate(); ws.options['input_mode'] = 'mdb'; ws.save()
            source_runs.create_source_run(ws)
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    def boundary(*args, **kwargs):
        actor = threading.Thread(target=change)
        actors.append(actor); actor.start()
        assert attempted.wait(5)
        assert not done.wait(.1), 'la transición concurrente no esperó al commit de publicación'
        return real(*args, **kwargs)

    monkeypatch.setattr(services, '_stamp_source_manifest', boundary)
    result = services.convert(ws, _ctx(), None, True)
    for actor in actors:
        actor.join(10)
        assert not actor.is_alive()
    assert not errors and done.is_set()
    assert result['summary']['ok'] == 1
    new = ws.active_run()
    assert new.mode == 'mdb' and new.run_id != old.run_id and ws.dataset is None
    assert not list((new.root / 'salida').glob('*'))
    manifest = json.loads((old.root / 'salida' / 'batch_manifest.json').read_text(encoding='utf-8'))
    assert manifest['source_run_id'] == old.run_id
    assert manifest['source_read_receipt'] == receipt


def test_conversion_larga_no_retiene_lock_http_y_aborta_commit_de_seleccion_obsoleta(tmp_path, monkeypatch):
    """065:RF-18; 034:RF-20 — el cerrojo breve no cubre el cálculo DGS."""
    import threading
    from convertersmartgrid.web import services
    from convertersmartgrid import batch

    ws, _ = _txt_workspace(tmp_path, feeders=1)
    services.load_dataset(ws, _ctx())
    original = batch.convert_selection
    completed = threading.Event()
    def converter(*args, **kwargs):
        def option_request():
            with ws.lock:
                ws.invalidate(); ws.options['input_mode'] = 'mdb'; ws.save()
            completed.set()
        actor = threading.Thread(target=option_request)
        actor.start(); actor.join(5)
        assert not actor.is_alive(), 'la conversión larga bloqueó una petición de opciones'
        assert completed.is_set()
        return original(*args, **kwargs)
    monkeypatch.setattr(batch, 'convert_selection', converter)
    with pytest.raises(services.UserError, match='SOURCE_SELECTION_CHANGED'):
        services.convert(ws, _ctx(), None, True)
    assert completed.is_set() and ws.dataset is None and not ws.conversions
