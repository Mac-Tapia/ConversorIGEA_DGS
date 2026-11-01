"""Evaluación del episodio por caso y norma (spec 024, T3).

Lo que se mide es igual en los tres casos (RF-28); lo que se exige cambia (RF-29 a RF-31).
El «Caso base» es la red tal como está y «Sin proyecto» su calibración con lo que hizo el
operador: una subtensión ahí es un hecho de la red real, que el gemelo tiene que aprender,
no un error. Solo «Con proyecto» se juzga contra la norma, porque es donde se proponen las
obras. En IN111–TA225 el flujo convergió tras reabrir con 0,8683 p.u. en una barra: eso es
una obra que no cumple, y la convergencia no puede ocultarlo (RF-26).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .episode import Caso, Clase


@dataclass(frozen=True)
class Limites:
    """Límites de la norma de calidad de un sistema eléctrico, tomados del perfil (P13)."""

    norma: str
    tension_min_pu: float
    tension_max_pu: float
    cargabilidad_max_pct: float
    transformador_max_pct: float | None


@dataclass(frozen=True)
class Evaluacion:
    clase: Clase
    violaciones: tuple[str, ...] = ()
    diagnostico: tuple[str, ...] = ()
    bloqueos: tuple[str, ...] = field(default_factory=tuple)


def limites_del_sistema(perfil: dict[str, Any], norma: str | None) -> Limites | None:
    """Límites de ``norma`` en el perfil; ``None`` si el perfil no los trae.

    La norma por defecto del perfil (``informes.norma``) usa ``estudios``; cualquier otra
    (la NTCSER de los sistemas rurales) va en ``normas.<nombre>``. Sin ella no se supone un
    valor: el episodio que la necesite queda en cuarentena.
    """
    estudios = perfil.get('estudios') or {}
    principal = (perfil.get('informes') or {}).get('norma')
    norma = norma or principal
    if norma in (perfil.get('normas') or {}):
        propia = perfil['normas'][norma]
    elif norma == principal:
        propia = estudios
    else:
        return None
    try:
        vmin, vmax = float(propia['tension_min_pu']), float(propia['tension_max_pu'])
        carga = float(propia.get('cargabilidad_max_pct', estudios['cargabilidad_max_pct']))
    except (KeyError, TypeError, ValueError):
        return None
    trafo = ((perfil.get('calibracion') or {}).get('transformadores_sed') or {}).get('umbral_carga_pct')
    return Limites(str(norma), vmin, vmax, carga, float(trafo) if trafo is not None else None)


def _valores(flujo: dict, clave: str) -> dict | None:
    bloque = flujo.get(clave) or {}
    return None if 'ausente' in bloque else bloque.get('valores')


def _sin_tension(flujo: dict) -> list[str]:
    """Barras sin alimentación (islas sin fuente): no son subtensión, pero sí un problema."""
    barras = (flujo.get('tensiones') or {}).get('sin_tension') or []
    if not barras:
        return []
    ejemplos = ', '.join(str(b).rsplit('\\', 1)[-1] for b in barras[:3])
    return [f'{len(barras)} barra(s) sin tensión, en islas sin fuente (p. ej. {ejemplos})']


def _fuera_de_norma(flujo: dict, lim: Limites) -> list[str]:
    fuera = _sin_tension(flujo)
    for barra, v in sorted((_valores(flujo, 'tensiones') or {}).items()):
        if isinstance(v, int | float) and not lim.tension_min_pu <= v <= lim.tension_max_pu:
            fuera.append(f'tensión {v:.4f} p.u. en {barra} fuera de {lim.tension_min_pu}–'
                         f'{lim.tension_max_pu} ({lim.norma})')
    carga = _valores(flujo, 'cargabilidad') or {}
    lineas = carga.get('lineas', {k: v for k, v in carga.items() if isinstance(v, int | float)})
    for elemento, pct in sorted(lineas.items()):
        if pct > lim.cargabilidad_max_pct:
            fuera.append(f'cargabilidad {pct:.1f} % en {elemento} sobre {lim.cargabilidad_max_pct:g} %')
    if lim.transformador_max_pct is not None:
        for elemento, pct in sorted((carga.get('transformadores') or {}).items()):
            if pct > lim.transformador_max_pct:
                fuera.append(f'transformador {elemento} al {pct:.1f} %, sobre el '
                             f'{lim.transformador_max_pct:g} % de la NTP 370.400')
    return fuera


def _peor_que_sin_proyecto(flujo: dict, ref: dict) -> tuple[list[str], list[str]]:
    """Pérdidas e índices de confiabilidad frente a «Sin proyecto» (RF-31)."""
    peores, notas = [], []
    total, total_ref = ((_valores(f, 'perdidas') or {}).get('total') for f in (flujo, ref))
    if total is not None and total_ref is not None and total > total_ref:
        peores.append(f'pérdidas {total:g} kW frente a {total_ref:g} kW en «Sin proyecto»')
    conf, conf_ref = _valores(flujo, 'confiabilidad'), _valores(ref, 'confiabilidad')
    if conf is None or conf_ref is None:
        notas.append('confiabilidad no evaluada: falta el índice en este caso o en «Sin proyecto»')
    else:
        for indice in sorted(set(conf) & set(conf_ref)):
            if conf[indice] > conf_ref[indice]:
                peores.append(f'{indice} {conf[indice]:g} frente a {conf_ref[indice]:g} en «Sin proyecto»')
    return peores, notas


def evaluar(caso: Caso, flujo: dict[str, Any], *, convergio: bool, revertido: bool,
            reabierto: bool, limites: Limites | None, calibracion_cuadra: bool | None,
            referencia: dict[str, Any] | None, manual: bool = False) -> Evaluacion:
    """Clase del episodio según su caso (RF-4, RF-5, RF-29 a RF-31).

    ``referencia`` es el flujo del último «Sin proyecto» aceptado del mismo proyecto; solo
    lo usa «Con proyecto». ``calibracion_cuadra`` es ``None`` si no hay medida con qué
    comprobarla.
    """
    if revertido:
        return Evaluacion(Clase.REJECTED, bloqueos=('acción revertida',))
    if not convergio:
        return Evaluacion(Clase.REJECTED, bloqueos=('el flujo no convergió',))
    if not reabierto:
        return Evaluacion(Clase.QUARANTINE,
                          bloqueos=('sin reabrir y releer el proyecto en una sesión nueva',))

    fuera = _fuera_de_norma(flujo, limites) if limites else _sin_tension(flujo)
    if caso is not Caso.CON_PROYECTO:
        diagnostico = list(fuera)
        if limites is None:
            diagnostico.append('sin límites de la norma de este sistema en el perfil: '
                               'diagnóstico sin comprobar la norma')
        if manual:
            diagnostico.append('incluye cambios manuales del operador, aceptados como intencionales')
        if caso is Caso.SIN_PROYECTO:
            if calibracion_cuadra is False:
                return Evaluacion(Clase.REJECTED, diagnostico=tuple(diagnostico),
                                  bloqueos=('la calibración no cuadra con la medida',))
            if calibracion_cuadra is None:
                return Evaluacion(Clase.QUARANTINE, diagnostico=tuple(diagnostico),
                                  bloqueos=('sin medida para comprobar la calibración',))
        return Evaluacion(Clase.ACCEPTED, diagnostico=tuple(diagnostico))

    if limites is None:
        return Evaluacion(Clase.QUARANTINE, bloqueos=(
            'faltan en el perfil los límites de la norma de este sistema (p. ej. la NTCSER)',))
    if referencia is None:
        # Para saber que una obra incumple la norma no hace falta «Sin proyecto»; para
        # aceptarla, sí: pérdidas y confiabilidad se comparan con él.
        if fuera:
            return Evaluacion(Clase.CONVERGED_WITH_VIOLATIONS, violaciones=tuple(fuera),
                              diagnostico=(('pérdidas y confiabilidad sin comparar: falta '
                                            '«Sin proyecto» de referencia'),))
        return Evaluacion(Clase.QUARANTINE, bloqueos=(
            'falta un «Sin proyecto» aceptado del mismo proyecto para comparar',))
    peores, notas = _peor_que_sin_proyecto(flujo, referencia)
    violaciones = tuple(fuera + peores)
    clase = Clase.CONVERGED_WITH_VIOLATIONS if violaciones else Clase.ACCEPTED
    return Evaluacion(clase, violaciones=violaciones, diagnostico=tuple(notas))
