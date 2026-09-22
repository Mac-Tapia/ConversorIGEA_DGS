import csv
import io

from hypothesis import HealthCheck, given, settings, strategies as st

from igea_dgs.ingestion import RED_CONTRACT, parse_igea_file


@given(
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Zs")),
        max_size=40,
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_parser_never_drops_extra_columns_silently(tmp_path, extra):
    stream = io.StringIO()
    csv.writer(stream, lineterminator="").writerow(["N1", "1", extra])
    path = tmp_path / "RED.txt"
    path.write_text(
        "[NODE]\nFORMAT_NODE=NodeID,CoordX\n" + stream.getvalue() + "\n",
        encoding="utf-8",
    )

    parsed = parse_igea_file(path, RED_CONTRACT)

    assert parsed.records[0].original_text == stream.getvalue()
    assert parsed.records[0].extra_columns == (extra.strip(),)
    assert any(item.code == "EXTRA_COLUMN" for item in parsed.gate.diagnostics)
