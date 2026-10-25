"""Spec 026, T11: búsquedas en internet sin datos de la red."""
from __future__ import annotations

import io
import json

from igea_dgs.asistente import almacen
from igea_dgs.asistente.internet import Buscador

ATOM = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Physics-informed GNN</title>'
        '<id>http://arxiv.org/abs/1</id><published>2025-01-01</published></entry></feed>')


class _R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _red():
    enviadas = []

    def abrir(peticion, timeout):
        url = peticion.full_url
        enviadas.append(url)
        if 'api.github.com' in url:
            return _R(json.dumps({'items': [{'full_name': 'e2nIEE/pandapower', 'html_url': 'https://github.com/x',
                                             'stargazers_count': 900, 'license': {'spdx_id': 'BSD-3-Clause'},
                                             'pushed_at': '2026-09-01', 'description': 'power flow'}]}).encode())
        if 'pypi.org' in url:
            return _R(json.dumps({'info': {'name': 'pandapower', 'version': '3.5', 'license': 'BSD',
                                           'summary': 'power flow'},
                                  'releases': {'3.5': [{'upload_time': '2026-09-01'}]}}).encode())
        return _R(ATOM.encode())

    return abrir, enviadas


def test_busca_en_github_y_arxiv(tmp_path, monkeypatch):
    """026:RF-29 / 026:RF-31 — busca con términos técnicos y registra cada consulta."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    abrir, enviadas = _red()
    r = Buscador(['IN111'], abrir=abrir).buscar('flujo de carga en python', 'buscar alternativas')
    assert r['bloqueada'] is None and r['github'][0]['licencia'] == 'BSD-3-Clause'
    assert r['arxiv'][0]['titulo'] == 'Physics-informed GNN' and len(enviadas) == 2
    registro = almacen.leer('internet')
    assert {f['destino'] for f in registro} == {'github', 'arxiv'}
    assert all(f['consulta'] == 'flujo de carga en python' and f['motivo'] == 'buscar alternativas' for f in registro)


def test_bloquea_identificadores_y_rutas(tmp_path, monkeypatch):
    """026:RF-30 / 026:RF-31 — una consulta con un alimentador, un proyecto, una ruta o un
    código con su forma no sale de la máquina y queda registrada sin su texto."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    abrir, enviadas = _red()
    b = Buscador(['IN111', '20261015-170359_IGEA_IN111_TA225', 'Pisco'], abrir=abrir)
    for consulta in ('caída de tensión en in111', 'red de pisco', 'leer D:\\BaseDatos\\red.mdb',
                     'calibración del alimentador XZ205', 'informe de 20261015-170359_IGEA_IN111_TA225'):
        assert b.buscar(consulta)['bloqueada'], consulta
    assert enviadas == []
    assert all(f['consulta'] == '[retenida]' and f['bloqueada'] for f in almacen.leer('internet'))


def test_ficha_de_pypi(tmp_path, monkeypatch):
    """026:RF-32 — de PyPI salen la licencia y la última versión para proponer una librería."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    abrir, _ = _red()
    r = Buscador(abrir=abrir).pypi('pandapower', 'flujo de carga')
    assert r['resultados'][0] == {'nombre': 'pandapower', 'version': '3.5', 'licencia': 'BSD',
                                  'publicada': '2026-09-01', 'url': None, 'descripcion': 'power flow'}
