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
