"""Spec 107 T5 — la red del área (contrato neutro) y el libro de la red declarado en el perfil (107:RF-2, 107:RF-4)."""
from __future__ import annotations

import getpass
import hashlib
import socket
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import openpyxl
import pytest

from datos_pit import perfil_a, perfil_b

from convertersmartgrid.pit.ambito import PitError, areas_del_perfil, reunir
from convertersmartgrid.pit.red_area import REQUERIDOS, desde_ambito, leer_libro_red

SEMILLAS = (2, 29)


def _libro(tmp_path, elementos):
    """El libro de la red con encabezados propios de la «empresa», que el perfil traduce a las claves del contrato."""
    claves = sorted({k for e in elementos for k in e})
    columnas = {k: f'Dato {k.replace("_", " ").upper()}' for k in claves}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Red AT'
    ws.append(['Inventario de transmisión'])
    ws.append([columnas[k] for k in claves])
    for e in elementos:
        fila = []
        for k in claves:
            v = e.get(k)
            fila.append(', '.join(v) if isinstance(v, list) else v)
        ws.append(fila)
    ruta = tmp_path / 'red.xlsx'
    wb.save(ruta)
    return ruta, {'hoja': 'Red AT', 'fila_cabecera': 2, 'columnas': columnas}


def _red(caso, tmp_path):
    ruta, cfg = _libro(tmp_path, caso['elementos'])
    elementos = leer_libro_red(ruta, cfg)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    return ruta, desde_ambito(reunir(area, elementos))


@pytest.mark.parametrize('seed', SEMILLAS)
def test_perfil_b_linea_sin_parametros_en_faltantes(seed, tmp_path):
    """107:RF-4 — la línea sin parámetros queda nombrada con lo que le falta y fuera de la red que se calcula."""
    caso = perfil_b(seed)
    _, red = _red(caso, tmp_path)
    sp = caso['pistas']['sin_parametros']
    falta = {f['id']: f for f in red.faltantes}
    assert sp in falta and 'r_ohm_per_km' in falta[sp]['falta'] and 'max_i_ka' in falta[sp]['falta']
    assert sp not in red.ids()
    assert not red.completa
    assert caso['pistas']['compartida'] in red.incompletos


@pytest.mark.parametrize('seed', SEMILLAS)
def test_cada_elemento_con_titular_area_y_fuente(seed, tmp_path):
    """107:RF-2 — cada elemento modelado dice su titular, su área y la fila del libro con la huella del libro."""
    caso = perfil_a(seed)
    ruta, red = _red(caso, tmp_path)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert red.completa and not red.faltantes
    for tipo, lista in red.elementos.items():
        assert tipo in REQUERIDOS
        for e in lista:
            assert e['titular'] in caso['pistas']['titulares'] and e['area'] == caso['area']
            assert e['fuente']['sha256'] == huella and e['fuente']['hoja'] == 'Red AT' and e['fuente']['fila'] > 2
    assert red.barras_de_carga() == {s: f'B-{s}-MT' for s in caso['pistas']['sets']}


def test_linea_a_una_barra_fuera_del_ambito(tmp_path):
    """107:RF-4 — un elemento que llega a una barra que no es del ámbito no se modela y se dice por qué."""
    caso = perfil_a(8)
    s = caso['pistas']['sets'][0]
    caso['elementos'].append({**next(e for e in caso['elementos'] if e['id'] == f'L-{s}'),
                              'id': 'L-suelta', 'hasta': 'B-inexistente'})
    _, red = _red(caso, tmp_path)
    falta = {f['id']: f for f in red.faltantes}
    assert 'B-inexistente' in ' '.join(falta['L-suelta']['falta'])


def test_libro_sin_la_columna_declarada(tmp_path):
    """107:RF-11 — el libro lo describe el perfil: una columna declarada que no está es un error que la nombra."""
    ruta, cfg = _libro(tmp_path, perfil_a(1)['elementos'])
    cfg['columnas']['id'] = 'Código que no existe'
    with pytest.raises(PitError, match='Código que no existe'):
        leer_libro_red(ruta, cfg)


# --- Todos los formatos y todas las hojas (orden del usuario 2026-11-14) -------------------------------------------

def _filas(elementos, columnas, claves):
    out = [[columnas[k] for k in claves]]
    for e in elementos:
        out.append([', '.join(e[k]) if isinstance(e.get(k), list) else e.get(k) for k in claves])
    return out


