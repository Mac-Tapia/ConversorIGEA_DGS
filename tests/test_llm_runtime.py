"""047:RF-19: una publicación fallida no instala ni anuncia un modelo completo."""
import json
import pytest


def test_checkpoint_incompleto_no_se_publica(tmp_path):
    """047:RF-19: ni un checkpoint parcial ni archivos sin hash acreditan un alumno."""
    from igea_dgs.asistente.llm_runtime import verificar_checkpoint
    (tmp_path/'estado.json').write_text(json.dumps({'training_completed':False}),encoding='utf-8')
    with pytest.raises(ValueError,match='complet'):
        verificar_checkpoint(tmp_path)


def test_checkpoint_que_cambio_se_rechaza(tmp_path):
    """047:RF-19: la recarga exige los mismos pesos que fueron entrenados."""
    from igea_dgs.asistente.llm_runtime import verificar_checkpoint
    from igea_dgs.asistente.llm_destilacion import custodiar
    f=tmp_path/'adaptador';f.mkdir()
    p=f/'adapter_model.safetensors';p.write_bytes(b'contrato, no pesos de aceptacion')
    sha=custodiar(p,localizador='contrato')['sha256']
    (tmp_path/'estado.json').write_text(json.dumps({'training_completed':True,
        'artefactos':{'adaptador/adapter_model.safetensors':sha}}),encoding='utf-8')
    p.write_bytes(b'cambiado')
    with pytest.raises(ValueError,match='alterado'):
        verificar_checkpoint(tmp_path)
