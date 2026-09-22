from igea_dgs.dgsio import build_dgs_document
from igea_dgs.domain.feeder import build_strict_feeder_model
from igea_dgs.validation import validate_model_dgs

from test_phase_model import _dataset


def test_model_dgs_validator_detects_circuit_loss():
    model = build_strict_feeder_model(_dataset(), "F1")
    document = build_dgs_document(model)
    tables = {name: tuple(dict(row) for row in rows) for name, rows in document.tables.items()}
    tables["ElmLne"][0]["nlnum"] = "1"

    result = validate_model_dgs(model, tables)

    assert "CIRCUIT_COUNT_MISMATCH" in result.error_codes
