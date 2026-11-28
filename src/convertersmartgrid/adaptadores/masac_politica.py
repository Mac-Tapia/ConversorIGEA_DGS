"""MASAC con CTDE para el agente de obras: un actor compartido y un crítico central por nivel (spec 114, T3).

El usuario pidió el 2026-11-26 que el MADRL de la 074 «se expanda y sea MASAC», con Dec-POMDP y CTDE. Es SAC discreto
multiagente (Christodoulou, 2019, en su forma multiagente de BenchMARL): cada nivel (alimentador, SET, sistema) tiene un
actor que comparten todos sus agentes y que decide solo con su observación, y dos críticos centrales que, al entrenar,
ven además el estado global (114:RF-2). La temperatura de la entropía se ajusta sola hacia una fracción de la máxima de
cada máscara.

BenchMARL no se usa: su 1.5.2 fija ``torchrl<0.12`` y no importa con la TorchRL 0.14.1 que pide torch 2.14.1; la misma
formulación va escrita aquí en PyTorch, que ya está en el ``.venv`` (114:RF-14). Así entrena e infiere sin las
dependencias aparte, y la inferencia va siempre en CPU (requisito no funcional: sin GPU con la política ya entrenada).

No escribe en DIgSILENT ni en la red: propone sobre el entorno de ``masac_entorno``, que trabaja sobre copias.
"""
from __future__ import annotations

import json
import random
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .masac_entorno import NIVELES, EntornoAgente, jugar

#: Lo que dice cada modelo guardado de cómo se entrenó (114:RF-14).
IMPLEMENTACION = 'masac_pytorch_propio (formulación de BenchMARL; BenchMARL 1.5.2 no admite torchrl 0.14.1)'


@dataclass(frozen=True)
class ConfigMASAC:
    episodios: int = 150
    lote: int = 64
    descuento: float = 0.9
    tasa_actor: float = 3e-3
    tasa_critico: float = 3e-3
    tasa_alfa: float = 3e-3
    tau: float = 0.05
    #: Fracción de la entropía máxima de cada máscara a la que tiende la temperatura.
    entropia_objetivo: float = 0.3
    ocultas: int = 64
    memoria: int = 20000
    actualizaciones_por_paso: int = 4
    inicio: int = 64
    semilla: int = 1


def _torch():
    import torch

    return torch


def _redes(tam_obs: int, tam_estado: int, n_acciones: int, ocultas: int):
    torch = _torch()
    from torch import nn

    def mlp(entrada: int):
        return nn.Sequential(nn.Linear(entrada, ocultas), nn.ReLU(), nn.Linear(ocultas, ocultas), nn.ReLU(),
                             nn.Linear(ocultas, n_acciones))

    class Nivel(nn.Module):
        """Actor local (solo su observación) y dos críticos centrales (estado global + su observación)."""

        def __init__(self) -> None:
            super().__init__()
            self.actor = mlp(tam_obs)
            self.q1, self.q2 = mlp(tam_estado + tam_obs), mlp(tam_estado + tam_obs)
            self.q1_obj, self.q2_obj = mlp(tam_estado + tam_obs), mlp(tam_estado + tam_obs)
            self.q1_obj.load_state_dict(self.q1.state_dict())
            self.q2_obj.load_state_dict(self.q2.state_dict())
            self.log_alfa = nn.Parameter(torch.zeros(()))

        def logits(self, obs, mascara):
            return self.actor(obs).masked_fill(~mascara, -1e9)

    return Nivel()


