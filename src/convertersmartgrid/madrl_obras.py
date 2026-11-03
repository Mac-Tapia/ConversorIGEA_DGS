"""Entorno multiagente de obras y sus controles, para el piloto MADRL (spec 074).

La revisión del 2026-11-02 no halló MADRL público para planificar obras, y podría no superar a NSGA-II ni a
la escalera. Por eso se mide primero: el entorno, la máscara y los controles existen antes que el
aprendizaje, y una puerta decide si este sigue. Cada alimentador es un agente; comparten recompensa porque
un alimentador alivia a otro al repartir carga en una misma SET.

La física es el barrido radial del oráculo: rápida, pero sin confirmar. Nada de aquí escribe en DIgSILENT.
"""
from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .digital_twin.oraculo import ModeloRadial, muestra

#: La acción 0 de cada agente: no hacer nada.
NINGUNA = 0
#: Lo que baja un multiplicador en un episodio que cumple.
_HOLGURA = 0.01


class EntornoError(ValueError):
    """Un grafo o unos parámetros con los que no se puede plantear el piloto."""


@dataclass(frozen=True)
class ParametrosObras:
    """Límites y costos, siempre declarados: sin valor por defecto de ninguna empresa."""

    tension_min_pu: float
    tension_max_pu: float
    cargabilidad_max_pct: float
    banco_mvar: float
    costo_banco: float
    costo_terna_km: float | None = None
    candidatos: int = 8
    max_bancos: int = 3
    max_pasos: int = 8


@dataclass(frozen=True)
class Accion:
    tipo: str
    elemento: str
    costo: float


@dataclass(frozen=True)
class Evaluacion:
    """Lo que dice la física de un estado: las violaciones se miden, no se suponen."""

    subtension: float
    sobretension: float
    sobrecarga: float
    vm_min: float

    @property
    def en_norma(self) -> bool:
        return self.subtension == 0 and self.sobretension == 0 and self.sobrecarga == 0


def cargas_de_rama(m, v: np.ndarray, th: np.ndarray) -> dict[str, float]:
    """La carga en % de cada rama, sumando las corrientes aguas abajo en el árbol de cada fuente.

    Dividir la caída entre la impedancia daba SM218 con un tramo al 202 % que DIgSILENT mide al 20 %: el
    oráculo sube a un mínimo la impedancia de los tramos cortos, y la caída ya no corresponde a esa z.
    """
    n = len(m.ids)
    vecinos: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for k in range(m.aristas.shape[1]):
        vecinos[m.aristas[0, k]].append((int(m.aristas[1, k]), k))
    padre, por = [-1] * n, [-1] * n
    visto, orden = [False] * n, []
    for s in np.flatnonzero(m.fuente):
        pila = [int(s)]
        visto[s] = True
        while pila:
            u = pila.pop()
            orden.append(u)
            for w, k in vecinos[u]:
                if not visto[w]:
                    visto[w], padre[w], por[w] = True, u, k
                    pila.append(w)
    fasor = np.where(v > 0, v, 1.0) * np.exp(1j * th)
    corriente = np.conj(m.s_carga / fasor)
    cargas: dict[str, float] = {}
    for u in reversed(orden):
        if padre[u] >= 0:
            corriente[padre[u]] += corriente[u]
            if m.inom[por[u]] > 0:
                cargas[m.ramas[por[u]]] = 100 * abs(corriente[u]) / m.inom[por[u]]
    return cargas


def evaluar_grafo(grafo: Mapping[str, Any], p: ParametrosObras, nodos: set[str] | None = None) -> Evaluacion:
    """Suma de lo que cada barra de media y cada rama se pasa de su límite (074:RF-1)."""
    m = muestra(grafo)
    r = ModeloRadial().predecir(grafo)
    v, th = np.asarray(r['v']), np.asarray(r['theta'])
    kv = 10 ** m.x[:, 0]
    dentro = np.array([(nodos is None or n in nodos) for n in m.ids])
    # Una barra sin fuente sale con 0 p.u.: no es una subtensión, es una isla (spec 024).
    medibles = dentro & (kv >= 1) & (v > 0) & ~m.fuente
    if not medibles.any():
        return Evaluacion(0.0, 0.0, 0.0, 1.0)
    sub = float(np.maximum(p.tension_min_pu - v[medibles], 0).sum())
    sob = float(np.maximum(v[medibles] - p.tension_max_pu, 0).sum())
    ramas_dentro = {m.ramas[k] for k in range(m.aristas.shape[1]) if dentro[m.aristas[0, k]]}
    sobrecarga = sum(max(c - p.cargabilidad_max_pct, 0.0) for rama, c in cargas_de_rama(m, v, th).items()
                     if rama in ramas_dentro)
    return Evaluacion(sub, sob, float(sobrecarga), float(v[medibles].min()))


