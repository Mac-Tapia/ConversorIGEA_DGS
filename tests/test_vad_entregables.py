"""Spec 108 T9 y T10 — los entregables del estudio VAD: Formatos A y B en Excel con sus fórmulas, mapas de densidad
del anexo 9 y manifiesto de fuentes con sus huellas (108:RF-11, 108:RF-9, 108:RF-13).

Datos sintéticos sorteados con semilla y dos empresas con CRS distintos; el anexo 2 y el anexo 9 son los
transcritos en ``config/vad`` (normas públicas del regulador). Ningún nombre, código ni coordenada de una empresa.

v3 (2026-11-16): cada caso comprueba primero, con una aserción y su mensaje, lo que va a leer (el libro escrito, sus
hojas y su traza, la estructura del anexo 9, los mapas y el manifiesto escritos) antes de abrirlo o recorrerlo; así un
módulo que no hace su trabajo cae por esa aserción y no por la excepción de leer algo que no está.
"""
from __future__ import annotations

import copy
import json
import random
import string
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.adaptadores.vad import entregables
from convertersmartgrid.aplicacion.vad.anexo2 import cargar_formatos

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / 'config' / 'vad'
FORMATOS = CONFIG / 'anexo2_formatos.json'
SEMILLAS = (5, 17)
#: Dos empresas sintéticas: CRS de origen distintos (del perfil) y el mismo CRS de los mapas.
EMPRESAS = (('EPSG:32719', (300_000.0, 8_500_000.0)), ('EPSG:3857', (-8_500_000.0, -1_500_000.0)))


def _ent():
    return entregables


def _escrito(libro, ruta) -> None:
    """Guarda: el libro de los Formatos está escrito donde se pidió, antes de reabrirlo."""
    assert Path(libro.ruta) == Path(ruta) and Path(libro.ruta).is_file(), \
        f'el libro de los Formatos no se escribió en {ruta}'


def _hojas(libro, *hojas: str) -> None:
    """Guarda: el libro dice las celdas calculadas de cada hoja que la prueba va a leer."""
    sin = [h for h in hojas if not libro.calculadas.get(h)]
    assert not sin, f'el libro no tiene celdas calculadas en {sin}: {sorted(libro.calculadas)}'


def _en_traza(libro, *claves: tuple[str, str, str]) -> dict:
    """Guarda: la traza del libro registra cada (hoja, fila, columna) que la prueba va a leer; devuelve la traza."""
    traza = {(e['hoja'], e['fila'], e['columna']): e for e in libro.traza}
    sin = [c for c in claves if c not in traza]
    assert not sin, f'la traza del libro no registra {sin} ({len(traza)} entradas)'
    return traza


def _anexo9(ent, registro):
    """Guarda: el registro da la estructura del anexo 9 con sus entidades y su regla citada."""
    entidades, rv = ent.estructura_anexo9(registro)
    assert entidades and rv is not None, 'la estructura del anexo 9 (vad.anexo9.entidades) no da entidades ni regla'
    assert any(e.get('entidad') == 'Suministro' and e.get('campos') for e in entidades), \
        f'el anexo 9 no da la entidad Suministro con sus campos: {[e.get("entidad") for e in entidades]}'
    return entidades, rv


def _fuente():
    return json.loads(FORMATOS.read_text(encoding='utf-8'))['fuente']


def _tablas(formatos, semilla):
    """Todas las tablas transcritas con valores sorteados (también en los totales: el escritor los sustituye por su
    fórmula) y un texto en las columnas de texto."""
    rnd = random.Random(semilla)

    def filas(formato):
        return {f.id: {c.id: (f'doc-{rnd.randint(1, 99)}' if c.unidad == 'texto' else round(rnd.uniform(1, 1e4), 3))
                       for c in formato.columnas if c.id not in f.no_aplica}
                for f in formato.filas if f.tipo != 'grupo'}

    out = {}
    for f in formatos.transcritos():
        if f.forma == 'larga':
            out[f.id] = {'bloques': [{'claves': {k: (m if k == 'Mes' else f'{k[:1]}1') for k in f.claves_de_fila},
                                      'filas': filas(f)} for m in range(1, 3)]}
        else:
            out[f.id] = {'filas': filas(f)}
    return out


