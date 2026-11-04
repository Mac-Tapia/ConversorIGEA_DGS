"""Oráculo PINN/GNN del estado eléctrico (spec 024, T11).

Aprende de los episodios del búfer la relación entre topología, inyecciones y tensiones
(RF-13 a RF-19), con una red de grafos que pasa mensajes por las ramas: los mismos pesos
sirven para cualquier red, de 10 o de 2 500 nodos (RF-44). Es una PINN porque su pérdida
suma al error frente a DIgSILENT el residuo del balance de potencia de cada nodo calculado
con las impedancias reales de la red (contrato físico de la spec, sección D).

La incertidumbre sale de un conjunto de modelos con semillas distintas (RF-15); una red
fuera de lo aprendido no se extrapola y pide el cálculo a DIgSILENT (RF-19). Cada modelo
entrenado queda registrado con la consulta y los episodios que usó (RF-13) y se promueve
solo si supera las puertas sin empeorar los casos dorados (RF-16, RF-42); el anterior se
conserva para volver a él. DIgSILENT sigue siendo la referencia (principio 1).

PyTorch es el extra opcional ``ml``: sin él, ``ModeloRadial`` (barrido físico) cumple el
mismo contrato (RF-38) y el resto del conversor funciona.
"""
from __future__ import annotations

from ..runtime_paths import staging_publicacion

import hashlib
import json
import math
import os
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from ..evaluacion_modelos import PoliticaDeError, alcance_de, evaluar_candidato, particionar_registros
from .buffer import BuferEpisodios, Consulta
from .contratos_fisicos import VERSION_GRAFO, Z_ACOPLADOR_PU, validar_alcance_fisico
from .episode import Clase, Episodio
from .escenarios import Escenario, familia, particion, reparto_del_sistema

#: Potencia base del sistema por unidad (MVA).
S_BASE = 10.0
#: Clases que enseñan tensiones (RF-14: las violaciones y rechazos, no como objetivo).
CLASES_OBJETIVO = (Clase.ACCEPTED.value, Clase.COUNTERFACTUAL.value)
#: Miembros del conjunto: la desviación entre ellos es la incertidumbre (RF-15).
MIEMBROS = 3


class Modelo(Protocol):
    """Contrato de un oráculo: el de la PINN y el de cualquier otro modelo (RF-38)."""

    nombre: str

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]: ...


# ------------------------------------------------------------------ grafo → tensores
@dataclass
class Muestra:
    ids: list[str]
    x: np.ndarray            # nodos × 5: log10 kV, P pu, Q pu, fuente, consigna de la fuente
    aristas: np.ndarray      # 2 × E (ambos sentidos)
    z: np.ndarray            # E: impedancia compleja en pu
    inom: np.ndarray         # E: corriente nominal en pu de la base del nodo de salida
    ramas: list[str]
    s_carga: np.ndarray      # nodos: carga compleja en pu (positiva consume)
    fuente: np.ndarray       # nodos: bool
    v: np.ndarray | None = None       # objetivo: magnitud en pu
    mascara: np.ndarray | None = None  # nodos con tensión medida
    familia: str = ''
    alimentado: np.ndarray | None = None  # nodos a los que llega una fuente
    base: np.ndarray | None = None        # V y θ de la física (``_con_base``)
    base_clave: tuple | None = None       # (física, exponente) con que se calculó ``base``
    sistema: Any = None                   # ``flujo.SistemaMallado`` factorizado, una vez
    ru: np.ndarray | None = None          # E: relación de cada arista en su origen (1 sin transformador)
    rw: np.ndarray | None = None          # E: relación de cada arista en su destino
    s_shunt: np.ndarray | None = None     # nodos: lo que consumen los bancos a 1 p.u.
    version: int | None = None            # versión del grafo de que sale
    bloqueos: tuple[str, ...] = ()        # por qué su física no vale (045:RF-4)
    etiquetas_sin_fuente: int = 0         # tensiones medidas en barras que el grafo deja sin fuente


def _factor_toma(toma: Mapping[str, Any] | None) -> tuple[float, int]:
    """Lo que multiplica la tensión nominal la toma, y en qué lado (0 alta, 1 baja)."""
    if not toma or not toma.get('paso_pct'):
        return 1.0, 0
    pasos = float(toma.get('posicion') or 0.0) - float(toma.get('neutra') or 0.0)
    return 1.0 + pasos * float(toma['paso_pct']) / 100.0, int(toma.get('lado') or 0)


def _relaciones(r: Mapping[str, Any], kv_a: float, kv_b: float) -> tuple[float, float, float]:
    """Relación en cada extremo de la rama e impedancia base de sus ohmios (045:RF-4).

    Los ohmios de un transformador están en la tensión nominal de su lado de alta, que no tiene
    por qué ser la de la barra. Un grafo hecho desde una muestra trae las relaciones ya calculadas.
    """
    if 'ru' in r:
        return float(r['ru']), float(r['rw']), kv_a ** 2 / S_BASE
    ua, ub = r.get('u_desde_kv'), r.get('u_hasta_kv')
    if not ua or not ub:
        return 1.0, 1.0, kv_a ** 2 / S_BASE
    t, lado = _factor_toma(r.get('toma'))
    return float(ua) / kv_a * (t if lado == 0 else 1.0), float(ub) / kv_b * (t if lado == 1 else 1.0), float(ua) ** 2 / S_BASE


def escalar_nodo(d: Mapping[str, Any], factor: float) -> dict[str, Any]:
    """El nodo con la demanda por ``factor``: la carga escala; la central y el banco, no.

    Con la potencia neta del grafo, escalar la demanda escalaba también lo que inyectan.
    """
    if 'carga_p_mw' not in d:
        return {**d, 'p_mw': (d.get('p_mw') or 0.0) * factor, 'q_mvar': (d.get('q_mvar') or 0.0) * factor}
    p, q = (d.get('carga_p_mw') or 0.0) * factor, (d.get('carga_q_mvar') or 0.0) * factor
    return {**d, 'carga_p_mw': p, 'carga_q_mvar': q, 'p_mw': p - (d.get('gen_p_mw') or 0.0),
            'q_mvar': q - (d.get('gen_q_mvar') or 0.0) - (d.get('banco_q_mvar') or 0.0)}


def muestra(grafo: Mapping[str, Any], tensiones: Mapping[str, float] | None = None,
            familia_: str = '') -> Muestra:
    """Pasa el grafo de ``tools/escenarios_pf.py`` a arrays por unidad."""
    nodos = grafo.get('nodos') or {}
    ids = sorted(nodos)
    pos = {n: i for i, n in enumerate(ids)}
    kv = np.array([float(nodos[n].get('kv') or 1.0) for n in ids])
    p = np.array([float(nodos[n].get('p_mw') or 0.0) for n in ids]) / S_BASE
    q = np.array([float(nodos[n].get('q_mvar') or 0.0) for n in ids]) / S_BASE
    # ``q_mvar`` es la neta, también en la entrada de la red; el banco en la física consume por |V|².
    banco = np.array([float(nodos[n].get('banco_q_mvar') or 0.0) for n in ids]) / S_BASE
    fuente = np.array([bool(nodos[n].get('fuente')) for n in ids])
    # Consigna de la fuente: la del grafo o, en episodios anteriores, la tensión medida en ella.
    consigna = np.array([float(nodos[n].get('v_pu') or (tensiones or {}).get(n) or 1.0) if fuente[i] else 0.0
                         for i, n in enumerate(ids)])
    x = np.stack([np.log10(np.maximum(kv, 1e-3)), p, q, fuente.astype(float), consigna], axis=1)
    origen, destino, z, inom, ramas, ru, rw = [], [], [], [], [], [], []
    for r in grafo.get('ramas') or []:
        a, b = pos.get(r.get('desde')), pos.get(r.get('hasta'))
        if a is None or b is None or not r.get('cerrada', True):
            continue
        en_a, en_b, z_base = _relaciones(r, kv[a], kv[b])
        zz = complex(float(r.get('r_ohm') or 0.0), float(r.get('x_ohm') or 0.0)) / z_base
        if abs(zz) < Z_ACOPLADOR_PU:
            zz = complex(Z_ACOPLADOR_PU, Z_ACOPLADOR_PU)       # acoplador cerrado
        i_base = S_BASE / (math.sqrt(3) * kv[a])
        for u, w, r_u, r_w in ((a, b, en_a, en_b), (b, a, en_b, en_a)):
            origen.append(u)
            destino.append(w)
            ru.append(r_u)
            rw.append(r_w)
            z.append(zz)
            inom.append(float(r.get('inom_ka') or 0.0) / i_base if i_base else 0.0)
            ramas.append(str(r.get('id')))
    # Una isla sin fuente no puede cumplir el balance: la física solo se exige donde llega
    # una fuente (IN111–TA225 tenía 392 barras sin tensión en un caso mal activado).
    alimentado = fuente.copy()
    vecinos: dict[int, list[int]] = {}
    for u, w in zip(origen, destino, strict=True):
        vecinos.setdefault(u, []).append(w)
    pila = list(np.flatnonzero(fuente))
    while pila:
        u = int(pila.pop())
        for w in vecinos.get(u, []):
            if not alimentado[w]:
                alimentado[w] = True
                pila.append(w)
    v = mascara = None
    sin_fuente = 0
    if tensiones is not None:
        v = np.array([float(tensiones.get(n, 0.0)) for n in ids])
        # 045:RF-5: una barra sin fuente no enseña «0 p.u.» ni una tensión que el grafo no explica.
        leida = np.array([n in tensiones and float(tensiones[n]) > 0 for n in ids])
        mascara = leida & alimentado
        sin_fuente = int(np.count_nonzero(leida & ~alimentado))
    return Muestra(ids, x, np.array([origen, destino], dtype=np.int64).reshape(2, -1),
                   np.array(z, dtype=complex), np.array(inom), ramas, p + 1j * (q + banco), fuente, v, mascara,
                   familia_, alimentado, ru=np.array(ru, dtype=float), rw=np.array(rw, dtype=float),
                   s_shunt=-1j * banco, version=grafo.get('version'), bloqueos=validar_alcance_fisico(grafo),
                   etiquetas_sin_fuente=sin_fuente)


def por_que_no_ensena(e: Episodio) -> str | None:
    """Por qué un episodio no entra en el entrenamiento; ``None`` si entra (045:RF-2, RF-4)."""
    grafo = (e.topologia or {}).get('grafo')
    if not grafo or not (e.flujo.get('tensiones') or {}).get('valores'):
        return 'sin grafo o sin tensiones'
    if grafo.get('version') != VERSION_GRAFO:
        return f"grafo de la versión {grafo.get('version')}, anterior a la {VERSION_GRAFO}"
    bloqueos = validar_alcance_fisico(grafo)
    return f'física no representada: {bloqueos[0]}' if bloqueos else None


def muestra_de_episodio(e: Episodio) -> Muestra | None:
    """La muestra de un episodio que puede enseñar; ``None`` si no (``por_que_no_ensena``)."""
    if por_que_no_ensena(e) is not None:
        return None
    return muestra(e.topologia['grafo'], e.flujo['tensiones']['valores'],
                   familia({'nativo': e.nativo, 'accion': e.accion, 'topologia': e.topologia}))


