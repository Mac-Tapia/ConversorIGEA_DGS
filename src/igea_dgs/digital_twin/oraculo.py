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


class Modelo(Protocol):
    """Contrato de un oráculo: el de la PINN y el de cualquier otro modelo (RF-38)."""

    nombre: str

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]: ...


# ------------------------------------------------------------------ grafo → tensores
@dataclass
class Muestra:
    ids: list[str]
    x: np.ndarray            # nodos × 4: kV relativo, P pu, Q pu, fuente
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
    base: np.ndarray | None = None        # V y θ del barrido físico (``_con_base``)
    base_exponente: float | None = None


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
        if abs(zz) < 1e-6:
            zz = complex(1e-6, 1e-6)       # acoplador cerrado
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
def residuo(m: Muestra, v: np.ndarray, theta: np.ndarray, exponente: float = 0.0) -> np.ndarray:
    """Desbalance de potencia de cada nodo (pu) con la tensión dada; 0 en las fuentes.

    Las cargas consumen S0·|V|^exponente: 0 potencia, 1 corriente, 2 impedancia constante.
    """
    vc = v * np.exp(1j * theta)
    a, b = m.aristas
    corriente = np.zeros(len(m.ids), dtype=complex)
    np.add.at(corriente, a, (vc[a] - vc[b]) / m.z)
    s_calc = vc * np.conj(corriente)          # lo que sale del nodo hacia la red
    r = np.abs(s_calc + m.s_carga * np.abs(v) ** exponente)   # sale + carga = 0
    r[m.fuente | ~m.alimentado] = 0.0
    return r


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


def dispositivo():
    """La GPU CUDA, siempre (usuario, 2026-10-22: «sí o sí debe conectar a GPU para no usar
    el CPU»). Sin ella, un error que lo dice; nunca la CPU en silencio."""
    torch = _torch()
    if not torch.cuda.is_available():
        raise SinGPU('No hay GPU CUDA para el gemelo digital: instale PyTorch con CUDA '
                     '(pip install torch --index-url https://download.pytorch.org/whl/cu126) '
                     'y compruebe el controlador de la tarjeta.')
    return torch.device('cuda')


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


def _con_base(m: Muestra, exponente: float = 0.0) -> np.ndarray:
    """Las entradas del nodo con la tensión y el ángulo del barrido físico, calculados una vez."""
    if m.base is None or m.base_exponente != exponente:
        p = ModeloRadial(exponente=exponente).predecir(_grafo_de_muestra(m))
        m.base = np.stack([p['v'], p['theta']], axis=1)
        m.base_exponente = exponente
    return np.concatenate([m.x, m.base], axis=1)


def _tensores(m: Muestra, disp, exponente: float = 0.0):
    torch = _torch()
    e = np.stack([np.log10(np.abs(m.z) + 1e-9), np.angle(m.z), np.log10(m.inom + 1e-6)], axis=1)
    return (torch.tensor(_con_base(m, exponente), dtype=torch.float32, device=disp),
            torch.tensor(m.aristas, dtype=torch.long, device=disp),
            torch.tensor(e, dtype=torch.float32, device=disp))


def _fisica(m: Muestra, disp, exponente: float = 0.0) -> dict:
    """Tensores fijos de la pérdida física de una muestra, creados una sola vez.

    Crearlos en cada paso agotó la memoria con IN111–TA225 (2470 nodos, 2026-10-22: «CUDA
    error: Memory allocation failure» con 1,3 GB de RAM libre) y tumbó la web.
    """
    torch = _torch()
    return {'a': torch.tensor(m.aristas[0], device=disp), 'b': torch.tensor(m.aristas[1], device=disp),
            'zr': torch.tensor(m.z.real, dtype=torch.float32, device=disp),
            'zi': torch.tensor(m.z.imag, dtype=torch.float32, device=disp),
            'sp': torch.tensor(m.s_carga.real, dtype=torch.float32, device=disp),
            'sq': torch.tensor(m.s_carga.imag, dtype=torch.float32, device=disp),
            'exigir': torch.tensor(~m.fuente & m.alimentado, device=disp), 'exponente': exponente}


def _residuo_torch(f: dict, v, theta):
    torch = _torch()
    a, b, zr, zi = f['a'], f['b'], f['zr'], f['zi']
    vr, vi = v * torch.cos(theta), v * torch.sin(theta)
    dr, di = vr[a] - vr[b], vi[a] - vi[b]
    den = zr * zr + zi * zi
    ir, ii = (dr * zr + di * zi) / den, (di * zr - dr * zi) / den
    i_r = torch.zeros_like(v).index_add_(0, a, ir)
    i_i = torch.zeros_like(v).index_add_(0, a, ii)
    p = vr * i_r + vi * i_i
    q = vi * i_r - vr * i_i
    e = v.abs() ** f['exponente']
    return ((p + f['sp'] * e) ** 2 + (q + f['sq'] * e) ** 2)[f['exigir']]


@dataclass
class Entrenamiento:
    epocas: int = 300
    lr: float = 3e-3
    peso_fisico: float = 1.0
    ocultas: int = 64
    pasos: int = 8
    semilla: int = 0
    exponente_carga: float = 0.0
    """Modelo de carga de la física, elegido con los datos (``elegir_exponente``)."""


