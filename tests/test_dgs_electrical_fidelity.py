from decimal import Decimal

from igea_dgs.dgsio import build_dgs_document, parse_dgs, write_dgs_document
from igea_dgs.domain.feeder import build_strict_feeder_model
from igea_dgs.dgs import write_strict_dgs

from test_phase_model import _dataset


def test_dgs_preserves_line_electrical_data_and_multiplicity(tmp_path):
    feeder = build_strict_feeder_model(_dataset(), "F1")
    path = write_strict_dgs(feeder, tmp_path / "f.dgs")
    tables = parse_dgs(path)
    typ = tables["TypLne"]["rows_dict"][0]
    line = tables["ElmLne"]["rows_dict"][0]

    assert Decimal(typ["bline"]) == feeder.lines[0].b1_us_km
    assert Decimal(typ["rline"]) == feeder.lines[0].r1_ohm_km
    assert line["nlnum"] == "2"
    assert Decimal(line["dline"]) == feeder.lines[0].length_km


def test_missing_transformer_spec_never_creates_typtr2():
    feeder = build_strict_feeder_model(_dataset(), "F1")
    tables = build_dgs_document(feeder).tables

    assert "TypTr2" not in tables or tables["TypTr2"] == ()
