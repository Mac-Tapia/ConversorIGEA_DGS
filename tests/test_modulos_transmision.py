"""Spec 072 T3: módulos estándar de transmisión por el mismo contrato de costos que el SICODI.

Los libros son sintéticos: el fichero de la Res. 152-2026-OS/CD (sustituido por la 181-2026-OS/CD)
no se lee desde ninguna prueba, y su disposición de columnas se declara, no se supone.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from convertersmartgrid.costos_fuentes import (CostosError, leer_modulos_transmision, leer_sicodi,
                                               valorar_obra)
from convertersmartgrid.metrados import valorar_metrados

COLUMNAS = {'codigo': 'Código Módulo', 'nombre': 'Descripción', 'unidad': 'Unidad', 'total': 'Costo Total'}
COLUMNAS_ZONA = {**COLUMNAS, 'zona': 'Zona'}
CAB_SICODI = ('EMPRESA\tSECTOR TIPICO\tCOD GRUPO\tGRUPO\tCOD FAMILIA\tFAMILIA\tCOD SUBFAMILIA\tSUBFAMILIA\t'
              'COD COSTINVER\tCOD TEN NOMI\tDSC TEN NOMI\tCOD SECUNDARIO\tDSC SECUNDARIO\tNOMBRE\tCOSTO MAT\t'
              'COSTO STOCK\tCOSTO MO\tCOSTO TRANS\tCOSTO OBRA\tCOSTO GASTOS GNRAL\tCOSTO INGENIERIA\t'
              'COSTO INTERCALARIO\tTOTAL')


def _libro(ruta, filas, *, cabecera=('Código Módulo', 'Descripción', 'Unidad', 'Costo Total'), hoja='Resumen'):
    """Un libro con títulos encima de la cabecera, como publica Osinergmin sus anexos."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(['BASE DE DATOS DE MÓDULOS ESTÁNDAR (sintética)'])
    ws.append([])
    ws.append(list(cabecera))
    for f in filas:
        ws.append(list(f))
    wb.save(ruta)
    return ruta


def _modulos(ruta, columnas=COLUMNAS, **kw):
    return leer_modulos_transmision(ruta, columnas=columnas, resolucion='R-T', anio=2030, moneda='MT',
                                    url='https://t', fecha_descarga='F', **kw)


@pytest.fixture
def libro(tmp_path):
    return _libro(tmp_path / 'm.xlsx', [
        ('LT-A1', 'Línea de transmisión simple terna', 'km', 1000.0),
        ('CE-B1', 'Celda de línea', 'u', 300.0),
        (None, 'Subtotal', None, None),  # filas de título intermedio, sin código, no son módulos
        ('TP-C1', 'Transformador de potencia', 'u', 5000.0),
    ])


@pytest.fixture
def zip_sicodi(tmp_path):
    ruta = tmp_path / 's.zip'
    fila = 'E\tST2\t1\tMT\tA\tRED\tA1\tRED\tAA03503\tG\tkV\tC\tEST\tRED AA03503\t1\t1\t1\t1\t4\t1\t1\t1\t100.0'
    with zipfile.ZipFile(ruta, 'w') as z:
        z.writestr('Archivos/Instalacion.txt', '\n'.join([CAB_SICODI, fila]))
    return leer_sicodi(ruta, resolucion='R-D', anio=2030, moneda='MD', url='https://d', fecha_descarga='F')


def test_los_modulos_declaran_su_fuente(libro):
    """072:RF-5, 072:RF-9 — ámbito transmisión, resolución, año, moneda, URL, fecha y huella del fichero."""
    t = _modulos(libro)
    f = t.fuente
    assert (f.nombre, f.ambito, f.resolucion, f.anio, f.moneda, f.url, f.fecha_descarga) == \
        ('Módulos estándar de transmisión', 'transmision', 'R-T', 2030, 'MT', 'https://t', 'F')
    assert f.huella == hashlib.sha256(libro.read_bytes()).hexdigest()
    assert set(t.modulos()) == {'LT-A1', 'CE-B1', 'TP-C1'}
    c = t.buscar_modulo('LT-A1')
    assert (c.total, c.unidad, c.nombre) == (1000.0, 'km', 'Línea de transmisión simple terna')


def test_sin_moneda_no_hay_fuente(libro):
    """072:RF-5 — la moneda se declara; el libro no la supone."""
    with pytest.raises(CostosError, match='moneda'):
        leer_modulos_transmision(libro, columnas=COLUMNAS, resolucion='R', anio=2030, moneda='', url='u',
                                 fecha_descarga='F')


