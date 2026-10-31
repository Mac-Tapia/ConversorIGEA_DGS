"""043:RF-5 043:RF-7 — reanudación y verificación del contrato completo."""
import json

import pytest


def test_resume_config_distinta_rechaza(tmp_path):
    """043:RF-7 — no reutilizar una ejecución de otras semillas/datos/configuración."""
    from igea_dgs.training_coordinator import TrainingCoordinator, TrainingStage
    etapas = [TrainingStage('gru', lambda: {'status': 'RECHAZADO'}, uses_gpu=False)]
    TrainingCoordinator(etapas, tmp_path, config_hash='a' * 64).run()
    with pytest.raises(ValueError, match='configuraci'):
        TrainingCoordinator(etapas, tmp_path, config_hash='b' * 64).run(resume=True)


def test_verify_rechaza_familias_duplicadas(tmp_path):
    """043:RF-7 — siete filas de una sola familia no son siete modelos entrenados."""
    from tools.reentrenar_modelos import verificar
    ruta = tmp_path / 'report.json'
    ruta.write_text(json.dumps({'complete': True, 'stages': [
        {'model': 'gru', 'status': 'PROMOVIDO'} for _ in range(7)]}), encoding='utf-8')
    assert verificar(ruta, fail_on_incomplete=True) != 0


def test_config_se_valida_sin_entrenar(tmp_path, capsys):
    """043:RF-2 043:RF-7 — inspección reproducible antes de ocupar GPU o motor nativo."""
    from dataclasses import asdict
    from test_experimentos import contexto
    from tools.reentrenar_modelos import main
    ruta = tmp_path / 'config.json'
    ruta.write_text(json.dumps({'schema_version': 1, 'contexto': asdict(contexto()),
        'algoritmo': 'gru', 'semillas': [11, 23], 'revision': 'revision-fijada',
        'politica': {'cobertura_objetivo': 0.9}}), encoding='utf-8')
    assert main(['run', '--config', str(ruta), '--validar-config']) == 0
    resultado = json.loads(capsys.readouterr().out)
    assert resultado['etapas'] == ['gru'] and len(resultado['config_hash']) == 64
    assert not (tmp_path / 'report.json').exists()
