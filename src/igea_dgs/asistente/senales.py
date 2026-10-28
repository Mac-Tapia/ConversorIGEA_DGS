"""Recompensas, penalizaciones y memoria de reflexiones del asistente (spec 027, T15 y T16).

Cada orden deja su señal (RF-35): confirmada, +1; corregida, −1 para la interpretación del
modelo y la corregida como ejemplo positivo; rechazada, −1; ejecución fallida, −1 para la
acción, con su error. Cada corrección forma un par de preferencia, rechazada frente a
corregida, para un ajuste DPO (Rafailov et al., 2023) dentro de RF-21 (RF-36). Un fallo o una
corrección deja una nota que vuelve como contexto cuando llega una orden parecida, sin tocar
pesos (Reflexion, Shinn et al., 2023; RF-37), y Ollama recibe además las k órdenes confirmadas
más parecidas como ejemplos (RF-39).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import almacen
from .sinteticos import normalizar

#: Valor de cada señal (RF-35).
VALOR = {'confirmada': 1, 'corregida': -1, 'rechazada': -1, 'fallida': -1}


def anotar(senal: str, *, plan: str, texto: str, tarea: str | None, datos: Mapping[str, Any] | None = None,
           modelo: str | None = None, error: str | None = None) -> dict[str, Any]:
    """La señal de una orden (RF-35)."""
    if senal not in VALOR:
        raise ValueError(f'señal desconocida: {senal}')
    return almacen.anotar('senales', {'senal': senal, 'valor': VALOR[senal], 'plan': plan, 'texto': texto,
                                      'tarea': tarea, 'datos': dict(datos or {}), 'modelo': modelo,
                                      'error': error})


def par_de_preferencia(texto: str, rechazada: Mapping[str, Any], elegida: Mapping[str, Any]) -> dict[str, Any]:
    """Un par «rechazada frente a corregida» para DPO (RF-36)."""
    return almacen.anotar('preferencias', {'texto': texto, 'rechazada': dict(rechazada), 'elegida': dict(elegida)})


def reflexion(texto: str, tarea: str | None, causa: str, correccion: str) -> dict[str, Any]:
    """Una nota con la causa y la corrección, para la próxima orden parecida (RF-37)."""
    return almacen.anotar('reflexiones', {'texto': texto, 'tarea': tarea, 'causa': causa, 'correccion': correccion})


def _trigramas(texto: str) -> set[str]:
    t = f'  {normalizar(texto)}  '
    return {t[i:i + 3] for i in range(len(t) - 2)}


def parecido(a: str, b: str) -> float:
    """Jaccard de trigramas de caracteres: robusto a erratas, sin modelo."""
    x, y = _trigramas(a), _trigramas(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def _mas_parecidas(texto: str, filas: list[dict], k: int, minimo: float) -> list[dict]:
    puntuadas = sorted(((parecido(texto, f.get('texto') or ''), i, f) for i, f in enumerate(filas)),
                       key=lambda x: (-x[0], -x[1]))
    return [f for p, _i, f in puntuadas[:k] if p >= minimo]


def contexto_para(texto: str, *, k: int = 5, minimo: float = 0.3) -> list[str]:
    """Lo que se le da a Ollama con la orden: las k confirmadas más parecidas (RF-39) y las notas
    de fallos o correcciones de órdenes parecidas (RF-37)."""
    out = []
    for f in _mas_parecidas(texto, [e for e in almacen.leer('ejemplos') if e.get('origen') == 'confirmado'],
                            k, minimo):
        out.append(f"Ejemplo confirmado: «{f['texto']}» → tarea {f['tarea']}")
    for f in _mas_parecidas(texto, almacen.leer('reflexiones'), 3, minimo):
        out.append(f"Nota de una orden parecida («{f['texto']}»): {f['causa']}; {f['correccion']}")
    return out


def resumen() -> dict[str, dict[str, int]]:
    """Recompensas y penalizaciones acumuladas por tarea (RF-35)."""
    out: dict[str, dict[str, int]] = {}
    for f in almacen.leer('senales'):
        d = out.setdefault(f.get('tarea') or '—', {'recompensas': 0, 'penalizaciones': 0, **dict.fromkeys(VALOR, 0)})
        d[f['senal']] += 1
        d['recompensas' if f['valor'] > 0 else 'penalizaciones'] += 1
    return out
