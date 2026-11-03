"""Asignación verificable de procedencia del conversor en objetos PowerFactory."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

ATTRIBUTE = 'p:alimentador'
CONFIGURATION = 'Trazabilidad CSG'
TARGET_CLASSES = ('ElmLod', 'ElmShnt', 'ElmSubstat', 'ElmSym', 'ElmXnet')


@dataclass(frozen=True)
class RuntimeObjectIdentity:
    class_name: str
    loc_name: str
    terminal: str
    substation: str
    grid: str = ''


@dataclass(frozen=True)
class PlannedAssignment:
    record: Any
    obj: Any


class PowerFactoryMetadataError(RuntimeError):
    """La trazabilidad no se pudo resolver o escribir de forma completa."""


class PowerFactoryMetadataWriteError(PowerFactoryMetadataError):
    """Fallo de escritura con evidencia explícita del rollback ejecutado."""

    def __init__(self, message: str, rollback: dict[str, Any]) -> None:
        super().__init__(message)
        self.rollback = rollback


_LOAD_INTERVENTION_INTENTS = frozenset({
    'disconnect_floating_loads',
    'scale_loads_50',
    'scale_loads_75',
    'scale_loads_100',
    'island_out_of_service',
})


def reconstruction_report_sha256(payload: dict[str, Any]) -> str:
    """Return the canonical identity used when a reconstruction is published."""

    canonical = dict(payload)
    canonical.pop('report_sha256', None)
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def verify_reconstruction_contract(
    feeder_metadata: dict[str, Any],
    report_path: str | Path,
    *,
    expected_hash: str | None = None,
) -> dict[str, Any]:
    """Verify report, sidecar and source run before PowerFactory mutation."""

    reconstruction = feeder_metadata.get('reconstruction')
    if not isinstance(reconstruction, dict):
        raise TypeError('el feeder metadata no declara reconstrucción')
    path = Path(report_path)
    if not path.is_file():
        raise ValueError(f'informe de reconstrucción no encontrado: {path}')
    payload = json.loads(path.read_text(encoding='utf-8'))
    actual_hash = reconstruction_report_sha256(payload)
    declared_hash = str(payload.get('report_sha256') or '')
    sidecar_hash = str(reconstruction.get('report_sha256') or '')
    required_hash = str(expected_hash or sidecar_hash)
    if not required_hash or actual_hash != required_hash:
        raise ValueError('SHA-256 del informe de reconstrucción no coincide')
    if declared_hash != actual_hash or sidecar_hash != actual_hash:
        raise ValueError('SHA-256 declarado por informe/sidecar no coincide')
    if reconstruction.get('report') and reconstruction['report'] != path.name:
        raise ValueError('nombre del informe de reconstrucción no coincide con el sidecar')
    report_run = payload.get('source_run_id')
    sidecar_run = feeder_metadata.get('source_run_id')
    if report_run and sidecar_run and report_run != sidecar_run:
        raise ValueError('ejecución fuente del informe de reconstrucción no coincide')

    counts = payload.get('counts') or {}
    repairs = len(payload.get('decisions') or [])
    declared_repairs = int(reconstruction.get('repairs', repairs))
    catalog_matches = int(counts.get('catalog_match', 0))
    assumptions = int(counts.get('engineering_assumption', 0))
    if declared_repairs != repairs:
        raise ValueError('cantidad de reparaciones del sidecar no coincide con el informe')
    if int(reconstruction.get('catalog_matches', catalog_matches)) != catalog_matches:
        raise ValueError('cantidad de coincidencias de catálogo no coincide')
    if int(reconstruction.get('assumptions', assumptions)) != assumptions:
        raise ValueError('cantidad de supuestos de ingeniería no coincide')
    return {
        'status': 'VERIFIED_BEFORE_MUTATION',
        'report': path.name,
        'report_sha256': actual_hash,
        'repairs': repairs,
        'catalog_matches': catalog_matches,
        'assumptions': assumptions,
        'selection': list(payload.get('selection') or reconstruction.get('selection') or []),
    }


def load_intervention_from_attempts(attempts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize correction attempts that change or shed load."""

    intents: list[str] = []
    changes: list[dict[str, Any]] = []
    for attempt in attempts:
        intent = str(attempt.get('intent') or '')
        correction = attempt.get('correction') or {}
        if intent not in _LOAD_INTERVENTION_INTENTS:
            continue
        if intent not in intents:
            intents.append(intent)
        for change in correction.get('changes') or []:
            changes.append(dict(change))
    return {
        'attempted': bool(intents),
        'intents': intents,
        'changes': changes,
    }


