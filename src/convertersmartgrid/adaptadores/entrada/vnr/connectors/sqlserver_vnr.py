"""VNR-GIS desde la copia de SQL Server (``.bak``) de cualquier concesionaria (spec 023).

VNR-GIS es el sistema del regulador (Osinergmin) con el que todas las concesionarias
entregan su red, con el mismo modelo de datos. La entrega real es una copia de SQL Server
de la base de red, con su base de parámetros y un ``ConfigBD.config`` (una distribuidora real,
2026-10-18: ``<sigla>_VNR_24_APR.bak``, 819 MB, 75 tablas). Una copia no se lee sin
restaurarla en un motor de SQL Server: aquí se restaura (``RESTORE … WITH MOVE``), se lee
por ODBC y se arma el modelo canónico, sin nada fijo de una empresa:

* las tablas se reconocen por sus campos, no por su nombre (RF-7);
* la tensión de ``CodTenNomi`` (una letra) sale de los códigos secundarios de tensión MT
  de la base de parámetros, por su orden (A = el primero…): en la copia de una distribuidora real,
  D = 10 kV y G = 22,9 kV, lo que dan sus alimentadores en las otras fuentes;
* el CRS sale del datum y la zona UTM de la empresa (``empEmpresa``); VNR-GIS es peruano,
  hemisferio sur (RF-8);
* material, sección y fases del conductor, de la descripción de su norma (Anexo 2 de la
  Guía del VNR: «RED AEREA CONDUCTOR DE AA O SIMIL. 3x50 mm2»).
"""
from __future__ import annotations

import hashlib
import heapq
import logging
import math
import re
import shutil
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from convertersmartgrid.dominio.fases_red import fases_de_carga_que_llegan, fases_desde_la_cabecera
from convertersmartgrid.dominio.util import finite_or_none
from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import SIN_REGLA_BT, estado_o_anota, medio_o_anota
from convertersmartgrid.adaptadores.entrada.vnr.models import (Capacitor, CanonicalModel, ConductorType, Load,
                                                             LowVoltageSection, Node, Regulator, Section, Source,
                                                             Switch)

#: Motor por omisión: la instancia de SQL Server Express de la máquina.
SERVIDOR = r'.\SQLEXPRESS'
#: Distancia para dar por unidos dos extremos de tramo (m).
TOLERANCIA_M = 0.5
#: 080:RF-60: filas que se piden al motor de cada vez al leer la red BT. No depende del tamaño de la empresa: la red
#: BT entera se lee por bloques y solo se guarda lo de las salidas pedidas.
FILAS_POR_BLOQUE = 5000
#: 080:RF-60: tramos BT sin salida MT que se guardan como ejemplo en su aviso (``TRAMO_BT_SIN_SALIDA_MT``).
EJEMPLOS_DE_AVISO = 20
#: 080:RF-60: bytes por fila con los que se estima, antes de leerla, la memoria de la red BT pedida. Medidos en MEM-BT
#: (2026-11-15, tracemalloc con un doble del motor que da textos nuevos por fila: ~600 B el tramo, ~240 B el vértice,
#: 135–221 B lo que queda de cada salida BT) y redondeados hacia arriba. Más el bloque de filas en curso.
BYTES_POR_TRAMO_BT = 700
BYTES_POR_VERTICE_BT = 300
BYTES_POR_SALIDA_BT = 256
BYTES_POR_FILA_DE_BLOQUE = 400
#: 080:RF-60: hasta cuántas salidas MT se cuentan con parámetros (SQL Server admite 2 100 por consulta); con más,
#: se cuentan las tablas enteras, que es una cota por arriba.
MAX_SALIDAS_EN_LA_CUENTA = 2000
#: 080:RF-60 (MEM-BT v2): en la exportación en flujo, salidas MT cuya red BT se pide al SQLite temporal de cada vez, y
#: tramos BT de una pieza (una salida desproporcionada va en varias piezas; al escribir se juntan piezas hasta este
#: tamaño, así que en memoria hay como mucho dos). Ninguno de los dos depende del tamaño de la empresa.
LOTE_SALIDAS = 8
TRAMOS_BT_POR_PIEZA = 5000
#: 080:RF-60 (MEM-BT v2): bytes con los que se estima la exportación en flujo, medidos en MEM-BT v2 (2026-11-15) y
#: redondeados hacia arriba: en memoria, una pieza de tramos BT con sus vértices (canónico, filas, geometrías y lote de
#: Arrow; 1 834 B por tramo de 3 vértices con tracemalloc, pendiente entre piezas de 2 000 y 8 000 tramos), contada dos
#: veces porque al juntar piezas hay dos a la vez; en disco, el SQLite temporal (61 B por fila de media, con índices).
BYTES_POR_TRAMO_BT_EN_PIEZA = 1500
BYTES_POR_VERTICE_BT_EN_PIEZA = 250
BYTES_EN_DISCO_POR_TRAMO_BT = 160
BYTES_EN_DISCO_POR_VERTICE_BT = 64
BYTES_EN_DISCO_POR_SALIDA_BT = 96

_log = logging.getLogger(__name__)


class MotorSqlNoDisponible(RuntimeError):
    """No hay motor de SQL Server con el que restaurar o leer la copia (RF-5)."""


