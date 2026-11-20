"""La referencia de soporte de una petición, que viaja a su trabajo, al motor y al informe (086:RF-127).

Cada petición de la API recibe una referencia (``trace_id``): la trae el cliente en ``X-CSG-Traza`` si es válida, y si
no se crea. El trabajo que la petición encola la hereda; el motor la recibe en ``CSG_TRAZA`` (los guiones de
DIgSILENT y los procesos del motor, que la apuntan en su registro), y el informe la lleva en sus metadatos. El
operador la copia desde la web y con ella se encuentra, en el soporte, todo lo que hizo esa petición.

Sin E/S ni dependencias: la usan la presentación, los adaptadores y los guiones por igual.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import re
import uuid
from collections.abc import Iterator

#: La cabecera de la petición y de la respuesta.
CABECERA = 'X-CSG-Traza'
#: La variable de entorno con que la recibe un proceso del motor.
VARIABLE = 'CSG_TRAZA'
#: Lo que se admite de fuera: letras, cifras, guion y guion bajo, de 8 a 64; nada que rompa un registro o una cabecera.
_VALIDA = re.compile(r'[A-Za-z0-9_-]{8,64}')

_ACTUAL: contextvars.ContextVar[str | None] = contextvars.ContextVar('csg_traza', default=None)


def nueva() -> str:
    """Una referencia nueva: 32 cifras hexadecimales."""
    return uuid.uuid4().hex


def valida(valor: object) -> str | None:
    """La referencia si es admisible, o ``None``: una de fuera nunca entra tal cual si no cumple el formato."""
    if isinstance(valor, str) and _VALIDA.fullmatch(valor.strip()):
        return valor.strip()
    return None


def actual() -> str | None:
    """La referencia en curso: la del contexto (petición o trabajo) o, en un proceso del motor, la de ``CSG_TRAZA``."""
    return _ACTUAL.get() or valida(os.environ.get(VARIABLE))


@contextlib.contextmanager
def en_traza(valor: str | None) -> Iterator[str | None]:
    """Fija la referencia mientras dura el bloque; una no válida deja la que hubiera."""
    referencia = valida(valor)
    if referencia is None:
        yield actual()
        return
    marca = _ACTUAL.set(referencia)
    try:
        yield referencia
    finally:
        _ACTUAL.reset(marca)
