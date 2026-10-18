"""Reglas del proyecto: se aplican siempre, en cualquier vía, y no pierden nada.

Ver ``igea_dgs.reglas``: hoja dinámica a escala real, coordenadas por el grafo, puentes fundidos,
trafomix excluidos, SED redimensionadas, catálogo del proyecto y auditoría de
completitud. Estas pruebas usan el export sintético, en sus dos disposiciones.
"""

from __future__ import annotations

import json

import pytest

from synthetic_export import CRS_SINTETICO, ExportSpec, load_export
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
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO)
    assert m['reglas'] == REGLAS_PROYECTO.__dict__
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        assert 'hoja' not in item
        assert item['completitud']['fallos'] == []


def test_un_default_largo_es_linea_real_y_no_se_funde(ds, tmp_path):
    """El sintético tipa DEFAULT sus tramos de 40 m: son líneas, no puentes."""
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO)
    for item in m['feeders']:
        tablas = parse_dgs(item['dgs'])
        largos = [float(r['dline']) * 1000 for r in tablas['ElmLne']['rows_dict']]
        assert any(x > 10 for x in largos), 'los tramos de 40 m siguen siendo ElmLne'
        assert all(x > 10 for x in largos), 'los puentes de 0,3 m se funden'


def test_sin_reglas_es_la_conversion_literal(ds, tmp_path):
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True,
                          source_crs=CRS_SINTETICO, reglas=SIN_REGLAS)
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        assert 'hoja' not in item
        assert len(parse_dgs(item['dgs'])['ElmLne']['rows_dict']) == len(
            ds.feeders[item['network_id']])


def test_varios_alimentadores_en_un_solo_dgs(ds, tmp_path):
    nombres = [f['feeder'] for f in convert_selection(
        ds, None, tmp_path / 'x', all_feeders=True, source_crs=CRS_SINTETICO)['feeders']]
    man = convert_group(ds, nombres, tmp_path / 'g', name='GRUPO 1', source_crs=CRS_SINTETICO)
    assert man['status'] == 'ok', man.get('error')
    assert man['name'] == 'GRUPO_1'
    assert man['completitud']['fallos'] == []
    tablas = parse_dgs(man['dgs'])
    assert len(tablas['ElmXnet']['rows_dict']) == len(nombres), 'una fuente por alimentador'
    assert man['hoja'] is None
    guardado = json.loads((tmp_path / 'g' / 'GRUPO_1_manifest.json').read_text(encoding='utf-8'))
    assert guardado['status'] == 'ok'


def test_un_grupo_con_un_alimentador_roto_no_publica_dgs(ds, tmp_path):
    man = convert_group(ds, ['NO_EXISTE', 'TAMPOCO'], tmp_path / 'g', name='MAL',
                        source_crs=CRS_SINTETICO)
    assert man['status'] == 'failed' and man.get('error')
    assert not (tmp_path / 'g' / 'MAL.dgs').exists()
    assert (tmp_path / 'g' / 'MAL_manifest.json').exists()


# ---------------------------------------------------------------------------
# Web: unir en un DGS
# ---------------------------------------------------------------------------

