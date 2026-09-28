#!/usr/bin/env python
"""Aceptación destructiva-controlada de cargas, con restauración obligatoria."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import powerfactory_load_batch as default_engine
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import powerfactory_load_batch as default_engine


PROJECT_PREFIX = 'IGEA_DGS_CONVERTER_'


def _same_snapshot(current: dict, expected: dict) -> bool:
    if current.keys() != expected.keys():
        return False
    for key, wanted in expected.items():
        actual = current[key]
        if isinstance(wanted, (int, float)) and isinstance(actual, (int, float)):
            if abs(float(actual) - float(wanted)) > 1e-9:
                return False
        elif actual != wanted:
            return False
    return True


def _application() -> Any:
    try:
        from powerfactory_acceptance import connect_powerfactory
    except ModuleNotFoundError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from powerfactory_acceptance import connect_powerfactory
    return connect_powerfactory(start_engine=True, command_line='-shared')


def run_acceptance(
    plan_path: Path | str,
    *,
    restore_originals: bool = True,
    app: Any = None,
    engine: Any = None,
    output_path: Path | str | None = None,
) -> dict:
    """Aplica el lote en proyectos dedicados y prueba que la restauración es exacta."""
    if not restore_originals:
        raise ValueError('La aceptación real exige restaurar siempre los valores originales.')
    path = Path(plan_path)
    raw = path.read_bytes()
    plan = json.loads(raw.decode('utf-8'))
    feeders = plan.get('feeders') or []
    invalid = [
        item.get('project_name') for item in feeders
        if not str(item.get('project_name') or '').startswith(PROJECT_PREFIX)
    ]
    if invalid:
        raise ValueError(
            f'La aceptación solo opera proyectos dedicados con prefijo {PROJECT_PREFIX}: {invalid}'
        )
    if not feeders:
        raise ValueError('El plan de aceptación no contiene alimentadores.')

    backend = engine or default_engine
    pf_app = app or _application()
    application_results = []
    restoration_results = []
    for feeder_plan in feeders:
        project = feeder_plan['project_name']
        resolved = backend.resolve_feeder_loads(pf_app, project, feeder_plan)
        if resolved.get('errors'):
            application_results.append({
                'feeder': feeder_plan.get('feeder'), 'status': 'FAILED',
                'errors': resolved['errors'],
            })
            restoration_results.append({
                'feeder': feeder_plan.get('feeder'), 'restored': True,
                'errors': [], 'load_flow': None,
            })
            continue
        objects = resolved['objects']
        originals = {code: backend.snapshot_load(obj) for code, obj in objects.items()}
        applied = None
        restore_errors: list[str] = []
        try:
            applied = backend.apply_feeder_transaction(pf_app, feeder_plan, dry_run=False)
            application_results.append(applied)
        except Exception as exc:
            application_results.append({
                'feeder': feeder_plan.get('feeder'), 'status': 'FAILED',
                'errors': [str(exc)],
            })
        finally:
            for code, obj in objects.items():
                try:
                    backend.restore_load(obj, originals[code])
                except Exception as exc:
                    restore_errors.append(f'{code}: {exc}')
            restored = True
            for code, obj in objects.items():
                current = backend.snapshot_load(obj)
                if not _same_snapshot(current, originals[code]):
                    restored = False
                    restore_errors.append(f'{code}: valores finales distintos de los originales')
            flow = backend.run_load_flow(pf_app)
            if not flow.get('converged'):
                restored = False
                restore_errors.append('ComLdf no converge después de restaurar')
            restoration_results.append({
                'feeder': feeder_plan.get('feeder'),
                'project_name': project,
                'restored': restored and not restore_errors,
                'errors': restore_errors,
                'load_flow': flow,
                'objects': len(objects),
            })

    ok = (
        all(item.get('status') == 'PASS' for item in application_results)
        and all(item.get('restored') for item in restoration_results)
    )
    report = {
        'status': 'PASS' if ok else 'FAIL',
        'batch_id': plan.get('batch_id'),
        'plan_path': str(path.resolve()),
        'plan_sha256': hashlib.sha256(raw).hexdigest(),
        'application_sessions': 1,
        'application': {'feeders': application_results},
        'restoration': {'required': True, 'feeders': restoration_results},
    }
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output-json', default='load_batch_acceptance.json')
    args = parser.parse_args(argv)
    report = run_acceptance(args.plan, output_path=args.output_json)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
