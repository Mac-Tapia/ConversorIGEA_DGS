"""Spec 072: el SICODI en libro de cálculo, reconocido por su contenido y hoja por hoja (072:RF-39 a RF-41)."""
from __future__ import annotations

import getpass
import hashlib
import os
import random
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.costos_fuentes import (SUBFAMILIA_POR_TIPO, CostosError, leer_sicodi, normalizar_cabecera,
                                               valorar_obra)
from convertersmartgrid.aplicacion.metrados import valorar_metrados

MUESTRAS = Path(__file__).resolve().parent / 'fixtures' / 'sicodi'
SEMILLA = int(os.environ.get('CSG_SICODI_SEED') or random.SystemRandom().randrange(10**6))

#: Cada campo de costos con las formas en que lo escriben el TXT y el libro.
VARIANTES = {
    'sector': ('COD_SECTOR_TIPICO', 'SECTOR TIPICO', 'Sector Típico'),
    'codigo': ('COD_COSTINVER', 'COD COSTINVER', 'Código Costo de Inversión'),
    'tension': ('COD_TEN_NOMI', 'COD TEN NOMI'),
    'estructura': ('COD_SECUNDARIO', 'COD SECUNDARIO', 'Código Secundario'),
    'nombre': ('NOMBRE_CI', 'NOMBRE'),
    'familia': ('Familia', 'FAMILIA'),
    'subfamilia': ('SubFamilia', 'SUB FAMILIA'),
    'material': ('COSTO_MAT', 'COSTO MAT', 'Costo Material'),
    'stock': ('COSTO_STOCK', 'COSTO STOCK'),
    'mano_obra': ('COSTO_MO', 'COSTO MO', 'Costo Mano de Obra'),
    'transporte': ('COSTO_TRANS', 'COSTO TRANS'),
    'obra': ('COSTO_OBRA', 'COSTO OBRA', 'Costo de Obra'),
    'gastos_generales': ('COSTO_GASTOS_GNRAL', 'COSTO GASTOS GNRAL'),
    'ingenieria': ('COSTO_INGENIERIA', 'Costo Ingeniería'),
    'intercalario': ('COSTO_INTERCALARIO', 'COSTO INTERCALARIO'),
    'total': ('TOTAL', 'Total', 'Costo Total'),
}
COMP = ('material', 'stock', 'mano_obra', 'transporte', 'obra', 'gastos_generales', 'ingenieria', 'intercalario',
        'total')
#: Las cuatro filas del zip de `test_estudio_y_costos`: código, tensión, estructura, sector y total.
FILAS = [('AA03503', 'G', 'C', 'ST2', 100.0), ('AA03503', 'G', 'A', 'ST2', 90.0), ('AA03503', 'D', 'C', 'ST2', 80.0),
         ('AA03503', 'G', 'C', 'ST3', 70.0)]
CAB_TXT = ('EMPRESA\tSECTOR TIPICO\tCOD GRUPO\tGRUPO\tCOD FAMILIA\tFAMILIA\tCOD SUBFAMILIA\tSUBFAMILIA\tCOD COSTINVER\t'
           'COD TEN NOMI\tDSC TEN NOMI\tCOD SECUNDARIO\tDSC SECUNDARIO\tNOMBRE\tCOSTO MAT\tCOSTO STOCK\tCOSTO MO\t'
           'COSTO TRANS\tCOSTO OBRA\tCOSTO GASTOS GNRAL\tCOSTO INGENIERIA\tCOSTO INTERCALARIO\tTOTAL')


def _valores(codigo, ten, sec, sector, total, subfamilia='RED'):
    return {'sector': sector, 'codigo': codigo, 'tension': ten, 'estructura': sec, 'nombre': f'RED {codigo}',
            'familia': 'RED', 'subfamilia': subfamilia, 'material': 1, 'stock': 1, 'mano_obra': 1, 'transporte': 1,
            'obra': 4, 'gastos_generales': 1, 'ingenieria': 1, 'intercalario': 1, 'total': total}


