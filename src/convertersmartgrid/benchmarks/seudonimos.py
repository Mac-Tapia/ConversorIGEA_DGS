"""Seudónimos del benchmark: identificadores sin relación recuperable con los originales (112:RF-2).

Cada identificador original recibe, por tipo, un seudónimo ``B<tipo><n>``. El número sale de una permutación sorteada
con la semilla del benchmark, no del orden del original: con el orden alfabético, o con un hash, una lista de códigos
candidatos de la empresa bastaría para recuperarlo por diccionario (plan de la 112, decisión descartada). El mismo
original recibe el mismo seudónimo en la RED, la CARGA y el BD_Equipo, porque todos se registran en el mismo mapa
antes de escribir nada.

El mapa vive solo en memoria y no se puede serializar: si se escribiera junto al benchmark, el benchmark dejaría de
ser anónimo.
"""
from __future__ import annotations

import math
import random
from collections.abc import Hashable, Sequence

#: Letra de cada tipo de identificador. Un tipo nuevo se añade aquí, nunca se reutiliza una letra.
TIPOS: dict[str, str] = {
    'red': 'R', 'alimentador': 'A', 'set': 'S', 'sistema': 'Y', 'nodo': 'N', 'tramo': 'T',
    'equipo': 'E', 'tipo_equipo': 'Q', 'cliente': 'C', 'medidor': 'M',
    # 112 T3: el código de SED que el modelo saca del sufijo de un cliente o de un equipo (``extract_sed_code``). Va
    # aparte de «medidor» para que las SED de medición se sigan reconociendo con el perfil neutro.
    'sed': 'D',
}

#: Origen neutro de las coordenadas: el de los exports sintéticos de las pruebas (``ExportSpec``), que no es ninguna
#: zona real. El centroide de la red cae aquí.
ORIGEN_NEUTRO: tuple[float, float] = (500000.0, 8500000.0)
#: Orígenes neutros entre los que se elige el primero que queda a más de 100 km del recuadro del original (112 T7).
#: Ninguno es una zona concreta; elegir de una lista fija no revela dónde está el original (desplazarlo respecto a
#: su recuadro sí lo revelaría).
ORIGENES_NEUTROS: tuple[tuple[float, float], ...] = (ORIGEN_NEUTRO, (500000.0, 1500000.0), (500000.0, 5000000.0))
DISTANCIA_MINIMA_M = 100_000.0


def _vacio(valor: object) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


class Mapa:
    """Tabla de seudónimos de un benchmark: se registra todo, se congela y solo entonces se consulta."""

    def __init__(self, semilla: int):
        self._semilla = int(semilla)
        self._originales: dict[str, set[Hashable]] = {t: set() for t in TIPOS}
        self._tabla: dict[str, dict[Hashable, str]] | None = None

    def registrar(self, tipo: str, valor: Hashable) -> None:
        """Apunta un original de ``tipo``. Lo vacío no se seudonimiza; registrar dos veces es inocuo."""
        if tipo not in TIPOS:
            raise ValueError(f'tipo de identificador desconocido: {tipo!r}; válidos: {", ".join(TIPOS)}')
        if self._tabla is not None:
            raise RuntimeError('el mapa ya está congelado: registre todo antes de escribir el benchmark')
        if not _vacio(valor):
            self._originales[tipo].add(valor)

    def congelar(self) -> None:
        """Asigna los seudónimos. El resultado solo depende de la semilla y del conjunto de originales."""
        if self._tabla is not None:
            return
        tabla: dict[str, dict[Hashable, str]] = {}
        for tipo, letra in TIPOS.items():
            originales = sorted(self._originales[tipo], key=lambda v: (type(v).__name__, str(v)))
            numeros = list(range(1, len(originales) + 1))
            # Una permutación por tipo, con su propia semilla derivada: los tipos no se pisan entre sí.
            random.Random(f'{self._semilla}:{tipo}').shuffle(numeros)
            ancho = len(str(len(originales))) if originales else 1
            tabla[tipo] = {o: f'B{letra}{n:0{ancho}d}' for o, n in zip(originales, numeros)}
        self._tabla = tabla
        self._originales = {t: set() for t in TIPOS}

    def __call__(self, tipo: str, valor: Hashable) -> Hashable:
        """El seudónimo de un original registrado. Lo vacío vuelve tal cual; lo no registrado es un error."""
        if self._tabla is None:
            raise RuntimeError('congele el mapa antes de pedir seudónimos')
        if tipo not in TIPOS:
            raise ValueError(f'tipo de identificador desconocido: {tipo!r}')
        if _vacio(valor):
            return valor
        try:
            return self._tabla[tipo][valor]
        except KeyError:
            raise KeyError(f'un {tipo} sin registrar: registre todos los ficheros antes de congelar') from None

    def __repr__(self) -> str:
        # Ni un original en la representación: un registro o una traza no deben poder filtrarlo.
        n = sum(len(v) for v in (self._tabla or {}).values())
        return f'Mapa(congelado={self._tabla is not None}, seudonimos={n})'

    def __reduce__(self):
        raise TypeError('el mapa de seudónimos no se serializa: vive solo en memoria')


def transformar_coordenadas(puntos: Sequence[tuple[float, float]], *, semilla: int,
                            origen: tuple[float, float] = ORIGEN_NEUTRO) -> list[tuple[float, float]]:
    """Lleva la red a un origen neutro con un giro sorteado: se pierde dónde está, no su forma (112:RF-2, RF-3).

    Resta el centroide, gira un ángulo sacado de la semilla y suma ``origen``. Un giro y una traslación
    conservan todas las distancias, así que las longitudes y la geometría relativa siguen iguales.
    """
    if not puntos:
        return []
    cx = math.fsum(x for x, _ in puntos) / len(puntos)
    cy = math.fsum(y for _, y in puntos) / len(puntos)
    angulo = random.Random(f'{int(semilla)}:giro').uniform(0.0, 2.0 * math.pi)
    c, s = math.cos(angulo), math.sin(angulo)
    ox, oy = origen
    return [(ox + c * (x - cx) - s * (y - cy), oy + s * (x - cx) + c * (y - cy)) for x, y in puntos]


def origen_lejano(recuadro: tuple[float, float, float, float] | None,
                  extension: tuple[float, float, float, float]) -> tuple[float, float]:
    """El primer origen neutro con el que la red (``extension``, relativa a él) queda a más de
    :data:`DISTANCIA_MINIMA_M` del recuadro original (112:RF-2, RF-4)."""
    if recuadro is None:
        return ORIGENES_NEUTROS[0]
    x0, y0, x1, y1 = recuadro
    ex0, ey0, ex1, ey1 = extension
    m = DISTANCIA_MINIMA_M
    for ox, oy in ORIGENES_NEUTROS:
        if ox + ex0 > x1 + m or ox + ex1 < x0 - m or oy + ey0 > y1 + m or oy + ey1 < y0 - m:
            return ox, oy
    raise ValueError('ningún origen neutro queda lejos de la red original: no se puede situar sin delatarla')
