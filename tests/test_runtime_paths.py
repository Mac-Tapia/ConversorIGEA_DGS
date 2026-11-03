"""065:RF-10 a RF-13: cachés, staging y temporales con custodia explícita."""
from pathlib import Path
import os
import json
import time

import pytest


@pytest.fixture(autouse=True)
def _restaurar_entorno():
    """La política cambia el proceso; una prueba no debe cambiar la siguiente."""
    previous = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(previous)


def _checkout(tmp_path):
    root = tmp_path / 'codigo'
    (root / '.git').mkdir(parents=True)
    return root


def test_raices_por_defecto_fuera_del_checkout(tmp_path):
    """065:RF-10 — ni el checkout ni su .worktrees alojan el scratch."""
    from convertersmartgrid.runtime_paths import rutas_runtime
    primary = _checkout(tmp_path)
    linked = primary / '.worktrees' / 'candidato'
    linked.mkdir(parents=True)
    git_dir = primary / '.git' / 'worktrees' / 'candidato'
    git_dir.mkdir(parents=True)
    (git_dir / 'commondir').write_text('../..', encoding='utf-8')
    (linked / '.git').write_text(f'gitdir: {git_dir.as_posix()}', encoding='utf-8')
    paths = rutas_runtime(linked, {'LOCALAPPDATA': str(tmp_path / 'local')})
    assert paths.checkout == linked.resolve()
    assert paths.primario == primary.resolve()
    assert not paths.runtime.is_relative_to(primary)
    assert not paths.cache.is_relative_to(primary)
    assert not paths.temporales.is_relative_to(primary)


@pytest.mark.parametrize('variable', ['CSG_RUNTIME_HOME', 'CSG_CACHE_HOME'])
def test_rechaza_override_dentro_de_codigo(tmp_path, variable):
    """065:RF-10 — un override no permite volver a guardar scratch bajo el código."""
    from convertersmartgrid.runtime_paths import rutas_runtime
    primary = _checkout(tmp_path)
    with pytest.raises(ValueError, match='fuera'):
        rutas_runtime(primary, {variable: str(primary / 'output' / 'tmp')})


def test_configurar_entorno_propaga_cache_y_temp(tmp_path, monkeypatch):
    """065:RF-10 — hijos y librerías heredan las mismas raíces externas."""
    from convertersmartgrid.runtime_paths import configurar_entorno
    primary = _checkout(tmp_path)
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    paths = configurar_entorno(primary)
    for name in ('TEMP', 'TMP', 'TMPDIR'):
        assert Path(os.environ[name]) == paths.temporales
        assert Path(os.environ[name]).is_dir()
    for name in ('HF_HOME', 'TORCH_HOME', 'RUFF_CACHE_DIR', 'npm_config_cache'):
        assert Path(os.environ[name]).is_relative_to(paths.cache)


