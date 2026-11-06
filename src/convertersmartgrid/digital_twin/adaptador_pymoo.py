"""GA, NSGA-II y DE de pymoo como candidatos del benchmark de la 048 (T2: RF-3).

pymoo (Blank y Deb, IEEE Access 2020) es opcional: sin él, el benchmark compara los
algoritmos vigentes de ``evolutivo.py`` y dice que faltan estos (los adaptadores ML opcionales
no bloquean el núcleo). Los genes de pymoo son reales; los repara ``problema_optimizacion.reparar``
dentro de ``evaluar``, la misma regla que para los demás, y el presupuesto lo corta el evaluador
del benchmark, no las generaciones de pymoo: así nadie gana por evaluar más.
"""
from __future__ import annotations

import importlib.util
from collections.abc import Callable, Sequence

import numpy as np

ALGORITMOS = ('pymoo_ga', 'pymoo_nsga2', 'pymoo_de')
#: Los que solo optimizan un objetivo: en un problema con varios no se comparan.
UN_OBJETIVO = ('pymoo_ga', 'pymoo_de')


def disponible() -> bool:
    return importlib.util.find_spec('pymoo') is not None


def ejecutar(nombre: str, *, inferior: Sequence[float], superior: Sequence[float], n_objetivos: int,
             evaluar: Callable[[np.ndarray], tuple[Sequence[float], float]], semilla: int, poblacion: int,
             generaciones_max: int) -> None:
    """Corre ``nombre`` hasta ``generaciones_max`` o hasta que ``evaluar`` corte (presupuesto o cancelación).

    ``evaluar(genes)`` da los objetivos y la violación total (0 = cumple), que pymoo trata como una
    restricción ``G <= 0``. Lo que importa del resultado lo guarda el evaluador del benchmark.
    """
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize

    if nombre not in ALGORITMOS:
        raise ValueError(f'algoritmo de pymoo desconocido: {nombre}')
    if nombre in UN_OBJETIVO and n_objetivos != 1:
        raise ValueError(f'{nombre} optimiza un solo objetivo')
    inf, sup = np.asarray(inferior, dtype=float), np.asarray(superior, dtype=float)

    class _Problema(ElementwiseProblem):
        def __init__(self):
            super().__init__(n_var=len(inf), n_obj=n_objetivos, n_ieq_constr=1, xl=inf, xu=sup)

        def _evaluate(self, x, out, *args, **kwargs):
            valores, violacion = evaluar(np.asarray(x, dtype=float))
            out['F'] = np.asarray(valores, dtype=float)
            out['G'] = np.array([float(violacion)])

    if nombre == 'pymoo_ga':
        from pymoo.algorithms.soo.nonconvex.ga import GA
        algoritmo = GA(pop_size=poblacion)
    elif nombre == 'pymoo_nsga2':
        from pymoo.algorithms.moo.nsga2 import NSGA2
        algoritmo = NSGA2(pop_size=poblacion)
    else:
        from pymoo.algorithms.soo.nonconvex.de import DE
        algoritmo = DE(pop_size=poblacion)
    minimize(_Problema(), algoritmo, termination=('n_gen', generaciones_max), seed=semilla, verbose=False)
