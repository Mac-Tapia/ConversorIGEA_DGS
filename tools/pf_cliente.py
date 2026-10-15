#!/usr/bin/env python
"""Envía un guion de DIgSILENT al proceso que se queda abierto (spec 019, RF-7, RF-8).

Lo usa la web en lugar del guion (``JobContext.run_process``): la primera línea, el
Registro línea a línea, el fichero de cancelación y los límites siguen igual, porque el
cliente reescribe en su salida lo que el guion escribe en el servidor y devuelve su
código. Si no hay servidor, lo arranca; si el turno lo tiene otro proceso, espera
diciendo quién (RF-2); si el servidor muere a mitad, lo dice y devuelve 3 (RF-8).

    python tools/pf_cliente.py <guion> [argumentos del guion...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent / 'src') not in sys.path:
    sys.path.insert(0, str(HERE.parent / 'src'))

from igea_dgs import pf_arnes  # noqa: E402


def _lanzar_servidor(cola: Path) -> subprocess.Popen:
    banderas = 0
    if os.name == 'nt':
        banderas = (getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
                    | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    salida = open(cola / 'servidor.log', 'a', encoding='utf-8')  # noqa: SIM115 - del hijo
    return subprocess.Popen([sys.executable, str(HERE / pf_arnes.SERVIDOR)],
                            stdin=subprocess.DEVNULL, stdout=salida, stderr=subprocess.STDOUT,
                            env={**os.environ, 'PYTHONUNBUFFERED': '1'}, creationflags=banderas)


def asegurar_servidor(cola: Path, espera_s: float = pf_arnes.ESPERA_S, *,
                      lanzar=_lanzar_servidor, reloj=time.monotonic,
                      dormir=time.sleep) -> bool:
    """Un servidor vivo con el turno, arrancándolo si el turno está libre (RF-7, RF-2)."""
    limite = reloj() + espera_s
    proceso = None
    ultimo_aviso = None
    while True:
        if pf_arnes.servidor_vivo():
            return True
        dueno = pf_arnes.leer_turno()
        libre = dueno is None or not pf_arnes.pid_vivo(int(dueno.get('pid') or 0))
        if libre and proceso is None:
            proceso = lanzar(cola)
        elif proceso is not None and proceso.poll() is not None:
            print(f'ERROR: el proceso de DIgSILENT terminó al arrancar (código '
                  f'{proceso.returncode}); ver {cola / "servidor.log"}.', flush=True)
            return False
        elif not libre and (ultimo_aviso is None or reloj() - ultimo_aviso >= pf_arnes.AVISO_S):
            print(f"DIgSILENT ocupado por {dueno.get('guion')} (proceso {dueno.get('pid')}, "
                  f"desde {dueno.get('desde')}): esperando turno.", flush=True)
            ultimo_aviso = reloj()
        if reloj() >= limite:
            print(f'ERROR: DIgSILENT sigue ocupado tras {espera_s / 60:.0f} min (019:RF-2).',
                  flush=True)
            return False
        dormir(0.5)


def enviar(guion: str, argv: list[str], cola: Path, *, dormir=time.sleep) -> int:
    """Deja la orden, reescribe su salida según llega y devuelve su código."""
    ident = uuid.uuid4().hex[:12]
    tmp = cola / f'{ident}.tmp'
    tmp.write_text(json.dumps({'id': ident, 'guion': guion, 'argv': argv,
                               'cliente': os.getpid()}), encoding='utf-8')
    tmp.replace(cola / f'{ident}.orden.json')
    log, fin = cola / f'{ident}.log', cola / f'{ident}.fin.json'
    leido = 0
    while True:
        terminado = fin.exists()
        if log.exists():
            with open(log, encoding='utf-8', errors='replace') as f:
                f.seek(leido)
                nuevo = f.read()
                leido = f.tell()
            if nuevo:
                sys.stdout.write(nuevo)
                sys.stdout.flush()
        if terminado:
            codigo = int(json.loads(fin.read_text(encoding='utf-8')).get('codigo') or 0)
            for f in (log, fin):
                f.unlink(missing_ok=True)
            return codigo
        if not pf_arnes.servidor_vivo():
            print('ERROR: el proceso de DIgSILENT terminó sin acabar la orden (019:RF-8).',
                  flush=True)
            return 3
        dormir(0.2)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print('usage: pf_cliente.py <guion> [argumentos del guion...]')
        print(__doc__)
        return 0
    guion, resto = Path(argv[0]).name, argv[1:]
    if guion not in pf_arnes.GUIONES_SERVIBLES:
        print(f'ERROR: el proceso de DIgSILENT no atiende {guion}.')
        return 2
    cola = pf_arnes.ruta_cola()
    cola.mkdir(parents=True, exist_ok=True)
    if not asegurar_servidor(cola):
        return 3
    return enviar(guion, resto, cola)


if __name__ == '__main__':
    raise SystemExit(main())
