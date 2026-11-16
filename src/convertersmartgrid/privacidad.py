"""Patrones que tapan lo que identifica al cliente, al operador o su red (112:RF-2, RF-4; 086:RF-42).

Vivían solo en el paquete de soporte (``web/soporte.py``). El benchmark anonimizado de la spec 112 necesita los
mismos para buscar fugas, y dos copias se habrían separado con el tiempo (constitución, principio 5): aquí hay una
sola, y soporte la importa sin cambiar lo que hace. Ningún patrón nombra a una empresa (principio 13): los términos
de cada una salen de su perfil.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

#: Rutas de Windows (``C:\…``) y UNC (``\\servidor\…``), hasta un separador o una comilla. Tras la unidad, una ruta
#: de Windows no lleva «:», así que esos dos puntos son del mensaje («Falta D:\a.txt: no existe»). Antes se comían
#: el separador y el mensaje anonimizado perdía su sentido (auditoría de la 112 T1; cambia la salida de 086:RF-42).
RUTA_WINDOWS = re.compile(r'(?:[A-Za-z]:|\\\\[^\\/\s]+)[\\/][^\s"\'<>|«»,;:]*')
RUTA_POSIX = re.compile(r'(?<![\w.:/])/(?:[\w.\- ]+/)+[\w.\-]*')
CORREO = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
#: Una IP; la del propio equipo (127.0.0.1) no identifica a nadie y se deja.
IP = re.compile(r'\b(?!127\.0\.0\.1\b)\d{1,3}(?:\.\d{1,3}){3}\b')
#: Códigos de red y de alimentador de cualquier empresa: letras y cifras juntas, en mayúsculas.
CODIGO = re.compile(r'\b[A-ZÑ]{1,6}[-_]?\d{1,6}[A-Z0-9_-]*\b')
#: Lo escrito entre comillas suele ser un nombre: de un cliente, de una SET o de un fichero.
ENTRECOMILLADO = re.compile(r'«[^»]*»|"[^"]*"|\'[^\']*\'')


class PerfilIlegible(ValueError):
    """El perfil de la empresa existe y no se puede leer, o se pidió uno que no está: sus términos son desconocidos.

    No se traduce en «ningún término»: con un conjunto vacío, el nombre de la empresa pasaría sin tapar y sin que nadie lo
    supiera. Quien lo pide decide: el benchmark no se emite y el paquete de soporte deja fuera lo que no puede tapar.
    """

    def __init__(self, ruta: Path, causa: str):
        self.ruta = Path(ruta)
        self.causa = causa
        super().__init__(f'el perfil de la empresa {self.ruta} {causa}: no se sabe qué nombres tapar')


def terminos_del_perfil(ruta: Path, *, obligatorio: bool = False) -> set[str]:
    """Los textos del perfil de una empresa (de tres caracteres o más), que pueden salir en cualquier mensaje.

    Sin perfil no hay términos, y devuelve un conjunto vacío, salvo con ``obligatorio``: quien pidió un perfil concreto
    tiene que saber que no está. Un perfil que existe y no se lee lanza :class:`PerfilIlegible` con la causa (112:RF-4).
    """
    ruta = Path(ruta)
    try:
        texto = ruta.read_bytes().decode('utf-8-sig')
    except FileNotFoundError:
        if obligatorio:
            raise PerfilIlegible(ruta, 'no existe') from None
        return set()
    except UnicodeDecodeError as exc:
        raise PerfilIlegible(ruta, f'no está en UTF-8 ({exc.reason} en el byte {exc.start})') from exc
    except OSError as exc:
        raise PerfilIlegible(ruta, f'no se puede leer ({type(exc).__name__}: {exc.strerror or exc})') from exc
    try:
        datos = json.loads(texto)
    except ValueError as exc:
        raise PerfilIlegible(ruta, f'no es JSON válido ({exc})') from exc

    def textos(x: Any) -> Iterator[str]:
        if isinstance(x, dict):
            for v in x.values():
                yield from textos(v)
        elif isinstance(x, list):
            for v in x:
                yield from textos(v)
        elif isinstance(x, str) and len(x.strip()) >= 3:
            yield x.strip()

    return set(textos(datos))


def anonimizar(linea: str, terminos: Iterable[str] = ()) -> str:
    """Sustituye lo que pueda identificar al cliente, al operador o su red; conserva el mensaje y la cifra."""
    salida = linea
    # Los más largos primero: «Empresa Norte» antes que «Norte».
    for termino in sorted(set(terminos), key=len, reverse=True):
        salida = re.sub(re.escape(termino), '<nombre>', salida, flags=re.IGNORECASE)
    salida = RUTA_WINDOWS.sub('<ruta>', salida)
    salida = RUTA_POSIX.sub('<ruta>', salida)
    salida = CORREO.sub('<correo>', salida)
    salida = IP.sub('<ip>', salida)
    salida = ENTRECOMILLADO.sub('<texto>', salida)
    return CODIGO.sub('<codigo>', salida)
