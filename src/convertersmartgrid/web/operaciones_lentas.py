"""Trabajos de descarga con cuota y temporales propios (spec 065)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import time
import zipfile

from ..runtime_paths import rutas_runtime, staging_publicacion


def presupuesto(variable: str, defecto: int) -> int:
    """Un límite inválido no desactiva silenciosamente el presupuesto."""
    text = os.environ.get(variable, str(defecto))
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError(f'{variable} debe ser un entero positivo en bytes.') from exc
    if value <= 0:
        raise ValueError(f'{variable} debe ser un entero positivo en bytes.')
    return value


def preparar_zip(ws_id: str, root: Path, seleccion: tuple[str, ...], ctx) -> dict:
    """Fija la raíz al admitir el trabajo y comprime por bloques cancelables."""
    limit = presupuesto('CSG_ARCHIVE_MAX_BYTES', 32 * 1024 ** 3)
    policy = rutas_runtime()
    destination = policy.runtime / 'descargas' / ws_id / ('csg-job-' + ctx.job.id)
    destination.mkdir(parents=True, exist_ok=False)
    marker = destination / 'owner.json'
    owner = {'version': 1, 'proyecto': policy.identidad, 'propietario': ctx.job.id,
             'pid': os.getpid(), 'estado': 'activo', 'actualizado': time.time()}
    marker.write_text(json.dumps(owner), encoding='utf-8')
    try:
        files = []
        source_root = root.resolve()
        for folder, dirs, names in os.walk(source_root, followlinks=False):
            ctx.check_cancel()
            dirs[:] = [d for d in dirs if not d.startswith('.csg-stage-')
                       and not Path(folder, d).is_symlink() and not Path(folder, d).is_junction()]
            for name in names:
                path = Path(folder, name)
                if path.is_symlink() or not path.resolve().is_relative_to(source_root):
                    raise ValueError('La salida contiene una redirección; no se incorpora al ZIP.')
                relative = path.relative_to(source_root).as_posix()
                if seleccion and not any(relative == f'{f}.dgs' or relative.startswith((f'{f}_', f'{f}/'))
                                         for f in seleccion):
                    continue
                files.append((path, relative))
                if len(files) > 100000:
                    raise ValueError('La descarga supera la cuota de 100000 archivos por trabajo.')
        if not files:
            raise ValueError('No hay ficheros de salida que descargar.')
        total = 0
        final = destination / 'salida.zip'
        with staging_publicacion(final) as temporary:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for index, (path, relative) in enumerate(files):
                    ctx.check_cancel()
                    with path.open('rb') as source, archive.open(relative, 'w', force_zip64=True) as target:
                        while block := source.read(1024 * 1024):
                            ctx.check_cancel()
                            total += len(block)
                            if total > limit:
                                raise ValueError('La descarga supera la cuota de almacenamiento configurada.')
                            target.write(block)
                    ctx.progress(index + 1, len(files), relative)
            ctx.check_cancel()
            # temporal_administrado usa la raíz runtime del mismo volumen que descargas.
            temporary.replace(final)
        owner.update(estado='terminado', actualizado=time.time())
        marker.write_text(json.dumps(owner), encoding='utf-8')
        # Ruta interna, no parte del JSON público del trabajo.
        ctx.job._archivo_zip = final
        name = f'convertersmartgrid_{"_".join(seleccion[:3]) if seleccion else "salida"}.zip'
        return {'download': f'/api/workspaces/{ws_id}/outputs.zip?job={ctx.job.id}',
                'nombre': name, 'archivos': len(files), 'bytes': final.stat().st_size}
    except BaseException:
        retirar_zip(destination / 'salida.zip', ctx.job.id, ws_id)
        raise


def retirar_zip(path: Path, job_id: str, ws_id: str) -> None:
    """Retira solo la carpeta externa identificada de este trabajo."""
    policy = rutas_runtime()
    expected = (policy.runtime / 'descargas' / ws_id / ('csg-job-' + job_id)).resolve()
    if path.parent.resolve() != expected or not expected.is_relative_to(policy.runtime.resolve()):
        raise ValueError('La descarga no pertenece al trabajo.')
    if expected.is_symlink() or expected.is_junction():
        raise ValueError('La carpeta de descarga está redirigida.')
    marker = expected / 'owner.json'
    if expected.is_dir() and marker.is_file():
        owner = json.loads(marker.read_text(encoding='utf-8'))
        if owner.get('propietario') != job_id or owner.get('proyecto') != policy.identidad:
            raise ValueError('El propietario de la descarga no coincide.')
        shutil.rmtree(expected)
