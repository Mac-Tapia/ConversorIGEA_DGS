"""Catálogo de publicaciones y registro dinámico de empresas (secciones D4–D6).

El catálogo **conserve** publicaciones antiguas: nunca se sobrescribe la historia
cuando aparece algo más nuevo. Las empresas se construyen dinámicamente a partir
de las publicaciones y sus alias, no de una lista congelada.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

FAMILIES = (
    'REGULATORY_VNRGIS_PACKAGE',
    'REGULATORY_VNR_PUBLICATION',
    'ARCGIS_PUBLIC_REFERENCE',
    'INTERRUPTION_GIS',
    'SICODI',
    'MAP_DENSITY',
    'MANUAL_INSTALLER',
    'UNKNOWN',
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Publication:
    """Un registro inmutable del catálogo de publicaciones (sección D5)."""

    publication_id: str
    title: str = ''
    publication_type: str = 'UNKNOWN'
    regulatory_reference: str = ''
    reference_date: str = ''
    published_at: str = ''
    discovered_at: str = ''
    official_page: str = ''
    company: str = ''
    company_code: str = ''
    period_label: str = ''
    download_url: str = ''
    file_name: str = ''
    file_type: str = ''
    status: str = 'DISCOVERED'

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping) -> Publication:
        fields = {k: data.get(k, '') for k in cls.__dataclass_fields__}
        return cls(**fields)


@dataclass(frozen=True)
class CompanyRecord:
    """Registro canónico de empresa (sección D4)."""

    company_id: str
    codes: tuple[str, ...] = ()
    official_name: str = ''
    aliases: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    first_seen: str = ''
    last_seen: str = ''

    def as_dict(self) -> dict:
        return {
            'company_id': self.company_id,
            'codes': list(self.codes),
            'official_name': self.official_name,
            'aliases': list(self.aliases),
            'source_refs': list(self.source_refs),
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
        }


class PublicationCatalog:
    """Almacén del catálogo y de las empresas, con persistencia JSON."""

    def __init__(self) -> None:
        self._publications: dict[str, Publication] = {}
        self._companies: dict[str, CompanyRecord] = {}

    # --- consulta ------------------------------------------------------------
    def publications(self, company: str | None = None, family: str | None = None) -> list[Publication]:
        pubs = list(self._publications.values())
        if company:
            pubs = [p for p in pubs if company in (p.company, p.company_code)]
        if family:
            pubs = [p for p in pubs if p.publication_type == family]
        return sorted(pubs, key=lambda p: (p.published_at, p.publication_id))

    def get(self, publication_id: str) -> Publication | None:
        return self._publications.get(publication_id)

    def companies(self) -> list[CompanyRecord]:
        return list(self._companies.values())

    def find_company(self, query: str) -> CompanyRecord | None:
        q = (query or '').strip().lower()
        if not q:
            return None
        for record in self._companies.values():
            candidates = [record.official_name, *record.aliases, *record.codes]
            if any(q == c.lower() for c in candidates if c):
                return record
        return None

    # --- mutación (aditiva e inmutable) -------------------------------------
    def upsert_publication(self, publication: Publication) -> bool:
        """Añade un registro; devuelve False si ya existía idéntico (sin sobrescribir).

        Una publicación ya conocida no se reescribe: la historia es inmutable y un
        enlace/cambio de fichero genera un registro nuevo, no una mutación del anterior.
        """
        existing = self._publications.get(publication.publication_id)
        if existing is not None and existing.as_dict() == publication.as_dict():
            return False
        if existing is not None:
            payload = json.dumps(
                publication.as_dict(), ensure_ascii=False, sort_keys=True
            ).encode('utf-8')
            version_id = f'{publication.publication_id}@{hashlib.sha256(payload).hexdigest()[:12]}'
            publication = replace(publication, publication_id=version_id)
            if self._publications.get(version_id) == publication:
                return False
        self._publications[publication.publication_id] = publication
        self._register_company(publication)
        return True

    def _register_company(self, publication: Publication) -> None:
        name = publication.company or publication.company_code
        if not name:
            return
        key = name.strip().lower()
        company_id = 'C_' + ''.join(c for c in key if c.isalnum())[:24] or 'C_UNKNOWN'
        existing = self._companies.get(company_id)
        now = _now_iso()
        if existing is None:
            self._companies[company_id] = CompanyRecord(
                company_id=company_id,
                codes=(publication.company_code,) if publication.company_code else (),
                official_name=publication.company,
                aliases=(),
                source_refs=(publication.official_page,),
                first_seen=now,
                last_seen=now,
            )
        else:
            codes = set(existing.codes)
            if publication.company_code:
                codes.add(publication.company_code)
            refs = set(existing.source_refs)
            if publication.official_page:
                refs.add(publication.official_page)
            aliases = set(existing.aliases)
            if publication.company and publication.company != existing.official_name:
                aliases.add(publication.company)
            self._companies[company_id] = CompanyRecord(
                company_id=company_id,
                codes=tuple(sorted(codes)),
                official_name=existing.official_name or publication.company,
                aliases=tuple(sorted(aliases)),
                source_refs=tuple(sorted(refs)),
                first_seen=existing.first_seen,
                last_seen=now,
            )

    # --- persistencia --------------------------------------------------------
    def save(self, directory: Path | str) -> tuple[Path, Path]:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        catalog_path = directory / 'catalog.json'
        companies_path = directory / 'companies.json'
        catalog_path.write_text(
            json.dumps(
                [p.as_dict() for p in self.publications()],
                ensure_ascii=False, indent=2,
            ), encoding='utf-8',
        )
        companies_path.write_text(
            json.dumps(
                [c.as_dict() for c in self.companies()],
                ensure_ascii=False, indent=2,
            ), encoding='utf-8',
        )
        return catalog_path, companies_path

    @classmethod
    def load(cls, directory: Path | str) -> PublicationCatalog:
        directory = Path(directory)
        catalog = cls()
        catalog_path = directory / 'catalog.json'
        if catalog_path.is_file():
            data = json.loads(catalog_path.read_text(encoding='utf-8'))
            for item in data:
                pub = Publication.from_dict(item)
                catalog._publications[pub.publication_id] = pub
        companies_path = directory / 'companies.json'
        if companies_path.is_file():
            data = json.loads(companies_path.read_text(encoding='utf-8'))
            for item in data:
                rec = CompanyRecord(
                    company_id=item['company_id'],
                    codes=tuple(item.get('codes', ())),
                    official_name=item.get('official_name', ''),
                    aliases=tuple(item.get('aliases', ())),
                    source_refs=tuple(item.get('source_refs', ())),
                    first_seen=item.get('first_seen', ''),
                    last_seen=item.get('last_seen', ''),
                )
                catalog._companies[rec.company_id] = rec
        return catalog
