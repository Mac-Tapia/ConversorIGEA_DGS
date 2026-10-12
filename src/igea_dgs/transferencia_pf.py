"""Lo que la transferencia de carga de la spec 011 decide sin DIgSILENT.

El guion ``tools/transferencia_pf.py`` toma el camino entre dos alimentadores por su
punto de enlace (la troncal de ``ComBbone``), cierra el enlace y abre, uno tras otro desde
el enlace hacia la cabecera del que cede, cada punto del camino, con un flujo de carga en
cada paso (RF-109). Aquí está lo que no necesita PowerFactory, para probarlo con caminos
sorteados:

- los pasos del camino y la carga que transfiere cada uno (RF-110);
- si un paso es viable y, si no, qué lo limita (RF-111, RF-114);
- el máximo por seccionador y por nodo de un sentido (RF-112, RF-113, RF-115 a RF-117,
  RF-129);
- el fichero con una fila por caso, sentido, enlace y paso (RF-121).

Los límites son los de los estudios (``estudios_pf.Limites``, RF-35): la transferencia no
tiene otros.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .estudios_pf import Limites, escribir_csv, violaciones

#: Clases de punto del camino.
NODO, SECCIONADOR = 'nodo', 'seccionador'

COLUMNAS = (
    'caso', 'cede', 'recibe', 'enlace', 'paso', 'punto', 'tipo', 'carga_kw', 'carga_kva',
    'converge', 'viable', 'vm_min', 'vm_min_barra', 'cargabilidad_max', 'mas_cargado',
    'cabecera_recibe_kw', 'cabecera_recibe_kvar', 'motivo', 'elemento_limita')


@dataclass(frozen=True)
class Punto:
    """Un punto del camino, desde el enlace hacia la cabecera del que cede.

    Una barra lleva la carga que cuelga de ella, derivaciones incluidas: la que pasa al
    que recibe si queda del lado del enlace.
    """

    nombre: str
    tipo: str
    carga_kw: float = 0.0
    carga_kvar: float = 0.0


@dataclass(frozen=True)
class Paso:
    """Abrir el camino en un punto: lo que queda del lado del enlace pasa al que recibe."""

    indice: int
    punto: str
    tipo: str
    carga_kw: float
    carga_kvar: float

    @property
    def carga_kva(self) -> float:
        return math.hypot(self.carga_kw, self.carga_kvar)


def pasos_del_camino(puntos: Sequence[Punto]) -> list[Paso]:
    """Un paso por punto del camino, con la carga que transfiere (RF-110).

    Abrir un seccionador transfiere las barras anteriores a él; abrir en una barra (el
    resultado por nodos, RF-113) transfiere hasta ella incluida, como si allí hubiera un
    seccionador aguas arriba. Un seccionador sin ninguna barra antes no transfiere nada y
    no es un paso.
    """
    pasos, kw, kvar, hay_barra = [], 0.0, 0.0, False
    for p in puntos:
        if p.tipo == NODO:
            kw, kvar, hay_barra = kw + p.carga_kw, kvar + p.carga_kvar, True
        elif p.tipo != SECCIONADOR:
            raise ValueError(f'Punto de camino desconocido: {p.tipo!r} ({p.nombre}).')
        elif not hay_barra:
            continue
        pasos.append(Paso(len(pasos) + 1, p.nombre, p.tipo, kw, kvar))
    return pasos


def _gravedad(v: Mapping[str, Any]) -> float:
    """Cuánto se pasa de su límite, relativo: compara una sobrecarga con una tensión."""
    return abs(v['valor'] - v['limite']) / v['limite']


def juzgar(paso: Paso, medida: Mapping[str, Any], limites: Limites) -> tuple[bool, dict | None]:
    """``(viable, lo que limita)`` de un paso (RF-111, RF-114).

    ``medida`` es la del alimentador que recibe y la parte transferida tras el flujo del
    paso: ``converge``, ``barras`` ``[(nombre, u)]`` y ``elementos`` ``[(nombre, clase,
    cargabilidad)]``. Con varias violaciones limita la que más se pasa de su límite.
    """
    if not medida.get('converge'):
        return False, {'motivo': 'no converge', 'elemento': None, 'valor': None, 'limite': None}
    fuera = violaciones(medida, limites)
    if not fuera:
        return True, None
    peor = max(fuera, key=lambda v: (_gravedad(v), v['elemento']))
    motivo = 'sobrecarga' if peor['tipo'] == 'sobrecarga' else 'tension'
    return False, {'motivo': motivo, 'elemento': peor['elemento'], 'valor': peor['valor'],
                   'limite': peor['limite']}


def _extremos(medida: Mapping[str, Any]) -> dict[str, Any]:
    barras = [(n, u) for n, u in medida.get('barras') or () if u is not None]
    elementos = [(n, c) for n, _clase, c in medida.get('elementos') or () if c is not None]
    lo = min(barras, key=lambda b: (b[1], b[0])) if barras else (None, None)
    hi = max(elementos, key=lambda e: (e[1], e[0])) if elementos else (None, None)
    return {'vm_min': lo[1], 'vm_min_barra': lo[0], 'cargabilidad_max': hi[1], 'mas_cargado': hi[0]}


def _maximo(paso: Paso | None) -> dict[str, Any] | None:
    if paso is None:
        return None
    return {'punto': paso.punto, 'carga_kw': paso.carga_kw, 'carga_kva': paso.carga_kva}


def resumir_sentido(pasos: Sequence[Paso], medidas: Sequence[Mapping[str, Any]], limites: Limites,
                    *, seccionadores_reconocidos: bool = True) -> dict[str, Any]:
    """El resultado de un sentido y un enlace (RF-112 a RF-117, RF-129).

    El máximo por seccionador es el del seccionador viable más lejano del enlace; el
    máximo por nodo, el de la barra viable más lejana. Lo que limita es lo del primer
    paso no viable. Si después de un paso no viable hay otro que sí lo es, el resultado
    no crece con la carga como cabe esperar, y se avisa.
    """
    if len(pasos) != len(medidas):
        raise ValueError(f'{len(pasos)} pasos y {len(medidas)} medidas.')
    filas, avisos, limita = [], [], None
    ultimo = {NODO: None, SECCIONADOR: None}
    for paso, medida in zip(pasos, medidas):
        viable, motivo = juzgar(paso, medida, limites)
        filas.append({'paso': paso.indice, 'punto': paso.punto, 'tipo': paso.tipo,
                      'carga_kw': paso.carga_kw, 'carga_kva': paso.carga_kva,
                      'converge': bool(medida.get('converge')), 'viable': viable,
                      **_extremos(medida),
                      'cabecera_recibe_kw': medida.get('cabecera_kw'),
                      'cabecera_recibe_kvar': medida.get('cabecera_kvar'),
                      'motivo': (motivo or {}).get('motivo'),
                      'elemento_limita': (motivo or {}).get('elemento')})
        if viable:
            if limita is not None:
                avisos.append(f'El paso {paso.punto} es viable aunque {limita["punto"]}, antes, '
                              'no lo es: revise el camino o los límites.')
            ultimo[paso.tipo] = paso
        elif limita is None:
            limita = {'paso': paso.indice, 'punto': paso.punto, **motivo}

    por_seccionador = seccionadores_reconocidos and any(p.tipo == SECCIONADOR for p in pasos)
    if not seccionadores_reconocidos:
        avisos.append('El proyecto no distingue los seccionadores de los demás equipos de '
                      'maniobra: solo se da el resultado por nodos. Hay que volver a convertir '
                      'el alimentador o cargar su entrada.')
    elif not por_seccionador:
        avisos.append('El camino no tiene ningún seccionador: solo se da el resultado por nodos.')
    admite = any(f['viable'] for f in filas)
    if not admite and limita is not None:
        avisos.append(f'Este sentido no admite transferencia: ya en el primer paso limita '
                      f'{limita["elemento"] or "el flujo"} ({limita["motivo"]}).')
    return {'admite': admite,
            'maximo_seccionador': _maximo(ultimo[SECCIONADOR]) if por_seccionador else None,
            'maximo_nodo': _maximo(ultimo[NODO]),
            'limita': limita, 'pasos': filas, 'avisos': avisos}


def filas_fichero(resultados: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por caso, sentido, enlace y paso (RF-121), en un orden que no depende del
    de llegada."""
    filas = []
    for r in resultados:
        for paso in r.get('pasos') or ():
            filas.append({'caso': r['caso'], 'cede': r['cede'], 'recibe': r['recibe'],
                          'enlace': r['enlace'], **paso})
    return sorted(filas, key=lambda f: (f['caso'], f['cede'], f['recibe'], f['enlace'], f['paso']))


