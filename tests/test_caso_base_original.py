"""Spec 032: el «Caso base» lleva lo que trae la entrada, sin correcciones de catálogo.

En 260924.mdb, ``SE50111`` declaraba 1197 kW sobre 50 kVA y el conversor la llevaba a un
tamaño normalizado; y los conductores tomaban la R, X, B y la corriente de la ficha del
catálogo aunque el archivo dijera otra cosa. El usuario (2026-10-28) quiere el «Caso base»
como lo registró la distribuidora: las fichas y las potencias propuestas van a
«Sin proyecto». Estas pruebas usan el export sintético, en sus dos disposiciones.
"""

from __future__ import annotations

import pytest

from synthetic_export import CRS_SINTETICO, ExportSpec, load_export
from igea_dgs.batch import convert_group, convert_selection
from igea_dgs.catalog import CorreccionConductor
from igea_dgs.validate import parse_dgs

pytest.importorskip('pyproj')

#: Lo que trae el BD_Equipo sintético para su único conductor (``DEFAULT``).
R1_ARCHIVO, AMPS_ARCHIVO = 0.31, 250.0
#: Una ficha que dice otra cosa: la que antes se aplicaba al convertir.
FICHA = {'DEFAULT': CorreccionConductor('DEFAULT', {'r1_ohm_km': 0.9, 'x1_ohm_km': 0.5,
                                                    'ampacity_a': 500.0},
                                        fuente='ficha de prueba', estado='ficha')}


@pytest.fixture(params=['reducido', 'completo'])
def ds(tmp_path, request):
    spec = ExportSpec(feeders=2, sections_per_feeder=4, loads_per_feeder=2,
                      switches_per_feeder=1, layout=request.param)
    datos = load_export(spec, tmp_path / 'src')
    # Una SED de cada alimentador pide 500 kW sobre sus 50 kVA (SE50111 en 260924.mdb).
    for filas in datos.customer_loads_by_feeder.values():
        filas[0][1]['Value1'] = '500'
    return datos


def _kva_sed(tablas) -> list[float]:
    return sorted({float(r['strn']) * 1000.0 for r in tablas['TypTr2']['rows_dict']})


def test_sed_con_la_potencia_de_la_entrada(ds, tmp_path):
    """032:RF-1 — la SED con más carga que kVA sale con su kVA, no con uno normalizado."""
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO)
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        assert _kva_sed(parse_dgs(item['dgs'])) == [50.0]
        assert not (item.get('reglas') or {}).get('sed_redimensionadas')


def test_conductor_con_los_parametros_de_la_entrada(ds, tmp_path):
    """032:RF-2 — una ficha distinta no cambia la R ni la corriente del archivo en el DGS."""
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO,
                          catalog_corrections=FICHA)
    for item in m['feeders']:
        assert item['status'] == 'ok', item.get('error')
        tipos = parse_dgs(item['dgs'])['TypLne']['rows_dict']
        rs = {round(float(t['rline']), 6) for t in tipos}
        amps = {round(float(t['sline']) * 1000.0, 3) for t in tipos}
        assert R1_ARCHIVO in rs and AMPS_ARCHIVO in amps
        assert 0.9 not in rs and 500.0 not in amps
    assert m['catalog_applied'] is False
    assert not any(m['catalog_changes'].values())


def test_conversion_sin_propuestas(ds, tmp_path):
    """032:RF-5 — el informe de la conversión no trae SED redimensionadas ni fichas aplicadas."""
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO,
                          catalog_corrections=FICHA)
    for item in m['feeders']:
        reglas = item.get('reglas') or {}
        assert 'sed_redimensionadas' not in reglas
        assert 'catalogo' not in reglas


def test_mismo_caso_base_por_todas_las_vias(ds, tmp_path):
    """032:RF-6 — la red unida da los mismos kVA y conductores que cada alimentador suelto."""
    sueltos = convert_selection(ds, None, tmp_path / 's', all_feeders=True,
                                source_crs=CRS_SINTETICO, catalog_corrections=FICHA)
    unida = convert_group(ds, [f['feeder'] for f in sueltos['feeders']], tmp_path / 'u',
                          name='UNIDA', source_crs=CRS_SINTETICO, catalog_corrections=FICHA)
    assert unida['status'] == 'ok', unida.get('error')
    tablas = parse_dgs(unida['dgs'])
    assert _kva_sed(tablas) == [50.0]
    rs = {round(float(r['rline']), 6) for r in tablas['TypLne']['rows_dict']}
    assert R1_ARCHIVO in rs and 0.9 not in rs


