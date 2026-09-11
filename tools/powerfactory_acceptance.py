#!/usr/bin/env python3
"""Runtime acceptance test for an IGEA_DGS feeder imported in PowerFactory.

Run this script with the Python interpreter bundled/configured for the target
PowerFactory installation, after importing the generated DGS and activating the
project/network. It intentionally imports ``powerfactory`` only inside main().
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


def _attr(obj: Any, name: str, default=None):
    if obj is None:
        return default
    try:
        value = obj.GetAttribute(name)
        if value is not None:
            return value
    except Exception:
        pass
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _name(obj: Any) -> str:
    return str(_attr(obj, 'loc_name', '') or '')


def _contents(obj: Any, pattern: str) -> list[Any]:
    if obj is None:
        return []
    try:
        return list(obj.GetContents(pattern, 1) or [])
    except TypeError:
        try:
            return list(obj.GetContents(pattern) or [])
        except Exception:
            return []
    except Exception:
        return []


def _find_network(app: Any, feeder: str):
    candidates: list[Any] = []
    try:
        folder = app.GetProjectFolder('netdat')
        candidates.extend(_contents(folder, '*.ElmNet'))
    except Exception:
        pass
    if not candidates:
        try:
            candidates.extend(list(app.GetCalcRelevantObjects('*.ElmNet') or []))
        except Exception:
            pass
    exact = [x for x in candidates if _name(x) == feeder]
    if exact:
        return exact[0]
    folded = [x for x in candidates if _name(x).casefold() == feeder.casefold()]
    return folded[0] if folded else None


def _terminal_of_cubicle(cub: Any):
    if cub is None:
        return None
    term = _attr(cub, 'cterm')
    if term is not None:
        return term
    try:
        parent = cub.GetParent()
        if parent is not None and str(parent.GetClassName()) == 'ElmTerm':
            return parent
    except Exception:
        pass
    return None


def _branch_cubicle(obj: Any, side: int):
    attr_name = 'bus1' if side == 0 else 'bus2'
    cub = _attr(obj, attr_name)
    if cub is not None:
        return cub
    for method_name in ('GetCubicle', 'GetBus'):
        try:
            method = getattr(obj, method_name)
            candidate = method(side)
            if candidate is not None:
                return candidate
        except Exception:
            continue
    return None


def _one_terminal_cubicle(obj: Any):
    cub = _attr(obj, 'bus1')
    if cub is not None:
        return cub
    for method_name in ('GetCubicle', 'GetBus'):
        try:
            candidate = getattr(obj, method_name)(0)
            if candidate is not None:
                return candidate
        except Exception:
            continue
    return None


def _write_reports(report: dict, json_path: Path, txt_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = [
        f"POWERFACTORY RUNTIME ACCEPTANCE: {report['feeder']}",
        '=' * 78,
        f"PowerFactory runtime PASS: {report['powerfactory_runtime_pass']}",
        f"Geographic diagram PASS:   {report['geographic_diagram_pass']}",
        f"Load flow executed:         {report['load_flow']['requested']}",
        f"Load flow PASS:             {report['load_flow']['pass']}",
        '',
        'COUNTS',
    ]
    for key, expected in report['expected_counts'].items():
        actual = report['actual_counts'].get(key)
        lines.append(f'  {key}: expected={expected}, actual={actual}')
    lines += [
        '',
        f"GPS terminals: {report['gps']['valid']}/{report['gps']['total']} ({report['gps']['coverage_pct']} %)",
        f"Lines with two valid terminal connections: {report['connectivity']['valid_lines']}/{report['connectivity']['total_lines']}",
        f"Diagram object: {report['diagram']['object_name']}",
        f"Rendered evidence: {report['diagram']['render_evidence']}",
        '',
        f"ERRORS: {len(report['errors'])}",
    ]
    lines.extend(f'  - {x}' for x in report['errors'])
    lines.append(f"WARNINGS: {len(report['warnings'])}")
    lines.extend(f'  - {x}' for x in report['warnings'])
    txt_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Validate an imported IGEA/DGS feeder inside DIgSILENT PowerFactory')
    p.add_argument('--manifest', required=True, help='Generated <FEEDER>_geography.json')
    p.add_argument('--run-load-flow', action='store_true', help='Execute ComLdf and require return code 0')
    p.add_argument('--require-diagram', action='store_true', help='Require ElmNet.pDiagram to resolve and graphical content to be accessible')
    p.add_argument('--export-wmf', help='Optional WMF path used as rendering evidence for the associated network diagram')
    p.add_argument('--output-json', help='Runtime acceptance JSON report')
    p.add_argument('--output-txt', help='Runtime acceptance text report')
    return p


def run_acceptance(app: Any, manifest_path: Path, *, run_load_flow: bool = False, require_diagram: bool = False, export_wmf: str | None = None) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    feeder = manifest['feeder']
    expected = dict(manifest['expected_counts'])
    errors: list[str] = []
    warnings: list[str] = []

    net = _find_network(app, feeder)
    if net is None:
        errors.append(f'ElmNet {feeder!r} not found in the active project/network data folder')
        return {
            'feeder': feeder,
            'powerfactory_runtime_pass': False,
            'geographic_diagram_pass': False,
            'expected_counts': expected,
            'actual_counts': {},
            'gps': {'valid': 0, 'total': expected.get('nodes', 0), 'coverage_pct': 0.0},
            'connectivity': {'valid_lines': 0, 'total_lines': expected.get('lines', 0)},
            'diagram': {'object_name': None, 'render_evidence': None},
            'load_flow': {'requested': run_load_flow, 'pass': None, 'return_code': None},
            'errors': errors,
            'warnings': warnings,
        }

    terms = _contents(net, '*.ElmTerm')
    lines = _contents(net, '*.ElmLne')
    loads = _contents(net, '*.ElmLod')
    switches = _contents(net, '*.StaSwitch')
    sources = _contents(net, '*.ElmXnet')
    actual = {
        'nodes': len(terms),
        'lines': len(lines),
        'loads': len(loads),
        'switches': len(switches),
        'sources': len(sources),
        # Intermediate geometry is stored in the conversion manifest and is
        # not represented as independent PowerFactory electrical objects.
        'intermediate_points': expected.get('intermediate_points'),
    }
    for key in ('nodes', 'lines', 'loads', 'switches', 'sources'):
        if actual[key] != expected.get(key):
            errors.append(f'{key} count mismatch: expected {expected.get(key)}, actual {actual[key]}')

    # GPS validation: every terminal must carry finite WGS84 coordinates.
    valid_gps = 0
    bad_gps: list[str] = []
    for term in terms:
        lat = _attr(term, 'GPSlat')
        lon = _attr(term, 'GPSlon')
        try:
            latf, lonf = float(lat), float(lon)
            ok = math.isfinite(latf) and math.isfinite(lonf) and -90 <= latf <= 90 and -180 <= lonf <= 180
        except (TypeError, ValueError):
            ok = False
        if ok:
            valid_gps += 1
        else:
            bad_gps.append(_name(term))
    gps_coverage = (100.0 * valid_gps / len(terms)) if terms else 0.0
    if valid_gps != len(terms):
        errors.append(f'{len(terms) - valid_gps} ElmTerm objects have invalid GPSlat/GPSlon')

    # Compare imported terminal coordinates with the source conversion manifest
    # whenever loc_name is unique after the DGS 40-character name limit.
    expected_geo = {str(k)[:40]: v for k, v in manifest.get('nodes', {}).items()}
    duplicate_expected_names = len(expected_geo) != len(manifest.get('nodes', {}))
    if duplicate_expected_names:
        warnings.append('Some source node names collide after 40-character DGS loc_name truncation; per-name GPS comparison skipped for those collisions.')
    imported_by_name = {_name(t): t for t in terms}
    coordinate_mismatches = 0
    for name, point in expected_geo.items():
        term = imported_by_name.get(name)
        if term is None:
            continue
        try:
            latf = float(_attr(term, 'GPSlat'))
            lonf = float(_attr(term, 'GPSlon'))
            if not (math.isclose(latf, float(point['lat']), rel_tol=0.0, abs_tol=1e-7) and math.isclose(lonf, float(point['lon']), rel_tol=0.0, abs_tol=1e-7)):
                coordinate_mismatches += 1
        except Exception:
            coordinate_mismatches += 1
    if coordinate_mismatches:
        errors.append(f'{coordinate_mismatches} ElmTerm GPS coordinates differ from the conversion manifest')

    # Topological connectivity: each line must resolve to two cubicles whose
    # parents are terminals. This directly tests the DGS StaCubic relationships.
    valid_lines = 0
    for line in lines:
        c1 = _branch_cubicle(line, 0)
        c2 = _branch_cubicle(line, 1)
        if c1 is not None and c2 is not None and _terminal_of_cubicle(c1) is not None and _terminal_of_cubicle(c2) is not None:
            valid_lines += 1
    if valid_lines != len(lines):
        errors.append(f'{len(lines) - valid_lines} ElmLne objects do not resolve to two valid terminal cubicles')

    unconnected_single = 0
    for obj in [*loads, *sources]:
        if _terminal_of_cubicle(_one_terminal_cubicle(obj)) is None:
            unconnected_single += 1
    if unconnected_single:
        errors.append(f'{unconnected_single} load/source objects do not resolve to a terminal cubicle')

    # Diagram evidence. The generated DGS explicitly points ElmNet.pDiagram to
    # its diagram. PowerFactory is final authority on whether that pointer is
    # materialised and renderable in the target release/project configuration.
    diagram = _attr(net, 'pDiagram')
    diagram_name = _name(diagram) if diagram is not None else None
    graphic_count = None
    graphic_connector_count = None
    if diagram is not None:
        try:
            graphic_count = len(_contents(diagram, '*.IntGrf'))
            graphic_connector_count = len(_contents(diagram, '*.IntGrfcon'))
        except Exception:
            pass
    diagram_pass = diagram is not None
    if require_diagram and diagram is None:
        errors.append('ElmNet.pDiagram is empty/unresolved; required geographic/single-line diagram was not materialised')

    render_evidence = None
    if export_wmf:
        target = Path(export_wmf)
        target.parent.mkdir(parents=True, exist_ok=True)
        if diagram is None:
            errors.append('Cannot export rendering evidence because ElmNet.pDiagram is unresolved')
        else:
            try:
                board = app.GetGraphicsBoard()
                try:
                    diagram.Show()
                except Exception:
                    board.Show(diagram)
                board.WriteWMF(str(target))
                if target.exists() and target.stat().st_size > 0:
                    render_evidence = str(target)
                else:
                    errors.append('Graphics Board did not produce a non-empty WMF rendering')
            except Exception as exc:
                errors.append(f'Network diagram rendering/export failed: {exc}')
        diagram_pass = diagram_pass and render_evidence is not None

    if require_diagram and graphic_count == 0:
        errors.append('Associated diagram exposes zero IntGrf objects')
        diagram_pass = False

    load_flow = {'requested': run_load_flow, 'pass': None, 'return_code': None}
    if run_load_flow:
        try:
            cmd = app.GetFromStudyCase('ComLdf')
            if cmd is None:
                errors.append('ComLdf not found in active study case')
                load_flow['pass'] = False
            else:
                rc = int(cmd.Execute())
                load_flow['return_code'] = rc
                load_flow['pass'] = rc == 0
                if rc != 0:
                    errors.append(f'Load flow ComLdf returned {rc}')
        except Exception as exc:
            load_flow['pass'] = False
            errors.append(f'Load flow execution failed: {exc}')

    powerfactory_runtime_pass = not errors
    report = {
        'feeder': feeder,
        'network_id': manifest.get('network_id'),
        'powerfactory_runtime_pass': powerfactory_runtime_pass,
        'geographic_diagram_pass': diagram_pass,
        'expected_counts': expected,
        'actual_counts': actual,
        'gps': {
            'valid': valid_gps,
            'total': len(terms),
            'coverage_pct': round(gps_coverage, 9),
            'invalid_names_sample': bad_gps[:20],
            'coordinate_mismatches': coordinate_mismatches,
        },
        'connectivity': {'valid_lines': valid_lines, 'total_lines': len(lines)},
        'diagram': {
            'object_name': diagram_name,
            'graphic_objects': graphic_count,
            'graphic_connections': graphic_connector_count,
            'render_evidence': render_evidence,
            'require_diagram': require_diagram,
        },
        'load_flow': load_flow,
        'errors': errors,
        'warnings': warnings,
    }
    return report


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = Path(args.manifest)
    try:
        import powerfactory as pf  # noqa: PLC0415 - must be runtime-only
    except ImportError:
        print('ERROR: powerfactory Python module is unavailable. Run this script with the PowerFactory Python environment.', file=sys.stderr)
        return 3
    app = pf.GetApplication()
    if app is None:
        print('ERROR: PowerFactory application is not available.', file=sys.stderr)
        return 3
    report = run_acceptance(
        app,
        manifest_path,
        run_load_flow=args.run_load_flow,
        require_diagram=args.require_diagram,
        export_wmf=args.export_wmf,
    )
    feeder = report['feeder']
    json_path = Path(args.output_json) if args.output_json else manifest_path.with_name(f'{feeder}_powerfactory_acceptance.json')
    txt_path = Path(args.output_txt) if args.output_txt else manifest_path.with_name(f'{feeder}_powerfactory_acceptance.txt')
    _write_reports(report, json_path, txt_path)
    print(f"PowerFactory runtime PASS: {report['powerfactory_runtime_pass']}")
    print(f"Geographic diagram PASS: {report['geographic_diagram_pass']}")
    print(f"JSON: {json_path}")
    print(f"TXT: {txt_path}")
    return 0 if report['powerfactory_runtime_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