# ======================================================================================== T9: Formatos A y B
@pytest.mark.parametrize('prefijo', ('A', 'B'))
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_108_rf11_formatos_a_y_b_con_formulas_vivas_y_sin_errores(tmp_path, prefijo, semilla):
    """108:RF-11, 108:RF-9 — una hoja por formato con el prefijo A (empresa) o B (empresa modelo); cada celda
    calculada es una fórmula de Excel traducida de la transcrita, el libro reabierto con openpyxl no tiene ninguna
    celda calculada sin fórmula ni ningún error de ERRORES_DE_FORMULA, y la fórmula de cada fila del A-VI da lo mismo
    que el balance (vad.balance.calcular_filas) con los mismos datos."""
    ent = _ent()
    from openpyxl import load_workbook

    from convertersmartgrid.aplicacion.vad.balance import calcular_filas
    formatos = cargar_formatos(FORMATOS)
    tablas = _tablas(formatos, semilla)
    fuentes = {f.id: 'libro contable sintético' for f in formatos.todos()}
    libro = ent.escribir_formatos(formatos, tablas, tmp_path / f'formatos_{prefijo}.xlsx', prefijo=prefijo,
                                  fuentes=fuentes, cita=_fuente())
    _escrito(libro, tmp_path / f'formatos_{prefijo}.xlsx')
    assert set(libro.hojas.values()) == {f'{prefijo}-{f.id.split("-", 1)[1]}' for f in formatos.todos()}
    assert ent.comprobar_formatos(libro.ruta, libro) == []
    assert sum(len(c) for c in libro.calculadas.values()) > 50
    _hojas(libro, f'{prefijo}-VI')
    wb = load_workbook(libro.ruta)
    vi = f'{prefijo}-VI'
    hoja = wb[vi]
    assert str(hoja['A2'].value).startswith('Fuente: tdr-vad-2026-anexo-r033, Anexo N° 2')
    assert hoja['A3'].value == 'Datos: libro contable sintético'
    for celda in libro.calculadas[vi]:
        assert str(hoja[celda].value).startswith('='), celda
    formato_vi = formatos.formato('A-VI')
    col = next(c.column_letter for c in hoja[5] if c.value == formato_vi.columnas[0].nombre)
    fila16 = next(c.row for c in hoja['A'] if c.value == '(16)')
    fila11 = next(c.row for c in hoja['A'] if c.value == '(11)')
    assert f'{col}{fila11}' in hoja[f'{col}{fila16}'].value
    entrada = {k: v[formato_vi.columnas[0].id] for k, v in tablas['A-VI']['filas'].items()
               if not next(c for c in formato_vi.filas if c.id == k).formula}
    esperado, huecos = calcular_filas(entrada, formato_vi)
    assert not huecos
    for fila_id in ('(16)', '(27)', '(47)', '(48)'):
        n = next(c.row for c in hoja['A'] if c.value == fila_id)
        assert ent.valor_calculado(hoja, f'{col}{n}') == pytest.approx(esperado[fila_id], rel=1e-12), fila_id
    v1 = wb[f'{prefijo}-V-1']
    formato_v1 = formatos.formato('A-V-1')
    letra = {c.nombre[:3]: next(x.column_letter for x in v1[5] if x.value == c.nombre) for c in formato_v1.columnas}
    ids = {c.nombre[:3]: c.id for c in formato_v1.columnas}
    fila = next(f.id for f in formato_v1.filas
                if f.tipo == 'dato' and not {ids['(e)'], ids['(f)'], ids['(g)']} & set(f.no_aplica))
    n = next(c.row for c in v1['A'] if c.value == fila)
    assert v1[f'{letra["(g)"]}{n}'].value == f'={letra["(e)"]}{n}+{letra["(f)"]}{n}'
    # Donde «(b)» y «(c)» no aplican, «(d) = (b)+(c)» suma dos términos que no existen: 0, con su fórmula.
    sin = next(f.id for f in formato_v1.filas if f.tipo == 'dato' and {ids['(b)'], ids['(c)']} <= set(f.no_aplica)
               and ids['(d)'] not in f.no_aplica)
    fila_sin = next(c.row for c in v1["A"] if c.value == sin)
    assert v1[f'{letra["(d)"]}{fila_sin}'].value == '=0+0'
    assert v1[f'{letra["(b)"]}{fila_sin}'].value == 'no aplica'
    assert not any(f', fila {sin}, columna {ids["(d)"]}' in h for h in libro.huecos)


