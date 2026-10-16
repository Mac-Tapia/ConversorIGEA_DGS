"""Reconstrucción auditable de una selección de alimentadores, sin estado de la web.

Estaba dentro de ``web/reconstruction_service.py``, atada al espacio de trabajo: solo
la web podía reconstruir. ``vnr-etl export`` necesita los mismos pasos para no negarse
a exportar un modelo con datos ausentes (spec 001, RF-17), y copiar la secuencia
habría abierto dos vías que acabarían divergiendo (constitución P5). Aquí está la
secuencia una sola vez; la web y VNR la llaman.

Cada paso trabaja sobre la copia de :func:`reconstruction.reconstruct_dataset` y
registra cada cambio con su evidencia: el dataset original nunca se toca.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .catalog_resolution import CatalogSource
from .reconstruction import (
    EvidenceLevel, ReconstructionPolicy, ReconstructionResult, reconstruct_dataset,
)
from .reconstruction_topology import repair_discontinuities, repair_missing_nodes
from .util import sha256_file

Paso = Callable[[int, int, str], None]
"""``paso(indice, total, etiqueta)``: avance y, en un trabajo, punto de cancelación."""

PASOS = 7


def reconstruir_seleccion(
    dataset,
    network_ids: Sequence[str],
    catalogos: Iterable[CatalogSource] = (),
    *,
    policy: ReconstructionPolicy | None = None,
    paso: Paso | None = None,
) -> tuple[ReconstructionResult, dict]:
    """Reconstruye los alimentadores elegidos; devuelve el resultado y los equipos resueltos."""
    avance = paso or (lambda *_args: None)
    avance(0, PASOS, 'Reconstruir el dataset')
    result = reconstruct_dataset(dataset, policy or ReconstructionPolicy(), ())
    result.report.metadata['selected_network_ids'] = list(network_ids)
    avance(1, PASOS, 'Fuentes')
    _repair_missing_sources(result, network_ids)
    avance(2, PASOS, 'Configuraciones de línea')
    _repair_missing_line_configurations(result, network_ids)
    avance(3, PASOS, 'Nodos')
    repair_missing_nodes(result, network_ids)
    avance(4, PASOS, 'Continuidad')
    repair_discontinuities(result, network_ids)
    avance(5, PASOS, 'Coordenadas')
    _complete_coordinates(result, network_ids)
    avance(6, PASOS, 'Catálogo')
    resolutions = result.resolve_equipment(tuple(catalogos), network_ids)
    return result, resolutions


def catalogos_del_fichero(path: Path | str | None) -> tuple[CatalogSource, ...]:
    """El catálogo de parámetros (Excel) como fuente del resolvedor; vacío si no hay."""
    if path is None or not Path(path).is_file():
        return ()
    path = Path(path)
    from .catalog import tablas_equipo_desde_catalogo

    parsed = tablas_equipo_desde_catalogo(path)
    rows = tuple(
        {**row, 'EquipmentClass': table, 'Overhead': table == 'LINE'}
        for table, table_rows in parsed.tablas.items()
        for row in table_rows
    )
    return (CatalogSource(
        name=path.stem,
        kind='global',
        version=str(path.stat().st_mtime_ns),
        manufacturer='',
        locator=str(path.resolve()),
        sha256=sha256_file(path),
        rows=rows,
    ),)


def _repair_missing_sources(result, network_ids: Iterable[str]) -> None:
    dataset = result.dataset
    for network_id in network_ids:
        if network_id in dataset.sources:
            continue
        headnodes = sorted(node for node, owner in dataset.headnodes.items() if owner == network_id)
        node_id = headnodes[0] if headnodes else ''
        if not node_id:
            continue
        inferred = _infer_voltage(dataset, network_id)
        voltage = inferred or result.policy.provisional_nominal_voltage_kv
        row = {'NetworkID': network_id, 'NodeID': node_id, 'DesiredVoltage': f'{voltage:g}'}
        dataset.sources[network_id] = row
        result.record_change(
            entity_type='source', entity_id=network_id, field='__row__',
            original_value=None, applied_value=row,
            level=EvidenceLevel.ENGINEERING_ASSUMPTION,
            rule='RECOVER_REFERENCED_NODE',
            reason='A unique declared headnode was used to reconstruct the omitted source.',
            confidence=0.45 if inferred is None else 0.7,
            provenance={
                'voltage_inferred': inferred is not None,
                'policy_fallback_kv': (
                    result.policy.provisional_nominal_voltage_kv if inferred is None else None
                ),
            },
        )


def _repair_missing_line_configurations(result, network_ids: Iterable[str]) -> None:
    dataset = result.dataset
    selected = set(network_ids)
    for section_id, section in sorted(dataset.sections.items()):
        if dataset.section_owner.get(section_id) not in selected:
            continue
        if section_id in dataset.line_configurations:
            continue
        length = _section_distance(dataset, section) or 1.0
        row = {
            'SectionID': section_id,
            'LineCableID': '',
            'Length': f'{length:.12g}',
            'Overhead': str(section.get('Overhead', '1')),
        }
        dataset.line_configurations[section_id] = row
        result.record_change(
            entity_type='line_configuration', entity_id=section_id, field='__row__',
            original_value=None, applied_value=row,
            level=EvidenceLevel.ENGINEERING_ASSUMPTION,
            rule='PROVISIONAL_PROFILE',
            reason='The section had no line configuration; length was derived from coordinates or a 1 m floor.',
            confidence=0.4 if length != 1.0 else 0.2,
        )


def _complete_coordinates(result, network_ids: Iterable[str]) -> None:
    from copy import deepcopy

    from .coordenadas import completar_coordenadas

    dataset = result.dataset
    selected = set(network_ids)
    selected_nodes = {
        node_id
        for section_id, section in dataset.sections.items()
        if dataset.section_owner.get(section_id) in selected
        for node_id in (section.get('FromNodeID'), section.get('ToNodeID'))
        if node_id
    }
    all_before = deepcopy(dataset.nodes)
    before = {node_id: deepcopy(dataset.nodes.get(node_id, {})) for node_id in selected_nodes}
    completar_coordenadas(dataset)
    for node_id, row in all_before.items():
        if node_id not in selected_nodes:
            dataset.nodes[node_id] = row
    for node_id in sorted(selected_nodes):
        old = before.get(node_id, {})
        current = dataset.nodes.get(node_id, {})
        for field in ('CoordX', 'CoordY', 'CoordOrigen'):
            if old.get(field) == current.get(field):
                continue
            result.record_change(
                entity_type='node', entity_id=node_id, field=field,
                original_value=old.get(field), applied_value=current.get(field),
                level=EvidenceLevel.ENGINEERING_ASSUMPTION,
                rule='CREATE_TERMINAL_NODE',
                reason='Missing coordinates were derived deterministically from the feeder graph.',
                confidence=0.6,
                provenance={'coordinate_method': 'graph'},
            )


def _section_distance(dataset, section) -> float | None:
    points = []
    for key in ('FromNodeID', 'ToNodeID'):
        row = dataset.nodes.get(section.get(key), {})
        try:
            point = float(row.get('CoordX')), float(row.get('CoordY'))
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in point):
            return None
        points.append(point)
    return math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1])


def _infer_voltage(dataset, network_id: str) -> float | None:
    for section_id in dataset.feeders.get(network_id, ()):
        for row in (
            dataset.sections.get(section_id, {}),
            dataset.line_configurations.get(section_id, {}),
        ):
            for key in ('NominalVoltageKV', 'VoltageKV', 'kV'):
                try:
                    value = float(row.get(key))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > 0:
                    return value
    return None
