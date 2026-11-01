"""043:RF-12: carga local de pesos y ensayo PEFT, sin promocion ni datos privados.

Exige las descargas del catalogo completas; no omite modelos ausentes.
El paso LoRA es una prueba de entorno, no un ajuste validado del agente.
"""
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
    from igea_dgs.training_coordinator import exigir_memoria_ml
    minimo_gb = 6 if 'qwen' in request.node.name else 4 if 'bge' in request.node.name else 3
    exigir_memoria_ml(minimo_gb, minimo_commit_gib=8. if 'qwen' in request.node.name else 6.)
    from igea_dgs.training_coordinator import BloqueoGPU
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    ruta = Path(os.environ.get('IGEA_ML_GPU_LOCK') or str(Path(tempfile.gettempdir()) / 'igea-dgs-gpu.lock'))
    with BloqueoGPU(ruta, 'ensayo-pesos-preentrenados'):
        # El supervisor no importa Torch: cada trabajador libera su contexto al salir.
        yield


def _codificar_e5(tmp_path):
    import numpy as np
    from sentence_transformers import SentenceTransformer
    f = _ficha('multilingual-e5-base')
    m = SentenceTransformer(f['id'], revision=f['revision'], local_files_only=True, device='cuda',
                           model_kwargs={'device_map': {'': 0}})
    r = m.encode(['query: flujo de potencia', 'query: demanda electrica'], normalize_embeddings=True)
    assert r.shape == (2, 768) and np.isfinite(r).all()
    assert np.allclose(np.linalg.norm(r, axis=1), 1., atol=1e-5)
    (tmp_path / 'embeddings.json').write_text(json.dumps({'shape': list(r.shape), 'device': str(m.device)}), encoding='utf-8')


def _inferir_bge(tmp_path):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    f = _ficha('bge-reranker-v2-m3')
    tok = AutoTokenizer.from_pretrained(f['id'], revision=f['revision'], local_files_only=True, trust_remote_code=False)
    m = AutoModelForSequenceClassification.from_pretrained(f['id'], revision=f['revision'],
        local_files_only=True, trust_remote_code=False, dtype=torch.float16, device_map={'': 0}).eval()
    x = tok([['flujo de potencia', 'calculo electrico de tensiones'],
             ['flujo de potencia', 'receta de una tortilla']], padding=True, return_tensors='pt').to('cuda')
    with torch.inference_mode():
        r = m(**x).logits
    assert r.shape == (2, 1) and torch.isfinite(r).all() and r[0].item() != r[1].item()
    (tmp_path / 'pares.json').write_text(json.dumps({'logits': r.float().cpu().tolist(), 'cuda': r.is_cuda}), encoding='utf-8')


def _entrenar_nf4(tmp_path):
    import torch
    assert torch.cuda.is_available()
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
    adaptador = tmp_path / 'adaptador'; m.save_pretrained(adaptador, safe_serialization=True, save_embedding_layers=False)
    assert (adaptador / 'adapter_model.safetensors').is_file()
    (tmp_path / 'entrenamiento.json').write_text(json.dumps({
        'id': f['id'], 'revision': f['revision'], 'esperado': esperado,
        'perdida': perdida.item(), 'pasos': 1, 'adaptador_cambio': True,
        'gpu_pico_bytes': torch.cuda.max_memory_allocated(), 'activado': False,
    }), encoding='utf-8')


def _reabrir_nf4(tmp_path):
    from igea_dgs.training_coordinator import exigir_memoria_ml
    exigir_memoria_ml(4., minimo_commit_gib=8.)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel, prepare_model_for_kbit_training
    f = json.loads((tmp_path / 'entrenamiento.json').read_text(encoding='utf-8'))
    tok = AutoTokenizer.from_pretrained(f['id'], revision=f['revision'], local_files_only=True, trust_remote_code=False)
    base = AutoModelForCausalLM.from_pretrained(f['id'], revision=f['revision'], local_files_only=True,
        trust_remote_code=False, dtype=torch.bfloat16, device_map={'': 0}, attn_implementation='eager')
    base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
    modelo = PeftModel.from_pretrained(base, tmp_path / 'adaptador', local_files_only=True).eval()
    x = tok('Orden de ensayo: consultar el estado del espacio.', return_tensors='pt').to('cuda')
    with torch.inference_mode():
        obtenido = modelo(**x).logits[0, -1, :8].float().cpu().tolist()
    error = max(abs(a-b) for a,b in zip(f['esperado'], obtenido, strict=True))
    assert error < .02
    (tmp_path / 'reapertura.json').write_text(json.dumps({
        'logits': obtenido, 'error_maximo': error, 'cuda': True, 'activado': False,
    }), encoding='utf-8')


def _ejecutar_trabajador(accion, tmp_path):
    r = subprocess.run([sys.executable, '-X', 'utf8', __file__, accion, str(tmp_path)],
                       capture_output=True, text=True, encoding='utf-8', timeout=240)
    assert r.returncode == 0, r.stdout + r.stderr


def test_e5_codifica_localmente(tmp_path):
    """043:RF-12: pesos, pooling y codificacion CUDA en trabajador liberable."""
    _ejecutar_trabajador('e5', tmp_path)
    r = json.loads((tmp_path / 'embeddings.json').read_text(encoding='utf-8'))
    assert r['shape'] == [2, 768] and r['device'].startswith('cuda')


def test_bge_inferencia_de_pares_local(tmp_path):
    """043:RF-12: cross-encoder CUDA real, sin acreditar benchmark de recuperacion."""
    _ejecutar_trabajador('bge', tmp_path)
    r = json.loads((tmp_path / 'pares.json').read_text(encoding='utf-8'))
    assert r['cuda'] and len(r['logits']) == 2 and r['logits'][0] != r['logits'][1]


def test_qwen_nf4_paso_lora_y_reapertura_real(tmp_path):
    """043:RF-12 / 047:RF-14: trabajadores CUDA consecutivos, sin conservar la primera copia."""
    for accion in ('entrenar', 'reabrir'):
        _ejecutar_trabajador(accion, tmp_path)
    assert (tmp_path / 'adaptador/adapter_model.safetensors').is_file()
    entrenamiento = json.loads((tmp_path / 'entrenamiento.json').read_text(encoding='utf-8'))
    reapertura = json.loads((tmp_path / 'reapertura.json').read_text(encoding='utf-8'))
    assert entrenamiento['adaptador_cambio'] and entrenamiento['pasos'] == 1
    assert reapertura['error_maximo'] < .02 and reapertura['cuda']
    evidencia = os.environ.get('IGEA_ENSAYO_NF4_EVIDENCIA')
    if evidencia:
        import shutil
        shutil.copytree(tmp_path, evidencia, dirs_exist_ok=False)


if __name__ == '__main__':
    {'entrenar': _entrenar_nf4, 'reabrir': _reabrir_nf4,
     'e5': _codificar_e5, 'bge': _inferir_bge}[sys.argv[1]](Path(sys.argv[2]))