def test_108_rf11_no_aplica_y_hueco_son_dos_estados_distintos(tmp_path):
    """108:RF-11 — «no aplica» lo dice el formato oficial (celda sombreada, citada con su página y sus líneas): la
    celda lo lleva escrito y en la suma es un término nulo. Un dato que falta es un hueco nombrado: la celda queda
    vacía y la fórmula que lo usa NO se escribe. La traza del libro (hoja «Traza») distingue los dos."""
    ent = _ent()
    from openpyxl import load_workbook
    formatos = cargar_formatos(FORMATOS)
    v1 = formatos.formato('A-V-1')
    ids = {c.nombre[:3]: c.id for c in v1.columnas}
    con_na = next(f for f in v1.filas if f.tipo == 'dato' and {ids['(b)'], ids['(c)']} <= set(f.no_aplica)
                  and ids['(d)'] not in f.no_aplica)
    aplica = next(f for f in v1.filas if f.tipo == 'dato' and not {ids['(e)'], ids['(f)'], ids['(g)']} & set(f.no_aplica))
    tablas = _tablas(formatos, SEMILLAS[0])
    del tablas['A-V-1']['filas'][aplica.id][ids['(e)']]
    libro = ent.escribir_formatos(formatos, tablas, tmp_path / 'f.xlsx', cita=_fuente())
    _escrito(libro, tmp_path / 'f.xlsx')
    traza = _en_traza(libro, ('A-V-1', con_na.id, ids['(b)']), ('A-V-1', aplica.id, ids['(e)']),
                      ('A-V-1', aplica.id, ids['(g)']))
    na = traza[('A-V-1', con_na.id, ids['(b)'])]
    assert na['estado'] == 'no_aplica' and 'sombreada' in na['motivo'] and v1.pagina in na['motivo'] \
        and v1.lineas in na['motivo']
    hueco = traza[('A-V-1', aplica.id, ids['(e)'])]
    assert hueco['estado'] == 'hueco' and 'sin valor' in hueco['motivo']
    g = traza[('A-V-1', aplica.id, ids['(g)'])]
    assert g['estado'] == 'hueco' and 'le faltan' in g['motivo']
    assert ('A-V-1', con_na.id, ids['(d)']) not in traza or traza[('A-V-1', con_na.id, ids['(d)'])]['estado'] != 'hueco'
    wb = load_workbook(libro.ruta)
    hoja = wb['A-V-1']
    assert hoja[hueco['celda']].value is None and hoja[g['celda']].value is None
    assert hoja[na['celda']].value == 'no aplica'
    filas = list(wb['Traza'].iter_rows(min_row=2, values_only=True))
    assert ('A-V-1', na['celda'], con_na.id, ids['(b)'], 'no_aplica') in {r[:5] for r in filas}
    assert ('A-V-1', hueco['celda'], aplica.id, ids['(e)'], 'hueco') in {r[:5] for r in filas}


def test_108_rf11_el_dato_de_una_celda_calculada_queda_en_la_traza_con_su_formula(tmp_path):
    """108:RF-11, 108:RF-9 — un dato traído en una celda calculada se sustituye por su fórmula, y la traza del
    entregable (hoja «Traza» del libro) dice la celda, el valor original y la fórmula que la sustituye."""
    ent = _ent()
    from openpyxl import load_workbook
    formatos = cargar_formatos(FORMATOS)
    tablas = _tablas(formatos, SEMILLAS[1])
    declarado = tablas['A-VI']['filas']['(16)'][formatos.formato('A-VI').columnas[0].id]
    libro = ent.escribir_formatos(formatos, tablas, tmp_path / 'f.xlsx', cita=_fuente())
    _escrito(libro, tmp_path / 'f.xlsx')
    clave = ('A-VI', '(16)', formatos.formato('A-VI').columnas[0].id)
    e = _en_traza(libro, clave)[clave]
    assert e['estado'] == 'sustituido' and e['valor_original'] == declarado and e['formula'].startswith('=')
    wb = load_workbook(libro.ruta)
    assert wb['A-VI'][e['celda']].value == e['formula']
    filas = [r for r in wb['Traza'].iter_rows(min_row=2, values_only=True) if r[0] == 'A-VI' and r[1] == e['celda']]
    assert filas, f'la hoja «Traza» no tiene la celda {e["celda"]} del A-VI'
    fila = filas[0]
    assert fila[4] == 'sustituido' and fila[5] == declarado and fila[6] == e['formula']
    assert any(e['celda'] in a and repr(declarado) in a and e['formula'] in a for a in libro.avisos)


