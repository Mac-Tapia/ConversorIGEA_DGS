"""Interfaz de exportador y perfil de destino (secciones 16 y U14).

Cada ``TargetProfile`` documenta el contrato real de un simulador (versión,
muestra/template verificado, codificación, delimitador, mapeo, campos, unidades y
reglas). Un exportador se **valida contra el perfil** antes de escribir; nunca se
inventan clases/columnas DGS ni columnas CYMDIST.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from vnr_etl.models import CanonicalModel


@dataclass(frozen=True)
class TargetProfile:
    simulator: str
    version: str = ''
    workflow: str = ''
    sample_hash: str = ''
    """Hash de la muestra/template verificada que da validez a este perfil."""
    sample_path: str = ''
    encoding: str = 'utf-8'
    delimiter: str = ';'
    object_mapping: dict = field(default_factory=dict)
    required_fields: tuple[str, ...] = ()
    units: dict = field(default_factory=dict)
    validation_rules: dict = field(default_factory=dict)

    @classmethod
    def load(cls, profile_path: Path | str) -> TargetProfile:
        path = Path(profile_path)
        if not path.is_file():
            raise FileNotFoundError(f'Perfil objetivo no encontrado: {path}')
        if path.suffix.lower() in ('.yaml', '.yml'):
            import yaml

            data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        else:
            data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, Mapping):
            raise TypeError(f'Perfil objetivo inválido: {path}')
        values = {name: data.get(name, field_.default)
                  for name, field_ in cls.__dataclass_fields__.items()}
        values['required_fields'] = tuple(values.get('required_fields') or ())
        sample_path = Path(str(values.get('sample_path') or ''))
        if sample_path and not sample_path.is_absolute():
            sample_path = (path.parent / sample_path).resolve()
        values['sample_path'] = str(sample_path) if str(sample_path) else ''
        return cls(**values)

    @property
    def verified(self) -> bool:
        """Valida el contrato contra la muestra local, no solo contra metadatos."""
        if not (self.sample_hash and self.sample_path and self.object_mapping):
            return False
        path = Path(self.sample_path)
        if not path.is_file():
            return False
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest().lower() == self.sample_hash.lower()


@runtime_checkable
class SimulatorExporter(Protocol):
    def validate_mapping(self, model: CanonicalModel) -> list: ...
    def export(self, model: CanonicalModel, output_dir: Path) -> list[Path]: ...


class ExportBlocked(RuntimeError):
    """El export está bloqueado por una puerta obligatoria (sección 17)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
