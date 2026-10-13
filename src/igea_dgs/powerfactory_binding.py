"""Vínculo auditable entre la fuente canónica y un proyecto PowerFactory.

El nombre de un proyecto no demuestra que sea el que se acaba de importar. Este
módulo conserva la identidad de la ejecución fuente y una huella del inventario
nativo. La huella describe objetos, conexiones, tipos y etiquetas de alimentador;
deliberadamente no incluye P/Q, resultados ni estados operativos que los estudios
pueden modificar.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


BINDING_SCHEMA = 'igea-dgs-powerfactory-project-binding-v1'

_NATIVE_CLASSES = (
    'ElmNet', 'ElmTerm', 'ElmLne', 'ElmTr2', 'ElmTr3', 'ElmLod', 'ElmXnet',
    'ElmShnt', 'ElmCoup', 'StaSwitch', 'StaCubic', 'ElmFeeder', 'ElmSubstat',
)
_POINTER_ATTRS = (
    'bus1', 'bus2', 'bushv', 'buslv', 'busmv', 'cterm', 'obj_id', 'typ_id',
    'cpSubstat', 'fold_id',
)
_IMMUTABLE_ATTRS: dict[str, tuple[str, ...]] = {
    'ElmTerm': ('uknom', 'systype', 'phtech'),
    'ElmLne': ('dline', 'nlnum', 'inAir'),
    'ElmTr2': ('nt2ph',),
    'ElmTr3': ('nt3ph',),
    'ElmShnt': ('ctech', 'shtype', 'qcapn', 'ncapx', 'ushnm'),
    'ElmXnet': ('uknom',),
}


class ProjectBindingError(ValueError):
    """El proyecto solicitado no satisface el vínculo persistido."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f'{code}: {detail}')


def _get(obj: Any, name: str) -> Any:
    try:
        value = obj.GetAttribute(name)
    except Exception:
        value = getattr(obj, name, None)
    if value is None and name == 'p:alimentador':
        try:
            value = obj.GetUserAttribute(name)
        except Exception:
            value = getattr(obj, name, None)
    return value


def _full_name(obj: Any) -> str:
    if obj is None:
        return ''
    try:
        value = obj.GetFullName()
    except Exception:
        value = getattr(obj, 'loc_name', '')
    return str(value or '')


def _class_name(obj: Any, fallback: str = '') -> str:
    try:
        return str(obj.GetClassName() or fallback)
    except Exception:
        return fallback


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, (list, tuple, set)):
        return sorted((_canonical(item) for item in value), key=lambda item: str(item))
    full_name = _full_name(value)
    return full_name or str(value)


