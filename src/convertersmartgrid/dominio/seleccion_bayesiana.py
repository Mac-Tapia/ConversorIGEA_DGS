"""Cuándo dejar de sortear una variante: la probabilidad bayesiana de que cumpla (spec 087, RF-7 a RF-9).

La escalera mide 200 sorteos por variante, y solo paraba si ya no podía llegar al cumplimiento pedido. Una variante sin ningún
fallo se sorteaba entera, a varios minutos cada una; y CHI201 (Pisco, 2026-11-03) salió con 94,5 % frente al 95 % pedido, una
diferencia que 200 sorteos no distinguen. Con una posterior Beta se para en cuanto la respuesta está clara y se dice la certeza.

Puro: no habla con DIgSILENT. La posterior es Beta(1 + cumplen, 1 + fallan), con la previa uniforme: sin datos no se supone nada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scipy.special import betainc

#: Certeza con la que se deja de sortear (087:RF-8): por encima de esto o por debajo de su complemento.
CERTEZA = 0.99
#: Con menos sorteos no se para a favor ni en contra: unos pocos instantes parecidos no dicen nada.
MINIMO_SORTEOS = 10


def probabilidad_de_alcanzar(cumplen: int, fallan: int, objetivo: float) -> float:
    """087:RF-7: la probabilidad posterior de que la fracción real de cumplimiento alcance ``objetivo``."""
    return float(1.0 - betainc(1 + int(cumplen), 1 + int(fallan), float(objetivo)))


@dataclass
class Seguimiento:
    """Los sorteos de una variante, uno a uno. Sin ``bayesiana``, la regla de antes (025:RF-72)."""

    total: int
    objetivo: float
    bayesiana: bool = False
    cumplen: int = 0
    fallan: int = 0
    parada: str = field(default='')

    def anota(self, bien: bool) -> bool:
        """Un sorteo más; devuelve si ya se puede dejar de sortear."""
        if bien:
            self.cumplen += 1
        else:
            self.fallan += 1
        if self.bayesiana:
            if self.medidos < MINIMO_SORTEOS:
                return False
            prob = probabilidad_de_alcanzar(self.cumplen, self.fallan, self.objetivo)
            self.parada = 'cumple' if prob > CERTEZA else 'no_cumple' if prob < 1 - CERTEZA else ''
            return bool(self.parada)
        return self.fallan > int((1 - self.objetivo) * self.total + 1e-9)

    @property
    def medidos(self) -> int:
        return self.cumplen + self.fallan

    def fraccion(self) -> float:
        """La fracción con que se juzga: de lo medido, o con la regla de antes sobre el total."""
        if self.bayesiana:
            return self.cumplen / self.medidos if self.medidos else 0.0
        return (self.total - self.fallan) / self.total if self.total else 0.0

    def resumen(self) -> dict[str, Any]:
        """087:RF-9: lo que se dice de la variante."""
        return {'sorteos_usados': self.medidos, 'sorteos_total': self.total, 'fraccion': round(self.fraccion(), 4),
                'probabilidad': round(probabilidad_de_alcanzar(self.cumplen, self.fallan, self.objetivo), 4),
                'objetivo': self.objetivo, 'parada': self.parada}
