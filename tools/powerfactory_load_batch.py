"""Motor transaccional para actualizar cargas de varios alimentadores en PowerFactory.

No importa ``powerfactory``: recibe la aplicación ya conectada para poder probar toda
la lógica de identidad, escritura, verificación y rollback sin la API propietaria.
"""

from __future__ import annotations

import math
from typing import Any, Callable


PHASES = ('r', 's', 't')
SNAPSHOT_ATTRS = (
    'mode_inp', 'i_sym', 'plini', 'qlini', 'slini', 'coslini', 'pf_recap',
    'plinir', 'plinis', 'plinit', 'qlinir', 'qlinis', 'qlinit',
)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = obj.GetAttribute(name)
    except Exception:
        try:
            value = getattr(obj, name)
        except Exception:
            return default
    return default if value is None else value


def _set(obj: Any, name: str, value: Any) -> None:
    try:
        obj.SetAttribute(name, value)
    except (AttributeError, TypeError):
        setattr(obj, name, value)


def snapshot_load(obj: Any) -> dict[str, Any]:
    """Captura todas las entradas capaces de cambiar, incluidas las fases."""
    return {name: _get(obj, name) for name in SNAPSHOT_ATTRS}


def restore_load(obj: Any, snapshot: dict[str, Any]) -> None:
    """Restaura el modo primero y después cada entrada capturada."""
    for name in SNAPSHOT_ATTRS:
        if name in snapshot:
            _set(obj, name, snapshot[name])


def _project_network_id(project: Any, app: Any) -> str:
    for name in ('p:network_id', 'NetworkID', 'network_id'):
        value = _get(project, name, '')
        if str(value or '').strip():
            return str(value).strip()
    try:
        grids = list(app.GetCalcRelevantObjects('*.ElmNet'))
    except Exception:
        grids = []
    names = [str(_get(grid, 'loc_name', '') or '').strip() for grid in grids]
    return names[0] if len([name for name in names if name]) == 1 else ''


def resolve_feeder_loads(app: Any, project_name: str, feeder_plan: dict) -> dict:
    """Resuelve proyecto y cargas por la identidad (proyecto, NetworkID, feeder, SED)."""
    projects = list(app.GetCurrentUser().GetContents('*.IntPrj'))
    exact = [project for project in projects if str(_get(project, 'loc_name', '')) == project_name]
    errors: list[str] = []
    if len(exact) != 1:
        return {
            'project': None,
            'objects': {},
            'errors': [f'Proyecto exacto {project_name!r} no encontrado o ambiguo.'],
        }
    project = exact[0]
    try:
        rc = project.Activate()
    except Exception as exc:
        return {'project': project, 'objects': {}, 'errors': [f'No se pudo activar: {exc}']}
    if rc not in (None, 0):
        errors.append(f'No se pudo activar el proyecto {project_name!r}: rc={rc}.')
    try:
        if not app.GetActiveStudyCase():
            folder = app.GetProjectFolder('study')
            cases = list(folder.GetContents('*.IntCase')) if folder else []
            if cases:
                cases[0].Activate()
    except (AttributeError, TypeError):
        pass

    expected_network = str(feeder_plan.get('network_id') or '').strip()
    actual_network = _project_network_id(project, app)
    if expected_network and actual_network and actual_network != expected_network:
        errors.append(
            f'NetworkID no coincide: proyecto={actual_network!r}, plan={expected_network!r}.'
        )

    feeder = str(feeder_plan.get('feeder') or '').strip()
    by_code: dict[str, list[Any]] = {}
    for obj in app.GetCalcRelevantObjects('*.ElmLod'):
        if str(_get(obj, 'p:alimentador', '') or '').strip() != feeder:
            continue
        code = str(_get(obj, 'loc_name', '') or '').strip()
        by_code.setdefault(code, []).append(obj)

    objects: dict[str, Any] = {}
    for row in feeder_plan.get('updates') or []:
        code = str(row.get('sed_code') or '').strip()
        if str(row.get('feeder') or feeder).strip() != feeder:
            errors.append(f'{code}: alimentador de la fila no coincide con {feeder}.')
            continue
        if str(row.get('network_id') or expected_network).strip() != expected_network:
            errors.append(f'{code}: NetworkID de la fila no coincide con el plan.')
            continue
        candidates = by_code.get(code, [])
        if not candidates:
            errors.append(f'{code}: carga no encontrada en el alimentador {feeder}.')
        elif len(candidates) > 1:
            errors.append(f'{code}: carga ambigua dentro del alimentador {feeder}.')
        else:
            objects[code] = candidates[0]
    return {'project': project, 'objects': objects, 'errors': errors}


