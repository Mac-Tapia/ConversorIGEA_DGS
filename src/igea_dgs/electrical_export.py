"""Exportación tabular completa y auditable de una red unida.

Las tablas conservan las filas fuente MDB/TXT y añaden, sin sobrescribirlas, los
valores normalizados que realmente llegan al DGS. El módulo no conoce la interfaz
web ni PowerFactory: recibe dataset, modelos y DGS, y publica CSV deterministas.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .dataset import CymdistDataset
from .model import FeederModel
from .naming import feeder_short_name
from .validate import parse_dgs


TABLE_ORDER = (
    'resumen', 'redes', 'nodos', 'tramos', 'tipos_linea', 'cargas', 'sed',
    'maniobras', 'fuentes', 'auditoria',
)


def _source_fields(prefix: str, row: Mapping[str, Any]) -> dict[str, Any]:
    return {f'{prefix}{key}': value for key, value in row.items()}


def _ordered_fields(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for field in row:
            if field not in seen:
                fields.append(field)
                seen.add(field)
    return fields


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = _ordered_fields(rows)
    if not fields:
        fields = ['Sin_registros']
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, '') for field in fields})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _source_file(path: Path | str) -> dict[str, Any] | None:
    source = Path(path)
    if not source.is_file():
        return None
    return {
        'path': str(source),
        'size': source.stat().st_size,
        'sha256': _sha256(source),
    }


def _dgs_rows(dgs_path: Path) -> dict[str, list[dict[str, str]]]:
    return {
        name: list(table['rows_dict'])
        for name, table in parse_dgs(dgs_path).items()
    }


def build_electrical_tables(
    dataset: CymdistDataset,
    networks: Sequence[str],
    models: Sequence[FeederModel],
    dgs_path: Path | str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Construye tablas fuente + normalizadas para los alimentadores seleccionados."""

    model_by_network = {model.network_id: model for model in models}
    dgs = _dgs_rows(Path(dgs_path))

    redes: list[dict[str, Any]] = []
    fuentes: list[dict[str, Any]] = []
    nodos: list[dict[str, Any]] = []
    tramos: list[dict[str, Any]] = []
    tipos: list[dict[str, Any]] = []
    cargas: list[dict[str, Any]] = []
    seds: list[dict[str, Any]] = []
    maniobras: list[dict[str, Any]] = []

    substation_by_name = {
        row.get('loc_name', ''): row for row in dgs.get('ElmSubstat', ())
    }
    transformer_by_folder = {
        row.get('fold_id', ''): row for row in dgs.get('ElmTr2', ())
    }
    transformer_type_by_fid = {
        row.get('FID', ''): row for row in dgs.get('TypTr2', ())
    }

    for network_id in networks:
        model = model_by_network[network_id]
        feeder = model.name or feeder_short_name(network_id)
        source = dataset.sources.get(network_id, {})
        redes.append({
            'Alimentador': feeder,
            'NetworkID': network_id,
            'Tension_Nominal_kV': model.nominal_kv,
            'Nodo_Fuente': model.source_node,
            'Tramos_Fuente': len(dataset.feeders.get(network_id, ())),
            'Cargas_Fuente': len(dataset.customer_loads_by_feeder.get(network_id, ())),
            'SED_Modeladas': len(model.seds),
            **_source_fields('Fuente_SOURCE_', source),
        })
        fuentes.append({
            'Name': f'External Grid {feeder}',
            'Alimentador': feeder,
            'NetworkID': network_id,
            'Nodo': model.source_node,
            'Tension_Nominal_kV': model.nominal_kv,
            **_source_fields('Fuente_', source),
        })

        referenced_nodes: set[str] = {model.source_node}
        for section_id in dataset.feeders.get(network_id, ()):
            section = dataset.sections.get(section_id, {})
            referenced_nodes.update(filter(None, (
                section.get('FromNodeID', ''), section.get('ToNodeID', ''),
            )))
        for node_id in sorted(referenced_nodes):
            raw = dataset.nodes.get(node_id, {})
            normalized = model.nodes.get(node_id)
            nodos.append({
                'Alimentador': feeder,
                'NetworkID': network_id,
                'NodeID': node_id,
                'CoordX_Modelo': normalized.x if normalized is not None else '',
                'CoordY_Modelo': normalized.y if normalized is not None else '',
                'Coordenada_Inferida': (
                    normalized.coord_inferida if normalized is not None else ''
                ),
                'Estado_Modelo': 'incluido' if normalized is not None else 'fusionado',
                **_source_fields('Fuente_', raw),
            })

        line_by_id = {line.section_id: line for line in model.lines}
        for section_id in dataset.feeders.get(network_id, ()):
            raw_section = dataset.sections.get(section_id, {})
            raw_config = dataset.line_configurations.get(section_id, {})
            line = line_by_id.get(section_id)
            line_type = model.line_types.get(line.type_key) if line is not None else None
            tramos.append({
                'Alimentador': feeder,
                'NetworkID': network_id,
                'SectionID': section_id,
                'FromNodeID': raw_section.get('FromNodeID', ''),
                'ToNodeID': raw_section.get('ToNodeID', ''),
                'Fases': line.phase if line is not None else raw_section.get('Phase', ''),
                'Estado_Modelo': 'incluido' if line is not None else 'fusionado_o_excluido',
                'Longitud_Fuente_m': raw_config.get('Length', ''),
                'Longitud_Modelo_m': line.length_m if line is not None else '',
                'Fuente_Longitud': line.length_source if line is not None else '',
                'Medio': ('aereo' if line.overhead else 'subterraneo') if line is not None else '',
                'Codigo_Tipo': line.source_type_code if line is not None else raw_config.get('LineCableID', ''),
                'R1_ohm_km': line_type.r1_ohm_km if line_type is not None else '',
                'X1_ohm_km': line_type.x1_ohm_km if line_type is not None else '',
                'R0_ohm_km': line_type.r0_ohm_km if line_type is not None else '',
                'X0_ohm_km': line_type.x0_ohm_km if line_type is not None else '',
                'B1_fuente': line_type.b1_source if line_type is not None else '',
                'B0_fuente': line_type.b0_source if line_type is not None else '',
                'Ampacidad_A': line_type.ampacity_a if line_type is not None else '',
                **_source_fields('Fuente_SECTION_', raw_section),
                **_source_fields('Fuente_CONFIG_', raw_config),
            })

        for key, line_type in sorted(model.line_types.items()):
            tipos.append({
                'Alimentador': feeder,
                'NetworkID': network_id,
                'Clave_Tipo': key,
                'Codigo': line_type.code,
                'Tabla_Fuente': line_type.source_table,
                'R1_ohm_km': line_type.r1_ohm_km,
                'X1_ohm_km': line_type.x1_ohm_km,
                'R0_ohm_km': line_type.r0_ohm_km,
                'X0_ohm_km': line_type.x0_ohm_km,
                'B1_fuente': line_type.b1_source,
                'B0_fuente': line_type.b0_source,
                'Ampacidad_A': line_type.ampacity_a,
            })

        load_by_key = {
            (load.section_id, load.device_number): load for load in model.loads
        }
        for key, raw_load in dataset.customer_loads_by_feeder.get(network_id, ()):
            placement = dataset.load_placements.get(key, {})
            load = load_by_key.get(key)
            cargas.append({
                'Name': (load.display_name or load.device_number) if load is not None else raw_load.get('DeviceNumber', ''),
                'Alimentador': feeder,
                'NetworkID': network_id,
                'SectionID': key[0],
                'DeviceNumber': key[1],
                'SED': load.sed_code if load is not None else '',
                'Nodo': load.node_id if load is not None else '',
                'Fases': load.phase if load is not None else raw_load.get('Phase', ''),
                'P_MW': load.p_mw if load is not None else '',
                'Q_Mvar': load.q_mvar if load is not None else '',
                'Potencia_Conectada_kVA': load.connected_kva if load is not None else raw_load.get('ConnectedKVA', ''),
                'Factor_Potencia': load.pf if load is not None else '',
                'Energia_kWh': load.kwh if load is not None else raw_load.get('KWH', ''),
                'Clientes': load.customers if load is not None else raw_load.get('NumberOfCustomer', ''),
                'Estado_Modelo': 'incluida' if load is not None else 'excluida_por_regla',
                **_source_fields('Fuente_LOADS_', placement),
                **_source_fields('Fuente_CUSTOMER_', raw_load),
            })

        for sed in sorted(model.seds, key=lambda item: (item.loc_name, item.section_id)):
            raw_customer = dataset.customer_loads.get(sed.load_key, {})
            raw_placement = dataset.load_placements.get(sed.load_key, {})
            substation = substation_by_name.get(sed.loc_name, {})
            transformer = transformer_by_folder.get(substation.get('FID', ''), {})
            transformer_type = transformer_type_by_fid.get(transformer.get('typ_id', ''), {})
            seds.append({
                'Name': sed.loc_name,
                'Alimentador': feeder,
                'NetworkID': network_id,
                'SectionID': sed.section_id,
                'DeviceNumber': sed.device_number,
                'Nodo_MT': sed.node_id,
                'Potencia_kVA': sed.design_kva,
                'Tension_MT_kV': transformer_type.get('utrn_h', ''),
                'Tension_BT_kV': transformer_type.get('utrn_l', ''),
                'Uk_pct': transformer_type.get('uktr', ''),
                'Perdidas_Cobre_kW': transformer_type.get('pcutr', ''),
                'Perdidas_Hierro_kW': transformer_type.get('pfe', ''),
                'Corriente_Vacio_pct': transformer_type.get('curmg', ''),
                'Conexion_MT': transformer_type.get('tr2cn_h', ''),
                'Conexion_BT': transformer_type.get('tr2cn_l', ''),
                'Grupo_Vectorial': transformer_type.get('nt2ag', ''),
                'Tap_Paso_pct': transformer_type.get('dutap', ''),
                'Tap_Minimo': transformer_type.get('ntpmn', ''),
                'Tap_Maximo': transformer_type.get('ntpmx', ''),
                'Tipo_Transformador': transformer_type.get('loc_name', ''),
                'FID_Substation': substation.get('FID', ''),
                'FID_Transformer': transformer.get('FID', ''),
                'FID_Tipo': transformer_type.get('FID', ''),
                **_source_fields('Fuente_LOADS_', raw_placement),
                **_source_fields('Fuente_CUSTOMER_', raw_customer),
            })

        final_devices: dict[tuple[str, str], Any] = {
            (device.section_id, device.eq_number): device for device in model.devices
        }
        for kind, row in dataset.switching_by_feeder.get(network_id, ()):
            key = (row.get('SectionID', ''), row.get('EquipmentNumber', ''))
            device = final_devices.get(key)
            maniobras.append({
                'Name': (device.eq_number or device.eq_id) if device is not None else row.get('EquipmentNumber', ''),
                'Alimentador': feeder,
                'NetworkID': network_id,
                'Clase_Fuente': kind,
                'SectionID': row.get('SectionID', ''),
                'Nodo': device.node_id if device is not None else '',
                'Lado_Terminal': device.terminal_side if device is not None else '',
                'Fases': device.phase if device is not None else row.get('Phase', ''),
                'En_Servicio': device.on_off if device is not None else row.get('ClosedPhase', ''),
                'Bloqueado': device.locked if device is not None else row.get('Locked', ''),
                'Estado_Modelo': 'StaSwitch' if device is not None else 'convertida_a_acoplador_o_excluida',
                **_source_fields('Fuente_', row),
            })

    source_sections = sum(len(dataset.feeders.get(network, ())) for network in networks)
    source_loads = sum(len(dataset.customer_loads_by_feeder.get(network, ())) for network in networks)
    source_switches = sum(len(dataset.switching_by_feeder.get(network, ())) for network in networks)
    modeled_seds = sum(len(model.seds) for model in models)
    checks = {
        'tramos': (source_sections, len(tramos)),
        'cargas': (source_loads, len(cargas)),
        'maniobras': (source_switches, len(maniobras)),
        'sed_modeladas': (modeled_seds, len(seds)),
        'fuentes': (len(networks), len(fuentes)),
    }
    auditoria = [
        {
            'Metrica': metric,
            'Esperado': expected,
            'Exportado': exported,
            'Diferencia': exported - expected,
            'Estado': 'OK' if expected == exported else 'ERROR',
        }
        for metric, (expected, exported) in checks.items()
    ]
    resumen = [
        {'Metrica': 'Grid', 'Valor': Path(dgs_path).stem},
        {'Metrica': 'Alimentadores', 'Valor': ','.join(model.name for model in models)},
        {'Metrica': 'Cantidad_alimentadores', 'Valor': len(models)},
        {'Metrica': 'Tramos_fuente', 'Valor': source_sections},
        {'Metrica': 'Cargas_fuente', 'Valor': source_loads},
        {'Metrica': 'SED_modeladas', 'Valor': modeled_seds},
        {'Metrica': 'Maniobras_fuente', 'Valor': source_switches},
    ]
    tables = {
        'resumen': resumen,
        'redes': redes,
        'nodos': nodos,
        'tramos': tramos,
        'tipos_linea': tipos,
        'cargas': cargas,
        'sed': seds,
        'maniobras': maniobras,
        'fuentes': fuentes,
        'auditoria': auditoria,
    }
    report = {
        'feeders': [model.name for model in models],
        'network_ids': list(networks),
        'checks': {
            'ok': all(item['Estado'] == 'OK' for item in auditoria),
            'items': auditoria,
        },
        'source_files': {
            'red': _source_file(dataset.red_path),
            'loads': _source_file(dataset.loads_path),
            'equipment': _source_file(dataset.equipment_path),
        },
    }
    return tables, report


def write_electrical_export(
    dataset: CymdistDataset,
    networks: Sequence[str],
    models: Sequence[FeederModel],
    dgs_path: Path | str,
    output_dir: Path | str,
    manifest_path: Path | str,
) -> tuple[Path, Path]:
    """Escribe el paquete CSV y un manifiesto con hashes y conciliaciones."""

    tables, report = build_electrical_tables(dataset, networks, models, dgs_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    for name in TABLE_ORDER:
        path = output / f'{name}.csv'
        _write_csv(path, tables[name])
        files[path.name] = {
            'rows': len(tables[name]),
            'sha256': _sha256(path),
        }
    report['files'] = files
    destination = Path(manifest_path)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
    )
    return output, destination
