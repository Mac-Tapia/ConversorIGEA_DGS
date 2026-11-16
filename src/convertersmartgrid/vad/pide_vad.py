"""Incorporación del PIDE aprobado al VAD: el contrato 072 → 108 (108:RF-17).

El TdR (numeral 7.5 y cargos adicionales, 3) incorpora al VAD de las empresas bajo el ámbito del FONAFE la inversión,
el COyM y la demanda adicionales del PIDE **aprobado por Osinergmin**. El PIDE lo produce la spec 072; aquí solo se
lee lo que ella entrega, con este contrato (versión ``pide_vad_v1``)::

    {
      "contrato": "pide_vad_v1",
      "id": "...",                    # identificador del PIDE en la 072
      "estado": "aprobado",           # solo «aprobado» se incorpora
      "acto_aprobacion": "...",       # resolución que lo aprueba
      "periodo": "AAAA-AAAA",         # periodo tarifario del VAD al que se incorpora
      "moneda": "...",
      "huella": "<sha256 del PIDE en la 072>",
      "niveles": {"<nivel>": {"inversion": [año 1, …], "oym": [...], "demanda": [...]}}
    }

La anualidad de la inversión adicional se calcula con el FRC de la única fórmula del conversor (``util.frc``), la tasa
``vad.tasa_actualizacion`` y la vida útil ``vad.vida_util_anios``; el VAD ajustado, con la fórmula registrada
(``vad.formula.pide_ajustado``) y la misma tasa; el número de años es ``vad.pide.anios``. Nada de eso está en el código
(108:RF-13).

Una sola tasa (UNA-TASA). La tasa del art. 79 de la LCE está UNA vez en el registro, en la regla principal
``pit.tasa_actualizacion`` (DL 25844); ``vad.tasa_actualizacion`` es una remisión,
``{"mismas_que": "pit.tasa_actualizacion"}``, con la cita del TdR, y :func:`regla_remitida` la sigue. El factor que
publica el TdR (``vad.frc``, 0,124144 para el 12 % y 30 años) es un contraste: si el FRC calculado no cuadra con él a 6
decimales, se usa el calculado y se avisa. Así un cambio de la tasa en la LCE mueve a la vez el VAD y el PIT.

Sin PIDE aprobado, con el ámbito sin declarar, de otro periodo o en otra moneda, **no se incorpora nada** y se dice
por qué: el VAD base queda como estaba.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

# La remisión «mismas_que» la resuelve el registro, en un solo sitio (UNA-TASA v2); se reexporta para quien la
# importaba de aquí.
from ..registro_normativo import (  # noqa: F401
    RegistroError,
    RegistroNormativo,
    ReglaRemitida,
    ReglaVigente,
    remite_a,
    regla_remitida,
)
from ..util import frc as factor_recuperacion
from . import VadError
from .formulas import FormulaError, evaluar

CONTRATO = 'pide_vad_v1'
_PERIODO = re.compile(r'\d{4}-\d{4}')
_SHA = re.compile(r'[0-9a-f]{64}')


@dataclass(frozen=True)
class NivelPide:
    inversion: tuple[float, ...]
    oym: tuple[float, ...]
    demanda: tuple[float, ...]


@dataclass(frozen=True)
class PideAprobado:
    id: str
    estado: str
    acto_aprobacion: str
    periodo: str
    moneda: str
    huella: str
    niveles: Mapping[str, NivelPide] = field(default_factory=dict)


def _serie(valor: Any, donde: str) -> tuple[float, ...]:
    if not isinstance(valor, (list, tuple)) or not valor:
        raise VadError(f'{donde} tiene que ser una lista de valores por año, no {valor!r}')
    out = []
    for i, x in enumerate(valor, 1):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
            raise VadError(f'{donde}, año {i}: tiene que ser un número no negativo, no {x!r}')
        out.append(float(x))
    return tuple(out)


def pide_desde_dict(datos: Mapping[str, Any]) -> PideAprobado:
    """Lee y valida lo que entrega la 072; un campo que falta o un tipo inesperado se nombran."""
    if not isinstance(datos, Mapping):
        raise VadError(f'el PIDE entregado no es un objeto: {type(datos).__name__}')
    if datos.get('contrato') != CONTRATO:
        raise VadError(f'el PIDE entregado no sigue el contrato {CONTRATO} (trae {datos.get("contrato")!r})')
    for campo in ('id', 'estado', 'acto_aprobacion', 'periodo', 'moneda', 'huella'):
        if not isinstance(datos.get(campo), str) or not datos[campo].strip():
            raise VadError(f'el PIDE entregado no trae «{campo}»')
    if not _PERIODO.fullmatch(datos['periodo']):
        raise VadError(f'el periodo del PIDE tiene que ser «AAAA-AAAA», no {datos["periodo"]!r}')
    if not _SHA.fullmatch(datos['huella']):
        raise VadError('la huella del PIDE tiene que ser un sha256 en hexadecimal')
    niveles = datos.get('niveles')
    if not isinstance(niveles, Mapping) or not niveles:
        raise VadError('el PIDE entregado no trae ningún nivel de tensión')
    leidos: dict[str, NivelPide] = {}
    for nivel, series in niveles.items():
        if not isinstance(series, Mapping):
            raise VadError(f'el nivel {nivel} del PIDE no es un objeto')
        nivel_pide = NivelPide(*(_serie(series.get(c), f'{c} del nivel {nivel}') for c in ('inversion', 'oym',
                                                                                           'demanda')))
        if len({len(nivel_pide.inversion), len(nivel_pide.oym), len(nivel_pide.demanda)}) != 1:
            raise VadError(f'las series del nivel {nivel} del PIDE tienen distinto número de años')
        leidos[str(nivel)] = nivel_pide
    return PideAprobado(datos['id'], datos['estado'], datos['acto_aprobacion'], datos['periodo'], datos['moneda'],
                        datos['huella'], leidos)


@dataclass(frozen=True)
class VadNivel:
    """El VAD base de un nivel de tensión: anualidad, COyM y demanda del año 0."""

    anualidad: float
    oym: float
    demanda: float


@dataclass(frozen=True)
class Incorporacion:
    #: True solo si el PIDE se incorporó en todos los niveles pedidos.
    incorporado: bool
    #: Nivel → VAD ajustado (solo si se incorporó).
    vad_ajustado: Mapping[str, float] = field(default_factory=dict)
    #: Por qué no se incorporó, o lo que hay que saber de lo incorporado.
    avisos: tuple[str, ...] = ()
    #: Reglas usadas → huella; y el PIDE de la 072 que se usó (id, acto y huella).
    reglas: Mapping[str, str] = field(default_factory=dict)
    pide: Mapping[str, str] = field(default_factory=dict)


def _numero(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return None
    return float(valor)


def _no(aviso: str) -> Incorporacion:
    return Incorporacion(False, avisos=(aviso,))


def incorporar_pide(registro: RegistroNormativo, base: Mapping[str, VadNivel], pide: PideAprobado | None, *,
                    ambito_fonafe: bool | None, periodo: str, moneda: str,
                    fecha: str | None = None) -> Incorporacion:
    """El VAD ajustado por nivel con el PIDE aprobado, o ninguno con el motivo (108:RF-17)."""
    if ambito_fonafe is None:
        return _no('el estudio no declara si la empresa está en el ámbito del FONAFE: no se incorpora el PIDE')
    if not ambito_fonafe:
        return Incorporacion(False)
    if pide is None:
        return _no('la empresa está en el ámbito del FONAFE y no hay PIDE aprobado entregado por la 072: no se '
                   'incorpora nada')
    if pide.estado != 'aprobado':
        return _no(f'el PIDE {pide.id} está «{pide.estado}», no aprobado: no se incorpora nada')
    if pide.periodo != periodo:
        return _no(f'el PIDE {pide.id} es del periodo {pide.periodo} y el estudio del {periodo}: no se incorpora')
    if pide.moneda != moneda:
        return _no(f'el PIDE {pide.id} está en {pide.moneda} y el VAD en {moneda}: no se suman monedas distintas')
    if not base:
        raise VadError('no hay ningún nivel de tensión en el VAD base')
    sin_pide = sorted(set(base) - set(pide.niveles))
    sobran = sorted(set(pide.niveles) - set(base))
    if sobran:
        return _no(f'el PIDE {pide.id} trae niveles que el VAD base no tiene: {", ".join(sobran)}')
    claves = ('vad.frc', 'vad.vida_util_anios', 'vad.tasa_actualizacion', 'vad.pide.anios',
              'vad.formula.pide_ajustado')
    reglas: dict[str, ReglaRemitida] = {}
    faltan = []
    for c in claves:
        try:
            reglas[c] = regla_remitida(registro, c, fecha)
        except RegistroError as exc:
            faltan.append(c if str(exc).startswith('ninguna norma') else f'{c} ({exc})')
    if faltan:
        return _no(f'el registro no trae {", ".join(faltan)}: no se incorpora el PIDE')
    no_obligan = [c for c, rv in reglas.items() if not rv.obligatoria]
    if no_obligan:
        return _no(f'las reglas {", ".join(no_obligan)} no obligan (norma no comprobada o sin cita): no se incorpora')
    tasa, vida = _numero(reglas['vad.tasa_actualizacion'].valor), _numero(reglas['vad.vida_util_anios'].valor)
    frc_tdr = _numero(reglas['vad.frc'].valor)
    if tasa is None or vida is None or vida <= 0 or frc_tdr is None:
        return _no('la tasa, la vida útil o el factor del TdR registrados no son números válidos: no se incorpora')
    frc = factor_recuperacion(tasa, vida)
    aviso_frc: tuple[str, ...] = ()
    if round(frc, 6) != round(frc_tdr, 6):
        aviso_frc = ((f'el FRC con la tasa vigente ({tasa:g}) y {vida:g} años es {frc:.6f} y el TdR publica '
                      f'{frc_tdr:.6f} (vad.frc): se usa el calculado'),)
    anios = reglas['vad.pide.anios'].valor
    formula = reglas['vad.formula.pide_ajustado'].valor
    ajustado: dict[str, float] = {}
    for nivel, vb in base.items():
        if nivel not in pide.niveles:
            continue
        np_ = pide.niveles[nivel]
        if len(np_.inversion) != anios:
            return _no(f'el PIDE {pide.id} trae {len(np_.inversion)} años en {nivel} y el TdR registrado pide {anios}')
        valores = {'aVNR0': vb.anualidad, 'OyM0': vb.oym, 'POT0': vb.demanda, 'i': float(tasa),
                   'aDVNR': [x * float(frc) for x in np_.inversion], 'DOyM': list(np_.oym),
                   'DPOT': list(np_.demanda)}
        try:
            ajustado[nivel] = evaluar(formula, valores)
        except FormulaError as exc:
            return _no(f'el VAD ajustado de {nivel} no se puede calcular: {exc}')
    avisos = tuple(f'el nivel {n} no tiene inversión en el PIDE {pide.id}: queda su VAD base' for n in sin_pide)
    huellas = {c: rv.huella() for c, rv in reglas.items()}
    huellas.update({rv.principal.regla.clave: rv.principal.huella() for rv in reglas.values()
                    if rv.principal is not rv.remision})
    return Incorporacion(True, ajustado, avisos + aviso_frc, huellas,
                         {'id': pide.id, 'acto_aprobacion': pide.acto_aprobacion, 'huella': pide.huella})
