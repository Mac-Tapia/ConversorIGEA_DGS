"""VNR-GIS desde la copia de SQL Server (``.bak``) de cualquier concesionaria (spec 023).

VNR-GIS es el sistema del regulador (Osinergmin) con el que todas las concesionarias
entregan su red, con el mismo modelo de datos. La entrega real es una copia de SQL Server
de la base de red, con su base de parámetros y un ``ConfigBD.config`` (Electro Dunas,
2026-10-18: ``ELDU_VNR_24_APR.bak``, 819 MB, 75 tablas). Una copia no se lee sin
restaurarla en un motor de SQL Server: aquí se restaura (``RESTORE … WITH MOVE``), se lee
por ODBC y se arma el modelo canónico, sin nada fijo de una empresa:

* las tablas se reconocen por sus campos, no por su nombre (RF-7);
* la tensión de ``CodTenNomi`` (una letra) sale de los códigos secundarios de tensión MT
  de la base de parámetros, por su orden (A = el primero…): en la copia de Electro Dunas,
  D = 10 kV y G = 22,9 kV, lo que dan sus alimentadores en las otras fuentes;
* el CRS sale del datum y la zona UTM de la empresa (``empEmpresa``); VNR-GIS es peruano,
  hemisferio sur (RF-8);
* material, sección y fases del conductor, de la descripción de su norma (Anexo 2 de la
  Guía del VNR: «RED AEREA CONDUCTOR DE AA O SIMIL. 3x50 mm2»).
"""
from __future__ import annotations

import hashlib
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from convertersmartgrid.fases_red import fases_de_carga_que_llegan, fases_desde_la_cabecera
from vnr_etl.models import (Capacitor, CanonicalModel, ConductorType, Load, Node, Regulator, Section,
                            Source, Switch)

