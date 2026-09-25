"""Tramos puente de CYMDIST: se funden en lugar de modelarse como líneas.

Qué son. En la base de CYMDIST cada seccionador, cada interruptor y cada carga cuelga
de un **tramo**: el dispositivo no puede existir sin una sección que lo sostenga. Para
eso la base crea tramos diminutos con tipo ``DEFAULT``. Medido en 260924.mdb sobre
CA101, PE104, NA203 y NA205:

* 1.221 aéreos ``DEFAULT``, mediana **2 m**, 2 km en total frente a 294 km de red real.
  1.188 llevan exactamente un seccionador o un interruptor; 33 no llevan nada.
* 570 subterráneos ``DEFAULT`` de **0,3 m**. Los 570 llevan exactamente una carga: son
  la bajada a cada SED.

Por qué no se modelan como líneas. ``DEFAULT`` es el conductor genérico de CYMDIST
(0,4 Ω/km): no es un conductor, es un marcador de posición. Modelarlo añade 1.791
líneas de impedancia inventada y 1.791 barras que no existen en campo, y el diagrama
se llena de trazos de 2 m sobre cada poste.

Qué se hace con cada uno, sin perder ningún elemento de la base:

* **Con seccionador o interruptor** → un :class:`~igea_dgs.model.Coupler` (``ElmCoup``)
  entre sus dos barras, con el estado normal de la base. La maniobra sigue ahí y se
  puede abrir en PowerFactory.
* **Sin dispositivo** (puente puro, o bajada a SED) → sus dos barras se funden en una.
  La carga y la SED que colgaban de él quedan en la barra resultante.

La barra que sobrevive es la de aguas arriba (``FromNode``), y nunca se funde la barra
de la fuente: la cabecera conserva su identidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .model import Coupler, FeederModel, Node

#: Códigos de tipo que marcan un tramo puente en CYMDIST.
CODIGOS_PUENTE = ('DEFAULT',)

#: Longitud máxima de un puente. En 260924.mdb los 1.791 puentes miden como mucho 5 m.
#: Un tramo ``DEFAULT`` más largo es una línea real cuyo conductor no se conoce: se
#: modela como línea (con el tipo DEFAULT del catálogo) y NO se funde, porque fundirlo
#: borraría su impedancia y su longitud. Mismo umbral que la carga a mitad de tramo
#: (model.LARGO_MAXIMO_CARGA_CENTRAL_M): por debajo de 10 m el error es despreciable.
LARGO_MAXIMO_PUENTE_M = 10.0


@dataclass
class InformePuentes:
    tramos: int = 0
    metros: float = 0.0
    fundidos: int = 0
    interruptores: int = 0
    cargas_reubicadas: int = 0
    seds_reubicadas: int = 0
    barras_eliminadas: int = 0
    avisos: list[str] = field(default_factory=list)

    def texto(self) -> str:
        return (
            f'Tramos puente ({"/".join(CODIGOS_PUENTE)}): {self.tramos} '
            f'({self.metros:,.1f} m). Convertidos en interruptor: {self.interruptores}. '
            f'Fundidos: {self.fundidos} ({self.barras_eliminadas} barras menos; '
            f'{self.cargas_reubicadas} cargas y {self.seds_reubicadas} SED en la barra '
            'resultante).'
        )


class _Uniones:
    """Unión de barras con una raíz preferida: la fuente nunca desaparece."""

    def __init__(self, fija: str) -> None:
        self.padre: dict[str, str] = {}
        self.fija = fija

    def raiz(self, n: str) -> str:
        camino = []
        while self.padre.get(n, n) != n:
            camino.append(n)
            n = self.padre[n]
        for c in camino:
            self.padre[c] = n
        return n

    def unir(self, sobrevive: str, desaparece: str) -> None:
        a, b = self.raiz(sobrevive), self.raiz(desaparece)
        if a == b:
            return
        if b == self.fija:
            a, b = b, a
        self.padre[b] = a


def es_puente(line, codigos=CODIGOS_PUENTE, *, largo_max_m: float = LARGO_MAXIMO_PUENTE_M) -> bool:
    if (line.source_type_code or '').strip().upper() not in {c.upper() for c in codigos}:
        return False
    largo = line.txt_length_m if line.txt_length_m is not None else line.length_m
    return largo <= largo_max_m


def fundir_puentes(model: FeederModel, *, codigos=CODIGOS_PUENTE) -> InformePuentes:
    """Funde los tramos puente del modelo, en el sitio. Devuelve lo que hizo."""
    informe = InformePuentes()
    puentes = [ln for ln in model.lines if es_puente(ln, codigos)]
    if not puentes:
        return informe
    ids_puente = {ln.section_id for ln in puentes}
    informe.tramos = len(puentes)
    informe.metros = sum(ln.length_m for ln in puentes)

    equipos_por_tramo: dict[str, list] = {}
    for dev in model.devices:
        if dev.section_id in ids_puente:
            equipos_por_tramo.setdefault(dev.section_id, []).append(dev)

    uniones = _Uniones(model.source_node)
    con_equipo = []
    for ln in sorted(puentes, key=lambda x: x.section_id):
        if equipos_por_tramo.get(ln.section_id):
            con_equipo.append(ln)
        else:
            uniones.unir(ln.from_node, ln.to_node)
            informe.fundidos += 1

    raiz = uniones.raiz
    nuevos_nodos: dict[str, Node] = {}
    for node_id, node in model.nodes.items():
        destino = raiz(node_id)
        if destino == node_id:
            nuevos_nodos[node_id] = node
    informe.barras_eliminadas = len(model.nodes) - len(nuevos_nodos)

    acopladores: list[Coupler] = []
    for ln in con_equipo:
        equipos = sorted(equipos_por_tramo[ln.section_id],
                         key=lambda d: (d.terminal_side, d.kind, d.eq_number))
        a, b = raiz(ln.from_node), raiz(ln.to_node)
        if a == b:
            # El puente con equipo quedó en paralelo con uno fundido: sus dos extremos
            # son ya la misma barra. No se inventa una barra para salvarlo; se avisa.
            informe.avisos.append(
                f'{ln.section_id}: el interruptor {equipos[0].eq_number} une una barra '
                'consigo misma tras fundir un puente en paralelo; queda sin modelar.')
            continue
        # Varios equipos en el mismo puente van en serie: barras intermedias en la
        # misma posición que el extremo de origen, una por equipo de más.
        extremos = [a]
        base = nuevos_nodos[a]
        for i in range(1, len(equipos)):
            nid = f'{ln.section_id}_P{i}'
            nuevos_nodos[nid] = replace(base, node_id=nid)
            extremos.append(nid)
        extremos.append(b)
        for i, dev in enumerate(equipos):
            acopladores.append(Coupler(
                name=dev.eq_number or dev.eq_id or ln.section_id,
                node_a=extremos[i], node_b=extremos[i + 1],
                on_off=dev.on_off, kind=dev.kind, eq_id=dev.eq_id,
                eq_number=dev.eq_number, section_id=ln.section_id, phase=ln.phase,
            ))
    informe.interruptores = len(acopladores)

    model.lines = [
        replace(ln, from_node=raiz(ln.from_node), to_node=raiz(ln.to_node))
        for ln in model.lines if ln.section_id not in ids_puente
    ]
    model.section_by_id = {ln.section_id: ln for ln in model.lines}
    model.devices = [
        replace(d, node_id=raiz(d.node_id)) if d.node_id else d
        for d in model.devices if d.section_id not in ids_puente
    ]
    nuevas_cargas = []
    for c in model.loads:
        if c.section_id in ids_puente:
            informe.cargas_reubicadas += 1
        nuevas_cargas.append(replace(c, node_id=raiz(c.node_id)))
    model.loads = nuevas_cargas
    nuevas_seds = []
    for s in model.seds:
        if s.section_id in ids_puente:
            informe.seds_reubicadas += 1
        nuevas_seds.append(replace(s, node_id=raiz(s.node_id)))
    model.seds = nuevas_seds
    model.couplers = list(model.couplers) + [
        replace(c, node_a=raiz(c.node_a) if c.node_a in model.nodes else c.node_a,
                node_b=raiz(c.node_b) if c.node_b in model.nodes else c.node_b)
        for c in acopladores
    ]
    model.nodes = nuevos_nodos
    model.source_node = raiz(model.source_node)

    # Tipos que ya no usa ninguna línea (el DEFAULT) no se escriben: un TypLne
    # huérfano en el DGS sugiere un conductor que no existe.
    usados = {ln.type_key for ln in model.lines}
    model.line_types = {k: t for k, t in model.line_types.items() if k in usados}
    model.warnings.append(informe.texto())
    model.warnings.extend(informe.avisos)
    return informe
