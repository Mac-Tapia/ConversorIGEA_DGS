"""Comprobación mínima del entorno que usa el lanzador web de Windows."""
from __future__ import annotations

import importlib
import json
import re
import sys
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_MODULES = (
    'convertersmartgrid',
    'pyproj',
    'fastapi',
    'uvicorn',
    'multipart',
    # Sin psutil jobs.py no puede vigilar el límite RAM de los libros (036:RF-1).
    'psutil',
    # Tercera fuente: VNR-GIS y su normalización GIS/topológica.
    'vnr_etl',
    'requests',
    'shapely',
    'networkx',
    'yaml',
    'geopandas',
    'pandas',
    'openpyxl',
    'python_calamine',
    'pypdf',
    'docx',
    'PIL',
    'pandapower',
    'pydantic',
    *(('pyodbc',) if sys.platform == 'win32' else ()),
)

MODULOS_POR_CAPACIDAD = {
    'web': ('convertersmartgrid', 'fastapi', 'uvicorn', 'multipart', 'psutil', 'pydantic'),
    'txt': ('convertersmartgrid',),
    'geografia': ('pyproj',),
    'xlsx': ('pandas', 'openpyxl', 'python_calamine'),
    'pdf': ('pypdf',),
    'informes': ('docx', 'PIL'),
    'oraculo': ('pandapower',),
    'mdb': ('pyodbc',),
    'vnr_gis': ('vnr_etl', 'requests', 'shapely', 'networkx', 'yaml', 'geopandas', 'pyproj'),
    'vnr_sqlserver': ('vnr_etl', 'pyodbc'),
}
DRIVERS_POR_CAPACIDAD = {
    'mdb': 'Microsoft Access Driver (*.mdb, *.accdb)',
    # El conector SQL actual usa expresamente la versión 18, no cualquier SQL Server.
    'vnr_sqlserver': 'ODBC Driver 18 for SQL Server',
}


def missing_dependencies(
    importer: Callable[[str], object] = importlib.import_module,
) -> tuple[str, ...]:
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importer(name)
        except Exception:  # Una distribución instalada puede fallar al cargar sus DLL.
            missing.append(name)
    return tuple(missing)


def diagnostico_capacidades(
    importer: Callable[[str], object] = importlib.import_module,
    *, version: tuple[int, ...] | None = None,
    drivers: Callable[[], object] | None = None,
) -> dict:
    """Separa imports reales, compatibilidad Python y drivers sin conectar a bases."""
    version = tuple(sys.version_info[:2] if version is None else version[:2])
    errores = {}
    modulos = {}
    for nombre in dict.fromkeys(m for grupo in MODULOS_POR_CAPACIDAD.values() for m in grupo):
        try:
            modulos[nombre] = importer(nombre)
        except Exception as exc:
            errores[nombre] = f'{type(exc).__name__}: {exc}'
    error_drivers = ''
    try:
        lector = drivers if drivers is not None else getattr(modulos.get('pyodbc'), 'drivers', None)
        instalados = tuple(lector()) if lector else ()
    except Exception as exc:
        instalados = ()
        error_drivers = f'{type(exc).__name__}: {exc}'
    capacidades = {}
    for capacidad, requeridos in MODULOS_POR_CAPACIDAD.items():
        faltantes = tuple(m for m in requeridos if m in errores)
        driver = DRIVERS_POR_CAPACIDAD.get(capacidad)
        drivers_faltantes = (driver,) if driver and driver not in instalados else ()
        capacidades[capacidad] = {
            'disponible': version == (3, 12) and not faltantes and not drivers_faltantes,
            'modulos_faltantes': faltantes, 'drivers_faltantes': drivers_faltantes,
        }
    return {
        'python': '.'.join(map(str, version)), 'python_valido': version == (3, 12),
        'listo': version == (3, 12) and not any(m in errores for m in REQUIRED_MODULES),
        'capacidades': capacidades, 'errores_importacion': errores,
        'drivers_odbc': instalados, 'error_drivers': error_drivers,
    }


# Lo que entra en la compilación del front: si algo de esto es más reciente que
# frontend/dist, la interfaz servida no es la del código.
FUENTES_DEL_FRONT = ('src', 'scripts', 'index.html', 'package.json', 'package-lock.json',
                     'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json')


class _RecursosHTML(HTMLParser):
    """Recoge recursos descargados al cargar la página, sin tratar enlaces como archivos."""

    def __init__(self):
        super().__init__()
        self.recursos: list[str] = []
        self._etiqueta = ''

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag in ('script', 'style'):
            self._etiqueta = tag
        if tag == 'base':
            # Vite se publica en la raíz; otra base invalidaría esta comprobación local.
            if atributos.get('href', '/') != '/':
                self.recursos.append('../base-no-admitida')
        for atributo in ('src', 'poster', *(('data',) if tag == 'object' else ())):
            if atributos.get(atributo):
                self.recursos.append(atributos[atributo])
        if tag in ('link', 'use', 'image') and atributos.get('href'):
            self.recursos.append(atributos['href'])
        if atributos.get('style'):
            self.recursos.extend(_referencias_css(atributos['style']))
        if atributos.get('srcset') and not atributos['srcset'].startswith('data:'):
            self.recursos.extend(parte.strip().split()[0] for parte in atributos['srcset'].split(',') if parte.strip())

    def handle_endtag(self, tag):
        if self._etiqueta == tag:
            self._etiqueta = ''

    def handle_data(self, data):
        if self._etiqueta == 'style':
            self.recursos.extend(_referencias_css(data))
        elif self._etiqueta == 'script':
            self.recursos.extend(_referencias_js(data))


