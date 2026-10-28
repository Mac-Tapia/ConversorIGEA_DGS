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

import hashlib
import json
import math
import os
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .buffer import BuferEpisodios, Consulta
from .episode import Clase, Episodio
from .escenarios import Escenario, familia, particion

#: Potencia base del sistema por unidad (MVA).
S_BASE = 10.0
#: Versión del grafo de ``tools/escenarios_pf.py``. La 2 trae los acopladores y la consigna
#: de las fuentes; los episodios con un grafo anterior no enseñan (sin acopladores, la red
#: real quedaba casi entera sin fuente).
VERSION_GRAFO = 2
#: Clases que enseñan tensiones (RF-14: las violaciones y rechazos, no como objetivo).
CLASES_OBJETIVO = (Clase.ACCEPTED.value, Clase.COUNTERFACTUAL.value)
#: Miembros del conjunto: la desviación entre ellos es la incertidumbre (RF-15).
MIEMBROS = 3
#: Tope de la impedancia de una rama en p.u. (r y x): un acoplador cerrado, sin impedancia en el
#: grafo. Cambiarlo invalida los pesos entrenados con el anterior (027:RF-31).
Z_ACOPLADOR_PU = 1e-6


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


def muestra(grafo: Mapping[str, Any], tensiones: Mapping[str, float] | None = None,
            familia_: str = '') -> Muestra:
    """Pasa el grafo de ``tools/escenarios_pf.py`` a arrays por unidad."""
    nodos = grafo.get('nodos') or {}
    ids = sorted(nodos)
    pos = {n: i for i, n in enumerate(ids)}
    kv = np.array([float(nodos[n].get('kv') or 1.0) for n in ids])
    p = np.array([float(nodos[n].get('p_mw') or 0.0) for n in ids]) / S_BASE
    q = np.array([float(nodos[n].get('q_mvar') or 0.0) for n in ids]) / S_BASE
    fuente = np.array([bool(nodos[n].get('fuente')) for n in ids])
    # Consigna de la fuente: la del grafo o, en episodios anteriores, la tensión medida en ella.
    consigna = np.array([float(nodos[n].get('v_pu') or (tensiones or {}).get(n) or 1.0) if fuente[i] else 0.0
                         for i, n in enumerate(ids)])
    x = np.stack([np.log10(np.maximum(kv, 1e-3)), p, q, fuente.astype(float), consigna], axis=1)
    origen, destino, z, inom, ramas = [], [], [], [], []
    for r in grafo.get('ramas') or []:
        a, b = pos.get(r.get('desde')), pos.get(r.get('hasta'))
        if a is None or b is None or not r.get('cerrada', True):
            continue
        z_base = kv[a] ** 2 / S_BASE
        zz = complex(float(r.get('r_ohm') or 0.0), float(r.get('x_ohm') or 0.0)) / z_base
        if abs(zz) < Z_ACOPLADOR_PU:
            zz = complex(Z_ACOPLADOR_PU, Z_ACOPLADOR_PU)       # acoplador cerrado
        i_base = S_BASE / (math.sqrt(3) * kv[a])
        for u, w in ((a, b), (b, a)):
            origen.append(u)
            destino.append(w)
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
    if tensiones is not None:
        v = np.array([float(tensiones.get(n, 0.0)) for n in ids])
        mascara = np.array([n in tensiones for n in ids])
    return Muestra(ids, x, np.array([origen, destino], dtype=np.int64).reshape(2, -1),
                   np.array(z, dtype=complex), np.array(inom), ramas, p + 1j * q, fuente, v, mascara,
                   familia_, alimentado)


