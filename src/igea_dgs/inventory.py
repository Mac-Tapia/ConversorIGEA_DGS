"""Deep inventory of a loaded IGEA/CYMDIST TXT dataset (production diagnostics)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .dataset import CymdistDataset
from .naming import feeder_short_name, sort_key_feeder


def build_dataset_inventory(dataset: CymdistDataset) -> dict[str, Any]:
    """Analyze RED/CARGA/BD_Equipo contents in depth for conversion planning.

    Returns a JSON-serializable report: totals, per-feeder stats, integrity issues,
    and how many independent DGS files this batch can produce.
    """
    load_by_owner: Counter[str] = Counter()
    loads_orphan = 0
    for section_id, _device in dataset.customer_loads:
        owner = dataset.section_owner.get(section_id)
        if owner:
            load_by_owner[owner] += 1
        else:
            loads_orphan += 1

    placement_orphan = 0
    for key in dataset.load_placements:
        section_id = key[0]
        if section_id not in dataset.sections:
            placement_orphan += 1

    switch_by_owner: Counter[str] = Counter()
    for row in dataset.switch_settings:
        owner = dataset.section_owner.get(row.get('SectionID', ''))
        if owner:
            switch_by_owner[owner] += 1

    sectionalizer_by_owner: Counter[str] = Counter()
    for row in dataset.sectionalizer_settings:
        owner = dataset.section_owner.get(row.get('SectionID', ''))
        if owner:
            sectionalizer_by_owner[owner] += 1

    intermediate_by_owner: Counter[str] = Counter()
    for row in dataset.intermediate_nodes:
        owner = dataset.section_owner.get(row.get('SectionID', ''))
        if owner:
            intermediate_by_owner[owner] += 1

    sections_missing_cfg: list[str] = []
    cfg_missing_section: list[str] = []
    sections_missing_nodes: list[str] = []
    for section_id, sec in dataset.sections.items():
        if section_id not in dataset.line_configurations:
            sections_missing_cfg.append(section_id)
        from_node = sec.get('FromNodeID', '')
        to_node = sec.get('ToNodeID', '')
        if from_node not in dataset.nodes or to_node not in dataset.nodes:
            sections_missing_nodes.append(section_id)
    for section_id in dataset.line_configurations:
        if section_id not in dataset.sections:
            cfg_missing_section.append(section_id)

    feeders_without_source: list[str] = []
    sources_without_feeder: list[str] = []
    for network_id in dataset.feeders:
        if network_id not in dataset.sources:
            feeders_without_source.append(network_id)
    for network_id in dataset.sources:
        if network_id not in dataset.feeders:
            sources_without_feeder.append(network_id)

    line_codes: Counter[str] = Counter()
    for cfg in dataset.line_configurations.values():
        code = (cfg.get('LineCableID') or 'DEFAULT').strip() or 'DEFAULT'
        line_codes[code] += 1

    equipment_counts = {
        name: len(rows) for name, rows in sorted(dataset.equipment_tables.items())
    }
    catalog_ids: set[str] = set()
    for table_name, rows in dataset.equipment_tables.items():
        if table_name not in {'LINE', 'CONCENTRIC NEUTRAL CABLE'}:
            continue
        for row in rows:
            code = (row.get('ID') or '').strip()
            if code:
                catalog_ids.add(code)
    missing_in_catalog = sorted(
        code for code in line_codes if code not in catalog_ids and code != 'DEFAULT'
    )

    feeder_rows: list[dict[str, Any]] = []
    convertible: list[str] = []
    stubs: list[str] = []
    for network_id in sorted(dataset.feeder_ids(), key=sort_key_feeder):
        sections = dataset.feeders.get(network_id, ())
        source = dataset.sources.get(network_id, {})
        n_sec = len(sections)
        n_loads = int(load_by_owner.get(network_id, 0))
        n_sw = int(switch_by_owner.get(network_id, 0))
        n_secz = int(sectionalizer_by_owner.get(network_id, 0))
        n_inter = int(intermediate_by_owner.get(network_id, 0))
        short = feeder_short_name(network_id)
        convertible_flag = n_sec > 0
        if convertible_flag:
            convertible.append(short)
        else:
            stubs.append(short)
        feeder_rows.append({
            'feeder': short,
            'network_id': network_id,
            'nominal_kv': source.get('DesiredVoltage', ''),
            'source_node': source.get('NodeID', ''),
            'sections': n_sec,
            'loads': n_loads,
            'switches': n_sw,
            'sectionalizers': n_secz,
            'intermediate_points': n_inter,
            'convertible': convertible_flag,
        })

    issues: list[dict[str, Any]] = []
    if stubs:
        issues.append({
            'severity': 'warning',
            'code': 'empty_section_blocks',
            'message': (
                f'{len(stubs)} alimentador(es) con FEEDER=/SOURCE pero 0 filas SECTION: '
                + ', '.join(stubs)
            ),
            'feeders': stubs,
        })
    if sections_missing_cfg:
        issues.append({
            'severity': 'error',
            'code': 'section_without_line_configuration',
            'message': f'{len(sections_missing_cfg)} SECTION sin LINE CONFIGURATION',
            'count': len(sections_missing_cfg),
            'samples': sections_missing_cfg[:20],
        })
    if cfg_missing_section:
        issues.append({
            'severity': 'error',
            'code': 'line_configuration_without_section',
            'message': f'{len(cfg_missing_section)} LINE CONFIGURATION sin SECTION',
            'count': len(cfg_missing_section),
            'samples': cfg_missing_section[:20],
        })
    if sections_missing_nodes:
        issues.append({
            'severity': 'error',
            'code': 'section_missing_nodes',
            'message': f'{len(sections_missing_nodes)} SECTION con nodos ausentes en NODE',
            'count': len(sections_missing_nodes),
            'samples': sections_missing_nodes[:20],
        })
    if loads_orphan:
        issues.append({
            'severity': 'warning',
            'code': 'loads_on_unknown_section',
            'message': f'{loads_orphan} CUSTOMER LOADS en SectionID no presente en RED',
            'count': loads_orphan,
        })
    if placement_orphan:
        issues.append({
            'severity': 'warning',
            'code': 'load_placement_unknown_section',
            'message': f'{placement_orphan} LOADS placement en SectionID ausente',
            'count': placement_orphan,
        })
    if feeders_without_source:
        issues.append({
            'severity': 'error',
            'code': 'feeder_without_source',
            'message': f'{len(feeders_without_source)} FEEDER sin SOURCE',
            'feeders': [feeder_short_name(n) for n in feeders_without_source],
        })
    if sources_without_feeder:
        issues.append({
            'severity': 'warning',
            'code': 'source_without_feeder_block',
            'message': f'{len(sources_without_feeder)} SOURCE sin bloque FEEDER=',
            'feeders': [feeder_short_name(n) for n in sources_without_feeder],
        })
    if missing_in_catalog:
        issues.append({
            'severity': 'warning',
            'code': 'line_types_missing_from_bd_equipo',
            'message': (
                f'{len(missing_in_catalog)} LineCableID usados en RED no están en BD_Equipo '
                '(se resolverán por alias / vecino de catálogo / DEFAULT)'
            ),
            'codes': missing_in_catalog[:50],
            'count': len(missing_in_catalog),
        })

    error_issues = sum(1 for i in issues if i['severity'] == 'error')
    warning_issues = sum(1 for i in issues if i['severity'] == 'warning')

    return {
        'format': 'igea-dgs-dataset-inventory-v1',
        'inputs': {
            'red': str(dataset.red_path),
            'loads': str(dataset.loads_path),
            'equipment': str(dataset.equipment_path),
            'red_name': Path(dataset.red_path).name,
            'loads_name': Path(dataset.loads_path).name,
            'equipment_name': Path(dataset.equipment_path).name,
        },
        'totals': {
            'feeders': len(dataset.feeders),
            'convertible_feeders': len(convertible),
            'stub_feeders': len(stubs),
            'sources': len(dataset.sources),
            'headnodes': len(dataset.headnodes),
            'nodes': len(dataset.nodes),
            'sections': len(dataset.sections),
            'line_configurations': len(dataset.line_configurations),
            'customer_loads': len(dataset.customer_loads),
            'load_placements': len(dataset.load_placements),
            'switches': len(dataset.switch_settings),
            'sectionalizers': len(dataset.sectionalizer_settings),
            'intermediate_nodes': len(dataset.intermediate_nodes),
            'distinct_line_cable_ids': len(line_codes),
            'equipment_tables': len(dataset.equipment_tables),
            'catalog_line_cable_ids': len(catalog_ids),
        },
        'conversion': {
            'expected_dgs_files': len(convertible),
            'skipped_stub_feeders': stubs,
            'convertible_feeders': convertible,
            'model': (
                'Un DGS independiente por alimentador convertible '
                '(tramos + cargas + SED + maniobras + geografía opcional).'
            ),
        },
        'equipment_tables': equipment_counts,
        'top_line_cable_ids': [
            {'code': code, 'sections': count}
            for code, count in line_codes.most_common(25)
        ],
        'feeders': feeder_rows,
        'integrity': {
            'errors': error_issues,
            'warnings': warning_issues,
            'issues': issues,
        },
    }


def format_inventory_report(inventory: dict[str, Any]) -> str:
    """Human-readable inventory for GUI Registro / CLI stdout."""
    t = inventory['totals']
    c = inventory['conversion']
    inputs = inventory['inputs']
    lines = [
        '=== INVENTARIO TXT IGEA/CYMDIST ===',
        f"RED:       {inputs['red_name']}",
        f"CARGA:     {inputs['loads_name']}",
        f"BD_Equipo: {inputs['equipment_name']}",
        '',
        '--- Totales leídos ---',
        f"Alimentadores (FEEDER=):     {t['feeders']}",
        f"  Convertibles (con tramos): {t['convertible_feeders']}",
        f"  Stub (0 SECTION):          {t['stub_feeders']}",
        f"SOURCE:                      {t['sources']}",
        f"Nodos:                       {t['nodes']}",
        f"Tramos (SECTION):            {t['sections']}",
        f"LINE CONFIGURATION:          {t['line_configurations']}",
        f"Cargas (CUSTOMER LOADS):     {t['customer_loads']}",
        f"LOADS (placement):           {t['load_placements']}",
        f"Interruptores (SWITCH):      {t['switches']}",
        f"Seccionalizadores:           {t['sectionalizers']}",
        f"Nodos intermedios:           {t['intermediate_nodes']}",
        f"LineCableID distintos:       {t['distinct_line_cable_ids']}",
        f"IDs en catálogo BD_Equipo:   {t['catalog_line_cable_ids']}",
        '',
        '--- Conversión esperada ---',
        f"Archivos .dgs a generar:     {c['expected_dgs_files']}",
        c['model'],
    ]
    if c['skipped_stub_feeders']:
        lines.append(
            'Omitidos (sin topología en RED): '
            + ', '.join(c['skipped_stub_feeders'])
        )
    lines.append('')
    lines.append('--- Integridad ---')
    integ = inventory['integrity']
    lines.append(f"Errores: {integ['errors']}   Avisos: {integ['warnings']}")
    for issue in integ['issues']:
        prefix = issue['severity'].upper()
        lines.append(f"  [{prefix}] {issue['message']}")
        if issue.get('codes'):
            lines.append('    Códigos: ' + ', '.join(issue['codes'][:20]))
        if issue.get('samples'):
            lines.append('    Muestras: ' + ', '.join(issue['samples'][:10]))

    lines.append('')
    lines.append('--- Alimentadores (resumen) ---')
    lines.append(
        f"{'Nombre':<10} {'kV':>6} {'Tramos':>7} {'Cargas':>7} {'SW':>5} {'Estado':<12}"
    )
    for row in inventory['feeders']:
        status = 'convertible' if row['convertible'] else 'STUB'
        lines.append(
            f"{row['feeder']:<10} {str(row['nominal_kv']):>6} {row['sections']:>7} "
            f"{row['loads']:>7} {row['switches']:>5} {status:<12}"
        )
    lines.append('=== FIN INVENTARIO ===')
    return '\n'.join(lines)


def write_inventory(inventory: dict[str, Any], path: Path | str) -> Path:
    import json

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return out
