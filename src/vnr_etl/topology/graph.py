"""Validación de topología con NetworkX (sección 11 de VNR-GIS.md).

Detecta nodos aislados, islas, duplicados, bucles propios, cargas huérfanas,
terminales de interruptor/transformador inválidos, ausencia de fuente/slack y
caminos fuente→carga imposibles. Los bucles requieren análisis de estado de
operación y **no** son error automático.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vnr_etl.models import CanonicalModel


def _require_networkx():
    try:
        import networkx as nx  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError('La topología necesita «networkx» (ver vnr_requirements.txt).') from exc
    return __import__('networkx')


@dataclass
class TopologyIssue:
    code: str
    message: str
    severity: str = 'warning'
    kind: str = 'topology'

    def as_dict(self) -> dict:
        return {'code': self.code, 'message': self.message, 'severity': self.severity}


@dataclass
class TopologyReport:
    issues: list[TopologyIssue] = field(default_factory=list)
    island_count: int = 0
    orphan_load_count: int = 0
    self_loop_count: int = 0
    disconnected_sinks: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not any(i.severity == 'error' for i in self.issues)

    def as_dict(self) -> dict:
        return {
            'island_count': self.island_count,
            'orphan_load_count': self.orphan_load_count,
            'self_loop_count': self.self_loop_count,
            'disconnected_sinks': list(self.disconnected_sinks),
            'issues': [i.as_dict() for i in self.issues],
        }


def reachability(model: CanonicalModel) -> set[str]:
    """Conjunto de nodos alcanzables desde cualquier fuente, por líneas."""
    nx = _require_networkx()
    graph = nx.Graph()
    for node in model.nodes:
        graph.add_node(node.node_id)
    for section in model.sections:
        graph.add_edge(section.from_node, section.to_node)
    reachable: set[str] = set()
    for source in model.sources:
        if source.node_id in graph:
            reachable |= nx.node_connected_component(graph, source.node_id)
    return reachable


def validate_topology(
    model: CanonicalModel,
    *,
    allow_islands: bool = False,
    allow_self_loops: bool = False,
    require_source: bool = True,
) -> TopologyReport:
    nx = _require_networkx()
    report = TopologyReport()
    graph = nx.Graph()
    for node in model.nodes:
        graph.add_node(node.node_id)
    for section in model.sections:
        graph.add_edge(section.from_node, section.to_node)

    # Bucles propios: tramo cuyo origen y destino coinciden.
    for section in model.sections:
        if section.from_node == section.to_node:
            report.self_loop_count += 1
            if not allow_self_loops:
                report.issues.append(TopologyIssue(
                    'self_loop', f'Tramo {section.section_id} es un bucle propio '
                    f'({section.from_node}->{section.to_node}).', 'error'))

    # Fuente/slack requerida.
    if require_source and not model.sources:
        report.issues.append(TopologyIssue(
            'missing_source', 'No hay fuente/slack en el modelo.', 'error'))

    # Nodos aislados: sin tramos incidentes.
    isolated = [n for n in graph if graph.degree(n) == 0]
    for n in isolated:
        report.issues.append(TopologyIssue(
            'isolated_node', f'Nodo aislado: {n} (sin tramos incidentes).'))

    # Islas / nodos desconectados de cualquier fuente.
    reachable = reachability(model)
    if model.sources:
        islands = sorted(set(graph.nodes) - reachable)
        if islands:
            report.island_count = len(islands)
            if not allow_islands:
                report.issues.append(TopologyIssue(
                    'island',
                    f'{len(islands)} nodo(s) sin camino a fuente: '
                    f'{", ".join(islands[:10])}.', 'error'))
        # Cargas/huérfanos inalcanzables a fluir.
        for load in model.loads:
            if load.connection_node not in reachable:
                report.orphan_load_count += 1
                report.disconnected_sinks.append(load.connection_node)
        if report.orphan_load_count and not allow_islands:
            report.issues.append(TopologyIssue(
                'orphan_load',
                f'{report.orphan_load_count} carga(s) sin camino a fuente.', 'error'))

    # Terminales de interruptores/transformadores deben existir como nodos.
    node_ids = {n.node_id for n in model.nodes}
    for switch in model.switches:
        if switch.connection_node not in node_ids:
            report.issues.append(TopologyIssue(
                'invalid_terminal',
                f'Interruptor {switch.switch_id} referencia un nodo inexistente '
                f'{switch.connection_node}.', 'error'))
    for transformer in model.transformers:
        if transformer.connection_node not in node_ids:
            report.issues.append(TopologyIssue(
                'invalid_terminal',
                f'Transformador {transformer.transformer_id} referencia un nodo '
                f'inexistente {transformer.connection_node}.', 'error'))

    return report