def muestra_de_episodio(e: Episodio) -> Muestra | None:
    """La muestra de un episodio con grafo y tensiones; ``None`` si no los trae."""
    grafo = (e.topologia or {}).get('grafo')
    tens = (e.flujo.get('tensiones') or {}).get('valores')
    if not grafo or not tens or grafo.get('version') != VERSION_GRAFO:
        return None
    return muestra(grafo, tens, familia({'nativo': e.nativo, 'accion': e.accion, 'topologia': e.topologia}))


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
    corriente = np.zeros(len(m.ids), dtype=complex)
    np.add.at(corriente, a, (vc[a] - vc[b]) / m.z[real])
    s_nodo = vc * np.conj(corriente) + m.s_carga * np.abs(v) ** exponente   # sale + carga = 0
    s_barra = np.zeros(n, dtype=complex)
    np.add.at(s_barra, grupo, s_nodo)
    return np.where(exigir, np.abs(s_barra), 0.0)[grupo]


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
        vecinos: list[list[tuple[int, complex]]] = [[] for _ in range(n)]
        for k in range(m.aristas.shape[1]):
            vecinos[m.aristas[0, k]].append((int(m.aristas[1, k]), m.z[k]))
        padre, zpadre, orden = [-1] * n, [0j] * n, []
        visto = [False] * n
        for s in np.flatnonzero(m.fuente):
            pila = [int(s)]
            visto[s] = True
            while pila:
                u = pila.pop()
                orden.append(u)
                for w, zz in vecinos[u]:
                    if not visto[w]:
                        visto[w], padre[w], zpadre[w] = True, u, zz
                        pila.append(w)
        vc = np.where(m.fuente, m.x[:, 4], 1.0).astype(complex)   # las fuentes, en su consigna
        for _ in range(self.iteraciones):
            i_nodo = np.conj(m.s_carga * np.abs(vc) ** self.exponente / vc)
            i_rama = i_nodo.copy()
            for u in reversed(orden):
                if padre[u] >= 0:
                    i_rama[padre[u]] += i_rama[u]
            nuevo = vc.copy()
            for u in orden:
                if padre[u] >= 0:
                    nuevo[u] = nuevo[padre[u]] - zpadre[u] * i_rama[u]
            if np.max(np.abs(nuevo - vc)) < 1e-9:
                vc = nuevo
                break
            vc = nuevo
        v = np.where(visto, np.abs(vc), 0.0)
        return {'ids': m.ids, 'v': v, 'theta': np.where(visto, np.angle(vc), 0.0),
                'incertidumbre': np.zeros(n), 'residuo': residuo(m, v, np.angle(vc), self.exponente),
                'fuera_de_dominio': False, 'modelo': self.nombre}


def sistema_de(m: Muestra):
    """La red de la muestra factorizada para el flujo mallado, construida una sola vez."""
    if m.sistema is None:
        from .flujo import SistemaMallado

        m.sistema = SistemaMallado(m.aristas, m.z, m.fuente, m.x[:, 4], m.alimentado)
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
                'residuo': residuo(m, v, th, self.exponente), 'fuera_de_dominio': not sol.convergio,
                'motivos': [] if sol.convergio else ['el flujo físico no converge'],
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
    entrada = (7 * h + h) + (h * h + h)
    por_paso = ((2 * h + 3) * h + h) + (h * h + h) + (6 * h * h + 6 * h)   # mensaje y GRUCell
    salida = (h * h + h) + (2 * h + 2)
    return entrada + k * por_paso + salida


def _red(ocultas: int = 64, pasos: int = 8):
    """GNN: codifica nodos, pasa mensajes ``pasos`` veces por las ramas y da (ΔV, θ)."""
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
            # En la fuente la tensión es su consigna: dato, no predicción.
            es_fuente = x[:, 3] > 0.5
            return torch.where(es_fuente, x[:, 4], v), th

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


def _fisica(m: Muestra, disp, exponente: float = 0.0) -> dict:
    """Tensores fijos de la pérdida física de una muestra, creados una sola vez.

    Crearlos en cada paso agotó la memoria con IN111–TA225 (2470 nodos, 2026-10-22: «CUDA
    error: Memory allocation failure» con 1,3 GB de RAM libre) y tumbó la web.
    """
    torch = _torch()
    grupo, real, exigir, n = barras_electricas(m)
    z = m.z[real]
    return {'a': torch.tensor(m.aristas[0][real], device=disp), 'b': torch.tensor(m.aristas[1][real], device=disp),
            'zr': torch.tensor(z.real, dtype=torch.float32, device=disp),
            'zi': torch.tensor(z.imag, dtype=torch.float32, device=disp),
            'sp': torch.tensor(m.s_carga.real, dtype=torch.float32, device=disp),
            'sq': torch.tensor(m.s_carga.imag, dtype=torch.float32, device=disp),
            'grupo': torch.tensor(grupo, dtype=torch.long, device=disp), 'n': n,
            'exigir': torch.tensor(exigir, device=disp), 'exponente': exponente}