def _hoja_costos(ws, filas, rng, quitar=(), blancos=()):
    """Títulos encima, columnas en orden sorteado y cada cabecera con una de sus formas."""
    campos = [c for c in VARIANTES if c not in quitar]
    rng.shuffle(campos)
    ws.append(['Costos Estándar de Inversión'])
    ws.append([])
    ws.append(['Ítem', *(rng.choice(VARIANTES[c]) for c in campos)])
    for n, v in enumerate(filas, 1):
        ws.append([n, *(None if (n - 1, c) in blancos else v[c] for c in campos)])


def _libro(ruta, *, semilla=SEMILLA, filas=None, quitar=(), blancos=(), solo_costos=False):
    from openpyxl import Workbook

    rng = random.Random(semilla)
    wb = Workbook()
    guia = wb.active
    guia.title = 'Guia'
    guia.append(['Guía de contenido de hojas'])
    guia.append(['Información de', 'Ítem', 'Nombre de Hoja', 'Descripción de contenido'])
    guia.append(['Parámetros', 1, 'Param', 'Parámetros de cálculo'])
    if not solo_costos:
        p = wb.create_sheet('Param')
        p.append([None, None, '% Otros Costos'])
        p.append([None, None, 'Porcentaje del Contratista (%): ', 25])
        p.append([None, None, 'Costo de stock (%): ', 6.81])
    _hoja_costos(wb.create_sheet('CI'), filas or [_valores(*f) for f in FILAS], rng, quitar, blancos)
    if solo_costos:
        wb.save(ruta)
        return ruta
    d = wb.create_sheet('Det')
    d.append(['COD_SECTOR_TIPICO', 'COD_COSTINVER', 'COD_TEN_NOMI', 'COD_SECUNDARIO', 'COD_ARMADO', 'Armado',
              'ABREVIATURA_UM', 'Cantidad', 'COSTO_MAT', 'Total'])
    d.append(['ST2', 'AA03503', 'G', 'C', 'CAMT05-A', 'RETENIDA SIMPLE', 'Und', 2, 10.5, 30.0])
    a = wb.create_sheet('Arm')
    a.append(['Código Armado', 'Código Material', 'Material', 'Unidad', 'Cantidad', 'US$ / Unidad', 'Sub Total  (US$)'])
    a.append(['CAMT05-A', 'ASS06', 'AISLADOR', 'Und', 1, 15.48, 15.48])
    m = wb.create_sheet('Mat')
    m.append(['Periodo', 'Proceso'])
    m.append([])
    m.append(['Código VNR', 'Material', 'Unidad ', 'Valor  (US$)'])
    m.append(['Aisladores y Accesorios'])
    m.append(['AXC02', 'ESPIGA CORTA', 'Und', 3.16])
    m.append(['Total general', None, None, 999])
    r = wb.create_sheet('Rec')
    r.append(['COD_RECURSO', 'Recurso', 'Unidad', 'Valor (US$)', 'VALOR_CALC'])
    r.append(['MOCA01', 'Capataz', 'h-h', 7.14, 8.93])
    mt = wb.create_sheet('Mant')
    mt.append(['Código Componente', 'Descripción', 'Costo de Mantenimiento'])
    mt.append(['RP', 'Red primaria', 1.25])
    t = wb.create_sheet('Trafos')
    t.append(['Transformador', 'Potencia (kVA)', 'Tensión primaria (kV)', 'Fases'])
    t.append(['T-50', 50, 22.9, 3])
    g = wb.create_sheet('Rangos')
    g.append(['Calibre (mm2)', 'Corriente mínima (A)', 'Corriente máxima (A)'])
    g.append(['35', 0, 85.5])
    td = wb.create_sheet('TD')
    td.append(['Etiquetas de fila', 'Familia', 'Descripción', 'Materiales', 'Total '])
    td.append(['A', 'RED AÉREA', 'X', 1, 2])
    rep = wb.create_sheet('Rep')
    rep.append(['Costo de Inversión por kilómetro'])
    rep.append([None, 'Ingeniería del Proyecto (11,17% de E) (US$)', 18.61])
    rep.append([None, 'Gastos Generales (6% de E) (US$)', 10.0])
    wb.save(ruta)
    return ruta


