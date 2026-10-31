"""043:RF-2 — contratos y huellas de experimentos con custodia exacta."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any


def _publico(valor: Any) -> Any:
    if is_dataclass(valor):
        return {f.name: _publico(getattr(valor, f.name)) for f in fields(valor)}
    if isinstance(valor, Mapping):
        return {k: _publico(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_publico(v) for v in valor]
    return valor


def _huella(valor: Any) -> str:
    contenido = json.dumps(_publico(valor), sort_keys=True, ensure_ascii=False,
                           separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(contenido.encode('utf-8')).hexdigest()


def _congelar(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        if not all(isinstance(k, str) for k in valor):
            raise ValueError('las claves de configuración deben ser texto')
        return MappingProxyType({k: _congelar(v) for k, v in valor.items()})
    if isinstance(valor, (list, tuple)):
        return tuple(_congelar(v) for v in valor)
    return valor


@dataclass(frozen=True)
class ContextoExperimento:
    source_run_id: str
    source_mode: str
    source_fingerprint: str
    project: str
    feeders: tuple[str, ...]
    case_id: str
    case_role: str
    year: int | None
    period: str
    criterio_fijas: str
    profile_hash: str
    topology_hash: str
    controls_hash: str
    scenario_hash: str

    def __post_init__(self):
        for f in fields(self):
            if f.name not in ('year', 'feeders'):
                valor = getattr(self, f.name)
                if not isinstance(valor, str) or not valor.strip():
                    raise ValueError(f'contexto sin {f.name}')
        if self.source_mode not in {'txt', 'mdb', 'vnr'}:
            raise ValueError('source_mode no soportado')
        if self.case_role not in {'caso_base', 'sin_proyecto', 'cargas_nuevas', 'con_proyecto'}:
            raise ValueError('case_role no soportado')
        if self.criterio_fijas not in {'coincidente', 'maximo_mes', 'no_aplica'}:
            raise ValueError('criterio_fijas no soportado')
        if self.year is not None and (type(self.year) is not int or not 1 <= self.year <= 9999):
            raise ValueError('year debe ser un año entero o null')
        if not isinstance(self.feeders, (tuple, list)) or not self.feeders or any(
                not isinstance(f, str) or not f.strip() for f in self.feeders):
            raise ValueError('feeders debe contener identidades explícitas')
        object.__setattr__(self, 'feeders', tuple(self.feeders))
        if len(set(self.feeders)) != len(self.feeders):
            raise ValueError('feeders contiene duplicados')
        for nombre in ('source_fingerprint', 'profile_hash', 'topology_hash', 'controls_hash', 'scenario_hash'):
            if not re.fullmatch(r'[0-9a-f]{64}', getattr(self, nombre)):
                raise ValueError(f'{nombre} debe ser SHA-256 hexadecimal canónico')


def clave_contexto(contexto: ContextoExperimento) -> str:
    return _huella(contexto)


@dataclass(frozen=True)
class ExperimentoSpec:
    contexto: ContextoExperimento
    algoritmo: str
    semillas: tuple[int, ...]
    politica: Mapping[str, Any]
    revision: str
    schema_version: int = 1

    def __post_init__(self):
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('schema_version de experimento no soportada')
        if not isinstance(self.contexto, ContextoExperimento):
            raise ValueError('contexto de experimento inválido')
        if not isinstance(self.algoritmo, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', self.algoritmo):
            raise ValueError('algoritmo inválido')
        if not isinstance(self.revision, str) or not self.revision.strip():
            raise ValueError('falta revision del modelo/código')
        if not isinstance(self.semillas, (list, tuple)) or not self.semillas or any(
                type(s) is not int or s < 0 for s in self.semillas):
            raise ValueError('semillas debe contener enteros no negativos')
        if len(set(self.semillas)) != len(self.semillas):
            raise ValueError('semillas duplicadas')
        if not isinstance(self.politica, Mapping) or not self.politica:
            raise ValueError('falta politica de evaluación')
        object.__setattr__(self, 'semillas', tuple(self.semillas))
        object.__setattr__(self, 'politica', _congelar(self.politica))
        _huella(self)  # Rechaza NaN e información no serializable antes de ejecutar.

    def publico(self) -> dict:
        return _publico(self)

    @property
    def huella(self) -> str:
        return _huella(self)


def cargar_experimento(ruta: Path) -> ExperimentoSpec:
    try:
        payload = json.loads(Path(ruta).read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('el experimento debe ser un objeto JSON')
        payload['contexto'] = ContextoExperimento(**payload['contexto'])
        return ExperimentoSpec(**payload)
    except (KeyError, TypeError) as exc:
        raise ValueError(f'contrato de experimento incompleto o desconocido: {exc}') from exc
