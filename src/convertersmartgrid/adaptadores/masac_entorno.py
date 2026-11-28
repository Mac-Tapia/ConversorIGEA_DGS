"""Entorno multiagente de obras del agente MASAC: alimentadores, SET y sistemas eléctricos (spec 114, T1).

Amplía el piloto de la 074, que tenía un agente por alimentador y solo bancos y ternas. El usuario pidió el 2026-11-26
agentes de alimentador, de SET y de sistema eléctrico: el alimentador pone sus obras, la SET mueve las tomas de sus
transformadores y transfiere carga entre sus alimentadores, y el sistema fija la consigna de sus fuentes y transfiere
entre SET. Es un Dec-POMDP: cada agente ve solo su parte de la red y lo que le pasa el nivel de arriba, y la recompensa
es común (114:RF-1).

Los pasos los resuelve el motor abierto o el oráculo, nunca DIgSILENT: es caro, tiene una sola licencia y solo confirma
la propuesta final (114:RF-4). Nada de aquí escribe en DIgSILENT ni en la red de entrada: cada episodio trabaja sobre
una copia.

La API es la de ``pettingzoo.ParallelEnv``. PettingZoo y gymnasium van aparte del ``.venv`` (``requirements-madrl.txt``);
sin ellos, el entorno ofrece la misma API con espacios propios, para que proponer y probar no dependan del entrenamiento
(114:RF-15).
"""
from __future__ import annotations

import copy
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .digital_twin.motores_flujo import resolver_con
from .digital_twin.oraculo import S_BASE, ModeloRadial, muestra, sistema_de
from .madrl_obras import (
    Accion,
    Evaluacion,
    Lagrange,
    ParametrosObras,
    aplicar,
    candidatos_de,
    cargas_de_rama,
    evaluar_flujo,
    zonas_por_alimentador,
    zonas_por_fuente,
)

try:  # 114:RF-15: con PettingZoo, el entorno es un ParallelEnv de verdad
    from pettingzoo import ParallelEnv as _BaseParalela
except ImportError:  # pragma: no cover - depende de lo instalado
    class _BaseParalela:  # type: ignore[no-redef]
        """La misma forma que ``pettingzoo.ParallelEnv``, sin la biblioteca."""

        metadata: dict[str, Any] = {}

        @property
        def unwrapped(self):
            return self

try:
    from gymnasium import spaces as _gym_spaces
except ImportError:  # pragma: no cover - depende de lo instalado
    _gym_spaces = None

#: Los tres niveles de la red, de abajo arriba.
NIVELES = ('alimentador', 'set', 'sistema')
#: La acción 0 de todos los agentes: no hacer nada.
NADA = 0


class EntornoAgenteError(ValueError):
    """Una red o unos parámetros con los que no se puede plantear el entorno."""


# ------------------------------------------------------------------ espacios sin gymnasium (114:RF-15)
class EspacioCaja:
    """Un vector con sus límites, como ``gymnasium.spaces.Box``."""

    def __init__(self, bajo: float, alto: float, n: int, dtype) -> None:
        self.low, self.high, self.shape, self.dtype = bajo, alto, (n,), np.dtype(dtype)
        self._rng = np.random.default_rng()

    def contains(self, x) -> bool:
        x = np.asarray(x)
        return x.shape == self.shape and x.dtype == self.dtype and bool(np.all((x >= self.low) & (x <= self.high)))

    def seed(self, semilla: int | None = None) -> None:
        self._rng = np.random.default_rng(semilla)

    def sample(self):
        if np.issubdtype(self.dtype, np.integer):
            return self._rng.integers(int(self.low), int(self.high) + 1, self.shape).astype(self.dtype)
        return self._rng.standard_normal(self.shape).astype(self.dtype)


class EspacioDiscreto:
    """Una acción entre ``n``, como ``gymnasium.spaces.Discrete``; ``sample`` respeta la máscara."""

    def __init__(self, n: int) -> None:
        self.n = n
        self._rng = np.random.default_rng()

    def contains(self, x) -> bool:
        return isinstance(x, (int, np.integer)) and 0 <= int(x) < self.n

    def seed(self, semilla: int | None = None) -> None:
        self._rng = np.random.default_rng(semilla)

    def sample(self, mask=None) -> int:
        validas = np.arange(self.n) if mask is None else np.flatnonzero(np.asarray(mask))
        return int(self._rng.choice(validas))


class EspacioDict:
    """Observación con su máscara, como ``gymnasium.spaces.Dict``."""

    def __init__(self, partes: Mapping[str, Any]) -> None:
        self.spaces = dict(partes)

    def contains(self, x) -> bool:
        return isinstance(x, Mapping) and x.keys() == self.spaces.keys() and all(
            e.contains(x[k]) for k, e in self.spaces.items())

    def seed(self, semilla: int | None = None) -> None:
        for e in self.spaces.values():
            e.seed(semilla)


def _espacio_observacion(n_obs: int, n_acciones: int):
    if _gym_spaces is not None:
        return _gym_spaces.Dict({'observation': _gym_spaces.Box(-np.inf, np.inf, (n_obs,), np.float32),
                                 'action_mask': _gym_spaces.Box(0, 1, (n_acciones,), np.int8)})
    return EspacioDict({'observation': EspacioCaja(-np.inf, np.inf, n_obs, np.float32),
                        'action_mask': EspacioCaja(0, 1, n_acciones, np.int8)})


def _espacio_accion(n_acciones: int):
    return _gym_spaces.Discrete(n_acciones) if _gym_spaces is not None else EspacioDiscreto(n_acciones)


# ------------------------------------------------------------------ evaluadores del paso (114:RF-4)
@dataclass
class MotorAbierto:
    """El flujo de la red con el motor abierto de la 083 (Z-bus y, si no converge, Newton).

    Respeta los lazos que deja una transferencia a medio hacer, que el barrido radial no ve. Sin solución, la física es
    el barrido del oráculo, y se dice: un paso sin flujo no puede dar 0 p.u. en todas las barras.
    """

    motor: str = 'auto'
    nombre: str = 'motor_abierto'

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]:
        m = muestra(grafo)
        sol, decidio = resolver_con(sistema_de(m), m.s_carga, self.motor)
        if not sol.convergio:
            radial = ModeloRadial().predecir(grafo)
            return {**radial, 'convergio': False, 'motor': decidio, 'modelo': self.nombre}
        return {'ids': m.ids, 'v': sol.v, 'theta': sol.theta, 'perdidas_mw': sol.perdidas_pu * S_BASE,
                'convergio': True, 'motor': decidio, 'modelo': self.nombre}


