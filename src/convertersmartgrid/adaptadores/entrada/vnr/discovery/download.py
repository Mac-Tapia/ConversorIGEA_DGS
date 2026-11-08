"""Gestor de descargas y manejo seguro de archivos (secciones D9–D11, E3).

Descarga con reintentos, staging externo, renombre atómico, SHA-256 y
``manifest.json``. La extracción de archivos rechaza rutas absolutas y recorrido
``../``, y separa la detección de formato de la extracción.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from convertersmartgrid.salidas_red import motivo_apagada, salida_permitida
from convertersmartgrid.util import importar_opcional, sha256_file, write_json_atomic
from convertersmartgrid.runtime_paths import rutas_runtime, staging_publicacion, temporal_administrado


class DownloadError(RuntimeError):
    pass


class DownloadCancelled(DownloadError):
    """La cancelación cooperativa no es un error transitorio de red."""


class DownloadQuotaExceeded(DownloadError):
    """Un recurso fuera de presupuesto no debe descargarse otra vez."""


class ArchiveSecurityError(DownloadError):
    pass


def preparar_unrar() -> None:
    """080:RF-23, RF-24: deja listo el extractor de RAR, o dice que falta.

    WinRAR no se añade al PATH al instalarse, y «rarfile» solo busca allí: en esta máquina,
    con WinRAR instalado, todo RAR oficial se daba por inválido (2026-11-02).
    """
    rarfile = importar_opcional('rarfile', DownloadError(
        'Para leer un paquete RAR falta el driver opcional «rarfile» (ver requirements-drivers.txt).'))
    candidatos = [os.environ.get('CSG_UNRAR'), shutil.which('unrar')]
    for variable in ('ProgramFiles', 'ProgramFiles(x86)'):
        if os.environ.get(variable):
            candidatos.append(str(Path(os.environ[variable]) / 'WinRAR' / 'UnRAR.exe'))
    for candidato in candidatos:
        if candidato and Path(candidato).is_file():
            rarfile.UNRAR_TOOL = candidato
            try:
                rarfile.tool_setup(force=True)
                return
            except rarfile.RarCannotExec:
                continue
    try:
        rarfile.tool_setup(force=True)
    except rarfile.RarCannotExec as exc:
        raise DownloadError(
            'Falta un extractor de RAR: instale WinRAR o indique su UnRAR.exe en CSG_UNRAR.'
        ) from exc


@dataclass
class DownloadManifest:
    publication_id: str
    company: str
    period: str
    source_url: str
    retrieved_at: str
    http_status: int
    content_type: str
    bytes: int
    sha256: str
    archive_test: str = 'N/A'
    extract_status: str = 'NOT_EXTRACTED'

    def as_dict(self) -> dict:
        return {
            'publication_id': self.publication_id,
            'company': self.company,
            'period': self.period,
            'source_url': self.source_url,
            'retrieved_at': self.retrieved_at,
            'http_status': self.http_status,
            'content_type': self.content_type,
            'bytes': self.bytes,
            'sha256': self.sha256,
            'archive_test': self.archive_test,
            'extract_status': self.extract_status,
        }


class DownloadManager:
    """Descarga fiable con caché, verificación y manifiesto."""

    def __init__(
        self,
        cache_dir: Path | str,
        *,
        temp_dir: Path | str | None = None,
        retries: int = 3,
        connect_timeout_s: float = 20,
        read_timeout_s: float = 180,
        max_file_size_bytes: int = 4096 * 1024 * 1024,
        verify_archive: bool = True,
        allowed_hosts: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.temp_dir = Path(temp_dir).resolve() if temp_dir is not None else None
        self.retries = retries
        self.connect_timeout_s = connect_timeout_s
        self.read_timeout_s = read_timeout_s
        self.max_file_size_bytes = max_file_size_bytes
        self.verify_archive = verify_archive
        self.allowed_hosts = tuple(host.lower().strip('.') for host in (allowed_hosts or ()))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ descarga
    def download(
        self,
        url: str,
        destination: Path | str,
        *,
        publication_id: str = '',
        company: str = '',
        period: str = '',
        force: bool = False,
        on_progress: Callable[[int, int | None], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> DownloadManifest:
        if cancelled is not None and cancelled():
            raise DownloadCancelled('Descarga cancelada.')
        self._validate_url(url)
        destination = Path(destination)
        # 086:RF-22: el paquete ya descargado se puede usar; bajarlo es lo que no sale.
        if not salida_permitida('vnr_oficial') and (force or not destination.is_file()):
            raise DownloadError(motivo_apagada('vnr_oficial'))
        requests = importar_opcional('requests', DownloadError(
            'La descarga necesita la dependencia «requests» (ver requirements.txt '
            'y `python -m vnr_etl doctor`).'))
        destination = Path(destination)
        if self.verify_archive and destination.suffix.lower() == '.rar':
            preparar_unrar()  # Antes de bajar cientos de MB que no se podrían verificar (080:RF-24).
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.is_file() and not force:
            return self._manifest_for_existing(destination, url, publication_id, company, period)

        if self.temp_dir is None:
            contexto = staging_publicacion(destination)
        else:
            # La ruta explícita conserva el contrato, con las mismas fronteras del runtime.
            policy = rutas_runtime(environ={**os.environ, 'CSG_RUNTIME_HOME': str(self.temp_dir)})
            target = destination.resolve()
            origen_existente = next(p for p in (self.temp_dir, *self.temp_dir.parents) if p.exists())
            destino_existente = next(p for p in (target, *target.parents) if p.exists())
            if (os.path.normcase(self.temp_dir.anchor) != os.path.normcase(target.anchor)
                    or origen_existente.stat().st_dev != destino_existente.stat().st_dev):
                raise ValueError('El temporal de descarga debe estar en el volumen del destino.')
            contexto = temporal_administrado(replace(policy, temporales=self.temp_dir),
                                             propietario=f'descarga:{destination.name}')
        with contexto as staging:
            part = staging if self.temp_dir is None else staging / destination.name
            last_error: Exception | None = None
            def progress(written, total):
                if cancelled is not None and cancelled():
                    raise DownloadCancelled('Descarga cancelada.')
                if on_progress is not None:
                    on_progress(written, total)

            for attempt in range(1, self.retries + 1):
                try:
                    progress(0, None)
                    content_type = self._stream(requests, url, part, on_progress=progress)
                    if cancelled is not None and cancelled():
                        raise DownloadCancelled('Descarga cancelada.')
                    if self.max_file_size_bytes and part.stat().st_size > self.max_file_size_bytes:
                        part.unlink(missing_ok=True)
                        raise DownloadQuotaExceeded(
                            f'El fichero supera el tamaño máximo de '
                            f'{self.max_file_size_bytes / (1024 * 1024):.0f} MB.'
                        )
                    manifest = self._finalize(
                        part, destination, url, publication_id, company, period,
                        content_type=content_type,
                    )
                    self._write_manifest(destination, manifest)
                    return manifest
                except (DownloadCancelled, DownloadQuotaExceeded):
                    raise
                except Exception as exc:  # noqa: BLE001 - reintentos con backoff
                    last_error = exc
                    part.unlink(missing_ok=True)
                    if attempt < self.retries:
                        until = time.monotonic() + 2 ** attempt
                        while time.monotonic() < until:
                            if cancelled is not None and cancelled():
                                raise DownloadCancelled('Descarga cancelada.')
                            time.sleep(min(.1, max(0, until - time.monotonic())))
            raise DownloadError(f'Descarga fallida de {url}: {last_error}')

    def _stream(self, requests, url: str, part: Path, *,
                on_progress: Callable[[int, int | None], None] | None) -> str:
        headers = {}
        resume_at = part.stat().st_size if part.is_file() else 0
        if resume_at:
            headers['Range'] = f'bytes={resume_at}-'
        with requests.get(
            url, stream=True, timeout=(self.connect_timeout_s, self.read_timeout_s),
            headers=headers,
        ) as response:
            self._validate_url(getattr(response, 'url', url))
            if response.status_code in (200, 206):
                content_type = str(response.headers.get('Content-Type') or '').split(';', 1)[0].lower()
                if content_type in ('application/pdf', 'text/html'):
                    raise DownloadError(
                        f'El recurso respondió {content_type}; no es un paquete de datos VNR-GIS.'
                    )
                mode = 'ab' if response.status_code == 206 else 'wb'
                total = response.headers.get('Content-Length')
                total_int = int(total) if total and total.isdigit() else None
                initial = resume_at if mode == 'ab' else 0
                if self.max_file_size_bytes and total_int is not None and initial + total_int > self.max_file_size_bytes:
                    raise DownloadQuotaExceeded('El fichero supera el tamaño máximo de descarga configurado.')
                written = 0
                with part.open(mode) as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        if self.max_file_size_bytes and initial + written + len(chunk) > self.max_file_size_bytes:
                            raise DownloadQuotaExceeded('El fichero supera el tamaño máximo de descarga configurado.')
                        fh.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(written, total_int)
                return content_type
            else:
                raise DownloadError(f'HTTP {response.status_code} para {url}')

    def _finalize(self, part: Path, destination: Path, url: str,
                  publication_id: str, company: str, period: str,
                  content_type: str = '') -> DownloadManifest:
        digest = sha256_file(part)
        archive_test = 'N/A'
        if self.verify_archive and destination.suffix.lower() in ('.zip', '.rar'):
            if destination.suffix.lower() == '.zip':
                try:
                    with zipfile.ZipFile(part) as zf:
                        bad_member = zf.testzip()
                    if bad_member is not None:
                        raise DownloadError(f'El archivo ZIP está corrupto: {bad_member}')
                    archive_test = 'PASS'
                except zipfile.BadZipFile as exc:
                    raise DownloadError('El archivo ZIP descargado no es válido.') from exc
            else:
                try:
                    import rarfile
                except ImportError as exc:
                    raise DownloadError(
                        'No se puede verificar el archivo RAR sin «rarfile».'
                    ) from exc
                try:
                    with rarfile.RarFile(part) as rf:
                        bad_member = rf.testrar()
                    if bad_member is not None:
                        raise DownloadError(f'El archivo RAR está corrupto: {bad_member}')
                    archive_test = 'PASS'
                except rarfile.Error as exc:
                    raise DownloadError('El archivo RAR descargado no es válido.') from exc
        # Renombre atómico: nunca queda un fichero a medias como si fuera válido.
        os.replace(part, destination)
        return DownloadManifest(
            publication_id=publication_id,
            company=company,
            period=period,
            source_url=url,
            retrieved_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            http_status=200,
            content_type=content_type,
            bytes=destination.stat().st_size,
            sha256=digest,
            archive_test=archive_test,
        )

    def _manifest_for_existing(self, destination: Path, url: str,
                               publication_id: str, company: str, period: str) -> DownloadManifest:
        return DownloadManifest(
            publication_id=publication_id,
            company=company,
            period=period,
            source_url=url,
            retrieved_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            http_status=200,
            content_type='',
            bytes=destination.stat().st_size,
            sha256=sha256_file(destination),
            archive_test='N/A',
        )

    def _write_manifest(self, destination: Path, manifest: DownloadManifest) -> None:
        path = destination.with_suffix(destination.suffix + '.manifest.json')
        write_json_atomic(path, manifest.as_dict())

    def verify(self, path: Path | str, expected_sha256: str | None = None) -> bool:
        digest = sha256_file(Path(path))
        return expected_sha256 is None or digest == expected_sha256

    def _validate_url(self, url: str) -> None:
        if not self.allowed_hosts:
            return
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower().strip('.')
        allowed = any(host == candidate or host.endswith('.' + candidate)
                      for candidate in self.allowed_hosts)
        if parsed.scheme != 'https' or not allowed:
            raise DownloadError(f'Host o esquema no permitido para descarga oficial: {url}')


# --------------------------------------------------------------------------- archivos
_UNSAFE_PATH = re.compile(r'^(?:[A-Za-z]:[\\/]|/|\\\\)')
_TRAVERSAL = re.compile(r'(^|[/\\])\.\.([/\\]|$)')


def inventory_zip(archive: Path | str) -> list[str]:
    """Inventario seguro de un ZIP: rechaza rutas absolutas y recorrido ``../``."""
    archive = Path(archive)
    names: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if _UNSAFE_PATH.match(name.replace('\\', '/')) or _TRAVERSAL.search(name.replace('\\', '/')):
                raise ArchiveSecurityError(f'Ruta insegura en el archivo: {name!r}')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ArchiveSecurityError(f'Enlace simbólico no permitido: {name!r}')
            names.append(name)
    return names


def safe_extract_zip(
    archive: Path | str,
    destination: Path | str,
    *,
    uncompressed_limit_bytes: int | None = None,
) -> list[Path]:
    """Extrae un ZIP a una carpeta de staging, sin rutas de salida y sin ejecutar nada."""
    archive = Path(archive)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    seen_targets: set[Path] = set()
    with zipfile.ZipFile(archive) as zf:
        total = sum(info.file_size for info in zf.infolist())
        if uncompressed_limit_bytes and total > uncompressed_limit_bytes:
            raise ArchiveSecurityError(
                f'Tamaño descomprimido {total} bytes supera el límite de '
                f'{uncompressed_limit_bytes} bytes.'
            )
        for info in zf.infolist():
            if info.is_dir():
                continue
            norm = info.filename.replace('\\', '/')
            if _UNSAFE_PATH.match(norm) or _TRAVERSAL.search(norm):
                raise ArchiveSecurityError(f'Ruta insegura en el archivo: {info.filename!r}')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ArchiveSecurityError(
                    f'Enlace simbólico no permitido: {info.filename!r}'
                )
            target = (destination / info.filename).resolve()
            if destination.resolve() not in target.parents:
                raise ArchiveSecurityError(f'Ruta fuera de la carpeta destino: {info.filename!r}')
            if target in seen_targets:
                raise ArchiveSecurityError(f'Ruta duplicada en el archivo: {info.filename!r}')
            seen_targets.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            extracted.append(target)
    return extracted


@contextmanager
def _comprimido(archive: Path) -> Iterator[tuple[list[tuple[str, int]], Callable]]:
    """Los ficheros de un ZIP o un RAR, con su tamaño, y cómo abrirlos."""
    sufijo = archive.suffix.lower()
    if sufijo == '.zip':
        with zipfile.ZipFile(archive) as zf:
            yield [(i.filename, i.file_size) for i in zf.infolist() if not i.is_dir()], zf.open
    elif sufijo == '.rar':
        rarfile = importar_opcional('rarfile', DownloadError(
            'Para leer un paquete RAR falta el driver opcional «rarfile».'))
        preparar_unrar()
        with rarfile.RarFile(archive) as rf:
            yield [(i.filename, int(i.file_size)) for i in rf.infolist() if not i.isdir()], rf.open
    else:
        yield [], archive.open


def extraer_copia_sql(
    archive: Path | str,
    destination: Path | str,
    *,
    cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path | None:
    """080:RF-18 a RF-22: la copia ``.bak`` de un paquete oficial, o ``None`` si no trae.

    El paquete trae, junto a la copia, el instalador de VNRGIS con sus ejecutables. Solo se
    sacan los ``.bak`` y ``.config`` de la carpeta de la copia, escritos por su nombre base, de
    modo que ninguna ruta del comprimido decide dónde se escribe y nada ejecutable sale de él.
    """
    archive, destination = Path(archive), Path(destination)
    with _comprimido(archive) as (ficheros, abrir):
        rutas = [(nombre, tam, PurePosixPath(nombre.replace('\\', '/'))) for nombre, tam in ficheros]
        copias = [r for r in rutas if r[2].suffix.lower() == '.bak']
        if not copias:
            return None
        # La de red, aunque la de parámetros pudiera pesar más: esa la encuentra la spec 023 junto a ella.
        de_red = [r for r in copias if 'param' not in r[2].name.casefold()] or copias
        red = max(de_red, key=lambda r: r[1])
        elegidos = [r for r in rutas if r[2].parent == red[2].parent
                    and r[2].suffix.lower() in ('.bak', '.config')]
        total = sum(r[1] for r in elegidos)
        if cancelled is not None and cancelled():
            raise DownloadCancelled('Extracción cancelada.')
        existente = next(p for p in (destination, *destination.parents) if p.exists())
        libre = shutil.disk_usage(existente).free
        if total > libre:
            raise DownloadError(
                f'No hay espacio para extraer la copia: necesita {total / 1024**3:.1f} GB '
                f'y quedan {libre / 1024**3:.1f} GB.')
        destination.mkdir(parents=True, exist_ok=True)
        escritos: list[Path] = []
        hecho = 0
        try:
            for nombre, tam, ruta in elegidos:
                final = destination / ruta.name
                if final.is_file() and final.stat().st_size == tam:
                    hecho += tam
                    continue
                parte = final.with_name(final.name + '.parte')
                try:
                    with abrir(nombre) as origen, parte.open('wb') as salida:
                        while bloque := origen.read(1024 * 1024):
                            if cancelled is not None and cancelled():
                                raise DownloadCancelled('Extracción cancelada.')
                            salida.write(bloque)
                            hecho += len(bloque)
                            if on_progress is not None:
                                on_progress(hecho, total)
                    os.replace(parte, final)
                    escritos.append(final)
                finally:
                    parte.unlink(missing_ok=True)
        except BaseException:
            for fichero in escritos:
                fichero.unlink(missing_ok=True)
            raise
    return destination / red[2].name


def safe_extract_rar(
    archive: Path | str,
    destination: Path | str,
    *,
    uncompressed_limit_bytes: int | None = None,
) -> list[Path]:
    """Extrae RAR sin rutas de salida, enlaces ni expansión ilimitada."""
    try:
        import rarfile
    except ImportError as exc:
        raise DownloadError(
            'La extracción de RAR necesita el driver opcional «rarfile» '
            '(ver requirements-drivers.txt).'
        ) from exc
    preparar_unrar()
    archive = Path(archive)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with rarfile.RarFile(archive) as rf:
        infos = [info for info in rf.infolist() if not info.isdir()]
        total = sum(int(getattr(info, 'file_size', 0)) for info in infos)
        if uncompressed_limit_bytes and total > uncompressed_limit_bytes:
            raise ArchiveSecurityError(
                f'Tamaño descomprimido {total} bytes supera el límite permitido.'
            )
        for info in infos:
            name = info.filename.replace('\\', '/')
            if _UNSAFE_PATH.match(name) or _TRAVERSAL.search(name):
                raise ArchiveSecurityError(f'Ruta insegura en el archivo: {info.filename!r}')
            if callable(getattr(info, 'is_symlink', None)) and info.is_symlink():
                raise ArchiveSecurityError(f'Enlace simbólico no permitido: {info.filename!r}')
            target = (destination / info.filename).resolve()
            if destination.resolve() not in target.parents:
                raise ArchiveSecurityError(f'Ruta fuera de la carpeta destino: {info.filename!r}')
            target.parent.mkdir(parents=True, exist_ok=True)
            with rf.open(info) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            extracted.append(target)
    return extracted
