"""Spec 039, RF-9 a RF-22: el cliente fijo «a su máxima» en la tabla cruzada, en la web y en la recalibración.

El cálculo del cruce y del plan se prueba en ``test_tabla_en_el_instante.py`` y ``test_ajuste_cabecera_web.py``;
el informe del guion, en ``test_q_con_bancos.py``; ``sistema_web.py``, en ``test_sistema_web.py``. Aquí, la ruta
de recalibrar y lo que enseña la web.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / 'frontend' / 'src'


def test_recalibrar_lleva_los_clientes_a_su_maxima_al_guion(tmp_path, monkeypatch):
    """039:RF-16, 039:RF-17 — ``a_su_maxima`` de la petición de recalibrar pasa a ``sistema_web.py`` como
    ``--a-su-maxima``; sin el campo no se pasa y el guion usa la selección guardada en el espacio."""
    from apoyo import esperar_trabajo
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import jobs
    from convertersmartgrid.web.app import create_app

    ordenes = []
    monkeypatch.setattr(jobs.JobContext, 'run_process', lambda self, cmd, **kw: ordenes.append(cmd) or 0)
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    libros = tmp_path / 'referencia'
    (libros / '2.-cabecera').mkdir(parents=True)
    proyecto = '20261107_CSG_RED_X'
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        ws = c.app.state.store.get(wid)
        ws.demanda = {'cabecera': {'path': str(libros / '2.-cabecera')}}
        ws.pf_projects = {'RED_X': proyecto}
        ws.groups = {'RED_X': {'tipo': 'sistema', 'feeders': ['X101', 'X202']}}
        for cuerpo in ({'a_su_maxima': ['11', ' 14 ', '11']}, {}, {'a_su_maxima': []}):
            fin = esperar_trabajo(c, c.post(f'/api/workspaces/{wid}/demanda/recalibrar', json={
                'project': proyecto, 'periodo': '2026-07', **cuerpo}).json())
            assert fin['status'] == 'done', fin
    con, sin, vacia = ordenes
    assert con[con.index('--a-su-maxima') + 1:][:2] == ['11', '14'] and con.count('11') == 1
    assert '--a-su-maxima' not in sin
    assert vacia.index('--a-su-maxima') == vacia.index('--resumen-json') - 1


def test_la_web_ensena_los_dos_valores_ordena_marca_y_recalibra():
    """039:RF-9, 039:RF-10, 039:RF-11, 039:RF-12, 039:RF-13, 039:RF-14, 039:RF-15, 039:RF-17, 039:RF-18 — la tabla
    cruzada tiene las columnas de los dos valores y de la diferencia, el orden y el filtro por ella, la casilla
    «a su máxima» con «Desmarcar todos», la selección guardada en el espacio y releída al abrir, el botón
    «Recalibrar con estos criterios» por la ruta de recalibrar, y el informe lista los clientes a su máxima."""
    demanda = (FRONT / 'features' / 'powerfactory' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    ajuste = (FRONT / 'features' / 'powerfactory' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    api = (FRONT / 'api' / 'client.ts').read_text(encoding='utf-8')
    tipos = (FRONT / 'api' / 'types.ts').read_text(encoding='utf-8')
    for pieza in ('>Coincidente</th>', '>Su máxima del mes</th>', '>Diferencia</th>', '>A su máxima</th>', '>Criterio</th>',
                  'Diferencia de su máxima (kW), de mayor a menor', 'Diferencia de su máxima (%), de mayor a menor',
                  'Diferencia mínima (%)', 'Desmarcar todos «a su máxima»', 'Recalibrar con estos criterios',
                  'aria-label={`Subir ${c.codigo} a su máxima del mes`}', 'ws.fijas_a_su_maxima',
                  'api.demandaASuMaxima(ws.id, codigos)', 'a_su_maxima: aSuMaxima }', 'aSuMaxima={aSuMaxima}'):
        assert pieza in demanda, pieza
    # 039:RF-11: nada se marca solo; la selección cambia solo con la casilla y con «Desmarcar todos».
    assert demanda.count('void guardarASuMaxima(') == 2
    assert "json('PUT', { codigos })" in api and 'a_su_maxima?: string[] }) =>' in api
    assert 'fijas_a_su_maxima?: string[];' in tipos and "criterio?: CriterioFijas | 'a_su_maxima';" in tipos
    assert 'Clientes a su máxima' in ajuste and 'inf.fijas_a_su_maxima' in ajuste
    assert '...(aSuMaxima ? { a_su_maxima: aSuMaxima } : {})' in ajuste