def perdidas_estimadas(m, v: np.ndarray, th: np.ndarray) -> float:
    """Las pérdidas en MW de un flujo que no las da (el barrido o la PINN): R·|I|² en el árbol de cada fuente."""
    n = len(m.ids)
    vecinos: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for k in range(m.aristas.shape[1]):
        vecinos[m.aristas[0, k]].append((int(m.aristas[1, k]), k))
    padre, por, visto, orden = [-1] * n, [-1] * n, [False] * n, []
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
    corriente = np.conj(m.s_carga / (np.where(v > 0, v, 1.0) * np.exp(1j * th)))
    total = 0.0
    for u in reversed(orden):
        if padre[u] >= 0:
            corriente[padre[u]] += corriente[u]
            total += float(m.z[por[u]].real) * abs(corriente[u]) ** 2
    return total * S_BASE


# ------------------------------------------------------------------ jerarquía de agentes (114:RF-1, RF-13, RF-16)
@dataclass(frozen=True)
class Agente:
    """Un agente de un nivel: sus barras, su superior y qué alimentadores tiene debajo."""

    nombre: str
    nivel: str
    codigo: str
    nodos: frozenset[str]
    superior: str | None
    alimentadores: tuple[str, ...] = ()
    #: Lo de arriba que le llega como consigna: la barra de su SET (alimentador) o las fuentes (SET y sistema).
    barras_consigna: tuple[str, ...] = ()


def _estructura_de(estructura: Any) -> dict[str, tuple[str, str]]:
    """Alimentador → (SET, sistema), venga de la ``Estructura`` de la 055 o de un diccionario."""
    if estructura is None:
        return {}
    alimentadores = getattr(estructura, 'alimentadores', None)
    if alimentadores is not None:
        return {str(c): (str(a.set_codigo), str(a.sistema or '')) for c, a in alimentadores.items()}
    return {str(c): (str(d.get('set') or ''), str(d.get('sistema') or '')) for c, d in estructura.items()}


def jerarquia(grafo: Mapping[str, Any], estructura: Any = None) -> dict[str, Agente]:
    """Un agente por alimentador, uno por SET y uno por sistema eléctrico, formados desde la red (114:RF-13).

    El alimentador es lo que cuelga de su cabecera (074:RF-11). Con la estructura de la fuente (055), su SET y su
    sistema son los de ella; si la fuente no la trae, la SET son las barras entre la fuente y la cabecera unidas sin
    líneas (transformadores y acopladores de la subestación), y el sistema es la fuente que la alimenta (114:RF-16).
    Ningún tamaño está fijado: con 10, 50 o 200 alimentadores salen tantos agentes como tenga la red.
    """
    nodos = grafo.get('nodos') or {}
    zonas = zonas_por_alimentador(grafo)
    if not zonas:
        raise EntornoAgenteError('La red no tiene ninguna fuente: no hay agentes que formar.')
    ramas = {str(r.get('id')): r for r in grafo.get('ramas') or []}
    de_estructura = _estructura_de(estructura)
    en_alimentador = {n for z in zonas.values() for n in z}

    # Las barras de subestación: fuera de los alimentadores, unidas por lo que no es una línea.
    grupo = {n: n for n in nodos if n not in en_alimentador}

    def raiz(n: str) -> str:
        while grupo[n] != n:
            grupo[n] = grupo[grupo[n]]
            n = grupo[n]
        return n

    for r in ramas.values():
        a, b = r.get('desde'), r.get('hasta')
        if r.get('cerrada', True) and r.get('clase') != 'ElmLne' and a in grupo and b in grupo:
            ra, rb = raiz(a), raiz(b)
            if ra != rb:
                grupo[max(ra, rb)] = min(ra, rb)
    barras_de_set: dict[str, set[str]] = {}
    for n in grupo:
        barras_de_set.setdefault(raiz(n), set()).add(n)

    sistema_de_nodo = {n: fuente for fuente, zona in zonas_por_fuente(grafo).items() for n in zona}
    alimentadores: dict[str, tuple[str, str, str, frozenset[str], str | None]] = {}
    for clave, zona in sorted(zonas.items()):
        cabecera = ramas.get(clave)
        codigo = str((cabecera or {}).get('alimentador') or clave)
        arriba = None
        if cabecera is not None:
            arriba = next((n for n in (cabecera.get('desde'), cabecera.get('hasta')) if n not in zona), None)
        grupo_set = raiz(arriba) if arriba in grupo else None
        set_codigo, sistema = de_estructura.get(codigo, ('', ''))
        if not set_codigo and grupo_set:
            declarado = next((nodos[n]['set'] for n in sorted(barras_de_set[grupo_set]) if nodos[n].get('set')), None)
            set_codigo = str(declarado or grupo_set)
        elif not set_codigo:
            set_codigo = str(clave)
        if not sistema:
            ancla = arriba if arriba is not None else zona[0]
            sistema = str(nodos.get(ancla, {}).get('sistema') or sistema_de_nodo.get(ancla, ancla))
        alimentadores[codigo] = (set_codigo, sistema, grupo_set or '', frozenset(zona), arriba)

    agentes: dict[str, Agente] = {}
    sets: dict[str, dict[str, Any]] = {}
    for codigo, (set_codigo, sistema, grupo_set, zona, arriba) in alimentadores.items():
        s = sets.setdefault(set_codigo, {'sistema': sistema, 'barras': set(), 'alimentadores': []})
        if grupo_set:
            s['barras'] |= barras_de_set.get(grupo_set, set())
        s['alimentadores'].append(codigo)
        agentes[f'alimentador:{codigo}'] = Agente(f'alimentador:{codigo}', 'alimentador', codigo, zona,
                                                  f'set:{set_codigo}', barras_consigna=(arriba,) if arriba else ())
    fuentes = sorted(n for n, d in nodos.items() if d.get('fuente'))
    sistemas: dict[str, dict[str, Any]] = {}
    for set_codigo, s in sorted(sets.items()):
        barras = set(s['barras'])
        for a in s['alimentadores']:
            barras |= agentes[f'alimentador:{a}'].nodos
        ss = sistemas.setdefault(s['sistema'], {'barras': set(), 'alimentadores': []})
        ss['barras'] |= barras
        ss['alimentadores'] += s['alimentadores']
        propias = tuple(f for f in fuentes if f in barras)
        agentes[f'set:{set_codigo}'] = Agente(f'set:{set_codigo}', 'set', set_codigo, frozenset(barras),
                                              f'sistema:{s["sistema"]}', tuple(sorted(s['alimentadores'])), propias)
    for sistema, ss in sorted(sistemas.items()):
        # El sistema es todo lo que alimentan sus fuentes, también las barras de 60 kV entre una SET y otra.
        barras = set(ss['barras'])
        suyas = {sistema_de_nodo.get(b) for b in ss['barras']}
        barras |= {n for n, f in sistema_de_nodo.items() if f in suyas}
        propias = tuple(f for f in fuentes if f in barras)
        agentes[f'sistema:{sistema}'] = Agente(f'sistema:{sistema}', 'sistema', sistema, frozenset(barras), None,
                                               tuple(sorted(ss['alimentadores'])), propias)
    return dict(sorted(agentes.items()))


