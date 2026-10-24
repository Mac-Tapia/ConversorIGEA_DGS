"""Reguladores de tensión de catálogo para la escalera de obras (spec 025, RF-59, RF-60).

En DIgSILENT no había ningún ``TypVoltreg`` (sonda del 2026-10-24: ni en la biblioteca
global ni en los proyectos) y la obra «regulador» lo necesita. El usuario pidió buscar
fichas de fabricante y crearlos: Eaton Cooper Power VR-32, monofásico, ±10 % en 32 pasos
de 5/8 % (16 a cada lado de la toma central). Corrientes a ±10 % de la tabla de 50 Hz del
catálogo CA225001EN (agosto de 2025).

Cada unidad se conecta en estrella entre fase y neutro: para un sistema de ``kv`` de línea
se usa la tensión nominal de catálogo más baja que cubre ``kv``/√3 (10 kV → 6600 V; 22,9 kV
→ 15 000 V). ``Un`` del tipo es la de fase del sistema, que es la que ve cada unidad
(DIgSILENT: «Rated values for single-phase unit»). Puro: no lee DIgSILENT.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .naming import sufijo_tension

FABRICANTE = 'Eaton Cooper Power VR-32'
FUENTE = ('Eaton, «Single-phase step voltage regulators», catálogo CA225001EN, agosto de 2025, '
          'tabla de 50 Hz (corriente a ±10 %)')
RANGO_PCT = 10.0
PASOS = 16
FRECUENCIA_HZ = 50.0
#: «Type B» (devanado serie del lado de la fuente), el de los VR-32; en DIgSILENT, 1.
TIPO_B = 1
#: Banco de tres unidades en estrella; en DIgSILENT, 2 (sonda del 2026-10-24).
CONFIG_ESTRELLA = 2

#: Tensión nominal de la unidad (V) → corrientes nominales a ±10 % (A).
CORRIENTES_A = {
    6600: (50, 100, 150, 200, 300, 400, 500, 600, 668),
    11000: (50, 100, 150, 200, 300, 400, 500, 600),
    15000: (50, 100, 150, 200, 300, 400, 500),
    22000: (50, 100, 150, 200, 300, 400, 454),
    33000: (50, 100, 150, 200, 250),
    35000: (50, 100, 150, 200),
}


class CatalogoError(ValueError):
    """Ninguna unidad del catálogo sirve para la tensión pedida."""


@dataclass(frozen=True)
class UnidadRegulador:
    tension_unidad_v: int
    tension_sistema_kv: float
    corriente_a: float

    @property
    def nombre(self) -> str:
        """``VR32_22_9kV_200A``: DIgSILENT no acepta «.» en un nombre (``naming.sufijo_tension``)."""
        return f'VR32_{sufijo_tension(self.tension_sistema_kv)}_{self.corriente_a:g}A'

    @property
    def kva(self) -> float:
        """Potencia de regulación de la unidad, como la da el catálogo (V × A × 10 %)."""
        return self.tension_unidad_v * self.corriente_a * RANGO_PCT / 100 / 1000

    def datos_tipo(self) -> dict[str, Any]:
        """Los atributos del ``TypVoltreg`` (``In`` en amperios, ``Un`` en kV de fase)."""
        return {'type': TIPO_B, 'config': CONFIG_ESTRELLA, 'frnom': FRECUENCIA_HZ,
                'Un': self.tension_sistema_kv / math.sqrt(3), 'In': float(self.corriente_a),
                'pcReg': RANGO_PCT, 'ntapmax': PASOS, 'ntapmin': -PASOS, 'nntap0': 0}

    def descripcion(self) -> str:
        return (f'{FABRICANTE}, unidad de {self.tension_unidad_v} V, {self.corriente_a:g} A, '
                f'{self.kva:g} kVA, ±{RANGO_PCT:g} % en {2 * PASOS} pasos; banco en estrella para '
                f'{self.tension_sistema_kv:g} kV. Fuente: {FUENTE}.')


def tension_de_unidad_v(kv_sistema: float) -> int:
    """La tensión nominal de catálogo más baja que cubre la de fase del sistema."""
    fase_v = float(kv_sistema) * 1000 / math.sqrt(3)
    for v in sorted(CORRIENTES_A):
        if v >= fase_v:
            return v
    raise CatalogoError(f'ninguna unidad {FABRICANTE} cubre {kv_sistema:g} kV en estrella')


def unidades_para(kv_sistema: float) -> list[UnidadRegulador]:
    """Las unidades del catálogo para un sistema de ``kv_sistema`` de línea, de menor a mayor."""
    v = tension_de_unidad_v(kv_sistema)
    return [UnidadRegulador(v, float(kv_sistema), float(a)) for a in CORRIENTES_A[v]]


def unidad_para_corriente(kv_sistema: float, corriente_a: float) -> UnidadRegulador | None:
    """La unidad más chica que lleva ``corriente_a``; ``None`` si ninguna (RF-60)."""
    return next((u for u in unidades_para(kv_sistema) if u.corriente_a >= corriente_a), None)