def _zip(ruta):
    cola = '\t1\t1\t1\t1\t4\t1\t1\t1\t'
    lineas = [CAB_TXT] + [f'E\t{s}\t1\tMT\tA\tRED\tA1\tRED\t{c}\t{t}\tkV\t{e}\tEST\tRED {c}{cola}{v}'
                          for c, t, e, s, v in FILAS]
    with zipfile.ZipFile(ruta, 'w') as z:
        z.writestr('Archivos/Instalacion.txt', '\n'.join(lineas))
    return ruta


def _tabla(ruta):
    return leer_sicodi(ruta, resolucion='R-1', anio=2030, moneda='M', url='https://x', fecha_descarga='F')


def _contenido(tabla):
    return {k: (c.nombre, dict(c.componentes), c.familia) for k, c in tabla.filas.items()}


def test_el_libro_da_la_misma_tabla_que_el_zip(tmp_path):
    """072:RF-39 — el libro y el zip del SICODI dan la misma TablaCostos, con su fuente y su huella."""
    libro = _tabla(_libro(tmp_path / 's.xlsx'))
    txt = _tabla(_zip(tmp_path / 's.zip'))
    assert _contenido(libro) == _contenido(txt), f'semilla {SEMILLA}'
    assert libro.buscar('AA03503', 'G', 'C', 'ST2').total == 100.0
    assert libro.fuente.huella == hashlib.sha256((tmp_path / 's.xlsx').read_bytes()).hexdigest()
    assert libro.fuente.nombre == 'SICODI' and libro.fuente.ambito == 'distribucion'
    c = libro.buscar('AA03503', 'D', 'C', 'ST2')
    assert (c.hoja, c.fila) == ('CI', 6)


@pytest.mark.parametrize('formato', ['.xlsx', '.xlsm', '.xls', '.xlsb'])
def test_los_cuatro_formatos_dan_la_misma_tabla(tmp_path, formato):
    """072:RF-39 — .xlsx, .xlsm, .xls y .xlsb, con el lector común (calamine real), dan la misma tabla.

    .xls y .xlsb no se pueden escribir con openpyxl: sus muestras de `tests/fixtures/sicodi/` son este
    mismo libro sintético (`_libro`, semilla 1), guardado con Excel por COM en los formatos 56 y 50 y con
    sus metadatos vaciados (ver `test_las_muestras_no_llevan_metadatos`).
    """
    referencia = _tabla(_libro(tmp_path / 'ref.xlsx', semilla=1))
    if formato in ('.xlsx', '.xlsm'):
        ruta = _libro(tmp_path / f's{formato}', semilla=1)
    else:
        ruta = MUESTRAS / f'sicodi_muestra{formato}'
    tabla = _tabla(ruta)
    assert _contenido(tabla) == _contenido(referencia)
    assert {h: x.tipo for h, x in tabla.hojas.items()} == {h: x.tipo for h, x in referencia.hojas.items()}
    assert {h: list(x.registros()) for h, x in tabla.hojas.items() if x.tipo != 'parametros'} == {
        h: list(x.registros()) for h, x in referencia.hojas.items() if x.tipo != 'parametros'}
    assert tabla.fuente.huella == hashlib.sha256(ruta.read_bytes()).hexdigest()


def _prohibidos() -> list[bytes]:
    """Nombres que delatarían la máquina o la herramienta, en ASCII y en UTF-16."""
    nombres = ['Lenovo', 'Legion', 'openp']
    usuario = getpass.getuser()
    if len(usuario) >= 4:
        nombres += [usuario, *(p for p in usuario.split() if len(p) >= 4)]
    out = []
    for n in nombres:
        for variante in {n, n.lower(), n.upper()}:
            out += [variante.encode('ascii', 'ignore'), variante.encode('utf-16-le')]
    return [p for p in out if p]