def _referencias_css(texto: str) -> list[str]:
    referencias = re.findall(r'url\(\s*[\'\"]?([^\s)\'\"]+)', texto)
    return referencias + re.findall(r'@import\s+[\'\"]([^\'\"]+)', texto)


def _referencias_js(texto: str) -> list[str]:
    referencias = re.findall(r'(?:\bfrom\s*|\bimport\s*\(?\s*|\bnew\s+URL\s*\(\s*)[\'\"]([^\'\"]+)', texto)
    if '__vite__mapDeps' in texto:
        # Vite retira el import CSS del chunk y lo conserva en su mapa de precarga.
        for grupo in re.findall(r'\b\w+\.f\s*=\s*\[([^\]]*)\]', texto):
            referencias.extend('/' + ruta.lstrip('/') for ruta in re.findall(r'[\'\"]([^\'\"]+)[\'\"]', grupo))
    return referencias


def integridad_del_front(dist: Path) -> str:
    """Rechaza recursos locales ausentes, rutas fuera de dist y dependencias transitivas."""
    dist = dist.resolve()
    pendientes = [dist / 'index.html']
    revisados: set[Path] = set()
    while pendientes:
        fichero = pendientes.pop().resolve()
        if not fichero.is_relative_to(dist):
            return 'recurso fuera de la compilación'
        if fichero in revisados:
            continue
        revisados.add(fichero)
        if not fichero.is_file():
            return f'falta el recurso {fichero.relative_to(dist).as_posix()}'
        if fichero.suffix not in ('.html', '.css', '.js', '.mjs'):
            continue
        try:
            texto = fichero.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            return f'no se puede leer {fichero.name}: {exc}'
        if fichero.suffix == '.html':
            parser = _RecursosHTML()
            parser.feed(texto)
            referencias = parser.recursos
        elif fichero.suffix == '.css':
            referencias = _referencias_css(texto)
        else:
            referencias = _referencias_js(texto)
        for referencia in referencias:
            try:
                url = urlsplit(referencia)
            except ValueError:
                return f'referencia de recurso inválida: {referencia}'
            if (url.scheme in ('http', 'https', 'data', 'blob')
                    or (url.netloc and not url.scheme) or not url.path):
                continue
            ruta = unquote(url.path)
            if url.scheme or '\\' in ruta or '\x00' in ruta:
                return f'recurso local no permitido: {referencia}'
            recurso = (dist / ruta.lstrip('/') if ruta.startswith('/') else fichero.parent / ruta).resolve()
            if not recurso.is_relative_to(dist):
                return f'recurso fuera de la compilación: {referencia}'
            pendientes.append(recurso)
    return ''


def front_desactualizado(frontend: Path) -> str:
    """Por qué hay que recompilar el front, o cadena vacía si ``dist`` está al día.

    El lanzador solo compilaba si faltaba ``dist``: tras un cambio del front, el acceso
    directo seguía sirviendo la versión anterior sin avisar (spec 001, RF-27).
    """
    compilado = frontend / 'dist' / 'index.html'
    if not compilado.is_file():
        return 'no está compilado'
    motivo = integridad_del_front(frontend / 'dist')
    if motivo:
        return motivo
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
    for paquete in ('convertersmartgrid', 'vnr_etl'):
        for f in sorted((src / paquete).rglob('*.py')):
            st = f.stat()
            h.update(f'{f.relative_to(src).as_posix()}:{st.st_mtime_ns}:{st.st_size};'.encode())
    if dist is not None and (dist / 'index.html').is_file():
        st = (dist / 'index.html').stat()
        h.update(f'dist:{st.st_mtime_ns}:{st.st_size}'.encode())
    return h.hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--validate-dist']:
        # El publicador Node ejecuta este archivo exacto con -I: ninguna dependencia
        # del servidor ni el paquete editable de otro checkout deben decidir el build.
        if len(argv) != 2:
            print('Uso: runtime.py --validate-dist DIRECTORIO')
            return 2
        motivo = integridad_del_front(Path(argv[1]))
        if motivo:
            print(f'Compilación web incompleta: {motivo}.')
            return 1
        print('La compilación web contiene todos sus recursos locales estáticos.')
        return 0

    from ..runtime_paths import configurar_entorno

    configurar_entorno()
    if argv[:1] in (['--front'], ['--front-integrity']):
        from ..powerfactory_env import project_root

        frontend = project_root() / 'frontend'
        motivo = (integridad_del_front(frontend / 'dist') if argv[0] == '--front-integrity'
                  else front_desactualizado(frontend))
        if motivo:
            print(f'Hay que compilar la interfaz web: {motivo}.')
            return 1
        print('La interfaz web compilada está al día.')
        return 0
    diagnostico = diagnostico_capacidades()
    if '--json' in argv:
        print(json.dumps(diagnostico, ensure_ascii=False))
    else:
        print(f"Python {diagnostico['python']}: " + ('compatible' if diagnostico['python_valido'] else 'se requiere 3.12'))
        for nombre, estado in diagnostico['capacidades'].items():
            detalle = [*estado['modulos_faltantes'], *estado['drivers_faltantes']]
            print(f"{nombre}: " + ('disponible' if estado['disponible'] else 'no disponible')
                  + (': ' + ', '.join(detalle) if detalle else ''))
        for nombre, error in diagnostico['errores_importacion'].items():
            print(f'{nombre}: {error}')
        if diagnostico['error_drivers']:
            print('No se pudieron enumerar los drivers ODBC: ' + diagnostico['error_drivers'])
    return (0 if diagnostico['listo'] else 1) if diagnostico['python_valido'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
