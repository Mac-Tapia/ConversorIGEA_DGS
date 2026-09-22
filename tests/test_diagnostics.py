import pytest

from igea_dgs.domain.provenance import Provenanced, ProvenanceKind
from igea_dgs.quality.diagnostics import Diagnostic, Severity, SourceLocation
from igea_dgs.quality.gates import GateResult, QualityGateError


def test_gate_blocks_only_blocking_diagnostics():
    location = SourceLocation("RED.txt", "LINE CONFIGURATION", 42, "Length")
    result = GateResult(
        "G1", [Diagnostic.blocking("E001", "Length missing", location)]
    )

    assert result.blocked is True
    with pytest.raises(QualityGateError, match="E001"):
        result.raise_if_blocked()


def test_non_blocking_diagnostics_do_not_block_gate():
    result = GateResult("G1", [Diagnostic.warning("W001", "Review value")])

    assert result.blocked is False
    result.raise_if_blocked()


def test_provenanced_value_rejects_assumed_in_production():
    value = Provenanced(value=0.3, kind=ProvenanceKind.ASSUMED, source="internal")

    assert value.production_eligible is False


@pytest.mark.parametrize(
    "kind",
    [
        ProvenanceKind.OBSERVED_TXT,
        ProvenanceKind.OBSERVED_CATALOG,
        ProvenanceKind.MANUFACTURER_DATASHEET,
        ProvenanceKind.APPROVED_MAPPING,
        ProvenanceKind.DERIVED,
    ],
)
def test_authorized_provenance_is_production_eligible(kind):
    assert Provenanced(value="x", kind=kind, source="source-id").production_eligible


def test_explicit_serialization_preserves_stable_values():
    location = SourceLocation("RED.txt", "LOAD", 8, "kW")
    diagnostic = Diagnostic.blocking("E100", "Missing kW", location)

    assert diagnostic.to_dict() == {
        "code": "E100",
        "message": "Missing kW",
        "severity": Severity.BLOCKING.value,
        "location": {
            "file": "RED.txt",
            "section": "LOAD",
            "row": 8,
            "field": "kW",
        },
        "details": {},
    }
