"""Medición de cabecera entregada «a lo ancho»: una columna por alimentador (spec 051).

La calibración (specs 006, 025 y 035) lee la cabecera como la entrega Electro Dunas: una hoja
por medidor con fecha, kW y kVAR, y un libro de medidores. Electro Oriente la entrega en los
perfiles de carga del PIDE 2026: una hoja por sistema y magnitud («BJSI_ACTIVA»), la fecha y la
hora en dos columnas y una columna por alimentador; y en Iquitos, solo una tabla de máximas
mensuales en MW por salida. Este módulo lee las dos formas y las escribe en la que la
calibración ya lee, sin tocarla. No supone nada de una empresa: los códigos, el nombre de cada
alimentador en DIgSILENT y las carpetas los da quien lo usa (051:RF-7).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .demanda_medida import ALIAS, DemandaError, _abrir, _filas, clave_codigo, normalizar, numero

FILAS_CABECERA = 12
EXTENSIONES = ('.xlsx', '.xlsm', '.xls', '.xlsb')
# Mes por sus tres primeras letras, con las variantes de los libros («MARZ», «AGT», «SET»).
MESES = {'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8,
         'agt': 8, 'set': 9, 'sep': 9, 'oct': 10, 'nov': 11, 'dic': 12}


@dataclass
class Lectura:
    """Las series leídas por código, con lo anotado."""

    #: código pedido → instante → [kW, kVAR] (``None`` si esa magnitud no vino).
    series: dict[str, dict[datetime, list[float | None]]] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    #: Códigos que vienen de una tabla de máximas mensuales: sin hora ni reactiva (RF-9).
    mensuales: set[str] = field(default_factory=set)

    def faltan(self, codigos: Iterable[str]) -> list[str]:
        return [c for c in codigos if not self.series.get(c)]


def libros_de(rutas: Iterable[Path | str]) -> list[Path]:
    """Cada ruta es un libro o una carpeta con libros, en orden de nombre."""
    out: list[Path] = []
    for ruta in rutas:
        p = Path(ruta)
        if p.is_dir():
            out += sorted(x for x in p.rglob('*') if x.suffix.lower() in EXTENSIONES
                          and not x.name.startswith('~$'))
        elif p.is_file():
            out.append(p)
        else:
            raise DemandaError(f'No existe: {p}')
    return list(dict.fromkeys(out))


# =========================================================================== RF-3
def _fecha(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    m = re.match(r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})', str(v or ''))
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})', str(v or ''))
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _hora(v: Any) -> timedelta | None:
    if isinstance(v, datetime):
        return None
    if isinstance(v, time):
        return timedelta(hours=v.hour, minutes=v.minute, seconds=v.second)
    if isinstance(v, timedelta):
        return v
    if isinstance(v, float) and 0 <= v <= 1:            # fracción del día de Excel
        return timedelta(days=v)
    m = re.match(r'^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$', str(v or ''))
    if m:
        return timedelta(hours=int(m.group(1)), minutes=int(m.group(2)), seconds=int(m.group(3) or 0))
    return None


def instante(a: Any, b: Any = None) -> datetime | None:
    """La fecha y la hora de dos celdas, en cualquier orden y como texto o como fecha (RF-3).

    «24:00» es la medianoche del día siguiente: el último cuarto de hora de un día.
    """
    for f, h in ((a, b), (b, a)):
        d = _fecha(f)
        if d is None:
            continue
        hora = _hora(h)
        if hora is not None:
            return datetime(d.year, d.month, d.day) + hora
        if isinstance(f, datetime):
            return f
        m = re.match(r'^\s*\d{4}-\d{1,2}-\d{1,2}[ T](\d{1,2}):(\d{2})', str(f))
        base = datetime(d.year, d.month, d.day)
        return base + timedelta(hours=int(m.group(1)), minutes=int(m.group(2))) if m else base
    return None


# =========================================================================== RF-1, RF-2, RF-4, RF-5
def _magnitud(hoja: str, filas: Sequence[Sequence[Any]]) -> str | None:
    """«kvar» o «kw» por el nombre de la hoja o por sus primeras filas (RF-2)."""
    textos = [normalizar(hoja)] + [normalizar(c) for f in filas[:3] for c in f if isinstance(c, str)]
    for t in textos:
        if 'reactiv' in t:
            return 'kvar'
    for t in textos:
        if 'activ' in t:
            return 'kw'
    return None


def _cabecera_ancha(filas, pedidos: Mapping[str, str]) -> tuple[int, int, dict[str, int]] | None:
    """Fila de cabecera con una columna de fecha y algún código pedido (RF-1)."""
    for i, fila in enumerate(filas[:FILAS_CABECERA]):
        norm = [normalizar(c) for c in fila]
        col_fecha = next((j for j, n in enumerate(norm) if n in ALIAS['fecha']), None)
        cols: dict[str, int] = {}
        for j, c in enumerate(fila):
            pedido = pedidos.get(clave_codigo(c))
            if pedido is not None:
                cols.setdefault(pedido, j)
        if col_fecha is not None and cols:
            return i, col_fecha, cols
    return None


def leer_ancho(rutas: Iterable[Path | str], codigos: Sequence[str],
               lectura: Lectura | None = None) -> Lectura:
    """Las series de los ``codigos`` en libros con una columna por alimentador (RF-1 a RF-5)."""
    lectura = lectura or Lectura()
    pedidos = {clave_codigo(c): c for c in codigos}
    for ruta in libros_de(rutas):
        libro = _abrir(ruta)
        for hoja in libro.sheet_names:
            filas = _filas(libro, hoja)
            hallada = _cabecera_ancha(filas, pedidos)
            if hallada is None:
                continue
            i, col_fecha, cols = hallada
            magnitud = _magnitud(hoja, filas)
            if magnitud is None:
                lectura.avisos.append(f'{ruta.name} / {hoja}: no dice si es activa o reactiva; no se lee (051:RF-2).')
                continue
            for codigo, j in cols.items():
                otras = [k for k, c in enumerate(filas[i]) if k != j and clave_codigo(c) == clave_codigo(codigo)]
                if otras:
                    lectura.avisos.append(f'{ruta.name} / {hoja}: {codigo} está {len(otras) + 1} veces; '
                                          f'se toma la primera columna (051:RF-5).')
            signo = {c: -1.0 if magnitud == 'kvar' and any(
                'capacitiv' in normalizar(f[j]) for f in filas[:i] if j < len(f)) else 1.0
                for c, j in cols.items()}
            for c, s in signo.items():
                if s < 0:
                    lectura.avisos.append(f'{ruta.name} / {hoja}: la reactiva de {c} es capacitiva; '
                                          'va con signo negativo (051:RF-4).')
            k = 0 if magnitud == 'kw' else 1
            for fila in filas[i + 1:]:
                cuando = instante(fila[col_fecha] if col_fecha < len(fila) else None,
                                  fila[col_fecha + 1] if col_fecha + 1 < len(fila) else None)
                if cuando is None:
                    continue
                for codigo, j in cols.items():
                    v = numero(fila[j]) if j < len(fila) else None
                    if v is None:
                        continue
                    par = lectura.series.setdefault(codigo, {}).setdefault(cuando, [None, None])
                    par[k] = v * signo[codigo]
    return lectura


# =========================================================================== RF-9
def _mes(texto: Any) -> int | None:
    n = normalizar(texto)
    return MESES.get(n[:3]) if len(n) >= 3 else None


def _anio(hoja: str, filas) -> int | None:
    for t in [hoja] + [c for f in filas[:3] for c in f]:
        m = re.fullmatch(r'\s*((?:19|20)\d{2})(?:\.0)?\s*', str(t if t is not None else ''))
        if m:
            return int(m.group(1))
    return None


def leer_maximas_mensuales(rutas: Iterable[Path | str], codigos: Sequence[str], *,
                           unidad: str | None = None, lectura: Lectura | None = None) -> Lectura:
    """Máximas mensuales por salida: un registro del día 1 a las 00:00 en kW, sin reactiva (RF-9).

    La unidad, de la tabla («MW» en su título) o de ``unidad``; sin ninguna, se pide.
    """
    lectura = lectura or Lectura()
    pedidos = {clave_codigo(c): c for c in codigos}
    for ruta in libros_de(rutas):
        libro = _abrir(ruta)
        for hoja in libro.sheet_names:
            filas = _filas(libro, hoja)
            anio = _anio(hoja, filas)
            for i, fila in enumerate(filas[:FILAS_CABECERA]):
                meses = {j: m for j, c in enumerate(fila) if (m := _mes(c))}
                if len(meses) >= 3:
                    break
            else:
                continue
            if anio is None:
                lectura.avisos.append(f'{ruta.name} / {hoja}: tabla de máximas sin año; no se lee (051:RF-9).')
                continue
            titulo = ' '.join(normalizar(c) for f in filas[:i + 1] for c in f if isinstance(c, str))
            u = (unidad or ('mw' if re.search(r'\bmw\b', titulo) else 'kw' if re.search(r'\bkw\b', titulo)
                            else '')).lower()
            if u not in ('mw', 'kw'):
                raise DemandaError(f'{ruta.name} / {hoja}: la tabla de máximas no dice si es MW o kW; '
                                   'indíquelo (051:RF-9).')
            factor = 1000.0 if u == 'mw' else 1.0
            vistos: set[str] = set()
            for fila in filas[i + 1:]:
                codigo = pedidos.get(clave_codigo(fila[0] if fila else None))
                if codigo is None:
                    continue
                if codigo in vistos:            # la tabla de capacidades debajo repite las salidas
                    continue
                vistos.add(codigo)
                for j, mes in meses.items():
                    v = numero(fila[j]) if j < len(fila) else None
                    if v is not None:
                        lectura.series.setdefault(codigo, {})[datetime(anio, mes, 1)] = [v * factor, None]
                lectura.mensuales.add(codigo)
    for c in sorted(lectura.mensuales):
        lectura.avisos.append(f'{c}: máximas mensuales sin hora ni reactiva; la calibración ajusta solo '
                              'la activa y no supone ningún factor de potencia (051:RF-9).')
    return lectura


# =========================================================================== RF-6, RF-10
def escribir(lectura: Lectura, carpeta: Path | str, medidores: Mapping[str, str],
             fp: Mapping[str, float] | None = None) -> list[Path]:
    """Un libro de cabecera por año (una hoja por código: Fecha, kW, kVAR) y el de medidores.

    ``medidores``: nombre del alimentador en DIgSILENT → código de la medición (R205 → R5,
    RF-10). ``fp``: el factor de potencia que da el usuario para un código cuya medición no trae
    reactiva (RF-11); va en la columna FP y la calibración saca de él la Q. Nada se escribe en
    ``referencia/`` (RF-7).
    """
    fp = {c: float(v) for c, v in (fp or {}).items()}
    malos = [f'{c}={v}' for c, v in fp.items() if not 0 < v <= 1]
    if malos:
        raise DemandaError('El factor de potencia va entre 0 y 1: ' + ', '.join(malos) + ' (051:RF-11).')
    from openpyxl import Workbook

    carpeta = Path(carpeta)
    if 'referencia' in {p.casefold() for p in carpeta.resolve().parts}:
        raise DemandaError('Los libros normalizados no se escriben en referencia/ (051:RF-7).')
    carpeta.mkdir(parents=True, exist_ok=True)
    escritos = []
    anios = sorted({t.year for s in lectura.series.values() for t in s})
    for anio in anios:
        wb = Workbook()
        wb.remove(wb.active)
        for codigo in sorted(lectura.series):
            puntos = sorted((t, pq) for t, pq in lectura.series[codigo].items() if t.year == anio)
            if not puntos:
                continue
            ws = wb.create_sheet(re.sub(r'[\[\]:*?/\\]', '_', codigo)[:31])
            if codigo in fp:
                ws.append(['Fecha', 'kW', 'kVAR', 'FP'])
                for t, (kw, kvar) in puntos:
                    # La reactiva medida, si la hay, manda: el FP solo cubre la que falta.
                    ws.append([t, kw, kvar, fp[codigo] if kvar is None else None])
            else:
                ws.append(['Fecha', 'kW', 'kVAR'])
                for t, (kw, kvar) in puntos:
                    ws.append([t, kw, kvar])
        # Una subcarpeta por año, como la lee la calibración (025:RF-1): en una carpeta plana
        # todos los libros cuentan para cualquier año y NJA202, que está en el de 2024 y en el
        # de 2025 (solo su «24:00» del 31 de diciembre), salía «sin registro en 2024».
        (carpeta / str(anio)).mkdir(exist_ok=True)
        destino = carpeta / str(anio) / f'cabecera_{anio}.xlsx'
        wb.save(destino)
        escritos.append(destino)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Medidores'
    ws.append(['Alimentador', 'Medidor'])
    for alimentador, codigo in sorted(medidores.items()):
        ws.append([alimentador, codigo])
    destino = carpeta / 'medidores.xlsx'
    wb.save(destino)
    return escritos + [destino]
