from dataclasses import replace

from igea_dgs.domain.feeder import build_strict_feeder_model
from igea_dgs.domain.phases import PhaseSet
from igea_dgs.validation import validate_source_model

from test_phase_model import _dataset


def test_source_model_validator_detects_phase_loss():
    source = _dataset()
    model = build_strict_feeder_model(source, "F1")
    mutated = replace(model, lines=(replace(model.lines[0], phases=PhaseSet.A),))

    result = validate_source_model(source, mutated)

    assert "PHASE_MISMATCH" in result.error_codes


def test_source_model_validator_accepts_faithful_model():
    source = _dataset()
    result = validate_source_model(source, build_strict_feeder_model(source, "F1"))
    assert not result.blocked
