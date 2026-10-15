"""Spec 016, T12: la web ofrece las obras nuevas y la distancia mínima de las cargas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apoyo import vincular_proyecto
from apoyo_pf_web import guion_falso  # noqa: F401
from igea_dgs.web.app import create_app

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = (RAIZ / 'frontend' / 'src' / 'components' / 'ObrasPF.tsx').read_text(encoding='utf-8')
CARGAS = (RAIZ / 'frontend' / 'src' / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
API = (RAIZ / 'frontend' / 'src' / 'api.ts').read_text(encoding='utf-8')
TYPES = (RAIZ / 'frontend' / 'src' / 'types.ts').read_text(encoding='utf-8')
CON, SIN = 'Con proyecto', 'Sin proyecto'
TIPO = {'nombre': 'AAAC_120', 'clase': 'TypLne'}


@pytest.fixture()
def client(tmp_path, monkeypatch, guion_falso):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _espacio(client):
    wid = client.post('/api/workspaces').json()['id']
    vincular_proyecto(client, wid, 'P', ['TA225', 'IN111'])
    return wid


# --------------------------------------------------------------------------- API
def test_las_obras_nuevas_se_guardan_con_sus_campos(client):
    """016:RF-68, 016:RF-69, 016:RF-70 — enlace (que recibe, que cede, tipo, distancia mínima y
    extremos), migración (nodo y tensión) y sección de toda la troncal con tipo de cable."""
    wid = _espacio(client)
    url = f'/api/workspaces/{wid}/obras'
    enlace = {'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111', 'casos': [CON], 'tipo': TIPO,
              'minima_m': 5, 'destino': '-14.03, -75.77'}
    migracion = {'clase': 'migracion', 'alimentador': 'IN111', 'casos': [CON], 'nodo': 'NODE_7',
                 'kv_destino': 22.9}
    seccion = {'clase': 'seccion', 'alimentador': 'IN111', 'casos': [SIN, CON], 'toda_troncal': True,
               'tipo': TIPO, 'tipo_cable': {'nombre': 'N2XSY_120', 'clase': 'TypLne'}}
    for obra in (enlace, migracion, seccion):
        r = client.post(url, json=obra)
        assert r.status_code == 201, r.text
    guardadas = client.get(url).json()
    assert guardadas[0]['cede'] == 'IN111' and guardadas[0]['minima_m'] == 5
    assert guardadas[1]['nodo'] == 'NODE_7' and guardadas[2]['toda_troncal'] is True
    assert guardadas[2]['tipo_cable']['nombre'] == 'N2XSY_120'


@pytest.mark.parametrize('obra, dice', [
    ({'clase': 'enlace', 'alimentador': 'TA225', 'cede': 'IN111', 'casos': [SIN, CON], 'tipo': TIPO},
     'solo en «Con proyecto»'),
    ({'clase': 'migracion', 'alimentador': 'IN111', 'casos': [SIN, CON], 'nodo': 'N7', 'kv_destino': 22.9},
     'solo en «Con proyecto»'),
    ({'clase': 'terna', 'alimentador': 'IN111', 'casos': [SIN]}, 'pasa siempre'),
])
def test_la_api_rechaza_los_casos_que_no_valen(client, obra, dice):
    """016:RF-71, 016:RF-13 — la API no guarda un enlace o una migración fuera de «Con
    proyecto», ni una obra solo en «Sin proyecto»."""
    wid = _espacio(client)
    r = client.post(f'/api/workspaces/{wid}/obras', json=obra)
    assert r.status_code == 400 and dice in r.text


# --------------------------------------------------------------------------- front
def test_el_formulario_ofrece_las_obras_nuevas():
    """016:RF-68, 016:RF-69, 016:RF-70, 016:RF-71 — clases nuevas, campos del enlace y de la
    migración, «toda la troncal» con tipo de cable, y solo «Con proyecto» para las dos nuevas."""
    for pieza in ("clase: 'enlace'", "clase: 'migracion'", "'Alimentador que cede'",
                  "texto('nodo'", "campo('minima_m'", "texto('origen'", "texto('destino'",
                  'Toda la troncal', 'Tipo de los tramos de cable', 'toda_troncal:', 'tipo_cable:',
                  "const SOLO_CON: ClaseObra[] = ['enlace', 'migracion']", 'soloCon ? [CON] : CASOS_OBRA'):
        assert pieza in OBRAS, pieza
    assert "| 'enlace' | 'migracion'" in TYPES and 'nodo?: string' in TYPES


def test_un_nodo_ajeno_se_dice_al_simular():
    """016:RF-72 — el error de un nodo que no es del alimentador sale de la simulación, en la
    fila de la obra, antes de aplicarla."""
    assert '{o.error && <div className="badge err">{o.error}</div>}' in OBRAS
    assert 'api.obrasSimular' in OBRAS


def test_el_paso_de_cargas_pide_la_distancia_minima(client, tmp_path):
    """016:RF-73 — el paso de cargas nuevas tiene el campo y lo envía; la API lo lleva al plan
    y rechaza una negativa."""
    assert 'Distancia mínima a una barra (m)' in CARGAS and "fd.append('minima_m'" in API
    wid = client.post('/api/workspaces').json()['id']
    vincular_proyecto(client, wid, 'P', ['F1'])
    nueva = json.dumps({'SED': 'N1', 'barra': 'B1', 'kVA_instalado': 50, 'Kw': 20, 'FP': 0.9})
    url = f'/api/workspaces/{wid}/lote/plan'
    r = client.post(url, data={'project': 'P', 'feeders': ['F1'], 'nueva': nueva, 'minima_m': '5'})
    assert r.status_code == 200, r.text
    (plan,) = tmp_path.rglob(f"cargas_pf_{r.json()['token']}.json")
    assert json.loads(plan.read_text(encoding='utf-8'))['minima_m'] == 5.0
    r = client.post(url, data={'project': 'P', 'feeders': ['F1'], 'nueva': nueva, 'minima_m': '-1'})
    assert r.status_code == 422
