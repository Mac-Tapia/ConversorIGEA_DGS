"""Libros de demanda por año de medición (spec 025, RF-1 a RF-3, RF-7 a RF-9, RF-26, RF-27).

La empresa entrega la medición de cabecera y los clientes importantes por año: el usuario
creó en cada carpeta una subcarpeta ``2025``, otra ``2026``, y vendrán más años, libros y
subcarpetas (2026-10-23). Hasta esta spec solo se miraba el primer nivel, así que con las
subcarpetas no se encontraba ningún libro.

Un año es una carpeta de cuatro cifras a cualquier altura bajo la elegida; un libro es del
año más cercano por encima de él. Los libros sin carpeta de año quedan sin año y valen para
todos, como antes. Solo se listan ficheros, sin abrirlos: listar ha de ser barato aunque
los libros pesen cientos de MB (P7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .demanda_medida import EXTENSIONES, DemandaError

_ANIO = re.compile(r'\d{4}')
_PERIODO = re.compile(r'(?P<anio>\d{4})(?:-(?P<mes>0[1-9]|1[0-2]))?')


@dataclass(frozen=True)
class LibroDeAnio:
    ruta: Path
    #: Ruta relativa a la carpeta elegida, con «/»: dos años pueden traer libros con el
    #: mismo nombre (RF-3).
    relativa: str
    anio: int | None


def es_libro(path: Path) -> bool:
    """Un libro de Excel que no es el fichero de bloqueo de uno abierto (``~$``)."""
    return path.is_file() and path.suffix.lower() in EXTENSIONES and not path.name.startswith('~$')


def _anio_de(partes: Sequence[str]) -> int | None:
    for parte in reversed(partes):
        if _ANIO.fullmatch(parte):
            return int(parte)
    return None


def arbol_de_libros(carpeta: Path | str) -> list[LibroDeAnio]:
    """Cada libro bajo ``carpeta``, a cualquier profundidad, con su año (RF-1, RF-26).

    Ordenado por ruta relativa, primero sin mayúsculas: el mismo árbol da siempre el mismo
    orden, se lea donde se lea.
    """
    raiz = Path(carpeta)
    if not raiz.is_dir():
        raise DemandaError(f'No existe la carpeta: {raiz}')
    libros = []
    for path in raiz.rglob('*'):
        if not es_libro(path):
            continue
        rel = path.relative_to(raiz)
        libros.append(LibroDeAnio(path, rel.as_posix(), _anio_de(rel.parts[:-1])))
    return sorted(libros, key=lambda x: (x.relativa.casefold(), x.relativa))


def anios_de(libros: Iterable[LibroDeAnio]) -> list[int]:
    """Años con algún libro, ordenados (RF-4)."""
    return sorted({x.anio for x in libros if x.anio is not None})


def anio_del_periodo(periodo: str) -> int:
    """Año de un periodo ``AAAA`` o ``AAAA-MM`` (RF-7)."""
    hallado = _PERIODO.fullmatch(str(periodo).strip())
    if hallado is None:
        raise DemandaError(f'Periodo no válido {periodo!r}: use AAAA (el año) o AAAA-MM (un mes).')
    return int(hallado.group('anio'))


def libros_del_periodo(libros: Sequence[LibroDeAnio], periodo: str | None) -> list[LibroDeAnio]:
    """Los libros del año del periodo y los que no tienen año (RF-8).

    Sin periodo y con carpetas de año no se elige nada: buscar la máxima en todos mezclaría
    años (RF-9).
    """
    if not periodo:
        if anios_de(libros):
            raise DemandaError('La carpeta tiene libros de varios años ('
                               + ', '.join(map(str, anios_de(libros)))
                               + '): elija el año o el mes de las mediciones.')
        return list(libros)
    anio = anio_del_periodo(periodo)
    return [x for x in libros if x.anio in (None, anio)]