#: 078:RF-1: los tres estados de un flujo. «sin_dato» es un estado, no un «no»: confundirlos daba
#: NOT_CONVERGED a un flujo bueno con ``load_flow_loop`` null, y por eso nadie creía la señal.
FLUJO_CONVERGE = 'converge'
FLUJO_NO_CONVERGE = 'no_converge'
FLUJO_SIN_DATO = 'sin_dato'
#: 078:RF-17, 015:RF-38 a RF-40: el flujo no bloquea la calibración; lo físico, sí.
#: 081:RF-15, RF-30: «CONVERGE_SIN_SERVIR» tampoco bloquea; solo no se llama VERIFICADO.
CASO_BASE_CALIBRABLE = ('VERIFICADO', 'CONVERGE_SIN_SERVIR', 'NO_CONVERGE', 'SIN_DATO_DE_FLUJO')
_MAX_FALLOS = 8
_MAX_HISTORIAL = 30


def _historial_flujo(report: dict[str, Any], load_flow: dict[str, Any], loop: dict[str, Any]) -> list[dict[str, Any]]:
    """Los intentos del flujo, en una sola forma (078:RF-7): el informe, el bucle o la reducción de demanda."""
    propio = report.get('historial')
    if isinstance(propio, list) and propio:
        return propio[:_MAX_HISTORIAL]
    pasos: list[dict[str, Any]] = []
    for intento in loop.get('attempts') or []:
        flujo = intento.get('load_flow') or {}
        pasos.append({'paso': intento.get('attempt'), 'accion': intento.get('intent') or intento.get('phase'),
                      'converge': flujo.get('pass'), 'return_code': flujo.get('return_code')})
    for intento in (load_flow.get('ajuste_de_cargas') or {}).get('intentos') or []:
        pasos.append({'paso': len(pasos), 'accion': f"demanda al {float(intento['factor']) * 100:.1f} %",
                      'factor': intento['factor'], 'converge': intento.get('converge')})
    return pasos[:_MAX_HISTORIAL]


def estado_flujo(report: dict[str, Any]) -> dict[str, Any]:
    """La única lectura del flujo de un informe de aceptación (078:RF-1).

    Mira lo que devolvió DIgSILENT en el último flujo que corrió: el de después de reducir la demanda
    (015:RF-38), el del bucle o el simple. Había tres señales y cada una miraba otra cosa: el código de
    salida del guion daba «OK» sin flujo, ``convergence_pass`` daba False sin flujo y la clasificación
    solo miraba ``load_flow_loop``, null en la vía de la web.
    """
    load_flow = report.get('load_flow') or {}
    loop = report.get('load_flow_loop') or {}
    ajuste = load_flow.get('ajuste_de_cargas') or {}
    ultimo = ajuste.get('final_load_flow') or loop.get('final_load_flow') or load_flow
    codigo, valido = ultimo.get('return_code'), ultimo.get('ldf_valid')
    if codigo not in (None, 0) or valido is False:
        estado = FLUJO_NO_CONVERGE
    elif valido is True:
        estado = FLUJO_CONVERGE
    else:
        estado = FLUJO_SIN_DATO
    factor = ajuste.get('factor') if ajuste.get('final_load_flow') else None
    significado = ultimo.get('return_meaning')
    solicitado = bool(load_flow.get('requested') or report.get('load_flow_loop'))
    if estado == FLUJO_CONVERGE:
        motivo = 'DIgSILENT devolvió return_code ' + ('0' if codigo == 0 else 'sin dato') + ' con el resultado válido.'
        if factor is not None:
            motivo += f' Con la demanda reducida al {float(factor) * 100:.1f} %.'
    elif estado == FLUJO_NO_CONVERGE:
        motivo = (f'DIgSILENT devolvió return_code {codigo}' if codigo not in (None, 0) else
                  'DIgSILENT terminó el flujo sin un resultado válido') + (f': {significado}.' if significado else '.')
    elif solicitado:
        motivo = 'Se pidió el flujo y no hay resultado de DIgSILENT.'
    else:
        motivo = 'El flujo no se ejecutó: sin dato de convergencia.'
    fallos: list[str] = []
    if estado != FLUJO_CONVERGE:
        for fuente in (ultimo.get('errors'), (load_flow.get('diagnostico') or {}).get('issues'),
                       (loop.get('final_diagnosis') or {}).get('issues')):
            fallos += [str(x) for x in fuente or [] if str(x) not in fallos]
    # 081:RF-14: DIgSILENT convergió y lo sigue diciendo; lo que no se sirvió va aparte, para que no parezca limpio.
    tras = report.get('tras_flujo') or {}
    limpio = estado == FLUJO_CONVERGE and tras.get('limpio', True)
    if estado == FLUJO_CONVERGE and not limpio:
        from .comprobacion_flujo import texto_tras_flujo

        motivo += f' Pero {texto_tras_flujo(tras)}.'
    resolucion = load_flow.get('resolucion') or {}                              # 081:RF-27, RF-29
    return {'estado': estado, 'solicitado': solicitado, 'return_code': codigo, 'ldf_valid': valido,
            'significado': significado, 'factor_demanda': factor, 'motivo': motivo, 'fallos': fallos[:_MAX_FALLOS],
            'historial': _historial_flujo(report, load_flow, loop), 'limpio': limpio,
            'tras_flujo': tras or None, 'correcciones': list(resolucion.get('anotaciones') or []),
            'queda': list(resolucion.get('queda') or [])}


