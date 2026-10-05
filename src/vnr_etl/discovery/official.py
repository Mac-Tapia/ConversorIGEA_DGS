"""Descubrimiento reproducible de publicaciones oficiales de OSINERGMIN.

Las páginas iniciales son reglas de descubrimiento calculadas por año; los enlaces,
periodos y archivos son datos encontrados en ejecución. Ningún resultado de un host
no oficial entra al catálogo.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

from .catalog import Publication, PublicationCatalog

DEFAULT_ALLOWED_HOSTS = (
    'osinergmin.gob.pe',
    'www.osinergmin.gob.pe',
    'www2.osinergmin.gob.pe',
    'gisem.osinergmin.gob.pe',
)

VNR_DATA_SUFFIXES = frozenset({
    '.zip', '.rar', '.mdb', '.accdb', '.gpkg', '.sqlite', '.db', '.geojson',
})


class OfficialDiscoveryError(RuntimeError):
    pass


def is_allowed_official_url(url: str, allowed_hosts=DEFAULT_ALLOWED_HOSTS) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().strip('.')
    return parsed.scheme == 'https' and any(
        host == allowed or host.endswith('.' + allowed)
        for allowed in allowed_hosts
    )


def is_vnr_data_package(value: Publication | str) -> bool:
    """Clasifica por tipo y formato; una resolución PDF nunca es una base VNR."""
    if isinstance(value, Publication):
        url = value.download_url
        if value.publication_type != 'REGULATORY_VNRGIS_PACKAGE':
            return False
    else:
        url = value
    return PurePosixPath(urlparse(url).path).suffix.lower() in VNR_DATA_SUFFIXES


def publication_evidence_sha256(publication: Publication) -> str:
    evidence = {
        'publication_id': publication.publication_id,
        'official_page': publication.official_page,
        'download_url': publication.download_url,
        'published_at': publication.published_at,
        'reference_date': publication.reference_date,
    }
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def validate_vnr_package_file(path) -> None:
    """Validación local mínima antes de ofrecer un archivo como fuente convertible."""
    from pathlib import Path

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in VNR_DATA_SUFFIXES:
        raise OfficialDiscoveryError(
            f'{source.name} no es un paquete VNR-GIS soportado; los PDF son solo evidencia.'
        )
    if not source.is_file() or source.stat().st_size == 0:
        raise OfficialDiscoveryError(f'Paquete VNR-GIS vacío o inexistente: {source}')
    with source.open('rb') as handle:
        prefix = handle.read(8)
    if prefix.startswith(b'%PDF'):
        raise OfficialDiscoveryError(f'{source.name} es un PDF, no una base VNR-GIS.')
    if suffix == '.zip' and not zipfile.is_zipfile(source):
        raise OfficialDiscoveryError(f'{source.name} no es un ZIP válido.')


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._in_row = False
        self._row_text: list[str] = []
        self._row_links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'tr':
            self._in_row = True
            self._row_text = []
            self._row_links = []
        if tag.lower() == 'a':
            self._href = dict(attrs).get('href')
            self._text = []
            if self._in_row and self._href:
                self._row_links.append(self._href)

    def handle_data(self, data):
        if self._in_row:
            self._row_text.append(data)
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self._href is not None:
            self.links.append((self._href, ' '.join(self._text).strip()))
            self._href = None
            self._text = []
        if tag.lower() == 'tr' and self._in_row:
            context = re.sub(r'\s+', ' ', ' '.join(self._row_text)).strip()
            self.links.extend((href, context) for href in self._row_links)
            self._in_row = False
            self._row_text = []
            self._row_links = []


def parse_official_publications(page_url: str, html: str,
                                allowed_hosts=DEFAULT_ALLOWED_HOSTS) -> list[Publication]:
    if not is_allowed_official_url(page_url, allowed_hosts):
        raise OfficialDiscoveryError(f'Página de descubrimiento no oficial: {page_url}')
    parser = _LinkParser()
    parser.feed(html)
    publications: dict[str, Publication] = {}
    for href, text in parser.links:
        url = urljoin(page_url, href)
        if not is_allowed_official_url(url, allowed_hosts):
            continue
        searchable = f'{text} {url}'.lower()
        if 'vnr' not in searchable and 'valor nuevo de reemplazo' not in searchable:
            continue
        path = PurePosixPath(urlparse(url).path)
        suffix = path.suffix.lower()
        package = suffix in VNR_DATA_SUFFIXES
        pub_type = 'REGULATORY_VNRGIS_PACKAGE' if package else 'REGULATORY_VNR_PUBLICATION'
        title = re.sub(r'\s+', ' ', text).strip() or path.name
        period_match = re.search(r'diciembre\s+de\s+(20\d{2})', title, re.IGNORECASE)
        if period_match is None:
            years = re.findall(r'\b(20\d{2})\b', title)
            period_value = years[-1] if years else ''
        else:
            period_value = period_match.group(1)
        reference = re.search(r'\b\d{1,3}-20\d{2}-OS/CD\b', title, re.IGNORECASE)
        date_match = re.search(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b', title)
        published_at = ''
        if date_match:
            day, month, year = date_match.groups()
            published_at = f'{year}-{int(month):02d}-{int(day):02d}'
        digest = hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]
        publications[url] = Publication(
            publication_id=f'OSINERGMIN_{digest}',
            title=title,
            publication_type=pub_type,
            regulatory_reference=reference.group(0).upper() if reference else '',
            reference_date=period_value,
            published_at=published_at,
            discovered_at=datetime.now(UTC).isoformat(),
            official_page=page_url,
            period_label=period_value,
            download_url=url,
            file_name=path.name,
            file_type=suffix.lstrip('.').upper(),
        )
    return sorted(publications.values(), key=lambda item: item.publication_id)


def default_discovery_pages(now: datetime | None = None) -> list[str]:
    year = (now or datetime.now(UTC)).year
    return [
        f'https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-{candidate}.aspx'
        for candidate in (year, year - 1)
    ]


def refresh_official_catalog(
    catalog_dir,
    *,
    pages: Iterable[str] | None = None,
    fetcher: Callable[[str], str] | None = None,
    allowed_hosts=DEFAULT_ALLOWED_HOSTS,
) -> tuple[PublicationCatalog, dict]:
    catalog = PublicationCatalog.load(catalog_dir)
    fetch = fetcher or _fetch_html
    added = 0
    errors: list[dict] = []
    for page in pages or default_discovery_pages():
        try:
            html = fetch(page)
            for publication in parse_official_publications(page, html, allowed_hosts):
                existing = catalog.get(publication.publication_id)
                if existing is not None:
                    publication = replace(publication, discovered_at=existing.discovered_at)
                added += int(catalog.upsert_publication(publication))
        except Exception as exc:  # noqa: BLE001 - una fuente no oculta las demás
            errors.append({'page': page, 'error': str(exc) or exc.__class__.__name__})
    catalog.save(catalog_dir)
    return catalog, {
        'pages': list(pages or default_discovery_pages()),
        'added': added,
        'total': len(catalog.publications()),
        'errors': errors,
    }


def _fetch_html(url: str) -> str:
    if not is_allowed_official_url(url):
        raise OfficialDiscoveryError(f'Página de descubrimiento no oficial: {url}')
    try:
        import requests
    except ImportError as exc:
        raise OfficialDiscoveryError('El descubrimiento oficial requiere «requests».') from exc
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.get(url, timeout=(20, 90))
            response.raise_for_status()
            final_url = getattr(response, 'url', url)
            if not is_allowed_official_url(final_url):
                raise OfficialDiscoveryError(f'Redirección a host no oficial: {final_url}')
            response.encoding = response.apparent_encoding or response.encoding
            return response.text
        except OfficialDiscoveryError:
            raise
        except Exception as exc:  # noqa: BLE001 - reintentos de red heterogéneos
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise OfficialDiscoveryError(f'No se pudo leer la página oficial {url}: {last_error}')
