"""Flujo de carga físico por matriz de admitancias, con lazos (spec 024, RF-64 a RF-66).

Es la física sobre la que la PINN aprende su corrección y con la que los algoritmos
evolutivos evalúan cada obra candidata. El barrido radial que la precedía recorría un árbol
desde cada fuente y descartaba las ramas que cierran un lazo: en IN111–TA225 (2470 barras,
3 lazos) se apartaba 0,019 p.u. de DIgSILENT y llevaba a elegir un modelo de carga que no
es el suyo; con la matriz de admitancias el error es 0,0032 p.u. con potencia constante
(2026-10-24).

Método de la matriz de impedancias implícita (Z-bus): las fuentes fijan su tensión y el
resto de barras resuelve ``Y_LL·V_L = I_L(V) − Y_LS·V_S`` por punto fijo, con la
factorización LU de ``Y_LL`` hecha una sola vez. Los acopladores (impedancia nula) unen sus
dos barras en una antes de factorizar: con su admitancia de 10⁶ p.u. la matriz quedaba mal
condicionada.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Por debajo de esta impedancia (p.u.) una rama es un acoplador y une sus dos barras.
Z_ACOPLADOR = 1e-5


@dataclass
class Solucion:
    v: np.ndarray            # magnitud por barra original (0 sin fuente)
    theta: np.ndarray        # ángulo en radianes
    iteraciones: int
    convergio: bool
    perdidas_pu: float       # potencia activa perdida en las ramas, por unidad
    s_fuentes: np.ndarray    # potencia compleja que entrega cada fuente (p.u.), en orden de barra


class SistemaMallado:
    """La red reducida y factorizada, lista para resolver muchas demandas distintas.

    ``aristas`` trae cada rama en los dos sentidos (como ``oraculo.Muestra``); ``z`` es su
    impedancia por unidad. Las barras sin camino a una fuente quedan a 0 p.u.
    """

    def __init__(self, aristas: np.ndarray, z: np.ndarray, fuente: np.ndarray,
                 consigna: np.ndarray, alimentado: np.ndarray):
        import scipy.sparse as sp
        import scipy.sparse.linalg as spl

        n = len(fuente)
        a, b = (np.asarray(aristas[0], dtype=np.int64), np.asarray(aristas[1], dtype=np.int64))
        z = np.asarray(z, dtype=complex)
        padre = np.arange(n)

        def raiz(i: int) -> int:
            while padre[i] != i:
                padre[i] = padre[padre[i]]
                i = int(padre[i])
            return i

        acoplador = np.abs(z) < Z_ACOPLADOR
        for k in np.flatnonzero(acoplador):
            ra, rb = raiz(int(a[k])), raiz(int(b[k]))
            if ra != rb:
                padre[max(ra, rb)] = min(ra, rb)
        rep = np.array([raiz(i) for i in range(n)], dtype=np.int64)
        _, self.indice = np.unique(rep, return_inverse=True)
        self.n = int(self.indice.max()) + 1 if n else 0
        ramas = ~acoplador
        ka, kb = self.indice[a[ramas]], self.indice[b[ramas]]
        y = 1.0 / z[ramas]
        # Cada rama llega en los dos sentidos: (a,a) += y y (a,b) −= y por sentido.
        self.y = sp.coo_matrix((np.concatenate([y, -y]), (np.concatenate([ka, ka]), np.concatenate([ka, kb]))),
                               shape=(self.n, self.n)).tocsr()
        self.fuente = np.zeros(self.n, dtype=bool)
        np.logical_or.at(self.fuente, self.indice, np.asarray(fuente, dtype=bool))
        self.alimentado = np.zeros(self.n, dtype=bool)
        np.logical_or.at(self.alimentado, self.indice, np.asarray(alimentado, dtype=bool))
        self.consigna = np.ones(self.n)
        self._fuentes_orig = np.flatnonzero(fuente)
        for i in self._fuentes_orig:
            self.consigna[self.indice[i]] = float(consigna[i])
        self.libres = np.flatnonzero(self.alimentado & ~self.fuente)
        self.fijas = np.flatnonzero(self.fuente)
        self.y_ls = self.y[self.libres][:, self.fijas]
        self._lu = spl.splu(self.y[self.libres][:, self.libres].tocsc()) if len(self.libres) else None

    def resolver(self, s_carga: np.ndarray, *, exponente: float = 0.0, consigna: np.ndarray | None = None,
                 iteraciones: int = 200, tolerancia: float = 1e-10) -> Solucion:
        """Tensiones con la demanda ``s_carga`` por barra original (p.u., positiva consume).

        La carga consume S0·|V|^exponente. ``consigna`` cambia la tensión de las fuentes
        (una por fuente, en orden de barra) sin volver a factorizar.
        """
        s = np.zeros(self.n, dtype=complex)
        np.add.at(s, self.indice, np.asarray(s_carga, dtype=complex))
        vs = self.consigna.copy()
        if consigna is not None:
            for i, u in zip(self._fuentes_orig, consigna, strict=True):
                vs[self.indice[i]] = float(u)
        v = np.where(self.alimentado, 1.0, 0.0).astype(complex)
        v[self.fijas] = vs[self.fijas]
        convergio, it = True, 0
        if self._lu is not None:
            libres = self.libres
            empuje = self.y_ls @ v[self.fijas]
            convergio = False
            for it in range(1, iteraciones + 1):
                vl = v[libres]
                corriente = -np.conj(s[libres] * np.abs(vl) ** exponente / vl)
                nuevo = self._lu.solve(corriente - empuje)
                if not np.all(np.isfinite(nuevo)):
                    break
                cambio = float(np.max(np.abs(nuevo - vl)))
                v[libres] = nuevo
                if cambio < tolerancia:
                    convergio = True
                    break
                if cambio > 10.0:       # diverge: demanda que la red no puede llevar
                    break
        inyeccion = v * np.conj(self.y @ v)
        # Lo que entra a la red por todas las barras es lo que se pierde en sus ramas.
        perdidas = float(np.sum(inyeccion.real)) if convergio else float('nan')
        s_fuentes = np.array([inyeccion[self.indice[i]] + s[self.indice[i]] * abs(v[self.indice[i]]) ** exponente
                              for i in self._fuentes_orig])
        return Solucion(np.abs(v)[self.indice], np.angle(v)[self.indice], it, convergio,
                        perdidas, s_fuentes)
