"""Destilación del modelo local de Ollama (maestro) al Transformer de órdenes (alumno).

Spec 027, RF-56 a RF-62. El usuario, el 2026-10-28: «no te olvides de verificar e implementar
la técnica y metodología de destilación para el entrenamiento de LLM». El Transformer se
entrenaba sobre todo con órdenes sintéticas (5 reales); las órdenes que el operador escribe y
no confirma no enseñaban nada. El maestro las interpreta k veces con temperatura y la
proporción de votos por tarea es su distribución blanda (autoconsistencia; destilación de
secuencia como en Hsieh et al., 2023, y Xu et al., 2024): el alumno aprende de ella con
α·CE + (1 − α)·T²·KL, y solo se usa si no acierta menos que sin destilar (RF-60).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from . import almacen
from .sinteticos import normalizar
from .tareas import TAREAS


@dataclass
class Destilacion:
    """Configuración de la destilación (RF-56 a RF-58, RF-62)."""

    k: int = 5
    """Interpretaciones del maestro por orden."""
    temperatura_maestro: float = 0.7
    acuerdo_min: float = 0.6
    """Fracción mínima de votos de la tarea más votada (RF-57)."""
    alfa: float = 0.5
    """Peso de la entropía cruzada con la etiqueta; 1 − α, el de la KL con el maestro."""
    T: float = 2.0
    """Temperatura del alumno en la KL (RF-58)."""
    maximo: int = 400
    """Órdenes sin etiqueta que se le piden al maestro como mucho."""


@dataclass
class EjemploBlando:
    """Una orden con la distribución del maestro y los datos que marcó en el texto."""

    texto: str
    distribucion: dict[str, float]
    datos: list[tuple[int, int, str]] = field(default_factory=list)
    acuerdo: float = 0.0

    @property
    def tarea(self) -> str:
        return max(self.distribucion, key=self.distribucion.get)


class Maestro(Protocol):
    modelo: str

    def interpretar(self, texto: str, *, temperatura: float = 0.0, semilla: int = 0) -> dict | None: ...


def sin_etiqueta(excluir: Iterable[str] = ()) -> list[str]:
    """Las órdenes del registro que el operador no confirmó ni corrigió (RF-59), sin las de
    ``excluir`` (la prueba fija), sin repetir y en el orden en que llegaron."""
    vistos = {normalizar(t) for t in excluir}
    vistos |= {normalizar(f.get('texto') or '') for f in almacen.leer('ejemplos')}
    out = []
    for f in almacen.leer('ordenes'):
        t = (f.get('texto') or '').strip()
        n = normalizar(t)
        if t and n not in vistos:
            vistos.add(n)
            out.append(t)
    return out


def _spans(texto: str, datos: dict[str, list[dict]]) -> list[tuple[int, int, str]]:
    """Los datos del maestro que aparecen tal cual en el texto, como trozos (sin solaparse)."""
    out: list[tuple[int, int, str]] = []
    bajo = texto.lower()
    for tipo, valores in (datos or {}).items():
        for v in valores or []:
            valor = str(v.get('valor') if isinstance(v, dict) else v).strip().lower()
            if not valor:
                continue
            m = re.search(re.escape(valor), bajo)
            if m and not any(a < m.end() and m.start() < b for a, b, _ in out):
                out.append((m.start(), m.end(), tipo))
    return sorted(out)


def etiquetar(textos: Sequence[str], maestro: Maestro, cfg: Destilacion | None = None
              ) -> dict[str, Any]:
    """Los votos del maestro por orden (RF-56) y el filtro por acuerdo (RF-57).

    Devuelve ``{'blandos', 'descartados', 'respondio'}``; ``respondio`` es falso si el maestro
    no dio ninguna respuesta (RF-61).
    """
    cfg = cfg or Destilacion()
    blandos, descartados, alguna = [], [], False
    for texto in list(textos)[:cfg.maximo]:
        votos: Counter = Counter()
        por_tarea: dict[str, dict] = {}
        for s in range(cfg.k):
            r = maestro.interpretar(texto, temperatura=cfg.temperatura_maestro, semilla=s)
            if r is None:
                continue
            alguna = True
            if r.get('tarea') in TAREAS:
                votos[r['tarea']] += 1
                por_tarea.setdefault(r['tarea'], r.get('datos') or {})
        total = sum(votos.values())
        if not total:
            descartados.append({'texto': texto, 'motivo': 'el maestro no dio una tarea'})
            continue
        tarea, n = votos.most_common(1)[0]
        acuerdo = n / cfg.k
        if acuerdo < cfg.acuerdo_min:
            descartados.append({'texto': texto, 'motivo': f'acuerdo {acuerdo:.2f} bajo {cfg.acuerdo_min}'})
            continue
        blandos.append(EjemploBlando(texto, {t: c / total for t, c in votos.items()},
                                     _spans(texto, por_tarea[tarea]), acuerdo))
    return {'blandos': blandos, 'descartados': descartados, 'respondio': alguna}


def registro(cfg: Destilacion, maestro: Maestro | None, resultado: dict[str, Any] | None) -> dict[str, Any]:
    """Lo que se guarda con el modelo (RF-62)."""
    return {**asdict(cfg), 'maestro': getattr(maestro, 'modelo', None),
            'etiquetadas': len((resultado or {}).get('blandos') or []),
            'descartadas': len((resultado or {}).get('descartados') or []),
            'respondio': bool((resultado or {}).get('respondio'))}
