"""Une todos los alimentadores en una sola red, para poder estudiar el sistema.

Por qué hace falta. Hasta ahora cada alimentador salía a su propio DGS y a su propio
proyecto de PowerFactory: 96 redes que no se ven entre sí. Con esa forma de trabajar hay
preguntas que no se pueden ni formular —¿qué pasa si abro este enlace?, ¿puede este
alimentador respaldar a aquel ante una falla?, ¿dónde conviene el punto de apertura?—
porque el respaldo y la reconfiguración ocurren **entre** alimentadores, y cada modelo
solo conoce el suyo.

Medido sobre el export real: los 96 alimentadores comparten **42 nodos**. Esos 42 son
los puntos de enlace de la red de media tensión, y hoy no existen en ningún modelo. La
unión no es una comodidad de empaquetado; es lo que hace posible el análisis de sistema
del que dependen la reconfiguración, el criterio N-1 y buena parte del PIDE.

Las dos reglas que gobiernan la unión
-------------------------------------

**Un nodo es el mismo nodo si coinciden su identificador y su tensión.** Solo el
identificador no basta. En el export real hay dos nodos —``5605`` y
``NODE_1080_907891_907891_1``— que aparecen en SL201 a 22,9 kV y en SL143 a 10 kV.
Fusionarlos uniría dos niveles de tensión con un cortocircuito franco y el flujo de
potencia daría cualquier cosa. Cuando el identificador choca con tensiones distintas se
mantienen separados, cada uno con su sufijo de tensión, y se avisa: o es un error del
export, o hay ahí una transformación MT/MT que el export no modela. Ninguna de las dos
la puede decidir esta función.

**Un tipo de línea es el mismo tipo si coinciden su código y su tensión.** ``TypLne``
lleva la tensión nominal en ``uline``, así que un AA12003D a 10 kV y otro a 22,9 kV son
dos tipos distintos en PowerFactory aunque sean el mismo conductor. En el export real 31
de los 40 tipos se usan a las dos tensiones.

Lo que esta función NO hace
---------------------------

No decide nada de ingeniería. No cierra enlaces, no abre nada, no arregla los conflictos
de tensión ni inventa transformadores. Une lo que el export dice que está unido y deja
constancia de lo que no encaja.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

from .model import FeederModel, Line, LineType, Load, Node, Sed


@dataclass(frozen=True)
class FeederRef:
    """Un alimentador dentro de la red unida: de dónde se alimenta y a qué tensión."""

    name: str
    network_id: str
    source_node: str
    nominal_kv: float


@dataclass(frozen=True)
class TiePoint:
    """Un enlace entre dos alimentadores, modelado como interruptor normalmente abierto.

    Es como opera de verdad una red de distribución: los alimentadores son radiales y
    se enlazan entre sí con interruptores **normalmente abiertos**, que solo se cierran
    para transferir carga o para reponer servicio. Fusionar los dos nodos en uno, que
    era el primer planteamiento, equivale a dejar todos esos enlaces cerrados: convierte
    la red en mallada, rompe la radialidad y hace que cada alimentador deje de poder
    estudiarse por separado.

    Modelado así, cada alimentador sigue siendo su propia área radial —converge igual
    que su DGS individual— y el enlace queda explícito y cerrable. Es además lo que
    necesita ``ComTieopt`` (Tie Open Point Optimisation, manual §41.6): sin puntos de
    apertura declarados no hay nada que optimizar.
    """

    original_node: str
    """Identificador que los dos alimentadores compartían en el export."""
    node_a: str
    node_b: str
    feeder_a: str
    feeder_b: str
    nominal_kv: float

    @property
    def name(self) -> str:
        return f'TIE_{self.feeder_a}_{self.feeder_b}_{self.original_node}'[:40]


@dataclass
class CombinedInfo:
    """Lo que solo tiene sentido cuando el modelo es la unión de varios alimentadores.

    Va en un único campo opcional de :class:`~igea_dgs.model.FeederModel` en lugar de
    repartido en varios, para que un modelo de un solo alimentador siga siendo
    exactamente lo que era y el escritor DGS pueda preguntar una sola vez si está ante
    una red unida.
    """

    feeders: list[FeederRef] = field(default_factory=list)
    """Cada alimentador con su fuente. Habrá un ``ElmXnet`` y un ``ElmFeeder`` por cada uno."""

    node_kv: dict[str, float] = field(default_factory=dict)
    """Tensión nominal de cada nodo. En una red unida ya no es única."""

    type_kv: dict[str, float] = field(default_factory=dict)
    """Tensión de cada clave de tipo de línea, para ``TypLne.uline``."""

    tie_nodes: dict[str, list[str]] = field(default_factory=dict)
    """Nodo compartido → alimentadores que lo comparten. Los puntos de enlace."""

    ties: list[TiePoint] = field(default_factory=list)
    """Enlaces entre alimentadores, cada uno con su interruptor normalmente abierto."""

    voltage_conflicts: list[str] = field(default_factory=list)
    """Identificadores que aparecían a más de una tensión y hubo que separar."""

    feeder_of_node: dict[str, list[str]] = field(default_factory=dict)
    """Nodo → alimentadores en los que aparece. Para diagnóstico y para el diagrama."""

    de_energised: set[str] = field(default_factory=set)
    """Nodos sin camino a ninguna fuente, que se escriben fuera de servicio.

    PowerFactory resuelve **todas las áreas aisladas en un mismo sistema de Newton**.
    Un área sin fuente no tiene referencia de tensión, así que sus ecuaciones son
    singulares y el algoritmo se estanca arrastrando al resto: con un alimentador la
    red aún converge, con trece ya no. Medido: «Grid split into 22 isolated areas» →
    «Newton algorithm stagnated» → «No convergence in load flow».

    El manual lo dice en §24.6.3: un área no alimentada necesita una fuente o hay que
    sacarla de servicio. Se saca de servicio, **no se borra**: el elemento sigue en el
    modelo y se sigue dibujando, que es lo que se pidió, pero deja de participar en el
    cálculo. Y queda anotado para que alguien decida si esa isla es un error del GIS o
    una red que de verdad está sin alimentar.
    """


@dataclass
class CombineReport:
    """Qué se unió y qué no encajó, con las cuentas hechas."""

    feeders: int = 0
    nodes_in: int = 0
    nodes_out: int = 0
    lines: int = 0
    loads: int = 0
    seds: int = 0
    line_types_in: int = 0
    line_types_out: int = 0
    tie_nodes: int = 0
    tie_switches: int = 0
    voltage_conflicts: int = 0
    voltages: dict[float, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    de_energised_nodes: int = 0
    de_energised_lines: int = 0
    de_energised_loads: int = 0
    de_energised_kw: float = 0.0
    de_energised_by_feeder: dict[str, int] = field(default_factory=dict)

    @property
    def merged_nodes(self) -> int:
        """Cuántos nodos dejaron de estar duplicados al unir.

        Con los enlaces abiertos no se fusiona ninguno a propósito, así que esto vale
        cero: cada alimentador conserva su nodo y entre ellos va el interruptor.
        """
        return self.nodes_in - self.nodes_out

    def text(self) -> str:
        tensiones = ', '.join(f'{kv:g} kV ({n})' for kv, n in sorted(self.voltages.items()))
        lineas = [
            f'Alimentadores unidos : {self.feeders}  [{tensiones}]',
            f'Nodos                : {self.nodes_in:,} por separado → {self.nodes_out:,} en la red '
            + (f'({self.merged_nodes:,} fusionados)' if self.merged_nodes
               else '(sin fusionar: los enlaces van con interruptor)'),
            f'Puntos de enlace     : {self.tie_nodes}  →  {self.tie_switches} interruptor(es) '
            f'NORMALMENTE ABIERTO(S) entre alimentadores',
            f'Tramos               : {self.lines:,}',
            f'Cargas               : {self.loads:,}',
            f'SED                  : {self.seds:,}',
            f'Tipos de línea       : {self.line_types_in} → {self.line_types_out} '
            f'(una variante por tensión, porque TypLne lleva uline)',
        ]
        if self.voltage_conflicts:
            lineas.append(
                f'Conflictos de tensión: {self.voltage_conflicts}  ← NO se fusionaron'
            )
        if self.de_energised_nodes:
            lineas.append(
                f'Fuera de servicio    : {self.de_energised_nodes} nodos, '
                f'{self.de_energised_lines} tramos y {self.de_energised_loads} cargas '
                f'({self.de_energised_kw:,.1f} kW) sin camino a ninguna fuente'
            )
        if self.skipped:
            lineas.append(f'Alimentadores omitidos: {len(self.skipped)}')
        return '\n'.join(lineas)


def _kv_suffix(kv: float) -> str:
    return f'{kv:g}kV'.replace('.', '_')


def type_key_for(key: str, kv: float) -> str:
    """Clave de tipo con la tensión incorporada.

    Se mantiene el prefijo original (``LINE:`` / ``CABLE:``) porque el escritor lo usa
    para distinguir aéreo de subterráneo en ``cohl_``.
    """
    return f'{key}@{_kv_suffix(kv)}'


def unsupplied_nodes(model: FeederModel, sources: Iterable[str]) -> set[str]:
    """Nodos sin camino eléctrico a ninguna de las fuentes dadas.

    Es la versión multifuente de :func:`~igea_dgs.model.find_topology_islands`, que
    parte de un único ``source_node`` y por tanto no sirve para una red unida: con 96
    fuentes, buscar desde una sola declararía aislados a los otros 95 alimentadores.
    """
    adyacencia: dict[str, list[str]] = defaultdict(list)
    for line in model.lines:
        adyacencia[line.from_node].append(line.to_node)
        adyacencia[line.to_node].append(line.from_node)

    alcanzables = {s for s in sources if s in model.nodes}
    pila = list(alcanzables)
    while pila:
        nodo = pila.pop()
        for vecino in adyacencia.get(nodo, ()):
            if vecino not in alcanzables:
                alcanzables.add(vecino)
                pila.append(vecino)
    return set(model.nodes) - alcanzables


def combine_models(
    models: Iterable[FeederModel], *, name: str = 'SISTEMA',
    de_energise_islands: bool = True, tie_mode: str = 'open',
) -> tuple[FeederModel, CombineReport]:
    """Une los modelos en uno solo. Devuelve el modelo unido y el informe.

    El modelo resultante es un :class:`FeederModel` corriente con ``combined`` relleno,
    así que lo escribe el mismo ``write_dgs`` de siempre. No hay una segunda ruta de
    conversión que pueda desviarse de la primera.
    """
    modelos = list(models)
    informe = CombineReport(feeders=len(modelos))
    if not modelos:
        raise ValueError('No hay ningún alimentador que unir.')

    # --- Paso 1: qué tensiones reclama cada identificador de nodo -------------
    kv_por_id: dict[str, set[float]] = defaultdict(set)
    for m in modelos:
        kv = round(float(m.nominal_kv), 6)
        informe.voltages[kv] = informe.voltages.get(kv, 0) + 1
        for node_id in m.nodes:
            kv_por_id[node_id].add(kv)

    conflictivos = {n for n, kvs in kv_por_id.items() if len(kvs) > 1}
    informe.voltage_conflicts = len(conflictivos)
    for node_id in sorted(conflictivos):
        kvs = ', '.join(f'{k:g} kV' for k in sorted(kv_por_id[node_id]))
        informe.warnings.append(
            f'El nodo «{node_id}» aparece a {kvs}. No se fusiona: unir dos niveles de '
            f'tensión sería un cortocircuito franco. Se separa uno por tensión. '
            f'Revise si es un error del export o una transformación MT/MT no modelada.'
        )

    # Nodos que más de un alimentador declara. Con `tie_mode='open'` cada alimentador
    # conserva el suyo y entre ellos va un interruptor abierto; fusionarlos dejaría
    # todos los enlaces cerrados y la red dejaría de ser radial.
    alimentadores_por_nodo: dict[str, list[str]] = defaultdict(list)
    for m in modelos:
        for node_id in m.nodes:
            alimentadores_por_nodo[node_id].append(m.name)
    enlazados = (
        {n for n, fs in alimentadores_por_nodo.items() if len(set(fs)) > 1}
        if tie_mode == 'open' else set()
    )

    def resolver(node_id: str, kv: float, feeder: str = '') -> str:
        """Identificador del nodo en la red unida."""
        if node_id in conflictivos:
            return f'{node_id}__{_kv_suffix(kv)}'
        if node_id in enlazados and feeder:
            return f'{node_id}@{feeder}'
        return node_id

    # --- Paso 2: nodos, tipos y elementos -------------------------------------
    nodes: dict[str, Node] = {}
    node_kv: dict[str, float] = {}
    feeder_of_node: dict[str, list[str]] = defaultdict(list)
    line_types: dict[str, LineType] = {}
    type_kv: dict[str, float] = {}
    lines: list[Line] = []
    loads: list[Load] = []
    devices: list = []
    seds: list[Sed] = []
    feeders: list[FeederRef] = []
    codigos_tipo: set[str] = set()

    for m in modelos:
        kv = round(float(m.nominal_kv), 6)
        informe.nodes_in += len(m.nodes)

        for node_id, node in m.nodes.items():
            clave = resolver(node_id, kv, m.name)
            feeder_of_node[clave].append(m.name)
            previo = nodes.get(clave)
            if previo is None:
                nodes[clave] = replace(node, node_id=clave)
                node_kv[clave] = kv
            elif previo.x is None and node.x is not None:
                # Un mismo nodo puede venir sin coordenadas en un alimentador y con
                # ellas en otro: se queda la versión que sí las trae.
                nodes[clave] = replace(node, node_id=clave)

        for clave_tipo, tipo in m.line_types.items():
            codigos_tipo.add(tipo.code)
            nueva = type_key_for(clave_tipo, kv)
            if nueva not in line_types:
                line_types[nueva] = replace(tipo, key=nueva)
                type_kv[nueva] = kv

        for line in m.lines:
            lines.append(replace(
                line,
                from_node=resolver(line.from_node, kv, m.name),
                to_node=resolver(line.to_node, kv, m.name),
                type_key=type_key_for(line.type_key, kv),
            ))

        for load in m.loads:
            loads.append(replace(load, node_id=resolver(load.node_id, kv, m.name)))

        for sed in m.seds:
            seds.append(replace(sed, node_id=resolver(sed.node_id, kv, m.name)))

        for dev in m.devices:
            campos = {}
            for atributo in ('from_node', 'to_node', 'node_id'):
                valor = getattr(dev, atributo, None)
                if isinstance(valor, str) and valor:
                    campos[atributo] = resolver(valor, kv, m.name)
            devices.append(replace(dev, **campos) if campos else dev)

        feeders.append(FeederRef(
            name=m.name, network_id=m.network_id,
            source_node=resolver(m.source_node, kv, m.name), nominal_kv=kv,
        ))
        informe.warnings.extend(f'{m.name}: {w}' for w in m.warnings)

    # Un interruptor NORMALMENTE ABIERTO por cada par de alimentadores que comparten
    # nodo. Con tres o más se encadenan (n-1 interruptores), que es lo que mantiene la
    # radialidad: cerrar uno solo basta para transferir carga entre dos.
    ties: list[TiePoint] = []
    # Los nodos con conflicto de tensión quedan FUERA: un interruptor entre una barra
    # de 10 kV y otra de 22,9 kV no es un enlace, es una conexión que nadie debe poder
    # cerrar. Se quedan separados y sin nada que los una, como ya se avisó.
    for original in sorted(enlazados - conflictivos):
        presentes = sorted({
            (f, resolver(original, round(float(m.nominal_kv), 6), f))
            for m in modelos for f in [m.name] if original in m.nodes
        })
        for (fa, na), (fb, nb) in zip(presentes, presentes[1:]):
            if na in nodes and nb in nodes:
                ties.append(TiePoint(
                    original_node=original, node_a=na, node_b=nb,
                    feeder_a=fa, feeder_b=fb, nominal_kv=node_kv.get(na, 0.0),
                ))

    # Los puntos de enlace se cuentan sobre el identificador ORIGINAL del export: con
    # `tie_mode='open'` los nodos ya llevan el sufijo del alimentador, así que buscarlos
    # entre los nombres resueltos no encontraría ninguno.
    tie_nodes = {
        n: sorted(set(fs)) for n, fs in alimentadores_por_nodo.items() if len(set(fs)) > 1
    }

    informe.nodes_out = len(nodes)
    informe.lines = len(lines)
    informe.loads = len(loads)
    informe.seds = len(seds)
    informe.line_types_in = len(codigos_tipo)
    informe.line_types_out = len(line_types)
    informe.tie_nodes = len(tie_nodes)
    informe.tie_switches = len(ties)

    # La tensión del modelo unido es la que más alimentadores usan. Solo actúa como
    # respaldo: cada nodo y cada tipo llevan la suya en CombinedInfo.
    kv_dominante = max(informe.voltages.items(), key=lambda kv_n: kv_n[1])[0]
    principal = next(m for m in modelos if round(float(m.nominal_kv), 6) == kv_dominante)

    # Áreas sin fuente: se sacan de servicio, no se borran. Sin esto PowerFactory no
    # converge en cuanto hay unos pocos alimentadores (ver CombinedInfo.de_energised).
    sin_alimentar: set[str] = set()
    if de_energise_islands:
        provisional = FeederModel(
            name=name, network_id=name, nominal_kv=1.0, source_node='',
            nodes=nodes, lines=lines, loads=loads, devices=devices,
            line_types=line_types, seds=seds,
        )
        sin_alimentar = unsupplied_nodes(provisional, (f.source_node for f in feeders))
        if sin_alimentar:
            tramos = [l for l in lines
                      if l.from_node in sin_alimentar or l.to_node in sin_alimentar]
            cargas = [c for c in loads if c.node_id in sin_alimentar]
            informe.de_energised_nodes = len(sin_alimentar)
            informe.de_energised_lines = len(tramos)
            informe.de_energised_loads = len(cargas)
            informe.de_energised_kw = sum(c.p_mw for c in cargas) * 1000.0
            por_alimentador: dict[str, int] = {}
            for c in cargas:
                for a in feeder_of_node.get(c.node_id, ()):
                    por_alimentador[a] = por_alimentador.get(a, 0) + 1
            informe.de_energised_by_feeder = por_alimentador
            informe.warnings.append(
                f'{len(sin_alimentar)} nodo(s), {len(tramos)} tramo(s) y '
                f'{len(cargas)} carga(s) ({informe.de_energised_kw:,.1f} kW) no tienen '
                f'camino a ninguna fuente. Se escriben FUERA DE SERVICIO para que el '
                f'flujo converja —un área sin referencia de tensión estanca el Newton '
                f'de toda la red (manual §24.6.3)—, pero siguen en el modelo y se '
                f'siguen dibujando. Alimentadores afectados: '
                f'{", ".join(sorted(por_alimentador)) or "ninguno con carga"}.'
            )

    combinado = FeederModel(
        name=name,
        network_id=name,
        nominal_kv=kv_dominante,
        source_node=principal.source_node,
        nodes=nodes,
        lines=lines,
        loads=loads,
        devices=devices,
        line_types=line_types,
        seds=seds,
        warnings=informe.warnings,
        section_by_id={ln.section_id: ln for ln in lines},
        combined=CombinedInfo(
            feeders=feeders,
            node_kv=node_kv,
            type_kv=type_kv,
            tie_nodes=tie_nodes,
            voltage_conflicts=sorted(conflictivos),
            feeder_of_node={n: sorted(set(f)) for n, f in feeder_of_node.items()},
            de_energised=sin_alimentar,
            ties=ties,
        ),
    )
    return combinado, informe


def build_combined(
    dataset, *, selectors: Sequence[str] | None = None, strict: bool = False,
    include_geography: bool = True, aliases=None, name: str = 'SISTEMA',
) -> tuple[FeederModel, CombineReport]:
    """Construye todos los alimentadores del dataset y los une.

    Un alimentador que no se puede construir **no detiene la unión**: queda anotado en
    ``report.skipped``. Con 96 alimentadores, que uno tenga una fila corrupta no puede
    impedir estudiar los otros 95.
    """
    from .model import build_feeder_model

    elegidos = set(selectors or ())
    modelos = []
    informe_parcial: list[str] = []
    for network_id in dataset.feeder_ids():
        try:
            m = build_feeder_model(
                dataset, network_id, aliases=aliases, strict=strict,
                include_geography=include_geography,
            )
        except Exception as exc:  # noqa: BLE001 - uno roto no para los demás
            informe_parcial.append(f'{network_id}: {exc}')
            continue
        if elegidos and m.name not in elegidos and network_id not in elegidos:
            continue
        modelos.append(m)

    if not modelos:
        raise ValueError(
            'Ningún alimentador se pudo construir.\n'
            + '\n'.join(informe_parcial[:10])
        )
    combinado, informe = combine_models(modelos, name=name)
    informe.skipped = informe_parcial
    return combinado, informe
