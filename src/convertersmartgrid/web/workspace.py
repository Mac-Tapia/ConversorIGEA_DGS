"""Espacio de trabajo: las entradas, las opciones y la salida de una sesión web.

Hace lo que en la GUI de escritorio, ya retirada, hacían los campos de la ventana y su
``settings.py``, con una diferencia de fondo: **cada espacio tiene su carpeta**. Dos
personas con el navegador abierto no comparten ni entradas ni salida, y un espacio
se puede reabrir al día siguiente con lo que se eligió.

Lo que se guarda en disco (``workspace.json``) son las rutas y las opciones. El
dataset leído vive solo en memoria: son cientos de MB de objetos Python y releer los
TXT tarda segundos. Si el servidor se reinicia, basta volver a pulsar «Cargar».

Las reglas de ``settings.py`` se mantienen, con un matiz de 086:RF-3:

* una ruta solo se usa si el fichero sigue existiendo, pero se conserva aparte, marcada como
  no disponible: una unidad desconectada no es una orden de olvidar lo que había en ella;
* «convertir TODOS» no es una opción guardada: es la acción, no una preferencia.
"""

from __future__ import annotations

import json
import logging
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
def _formatos_vnr() -> tuple[str, ...]:
    try:
        from vnr_etl.connectors.registry import FORMATOS_PAQUETE_VNR
    except ImportError:  # sin el módulo VNR la casilla no se puede usar igual
        return ('.zip',)
    return FORMATOS_PAQUETE_VNR


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
    'vnr_package': {
        'grupo': 'vnr', 'tipo': None,
        'etiqueta': 'Paquete o base VNR-GIS', 'obligatorio': True,
        # La interfaz ofrece estos y solo estos (spec 001, RF-26); ver FORMATOS_PAQUETE_VNR.
        'extensiones': list(_formatos_vnr()),
    },
    'aliases': {'grupo': 'comun', 'tipo': None,
                'etiqueta': 'Aliases de tipos (JSON, opcional)', 'obligatorio': False},
}

DEFAULT_OPTIONS: dict[str, Any] = {
    # Sin fuente hasta que se carga un fichero: la dice el fichero (059:RF-1). Con 'txt' por
    # defecto, el 2026-11-01 un espacio vacío se abrió como «Tres TXT de CYMDIST».
    'input_mode': None,
    'source_company': None,
    # 081:RF-51: la empresa de una fuente que no la dice (un TXT, una .mdb); ``source_company`` es lo elegido en VNR-GIS.
    'empresa_espacio': None,
    'source_period': None,
    # Sin CRS: el del perfil de empresa o, sin perfil, se pide (spec 002, RF-32).
    'source_crs': None,
    'target_crs': 'EPSG:4326',
    'include_geography': True,
    'strict': True,
    'write_preview': False,
    'export_xlsx': False,
    'export_tsv': False,
    # Procesos para convertir alimentadores a la vez: 0 automático, 1 en serie.
    'workers': 0,
    # None = hoja a medida y escala geográfica real; A0–A4 son formatos explícitos.
    'hoja': None,
}

#: Las tres fuentes del conversor (spec 059).
FUENTES = ('txt', 'mdb', 'vnr')
PIDE_FUENTE = ('la fuente: los tres TXT de CYMDIST, una base Access (.mdb) o un paquete '
               'VNR-GIS, reconocida por el fichero que se carga')

TEXT_OPTIONS = ('input_mode', 'source_company', 'empresa_espacio', 'source_period', 'source_crs', 'target_crs', 'hoja')
BOOL_OPTIONS = ('include_geography', 'strict', 'write_preview', 'export_xlsx', 'export_tsv')
#: Tope del selector de procesos. Más allá no se gana (ver batch.AUTO_WORKERS_MAX) y
#: cada proceso guarda una copia del dataset en memoria.
MAX_WORKERS = 16

_ID_RE = re.compile(r'^[a-f0-9]{8,32}$')
# Vive junto a los espacios (output/web/), no dentro de ninguno: lo comparten todos (spec 018).
REGISTRO_VINCULOS_FILE = 'vinculos_pf.json'
_SAFE_NAME = re.compile(r'[^A-Za-z0-9._() \-]+')


def data_root() -> Path:
    """Los espacios nuevos viven fuera del código; la raíz explícita sigue vigente."""
    from ..runtime_paths import rutas_runtime

    env = os.environ.get('CSG_WEB_DATA', '').strip()
    return Path(env) if env else rutas_runtime(project_root()).runtime / 'data' / 'web'


def raiz_componente(nombre: str, variable: str) -> Path:
    """Mantiene los modelos/episodios heredados hasta una migración explícita."""
    env = os.environ.get(variable, '').strip()
    if env:
        return Path(env)
    if nombre not in ('_asistente', '_digital_twin'):
        raise ValueError('Componente de datos no reconocido.')
    legacy = project_root() / 'output' / 'web' / nombre
    if not os.environ.get('CSG_WEB_DATA', '').strip() and legacy.is_dir():
        return legacy
    return data_root() / nombre


