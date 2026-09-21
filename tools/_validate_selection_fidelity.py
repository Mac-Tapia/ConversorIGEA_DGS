"""Validate GUI selection → full TXT fidelity (sections/loads/devices → DGS)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from igea_dgs.batch import convert_selection, load_aliases
from igea_dgs.dataset import CymdistDataset
from igea_dgs.inventory import build_dataset_inventory
from igea_dgs.model import build_feeder_model

ROOT = Path(__file__).resolve().parents[1]
RED = ROOT / 'referencia' / 'RED_030826(1).txt'
CARGA = ROOT / 'referencia' / 'CARGA_030826(1).txt'
EQUIP = ROOT / 'referencia' / 'BD_Equipo_V261124 (1)(1).txt'
ALIASES = ROOT / 'config' / 'line_type_aliases.json'
OUT = ROOT / 'output' / 'validate_selection'


def endpoint_key(sec: dict) -> tuple[str, str]:
    a, b = sec.get('FromNodeID', ''), sec.get('ToNodeID', '')
    return tuple(sorted((a, b)))


def main() -> int:
    print('Cargando TXT...')
    ds = CymdistDataset.from_files(RED, CARGA, EQUIP)
    aliases = load_aliases(ALIASES)
    inv = build_dataset_inventory(ds)
    totals = inv['totals']
    integ = inv['integrity']
    print('Inventario:', totals)
    print(f"Integridad: errors={integ['errors']} warnings={integ['warnings']}")
    for issue in integ.get('issues', [])[:20]:
        print(f"  [{issue.get('level')}] {issue.get('code')}: {issue.get('message')}")

    convertible = [r for r in inv['feeders'] if r['convertible']]
    stubs = [r['feeder'] for r in inv['feeders'] if not r['convertible']]
    print(f'Convertibles={len(convertible)} stubs={len(stubs)}')
    if stubs:
        print('  Stubs (omitidos a proposito, 0 SECTION):', ', '.join(stubs[:12]))

    double_circuit_feeders: list[tuple[str, int, int, int]] = []
    for row in convertible:
        nid = row['network_id']
        ends: Counter[tuple[str, str]] = Counter()
        for sid in ds.feeders[nid]:
            ends[endpoint_key(ds.sections[sid])] += 1
        doubles = sum(1 for c in ends.values() if c >= 2)
        if doubles:
            double_circuit_feeders.append((row['feeder'], doubles, row['sections'], row['loads']))
    print(f'Alimentadores con tramos paralelos (doble circuito): {len(double_circuit_feeders)}')
    for item in double_circuit_feeders[:8]:
        print(' ', item)

    by_name = {r['feeder']: r for r in convertible}
    pick: list[str] = []
    for name in ('AL104', 'AL105', 'AL111', 'AL115', 'AL120'):
        if name in by_name:
            pick.append(name)
    if double_circuit_feeders:
        pick.append(double_circuit_feeders[0][0])
    pick = list(dict.fromkeys(pick))[:6]
    print('Seleccion a validar:', pick)

    print('\n=== Conteos TXT vs modelo ===')
    model_ok = True
    for sel in pick:
        nid = ds.resolve_feeder(sel)
        txt_secs = len(ds.feeders[nid])
        txt_cfg = sum(1 for sid in ds.feeders[nid] if sid in ds.line_configurations)
        txt_loads = sum(1 for (sid, _) in ds.customer_loads if ds.section_owner.get(sid) == nid)
        txt_sw = sum(1 for r in ds.switch_settings if ds.section_owner.get(r.get('SectionID', '')) == nid)
        txt_secz = sum(
            1 for r in ds.sectionalizer_settings if ds.section_owner.get(r.get('SectionID', '')) == nid
        )
        model = build_feeder_model(ds, nid, aliases=aliases, strict=True)
        ends = Counter(tuple(sorted((line.from_node, line.to_node))) for line in model.lines)
        parallel = sum(1 for c in ends.values() if c >= 2)
        match_lines = len(model.lines) == txt_secs == txt_cfg
        match_loads = len(model.loads) == txt_loads
        match_dev = len(model.devices) == (txt_sw + txt_secz)
        match = match_lines and match_loads and match_dev
        model_ok = model_ok and match
        print(
            f'{sel}: TXT sec/cfg/loads/sw+secz={txt_secs}/{txt_cfg}/{txt_loads}/{txt_sw}+{txt_secz} | '
            f'MODEL lines/loads/seds/dev={len(model.lines)}/{len(model.loads)}/{len(model.seds)}/{len(model.devices)} '
            f'parallel_pairs={parallel} MATCH={match}'
        )
        for warn in model.warnings:
            print('   WARN:', warn[:160])
        if model.unresolved_line_types:
            print('   unresolved:', sorted(model.unresolved_line_types)[:12])

    print('\n=== Conversion DGS ===')
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = convert_selection(
        ds,
        pick,
        OUT,
        aliases=aliases,
        strict=True,
        include_geography=True,
        source_crs='EPSG:32718',
    )
    print('Summary:', manifest['summary'])
    dgs_ok = True
    for item in manifest['feeders']:
        counts = item.get('counts') or {}
        keys = (
            'source_lines',
            'dgs_lines',
            'source_loads',
            'dgs_loads',
            'source_seds',
            'dgs_seds',
        )
        subset = {k: counts.get(k) for k in keys}
        line_ok = counts.get('source_lines') == counts.get('dgs_lines')
        load_ok = counts.get('source_loads') == counts.get('dgs_loads')
        status = item['status']
        if status != 'ok' or not line_ok or not load_ok:
            dgs_ok = False
        err = (item.get('error') or '')[:220]
        print(
            f"  {item['feeder']}: {status} errors={item.get('errors_total')} "
            f'counts={subset} line_match={line_ok} load_match={load_ok} {err}'
        )

    (OUT / 'fidelity_check.json').write_text(
        json.dumps(
            {
                'selection': pick,
                'inventory_totals': totals,
                'integrity': {'errors': integ['errors'], 'warnings': integ['warnings']},
                'model_match': model_ok,
                'dgs_match': dgs_ok,
                'summary': manifest['summary'],
            },
            indent=2,
            ensure_ascii=False,
        )
        + '\n',
        encoding='utf-8',
    )

    ok = model_ok and dgs_ok and manifest['summary']['failed'] == 0
    print('\nRESULTADO:', 'FIDELIDAD OK' if ok else 'HAY DESAJUSTES / ERRORES')
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
