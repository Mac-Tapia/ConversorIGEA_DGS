"""Adaptador de un paquete VNR-GIS custodiado."""

from __future__ import annotations

from pathlib import Path

from .base import SourceLoadResult, provenance, validate_snapshot
from .snapshot import SourceSnapshot


class VnrSourceAdapter:
    mode = 'vnr'

    def __init__(self, *, company: str | None = None, period: str | None = None) -> None:
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
        if Path(package).suffix.lower() == '.bak':
            return self._cargar_copia_sql(snapshot, Path(package))
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

    def _cargar_copia_sql(self, snapshot: SourceSnapshot, bak: Path) -> SourceLoadResult:
        """Spec 023: la copia de SQL Server de VNR-GIS de cualquier concesionaria."""
        import os

        from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
        from vnr_etl.connectors.sqlserver_vnr import SERVIDOR, cargar_copia

        servidor = os.environ.get('IGEA_SQLSERVER', SERVIDOR)
        original = Path(snapshot.files['vnr_package'].source_path or bak)
        modelo, avisos, alcance = cargar_copia(bak, servidor=servidor,
                                               vecinas=[original.parent])
        bridge = canonical_to_cymdist(modelo, source_path=bak)
        source = provenance(snapshot)
        source.update({
            'company': alcance['company'],
            'period': alcance['period'],
            'package_format': 'sqlserver_bak',
            'sqlserver': alcance,
            'canonical_counts': modelo.counts(),
            'vnr_avisos': avisos,
            'bridge_issues': bridge.issues,
        })
        return SourceLoadResult(
            dataset=bridge.dataset,
            catalog_report=None,
            readiness=bridge.readiness,
            provenance=source,
        )
