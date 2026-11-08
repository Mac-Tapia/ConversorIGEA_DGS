"""Descubrimiento, huella, catálogo, frescura y descarga de fuentes VNRGIS."""

from .catalog import (  # noqa: F401
    FAMILIES,
    CompanyRecord,
    Publication,
    PublicationCatalog,
)
from .download import (  # noqa: F401
    ArchiveSecurityError,
    DownloadManager,
    DownloadManifest,
)
from .fingerprint import (  # noqa: F401
    SourceFingerprint,
    compute_schema_fingerprint,
    compute_source_fingerprint,
)
from .freshness import (  # noqa: F401
    FreshnessResolver,
    resolve_freshness,
)
from .official import (  # noqa: F401
    OfficialDiscoveryError,
    default_discovery_pages,
    is_allowed_official_url,
    parse_official_publications,
    refresh_official_catalog,
)
from .schema import (  # noqa: F401
    CANONICAL_ALIASES,
    FieldLineage,
    SchemaResolver,
    classify_field,
    resolve_alias,
)