# ------------------------------------------------------------------ parámetros y acciones
@dataclass(frozen=True)
class ParametrosAgente:
    """Límites, costos y huecos de acción: todo declarado, sin valor por defecto de ninguna empresa.

    Los huecos (tomas, transferencias y consignas por agente) fijan el tamaño del actor de cada nivel, no el de la red.
    """

    obras: ParametrosObras
    costo_maniobra: float
    costo_perdidas_mw: float
    factor_valle: float | None = None
    paso_consigna_pu: float | None = None
    max_tomas: int = 2
    max_transferencias: int = 2
    max_consignas: int = 1
    #: Lo que cuesta, en presupuestos, repetir una acción que el operador deshizo (114:RF-10).
    castigo_deshecha: float = 1.0
    #: Lo que cuesta cada paso en presupuestos: el tiempo también cuenta (114:RF-10).
    costo_paso: float = 0.0


def acciones_por_nivel(p: ParametrosAgente) -> dict[str, int]:
    """Cuántas acciones tiene el actor de cada nivel, contando «no hacer nada»."""
    k = p.obras.candidatos
    return {'alimentador': 2 + 2 * k, 'set': 1 + 2 * p.max_tomas + p.max_transferencias,
            'sistema': 1 + 2 * p.max_consignas + p.max_transferencias}


def _protegido(elemento: Mapping[str, Any] | None) -> bool:
    return bool(elemento and elemento.get('operador'))


def transferencias_de(grafo: Mapping[str, Any], agentes: Mapping[str, Agente], entre: Iterable[str],
                      protegidos: set[str]) -> list[Accion]:
    """Las transferencias posibles entre unos alimentadores, solo en maniobras (114:RF-17).

    Cerrar la maniobra abierta entre dos alimentadores y abrir la primera maniobra cerrada del que cede, subiendo desde
    la maniobra hacia su cabecera: lo que queda debajo pasa al otro y la red sigue radial. Sin esa segunda maniobra no se
    ofrece, porque cerrar solo haría un lazo (memoria del operador: las transferencias, solo en interruptor o seccionador).
    """
    entre = set(entre)
    de_nodo = {n: a for a in entre for n in agentes[f'alimentador:{a}'].nodos}
    ramas = grafo.get('ramas') or []
    vecinos: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for r in ramas:
        if r.get('cerrada', True):
            vecinos.setdefault(r['desde'], []).append((r['hasta'], r))
            vecinos.setdefault(r['hasta'], []).append((r['desde'], r))
    cabeceras = {a: agentes[f'alimentador:{a}'].barras_consigna for a in entre}

    def maniobra_hacia_cabecera(desde: str, alimentador: str) -> str | None:
        # El camino de la barra a la cabecera dentro del alimentador; la primera maniobra cerrada que no sea la cabecera.
        zona = agentes[f'alimentador:{alimentador}'].nodos
        arriba = set(cabeceras[alimentador])
        padre: dict[str, tuple[str, Mapping[str, Any]] | None] = {desde: None}
        pila, meta = [desde], None
        while pila and meta is None:
            u = pila.pop()
            for w, r in vecinos.get(u, []):
                if w in padre or (w not in zona and w not in arriba):
                    continue
                padre[w] = (u, r)
                if w in arriba:
                    meta = w
                    break
                pila.append(w)
        if meta is None:
            return None
        camino, n = [], meta
        while padre[n] is not None:
            u, r = padre[n]
            camino.append(r)
            n = u
        for r in reversed(camino[1:]):           # camino[0] es la cabecera, junto a la barra de la SET
            if r.get('clase') == 'ElmCoup' and str(r['id']) not in protegidos and not _protegido(r):
                return str(r['id'])
        return None

    salida: list[Accion] = []
    for r in sorted(ramas, key=lambda r: str(r.get('id'))):
        if r.get('cerrada', True) or r.get('clase') != 'ElmCoup' or str(r['id']) in protegidos or _protegido(r):
            continue
        a, b = de_nodo.get(r.get('desde')), de_nodo.get(r.get('hasta'))
        if not a or not b or a == b:
            continue
        for cede, extremo in ((b, r['hasta']), (a, r['desde'])):
            abrir = maniobra_hacia_cabecera(extremo, cede)
            if abrir:
                salida.append(Accion('transferencia', f'{r["id"]}|{abrir}', 0.0))
    return salida


def tomas_de(grafo: Mapping[str, Any], barras: set[str], protegidos: set[str]) -> list[str]:
    """Los transformadores de la SET cuya toma declara paso y límites; sin ellos no se ofrecen (114:RF-18)."""
    salida = []
    for r in sorted(grafo.get('ramas') or [], key=lambda r: str(r.get('id'))):
        toma = r.get('toma') or {}
        if not str(r.get('clase') or '').startswith('ElmTr') or not r.get('cerrada', True):
            continue
        if r.get('desde') not in barras and r.get('hasta') not in barras:
            continue
        if str(r['id']) in protegidos or _protegido(r):
            continue
        if toma.get('paso_pct') and toma.get('minimo') is not None and toma.get('maximo') is not None:
            salida.append(str(r['id']))
    return salida


