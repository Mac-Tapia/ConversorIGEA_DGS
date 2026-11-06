"""Tramo continuo de un problema mixto con Pyomo y un solucionador PNL, y elección top-k (spec 048, T3).

Con las discretas fijas (módulos, equipos, maniobras), lo que queda continuo (consignas, por
ejemplo) se resuelve con un solucionador PNL: Ipopt por omisión, o cualquiera de los de
``pyomo.contrib.solver`` que admita el modelo (HiGHS resuelve los cuadráticos convexos). Su
resultado es un punto **local** del tramo continuo: un MINLP no tiene óptimo global
garantizado por Ipopt (Pyomo e Ipopt lo documentan así), y el resultado lo dice siempre con
``alcance='local_continuo'`` y ``optimo_global=False`` (RF-4). Las discretas nunca se relajan:
se validan enteras y del catálogo y entran en el modelo como constantes.

Si falta Pyomo o el solucionador, el resultado es ``ERROR_ENTORNO`` para este candidato y nada
más: los algoritmos evolutivos no dependen de él. Ningún resultado se elige sin pasar por
``evolutivo.verificar_top_k`` (la verificación completa de la 044), con las ``TOP_K`` primeras
admisibles, en orden y de una en una (RF-7).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..experimentos import ContextoExperimento
from .evaluacion import Limites
from .evolutivo import verificar_top_k
from .problema_optimizacion import ProblemaOptimizacion, evaluar_vector, validar_vector

ALCANCE = 'local_continuo'
SOLVER = 'ipopt'
#: Candidatos que se verifican en DIgSILENT, en orden, antes de darse por vencido.
TOP_K = 3
#: Residuo máximo admitido en restricciones y cotas para dar por convergido el punto local.
RESIDUO_MAX = 1e-6


def _resultado(estado: str, motivo: str | None = None, **campos: Any) -> dict[str, Any]:
    base = {'estado': estado, 'alcance': ALCANCE, 'optimo_global': False, 'motivo': motivo, 'continuas': None,
            'requiere_verificacion_nativa': True}
    return {**base, **campos}


def _fijar_discretas(problema: ProblemaOptimizacion, discretas_fijas: Mapping[str, Any]) -> dict[str, Any]:
    """Las discretas validadas (enteras y del dominio); ``ValueError`` si falta o sobra alguna."""
    discretas = [v.nombre for v in problema.variables if v.discreta]
    continuas = {v.nombre for v in problema.variables if not v.discreta}
    if sobran := sorted(k for k in discretas_fijas if k in continuas):
        raise ValueError(f'una variable continua no se fija como discreta: {", ".join(sobran)}')
    if faltan := [n for n in discretas if n not in discretas_fijas]:
        raise ValueError(f'falta fijar la discreta: {", ".join(faltan)}')
    if extra := sorted(str(k) for k in discretas_fijas if k not in set(discretas)):
        raise ValueError(f'variable desconocida: {", ".join(extra)}')
    # Se validan con el mismo dominio que cualquier vector: un 1,5 no se redondea (048:RF-2).
    medio = {v.nombre: (v.inferior + v.superior) / 2 for v in problema.variables if not v.discreta}
    canonico = validar_vector(problema, {**medio, **discretas_fijas})
    return {n: canonico[n] for n in discretas}


def _iniciales(problema: ProblemaOptimizacion, dadas: Mapping[str, Any] | None) -> dict[str, float]:
    iniciales = {}
    for v in problema.variables:
        if v.discreta:
            continue
        x = (dadas or {}).get(v.nombre, (v.inferior + v.superior) / 2)
        if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) \
                or not v.inferior <= x <= v.superior:
            raise ValueError(f'valor inicial de {v.nombre} fuera de [{v.inferior}, {v.superior}]: {x!r}')
        iniciales[v.nombre] = float(x)
    return iniciales


def resolver_continuo(problema: ProblemaOptimizacion, *, discretas_fijas: Mapping[str, Any],
                      opciones_solver: Mapping[str, Any]) -> dict[str, Any]:
    """Resuelve las continuas con las discretas fijas y dice qué alcance tiene lo obtenido (RF-4).

    ``opciones_solver``: ``solver`` (por omisión ``ipopt``), ``iniciales`` (por variable),
    ``residuo_max`` (por omisión ``RESIDUO_MAX``) y ``opciones`` (las del solucionador, tal cual).
    El problema declara su tramo continuo en ``modelo_pnl(m, x, discretas)``, que devuelve el
    ``objetivo`` y las ``restricciones`` en expresiones de Pyomo sobre las variables ``x``.
    """
    discretas = _fijar_discretas(problema, discretas_fijas)
    iniciales = _iniciales(problema, opciones_solver.get('iniciales'))
    nombre_solver = str(opciones_solver.get('solver') or SOLVER)
    residuo_max = float(opciones_solver.get('residuo_max', RESIDUO_MAX))
    if not math.isfinite(residuo_max) or residuo_max <= 0:
        raise ValueError('residuo_max es una tolerancia positiva y finita')
    tolerancias = {'residuo_max': residuo_max, 'solver': dict(opciones_solver.get('opciones') or {})}
    comunes = {'solver': nombre_solver, 'discretas': discretas, 'iniciales': iniciales, 'tolerancias': tolerancias}
    if problema.modelo_pnl is None:
        return _resultado('NO_APLICA', 'el problema no declara modelo_pnl para su tramo continuo', **comunes)
    if not iniciales:
        return _resultado('NO_APLICA', 'no quedan variables continuas con las discretas fijas', **comunes)
    try:
        import pyomo.environ as pe
        from pyomo.contrib.solver.common.factory import SolverFactory
        from pyomo.contrib.solver.common.results import TerminationCondition
    except ImportError as exc:
        return _resultado('ERROR_ENTORNO', f'Pyomo no está disponible: {exc}', **comunes)
    solver = SolverFactory(nombre_solver)
    if solver is None or not bool(solver.available()):
        return _resultado('ERROR_ENTORNO', f'el solucionador {nombre_solver} no está instalado o no tiene licencia',
                          **comunes)
    continuas = [v for v in problema.variables if not v.discreta]
    m = pe.ConcreteModel()
    m.x = pe.Var([v.nombre for v in continuas], within=pe.Reals,
                 bounds={v.nombre: (v.inferior, v.superior) for v in continuas}, initialize=iniciales)
    x = {v.nombre: m.x[v.nombre] for v in continuas}
    formulado = problema.modelo_pnl(m, x, dict(discretas))
    m.objetivo = pe.Objective(expr=formulado['objetivo'], sense=pe.minimize)
    m.restricciones = pe.ConstraintList()
    for expr in formulado.get('restricciones') or ():
        m.restricciones.add(expr)
    comunes['variables_pnl'] = [v.nombre for v in continuas]
    try:
        r = solver.solve(m, load_solutions=False, raise_exception_on_nonoptimal_result=False,
                         solver_options=dict(tolerancias['solver']))
    except Exception as exc:    # el solucionador rechaza el modelo (grado, licencia): se dice, no se esconde
        return _resultado('FALLO_SOLVER', f'{nombre_solver}: {type(exc).__name__}: {exc}', **comunes)
    terminacion = getattr(r.termination_condition, 'name', str(r.termination_condition))
    comunes['terminacion'] = terminacion
    comunes['estado_solucion'] = getattr(r.solution_status, 'name', str(r.solution_status))
    try:
        r.solution_loader.load_vars()
    except Exception as exc:
        return _resultado('NO_CONVERGIDO', f'{nombre_solver} terminó en {terminacion} sin solución: {exc}', **comunes)
    valores = {n: float(pe.value(x[n])) for n in x}
    res_restr = 0.0
    for c in m.restricciones.values():
        cuerpo = float(pe.value(c.body))
        if c.has_lb():
            res_restr = max(res_restr, float(pe.value(c.lower)) - cuerpo)
        if c.has_ub():
            res_restr = max(res_restr, cuerpo - float(pe.value(c.upper)))
    res_cotas = max(max(v.inferior - valores[v.nombre], valores[v.nombre] - v.superior, 0.0) for v in continuas)
    residuos = {'restricciones_max': max(res_restr, 0.0), 'cotas_max': res_cotas}
    convergido = (r.termination_condition == TerminationCondition.convergenceCriteriaSatisfied
                  and residuos['restricciones_max'] <= residuo_max and res_cotas <= residuo_max)
    # Lo que quede dentro de la tolerancia pero apenas fuera de una cota se recorta antes de
    # evaluarlo: validar_vector no admite ni una milésima fuera del dominio.
    recortados = {v.nombre: min(max(valores[v.nombre], v.inferior), v.superior) for v in continuas}
    vector = {**discretas, **recortados}
    evaluacion = evaluar_vector(problema, vector) if convergido else None
    return _resultado('LOCAL_CONVERGIDO' if convergido else 'NO_CONVERGIDO',
                      None if convergido else f'{nombre_solver} terminó en {terminacion} con residuos {residuos}',
                      continuas=valores, vector=vector, objetivo_pnl=float(pe.value(m.objetivo)),
                      residuos=residuos, evaluacion=evaluacion, **comunes)


def _motivo_de_exclusion(c: Mapping[str, Any]) -> str | None:
    """Por qué un candidato no merece una simulación en DIgSILENT, o ``None`` si la merece."""
    estado_pnl = (c.get('pnl') or {}).get('estado')
    if estado_pnl is not None and estado_pnl != 'LOCAL_CONVERGIDO':
        return f'el PNL de este candidato terminó en {estado_pnl}'
    evaluacion = c.get('evaluacion')
    if isinstance(evaluacion, Mapping) and evaluacion.get('factible') is not True:
        return 'el gemelo ya lo da por no factible'
    return None


def verificar_candidatos(candidatos: Sequence[Mapping[str, Any]], medir: Callable[[Mapping[str, Any]], Mapping | None],
                         *, contexto: ContextoExperimento, limites: Limites, k: int = TOP_K,
                         **verificacion: Any) -> dict[str, Any]:
    """La primera de las ``k`` primeras admisibles que pasa ``verificar_top_k`` completa (RF-7).

    Los candidatos llegan en orden de preferencia (del benchmark o del PNL). Los que el PNL no
    resolvió o el gemelo da por no factibles se apartan con su motivo y no gastan simulación; de
    los demás, las ``k`` primeras se miden de una en una con la verificación de la 044, que es la
    única que puede devolver una ``elegida``. ``contexto`` y ``limites`` son obligatorios: sin ellos
    la 044 lo descartaría todo sin decir por qué. ``verificacion`` (tolerancias, ``guardar``) va tal
    cual a ``verificar_top_k``.
    """
    if type(k) is not int or k < 1:
        raise ValueError('k es un entero positivo de candidatos a verificar')
    excluidas, admisibles = [], []
    for c in candidatos:
        motivo = _motivo_de_exclusion(c)
        if motivo:
            excluidas.append({'alternativa': dict(c), 'motivo': motivo})
        else:
            admisibles.append(c)
    resultado = verificar_top_k(admisibles[:k], medir, contexto=contexto, limites=limites, **verificacion)
    return {**resultado, 'excluidas': excluidas, 'k': k, 'sin_verificar': len(admisibles[k:])}
