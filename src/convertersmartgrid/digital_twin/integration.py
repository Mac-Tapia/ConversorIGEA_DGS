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
from .contratos_fisicos import contexto_fisico
from .episode import Caso, Clase, EpisodioInvalido
from .evaluacion import Limites, limites_del_sistema

#: Aviso del Registro cuando un episodio no se pudo capturar entero.
AVISO_CUARENTENA = 'AVISO DIGITAL_TWIN_QUARANTINE'

#: ``0`` apaga la captura; las pruebas de la web la apagan para no ver un proceso de más,
#: como aíslan el turno de DIgSILENT (spec 019). Sin la variable, la captura está activa.
VARIABLE_CAPTURA = 'CSG_TWIN_CAPTURA'

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
    normas = []
    for f in feeders:
        a = estructura.alimentador(f)                                     # 022:RF-81
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


#: 044:RF-6: diferencias admitidas entre lo que predijo el oráculo y lo que mide DIgSILENT al aceptar una
#: alternativa. No son de una empresa: son la precisión que se exige al gemelo (0,003 p.u. medida en el
#: arranque de la 052). El perfil puede dar otras en ``gemelo.aceptacion``.
TOLERANCIAS_ACEPTACION = {'tolerancia_v_pu': 0.01, 'tolerancia_perdidas': 0.2, 'tolerancia_perdidas_kw': None}


def _contexto_experimento(origen: Mapping[str, Any], project: Any, feeders: Iterable[Any], caso: Mapping[str, Any],
                          fisico: Mapping[str, Any], base: Mapping[str, Any]):
    from ..experimentos import ContextoExperimento

    try:
        return ContextoExperimento(
            source_run_id=origen.get('source_run_id'), source_mode=origen.get('source_mode'),
            source_fingerprint=origen.get('source_fingerprint'), project=str(project or '').strip(),
            feeders=tuple(sorted(str(f) for f in feeders)), case_id=caso.get('id'), case_role=caso.get('rol'),
            year=base.get('year'), period=base.get('period'), criterio_fijas=base.get('criterio_fijas'),
            profile_hash=base.get('profile_hash'), topology_hash=fisico.get('topology_hash'),
            controls_hash=fisico.get('controls_hash'), scenario_hash=fisico.get('scenario_hash'))
    except (TypeError, ValueError):
        return None


def contexto_de_lectura(lectura: Mapping[str, Any] | None, base: Mapping[str, Any], *, esperado: bool = False):
    """El ``ContextoExperimento`` de una lectura nativa tras reabrir (044:RF-7); ``None`` si le falta algo.

    Con ``esperado``, proyecto, alimentadores y fuente son los del contexto firmado de la acción, y el caso, el
    pedido: así se nota una lectura de otro proyecto, otros alimentadores u otro caso. Topología, controles y
    escenario solo los da DIgSILENT tras aplicar: no hay otra predicción de ellos.
    """
    if not isinstance(lectura, Mapping):
        return None
    fisico = contexto_fisico(lectura)
    if 'ausente' in fisico:
        return None
    firmado = base.get('native_action_context') or {}
    caso = dict(lectura.get('caso_nativo') or {})
    if esperado:
        caso['rol'] = base.get('case_role')
        return _contexto_experimento(firmado.get('source') or {}, firmado.get('project'), firmado.get('feeders') or (),
                                     caso, fisico, base)
    return _contexto_experimento(firmado.get('source') or {}, lectura.get('project'), lectura.get('feeders') or (),
                                 caso, fisico, base)


def _flujo_de_media(lectura: Mapping[str, Any], kv_min: float) -> dict[str, Any] | None:
    """El flujo leído con las tensiones de las barras de media, las que juzga el oráculo de la 052.

    Con las de baja de cada SED, la mínima de DIgSILENT no sería la misma magnitud que la del oráculo.
    """
    flujo = lectura.get('flujo')
    if not isinstance(flujo, Mapping):
        return None
    barras = (lectura.get('topologia') or {}).get('barras') or {}
    tensiones = dict(flujo.get('tensiones') or {})
    valores = {b: v for b, v in (tensiones.get('valores') or {}).items()
               if float((barras.get(b) or {}).get('kv') or 0.0) >= kv_min}
    return {**flujo, 'tensiones': {**tensiones, 'valores': valores}}


def medicion_de_lecturas(con: Mapping[str, Any] | None, sin: Mapping[str, Any] | None, base: Mapping[str, Any], *,
                         aplicadas: Iterable[str], kv_min: float) -> dict[str, Any]:
    """La medición nativa que exige ``validar_medicion_nativa`` (044:RF-6, RF-7), de dos lecturas tras reabrir:
    la del caso con la alternativa aplicada y la de su referencia, «Sin proyecto»."""
    from ..evaluacion_modelos import UNIDADES_NATIVAS

    con = con if isinstance(con, Mapping) and not con.get('error') else {}
    sin = sin if isinstance(sin, Mapping) and not sin.get('error') else {}
    flujo = _flujo_de_media(con, kv_min) if con else None
    tensiones = list(((flujo or {}).get('tensiones') or {}).get('valores', {}).values())
    perdidas = (((flujo or {}).get('perdidas') or {}).get('valores') or {}).get('total')
    activas = set((con.get('topologia') or {}).get('variaciones_activas') or ())
    return {'converge': flujo is not None, 'v_min': min(tensiones) if tensiones else None, 'perdidas_kw': perdidas,
            'contexto': contexto_de_lectura(con, base), 'unidades': dict(UNIDADES_NATIVAS), 'flujo': flujo,
            'reabierto': con.get('reopen_verified') is True,
            # Una obra que tras reabrir ya no está activa no es la que se acepta.
            'revertido': not set(aplicadas) <= activas,
            'referencia': {'contexto': contexto_de_lectura(sin, base), 'flujo': _flujo_de_media(sin, kv_min) if sin else None,
                           'reabierto': sin.get('reopen_verified') is True},
            'avisos': list(con.get('avisos') or []) + list(sin.get('avisos') or [])}


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
        # 045:RF-1, RF-3: el caso del año, el año y el criterio de las fijas, si los hay; nunca supuestos.
        **{k: plan[k] for k in ('anio_casos', 'periodo', 'criterio_fijas') if plan.get(k) is not None},
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
