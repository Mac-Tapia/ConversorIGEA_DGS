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
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
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


def _corpus_redaccion_sellado(tmp_path):
    from convertersmartgrid.aplicacion.asistente import corpus_redaccion as cr
    sellar = getattr(cr, 'sellar_corpus_redaccion', None)
    assert callable(sellar), 'no hay puente del corpus aprobado al corpus sellado'
    carpeta = tmp_path / 'pide'
    carpeta.mkdir()
    # 072:RF-20: empresa y textos ficticios, casos de prueba del conversor.
    frags = [{'record_id': f'r{i}', 'empresa': 'Empresa de prueba', 'relative_path': f'PIDE X/{i}.docx',
              'location': 'document', 'periodo': '2026', 'text': t}
             for i, t in enumerate(['La SET Puerto Imaginario atiende 12 MW de la demanda.', 'CRITERIOS DE DISEÑO'])]
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    for f, origen, uso in zip(frags, ('humano', 'maestro'), ('redaccion', 'formato')):
        cr.registrar_revision(carpeta / 'revision_redaccion.jsonl', f, revisor='revisor de prueba', origen=origen,
                              aprobado=True, uso=uso)
    dataset = tmp_path / 'sellado'
    sellar(carpeta, dataset)
    return dataset


def test_preflight_lee_el_corpus_de_redaccion_sellado(tmp_path, sin_gpu):
    """072:RF-50 — el corpus de redacción aprobado y sellado pasa el preflight con su propia auditoría; no entrena."""
    dataset = _corpus_redaccion_sellado(tmp_path)
    salida = tmp_path / 'qlora'
    assert _herramienta().main(['preflight', '--dataset', str(dataset), '--salida', str(salida)]) == 0
    informe = json.loads((salida / 'training_manifest.json').read_text(encoding='utf-8'))
    assert informe['auditoria']['tipo_corpus'] == 'redaccion_pide' and informe['auditoria']['ejemplos'] == 2
    assert informe['auditoria']['por_origen'] == {'humano': 1, 'maestro': 1}
    assert informe['training_completed'] is False and informe['promovido'] is False


def test_entrenar_admite_el_corpus_de_redaccion(tmp_path, sin_gpu, monkeypatch):
    """072:RF-51 — `entrenar` acepta el corpus de redacción sellado, lo audita y entrena sin promover nada."""
    import contextlib
    from convertersmartgrid.aplicacion import trabajadores_ml
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    dataset = _corpus_redaccion_sellado(tmp_path)
    llamadas = []

    def entrenar(ds, destino, **k):
        llamadas.append((Path(ds), k['epoca'], sorted(k.get('lectores') or {})))
        destino.mkdir(parents=True)
        return {'checkpoint': str(destino), 'epoca': k['epoca']}

    monkeypatch.setattr(llm_destilacion, 'entrenar_epoca', entrenar)
    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', lambda _n: contextlib.nullcontext())
    salida = tmp_path / 'qlora'
    assert _herramienta().main(['entrenar', '--dataset', str(dataset), '--salida', str(salida)]) == 0
    informe = json.loads((salida / 'training_manifest.json').read_text(encoding='utf-8'))
    assert llamadas == [(dataset, 1, ['redaccion_pide'])]
    assert informe['auditoria']['tipo_corpus'] == 'redaccion_pide' and informe['promovido'] is False
    assert informe['candidate_status'] == 'CANDIDATO' and informe['gates'] == {'approved': False}


def test_entrenar_reanuda_desde_un_punto_de_control(tmp_path, sin_gpu, monkeypatch):
    """047:RF-84 — `entrenar --reanudar DIR` retoma la época desde ese punto de control (entrenar_epoca con desde=DIR,
    que verifica configuración, base y época); sin la opción, desde cero. (23-11: una suspensión del equipo cortó la
    época 1 de 047 T7c en el ejemplo 1 352 de 3 280 con un punto de control en la actualización 128.)"""
    import contextlib
    from convertersmartgrid.aplicacion import trabajadores_ml
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    dataset = _corpus_redaccion_sellado(tmp_path)
    punto = tmp_path / 'previa' / 'epoca_1' / 'progreso_000128'
    punto.mkdir(parents=True)
    llamadas = []

    def entrenar(ds, destino, **k):
        llamadas.append((k['epoca'], k.get('desde')))
        destino.mkdir(parents=True)
        return {'checkpoint': str(destino), 'epoca': k['epoca']}

    monkeypatch.setattr(llm_destilacion, 'entrenar_epoca', entrenar)
    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', lambda _n: contextlib.nullcontext())
    try:
        codigo = _herramienta().main(['entrenar', '--dataset', str(dataset), '--salida', str(tmp_path / 'q1'),
                                      '--reanudar', str(punto)])
    except SystemExit as exc:      # sin la opción, argparse sale con 2
        codigo = exc.code
    assert codigo == 0
    assert llamadas == [(1, punto)]
    informe = json.loads((tmp_path / 'q1' / 'training_manifest.json').read_text(encoding='utf-8'))
    assert informe['reanudado_desde'] == str(punto) and informe['promovido'] is False
    llamadas.clear()
    assert _herramienta().main(['entrenar', '--dataset', str(dataset), '--salida', str(tmp_path / 'q2')]) == 0
    assert llamadas == [(1, None)]


