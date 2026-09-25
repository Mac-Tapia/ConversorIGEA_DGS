"""Arranca la interfaz web: ``python -m igea_dgs.web`` o ``igea-dgs-web``.

Por defecto escucha solo en 127.0.0.1, que es lo que permite indicar rutas del disco
local en lugar de subir los ficheros. Con ``--host 0.0.0.0`` se expone en la red y
esas rutas se desactivan salvo que se pida lo contrario (``IGEA_WEB_SERVER_PATHS=1``).
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser


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

    if args.host not in ('127.0.0.1', 'localhost'):
        os.environ.setdefault('IGEA_WEB_SERVER_PATHS', '0')

    from .app import frontend_dist

    url = f'http://{"127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host}:{args.port}/'
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