def test_108_rf11_total_sin_formula_transcrita_es_un_hueco_y_no_un_valor(tmp_path):
    """108:RF-11 — un total que el anexo 2 no da con su fórmula (A-V-1 «TOTAL MERCADO LIBRE») y una fórmula transcrita
    que no se traduce sin suponer (A-I-1 «suma de los componentes») dejan la celda vacía con su hueco: el valor
    declarado no se escribe donde va una fórmula."""
    ent = _ent()
    from openpyxl import load_workbook
    formatos = cargar_formatos(FORMATOS)
    tablas = _tablas(formatos, SEMILLAS[0])
    libro = ent.escribir_formatos(formatos, tablas, tmp_path / 'f.xlsx', fuentes={}, cita=_fuente())
    _escrito(libro, tmp_path / 'f.xlsx')
    assert any('TOTAL MERCADO LIBRE' in h and 'sin fórmula transcrita' in h for h in libro.huecos)
    assert any('fila total' in h and 'suma de los componentes' in h for h in libro.huecos)
    assert any('se sustituye por la fórmula' in a for a in libro.avisos)
    wb = load_workbook(libro.ruta)
    hoja = wb['A-V-1']
    filas = [c.row for c in hoja['A'] if c.value == 'TOTAL MERCADO LIBRE']
    assert filas, 'el A-V-1 no tiene la fila «TOTAL MERCADO LIBRE» del formato oficial'
    n = filas[0]
    # Sin valor ni fórmula: vacía, o «no aplica» donde el formato oficial la sombrea.
    assert all(hoja.cell(n, j).value in (None, 'no aplica')
               for j in range(4, 4 + len(formatos.formato('A-V-1').columnas)))
    assert any(hoja.cell(n, j).value is None for j in range(4, 4 + len(formatos.formato('A-V-1').columnas)))
    assert any('no dicen de qué documento salen' in h for h in libro.huecos)


def test_108_rf11_una_formula_que_apunta_a_una_celda_vacia_no_se_escribe(tmp_path):
    """108:RF-11 — sin la fila (12) del A-VI, la (16) que la suma no se escribe y su hueco nombra lo que le falta."""
    ent = _ent()
    formatos = cargar_formatos(FORMATOS)
    tablas = _tablas(formatos, SEMILLAS[1])
    del tablas['A-VI']['filas']['(12)']
    libro = ent.escribir_formatos(formatos, tablas, tmp_path / 'f.xlsx', cita=_fuente())
    _escrito(libro, tmp_path / 'f.xlsx')
    assert any('A-VI, fila (16)' in h and '(12)' in h and 'le faltan' in h for h in libro.huecos)
    assert any('A-VI, fila (12)' in h and 'sin valor' in h for h in libro.huecos)
    assert ent.comprobar_formatos(libro.ruta, libro) == []