# ------------------------------------------------------------------ física
def barras_electricas(m: Muestra) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Barra eléctrica de cada nodo (los unidos por acopladores son una), las ramas que no
    son acopladores y qué barras eléctricas deben cumplir el balance.

    Un acoplador es una rama de 10⁻⁶ p.u.: en el balance por nodo, una diferencia de tensión
    mínima entre sus dos barras daba corrientes enormes. La PINN de IN111–TA225 (1221
    acopladores) empezaba con una pérdida de 1,7·10⁷ y acababa peor que la física sola
    (0,0072 p.u. frente a 0,0032, 2026-10-24).
    """
    from .flujo import Z_ACOPLADOR

    sis = sistema_de(m)
    exigir = np.zeros(sis.n, dtype=bool)
    exigir[sis.libres] = True
    return sis.indice, np.abs(m.z) >= Z_ACOPLADOR, exigir, sis.n


def residuo(m: Muestra, v: np.ndarray, theta: np.ndarray, exponente: float = 0.0) -> np.ndarray:
    """Desbalance de potencia (pu) de la barra eléctrica de cada nodo; 0 en las fuentes.

    Las cargas consumen S0·|V|^exponente: 0 potencia, 1 corriente, 2 impedancia constante.
    """
    grupo, real, exigir, n = barras_electricas(m)
    vc = v * np.exp(1j * theta)
    a, b = m.aristas[:, real]
    ru, rw = m.ru[real], m.rw[real]
    corriente = np.zeros(len(m.ids), dtype=complex)
    np.add.at(corriente, a, (vc[a] / ru - vc[b] / rw) / (m.z[real] * ru))
    # sale + carga + banco = 0
    s_nodo = vc * np.conj(corriente) + m.s_carga * np.abs(v) ** exponente + m.s_shunt * np.abs(v) ** 2
    s_barra = np.zeros(n, dtype=complex)
    np.add.at(s_barra, grupo, s_nodo)
    return np.where(exigir, np.abs(s_barra), 0.0)[grupo]


def error_de_fronteras(m: Muestra, v: np.ndarray, theta: np.ndarray) -> float:
    """Error cuadrático medio (p.u.²) de lo que no se predice: es dato (045:RF-5, RF-6).

    Magnitud y ángulo de referencia en cada fuente, una barra eléctrica a una sola tensión y las
    islas sin fuente a cero.
    """
    grupo, _real, _exigir, n = barras_electricas(m)
    errores = [v[m.fuente] - m.x[m.fuente, 4], theta[m.fuente], v[~m.alimentado], theta[~m.alimentado]]
    cuenta = np.bincount(grupo, minlength=n)
    media = np.bincount(grupo, weights=v, minlength=n) / np.maximum(cuenta, 1)
    errores.append((v - media[grupo])[(cuenta[grupo] > 1) & m.alimentado])
    todos = np.concatenate(errores)
    return float(np.mean(todos ** 2)) if todos.size else 0.0


def perdidas_fisicas(prediccion: Mapping[str, Any], m: Muestra, *, pesos: Mapping[str, float],
                     exponente: float = 0.0) -> dict[str, Any]:
    """Datos, residuo físico y fronteras por separado (045:RF-6), en p.u. al cuadrado.

    Sin barras medidas, ``datos`` es ``None`` y no 0: una ausencia no aparenta un ajuste perfecto.
    """
    faltan = [k for k in ('datos', 'fisica', 'fronteras') if k not in pesos]
    if faltan:
        raise ValueError(f'faltan los pesos de {", ".join(faltan)}')
    v, theta = np.asarray(prediccion['v'], dtype=float), np.asarray(prediccion['theta'], dtype=float)
    datos = None
    if m.mascara is not None and m.mascara.any():
        datos = float(np.mean((v - m.v)[m.mascara] ** 2))
    grupo, _real, exigir, _n = barras_electricas(m)
    balance = residuo(m, v, theta, exponente)
    # ``residuo`` da el desbalance de la barra eléctrica en cada nodo suyo: una vez por barra.
    primero = np.unique(grupo, return_index=True)[1]
    fisica = float(np.mean(balance[primero][exigir] ** 2)) if exigir.any() else 0.0
    fronteras = error_de_fronteras(m, v, theta)
    total = float(pesos['fisica']) * fisica + float(pesos['fronteras']) * fronteras
    if datos is not None:
        total += float(pesos['datos']) * datos
    return {'datos': datos, 'fisica': fisica, 'fronteras': fronteras, 'total': total,
            'pesos': {k: float(pesos[k]) for k in ('datos', 'fisica', 'fronteras')},
            'unidades': {'datos': 'p.u.²', 'fisica': 'p.u.²', 'fronteras': 'p.u.²'}}


def imponer_fronteras(m: Muestra, v: np.ndarray, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """La predicción con lo que es dato: la consigna y el ángulo 0 de la referencia de cada isla
    energizada, que los acopladores comparten, y las barras sin fuente a 0 (045:RF-5).

    La física fija el ángulo de cada isla en sus fuentes; la red de la 024 lo dejaba flotar.
    """
    sis = sistema_de(m)
    v, theta = np.array(v, dtype=float), np.array(theta, dtype=float)
    fijas = sis.fuente[sis.indice]
    v[fijas], theta[fijas] = sis.consigna[sis.indice][fijas], 0.0
    v[~m.alimentado], theta[~m.alimentado] = 0.0, 0.0
    return v, theta


@dataclass
class ModeloRadial:
    """Barrido hacia atrás y adelante sobre el árbol de cada fuente (RF-38).

    Física pura, sin aprendizaje: sirve de oráculo de respaldo sin PyTorch y para generar
    datos de prueba. Vale para redes radiales (las de distribución en operación).
    """

    nombre: str = 'radial'
    iteraciones: int = 50
    exponente: float = 0.0
    """Modelo de carga: S0·|V|^exponente (el entrenamiento elige el que reproduce a DIgSILENT)."""

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]:
        m = muestra(grafo)
        n = len(m.ids)
        vecinos: list[list[tuple[int, int]]] = [[] for _ in range(n)]
        for k in range(m.aristas.shape[1]):
            vecinos[m.aristas[0, k]].append((int(m.aristas[1, k]), k))
        padre, arista, orden = [-1] * n, [-1] * n, []
        visto = [False] * n
        for s in np.flatnonzero(m.fuente):
            pila = [int(s)]
            visto[s] = True
            while pila:
                u = pila.pop()
                orden.append(u)
                for w, k in vecinos[u]:
                    if not visto[w]:
                        visto[w], padre[w], arista[w] = True, u, k
                        pila.append(w)
        vc = np.where(m.fuente, m.x[:, 4], 1.0).astype(complex)   # las fuentes, en su consigna
        for _ in range(self.iteraciones):
            i_nodo = np.conj((m.s_carga * np.abs(vc) ** self.exponente + m.s_shunt * np.abs(vc) ** 2) / vc)
            i_rama = i_nodo.copy()
            for u in reversed(orden):
                if padre[u] >= 0:
                    k = arista[u]
                    i_rama[padre[u]] += i_rama[u] * m.rw[k] / m.ru[k]
            nuevo = vc.copy()
            for u in orden:
                if padre[u] >= 0:
                    k = arista[u]
                    nuevo[u] = m.rw[k] * (nuevo[padre[u]] / m.ru[k] - m.z[k] * m.rw[k] * i_rama[u])
            if np.max(np.abs(nuevo - vc)) < 1e-9:
                vc = nuevo
                break
            vc = nuevo
        v = np.where(visto, np.abs(vc), 0.0)
        return {'ids': m.ids, 'v': v, 'theta': np.where(visto, np.angle(vc), 0.0),
                'incertidumbre': np.zeros(n), 'residuo': residuo(m, v, np.angle(vc), self.exponente),
                'fuera_de_dominio': bool(m.bloqueos), 'motivos': list(m.bloqueos), 'modelo': self.nombre}


def sistema_de(m: Muestra):
    """La red de la muestra factorizada para el flujo mallado, construida una sola vez."""
    if m.sistema is None:
        from .flujo import SistemaMallado

        m.sistema = SistemaMallado(m.aristas, m.z, m.fuente, m.x[:, 4], m.alimentado, m.ru, m.rw, m.s_shunt)
    return m.sistema


@dataclass
class ModeloMallado:
    """Flujo de carga por matriz de admitancias, con los lazos de la red (RF-38, RF-64).

    Es la física de la PINN y el evaluador de los algoritmos evolutivos. A diferencia del
    barrido radial, respeta las ramas que cierran un lazo: IN111–TA225 tiene 3 y el barrido
    se apartaba 0,019 p.u. de DIgSILENT frente a 0,0032 de este (2026-10-24).
    """

    nombre: str = 'mallado'
    exponente: float = 0.0

    def predecir_muestra(self, m: Muestra) -> dict[str, Any]:
        sol = sistema_de(m).resolver(m.s_carga, exponente=self.exponente)
        v, th = (sol.v, sol.theta) if sol.convergio else (np.zeros(len(m.ids)), np.zeros(len(m.ids)))
        return {'ids': m.ids, 'v': v, 'theta': th, 'incertidumbre': np.zeros(len(m.ids)),
                'residuo': residuo(m, v, th, self.exponente),
                # 045:RF-4: converger sobre una red que la física no representa no es un resultado.
                'fuera_de_dominio': not sol.convergio or bool(m.bloqueos),
                'motivos': ([] if sol.convergio else ['el flujo físico no converge']) + list(m.bloqueos),
                'convergio': sol.convergio, 'perdidas_mw': sol.perdidas_pu * S_BASE, 'modelo': self.nombre}

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]:
        return self.predecir_muestra(muestra(grafo))


#: Física de la base de la PINN, por nombre (se guarda con cada modelo entrenado).
FISICAS = {'mallado': ModeloMallado, 'radial': ModeloRadial}


# ------------------------------------------------------------------ red de grafos
def _torch():
    try:
        import torch
    except ImportError as exc:     # el extra «ml» no está instalado
        raise ImportError('PyTorch no está instalado (extra «ml»): el oráculo PINN no está '
                          'disponible; ModeloRadial cumple el mismo contrato') from exc
    return torch


class SinGPU(RuntimeError):
    """No hay GPU CUDA: el gemelo no entrena ni predice en la CPU."""


#: cuBLAS solo es determinista con este espacio de trabajo, fijado antes de usar la GPU (027:RF-9).
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')


def dispositivo():
    """La GPU CUDA, siempre (usuario, 2026-10-22: «sí o sí debe conectar a GPU para no usar
    el CPU»). Sin ella, un error que lo dice; nunca la CPU en silencio."""
    torch = _torch()
    if not torch.cuda.is_available():
        raise SinGPU('No hay GPU CUDA para el gemelo digital: instale PyTorch con CUDA '
                     '(pip install torch --index-url https://download.pytorch.org/whl/cu126) '
                     'y compruebe el controlador de la tarjeta.')
    return torch.device('cuda')


def _parametros(cfg: Entrenamiento) -> int:
    """Parámetros de un miembro de ``_red`` sin construirla (sin GPU), para la auditoría
    (027:RF-33): 309 506 con 64 ocultas y 8 pasos, lo mismo que cuenta PyTorch."""
    h, k = cfg.ocultas, cfg.pasos
    if cfg.arquitectura == 'powerflownet':
        return h * h + 19 * h + (k - 1) * (4 * h * h + h) + 8 * h + 2
    entrada = (7 * h + h) + (h * h + h)
    por_paso = ((2 * h + 3) * h + h) + (h * h + h) + (6 * h * h + 6 * h)   # mensaje y GRUCell
    salida = (h * h + h) + (2 * h + 2)
    return entrada + k * por_paso + salida


#: Nombre de la arquitectura propia antes de la spec 058, en los manifiestos ya guardados.
ARQUITECTURA_ANTERIOR = {'igea': 'csg'}  # legado-058


def _red(ocultas: int = 64, pasos: int = 8, arquitectura: str = 'csg'):
    """GNN: codifica nodos, pasa mensajes ``pasos`` veces por las ramas y da (ΔV, θ)."""
    if arquitectura == 'powerflownet':
        from .adaptador_pyg import crear_red_powerflownet
        return crear_red_powerflownet(ocultas, pasos)
    if ARQUITECTURA_ANTERIOR.get(arquitectura, arquitectura) != 'csg':
        raise ValueError(f'arquitectura de gemelo no soportada: {arquitectura}')
    torch = _torch()
    nn = torch.nn

    class Red(nn.Module):
        def __init__(self):
            super().__init__()
            self.entrada = nn.Sequential(nn.Linear(7, ocultas), nn.SiLU(), nn.Linear(ocultas, ocultas))
            self.mensaje = nn.ModuleList(nn.Sequential(nn.Linear(2 * ocultas + 3, ocultas), nn.SiLU(),
                                                       nn.Linear(ocultas, ocultas)) for _ in range(pasos))
            self.actualiza = nn.ModuleList(nn.GRUCell(ocultas, ocultas) for _ in range(pasos))
            self.salida = nn.Sequential(nn.Linear(ocultas, ocultas), nn.SiLU(), nn.Linear(ocultas, 2))

        def forward(self, x, aristas, e):
            h = self.entrada(x)
            a, b = aristas
            for msg, upd in zip(self.mensaje, self.actualiza, strict=True):
                m = msg(torch.cat([h[a], h[b], e], dim=1))
                agg = torch.zeros_like(h).index_add_(0, b, m)
                h = upd(agg, h)
            out = self.salida(h)
            # Híbrido: la tensión del barrido físico (columnas 5 y 6) más la corrección que la
            # red aprende de DIgSILENT. Solo con mensajes, la consigna de la fuente no llegaba a
            # los nodos a cientos de tramos (IN111–TA225: error de 0,035 p.u., 2026-10-22).
            v = x[:, 5] + 0.1 * torch.tanh(out[:, 0])
            th = x[:, 6] + 0.2 * torch.tanh(out[:, 1])
            # En la fuente tensión y ángulo son dato, no predicción (045:RF-5): el ángulo flotaba.
            es_fuente = x[:, 3] > 0.5
            return torch.where(es_fuente, x[:, 4], v), torch.where(es_fuente, x[:, 6], th)

    return Red()


def _con_base(m: Muestra, exponente: float = 0.0, fisica: str = 'mallado') -> np.ndarray:
    """Las entradas del nodo con la tensión y el ángulo de la física, calculados una vez."""
    if m.base is None or m.base_clave != (fisica, exponente):
        modelo = FISICAS[fisica](exponente=exponente)
        p = modelo.predecir_muestra(m) if fisica == 'mallado' else modelo.predecir(_grafo_de_muestra(m))
        m.base = np.stack([p['v'], p['theta']], axis=1)
        m.base_clave = (fisica, exponente)
    return np.concatenate([m.x, m.base], axis=1)


def _tensores(m: Muestra, disp, exponente: float = 0.0, fisica: str = 'mallado'):
    torch = _torch()
    e = np.stack([np.log10(np.abs(m.z) + 1e-9), np.angle(m.z), np.log10(m.inom + 1e-6)], axis=1)
    return (torch.tensor(_con_base(m, exponente, fisica), dtype=torch.float32, device=disp),
            torch.tensor(m.aristas, dtype=torch.long, device=disp),
            torch.tensor(e, dtype=torch.float32, device=disp))


def _fisica(m: Muestra, disp, exponente: float = 0.0, dtype=None) -> dict:
    """Tensores fijos de la pérdida física de una muestra, creados una sola vez.

    Crearlos en cada paso agotó la memoria con IN111–TA225 (2470 nodos, 2026-10-22: «CUDA
    error: Memory allocation failure» con 1,3 GB de RAM libre) y tumbó la web.
    """
    torch = _torch()
    dtype = dtype or torch.float32
    grupo, real, exigir, n = barras_electricas(m)
    z = m.z[real]
    return {'a': torch.tensor(m.aristas[0][real], device=disp), 'b': torch.tensor(m.aristas[1][real], device=disp),
            'zr': torch.tensor(z.real, dtype=dtype, device=disp),
            'zi': torch.tensor(z.imag, dtype=dtype, device=disp),
            'ru': torch.tensor(m.ru[real], dtype=dtype, device=disp),
            'rw': torch.tensor(m.rw[real], dtype=dtype, device=disp),
            'sp': torch.tensor(m.s_carga.real, dtype=dtype, device=disp),
            'sq': torch.tensor(m.s_carga.imag, dtype=dtype, device=disp),
            'bq': torch.tensor(m.s_shunt.imag, dtype=dtype, device=disp),
            'grupo': torch.tensor(grupo, dtype=torch.long, device=disp), 'n': n,
            'exigir': torch.tensor(exigir, device=disp), 'exponente': exponente,
            # 045:RF-6: lo que es dato, para medir el error de fronteras aparte.
            'fuente': torch.tensor(m.fuente, device=disp),
            'consigna': torch.tensor(m.x[:, 4], dtype=dtype, device=disp),
            'alimentado': torch.tensor(m.alimentado, device=disp),
            'cuenta': torch.tensor(np.bincount(grupo, minlength=n), dtype=dtype, device=disp)}


def _residuo_torch(f: dict, v, theta):
    """El balance de cada barra eléctrica (``barras_electricas``), al cuadrado."""
    torch = _torch()
    a, b, zr, zi = f['a'], f['b'], f['zr'], f['zi']
    vr, vi = v * torch.cos(theta), v * torch.sin(theta)
    ru, rw = f['ru'], f['rw']
    dr, di = vr[a] / ru - vr[b] / rw, vi[a] / ru - vi[b] / rw
    den = (zr * zr + zi * zi) * ru
    ir, ii = (dr * zr + di * zi) / den, (di * zr - dr * zi) / den
    i_r = torch.zeros_like(v).index_add_(0, a, ir)
    i_i = torch.zeros_like(v).index_add_(0, a, ii)
    e = v.abs() ** f['exponente']
    p = vr * i_r + vi * i_i + f['sp'] * e
    q = vi * i_r - vr * i_i + f['sq'] * e + f['bq'] * v * v
    pb = torch.zeros(f['n'], dtype=v.dtype, device=v.device).index_add_(0, f['grupo'], p)
    qb = torch.zeros(f['n'], dtype=v.dtype, device=v.device).index_add_(0, f['grupo'], q)
    return (pb ** 2 + qb ** 2)[f['exigir']]


def _fronteras_torch(f: dict, v, theta):
    """``error_de_fronteras`` con gradiente: mismos términos, en PyTorch."""
    torch = _torch()
    fuente, vivo, grupo, cuenta = f['fuente'], f['alimentado'], f['grupo'], f['cuenta']
    suma = torch.zeros(f['n'], dtype=v.dtype, device=v.device).index_add_(0, grupo, v)
    media = suma / cuenta.clamp(min=1)
    errores = [v[fuente] - f['consigna'][fuente], theta[fuente], v[~vivo], theta[~vivo],
               (v - media[grupo])[(cuenta[grupo] > 1) & vivo]]
    todos = torch.cat(errores)
    # Una red sin fuentes no llega a entrenar; aquí un NaN se llevaría todos los pesos.
    return (todos ** 2).mean() if todos.numel() else torch.zeros((), dtype=v.dtype, device=v.device)


def _terminos_torch(f: dict, v, theta, objetivo, mascara) -> dict:
    """Los tres términos de la pérdida, sin sumar (045:RF-6)."""
    return {'datos': ((v - objetivo)[mascara] ** 2).mean(), 'fisica': _residuo_torch(f, v, theta).mean(),
            'fronteras': _fronteras_torch(f, v, theta)}


@dataclass
class Entrenamiento:
    epocas: int = 300
    lr: float = 3e-3
    peso_fisico: float = 1e-4
    """La física de la base no tiene la capacidad de las líneas ni las tomas: con peso 1 la red
    se quedaba en ella (0,0032 p.u. en IN111–TA225); con 10⁻⁴ aprende lo que le falta de
    DIgSILENT (0,00046 p.u. en escenarios no vistos, residuo 0,011; 2026-10-24)."""
    ocultas: int = 64
    pasos: int = 8
    semilla: int = 0
    exponente_carga: float = 0.0
    """Modelo de carga de la física, elegido con los datos (``elegir_exponente``)."""
    fisica: str = 'mallado'
    """Física de la base (``FISICAS``): los pesos solo valen sobre la base con que se entrenaron."""
    paciencia: int = 60
    """Épocas sin mejorar el error de validación antes de parar (027:RF-5): con 300 épocas fijas
    el miembro seguía hasta el final aunque la validación ya no bajara."""
    cada: int = 5
    """Cada cuántas épocas se mide la validación."""
    lr_min: float = 1e-5
    """Tasa final del coseno (027:RF-6)."""
    recorte: float = 1.0
    """Norma máxima del gradiente (027:RF-6): con cargas grandes, el residuo físico daba saltos."""
    cobertura: float = 0.9
    """Cobertura del intervalo conforme de tensión por barra (027:RF-12)."""
    arquitectura: str = 'csg'
    peso_fronteras: float = 0.0
    """Peso del error de fronteras (045:RF-6). Se mide siempre y por defecto no se optimiza: la red ya
    impone la fuente, y un peso nuevo cambiaría el objetivo sin una medida que lo justifique."""

    def __post_init__(self):
        # Los modelos entrenados antes de la spec 058 guardan el nombre anterior.
        object.__setattr__(self, 'arquitectura',
                           ARQUITECTURA_ANTERIOR.get(self.arquitectura, self.arquitectura))


def entrenar_miembro(muestras: Sequence[Muestra], cfg: Entrenamiento, inicial: dict | None = None,
                     log: Callable[[str], None] = lambda _m: None, validacion: Sequence[Muestra] = (),
                     historial: list | None = None, al_validar: Callable[[int, float], None] | None = None,
                     terminos: list | None = None):
    """Un miembro del conjunto: error frente a DIgSILENT + residuo físico (PINN).

    Con ``validacion``, para tras ``cfg.paciencia`` épocas sin mejorar y devuelve los pesos de
    la mejor época (027:RF-5); ``historial`` recibe ``(época, mae de validación)`` y
    ``al_validar`` se llama con los dos tras cada medida (la poda de la búsqueda, RF-7).
    ``terminos`` recibe, por época, la media de datos, física y fronteras (045:RF-6).
    """
    torch = _torch()
    try:
        return _entrenar_en(muestras, cfg, inicial, log, dispositivo(), validacion,
                            historial if historial is not None else [], al_validar, terminos)
    finally:
        torch.cuda.empty_cache()     # cada miembro devuelve la memoria de la GPU


def _entrenar_en(muestras: Sequence[Muestra], cfg: Entrenamiento, inicial: dict | None,
                 log: Callable[[str], None], disp, validacion: Sequence[Muestra] = (),
                 historial: list | None = None, al_validar: Callable[[int, float], None] | None = None,
                 terminos: list | None = None):
    torch = _torch()
    # 027:RF-9: mismo manifiesto, misma GPU, mismo modelo. ``index_add_`` en CUDA no tiene
    # versión determinista: se avisa en vez de fallar y la prueba mide la diferencia.
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(cfg.semilla)
    random.seed(cfg.semilla)
    red = _red(cfg.ocultas, cfg.pasos, cfg.arquitectura).to(disp)
    if inicial:
        red.load_state_dict(inicial)
    opt = torch.optim.Adam(red.parameters(), lr=cfg.lr)
    plan = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(cfg.epocas, 1), eta_min=cfg.lr_min)
    datos = [(_fisica(m, disp, cfg.exponente_carga), *_tensores(m, disp, cfg.exponente_carga, cfg.fisica),
              torch.tensor(m.v, dtype=torch.float32, device=disp),
              torch.tensor(m.mascara, device=disp)) for m in muestras]
    val = [(*_tensores(m, disp, cfg.exponente_carga, cfg.fisica),
            torch.tensor(m.v, dtype=torch.float32, device=disp),
            torch.tensor(m.mascara, device=disp)) for m in validacion]
    historial = historial if historial is not None else []
    mejor, mejor_estado, mejor_epoca = math.inf, None, -1
    for epoca in range(cfg.epocas):
        random.shuffle(datos)
        total = 0.0
        suma = {'datos': 0.0, 'fisica': 0.0, 'fronteras': 0.0}
        for f, x, ar, e, v, mask in datos:
            vp, th = red(x, ar, e)
            t = _terminos_torch(f, vp, th, v, mask)
            perdida = t['datos'] + cfg.peso_fisico * t['fisica'] + cfg.peso_fronteras * t['fronteras']
            for clave in suma:
                suma[clave] += float(t[clave].detach())
            opt.zero_grad()
            perdida.backward()
            torch.nn.utils.clip_grad_norm_(red.parameters(), cfg.recorte)
            opt.step()
            total += float(perdida.detach())
        plan.step()
        if terminos is not None:
            terminos.append({'epoca': epoca, **{k: w / max(len(datos), 1) for k, w in suma.items()}})
        if epoca % 100 == 0:
            log(f'  época {epoca}: pérdida {total / max(len(datos), 1):.3e}')
        if val and (epoca % cfg.cada == 0 or epoca == cfg.epocas - 1):
            red.eval()
            with torch.no_grad():
                err = float(np.mean([float((red(x, ar, e)[0] - v)[mask].abs().mean()) for x, ar, e, v, mask in val]))
            red.train()
            historial.append((epoca, err))
            if al_validar is not None:
                al_validar(epoca, err)
            if err < mejor - 1e-9:
                mejor, mejor_epoca = err, epoca
                mejor_estado = {k: v.detach().clone() for k, v in red.state_dict().items()}
            elif epoca - mejor_epoca >= cfg.paciencia:
                log(f'  parada temprana en la época {epoca}: la mejor fue la {mejor_epoca} ({mejor:.3e} p.u.)')
                break
    final = mejor_estado if mejor_estado is not None else red.state_dict()
    return {k: v.detach().cpu() for k, v in final.items()}


def motivos_de_dominio(m: Muestra, dominio: Mapping[str, Any]) -> list[str]:
    """Por qué esta red está fuera de lo que un modelo aprendió (RF-19, 045:RF-4, RF-9)."""
    motivos = list(m.bloqueos)
    # 045:RF-2: los pesos aprendieron con la física de su grafo; un modelo anterior no dice cuál fue.
    if dominio.get('version_grafo') != m.version:
        motivos.append(f"modelo entrenado con el grafo versión {dominio.get('version_grafo')}, esta red es "
                       f'versión {m.version}')
    lo, hi = np.array(dominio['x_min']), np.array(dominio['x_max'])
    margen = 0.1 * np.maximum(hi - lo, 1e-6)
    fuera = (m.x < lo - margen) | (m.x > hi + margen)
    if fuera.any():
        motivos.append(f'{int(fuera.any(axis=1).sum())} nodo(s) con datos fuera de lo aprendido')
    n_min, n_max = dominio['nodos']
    if not 0.5 * n_min <= len(m.ids) <= 2 * n_max:
        motivos.append(f'{len(m.ids)} nodos frente a {n_min}–{n_max} aprendidos')
    # 071:RF-2: rangos y tamaño no dicen de qué red se trata: un modelo con 0,0024 p.u. en su red
    # dio 0,308 p.u. en otra (2026-10-28). Sin redes declaradas, tampoco se sabe: decide la física.
    redes = dominio.get('redes')
    if not redes:
        motivos.append('el modelo no declara en qué redes se probó')
    elif red_de(m) not in redes:
        motivos.append('red distinta de aquellas en las que se probó el modelo')
    return motivos


@dataclass
class OraculoPINN:
    """Conjunto de GNN con su dominio (RF-15, RF-19)."""

    estados: list[dict]
    cfg: Entrenamiento
    dominio: dict[str, Any]
    nombre: str = 'pinn_gnn'
    version: str = ''
    cuantil: float | None = None
    """Cuantil conforme de |error| / (dispersión + ε) en calibración (027:RF-12, 044:RF-4)."""
    cobertura_justificada: bool = False
    """Si hay familias de calibración para afirmar la cobertura pedida (044:RF-8)."""

    def _redes(self):
        disp = dispositivo()
        out = []
        for s in self.estados:
            red = _red(self.cfg.ocultas, self.cfg.pasos, self.cfg.arquitectura).to(disp)
            red.load_state_dict(s)
            red.eval()
            out.append(red)
        return out, disp

    def fuera_de_dominio(self, m: Muestra) -> list[str]:
        """Motivos por los que esta red está fuera de lo aprendido (RF-19)."""
        return motivos_de_dominio(m, self.dominio)

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]:
        torch = _torch()
        m = muestra(grafo)
        redes, disp = self._redes()
        x, ar, e = _tensores(m, disp, self.cfg.exponente_carga, self.cfg.fisica)
        with torch.no_grad():
            salidas = [red(x, ar, e) for red in redes]
        vs = np.stack([s[0].cpu().numpy() for s in salidas])
        ths = np.stack([s[1].cpu().numpy() for s in salidas])
        v, th = imponer_fronteras(m, vs.mean(axis=0), ths.mean(axis=0))     # 045:RF-5
        motivos = self.fuera_de_dominio(m)
        sigma = vs.std(axis=0)
        # 027:RF-12: semiancho del intervalo con la cobertura pedida.
        semiancho = None if self.cuantil is None else self.cuantil * (sigma + EPS_CONFORME)
        return {'ids': m.ids, 'v': v, 'theta': th, 'incertidumbre': sigma,
                'intervalo_pu': semiancho,
                'cobertura': self.cfg.cobertura if semiancho is not None and self.cobertura_justificada else None,
                'residuo': residuo(m, v, th, self.cfg.exponente_carga), 'fuera_de_dominio': bool(motivos),
                'motivos': motivos,
                'modelo': self.nombre, 'version': self.version}


#: Suelo de la dispersión en el cociente conforme: con los tres miembros casi iguales en una
#: barra, |error|/σ se disparaba y el cuantil salía de una sola barra (027:RF-12).
EPS_CONFORME = 1e-4


def cuantil_conforme(puntuaciones: Sequence[float], cobertura: float) -> float:
    """El cuantil de predicción conforme partida (Lei et al., 2018; Angelopoulos y Bates, 2023):
    el ⌈(n+1)·cobertura⌉-ésimo de las puntuaciones de calibración, que da cobertura ≥ la pedida
    con datos intercambiables (027:RF-12)."""
    s = np.sort(np.asarray(puntuaciones, dtype=float))
    if not len(s):
        raise ValueError('sin puntuaciones de calibración')
    k = int(np.ceil((len(s) + 1) * cobertura)) - 1
    return float(s[min(max(k, 0), len(s) - 1)])


def calibrar_conforme(oraculo: OraculoPINN, calibracion: Sequence[Muestra]) -> float | None:
    """Puntuaciones |v − v_DIgSILENT| / (σ + ε) por barra en ``calibracion`` y su cuantil."""
    puntuaciones = []
    for m in calibracion:
        p = oraculo.predecir(_grafo_de_muestra(m))
        err = np.abs(np.asarray(p['v']) - m.v)[m.mascara]
        puntuaciones.extend((err / (np.asarray(p['incertidumbre'])[m.mascara] + EPS_CONFORME)).tolist())
    return cuantil_conforme(puntuaciones, oraculo.cfg.cobertura) if puntuaciones else None


def confiable(prediccion: Mapping[str, Any], limites=None) -> tuple[bool, str | None]:
    """SI el intervalo de una barra es más ancho que la banda de la norma, no se usa para
    decidir (027:RF-13). Sin intervalo o sin límites, no se puede negar."""
    semi = prediccion.get('intervalo_pu')
    if semi is None or limites is None:
        return True, None
    banda = float(limites.tension_max_pu) - float(limites.tension_min_pu)
    ancho = 2 * np.asarray(semi, dtype=float)
    if len(ancho) and float(ancho.max()) > banda:
        k = int(np.argmax(ancho))
        return False, (f'intervalo de {ancho[k]:.3f} p.u. en {prediccion["ids"][k]}, más ancho que la banda '
                       f'{banda:.3f} p.u. de {limites.norma} (027:RF-13)')
    return True, None


def estado_electrico(prediccion: Mapping[str, Any], grafo: Mapping[str, Any], limites=None) -> dict[str, Any]:
    """Tensiones, flujos, pérdidas y cargabilidad de una predicción (RF-18).

    Fuera de dominio no se da como verdad: se pide el cálculo a DIgSILENT (RF-19); tampoco con
    un intervalo más ancho que la banda de la norma (027:RF-13).
    """
    if prediccion.get('fuera_de_dominio'):
        return {'requiere_pf': True, 'motivos': prediccion.get('motivos') or []}
    ok, motivo = confiable(prediccion, limites)
    if not ok:
        return {'requiere_pf': True, 'no_confiable': True, 'motivos': [motivo]}
    m = muestra(grafo)
    vc = np.asarray(prediccion['v']) * np.exp(1j * np.asarray(prediccion['theta']))
    a, b = m.aristas
    i = (vc[a] / m.ru - vc[b] / m.rw) / m.z
    perdidas = float(np.sum(np.abs(i) ** 2 * m.z.real) / 2 * S_BASE)
    carga = {}
    for k, rama in enumerate(m.ramas):
        if m.inom[k] > 0:
            carga[rama] = max(carga.get(rama, 0.0), 100 * abs(i[k]) / m.ru[k] / m.inom[k])
    return {'requiere_pf': False, 'tensiones': dict(zip(m.ids, map(float, prediccion['v']), strict=True)),
            'incertidumbre': dict(zip(m.ids, map(float, prediccion['incertidumbre']), strict=True)),
            'perdidas_mw': perdidas, 'cargabilidad_pct': carga,
            'residuo_max_pu': float(np.max(prediccion['residuo'])) if len(m.ids) else 0.0}


# ------------------------------------------------------------------ registro y puertas
def _raiz_modelos(bufer: BuferEpisodios) -> Path:
    return bufer.raiz / 'modelos'


def mae(modelo: Modelo, muestras: Iterable[Muestra]) -> float | None:
    """Error medio absoluto de tensión frente a DIgSILENT en las muestras."""
    errores = []
    for m in muestras:
        grafo = _grafo_de_muestra(m)
        p = modelo.predecir(grafo)
        errores.extend(np.abs(np.asarray(p['v'])[m.mascara] - m.v[m.mascara]).tolist())
    return float(np.mean(errores)) if errores else None


def _grafo_de_muestra(m: Muestra) -> dict:
    """Reconstruye el grafo de una muestra (para evaluar con el contrato ``predecir``)."""
    nodos = {}
    for i, n in enumerate(m.ids):
        nodos[n] = {'kv': 10 ** m.x[i, 0], 'p_mw': m.x[i, 1] * S_BASE, 'q_mvar': m.x[i, 2] * S_BASE,
                    'fuente': bool(m.fuente[i]), 'v_pu': float(m.x[i, 4]) if m.fuente[i] else None,
                    'banco_q_mvar': float(-m.s_shunt[i].imag * S_BASE)}
    ramas, vistos = [], set()
    kv = 10 ** m.x[:, 0]
    for k in range(m.aristas.shape[1]):
        a, b = int(m.aristas[0, k]), int(m.aristas[1, k])
        if (b, a) in vistos:
            continue
        vistos.add((a, b))
        z_base = kv[a] ** 2 / S_BASE
        i_base = S_BASE / (math.sqrt(3) * kv[a])
        ramas.append({'id': m.ramas[k], 'desde': m.ids[a], 'hasta': m.ids[b], 'cerrada': True,
                      'r_ohm': m.z[k].real * z_base, 'x_ohm': m.z[k].imag * z_base,
                      'inom_ka': m.inom[k] * i_base, 'ru': float(m.ru[k]), 'rw': float(m.rw[k])})
    # Sin versión ni motivos, lo evaluado parecería una red distinta de la que salió la muestra.
    return {'nodos': nodos, 'ramas': ramas, 'version': m.version, 'bloqueos_heredados': list(m.bloqueos)}


def guardar(oraculo: OraculoPINN, bufer: BuferEpisodios, meta: dict) -> Path:
    """Registra un modelo con lo que lo hizo (RF-13): consulta, episodios, semilla, métricas."""
    torch = _torch()
    version = time.strftime('%Y%m%d-%H%M%S') + f'-{random.getrandbits(16):04x}'
    carpeta = _raiz_modelos(bufer) / version
    carpeta.mkdir(parents=True)
    for i, s in enumerate(oraculo.estados):
        torch.save(s, carpeta / f'miembro_{i}.pt')
    (carpeta / 'modelo.json').write_text(json.dumps({
        **meta, 'version': version, 'cfg': oraculo.cfg.__dict__, 'dominio': oraculo.dominio,
        'miembros': len(oraculo.estados), 'torch': torch.__version__}, indent=2, ensure_ascii=False),
        encoding='utf-8')
    oraculo.version = version
    return carpeta


def cargar(bufer: BuferEpisodios, version: str | None = None) -> OraculoPINN | None:
    """El modelo promovido (o la versión pedida), o ``None`` si no hay."""
    raiz = _raiz_modelos(bufer)
    if version is None:
        puntero = raiz / 'promovido.json'
        if not puntero.is_file():
            return None
        version = json.loads(puntero.read_text(encoding='utf-8'))['version']
    return _abrir_carpeta(raiz / version)


def _abrir_carpeta(carpeta: Path) -> OraculoPINN:
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    torch = _torch()
    estados = [torch.load(carpeta / f'miembro_{i}.pt', weights_only=True) for i in range(meta['miembros'])]
    # Los modelos de antes del 2026-10-24 se entrenaron sobre el barrido radial.
    cfg = Entrenamiento(**{'fisica': 'radial', **meta['cfg']})
    conforme = meta.get('conforme') or {}
    return OraculoPINN(estados, cfg, meta['dominio'], version=carpeta.name, cuantil=conforme.get('cuantil'),
                       cobertura_justificada=conforme.get('publicable') is True)


def verificar_reapertura(carpeta: Path | str) -> dict[str, Any]:
    """043:RF-5: el candidato reabierto da lo mismo que al guardarlo; se llama en un proceso nuevo,
    porque en el que entrena los pesos siguen en memoria y un fichero roto no se notaría."""
    carpeta = Path(carpeta)
    prueba = json.loads((carpeta / 'readback.json').read_text(encoding='utf-8'))
    obtenido = np.asarray(_abrir_carpeta(carpeta).predecir(prueba['grafo'])['v'], dtype=float)
    esperado = np.asarray(prueba['v'], dtype=float)
    if obtenido.shape != esperado.shape or not obtenido.size:
        return {'ok': False, 'motivo': 'la predicción reabierta no tiene la forma de la guardada', 'proceso_nuevo': True}
    error = float(np.max(np.abs(obtenido - esperado)))
    return {'ok': error <= TOLERANCIA_REPRODUCCION, 'error_max_pu': error, 'nodos': int(obtenido.size),
            'proceso_nuevo': True}


def _reabrir_en_otro_proceso(carpeta: Path) -> dict[str, Any]:
    """043:RF-5: en un hijo, con el turno de GPU de quien entrena; sin el token la encontraría ocupada."""
    import sys

    from ..model_registry import reabrir_en_subproceso
    from ..trabajadores_ml import entorno_hijo_gpu

    herramienta = Path(__file__).resolve().parents[3] / 'tools' / 'digital_twin_entrenar.py'
    return reabrir_en_subproceso([sys.executable, str(herramienta), '--reabrir-candidato', str(carpeta)],
                                 timeout_s=600.0, env=entorno_hijo_gpu())


def _decidir_promocion(bufer: BuferEpisodios, carpeta: Path, meta: Mapping[str, Any], fallos: list[str], motivo: str, *,
                       reabrir: Callable[[Path], dict[str, Any]] | None = None, registro=None) -> dict[str, Any]:
    """043:RF-1, RF-5: reapertura en otro proceso, decisión en el registro común y, si se aprueba, puntero.

    La PINN se promovía con solo sus puertas: un fichero roto se habría puesto en uso y su decisión no
    constaba en el registro de las demás familias. ``promovido.json`` sigue siendo lo único que la pone en
    uso (071:RF-5), de modo que no hay un segundo puntero que se quede atrás al volver al anterior.
    """
    from ..model_registry import EstadoModelo

    smoke: dict[str, Any] = {'ok': False, 'motivo': 'no se reabre: no pasó sus puertas'}
    if not fallos:
        smoke = (reabrir or _reabrir_en_otro_proceso)(carpeta)
        if smoke.get('ok') is not True:
            # El hijo deja su motivo en la última línea (``payload``). Sin leerlo, con la GPU en manos de
            # otro proceso el operador veía «falló la reapertura en un proceso nuevo: 2» (2026-11-03).
            hijo = smoke.get('payload') if isinstance(smoke.get('payload'), Mapping) else {}
            fallos.append('falló la reapertura en un proceso nuevo: '
                          f"{smoke.get('error') or smoke.get('motivo') or hijo.get('error') or hijo.get('motivo') or smoke.get('stderr') or smoke.get('returncode')}")
    candidate_id = None
    if registro is not None:
        estado = EstadoModelo.RECHAZADO if fallos else EstadoModelo.PROMOVIDO
        artefactos = sorted(p for p in carpeta.iterdir() if p.is_file())
        try:
            candidate_id = registro.registrar_candidato(
                'pinn', model_manifest={'algorithm': 'pinn_gnn', 'version': carpeta.name, 'cfg': meta.get('cfg'),
                                        'manifiesto': meta.get('manifiesto')},
                dataset_manifest={'particiones': meta.get('particiones'), 'particiones_ids': meta.get('particiones_ids'),
                                  'politica_hash': (meta.get('evaluacion') or {}).get('politica_hash')},
                metrics={**{k: meta.get(k) for k in ('mae_v', 'residuo_medio', 'mae_dorados')},
                         'evaluacion': meta.get('evaluacion'), 'conforme': meta.get('conforme')},
                decision={'status': estado.value, 'gates': {'approved': not fallos}, 'fallos': list(fallos)},
                smoke_reload=smoke, artifacts=artefactos)['candidate_id']
        except (OSError, ValueError) as exc:
            # Sin decisión anotada no hay promoción: un valor no finito cae aquí, no en el puntero.
            fallos.append(f'no se pudo anotar en el registro de modelos: {exc}')
    if not fallos:
        promover(bufer, carpeta.name, motivo)
    return {'promovido': not fallos, 'candidate_id': candidate_id, 'smoke_reload': smoke}


def guardar_y_reabrir(oraculo: OraculoPINN, bufer: BuferEpisodios, meta: dict, sonda: Muestra,
                      reabrir: Callable[[Path], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Guarda un candidato sin promoverlo y lo reabre en otro proceso (045:RF-8, 043:RF-5).

    Una ablación se mide con lo que queda en disco: en memoria, un fichero roto no se notaría.
    """
    carpeta = guardar(oraculo, bufer, meta)
    grafo = _grafo_de_muestra(sonda)
    (carpeta / 'readback.json').write_text(json.dumps(
        {'grafo': grafo, 'v': oraculo.predecir(grafo)['v'].tolist()}, ensure_ascii=False, default=float), encoding='utf-8')
    return {**(reabrir or _reabrir_en_otro_proceso)(carpeta), 'version': carpeta.name}


