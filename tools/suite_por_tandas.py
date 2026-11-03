#!/usr/bin/env python
"""La suite nocturna por tandas, en un proceso separado de la web (081:RF-37 a RF-41).

Corría en un hilo del servidor: si la web caía, la suite moría con ella y su registro quedaba en
«empezada» sin resultado. Se separa en dos pasos porque ``taskkill /T`` sigue la cadena de padres:

    python tools/suite_por_tandas.py --separar   # lanza el proceso de abajo, lo registra y termina
    python tools/suite_por_tandas.py --correr    # las tandas, una tras otra; siempre deja resultado

Lo escribe en el registro ``suite`` (y cada tanda en ``suite_tandas``) del asistente.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO / 'src'))


def _flags_separado() -> int:
    # DETACHED_PROCESS: sin la consola de la web; NEW_PROCESS_GROUP: su Ctrl+C no llega aquí;
    # BREAKAWAY_FROM_JOB: el trabajo de Windows que cierra el árbol de la web no se lo lleva.
    return (getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            | getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0))


def separar(*, abrir=subprocess.Popen, inicio=None) -> int:
    """Lanza ``--correr`` separado y deja registrada la suite con su proceso (081:RF-37, RF-41)."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.vigilancia import EMPEZADA, ENTORNO_SUITE
    from convertersmartgrid.pf_arnes import inicio_proceso

    salida = almacen.raiz() / 'suite_salida.log'
    salida.parent.mkdir(parents=True, exist_ok=True)
    entorno = {**os.environ, **ENTORNO_SUITE}
    with open(salida, 'ab') as log:
        lanzar = dict(args=[sys.executable, str(Path(__file__).resolve()), '--correr'], cwd=str(_REPO), env=entorno,
                      stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True)
        try:
            proceso = abrir(**lanzar, creationflags=_flags_separado())
        except PermissionError:
            # Un trabajo de Windows que no deja salir de él; sin BREAKAWAY sigue fuera del árbol de la web.
            proceso = abrir(**lanzar, creationflags=_flags_separado() & ~getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0))
    almacen.anotar('suite', {'codigo': None, 'resumen': EMPEZADA, 'pid': proceso.pid,
                             'inicio': (inicio or inicio_proceso)(proceso.pid)})
    return 0


def correr() -> int:
    """Las tandas; una señal de cierre deja «interrumpida» (081:RF-40) en vez de un registro a medias."""
    from convertersmartgrid.asistente.vigilancia import correr_por_tandas

    def al_recibir(numero, _marco):
        raise KeyboardInterrupt(f'señal {numero}')

    for nombre in ('SIGTERM', 'SIGBREAK', 'SIGINT'):
        if hasattr(signal, nombre):
            signal.signal(getattr(signal, nombre), al_recibir)
    try:
        fila = correr_por_tandas(_REPO)
    except KeyboardInterrupt:
        return 3
    print(fila.get('resumen'), flush=True)
    return 0 if fila.get('codigo') == 0 else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument('--separar', action='store_true', help='Lanza --correr separado de este proceso y termina')
    modo.add_argument('--correr', action='store_true', help='Corre las tandas en este proceso')
    args = p.parse_args(argv)
    return separar() if args.separar else correr()


if __name__ == '__main__':
    raise SystemExit(main())