def _residuo_torch(f: dict, v, theta):
    """El balance de cada barra eléctrica (``barras_electricas``), al cuadrado."""
    torch = _torch()
    a, b, zr, zi = f['a'], f['b'], f['zr'], f['zi']
    vr, vi = v * torch.cos(theta), v * torch.sin(theta)
    dr, di = vr[a] - vr[b], vi[a] - vi[b]
    den = zr * zr + zi * zi
    ir, ii = (dr * zr + di * zi) / den, (di * zr - dr * zi) / den
    i_r = torch.zeros_like(v).index_add_(0, a, ir)
    i_i = torch.zeros_like(v).index_add_(0, a, ii)
    e = v.abs() ** f['exponente']
    p = vr * i_r + vi * i_i + f['sp'] * e
    q = vi * i_r - vr * i_i + f['sq'] * e
    pb = torch.zeros(f['n'], dtype=v.dtype, device=v.device).index_add_(0, f['grupo'], p)
    qb = torch.zeros(f['n'], dtype=v.dtype, device=v.device).index_add_(0, f['grupo'], q)
    return (pb ** 2 + qb ** 2)[f['exigir']]


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


def entrenar_miembro(muestras: Sequence[Muestra], cfg: Entrenamiento, inicial: dict | None = None,
                     log: Callable[[str], None] = lambda _m: None, validacion: Sequence[Muestra] = (),
                     historial: list | None = None):
    """Un miembro del conjunto: error frente a DIgSILENT + residuo físico (PINN).

    Con ``validacion``, para tras ``cfg.paciencia`` épocas sin mejorar y devuelve los pesos de
    la mejor época (027:RF-5); ``historial`` recibe ``(época, mae de validación)``.
    """
    torch = _torch()
    try:
        return _entrenar_en(muestras, cfg, inicial, log, dispositivo(), validacion,
                            historial if historial is not None else [])
    finally:
        torch.cuda.empty_cache()     # cada miembro devuelve la memoria de la GPU


def _entrenar_en(muestras: Sequence[Muestra], cfg: Entrenamiento, inicial: dict | None,
                 log: Callable[[str], None], disp, validacion: Sequence[Muestra] = (),
                 historial: list | None = None):
    torch = _torch()
    # 027:RF-9: mismo manifiesto, misma GPU, mismo modelo. ``index_add_`` en CUDA no tiene
    # versión determinista: se avisa en vez de fallar y la prueba mide la diferencia.
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(cfg.semilla)
    random.seed(cfg.semilla)
    red = _red(cfg.ocultas, cfg.pasos).to(disp)
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
        for f, x, ar, e, v, mask in datos:
            vp, th = red(x, ar, e)
            perdida = ((vp - v)[mask] ** 2).mean() + cfg.peso_fisico * _residuo_torch(f, vp, th).mean()
            opt.zero_grad()
            perdida.backward()
            torch.nn.utils.clip_grad_norm_(red.parameters(), cfg.recorte)
            opt.step()
            total += float(perdida.detach())
        plan.step()
        if epoca % 100 == 0:
            log(f'  época {epoca}: pérdida {total / max(len(datos), 1):.3e}')
        if val and (epoca % cfg.cada == 0 or epoca == cfg.epocas - 1):
            red.eval()
            with torch.no_grad():
                err = float(np.mean([float((red(x, ar, e)[0] - v)[mask].abs().mean()) for x, ar, e, v, mask in val]))
            red.train()
            historial.append((epoca, err))
            if err < mejor - 1e-9:
                mejor, mejor_epoca = err, epoca
                mejor_estado = {k: v.detach().clone() for k, v in red.state_dict().items()}
            elif epoca - mejor_epoca >= cfg.paciencia:
                log(f'  parada temprana en la época {epoca}: la mejor fue la {mejor_epoca} ({mejor:.3e} p.u.)')
                break
    final = mejor_estado if mejor_estado is not None else red.state_dict()
    return {k: v.detach().cpu() for k, v in final.items()}


