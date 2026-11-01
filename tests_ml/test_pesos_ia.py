"""043:RF-12: carga local de pesos y ensayo PEFT, sin promocion ni datos privados.

Exige las descargas del catalogo completas; no omite modelos ausentes.
El paso LoRA es una prueba de entorno, no un ajuste validado del agente.
"""
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MODELOS = json.loads((RAIZ / 'docs/MODELOS_IA_LOCK.json').read_text(encoding='utf-8'))['modelos']


def _ficha(identidad):
    return next(m for m in MODELOS if identidad in m['id'])


@pytest.fixture(autouse=True)
def gpu_exclusiva(monkeypatch, request):
    import psutil
    minimo_gb = 6 if 'qwen' in request.node.name else 4 if 'bge' in request.node.name else 3
    disponible = psutil.virtual_memory().available / 1024**3
    if disponible < minimo_gb:
        pytest.fail(f'RAM insuficiente antes de cargar pesos: {disponible:.2f} GiB disponibles; '
                    f'se requieren {minimo_gb} GiB para este ensayo. No se omite ni acredita la prueba.', pytrace=False)
    import torch
    from igea_dgs.training_coordinator import BloqueoGPU
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    assert torch.cuda.is_available()
    ruta = Path(os.environ.get('IGEA_ML_GPU_LOCK') or str(Path(tempfile.gettempdir()) / 'igea-dgs-gpu.lock'))
    with BloqueoGPU(ruta, 'ensayo-pesos-preentrenados'):
        yield
        gc.collect(); torch.cuda.empty_cache()


def test_e5_codifica_localmente():
    """043:RF-12: config de pooling y pesos completos permiten reapertura e inferencia."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    f = _ficha('multilingual-e5-base')
    m = SentenceTransformer(f['id'], revision=f['revision'], local_files_only=True, device='cuda')
    r = m.encode(['query: flujo de potencia', 'query: demanda electrica'], normalize_embeddings=True)
    assert r.shape == (2, 768) and np.isfinite(r).all()
    assert np.allclose(np.linalg.norm(r, axis=1), 1., atol=1e-5)


def test_bge_inferencia_de_pares_local():
    """043:RF-12: ejecutar el cross-encoder no acredita el benchmark de recuperacion."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    f = _ficha('bge-reranker-v2-m3')
    tok = AutoTokenizer.from_pretrained(f['id'], revision=f['revision'], local_files_only=True, trust_remote_code=False)
    m = AutoModelForSequenceClassification.from_pretrained(f['id'], revision=f['revision'],
        local_files_only=True, trust_remote_code=False, dtype=torch.float16).cuda().eval()
    x = tok([['flujo de potencia', 'calculo electrico de tensiones'],
             ['flujo de potencia', 'receta de una tortilla']], padding=True, return_tensors='pt').to('cuda')
    with torch.inference_mode():
        r = m(**x).logits
    assert r.shape == (2, 1) and torch.isfinite(r).all() and r[0].item() != r[1].item()


def test_qwen_nf4_paso_lora_y_reapertura_real(tmp_path):
    """043:RF-12 / 047:RF-14: un paso CUDA y recarga en proceso nuevo, sin activacion."""
    import torch
    import bitsandbytes as bnb
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer
    f = _ficha('Instruct-2507-bnb-4bit')
    torch.manual_seed(11)
    tok = AutoTokenizer.from_pretrained(f['id'], revision=f['revision'], local_files_only=True, trust_remote_code=False)
    base = AutoModelForCausalLM.from_pretrained(f['id'], revision=f['revision'],
        local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16,
        device_map={'': 0}, attn_implementation='eager')
    assert any(isinstance(m, bnb.nn.Linear4bit) for m in base.modules())
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
    m = get_peft_model(base, LoraConfig(r=4, lora_alpha=8, target_modules=['q_proj', 'v_proj'],
                                     lora_dropout=0., bias='none', task_type='CAUSAL_LM'))
    parametro = next(p for n, p in m.named_parameters() if 'lora_B' in n)
    antes = parametro.detach().clone()
    x = tok('Orden de ensayo: consultar el estado del espacio.', return_tensors='pt').to('cuda')
    opt = torch.optim.AdamW([p for p in m.parameters() if p.requires_grad], lr=1e-3)
    m.train(); perdida = m(**x, labels=x['input_ids']).loss
    assert torch.isfinite(perdida)
    perdida.backward(); opt.step(); opt.zero_grad(set_to_none=True)
    assert torch.isfinite(parametro).all() and not torch.equal(antes, parametro)
    m.eval()
    with torch.inference_mode():
        esperado = m(**x).logits[0, -1, :8].float().cpu().tolist()
    adaptador = tmp_path / 'adaptador'; m.save_pretrained(adaptador, safe_serialization=True)
    assert (adaptador / 'adapter_model.safetensors').is_file()
    del m, base, opt, parametro, antes, perdida, x
    gc.collect(); torch.cuda.empty_cache()
    codigo = '''import json,sys,psutil
assert psutil.virtual_memory().available >= 4*1024**3, 'RAM insuficiente para reapertura NF4; se requieren 4 GiB libres'
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from peft import PeftModel,prepare_model_for_kbit_training
n,rev,ad=sys.argv[1:]
t=AutoTokenizer.from_pretrained(n,revision=rev,local_files_only=True,trust_remote_code=False)
b=AutoModelForCausalLM.from_pretrained(n,revision=rev,local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16,device_map={'':0},attn_implementation='eager')
b=prepare_model_for_kbit_training(b,use_gradient_checkpointing=False)
m=PeftModel.from_pretrained(b,ad,local_files_only=True).eval()
x=t('Orden de ensayo: consultar el estado del espacio.',return_tensors='pt').to('cuda')
with torch.inference_mode():r=m(**x).logits[0,-1,:8].float().cpu().tolist()
print('READBACK='+json.dumps(r))
'''
    r = subprocess.run([sys.executable, '-c', codigo, f['id'], f['revision'], str(adaptador)],
                       capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert r.returncode == 0, r.stderr
    obtenido = json.loads(next(s.removeprefix('READBACK=') for s in r.stdout.splitlines() if s.startswith('READBACK=')))
    assert max(abs(a-b) for a,b in zip(esperado, obtenido, strict=True)) < .02