class MASAC:
    """Los tres niveles con sus redes; ``actuar`` es la inferencia local, en CPU."""

    def __init__(self, dims: Mapping[str, tuple[int, int]], tam_estado: int, cfg: ConfigMASAC | None = None) -> None:
        torch = _torch()
        self.cfg = cfg or ConfigMASAC()
        self.dims = {n: tuple(d) for n, d in dims.items()}
        self.tam_estado = tam_estado
        torch.manual_seed(self.cfg.semilla)
        self.niveles = {n: _redes(o, tam_estado, a, self.cfg.ocultas) for n, (o, a) in self.dims.items()}
        self.opt_actor = {n: torch.optim.Adam(r.actor.parameters(), lr=self.cfg.tasa_actor) for n, r in self.niveles.items()}
        self.opt_critico = {n: torch.optim.Adam([*r.q1.parameters(), *r.q2.parameters()], lr=self.cfg.tasa_critico)
                            for n, r in self.niveles.items()}
        self.opt_alfa = {n: torch.optim.Adam([r.log_alfa], lr=self.cfg.tasa_alfa) for n, r in self.niveles.items()}

    @classmethod
    def para(cls, entorno: EntornoAgente, cfg: ConfigMASAC | None = None) -> MASAC:
        return cls(entorno.dimensiones(), entorno.tam_estado, cfg)

    def actuar(self, nivel: str, obs: np.ndarray, mascara: np.ndarray, *, deterministico: bool,
               rng: np.random.Generator | None = None) -> int:
        """La acción de un agente con solo su observación: así decide en producción (114:RF-2)."""
        torch = _torch()
        with torch.no_grad():
            logits = self.niveles[nivel].logits(torch.as_tensor(obs, dtype=torch.float32)[None],
                                                torch.as_tensor(np.asarray(mascara, dtype=bool))[None])[0]
        if deterministico:
            return int(torch.argmax(logits))
        p = torch.softmax(logits, 0).numpy().astype(float)
        p /= p.sum()
        return int((rng or np.random.default_rng()).choice(len(p), p=p))

    def explicar(self, nivel: str, obs: np.ndarray, mascara: np.ndarray, estado: np.ndarray) -> list[dict[str, float]]:
        """Por qué elige: la probabilidad del actor y el valor del crítico de cada acción permitida, de mejor a peor."""
        torch = _torch()
        r = self.niveles[nivel]
        o = torch.as_tensor(obs, dtype=torch.float32)[None]
        m = torch.as_tensor(np.asarray(mascara, dtype=bool))[None]
        x = torch.cat([torch.as_tensor(estado, dtype=torch.float32)[None], o], 1)
        with torch.no_grad():
            prob = torch.softmax(r.logits(o, m), 1)[0]
            q = torch.min(r.q1(x), r.q2(x))[0]
        filas = [{'accion': int(i), 'probabilidad': float(prob[i]), 'valor': float(q[i])}
                 for i in np.flatnonzero(np.asarray(mascara))]
        return sorted(filas, key=lambda f: (-f['probabilidad'], f['accion']))

    def actualizar(self, nivel: str, lote: Sequence[Mapping[str, Any]]) -> dict[str, float]:
        """Un paso de SAC discreto en un nivel: críticos con el objetivo blando, actor y temperatura."""
        torch = _torch()
        import torch.nn.functional as F

        r, cfg = self.niveles[nivel], self.cfg

        def tensor(clave, dtype=torch.float32):
            return torch.as_tensor(np.stack([t[clave] for t in lote]), dtype=dtype)

        o, m, s = tensor('obs'), tensor('mascara', torch.bool), tensor('estado')
        o2, m2, s2 = tensor('obs2'), tensor('mascara2', torch.bool), tensor('estado2')
        a = torch.as_tensor([t['accion'] for t in lote], dtype=torch.long)
        rec = torch.as_tensor([t['recompensa'] for t in lote], dtype=torch.float32)
        fin = torch.as_tensor([float(t['fin']) for t in lote], dtype=torch.float32)
        alfa = r.log_alfa.exp().detach()

        with torch.no_grad():
            logp2 = F.log_softmax(r.logits(o2, m2), 1)
            p2 = logp2.exp()
            x2 = torch.cat([s2, o2], 1)
            q_obj = torch.min(r.q1_obj(x2), r.q2_obj(x2))
            # Las acciones fuera de la máscara tienen probabilidad cero: no suman ni su valor ni su entropía.
            v2 = (p2 * (q_obj - alfa * logp2.masked_fill(~m2, 0.0))).masked_fill(~m2, 0.0).sum(1)
            y = rec + cfg.descuento * (1 - fin) * v2
        x = torch.cat([s, o], 1)
        q1 = r.q1(x).gather(1, a[:, None])[:, 0]
        q2 = r.q2(x).gather(1, a[:, None])[:, 0]
        perdida_q = F.mse_loss(q1, y) + F.mse_loss(q2, y)
        self.opt_critico[nivel].zero_grad()
        perdida_q.backward()
        self.opt_critico[nivel].step()

        logp = F.log_softmax(r.logits(o, m), 1)
        p = logp.exp()
        with torch.no_grad():
            q = torch.min(r.q1(x), r.q2(x))
        logp0 = logp.masked_fill(~m, 0.0)
        perdida_pi = (p * (alfa * logp0 - q)).masked_fill(~m, 0.0).sum(1).mean()
        self.opt_actor[nivel].zero_grad()
        perdida_pi.backward()
        self.opt_actor[nivel].step()

        validas = m.sum(1).float()
        objetivo = cfg.entropia_objetivo * torch.log(validas.clamp(min=1.0))
        menos_entropia = (p * logp0).sum(1).detach()
        perdida_alfa = -(r.log_alfa * (menos_entropia + objetivo)).mean()
        self.opt_alfa[nivel].zero_grad()
        perdida_alfa.backward()
        self.opt_alfa[nivel].step()

        with torch.no_grad():
            for red, obj in ((r.q1, r.q1_obj), (r.q2, r.q2_obj)):
                for w, w_obj in zip(red.parameters(), obj.parameters(), strict=True):
                    w_obj.mul_(1 - cfg.tau).add_(cfg.tau * w)
        return {'critico': perdida_q.item(), 'actor': perdida_pi.item(), 'alfa': alfa.item()}

    def estado(self) -> dict[str, Any]:
        return {n: {k: v.detach().cpu() for k, v in r.state_dict().items()} for n, r in self.niveles.items()}


