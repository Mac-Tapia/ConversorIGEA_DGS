from pathlib import Path

from igea_dgs.ingestion import RED_CONTRACT, parse_igea_file


def _write(tmp_path: Path, text: str, raw: bool = False) -> Path:
    path = tmp_path / "RED.txt"
    if raw:
        path.write_bytes(text.encode("latin-1"))
    else:
        path.write_text(text, encoding="utf-8")
    return path


def test_duplicate_node_is_blocking(tmp_path):
    path = _write(
        tmp_path,
        "[NODE]\nFORMAT_NODE=NodeID,CoordX,CoordY\nN1,1,2\nN1,3,4\n",
    )
    parsed = parse_igea_file(path, RED_CONTRACT)

    assert parsed.gate.blocked
    assert "DUPLICATE_KEY" in {item.code for item in parsed.gate.diagnostics}


def test_unknown_section_and_invalid_utf8_are_blocking(tmp_path):
    unknown = parse_igea_file(_write(tmp_path, "[MYSTERY]\nFORMAT_X=A\n1\n"), RED_CONTRACT)
    assert "UNKNOWN_SECTION" in {item.code for item in unknown.gate.diagnostics}

    invalid = parse_igea_file(_write(tmp_path, "[NODE]\nniño\n", raw=True), RED_CONTRACT)
    assert "INVALID_ENCODING" in {item.code for item in invalid.gate.diagnostics}


def test_extra_column_is_preserved_and_blocking(tmp_path):
    parsed = parse_igea_file(
        _write(tmp_path, "[NODE]\nFORMAT_NODE=NodeID,CoordX\nN1,1,UNDECLARED\n"),
        RED_CONTRACT,
    )

    record = parsed.records[0]
    assert record.original_text == "N1,1,UNDECLARED"
    assert record.extra_columns == ("UNDECLARED",)
    assert "EXTRA_COLUMN" in {item.code for item in parsed.gate.diagnostics}