def test_la_verificacion_compara_con_la_entrada_sin_corregir(ds, tmp_path):
    """032:RF-7 — la capacidad «del archivo» con que se verifica el «Caso base» es la de la
    entrada: un transformador llevado a 630 kVA en DIgSILENT es una diferencia, no lo
    esperado."""
    from dataclasses import replace

    from igea_dgs.capacidades import comparar_equipos, equipos_de_dgs

    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO,
                          catalog_corrections=FICHA)
    archivo = equipos_de_dgs(parse_dgs(m['feeders'][0]['dgs']))
    assert {round(t.mva, 6) for t in archivo['transformadores'].values()} == {0.05}
    assert comparar_equipos(archivo, archivo)['capacidad_distinta'] == []
    nombre, tr = sorted(archivo['transformadores'].items())[0]
    leidos = {**archivo, 'transformadores': {**archivo['transformadores'],
                                             nombre: replace(tr, mva=0.63)}}
    [distinta] = comparar_equipos(archivo, leidos)['capacidad_distinta']
    assert (distinta['nombre'], distinta['archivo'], distinta['digsilent']) == (nombre, 0.05, 0.63)


def _catalogo_con(tmp_path, codigo: str):
    openpyxl = pytest.importorskip('openpyxl')
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = 'conductores_aereos'
    hoja.append(['codigo', 'R1_modelo_ohm_km', 'X1_modelo_ohm_km', 'R0_modelo_ohm_km',
                 'X0_modelo_ohm_km', 'B1_modelo_uS_km', 'ampacidad_modelo_A', 'estado'])
    hoja.append([codigo, 0.6755, 0.47, 0.8, 1.4, 3.1, 195, 'por_confirmar'])
    ruta = tmp_path / 'catalogo.xlsx'
    wb.save(ruta)
    return ruta


def test_conductor_sin_parametros_se_completa_y_se_anota(ds, tmp_path):
    """032:RF-3, 032:RF-4 — un código que la entrada usa sin parámetros se completa con el
    catálogo y queda anotado como dato deducido, con su fuente y sus tramos."""
    secciones = sorted(s for s, lc in ds.line_configurations.items()
                       if lc.get('Overhead') == '1')[:3]
    for s in secciones:
        ds.line_configurations[s]['LineCableID'] = 'AA05003D'
    m = convert_selection(ds, None, tmp_path / 'o', all_feeders=True, source_crs=CRS_SINTETICO,
                          catalogo=_catalogo_con(tmp_path, 'AA05003D'))
    assert all(f['status'] == 'ok' for f in m['feeders']), m['feeders']
    [anotado] = m['conductores_deducidos']
    assert anotado['codigo'] == 'AA05003D' and anotado['tramos'] == 3
    assert 'catalogo.xlsx' in anotado['fuente']
    tipos = [r for f in m['feeders'] for r in parse_dgs(f['dgs'])['TypLne']['rows_dict']]
    assert any(abs(float(t['rline']) - 0.6755) < 1e-9 for t in tipos)


def test_mismo_dgs_en_serie_y_en_paralelo(ds, tmp_path):
    """032:RF-6 — sin las correcciones, el DGS sigue siendo idéntico con workers=1 y >1."""
    a = convert_selection(ds, None, tmp_path / 'a', all_feeders=True, source_crs=CRS_SINTETICO,
                          workers=1, catalog_corrections=FICHA)
    b = convert_selection(ds, None, tmp_path / 'b', all_feeders=True, source_crs=CRS_SINTETICO,
                          workers=2, catalog_corrections=FICHA)
    for x, y in zip(a['feeders'], b['feeders'], strict=True):
        with open(x['dgs'], 'rb') as fx, open(y['dgs'], 'rb') as fy:
            assert fx.read() == fy.read()