def grafo_en_valle(grafo: Mapping[str, Any], factor: float, agregados: Mapping[str, float]) -> dict[str, Any]:
    """La red en valle: la demanda por ``factor``; los bancos, los de la red y los que puso el agente, no bajan.

    Los bancos del agente restan su reactiva de ``q_mvar`` (074), así que se devuelven antes de escalar y se quitan
    después: escalarlos con la carga escondía la sobretensión de valle que provocan (spec 073).
    """
    g = dict(grafo)
    nodos = {}
    for n, d in (grafo.get('nodos') or {}).items():
        banco = float(agregados.get(n, 0.0))
        if 'carga_p_mw' in d:
            p, q = float(d.get('carga_p_mw') or 0.0) * factor, float(d.get('carga_q_mvar') or 0.0) * factor
            nodos[n] = {**d, 'carga_p_mw': p, 'carga_q_mvar': q, 'p_mw': p - float(d.get('gen_p_mw') or 0.0),
                        'q_mvar': q - float(d.get('gen_q_mvar') or 0.0) - float(d.get('banco_q_mvar') or 0.0) - banco}
        else:
            q_carga = float(d.get('q_mvar') or 0.0) + banco
            nodos[n] = {**d, 'p_mw': float(d.get('p_mw') or 0.0) * factor, 'q_mvar': q_carga * factor - banco}
    g['nodos'] = nodos
    return g


@dataclass
class EstadoRed:
    """Lo que dio el flujo en máxima y en valle tras las acciones hechas."""

    maxima: Evaluacion
    valle: Evaluacion | None
    por_agente: dict[str, Evaluacion]
    por_agente_valle: dict[str, Evaluacion]
    tension: dict[str, float]
    carga_rama: dict[str, float]
    perdidas_mw: float
    motor: str

    @property
    def en_norma(self) -> bool:
        return self.maxima.en_norma and (self.valle is None or self.valle.en_norma)

    def en_norma_agente(self, nombre: str) -> bool:
        return self.por_agente[nombre].en_norma and (not self.por_agente_valle or self.por_agente_valle[nombre].en_norma)


