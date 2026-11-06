"""Benchmark de los optimizadores con el mismo presupuesto, las mismas semillas y la misma reparación (spec 048, T2).

El benchmark de ``tools/evaluar_evolutivos.py`` daba a cada algoritmo sus generaciones: el
genético con 30 individuos y 100 generaciones evaluaba más que NSGA-II con 40, y la
diferencia de resultados medía el presupuesto, no el algoritmo. Aquí:

- el presupuesto son **evaluaciones reales** del evaluador del problema; las consultas que
  devuelve la caché (``CacheEvaluaciones``, una por ejecución) se informan aparte (RF-3);
- todos los algoritmos corren con la misma lista de semillas, de al menos veinte, sobre los
  mismos problemas, y sus genes pasan por ``problema_optimizacion.reparar`` (RF-3);
- las métricas salen del archivo de lo evaluado, igual para todos: factibles, frente no
  dominado, hipervolumen con los objetivos normalizados por el ideal y el nadir que declara
  cada problema y un punto de referencia declarado antes de correr, tiempo y evaluaciones (RF-6);
- si se cancela, se devuelve lo evaluado hasta ahí sin candidatos ni óptimo (RF-8). Completo
  tampoco acepta nada: propone candidatos que la verificación de la 044 confirma o descarta.

Un algoritmo de un solo objetivo no se compara en un problema de varios: escalarizar sería
inventar pesos que nadie ha declarado.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from . import adaptador_pymoo
from .evolutivo import algoritmo_genetico, evolucion_diferencial, nsga2
from .problema_optimizacion import (CRITERIO_REPARACION, CacheEvaluaciones, ProblemaOptimizacion, cotas_geneticas,
                                    huella, huella_problema, reparar)

SEMILLAS_MINIMAS = 20
ALGORITMOS_VIGENTES = ('genetico', 'nsga2', 'evolucion_diferencial')
UN_OBJETIVO = ('genetico', 'evolucion_diferencial', *adaptador_pymoo.UN_OBJETIVO)
POBLACION = 30
#: Punto de referencia del hipervolumen en el espacio normalizado (ideal 0, nadir 1).
REFERENCIA_HV = 1.1
#: Consultas a la caché por evaluación real antes de dar la ejecución por estancada: un
#: algoritmo que solo repite vectores ya vistos no gasta presupuesto, pero tampoco avanza.
CONSULTAS_POR_EVALUACION = 20
#: Aptitud de lo que no es comparable o no cumple, como en ``evolutivo`` (regla de Deb).
INFACTIBLE = 1e9
CANDIDATOS = 10


class _Corte(Exception):
    def __init__(self, estado: str):
        super().__init__(estado)
        self.estado = estado


class _Ejecucion:
    """Evaluador de una ejecución: repara, gasta presupuesto, archiva y corta."""

    def __init__(self, problema: ProblemaOptimizacion, presupuesto: int, politica_hash: str,
                 cancelado: Callable[[], bool]):
        self.problema, self.presupuesto, self.politica = problema, presupuesto, politica_hash
        self.cancelado = cancelado
        self.cache = CacheEvaluaciones()
        self.archivo: list[dict[str, Any]] = []
        self.consultas = 0
        self.nombres = [o.nombre for o in problema.objetivos]

    def evaluar(self, genes: np.ndarray) -> dict[str, Any]:
        vector = reparar(self.problema, genes)
        self.consultas += 1
        if self.consultas > CONSULTAS_POR_EVALUACION * self.presupuesto:
            raise _Corte('consultas_agotadas')
        if self.cache.consultar(self.problema, vector, self.politica) is not None:
            return self.cache.evaluar(self.problema, vector, self.politica)   # no gasta presupuesto
        if self.cache.reales >= self.presupuesto:
            raise _Corte('presupuesto_agotado')
        if self.cancelado():
            raise _Corte('cancelado')
        resultado = self.cache.evaluar(self.problema, vector, self.politica)
        self.archivo.append(resultado)
        return resultado

    def valores(self, r: Mapping[str, Any]) -> tuple[list[float], float]:
        """Objetivos y violación para un algoritmo; lo no comparable, peor que cualquier infactible."""
        if not r['comparable']:
            return [INFACTIBLE * 10] * len(self.nombres), INFACTIBLE
        violacion = r['violacion_total'] if math.isfinite(r['violacion_total']) else INFACTIBLE / 10
        if not r['convergio']:
            violacion = max(violacion, INFACTIBLE / 10)
        return [float(r['objetivos'][n]) for n in self.nombres], float(violacion)

    def aptitud(self, genes: np.ndarray) -> float:
        valores, violacion = self.valores(self.evaluar(genes))
        if violacion > 0:
            return INFACTIBLE * (1 + min(violacion, 1e6))
        return valores[0]

    def objetivos(self, genes: np.ndarray) -> tuple[list[float], float]:
        return self.valores(self.evaluar(genes))


def hipervolumen(puntos: np.ndarray, referencia: float | Sequence[float]) -> float:
    """Hipervolumen exacto (a minimizar) de ``puntos`` ya normalizados, hasta ``referencia``.

    Uno y dos objetivos por barrido; con más, el de pymoo (si no está, error: no se aproxima).
    """
    p = np.asarray(puntos, dtype=float)
    if p.size == 0:
        return 0.0
    r = np.broadcast_to(np.asarray(referencia, dtype=float), (p.shape[1],))
    p = p[np.all(p < r, axis=1)]
    if len(p) == 0:
        return 0.0
    if p.shape[1] == 1:
        return float(r[0] - p[:, 0].min())
    if p.shape[1] == 2:
        return _hv_2d(p[np.lexsort((p[:, 1], p[:, 0]))], r)
    if not adaptador_pymoo.disponible():
        raise RuntimeError('hipervolumen de más de dos objetivos sin pymoo instalado')
    from pymoo.indicators.hv import HV
    return float(HV(ref_point=r)(p))


def _hv_2d(p: np.ndarray, r: np.ndarray) -> float:
    """Barrido de escalones: cada punto no dominado añade su franja hasta el techo del anterior."""
    area, techo = 0.0, r[1]
    for x, y in p:                       # ordenados por el primer objetivo
        if y < techo:
            area += (r[0] - x) * (techo - y)
            techo = y
    return float(area)


def _no_dominados(filas: list[dict[str, Any]], nombres: list[str]) -> list[dict[str, Any]]:
    puntos = [np.array([f['objetivos'][n] for n in nombres]) for f in filas]
    frente, vistos = [], set()
    for i, a in enumerate(puntos):
        if any(np.all(b <= a) and np.any(b < a) for j, b in enumerate(puntos) if j != i):
            continue
        clave = tuple(sorted(filas[i]['vector'].items()))
        if clave not in vistos:
            vistos.add(clave)
            frente.append(filas[i])
    return sorted(frente, key=lambda f: tuple(f['objetivos'][n] for n in nombres))


def _fila(r: Mapping[str, Any]) -> dict[str, Any]:
    return {'vector': dict(r['vector']), 'objetivos': dict(r['objetivos'])}


def _metricas(ej: _Ejecucion, normalizacion: Mapping[str, tuple[float, float]], referencia) -> dict[str, Any]:
    nombres = ej.nombres
    validas = [r for r in ej.archivo if r['factible'] and r['comparable']]
    frente = _no_dominados(validas, nombres)
    if frente:
        ideal = np.array([normalizacion[n][0] for n in nombres])
        nadir = np.array([normalizacion[n][1] for n in nombres])
        puntos = (np.array([[f['objetivos'][n] for n in nombres] for f in frente]) - ideal) / (nadir - ideal)
        hv = hipervolumen(puntos, referencia)
    else:
        hv = 0.0
    mejor = _fila(frente[0]) if frente and len(nombres) == 1 else None
    primera = next((i + 1 for i, r in enumerate(ej.archivo) if r['factible'] and r['comparable']), None)
    return {'evaluaciones_reales': ej.cache.reales, 'consultas_cacheadas': ej.cache.cacheadas,
            'factibles': len(validas), 'no_comparables': sum(not r['comparable'] for r in ej.archivo),
            'primera_factible': primera, 'frente': [_fila(f) for f in frente], 'hipervolumen': hv, 'mejor': mejor}


def _correr(nombre: str, ej: _Ejecucion, semilla: int, poblacion: int) -> None:
    p = ej.problema
    inf, sup = cotas_geneticas(p)
    tope = ej.presupuesto       # generaciones: nunca el límite que corta antes que el presupuesto
    if nombre == 'genetico':
        algoritmo_genetico(ej.aptitud, inf.astype(np.int64), sup.astype(np.int64), poblacion=poblacion,
                           generaciones=tope, paciencia=tope, semilla=semilla)
    elif nombre == 'nsga2':
        nsga2(ej.objetivos, inf, sup, enteros=all(v.discreta for v in p.variables), poblacion=poblacion,
              generaciones=tope, semilla=semilla, paciencia=CONSULTAS_POR_EVALUACION)
    elif nombre == 'evolucion_diferencial':
        evolucion_diferencial(ej.aptitud, inf, sup, poblacion=poblacion, generaciones=tope, paciencia=tope,
                              semilla=semilla)
    else:
        adaptador_pymoo.ejecutar(nombre, inferior=inf, superior=sup, n_objetivos=len(p.objetivos),
                                 evaluar=ej.objetivos, semilla=semilla, poblacion=poblacion, generaciones_max=tope)


def _compatible(nombre: str, problema: ProblemaOptimizacion) -> str | None:
    if nombre in UN_OBJETIVO and len(problema.objetivos) != 1:
        return 'optimiza un solo objetivo y el problema tiene varios; no se escalariza con pesos no declarados'
    if nombre == 'genetico' and not all(v.discreta for v in problema.variables):
        return 'el genético vigente solo trabaja con genes enteros y el problema tiene variables continuas'
    return None


def _intervalo(valores: Sequence[float], semilla: int = 0, remuestras: int = 2000) -> dict[str, Any]:
    """Media, mediana e IC del 95 % por bootstrap de percentiles, determinista."""
    x = np.asarray(valores, dtype=float)
    if len(x) == 0:
        return {'media': None, 'mediana': None, 'ic95': None}
    rng = np.random.default_rng(semilla)
    medias = rng.choice(x, size=(remuestras, len(x)), replace=True).mean(axis=1)
    return {'media': float(x.mean()), 'mediana': float(np.median(x)),
            'ic95': [float(np.quantile(medias, 0.025)), float(np.quantile(medias, 0.975))]}


def _resumen(ejecuciones: list[dict[str, Any]], nombres: list[str]) -> dict[str, Any]:
    r = {'semillas': len(ejecuciones),
         'tasa_con_factible': (sum(e['factibles'] > 0 for e in ejecuciones) / len(ejecuciones)) if ejecuciones else 0.0,
         'hipervolumen': _intervalo([e['hipervolumen'] for e in ejecuciones]),
         'evaluaciones_reales': _intervalo([e['evaluaciones_reales'] for e in ejecuciones]),
         'tiempo_s': _intervalo([e['tiempo_s'] for e in ejecuciones])}
    if len(nombres) == 1:
        r['mejor'] = _intervalo([e['mejor']['objetivos'][nombres[0]] for e in ejecuciones if e['mejor']])
    return r


def _candidatos(ejecuciones: list[dict[str, Any]], nombres: list[str]) -> list[dict[str, Any]]:
    """Lo mejor del frente de todas las ejecuciones, sin repetir, para la verificación de la 044."""
    filas = [f for e in ejecuciones for f in e['frente']]
    frente = _no_dominados(filas, nombres) if len(nombres) > 1 else sorted(
        {tuple(sorted(f['vector'].items())): f for f in filas}.values(), key=lambda f: f['objetivos'][nombres[0]])
    return [{**f, 'requiere_verificacion_nativa': True} for f in frente[:CANDIDATOS]]


def comparar_optimizadores(problemas: Sequence[ProblemaOptimizacion], *, semillas: tuple[int, ...],
                           presupuesto: int, cancelado: Callable[[], bool],
                           algoritmos: Sequence[str] | None = None, poblaciones: Mapping[str, int] | None = None,
                           referencia_hv: float = REFERENCIA_HV, politica_hash: str | None = None) -> dict[str, Any]:
    """Compara los algoritmos compatibles con cada problema con el mismo método (RF-3, RF-6, RF-8).

    ``presupuesto`` son evaluaciones reales por ejecución (un problema, un algoritmo, una
    semilla). ``cancelado()`` se consulta antes de cada evaluación nueva.
    """
    semillas = tuple(semillas)
    if len(semillas) < SEMILLAS_MINIMAS:
        raise ValueError(f'se comparan algoritmos con al menos veinte semillas ({len(semillas)} dadas)')
    if len(set(semillas)) != len(semillas) or any(type(s) is not int or s < 0 for s in semillas):
        raise ValueError('semillas repetidas o no enteras no negativas')
    if type(presupuesto) is not int or presupuesto <= 0:
        raise ValueError('el presupuesto es un número entero positivo de evaluaciones')
    if not problemas:
        raise ValueError('sin problemas que comparar')
    if not math.isfinite(referencia_hv) or referencia_hv <= 1:
        raise ValueError('el punto de referencia del hipervolumen va más allá del nadir normalizado (> 1)')
    for p in problemas:
        if p.normalizacion is None:
            raise ValueError(f'{p.nombre}: falta la normalizacion (ideal y nadir) declarada antes de comparar')
    avisos: list[str] = []
    elegidos = list(ALGORITMOS_VIGENTES)
    if adaptador_pymoo.disponible():
        elegidos += list(adaptador_pymoo.ALGORITMOS)
    else:
        avisos.append('pymoo no está instalado: se comparan solo los algoritmos vigentes')
    if algoritmos is not None:
        desconocidos = set(algoritmos) - set(ALGORITMOS_VIGENTES) - set(adaptador_pymoo.ALGORITMOS)
        if desconocidos:
            raise ValueError(f'algoritmos desconocidos: {", ".join(sorted(desconocidos))}')
        elegidos = [a for a in elegidos if a in algoritmos]
    poblaciones = dict(poblaciones or {})
    metodo = {'semillas': list(semillas), 'presupuesto': presupuesto,
              'unidad_presupuesto': 'evaluaciones reales del evaluador por ejecución; '
                                    'las consultas reutilizadas de la caché se informan aparte',
              'criterio_reparacion': CRITERIO_REPARACION, 'referencia_hipervolumen': referencia_hv,
              'normalizacion': {p.nombre: {k: list(v) for k, v in p.normalizacion.items()} for p in problemas},
              'algoritmos': elegidos, 'poblaciones': {a: poblaciones.get(a, POBLACION) for a in elegidos}}
    politica = politica_hash or huella({'benchmark_048': metodo})
    metodo['politica_hash'] = politica
    salida: list[dict[str, Any]] = []
    estado = 'completo'
    for p in problemas:
        nombres = [o.nombre for o in p.objetivos]
        fila: dict[str, Any] = {'nombre': p.nombre, 'huella': huella_problema(p), 'algoritmos': {}, 'candidatos': []}
        salida.append(fila)
        for nombre in elegidos:
            motivo = _compatible(nombre, p)
            if motivo:
                fila['algoritmos'][nombre] = {'estado': 'no_compatible', 'motivo': motivo, 'ejecuciones': []}
                continue
            corridas: list[dict[str, Any]] = []
            fila['algoritmos'][nombre] = {'estado': 'completo', 'ejecuciones': corridas}
            for semilla in semillas:
                ej = _Ejecucion(p, presupuesto, politica, cancelado)
                inicio = time.perf_counter()
                cierre, error = 'terminado', None
                try:
                    _correr(nombre, ej, semilla, metodo['poblaciones'][nombre])
                except _Corte as corte:
                    cierre = corte.estado
                except Exception as exc:    # un algoritmo que revienta no tumba el benchmark: se anota
                    cierre, error = 'error', f'{type(exc).__name__}: {exc}'
                corridas.append({'semilla': semilla, 'estado': cierre, 'error': error,
                                 'tiempo_s': time.perf_counter() - inicio,
                                 **_metricas(ej, p.normalizacion, referencia_hv)})
                if cierre == 'cancelado':
                    estado = 'cancelado'
                    break
            fila['algoritmos'][nombre]['resumen'] = _resumen(corridas, nombres)
            if estado == 'cancelado':
                fila['algoritmos'][nombre]['estado'] = 'cancelado'
                break
        if estado == 'cancelado':
            break
        todas = [e for a in fila['algoritmos'].values() for e in a['ejecuciones']]
        fila['candidatos'] = _candidatos(todas, nombres)
    if estado == 'cancelado':
        for fila in salida:
            fila['candidatos'] = []
    return {'estado': estado, 'metodo': metodo, 'problemas': salida, 'avisos': avisos,
            'publicable': estado == 'completo', 'optimo_aceptado': None,
            'nota': 'el benchmark propone candidatos; ninguno se acepta sin la verificación completa de la 044'}