class _Tok:
    """Doble de tokenizador: un token por carácter y la plantilla de chat a la vista."""
    eos_token = '¶'

    def apply_chat_template(self, mensajes, tokenize=False, add_generation_prompt=True):
        return ''.join(f"<{m['role']}>{m['content']}" for m in mensajes) + '<assistant>'

    def encode(self, texto, add_special_tokens=False):
        return [ord(c) for c in texto]


def test_el_prompt_lo_elige_el_tipo_de_corpus(tmp_path, monkeypatch):
    """072:RF-51 — el corpus de redacción entrena con su prompt sellado; el de órdenes sigue con el del alumno."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    from convertersmartgrid.aplicacion.asistente.tareas import sistema_alumno
    elegir = getattr(llm_destilacion, 'ejemplos_de_entrenamiento', None)
    codificar = getattr(llm_destilacion, 'codificar_ejemplos', None)
    assert callable(elegir) and callable(codificar), 'el entrenamiento no elige el prompt por el tipo de corpus'
    from convertersmartgrid.aplicacion.asistente import corpus_redaccion as cr
    dataset = _corpus_redaccion_sellado(tmp_path)
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    lectores = {cr.TIPO_CORPUS: getattr(cr, 'leer_particion_redaccion', None)}
    registros, leido, sistema = elegir(dataset, lectores=lectores)
    assert sistema == meta['sistema'] != sistema_alumno() and leido['dataset_hash'] == meta['dataset_hash']
    assert len(registros) == 2 and all(r['particion'] == 'entrenamiento' for r in registros)
    [(ids, etiquetas), _] = codificar(_Tok(), sistema, registros, max_tokens=4096)
    prompt = _Tok().apply_chat_template([{'role': 'system', 'content': sistema},
                                         {'role': 'user', 'content': registros[0]['texto']}])
    assert ''.join(map(chr, ids)) == prompt + registros[0]['respuesta'] + '¶'
    assert etiquetas[:len(prompt)] == [-100] * len(prompt) and -100 not in etiquetas[len(prompt):]
    # El corpus de órdenes no cambia: sin tipo, su lector y el prompt del alumno.
    ordenes = tmp_path / 'ordenes'
    ordenes.mkdir()
    (ordenes / 'dataset_manifest.json').write_text(json.dumps({'schema_version': 2}), encoding='utf-8')
    monkeypatch.setattr(llm_destilacion, 'leer_particion_real',
                        lambda d, parte: ([{'texto': 'une A y B', 'respuesta': '{}'}], {'dataset_hash': 'h'}))
    registros, _meta, sistema = elegir(ordenes)
    assert sistema == sistema_alumno() and registros == [{'texto': 'une A y B', 'respuesta': '{}'}]
    corpus_ajeno = tmp_path / 'ajeno'
    corpus_ajeno.mkdir()
    (corpus_ajeno / 'dataset_manifest.json').write_text(json.dumps({'tipo_corpus': 'otro'}), encoding='utf-8')
    with pytest.raises(ValueError, match='tipo'):
        elegir(corpus_ajeno, lectores=lectores)
    # Sin su lector, el corpus de redacción tampoco se entrena con el prompt del alumno.
    with pytest.raises(ValueError, match='tipo'):
        elegir(dataset)


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


def test_ajuste_de_ordenes_sin_decision_necesaria_no_pide_la_gpu(tmp_path, sin_gpu, monkeypatch):
    """047:RF-59 — el corpus de órdenes no se ajusta sin `decidir_ajuste` «necesaria» o un experimento autorizado."""
    from convertersmartgrid.aplicacion import trabajadores_ml
    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', lambda _n: pytest.fail('no debe pedir la GPU'))
    dataset = tmp_path / 'corpus'
    dataset.mkdir()
    decision = tmp_path / 'decision.json'
    decision.write_text(json.dumps({'decision': 'bloqueada', 'motivos': ['3 de 200']}), encoding='utf-8')
    for extra in ([], ['--decision', str(decision)]):
        salida = tmp_path / ('salida' + str(len(extra)))
        assert _herramienta().main(['entrenar', '--dataset', str(dataset), '--salida', str(salida), *extra]) == 2
        informe = json.loads((salida / 'training_manifest.json').read_text(encoding='utf-8'))
        assert 'decidir_ajuste' in json.dumps(informe, ensure_ascii=False)
