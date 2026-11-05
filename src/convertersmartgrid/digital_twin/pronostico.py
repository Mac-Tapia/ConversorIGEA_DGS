"""Contrato multihorizonte del pronóstico de demanda (spec 046).

Objetivos: la demanda de cabecera y la de cada cliente fijo, en kW y kVAR. Compiten en las
mismas ventanas el ingenuo y el estacional semanal, que son referencias y no piden GPU, la GRU
y los adaptadores opcionales. Un pronóstico es siempre un artefacto aparte con su marca: nunca
sustituye a la medición en la calibración, el «Caso base» o los informes (046:RF-20).

Importar este módulo no carga PyTorch ni neuralforecast: son dependencias opcionales y el
núcleo del conversor arranca sin ellas (046:RF-14).
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from ..evaluacion_modelos import PARTES, PoliticaEvaluacion
from .series_causales import (
    CUANTILES,
    horizontes_validos,
    particionar_dias,
    preparar_serie,
    ventanas_causales,
)

REFERENCIAS = ('ingenuo', 'estacional_semanal')
NEURONALES = ('gru', 'nhits', 'tft', 'patchtst')
CLASES = ('cabecera', 'cliente', 'escaladas')
#: Lo único que se usa además de la serie: se conoce al emitir porque es el reloj (046:RF-2).
COVARIABLES = ('hora_sin', 'hora_cos', 'dia_sin', 'dia_cos')
#: Un objetivo con más ceros que esto en lo observado no tiene señal que aprender. Hay medidores
#: de reserva con todas sus lecturas en cero, y la habilidad frente a una referencia perfecta no
#: tendría sentido; los cortes reales, unas decenas de ceros, se quedan.
FRACCION_MAX_CEROS = .5


@dataclass(frozen=True)
class Objetivo:
    """Una serie medida que pronosticar, con su procedencia."""

    clase: str
    ident: str
    magnitud: str
    unidad: str
    curva: Sequence[tuple[datetime, float]]
    fuente: Mapping[str, Any] = field(default_factory=dict)

    @property
    def nombre(self) -> str:
        return f'{self.clase}:{self.ident}:{self.magnitud}'


@dataclass
class LoteVentanas:
    """Lo que un modelo puede ver al emitir: nunca una medida posterior (046:RF-1, RF-2)."""

    objetivos: list[str]
    contextos: np.ndarray               # (n, contexto)
    calendario_pasado: np.ndarray       # (n, contexto, covariables)
    calendario_futuro: np.ndarray       # (n, horizonte, covariables)
    fin_contexto: list[datetime]        # instante de cada emisión, en UTC sin zona
    cadencia_min: int
    covariables: tuple[str, ...] = COVARIABLES

    @property
    def n(self) -> int:
        return len(self.objetivos)

    @property
    def horizonte(self) -> int:
        return self.calendario_futuro.shape[1]

    def recorte(self, contexto: int) -> tuple[np.ndarray, np.ndarray]:
        """Los últimos ``contexto`` pasos, para un modelo que usa menos de la ventana común."""
        if contexto > self.contextos.shape[1]:
            raise ValueError(f'el modelo pide {contexto} pasos y la ventana común tiene {self.contextos.shape[1]}')
        return self.contextos[:, -contexto:], self.calendario_pasado[:, -contexto:]


def _calendario(instantes: Sequence[datetime], zona: ZoneInfo) -> np.ndarray:
    """Hora del día y día de la semana locales en senos y cosenos."""
    salida = np.zeros((len(instantes), len(COVARIABLES)))
    for i, t in enumerate(instantes):
        local = t.astimezone(zona)
        hora = 2 * math.pi * (local.hour * 60 + local.minute) / 1440
        dia = 2 * math.pi * local.weekday() / 7
        salida[i] = (math.sin(hora), math.cos(hora), math.sin(dia), math.cos(dia))
    return salida


class Conjunto:
    """Los objetivos de una corrida sobre una rejilla común en UTC, con NaN en los huecos."""

    def __init__(self, instantes: list[datetime], valores: dict[str, np.ndarray], objetivos: Mapping[str, Objetivo],
                 apartados: list[dict], *, cadencia_min: int, zona_horaria: str):
        self.instantes, self.valores, self.objetivos = instantes, valores, dict(objetivos)
        self.apartados, self.cadencia_min, self.zona_horaria = apartados, cadencia_min, zona_horaria
        self.zona = ZoneInfo(zona_horaria)
        self.covariables = COVARIABLES
        self.calendario = _calendario(instantes, self.zona)
        self._extendido = self.calendario

    @property
    def nombres(self) -> list[str]:
        return list(self.valores)

    def _calendario_hasta(self, fin: int) -> np.ndarray:
        """El calendario sigue después del último dato: un pronóstico cae en el futuro."""
        if fin > len(self._extendido):
            paso = timedelta(minutes=self.cadencia_min)
            ultimo = self.instantes[-1]
            extra = [ultimo + paso * (i + 1) for i in range(fin - len(self.instantes))]
            self._extendido = np.vstack((self.calendario, _calendario(extra, self.zona)))
        return self._extendido

    def lote(self, objetivos: Sequence[str], emisiones: np.ndarray, *, contexto: int, horizonte: int) -> LoteVentanas:
        """Solo copia lo conocido en cada emisión: ``valores[e - contexto + 1 .. e]``."""
        emisiones = np.asarray(emisiones, dtype=int)
        desplazamiento = np.arange(contexto) - contexto + 1
        contextos = np.stack([self.valores[o][e + desplazamiento] for o, e in zip(objetivos, emisiones, strict=True)]) \
            if len(emisiones) else np.zeros((0, contexto))
        if not np.isfinite(contextos).all():
            raise ValueError('una ventana tiene un hueco en el contexto: no se rellena')
        calendario = self._calendario_hasta(int(emisiones.max(initial=0)) + horizonte + 1)
        futuro = np.arange(1, horizonte + 1)
        return LoteVentanas(list(objetivos), contextos,
                            calendario[emisiones[:, None] + desplazamiento],
                            calendario[emisiones[:, None] + futuro],
                            [self.instantes[int(e)].replace(tzinfo=None) for e in emisiones], self.cadencia_min)

    def ventanas_comunes(self, politica: PoliticaEvaluacion, *, contexto_pasos: int, horizonte_max: int,
                         paso: int) -> dict:
        """Las ventanas de cada objetivo por partición, fijadas antes de ajustar ningún modelo (046:RF-5)."""
        particion = particionar_dias(self.instantes, self.zona_horaria, politica)
        partes = {p: {n: ventanas_causales(self.valores[n], inicio=particion['limites'][p][0],
                                           fin=particion['limites'][p][1], contexto_pasos=contexto_pasos,
                                           horizonte_max=horizonte_max, paso=paso)
                      for n in self.nombres} for p in PARTES}
        huella = hashlib.sha256()
        huella.update(json.dumps([self.instantes[0].isoformat(), self.cadencia_min, contexto_pasos, horizonte_max,
                                  paso, politica.hash]).encode())
        for p in PARTES:
            for n in sorted(self.nombres):
                huella.update(f'{p}|{n}|'.encode())
                huella.update(partes[p][n].astype('int64').tobytes())
        return {**particion, 'partes': partes, 'huella': huella.hexdigest()}

    def ultima_emision(self, nombre: str, contexto: int) -> int:
        """La última emisión con todo su contexto observado."""
        ok = np.isfinite(self.valores[nombre])
        for e in range(len(ok) - 1, contexto - 2, -1):
            if ok[e - contexto + 1:e + 1].all():
                return e
        raise ValueError(f'{nombre}: ningún contexto de {contexto} pasos está completo')


def construir_conjunto(objetivos: Sequence[Objetivo], *, cadencia_min: int, zona_horaria: str) -> Conjunto:
    """Valida cada objetivo con ``preparar_serie``; el que no cumple se aparta y se dice (046:RF-12)."""
    preparadas, apartados = {}, []
    for o in objetivos:
        try:
            if not o.curva:
                raise ValueError('sin registros')
            ultimo = max(t for t, _v in o.curva)
            p = preparar_serie([{'instante': t.isoformat(), 'valor': v, 'unidad': o.unidad} for t, v in o.curva],
                               corte=(ultimo + timedelta(minutes=cadencia_min)).isoformat(),
                               cadencia_min=cadencia_min, zona_horaria=zona_horaria, covariables={})
        except ValueError as exc:
            apartados.append({'objetivo': o.nombre, 'motivo': str(exc)})
            continue
        observados = [f['valor'] for f in p['filas'] if f['valor'] is not None]
        if sum(v == 0 for v in observados) > FRACCION_MAX_CEROS * len(observados):
            apartados.append({'objetivo': o.nombre, 'motivo': 'sin señal: más de la mitad de las lecturas son cero'})
            continue
        preparadas[o.nombre] = (o, {datetime.fromisoformat(f['instante']): f['valor'] for f in p['filas']})
    if not preparadas:
        return Conjunto([], {}, {}, apartados, cadencia_min=cadencia_min, zona_horaria=zona_horaria)
    inicio = min(min(s) for _o, s in preparadas.values())
    fin = max(max(s) for _o, s in preparadas.values())
    paso = timedelta(minutes=cadencia_min)
    instantes = [inicio + paso * i for i in range((fin - inicio) // paso + 1)]
    valores = {}
    for nombre, (_o, serie) in preparadas.items():
        valores[nombre] = np.array([np.nan if (v := serie.get(t)) is None else v for t in instantes])
    return Conjunto(instantes, valores, {n: o for n, (o, _s) in preparadas.items()}, apartados,
                    cadencia_min=cadencia_min, zona_horaria=zona_horaria)


def _trayectoria(punto: np.ndarray) -> np.ndarray:
    """Una referencia da un solo valor por paso: sus intervalos salen de la calibración."""
    return np.repeat(punto[:, :, None], len(CUANTILES), axis=2)


class Ingenuo:
    """Persistencia: el último valor observado. Difícil de batir a 15 minutos."""

    algoritmo = 'ingenuo'
    requiere_gpu = False
    contexto_pasos = 1

    def ajustar(self, _conjunto: Conjunto, _fin: int, _horizonte: int, _semilla: int) -> dict:
        return {}

    def predecir(self, lote: LoteVentanas) -> np.ndarray:
        return _trayectoria(np.repeat(lote.contextos[:, -1:], lote.horizonte, axis=1))


class EstacionalSemanal:
    """El mismo instante de la última semana ya observada al emitir, en cada horizonte."""

    algoritmo = 'estacional_semanal'
    requiere_gpu = False

    def __init__(self, cadencia_min: int):
        periodo = 7 * 1440 / cadencia_min
        if not periodo.is_integer():
            raise ValueError(f'una cadencia de {cadencia_min} min no divide la semana')
        self.periodo = self.contexto_pasos = int(periodo)

    def ajustar(self, _conjunto: Conjunto, _fin: int, _horizonte: int, _semilla: int) -> dict:
        return {}

    def predecir(self, lote: LoteVentanas) -> np.ndarray:
        if lote.contextos.shape[1] < self.periodo:
            raise ValueError(f'el estacional semanal pide {self.periodo} pasos de contexto')
        h = np.arange(1, lote.horizonte + 1)
        semanas = np.ceil(h / self.periodo).astype(int)
        return _trayectoria(lote.contextos[:, -1 + h - semanas * self.periodo])


def disponibilidad(algoritmo: str) -> dict:
    """Disponible solo si de verdad carga: un adaptador no se declara por estar en la lista (046:RF-14)."""
    if algoritmo in REFERENCIAS:
        return {'disponible': True, 'motivo': ''}
    if algoritmo == 'gru':
        try:
            from .oraculo import dispositivo

            dispositivo()
        except (ImportError, OSError, RuntimeError) as exc:
            return {'disponible': False, 'motivo': str(exc)}
        return {'disponible': True, 'motivo': ''}
    if algoritmo in NEURONALES:
        from .adaptador_neuralforecast import disponibilidad_neuralforecast

        return disponibilidad_neuralforecast(algoritmo)
    return {'disponible': False, 'motivo': f'algoritmo desconocido: {algoritmo}'}


def fabrica(algoritmo: str, *, horizonte: int, cadencia_min: int, contexto_pasos: int | None = None,
            pasos: int | None = None, lote: int | None = None, semilla: int = 0):
    """El modelo de cada algoritmo; PyTorch y neuralforecast se cargan aquí, al pedirlo."""
    if algoritmo == 'ingenuo':
        return Ingenuo()
    if algoritmo == 'estacional_semanal':
        return EstacionalSemanal(cadencia_min)
    ajustes = {k: v for k, v in (('contexto_pasos', contexto_pasos), ('pasos', pasos), ('lote', lote)) if v is not None}
    if algoritmo == 'gru':
        from .temporal import GemeloGRUMultihorizonte

        return GemeloGRUMultihorizonte(horizonte=horizonte, cadencia_min=cadencia_min, semilla=semilla, **ajustes)
    if algoritmo in NEURONALES:
        from .adaptador_neuralforecast import AdaptadorNeuralForecast

        return AdaptadorNeuralForecast(algoritmo, horizonte=horizonte, cadencia_min=cadencia_min, semilla=semilla, **ajustes)
    raise ValueError(f'algoritmo desconocido: {algoritmo}')


def reabrir_modelo(algoritmo: str, carpeta: Path):
    """El modelo guardado en ``carpeta``, para la reapertura en otro proceso (046:RF-7)."""
    if algoritmo == 'gru':
        from .temporal import GemeloGRUMultihorizonte

        return GemeloGRUMultihorizonte.reabrir(carpeta)
    if algoritmo in NEURONALES:
        from .adaptador_neuralforecast import AdaptadorNeuralForecast

        return AdaptadorNeuralForecast.reabrir(carpeta, algoritmo)
    raise ValueError(f'{algoritmo} no guarda artefacto')


def calibrar_intervalos(prediccion: np.ndarray, real: np.ndarray, *, cobertura: float) -> np.ndarray:
    """Ensanche por horizonte (conformal por cuantiles) con datos que no ajustaron el modelo (046:RF-6).

    Es igual para todos los modelos: el estacional, sin intervalos propios, y las redes, cuyos
    cuantiles salen del entrenamiento y suelen quedarse cortos en datos posteriores.
    """
    if not len(real):
        raise ValueError('sin ventanas de calibración')
    error = np.maximum(prediccion[..., 0] - real, real - prediccion[..., 2])
    nivel = min(1.0, cobertura * (1 + 1 / len(real)))
    return np.quantile(error, nivel, axis=0)


def aplicar_ajuste(prediccion: np.ndarray, ajuste: np.ndarray | None) -> np.ndarray:
    """Cuantiles ensanchados y en orden."""
    salida = prediccion.copy()
    if ajuste is not None:
        salida[..., 0] -= ajuste
        salida[..., 2] += ajuste
    return np.sort(salida, axis=-1)


def filas_pronostico(conjunto: Conjunto, nombre: str, emisiones: np.ndarray, prediccion: np.ndarray,
                     horizontes: Sequence[int], algoritmo: str) -> list[dict]:
    """Las filas del contrato (046:RF-4, RF-19): en cada una, qué se predijo, cuándo y con qué."""
    o = conjunto.objetivos[nombre]
    cadencia = conjunto.cadencia_min
    paso = timedelta(minutes=cadencia)
    filas = []
    for i, e in enumerate(np.asarray(emisiones, dtype=int)):
        emision = conjunto.instantes[int(e)].astimezone(timezone.utc)
        texto = emision.astimezone(conjunto.zona).isoformat()
        for h in horizontes:
            q05, q50, q95 = (float(v) for v in prediccion[i, h - 1])
            filas.append({'target': nombre, 'clase': o.clase, 'magnitud': o.magnitud, 'unit': o.unidad,
                          'emission_time': texto,
                          'forecast_time': (emision + paso * h).astimezone(conjunto.zona).isoformat(),
                          'horizon_steps': h, 'horizon_min': h * cadencia, 'cadence_min': cadencia,
                          'q05': q05, 'q50': q50, 'q95': q95, 'algorithm': algoritmo, 'marca': 'pronostico'})
    return filas


def pronosticar(contexto: Mapping, *, horizontes: tuple[int, ...], algoritmo: str) -> list[dict]:
    """Un pronóstico desde una emisión, con su contrato y sin ver nada posterior (046:RF-1, RF-4)."""
    conjunto: Conjunto = contexto['conjunto']
    nombre, e, modelo = contexto['objetivo'], int(contexto['emision']), contexto['modelo']
    horizontes = horizontes_validos(conjunto.cadencia_min, horizontes)
    pasos = int(contexto.get('contexto_pasos') or getattr(modelo, 'contexto_pasos', 1))
    lote = conjunto.lote([nombre], np.array([e]), contexto=pasos, horizonte=max(horizontes))
    prediccion = aplicar_ajuste(modelo.predecir(lote), contexto.get('ajuste'))
    return filas_pronostico(conjunto, nombre, np.array([e]), prediccion, horizontes, algoritmo)
