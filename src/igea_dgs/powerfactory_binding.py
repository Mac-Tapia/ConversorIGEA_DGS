"""Vínculo auditable y flexible entre la fuente canónica y PowerFactory.

El nombre de un proyecto no demuestra que sea el que se acaba de importar. Este
módulo conserva la identidad de la ejecución fuente y una huella del inventario
nativo. La huella describe objetos, conexiones, tipos y etiquetas de alimentador;
deliberadamente no incluye P/Q, resultados ni estados operativos que los estudios
pueden modificar. Una recarga equivalente o una modificación manual legible se
informa como evolución del proyecto y no impide trabajar; se bloquea solo cuando ya
no puede demostrarse la fuente, el proyecto o el alimentador solicitado.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
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


# Registro de vínculos compartido entre espacios de trabajo (spec 018, RF-1, RF-2, RF-8).
# Un proyecto de DIgSILENT vive en una carpeta común a todos los espacios; su vínculo no
# puede depender de qué espacio lo aceptó. Un único proceso de la web lo escribe, así que
# un bloqueo de hilos basta; con varios procesos habría que pasar a un bloqueo de fichero.
REGISTRO_SCHEMA = 'igea-dgs-powerfactory-vinculos-v1'
_REGISTRO_LOCK = threading.Lock()


def _leer_registro(path: Path) -> dict[str, dict[str, Any]]:
    """Lee el registro compartido. Sin lock: el llamador lo toma.

    Un registro ilegible bloquea en vez de vaciarse: vaciarlo haría que todos los proyectos
    aparecieran a la vez como «no aceptados», sin una causa visible para el operador.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ProjectBindingError(
            'PROJECT_BINDING_REGISTRY_UNREADABLE', f'{path.name} no se puede leer: {exc}',
        ) from exc
    if (not isinstance(data, dict) or data.get('schema') != REGISTRO_SCHEMA
            or not isinstance(data.get('vinculos'), dict)):
        raise ProjectBindingError(
            'PROJECT_BINDING_REGISTRY_UNREADABLE', f'{path.name} no tiene el esquema esperado',
        )
    return dict(data['vinculos'])


