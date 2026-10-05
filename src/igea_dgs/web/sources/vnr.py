"""Adaptador web de un paquete VNR-GIS custodiado."""

from __future__ import annotations

from .base import SourceLoadResult, provenance, validate_snapshot
from ..source_runs import SourceSnapshot


class VnrSourceAdapter:
    mode = 'vnr'

    def __init__(self, *, company: str = 'ELDU', period: str = 'latest_available') -> None:
        self.company = company
        self.period = period

    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult:
        del aliases
        validate_snapshot(
            snapshot,
            mode=self.mode,
            allowed={'vnr_package'},
            required={'vnr_package'},
        )
        from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
        from vnr_etl.pipeline import canonicalize_vnr_package, safe_extract_package

        package = snapshot.files['vnr_package'].path
        extracted = safe_extract_package(package, snapshot.root / 'derivados' / 'vnr')
        canonical, scope = canonicalize_vnr_package(
            extracted.destination,
            company=self.company,
            period=self.period,
        )
        bridge = canonical_to_cymdist(canonical.model, source_path=package)
        source = provenance(snapshot)
        source.update({
            'company': scope['company'],
            'period': scope['period'],
            'package_format': extracted.format,
            'extracted_files': len(extracted.files),
            'canonical_counts': canonical.model.counts(),
            'bridge_issues': bridge.issues,
        })
        return SourceLoadResult(
            dataset=bridge.dataset,
            catalog_report=None,
            readiness=bridge.readiness,
            provenance=source,
        )
