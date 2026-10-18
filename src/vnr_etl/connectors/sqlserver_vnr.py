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
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vnr_etl.models import (Capacitor, CanonicalModel, ConductorType, Load, Node, Section,
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


def restaurar(bak: Path | str, *, servidor: str = SERVIDOR, carpeta: Path | str | None = None,
              conectar_odbc: Callable | None = None) -> str:
    """Restaura la copia con su huella en el nombre; si ya está, la reutiliza (RF-3, RF-4).

    Los ficheros de datos van a ``carpeta`` (``WITH MOVE``): la copia trae las rutas del
    servidor de la empresa, que aquí no existen.
    """
    bak = Path(bak).resolve()
    nombre = f'IGEA_VNR_{huella(bak)[:16]}'
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
    'tramo': ('CodTramoMT', 'CodSalidaMT', 'CodTramoMTPadre', 'CodNorma'),
    'vertice': ('CodTramoMT', 'SecVertice', 'UTMEste', 'UTMNorte'),
    'sed': ('CodSed', 'CodSalidaMT', 'PotInstalada', 'UTMEste', 'UTMNorte'),
    'enlace': ('CodNodoMT', 'CodTramoMT', 'CodSed', 'UTMEste', 'UTMNorte'),
    'norma': ('CodNorma', 'Descripcion', 'CodSubComponente'),
    'codigo_secundario': ('CodSecundario', 'CodTipSecundario', 'Descripcion'),
    'equipo': ('CodEqp', 'CodTramoMT', 'CodTipoEquipoProteccion', 'CodEstadoOperacion'),
}

#: Tipos de equipo MT de VNR-GIS (``TIPO_EQUIPO_MT`` de los parámetros) que abren o cierran
#: el circuito; el seccionalizador va aparte. Pararrayos y derivaciones no son maniobras.
MANIOBRAS = {'IN', 'SE', 'SF', 'SC', 'RE', 'FU'}
SECCIONALIZADORES = {'SL'}
BANCOS = {'BC'}


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
    tramos: list[dict] = field(default_factory=list)
    vertices: list[dict] = field(default_factory=list)
    seds: list[dict] = field(default_factory=list)
    enlaces: list[dict] = field(default_factory=list)
    normas: list[dict] = field(default_factory=list)
    codigos_secundarios: list[dict] = field(default_factory=list)
    equipos: list[dict] = field(default_factory=list)


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


