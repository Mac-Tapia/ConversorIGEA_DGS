"""065:RF-10 / 065:RF-12: espacios externos sin perder sesiones previas."""
import json
from pathlib import Path


def test_espacios_nuevos_fuera_del_codigo_y_antiguos_accesibles(tmp_path, monkeypatch):
    """065:RF-10 / 065:RF-12 — cambiar la raíz no abandona sesiones ni sus vínculos."""
    from convertersmartgrid.web import workspace
    root = tmp_path / 'codigo'
    (root / '.git').mkdir(parents=True)
    external = tmp_path / 'ejecucion'
    monkeypatch.delenv('CSG_WEB_DATA', raising=False)
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(external))
    monkeypatch.setattr(workspace, 'project_root', lambda: root)
    wid = 'a' * 16
    old = workspace.Workspace(id=wid, root=root / 'output' / 'web' / wid)
    old.save()
    original = (old.root / 'workspace.json').read_bytes()
    store = workspace.WorkspaceStore()
    assert not store.root.is_relative_to(root)
    assert store.get(wid).root == old.root
    assert wid in {r['id'] for r in store.list()}
    new = store.create()
    assert new.root.is_relative_to(external)
    assert (old.root / 'workspace.json').read_bytes() == original
    assert store.get(wid).vinculos_compartidos.parent == old.root.parent


def test_override_explicito_no_descubre_otros_espacios(tmp_path, monkeypatch):
    """065:RF-12 — una instancia aislada no descubre datos de otra sesión por omisión."""
    from convertersmartgrid.web import workspace
    root = tmp_path / 'codigo'
    monkeypatch.setattr(workspace, 'project_root', lambda: root)
    wid = 'b' * 16
    old = workspace.Workspace(id=wid, root=root / 'output' / 'web' / wid)
    old.save()
    monkeypatch.setenv('CSG_WEB_DATA', str(tmp_path / 'aislado'))
    store = workspace.WorkspaceStore()
    assert store.get(wid) is None
    assert store.list() == []


def test_modelos_y_episodios_heredados_siguen_disponibles(tmp_path, monkeypatch):
    """065:RF-12 — una raíz nueva de espacios no abandona al asistente ya entrenado."""
    from convertersmartgrid.web import workspace
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid import runtime_paths
    from convertersmartgrid.digital_twin.buffer import raiz_buffer
    root = tmp_path / 'codigo'
    (root / '.git').mkdir(parents=True)
    monkeypatch.setattr(workspace, 'project_root', lambda: root)
    # 002:RF-2: el asistente y el gemelo toman la raíz de runtime_paths, no de la web.
    monkeypatch.setattr(runtime_paths, 'raiz_programa', lambda: root)
    for variable in ('CSG_WEB_DATA', 'CSG_ASISTENTE_DATA', 'CSG_TWIN_DATA'):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    for component in ('_asistente', '_digital_twin'):
        (root / 'output' / 'web' / component).mkdir(parents=True)
    assert almacen.raiz() == root / 'output' / 'web' / '_asistente'
    assert raiz_buffer() == root / 'output' / 'web' / '_digital_twin'
    isolated = tmp_path / 'aislado'
    monkeypatch.setenv('CSG_WEB_DATA', str(isolated))
    assert almacen.raiz() == isolated / '_asistente'
    assert raiz_buffer() == isolated / '_digital_twin'