def _feeders(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return tuple(sorted({str(item).strip() for item in values if str(item).strip()}))


def native_inventory_records(app: Any, feeders: Iterable[str]) -> list[dict[str, Any]]:
    """Inventario estable del proyecto activo, sin P/Q ni resultados calculados."""
    selected = {str(item).strip() for item in feeders if str(item).strip()}
    by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for class_name in _NATIVE_CLASSES:
        try:
            objects = list(app.GetCalcRelevantObjects(f'*.{class_name}') or [])
        except Exception:
            objects = []
        for obj in objects:
            actual_class = _class_name(obj, class_name)
            full_name = _full_name(obj)
            if not full_name:
                continue
            labels = _feeders(_get(obj, 'p:alimentador'))
            # Un objeto explícitamente rotulado para otro alimentador no pertenece al
            # alcance. Los objetos sin rótulo siguen dentro: quitárselo no puede
            # esconder una alteración topológica.
            if selected and labels and not selected.intersection(labels):
                continue
            record: dict[str, Any] = {
                'class': actual_class,
                'full_name': full_name,
                'feeders': list(labels),
                'connections': {},
                'equipment': {},
            }
            for name in _POINTER_ATTRS:
                value = _get(obj, name)
                if value is not None:
                    record['connections'][name] = _canonical(value)
            for name in _IMMUTABLE_ATTRS.get(actual_class, ()):
                value = _get(obj, name)
                if value is not None:
                    record['equipment'][name] = _canonical(value)
            by_identity[(actual_class, full_name)] = record
    return [by_identity[key] for key in sorted(by_identity)]


def native_inventory_sha256(app: Any, feeders: Iterable[str]) -> str:
    payload = {
        'schema': 'igea-dgs-native-inventory-v1',
        'feeders': sorted({str(item).strip() for item in feeders if str(item).strip()}),
        'objects': native_inventory_records(app, feeders),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class PowerFactoryProjectBinding:
    project: str
    folder: str
    source_run_id: str
    source_mode: str
    source_fingerprint: str
    feeders: tuple[str, ...]
    dgs_sha256: dict[str, str]
    native_inventory_sha256: str
    native_reread: dict[str, Any]
    accepted_at: float = field(default_factory=time.time)
    schema_version: str = BINDING_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, 'feeders', tuple(sorted(set(self.feeders))))

    @property
    def binding_sha256(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result['feeders'] = list(self.feeders)
        result['binding_sha256'] = self.binding_sha256
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'PowerFactoryProjectBinding':
        result = cls(
            project=str(value['project']),
            folder=str(value.get('folder') or ''),
            source_run_id=str(value['source_run_id']),
            source_mode=str(value['source_mode']),
            source_fingerprint=str(value['source_fingerprint']),
            feeders=tuple(str(item) for item in value.get('feeders') or []),
            dgs_sha256={str(k): str(v) for k, v in (value.get('dgs_sha256') or {}).items()},
            native_inventory_sha256=str(value['native_inventory_sha256']),
            native_reread=dict(value.get('native_reread') or {}),
            accepted_at=float(value.get('accepted_at') or 0.0),
            schema_version=str(value.get('schema_version') or BINDING_SCHEMA),
        )
        if result.schema_version != BINDING_SCHEMA:
            raise ProjectBindingError(
                'PROJECT_BINDING_SCHEMA_MISMATCH', result.schema_version,
            )
        recorded_hash = str(value.get('binding_sha256') or '')
        if recorded_hash and recorded_hash != result.binding_sha256:
            raise ProjectBindingError(
                'PROJECT_BINDING_RECORD_MISMATCH',
                'la evidencia persistida fue modificada después de su aceptación',
            )
        return result


def record_project_binding(ws: Any, binding: PowerFactoryProjectBinding) -> None:
    """Guarda el vínculo bajo el mismo bloqueo y escritura atómica del workspace."""
    with ws.lock:
        ws.pf_project_bindings[binding.project] = binding.as_dict()
        ws.save()


def _active_source_identity(ws: Any) -> tuple[str | None, str | None, str | None]:
    return (
        getattr(ws, 'active_run_id', None),
        getattr(ws, 'loaded_source_mode', None),
        getattr(ws, 'loaded_source_fingerprint', None),
    )


def require_project_binding(
    ws: Any,
    project: str,
    feeders: Iterable[str],
) -> PowerFactoryProjectBinding:
    """Exige el proyecto exacto de la ejecución activa antes de una acción nativa."""
    project = str(project or '').strip()
    requested = {str(item).strip() for item in feeders if str(item).strip()}
    raw = (getattr(ws, 'pf_project_bindings', {}) or {}).get(project)
    if not raw:
        raise ProjectBindingError(
            'PROJECT_BINDING_MISSING',
            f'el proyecto {project!r} no fue aceptado para la ejecución fuente activa',
        )
    binding = PowerFactoryProjectBinding.from_dict(raw)
    active = _active_source_identity(ws)
    expected = (
        binding.source_run_id, binding.source_mode, binding.source_fingerprint,
    )
    if active != expected:
        raise ProjectBindingError(
            'PROJECT_BINDING_SOURCE_MISMATCH',
            f'el vínculo pertenece a {binding.source_run_id!r} y la fuente activa es {active[0]!r}',
        )
    if not requested or not requested.issubset(set(binding.feeders)):
        raise ProjectBindingError(
            'PROJECT_BINDING_FEEDER_MISMATCH',
            f'{sorted(requested)} no es subconjunto de {list(binding.feeders)}',
        )

    inventory = getattr(ws, 'pf_inventory', {}) or {}
    projects = inventory.get('projects') or []
    current = next(
        (item for item in projects if str(item.get('path') or item.get('name') or '') == project),
        None,
    )
    if projects and current is None:
        raise ProjectBindingError(
            'PROJECT_BINDING_PROJECT_MISMATCH',
            f'el proyecto vinculado {project!r} no aparece en la última relectura nativa',
        )
    if current is not None:
        native_warning = str(current.get('native_warning') or '')
        if native_warning:
            raise ProjectBindingError(
                'PROJECT_BINDING_NATIVE_UNREADABLE', native_warning,
            )
        current_feeders = {str(item) for item in current.get('feeders') or []}
        if not requested.issubset(current_feeders):
            raise ProjectBindingError(
                'PROJECT_BINDING_FEEDER_MISMATCH',
                'la última relectura nativa ya no contiene todos los alimentadores solicitados',
            )
        current_hash = str(current.get('native_inventory_sha256') or '')
        if 'native_inventory_sha256' in current and not current_hash:
            raise ProjectBindingError(
                'PROJECT_BINDING_NATIVE_UNREADABLE',
                'la última lectura no produjo una huella del inventario nativo',
            )
        if current_hash and current_hash != binding.native_inventory_sha256:
            raise ProjectBindingError(
                'PROJECT_BINDING_NATIVE_MISMATCH',
                'la topología o identidad de equipos cambió desde la aceptación nativa',
            )
    return binding