# --------------------------------------------------------------------------- copia y motor
def huella(path: Path | str, bloque: int = 1 << 20) -> str:
    """SHA-256 del fichero: la base restaurada lleva esta huella en su nombre (RF-3, RF-4)."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            parte = f.read(bloque)
            if not parte:
                break
            h.update(parte)
    return h.hexdigest()


def es_copia_sql(path: Path | str) -> bool:
    """Si el fichero es una copia de seguridad de SQL Server, por su cabecera MTF «TAPE» y no por
    su extensión: una distribuidora entregó la suya sin «.bak» (2026-11-01)."""
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'TAPE'
    except OSError:
        return False


def leer_config_bd(carpeta: Path | str) -> dict[str, str]:
    """``ConfigBD.config`` de VNR-GIS junto a la copia: empresa y bases (RF-2); vacío si no."""
    ruta = Path(carpeta) / 'ConfigBD.config'
    if not ruta.is_file():
        return {}
    try:
        raiz = ET.fromstring(ruta.read_text(encoding='utf-8', errors='replace'))
    except ET.ParseError:
        return {}
    valores = raiz.find('valores')
    if valores is None:
        return {}
    return {hijo.tag: (hijo.text or '').strip() for hijo in valores}


def cadena_de_conexion(servidor: str, base: str = 'master') -> str:
    return (f'DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={servidor};DATABASE={base};'
            'Trusted_Connection=yes;TrustServerCertificate=yes')


def conectar(servidor: str, base: str = 'master', *, conectar_odbc: Callable | None = None,
             autocommit: bool = True):
    """Conexión ODBC al motor; sin motor, :class:`MotorSqlNoDisponible` con qué instalar."""
    if conectar_odbc is None:
        try:
            import pyodbc
        except ImportError as exc:
            raise MotorSqlNoDisponible('Falta pyodbc para leer la copia de VNR-GIS.') from exc
        conectar_odbc = pyodbc.connect
    try:
        return conectar_odbc(cadena_de_conexion(servidor, base), autocommit=autocommit)
    except Exception as exc:  # noqa: BLE001 - pyodbc.Error y los de los dobles
        raise MotorSqlNoDisponible(
            f'No hay motor de SQL Server en {servidor!r} para la copia de VNR-GIS: instale '
            'SQL Server Express (gratuito) y arranque su servicio. Detalle: '
            f'{exc}') from exc


def _cuenta_del_motor(cur) -> str:
    """La cuenta con la que corre el motor, que es quien abre la copia, no este proceso."""
    try:
        cur.execute("SELECT service_account FROM sys.dm_server_services "
                    "WHERE servicename LIKE 'SQL Server (%'")
        fila = cur.fetchone()
        if fila and fila[0]:
            return str(fila[0])
    except Exception:  # noqa: BLE001 - esa vista pide un permiso que no todo usuario tiene
        pass
    cur.execute('SELECT @@SERVICENAME')
    instancia = str(cur.fetchone()[0])
    return 'NT SERVICE\\MSSQLSERVER' if instancia.upper() == 'MSSQLSERVER' else f'NT SERVICE\\MSSQL${instancia}'


def permitir_lectura_al_motor(bak: Path, cuenta: str) -> None:
    """080:RF-25, RF-26: lectura para el motor, solo a su cuenta y solo sobre este fichero.

    Desde Python 3.12, ``mkdtemp`` crea en Windows carpetas privadas, y lo publicado desde ellas
    conserva esos permisos. La custodia de la web deja así la copia, y el motor respondía «error
    5, acceso denegado» (paquete de otra distribuidora, 2026-11-02). Las empresas ya restauradas no lo
    revelaban, porque su base se reutiliza sin abrir el fichero.
    """
    resultado = subprocess.run(['icacls', str(bak), '/grant', f'{cuenta}:R'],
                               capture_output=True, text=True, errors='replace', check=False)
    if resultado.returncode != 0:
        raise MotorSqlNoDisponible(
            f'SQL Server no puede leer «{bak.name}» y no se le pudo dar permiso a su cuenta '
            f'{cuenta}: {(resultado.stdout + resultado.stderr).strip()}. Déle permiso de '
            'lectura sobre el fichero o cópielo a una carpeta que el servicio pueda leer.')


def restaurar(bak: Path | str, *, servidor: str = SERVIDOR, carpeta: Path | str | None = None,
              conectar_odbc: Callable | None = None, avisos: list[dict] | None = None) -> str:
    """Restaura la copia con su huella en el nombre; si ya está en línea, la reutiliza (RF-3, RF-4).

    Los ficheros de datos van a ``carpeta`` (``WITH MOVE``): la copia trae las rutas del
    servidor de la empresa, que aquí no existen.

    Solo se reutiliza una base ``ONLINE`` (``sys.databases.state_desc``). Un ``RESTORE`` cortado (el servidor
    apagado, el motor reiniciado a mitad) deja la base de la huella en ``RESTORING``, y cada carga posterior la
    «reutilizaba» sin poder leerla, con un error de ODBC que no decía la causa y sin salida desde la web. En otro
    estado se retira con ``DROP DATABASE`` (vale en cualquier estado, pero los ficheros de una base fuera de línea
    quedan en disco) y se restaura de nuevo con ``REPLACE``, que deja sobrescribir esos ficheros; lo anotado
    (``BASE_VNR_RESTAURADA_DE_NUEVO``) va a ``avisos`` y de ahí al registro del trabajo. Solo se toca la base con el
    nombre de esta huella, nunca otra del motor (RF-6).
    """
    bak = Path(bak).resolve()
    nombre = f'CSG_VNR_{huella(bak)[:16]}'
    cn = conectar(servidor, conectar_odbc=conectar_odbc)
    cur = cn.cursor()
    cur.execute('SELECT state_desc FROM sys.databases WHERE name = ?', nombre)
    fila = cur.fetchone()
    estado = str(fila[0]).strip().upper() if fila and fila[0] is not None else None
    if estado == 'ONLINE':
        return nombre
    if fila:
        cur.execute(f'DROP DATABASE [{nombre}]')
        while cur.nextset():
            pass
        if avisos is not None:
            avisos.append({'code': 'BASE_VNR_RESTAURADA_DE_NUEVO', 'source_id': nombre,
                           'detalle': f'La base {nombre} de «{bak.name}» estaba en {estado or "estado desconocido"} '
                                      '(una restauración anterior no terminó): se retiró y se restauró de nuevo.'})
    if carpeta is None:
        # La del propio motor: su cuenta de servicio siempre puede escribir en ella.
        cur.execute("SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(400))")
        carpeta = Path(str(cur.fetchone()[0]))
    else:
        carpeta = Path(carpeta).resolve()
        carpeta.mkdir(parents=True, exist_ok=True)
    try:
        cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{_literal(bak)}'")
    except Exception as exc:  # noqa: BLE001 - pyodbc.Error y los de los dobles
        if '3201' not in str(exc):
            raise
        permitir_lectura_al_motor(bak, _cuenta_del_motor(cur))
        cur.execute(f"RESTORE FILELISTONLY FROM DISK = N'{_literal(bak)}'")
    ficheros = [(fila[0], fila[2]) for fila in cur.fetchall()]       # LogicalName, Type
    moves = ', '.join(
        f"MOVE N'{_literal(n)}' TO N'{_literal(Path(carpeta) / f'{nombre}_{i}{_ext(t)}')}'"
        for i, (n, t) in enumerate(ficheros))
    # REPLACE: los ficheros de la base retirada pueden seguir en disco con estos mismos nombres.
    cur.execute(f"RESTORE DATABASE [{nombre}] FROM DISK = N'{_literal(bak)}' WITH {moves}, REPLACE, RECOVERY")
    while cur.nextset():
        pass
    return nombre


def _literal(valor) -> str:
    return str(valor).replace("'", "''")


def _ext(tipo) -> str:
    return '.ldf' if str(tipo).strip().upper() == 'L' else '.mdf'


# --------------------------------------------------------------------------- tablas por campos
#: Concepto → campos que la tabla debe tener (RF-7). Los nombres son los del modelo de
#: VNR-GIS, iguales para toda concesionaria; la tabla se busca por ellos.
CAMPOS: dict[str, tuple[str, ...]] = {
    'empresa': ('CodEmpresa', 'Datum', 'ZonaUTM'),
    'salida': ('CodSalidaMT', 'CodSet', 'CodTenNomi', 'EtiquetaSalida'),
    'set': ('CodSet', 'Nombre', 'UTMEste', 'UTMNorte'),
    # El sistema eléctrico con su nombre y su sector típico (055:RF-1): «empSistemaElectrico».
    'sistema': ('CodSisElectrico', 'Nombre', 'CodSectorTipico'),
    'tramo': ('CodTramoMT', 'CodSalidaMT', 'CodTramoMTPadre', 'CodNorma'),
    'vertice': ('CodTramoMT', 'SecVertice', 'UTMEste', 'UTMNorte'),
    'sed': ('CodSed', 'CodSalidaMT', 'PotInstalada', 'UTMEste', 'UTMNorte'),
    'enlace': ('CodNodoMT', 'CodTramoMT', 'CodSed', 'UTMEste', 'UTMNorte'),
    'norma': ('CodNorma', 'Descripcion', 'CodSubComponente'),
    'codigo_secundario': ('CodSecundario', 'CodTipSecundario', 'Descripcion'),
    # La tabla «Tensiones» de la base de red: letra y kV. Una distribuidora no entregó su
    # base de parámetros (donde está «cfgCodigoSecundario») y sin ella ninguna salida tenía
    # tensión; su copia de red sí trae esta tabla (2026-11-01).
    'tension': ('CodTenNomi', 'Tension'),
    'equipo': ('CodEqp', 'CodTramoMT', 'CodTipoEquipoProteccion', 'CodEstadoOperacion'),
    # 080:RF-55: la red BT de cada SED («btTramo», «verTramoBT» y «btSalida» en VNR-GIS). La salida BT pide
    # CodTenNomi3: las tablas de reportes («CB7_0»…) también traen CodSalidaBT, CodSed y EtiquetaSalida.
    'tramo_bt': ('CodTramoBT', 'CodSalidaBT', 'CodTramoBTPadre', 'CodNormaFase'),
    'vertice_bt': ('CodTramoBT', 'SecVertice', 'UTMEste', 'UTMNorte'),
    'salida_bt': ('CodSalidaBT', 'CodSed', 'EtiquetaSalida', 'CodTenNomi3'),
}

#: Tipos de equipo MT de VNR-GIS (``TIPO_EQUIPO_MT`` de los parámetros) que abren o cierran
#: el circuito; el seccionalizador va aparte. Pararrayos y derivaciones no son maniobras.
# 080:RF-35: celdas y derivaciones de bóveda y pedestal se perdían (en una red subterránea, 2026-11-03).
MANIOBRAS = {'IN', 'SE', 'SF', 'SC', 'RE', 'FU', 'CE', 'DB', 'DP'}
SECCIONALIZADORES = {'SL'}
BANCOS = {'BC'}
REGULADORES = {'BR'}
#: 080:RF-39: por decisión del usuario (2026-11-03) no se modelan en la entrada VNR-GIS.
PARARRAYOS = {'PA'}
SECCIONADORES = {'SE', 'SF', 'SC'}
#: Separación del nodo que abre un tramo para poner en serie un regulador (m).
SEPARACION_REGULADOR_M = 1.0


def tablas_por_campos(columnas: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """Concepto → tabla, la que tenga todos sus campos (sin mirar el nombre). Con varias,
    la de menos columnas: la base trae copias «Ada» y de reportes con más campos."""
    norm = {t: {c.casefold() for c in cs} for t, cs in columnas.items()}
    out: dict[str, str] = {}
    for concepto, campos in CAMPOS.items():
        cand = sorted((len(cs), t) for t, cs in norm.items()
                      if all(c.casefold() in cs for c in campos))
        if cand:
            out[concepto] = cand[0][1]
    return out


# --------------------------------------------------------------------------- modelo
@dataclass
class DatosVnr:
    """Las filas de VNR-GIS que hacen falta, como diccionarios (sin SQL: se prueba así)."""

    empresa: list[dict] = field(default_factory=list)
    salidas: list[dict] = field(default_factory=list)
    sets: list[dict] = field(default_factory=list)
    sistemas: list[dict] = field(default_factory=list)
    tramos: list[dict] = field(default_factory=list)
    vertices: list[dict] = field(default_factory=list)
    seds: list[dict] = field(default_factory=list)
    enlaces: list[dict] = field(default_factory=list)
    normas: list[dict] = field(default_factory=list)
    codigos_secundarios: list[dict] = field(default_factory=list)
    equipos: list[dict] = field(default_factory=list)
    tensiones: list[dict] = field(default_factory=list)
    #: 080:RF-55: la red BT, solo si se pide (``leer_datos(con_bt=True)``).
    tramos_bt: list[dict] = field(default_factory=list)
    vertices_bt: list[dict] = field(default_factory=list)
    salidas_bt: list[dict] = field(default_factory=list)
    #: 080:RF-60: lo que ``leer_datos`` contó de la red BT al leerla por bloques: ``leidos`` (tramos BT de la copia),
    #: ``salidas`` (las salidas MT, por su código de VNR-GIS, cuyas filas BT se guardaron; ``None``, todas) y los tramos
    #: cuya SED no cuelga de ninguna salida MT (``sin_salida`` y sus ``ejemplos``), que no se guardan. ``None`` si las
    #: listas BT son las tablas enteras (un ``DatosVnr`` hecho a mano).
    resumen_bt: dict | None = None
    #: 080:RF-60: avisos de la lectura (la memoria estimada de la red BT); ``modelo_canonico`` los da los primeros.
    avisos: list[dict] = field(default_factory=list)
    ilegibles: list[dict] = field(default_factory=list)
    """Tablas o vistas que el motor no pudo leer, con su motivo (se anotan, no bloquean)."""


def _s(fila: Mapping, campo: str) -> str:
    return _sv(fila.get(campo))


def _sv(v) -> str:
    return '' if v is None else str(v).strip()


def _f(fila: Mapping, campo: str) -> float | None:
    return _fv(fila.get(campo))


#: El número finito de un valor, o None: la utilidad común, no una copia (tests/test_util.py).
_fv = finite_or_none


def tensiones_mt(codigos: Sequence[Mapping]) -> dict[str, float]:
    """Letra de ``CodTenNomi`` → kV, por el orden de los códigos de tensión MT (A = el primero)."""
    mt = sorted((_s(c, 'CodSecundario'), _s(c, 'Descripcion')) for c in codigos
                if _s(c, 'CodTipSecundario').upper() == 'MT')
    out = {}
    for i, (_cod, desc) in enumerate(mt):
        m = re.search(r'([\d.,]+)\s*kV', desc, re.I)
        if m:
            out[chr(ord('A') + i)] = float(m.group(1).replace(',', '.'))
    return out


def tensiones_de_tabla(filas: Sequence[Mapping]) -> dict[str, float]:
    """Letra de ``CodTenNomi`` → kV de la tabla «Tensiones» (redondeada: viene en coma flotante
    simple, 22,899999618 kV)."""
    out = {}
    for f in filas:
        letra, kv = _s(f, 'CodTenNomi').upper(), _f(f, 'Tension')
        if letra and kv and kv > 0:
            out[letra] = round(kv, 3)
    return out


def crs_de_empresa(empresa: Sequence[Mapping]) -> str | None:
    """EPSG de la empresa: WGS84 y su zona UTM, hemisferio sur (VNR-GIS es peruano)."""
    for fila in empresa:
        zona = _f(fila, 'ZonaUTM')
        datum = _s(fila, 'Datum').upper().replace(' ', '')
        if zona and datum in ('WGS84', 'WGS-84'):
            return f'EPSG:{32700 + int(zona)}'
        if zona and datum.startswith('PSAD'):
            return f'EPSG:{24860 + int(zona)}'
    return None


def norma_de(descripcion: str) -> tuple[str, float | None, int | None]:
    """(material, sección mm², fases) de la descripción de una norma del Anexo 2."""
    d = descripcion.upper()
    m = re.search(r'(\d)\s*X\s*(\d+(?:[.,]\d+)?)\s*MM2', d)
    fases = int(m.group(1)) if m else None
    seccion = float(m.group(2).replace(',', '.')) if m else None
    material = ('CU' if 'COBRE' in d or ' CU ' in f' {d} ' else
                'AL' if ' AL ' in f' {d} ' or 'ALUMINIO' in d or ' AA ' in f' {d} ' else '')
    return material, seccion, fases


def repartir_ramales_monofasicos(modelo: CanonicalModel, salida: str, avisos: list[dict]) -> None:
    """Reparte los ramales monofásicos de una salida entre las fases A, B y C (054:RF-1, RF-5).

    VNR-GIS dice cuántas fases tiene un tramo, no cuál: todos salían en la A, y en un alimentador rural
    (2026-11-01) cientos de kilómetros de ramales y de SED monofásicas colgaban de la misma fase de la
    troncal; con el flujo desequilibrado la red colapsaba (cargas a 0,0000x-0,29 pu). Cada ramal
    (tramos monofásicos unidos entre sí) va entero a una fase: el de más kVA primero, a la de
    menos kVA; se anota que la fase es deducida. Un ramal con fase ya distinta de la A se respeta.
    """
    tramos = [s for s in modelo.sections if s.feeder_id == salida and len(s.phases or 'ABC') == 1]
    if not tramos:
        return
    padre: dict[str, str] = {}

    def raiz(n: str) -> str:
        while padre.get(n, n) != n:
            padre[n] = padre.get(padre[n], padre[n])
            n = padre[n]
        return n

    # Un nodo que toca un tramo de 2 o 3 fases es la frontera con la troncal: no une ramales
    # (cada ramal que sale de él es otro).
    letras_frontera: dict[str, set[str]] = {}
    for s in modelo.sections:
        if s.feeder_id == salida and len(s.phases or 'ABC') > 1:
            for n in (s.from_node, s.to_node):
                letras_frontera.setdefault(n, set()).update(s.phases or 'ABC')
    frontera = set(letras_frontera)

    def clave(n: str, s) -> str:
        return f'{n}#{s.section_id}' if n in frontera else n

    for s in tramos:
        a, b = raiz(clave(s.from_node, s)), raiz(clave(s.to_node, s))
        padre.setdefault(a, a)
        padre.setdefault(b, b)
        if a != b:
            padre[max(a, b)] = min(a, b)
    cargas = [c for c in modelo.loads if c.feeder_id == salida and len(c.phases or 'ABC') == 1]
    kva: dict[str, float] = {}
    for c in cargas:
        if c.connection_node in padre and c.connection_node not in frontera:
            r = raiz(c.connection_node)
            kva[r] = kva.get(r, 0.0) + float(c.connected_kva or c.kw or 0.0)
    ramales = sorted({raiz(clave(s.from_node, s)) for s in tramos}, key=lambda r: (-kva.get(r, 0.0), r))
    # Un ramal solo puede tomar una fase que tenga el tramo del que sale: uno que cuelga de un
    # tramo bifásico AB no puede ir a la C (caso real, 2026-11-01: la C llevaba el doble de corriente).
    permitidas: dict[str, set[str]] = {}
    for s in tramos:
        for n in (s.from_node, s.to_node):
            if n in frontera:
                r = raiz(clave(s.from_node, s))
                permitidas[r] = permitidas.get(r, {'A', 'B', 'C'}) & letras_frontera[n]
    carga_fase = {'A': 0.0, 'B': 0.0, 'C': 0.0}
    fase_de: dict[str, str] = {}
    for r in ramales:
        opciones = sorted(permitidas.get(r) or {'A', 'B', 'C'})
        f = min(opciones, key=lambda x: (carga_fase[x], x))
        fase_de[r] = f
        carga_fase[f] += kva.get(r, 0.0)
    for s in tramos:
        s.phases = fase_de[raiz(clave(s.from_node, s))]
    for c in cargas:
        if c.connection_node in padre and c.connection_node not in frontera:
            c.phases = fase_de[raiz(c.connection_node)]
    avisos.append({'code': 'FASE_DEDUCIDA', 'source_id': salida,
                   'detalle': f'{len(ramales)} ramales monofásicos repartidos entre A, B y C por kVA '
                              f'instalados (A {carga_fase["A"]:.0f}, B {carga_fase["B"]:.0f}, '
                              f'C {carga_fase["C"]:.0f}): la fuente no dice la fase'})


def coherencia_de_fases(modelo: CanonicalModel, salida: str, cabecera: str,
                        avisos: list[dict]) -> None:
    """Que cada tramo y cada SED tenga solo fases que le llegan desde la cabecera (054:RF-9).

    En un alimentador real (2026-11-01) casi la mitad de sus SED no consumían en el flujo de
    DIgSILENT, con su barra de BT a 0 pu: unos empalmes cortaban ramales enteros. Unos tramos
    trifásicos salían de uno monofásico (la copia clasifica mal ese tramo: tres fases no salen
    de una) y otros ramales monofásicos seguidos quedaban con letras distintas. Se reconstruye
    desde la cabecera, sin bloquear: el hijo con fases que no le llegan toma las del padre; el
    tramo que tiene más fases que su padre las devuelve aguas arriba hasta un tramo que ya las
    tenga, y la SED toma las que le llegan. Cada cambio se anota.
    """
    tramos = [t for t in modelo.sections if t.feeder_id == salida]
    if not tramos:
        return
    cambiados, en_nodo = fases_desde_la_cabecera(
        [(t.section_id, t.from_node, t.to_node, t.phases or 'ABC') for t in tramos], cabecera)
    cambios = len(cambiados)
    for t in tramos:
        t.phases = cambiados.get(t.section_id, t.phases)
    for c in modelo.loads:
        if c.feeder_id != salida:
            continue
        propias = c.phases or 'ABC'
        # La SED no sube fases aguas arriba: sin sufijo de norma se supone trifásica (054:RF-5) y
        # el tramo, que sí dice sus fases, manda. Toma las que le llegan.
        llegan = fases_de_carga_que_llegan(propias, en_nodo.get(c.connection_node, 'ABC'))
        if llegan != propias:
            c.phases = llegan
            cambios += 1
    if cambios:
        avisos.append({'code': 'FASE_RECONSTRUIDA', 'source_id': salida,
                       'detalle': f'{cambios} tramo(s) o SED con fases que no les llegaban desde la '
                                  'cabecera, corregidos aguas arriba o tomando las del tramo padre'})


def fases_de_sed(norma: str, en_el_nodo: str) -> str:
    """Las fases de una SED por el sufijo de su norma (Anexo 2 del regulador, igual para toda
    empresa, 054:RF-1): «01» un trafo monofásico (1×kVA), «02» dos (2×kVA), «03» un banco de tres
    y «04»/«05» trifásica. Las letras son las del tramo que llega a su nodo: una SED monofásica en
    un ramal de la fase A es de la A. Sin sufijo conocido, trifásica (054:RF-5)."""
    m = re.search(r'(\d{2})$', (norma or '').strip())
    n = {'01': 1, '02': 2}.get(m.group(1), 3) if m else 3
    letras = ''.join(f for f in 'ABC' if f in (en_el_nodo or 'ABC')) or 'ABC'
    return (letras + 'ABC'.replace(letras, ''))[:n] if n < 3 else 'ABC'


def _fases(n: int | None, codigo: str) -> str:
    if n is None and len(codigo) >= 1 and codigo[-1].isdigit():
        n = int(codigo[-1])
    return {1: 'A', 2: 'AB'}.get(n or 3, 'ABC')


class _Nodos:
    """Extremos de tramo unidos a menos de ``tol`` metros, con unión de nodos."""

    def __init__(self, tol: float):
        self.tol = tol
        self.celdas: dict[tuple[int, int], list[str]] = defaultdict(list)
        self.xy: dict[str, tuple[float, float]] = {}
        self.padre: dict[str, str] = {}

    def nodo(self, nombre: str, x: float, y: float) -> str:
        cx, cy = round(x / self.tol), round(y / self.tol)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in self.celdas.get((cx + dx, cy + dy), ()):
                    if math.dist((x, y), self.xy[n]) <= self.tol:
                        return self.raiz(n)
        self.celdas[(cx, cy)].append(nombre)
        self.xy[nombre] = (x, y)
        self.padre[nombre] = nombre
        return nombre

    def raiz(self, n: str) -> str:
        while self.padre[n] != n:
            self.padre[n] = self.padre[self.padre[n]]
            n = self.padre[n]
        return n

    def unir(self, a: str, b: str) -> str:
        ra, rb = self.raiz(a), self.raiz(b)
        if ra != rb:
            # Se queda el de menor nombre: determinista.
            ra, rb = sorted((ra, rb))
            self.padre[rb] = ra
        return ra


def codigos_operativos_sed(seds: Sequence[Mapping], avisos: list[dict]) -> dict[str, str]:
    """080:RF-46, RF-47: ``{CodSed: código operativo}``, único y determinista.

    Una distribuidora repite etiquetas (cientos de SED repetidas, 2026-11-03) y DIgSILENT pide
    nombres únicos: la primera por ``CodSed`` la conserva y las siguientes llevan un sufijo.
    """
    codigos: dict[str, str] = {}
    vistas: dict[str, int] = defaultdict(int)
    for sed in sorted(seds, key=lambda s: _s(s, 'CodSed')):
        cod, etiqueta = _s(sed, 'CodSed'), _s(sed, 'EtiquetaCampo')
        if not etiqueta:
            avisos.append({'code': 'SED_SIN_ETIQUETA', 'source_id': cod})
            codigos[cod] = cod
            continue
        vistas[etiqueta.upper()] += 1
        n = vistas[etiqueta.upper()]
        if n > 1:
            avisos.append({'code': 'ETIQUETA_SED_REPETIDA', 'source_id': cod, 'etiqueta': etiqueta})
        codigos[cod] = etiqueta if n == 1 else f'{etiqueta}_{n}'
    return codigos


def codigos_operativos(salidas: Sequence[Mapping], avisos: list[dict]) -> dict[str, str]:
    """``{CodSalidaMT: código operativo}``: el que el operador usa, ``EtiquetaSalida`` (056:RF-7).

    En una distribuidora (2026-11-01) la web listaba los códigos internos de VNR-GIS de sus salidas,
    y el operador las conoce por su etiqueta; su medición de cabecera ya viene con la etiqueta. Sin
    etiqueta, o con una repetida, la salida conserva su código y se anota.
    """
    etiquetas = {_s(f, 'CodSalidaMT'): _s(f, 'EtiquetaSalida') for f in salidas}
    cuenta: dict[str, int] = defaultdict(int)
    for etiqueta in etiquetas.values():
        if etiqueta:
            cuenta[etiqueta.upper()] += 1
    codigos: dict[str, str] = {}
    for salida in sorted(etiquetas):
        etiqueta = etiquetas[salida]
        if not etiqueta:
            avisos.append({'code': 'SALIDA_SIN_ETIQUETA', 'source_id': salida})
            codigos[salida] = salida
        elif cuenta[etiqueta.upper()] > 1 or (etiqueta != salida and etiqueta in etiquetas):
            avisos.append({'code': 'ETIQUETA_REPETIDA', 'source_id': salida, 'etiqueta': etiqueta})
            codigos[salida] = salida
        else:
            codigos[salida] = etiqueta
    return codigos


def estructura_de_salidas(datos: DatosVnr, codigo_de: Mapping[str, str], cargados: set[str]) -> dict[str, dict[str, str]]:
    """Lo que VNR-GIS dice de cada alimentador cargado: su sistema eléctrico y su SET (055:RF-1)."""
    sets = {_s(s, 'CodSet'): s for s in datos.sets}
    sistemas = {_s(s, 'CodSisElectrico'): s for s in datos.sistemas}
    out: dict[str, dict[str, str]] = {}
    for fila in datos.salidas:
        salida = _s(fila, 'CodSalidaMT')
        codigo = codigo_de.get(salida, salida)
        if codigo not in cargados:
            continue
        cod_set, cod_sis = _s(fila, 'CodSet'), _s(fila, 'CodSisElectrico')
        sis = sistemas.get(cod_sis) or {}
        out[codigo] = {'sistema_codigo': cod_sis, 'sistema_nombre': _s(sis, 'Nombre'), 'sector': _s(sis, 'CodSectorTipico'),
                       'set_codigo': cod_set, 'set_nombre': _s(sets.get(cod_set) or {}, 'Nombre')}
    return out


def modelo_canonico(datos: DatosVnr, salidas: Iterable[str] | None = None, *,
                    tolerancia_m: float = TOLERANCIA_M) -> tuple[CanonicalModel, list[dict]]:
    """El modelo canónico de las salidas MT pedidas (todas si ``None``) y lo anotado (RF-9, RF-10).

    La red se arma por la relación padre–hijo de los tramos, que es la de VNR-GIS: cada hijo
    se une al extremo más cercano de su padre; si sus vértices no se tocan (en la copia de
    una distribuidora real, 3 900 de 15 304 hijos quedan a más de 0,5 m), el hueco se anota.

    080:RF-60 (MEM-MT): cada salida se arma con :func:`_canonico_de_la_salida`, lo mismo que hace la exportación en
    flujo (:meth:`RedMtEnDisco.canonico_por_lotes`) con las filas de un lote de salidas.
    """
    pedidas = {s.strip() for s in salidas} if salidas is not None else None
    avisos: list[dict] = list(datos.avisos)
    codigo_de = codigos_operativos(datos.salidas, avisos)
    codigo_de_sed = codigos_operativos_sed(datos.seds, avisos)
    vertices: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for v in datos.vertices:
        x, y = _f(v, 'UTMEste'), _f(v, 'UTMNorte')
        if x is not None and y is not None:
            vertices[_s(v, 'CodTramoMT')].append((int(_f(v, 'SecVertice') or 0), x, y))
    modelo = CanonicalModel()
    modelo.metadata.update(_metadatos_mt(datos))
    tramos_de: dict[str, list[dict]] = defaultdict(list)
    # 080:RF-59: lo que cada salida necesita de las demás tablas sale de índices construidos una sola vez, en el
    # orden de lectura; recorrer las tablas enteras dentro del bucle de salidas era O(salidas × filas).
    normas_por_tension: dict[str, Counter] = defaultdict(Counter)
    for t in datos.tramos:
        tramos_de[_s(t, 'CodSalidaMT')].append(t)
        if _s(t, 'CodNorma'):
            normas_por_tension[_s(t, 'CodTenNomi').upper()][_s(t, 'CodNorma')] += 1
    seds_de: dict[str, list[dict]] = defaultdict(list)
    for s in datos.seds:
        seds_de[_s(s, 'CodSalidaMT')].append(s)
    enlace_de: dict[str, list[dict]] = defaultdict(list)
    for e in datos.enlaces:
        enlace_de[_s(e, 'CodSed')].append(e)
    equipos_de_tramo: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, e in enumerate(datos.equipos):
        equipos_de_tramo[_s(e, 'CodTramoMT')].append((i, e))
    ctx = _contexto_mt(datos, normas_por_tension, tolerancia_m)
    ix = _IndicesMt(tramos_de=tramos_de, vertices=vertices, seds_de=seds_de, enlace_de=enlace_de,
                    equipos_de_tramo=equipos_de_tramo, codigo_de_sed=codigo_de_sed)
    for salida in _salidas_en_orden(datos):
        if pedidas is not None and salida not in pedidas and codigo_de.get(salida) not in pedidas:
            continue
        _canonico_de_la_salida(salida, ctx, ix, modelo, avisos)
    modelo.conductor_types.extend(ctx.conductores[c] for c in sorted(ctx.conductores))
    _tramos_bt(datos, {f.feeder_id for f in modelo.sources}, modelo, avisos)
    _al_codigo_operativo(modelo, codigo_de)
    # El código de VNR-GIS queda en los metadatos para rastrear la salida en la copia.
    modelo.metadata['codigo_vnr'] = {c: s for s, c in codigo_de.items() if c != s}
    modelo.metadata['estructura_fuente'] = estructura_de_salidas(datos, codigo_de, {f.feeder_id for f in modelo.sources})
    return modelo, avisos


@dataclass
class _ContextoMt:
    """080:RF-60 (MEM-MT): lo que el canónico de cada salida MT toma de la red entera, igual con las tablas enteras
    (:func:`modelo_canonico`) que por lotes (:meth:`RedMtEnDisco.canonico_por_lotes`): las tablas pequeñas, la norma más
    usada de cada tensión y lo que las salidas comparten mientras se arman (los tipos de conductor y los tramos mínimos
    de las salidas sin tramos, cuya geometría sigue valiendo para las salidas que se arman después)."""

    kv_de: dict[str, float]
    sets: dict[str, dict]
    normas: dict[str, str]
    fila_de: dict[str, dict]
    normas_por_tension: Mapping[str, Counter]
    tolerancia_m: float
    conductores: dict[str, ConductorType] = field(default_factory=dict)
    sinteticos: dict[str, list[tuple[int, float, float]]] = field(default_factory=dict)


@dataclass
class _IndicesMt:
    """080:RF-59, RF-60 (MEM-MT): las filas de las tablas grandes de la red MT por salida, SED o tramo, en el orden de
    lectura: de la red entera (:func:`modelo_canonico`) o solo las de un lote de salidas (:class:`RedMtEnDisco`)."""

    tramos_de: Mapping[str, list[dict]]
    vertices: dict[str, list[tuple[int, float, float]]]
    seds_de: Mapping[str, list[dict]]
    enlace_de: Mapping[str, list[dict]]
    equipos_de_tramo: Mapping[str, list[tuple[int, dict]]]
    codigo_de_sed: Mapping[str, str]


def _contexto_mt(datos: DatosVnr, normas_por_tension: Mapping[str, Counter], tolerancia_m: float) -> _ContextoMt:
    # La tabla de códigos del regulador manda; lo que no trae, de la tabla «Tensiones» de la red.
    kv_de = {**tensiones_de_tabla(datos.tensiones), **tensiones_mt(datos.codigos_secundarios)}
    fila_de: dict[str, dict] = {}
    for s in datos.salidas:
        fila_de.setdefault(_s(s, 'CodSalidaMT'), s)
    return _ContextoMt(kv_de=kv_de, sets={_s(s, 'CodSet'): s for s in datos.sets},
                       normas={_s(n, 'CodNorma'): _s(n, 'Descripcion') for n in datos.normas}, fila_de=fila_de,
                       normas_por_tension=normas_por_tension, tolerancia_m=tolerancia_m)


def _metadatos_mt(datos: DatosVnr) -> dict:
    crs = crs_de_empresa(datos.empresa)
    return {'source_crs': crs, 'working_crs': crs, 'working_crs_is_projected': crs is not None,
            'company': next((_s(e, 'CodEmpresa') for e in datos.empresa), '')}


def _salidas_en_orden(datos: DatosVnr) -> list[str]:
    """Las salidas MT en el orden en que se arman (por su código de VNR-GIS; una fila repetida se arma dos veces)."""
    return sorted(_s(s, 'CodSalidaMT') for s in datos.salidas)


def _al_codigo_operativo(modelo: CanonicalModel, codigo_de: Mapping[str, str]) -> None:
    """El alimentador, con su código operativo en todo el modelo (056:RF-7)."""
    for lista in (modelo.sources, modelo.sections, modelo.loads, modelo.switches,
                  modelo.capacitors, modelo.transformers, modelo.regulators, modelo.sections_bt):
        for objeto in lista:
            if getattr(objeto, 'feeder_id', '') in codigo_de:
                objeto.feeder_id = codigo_de[objeto.feeder_id]


def _canonico_de_la_salida(salida: str, ctx: _ContextoMt, ix: _IndicesMt, modelo: CanonicalModel,
                           avisos: list[dict]) -> None:
    """El canónico de una salida MT, añadido a ``modelo``, con sus filas de ``ix`` y lo común de ``ctx``."""
    fila = ctx.fila_de[salida]
    letra = _s(fila, 'CodTenNomi').upper()
    kv = ctx.kv_de.get(letra)
    tramos = sorted(ix.tramos_de.get(salida, []), key=lambda t: _s(t, 'CodTramoMT'))
    if not tramos:
        # 080:RF-32: SED sin ningún tramo (caso real, 2026-11-03): su demanda es real y no
        # se pierde. El tramo mínimo se arma en la primera SED ubicada.
        con_lugar = sorted(
            (s for s in ix.seds_de.get(salida, ())
             if None not in (_f(s, 'UTMEste'), _f(s, 'UTMNorte'))),
            key=lambda s: _s(s, 'CodSed'))
        if not con_lugar:
            avisos.append({'code': 'SALIDA_SIN_TRAMOS', 'source_id': salida})
            return
        normas_de_su_tension = Counter()
        for clave in {letra, ''}:
            normas_de_su_tension.update(ctx.normas_por_tension.get(clave, Counter()))
        sintetico = f'{salida}_SED'
        x, y = _f(con_lugar[0], 'UTMEste'), _f(con_lugar[0], 'UTMNorte')
        ix.vertices[sintetico] = ctx.sinteticos[sintetico] = [(0, x, y), (1, x, y)]
        tramos = [{'CodTramoMT': sintetico, 'CodSalidaMT': salida, 'CodTramoMTPadre': '',
                   'CodTenNomi': letra,
                   'CodNorma': max(sorted(normas_de_su_tension),
                                   key=lambda n: normas_de_su_tension[n], default='')}]
        avisos.append({'code': 'SALIDA_SIN_TRAMOS_CON_SED', 'source_id': salida,
                       'sed': len(con_lugar)})
    nodos = _Nodos(ctx.tolerancia_m)
    extremos: dict[str, tuple[str, str]] = {}
    geo: dict[str, list[tuple[float, float]]] = {}
    for t in tramos:
        cod = _s(t, 'CodTramoMT')
        pts = [(x, y) for _sec, x, y in sorted(ix.vertices.get(cod, []))]
        if len(pts) < 2:
            avisos.append({'code': 'TRAMO_SIN_GEOMETRIA', 'source_id': cod})
            continue
        geo[cod] = pts
        extremos[cod] = (nodos.nodo(f'{cod}_0', *pts[0]), nodos.nodo(f'{cod}_1', *pts[-1]))
    # Orientación y unión por el padre: el extremo del hijo más cercano a un extremo
    # del padre es su origen, y se une a él.
    origen: dict[str, int] = {}
    for t in tramos:
        cod, padre = _s(t, 'CodTramoMT'), _s(t, 'CodTramoMTPadre')
        if cod not in geo:
            continue
        if padre and padre in geo:
            d, i, j = min((math.dist(geo[cod][-i], geo[padre][-j]), i, j)
                          for i in (0, 1) for j in (0, 1))
            i_hijo = 0 if i == 0 else 1
            j_padre = 0 if j == 0 else 1
            if d > ctx.tolerancia_m:
                avisos.append({'code': 'HUECO_CON_SU_PADRE', 'source_id': cod,
                               'distancia_m': round(d, 2)})
            nodos.unir(extremos[cod][i_hijo], extremos[padre][j_padre])
            origen[cod] = i_hijo
    # Cabecera: el extremo de un tramo raíz más cercano a su SET (o el primero).
    st = ctx.sets.get(_s(fila, 'CodSet'))
    set_xy = ((_f(st, 'UTMEste'), _f(st, 'UTMNorte')) if st else (None, None))
    raices = [_s(t, 'CodTramoMT') for t in tramos
              if _s(t, 'CodTramoMT') in geo and _s(t, 'CodTramoMTPadre') not in geo]

    def cercania(cod, i):
        if set_xy[0] is None:
            return (0.0 if i == 0 else 1.0, cod)
        return (math.dist(geo[cod][-i if i else 0], set_xy), cod)

    if not raices:
        # La cadena de padres no acaba en un tramo sin padre (un alimentador real, 2026-10-18): la
        # cabecera es el tramo más cercano a su SET.
        raices = [min(geo, key=lambda c: min(cercania(c, 0), cercania(c, 1)))]
        avisos.append({'code': 'SALIDA_SIN_TRAMO_RAIZ', 'source_id': salida,
                       'cabecera': raices[0]})
    _c, raiz, i_raiz = min((cercania(c, i)[0], c, i) for c in raices for i in (0, 1))
    cabecera = nodos.raiz(extremos[raiz][i_raiz])
    for c in raices:
        if c == raiz:
            origen[c] = i_raiz
            continue
        # Otra raíz: un tramo cuyo padre no está; se une al nodo más cercano de la red.
        propios = (nodos.raiz(extremos[c][0]), nodos.raiz(extremos[c][1]))
        candidatos_raiz = [(math.dist(geo[c][-i if i else 0], nodos.xy[n]), i, n)
                           for i in (0, 1) for n in nodos.xy
                           if nodos.raiz(n) not in propios]
        if not candidatos_raiz:
            # 080:RF-33: ya está en el mismo punto que el resto; no hay nada que unir.
            origen[c] = 0
            continue
        d, i, n = min(candidatos_raiz)
        avisos.append({'code': 'TRAMO_SIN_PADRE_UNIDO', 'source_id': c,
                       'distancia_m': round(d, 2)})
        nodos.unir(extremos[c][i], n)
        origen[c] = i
    _unir_islas(nodos, extremos, cabecera, avisos)
    cabecera = nodos.raiz(cabecera)
    modelo.sources.append(Source(source_id=f'SRC_{salida}', node_id=cabecera,
                                 nominal_kv=kv, feeder_id=salida,
                                 source_layer='mtSalida', source_sid=salida))
    usados = set()
    orientado: dict[str, tuple[str, str, list]] = {}
    fases_en_nodo: dict[str, str] = {}                     # 054:RF-1: las del tramo que llega
    if len({nodos.raiz(n) for par in extremos.values() for n in par}) == 1:
        # 080:RF-27: toda la salida en un punto: decenas en una distribuidora, de un tramo de medio metro
        # con una SED. Sin tramo, la salida desaparecía con su demanda; se le da uno mínimo,
        # a dos veces la tolerancia para que no vuelva a unirse.
        cod = min(extremos)
        x, y = nodos.xy[nodos.raiz(extremos[cod][0])]
        final = nodos.nodo(f'{cod}_fin', x + 2 * ctx.tolerancia_m, y)
        extremos[cod] = (extremos[cod][0], final)
        geo[cod] = [(x, y), (x + 2 * ctx.tolerancia_m, y)]
        origen[cod] = 0
        avisos.append({'code': 'SALIDA_DE_TRAMO_NULO', 'source_id': salida, 'tramo': cod})
    for t in tramos:
        cod = _s(t, 'CodTramoMT')
        if cod not in geo:
            continue
        a, b = (nodos.raiz(n) for n in extremos[cod])
        puntos = geo[cod]
        if origen.get(cod, 0) == 1:
            a, b = b, a
            puntos = list(reversed(puntos))
        if a == b:
            avisos.append({'code': 'TRAMO_CERRADO_EN_SI', 'source_id': cod})
            continue
        usados |= {a, b}
        norma = _s(t, 'CodNorma')
        material, seccion, n_fases = norma_de(ctx.normas.get(norma, ''))
        # El tipo es la norma con la letra de tensión («AA05003D»): así lo forman los
        # modelos de la misma red en las otras fuentes y los catálogos de la empresa.
        # Con la norma sola no casaba ninguna ficha (un alimentador real, 2026-10-18).
        tipo = f'{norma}{_s(t, "CodTenNomi").upper() or letra}' if norma else ''
        if tipo and tipo not in ctx.conductores:
            # 080:RF-53: con la descripción de la norma, que dice si es aéreo o cable.
            ctx.conductores[tipo] = ConductorType(
                conductor_code=tipo, material=material, section_mm2=seccion,
                nominal_kv=kv, source_layer='admCodigosNorma', source_id=norma,
                description=ctx.normas.get(norma, ''))
        largo = sum(math.dist(p, q) for p, q in zip(geo[cod], geo[cod][1:]))
        modelo.sections.append(Section(
            section_id=cod, from_node=a, to_node=b, conductor_code=tipo,
            phases=_fases(n_fases, norma), nominal_kv=kv, length_m=round(largo, 3),
            geometry=puntos, source_layer='mtTramo', source_id=cod, feeder_id=salida,
            # 080:RF-55: «NA» en el estado de operación, como en sus equipos: fuera de servicio.
            # 080:RF-55: «NA» en el estado de operación lo abre: «NORMALMENTE ABIERTO» en la
            # leyenda ESTADO_OP_EPS de cfgTablaCodigo. Si no, manda EstadoVNR, con la leyenda
            # ESTADO_VNR de cfgTablaCodigo (E, M y N construidos; P y X no: ``ESTADOS_VNR``).
            status='out_of_service' if _s(t, 'CodEstadoOperacion').upper() == 'NA'
            else estado_o_anota(modelo.metadata, _s(t, 'EstadoVNR')),
            # 080:RF-53: aéreo o cable por el tipo de red (A o S); otro valor se anota.
            overhead=medio_o_anota(modelo.metadata, _s(t, 'CodTipoRed')),
            # Y lo que dice la fuente, tal cual, para serializar el canónico a capas (080:RF-55).
            source_status=('NA' if _s(t, 'CodEstadoOperacion').upper() == 'NA' else _s(t, 'EstadoVNR')),
            source_network_type=_s(t, 'CodTipoRed')))
        orientado[cod] = (a, b, puntos)
        for extremo in (a, b):
            fases_en_nodo[extremo] = ''.join(sorted(set(fases_en_nodo.get(extremo, '')) | set(
                _fases(n_fases, norma))))
    for n in sorted(usados):
        x, y = nodos.xy[n]
        modelo.nodes.append(Node(node_id=n, x=x, y=y, nominal_kv=kv, phases='ABC',
                                 source_layer='verTramoMT', source_id=n))
    # SED: en el nodo de su tramo más cercano al enlace (o a la SED, sin enlace).
    for sed in sorted(ix.seds_de.get(salida, ()),
                      key=lambda s: _s(s, 'CodSed')):
        cod = _s(sed, 'CodSed')
        punto, candidatos = None, []
        for e in ix.enlace_de.get(cod, []):
            tramo = _s(e, 'CodTramoMT')
            if tramo in extremos:
                punto = (_f(e, 'UTMEste'), _f(e, 'UTMNorte'))
                candidatos = [nodos.raiz(n) for n in extremos[tramo]]
                break
        if punto is None or None in punto:
            punto = (_f(sed, 'UTMEste'), _f(sed, 'UTMNorte'))
            candidatos = sorted(usados)
            avisos.append({'code': 'SED_SIN_ENLACE', 'source_id': cod})
        if None in punto or not candidatos:
            avisos.append({'code': 'SED_SIN_UBICACION', 'source_id': cod})
            continue
        nodo = min(candidatos, key=lambda n: (math.dist(nodos.xy[n], punto), n))
        modelo.loads.append(Load(
            load_id=cod, connection_node=nodo, kw=_f(sed, 'MaxDemTotal') or 0.0,
            kvar=0.0, phases=fases_de_sed(_s(sed, 'CodNorma'), fases_en_nodo.get(nodo, 'ABC')),
            nominal_kv=kv, source_layer='Sed', source_id=cod,
            feeder_id=salida, connected_kva=_f(sed, 'PotInstalada'),
            etiqueta=ix.codigo_de_sed.get(cod, cod)))
    repartir_ramales_monofasicos(modelo, salida, avisos)
    coherencia_de_fases(modelo, salida, cabecera, avisos)
    _equipos(salida, orientado, ctx.normas, kv, modelo, avisos, ix.equipos_de_tramo)


def _tramos_bt(datos: DatosVnr, cargadas: set[str], modelo: CanonicalModel, avisos: list[dict]) -> None:
    """080:RF-55: los tramos BT de las SED de las salidas MT cargadas, al canónico, en una sola pasada.

    Cada tramo lleva su SED (por su salida BT), el alimentador MT de la SED, su padre, su norma de fase,
    su geometría por sus vértices y la longitud de esa geometría, como en MT. El estado y el tipo de red
    pasan por las reglas de MT; lo que no tiene regla se cuenta en ``valores_sin_regla_bt``. Un tramo sin
    vértices, o cuya SED no cuelga de ninguna salida de la copia, se anota con su recuento.

    080:RF-60: si ``leer_datos`` leyó la red BT por bloques (``datos.resumen_bt``), las listas BT traen solo lo de las
    salidas pedidas y los tramos sin salida MT llegan contados en el resumen; el resultado es el mismo que con las
    tablas enteras. Pedir aquí una salida cuya red BT no se leyó es un error, no una red BT vacía.
    """
    resumen = datos.resumen_bt
    if not datos.tramos_bt and not (resumen and resumen['leidos']):
        return
    if resumen is not None and resumen['salidas'] is not None and not cargadas <= resumen['salidas']:
        faltan = sorted(cargadas - resumen['salidas'])
        raise ValueError(f'La red BT se leyó sin las salidas {faltan[:EJEMPLOS_DE_AVISO]}: pide a leer_datos las '
                         'mismas salidas que a modelo_canonico.')
    todas = {_s(s, 'CodSalidaMT') for s in datos.salidas}
    salida_de_sed = {_s(s, 'CodSed'): _s(s, 'CodSalidaMT') for s in datos.seds}
    sed_de_salida_bt = {_s(s, 'CodSalidaBT'): _s(s, 'CodSed') for s in datos.salidas_bt}
    vertices: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for v in datos.vertices_bt:
        x, y = _f(v, 'UTMEste'), _f(v, 'UTMNorte')
        if x is not None and y is not None:
            vertices[_s(v, 'CodTramoBT')].append((int(_f(v, 'SecVertice') or 0), x, y))
    sin_geometria: list[str] = []
    sin_salida: list[str] = []
    for t in sorted(datos.tramos_bt, key=lambda t: _s(t, 'CodTramoBT')):
        cod = _s(t, 'CodTramoBT')
        sed = sed_de_salida_bt.get(_s(t, 'CodSalidaBT'), '')
        salida = salida_de_sed.get(sed, '')
        if salida not in todas:
            sin_salida.append(cod)
            continue
        if salida not in cargadas:
            continue
        puntos = [(x, y) for _sec, x, y in sorted(vertices.get(cod, []))]
        if len(puntos) < 2:
            sin_geometria.append(cod)
            continue
        modelo.sections_bt.append(_seccion_bt(
            cod, _s(t, 'CodSalidaBT'), _s(t, 'CodTramoBTPadre'), _s(t, 'CodNormaFase'), _s(t, 'EstadoVNR'),
            _s(t, 'CodTipoRed'), sed, salida, puntos, modelo.metadata))
    # 080:RF-60: los contados al leer por bloques se suman a los de las listas (que ya vienen en orden).
    sin_salida_n = len(sin_salida) + (resumen['sin_salida'] if resumen else 0)
    ejemplos = heapq.nsmallest(EJEMPLOS_DE_AVISO, sin_salida + (resumen['ejemplos'] if resumen else []))
    avisos.extend(_avisos_bt(len(sin_geometria), sin_geometria[:EJEMPLOS_DE_AVISO], sin_salida_n, ejemplos))


def _seccion_bt(cod: str, salida_bt: str, padre: str, norma: str, estado: str, tipo_red: str, sed: str, salida: str,
                puntos: list[tuple[float, float]], metadata: dict) -> LowVoltageSection:
    """080:RF-55: un tramo BT del canónico, con los textos de su fila ya limpios (``_s``) y su geometría ordenada. Lo
    usan la lectura con las tablas enteras (:func:`_tramos_bt`) y la exportación en flujo (:class:`RedBtEnDisco`)."""
    return LowVoltageSection(
        section_id=cod, sed_id=sed, bt_feeder_id=salida_bt, feeder_id=salida, parent_id=padre, conductor_code=norma,
        length_m=round(sum(math.dist(p, q) for p, q in zip(puntos, puntos[1:])), 3), geometry=puntos,
        status=estado_o_anota(metadata, estado, clave=SIN_REGLA_BT),
        overhead=medio_o_anota(metadata, tipo_red, clave=SIN_REGLA_BT),
        source_status=estado, source_network_type=tipo_red, source_layer='btTramo', source_id=cod)


def _avisos_bt(sin_geometria: int, ejemplos_sin_geometria: list[str], sin_salida: int,
               ejemplos_sin_salida: list[str]) -> list[dict]:
    """080:RF-55: los avisos de la red BT, en su orden: tramos sin vértices y tramos cuya SED no cuelga de salida."""
    avisos = []
    if sin_geometria:
        avisos.append({'code': 'TRAMO_BT_SIN_GEOMETRIA', 'tramos': sin_geometria, 'ejemplos': ejemplos_sin_geometria})
    if sin_salida:
        avisos.append({'code': 'TRAMO_BT_SIN_SALIDA_MT', 'tramos': sin_salida, 'ejemplos': ejemplos_sin_salida})
    return avisos


def _regulador_en_serie(e: Mapping, tramo: str, salida: str,
                        orientado: dict[str, tuple[str, str, list]], normas: Mapping[str, str],
                        kv: float | None, lado_carga: bool, modelo: CanonicalModel,
                        avisos: list[dict]) -> None:
    """080:RF-38, RF-41: un banco de regulación de tensión en serie en su tramo.

    Unidades, corriente y tensión salen de la leyenda de VNR-GIS («BANCO DE REGULACION DE TENSION
    x 3, MONOFASICO, In = 200 A, 10 kV»), que no trae ni el rango ni los pasos. Se abre el tramo con
    un nodo y un tramo auxiliar, para que la topología siga conexa; luego se funde en el regulador
    (``puentes.fundir_reguladores``), como los puentes con su seccionador.
    """
    cod, norma = _s(e, 'CodEqp'), _s(e, 'CodNorma')
    leyenda = normas.get(norma, '').upper()
    unidades = re.search(r'X\s*(\d)\b', leyenda)
    corriente = re.search(r'IN\s*=\s*(\d+(?:[.,]\d+)?)\s*A\b', leyenda)
    a, b, puntos = orientado[tramo]
    seccion = next(s for s in reversed(modelo.sections) if s.section_id == tramo)
    (x, y) = puntos[-1] if lado_carga else puntos[0]
    nuevo = f'{cod}_BRN'
    punto_nuevo = (x + SEPARACION_REGULADOR_M, y)
    if lado_carga:
        desde, hasta = nuevo, b
        seccion.to_node = nuevo
        puntos = [*puntos[:-1], punto_nuevo]
        orientado[tramo] = (a, nuevo, puntos)
        tramo_serie = [punto_nuevo, (x, y)]
    else:
        desde, hasta = a, nuevo
        seccion.from_node = nuevo
        puntos = [punto_nuevo, *puntos[1:]]
        orientado[tramo] = (nuevo, b, puntos)
        tramo_serie = [(x, y), punto_nuevo]
    seccion.geometry = puntos
    modelo.nodes.append(Node(node_id=nuevo, x=punto_nuevo[0], y=punto_nuevo[1], nominal_kv=kv,
                             phases='ABC', source_layer='mtEquipo', source_id=cod))
    serie = f'{cod}_BR'
    modelo.sections.append(Section(
        section_id=serie, from_node=desde, to_node=hasta, conductor_code=seccion.conductor_code,
        phases=seccion.phases, nominal_kv=kv, length_m=SEPARACION_REGULADOR_M, geometry=tramo_serie,
        source_layer='mtEquipo', source_id=cod, feeder_id=salida))
    modelo.regulators.append(Regulator(
        regulator_id=cod, connection_node=desde, source_layer='mtEquipo', source_id=cod,
        from_node=desde, to_node=hasta, section_id=serie, feeder_id=salida, nominal_kv=kv,
        corriente_a=float(corriente.group(1).replace(',', '.')) if corriente else None,
        unidades=int(unidades.group(1)) if unidades else 3,
        on_off=0 if _s(e, 'CodEstadoOperacion').upper() == 'NA' else 1, norma=norma))
    avisos.append({'code': 'REGULADOR_DEDUCIDO', 'source_id': cod, 'norma': norma,
                   'detalle': 'rango y pasos deducidos: la leyenda de VNR-GIS no los trae'})


def _equipos(salida: str, orientado: Mapping[str, tuple[str, str, list]],
             normas: Mapping[str, str], kv: float | None, modelo: CanonicalModel,
             avisos: list[dict], equipos_de_tramo: Mapping[str, list[tuple[int, dict]]]) -> None:
    """Maniobras y bancos de la salida, cada uno en su tramo y en el lado más cercano.

    080:RF-59: solo los equipos de los tramos de la salida (``equipos_de_tramo``, construido una vez), en el
    mismo orden que antes: por código y, a igual código, por orden de lectura."""
    propios = [par for tramo in orientado for par in equipos_de_tramo.get(tramo, ())]
    for _i, e in sorted(propios, key=lambda par: (_s(par[1], 'CodEqp'), par[0])):
        tramo, tipo = _s(e, 'CodTramoMT'), _s(e, 'CodTipoEquipoProteccion').upper()
        if tramo not in orientado:
            continue
        a, b, puntos = orientado[tramo]
        x, y = _f(e, 'UTMEste'), _f(e, 'UTMNorte')
        lado_carga = (x is not None and y is not None
                      and math.dist((x, y), puntos[-1]) < math.dist((x, y), puntos[0]))
        nodo = b if lado_carga else a
        cod = _s(e, 'CodEqp')
        abierto = _s(e, 'CodEstadoOperacion').upper() == 'NA'
        # 080:RF-40: un seccionador abierto se queda: define dónde termina la red.
        if tipo in PARARRAYOS or (tipo in SECCIONADORES and not abierto):
            fuera = modelo.metadata.setdefault('equipos_no_modelados', {})
            fuera[tipo] = fuera.get(tipo, 0) + 1
            continue
        if tipo in REGULADORES:
            _regulador_en_serie(e, tramo, salida, orientado, normas, kv, lado_carga, modelo, avisos)
            continue
        if tipo in MANIOBRAS | SECCIONALIZADORES:
            modelo.switches.append(Switch(
                switch_id=cod, connection_node=nodo, kind=tipo,
                on_off=0 if _s(e, 'CodEstadoOperacion').upper() == 'NA' else 1,
                source_layer='mtEquipo', source_id=cod, section_id=tramo,
                location='L' if lado_carga else 'S', sectionalizer=tipo in SECCIONALIZADORES))
        elif tipo in BANCOS:
            # Los kvar, de la descripción de su norma; sin ellos el banco queda sin potencia
            # y se dice (no se inventa).
            # 080:RF-36: «3x200 kVAR» son tres unidades de 200: 600 kvar, no 200.
            m = re.search(r'(?:(\d+)\s*X\s*)?(\d+(?:[.,]\d+)?)\s*KVAR',
                          normas.get(_s(e, 'CodNorma'), '').upper())
            kvar = int(m.group(1) or 1) * float(m.group(2).replace(',', '.')) if m else 0.0
            if not kvar:
                avisos.append({'code': 'BANCO_SIN_KVAR', 'source_id': cod})
            modelo.capacitors.append(Capacitor(
                capacitor_id=cod, connection_node=nodo, kvar=kvar, source_layer='mtEquipo',
                source_id=cod, feeder_id=salida, phases='ABC', nominal_kv=kv,
                status='in_service' if _s(e, 'CodEstadoOperacion').upper() != 'NA'
                else 'out_of_service'))
        else:
            # 080:RF-37: un tipo que no se modela se dice; antes se perdía sin ningún rastro.
            avisos.append({'code': 'EQUIPO_SIN_MODELAR', 'source_id': cod, 'tipo': tipo,
                           'tramo': tramo, 'norma': _s(e, 'CodNorma')})


# --------------------------------------------------------------------------- lectura SQL
def leer_datos(cn_red, cn_param=None, *, con_bt: bool = False,
               salidas: Iterable[str] | None = None) -> DatosVnr:
    """Las tablas por sus campos y sus filas (RF-6: solo SELECT).

    080:RF-55: con ``con_bt`` también la red BT (tramos, vértices y salidas BT). La conversión a un
    simulador modela la red MT y no la pide: la red BT entera es la mayor parte de la base.

    080:RF-60: la red BT se lee por bloques de :data:`FILAS_POR_BLOQUE` filas y solo se guarda la de las
    ``salidas`` MT pedidas (por su código de VNR-GIS o el operativo, como en :func:`modelo_canonico`; ``None``,
    todas). La memoria crece con lo que se pide, no con la empresa entera. A :func:`modelo_canonico` hay que
    pedirle las mismas salidas.
    """
    datos = DatosVnr()

    def filas(cn, cols: Mapping[str, set[str]], tabla: str, campos: Sequence[str]) -> list[dict]:
        cur, campos = _consulta(cn, cols, tabla, campos, datos.ilegibles)
        return [] if cur is None else [dict(zip(campos, fila)) for fila in cur.fetchall()]

    cols_red = _columnas(cn_red)
    red = tablas_por_campos(cols_red)
    extra = _CAMPOS_EXTRA
    for concepto, atributo in _CONCEPTOS_MT:
        if concepto in red:
            campos = CAMPOS[concepto] + extra.get(concepto, ())
            setattr(datos, atributo, filas(cn_red, cols_red, red[concepto], campos))
    if con_bt:
        # 080:RF-60: una tabla BT que no se puede leer se anota en el orden de antes (tramos, vértices, salidas).
        ilegibles_bt: dict[str, list[dict]] = defaultdict(list)

        def en_bloques(concepto: str) -> Iterator[dict]:
            return _en_bloques(cn_red, cols_red, red, concepto, ilegibles_bt[concepto])

        def contar(salidas_mt: frozenset | None) -> dict[str, int]:
            return _contar_red_bt(cn_red, red, salidas_mt)

        _leer_red_bt(datos, en_bloques, salidas, contar if 'tramo_bt' in red else None)
        for concepto in ('tramo_bt', 'vertice_bt', 'salida_bt'):
            datos.ilegibles.extend(ilegibles_bt[concepto])
    _leer_parametros(datos, cn_param, cn_red, filas)
    return datos


#: Las tablas de la red, por concepto, y el campo de :class:`DatosVnr` donde van, en el orden en que se leen.
_CONCEPTOS_MT = (('empresa', 'empresa'), ('salida', 'salidas'), ('set', 'sets'), ('sistema', 'sistemas'),
                 ('tramo', 'tramos'), ('vertice', 'vertices'), ('sed', 'seds'),
                 ('enlace', 'enlaces'), ('equipo', 'equipos'))


def _leer_parametros(datos: DatosVnr, cn_param, cn_red,
                     filas: Callable[[object, Mapping[str, set[str]], str, Sequence[str]], list[dict]]) -> None:
    """Las tablas de parámetros (sistemas, normas, tensiones y códigos secundarios): de la base de parámetros y, lo que
    no traiga, de la de red. Las usan :func:`leer_datos` y :func:`volcar_red_mt`."""
    for cn in ([cn_param] if cn_param is not None else []) + [cn_red]:
        cols_cn = _columnas(cn)
        param = tablas_por_campos(cols_cn)
        if not datos.sistemas and 'sistema' in param:
            datos.sistemas = filas(cn, cols_cn, param['sistema'], CAMPOS['sistema'])
        if not datos.normas and 'norma' in param:
            datos.normas = filas(cn, cols_cn, param['norma'], ('CodNorma', 'Descripcion'))
        if not datos.tensiones and 'tension' in param:
            datos.tensiones = filas(cn, cols_cn, param['tension'], CAMPOS['tension'])
        if not datos.codigos_secundarios and 'codigo_secundario' in param:
            datos.codigos_secundarios = filas(cn, cols_cn, param['codigo_secundario'],
                                              CAMPOS['codigo_secundario'])


#: Campos opcionales que se leen además de los de :data:`CAMPOS`, si la tabla los trae.
_CAMPOS_EXTRA: dict[str, tuple[str, ...]] = {
    'salida': ('CodSisElectrico',), 'sed': ('MaxDemTotal', 'CodNorma', 'EtiquetaCampo'),
    # 080:RF-55: el estado del tramo, si la tabla lo trae (opcional en otra empresa).
    'tramo': ('CodTenNomi', 'CodEstadoOperacion', 'CodTipoRed', 'EstadoVNR'),
    'equipo': ('CodNorma', 'UTMEste', 'UTMNorte'),
    'tramo_bt': ('CodTipoRed', 'Longitud', 'EstadoVNR')}


def _columnas(cn) -> dict[str, set[str]]:
    """Tabla → sus columnas, de ``INFORMATION_SCHEMA``."""
    cur = cn.cursor()
    cur.execute('SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS')
    out: dict[str, set[str]] = defaultdict(set)
    for tabla, col in cur.fetchall():
        out[tabla].add(col)
    return out


def _consulta(cn, cols: Mapping[str, set[str]], tabla: str, campos: Sequence[str],
              ilegibles: list[dict]) -> tuple[object | None, list[str]]:
    """El cursor con el ``SELECT`` de los ``campos`` que la tabla tiene, ya ejecutado; ``None`` si no se puede leer."""
    # Solo los campos que la tabla tiene: los opcionales pueden faltar en otra empresa.
    presentes = {c.casefold() for c in cols[tabla]}
    campos = [c for c in campos if c.casefold() in presentes]
    cur = cn.cursor()
    try:
        cur.execute('SELECT ' + ', '.join(f'[{c}]' for c in campos) + f' FROM [{tabla}]')
    except Exception as exc:  # noqa: BLE001 - el error del controlador ODBC, sea cual sea
        # Una vista que nombra otra base que no vino en la copia (caso real, 2026-11-01:
        # «norEquipoMT» apunta a «VNRGISGART», su base de parámetros, que no se entregó)
        # no tumba la conversión: se anota y se sigue con lo que trae la red.
        ilegibles.append({'tabla': tabla, 'motivo': str(exc)[:300]})
        return None, campos
    return cur, campos


def _en_bloques(cn, cols: Mapping[str, set[str]], red: Mapping[str, str], concepto: str,
                ilegibles: list[dict]) -> Iterator[dict]:
    """080:RF-60: las filas de la tabla de ``concepto`` por bloques (:func:`_por_bloques`); nada si no está."""
    if concepto not in red:
        return iter(())
    cur, campos = _consulta(cn, cols, red[concepto], CAMPOS[concepto] + _CAMPOS_EXTRA.get(concepto, ()), ilegibles)
    return iter(()) if cur is None else _por_bloques(cur, campos)


def _contar_red_bt(cn_red, red: Mapping[str, str], salidas_mt: frozenset | None) -> dict[str, int]:
    """080:RF-60: las filas BT de las salidas MT pedidas (``None``, todas), contadas en el motor sin traerlas. Las
    salidas van como parámetros, nunca escritas en el SQL."""
    tramo, vertice, salida_bt, sed = (red.get(c) for c in ('tramo_bt', 'vertice_bt', 'salida_bt', 'sed'))
    filtro, parametros = '', ()
    if salidas_mt is not None and salida_bt and sed and len(salidas_mt) <= MAX_SALIDAS_EN_LA_CUENTA:
        marcas = ', '.join('?' * len(salidas_mt))
        filtro = (f' WHERE [CodSalidaBT] IN (SELECT [CodSalidaBT] FROM [{salida_bt}] WHERE [CodSed] IN '
                  f'(SELECT [CodSed] FROM [{sed}] WHERE [CodSalidaMT] IN ({marcas})))')
        parametros = tuple(sorted(salidas_mt))
    cuentas = {'tramos': (f'SELECT COUNT(*) FROM [{tramo}]{filtro}', parametros)}
    if vertice:
        de_los_tramos = f' WHERE [CodTramoBT] IN (SELECT [CodTramoBT] FROM [{tramo}]{filtro})' if filtro else ''
        cuentas['vertices'] = (f'SELECT COUNT(*) FROM [{vertice}]{de_los_tramos}', parametros)
    if salida_bt:
        cuentas['salidas_bt'] = (f'SELECT COUNT(*) FROM [{salida_bt}]', ())
    out = {}
    for clave, (sql, params) in cuentas.items():
        cur = cn_red.cursor()
        cur.execute(sql, *params)
        fila = cur.fetchone()
        out[clave] = int(fila[0]) if fila and fila[0] is not None else 0
    return out


def _por_bloques(cur, campos: Sequence[str]) -> Iterator[dict]:
    """080:RF-60: las filas de una consulta ya ejecutada, pedidas al motor de :data:`FILAS_POR_BLOQUE` en
    :data:`FILAS_POR_BLOQUE` (``fetchmany``, de la DB-API): en memoria, un bloque y la fila en curso."""
    for fila in _tuplas_por_bloques(cur):
        yield dict(zip(campos, fila))


def _tuplas_por_bloques(cur) -> Iterator[Sequence]:
    """080:RF-60: las filas tal como las da el motor, por bloques de :data:`FILAS_POR_BLOQUE` (``fetchmany``)."""
    while True:
        bloque = cur.fetchmany(FILAS_POR_BLOQUE)
        if not bloque:
            return
        yield from bloque


#: 080:RF-60: dónde cae una salida BT, por su SED: en una salida MT pedida, en otra de la copia o en ninguna.
_BT_PEDIDA, _BT_OTRA, _BT_SIN_SALIDA = 2, 1, 0


def _memoria_libre() -> int | None:
    """Bytes de memoria disponibles (``psutil``, extra opcional); ``None`` si no se puede saber."""
    try:
        import psutil
    except ImportError:
        return None
    return int(psutil.virtual_memory().available)


def _avisar_memoria_bt(datos: DatosVnr, contar: Callable[[frozenset | None], dict[str, int]],
                       salidas_mt: frozenset | None, mostrar: Callable[[str], None] | None = None) -> None:
    """080:RF-60: antes de leer la red BT, su memoria estimada (las filas contadas en el motor por los bytes medidos)
    frente a la libre. Si no cabe, se avisa con las cifras y la lectura sigue por bloques: es un aviso, no un error."""
    try:
        filas = contar(salidas_mt)
    except Exception as exc:  # noqa: BLE001 - el error del controlador ODBC; sin cuenta no hay estimación, y se dice
        _avisar(datos.avisos, {'code': 'MEMORIA_BT_SIN_ESTIMAR', 'source_id': 'red BT',
                               'detalle': f'no se pudieron contar sus filas: {str(exc)[:300]}'},
                'memoria de la red BT: sin estimar, no se pudieron contar sus filas', mostrar)
        return
    estimados = (filas.get('tramos', 0) * BYTES_POR_TRAMO_BT + filas.get('vertices', 0) * BYTES_POR_VERTICE_BT
                 + filas.get('salidas_bt', 0) * BYTES_POR_SALIDA_BT + FILAS_POR_BLOQUE * BYTES_POR_FILA_DE_BLOQUE)
    _comparar_con_lo_libre(datos.avisos, 'MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE', 'memoria de la red BT', filas,
                           estimados, _memoria_libre(),
                           f'la red BT pedida ({filas.get("tramos", 0)} tramos y {filas.get("vertices", 0)} vértices) '
                           'ocupará más de lo que hay libre; la lectura sigue por bloques', mostrar)


def _gib(n: int) -> str:
    return f'{n / 2**30:.2f} GiB'


def _avisar(avisos: list[dict], aviso: dict, linea: str, mostrar: Callable[[str], None] | None) -> None:
    """080:RF-60 (MEM-BT v2): un aviso de memoria o de disco va a los avisos y además se ve: su línea va al log
    (``logging.warning``) y, si se pide (el CLI), a ``mostrar``."""
    aviso['linea'] = linea
    avisos.append(aviso)
    _log.warning(linea)
    if mostrar is not None:
        mostrar(f'AVISO {aviso["code"]}: {linea}')


def _comparar_con_lo_libre(avisos: list[dict], codigo: str, que: str, filas: dict, estimados: int,
                           libres: int | None, detalle: str, mostrar: Callable[[str], None] | None) -> None:
    """080:RF-60: lo estimado frente a lo libre, con la línea «estimado X GiB, libre Y GiB». Si no cabe, el aviso
    ``codigo``; si cabe, la línea va al log como información (y a ``mostrar``); sin saber lo libre, ``*_SIN_ESTIMAR``.
    """
    if libres is None:
        sin = codigo.split('_ESTIMAD')[0] + '_SIN_ESTIMAR'
        _avisar(avisos, {'code': sin, 'source_id': 'red BT', 'filas': filas, 'bytes_estimados': estimados,
                         'detalle': 'no se sabe lo libre (falta psutil)'},
                f'{que}: estimado {_gib(estimados)}, libre desconocido', mostrar)
        return
    linea = f'{que}: estimado {_gib(estimados)}, libre {_gib(libres)}'
    if estimados > libres:
        _avisar(avisos, {'code': codigo, 'source_id': 'red BT', 'filas': filas, 'bytes_estimados': estimados,
                         'bytes_libres': libres, 'detalle': detalle}, linea, mostrar)
    else:
        _log.info(linea)
        if mostrar is not None:
            mostrar(linea)


def _leer_red_bt(datos: DatosVnr, en_bloques: Callable[[str], Iterator[dict]],
                 salidas: Iterable[str] | None,
                 contar: Callable[[frozenset | None], dict[str, int]] | None = None) -> None:
    """080:RF-60: la red BT de las salidas MT pedidas, leída por bloques, con lo mismo que da :func:`_tramos_bt`
    sobre las tablas enteras.

    Se recorren ``btSalida``, ``btTramo`` y ``verTramoBT`` una vez cada una, en ese orden y por bloques. De cada salida
    BT queda solo dónde cae su SED (un entero por salida BT; la última fila manda, como en el diccionario de antes) y la
    fila de las que caen en una salida pedida; de los tramos, los de una salida pedida, y de los que no cuelgan de
    ninguna salida MT, su recuento y los :data:`EJEMPLOS_DE_AVISO` primeros por código; de los vértices, los de los
    tramos guardados. Las filas se reparten con las mismas claves (``_s``) que :func:`_tramos_bt`.
    """
    todas = {_s(s, 'CodSalidaMT') for s in datos.salidas}
    if salidas is None:
        pedidas, guardadas = todas, None
    else:
        pedidas_ = {s.strip() for s in salidas}
        codigo_de = codigos_operativos(datos.salidas, [])
        pedidas = guardadas = frozenset(s for s in todas if s in pedidas_ or codigo_de.get(s) in pedidas_)
    if contar is not None:
        _avisar_memoria_bt(datos, contar, guardadas)
    salida_de_sed = {_s(s, 'CodSed'): _s(s, 'CodSalidaMT') for s in datos.seds}

    def donde(sed: str) -> int:
        salida = salida_de_sed.get(sed, '')
        return _BT_PEDIDA if salida in pedidas else _BT_OTRA if salida in todas else _BT_SIN_SALIDA

    lugar: dict[str, int] = {}
    filas_salida: dict[str, dict] = {}
    for fila in en_bloques('salida_bt'):
        clave = _s(fila, 'CodSalidaBT')
        lugar[clave] = donde(_s(fila, 'CodSed'))
        if lugar[clave] == _BT_PEDIDA:
            filas_salida[clave] = fila
        else:
            filas_salida.pop(clave, None)
    # Una salida BT que no está en btSalida lleva a la SED '' (como ``dict.get(…, '')`` en _tramos_bt).
    sin_fila = donde('')
    leidos = sin_salida = 0
    ejemplos: list[str] = []
    tramos: list[dict] = []
    for fila in en_bloques('tramo_bt'):
        leidos += 1
        caso = lugar.get(_s(fila, 'CodSalidaBT'), sin_fila)
        if caso == _BT_PEDIDA:
            tramos.append(fila)
        elif caso == _BT_SIN_SALIDA:
            sin_salida += 1
            ejemplos.append(_s(fila, 'CodTramoBT'))
            if len(ejemplos) > 10 * EJEMPLOS_DE_AVISO:
                ejemplos = heapq.nsmallest(EJEMPLOS_DE_AVISO, ejemplos)
    del lugar
    codigos = {_s(t, 'CodTramoBT') for t in tramos}
    datos.vertices_bt = [v for v in en_bloques('vertice_bt') if _s(v, 'CodTramoBT') in codigos]
    datos.tramos_bt = tramos
    datos.salidas_bt = list(filas_salida.values())
    datos.resumen_bt = {'leidos': leidos, 'salidas': guardadas, 'sin_salida': sin_salida,
                        'ejemplos': heapq.nsmallest(EJEMPLOS_DE_AVISO, ejemplos)}


# --------------------------------------------------------------------------- red BT en flujo (080:RF-60, MEM-BT v2)
class RedBtEnDisco:
    """080:RF-60 (MEM-BT v2): la red BT de la copia volcada a un SQLite temporal, para armarla y escribirla por lotes de
    salidas MT sin tenerla entera en memoria.

    :func:`volcar_red_bt` lee ``btSalida``, ``btTramo`` y ``verTramoBT`` una sola vez cada una, por bloques
    (``fetchmany``), y guarda aquí sus filas con los textos ya limpios (``_s``) y los vértices con coordenadas. Después,
    :meth:`secciones` da los tramos BT del canónico por lotes de salidas MT, con lo mismo que :func:`_tramos_bt` sobre
    las tablas enteras: la SED de cada salida BT es la de su última fila, la salida MT es la de esa SED, la geometría es
    la de sus vértices ordenados, y los tramos sin vértices o sin salida MT se cuentan con sus ejemplos de menor código.
    En memoria hay una pieza de :data:`TRAMOS_BT_POR_PIEZA` tramos como mucho, con sus vértices; el resto, en el disco.
    """

    def __init__(self, ruta: Path | str, cn: sqlite3.Connection | None = None):
        # MEM-MT: con ``cn``, en el SQLite temporal de la red MT (:class:`RedMtEnDisco`), que lo cierra: una sola caché.
        self.ruta = Path(ruta)
        self._propio = cn is None
        self.cn = _sqlite_temporal(self.ruta) if cn is None else cn
        self.cn.executescript('''
            CREATE TABLE sbt (seq INTEGER PRIMARY KEY, cod TEXT NOT NULL, sed TEXT NOT NULL);
            CREATE TABLE tbt (seq INTEGER PRIMARY KEY, cod TEXT NOT NULL, clave TEXT NOT NULL, padre TEXT NOT NULL,
                              norma TEXT NOT NULL, estado TEXT NOT NULL, tipo TEXT NOT NULL);
            CREATE TABLE vbt (cod TEXT NOT NULL, sec INTEGER NOT NULL, x REAL NOT NULL, y REAL NOT NULL);
            CREATE TABLE sed_mt (sed TEXT PRIMARY KEY, salida TEXT NOT NULL);
            CREATE TABLE todas (salida TEXT PRIMARY KEY);
            CREATE TEMP TABLE lote (salida TEXT PRIMARY KEY);
            CREATE TEMP TABLE pieza (cod TEXT PRIMARY KEY);
        ''')
        self.leidos = 0
        self._sin_geometria = 0
        self._ejemplos_sin_geometria: list[tuple[str, int]] = []

    def cerrar(self) -> None:
        if self._propio:
            self.cn.close()

    def _insertar(self, sql: str, filas: Iterable[tuple]) -> int:
        return _insertar(self.cn, sql, filas)

    def cargar(self, salidas_bt: Callable[[], tuple[Sequence[str], Iterable[Sequence]]],
               tramos_bt: Callable[[], tuple[Sequence[str], Iterable[Sequence]]],
               vertices_bt: Callable[[], tuple[Sequence[str], Iterable[Sequence]]], seds: Iterable[Mapping],
               salidas_mt: Iterable[Mapping]) -> None:
        """Las filas BT al disco, en el orden de lectura (que decide «la última fila manda»), y lo que hace falta de la
        red MT: la salida de cada SED (la última fila manda, como en el diccionario de :func:`_tramos_bt`) y las salidas
        de la copia. Cada tabla BT es ``(campos, filas)`` y se pide (``salidas_bt()``…) cuando la anterior ya se leyó
        entera: sin MARS, SQL Server no deja dos consultas abiertas en la misma conexión. Las filas van como tuplas, sin
        pasar por un diccionario; un campo que la tabla no trae vale como vacío, igual que ``_s`` y ``_f``."""
        self._insertar('INSERT INTO sbt (cod, sed) VALUES (?, ?)', _textos(*salidas_bt(), ('CodSalidaBT', 'CodSed')))
        self.leidos = self._insertar(
            'INSERT INTO tbt (cod, clave, padre, norma, estado, tipo) VALUES (?, ?, ?, ?, ?, ?)',
            _textos(*tramos_bt(), ('CodTramoBT', 'CodSalidaBT', 'CodTramoBTPadre', 'CodNormaFase', 'EstadoVNR',
                                   'CodTipoRed')))

        def vertices():
            campos, filas = vertices_bt()
            cod, sec, x_, y_ = (_posicion(campos, c) for c in ('CodTramoBT', 'SecVertice', 'UTMEste', 'UTMNorte'))
            for v in filas:
                x, y = _fv(_en(v, x_)), _fv(_en(v, y_))
                if x is not None and y is not None:
                    yield _sv(_en(v, cod)), int(_fv(_en(v, sec)) or 0), x, y

        self._insertar('INSERT INTO vbt (cod, sec, x, y) VALUES (?, ?, ?, ?)', vertices())
        self._insertar('INSERT OR REPLACE INTO sed_mt (sed, salida) VALUES (?, ?)',
                       ((_s(s, 'CodSed'), _s(s, 'CodSalidaMT')) for s in seds))
        self._insertar('INSERT OR IGNORE INTO todas (salida) VALUES (?)', ((_s(s, 'CodSalidaMT'),) for s in salidas_mt))
        # La SED de cada salida BT es la de su última fila (con MAX, SQLite da las demás columnas de esa fila); la
        # salida MT, la de esa SED. Una salida BT sin fila lleva a la SED '' y una SED sin salida, a la salida ''.
        self.cn.executescript('''
            CREATE TABLE sbt_u AS SELECT cod, sed FROM (SELECT cod, sed, MAX(seq) FROM sbt GROUP BY cod);
            CREATE UNIQUE INDEX sbt_u_cod ON sbt_u (cod);
            CREATE TABLE tsal AS SELECT t.seq AS seq, COALESCE(u.sed, '') AS sed, COALESCE(m.salida, '') AS salida
                FROM tbt t LEFT JOIN sbt_u u ON u.cod = t.clave LEFT JOIN sed_mt m ON m.sed = COALESCE(u.sed, '');
            CREATE INDEX tsal_salida ON tsal (salida, seq);
            CREATE INDEX vbt_cod ON vbt (cod);
        ''')
        self.cn.commit()

    def sin_salida(self) -> tuple[int, list[str]]:
        """Los tramos BT cuya SED no cuelga de ninguna salida MT de la copia y sus ejemplos de menor código."""
        fuera = 'WHERE s.salida NOT IN (SELECT salida FROM todas)'
        n = self.cn.execute(f'SELECT COUNT(*) FROM tsal s {fuera}').fetchone()[0]
        ejemplos = [c for (c,) in self.cn.execute(
            f'SELECT t.cod FROM tsal s JOIN tbt t ON t.seq = s.seq {fuera} ORDER BY t.cod LIMIT ?',
            (EJEMPLOS_DE_AVISO,))]
        return int(n), ejemplos

    def secciones(self, cargadas: Iterable[str], codigo_de: Mapping[str, str], metadata: dict, *,
                  lote_salidas: int | None = None, por_pieza: int | None = None
                  ) -> Iterator[list[LowVoltageSection]]:
        """Los tramos BT del canónico de las salidas MT ``cargadas`` (su código de VNR-GIS), por lotes de
        ``lote_salidas`` salidas y en piezas de ``por_pieza`` tramos como mucho, con el alimentador ya en su código
        operativo (``codigo_de``) y lo que no tiene regla anotado en ``metadata``, como :func:`_tramos_bt`. Por
        omisión, :data:`LOTE_SALIDAS` y :data:`TRAMOS_BT_POR_PIEZA`."""
        lote_salidas = LOTE_SALIDAS if lote_salidas is None else lote_salidas
        por_pieza = TRAMOS_BT_POR_PIEZA if por_pieza is None else por_pieza
        if lote_salidas < 1 or por_pieza < 1:
            raise ValueError('el lote de salidas y la pieza de tramos tienen que ser de 1 o más')
        lista = sorted(set(cargadas))
        for i in range(0, len(lista), lote_salidas):
            self.cn.execute('DELETE FROM lote')
            self.cn.executemany('INSERT INTO lote (salida) VALUES (?)', ((s,) for s in lista[i:i + lote_salidas]))
            cur = self.cn.execute(
                'SELECT t.seq, t.cod, t.clave, t.padre, t.norma, t.estado, t.tipo, s.sed, s.salida '
                'FROM tsal s JOIN tbt t ON t.seq = s.seq WHERE s.salida IN (SELECT salida FROM lote) '
                'ORDER BY s.salida, t.cod, t.seq')
            while True:
                filas = cur.fetchmany(por_pieza)
                if not filas:
                    break
                yield self._pieza(filas, codigo_de, metadata)

    def _pieza(self, filas: list[tuple], codigo_de: Mapping[str, str], metadata: dict) -> list[LowVoltageSection]:
        self.cn.execute('DELETE FROM pieza')
        self.cn.executemany('INSERT OR IGNORE INTO pieza (cod) VALUES (?)', ((f[1],) for f in filas))
        vertices: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
        for cod, sec, x, y in self.cn.execute('SELECT v.cod, v.sec, v.x, v.y FROM vbt v JOIN pieza p ON p.cod = v.cod'):
            vertices[cod].append((sec, x, y))
        out = []
        for seq, cod, clave, padre, norma, estado, tipo, sed, salida in filas:
            puntos = [(x, y) for _sec, x, y in sorted(vertices.get(cod, []))]
            if len(puntos) < 2:
                self._sin_geometria += 1
                self._ejemplos_sin_geometria = heapq.nsmallest(
                    EJEMPLOS_DE_AVISO, self._ejemplos_sin_geometria + [(cod, seq)])
                continue
            seccion = _seccion_bt(cod, clave, padre, norma, estado, tipo, sed, salida, puntos, metadata)
            seccion.feeder_id = codigo_de.get(salida, salida)
            out.append(seccion)
        return out

    def avisos(self) -> list[dict]:
        """Los avisos de la red BT, como los de :func:`_tramos_bt`; después de recorrer :meth:`secciones`."""
        if not self.leidos:
            return []
        sin_salida, ejemplos = self.sin_salida()
        return _avisos_bt(self._sin_geometria, [c for c, _seq in self._ejemplos_sin_geometria], sin_salida, ejemplos)


def _posicion(campos: Sequence[str], campo: str) -> int | None:
    return list(campos).index(campo) if campo in campos else None


def _en(fila: Sequence, i: int | None):
    return None if i is None else fila[i]


def _textos(campos: Sequence[str], filas: Iterable[Sequence], quiero: Sequence[str]) -> Iterator[tuple[str, ...]]:
    """Los campos ``quiero`` de cada fila, como textos limpios (``_s``); el que la tabla no trae, vacío."""
    posiciones = [_posicion(campos, c) for c in quiero]
    for fila in filas:
        yield tuple(_sv(_en(fila, i)) for i in posiciones)


def _crudas(cn, cols: Mapping[str, set[str]], red: Mapping[str, str], concepto: str,
            ilegibles: list[dict]) -> tuple[list[str], Iterator[Sequence]]:
    """080:RF-60 (MEM-BT v2): ``(campos, filas)`` de la tabla de ``concepto``, con las filas como tuplas y por bloques
    (``fetchmany``); nada si no está o no se puede leer."""
    if concepto not in red:
        return [], iter(())
    cur, campos = _consulta(cn, cols, red[concepto], CAMPOS[concepto] + _CAMPOS_EXTRA.get(concepto, ()), ilegibles)
    return campos, iter(()) if cur is None else _tuplas_por_bloques(cur)


def volcar_red_bt(cn_red, datos: DatosVnr, ruta: Path | str, *,
                  mostrar: Callable[[str], None] | None = None, seds: Iterable[Mapping] | None = None,
                  cn: sqlite3.Connection | None = None) -> RedBtEnDisco:
    """080:RF-60 (MEM-BT v2): la red BT entera de la copia a un SQLite temporal en ``ruta`` (:class:`RedBtEnDisco`),
    leída una vez por tabla y por bloques; ``datos`` es la red MT ya leída (``leer_datos`` sin ``con_bt``).

    Antes de leerla se cuentan sus filas en el motor (``COUNT``) y se estiman la memoria que tendrá a la vez la
    exportación (dos piezas de :data:`TRAMOS_BT_POR_PIEZA` tramos) y el disco del SQLite: si alguna no cabe, el aviso
    ``MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE`` o ``DISCO_BT_ESTIMADO_SUPERA_EL_LIBRE`` va a ``datos.avisos``, con su
    línea «estimado X GiB, libre Y GiB» en el log y en ``mostrar``. Las tablas ilegibles van a ``datos.ilegibles``.

    MEM-MT: ``seds`` son las SED de la red MT, si no están en ``datos.seds`` (:meth:`RedMtEnDisco.seds`, del disco), y
    ``cn`` el SQLite temporal donde ya está la red MT, para volcar ahí también la BT."""
    cols = _columnas(cn_red)
    red = tablas_por_campos(cols)
    red_bt = RedBtEnDisco(ruta, cn)
    try:
        if 'tramo_bt' in red:
            _avisar_flujo_bt(datos, cn_red, red, Path(ruta).parent, mostrar)
        ilegibles: dict[str, list[dict]] = defaultdict(list)
        def tabla(concepto: str) -> Callable[[], tuple[list[str], Iterator[Sequence]]]:
            return lambda: _crudas(cn_red, cols, red, concepto, ilegibles[concepto])

        red_bt.cargar(tabla('salida_bt'), tabla('tramo_bt'), tabla('vertice_bt'), datos.seds if seds is None else seds,
                      datos.salidas)
        for concepto in ('tramo_bt', 'vertice_bt', 'salida_bt'):
            datos.ilegibles.extend(ilegibles[concepto])
    except BaseException:
        red_bt.cerrar()
        raise
    return red_bt


def _avisar_flujo_bt(datos: DatosVnr, cn_red, red: Mapping[str, str], carpeta: Path,
                     mostrar: Callable[[str], None] | None) -> None:
    """080:RF-60 (MEM-BT v2): la memoria y el disco estimados de la exportación en flujo, frente a lo libre."""
    try:
        filas = _contar_red_bt(cn_red, red, None)
    except Exception as exc:  # noqa: BLE001 - el error del controlador ODBC; sin cuenta no hay estimación, y se dice
        _avisar(datos.avisos, {'code': 'MEMORIA_BT_SIN_ESTIMAR', 'source_id': 'red BT',
                               'detalle': f'no se pudieron contar sus filas: {str(exc)[:300]}'},
                'memoria de la red BT en flujo: sin estimar, no se pudieron contar sus filas', mostrar)
        return
    tramos, vertices = filas.get('tramos', 0), filas.get('vertices', 0)
    en_pieza = min(tramos, 2 * TRAMOS_BT_POR_PIEZA)
    memoria = (en_pieza * BYTES_POR_TRAMO_BT_EN_PIEZA + (vertices * en_pieza // max(tramos, 1))
               * BYTES_POR_VERTICE_BT_EN_PIEZA + FILAS_POR_BLOQUE * BYTES_POR_FILA_DE_BLOQUE)
    _comparar_con_lo_libre(datos.avisos, 'MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE', 'memoria de la red BT en flujo', filas,
                           memoria, _memoria_libre(),
                           f'una pieza de {en_pieza} tramos BT ocupará más de lo que hay libre; la exportación sigue',
                           mostrar)
    disco = (tramos * BYTES_EN_DISCO_POR_TRAMO_BT + vertices * BYTES_EN_DISCO_POR_VERTICE_BT
             + filas.get('salidas_bt', 0) * BYTES_EN_DISCO_POR_SALIDA_BT)
    try:
        libre = shutil.disk_usage(carpeta).free
    except OSError:
        libre = None
    _comparar_con_lo_libre(datos.avisos, 'DISCO_BT_ESTIMADO_SUPERA_EL_LIBRE', 'disco de la red BT en flujo', filas,
                           disco, libre,
                           f'la red BT ({tramos} tramos y {vertices} vértices) no cabe en el disco del temporal; la '
                           'exportación sigue', mostrar)


def _sqlite_temporal(ruta: Path | str) -> sqlite3.Connection:
    """080:RF-60: el SQLite temporal de la exportación en flujo: sin diario ni sincronía (se tira al acabar) y con una
    caché de páginas fija de 8 MiB, que no depende de la empresa."""
    cn = sqlite3.connect(str(ruta))
    for pragma in ('journal_mode=OFF', 'synchronous=OFF', 'temp_store=FILE', 'cache_size=-8192'):
        cn.execute(f'PRAGMA {pragma}')
    return cn


def _insertar(cn: sqlite3.Connection, sql: str, filas: Iterable[tuple]) -> int:
    """Las filas a ``cn`` por bloques de :data:`FILAS_POR_BLOQUE`; da cuántas."""
    n = 0
    filas = iter(filas)
    while True:
        bloque = [f for _i, f in zip(range(FILAS_POR_BLOQUE), filas)]
        if not bloque:
            return n
        cn.executemany(sql, bloque)
        n += len(bloque)


# --------------------------------------------------------------------------- red MT en flujo (080:RF-60, MEM-MT)
#: 080:RF-60 (MEM-MT): las tablas de la red MT que crecen con la empresa; la exportación en flujo las vuelca a disco.
#: Las demás (empresa, salidas, SET, sistemas y las de parámetros) son pequeñas y quedan en memoria.
_MT_EN_DISCO = ('tramo', 'vertice', 'sed', 'enlace', 'equipo')
#: 080:RF-60 (MEM-MT): los campos de esas tablas que el canónico lee como números (``_f``); los demás los lee como
#: textos (``_s``). Lo que no es texto, None ni un real finito va al disco ya pasado por esa misma función, así que el
#: canónico lee lo mismo que antes.
_CAMPOS_MT_NUMERICOS = frozenset({'SecVertice', 'UTMEste', 'UTMNorte', 'PotInstalada', 'MaxDemTotal'})
#: 080:RF-60 (MEM-MT): el campo por el que se piden al disco las filas de un lote: su salida (tramos y SED), su
#: SED (enlaces) o su tramo (equipos).
_CLAVE_DEL_LOTE = {'tramo': 'CodSalidaMT', 'sed': 'CodSalidaMT', 'enlace': 'CodSed', 'equipo': 'CodTramoMT'}
#: 080:RF-60 (MEM-MT): los campos que se guardan siempre limpios, porque el disco busca, ordena o cuenta por ellos.
_CAMPOS_MT_LIMPIOS = {'tramo': ('CodSalidaMT', 'CodNorma', 'CodTenNomi'),
                      'sed': ('CodSalidaMT', 'CodSed', 'EtiquetaCampo'), 'enlace': ('CodSed',), 'equipo': ('CodTramoMT',)}


class RedMtEnDisco:
    """080:RF-60 (MEM-MT): la red MT de la copia volcada a un SQLite temporal, para armar su canónico por lotes de
    salidas MT sin tenerla entera en memoria.

    :func:`volcar_red_mt` lee las tablas como ``leer_datos`` (las mismas, en el mismo orden y con las mismas ilegibles),
    pero las grandes (:data:`_MT_EN_DISCO`: tramos, vértices, SED, enlaces y equipos) una sola vez cada una, por bloques
    (``fetchmany``), y las guarda aquí con los textos ya limpios (``_s``) y los números ya leídos (``_f``); las pequeñas
    quedan en :attr:`datos`. Después, :meth:`canonico_por_lotes` da el canónico de :data:`LOTE_SALIDAS` salidas cada
    vez, con :func:`_canonico_de_la_salida`, la misma función que :func:`modelo_canonico`, y lo que toman de la red sale
    de aquí: los códigos operativos de las SED (con sus avisos), la norma más usada de cada tensión y los tramos mínimos
    de las salidas sin tramos. En memoria está un lote de salidas con sus filas; el resto, en el disco.
    """

    def __init__(self, ruta: Path | str):
        self.ruta = Path(ruta)
        self.cn = _sqlite_temporal(self.ruta)
        self.cn.executescript('''
            CREATE TEMP TABLE mt_lote (salida TEXT PRIMARY KEY);
            CREATE TEMP TABLE mt_lote_tramo (cod TEXT PRIMARY KEY);
            CREATE TEMP TABLE mt_lote_sed (cod TEXT PRIMARY KEY);
        ''')
        #: Las tablas pequeñas, como las da ``leer_datos``; las grandes, vacías (están en el disco).
        self.datos = DatosVnr()
        self.campos: dict[str, list[str]] = {}
        self.filas: dict[str, int] = {}
        self.normas_por_tension: dict[str, Counter] = defaultdict(Counter)
        #: Lo de la red entera, cuando :meth:`canonico_por_lotes` acaba: los avisos (en el orden de
        #: ``modelo_canonico``), el código operativo de cada salida, los metadatos y los tipos de conductor.
        self.avisos: list[dict] = []
        self.codigo_de: dict[str, str] = {}
        self.metadata: dict = {}
        self.conductores: list[ConductorType] = []
        self.lotes = 0

    def cerrar(self) -> None:
        self.cn.close()

    def _columna(self, concepto: str, campo: str) -> str:
        return f'c{self.campos[concepto].index(campo)}'

    def cargar(self, concepto: str, campos: Sequence[str], filas: Iterable[Sequence]) -> None:
        """Las filas de ``concepto`` (tuplas con ``campos``, como las da el motor) al disco, en el orden de lectura."""
        campos = list(campos)
        self.campos[concepto] = campos
        if concepto == 'vertice':
            # Como en ``modelo_canonico``: solo los vértices con coordenadas, con su orden ya como entero.
            self.cn.execute('CREATE TABLE mt_vertice (seq INTEGER PRIMARY KEY, cod TEXT NOT NULL, '
                            'sec INTEGER NOT NULL, x REAL NOT NULL, y REAL NOT NULL)')
            cod, sec, x_, y_ = (_posicion(campos, c) for c in ('CodTramoMT', 'SecVertice', 'UTMEste', 'UTMNorte'))

            def vertices():
                for v in filas:
                    x, y = _fv(_en(v, x_)), _fv(_en(v, y_))
                    if x is not None and y is not None:
                        yield _sv(_en(v, cod)), int(_fv(_en(v, sec)) or 0), x, y

            self.filas[concepto] = _insertar(self.cn, 'INSERT INTO mt_vertice (cod, sec, x, y) VALUES (?, ?, ?, ?)',
                                             vertices())
            return
        limpiar = [_fv if c in _CAMPOS_MT_NUMERICOS else _sv for c in campos]
        columnas = [f'c{i}' for i in range(len(campos))]
        extra = ['etq_up'] if concepto == 'sed' else []
        self.cn.execute(f'CREATE TABLE mt_{concepto} (seq INTEGER PRIMARY KEY, {", ".join(columnas + extra)})')
        normas, tension = _posicion(campos, 'CodNorma'), _posicion(campos, 'CodTenNomi')
        etiqueta = _posicion(campos, 'EtiquetaCampo')

        # Los campos por los que se busca, se ordena o se cuenta en el disco van ya limpios; los demás, tal cual si son
        # texto, None o un real finito (el canónico les aplica _s o _f al leerlos, y dan lo mismo), y limpios si no.
        siempre = [i for i, c in enumerate(campos) if c in _CAMPOS_MT_LIMPIOS.get(concepto, ())]

        def limpias():
            for fila in filas:
                limpia = [v if (type(v) is str or v is None or (type(v) is float and v - v == 0)) else f(v)
                          for f, v in zip(limpiar, fila)]
                for i in siempre:
                    limpia[i] = limpiar[i](fila[i])
                limpia = tuple(limpia)
                if concepto == 'tramo' and normas is not None and limpia[normas]:
                    # 080:RF-32: la norma más usada de cada tensión, para el tramo mínimo de una salida sin tramos.
                    letra = limpia[tension].upper() if tension is not None else ''
                    self.normas_por_tension[letra][limpia[normas]] += 1
                if concepto == 'sed':
                    # La etiqueta en mayúsculas de Python: con ella cuenta ``codigos_operativos_sed`` las repetidas.
                    limpia += ((limpia[etiqueta] if etiqueta is not None else '').upper(),)
                yield limpia

        marcas = ', '.join('?' * (len(columnas) + len(extra)))
        self.filas[concepto] = _insertar(
            self.cn, f'INSERT INTO mt_{concepto} ({", ".join(columnas + extra)}) VALUES ({marcas})', limpias())

    def indexar(self) -> None:
        """Los índices por los que se piden las filas de un lote; después de cargar todas las tablas."""
        for concepto, campo in _CLAVE_DEL_LOTE.items():
            self.cn.execute(f'CREATE INDEX mt_{concepto}_lote ON mt_{concepto} ({self._columna(concepto, campo)}, seq)')
        self.cn.execute('CREATE INDEX mt_vertice_cod ON mt_vertice (cod, seq)')
        self.cn.commit()

    def seds(self) -> Iterator[dict]:
        """Las SED, con su salida MT, en el orden de lectura (para la red BT, que las cruza con sus salidas BT)."""
        cur = self.cn.execute(f'SELECT {self._columna("sed", "CodSed")}, {self._columna("sed", "CodSalidaMT")} '
                              'FROM mt_sed ORDER BY seq')
        while True:
            bloque = cur.fetchmany(FILAS_POR_BLOQUE)
            if not bloque:
                return
            for sed, salida in bloque:
                yield {'CodSed': sed, 'CodSalidaMT': salida}

    def _codigos_operativos_sed(self, avisos: list[dict]) -> None:
        """Lo de :func:`codigos_operativos_sed` sobre la tabla entera, en el disco: el código operativo de cada SED (la
        primera de cada etiqueta, por ``CodSed``, la conserva; las siguientes llevan un sufijo; la última fila de un
        ``CodSed`` repetido manda) y sus avisos, en el mismo orden."""
        cod = self._columna('sed', 'CodSed')
        etq = self._columna('sed', 'EtiquetaCampo') if 'EtiquetaCampo' in self.campos['sed'] else "''"
        self.cn.execute('CREATE TABLE mt_sed_codigo (cod TEXT PRIMARY KEY, codigo TEXT NOT NULL)')
        # ``sorted`` es estable: a igual CodSed, el orden de lectura (seq). En SQLite el texto se ordena por sus bytes
        # UTF-8, que es el orden de los caracteres, como en Python.
        cur = self.cn.execute(
            f'SELECT {cod}, {etq}, CASE WHEN {etq} = \'\' THEN 0 else ROW_NUMBER() OVER '
            f'(PARTITION BY {etq} = \'\', etq_up ORDER BY {cod}, seq) END FROM mt_sed ORDER BY {cod}, seq')

        def codigos():
            while True:
                bloque = cur.fetchmany(FILAS_POR_BLOQUE)
                if not bloque:
                    return
                for codigo, etiqueta, n in bloque:
                    if not etiqueta:
                        avisos.append({'code': 'SED_SIN_ETIQUETA', 'source_id': codigo})
                        yield codigo, codigo
                        continue
                    if n > 1:
                        avisos.append({'code': 'ETIQUETA_SED_REPETIDA', 'source_id': codigo, 'etiqueta': etiqueta})
                    yield codigo, etiqueta if n == 1 else f'{etiqueta}_{n}'

        _insertar(self.cn, 'INSERT OR REPLACE INTO mt_sed_codigo (cod, codigo) VALUES (?, ?)', codigos())
        self.cn.execute(f'CREATE INDEX mt_sed_cod ON mt_sed ({cod})')

    def _dicts(self, concepto: str, donde: str) -> Iterator[tuple[int, dict]]:
        """``(seq, fila)`` de ``concepto`` cuya clave del lote está en la tabla temporal ``donde``, en el orden de
        lectura, con las mismas claves que las filas de ``leer_datos``."""
        campos = self.campos[concepto]
        columnas = ', '.join(f'c{i}' for i in range(len(campos)))
        clave = self._columna(concepto, _CLAVE_DEL_LOTE[concepto])
        cur = self.cn.execute(f'SELECT seq, {columnas} FROM mt_{concepto} WHERE {clave} IN (SELECT * FROM {donde}) '
                              'ORDER BY seq')
        for fila in cur:
            yield fila[0], dict(zip(campos, fila[1:]))

    def _indices(self, lote: Sequence[str], ctx: _ContextoMt) -> _IndicesMt:
        """Las filas del lote de salidas, indexadas como en :func:`modelo_canonico`."""
        cn = self.cn
        cn.execute('DELETE FROM mt_lote')
        cn.executemany('INSERT INTO mt_lote (salida) VALUES (?)', ((s,) for s in sorted(set(lote))))
        tramos_de: dict[str, list[dict]] = defaultdict(list)
        codigos: set[str] = {f'{s}_SED' for s in lote}            # los tramos mínimos de las salidas sin tramos
        for _seq, t in self._dicts('tramo', 'mt_lote'):
            tramos_de[_s(t, 'CodSalidaMT')].append(t)
            codigos.add(_s(t, 'CodTramoMT'))
        cn.execute('DELETE FROM mt_lote_tramo')
        cn.executemany('INSERT INTO mt_lote_tramo (cod) VALUES (?)', ((c,) for c in sorted(codigos)))
        vertices: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
        for cod, sec, x, y in cn.execute('SELECT cod, sec, x, y FROM mt_vertice WHERE cod IN '
                                         '(SELECT cod FROM mt_lote_tramo) ORDER BY seq'):
            vertices[cod].append((sec, x, y))
        # El tramo mínimo de una salida sin tramos de un lote anterior sustituye a los vértices de su código, como en el
        # diccionario único de ``modelo_canonico``.
        for cod in codigos & ctx.sinteticos.keys():
            vertices[cod] = ctx.sinteticos[cod]
        seds_de: dict[str, list[dict]] = defaultdict(list)
        cods_sed: set[str] = set()
        for _seq, s in self._dicts('sed', 'mt_lote'):
            seds_de[_s(s, 'CodSalidaMT')].append(s)
            cods_sed.add(_s(s, 'CodSed'))
        cn.execute('DELETE FROM mt_lote_sed')
        cn.executemany('INSERT INTO mt_lote_sed (cod) VALUES (?)', ((c,) for c in sorted(cods_sed)))
        enlace_de: dict[str, list[dict]] = defaultdict(list)
        for _seq, e in self._dicts('enlace', 'mt_lote_sed'):
            enlace_de[_s(e, 'CodSed')].append(e)
        equipos_de_tramo: dict[str, list[tuple[int, dict]]] = defaultdict(list)
        for seq, e in self._dicts('equipo', 'mt_lote_tramo'):
            equipos_de_tramo[_s(e, 'CodTramoMT')].append((seq, e))
        codigo_de_sed = dict(cn.execute('SELECT cod, codigo FROM mt_sed_codigo WHERE cod IN '
                                        '(SELECT cod FROM mt_lote_sed)'))
        return _IndicesMt(tramos_de=tramos_de, vertices=vertices, seds_de=seds_de, enlace_de=enlace_de,
                          equipos_de_tramo=equipos_de_tramo, codigo_de_sed=codigo_de_sed)

    def canonico_por_lotes(self, *, lote_salidas: int | None = None,
                           tolerancia_m: float = TOLERANCIA_M) -> Iterator[CanonicalModel]:
        """El canónico de la red MT por lotes de ``lote_salidas`` salidas (:data:`LOTE_SALIDAS` por omisión), en el
        orden de :func:`modelo_canonico`: juntos, son su ``modelo_canonico(datos)`` sin la red BT, con los alimentadores
        ya en su código operativo. Todos los lotes comparten el mismo diccionario de metadatos (:attr:`metadata`).

        Al acabar quedan en :attr:`avisos`, :attr:`codigo_de`, :attr:`metadata` y :attr:`conductores` los avisos, los
        códigos, los metadatos (con ``codigo_vnr`` y ``estructura_fuente``) y los tipos de conductor de toda la red."""
        lote_salidas = LOTE_SALIDAS if lote_salidas is None else int(lote_salidas)
        if lote_salidas < 1:
            raise ValueError(f'El lote de salidas tiene que ser de 1 o más (se pidió {lote_salidas}).')
        datos = self.datos
        avisos = self.avisos = list(datos.avisos)
        codigo_de = self.codigo_de = codigos_operativos(datos.salidas, avisos)
        self._codigos_operativos_sed(avisos)
        metadata = self.metadata = _metadatos_mt(datos)
        ctx = _contexto_mt(datos, self.normas_por_tension, tolerancia_m)
        orden = _salidas_en_orden(datos)
        cargadas: set[str] = set()
        self.lotes = 0
        for lote in _lotes_de_salidas(orden, lote_salidas):
            ix = self._indices(lote, ctx)
            modelo = CanonicalModel()
            modelo.metadata = metadata
            for salida in lote:
                _canonico_de_la_salida(salida, ctx, ix, modelo, avisos)
            del ix
            _al_codigo_operativo(modelo, codigo_de)
            cargadas |= {f.feeder_id for f in modelo.sources}
            self.lotes += 1
            yield modelo
            del modelo
        self.conductores = [ctx.conductores[c] for c in sorted(ctx.conductores)]
        metadata['codigo_vnr'] = {c: s for s, c in codigo_de.items() if c != s}
        metadata['estructura_fuente'] = estructura_de_salidas(datos, codigo_de, cargadas)


def _lotes_de_salidas(orden: Sequence[str], lote_salidas: int) -> Iterator[list[str]]:
    """080:RF-60 (MEM-MT): las salidas ya ordenadas en lotes de ``lote_salidas``; una salida repetida en la tabla
    va entera en un lote: su segunda vez se arma viendo lo que dejó la primera en el modelo, como con las tablas
    enteras."""
    i = 0
    while i < len(orden):
        j = min(i + lote_salidas, len(orden))
        while j < len(orden) and orden[j] == orden[j - 1]:
            j += 1
        yield list(orden[i:j])
        i = j


def volcar_red_mt(cn_red, cn_param, ruta: Path | str) -> RedMtEnDisco:
    """080:RF-60 (MEM-MT): la red MT de la copia a un SQLite temporal en ``ruta`` (:class:`RedMtEnDisco`).

    Lee las mismas tablas que ``leer_datos`` sin ``con_bt``, en el mismo orden y con las mismas ilegibles, todas por
    bloques (``fetchmany``) y una detrás de otra (sin MARS, SQL Server no deja dos consultas abiertas): las grandes
    van al disco y las pequeñas quedan en :attr:`RedMtEnDisco.datos`. No hay una consulta por salida."""
    red_mt = RedMtEnDisco(ruta)
    try:
        datos = red_mt.datos

        def filas(cn, cols: Mapping[str, set[str]], tabla: str, campos: Sequence[str]) -> list[dict]:
            cur, campos = _consulta(cn, cols, tabla, campos, datos.ilegibles)
            return [] if cur is None else list(_por_bloques(cur, campos))

        cols_red = _columnas(cn_red)
        red = tablas_por_campos(cols_red)
        for concepto, atributo in _CONCEPTOS_MT:
            campos = CAMPOS[concepto] + _CAMPOS_EXTRA.get(concepto, ())
            if concepto in _MT_EN_DISCO:
                cur = None
                if concepto in red:
                    cur, campos = _consulta(cn_red, cols_red, red[concepto], campos, datos.ilegibles)
                else:
                    campos = CAMPOS[concepto]
                red_mt.cargar(concepto, campos, () if cur is None else _tuplas_por_bloques(cur))
            elif concepto in red:
                setattr(datos, atributo, filas(cn_red, cols_red, red[concepto], campos))
        _leer_parametros(datos, cn_param, cn_red, filas)
        red_mt.indexar()
    except BaseException:
        red_mt.cerrar()
        raise
    return red_mt


def _carpetas(bak: Path, vecinas: Iterable[Path | str]) -> list[Path]:
    return list(dict.fromkeys([bak.parent] + [Path(v) for v in vecinas]))


def config_de(bak: Path | str, vecinas: Iterable[Path | str] = ()) -> dict[str, str]:
    """El ``ConfigBD.config`` de la copia, en su carpeta o en la del original (RF-2)."""
    for carpeta in _carpetas(Path(bak), vecinas):
        config = leer_config_bd(carpeta)
        if config:
            return config
    return {}


def copia_de_parametros(bak: Path | str, vecinas: Iterable[Path | str] = ()) -> Path | None:
    """La copia de la base de parámetros junto a la de red (RF-2): la que dice su
    ``ConfigBD.config`` o, sin él, otra ``.bak`` con «param» en el nombre. Se busca también
    donde estaba el original: la web custodia la copia de red en su ejecución, sola."""
    bak = Path(bak)
    nombre = config_de(bak, vecinas).get('nombreArchBD_param')
    for carpeta in _carpetas(bak, vecinas):
        if nombre and (carpeta / nombre).is_file():
            return carpeta / nombre
    for carpeta in _carpetas(bak, vecinas):
        otras = sorted(p for p in carpeta.glob('*.bak')
                       if p.name != bak.name and 'param' in p.name.casefold())
        if otras:
            return otras[0]
    return None


def cargar_copia(bak: Path | str, *, servidor: str = SERVIDOR,
                 salidas: Iterable[str] | None = None,
                 vecinas: Iterable[Path | str] = ()) -> tuple[CanonicalModel, list[dict], dict]:
    """Restaura la copia (y su base de parámetros), la lee y da el modelo canónico (RF-1 a RF-9).

    ``vecinas``: otras carpetas donde buscar su ``ConfigBD.config`` y su base de parámetros
    (la del fichero original). Devuelve el modelo, lo anotado y el alcance.
    """
    bak = Path(bak)
    vecinas = list(vecinas)
    config = config_de(bak, vecinas)
    de_la_restauracion: list[dict] = []
    base_red = restaurar(bak, servidor=servidor, avisos=de_la_restauracion)
    param_bak = copia_de_parametros(bak, vecinas)
    base_param = restaurar(param_bak, servidor=servidor, avisos=de_la_restauracion) if param_bak else None
    cn_red = conectar(servidor, base_red, autocommit=False)
    cn_param = conectar(servidor, base_param, autocommit=False) if base_param else None
    try:
        datos = leer_datos(cn_red, cn_param)
    finally:
        cn_red.close()
        if cn_param is not None:
            cn_param.close()
    modelo, avisos = modelo_canonico(datos, salidas)
    avisos[:0] = de_la_restauracion               # 023:RF-4: una base que se restauró de nuevo queda anotada
    avisos.extend({'code': 'TABLA_ILEGIBLE', 'source_id': x['tabla'], 'detalle': x['motivo']}
                  for x in datos.ilegibles)
    empresa = config.get('CodEmpresa') or modelo.metadata.get('company') or ''
    modelo.metadata['company'] = empresa
    alcance = {'company': empresa, 'period': config.get('nombreBD', base_red),
               'base_red': base_red, 'base_parametros': base_param,
               'copia_parametros': param_bak.name if param_bak else None,
               'servidor': servidor}
    if param_bak is None:
        avisos.append({'code': 'SIN_BASE_DE_PARAMETROS', 'source_id': bak.name})
    return modelo, avisos, alcance


def _unir_islas(nodos: _Nodos, extremos: Mapping[str, tuple[str, str]], cabecera: str,
                avisos: list[dict]) -> None:
    """Une a la red de la cabecera cada parte que quedó suelta, por su par de nodos más
    cercano, y anota el hueco (RF-10: se reconstruye, no se bloquea).

    Una cadena de padres que no llega a la cabecera deja una isla: SM117 en la copia de
    una distribuidora real (2026-10-18) tenía 257 tramos y 122 SED sin camino a su SET.
    """
    while True:
        vecinos: dict[str, set[str]] = defaultdict(set)
        for a, b in extremos.values():
            ra, rb = nodos.raiz(a), nodos.raiz(b)
            vecinos[ra].add(rb)
            vecinos[rb].add(ra)
        alcanzados, pila = set(), [nodos.raiz(cabecera)]
        while pila:
            n = pila.pop()
            if n not in alcanzados:
                alcanzados.add(n)
                pila.extend(vecinos.get(n, ()))
        sueltos = sorted(set(vecinos) - alcanzados)
        if not sueltos:
            return
        # La isla del primer nodo suelto, entera, y su par más cercano con la red.
        isla, pila = set(), [sueltos[0]]
        while pila:
            n = pila.pop()
            if n not in isla:
                isla.add(n)
                pila.extend(vecinos.get(n, ()))
        d, a, b = min((math.dist(nodos.xy[a], nodos.xy[b]), a, b)
                      for a in sorted(isla) for b in sorted(alcanzados))
        avisos.append({'code': 'ISLA_UNIDA', 'source_id': a, 'nodo_red': b,
                       'distancia_m': round(d, 2), 'nodos': len(isla)})
        nodos.unir(a, b)
