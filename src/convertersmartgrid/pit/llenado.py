"""Llenado de los formatos que exige el estudio del PIT (107:RF-9, aclaración; 107-T19b).

Qué formatos lleva el estudio del plan no está en el código: sale de la regla ``pit.plan.formatos_exigidos`` del
registro (en el real, el num. 5.7 de la Norma Tarifas). Cada formato exigido sale de una de dos maneras:
- **llenado**, si tiene mapeo campo → celda (``MAPEADORES``) y se entregó su fuente;
- **plantilla**, nombrada con su causa: no transcrito, sin datos de origen o sin mapeo todavía.

Nunca sale vacío en silencio. Los que aún no tienen mapeo se listan en ``pendientes_de_mapeo``: mientras quede uno,
T19 no se cierra (condición del auditor ca, 2026-11-14).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError
from .cuadros import codigos_de_grupos, formatos_aplicables
from .f208 import CODIGO as F208
from .f208 import celdas_f208
from .formatos_red import datos_f001, datos_f002, datos_f003
from .plantillas import celdas_de_formato

__all__ = ['MAPEADORES', 'formatos_exigidos', 'llenar_formatos']

Mapeador = Callable[[RegistroNormativo, Mapping[str, Any], 'str | None'], dict[str, Any]]


def _f208(registro: RegistroNormativo, fuente: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    return celdas_f208(registro, fuente, fecha)


def _f001(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    datos, sin_nivel = datos_f001(entrada['red'], registro, entrada['fuente'], fecha)
    resultado = celdas_de_formato(registro, 'F-001', datos, fecha=fecha)
    resultado['huecos'] += [{'bloque': 'titulares', 'causa': f'{e["tipo"]} {e["id"]}: {e["causa"]}'} for e in sin_nivel]
    return resultado


def _f002(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    datos = datos_f002(entrada['red'], entrada['fuente'], entrada.get('frecuencia_hz'))
    return celdas_de_formato(registro, 'F-002', datos, fecha=fecha)


def _f003(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    return celdas_de_formato(registro, 'F-003', datos_f003(entrada['red'], entrada['fuente']), fecha=fecha)


#: Formato → (clave de su fuente en ``fuentes``, función que lo llena). Crece formato a formato en 107-T19b. La red
#: del área (``red``: ``{'fuente', 'red', 'frecuencia_hz'}``) alimenta a F-001, F-002 y F-003.
MAPEADORES: dict[str, tuple[str, Mapeador]] = {
    'F-001': ('red', _f001), 'F-002': ('red', _f002), 'F-003': ('red', _f003), F208: (F208, _f208)}


def formatos_exigidos(registro: RegistroNormativo, fecha: str | None = None) -> list[str]:
    """Los códigos que exige el estudio del plan, de la regla citada del registro."""
    try:
        rv = registro.regla('pit.plan.formatos_exigidos', fecha)
    except RegistroError as exc:
        raise PitError('falta la regla pit.plan.formatos_exigidos en el registro normativo: no se supone qué formatos '
                       f'lleva el estudio ({exc})') from exc
    grupos = rv.regla.valor.get('grupos') if isinstance(rv.regla.valor, Mapping) else None
    if not grupos:
        raise PitError('la regla pit.plan.formatos_exigidos no trae sus «grupos»')
    return codigos_de_grupos(grupos)


def llenar_formatos(registro: RegistroNormativo, fuentes: Mapping[str, Mapping[str, Any]], fecha: str | None = None,
                    mapeadores: Mapping[str, tuple[str, Mapeador]] | None = None) -> dict[str, Any]:
    """Cada formato exigido, llenado o como plantilla con su causa, y las celdas de los llenados.

    ``fuentes``: clave de fuente (``red``, ``F-208``…) → la entrada de su mapeador, con su ``fuente`` y su huella.
    ``mapeadores`` sustituye a ``MAPEADORES`` (pruebas).
    """
    tabla: Mapping[str, tuple[str, Mapeador]] = MAPEADORES if mapeadores is None else mapeadores
    aplicables = {f['codigo']: f for f in formatos_aplicables(registro, fecha)['formatos']}
    salida, celdas, pendientes = [], [], []
    for codigo in formatos_exigidos(registro, fecha):
        f = aplicables.get(codigo)
        fila: dict[str, Any] = {'codigo': codigo, 'titulo': (f or {}).get('titulo') or codigo, 'huecos': []}
        if f is None:
            fila.update(estado='plantilla', causa='el estudio lo exige y la norma vigente no lo lista')
        elif not f['transcrito']:
            fila.update(estado='plantilla', causa='formato no transcrito en el registro normativo')
        elif codigo not in tabla:
            fila.update(estado='plantilla', causa='sin mapeo campo → celda todavía (107-T19b)')
            pendientes.append(codigo)
        elif tabla[codigo][0] not in fuentes:
            fila.update(estado='plantilla', causa=f'sin datos de origen: no se entregó la fuente '
                                                  f'«{tabla[codigo][0]}» de {codigo}')
        else:
            clave, funcion = tabla[codigo]
            resultado = funcion(registro, fuentes[clave], fecha)
            fila.update(estado='llenado', causa='', huecos=resultado.get('huecos', []))
            celdas += resultado['celdas']
        salida.append(fila)
    return {'formatos': salida, 'celdas': celdas, 'pendientes_de_mapeo': pendientes}
