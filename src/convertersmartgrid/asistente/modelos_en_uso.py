"""067:RF-20 a RF-24: el registro decide y un único puntero pone el modelo en uso.

Había dos mundos sin unir: ``model_registry`` guardaba candidatos y decisiones, y ``transformer.cargar`` solo
leía ``promovido.json``. «Reentrenar» registraba y nada cambiaba. Aquí se unen sin relajar nada: solo entra lo
que el registro aprobó, con sus huellas comprobadas, y el puntero sigue siendo la única operación atómica de
carga, porque los modelos heredados que están en uso no figuran en el registro.

085:RF-26 a RF-33: la otra puerta de entrada no aprueba nada. El 2026-11-04 el usuario decidió usar un candidato que no
pasa las puertas, porque el modelo en uso da 0,17 en la prueba sellada y deja colarse el 67 % de lo que no es una orden.
Esa decisión es suya, queda anotada con su motivo y sus cifras, y el candidato sigue rechazado.
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
#: Un prefijo propio: ``_candidato_de`` lleva los ``reg-`` a ``promover``, que rechazaría a uno de estos.
_PREFIJO_PROVISIONAL = 'prov-'
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


def version_provisional(candidate_id: str) -> str:
    return f'{_PREFIJO_PROVISIONAL}{candidate_id[:_LARGO]}'


def _candidato_provisional_de(familia: str, version: str) -> str | None:
    hallados = list((registro().raiz / familia / 'candidates').glob(f'{version[len(_PREFIJO_PROVISIONAL):]}*'))
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


def _una_cifra(medida: Any) -> dict[str, Any] | None:
    if not isinstance(medida, dict):
        return None
    return {k: medida[k] for k in ('acierto_tarea', 'f1_datos', 'ejemplos') if k in medida} or None


def cifras_de(detalle: dict) -> dict[str, Any]:
    """Las cifras tal como las guardó el registro al decidir: nadie las escribe a mano (085:RF-26)."""
    m = detalle['metrics']
    rechazo, previo = m.get('rechazo') or {}, m.get('en_uso') or {}
    return {'examen_maestro': _una_cifra(m.get('examen_maestro')),
            'prueba_sellada': _una_cifra((m.get('prueba_sellada') or {}).get('medida')),
            'sinteticas': _una_cifra(m.get('sinteticas')), 'humanas': _una_cifra(m.get('humanas')),
            'rechazo': {k: rechazo[k] for k in ('rechazada', 'se_cuela', 'ejemplos') if k in rechazo},
            'fallos_de_puertas': len(detalle['decision'].get('fallos') or ()),
            'modelo_en_uso_al_decidir': {'version': previo.get('version'), 'sinteticas': _una_cifra(previo.get('sinteticas')),
                                         'humanas': _una_cifra(previo.get('humanas')),
                                         'se_cuela': (previo.get('rechazo') or {}).get('se_cuela')}}


def poner_provisional(familia: str, candidate_id: str, *, decidido_por: str, motivo: str,
                      fecha: str | None = None) -> dict[str, Any]:
    """Pone en uso un candidato rechazado por decisión del usuario, sin aprobarlo (085:RF-26 a RF-29).

    La decisión se anota antes de mover el puntero: lo contrario dejaría un rato un modelo sin aprobar en uso y sin motivo."""
    nombre, reg = FAMILIAS[familia], registro()
    version = version_provisional(candidate_id)
    if transformer.version_promovida(nombre) == version:
        # Repetirla haría de este modelo su propio anterior, y «volver» ya no volvería a ningún sitio.
        raise ValueError(f'{version} ya está en uso')
    detalle = reg.validar_uso_provisional(familia, candidate_id)
    _copiar_artefactos(detalle, transformer.raiz_modelos(nombre) / version)
    anterior = transformer.version_promovida(nombre)
    fila = reg.anotar_uso_provisional(familia, candidate_id, version=version, decidido_por=decidido_por, motivo=motivo,
                                      fecha=fecha or almacen.ahora(), cifras=cifras_de(detalle), anterior=anterior)
    transformer.promover(version, f"provisional por decisión de {fila['decidido_por']}, no pasa las puertas: {candidate_id}", nombre)
    return fila


def uso_provisional(familia: str) -> dict[str, Any] | None:
    """La decisión del modelo en uso si es provisional; sale del puntero, y deja de valer al volver o al aprobarse otro (085:RF-29)."""
    version = transformer.version_promovida(FAMILIAS[familia])
    if not version or not version.startswith(_PREFIJO_PROVISIONAL):
        return None
    candidato = _candidato_provisional_de(familia, version)
    fila = registro().uso_provisional(familia, candidato) if candidato else None
    # Un puntero provisional sin su anotación no se calla ni pasa por aprobado: sigue siendo provisional.
    return fila or {'decision': 'uso_provisional', 'version': version, 'candidate_id': candidato, 'puertas_aprobadas': False,
                    'confirmacion_obligatoria': True, 'sin_anotacion': True, 'cifras': {}}


def _numero(valor: Any, decimales: int = 3) -> str:
    return f'{valor:.{decimales}f}'.replace('.', ',') if isinstance(valor, (int, float)) else 'sin medir'


def aviso_provisional(uso: dict[str, Any]) -> str:
    """Lo que el operador lee en cada plan: que no pasa las puertas y con qué cifras (085:RF-30)."""
    if uso.get('sin_anotacion'):
        return (f"Modelo de órdenes provisional, no pasa las puertas: {uso.get('version')} no tiene anotada la decisión que lo "
                'puso en uso. Cada plan espera su confirmación.')
    c = uso.get('cifras') or {}
    maestro, sellada = c.get('examen_maestro') or {}, c.get('prueba_sellada') or {}
    sinteticas, rechazo = c.get('sinteticas') or {}, c.get('rechazo') or {}
    cuela = rechazo.get('se_cuela')
    return (f"Modelo de órdenes provisional, no pasa las puertas (decisión de {uso.get('decidido_por')}, {str(uso.get('fecha'))[:10]}): "
            f"examen del maestro {_numero(maestro.get('acierto_tarea'))} de 0,98 y F1 {_numero(maestro.get('f1_datos'))} de 0,95 "
            f"({maestro.get('ejemplos', 'sin')} órdenes); prueba sellada {_numero(sellada.get('acierto_tarea'))}; "
            f"sintéticas {_numero(sinteticas.get('acierto_tarea'))}; se cuela {_numero(cuela * 100 if cuela is not None else None, 1)} %. "
            'Cada plan espera su confirmación.')


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