def transiciones(ep, entorno: EntornoAgente) -> list[tuple[str, dict[str, Any]]]:
    """Lo jugado en un episodio, por agente: lo que guarda la memoria y lo que va al registro de experiencia."""
    salida = []
    for paso in ep.pasos:
        for agente, accion in paso['acciones'].items():
            o, o2 = paso['obs'][agente], paso['siguiente'][agente]
            salida.append((entorno.estructura[agente].nivel, {
                'obs': o['observation'], 'mascara': o['action_mask'].astype(bool), 'accion': int(accion),
                'recompensa': float(paso['recompensa']), 'obs2': o2['observation'], 'mascara2': o2['action_mask'].astype(bool),
                'estado': paso['estado'], 'estado2': paso['siguiente_estado'], 'fin': bool(paso['fin'])}))
    return salida


def entrenar_masac(entorno: EntornoAgente, cfg: ConfigMASAC | None = None,
                   al_episodio: Callable[[int, int], None] | None = None) -> tuple[MASAC, list[float]]:
    """Entrena en CPU sobre el entorno; devuelve la política y el retorno de cada episodio.

    ``al_episodio(hechos, total)`` tras cada episodio: la web avanza su barra y cancela entre episodios.
    """
    torch = _torch()
    cfg = cfg or ConfigMASAC()
    random.seed(cfg.semilla)
    np.random.seed(cfg.semilla)
    torch.manual_seed(cfg.semilla)
    agente = MASAC.para(entorno, cfg)
    rng = np.random.default_rng(cfg.semilla)
    memoria = {n: deque(maxlen=cfg.memoria) for n in NIVELES}
    curva: list[float] = []
    for ep_i in range(cfg.episodios):
        ep = jugar(entorno, lambda a, o, m: agente.actuar(entorno.estructura[a].nivel, o, m, deterministico=False, rng=rng),
                   semilla=cfg.semilla + ep_i)
        curva.append(float(sum(p['recompensa'] for p in ep.pasos)))
        if al_episodio is not None:
            al_episodio(ep_i + 1, cfg.episodios)
        for nivel, t in transiciones(ep, entorno):
            memoria[nivel].append(t)
        for _ in range(cfg.actualizaciones_por_paso * len(ep.pasos)):
            for nivel, mem in memoria.items():
                if len(mem) >= min(cfg.inicio, cfg.lote):
                    agente.actualizar(nivel, [mem[i] for i in rng.integers(0, len(mem), min(cfg.lote, len(mem)))])
    return agente, curva


def evaluar_masac(entorno: EntornoAgente, agente: MASAC) -> dict[str, Any]:
    """La política sin azar, una vez: lo que se compara con el azar, la escalera, NSGA-II y la PPO de la 074."""
    ep = jugar(entorno, lambda a, o, m: agente.actuar(entorno.estructura[a].nivel, o, m, deterministico=True))
    return {**entorno.resultado('masac'), 'retorno': float(sum(p['recompensa'] for p in ep.pasos))}


def evaluar_azar(entorno: EntornoAgente, episodios: int, semilla: int) -> dict[str, Any]:
    """La referencia más baja: cada agente elige al azar entre lo que su máscara permite."""
    rng = np.random.default_rng(semilla)
    retornos, en_norma, costos = [], [], []
    for i in range(episodios):
        ep = jugar(entorno, lambda _a, _o, m: int(rng.choice(np.flatnonzero(m))), semilla=semilla + i)
        retornos.append(float(sum(p['recompensa'] for p in ep.pasos)))
        en_norma.append(bool(ep.resultado['en_norma']))
        costos.append(float(ep.resultado['costo']))
    return {'control': 'azar', 'episodios': episodios, 'retorno': float(np.mean(retornos)),
            'retorno_mejor': float(np.max(retornos)), 'en_norma': float(np.mean(en_norma)), 'costo': float(np.mean(costos))}


def guardar_masac(carpeta: Path, agente: MASAC, **extra) -> dict[str, Any]:
    """Pesos y manifiesto: dimensiones, configuración y cómo se entrenó (114:RF-14)."""
    torch = _torch()
    carpeta.mkdir(parents=True, exist_ok=True)
    torch.save(agente.estado(), carpeta / 'masac.pt')
    manifiesto = {'politica': 'masac', 'implementacion': IMPLEMENTACION, 'dims': {n: list(d) for n, d in agente.dims.items()},
                  'tam_estado': agente.tam_estado, 'config': asdict(agente.cfg), **extra}
    from ..dominio.util import write_json_atomic

    write_json_atomic(carpeta / 'modelo.json', manifiesto)          # 001:RF-5
    return manifiesto


def cargar_masac(carpeta: Path) -> MASAC:
    """La política guardada, siempre en CPU: la inferencia no pide GPU."""
    torch = _torch()
    manifiesto = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    agente = MASAC({n: tuple(d) for n, d in manifiesto['dims'].items()}, int(manifiesto['tam_estado']),
                   ConfigMASAC(**manifiesto['config']))
    pesos = torch.load(carpeta / 'masac.pt', map_location='cpu', weights_only=True)
    for n, r in agente.niveles.items():
        r.load_state_dict(pesos[n])
        r.eval()
    return agente
