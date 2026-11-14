"""Qué edición corre, y qué funciones en beta marca la de producto (086:RF-15, RF-16, RF-22).

Una sola función para preguntarlo, para que las salidas a la red y la web no acaben leyendo dos variables distintas.
Hasta el 2026-11-13 aquí estaba también la lista de rutas y tareas que el producto negaba (entrenar, gemelo, pronóstico,
mejoras, revisión por roles y preguntas sobre el código). El usuario lo cambió ese día: «nada debería estar apagado ni
bloqueado». La edición ya solo decide lo que es de seguridad, en ``salidas_red.py`` (RF-22) y en el CORS de la web, y
marca las funciones en beta, que siguen activas por defecto y el operador puede apagar.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .runtime_paths import es_programa_instalado, raiz_programa

VARIABLE_EDICION = 'CSG_EDICION'
#: Las funciones en beta que esta instalación no quiere, separadas por comas (086, «desactivable»).
VARIABLE_BETA_APAGADAS = 'CSG_BETA_APAGADAS'

MENSAJE_BETA_APAGADA = 'Esta función está desactivada en esta instalación.'
#: 086:RF-15 (usuario, 2026-11-13): las mejoras del código preparan una rama con git y corren las pruebas; el programa
#: instalado no trae ni git ni el código fuente, y no se entregan.
MENSAJE_SOLO_DESARROLLO = ('Las mejoras del código solo funcionan en el entorno de desarrollo, donde están el código '
                           'fuente y sus pruebas. En esta instalación no se preparan; lo demás, también entrenar, sigue '
                           'disponible.')


class SoloDesarrollo(RuntimeError):
    """Una función que necesita el repositorio, pedida en el programa instalado (086:RF-15)."""

_ESPACIO = r'^/api/workspaces/[^/]+'


@dataclass(frozen=True)
class Beta:
    clave: str
    nombre: str
    aviso: str
    rutas: tuple[str, ...]


_BETAS = (
    Beta('asistente', 'Asistente de órdenes',
         'En beta: el asistente puede entender mal una orden. Revise cada plan antes de confirmarlo.',
         (rf'{_ESPACIO}/(asistente|agente)(/|$)', r'^/api/asistente(/|$)',
          r'^/api/modelos/(asistente|clasificador)/volver$')),
    Beta('set_nueva', 'SET nueva',
         'En beta: el diseño de una SET nueva lo tiene que revisar un ingeniero antes de usarlo.',
         (rf'{_ESPACIO}/pf/obras/(set-nueva|con-proyecto)(/|$)',)),
    Beta('pide', 'Planificación PIDE',
         'En beta: es un diagnóstico y un borrador de los formatos; revíselos antes de presentarlos.',
         (rf'{_ESPACIO}/pide(/|$)',)),
    Beta('confiabilidad', 'Confiabilidad',
         'En beta: sus cifras dependen del libro de la empresa; revíselas antes de usarlas.',
         (rf'{_ESPACIO}/pf/datos-empresa(/|$)',)),
)
_RUTAS_BETA = {b.clave: tuple(re.compile(p) for p in b.rutas) for b in _BETAS}


def es_instalado() -> bool:
    """Si corre el programa instalado: lo dice su carpeta, como en ``es_edicion_producto`` (M-3), nunca la variable."""
    return es_programa_instalado(raiz_programa())


def exigir_desarrollo() -> None:
    """086:RF-15: lo que necesita git o el código fuente avisa en el instalado, antes de tocar git o la red."""
    if es_instalado():
        raise SoloDesarrollo(MENSAJE_SOLO_DESARROLLO)


def es_edicion_producto() -> bool:
    """Si esto es la edición de producto. Un programa instalado lo es siempre; en el árbol, solo si la variable lo dice.

    ``CSG_EDICION`` solo puede forzar «producto» (086:RF-22): con «desarrollo», un programa instalado encendía por
    defecto las salidas a la red, y los datos del cliente salían de su equipo. Abrirlo sin el lanzador
    (``python -m convertersmartgrid.web``) tampoco cambia la edición.
    """
    if es_instalado():
        return True
    return os.environ.get(VARIABLE_EDICION, '').strip().lower() == 'producto'


def _betas_apagadas() -> frozenset[str]:
    return frozenset(c.strip().lower() for c in os.environ.get(VARIABLE_BETA_APAGADAS, '').split(',') if c.strip())


def motivo_ruta_negada(ruta: str) -> str | None:
    """Por qué esta ruta no se atiende: solo si es de una beta que el operador apagó en el producto; si no, None."""
    if not es_edicion_producto():
        return None
    for clave in _betas_apagadas():
        if any(p.search(ruta) for p in _RUTAS_BETA.get(clave, ())):
            return MENSAJE_BETA_APAGADA
    return None


def estado_edicion() -> dict:
    """Lo que la web necesita para marcar cada beta; en desarrollo no marca nada."""
    if not es_edicion_producto():
        return {'producto': False, 'beta': []}
    apagadas = _betas_apagadas()
    return {'producto': True, 'beta': [{'clave': b.clave, 'nombre': b.nombre, 'aviso': b.aviso,
                                        'activa': b.clave not in apagadas} for b in _BETAS]}
