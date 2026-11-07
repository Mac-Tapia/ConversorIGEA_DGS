"""Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT (spec 052).

La escalera de la 025 probaba cada variante en DIgSILENT (de 20 a 85 s cada una): en NA203 +
NA205 (2026-11-01) unas 3 horas por optimización. Aquí cada variante se calcula con el flujo
físico del gemelo (``digital_twin.flujo``, 0,003 p.u. frente a DIgSILENT en IN111–TA225) sobre
el grafo leído una vez de «Con proyecto», en milisegundos, y DIgSILENT solo confirma lo
elegido (RF-5).

Además de las variantes de la escalera (RF-2, RF-3), la búsqueda usa los módulos que ya tiene
el proyecto (usuario, 2026-11-01): búsqueda bayesiana con Optuna sobre combinaciones de obras
(RF-11, RF-12), el NSGA-II del gemelo para el frente de Pareto (RF-13), una cadena de Markov de
la curva de cabecera para sortear la demanda (RF-14) y el valor de Shapley para repartir el
costo de la obra entre las cargas que la necesitan (RF-15).

Puro: no habla con DIgSILENT. Leer el grafo es de ``tools/obras_pf.py`` y confirmar, de la
escalera de siempre.
"""
from __future__ import annotations

import math
import random
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .digital_twin.evolutivo import nombre_corto, nsga2
from .digital_twin.oraculo import S_BASE, muestra, sistema_de
from .escalera_optima import Parametros, Variante, cumple, obra_terna, rango as rango_escalon
from .estudios_pf import CON_PROYECTO
from .valle import CASOS_CARGAS, anotar_punto, sin_comprobar

#: Por debajo de esta tensión nominal una barra es de baja (la de cada SED): no la juzga la escalera.
KV_MEDIA_MIN = 1.0

#: 087:RF-43: redes factorizadas que guarda el oráculo a la vez (unos 4 MB cada una con Pisco entero).
MAX_SISTEMAS = 64

#: Presupuestos por defecto, si el perfil no da los suyos (RF-11, RF-14, RF-15).
EVALUACIONES_BAYES = 200
NIVELES_MARKOV = 5
PERMUTACIONES_SHAPLEY = 50
#: 087:RF-56: barras de banco que pasan a la búsqueda, si el perfil no da ``escalera.candidatas_banco``. Las mismas
#: 30 que usa el PIDE (``afinar_bancos_pide``): con más, Optuna no llega a explorar en sus 200 evaluaciones.
CANDIDATAS_BANCO = 30


@dataclass
class Medida:
    """Un flujo del oráculo en la forma de ``escalera_optima.cumple``."""
    converge: bool
    u: dict[str, float]                 # barra (nombre corto) → p.u.
    carga: dict[str, float]             # rama (nombre corto) → % de su corriente nominal
    perdidas_kw: float | None
    v_min: float | None
    aproximada: bool = False            # con regulador: tensión aguas abajo ajustada, no resuelta
    oraculo: str = 'fisica'             # 'pinn' si la tensión es la del PINN promovido (RF-17)

    def para_criterio(self) -> dict[str, Any]:
        return {'converge': self.converge, 'u': self.u, 'carga': self.carga}


