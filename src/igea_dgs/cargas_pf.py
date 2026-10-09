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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .loads import (
    LoadTemplateError, SUPPORTED_SUFFIXES, _normalise, _number, _power_conflict,
    _resolve_power, canonical_columns, read_sheet,
)

SCHEMA = 'igea-dgs-cargas-pf-v1'

DEMANDA_COLUMNS = ('SED', 'Kw', 'Kvar', '(kVA)', 'FP', 'accion', 'observaciones')
NUEVA_COLUMNS = (
    'SED', 'alimentador', 'barra', 'Lat', 'Lon', 'CoordX', 'CoordY', 'kVA_instalado',
    'Kw', 'Kvar', '(kVA)', 'FP', 'tipo_linea', 'tension_bt_kv', 'observaciones',
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
}


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

    def para_pf(self) -> dict[str, Any]:
        datos = asdict(self)
        datos.update(plini_mw=self.kw / 1000.0, qlini_mvar=self.kvar / 1000.0)
        return datos


@dataclass
class Lectura:
    filas: list = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    omitidas: list[str] = field(default_factory=list)      # accion = omitir
    sin_datos: list[str] = field(default_factory=list)     # ni kW ni kVA/FP


# --------------------------------------------------------------------------- libros
def _hojas(path: Path | str) -> dict[str, tuple[list[Any], list[list[Any]]]]:
    """``{hoja: (cabecera, filas)}`` de un .xlsx (una por hoja) o un .csv (una)."""
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
            try:
                header = next(reader)
            except StopIteration:
                raise LoadTemplateError(f'{src.name}: fichero vacío.') from None
            body = [row for row in reader if any((c or '').strip() for c in row)]
        return {src.stem: (header, body)}
    if suffix != '.xlsx':
        raise LoadTemplateError(
            f'Extensión no soportada: {src.suffix!r}. Use ' + ' o '.join(SUPPORTED_SUFFIXES))
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise LoadTemplateError(
            'Leer .xlsx necesita openpyxl. Instale con: pip install -r requirements.txt') from exc
    wb = load_workbook(src, data_only=True, read_only=True)
    out: dict[str, tuple[list[Any], list[list[Any]]]] = {}
    try:
        for name in wb.sheetnames:
            it = wb[name].iter_rows(values_only=True)
            try:
                header = list(next(it))
            except StopIteration:
                continue
            body = [list(v) for v in it if v and any(c is not None and str(c).strip() for c in v)]
            if body:
                out[name] = (header, body)
    finally:
        wb.close()
    if not out:
        raise LoadTemplateError(f'{src.name}: ninguna hoja con datos.')
    return out


def leer_demandas(path: Path | str) -> Lectura:
    """Demandas por SED de todas las hojas. Sin modelo: valida cada fila por sí misma."""
    lectura = Lectura()
    vistas: dict[str, str] = {}
    for hoja, (header, body) in _hojas(path).items():
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


def leer_nuevas(path: Path | str, *, source_crs: str = '') -> Lectura:
    """Cargas nuevas de todas las hojas, con su posición ya en WGS84.

    La posición puede venir como ``Lat``/``Lon`` o como ``CoordX``/``CoordY`` en el CRS
    del perfil de empresa (``source_crs``): DIgSILENT compara con el GPS de sus barras,
    así que el guion la recibe siempre en grados.
    """
    lectura = Lectura()
    for hoja, (header, body) in _hojas(path).items():
        filas, errores = leer_hoja_nuevas(header, body, hoja, source_crs=source_crs)
        lectura.filas += filas
        lectura.errores += errores
    return lectura


