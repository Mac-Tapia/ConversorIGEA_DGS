"""Artefactos inmutables y legibles de cada ejecución de cargas."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _rows(plan: dict, result: dict) -> list[dict[str, Any]]:
    details = {
        (feeder_result.get('feeder'), detail.get('sed_code')): detail
        for feeder_result in result.get('feeders') or []
        for detail in feeder_result.get('details') or []
    }
    statuses = {
        feeder_result.get('feeder'): feeder_result.get('status', result.get('status', ''))
        for feeder_result in result.get('feeders') or []
    }
    rows = []
    for feeder_plan in plan.get('feeders') or []:
        feeder = feeder_plan.get('feeder', '')
        for update in feeder_plan.get('updates') or []:
            detail = details.get((feeder, update.get('sed_code'))) or {}
            before = detail.get('before') or update.get('previous') or {}
            verified = detail.get('verified') or {}
            rows.append({
                'alimentador': feeder,
                'network_id': feeder_plan.get('network_id', ''),
                'sed': update.get('sed_code', ''),
                'p_before_mw': before.get('plini_mw', before.get('plini', '')),
                'q_before_mvar': before.get('qlini_mvar', before.get('qlini', '')),
                'p_requested_mw': update.get('plini_mw', ''),
                'q_requested_mvar': update.get('qlini_mvar', ''),
                'fp_requested': update.get('coslini', ''),
                'p_verified_mw': verified.get('plini_mw', ''),
                'q_verified_mvar': verified.get('qlini_mvar', ''),
                'fp_verified': verified.get('coslini', ''),
                'status': detail.get('status', statuses.get(feeder, '')),
                'reason': detail.get('reason', ''),
            })
    return rows


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = list(rows[0]) if rows else [
        'alimentador', 'network_id', 'sed', 'p_before_mw', 'q_before_mvar',
        'p_requested_mw', 'q_requested_mvar', 'fp_requested', 'p_verified_mw',
        'q_verified_mvar', 'fp_verified', 'status', 'reason',
    ]
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)


def write_load_batch_artifacts(root: Path, plan: dict, result: dict) -> dict[str, str]:
    """Escribe el expediente autocontenido de una ejecución en un directorio nuevo."""
    root.mkdir(parents=True, exist_ok=False)
    canonical = json.dumps(plan, sort_keys=True, ensure_ascii=False).encode('utf-8')
    manifest = {
        'batch_id': plan.get('batch_id'),
        'input_sha256': plan.get('input_sha256'),
        'plan_sha256': _sha256_bytes(canonical),
        'feeders': [
            {
                key: feeder.get(key)
                for key in ('feeder', 'network_id', 'project_name', 'revision',
                            'dgs_sha256', 'metadata_sha256')
            }
            for feeder in plan.get('feeders') or []
        ],
    }
    rows = _rows(plan, result)
    preview = [
        {**row, 'p_verified_mw': '', 'q_verified_mvar': '', 'fp_verified': ''}
        for row in rows
    ]
    rollback = {
        'batch_id': plan.get('batch_id'),
        'feeders': [
            feeder for feeder in result.get('feeders') or []
            if feeder.get('status') in {'ROLLED_BACK', 'CRITICAL'}
        ],
    }
    logs = [
        {'event': 'batch', 'status': result.get('status'), 'dry_run': result.get('dry_run')},
        *(
            {'event': 'feeder', 'feeder': feeder.get('feeder'), 'status': feeder.get('status')}
            for feeder in result.get('feeders') or []
        ),
    ]
    _json(root / 'input_manifest.json', manifest)
    _json(root / 'plan.json', plan)
    _csv(root / 'preview.csv', preview)
    _json(root / 'result.json', result)
    _csv(root / 'result.csv', rows)
    _json(root / 'rollback.json', rollback)
    (root / 'logs.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in logs),
        encoding='utf-8',
    )
    return {name: name for name in (
        'input_manifest.json', 'plan.json', 'preview.csv', 'result.json',
        'result.csv', 'rollback.json', 'logs.jsonl',
    )}