def safe_filename(name: str) -> str:
    base = Path(name or 'fichero').name
    cleaned = _SAFE_NAME.sub('_', base).strip(' .')
    return cleaned or 'fichero'


#: Versión de ``workspace.json`` que escribe este código (086:RF-4).
VERSION_ESPACIO = 3
#: Una ruta de dentro del espacio, relativa a su carpeta (086:RF-6).
PREFIJO_RELATIVA = 'espacio:'
#: Campos con rutas de ficheros. Quedan fuera los vínculos con DIgSILENT y el inventario: son
#: evidencia con su huella, y lo guardado no se reescribe (058:RF-6).
CAMPOS_CON_RUTAS = ('inputs', 'catalog_file', 'groups', 'calibraciones', 'escaneo', 'demanda',
                    'obras', 'obras_aplicadas', 'informes', 'datos_empresa')
_RUTA_ABSOLUTA = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\|/)')
#: Cada cuánto se mira si volvió una unidad ausente; en una ruta de red, mirar puede tardar segundos.
REVISION_NO_DISPONIBLES_S = 30.0


class EspacioNoUtilizable(ValueError):
    """Un espacio que se ve en la lista pero no se puede abrir; ``str`` dice por qué."""


class EspacioDanado(EspacioNoUtilizable):
    """``workspace.json`` no se puede leer (086:RF-2)."""


class EspacioVersionFutura(EspacioNoUtilizable):
    """``workspace.json`` es de una versión más nueva que este código (086:RF-5)."""


def _recorrer_textos(valor: Any, cambiar) -> Any:
    if isinstance(valor, dict):
        return {k: _recorrer_textos(v, cambiar) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_recorrer_textos(v, cambiar) for v in valor]
    return cambiar(valor) if isinstance(valor, str) else valor


def relativizar_rutas(valor: Any, root: Path) -> Any:
    """Lo que está dentro de ``root`` pasa a ``espacio:…``; las rutas de fuera siguen enteras (086:RF-6)."""
    base = os.path.normcase(os.path.abspath(root))

    def cambiar(texto: str) -> str:
        if not _RUTA_ABSOLUTA.match(texto):
            return texto
        ruta = os.path.normpath(texto)
        if not os.path.normcase(ruta).startswith(base + os.sep):
            return texto
        return PREFIJO_RELATIVA + ruta[len(base) + 1:].replace(os.sep, '/')

    return _recorrer_textos(valor, cambiar)


def expandir_rutas(valor: Any, root: Path) -> Any:
    """Lo contrario de :func:`relativizar_rutas`, en la carpeta donde esté hoy el espacio."""

    def cambiar(texto: str) -> str:
        if not texto.startswith(PREFIJO_RELATIVA):
            return texto
        relativa = texto[len(PREFIJO_RELATIVA):]
        if '..' in relativa.split('/') or _RUTA_ABSOLUTA.match(relativa):
            return texto  # no salió de save(): queda sin resolver y se verá como no disponible
        return str(Path(root) / relativa)

    return _recorrer_textos(valor, cambiar)


def _rebasar_rutas(valor: Any, wid: str, root: Path) -> Any:
    """Las rutas absolutas de un espacio movido: su componente ``<id>`` dice dónde empieza lo suyo."""

    def cambiar(texto: str) -> str:
        if not _RUTA_ABSOLUTA.match(texto):
            return texto
        partes = re.split(r'[\\/]+', texto)
        if wid not in partes:
            return texto
        return str(Path(root, *partes[partes.index(wid) + 1:]))

    return _recorrer_textos(valor, cambiar)


def leer_metadatos_espacio(root: Path) -> dict[str, Any]:
    """``workspace.json`` de otro espacio, con sus rutas enteras, sin migrarlo ni escribir nada."""
    datos = json.loads((root / 'workspace.json').read_text(encoding='utf-8'))
    if not isinstance(datos, dict):
        raise ValueError(f'{root.name}: workspace.json no es un objeto')
    return {k: expandir_rutas(v, root) if k in CAMPOS_CON_RUTAS else v for k, v in datos.items()}


def _de_1_a_2(datos: dict[str, Any], _root: Path) -> dict[str, Any]:
    """Los ficheros sin ``version`` o con la 1 tienen los mismos campos; lo que falta se lee vacío."""
    return datos


def _de_2_a_3(datos: dict[str, Any], root: Path) -> dict[str, Any]:
    """Rutas relativas al espacio (086:RF-6); arregla de paso las de un espacio ya movido."""
    wid = str(datos.get('id') or root.name)
    return {k: relativizar_rutas(_rebasar_rutas(v, wid, root), root) if k in CAMPOS_CON_RUTAS else v
            for k, v in datos.items()}


#: Un paso por versión, de la clave a la siguiente (086:RF-4). Una versión nueva añade aquí el suyo.
MIGRACIONES = {1: _de_1_a_2, 2: _de_2_a_3}


def _version_de(datos: dict[str, Any]) -> int:
    version = datos.get('version', 1)
    if type(version) is not int or version < 1:
        raise EspacioDanado(f'workspace.json con una versión no válida: {version!r}')
    return version


