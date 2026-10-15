"""Arranca la interfaz web: ``python -m igea_dgs.web`` o ``igea-dgs-web``.

Por defecto escucha solo en 127.0.0.1, que es lo que permite indicar rutas del disco
local en lugar de subir los ficheros. Con ``--host 0.0.0.0`` se expone en la red y
esas rutas se desactivan siempre, aunque ``IGEA_WEB_SERVER_PATHS`` valga ``1``.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser


def puerto_ocupado(host: str, port: int) -> bool:
    """Si ya escucha algo en ``host:port``: el servidor nuevo no podría arrancar."""
    import socket

    destino = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((destino, port)) == 0


def _salida(cmd: list[str]) -> str:
    import subprocess

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return ''
    return r.stdout or ''


def quien_escucha(port: int) -> tuple[int, str] | None:
    """PID y línea de órdenes de quien escucha en ``port``, o None si no se averigua.

    2026-10-14: un servidor arrancado con ``--no-browser`` por una sesión de prueba se
    quedó escuchando sin ventana; el acceso directo decía «cierre la otra ventana» y no
    había ninguna que cerrar. Sin el PID no había forma de encontrarlo desde la consola.
    Es solo para el aviso: si falla cualquier paso, se avisa sin él.
    """
    pid = None
    if os.name == 'nt':
        for linea in _salida(['netstat', '-ano', '-p', 'TCP']).splitlines():
            campos = linea.split()
            if (len(campos) >= 5 and campos[1].endswith(f':{port}')
                    and campos[3].upper() in ('LISTENING', 'ESCUCHANDO') and campos[4].isdigit()):
                pid = int(campos[4])
                break
    else:
        primera = _salida(['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t']).split()
        pid = int(primera[0]) if primera and primera[0].isdigit() else None
    if pid is None:
        return None
    if os.name == 'nt':
        orden = _salida(['powershell', '-NoProfile', '-Command',
                         f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'])
    else:
        orden = _salida(['ps', '-o', 'args=', '-p', str(pid)])
    return pid, orden.strip()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog='igea-dgs-web', description=__doc__)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--no-browser', action='store_true', help='No abrir el navegador')
    p.add_argument('--reload', action='store_true', help='Recarga en caliente (desarrollo)')
    args = p.parse_args(argv)

    # En Windows, con la salida redirigida (servicio, .bat > log), la consola es cp1252
    # y cualquier carácter fuera de ella tumbaba el arranque antes de servir nada.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass

    try:
        import uvicorn
    except ImportError:
        print('Falta la parte web. Instale:  python -m pip install -r requirements.txt',
              file=sys.stderr)
        return 1

    # La API decide las rutas locales por la interfaz de escucha (create_app); con
    # factory=True no recibe argumentos, así que va por el entorno, que hereda también
    # el proceso de recarga.
    os.environ['IGEA_WEB_HOST'] = args.host

    from .app import frontend_dist

    url = f'http://{"127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host}:{args.port}/'
    if puerto_ocupado(args.host, args.port):
        # 2026-10-14: con un servidor de la mañana aún abierto, el acceso directo abría el
        # navegador en él —sin los cambios del día— y el nuevo moría sin bind; la ventana
        # solo decía «si faltan librerías».
        print(f'Ya hay un Conversor u otro programa escuchando en {url}. Cierre esa ventana '
              '(Ctrl+C) y vuelva a abrir el acceso directo para usar esta versión.',
              file=sys.stderr)
        ocupante = quien_escucha(args.port)
        if ocupante:
            pid, orden = ocupante
            cerrar = f'taskkill /PID {pid} /F' if os.name == 'nt' else f'kill {pid}'
            print(f'  Proceso {pid}: {orden or "(línea de órdenes no disponible)"}\n'
                  f'  Si no ve su ventana (p. ej. arrancado con --no-browser), ciérrelo con:  '
                  f'{cerrar}', file=sys.stderr)
        return 2
    if not (frontend_dist() / 'index.html').is_file():
        print('AVISO: no está compilado el front (frontend/dist). Solo responderá la API.\n'
              '       Compílelo con:  cd frontend && npm install && npm run build',
              file=sys.stderr)
    elif not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    print(f'Conversor IGEA -> DGS en {url}  (Ctrl+C para salir)')
    uvicorn.run('igea_dgs.web.app:create_app', factory=True, host=args.host, port=args.port,
                reload=args.reload, log_level='info')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
