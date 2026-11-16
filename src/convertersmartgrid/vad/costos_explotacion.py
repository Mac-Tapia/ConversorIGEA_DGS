"""VNR no eléctrico y costos de explotación de la empresa modelo, por rubro del TdR (108:RF-19).

El TdR (numerales 6.8.3 y 6.13 a 6.15) pide **dimensionar** el VNR no eléctrico y los costos comerciales, indirectos y
adicionales de la empresa modelo; el costo real de la empresa sirve de referencia, nunca de estándar. Los rubros
salen del registro (``vad.explotacion.rubros``: clave, nombre y numeral), no del código.

Cada partida dimensionada trae su cantidad, su costo unitario, su moneda y su **fuente** (de dónde sale el costo
unitario). El total estándar de un rubro es la suma de sus partidas dimensionadas; el costo real va en otra columna,
rotulada como referencia, y nunca entra en el total. Un rubro que solo trae el costo real queda «sin dimensionar» y
fuera del total. Dos monedas no se suman.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..registro_normativo import RegistroError, RegistroNormativo
from . import VadError

#: Rótulo de la columna del costo real: lo que se escribe en cualquier tabla que lo muestre.
ROTULO_REAL = 'Referencia: costo real de la empresa (no es costo estándar)'


@dataclass(frozen=True)
class Rubro:
    clave: str
    nombre: str
    numeral: str


@dataclass(frozen=True)
class Partida:
    descripcion: str
    cantidad: float
    costo_unitario: float
    moneda: str
    fuente: str

    def __post_init__(self) -> None:
        if not self.descripcion.strip():
            raise VadError('una partida dimensionada necesita su descripción')
        if not self.fuente.strip():
            raise VadError(f'la partida «{self.descripcion}» no dice de dónde sale su costo unitario (fuente)')
        if not self.moneda.strip():
            raise VadError(f'la partida «{self.descripcion}» no trae moneda')
        for nombre in ('cantidad', 'costo_unitario'):
            v = getattr(self, nombre)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise VadError(f'la partida «{self.descripcion}»: {nombre} tiene que ser un número no negativo, '
                               f'no {v!r}')

    @property
    def importe(self) -> float:
        return self.cantidad * self.costo_unitario


@dataclass(frozen=True)
class CostoReal:
    importe: float
    moneda: str
    fuente: str


@dataclass(frozen=True)
class RubroCosteado:
    rubro: Rubro
    #: Total estándar (solo partidas dimensionadas) o None si el rubro no está dimensionado o mezcla monedas.
    estandar: float | None
    moneda: str
    partidas: tuple[Partida, ...] = ()
    #: El costo real, solo como referencia rotulada.
    referencia_real: CostoReal | None = None
    rotulo_referencia: str = ROTULO_REAL
    motivo: str = ''


@dataclass(frozen=True)
class CostosExplotacion:
    rubros: tuple[RubroCosteado, ...]
    #: Moneda → total estándar de los rubros dimensionados en esa moneda.
    totales: Mapping[str, float] = field(default_factory=dict)

    @property
    def sin_dimensionar(self) -> list[str]:
        return [r.rubro.clave for r in self.rubros if r.estandar is None]


def rubros(registro: RegistroNormativo, fecha: str | None = None) -> list[Rubro]:
    try:
        valor = registro.regla('vad.explotacion.rubros', fecha).regla.valor
    except RegistroError as exc:
        raise VadError(f'el registro no trae los rubros de explotación (vad.explotacion.rubros): {exc}') from exc
    if not isinstance(valor, list) or not valor:
        raise VadError('vad.explotacion.rubros tiene que ser una lista no vacía')
    out = []
    for d in valor:
        if not isinstance(d, Mapping) or not all(isinstance(d.get(c), str) and d[c].strip()
                                                 for c in ('clave', 'nombre', 'numeral')):
            raise VadError(f'un rubro de explotación del registro no trae clave, nombre y numeral: {d!r}')
        out.append(Rubro(d['clave'], d['nombre'], d['numeral']))
    if len({r.clave for r in out}) != len(out):
        raise VadError('rubros de explotación repetidos en el registro')
    return out


def _real(dato: Any, rubro: str) -> CostoReal | None:
    if dato is None:
        return None
    if not isinstance(dato, CostoReal):
        raise VadError(f'el costo real del rubro {rubro} tiene que ser un CostoReal, no {type(dato).__name__}')
    if isinstance(dato.importe, bool) or not isinstance(dato.importe, (int, float)) \
            or not math.isfinite(dato.importe) or dato.importe < 0 or not dato.moneda.strip() or not dato.fuente.strip():
        raise VadError(f'el costo real del rubro {rubro} necesita importe no negativo, moneda y fuente')
    return dato


def costear(registro: RegistroNormativo, dimensionado: Mapping[str, Sequence[Partida]],
            reales: Mapping[str, CostoReal] | None = None, fecha: str | None = None) -> CostosExplotacion:
    """El costo estándar por rubro del registro, con el real solo como referencia rotulada (108:RF-19)."""
    lista = rubros(registro, fecha)
    claves = {r.clave for r in lista}
    reales = reales or {}
    extra = sorted((set(dimensionado) | set(reales)) - claves)
    if extra:
        raise VadError(f'rubros que el registro no tiene: {", ".join(extra)}')
    out: list[RubroCosteado] = []
    totales: dict[str, float] = {}
    for rubro in lista:
        partidas = tuple(dimensionado.get(rubro.clave) or ())
        if not all(isinstance(p, Partida) for p in partidas):
            raise VadError(f'las partidas del rubro {rubro.clave} tienen que ser Partida')
        real = _real(reales.get(rubro.clave), rubro.clave)
        if not partidas:
            motivo = (f'{rubro.nombre} ({rubro.numeral}): sin dimensionar'
                      + ('; el costo real no se toma como estándar' if real else ''))
            out.append(RubroCosteado(rubro, None, '', (), real, motivo=motivo))
            continue
        monedas = sorted({p.moneda for p in partidas})
        if len(monedas) != 1:
            out.append(RubroCosteado(rubro, None, '', partidas, real,
                                     motivo=f'{rubro.nombre}: partidas en varias monedas ({", ".join(monedas)}); '
                                            'no se suman'))
            continue
        total = math.fsum(p.importe for p in partidas)
        out.append(RubroCosteado(rubro, total, monedas[0], partidas, real))
        totales[monedas[0]] = totales.get(monedas[0], 0.0) + total
    return CostosExplotacion(tuple(out), totales)
