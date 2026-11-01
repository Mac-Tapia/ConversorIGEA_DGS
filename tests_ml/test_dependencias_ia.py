"""043:RF-12: operaciones reales del entorno instalado; no acreditan modelos de campo."""
import os
from pathlib import Path
import tempfile

import pytest


@pytest.fixture(autouse=True)
def gpu_exclusiva():
    from convertersmartgrid.training_coordinator import BloqueoGPU
    ruta = Path(os.environ.get('CSG_ML_GPU_LOCK') or str(Path(tempfile.gettempdir()) / 'convertersmartgrid-gpu.lock'))
    with BloqueoGPU(ruta, 'verificacion-dependencias-ia'):
        yield


def test_pymoo_wheel_ejecuta_optimizacion():
    """043:RF-12: ejecutar el optimizador detecta errores ABI que un import no prueba."""
    import numpy as np
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.problems import get_problem
    from pymoo.optimize import minimize
    r = minimize(get_problem('zdt1', n_var=5), NSGA2(pop_size=16), ('n_gen', 5), seed=11)
    assert r.X.shape[1] == 5 and r.F.shape[1] == 2
    assert np.isfinite(r.F).all() and ((0 <= r.X) & (r.X <= 1)).all()


def test_pyomo_highs_resuelve_con_restricciones():
    """043:RF-12: Pyomo instalado no implica solver disponible; se resuelve un LP real."""
    import pyomo.environ as p
    m = p.ConcreteModel()
    m.x = p.Var(domain=p.NonNegativeReals)
    m.y = p.Var(domain=p.NonNegativeReals)
    m.obj = p.Objective(expr=m.x + 2*m.y)
    m.c = p.Constraint(expr=m.x + m.y >= 3)
    s = p.SolverFactory('appsi_highs')
    assert s.available()
    r = s.solve(m)
    assert r.solver.termination_condition == p.TerminationCondition.optimal
    assert abs(p.value(m.obj) - 3) < 1e-7 and p.value(m.x + m.y) >= 3-1e-7


def test_ipopt_resuelve_pnl_con_cotas():
    """043:RF-12: ejecutable/DLL reales para PNL; HiGHS no sustituye ese requisito."""
    import pyomo.environ as p
    raiz = Path(__file__).resolve().parents[1]
    ejecutable = Path(os.environ.get('CSG_IPOPT_PATH') or
        raiz / 'external/solvers/ipopt-3.14.19/Ipopt-3.14.19-win64-msvs2022-md/bin/ipopt.exe')
    assert ejecutable.is_file()
    m = p.ConcreteModel()
    m.x = p.Var(bounds=(0, 5), initialize=.5)
    m.y = p.Var(bounds=(0, 5), initialize=.5)
    m.obj = p.Objective(expr=(m.x-1)**2 + 3*(m.y-2)**2)
    m.c = p.Constraint(expr=m.x+m.y >= 3)
    s = p.SolverFactory('ipopt', executable=str(ejecutable))
    assert s.available()
    r = s.solve(m, options={'tol': 1e-9})
    assert r.solver.termination_condition == p.TerminationCondition.optimal
    assert p.value(m.obj) < 1e-8 and p.value(m.x+m.y) >= 3-1e-7


def test_bitsandbytes_nf4_en_cuda():
    """043:RF-12: DLL cuantizada Windows/CUDA con forward y gradiente reales."""
    import torch
    import bitsandbytes as bnb
    assert torch.cuda.is_available()
    red = bnb.nn.Linear4bit(16, 8, quant_type='nf4', compute_dtype=torch.float16).cuda()
    x = torch.randn(2, 16, device='cuda', dtype=torch.float16, requires_grad=True)
    y = red(x)
    y.float().square().mean().backward()
    assert y.shape == (2, 8) and torch.isfinite(y).all() and torch.isfinite(x.grad).all()


@pytest.mark.parametrize('nombre', ['GRU', 'NHITS', 'TFT', 'PatchTST'])
def test_neuralforecast_entrena_y_predice_en_cuda(nombre):
    """043:RF-12: dos pasos reales por arquitectura, sobre una fixture, sin declarar precision."""
    import numpy as np
    import pandas as pd
    import torch
    from neuralforecast import NeuralForecast
    from neuralforecast import models
    from pytorch_lightning import Callback
    assert torch.cuda.is_available()
    cls = getattr(models, nombre)
    extra = {'GRU': {'encoder_hidden_size': 8, 'decoder_hidden_size': 8},
             'NHITS': {'mlp_units': [[8, 8], [8, 8], [8, 8]]},
             'TFT': {'hidden_size': 8, 'n_head': 2},
             'PatchTST': {'hidden_size': 8, 'n_heads': 2, 'patch_len': 4, 'stride': 2}}
    dispositivos = []
    class EvidenciaCUDA(Callback):
        def on_train_batch_start(self, trainer, pl_module, batch, batch_idx):
            dispositivos.append(next(pl_module.parameters()).device.type)
    modelo = cls(h=2, input_size=8, max_steps=2, val_check_steps=2, batch_size=2,
                 accelerator='gpu', devices=1, enable_progress_bar=False, logger=False,
                 enable_checkpointing=False, random_seed=11, callbacks=[EvidenciaCUDA()], **extra[nombre])
    datos = pd.DataFrame({'unique_id': ['A']*20 + ['B']*20,
        'ds': list(pd.date_range('2020-01-01', periods=20))*2,
        'y': np.r_[np.sin(np.arange(20)), np.cos(np.arange(20))]})
    nf = NeuralForecast(models=[modelo], freq='D')
    nf.fit(df=datos)
    r = nf.predict()
    assert len(r) == 4 and np.isfinite(r[nombre].to_numpy()).all()
    # Lightning devuelve el modelo a CPU al terminar; registrar el dispositivo durante el ajuste.
    assert len(dispositivos) == 2 and set(dispositivos) == {'cuda'}