def write_load(obj: Any, requested: dict) -> None:
    p = float(requested['plini_mw'])
    q = float(requested['qlini_mvar'])
    s = float(requested.get('slini_mva') or math.hypot(p, q))
    cos = float(requested.get('coslini') or (abs(p) / s if s else 1.0))
    if int(_get(obj, 'i_sym', 0) or 0) == 1:
        p_old = [float(_get(obj, f'plini{phase}', 0.0) or 0.0) for phase in PHASES]
        q_old = [float(_get(obj, f'qlini{phase}', 0.0) or 0.0) for phase in PHASES]
        p_sum, q_sum = sum(p_old), sum(q_old)
        p_new = [value * p / p_sum for value in p_old] if p_sum else [p / 3.0] * 3
        if q_sum:
            q_new = [value * q / q_sum for value in q_old]
        elif p:
            q_new = [q * value / p for value in p_new]
        else:
            q_new = [q / 3.0] * 3
        targets = {}
        for phase, p_value, q_value in zip(PHASES, p_new, q_new):
            targets[f'plini{phase}'] = p_value
            targets[f'qlini{phase}'] = q_value
            _set(obj, f'plini{phase}', p_value)
            _set(obj, f'qlini{phase}', q_value)
        requested['_phase_targets'] = targets
        return

    mode = str(_get(obj, 'mode_inp', 'PC') or 'PC').upper()
    if mode == 'PQ':
        _set(obj, 'plini', p)
        _set(obj, 'qlini', q)
    elif mode == 'SC':
        _set(obj, 'slini', s)
        _set(obj, 'coslini', cos)
    elif mode == 'SP':
        _set(obj, 'slini', s)
        _set(obj, 'plini', p)
    elif mode == 'QC':
        _set(obj, 'qlini', q)
        _set(obj, 'coslini', cos)
    else:
        _set(obj, 'plini', p)
        _set(obj, 'coslini', cos)
    if mode in ('PC', 'SC', 'QC'):
        _set(obj, 'pf_recap', 1 if q < 0 else 0)


def verify_load(obj: Any, requested: dict) -> list[str]:
    expected_p = float(requested['plini_mw'])
    expected_q = float(requested['qlini_mvar'])
    expected_pf = float(
        requested.get('coslini')
        or (abs(expected_p) / math.hypot(expected_p, expected_q)
            if expected_p or expected_q else 1.0)
    )
    errors: list[str] = []

    if int(_get(obj, 'i_sym', 0) or 0) == 1:
        p_values = [float(_get(obj, f'plini{phase}', 0.0) or 0.0) for phase in PHASES]
        q_values = [float(_get(obj, f'qlini{phase}', 0.0) or 0.0) for phase in PHASES]
        actual_p, actual_q = sum(p_values), sum(q_values)
        for attr, expected in (requested.get('_phase_targets') or {}).items():
            actual = float(_get(obj, attr, 0.0) or 0.0)
            if not _close_power(actual, float(expected)):
                errors.append(f'{attr}: {actual:.9g} != {float(expected):.9g}')
    else:
        actual_p, actual_q = _balanced_pq(obj)

    actual_pf = (
        abs(actual_p) / math.hypot(actual_p, actual_q)
        if actual_p or actual_q else 1.0
    )
    if not _close_power(actual_p, expected_p):
        errors.append(f'P total: {actual_p:.9g} != {expected_p:.9g}')
    if not _close_power(actual_q, expected_q):
        errors.append(f'Q total: {actual_q:.9g} != {expected_q:.9g}')
    if abs(actual_pf - expected_pf) > 1e-6:
        errors.append(f'FP: {actual_pf:.9g} != {expected_pf:.9g}')
    return errors


