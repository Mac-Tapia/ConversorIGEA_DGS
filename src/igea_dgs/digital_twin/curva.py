"""Episodios por sistema eléctrico y curva de aprendizaje del gemelo (spec 027, T24; RF-53, RF-54).

El 2026-10-28 el búfer tenía 24 muestras de una sola red (IN111–TA225): el gemelo no podía
decir nada de Nasca, Chincha o Pisco. Antes de promoverlo con un sistema hacen falta al menos
30 episodios de entrenamiento, 10 de validación y 10 de prueba de ese sistema (usuario,
2026-10-28), repartidos por la huella de cada episodio para que el reparto no cambie al crecer
el búfer. La curva de aprendizaje dice si hacen falta más: si añadir un 20 % de episodios
mejora el error de validación menos de un 5 %, ha convergido y no se piden más (Bischl et al.,
2023: el presupuesto de datos se decide con la curva, no a ojo).
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Any

from .escenarios import particion
from .oraculo import Entrenamiento, Muestra, OraculoPINN, entrenar_miembro, mae, red_de

#: Episodios mínimos por sistema y partición (RF-53).
MINIMOS = {'entrenamiento': 30, 'validacion': 10, 'prueba': 10}
#: Mejora relativa por debajo de la cual, con un 20 % más de episodios, se da por convergido.
MEJORA_MIN = 0.05


def reparto_del_sistema(ids: Sequence[str]) -> dict[str, list[int]]:
    """Los índices de los episodios de un sistema por partición, por la huella de cada uno."""
    out: dict[str, list[int]] = {k: [] for k in MINIMOS}
    for i, ident in enumerate(ids):
        out[particion(hashlib.sha256(ident.encode('utf-8')).hexdigest())].append(i)
    return out


def por_sistema(muestras: Sequence[Muestra], ids: Sequence[str]) -> list[dict[str, Any]]:
    """Por sistema (red), sus episodios por partición y cuántos faltan para RF-53."""
    grupos: dict[str, list[int]] = {}
    for i, m in enumerate(muestras):
        grupos.setdefault(red_de(m), []).append(i)
    filas = []
    for red, idx in sorted(grupos.items(), key=lambda x: -len(x[1])):
        reparto = reparto_del_sistema([ids[i] for i in idx])
        cuenta = {k: len(v) for k, v in reparto.items()}
        faltan = {k: max(0, MINIMOS[k] - cuenta[k]) for k in MINIMOS}
        filas.append({'red': red[:12], 'nodos': len(muestras[idx[0]].ids), 'episodios': len(idx),
                      **cuenta, 'faltan': faltan, 'suficiente': not any(faltan.values()),
                      'indices': {k: [idx[j] for j in v] for k, v in reparto.items()}})
    return filas


def curva(entrenamiento: Sequence[Muestra], validacion: Sequence[Muestra], cfg: Entrenamiento,
          fracciones: Sequence[float] = (0.5, 1 / 1.2, 1.0),
          log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """El error de validación con una fracción creciente de los episodios de entrenamiento, y si
    ha convergido: la última fracción es un 20 % más que la anterior (RF-53)."""
    puntos = []
    for f in fracciones:
        n = max(1, round(f * len(entrenamiento)))
        estado = entrenar_miembro(list(entrenamiento)[:n], cfg, None, validacion=validacion)
        dominio = _dominio(entrenamiento)
        error = mae(OraculoPINN([estado], cfg, dominio), validacion)
        puntos.append({'episodios': n, 'mae_validacion': error})
        log(f'  curva: {n} episodio(s) → {error:.3e} p.u. en validación')
    previo, ultimo = puntos[-2]['mae_validacion'], puntos[-1]['mae_validacion']
    mejora = (previo - ultimo) / previo if previo else 0.0
    return {'puntos': puntos, 'mejora_ultimo_20pct': mejora, 'convergido': mejora < MEJORA_MIN}


def _dominio(muestras: Sequence[Muestra]) -> dict[str, Any]:
    import numpy as np

    x = np.concatenate([m.x for m in muestras])
    return {'x_min': x.min(axis=0).tolist(), 'x_max': x.max(axis=0).tolist(),
            'nodos': [min(len(m.ids) for m in muestras), max(len(m.ids) for m in muestras)]}


def informe(muestras: Sequence[Muestra], ids: Sequence[str], cfg: Entrenamiento | None = None,
            log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Por sistema, sus episodios y, si ya tiene los mínimos, su curva de aprendizaje (RF-53)."""
    cfg = cfg or Entrenamiento()
    filas = por_sistema(muestras, ids)
    for f in filas:
        if f['suficiente']:
            log(f"Sistema {f['red']}: {f['entrenamiento']}/{f['validacion']}/{f['prueba']} episodios; curva…")
            f['curva'] = curva([muestras[i] for i in f['indices']['entrenamiento']],
                               [muestras[i] for i in f['indices']['validacion']], cfg, log=log)
        f.pop('indices')
    return {'minimos': MINIMOS, 'sistemas': filas,
            'listos': sum(f['suficiente'] for f in filas), 'convergidos': sum(
                bool((f.get('curva') or {}).get('convergido')) for f in filas)}