def _leer_estado(root: Path) -> dict[str, Any]:
    """El ``workspace.json`` de ``root`` comprobado, o la excepción que dice qué le pasa."""
    try:
        datos = json.loads((root / 'workspace.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise EspacioDanado(f'workspace.json no se puede leer: {exc}') from exc
    if not isinstance(datos, dict) or not datos.get('id'):
        raise EspacioDanado('workspace.json no tiene el contenido esperado')
    version = _version_de(datos)
    if version > VERSION_ESPACIO:
        raise EspacioVersionFutura(
            f'Este espacio es de una versión más nueva ({version}; este programa llega a la '
            f'{VERSION_ESPACIO}). No se abre ni se escribe para no estropearlo: actualice el programa.')
    return datos


def _migrar(root: Path, datos: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Copia primero y luego los pasos, uno a uno; la copia de la versión no se pisa nunca (086:RF-4)."""
    version = _version_de(datos)
    if version == VERSION_ESPACIO:
        return datos, None
    from ..util import publicar_duradero

    copia = root / f'workspace.v{version}.json'
    if not copia.exists():
        publicar_duradero(copia, (root / 'workspace.json').read_bytes())
    actual = version
    while actual < VERSION_ESPACIO:
        datos = MIGRACIONES[actual](datos, root)
        actual += 1
        datos['version'] = actual
    return datos, f'Espacio migrado de la versión {version} a la {actual}; copia en {copia.name}.'


def _leer_conversiones(root: Path) -> tuple[dict[str, Any], str | None]:
    """``conversiones.json``, o su copia si está dañado; lo dañado se aparta, no se pisa."""
    from ..util import ruta_copia_anterior

    ruta = root / 'conversiones.json'
    if not ruta.is_file():
        return {}, None
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
        if isinstance(datos, dict):
            return datos, None
    except (OSError, ValueError):
        pass
    apartado = ruta.with_name(f'conversiones.danado-{time.strftime("%Y%m%dT%H%M%S")}.json')
    try:
        shutil.copy2(ruta, apartado)
    except OSError:
        pass
    try:
        datos = json.loads(ruta_copia_anterior(ruta).read_text(encoding='utf-8'))
        if isinstance(datos, dict):
            return datos, (f'conversiones.json estaba dañado: se recuperó su copia anterior y el '
                           f'dañado queda en {apartado.name}.')
    except (OSError, ValueError):
        pass
    return {}, (f'conversiones.json estaba dañado y no hay copia anterior: la tabla de alimentadores se '
                f'rehace al convertir, y el dañado queda en {apartado.name}.')


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
    # Contrato fuente → DGS → proyecto nativo, indexado por ruta de proyecto.
    pf_project_bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Registro compartido de vínculos entre espacios (spec 018); lo fija WorkspaceStore.
    vinculos_compartidos: Path | None = None
    # Spec 015: demanda que dejó la última calibración de cada alimentador, por proyecto.
    # La calibración ya no deja variación en DIgSILENT donde leerla, y sin ella no se ve
    # qué cambió el operador a mano (014:RF-10).
    calibraciones: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: 028: el último escaneo de cada proyecto de DIgSILENT (generadores, bancos, variaciones).
    escaneo: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Spec 025, RF-17: año de medición de los casos sin año («Sin proyecto», «Con
    # proyecto») de cada proyecto; otro año se calibra en «Sin proyecto <año>».
    anios_casos: dict[str, int] = field(default_factory=dict)
    # Último inventario leído directamente de PowerFactory; su identidad invalida
    # planes de carga revisados si el proyecto cambia antes de aplicar.
    pf_inventory: dict[str, Any] = field(default_factory=dict)
    # Ejecución inmutable que respalda el dataset en memoria y sus salidas.
    active_run_id: str | None = None
    # Obras de mejora definidas en el formulario hasta que se aplican (spec 011, RF-95),
    # cada una con su ``id`` y la forma de ``obras_pf.Obra.a_dict``.
    obras: list[dict[str, Any]] = field(default_factory=list)
    # Obras ya aplicadas en DIgSILENT, con su proyecto y su variación: salen de ``obras``
    # al aplicarse y el informe de estudio las necesita (017:RF-35; CA101, 2026-10-15).
    obras_aplicadas: list[dict[str, Any]] = field(default_factory=list)
    # Spec 017: lo escrito en los formularios de 4.4 por proyecto y tipo (RF-82), y el
    # libro de pérdidas de la empresa (RF-93), para no perderlos al recargar la página.
    informes: dict[str, Any] = field(default_factory=lambda: {'formularios': {}})
    # Spec 012: el último libro de la empresa de cada proyecto ({'path', 'nombre', 'cargado',
    # 'libro'}, RF-20) y los módulos que DIgSILENT rechazó por licencia (RF-4).
    datos_empresa: dict[str, dict[str, Any]] = field(default_factory=dict)
    sin_licencia: list[str] = field(default_factory=list)
    # 086:RF-3: lo que apunta a un fichero que hoy no está. Fuera de ``inputs`` y compañía, porque
    # quien los lee da por hecho que el fichero existe; save() lo vuelve a escribir tal cual.
    no_disponibles: dict[str, Any] = field(default_factory=dict)
    # --- solo en memoria
    # 086:RF-2, RF-4: lo que pasó al abrir el espacio, para decírselo al operador.
    avisos_datos: list[str] = field(default_factory=list)
    _no_disponibles_revisados: float = field(default=0.0, repr=False)
    dataset: Any = None
    # 038:RF-1: índice de pertenencia por identidad de la fuente, solo en memoria.
    _sed_owners_cache: tuple[Any, dict[str, set[str]]] | None = field(default=None, repr=False)
    loaded_run_id: str | None = None
    loaded_source_mode: str | None = None
    loaded_source_fingerprint: str | None = None
    inventory: dict | None = None
    source_audit: dict | None = None
    feeder_readiness: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog_report: dict | None = None
    reconstructed_dataset: Any = None
    reconstruction_report: dict | None = None
    reconstruction_report_hash: str | None = None
    reconstruction_run_id: str | None = None
    reconstruction_selection: tuple[str, ...] = ()
    loaded_at: float | None = None
    plans: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Planes del módulo de cargas en DIgSILENT (spec 004). Aparte de ``plans`` porque
    # no dependen de las entradas: cargar otro TXT no debe tirar un plan de demandas.
    cargas_planes: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Libros de la demanda medida (spec 004, RF-39), por tipo: {'path', 'name', 'origin'}.
    demanda: dict[str, Any] = field(default_factory=dict)
    # Curvas del último trabajo de máxima de cabecera, {job_id: {medidor: {curva, fuera}}} (spec 006,
    # RF-31). Solo la última: un año de lecturas cada 15 min son ~35 000 registros por
    # medidor, y no deben acumularse búsqueda tras búsqueda.
    curvas_cabecera: dict[str, dict[str, list]] = field(default_factory=dict)
    # Mes de análisis (013:RF-11) e instante coincidente (021:RF-50) de cada búsqueda de
    # la máxima: la central y el ajuste usan el mismo criterio que la tabla.
    criterio_cabecera: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Última lectura de alimentadores y tipos de DIgSILENT para el formulario de obras:
    # abrir DIgSILENT tarda, y no se repite al cambiar de obra (plan de la spec 011).
    pf_bibliotecas: dict[str, Any] = field(default_factory=dict)
    events: EventLog = field(default_factory=EventLog)
    lock: threading.RLock = field(default_factory=threading.RLock)
    _corrections_cache: tuple[float, Any] | None = None

    # -------------------------------------------------------------- carpetas
    @property
    def inputs_dir(self) -> Path:
        return self.root / 'entradas'

    @property
    def out_dir(self) -> Path:
        if self.active_run_id:
            return self.root / 'runs' / self.active_run_id / 'salida'
        return self.root / 'salida'

    @property
    def plans_dir(self) -> Path:
        return self.root / 'planes'

    # -------------------------------------------------------------- persistencia
    def save(self) -> None:
        nd = self.no_disponibles
        informes = dict(self.informes)
        if 'libro_perdidas' in nd:
            informes.setdefault('libro_perdidas', nd['libro_perdidas'])
        payload = {
            'version': VERSION_ESPACIO,
            'id': self.id,
            'created_at': self.created_at,
            'options': self.options,
            # Lo vigente manda sobre lo no disponible de la misma casilla: el operador ya eligió otro.
            'inputs': {**(nd.get('inputs') or {}), **self.inputs},
            'catalog_file': self.catalog_file or nd.get('catalog_file'),
            'groups': self.groups,
            'pf_projects': self.pf_projects,
            'pf_project_bindings': self.pf_project_bindings,
            'calibraciones': self.calibraciones,
            'escaneo': self.escaneo,
            'anios_casos': self.anios_casos,
            'pf_inventory': self.pf_inventory,
            'active_run_id': self.active_run_id or nd.get('active_run_id'),
            'demanda': {**(nd.get('demanda') or {}), **self.demanda},
            'obras': self.obras,
            'obras_aplicadas': self.obras_aplicadas,
            'informes': informes,
            'datos_empresa': {**(nd.get('datos_empresa') or {}), **self.datos_empresa},
            'sin_licencia': self.sin_licencia,
        }
        payload = {k: relativizar_rutas(v, self.root) if k in CAMPOS_CON_RUTAS else v
                   for k, v in payload.items()}
        self.root.mkdir(parents=True, exist_ok=True)
        from ..util import write_json_atomic

        ruta = self.root / 'workspace.json'
        # 086:RF-5: otro proceso más nuevo pudo actualizarlo después de que este lo abriera.
        try:
            _leer_estado(self.root)
        except EspacioVersionFutura:
            raise
        except EspacioDanado:
            pass  # lo que hay en memoria es mejor; write_json_atomic no copia lo dañado sobre el .bak
        write_json_atomic(ruta, payload, copia=True)
        write_json_atomic(self.root / 'conversiones.json', relativizar_rutas(self.conversions, self.root),
                          copia=True)

    @classmethod
    def load(cls, root: Path) -> 'Workspace':
        crudo = _leer_estado(root)
        data, migrado = _migrar(root, crudo)
        data = {k: expandir_rutas(v, root) if k in CAMPOS_CON_RUTAS else v for k, v in data.items()}
        ws = cls(id=data['id'], root=root, created_at=data.get('created_at', time.time()))
        options = dict(DEFAULT_OPTIONS)
        options.update({k: v for k, v in (data.get('options') or {}).items()
                        if k in DEFAULT_OPTIONS})
        ws.options = options
        # Una ruta que ya no existe no se usa: el campo queda vacío en lugar de apuntar a la
        # nada y fallar cuando alguien pulse convertir. Pero se conserva (086:RF-3).
        entradas = {slot: meta for slot, meta in (data.get('inputs') or {}).items()
                    if slot in SLOTS and isinstance(meta, dict)}
        ws.inputs = {s: m for s, m in entradas.items() if Path(m.get('path', '')).is_file()}
        ws._apartar('inputs', {s: m for s, m in entradas.items() if s not in ws.inputs and m.get('path')})
        # La fuente es la de lo cargado, no la guardada si no tiene entradas suyas (059:RF-2).
        if ws.options.get('input_mode') not in FUENTES or not any(
                SLOTS[slot]['grupo'] == ws.options['input_mode'] for slot in ws.inputs):
            ws.options['input_mode'] = ws.fuente_por_entradas()
        catalog = data.get('catalog_file')
        ws.catalog_file = catalog if catalog and Path(catalog).is_file() else None
        if catalog and not ws.catalog_file:
            ws.no_disponibles['catalog_file'] = catalog
        ws.groups = dict(data.get('groups') or {})
        ws.pf_projects = dict(data.get('pf_projects') or {})
        ws.pf_project_bindings = dict(data.get('pf_project_bindings') or {})
        ws.calibraciones = dict(data.get('calibraciones') or {})
        ws.escaneo = dict(data.get('escaneo') or {})
        ws.anios_casos = {str(k): int(v) for k, v in (data.get('anios_casos') or {}).items()}
        ws.pf_inventory = dict(data.get('pf_inventory') or {})
        # Igual que las entradas: un libro o una carpeta que ya no está no se usa, y se conserva.
        demanda = {tipo: meta for tipo, meta in (data.get('demanda') or {}).items() if isinstance(meta, dict)}
        ws.demanda = {t: m for t, m in demanda.items() if Path(m.get('path', '')).exists()}
        ws._apartar('demanda', {t: m for t, m in demanda.items() if t not in ws.demanda and m.get('path')})
        ws.obras = [o for o in (data.get('obras') or []) if isinstance(o, dict) and o.get('id')]
        ws.obras_aplicadas = [o for o in (data.get('obras_aplicadas') or [])
                              if isinstance(o, dict) and o.get('variacion')]
        informes = data.get('informes') if isinstance(data.get('informes'), dict) else {}
        libro = informes.get('libro_perdidas')
        libro_esta = isinstance(libro, dict) and Path(libro.get('path', '')).is_file()
        ws.informes = {
            'formularios': dict(informes.get('formularios') or {}),
            **({'libro_perdidas': libro} if libro_esta else {}),
        }
        if isinstance(libro, dict) and not libro_esta and libro.get('path'):
            ws.no_disponibles['libro_perdidas'] = libro
        # Como las entradas: un libro de la empresa que ya no está no se usa, y se conserva.
        empresa = {p: d for p, d in (data.get('datos_empresa') or {}).items() if isinstance(d, dict)}
        ws.datos_empresa = {p: d for p, d in empresa.items() if Path(d.get('path', '')).is_file()}
        ws._apartar('datos_empresa', {p: d for p, d in empresa.items()
                                      if p not in ws.datos_empresa and d.get('path')})
        ws.sin_licencia = [str(m) for m in data.get('sin_licencia') or []]
        run_id = data.get('active_run_id')
        if run_id and (root / 'runs' / str(run_id) / 'source_manifest.json').is_file():
            ws.active_run_id = str(run_id)
        elif run_id:
            # La migración de T7 sobre una copia sin ``runs`` lo destapó: se perdía sin decir nada.
            ws.no_disponibles['active_run_id'] = str(run_id)
        conversiones, aviso = _leer_conversiones(root)
        ws.conversions = expandir_rutas(_rebasar_rutas(conversiones, ws.id, root), root)
        ws.avisos_datos.extend(a for a in (migrado, aviso) if a)
        if migrado:
            try:
                ws.save()
            except OSError as exc:
                # En memoria ya está migrado, y su copia guardada: se reintenta en el próximo guardado.
                logging.getLogger(__name__).warning('Espacio %s sin guardar tras migrar: %s', ws.id, exc)
        return ws

    # -------------------------------------------------------------- no disponibles
    def _apartar(self, campo: str, entradas: dict[str, Any]) -> None:
        if entradas:
            self.no_disponibles[campo] = entradas

    def _resumen_no_disponibles(self) -> list[dict[str, str]]:
        """Lo que apunta a un fichero que no está, para que el operador lo vea (086:RF-3)."""
        nd = self.no_disponibles
        filas = [(campo, clave, meta) for campo in ('inputs', 'demanda', 'datos_empresa')
                 for clave, meta in (nd.get(campo) or {}).items()]
        if 'libro_perdidas' in nd:
            filas.append(('libro_perdidas', 'libro_perdidas', nd['libro_perdidas']))
        if 'catalog_file' in nd:
            filas.append(('catalog_file', 'catalog_file', {'path': nd['catalog_file']}))
        if 'active_run_id' in nd:
            filas.append(('active_run_id', 'active_run_id', {
                'path': str(self.root / 'runs' / nd['active_run_id']), 'name': nd['active_run_id']}))
        return [{'campo': campo, 'clave': clave, 'ruta': str(meta.get('path') or ''),
                 'nombre': str(meta.get('name') or meta.get('nombre') or Path(str(meta.get('path') or '')).name)}
                for campo, clave, meta in filas]

    def reponer_disponibles(self, *, ahora: float | None = None) -> None:
        """Una unidad que vuelve con la web abierta devuelve lo suyo sin reiniciar (086:RF-3)."""
        reloj = time.monotonic() if ahora is None else ahora
        if not self.no_disponibles or reloj - self._no_disponibles_revisados < REVISION_NO_DISPONIBLES_S:
            return
        self._no_disponibles_revisados = reloj
        # Con el cerrojo ocupado se mira a la próxima: una petición no espera por esto.
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._reponer()
        finally:
            self.lock.release()

    def _reponer(self) -> None:
        nd = self.no_disponibles
        for campo, vigentes, existe in (('inputs', self.inputs, Path.is_file), ('demanda', self.demanda, Path.exists),
                                        ('datos_empresa', self.datos_empresa, Path.is_file)):
            for clave, meta in list((nd.get(campo) or {}).items()):
                if clave in vigentes:
                    del nd[campo][clave]
                elif existe(Path(meta.get('path', ''))):
                    vigentes[clave] = meta
                    del nd[campo][clave]
            if campo in nd and not nd[campo]:
                del nd[campo]
        libro = nd.get('libro_perdidas')
        if libro and Path(libro.get('path', '')).is_file():
            self.informes.setdefault('libro_perdidas', libro)
            del nd['libro_perdidas']
        catalogo = nd.get('catalog_file')
        if catalogo and Path(catalogo).is_file():
            self.catalog_file = self.catalog_file or catalogo
            del nd['catalog_file']
        ejecucion = nd.get('active_run_id')
        if ejecucion and (self.root / 'runs' / ejecucion / 'source_manifest.json').is_file():
            self.active_run_id = self.active_run_id or ejecucion
            del nd['active_run_id']
        if self.options.get('input_mode') not in FUENTES:
            self.options['input_mode'] = self.fuente_por_entradas()

    def descartar_no_disponible(self, campo: str, clave: str) -> bool:
        """El operador da por perdida una referencia; sin esto, el aviso quedaría para siempre."""
        with self.lock:
            nd = self.no_disponibles
            if campo in ('libro_perdidas', 'catalog_file', 'active_run_id'):
                quitado = nd.pop(campo, None) is not None
            else:
                quitado = (nd.get(campo) or {}).pop(clave, None) is not None
                if campo in nd and not nd[campo]:
                    del nd[campo]
            if quitado:
                self.save()
            return quitado

    # -------------------------------------------------------------- entradas
    def invalidate(self) -> None:
        """Otra entrada = otro dataset. Lo leído deja de valer, y los planes también."""
        self.dataset = None
        self._sed_owners_cache = None
        self.loaded_run_id = None
        self.loaded_source_mode = None
        self.loaded_source_fingerprint = None
        self.inventory = None
        self.source_audit = None
        self.feeder_readiness.clear()
        self.catalog_report = None
        self.reconstructed_dataset = None
        self.reconstruction_report = None
        self.reconstruction_report_hash = None
        self.reconstruction_run_id = None
        self.reconstruction_selection = ()
        self.loaded_at = None
        self.plans.clear()
        self.active_run_id = None
        # Otra entrada deja sin sentido la ejecución que se esperaba que volviera.
        self.no_disponibles.pop('active_run_id', None)

    def active_run(self):
        """Devuelve la instantánea activa persistida, o ``None`` si fue invalidada."""
        if not self.active_run_id:
            return None
        from .source_runs import load_source_run

        try:
            return load_source_run(self, self.active_run_id)
        except (OSError, ValueError, KeyError, TypeError):
            return None

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
            self._olvidar_entrada_no_disponible(slot)
            if slot == 'vnr_package':
                self.options['source_company'] = None
                self.options['source_period'] = None
            self.invalidate()
            self._drop_upload(old, keep=path)
            self.save()
        return meta

    def clear_input(self, slot: str) -> None:
        with self.lock:
            old = self.inputs.pop(slot, None)
            self._olvidar_entrada_no_disponible(slot)
            self.invalidate()
            self._drop_upload(old)
            # Sin ningún fichero de su fuente, el espacio deja de tener esa fuente (059:RF-2).
            mode = self.options.get('input_mode')
            if not any(SLOTS[s]['grupo'] == mode for s in self.inputs):
                self.options['input_mode'] = self.fuente_por_entradas()
            self.save()

    def _olvidar_entrada_no_disponible(self, slot: str) -> None:
        """Elegir otra o quitarla es decisión del operador: lo que había en la casilla ya no vuelve."""
        entradas = self.no_disponibles.get('inputs') or {}
        entradas.pop(slot, None)
        if 'inputs' in self.no_disponibles and not entradas:
            del self.no_disponibles['inputs']

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

    def fuente_por_entradas(self) -> str | None:
        """La fuente del único grupo con entradas; ninguna si no hay o si hay de varios (059:RF-2)."""
        grupos = {SLOTS[s]['grupo'] for s in self.inputs if SLOTS[s]['grupo'] in FUENTES}
        return grupos.pop() if len(grupos) == 1 else None

    def missing_inputs(self) -> list[str]:
        mode = self.options.get('input_mode')
        if mode not in FUENTES:
            return [PIDE_FUENTE]
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
        manifest_url = (
            f'/api/workspaces/{self.id}/runs/{self.active_run_id}/manifest'
            if self.active_run_id else None
        )
        return {
            'id': self.id,
            'created_at': self.created_at,
            'options': self.options,
            'inputs': self.inputs,
            'no_disponibles': self._resumen_no_disponibles(),
            'avisos_datos': self.avisos_datos,
            'missing_inputs': self.missing_inputs(),
            'loaded': self.dataset is not None,
            'loaded_at': self.loaded_at,
            'active_run_id': self.active_run_id,
            'loaded_run_id': self.loaded_run_id,
            'source_mode': self.loaded_source_mode,
            'source_fingerprint': self.loaded_source_fingerprint,
            'source_manifest_url': manifest_url,
            'totals': inv.get('totals'),
            'conversion': inv.get('conversion'),
            'integrity': inv.get('integrity'),
            'universal_audit': self.source_audit,
            'catalog_report': self.catalog_report,
            'catalog_applied': bool(self.catalog_file),
            'catalog_file': Path(self.catalog_file).name if self.catalog_file else None,
            'reconstruction': {
                'run_id': self.reconstruction_run_id,
                'selection': list(self.reconstruction_selection),
                'report': 'reconstruction_report.json',
                'report_sha256': self.reconstruction_report_hash,
            } if self.reconstruction_report_hash else None,
            'converted': sum(1 for c in self.conversions.values() if c.get('status') == 'ok'),
            'groups': [
                group for group in self.groups.values()
                if group.get('source_run_id') == self.active_run_id
            ],
            'pf_projects': self.pf_projects,
            'pf_project_bindings': self.pf_project_bindings,
            'obras': self.obras,
            'obras_aplicadas': self.obras_aplicadas,
            # 035:RF-21: qué proyectos y alimentadores ya tienen su primera calibración y cuántas
            # recalibraciones llevan; sin la demanda por SED, que pesa y no es de la web.
            'calibraciones': {clave: {f: {'recalibracion': int(c.get('recalibracion') or 0),
                                          'nombre': c.get('nombre'), 'caso': c.get('caso')}
                                      for f, c in por_feeder.items()}
                              for clave, por_feeder in self.calibraciones.items()},
            'demanda': {tipo: {k: v for k, v in meta.items() if k != 'path'}
                        for tipo, meta in self.demanda.items()},
            'last_seq': self.events.last_seq,
        }


class WorkspaceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_root()
        # No mover fuentes mientras otra sesión puede leerlas. Los espacios heredados
        # siguen usando su raíz y registro; solo los nuevos nacen en el almacén externo.
        legacy = project_root() / 'output' / 'web'
        self.roots = (self.root,)
        if root is None and not os.environ.get('CSG_WEB_DATA', '').strip() and legacy.is_dir():
            if legacy.resolve() != self.root.resolve():
                self.roots += (legacy,)
        self._items: dict[str, Workspace] = {}
        self._lock = threading.Lock()
        self.siembra: dict[str, int] | None = None
        self._sembrar_vinculos()

    def _sembrar_vinculos(self) -> None:
        """Arranque: los vínculos que ya tienen los espacios pasan al registro compartido.

        Un fallo aquí no detiene el servidor: si el registro es ilegible, los proyectos
        quedan bloqueados con PROJECT_BINDING_REGISTRY_UNREADABLE, que es lo visible.
        """
        from ..powerfactory_binding import ProjectBindingError, sembrar_registro

        if not self.root.is_dir():
            return
        crudos = []
        for carpeta in sorted(self.root.iterdir()):
            meta = carpeta / 'workspace.json'
            if not meta.is_file():
                continue
            try:
                datos = json.loads(meta.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(datos, dict):
                crudos.append(datos.get('pf_project_bindings') or {})
        try:
            self.siembra = sembrar_registro(self.root / REGISTRO_VINCULOS_FILE, crudos)
        except ProjectBindingError as exc:
            logging.getLogger(__name__).warning('Vínculos de DIgSILENT sin sembrar: %s', exc)

    def create(self) -> Workspace:
        wid = uuid.uuid4().hex[:16]
        ws = Workspace(id=wid, root=self.root / wid)
        ws.vinculos_compartidos = self.root / REGISTRO_VINCULOS_FILE
        ws.out_dir.mkdir(parents=True, exist_ok=True)
        ws.save()
        with self._lock:
            self._items[wid] = ws
        return ws

    def _carpeta(self, wid: str) -> Path | None:
        """La carpeta de ``wid``; también si solo le queda la copia, para poder recuperarla."""
        from ..util import ruta_copia_anterior

        folders = [base / wid for base in self.roots
                   if (base / wid / 'workspace.json').is_file()
                   or ruta_copia_anterior(base / wid / 'workspace.json').is_file()]
        if len(folders) > 1:
            raise ValueError(f'Identificador de espacio duplicado en dos raíces: {wid}')
        if not folders:
            return None
        folder = folders[0]
        if folder.is_symlink() or folder.is_junction() or folder.resolve().parent != folder.parent.resolve():
            return None
        return folder

    def get(self, wid: str) -> Workspace | None:
        if not _ID_RE.match(wid or ''):
            return None
        with self._lock:
            ws = self._items.get(wid)
            if ws is None:
                folder = self._carpeta(wid)
                if folder is None:
                    return None
                try:
                    ws = Workspace.load(folder)
                except (OSError, ValueError, KeyError):
                    return None
                ws.vinculos_compartidos = folder.parent / REGISTRO_VINCULOS_FILE
                self._items[wid] = ws
        # Fuera del cerrojo del almacén: mirar una ruta de red no para a los demás espacios.
        ws.reponer_disponibles()
        return ws

    def problema(self, wid: str) -> dict[str, Any] | None:
        """Por qué un espacio que existe no se abre (086:RF-2, RF-5), o None si no le pasa nada."""
        if not _ID_RE.match(wid or ''):
            return None
        with self._lock:
            if wid in self._items:
                return None
            folder = self._carpeta(wid)
        return self._problema_de(folder) if folder is not None else None

    @staticmethod
    def _problema_de(folder: Path) -> dict[str, Any] | None:
        from ..util import ruta_copia_anterior

        try:
            _leer_estado(folder)
        except EspacioVersionFutura as exc:
            return {'estado': 'version_futura', 'motivo': str(exc), 'restaurable': False}
        except EspacioDanado as exc:
            copia = ruta_copia_anterior(folder / 'workspace.json')
            try:
                restaurable = isinstance(json.loads(copia.read_text(encoding='utf-8')), dict)
            except (OSError, ValueError):
                restaurable = False
            return {'estado': 'danado', 'motivo': str(exc), 'restaurable': restaurable}
        return None

    def restaurar_copia(self, wid: str) -> Workspace:
        """Un espacio dañado vuelve a su copia anterior; lo dañado se aparta, no se borra (086:RF-2)."""
        from ..util import publicar_duradero, ruta_copia_anterior

        folder = self._carpeta(wid) if _ID_RE.match(wid or '') else None
        problema = self._problema_de(folder) if folder is not None else None
        if folder is None or problema is None or problema['estado'] != 'danado':
            raise EspacioNoUtilizable('Este espacio no está dañado: no hay nada que restaurar.')
        if not problema['restaurable']:
            raise EspacioDanado(f"No hay copia anterior que restaurar. {problema['motivo']}")
        meta = folder / 'workspace.json'
        if meta.is_file():
            shutil.copy2(meta, folder / f'workspace.danado-{time.strftime("%Y%m%dT%H%M%S")}.json')
        publicar_duradero(meta, ruta_copia_anterior(meta).read_bytes())
        with self._lock:
            self._items.pop(wid, None)
        ws = self.get(wid)
        if ws is None:
            raise EspacioDanado('La copia anterior tampoco se puede abrir.')
        ws.avisos_datos.append('Espacio restaurado de su copia anterior; lo dañado se conserva aparte.')
        return ws

    def list(self) -> list[dict]:
        from ..util import ruta_copia_anterior

        out = []
        for folder in (p for base in self.roots if base.is_dir() for p in base.iterdir()):
            if folder.is_symlink() or folder.is_junction():
                continue
            meta = folder / 'workspace.json'
            if not meta.is_file() and not ruta_copia_anterior(meta).is_file():
                continue
            modificado = (meta if meta.is_file() else ruta_copia_anterior(meta)).stat().st_mtime
            # Dañado o más nuevo, se ve con su motivo: sin esto, el espacio desaparecía sin decir nada.
            problema = self._problema_de(folder)
            try:
                data = json.loads(meta.read_text(encoding='utf-8'))
                entradas = {k: v.get('name') for k, v in (data.get('inputs') or {}).items()}
            except (OSError, ValueError, AttributeError):
                data, entradas = {}, {}
            if problema and problema['estado'] == 'danado':
                data, entradas = {}, {}
            out.append({
                'id': data.get('id', folder.name),
                'created_at': data.get('created_at'),
                'inputs': entradas,
                'modified_at': modificado,
                **(problema or {'estado': 'ok'}),
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
