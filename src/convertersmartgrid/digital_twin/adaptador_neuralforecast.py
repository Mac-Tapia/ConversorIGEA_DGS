"""N-HiTS, TFT, PatchTST, TiDE e iTransformer de neuralforecast, opcionales y solo en CUDA (046:RF-13 a RF-15, RF-26).

neuralforecast se importa al crear el adaptador: el núcleo arranca sin él. Si no se le fuerza,
cae a la CPU cuando no ve la GPU sin decir nada, y el usuario lo prohíbe (2026-10-22: «sí o sí
debe conectar a GPU»): por eso se exige CUDA antes de cargarlo y se le pasa ``accelerator='gpu'``.

La escala es la de cada ventana de entrada (``scaler_type='robust'``), con ``local_scaler_type``
vacío: una escala global por serie se ajustaría con toda la curva que se le da, y aquí solo
llega lo anterior al corte (046:RF-1).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from .series_causales import CUANTILES, tramos_observados

CLASE = {'nhits': 'NHITS', 'tft': 'TFT', 'patchtst': 'PatchTST', 'nbeatsx': 'NBEATSx', 'itransformer': 'iTransformer',
         'timesnet': 'TimesNet', 'tide': 'TiDE', 'tsmixerx': 'TSMixerx', 'bitcn': 'BiTCN'}
#: Los que aceptan el calendario como futuro conocido. PatchTST declara ``EXOGENOUS_FUTR = False``.
CON_CALENDARIO = ('nhits', 'tft', 'nbeatsx', 'itransformer', 'timesnet', 'tide', 'tsmixerx', 'bitcn')
#: Ventanas por tanda al predecir: una tanda grande llena la memoria con la tabla de entrada.
VENTANAS_POR_TANDA = 64
#: Multivariantes: piden ``n_series`` y ven todas las series juntas (046:RF-26). Con la tabla de los univariantes
#: (cada tramo y cada ventana, una serie) iTransformer fallaba en la GPU: «missing n_series» (2026-11-10).
MULTIVARIANTES = ('itransformer', 'tsmixerx')


def tramo_comun(conjunto: Any, fin: int, *, minimo: int) -> tuple[int, int]:
    """El tramo continuo más largo antes de ``fin`` en que todas las series tienen dato; un hueco no se rellena."""
    ok = np.all([np.isfinite(conjunto.valores[n][:fin]) for n in conjunto.nombres], axis=0)
    mejor, inicio = (0, 0), None
    for i, bueno in enumerate([*ok, False]):
        if bueno and inicio is None:
            inicio = i
        elif not bueno and inicio is not None:
            if i - inicio > mejor[1] - mejor[0]:
                mejor = (inicio, i)
            inicio = None
    if mejor[1] - mejor[0] < minimo:
        raise ValueError(f'ningún tramo con todas las series ({len(conjunto.nombres)}) llega a {minimo} pasos: '
                         'el modelo multivariante necesita verlas juntas')
    return mejor


def tabla_panel(conjunto: Any, fin: int, *, minimo: int):
    """Todas las series en su tramo común, cada una con su nombre (046:RF-26)."""
    import pandas as pd

    a, b = tramo_comun(conjunto, fin, minimo=minimo)
    partes = []
    for nombre in sorted(conjunto.nombres):
        d = pd.DataFrame(conjunto.calendario[a:b], columns=list(conjunto.covariables))
        d.insert(0, 'y', conjunto.valores[nombre][a:b])
        d.insert(0, 'ds', [t.replace(tzinfo=None) for t in conjunto.instantes[a:b]])
        d.insert(0, 'unique_id', nombre)
        partes.append(d)
    return pd.concat(partes, ignore_index=True)


def disponibilidad_neuralforecast(algoritmo: str) -> dict:
    """Disponible si carga de verdad, con el motivo si no (046:RF-14)."""
    try:
        from neuralforecast import models
        getattr(models, CLASE[algoritmo])
    except Exception as exc:  # noqa: BLE001 - una DLL o un paquete roto dan errores propios; es el motivo
        return {'disponible': False, 'motivo': f'neuralforecast no carga {algoritmo}: {exc}'}
    return {'disponible': True, 'motivo': ''}


def tabla_entrenamiento(conjunto: Any, fin: int, *, minimo: int):
    """Solo lo anterior a ``fin``, en tramos continuos: cada tramo es una serie y un hueco no se rellena."""
    import pandas as pd

    partes = []
    for nombre in conjunto.nombres:
        v = conjunto.valores[nombre]
        for k, (a, b) in enumerate(tramos_observados(v, fin, minimo=minimo)):
            d = pd.DataFrame(conjunto.calendario[a:b], columns=list(conjunto.covariables))
            d.insert(0, 'y', v[a:b])
            d.insert(0, 'ds', [t.replace(tzinfo=None) for t in conjunto.instantes[a:b]])
            d.insert(0, 'unique_id', f'{nombre}#{k}')
            partes.append(d)
    if not partes:
        raise ValueError('ningún tramo de entrenamiento llega al contexto más el horizonte')
    return pd.concat(partes, ignore_index=True)


def argumentos_modelo(algoritmo: str, *, horizonte: int, contexto_pasos: int, semilla: int, pasos: int, lote: int,
                      covariables: Sequence[str]) -> dict:
    """Argumentos del modelo, en lotes pequeños: la tarjeta es de 8 GB y la memoria es compartida."""
    kw = {'h': horizonte, 'input_size': contexto_pasos, 'max_steps': pasos, 'batch_size': min(32, lote),
          'windows_batch_size': lote, 'inference_windows_batch_size': lote, 'scaler_type': 'robust',
          'random_seed': semilla, 'accelerator': 'gpu', 'devices': 1, 'logger': False,
          'enable_progress_bar': False, 'enable_model_summary': False}
    if algoritmo in CON_CALENDARIO:
        kw['futr_exog_list'] = list(covariables)
    return kw


def tablas_prediccion(lote: Any, algoritmo: str):
    """Cada ventana es una serie propia: así predicen en las mismas emisiones que los demás (046:RF-5)."""
    import pandas as pd

    con_calendario = algoritmo in CON_CALENDARIO
    contexto, futuro = [], []
    n_ctx = lote.contextos.shape[1]
    frecuencia = f'{lote.cadencia_min}min'
    for i, fin in enumerate(lote.fin_contexto):
        ident = f'v{i:07d}'
        horas = pd.date_range(end=fin, periods=n_ctx, freq=frecuencia)
        c = pd.DataFrame({'unique_id': ident, 'ds': horas, 'y': lote.contextos[i]})
        f = pd.DataFrame({'unique_id': ident,
                          'ds': pd.date_range(start=fin, periods=lote.horizonte + 1, freq=frecuencia)[1:]})
        if con_calendario:
            for j, nombre in enumerate(lote.covariables):
                c[nombre] = lote.calendario_pasado[i, :, j]
                f[nombre] = lote.calendario_futuro[i, :, j]
        contexto.append(c)
        futuro.append(f)
    return pd.concat(contexto, ignore_index=True), pd.concat(futuro, ignore_index=True)


def a_arreglo(salida, prefijo: str, *, n: int, horizonte: int) -> np.ndarray:
    """(ventana, horizonte, cuantil) desde las columnas ``-lo-90.0``, ``-median`` y ``-hi-90.0``."""
    if 'unique_id' not in salida.columns:
        salida = salida.reset_index()
    salida = salida.sort_values(['unique_id', 'ds'])
    if len(salida) != n * horizonte:
        raise RuntimeError(f'neuralforecast devolvió {len(salida)} filas; se esperaban {n * horizonte}')
    columnas = [next(c for c in salida.columns if c.startswith(f'{prefijo}-{parte}')) for parte in ('lo', 'median', 'hi')]
    return salida[columnas].to_numpy(dtype=float).reshape(n, horizonte, len(CUANTILES))


class AdaptadorNeuralForecast:
    """Un modelo global para todos los objetivos de la corrida, con la interfaz común."""

    requiere_gpu = True

    def __init__(self, algoritmo: str, *, horizonte: int, cadencia_min: int, contexto_pasos: int | None = None,
                 pasos: int = 1500, lote: int = 128, semilla: int = 0, series: Sequence[str] | None = None):
        from .oraculo import dispositivo

        dispositivo()                    # sin CUDA, SinGPU antes de cargar nada (046:RF-15)
        self.algoritmo = algoritmo
        self.horizonte, self.cadencia_min, self.pasos, self.lote = horizonte, cadencia_min, pasos, lote
        self.contexto_pasos = contexto_pasos or 2 * 1440 // cadencia_min
        self.semilla = semilla
        self.series: list[str] = list(series or [])
        self.nf = None

    @property
    def multivariante(self) -> bool:
        return self.algoritmo in MULTIVARIANTES

    def ajustar(self, conjunto: Any, fin_entrenamiento: int, horizonte: int, semilla: int) -> dict:
        from neuralforecast import NeuralForecast, models
        from neuralforecast.losses.pytorch import MQLoss

        minimo = self.contexto_pasos + horizonte
        kw = argumentos_modelo(self.algoritmo, horizonte=horizonte, contexto_pasos=self.contexto_pasos, semilla=semilla,
                               pasos=self.pasos, lote=self.lote, covariables=conjunto.covariables)
        if self.multivariante:
            tabla = tabla_panel(conjunto, fin_entrenamiento, minimo=minimo)[['unique_id', 'ds', 'y']]
            self.series = sorted(conjunto.nombres)
            kw['n_series'] = len(self.series)
            # Sin calendario: neuralforecast 3.3 escala también las exógenas de un multivariante con la escala de la
            # ventana, y en una ventana corta el día de la semana es constante: escala cero y todo sale NaN (2026-11-10).
            kw.pop('futr_exog_list', None)
        else:
            tabla = tabla_entrenamiento(conjunto, fin_entrenamiento, minimo=minimo)
        modelo = getattr(models, CLASE[self.algoritmo])(loss=MQLoss(quantiles=list(CUANTILES)), **kw)
        self.nf = NeuralForecast(models=[modelo], freq=f'{self.cadencia_min}min', local_scaler_type=None)
        if self.algoritmo not in CON_CALENDARIO:
            tabla = tabla[['unique_id', 'ds', 'y']]
        self.nf.fit(df=tabla)
        self.horizonte = horizonte
        return {'pasos': self.pasos, 'series': int(tabla['unique_id'].nunique()), 'filas': len(tabla)}

    def predecir(self, lote: Any) -> np.ndarray:
        if self.nf is None:
            raise RuntimeError(f'{self.algoritmo} sin ajustar')
        if self.multivariante:
            return self._predecir_panel(lote)
        contextos, calendario = lote.recorte(self.contexto_pasos)
        salida = []
        for a in range(0, lote.n, VENTANAS_POR_TANDA):
            b = min(a + VENTANAS_POR_TANDA, lote.n)
            tanda = replace(lote, objetivos=lote.objetivos[a:b], contextos=contextos[a:b], calendario_pasado=calendario[a:b],
                            calendario_futuro=lote.calendario_futuro[a:b], fin_contexto=lote.fin_contexto[a:b])
            ctx, fut = tablas_prediccion(tanda, self.algoritmo)
            kw = {'futr_df': fut} if self.algoritmo in CON_CALENDARIO else {}
            salida.append(a_arreglo(self.nf.predict(df=ctx, **kw), CLASE[self.algoritmo], n=b - a, horizonte=lote.horizonte))
        return np.concatenate(salida) if salida else np.zeros((0, lote.horizonte, len(CUANTILES)))

    def _predecir_panel(self, lote: Any) -> np.ndarray:
        """Una predicción por emisión con todas las series, y a cada ventana la de su objetivo (046:RF-26).

        Solo con lo conocido en esa emisión: si a una serie le falta un dato del contexto, esa emisión no se predice
        y se dice; no se rellena (046:RF-1).
        """
        import pandas as pd

        if lote.valores is None or lote.emisiones is None:
            raise ValueError(f'{self.algoritmo} es multivariante: el lote debe venir de Conjunto.lote, con la rejilla')
        ajenas = sorted(set(lote.objetivos) - set(self.series))
        if ajenas:
            raise ValueError(f'{self.algoritmo} no se entrenó con {", ".join(ajenas)}')
        n_ctx, h = self.contexto_pasos, lote.horizonte
        if n_ctx > lote.contextos.shape[1]:
            raise ValueError(f'el modelo pide {n_ctx} pasos y la ventana común tiene {lote.contextos.shape[1]}')
        salida = np.full((lote.n, h, len(CUANTILES)), np.nan)
        frecuencia = f'{lote.cadencia_min}min'
        por_emision: dict[int, list[int]] = {}
        for i, e in enumerate(lote.emisiones):
            por_emision.setdefault(int(e), []).append(i)
        for e, indices in por_emision.items():
            fin = lote.fin_contexto[indices[0]]
            horas = pd.date_range(end=fin, periods=n_ctx, freq=frecuencia)
            contexto = []
            for nombre in self.series:
                v = np.asarray(lote.valores[nombre][e - n_ctx + 1:e + 1], dtype=float)
                if len(v) != n_ctx or not np.isfinite(v).all():
                    raise ValueError(f'{nombre} tiene un hueco en el contexto de la emisión {fin}: '
                                     f'{self.algoritmo} necesita todas las series y no se rellena')
                contexto.append(pd.DataFrame({'unique_id': nombre, 'ds': horas, 'y': v}))
            pred = a_arreglo(self.nf.predict(df=pd.concat(contexto, ignore_index=True)),
                             CLASE[self.algoritmo], n=len(self.series), horizonte=h)
            for i in indices:
                salida[i] = pred[self.series.index(lote.objetivos[i])]
        return salida

    def guardar(self, carpeta: Path) -> None:
        if self.nf is None:
            raise RuntimeError(f'{self.algoritmo} sin ajustar')
        carpeta.mkdir(parents=True, exist_ok=True)
        self.nf.save(path=str(carpeta), overwrite=True, save_dataset=False)
        (carpeta / 'adaptador.json').write_text(json.dumps({
            'horizonte': self.horizonte, 'cadencia_min': self.cadencia_min, 'contexto_pasos': self.contexto_pasos,
            'pasos': self.pasos, 'lote': self.lote, 'semilla': self.semilla, 'series': self.series}), encoding='utf-8')

    @classmethod
    def reabrir(cls, carpeta: Path, algoritmo: str) -> AdaptadorNeuralForecast:
        from neuralforecast import NeuralForecast

        cfg = json.loads((carpeta / 'adaptador.json').read_text(encoding='utf-8'))
        m = cls(algoritmo, **cfg)
        m.nf = NeuralForecast.load(path=str(carpeta))
        return m