def convergence_pass_de(flujo: dict[str, Any]) -> bool | None:
    """``convergence_pass`` de la lectura (078:RF-8): null si no hay dato."""
    return {FLUJO_CONVERGE: True, FLUJO_NO_CONVERGE: False}.get(flujo['estado'])


def estado_caso_base(fisico_ok: bool, flujo: str, *, limpio: bool = True) -> str:
    """El estado del «Caso base» (078:RF-13 a RF-15): VERIFICADO solo con lo físico y el flujo bien.

    Y limpio (081:RF-15): con la barra de baja de una SED a 0 p.u., el flujo «converge» sin servirla.
    """
    if not fisico_ok:
        return 'NO_VERIFICADO'
    if flujo == FLUJO_CONVERGE and not limpio:
        return 'CONVERGE_SIN_SERVIR'
    return {FLUJO_CONVERGE: 'VERIFICADO', FLUJO_NO_CONVERGE: 'NO_CONVERGE'}.get(flujo, 'SIN_DATO_DE_FLUJO')


def classify_convergence(report: dict[str, Any]) -> str:
    """Classify convergence without promoting stale or operator-modified models."""

    source = report.get('source_verification') or {}
    if source.get('status') != 'VERIFIED_BEFORE_MUTATION':
        return 'REJECTED_STALE_EVIDENCE'

    flujo = estado_flujo(report)
    if flujo['estado'] == FLUJO_SIN_DATO:                                       # 078:RF-9
        return 'SIN_DATO'
    if flujo['estado'] == FLUJO_NO_CONVERGE:                                    # 078:RF-10
        return 'NOT_CONVERGED'
    loop = report.get('load_flow_loop') or {}

    reread = report.get('effective_reread') or {}
    rollback = report.get('rollback') or {}
    safe_rollback = {'NOT_REQUIRED', 'NOT_REQUIRED_ISOLATED_PROJECT', 'RESTORED'}
    if (
        not reread.get('feeder_metadata')
        or not reread.get('comldf_executed')
        or not reread.get('comldf_valid')
        or reread.get('capacitor_banks') is False
        or rollback.get('status') not in safe_rollback
    ):
        return 'NEEDS_OPERATOR_REVIEW'

    intervention = report.get('load_intervention') or load_intervention_from_attempts(
        loop.get('attempts') or []
    )
    if intervention.get('attempted') or flujo['factor_demanda'] is not None:    # 078:RF-12
        return 'NEEDS_OPERATOR_REVIEW'

    if flujo['correcciones']:                                                   # 081:RF-32
        return 'CONVERGED_RECONSTRUCTED'

    reconstruction = report.get('reconstruction_verification') or {}
    if reconstruction and reconstruction.get('status') != 'VERIFIED_BEFORE_MUTATION':
        return 'REJECTED_STALE_EVIDENCE'
    if int(reconstruction.get('assumptions', 0)):
        return 'CONVERGED_WITH_ASSUMPTIONS'
    if int(reconstruction.get('repairs', 0)) or int(reconstruction.get('catalog_matches', 0)):
        return 'CONVERGED_RECONSTRUCTED'
    return 'CONVERGED_ORIGINAL'