def _close_power(actual: float, expected: float) -> bool:
    return abs(actual - expected) <= 1e-6 + 1e-4 * abs(expected)


def _balanced_pq(obj: Any) -> tuple[float, float]:
    mode = str(_get(obj, 'mode_inp', 'PC') or 'PC').upper()
    recap = -1.0 if int(_get(obj, 'pf_recap', 0) or 0) == 1 else 1.0
    if mode == 'PQ':
        return float(_get(obj, 'plini', 0.0) or 0.0), float(_get(obj, 'qlini', 0.0) or 0.0)
    if mode == 'SP':
        s = float(_get(obj, 'slini', 0.0) or 0.0)
        p = float(_get(obj, 'plini', 0.0) or 0.0)
        return p, recap * math.sqrt(max(0.0, s * s - p * p))
    cos = min(1.0, max(0.0, abs(float(_get(obj, 'coslini', 1.0) or 0.0))))
    if mode == 'SC':
        s = float(_get(obj, 'slini', 0.0) or 0.0)
        return s * cos, recap * s * math.sqrt(max(0.0, 1.0 - cos * cos))
    if mode == 'QC':
        q = float(_get(obj, 'qlini', 0.0) or 0.0)
        sine = math.sqrt(max(0.0, 1.0 - cos * cos))
        return (abs(q) * cos / sine if sine else 0.0), q
    p = float(_get(obj, 'plini', 0.0) or 0.0)
    return p, recap * abs(p) * math.tan(math.acos(cos))


def _verified_values(obj: Any) -> dict[str, Any]:
    if int(_get(obj, 'i_sym', 0) or 0) == 1:
        phases = {
            attr: float(_get(obj, attr, 0.0) or 0.0)
            for prefix in ('plini', 'qlini') for attr in (f'{prefix}r', f'{prefix}s', f'{prefix}t')
        }
        p = sum(phases[f'plini{phase}'] for phase in PHASES)
        q = sum(phases[f'qlini{phase}'] for phase in PHASES)
    else:
        p, q = _balanced_pq(obj)
        phases = {}
    pf = abs(p) / math.hypot(p, q) if p or q else 1.0
    return {'plini_mw': p, 'qlini_mvar': q, 'coslini': pf, 'phases': phases}


class TransactionCancelled(RuntimeError):
    pass


