"""Detail ABC sections that sit behind a non-ABC bottleneck from the source."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from igea_dgs.dataset import CymdistDataset
from igea_dgs.naming import feeder_short_name
from igea_paths import resolve_igea_txt_paths


def analyze_feeder(ds: CymdistDataset, network_id: str) -> dict:
    short = feeder_short_name(network_id)
    source = ds.sources.get(network_id, {}).get('NodeID', '')
    section_ids = ds.feeders[network_id]
    if not source or not section_ids:
        return {'feeder': short, 'issues': [], 'skip': True}

    adj: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    info: dict[str, dict] = {}
    for sid in section_ids:
        s = ds.sections[sid]
        cfg = ds.line_configurations[sid]
        ph = s.get('Phase') or ''
        info[sid] = {
            'phase': ph,
            'oh': cfg.get('Overhead', '1'),
            'a': s['FromNodeID'],
            'b': s['ToNodeID'],
            'cable': cfg.get('LineCableID', ''),
        }
        adj[s['FromNodeID']].append((s['ToNodeID'], sid, ph))
        adj[s['ToNodeID']].append((s['FromNodeID'], sid, ph))

    parent: dict[str, tuple[str | None, str | None]] = {source: (None, None)}
    q: deque[str] = deque([source])
    while q:
        u = q.popleft()
        for v, sid, _ in adj[u]:
            if v not in parent:
                parent[v] = (u, sid)
                q.append(v)

    reach = {source}
    q = deque([source])
    while q:
        u = q.popleft()
        for v, sid, ph in adj[u]:
            if ph == 'ABC' and v not in reach:
                reach.add(v)
                q.append(v)

    issues = []
    for sid, meta in info.items():
        if meta['phase'] != 'ABC':
            continue
        if meta['a'] in reach and meta['b'] in reach:
            continue
        end = meta['b'] if meta['a'] in reach else meta['a']
        if end not in parent:
            end = meta['a'] if meta['a'] in parent else meta['b']
        path = []
        cur = end
        while cur != source and cur in parent:
            prev, psid = parent[cur]
            if psid is None:
                break
            path.append({
                'section': psid,
                'phase': info[psid]['phase'],
                'overhead': info[psid]['oh'],
                'cable': info[psid]['cable'],
            })
            cur = prev
        path.reverse()
        bottleneck = next((p for p in path if p['phase'] != 'ABC'), None)
        issues.append({
            'unreachable_abc_section': sid,
            'unreachable_oh': meta['oh'],
            'unreachable_cable': meta['cable'],
            'bottleneck': bottleneck,
            'path_phases': [p['phase'] for p in path],
            'path_overhead': [p['overhead'] for p in path],
        })

    ug_total = sum(1 for m in info.values() if m['oh'] == '0')
    abc_total = sum(1 for m in info.values() if m['phase'] == 'ABC')
    return {
        'feeder': short,
        'n_sections': len(section_ids),
        'n_abc': abc_total,
        'n_ug': ug_total,
        'n_abc_behind_non_abc': len(issues),
        'issues': issues,
        'skip': False,
    }


def main() -> int:
    paths = resolve_igea_txt_paths()
    assert paths
    ds = CymdistDataset.from_files(*paths)
    reports = []
    for network_id in sorted(ds.feeders, key=lambda x: feeder_short_name(x)):
        reports.append(analyze_feeder(ds, network_id))

    with_issues = [r for r in reports if r['issues']]
    out = {
        'red': str(paths[0]),
        'n_feeders': len(reports),
        'n_feeders_with_abc_behind_non_abc': len(with_issues),
        'feeders': with_issues,
        'ok_feeders': [r['feeder'] for r in reports if not r.get('skip') and not r['issues']],
        'skipped': [r['feeder'] for r in reports if r.get('skip')],
    }
    out_path = ROOT / 'referencia' / 'audit_ternas_backbone.json'
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'Alimentadores: {out["n_feeders"]}')
    print(f'Con tramos ABC detras de cuello 1/2 fase: {out["n_feeders_with_abc_behind_non_abc"]}')
    print(f'OK: {len(out["ok_feeders"])}  SKIP: {len(out["skipped"])}')
    for r in sorted(with_issues, key=lambda x: -x['n_abc_behind_non_abc']):
        print(
            f"  {r['feeder']}: abc_behind_gap={r['n_abc_behind_non_abc']} "
            f"abc={r['n_abc']} ug={r['n_ug']}"
        )
        for iss in r['issues'][:4]:
            bn = iss['bottleneck']
            print(
                f"    ABC {iss['unreachable_abc_section']} oh={iss['unreachable_oh']} "
                f"| bottleneck={bn}"
            )
    print(f'Reporte: {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
