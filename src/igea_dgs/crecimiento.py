"""Crecimiento anual de la demanda de cada alimentador desde la medición de cabecera (spec 029).

El PIDE de Chincha (2026-10-28) no tenía tasa: el perfil la dejaba vacía y solo se diagnosticaba
el año 00. La cabecera trae 2025 entero y 2026 hasta el mes del último libro: comparar la máxima
de un año entero con la de medio año daba un crecimiento falso, así que se comparan las máximas
de los meses que tienen los dos años (RF-2). Es la tasa de la demanda medida y nada más: la
proyección con variables exógenas es otra spec (la 030).
"""
from __future__ import annotations

import statistics
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

Curva = Sequence[tuple[Any, float | None, Any]]


def _fecha(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError:
        return None


def maximas_mensuales(curva: Curva) -> dict[int, float]:
    """La máxima de cada mes de una curva ``[(fecha, kW, kVAR)]``."""
    out: dict[int, float] = {}
    for fecha, kw, *_ in curva:
        f = _fecha(fecha)
        if f is None or kw is None:
            continue
        out[f.month] = max(out.get(f.month, float('-inf')), float(kw))
    return out


def sumar(curvas: Sequence[Curva]) -> list[tuple[Any, float, None]]:
    """Las curvas de los medidores de un alimentador sumadas en sus registros comunes."""
    if len(curvas) == 1:
        return [(f, kw, None) for f, kw, *_ in curvas[0] if kw is not None]
    por_fecha: dict[Any, list[float]] = {}
    for c in curvas:
        for f, kw, *_ in c:
            if kw is not None:
                por_fecha.setdefault(f, []).append(float(kw))
    return [(f, sum(v), None) for f, v in sorted(por_fecha.items(), key=lambda x: str(x[0]))
            if len(v) == len(curvas)]


def tasa_entre(anterior: Curva, ultima: Curva, anios: int) -> dict[str, Any] | None:
    """La tasa compuesta entre las máximas de los meses comunes de dos años (RF-2)."""
    a, b = maximas_mensuales(anterior), maximas_mensuales(ultima)
    meses = sorted(set(a) & set(b))
    if not meses or anios <= 0:
        return None
    ma, mb = max(a[m] for m in meses), max(b[m] for m in meses)
    if ma <= 0 or mb <= 0:
        return None
    return {'tasa': (mb / ma) ** (1 / anios) - 1, 'meses': meses, 'max_anterior_kw': ma,
            'max_ultimo_kw': mb}


def tasas_por_alimentador(curvas: Mapping[int, Mapping[str, Curva]],
                          alimentadores: Sequence[str]) -> dict[str, dict[str, Any]]:
    """La tasa de cada alimentador entre su primer y su último año con datos; los demás, la
    mediana de las medidas (RF-1 a RF-3, RF-5)."""
    out: dict[str, dict[str, Any]] = {}
    for a in alimentadores:
        anios = sorted(y for y, cs in curvas.items() if cs.get(a))
        if len(anios) >= 2:
            r = tasa_entre(curvas[anios[0]][a], curvas[anios[-1]][a], anios[-1] - anios[0])
            if r is not None:
                out[a] = {**r, 'anios': [anios[0], anios[-1]], 'origen': 'medida'}
    medidas = [x['tasa'] for x in out.values()]
    mediana = statistics.median(medidas) if medidas else None
    for a in alimentadores:
        if a not in out:
            out[a] = {'tasa': mediana, 'origen': 'mediana del sistema' if mediana is not None else 'sin datos'}
    return out


def curvas_por_anio(libros_por_anio: Mapping[int, Sequence[Path | str]], pares: Sequence[tuple[str, str]],
                    alias: Any, *, progreso: Callable = lambda *_a: None, log: Callable = lambda _t: None,
                    cancelado: Callable[[], bool] = lambda: False) -> dict[int, dict[str, list]]:
    """Las curvas de cada alimentador (sus medidores sumados) por año, leídas con ``maximas``;
    corre en el proceso del trabajo (RF-7)."""
    from .demanda_medida import maximas

    out: dict[int, dict[str, list]] = {}
    for anio, libros in sorted(libros_por_anio.items()):
        if cancelado():
            break
        log(f'Crecimiento: leyendo la cabecera de {anio} ({len(libros)} libro(s))…')
        res = maximas(list(libros), list(pares), alias=alias, periodo=str(anio), cancelado=cancelado,
                      progreso=progreso)
        por_alim: dict[str, list] = {}
        for r in res:
            if r.curva and r.alimentador:
                por_alim.setdefault(r.alimentador, []).append(r.curva)
        out[anio] = {a: sumar(cs) for a, cs in por_alim.items()}
    return out
