"""043:RF-1 043:RF-5 — Registro común: candidato inmutable, puntero atómico, reapertura y reversión."""
from __future__ import annotations

import json
import sys

import pytest


def _payload(tmp_path, status='PROMOVIDO', contenido=b'pesos'):
    artefacto = tmp_path / 'pesos.bin'
    artefacto.write_bytes(contenido)
    return dict(
        model_manifest={'model': 'transformer', 'commit': 'a' * 40, 'seeds': [1, 2, 3]},
        dataset_manifest={'sha256': 'd' * 64}, metrics={'macro_f1': .91},
        decision={'status': status, 'gates': {'approved': status == 'PROMOVIDO'}},
        smoke_reload={'ok': status == 'PROMOVIDO', 'predictions': ['convertir']},
        artifacts=[artefacto])


def test_cuatro_estados_y_promocion_reversion_atomicas(tmp_path):
    from igea_dgs.model_registry import EstadoModelo, RegistroModelo

    assert {e.value for e in EstadoModelo} == {
        'PROMOVIDO', 'RECHAZADO', 'BLOQUEADO_POR_DATOS', 'ERROR_ENTORNO'}
    registro = RegistroModelo(tmp_path / 'registro')
    primero = registro.registrar_candidato('transformer', **_payload(tmp_path))
    activo1 = registro.promover('transformer', primero['candidate_id'])
    assert activo1['candidate_id'] == primero['candidate_id']

    segundo = registro.registrar_candidato('transformer', **_payload(tmp_path, contenido=b'pesos-2'))
    assert segundo['candidate_id'] != primero['candidate_id']
    registro.promover('transformer', segundo['candidate_id'])
    assert registro.volver_al_anterior('transformer')['candidate_id'] == primero['candidate_id']


def test_fallo_entre_candidato_y_puntero_no_cambia_activo(tmp_path, monkeypatch):
    from igea_dgs.model_registry import RegistroModelo

    registro = RegistroModelo(tmp_path / 'registro')
    candidato = registro.registrar_candidato('transformer', **_payload(tmp_path))
    registro.promover('transformer', candidato['candidate_id'])
    antes = registro.activo('transformer')
    nuevo = registro.registrar_candidato('transformer', **_payload(tmp_path, contenido=b'nuevo'))
    monkeypatch.setattr(registro, '_reemplazar_json', lambda *_a, **_kw: (_ for _ in ()).throw(OSError('corte')))
    with pytest.raises(OSError, match='corte'):
        registro.promover('transformer', nuevo['candidate_id'])
    assert registro.activo('transformer') == antes


def test_reapertura_ocurre_en_subproceso_y_falla_cerrado(tmp_path):
    from igea_dgs.model_registry import reabrir_en_subproceso

    ok = reabrir_en_subproceso([sys.executable, '-c', 'print("{\\"ok\\": true}")'])
    mal = reabrir_en_subproceso([sys.executable, '-c', 'raise SystemExit(3)'])
    assert ok['ok'] is True and ok['returncode'] == 0
    assert mal['ok'] is False and mal['returncode'] == 3


def test_artefacto_modificado_no_promueve(tmp_path):
    """043:RF-5 — los bytes copiados deben seguir coincidiendo con su huella."""
    from igea_dgs.model_registry import RegistroModelo
    registro = RegistroModelo(tmp_path / 'registro')
    candidato = registro.registrar_candidato('gru', **_payload(tmp_path))
    from pathlib import Path
    (Path(candidato['path']) / 'artifacts' / 'pesos.bin').write_bytes(b'alterado')
    with pytest.raises(ValueError, match='integridad'):
        registro.promover('gru', candidato['candidate_id'])
    assert registro.activo('gru') is None


@pytest.mark.parametrize('modelo', ['../otro', '/absoluto', 'a/b', 'a\\b'])
def test_identidad_modelo_no_es_ruta(tmp_path, modelo):
    """043:RF-1 — los modelos no pueden salir del registro de candidatos."""
    from igea_dgs.model_registry import RegistroModelo
    with pytest.raises(ValueError):
        RegistroModelo(tmp_path / 'registro').registrar_candidato(modelo, **_payload(tmp_path))
