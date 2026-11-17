"""107:RF-21 — la biblioteca normativa general en la web: las normas con su estado en una fecha, las reglas con su cita
y la subida de una norma a la capa del usuario (solo entra lo que cumple el esquema)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web(tmp_path, monkeypatch):
    from convertersmartgrid import biblioteca_normativa as bn
    from convertersmartgrid.web.app import create_app

    from convertersmartgrid.web import services

    monkeypatch.setenv(bn.VARIABLE_CAPA, str(tmp_path / 'capa'))
    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    with TestClient(create_app(tmp_path / 'web')) as cliente:
        yield cliente, tmp_path / 'capa'


def _norma(acto: str) -> dict:
    return {'acto': acto, 'titulo': f'Norma {acto}', 'estado_juridico': 'vigente_comprobada', 'sha256': 'a' * 64,
            'vigencia_desde': '2026-01-01',
            'reglas': [{'clave': 'prueba.valor', 'valor': 3, 'unidad': '-', 'articulo_o_anexo': 'art. 1',
                        'pagina': '1', 'lineas': '1', 'cita_literal': 'El valor es 3.'}]}


def test_107_rf21_la_web_lista_la_biblioteca_con_lo_que_obliga_en_la_fecha(web):
    cliente, _ = web
    r = cliente.get('/api/normativa', params={'fecha': '2026-11-17'}).json()
    normas = {n['acto']: n for n in r['normas']}
    assert r['fecha'] == '2026-11-17' and len(r['huella']) == 64
    assert normas['DS 028-2021-EM']['obliga'] and normas['DS 028-2021-EM']['reglas'] >= 3
    assert not normas['RCD 147-2017-OS/CD']['obliga']  # sin verificar: no obliga


def test_107_rf21_la_web_da_las_reglas_con_su_cita(web):
    cliente, _ = web
    r = cliente.get('/api/normativa/reglas', params={'acto': 'DS 028-2021-EM'}).json()
    assert r['acto'] == 'DS 028-2021-EM' and all(x['citada'] and x['cita_literal'] for x in r['reglas'])
    assert cliente.get('/api/normativa/reglas', params={'acto': 'no existe'}).status_code == 404


def test_107_rf21_la_web_sube_una_norma_y_rechaza_la_que_no_valida(web):
    cliente, capa = web
    buena = json.dumps({'esquema': 'registro_normativo_v1', 'normas': [_norma('RM 997-2026-MINEM/DM')]})
    r = cliente.post('/api/normativa', files={'file': ('mia.json', buena, 'application/json')})
    assert r.status_code == 200 and r.json()['actos'] == ['RM 997-2026-MINEM/DM'] and (capa / 'mia.json').is_file()
    lista = cliente.get('/api/normativa').json()['normas']
    assert any(n['acto'] == 'RM 997-2026-MINEM/DM' for n in lista)
    mala = json.dumps({'esquema': 'registro_normativo_v1', 'normas': [{'acto': 'X', 'titulo': 'X',
                                                                      'estado_juridico': 'inventado'}]})
    r = cliente.post('/api/normativa', files={'file': ('mala.json', mala, 'application/json')})
    assert r.status_code == 422 and not (capa / 'mala.json').exists()
    r = cliente.post('/api/normativa', files={'file': ('norma.pdf', b'%PDF', 'application/pdf')})
    assert r.status_code == 422