def fidelidad(grafo: Mapping[str, Any], tensiones: Mapping[str, float], cargas: Mapping[str, float], *,
              max_error_pu: float = 0.01, max_error_carga_pct: float = 10.0, peor_carga_pct: float = 25.0) -> dict[str, Any]:
    """Si el entorno reproduce lo que midió DIgSILENT en esa misma red (074:RF-7).

    Una política que aprende contra una física equivocada aprende a resolver otra red: NJA202 da 0,683 p.u.
    de mínima donde DIgSILENT mide 0,532. Sin medida comparable, tampoco pasa. El peor error también cuenta:
    SM218 tiene 0,9 % de error medio y una rama a 245 %, y una obra se decide por esa rama, no por la media.
    """
    m = muestra(grafo)
    r = ModeloRadial().predecir(grafo)
    v, th = np.asarray(r['v']), np.asarray(r['theta'])
    dv = [abs(v[i] - tensiones[n]) for i, n in enumerate(m.ids) if v[i] > 0 and (tensiones.get(n) or 0) > 0]
    propias = cargas_de_rama(m, v, th)
    dc = [abs(c - cargas[rama]) for rama, c in propias.items() if cargas.get(rama) is not None]
    if not dv or not dc:
        return {'vale': False, 'motivo': 'no hay medidas de DIgSILENT que comparar en esta red'}
    error_v, error_c = float(np.mean(dv)), float(np.mean(dc))
    peor = float(np.max(dc))
    vale = error_v <= max_error_pu and error_c <= max_error_carga_pct and peor <= peor_carga_pct
    return {'vale': vale, 'error_tension_pu': error_v, 'error_tension_max_pu': float(np.max(dv)), 'error_carga_pct': error_c,
            'error_carga_max_pct': peor, 'barras': len(dv), 'ramas': len(dc),
            'motivo': 'el entorno reproduce lo medido' if vale else
            f'error medio {error_v:.4f} p.u. y {error_c:.1f} % de carga, peor rama {peor:.0f} %: sobre lo admitido'}


def zonas_por_fuente(grafo: Mapping[str, Any]) -> dict[str, list[str]]:
    """Las barras que alimenta cada fuente, en ramas cerradas: un agente por zona (074:RF-1).

    Se deduce de la red y no de una tabla de alimentadores, para valer con cualquier empresa. Varias
    cabeceras bajo una misma red externa quedan como un solo agente.
    """
    nodos = grafo.get('nodos') or {}
    vecinos: dict[str, list[str]] = {}
    for r in grafo.get('ramas') or []:
        if r.get('cerrada', True) and r.get('desde') in nodos and r.get('hasta') in nodos:
            vecinos.setdefault(r['desde'], []).append(r['hasta'])
            vecinos.setdefault(r['hasta'], []).append(r['desde'])
    vistos: set[str] = set()
    zonas: dict[str, list[str]] = {}
    for fuente in sorted(n for n, d in nodos.items() if d.get('fuente')):
        if fuente in vistos:
            continue
        pila, zona = [fuente], []
        vistos.add(fuente)
        while pila:
            u = pila.pop()
            zona.append(u)
            for w in vecinos.get(u, []):
                if w not in vistos:
                    vistos.add(w)
                    pila.append(w)
        zonas[fuente] = sorted(zona)
    return zonas


