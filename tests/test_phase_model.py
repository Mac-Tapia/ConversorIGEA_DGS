from decimal import Decimal
from types import SimpleNamespace

import pytest

from igea_dgs.domain.feeder import build_strict_feeder_model
from igea_dgs.domain.phases import PhaseSet
from igea_dgs.quality.gates import QualityGateError


def _dataset(value_type="2"):
    return SimpleNamespace(
        feeders={"F1": ("S1",)},
        sources={"F1": {"NodeID": "N1", "DesiredVoltage": "13.2"}},
        sections={"S1": {"FromNodeID": "N1", "ToNodeID": "N2", "Phase": "ABC"}},
        line_configurations={
            "S1": {
                "LineCableID": "L150",
                "Length": "1.25",
                "Overhead": "1",
                "NumberOfCircuits": "2",
                "ConductorsPerPhase": "3",
                "CrossSection": "150",
            }
        },
        customer_loads={
            ("S1", "LD1"): {
                "SectionID": "S1", "DeviceNumber": "LD1", "Phase": "A",
                "ValueType": value_type, "Value1": "100", "Value2": "0.95",
            }
        },
        load_placements={("S1", "LD1"): {"Location": "1"}},
    )


def test_single_phase_load_is_preserved():
    feeder = build_strict_feeder_model(_dataset(), "F1")

    assert feeder.loads[0].phases == PhaseSet.A
    assert feeder.loads[0].p_mw == Decimal("0.1")
    assert feeder.loads[0].q_mvar > Decimal("0")


def test_unknown_load_value_type_blocks():
    with pytest.raises(QualityGateError, match="UNSUPPORTED_LOAD_VALUE_TYPE"):
        build_strict_feeder_model(_dataset("999"), "F1")
