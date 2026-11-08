"""Algoritmos genéticos y evolutivos del gemelo digital (spec 024, RF-67 a RF-73).

El PIDE pide la alternativa que cumple la norma con el menor coste, sin sobredimensionar
(RF-33, RF-34), y la spec deja al oráculo como «evaluador rápido dentro de un optimizador»
(sección D2). Aquí están los optimizadores y los problemas de la red que resuelven:

- ``algoritmo_genetico``: genoma entero, torneo, cruce uniforme, mutación de reinicio y de
  paso, elitismo y memoria de evaluaciones (un genoma repetido no se vuelve a simular).
- ``nsga2``: NSGA-II de Deb et al. (2002), multiobjetivo con dominancia restringida: el
  frente de Pareto entre inversión y pérdidas con la norma como restricción.
- ``evolucion_diferencial``: jDE de Brest et al. (2006), evolución diferencial con F y CR
  autoadaptados por individuo, para variables continuas (la consigna de las fuentes).

Problemas: ubicación y tamaño de bancos de condensadores (``optimizar_bancos``),
reconfiguración radial por maniobras (``reconfigurar``) y consigna de cabecera
(``optimizar_consigna``). Cada evaluación es un flujo mallado (``flujo.SistemaMallado``).
Nada se escribe en DIgSILENT: cada propuesta sale con ``confirmar_en_pf`` y se confirma allí
antes de aceptarse (principio 1, RF-35, RF-46).

``problema_bancos`` y ``problema_maniobras`` formulan los mismos problemas con el contrato de
``problema_optimizacion`` (spec 048, T1): variables con su unidad, la norma como restricción y
la demanda atendida frente a la del estado actual, para que el benchmark de la 048 compare
algoritmos sobre la red sin que una isla pase por mejora.

Todo es determinista con la semilla: misma red, mismos parámetros y misma semilla, misma
propuesta.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..evaluacion_modelos import comprobar_tolerancias, validar_medicion_nativa
from ..experimentos import ContextoExperimento
from .episode import Caso, Clase
from .evaluacion import Limites, evaluar
from .oraculo import S_BASE, Muestra, escalar_nodo, muestra, sistema_de
from .problema_optimizacion import (
    ContextoSintetico,
    Objetivo,
    ProblemaOptimizacion,
    Restriccion,
    Variable,
)

#: Aptitud de una solución que incumple: siempre peor que cualquiera que cumple (regla de
#: factibilidad de Deb); entre las que incumplen, gana la que menos se aparta.
INFACTIBLE = 1e9


def casos_aprendizaje(instantanea: dict) -> list[dict]:
    """050:RF-2/3, 048:RF-1: problemas declarados sobre episodios custodiados, sin aceptar propuestas."""
    import json
    import re
    from dataclasses import replace
    from ..aprendizaje_continuo import (CicloBloqueado, ESQUEMA_PROCEDENCIA,
        crear_observacion_id, muestra_de_registro, ruta_de)
    from ..experimentos import clave_contexto
    from .episode import leer_episodio
    from .oraculo import por_que_no_ensena

    datos = json.loads(ruta_de(instantanea, 'evolutivos_casos').read_text(encoding='utf-8'))
    procedencia = json.loads(ruta_de(instantanea, 'procedencia').read_text(encoding='utf-8'))
    if datos.get('schema') != 'convertersmartgrid-optimization-learning-cases-v1' or not datos.get('casos'):
        raise CicloBloqueado('evolutivos: manifiesto de casos vacío o inválido')
    if procedencia.get('schema') != ESQUEMA_PROCEDENCIA:
        raise CicloBloqueado('evolutivos: procedencia inválida')
    preparados, vistos = [], set()
    for caso in datos['casos']:
        if set(caso) != {'record_id', 'episode_id', 'contexto_043', 'problema', 'particion', 'parametros', 'normalizacion'}:
            raise CicloBloqueado('evolutivos: campos del caso incompletos o desconocidos')
        eid, rid = caso['episode_id'], caso['record_id']
        if (not isinstance(eid, str) or not re.fullmatch(r'[0-9a-f]{64}', eid)
                or not isinstance(rid, str) or not rid or rid in vistos):
            raise CicloBloqueado('evolutivos: identidad de caso/episodio inválida o duplicada')
        vistos.add(rid)
        ruta = ruta_de(instantanea, 'twin') / 'objetos' / eid[:2] / f'{eid}.json'
        e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
        contexto = ContextoExperimento(**caso['contexto_043'])
        fisico = e.contexto_fisico or {}
        if (e.episode_id != eid or e.clase not in (Clase.ACCEPTED, Clase.COUNTERFACTUAL)
                or not e.nativo.get('reopen_verified') or por_que_no_ensena(e)
                or clave_contexto(contexto) not in instantanea.get('contextos', {}).values()
                or contexto.project != e.nativo['project'] or tuple(contexto.feeders) != tuple(e.nativo['feeders'])
                or any(getattr(contexto, k) != e.fuente.get(k) for k in ('source_run_id', 'source_mode', 'source_fingerprint'))
                or contexto.case_id != fisico.get('case_id') or contexto.case_role != e.caso.value
                or any(getattr(contexto, k) != fisico.get(k) for k in ('topology_hash', 'controls_hash', 'scenario_hash'))):
            raise CicloBloqueado('evolutivos: episodio sin contexto físico 043 coincidente y reabierto')
        parametros = caso['parametros']
        comun = {'tension_min_pu', 'tension_max_pu', 'exponente'}
        extras = {'maniobras'} if caso['problema'] == 'maniobras' else {
            'candidatos', 'kvar_modulo', 'modulos_max', 'costo_modulo', 'origen_costo', 'factor_carga'}
        if (caso['problema'] not in ('bancos', 'maniobras') or not isinstance(parametros, dict)
                or set(parametros) - comun - extras
                or not 0 < parametros.get('tension_min_pu', 0) < parametros.get('tension_max_pu', 0)
                or not math.isfinite(parametros['tension_max_pu'])):
            raise CicloBloqueado('evolutivos: parámetros del problema ausentes o inválidos')
        factory = problema_maniobras if caso['problema'] == 'maniobras' else problema_bancos
        problema = factory(e.topologia['grafo'], contexto=contexto,
            modelo_id=f'flujo_mallado:{instantanea["versiones"]["codigo"]}', **parametros)
        problema = replace(problema, nombre=rid, normalizacion=caso['normalizacion'])
        m = muestra_de_registro(instantanea, procedencia['referencias'], 'evolutivos_casos',
            rid, caso, familia='evolutivos', particion=caso['particion'],
            origen='simulado_nativo', etiqueta='motor_nativo')
        if m.contexto != clave_contexto(contexto):
            raise CicloBloqueado('evolutivos: referencia de observación de otro contexto')
        ref = procedencia['referencias']['evolutivos_casos'][rid]
        if m.observacion_id != crear_observacion_id(m.contexto, ref['fuente_hash'], e.episode_id, e.creado):
            raise CicloBloqueado('evolutivos: referencia distinta de la observación fuente del episodio')
        preparados.append({'problema': problema, 'muestra': m})
    return preparados


@dataclass
class Resultado:
    mejor: np.ndarray
    aptitud: float
    historia: list[float]       # mejor aptitud por generación (no crece: hay elitismo)
    evaluaciones: int           # genomas distintos evaluados
    generaciones: int


@dataclass
class FrentePareto:
    soluciones: list[np.ndarray]
    objetivos: np.ndarray       # una fila por solución
    violacion: np.ndarray       # 0 = cumple las restricciones
    evaluaciones: int
    generaciones: int


# ------------------------------------------------------------------ algoritmo genético
def algoritmo_genetico(aptitud: Callable[[np.ndarray], float], inferior: Sequence[int], superior: Sequence[int],
                       *, poblacion: int = 40, generaciones: int = 80, prob_cruce: float = 0.9,
                       prob_mutacion: float | None = None, elite: int = 2, torneo: int = 3,
                       paciencia: int = 25, semilla: int = 0, iniciales: Sequence[Sequence[int]] = ()
                       ) -> Resultado:
    """Minimiza ``aptitud`` sobre genomas enteros entre ``inferior`` y ``superior`` (incluidos).

    Para tras ``paciencia`` generaciones sin mejorar. ``iniciales`` siembra la población
    (por ejemplo, el estado actual de la red, para no proponer nada peor que no hacer nada).
    """
    rng = np.random.default_rng(semilla)
    inf, sup = np.asarray(inferior, dtype=np.int64), np.asarray(superior, dtype=np.int64)
    n = len(inf)
    pm = prob_mutacion if prob_mutacion is not None else 1.0 / max(n, 1)
    memoria: dict[tuple[int, ...], float] = {}

    def f(g: np.ndarray) -> float:
        clave = tuple(int(x) for x in g)
        if clave not in memoria:
            memoria[clave] = float(aptitud(np.array(clave, dtype=np.int64)))
        return memoria[clave]

    pob = [np.clip(np.asarray(g, dtype=np.int64), inf, sup) for g in iniciales][:poblacion]
    while len(pob) < poblacion:
        pob.append(rng.integers(inf, sup + 1))
    fit = np.array([f(g) for g in pob])
    historia = [float(fit.min())]
    sin_mejora, gen = 0, 0

    def elegir() -> np.ndarray:
        rivales = rng.integers(0, len(pob), size=torneo)
        return pob[int(rivales[np.argmin(fit[rivales])])]

    for gen in range(1, generaciones + 1):
        orden = np.argsort(fit, kind='stable')
        nueva = [pob[i].copy() for i in orden[:elite]]
        while len(nueva) < poblacion:
            p1, p2 = elegir(), elegir()
            if rng.random() < prob_cruce:
                mascara = rng.random(n) < 0.5
                hijos = [np.where(mascara, p1, p2), np.where(mascara, p2, p1)]
            else:
                hijos = [p1.copy(), p2.copy()]
            for h in hijos:
                mutar = rng.random(n) < pm
                reinicio = rng.random(n) < 0.5
                paso = rng.choice((-1, 1), size=n)
                h[:] = np.where(mutar & reinicio, rng.integers(inf, sup + 1), np.where(mutar, h + paso, h))
                np.clip(h, inf, sup, out=h)
            nueva.extend(hijos)
        pob = nueva[:poblacion]
        fit = np.array([f(g) for g in pob])
        mejor = float(fit.min())
        sin_mejora = 0 if mejor < historia[-1] - 1e-12 else sin_mejora + 1
        historia.append(min(mejor, historia[-1]))
        if sin_mejora >= paciencia:
            break
    i = int(np.argmin(fit))
    return Resultado(pob[i].copy(), float(fit[i]), historia, len(memoria), gen)


# ------------------------------------------------------------------ NSGA-II
def _domina(fa: np.ndarray, va: float, fb: np.ndarray, vb: float) -> bool:
    """Dominancia restringida de Deb: cumplir gana a incumplir; entre las que incumplen,
    la de menor violación; entre las que cumplen, Pareto."""
    if va <= 0 < vb:
        return True
    if va > 0 and vb > 0:
        return va < vb
    if va > 0:
        return False
    return bool(np.all(fa <= fb) and np.any(fa < fb))


def _frentes(obj: np.ndarray, vio: np.ndarray) -> list[list[int]]:
    n = len(obj)
    dominadas: list[list[int]] = [[] for _ in range(n)]
    cuenta = np.zeros(n, dtype=np.int64)
    for p in range(n):
        for q in range(p + 1, n):
            if _domina(obj[p], vio[p], obj[q], vio[q]):
                dominadas[p].append(q)
                cuenta[q] += 1
            elif _domina(obj[q], vio[q], obj[p], vio[p]):
                dominadas[q].append(p)
                cuenta[p] += 1
    frentes = [[p for p in range(n) if cuenta[p] == 0]]
    while frentes[-1]:
        siguiente = []
        for p in frentes[-1]:
            for q in dominadas[p]:
                cuenta[q] -= 1
                if cuenta[q] == 0:
                    siguiente.append(q)
        frentes.append(siguiente)
    return frentes[:-1]


def _hacinamiento(obj: np.ndarray, frente: list[int]) -> np.ndarray:
    if len(frente) <= 2:
        return np.full(len(frente), np.inf)
    d = np.zeros(len(frente))
    f = obj[frente]
    for k in range(f.shape[1]):
        orden = np.argsort(f[:, k], kind='stable')
        d[orden[0]] = d[orden[-1]] = np.inf
        rango = f[orden[-1], k] - f[orden[0], k]
        if rango > 0:
            d[orden[1:-1]] += (f[orden[2:], k] - f[orden[:-2], k]) / rango
    return d


def nsga2(objetivos: Callable[[np.ndarray], tuple[Sequence[float], float]], inferior: Sequence[float],
          superior: Sequence[float], *, enteros: bool = True, poblacion: int = 40, generaciones: int = 60,
          prob_cruce: float = 0.9, eta_cruce: float = 15.0, eta_mutacion: float = 20.0, semilla: int = 0,
          iniciales: Sequence[Sequence[float]] = (), paciencia: int | None = None) -> FrentePareto:
    """Frente de Pareto de ``objetivos`` (todos a minimizar).

    ``objetivos(genoma)`` devuelve ``(valores, violacion)``: la violación es 0 si cumple las
    restricciones. Cruce SBX y mutación polinómica; con ``enteros``, redondeo al entero.
    Con ``paciencia``, para tras esas generaciones sin ningún genoma nuevo: en un dominio
    pequeño ya visto entero, seguir solo repite la ordenación por frentes (048, T2).
    """
    rng = np.random.default_rng(semilla)
    inf, sup = np.asarray(inferior, dtype=float), np.asarray(superior, dtype=float)
    n = len(inf)
    memoria: dict[tuple, tuple[np.ndarray, float]] = {}

    def ajustar(g: np.ndarray) -> np.ndarray:
        g = np.clip(g, inf, sup)
        return np.round(g) if enteros else g

    def evaluar(g: np.ndarray) -> tuple[np.ndarray, float]:
        clave = tuple(int(x) for x in g) if enteros else tuple(np.round(g, 12))
        if clave not in memoria:
            valores, violacion = objetivos(g.astype(np.int64) if enteros else g.copy())
            memoria[clave] = (np.asarray(valores, dtype=float), max(float(violacion), 0.0))
        return memoria[clave]

    def cruzar(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if rng.random() >= prob_cruce:
            return a.copy(), b.copy()
        u = rng.random(n)
        beta = np.where(u <= 0.5, (2 * u) ** (1 / (eta_cruce + 1)), (1 / (2 * (1 - u))) ** (1 / (eta_cruce + 1)))
        cambia = rng.random(n) < 0.5
        h1 = np.where(cambia, 0.5 * ((1 + beta) * a + (1 - beta) * b), a)
        h2 = np.where(cambia, 0.5 * ((1 - beta) * a + (1 + beta) * b), b)
        return h1, h2

    def mutar(g: np.ndarray) -> np.ndarray:
        rango = np.maximum(sup - inf, 1e-12)
        u = rng.random(n)
        delta = np.where(u < 0.5, (2 * u) ** (1 / (eta_mutacion + 1)) - 1,
                         1 - (2 * (1 - u)) ** (1 / (eta_mutacion + 1)))
        paso = delta * rango
        # Con enteros, un paso polinómico de menos de medio entero no movería nada: al menos uno.
        if enteros:
            paso = np.where(np.abs(paso) < 0.5, np.where(delta < 0, -1.0, 1.0), paso)
        return np.where(rng.random(n) < 1.0 / max(n, 1), g + paso, g)

    pob = [ajustar(np.asarray(g, dtype=float)) for g in iniciales][:poblacion]
    while len(pob) < poblacion:
        pob.append(ajustar(inf + rng.random(n) * (sup - inf)))
    gen, sin_nuevos = 0, 0
    for gen in range(1, generaciones + 1):
        vistos_antes = len(memoria)
        ev = [evaluar(g) for g in pob]
        obj = np.array([e[0] for e in ev])
        vio = np.array([e[1] for e in ev])
        rango = np.zeros(len(pob), dtype=np.int64)
        haci = np.zeros(len(pob))
        for r, fr in enumerate(_frentes(obj, vio)):
            rango[fr] = r
            haci[fr] = _hacinamiento(obj, fr)

        def torneo() -> np.ndarray:
            a, b = (int(x) for x in rng.integers(0, len(pob), size=2))
            mejor = a if (rango[a], -haci[a]) < (rango[b], -haci[b]) else b
            return pob[mejor]

        hijos = []
        while len(hijos) < poblacion:
            h1, h2 = cruzar(torneo(), torneo())
            hijos.extend([ajustar(mutar(h1)), ajustar(mutar(h2))])
        union = pob + hijos[:poblacion]
        ev = [evaluar(g) for g in union]
        obj = np.array([e[0] for e in ev])
        vio = np.array([e[1] for e in ev])
        nueva: list[int] = []
        for fr in _frentes(obj, vio):
            if len(nueva) + len(fr) <= poblacion:
                nueva.extend(fr)
                continue
            d = _hacinamiento(obj, fr)
            nueva.extend(fr[i] for i in np.argsort(-d, kind='stable')[:poblacion - len(nueva)])
            break
        pob = [union[i] for i in nueva]
        sin_nuevos = sin_nuevos + 1 if len(memoria) == vistos_antes else 0
        if paciencia is not None and sin_nuevos >= paciencia:
            break
    ev = [evaluar(g) for g in pob]
    obj = np.array([e[0] for e in ev])
    vio = np.array([e[1] for e in ev])
    vistos, sol = set(), []
    for i in _frentes(obj, vio)[0]:
        clave = tuple(np.round(pob[i], 12))
        if clave not in vistos:
            vistos.add(clave)
            sol.append(i)
    sol.sort(key=lambda i: tuple(obj[i]))
    return FrentePareto([pob[i].astype(np.int64) if enteros else pob[i] for i in sol], obj[sol], vio[sol],
                        len(memoria), gen)


# ------------------------------------------------------------------ evolución diferencial
def evolucion_diferencial(aptitud: Callable[[np.ndarray], float], inferior: Sequence[float],
                          superior: Sequence[float], *, poblacion: int | None = None, generaciones: int = 150,
                          paciencia: int = 40, semilla: int = 0, iniciales: Sequence[Sequence[float]] = ()
                          ) -> Resultado:
    """jDE: DE/rand/1/bin con F y CR propios de cada individuo, que se heredan si su hijo gana."""
    rng = np.random.default_rng(semilla)
    inf, sup = np.asarray(inferior, dtype=float), np.asarray(superior, dtype=float)
    n = len(inf)
    np_ = max(poblacion or 10 * n, 6)
    sembrados = [np.clip(np.asarray(g, dtype=float), inf, sup) for g in iniciales][:np_]
    pob = np.array(sembrados + [inf + rng.random(n) * (sup - inf) for _ in range(np_ - len(sembrados))])
    fit = np.array([float(aptitud(x.copy())) for x in pob])
    evaluaciones = len(pob)
    f_ind, cr_ind = np.full(np_, 0.5), np.full(np_, 0.9)
    historia = [float(fit.min())]
    sin_mejora, gen = 0, 0
    for gen in range(1, generaciones + 1):
        for i in range(np_):
            f_i = 0.1 + 0.9 * rng.random() if rng.random() < 0.1 else f_ind[i]
            cr_i = rng.random() if rng.random() < 0.1 else cr_ind[i]
            r1, r2, r3 = rng.choice([j for j in range(np_) if j != i], size=3, replace=False)
            mutante = pob[r1] + f_i * (pob[r2] - pob[r3])
            # Fuera de los límites, a medio camino entre el límite y el padre (no se pega al borde).
            mutante = np.where(mutante < inf, (inf + pob[i]) / 2, mutante)
            mutante = np.where(mutante > sup, (sup + pob[i]) / 2, mutante)
            cruza = rng.random(n) < cr_i
            cruza[rng.integers(n)] = True
            prueba = np.where(cruza, mutante, pob[i])
            fp = float(aptitud(prueba.copy()))
            evaluaciones += 1
            if fp <= fit[i]:
                pob[i], fit[i], f_ind[i], cr_ind[i] = prueba, fp, f_i, cr_i
        mejor = float(fit.min())
        sin_mejora = 0 if mejor < historia[-1] - 1e-12 else sin_mejora + 1
        historia.append(min(mejor, historia[-1]))
        if sin_mejora >= paciencia:
            break
    i = int(np.argmin(fit))
    return Resultado(pob[i].copy(), float(fit[i]), historia, evaluaciones, gen)


# ------------------------------------------------------------------ problemas de la red
def _energizadas(m: Muestra) -> np.ndarray:
    return m.alimentado & ~m.fuente


def violacion_tension(v: np.ndarray, medir: np.ndarray, tension_min_pu: float, tension_max_pu: float) -> float:
    """Suma de lo que cada barra se sale de la banda (p.u.); 0 si toda la red cumple."""
    vv = v[medir]
    return float(np.sum(np.maximum(tension_min_pu - vv, 0.0)) + np.sum(np.maximum(vv - tension_max_pu, 0.0)))


def nombre_corto(nodo: str) -> str:
    """El ``loc_name`` de una identidad ``Clase:ruta\\Nombre.Clase``."""
    return nodo.rsplit('\\', 1)[-1].rsplit(':', 1)[-1].rsplit('.', 1)[0]


def optimizar_bancos(grafo: Mapping[str, Any], *, candidatos: Sequence[str], kvar_modulo: float,
                     tension_min_pu: float, tension_max_pu: float, modulos_max: int = 3,
                     costo_modulo: float | None = None, valor_kw_perdidas: float | None = None,
                     factor_carga: float = 1.0, exponente: float = 0.0, semilla: int = 0,
                     poblacion: int = 40, generaciones: int = 80, top_k: int = 3) -> dict[str, Any]:
    """Dónde y cuántos módulos de banco poner para cumplir la norma al menor coste (RF-68, RF-70).

    El genoma da los módulos (0 a ``modulos_max``) en cada barra candidata. El algoritmo
    genético busca el de menor coste que cumple la norma y NSGA-II el frente inversión–
    pérdidas; se elige, entre los que cumplen, el de menor coste total, y los demás del frente
    que cuestan más quedan como sobredimensionados (RF-34). Sin ``costo_modulo`` (sin libro
    CAPEX) el coste es el número de módulos: la menor intervención. Sin ``valor_kw_perdidas``
    las pérdidas solo desempatan: no se inventa su precio (RF-58e).
    """
    m = muestra(grafo)
    sis = sistema_de(m)
    pos = {n: i for i, n in enumerate(m.ids)}
    nodos = [c for c in dict.fromkeys(candidatos) if c in pos and not m.fuente[pos[c]]]
    if not nodos:
        return {'bancos': [], 'factible': False, 'motivo': 'ninguna barra candidata está en el grafo',
                'confirmar_en_pf': True}
    idx = np.array([pos[c] for c in nodos])
    medir = _energizadas(m)
    s_base = m.s_carga * factor_carga
    q_modulo = kvar_modulo / 1000.0 / S_BASE

    def estado(genoma: np.ndarray):
        s = s_base.copy()
        s[idx] -= 1j * genoma * q_modulo
        return sis.resolver(s, exponente=exponente)

    def inversion(genoma: np.ndarray) -> float:
        return float(np.sum(genoma)) * (costo_modulo if costo_modulo is not None else 1.0)

    def perdidas_kw(sol) -> float:
        return sol.perdidas_pu * S_BASE * 1000.0

    def coste(genoma: np.ndarray, sol) -> float:
        peso = valor_kw_perdidas if valor_kw_perdidas is not None else 1e-6
        return inversion(genoma) + peso * perdidas_kw(sol)

    def aptitud(genoma: np.ndarray) -> float:
        sol = estado(genoma)
        if not sol.convergio:
            return INFACTIBLE * 2
        vio = violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu)
        return coste(genoma, sol) if vio <= 0 else INFACTIBLE * (1 + vio)

    def objetivos(genoma: np.ndarray) -> tuple[list[float], float]:
        sol = estado(genoma)
        if not sol.convergio:
            return [inversion(genoma), 1e12], 1e6
        return [inversion(genoma), perdidas_kw(sol)], violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu)

    cero = np.zeros(len(nodos), dtype=np.int64)
    inf, sup = [0] * len(nodos), [modulos_max] * len(nodos)
    ga = algoritmo_genetico(aptitud, inf, sup, poblacion=poblacion, generaciones=generaciones,
                            semilla=semilla, iniciales=[cero])
    frente = nsga2(objetivos, inf, sup, poblacion=poblacion, generaciones=max(generaciones // 2, 10),
                   semilla=semilla, iniciales=[cero, ga.mejor])
    puntuadas = []
    for g in [ga.mejor] + list(frente.soluciones):
        sol = estado(g)
        vio = violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu) if sol.convergio else math.inf
        puntuadas.append(((vio > 0, vio if vio > 0 else coste(g, sol), int(np.sum(g)), tuple(int(x) for x in g)),
                          g, sol))
    puntuadas.sort(key=lambda t: t[0])
    _orden, elegido, sol = puntuadas[0]
    base = estado(cero)
    factible = sol.convergio and violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu) <= 0
    filas_frente = [{'modulos': int(np.sum(g)), 'inversion': float(obj[0]), 'perdidas_kw': float(obj[1]),
                     'cumple': bool(vio <= 0),
                     'sobredimensionada': bool(vio <= 0 and float(obj[0]) > inversion(elegido) + 1e-9)}
                    for g, obj, vio in zip(frente.soluciones, frente.objetivos, frente.violacion, strict=True)]
    v_med = sol.v[medir] if medir.any() else np.array([0.0])
    # 027:RF-14: las k mejores que cumplen, distintas, para verificarlas en DIgSILENT en orden.
    alternativas, vistas = [], set()
    for (_inf, _c, _n, clave), g, s in puntuadas:
        if len(alternativas) >= top_k or clave in vistas or _inf or not s.convergio:
            continue
        vistas.add(clave)
        alternativas.append({
            'bancos': [{'nodo': nodos[i], 'barra': nombre_corto(nodos[i]), 'modulos': int(k),
                        'q_kvar': float(k * kvar_modulo)} for i, k in enumerate(g) if k > 0],
            'inversion': inversion(g), 'coste_total': coste(g, s), 'perdidas_kw': perdidas_kw(s),
            'v_min': float(s.v[medir].min()) if medir.any() else None})
    return {
        'alternativas': alternativas,
        'bancos': [{'nodo': nodos[i], 'barra': nombre_corto(nodos[i]), 'modulos': int(k),
                    'q_kvar': float(k * kvar_modulo)} for i, k in enumerate(elegido) if k > 0],
        'factible': bool(factible), 'inversion': inversion(elegido), 'coste_total': coste(elegido, sol),
        'perdidas_kw': perdidas_kw(sol) if sol.convergio else None,
        'perdidas_kw_base': perdidas_kw(base) if base.convergio else None,
        'v_min': float(v_med.min()), 'v_max': float(v_med.max()),
        'v_min_base': float(base.v[medir].min()) if base.convergio and medir.any() else None,
        'frente': filas_frente,
        'algoritmos': {'genetico': {'evaluaciones': ga.evaluaciones, 'generaciones': ga.generaciones},
                       'nsga2': {'evaluaciones': frente.evaluaciones, 'generaciones': frente.generaciones,
                                 'soluciones': len(frente.soluciones)}},
        'confirmar_en_pf': True}


def _demanda_kw(m: Muestra) -> tuple[float, float]:
    """Demanda activa de la red (kW) y la parte que llega a una fuente en este estado."""
    p_kw = np.real(m.s_carga) * S_BASE * 1000.0
    carga = p_kw > 0
    alimentado = m.alimentado if m.alimentado is not None else np.ones(len(p_kw), dtype=bool)
    return float(np.sum(p_kw[carga])), float(np.sum(p_kw[carga & alimentado]))


def problema_bancos(grafo: Mapping[str, Any], *, candidatos: Sequence[str], kvar_modulo: float,
                    tension_min_pu: float, tension_max_pu: float,
                    contexto: ContextoExperimento | ContextoSintetico, modelo_id: str, modulos_max: int = 3,
                    costo_modulo: float | None = None, origen_costo: str | None = None,
                    factor_carga: float = 1.0, exponente: float = 0.0) -> ProblemaOptimizacion:
    """Los bancos de ``optimizar_bancos`` como problema declarado (048:RF-1, RF-2).

    Una variable entera por barra candidata (módulos de ``kvar_modulo``), la banda de tensión
    como restricción y la inversión con el coste del perfil (sin él, sin valor: 048, T1).
    """
    m = muestra(grafo)
    sis = sistema_de(m)
    pos = {n: i for i, n in enumerate(m.ids)}
    nodos = [c for c in dict.fromkeys(candidatos) if c in pos and not m.fuente[pos[c]]]
    if not nodos:
        raise ValueError('ninguna barra candidata está en el grafo')
    idx = np.array([pos[c] for c in nodos])
    medir = _energizadas(m)
    s_base = m.s_carga * factor_carga
    q_modulo = kvar_modulo / 1000.0 / S_BASE
    referencia_kw, atendida_kw = (x * factor_carga for x in _demanda_kw(m))

    def evaluador(vector: Mapping[str, Any]) -> dict[str, Any]:
        genoma = np.array([vector[n] for n in nodos], dtype=float)
        s = s_base.copy()
        s[idx] -= 1j * genoma * q_modulo
        sol = sis.resolver(s, exponente=exponente)
        if not sol.convergio:
            return {'convergio': False}
        return {'convergio': True, 'objetivos': {'perdidas_kw': sol.perdidas_pu * S_BASE * 1000.0},
                'violaciones': {'tension_pu': violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu)},
                # Los bancos no cambian la topología: la red atiende lo mismo que en su estado actual.
                'demanda_referencia_kw': referencia_kw, 'demanda_atendida_kw': atendida_kw,
                'referencia': {'estado': 'red actual sin bancos nuevos', 'factor_carga': factor_carga}}

    variables = tuple(Variable(n, 'entera', f'módulos de {kvar_modulo:g} kvar', inferior=0, superior=modulos_max,
                               origen='barras candidatas del diagnóstico y módulo de banco del perfil',
                               coste=costo_modulo, origen_coste=origen_costo if costo_modulo is not None else None)
                      for n in nodos)
    return ProblemaOptimizacion(
        nombre='bancos_de_condensadores', variables=variables,
        restricciones=(Restriccion('tension_pu', 'p.u.', f'banda {tension_min_pu}–{tension_max_pu} p.u. de la norma'),),
        objetivos=(Objetivo('inversion', 'coste del perfil', origen='coste'), Objetivo('perdidas_kw', 'kW')),
        contexto=contexto, modelo_id=modelo_id, evaluador=evaluador)


def problema_maniobras(grafo: Mapping[str, Any], *, maniobras: Sequence[str], tension_min_pu: float,
                       tension_max_pu: float, contexto: ContextoExperimento | ContextoSintetico, modelo_id: str,
                       exponente: float = 0.0) -> ProblemaOptimizacion:
    """La reconfiguración de ``reconfigurar`` como problema declarado (048:RF-1, RF-2).

    Una variable binaria por maniobra (1 cerrada). La referencia de demanda es la del estado
    actual de la red: abrir una maniobra que deja carga sin fuente pierde menos solo porque deja
    de alimentarla, y ``evaluar_vector`` lo declara no factible. Los lazos nuevos son violación.
    """
    ramas = {str(r.get('id')) for r in grafo.get('ramas') or []}
    maniobras = [x for x in dict.fromkeys(maniobras) if x in ramas]
    if not maniobras:
        raise ValueError('ninguna maniobra está en el grafo')
    referencia_kw = _demanda_kw(muestra(grafo))[1]
    lazos_fijos = _lazos(muestra(_grafo_con_estados(grafo, dict.fromkeys(maniobras, False))))

    def evaluador(vector: Mapping[str, Any]) -> dict[str, Any]:
        m = muestra(_grafo_con_estados(grafo, {x: bool(vector[x]) for x in maniobras}))
        _total, atendida_kw = _demanda_kw(m)
        sol = sistema_de(m).resolver(m.s_carga, exponente=exponente)
        if not sol.convergio:
            return {'convergio': False, 'demanda_referencia_kw': referencia_kw, 'demanda_atendida_kw': atendida_kw}
        medir = _energizadas(m)
        return {'convergio': True, 'objetivos': {'perdidas_kw': sol.perdidas_pu * S_BASE * 1000.0},
                'violaciones': {'tension_pu': violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu),
                                'lazos': float(max(_lazos(m) - lazos_fijos, 0))},
                'demanda_referencia_kw': referencia_kw, 'demanda_atendida_kw': atendida_kw,
                'referencia': {'estado': 'maniobras en su estado actual'}}

    return ProblemaOptimizacion(
        nombre='reconfiguracion_por_maniobras',
        variables=tuple(Variable(x, 'binaria', 'estado (1 cerrada, 0 abierta)', origen='maniobras del grafo del gemelo')
                        for x in maniobras),
        restricciones=(Restriccion('tension_pu', 'p.u.', f'banda {tension_min_pu}–{tension_max_pu} p.u. de la norma'),
                       Restriccion('lazos', 'lazos', 'red radial: ningún lazo además de los fijos')),
        objetivos=(Objetivo('perdidas_kw', 'kW'),), contexto=contexto, modelo_id=modelo_id, evaluador=evaluador)


def _grafo_con_estados(grafo: Mapping[str, Any], cerradas: Mapping[str, bool]) -> dict:
    return {**grafo, 'nodos': grafo.get('nodos') or {},
            'ramas': [{**r, 'cerrada': cerradas.get(str(r.get('id')), r.get('cerrada', True))}
                      for r in grafo.get('ramas') or []]}


def _lazos(m: Muestra) -> int:
    """Ramas cerradas que unen dos barras ya unidas: los lazos independientes de la red."""
    padre = np.arange(len(m.ids))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = int(padre[i])
        return i

    lazos = 0
    a, b = m.aristas
    for k in range(0, a.shape[0], 2):       # cada rama llega en los dos sentidos, seguidos
        ra, rb = raiz(int(a[k])), raiz(int(b[k]))
        if ra == rb:
            lazos += 1
        else:
            padre[ra] = rb
    return lazos


def reconfigurar(grafo: Mapping[str, Any], *, maniobras: Sequence[str], tension_min_pu: float,
                 tension_max_pu: float, exponente: float = 0.0, semilla: int = 0, poblacion: int = 30,
                 generaciones: int = 60) -> dict[str, Any]:
    """Qué maniobras abrir y cuáles cerrar para perder menos, radial y sin dejar carga sin
    fuente (RF-71). El genoma: 1 cerrada, 0 abierta, por maniobra.

    La red es radial si no tiene más lazos que los que ya tiene con todas las maniobras
    abiertas (las ternas en paralelo y los lazos fijos no se abren con estas maniobras).
    """
    ramas = {str(r.get('id')) for r in grafo.get('ramas') or []}
    maniobras = [x for x in dict.fromkeys(maniobras) if x in ramas]
    if not maniobras:
        return {'factible': False, 'motivo': 'ninguna maniobra está en el grafo', 'confirmar_en_pf': True}
    actual = {str(r.get('id')): bool(r.get('cerrada', True)) for r in grafo.get('ramas') or []}
    m_abierta = muestra(_grafo_con_estados(grafo, dict.fromkeys(maniobras, False)))
    lazos_fijos = _lazos(m_abierta)
    con_carga = np.abs(m_abierta.s_carga) > 0

    def evaluar(genoma: np.ndarray) -> tuple[float, dict]:
        m = muestra(_grafo_con_estados(grafo, {x: bool(g) for x, g in zip(maniobras, genoma, strict=True)}))
        lazos = _lazos(m) - lazos_fijos
        sin_fuente = int(np.sum(con_carga & ~m.alimentado))
        if lazos > 0 or sin_fuente:
            return INFACTIBLE * (1 + lazos + sin_fuente), {'lazos': lazos, 'sin_fuente': sin_fuente}
        sol = sistema_de(m).resolver(m.s_carga, exponente=exponente)
        if not sol.convergio:
            return INFACTIBLE * 2, {'convergio': False}
        medir = _energizadas(m)
        vio = violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu)
        kw = sol.perdidas_pu * S_BASE * 1000.0
        info = {'perdidas_kw': kw, 'v_min': float(sol.v[medir].min()) if medir.any() else None,
                'violacion_pu': vio}
        # Una red que ya incumple no se descarta: gana la que menos se aparta de la norma.
        return (kw if vio <= 0 else INFACTIBLE / 10 * (1 + vio) + kw), info

    inicial = np.array([int(actual[x]) for x in maniobras], dtype=np.int64)
    ga = algoritmo_genetico(lambda g: evaluar(g)[0], [0] * len(maniobras), [1] * len(maniobras),
                            poblacion=poblacion, generaciones=generaciones, semilla=semilla, iniciales=[inicial])
    apt_inicial, antes = evaluar(inicial)
    apt, despues = evaluar(ga.mejor)
    return {'abrir': [x for x, g, i in zip(maniobras, ga.mejor, inicial, strict=True) if not g and i],
            'cerrar': [x for x, g, i in zip(maniobras, ga.mejor, inicial, strict=True) if g and not i],
            'factible': apt < INFACTIBLE / 10, 'antes': antes, 'despues': despues,
            'mejora': apt <= apt_inicial,
            'algoritmos': {'genetico': {'evaluaciones': ga.evaluaciones, 'generaciones': ga.generaciones}},
            'confirmar_en_pf': True}


def optimizar_consigna(grafo: Mapping[str, Any], *, tension_min_pu: float, tension_max_pu: float,
                       inferior_pu: float = 0.95, superior_pu: float = 1.05, factor_carga: float = 1.0,
                       exponente: float = 0.0, semilla: int = 0, generaciones: int = 60) -> dict[str, Any]:
    """La consigna de cada fuente que cumple la norma con las menores pérdidas (RF-72), con jDE.

    Es la obra ``consigna`` de la cabecera (019:RF-12). La factorización no cambia con la
    consigna, así que cada evaluación es un solo flujo.
    """
    m = muestra(grafo)
    sis = sistema_de(m)
    fuentes = [m.ids[i] for i in np.flatnonzero(m.fuente)]
    if not fuentes:
        return {'factible': False, 'motivo': 'la red no tiene fuentes', 'confirmar_en_pf': True}
    medir = _energizadas(m)
    s = m.s_carga * factor_carga
    actual = m.x[m.fuente, 4]

    def estado(u: np.ndarray):
        return sis.resolver(s, exponente=exponente, consigna=u)

    def aptitud(u: np.ndarray) -> float:
        sol = estado(u)
        if not sol.convergio:
            return INFACTIBLE * 2
        vio = violacion_tension(sol.v, medir, tension_min_pu, tension_max_pu)
        kw = sol.perdidas_pu * S_BASE * 1000.0
        return kw if vio <= 0 else INFACTIBLE * (1 + vio)

    de = evolucion_diferencial(aptitud, [inferior_pu] * len(fuentes), [superior_pu] * len(fuentes),
                               generaciones=generaciones, semilla=semilla, iniciales=[actual])

    def resumen(sol) -> dict:
        ok = sol.convergio and medir.any()
        return {'perdidas_kw': sol.perdidas_pu * S_BASE * 1000.0 if sol.convergio else None,
                'v_min': float(sol.v[medir].min()) if ok else None,
                'v_max': float(sol.v[medir].max()) if ok else None}

    return {'consignas': {f: round(float(u), 4) for f, u in zip(fuentes, de.mejor, strict=True)},
            'factible': de.aptitud < INFACTIBLE, 'antes': resumen(estado(actual)),
            'despues': resumen(estado(de.mejor)),
            'algoritmos': {'evolucion_diferencial': {'evaluaciones': de.evaluaciones,
                                                     'generaciones': de.generaciones}},
            'confirmar_en_pf': True}


# ------------------------------------------------------------------ obras del PIDE
def red_del_gemelo(episodios: Sequence[Any]) -> dict | None:
    """La red más reciente de los episodios que la traen, preferida sin perturbar.

    Un escenario del aprendizaje activo lleva la demanda escalada y tramos abiertos: si no
    hay otro, se devuelve con la demanda a su factor 1 y los tramos del escenario cerrados.
    """
    con_red = [e for e in episodios if ((e.topologia or {}).get('grafo') or {}).get('nodos')]
    if not con_red:
        return None

    def perturbado(e) -> bool:
        esc = (e.accion or {}).get('escenario') or {}
        return float(esc.get('factor_carga') or 1.0) != 1.0 or bool(esc.get('tramos_abiertos'))

    limpios = [e for e in con_red if not perturbado(e)]
    e = (limpios or con_red)[-1]
    grafo = e.topologia['grafo']
    esc = (e.accion or {}).get('escenario') or {}
    factor = float(esc.get('factor_carga') or 1.0)
    abiertos = set(esc.get('tramos_abiertos') or ())
    if factor == 1.0 and not abiertos:
        return grafo
    nodos = {n: escalar_nodo(d, 1.0 / factor)
             for n, d in grafo['nodos'].items()}
    ramas = [{**r, 'cerrada': True} if nombre_corto(str(r.get('id'))) in abiertos else r
             for r in grafo.get('ramas') or []]
    return {**grafo, 'nodos': nodos, 'ramas': ramas}


def _camino(m: Muestra, destino: int) -> list[int]:
    """Barras del camino más corto (en tramos) desde una fuente hasta ``destino``."""
    vecinos: dict[int, list[int]] = {}
    a, b = m.aristas
    for u, w in zip(a.tolist(), b.tolist(), strict=True):
        vecinos.setdefault(u, []).append(w)
    previo = {int(s): -1 for s in np.flatnonzero(m.fuente)}
    cola = list(previo)
    while cola and destino not in previo:
        siguiente = []
        for u in cola:
            for w in vecinos.get(u, []):
                if w not in previo:
                    previo[w] = u
                    siguiente.append(w)
        cola = siguiente
    if destino not in previo:
        return []
    camino, u = [], destino
    while u != -1:
        camino.append(u)
        u = previo[u]
    return camino[::-1]


def afinar_bancos_pide(obras: list[dict], grafo: Mapping[str, Any], *, tension_min_pu: float,
                       tension_max_pu: float, bancos_kvar: Mapping[float, float], tasa_demanda: float = 0.0,
                       costo_modulo: float | None = None, valor_kw_perdidas: float | None = None,
                       candidatos_max: int = 30, semilla: int = 0) -> list[str]:
    """Sustituye la ubicación y el tamaño de los bancos que propone el PIDE por los del
    algoritmo genético y NSGA-II, sobre la red del gemelo (RF-73).

    Por alimentador y año, las candidatas son las barras de media del camino de la fuente a
    cada barra con problema (donde un banco sube la tensión). La demanda se escala al año de
    la obra con la tasa del perfil. Si el optimizador no cumple la norma o no reconoce la
    barra, la obra se queda como estaba y se dice por qué. Cada banco sigue pasando por la
    simulación en DIgSILENT antes de aplicarse (RF-46).
    """
    avisos: list[str] = []
    m = muestra(grafo)
    por_nombre: dict[str, list[int]] = {}
    for i, n in enumerate(m.ids):
        por_nombre.setdefault(nombre_corto(n), []).append(i)
    kv = 10 ** m.x[:, 0]
    grupos: dict[tuple, list[dict]] = {}
    for o in obras:
        if (o.get('obra_011') or {}).get('clase') == 'condensador' and not o.get('descartada'):
            grupos.setdefault((o['obra_011'].get('alimentador'), int(o.get('anio') or 0)), []).append(o)
    for (alimentador, anio), lista in sorted(grupos.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        destinos = []
        for o in lista:
            hallados = por_nombre.get(o['obra_011']['barra']) or []
            if len(hallados) == 1:
                destinos.append(hallados[0])
            else:
                avisos.append(f"{o['codigo']}: la barra {o['obra_011']['barra']!r} "
                              f"{'no está' if not hallados else 'está repetida'} en la red del gemelo; "
                              'queda el banco del diagnóstico')
        candidatos = list(dict.fromkeys(i for d in destinos for i in _camino(m, d)
                                        if kv[i] >= 1 and not m.fuente[i]))
        if not candidatos or not bancos_kvar:
            continue
        if len(candidatos) > candidatos_max:
            candidatos = [candidatos[int(k)] for k in np.linspace(0, len(candidatos) - 1, candidatos_max)]
        kv_mt = float(np.median(kv[candidatos]))
        kvar = min(bancos_kvar.items(), key=lambda x: abs(x[0] - kv_mt))[1]
        r = optimizar_bancos(grafo, candidatos=[m.ids[i] for i in candidatos], kvar_modulo=kvar,
                             tension_min_pu=tension_min_pu, tension_max_pu=tension_max_pu,
                             costo_modulo=costo_modulo, valor_kw_perdidas=valor_kw_perdidas,
                             factor_carga=(1 + tasa_demanda) ** anio, semilla=semilla)
        resumen = {k: r.get(k) for k in ('factible', 'inversion', 'perdidas_kw', 'perdidas_kw_base', 'v_min',
                                          'v_min_base', 'algoritmos', 'frente', 'alternativas')}
        if not r['factible'] or not r['bancos']:
            motivo = ('con bancos no se cumple la norma en la red del gemelo' if not r['factible']
                      else 'la red del gemelo ya cumple sin bancos')
            for o in lista:
                o['optimizacion'] = {**resumen, 'aplicada': False, 'motivo': motivo}
            avisos.append(f'{alimentador} año {anio:02d}: {motivo}; quedan los bancos del diagnóstico')
            continue
        bancos = sorted(r['bancos'], key=lambda x: -x['q_kvar'])
        for k, o in enumerate(lista):
            if k < len(bancos):
                b = bancos[k]
                o['obra_011'] = {**o['obra_011'], 'barra': b['barra'], 'q_kvar': b['q_kvar'],
                                 'escalones': b['modulos']}
                o['elemento'] = b['barra']
                o['optimizacion'] = {**resumen, 'aplicada': True, 'metodo': 'algoritmo_genetico+nsga2'}
            else:
                o['obra_011'] = None
                o['motivo_sin_obra'] = 'el algoritmo genético cumple la norma sin este banco'
                o['optimizacion'] = {**resumen, 'aplicada': False}
        if len(bancos) > len(lista):
            lista[0]['obras_011_extra'] = [
                {**lista[0]['obra_011'], 'barra': b['barra'], 'q_kvar': b['q_kvar'], 'escalones': b['modulos']}
                for b in bancos[len(lista):]]
    return avisos


def verificar_top_k(alternativas: Sequence[Mapping[str, Any]], medir: Callable[[Mapping[str, Any]], Mapping | None],
                    *, tolerancia_v_pu: float, tolerancia_perdidas: float = 0.2,
                    tolerancia_perdidas_kw: float | None = None, contexto: ContextoExperimento | None = None,
                    limites: Limites | None = None,
                    guardar: Callable[[Mapping[str, Any], Mapping | None, str], None] = lambda *_a: None
                    ) -> dict[str, Any]:
    """La primera de las k mejores que DIgSILENT confirma (027:RF-14 a RF-16, 044:RF-6, RF-7).

    ``medir(alternativa)`` la simula en DIgSILENT y da, además de ``converge``, ``v_min`` y
    ``perdidas_kw``, lo que ``validar_medicion_nativa`` exige: ``contexto``, ``unidades``, ``flujo``,
    ``reabierto``, ``revertido`` y la ``referencia`` vinculada. Antes bastaba ``converge=True`` con dos
    cifras parecidas; una obra así podía aceptarse con una línea sobrecargada. Si no converge, si la
    medición está incompleta, si se aparta de lo predicho más que la tolerancia (tensión mínima en p.u.,
    pérdidas en fracción, o en kW con ``tolerancia_perdidas_kw`` si lo predicho es cero) o si ``evaluar``
    no la acepta por su caso y norma, se descarta, se guarda como episodio (``guardar``) y se prueba la
    siguiente. La elegida lleva la evaluación del gemelo y la de DIgSILENT.
    """
    politica = {'tolerancia_v_pu': tolerancia_v_pu, 'tolerancia_perdidas': tolerancia_perdidas,
                'tolerancia_perdidas_kw': tolerancia_perdidas_kw}
    comprobar_tolerancias(politica)
    descartadas = []
    for alt in alternativas:
        if alt.get('fuera_de_dominio'):
            # 045:RF-9: lo predicho fuera de lo validado no se compara ni se da por diseño.
            motivo = 'la predicción está fuera del dominio validado del modelo'
            guardar(alt, None, motivo)
            descartadas.append({'alternativa': dict(alt), 'motivo': motivo, 'digsilent': {}})
            continue
        m = medir(alt)
        if not m or not m.get('converge'):
            motivo = 'el flujo de DIgSILENT no converge con ella'
        else:
            validacion = validar_medicion_nativa(alt, m, contexto, politica=politica)
            motivo = '; '.join(validacion['motivos']) or None
            if motivo is None:
                juicio, motivo = _juzgar_por_su_caso(m, contexto, limites)
                if motivo is None:
                    return {'elegida': dict(alt), 'gemelo': {k: alt.get(k) for k in ('v_min', 'perdidas_kw')},
                            'digsilent': dict(m), 'descartadas': descartadas, 'verificada': True,
                            'evaluacion': juicio, 'validacion': validacion}
        guardar(alt, m, motivo)
        descartadas.append({'alternativa': dict(alt), 'motivo': motivo, 'digsilent': dict(m or {})})
    return {'elegida': None, 'descartadas': descartadas, 'verificada': False}


def _juzgar_por_su_caso(medicion: Mapping[str, Any], contexto: ContextoExperimento,
                        limites: Limites | None) -> tuple[dict[str, Any] | None, str | None]:
    """El veredicto de ``evaluacion.evaluar`` sobre el flujo ya validado: solo ``accepted`` confirma."""
    try:
        caso = Caso(contexto.case_role)
    except ValueError:
        return None, f'el caso {contexto.case_role} no tiene criterio de evaluación propio'
    juicio = evaluar(caso, medicion['flujo'], convergio=True, revertido=medicion['revertido'],
                     reabierto=medicion['reabierto'], limites=limites,
                     calibracion_cuadra=medicion.get('calibracion_cuadra'),
                     referencia=(medicion.get('referencia') or {}).get('flujo'))
    publico = {'clase': juicio.clase.value, 'violaciones': list(juicio.violaciones),
               'diagnostico': list(juicio.diagnostico), 'bloqueos': list(juicio.bloqueos)}
    if juicio.clase is Clase.ACCEPTED:
        return publico, None
    razones = list(juicio.bloqueos) + list(juicio.violaciones)
    return publico, f'evaluación nativa {juicio.clase.value}: ' + ('; '.join(razones[:5]) or 'sin motivo')
