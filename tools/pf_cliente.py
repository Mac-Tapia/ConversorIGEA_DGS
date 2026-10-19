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


#: Lanzador intermedio: arranca el servidor, escribe su pid y sale. Así el servidor no
#: cuelga del cliente y ``taskkill /T`` sobre un cliente cortado no se lo lleva.
_INTERMEDIO = r'''
import os, subprocess, sys
banderas = 0
if os.name == 'nt':
    banderas = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
salida = open(sys.argv[2], 'a', encoding='utf-8')
p = subprocess.Popen([sys.executable, sys.argv[1]], stdin=subprocess.DEVNULL, stdout=salida,
                     stderr=subprocess.STDOUT, creationflags=banderas, close_fds=True,
                     env={**os.environ, 'PYTHONUNBUFFERED': '1'})
print(p.pid, flush=True)
'''


class _Servidor:
    """El servidor arrancado, seguido por su pid (no es hijo de este proceso)."""

    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None

    def poll(self):
        if pf_arnes.pid_vivo(self.pid):
            return None
        self.returncode = '?'
        return self.returncode


def _lanzar_servidor(cola: Path) -> _Servidor:
    """Arranca ``pf_servidor.py`` fuera del árbol del cliente (019:RF-20).

    Era hijo del primer cliente que lo arrancó: al cortar la web ese cliente
    (``taskkill /T``), caía también el servidor con la orden que atendía para otro.
    """
    r = subprocess.run([sys.executable, '-c', _INTERMEDIO, str(HERE / pf_arnes.SERVIDOR),
                        str(cola / 'servidor.log')], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        return _Servidor(int(r.stdout.split()[0]))
    except (IndexError, ValueError):
        raise OSError(f'no se pudo arrancar el proceso de DIgSILENT: {r.stderr.strip()}')


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
        # 019:RF-19: el que ya se despidió y cierra DIgSILENT no atiende; el servidor nuevo
        # espera en su turno a que acabe de cerrarse.
        libre = (dueno is None or not pf_arnes.dueno_vivo(dueno)
                 or (dueno.get('guion') == pf_arnes.SERVIDOR
                     and dueno.get('liberado') is not None))
        if libre and proceso is None:
            try:
                proceso = lanzar(cola)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f'ERROR: {exc}', flush=True)
                return False
        elif proceso is not None and proceso.poll() is not None:
            print(f'ERROR: el proceso de DIgSILENT terminó al arrancar (código '
                  f'{proceso.returncode}); ver {cola / "servidor.log"}.', flush=True)
            return False
        elif (dueno is not None and not libre
              and (ultimo_aviso is None or reloj() - ultimo_aviso >= pf_arnes.AVISO_S)):
            print(f"DIgSILENT ocupado por {dueno.get('guion')} (proceso {dueno.get('pid')}, "
                  f"desde {dueno.get('desde')}): esperando turno.", flush=True)
            ultimo_aviso = reloj()
        if reloj() >= limite:
            print(f'ERROR: DIgSILENT sigue ocupado tras {espera_s / 60:.0f} min (019:RF-2).',
                  flush=True)
            return False
        dormir(0.5)


def _servidor_caido(dormir) -> bool:
    """Sin servidor en dos lecturas seguidas: una sola puede caer en una reescritura."""
    if pf_arnes.servidor_vivo():
        return False
    dormir(0.5)
    return pf_arnes.servidor_vivo() is None


def _otra_en_curso(cola: Path, propia: Path) -> str | None:
    """El guion de la orden que el servidor atiende si no es la nuestra."""
    for en_curso in cola.glob('*.en_curso.json'):
        if en_curso.name != propia.name:
            try:
                return json.loads(en_curso.read_text(encoding='utf-8')).get('guion') or '?'
            except (OSError, ValueError):
                return '?'
    return None


def enviar(guion: str, argv: list[str], cola: Path, *, dormir=time.sleep,
           reloj=time.monotonic, asegurar=asegurar_servidor, ident: str | None = None) -> int:
    """Deja la orden, reescribe su salida según llega y devuelve su código.

    019:RF-20: el identificador lo da la web (``IGEA_PF_ORDEN``) para poder retirar o cortar
    solo esta orden. 019:RF-22: si el servidor se cerró con la orden aún en la cola (cerró
    por inactividad justo cuando se dejó), se arranca otro en vez de fallar; mientras
    espera detrás de la orden de otro, se dice, y la web no la toma por DIgSILENT colgado.
    """
    ident = ident or os.environ.get(pf_arnes.VARIABLE_ORDEN) or uuid.uuid4().hex[:12]
    tmp = cola / f'{ident}.tmp'
    tmp.write_text(json.dumps({'id': ident, 'guion': guion, 'argv': argv,
                               'cliente': os.getpid(),
                               'cliente_inicio': pf_arnes.inicio_proceso(os.getpid())}),
                   encoding='utf-8')
    orden = cola / f'{ident}.orden.json'
    en_curso = cola / f'{ident}.en_curso.json'
    tmp.replace(orden)
    log, fin = cola / f'{ident}.log', cola / f'{ident}.fin.json'
    leido = 0
    ultimo_aviso = None
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
            try:
                codigo = int(json.loads(fin.read_text(encoding='utf-8')).get('codigo') or 0)
            except (OSError, ValueError):
                dormir(0.2)             # el servidor aún lo escribe
                continue
            for f in (log, fin):
                f.unlink(missing_ok=True)
            return codigo
        if orden.exists():
            if _servidor_caido(dormir):
                if not asegurar(cola):
                    orden.unlink(missing_ok=True)
                    return 3
                continue
            otra = _otra_en_curso(cola, en_curso)
            if otra and (ultimo_aviso is None or reloj() - ultimo_aviso >= pf_arnes.AVISO_S):
                print(f'DIgSILENT atiende otra orden ({otra}): esta espera su turno en la '
                      'cola (019:RF-22).', flush=True)
                ultimo_aviso = reloj()
        elif not fin.exists() and _servidor_caido(dormir):
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
