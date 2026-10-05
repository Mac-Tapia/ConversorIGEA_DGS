"""CLI de la interfaz web: `python -m vnr_etl web`."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser

LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='vnr_etl web')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8776)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    token = os.environ.get('VNR_WEB_TOKEN', '').strip() or None
    if args.host not in LOOPBACK_HOSTS and token is None:
        raise SystemExit(
            'Exposición web bloqueada: defina VNR_WEB_TOKEN para escuchar fuera de loopback.'
        )

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SystemExit('La web necesita «uvicorn» (ver vnr_requirements.txt).') from exc

    if not args.no_browser:
        browser_host = args.host if args.host in LOOPBACK_HOSTS else '127.0.0.1'
        threading.Timer(1.0, lambda: webbrowser.open(f'http://{browser_host}:{args.port}/')).start()
    from .app import create_app

    uvicorn.run(create_app(auth_token=token), host=args.host, port=args.port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
