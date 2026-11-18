"""045:RF-8 — PowerFlowNet MIT, reutilizado desde una copia Git verificada."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def crear_red_powerflownet(ocultas: int = 64, pasos: int = 8):
    """Adapta el MPN original a correcciones sobre la física del conversor."""
    if type(ocultas) is not int or ocultas < 1 or type(pasos) is not int or pasos < 2:
        raise ValueError('PowerFlowNet requiere ocultas positivas y al menos dos capas')
    from ..upstream_ia import verificar_repositorio
    origen = verificar_repositorio('powerflownet')
    import torch
    from torch_geometric.data import Data
    from torch import nn

    nombre = '_csg_powerflownet_' + origen['commit']
    if nombre not in sys.modules:
        archivo = Path(origen['path']) / 'networks/MPN.py'
        spec = importlib.util.spec_from_file_location(nombre, archivo)
        if spec is None or spec.loader is None:
            raise ImportError('no se puede cargar el MPN de PowerFlowNet')
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[nombre] = modulo
        try:
            spec.loader.exec_module(modulo)
        except BaseException:
            sys.modules.pop(nombre, None)
            raise
    modulo = sys.modules[nombre]

    class RedHibrida(nn.Module):
        def __init__(self):
            super().__init__()
            self.mpn = modulo.MPN(nfeature_dim=7, efeature_dim=3, output_dim=2,
                                  hidden_dim=ocultas, n_gnn_layers=pasos, K=3, dropout_rate=0.0)
            self.modelo_upstream = origen

        def forward(self, x, aristas, e):
            if x.ndim != 2 or x.shape[1] != 7 or aristas.shape[0] != 2 or aristas.shape[1] == 0:
                raise ValueError('PowerFlowNet necesita siete entradas y ramas explícitas')
            if e.ndim != 2 or e.shape != (aristas.shape[1], 3):
                raise ValueError('atributos de rama incompatibles')
            es_fuente = x[:, 3] > 0.5
            tipos = torch.where(es_fuente, 0, 2)
            indicadores = torch.nn.functional.one_hot(tipos, num_classes=4).to(x.dtype)
            data = Data(x=torch.cat([indicadores, x, torch.ones_like(x)], dim=1),
                        edge_index=aristas, edge_attr=e)
            correccion = self.mpn(data)
            v = x[:, 5] + 0.1 * torch.tanh(correccion[:, 0])
            theta = x[:, 6] + 0.2 * torch.tanh(correccion[:, 1])
            return torch.where(es_fuente, x[:, 4], v), torch.where(es_fuente, x[:, 6], theta)

    return RedHibrida()