@dataclass
class Oraculo:
    """El grafo de «Con proyecto» con todas las cargas nuevas activas, listo para medir (RF-2, RF-3).

    ``nuevas``: en el orden de la 042 (de mayor a menor potencia), cada una con ``nodo`` (id del
    grafo), ``p_mw`` y ``q_mvar``: lo que su variación pone en ese nodo. ``tipos``: datos de los
    tipos de línea por nombre (``rline``, ``xline`` en Ω/km, ``sline`` en kA) para el cambio de
    sección. ``exponente``: el de la carga del gemelo (0, potencia constante).
    """
    grafo: Mapping[str, Any]
    nuevas: Sequence[Mapping[str, Any]]
    tipos: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    exponente: float = 0.0
    pinn: Any = None                    # ``digital_twin.oraculo.OraculoPINN`` promovido (RF-17)
    evaluaciones: int = 0
    _sistemas: OrderedDict = field(default_factory=OrderedDict, repr=False)

    def __post_init__(self) -> None:
        nodos = {n: dict(d) for n, d in (self.grafo.get('nodos') or {}).items()}
        # La demanda existente, sin las nuevas: el grafo se leyó con todas activas (RF-1).
        for c in self.nuevas:
            d = nodos.get(c['nodo'])
            if d is not None:
                d['p_mw'] = float(d.get('p_mw') or 0.0) - float(c.get('p_mw') or 0.0)
                d['q_mvar'] = float(d.get('q_mvar') or 0.0) - float(c.get('q_mvar') or 0.0)
        self._nodos = nodos
        self._ramas = [dict(r) for r in self.grafo.get('ramas') or []]
        self.nodo_de = {nombre_corto(n): n for n in nodos}
        self.rama_de = {nombre_corto(str(r.get('id'))): i for i, r in enumerate(self._ramas)}
        self._lineas = {str(r.get('id')) for r in self._ramas if r.get('clase', 'ElmLne') == 'ElmLne'}

    # ------------------------------------------------------------------ el grafo de una variante
    def _ramas_con(self, obras: Sequence[Mapping[str, Any]], avisos: list[str]) -> list[dict]:
        """Las ramas con las obras que cambian impedancia: terna y sección (RF-2)."""
        ramas = [dict(r) for r in self._ramas]
        for o in obras:
            clase = o.get('clase')
            if clase not in ('terna', 'seccion'):
                continue
            for nombre in o.get('tramos') or []:
                i = self.rama_de.get(str(nombre))
                if i is None:
                    avisos.append(f'el tramo {nombre} no está en el grafo')
                    continue
                r = ramas[i]
                if clase == 'terna':                       # un circuito igual en paralelo
                    # 042:RF-104: con el conductor de la terna del perfil, los dos circuitos son de ese conductor.
                    nombre_nuevo = (o.get('cambia_tipo') or {}).get(str(nombre))
                    nuevo, largo = self.tipos.get(str(nombre_nuevo)), r.get('largo_km')
                    if nombre_nuevo and nuevo and largo is not None and nuevo.get('sline'):
                        r['r_ohm'] = float(nuevo.get('rline') or 0.0) * float(largo) / 2
                        r['x_ohm'] = float(nuevo.get('xline') or 0.0) * float(largo) / 2
                        r['inom_ka'] = float(nuevo['sline']) * 2
                    else:
                        if nombre_nuevo:
                            avisos.append(f'sin datos de {nombre_nuevo} o del largo de {nombre}: la terna se mide '
                                          'con su conductor actual')
                        r['r_ohm'] = float(r.get('r_ohm') or 0.0) / 2
                        r['x_ohm'] = float(r.get('x_ohm') or 0.0) / 2
                        r['inom_ka'] = float(r.get('inom_ka') or 0.0) * 2
                    # 084:RF-16: con la capacidad del fabricante para esa configuración, no el doble del tipo.
                    capacidad = (o.get('capacidad_terna_a') or {}).get(str(nombre))
                    if capacidad:
                        r['inom_ka'] = float(capacidad) * 2 / 1000
                    continue
                tipo = self.tipos.get(str((o.get('tipo') or {}).get('nombre')))
                largo = r.get('largo_km')
                if not tipo or largo is None:
                    avisos.append(f'sin datos del conductor o del largo de {nombre}: la sección no se aplica')
                    continue
                r['r_ohm'] = float(tipo.get('rline') or 0.0) * float(largo)
                r['x_ohm'] = float(tipo.get('xline') or 0.0) * float(largo)
                if tipo.get('sline'):
                    r['inom_ka'] = float(tipo['sline'])
        return ramas

    def _sistema(self, obras: Sequence[Mapping[str, Any]], avisos: list[str]):
        """La red factorizada de las obras que cambian impedancia, una vez por combinación."""
        clave = tuple(sorted((o.get('clase'), tuple(o.get('tramos') or ()),
                              str((o.get('tipo') or {}).get('nombre')),
                              tuple(sorted((o.get('capacidad_terna_a') or {}).items())),
                              tuple(sorted((o.get('cambia_tipo') or {}).items())))                # 042:RF-104
                             for o in obras if o.get('clase') in ('terna', 'seccion')))
        if clave in self._sistemas:
            self._sistemas.move_to_end(clave)
        else:
            ramas = self._ramas_con(obras, avisos)
            m = muestra({**self.grafo, 'nodos': self._nodos, 'ramas': ramas})
            self._sistemas[clave] = (m, sistema_de(m), ramas)
            # 087:RF-43: solo las más recientes. Pisco entero (2026-11-04): unos 4 MB por combinación y Optuna, Pareto y
            # Shapley probaban cientos por alimentador; la web llegó a 6 GB y el trabajo cayó con MemoryError.
            while len(self._sistemas) > MAX_SISTEMAS:
                self._sistemas.popitem(last=False)
        return self._sistemas[clave]

    def activas(self, k: int, alimentador: str | None = None) -> list[Mapping[str, Any]]:
        """Las k primeras cargas nuevas; con ``alimentador``, solo las suyas (las de los demás,
        apartadas, como hace la escalera con ``apartar_cargas_de``, 025:RF-69)."""
        return [c for c in self.nuevas[:max(int(k), 0)]
                if alimentador is None or str(c.get('alimentador')) == str(alimentador)]

    def medir(self, obras: Sequence[Mapping[str, Any]], k: int, factor: float = 1.0,
              alimentador: str | None = None, *, factor_q: float | None = None,
              factor_nuevas: float = 1.0) -> Medida:
        """Flujo con la variante, las k primeras cargas nuevas y la demanda existente por ``factor``
        (la máxima, 1; un sorteo, el suyo) (RF-3).

        073:RF-22, RF-23: en valle, la Q con ``factor_q``, porque un valle medido no es la máxima a
        escala, y las cargas nuevas por ``factor_nuevas``.
        """
        avisos: list[str] = []
        m, sis, ramas = self._sistema(obras, avisos)
        pos = {n: i for i, n in enumerate(m.ids)}
        fq = factor if factor_q is None else factor_q
        s = np.array([complex(float(self._nodos[n].get('p_mw') or 0.0) * factor,
                              float(self._nodos[n].get('q_mvar') or 0.0) * fq) for n in m.ids]) / S_BASE
        for c in self.activas(k, alimentador):
            i = pos.get(c['nodo'])
            if i is not None:
                s[i] += complex(float(c.get('p_mw') or 0.0), float(c.get('q_mvar') or 0.0)) / S_BASE * factor_nuevas
        for o in obras:
            if o.get('clase') == 'condensador':
                n = self.nodo_de.get(str(o.get('barra')))
                if n is not None and n in pos:
                    s[pos[n]] -= 1j * float(o.get('q_kvar') or 0.0) / 1000.0 / S_BASE
        self.evaluaciones += 1
        sol = sis.resolver(s, exponente=self.exponente)
        if not sol.convergio:
            return Medida(False, {}, {}, None, None)
        v = sol.v.copy()
        oraculo = 'fisica'
        if self.pinn is not None:
            v, oraculo = self._con_pinn(m, s, ramas, v)
        aproximada = False
        for o in obras:
            if o.get('clase') == 'regulador':
                aproximada = self._regulador(o, m, v) or aproximada
        # Lo mismo que mide la escalera en DIgSILENT (025:RF-50): la tensión de las barras de media
        # y la carga de los tramos de línea. Con las de baja de cada SED y los transformadores, en
        # NA203 + NA205 (2026-11-01) el oráculo rechazaba hasta la carga mayor sola por su propio
        # transformador al 104 % y por una barra de baja ya fuera de límites.
        media = np.array([float(self._nodos[n].get('kv') or 0.0) >= KV_MEDIA_MIN for n in m.ids])
        energ = m.alimentado & ~m.fuente & media
        u = {nombre_corto(n): float(v[i]) for i, n in enumerate(m.ids) if m.alimentado[i] and media[i]}
        carga = {}
        if len(m.z):
            vc = sol.v * np.exp(1j * sol.theta)
            a, b = m.aristas
            corriente = np.abs(vc[a] - vc[b]) / np.abs(m.z)
            for e in range(0, len(m.ramas), 2):            # cada rama llega en los dos sentidos
                if m.inom[e] > 0 and m.ramas[e] in self._lineas:
                    carga[nombre_corto(m.ramas[e])] = float(100.0 * corriente[e] / m.inom[e])
        return Medida(True, u, carga, sol.perdidas_pu * S_BASE * 1000.0,
                      float(v[energ].min()) if energ.any() else None, aproximada, oraculo)

    def _con_pinn(self, m, s: np.ndarray, ramas: list[dict], v: np.ndarray) -> tuple[np.ndarray, str]:
        """La tensión del PINN promovido si la red está en su dominio; si no, la física (RF-17)."""
        # ``s`` no lleva los bancos, que están en ``m.s_shunt``; ``q_mvar`` es la neta (045:RF-3).
        nodos = {n: {**self._nodos[n], 'p_mw': float(s[i].real * S_BASE),
                     'q_mvar': float(s[i].imag * S_BASE) - float(self._nodos[n].get('banco_q_mvar') or 0.0)}
                 for i, n in enumerate(m.ids)}
        pred = self.pinn.predecir({**self.grafo, 'nodos': nodos, 'ramas': ramas})
        if pred.get('fuera_de_dominio'):
            return v, 'fisica'
        indice = {n: i for i, n in enumerate(pred['ids'])}
        if not all(n in indice for n in m.ids):
            return v, 'fisica'
        return np.array([float(pred['v'][indice[n]]) for n in m.ids]), 'pinn'

    def _regulador(self, o: Mapping[str, Any], m, v: np.ndarray) -> bool:
        """Aguas abajo del tramo, la tensión llevada a la consigna dentro del rango (RF-2).

        El flujo del gemelo no tiene tomas: se escala la tensión de lo que cuelga del tramo, sin
        la corriente que eso cambia. Es una aproximación y se dice; DIgSILENT confirma (RF-5).
        """
        i = self.rama_de.get(str(o.get('tramo')))
        if i is None:
            return False
        r = self._ramas[i]
        pos = {n: j for j, n in enumerate(m.ids)}
        a, b = pos.get(r.get('desde')), pos.get(r.get('hasta'))
        if a is None or b is None or v[b] <= 0:
            return False
        rango = float(o.get('rango_pct') or 10.0) / 100.0
        ratio = min(max(float(o.get('consigna_pu') or 1.0) / float(v[b]), 1 - rango), 1 + rango)
        abajo = _aguas_abajo(m, a, b)
        v[abajo] = v[abajo] * ratio
        return True

    def con_set_nueva(self, ramas: Sequence[Mapping[str, Any]], kv: float) -> 'Oraculo':
        """El mismo oráculo con la SET nueva: cada rama abierta en su tramo de ``entrada`` y
        alimentada desde la SET por una línea de ``distancia_km`` con ``r_ohm_km`` y ``x_ohm_km``
        hasta su barra ``nodo`` (052:RF-18)."""
        nodos = {n: dict(d) for n, d in (self.grafo.get('nodos') or {}).items()}
        ramas_g = [dict(r) for r in self.grafo.get('ramas') or []]
        for i, r in enumerate(ramas):
            j = self.rama_de.get(str(r.get('entrada')))
            if j is not None:
                ramas_g[j]['cerrada'] = False
            nodo = self.nodo_de.get(str(r.get('nodo')))
            if nodo is None:
                continue
            fuente = f'SET_NUEVA_{i}'
            nodos[fuente] = {'kv': kv, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': True, 'v_pu': 1.0}
            d = max(float(r.get('distancia_km') or 0.0), 0.001)
            ramas_g.append({'id': fuente, 'clase': 'ElmLne', 'desde': fuente, 'hasta': nodo,
                            'r_ohm': float(r.get('r_ohm_km') or 0.0) * d,
                            'x_ohm': float(r.get('x_ohm_km') or 0.0) * d,
                            'inom_ka': float(r.get('inom_ka') or 0.0), 'cerrada': True})
        return Oraculo({'nodos': nodos, 'ramas': ramas_g}, self.nuevas, self.tipos, self.exponente)

    # ------------------------------------------------------------------ criterio con k cargas
    def barras_de(self, k: int, alimentador: str | None = None) -> list[str]:
        """Las barras que juzga el criterio: la de media de cada carga (``barra``; la de una
        ampliación es la de baja de su SED, 042) o, sin ella, la de su nodo."""
        return list(dict.fromkeys(str(c.get('barra') or nombre_corto(c['nodo']))
                                  for c in self.activas(k, alimentador)))

    def en_valle(self, obras: Sequence[Mapping[str, Any]], k: int, p: Parametros, valle: Mapping[str, Any] | None,
                 alimentador: str | None = None) -> dict[str, Any]:
        """La variante en cada punto de valle, con el criterio de siempre (073:RF-17, RF-23, RF-30).

        Sin las cargas nuevas y con ellas (RF-39): pueden ingresar en cualquier momento, y sin ellas es
        el peor caso para la sobretensión. Tiene que cumplir en los dos. Sin puntos, ``valle`` es
        ``None``: no comprobado, nunca «cumple» (RF-24, RF-31).
        """
        out = sin_comprobar((valle or {}).get('motivo'))
        hay_nuevas = bool(self.activas(k, alimentador))
        for pt in (valle or {}).get('puntos') or []:
            fp, fq = float(pt['factor_p']), pt.get('factor_q')
            sin = self.medir([], 0, fp, factor_q=fq)
            for caso, factor_nuevas in CASOS_CARGAS:
                if factor_nuevas and not hay_nuevas:
                    continue
                con = self.medir(obras, k, fp, alimentador, factor_q=fq, factor_nuevas=factor_nuevas)
                # Sin las cargas nuevas no hay barra suya que juzgar: las demás, como en «Sin proyecto».
                barras = self.barras_de(k, alimentador) if factor_nuevas else []
                ok, motivos = cumple(sin.para_criterio(), con.para_criterio(), barras, p)
                anotar_punto(out, pt, caso, ok, motivos, con.u)
        return out

    def evaluar(self, obras: Sequence[Mapping[str, Any]], k: int, p: Parametros,
                factores: Sequence[float] = (), alimentador: str | None = None,
                valle: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Si la variante cumple con k cargas en la máxima, en qué fracción de los sorteos
        (025:RF-50, RF-52b) y en valle (073:RF-17), en la forma de ``escalera_optima.elegir``."""
        barras = self.barras_de(k, alimentador)
        con = self.medir(obras, k, 1.0, alimentador)
        sin = self.medir([], 0)
        ok, motivos = cumple(sin.para_criterio(), con.para_criterio(), barras, p)
        fraccion = None
        if ok and factores:
            buenos = 0
            for f in factores:
                c, s_ = self.medir(obras, k, f, alimentador), self.medir([], 0, f)
                buenos += cumple(s_.para_criterio(), c.para_criterio(), barras, p)[0]
            fraccion = buenos / len(factores)
        return {'maxima': ok, 'fraccion': fraccion, 'motivos': motivos,
                'perdidas_kw': con.perdidas_kw, 'v_min': con.v_min, 'aproximada': con.aproximada,
                **self.en_valle(obras, k, p, valle, alimentador)}


def _aguas_abajo(m, a: int, b: int) -> np.ndarray:
    """Las barras a las que se llega desde ``b`` sin pasar por ``a`` (el lado del tramo)."""
    vecinos: dict[int, list[int]] = {}
    for u, w in zip(m.aristas[0], m.aristas[1], strict=True):
        vecinos.setdefault(int(u), []).append(int(w))
    vistos, pila = {b}, [b]
    while pila:
        u = pila.pop()
        for w in vecinos.get(u, []):
            if w != a and w not in vistos:
                vistos.add(w)
                pila.append(w)
    return np.array(sorted(vistos), dtype=np.int64)


# =========================================================================== RF-14: Markov
def sorteos_markov(curva: Sequence[tuple[Any, Mapping[str, float]]], maximas: Mapping[str, float],
                   n: int, semilla: int, niveles: int = NIVELES_MARKOV) -> dict[str, Any]:
    """``n`` instantes de una cadena de Markov de la curva de cabecera del año (RF-14).

    Los estados son niveles de la demanda total (por cuantiles), la transición se cuenta entre
    instantes consecutivos y la cadena arranca de su distribución estacionaria. Cada sorteo es
    un instante real de su nivel, con el factor de cada alimentador como en
    ``escalera_optima.sorteos``. Con la misma semilla, lo mismo.
    """
    puntos = [(t, {f: float(kw) / float(maximas[f]) for f, kw in por.items()
                   if f in maximas and maximas[f] and kw is not None and math.isfinite(float(kw))})
              for t, por in curva]
    puntos = [(t, fs) for t, fs in puntos if set(fs) == set(maximas)]
    if not puntos:
        raise ValueError('la curva de cabecera no tiene ningún instante con todos los alimentadores')
    total = np.array([sum(fs.values()) for _, fs in puntos])
    niveles = max(1, min(int(niveles), len(set(total.round(9)))))
    cortes = np.quantile(total, np.linspace(0, 1, niveles + 1)[1:-1]) if niveles > 1 else np.array([])
    estado = np.searchsorted(cortes, total, side='right')
    p = np.zeros((niveles, niveles))
    for a, b in zip(estado[:-1], estado[1:], strict=True):
        p[a, b] += 1
    for i in range(niveles):                         # un nivel sin salida se queda en sí mismo
        p[i] = p[i] / p[i].sum() if p[i].sum() else np.eye(niveles)[i]
    valores, vectores = np.linalg.eig(p.T)
    pi = np.real(vectores[:, int(np.argmin(np.abs(valores - 1.0)))])
    pi = np.abs(pi) / np.abs(pi).sum()
    rng = random.Random(semilla)
    por_estado = {i: [j for j, e in enumerate(estado) if e == i] for i in range(niveles)}
    e = rng.choices(range(niveles), weights=pi.tolist())[0]
    out = []
    for _ in range(int(n)):
        j = rng.choice(por_estado[e]) if por_estado[e] else rng.randrange(len(puntos))
        out.append({'instante': str(puntos[j][0]), 'factores': puntos[j][1], 'nivel': int(e)})
        e = rng.choices(range(niveles), weights=p[e].tolist())[0]
    return {'sorteos': out, 'transicion': p.round(6).tolist(),
            'estacionaria': [float(x) for x in pi.round(6)], 'niveles': niveles}


# =========================================================================== RF-15: Shapley
def reparto_shapley(cargas: Sequence[str], costo_de_grupo: Callable[[frozenset[str]], float | None],
                    semilla: int, permutaciones: int = PERMUTACIONES_SHAPLEY) -> dict[str, Any]:
    """El costo de la obra repartido entre las cargas por su valor de Shapley (RF-15, RF-16).

    ``costo_de_grupo``: el costo anual de la variante más barata que cumple con ese grupo de
    cargas (None si ninguna cumple). Con hasta seis cargas, exacto (todas las permutaciones);
    con más, por permutaciones sorteadas: en cada una, cada carga paga lo que su llegada sube el
    costo del grupo. Los grupos ya vistos no se recalculan.
    """
    import itertools

    cargas = list(dict.fromkeys(cargas))
    memo: dict[frozenset[str], float | None] = {frozenset(): 0.0}

    def v(grupo: frozenset[str]) -> float | None:
        if grupo not in memo:
            memo[grupo] = costo_de_grupo(grupo)
        return memo[grupo]

    exacto = len(cargas) <= 6
    if exacto:
        ordenes = [list(o) for o in itertools.permutations(cargas)]
    else:
        rng = random.Random(semilla)
        ordenes = []
        for _ in range(int(permutaciones)):
            o = cargas[:]
            rng.shuffle(o)
            ordenes.append(o)
    aporte = {c: 0.0 for c in cargas}
    validas = 0
    for orden in ordenes:
        grupo: frozenset[str] = frozenset()
        previo, filas, completo = 0.0, {}, True
        for c in orden:
            grupo = grupo | {c}
            actual = v(grupo)
            if actual is None:
                completo = False
                break
            filas[c] = actual - previo
            previo = actual
        if completo:
            validas += 1
            for c, x in filas.items():
                aporte[c] += x
    if not validas:
        return {'reparto': {}, 'permutaciones': 0, 'grupos': len(memo), 'exacto': exacto,
                'aviso': 'ningún orden de las cargas cumple con todas: no hay costo que repartir'}
    return {'reparto': {c: aporte[c] / validas for c in cargas}, 'permutaciones': validas,
            'grupos': len(memo), 'exacto': exacto, 'costo_total': v(frozenset(cargas))}


# =========================================================================== RF-11 a RF-13
@dataclass
class Espacio:
    """Las obras que se combinan: módulos de banco por barra y, por tramo, nada, terna o sección."""
    alimentador: str
    barras: Sequence[str]
    banco_kvar: float | None
    modulos_max: int
    tramos: Sequence[Mapping[str, Any]]          # troncal: ``nombre`` y ``largo_m``
    secciones: Sequence[Mapping[str, Any]] = ()  # tipos aptos (``nombre``, ``origen``, ``proyecto``)
    ternas: Mapping[str, Any] | None = None      # 084:RF-16: ``planificacion.ternas_subterraneas``
    #: 042:RF-98: ``escalera_optima.tipos_de_terna``; ``None`` si el perfil no da ``escalera.conductor_terna``.
    de_terna: Mapping[str, Mapping[str, Any]] | None = None

    def opciones_tramo(self) -> list[str]:
        return ['nada', 'terna', *[f"seccion:{s['nombre']}" for s in self.secciones]]

    def obras(self, bancos: Sequence[int], por_tramo: Sequence[str]) -> Variante:
        """La variante de un genoma, con sus cantidades para ``escalera_optima.costo``."""
        obras: list[dict[str, Any]] = []
        cantidades: dict[str, float] = {}
        nombre = []
        for b, n in zip(self.barras, bancos, strict=True):
            if n and self.banco_kvar:
                obras.append({'clase': 'condensador', 'alimentador': self.alimentador, 'casos': [CON_PROYECTO],
                              'barra': b, 'q_kvar': float(self.banco_kvar) * int(n), 'escalones': int(n)})
                cantidades['bancos'] = cantidades.get('bancos', 0.0) + int(n)
                nombre.append(f'{int(n)}×{self.banco_kvar:g} kvar en {b}')
        ternas = [t for t, o in zip(self.tramos, por_tramo, strict=True) if o == 'terna']
        if ternas:
            # 042:RF-98, RF-103: la misma terna que la escalera, con el conductor del perfil en los dos circuitos.
            obra, km_cambia = obra_terna(self.alimentador, ternas, self.ternas, self.de_terna)
            obras.append(obra)
            cantidades['terna'] = sum(float(t.get('largo_m') or 0.0) for t in ternas) / 1000
            if km_cambia:
                cantidades['seccion'] = km_cambia
            nombre.append(f'terna en {len(ternas)} tramo(s)')
        por_tipo: dict[str, list] = {}
        for t, o in zip(self.tramos, por_tramo, strict=True):
            if o.startswith('seccion:'):
                por_tipo.setdefault(o.split(':', 1)[1], []).append(t)
        refs = {str(s['nombre']): s for s in self.secciones}
        for tipo, tramos in por_tipo.items():
            ref = refs.get(tipo, {})
            obras.append({'clase': 'seccion', 'alimentador': self.alimentador, 'casos': [CON_PROYECTO],
                          'tramos': [t['nombre'] for t in tramos],
                          'tipo': {'nombre': tipo, 'clase': 'TypLne', 'origen': ref.get('origen') or 'proyecto',
                                   'proyecto': ref.get('proyecto') or ''}})
            cantidades['seccion'] = cantidades.get('seccion', 0.0) + sum(
                float(t.get('largo_m') or 0.0) for t in tramos) / 1000
            nombre.append(f'sección {tipo} en {len(tramos)} tramo(s)')
        # 042:RF-103: el conductor que cambia con la terna se costea como sección, pero la obra sigue siendo una terna.
        clases = {o['clase'] for o in obras}
        escalones = tuple(e for e, c in (('bancos', 'condensador'), ('terna', 'terna'), ('seccion', 'seccion')) if c in clases)
        return Variante(' + '.join(nombre) or 'sin obras', escalones, obras, cantidades)


def barras_candidatas(oraculo: Oraculo, alimentador: str, k: int, base: Sequence[str], media: Sequence[str],
                      banco_kvar: float | None, maximo: int = CANDIDATAS_BANCO) -> dict[str, Any]:
    """Las barras de media del alimentador donde la búsqueda prueba bancos (087:RF-55, RF-56).

    AL209 (2026-11-06): la bayesiana y el NSGA-II solo veían la barra de la carga nueva; el usuario pidió la
    ubicación óptima en todo el alimentador. ``base`` (la barra de banco de cada carga) va siempre; de ``media``
    (las de media que existen sin las cargas nuevas), si no caben todas, las que más suben con un módulo la
    tensión de las barras de sus cargas y, a igualdad, más bajan las pérdidas. Una barra que el grafo no tiene o
    de baja tensión no entra: el banco no se podría medir.
    """
    # Con el flujo físico, en milisegundos, como la bayesiana: el PINN juzga solo las candidatas (052:RF-17).
    oraculo = _con_solo(oraculo, frozenset(str(c.get('variacion')) for c in oraculo.nuevas))
    oraculo.pinn = None
    base = [b for b in dict.fromkeys(str(x) for x in base)]
    validas =[b for b in dict.fromkeys(str(x) for x in media)
               if b not in base and b in oraculo.nodo_de
               and float(oraculo._nodos[oraculo.nodo_de[b]].get('kv') or 0.0) >= KV_MEDIA_MIN]
    libres = max(int(maximo) - len(base), 0)
    elegidas = validas
    if len(validas) > libres:
        barras = oraculo.barras_de(k, alimentador)

        def puntaje(b: str) -> tuple:
            m = oraculo.medir([{'clase': 'condensador', 'barra': b, 'q_kvar': float(banco_kvar or 0.0)}],
                              k, 1.0, alimentador)
            us = [m.u[x] for x in barras if x in m.u]
            return (-(min(us) if m.converge and us else -1.0),
                    m.perdidas_kw if m.converge and m.perdidas_kw is not None else math.inf, b)
        elegidas = [b for *_s, b in sorted(puntaje(b) for b in validas)[:libres]] if banco_kvar else []
    return {'barras': base + elegidas, 'media': len(validas) + len(base), 'descartadas': len(validas) - len(elegidas)}


def buscar_combinacion(espacio: Espacio, valorar: Callable[[Variante], tuple[float | None, bool, dict]],
                       *, evaluaciones: int = EVALUACIONES_BAYES, semilla: int = 0) -> dict[str, Any]:
    """La combinación de obras de menor costo anual que cumple, por búsqueda bayesiana (RF-11, RF-16).

    ``valorar(variante)`` da (costo anual o None, si cumple, detalle). Optuna (TPE) propone
    módulos de banco por barra y una opción por tramo; lo que no cumple se penaliza por encima de
    cualquier costo. Si se agota el presupuesto, se da lo mejor encontrado y cuántas usó.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    opciones = espacio.opciones_tramo()
    vistas: dict[tuple, tuple] = {}

    def objetivo(trial) -> float:
        bancos = [trial.suggest_int(f'banco_{i}', 0, espacio.modulos_max if espacio.banco_kvar else 0)
                  for i in range(len(espacio.barras))]
        tramos = [trial.suggest_categorical(f'tramo_{i}', opciones) for i in range(len(espacio.tramos))]
        clave = (tuple(bancos), tuple(tramos))
        if clave not in vistas:
            v = espacio.obras(bancos, tramos)
            vistas[clave] = (v, *valorar(v))
        _v, costo, ok, _det = vistas[clave]
        return float(costo) if ok and costo is not None else 1e15

    estudio = optuna.create_study(direction='minimize', sampler=optuna.samplers.TPESampler(seed=semilla))
    estudio.optimize(objetivo, n_trials=int(evaluaciones))
    buenas = [(c, v, d) for (v, c, ok, d) in vistas.values() if ok and c is not None]
    mejor = min(buenas, key=lambda t: (t[0], t[1].nombre), default=None)
    return {'variante': mejor[1] if mejor else None, 'costo_anual': mejor[0] if mejor else None,
            'detalle': mejor[2] if mejor else None, 'evaluaciones': len(estudio.trials),
            'distintas': len(vistas), 'agotado': len(estudio.trials) >= int(evaluaciones),
            'cumplen': len(buenas)}


def frente_pareto(espacio: Espacio,
                  medir: Callable[[Variante], tuple[float | None, float | None, float | None, bool]],
                  *, semilla: int = 0, poblacion: int = 24, generaciones: int = 20) -> dict[str, Any]:
    """Costo anual, pérdidas y 1 − tensión mínima de las combinaciones, con el NSGA-II del gemelo (RF-13).

    ``medir(variante)`` da (costo, pérdidas kW, tensión mínima p.u., si cumple). Lo que no cumple
    entra como violación de la restricción, no como objetivo.
    """
    opciones = espacio.opciones_tramo()
    nb, nt = len(espacio.barras), len(espacio.tramos)
    sup_b = espacio.modulos_max if espacio.banco_kvar else 0

    def decodificar(g: np.ndarray) -> Variante:
        bancos = [int(round(x)) for x in g[:nb]]
        tramos = [opciones[min(int(round(x)), len(opciones) - 1)] for x in g[nb:]]
        return espacio.obras(bancos, tramos)

    def objetivos(g: np.ndarray) -> tuple[list[float], float]:
        costo, perdidas, vmin, ok = medir(decodificar(g))
        if costo is None or perdidas is None or vmin is None:
            return [1e15, 1e15, 1.0], 1.0
        return [float(costo), float(perdidas), 1.0 - float(vmin)], 0.0 if ok else 1.0

    frente = nsga2(objetivos, [0] * (nb + nt), [sup_b] * nb + [len(opciones) - 1] * nt,
                   poblacion=poblacion, generaciones=generaciones, semilla=semilla,
                   iniciales=[np.zeros(nb + nt)])
    filas = []
    for g, obj, vio in zip(frente.soluciones, frente.objetivos, frente.violacion, strict=True):
        if vio > 0:
            continue
        filas.append({'variante': decodificar(g).nombre, 'costo_anual': float(obj[0]),
                      'perdidas_kw': float(obj[1]), 'v_min': 1.0 - float(obj[2])})
    return {'frente': sorted(filas, key=lambda f: f['costo_anual']),
            'evaluaciones': frente.evaluaciones, 'generaciones': frente.generaciones}


# =========================================================================== RF-4, RF-12: búsqueda
@dataclass
class Alimentador:
    """Lo de un alimentador para la búsqueda: sus variantes de la escalera, cómo costear una
    (``costo(variante, perdidas_kw)`` → costo anual o None) y el espacio de la bayesiana."""
    nombre: str
    variantes: Sequence[Variante]
    costo: Callable[[Variante, float | None], float | None]
    espacio: Espacio | None = None


def _cumple_en(e: Mapping[str, Any], p: Parametros) -> bool:
    """Cumple con la máxima, si se sorteó en la fracción del perfil (025:RF-52b) y, si se midió,
    en valle: la fracción no lo compensa (073:RF-18)."""
    return (bool(e.get('maxima')) and (e.get('fraccion') is None or e['fraccion'] >= p.cumplimiento)
            and e.get('valle') is not False)


def modulos_en_valle(oraculo: Oraculo, barras: Sequence[str], banco_kvar: float, valle: Mapping[str, Any] | None,
                     p: Parametros, *, k: int = 0, alimentador: str | None = None,
                     tope: int | None = None) -> dict[str, Any]:
    """Cuántos módulos de banco en cada barra admite el valle: el mayor que aún cumple (073:RF-19).

    Sube de uno en uno con el flujo físico y para al pasarse o al no converger: en una red radial la
    tensión solo sube con la Q, así que no hace falta otro tope que ``tope``, el del perfil. Si el
    banco no mueve la tensión (una barra fuera del grafo, un tramo sin impedancia), para y lo dice.
    """
    out: dict[str, Any] = {'modulos': None, 'comprobado': False, 'por_tope': False, 'u_max': None,
                           'motivo': (valle or {}).get('motivo') or '', 'aviso': None}
    puntos = (valle or {}).get('puntos') or []
    if not puntos or not banco_kvar:
        return out
    rapido = _con_solo(oraculo, frozenset(str(c.get('variacion')) for c in oraculo.nuevas))
    rapido.pinn = None
    out.update(modulos=0, comprobado=True)
    barras = [b for b in barras if b in rapido.nodo_de]
    if not barras:
        out['aviso'] = 'las barras del banco no están en el grafo: el valle no admite ningún módulo sin medirlo'
        return out
    pt = puntos[0]

    def tension(n: int) -> float:
        obras = [{'clase': 'condensador', 'barra': b, 'q_kvar': float(banco_kvar) * n} for b in barras]
        u = rapido.medir(obras, k, float(pt['factor_p']), alimentador, factor_q=pt.get('factor_q'),
                         factor_nuevas=0.0).u               # sin ellas: el peor caso (073:RF-39)
        return sum(u.get(b, 0.0) for b in barras)

    previa = tension(0)
    while tope is None or out['modulos'] < int(tope):
        n = out['modulos'] + 1
        e = rapido.en_valle([{'clase': 'condensador', 'barra': b, 'q_kvar': float(banco_kvar) * n} for b in barras],
                            k, p, valle, alimentador)
        if e['valle'] is False:
            return out
        ahora = tension(n)
        if ahora <= previa + 1e-12:
            out['aviso'] = f'{banco_kvar:g} kvar no mueven la tensión de {", ".join(barras)}: se para en {n - 1} módulos'
            return out
        previa = ahora
        out.update(modulos=n, u_max=e['valle_u_max'])
    out['por_tope'] = True
    return out


def buscar_k(oraculo: Oraculo, alimentadores: Sequence[Alimentador], p: Parametros,
             factores: Sequence[float] = (), *, valle: Mapping[str, Any] | None = None) -> tuple[int, list[dict[str, Any]]]:
    """El mayor k de cargas que caben con obra en cada alimentador, con el oráculo (RF-4).

    Galope y bisección de la 042 (``set_nueva.cuantas_caben``); para cada k, en cada alimentador
    con cargas entre las k, basta la primera variante, de la más barata a la más cara, que cumple.
    """
    from .set_nueva import cuantas_caben

    def cabe(k: int) -> bool:
        for a in alimentadores:
            if not oraculo.activas(k, a.nombre):
                continue
            if _cumple_en(oraculo.evaluar([], k, p, factores, a.nombre, valle), p):
                continue                               # ya cumple sin obra (025:RF-74)
            # 063:RF-22: primero el escalón más bajo (bancos, sección, terna), luego el costo.
            baratas = sorted(a.variantes, key=lambda v: (rango_escalon(v.escalones), a.costo(v, None) is None,
                                                         a.costo(v, None) or 0.0, v.nombre))
            if not any(_cumple_en(oraculo.evaluar(v.obras, k, p, factores, a.nombre, valle), p) for v in baratas):
                return False
        return True

    return cuantas_caben(len(oraculo.nuevas), cabe)


def perdidas_de_energia_markov(oraculo: Oraculo, obras: Sequence[Mapping[str, Any]], k: int, markov: Mapping[str, Any],
                               alimentador: str | None = None) -> dict[str, Any] | None:
    """087:RF-13: la energía perdida al año: las pérdidas de cada nivel de la cadena de Markov, por su probabilidad estacionaria.

    El factor de cada nivel es la media de sus sorteos; un nivel sin sorteos no cuenta, y las probabilidades se reparten entre el resto.
    """
    pi = list(markov.get('estacionaria') or [])
    por_nivel: dict[int, list[float]] = {}
    for x in markov.get('sorteos') or []:
        fs = list((x.get('factores') or {}).values())
        if fs:
            por_nivel.setdefault(int(x.get('nivel') or 0), []).append(sum(fs) / len(fs))
    total = sum(pi[i] for i in por_nivel if i < len(pi))
    if not total:
        return None
    kw = 0.0
    for i, fs in por_nivel.items():
        if i >= len(pi):
            continue
        perdidas = oraculo.medir(obras, k, sum(fs) / len(fs), alimentador).perdidas_kw
        if perdidas is None:
            return None
        kw += pi[i] / total * float(perdidas)
    return {'perdidas_medias_kw': round(kw, 3), 'energia_kwh_anio': round(kw * 8760.0, 1), 'niveles': len(por_nivel)}


def margen_de_demanda(oraculo: Oraculo, obras: Sequence[Mapping[str, Any]], k: int, p: Parametros, alimentador: str | None = None,
                      *, hasta: float = 3.0, pasos: int = 12) -> float:
    """087:RF-29: cuánto puede crecer la demanda existente (0,1 = 10 %) antes de incumplir; 0 si ya no cumple; por bisección."""
    def bien(factor: float) -> bool:
        m = oraculo.medir(obras, k, factor, alimentador)
        return (m.converge and all(p.tension_min_pu <= u <= p.tension_max_pu for u in m.u.values())
                and all(c <= p.cargabilidad_max_pct for c in m.carga.values()))

    if not bien(1.0):
        return 0.0
    if bien(hasta):
        return hasta - 1.0
    bajo, alto = 1.0, hasta
    for _ in range(int(pasos)):
        medio = (bajo + alto) / 2
        bajo, alto = (medio, alto) if bien(medio) else (bajo, medio)
    return bajo - 1.0


def seleccion_por_alimentador(oraculo: Oraculo, alimentadores: Sequence[Alimentador], p: Parametros, factores: Sequence[float] = (),
                              *, evaluaciones_bayes: int = EVALUACIONES_BAYES, semilla: int = 0,
                              valle: Mapping[str, Any] | None = None,
                              markov: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """087:RF-1, RF-10, RF-11, RF-13: cada alimentador, con todas las cargas nuevas puestas: el orden en que DIgSILENT lo mide.

    El que ya cumple en el oráculo no gasta búsqueda bayesiana ni frente: no le hace falta obra.
    """
    k = len(oraculo.nuevas)
    out: dict[str, dict[str, Any]] = {}
    for a in alimentadores:
        if not oraculo.activas(k, a.nombre):
            continue
        ya = _cumple_en(oraculo.evaluar([], k, p, factores, a.nombre, valle), p)
        e = elegir_para_k(oraculo, [a], k, p, factores, evaluaciones_bayes=0 if ya else evaluaciones_bayes, permutaciones=0,
                          semilla=semilla, pareto=not ya, valle=valle).get(a.nombre)
        if e is None:
            continue
        e['ya_cumple'] = ya
        primera = e['orden'][0] if e['orden'] and e['elegida'] else None
        e['margen'] = round(margen_de_demanda(oraculo, [], k, p, a.nombre), 4)
        e['margen_con_obra'] = round(margen_de_demanda(oraculo, primera.obras, k, p, a.nombre), 4) if primera is not None else None
        e['perdidas_energia'] = (perdidas_de_energia_markov(oraculo, primera.obras, k, markov, a.nombre)
                                 if primera is not None and markov else None)
        out[a.nombre] = e
    return out


#: Las obras que el oráculo sabe calcular (``Oraculo._ramas_con`` y ``medir``): las demás solo las mide DIgSILENT.
MODELADAS = frozenset({'terna', 'seccion', 'condensador', 'regulador'})


def modelable(v: Variante) -> bool:
    """087:RF-41: si el oráculo puede juzgar la variante. El paso a 22,9 kV (migración, tensión, elevador) no."""
    return all(o.get('clase') in MODELADAS for o in v.obras)


def a_confirmar(eleccion: Mapping[str, Any], tanda: int) -> list[Variante]:
    """087:RF-39: lo que DIgSILENT confirma de un alimentador: las que el oráculo da por cumplidoras y una sola tanda
    de las más cercanas, por si el oráculo se equivoca. El resto no se mide: si ninguna de estas cumple, no la va a
    cumplir otra de menos (Pisco, 2026-11-04: AL209 medía en DIgSILENT sus 150 variantes, una por minuto, cuando la
    primera que cumplía era la 12.ª y las de bancos se quedaban a 0,93 p.u.)."""
    orden = list(eleccion.get('orden') or [])
    buenas = sum(1 for t in eleccion.get('tabla') or [] if t.get('cumple') and t.get('costo_anual') is not None)
    return orden[:buenas + max(1, int(tanda))]


def tandas(orden: Sequence[Variante], n: int) -> list[list[Variante]]:
    """087:RF-2, RF-3: las variantes de ``n`` en ``n``, en su orden."""
    n = max(1, int(n))
    return [list(orden[i:i + n]) for i in range(0, len(orden), n)]


def _con_solo(oraculo: Oraculo, grupo: frozenset[str]) -> Oraculo:
    """El mismo oráculo (y su red ya factorizada) con solo esas cargas nuevas."""
    sub = Oraculo.__new__(Oraculo)
    sub.__dict__.update(oraculo.__dict__)
    sub.nuevas = [c for c in oraculo.nuevas if str(c.get('variacion')) in grupo]
    return sub


def elegir_para_k(oraculo: Oraculo, alimentadores: Sequence[Alimentador], k: int, p: Parametros,
                  factores: Sequence[float] = (), *, evaluaciones_bayes: int = EVALUACIONES_BAYES,
                  permutaciones: int = PERMUTACIONES_SHAPLEY, semilla: int = 0,
                  pareto: bool = True, valle: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Por alimentador con cargas entre las k: el orden en que DIgSILENT debe confirmar (RF-5),
    con la bayesiana primero si cumple y cuesta menos (RF-12), el frente (RF-13) y el reparto de
    Shapley del costo de la elegida entre sus cargas (RF-15)."""
    campos = ('maxima', 'fraccion', 'motivos', 'perdidas_kw', 'v_min', 'aproximada', 'valle', 'valle_motivos',
              'valle_u_max', 'valle_nodo', 'valle_fecha', 'valle_sin_comprobar', 'valle_casos')   # 073:RF-30
    # Explorar (bayesiana, frente, Shapley) con el flujo físico, en milisegundos; el PINN juzga solo
    # las candidatas (RF-17). Con el PINN en cada combinación, NA203 + NA205 (2026-11-01) pasaba de 7 min.
    rapido = _con_solo(oraculo, frozenset(str(c.get('variacion')) for c in oraculo.nuevas))
    rapido.pinn = None
    out: dict[str, dict[str, Any]] = {}
    for a in alimentadores:
        suyas = oraculo.activas(k, a.nombre)
        if not suyas:
            continue
        tabla = []
        for v in a.variantes:
            e = oraculo.evaluar(v.obras, k, p, factores, a.nombre, valle)
            tabla.append({'variante': v, 'cumple': _cumple_en(e, p),
                          'costo_anual': a.costo(v, e.get('perdidas_kw')), **{x: e.get(x) for x in campos}})
        bayes = None
        if a.espacio is not None and evaluaciones_bayes > 0:
            # Con la máxima, que descarta casi todo; los sorteos, solo a lo que la cumple (abajo).
            # Con los 200 sorteos en cada combinación, NA203 + NA205 (2026-11-01) pasaba de 15 min.
            def valorar(v: Variante, a=a):
                e = rapido.evaluar(v.obras, k, p, (), a.nombre, valle)                 # 073:RF-21
                return a.costo(v, e.get('perdidas_kw')), _cumple_en(e, p), e
            bayes = buscar_combinacion(a.espacio, valorar, evaluaciones=evaluaciones_bayes, semilla=semilla)
            if bayes['variante'] is not None:
                e = oraculo.evaluar(bayes['variante'].obras, k, p, factores, a.nombre, valle)
                tabla.append({'variante': bayes['variante'], 'cumple': _cumple_en(e, p),
                              'costo_anual': a.costo(bayes['variante'], e.get('perdidas_kw')),
                              'bayesiana': True, **{x: e.get(x) for x in campos}})
        buenas = sorted((t for t in tabla if t['cumple'] and t['costo_anual'] is not None),
                        key=lambda t: (rango_escalon(t['variante'].escalones), t['costo_anual'], t['variante'].nombre))
        cercanas = sorted((t for t in tabla if not (t['cumple'] and t['costo_anual'] is not None)),
                          key=lambda t: (not t.get('maxima'), -(t.get('fraccion') or 0.0),
                                         -(t.get('v_min') or 0.0), t['variante'].nombre))
        frente = None
        if pareto and a.espacio is not None:
            def medir(v: Variante, a=a):
                e = rapido.evaluar(v.obras, k, p, (), a.nombre, valle)                 # 073:RF-21
                return a.costo(v, e.get('perdidas_kw')), e.get('perdidas_kw'), e.get('v_min'), _cumple_en(e, p)
            frente = frente_pareto(a.espacio, medir, semilla=semilla)
        shapley = None
        if buenas:
            candidatas = [t['variante'] for t in buenas]

            def costo_grupo(grupo: frozenset[str], a=a):
                sub = _con_solo(rapido, grupo)
                n = len(sub.nuevas)
                if _cumple_en(sub.evaluar([], n, p, (), a.nombre, valle), p):
                    return 0.0
                for v in candidatas:
                    e = sub.evaluar(v.obras, n, p, (), a.nombre, valle)                # 073:RF-21
                    if _cumple_en(e, p):
                        return a.costo(v, e.get('perdidas_kw'))
                return None
            shapley = reparto_shapley([str(c.get('variacion')) for c in suyas], costo_grupo, semilla, permutaciones)
        elegida = buenas[0]['variante'].nombre if buenas else None
        if frente and elegida:
            for fila in frente['frente']:
                fila['elegida'] = fila['variante'] == elegida
        resumen_bayes = None
        if bayes:
            resumen_bayes = {x: bayes[x] for x in ('evaluaciones', 'distintas', 'agotado', 'cumplen', 'costo_anual')}
            resumen_bayes['variante'] = bayes['variante'].nombre if bayes['variante'] else None
        out[a.nombre] = {'orden': [t['variante'] for t in buenas + cercanas], 'elegida': elegida,
                         'tabla': [{**{x: t.get(x) for x in t if x != 'variante'}, 'nombre': t['variante'].nombre}
                                   for t in buenas + cercanas],
                         'bayesiana': resumen_bayes, 'pareto': frente, 'shapley': shapley}
    return out
