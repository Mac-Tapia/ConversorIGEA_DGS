"""Spec 081, RF-70: el aviso del catálogo subido dice dónde entran sus fichas (032:RF-2, RF-14)."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient

from convertersmartgrid import catalog
from convertersmartgrid.reglas import REGLAS_PROYECTO, Reglas
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    # La subida se mueve con Path.replace, que no cruza de unidad: el temporal, junto al espacio.
    monkeypatch.setenv('CSG_TEMP_HOME', str(tmp_path / 'tmp'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def test_el_aviso_no_manda_reconvertir_porque_el_dgs_no_aplica_fichas():
    """081:RF-70 — mientras las reglas no apliquen fichas al convertir, el aviso no puede prometer el DGS."""
    assert Reglas().aplicar_fichas is False and REGLAS_PROYECTO.aplicar_fichas is False
    aviso = services.AVISO_CATALOGO_APLICADO
    assert 'Reconvierta' not in aviso and '«Sin proyecto»' in aviso and 'entrada' in aviso


def test_subir_el_catalogo_registra_y_devuelve_el_aviso(client, monkeypatch):
    """081:RF-70 — el Registro y la respuesta dicen lo mismo; la pantalla lo toma de la respuesta.

    Antes la web decía «Reconvierta para llevarlo al DGS», el operador reconvertía y el DGS seguía igual.
    """
    monkeypatch.setattr(catalog, 'leer_catalogo', lambda ruta, **_: {'COD1': object()})
    wid = client.post('/api/workspaces', json={'name': 'catalogo'}).json()['id']
    r = client.post(f'/api/workspaces/{wid}/catalog/apply',
                    files={'file': ('catalogo.xlsx', b'PK', 'application/octet-stream')})
    assert r.status_code == 200, r.text
    assert r.json()['aviso'] == services.AVISO_CATALOGO_APLICADO
    ws = client.app.state.store.get(wid)
    textos = [e['data'].get('text', '') for e in ws.events.since(0) if e['type'] == 'log']
    assert any(services.AVISO_CATALOGO_APLICADO in t for t in textos)
    assert not any('Reconvierta' in t for t in textos)


def test_la_pantalla_no_repite_un_aviso_propio():
    """081:RF-70 — el aviso de la pantalla sale de la respuesta: una sola frase que mantener."""
    fuente = (RAIZ / 'frontend/src/components/Modules.tsx').read_text(encoding='utf-8')
    assert '${r.aviso}' in fuente and 'Reconvierta' not in fuente
    assert 'Las próximas conversiones volverán a usar' not in fuente
