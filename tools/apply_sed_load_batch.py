#!/usr/bin/env python
"""Aplica o simula un plan multi-alimentador en una sola sesión PowerFactory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from powerfactory_load_batch import apply_feeder_transaction


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Actualiza cargas por alimentador con preflight, verificación y rollback.',
    )
    parser.add_argument('--plan', required=True, help='JSON de plan cargas_lote')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Valida sin escribir')
    mode.add_argument('--apply', action='store_true', help='Aplica y exige ComLdf convergente')
    parser.add_argument('--output-json', required=True, help='Informe JSON de ejecución')
    parser.add_argument('--cancel-file', help='Marcador cooperativo de cancelación')
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    payload = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    feeders = payload.get('feeders') or []
    if not feeders:
        print('ERROR: el plan no contiene alimentadores.')
        return 2
    try:
        import powerfactory
        app = powerfactory.GetApplicationExt()
    except (ImportError, RuntimeError, OSError) as exc:
        print(f'ERROR: API de PowerFactory no disponible: {exc}')
        return 3
    if app is None:
        print('ERROR: PowerFactory no devolvió una aplicación activa.')
        return 3

    results = []
    cancel_file = Path(args.cancel_file) if args.cancel_file else None
    for feeder_plan in feeders:
        result = apply_feeder_transaction(
            app,
            feeder_plan,
            dry_run=bool(args.dry_run),
            cancel_requested=(lambda: bool(cancel_file and cancel_file.exists())),
        )
        results.append(result)
        print(
            f"{result.get('feeder')}: {result['status']} "
            f"({result.get('written', 0)} escritura(s))"
        )
        if cancel_file and cancel_file.exists():
            break
    statuses = [item['status'] for item in results]
    if statuses and all(status == 'PASS' for status in statuses):
        overall = 'PASS'
    elif 'CRITICAL' in statuses:
        overall = 'CRITICAL'
    elif 'PASS' in statuses:
        overall = 'PARTIAL'
    elif statuses and all(status == 'ROLLED_BACK' for status in statuses):
        overall = 'ROLLED_BACK'
    else:
        overall = 'FAILED'
    report = {
        'batch_id': payload.get('batch_id'),
        'dry_run': bool(args.dry_run),
        'status': overall,
        'feeders': results,
    }
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