def test_staging_en_volumen_de_destino(tmp_path):
    """065:RF-11 — staging externo conserva el volumen de publicación."""
    from convertersmartgrid.runtime_paths import rutas_runtime
    primary = _checkout(tmp_path)
    paths = rutas_runtime(primary, {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime')})
    destination = primary / 'output' / 'modelo.json'
    folder = paths.staging_para(destination)
    assert folder.anchor == destination.anchor
    assert not folder.is_relative_to(primary)


def test_temporal_propio_limpia_en_error_y_no_toca_original(tmp_path):
    """065:RF-12 — una excepción no conserva scratch ni borra la entrada."""
    from convertersmartgrid.runtime_paths import rutas_runtime, temporal_administrado
    primary = _checkout(tmp_path)
    original = primary / 'fuente.txt'
    original.write_text('original', encoding='utf-8')
    paths = rutas_runtime(primary, {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime')})
    with pytest.raises(RuntimeError):
        with temporal_administrado(paths, propietario='trabajo-1') as scratch:
            (scratch / 'parcial').write_text('derivado', encoding='utf-8')
            assert (scratch / 'owner.json').is_file()
            raise RuntimeError('interrumpido')
    assert not scratch.exists()
    assert original.read_text(encoding='utf-8') == 'original'


def test_reconciliar_solo_terminal_vencido_sin_referencias(tmp_path):
    """065:RF-13 — las referencias y estados activos impiden retirar restos."""
    from convertersmartgrid.runtime_paths import rutas_runtime, reconciliar_temporales
    primary = _checkout(tmp_path)
    paths = rutas_runtime(primary, {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime')})
    for name, status in [('terminal', 'terminado'), ('activo', 'activo'), ('referido', 'terminado')]:
        folder = paths.temporales / ('csg-job-' + name)
        folder.mkdir(parents=True)
        (folder / 'owner.json').write_text(json.dumps({
            'version': 1, 'proyecto': paths.identidad, 'propietario': name,
            'estado': status, 'pid': os.getpid(), 'actualizado': time.time() - 10 * 86400,
        }), encoding='utf-8')
    unknown = paths.temporales / 'mis_documentos'
    unknown.mkdir()
    dry = reconciliar_temporales(paths, propietarios_vigentes={'referido'}, simular=True)
    assert {Path(p).name for p in dry['seleccionados']} == {'csg-job-terminal'}
    assert (paths.temporales / 'csg-job-terminal').exists()
    result = reconciliar_temporales(paths, propietarios_vigentes={'referido'}, simular=False)
    assert len(result['retirados']) == 1
    assert not (paths.temporales / 'csg-job-terminal').exists()
    assert (paths.temporales / 'csg-job-activo').exists()
    assert (paths.temporales / 'csg-job-referido').exists()
    assert unknown.exists()


def test_publicacion_json_no_crea_tmp_en_destino_y_conserva_anterior(tmp_path, monkeypatch):
    """065:RF-10 / 065:RF-11 — incluso fallando replace, no hay parciales junto al código."""
    from convertersmartgrid.util import write_json_atomic
    target = tmp_path / 'codigo' / 'salida.json'
    target.parent.mkdir()
    target.write_text('{"anterior": true}', encoding='utf-8')
    replace = Path.replace
    observed = []
    def fail(source, destination):
        observed.append(source)
        assert source.parent != target.parent
        raise OSError('publicación fallida')
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError, match='publicación fallida'):
        write_json_atomic(target, {'nuevo': True})
    assert json.loads(target.read_text(encoding='utf-8')) == {'anterior': True}
    assert list(target.parent.iterdir()) == [target]
    assert observed and not observed[0].exists()


def test_cleanup_readonly_conserva_el_error_original(tmp_path):
    """065:RF-12 — copy2 de una fuente readonly no deja un stage ni oculta el fallo."""
    import stat
    from convertersmartgrid.runtime_paths import rutas_runtime, temporal_administrado
    paths = rutas_runtime(_checkout(tmp_path), {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime')})
    with pytest.raises(RuntimeError, match='fallo original'):
        with temporal_administrado(paths, propietario='readonly') as scratch:
            path = scratch / 'original_copiado'
            path.write_bytes(b'conservar fuente')
            path.chmod(stat.S_IREAD)
            raise RuntimeError('fallo original')
    assert not scratch.exists()


def test_publicar_owner_json_no_reemplaza_el_manifiesto_de_custodia(tmp_path, monkeypatch):
    """065:RF-12 / 065:RF-13 — un artefacto owner.json no es el dueño de su staging."""
    from convertersmartgrid.runtime_paths import rutas_runtime
    from convertersmartgrid.util import write_json_atomic
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    target = tmp_path / 'datos' / 'owner.json'
    write_json_atomic(target, {'propietario': 'dato del modelo'})
    paths = rutas_runtime()
    assert json.loads(target.read_text(encoding='utf-8')) == {'propietario': 'dato del modelo'}
    assert not list(paths.staging_para(target).glob('csg-job-*'))


def test_reconfigurar_cache_actualiza_solo_rutas_generadas(tmp_path, monkeypatch):
    """065:RF-10 — reconfigurar una raíz no retiene cachés automáticas del arranque previo."""
    from convertersmartgrid.runtime_paths import configurar_entorno
    root = _checkout(tmp_path)
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache_1'))
    for name in ('HF_HOME', 'TORCH_HOME', 'RUFF_CACHE_DIR', 'npm_config_cache'):
        monkeypatch.delenv(name, raising=False)
    configurar_entorno(root)
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache_2'))
    custom = tmp_path / 'mi_torch'
    monkeypatch.setenv('TORCH_HOME', str(custom))
    paths = configurar_entorno(root)
    assert Path(os.environ['HF_HOME']).is_relative_to(paths.cache)
    assert Path(os.environ['TORCH_HOME']) == custom


def test_reconciliar_crash_exige_pid_muerto_y_edad(tmp_path):
    """065:RF-13 — un crash comprobado vence; PID vivo nunca se supone abandonado."""
    import psutil
    from convertersmartgrid.runtime_paths import rutas_runtime, reconciliar_temporales
    paths = rutas_runtime(_checkout(tmp_path), {'CSG_RUNTIME_HOME': str(tmp_path / 'runtime')})
    dead = next(pid for pid in range(2147483647, 2147483600, -1) if not psutil.pid_exists(pid))
    for name, pid in [('muerto', dead), ('vivo', os.getpid())]:
        folder = paths.temporales / ('csg-job-' + name)
        folder.mkdir(parents=True)
        (folder / 'owner.json').write_text(json.dumps({
            'version': 1, 'proyecto': paths.identidad, 'propietario': name,
            'estado': 'activo', 'pid': pid, 'actualizado': time.time() - 8 * 86400,
        }), encoding='utf-8')
    result = reconciliar_temporales(paths, simular=False)
    assert {Path(p).name for p in result['retirados']} == {'csg-job-muerto'}
    assert (paths.temporales / 'csg-job-vivo').is_dir()


def test_catalogo_de_empresa_se_prepara_fuera_de_su_carpeta(tmp_path, monkeypatch):
    """065:RF-10, 065:RF-11 — el catálogo nuevo no deja borrador «.tmp» junto a él, ni si falla al guardar."""
    import openpyxl
    from convertersmartgrid.catalog import asegurar_catalogo_empresa
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    carpeta = tmp_path / 'input' / 'empresas' / 'E'
    destino = asegurar_catalogo_empresa(carpeta / 'catalogo_parametros.xlsx')
    assert list(carpeta.iterdir()) == [destino]
    assert openpyxl.load_workbook(destino).sheetnames
    otro = tmp_path / 'input' / 'empresas' / 'F'
    monkeypatch.setattr(openpyxl.Workbook, 'save', lambda *_: (_ for _ in ()).throw(OSError('disco lleno')))
    with pytest.raises(OSError, match='disco lleno'):
        asegurar_catalogo_empresa(otro / 'catalogo_parametros.xlsx')
    assert list(otro.iterdir()) == []
    assert not list((tmp_path / 'runtime').rglob('csg-job-*'))


def test_retencion_diaria_incluye_temporales_externos_propios(tmp_path, monkeypatch):
    """065:RF-13 / 062:RF-1 — la política tiene consumidor periódico, no solo una utilidad."""
    from convertersmartgrid.runtime_paths import rutas_runtime
    from convertersmartgrid.web.workspace import WorkspaceStore
    from convertersmartgrid.web.jobs import JobManager
    from convertersmartgrid.web.retencion import RetencionDiaria
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    paths = rutas_runtime()
    folder = paths.temporales / 'csg-job-terminal'
    folder.mkdir(parents=True)
    (folder / 'owner.json').write_text(json.dumps({
        'version': 1, 'proyecto': paths.identidad, 'propietario': 'viejo',
        'pid': os.getpid(), 'estado': 'terminado', 'actualizado': time.time() - 9 * 86400,
    }), encoding='utf-8')
    jobs = JobManager(lambda *args: None)
    try:
        result = RetencionDiaria(WorkspaceStore(tmp_path / 'datos'), jobs).revisar_si_vence()
        assert result['estado'] == 'completada'
        assert not folder.exists()
        assert any(str(folder) in r['retirados'] for r in result['temporales_externos'])
    finally:
        jobs.shutdown()
