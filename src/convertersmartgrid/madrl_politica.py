"""Política con atención del piloto MADRL: GATv2 compartida entre agentes y crítico central (spec 074, T7).

Cada agente puntúa sus obras con la incrustación de la barra donde caen, de modo que la misma política vale para
alimentadores de cualquier tamaño, también los que no vio. El crítico ve toda la red: los agentes cooperan y la
recompensa es común. El aprendizaje es PPO con recorte, sin bibliotecas aparte; MaskablePPO es el control.

No escribe en DIgSILENT ni promueve modelos: lo que elige pasa por la puerta y por la spec 011 (074:RF-6, RF-10).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .digital_twin.oraculo import ModeloRadial, muestra
from .madrl_obras import EntornoPlano, resultado

#: Rasgos de cada barra: log10 kV, P, Q, fuente, consigna (del oráculo) y la tensión que da la física ahora.
RASGOS = 6


def observacion_grafo(plano: EntornoPlano) -> dict[str, Any]:
    """La red tal como está tras las obras hechas, y dónde cae cada obra posible."""
    g = plano.e.grafo
    m = muestra(g)
    v = np.asarray(ModeloRadial().predecir(g)['v'])
    x = np.concatenate([m.x, v[:, None]], axis=1).astype(np.float32)
    pos = {n: i for i, n in enumerate(m.ids)}
    rama_desde = {str(r['id']): r['desde'] for r in g.get('ramas') or []}
    sitio, tipo = [], []
    for agente, i in plano.todas:
        accion = plano.e.acciones[agente][i - 1]
        nodo = accion.elemento if accion.tipo == 'banco' else rama_desde[accion.elemento]
        sitio.append(pos[nodo])
        tipo.append(0 if accion.tipo == 'banco' else 1)
    hechas = [float(i - 1 in plano.e.hechas[a]) for a, i in plano.todas]
    return {'x': x, 'aristas': m.aristas, 'sitio': np.array(sitio, dtype=np.int64),
            'tipo': np.array(tipo, dtype=np.int64), 'hechas': np.array(hechas, dtype=np.float32),
            'mascara': plano.mascara()}


def crear_politica(ocultas: int = 32, cabezas: int = 2):
    """La red: dos capas GATv2, un actor por obra y un crítico central sobre toda la red."""
    import torch
    from torch import nn
    from torch_geometric.nn import GATv2Conv

    class Politica(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.g1 = GATv2Conv(RASGOS, ocultas, heads=cabezas, concat=False)
            self.g2 = GATv2Conv(ocultas, ocultas, heads=cabezas, concat=False)
            self.actor = nn.Sequential(nn.Linear(ocultas + 3, ocultas), nn.Tanh(), nn.Linear(ocultas, 1))
            self.nada = nn.Sequential(nn.Linear(ocultas, ocultas), nn.Tanh(), nn.Linear(ocultas, 1))
            self.critico = nn.Sequential(nn.Linear(2 * ocultas, ocultas), nn.Tanh(), nn.Linear(ocultas, 1))

        def forward(self, o: dict[str, Any]):
            x = torch.as_tensor(o['x'])
            ei = torch.as_tensor(o['aristas'])
            h = torch.relu(self.g1(x, ei))
            h = torch.relu(self.g2(h, ei))
            red = torch.cat([h.mean(0), h.max(0).values])
            tipo = torch.as_tensor(o['tipo']).float()
            rasgos = torch.stack([tipo, 1 - tipo, torch.as_tensor(o['hechas'])], dim=1)
            obras = self.actor(torch.cat([h[torch.as_tensor(o['sitio'])], rasgos], dim=1)).squeeze(1)
            logits = torch.cat([self.nada(h.mean(0)), obras])
            logits = logits.masked_fill(~torch.as_tensor(o['mascara']), -1e9)
            return logits, self.critico(red).squeeze(0)

    return Politica()


@dataclass(frozen=True)
class Entrenamiento:
    iteraciones: int = 40
    episodios_por_iteracion: int = 8
    epocas: int = 4
    recorte: float = 0.2
    descuento: float = 0.99
    tasa: float = 3e-3
    semilla: int = 1


def _episodio(plano: EntornoPlano, politica, *, muestrear: bool):
    import torch

    pasos, fin = [], False
    plano.reiniciar()
    while not fin:
        o = observacion_grafo(plano)
        with torch.no_grad():
            logits, valor = politica(o)
        dist = torch.distributions.Categorical(logits=logits)
        accion = int(dist.sample()) if muestrear else int(torch.argmax(logits))
        _obs, recompensa, fin = plano.paso(accion)
        pasos.append({'o': o, 'a': accion, 'logp': float(dist.log_prob(torch.tensor(accion))), 'v': float(valor),
                      'r': float(recompensa)})
    return pasos


def entrenar_ppo(plano: EntornoPlano, cfg: Entrenamiento | None = None, politica=None) -> tuple[Any, list[float]]:
    """PPO con recorte, retorno descontado y ventaja contra el crítico central. Devuelve (política, retorno medio)."""
    import torch

    cfg = cfg or Entrenamiento()

    torch.manual_seed(cfg.semilla)
    politica = politica or crear_politica()
    opt = torch.optim.Adam(politica.parameters(), lr=cfg.tasa)
    curva: list[float] = []
    for _ in range(cfg.iteraciones):
        lote, retornos_ep = [], []
        for _e in range(cfg.episodios_por_iteracion):
            pasos = _episodio(plano, politica, muestrear=True)
            g = 0.0
            for p in reversed(pasos):
                g = p['r'] + cfg.descuento * g
                p['g'] = g
            retornos_ep.append(pasos[0]['g'])
            lote += pasos
        curva.append(float(np.mean(retornos_ep)))
        ventajas = torch.tensor([p['g'] - p['v'] for p in lote])
        if len(lote) > 1:
            ventajas = (ventajas - ventajas.mean()) / (ventajas.std() + 1e-8)
        for _ep in range(cfg.epocas):
            perdida = torch.zeros(())
            for p, adv in zip(lote, ventajas, strict=True):
                logits, valor = politica(p['o'])
                dist = torch.distributions.Categorical(logits=logits)
                razon = torch.exp(dist.log_prob(torch.tensor(p['a'])) - p['logp'])
                actor = -torch.min(razon * adv, torch.clamp(razon, 1 - cfg.recorte, 1 + cfg.recorte) * adv)
                perdida = perdida + actor + 0.5 * (valor - p['g']) ** 2 - 0.01 * dist.entropy()
            opt.zero_grad()
            (perdida / len(lote)).backward()
            opt.step()
    return politica, curva


def evaluar_politica(plano: EntornoPlano, politica) -> dict[str, Any]:
    """La política sin azar, una vez: lo que se compara en la puerta (074:RF-6)."""
    pasos = _episodio(plano, politica, muestrear=False)
    return resultado(plano.e, 'gatv2', len(pasos))


def evaluar_en(planos: Sequence[EntornoPlano], politica) -> list[dict[str, Any]]:
    """La misma política en alimentadores que no vio: así se pide a la puerta."""
    return [evaluar_politica(p, politica) for p in planos]