@pytest.mark.parametrize('nombre', ['sicodi_muestra.xls', 'sicodi_muestra.xlsb'])
def test_las_muestras_no_llevan_metadatos(nombre):
    """072:RF-39 — las muestras no llevan autor, último en guardar, empresa, título ni ICV; sus fechas son fijas."""
    ruta = MUESTRAS / nombre
    datos = ruta.read_bytes()
    trozos = {nombre: datos}
    if datos[:4] == b'PK' + bytes((3, 4)):
        with zipfile.ZipFile(ruta) as z:
            trozos.update({f'{nombre}:{n}': z.read(n) for n in z.namelist()})
            core, app = z.read('docProps/core.xml').decode('utf-8'), z.read('docProps/app.xml').decode('utf-8')
            custom = z.read('docProps/custom.xml').decode('utf-8') if 'docProps/custom.xml' in z.namelist() else ''
        for etiqueta in ('dc:creator', 'cp:lastModifiedBy', 'dc:title', 'dc:subject', 'cp:keywords'):
            assert not re.search(rf'<{etiqueta}>[^<]+</{etiqueta}>', core), (nombre, etiqueta)
        assert re.findall(r'<dcterms:(?:created|modified)[^>]*>([^<]+)<', core) == ['2000-01-01T00:00:00Z'] * 2
        for etiqueta in ('Company', 'Manager', 'Application'):
            assert not re.search(rf'<{etiqueta}>[^<]+</{etiqueta}>', app), (nombre, etiqueta)
        assert '<property' not in custom
    else:
        # OLE2 (.xls): en el flujo de propiedades, toda fecha es la fija y no queda el ICV de la instalación.
        fija = int((datetime(2000, 1, 1, tzinfo=UTC) - datetime(1601, 1, 1, tzinfo=UTC)).total_seconds() * 10**7)
        fechas = [int.from_bytes(datos[m.end():m.end() + 8], 'little')
                  for m in re.finditer(rb'@\x00\x00\x00', datos) if m.start() % 4 == 0]
        recientes = [f for f in fechas if 125911584000000000 <= f < 157469184000000000]  # entre 2000 y 2100
        assert recientes and set(recientes) == {fija}, recientes
        assert not re.search(rb'(?:[0-9A-F]\x00){32}_\x00', datos)
    for donde, cuerpo in trozos.items():
        hallados = [p for p in _prohibidos() if p in cuerpo]
        assert not hallados, (donde, hallados)


def test_se_reconoce_por_el_contenido_no_por_la_extension(tmp_path):
    """072:RF-39 — un zip con Instalacion.txt llamado .xlsx es el zip; un fichero que no es ninguno lo dice."""
    disfrazado = _zip(tmp_path / 'sicodi.xlsx')
    tabla = _tabla(disfrazado)
    assert tabla.columnas['total'] == 'Instalacion.txt: TOTAL'
    assert _contenido(tabla) == _contenido(_tabla(_zip(tmp_path / 's.zip')))
    raro = tmp_path / 'sicodi.xlsx'
    raro.write_bytes(b'no es un libro')
    with pytest.raises(CostosError, match='ni el zip del SICODI'):
        _tabla(raro)


@pytest.mark.parametrize('semilla', [SEMILLA, SEMILLA + 1, SEMILLA + 2])
def test_columnas_por_contenido_y_sinonimos(tmp_path, semilla):
    """072:RF-39 — sin disposición fija: cada componente dice de qué columna sale."""
    tabla = _tabla(_libro(tmp_path / 's.xlsx', semilla=semilla))
    assert set(tabla.columnas) == set(COMP), f'semilla {semilla}'
    for k, col in tabla.columnas.items():
        hoja, cab = col.split(': ', 1)
        assert hoja == 'CI' and normalizar_cabecera(cab) in {normalizar_cabecera(v) for v in VARIANTES[k]}, \
            f'semilla {semilla}: {k} → {col}'


