from types import SimpleNamespace

import pytest

from igea_dgs.domain.lengths import LengthPolicy, apply_length_policy
from igea_dgs.model import FeederModel, Line, Node


def _model(x2: float, y2: float, txt_length: float = 123.0) -> FeederModel:
    line = Line("S1", "N1", "N2", "ABC", "LINE:L1", "L1", txt_length, True, txt_length, "txt")
    return FeederModel(
        "F1", "NET_F1", 13.2, "N1", {"N1": Node("N1", 0.0, 0.0), "N2": Node("N2", x2, y2)},
        [line], [], [], {}, section_by_id={"S1": line}
    )


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:2230"])
def test_non_metric_crs_never_replaces_txt_length_implicitly(crs):
    model = _model(1.0, 0.0)
    dataset = SimpleNamespace(intermediate_nodes=[])

    result = apply_length_policy(model, dataset, crs, LengthPolicy.TXT_AUTHORITATIVE)

    assert all(line.length_source == "txt" for line in result.lines)
    assert result.lines[0].length_m == 123.0


def test_projected_feet_are_converted_to_metres_explicitly():
    model = _model(1.0, 0.0)
    dataset = SimpleNamespace(intermediate_nodes=[])

    result = apply_length_policy(model, dataset, "EPSG:2230", LengthPolicy.PROJECTED_VALIDATED)

    assert result.lines[0].length_source == "projected_validated"
    assert result.lines[0].length_m == pytest.approx(0.3048006096)


def test_cli_defaults_to_txt_authoritative_length_policy():
    from igea_dgs.cli import _parser

    args = _parser().parse_args(
        ["convert", "--red", "r", "--loads", "l", "--equipment", "e", "--all", "--out-dir", "o"]
    )
    assert args.length_policy == LengthPolicy.TXT_AUTHORITATIVE.value
