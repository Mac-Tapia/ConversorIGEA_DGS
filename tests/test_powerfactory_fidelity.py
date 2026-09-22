from copy import deepcopy
from decimal import Decimal

from igea_dgs.domain.equipment import CircuitMultiplicity, OverheadLine, SourceSpec
from igea_dgs.domain.feeder import StrictFeederModel
from igea_dgs.domain.phases import PhaseSet
from igea_dgs.powerfactory.studies import (
    run_diagnostic_copy,
    run_original_load_flow,
    run_short_circuit_if_complete,
)
from igea_dgs.validation import inspect_and_validate_pf


class StudyPort:
    def __init__(self, converged=False, licensed=True):
        self.objects = [
            {
                "class_name": "ElmLne",
                "external_id": "L1",
                "from_node": "N1",
                "to_node": "N2",
                "phases": "ABC",
                "circuits": 2,
                "conductors_per_phase": 1,
                "length_km": Decimal("1.25"),
                "cross_section_mm2": Decimal("70"),
                "outserv": 0,
            }
        ]
        self.converged = converged
        self.licensed = licensed
        self.copy_names = []

    def list_objects(self, class_name):
        return [x for x in self.objects if x["class_name"] == class_name]

    def snapshot(self):
        return deepcopy(self.objects)

    def run_load_flow(self):
        return self.converged

    def create_diagnostic_copy(self, name):
        self.copy_names.append(name)
        return self

    def run_short_circuit(self):
        if not self.licensed:
            raise PermissionError("ComShc licence unavailable")
        return True


def feeder():
    line = OverheadLine(
        "L1", "N1", "N2", PhaseSet.ABC, "CAT-1", Decimal("1.25"),
        CircuitMultiplicity(2), 1, Decimal("70"), Decimal("0.1"),
        Decimal("0.2"), Decimal("0.3"), Decimal("0.4"), Decimal("1"),
        Decimal("2"), Decimal("200"),
    )
    return StrictFeederModel(
        "F1", SourceSpec("SRC", "N1", Decimal("13.2")), (line,), ()
    )


def test_original_case_is_not_mutated_when_load_flow_diverges():
    fake_pf = StudyPort(converged=False)
    before = fake_pf.snapshot()

    result = run_original_load_flow(fake_pf, feeder())

    assert result.converged is False
    assert fake_pf.snapshot() == before


def test_diagnostic_copy_has_distinct_traceable_name():
    fake_pf = StudyPort()
    result = run_diagnostic_copy(fake_pf, feeder(), run_id="RUN-7")
    assert result.copy_name == "F1__diagnostic__RUN-7"
    assert fake_pf.copy_names == [result.copy_name]


def test_short_circuit_blocks_without_source_impedance():
    result = run_short_circuit_if_complete(StudyPort(), feeder().source)
    assert result.status == "blocked"
    assert "SOURCE_SHORT_CIRCUIT_DATA_MISSING" in result.error_codes


def test_short_circuit_distinguishes_missing_licence():
    source = {
        "source_id": "SRC", "r0_ohm": "0.1", "x0_ohm": "0.2",
        "r1_ohm": "0.1", "x1_ohm": "0.2", "short_circuit_mva": "100",
    }
    result = run_short_circuit_if_complete(StudyPort(licensed=False), source)
    assert result.status == "unavailable"
    assert result.error_codes == frozenset({"POWERFACTORY_SHORT_CIRCUIT_LICENCE_UNAVAILABLE"})


def test_effective_pf_objects_are_compared_independently():
    fake_pf = StudyPort()
    assert not inspect_and_validate_pf(feeder(), fake_pf).blocked
    fake_pf.objects[0]["circuits"] = 1
    assert "PF_CIRCUIT_COUNT_MISMATCH" in inspect_and_validate_pf(feeder(), fake_pf).error_codes
