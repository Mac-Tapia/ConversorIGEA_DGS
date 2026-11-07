"""Valida un perfil de empresa contra su esquema, y dice qué falta y qué función afecta (086:RF-30).

Hasta ahora, una empresa nueva solo descubría que le faltaba una clave al llegar a la función que la usaba, y una errata
al escribir una clave pasaba por «no definida». La validación es una lectura: una clave ausente nunca bloquea, porque
cada función sabe qué hacer sin ella; solo un valor imposible es un error, el mismo que daría al usarlo.

El esquema es ``schemas/perfil_empresa_v1.schema.json``. No se usa ``jsonschema``: el núcleo se instala sin dependencias
de más (086:RF-37), y aquí basta el subconjunto de tipos y rangos, más los ``x-`` que dicen la función afectada.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .informes import ConfigInforme, InformeError
from .protecciones import ProteccionesError, criterios_de_perfil
from .perfil_empresa import (PerfilEmpresa, PerfilError, bancos_kvar_por_tension, centrales_termicas, datos_perfil,
                             factor_potencia_cargas, moneda_informes, transformadores_sed)

_TIPOS = {'string': str, 'object': Mapping, 'array': (list, tuple)}


def esquema() -> dict[str, Any]:
    return json.loads((Path(__file__).resolve().parent / 'schemas' / 'perfil_empresa_v1.schema.json').read_text(encoding='utf-8'))


@dataclass(frozen=True)
class Falta:
    """Una clave que el perfil no da: qué función afecta, qué hace el programa sin ella y de quién es el dato."""

    clave: str
    funcion: str
    si_falta: str
    origen: str
    opcional: bool = False


@dataclass
class Resultado:
    errores: list[str] = field(default_factory=list)
    faltan: list[Falta] = field(default_factory=list)
    desconocidas: list[str] = field(default_factory=list)


def _hojas(nodo: Mapping[str, Any], prefijo: str = '') -> list[tuple[str, Mapping[str, Any]]]:
    """Cada clave con su función, con su ruta; las secciones solo agrupan."""
    salida = []
    for clave, sub in (nodo.get('properties') or {}).items():
        ruta = f'{prefijo}{clave}'
        if 'x-funcion' in sub:
            salida.append((ruta, sub))
        salida += _hojas(sub, f'{ruta}.')
    return salida


def claves_del_esquema() -> list[str]:
    """Todas las claves documentadas; la guía tiene que nombrarlas una por una."""
    return [ruta for ruta, _ in _hojas(esquema())]


def _es_del_tipo(valor: Any, tipo: str) -> bool:
    if tipo == 'null':
        return valor is None
    if tipo == 'number':
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    return isinstance(valor, _TIPOS[tipo])


def _revisar_valor(ruta: str, valor: Any, nodo: Mapping[str, Any], errores: list[str]) -> None:
    tipos = nodo.get('type')
    if tipos is not None:
        tipos = [tipos] if isinstance(tipos, str) else tipos
        if not any(_es_del_tipo(valor, t) for t in tipos):
            errores.append(f'{ruta}: tiene que ser {" o ".join(t for t in tipos if t != "null")}, no {valor!r}.')
            return
    if valor is None:
        return
    if 'exclusiveMinimum' in nodo and isinstance(valor, (int, float)) and not valor > nodo['exclusiveMinimum']:
        errores.append(f'{ruta}: tiene que ser mayor que {nodo["exclusiveMinimum"]}, no {valor!r}.')
    if 'maximum' in nodo and isinstance(valor, (int, float)) and valor > nodo['maximum']:
        errores.append(f'{ruta}: no puede pasar de {nodo["maximum"]}, no {valor!r}.')
    if nodo.get('x-formato') == 'regex':
        try:
            re.compile(valor)
        except re.error as exc:
            errores.append(f'{ruta}: no es una expresión regular válida ({exc}): {valor!r}.')
    if isinstance(valor, (list, tuple)):
        for i, x in enumerate(valor):
            if 'items' in nodo:
                _revisar_valor(f'{ruta}[{i}]', x, nodo['items'], errores)
        if nodo.get('x-creciente') and all(isinstance(x, (int, float)) for x in valor) and any(b <= a for a, b in zip(valor, valor[1:])):
            errores.append(f'{ruta}: tiene que ir de menor a mayor: {valor!r}.')


def _recorrer(datos: Mapping[str, Any], nodo: Mapping[str, Any], prefijo: str, r: Resultado) -> None:
    propiedades = nodo.get('properties') or {}
    for clave, valor in datos.items():
        if str(clave).startswith('_'):
            continue
        ruta = f'{prefijo}{clave}'
        sub = propiedades.get(clave)
        if sub is None:
            # Una sección abierta tiene muchas claves técnicas con su propia validación al usarlas.
            if not nodo.get('x-abierta'):
                r.desconocidas.append(ruta)
            continue
        _revisar_valor(ruta, valor, sub, r.errores)
        if isinstance(valor, Mapping) and 'properties' in sub:
            _recorrer(valor, sub, f'{ruta}.', r)


def _valor(datos: Mapping[str, Any], ruta: str) -> Any:
    actual: Any = datos
    for parte in ruta.split('.'):
        if not isinstance(actual, Mapping):
            return None
        actual = actual.get(parte)
    return actual


def _reglas_de_dominio(datos: dict[str, Any], r: Resultado) -> None:
    """Las mismas reglas que al usar el perfil: nada de una segunda versión de ellas."""
    comprobaciones = [
        lambda: PerfilEmpresa(**{k: datos[k] for k in ('crs_origen', 'patron_sed_medicion', 'escala_diagrama',
                                                       'forma_alimentador', 'patron_libro_clientes') if k in datos}),
        lambda: moneda_informes(datos),
        lambda: bancos_kvar_por_tension(datos),
        lambda: transformadores_sed(datos),
        lambda: centrales_termicas(datos),
        lambda: ConfigInforme.de_perfil(datos, Path('.')),
        lambda: criterios_de_perfil(datos),                                   # 049:RF-5, RF-6
        *[(lambda c=c: factor_potencia_cargas(datos, c))
          for c in ('factor_potencia_cargas', 'factor_potencia_minimo_fijas', 'factor_potencia_minimo_escaladas')],
    ]
    for comprobar in comprobaciones:
        try:
            comprobar()
        except (PerfilError, InformeError, ProteccionesError, AttributeError, TypeError, ValueError) as exc:
            texto = str(exc)
            # Lo que el esquema ya dijo no se repite con otras palabras.
            if not any(e.split(':')[0] in texto for e in r.errores):
                r.errores.append(texto)


def validar_perfil(datos: Mapping[str, Any]) -> Resultado:
    """Solo lee: los errores son valores imposibles; lo demás es información para quien configura."""
    r = Resultado()
    datos = dict(datos)
    _recorrer(datos, esquema(), '', r)
    _reglas_de_dominio(datos, r)
    r.faltan = [Falta(ruta, nodo['x-funcion'], nodo['x-si-falta'], nodo['x-origen'], bool(nodo.get('x-opcional')))
                for ruta, nodo in _hojas(esquema()) if _valor(datos, ruta) is None]
    return r


def validar_fichero(ruta: Path | None = None, nombre: str | None = None) -> Resultado:
    """El perfil activo, un fichero o uno con nombre, con su herencia resuelta; sin perfil, todo «falta»."""
    try:
        if nombre:
            activo = {'perfil': nombre}
            from .perfil_empresa import carpeta_perfiles, perfil_con_nombre

            perfil_con_nombre(nombre)
            datos = {**json.loads((carpeta_perfiles() / f'{nombre}.json').read_text(encoding='utf-8')), **activo}
        else:
            datos = datos_perfil(ruta)
    except (PerfilError, OSError, ValueError) as exc:
        return Resultado(errores=[str(exc)])
    return validar_perfil(datos)


def texto_del_resultado(r: Resultado) -> str:
    """Para la orden `validar-perfil`: errores, luego lo que conviene dar, y al final lo opcional."""
    lineas: list[str] = []
    if r.errores:
        lineas += ['Valores imposibles (hay que corregirlos):'] + [f'  - {e}' for e in r.errores] + ['']
    if r.desconocidas:
        lineas += ['Claves que el programa no conoce (¿una errata?):'] + [f'  - {c}' for c in r.desconocidas] + ['']
    for titulo, grupo in (('Faltan, y conviene darlas', [f for f in r.faltan if not f.opcional]),
                          ('Opcionales que no están', [f for f in r.faltan if f.opcional])):
        if grupo:
            lineas.append(f'{titulo}:')
            for f in grupo:
                lineas.append(f'  - {f.clave} [{f.origen}]')
                lineas.append(f'      Función afectada: {f.funcion}')
                lineas.append(f'      Sin ella: {f.si_falta}')
            lineas.append('')
    if not lineas:
        return 'El perfil está completo: da todas las claves del esquema.'
    lineas.append(f'Resultado: {len(r.errores)} error(es), {len(r.faltan)} clave(s) sin dar, {len(r.desconocidas)} desconocida(s). '
                  'Nada de lo que falta impide trabajar.')
    return '\n'.join(lineas)
