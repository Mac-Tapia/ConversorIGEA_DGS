"""Gestor de descargas y manejo seguro de archivos (secciones D9–D11, E3).

Descarga con reintentos, fichero ``.part``, renombre atómico, SHA-256 y
``manifest.json``. La extracción de archivos rechaza rutas absolutas y recorrido
``../``, y separa la detección de formato de la extracción.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class DownloadError(RuntimeError):
    pass


class ArchiveSecurityError(DownloadError):
    pass


def _require_requests():
    try:
        import requests  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise DownloadError(
            'La descarga necesita la dependencia «requests» (ver requirements.txt '
            'y `python -m vnr_etl doctor`).'
        ) from exc
    return __import__('requests')


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


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
        self.temp_dir = Path(temp_dir) if temp_dir else self.cache_dir / '_tmp'
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
    ) -> DownloadManifest:
        self._validate_url(url)
        requests = _require_requests()
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        part = destination.with_suffix(destination.suffix + '.part')

        if destination.is_file() and not force:
            return self._manifest_for_existing(destination, url, publication_id, company, period)

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                content_type = self._stream(requests, url, part, on_progress=on_progress)
                if self.max_file_size_bytes and part.stat().st_size > self.max_file_size_bytes:
                    part.unlink(missing_ok=True)
                    raise DownloadError(
                        f'El fichero supera el tamaño máximo de '
                        f'{self.max_file_size_bytes / (1024 * 1024):.0f} MB.'
                    )
                manifest = self._finalize(
                    part, destination, url, publication_id, company, period,
                    content_type=content_type,
                )
                self._write_manifest(destination, manifest)
                return manifest
            except Exception as exc:  # noqa: BLE001 - reintentos con backoff
                last_error = exc
                part.unlink(missing_ok=True)
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
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
                written = 0
                with part.open(mode) as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
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
        digest = sha256_of(part)
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
            sha256=sha256_of(destination),
            archive_test='N/A',
        )

    def _write_manifest(self, destination: Path, manifest: DownloadManifest) -> None:
        path = destination.with_suffix(destination.suffix + '.manifest.json')
        path.write_text(json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2), encoding='utf-8')

    def verify(self, path: Path | str, expected_sha256: str | None = None) -> bool:
        digest = sha256_of(Path(path))
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
