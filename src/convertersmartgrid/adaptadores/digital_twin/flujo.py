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

Las relaciones de un transformador (045:RF-4) entran en la matriz: una barra de 10 kV con un
transformador de 10,5 kV o una toma fuera de la neutra no están a la relación 1. Un banco consume
S·|V|², impedancia constante, sea cual sea el modelo de las cargas.
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
    impedancia por unidad. Las barras sin camino a una fuente quedan a 0 p.u. ``ru`` y ``rw`` son la
    relación de cada arista en su origen y en su destino (1 sin transformador) y ``s_shunt`` lo que
    consume cada banco a 1 p.u.
    """

    def __init__(self, aristas: np.ndarray, z: np.ndarray, fuente: np.ndarray,
                 consigna: np.ndarray, alimentado: np.ndarray, ru: np.ndarray | None = None,
                 rw: np.ndarray | None = None, s_shunt: np.ndarray | None = None):
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
        origen = np.ones(len(z)) if ru is None else np.asarray(ru, dtype=float)
        destino = np.ones(len(z)) if rw is None else np.asarray(rw, dtype=float)
        ro, rd = origen[ramas], destino[ramas]
        # Cada rama llega en los dos sentidos: (a,a) += y/ro² y (a,b) −= y/(ro·rd) por sentido.
        self.y = sp.coo_matrix((np.concatenate([y / ro ** 2, -y / (ro * rd)]),
                                (np.concatenate([ka, ka]), np.concatenate([ka, kb]))),
                               shape=(self.n, self.n)).tocsr()
        self.s_shunt = np.zeros(self.n, dtype=complex)
        if s_shunt is not None:
            np.add.at(self.s_shunt, self.indice, np.asarray(s_shunt, dtype=complex))
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
                corriente = -np.conj((s[libres] * np.abs(vl) ** exponente + self.s_shunt[libres] * np.abs(vl) ** 2) / vl)
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
            if not convergio:
                # 045:RF-14: el punto fijo oscila en una red muy cargada aunque tenga solución. Red 9f53b98… del búfer
                # (2026-11-11): DIgSILENT da 0,54 p.u. en su barra más baja y el punto fijo no bajaba de 0,01 de cambio
                # con 2 000 iteraciones; sin solución, la física daba 0 p.u. y la PINN aprendía de ceros (mae 0,354).
                v_newton = self._newton(s, v, exponente, tolerancia)
                if v_newton is not None:
                    v, convergio = v_newton, True
        inyeccion = v * np.conj(self.y @ v)
        # Lo que entra a la red por todas las barras es lo que se pierde en sus ramas.
        perdidas = float(np.sum(inyeccion.real)) if convergio else float('nan')
        s_fuentes = np.array([inyeccion[self.indice[i]] + s[self.indice[i]] * abs(v[self.indice[i]]) ** exponente
                              + self.s_shunt[self.indice[i]] * abs(v[self.indice[i]]) ** 2
                              for i in self._fuentes_orig])
        return Solucion(np.abs(v)[self.indice], np.angle(v)[self.indice], it, convergio,
                        perdidas, s_fuentes)

    def _newton(self, s: np.ndarray, v0: np.ndarray, exponente: float, tolerancia: float,
                iteraciones: int = 50) -> np.ndarray | None:
        """045:RF-14: Newton-Raphson en coordenadas polares sobre las barras libres; las fuentes son de tensión fija.

        Balance en cada barra libre: ``V·conj(Y·V) + s·|V|^e + s_shunt·|V|²`` = 0 (la carga es positiva cuando consume).
        Jacobiano disperso como en MATPOWER (``dSbus_dV``) más la derivada de la carga con |V|. Parte del perfil plano,
        no del punto fijo que osciló. ``None`` si no converge.
        """
        import scipy.sparse as sp
        import scipy.sparse.linalg as spl

        libres = self.libres
        if not len(libres):
            return v0
        v = v0.copy()
        v[libres] = 1.0 + 0j
        y = self.y
        for _ in range(iteraciones):
            corriente = y @ v
            vm = np.abs(v)
            balance = (v * np.conj(corriente) + s * vm ** exponente + self.s_shunt * vm ** 2)[libres]
            if not np.all(np.isfinite(balance)):
                return None
            if float(np.max(np.abs(balance))) < max(tolerancia, 1e-9):
                return v
            vn = np.where(vm > 0, v / np.where(vm > 0, vm, 1.0), 0)
            d_v, d_i, d_vn = sp.diags(v), sp.diags(corriente), sp.diags(vn)
            ds_dvm = d_v @ np.conj(y @ d_vn) + np.conj(d_i) @ d_vn
            ds_dva = 1j * d_v @ np.conj(d_i - y @ d_v)
            carga_dvm = exponente * s * np.where(vm > 0, vm, 1.0) ** (exponente - 1) + 2 * self.s_shunt * vm
            ds_dvm = ds_dvm + sp.diags(carga_dvm)
            a = ds_dva.tocsr()[libres][:, libres]
            m = ds_dvm.tocsr()[libres][:, libres]
            jac = sp.bmat([[a.real, m.real], [a.imag, m.imag]], format='csc')
            try:
                paso = spl.spsolve(jac, -np.concatenate([balance.real, balance.imag]))
            except (RuntimeError, ValueError):
                return None
            if not np.all(np.isfinite(paso)):
                return None
            k = len(libres)
            # Paso con búsqueda lineal hacia atrás: cerca del colapso de tensión el paso entero se pasa y oscila (red
            # 9f53b98…: el desbalance bajaba a 0,0018 y volvía a 0,01). Se acepta el primero que reduce el desbalance.
            actual = float(np.max(np.abs(balance)))
            for alfa in (1.0, 0.5, 0.25, 0.125, 0.0625):
                magnitud = vm[libres] + alfa * paso[k:]
                if np.any(magnitud <= 0):
                    continue
                prueba = v.copy()
                prueba[libres] = magnitud * np.exp(1j * (np.angle(v[libres]) + alfa * paso[:k]))
                pm = np.abs(prueba)
                nuevo = (prueba * np.conj(y @ prueba) + s * pm ** exponente + self.s_shunt * pm ** 2)[libres]
                if np.all(np.isfinite(nuevo)) and float(np.max(np.abs(nuevo))) < actual:
                    v = prueba
                    break
            else:
                return None
        return None