def escribir_fichero(resultados: Iterable[Mapping[str, Any]], destino: Path) -> Path:
    """El fichero descargable de las transferencias, como los de los estudios."""
    return escribir_csv(filas_fichero(resultados), COLUMNAS, destino)


# --------------------------------------------------------------------------- capacidad
#: Hasta cuántas veces la carga transferida se busca la capacidad del enlace por flujos
#: sucesivos (RF-125). Más allá, el límite no es del enlace sino de otra cosa: se dice.
TOPE_FACTOR = 1024.0
#: Precisión relativa de la bisección: 0,1 % del factor, muy por debajo de lo que
#: distingue un límite de otro en una red de distribución.
TOLERANCIA_FACTOR = 1e-3


def maximo_factor(es_viable, *, tope: float = TOPE_FACTOR,
                  tolerancia: float = TOLERANCIA_FACTOR) -> tuple[float, bool]:
    """El mayor factor de escala de la parte transferida que sigue siendo viable (RF-125).

    ``es_viable(k)`` ejecuta el flujo con la carga transferida multiplicada por ``k``. Se
    parte de 1, que es viable (es la configuración del seccionador viable más lejano), se
    dobla hasta el primero que no lo es y se biseca entre los dos. Devuelve el factor y si
    se llegó al tope sin encontrar límite.
    """
    bajo, alto = 1.0, 2.0
    while es_viable(alto):
        bajo = alto
        if alto >= tope:
            return bajo, True
        alto = min(alto * 2.0, tope)
    while alto - bajo > tolerancia * bajo:
        medio = (bajo + alto) / 2.0
        if es_viable(medio):
            bajo = medio
        else:
            alto = medio
    return bajo, False


def margen(capacidad_kw: float | None, transferida_kw: float) -> float | None:
    """Lo que el enlace puede llevar además de lo que ya transfiere (RF-123)."""
    return None if capacidad_kw is None else capacidad_kw - transferida_kw