def test_componente_en_blanco_es_sin_dato_nunca_cero(tmp_path):
    """072:RF-39 — una celda en blanco o una columna que no está es «sin dato»; el total sigue."""
    tabla = _tabla(_libro(tmp_path / 's.xlsx', quitar=('stock',), blancos={(0, 'mano_obra')}))
    c = tabla.buscar('AA03503', 'G', 'C', 'ST2')
    assert c.componentes['mano_obra'] is None and c.componentes['stock'] is None and c.total == 100.0
    assert tabla.buscar('AA03503', 'G', 'A', 'ST2').componentes['mano_obra'] == 1.0
    assert tabla.columnas['stock'] is None
    assert any('stock' in a and 'sin dato' in a for a in tabla.avisos)


def test_sin_hoja_de_costos_error_con_lo_encontrado(tmp_path):
    """072:RF-39 — si las columnas cambian, el error nombra la hoja, lo que falta y lo que encontró."""
    ruta = _libro(tmp_path / 's.xlsx', quitar=('tension',), solo_costos=True)
    with pytest.raises(CostosError, match='ninguna hoja trae los costos') as e:
        _tabla(ruta)
    assert '«CI»' in str(e.value) and 'tension' in str(e.value) and '«Guia»' in str(e.value)


def test_cada_hoja_se_reconoce_y_la_que_no_se_avisa(tmp_path):
    """072:RF-40 — cada hoja por su contenido, con su hoja, su fila y la huella; la no reconocida, en avisos."""
    ruta = _libro(tmp_path / 's.xlsx')
    tabla = _tabla(ruta)
    assert {h: x.tipo for h, x in tabla.hojas.items()} == {
        'Param': 'parametros', 'Det': 'costos_inversion_detalle', 'Arm': 'armados', 'Mat': 'materiales',
        'Rec': 'recursos', 'Mant': 'mantenimiento', 'Trafos': 'transformadores', 'Rangos': 'rangos_corriente'}
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert all(x.huella == huella for x in tabla.hojas.values())
    mat = list(tabla.hojas['Mat'].registros())
    # El título de grupo y el «Total general» de la tabla dinámica no son materiales.
    assert mat == [{'hoja': 'Mat', 'fila': 5, 'cod_material': 'AXC02', 'descripcion_material': 'ESPIGA CORTA',
                    'valor': 3.16, 'unidad': 'Und'}]
    assert tabla.hojas['Mat'].columnas['valor'] == 'Valor  (US$)'
    rec = next(tabla.hojas['Rec'].registros())
    assert (rec['valor'], rec['valor_calculado'], rec['fila']) == (7.14, 8.93, 2)
    assert next(tabla.hojas['Det'].registros())['cantidad'] == 2.0
    assert next(tabla.hojas['Arm'].registros())['costo_unitario'] == 15.48
    assert next(tabla.hojas['Mant'].registros())['costo_mantenimiento'] == 1.25
    assert next(tabla.hojas['Trafos'].registros())['potencia'] == 50.0
    assert next(tabla.hojas['Rangos'].registros())['corriente_max'] == 85.5
    assert [(r['nombre'], r['valor'], r['fila']) for r in tabla.hojas['Param'].registros()] == [
        ('Porcentaje del Contratista (%)', 25.0, 2), ('Costo de stock (%)', 6.81, 3)]
    # El renglón de un informe con «%» no es un parámetro: la hoja se avisa.
    no = [a for a in tabla.avisos if 'no reconocida' in a]
    assert len(no) == 3 and any('«Guia»' in a and 'Nombre de Hoja' in a for a in no)
    assert any('«TD»' in a and 'Etiquetas de fila' in a for a in no) and any('«Rep»' in a for a in no)
    # Lo que hay encima de la cabecera de una tabla dinámica son sus filtros, y se avisa.
    assert tabla.hojas['Mat'].filtros == {'Periodo': 'Proceso'} and tabla.hojas['Rec'].filtros == {}
    assert any('«Mat»' in a and 'filtros' in a for a in tabla.avisos)


