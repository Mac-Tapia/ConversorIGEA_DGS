"""043:RF-7 — Regresiones del donante de reentrenamiento."""
import json


def test_verify_exige_siete_etapas_entrenadas_con_fail_on_incomplete(tmp_path, capsys):
    from tools.reentrenar_modelos import verificar

    reporte = tmp_path / 'report.json'
    nombres = ('transformer', 'clasificador', 'gru', 'pinn', 'evolutivos', 'embeddings', 'qlora')
    reporte.write_text(json.dumps({'complete': True, 'stages': [
        {'model': n, 'status': 'PROMOVIDO' if n != 'qlora' else 'RECHAZADO',
         'training_completed': True} for n in nombres]}),
        encoding='utf-8')

    assert verificar(reporte, fail_on_incomplete=True) == 0
    assert json.loads(capsys.readouterr().out)['all_trained'] is True


def test_verify_no_declara_entrenado_un_bloqueo(tmp_path):
    from tools.reentrenar_modelos import verificar

    reporte = tmp_path / 'report.json'
    nombres = ('transformer', 'clasificador', 'gru', 'pinn', 'evolutivos', 'embeddings', 'qlora')
    reporte.write_text(json.dumps({'complete': True, 'stages': [
        {'model': n, 'status': 'BLOQUEADO_POR_DATOS' if n == 'gru' else 'PROMOVIDO'} for n in nombres]}),
        encoding='utf-8')

    assert verificar(reporte, fail_on_incomplete=False) == 0
    assert verificar(reporte, fail_on_incomplete=True) == 2


def test_la_campana_pasa_el_experimento_autorizado_al_qlora(tmp_path):
    """043:RF-17 — el QLoRA de la campaña recibe la decisión o el experimento autorizado que pide 047:RF-59."""
    from types import SimpleNamespace

    from tools.reentrenar_modelos import orden_qlora

    base = dict(llm_dataset=tmp_path / 'corpus', qlora_model=None, qlora_revision=None, qlora_decision=None,
                qlora_experimento_autorizado=None)
    sin = orden_qlora(SimpleNamespace(**base), 'py', tmp_path / 'q')
    assert '--decision' not in sin and '--experimento-autorizado' not in sin
    con = orden_qlora(SimpleNamespace(**{**base, 'qlora_experimento_autorizado': '047-T7',
                                         'qlora_decision': tmp_path / 'd.json'}), 'py', tmp_path / 'q')
    assert con[con.index('--experimento-autorizado') + 1] == '047-T7'
    assert con[con.index('--decision') + 1] == str(tmp_path / 'd.json')
