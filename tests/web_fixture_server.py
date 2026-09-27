"""Servidor aislado para las pruebas de equivalencia de la interfaz web.

Usa la aplicacion FastAPI real y un export CYMDIST sintetico. La unica ruta auxiliar
de trabajo introduce una espera controlada para poder observar la barra asincrona;
no sustituye rutas ni servicios productivos.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

import uvicorn  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from igea_dgs.web.app import create_app  # noqa: E402
from synthetic_export import ExportSpec, write_export  # noqa: E402


def build_app():
    temp = tempfile.TemporaryDirectory(prefix='igea-dgs-e2e-')
    root = Path(temp.name)
    red, loads, equipment = write_export(
        ExportSpec(feeders=3, naming='net', layout='completo'), root / 'fixture',
    )
    app = create_app(root / 'workspaces')
    app.state.e2e_temp = temp

    @app.get('/__e2e__/fixture', include_in_schema=False)
    def fixture() -> dict:
        return {'files': {
            'red': str(red),
            'loads': str(loads),
            'equipment': str(equipment),
        }}

    @app.post('/__e2e__/workspaces/{wid}/slow-job', include_in_schema=False)
    def slow_job(wid: str) -> dict:
        if app.state.store.get(wid) is None:
            raise HTTPException(404, 'Espacio E2E no encontrado.')

        def run(ctx):
            ctx.log('Trabajo de prueba E2E iniciado')
            ctx.progress(1, 2, 'comprobando barra')
            time.sleep(2.0)
            ctx.progress(2, 2, 'terminado')
            return {'ok': True}

        return app.state.jobs.submit(
            wid, 'e2e', 'Trabajo de prueba E2E', run, lane='engine',
        ).public()

    # create_app registra al final el fallback de la SPA (/{full_path:path}). Las
    # rutas auxiliares se declaran despues deliberadamente, asi que se adelantan al
    # fallback solo en este servidor aislado.
    fallback_index = next(
        index for index, route in enumerate(app.router.routes)
        if getattr(route, 'path', None) == '/{full_path:path}'
    )
    auxiliary = [
        route for route in app.router.routes
        if str(getattr(route, 'path', '')).startswith('/__e2e__/')
    ]
    for route in auxiliary:
        app.router.routes.remove(route)
        app.router.routes.insert(fallback_index, route)
        fallback_index += 1

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8876)
    args = parser.parse_args()
    uvicorn.run(build_app(), host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
