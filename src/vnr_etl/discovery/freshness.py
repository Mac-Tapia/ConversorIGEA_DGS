"""Resolución de «lo más nuevo» por fecha autoritativa (sección D6).

``latest`` significa la publicación autoritativa más reciente descubierta para la
empresa/familia pedida, no la marca de tiempo de hoy. Si las fechas/periodos
entran en conflicto, se informa ambigüedad en lugar de adivinar.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .catalog import Publication


def _parse_date(value: str) -> datetime | None:
    """Parsea una fecha ISO (``YYYY-MM-DD``), ``YYYY-MM`` o ``YYYY``; None si no es defendible."""
    value = (value or '').strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


@dataclass
class FreshnessResult:
    company: str
    requested: str
    selected_publication: str = ''
    reference_period: str = ''
    published_at: str = ''
    confidence: str = 'LOW'
    alternatives: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            'company': self.company,
            'requested': self.requested,
            'selected_publication': self.selected_publication,
            'reference_period': self.reference_period,
            'published_at': self.published_at,
            'confidence': self.confidence,
            'alternatives': list(self.alternatives),
        }


class FreshnessResolver:
    def __init__(self, publications: Iterable[Publication]) -> None:
        self.publications = list(publications)

    def _candidates(self, company: str | None, family: str | None) -> list[Publication]:
        pubs = self.publications
        if company:
            pubs = [p for p in pubs if company in (p.company, p.company_code)]
        if family:
            pubs = [p for p in pubs if p.publication_type == family]
        return pubs

    def resolve(self, company: str | None = None, period: str | None = None,
                family: str | None = None) -> FreshnessResult:
        requested = period or 'latest'
        candidates = self._candidates(company, family)
        if period:  # periodo explícito: filtrar por etiqueta/año y devolver ambigüedad si hay varios
            exact = [p for p in candidates
                     if period in (p.period_label, p.reference_date[:4])]
            if len(exact) == 1:
                return FreshnessResult(
                    company=company or '', requested=requested,
                    selected_publication=exact[0].publication_id,
                    reference_period=exact[0].period_label,
                    published_at=exact[0].published_at,
                    confidence='HIGH', alternatives=[],
                )
            return FreshnessResult(
                company=company or '', requested=requested,
                alternatives=[p.publication_id for p in exact],
                confidence='LOW',
            )

        # «latest»: rango solo de registros con fecha defendible.
        dated = [(p, d) for p in candidates
                 for d in (_parse_date(p.published_at) or _parse_date(p.reference_date),)
                 if d is not None]
        if not dated:
            return FreshnessResult(company=company or '', requested=requested, confidence='LOW')

        dated_sorted = sorted(dated, key=lambda item: item[1], reverse=True)
        newest, newest_date = dated_sorted[0]
        ties = [p for p, d in dated_sorted if d == newest_date]
        if len(ties) > 1:
            return FreshnessResult(
                company=company or '', requested=requested,
                alternatives=sorted(p.publication_id for p in ties),
                confidence='MEDIUM',
            )
        return FreshnessResult(
            company=company or '', requested=requested,
            selected_publication=newest.publication_id,
            reference_period=newest.period_label,
            published_at=newest.published_at,
            confidence='HIGH',
        )


def resolve_freshness(
    publications: Iterable[Publication],
    company: str | None = None,
    period: str | None = None,
    family: str | None = None,
) -> FreshnessResult:
    return FreshnessResolver(publications).resolve(company, period, family)