@pytest.mark.parametrize('columnas, motivo', [
    ({'codigo': 'Código Módulo', 'total': 'Costo Total'}, 'unidad'),
    ({**COLUMNAS, 'total': 'Costo (inexistente)'}, 'Costo \\(inexistente\\)'),
])
def test_columnas_declaradas_o_lo_dice(libro, columnas, motivo):
    """072:RF-5 — la disposición cambia con cada resolución: se declara y, si no está, se nombra."""
    with pytest.raises(CostosError, match=motivo):
        _modulos(libro, columnas=columnas)


def test_hoja_inexistente_o_codigo_repetido(tmp_path, libro):
    """072:RF-7 — dos costos para un mismo módulo no se resuelven eligiendo uno."""
    with pytest.raises(CostosError, match='hoja'):
        _modulos(libro, hoja='NoExiste')
    rep = _libro(tmp_path / 'r.xlsx', [('LT-A1', 'x', 'km', 1.0), ('LT-A1', 'x', 'km', 2.0)])
    with pytest.raises(CostosError, match='LT-A1'):
        _modulos(rep)
    sin_total = _libro(tmp_path / 't.xlsx', [('LT-A1', 'x', 'km', None)])
    with pytest.raises(CostosError, match='sin total'):
        _modulos(sin_total)


def test_una_obra_de_transmision_se_valora_con_sus_modulos(libro):
    """072:RF-6, 072:RF-15 — metrado × costo unitario del módulo, elemento por elemento."""
    t = _modulos(libro)
    r = valorar_obra([
        {'elemento': 'LT 60 kV', 'ambito': 'transmision', 'codigo': 'LT-A1', 'cantidad': 12.5, 'unidad': 'km'},
        {'elemento': 'Celdas', 'ambito': 'transmision', 'codigo': 'CE-B1', 'cantidad': 2, 'unidad': 'u'},
    ], {'transmision': t})
    assert r['sin_costo'] == [] and r['completa'] is True
    assert r['total_por_moneda'] == {'MT': 12.5 * 1000.0 + 2 * 300.0}
    assert {x['fuente'] for x in r['valorados']} == {'R-T'}


def test_lo_que_no_cruza_queda_nombrado_y_fuera_del_total(libro):
    """072:RF-7, 072:RF-15, 072:RF-16 — sin módulo, sin metrado o con otra unidad: hueco, no costo."""
    t = _modulos(libro)
    r = valorar_obra([
        {'elemento': 'A', 'ambito': 'transmision', 'codigo': 'LT-A1', 'cantidad': 1, 'unidad': 'km'},
        {'elemento': 'B', 'ambito': 'transmision', 'codigo': 'LT-ZZ', 'cantidad': 3},
        {'elemento': 'C', 'ambito': 'transmision', 'codigo': 'CE-B1'},
        {'elemento': 'D', 'ambito': 'transmision', 'codigo': 'LT-A1', 'cantidad': 4, 'unidad': 'm'},
        {'elemento': 'E', 'ambito': 'generacion', 'codigo': 'X', 'cantidad': 1},
    ], {'transmision': t})
    assert r['total_por_moneda'] == {'MT': 1000.0} and r['completa'] is False
    motivos = {x['elemento']: x['motivo'] for x in r['sin_costo']}
    assert 'LT-ZZ' in motivos['B'] and 'no está' in motivos['B']
    assert 'metrado' in motivos['C']
    assert 'unidad' in motivos['D'] and 'km' in motivos['D']
    assert 'generacion' in motivos['E']


def test_distribucion_y_transmision_no_se_mezclan(libro, zip_sicodi):
    """072:RF-6 — cada elemento con la fuente de su ámbito, nunca con la otra aunque el código cruce."""
    t = _modulos(libro)
    elementos = [
        {'elemento': 'Red MT', 'ambito': 'distribucion', 'codigo': 'AA03503G', 'cantidad': 2,
         'sector': 'ST2', 'estructura': 'C'},
        {'elemento': 'LT', 'ambito': 'transmision', 'codigo': 'LT-A1', 'cantidad': 1, 'unidad': 'km'},
    ]
    r = valorar_obra(elementos, {'distribucion': zip_sicodi, 'transmision': t})
    assert r['total_por_moneda'] == {'MD': 200.0, 'MT': 1000.0}  # cada moneda por su lado, sin convertir
    assert {x['elemento']: x['fuente'] for x in r['valorados']} == {'Red MT': 'R-D', 'LT': 'R-T'}
    # Sin la fuente de transmisión, la LT queda como hueco: el SICODI no la valora.
    solo = valorar_obra([{**elementos[1], 'codigo': 'LT-A1'}], {'distribucion': zip_sicodi})
    assert solo['valorados'] == [] and 'transmision' in solo['sin_costo'][0]['motivo']
    # Una tabla declarada con el ámbito que no es el suyo no se acepta.
    with pytest.raises(CostosError, match='ámbito'):
        valorar_obra(elementos, {'transmision': zip_sicodi})
    with pytest.raises(CostosError, match='ámbito'):
        valorar_metrados({'LT-A1': {'km': 1.0, 'km_aereo': 1.0}}, t, sector='ST2', estructura='C')


