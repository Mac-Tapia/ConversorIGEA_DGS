"""Spec 072: los nombres de empresas y clientes son casos de prueba, nunca valores del código (RF-20).

Un comentario puede contar el caso real que motivó una regla (así lo pide el proyecto); un valor no puede
llevarlos, porque entonces la herramienta solo serviría para esa empresa. Los perfiles de empresa son el
sitio de esos nombres y por eso quedan fuera.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NOMBRES = re.compile(r"inka'?s?\b|casa blanca|santa mar[ií]a|electro ?oriente|\belor\b|electro ?dunas|\beldu\b|copara", re.IGNORECASE)


def valores_con_nombres(codigo: str) -> list[tuple[int, str]]:
    """Las cadenas del programa con un nombre de caso, sin docstrings ni comentarios."""
    arbol = ast.parse(codigo)
    docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [(n.lineno, n.value) for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
            and NOMBRES.search(n.value)]


def test_el_detector_ve_un_valor_y_respeta_comentarios_y_docstrings():
    """072:RF-20 — sin este control, un detector roto daría la siguiente prueba por buena."""
    assert valores_con_nombres("EMPRESA = 'Electro Dunas'\n") == [(1, 'Electro Dunas')]
    assert valores_con_nombres('"""Caso: INKA."""\n# ELOR, Casa Blanca\nx = 1\n') == []


def test_el_codigo_no_lleva_nombres_de_casos_como_valores():
    """072:RF-20 — ni en `src/` ni en `tools/`."""
    hallados = [f'{p.relative_to(RAIZ)}:{linea}: {valor[:60]!r}'
                for carpeta in ('src/convertersmartgrid', 'tools') for p in sorted((RAIZ / carpeta).rglob('*.py'))
                for linea, valor in valores_con_nombres(p.read_text(encoding='utf-8'))]
    assert not hallados, '\n'.join(hallados)


def test_la_metodologia_universal_no_lleva_nombres_de_casos():
    """072:RF-20 — la configuración que vale para toda distribuidora."""
    assert not NOMBRES.search((RAIZ / 'config/pide_universal_2017.json').read_text(encoding='utf-8'))


def test_la_arquitectura_lo_declara():
    """072:RF-20 — la regla consta donde se explica el sistema."""
    texto = (RAIZ / 'docs/ARQUITECTURA.md').read_text(encoding='utf-8')
    assert '**Casos de prueba:**' in texto and '072:RF-20' in texto


def test_la_lista_negra_no_nombra_a_ninguna_empresa():
    """081:RF-62, 077:RF-20 — ni la empresa ni su carpeta de datos: lo que está fuera del árbol ya se rechaza."""
    from convertersmartgrid.asistente.lectura_proyecto import SEGMENTOS_NEGROS

    assert not [s for s in SEGMENTOS_NEGROS if NOMBRES.search(s) or s[:9] == 'basedatos' or s.startswith('referencia_')]
