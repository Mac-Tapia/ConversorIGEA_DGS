"""Spec 017: el informe de estudio desde la web, con lo que guardaron los estudios."""
from __future__ import annotations

import json
import time
from pathlib import Path

import docx
import pytest

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402


def _medida(vmin, kvar_perdidas=55.0):
    return {'converge': True, 'barras': [['CAB', 1.0], ['N1', vmin]], 'elementos': [['L1', 'ElmLne', 60.0]],
            'vm_min': vmin, 'vm_min_barra': 'N1', 'vm_max': 1.0, 'vm_max_barra': 'CAB', 'mas_cargado': 'L1',
            'cargabilidad_max': 60.0, 'cabecera_kw': 6000.0, 'cabecera_kvar': 3000.0, 'perdidas_kw': 300.0,
            'perdidas_kvar': kvar_perdidas,
            'vm_min_fases': {'A': [vmin, 'N1'], 'B': [vmin + 0.01, 'N1'], 'C': [vmin + 0.02, 'N1']}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    modelo = docx.Document()
    modelo.sections[0].header.add_table(1, 1, width=modelo.sections[0].page_width).cell(0, 0).text = \
        'INFORME TECNICO Nº :\nGT-019-PR'
    modelo.add_paragraph('Texto del modelo: AGROINDUSTRIAS DEL MODELO.')
    modelo.save(tmp_path / 'modelo.docx')
    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text(json.dumps({'informes': {
        'modelo_estudio': str(tmp_path / 'modelo.docx'), 'bandas_tension_pct': [95, 105],
        'bandas_cargabilidad_pct': [80, 100], 'cabecera': {'numero': 'INFORME TECNICO'}, 'norma': 'NTCSE'}}),
        encoding='utf-8')
    monkeypatch.setenv('IGEA_PERFIL_EMPRESA', str(perfil))
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _espacio(client, tmp_path, *, con=True) -> tuple[str, Path]:
    wid = client.post('/api/workspaces').json()['id']
    salida = tmp_path / 'web' / wid / 'salida'
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'estudio_sin_flujo_desequilibrado_a.json').write_text(
        json.dumps({'medidas': {'AL01': _medida(0.90)}}), encoding='utf-8')
    time.sleep(0.01)
    if con:
        (salida / 'estudio_con_flujo_desequilibrado_b.json').write_text(
            json.dumps({'medidas': {'AL01': _medida(0.96)}}), encoding='utf-8')
    return wid, salida


FORMULARIO = {'alimentador': 'AL01', 'fecha': '2026-10-15', 'lugar': 'Ica', 'numero': 'GT-300-PR',
              'asunto': 'CAÍDA DE TENSIÓN DEL CLIENTE X', 'destinatario': 'ING. Z',
              'antecedentes': ['El cliente X reclama baja tensión.'],
              'limites': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}


def test_informe_de_estudio_desde_los_estudios_guardados(client, tmp_path):
    """017:RF-1b, 017:RF-26, 017:RF-29, 017:RF-30 — el Word sale de los estudios de los dos casos y del formulario."""
    wid, salida = _espacio(client, tmp_path)
    obra = {'clase': 'condensador', 'alimentador': 'AL01', 'casos': ['Con proyecto'], 'barra': 'N7',
            'q_kvar': 300}
    r = client.post(f'/api/workspaces/{wid}/obras', json=obra)
    if r.status_code != 201:  # la validación de obras pide la red de DIgSILENT: se guarda a mano
        datos = json.loads((tmp_path / 'web' / wid / 'workspace.json').read_text(encoding='utf-8'))
        datos['obras'] = [obra]
        (tmp_path / 'web' / wid / 'workspace.json').write_text(json.dumps(datos), encoding='utf-8')
    job = client.post(f'/api/workspaces/{wid}/informes/estudio', json=FORMULARIO)
    assert job.status_code == 202
    fin = esperar_trabajo(client, job.json())
    assert fin['status'] == 'done', fin
    resultado = fin['result']
    informe = salida / resultado['informe']
    texto = '\n'.join(p.text for p in docx.Document(informe).paragraphs)
    assert 'CAÍDA DE TENSIÓN DEL CLIENTE X' in texto and 'El cliente X reclama baja tensión.' in texto
    assert 'AGROINDUSTRIAS DEL MODELO' not in texto and 'Sin proyecto' not in texto
    assert '0,900 p.u.' in texto
    assert resultado['estudios'][0] == 'estudio_sin_flujo_desequilibrado_a.json'


def test_sin_estudios_de_sin_proyecto_lo_dice(client, tmp_path):
    """017:RF-29 — sin el flujo de «Sin proyecto» guardado, el trabajo dice qué estudio falta."""
    wid = client.post('/api/workspaces').json()['id']
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio', json=FORMULARIO).json())
    assert fin['status'] == 'failed' and 'estudio de flujo' in (fin['error'] or '')