def test_zona_declarada_se_cruza(tmp_path):
    """072:RF-7, 072:RF-17 — si el libro trae zona, el elemento la declara desde el perfil; sin ella, hueco."""
    ruta = _libro(tmp_path / 'z.xlsx', [('LT-A1', 'x', 'km', 100.0, 'COSTA'), ('LT-A1', 'x', 'km', 130.0, 'SIERRA')],
                  cabecera=('Código Módulo', 'Descripción', 'Unidad', 'Costo Total', 'Zona'))
    t = _modulos(ruta, columnas=COLUMNAS_ZONA)
    base = {'ambito': 'transmision', 'codigo': 'LT-A1', 'cantidad': 1, 'unidad': 'km'}
    r = valorar_obra([{**base, 'elemento': 'S', 'zona': 'SIERRA'}, {**base, 'elemento': 'N'},
                      {**base, 'elemento': 'X', 'zona': 'SELVA'}], {'transmision': t})
    assert r['total_por_moneda'] == {'MT': 130.0}
    motivos = {x['elemento']: x['motivo'] for x in r['sin_costo']}
    assert 'zona' in motivos['N'] and 'SELVA' in motivos['X']


def _herramienta():
    import importlib.util

    ruta = Path(__file__).resolve().parents[1] / 'tools/costos_cruce.py'
    spec = importlib.util.spec_from_file_location('costos_cruce_072', ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_la_herramienta_valora_una_obra_de_transmision(tmp_path, libro, capsys):
    """072:RF-6, 072:RF-9 — `tools/costos_cruce.py --obra` con solo módulos, sin SICODI ni sector."""
    obra = tmp_path / 'obra.json'
    obra.write_text(json.dumps([{'elemento': 'LT', 'ambito': 'transmision', 'codigo': 'LT-A1', 'cantidad': 3,
                                 'unidad': 'km'},
                                {'elemento': 'Red', 'ambito': 'distribucion', 'codigo': 'AA03503G', 'cantidad': 1}]),
                    encoding='utf-8')
    cols = tmp_path / 'cols.json'
    cols.write_text(json.dumps(COLUMNAS, ensure_ascii=False), encoding='utf-8')
    salida = tmp_path / 'r.json'
    base = ['--obra', str(obra), '--modulos', str(libro), '--modulos-columnas', str(cols), '--salida', str(salida)]
    prov = ['--modulos-resolucion', 'R-T', '--modulos-anio', '2030', '--modulos-moneda', 'MT',
            '--modulos-url', 'https://t', '--modulos-fecha-descarga', 'F']
    h = _herramienta()
    assert h.main(base) == 2 and '--modulos-moneda' in capsys.readouterr().out
    assert h.main(base + prov) == 0
    r = json.loads(salida.read_text(encoding='utf-8'))
    assert r['total_por_moneda'] == {'MT': 3000.0}
    assert r['fuentes']['transmision']['huella'] == hashlib.sha256(libro.read_bytes()).hexdigest()
    assert 'distribucion' in r['sin_costo'][0]['motivo']


def test_factor_solo_con_sustento(libro):
    """072:RF-8 — el factor de Amazonía de la resolución se declara con su sustento o no se aplica."""
    with pytest.raises(CostosError, match='sustento'):
        _modulos(libro, factor=1.05)
    t = _modulos(libro, factor=1.05, sustento_factor='artículo 2 de la resolución (sintético)')
    r = valorar_obra([{'elemento': 'A', 'ambito': 'transmision', 'codigo': 'CE-B1', 'cantidad': 1}],
                     {'transmision': t})
    assert r['total_por_moneda']['MT'] == pytest.approx(300.0 * 1.05)
    assert r['valorados'][0]['factor'] == 1.05


def _base_por_hojas(tmp_path):
    """Como la base real: una hoja por tipo de módulo, sin columna de unidad y con filtros encima."""
    wb = Workbook()
    for i, (titulo, filas) in enumerate((('Res LT', [('LT-060A', 'Línea 60 kV', 1000.0)]),
                                         ('Res CEL', [('CE-060A', 'Celda 60 kV', 300.0)]))):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = titulo
        ws.append(['Filtros', 'Tension'])
        ws.append([])
        ws.append(['CODIGO', 'Descripción', 'TOTAL GENERAL \n(USD)'])
        for f in filas:
            ws.append(list(f))
    ruta = tmp_path / 'base.xlsx'
    wb.save(ruta)
    return ruta


def test_unidades_por_codigo_no_pueden_contradecir_declaracion_fija(tmp_path):
    """072:RF-5, 072:RF-7 — fragmento auténtico RR181, no un costo inventado.

    REST_MOD_INV_2025_RR.xlsm SHA7bddb201...f712505, I-114 Res Mod TL:
    PHD-COU=1113.0655325190469 USD; I-104 Val TL B43 dice costo por METRO.
    Sus 50m nominales no autorizan etiquetar el precio como km ni convertirlo.
    """
    ruta = _libro(tmp_path/'fragmento181.xlsx',
        [('PHD-COU', 'PERFORACIÓN HORIZONTAL DIRIGIDA', 1113.0655325190469)],
        cabecera=('CODIGO', 'Descripción', 'TOTAL GENERAL \n(USD)'), hoja='I-114 Res Mod TL')
    cols = {'codigo': 'CODIGO', 'nombre': 'Descripción', 'total': 'TOTAL GENERAL \n(USD)'}
    # Sin columna, la declaración del operador se conserva como tal; no la
    # certifica ni la infiere el lector. Una segunda declaración contradictoria sí falla.
    assert _modulos(ruta, columnas=cols, hoja='I-114 Res Mod TL',
                    unidad='km').buscar_modulo('PHD-COU').unidad == 'km'
    for unidad in ('km', {'I-114 Res Mod TL': 'km'}):
        with pytest.raises(CostosError, match='unidad'):
            _modulos(ruta, columnas=cols, hoja='I-114 Res Mod TL', unidad=unidad,
                     unidades_por_codigo={'PHD-COU': 'm'})


def test_unidad_por_codigo_autentico_conserva_precio_y_archivo(tmp_path):
    """072:RF-5, 072:RF-8, 072:RF-9 — la unidad no introduce un factor de precio."""
    ruta = _libro(tmp_path/'fragmento181.xlsx',
        [('PHD-COU', 'PERFORACIÓN HORIZONTAL DIRIGIDA', 1113.0655325190469)],
        cabecera=('CODIGO', 'Descripción', 'TOTAL GENERAL \n(USD)'))
    cols = {'codigo': 'CODIGO', 'nombre': 'Descripción', 'total': 'TOTAL GENERAL \n(USD)'}
    antes, mtime = ruta.read_bytes(), ruta.stat().st_mtime_ns
    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        precio_guardado = wb.active['C4'].value
    finally:
        wb.close()
    tabla = _modulos(ruta, columnas=cols, unidades_por_codigo={'PHD-COU': 'm'})
    assert tabla.buscar_modulo('PHD-COU').unidad == 'm'
    assert tabla.buscar_modulo('PHD-COU').total == precio_guardado
    assert tabla.fuente.factor is None
    assert tabla.fuente.huella == hashlib.sha256(antes).hexdigest()
    assert ruta.read_bytes() == antes and ruta.stat().st_mtime_ns == mtime
    with pytest.raises(CostosError, match='PHD-COU'):
        _modulos(ruta, columnas=cols, unidades_por_codigo={'OTRO': 'km'})


def test_declaracion_no_sobrescribe_unidad_autentica_de_columna(libro):
    """072:RF-7 — ni fija ni mapa por código pueden contradecir la fuente."""
    for declaracion in ({'unidad': 'km'},
                        {'unidades_por_codigo': {'LT-A1': 'km', 'CE-B1': 'km', 'TP-C1': 'u'}}):
        with pytest.raises(CostosError, match='unidad'):
            _modulos(libro, **declaracion)


def test_modulo_sin_unidad_en_fila_no_se_inventa(tmp_path):
    """072:RF-7, 072:RF-16 — declarar el nombre de columna no rellena celdas vacías."""
    ruta = _libro(tmp_path/'sin_unidad.xlsx', [('PHD-COU', 'PHD', '', 1113.0655325190469)])
    with pytest.raises(CostosError, match='unidad'):
        _modulos(ruta)


def test_mapa_por_codigo_exige_cobertura_y_declaraciones_compatibles(libro, tmp_path):
    """072:RF-7 — si se proporciona el mapa, un código ausente no hereda otro."""
    with pytest.raises(CostosError, match='CE-B1'):
        _modulos(libro, unidades_por_codigo={'LT-A1': 'km'})
    for mapa in ({'LT-A1': ''}, {'LT-A1': True}, ['km']):
        with pytest.raises(CostosError, match='unidades_por_codigo'):
            _modulos(libro, unidades_por_codigo=mapa)
    ruta = _libro(tmp_path/'compatible.xlsx', [('PHD-COU', 'PHD', 'm', 1113.0655325190469)])
    for fija in ('m', {'Resumen': 'm'}):
        tabla = _modulos(ruta, hoja='Resumen', unidad=fija, unidades_por_codigo={'PHD-COU': 'm'})
        assert tabla.buscar_modulo('PHD-COU').unidad == 'm'


def test_cli_pasa_mapa_por_codigo_sin_inferir_unidades(tmp_path, capsys):
    """072:RF-5, 072:RF-9 — opción aditiva, mismas fuentes/precios de la fixture."""
    ruta = _base_por_hojas(tmp_path)
    columnas = tmp_path/'columnas.json'
    columnas.write_text(json.dumps({'codigo': 'CODIGO', 'nombre': 'Descripción',
                                   'total': 'TOTAL GENERAL \n(USD)'}), encoding='utf-8')
    unidades = tmp_path/'unidades_por_codigo.json'
    unidades.write_text(json.dumps({'LT-060A': 'km', 'CE-060A': 'u'}), encoding='utf-8')
    obra = tmp_path/'obra_sintetica.json'
    obra.write_text(json.dumps([{'elemento': 'LT de prueba', 'ambito': 'transmision',
                                'codigo': 'LT-060A', 'cantidad': 2, 'unidad': 'km'}]), encoding='utf-8')
    salida = tmp_path/'valoracion_sintetica.json'
    args = ['--obra', str(obra), '--modulos', str(ruta), '--modulos-columnas', str(columnas),
            '--modulos-hoja', 'Res LT', '--modulos-hoja', 'Res CEL',
            '--modulos-unidades-por-codigo', str(unidades), '--modulos-resolucion', 'R-T',
            '--modulos-anio', '2030', '--modulos-moneda', 'MT', '--modulos-url', 'https://t',
            '--modulos-fecha-descarga', 'F', '--salida', str(salida)]
    assert _herramienta().main(args) == 0
    r = json.loads(salida.read_text(encoding='utf-8'))
    assert r['total_por_moneda'] == {'MT': 2000.0}
    assert r['fuentes']['transmision']['huella'] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert r['fuentes']['transmision']['resolucion'] == 'R-T'
    assert capsys.readouterr().out


def test_base_por_hojas_con_la_unidad_declarada(tmp_path):
    """072:RF-5, 072:RF-7 — la base de la resolución trae una hoja por tipo de módulo y no dice la unidad:
    se leen las hojas declaradas, cada una con la unidad que se declara (km en las líneas), y sin
    unidad declarada se rechaza en vez de suponerla."""
    ruta = _base_por_hojas(tmp_path)
    cols = {'codigo': 'CODIGO', 'nombre': 'Descripción', 'total': 'TOTAL GENERAL \n(USD)'}
    t = _modulos(ruta, columnas=cols, hoja=['Res LT', 'Res CEL'], unidad={'Res LT': 'km', 'Res CEL': 'u'})
    assert set(t.modulos()) == {'LT-060A', 'CE-060A'}
    assert (t.buscar_modulo('LT-060A').unidad, t.buscar_modulo('CE-060A').unidad) == ('km', 'u')
    r = valorar_obra([{'elemento': 'LT', 'ambito': 'transmision', 'codigo': 'LT-060A', 'cantidad': 2, 'unidad': 'km'},
                      {'elemento': 'Celda', 'ambito': 'transmision', 'codigo': 'CE-060A', 'cantidad': 1}],
                     {'transmision': t})
    assert r['total_por_moneda'] == {'MT': 2300.0} and r['completa']
    with pytest.raises(CostosError, match='unidad'):
        _modulos(ruta, columnas=cols, hoja=['Res LT', 'Res CEL'], unidad={'Res LT': 'km'})
    with pytest.raises(CostosError, match='unidad'):
        _modulos(ruta, columnas=cols, hoja='Res LT')
    assert _modulos(ruta, columnas=cols, hoja='Res LT', unidad='km').buscar_modulo('LT-060A').unidad == 'km'
