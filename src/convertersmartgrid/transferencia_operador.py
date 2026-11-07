"""Transferencias de carga que el operador hizo a mano en DIgSILENT (spec 098).

CA101 y CHN102 (2026-11-07, ``20261105-124711_CSG_TXT_CA101_CHN102``): el operador pasó parte de CA101 a CHN102 con dos
tramos nuevos y dejó abierto el punto que la unía a CA101; con ella pasaron tres bancos de 300 kvar. Las SED conservan su
``p:alimentador=CA101`` de la fuente, pero las alimenta CHN102. La recalibración de julio, con medidas de antes de la
transferencia, terminó con «pérdidas activas negativas en CA101 (-1 271,2 kW)»: contaba en CA101 unas cargas cuya
potencia entraba por la cabecera de CHN102.

La decisión del usuario (2026-11-07): para calibrar y recalibrar se desactiva la transferencia y se calibra con sus
alimentadores completos, como cuando se midió, y al terminar se deja exactamente como estaba. Aquí está la parte pura:
qué cargas están transferidas, qué zona forman, qué elementos que no son de la fuente la unen al alimentador que ahora
la alimenta y qué punto abierto la unía al suyo. No habla con DIgSILENT: la lectura y las escrituras, con su registro en
disco, son de ``tools/cargas_pf.py``. Vale para cualquier número de alimentadores, cadenas (X→Y y Y→Z) y transferencias
en los dos sentidos: todo sale de los datos, sin nombres de alimentador ni de empresa (constitución P13).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

#: Por qué una zona transferida no se puede devolver a su alimentador mientras se calibra (098:RF-8).
MOTIVO_MEZCLA = 'mezcla'
MOTIVO_SIN_UNION = 'sin_union'
MOTIVO_SIN_PUNTO = 'sin_punto'
MOTIVO_UNIDA_EN_LA_FUENTE = 'unida_en_la_fuente'


@dataclass(frozen=True)
class Rama:
    """Un elemento de dos extremos (tramo, acoplador, transformador...) con su estado de ahora y el de la fuente.

    ``en_fuente`` es ``False`` para un tramo que no venía en el DGS aceptado (028:RF-17) y ``None`` si no se sabe;
    ``cerrada_en_fuente`` dice si estaba cerrado en la fuente, o ``None`` si el plan no trae los estados del DGS.
    """

    clave: str
    clase: str
    nombre: str
    extremos: tuple[str, str]
    cerrada: bool
    en_fuente: bool | None = None
    cerrada_en_fuente: bool | None = None

    @property
    def fuera_de_la_fuente(self) -> bool:
        """Cerrada ahora y no en la fuente: un tramo nuevo, o un enlace que en la fuente estaba abierto."""
        return self.cerrada and (self.en_fuente is False or self.cerrada_en_fuente is False)


@dataclass(frozen=True)
class CargaRed:
    """Una carga con la etiqueta de su alimentador en la fuente (``p:alimentador``) y el que la alimenta ahora."""

    clave: str
    nombre: str
    terminal: str
    etiqueta: str | None
    alimentador: str | None
    p_kw: float = 0.0
    q_kvar: float = 0.0


@dataclass
class Zona:
    """Una parte de un alimentador ``desde`` que la red de ahora alimenta desde ``hacia``.

    ``abrir``: lo que no es de la fuente y la une a ``hacia``; ``cerrar``: el camino abierto que la unía a ``desde``.
    ``motivo`` no vacío: no se puede devolver mientras se calibra (098:RF-8) y se dice por qué.
    """

    desde: str
    hacia: str
    cargas: list[CargaRed]
    terminales: set[str] = field(default_factory=set)
    abrir: list[Rama] = field(default_factory=list)
    cerrar: list[Rama] = field(default_factory=list)
    supuesto: bool = False
    motivo: str = ''

    @property
    def kw(self) -> float:
        return sum(c.p_kw for c in self.cargas)

    @property
    def kvar(self) -> float:
        return sum(c.q_kvar for c in self.cargas)

    def resumen(self) -> dict:
        """Lo que va al informe de la calibración y del escaneo (098:RF-7, RF-9)."""
        return {'desde': self.desde, 'hacia': self.hacia, 'sed': sorted(c.nombre for c in self.cargas),
                'n_sed': len(self.cargas), 'kw': round(self.kw, 1), 'kvar': round(self.kvar, 1),
                'abrir': [{'clase': r.clase, 'nombre': r.nombre} for r in self.abrir],
                'cerrar': [{'clase': r.clase, 'nombre': r.nombre} for r in self.cerrar],
                'supuesto': self.supuesto, 'motivo': self.motivo or None}


def transferidas(cargas: Iterable[CargaRed], alimentadores: Iterable[str]) -> list[CargaRed]:
    """098:RF-1: las cargas con la etiqueta de un alimentador del proyecto que alimenta otro del mismo proyecto.

    Sin etiqueta, o alimentada por ninguno (aislada o fuera del ``ElmFeeder``, como la segunda troncal de CA101 el
    2026-10-15, 063:RF-39), no es una transferencia.
    """
    del_proyecto = set(alimentadores)
    return [c for c in cargas if c.etiqueta in del_proyecto and c.alimentador in del_proyecto
            and c.etiqueta != c.alimentador]


class _Componentes:
    """Unión de barras por las ramas dadas (union-find), sin recursión: 200 alimentadores son cientos de miles."""

    def __init__(self) -> None:
        self.padre: dict[str, str] = {}

    def raiz(self, x: str) -> str:
        self.padre.setdefault(x, x)
        r = x
        while self.padre[r] != r:
            r = self.padre[r]
        while self.padre[x] != r:
            self.padre[x], x = r, self.padre[x]
        return r

    def unir(self, a: str, b: str) -> None:
        ra, rb = self.raiz(a), self.raiz(b)
        if ra != rb:
            self.padre[max(ra, rb)] = min(ra, rb)


def zonas_transferidas(cargas: Sequence[CargaRed], ramas: Sequence[Rama], topologia: Mapping[str, Iterable[str]],
                       cabeceras: Iterable[str] = ()) -> list[Zona]:
    """098:RF-1, RF-2, RF-8: las zonas transferidas por el operador y cómo devolver cada una a su alimentador.

    ``topologia``: por alimentador del proyecto, las barras que alimenta ahora; ``cabeceras``: las barras de donde
    salen los alimentadores (la de la SET), que se apartan del grafo: varios alimentadores salen de la misma y, con
    ella, todo quedaría unido. La zona es lo que queda unido a las cargas transferidas por ramas que son de la fuente;
    se abre lo que no es de la fuente y la une a otro alimentador, y se cierra el camino más corto de elementos
    abiertos que la vuelve a unir con el suyo. Sin el estado de la fuente de esos elementos (``cerrada_en_fuente``
    nulo) se supone y la zona lo dice (``supuesto``).
    """
    alimentadores = set(topologia)
    pasadas = transferidas(cargas, alimentadores)
    if not pasadas:
        return []
    fuera = set(cabeceras)
    comp = _Componentes()
    for r in ramas:
        a, b = r.extremos
        if a in fuera or b in fuera:
            continue
        comp.raiz(a), comp.raiz(b)
        if r.cerrada and not r.fuera_de_la_fuente:
            comp.unir(a, b)
    # Por alimentador, lo que cuelga de su cabecera: la componente de la barra a la que llega el elemento que sale de
    # ella. Una barra que el alimentador alimenta solo a través de la zona (una SED nueva tras ella) no cuenta.
    barras_f = {f: set(b) for f, b in topologia.items()}
    fuentes: dict[str, set[str]] = {}
    for r in ramas:
        a, b = r.extremos
        if r.cerrada and (a in fuera) != (b in fuera):
            t = b if a in fuera else a
            for f, barras in barras_f.items():
                if t in barras:
                    fuentes.setdefault(f, set()).add(comp.raiz(t))
    for f, barras in barras_f.items():
        if f not in fuentes:                  # sin cabecera conocida: todo lo que alimenta
            fuentes[f] = {comp.raiz(t) for t in barras if t not in fuera}
    # Grafos entre componentes: por lo que no es de la fuente (lo que une la zona a quien la alimenta) y por lo
    # abierto que en la fuente estaba cerrado, o no se sabe (lo que la unía al suyo).
    union: dict[str, list[tuple[str, Rama]]] = {}
    abiertos: dict[str, list[tuple[str, Rama]]] = {}
    for r in sorted(ramas, key=lambda x: (x.nombre, x.clase, x.clave)):
        a, b = r.extremos
        if a in fuera or b in fuera:
            continue
        ca, cb = comp.raiz(a), comp.raiz(b)
        if ca == cb:
            continue
        if r.fuera_de_la_fuente:
            union.setdefault(ca, []).append((cb, r))
            union.setdefault(cb, []).append((ca, r))
        elif not r.cerrada and r.en_fuente is not False and r.cerrada_en_fuente is not False:
            abiertos.setdefault(ca, []).append((cb, r))
            abiertos.setdefault(cb, []).append((ca, r))
    por_comp: dict[str, list[CargaRed]] = {}
    for c in pasadas:
        por_comp.setdefault(comp.raiz(c.terminal), []).append(c)
    propias = {comp.raiz(c.terminal) for c in cargas
               if c.etiqueta and c.etiqueta == c.alimentador and c.alimentador in alimentadores}
    barras_de: dict[str, set[str]] = {r: set() for r in por_comp}
    for t in comp.padre:                                   # una pasada, no una por zona
        r = comp.raiz(t)
        if r in barras_de:
            barras_de[r].add(t)
    zonas = []
    for raiz, lista in sorted(por_comp.items(), key=lambda kv: min(c.nombre for c in kv[1])):
        lista = sorted(lista, key=lambda c: c.nombre)
        desde = {c.etiqueta for c in lista}
        hacia = {c.alimentador for c in lista}
        zona = Zona(desde=min(desde), hacia=min(hacia), cargas=lista, terminales=barras_de[raiz])
        if len(desde) > 1 or len(hacia) > 1:
            zona.motivo = MOTIVO_MEZCLA
        elif raiz in propias:
            # Unida por elementos de la fuente a cargas propias de quien la alimenta: no hay tramo nuevo que abrir.
            zona.motivo = MOTIVO_UNIDA_EN_LA_FUENTE
        else:
            zona.abrir = _uniones(raiz, union, fuentes.get(zona.hacia, set()))
            zona.cerrar, zona.supuesto = _camino(raiz, abiertos, fuentes.get(zona.desde, set()))
            if not zona.abrir:
                zona.motivo = MOTIVO_SIN_UNION
            elif not zona.cerrar:
                zona.motivo = MOTIVO_SIN_PUNTO
        zonas.append(zona)
    return zonas


def _uniones(zona: str, union: Mapping[str, list[tuple[str, Rama]]], destino: set[str]) -> list[Rama]:
    """Lo que no es de la fuente y une la zona con el alimentador que la alimenta, sin volver a pasar por ella.

    Un tramo nuevo que lleva a SED nuevas sin etiqueta (sin llegar a ``destino``) no es de la transferencia y no se
    abre: dejaría sin tensión una carga que nada tiene que ver.
    """
    out = []
    for otra, r in union.get(zona, []):
        vistos, cola = {zona, otra}, deque([otra])
        llega = otra in destino
        while cola and not llega:
            n = cola.popleft()
            for m, _r in union.get(n, []):
                if m not in vistos:
                    vistos.add(m)
                    llega = llega or m in destino
                    cola.append(m)
        if llega and r not in out:
            out.append(r)
    return out


def _camino(zona: str, abiertos: Mapping[str, list[tuple[str, Rama]]], destino: set[str]) -> tuple[list[Rama], bool]:
    """El camino más corto de elementos abiertos de la zona a su alimentador: el punto que abrió el operador."""
    if not destino:
        return [], False
    previo: dict[str, tuple[str, Rama] | None] = {zona: None}
    cola = deque([zona])
    fin = None
    while cola:
        n = cola.popleft()
        if n in destino and n != zona:
            fin = n
            break
        for m, r in abiertos.get(n, []):
            if m not in previo:
                previo[m] = (n, r)
                cola.append(m)
    if fin is None:
        return [], False
    out = []
    while previo[fin] is not None:
        fin, r = previo[fin]
        out.append(r)
    out.reverse()
    return out, any(r.cerrada_en_fuente is None for r in out)


def texto_de_zona(zona: Zona) -> str:
    """El aviso de una zona, con sus SED y lo que se tocó o por qué no (098:RF-7)."""
    sed = ', '.join(c.nombre for c in zona.cargas)
    base = (f'Transferencia del operador de {zona.desde} a {zona.hacia}: {len(zona.cargas)} SED ({sed}), '
            f'{zona.kw:,.1f} kW y {zona.kvar:,.1f} kvar')
    if zona.motivo:
        return base + ': ' + MOTIVOS[zona.motivo] + ' (098:RF-8).'
    abre = ', '.join(r.nombre for r in zona.abrir)
    cierra = ', '.join(r.nombre for r in zona.cerrar)
    return (base + f'. Mientras se calibra se abre {abre} y se cierra {cierra}, para medir cada alimentador completo, '
            'como cuando se tomó la medida; al terminar se deja como estaba (098:RF-3, RF-5)'
            + ('. El estado de la fuente de lo que se cierra no venía en el plan: se supone cerrado' if zona.supuesto else '')
            + '.')


MOTIVOS = {
    MOTIVO_MEZCLA: 'la zona lleva SED de varios alimentadores de origen o de destino; no se toca',
    MOTIVO_SIN_UNION: 'no hay tramo nuevo ni enlace de la fuente que la una a su alimentador de ahora; no se toca',
    MOTIVO_SIN_PUNTO: 'no se encontró el punto abierto que la unía a su alimentador; no se toca',
    MOTIVO_UNIDA_EN_LA_FUENTE: 'sigue unida por la red de la fuente a SED del alimentador que la alimenta; no se toca',
}


def maniobras_abiertas_del_dgs(lineas: Iterable[str]) -> dict[str, list[str]]:
    """098:RF-2: por clase, los elementos abiertos o fuera de servicio en el DGS aceptado (``on_off=0``, ``outserv=1``).

    Así se distingue el punto que abrió el operador de un enlace que ya venía abierto en la fuente. Lee la cabecera de
    cada tabla para saber en qué columna está cada atributo: el DGS no fija el orden.
    """
    clases = ('ElmCoup', 'ElmLne', 'StaSwitch')
    out: dict[str, set[str]] = {}
    tabla, campos = None, []
    for linea in lineas:
        if linea.startswith('$$'):
            partes = linea.strip()[2:].split(';')
            tabla = partes[0] if partes[0] in clases else None
            campos = [p.split('(')[0] for p in partes[1:]]
            continue
        if tabla is None or not linea.strip() or linea.startswith('*'):
            continue
        valores = linea.strip().split(';')
        fila = dict(zip(campos, valores))
        nombre = fila.get('loc_name')
        if not nombre:
            continue
        if fila.get('on_off', '1').strip() == '0' or fila.get('outserv', '0').strip() == '1':
            out.setdefault(tabla, set()).add(nombre)
    return {k: sorted(v) for k, v in sorted(out.items())}
