"""Gemelo temporal: la demanda del mes, hora a hora o cada 15 minutos (spec 024, T12).

Una red recurrente (GRU) aprende la curva de cada cabecera y la reproduce un paso por
delante (RF-20, RF-37); comparada con lo medido, dice cuándo y en qué alimentador el
gemelo se aparta y cuánto aporta cada uno a la desviación (RF-21). Con la medida de la
barra de la SET, reparte lo que falta entre los alimentadores sin medidor por su potencia
instalada, descontando clientes fijos y pérdidas, con su intervalo y siempre marcado como
estimado (RF-22). El instante crítico es el de máxima coincidente: ahí se evalúan las
alternativas, no solo en la máxima de cada uno (RF-37).

Sin PyTorch, ``ModeloEstacional`` (el mismo instante del día anterior) cumple el contrato.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

#: Puntos por día con medidas cada 15 minutos.
PUNTOS_DIA = 96


@dataclass
class ModeloEstacional:
    """Predice cada punto con el mismo instante del día anterior."""

    periodo: int = PUNTOS_DIA
    nombre: str = 'estacional'

    def reproducir(self, serie: Sequence[float]) -> np.ndarray:
        s = np.asarray(serie, dtype=float)
        out = np.full_like(s, np.nan)
        out[self.periodo:] = s[:-self.periodo]
        return out


class GemeloGRU:
    """GRU que predice el punto siguiente a partir de la ventana anterior (RF-20, RF-37)."""

    nombre = 'gru'

    def __init__(self, ventana: int = PUNTOS_DIA, ocultas: int = 32, epocas: int = 40, semilla: int = 0):
        import torch

        self.torch = torch
        self.ventana, self.ocultas, self.epocas, self.semilla = ventana, ocultas, epocas, semilla
        self.escala = 1.0
        from .oraculo import dispositivo

        self.disp = dispositivo()          # solo en la GPU, como la PINN
        torch.manual_seed(semilla)
        nn = torch.nn

        class Red(nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = nn.GRU(2, ocultas, batch_first=True)
                self.salida = nn.Linear(ocultas, 1)

            def forward(self, x):
                h, _ = self.gru(x)
                return self.salida(h[:, -1, :]).squeeze(-1)

        self.red = Red().to(self.disp)

    def _entradas(self, s: np.ndarray, inicio: int) -> np.ndarray:
        """Ventana con el valor y la hora del día (seno), para que aprenda la forma diaria."""
        idx = np.arange(inicio, inicio + self.ventana)
        hora = np.sin(2 * np.pi * (idx % PUNTOS_DIA) / PUNTOS_DIA)
        return np.stack([s[inicio:inicio + self.ventana], hora], axis=1)

    def entrenar(self, serie: Sequence[float]) -> float:
        torch = self.torch
        s = np.asarray(serie, dtype=float)
        self.escala = float(np.max(np.abs(s))) or 1.0
        s = s / self.escala
        n = len(s) - self.ventana
        if n <= 0:
            raise ValueError(f'hacen falta más de {self.ventana} puntos para entrenar')
        x = torch.tensor(np.stack([self._entradas(s, i) for i in range(n)]), dtype=torch.float32, device=self.disp)
        y = torch.tensor(s[self.ventana:], dtype=torch.float32, device=self.disp)
        opt = torch.optim.Adam(self.red.parameters(), lr=1e-2)
        perdida = torch.tensor(0.0)
        for _ in range(self.epocas):
            for lote in torch.split(torch.randperm(n, device=self.disp), 256):
                perdida = ((self.red(x[lote]) - y[lote]) ** 2).mean()
                opt.zero_grad()
                perdida.backward()
                opt.step()
        return float(perdida.detach()) * self.escala ** 2

    def reproducir(self, serie: Sequence[float]) -> np.ndarray:
        torch = self.torch
        s = np.asarray(serie, dtype=float) / self.escala
        out = np.full(len(s), np.nan)
        n = len(s) - self.ventana
        if n <= 0:
            return out
        x = torch.tensor(np.stack([self._entradas(s, i) for i in range(n)]), dtype=torch.float32, device=self.disp)
        with torch.no_grad():
            out[self.ventana:] = self.red(x).cpu().numpy() * self.escala
        return out


def metricas(medida: Sequence[float], reproducida: Sequence[float]) -> dict[str, float]:
    """Error del gemelo frente a lo medido, donde hay las dos (RF-20)."""
    m, r = np.asarray(medida, dtype=float), np.asarray(reproducida, dtype=float)
    ok = ~np.isnan(r)
    if not ok.any():
        return {'mae_kw': float('nan'), 'mape_pct': float('nan'), 'puntos': 0}
    err = np.abs(m[ok] - r[ok])
    base = np.where(np.abs(m[ok]) > 1e-9, np.abs(m[ok]), np.nan)
    return {'mae_kw': float(err.mean()), 'mape_pct': float(np.nanmean(100 * err / base)),
            'puntos': int(ok.sum())}


def desviaciones(medidas: Mapping[str, Sequence[float]], reproducidas: Mapping[str, Sequence[float]],
                 instantes: Sequence[datetime], umbral_pct: float) -> list[dict[str, Any]]:
    """Instantes en que el total se aparta más del umbral, con el alimentador que más aporta
    y la contribución de cada uno (RF-21). Cada uno se confirma después en DIgSILENT."""
    nombres = sorted(medidas)
    m = np.array([np.asarray(medidas[a], dtype=float) for a in nombres])
    r = np.array([np.asarray(reproducidas[a], dtype=float) for a in nombres])
    res = np.where(np.isnan(r), 0.0, m - r)
    total_m = m.sum(axis=0)
    out = []
    for t in range(m.shape[1]):
        if np.isnan(r[:, t]).all() or abs(total_m[t]) < 1e-9:
            continue
        dev = abs(res[:, t].sum()) / abs(total_m[t]) * 100
        if dev > umbral_pct:
            aporte = np.abs(res[:, t])
            k = int(np.argmax(aporte))
            out.append({'instante': instantes[t].isoformat(), 'desviacion_pct': float(dev),
                        'alimentador': nombres[k],
                        'contribucion_pct': {a: float(100 * aporte[i] / aporte.sum()) for i, a in enumerate(nombres)},
                        'confirmar_en_pf': True})
    return out


def pseudo_medidas(barra: Sequence[float], medidas: Mapping[str, Sequence[float]],
                   kva: Mapping[str, float], *, fijas_kw: Mapping[str, float] | None = None,
                   perdidas_pct: float = 0.0, sigma_pct: float = 10.0) -> dict[str, dict[str, Any]]:
    """La demanda estimada de cada alimentador sin medidor (RF-22).

    Lo que mide la barra, menos lo medido, menos las pérdidas y los clientes fijos, se
    reparte por potencia instalada; cada estimado lleva su intervalo y nunca pierde la marca
    de estimado. Si lo que queda es negativo, el estimado es 0 y se dice.
    """
    b = np.asarray(barra, dtype=float)
    medido = sum((np.asarray(s, dtype=float) for s in medidas.values()), np.zeros_like(b))
    fijas = dict(fijas_kw or {})
    resto = b * (1 - perdidas_pct / 100) - medido - sum(fijas.values())
    negativos = int((resto < 0).sum())
    resto = np.maximum(resto, 0.0)
    total_kva = sum(kva.values()) or 1.0
    out = {}
    for a, s in sorted(kva.items()):
        serie = resto * s / total_kva + fijas.get(a, 0.0)
        out[a] = {'kw': serie.tolist(), 'inferior': (serie * (1 - sigma_pct / 100)).tolist(),
                  'superior': (serie * (1 + sigma_pct / 100)).tolist(), 'estimada': True,
                  'aviso': (f'{negativos} instante(s) en que lo medido supera a la barra: estimado 0'
                            if negativos else None)}
    return out


def instante_critico(curvas: Mapping[str, Sequence[float]], instantes: Sequence[datetime]) -> dict[str, Any]:
    """El instante de máxima coincidente del conjunto y lo de cada uno en él (RF-37)."""
    total = sum((np.asarray(c, dtype=float) for c in curvas.values()), np.zeros(len(instantes)))
    t = int(np.argmax(total))
    return {'instante': instantes[t].isoformat(), 'total_kw': float(total[t]),
            'por_alimentador': {a: float(np.asarray(c, dtype=float)[t]) for a, c in curvas.items()}}


def modelo_temporal(**kw):
    """La GRU si hay PyTorch; si no, el estacional (mismo contrato ``reproducir``)."""
    try:
        return GemeloGRU(**kw)
    except ImportError:
        return ModeloEstacional()
