"""Cargas en un proyecto existente de DIgSILENT: lectura de los libros y plan (spec 004).

Este módulo es aparte de la conversión. Antes, el plan se armaba con el modelo del TXT
o la MDB cargado en la web: sin esas entradas no se podía actualizar ni una demanda, y
la SED «no existía» si el proyecto venía de otra conversión. Ahora la web solo valida
el Excel; qué SED coincide y a qué barra se conecta una carga nueva lo decide el guion
``tools/cargas_pf.py`` mirando el propio proyecto de DIgSILENT (spec 004, RF-1).

Una fila con error no detiene las demás: se informa y el resto sigue. Una SED que no
coincide en el proyecto se omite allí, no aquí (RF-7).
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .loads import (
    LoadTemplateError, SUPPORTED_SUFFIXES, normalise_header, parse_number, power_conflict,
    resolve_power, canonical_columns, read_sheet,
)

SCHEMA = 'convertersmartgrid-cargas-pf-v1'

DEMANDA_COLUMNS = ('SED', 'Kw', 'Kvar', '(kVA)', 'FP', 'accion', 'observaciones')
NUEVA_COLUMNS = (
    'SED', 'alimentador', 'barra', 'Lat', 'Lon', 'CoordX', 'CoordY', 'kVA_instalado',
    'Kw', 'Kvar', '(kVA)', 'FP', 'tipo_linea', 'tension_bt_kv', 'observaciones', 'anio_ingreso',
)

# Columnas propias de la carga nueva, con sus variantes de grafía (cabecera normalizada).
NUEVA_ALIASES = {
    'alimentador': 'alimentador', 'feeder': 'alimentador',
    'barra': 'barra', 'nodo': 'barra', 'nodoconexion': 'barra', 'nodeid': 'barra',
    'terminal': 'barra',
    'lat': 'Lat', 'latitud': 'Lat', 'latitude': 'Lat', 'gpslat': 'Lat',
    'lon': 'Lon', 'long': 'Lon', 'longitud': 'Lon', 'longitude': 'Lon', 'gpslon': 'Lon',
    'coordx': 'CoordX', 'x': 'CoordX', 'este': 'CoordX', 'easting': 'CoordX',
    'coordy': 'CoordY', 'y': 'CoordY', 'norte': 'CoordY', 'northing': 'CoordY',
    'kvainstalado': 'kVA_instalado', 'kvainst': 'kVA_instalado', 'trafo': 'kVA_instalado',
    'tipolinea': 'tipo_linea', 'conductor': 'tipo_linea', 'cable': 'tipo_linea',
    'tensionbtkv': 'tension_bt_kv', 'tensionbt': 'tension_bt_kv', 'btkv': 'tension_bt_kv',
    'kvbt': 'tension_bt_kv',
    'observaciones': 'observaciones', 'obs': 'observaciones',
    # Libro de planificación (SI213, 2026-10-12): la carga no tiene SED aún y se nombra
    # por su descripción; el alimentador va como «TRONCAL».
    'descripcion': 'nombre', 'nombre': 'nombre', 'proyecto': 'nombre', 'cliente': 'nombre',
    'troncal': 'alimentador',
    # 093:RF-1: la sigla con que la distribuidora identifica la carga (PI_15) la nombra; con la
    # descripción, AL209 (2026-11-06) confundía dos clientes de cemento.
    'siglasdecarga': 'sigla', 'siglas': 'sigla', 'sigla': 'sigla', 'siglasdelacarga': 'sigla',
    # 030:RF-10: año de ingreso, calendario (2030) o del PIDE (4); con o sin ñ.
    'añodeingreso': 'anio_ingreso', 'añoingreso': 'anio_ingreso', 'anodeingreso': 'anio_ingreso',
    'anoingreso': 'anio_ingreso', 'aniodeingreso': 'anio_ingreso', 'anioingreso': 'anio_ingreso',
    'ingreso': 'anio_ingreso', 'añoentrada': 'anio_ingreso', 'anoentrada': 'anio_ingreso',
    # 030:RF-13: el total de una carga fraccionada es su demanda.
    'total': 'Kw', 'totalkw': 'Kw', 'kwtotal': 'Kw', 'demandatotal': 'Kw', 'potenciatotal': 'Kw',
}

#: 030:RF-13: una cabecera que es un año (calendario o del PIDE), con o sin «año» delante.
_ANIO_DE_ETAPA = re.compile(r'^(?:año|ano|anio)?(\d{1,4})$')

# Potencias normalizadas de transformador (IEC 60076-1, serie R10) para deducir el kVA
# instalado de una carga que solo trae su demanda (RF-52). Se repite ×10 hasta cubrirla.
SERIE_R10_KVA = (10, 12.5, 16, 20, 25, 31.5, 40, 50, 63, 80)


def _columna_por_patron(clave: str) -> str:
    """Nombre canónico de una cabecera que no es un alias exacto (RF-51).

    «DEM PROY (KW)» o «COORDENADAS UTM (X)» no se pueden listar todas: se reconoce la
    unidad o el eje al final. El kVA no, porque puede ser la demanda o el instalado.
    """
    if clave.endswith('kvar'):
        return 'Kvar'
    if clave.endswith('kw'):
        return 'Kw'
    if 'utm' in clave or clave.startswith('coord'):
        if clave.endswith(('x', 'este')):
            return 'CoordX'
        if clave.endswith(('y', 'norte')):
            return 'CoordY'
    return ''


def kva_normalizado(kva: float) -> float:
    """La menor potencia de la serie R10 que cubre ``kva`` (RF-52)."""
    escala = 1.0
    while True:
        for valor in SERIE_R10_KVA:
            if valor * escala >= kva - 1e-9:
                return valor * escala
        escala *= 10


@dataclass(frozen=True)
class Demanda:
    """Demanda pedida para una SED. ``hoja`` orienta si la SED está en dos alimentadores."""

    sed: str
    hoja: str
    kw: float
    kvar: float
    fp: float

    def para_pf(self) -> dict[str, Any]:
        return {
            'sed': self.sed, 'hoja': self.hoja, 'kw': self.kw, 'kvar': self.kvar,
            'fp': self.fp, 'plini_mw': self.kw / 1000.0, 'qlini_mvar': self.kvar / 1000.0,
        }


@dataclass(frozen=True)
class CargaNueva:
    """Carga nueva: su demanda y lo necesario para conectarla en el proyecto."""

    sed: str
    hoja: str
    alimentador: str
    barra: str
    lat: float | None
    lon: float | None
    kva_instalado: float
    kw: float
    kvar: float
    fp: float
    tipo_linea: str = ''
    tension_bt_kv: float | None = None
    anio_ingreso: int | None = None
    """030:RF-10: año calendario (≥ 1900) o año del PIDE en que entra; ``None``, el año 00."""
    etapas: tuple[tuple[int, float], ...] = ()
    """030:RF-13: (año, kW que entra ese año) de una carga fraccionada; suman ``kw``."""
    descripcion: str = ''
    """093:RF-3: el cliente según el libro, cuando la carga se nombra por su sigla."""
    kva_deducido: bool = False
    """004:RF-68: el libro no da kVA_instalado; con fichas en el perfil, el guion elige el
    transformador por la regla de 020:RF-6 y RF-7, no por la serie R10 al 100 %."""

    def para_pf(self) -> dict[str, Any]:
        datos = asdict(self)
        datos.update(plini_mw=self.kw / 1000.0, qlini_mvar=self.kvar / 1000.0)
        return datos


@dataclass
class Lectura:
    filas: list = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)        # valores deducidos (RF-52, RF-53)
    omitidas: list[str] = field(default_factory=list)      # accion = omitir
    sin_datos: list[str] = field(default_factory=list)     # ni kW ni kVA/FP


# --------------------------------------------------------------------------- libros
def _vacia(fila: Sequence[Any] | None) -> bool:
    return not fila or not any(c is not None and str(c).strip() for c in fila)


def _hojas(path: Path | str) -> dict[str, tuple[list[Any], list[list[Any]], int]]:
    """``{hoja: (cabecera, filas, fila_cabecera)}`` de un .xlsx (una por hoja) o un .csv (una).

    La cabecera es la primera fila con algo, no la fila 1: el libro de planificación de
    Electro Dunas (NuevosclientesMayoresv1, 2026-10-14) la trae en la fila 3 tras dos
    vacías, y tomando la fila 1 no se reconocía ninguna columna y sus 58 cargas se
    descartaban sin un solo aviso. ``fila_cabecera`` es su número en Excel, para que los
    mensajes citen la fila que el operador ve.
    """
    src = Path(path)
    if not src.is_file():
        raise LoadTemplateError(f'No se encuentra el fichero: {src}')
    suffix = src.suffix.lower()
    if suffix == '.csv':
        with src.open('r', encoding='utf-8-sig', newline='') as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=';,\t')
            except csv.Error:
                dialect = csv.excel
                dialect.delimiter = ';'
            reader = csv.reader(fh, dialect=dialect)
            fila_cabecera = 0
            header: list[Any] | None = None
            for header in reader:
                fila_cabecera += 1
                if not _vacia(header):
                    break
            if header is None or _vacia(header):
                raise LoadTemplateError(f'{src.name}: fichero vacío.')
            body = [row for row in reader if not _vacia(row)]
        return {src.stem: (header, body, fila_cabecera)}
    if suffix != '.xlsx':
        raise LoadTemplateError(
            f'Extensión no soportada: {src.suffix!r}. Use ' + ' o '.join(SUPPORTED_SUFFIXES))
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise LoadTemplateError(
            'Leer .xlsx necesita openpyxl. Instale con: pip install -r requirements.txt') from exc
    wb = load_workbook(src, data_only=True, read_only=True)
    out: dict[str, tuple[list[Any], list[list[Any]], int]] = {}
    try:
        for name in wb.sheetnames:
            it = wb[name].iter_rows(values_only=True)
            fila_cabecera = 0
            header = None
            for fila in it:
                fila_cabecera += 1
                if not _vacia(fila):
                    header = list(fila)
                    break
            if header is None:
                continue
            body = [list(v) for v in it if not _vacia(v)]
            if body:
                out[name] = (header, body, fila_cabecera)
    finally:
        wb.close()
    if not out:
        raise LoadTemplateError(f'{src.name}: ninguna hoja con datos.')
    return out


def leer_demandas(path: Path | str) -> Lectura:
    """Demandas por SED de todas las hojas. Sin modelo: valida cada fila por sí misma."""
    lectura = Lectura()
    vistas: dict[str, str] = {}
    for hoja, (header, body, _fila_cabecera) in _hojas(path).items():
        try:
            read = read_sheet(header, body, hoja)
        except LoadTemplateError as exc:
            lectura.errores.append(str(exc))
            continue
        lectura.errores += read.errors
        lectura.omitidas += read.skipped
        lectura.sin_datos += read.no_data
        for row in read.rows:
            if row.no_data:
                continue
            clave = f'{hoja}\x00{row.sed_code}'
            if clave in vistas:
                continue
            vistas[clave] = hoja
            lectura.filas.append(Demanda(row.sed_code, hoja, row.kw, row.kvar, row.fp))
    return lectura


def leer_nuevas(path: Path | str, *, source_crs: str = '', fp_por_defecto: float | None = None) -> Lectura:
    """Cargas nuevas de todas las hojas, con su posición ya en WGS84.

    La posición puede venir como ``Lat``/``Lon`` o como ``CoordX``/``CoordY`` en el CRS
    del perfil de empresa (``source_crs``): DIgSILENT compara con el GPS de sus barras,
    así que el guion la recibe siempre en grados.
    """
    lectura = Lectura()
    for hoja, (header, body, fila_cabecera) in _hojas(path).items():
        filas, errores = leer_hoja_nuevas(header, body, hoja, source_crs=source_crs,
                                          avisos=lectura.avisos, fila_cabecera=fila_cabecera,
                                          fp_por_defecto=fp_por_defecto)
        lectura.filas += filas
        lectura.errores += errores
    return lectura


def leer_hoja_nuevas(
    header: Sequence[Any], body: Sequence[Sequence[Any]], hoja: str, *, source_crs: str = '',
    avisos: list[str] | None = None, fila_cabecera: int = 1, fp_por_defecto: float | None = None,
) -> tuple[list[CargaNueva], list[str]]:
    """Filas de una hoja de cargas nuevas. Lo deducido se anota en ``avisos`` (RF-52, RF-53)."""
    avisos = [] if avisos is None else avisos
    mapping = dict(canonical_columns(header))
    for index, raw in enumerate(header):
        clave = normalise_header(raw)
        if clave in NUEVA_ALIASES:
            mapping[index] = NUEVA_ALIASES[clave]
    for index, raw in enumerate(header):
        nombre = '' if index in mapping else _columna_por_patron(normalise_header(raw))
        if nombre and nombre not in mapping.values():
            mapping[index] = nombre
    # 030:RF-13: las columnas de año de una carga fraccionada.
    etapas_de: dict[int, int] = {}
    for index, raw in enumerate(header):
        m = _ANIO_DE_ETAPA.match(normalise_header(raw)) if index not in mapping else None
        if m:
            etapas_de[index] = int(m.group(1))
    # Sin columna de nombre ni de demanda, cada fila se saltaría como «resto de la hoja»
    # y el libro entero daría cero cargas sin decir por qué.
    if body and not {'SED', 'nombre', 'Kw', '(kVA)'} & set(mapping.values()):
        cabecera = ', '.join(str(c).strip() for c in header if c is not None and str(c).strip())
        return [], [f'hoja {hoja}, fila {fila_cabecera}: no se reconoce la cabecera '
                    f'({cabecera or "vacía"}); hace falta SED o descripción, y Kw o (kVA).']
    filas: list[CargaNueva] = []
    errores: list[str] = []
    vistas: dict[str, int] = {}
    pendientes_xy: list[tuple[int, float, float]] = []
    for offset, values in enumerate(body):
        fila = offset + fila_cabecera + 1
        cell = {name: values[i] if i < len(values) else None for i, name in mapping.items()}
        texto = {k: ('' if v is None else str(v)).strip() for k, v in cell.items()}
        # RF-53: sin SED, la carga se nombra por su descripción y, sin ella, por su fila;
        # una fila sin nombre ni demanda es un resto de la hoja y se salta.
        sed = texto.get('SED') or texto.get('sigla') or texto.get('nombre', '')        # 093:RF-1, RF-2
        if not sed:
            if not any(texto.get(c) for c in ('Kw', 'Kvar', '(kVA)')):
                continue
            sed = f'{hoja}_F{fila}'
            avisos.append(f'hoja {hoja}, fila {fila}: sin SED ni descripción; se nombra {sed} (RF-53)')
        donde = f'hoja {hoja}, fila {fila}: {sed}'
        if sed in vistas:
            errores.append(f'{donde} repetida (fila {vistas[sed]})')
            continue
        vistas[sed] = fila
        numeros: dict[str, float | None] = {}
        malo = ''
        for nombre in ('Lat', 'Lon', 'CoordX', 'CoordY', 'kVA_instalado', 'Kw', 'Kvar',
                       '(kVA)', 'FP', 'tension_bt_kv', 'anio_ingreso'):
            valor = parse_number(cell.get(nombre))
            if valor is not None and math.isnan(valor):
                malo = f'{nombre}={cell.get(nombre)!r} no es un número'
                break
            if valor is not None and valor < 0 and nombre not in ('Lat', 'Lon', 'CoordX', 'CoordY'):
                malo = f'{nombre}={valor} negativo'
                break
            numeros[nombre] = valor
        ingreso = numeros.get('anio_ingreso')
        if not malo and ingreso is not None and ingreso != int(ingreso):
            malo = f'año de ingreso {ingreso} no es un año entero'
        etapas = []
        for index, anio_etapa in sorted(etapas_de.items(), key=lambda x: x[1]):
            v = parse_number(values[index]) if index < len(values) else None
            if v is not None and not math.isnan(v) and v > 0:
                etapas.append((anio_etapa, float(v)))
        if not malo and numeros.get('FP') is not None and not 0 <= numeros['FP'] <= 1:
            malo = f'FP={numeros["FP"]} fuera de [0, 1]'
        lat, lon = numeros.get('Lat'), numeros.get('Lon')
        if not malo and (lat is None) != (lon is None):
            malo = 'Lat y Lon van juntas'
        if not malo and lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
            malo = f'Lat/Lon fuera de rango ({lat}, {lon})'
        x, y = numeros.get('CoordX'), numeros.get('CoordY')
        tiene_xy = x is not None and y is not None
        if not malo and lat is None and tiene_xy and not source_crs:
            malo = 'CoordX/CoordY sin CRS del perfil: use Lat/Lon o configure el CRS'
        if not malo and not texto.get('barra') and lat is None and not tiene_xy:
            malo = 'sin barra ni coordenadas: indique la barra o Lat/Lon (o CoordX/CoordY)'
        if not malo and not texto.get('alimentador'):
            # 025:RF-45 (usuario, 2026-10-23): una carga sin los datos necesarios se rechaza
            # y se dice, en vez de deducir de qué alimentador es por su barra.
            malo = 'sin alimentador (TRONCAL): indique a qué alimentador pertenece'
        if malo:
            errores.append(f'{donde}: {malo}')
            continue
        fp_fila = numeros.get('FP')
        if numeros.get('Kw') is not None and numeros.get('Kvar') is None and fp_fila is None:
            # 004:RF-70: con Q = 0 la tensión de una carga nueva salía optimista; el FP sale del perfil de la empresa.
            if fp_por_defecto is not None and 0 < fp_por_defecto <= 1:
                fp_fila = float(fp_por_defecto)
                q = numeros['Kw'] * math.sqrt(max(1.0 - fp_fila ** 2, 0.0)) / fp_fila
                avisos.append(f'{donde}: sin kVAR ni FP; se toma el FP {fp_fila:.2f} del perfil de la empresa '
                              f'({q:.1f} kvar)'.replace('.', ',') + ' (004:RF-70)')
            else:
                avisos.append(f'{donde}: sin kVAR ni FP y sin FP en el perfil de la empresa: la carga entra con Q = 0 '
                              '(004:RF-70)')
        kw, kvar, _kva, fp, _derivada, sin_datos = resolve_power(
            numeros.get('Kw'), numeros.get('Kvar'), numeros.get('(kVA)'), fp_fila)
        conflicto = power_conflict(numeros.get('(kVA)'), numeros.get('FP'), kw, kvar)
        if conflicto:
            errores.append(f'{donde}: {conflicto}. Deje un solo par: Kw y Kvar, Kw y FP, o (kVA) y FP.')
            continue
        if sin_datos and etapas:
            # 030:RF-13: sin total, el total es la suma de sus partes.
            kw, kvar, _kva, fp, _derivada, sin_datos = resolve_power(
                sum(x for _a, x in etapas), numeros.get('Kvar'), None, numeros.get('FP'))
        if sin_datos:
            errores.append(f'{donde}: sin demanda (Kw, o (kVA) y FP)')
            continue
        if etapas and not math.isclose(sum(x for _a, x in etapas), kw, rel_tol=0.01):
            errores.append(f'{donde}: las partes por año suman {sum(x for _a, x in etapas):g} kW y el '
                           f'total es {kw:g} kW (030:RF-14)')
            continue
        kva_instalado = numeros.get('kVA_instalado')
        kva_deducido = not kva_instalado
        if kva_deducido:
            # RF-52: un libro de planificación da la demanda, no el transformador; se toma
            # el normalizado que la cubre y se anota, en vez de rechazar la carga.
            kva_instalado = kva_normalizado(math.hypot(kw, kvar))
            avisos.append(f'{donde}: sin kVA_instalado; se toma {kva_instalado:g} kVA, el '
                          f'normalizado que cubre {math.hypot(kw, kvar):.1f} kVA de demanda (RF-52); '
                          'con fichas en el perfil, el transformador sale de ellas al crear la '
                          'carga (004:RF-68)')
        if lat is None and tiene_xy:
            pendientes_xy.append((len(filas), x, y))
        filas.append(CargaNueva(
            sed=sed, hoja=hoja, alimentador=texto.get('alimentador', ''),
            barra=texto.get('barra', ''), lat=lat, lon=lon,
            kva_instalado=float(kva_instalado), kva_deducido=kva_deducido, kw=kw, kvar=kvar, fp=fp,
            tipo_linea=texto.get('tipo_linea', ''), tension_bt_kv=numeros.get('tension_bt_kv'),
            anio_ingreso=int(ingreso) if ingreso is not None else None, etapas=tuple(etapas),
            descripcion=texto.get('nombre', ''),                                     # 093:RF-3
        ))
    if pendientes_xy:
        gps = a_wgs84([(x, y) for _i, x, y in pendientes_xy], source_crs)
        for (index, _x, _y), punto in zip(pendientes_xy, gps):
            fila = filas[index]
            if punto is None:
                if not fila.barra:
                    errores.append(f'hoja {hoja}: {fila.sed}: CoordX/CoordY no se pudieron '
                                   f'pasar a GPS con {source_crs}')
                    filas[index] = None  # type: ignore[call-overload]
                continue
            filas[index] = CargaNueva(**{**asdict(fila), 'lat': punto[0], 'lon': punto[1]})
    return [f for f in filas if f is not None], errores


#: 099:RF-2: palabras que no distinguen a un cliente: el tipo de solicitud, la razón social y los conectores.
#: Son del castellano de cualquier libro de solicitudes, no de una empresa.
PALABRAS_GENERICAS = frozenset({
    'su', 'suministro', 'sac', 'saa', 'sa', 'srl', 'eirl', 'sociedad', 'anonima', 'cerrada', 'empresa', 'cliente',
    'de', 'del', 'el', 'la', 'los', 'las', 'y', 'e', 'en', 'a', 'al', 'para', 'con', 'por',
    'distrito', 'provincia', 'departamento', 'region', 'sector', 'nuevo', 'nueva', 'ampliacion', 'carga'})


def palabras_del_cliente(nombre: str) -> frozenset[str]:
    """099:RF-2: lo que distingue a un cliente en su nombre: sin tildes ni signos, sin la potencia
    («1770KW», «1,39 MW») ni números, y sin :data:`PALABRAS_GENERICAS`."""
    import unicodedata

    plano = unicodedata.normalize('NFKD', nombre or '').encode('ascii', 'ignore').decode().lower()
    plano = re.sub(r'\d+(?:[.,]\d+)?\s*(?:kw|kva|mw|mva|kv)\b', ' ', plano)
    palabras = [p for p in re.split(r'[^a-z0-9]+', plano) if p and not p.isdigit()]
    return frozenset(p for p in palabras if p not in PALABRAS_GENERICAS and len(p) > 1)


def _con_compuestas(nombre: str) -> frozenset[str]:
    """Las palabras y las parejas seguidas escritas juntas: «Tierra Larga» también es «tierralarga»."""
    import unicodedata

    plano = unicodedata.normalize('NFKD', nombre or '').encode('ascii', 'ignore').decode().lower()
    plano = re.sub(r'\d+(?:[.,]\d+)?\s*(?:kw|kva|mw|mva|kv)\b', ' ', plano)
    seguidas = [p for p in re.split(r'[^a-z0-9]+', plano) if p and not p.isdigit()]
    return frozenset(seguidas) | frozenset(a + b for a, b in zip(seguidas, seguidas[1:]))


def mismo_cliente(a: str, b: str) -> bool:
    """099:RF-1, RF-2: dos nombres del libro son el mismo cliente si todo lo que distingue al más corto
    está en el otro, contando las palabras que uno escribe juntas y el otro separadas.

    Chincha (2026-11-07): «SU-1770KW-Tierra Larga - Distrito el Camen- Provincia de chincha» (CH_20) y
    «SU-1390KW-TierraLarga-Chincha» (CH_23) son la misma solicitud con otra potencia; a 2,6 km una de
    otra, 040:RF-1 (1 m) no las unía y se creaban las dos.
    """
    pa, pb = palabras_del_cliente(a), palabras_del_cliente(b)
    if not pa or not pb:
        return False
    if pa == pb:
        return True
    corto, largo, nombre_largo = (pa, pb, b) if len(pa) <= len(pb) else (pb, pa, a)
    # 099:RF-2: una sola palabra distintiva no basta. Usuario (2026-11-07): «PREDIO SUBLOTE N°01-FUNDO YANACA»
    # y «YANACA» (NA205) son clientes distintos: un sublote es otra solicitud.
    if len(corto) < 2:
        return False
    return corto <= (largo | _con_compuestas(nombre_largo))


def _mismo_punto(a: dict, b: dict, radio_m: float) -> bool:
    if a.get('lat') is None or b.get('lat') is None or a.get('lon') is None or b.get('lon') is None:
        return False
    la1, lo1, la2, lo2 = map(math.radians, (float(a['lat']), float(a['lon']), float(b['lat']), float(b['lon'])))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(h)) <= radio_m


def duplicadas_por_cliente(filas: Sequence[dict], radio_m: float = 1.0) -> dict[str, str]:
    """099:RF-1, RF-3, RF-4: de cada fila que repite el cliente de otra posterior del mismo alimentador del libro,
    por el nombre (:func:`mismo_cliente`) o por el mismo punto (040:RF-1, a ``radio_m`` o menos), la fila que
    queda. Cuenta la última del libro: es la versión vigente de la solicitud (usuario, 2026-11-07: «considera
    uno solo de Tierra Larga, la CH_23; la otra es duplicado», y «la última del libro» también para el mismo
    punto, que cambia 040:RF-1). Una pasada por alimentador, con las filas de ese alimentador nada más."""
    por_alimentador: dict[str, list[dict]] = {}
    for fila in filas:
        por_alimentador.setdefault(str(fila.get('alimentador') or '').strip().upper(), []).append(fila)
    queda: dict[str, str] = {}
    for grupo in por_alimentador.values():
        for i, fila in enumerate(grupo):
            nombre = fila.get('descripcion') or fila.get('sed') or ''
            for posterior in reversed(grupo[i + 1:]):
                if posterior['sed'] != fila['sed'] and (_mismo_punto(fila, posterior, radio_m) or mismo_cliente(
                        nombre, posterior.get('descripcion') or posterior.get('sed') or '')):
                    queda[fila['sed']] = posterior['sed']
                    break
    # La que queda es la última de su cadena (CH_a → CH_b → CH_c: todas van a CH_c).
    for sed in list(queda):
        destino, vistos = queda[sed], {sed}
        while destino in queda and destino not in vistos:
            vistos.add(destino)
            destino = queda[destino]
        queda[sed] = destino
    return queda


def a_wgs84(puntos: Sequence[tuple[float, float]], source_crs: str) -> list[tuple[float, float] | None]:
    """(x, y) en ``source_crs`` → (lat, lon). ``None`` si un punto no se puede pasar."""
    from .geography import make_transformer

    try:
        transformer = make_transformer(source_crs, 'EPSG:4326')
    except ImportError:
        return [None] * len(puntos)
    out: list[tuple[float, float] | None] = []
    for x, y in puntos:
        try:
            lon, lat = transformer.transform(x, y)
        except Exception:  # noqa: BLE001 - un punto malo no tumba el libro
            out.append(None)
            continue
        ok = math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
        out.append((lat, lon) if ok else None)
    return out


# --------------------------------------------------------------------------- plan
def armar_plan(
    *,
    project: str,
    feeders: Sequence[str],
    demandas: Lectura | None,
    nuevas: Lectura | None,
    costos: dict | None = None,
    tec: dict | None = None,
    ahora: datetime | None = None,
    carpeta: str | None = None,
    base: dict | None = None,
    minima_m: float | None = None,
) -> dict[str, Any]:
    """El plan que recibe ``tools/cargas_pf.py``. Igual para uno que para varios (RF-5).

    ``project`` es la ruta del proyecto dentro de ``carpeta``, la de importación de
    DIgSILENT (spec 005, RF-16): dos proyectos con el mismo nombre en subcarpetas
    distintas son dos proyectos.

    ``base`` es el ajuste a la máxima sobre el que se integra (spec 007, RF-1): sus
    variaciones, una por alimentador ajustado, forman con las demandas del envío el
    estado sin proyecto. La lee la web del trabajo del ajuste (``services.base_del_ajuste``).

    ``minima_m`` es la distancia mínima de la spec 016 (RF-20, RF-73): una carga cuyo punto
    de la troncal queda más cerca de una barra se engancha en ella sin partir el tramo.
    """
    if minima_m is not None and (not isinstance(minima_m, (int, float)) or minima_m < 0):
        raise LoadTemplateError(f'La distancia mínima tiene que ser un número de metros, 0 o más: '
                                f'{minima_m!r}.')
    elegidos = list(dict.fromkeys(f.strip() for f in feeders if f and f.strip()))
    if not project.strip():
        raise LoadTemplateError('Elija el proyecto de DIgSILENT.')
    if not elegidos:
        raise LoadTemplateError('Elija al menos un alimentador.')
    if demandas is None and nuevas is None:
        raise LoadTemplateError('Suba el libro de demandas, el de cargas nuevas o los dos.')
    stamp = (ahora or datetime.now()).strftime('%Y%m%d_%H%M%S')
    errores = list((demandas.errores if demandas else []) + (nuevas.errores if nuevas else []))
    plan = {
        'schema': SCHEMA,
        'project': project.strip(),
        'folder': carpeta,
        'feeders': elegidos,
        'stamp': stamp,
        # El guion añade un sufijo si ya existe (spec 004, RF-4). Las demandas van en su
        # propia variación y cada carga nueva en la suya, que el guion nombra con su SED y
        # su alimentador cuando sabe a cuál se conecta (spec 007, RF-9, RF-10, RF-19).
        'variacion': f'Demandas_{stamp}',
        'variacion_demandas': f'Demandas_{stamp}',
        'demandas': [d.para_pf() for d in (demandas.filas if demandas else [])],
        'nuevas': [n.para_pf() for n in (nuevas.filas if nuevas else [])],
        'omitidas_por_el_operador': list(demandas.omitidas) if demandas else [],
        'sin_datos': list(demandas.sin_datos) if demandas else [],
        'row_errors': errores,
        'costos': costos,
        'tec': tec,
        'minima_m': minima_m,
    }
    plan['aplicable'] = bool(plan['demandas'] or plan['nuevas'])
    plan['base'] = base or None
    plan['avisos'] = _avisos_de_la_base(base) + list(nuevas.avisos if nuevas else [])
    plan['calibradas_cambiadas'] = _calibradas_cambiadas(base, plan['demandas'])
    return plan


def _avisos_de_la_base(base: dict | None) -> list[str]:
    """Lo que el operador debe saber de la base antes de aplicar (spec 007, RF-5, RF-34, RF-37)."""
    if not base:
        return ['Sin base del ajuste: se aplica sobre las variaciones que estén activas en el '
                'proyecto (spec 007, RF-5).']
    avisos = []
    for a in base.get('ajustes') or []:
        if not a.get('cuadrado'):
            desvio = (a.get('desvio') or {}).get('kw')
            error = f' (error en la cabecera {desvio:+.2%})' if isinstance(desvio, (int, float)) else ''
            avisos.append(f"El ajuste de {a['feeder']} no cuadró{error}: se usa igual como base (RF-34).")
    for x in base.get('excluidos') or []:
        avisos.append(f"{x['feeder']} queda fuera de la base: {x['motivo']} (RF-37).")
    return avisos


def _calibradas_cambiadas(base: dict | None, demandas: list[dict]) -> list[dict]:
    """SED que el ajuste calibró y que el libro de demandas cambia (spec 007, RF-20, RF-21)."""
    calibradas = (base or {}).get('sed') or {}
    out = []
    for d in demandas:
        c = calibradas.get(d['sed'])
        if c is not None:
            out.append({'sed': d['sed'], 'feeder': c.get('feeder'),
                        'calibrada': {'kw': c.get('kw'), 'kvar': c.get('kvar')},
                        'libro': {'kw': d['kw'], 'kvar': d['kvar']}})
    return out


# --------------------------------------------------------------------------- plantillas
def escribir_plantilla(tipo: str, destino: Path) -> Path:
    """Plantilla vacía de demandas (``tipo='demandas'``) o de cargas nuevas (``'nuevas'``)."""
    columnas = {'demandas': DEMANDA_COLUMNS, 'nuevas': NUEVA_COLUMNS}[tipo]
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.suffix.lower() == '.csv':
        with destino.open('w', encoding='utf-8-sig', newline='') as fh:
            csv.writer(fh, delimiter=';').writerow(columnas)
        return destino
    from openpyxl import Workbook

    wb = Workbook()
    hoja = wb.active
    hoja.title = 'cargas'
    hoja.append(list(columnas))
    wb.save(destino)
    return destino