def modelo_canonico(datos: DatosVnr, salidas: Iterable[str] | None = None, *,
                    tolerancia_m: float = TOLERANCIA_M) -> tuple[CanonicalModel, list[dict]]:
    """El modelo canónico de las salidas MT pedidas (todas si ``None``) y lo anotado (RF-9, RF-10).

    La red se arma por la relación padre–hijo de los tramos, que es la de VNR-GIS: cada hijo
    se une al extremo más cercano de su padre; si sus vértices no se tocan (en la copia de
    Electro Dunas, 3 900 de 15 304 hijos quedan a más de 0,5 m), el hueco se anota.
    """
    pedidas = {s.strip() for s in salidas} if salidas is not None else None
    avisos: list[dict] = []
    kv_de = tensiones_mt(datos.codigos_secundarios)
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
        if pedidas is not None and salida not in pedidas:
            continue
        fila = next(s for s in datos.salidas if _s(s, 'CodSalidaMT') == salida)
        letra = _s(fila, 'CodTenNomi').upper()
        kv = kv_de.get(letra)
        tramos = sorted(tramos_de.get(salida, []), key=lambda t: _s(t, 'CodTramoMT'))
        if not tramos:
            avisos.append({'code': 'SALIDA_SIN_TRAMOS', 'source_id': salida})
            continue
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
            d, i, n = min((math.dist(geo[c][-i if i else 0], nodos.xy[n]), i, n)
                          for i in (0, 1) for n in nodos.xy
                          if nodos.raiz(n) not in (nodos.raiz(extremos[c][0]),
                                                   nodos.raiz(extremos[c][1])))
            avisos.append({'code': 'TRAMO_SIN_PADRE_UNIDO', 'source_id': c,
                           'distancia_m': round(d, 2)})
            nodos.unir(extremos[c][i], n)
            origen[c] = i
        modelo.sources.append(Source(source_id=f'SRC_{salida}', node_id=cabecera,
                                     nominal_kv=kv, feeder_id=salida,
                                     source_layer='mtSalida', source_sid=salida))
        usados = set()
        orientado: dict[str, tuple[str, str, list]] = {}
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
                kvar=0.0, phases='ABC', nominal_kv=kv, source_layer='Sed', source_id=cod,
                feeder_id=salida, connected_kva=_f(sed, 'PotInstalada')))
        _equipos(datos, salida, orientado, normas, kv, modelo, avisos)
    modelo.conductor_types.extend(conductores[c] for c in sorted(conductores))
    return modelo, avisos


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
        if tipo in MANIOBRAS | SECCIONALIZADORES:
            modelo.switches.append(Switch(
                switch_id=cod, connection_node=nodo, kind=tipo,
                on_off=0 if _s(e, 'CodEstadoOperacion').upper() == 'NA' else 1,
                source_layer='mtEquipo', source_id=cod, section_id=tramo,
                location='L' if lado_carga else 'S', sectionalizer=tipo in SECCIONALIZADORES))
        elif tipo in BANCOS:
            # Los kvar, de la descripción de su norma; sin ellos el banco queda sin potencia
            # y se dice (no se inventa).
            m = re.search(r'(\d+(?:[.,]\d+)?)\s*KVAR', normas.get(_s(e, 'CodNorma'), '').upper())
            kvar = float(m.group(1).replace(',', '.')) if m else 0.0
            if not kvar:
                avisos.append({'code': 'BANCO_SIN_KVAR', 'source_id': cod})
            modelo.capacitors.append(Capacitor(
                capacitor_id=cod, connection_node=nodo, kvar=kvar, source_layer='mtEquipo',
                source_id=cod, feeder_id=salida, phases='ABC', nominal_kv=kv,
                status='in_service' if _s(e, 'CodEstadoOperacion').upper() != 'NA'
                else 'out_of_service'))


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
        cur.execute('SELECT ' + ', '.join(f'[{c}]' for c in campos) + f' FROM [{tabla}]')
        return [dict(zip(campos, fila)) for fila in cur.fetchall()]

    cols_red = columnas(cn_red)
    red = tablas_por_campos(cols_red)
    extra = {'salida': ('CodSisElectrico',), 'sed': ('MaxDemTotal',),
             'tramo': ('CodTenNomi',),
             'equipo': ('CodNorma', 'UTMEste', 'UTMNorte')}
    for concepto, atributo in (('empresa', 'empresa'), ('salida', 'salidas'), ('set', 'sets'),
                               ('tramo', 'tramos'), ('vertice', 'vertices'), ('sed', 'seds'),
                               ('enlace', 'enlaces'), ('equipo', 'equipos')):
        if concepto in red:
            campos = CAMPOS[concepto] + extra.get(concepto, ())
            setattr(datos, atributo, filas(cn_red, cols_red, red[concepto], campos))
    for cn in ([cn_param] if cn_param is not None else []) + [cn_red]:
        cols_cn = columnas(cn)
        param = tablas_por_campos(cols_cn)
        if not datos.normas and 'norma' in param:
            datos.normas = filas(cn, cols_cn, param['norma'], ('CodNorma', 'Descripcion'))
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
    empresa = config.get('CodEmpresa') or modelo.metadata.get('company') or ''
    modelo.metadata['company'] = empresa
    alcance = {'company': empresa, 'period': config.get('nombreBD', base_red),
               'base_red': base_red, 'base_parametros': base_param,
               'copia_parametros': param_bak.name if param_bak else None,
               'servidor': servidor}
    if param_bak is None:
        avisos.append({'code': 'SIN_BASE_DE_PARAMETROS', 'source_id': bak.name})
    return modelo, avisos, alcance
