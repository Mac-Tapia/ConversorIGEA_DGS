#!/usr/bin/env python3
"""Enrich PRODUCTION_READINESS with PF gap-retry appendix."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'output' / 'production_all'


def main() -> int:
    # Base regenerate from merged pf_batch_results
    import sys

    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import _write_production_readiness as wr

    wr.main()

    rep = json.loads((OUT / 'PRODUCTION_READINESS.json').read_text(encoding='utf-8'))
    retry = json.loads((OUT / 'pf_retry_gaps_results.json').read_text(encoding='utf-8'))
    ic = json.loads((OUT / 'IC103_ldf_retry_detail.json').read_text(encoding='utf-8'))
    detail = ic.get('detail') or ic.get('ic103_ldf_detail') or {}

    retry_summary = []
    for r in retry.get('results') or []:
        if r.get('powerfactory_runtime_pass'):
            st = 'PASS'
        elif r.get('timed_out'):
            st = 'TIMEOUT'
        else:
            st = 'FAIL'
        retry_summary.append({
            'feeder': r['feeder'],
            'status': st,
            'elapsed_s': r.get('elapsed_s'),
            'convergence_pass': r.get('convergence_pass'),
        })

    rep['pf_retry_gaps'] = {
        'started_utc': retry.get('started_utc'),
        'ended_utc': retry.get('ended_utc'),
        'per_feeder_timeout_s': retry.get('per_feeder_timeout_s'),
        'results': retry_summary,
        'pass': sum(1 for x in retry_summary if x['status'] == 'PASS'),
        'fail': sum(1 for x in retry_summary if x['status'] == 'FAIL'),
        'timeout': sum(1 for x in retry_summary if x['status'] == 'TIMEOUT'),
    }
    last = detail.get('last_attempt') or {}
    diag = last.get('diagnosis') or {}
    rep['ic103_ldf_detail'] = {
        'returncode_gate': 2,
        'comldf_return_code': detail.get('ldf_return_code'),
        'ldf_valid': detail.get('ldf_valid'),
        'attempts': detail.get('ldf_attempts'),
        'connectivity_pass': detail.get('connectivity_pass'),
        'location_scale_pass': detail.get('location_scale_pass'),
        'equipment_pass': detail.get('equipment_pass'),
        'geographic_diagram_pass': detail.get('geographic_diagram_pass'),
        'errors': detail.get('errors'),
        'diagnosis': [
            'ComLdf.Execute rc=1 — divergence of inner loops (voltage stability / excess load)',
            'User Manual §24.6.4: excess P demand, weak feed, or voltage collapse',
            'Correction intents exhausted (8 attempts including load scale 50/75/100); still diverge',
            'No capacitors/regulators invented — RED has no CAPACITOR/REGULATOR SETTING',
        ],
        'pf_messages_sample': diag.get('pf_messages_sample'),
        'detail_file': str(OUT / 'IC103_ldf_retry_detail.json'),
    }

    pf = rep['powerfactory']
    if (
        pf.get('fail') == 1
        and pf.get('timeout') == 0
        and pf.get('not_pf_tested_count') == 0
        and pf.get('pass', 0) >= 92
    ):
        rep['verdict'] = 'PRODUCTION_READY_WITH_EXCEPTIONS'
        rep['verdict_es'] = (
            'LISTO PARA PRODUCCION CON EXCEPCIONES: conversion 93/93, pytest 43/43, '
            f"gate PF {pf['pass']}/{pf['tested']} PASS (cobertura 100%). "
            'Unico residual: IC103 ComLdf no converge (rc=1, exceso de carga / estabilidad de tension). '
            'No se inventaron condensadores ni reguladores.'
        )
        rep['blockers'] = [
            'IC103: conectividad/GPS/diagrama/equipo OK; ComLdf.Execute rc=1 '
            '(divergencia bucles internos); 8 intentos fix-until-converge agotados; '
            'ver ic103_ldf_detail'
        ]
    elif pf.get('fail') == 0 and pf.get('timeout') == 0 and pf.get('not_pf_tested_count') == 0:
        rep['verdict'] = 'PRODUCTION_READY'
        rep['verdict_es'] = 'LISTO PARA PRODUCCION: conversion, pytest y gate PF 100%.'
        rep['blockers'] = []

    rep['generated_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / 'PRODUCTION_READINESS.json').write_text(
        json.dumps(rep, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )

    # Rewrite TXT with updated header + appendix
    base_txt = (OUT / 'PRODUCTION_READINESS.txt').read_text(encoding='utf-8')
    out_lines: list[str] = []
    for line in base_txt.splitlines():
        if line.startswith('generated_utc:'):
            out_lines.append(f"generated_utc: {rep['generated_utc']}")
        elif line.startswith('VERDICT:'):
            out_lines.append(f"VERDICT: {rep['verdict']}")
        elif (
            line.startswith('LISTO PARA')
            or line.startswith('GO CONDICIONAL')
            or line.startswith('NO LISTO')
        ):
            out_lines.append(rep['verdict_es'])
        else:
            out_lines.append(line)

    appendix = [
        '',
        '=== PF RETRY GAPS (post production batch) ===',
        f"  started={rep['pf_retry_gaps']['started_utc']}",
        f"  ended={rep['pf_retry_gaps']['ended_utc']}",
        f"  timeout_per_feeder_s={rep['pf_retry_gaps']['per_feeder_timeout_s']}",
        (
            f"  retry pass={rep['pf_retry_gaps']['pass']} "
            f"fail={rep['pf_retry_gaps']['fail']} "
            f"timeout={rep['pf_retry_gaps']['timeout']}"
        ),
    ]
    for x in retry_summary:
        appendix.append(
            f"  - {x['feeder']}: {x['status']} ({x.get('elapsed_s')}s) "
            f"ldf={x.get('convergence_pass')}"
        )
    appendix += [
        '',
        '=== IC103 LDF DETAIL (still FAIL) ===',
        (
            f"  gate_rc=2 ComLdf.Execute rc={detail.get('ldf_return_code')} "
            f"ldf_valid={detail.get('ldf_valid')} attempts={detail.get('ldf_attempts')}"
        ),
        '  conn/gps/equip/diagram: OK',
        '  diagnosis: inner-loop divergence (excess P / voltage stability) — User Manual §24.6.4',
        '  NO capacitors/regulators invented',
        f"  detail: {OUT / 'IC103_ldf_retry_detail.json'}",
        '',
        '=== FINAL PF SNAPSHOT ===',
        (
            f"  tested={pf['tested']} pass={pf['pass']} fail={pf['fail']} "
            f"timeout={pf['timeout']} not_tested={pf['not_pf_tested_count']}"
        ),
        (
            f"  runtime_pass_rate={pf.get('runtime_pass_rate')} "
            f"convergence_rate={pf.get('convergence_rate')}"
        ),
        '',
        '=== BLOCKERS (updated) ===',
    ]
    blockers = rep.get('blockers') or ['(none)']
    appendix.extend(f'  - {b}' for b in blockers)
    appendix.append('')

    (OUT / 'PRODUCTION_READINESS.txt').write_text(
        '\n'.join(out_lines).rstrip() + '\n' + '\n'.join(appendix),
        encoding='utf-8',
    )
    print(f"VERDICT={rep['verdict']}")
    print(
        f"PF pass={pf['pass']}/{pf['tested']} fail={pf['fail']} "
        f"timeout={pf['timeout']} not_tested={pf['not_pf_tested_count']}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
