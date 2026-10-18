"""Puente explícito del modelo canónico VNR al contrato del conversor IGEA.

El puente no completa datos ausentes. Construye un inventario navegable y devuelve
por alimentador las puertas que impiden declararlo listo para conversión.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from igea_dgs.dataset import CymdistDataset
from vnr_etl.models import CanonicalModel


@dataclass
class BridgeResult:
    dataset: CymdistDataset
    readiness: dict[str, dict[str, Any]]
    issues: list[dict[str, Any]]


def _text(value: Any) -> str:
    return '' if value is None else str(value)


def canonical_to_cymdist(
    model: CanonicalModel,
    *,
    source_path: Path,
) -> BridgeResult:
    """Convierte identidades exactas y marca como bloqueado lo que no puede mapear."""
    issues: list[dict[str, Any]] = []
    sections: dict[str, dict[str, str]] = {}
    section_owner: dict[str, str] = {}
    feeders: dict[str, list[str]] = defaultdict(list)
    line_configurations: dict[str, dict[str, str]] = {}

    tipos = {item.conductor_code: item for item in model.conductor_types}
    for section in model.sections:
        feeder = (section.feeder_id or '').strip()
        if not feeder:
            issues.append({
                'code': 'MISSING_FEEDER_ID', 'object_type': 'section',
                'source_id': section.section_id,
            })
            continue
        if section.section_id in sections:
            raise ValueError(f'Identificador de tramo duplicado en puente: {section.section_id}')
        sections[section.section_id] = {
            'SectionID': section.section_id,
            'FromNodeID': section.from_node,
            'ToNodeID': section.to_node,
            'Phase': section.phases,
        }
        section_owner[section.section_id] = feeder
        feeders[feeder].append(section.section_id)
        line_configurations[section.section_id] = {
            'SectionID': section.section_id,
            'LineCableID': section.conductor_code,
            'Length': _text(section.length_m),
            'Overhead': '1',
        }
        # Material y sección permiten al resolvedor buscar un conductor compatible en el
        # catálogo de parámetros cuando el código no está (spec 001, RF-18).
        tipo = tipos.get(section.conductor_code)
        if tipo is not None:
            if tipo.material:
                line_configurations[section.section_id]['Material'] = tipo.material
            if tipo.section_mm2:
                line_configurations[section.section_id]['SectionMM2'] = _text(tipo.section_mm2)

    nodes = {
        node.node_id: {
            'NodeID': node.node_id,
            'CoordX': _text(node.x),
            'CoordY': _text(node.y),
            'Phase': node.phases,
        }
        for node in model.nodes
    }

    sources: dict[str, dict[str, str]] = {}
    headnodes: dict[str, str] = {}
    for source in model.sources:
        feeder = (source.feeder_id or '').strip()
        if not feeder:
            candidates = {
                section_owner[sid]
                for sid, section in sections.items()
                if source.node_id in (section['FromNodeID'], section['ToNodeID'])
            }
            feeder = next(iter(candidates)) if len(candidates) == 1 else ''
        if not feeder or feeder not in feeders:
            issues.append({
                'code': 'UNRESOLVED_SOURCE_FEEDER', 'object_type': 'source',
                'source_id': source.source_id,
            })
            continue
        if feeder in sources:
            raise ValueError(f'Más de una fuente para el alimentador {feeder}.')
        sources[feeder] = {
            'SourceID': source.source_id,
            'DeviceNumber': source.source_id,
            'NodeID': source.node_id,
            'NetworkID': feeder,
            'DesiredVoltage': _text(source.nominal_kv),
        }
        headnodes[source.node_id] = feeder

    by_node: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for section_id, section in sections.items():
        feeder = section_owner[section_id]
        by_node[(feeder, section['FromNodeID'])].append((section_id, '0'))
        by_node[(feeder, section['ToNodeID'])].append((section_id, '1'))

    load_placements: dict[tuple[str, str], dict[str, str]] = {}
    customer_loads: dict[tuple[str, str], dict[str, str]] = {}
    mapped_loads: dict[str, int] = defaultdict(int)
    for load in model.loads:
        feeder = (load.feeder_id or '').strip()
        candidates: list[tuple[str, str, str]] = []
        if feeder:
            candidates = [(feeder, sid, location) for sid, location in by_node.get(
                (feeder, load.connection_node), [])]
        else:
            for (candidate_feeder, node_id), placements in by_node.items():
                if node_id == load.connection_node:
                    candidates.extend(
                        (candidate_feeder, sid, location) for sid, location in placements
                    )
        if len(candidates) > 1 and len({feeder for feeder, _sid, _loc in candidates}) == 1:
            # Varios tramos del mismo alimentador tocan el nodo de la carga: cualquiera la
            # conecta al mismo nodo. Se toma el primero por identificador, para que sea
            # determinista, en vez de dejar la carga fuera del DGS.
            candidates = sorted(candidates, key=lambda item: (item[1], item[2]))[:1]
        if len(candidates) != 1:
            issues.append({
                'code': 'AMBIGUOUS_LOAD_SECTION' if candidates else 'MISSING_LOAD_SECTION',
                'object_type': 'load', 'source_id': load.load_id,
            })
            continue
        feeder, section_id, location = candidates[0]
        apparent = math.hypot(load.kw, load.kvar)
        if apparent and not load.kw:
            issues.append({
                'code': 'PURE_REACTIVE_LOAD_UNSUPPORTED',
                'object_type': 'load', 'source_id': load.load_id,
            })
            continue
        power_factor = abs(load.kw) / apparent if apparent else 1.0
        if load.kvar < 0:
            power_factor = -power_factor
        key = (section_id, load.load_id)
        load_placements[key] = {
            'SectionID': section_id,
            'DeviceNumber': load.load_id,
            'LoadType': 'SPOT',
            'Location': location,
        }
        # CYMDIST ValueType 2 guarda kW + FP; el FP se deriva exactamente de P/Q.
        customer_loads[key] = {
            'SectionID': section_id,
            'DeviceNumber': load.load_id,
            'CustomerNumber': load.load_id,
            'ValueType': '2',
            'Value1': _text(load.kw),
            'Value2': _text(power_factor),
            # Spec 023: la potencia instalada de la SED, si la fuente la trae.
            'ConnectedKVA': _text(getattr(load, 'connected_kva', None) or ''),
            'KWH': '',
            'Phase': load.phases,
            'NumberOfCustomer': '1',
            'CustomerType': 'VNR',
            'Year': '',
        }
        mapped_loads[feeder] += 1

    capacitor_settings = tuple({
        'DeviceNumber': capacitor.capacitor_id,
        'NetworkID': capacitor.feeder_id,
        'NodeID': capacitor.connection_node,
        'Phase': capacitor.phases,
        # ``kvar`` del contrato VNR es potencia total. Cero significa ausente:
        # no se transforma en un banco de 0 ni en un valor por defecto.
        'TotalKVAR': _text(capacitor.kvar) if capacitor.kvar > 0 else '',
        'KVARPerStep': '',
        'NumberOfSteps': _text(capacitor.steps),
        'NominalKV': _text(capacitor.nominal_kv),
        'Status': capacitor.status,
        'SourceTable': capacitor.source_layer or 'VNR_CAPACITOR',
    } for capacitor in model.capacitors)

    conductor_types = {item.conductor_code: item for item in model.conductor_types}
    equipment_rows = []
    for conductor in model.conductor_types:
        equipment_rows.append({
            'ID': conductor.conductor_code,
            'R1': _text(conductor.r1_ohm_km),
            'X1': _text(conductor.x1_ohm_km),
            'R0': _text(conductor.r0_ohm_km),
            'X0': _text(conductor.x0_ohm_km),
            'B1': '0',
            'B0': '0',
            'Amps': _text(conductor.ampacity_a),
        })

    # Spec 023: las maniobras con su tramo y los vértices intermedios de cada tramo, que
    # la copia de VNR-GIS trae y el puente no pasaba (líneas rectas, ninguna maniobra).
    switch_settings, sectionalizer_settings = [], []
    for switch in model.switches:
        section = sections.get(getattr(switch, 'section_id', ''))
        if section is None:
            continue
        row = {
            'SectionID': section['SectionID'], 'EqID': switch.kind or 'SWITCH',
            'EqNumber': switch.switch_id, 'EqPhase': section.get('Phase', ''),
            'Location': getattr(switch, 'location', '') or 'L',
            'Status': '1' if switch.on_off else '0', 'Locked': '0', 'EqState': '0',
        }
        (sectionalizer_settings if getattr(switch, 'sectionalizer', False)
         else switch_settings).append(row)
    intermediate_nodes = []
    for section in model.sections:
        if section.section_id not in sections or not section.geometry:
            continue
        for i, (x, y) in enumerate(section.geometry[1:-1], start=1):
            intermediate_nodes.append({'SectionID': section.section_id, 'SeqNumber': str(i),
                                       'CoordX': _text(x), 'CoordY': _text(y)})

    dataset = CymdistDataset(
        red_path=Path(source_path), loads_path=Path(source_path), equipment_path=Path(source_path),
        headnodes=headnodes,
        nodes=nodes,
        sources=sources,
        line_configurations=line_configurations,
        sections=sections,
        section_owner=section_owner,
        feeders={feeder: tuple(section_ids) for feeder, section_ids in feeders.items()},
        switch_settings=tuple(switch_settings),
        sectionalizer_settings=tuple(sectionalizer_settings),
        intermediate_nodes=tuple(intermediate_nodes),
        load_placements=load_placements,
        customer_loads=customer_loads,
        equipment_tables={'LINE': tuple(equipment_rows)},
        capacitor_settings=capacitor_settings,
    )

    projected = model.metadata.get('working_crs_is_projected') is True
    readiness: dict[str, dict[str, Any]] = {}
    for feeder, section_ids in dataset.feeders.items():
        blocking: list[str] = []
        source = sources.get(feeder)
        if source is None:
            blocking.append('MISSING_SOURCE')
        elif not source.get('DesiredVoltage'):
            blocking.append('MISSING_NOMINAL_VOLTAGE')
        if not mapped_loads.get(feeder):
            blocking.append('MISSING_LOADS')
        codes = {
            line_configurations[sid].get('LineCableID', '') for sid in section_ids
        }
        if any(not code or code not in conductor_types for code in codes):
            blocking.append('MISSING_CONDUCTOR_CATALOG')
        for code in sorted(codes):
            conductor = conductor_types.get(code)
            if conductor and any(
                value is None for value in (
                    conductor.r1_ohm_km, conductor.x1_ohm_km,
                    conductor.r0_ohm_km, conductor.x0_ohm_km, conductor.ampacity_a,
                )
            ):
                blocking.append('MISSING_CONDUCTOR_PARAMETERS')
                break
        if any(not sections[sid].get('Phase') for sid in section_ids):
            blocking.append('MISSING_PHASES')
        if not projected:
            blocking.append('MISSING_PROJECTED_CRS')
        blocking = list(dict.fromkeys(blocking))
        readiness[feeder] = {
            'feeder': feeder,
            'network_id': feeder,
            'status': 'CONVERSION_READY' if not blocking else 'INVENTORY_ONLY',
            'blocking_codes': blocking,
        }
    return BridgeResult(dataset=dataset, readiness=readiness, issues=issues)
