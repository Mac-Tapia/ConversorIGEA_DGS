"""Suspensión del equipo durante un trabajo de la web (spec 096).

Pisco (2026-11-05): una recalibración de AL209 y PA217 tardaba más de media hora en DIgSILENT y el operador quería
suspender el equipo. Suspendido, todo se congela; al despertar la orden de DIgSILENT puede fallar (licencia de red,
conexión) y el trabajo quedaba fallido sin que nadie lo repitiera.
"""
from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator

#: ``SetThreadExecutionState``: mientras el hilo lo pida, Windows no suspende el equipo por inactividad (096:RF-1).
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def suspendido_s() -> float:
    """Segundos que el equipo estuvo suspendido o en hibernación desde que arrancó; fuera de Windows, 0.

    ``GetTickCount64`` sigue contando mientras el equipo duerme y ``QueryUnbiasedInterruptTime`` no: su diferencia es
    el tiempo suspendido. Un salto entre el reloj de pared y ``time.monotonic`` no sirve: en Windows ``monotonic`` es
    el mismo ``GetTickCount64``, y un cambio de hora daría una suspensión que no hubo.
    """
    if sys.platform != 'win32':
        return 0.0
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        con_sueno_ms = kernel32.GetTickCount64()
        sin_sueno = ctypes.c_ulonglong(0)
        if not kernel32.QueryUnbiasedInterruptTime(ctypes.byref(sin_sueno)):
            return 0.0
        return max(0.0, con_sueno_ms / 1000.0 - sin_sueno.value / 1e7)
    except (AttributeError, OSError):
        return 0.0


def _estado(banderas: int) -> None:
    if sys.platform != 'win32':
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(banderas))
    except (AttributeError, OSError):
        pass


@contextlib.contextmanager
def sin_suspender() -> Iterator[None]:
    """096:RF-1: mientras dura, Windows no suspende el equipo por inactividad; el estado es del hilo que lo llama."""
    _estado(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        _estado(ES_CONTINUOUS)
