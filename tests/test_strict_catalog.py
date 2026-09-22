import hashlib

import pytest

from igea_dgs.catalog import (
    ApprovedMapping,
    EquipmentCatalog,
    UnresolvedEquipmentError,
)
from igea_dgs.domain.provenance import ProvenanceKind


@pytest.fixture
def catalog():
    fingerprint = hashlib.sha256(b"AA05002D|50|0.641|0.38").hexdigest()
    return EquipmentCatalog(
        equipment={
            "overhead_line": {
                "AA05002D": {"section_mm2": 50.0, "r1_ohm_km": 0.641, "x1_ohm_km": 0.38}
            }
        },
        mappings={
            ("overhead_line", "UTILITY-X"): ApprovedMapping(
                source_id="UTILITY-X",
                target_id="AA05002D",
                medium="overhead_line",
                compared_parameters=("section_mm2", "r1_ohm_km", "x1_ohm_km"),
                justification="Ficha oficial equivalente aprobada",
                approved_by="responsable-tecnico",
                approved_at="2026-09-21",
                sha256=fingerprint,
            )
        },
    )


def test_similar_conductor_code_is_not_auto_selected(catalog):
    with pytest.raises(UnresolvedEquipmentError) as exc:
        catalog.resolve_exact("overhead_line", "AA05001D")

    assert exc.value.code == "EQUIPMENT_NOT_FOUND"


def test_default_is_not_used_for_missing_code(catalog):
    with pytest.raises(UnresolvedEquipmentError):
        catalog.resolve_exact("overhead_line", "DEFAULT")


def test_approved_mapping_requires_parameter_fingerprint(catalog):
    resolved = catalog.resolve_exact("overhead_line", "UTILITY-X")

    assert resolved.provenance.kind is ProvenanceKind.APPROVED_MAPPING
    assert resolved.mapping is not None
    assert resolved.mapping.sha256


def test_mapping_with_wrong_fingerprint_is_rejected(catalog):
    mapping = catalog.mappings[("overhead_line", "UTILITY-X")]
    broken = EquipmentCatalog(catalog.equipment, {("overhead_line", "UTILITY-X"): mapping.with_sha256("0" * 64)})

    with pytest.raises(UnresolvedEquipmentError) as exc:
        broken.resolve_exact("overhead_line", "UTILITY-X")
    assert exc.value.code == "MAPPING_FINGERPRINT_MISMATCH"
