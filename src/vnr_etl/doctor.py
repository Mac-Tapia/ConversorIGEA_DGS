"""Doctor de dependencias (sección E8 de VNR-GIS.md).

Informa qué adaptadores están disponibles en este intérprete y qué soporte
nativo (Poppler, ODBC, clientes de base de datos) falta. Un adaptador opcional
ausente solo desactiva ese adaptador, no el resto del ETL.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from dataclasses import dataclass, field

#: Mapa de dependencia Python → adaptador que desbloquea.
ADAPTER_DEPS: dict[str, str] = {
    'requests': 'arcgis / download',
    'shapely': 'gis (snapping/geometría)',
    'geopandas': 'archivos GIS (SHP/GeoPackage/GeoJSON)',
    'pyproj': 'reproyección CRS',
    'networkx': 'topología y validación de grafo',
    'pandas': 'lectura de catálogos y CSV',
    'psycopg2': 'PostgreSQL/PostGIS',
    'oracledb': 'Oracle / Oracle Spatial',
    'sqlalchemy': 'abstracción de bases de datos',
    'pyodbc': 'SQL Server / Access / ODBC',
    'opencv-python': 'recuperación opcional por PDF/OpenCV',
    'pdf2image': 'recuperación opcional por PDF (requiere Poppler)',
}

#: Pares módulo->nombre de instalación cuando difieren.
IMPORT_NAMES: dict[str, str] = {
    'opencv-python': 'cv2',
    'psycopg2': 'psycopg2',
}


@dataclass
class DoctorResult:
    python_version: str
    platform: str
    packages: dict[str, bool] = field(default_factory=dict)
    native: dict[str, bool] = field(default_factory=dict)
    web_ui: bool = False

    def available_adapters(self) -> dict[str, bool]:
        """Cada adaptador y si sus dependencias Python están presentes."""
        return {
            name: bool(all(self.packages.get(dep) for dep in deps))
            for name, deps in ADAPTER_REQUIREMENTS.items()
        }

    def report(self) -> str:
        lines = [
            f'Python: {self.python_version}',
            f'Plataforma: {self.platform}',
            '',
            'Dependencias Python:',
        ]
        for name in sorted(self.packages):
            marker = 'OK' if self.packages[name] else 'FALTA'
            lines.append(f'  [{marker:5}] {name:16} -> {ADAPTER_DEPS.get(name, "")}')
        lines.append('')
        lines.append('Soporte nativo:')
        for name in sorted(self.native):
            marker = 'OK' if self.native[name] else 'FALTA'
            lines.append(f'  [{marker:5}] {name}')
        lines.append('')
        lines.append(f'Web UI (FastAPI/uvicorn): {"OK" if self.web_ui else "FALTA"}')
        return '\n'.join(lines)


#: Dependencias que desbloquean cada adaptador lógico.
ADAPTER_REQUIREMENTS: dict[str, list[str]] = {
    'arcgis_rest': ['requests'],
    'download': ['requests'],
    'gis': ['shapely', 'pyproj'],
    'vector_files': ['geopandas', 'shapely', 'pyproj'],
    'postgis': ['psycopg2'],
    'oracle': ['oracledb'],
    'sqlserver_odbc': ['pyodbc'],
    'access': ['pyodbc'],
    'topology': ['networkx'],
    'pdf_recovery': ['opencv-python', 'pdf2image'],
}


def _native_status() -> dict[str, bool]:
    return {
        'poppler': shutil.which('pdftoppm') is not None,
        'python': sys.executable,
    } if False else {
        'poppler': shutil.which('pdftoppm') is not None,
    }


def run_doctor() -> DoctorResult:
    return doctor()


def doctor() -> DoctorResult:
    packages: dict[str, bool] = {}
    for dep in sorted(ADAPTER_DEPS):
        import_name = IMPORT_NAMES.get(dep, dep)
        packages[dep] = importlib.util.find_spec(import_name) is not None
    native = _native_status()
    web = all(
        importlib.util.find_spec(m) is not None
        for m in ('fastapi', 'uvicorn')
    )
    return DoctorResult(
        python_version=platform.python_version(),
        platform=platform.platform(),
        packages=packages,
        native=native,
        web_ui=web,
    )