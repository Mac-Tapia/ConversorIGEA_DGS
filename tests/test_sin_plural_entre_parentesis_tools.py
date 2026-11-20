"""086:RF-110 (T104, revisión web del 2026-11-19): los guiones de ``tools/`` tampoco escriben «palabra(s)».

La web (``frontend/test/sinPluralEntreParentesis.test.mjs``, T89) y el servidor (T101) ya concuerdan la cuenta, pero los
avisos de los guiones llegan igual a la web y al Registro: los de DIgSILENT («3 SED fija(s) piden más…», «1 banco(s) de
300 kvar»), el escaneo, el diagnóstico de un ``.pfd`` y los resúmenes de entrenamiento traían 86 apariciones en 22
guiones. Se leen con ``ast`` los literales de ``tools/`` (también los trozos de las f-strings), sin docstrings ni
comentarios; un grupo opcional de expresión regular, ``medidor(es)?``, es código y no cuenta. La concordancia la da
``tools/_plural.py``, con la biblioteca estándar de Python 3.9 porque los guiones de DIgSILENT corren con el intérprete
de PowerFactory.
"""
from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TOOLS = RAIZ / 'tools'

#: Una palabra con su plural entre paréntesis; seguida de «?» es el grupo opcional de una expresión regular.
PLURAL_ENTRE_PARENTESIS = re.compile(r'[^\W\d_]+\((?:s|es|as|os|S|ES|AS|OS)\)(?!\?)')

#: (fichero relativo a ``tools/``, texto exacto) que se conserva por ser una fórmula, una unidad o un texto oficial que
#: se reproduce tal cual. Hoy no hay ninguno: ningún guion copia un formato de Osinergmin con el plural entre paréntesis.
LISTA_BLANCA: frozenset[tuple[str, str]] = frozenset()

#: Lo único que importa el ayudante: lo trae cualquier Python 3.9, también el de PowerFactory.
IMPORTS_DEL_AYUDANTE = {'__future__', 'argparse', 'typing'}


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


def _ayudante():
    ruta = TOOLS / '_plural.py'
    assert ruta.is_file(), 'falta tools/_plural.py: los guiones no tienen con qué concordar la cuenta'
    spec = importlib.util.spec_from_file_location('_plural_t104', ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_086_rf110_el_detector_de_tools_separa_el_texto_del_codigo_y_de_los_comentarios():
    muestra = '\n'.join([
        '"""Guion de DIgSILENT con banco(s): la docstring no llega a la web."""',
        '# un comentario con carga(s) no cuenta',
        "PATRON = r'\\bmedidor(es)?\\b'",
        "a = 'Faltan 3 dato(s)'",
        "b = f'{n} alimentador(es) y {m} SED fija(s)'",
        "c = 'interruptor NORMALMENTE ABIERTO(S)'",
        "d = f(s) + nombre(s)",
    ])
    assert plurales_entre_parentesis(muestra) == [
        (4, 'dato(s)'), (5, 'alimentador(es)'), (5, 'fija(s)'), (6, 'ABIERTO(S)')]


def test_086_rf110_ningun_texto_de_los_guiones_lleva_el_plural_entre_parentesis():
    malos = []
    for fichero in sorted(TOOLS.rglob('*.py')):
        if '__pycache__' in fichero.parts:
            continue
        rel = fichero.relative_to(TOOLS).as_posix()
        for linea, palabra in plurales_entre_parentesis(fichero.read_text(encoding='utf-8')):
            if (rel, palabra) not in LISTA_BLANCA:
                malos.append(f'tools/{rel}:{linea}: {palabra}')
    assert not malos, f'{len(malos)} textos de tools/ con el plural entre paréntesis:\n' + '\n'.join(malos)


def test_086_rf110_el_ayudante_de_tools_concuerda_con_uno_y_con_varios():
    p = _ayudante()
    assert p.cuenta(1, 'banco', 'bancos') == '1 banco'
    assert p.cuenta(3, 'banco', 'bancos') == '3 bancos'
    assert p.cuenta(0, 'carga nueva', 'cargas nuevas') == '0 cargas nuevas'
    assert p.cuenta('1', 'fase', 'fases') == '1 fase'
    assert p.plural(1, 'fija pide', 'fijas piden') == 'fija pide'
    assert p.plural(2.0, 'fija pide', 'fijas piden') == 'fijas piden'
    assert p.plural(None, 'dato', 'datos') == 'datos'


def test_086_rf110_el_ayudante_solo_usa_la_biblioteca_estandar_de_python_39():
    """Lo importan los guiones que corren dentro de PowerFactory (103:RF-5), sin el paquete ni librerías de terceros."""
    ruta = TOOLS / '_plural.py'
    assert ruta.is_file(), 'falta tools/_plural.py'
    texto = ruta.read_text(encoding='utf-8')
    arbol = ast.parse(texto, feature_version=(3, 9))
    importados = {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    importados |= {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
    assert importados <= IMPORTS_DEL_AYUDANTE, importados - IMPORTS_DEL_AYUDANTE


def test_086_rf110_los_guiones_que_concuerdan_importan_el_ayudante():
    """Cada guion que llama a ``cuenta`` o ``plural`` lo trae de ``tools/_plural.py``, no de una copia propia."""
    sin_importar, copias = [], []
    for fichero in sorted(TOOLS.glob('*.py')):
        if fichero.name == '_plural.py':
            continue
        arbol = ast.parse(fichero.read_text(encoding='utf-8'))
        llama = {n.func.id for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        definidas = {n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}
        traidas = {a.asname or a.name for n in ast.walk(arbol)
                   if isinstance(n, ast.ImportFrom) and n.module == '_plural' for a in n.names}
        if {'cuenta', 'plural'} & definidas:
            copias.append(fichero.name)
        elif ({'cuenta', 'plural'} & llama) - traidas:
            sin_importar.append(fichero.name)
    assert not copias, f'copias de cuenta/plural fuera de tools/_plural.py: {copias}'
    assert not sin_importar, f'llaman a cuenta/plural sin importarlo de _plural: {sin_importar}'