def leer_hoja_nuevas(
    header: Sequence[Any], body: Sequence[Sequence[Any]], hoja: str, *, source_crs: str = '',
) -> tuple[list[CargaNueva], list[str]]:
    mapping = dict(canonical_columns(header))
    for index, raw in enumerate(header):
        clave = _normalise(raw)
        if clave in NUEVA_ALIASES:
            mapping[index] = NUEVA_ALIASES[clave]
    if 'SED' not in mapping.values():
        return [], [f'hoja {hoja!r}: falta la columna «SED». Cabecera: {[str(h) for h in header]}']
    filas: list[CargaNueva] = []
    errores: list[str] = []
    vistas: dict[str, int] = {}
    pendientes_xy: list[tuple[int, float, float]] = []
    for offset, values in enumerate(body):
        fila = offset + 2
        cell = {name: values[i] if i < len(values) else None for i, name in mapping.items()}
        texto = {k: ('' if v is None else str(v)).strip() for k, v in cell.items()}
        sed = texto.get('SED', '')
        if not sed:
            continue
        donde = f'hoja {hoja}, fila {fila}: {sed}'
        if sed in vistas:
            errores.append(f'{donde} repetida (fila {vistas[sed]})')
            continue
        vistas[sed] = fila
        numeros: dict[str, float | None] = {}
        malo = ''
        for nombre in ('Lat', 'Lon', 'CoordX', 'CoordY', 'kVA_instalado', 'Kw', 'Kvar',
                       '(kVA)', 'FP', 'tension_bt_kv'):
            valor = _number(cell.get(nombre))
            if valor is not None and math.isnan(valor):
                malo = f'{nombre}={cell.get(nombre)!r} no es un número'
                break
            if valor is not None and valor < 0 and nombre not in ('Lat', 'Lon', 'CoordX', 'CoordY'):
                malo = f'{nombre}={valor} negativo'
                break
            numeros[nombre] = valor
        if not malo and numeros.get('FP') is not None and not 0 <= numeros['FP'] <= 1:
            malo = f'FP={numeros["FP"]} fuera de [0, 1]'
        if not malo and not numeros.get('kVA_instalado'):
            malo = 'sin kVA_instalado: hace falta la potencia del transformador'
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
        if malo:
            errores.append(f'{donde}: {malo}')
            continue
        kw, kvar, _kva, fp, _derivada, sin_datos = _resolve_power(
            numeros.get('Kw'), numeros.get('Kvar'), numeros.get('(kVA)'), numeros.get('FP'))
        conflicto = _power_conflict(numeros.get('(kVA)'), numeros.get('FP'), kw, kvar)
        if conflicto:
            errores.append(f'{donde}: {conflicto}. Deje un solo par: Kw y Kvar, Kw y FP, o (kVA) y FP.')
            continue
        if sin_datos:
            errores.append(f'{donde}: sin demanda (Kw, o (kVA) y FP)')
            continue
        if lat is None and tiene_xy:
            pendientes_xy.append((len(filas), x, y))
        filas.append(CargaNueva(
            sed=sed, hoja=hoja, alimentador=texto.get('alimentador', ''),
            barra=texto.get('barra', ''), lat=lat, lon=lon,
            kva_instalado=float(numeros['kVA_instalado']), kw=kw, kvar=kvar, fp=fp,
            tipo_linea=texto.get('tipo_linea', ''), tension_bt_kv=numeros.get('tension_bt_kv'),
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
) -> dict[str, Any]:
    """El plan que recibe ``tools/cargas_pf.py``. Igual para uno que para varios (RF-5).

    ``project`` es la ruta del proyecto dentro de ``carpeta``, la de importación de
    DIgSILENT (spec 005, RF-16): dos proyectos con el mismo nombre en subcarpetas
    distintas son dos proyectos.
    """
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
        # El guion añade un sufijo si ya existe (RF-4).
        'variacion': f'Cargas_{stamp}',
        'demandas': [d.para_pf() for d in (demandas.filas if demandas else [])],
        'nuevas': [n.para_pf() for n in (nuevas.filas if nuevas else [])],
        'omitidas_por_el_operador': list(demandas.omitidas) if demandas else [],
        'sin_datos': list(demandas.sin_datos) if demandas else [],
        'row_errors': errores,
        'costos': costos,
        'tec': tec,
    }
    plan['aplicable'] = bool(plan['demandas'] or plan['nuevas'])
    return plan


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
