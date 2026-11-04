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
from html import unescape
from html.parser import HTMLParser
from pathlib import PurePosixPath
from unicodedata import combining, normalize
from urllib.parse import unquote, urljoin, urlparse

from convertersmartgrid.salidas_red import motivo_apagada, salida_permitida

from .catalog import Publication, PublicationCatalog

DEFAULT_ALLOWED_HOSTS = (
    'osinergmin.gob.pe',
    'www.osinergmin.gob.pe',
    'www2.osinergmin.gob.pe',
    'gisem.osinergmin.gob.pe',
)

# 080:RF-1: de aquí salen los ciclos. Los paquetes no están en las páginas anuales de
# resoluciones, donde se buscaban, sino en la página de cada proceso VNR que esta enlaza.
PORTAL_VNR = ('https://www.osinergmin.gob.pe/seccion/institucional/regulacion-tarifaria/'
              'procesos-regulatorios/electricidad/vnr-distribucion')
_PAGINA_DE_CICLO = re.compile(r'/actividades-relacionadas/[^/]*vnr[^/]*$', re.IGNORECASE)
_ANIO_DE_CICLO = re.compile(r'vnr-adaptado-(20\d{2})', re.IGNORECASE)
_RESOLUCION = re.compile(r'\b(\d{1,3})-(20\d{2})-OS/CD\b', re.IGNORECASE)

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

    from vnr_etl.connectors.registry import FORMATOS_PAQUETE_VNR
    from vnr_etl.connectors.sqlserver_vnr import es_copia_sql

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix not in FORMATOS_PAQUETE_VNR and not es_copia_sql(source):
        raise OfficialDiscoveryError(
            f'{source.name} no es un paquete VNR-GIS soportado. Formatos admitidos: '
            + ', '.join(FORMATOS_PAQUETE_VNR) + '. Los PDF son solo evidencia.'
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
        self.anclas: dict[str, str] = {}
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
            # El texto de la fila junta a todas sus empresas: el del enlace es de la suya (080:RF-5).
            self.anclas[self._href] = ' '.join(self._text)
            self._href = None
            self._text = []
        if tag.lower() == 'tr' and self._in_row:
            context = re.sub(r'\s+', ' ', ' '.join(self._row_text)).strip()
            self.links.extend((href, context) for href in self._row_links)
            self._in_row = False
            self._row_text = []
            self._row_links = []


def _limpio(texto: str) -> str:
    return re.sub(r'\s+', ' ', texto.replace('​', ' ')).strip()


def _normal(texto: str) -> str:
    """Sin acentos ni mayúsculas, para comparar nombres de empresa."""
    sin_acentos = ''.join(c for c in normalize('NFKD', texto) if not combining(c))
    return _limpio(sin_acentos).casefold()


def _familia(suffix: str, ruta: str, ancla: str) -> str:
    """080:RF-3, RF-4: en una página de ciclo también hay costos, mapas y anexos en ZIP o RAR."""
    if suffix not in VNR_DATA_SUFFIXES:
        return 'REGULATORY_VNR_PUBLICATION'
    ruta = ruta.upper()
    if 'SICODI' in ruta:
        return 'SICODI'
    if 'MAPA_DENSIDAD' in ruta:
        return 'MAP_DENSITY'
    if 'VNRGIS' in ruta or 'VNRGIS' in ancla.upper():
        return 'REGULATORY_VNRGIS_PACKAGE'
    return 'REGULATORY_VNR_PUBLICATION'


def _empresa_del_paquete(ancla: str, archivo: str) -> str:
    """080:RF-6: el rótulo, salvo si no corresponde al archivo («CVS Energía» en `CVC Energia.zip`)."""
    rotulo, nombre = _normal(ancla), _normal(archivo)
    if rotulo and (rotulo == nombre or rotulo.startswith(nombre + ' ') or nombre.startswith(rotulo + ' ')):
        return ancla
    return archivo


def _clave_de_resolucion(referencia: str) -> tuple[int, int]:
    encontrada = _RESOLUCION.search(referencia or '')
    return (int(encontrada.group(2)), int(encontrada.group(1))) if encontrada else (0, 0)


def paginas_de_ciclos(html: str, hub: str = PORTAL_VNR,
                      allowed_hosts=DEFAULT_ALLOWED_HOSTS) -> list[str]:
    """080:RF-1: las páginas de cada proceso VNR que enlaza la página oficial."""
    parser = _LinkParser()
    parser.feed(unescape(html))
    paginas = {urljoin(hub, href.strip()).split('#', 1)[0] for href, _ in parser.links}
    return sorted(p for p in paginas if is_allowed_official_url(p, allowed_hosts)
                  and _PAGINA_DE_CICLO.search(urlparse(p).path))


def vigentes_por_empresa(publicaciones: Iterable[Publication]) -> dict[str, dict]:
    """080:RF-9, RF-10: por paquete, su empresa y si es el vigente de ella.

    Se comparan resoluciones, no títulos de página: la «publicación de la resolución de
    fijación 2025» trae en realidad el proyecto (RCD 154-2026), y la definitiva es la 184-2026.
    """
    paquetes = list(publicaciones)
    clave = {p.publication_id: _normal(p.company or p.title) for p in paquetes}
    por_ciclo: dict[str, set[str]] = {}
    for p in paquetes:
        por_ciclo.setdefault(p.period_label, set()).add(clave[p.publication_id])
    # Solo dentro de un ciclo: «Pluz Energia» y «Pluz Energia Peru» son la misma; en ciclos
    # distintos, un comienzo igual no prueba que lo sean.
    alias: dict[str, str] = {}
    for nombres in por_ciclo.values():
        for nombre in nombres:
            for otro in nombres:
                if nombre.startswith(otro + ' '):
                    alias[nombre] = otro
    grupos: dict[str, list[Publication]] = {}
    for p in paquetes:
        nombre = clave[p.publication_id]
        grupos.setdefault(alias.get(nombre, nombre), []).append(p)
    resultado: dict[str, dict] = {}
    for miembros in grupos.values():
        def orden(p: Publication) -> tuple:
            anio = int(p.period_label) if str(p.period_label).isdigit() else 0
            return (anio, _clave_de_resolucion(p.regulatory_reference))

        mejor = max(miembros, key=orden)
        empresa = mejor.company or mejor.title
        for p in miembros:
            resultado[p.publication_id] = {'empresa': empresa, 'vigente': p is mejor}
    return resultado


def parse_official_publications(page_url: str, html: str,
                                allowed_hosts=DEFAULT_ALLOWED_HOSTS) -> list[Publication]:
    if not is_allowed_official_url(page_url, allowed_hosts):
        raise OfficialDiscoveryError(f'Página de descubrimiento no oficial: {page_url}')
    parser = _LinkParser()
    # 080:RF-2: el portal guarda la tabla de cada proceso como HTML escapado («&lt;a href=…»).
    pagina = unescape(html)
    parser.feed(pagina)
    ciclo = _ANIO_DE_CICLO.search(urlparse(page_url).path)
    resolucion = ''
    if ciclo:
        citadas = (m.group(0).upper() for m in _RESOLUCION.finditer(pagina))
        resolucion = max(citadas, key=_clave_de_resolucion, default='')
    publications: dict[str, Publication] = {}
    for href, text in parser.links:
        url = urljoin(page_url, href.strip())
        if not is_allowed_official_url(url, allowed_hosts):
            continue
        searchable = f'{text} {url}'.lower()
        if 'vnr' not in searchable and 'valor nuevo de reemplazo' not in searchable:
            continue
        ruta = unquote(urlparse(url).path)
        path = PurePosixPath(ruta)
        suffix = path.suffix.lower()
        if ciclo and not suffix:
            continue  # El menú del portal enlaza los otros ciclos: no son publicaciones de este.
        ancla = _limpio(parser.anclas.get(href, ''))
        pub_type = _familia(suffix, ruta, ancla)
        title = re.sub(r'\s+', ' ', text).strip() or path.name
        period_match = re.search(r'diciembre\s+de\s+(20\d{2})', title, re.IGNORECASE)
        if period_match is None:
            years = re.findall(r'\b(20\d{2})\b', title)
            period_value = years[-1] if years else ''
        else:
            period_value = period_match.group(1)
        if ciclo:
            period_value = ciclo.group(1)
        reference = re.search(r'\b\d{1,3}-20\d{2}-OS/CD\b', title, re.IGNORECASE)
        date_match = re.search(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b', title)
        company = ''
        if pub_type == 'REGULATORY_VNRGIS_PACKAGE' and 'VNRGIS' in str(path.parent).upper():
            company = _empresa_del_paquete(ancla, path.stem)
            title = f'VNR-GIS {company}'
        published_at = ''
        if date_match:
            day, month, year = date_match.groups()
            published_at = f'{year}-{int(month):02d}-{int(day):02d}'
        digest = hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]
        publications[url] = Publication(
            publication_id=f'OSINERGMIN_{digest}',
            title=title,
            publication_type=pub_type,
            regulatory_reference=resolucion or (reference.group(0).upper() if reference else ''),
            reference_date=period_value,
            published_at=published_at,
            discovered_at=datetime.now(UTC).isoformat(),
            official_page=page_url,
            company=company,
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
    por_leer = list(pages) if pages else default_discovery_pages()
    if not pages:
        try:
            por_leer += paginas_de_ciclos(fetch(PORTAL_VNR))
        except Exception as exc:  # noqa: BLE001 - se informa cuál falló (080:RF-17)
            errors.append({'page': PORTAL_VNR, 'error': str(exc) or exc.__class__.__name__})
    for page in por_leer:
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
        'pages': por_leer,
        'added': added,
        'total': len(catalog.publications()),
        'errors': errors,
    }


def _fetch_html(url: str) -> str:
    if not is_allowed_official_url(url):
        raise OfficialDiscoveryError(f'Página de descubrimiento no oficial: {url}')
    if not salida_permitida('vnr_oficial'):                                    # 086:RF-22
        raise OfficialDiscoveryError(motivo_apagada('vnr_oficial'))
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
            # Por los bytes: con «apparent_encoding», las páginas de cada proceso VNR (UTF-8 con
            # espacios de ancho cero) no dejaban ver sus enlaces (2026-11-02).
            contenido = getattr(response, 'content', None)
            if isinstance(contenido, bytes):
                try:
                    return contenido.decode('utf-8')
                except UnicodeDecodeError:
                    pass
            response.encoding = response.apparent_encoding or response.encoding
            return response.text
        except OfficialDiscoveryError:
            raise
        except Exception as exc:  # noqa: BLE001 - reintentos de red heterogéneos
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise OfficialDiscoveryError(f'No se pudo leer la página oficial {url}: {last_error}')
