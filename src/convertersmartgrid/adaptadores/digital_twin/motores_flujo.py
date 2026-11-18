"""Motores de flujo del oráculo sobre la red ya factorizada de ``SistemaMallado`` (spec 083, RF-16 a RF-19).

Todos reciben lo mismo y dan la misma ``Solucion``: la red es una sola y solo cambia quién la resuelve.

- ``zbus``: el punto fijo de siempre (``SistemaMallado.resolver``).
- ``anderson``: el mismo punto fijo con aceleración de Anderson; sin dependencias. No es el de por defecto: ver ``resolver_con``.
- ``newton``: Newton-Raphson con KLU de lightsim2grid, más robusto cerca del límite de la red.
- ``pgm``: power-grid-model. ``dss``: OpenDSS (dss-python). Los dos resuelven aquí la red equilibrada; son los que pueden
  crecer al desequilibrado cuando el grafo traiga las fases (spec 082).

Las dependencias van aparte del ``.venv`` (``requirements-motores.txt``); sin ellas se dice y decide el Z-bus. Solo se admiten
cargas de potencia constante en los motores externos: es lo que usa la calibración.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .flujo import Solucion, SistemaMallado

#: Dónde están las dependencias de los motores externos.
CARPETA_DEPENDENCIAS = Path.home() / '.convertersmartgrid' / 'motores_deps'
#: El motor elegido; sin él, ``auto``.
VARIABLE_MOTOR = 'CSG_MOTOR_FLUJO'
#: Iteraciones que recuerda Anderson: con pocas ya converge, y más solo gasta memoria.
MEMORIA_ANDERSON = 5


class MotorNoDisponible(RuntimeError):
    """El motor pedido no se puede usar aquí; se dice y decide otro."""


def _rutas_de_dependencias() -> None:
    carpeta = os.environ.get('CSG_MOTORES_DEPS') or str(CARPETA_DEPENDENCIAS)
    if Path(carpeta).is_dir() and carpeta not in sys.path:
        sys.path.append(carpeta)      # al final: lo del .venv siempre manda


def _sin_converger(sis: SistemaMallado, s: np.ndarray, iteraciones: int = 0) -> Solucion:
    return Solucion(np.zeros(len(sis.indice)), np.zeros(len(sis.indice)), iteraciones, False, float('nan'),
                    np.zeros(len(sis._fuentes_orig), dtype=complex))


def _solucion(sis: SistemaMallado, v: np.ndarray, s: np.ndarray, iteraciones: int) -> Solucion:
    '''La misma salida de ``SistemaMallado.resolver`` a partir de las tensiones de las barras unidas.'''
    # Un motor puede declarar convergencia con tensiones nan (runpp_3ph, 082:RF-9): eso no es una solución.
    if not np.all(np.isfinite(v)):
        return _sin_converger(sis, s, iteraciones)
    inyeccion = v * np.conj(sis.y @ v)
    perdidas = float(np.sum(inyeccion.real))
    fuentes = np.array([inyeccion[sis.indice[i]] + s[sis.indice[i]] for i in sis._fuentes_orig])
    return Solucion(np.abs(v)[sis.indice], np.angle(v)[sis.indice], iteraciones, True, perdidas, fuentes)


def _demanda(sis: SistemaMallado, s_carga: np.ndarray) -> np.ndarray:
    s = np.zeros(sis.n, dtype=complex)
    np.add.at(s, sis.indice, np.asarray(s_carga, dtype=complex))
    return s


def _ramas(sis: SistemaMallado) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    '''Las ramas de las barras unidas, deducidas de la matriz: ``(desde, hasta, z)`` en p.u.'''
    import scipy.sparse as sp

    y = sp.triu(sis.y, k=1).tocoo()
    con_valor = np.abs(y.data) > 0
    return y.row[con_valor], y.col[con_valor], -1.0 / y.data[con_valor]


def anderson(sis: SistemaMallado, s_carga: np.ndarray, *, iteraciones: int = 200, tolerancia: float = 1e-10,
             memoria: int = MEMORIA_ANDERSON) -> Solucion:
    '''El punto fijo del Z-bus acelerado (Anderson, 1965; Walker y Ni, 2011): cada paso combina los anteriores.'''
    s = _demanda(sis, s_carga)
    v = np.where(sis.alimentado, 1.0, 0.0).astype(complex)
    v[sis.fijas] = sis.consigna[sis.fijas]
    if sis._lu is None:
        return _solucion(sis, v, s, 0)
    libres = sis.libres
    empuje = sis.y_ls @ v[sis.fijas]

    def paso(vl: np.ndarray) -> np.ndarray:
        return sis._lu.solve(-np.conj(s[libres] / vl) - empuje)

    x = v[libres]
    historia_x: list[np.ndarray] = []
    historia_r: list[np.ndarray] = []
    for it in range(1, iteraciones + 1):
        g = paso(x)
        if not np.all(np.isfinite(g)):
            return _sin_converger(sis, s, it)
        r = g - x
        cambio = float(np.max(np.abs(r)))
        if cambio < tolerancia:
            v[libres] = g
            return _solucion(sis, v, s, it)
        if cambio > 10.0:           # diverge: demanda que la red no puede llevar
            return _sin_converger(sis, s, it)
        historia_x.append(g)
        historia_r.append(r)
        if len(historia_r) > memoria + 1:
            historia_x.pop(0)
            historia_r.pop(0)
        if len(historia_r) >= 2:
            dr = np.column_stack([historia_r[i + 1] - historia_r[i] for i in range(len(historia_r) - 1)])
            dg = np.column_stack([historia_x[i + 1] - historia_x[i] for i in range(len(historia_x) - 1)])
            gamma = np.linalg.lstsq(dr, r, rcond=None)[0]
            x = g - dg @ gamma
            if not np.all(np.isfinite(x)) or np.min(np.abs(x)) < 1e-3:
                x, historia_x, historia_r = g, [], []     # un salto malo: se olvida y sigue con el punto fijo
        else:
            x = g
    return _sin_converger(sis, s, iteraciones)


def newton(sis: SistemaMallado, s_carga: np.ndarray, *, iteraciones: int = 40, tolerancia: float = 1e-8) -> Solucion:
    '''Newton-Raphson con KLU de lightsim2grid, sobre las barras con fuente.'''
    _rutas_de_dependencias()
    try:
        from lightsim2grid_cpp import NR_KLU
    except ImportError:
        try:
            from lightsim2grid.solver import KLUSolver as NR_KLU
        except ImportError as exc:
            raise MotorNoDisponible(f'lightsim2grid no está instalado: {exc}') from exc
    s = _demanda(sis, s_carga)
    vivas = np.flatnonzero(sis.alimentado)
    pos = {int(b): i for i, b in enumerate(vivas)}
    y = sis.y.tocsc()[vivas][:, vivas].tocsc()
    y.sort_indices()
    ref = np.array([pos[int(b)] for b in sis.fijas if int(b) in pos], dtype=np.int32)
    pq = np.array([i for i in range(len(vivas)) if i not in set(ref.tolist())], dtype=np.int32)
    v0 = np.ones(len(vivas), dtype=complex)
    v0[ref] = sis.consigna[vivas[ref]]
    pesos = np.zeros(len(vivas))
    pesos[ref] = 1.0 / max(len(ref), 1)         # por barra, no por fuente
    solver = NR_KLU()
    ok = solver.compute_pf(y, v0, -s[vivas], ref, pesos, np.array([], dtype=np.int32), pq, iteraciones, tolerancia)
    if not ok or not solver.converged():
        return _sin_converger(sis, s, iteraciones)
    v = np.zeros(sis.n, dtype=complex)
    v[vivas] = np.asarray(solver.get_V())
    return _solucion(sis, v, s, int(solver.get_nb_iter()))


def pgm(sis: SistemaMallado, s_carga: np.ndarray, *, iteraciones: int = 40, tolerancia: float = 1e-8) -> Solucion:
    '''power-grid-model con la red en por unidad: 1 kV y 1 MVA de base, así 1 p.u. de impedancia es 1 Ω.'''
    _rutas_de_dependencias()
    try:
        from power_grid_model import CalculationMethod, ComponentType, DatasetType, LoadGenType, PowerGridModel, initialize_array
        from power_grid_model.errors import PowerGridError
    except ImportError as exc:
        raise MotorNoDisponible(f'power-grid-model no está instalado: {exc}') from exc
    s = _demanda(sis, s_carga)
    desde, hasta, z = _ramas(sis)
    n = sis.n
    nodos = initialize_array(DatasetType.input, ComponentType.node, n)
    nodos['id'], nodos['u_rated'] = np.arange(n), 1000.0
    lineas = initialize_array(DatasetType.input, ComponentType.line, len(z))
    lineas['id'] = n + np.arange(len(z))
    lineas['from_node'], lineas['to_node'] = desde, hasta
    lineas['from_status'], lineas['to_status'] = 1, 1
    lineas['r1'], lineas['x1'] = np.maximum(z.real, 1e-9), z.imag
    lineas['c1'], lineas['tan1'] = 0.0, 0.0
    lineas['i_n'] = 1e6
    fijas = np.asarray(sis.fijas)
    fuentes = initialize_array(DatasetType.input, ComponentType.source, len(fijas))
    fuentes['id'] = n + len(z) + np.arange(len(fijas))
    fuentes['node'], fuentes['status'] = fijas, 1
    fuentes['u_ref'], fuentes['sk'] = sis.consigna[fijas].real, 1e15
    con_carga = np.flatnonzero(np.abs(s) > 0)
    cargas = initialize_array(DatasetType.input, ComponentType.sym_load, len(con_carga))
    cargas['id'] = n + len(z) + len(fijas) + np.arange(len(con_carga))
    cargas['node'], cargas['status'] = con_carga, 1
    cargas['type'] = LoadGenType.const_power
    cargas['p_specified'], cargas['q_specified'] = s[con_carga].real * 1e6, s[con_carga].imag * 1e6
    try:
        modelo = PowerGridModel({ComponentType.node: nodos, ComponentType.line: lineas,
                                 ComponentType.source: fuentes, ComponentType.sym_load: cargas})
        res = modelo.calculate_power_flow(symmetric=True, error_tolerance=tolerancia, max_iterations=iteraciones,
                                          calculation_method=CalculationMethod.newton_raphson)
    except PowerGridError:
        return _sin_converger(sis, s, iteraciones)
    salida = res[ComponentType.node]
    v = salida['u_pu'] * np.exp(1j * salida['u_angle'])
    v = np.where(sis.alimentado, v, 0.0)          # sin fuente, 0; con fuente, un nan es no convergir
    return _solucion(sis, v, s, iteraciones)


def dss(sis: SistemaMallado, s_carga: np.ndarray, *, iteraciones: int = 100, tolerancia: float = 1e-8) -> Solucion:
    '''OpenDSS con la red en por unidad: base de 1,732 kV entre fases y 1 MVA, así 1 p.u. de impedancia son 3 Ω.'''
    _rutas_de_dependencias()
    try:
        from dss import DSS
    except ImportError as exc:
        raise MotorNoDisponible(f'dss-python no está instalado: {exc}') from exc
    kv, z_base = 3 ** 0.5, 3.0
    s = _demanda(sis, s_carga)
    desde, hasta, z = _ramas(sis)
    fijas = [int(b) for b in sis.fijas]
    cab = fijas[0]
    orden = ['clear', f'new circuit.csg bus1=n{cab} basekv={kv} pu={sis.consigna[cab].real} phases=3 '
                      f'angle=0 r1=1e-7 x1=1e-7 r0=1e-7 x0=1e-7']
    for k, b in enumerate(fijas[1:]):
        orden.append(f'new vsource.f{k} bus1=n{b} basekv={kv} pu={sis.consigna[b].real} phases=3 '
                     f'r1=1e-7 x1=1e-7 r0=1e-7 x0=1e-7')
    for k, (a, b, zk) in enumerate(zip(desde.tolist(), hasta.tolist(), z.tolist(), strict=True)):
        r, x = max(zk.real, 1e-9) * z_base, zk.imag * z_base
        orden.append(f'new line.l{k} bus1=n{a} bus2=n{b} phases=3 length=1 units=none r1={r} x1={x} r0={r} x0={x} '
                     'c1=0 c0=0')
    for b in np.flatnonzero(np.abs(s) > 0).tolist():
        orden.append(f'new load.c{b} bus1=n{b} phases=3 kv={kv} model=1 kw={s[b].real * 1000.0} kvar={s[b].imag * 1000.0} '
                     'vminpu=0.05 vmaxpu=2')
    orden += [f'set voltagebases=[{kv}]', 'calcvoltagebases', f'set maxiterations={iteraciones}',
              f'set tolerance={tolerancia}', 'solve mode=snap']
    DSS.Text.Commands(orden)
    circuito = DSS.ActiveCircuit
    if not circuito.Solution.Converged:
        return _sin_converger(sis, s, iteraciones)
    v = np.zeros(sis.n, dtype=complex)
    voltios = np.asarray(circuito.AllBusVolts).reshape(-1, 2)
    for nombre, (re, im) in zip(circuito.AllNodeNames, voltios, strict=True):
        barra, fase = nombre.split('.')
        if fase == '1':
            v[int(barra[1:])] = complex(re, im) / (kv * 1000.0 / 3 ** 0.5)
    return _solucion(sis, v, s, int(circuito.Solution.Iterations))


def _zbus(sis: SistemaMallado, s_carga: np.ndarray) -> Solucion:
    return sis.resolver(s_carga)


MOTORES: dict[str, Callable[[SistemaMallado, np.ndarray], Solucion]] = {
    'zbus': _zbus, 'anderson': anderson, 'newton': newton, 'pgm': pgm, 'dss': dss}


def resolver_con(sis: SistemaMallado, s_carga: np.ndarray, motor: str | None = None) -> tuple[Solucion, str]:
    '''Resuelve con el motor pedido y dice cuál decidió (083:RF-17, RF-18).

    ``auto``: el Z-bus y, si no converge, Newton. Medido en 5 000 barras (2026-11-03): el Z-bus es el más rápido con la red poco
    cargada (3,7 ms frente a 13 ms) y Newton le gana cerca del límite (13 ms frente a 16 ms, 5 iteraciones frente a 31). Anderson no
    mejoró en ningún nivel de carga en que convergió (de 8 a 89 iteraciones frente a 7 a 31): queda disponible, no por defecto.
    El que no esté instalado cede al siguiente: nada se bloquea por un motor.
    '''
    pedido = (motor or os.environ.get(VARIABLE_MOTOR) or 'auto').strip().lower()
    if pedido != 'auto' and pedido not in MOTORES:
        raise ValueError(f'motor de flujo desconocido: {pedido}; use auto o {", ".join(MOTORES)}')
    orden = ('zbus', 'newton') if pedido == 'auto' else (pedido,)
    sol = None
    decidio = 'zbus'
    for nombre in orden:
        try:
            sol, decidio = MOTORES[nombre](sis, s_carga), nombre
        except MotorNoDisponible:
            continue
        if sol.convergio:
            return sol, nombre
    return (sol, decidio) if sol is not None else (sis.resolver(s_carga), 'zbus')