# ------------------------------------------------------------------ el entorno
class EntornoAgente(_BaseParalela):
    """El ``ParallelEnv`` de obras: agentes en tres niveles, pasos simultáneos y recompensa común (114:RF-1, RF-4).

    ``evaluador`` es lo que resuelve cada paso: el motor abierto (por defecto), el barrido del oráculo o un
    ``OraculoPINN`` ya entrenado; cualquiera con ``predecir(grafo)``. ``protegidos`` son elementos que el operador
    cambió: no se ofrecen (aclaración de 114:RF-9). ``deshechas`` son acciones que el operador ya deshizo: se pueden
    elegir, pero cuestan caro (114:RF-10).
    """

    metadata = {'name': 'convertersmartgrid_obras_v0', 'render_modes': []}

    def __init__(self, grafo: Mapping[str, Any], p: ParametrosAgente, *, estructura: Any = None, evaluador: Any = None,
                 protegidos: Iterable[str] = (), deshechas: Iterable[tuple[str, str, str]] = (),
                 escenario: Callable[[dict[str, Any], np.random.Generator], dict[str, Any]] | None = None) -> None:
        self.original, self.p = grafo, p
        self.evaluador = evaluador if evaluador is not None else MotorAbierto()
        self.protegidos = {str(x) for x in protegidos}
        self.deshechas = {tuple(x) for x in deshechas}
        self.escenario = escenario
        self.estructura = jerarquia(grafo, estructura)
        self.possible_agents = list(self.estructura)
        self.agents: list[str] = []
        self.niveles = acciones_por_nivel(p)
        self.lagrange = Lagrange()
        self._obs_tam = {'alimentador': 11 + 2 * 2 * p.obras.candidatos, 'set': 11 + 2 * p.max_tomas + 3 * p.max_transferencias,
                         'sistema': 11 + p.max_consignas + 3 * p.max_transferencias}
        self._espacios_obs = {a: _espacio_observacion(self._obs_tam[ag.nivel], self.niveles[ag.nivel])
                              for a, ag in self.estructura.items()}
        self._espacios_acc = {a: _espacio_accion(self.niveles[ag.nivel]) for a, ag in self.estructura.items()}
        self._rng = np.random.default_rng()
        self.grafo: dict[str, Any] = {}

    # --- API de PettingZoo
    def observation_space(self, agent: str):
        return self._espacios_obs[agent]

    def action_space(self, agent: str):
        return self._espacios_acc[agent]

    def dimensiones(self) -> dict[str, tuple[int, int]]:
        """Observación y acciones de cada nivel: lo que fija el tamaño de su actor, no el de la red (114:RF-13)."""
        return {n: (self._obs_tam[n], self.niveles[n]) for n in NIVELES}

    @property
    def tam_estado(self) -> int:
        """Tamaño del estado global del crítico central: no depende del número de agentes (114:RF-2, RF-13)."""
        return 11 + 2 * sum(self._obs_tam.values())

    def reset(self, seed: int | None = None, options: Mapping[str, Any] | None = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)
            for e in (*self._espacios_obs.values(), *self._espacios_acc.values()):
                e.seed(seed)
        self.grafo = copy.deepcopy(dict(self.original))
        if self.escenario is not None:
            self.grafo = self.escenario(self.grafo, self._rng)
        self.agents = list(self.possible_agents)
        self.pasos = 0
        self.costo_obras = 0.0
        self.costo_maniobras = 0.0
        self.bancos_agregados: dict[str, float] = {}
        self.hechas: dict[str, set[int]] = {a: set() for a in self.possible_agents}
        self.historial: list[dict[str, Any]] = []
        self._rama = {str(r.get('id')): r for r in self.grafo.get('ramas') or []}
        self._ramas_de = {a: [i for i, r in self._rama.items() if r.get('desde') in ag.nodos]
                          for a, ag in self.estructura.items() if ag.nivel == 'alimentador'}
        self._preparar_acciones()
        self.estado = self._medir()
        self.inicial = self.estado
        return self._observar(), {a: {'nivel': self.estructura[a].nivel} for a in self.agents}

    def state(self) -> np.ndarray:
        """El estado global para el crítico central: lo global y la media y el máximo de cada nivel (114:RF-2)."""
        obs = self._observar()
        partes = [self._global()]
        for nivel in NIVELES:
            filas = [obs[a]['observation'] for a, ag in self.estructura.items() if ag.nivel == nivel]
            tam = self._obs_tam[nivel]
            pila = np.stack(filas) if filas else np.zeros((1, tam), dtype=np.float32)
            partes += [pila.mean(0), pila.max(0)]
        return np.concatenate(partes).astype(np.float32)

    def step(self, actions: Mapping[str, int]):
        invalidas: dict[str, int] = {}
        mascaras = {a: self.mascara(a) for a in self.agents}
        gasto_obras = gasto_maniobras = castigo = 0.0
        elegidas: dict[str, Accion] = {}
        # Primero las del sistema, luego las SET y luego los alimentadores: la consigna baja antes de las obras.
        orden = sorted(actions, key=lambda a: -NIVELES.index(self.estructura[a].nivel) if a in self.estructura else 0)
        for agente in orden:
            if agente not in mascaras:
                continue
            indice = int(actions[agente])
            if indice == NADA:
                continue
            if not (0 <= indice < len(mascaras[agente])) or not mascaras[agente][indice]:
                invalidas[agente] = indice                      # 114:RF-20: se toma como «no hacer nada»
                continue
            accion = self._resolver(agente, indice)
            if accion is None:
                continue
            self._aplicar(accion)
            self.hechas[agente].add(indice)
            elegidas[agente] = accion
            if accion.tipo in ('banco', 'terna'):
                gasto_obras += accion.costo
            else:
                gasto_maniobras += accion.costo
            if (agente, accion.tipo, accion.elemento) in self.deshechas:
                castigo += self.p.castigo_deshecha * self.presupuesto
        self.costo_obras += gasto_obras
        self.costo_maniobras += gasto_maniobras
        self.pasos += 1
        self.estado = self._medir()
        hizo_algo = bool(elegidas)
        terminado = self.estado.en_norma or not hizo_algo
        truncado = not terminado and self.pasos >= self.limite_pasos
        componentes = {'obras': -gasto_obras / self.escala, 'maniobras': -gasto_maniobras / self.escala,
                       'tiempo': -self.p.costo_paso, 'deshechas': -castigo, 'digsilent': 0.0,
                       'norma': 0.0, 'perdidas': 0.0}
        if terminado or truncado:
            componentes['norma'] = -self.penalidad_final()
            componentes['perdidas'] = (self.inicial.perdidas_mw - self.estado.perdidas_mw) * self.p.costo_perdidas_mw / self.escala
        recompensa = float(sum(componentes.values()))
        self.historial.append({'paso': self.pasos, 'acciones': {a: (x.tipo, x.elemento) for a, x in elegidas.items()},
                               'recompensa': recompensa, 'componentes': componentes})
        vivos = list(self.agents)
        obs = self._observar()
        info = {a: {'nivel': self.estructura[a].nivel, 'recompensa': componentes, 'en_norma': self.estado.en_norma,
                    'motor': self.estado.motor, **({'accion_invalida': invalidas[a]} if a in invalidas else {})}
                for a in vivos}
        if terminado or truncado:
            self.agents = []
        return (obs, dict.fromkeys(vivos, recompensa), dict.fromkeys(vivos, terminado), dict.fromkeys(vivos, truncado), info)

    def render(self) -> None:
        return None

    def close(self) -> None:
        return None

    # --- acciones
    def _preparar_acciones(self) -> None:
        """Los huecos de acción de cada agente sobre la red de este episodio; ``None`` es un hueco vacío."""
        p, k = self.p, self.p.obras.candidatos
        evaluado = self.evaluador.predecir(self.grafo)
        flujo = (muestra(self.grafo), np.asarray(evaluado['v']))
        nodos = self.grafo.get('nodos') or {}
        ramas = {str(r.get('id')): r for r in self.grafo.get('ramas') or []}
        self.huecos: dict[str, list[Accion | None]] = {}
        todas_obras = 0.0
        for nombre, ag in self.estructura.items():
            if ag.nivel == 'alimentador':
                libres = {n for n in ag.nodos if n not in self.protegidos and not _protegido(nodos.get(n))}
                cand = [a for a in candidatos_de(self.grafo, libres, p.obras, flujo=flujo)
                        if a.tipo == 'banco' or (a.elemento not in self.protegidos and not _protegido(ramas.get(a.elemento)))]
                bancos = [a for a in cand if a.tipo == 'banco'][:k]
                ternas = [a for a in cand if a.tipo == 'terna'][:k]
                todas_obras += sum(a.costo for a in bancos + ternas)
                self.huecos[nombre] = ([None, Accion('escalera', '', 0.0)] + bancos + [None] * (k - len(bancos))
                                       + ternas + [None] * (k - len(ternas)))
            elif ag.nivel == 'set':
                tomas = tomas_de(self.grafo, set(ag.nodos), self.protegidos)[:p.max_tomas]
                huecos: list[Accion | None] = [None]
                for t in tomas + [None] * (p.max_tomas - len(tomas)):
                    huecos += [Accion('toma+', t, p.costo_maniobra), Accion('toma-', t, p.costo_maniobra)] if t else [None, None]
                tr = [Accion(a.tipo, a.elemento, p.costo_maniobra)
                      for a in transferencias_de(self.grafo, self.estructura, ag.alimentadores, self.protegidos)]
                tr = tr[:p.max_transferencias]
                self.huecos[nombre] = huecos + tr + [None] * (p.max_transferencias - len(tr))
            else:
                huecos = [None]
                fuentes = [f for f in ag.barras_consigna if f not in self.protegidos and not _protegido(nodos.get(f))]
                fuentes = fuentes[:p.max_consignas] if p.paso_consigna_pu else []         # 114:RF-18
                for f in fuentes + [None] * (p.max_consignas - len(fuentes)):
                    huecos += [Accion('consigna+', f, p.costo_maniobra), Accion('consigna-', f, p.costo_maniobra)] if f else [None, None]
                # Las del sistema son las transferencias entre SET distintas: las de una misma SET son de su agente.
                set_de = {a: self.estructura[f'alimentador:{a}'].superior for a in ag.alimentadores}
                tr = [Accion(x.tipo, x.elemento, p.costo_maniobra)
                      for x in transferencias_de(self.grafo, self.estructura, ag.alimentadores, self.protegidos)
                      if self._cruza_sets(x, set_de)]
                tr = tr[:p.max_transferencias]
                self.huecos[nombre] = huecos + tr + [None] * (p.max_transferencias - len(tr))
        self.escala = max(p.obras.costo_banco, 1.0)
        self.presupuesto = max(todas_obras / self.escala, 1.0)
        self.limite_pasos = p.obras.max_pasos

    def _cruza_sets(self, accion: Accion, set_de: Mapping[str, str | None]) -> bool:
        lazo = accion.elemento.split('|')[0]
        r = self._rama[lazo]
        dueno = {n: a for a in set_de for n in self.estructura[f'alimentador:{a}'].nodos}
        a, b = dueno.get(r['desde']), dueno.get(r['hasta'])
        return bool(a and b and set_de[a] != set_de[b])

    def mascara(self, agente: str) -> np.ndarray:
        """Qué puede elegir un agente ahora: nada siempre; lo demás, solo si su zona incumple (074:RF-2)."""
        huecos = self.huecos[agente]
        m = np.zeros(len(huecos), dtype=np.int8)
        m[NADA] = 1
        if self.estado.en_norma_agente(agente):
            return m
        ag = self.estructura[agente]
        hechas = self.hechas[agente]
        if ag.nivel == 'alimentador':
            obras = [i for i, x in enumerate(huecos) if x is not None and x.tipo in ('banco', 'terna') and i not in hechas]
            bancos = sum(huecos[i].tipo == 'banco' for i in hechas if huecos[i] is not None and huecos[i].tipo == 'banco')
            quedan_bancos = bancos < self.p.obras.max_bancos and any(huecos[i].tipo == 'banco' for i in obras)
            for i in obras:
                m[i] = (huecos[i].tipo == 'banco') == quedan_bancos       # la escalera: primero los bancos
            m[1] = int(m[2:].any())
            return m
        for i, x in enumerate(huecos):
            if x is None or i == NADA:
                continue
            if x.tipo == 'transferencia':
                m[i] = i not in hechas
            elif x.tipo.startswith('toma'):
                m[i] = self._toma_admite(x)
            elif x.tipo.startswith('consigna'):
                m[i] = self._consigna_admite(x)
        return m

    def _toma_admite(self, x: Accion) -> bool:
        r = self._rama[x.elemento]
        toma = r['toma']
        pos = float(toma.get('posicion') or 0.0) + (1 if x.tipo == 'toma+' else -1)
        return float(toma['minimo']) <= pos <= float(toma['maximo'])

    def _consigna_admite(self, x: Accion) -> bool:
        v = float(self.grafo['nodos'][x.elemento].get('v_pu') or 1.0)
        v += self.p.paso_consigna_pu if x.tipo == 'consigna+' else -self.p.paso_consigna_pu
        return self.p.obras.tension_min_pu - 1e-9 <= v <= self.p.obras.tension_max_pu + 1e-9

    def _resolver(self, agente: str, indice: int) -> Accion | None:
        x = self.huecos[agente][indice]
        if x is not None and x.tipo == 'escalera':
            # La escalera de la 074: la primera obra que su máscara permite, bancos antes que terna.
            m = self.mascara(agente)
            primera = next((i for i in range(2, len(m)) if m[i]), None)
            if primera is None:
                return None
            self.hechas[agente].add(primera)
            return self.huecos[agente][primera]
        return x

    def _aplicar(self, x: Accion) -> None:
        if x.tipo in ('banco', 'terna'):
            aplicar(self.grafo, x, self.p.obras)
            if x.tipo == 'banco':
                self.bancos_agregados[x.elemento] = self.bancos_agregados.get(x.elemento, 0.0) + self.p.obras.banco_mvar
        elif x.tipo.startswith('toma'):
            r = self._rama[x.elemento]
            r['toma'] = {**r['toma'], 'posicion': float(r['toma'].get('posicion') or 0.0) + (1 if x.tipo == 'toma+' else -1)}
        elif x.tipo.startswith('consigna'):
            nodo = self.grafo['nodos'][x.elemento]
            paso = self.p.paso_consigna_pu if x.tipo == 'consigna+' else -self.p.paso_consigna_pu
            self.grafo['nodos'][x.elemento] = {**nodo, 'v_pu': float(nodo.get('v_pu') or 1.0) + paso}
        elif x.tipo == 'transferencia':
            cerrar, abrir = x.elemento.split('|')
            self._rama[cerrar]['cerrada'] = True
            self._rama[abrir]['cerrada'] = False
        else:
            raise EntornoAgenteError(f'acción desconocida: {x.tipo}')

    # --- física y recompensa
    def _evaluar(self, grafo: Mapping[str, Any]):
        r = self.evaluador.predecir(grafo)
        m = muestra(grafo)
        v, th = np.asarray(r['v']), np.asarray(r['theta'])
        zonas = {a: set(ag.nodos) for a, ag in self.estructura.items()}
        total, por = evaluar_flujo(m, v, th, self.p.obras, zonas)
        perdidas = r.get('perdidas_mw')
        if perdidas is None or not math.isfinite(perdidas):
            perdidas = perdidas_estimadas(m, v, th)
        return total, por, m, v, th, float(perdidas), str(r.get('motor') or r.get('modelo') or '')

    def _medir(self) -> EstadoRed:
        return self.medir(self.grafo, self.bancos_agregados)

    def medir(self, grafo: Mapping[str, Any], bancos_agregados: Mapping[str, float]) -> EstadoRed:
        """Una red cualquiera con la misma medida del entorno: así se compara la propuesta con la regla actual (114:RF-19)."""
        total, por, m, v, th, perdidas, motor = self._evaluar(grafo)
        valle = por_valle = None
        if self.p.factor_valle is not None:
            valle, por_valle, *_ = self._evaluar(grafo_en_valle(grafo, self.p.factor_valle, bancos_agregados))
        return EstadoRed(total, valle, por, por_valle or {}, {n: float(v[i]) for i, n in enumerate(m.ids)},
                         cargas_de_rama(m, v, th), perdidas, motor)

    def penalidad_final(self) -> float:
        """Terminar fuera de norma cuesta al menos todas las obras (074:RF-4), en máxima y en valle (114:RF-10)."""
        if self.estado.en_norma:
            return 0.0

        def parte(ahora: Evaluacion | None, inicio: Evaluacion | None) -> float:
            if ahora is None or inicio is None:
                return 0.0
            # Cada parte se acota a 2: en el ensayo del 2026-11-27 con una red sintética de tres alimentadores, sin tope, un
            # episodio al azar que hundía la red a 0,66 p.u. costaba 500 presupuestos, y el crítico aprendía esa cola en vez
            # de las obras.
            return sum(min(getattr(ahora, k) / getattr(inicio, k), 2.0) if getattr(inicio, k) else float(getattr(ahora, k) > 0)
                       for k in ('subtension', 'sobretension', 'sobrecarga'))

        resto = parte(self.estado.maxima, self.inicial.maxima) + parte(self.estado.valle, self.inicial.valle)
        return self.presupuesto * (1.0 + resto)

    # --- observaciones
    def _global(self) -> np.ndarray:
        e, i = self.estado, self.inicial
        sets = [a for a, ag in self.estructura.items() if ag.nivel == 'set']
        return np.array([e.maxima.vm_min, e.maxima.subtension, e.maxima.sobretension, e.maxima.sobrecarga / 100,
                         e.valle.vm_min if e.valle else 1.0, e.valle.sobretension if e.valle else 0.0,
                         float(e.en_norma), e.perdidas_mw / max(i.perdidas_mw, 1e-6),
                         (self.costo_obras + self.costo_maniobras) / self.escala / self.presupuesto,
                         self.pasos / max(self.limite_pasos, 1),
                         sum(not e.en_norma_agente(s) for s in sets) / max(len(sets), 1)], dtype=np.float32)

    def _resumen(self, nombre: str) -> list[float]:
        e = self.estado
        z, zv = e.por_agente[nombre], e.por_agente_valle.get(nombre)
        vs = [e.tension[n] for n in self.estructura[nombre].nodos if e.tension.get(n, 0) > 0]
        return [z.vm_min, max(vs) if vs else 1.0, z.subtension, z.sobretension, z.sobrecarga / 100,
                zv.vm_min if zv else 1.0, zv.sobretension if zv else 0.0, self.pasos / max(self.limite_pasos, 1)]

    def _observar(self) -> dict[str, dict[str, np.ndarray]]:
        """Lo que ve cada agente: su zona, lo que le pasa el de arriba y sus huecos de acción (114:RF-1, RF-2)."""
        e = self.estado
        salida: dict[str, dict[str, np.ndarray]] = {}
        for nombre in self.possible_agents:
            ag = self.estructura[nombre]
            huecos = self.huecos[nombre]
            obs = self._resumen(nombre)
            if ag.nivel == 'alimentador':
                consigna = [e.tension.get(n, 1.0) for n in ag.barras_consigna] or [1.0]
                bancos = sum(huecos[i].tipo == 'banco' for i in self.hechas[nombre] if huecos[i] is not None)
                cargas = [e.carga_rama.get(i, 0.0) for i in self._ramas_de[nombre]]
                obs += [float(np.mean(consigna)), bancos / max(self.p.obras.max_bancos, 1), max(cargas, default=0.0) / 100]
                for i, x in enumerate(huecos[2:], start=2):
                    if x is None:
                        obs += [0.0, 0.0]
                    elif x.tipo == 'banco':
                        obs += [e.tension.get(x.elemento, 0.0), float(i in self.hechas[nombre])]
                    else:
                        obs += [e.carga_rama.get(x.elemento, 0.0) / 100, float(i in self.hechas[nombre])]
            else:
                debajo = ag.alimentadores if ag.nivel == 'set' else [s for s in self.estructura if
                                                                    self.estructura[s].superior == nombre]
                debajo = [f'alimentador:{a}' for a in debajo] if ag.nivel == 'set' else debajo
                fuera = sum(not e.en_norma_agente(a) for a in debajo) / max(len(debajo), 1)
                consigna = [float(self.grafo['nodos'][f].get('v_pu') or 1.0) for f in ag.barras_consigna] or [1.0]
                hechas_tr = sum(1 for i in self.hechas[nombre] if huecos[i] is not None and huecos[i].tipo == 'transferencia')
                obs += [fuera, float(np.mean(consigna)), 1.0 - hechas_tr / max(self.p.max_transferencias, 1)]
                pares = self.p.max_tomas if ag.nivel == 'set' else self.p.max_consignas
                for j in range(pares):
                    x = huecos[1 + 2 * j]
                    if ag.nivel == 'set':
                        if x is None:
                            obs += [0.0, 0.0]
                        else:
                            r = self._rama[x.elemento]
                            t = r['toma']
                            rango = max(float(t['maximo']) - float(t['minimo']), 1.0)
                            obs += [(float(t.get('posicion') or 0.0) - float(t['minimo'])) / rango,
                                    e.tension.get(r['hasta'], 0.0)]
                    else:
                        obs += [0.0] if x is None else [float(self.grafo['nodos'][x.elemento].get('v_pu') or 1.0)]
                for j in range(self.p.max_transferencias):
                    i = 1 + 2 * pares + j
                    x = huecos[i]
                    if x is None:
                        obs += [0.0, 0.0, 0.0]
                    else:
                        r = self._rama[x.elemento.split('|')[0]]
                        obs += [e.tension.get(r['desde'], 0.0), e.tension.get(r['hasta'], 0.0), float(i in self.hechas[nombre])]
            vector = np.asarray(obs, dtype=np.float32)
            salida[nombre] = {'observation': vector, 'action_mask': self.mascara(nombre)}
        return salida

    # --- lo que se hizo
    def acciones_hechas(self) -> list[str]:
        return [f'{a}:{t}:{e}' for paso in self.historial for a, (t, e) in sorted(paso['acciones'].items())]

    def resultado(self, nombre: str) -> dict[str, Any]:
        """El resultado del episodio con las claves de la 074, para compararlo con la escalera, NSGA-II y la PPO."""
        e = self.estado
        return {'control': nombre, 'en_norma': e.en_norma, 'en_norma_maxima': e.maxima.en_norma,
                'en_norma_valle': None if e.valle is None else e.valle.en_norma, 'costo': self.costo_obras,
                'costo_maniobras': self.costo_maniobras, 'vm_min': e.maxima.vm_min, 'perdidas_mw': e.perdidas_mw,
                'obras': self.acciones_hechas(), 'pasos': self.pasos, 'motor': e.motor}


