#!/usr/bin/env python
"""Concordancia de número en los textos de los guiones de ``tools/`` (086:RF-110, T104).

Los avisos y el resumen que escriben los guiones, también los que corren dentro de DIgSILENT PowerFactory con su
propio intérprete, llegan a la web y al Registro: no llevan «alimentador(es)» ni «carga(s)». ``cuenta(3, 'carga',
'cargas')`` da «3 cargas» y ``plural`` da solo la forma que concuerda, para el adjetivo o el verbo que la acompañan.
Es la regla de ``plural`` y ``cuenta`` de ``frontend/src/shared/formato.ts``, con la biblioteca estándar de Python
3.9 para que la importe cualquier guion de ``tools/`` sin el paquete instalado.

    python tools/_plural.py 3 carga cargas
"""

from __future__ import annotations

import argparse
from typing import Any, Optional, Sequence


def plural(n: Any, uno: str, varios: str) -> str:
    """La forma que concuerda con ``n``: ``uno`` con 1 y ``varios`` con cualquier otro número.

    Con adjetivo, la frase entera: ``plural(n, 'carga nueva', 'cargas nuevas')``. Lo que no es un número
    toma el plural.
    """
    try:
        return uno if float(n) == 1 else varios
    except (TypeError, ValueError):
        return varios


def cuenta(n: Any, uno: str, varios: str) -> str:
    """El número con su palabra: «1 carga», «3 cargas»."""
    return f'{n} {plural(n, uno, varios)}'


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Escribe un número con la forma de la palabra que concuerda con él.')
    parser.add_argument('numero', help='la cuenta, p. ej. 3')
    parser.add_argument('uno', help='la forma del singular, p. ej. carga')
    parser.add_argument('varios', help='la forma del plural, p. ej. cargas')
    args = parser.parse_args(argv)
    print(cuenta(args.numero, args.uno, args.varios))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
