"""Raíces externas de ejecución y custodia de temporales (spec 065).

Un worktree bajo .worktrees no convierte a su padre en un almacén externo: se
resuelve también el checkout primario antes de elegir staging y limpiar scratch.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time
from typing import Iterator, Mapping
import uuid


def _primario(checkout: Path) -> Path:
    marker = checkout / '.git'
    if marker.is_file():
        text = marker.read_text(encoding='utf-8').strip()
        if text.startswith('gitdir:'):
            gitdir = (checkout / text.partition(':')[2].strip()).resolve()
            common = gitdir / 'commondir'
            if common.is_file():
                return (gitdir / common.read_text(encoding='utf-8').strip()).resolve().parent
    return checkout


def _externa(path: Path, checkout: Path, primario: Path) -> Path:
    absolute = path.expanduser().resolve()
    if any(absolute == root or absolute.is_relative_to(root) for root in (checkout, primario)):
        raise ValueError(f'La raíz temporal debe quedar fuera del código: {absolute}')
    return absolute


@dataclass(frozen=True)
class RutasRuntime:
    checkout: Path
    primario: Path
    identidad: str
    runtime: Path
    cache: Path
    temporales: Path

    def staging_para(self, destino: Path) -> Path:
        """Publicar por rename exige el mismo volumen, también en Windows."""
        destination = destino.resolve()
        for base in (self.runtime, self.cache.parent):
            if os.path.normcase(destination.anchor) == os.path.normcase(base.anchor):
                return base / 'staging'
        raise ValueError('Configure una raíz runtime o caché en el volumen del destino para publicar.')


def rutas_runtime(checkout: Path | None = None,
                  environ: Mapping[str, str] | None = None) -> RutasRuntime:
    """Calcula rutas sin crear carpetas ni cambiar el entorno del llamador."""
    env = os.environ if environ is None else environ
    root = (checkout or Path(__file__).resolve().parents[2]).resolve()
    primary = _primario(root)
    spelling = root.as_posix().casefold() if os.name == 'nt' else root.as_posix()
    identity = hashlib.sha256(spelling.encode('utf-8')).hexdigest()[:16]
    default_runtime = primary.parent / '.convertersmartgrid-runtime' / identity
    runtime = _externa(Path(env.get('CSG_RUNTIME_HOME') or default_runtime), root, primary)
    local = Path(env.get('LOCALAPPDATA') or env.get('XDG_CACHE_HOME') or Path.home() / '.cache')
    cache = _externa(Path(env.get('CSG_CACHE_HOME') or local / 'ConverterSmartGrid' / identity / 'cache'), root, primary)
    temporary = _externa(Path(env.get('CSG_TEMP_HOME') or runtime / 'tmp'), root, primary)
    return RutasRuntime(root, primary, identity, runtime, cache, temporary)


def configurar_entorno(checkout: Path | None = None) -> RutasRuntime:
    """Configura este proceso y sus hijos antes de importar motores y librerías."""
    try:
        anteriores = json.loads(os.environ.get('CSG_RUTAS_AUTOMATICAS', '{}'))
    except ValueError:
        anteriores = {}
    if not isinstance(anteriores, dict):
        anteriores = {}
    inputs = dict(os.environ)
    for name in ('CSG_RUNTIME_HOME', 'CSG_CACHE_HOME', 'CSG_TEMP_HOME'):
        if inputs.get(name) == anteriores.get(name):
            inputs.pop(name, None)
    paths = rutas_runtime(checkout, inputs)
    paths.temporales.mkdir(parents=True, exist_ok=True)
    paths.cache.mkdir(parents=True, exist_ok=True)
    os.environ.update(CSG_RUNTIME_HOME=str(paths.runtime), CSG_CACHE_HOME=str(paths.cache),
                      CSG_TEMP_HOME=str(paths.temporales), PYTHONDONTWRITEBYTECODE='1')
    for name in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[name] = str(paths.temporales)
    automaticas = {name: str(value) for name, value in {
        'CSG_RUNTIME_HOME': paths.runtime, 'CSG_CACHE_HOME': paths.cache,
        'CSG_TEMP_HOME': paths.temporales,
    }.items() if not inputs.get(name)}
    for name, relative in {
        'PYTHONPYCACHEPREFIX': 'python', 'RUFF_CACHE_DIR': 'ruff',
        'npm_config_cache': 'npm', 'TORCH_HOME': 'torch',
        'TORCHINDUCTOR_CACHE_DIR': 'torchinductor', 'TRITON_CACHE_DIR': 'triton',
        'HF_HOME': 'huggingface', 'HF_HUB_CACHE': 'huggingface/hub',
    }.items():
        override = os.environ.get(name)
        if override == anteriores.get(name):
            override = None
        value = _externa(Path(override or paths.cache / relative), paths.checkout, paths.primario)
        os.environ[name] = str(value)
        if not override:
            automaticas[name] = str(value)
    os.environ['CSG_RUTAS_AUTOMATICAS'] = json.dumps(automaticas)
    sys.dont_write_bytecode = True
    tempfile.tempdir = None
    return paths


def _retirar_propio(folder: Path) -> None:
    """copy2 conserva readonly: solo se cambia el atributo dentro de este scratch."""
    root = folder.resolve()

    def permitir_borrado(funcion, nombre, exc):
        path = Path(nombre)
        if (not isinstance(exc, PermissionError) or path.is_symlink() or path.is_junction()
                or not path.resolve().is_relative_to(root)):
            raise exc
        path.chmod(stat.S_IWRITE | stat.S_IREAD)
        funcion(path)

    shutil.rmtree(root, onexc=permitir_borrado)


@contextmanager
def temporal_administrado(paths: RutasRuntime | None = None, *, propietario: str) -> Iterator[Path]:
    """Cada trabajo limpia solo su directorio y conserva un manifiesto si cae el proceso."""
    policy = paths or rutas_runtime()
    policy.temporales.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='csg-job-', dir=policy.temporales)).resolve()
    nonce = uuid.uuid4().hex
    metadata = {'version': 1, 'proyecto': policy.identidad, 'propietario': propietario,
                'pid': os.getpid(), 'nonce': nonce, 'estado': 'activo', 'actualizado': time.time()}
    marker = folder / 'owner.json'
    marker.write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    try:
        yield folder
    finally:
        # No seguir una carpeta o un manifiesto sustituidos durante el trabajo.
        if (folder.is_dir() and not folder.is_symlink() and not folder.is_junction()
                and folder.parent == policy.temporales.resolve() and not marker.is_symlink()):
            current = json.loads(marker.read_text(encoding='utf-8')) if marker.is_file() else {}
            if current.get('nonce') == nonce:
                current.update(estado='terminado', actualizado=time.time())
                marker.write_text(json.dumps(current, ensure_ascii=False), encoding='utf-8')
                _retirar_propio(folder)


@contextmanager
def staging_publicacion(destino: Path) -> Iterator[Path]:
    """Entrega una ruta privada inexistente fuera del código y en el volumen destino."""
    policy = rutas_runtime()
    stage = policy.staging_para(destino)
    with temporal_administrado(replace(policy, temporales=stage),
                               propietario=f'publicacion:{destino.name}') as folder:
        # El artefacto puede llamarse owner.json: nunca reemplaza el manifiesto.
        yield folder / ('contenido-' + destino.name)


def reconciliar_temporales(paths: RutasRuntime | None = None, *,
                          propietarios_vigentes: set[str] | None = None,
                          simular: bool = True, ahora: float | None = None,
                          edad_minima_s: float = 7 * 86400) -> dict:
    """Selecciona restos terminales vencidos; desconocidos y activos se conservan.

    No basta con encontrar un nombre tmp. Un crash deja estado activo: requiere
    reconciliar su dueño antes de marcarlo terminal, no se supone por su edad.
    """
    policy = paths or rutas_runtime()
    active = propietarios_vigentes or set()
    now = time.time() if ahora is None else ahora
    selected, removed, errors = [], [], []
    root = policy.temporales.resolve()
    if not root.is_dir():
        return {'seleccionados': selected, 'retirados': removed, 'errores': errors, 'simulacion': simular}
    for child in root.iterdir():
        if not re.fullmatch(r'csg-job-[A-Za-z0-9_-]+', child.name):
            continue
        marker = child / 'owner.json'
        if (not child.is_dir() or child.is_symlink() or child.is_junction()
                or child.resolve().parent != root or marker.is_symlink() or not marker.is_file()):
            continue
        try:
            meta = json.loads(marker.read_text(encoding='utf-8'))
            owner = meta.get('propietario')
            updated = meta.get('actualizado')
            state = meta.get('estado')
            if state == 'activo' and type(meta.get('pid')) is int and meta['pid'] > 0:
                # pid_exists es de solo lectura en Windows; os.kill(pid, 0) allí
                # no tiene el contrato POSIX y no debe usarse para esta comprobación.
                try:
                    import psutil
                except ImportError:
                    continue
                if not psutil.pid_exists(meta['pid']):
                    state = 'abandonado'
            if (meta.get('version') != 1 or meta.get('proyecto') != policy.identidad
                    or state not in {'terminado', 'cancelado', 'abandonado'}
                    or not isinstance(owner, str) or not owner or owner in active
                    or not isinstance(updated, (int, float)) or not 0 <= updated < now - edad_minima_s):
                continue
            # Aunque rmtree no siga symlinks, la política no retira árboles redirigidos.
            redirected = any(Path(base, name).is_symlink() or Path(base, name).is_junction()
                             for base, dirs, files in os.walk(child, followlinks=False)
                             for name in (*dirs, *files))
            if redirected:
                continue
            selected.append(str(child))
            if not simular:
                # Releer evita borrar un dueño reactivado entre selección y ejecución.
                if json.loads(marker.read_text(encoding='utf-8')) != meta:
                    continue
                if child.resolve().parent != root:
                    continue
                _retirar_propio(child)
                removed.append(str(child))
        except (OSError, ValueError, TypeError) as exc:
            errors.append({'ruta': str(child), 'motivo': str(exc)})
    return {'seleccionados': selected, 'retirados': removed, 'errores': errors, 'simulacion': simular}


def revisar_temporales_runtime(*, ahora: float | None = None) -> list[dict]:
    """Reconciliación periódica de scratch/staging y descargas, con la misma custodia."""
    policy = rutas_runtime()
    roots = {policy.temporales, policy.runtime / 'staging', policy.cache.parent / 'staging'}
    downloads = policy.runtime / 'descargas'
    if downloads.is_dir() and not downloads.is_symlink() and not downloads.is_junction():
        roots.update(p for p in downloads.iterdir() if re.fullmatch('[a-f0-9]{16}', p.name)
                     and p.is_dir() and not p.is_symlink() and not p.is_junction())
    results = []
    for folder in sorted(roots):
        if folder.is_symlink() or folder.is_junction():
            results.append({'retirados': [], 'errores': [{'ruta': str(folder), 'motivo': 'raíz redirigida'}]})
            continue
        result = reconciliar_temporales(replace(policy, temporales=folder), simular=False, ahora=ahora)
        results.append({'raiz': str(folder), **result})
    return results
