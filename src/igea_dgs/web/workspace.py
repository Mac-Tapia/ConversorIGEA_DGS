"""Espacio de trabajo: las entradas, las opciones y la salida de una sesión web.

Hace lo que en la GUI de escritorio hacían los campos de la ventana más
``settings.py``, con una diferencia de fondo: **cada espacio tiene su carpeta**. Dos
personas con el navegador abierto no comparten ni entradas ni salida, y un espacio
se puede reabrir al día siguiente con lo que se eligió.

Lo que se guarda en disco (``workspace.json``) son las rutas y las opciones. El
dataset leído vive solo en memoria: son cientos de MB de objetos Python y releer los
TXT tarda segundos. Si el servidor se reinicia, basta volver a pulsar «Cargar».

Las reglas de ``settings.py`` se mantienen:

* una ruta solo se restaura si el fichero sigue existiendo;
* «convertir TODOS» no es una opción guardada: es la acción, no una preferencia.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..identify import CARGA, EQUIPOS, RED
from ..powerfactory_env import project_root
from .jobs import EventLog

#: Casillas de entrada. ``grupo`` decide con qué alternativa se usa cada una y
#: ``tipo`` el contenido que se comprueba al elegirla (``identify``).
SLOTS: dict[str, dict[str, Any]] = {
    'red': {'grupo': 'txt', 'tipo': RED, 'etiqueta': 'RED — topología (nodos, tramos, fuentes)',
            'obligatorio': True},
    'loads': {'grupo': 'txt', 'tipo': CARGA, 'etiqueta': 'CARGA — demanda por cliente',
              'obligatorio': True},
    'equipment': {'grupo': 'txt', 'tipo': EQUIPOS,
                  'etiqueta': 'EQUIPOS — catálogo de conductores y cables', 'obligatorio': True},
    # Cuando la entrega trae un catálogo incompleto —pasó: 9 tipos frente a los 43
    # que usaba la red— sin esto el 100 % de los tramos toma la impedancia de DEFAULT
    # y el modelo converge igual, sin que nada lo delate.
    'equipment_extra': {'grupo': 'txt', 'tipo': EQUIPOS,
                        'etiqueta': 'EQUIPOS complementario (opcional)', 'obligatorio': False},
    'mdb': {'grupo': 'mdb', 'tipo': None, 'etiqueta': 'Base de red (.mdb)', 'obligatorio': True},
    'equipment_mdb': {'grupo': 'mdb', 'tipo': None,
                      'etiqueta': 'Base de equipos (.mdb, si está aparte)', 'obligatorio': False},
    'study': {'grupo': 'mdb', 'tipo': None,
              'etiqueta': 'Estudio o proyecto (.zxst, opcional)', 'obligatorio': False},
    'aliases': {'grupo': 'comun', 'tipo': None,
                'etiqueta': 'Aliases de tipos (JSON, opcional)', 'obligatorio': False},
}

DEFAULT_OPTIONS: dict[str, Any] = {
    'input_mode': 'txt',
    'source_crs': 'EPSG:32718',
    'target_crs': 'EPSG:4326',
    'include_geography': True,
    'strict': True,
    'write_preview': False,
    'export_xlsx': False,
    'export_tsv': False,
    # Procesos para convertir alimentadores a la vez: 0 automático, 1 en serie.
    'workers': 0,
    # AUTO conserva 2,08 unidades/metro y hace crecer el lienzo con la red.
    'hoja': 'AUTO',
}

TEXT_OPTIONS = ('input_mode', 'source_crs', 'target_crs', 'hoja')
BOOL_OPTIONS = ('include_geography', 'strict', 'write_preview', 'export_xlsx', 'export_tsv')
#: Tope del selector de procesos. Más allá no se gana (ver batch.AUTO_WORKERS_MAX) y
#: cada proceso guarda una copia del dataset en memoria.
MAX_WORKERS = 16

_ID_RE = re.compile(r'^[a-f0-9]{8,32}$')
_SAFE_NAME = re.compile(r'[^A-Za-z0-9._() \-]+')


def data_root() -> Path:
    """Dónde viven los espacios. ``output/`` ya está fuera del control de versiones."""
    env = os.environ.get('IGEA_WEB_DATA', '').strip()
    return Path(env) if env else project_root() / 'output' / 'web'


def safe_filename(name: str) -> str:
    base = Path(name or 'fichero').name
    cleaned = _SAFE_NAME.sub('_', base).strip(' .')
    return cleaned or 'fichero'


@dataclass
class Workspace:
    id: str
    root: Path
    created_at: float = field(default_factory=time.time)
    options: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_OPTIONS))
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog_file: str | None = None
    conversions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # DGS de red unida (varios alimentadores en uno), por nombre.
    groups: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Proyecto de PowerFactory creado al importar cada DGS (por nombre del DGS). Las
    # actualizaciones de cargas y las SED nuevas se aplican sobre ese proyecto.
    pf_projects: dict[str, str] = field(default_factory=dict)
    # --- solo en memoria
    dataset: Any = None
    inventory: dict | None = None
    catalog_report: dict | None = None
    loaded_at: float | None = None
    plans: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: EventLog = field(default_factory=EventLog)
    lock: threading.RLock = field(default_factory=threading.RLock)
    _corrections_cache: tuple[float, Any] | None = None

    # -------------------------------------------------------------- carpetas
    @property
    def inputs_dir(self) -> Path:
        return self.root / 'entradas'

    @property
    def out_dir(self) -> Path:
        return self.root / 'salida'

    @property
    def plans_dir(self) -> Path:
        return self.root / 'planes'

    # -------------------------------------------------------------- persistencia
    def save(self) -> None:
        payload = {
            'version': 1,
            'id': self.id,
            'created_at': self.created_at,
            'options': self.options,
            'inputs': self.inputs,
            'catalog_file': self.catalog_file,
            'groups': self.groups,
            'pf_projects': self.pf_projects,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / 'workspace.json.tmp'
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        tmp.replace(self.root / 'workspace.json')
        (self.root / 'conversiones.json').write_text(
            json.dumps(self.conversions, indent=2, ensure_ascii=False), encoding='utf-8')

    @classmethod
    def load(cls, root: Path) -> 'Workspace':
        data = json.loads((root / 'workspace.json').read_text(encoding='utf-8'))
        ws = cls(id=data['id'], root=root, created_at=data.get('created_at', time.time()))
        options = dict(DEFAULT_OPTIONS)
        options.update({k: v for k, v in (data.get('options') or {}).items()
                        if k in DEFAULT_OPTIONS})
        ws.options = options
        # Una ruta que ya no existe no se restaura: el campo queda vacío en lugar de
        # apuntar a la nada y fallar cuando alguien pulse convertir.
        ws.inputs = {slot: meta for slot, meta in (data.get('inputs') or {}).items()
                     if slot in SLOTS and Path(meta.get('path', '')).is_file()}
        catalog = data.get('catalog_file')
        ws.catalog_file = catalog if catalog and Path(catalog).is_file() else None
        ws.groups = dict(data.get('groups') or {})
        ws.pf_projects = dict(data.get('pf_projects') or {})
        conv = root / 'conversiones.json'
        if conv.is_file():
            try:
                ws.conversions = json.loads(conv.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                ws.conversions = {}
        return ws

    # -------------------------------------------------------------- entradas
    def invalidate(self) -> None:
        """Otra entrada = otro dataset. Lo leído deja de valer, y los planes también."""
        self.dataset = None
        self.inventory = None
        self.catalog_report = None
        self.loaded_at = None
        self.plans.clear()

    def set_input(self, slot: str, path: Path, *, origin: str, warning: str = '') -> dict:
        meta = {
            'path': str(path),
            'name': path.name,
            'size': path.stat().st_size,
            'origin': origin,
            'warning': warning,
            'set_at': time.time(),
        }
        with self.lock:
            old = self.inputs.get(slot)
            self.inputs[slot] = meta
            self.invalidate()
            self._drop_upload(old, keep=path)
            self.save()
        return meta

    def clear_input(self, slot: str) -> None:
        with self.lock:
            old = self.inputs.pop(slot, None)
            self.invalidate()
            self._drop_upload(old)
            self.save()

    def _drop_upload(self, meta: dict | None, keep: Path | None = None) -> None:
        """Borra un fichero subido que ya no usa nadie. Nunca uno del servidor."""
        if not meta or meta.get('origin') != 'upload':
            return
        old = Path(meta['path'])
        if keep is not None and old.resolve() == keep.resolve():
            return
        if self.inputs_dir.resolve() in old.resolve().parents:
            try:
                old.unlink()
            except OSError:
                pass

    def upload_target(self, slot: str, filename: str) -> Path:
        folder = self.inputs_dir / slot
        folder.mkdir(parents=True, exist_ok=True)
        return folder / safe_filename(filename)

    def input_path(self, slot: str) -> str:
        meta = self.inputs.get(slot)
        return meta['path'] if meta else ''

    def missing_inputs(self) -> list[str]:
        mode = self.options.get('input_mode', 'txt')
        return [SLOTS[s]['etiqueta'] for s, spec in SLOTS.items()
                if spec['grupo'] == mode and spec['obligatorio'] and not self.input_path(s)]

    # -------------------------------------------------------------- catálogo
    def catalog_corrections(self) -> dict | None:
        """Correcciones del catálogo aplicado, leídas una vez por versión del fichero."""
        if not self.catalog_file:
            return None
        path = Path(self.catalog_file)
        if not path.is_file():
            return None
        mtime = path.stat().st_mtime
        if self._corrections_cache and self._corrections_cache[0] == mtime:
            return self._corrections_cache[1]
        from ..catalog import leer_catalogo

        corrections = leer_catalogo(path)
        self._corrections_cache = (mtime, corrections)
        return corrections

    # -------------------------------------------------------------- conversiones
    def record_conversions(self, manifest: dict) -> None:
        """Estado por alimentador, acumulado entre lotes.

        ``batch_manifest.json`` se reescribe en cada lote; si se convierten SE101 y
        luego SE102, el manifiesto solo recuerda SE102. Aquí se acumula para que la
        tabla sepa qué alimentadores tienen ya su DGS.
        """
        with self.lock:
            for item in manifest.get('feeders', []):
                key = item.get('network_id') or item.get('feeder')
                if key:
                    self.conversions[key] = {**item, 'converted_at': time.time()}
            self.save()

    # -------------------------------------------------------------- vista pública
    def public(self) -> dict:
        inv = self.inventory or {}
        return {
            'id': self.id,
            'created_at': self.created_at,
            'options': self.options,
            'inputs': self.inputs,
            'missing_inputs': self.missing_inputs(),
            'loaded': self.dataset is not None,
            'loaded_at': self.loaded_at,
            'totals': inv.get('totals'),
            'conversion': inv.get('conversion'),
            'integrity': inv.get('integrity'),
            'catalog_report': self.catalog_report,
            'catalog_applied': bool(self.catalog_file),
            'catalog_file': Path(self.catalog_file).name if self.catalog_file else None,
            'converted': sum(1 for c in self.conversions.values() if c.get('status') == 'ok'),
            'groups': list(self.groups.values()),
            'pf_projects': self.pf_projects,
            'last_seq': self.events.last_seq,
        }


class WorkspaceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_root()
        self._items: dict[str, Workspace] = {}
        self._lock = threading.Lock()

    def create(self) -> Workspace:
        wid = uuid.uuid4().hex[:16]
        ws = Workspace(id=wid, root=self.root / wid)
        ws.out_dir.mkdir(parents=True, exist_ok=True)
        ws.save()
        with self._lock:
            self._items[wid] = ws
        return ws

    def get(self, wid: str) -> Workspace | None:
        if not _ID_RE.match(wid or ''):
            return None
        with self._lock:
            ws = self._items.get(wid)
            if ws is not None:
                return ws
            folder = self.root / wid
            if not (folder / 'workspace.json').is_file():
                return None
            try:
                ws = Workspace.load(folder)
            except (OSError, ValueError, KeyError):
                return None
            self._items[wid] = ws
            return ws

    def list(self) -> list[dict]:
        out = []
        if not self.root.is_dir():
            return out
        for folder in self.root.iterdir():
            meta = folder / 'workspace.json'
            if not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            out.append({
                'id': data.get('id', folder.name),
                'created_at': data.get('created_at'),
                'inputs': {k: v.get('name') for k, v in (data.get('inputs') or {}).items()},
                'modified_at': meta.stat().st_mtime,
            })
        return sorted(out, key=lambda d: d['modified_at'], reverse=True)

    def delete(self, wid: str) -> bool:
        ws = self.get(wid)
        if ws is None:
            return False
        with self._lock:
            self._items.pop(wid, None)
        shutil.rmtree(ws.root, ignore_errors=True)
        return True
