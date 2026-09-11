"""Audit ternas on trunk paths to enlace points, and underground sections."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from igea_dgs.dataset import CymdistDataset  # noqa: E402
from igea_dgs.naming import feeder_short_name  # noqa: E402
from igea_paths import resolve_igea_txt_paths  # noqa: E402


def main() -> int:
    paths = resolve_igea_txt_paths()
    if not paths:
        print('TXT IGEA no encontrados')
        return 2
    ds = CymdistDataset.from_files(*paths)

    devices_by_sec: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)
    for row in ds.switch_settings:
        devices_by_sec[row.get('SectionID', '')].append(('SWITCH', row))
    for row in ds.sectionalizer_settings:
        devices_by_sec[row.get('SectionID', '')].append(('SECTIONALIZER', row))

    node_feeders: dict[str, set[str]] = defaultdict(set)
    for network_id, secs in ds.feeders.items():
        for sid in secs:
            sec = ds.sections[sid]
            for n in (sec['FromNodeID'], sec['ToNodeID']):
                node_feeders[n].add(network_id)
    shared_nodes = {n: feds for n, feds in node_feeders.items() if len(feds) > 1}

    results: list[dict] = []
    issues_terna: list[dict] = []

    for network_id, section_ids in sorted(ds.feeders.items(), key=lambda x: feeder_short_name(x[0])):
        short = feeder_short_name(network_id)
        source = ds.sources.get(network_id, {})
        source_node = source.get('NodeID', '')
        if not source_node or not section_ids:
            results.append({'feeder': short, 'status': 'SKIP', 'reason': 'no source/sections'})
            continue

        adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
        sec_info: dict[str, dict] = {}
        for sid in section_ids:
            sec = ds.sections[sid]
            cfg = ds.line_configurations[sid]
            a, b = sec['FromNodeID'], sec['ToNodeID']
            info = {
                'phase': sec.get('Phase') or '',
                'overhead': cfg.get('Overhead', '1'),
                'from': a,
                'to': b,
                'sid': sid,
                'cable': cfg.get('LineCableID', ''),
            }
            sec_info[sid] = info
            adj[a].append((b, sid))
            adj[b].append((a, sid))

        enlace_nodes: set[str] = set()
        open_devs: list[dict] = []
        for sid in section_ids:
            for kind, row in devices_by_sec.get(sid, []):
                if row.get('Status', '1') == '0':
                    info = sec_info[sid]
                    enlace_nodes.add(info['from'])
                    enlace_nodes.add(info['to'])
                    open_devs.append({
                        'kind': kind,
                        'section': sid,
                        'device': row.get('DeviceNumber', ''),
                        'phase_sec': info['phase'],
                        'overhead': info['overhead'],
                    })
        for n, feds in shared_nodes.items():
            if network_id in feds:
                enlace_nodes.add(n)

        parent: dict[str, tuple[str | None, str | None]] = {source_node: (None, None)}
        q = deque([source_node])
        while q:
            u = q.popleft()
            for v, sid in adj[u]:
                if v not in parent:
                    parent[v] = (u, sid)
                    q.append(v)

        troncal_sections: set[str] = set()
        enlace_reachable: list[str] = []
        for en in enlace_nodes:
            if en not in parent or en == source_node:
                continue
            enlace_reachable.append(en)
            cur = en
            while cur != source_node:
                prev, sid = parent[cur]
                if sid is None:
                    break
                troncal_sections.add(sid)
                cur = prev

        # Fallback trunk: BFS-tree path from source to every ABC leaf tip
        # (degree-1 node reached only via ABC tree edges). Captures feeders
        # without open/shared enlaces.
        if not troncal_sections:
            for node, neighbors in adj.items():
                if node == source_node or node not in parent:
                    continue
                if len(neighbors) != 1:
                    continue
                # walk to source; include only while phases are continuous
                path_secs: list[str] = []
                cur = node
                ok = True
                while cur != source_node:
                    prev, sid = parent[cur]
                    if sid is None:
                        ok = False
                        break
                    path_secs.append(sid)
                    cur = prev
                if not ok:
                    continue
                # trunk candidate if the leaf tip section is ABC (main spine tip)
                if path_secs and sec_info[path_secs[0]]['phase'] == 'ABC':
                    troncal_sections.update(path_secs)

        non_abc_on_troncal = [
            {
                'section': sid,
                'phase': sec_info[sid]['phase'],
                'overhead': sec_info[sid]['overhead'],
                'cable': sec_info[sid]['cable'],
            }
            for sid in sorted(troncal_sections)
            if sec_info[sid]['phase'] != 'ABC'
        ]
        open_non_abc = [d for d in open_devs if d['phase_sec'] != 'ABC']

        ug = [sid for sid, i in sec_info.items() if i['overhead'] == '0']
        oh = [sid for sid, i in sec_info.items() if i['overhead'] == '1']
        ug_phase = Counter(sec_info[s]['phase'] for s in ug)

        # Continuity of Overhead along troncal: transitions are OK, just inventory
        ug_on_troncal = [sid for sid in troncal_sections if sec_info[sid]['overhead'] == '0']

        feeder_issue = {
            'feeder': short,
            'network_id': network_id,
            'n_sections': len(section_ids),
            'n_ug': len(ug),
            'n_oh': len(oh),
            'n_open_devs': len(open_devs),
            'n_enlace_nodes': len(enlace_reachable),
            'n_troncal_secs': len(troncal_sections),
            'n_ug_on_troncal': len(ug_on_troncal),
            'non_abc_on_troncal': non_abc_on_troncal,
            'open_non_abc': open_non_abc,
            'ug_phase': dict(ug_phase),
            'all_phase': dict(Counter(i['phase'] for i in sec_info.values())),
            'ug_on_troncal_sample': ug_on_troncal[:10],
        }
        results.append(feeder_issue)
        if non_abc_on_troncal or open_non_abc:
            issues_terna.append(feeder_issue)

    # Global UG integrity: every Overhead=0 must stay Overhead=0 in model build
    from igea_dgs.model import build_feeder_model

    ug_mismatch: list[dict] = []
    build_fail: list[dict] = []
    for network_id in ds.feeders:
        short = feeder_short_name(network_id)
        try:
            model = build_feeder_model(ds, network_id)
        except Exception as exc:  # noqa: BLE001 — audit all feeders
            build_fail.append({'feeder': short, 'error': str(exc)})
            continue
        txt_ug = {
            sid
            for sid in ds.feeders[network_id]
            if ds.line_configurations[sid].get('Overhead', '1') == '0'
        }
        model_ug = {line.section_id for line in model.lines if not line.overhead}
        model_oh = {line.section_id for line in model.lines if line.overhead}
        missing = sorted(txt_ug - model_ug)
        false_ug = sorted(model_ug - txt_ug)
        if missing or false_ug:
            ug_mismatch.append({
                'feeder': short,
                'missing_ug': missing[:20],
                'false_ug': false_ug[:20],
                'n_missing': len(missing),
                'n_false': len(false_ug),
            })

    out = {
        'red': str(paths[0]),
        'n_feeders': len(results),
        'shared_nodes': len(shared_nodes),
        'n_with_terna_issues': len(issues_terna),
        'n_ug_mismatch': len(ug_mismatch),
        'n_build_fail': len(build_fail),
        'terna_issues': [
            {
                'feeder': r['feeder'],
                'n_non_abc_on_troncal': len(r['non_abc_on_troncal']),
                'n_open_non_abc': len(r['open_non_abc']),
                'non_abc_sample': r['non_abc_on_troncal'][:8],
                'open_non_abc': r['open_non_abc'][:8],
                'all_phase': r['all_phase'],
                'n_ug': r['n_ug'],
                'n_open_devs': r['n_open_devs'],
                'n_troncal_secs': r['n_troncal_secs'],
            }
            for r in sorted(issues_terna, key=lambda x: -len(x['non_abc_on_troncal']))
        ],
        'ug_mismatch': ug_mismatch,
        'build_fail': build_fail,
        'per_feeder_summary': [
            {
                'feeder': r.get('feeder'),
                'n_sections': r.get('n_sections'),
                'n_ug': r.get('n_ug'),
                'n_oh': r.get('n_oh'),
                'n_open_devs': r.get('n_open_devs'),
                'n_troncal_secs': r.get('n_troncal_secs'),
                'n_ug_on_troncal': r.get('n_ug_on_troncal'),
                'n_non_abc_troncal': len(r.get('non_abc_on_troncal') or []),
                'all_phase': r.get('all_phase'),
                'status': r.get('status', 'OK' if not (r.get('non_abc_on_troncal') or r.get('open_non_abc')) else 'TERNA_GAP'),
            }
            for r in results
        ],
    }

    out_path = ROOT / 'referencia' / 'audit_ternas_ug.json'
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'ReD: {paths[0]}')
    print(f'Alimentadores: {out["n_feeders"]}')
    print(f'Nodos compartidos entre alimentadores: {out["shared_nodes"]}')
    print(f'Con gaps de terna en troncal->enlace: {out["n_with_terna_issues"]}')
    print(f'Mismatch Overhead TXT<->modelo: {out["n_ug_mismatch"]}')
    print(f'Fallos build_feeder_model: {out["n_build_fail"]}')
    print()
    print('--- Top gaps de terna ---')
    for item in out['terna_issues'][:30]:
        print(
            f"{item['feeder']}: non_abc_troncal={item['n_non_abc_on_troncal']} "
            f"open_non_abc={item['n_open_non_abc']} ug={item['n_ug']} "
            f"open_devs={item['n_open_devs']} troncal={item['n_troncal_secs']} "
            f"phases={item['all_phase']}"
        )
        for s in item['non_abc_sample'][:3]:
            print(f"    {s}")
    if out['ug_mismatch']:
        print('--- UG mismatch ---')
        for m in out['ug_mismatch'][:20]:
            print(m)
    if out['build_fail']:
        print('--- Build fail ---')
        for m in out['build_fail'][:20]:
            print(m)
    print(f'Reporte: {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