def test_web_une_en_un_dgs(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    import time

    from fastapi.testclient import TestClient

    from synthetic_export import write_export
    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    red, carga, equipo = write_export(ExportSpec(feeders=3), tmp_path / 'e')
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        wid = c.post('/api/workspaces').json()['id']
        c.put(f'/api/workspaces/{wid}/options', json={'source_crs': CRS_SINTETICO})
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
        assert estado['groups'][0]['converted_at'] is not None
        assert estado['groups'][0]['requested_feeders'] == nombres
        assert estado['groups'][0]['feeder_metadata'].endswith('RED_feeder_metadata.json')
        assert estado['options']['hoja'] is None


def test_la_red_unida_por_zonal_y_set(ds, tmp_path):
    """022:RF-6, 022:RF-7, 022:RF-25, 022:RF-34 — con la estructura, un DGS con una red por
    zonal y una fuente por barra de SET, en las dos disposiciones; el manifiesto trae el
    informe por zonal y SET, los «Sin SET», las aperturas y el oráculo."""
    from igea_dgs.estructura import estructura_de_dict

    nombres = [f['feeder'] for f in convert_selection(
        ds, None, tmp_path / 'x', all_feeders=True, source_crs=CRS_SINTETICO)['feeders']]
    e = estructura_de_dict({'zonales': [
        {'nombre': 'Norte', 'sets': [{'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': nombres[:2]}]},
        {'nombre': 'Sur', 'sets': [{'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': ['NO_VIENE']}]}]})
    man = convert_group(ds, nombres, tmp_path / 'g', name='POR SET', source_crs=CRS_SINTETICO,
                        estructura=e)
    assert man['status'] == 'ok', man.get('error')
    tablas = parse_dgs(man['dgs'])
    assert {r['loc_name'] for r in tablas['ElmNet']['rows_dict']} == {'Norte', 'Sin SET'}
    xnets = [r['loc_name'] for r in tablas['ElmXnet']['rows_dict']]
    assert len(xnets) == 1 + len(nombres) - 2, 'una por barra de SET y una por «Sin SET»'
    por_set = man['estructura']
    assert set(por_set['zonales']) == {'Norte'}
    assert sorted(por_set['zonales']['Norte']['SET 1 Uno']['alimentadores']) == sorted(nombres[:2])
    assert por_set['sin_set'] == sorted(nombres[2:]) and por_set['faltan'] == ['NO_VIENE']
    assert por_set['omitidos']['zonales'] == ['Sur']
    assert isinstance(por_set['aperturas'], list)
    if por_set['oraculo'] is not None:
        assert por_set['oraculo']['islas']


def test_web_convierte_por_sistema_electrico_con_la_tabla_subida(tmp_path, monkeypatch):
    """022:RF-4, 022:RF-5, 022:RF-7, 022:RF-25, 022:RF-47, 022:RF-48, 022:RF-49, 022:RF-50,
    022:RF-51 — la tabla de la estructura en Excel se sube al espacio (una mal formada se
    rechaza nombrando la fila); la conversión por sistema eléctrico es una opción propia que
    la usa (SISTEMA_ELECTRICO, tipo «sistema», informe por zonal y SET en el Registro) y unir
    dos o más sigue sin usarla (tipo «unida», una sola red)."""
    pytest.importorskip('fastapi')
    import time

    from fastapi.testclient import TestClient
    from openpyxl import Workbook

    from synthetic_export import write_export
    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    red, carga, equipo = write_export(ExportSpec(feeders=3), tmp_path / 'e')
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        wid = c.post('/api/workspaces').json()['id']
        c.put(f'/api/workspaces/{wid}/options', json={'source_crs': CRS_SINTETICO})
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

        def tabla(filas, nombre):
            wb = Workbook()
            h = wb.active
            h.append(['Zonal', 'Codigo SET', 'Codigo VNR Alimentador'])
            for f in filas:
                h.append(f)
            ruta = tmp_path / nombre
            wb.save(ruta)
            return ruta

        mala = tabla([['Z', 'SET 1 UNO', nombres[0]], ['Z', 'SET 2 DOS', nombres[0]]], 'mala.xlsx')
        r = c.post(f'/api/workspaces/{wid}/demanda/estructura/path', json={'path': str(mala)})
        assert r.status_code == 400 and 'fila 3' in r.json()['detail']
        buena = tabla([['Z', 'SET 1 UNO', n] for n in nombres], 'buena.xlsx')
        r = c.post(f'/api/workspaces/{wid}/demanda/estructura/path', json={'path': str(buena)})
        assert r.status_code == 200, r.text
        assert r.json()['demanda']['estructura']['alimentadores'] == len(nombres)
        r = c.get(f'/api/workspaces/{wid}/estructura')
        assert r.status_code == 200 and r.json()['origen'] == 'excel'
        assert r.json()['zonales'][0]['nombre'] == 'Z'
        assert sorted(r.json()['zonales'][0]['alimentadores']) == sorted(nombres)
        r = c.post(f'/api/workspaces/{wid}/convert/sistema', json={'zonales': ['NO_EXISTE']})
        assert r.status_code == 400
        j = esperar(c.post(f'/api/workspaces/{wid}/convert/sistema', json={'zonales': []}).json())
        assert j['result']['status'] == 'ok', j['result']
        textos = [e['data'].get('text') or '' for e in c.get(f'/api/workspaces/{wid}/events').json()]
        assert any(t.startswith('Por zonal y SET') for t in textos)
        assert any('SET 1 UNO' in t for t in textos)
        # 022:RF-50: unir dos o más, con la estructura subida, sigue sin usarla.
        j = esperar(c.post(f'/api/workspaces/{wid}/convert', json={
            'feeders': nombres[:2], 'unir': True, 'nombre': 'DOS'}).json())
        assert j['result']['status'] == 'ok', j['result']
        grupos = {g['name']: g for g in c.get(f'/api/workspaces/{wid}').json()['groups']}
        assert grupos['SISTEMA_ELECTRICO']['tipo'] == 'sistema' and grupos['DOS']['tipo'] == 'unida'
        dos = next((tmp_path / 'web').rglob('DOS.dgs'))
        assert len(parse_dgs(dos)['ElmNet']['rows_dict']) == 1, 'unir no usa la estructura'
        sis = next((tmp_path / 'web').rglob('SISTEMA_ELECTRICO.dgs'))
        assert {r['loc_name'] for r in parse_dgs(sis)['ElmNet']['rows_dict']} == {'Z'}


def test_cli_por_sistema_electrico(tmp_path):
    """022:RF-47, 022:RF-48, 022:RF-49 — `--por-sistema ZONAL` convierte solo los de ese zonal
    en SISTEMA_<ZONAL>, aparte de `--unir`, con el que no se mezcla."""
    from openpyxl import Workbook

    from synthetic_export import write_export
    from igea_dgs.cli import main
    from igea_dgs.naming import feeder_short_name

    red, carga, equipo = write_export(ExportSpec(feeders=3), tmp_path / 'e')
    nombres = sorted(f['feeder'] for f in convert_selection(
        load_export(ExportSpec(feeders=3), tmp_path / 'e2'), None, tmp_path / 'x',
        all_feeders=True, source_crs=CRS_SINTETICO)['feeders'])
    wb = Workbook()
    h = wb.active
    h.append(['Zonal', 'Codigo SET', 'Codigo VNR Alimentador'])
    h.append(['NORTE', 'SET 1 UNO', nombres[0]])
    h.append(['NORTE', 'SET 1 UNO', nombres[1]])
    h.append(['SUR', 'SET 2 DOS', nombres[2]])
    wb.save(tmp_path / 't.xlsx')
    base = ['convert', '--red', str(red), '--loads', str(carga), '--equipment', str(equipo),
            '--source-crs', CRS_SINTETICO, '--out-dir', str(tmp_path / 'o'), '--no-geography']
    assert main(base + ['--por-sistema', 'NORTE', '--estructura', str(tmp_path / 't.xlsx')]) == 0
    tablas = parse_dgs(tmp_path / 'o' / 'SISTEMA_NORTE.dgs')
    assert {r['loc_name'] for r in tablas['ElmNet']['rows_dict']} == {'NORTE'}
    assert len(tablas['ElmFeeder']['rows_dict']) == 2
    with pytest.raises(SystemExit, match='distintas'):
        main(base + ['--por-sistema', '--unir', 'X', '--estructura', str(tmp_path / 't.xlsx')])
    del feeder_short_name
