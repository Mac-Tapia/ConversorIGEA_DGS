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
from dataclasses import dataclass, field, replace

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
    #: Los nombres de sus dos barras, para compararlas con las del DGS (098:RF-16); ``extremos`` son las claves.
    barras: tuple[str, str] | None = None

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
    # También lo que tiene SED propias del alimentador que no pasaron a otro: la segunda troncal de un medidor con dos
    # salidas queda fuera del ``ElmFeeder`` (CA101, 2026-10-15, 063:RF-39) y sigue siendo suya.
    for c in cargas:
        if c.etiqueta in barras_f and c.alimentador in (c.etiqueta, None) and c.terminal not in fuera:
            fuentes.setdefault(c.etiqueta, set()).add(comp.raiz(c.terminal))
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
        zona = Zona(desde=min(str(x) for x in desde), hacia=min(str(x) for x in hacia), cargas=lista,
                    terminales=barras_de[raiz])
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


# =========================================================================== la red de la fuente (098:RF-16 a RF-19)
#: Lo que une dos barras en el DGS y en DIgSILENT: tramos, acopladores, transformadores y equipos en serie.
CLASES_DE_RAMA = ('ElmLne', 'ElmCoup', 'ElmTr2', 'ElmZpu', 'ElmVoltreg', 'ElmSind')


@dataclass
class RedFuente:
    """Lo que dice el DGS aceptado: sus barras, cada rama con las dos barras que une, y lo que deja abierto."""

    barras: set[str] = field(default_factory=set)
    ramas: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    abiertos: dict[str, set[str]] = field(default_factory=dict)


def red_del_dgs(lineas: Iterable[str], fuente: RedFuente | None = None) -> RedFuente:
    """098:RF-16: la red del DGS aceptado, con las barras de cada rama por sus cubículos (``StaCubic``).

    Cada tabla se lee por su cabecera. El DGS del conversor no trae las maniobras abiertas (se quitan al convertir: 90
    en el de CA101 y CHN102), así que dos barras que el DGS no une no se unían en la fuente.
    """
    fuente = fuente or RedFuente()
    nombres: dict[str, tuple[str, str]] = {}
    cubiculos: list[tuple[str, int, str]] = []
    tabla, campos = None, []
    for linea in lineas:
        if linea.startswith('$$'):
            partes = linea.strip()[2:].split(';')
            tabla, campos = partes[0], [x.split('(')[0].replace(':MATRIX', '') for x in partes[1:]]
            continue
        if tabla is None or not linea.strip() or linea.startswith('*'):
            continue
        fila = dict(zip(campos, linea.strip().split(';')))
        fid = fila.get('FID') or fila.get('ID')
        if tabla == 'StaCubic':
            try:
                cubiculos.append((fila.get('fold_id', ''), int(fila.get('obj_bus') or 0), fila.get('obj_id', '')))
            except ValueError:
                continue
            continue
        nombre = fila.get('loc_name')
        if not fid or not nombre:
            continue
        nombres[fid] = (tabla, nombre)
        if tabla == 'ElmTerm':
            fuente.barras.add(nombre)
        if fila.get('on_off', '1').strip() == '0' or fila.get('outserv', '0').strip() == '1':
            fuente.abiertos.setdefault(tabla, set()).add(nombre)
    lados: dict[str, list[tuple[int, str]]] = {}
    for barra, lado, elemento in cubiculos:
        if barra in nombres and nombres[barra][0] == 'ElmTerm' and elemento in nombres:
            lados.setdefault(elemento, []).append((lado, nombres[barra][1]))
    for elemento, extremos in lados.items():
        clase, nombre = nombres[elemento]
        if clase in CLASES_DE_RAMA and len(extremos) == 2:
            a, b = (n for _l, n in sorted(extremos))
            fuente.ramas[(clase, nombre)] = (a, b)
    return fuente