@dataclass
class OraculoPINN:
    """Conjunto de GNN con su dominio (RF-15, RF-19)."""

    estados: list[dict]
    cfg: Entrenamiento
    dominio: dict[str, Any]
    nombre: str = 'pinn_gnn'
    version: str = ''

    def _redes(self):
        disp = dispositivo()
        out = []
        for s in self.estados:
            red = _red(self.cfg.ocultas, self.cfg.pasos).to(disp)
            red.load_state_dict(s)
            red.eval()
            out.append(red)
        return out, disp

    def fuera_de_dominio(self, m: Muestra) -> list[str]:
        """Motivos por los que esta red está fuera de lo aprendido (RF-19)."""
        motivos = []
        lo, hi = np.array(self.dominio['x_min']), np.array(self.dominio['x_max'])
        margen = 0.1 * np.maximum(hi - lo, 1e-6)
        fuera = (m.x < lo - margen) | (m.x > hi + margen)
        if fuera.any():
            motivos.append(f'{int(fuera.any(axis=1).sum())} nodo(s) con datos fuera de lo aprendido')
        n_min, n_max = self.dominio['nodos']
        if not 0.5 * n_min <= len(m.ids) <= 2 * n_max:
            motivos.append(f'{len(m.ids)} nodos frente a {n_min}–{n_max} aprendidos')
        return motivos

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]:
        torch = _torch()
        m = muestra(grafo)
        redes, disp = self._redes()
        x, ar, e = _tensores(m, disp, self.cfg.exponente_carga, self.cfg.fisica)
        with torch.no_grad():
            salidas = [red(x, ar, e) for red in redes]
        vs = np.stack([s[0].cpu().numpy() for s in salidas])
        ths = np.stack([s[1].cpu().numpy() for s in salidas])
        v, th = vs.mean(axis=0), ths.mean(axis=0)
        motivos = self.fuera_de_dominio(m)
        return {'ids': m.ids, 'v': v, 'theta': th, 'incertidumbre': vs.std(axis=0),
                'residuo': residuo(m, v, th, self.cfg.exponente_carga), 'fuera_de_dominio': bool(motivos),
                'motivos': motivos,
                'modelo': self.nombre, 'version': self.version}


def estado_electrico(prediccion: Mapping[str, Any], grafo: Mapping[str, Any]) -> dict[str, Any]:
    """Tensiones, flujos, pérdidas y cargabilidad de una predicción (RF-18).

    Fuera de dominio no se da como verdad: se pide el cálculo a DIgSILENT (RF-19).
    """
    if prediccion.get('fuera_de_dominio'):
        return {'requiere_pf': True, 'motivos': prediccion.get('motivos') or []}
    m = muestra(grafo)
    vc = np.asarray(prediccion['v']) * np.exp(1j * np.asarray(prediccion['theta']))
    a, b = m.aristas
    i = (vc[a] - vc[b]) / m.z
    perdidas = float(np.sum(np.abs(i) ** 2 * m.z.real) / 2 * S_BASE)
    carga = {}
    for k, rama in enumerate(m.ramas):
        if m.inom[k] > 0:
            carga[rama] = max(carga.get(rama, 0.0), 100 * abs(i[k]) / m.inom[k])
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
                    'fuente': bool(m.fuente[i]), 'v_pu': float(m.x[i, 4]) if m.fuente[i] else None}
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
                      'inom_ka': m.inom[k] * i_base})
    return {'nodos': nodos, 'ramas': ramas}


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
    torch = _torch()
    raiz = _raiz_modelos(bufer)
    if version is None:
        puntero = raiz / 'promovido.json'
        if not puntero.is_file():
            return None
        version = json.loads(puntero.read_text(encoding='utf-8'))['version']
    carpeta = raiz / version
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    estados = [torch.load(carpeta / f'miembro_{i}.pt', weights_only=True) for i in range(meta['miembros'])]
    # Los modelos de antes del 2026-10-24 se entrenaron sobre el barrido radial.
    cfg = Entrenamiento(**{'fisica': 'radial', **meta['cfg']})
    return OraculoPINN(estados, cfg, meta['dominio'], version=version)


