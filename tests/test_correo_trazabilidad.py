"""Spec 110, T13: la tabla de trazabilidad de ``plan.md`` lleva cada RF a pruebas que existen y lo citan.

La tabla es la evidencia de T13 que queda en el repositorio; esta prueba impide que se quede vieja: una prueba
renombrada, borrada o que deja de citar su RF la rompe. Que esas pruebas pasen lo dice su propia corrida.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / 'specs' / '110-envio-de-informes-por-correo-desde-la-web'
FILA = re.compile(r'^\| RF-(\d+) \| (.+?) \|\s*$')
PRUEBA = re.compile(r'`(tests/[\w./]+\.py)::(\w+)`')
CITA = re.compile(r'110:(RF-\d+(?:(?:, | y | a )RF-\d+)*)')


def _rf_de_la_spec() -> set[int]:
    texto = (SPEC / 'spec.md').read_text(encoding='utf-8')
    return {int(n) for n in re.findall(r'^- RF-(\d+):', texto, re.M)}


def _tabla() -> dict[int, list[tuple[str, str]]]:
    texto = (SPEC / 'plan.md').read_text(encoding='utf-8')
    assert '## Trazabilidad (T13)' in texto, 'plan.md sin la sección «## Trazabilidad (T13)»'
    seccion = texto.split('## Trazabilidad (T13)', 1)[1].split('\n## ', 1)[0]
    filas = {}
    for linea in seccion.splitlines():
        m = FILA.match(linea)
        if m:
            filas[int(m.group(1))] = PRUEBA.findall(m.group(2))
    return filas


def _citados(doc: str | None) -> set[int]:
    salida = set()
    for m in CITA.finditer(doc or ''):
        texto = m.group(1)
        salida |= {int(n) for n in re.findall(r'RF-(\d+)', texto)}
        for a, b in re.findall(r'RF-(\d+) a RF-(\d+)', texto):
            salida |= set(range(int(a), int(b) + 1))
    return salida


def _docstrings(fichero: str) -> dict[str, str | None]:
    arbol = ast.parse((RAIZ / fichero).read_text(encoding='utf-8'))
    return {n.name: ast.get_docstring(n) for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}


def test_cada_rf_de_la_110_tiene_su_fila():
    """110:RF-1 a RF-14 (T13) — una fila por RF de la spec, ni más ni menos, y cada una con al menos una prueba."""
    rf = _rf_de_la_spec()
    assert rf == set(range(1, 15)), sorted(rf)
    filas = _tabla()
    assert set(filas) == rf, sorted(set(filas) ^ rf)
    assert all(filas[n] for n in rf), [n for n in rf if not filas[n]]


def test_cada_prueba_de_la_tabla_existe_y_cita_su_rf():
    """110:RF-1 a RF-14 (T13) — la prueba nombrada existe en su fichero y su docstring cita ese RF de la 110."""
    malas = []
    cache: dict[str, dict[str, str | None]] = {}
    for n, pruebas in _tabla().items():
        for fichero, nombre in pruebas:
            if not (RAIZ / fichero).is_file():
                malas.append(f'RF-{n}: no existe {fichero}')
                continue
            docs = cache.setdefault(fichero, _docstrings(fichero))
            if nombre not in docs:
                malas.append(f'RF-{n}: no existe {fichero}::{nombre}')
            elif n not in _citados(docs[nombre]):
                malas.append(f'RF-{n}: {fichero}::{nombre} no cita 110:RF-{n}')
    assert not malas, malas