# ------------------------------------------------------------------ redes sintéticas sorteadas
def red_sintetica(semilla: int, *, sistemas: int | None = None, sets: int | None = None, alimentadores: int | None = None,
                  barras: int | None = None, carga_mw: float | None = None) -> dict[str, Any]:
    """Una red sorteada con sistemas, SET de 60/10 kV con toma declarada y alimentadores con maniobras.

    Cada alimentador sale de su SET por su cabecera, tiene un seccionador a mitad y una maniobra abierta con el siguiente;
    el último de una SET se enlaza con el primero de la siguiente. Los tamaños que no se dan se sortean: ninguna prueba
    fija cuántos alimentadores tiene la red.
    """
    rng = np.random.default_rng(semilla)
    n_sis = sistemas or int(rng.integers(1, 3))
    nodos: dict[str, dict[str, Any]] = {}
    ramas: list[dict[str, Any]] = []
    for s in range(n_sis):
        fuente = f'S{s}'
        nodos[fuente] = {'kv': 60.0, 'fuente': True, 'v_pu': 1.0}
        n_sets = sets or int(rng.integers(1, 3))
        ultimos: list[tuple[str, str]] = []
        for j in range(n_sets):
            alta, baja = f'S{s}T{j}A', f'S{s}T{j}B'
            nodos[alta] = {'kv': 60.0}
            nodos[baja] = {'kv': 10.0}
            ramas.append({'id': f'S{s}T{j}LT', 'clase': 'ElmLne', 'desde': fuente, 'hasta': alta, 'r_ohm': 1.0,
                          'x_ohm': 3.0, 'inom_ka': 0.4, 'km': 10.0, 'cerrada': True})
            ramas.append({'id': f'S{s}T{j}TR', 'clase': 'ElmTr2', 'desde': alta, 'hasta': baja, 'r_ohm': 1.44,
                          'x_ohm': 14.4, 'inom_ka': 0.24, 'u_desde_kv': 60.0, 'u_hasta_kv': 10.0, 'cerrada': True,
                          'toma': {'paso_pct': 1.25, 'posicion': 0, 'neutra': 0, 'lado': 0, 'minimo': -8, 'maximo': 8}})
            n_al = alimentadores or int(rng.integers(1, 4))
            anterior = None
            for k in range(n_al):
                pre = f'S{s}T{j}F{k}'
                n = barras or int(rng.integers(5, 9))
                carga = carga_mw if carga_mw is not None else float(rng.uniform(0.15, 0.45))
                for i in range(n):
                    nodos[f'{pre}N{i}'] = {'kv': 10.0, 'p_mw': carga if i else 0.0, 'q_mvar': carga * 0.6 if i else 0.0}
                ramas.append({'id': f'{pre}CAB', 'clase': 'ElmCoup', 'desde': baja, 'hasta': f'{pre}N0', 'cerrada': True,
                              'alimentador': pre})
                medio = n // 2
                for i in range(n - 1):
                    if i == medio - 1:
                        ramas.append({'id': f'{pre}SEC', 'clase': 'ElmCoup', 'desde': f'{pre}N{i}', 'hasta': f'{pre}N{i + 1}',
                                      'cerrada': True})
                        continue
                    ramas.append({'id': f'{pre}L{i}', 'clase': 'ElmLne', 'desde': f'{pre}N{i}', 'hasta': f'{pre}N{i + 1}',
                                  'r_ohm': 0.5, 'x_ohm': 0.4, 'inom_ka': 0.3, 'km': 1.5, 'cerrada': True})
                fin = f'{pre}N{n - 1}'
                if anterior:
                    ramas.append({'id': f'{pre}ENL', 'clase': 'ElmCoup', 'desde': anterior, 'hasta': fin, 'cerrada': False})
                anterior = fin
            ultimos.append((_ultima(nodos, f'S{s}T{j}F0'), anterior))
        for j in range(1, len(ultimos)):
            ramas.append({'id': f'S{s}T{j}ENLSET', 'clase': 'ElmCoup', 'desde': ultimos[j - 1][1], 'hasta': ultimos[j][0],
                          'cerrada': False})
    return {'nodos': nodos, 'ramas': ramas}


