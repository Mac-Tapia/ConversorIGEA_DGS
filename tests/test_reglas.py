"""Reglas del proyecto: se aplican siempre, en cualquier vía, y no pierden nada.

Ver ``igea_dgs.reglas``: lienzo adaptativo, coordenadas por el grafo, puentes fundidos,
trafomix excluidos, SED redimensionadas, catálogo del proyecto y auditoría de
completitud. Estas pruebas usan el export sintético, en sus dos disposiciones.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from synthetic_export import ExportSpec, load_export
from igea_dgs.batch import convert_group, convert_selection
from igea_dgs.reglas import REGLAS_PROYECTO, SIN_REGLAS
from igea_dgs.validate import parse_dgs

pytest.importorskip('pyproj')


@pytest.fixture(params=['reducido', 'completo'])
def ds(tmp_path, request):
    spec = ExportSpec(feeders=3, sections_per_feeder=5, loads_per_feeder=2,
                      switches_per_feeder=1, layout=request.param)
    return load_export(spec, tmp_path / 'src')


def test_las_reglas_del_proyecto_son_el_defecto(ds, tmp_path):
    assert REGLAS_PROYECTO.hoja is None
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs='EPSG:32718')
    assert m['reglas'] == REGLAS_PROYECTO.__dict__
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        assert 'hoja' not in item
        assert item['completitud']['fallos'] == []


def test_una_hoja_a0_sigue_disponible_si_se_solicita(ds, tmp_path):
    reglas = replace(REGLAS_PROYECTO, hoja='A0')
    m = convert_selection(
        ds, None, tmp_path / 'a0', all_feeders=True,
        source_crs='EPSG:32718', reglas=reglas,
    )
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        assert item['hoja']['formato'] == 'A0'


def test_un_default_largo_es_linea_real_y_no_se_funde(ds, tmp_path):
    """El sintético tipa DEFAULT sus tramos de 40 m: son líneas, no puentes."""
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs='EPSG:32718')
    for item in m['feeders']:
        tablas = parse_dgs(item['dgs'])
        largos = [float(r['dline']) * 1000 for r in tablas['ElmLne']['rows_dict']]
        assert any(x > 10 for x in largos), 'los tramos de 40 m siguen siendo ElmLne'
        assert all(x > 10 for x in largos), 'los puentes de 0,3 m se funden'


def test_sin_reglas_es_la_conversion_literal(ds, tmp_path):
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True,
                          source_crs='EPSG:32718', reglas=SIN_REGLAS)
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        assert 'hoja' not in item
        assert len(parse_dgs(item['dgs'])['ElmLne']['rows_dict']) == len(
            ds.feeders[item['network_id']])


def test_varios_alimentadores_en_un_solo_dgs(ds, tmp_path):
    nombres = [f['feeder'] for f in convert_selection(
        ds, None, tmp_path / 'x', all_feeders=True, source_crs='EPSG:32718')['feeders']]
    man = convert_group(ds, nombres, tmp_path / 'g', name='GRUPO 1', source_crs='EPSG:32718')
    assert man['status'] == 'ok', man.get('error')
    assert man['name'] == 'GRUPO_1'
    assert man['completitud']['fallos'] == []
    tablas = parse_dgs(man['dgs'])
    assert len(tablas['ElmXnet']['rows_dict']) == len(nombres), 'una fuente por alimentador'
    assert man['hoja'] is None
    metadata_path = tmp_path / 'g' / 'GRUPO_1_feeder_metadata.json'
    assert man['feeder_metadata'] == str(metadata_path)
    mapping_path = tmp_path / 'g' / 'GRUPO_1_name_alimentador.csv'
    assert man['name_feeder_mapping'] == str(mapping_path)
    assert mapping_path.is_file()
    assert mapping_path.read_text(encoding='utf-8-sig').splitlines()[0] == (
        'Name,Alimentador,Clase,NetworkID,Terminal,Substation'
    )
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    assert sum(r['class_name'] == 'ElmLod' for r in metadata['assignments']) == len(
        tablas['ElmLod']['rows_dict'])
    assert sum(r['class_name'] == 'ElmXnet' for r in metadata['assignments']) == len(nombres)
    guardado = json.loads((tmp_path / 'g' / 'GRUPO_1_manifest.json').read_text(encoding='utf-8'))
    assert guardado['status'] == 'ok'


def test_un_grupo_con_un_alimentador_roto_no_publica_dgs(ds, tmp_path):
    man = convert_group(ds, ['NO_EXISTE', 'TAMPOCO'], tmp_path / 'g', name='MAL',
                        source_crs='EPSG:32718')
    assert man['status'] == 'failed' and man.get('error')
    assert not (tmp_path / 'g' / 'MAL.dgs').exists()
    assert (tmp_path / 'g' / 'MAL_manifest.json').exists()


# ---------------------------------------------------------------------------
# Web: unir en un DGS y aplicar cargas sobre el proyecto correcto
# ---------------------------------------------------------------------------

def test_web_une_en_un_dgs_y_exige_proyecto_para_aplicar_cargas(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    import time

    from fastapi.testclient import TestClient

    from synthetic_export import write_export
    from igea_dgs.web import services
    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    red, carga, equipo = write_export(ExportSpec(feeders=3), tmp_path / 'e')
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        for slot, path in (('red', red), ('loads', carga), ('equipment', equipo)):
            c.post(f'/api/workspaces/{wid}/inputs/{slot}/path', json={'path': str(path)})

        def esperar(job):
            for _ in range(600):
                j = c.get(f"/api/jobs/{job['id']}").json()
                if j['status'] in ('done', 'failed', 'cancelled'):
                    return j
                time.sleep(0.05)
            raise AssertionError('no terminó')

        assert esperar(c.post(f'/api/workspaces/{wid}/load').json())['status'] == 'done'
        nombres = [f['feeder'] for f in c.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
        r = c.post(f'/api/workspaces/{wid}/convert', json={'feeders': nombres[:1], 'unir': True})
        assert r.status_code == 400, 'unir exige al menos dos'
        j = esperar(c.post(f'/api/workspaces/{wid}/convert',
                           json={'feeders': nombres, 'unir': True, 'nombre': 'RED'}).json())
        assert j['result']['status'] == 'ok', j['result']
        estado = c.get(f'/api/workspaces/{wid}').json()
        assert [g['name'] for g in estado['groups']] == ['RED']
        assert estado['groups'][0]['name_feeder_mapping'].endswith(
            'RED_name_alimentador.csv'
        )
        assert estado['options']['hoja'] == 'AUTO'

        ws = c.app.state.store.get(wid)
        assert services.proyecto_pf_de(ws, nombres[0]) is None
        ws.pf_projects['RED'] = 'RED_proyecto'
        assert services.proyecto_pf_de(ws, nombres[0]) == 'RED_proyecto', \
            'un alimentador de un DGS unido usa el proyecto del grupo'
