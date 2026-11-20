"""086:RF-110 (revisión web W5b, 2026-11-19): el servidor tampoco escribe «palabra(s)» ni «palabra(es)».

La web ya lo comprueba en ``frontend/test/sinPluralEntreParentesis.test.mjs`` (086 T89), pero los mensajes que
llegan del servidor (``detail`` de HTTPException, avisos, motivos, registros de los trabajos, textos de informes y
cabeceras de los libros) traían unas 230 apariciones: «Máxima de cabecera (… medidor(es))», «12 alimentador(es) no
se pudieron construir». Se leen con ``ast`` los literales de ``src/convertersmartgrid`` —también los trozos de las
f-strings—, sin docstrings ni comentarios. Un patrón de expresión regular, ``medidor(es)?``, es código y no cuenta.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from convertersmartgrid.dominio.util import cuenta, plural

RAIZ = Path(__file__).resolve().parents[1] / 'src' / 'convertersmartgrid'

#: Una palabra con su plural entre paréntesis; seguida de «?» es el grupo opcional de una expresión regular.
PLURAL_ENTRE_PARENTESIS = re.compile(r'[^\W\d_]+\((?:s|es|as|os|S|ES|AS|OS)\)(?!\?)')

#: (fichero relativo a ``src/convertersmartgrid``, texto exacto) que la norma escribe así y se conserva.
#: Hoy no hay ninguno: los formatos oficiales de Osinergmin que se reproducen no llevan el plural entre paréntesis.
LISTA_BLANCA: frozenset[tuple[str, str]] = frozenset()


def _docstrings(arbol: ast.AST) -> set[int]:
    tipos = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {id(n.body[0].value) for n in ast.walk(arbol)
            if isinstance(n, tipos) and n.body and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str)}


def plurales_entre_parentesis(texto: str) -> list[tuple[int, str]]:
    """[(línea, palabra)] de cada «palabra(s)» en los literales de ``texto``, sin docstrings ni comentarios."""
    arbol = ast.parse(texto)
    fuera = _docstrings(arbol)
    hallados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in fuera:
            hallados += [(nodo.lineno, m) for m in PLURAL_ENTRE_PARENTESIS.findall(nodo.value)]
    return sorted(hallados)


def test_086_rf110_el_detector_separa_el_texto_del_codigo_y_de_los_comentarios():
    muestra = '\n'.join([
        '"""Docstring con fichero(s): no es texto de la web."""',
        '# un comentario con fichero(s) no cuenta',
        "PATRON = r'\\bmedidor(es)?\\b'",
        "a = 'Faltan 3 dato(s)'",
        "b = f'{n} alimentador(es) y {m} cliente(s)'",
        "c = 'interruptor NORMALMENTE ABIERTO(S)'",
        "d = f(s) + nombre(s)",
    ])
    assert plurales_entre_parentesis(muestra) == [
        (4, 'dato(s)'), (5, 'alimentador(es)'), (5, 'cliente(s)'), (6, 'ABIERTO(S)')]


def test_086_rf110_ningun_texto_del_servidor_lleva_el_plural_entre_parentesis():
    malos = []
    for fichero in sorted(RAIZ.rglob('*.py')):
        rel = fichero.relative_to(RAIZ).as_posix()
        for linea, palabra in plurales_entre_parentesis(fichero.read_text(encoding='utf-8')):
            if (rel, palabra) not in LISTA_BLANCA:
                malos.append(f'{rel}:{linea}: {palabra}')
    assert not malos, f'{len(malos)} textos con el plural entre paréntesis:\n' + '\n'.join(malos)


def test_086_rf110_cuenta_y_plural_concuerdan_con_uno_y_con_varios():
    assert cuenta(1, 'alimentador', 'alimentadores') == '1 alimentador'
    assert cuenta(12, 'alimentador', 'alimentadores') == '12 alimentadores'
    assert cuenta(0, 'carga', 'cargas') == '0 cargas'
    assert cuenta(1, 'libro nuevo', 'libros nuevos') == '1 libro nuevo'
    assert plural(1, 'fallo', 'fallos') == 'fallo'
    assert plural(5, 'fallo', 'fallos') == 'fallos'
    assert plural(1.0, 'kW', 'kW') == 'kW'
    assert plural(None, 'dato', 'datos') == 'datos'
