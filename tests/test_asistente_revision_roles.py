"""047:RF-5 / RF-6 / RF-7 — revisión local, con dictámenes y sin autoridad nativa."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from convertersmartgrid.asistente.revision_roles import revisar_propuesta


def paquete(tmp_path):
    fuente = tmp_path / 'fuente.txt'
    fuente.write_text('evidencia verificable', encoding='utf-8')
    import hashlib
    contexto = SimpleNamespace(project='P1', source_fingerprint='abc')
    evidencia = {'e1': {'archivo': str(fuente), 'sha256': hashlib.sha256(fuente.read_bytes()).hexdigest(),
                        'proyecto': 'P1', 'fuente': 'abc'}}
    return contexto, evidencia


def revisor(rol, propuesta, evidencia, contexto, ronda):
    return {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [], 'contradicciones': []}


def test_critico_sin_evidencia_no_aprueba(tmp_path):
    """047:RF-5 / 047:RF-6 — coincidencia de cuatro roles sin fuente no aprueba."""
    contexto, _ = paquete(tmp_path)
    r = revisar_propuesta({}, {}, contexto=contexto, revisor=revisor)
    assert not r['aprobada'] and not r['autoriza_ejecucion']
    assert {d['rol'] for d in r['dictamenes']} == {'fuentes', 'fisica', 'coste', 'riesgo'}
    assert all(d['decision'] == 'bloqueada' for d in r['dictamenes'])


def test_revisores_con_evidencia_y_restricciones_verificadas(tmp_path):
    """047:RF-5 / 047:RF-6 — dictámenes separados y huella compartida."""
    contexto, evidencia = paquete(tmp_path)
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia,
                          contexto=contexto, revisor=revisor)
    assert r['aprobada'] and not r['autoriza_ejecucion']
    assert len({d['entrada_sha256'] for d in r['dictamenes']}) == 1
    assert all(d['evidencia_ids'] == ['e1'] for d in r['dictamenes'])


def test_desacuerdo_fisico_bloquea(tmp_path):
    """047:RF-6 — consenso textual nunca sustituye la restricción determinista."""
    contexto, evidencia = paquete(tmp_path)
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': False}}, evidencia,
                          contexto=contexto, revisor=revisor)
    assert not r['aprobada'] and 'restricciones' in r['motivo']


def test_dos_rondas_y_cancelacion(tmp_path):
    """047:RF-7 — tope real, cancelación entre intervenciones y sin ruta de escritura."""
    contexto, evidencia = paquete(tmp_path)
    llamadas = []
    def indeciso(*args):
        llamadas.append(args[0])
        return {'decision': 'revisar', 'evidencia_ids': ['e1'], 'incertidumbres': ['falta contraste'],
                'contradicciones': []}
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=indeciso, max_rondas=2)
    assert len(llamadas) == 8 and r['rondas'] == 2 and not r['aprobada']
    llamadas.clear()
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=indeciso,
                          cancelado=lambda: len(llamadas) >= 1)
    assert len(llamadas) == 1 and r['cancelada'] and not r['aprobada']
    with pytest.raises(ValueError, match='rondas'):
        revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=3)


def test_evidencia_alterada_no_aprueba(tmp_path):
    """047:RF-6 — el identificador nominal no basta, se relee el archivo y su hash."""
    contexto, evidencia = paquete(tmp_path)
    from pathlib import Path
    Path(evidencia['e1']['archivo']).write_text('alterada', encoding='utf-8')
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=revisor)
    assert not r['aprobada']