def test_clave_ambigua_no_elige_sin_subfamilia(tmp_path):
    """072:RF-41 — dos costos para una misma clave: ninguno sin la subfamilia; con ella, el suyo."""
    filas = [_valores('CU01601', 'X', 'E', 'SER', 0.0, 'RED AÉREA'),
             _valores('CU01601', 'X', 'E', 'SER', 4663.3, 'RED AÉREA ALUMBRADO PÚBLICO'),
             _valores('AA03503', 'G', 'C', 'ST2', 100.0), _valores('AA03503', 'G', 'C', 'ST2', 100.0)]
    tabla = _tabla(_libro(tmp_path / 's.xlsx', filas=filas))
    assert tabla.buscar('CU01601', 'X', 'E', 'SER') is None
    assert 'ambiguo' in tabla.motivo_sin_costo('CU01601', 'X', 'E', 'SER')
    assert tabla.buscar('CU01601', 'X', 'E', 'SER', 'Red aérea alumbrado público').total == 4663.3
    assert tabla.buscar('CU01601', 'X', 'E', 'SER', 'OTRA') is None
    # Dos filas iguales no son una ambigüedad.
    assert tabla.buscar('AA03503', 'G', 'C', 'ST2').total == 100.0
    assert any('subfamilia' in a for a in tabla.avisos)
    obra = valorar_obra([
        {'elemento': 'L1', 'ambito': 'distribucion', 'codigo': 'CU01601X', 'cantidad': 2, 'sector': 'SER',
         'estructura': 'E'},
        {'elemento': 'L2', 'ambito': 'distribucion', 'codigo': 'CU01601X', 'cantidad': 2, 'sector': 'SER',
         'estructura': 'E', 'subfamilia': 'RED AÉREA ALUMBRADO PÚBLICO'}], {'distribucion': tabla})
    assert [x['elemento'] for x in obra['valorados']] == ['L2'] and obra['valorados'][0]['costo'] == 2 * 4663.3
    assert 'ambiguo' in obra['sin_costo'][0]['motivo']


def _tabla_por_subfamilias(tmp_path, subfamilias):
    filas = [_valores('CU01601', 'X', 'E', 'SER', total, sub) for sub, total in subfamilias]
    return _tabla(_libro(tmp_path / 's.xlsx', filas=filas))


def _elemento(nombre, tipo):
    return {'elemento': nombre, 'ambito': 'distribucion', 'codigo': 'CU01601X', 'cantidad': 1, 'sector': 'SER',
            'estructura': 'E', 'tipo': tipo}


def test_el_tipo_del_elemento_deduce_la_subfamilia(tmp_path):
    """072:RF-41 — sin subfamilia en la red, el tipo la deduce con la tabla universal y se anota."""
    tabla = _tabla_por_subfamilias(tmp_path, [('RED AÉREA', 10.0),
                                              ('RED AÉREA ALUMBRADO PÚBLICO - SOBRE ESTRUCTURA AP', 4663.3),
                                              ('RED SUBTERRÁNEA', 20.0)])
    obra = valorar_obra([_elemento('L1', 'tramo_aereo'), _elemento('L2', 'tramo_subterraneo'),
                         _elemento('L3', 'tramo_alumbrado_aereo')], {'distribucion': tabla})
    assert obra['completa'] and [(x['elemento'], x['costo']) for x in obra['valorados']] == [
        ('L1', 10.0), ('L2', 20.0), ('L3', 4663.3)]
    assert all(x['anotacion'].startswith('subfamilia deducida por el tipo') for x in obra['valorados'])
    assert 'RED AÉREA' in obra['valorados'][0]['anotacion']
    # Un código solo aéreo en los metrados de la red toma la red aérea, con la misma anotación.
    v = valorar_metrados({'CU01601X': {'tramos': 1, 'km': 2.0, 'km_aereo': 2.0, 'km_subterraneo': 0.0}}, tabla,
                         sector='SER', estructura='E')
    assert v['total'] == 20.0 and 'subfamilia deducida por el tipo' in v['valorados'][0]['anotacion']
    # Un costo que no es ambiguo no lleva anotación.
    assert 'anotacion' not in valorar_obra([{**_elemento('L4', 'tramo_aereo'), 'codigo': 'AA03503G',
                                              'sector': 'ST2', 'estructura': 'C'}],
                                           {'distribucion': _tabla(_libro(tmp_path / 'b.xlsx'))})['valorados'][0]