#: Motor por omisión: la instancia de SQL Server Express de la máquina.
SERVIDOR = r'.\SQLEXPRESS'
#: Distancia para dar por unidos dos extremos de tramo (m).
TOLERANCIA_M = 0.5


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
    su extensión: Electro Oriente entregó la suya como «ELOR25_V2», sin «.bak» (2026-11-01)."""
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
            'SQL Server Express (gratuito) y arranque su servicio (023:RF-5). Detalle: '
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
    5, acceso denegado» (Electro Sur Este, 2026-11-02). Las empresas ya restauradas no lo
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
              conectar_odbc: Callable | None = None) -> str:
    """Restaura la copia con su huella en el nombre; si ya está, la reutiliza (RF-3, RF-4).

    Los ficheros de datos van a ``carpeta`` (``WITH MOVE``): la copia trae las rutas del
    servidor de la empresa, que aquí no existen.
    """
    bak = Path(bak).resolve()
    nombre = f'CSG_VNR_{huella(bak)[:16]}'
    cn = conectar(servidor, conectar_odbc=conectar_odbc)
    cur = cn.cursor()
    cur.execute('SELECT name FROM sys.databases WHERE name = ?', nombre)
    if cur.fetchone():
        return nombre
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
    cur.execute(f"RESTORE DATABASE [{nombre}] FROM DISK = N'{_literal(bak)}' WITH {moves}, RECOVERY")
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
    # La tabla «Tensiones» de la base de red: letra y kV. Electro Oriente 2025 no entregó su
    # base de parámetros (donde está «cfgCodigoSecundario») y sin ella ninguna salida tenía
    # tensión; su copia de red sí trae esta tabla (2026-11-01).
    'tension': ('CodTenNomi', 'Tension'),
    'equipo': ('CodEqp', 'CodTramoMT', 'CodTipoEquipoProteccion', 'CodEstadoOperacion'),
}

#: Tipos de equipo MT de VNR-GIS (``TIPO_EQUIPO_MT`` de los parámetros) que abren o cierran
#: el circuito; el seccionalizador va aparte. Pararrayos y derivaciones no son maniobras.
# 080:RF-35: celdas y derivaciones de bóveda y pedestal se perdían (190 en Luz del Sur, 2026-11-03).
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
    ilegibles: list[dict] = field(default_factory=list)
    """Tablas o vistas que el motor no pudo leer, con su motivo (se anotan, no bloquean)."""


def _s(fila: Mapping, campo: str) -> str:
    v = fila.get(campo)
    return '' if v is None else str(v).strip()


def _f(fila: Mapping, campo: str) -> float | None:
    v = fila.get(campo)
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


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

    VNR-GIS dice cuántas fases tiene un tramo, no cuál: todos salían en la A, y en NJA202
    (2026-11-01) sus 698 km de ramales y ~780 SED monofásicas colgaban de la misma fase de la
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
    # tramo bifásico AB no puede ir a la C (NJA202, 2026-11-01: la C llevaba el doble de corriente).
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

    En NJA202 (Electro Oriente, 2026-11-01) 374 de 849 SED no consumían en el flujo de
    DIgSILENT, con su barra de BT a 0 pu: 18 empalmes cortaban ramales enteros. Siete tramos
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

    Luz del Sur repite etiquetas (12 194 distintas en 13 095 SED, 2026-11-03) y DIgSILENT pide
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

    En Electro Oriente (2026-11-01) la web listaba W12882 y L14243, códigos internos de VNR-GIS,
    y el operador los conoce como NJA202 y 0205; su medición de cabecera ya viene con NJA202. Sin
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
    Electro Dunas, 3 900 de 15 304 hijos quedan a más de 0,5 m), el hueco se anota.
    """
    pedidas = {s.strip() for s in salidas} if salidas is not None else None
    avisos: list[dict] = []
    codigo_de = codigos_operativos(datos.salidas, avisos)
    codigo_de_sed = codigos_operativos_sed(datos.seds, avisos)
    # La tabla de códigos del regulador manda; lo que no trae, de la tabla «Tensiones» de la red.
    kv_de = {**tensiones_de_tabla(datos.tensiones), **tensiones_mt(datos.codigos_secundarios)}
    crs = crs_de_empresa(datos.empresa)
    sets = {_s(s, 'CodSet'): s for s in datos.sets}
    normas = {_s(n, 'CodNorma'): _s(n, 'Descripcion') for n in datos.normas}
    vertices: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for v in datos.vertices:
        x, y = _f(v, 'UTMEste'), _f(v, 'UTMNorte')
        if x is not None and y is not None:
            vertices[_s(v, 'CodTramoMT')].append((int(_f(v, 'SecVertice') or 0), x, y))
    modelo = CanonicalModel()
    modelo.metadata.update({'source_crs': crs, 'working_crs': crs,
                            'working_crs_is_projected': crs is not None,
                            'company': next((_s(e, 'CodEmpresa') for e in datos.empresa), '')})
    tramos_de: dict[str, list[dict]] = defaultdict(list)
    for t in datos.tramos:
        tramos_de[_s(t, 'CodSalidaMT')].append(t)
    conductores: dict[str, ConductorType] = {}
    for salida in sorted(_s(s, 'CodSalidaMT') for s in datos.salidas):
        if pedidas is not None and salida not in pedidas and codigo_de.get(salida) not in pedidas:
            continue
        fila = next(s for s in datos.salidas if _s(s, 'CodSalidaMT') == salida)
        letra = _s(fila, 'CodTenNomi').upper()
        kv = kv_de.get(letra)
        tramos = sorted(tramos_de.get(salida, []), key=lambda t: _s(t, 'CodTramoMT'))
        if not tramos:
            # 080:RF-32: SED sin ningún tramo (748055397 de Luz del Sur): su demanda es real y no
            # se pierde. El tramo mínimo se arma en la primera SED ubicada.
            con_lugar = sorted(
                (s for s in datos.seds if _s(s, 'CodSalidaMT') == salida
                 and None not in (_f(s, 'UTMEste'), _f(s, 'UTMNorte'))),
                key=lambda s: _s(s, 'CodSed'))
            if not con_lugar:
                avisos.append({'code': 'SALIDA_SIN_TRAMOS', 'source_id': salida})
                continue
            normas_de_su_tension = Counter(_s(t, 'CodNorma') for t in datos.tramos
                                           if _s(t, 'CodTenNomi').upper() in (letra, '') and _s(t, 'CodNorma'))
            sintetico = f'{salida}_SED'
            x, y = _f(con_lugar[0], 'UTMEste'), _f(con_lugar[0], 'UTMNorte')
            vertices[sintetico] = [(0, x, y), (1, x, y)]
            tramos = [{'CodTramoMT': sintetico, 'CodSalidaMT': salida, 'CodTramoMTPadre': '',
                       'CodTenNomi': letra,
                       'CodNorma': max(sorted(normas_de_su_tension),
                                       key=lambda n: normas_de_su_tension[n], default='')}]
            avisos.append({'code': 'SALIDA_SIN_TRAMOS_CON_SED', 'source_id': salida,
                           'sed': len(con_lugar)})
        nodos = _Nodos(tolerancia_m)
        extremos: dict[str, tuple[str, str]] = {}
        geo: dict[str, list[tuple[float, float]]] = {}
        for t in tramos:
            cod = _s(t, 'CodTramoMT')
            pts = [(x, y) for _sec, x, y in sorted(vertices.get(cod, []))]
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
                if d > tolerancia_m:
                    avisos.append({'code': 'HUECO_CON_SU_PADRE', 'source_id': cod,
                                   'distancia_m': round(d, 2)})
                nodos.unir(extremos[cod][i_hijo], extremos[padre][j_padre])
                origen[cod] = i_hijo
        # Cabecera: el extremo de un tramo raíz más cercano a su SET (o el primero).
        st = sets.get(_s(fila, 'CodSet'))
        set_xy = ((_f(st, 'UTMEste'), _f(st, 'UTMNorte')) if st else (None, None))
        raices = [_s(t, 'CodTramoMT') for t in tramos
                  if _s(t, 'CodTramoMT') in geo and _s(t, 'CodTramoMTPadre') not in geo]

        def cercania(cod, i):
            if set_xy[0] is None:
                return (0.0 if i == 0 else 1.0, cod)
            return (math.dist(geo[cod][-i if i else 0], set_xy), cod)

        if not raices:
            # La cadena de padres no acaba en un tramo sin padre (IN111 en la copia de
            # Electro Dunas, 2026-10-18): la cabecera es el tramo más cercano a su SET.
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
            # 080:RF-27: toda la salida en un punto: 47 de Electro Sur Este, de un tramo de 0,5 m
            # con una SED. Sin tramo, la salida desaparecía con su demanda; se le da uno mínimo,
            # a dos veces la tolerancia para que no vuelva a unirse.
            cod = min(extremos)
            x, y = nodos.xy[nodos.raiz(extremos[cod][0])]
            final = nodos.nodo(f'{cod}_fin', x + 2 * tolerancia_m, y)
            extremos[cod] = (extremos[cod][0], final)
            geo[cod] = [(x, y), (x + 2 * tolerancia_m, y)]
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
            material, seccion, n_fases = norma_de(normas.get(norma, ''))
            # El tipo es la norma con la letra de tensión («AA05003D»): así lo forman los
            # modelos de la misma red en las otras fuentes y los catálogos de la empresa.
            # Con la norma sola no casaba ninguna ficha (IN111, 2026-10-18).
            tipo = f'{norma}{_s(t, "CodTenNomi").upper() or letra}' if norma else ''
            if tipo and tipo not in conductores:
                conductores[tipo] = ConductorType(
                    conductor_code=tipo, material=material, section_mm2=seccion,
                    nominal_kv=kv, source_layer='admCodigosNorma', source_id=norma)
            largo = sum(math.dist(p, q) for p, q in zip(geo[cod], geo[cod][1:]))
            modelo.sections.append(Section(
                section_id=cod, from_node=a, to_node=b, conductor_code=tipo,
                phases=_fases(n_fases, norma), nominal_kv=kv, length_m=round(largo, 3),
                geometry=puntos, source_layer='mtTramo', source_id=cod, feeder_id=salida))
            orientado[cod] = (a, b, puntos)
            for extremo in (a, b):
                fases_en_nodo[extremo] = ''.join(sorted(set(fases_en_nodo.get(extremo, '')) | set(
                    _fases(n_fases, norma))))
        for n in sorted(usados):
            x, y = nodos.xy[n]
            modelo.nodes.append(Node(node_id=n, x=x, y=y, nominal_kv=kv, phases='ABC',
                                     source_layer='verTramoMT', source_id=n))
        # SED: en el nodo de su tramo más cercano al enlace (o a la SED, sin enlace).
        enlace_de = defaultdict(list)
        for e in datos.enlaces:
            enlace_de[_s(e, 'CodSed')].append(e)
        for sed in sorted((s for s in datos.seds if _s(s, 'CodSalidaMT') == salida),
                          key=lambda s: _s(s, 'CodSed')):
            cod = _s(sed, 'CodSed')
            punto, candidatos = None, []
            for e in enlace_de.get(cod, []):
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
                etiqueta=codigo_de_sed.get(cod, cod)))
        repartir_ramales_monofasicos(modelo, salida, avisos)
        coherencia_de_fases(modelo, salida, cabecera, avisos)
        _equipos(datos, salida, orientado, normas, kv, modelo, avisos)
    modelo.conductor_types.extend(conductores[c] for c in sorted(conductores))
    # El alimentador, con su código operativo en todo el modelo (056:RF-7); el de VNR-GIS queda
    # en los metadatos para rastrear la salida en la copia.
    for lista in (modelo.sources, modelo.sections, modelo.loads, modelo.switches,
                  modelo.capacitors, modelo.transformers, modelo.regulators):
        for objeto in lista:
            if getattr(objeto, 'feeder_id', '') in codigo_de:
                objeto.feeder_id = codigo_de[objeto.feeder_id]
    modelo.metadata['codigo_vnr'] = {c: s for s, c in codigo_de.items() if c != s}
    modelo.metadata['estructura_fuente'] = estructura_de_salidas(datos, codigo_de, {f.feeder_id for f in modelo.sources})
    return modelo, avisos


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


