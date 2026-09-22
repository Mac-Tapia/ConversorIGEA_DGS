from decimal import Decimal

from igea_dgs.domain.feeder import build_strict_feeder_model

from test_phase_model import _dataset


def test_double_circuit_and_parallel_conductors_are_preserved():
    feeder = build_strict_feeder_model(_dataset(), "F1")
    line = feeder.lines[0]

    assert line.circuits.count == 2
    assert line.conductors_per_phase == 3
    assert line.cross_section_mm2 == Decimal("150")
    assert line.length_km == Decimal("1.25")
