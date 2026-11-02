"""067:RF-20 a RF-24: el registro decide y un único puntero pone el modelo en uso.

Había dos mundos sin unir: ``model_registry`` guardaba candidatos y decisiones, y ``transformer.cargar`` solo
leía ``promovido.json``. «Reentrenar» registraba y nada cambiaba. Aquí se unen sin relajar nada: solo entra lo
que el registro aprobó, con sus huellas comprobadas, y el puntero sigue siendo la única operación atómica de
carga, porque los modelos heredados que están en uso no figuran en el registro.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from ..model_registry import EstadoModelo, RegistroModelo
from ..runtime_paths import staging_publicacion
from . import almacen, transformer

#: Familia del registro y carpeta de sus modelos en uso.
FAMILIAS = {'transformer': 'ordenes', 'clasificador': 'informes'}
_PREFIJO = 'reg-'
_LARGO = 16
_ARTEFACTOS = ('pesos.pt', 'modelo.json')


def registro() -> RegistroModelo:
    return RegistroModelo(almacen.raiz() / 'model_registry')


def version_de(candidate_id: str) -> str:
    return f'{_PREFIJO}{candidate_id[:_LARGO]}'


def _candidato_de(familia: str, version: str | None) -> str | None:
    """El candidato del registro de una versión en uso; ``None`` si es un modelo heredado."""
    if not version or not version.startswith(_PREFIJO):
        return None
    hallados = list((registro().raiz / familia / 'candidates').glob(f'{version[len(_PREFIJO):]}*'))
    return hallados[0].name if len(hallados) == 1 else None


def _copiar_artefactos(detalle: dict, carpeta: Path) -> None:
    """Una copia verificada y publicada de una vez: nunca queda una versión a medias a la que apuntar."""
    if carpeta.is_dir():
        return
    carpeta.parent.mkdir(parents=True, exist_ok=True)
    origen = Path(detalle['path']) / 'artifacts'
    with staging_publicacion(carpeta) as temporal:
        temporal.mkdir()
        for nombre in _ARTEFACTOS:
            if nombre not in detalle['artifacts']:
                raise ValueError(f'integridad: el candidato no trae {nombre}')
            shutil.copy2(origen / nombre, temporal / nombre)
            with (temporal / nombre).open('rb') as f:
                if hashlib.file_digest(f, 'sha256').hexdigest() != detalle['artifacts'][nombre]:
                    raise ValueError(f'integridad: la copia de {nombre} no coincide')
        os.replace(temporal, carpeta)


def activar(familia: str, candidate_id: str) -> str:
    """Pone en uso un candidato aprobado; el anterior queda en el puntero y en disco (067:RF-20 a RF-22)."""
    nombre, reg = FAMILIAS[familia], registro()
    detalle = reg.detalle(familia, candidate_id)                                     # RF-21: compara huellas
    if (detalle['decision'].get('status') != EstadoModelo.PROMOVIDO.value
            or (detalle['decision'].get('gates') or {}).get('approved') is not True
            or detalle['smoke_reload'].get('ok') is not True):
        raise ValueError('candidato no aprobado por sus puertas o no reabierto')
    version = version_de(candidate_id)
    _copiar_artefactos(detalle, transformer.raiz_modelos(nombre) / version)
    anterior = transformer.version_promovida(nombre)
    transformer.promover(version, f'aprobado por el registro: {candidate_id}', nombre)
    try:
        reg.promover(familia, candidate_id)
    except (OSError, ValueError):
        # El puntero es lo que se carga: no se queda adelantado a una decisión que no se pudo anotar.
        if anterior:
            transformer.promover(anterior, 'el registro no pudo anotar el candidato', nombre)
        else:
            (transformer.raiz_modelos(nombre) / 'promovido.json').unlink(missing_ok=True)
        raise
    return version


def aplicar_decision(familia: str, candidato: dict[str, Any]) -> dict[str, Any]:
    """Lo que el registro decidió, hecho: entra si está aprobado; si no, sigue el actual (067:RF-20, RF-24)."""
    nombre, estado = FAMILIAS[familia], candidato.get('status')
    if estado == EstadoModelo.PROMOVIDO.value:
        try:
            version = activar(familia, candidato['candidate_id'])
            return {'promovido': True, 'estado': estado, 'version': version, 'en_uso': version, 'motivo': ''}
        except (OSError, ValueError, KeyError) as exc:
            motivo = str(exc)
    else:
        motivo = f'el registro dejó el candidato en {estado}'
    return {'promovido': False, 'estado': estado, 'version': None,
            'en_uso': transformer.version_promovida(nombre), 'motivo': motivo}


def volver_al_anterior(familia: str) -> str | None:
    """Vuelve al modelo anterior con el puntero y el registro de acuerdo (067:RF-23)."""
    version = transformer.volver_al_anterior(FAMILIAS[familia])
    if version is None:
        return None
    candidato = _candidato_de(familia, version)
    if candidato is not None:
        registro().promover(familia, candidato)
    else:
        registro().retirar_activo(familia)
    return version
