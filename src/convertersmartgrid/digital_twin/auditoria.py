"""Auditoría del dataset de cada modelo antes de entrenar (spec 027, RF-29 a RF-34).

La revisión del 2026-10-28 halló que el gemelo se entrenaba con 24 muestras de una sola red
(IN111–TA225, 2 470 nodos) y 928 518 parámetros, y el asistente con 4 055 órdenes de las que
una era real, medido con órdenes sintéticas. Nada de eso fallaba: el error de prueba salía
bueno porque medía lo mismo con que se entrenó. Este informe lo dice antes de cada
entrenamiento, y un dataset con valores no finitos no se entrena (RF-30).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Umbrales:
    v_min_pu: float = 0.8           # RF-32: fuera de este rango se marca, no se excluye
    v_max_pu: float = 1.2
    min_redes: int = 2              # RF-33
    min_ordenes_reales: int = 200   # RF-19, RF-33


def _red(m: Any) -> tuple:
    """Lo que distingue una red de otra: sus nodos. Ni las cargas ni el estado de una maniobra:
    IN111–TA225 con una maniobra más cerrada (4 942 aristas frente a 4 940) es la misma red y
    contaba como dos (2026-10-28)."""
    return tuple(m.ids)


def auditar_muestras(muestras: Sequence[Any], ids: Sequence[str], *, parametros: int | None = None,
                     umbrales: Umbrales | None = None) -> dict[str, Any]:
    """El informe del dataset del gemelo (RF-29 a RF-33); ``apto`` es falso sin muestras o con
    valores no finitos."""
    from .oraculo import Z_ACOPLADOR_PU

    u = umbrales or Umbrales()
    if not muestras:
        return {'apto': False, 'muestras': 0, 'avisos': ['sin muestras con grafo y tensiones'],
                'no_finitos': [], 'tensiones_fuera_de_rango': []}
    no_finitos, fuera = [], []
    for i, m in zip(ids, muestras, strict=True):
        for campo, arr in (('x', m.x), ('z', m.z), ('v', None if m.v is None else m.v[m.mascara])):
            if arr is not None and not np.isfinite(arr).all():
                no_finitos.append({'episodio': i, 'campo': campo})
        if m.v is not None:
            v = m.v[m.mascara]
            malos = (v < u.v_min_pu) | (v > u.v_max_pu)
            if malos.any():
                fuera.append({'episodio': i, 'nodos': int(malos.sum()),
                              'min_pu': float(v.min()), 'max_pu': float(v.max())})
    redes = len({_red(m) for m in muestras})
    nodos = [len(m.ids) for m in muestras]
    etiquetadas = [float(m.mascara.mean()) if m.mascara is not None and len(m.ids) else 0.0
                   for m in muestras]
    etiquetas = int(sum(m.mascara.sum() for m in muestras if m.mascara is not None))
    con_ramas = [np.abs(m.z) for m in muestras if len(m.z)]
    absz = np.concatenate(con_ramas) if con_ramas else np.array([1.0])
    finitos = absz[np.isfinite(absz) & (absz > 0)]
    # El tope se escribe como r = x = Z_ACOPLADOR_PU: su módulo es √2 veces el tope.
    tope = [int((np.abs(m.z) <= Z_ACOPLADOR_PU * np.sqrt(2) * (1 + 1e-9)).sum()) for m in muestras]
    x = np.concatenate([m.x for m in muestras])
    duplicados = len(muestras) - len({(_red(m), round(float(np.nansum(m.x[:, 1:3])), 9),
                                       round(float(np.nansum(m.v[m.mascara])) if m.v is not None else 0.0, 9))
                                      for m in muestras})
    avisos: list[str] = []
    if no_finitos:
        avisos.append(f'{len(no_finitos)} campo(s) con valores no finitos: no se entrena (027:RF-30).')
    if redes < u.min_redes:
        quien = 'una sola red' if redes == 1 else f'{redes} redes'
        avisos.append(f'{quien} en el dataset: el error de prueba no mide la generalización a otra red '
                      '(027:RF-33).')
    if fuera:
        avisos.append(f'{len(fuera)} episodio(s) con tensiones fuera de {u.v_min_pu}–{u.v_max_pu} p.u.; '
                      'se mantienen: las calculó DIgSILENT (027:RF-32).')
    if parametros and etiquetas:
        avisos.append(f'{parametros:,} parámetros frente a {etiquetas:,} tensiones etiquetadas de '
                      f'{redes} red(es) (027:RF-33).')
    return {
        'apto': not no_finitos,
        'muestras': len(muestras), 'redes': redes,
        'nodos': {'min': min(nodos), 'mediana': int(np.median(nodos)), 'max': max(nodos)},
        'columnas_x': int(x.shape[1]),
        'rango_x': {'min': np.nanmin(x, axis=0).round(4).tolist(), 'max': np.nanmax(x, axis=0).round(4).tolist()},
        'fraccion_etiquetada': {'min': round(min(etiquetadas), 4),
                                'mediana': round(float(np.median(etiquetadas)), 4)},
        'etiquetas': etiquetas, 'parametros': parametros,
        'no_finitos': no_finitos, 'tensiones_fuera_de_rango': fuera, 'duplicados': duplicados,
        'ramas_en_tope': {'tope_pu': Z_ACOPLADOR_PU, 'por_muestra_max': max(tope)},
        'relacion_z': float(finitos.max() / finitos.min()) if len(finitos) else None,
        'avisos': avisos,
    }


def auditar_ordenes(*, reales: int, sinteticas: int, prueba_real: int, parametros: int | None = None,
                    umbrales: Umbrales | None = None) -> dict[str, Any]:
    """El informe del dataset del asistente (RF-33, RF-34): sus puertas solo valen medidas con
    órdenes reales, y con menos de 200 se pide confirmación de todo (RF-19)."""
    u = umbrales or Umbrales()
    avisos = []
    if reales < u.min_ordenes_reales:
        avisos.append(f'{reales} órdenes reales de las {u.min_ordenes_reales} que hacen falta: toda acción '
                      'que escribe pide confirmación (027:RF-19).')
    if prueba_real == 0:
        avisos.append('sin órdenes reales en la prueba: sus métricas son de órdenes sintéticas y no valen '
                      'como puertas (027:RF-34).')
    if parametros:
        avisos.append(f'{parametros:,} parámetros frente a {reales + sinteticas:,} órdenes, '
                      f'{reales} reales (027:RF-33).')
    return {'reales': reales, 'sinteticas': sinteticas, 'prueba_real': prueba_real,
            'parametros': parametros,
            'puertas_con_reales': prueba_real > 0 and reales >= u.min_ordenes_reales,
            'avisos': avisos}