def test_108_rf11_comprobar_nombra_la_celda_sin_formula_y_cada_error(tmp_path):
    """108:RF-11 — si en el libro una celda calculada pierde su fórmula, una fórmula divide entre cero o apunta a una
    celda vacía, o una celda guarda «#REF!», la comprobación lo nombra con su hoja y su celda."""
    ent = _ent()
    from openpyxl import load_workbook
    formatos = cargar_formatos(FORMATOS)
    libro = ent.escribir_formatos(formatos, _tablas(formatos, SEMILLAS[0]), tmp_path / 'f.xlsx', cita=_fuente())
    _escrito(libro, tmp_path / 'f.xlsx')
    _hojas(libro, 'A-VI')
    calc = libro.calculadas['A-VI']
    assert len(calc) >= 3, f'el A-VI tiene {len(calc)} celdas calculadas y la prueba altera tres'
    wb = load_workbook(libro.ruta)
    hoja = wb['A-VI']
    hoja[calc[0]] = 123.0
    hoja[calc[1]] = '=1/(D1-D1)'
    hoja[calc[2]] = '=ZZ999+1'
    hoja['B3'] = '#REF!'
    wb.save(libro.ruta)
    problemas = ent.comprobar_formatos(libro.ruta, libro)
    assert any(p.startswith(f'A-VI!{calc[0]}: celda calculada sin fórmula') for p in problemas), problemas
    assert any(p.startswith(f'A-VI!{calc[1]}') and '#' in p for p in problemas), problemas
    assert any(p.startswith(f'A-VI!{calc[2]}') and '#REF!' in p for p in problemas), problemas
    assert 'A-VI!B3: #REF!' in problemas
    with pytest.raises(VadError, match='prefijo'):
        ent.escribir_formatos(formatos, {}, tmp_path / 'g.xlsx', prefijo='C')
    with pytest.raises(VadError, match='X-9'):
        ent.escribir_formatos(formatos, {'X-9': {}}, tmp_path / 'g.xlsx')


# ======================================================================================== T10: anexo 9
def _valor(campo, rnd):
    if campo['tipo'] == 'caracter':
        return ''.join(rnd.choice(string.ascii_uppercase + string.digits) for _ in range(rnd.randint(1, campo['ancho'])))
    dec = int(campo['decimales'] or 0)
    enteros = int(campo['ancho']) - (dec + 1 if dec else 0)
    if enteros <= 0:  # N(5,4): solo .xxxx
        return round(rnd.uniform(0, 0.9999), dec)
    tope = 10 ** min(enteros, 6) - 1
    return round(rnd.uniform(0, tope), dec) if dec else rnd.randint(0, tope)


def _suministros(entidades, rnd, origen, n=7):
    sum_ = next(e for e in entidades if e['entidad'] == 'Suministro')
    x0, y0 = origen
    return [{'propiedades': {c['nombre']: _valor(c, rnd) for c in reversed(sum_['campos'])},
             'geometria': {'type': 'Point', 'coordinates': [x0 + rnd.uniform(0, 5e3), y0 + rnd.uniform(0, 5e3)]}}
            for _ in range(n)]


def test_108_rf11_el_anexo9_esta_transcrito_con_su_cita_y_sus_campos_en_orden():
    """108:RF-11, 108:RF-9 — el registro trae las entidades del anexo 9 con sus campos en el orden del anexo (nombre,
    tipo, ancho, decimales y línea del texto) y las tablas de códigos, con su cita; el código repetido de TARIFAS se
    nombra, no se corrige."""
    ent = _ent()
    registro = cargar_registro(CONFIG)
    entidades, rv = _anexo9(ent, registro)
    assert rv.norma.acto == 'tdr-vad-2026-anexo-r033' and rv.regla.citada and rv.obligatoria
    assert [e['entidad'] for e in entidades] == ['Suministro', 'Cuadricula_BT', 'Cuadricula_MT_BT',
                                                 'Zona Histórica o Monumental', 'Manzana', 'Vía', 'Parque',
                                                 'ZonaConvenio']
    sum_ = entidades[0]
    assert sum_['geometria'] == 'punto'
    assert [c['nombre'] for c in sum_['campos']][:4] == ['Cod', 'CodSis', 'sector', 'UTM_X']
    assert any(c['nombre'] == 'Fc' for c in sum_['campos']), 'el Suministro del anexo 9 no tiene el campo Fc'
    assert next(c for c in sum_['campos'] if c['nombre'] == 'Fc') | {'linea': 0} == {
        'nombre': 'Fc', 'tipo': 'numerico', 'ancho': 5, 'decimales': 4, 'descripcion': 'Factor de carga',
        'en_guia_vnr': False, 'linea': 0}
    ini, fin = (int(x) for x in rv.regla.lineas.split('-'))
    assert all(ini <= c['linea'] <= fin for e in entidades for c in e['campos'])
    assert 'vad.anexo9.tablas' in {r.clave for n in registro.normas.values() for r in n.reglas}, \
        'el registro no trae las tablas de códigos del anexo 9 (vad.anexo9.tablas)'
    tablas = {t['tabla']: t for t in registro.regla('vad.anexo9.tablas').regla.valor}
    assert {'TARIFAS', 'SENTIDO DE TRAMO DE VÍA'} <= set(tablas), sorted(tablas)
    assert tablas['TARIFAS']['codigos_repetidos'] == ['BT5C']
    assert [c['codigo'] for c in tablas['SENTIDO DE TRAMO DE VÍA']['codigos']] == ['D', 'M', 'C']


