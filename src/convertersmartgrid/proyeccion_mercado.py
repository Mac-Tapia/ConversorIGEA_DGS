"""Proyección anual de la demanda por sistema, medida contra lo ocurrido (072:RF-10, RF-11).

El pronóstico de la spec 046 es de corto plazo (1, 4 y 96 pasos) y no llega a los 20 años del
planeamiento. Aquí se lee la historia anual del Formato 01 y se compara cada método cortando esa
historia en un año: el método solo ve hasta el corte, y se mide contra lo que ocurrió después. La
tasa de un año, como la de 029, es la referencia; un método más complejo solo vale si la supera.
"""
from __future__ import annotations

import math
import re
import statistics
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path


class MercadoError(ValueError):
    """Un formato que no se puede leer o una serie que no da para el método."""


@dataclass(frozen=True)
class SerieMercado:
    """La historia y lo proyectado por el entregable de un sistema eléctrico."""

    codigo: str
    nombre: str
    sector: str
    historico: Mapping[int, float]
    proyeccion_entregable: Mapping[int, float] = field(default_factory=dict)


_ES_ANIO = re.compile(r'^(19|20)[0-9]{2}([.]0)?$')


def sector_tipico(texto: str) -> str:
    """El sector como lo usa el SICODI: «2» y «SECTOR TIPICO 2» son ST2; «SER» sigue igual."""
    t = str(texto or '').strip().upper()
    # Excel guardó un «3» como fecha en una hoja real del Formato 01: 1900-01-03.
    fecha = re.match(r'^1900-01-0([1-6])', t)
    if fecha:
        return f'ST{fecha.group(1)}'
    if 'SER' in t.split() or t == 'SER':
        return 'SER'
    m = re.search(r'([1-6])$', t)
    return f'ST{m.group(1)}' if m else t


def _texto(x) -> str:
    return str(x).strip() if x is not None else ''


def _valor_a_la_derecha(filas, etiqueta: str) -> str:
    for fila in filas:
        for i, x in enumerate(fila):
            if _texto(x).lower().startswith(etiqueta.lower()):
                return next((_texto(v) for v in fila[i + 1:] if _texto(v)), '')
    return ''


def leer_hoja_formato_01(filas: Iterable[tuple]) -> SerieMercado | None:
    """Una hoja del Formato 01, por sus rótulos y no por posición; ``None`` si no lo es."""
    filas = list(filas)
    cab = next((f for f in filas if any(_texto(x) == 'Año' for x in f)), None)
    if cab is None or not any(_texto(x) == 'MW.h' for x in cab):
        return None
    c_energia = next(i for i, x in enumerate(cab) if _texto(x) == 'MW.h')
    historico: dict[int, float] = {}
    proyeccion: dict[int, float] = {}
    destino = None
    for fila in filas:
        # En el Formato 01 real, el rótulo de la sección no está en la columna del año.
        rotulos = {_texto(x) for x in fila}
        if 'Histórico' in rotulos:
            destino = historico
        elif 'Proyección' in rotulos:
            destino = proyeccion
        elif destino is not None and c_energia < len(fila):
            # Bajo «Año» va también el índice (1, 2… 00): el año es la celda de cuatro cifras.
            anio = next((int(_texto(x)[:4]) for x in fila[:c_energia] if _ES_ANIO.match(_texto(x))), None)
            v = fila[c_energia]
            if anio is not None and isinstance(v, (int, float)) and v > 0:
                destino[anio] = float(v)
    if not historico:
        return None
    # El código y el nombre vienen con el mismo rótulo que la empresa: se toman del bloque del sistema.
    i = next((k for k, f in enumerate(filas) if any(_texto(x).startswith('Sistema El') for x in f)), 0)
    bloque = filas[i:]
    return SerieMercado(_valor_a_la_derecha(bloque, 'Código:'), _valor_a_la_derecha(bloque, 'Nombre:'),
                        sector_tipico(_valor_a_la_derecha(bloque, 'Sector:')), historico, proyeccion)


def leer_formato_01(ruta: Path | str) -> list[SerieMercado]:
    """Todas las hojas de sistema de un libro del Formato 01."""
    from openpyxl import load_workbook

    libro = load_workbook(ruta, read_only=True, data_only=True)
    series = [s for s in (leer_hoja_formato_01(libro[n].iter_rows(values_only=True)) for n in libro.sheetnames) if s]
    if not series:
        raise MercadoError(f'{Path(ruta).name} no trae hojas del Formato 01')
    return series


def _hasta(hist: Mapping[int, float], corte: int) -> list[tuple[int, float]]:
    return sorted((a, v) for a, v in hist.items() if a <= corte)


def tasa_de_un_anio(hist: Mapping[int, float], corte: int, anios: Iterable[int]) -> dict[int, float]:
    """La referencia: la variación del último año, compuesta (como 029)."""
    s = _hasta(hist, corte)
    if len(s) < 2:
        raise MercadoError('hacen falta 2 años')
    tasa = s[-1][1] / s[-2][1] - 1
    return {a: s[-1][1] * (1 + tasa) ** (a - s[-1][0]) for a in anios}


