"""Matriz estudio × motor: con qué motor está validado cada estudio que ofrece la web (spec 100, RF-8 a RF-12).

Por qué. Hasta el 2026-11-19 la web ofrecía cada estudio como si estuviera listo, también los que solo tenían código
y ninguna corrida de aceptación (el cortocircuito y la fiabilidad de la 012, el PIT de la 107). Un software
comercial dice con qué motor ha comprobado cada cálculo (Plan Maestro PM-20). Aquí se declara, para cada estudio y
cada motor, o bien la evidencia que lo sostiene (las specs cuyo cierre lo prueba), o bien que ese motor no lo
calcula y por qué. El estado no se escribe a mano: «validado» solo si TODAS las specs de su evidencia están
cumplidas; cualquier otra cosa, o no poder leerlas, es «sin validar». Así una spec que se reabre o una instalación
sin la carpeta ``specs/`` nunca enseña un estudio como validado.

Este módulo es puro: quien sirve la matriz le pasa cómo leer el estado de una spec por su número.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

#: Los tres estados que ve el operador.
ESTADOS = ('validado', 'sin_validar', 'no_disponible')
#: El estado de spec que cierra una evidencia (033).
CERRADA = 'cumplida'
#: De dónde salen los estados: la carpeta ``specs/`` del repositorio, el recurso que viaja en la entrega
#: (``recursos/estado_specs.json``, que la excluye) o ninguno de los dos.
ORIGENES = ('specs', 'recurso', 'ninguno')


@dataclass(frozen=True)
class Motor:
    clave: str
    nombre: str


#: En el orden de las columnas. ``abierto``: el oráculo físico con los motores de ``motores_flujo`` (Z-bus, Newton,
#: power-grid-model, OpenDSS) y pandapower. ``pinn``: el gemelo aprendido. ``conversor``: cálculo propio, sin motor
#: eléctrico (costos, inventario, pronóstico).
MOTORES = (Motor('digsilent', 'DIgSILENT'), Motor('abierto', 'Motores abiertos'), Motor('pinn', 'Oráculo PINN'),
           Motor('conversor', 'Cálculo del conversor'))


@dataclass(frozen=True)
class Evidencia:
    """Las specs cuyo cierre prueba ese estudio con ese motor."""
    specs: tuple[str, ...]


@dataclass(frozen=True)
class NoDisponible:
    """Ese motor no calcula ese estudio; ``motivo`` es para el operador."""
    motivo: str


Celda = Evidencia | NoDisponible

NO_CALCULA = NoDisponible('Este motor no calcula este estudio.')
FUERA = NoDisponible('Fuera de esta versión.')
SIN_VALIDAR = 'Falta su prueba de aceptación con este motor.'


def _fila(nombre: str, **celdas: Celda) -> tuple[str, dict[str, Celda]]:
    desconocidos = set(celdas) - {m.clave for m in MOTORES}
    if desconocidos:
        raise ValueError(f'motor desconocido en la matriz: {sorted(desconocidos)}')
    return nombre, {m.clave: celdas.get(m.clave, NO_CALCULA) for m in MOTORES}


#: Specs con alguna tarea de DIgSILENT cerrada el 2026-11-08 por orden del usuario, sin corrida propia, con la nota
#: «su comprobación pasa a la aceptación automática (spec 100)». La 011, 042, 049, 052 y 087 están «cumplida», pero su
#: cierre no prueba el estudio: cada celda que cite una de ellas lleva también la 100, y no sale validada hasta que la
#: 100 se cumpla (su T4). La prueba comprueba que la lista sigue a las notas de las tareas.
ACEPTACION_EN_LA_100 = frozenset({'011', '012', '042', '045', '049', '052', '087'})
SPEC_ACEPTACION = '100'


def _e(*specs: str) -> Evidencia:
    if ACEPTACION_EN_LA_100 & set(specs) and SPEC_ACEPTACION not in specs:
        specs = (*specs, SPEC_ACEPTACION)
    return Evidencia(specs)


#: clave → (nombre, celdas). Las de «4.2 · Estudios» llevan la clave y el nombre del catálogo de la web
#: (``aplicacion.studies.ESTUDIOS``; la prueba comprueba que coinciden). El resto son los módulos de la web.
#: La 011 tiene el código de los estudios de su iteración, pero su aceptación en DIgSILENT pasó a la 100; la 012
#: tiene código y le falta su corrida (T17).
ESTUDIOS: Mapping[str, tuple[str, dict[str, Celda]]] = dict([
    ('flujo', _fila('Flujo de potencia', digsilent=_e('011'), abierto=_e('082', '083'), pinn=_e('024', '045'))),
    ('flujo_desequilibrado', _fila('Flujo de potencia desequilibrado', digsilent=_e('011'), abierto=_e('082'))),
    ('cortocircuito', _fila('Cortocircuito', digsilent=_e('012'),
                            abierto=NoDisponible('Sin motor abierto de cortocircuito en esta versión.'))),
    ('contingencias', _fila('Contingencias N-1', digsilent=_e('011'))),
    ('fiabilidad', _fila('Fiabilidad (SAIDI, SAIFI, ENS)', digsilent=_e('012'))),
    ('reconectadores', _fila('Ubicación óptima de reconectadores', digsilent=_e('012'))),
    ('alojamiento', _fila('Capacidad de alojamiento', digsilent=_e('012'))),
    ('curvas_pv', _fila('Curvas PV', digsilent=_e('012'))),
    ('cuasi_dinamica', _fila('Simulación cuasi-dinámica', digsilent=_e('012'))),
    ('troncal', _fila('Cálculo de troncal', digsilent=_e('011'))),
    ('punto_apertura', _fila('Punto de apertura óptimo', digsilent=_e('011'))),
    ('condensadores', _fila('Colocación óptima de condensadores', digsilent=_e('012'))),
    ('balance_fases', _fila('Balance de fases', digsilent=_e('011'))),
    ('perfil_tension', _fila('Optimización del perfil de tensión', digsilent=_e('011'))),
    ('flujo_optimo', _fila('Flujo óptimo de potencia', digsilent=FUERA, abierto=FUERA)),
    ('economico', _fila('Evaluación técnico-económica', digsilent=FUERA)),
    ('comparacion', _fila('Comparación de alternativas', digsilent=FUERA)),
    ('protecciones', _fila('Coordinación de protecciones', digsilent=_e('049'))),
    ('armonicos', _fila('Flujo armónico', digsilent=FUERA)),
    # Los módulos de la web.
    ('calibracion', _fila('Calibración a la máxima de cabecera', digsilent=_e('006', '014', '083', '101'),
                          abierto=_e('057', '083'))),
    ('obras', _fila('Obras de mejora y optimización', digsilent=_e('042', '052', '087'), abierto=_e('052', '087'))),
    ('gemelo', _fila('Gemelo digital', pinn=_e('024', '045'))),
    ('pide', _fila('Plan de inversiones (PIDE)', digsilent=_e('030', '072'), pinn=_e('045', '072'))),
    ('largo_plazo', _fila('Planeamiento de largo plazo', digsilent=_e('072'))),
    ('pit', _fila('Plan de inversiones en transmisión (PIT)', digsilent=_e('107'), abierto=_e('107'))),
    ('vad', _fila('Estudio de costos del VAD', conversor=_e('108'))),
    ('vnr', _fila('Estudio VNR', conversor=_e('108'))),
    ('pronostico', _fila('Pronóstico de la demanda', conversor=_e('089'))),
])


def _fecha(iso: str) -> str:
    """«2026-11-28T…» → «28-11-2026», como escribe las fechas el operador."""
    partes = str(iso or '')[:10].split('-')
    return '-'.join(reversed(partes)) if len(partes) == 3 else str(iso or '')


def validado_por_aceptacion(aceptacion: Mapping[str, Any]) -> str:
    """100:RF-23: lo que dice la celda que valida el sello de la aceptación de la versión."""
    version = str(aceptacion.get('version') or '')
    return f'Validado por la aceptación de la versión {version[:12]} del {_fecha(aceptacion.get("fecha"))}.'


def _celda(motor: str, celda: Celda, estado_de: Callable[[str], str | None],
           aceptacion: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(celda, NoDisponible):
        return {'motor': motor, 'estado': 'no_disponible', 'motivo': celda.motivo, 'evidencia': []}
    evidencia = [{'spec': n, 'estado': estado_de(n)} for n in celda.specs]
    # 100:RF-21: con el sello de la versión que corre, la evidencia de la aceptación (la 100) vale por cumplida; las
    # demás specs siguen la regla de RF-9.
    cerrada = [x['estado'] == CERRADA or (x['spec'] == SPEC_ACEPTACION and aceptacion is not None) for x in evidencia]
    validado = bool(evidencia) and all(cerrada)
    por_sello = validado and any(x['spec'] == SPEC_ACEPTACION and x['estado'] != CERRADA for x in evidencia)
    motivo = validado_por_aceptacion(aceptacion) if por_sello else ('' if validado else SIN_VALIDAR)
    return {'motor': motor, 'estado': 'validado' if validado else 'sin_validar', 'motivo': motivo,
            'evidencia': evidencia}


def matriz(estado_de: Callable[[str], str | None], origen: str = 'specs',
           aceptacion: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """La matriz entera: los motores y, por estudio, una celda por motor con su estado, motivo y evidencia.

    ``estado_de``: la palabra de la línea ``Estado:`` de la spec de ese número, o ``None`` si no se puede leer.
    ``origen``: de dónde salen esos estados (``ORIGENES``), para que la respuesta lo diga (100:RF-13).
    ``aceptacion``: el sello aceptado de la versión que corre (``version`` y ``fecha``), o None (100:RF-21 a RF-23).
    Quien sirve la matriz decide que es de su versión: aquí no se compara nada.
    """
    if origen not in ORIGENES:
        raise ValueError(f'origen desconocido de los estados: {origen}')
    return {
        'origen': origen,
        'aceptacion': ({'version': str(aceptacion.get('version') or ''), 'fecha': str(aceptacion.get('fecha') or '')}
                       if aceptacion is not None else None),
        'motores': [{'clave': m.clave, 'nombre': m.nombre} for m in MOTORES],
        'estudios': [{'clave': clave, 'nombre': nombre,
                      'celdas': [_celda(m, c, estado_de, aceptacion) for m, c in celdas.items()]}
                     for clave, (nombre, celdas) in ESTUDIOS.items()],
    }
