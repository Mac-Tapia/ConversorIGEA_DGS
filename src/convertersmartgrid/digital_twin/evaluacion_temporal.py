"""Métricas por horizonte y puertas predeclaradas del pronóstico (046:RF-5, RF-6, RF-8, RF-18).

Las puertas se fijaron en la spec antes de la primera medición real, y su huella viaja en cada
candidato. Reutiliza ``PoliticaEvaluacion`` y ``verificar_familias`` de 044: una familia es un
objetivo en un horizonte, y toda familia debe pasar, porque una media buena taparía el horizonte
o la máxima que alimentan la calibración y las obras.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

import numpy as np

from ..evaluacion_modelos import PoliticaEvaluacion

#: Solo cambia abriendo otra política con su huella: ver «Puertas predeclaradas» en la spec 046.
POLITICA_TEMPORAL = PoliticaEvaluacion(
    modo='agente', min_calibracion_grupos=7, cobertura_objetivo=.9,
    puertas_por_familia=(('habilidad_pinball', .02), ('habilidad_mae', 0.0), ('maxima_no_peor', 1.0),
                         ('instante_no_peor', 1.0), ('cobertura_en_banda', 1.0), ('mejora_significativa', 1.0)),
    semillas=(11, 23, 37), minimos=(30, 7, 7, 14))
BANDA_COBERTURA = (.85, .95)
#: Mejora de pinball exigida frente al modelo activo, en las mismas ventanas.
MARGEN_ACTIVO = .01
REMUESTRAS_DIAS = 2000
CUANTILES_FILA = {'q05': .05, 'q50': .5, 'q95': .95}


def pinball_de(prediccion: np.ndarray, real: np.ndarray) -> np.ndarray:
    """Pérdida pinball media de los tres cuantiles, por ventana y horizonte."""
    q = np.array(list(CUANTILES_FILA.values()))
    error = real[..., None] - prediccion
    return np.maximum(q * error, (q - 1) * error).mean(axis=-1)


def _claves(filas: Sequence[Mapping]) -> str:
    claves = sorted(f"{f['target']}|{f['emission_time']}|{f['horizon_steps']}" for f in filas)
    return hashlib.sha256('\n'.join(claves).encode('utf-8')).hexdigest()


def verificar_ventanas_identicas(por_modelo: Mapping[str, Sequence[Mapping]]) -> str:
    """Todos los modelos con las mismas emisiones, objetivos y horizontes, o error (046:RF-5)."""
    huellas = {modelo: _claves(filas) for modelo, filas in por_modelo.items()}
    if len(set(huellas.values())) > 1:
        raise ValueError(f'ventanas distintas entre modelos: {sorted(huellas)}')
    return next(iter(huellas.values()))


def evaluar_pronosticos(real: Sequence[Mapping], predicciones: Sequence[Mapping], *,
                        politica: PoliticaEvaluacion) -> dict:
    """MAE, RMSE, pinball y cobertura por objetivo y horizonte, con su n y sus días (046:RF-6).

    Se agrupa por el día de la emisión: las ventanas de un día se solapan y no son muestras
    independientes. El intervalo es q05–q95 y solo vale para una política del 90 %.
    """
    nominal = CUANTILES_FILA['q95'] - CUANTILES_FILA['q05']
    if not math.isclose(nominal, politica.cobertura_objetivo):
        raise ValueError(f'los cuantiles q05–q95 son un {nominal:.0%}, no el {politica.cobertura_objetivo:.0%} de la política')
    medido = {(r['target'], r['forecast_time']): float(r['valor']) for r in real}
    filas_por = defaultdict(list)
    for f in predicciones:
        if not set(CUANTILES_FILA) <= set(f):
            raise ValueError(f"{f.get('target')}: sin los cuantiles q05, q50 y q95")
        if not f['q05'] - 1e-9 <= f['q50'] <= f['q95'] + 1e-9:
            raise ValueError(f"{f['target']}: cuantiles no ordenados en {f['forecast_time']}")
        clave = (f['target'], f['forecast_time'])
        if clave not in medido:
            raise ValueError(f"{f['target']}: {f['forecast_time']} sin medición con que compararlo")
        filas_por[f['target'], f['horizon_steps']].append(f)
    contextos: dict[str, dict[int, dict]] = defaultdict(dict)
    for (objetivo, h), filas in sorted(filas_por.items()):
        y = np.array([medido[f['target'], f['forecast_time']] for f in filas])
        pred = np.array([[f['q05'], f['q50'], f['q95']] for f in filas])
        perdida = pinball_de(pred, y)
        error = pred[:, 1] - y
        dias: dict[str, list[float]] = defaultdict(list)
        for f, p in zip(filas, perdida.tolist(), strict=True):
            dias[f['emission_time'][:10]].append(p)
        contextos[objetivo][h] = {
            'n': len(y), 'grupos': len(dias), 'mae': float(np.abs(error).mean()),
            'rmse': float(np.sqrt((error ** 2).mean())), 'pinball': float(perdida.mean()),
            'cobertura': float(((pred[:, 0] <= y) & (y <= pred[:, 2])).mean()),
            'por_dia': {d: float(np.mean(v)) for d, v in dias.items()}}
    return {'contextos': dict(contextos), 'cobertura_nominal': nominal, 'politica_hash': politica.hash}


def sesgo_de_maxima(real: np.ndarray, q50: np.ndarray, *, puntos_trayectoria: int) -> float:
    """Lo que la máxima real supera a la de q50 en la mediana, medido en calibración (spec 046, puertas)."""
    if not len(real):
        return 0.0
    return float(np.median(real[:, :puntos_trayectoria].max(axis=1) - q50[:, :puntos_trayectoria].max(axis=1)))


def error_de_maxima(real: np.ndarray, q50: np.ndarray, *, cadencia_min: int, puntos_trayectoria: int,
                    sesgo: float = 0.0, dias: Sequence[str] | None = None) -> dict:
    """Error de la máxima de cada trayectoria y minutos de error en su instante (046:RF-18).

    Son los dos valores que usarían la calibración y las obras: una curva buena en media que se
    pierde el pico o lo pone tres horas tarde no sirve para eso.
    """
    y, p = real[:, :puntos_trayectoria], q50[:, :puntos_trayectoria]
    if not len(y):
        return {'error_maxima': float('inf'), 'error_instante_min': float('inf'), 'n': 0}
    maxima = np.abs(y.max(axis=1) - p.max(axis=1) - sesgo)
    instante = np.abs(y.argmax(axis=1) - p.argmax(axis=1)) * float(cadencia_min)
    salida = {'error_maxima': float(maxima.mean()), 'error_instante_min': float(instante.mean()), 'n': len(y)}
    if dias is not None:
        salida['por_dia_maxima'] = _media_por_dia(dias, maxima)
        salida['por_dia_instante'] = _media_por_dia(dias, instante)
    return salida


def _media_por_dia(dias: Sequence[str], valores: np.ndarray) -> dict[str, float]:
    grupos: dict[str, list[float]] = defaultdict(list)
    for d, v in zip(dias, valores.tolist(), strict=True):
        grupos[d].append(v)
    return {d: float(np.mean(v)) for d, v in grupos.items()}


def _habilidad(modelo: float, referencia: float) -> float:
    """1 − modelo/referencia. Una referencia con error cero no se puede mejorar."""
    if referencia <= 0:
        return 0.0 if modelo <= 0 else -1.0
    return float(1 - modelo / referencia)


def _ic_mejora(modelo: Mapping[str, float], referencia: Mapping[str, float], semilla: int) -> tuple[float, float] | None:
    """IC 90 % de la mejora media por día; se remuestrean días, no ventanas, que se solapan."""
    dias = sorted(set(modelo) & set(referencia))
    if not dias:
        return None
    mejora = np.array([referencia[d] - modelo[d] for d in dias])
    rng = np.random.default_rng(semilla)
    medias = mejora[rng.integers(0, len(dias), (REMUESTRAS_DIAS, len(dias)))].mean(axis=1)
    return float(np.quantile(medias, .05)), float(np.quantile(medias, .95))


def _mejora_significativa(modelo: Mapping[str, float], referencia: Mapping[str, float], semilla: int) -> float:
    ic = _ic_mejora(modelo, referencia, semilla)
    return float(ic is not None and ic[0] > 0)


def _no_peor(modelo: Mapping[str, float], referencia: Mapping[str, float], semilla: int) -> float:
    ic = _ic_mejora(modelo, referencia, semilla)
    return float(ic is not None and ic[1] >= 0)


def familias_de(objetivo: str, modelo: Mapping[int, Mapping], referencia: Mapping[int, Mapping], *,
                politica: PoliticaEvaluacion) -> dict[str, dict]:
    """Por horizonte, los valores que ``verificar_familias`` compara con las puertas."""
    familias = {}
    for h, m in modelo.items():
        r = referencia[h]
        familias[f'{objetivo}|h{h}'] = {
            'ejemplos': int(m['grupos']),
            'habilidad_pinball': _habilidad(m['pinball'], r['pinball']),
            'habilidad_mae': _habilidad(m['mae'], r['mae']),
            'maxima_no_peor': _no_peor(m['por_dia_maxima'], r['por_dia_maxima'], politica.semillas[0]),
            'instante_no_peor': _no_peor(m['por_dia_instante'], r['por_dia_instante'], politica.semillas[0]),
            'habilidad_maxima': _habilidad(m['error_maxima'], r['error_maxima']),
            'habilidad_instante': _habilidad(m['error_instante_min'], r['error_instante_min']),
            'cobertura_en_banda': float(BANDA_COBERTURA[0] <= m['cobertura'] <= BANDA_COBERTURA[1]),
            'mejora_significativa': _mejora_significativa(m['por_dia'], r['por_dia'], politica.semillas[0])}
    return familias
