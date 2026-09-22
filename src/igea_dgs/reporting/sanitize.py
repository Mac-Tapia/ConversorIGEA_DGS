"""Sanitización contextual para artefactos destinados a usuarios."""

import html
import json
from typing import Any


def escape_html_text(value: object) -> str:
    return html.escape(str(value), quote=True)


def safe_script_json(value: Any) -> str:
    """JSON válido que no puede cerrar el elemento script contenedor."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def neutralize_spreadsheet_formula(value: object) -> object:
    """Impide que Excel/Calc evalúen texto no confiable como fórmula."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
