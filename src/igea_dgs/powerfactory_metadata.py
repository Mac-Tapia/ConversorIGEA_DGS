"""Asignación verificable de procedencia IGEA en objetos PowerFactory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

ATTRIBUTE = 'p:alimentador'
CONFIGURATION = 'Trazabilidad IGEA'
TARGET_CLASSES = ('ElmLod', 'ElmSubstat', 'ElmSym', 'ElmXnet')


@dataclass(frozen=True)
class RuntimeObjectIdentity:
    class_name: str
    loc_name: str
    terminal: str
    substation: str


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
    return RuntimeObjectIdentity(class_name, loc_name, terminal, substation)


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
    for obj in objects:
        identity = build_runtime_identity(obj)
        runtime.setdefault(identity, []).append(obj)

    plan: list[PlannedAssignment] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for record in records:
        identity = RuntimeObjectIdentity(
            record.class_name,
            str(record.loc_name or '').strip(),
            str(record.terminal or '').strip(),
            str(record.substation or '').strip(),
        )
        candidates = runtime.get(identity, [])
        label = f'{record.class_name} {record.loc_name} [{record.terminal}/{record.substation}]'
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