def apply_feeder_transaction(
    app: Any,
    feeder_plan: dict,
    *,
    dry_run: bool,
    cancel_requested: Callable[[], bool] | None = None,
) -> dict:
    cancelled = cancel_requested or (lambda: False)
    resolved = resolve_feeder_loads(
        app, str(feeder_plan.get('project_name') or ''), feeder_plan,
    )
    if resolved['errors']:
        return {
            'feeder': feeder_plan.get('feeder'),
            'status': 'ROLLED_BACK',
            'written': 0,
            'errors': resolved['errors'],
            'dry_run': bool(dry_run),
            'details': [],
        }
    if cancelled():
        return {
            'feeder': feeder_plan.get('feeder'), 'status': 'ROLLED_BACK',
            'written': 0, 'errors': ['Cancelado antes de escribir.'],
            'rollback_errors': [], 'dry_run': bool(dry_run), 'details': [],
        }
    if dry_run:
        details = [
            {
                'sed_code': code,
                'before': snapshot_load(obj),
                'requested': rows,
                'verified': None,
                'status': 'VALIDATED',
                'reason': '',
            }
            for code, obj in sorted(resolved['objects'].items())
            for rows in [next(
                row for row in feeder_plan.get('updates') or []
                if str(row.get('sed_code') or '').strip() == code
            )]
        ]
        return {
            'feeder': feeder_plan.get('feeder'),
            'status': 'PASS',
            'written': 0,
            'matched': len(resolved['objects']),
            'errors': [],
            'dry_run': True,
            'details': details,
        }

    objects = resolved['objects']
    rows = {
        str(row.get('sed_code') or '').strip(): row
        for row in feeder_plan.get('updates') or []
    }
    snapshots = {code: snapshot_load(obj) for code, obj in objects.items()}
    written = 0
    errors: list[str] = []
    details: list[dict[str, Any]] = []
    load_flow = None
    try:
        for code in sorted(objects):
            if cancelled():
                raise TransactionCancelled('Cancelación solicitada; iniciando rollback.')
            write_load(objects[code], rows[code])
            written += 1
            verification = verify_load(objects[code], rows[code])
            errors.extend(f'{code}: {error}' for error in verification)
            details.append({
                'sed_code': code,
                'before': snapshots[code],
                'requested': rows[code],
                'verified': _verified_values(objects[code]),
                'status': 'FAILED' if verification else 'VERIFIED',
                'reason': '; '.join(verification),
            })
            if cancelled():
                raise TransactionCancelled('Cancelación solicitada; iniciando rollback.')
        if errors:
            raise RuntimeError('La relectura no coincide con los valores solicitados.')
        load_flow = _run_load_flow(app)
        if not load_flow['converged']:
            raise RuntimeError('ComLdf no convergió después de actualizar las cargas.')
    except Exception as exc:
        errors.append(str(exc))
        rollback_errors: list[str] = []
        for code in sorted(objects):
            try:
                restore_load(objects[code], snapshots[code])
                current = snapshot_load(objects[code])
                for attr, expected in snapshots[code].items():
                    actual = current.get(attr)
                    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                        if abs(float(actual) - float(expected)) > 1e-9:
                            rollback_errors.append(
                                f'{code}: rollback no restauró {attr} ({actual!r} != {expected!r})'
                            )
                    elif actual != expected:
                        rollback_errors.append(
                            f'{code}: rollback no restauró {attr} ({actual!r} != {expected!r})'
                        )
            except Exception as rollback_exc:
                rollback_errors.append(f'{code}: rollback falló: {rollback_exc}')
        rollback_flow = _run_load_flow(app)
        if not rollback_flow['converged']:
            rollback_errors.append('ComLdf no converge después del rollback.')
        detailed = {item['sed_code']: item for item in details}
        for code, obj in sorted(objects.items()):
            item = detailed.setdefault(code, {
                'sed_code': code,
                'before': snapshots[code],
                'requested': rows[code],
                'verified': None,
                'reason': '',
            })
            item['status'] = 'CRITICAL' if rollback_errors else 'ROLLED_BACK'
            item['rollback_verified'] = snapshot_load(obj) == snapshots[code]
        details = list(detailed.values())
        return {
            'feeder': feeder_plan.get('feeder'),
            'status': 'CRITICAL' if rollback_errors else 'ROLLED_BACK',
            'written': written,
            'errors': errors,
            'rollback_errors': rollback_errors,
            'load_flow': load_flow,
            'rollback_load_flow': rollback_flow,
            'dry_run': False,
            'details': details,
        }

    return {
        'feeder': feeder_plan.get('feeder'),
        'status': 'PASS',
        'written': written,
        'errors': [],
        'rollback_errors': [],
        'load_flow': load_flow,
        'dry_run': False,
        'details': details,
    }


def _run_load_flow(app: Any) -> dict[str, Any]:
    command = app.GetFromStudyCase('ComLdf')
    if command is None:
        return {'return_code': None, 'ldf_valid': False, 'converged': False}
    try:
        rc = command.Execute()
        valid = bool(app.IsLdfValid())
    except Exception as exc:
        return {
            'return_code': None,
            'ldf_valid': False,
            'converged': False,
            'error': str(exc),
        }
    return {'return_code': rc, 'ldf_valid': valid, 'converged': rc == 0 and valid}