def _equipos(datos: DatosVnr, salida: str, orientado: Mapping[str, tuple[str, str, list]],
             normas: Mapping[str, str], kv: float | None, modelo: CanonicalModel,
             avisos: list[dict]) -> None:
    """Maniobras y bancos de la salida, cada uno en su tramo y en el lado más cercano."""
    for e in sorted(datos.equipos, key=lambda e: _s(e, 'CodEqp')):
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
def leer_datos(cn_red, cn_param=None) -> DatosVnr:
    """Las tablas por sus campos y sus filas (RF-6: solo SELECT)."""
    datos = DatosVnr()

    def columnas(cn) -> dict[str, set[str]]:
        cur = cn.cursor()
        cur.execute('SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS')
        out: dict[str, set[str]] = defaultdict(set)
        for tabla, col in cur.fetchall():
            out[tabla].add(col)
        return out

    def filas(cn, cols: Mapping[str, set[str]], tabla: str, campos: Sequence[str]) -> list[dict]:
        # Solo los campos que la tabla tiene: los opcionales pueden faltar en otra empresa.
        presentes = {c.casefold() for c in cols[tabla]}
        campos = [c for c in campos if c.casefold() in presentes]
        cur = cn.cursor()
        try:
            cur.execute('SELECT ' + ', '.join(f'[{c}]' for c in campos) + f' FROM [{tabla}]')
        except Exception as exc:  # noqa: BLE001 - el error del controlador ODBC, sea cual sea
            # Una vista que nombra otra base que no vino en la copia (Electro Oriente 2025:
            # «norEquipoMT» apunta a «VNRGISGART», su base de parámetros, que no se entregó)
            # no tumba la conversión: se anota y se sigue con lo que trae la red.
            datos.ilegibles.append({'tabla': tabla, 'motivo': str(exc)[:300]})
            return []
        return [dict(zip(campos, fila)) for fila in cur.fetchall()]

    cols_red = columnas(cn_red)
    red = tablas_por_campos(cols_red)
    extra = {'salida': ('CodSisElectrico',), 'sed': ('MaxDemTotal', 'CodNorma', 'EtiquetaCampo'),
             'tramo': ('CodTenNomi',),
             'equipo': ('CodNorma', 'UTMEste', 'UTMNorte')}
    for concepto, atributo in (('empresa', 'empresa'), ('salida', 'salidas'), ('set', 'sets'), ('sistema', 'sistemas'),
                               ('tramo', 'tramos'), ('vertice', 'vertices'), ('sed', 'seds'),
                               ('enlace', 'enlaces'), ('equipo', 'equipos')):
        if concepto in red:
            campos = CAMPOS[concepto] + extra.get(concepto, ())
            setattr(datos, atributo, filas(cn_red, cols_red, red[concepto], campos))
    for cn in ([cn_param] if cn_param is not None else []) + [cn_red]:
        cols_cn = columnas(cn)
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
    return datos


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
    base_red = restaurar(bak, servidor=servidor)
    param_bak = copia_de_parametros(bak, vecinas)
    base_param = restaurar(param_bak, servidor=servidor) if param_bak else None
    cn_red = conectar(servidor, base_red, autocommit=False)
    cn_param = conectar(servidor, base_param, autocommit=False) if base_param else None
    try:
        datos = leer_datos(cn_red, cn_param)
    finally:
        cn_red.close()
        if cn_param is not None:
            cn_param.close()
    modelo, avisos = modelo_canonico(datos, salidas)
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
    Electro Dunas (2026-10-18) tenía 257 tramos y 122 SED sin camino a su SET.
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
