"""Qué edición corre, y qué se entrega en la de producto (086:RF-15, RF-16, RF-22).

Una sola función para preguntarlo, para que lo que se oculta y las salidas a la red no acaben leyendo
dos variables distintas. El alcance de la 1.0 está aquí y en ningún otro sitio: el servidor niega estas
rutas y tareas, y la web solo pregunta en ``/api/health`` qué enseñar. Ocultar un botón sin negar su ruta
dejaba a cualquier petición entrenar un modelo en el equipo de un cliente.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

VARIABLE_EDICION = 'CSG_EDICION'
#: Las funciones en beta que esta instalación no quiere, separadas por comas (086, «desactivable»).
VARIABLE_BETA_APAGADAS = 'CSG_BETA_APAGADAS'

MENSAJE_FUERA_DE_ALCANCE = 'Esta función no forma parte de esta versión del programa.'
MENSAJE_BETA_APAGADA = 'Esta función está desactivada en esta instalación.'

_ESPACIO = r'^/api/workspaces/[^/]+'

#: Entrenar modelos, revisión por roles, gemelo (PINN, GRU, aprendizaje) y proponer mejoras, que corre pruebas.
_RUTAS_FUERA_DE_ALCANCE = tuple(re.compile(p) for p in (
    rf'{_ESPACIO}/digital-twin(/|$)',
    r'^/api/modelos/gemelo/volver$',
    rf'{_ESPACIO}/asistente/entrenar$',
    rf'{_ESPACIO}/asistente/[^/]+/revision$',
    r'^/api/(workspaces/[^/]+/)?asistente/equipo$',
    r'^/api/(workspaces/[^/]+/)?asistente/mejoras(/|$)',
    r'^/api/asistente/aceptacion$',
))

#: Lo mismo por el asistente. «pregunta» responde con el índice RAG del propio código, que no se entrega.
TAREAS_FUERA_DE_ALCANCE = frozenset({
    'episodios', 'evaluar_gemelo', 'gemelo_aprender', 'gemelo_entrenar', 'gemelo_temporal', 'pronostico',
    'entrenar_asistente', 'pregunta',
})


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


def es_edicion_producto() -> bool:
    """Si esto es la edición de producto. Sin la variable es desarrollo: el árbol de hoy no cambia."""
    return os.environ.get(VARIABLE_EDICION, '').strip().lower() == 'producto'


def _betas_apagadas() -> frozenset[str]:
    return frozenset(c.strip().lower() for c in os.environ.get(VARIABLE_BETA_APAGADAS, '').split(',') if c.strip())


def motivo_ruta_negada(ruta: str) -> str | None:
    """Por qué esta ruta no se atiende en la edición de producto; None si se atiende (o en desarrollo)."""
    if not es_edicion_producto():
        return None
    if any(p.search(ruta) for p in _RUTAS_FUERA_DE_ALCANCE):
        return MENSAJE_FUERA_DE_ALCANCE
    for clave in _betas_apagadas():
        if any(p.search(ruta) for p in _RUTAS_BETA.get(clave, ())):
            return MENSAJE_BETA_APAGADA
    return None


def tarea_fuera_de_alcance(tarea: str | None) -> bool:
    return es_edicion_producto() and tarea in TAREAS_FUERA_DE_ALCANCE


def estado_edicion() -> dict:
    """Lo que la web necesita para enseñar o marcar cada cosa; en desarrollo no marca nada."""
    if not es_edicion_producto():
        return {'producto': False, 'beta': []}
    apagadas = _betas_apagadas()
    return {'producto': True, 'beta': [{'clave': b.clave, 'nombre': b.nombre, 'aviso': b.aviso,
                                        'activa': b.clave not in apagadas} for b in _BETAS]}
