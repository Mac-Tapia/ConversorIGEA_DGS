"""Lo que cada tarea del asistente necesita del espacio, antes de ofrecer confirmar (spec 070).

Varias tareas fallaban después de que el operador confirmara, o quedaban a medias en silencio: los estudios
sin su base, el sistema sin la carpeta de los libros, la escalera sin cómo costear. Aquí se comprueba con lo que
la web ya sabe, y lo que no está va a ``plan.faltan``: nunca se deduce ni se inventa un valor.

Es un módulo aparte de ``services.py``, que comparten varias sesiones; las rutas y sus validaciones siguen
siendo las de allí (026:RF-10).
"""
from __future__ import annotations

import re
from typing import Any

from ..asistente.sinteticos import normalizar
from . import services

_TIPO_CAMBIO = re.compile(r'tipo de cambio\s*(?:de|:|=)?\s*(\d+(?:[.,]\d+)?)')
_DIRECTO = re.compile(r'\bdirect[oa]\b.*\bset nueva\b|\bset nueva\b.*\bdirect[oa]\b|\bsin (?:probar )?escalera\b')


def tipo_de_cambio_de(texto: str) -> float | None:
    """El que escribe el operador (025:RF-67): la forma decimal no la puede dar ``numero_de``."""
    m = _TIPO_CAMBIO.search(normalizar(texto))
    return float(m.group(1).replace(',', '.')) if m else None


def parametros_de_costeo(tipo_cambio: float | None) -> None:
    """Lo mismo que comprueba la escalera antes de tocar DIgSILENT (025:RF-57, RF-67, RF-68)."""
    from .. import escalera_optima as eo
    from ..perfil_empresa import PerfilError, datos_perfil

    try:
        eo.parametros(datos_perfil(), tipo_cambio)
    except (eo.EscaleraError, PerfilError) as exc:
        raise services.UserError(str(exc)) from exc


def _exige_calibracion(ws, plan) -> None:
    proyecto = plan.datos.get('proyecto')
    if proyecto and services.ajuste_aplicado_en_disco(ws, proyecto) is None:
        plan.faltan.append(f'la calibración: {proyecto} no tiene ninguna aplicada en este espacio; calíbrelo antes.')


def _estudio_nombrado(ws, plan) -> None:
    pedido = plan.datos.get('estudio')
    if not pedido:
        return
    catalogo = services.estudios_catalogo(ws, plan.datos.get('proyecto') or '')
    clave = normalizar(str(pedido)).strip()

    def coincide(fila: dict) -> bool:
        return clave in (normalizar(str(fila.get('clave'))), normalizar(str(fila.get('nombre'))))

    ofrecido = next((e for e in catalogo.get('ofrecidos') or [] if coincide(e)), None)
    if ofrecido is not None:
        plan.datos['estudio'] = ofrecido['clave']
        return
    negado = next((e for e in catalogo.get('no_ofrecidos') or [] if coincide(e)), None)
    plan.faltan.append(f"el estudio {pedido}: {negado['motivo']}" if negado else
                       f'el estudio {pedido}: no está en el catálogo de esta versión.')


def _libros_de_la_demanda(ws, plan) -> None:
    if plan.datos.get('ruta'):
        return
    carpeta = services.carpeta_de_libros(ws)
    if carpeta is None:
        plan.faltan.append('la carpeta de los libros de demanda: dígala en la orden o asígnelos en «2.1».')
        return
    plan.datos['ruta'] = carpeta
    plan.razonamiento.append(f'libros de demanda: los del espacio, en {carpeta} (070:RF-6).')


def _obras(ws, plan, extras: dict) -> None:
    tipo_cambio = tipo_de_cambio_de(plan.texto)
    if tipo_cambio:
        extras['tipo_cambio'] = tipo_cambio
    if plan.tarea == 'optimizar_con_proyecto' and _DIRECTO.search(normalizar(plan.texto)):
        extras['directo_set_nueva'] = True
        if not plan.datos.get('ruta'):
            plan.faltan.append('el libro CAPEX: la SET nueva se elige entre sus módulos (042:RF-7).')
    try:
        parametros_de_costeo(tipo_cambio)
    except services.UserError as exc:
        plan.faltan.append(f'cómo costear las obras: {exc}')


def _factibilidad(plan, extras: dict) -> None:
    formulario = extras.get('formulario') or {}
    if formulario and not formulario.get('solicitud'):
        plan.faltan.append('la solicitud de la carga en el formulario del informe: rellénela en el paso 4.4.')


def requisitos(ws, plan, extras: dict) -> None:
    """Completa el plan con lo que el espacio resuelve y dice lo que falta (070:RF-2 a RF-15)."""
    tarea: Any = plan.tarea
    if tarea == 'estudios':
        _exige_calibracion(ws, plan)
        _estudio_nombrado(ws, plan)
    elif tarea == 'cargas_nuevas':
        _exige_calibracion(ws, plan)
    elif tarea == 'sistema_completo':
        _libros_de_la_demanda(ws, plan)
    elif tarea in ('obras_escalera', 'optimizar_con_proyecto'):
        _obras(ws, plan, extras)
    elif tarea == 'informe_factibilidad':
        _factibilidad(plan, extras)
