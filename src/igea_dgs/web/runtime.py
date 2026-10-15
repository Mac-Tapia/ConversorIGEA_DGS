"""Comprobación mínima del entorno que usa el lanzador web de Windows."""
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

REQUIRED_MODULES = (
    'igea_dgs',
    'pyproj',
    'fastapi',
    'uvicorn',
    'multipart',
    # Tercera fuente: VNR-GIS y su normalización GIS/topológica.
    'vnr_etl',
    'requests',
    'shapely',
    'networkx',
    'yaml',
    'geopandas',
)


def missing_dependencies(
    importer: Callable[[str], object] = importlib.import_module,
) -> tuple[str, ...]:
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importer(name)
        except (ImportError, OSError):
            missing.append(name)
    return tuple(missing)


# Lo que entra en la compilación del front: si algo de esto es más reciente que
# frontend/dist, la interfaz servida no es la del código.
FUENTES_DEL_FRONT = ('src', 'index.html', 'package.json', 'package-lock.json',
                     'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json')


def front_desactualizado(frontend: Path) -> str:
    """Por qué hay que recompilar el front, o cadena vacía si ``dist`` está al día.

    El lanzador solo compilaba si faltaba ``dist``: tras un cambio del front, el acceso
    directo seguía sirviendo la versión anterior sin avisar (spec 001, RF-27).
    """
    compilado = frontend / 'dist' / 'index.html'
    if not compilado.is_file():
        return 'no está compilado'
    referencia = compilado.stat().st_mtime
    for nombre in FUENTES_DEL_FRONT:
        ruta = frontend / nombre
        ficheros = ruta.rglob('*') if ruta.is_dir() else [ruta]
        for fichero in ficheros:
            if fichero.is_file() and fichero.stat().st_mtime > referencia:
                return f'{fichero.relative_to(frontend).as_posix()} es más reciente que la compilación'
    return ''


def huella_del_codigo(dist: Path | None = None) -> str:
    """Huella del código Python y del front compilado, para saber si un servidor es este.

    2026-10-15: con un servidor de otra versión en el puerto, el acceso directo no sabía si
    reutilizarlo o reemplazarlo. El servidor la calcula al arrancar y la publica en
    ``/api/health``; el lanzador la calcula del disco y las compara. Es fecha y tamaño de
    cada fichero, no su contenido: un par de cientos de ``stat``, sin leer nada.
    """
    import hashlib

    src = Path(__file__).resolve().parents[2]
    h = hashlib.sha1()
    for paquete in ('igea_dgs', 'vnr_etl'):
        for f in sorted((src / paquete).rglob('*.py')):
            st = f.stat()
            h.update(f'{f.relative_to(src).as_posix()}:{st.st_mtime_ns}:{st.st_size};'.encode())
    if dist is not None and (dist / 'index.html').is_file():
        st = (dist / 'index.html').stat()
        h.update(f'dist:{st.st_mtime_ns}:{st.st_size}'.encode())
    return h.hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--front']:
        from ..powerfactory_env import project_root

        motivo = front_desactualizado(project_root() / 'frontend')
        if motivo:
            print(f'Hay que compilar la interfaz web: {motivo}.')
            return 1
        print('La interfaz web compilada está al día.')
        return 0
    missing = missing_dependencies()
    if missing:
        print('Dependencias faltantes: ' + ', '.join(missing))
        return 1
    print('Entorno web listo: TXT, MDB y VNR-GIS.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
