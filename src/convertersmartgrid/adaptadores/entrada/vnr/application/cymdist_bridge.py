"""Puente explícito del modelo canónico VNR al contrato del ConverterSmartGrid.

El puente no completa datos ausentes. Construye un inventario navegable y devuelve
por alimentador las puertas que impiden declararlo listo para conversión.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import logging
import math
from pathlib import Path
import re
from typing import Any

from convertersmartgrid.dataset import CymdistDataset
from convertersmartgrid.adaptadores.entrada.vnr.models import CanonicalModel
# 080:RF-53, RF-55: las reglas de estado y medio, de su módulo de dominio (se reexportan aquí).
from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import (  # noqa: F401
    AEREO, CABLE, EN_SERVICIO, ESTADOS_VNR, FUERA_DE_SERVICIO, TIPOS_RED, anotar_sin_regla,
    estado_de_tramo, fuera_de_servicio, medio_de_tipo_red)


@dataclass
class BridgeResult:
    dataset: CymdistDataset
    readiness: dict[str, dict[str, Any]]
    issues: list[dict[str, Any]]


def _text(value: Any) -> str:
    return '' if value is None else str(value)


#: Clave del perfil de empresa con la regla de los tipos que son cable (080:RF-53).
CLAVE_PERFIL_CABLE = 'vnr_patron_tipo_cable'


def patron_cable_del_perfil() -> str | None:
    """La regla del perfil activo para los tipos de cable, o None si no la da o no se puede leer."""
    try:
        from convertersmartgrid.perfil_empresa import datos_perfil

        valor = datos_perfil().get(CLAVE_PERFIL_CABLE)
    except Exception as exc:  # noqa: BLE001  # justificado: un perfil ilegible no impide convertir (reconstruir, no bloquear); queda el aviso con su causa
        logging.getLogger(__name__).warning(
            'PERFIL_ILEGIBLE: no se pudo leer %s del perfil de la empresa (%s: %s); el medio de cada tramo se deduce de la '
            'fuente (080:RF-53)', CLAVE_PERFIL_CABLE, type(exc).__name__, exc)
        return None
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def deducir_medio(section, tipo, patron_cable: str | None = None) -> tuple[bool, str]:
    """(aéreo, método) de un tramo (080:RF-53), en este orden:

    1. ``SOURCE``: el tramo o su tipo lo dicen (``overhead`` no es None).
    2. ``PROFILE_RULE``: la regla del perfil (expresión regular) casa con el código, la
       descripción de la norma o la capa: es cable.
    3. ``SOURCE_LAYER``: la capa de la fuente dice aéreo o subterráneo.
    4. ``CONDUCTOR_TYPE``: el código o la descripción de la norma dicen aéreo o cable.
    5. ``DEFAULT_OVERHEAD``: nada lo dice; aéreo, como la mayoría de la MT, y se anota.
    """
    if getattr(section, 'overhead', None) is not None:
        return bool(section.overhead), 'SOURCE'
    if tipo is not None and getattr(tipo, 'overhead', None) is not None:
        return bool(tipo.overhead), 'SOURCE'
    codigo = section.conductor_code or ''
    descripcion = (getattr(tipo, 'description', '') or '') if tipo is not None else ''
    capa = section.source_layer or ''
    if patron_cable:
        try:
            regla = re.compile(patron_cable, re.I)
        except re.error:
            regla = None
        if regla is not None and any(regla.search(t) for t in (codigo, descripcion, capa) if t):
            return False, 'PROFILE_RULE'
    if AEREO.search(capa):
        return True, 'SOURCE_LAYER'
    if CABLE.search(capa):
        return False, 'SOURCE_LAYER'
    del_tipo = f'{codigo} {descripcion}'
    if AEREO.search(del_tipo):
        return True, 'CONDUCTOR_TYPE'
    if CABLE.search(del_tipo):
        return False, 'CONDUCTOR_TYPE'
    return True, 'DEFAULT_OVERHEAD'


#: 080:RF-58: cómo decide la clase el paso (3), dicho en el issue.
PASO_3_CLASE = 'paso (3): criterio de fase del usuario con margen; si ninguna clase cumple, tabla 1 por Um'


def _susceptancia_de_cable(tipo, kv: float | None) -> tuple[float, dict[str, Any]]:
    """080:RF-58: B (µS/km) de un cable VNR sin capacitancia en la fuente, con su issue.

    La clase del cable, por este orden: la de su designación en la fuente (CLASE_DE_LA_FUENTE); la
    de la ficha que ya le dio R y X, para que el tramo sea un solo cable (CLASE_COHERENTE_CON_RX); o la
    de la tensión de fase de la red (CLASE_POR_TENSION_DE_FASE, :func:`catalog.regla_de_clase`): paso (3),
    criterio de fase del usuario con margen; si ninguna clase cumple, tabla 1 por Um. Con la clase, de la ficha del catálogo si la hay; si no, de la geometría del
    cable apantallado, C = 2π·ε0·εr / ln(Di/dc) (εr del XLPE 2,5: IEC 60287-1-1, tabla 3, según
    quickfield.com; el 3,0 del EPR, supuesto; Di con el espesor de aislamiento de IEC 60502-2). B1 = B0: en un cable unipolar apantallado
    el campo queda dentro de la pantalla y la capacitancia homopolar es la misma.
    """
    from convertersmartgrid.catalog import (
        capacitancia_cable, clase_de_designacion, regla_de_clase, seccion_de_codigo, susceptancia_us_km)

    texto = f'{tipo.conductor_code} {getattr(tipo, "description", "") or ""}'.upper()
    aislante = 'EPR' if re.search(r'\bEPR\b', texto) else 'XLPE'
    seccion = tipo.section_mm2 or seccion_de_codigo(tipo.conductor_code)
    kv = kv or tipo.nominal_kv
    clase = clase_de_designacion(texto)
    metodo_clase, regla = 'CLASE_DE_LA_FUENTE', ''
    if not clase and getattr(tipo, 'clase_cable_rx', ''):
        clase, metodo_clase = tipo.clase_cable_rx, 'CLASE_COHERENTE_CON_RX'
    if not clase:
        clase, regla = regla_de_clase(kv)
        metodo_clase = 'CLASE_POR_TENSION_DE_FASE'
    c_uf_km, metodo, detalle = capacitancia_cable(seccion, kv, aislante, clase=clase)
    b = susceptancia_us_km(c_uf_km)
    return b, {
        'code': 'CAPACITANCIA_DEDUCIDA', 'object_type': 'conductor_type',
        'source_id': tipo.conductor_code, 'severity': 'deducido', 'metodo': metodo,
        'clase': clase, 'metodo_clase': metodo_clase, 'regla_clase': regla,
        'criterio_clase': (PASO_3_CLASE if metodo_clase == 'CLASE_POR_TENSION_DE_FASE' else ''),
        'c_uf_km': round(c_uf_km, 4), 'b_us_km': round(b, 3), 'detalle': detalle,
    }


#: 080:RF-53, RF-55: el issue de cada valor de la fuente sin regla, por el campo en que se anotó.
SIN_REGLA_POR_CAMPO: dict[str, tuple[str, str, str]] = {
    'estado': ('STATUS_UNKNOWN', 'section', 'sin regla: el tramo queda en servicio'),
    'tipo_red': ('NETWORK_TYPE_UNKNOWN', 'section', 'sin regla: el medio se deduce de la capa y la norma'),
    'tipo_equipo': ('EQUIPMENT_TYPE_UNKNOWN', 'equipment', 'sin regla: el equipo no se modela'),
}


def canonical_to_cymdist(
    model: CanonicalModel,
    *,
    source_path: Path,
    patron_cable: str | None = None,
) -> BridgeResult:
    """Convierte identidades exactas y marca como bloqueado lo que no puede mapear.

    ``patron_cable`` es la regla del perfil de la empresa para los tipos que son cable
    (:func:`patron_cable_del_perfil`); sin ella, el medio se deduce de la fuente (080:RF-53).
    """
    issues: list[dict[str, Any]] = []
    sections: dict[str, dict[str, str]] = {}
    section_owner: dict[str, str] = {}
    feeders: dict[str, list[str]] = defaultdict(list)
    line_configurations: dict[str, dict[str, str]] = {}
    # 080:RF-53: qué medio se dedujo, por tipo y método, para anotarlo una vez por tipo.
    deducidos: Counter[tuple[str, bool, str]] = Counter()
    medios_por_tipo: dict[str, set[bool]] = defaultdict(set)
    kv_por_tipo: dict[str, float] = {}
    fuera: list[str] = []
    # 080:RF-53, RF-55: un valor de la fuente sin regla no se adivina: se dice, con sus tramos.
    # 080:RF-55: un TIPO de equipo sin regla es de un equipo, no el estado de un tramo.
    for campo, valores in sorted((model.metadata.get('valores_sin_regla') or {}).items()):
        code, objeto, detalle = SIN_REGLA_POR_CAMPO.get(campo, SIN_REGLA_POR_CAMPO['estado'])
        for valor, tramos in sorted(valores.items()):
            issues.append({
                'code': code, 'object_type': objeto, 'source_id': valor, 'severity': 'deducido',
                'campo': campo, 'tramos': tramos, 'detalle': detalle,
            })

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
        tipo = tipos.get(section.conductor_code)
        # 080:RF-53: aéreo o cable, de la fuente o deducido; antes, todo tramo salía aéreo.
        aereo, metodo = deducir_medio(section, tipo, patron_cable)
        if metodo != 'SOURCE':
            deducidos[(section.conductor_code, aereo, metodo)] += 1
        medios_por_tipo[section.conductor_code].add(aereo)
        config = line_configurations[section.section_id] = {
            'SectionID': section.section_id,
            'LineCableID': section.conductor_code,
            'Length': _text(section.length_m),
            'Overhead': '1' if aereo else '0',
        }
        # 080:RF-54: la tensión del tramo, para que el resolvedor busque el tipo de su tensión.
        kv = section.nominal_kv or (tipo.nominal_kv if tipo is not None else None)
        if kv:
            config['NominalKV'] = _text(kv)
            kv_por_tipo[section.conductor_code] = max(kv, kv_por_tipo.get(section.conductor_code, 0.0))
        # Material y sección permiten al resolvedor buscar un conductor compatible en el
        # catálogo de parámetros cuando el código no está (spec 001, RF-18).
        if tipo is not None:
            if tipo.material:
                config['Material'] = tipo.material
            if tipo.section_mm2:
                config['SectionMM2'] = _text(tipo.section_mm2)
            # 080:RF-54: y lo que el tipo VNR sí trae (R, X, amperios) llega al resolvedor.
            for campo, valor in (('R1', tipo.r1_ohm_km), ('X1', tipo.x1_ohm_km),
                                 ('R0', tipo.r0_ohm_km), ('X0', tipo.x0_ohm_km),
                                 ('Amps', tipo.ampacity_a)):
                if valor is not None:
                    config[campo] = _text(valor)
        if fuera_de_servicio(section.status):
            fuera.append(section.section_id)
    for (codigo, aereo, metodo), tramos in sorted(deducidos.items()):
        # 080:RF-53: reconstruir, no bloquear: se deduce y se dice, una vez por tipo y método.
        issues.append({
            'code': 'OVERHEAD_DEDUCED' if aereo else 'CABLE_DEDUCED',
            'object_type': 'conductor_type', 'source_id': codigo,
            'severity': 'deducido', 'metodo': metodo, 'tramos': tramos,
        })

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
            # 080:RF-44: viene de la tabla Sed: es una SED, tenga el código que tenga.
            # 080:RF-46: con su código operativo, si lo tiene.
            'SedCode': (getattr(load, 'etiqueta', '') or load.load_id)
            if getattr(load, 'source_layer', '') == 'Sed' else '',
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
    # 080:RF-53: el tipo va a la tabla de su medio (LINE o CONCENTRIC NEUTRAL CABLE); uno
    # que usan tramos aéreos y cables, a las dos. Sin tramos que lo usen, a LINE, como antes.
    equipment_tables: dict[str, list[dict[str, str]]] = {'LINE': []}
    for conductor in model.conductor_types:
        row = {
            'ID': conductor.conductor_code,
            'R1': _text(conductor.r1_ohm_km),
            'X1': _text(conductor.x1_ohm_km),
            'R0': _text(conductor.r0_ohm_km),
            'X0': _text(conductor.x0_ohm_km),
            'B1': '0',
            'B0': '0',
            'Amps': _text(conductor.ampacity_a),
        }
        for aereo in sorted(medios_por_tipo.get(conductor.conductor_code) or {True}, reverse=True):
            tabla = 'LINE' if aereo else 'CONCENTRIC NEUTRAL CABLE'
            fila = dict(row)
            if not aereo:
                # 080:RF-58: un cable no queda con capacitancia 0: de su ficha o de su geometría.
                b, issue = _susceptancia_de_cable(conductor, kv_por_tipo.get(conductor.conductor_code))
                fila['B1'] = fila['B0'] = format(b, '.12g')
                issues.append(issue)
            equipment_tables.setdefault(tabla, []).append(fila)

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
    # 080:RF-55: un tramo fuera de servicio no entra energizado: se abre por sus dos extremos,
    # con su propia maniobra si la tiene o con una que lo dice, y se conserva en la red.
    for section_id in fuera:
        section = sections[section_id]
        for lado in ('S', 'L'):
            propias = [r for r in (*switch_settings, *sectionalizer_settings)
                       if r['SectionID'] == section_id and r['Location'].upper() == lado]
            for r in propias:
                r['Status'] = '0'
            if not propias:
                switch_settings.append({
                    'SectionID': section_id, 'EqID': 'FUERA_DE_SERVICIO',
                    'EqNumber': f'{section_id}_FS_{lado}', 'EqPhase': section.get('Phase', ''),
                    'Location': lado, 'Status': '0', 'Locked': '0', 'EqState': '0',
                })
        issues.append({
            'code': 'SECTION_OUT_OF_SERVICE', 'object_type': 'section',
            'source_id': section_id, 'severity': 'deducido',
            'detalle': 'abierto por sus dos extremos: no entra energizado',
        })
    intermediate_nodes = []
    for section in model.sections:
        if section.section_id not in sections or not section.geometry:
            continue
        for i, (x, y) in enumerate(section.geometry[1:-1], start=1):
            intermediate_nodes.append({'SectionID': section.section_id, 'SeqNumber': str(i),
                                       'CoordX': _text(x), 'CoordY': _text(y)})

    # 080:RF-38: los bancos de regulación, por el tramo auxiliar que los sostiene.
    regulator_settings = tuple({
        'SectionID': r.section_id, 'EqNumber': r.regulator_id, 'Units': str(r.unidades),
        'Amps': _text(r.corriente_a), 'NominalKV': _text(r.nominal_kv),
        'Status': '1' if r.on_off else '0', 'Norma': r.norma,
    } for r in model.regulators if r.section_id in sections)
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
        equipment_tables={tabla: tuple(filas) for tabla, filas in equipment_tables.items()},
        capacitor_settings=capacitor_settings,
        fuente='vnr',
        estructura_fuente=dict(model.metadata.get('estructura_fuente') or {}),
        regulator_settings=regulator_settings,
    )

    projected = model.metadata.get('working_crs_is_projected') is True
    readiness: dict[str, dict[str, Any]] = {}
    for feeder, section_ids in dataset.feeders.items():
        blocking: list[str] = []
        avisos: list[str] = []
        source = sources.get(feeder)
        if source is None:
            blocking.append('MISSING_SOURCE')
        elif not source.get('DesiredVoltage'):
            blocking.append('MISSING_NOMINAL_VOLTAGE')
        if not mapped_loads.get(feeder):
            # Una red sin cargas se convierte igual, como en la vía TXT (alimentadores
            # fuera de servicio o vacíos: SC215, SI114 y TM101 de la copia de Electro
            # Dunas, 2026-10-18); se dice, no bloquea (023:RF-10).
            avisos.append('MISSING_LOADS')
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
            'warning_codes': avisos,
        }
    return BridgeResult(dataset=dataset, readiness=readiness, issues=issues)