def promover(bufer: BuferEpisodios, version: str, motivo: str) -> None:
    """Pasa a ser el modelo en uso; el historial guarda cada cambio (RF-42)."""
    raiz = _raiz_modelos(bufer)
    anterior = None
    if (raiz / 'promovido.json').is_file():
        anterior = json.loads((raiz / 'promovido.json').read_text(encoding='utf-8'))['version']
    fila = {'version': version, 'anterior': anterior, 'motivo': motivo,
            'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
    with staging_publicacion(raiz / 'promovido.json') as tmp:
        tmp.write_text(json.dumps(fila, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, raiz / 'promovido.json')
    with open(raiz / 'historial.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(fila, ensure_ascii=False) + '\n')


def volver_al_anterior(bufer: BuferEpisodios) -> str | None:
    """Vuelve al modelo promovido antes del actual (RF-42)."""
    raiz = _raiz_modelos(bufer)
    if not (raiz / 'promovido.json').is_file():
        return None
    anterior = json.loads((raiz / 'promovido.json').read_text(encoding='utf-8')).get('anterior')
    if anterior:
        promover(bufer, anterior, 'vuelta al anterior')
    return anterior


@dataclass
class Puertas:
    """Umbrales de promoción (RF-16): el error de tensión, la décima parte de la banda."""

    mae_v_max: float = 0.005
    residuo_max: float = 0.05
    tolerancia_dorados: float = 1.05


def _muestras(bufer: BuferEpisodios, consulta: Consulta,
              excluidos: dict[str, int] | None = None) -> tuple[list[Muestra], list[str]]:
    """Las muestras de la consulta; ``excluidos`` recibe, por motivo, los episodios que no enseñan.

    045:RF-2: sin ese recuento, un búfer entero de grafos anteriores parecía un búfer sin episodios.
    """
    muestras, ids = [], []
    for e in bufer.consultar(consulta):
        if e.clase.value not in CLASES_OBJETIVO:
            continue
        motivo = por_que_no_ensena(e)
        if motivo is not None:
            if excluidos is not None:
                excluidos[motivo] = excluidos.get(motivo, 0) + 1
            continue
        muestras.append(muestra_de_episodio(e))
        ids.append(e.episode_id)
    return muestras, ids


#: Episodios de prueba de otra red sin los que no se promueve (027:RF-3; usuario, 2026-10-28).
MIN_EPISODIOS_PRUEBA = 10


def fallos_de_comparacion(error: float | None, error_fisica: float | None, error_actual: float | None,
                          puertas: Puertas) -> list[str]:
    """Lo que impide promover frente al flujo físico y al modelo en uso (071:RF-3, RF-4).

    Sin esta comparación, una PINN peor que el flujo que ya tiene el conversor pasaba solo por
    no superar 0,005 p.u. Sin una medida de la física no se puede demostrar que la mejore.
    """
    fallos = []
    if error is None or error_fisica is None:
        fallos.append('sin medida en la prueba para comparar con el flujo físico')
    elif error >= error_fisica:
        fallos.append(f'no mejora al flujo físico: {error:.4g} frente a {error_fisica:.4g} p.u.')
    if error is not None and error_actual is not None and error > puertas.tolerancia_dorados * error_actual + 1e-6:
        fallos.append(f'empeora al modelo en uso: {error:.4g} frente a {error_actual:.4g} p.u.')
    return fallos


def red_de(m: Muestra) -> str:
    """La red de una muestra por sus nodos: los escenarios de una misma red comparten huella."""
    return hashlib.sha256('\n'.join(m.ids).encode('utf-8')).hexdigest()


def particionar(muestras: Sequence[Muestra]) -> dict[str, list[Muestra]]:
    """«Un sistema fuera» (027:RF-2): cada red entera a prueba o a entrenamiento; con dos o
    más redes, al menos una a prueba (la de huella menor si el reparto fijo no da ninguna) y
    nunca todas. La validación sale de los escenarios de las redes de entrenamiento."""
    redes = sorted({red_de(m) for m in muestras})
    de_prueba = {r for r in redes if particion(r) == 'prueba'}
    if len(redes) >= 2 and (not de_prueba or de_prueba == set(redes)):
        de_prueba = {redes[0]}
    if len(redes) < 2:
        de_prueba = set()
    grupos: dict[str, list[Muestra]] = {'entrenamiento': [], 'validacion': [], 'prueba': []}
    for m in muestras:
        if red_de(m) in de_prueba:
            grupos['prueba'].append(m)
        elif particion(hashlib.sha256((m.familia or 'x').encode('utf-8')).hexdigest()) == 'validacion':
            grupos['validacion'].append(m)
        else:
            grupos['entrenamiento'].append(m)
    return grupos


def _grupos(muestras: Sequence[Muestra], ids: Sequence[str], sistema: str | None) -> dict[str, list[Muestra]]:
    """«Un sistema fuera» (RF-2) o, con ``sistema``, su propio reparto por la huella de cada
    episodio (RF-68, el de ``curva.reparto_del_sistema``)."""
    if not sistema:
        return particionar(muestras)
    return {k: [muestras[i] for i in v]
            for k, v in reparto_del_sistema(ids, [m.familia for m in muestras]).items()}


def politica_pinn(puertas: Puertas, cfg: Entrenamiento, sistema: str | None) -> PoliticaDeError:
    """Lo que se exige a la PINN, escrito antes de ajustar nada (044:RF-3, RF-5): las puertas de
    siempre, ahora también por familia. El modo dice qué se puede afirmar del resultado (027:RF-68)."""
    return PoliticaDeError(modo='por_sistema' if sistema else 'generalizacion',
                           cobertura_objetivo=cfg.cobertura,
                           semillas=tuple(cfg.semilla + k for k in range(MIEMBROS)),
                           topes=(('mae_v', puertas.mae_v_max), ('residuo', puertas.residuo_max)),
                           tolerancia_regresion=puertas.tolerancia_dorados)


def fallos_de_custodia(grupos: Mapping[str, Sequence[Muestra]], identidades: Mapping[int, str],
                       politica: PoliticaDeError) -> list[str]:
    """044:RF-1, RF-2: las cuatro particiones pasan por el particionador común, con su familia como
    grupo de custodia y su red como sistema; si no, cada familia de modelos tendría su criterio."""
    nombres = {'entrenamiento': 'entrenamiento', 'validacion': 'seleccion',
               'calibracion': 'calibracion', 'prueba': 'prueba'}
    registros = [{'record_id': identidades[id(m)], 'group_id': f'{red_de(m)}:{m.familia}',
                  'particion': nombres[parte], 'sistema': red_de(m)}
                 for parte, ms in grupos.items() for m in ms]
    try:
        particionar_registros(registros, politica)
    except ValueError as exc:
        return [f'{exc} (044:RF-1, RF-2)']
    return []


def fallos_de_particion(grupos: Mapping[str, Sequence[Muestra]]) -> list[str]:
    """Lo que impide promover por el reparto (027:RF-3)."""
    if not grupos['prueba']:
        return ['sin una red de prueba distinta de las de entrenamiento: hace falta otro sistema '
                '(027:RF-3)']
    if len(grupos['prueba']) < MIN_EPISODIOS_PRUEBA:
        return [f"{len(grupos['prueba'])} episodios de prueba de otra red, menos de "
                f'{MIN_EPISODIOS_PRUEBA} (027:RF-3)']
    return []


def separar_calibracion(grupos: Mapping[str, Sequence[Muestra]]) -> dict[str, list[Muestra]]:
    """060:RF-2: reserva familias completas de validación antes de cualquier ajuste."""
    salida = {k: list(v) for k, v in grupos.items()}
    familias = sorted({(red_de(m), m.familia or '') for m in grupos['validacion']})
    reservadas = set(familias[::2])
    salida['calibracion'] = [m for m in grupos['validacion'] if (red_de(m), m.familia or '') in reservadas]
    salida['validacion'] = [m for m in grupos['validacion'] if (red_de(m), m.familia or '') not in reservadas]
    return salida


def herencia_independiente(previas: Mapping | None, actuales: Mapping) -> bool:
    """060:RF-3: pesos sin genealogía demostrada no transfieren una prueba independiente."""
    if not previas or not previas.get('entrenamiento') or not previas.get('validacion'):
        return False
    vistas = set(previas['entrenamiento']) | set(previas['validacion'])
    reservadas = set(actuales['calibracion']) | set(actuales['prueba'])
    return not bool(vistas & reservadas)


def elegir_exponente(muestras: Sequence[Muestra], candidatos: Sequence[float] = (0.0, 1.0, 2.0),
                     fisica: str = 'mallado') -> float:
    """El modelo de carga que mejor reproduce a DIgSILENT con la física de la base.

    No se fija en el código porque otra empresa o versión puede modelar las cargas de otro
    modo. Con el barrido radial salía impedancia constante (0,019 p.u. frente a 0,050), pero
    era el barrido el que fallaba: con el flujo mallado gana la potencia constante, con
    0,0032 p.u. frente a 0,016 (IN111–TA225, 2026-10-24).
    """
    def error(x: float) -> float:
        errores = []
        for m in muestras[:8]:
            modelo = FISICAS[fisica](exponente=x)
            p = modelo.predecir_muestra(m) if fisica == 'mallado' else modelo.predecir(_grafo_de_muestra(m))
            errores.append(float(np.mean(np.abs(p['v'][m.mascara] - m.v[m.mascara]))))
        return float(np.mean(errores)) if errores else 0.0
    return min(candidatos, key=error)


#: Con qué se agrupa al apartar y al contar: las variantes de demanda de una maniobra no son independientes.
AGRUPACION_DE_CUSTODIA = 'red y familia topológica: cada familia entera en una sola partición'


def _denominador(muestras: Sequence[Muestra]) -> dict[str, int]:
    """044:RF-8: una media sin saber de cuántos sale no se puede juzgar ni repetir."""
    return {'ejemplos': len(muestras),
            'grupos': len({(red_de(m), m.familia) for m in muestras}),
            'barras': sum(int(np.count_nonzero(m.mascara)) for m in muestras)}


def metricas_por_familia(candidato: Modelo, evaluacion: Sequence[Muestra], residuos: Sequence[float],
                         fisica: Modelo, actual: Modelo | None) -> dict[str, dict[str, Any]]:
    """Error del candidato, de la física y del modelo en uso en cada familia de la prueba (044:RF-5)."""
    por_familia: dict[str, list[int]] = {}
    for i, m in enumerate(evaluacion):
        por_familia.setdefault(m.familia or '—', []).append(i)
    salida = {}
    for familia, indices in sorted(por_familia.items()):
        ms = [evaluacion[i] for i in indices]
        salida[familia] = {**_denominador(ms), 'mae_v': mae(candidato, ms),
                           'residuo': float(np.mean([residuos[i] for i in indices])),
                           'mae_fisica': mae(fisica, ms),
                           'mae_activo': mae(actual, ms) if actual is not None else None}
    return salida


def metricas_de_prueba(modelo: Modelo, prueba: Sequence[Muestra], fisica: Modelo) -> tuple[dict[str, Any], float]:
    """Las métricas que juzga ``evaluar_candidato`` y la latencia media (s por red) de un modelo sin uso previo."""
    inicio = time.perf_counter()
    residuos = [float(np.mean(modelo.predecir(_grafo_de_muestra(m))['residuo'])) for m in prueba]
    latencia = (time.perf_counter() - inicio) / max(len(prueba), 1)
    return ({'global': {**_denominador(prueba), 'mae_v': mae(modelo, prueba), 'residuo': float(np.mean(residuos)),
                        'mae_fisica': mae(fisica, prueba), 'mae_activo': None},
             'familias': metricas_por_familia(modelo, prueba, residuos, fisica, None)}, latencia)


def denominadores(grupos: Mapping[str, Sequence[Muestra]]) -> dict[str, dict[str, int]]:
    """044:RF-8: de cuántos ejemplos, familias y barras sale cada partición."""
    return {k: _denominador(v) for k, v in grupos.items()}


def particiones_del_bufer(bufer: BuferEpisodios, consulta: Consulta | None = None, *,
                          sistema: str | None = None, puertas: Puertas | None = None):
    """Las particiones de custodia de los episodios vigentes, las mismas que usa ``entrenar`` (045:RF-8)."""
    muestras, ids = _muestras(bufer, consulta or Consulta())
    if not muestras:
        raise ValueError('BLOQUEADO_POR_DATOS: no hay episodios vigentes con que comparar')
    grupos = separar_calibracion(_grupos(muestras, ids, sistema))
    identidades = {id(m): i for m, i in zip(muestras, ids, strict=True)}
    nombres = {'entrenamiento': 'entrenamiento', 'validacion': 'seleccion', 'calibracion': 'calibracion', 'prueba': 'prueba'}
    registros = [{'record_id': identidades[id(m)], 'group_id': f'{red_de(m)}:{m.familia}', 'particion': nombres[parte],
                  'sistema': red_de(m)} for parte, ms in grupos.items() for m in ms]
    return particionar_registros(registros, politica_pinn(puertas or Puertas(), Entrenamiento(), sistema))


def informe_conforme(oraculo: OraculoPINN, calibracion: Sequence[Muestra], prueba: Sequence[Muestra]) -> dict[str, Any]:
    """Lo que se puede decir del intervalo, con sus denominadores (044:RF-4, RF-8).

    El cuantil sale de las barras, pero las barras de un episodio y los episodios de una familia están
    correlacionados: el recuento que cuenta para la cobertura pedida es el de familias, no el de barras. Con
    pocas, ⌈(g+1)·cobertura⌉ no cabe en g y no se afirma la cobertura: el intervalo sigue sirviendo para negar
    una predicción demasiado ancha (027:RF-13), pero no se publica como un 90 % que nadie ha demostrado.
    """
    objetivo = oraculo.cfg.cobertura
    grupos = _denominador(calibracion)['grupos']
    motivo = None
    if oraculo.cuantil is None or not math.isfinite(oraculo.cuantil):
        motivo = 'sin cuantil calibrado'
    elif math.ceil((grupos + 1) * objetivo) > grupos:
        motivo = f'{grupos} familia(s) de calibración no bastan para afirmar una cobertura de {objetivo:g}'
    cubiertas = barras = 0
    if oraculo.cuantil is not None and math.isfinite(oraculo.cuantil):
        for m in prueba:
            p = oraculo.predecir(_grafo_de_muestra(m))
            error = np.abs(np.asarray(p['v']) - m.v)[m.mascara]
            semi = oraculo.cuantil * (np.asarray(p['incertidumbre'])[m.mascara] + EPS_CONFORME)
            cubiertas += int(np.count_nonzero(error <= semi))
            barras += int(error.size)
    empirica = cubiertas / barras if barras else None
    if motivo is None and empirica is None:
        motivo = 'sin barras de prueba donde medir la cobertura'
    return {'cuantil': oraculo.cuantil, 'cobertura': objetivo if motivo is None else None,
            'cobertura_objetivo': objetivo, 'cobertura_empirica': empirica, 'calibracion': len(calibracion),
            'denominadores': {'calibracion': _denominador(calibracion), 'prueba': _denominador(prueba)},
            'metodo': 'conforme partida por barra', 'agrupacion': AGRUPACION_DE_CUSTODIA,
            'garantia': 'sin garantía de datos intercambiables: las barras y los episodios están correlacionados',
            'publicable': motivo is None, 'motivo': motivo}


def _commit() -> str | None:
    """El commit del código con que se entrena (027:RF-8), o ``None`` fuera de git."""
    import subprocess

    try:
        r = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parent,
                           capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def manifiesto(cfg: Entrenamiento, ids: Sequence[str], grupos: Mapping[str, Sequence[Muestra]],
               candidato: OraculoPINN, parte_de: str | None) -> dict[str, Any]:
    """Lo que hace falta para reproducir el modelo (027:RF-8): episodios (su id es la huella
    de su contenido), commit, configuración, semillas, dispositivo, de qué modelo parte y el
    error por familia de la partición de evaluación."""
    torch = _torch()
    evaluacion = grupos.get('prueba') or []
    por_familia: dict[str, list[Muestra]] = {}
    for m in evaluacion:
        por_familia.setdefault(m.familia or '—', []).append(m)
    return {'episodios': list(ids), 'commit': _commit(), 'cfg': dict(cfg.__dict__),
            'semillas': [cfg.semilla + k for k in range(MIEMBROS)],
            'dispositivo': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            'torch': torch.__version__, 'cuda': torch.version.cuda, 'parte_de': parte_de,
            'particiones': {k: len(v) for k, v in grupos.items()},
            'mae_por_familia': {f: mae(candidato, ms) for f, ms in sorted(por_familia.items())}}


#: Diferencia de MAE de tensión que se acepta al reproducir (027:RF-9).
TOLERANCIA_REPRODUCCION = 1e-5


def reproducir(bufer: BuferEpisodios, version: str, log: Callable[[str], None] = lambda _m: None
               ) -> dict[str, Any]:
    """Vuelve a entrenar un modelo con su manifiesto y compara su error (027:RF-9)."""
    torch = _torch()
    carpeta = _raiz_modelos(bufer) / version
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    man = meta.get('manifiesto')
    if not man:
        raise ValueError(f'el modelo {version} no tiene manifiesto (es de antes de 027:RF-8)')
    pares = [(m, i) for i in man['episodios'] if (m := muestra_de_episodio(bufer.leer(i))) is not None]
    muestras = [m for m, _i in pares]
    cfg = Entrenamiento(**man['cfg'])
    if meta.get('particiones_ids'):
        por_id = {i: m for m, i in pares}
        grupos = {k: [por_id[i] for i in v] for k, v in meta['particiones_ids'].items()}
    else:
        grupos = _grupos(muestras, [i for _m, i in pares], man.get('sistema'))
    if not all(grupos.get(k) for k in ('entrenamiento', 'validacion', 'prueba')):
        raise ValueError('no se reproduce ajustando con particiones de respaldo (060:RF-1)')
    inicial = cargar(bufer, man['parte_de']) if man.get('parte_de') else None
    estados = [entrenar_miembro(grupos['entrenamiento'], Entrenamiento(**{**cfg.__dict__, 'semilla': s}),
                                inicial.estados[k] if inicial and k < len(inicial.estados) else None,
                                log, validacion=grupos['validacion'])
               for k, s in enumerate(man['semillas'])]
    candidato = OraculoPINN(estados, cfg, meta['dominio'])
    evaluacion = grupos['prueba']
    error = mae(candidato, evaluacion)
    diferencia = abs((error or 0.0) - (meta.get('mae_v') or 0.0))
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    return {'version': version, 'mae_original': meta.get('mae_v'), 'mae_reproducido': error,
            'diferencia': diferencia, 'reproducible': diferencia < TOLERANCIA_REPRODUCCION,
            'mismo_commit': man.get('commit') == _commit(), 'misma_gpu': man.get('dispositivo') == gpu}


def entrenar(bufer: BuferEpisodios, *, consulta: Consulta | None = None, cfg: Entrenamiento | None = None,
             puertas: Puertas | None = None, dorados: Sequence[str] = (),
             log: Callable[[str], None] = lambda _m: None, sistema: str | None = None,
             reabrir: Callable[[Path], dict[str, Any]] | None = None, registro=None) -> dict[str, Any]:
    """Entrena un candidato con una consulta fija del búfer, lo evalúa por particiones de
    familia y lo promueve si supera las puertas sin empeorar los dorados (RF-12, RF-13,
    RF-16, RF-17, RF-42). Si ya hay modelo, parte de sus pesos y repite el histórico entero
    (RF-17, RF-43): ajuste fino, no desde cero."""
    consulta = consulta or Consulta()
    puertas = puertas or Puertas()
    excluidos: dict[str, int] = {}
    muestras, ids = _muestras(bufer, consulta, excluidos)
    for motivo, cuantos in sorted(excluidos.items()):
        log(f'Gemelo: {cuantos} episodio(s) no enseñan: {motivo}')
    if sistema:
        # 027:RF-68: solo los episodios de ese sistema (su red, por la huella de sus nodos).
        elegidos = [i for i, m in enumerate(muestras) if red_de(m).startswith(sistema)]
        muestras, ids = [muestras[i] for i in elegidos], [ids[i] for i in elegidos]
    if not muestras:
        detalle = ''.join(f'; {cuantos} con {motivo}' for motivo, cuantos in sorted(excluidos.items()))
        return {'entrenado': False, 'motivo': f'no hay episodios con grafo y tensiones{detalle}',
                'excluidos': excluidos}
    # 027:RF-29, RF-30: el dataset se audita antes; con valores no finitos no se entrena.
    from .auditoria import auditar_muestras

    actual_cfg = (cfg or Entrenamiento())
    auditoria = auditar_muestras(muestras, ids, parametros=MIEMBROS * _parametros(actual_cfg))
    for aviso in auditoria['avisos']:
        log(f'Gemelo: {aviso}')
    if not auditoria['apto']:
        return {'entrenado': False, 'auditoria': auditoria,
                'motivo': 'dataset con valores no finitos: ' + ', '.join(
                    f"{x['episodio']} ({x['campo']})" for x in auditoria['no_finitos'][:10])}
    grupos = separar_calibracion(_grupos(muestras, ids, sistema))
    fallos = fallos_de_particion(grupos)
    for parte in ('entrenamiento', 'validacion', 'calibracion'):
        if not grupos[parte]:
            fallos.append(f'sin partición independiente de {parte} (060:RF-1)')
    asignadas = [id(m) for ms in grupos.values() for m in ms]
    if len(asignadas) != len(set(asignadas)):
        fallos.append('muestras compartidas entre particiones (060:RF-2)')
    familias_asignadas: dict[tuple[str, str], str] = {}
    for parte, ms in grupos.items():
        for m in ms:
            clave = (red_de(m), m.familia or '')
            if clave in familias_asignadas and familias_asignadas[clave] != parte:
                fallos.append('familia compartida entre particiones (060:RF-2)')
                break
            familias_asignadas[clave] = parte
    identidades = {id(m): i for m, i in zip(muestras, ids, strict=True)}
    if not fallos:
        fallos += fallos_de_custodia(grupos, identidades, politica_pinn(puertas, actual_cfg, sistema))
    if fallos:
        return {'entrenado': False, 'promovido': False, 'status': 'BLOQUEADO_POR_DATOS',
                'fallos': fallos, 'motivo': '; '.join(fallos),
                'particiones': {k: len(v) for k, v in grupos.items()}}
    particiones_ids = {k: [identidades[id(m)] for m in ms] for k, ms in grupos.items()}
    particiones_familias = {k: sorted({red_de(m) + ':' + (m.familia or '') for m in ms})
                           for k, ms in grupos.items()}
    actual = cargar(bufer)
    # Sin configuración, la del modelo en uso; sus pesos solo valen con la misma arquitectura.
    cfg = cfg or (actual.cfg if actual else Entrenamiento())
    # Un modelo en uso sobre el barrido radial no fija la física del candidato: la mallada lo sustituye.
    cfg = Entrenamiento(**{**cfg.__dict__, 'fisica': 'mallado'})
    cfg = Entrenamiento(**{**cfg.__dict__,
                           'exponente_carga': elegir_exponente(grupos['entrenamiento'], fisica=cfg.fisica)})
    log(f'Gemelo: física {cfg.fisica}, modelo de carga S0·|V|^{cfg.exponente_carga:g}')
    politica = politica_pinn(puertas, cfg, sistema)                      # 044:RF-3: sellada antes de ajustar.
    compatible = actual is not None and (actual.cfg.ocultas, actual.cfg.pasos, actual.cfg.fisica, actual.cfg.arquitectura) == \
        (cfg.ocultas, cfg.pasos, cfg.fisica, cfg.arquitectura)
    previas = previas_familias = None
    if actual is not None:
        anterior = json.loads((_raiz_modelos(bufer) / actual.version / 'modelo.json').read_text(encoding='utf-8'))
        # También conserva el linaje acumulado: no basta mirar la última época.
        previas = anterior.get('ajuste_acumulado_ids')
        previas_familias = anterior.get('ajuste_acumulado_familias')
    independiente = (herencia_independiente(previas, particiones_ids)
                     and herencia_independiente(previas_familias, particiones_familias))
    compatible = compatible and independiente
    if actual is not None and not compatible:
        log('Gemelo: ajuste desde cero; arquitectura o genealogía no acreditan herencia independiente')
    x_all = np.concatenate([m.x for m in grupos['entrenamiento']])
    dominio = {'x_min': x_all.min(axis=0).tolist(), 'x_max': x_all.max(axis=0).tolist(),
               'nodos': [min(len(m.ids) for m in grupos['entrenamiento']),
                         max(len(m.ids) for m in grupos['entrenamiento'])],
               # 071:RF-1: la de prueba cuenta porque en ella se demuestra el error que abre la puerta.
               'redes': sorted({red_de(m) for ms in grupos.values() for m in ms})}
    dominio['version_grafo'] = VERSION_GRAFO                              # 045:RF-2
    estados, curvas, terminos = [], [], []
    for k in range(MIEMBROS):
        inicial = actual.estados[k] if compatible and k < len(actual.estados) else None
        log(f'Gemelo: entrenando el miembro {k + 1} de {MIEMBROS} en {dispositivo()}…')
        curvas.append([])
        terminos.append([])
        estados.append(entrenar_miembro(grupos['entrenamiento'],
                                        Entrenamiento(**{**cfg.__dict__, 'semilla': cfg.semilla + k}),
                                        inicial, log, validacion=grupos['validacion'],
                                        historial=curvas[-1], terminos=terminos[-1]))
    candidato = OraculoPINN(estados, cfg, dominio)
    # 060:RF-2: calibración apartada también de la selección por parada temprana.
    calibracion = grupos['calibracion']
    candidato.cuantil = calibrar_conforme(candidato, calibracion)
    evaluacion = grupos['prueba']
    error = mae(candidato, evaluacion)
    man = manifiesto(cfg, ids, grupos, candidato, actual.version if compatible else None)   # 027:RF-8
    man['sistema'] = sistema
    man['particiones_ids'] = particiones_ids
    man['particiones_familias'] = particiones_familias
    residuos = [float(np.mean(candidato.predecir(_grafo_de_muestra(m))['residuo'])) for m in evaluacion]
    dorados_m = [m for m, i in zip(muestras, ids, strict=True) if i in set(dorados)]
    error_dorados = mae(candidato, dorados_m) if dorados_m else None
    error_dorados_actual = mae(actual, dorados_m) if actual and dorados_m else None
    meta = {'consulta': consulta.__dict__, 'episodios': ids, 'mae_v': error, 'excluidos': excluidos,
            'terminos_por_epoca': terminos,                               # 045:RF-6
            'particiones_ids': particiones_ids,
            'ajuste_acumulado_ids': {k: sorted(set(particiones_ids[k]) | (set(previas[k]) if compatible else set()))
                                    for k in ('entrenamiento', 'validacion')},
            'ajuste_acumulado_familias': {k: sorted(set(particiones_familias[k]) |
                (set(previas_familias[k]) if compatible else set())) for k in ('entrenamiento', 'validacion')},
            'herencia': {'usada': compatible, 'independencia_acreditada': independiente},
            'residuo_medio': float(np.mean(residuos)), 'mae_dorados': error_dorados,
            'particiones': {k: len(v) for k, v in grupos.items()},
            # 027:RF-5: la mejor época de cada miembro y su curva de validación.
            'validacion': [{'mejor_epoca': min(c, key=lambda x: x[1])[0] if c else None,
                            'epocas': c[-1][0] + 1 if c else None, 'curva': c} for c in curvas],
            'manifiesto': man,
            'conforme': informe_conforme(candidato, calibracion, evaluacion)}
    candidato.cobertura_justificada = meta['conforme']['publicable']
    fallos = fallos_de_particion(grupos)                                 # 027:RF-3
    if error is None or error > puertas.mae_v_max:
        fallos.append(f'error de tensión {error} p.u. sobre {puertas.mae_v_max}')
    if meta['residuo_medio'] > puertas.residuo_max:
        fallos.append(f"residuo físico {meta['residuo_medio']:.3g} sobre {puertas.residuo_max}")
    # 071:RF-3, RF-4: en la misma prueba, frente al flujo físico y al modelo en uso.
    error_fisica = mae(ModeloMallado(exponente=cfg.exponente_carga), evaluacion)
    error_actual = mae(actual, evaluacion) if actual is not None else None
    fallos += fallos_de_comparacion(error, error_fisica, error_actual, puertas)
    if error_dorados_actual is not None and error_dorados is not None and \
            error_dorados > puertas.tolerancia_dorados * error_dorados_actual + 1e-6:
        fallos.append('empeora los casos dorados')
    # 044:RF-5: las de arriba miran la media; una familia pequeña que empeora no se ve en ella.
    metricas = {'global': {**_denominador(evaluacion), 'mae_v': error, 'residuo': meta['residuo_medio'],
                           'mae_fisica': error_fisica, 'mae_activo': error_actual},
                'familias': metricas_por_familia(candidato, evaluacion, residuos,
                                                 ModeloMallado(exponente=cfg.exponente_carga), actual)}
    veredicto = evaluar_candidato(metricas, politica)
    fallos += [b for b in veredicto['bloqueos'] if not b.startswith('global:')]
    # 044:RF-8: con esto, el manifiesto y los identificadores de cada partición se puede repetir la evaluación.
    meta['evaluacion'] = {
        'schema_version': 1, 'politica': asdict(politica), 'politica_hash': politica.hash,
        'alcance': alcance_de(politica), 'veredicto': veredicto,
        'unidades': {'mae_v': 'p.u.', 'residuo': 'p.u.', 'mae_fisica': 'p.u.', 'mae_activo': 'p.u.'},
        'agrupacion': AGRUPACION_DE_CUSTODIA,
        'denominadores': {k: _denominador(v) for k, v in grupos.items()}}
    carpeta = guardar(candidato, bufer, meta)
    # 043:RF-5: lo que se comprueba al reabrir; ``guardar`` ya dejó los pesos.
    if evaluacion:
        sonda = _grafo_de_muestra(evaluacion[0])
        (carpeta / 'readback.json').write_text(json.dumps(
            {'grafo': sonda, 'v': candidato.predecir(sonda)['v'].tolist()}, ensure_ascii=False, default=float), encoding='utf-8')
    decidido = _decidir_promocion(bufer, carpeta, {**meta, 'cfg': cfg.__dict__}, fallos,
                                  f'mae {error:.4g}' if error is not None else '', reabrir=reabrir, registro=registro)
    log(f"Gemelo: candidato {candidato.version}: {'promovido' if not fallos else 'no promovido: ' + '; '.join(fallos)}")
    return {'entrenado': True, 'version': candidato.version, 'carpeta': str(carpeta), **decidido,
            'modelo_registro': 'pinn', 'fallos': fallos, 'mae_fisica': error_fisica, 'mae_en_uso': error_actual,
            'evaluacion': meta['evaluacion'], 'conforme': meta['conforme'],
            **{k: meta[k] for k in ('mae_v', 'residuo_medio', 'particiones')}}


def evaluar(bufer: BuferEpisodios, consulta: Consulta | None = None) -> dict[str, Any]:
    """Si el oráculo aprendió: cuánto se apartan de DIgSILENT el modelo promovido y la física
    sola en cada episodio entrenable, y la media por partición (RF-74). Lo que importa es la
    partición de prueba, con familias que el modelo no vio al entrenar (RF-12).

    044:RF-8: las particiones son las que guardó el modelo. Calcularlas de nuevo daba por «prueba» y
    «validación» lo que el modelo con ``sistema`` usó de otro modo, y por validación su calibración.
    """
    muestras, ids = _muestras(bufer, consulta or Consulta())
    actual = cargar(bufer) if muestras else None
    fisica = ModeloMallado(exponente=actual.cfg.exponente_carga if actual else 0.0)
    filas = []
    meta = (json.loads((_raiz_modelos(bufer) / actual.version / 'modelo.json').read_text(encoding='utf-8'))
            if actual is not None else {})
    guardadas = meta.get('particiones_ids')
    if guardadas:
        parte_de_id = {i: p for p, lista in guardadas.items() for i in lista}
        parte_de = {id(m): parte_de_id.get(i, 'sin_asignar') for m, i in zip(muestras, ids, strict=True)}
    else:
        parte_de = {id(m): p for p, ms in particionar(muestras).items() for m in ms}     # 027:RF-2
    for m, i in zip(muestras, ids, strict=True):
        fila = {'episodio': i, 'particion': parte_de[id(m)], 'nodos': len(m.ids),
                'mae_fisica': mae(fisica, [m])}
        if actual is not None:
            fila['mae_modelo'] = mae(actual, [m])
        filas.append(fila)
    resumen: dict[str, dict[str, float]] = {}
    for parte in ('entrenamiento', 'validacion', 'calibracion', 'prueba', 'sin_asignar'):
        sel = [f for f in filas if f['particion'] == parte]
        if sel:
            resumen[parte] = {'episodios': len(sel), 'mae_fisica': float(np.mean([f['mae_fisica'] for f in sel]))}
            if actual is not None:
                resumen[parte]['mae_modelo'] = float(np.mean([f['mae_modelo'] for f in sel]))
    return {'modelo': actual.version if actual else None, 'por_particion': resumen, 'episodios': filas,
            'unidades': {'mae_fisica': 'p.u.', 'mae_modelo': 'p.u.'},
            'reparto': 'guardado con el modelo' if guardadas else 'calculado ahora: el modelo no guardó el suyo',
            'politica_hash': (meta.get('evaluacion') or {}).get('politica_hash')}


def deriva(bufer: BuferEpisodios, nuevos: Sequence[str], puertas: Puertas | None = None) -> bool:
    """El modelo en uso ya no reproduce lo nuevo: error al doble del umbral (RF-43)."""
    puertas = puertas or Puertas()
    actual = cargar(bufer)
    if actual is None:
        return False
    muestras = [m for e in (bufer.leer(i) for i in nuevos) if (m := muestra_de_episodio(e)) is not None]
    error = mae(actual, muestras)
    return error is not None and error > 2 * puertas.mae_v_max


def deriva_por_familia(bufer: BuferEpisodios, *, minimo: int = 10, fraccion: float = 0.2) -> dict[str, Any]:
    """Por familia, los episodios que el modelo en uso no vio y cuántos están fuera de su
    dominio (027:RF-22); propone reentrenar si una familia sale del dominio, trae al menos
    ``minimo`` episodios nuevos o un ``fraccion`` más que los suyos de entrenamiento (RF-23)."""
    muestras, ids = _muestras(bufer, Consulta())
    actual = cargar(bufer)
    vistos: set[str] = set()
    if actual is not None:
        meta = json.loads((_raiz_modelos(bufer) / actual.version / 'modelo.json').read_text(encoding='utf-8'))
        vistos = set(meta.get('episodios') or [])
    familias: dict[str, dict[str, int]] = {}
    for m, i in zip(muestras, ids, strict=True):
        f = familias.setdefault(m.familia or '—', {'entrenamiento': 0, 'nuevos': 0, 'fuera_de_dominio': 0})
        if i in vistos:
            f['entrenamiento'] += 1
            continue
        f['nuevos'] += 1
        if actual is not None and actual.fuera_de_dominio(m):
            f['fuera_de_dominio'] += 1
    motivos = []
    for nombre, f in sorted(familias.items()):
        if f['fuera_de_dominio']:
            motivos.append(f"{nombre}: {f['fuera_de_dominio']} episodio(s) fuera del dominio del modelo")
        elif f['nuevos'] >= minimo:
            motivos.append(f"{nombre}: {f['nuevos']} episodios nuevos")
        elif f['nuevos'] and f['entrenamiento'] and f['nuevos'] >= fraccion * f['entrenamiento']:
            motivos.append(f"{nombre}: {f['nuevos']} nuevos, más del {fraccion:.0%} de sus {f['entrenamiento']}")
    return {'modelo': actual.version if actual else None, 'familias': familias,
            'proponer_reentrenar': bool(motivos), 'motivos': motivos}


def entrenar_si_toca(bufer: BuferEpisodios, *, minimo: int = 10,
                     log: Callable[[str], None] = lambda _m: None, registro=None) -> dict[str, Any]:
    """Reentrena solo cuando hay episodios nuevos que el modelo en uso no vio (RF-39), o
    antes si los nuevos muestran deriva (RF-43)."""
    _muestras_todas, ids = _muestras(bufer, Consulta())
    vistos: set[str] = set()
    raiz = _raiz_modelos(bufer)
    if (raiz / 'promovido.json').is_file():
        version = json.loads((raiz / 'promovido.json').read_text(encoding='utf-8'))['version']
        vistos = set(json.loads((raiz / version / 'modelo.json').read_text(encoding='utf-8'))['episodios'])
    nuevos = [i for i in ids if i not in vistos]
    if not nuevos:
        return {'entrenado': False, 'motivo': 'sin episodios nuevos'}
    if len(nuevos) < minimo and not deriva(bufer, nuevos):
        return {'entrenado': False, 'motivo': f'{len(nuevos)} episodio(s) nuevo(s), se espera a {minimo}'}
    return entrenar(bufer, log=log, registro=registro)


# ------------------------------------------------------------------ uso del oráculo
def perturbar(grafo: Mapping[str, Any], escenario: Escenario) -> dict:
    """El grafo con la demanda escalada y los tramos del escenario abiertos."""
    nodos = {n: escalar_nodo(d, escenario.factor_carga) for n, d in (grafo.get('nodos') or {}).items()}
    abiertos = set(escenario.tramos_abiertos)
    ramas = [{**r, 'cerrada': r.get('cerrada', True) and not any(
        str(r.get('id', '')).endswith(f'\\{t}.ElmLne') or str(r.get('id')) == t for t in abiertos)}
        for r in grafo.get('ramas') or []]
    return {**grafo, 'nodos': nodos, 'ramas': ramas}


def incertidumbre_de_escenarios(grafo: Mapping[str, Any], bufer: BuferEpisodios | None = None):
    """La función de incertidumbre del modelo en uso para el aprendizaje activo (RF-40), o
    ``None`` si aún no hay modelo."""
    bufer = bufer or BuferEpisodios()
    oraculo = cargar(bufer)
    if oraculo is None or not grafo:
        return None

    def incertidumbre(e: Escenario) -> float:
        p = oraculo.predecir(perturbar(grafo, e))
        return float(np.mean(p['incertidumbre'])) + (1.0 if p['fuera_de_dominio'] else 0.0)

    return incertidumbre


def ordenar_candidatos(modelo: Modelo, grafo: Mapping[str, Any], candidatos: Sequence[Mapping[str, Any]],
                       tension_min_pu: float) -> list[dict[str, Any]]:
    """Ordena obras candidatas con el oráculo antes de confirmarlas en DIgSILENT (RF-23,
    RF-35, RF-36): primero las que dejan menos barras bajo la norma, luego la mayor mínima
    y la menor incertidumbre. Ninguna se escribe en el proyecto aquí.

    Un candidato: ``{'codigo', 'nodo', 'q_mvar'}`` (banco) o ``{'codigo', 'rama', 'factor_z'}``
    (cambio de sección o terna: la impedancia de la rama por ese factor).
    """
    out = []
    for c in candidatos:
        g = {**grafo, 'nodos': {n: dict(d) for n, d in (grafo.get('nodos') or {}).items()},
             'ramas': [dict(r) for r in grafo.get('ramas') or []]}
        if c.get('nodo') in g['nodos']:
            nodo = g['nodos'][c['nodo']]
            nodo['q_mvar'] = (nodo.get('q_mvar') or 0) - float(c.get('q_mvar') or 0)
            if 'banco_q_mvar' in nodo:                                    # 045:RF-3: es un banco, no una carga
                nodo['banco_q_mvar'] = float(nodo['banco_q_mvar'] or 0) + float(c.get('q_mvar') or 0)
        for r in g['ramas']:
            if c.get('rama') and r.get('id') == c['rama']:
                r['r_ohm'] = r['r_ohm'] * float(c.get('factor_z') or 1)
                r['x_ohm'] = r['x_ohm'] * float(c.get('factor_z') or 1)
        p = modelo.predecir(g)
        v = np.asarray(p['v'])
        energizados = v > 0
        out.append({**c, 'bajo_norma': int(np.sum(energizados & (v < tension_min_pu))),
                    'v_min': float(v[energizados].min()) if energizados.any() else 0.0,
                    'incertidumbre': float(np.mean(p['incertidumbre'])),
                    'fuera_de_dominio': bool(p['fuera_de_dominio']), 'confirmar_en_pf': True})
    return sorted(out, key=lambda c: (c['fuera_de_dominio'], c['bajo_norma'], -c['v_min'], c['incertidumbre']))