@pytest.mark.parametrize('crs_origen, origen', EMPRESAS, ids=('utm', 'mercator'))
def test_108_rf11_mapas_con_los_campos_del_anexo9_en_orden_y_reproyectados_sobre_una_copia(tmp_path, crs_origen,
                                                                                            origen):
    """108:RF-11 — cada entidad va en <Entidad>.geojson con sus campos en el orden del anexo 9 (aunque la entrada
    venga en otro orden) y las coordenadas reproyectadas con geography.make_transformer; la entrada no cambia."""
    ent = _ent()
    from convertersmartgrid.adaptadores.geography import make_transformer
    registro = cargar_registro(CONFIG)
    entidades, _ = _anexo9(ent, registro)
    rnd = random.Random(f'{crs_origen}-{SEMILLAS[0]}')
    capas = {'Suministro': _suministros(entidades, rnd, origen)}
    antes = copy.deepcopy(capas)
    mapas = ent.escribir_mapas(registro, capas, tmp_path / 'mapas', crs_origen=crs_origen, crs_destino='EPSG:4326')
    assert capas == antes, 'la entrada no se toca: se reproyecta una copia'
    assert set(mapas.ficheros) == {'Suministro'}
    assert mapas.ficheros['Suministro'] == tmp_path / 'mapas' / 'Suministro.geojson'
    assert mapas.ficheros['Suministro'].is_file(), 'el mapa del Suministro no se escribió'
    assert all(h.endswith('sin registros; el mapa no se escribe') for h in mapas.huecos)
    assert len(mapas.huecos) == len(entidades) - 1
    datos = json.loads(mapas.ficheros['Suministro'].read_text(encoding='utf-8'))
    assert len(datos.get('features') or ()) == len(antes['Suministro']), 'el mapa no tiene un rasgo por registro'
    orden = [c['nombre'] for c in entidades[0]['campos']]
    t = make_transformer(crs_origen, 'EPSG:4326')
    for rasgo, reg in zip(datos['features'], antes['Suministro']):
        assert list(rasgo['properties']) == orden
        x, y = t.transform(*reg['geometria']['coordinates'])
        assert rasgo['geometry']['coordinates'] == pytest.approx([x, y])
        assert rasgo['geometry']['coordinates'] != reg['geometria']['coordinates']
    assert datos['crs_csg'] == 'EPSG:4326'


