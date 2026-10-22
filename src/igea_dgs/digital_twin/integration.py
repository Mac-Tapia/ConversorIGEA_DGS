"""Registro automático de episodios tras cada acción nativa (spec 024, T6).

Un solo punto de entrada para la web: cuando una acción en DIgSILENT termina (flujo,
verificación, ajuste, cargas, obras, estudios, transferencia, guiones), se lee el proyecto
en una sesión nueva, se arma el episodio y se guarda en el búfer. Si algo falla aquí, la
acción ya hecha no se repite ni se deshace: se avisa en el Registro y se sigue (RF-1).
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .buffer import BuferEpisodios, Consulta
from .capture import CapturaImposible, artefacto_de, construir_episodio
from .episode import Caso, Clase, EpisodioInvalido
from .evaluacion import Limites, limites_del_sistema

#: Aviso del Registro cuando un episodio no se pudo capturar entero.
AVISO_CUARENTENA = 'AVISO DIGITAL_TWIN_QUARANTINE'

#: ``0`` apaga la captura; las pruebas de la web la apagan para no ver un proceso de más,
#: como aíslan el turno de DIgSILENT (spec 019). Sin la variable, la captura está activa.
VARIABLE_CAPTURA = 'IGEA_TWIN_CAPTURA'

#: Clase de obra de la spec 011 → alternativa del PIDE (RF-32). El reconectador y la
#: consigna de cabecera no son alternativas de inversión de la tabla: no entran.
ALTERNATIVA_DE_OBRA = {'condensador': 'bancos', 'regulador': 'reguladores',
                       'seccion': 'cambio_seccion', 'terna': 'nueva_terna',
                       'enlace': 'refuerzo_red', 'migracion': 'refuerzo_red',
                       'tension': 'refuerzo_red'}


def captura_activa() -> bool:
    return os.environ.get(VARIABLE_CAPTURA, '1').strip() != '0'


def obras_pide(obras: Iterable[Mapping[str, Any]],
               filas: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Las obras creadas, con su alternativa del PIDE y su variación como elemento.

    ``obras`` son las del plan, en orden; ``filas``, lo que informó el guion (``obra`` es
    el número de la obra, desde 1). Las que fallaron o no son inversión del PIDE no entran.
    """
    obras = list(obras)
    out = []
    for fila in filas:
        n = int(fila.get('obra') or 0)
        if not 1 <= n <= len(obras) or fila.get('error') or not fila.get('variacion'):
            continue
        alternativa = ALTERNATIVA_DE_OBRA.get(str(obras[n - 1].get('clase')))
        if alternativa:
            out.append({'alternativa': alternativa, 'elemento': str(fila['variacion']),
                        'coste': None, 'van': None, 'tir': None, 'retorno_anios': None})
    return out


def normas_de(estructura: Any, feeders: Iterable[str]) -> list[str | None]:
    """Norma de calidad del sistema eléctrico de cada alimentador, según la estructura."""
    if estructura is None:
        return [None]
    from ..estructura import clave

    normas = []
    for f in feeders:
        a = estructura.alimentadores.get(clave(f))
        sistema = estructura.sistemas.get(a.sistema) if a is not None else None
        normas.append((sistema.norma or None) if sistema is not None else None)
    return normas or [None]


def limites_combinados(perfil: Mapping[str, Any], normas: Iterable[str | None]) -> Limites | None:
    """Los límites más estrictos de las normas de los alimentadores del episodio.

    Un enlace entre un sistema urbano (NTCSE) y uno rural (NTCSER) tiene que cumplir las
    dos; si falta en el perfil la tolerancia de alguna, no hay límites (P13).
    """
    leidos = [limites_del_sistema(dict(perfil), n) for n in dict.fromkeys(normas)]
    todos = [lim for lim in leidos if lim is not None]
    if not todos or len(todos) != len(leidos):
        return None
    if len(todos) == 1:
        return todos[0]
    trafos = [t for lim in todos if (t := lim.transformador_max_pct) is not None]
    return Limites('+'.join(lim.norma for lim in todos),
                   max(lim.tension_min_pu for lim in todos),
                   min(lim.tension_max_pu for lim in todos),
                   min(lim.cargabilidad_max_pct for lim in todos),
                   min(trafos) if trafos else None)