def tasa_media(hist: Mapping[int, float], corte: int, anios: Iterable[int]) -> dict[int, float]:
    """La tasa media de toda la historia hasta el corte."""
    s = _hasta(hist, corte)
    if len(s) < 2:
        raise MercadoError('hacen falta 2 años')
    tasa = (s[-1][1] / s[0][1]) ** (1 / (s[-1][0] - s[0][0])) - 1
    return {a: s[-1][1] * (1 + tasa) ** (a - s[-1][0]) for a in anios}


def tendencia_logaritmica(hist: Mapping[int, float], corte: int, anios: Iterable[int]) -> dict[int, float]:
    """La recta de mínimos cuadrados del logaritmo: menos sensible al último año."""
    s = _hasta(hist, corte)
    if len(s) < 3:
        raise MercadoError('hacen falta 3 años')
    xs, ys = [a for a, _v in s], [math.log(v) for _a, v in s]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sum((x - mx) ** 2 for x in xs)
    return {a: math.exp(my + b * (a - mx)) for a in anios}


def sin_crecimiento(hist: Mapping[int, float], corte: int, anios: Iterable[int]) -> dict[int, float]:
    """El último valor: cualquier método tiene que superar esto."""
    s = _hasta(hist, corte)
    if not s:
        raise MercadoError('sin años hasta el corte')
    return {a: s[-1][1] for a in anios}


METODOS: dict[str, Callable] = {'tasa_de_un_anio': tasa_de_un_anio, 'tasa_media': tasa_media,
                                'tendencia_logaritmica': tendencia_logaritmica, 'sin_crecimiento': sin_crecimiento}
REFERENCIA = 'tasa_de_un_anio'


def errores_contra_lo_ocurrido(hist: Mapping[int, float], cortes: Iterable[int], horizonte: int) -> dict[str, list[float]]:
    """Error porcentual absoluto de cada método, por año pronosticado (072:RF-11).

    Cada método recibe solo la historia hasta su corte, de modo que no puede mirar el futuro.
    """
    errores: dict[str, list[float]] = {m: [] for m in METODOS}
    for corte in cortes:
        anios = [a for a in range(corte + 1, corte + horizonte + 1) if a in hist]
        visible = {a: v for a, v in hist.items() if a <= corte}
        if not anios or len(visible) < 3:
            continue
        for nombre, metodo in METODOS.items():
            pronostico = metodo(visible, corte, anios)
            errores[nombre] += [abs(pronostico[a] - hist[a]) / hist[a] * 100.0 for a in anios]
    return errores


def perfiles_distintos(series: Iterable[SerieMercado]) -> list[SerieMercado]:
    """Una serie por cada forma de la historia: las copias a escala no son pruebas independientes.

    En el Formato 01 de Electro Oriente, los 53 sistemas son 9 perfiles: la historia por sistema sale
    de repartir unas pocas series comunes, y contarlas como 53 inflaría la evidencia.
    """
    vistos: dict[tuple, SerieMercado] = {}
    for s in series:
        anios = sorted(s.historico)
        base = s.historico[anios[-1]]
        vistos.setdefault((anios[0], tuple(round(s.historico[a] / base, 2) for a in anios)), s)
    return list(vistos.values())


def comparar_metodos(series: Iterable[SerieMercado], *, horizonte: int, minimo_anios: int = 3) -> dict:
    """Mediana de error de cada método entre perfiles, y en cuántos gana (072:RF-10, RF-11).

    El ganador sale de la medida: si ninguno supera a la referencia, se queda la referencia.
    """
    series = list(series)
    total_series = len(series)
    series = perfiles_distintos(s for s in series if s.historico)
    por_metodo: dict[str, list[float]] = {m: [] for m in METODOS}
    victorias = dict.fromkeys(METODOS, 0)
    usados = 0
    for s in series:
        anios = sorted(s.historico)
        cortes = [a for a in anios[minimo_anios - 1:-1]]
        e = errores_contra_lo_ocurrido(s.historico, cortes, horizonte)
        if not e[REFERENCIA]:
            continue
        usados += 1
        medias = {m: statistics.fmean(v) for m, v in e.items()}
        for m, v in medias.items():
            por_metodo[m].append(v)
        victorias[min(medias, key=medias.get)] += 1
    if not usados:
        raise MercadoError('ninguna serie da para comparar')
    medianas = {m: statistics.median(v) for m, v in por_metodo.items()}
    mejor = min(medianas, key=medianas.get)
    return {'sistemas': total_series, 'perfiles': usados, 'horizonte': horizonte, 'mediana_error_pct': medianas, 'victorias': victorias,
            'referencia': REFERENCIA, 'ganador': mejor if medianas[mejor] < medianas[REFERENCIA] else REFERENCIA}
