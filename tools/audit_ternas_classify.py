"""Classify orphan ABC islands vs real ternary gaps; verify UG type mapping."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from igea_dgs.dataset import CymdistDataset
from igea_dgs.model import build_feeder_model
from igea_dgs.naming import feeder_short_name
from igea_paths import resolve_igea_txt_paths


def main() -> int:
    ds = CymdistDataset.from_files(*resolve_igea_txt_paths())
    orphans: list[dict] = []
    real: list[dict] = []

    for network_id, section_ids in ds.feeders.items():
        short = feeder_short_name(network_id)
        source = ds.sources.get(network_id, {}).get('NodeID', '')
        if not source or not section_ids:
            continue
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

        for sid, meta in info.items():
            if meta['phase'] != 'ABC':
                continue
            if meta['a'] in reach and meta['b'] in reach:
                continue
            connected = meta['a'] in parent or meta['b'] in parent
            if not connected:
                orphans.append({
                    'feeder': short,
                    'section': sid,
                    'overhead': meta['oh'],
                    'cable': meta['cable'],
                    'from': meta['a'],
                    'to': meta['b'],
                })
                continue

            end = meta['b'] if meta['a'] in reach else meta['a']
            if end not in parent:
                end = meta['a'] if meta['a'] in parent else meta['b']
            path: list[str] = []
            cur = end
            while cur != source and cur in parent:
                prev, psid = parent[cur]
                if psid is None:
                    break
                path.append(psid)
                cur = prev
            bottleneck = None
            for psid in reversed(path):
                if info[psid]['phase'] != 'ABC':
                    bottleneck = {
                        'section': psid,
                        'phase': info[psid]['phase'],
                        'overhead': info[psid]['oh'],
                        'cable': info[psid]['cable'],
                    }
                    break
            real.append({
                'feeder': short,
                'unreachable_abc': sid,
                'unreachable_oh': meta['oh'],
                'unreachable_cable': meta['cable'],
                'bottleneck': bottleneck,
            })

    ug_type_wrong: list[dict] = []
    build_ok = 0
    for network_id in ds.feeders:
        short = feeder_short_name(network_id)
        try:
            model = build_feeder_model(ds, network_id)
        except Exception as exc:  # noqa: BLE001
            continue
        build_ok += 1
        for line in model.lines:
            typ = model.line_types[line.type_key]
            if (not line.overhead) and typ.source_table == 'LINE':
                ug_type_wrong.append({
                    'feeder': short,
                    'section': line.section_id,
                    'code': line.source_type_code,
                    'issue': 'UG_mapped_to_LINE_table',
                })
            if line.overhead and typ.source_table == 'CONCENTRIC NEUTRAL CABLE':
                ug_type_wrong.append({
                    'feeder': short,
                    'section': line.section_id,
                    'code': line.source_type_code,
                    'issue': 'OH_mapped_to_CABLE_table',
                })

    out = {
        'orphans_abc': orphans,
        'real_terna_gaps': real,
        'n_orphans': len(orphans),
        'n_real_gaps': len(real),
        'orphans_by_feeder': dict(Counter(o['feeder'] for o in orphans)),
        'real_by_feeder': dict(Counter(r['feeder'] for r in real)),
        'ug_type_wrong': ug_type_wrong,
        'n_ug_type_wrong': len(ug_type_wrong),
        'n_build_ok': build_ok,
    }
    path = ROOT / 'referencia' / 'audit_ternas_classified.json'
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    print('ORPHAN ABC (desconectados de cabecera):', out['n_orphans'], out['orphans_by_feeder'])
    print('REAL gaps terna (ABC detras de 1/2 fase):', out['n_real_gaps'], out['real_by_feeder'])
    for r in real:
        print(' ', r)
    print('UG/OH type mismatches:', out['n_ug_type_wrong'])
    for x in ug_type_wrong[:15]:
        print(' ', x)
    print('build_ok feeders:', build_ok)
    print('Reporte:', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
