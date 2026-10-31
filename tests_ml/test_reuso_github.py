"""045:RF-8 — ensayos con código clonado real; ejecutar en el entorno ML opcional."""
import os
from pathlib import Path
import tempfile

import numpy as np
import torch
import pytest

from igea_dgs.digital_twin import oraculo


@pytest.fixture(autouse=True)
def gpu_exclusiva():
    """043:RF-6 — estos ensayos respetan la misma exclusión que el coordinador."""
    from igea_dgs.training_coordinator import BloqueoGPU
    ruta = Path(os.environ.get('IGEA_ML_GPU_LOCK') or
                str(Path(tempfile.gettempdir()) / 'igea-dgs-gpu.lock'))
    with BloqueoGPU(ruta, 'ensayo-powerflownet'):
        yield


def grafo():
    return {'version': oraculo.VERSION_GRAFO, 'nodos': {
        'S': {'kv': 10.0, 'p_mw': 0, 'q_mvar': 0, 'fuente': True, 'v_pu': 1.02},
        'A': {'kv': 10.0, 'p_mw': .2, 'q_mvar': .07, 'fuente': False},
        'B': {'kv': 10.0, 'p_mw': .1, 'q_mvar': .03, 'fuente': False}}, 'ramas': [
        {'id': 'L1', 'desde': 'S', 'hasta': 'A', 'cerrada': True, 'r_ohm': .4, 'x_ohm': .3, 'inom_ka': .2},
        {'id': 'L2', 'desde': 'A', 'hasta': 'B', 'cerrada': True, 'r_ohm': .5, 'x_ohm': .3, 'inom_ka': .2}]}


def test_powerflownet_clonado_entrena_en_cuda(tmp_path):
    """045:RF-8 — forward, gradiente, fronteras y descenso de pérdida con el MPN real."""
    from igea_dgs.digital_twin.adaptador_pyg import crear_red_powerflownet
    torch.manual_seed(11)
    muestra = oraculo.muestra(grafo())
    dispositivo = oraculo.dispositivo()
    assert dispositivo.type == 'cuda'
    red = crear_red_powerflownet(ocultas=8, pasos=2).to(dispositivo)
    x, aristas, e = oraculo._tensores(muestra, dispositivo)
    referencia = oraculo.ModeloMallado().predecir(grafo())
    objetivo = torch.tensor(referencia['v'], device=dispositivo, dtype=torch.float32)
    opt = torch.optim.Adam(red.parameters(), lr=0.005)
    errores = []
    for _ in range(30):
        v, angulo = red(x, aristas, e)
        perdida = ((v - objetivo) ** 2).mean()
        errores.append(float(perdida.detach()))
        opt.zero_grad()
        perdida.backward()
        assert all(torch.isfinite(p.grad).all() for p in red.parameters() if p.grad is not None)
        opt.step()
    assert errores[-1] < errores[0]
    assert v.shape == angulo.shape == (3,)
    indice_fuente = muestra.ids.index('S')
    assert v[indice_fuente].item() == np.float32(1.02)
    assert angulo[indice_fuente].item() == x[indice_fuente, 6].item()
    assert red.modelo_upstream['id'] == 'powerflownet'
    assert len(red.modelo_upstream['commit']) == 40
    red.eval()
    archivo = tmp_path / 'pesos.pt'
    torch.save(red.state_dict(), archivo)
    reabierta = crear_red_powerflownet(ocultas=8, pasos=2).to(dispositivo)
    reabierta.load_state_dict(torch.load(archivo, map_location=dispositivo, weights_only=True))
    reabierta.eval()
    with torch.no_grad():
        antes = red(x, aristas, e)
        despues = reabierta(x, aristas, e)
    assert all(torch.equal(a, b) for a, b in zip(antes, despues, strict=True))


def test_configuracion_oraculo_reutiliza_powerflownet():
    """045:RF-8 — el backend opcional usa la misma firma y cuenta sus parámetros reales."""
    cfg = oraculo.Entrenamiento(arquitectura='powerflownet', ocultas=8, pasos=2)
    red = oraculo._red(cfg.ocultas, cfg.pasos, cfg.arquitectura)
    assert sum(p.numel() for p in red.parameters()) == oraculo._parametros(cfg)
