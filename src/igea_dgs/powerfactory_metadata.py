"""Creación y acceso a la Data Extension ``Alimentador`` en PowerFactory."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .feeder_metadata import FeederAssignment, TARGET_CLASSES


CONFIGURATION_NAME = 'Trazabilidad IGEA'
_ATTRIBUTE_NAME = 'alimentador'
_ATTRIBUTE_DESCRIPTION = 'Alimentador'


@dataclass(frozen=True)
class RuntimeObjectIdentity:
    class_name: str
    loc_name: str
    terminal: str
    substation: str
    obj: Any = field(compare=False, repr=False)

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.class_name, self.loc_name, self.terminal, self.substation)


@dataclass(frozen=True)
class ResolvedFeederAssignment:
    record: FeederAssignment
    identity: RuntimeObjectIdentity


@dataclass(frozen=True)
class AmbiguousFeederAssignment:
    record: FeederAssignment
    candidates: tuple[RuntimeObjectIdentity, ...]


@dataclass(frozen=True)
class ResolutionPlan:
    resolved: tuple[ResolvedFeederAssignment, ...]
    unresolved: tuple[FeederAssignment, ...]
    ambiguous: tuple[AmbiguousFeederAssignment, ...]

    @property
    def ok(self) -> bool:
        return not self.unresolved and not self.ambiguous


def data_extension_attribute_name() -> str:
    """Devuelve el nombre calificado que exponen los objetos de PowerFactory."""

    return f'p:{_ATTRIBUTE_NAME}'


def _pf_attribute(obj: Any, name: str, default: Any = None) -> Any:
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


def _pf_class_name(obj: Any) -> str:
    try:
        return str(obj.GetClassName() or '').strip()
    except Exception:
        return ''


def _pf_name(obj: Any) -> str:
    return str(_pf_attribute(obj, 'loc_name', '') or '').strip()


def _pf_parent(obj: Any) -> Any:
    try:
        return obj.GetParent()
    except Exception:
        return None


def _terminal_for(obj: Any) -> Any:
    cubicle = _pf_attribute(obj, 'bus1')
    if cubicle is None:
        for method_name in ('GetCubicle', 'GetBus'):
            try:
                cubicle = getattr(obj, method_name)(0)
            except Exception:
                cubicle = None
            if cubicle is not None:
                break
    if cubicle is None:
        return None
    terminal = _pf_attribute(cubicle, 'cterm')
    if terminal is not None:
        return terminal
    parent = _pf_parent(cubicle)
    return parent if _pf_class_name(parent) == 'ElmTerm' else None


def _substation_for(obj: Any, terminal: Any) -> Any:
    direct = _pf_attribute(terminal, 'cpSubstat')
    if direct is not None:
        return direct
    for start in (terminal, obj):
        current = _pf_parent(start)
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            if _pf_class_name(current) == 'ElmSubstat':
                return current
            current = _pf_parent(current)
    return None


def build_runtime_identity(obj: Any) -> RuntimeObjectIdentity:
    """Construye la identidad eléctrica exacta usada por el manifiesto DGS."""

    terminal = _terminal_for(obj)
    substation = _substation_for(obj, terminal)
    return RuntimeObjectIdentity(
        class_name=_pf_class_name(obj),
        loc_name=_pf_name(obj),
        terminal=_pf_name(terminal),
        substation=_pf_name(substation),
        obj=obj,
    )


def resolve_feeder_assignments(
    records: Iterable[FeederAssignment],
    objects: Iterable[Any],
) -> ResolutionPlan:
    """Resuelve el lote completo sin escribir ningún objeto de PowerFactory."""

    index: dict[tuple[str, str, str, str], list[RuntimeObjectIdentity]] = defaultdict(list)
    for obj in objects:
        identity = build_runtime_identity(obj)
        if identity.class_name in TARGET_CLASSES:
            index[identity.key].append(identity)

    resolved: list[ResolvedFeederAssignment] = []
    unresolved: list[FeederAssignment] = []
    ambiguous: list[AmbiguousFeederAssignment] = []
    for record in records:
        key = tuple(str(value).strip() for value in record.runtime_key)
        candidates = tuple(index.get(key, ()))
        if len(candidates) == 1:
            resolved.append(ResolvedFeederAssignment(record, candidates[0]))
        elif not candidates:
            unresolved.append(record)
        else:
            ambiguous.append(AmbiguousFeederAssignment(record, candidates))
    return ResolutionPlan(tuple(resolved), tuple(unresolved), tuple(ambiguous))


def _record_summary(record: FeederAssignment) -> dict[str, Any]:
    return {
        'class_name': record.class_name,
        'dgs_fid': record.dgs_fid,
        'loc_name': record.loc_name,
        'terminal': record.terminal,
        'substation': record.substation,
        'feeder': record.feeder,
    }


def _strict_set_attribute(obj: Any, attribute: str, value: Any) -> None:
    setter = getattr(obj, 'SetAttribute', None)
    if not callable(setter):
        raise RuntimeError(f'{_pf_name(obj)!r} no ofrece SetAttribute')
    result = setter(attribute, value)
    if result not in (None, 0):
        raise RuntimeError(f'SetAttribute({attribute!r}) devolvió {result!r}')


def apply_feeder_assignment_plan(
    plan: ResolutionPlan,
    attribute: str = 'p:alimentador',
) -> dict[str, Any]:
    """Aplica un plan completo y revierte el lote ante el primer fallo."""

    report: dict[str, Any] = {
        'ok': False,
        'expected': len(plan.resolved) + len(plan.unresolved) + len(plan.ambiguous),
        'assigned': 0,
        'unchanged': 0,
        'rolled_back': 0,
        'counts_by_class': {},
        'counts_by_feeder': {},
        'unresolved': [_record_summary(record) for record in plan.unresolved],
        'ambiguous': [
            {**_record_summary(item.record), 'candidate_count': len(item.candidates)}
            for item in plan.ambiguous
        ],
        'errors': [],
    }
    if not plan.ok:
        return report

    previous = [
        (item.identity.obj, _pf_attribute(item.identity.obj, attribute))
        for item in plan.resolved
    ]
    touched: list[tuple[Any, Any]] = []
    try:
        for item, (obj, old_value) in zip(plan.resolved, previous, strict=True):
            # PowerFactory 2024 exposes values created with AddString as
            # STRING_VEC (``[]`` / ``['NA203']``), despite the scalar-looking
            # AddString signature in the official example.
            encoded_value: Any = (
                [item.record.feeder] if isinstance(old_value, list) else item.record.feeder
            )
            if old_value == encoded_value:
                report['unchanged'] += 1
                continue
            _strict_set_attribute(obj, attribute, encoded_value)
            touched.append((obj, old_value))
            actual = _pf_attribute(obj, attribute)
            if actual != encoded_value:
                raise RuntimeError(
                    f'lectura posterior distinta para {item.record.loc_name!r}: {actual!r}'
                )
    except Exception as exc:
        report['errors'].append(str(exc))
        rollback_errors: list[str] = []
        for obj, old_value in reversed(touched):
            try:
                _strict_set_attribute(obj, attribute, old_value)
                report['rolled_back'] += 1
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        report['errors'].extend(f'rollback: {error}' for error in rollback_errors)
        return report

    by_class = Counter(item.record.class_name for item in plan.resolved)
    by_feeder = Counter(item.record.feeder for item in plan.resolved)
    report.update(
        ok=True,
        assigned=len(plan.resolved),
        counts_by_class=dict(sorted(by_class.items())),
        counts_by_feeder=dict(sorted(by_feeder.items())),
    )
    return report


def ensure_alimentador_data_extensions(
    project: Any,
    classes: Iterable[str] = TARGET_CLASSES,
) -> dict[str, list[Any]]:
    """Crea una sola columna ``Alimentador`` para cada clase objetivo.

    PowerFactory exige encerrar los cambios de Data Extensions entre
    ``BeginDataExtensionModification`` y ``EndDataExtensionModification``.
    Un fallo en una clase se registra sin impedir que se intenten las demás.
    """

    begin = getattr(project, 'BeginDataExtensionModification', None)
    end = getattr(project, 'EndDataExtensionModification', None)
    if project is None or not callable(begin) or not callable(end):
        raise RuntimeError(
            'No hay un proyecto activo o la API de Data Extensions no está disponible'
        )

    settings = begin()
    try:
        get_configuration = getattr(settings, 'GetConfiguration', None)
        add_configuration = getattr(settings, 'AddConfiguration', None)
        if settings is None or not callable(get_configuration) or not callable(add_configuration):
            raise RuntimeError('La API de Data Extensions no devolvió una configuración válida')

        report: dict[str, list[Any]] = {
            'created': [],
            'existing': [],
            'errors': [],
        }
        for class_name in classes:
            try:
                configuration = get_configuration(class_name, CONFIGURATION_NAME)
                if configuration is not None:
                    report['existing'].append(class_name)
                    continue

                configuration = add_configuration(class_name, CONFIGURATION_NAME)
                if configuration is None:
                    raise RuntimeError('AddConfiguration no devolvió una configuración')
                add_string = getattr(configuration, 'AddString', None)
                if not callable(add_string):
                    raise RuntimeError('La configuración no ofrece AddString')
                result = add_string(
                    _ATTRIBUTE_NAME,
                    _ATTRIBUTE_DESCRIPTION,
                    '',
                    '',
                )
                if result not in (None, 0):
                    raise RuntimeError(f'AddString devolvió {result!r}')
                report['created'].append(class_name)
            except Exception as exc:  # PowerFactory expone errores de tipos variables.
                report['errors'].append(
                    {'class_name': class_name, 'error': str(exc)}
                )
        return report
    finally:
        end()