def entrenar_miembro(muestras: Sequence[Muestra], cfg: Entrenamiento, inicial: dict | None = None,
                     log: Callable[[str], None] = lambda _m: None):
    """Un miembro del conjunto: error frente a DIgSILENT + residuo físico (PINN)."""
    torch = _torch()
    try:
        return _entrenar_en(muestras, cfg, inicial, log, dispositivo())
    finally:
        torch.cuda.empty_cache()     # cada miembro devuelve la memoria de la GPU


def _entrenar_en(muestras: Sequence[Muestra], cfg: Entrenamiento, inicial: dict | None,
                 log: Callable[[str], None], disp):
    torch = _torch()
    torch.manual_seed(cfg.semilla)
    random.seed(cfg.semilla)
    red = _red(cfg.ocultas, cfg.pasos).to(disp)
    if inicial:
        red.load_state_dict(inicial)
    opt = torch.optim.Adam(red.parameters(), lr=cfg.lr)
    datos = [(_fisica(m, disp, cfg.exponente_carga), *_tensores(m, disp, cfg.exponente_carga),
              torch.tensor(m.v, dtype=torch.float32, device=disp),
              torch.tensor(m.mascara, device=disp)) for m in muestras]
    for epoca in range(cfg.epocas):
        random.shuffle(datos)
        total = 0.0
        for f, x, ar, e, v, mask in datos:
            vp, th = red(x, ar, e)
            perdida = ((vp - v)[mask] ** 2).mean() + cfg.peso_fisico * _residuo_torch(f, vp, th).mean()
            opt.zero_grad()
            perdida.backward()
            opt.step()
            total += float(perdida.detach())
        if epoca % 100 == 0:
            log(f'  época {epoca}: pérdida {total / max(len(datos), 1):.3e}')
    return {k: v.detach().cpu() for k, v in red.state_dict().items()}


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
        x, ar, e = _tensores(m, disp, self.cfg.exponente_carga)
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
    return OraculoPINN(estados, Entrenamiento(**meta['cfg']), meta['dominio'], version=version)


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


def elegir_exponente(muestras: Sequence[Muestra], candidatos: Sequence[float] = (0.0, 1.0, 2.0)) -> float:
    """El modelo de carga que mejor reproduce a DIgSILENT con el barrido físico.

    DIgSILENT calcula estas cargas según la tensión: con potencia constante el barrido se
    apartaba 0,050 p.u. de IN111–TA225 y con impedancia constante 0,019 (2026-10-22). No se
    fija en el código porque otra empresa o versión puede modelarlas de otro modo.
    """
    def error(x: float) -> float:
        errores = []
        for m in muestras[:8]:
            p = ModeloRadial(exponente=x).predecir(_grafo_de_muestra(m))
            errores.append(float(np.mean(np.abs(p['v'][m.mascara] - m.v[m.mascara]))))
        return float(np.mean(errores)) if errores else 0.0
    return min(candidatos, key=error)


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
    grupos = {'entrenamiento': [], 'validacion': [], 'prueba': []}
    for m in muestras:
        grupos[particion(m.familia or 'x')].append(m)
    if not grupos['entrenamiento']:
        grupos['entrenamiento'] = list(muestras)
    actual = cargar(bufer)
    # Sin configuración, la del modelo en uso; sus pesos solo valen con la misma arquitectura.
    cfg = cfg or (actual.cfg if actual else Entrenamiento())
    cfg = Entrenamiento(**{**cfg.__dict__, 'exponente_carga': elegir_exponente(grupos['entrenamiento'])})
    log(f'Gemelo: modelo de carga de la física, S0·|V|^{cfg.exponente_carga:g}')
    compatible = actual is not None and (actual.cfg.ocultas, actual.cfg.pasos) == (cfg.ocultas, cfg.pasos)
    x_all = np.concatenate([m.x for m in grupos['entrenamiento']])
    dominio = {'x_min': x_all.min(axis=0).tolist(), 'x_max': x_all.max(axis=0).tolist(),
               'nodos': [min(len(m.ids) for m in grupos['entrenamiento']),
                         max(len(m.ids) for m in grupos['entrenamiento'])]}
    estados = []
    for k in range(MIEMBROS):
        inicial = actual.estados[k] if compatible and k < len(actual.estados) else None
        log(f'Gemelo: entrenando el miembro {k + 1} de {MIEMBROS} en {dispositivo()}…')
        estados.append(entrenar_miembro(grupos['entrenamiento'],
                                        Entrenamiento(**{**cfg.__dict__, 'semilla': cfg.semilla + k}),
                                        inicial, log))
    candidato = OraculoPINN(estados, cfg, dominio)
    evaluacion = grupos['prueba'] or grupos['validacion'] or grupos['entrenamiento']
    error = mae(candidato, evaluacion)
    residuos = [float(np.mean(candidato.predecir(_grafo_de_muestra(m))['residuo'])) for m in evaluacion]
    dorados_m = [m for m, i in zip(muestras, ids, strict=True) if i in set(dorados)]
    error_dorados = mae(candidato, dorados_m) if dorados_m else None
    error_dorados_actual = mae(actual, dorados_m) if actual and dorados_m else None
    meta = {'consulta': consulta.__dict__, 'episodios': ids, 'mae_v': error,
            'residuo_medio': float(np.mean(residuos)), 'mae_dorados': error_dorados,
            'particiones': {k: len(v) for k, v in grupos.items()}}
    carpeta = guardar(candidato, bufer, meta)
    fallos = []
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