def test_el_tipo_que_no_decide_deja_la_ambiguedad(tmp_path):
    """072:RF-41 — si el tipo no decide entre varias subfamilias, la ambigüedad se nombra y no hay costo."""
    tabla = _tabla_por_subfamilias(tmp_path, [('RED AÉREA', 10.0), ('RED AÉREA SERVICIO PARTICULAR', 12.0),
                                              ('RED SUBTERRÁNEA', 20.0)])
    obra = valorar_obra([_elemento('L1', 'tramo_aereo'), _elemento('L2', 'poste'), _elemento('L3', '')],
                        {'distribucion': tabla})
    assert obra['valorados'] == []
    motivos = [x['motivo'] for x in obra['sin_costo']]
    assert 'el tipo «tramo_aereo» no decide' in motivos[0]
    assert 'el tipo «poste» no está en la tabla' in motivos[1]
    assert 'no declara su tipo' in motivos[2]
    assert all('ambiguo' in m for m in motivos)
    # Tramos aéreos y subterráneos con el mismo código: el tipo no decide.
    v = valorar_metrados({'CU01601X': {'tramos': 2, 'km': 2.0, 'km_aereo': 1.0, 'km_subterraneo': 1.0}}, tabla,
                         sector='SER', estructura='E')
    assert v['valorados'] == [] and 'ambiguo' in v['sin_costo'][0]['motivo']


def test_la_tabla_de_subfamilias_es_universal():
    """072:RF-41 — la correspondencia tipo → subfamilia es una tabla, sin nombres de empresas ni de redes."""
    for tipo, (lleva, no_lleva) in SUBFAMILIA_POR_TIPO.items():
        assert lleva, tipo
        assert all(p == normalizar_cabecera(p) for p in (*lleva, *no_lleva)), tipo


def test_sicodi_real_en_libro():
    """072:RF-39, 072:RF-40, 072:RF-41 — el libro real de `CSG_SICODI`, todas sus hojas, sin copiarlo."""
    ruta = Path(os.environ.get('CSG_SICODI') or '')
    if not os.environ.get('CSG_SICODI') or not ruta.is_file():
        pytest.skip('CSG_SICODI no apunta a un libro del SICODI')
    tabla = leer_sicodi(ruta, resolucion='SICODI declarado', anio=0, moneda='declarada', url='https://declarada',
                        fecha_descarga='declarada')
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    assert tabla.fuente.huella == h.hexdigest()
    assert tabla.filas, 'el libro real no dio ningún costo'
    assert all(tabla.columnas.get(k) for k in COMP), tabla.columnas
    tipos = {x.tipo for x in tabla.hojas.values()}
    assert {'materiales', 'recursos', 'armados', 'parametros'} <= tipos, tipos
    for x in tabla.hojas.values():
        assert x.huella == tabla.fuente.huella and all(f[0] > x.fila_cabecera for f in x.filas)
    c = next(iter(tabla.filas.values()))
    assert c.hoja and c.fila > 1 and c.total == c.componentes['total']
    for clave, costos in tabla.ambiguos.items():
        assert tabla.buscar(*clave) is None and len({c.componentes['total'] for c in costos}) >= 1
    reconocidas = set(tabla.hojas) | {c.split(': ', 1)[0] for c in tabla.columnas.values() if c}
    citadas = {a.split('«', 1)[1].split('»', 1)[0] for a in tabla.avisos if 'no reconocida' in a}
    from python_calamine import CalamineWorkbook
    libro = CalamineWorkbook.from_path(str(ruta))
    try:
        assert reconocidas | citadas == set(libro.sheet_names)
    finally:
        libro.close()