def frente_a_la_fuente(ramas: Sequence[Rama], fuente: RedFuente) -> tuple[list[Rama], dict]:
    """098:RF-16 a RF-18: cada rama de ahora frente al DGS aceptado, con ``en_fuente`` y ``cerrada_en_fuente``.

    - La rama del DGS con las mismas barras es de la fuente; cerrada salvo que el DGS la deje abierta.
    - Una partición (``SplitLine`` o una barra insertada): la rama del DGS con otras barras y la cadena de ramas y barras
      nuevas que vuelve a unir sus barras originales equivalen a la rama de la fuente, cerrada. Si en la cadena hay algo
      abierto, es el punto que abrió el operador: SEC_1091_1082269 de CA101 (2026-11-07) quedó partida en dos con un
      acoplador nuevo abierto en medio.
    - Lo demás que no está en el DGS no es de la fuente: un acoplador nuevo cerrado entre dos barras del DGS que el DGS
      no une es un enlace del operador («Breaker/Switch(1)», por donde CHN102 alimentaba la zona).
    Devuelve las ramas reclasificadas y un resumen con las particiones y lo nuevo.
    """
    por_barra: dict[str, list[Rama]] = {}
    nuevas = [r for r in ramas if r.barras and (r.clase, r.nombre) not in fuente.ramas]
    for r in nuevas:
        for b in r.barras or ():
            por_barra.setdefault(b, []).append(r)
    de_particion: dict[str, str] = {}             # clave de la rama → nombre de la rama del DGS que reconstruye
    particiones = []
    for r in ramas:
        original = fuente.ramas.get((r.clase, r.nombre))
        if original is None or not r.barras or set(r.barras) == set(original):
            continue
        faltan = set(original) - set(r.barras)
        inicios = [b for b in r.barras if b not in original]
        cadena = _cadena(inicios, faltan, por_barra, fuente.barras)
        if cadena is not None:
            de_particion[r.clave] = r.nombre
            for x in cadena:
                de_particion[x.clave] = r.nombre
            particiones.append({'rama': r.nombre, 'clase': r.clase, 'cadena': [x.nombre for x in cadena],
                                'abierto': [x.nombre for x in [r, *cadena] if not x.cerrada]})
    out = []
    for r in ramas:
        if not r.barras:
            out.append(r)
            continue
        clave = (r.clase, r.nombre)
        if r.clave in de_particion:
            out.append(replace(r, en_fuente=True, cerrada_en_fuente=True))
        elif clave in fuente.ramas:
            abierta = r.nombre in fuente.abiertos.get(r.clase, set())
            out.append(replace(r, en_fuente=True, cerrada_en_fuente=not abierta))
        else:
            out.append(replace(r, en_fuente=False, cerrada_en_fuente=None))
    resumen = {'particiones': particiones,
               'nuevas': sorted(r.nombre for r in nuevas if r.clave not in de_particion)}
    return out, resumen


def _cadena(inicios: Sequence[str], faltan: set[str], por_barra: Mapping[str, list[Rama]],
            barras_dgs: set[str]) -> list[Rama] | None:
    """Las ramas nuevas que, por barras nuevas, van de cada barra nueva de la rama partida a una barra original suya."""
    if not inicios or not faltan:
        return None
    cadena: list[Rama] = []
    for inicio in inicios:
        previo: dict[str, tuple[str, Rama] | None] = {inicio: None}
        cola, fin = deque([inicio]), None
        while cola and fin is None:
            n = cola.popleft()
            for r in sorted(por_barra.get(n, []), key=lambda x: (x.nombre, x.clase)):
                otra = r.barras[1] if r.barras[0] == n else r.barras[0]
                if otra in previo:
                    continue
                if otra in faltan:
                    previo[otra], fin = (n, r), otra
                    break
                if otra not in barras_dgs:          # solo por barras nuevas: la cadena no se sale de la partición
                    previo[otra] = (n, r)
                    cola.append(otra)
        if fin is None:
            return None
        while previo[fin] is not None:
            fin, r = previo[fin]
            if r not in cadena:
                cadena.append(r)
    return cadena
