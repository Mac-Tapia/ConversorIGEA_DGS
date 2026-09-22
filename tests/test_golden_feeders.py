from dataclasses import replace
from decimal import Decimal

from igea_dgs.validation.kpis import FeederKpis, compare_kpis


def expected():
    return FeederKpis(
        bus_voltage_pu={"N1": Decimal("1.0"), "N2": Decimal("0.99")},
        line_current_a={"L1": Decimal("40")},
        source_p_mw={"SRC": Decimal("1.0")},
        source_q_mvar={"SRC": Decimal("0.2")},
        load_p_mw={"LD1": Decimal("0.98")},
        load_q_mvar={"LD1": Decimal("0.19")},
        losses_mw=Decimal("0.02"),
        in_service={"L1": True, "LD1": True},
    )


def test_golden_voltage_outside_predeclared_tolerance_fails():
    golden = expected()
    actual = replace(expected(), bus_voltage_pu={"N1": Decimal("1.0"), "N2": Decimal("1.01")})
    comparison = compare_kpis(golden, actual, {"bus_voltage_pu": Decimal("0.005")})
    assert comparison.passed is False
    assert comparison.failures[0].metric == "bus_voltage_pu"


def test_golden_all_declared_metrics_pass_within_tolerance():
    golden = expected()
    tolerances = {name: Decimal("0.001") for name in golden.numeric_metric_names()}
    assert compare_kpis(golden, expected(), tolerances).passed


def test_missing_expected_or_tolerance_is_a_failure():
    golden = expected()
    actual = replace(expected(), line_current_a={})
    result = compare_kpis(
        golden,
        actual,
        {"bus_voltage_pu": Decimal("0.01"), "line_current_a": Decimal("0.1")},
    )
    assert {failure.reason for failure in result.failures} == {"missing_actual", "missing_tolerance"}