def candidatos_de(grafo: Mapping[str, Any], nodos: set[str], p: ParametrosObras) -> list[Accion]:
    """Las obras que puede elegir un agente: un espacio fijo, para que política y NSGA-II vean lo mismo.

    Los bancos van en las barras de menor tensión, repartidas a lo largo de la lista. La terna exige el
    metrado de su rama y un costo declarado: sin ellos no se ofrece, y no se supone un largo (072:RF-15).
    """
    m = muestra(grafo)
    v = np.asarray(ModeloRadial().predecir(grafo)['v'])
    kv = 10 ** m.x[:, 0]
    barras = [i for i, n in enumerate(m.ids) if n in nodos and kv[i] >= 1 and v[i] > 0 and not m.fuente[i]]
    barras.sort(key=lambda i: (v[i], m.ids[i]))
    paso = max(len(barras) // max(p.candidatos, 1), 1)
    acciones = [Accion('banco', m.ids[i], p.costo_banco) for i in barras[::paso][:p.candidatos]]
    if p.costo_terna_km is not None:
        ramas = [r for r in grafo.get('ramas') or []
                 if r.get('clase') == 'ElmLne' and r.get('desde') in nodos and r.get('km') and r.get('cerrada', True)]
        ramas.sort(key=lambda r: (-float(r.get('r_ohm') or 0), str(r['id'])))
        acciones += [Accion('terna', str(r['id']), float(r['km']) * p.costo_terna_km) for r in ramas[:p.candidatos]]
    return acciones


def aplicar(grafo: dict[str, Any], accion: Accion, p: ParametrosObras) -> None:
    """Una obra sobre el grafo: el banco resta reactiva; la terna en paralelo reparte impedancia y corriente."""
    if accion.tipo == 'banco':
        nodo = grafo['nodos'][accion.elemento]
        nodo['q_mvar'] = float(nodo.get('q_mvar') or 0.0) - p.banco_mvar
    elif accion.tipo == 'terna':
        rama = next(r for r in grafo['ramas'] if str(r['id']) == accion.elemento)
        rama['r_ohm'], rama['x_ohm'] = float(rama.get('r_ohm') or 0) / 2, float(rama.get('x_ohm') or 0) / 2
        rama['inom_ka'] = float(rama.get('inom_ka') or 0) * 2
    else:
        raise EntornoError(f'obra desconocida: {accion.tipo}')


@dataclass
class Lagrange:
    """Las penalidades que se aprenden (074:RF-4): suben mientras se incumple y bajan al cumplir.

    Lo que el agente no aprende es la recompensa: si eligiera sus penalidades, le bastaría con bajarlas.
    """

    tasa: float = 0.05
    multiplicadores: dict[str, float] = field(default_factory=lambda: {'subtension': 1.0, 'sobretension': 1.0, 'sobrecarga': 1.0})

    def penalidad(self, e: Evaluacion) -> float:
        return sum(lam * getattr(e, k) for k, lam in self.multiplicadores.items())

    def actualizar(self, e: Evaluacion) -> None:
        for k, lam in self.multiplicadores.items():
            self.multiplicadores[k] = max(lam + self.tasa * (getattr(e, k) - _HOLGURA), 0.0)


class EntornoObras:
    """Un agente por alimentador, pasos simultáneos y recompensa compartida (074:RF-1, RF-2, RF-4)."""

    def __init__(self, grafo: Mapping[str, Any], zonas: Mapping[str, Sequence[str]], p: ParametrosObras,
                 lagrange: Lagrange | None = None, escala_costo: float | None = None) -> None:
        if not zonas:
            raise EntornoError('El piloto necesita al menos un alimentador con sus barras.')
        self.original, self.p = grafo, p
        self.zonas = {a: set(n) for a, n in zonas.items()}
        self.lagrange = lagrange or Lagrange()
        self.acciones = {a: candidatos_de(grafo, n, p) for a, n in self.zonas.items()}
        self.escala = escala_costo or max(p.costo_banco, 1.0)
        self.presupuesto = max(sum(x.costo for lista in self.acciones.values() for x in lista) / self.escala, 1.0)
        self.inicial = evaluar_grafo(grafo, p)
        self.reiniciar()

    def reiniciar(self) -> None:
        self.grafo = copy.deepcopy(dict(self.original))
        self.hechas: dict[str, set[int]] = {a: set() for a in self.zonas}
        self.costo = 0.0
        self.pasos = 0
        self.estado = evaluar_grafo(self.grafo, self.p)

    def mascara(self, agente: str) -> np.ndarray:
        """Qué puede elegir un agente: la acción 0 siempre; una obra, solo si hay problemas en su zona."""
        acciones = self.acciones[agente]
        m = np.zeros(len(acciones) + 1, dtype=bool)
        m[NINGUNA] = True
        if evaluar_grafo(self.grafo, self.p, self.zonas[agente]).en_norma:
            return m                                                     # obras solo si hay problemas
        hechas = self.hechas[agente]
        bancos = sum(acciones[i].tipo == 'banco' for i in hechas)
        libres = [i for i in range(len(acciones)) if i not in hechas]
        quedan_bancos = bancos < self.p.max_bancos and any(acciones[i].tipo == 'banco' for i in libres)
        for i in libres:
            if acciones[i].tipo == 'banco':
                m[i + 1] = quedan_bancos
            else:
                m[i + 1] = not quedan_bancos                             # la escalera: primero los bancos
        return m

    def paso(self, elegidas: Mapping[str, int]) -> tuple[float, bool]:
        """Aplica una acción por agente; devuelve la recompensa común y si terminó el episodio."""
        gasto = 0.0
        mascaras = {a: self.mascara(a) for a in elegidas}
        for agente, indice in elegidas.items():
            if indice == NINGUNA:
                continue
            if not mascaras[agente][indice]:
                raise EntornoError(f'{agente}: la acción {indice} está fuera de su máscara')
            accion = self.acciones[agente][indice - 1]
            aplicar(self.grafo, accion, self.p)
            self.hechas[agente].add(indice - 1)
            gasto += accion.costo
        self.costo += gasto
        self.pasos += 1
        self.estado = evaluar_grafo(self.grafo, self.p)
        fin = self.estado.en_norma or self.pasos >= self.p.max_pasos or not gasto
        # La violación se cobra una vez, por cómo queda la red. Cobrada en cada paso, cada obra alargaba el
        # episodio y sumaba castigo: MaskablePPO aprendió a terminar sin hacer nada, con el multiplicador en 27.
        return -gasto / self.escala - (self.penalidad_final() if fin else 0.0), fin

    def relativa(self) -> Evaluacion:
        """Lo que queda de cada violación frente a la inicial: las sumas en p.u. no se comparan con un costo."""
        def parte(ahora: float, inicio: float) -> float:
            return ahora / inicio if inicio else 0.0

        return Evaluacion(parte(self.estado.subtension, self.inicial.subtension),
                          parte(self.estado.sobretension, self.inicial.sobretension),
                          parte(self.estado.sobrecarga, self.inicial.sobrecarga), self.estado.vm_min)

    def penalidad_final(self) -> float:
        """Dejar el problema entero cuesta al menos todas las obras: si no, rendirse sale más barato que arreglar.

        Con la violación en p.u., dejar la red fuera de norma costaba 2,6 y arreglarla, 5. El cargo fijo es
        porque la puerta pide norma, sin términos medios: en proporción a lo que falta, MaskablePPO se quedaba
        en 0,9472 p.u. con un banco menos.
        """
        if self.estado.en_norma:
            return 0.0
        return self.presupuesto * (1.0 + self.lagrange.penalidad(self.relativa()))

    def obras(self) -> list[str]:
        return sorted(f'{a}:{self.acciones[a][i].tipo}:{self.acciones[a][i].elemento}' for a, h in self.hechas.items() for i in h)


class EntornoPlano:
    """Una obra por paso en un espacio fijo: la forma que pide MaskablePPO, el control del piloto (074:RF-9).

    No depende de ninguna biblioteca de aprendizaje; el adaptador a gymnasium vive en la herramienta. La
    acción 0 termina el episodio; las penalidades se actualizan al terminar, con el estado final.
    """

    def __init__(self, entorno: EntornoObras) -> None:
        self.e = entorno
        self.todas = [(a, i + 1) for a, lista in entorno.acciones.items() for i in range(len(lista))]
        self.n_acciones = len(self.todas) + 1
        self.tam_observacion = 4 + 2 * len(self.todas)

    def reiniciar(self) -> np.ndarray:
        self.e.reiniciar()
        return self.observar()

    def observar(self) -> np.ndarray:
        x = self.e.estado
        obs = [x.vm_min, x.subtension, x.sobretension, x.sobrecarga / 100]
        for a, i in self.todas:
            obs += [float(i - 1 in self.e.hechas[a]), self.e.acciones[a][i - 1].costo / self.e.escala]
        return np.asarray(obs, dtype=np.float32)

    def mascara(self) -> np.ndarray:
        por_agente = {a: self.e.mascara(a) for a in self.e.zonas}
        return np.array([True] + [bool(por_agente[a][i]) for a, i in self.todas], dtype=bool)

    def paso(self, indice: int) -> tuple[np.ndarray, float, bool]:
        elegidas = {} if indice == 0 else dict([self.todas[indice - 1]])
        recompensa, fin = self.e.paso(elegidas)
        if fin:
            self.e.lagrange.actualizar(self.e.relativa())
        return self.observar(), recompensa, fin


def resultado(entorno: EntornoObras, nombre: str, evaluaciones: int) -> dict[str, Any]:
    return {'control': nombre, 'en_norma': entorno.estado.en_norma, 'costo': entorno.costo, 'vm_min': entorno.estado.vm_min,
            'obras': entorno.obras(), 'evaluaciones': evaluaciones}


def control_escalera(entorno: EntornoObras) -> dict[str, Any]:
    """La referencia sin aprendizaje: en cada paso, cada agente toma la primera obra que su máscara permite."""
    entorno.reiniciar()
    n = 0
    while True:
        elegidas = {}
        for a in entorno.zonas:
            permitidas = np.flatnonzero(entorno.mascara(a))
            elegidas[a] = int(permitidas[1]) if len(permitidas) > 1 else NINGUNA
        _, fin = entorno.paso(elegidas)
        n += 1
        if fin:
            return resultado(entorno, 'escalera', n)


def control_nsga2(entorno: EntornoObras, *, generaciones: int = 30, poblacion: int = 40, semilla: int = 1) -> dict[str, Any]:
    """NSGA-II sobre las mismas obras: minimiza costo y violación, sin la máscara de la escalera (074:RF-5)."""
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.operators.crossover.pntx import TwoPointCrossover
    from pymoo.operators.mutation.bitflip import BitflipMutation
    from pymoo.operators.sampling.rnd import BinaryRandomSampling
    from pymoo.optimize import minimize

    todas = [(a, x) for a, lista in entorno.acciones.items() for x in lista]
    if not todas:
        entorno.reiniciar()
        return resultado(entorno, 'nsga2', 0)
    p, base = entorno.p, entorno.original
    cuenta = [0]

    def medir(bits) -> tuple[float, float]:
        g = copy.deepcopy(dict(base))
        costo = 0.0
        for b, (_a, accion) in zip(bits, todas, strict=True):
            if b:
                aplicar(g, accion, p)
                costo += accion.costo
        e = evaluar_grafo(g, p)
        cuenta[0] += 1
        return costo, e.subtension + e.sobretension + e.sobrecarga

    class Problema(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(n_var=len(todas), n_obj=2, xl=0, xu=1, vtype=bool)

        def _evaluate(self, x, out, *_a, **_k) -> None:
            out['F'] = list(medir(x))

    final = minimize(Problema(), NSGA2(pop_size=poblacion, sampling=BinaryRandomSampling(), crossover=TwoPointCrossover(),
                                       mutation=BitflipMutation(), eliminate_duplicates=True),
                     ('n_gen', generaciones), seed=semilla, verbose=False)
    xs = np.atleast_2d(final.X)
    fs = np.atleast_2d(final.F)
    validos = np.flatnonzero(fs[:, 1] <= 1e-9)
    # Entre las que cumplen, la más barata; si ninguna cumple, la que menos incumple.
    mejor = validos[np.argmin(fs[validos, 0])] if len(validos) else int(np.argmin(fs[:, 1]))
    entorno.reiniciar()
    for b, (a, accion) in zip(xs[mejor], todas, strict=True):
        if b:
            aplicar(entorno.grafo, accion, p)
            entorno.hechas[a].add(entorno.acciones[a].index(accion))
            entorno.costo += accion.costo
    entorno.estado = evaluar_grafo(entorno.grafo, p)
    return resultado(entorno, 'nsga2', cuenta[0])


def puerta_del_aprendizaje(aprendido: Sequence[Mapping[str, Any]], referencia: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Si el piloto sigue: en alimentadores no vistos, 100 % en norma y costo no peor que NSGA-II (074:RF-6)."""
    if not aprendido or len(aprendido) != len(referencia):
        return {'sigue': False, 'motivo': 'hacen falta los mismos alimentadores no vistos en los dos'}
    en_norma = sum(bool(x['en_norma']) for x in aprendido) / len(aprendido)
    costo, base = sum(x['costo'] for x in aprendido), sum(x['costo'] for x in referencia)
    if en_norma < 1:
        return {'sigue': False, 'en_norma': en_norma, 'motivo': f'solo {en_norma:.0%} queda en norma'}
    if costo > base:
        return {'sigue': False, 'en_norma': en_norma, 'motivo': f'cuesta {costo:,.0f} frente a {base:,.0f} de la referencia'}
    return {'sigue': True, 'en_norma': en_norma, 'motivo': f'cuesta {costo:,.0f} frente a {base:,.0f} de la referencia'}


def comparar_controles(grafo: Mapping[str, Any], zonas: Mapping[str, Sequence[str]], p: ParametrosObras,
                       medir_nsga2: Callable[..., dict[str, Any]] = control_nsga2) -> dict[str, Any]:
    """Los dos controles sobre la misma red: la referencia que el aprendizaje tendrá que superar."""
    entorno = EntornoObras(grafo, zonas, p)
    inicio = entorno.estado
    return {'inicio': {'en_norma': inicio.en_norma, 'vm_min': inicio.vm_min, 'subtension': inicio.subtension,
                       'sobrecarga': inicio.sobrecarga},
            'acciones': {a: len(x) for a, x in entorno.acciones.items()},
            'escalera': control_escalera(entorno), 'nsga2': medir_nsga2(entorno)}
