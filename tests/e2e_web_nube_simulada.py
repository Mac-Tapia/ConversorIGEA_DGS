"""La web real con la nube simulada, para el recorrido e2e del selector único (spec 109, T19; 109:RF-21 a RF-24).

No es una prueba (pytest no la recoge): la arranca ``frontend/test/e2e/playwright.config.mjs`` como segundo servidor.
Es la web de siempre (``python -m convertersmartgrid.web``), con dos cambios solo en este proceso:

- ``Cuentas`` usa el proveedor simulado de ``tests/nube_simulada.py`` (Google Drive y OneDrive en memoria) y un
  ``nube.json`` de prueba en el temporal del recorrido: nada sale a la red y no hace falta registrar ninguna aplicación.
- Dos rutas de apoyo del recorrido, ``POST /__sim/crear`` (un fichero en la nube simulada) y ``POST /__sim/autorizar``
  (lo que haría el operador en la página del proveedor al conectar la cuenta).

Uso: ``python tests/e2e_web_nube_simulada.py --host 127.0.0.1 --port 8800 --no-browser``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / 'tests'), str(RAIZ / 'src')]

from nube_simulada import CONFIG_PRUEBA, NubeSimulada  # noqa: E402

from convertersmartgrid.adaptadores.nube import cuentas as modulo_cuentas  # noqa: E402
from convertersmartgrid.web import app as modulo_app  # noqa: E402


def _puerto(argv: list[str]) -> str:
    return argv[argv.index('--port') + 1] if '--port' in argv else '8765'


def preparar(argv: list[str]) -> NubeSimulada:
    sim = NubeSimulada()
    carpeta = Path(os.environ.get('CSG_E2E_NUBE_DIR') or Path(os.environ.get('LOCALAPPDATA', '.')) / 'nube_simulada')
    carpeta.mkdir(parents=True, exist_ok=True)
    retorno = f'http://127.0.0.1:{_puerto(argv)}/nube/retorno'
    ruta_config = carpeta / 'nube.json'
    ruta_config.write_text(json.dumps({p: {**c, 'uri_retorno': retorno} for p, c in CONFIG_PRUEBA.items()}),
                           encoding='utf-8')

    original = modulo_cuentas.Cuentas.__init__

    def iniciar(self, *, config=None, cofre=None, adaptador=None, dormir=None):
        original(self, config=config or ruta_config, cofre=cofre or carpeta / 'cofre',
                 adaptador=adaptador or sim, dormir=dormir or (lambda _s: None))

    modulo_cuentas.Cuentas.__init__ = iniciar
    crear_app = modulo_app.create_app

    def create_app(*args, **kwargs):
        app = crear_app(*args, **kwargs)

        async def sim_crear(cuerpo: dict) -> dict:
            return {'id': sim.crear(cuerpo['proveedor'], cuerpo['nombre'], cuerpo.get('contenido', '').encode('utf-8'))}

        async def sim_autorizar(cuerpo: dict) -> dict:
            return sim.autorizar(cuerpo['url'], cuerpo.get('cuenta', 'operador@ejemplo.org'))

        antes = len(app.router.routes)
        app.add_api_route('/__sim/crear', sim_crear, methods=['POST'])
        app.add_api_route('/__sim/autorizar', sim_autorizar, methods=['POST'])
        # Delante de la ruta comodín de la SPA, que si no las taparía.
        nuevas = app.router.routes[antes:]
        del app.router.routes[antes:]
        app.router.routes[:0] = nuevas
        return app

    modulo_app.create_app = create_app
    return sim


if __name__ == '__main__':
    preparar(sys.argv[1:])
    from convertersmartgrid.web.__main__ import main

    sys.argv = [sys.argv[0], *sys.argv[1:]]
    raise SystemExit(main())