def plan_de_lectura(plan: Mapping[str, Any], caso: Caso,
                    informe: Mapping[str, Any]) -> dict[str, Any]:
    """El plan del guion de lectura: el mismo proyecto, alimentadores y contexto firmado."""
    return {
        'project': plan.get('project'), 'folder': plan.get('folder'),
        'feeders': list(plan.get('feeders') or ([plan['feeder']] if plan.get('feeder') else [])),
        'case': caso.value,
        'variaciones_esperadas': list(informe.get('variaciones_creadas') or []),
        'huellas_gps_de': sorted(plan.get('huellas_gps_esperadas') or {}),
        'native_action_context': plan.get('native_action_context'),
    }


def capturar_accion(plan: Mapping[str, Any], informe: Mapping[str, Any], *, caso: Caso,
                    rutas: Mapping[str, Path], base: Path,
                    leer: Callable[[dict[str, Any]], Mapping[str, Any] | None],
                    perfil: Mapping[str, Any], estructura: Any,
                    bufer: BuferEpisodios | None = None,
                    log: Callable[[str], None] = lambda _m: None,
                    manual: bool = False) -> dict[str, Any] | None:
    """Arma y guarda el episodio de una acción nativa ya terminada.

    ``leer`` ejecuta la lectura nativa con el plan que se le da y devuelve la lectura, o
    ``None`` si no se pudo. Devuelve lo que la web añade al resultado de la acción
    (``digital_twin_episode``), o ``None`` si el plan no trae contexto firmado.
    """
    if not plan.get('native_action_context'):
        return None
    try:
        bufer = bufer or BuferEpisodios()
        artefactos = [artefacto_de(ruta, rol, base) for rol, ruta in sorted(rutas.items())
                      if ruta is not None and Path(ruta).is_file()]
        try:
            lectura = leer(plan_de_lectura(plan, caso, informe))
        except Exception as exc:  # noqa: BLE001 - sin lectura el episodio va a cuarentena
            log(f'{AVISO_CUARENTENA}: la lectura nativa falló: {exc}')
            lectura = None
        if lectura is not None and (lectura.get('error') or lectura.get('status') == 'BLOQUEADO_DATOS'):
            log(f"{AVISO_CUARENTENA}: {lectura.get('error')}")
            lectura = None
        feeders = list(plan.get('feeders') or [])
        referencia = None
        if caso is Caso.CON_PROYECTO:
            previos = bufer.consultar(Consulta(proyecto=str(plan.get('project')),
                                               caso=Caso.SIN_PROYECTO.value,
                                               clase=Clase.ACCEPTED.value))
            referencia = previos[-1].flujo if previos else None
        cuadra = informe.get('cuadrado') if caso is Caso.SIN_PROYECTO else None
        episodio = construir_episodio(
            plan, informe, lectura, artefactos, caso=caso,
            limites=limites_combinados(perfil, normas_de(estructura, feeders)),
            referencia=referencia,
            calibracion_cuadra=None if cuadra is None else bool(cuadra),
            creado=datetime.now(UTC).isoformat(timespec='seconds'), manual=manual)
        bufer.guardar(episodio)
    except (CapturaImposible, EpisodioInvalido, OSError, ValueError) as exc:
        log(f'{AVISO_CUARENTENA}: {exc}')
        return {'error': str(exc)}
    if episodio.clase is Clase.QUARANTINE:
        log(f"{AVISO_CUARENTENA}: {'; '.join(episodio.aceptacion.get('bloqueos') or [])}")
    return {'episode_id': episodio.episode_id, 'clase': episodio.clase.value,
            'caso': episodio.caso.value, 'bloqueos': list(episodio.aceptacion.get('bloqueos') or []),
            'violaciones': list(episodio.aceptacion.get('violaciones') or [])}