def _ultima(nodos: Mapping[str, Any], prefijo: str) -> str:
    return max((n for n in nodos if n.startswith(prefijo + 'N')), key=lambda n: int(n[len(prefijo) + 1:]))


@dataclass
class Episodio:
    """Un episodio jugado: lo que vio y eligió cada agente en cada paso, para el registro de experiencia (114:RF-11)."""

    pasos: list[dict[str, Any]] = field(default_factory=list)
    resultado: dict[str, Any] = field(default_factory=dict)


def jugar(entorno: EntornoAgente, elegir: Callable[[str, np.ndarray, np.ndarray], int], *, semilla: int | None = None) -> Episodio:
    """Un episodio con la regla ``elegir(agente, observación, máscara)``; devuelve lo jugado y el resultado."""
    obs, _info = entorno.reset(seed=semilla)
    ep = Episodio()
    while entorno.agents:
        acciones = {a: int(elegir(a, obs[a]['observation'], obs[a]['action_mask'])) for a in entorno.agents}
        estado = entorno.state()
        siguiente, recompensas, terminados, truncados, info = entorno.step(acciones)
        ep.pasos.append({'obs': obs, 'acciones': acciones, 'recompensa': next(iter(recompensas.values()), 0.0),
                         'estado': estado, 'siguiente': siguiente, 'siguiente_estado': entorno.state(),
                         'fin': any(terminados.values()) or any(truncados.values()), 'info': info})
        obs = siguiente
    ep.resultado = entorno.resultado('jugado')
    return ep
