"""Indicadores mensuales de una serie de 15 minutos y su evolución (105:RF-5 a RF-11).

Cálculo puro, sin libros: lo mismo para un cliente fijo que para la suma de un alimentador. Las cifras son las del libro
de AL209 hecho a mano el 2026-11-12, que se tomó como especificación: energía = suma de la potencia de 15 minutos / 4,
FP medio = energía activa / aparente del mes, factor de carga = P media / P máxima.
"""
from __future__ import annotations

import calendar
import math
from collections.abc import Mapping, Sequence
from datetime import datetime

import numpy as np

from .meses_copiados import mes_de_registro


def _f(valor) -> float | None:
    """Un número finito, o ``None``: el JSON de la web no admite NaN."""
    if valor is None:
        return None
    v = float(valor)
    return v if math.isfinite(v) else None


def iso_minuto(t) -> str:
    return np.datetime64(t, 'm').astype(datetime).isoformat(timespec='minutes')


def esperados(mes: str) -> int:
    """Registros de 15 minutos de un mes completo: días × 96 (105:RF-6)."""
    anio, m = map(int, mes.split('-'))
    return calendar.monthrange(anio, m)[1] * 96


def indicadores_por_mes(t: np.ndarray, p: np.ndarray, q: np.ndarray | None) -> dict[str, dict]:
    """``{mes: indicadores}`` de una serie (105:RF-5, RF-6). Una Q vacía no cuenta en sus medias ni en su energía."""
    t = np.asarray(t, dtype='datetime64[m]')
    p = np.asarray(p, dtype=float)
    q = np.full(len(t), np.nan) if q is None else np.asarray(q, dtype=float)
    orden = np.argsort(t, kind='stable')
    t, p, q = t[orden], p[orden], q[orden]
    meses = mes_de_registro(t)
    salida: dict[str, dict] = {}
    for m in np.unique(meses):
        sel = meses == m
        tm, pm, qm = t[sel], p[sel], q[sel]
        con_p = np.isfinite(pm)
        if not con_p.any():
            continue
        clave = str(m)
        i = int(np.nanargmax(pm))
        p_max = float(pm[i])
        e_p = float(np.nansum(pm)) / 4 / 1000
        con_q = np.isfinite(qm)
        e_q = float(np.nansum(qm)) / 4 / 1000 if con_q.any() else None
        aparente = math.hypot(e_p, e_q or 0.0)
        iq = int(np.nanargmax(qm)) if con_q.any() else None
        registros = int(con_p.sum())
        salida[clave] = {
            'mes': clave,
            'p_max': p_max, 'fecha_p_max': iso_minuto(tm[i]), 'q_en_p_max': _f(qm[i]),
            'q_max': _f(qm[iq]) if iq is not None else None,
            'fecha_q_max': iso_minuto(tm[iq]) if iq is not None else None,
            'p_media': float(np.nanmean(pm)), 'q_media': float(np.nanmean(qm)) if con_q.any() else None,
            'energia_p': e_p, 'energia_q': e_q,
            'fp': e_p / aparente if aparente else None,
            'factor_carga': float(np.nanmean(pm)) / p_max if p_max else None,
            'registros': registros, 'esperados': esperados(clave),
            'completo': registros >= esperados(clave),
        }
    return salida


def _numero_de_mes(mes: str) -> int:
    anio, m = map(int, mes.split('-'))
    return anio * 12 + m


def _con_datos(valores: Mapping[str, float | None]) -> list[tuple[str, float]]:
    return sorted((m, float(v)) for m, v in valores.items() if v is not None and math.isfinite(v))


def crecimiento(valores: Mapping[str, float | None]) -> dict:
    """Del primer al último mes con datos, en % (105:RF-7): un cliente que entra a mitad crece desde su primer mes."""
    v = _con_datos(valores)
    if len(v) < 2 or not v[0][1]:
        return {'pct': None, 'desde': v[0][0] if v else None, 'hasta': v[-1][0] if v else None}
    return {'pct': (v[-1][1] / v[0][1] - 1) * 100, 'desde': v[0][0], 'hasta': v[-1][0]}


def variaciones(valores: Mapping[str, float | None]) -> dict[str, dict]:
    """Cada mes frente al mes anterior con datos, en % (105:RF-8)."""
    v = _con_datos(valores)
    return {m: {'pct': (x / x0 - 1) * 100 if x0 else None, 'respecto': m0}
            for (m0, x0), (m, x) in zip(v, v[1:])}


def tendencia(valores: Mapping[str, float | None]) -> float | None:
    """Pendiente de la recta sobre el número real de cada mes, en % de la media; tres meses o más (105:RF-9)."""
    v = _con_datos(valores)
    if len(v) < 3:
        return None
    y = np.array([x for _m, x in v])
    if not y.mean():
        return None
    return float(np.polyfit([_numero_de_mes(m) for m, _x in v], y, 1)[0] / y.mean() * 100)


def mes_mayor(valores: Mapping[str, float | None]) -> str | None:
    """El mes de mayor valor; a igualdad, el primero (105:RF-10)."""
    v = _con_datos(valores)
    return max(v, key=lambda par: (par[1], -_numero_de_mes(par[0])))[0] if v else None


#: Magnitud de los indicadores → su crecimiento, su tendencia y su mes de mayor valor.
MAGNITUDES = ('p_max', 'energia_p', 'q_max', 'energia_q')


def resumen(meses: Mapping[str, Mapping], excluidos: Sequence[str] = ()) -> dict:
    """Crecimiento, variación, tendencia y meses de mayor valor sin los meses excluidos (105:RF-7 a RF-10, RF-13)."""
    usados = {m: d for m, d in meses.items() if m not in set(excluidos)}
    serie = {k: {m: d.get(k) for m, d in usados.items()} for k in MAGNITUDES}
    pico = max(usados.values(), key=lambda d: d['p_max'], default=None)
    return {
        'p_max': pico['p_max'] if pico else None, 'fecha_p_max': pico['fecha_p_max'] if pico else None,
        'crecimiento': {k: crecimiento(serie[k]) for k in ('p_max', 'energia_p', 'q_max')},
        'tendencia': {k: tendencia(serie[k]) for k in ('p_max', 'energia_p', 'q_max')},
        'variacion': {k: variaciones(serie[k]) for k in ('p_max', 'energia_p')},
        'mes_mayor': {k: mes_mayor(serie[k]) for k in MAGNITUDES},
    }


def suma_por_mes(por_cliente: Sequence[Mapping[str, Mapping]]) -> dict[str, dict]:
    """La suma de los clientes con datos en cada mes (105:RF-11): un mes sin ninguno no existe."""
    salida: dict[str, dict] = {}
    for meses in por_cliente:
        for m, d in meses.items():
            s = salida.setdefault(m, {'mes': m, 'clientes': 0})
            s['clientes'] += 1
            for k in MAGNITUDES:
                if d.get(k) is not None:
                    s[k] = s.get(k, 0.0) + d[k]
    return dict(sorted(salida.items()))
