"""Intérprete cerrado de las fórmulas del registro normativo del VAD (108:RF-16, RF-17, RF-13).

Por qué existe. Las fórmulas del cargo fijo, del VAD de cada nivel, del factor de economía de escala y de la
incorporación del PIDE cambian con cada TdR. Si estuvieran escritas en Python, un periodo nuevo obligaría a cambiar el
código (108:RF-13). Aquí viven como texto en el registro (``config/vad/``) y se evalúan con un intérprete que solo
admite aritmética: números, variables, ``+ - * / **``, paréntesis y ``suma(n, expresión)``. No se usa ``eval``: un
registro alterado no puede ejecutar nada.

``suma(n, expr)`` recorre los años ``n = 1 … N`` del vector que la expresión usa: dentro de ella, una variable que es
una secuencia vale su elemento ``n`` (el primero es el año 1). Todas las secuencias de una suma tienen que tener la
misma longitud, y fuera de una suma una secuencia es un error: así no se suma un vector sin decirlo.

Los errores son :class:`FormulaError` con la fórmula y el motivo (variable que falta, división entre cero, resultado
no finito, sintaxis no admitida): quien calcula los convierte en huecos nombrados, nunca en 0.
"""
from __future__ import annotations

import ast
import math
from typing import Mapping, Sequence, Union

from . import VadError

Valor = Union[float, int, Sequence[float]]
#: Longitud máxima de una fórmula del registro: una fórmula del TdR cabe holgada; un texto mayor no es una fórmula.
LONGITUD_MAXIMA = 2000
_BINARIOS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
             ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b}
_UNARIOS = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}


class FormulaError(VadError):
    """La fórmula no se puede evaluar; el mensaje nombra la fórmula y el motivo."""


def _numero(valor: object, nombre: str, formula: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise FormulaError(f'la variable {nombre} de «{formula}» no es un número: {valor!r}')
    if not math.isfinite(valor):
        raise FormulaError(f'la variable {nombre} de «{formula}» no es finita: {valor!r}')
    return float(valor)


def _es_secuencia(valor: object) -> bool:
    return isinstance(valor, (list, tuple))


def analizar(formula: str) -> ast.Expression:
    """Comprueba que la fórmula solo use lo admitido y devuelve su árbol."""
    if not isinstance(formula, str) or not formula.strip():
        raise FormulaError(f'la fórmula está vacía o no es texto: {formula!r}')
    if len(formula) > LONGITUD_MAXIMA:
        raise FormulaError(f'la fórmula tiene {len(formula)} caracteres; el máximo es {LONGITUD_MAXIMA}')
    try:
        arbol = ast.parse(formula, mode='eval')
    except SyntaxError as exc:
        raise FormulaError(f'la fórmula «{formula}» no se puede leer: {exc.msg}') from None
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Expression, ast.Load, ast.Name, *_BINARIOS, *_UNARIOS)):
            continue
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _BINARIOS:
            continue
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _UNARIOS:
            continue
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)) \
                and not isinstance(nodo.value, bool):
            continue
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == 'suma' \
                and len(nodo.args) == 2 and not nodo.keywords and isinstance(nodo.args[0], ast.Name):
            continue
        raise FormulaError(f'la fórmula «{formula}» usa algo que el intérprete no admite: '
                           f'{type(nodo).__name__} (solo números, variables, + - * / **, paréntesis y suma(n, …))')
    return arbol


def variables(formula: str) -> set[str]:
    """Las variables que la fórmula necesita (sin los índices de ``suma``)."""
    arbol = analizar(formula)
    indices = {n.args[0].id for n in ast.walk(arbol) if isinstance(n, ast.Call)}
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    return nombres - indices - {'suma'}


def evaluar(formula: str, valores: Mapping[str, Valor]) -> float:
    """El valor de la fórmula con ``valores``. Lanza :class:`FormulaError` si no se puede calcular bien."""
    arbol = analizar(formula)
    faltan = sorted(variables(formula) - set(valores))
    if faltan:
        raise FormulaError(f'faltan las variables {", ".join(faltan)} para «{formula}»')

    def ev(nodo: ast.AST, indice: dict[str, int]) -> float:
        if isinstance(nodo, ast.Expression):
            return ev(nodo.body, indice)
        if isinstance(nodo, ast.Constant):
            return float(nodo.value)
        if isinstance(nodo, ast.Name):
            if nodo.id in indice:
                return float(indice[nodo.id])
            valor = valores[nodo.id]
            if _es_secuencia(valor):
                if not indice:
                    raise FormulaError(f'la variable {nodo.id} es una serie por año y en «{formula}» se usa fuera '
                                       'de suma(n, …)')
                (n,) = indice.values()
                return _numero(valor[n - 1], f'{nodo.id}[{n}]', formula)
            return _numero(valor, nodo.id, formula)
        if isinstance(nodo, ast.UnaryOp):
            return _UNARIOS[type(nodo.op)](ev(nodo.operand, indice))
        if isinstance(nodo, ast.BinOp):
            izquierda, derecha = ev(nodo.left, indice), ev(nodo.right, indice)
            if isinstance(nodo.op, ast.Div) and derecha == 0:
                raise FormulaError(f'división entre cero en «{formula}» ({ast.unparse(nodo.right)} = 0)')
            try:
                resultado = _BINARIOS[type(nodo.op)](izquierda, derecha)
            except (OverflowError, ZeroDivisionError) as exc:
                raise FormulaError(f'«{formula}» no da un número ({exc})') from None
            if isinstance(resultado, complex) or not math.isfinite(resultado):
                raise FormulaError(f'«{formula}» no da un número real finito en {ast.unparse(nodo)}')
            return float(resultado)
        if isinstance(nodo, ast.Call):
            if indice:
                raise FormulaError(f'«{formula}» anida una suma dentro de otra; no se admite')
            nombre = nodo.args[0].id
            if nombre in valores:
                raise FormulaError(f'el índice {nombre} de la suma de «{formula}» choca con una variable del cálculo')
            internas = {n.id for n in ast.walk(nodo.args[1]) if isinstance(n, ast.Name)} - {nombre}
            series = {v: valores[v] for v in internas if _es_secuencia(valores[v])}
            if not series:
                raise FormulaError(f'la suma de «{formula}» no usa ninguna serie por año')
            largos = {len(s) for s in series.values()}
            if len(largos) != 1 or 0 in largos:
                raise FormulaError(f'las series de la suma de «{formula}» tienen longitudes distintas o vacías: '
                                   + ', '.join(f'{k}={len(v)}' for k, v in sorted(series.items())))
            return math.fsum(ev(nodo.args[1], {nombre: n}) for n in range(1, largos.pop() + 1))
        raise FormulaError(f'«{formula}»: nodo no admitido {type(nodo).__name__}')  # analizar ya lo impide

    return ev(arbol, {})