def assignment_plan_sha256(plan: Iterable[PlannedAssignment]) -> str:
    """Identidad estable del plan resuelto antes de modificar PowerFactory."""
    rows = []
    for item in plan:
        record = item.record
        rows.append({
            'class_name': record.class_name,
            'dgs_fid': record.dgs_fid,
            'loc_name': record.loc_name,
            'feeder': record.feeder,
            'network_id': record.network_id,
            'terminal': record.terminal,
            'substation': record.substation,
            'grid': record.grid,
        })
    encoded = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _attribute(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    try:
        value = obj.GetAttribute(name)
        return default if value is None else value
    except Exception:
        return getattr(obj, name, default)


def _custom_attribute_value(obj: Any, attribute: str) -> Any:
    value = _attribute(obj, attribute, None)
    if value is not None:
        return value
    user_name = attribute.removeprefix('p:')
    getter = getattr(obj, 'GetUserAttribute', None)
    if callable(getter):
        for name in (user_name, attribute):
            try:
                value = getter(name)
            except Exception:
                continue
            if value is not None:
                return value
    return ''


def _scalar_user_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if len(value) == 1 else ('' if not value else value)
    return str(value or '').strip()


def _list_user_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else [value if value is not None else '']


def _class_name(obj: Any) -> str:
    try:
        return str(obj.GetClassName() or '')
    except Exception:
        return ''


def _terminal_name(obj: Any) -> str:
    cubicle = _attribute(obj, 'bus1')
    if cubicle is None:
        for method_name in ('GetCubicle', 'GetBus'):
            try:
                cubicle = getattr(obj, method_name)(0)
                if cubicle is not None:
                    break
            except Exception:
                continue
    terminal = _attribute(cubicle, 'cterm')
    if terminal is None and cubicle is not None:
        try:
            parent = cubicle.GetParent()
            if _class_name(parent) == 'ElmTerm':
                terminal = parent
        except Exception:
            pass
    return str(_attribute(terminal, 'loc_name', '') or '').strip()


def build_runtime_identity(obj: Any) -> RuntimeObjectIdentity:
    class_name = _class_name(obj)
    loc_name = str(_attribute(obj, 'loc_name', '') or '').strip()
    parent = None
    try:
        parent = obj.GetParent()
    except Exception:
        pass
    parent_class = _class_name(parent)
    substation = loc_name if class_name == 'ElmSubstat' else (
        str(_attribute(parent, 'loc_name', '') or '').strip()
        if parent_class == 'ElmSubstat' else ''
    )
    terminal = '' if class_name == 'ElmSubstat' else _terminal_name(obj)
    grid = str(_attribute(parent, 'loc_name', '') or '').strip() if parent_class == 'ElmNet' else ''
    if not grid and parent_class == 'ElmSubstat':
        try:
            grandparent = parent.GetParent()
        except Exception:
            grandparent = None
        if _class_name(grandparent) == 'ElmNet':
            grid = str(_attribute(grandparent, 'loc_name', '') or '').strip()
    return RuntimeObjectIdentity(class_name, loc_name, terminal, substation, grid)


def ensure_alimentador_data_extensions(
    project: Any,
    classes: tuple[str, ...] = TARGET_CLASSES,
) -> dict[str, list[str]]:
    if project is None:
        raise PowerFactoryMetadataError('No hay proyecto activo para crear Data Extensions.')
    begin = getattr(project, 'BeginDataExtensionModification', None)
    end = getattr(project, 'EndDataExtensionModification', None)
    if not callable(begin) or not callable(end):
        raise PowerFactoryMetadataError('La API PowerFactory no expone modificación de Data Extensions.')

    report = {'created': [], 'existing': [], 'errors': []}
    try:
        settings = begin()
    except Exception as exc:
        raise PowerFactoryMetadataError(f'BeginDataExtensionModification falló: {exc}') from exc
    if settings is None:
        raise PowerFactoryMetadataError('BeginDataExtensionModification no devolvió configuración.')
    try:
        for class_name in classes:
            try:
                config = settings.GetConfiguration(class_name, CONFIGURATION)
                created = config is None
                if created:
                    config = settings.AddConfiguration(class_name, CONFIGURATION)
                if config is None:
                    raise RuntimeError('Add/GetConfiguration devolvió None')
                if _configuration_has_variable(config, 'alimentador'):
                    report['existing'].append(class_name)
                else:
                    config.AddString('alimentador', 'Alimentador', '', '')
                    report['created'].append(class_name)
            except Exception as exc:
                report['errors'].append(f'{class_name}: {exc}')
    finally:
        try:
            end()
        except Exception as exc:
            raise PowerFactoryMetadataError(
                f'EndDataExtensionModification falló: {exc}') from exc

    if report['errors']:
        raise PowerFactoryMetadataError('; '.join(report['errors']))
    return report


def _configuration_has_variable(config: Any, variable: str) -> bool:
    for pattern in ('*.IntAddonvars', '*'):
        try:
            entries = config.GetContents(pattern, 1) or []
        except TypeError:
            try:
                entries = config.GetContents(pattern) or []
            except Exception:
                continue
        except Exception:
            continue
        for entry in entries:
            names = {
                str(_attribute(entry, key, '') or '').strip()
                for key in ('loc_name', 'varname', 'variable', 'name')
            }
            if variable in names or f'p:{variable}' in names:
                return True
    try:
        return config.GetAttribute(f'p:{variable}') is not None
    except Exception:
        return False


def resolve_feeder_assignments(records: Iterable[Any], objects: Iterable[Any]) -> list[PlannedAssignment]:
    records = list(records)
    runtime: dict[RuntimeObjectIdentity, list[Any]] = {}
    # Metadatos escritos antes de que la identidad llevara la red (commit 1f415549, 13/10
    # a las 16:13) no traen ``grid``: CA101 de las 12:18 no resolvía ninguna carga al
    # reimportarse. Sin red en el registro se busca sin ella; si hay dos, sigue ambiguo.
    sin_red: dict[RuntimeObjectIdentity, list[Any]] = {}
    for obj in objects:
        identity = build_runtime_identity(obj)
        runtime.setdefault(identity, []).append(obj)
        sin_red.setdefault(replace(identity, grid=''), []).append(obj)

    plan: list[PlannedAssignment] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for record in records:
        identity = RuntimeObjectIdentity(
            record.class_name,
            str(record.loc_name or '').strip(),
            str(record.terminal or '').strip(),
            str(record.substation or '').strip(),
            str(record.grid or '').strip(),
        )
        candidates = (runtime if identity.grid else sin_red).get(identity, [])
        label = (
            f'{record.class_name} {record.loc_name} '
            f'[{record.terminal}/{record.substation}/{record.grid}]'
        )
        if not candidates:
            missing.append(label)
        elif len(candidates) != 1:
            ambiguous.append(f'{label}: {len(candidates)} objetos')
        else:
            plan.append(PlannedAssignment(record, candidates[0]))

    if missing or ambiguous:
        details = []
        if missing:
            details.append('sin resolver: ' + ', '.join(missing[:12]))
        if ambiguous:
            details.append('ambiguos: ' + ', '.join(ambiguous[:12]))
        raise PowerFactoryMetadataError('No se asignó ningún alimentador; ' + '; '.join(details))
    return plan


def apply_feeder_assignment_plan(
    plan: Iterable[PlannedAssignment],
    *,
    attribute: str = ATTRIBUTE,
    expected_plan_sha256: str | None = None,
) -> dict[str, Any]:
    plan = list(plan)
    plan_sha256 = assignment_plan_sha256(plan)
    if expected_plan_sha256 is not None and plan_sha256 != expected_plan_sha256:
        raise PowerFactoryMetadataError(
            'El plan resuelto cambió entre preflight y aplicación; no se escribió nada.'
        )
    previous = [(item.obj, _custom_attribute_value(item.obj, attribute)) for item in plan]
    written: list[tuple[Any, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    try:
        for item, (_obj, old_value) in zip(plan, previous):
            try:
                result = item.obj.SetAttribute(attribute, [item.record.feeder])
            except Exception as exc:
                raise RuntimeError(
                    f'{item.record.class_name} {item.record.loc_name}: '
                    f'SetAttribute({attribute}) falló: {exc}'
                ) from exc
            if result not in (None, 0, True):
                raise RuntimeError(f'SetAttribute devolvió {result!r}')
            written.append((item.obj, old_value))
            actual = _custom_attribute_value(item.obj, attribute)
            if _scalar_user_value(actual) != item.record.feeder:
                raise RuntimeError(
                    f'{item.record.class_name} {item.record.loc_name}: '
                    f'lectura posterior {actual!r}, esperado {item.record.feeder!r}'
                )
            bucket = counts.setdefault(item.record.feeder, {})
            bucket[item.record.class_name] = bucket.get(item.record.class_name, 0) + 1
    except Exception as exc:
        rollback_failures: list[str] = []
        restored = 0
        for obj, old_value in reversed(written):
            try:
                obj.SetAttribute(attribute, _list_user_value(old_value))
                restored += 1
            except Exception as rollback_exc:
                rollback_failures.append(str(rollback_exc))
        rollback = {
            'status': 'RESTORED' if not rollback_failures else 'PARTIAL',
            'attempted': bool(written),
            'restored': restored,
            'failed': rollback_failures,
        }
        raise PowerFactoryMetadataWriteError(str(exc), rollback) from exc
    return {
        'written': len(written),
        'by_feeder': counts,
        'attribute': attribute,
        'dry_run_plan_sha256': plan_sha256,
        'applied_plan_sha256': plan_sha256,
        'plan_identity_match': True,
        'reread_verified': True,
        'reread_count': len(written),
        'rollback': {'status': 'NOT_REQUIRED', 'attempted': False, 'restored': 0, 'failed': []},
    }


def populate_feeder_metadata(app: Any, records: Iterable[Any]) -> dict[str, Any]:
    records = list(records)
    classes = sorted({record.class_name for record in records})
    objects = []
    for class_name in classes:
        objects.extend(list(app.GetCalcRelevantObjects(f'*.{class_name}') or []))
    plan = resolve_feeder_assignments(records, objects)
    plan_sha256 = assignment_plan_sha256(plan)
    project = app.GetActiveProject()
    extension = ensure_alimentador_data_extensions(project)
    assignment = apply_feeder_assignment_plan(plan, expected_plan_sha256=plan_sha256)
    return {'extensions': extension, **assignment}


def apply_imported_feeder_metadata(
    app: Any,
    import_info: dict[str, Any],
    dgs_path: str,
    metadata_path: str | None = None,
) -> dict[str, Any]:
    """Valida el sidecar y asigna propiedad solo al proyecto recién importado."""
    from pathlib import Path

    from .feeder_metadata import FeederAssignment, read_feeder_metadata

    dgs = Path(dgs_path)
    sidecar = Path(metadata_path) if metadata_path else dgs.with_name(
        f'{dgs.stem}_feeder_metadata.json')
    if not sidecar.is_file():
        if metadata_path:
            raise PowerFactoryMetadataError(f'feeder metadata no encontrado: {sidecar}')
        return {'status': 'missing', 'warning': f'No se encontró {sidecar.name}.'}

    metadata = read_feeder_metadata(sidecar, expected_dgs=dgs)
    expected_project = import_info.get('project_name')
    active_project = app.GetActiveProject()
    active_name = str(_attribute(active_project, 'loc_name', '') or '')
    if not expected_project or active_name != expected_project:
        raise PowerFactoryMetadataError(
            f'Proyecto activo {active_name!r} no coincide con el recién importado '
            f'{expected_project!r}; no se asignó Alimentador.'
        )
    result = populate_feeder_metadata(app, [
        FeederAssignment(**row) for row in metadata['assignments']
    ])
    return {'status': 'assigned', 'metadata_file': sidecar.name,
            'dgs_sha256': metadata['dgs_sha256'], **result}
