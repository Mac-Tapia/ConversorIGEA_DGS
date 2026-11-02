"""Modelo efectivo del DGS, sin releer fuentes ni ejecutar objetos serializados (065:RF-6).

El snapshot se publica en el mismo staging que el DGS. Su hash queda enlazado en la
metadata del DGS; un artefacto antiguo o incompleto exige volver a convertir.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from pathlib import Path

from . import combine, estructura, model
from .util import write_json_atomic


_TIPOS = {clase.__name__: clase for clase in (
    model.FeederModel, model.Node, model.Line, model.LineType, model.Load, model.Sed,
    model.SwitchingDevice, model.Coupler, model.CapacitorBank,
    combine.CombinedInfo, combine.FeederRef, combine.TiePoint, combine.BarraSet,
    combine.Cabecera, estructura.Sistema,
)}
_VERSION = 'convertersmartgrid-preflight-v1'


def snapshot_model(valor):
    """Codifica solo datos y clases conocidas; conserva tuplas, conjuntos y claves."""
    if is_dataclass(valor):
        if _TIPOS.get(type(valor).__name__) is not type(valor):
            raise ValueError(f'Tipo no admitido en el modelo efectivo: {type(valor).__name__}')
        return {'tipo': type(valor).__name__,
                'campos': {f.name: snapshot_model(getattr(valor, f.name)) for f in fields(valor)}}
    if isinstance(valor, dict):
        return {'mapa': [[snapshot_model(k), snapshot_model(v)] for k, v in valor.items()]}
    if isinstance(valor, (set, frozenset)):
        return {'conjunto': sorted((snapshot_model(v) for v in valor), key=_texto)}
    if isinstance(valor, tuple):
        return {'tupla': [snapshot_model(v) for v in valor]}
    if isinstance(valor, list):
        return [snapshot_model(v) for v in valor]
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    raise ValueError(f'Valor no admitido en el modelo efectivo: {type(valor).__name__}')


def _restaurar(valor):
    if isinstance(valor, list):
        return [_restaurar(v) for v in valor]
    if not isinstance(valor, dict):
        return valor
    if set(valor) == {'mapa'}:
        return {_restaurar(k): _restaurar(v) for k, v in valor['mapa']}
    if set(valor) == {'conjunto'}:
        return {_restaurar(v) for v in valor['conjunto']}
    if set(valor) == {'tupla'}:
        return tuple(_restaurar(v) for v in valor['tupla'])
    if set(valor) == {'tipo', 'campos'} and valor['tipo'] in _TIPOS:
        clase = _TIPOS[valor['tipo']]
        if set(valor['campos']) != {f.name for f in fields(clase)}:
            raise ValueError('Esquema del modelo efectivo incompatible; vuelva a convertir.')
        return clase(**{k: _restaurar(v) for k, v in valor['campos'].items()})
    raise ValueError('Objeto no admitido en el contrato del modelo efectivo.')


def _texto(datos) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _digest(datos) -> str:
    return hashlib.sha256(_texto(datos).encode('utf-8')).hexdigest()


def model_digest(modelo: model.FeederModel) -> str:
    """Huella lógica del modelo completo, incluidos estados y asignación de miembros."""
    return _digest(snapshot_model(modelo))


def write_contract(dgs: Path, modelo: model.FeederModel, *, members=None, context=None) -> Path:
    """Enlaza el snapshot post-reglas al DGS y a su metadata antes de publicar."""
    contrato = {
        'schema_version': _VERSION, 'dgs_file': dgs.name,
        'dgs_sha256': hashlib.sha256(dgs.read_bytes()).hexdigest(),
        'model': snapshot_model(modelo),
        'members': members if members is not None else [snapshot_model(modelo)],
        'context': context or {},
    }
    contrato['model_sha256'] = _digest(contrato['model'])
    contrato['payload_sha256'] = _digest(contrato)
    ruta = dgs.with_name(f'{dgs.stem}_preflight.json')
    write_json_atomic(ruta, contrato)
    metadata_path = dgs.with_name(f'{dgs.stem}_feeder_metadata.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    metadata['preflight_contract'] = {
        'file': ruta.name, 'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest(),
        'model_sha256': contrato['model_sha256'],
    }
    write_json_atomic(metadata_path, metadata)
    return ruta


def load_contract(dgs: Path) -> dict:
    """Rechaza snapshots ausentes, modificados, incompatibles o de otro DGS."""
    metadata = json.loads(dgs.with_name(f'{dgs.stem}_feeder_metadata.json').read_text(encoding='utf-8'))
    enlace = metadata.get('preflight_contract') or {}
    ruta = dgs.with_name(f'{dgs.stem}_preflight.json')
    if enlace.get('file') != ruta.name:
        raise ValueError('Falta el contrato del modelo efectivo; vuelva a convertir.')
    contenido = ruta.read_bytes()
    if hashlib.sha256(contenido).hexdigest() != enlace.get('sha256'):
        raise ValueError('El contrato del modelo efectivo fue modificado; vuelva a convertir.')
    contrato = json.loads(contenido)
    huella = contrato.pop('payload_sha256', None)
    if contrato.get('schema_version') != _VERSION or _digest(contrato) != huella:
        raise ValueError('Contrato del modelo efectivo incompatible o corrupto.')
    if (contrato.get('dgs_file') != dgs.name
            or contrato.get('dgs_sha256') != hashlib.sha256(dgs.read_bytes()).hexdigest()
            or contrato['dgs_sha256'] != metadata.get('dgs_sha256')):
        raise ValueError('El DGS ya no corresponde al modelo efectivo; vuelva a convertir.')
    if (_digest(contrato['model']) != contrato.get('model_sha256')
            or contrato['model_sha256'] != enlace.get('model_sha256')):
        raise ValueError('La huella del modelo efectivo no corresponde al contrato.')
    contrato['model'] = _restaurar(contrato['model'])
    contrato['members'] = [_restaurar(m) for m in contrato['members']]
    if (not isinstance(contrato['model'], model.FeederModel) or not contrato['members']
            or any(not isinstance(m, model.FeederModel) for m in contrato['members'])):
        raise ValueError('El contrato no contiene modelos efectivos completos.')
    esperado = ({f.name for f in contrato['model'].combined.feeders}
                if contrato['model'].combined is not None else {contrato['model'].name})
    if {m.name for m in contrato['members']} != esperado or len(contrato['members']) != len(esperado):
        raise ValueError('Los miembros del contrato no corresponden al DGS.')
    return contrato
