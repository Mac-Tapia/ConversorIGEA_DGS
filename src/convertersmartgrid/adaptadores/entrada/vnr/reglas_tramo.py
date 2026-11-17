"""Las reglas de estado y medio de un tramo VNR-GIS, en un solo sitio y sin dependencias (080:RF-53, RF-55).

Las usan la vía SQL (``connectors.sqlserver_vnr``), la vía de capas (``pipeline``) y el puente
(``application.cymdist_bridge``). No importan nada del proyecto: así ninguna de las tres cierra un
ciclo con las otras. Un valor de la fuente sin regla no se adivina: se anota en
``metadata['valores_sin_regla']`` y el puente lo dice como issue.
"""

from __future__ import annotations

import re
from typing import Any

#: 080:RF-53: designaciones que dicen «aéreo» en la capa, el código o la descripción de la norma.
#: Van antes que las de cable: el autoportante lleva aislamiento XLPE y es aéreo.
AEREO = re.compile(r'A[EÉ]RE[OA]|OVERHEAD|AUTOPORTANTE|\bCAAI\b|\bAAAC\b|\bACSR\b|DESNUD', re.I)
#: Designaciones de cable de energía (NTP/IEC) y de red subterránea, de cualquier empresa.
CABLE = re.compile(r'SUBTERR|SOTERR|UNDERGROUND|ENTERRAD|\bN2XS\w*|\bNA2XS\w*|\bN2XOH\b'
                   r'|\bNKY\b|\bNYY\b|\bXLPE\b', re.I)
#: Estados de un tramo que no está en servicio (080:RF-55).
FUERA_DE_SERVICIO = frozenset({'out_of_service', 'fuera_de_servicio', 'fuera de servicio',
                               'fuera servicio', 'outserv', 'off', 'na', 'no activo', '0', 'false',
                               'inactivo', 'inactive', 'retirado', 'desenergizado'})
#: 080:RF-55: la leyenda ESTADO_VNR de VNR-GIS (tabla ``cfgTablaCodigo`` de su base de parámetros,
#: la misma en las copias de cuatro empresas, 2026-11-14): E existente, M modificado y N nuevo
#: están construidos; P proyectado y X eliminado no están en la red. En la misma tabla, la leyenda
#: ESTADO_OP_EPS dice que «NA» es «NORMALMENTE ABIERTO».
ESTADOS_VNR = {'E': 'in_service', 'M': 'in_service', 'N': 'in_service',
               'P': 'out_of_service', 'X': 'out_of_service'}
EN_SERVICIO = frozenset({'in_service', 'en servicio', 'en_servicio', 'existente', 'activo', 'active',
                         'on', '1', 'true'})
#: 080:RF-53: ``CodTipoRed`` de VNR-GIS: A aérea, S subterránea. Sin leyenda en la base; confirmado
#: con los tramos de cuatro empresas (2026-11-14): todo «S» lleva norma de cable (N2, NK, NA, EC,
#: YC, NY) y todo «A», de conductor aéreo o autoportante (AA, CU, AS, CS, AP, CP).
TIPOS_RED = {'A': True, 'S': False}


def fuera_de_servicio(status: Any) -> bool:
    """080:RF-55: el estado del tramo dice que no está en servicio."""
    return str(status or '').strip().casefold() in FUERA_DE_SERVICIO


def texto_fuente(valor: Any) -> str:
    """080:RF-55: el valor de la fuente como texto, sin regla (vacío si no hay o es NaN)."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return ''
    return str(valor).strip()


def estado_de_tramo(valor: Any) -> str | None:
    """080:RF-55: ``in_service``/``out_of_service`` del estado de la fuente; None si no tiene regla.

    Vacío es en servicio (la fuente no dice nada). Un valor sin regla no se adivina: devuelve
    None y quien llama lo deja en servicio y lo anota.
    """
    texto = str(valor or '').strip()
    if not texto:
        return 'in_service'
    if texto.upper() in ESTADOS_VNR:
        return ESTADOS_VNR[texto.upper()]
    if fuera_de_servicio(texto):
        return 'out_of_service'
    if texto.casefold() in EN_SERVICIO:
        return 'in_service'
    return None


def medio_de_tipo_red(valor: Any) -> bool | None:
    """080:RF-53: lo que dice el tipo de red de la fuente (``CODTIPORED``): aéreo, cable o None.

    El código de VNR-GIS (``TIPOS_RED``) o una palabra («AEREA», «SUBTERRANEA»…). Lo demás no se
    adivina: queda None y el medio se deduce como si la fuente no lo dijera.
    """
    texto = str(valor or '').strip()
    if not texto:
        return None
    if texto.upper() in TIPOS_RED:
        return TIPOS_RED[texto.upper()]
    if AEREO.search(texto):
        return True
    if CABLE.search(texto):
        return False
    return None


#: 080:RF-55: dónde se cuentan los valores sin regla de los tramos MT (los que el puente dice como issue).
SIN_REGLA_MT = 'valores_sin_regla'
#: 080:RF-55: y los de los tramos BT, aparte: el puente a CYMDIST solo cuenta tramos MT.
SIN_REGLA_BT = 'valores_sin_regla_bt'


def anotar_sin_regla(metadata: dict, campo: str, valor: Any, *, clave: str = SIN_REGLA_MT) -> None:
    """080:RF-53, RF-55: cuenta en el modelo un valor de la fuente que no tiene regla, para el issue."""
    cuenta = metadata.setdefault(clave, {}).setdefault(campo, {})
    clave = str(valor).strip()
    cuenta[clave] = cuenta.get(clave, 0) + 1


def estado_o_anota(metadata: dict, valor: Any, *, clave: str = SIN_REGLA_MT) -> str:
    """080:RF-55: el estado del tramo; uno sin regla queda en servicio y se anota (en ``clave``)."""
    estado = estado_de_tramo(valor)
    if estado is None:
        anotar_sin_regla(metadata, 'estado', valor, clave=clave)
        return 'in_service'
    return estado


def medio_o_anota(metadata: dict, valor: Any, *, clave: str = SIN_REGLA_MT) -> bool | None:
    """080:RF-53: aéreo o cable del tipo de red; uno sin regla queda None y se anota (en ``clave``)."""
    medio = medio_de_tipo_red(valor)
    if medio is None and str(valor or '').strip():
        anotar_sin_regla(metadata, 'tipo_red', valor, clave=clave)
    return medio
