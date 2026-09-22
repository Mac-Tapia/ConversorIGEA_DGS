"""Comparación cuantitativa contra expectativas obtenidas independientemente."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


@dataclass(frozen=True, slots=True)
class FeederKpis:
    bus_voltage_pu: Mapping[str, Decimal]
    line_current_a: Mapping[str, Decimal]
    source_p_mw: Mapping[str, Decimal]
    source_q_mvar: Mapping[str, Decimal]
    load_p_mw: Mapping[str, Decimal]
    load_q_mvar: Mapping[str, Decimal]
    losses_mw: Decimal
    in_service: Mapping[str, bool]

    def numeric_metric_names(self) -> tuple[str, ...]:
        return (
            "bus_voltage_pu", "line_current_a", "source_p_mw", "source_q_mvar",
            "load_p_mw", "load_q_mvar", "losses_mw",
        )


@dataclass(frozen=True, slots=True)
class KpiFailure:
    metric: str
    key: str
    reason: str
    expected: object | None = None
    actual: object | None = None
    tolerance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class KpiComparison:
    failures: tuple[KpiFailure, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def compare_kpis(
    expected: FeederKpis,
    actual: FeederKpis,
    tolerances: Mapping[str, Decimal],
) -> KpiComparison:
    failures: list[KpiFailure] = []
    for metric in expected.numeric_metric_names():
        tolerance = tolerances.get(metric)
        if tolerance is None:
            failures.append(KpiFailure(metric, "*", "missing_tolerance"))
            continue
        expected_value = getattr(expected, metric)
        actual_value = getattr(actual, metric)
        expected_map = expected_value if isinstance(expected_value, Mapping) else {"total": expected_value}
        actual_map = actual_value if isinstance(actual_value, Mapping) else {"total": actual_value}
        for key, target in expected_map.items():
            observed = actual_map.get(key)
            if observed is None:
                failures.append(KpiFailure(metric, str(key), "missing_actual", target))
            elif abs(observed - target) > tolerance:
                failures.append(
                    KpiFailure(metric, str(key), "outside_tolerance", target, observed, tolerance)
                )
    if dict(expected.in_service) != dict(actual.in_service):
        failures.append(
            KpiFailure("in_service", "*", "state_mismatch", expected.in_service, actual.in_service)
        )
    return KpiComparison(tuple(failures))
