"""Diagnóstico del área por año: caso base y N-1 de cada línea y transformador (107:RF-3, 107:RF-4).

La demanda de cada año sale de la proyección (``proyeccion_anual``: filas con ``alimentador``, ``anio_calendario``,
``p_kw`` y ``q_kvar``) y se lleva a la barra de carga de su SET con la correspondencia SET → alimentadores del perfil,
en una sola pasada por las filas (nada de recorrerlas por SET ni por año). Un año sin demanda proyectada no se
extrapola: queda nombrado. Los límites vienen del registro normativo o del perfil, sin valores por defecto; un límite
que no da ninguno de los dos es un error que lo nombra. El trabajo es cancelable entre años (P7).
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError
from .ambito import AreaPit
from .motores import ejecutar
from .red_area import RedArea
from .red_pandapower import ResultadoFlujo

__all__ = ['Diagnostico', 'agregar_demanda', 'diagnosticar', 'limites_del_estudio']

LIMITES = ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct')
#: Regla del registro que da cada límite y el factor que la lleva a la unidad del límite.
_REGLAS = {'tension_min_pu': ('pit.tension_min_pu', 1.0), 'tension_max_pu': ('pit.tension_max_pu', 1.0),
           'cargabilidad_max_pct': ('pit.factor_utilizacion_max', 100.0)}


def limites_del_estudio(registro: RegistroNormativo | None, perfil: Mapping[str, Any], fecha: str | None = None
                        ) -> dict[str, dict[str, Any]]:
    """Cada límite con su origen: la regla obligatoria del registro, si no el perfil (``pit.limites``), y si no la
    regla del registro como referencia, rotulada así (107:RF-8)."""
    propios = ((perfil.get('pit') or {}).get('limites') or {}) if isinstance(perfil, Mapping) else {}
    out = {}
    for limite in LIMITES:
        clave, factor = _REGLAS[limite]
        regla = None
        if registro is not None:
            try:
                regla = registro.regla(clave, fecha)
            except RegistroError:
                regla = None
        if regla is not None and regla.obligatoria:
            out[limite] = {'valor': float(regla.regla.valor) * factor, 'origen': 'registro', 'regla': clave,
                           'norma': regla.norma.acto, 'estado': regla.estado, 'obligatoria': True}
        elif propios.get(limite) is not None:
            out[limite] = {'valor': float(propios[limite]), 'origen': 'perfil', 'regla': f'pit.limites.{limite}',
                           'obligatoria': False}
        elif regla is not None:
            out[limite] = {'valor': float(regla.regla.valor) * factor, 'origen': 'registro_referencia',
                           'regla': clave, 'norma': regla.norma.acto, 'estado': regla.estado, 'obligatoria': False}
        else:
            raise PitError(f'falta el límite {limite}: ni el registro normativo ({clave}) ni el perfil '
                           f'(pit.limites.{limite}) lo dan, y el PIT no lo supone')
    return out


def agregar_demanda(area: AreaPit, red: RedArea, filas: Iterable[Mapping[str, Any]]
                    ) -> dict[int, dict[str, tuple[float, float]]]:
    """Año → barra de carga → (P MW, Q Mvar), sumando los alimentadores de cada SET del área."""
    barras = red.barras_de_carga()
    sin_barra = [s for s in area.set_alimentadores if s not in barras]
    if sin_barra:
        raise PitError(f'las SET {sin_barra} tienen alimentadores en el perfil y ninguna barra de carga en la red')
    barra_de = {a: barras[s] for s, alims in area.set_alimentadores.items() for a in alims}
    out: dict[int, dict[str, list[float]]] = {}
    for f in filas:
        barra = barra_de.get(str(f.get('alimentador')))
        if barra is None:
            continue
        pq = out.setdefault(int(f['anio_calendario']), {}).setdefault(barra, [0.0, 0.0])
        pq[0] += float(f['p_kw']) / 1000
        pq[1] += float(f.get('q_kvar') or 0.0) / 1000
    return {a: {b: (pq[0], pq[1]) for b, pq in sorted(por.items())} for a, por in sorted(out.items())}


@dataclass
class CasoDiagnostico:
    caso: str
    fuera: tuple[str, ...]
    converge: bool
    p_sin_servir_mw: float
    sin_tension: list[str]
    violaciones: list[dict[str, Any]]
    perdidas_mw: float | None


@dataclass
class AnioDiagnostico:
    anio: int
    demanda_mw: float
    base: CasoDiagnostico
    contingencias: list[CasoDiagnostico] = field(default_factory=list)


@dataclass
class Diagnostico:
    area: str
    motor: str
    limites: dict[str, dict[str, Any]]
    anios: list[AnioDiagnostico] = field(default_factory=list)
    sin_demanda: list[int] = field(default_factory=list)
    faltantes: list[dict[str, Any]] = field(default_factory=list)
    incompletos: list[str] = field(default_factory=list)
    cancelado: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return not (self.faltantes or self.incompletos or self.sin_demanda or self.cancelado)

    def como_dict(self) -> dict[str, Any]:
        return {**asdict(self), 'completo': self.completo}


def _violaciones(r: ResultadoFlujo, limites: Mapping[str, Mapping[str, Any]], incompletos: set[str]
                 ) -> list[dict[str, Any]]:
    out = []
    vmin, vmax = limites['tension_min_pu']['valor'], limites['tension_max_pu']['valor']
    cmax = limites['cargabilidad_max_pct']['valor']
    for barra, v in sorted(r.tensiones_pu.items()):
        if v < vmin or v > vmax:
            out.append({'elemento': barra, 'magnitud': 'tension_pu', 'valor': v,
                        'limite': vmin if v < vmin else vmax})
    for elemento, c in sorted(r.cargabilidad_pct.items()):
        if c > cmax:
            out.append({'elemento': elemento, 'magnitud': 'cargabilidad_pct', 'valor': c, 'limite': cmax,
                        'completo': elemento not in incompletos})
    for barra in r.sin_tension:
        out.append({'elemento': barra, 'magnitud': 'sin_tension', 'valor': None, 'limite': None})
    return out


def _caso(nombre: str, r: ResultadoFlujo, limites, incompletos) -> CasoDiagnostico:
    return CasoDiagnostico(nombre, r.fuera, r.converge, r.p_sin_servir_mw, list(r.sin_tension),
                           _violaciones(r, limites, incompletos) if r.converge else [], r.perdidas_mw)


def diagnosticar(area: AreaPit, red: RedArea, filas: Iterable[Mapping[str, Any]], anios: Iterable[int],
                 limites: Mapping[str, Mapping[str, Any]], *, motor: str = 'abierto',
                 cancel: threading.Event | None = None,
                 on_progress: Callable[[int, int, int], None] | None = None) -> Diagnostico:
    """El diagnóstico del horizonte ``anios`` (los da el estudio, nunca el código)."""
    faltan = [k for k in LIMITES if k not in limites]
    if faltan:
        raise PitError(f'faltan los límites {faltan} para el diagnóstico')
    demanda = agregar_demanda(area, red, filas)
    anios = sorted(set(int(a) for a in anios))
    diag = Diagnostico(area.codigo, motor, {k: dict(v) for k, v in limites.items()},
                       faltantes=list(red.faltantes), incompletos=list(red.incompletos), avisos=list(red.avisos))
    incompletos = set(red.incompletos)
    contingencias = [e['id'] for t in ('linea', 'trafo2', 'trafo3') for e in red.de_tipo(t)]
    for i, anio in enumerate(anios):
        if cancel is not None and cancel.is_set():
            diag.cancelado = True
            diag.avisos.append(f'cancelado antes del año {anio}: quedan sin diagnosticar {anios[i:]}')
            break
        cargas = demanda.get(anio)
        if not cargas:
            diag.sin_demanda.append(anio)
            diag.avisos.append(f'el año {anio} no tiene demanda proyectada en el área {area.codigo}: no se extrapola')
        else:
            base = ejecutar('flujo', red, cargas, motor=motor)['resultado']
            ad = AnioDiagnostico(anio, sum(p for p, _q in cargas.values()), _caso('base', base, limites, incompletos))
            for eid in contingencias:
                r = ejecutar('n_1', red, cargas, motor=motor, fuera=[eid])['resultado']
                ad.contingencias.append(_caso(f'N-1 {eid}', r, limites, incompletos))
            diag.anios.append(ad)
        if on_progress is not None:
            on_progress(i + 1, len(anios), anio)
    return diag