def promover(bufer: BuferEpisodios, version: str, motivo: str) -> None:
    """Pasa a ser el modelo en uso; el historial guarda cada cambio (RF-42)."""
    raiz = _raiz_modelos(bufer)
    anterior = None
    if (raiz / 'promovido.json').is_file():
        anterior = json.loads((raiz / 'promovido.json').read_text(encoding='utf-8'))['version']
    fila = {'version': version, 'anterior': anterior, 'motivo': motivo,
            'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
    tmp = raiz / 'promovido.json.tmp'
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


def _muestras(bufer: BuferEpisodios, consulta: Consulta) -> tuple[list[Muestra], list[str]]:
    muestras, ids = [], []
    for e in bufer.consultar(consulta):
        if e.clase.value not in CLASES_OBJETIVO:
            continue
        m = muestra_de_episodio(e)
        if m is not None:
            muestras.append(m)
            ids.append(e.episode_id)
    return muestras, ids


#: Episodios de prueba de otra red sin los que no se promueve (027:RF-3; usuario, 2026-10-28).
MIN_EPISODIOS_PRUEBA = 10


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


def fallos_de_particion(grupos: Mapping[str, Sequence[Muestra]]) -> list[str]:
    """Lo que impide promover por el reparto (027:RF-3)."""
    if not grupos['prueba']:
        return ['sin una red de prueba distinta de las de entrenamiento: hace falta otro sistema '
                '(027:RF-3)']
    if len(grupos['prueba']) < MIN_EPISODIOS_PRUEBA:
        return [f"{len(grupos['prueba'])} episodios de prueba de otra red, menos de "
                f'{MIN_EPISODIOS_PRUEBA} (027:RF-3)']
    return []


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
    evaluacion = grupos.get('prueba') or grupos.get('validacion') or grupos.get('entrenamiento') or []
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
    muestras = [m for m in (muestra_de_episodio(bufer.leer(i)) for i in man['episodios']) if m is not None]
    cfg = Entrenamiento(**man['cfg'])
    grupos = particionar(muestras)
    if not grupos['entrenamiento']:
        grupos['entrenamiento'] = list(grupos['validacion'])
    inicial = cargar(bufer, man['parte_de']) if man.get('parte_de') else None
    estados = [entrenar_miembro(grupos['entrenamiento'], Entrenamiento(**{**cfg.__dict__, 'semilla': s}),
                                inicial.estados[k] if inicial and k < len(inicial.estados) else None,
                                log, validacion=grupos['validacion'])
               for k, s in enumerate(man['semillas'])]
    candidato = OraculoPINN(estados, cfg, meta['dominio'])
    evaluacion = grupos['prueba'] or grupos['validacion'] or grupos['entrenamiento']
    error = mae(candidato, evaluacion)
    diferencia = abs((error or 0.0) - (meta.get('mae_v') or 0.0))
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    return {'version': version, 'mae_original': meta.get('mae_v'), 'mae_reproducido': error,
            'diferencia': diferencia, 'reproducible': diferencia < TOLERANCIA_REPRODUCCION,
            'mismo_commit': man.get('commit') == _commit(), 'misma_gpu': man.get('dispositivo') == gpu}


def entrenar(bufer: BuferEpisodios, *, consulta: Consulta | None = None, cfg: Entrenamiento | None = None,
             puertas: Puertas | None = None, dorados: Sequence[str] = (),
             log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Entrena un candidato con una consulta fija del búfer, lo evalúa por particiones de
    familia y lo promueve si supera las puertas sin empeorar los dorados (RF-12, RF-13,
    RF-16, RF-17, RF-42). Si ya hay modelo, parte de sus pesos y repite el histórico entero
    (RF-17, RF-43): ajuste fino, no desde cero."""
    consulta = consulta or Consulta()
    puertas = puertas or Puertas()
    muestras, ids = _muestras(bufer, consulta)
    if not muestras:
        return {'entrenado': False, 'motivo': 'no hay episodios con grafo y tensiones'}
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
    grupos = particionar(muestras)                                       # 027:RF-2
    if not grupos['entrenamiento']:
        grupos['entrenamiento'] = list(grupos['validacion'])
    actual = cargar(bufer)
    # Sin configuración, la del modelo en uso; sus pesos solo valen con la misma arquitectura.
    cfg = cfg or (actual.cfg if actual else Entrenamiento())
    # Un modelo en uso sobre el barrido radial no fija la física del candidato: la mallada lo sustituye.
    cfg = Entrenamiento(**{**cfg.__dict__, 'fisica': 'mallado'})
    cfg = Entrenamiento(**{**cfg.__dict__,
                           'exponente_carga': elegir_exponente(grupos['entrenamiento'], fisica=cfg.fisica)})
    log(f'Gemelo: física {cfg.fisica}, modelo de carga S0·|V|^{cfg.exponente_carga:g}')
    compatible = actual is not None and (actual.cfg.ocultas, actual.cfg.pasos, actual.cfg.fisica) == \
        (cfg.ocultas, cfg.pasos, cfg.fisica)
    x_all = np.concatenate([m.x for m in grupos['entrenamiento']])
    dominio = {'x_min': x_all.min(axis=0).tolist(), 'x_max': x_all.max(axis=0).tolist(),
               'nodos': [min(len(m.ids) for m in grupos['entrenamiento']),
                         max(len(m.ids) for m in grupos['entrenamiento'])]}
    estados, curvas = [], []
    for k in range(MIEMBROS):
        inicial = actual.estados[k] if compatible and k < len(actual.estados) else None
        log(f'Gemelo: entrenando el miembro {k + 1} de {MIEMBROS} en {dispositivo()}…')
        curvas.append([])
        estados.append(entrenar_miembro(grupos['entrenamiento'],
                                        Entrenamiento(**{**cfg.__dict__, 'semilla': cfg.semilla + k}),
                                        inicial, log, validacion=grupos['validacion'],
                                        historial=curvas[-1]))
    candidato = OraculoPINN(estados, cfg, dominio)
    evaluacion = grupos['prueba'] or grupos['validacion'] or grupos['entrenamiento']
    error = mae(candidato, evaluacion)
    man = manifiesto(cfg, ids, grupos, candidato, actual.version if compatible else None)   # 027:RF-8
    residuos = [float(np.mean(candidato.predecir(_grafo_de_muestra(m))['residuo'])) for m in evaluacion]
    dorados_m = [m for m, i in zip(muestras, ids, strict=True) if i in set(dorados)]
    error_dorados = mae(candidato, dorados_m) if dorados_m else None
    error_dorados_actual = mae(actual, dorados_m) if actual and dorados_m else None
    meta = {'consulta': consulta.__dict__, 'episodios': ids, 'mae_v': error,
            'residuo_medio': float(np.mean(residuos)), 'mae_dorados': error_dorados,
            'particiones': {k: len(v) for k, v in grupos.items()},
            # 027:RF-5: la mejor época de cada miembro y su curva de validación.
            'validacion': [{'mejor_epoca': min(c, key=lambda x: x[1])[0] if c else None,
                            'epocas': c[-1][0] + 1 if c else None, 'curva': c} for c in curvas],
            'manifiesto': man}
    carpeta = guardar(candidato, bufer, meta)
    fallos = fallos_de_particion(grupos)                                 # 027:RF-3
    if error is None or error > puertas.mae_v_max:
        fallos.append(f'error de tensión {error} p.u. sobre {puertas.mae_v_max}')
    if meta['residuo_medio'] > puertas.residuo_max:
        fallos.append(f"residuo físico {meta['residuo_medio']:.3g} sobre {puertas.residuo_max}")
    if error_dorados_actual is not None and error_dorados is not None and \
            error_dorados > puertas.tolerancia_dorados * error_dorados_actual + 1e-6:
        fallos.append('empeora los casos dorados')
    if not fallos:
        promover(bufer, candidato.version, f'mae {error:.4g}')
    log(f"Gemelo: candidato {candidato.version}: {'promovido' if not fallos else 'no promovido: ' + '; '.join(fallos)}")
    return {'entrenado': True, 'version': candidato.version, 'carpeta': str(carpeta),
            'promovido': not fallos, 'fallos': fallos, **{k: meta[k] for k in ('mae_v', 'residuo_medio', 'particiones')}}


def evaluar(bufer: BuferEpisodios, consulta: Consulta | None = None) -> dict[str, Any]:
    """Si el oráculo aprendió: cuánto se apartan de DIgSILENT el modelo promovido y la física
    sola en cada episodio entrenable, y la media por partición (RF-74). Lo que importa es la
    partición de prueba, con familias que el modelo no vio al entrenar (RF-12)."""
    muestras, ids = _muestras(bufer, consulta or Consulta())
    actual = cargar(bufer) if muestras else None
    fisica = ModeloMallado(exponente=actual.cfg.exponente_carga if actual else 0.0)
    filas = []
    grupos = particionar(muestras)                                       # 027:RF-2
    parte_de = {id(m): p for p, ms in grupos.items() for m in ms}
    for m, i in zip(muestras, ids, strict=True):
        fila = {'episodio': i, 'particion': parte_de[id(m)], 'nodos': len(m.ids),
                'mae_fisica': mae(fisica, [m])}
        if actual is not None:
            fila['mae_modelo'] = mae(actual, [m])
        filas.append(fila)
    resumen: dict[str, dict[str, float]] = {}
    for parte in ('entrenamiento', 'validacion', 'prueba'):
        sel = [f for f in filas if f['particion'] == parte]
        if sel:
            resumen[parte] = {'episodios': len(sel), 'mae_fisica': float(np.mean([f['mae_fisica'] for f in sel]))}
            if actual is not None:
                resumen[parte]['mae_modelo'] = float(np.mean([f['mae_modelo'] for f in sel]))
    return {'modelo': actual.version if actual else None, 'por_particion': resumen, 'episodios': filas}


def deriva(bufer: BuferEpisodios, nuevos: Sequence[str], puertas: Puertas | None = None) -> bool:
    """El modelo en uso ya no reproduce lo nuevo: error al doble del umbral (RF-43)."""
    puertas = puertas or Puertas()
    actual = cargar(bufer)
    if actual is None:
        return False
    muestras = [m for e in (bufer.leer(i) for i in nuevos) if (m := muestra_de_episodio(e)) is not None]
    error = mae(actual, muestras)
    return error is not None and error > 2 * puertas.mae_v_max


def entrenar_si_toca(bufer: BuferEpisodios, *, minimo: int = 10,
                     log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
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
    return entrenar(bufer, log=log)


# ------------------------------------------------------------------ uso del oráculo
def perturbar(grafo: Mapping[str, Any], escenario: Escenario) -> dict:
    """El grafo con la demanda escalada y los tramos del escenario abiertos."""
    nodos = {n: {**d, 'p_mw': (d.get('p_mw') or 0) * escenario.factor_carga,
                 'q_mvar': (d.get('q_mvar') or 0) * escenario.factor_carga}
             for n, d in (grafo.get('nodos') or {}).items()}
    abiertos = set(escenario.tramos_abiertos)
    ramas = [{**r, 'cerrada': r.get('cerrada', True) and not any(
        str(r.get('id', '')).endswith(f'\\{t}.ElmLne') or str(r.get('id')) == t for t in abiertos)}
        for r in grafo.get('ramas') or []]
    return {'nodos': nodos, 'ramas': ramas}


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
        g = {'nodos': {n: dict(d) for n, d in (grafo.get('nodos') or {}).items()},
             'ramas': [dict(r) for r in grafo.get('ramas') or []]}
        if c.get('nodo') in g['nodos']:
            g['nodos'][c['nodo']]['q_mvar'] = (g['nodos'][c['nodo']].get('q_mvar') or 0) - float(c.get('q_mvar') or 0)
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
