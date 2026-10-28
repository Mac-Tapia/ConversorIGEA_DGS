"""Spec 004: lectura de los libros de cargas sin el modelo de la conversión."""
from __future__ import annotations

import os
import random
from datetime import datetime

import pytest

from igea_dgs.cargas_pf import (
    DEMANDA_COLUMNS, NUEVA_COLUMNS, armar_plan, escribir_plantilla, leer_demandas,
    kva_normalizado, leer_hoja_nuevas, leer_nuevas,
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
        v = {'alimentador': 'A', **v}         # 025:RF-45: el alimentador es obligatorio
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
    assert set(por_sed) == {'N1', 'N2', 'N3', 'N5', 'N6'}
    assert por_sed['N1'].barra == 'B12' and por_sed['N1'].lat is None
    assert por_sed['N2'].lat == pytest.approx(-14.06)
    assert -15 < por_sed['N3'].lat < -13 and -77 < por_sed['N3'].lon < -75
    assert por_sed['N6'].tipo_linea == 'AAAC 35' and por_sed['N6'].tension_bt_kv == 0.38
    assert any('N4' in e and 'sin barra ni coordenadas' in e for e in errores)
    # 004:RF-52: sin kVA_instalado ya no es un error: se deduce de la demanda.
    assert por_sed['N5'].kva_instalado == 10 and not any('N5' in e for e in errores)


def test_libro_de_planificacion_sin_sed_ni_kva_instalado():
    """004:RF-51 / 004:RF-53 — «DESCRIPCION», «DEM PROY (KW)», «TRONCAL» y «COORDENADAS UTM
    (X)/(Y)», con columnas vacías al final, como el libro de SI213 del 2026-10-12."""
    pytest.importorskip('pyproj')
    header = ['DESCRIPCION', 'DEM PROY (KW)', 'TRONCAL', 'BARRA', 'SISTEMA', 'SUBESTACIÓN',
              'COORDENADAS UTM (X)', 'COORDENADAS UTM (Y)'] + [None] * 5
    avisos: list[str] = []
    filas, errores = leer_hoja_nuevas(header, [
        ['Habilitación urbana Los Pinos', 300, 'F1', 'B 10 kV', 'S', 'SE', 420000, 8445000],
        [None, 50, 'F1', '', '', '', 420100, 8445100],
        [None, None, None, None, None, None, None, None, None, 'resto'],
    ], 'DemandaNUEVA', source_crs='EPSG:32718', avisos=avisos)
    assert errores == []
    assert [f.sed for f in filas] == ['Habilitación urbana Los Pinos', 'DemandaNUEVA_F3']
    pinos = filas[0]
    assert (pinos.kw, pinos.alimentador, pinos.barra) == (300, 'F1', 'B 10 kV')
    assert -15 < pinos.lat < -13 and -77 < pinos.lon < -75
    assert any('DemandaNUEVA_F3' in a and 'RF-53' in a for a in avisos)


@pytest.mark.parametrize('kva,esperado', [(0.5, 10), (10, 10), (300, 315), (316, 400),
                                          (2600, 3150), (12000, 12500)])
def test_kva_instalado_deducido_es_el_normalizado_que_cubre_la_demanda(kva, esperado):
    """004:RF-52 — la menor potencia de la serie R10 que cubre la demanda, anotada."""
    assert kva_normalizado(kva) == esperado
    avisos: list[str] = []
    filas, _ = leer_hoja_nuevas(['SED', 'Kw', 'barra', 'alimentador'], [['N1', kva, 'B1', 'A']], 'A',
                                  avisos=avisos)
    assert filas[0].kva_instalado == esperado and 'RF-52' in avisos[0]
    plan = armar_plan(project='P', feeders=['A'], demandas=None,
                      nuevas=type('L', (), {'filas': filas, 'errores': [], 'avisos': avisos})())
    assert avisos[0] in plan['avisos']


def test_carga_nueva_sin_alimentador_se_rechaza_y_se_dice():
    """025:RF-45, 025:RF-46 — sin alimentador (TRONCAL) la fila sale con su motivo y no se deduce
    de la barra; las demás siguen."""
    filas, errores = leer_hoja_nuevas(
        ['SED', 'barra', 'Kw', 'kVA_instalado', 'TRONCAL'],
        [['N1', 'B1', 10, 50, ''], ['N2', 'B2', 10, 50, 'F7']], 'HOJA')
    assert [f.sed for f in filas] == ['N2'] and filas[0].alimentador == 'F7'
    assert len(errores) == 1 and 'N1' in errores[0] and 'HOJA' in errores[0]
    assert 'sin alimentador (TRONCAL)' in errores[0]


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
    # 007:RF-19: las demandas van en su propia variación.
    assert uno['variacion_demandas'] == uno['variacion'] == 'Demandas_20261008_093015'
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


def test_plan_con_carpeta(tmp_path):
    """005:RF-16 — el plan lleva la carpeta donde buscar la ruta del proyecto."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [['SED', 'Kw'], ['S1', 5]]}))
    plan = armar_plan(project='Oct/P', feeders=['A'], demandas=lectura, nuevas=None, carpeta='Red')
    assert (plan['project'], plan['folder']) == ('Oct/P', 'Red')
    sin = armar_plan(project='P', feeders=['A'], demandas=lectura, nuevas=None)
    assert sin['folder'] is None


def _base(cuadrado=True):
    return {'job_id': 'j1', 'feeders': ['A'], 'variaciones': ['Ajuste_A_20261009_120000'],
            'ajustes': [{'feeder': 'A', 'variacion': 'Ajuste_A_20261009_120000', 'cuadrado': cuadrado,
                         'desvio': {'kw': 0.031, 'kvar': 0.0}, 'cabecera': {'kw': 500.0, 'kvar': 90.0},
                         'objetivo': {'kw': 485.0, 'kvar': 90.0, 'medidor': 'M1'}}],
            'sed': {'S1': {'kw': 40.0, 'kvar': 9.0, 'feeder': 'A'}}, 'excluidos': []}


def test_plan_con_base_y_calibradas_que_el_libro_cambia(tmp_path):
    """007:RF-1 / 007:RF-21 — el plan lleva la base del ajuste y lista las SED calibradas que
    el libro de demandas cambia, con la calibrada y la del libro."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [['SED', 'Kw', 'Kvar'], ['S1', 55, 12], ['S2', 5, 1]]}))
    plan = armar_plan(project='P', feeders=['A'], demandas=lectura, nuevas=None, base=_base())
    assert plan['base']['variaciones'] == ['Ajuste_A_20261009_120000']
    assert plan['calibradas_cambiadas'] == [{'sed': 'S1', 'feeder': 'A', 'calibrada': {'kw': 40.0, 'kvar': 9.0},
                                             'libro': {'kw': 55.0, 'kvar': 12.0}}]
    assert plan['avisos'] == []


def test_base_que_no_cuadro_se_avisa(tmp_path):
    """007:RF-34 — un ajuste que no cuadró sirve de base, con su error en la cabecera."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [['SED', 'Kw'], ['S2', 5]]}))
    plan = armar_plan(project='P', feeders=['A'], demandas=lectura, nuevas=None, base=_base(cuadrado=False))
    assert plan['base'] and len(plan['avisos']) == 1
    assert 'A no cuadró' in plan['avisos'][0] and '+3.10%' in plan['avisos'][0]


def test_sin_base_se_dice(tmp_path):
    """007:RF-5 — sin ajuste previo, el plan dice que se aplica sobre lo activo."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [['SED', 'Kw'], ['S2', 5]]}))
    plan = armar_plan(project='P', feeders=['A'], demandas=lectura, nuevas=None)
    assert plan['base'] is None and 'Sin base' in plan['avisos'][0]
    assert plan['calibradas_cambiadas'] == []


def test_alimentadores_fuera_de_la_base_se_dicen(tmp_path):
    """007:RF-37 — un alimentador cuyo ajuste falló queda fuera de la base, y se dice."""
    lectura = leer_demandas(_libro(tmp_path / 'd.xlsx', {'A': [['SED', 'Kw'], ['S2', 5]]}))
    base = {**_base(), 'excluidos': [{'feeder': 'B', 'motivo': 'su ajuste falló'}]}
    plan = armar_plan(project='P', feeders=['A', 'B'], demandas=lectura, nuevas=None, base=base)
    assert any(a.startswith('B queda fuera de la base') for a in plan['avisos'])


def test_libro_con_filas_vacias_sobre_la_cabecera(tmp_path):
    """004:RF-51 — la cabecera es la primera fila con algo y las filas citan su número en Excel.

    El libro de planificación real la trae en la fila 3 tras dos vacías; tomando la fila 1
    sus cargas se descartaban todas sin un aviso.
    """
    libro = _libro(tmp_path / 'nuevas.xlsx', {'H': [
        [None, None], [None, None],
        ['DESCRIPCION', 'DEM PROY (KW)', 'TRONCAL', 'BARRA'],
        ['Carga A', 120, 'AL1', 'B1'],
        ['Carga B', -5, 'AL1', 'B1'],
    ]})
    lectura = leer_nuevas(libro)
    assert [f.sed for f in lectura.filas] == ['Carga A']
    assert lectura.filas[0].alimentador == 'AL1'
    assert any(e.startswith('hoja H, fila 5:') for e in lectura.errores), lectura.errores


def test_cabecera_irreconocible_es_un_error_y_no_cero_cargas(tmp_path):
    """004:RF-51 — una hoja con datos y sin columnas de carga lo dice, no da cero en silencio."""
    libro = _libro(tmp_path / 'nuevas.xlsx', {'H': [['foo', 'bar'], ['x', 'y']]})
    lectura = leer_nuevas(libro)
    assert not lectura.filas
    assert lectura.errores and 'no se reconoce la cabecera' in lectura.errores[0]


def test_carga_fraccionada_por_anios(tmp_path):
    """030:RF-10 / 030:RF-13 / 030:RF-14 — el total y sus partes por año (calendario o del PIDE);
    si no suman el total, se rechaza diciendo las dos sumas; un solo año de ingreso también vale."""
    libro = _libro(tmp_path / 'nuevas.xlsx', {'H': [
        ['DESCRIPCION', 'TOTAL', 'TRONCAL', 'BARRA', '2027', '2029', 'Año 8', 'AÑO DE INGRESO'],
        ['Planta A', 900, 'AL1', 'B1', 300, 300, 300, None],
        ['Planta B', 1000, 'AL1', 'B1', 300, 300, 300, None],
        ['Planta C', 500, 'AL1', 'B1', None, None, None, 2030],
        ['Planta D', None, 'AL1', 'B1', 100, 50, None, None],
    ]})
    lectura = leer_nuevas(libro)
    por = {f.sed: f for f in lectura.filas}
    assert por['Planta A'].kw == 900 and por['Planta A'].etapas == ((8, 300.0), (2027, 300.0), (2029, 300.0))
    assert 'Planta B' not in por and any('suman 900' in e and '1000' in e for e in lectura.errores)
    assert por['Planta C'].anio_ingreso == 2030 and por['Planta C'].etapas == ()
    assert por['Planta D'].kw == pytest.approx(150) and len(por['Planta D'].etapas) == 2
