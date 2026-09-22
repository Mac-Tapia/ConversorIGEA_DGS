import json

import pytest

from igea_dgs.reporting.sanitize import (
    escape_html_text,
    neutralize_spreadsheet_formula,
    safe_script_json,
)


@pytest.mark.parametrize(
    "value",
    ["</script><script>alert(1)</script>", '=WEBSERVICE("https://example.invalid")', "+CMD|' /C calc'!A0"],
)
def test_untrusted_identifier_cannot_execute_in_exports(value):
    html = f"<script>const data={safe_script_json({'name': value})};</script>"
    cell = neutralize_spreadsheet_formula(value)
    assert "</script><script>" not in html
    assert not cell.startswith(("=", "+", "-", "@"))


def test_html_text_is_escaped_and_json_value_round_trips():
    value = '<img src=x onerror="alert(1)">'
    assert escape_html_text(value) == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
    encoded = safe_script_json({"name": value})
    assert json.loads(encoded)["name"] == value
