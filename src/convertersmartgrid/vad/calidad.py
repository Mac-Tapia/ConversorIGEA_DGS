"""Verificación de la calidad de servicio de la empresa modelo (108:RF-18).

El TdR (numeral 6.11) pide demostrar que la red adaptada cumple los indicadores de calidad de producto y de
suministro de la NTCSE o la NTCSER. Qué indicadores se verifican sale del registro (``vad.calidad.indicadores``: clave,
nombre, unidad y sentido, ``maximo`` o ``minimo``), y el límite de cada uno también
(``vad.calidad.limite.<clave>``, transcrito de la norma técnica que corresponda). El código no tiene ningún límite.

Un indicador sin límite registrado, con un límite que no obliga o sin valor calculado es un **hueco nombrado**: nunca
se da por cumplido. El resultado dice, por sistema, qué indicador no cumple y por cuánto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from ..registro_normativo import RegistroError, RegistroNormativo
from . import VadError

SENTIDOS = ('maximo', 'minimo')
ESTADOS = ('cumple', 'no_cumple', 'sin_verificar')


@dataclass(frozen=True)
class Indicador:
    clave: str
    nombre: str
    unidad: str
    sentido: str


@dataclass(frozen=True)
class Verificacion:
    sistema: str
    indicador: str
    estado: str
    valor: float | None = None
    limite: float | None = None
    regla_limite: str = ''
    motivo: str = ''


@dataclass(frozen=True)
class ResultadoCalidad:
    verificaciones: tuple[Verificacion, ...]

    @property
    def no_cumplen(self) -> list[Verificacion]:
        return [v for v in self.verificaciones if v.estado == 'no_cumple']

    @property
    def sin_verificar(self) -> list[Verificacion]:
        return [v for v in self.verificaciones if v.estado == 'sin_verificar']

    @property
    def estado(self) -> str:
        """``no_cumple`` si alguno no cumple; ``sin_verificar`` si alguno no se pudo verificar; si no, ``cumple``."""
        if self.no_cumplen:
            return 'no_cumple'
        return 'sin_verificar' if self.sin_verificar else 'cumple'


def indicadores(registro: RegistroNormativo, fecha: str | None = None) -> list[Indicador]:
    try:
        valor = registro.regla('vad.calidad.indicadores', fecha).regla.valor
    except RegistroError as exc:
        raise VadError(f'el registro no trae los indicadores de calidad (vad.calidad.indicadores): {exc}') from exc
    if not isinstance(valor, list) or not valor:
        raise VadError('vad.calidad.indicadores tiene que ser una lista no vacía')
    out: list[Indicador] = []
    for d in valor:
        if not isinstance(d, Mapping) or not all(isinstance(d.get(c), str) and d[c].strip()
                                                 for c in ('clave', 'nombre', 'unidad', 'sentido')):
            raise VadError(f'un indicador de calidad del registro no trae clave, nombre, unidad y sentido: {d!r}')
        if d['sentido'] not in SENTIDOS:
            raise VadError(f'el indicador {d["clave"]} tiene sentido {d["sentido"]!r}; los válidos son {SENTIDOS}')
        out.append(Indicador(d['clave'], d['nombre'], d['unidad'], d['sentido']))
    claves = [i.clave for i in out]
    if len(set(claves)) != len(claves):
        raise VadError(f'indicadores de calidad repetidos en el registro: {claves}')
    return out


def _numero(x: Any) -> bool:
    return not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)


def verificar_calidad(registro: RegistroNormativo, calculados: Mapping[str, Mapping[str, float]],
                      fecha: str | None = None) -> ResultadoCalidad:
    """``calculados``: sistema → indicador → valor esperable de la red adaptada."""
    if not calculados:
        raise VadError('no hay ningún sistema con indicadores de calidad calculados')
    lista = indicadores(registro, fecha)
    conocidos = {i.clave for i in lista}
    out: list[Verificacion] = []
    for sistema, valores in calculados.items():
        extra = sorted(set(valores) - conocidos)
        if extra:
            raise VadError(f'el sistema {sistema} trae indicadores que el registro no tiene: {", ".join(extra)}')
        for ind in lista:
            clave_limite = f'vad.calidad.limite.{ind.clave}'
            valor = valores.get(ind.clave)
            if valor is None:
                out.append(Verificacion(sistema, ind.clave, 'sin_verificar', regla_limite=clave_limite,
                                        motivo=f'{ind.nombre}: sin valor calculado para la red adaptada'))
                continue
            if not _numero(valor):
                raise VadError(f'{ind.nombre} del sistema {sistema} no es un número: {valor!r}')
            try:
                rv = registro.regla(clave_limite, fecha)
            except RegistroError:
                out.append(Verificacion(sistema, ind.clave, 'sin_verificar', float(valor), regla_limite=clave_limite,
                                        motivo=f'{ind.nombre}: el límite no está en el registro ({clave_limite}); '
                                               'hay que transcribirlo de la norma técnica de calidad'))
                continue
            limite = rv.regla.valor
            if not _numero(limite):
                raise VadError(f'el límite {clave_limite} del registro no es un número: {limite!r}')
            if not rv.obligatoria:
                out.append(Verificacion(sistema, ind.clave, 'sin_verificar', float(valor), float(limite), clave_limite,
                                        f'{ind.nombre}: el límite es de {rv.norma.acto}, «{rv.estado}», y no obliga'))
                continue
            excede = valor > limite if ind.sentido == 'maximo' else valor < limite
            if excede:
                out.append(Verificacion(sistema, ind.clave, 'no_cumple', float(valor), float(limite), clave_limite,
                                        f'{ind.nombre} = {valor} {ind.unidad} '
                                        f'{"supera" if ind.sentido == "maximo" else "no llega a"} el límite {limite} '
                                        f'({rv.norma.acto})'))
            else:
                out.append(Verificacion(sistema, ind.clave, 'cumple', float(valor), float(limite), clave_limite))
    return ResultadoCalidad(tuple(out))