def _escribir_registro(path: Path, vinculos: dict[str, dict[str, Any]]) -> None:
    """Escritura atómica: un fallo a mitad deja el registro anterior, no uno a medias."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    payload = {'schema': REGISTRO_SCHEMA, 'vinculos': vinculos}
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
                   encoding='utf-8')
    os.replace(tmp, path)


def sembrar_registro(path: Path, vinculos_por_espacio: Iterable[Any]) -> dict[str, int]:
    """Lleva al registro compartido los vínculos que ya tenían los espacios (spec 018, RF-8).

    Sin esto, un proyecto aceptado antes de la spec 018 seguiría bloqueado en todos los
    espacios salvo en el que se aceptó. Cada vínculo se valida con su propia huella: uno
    alterado se descarta y se cuenta. Si un mismo proyecto tiene vínculos distintos, gana el
    aceptado más tarde. Es idempotente: una segunda siembra no cambia nada.
    """
    resumen = {'añadidos': 0, 'actualizados': 0, 'iguales': 0, 'descartados': 0}
    with _REGISTRO_LOCK:
        vinculos = _leer_registro(path)
        cambio = False
        for crudos in vinculos_por_espacio:
            for proyecto, raw in dict(crudos or {}).items():
                try:
                    binding = PowerFactoryProjectBinding.from_dict(raw)
                except (KeyError, TypeError, ValueError):
                    resumen['descartados'] += 1
                    continue
                actual = vinculos.get(proyecto)
                if actual is None:
                    vinculos[proyecto] = binding.as_dict()
                    resumen['añadidos'] += 1
                    cambio = True
                elif actual.get('binding_sha256') == binding.binding_sha256:
                    resumen['iguales'] += 1
                elif binding.accepted_at > float(actual.get('accepted_at') or 0.0):
                    vinculos[proyecto] = binding.as_dict()
                    resumen['actualizados'] += 1
                    cambio = True
        if cambio:
            _escribir_registro(path, vinculos)
    return resumen


def vinculo_guardado(ws: Any, project: str) -> dict[str, Any] | None:
    """Vínculo de un proyecto para este espacio (spec 018, RF-1 y RF-2).

    El registro compartido manda: una aceptación en cualquier espacio llega a todos, y una
    copia antigua del propio espacio no puede contradecirla. La copia del espacio solo
    responde cuando el registro no tiene el proyecto (espacios de antes de la spec 018).
    Si el registro es ilegible, lanza ``ProjectBindingError``: nunca se cae a la copia.
    """
    project = str(project or '').strip()
    registro = getattr(ws, 'vinculos_compartidos', None)
    if registro is not None:
        with _REGISTRO_LOCK:
            entrada = _leer_registro(Path(registro)).get(project)
        if entrada:
            return entrada
    return (getattr(ws, 'pf_project_bindings', {}) or {}).get(project)


def alimentadores_vinculados(ws: Any, project: str) -> list[str]:
    """Alimentadores del vínculo, o ninguno si el registro no se puede leer.

    Sin excepción aquí: quien lo usa para elegir qué alimentadores pedir decide mal si
    falla; el control de verdad es ``require_project_binding``, que sí lanza.
    """
    try:
        raw = vinculo_guardado(ws, project) or {}
    except ProjectBindingError:
        return []
    return [str(f) for f in raw.get('feeders') or [] if str(f).strip()]


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


def alimentadores_de_rotulos(rotulos: Iterable[str]) -> set[str]:
    """Los alimentadores de los rótulos del vínculo, con los de una barra de SET separados.

    La red externa de una barra de SET la comparten sus alimentadores y se rotula con todos,
    «PI101 + PI102 + PI103 + PI116» (022:RF-11). En el sistema Pisco (2026-10-18), PI101 y
    SI114 solo salían en esos rótulos y el plan de la calibración se rechazaba.
    """
    return {parte.strip() for rotulo in rotulos for parte in str(rotulo).split(' + ')
            if parte.strip()}

def native_inventory_sha256(app: Any, feeders: Iterable[str]) -> str:
    digest, _manifest = native_inventory_evidence(app, feeders)
    return digest


def native_inventory_evidence(
    app: Any, feeders: Iterable[str],
) -> tuple[str, list[dict[str, str]]]:
    """Devuelve huella global y manifiesto compacto para explicar cambios manuales."""
    normalized = sorted({str(item).strip() for item in feeders if str(item).strip()})
    records = native_inventory_records(app, normalized)
    payload = {
        'schema': 'igea-dgs-native-inventory-v1',
        'feeders': normalized,
        'objects': records,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    manifest = []
    for record in records:
        serialized = json.dumps(
            record, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
        ).encode('utf-8')
        manifest.append({
            'class': str(record['class']),
            'full_name': str(record['full_name']),
            'sha256': hashlib.sha256(serialized).hexdigest(),
        })
    return hashlib.sha256(raw.encode('utf-8')).hexdigest(), manifest


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
    """Guarda el vínculo en el registro compartido y en la copia del espacio.

    Primero el registro: si falla (p. ej. ilegible), el espacio no queda con una copia que
    el registro no tiene. Sin registro configurado (pruebas, CLI) solo escribe la copia.
    """
    registro = getattr(ws, 'vinculos_compartidos', None)
    if registro is not None:
        with _REGISTRO_LOCK:
            path = Path(registro)
            vinculos = _leer_registro(path)
            vinculos[binding.project] = binding.as_dict()
            _escribir_registro(path, vinculos)
    with ws.lock:
        ws.pf_project_bindings[binding.project] = binding.as_dict()
        ws.save()


def fusionar_caso_base(
    anterior: dict[str, Any] | None, binding: PowerFactoryProjectBinding,
) -> PowerFactoryProjectBinding:
    """Conserva el estado del «Caso base» de los alimentadores que no se volvieron a verificar.

    Spec 015, RF-14: se verifica alimentador por alimentador y el vínculo es uno por
    proyecto; sin fusionar, verificar PE104 borraría el estado de CA101. Solo se fusiona
    con un vínculo de la misma fuente; otra fuente es otro modelo y empieza de cero.
    """
    if not anterior or anterior.get('source_fingerprint') != binding.source_fingerprint:
        return binding
    previo = dict((anterior.get('native_reread') or {}).get('caso_base') or {})
    nuevo = dict(binding.native_reread.get('caso_base') or {})
    feeders = tuple(sorted(set(binding.feeders) | set(anterior.get('feeders') or [])))
    return PowerFactoryProjectBinding(
        project=binding.project, folder=binding.folder,
        source_run_id=binding.source_run_id, source_mode=binding.source_mode,
        source_fingerprint=binding.source_fingerprint, feeders=feeders,
        dgs_sha256={**dict(anterior.get('dgs_sha256') or {}), **binding.dgs_sha256},
        native_inventory_sha256=binding.native_inventory_sha256,
        native_reread={**binding.native_reread, 'caso_base': {**previo, **nuevo}},
        accepted_at=binding.accepted_at,
    )


def caso_base_verificado(ws: Any, project: str, feeders: Iterable[str]) -> dict[str, list[str]]:
    """Alimentador → comprobaciones que fallan en su «Caso base»; vacío si todos pasan.

    Spec 015, RF-13: sin «Caso base» verificado no se calibra ni se crea «Sin proyecto».
    Un vínculo de antes de la spec 015 no trae ``caso_base`` (CA101, 2026-10-13, adoptado
    sin GPS ni convergencia y promovido por el ajuste): cuenta como no verificado y hay
    que volver a verificarlo.
    """
    try:
        raw = vinculo_guardado(ws, str(project or '').strip()) or {}
    except ProjectBindingError as exc:
        # Registro ilegible: nada está verificado a ciencia cierta; se dice por qué.
        return {str(f).strip(): [exc.code] for f in feeders}
    estados = ((raw.get('native_reread') or {}).get('caso_base') or {})
    # 022:RF-52: un alimentador sin cargas solo está en el rótulo de su barra de SET
    # («CA101 + CA103 + …»); vale el estado de ese rótulo (CA103 y TM101 en Chincha,
    # 2026-10-18, salían «sin verificar» con el sistema verificado).
    for rotulo, estado in list(estados.items()):
        for parte in alimentadores_de_rotulos([rotulo]):
            estados.setdefault(parte, estado)
    out: dict[str, list[str]] = {}
    for feeder in feeders:
        estado = estados.get(str(feeder).strip()) or {}
        if estado.get('status') != 'VERIFICADO':
            out[str(feeder).strip()] = list(estado.get('fallos') or ['sin verificar'])
    return out


def _active_source_identity(ws: Any) -> tuple[str | None, str | None, str | None]:
    run_id = getattr(ws, 'active_run_id', None)
    mode = getattr(ws, 'loaded_source_mode', None)
    fingerprint = getattr(ws, 'loaded_source_fingerprint', None)
    # El modo y la huella cargados solo viven en memoria; ``active_run_id`` se guarda en
    # disco. El 2026-10-14, tras reiniciar la web, CA101 quedó bloqueado con
    # PROJECT_BINDING_SOURCE_MISMATCH frente a la misma .mdb: la pestaña de cargas no
    # vuelve a cargar la fuente. El manifiesto de la ejecución activa es inmutable y
    # dice lo mismo que la carga en memoria.
    if (mode is None or fingerprint is None
            or getattr(ws, 'loaded_run_id', None) != run_id):
        active_run = getattr(ws, 'active_run', None)
        snapshot = active_run() if callable(active_run) else None
        if snapshot is not None:
            return snapshot.run_id, snapshot.mode, snapshot.fingerprint
    return run_id, mode, fingerprint


def _current_project(ws: Any, project: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    inventory = getattr(ws, 'pf_inventory', {}) or {}
    projects = list(inventory.get('projects') or [])
    current = next(
        (item for item in projects if str(item.get('path') or item.get('name') or '') == project),
        None,
    )
    return projects, current


def _manifest_index(items: Any) -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        class_name = str(item.get('class') or '').strip()
        full_name = str(item.get('full_name') or '').strip()
        digest = str(item.get('sha256') or '').strip()
        if class_name and full_name and digest:
            index[(class_name, full_name)] = digest
    return index


def _modified_elements(before: Any, after: Any) -> list[dict[str, str]]:
    previous = _manifest_index(before)
    current = _manifest_index(after)
    elements: list[dict[str, str]] = []
    for class_name, full_name in sorted(current.keys() - previous.keys()):
        elements.append({'change': 'added', 'class': class_name, 'full_name': full_name})
    for class_name, full_name in sorted(previous.keys() - current.keys()):
        elements.append({'change': 'removed', 'class': class_name, 'full_name': full_name})
    for class_name, full_name in sorted(previous.keys() & current.keys()):
        if previous[(class_name, full_name)] != current[(class_name, full_name)]:
            elements.append({'change': 'modified', 'class': class_name, 'full_name': full_name})
    return elements


def require_project_binding(
    ws: Any,
    project: str,
    feeders: Iterable[str],
) -> PowerFactoryProjectBinding:
    """Exige identidad suficiente; la evolución manual legible queda como aviso."""
    project = str(project or '').strip()
    requested = {str(item).strip() for item in feeders if str(item).strip()}
    raw = vinculo_guardado(ws, project)
    if not raw:
        raise ProjectBindingError(
            'PROJECT_BINDING_MISSING',
            f'el proyecto {project!r} no fue aceptado para la ejecución fuente activa',
        )
    binding = PowerFactoryProjectBinding.from_dict(raw)
    active = _active_source_identity(ws)
    # El vínculo vive en cada espacio de trabajo (workspace.json), no en la carpeta de
    # DIgSILENT, que es compartida. Un espacio sin fuente activa no puede demostrar la
    # procedencia: se dice así, en vez de un «fuente activa None» que parece un desajuste.
    if active[0] is None:
        raise ProjectBindingError(
            'PROJECT_BINDING_NO_ACTIVE_SOURCE',
            'este espacio de trabajo no tiene una ejecución fuente activa; cargue y convierta '
            'la fuente antes de usar proyectos de DIgSILENT',
        )
    if active[1:] != (binding.source_mode, binding.source_fingerprint):
        raise ProjectBindingError(
            'PROJECT_BINDING_SOURCE_MISMATCH',
            f'el vínculo pertenece a {binding.source_run_id!r} y la fuente activa es {active[0]!r}',
        )
    if not requested or not requested.issubset(alimentadores_de_rotulos(binding.feeders)):
        raise ProjectBindingError(
            'PROJECT_BINDING_FEEDER_MISMATCH',
            f'{sorted(requested)} no es subconjunto de {list(binding.feeders)}',
        )
    # Spec 018, RF-4: el mismo nombre de proyecto en otra carpeta de DIgSILENT es otro
    # proyecto. Solo se compara si las dos partes dicen su carpeta.
    carpeta_actual = str((getattr(ws, 'pf_inventory', {}) or {}).get('folder') or '').strip()
    if carpeta_actual and binding.folder and carpeta_actual != binding.folder:
        raise ProjectBindingError(
            'PROJECT_BINDING_FOLDER_MISMATCH',
            f'el vínculo es de la carpeta {binding.folder!r} y la carpeta actual es '
            f'{carpeta_actual!r}',
        )

    projects, current = _current_project(ws, project)
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
        current_feeders = alimentadores_de_rotulos(current.get('feeders') or [])
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
    return binding


def project_binding_warnings(
    ws: Any,
    project: str,
    feeders: Iterable[str],
) -> list[dict[str, Any]]:
    """Describe evolución deliberada sin convertirla en impedimento operativo."""
    binding = require_project_binding(ws, project, feeders)
    active = _active_source_identity(ws)
    warnings: list[dict[str, Any]] = []
    if active[0] != binding.source_run_id:
        warnings.append({
            'code': 'PROJECT_BINDING_SOURCE_RUN_CHANGED',
            'message': (
                f'La fuente se volvió a cargar como {active[0]!r}; conserva la misma '
                f'huella que {binding.source_run_id!r}.'
            ),
            'elements': [],
        })

    _projects, current = _current_project(ws, str(project or '').strip())
    current_hash = str((current or {}).get('native_inventory_sha256') or '')
    if current_hash and current_hash != binding.native_inventory_sha256:
        baseline = binding.native_reread.get('inventory_manifest') or []
        actual = (current or {}).get('native_inventory_manifest') or []
        warnings.append({
            'code': 'PROJECT_BINDING_NATIVE_MODIFIED',
            'message': 'El proyecto contiene modificaciones manuales posteriores a su aceptación.',
            'elements': _modified_elements(baseline, actual),
        })
    return warnings
