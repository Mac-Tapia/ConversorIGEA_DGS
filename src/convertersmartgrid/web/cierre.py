"""Por qué se cerró la web (081:RF-42, RF-43).

El 2026-11-03 la web cayó a mitad de la noche y nadie pudo decir por qué: cerrarla tiene al menos
tres caminos (el lanzador de otra versión, ``taskkill`` a un servidor que no responde, la ventana) y
ninguno dejaba rastro en el servidor. Cada arranque y cada cierre van a un registro; un arranque sin su
cierre, con el proceso ya muerto, es una caída de la que el operador se entera al abrir la siguiente.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ..asistente import almacen
from ..pf_arnes import dueno_vivo, inicio_proceso

REGISTRO = 'cierres'
ARRANQUE, CIERRE = 'arranque', 'cierre'
#: Basta con mirar lo reciente: una web abierta anota muy poco.
_FILAS = 200


def _sin_cierre(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    abiertos: dict[Any, dict[str, Any]] = {}
    for fila in filas:
        if fila.get('evento') == ARRANQUE:
            abiertos[fila.get('pid')] = fila
        elif fila.get('evento') == CIERRE:
            abiertos.pop(fila.get('pid'), None)
    return list(abiertos.values())


def anotar_arranque(huella: str | None = None, *,
                    vivo: Callable[[Any], bool] = dueno_vivo) -> list[dict[str, Any]]:
    """Anota el arranque y avisa de cada web anterior sin cierre cuyo proceso ya no vive (RF-43).

    Otra web abierta desde otra carpeta (081:RF-44) sigue viva: no es una caída. Cada caída se cierra
    en el registro con su motivo, para no avisarla dos veces.
    """
    avisos = []
    for fila in _sin_cierre(almacen.leer(REGISTRO, _FILAS)):
        if vivo(fila):
            continue
        aviso = {'clave': f"caida:{fila.get('fecha')}", 'nivel': 'error',
                 'texto': f"La web anterior (proceso {fila.get('pid')}, abierta el {fila.get('fecha')}) cayó sin "
                          'registrar su cierre: motivo desconocido (081:RF-43).'}
        almacen.anotar('avisos', aviso)
        anotar_cierre('caída sin motivo conocido', quien='la web siguiente', pid=fila.get('pid'))
        avisos.append(aviso)
    almacen.anotar(REGISTRO, {'evento': ARRANQUE, 'pid': os.getpid(), 'inicio': inicio_proceso(os.getpid()),
                              'huella': huella})
    return avisos


def anotar_cierre(motivo: str, *, quien: str = '', pid: int | None = None) -> dict[str, Any]:
    """Un cierre con su motivo y quién lo pidió (RF-42); ``pid`` es el del servidor que se cierra."""
    return almacen.anotar(REGISTRO, {'evento': CIERRE, 'motivo': motivo, 'quien': quien or f'proceso {os.getpid()}',
                                     'pid': os.getpid() if pid is None else pid})
