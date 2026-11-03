"""046:RF-13 — series de contrato sorteadas para las pruebas de pronóstico; no son medición real."""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from convertersmartgrid.digital_twin.pronostico import Objetivo

CADENCIA = 15
PUNTOS_DIA = 96
SEMILLA = int(os.environ.get('CSG_SCALE_SEED') or random.SystemRandom().randrange(1, 10**6))


def sorteo() -> random.Random:
    return random.Random(SEMILLA)


def curva(dias: int, *, base: float, semilla: int, ruido: float = .06, inicio: datetime | None = None):
    """Forma diaria con un pico marcado y semanal, con ruido: un perfil medio la aprende y un ingenuo no."""
    rng = np.random.default_rng(semilla)
    inicio = inicio or datetime(2026, 1, 5)
    n = dias * PUNTOS_DIA
    t = np.arange(n)
    diaria = 1 + .35 * np.sin(2 * np.pi * (t % PUNTOS_DIA) / PUNTOS_DIA - 1.2) \
        + .9 * np.exp(-(((t % PUNTOS_DIA) - .75 * PUNTOS_DIA) / (.04 * PUNTOS_DIA)) ** 2)
    semanal = np.where((t // PUNTOS_DIA) % 7 >= 5, .75, 1.0)
    v = base * diaria * semanal * (1 + ruido * rng.standard_normal(n))
    return [(inicio + timedelta(minutes=CADENCIA * i), float(v[i])) for i in range(n)]


def objetivos(cuantos: int, dias: int, *, clase: str = 'cabecera', ruido: float = .06,
              semilla_ruido: int | None = None) -> list[Objetivo]:
    """``semilla_ruido`` fija solo el ruido: una puerta estadística puede no pasar con mala suerte, y
    las pruebas que afirman quién gana no deben depender de ella. El tamaño de la red sigue sorteado."""
    r = sorteo()
    base = SEMILLA if semilla_ruido is None else semilla_ruido
    return [Objetivo(clase=clase, ident=f'X{i}', magnitud='kW', unidad='kW',
                     curva=curva(dias, base=r.uniform(100, 5000), semilla=base + i, ruido=ruido))
            for i in range(cuantos)]


class PerfilMedio:
    """Candidato de contrato sin GPU: la media por instante de la semana, solo de entrenamiento.

    Prueba el circuito de competición, no a un modelo: por eso no vive en ``src/``.
    """

    requiere_gpu = False
    contexto_pasos = 1

    def __init__(self, algoritmo: str = 'perfil', **_cfg):
        self.algoritmo = algoritmo
        self.perfil: dict[str, dict[tuple, float]] = {}
        self.vistos_fin_entrenamiento: int | None = None

    def ajustar(self, conjunto, fin_entrenamiento: int, horizonte: int, semilla: int) -> dict:
        self.vistos_fin_entrenamiento = fin_entrenamiento
        self.horizonte = horizonte
        for nombre in conjunto.nombres:
            valores = conjunto.valores[nombre][:fin_entrenamiento]
            suma: dict[tuple, list[float]] = {}
            calendario = np.round(conjunto.calendario[:fin_entrenamiento], 3).tolist()
            for fila, v in zip(calendario, valores.tolist(), strict=True):
                if np.isfinite(v):
                    c = suma.setdefault(tuple(fila), [0.0, 0.0])
                    c[0] += float(v)
                    c[1] += 1.0
            self.perfil[nombre] = {k: s / n for k, (s, n) in suma.items()}
        return {'pasos': 1}

    def predecir(self, lote) -> np.ndarray:
        out = np.zeros((lote.n, lote.horizonte, 3))
        claves = np.round(lote.calendario_futuro, 3).tolist()
        for i, nombre in enumerate(lote.objetivos):
            perfil = self.perfil[nombre]
            out[i] = [[v, v, v] for v in (perfil.get(tuple(c), np.nan) for c in claves[i])]
        return out

    def guardar(self, carpeta: Path) -> None:
        carpeta.mkdir(parents=True, exist_ok=True)
        filas = {n: [[list(k), v] for k, v in p.items()] for n, p in self.perfil.items()}
        (carpeta / 'perfil.json').write_text(json.dumps(filas), encoding='utf-8')

    @classmethod
    def reabrir(cls, carpeta: Path, algoritmo: str = 'perfil') -> PerfilMedio:
        m = cls(algoritmo)
        filas = json.loads((carpeta / 'perfil.json').read_text(encoding='utf-8'))
        m.perfil = {n: {tuple(k): v for k, v in p} for n, p in filas.items()}
        return m
