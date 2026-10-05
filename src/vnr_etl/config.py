"""Configuración del ETL (secciones 7 y D17 de VNR-GIS.md).

Los valores por defecto no son la verdad: el CRS debe salir de los metadatos de
la fuente y las URLs/empresas/años son DATOS descubiertos en ejecución. Aquí solo
viven las reglas de validación, tolerancias y políticas de descubrimiento/descarga.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    'project': {'mode': 'audit', 'strict': True},
    'gis': {
        'source_crs': None,
        'working_crs': None,
        'snap_tolerance_m': 0.50,
        'equipment_snap_tolerance_m': 1.00,
    },
    'validation': {
        'allow_islands': False,
        'allow_self_loops': False,
        'require_source': True,
        'require_catalog_mapping': True,
    },
    'qa': {
        'length_warn_pct': 2.0,
        'length_error_pct': 10.0,
    },
    'exports': {
        'cymdist_enabled': True,
        'dgs_enabled': True,
        'output_dir': 'output',
    },
    'templates': {'cymdist': None, 'dgs': 'config/vnr_dgs_profile.json'},
    'discovery': {
        'enabled': True,
        'official_only': True,
        'source_priority': [
            'REGULATORY_VNRGIS_PACKAGE',
            'REGULATORY_VNR_PUBLICATION',
            'ARCGIS_PUBLIC_REFERENCE',
        ],
        'allowed_hosts': [
            'osinergmin.gob.pe',
            'www.osinergmin.gob.pe',
            'www2.osinergmin.gob.pe',
            'gisem.osinergmin.gob.pe',
        ],
        'refresh_catalog_hours': 24,
    },
    'download': {
        'cache_dir': 'data/vnr_downloads',
        'temp_dir': 'data/tmp',
        'retries': 3,
        'connect_timeout_s': 20,
        'read_timeout_s': 180,
        'max_file_size_mb': 4096,
        'sha256': True,
        'verify_archive': True,
        'auto_extract': False,
    },
}


@dataclass
class Settings:
    """Configuración resuelta (por defecto + YAML del usuario)."""

    project: dict = field(default_factory=lambda: dict(DEFAULTS['project']))
    gis: dict = field(default_factory=lambda: dict(DEFAULTS['gis']))
    validation: dict = field(default_factory=lambda: dict(DEFAULTS['validation']))
    qa: dict = field(default_factory=lambda: dict(DEFAULTS['qa']))
    exports: dict = field(default_factory=lambda: dict(DEFAULTS['exports']))
    templates: dict = field(default_factory=lambda: dict(DEFAULTS['templates']))
    discovery: dict = field(default_factory=lambda: dict(DEFAULTS['discovery']))
    download: dict = field(default_factory=lambda: dict(DEFAULTS['download']))

    @property
    def strict(self) -> bool:
        return bool(self.project.get('strict', True))

    def output_dir(self, base: Path | None = None) -> Path:
        value = str(self.exports.get('output_dir', 'output'))
        path = Path(value)
        if not path.is_absolute() and base is not None:
            return base / path
        return path

    @classmethod
    def load(cls, path: Path | str | None = None) -> Settings:
        """Carga la configuración desde un YAML, fusionada sobre los por defecto.

        Fusiona solo claves de primer nivel y los dictados de segundo nivel, de modo
        que un YAML parcial no anula tolerancias ni políticas que no mencione.
        """
        settings = cls()
        if not path:
            return settings
        yaml_path = Path(path)
        if not yaml_path.is_file():
            raise FileNotFoundError(f'Configuración no encontrada: {yaml_path}')
        import yaml

        with yaml_path.open('r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise TypeError(f'Configuración inválida (no es un objeto): {yaml_path}')
        for key, value in data.items():
            if not isinstance(value, dict):
                raise TypeError(f'Configuración inválida: la sección {key!r} debe ser un objeto.')
            current = getattr(settings, key, None)
            if isinstance(current, dict):
                merged = dict(current)
                merged.update(value)
                setattr(settings, key, merged)
        return settings

    def with_overrides(self, **kwargs) -> Settings:
        """Devuelve una copia con valores sobrescritos (para el CLI)."""
        return replace(self, **kwargs)

    def as_dict(self) -> dict:
        return {
            'project': dict(self.project),
            'gis': dict(self.gis),
            'validation': dict(self.validation),
            'qa': dict(self.qa),
            'exports': dict(self.exports),
            'templates': dict(self.templates),
            'discovery': dict(self.discovery),
            'download': dict(self.download),
        }


def deep_get(mapping: Mapping[str, Any], dotted: str, default: Any = None) -> Any:
    """Acceso por puntos a un dictado anidado (``gis.snap_tolerance_m``)."""
    node: Any = mapping
    for part in dotted.split('.'):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node
