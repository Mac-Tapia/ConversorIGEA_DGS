"""¿Son dos entradas la misma foto de la red?

La distribuidora exporta la red cuando le piden, y entre dos exportaciones CYMDIST
**renumera nodos**. El TXT de referencia (03/08) y la base ``260924.mdb`` comparten el
99,4 % de los identificadores de tramo, pero solo el 55 % de esos tramos une los mismos
nodos: una parte de la red se renumeró entre medias. Compararlas tramo a tramo daba
10 fallos que parecían del lector Access y eran de la elección de ficheros.

Este módulo mide el parecido con lo que **no** depende del mapeo que se quiere
probar: los identificadores de la tabla NODE y de la tabla SECTION, cada uno por su
lado. Si el lector Access mezclara columnas de tramo, estos conjuntos seguirían siendo
los mismos y la comparación tramo a tramo lo seguiría detectando.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .dataset import CymdistDataset

#: Por debajo de esto no son la misma exportación. Una misma foto leída por las dos
#: vías da 1,0; entre las dos entregas de 2026 se midió 0,725 en nodos.
UMBRAL_MISMA_FOTO = 0.98


def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    union = a | b
    return len(a & b) / len(union) if union else 1.0


@dataclass(frozen=True)
class Comparacion:
    nodos: float
    tramos: float
    alimentadores: float
    alimentadores_comunes: int
    solo_en_a: int
    solo_en_b: int

    @property
    def misma_foto(self) -> bool:
        return min(self.nodos, self.tramos) >= UMBRAL_MISMA_FOTO

    def motivo(self) -> str:
        """Frase para el operador (y para el *skip* de una prueba)."""
        if self.misma_foto:
            return 'misma exportación'
        return (
            f'no son la misma exportación: comparten el {self.nodos:.1%} de los nodos y el '
            f'{self.tramos:.1%} de los tramos (hace falta {UMBRAL_MISMA_FOTO:.0%}). '
            'CYMDIST renumera nodos entre exportaciones; use un TXT y una base del mismo '
            'día (tools/emparejar_entradas.py las busca).'
        )

    def as_dict(self) -> dict:
        return {**asdict(self), 'misma_foto': self.misma_foto}


def comparar(a: CymdistDataset, b: CymdistDataset) -> Comparacion:
    fa, fb = set(a.feeders), set(b.feeders)
    return Comparacion(
        nodos=_jaccard(a.nodes, b.nodes),
        tramos=_jaccard(a.sections, b.sections),
        alimentadores=_jaccard(fa, fb),
        alimentadores_comunes=len(fa & fb),
        solo_en_a=len(fa - fb),
        solo_en_b=len(fb - fa),
    )