def test_108_rf11_un_campo_que_no_cumple_el_anexo9_es_un_hueco_y_no_se_corrige(tmp_path):
    """108:RF-11, 108:RF-13 — un texto más largo que su ancho, un número con más decimales, un campo que falta y un
    campo adicional sin diccionario de datos se nombran y no se escriben; con su diccionario, el adicional se escribe.
    Una entidad que el anexo no tiene, otra geometría o un CRS de origen sin declarar son un error."""
    ent = _ent()
    registro = cargar_registro(CONFIG)
    entidades, _ = _anexo9(ent, registro)
    rnd = random.Random(SEMILLAS[1])
    regs = _suministros(entidades, rnd, EMPRESAS[0][1], n=2)
    regs[0]['propiedades']['Cod'] = 'X' * 13
    regs[0]['propiedades']['Fc'] = 0.123456
    del regs[0]['propiedades']['Grupo']
    regs[1]['propiedades']['extra_sintetico'] = 1
    mapas = ent.escribir_mapas(registro, {'Suministro': regs}, tmp_path / 'm', crs_origen='EPSG:32719')
    texto = '\n'.join(mapas.huecos)
    assert 'Suministro, registro 1, campo Cod: 13 caracteres y el anexo 9 da un ancho de 12' in texto
    assert 'Suministro, registro 1, campo Fc: 0.123456 tiene más de 4 decimales' in texto
    assert 'Suministro, registro 1, campo Grupo: sin valor' in texto
    assert "campo adicional 'extra_sintetico' no está en el diccionario" in texto
    assert 'Suministro' in mapas.ficheros and mapas.ficheros['Suministro'].is_file(), \
        'el mapa del Suministro no se escribió'
    datos = json.loads(mapas.ficheros['Suministro'].read_text(encoding='utf-8'))
    assert len(datos.get('features') or ()) == 2, 'el mapa no tiene un rasgo por registro'
    assert datos['features'][0]['properties']['Cod'] is None and 'extra_sintetico' not in datos['features'][1]['properties']
    con = ent.escribir_mapas(registro, {'Suministro': regs}, tmp_path / 'm2', crs_origen='EPSG:32719',
                             diccionario={'extra_sintetico': 'campo de prueba'})
    assert 'Suministro' in con.ficheros, 'con el diccionario, el mapa del Suministro no se escribió'
    assert json.loads(con.ficheros['Suministro'].read_text(encoding='utf-8'))['features'][1]['properties'][
        'extra_sintetico'] == 1
    with pytest.raises(VadError, match='Entidad Inventada'):
        ent.escribir_mapas(registro, {'Entidad Inventada': regs}, tmp_path / 'x', crs_origen='EPSG:32719')
    malo = copy.deepcopy(regs[:1])
    malo[0]['geometria'] = {'type': 'LineString', 'coordinates': [[0, 0], [1, 1]]}
    with pytest.raises(VadError, match='punto'):
        ent.escribir_mapas(registro, {'Suministro': malo}, tmp_path / 'x', crs_origen='EPSG:32719')
    with pytest.raises(VadError, match='CRS de origen'):
        ent.escribir_mapas(registro, {'Suministro': regs}, tmp_path / 'x', crs_origen='')


def test_108_rf11_manifiesto_de_fuentes_con_huellas_recalculadas_e_iguales(tmp_path):
    """108:RF-11, 108:RF-9 — el manifiesto lleva por cada entrada su SHA-256, su versión y la regla del registro con su
    acto y su huella; recalculadas, las huellas son iguales, y un fichero cambiado se nombra. Una fuente sin versión
    o sin regla registrada no entra."""
    ent = _ent()
    import hashlib
    registro = cargar_registro(CONFIG)
    rnd = random.Random(SEMILLAS[0])
    a, b = tmp_path / 'inventario.bin', tmp_path / 'medidas.bin'
    a.write_bytes(rnd.randbytes(4096))
    b.write_bytes(rnd.randbytes(1000))
    entradas = {'inventario': {'ruta': str(a), 'version': 'v1', 'regla': 'vad.anexo9.entidades'},
                'medidas': {'ruta': str(b), 'version': '2', 'regla': 'vad.anexo9.tablas'}}
    destino = tmp_path / 'manifiesto_fuentes.json'
    datos = ent.manifiesto_fuentes(entradas, registro, destino)
    assert destino.is_file(), f'el manifiesto de fuentes no se escribió en {destino}'
    leido = json.loads(destino.read_text(encoding='utf-8'))
    assert leido == datos
    por = {f.get('nombre'): f for f in leido.get('fuentes') or ()}
    assert set(por) == {'inventario', 'medidas'}, f'el manifiesto no lleva una fuente por entrada: {sorted(por)}'
    assert por['inventario']['sha256'] == hashlib.sha256(a.read_bytes()).hexdigest()
    assert por['medidas']['registro']['clave'] == 'vad.anexo9.tablas'
    assert por['medidas']['registro']['huella'] == registro.regla('vad.anexo9.tablas').huella()
    assert ent.comprobar_manifiesto(destino) == []
    b.write_bytes(b'otra cosa')
    assert ent.comprobar_manifiesto(destino) == ['medidas: la huella cambió desde el manifiesto']
    with pytest.raises(VadError, match='versión'):
        ent.manifiesto_fuentes({'x': {'ruta': str(a), 'version': ''}}, registro, tmp_path / 'm.json')
    with pytest.raises(VadError, match='registro normativo'):
        ent.manifiesto_fuentes({'x': {'ruta': str(a), 'version': '1', 'regla': 'vad.regla.inexistente'}}, registro,
                               tmp_path / 'm.json')
