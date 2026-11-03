"""El oráculo antes de calibrar: los factores de arranque, sin gastar flujos de DIgSILENT (spec 083).

La búsqueda es la misma de la calibración (``cuadrar_conjunto``); solo cambia quién calcula cada intento. DIgSILENT arranca de lo
hallado y sigue siendo la referencia: esto no da ninguna calibración por buena.
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .ajuste_cabecera import MedidaConjunta, Objetivo, Reparto, cuadrar_conjunto
from .digital_twin.motores_flujo import resolver_con
from .optimizacion_oraculo import S_BASE, Oraculo

#: Intentos del oráculo: cuesta poco, pero una red que no cuadra no debe retenerlo.
MAX_EVALUACIONES = 12


@dataclass
class Arranque:
    """Lo hallado por el oráculo: ``repartos`` es ``None`` si no hay arranque que proponer (083:RF-4)."""

    repartos: dict[str, Reparto] | None = None
    cuadrado: bool = False
    modelo: str = 'fisica'
    motor: str = ''
    evaluaciones: int = 0
    segundos: float = 0.0
    v_min: float | None = None
    motivo: str = ''
    factores: dict[str, float] = field(default_factory=dict)
    sin_cuadre: dict[str, dict[str, float]] = field(default_factory=dict)   # 083:RF-28
    flujo: Any = None                   # 083:RF-20: para las muestras del reparto probabilístico

    def informe(self) -> dict[str, Any]:
        return {'sin_cuadre': self.sin_cuadre, 'modelo': self.modelo, 'motor': self.motor, 'evaluaciones': self.evaluaciones, 'segundos': round(self.segundos, 2),
                'cuadrado': self.cuadrado, 'v_min': self.v_min, 'motivo': self.motivo, 'factores': self.factores}


class FlujoOraculo:
    """El flujo de la calibración sin DIgSILENT, para cuadrar y leer repartos: mismas entradas y misma medida (083:RF-2, RF-20).

    ``nodo_de_sed``: por alimentador, el nodo del grafo de cada SED. ``ramas_de``: las ramas de cada uno, cuyas pérdidas le tocan.
    ``trafos_de``: por SED, sus transformadores en el grafo. Cada reparto reemplaza en su nodo lo que el grafo traía de esa SED.
    """

    def __init__(self, grafo: Mapping[str, Any], nodo_de_sed: Mapping[str, Mapping[str, str]],
                 ramas_de: Mapping[str, Iterable[str]], *, pinn: Any = None, motor: str | None = None,
                 trafos_de: Mapping[str, Iterable[str]] | None = None) -> None:
        self.ora = Oraculo(grafo, [], pinn=pinn)
        self.pinn, self.pedido = pinn, motor
        self.m, self.sis, self.ramas = self.ora._sistema([], [])
        m = self.m
        pos = {n: i for i, n in enumerate(m.ids)}
        self.base = np.array([complex(float(self.ora._nodos[n].get('p_mw') or 0.0), float(self.ora._nodos[n].get('q_mvar') or 0.0))
                              for n in m.ids])
        self.indice = {k: {sed: pos[n] for sed, n in nodos.items() if n in pos} for k, nodos in nodo_de_sed.items()}
        for nodos in self.indice.values():
            for i in nodos.values():
                self.base[i] = 0.0
        pos_rama = {r: e for e, r in reversed(list(enumerate(m.ramas)))}     # la primera vez de cada una: llegan en los dos sentidos
        self.ramas_de = {k: np.array([pos_rama[x] for x in v if x in pos_rama], dtype=np.int64) for k, v in ramas_de.items()}
        self.trafos_de = {sed: [pos_rama[x] for x in v if x in pos_rama] for sed, v in (trafos_de or {}).items()}
        self.modelo, self.motor, self.evaluaciones = 'fisica', '', 0
        self.v_min: float | None = None
        self._v = self._carga = None

    def __call__(self, reps: Mapping[str, Reparto]) -> MedidaConjunta:
        m = self.m
        s = self.base.copy()
        for k, r in reps.items():
            indice = self.indice.get(k, {})
            for sed, d in r.demandas.items():
                if sed in indice:
                    s[indice[sed]] += complex(d.kw, d.kvar) / 1000.0
        sol, self.motor = resolver_con(self.sis, s / S_BASE, self.pedido)    # 083:RF-17
        self.evaluaciones += 1
        if not sol.convergio:
            return MedidaConjunta(False, motivo='el flujo del oráculo no converge')
        v = sol.v.copy()
        if self.pinn is not None:
            v, self.modelo = self.ora._con_pinn(m, s / S_BASE, self.ramas, v)
        energ = m.alimentado & ~m.fuente
        self.v_min = float(v[energ].min()) if energ.any() else None
        self._v = v
        vc = sol.v * np.exp(1j * sol.theta)
        a, b = m.aristas
        corriente = (vc[a] - vc[b]) / m.z
        self._carga = np.divide(100.0 * np.abs(corriente), m.inom, out=np.zeros(len(m.z)), where=m.inom > 0)
        perdida = np.abs(corriente) ** 2 * m.z * S_BASE * 1000.0
        kw, kvar = {}, {}
        for k, r in reps.items():
            propia = perdida[self.ramas_de[k]].sum() if k in self.ramas_de else 0j
            kw[k] = sum(d.kw for d in r.demandas.values()) + float(propia.real)
            kvar[k] = sum(d.kvar for d in r.demandas.values()) + float(propia.imag)
        return MedidaConjunta(True, kw=kw, kvar=kvar)

    def lectura(self, feeder: str, rep: Reparto, banda: Any = None) -> dict[str, Any]:
        """Lo mismo que se lee de un flujo de una muestra (041:RF-6): la carga del transformador de cada escalada y la banda."""
        carga = {}
        for sed in rep.base:
            ramas = self.trafos_de.get(sed) or []
            carga[sed] = max((float(self._carga[e]) for e in ramas), default=None)
        fuera = None
        if banda and self.indice.get(feeder):
            nodos = np.array(sorted(self.indice[feeder].values()), dtype=np.int64)
            us = self._v[nodos]
            us = us[us > 0]
            fuera = bool(((us < banda[0]) | (us > banda[1])).any()) if len(us) else None
        return {'carga': carga, 'fuera_de_banda': fuera}


def arranque_con_oraculo(grafo: Mapping[str, Any], nodo_de_sed: Mapping[str, Mapping[str, str]],
                         ramas_de: Mapping[str, Iterable[str]], repartos: Mapping[str, Reparto],
                         objetivos: Mapping[str, Objetivo], *, quietas: Iterable[str] = (), tolerancia: float = 0.01,
                         pinn: Any = None, max_evaluaciones: int = MAX_EVALUACIONES, motor: str | None = None,
                         trafos_de: Mapping[str, Iterable[str]] | None = None) -> Arranque:
    """Los factores que cuadran cada alimentador en el oráculo (083:RF-1, RF-2).

    ``nodo_de_sed``: por alimentador, el nodo del grafo de cada SED. ``ramas_de``: las ramas de cada uno, cuyas pérdidas le tocan.
    Cada reparto reemplaza en su nodo lo que el grafo traía de esa SED; lo demás queda como estaba.
    """
    inicio = time.perf_counter()
    salida = Arranque()
    flujo = FlujoOraculo(grafo, nodo_de_sed, ramas_de, pinn=pinn, motor=motor, trafos_de=trafos_de)
    salida.flujo = flujo
    res = cuadrar_conjunto(repartos, objetivos, flujo, quietas=quietas, tolerancia=tolerancia,
                           max_flujos=max_evaluaciones)
    salida.segundos = time.perf_counter() - inicio
    salida.cuadrado = res.cuadrado
    salida.modelo, salida.motor, salida.evaluaciones, salida.v_min = flujo.modelo, flujo.motor, flujo.evaluaciones, flujo.v_min
    salida.motivo = res.motivo or ''
    if res.repartos:
        salida.repartos = dict(res.repartos)
        salida.factores = {k: round(r.a, 6) for k, r in res.repartos.items()}
        if res.medida is not None and res.medida.converge:
            # 083:RF-28: el que sigue por encima con sus escaladas casi en cero no puede cuadrar: sus fijas y pérdidas ya pasan.
            for k, r in res.repartos.items():
                kw, objetivo = res.medida.kw.get(k), objetivos[k].kw
                if kw is not None and objetivo and kw > objetivo * (1 + tolerancia) and r.a < 0.05 * max(repartos[k].a, 1e-9):
                    salida.sin_cuadre[k] = {'oraculo_kw': round(kw, 1), 'medida_kw': round(objetivo, 1),
                                            'fijas_kw': round(sum(p for p, _q in r.fijas.values()), 1)}
    return salida