def _libro_hojas(tmp_path, hojas, nombre='red.xlsx'):
    """Un libro con varias hojas: ``hojas`` es nombre → filas; la cabecera puede no estar en la primera fila."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, filas in hojas.items():
        ws = wb.create_sheet(titulo)
        for f in filas:
            ws.append(f)
    ruta = tmp_path / nombre
    wb.save(ruta)
    return ruta


def _repartido(caso):
    """Las líneas en una hoja (cabecera en la fila 3, tras un título), el resto en otra y una hoja de notas sin
    contrato."""
    claves = sorted({k for e in caso['elementos'] for k in e})
    columnas = {k: f'Dato {k.replace("_", " ").upper()}' for k in claves}
    lineas = [e for e in caso['elementos'] if e['tipo'] == 'linea']
    resto = [e for e in caso['elementos'] if e['tipo'] != 'linea']
    hojas = {'Notas': [['Notas del inventario'], ['Revisado por', 'planificación']],
             'Líneas': [['Líneas de transmisión'], []] + _filas(lineas, columnas, claves),
             'Barras y trafos': _filas(resto, columnas, claves)}
    return hojas, columnas, lineas, resto


def _sin_fuente(elementos):
    return sorted(({k: v for k, v in e.items() if k != 'fuente'} for e in elementos), key=lambda e: e['id'])


@pytest.mark.parametrize('ext', ['.xlsx', '.xlsm'])
def test_mismo_libro_en_xlsx_y_xlsm(ext, tmp_path):
    """107:RF-12 — el mismo libro en .xlsx y en .xlsm da los mismos elementos, con la huella de cada fichero."""
    caso = perfil_a(5)
    ruta, cfg = _libro(tmp_path, caso['elementos'])
    otra = tmp_path / f'red_copia{ext}'
    otra.write_bytes(ruta.read_bytes())
    base, leidos = leer_libro_red(ruta, cfg), leer_libro_red(otra, cfg)
    assert _sin_fuente(leidos) == _sin_fuente(base) and len(leidos) == len(caso['elementos'])
    huella = hashlib.sha256(otra.read_bytes()).hexdigest()
    assert {(e['fuente']['libro'], e['fuente']['sha256']) for e in leidos} == {(otra.name, huella)}


#: Muestras sintéticas, sin datos de ninguna empresa: el ``perfil_a(13)`` de datos_pit en una hoja
#: «Inventario» (título en la fila 1, claves del contrato en la 2) y una hoja «Notas» sin contrato, escritas con
#: openpyxl y guardadas como .xls (FileFormat 56) y .xlsb (50) por COM de WPS el 2026-11-14. Sin metadatos
#: personales: docProps genéricos en los zip y, en el .xls, el último que guardó borrado en su sitio. Huellas en
#: 107/PROGRESO.md.
MUESTRAS = Path(__file__).resolve().parent / 'fixtures' / 'pit'
_FIN_OLE = 0xFFFFFFFA


def _flujos_ole(datos):
    """Los flujos de un fichero OLE (CFB) pequeño, sin olefile (no está en el .venv): FAT, directorio y mini flujo."""
    assert datos[:8] == bytes.fromhex('d0cf11e0a1b11ae1'), 'no es un fichero OLE'
    sec = 1 << struct.unpack_from('<H', datos, 0x1E)[0]
    mini = 1 << struct.unpack_from('<H', datos, 0x20)[0]
    dir0, corte, minifat0 = (struct.unpack_from('<I', datos, o)[0] for o in (0x30, 0x38, 0x3C))
    difat = [s for s in struct.unpack_from('<109I', datos, 0x4C) if s < _FIN_OLE]

    def sector(s):
        return datos[(s + 1) * sec:(s + 2) * sec]

    fat = [x for s in difat for x in struct.unpack(f'<{sec // 4}I', sector(s))]

    def cadena(s, tabla):
        out = []
        while s < _FIN_OLE and len(out) <= len(tabla):
            out.append(s)
            s = tabla[s]
        return out

    directorio = b''.join(sector(s) for s in cadena(dir0, fat))
    entradas = []
    for i in range(0, len(directorio), 128):
        e = directorio[i:i + 128]
        largo = struct.unpack_from('<H', e, 64)[0]
        entradas.append((e[:max(largo - 2, 0)].decode('utf-16-le'), e[66],
                         struct.unpack_from('<I', e, 116)[0], struct.unpack_from('<I', e, 120)[0]))
    flujo_mini = b''.join(sector(s) for s in cadena(entradas[0][2], fat))
    minifat = ([x for s in cadena(minifat0, fat) for x in struct.unpack(f'<{sec // 4}I', sector(s))]
               if minifat0 < _FIN_OLE else [])
    flujos = {}
    for nombre, tipo, inicio, tam in entradas[1:]:
        if tipo != 2:
            continue
        if tam < corte:
            datos_flujo = b''.join(flujo_mini[s * mini:(s + 1) * mini] for s in cadena(inicio, minifat))
        else:
            datos_flujo = b''.join(sector(s) for s in cadena(inicio, fat))
        flujos[nombre] = datos_flujo[:tam]
    return flujos


def _propiedades_ole(flujo):
    """Las cadenas de la primera sección de un conjunto de propiedades OLE (MS-OLEPS), por su identificador."""
    inicio = struct.unpack_from('<I', flujo, 44)[0]
    n = struct.unpack_from('<I', flujo, inicio + 4)[0]
    pares = [struct.unpack_from('<II', flujo, inicio + 8 + 8 * i) for i in range(n)]
    pagina = next((struct.unpack_from('<h', flujo, inicio + o + 4)[0] for pid, o in pares if pid == 1), 1252)
    out = {}
    for pid, o in pares:
        tipo, cuenta = struct.unpack_from('<II', flujo, inicio + o)
        crudo = flujo[inicio + o + 8:inicio + o + 8 + cuenta * 2]
        if tipo == 0x1F or (tipo == 0x1E and pagina == 1200):
            out[pid] = crudo.decode('utf-16-le', 'replace').split('\x00')[0]
        elif tipo == 0x1E:
            out[pid] = crudo[:cuenta].decode('latin-1').split('\x00')[0]
    return out


def _metadatos(ruta):
    """Autor, último que guardó y empresa: docProps del zip (.xlsx, .xlsb) o SummaryInformation del OLE (.xls)."""
    if ruta.suffix == '.xls':
        flujos = _flujos_ole(ruta.read_bytes())
        resumen = _propiedades_ole(flujos['\x05SummaryInformation'])
        doc = flujos.get('\x05DocumentSummaryInformation')
        empresa = _propiedades_ole(doc).get(15, '') if doc else ''
        return {'autor': resumen.get(4, ''), 'ultimo': resumen.get(8, ''), 'empresa': empresa}
    ns = {'dc': 'http://purl.org/dc/elements/1.1/',
          'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
          'ep': 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'}
    with zipfile.ZipFile(ruta) as z:
        core = ET.fromstring(z.read('docProps/core.xml'))
        app = ET.fromstring(z.read('docProps/app.xml')) if 'docProps/app.xml' in z.namelist() else None
    return {'autor': core.findtext('dc:creator', '', ns), 'ultimo': core.findtext('cp:lastModifiedBy', '', ns),
            'empresa': app.findtext('ep:Company', '', ns) if app is not None else ''}


@pytest.mark.parametrize('ext', ['.xlsx', '.xls', '.xlsb'])
def test_muestras_sin_metadatos_personales(ext):
    """107:RF-12 — las muestras que van al repositorio no llevan quién las hizo: el autor, el último que guardó y la
    empresa están vacíos, y ni el usuario ni el equipo que corre la prueba ni «openpyxl» aparecen en ninguna parte."""
    ruta = MUESTRAS / f'red_pit_sintetica{ext}'
    meta = _metadatos(ruta)
    assert set(meta) == {'autor', 'ultimo', 'empresa'}
    con_nombre = sorted(k for k, v in meta.items() if v.strip())
    assert not con_nombre, f'{ruta.name}: metadatos con nombre: {con_nombre}'
    if ext == '.xls':
        contenido = ruta.read_bytes()
    else:
        with zipfile.ZipFile(ruta) as z:
            contenido = b'\n'.join(z.read(n) for n in z.namelist())
    contenido = contenido.lower()
    nombres = {p for n in (getpass.getuser(), socket.gethostname(), 'openpyxl') for p in [n, *n.split()] if len(p) >= 4}
    for p in nombres:
        for cod in ('utf-8', 'utf-16-le'):
            assert p.lower().encode(cod) not in contenido, f'{ruta.name} lleva un nombre del equipo o del autor'


@pytest.mark.parametrize('ext', ['.xls', '.xlsb'])
def test_xls_y_xlsb_reales_por_el_lector_comun(ext, tmp_path):
    """107:RF-12 — un .xls y un .xlsb reales los abre el lector común (calamine) y dan lo mismo que el .xlsx de origen y
    que el libro escrito en el momento; sin ``columnas`` en el perfil, los encabezados son las claves del contrato, y
    la hoja sin contrato queda en los avisos."""
    from convertersmartgrid.libros_por_anio import EXTENSIONES

    assert {'.xls', '.xlsb', '.xlsx', '.xlsm'} <= set(EXTENSIONES)
    ruta = MUESTRAS / f'red_pit_sintetica{ext}'
    leidos = leer_libro_red(ruta, {})
    origen = leer_libro_red(MUESTRAS / 'red_pit_sintetica.xlsx', {})
    base = leer_libro_red(*_libro(tmp_path, perfil_a(13)['elementos']))
    assert _sin_fuente(leidos) == _sin_fuente(origen) == _sin_fuente(base) and len(leidos) == len(base) > 0
    assert leidos.hojas == ['Inventario'] and any('Notas' in a for a in leidos.avisos)
    assert {e['fuente']['hoja'] for e in leidos} == {'Inventario'} and min(e['fuente']['fila'] for e in leidos) == 3
    assert {(e['fuente']['libro'], e['fuente']['sha256']) for e in leidos} == {
        (ruta.name, hashlib.sha256(ruta.read_bytes()).hexdigest())}


def test_formato_que_no_es_un_libro(tmp_path):
    """107:RF-12 — un fichero que no es un libro de Excel es un error que nombra el fichero, no una red vacía."""
    ruta = tmp_path / 'red.csv'
    ruta.write_text('id;tipo\n', encoding='utf-8')
    with pytest.raises(PitError, match='red.csv'):
        leer_libro_red(ruta, {})


@pytest.mark.parametrize('seed', SEMILLAS)
def test_sin_hoja_declarada_se_leen_todas(seed, tmp_path):
    """107:RF-12 — sin hoja declarada se recorren todas: cada elemento dice su hoja y su fila, la cabecera se halla por
    contenido aunque no esté en la primera fila, y la hoja sin el contrato queda nombrada en los avisos."""
    caso = perfil_b(seed)
    hojas, columnas, lineas, resto = _repartido(caso)
    ruta = _libro_hojas(tmp_path, hojas)
    leidos = leer_libro_red(ruta, {'columnas': columnas})
    assert _sin_fuente(leidos) == _sin_fuente(leer_libro_red(*_libro(tmp_path, caso['elementos'])))
    hoja_de = {e['id']: e['fuente']['hoja'] for e in leidos}
    assert {hoja_de[e['id']] for e in lineas} == {'Líneas'}
    assert {hoja_de[e['id']] for e in resto} == {'Barras y trafos'}
    assert min(e['fuente']['fila'] for e in leidos if e['fuente']['hoja'] == 'Líneas') == 4
    assert leidos.hojas == ['Líneas', 'Barras y trafos']
    assert any('Notas' in a for a in leidos.avisos)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, leidos))
    assert caso['pistas']['sin_parametros'] in {f['id'] for f in red.faltantes}


def test_hoja_declarada_se_respeta(tmp_path):
    """107:RF-12 — si el perfil declara una hoja, solo se lee esa, aunque otras traigan el contrato."""
    caso = perfil_a(21)
    hojas, columnas, lineas, _ = _repartido(caso)
    ruta = _libro_hojas(tmp_path, hojas)
    leidos = leer_libro_red(ruta, {'hoja': 'Líneas', 'columnas': columnas})
    assert sorted(e['id'] for e in leidos) == sorted(e['id'] for e in lineas)
    assert leidos.hojas == ['Líneas'] and not leidos.avisos
    with pytest.raises(PitError, match='Otra hoja'):
        leer_libro_red(ruta, {'hoja': 'Otra hoja', 'columnas': columnas})


def test_varias_hojas_declaradas(tmp_path):
    """107:RF-12 — con varias hojas declaradas se recorren esas: la que no trae el contrato va a los avisos."""
    caso = perfil_a(34)
    hojas, columnas, _, resto = _repartido(caso)
    ruta = _libro_hojas(tmp_path, hojas)
    leidos = leer_libro_red(ruta, {'hoja': ['Barras y trafos', 'Notas'], 'columnas': columnas})
    assert sorted(e['id'] for e in leidos) == sorted(e['id'] for e in resto) and leidos.hojas == ['Barras y trafos']
    assert [a for a in leidos.avisos if 'Notas' in a]


def test_elemento_repetido_en_dos_hojas(tmp_path):
    """107:RF-12 — un mismo elemento en dos hojas se toma una vez, la primera, y se avisa con las dos hojas."""
    caso = perfil_a(3)
    hojas, columnas, lineas, _ = _repartido(caso)
    hojas['Copia'] = hojas['Líneas'][2:4]
    ruta = _libro_hojas(tmp_path, hojas)
    leidos = leer_libro_red(ruta, {'columnas': columnas})
    assert [e['id'] for e in leidos].count(lineas[0]['id']) == 1
    assert any(lineas[0]['id'] in a and 'Copia' in a for a in leidos.avisos)


def test_ninguna_hoja_con_el_contrato(tmp_path):
    """107:RF-12 — si ninguna hoja trae las columnas del contrato, el error nombra cada hoja y lo que trae."""
    ruta = _libro_hojas(tmp_path, {'Resumen': [['Total', 'MW']], 'Notas': [['Revisado por', 'planificación']]})
    with pytest.raises(PitError) as exc:
        leer_libro_red(ruta, {})
    texto = str(exc.value)
    assert 'Resumen' in texto and 'Notas' in texto and 'MW' in texto and 'planificación' in texto
