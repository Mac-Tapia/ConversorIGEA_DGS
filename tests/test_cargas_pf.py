"""Spec 004: lectura de los libros de cargas sin el modelo de la conversión."""
from __future__ import annotations

import os
import random
from datetime import datetime

import pytest

from igea_dgs.cargas_pf import (
    DEMANDA_COLUMNS, NUEVA_COLUMNS, armar_plan, escribir_plantilla, leer_demandas,
    leer_hoja_nuevas, leer_nuevas,
)

openpyxl = pytest.importorskip('openpyxl')

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _libro(path, hojas: dict[str, list[list]]):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        hoja = wb.create_sheet(nombre)
        for fila in filas:
            hoja.append(fila)
    wb.save(path)
    return path


def test_demandas_de_varias_hojas_sin_entradas_cargadas(tmp_path):
    """004:RF-1 — el libro de demandas se lee sin TXT, MDB ni modelo; cada fila por sí sola."""
    rng = random.Random(SEMILLA)
    hojas, esperadas, malas = {}, set(), 0
    for f in range(rng.randint(1, 6)):
        filas = [['SED', 'Kw', 'Kvar', '(kVA)', 'FP']]
        for i in range(rng.randint(1, 30)):
            if rng.random() < 0.15:
                filas.append([f'E{f}_{i}', 'abc', '', '', ''])
                malas += 1
            else:
                filas.append([f'S{f}_{i}', round(rng.uniform(1, 500), 2), '', '', 0.9])
                esperadas.add((f'ALIM{f}', f'S{f}_{i}'))
        hojas[f'ALIM{f}'] = filas
    lectura = leer_demandas(_libro(tmp_path / 'demandas.xlsx', hojas))
    assert {(d.hoja, d.sed) for d in lectura.filas} == esperadas, f'semilla {SEMILLA}'
    assert len(lectura.errores) == malas
    assert all(d.kvar == pytest.approx(d.kw * (1 / 0.9 ** 2 - 1) ** 0.5, rel=1e-6)
               for d in lectura.filas)


def test_demandas_omitir_y_sin_datos_no_son_filas(tmp_path):
    """004:RF-7 — `accion=omitir` y filas sin datos no llegan a DIgSILENT, y se informan."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [
        ['SED', 'Kw', 'Kvar', '(kVA)', 'FP', 'accion'],
        ['S1', 10, 2, '', '', ''],
        ['S2', 10, 2, '', '', 'omitir'],
        ['S3', '', '', 0, 0, ''],
    ]}))
    assert [d.sed for d in lectura.filas] == ['S1']
    assert lectura.omitidas == ['S2'] and lectura.sin_datos == ['S3']


def test_nuevas_con_barra_latlon_o_coordenadas_proyectadas():
    """004:RF-10 — barra, Lat/Lon o CoordX/CoordY (pasadas a WGS84 con el CRS del perfil)."""
    pytest.importorskip('pyproj')
    header = list(NUEVA_COLUMNS)

    def fila(**v):
        return [v.get(c, '') for c in header]

    filas, errores = leer_hoja_nuevas(header, [
        fila(SED='N1', barra='B12', kVA_instalado=100, Kw=80, FP=0.9),
        fila(SED='N2', Lat=-14.06, Lon=-75.73, kVA_instalado=50, Kw=40, Kvar=10),
        fila(SED='N3', CoordX=420000, CoordY=8445000, kVA_instalado=160, **{'(kVA)': 120}, FP=0.95),
        fila(SED='N4', kVA_instalado=50, Kw=10),
        fila(SED='N5', barra='B1', Kw=10),
        fila(SED='N6', barra='B1', kVA_instalado=50, Kw=10, tipo_linea='AAAC 35',
             tension_bt_kv=0.38),
    ], 'A', source_crs='EPSG:32718')
    por_sed = {f.sed: f for f in filas}
    assert set(por_sed) == {'N1', 'N2', 'N3', 'N6'}
    assert por_sed['N1'].barra == 'B12' and por_sed['N1'].lat is None
    assert por_sed['N2'].lat == pytest.approx(-14.06)
    assert -15 < por_sed['N3'].lat < -13 and -77 < por_sed['N3'].lon < -75
    assert por_sed['N6'].tipo_linea == 'AAAC 35' and por_sed['N6'].tension_bt_kv == 0.38
    assert any('N4' in e and 'sin barra ni coordenadas' in e for e in errores)
    assert any('N5' in e and 'kVA_instalado' in e for e in errores)


def test_coordenadas_proyectadas_sin_crs_del_perfil_es_error_de_fila():
    """004:RF-11 — CoordX/CoordY sin CRS no se adivinan: esa fila sale con su motivo."""
    header = list(NUEVA_COLUMNS)
    fila = [{'SED': 'N1', 'CoordX': 420000, 'CoordY': 8445000, 'kVA_instalado': 50,
             'Kw': 10}.get(c, '') for c in header]
    filas, errores = leer_hoja_nuevas(header, [fila], 'A', source_crs='')
    assert filas == [] and 'sin CRS' in errores[0]


def test_plan_es_igual_para_uno_que_para_varios(tmp_path):
    """004:RF-5 — un alimentador es un lote de uno: mismo plan, mismas claves."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [['SED', 'Kw'], ['S1', 5]]}))
    hora = datetime(2026, 10, 8, 9, 30, 15)
    uno = armar_plan(project='P', feeders=['A'], demandas=lectura, nuevas=None, ahora=hora)
    varios = armar_plan(project='P', feeders=['A', 'B', 'A'], demandas=lectura, nuevas=None,
                        ahora=hora)
    assert uno.keys() == varios.keys()
    assert varios['feeders'] == ['A', 'B']
    assert uno['variacion'] == 'Cargas_20261008_093015'
    assert uno['aplicable'] and uno['demandas'][0]['plini_mw'] == pytest.approx(0.005)


def test_plan_con_errores_sigue_siendo_aplicable_con_lo_valido(tmp_path):
    """004:RF-7 — una fila mala no impide aplicar las buenas; se informa."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [
        ['SED', 'Kw'], ['S1', 5], ['S2', 'x']]}))
    plan = armar_plan(project='P', feeders=['A'], demandas=lectura, nuevas=None)
    assert plan['aplicable'] and len(plan['row_errors']) == 1


@pytest.mark.parametrize(
    'tipo,columnas', [('demandas', DEMANDA_COLUMNS), ('nuevas', NUEVA_COLUMNS)])
@pytest.mark.parametrize('ext', ['.xlsx', '.csv'])
def test_plantillas_vacias_se_vuelven_a_leer(tmp_path, tipo, columnas, ext):
    """004:RF-1 — la plantilla vacía tiene las columnas que el lector entiende."""
    ruta = escribir_plantilla(tipo, tmp_path / f'plantilla{ext}')
    if ext == '.xlsx':
        cabecera = [c.value for c in openpyxl.load_workbook(ruta).active[1]]
    else:
        cabecera = ruta.read_text(encoding='utf-8-sig').strip().split(';')
    assert cabecera == list(columnas)
    lector = leer_demandas if tipo == 'demandas' else leer_nuevas
    if ext == '.xlsx':
        from igea_dgs.loads import LoadTemplateError

        with pytest.raises(LoadTemplateError, match='ninguna hoja con datos'):
            lector(ruta)
    else:
        assert lector(ruta).filas == []
