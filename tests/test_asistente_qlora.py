"""047:RF-8 — el adaptador QLoRA: la herramienta no promueve ni acepta otra base, y el adaptador se reabre.

Sin GPU. La carga cuantizada real y el paso en CUDA son de la tarea T7 y no se acreditan aquí.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _herramienta():
    spec = importlib.util.spec_from_file_location('asistente_qlora_047', RAIZ / 'tools/asistente_qlora.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def sin_gpu(monkeypatch):
    from convertersmartgrid.asistente import llm_destilacion
    monkeypatch.setattr(llm_destilacion, 'auditar_fuentes_corpus', lambda _d: {'valid': True})
    monkeypatch.setattr(llm_destilacion, 'ficha_base', lambda: {'id': 'base/fijada', 'revision': 'a' * 40})
    monkeypatch.setattr(llm_destilacion, 'entrenar_epoca', lambda *a, **k: pytest.fail('no debe entrenar'))


@pytest.mark.parametrize('extra', [['--modelo', 'otra/base'], ['--revision', 'main'], ['--epocas', '9']])
def test_otra_base_o_mas_epocas_se_rechazan_antes_de_la_gpu(tmp_path, sin_gpu, extra):
    """047:RF-8 — la base y el presupuesto están fijados: lo distinto falla sin cargar nada y deja su informe."""
    dataset = tmp_path / 'corpus'
    dataset.mkdir()
    salida = tmp_path / 'qlora'
    assert _herramienta().main(['entrenar', '--dataset', str(dataset), '--salida', str(salida), *extra]) == 2
    assert (salida / 'training_manifest.json').is_file()


def test_preflight_no_entrena_ni_promueve(tmp_path, sin_gpu, capsys):
    """047:RF-8 — comprobar los datos no es ajustar: queda rechazado, sin pesos y sin promoción."""
    dataset = tmp_path / 'corpus'
    dataset.mkdir()
    salida = tmp_path / 'qlora'
    assert _herramienta().main(['preflight', '--dataset', str(dataset), '--salida', str(salida)]) == 0
    informe = json.loads((salida / 'training_manifest.json').read_text(encoding='utf-8'))
    assert informe['status'] == 'RECHAZADO' and informe['promovido'] is False and informe['training_completed'] is False


#: Dos procesos, y pytest no carga Torch. Un modelo diminuto, sin descargas ni GPU: lo que se prueba es la reapertura.
_GUARDAR = """
import json, sys, torch
from peft import LoraConfig, get_peft_model
from transformers import GPT2Config, GPT2LMHeadModel
ruta = sys.argv[1]
torch.manual_seed(0)
base = GPT2LMHeadModel(GPT2Config(vocab_size=32, n_positions=16, n_embd=8, n_layer=1, n_head=1))
base.save_pretrained(ruta + '/base')
modelo = get_peft_model(base, LoraConfig(r=2, target_modules=['c_attn'], fan_in_fan_out=True, init_lora_weights=False)).eval()
modelo.save_pretrained(ruta + '/adaptador')
with torch.no_grad():
    salida = modelo(torch.arange(6).unsqueeze(0)).logits
print(json.dumps({'vocabulario': base.config.vocab_size, 'logits': salida[0, -1, :4].tolist()}))
"""
_REABRIR = """
import json, sys, torch
from peft import PeftModel
from transformers import AutoModelForCausalLM
ruta = sys.argv[1]
base = AutoModelForCausalLM.from_pretrained(ruta + '/base', local_files_only=True)
modelo = PeftModel.from_pretrained(base, ruta + '/adaptador', local_files_only=True).eval()
with torch.no_grad():
    salida = modelo(torch.arange(6).unsqueeze(0)).logits
print(json.dumps({'vocabulario': base.config.vocab_size, 'logits': salida[0, -1, :4].tolist()}))
"""


def _proceso(guion: str, ruta: Path) -> dict:
    r = subprocess.run([sys.executable, '-c', guion, str(ruta)], capture_output=True, text=True, timeout=300,
                       env={**os.environ, 'CUDA_VISIBLE_DEVICES': '-1', 'HF_HUB_OFFLINE': '1'})
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_adaptador_reabre(tmp_path):
    """047:RF-8 — un adaptador PEFT guardado se reabre en otro proceso con el mismo vocabulario y la misma salida."""
    guardado = _proceso(_GUARDAR, tmp_path)
    reabierto = _proceso(_REABRIR, tmp_path)
    assert reabierto['vocabulario'] == guardado['vocabulario'] == 32
    assert reabierto['logits'] == pytest.approx(guardado['logits'], abs=1e-6)
