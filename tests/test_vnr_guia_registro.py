"""108 T23 (108:RF-20): la Guía del VNR (RCD 232-2017-OS/CD) en el registro normativo y sus tablas del Anexo 6.

Se prueban los ficheros generados (``config/normativa/rcd_232_2017.json`` y ``config/vnr/anexo6_equivalencias.json``)
y el lector del generador con textos sintéticos, sin depender de la carpeta de fuentes oficiales.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = RAIZ / 'config' / 'normativa' / 'rcd_232_2017.json'
ANEXO6 = RAIZ / 'config' / 'vnr' / 'anexo6_equivalencias.json'


def _generador():
    ruta = RAIZ / 'tools' / 'normativa' / 'generar_guia_vnr_232.py'
    spec = importlib.util.spec_from_file_location('generar_guia_vnr_232', ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _reglas():
    datos = json.loads(REGISTRO.read_text(encoding='utf-8'))
    (norma,) = datos['normas']
    return norma, {r['clave']: r for r in norma['reglas']}


def test_108_rf20_la_guia_carga_en_el_registro_con_su_huella():
    cargar_registro(REGISTRO)
    norma, _ = _reglas()
    assert norma['acto'] == 'RCD 232-2017-OS/CD'
    assert norma['sha256'].startswith('c2236182c2032033')
    assert norma['fichero_local'] == 'VNR_GUIA_232_2017/rcd_232-2017.txt'


def test_108_rf20_la_guia_esta_comprobada_con_su_publicacion_en_el_peruano():
    """108:RF-20: publicación comprobada en la separata especial de El Peruano del 29-12-2017 (pág. 4), con la huella
    de esa copia; su art. 2 fija la vigencia desde el día siguiente. Antes de esa fecha no obliga."""
    norma, _ = _reglas()
    assert norma['estado_juridico'] == 'vigente_comprobada'
    assert norma['fecha_publicacion'] == '2017-12-29' and norma['vigencia_desde'] == '2017-12-30'
    assert norma['fecha_consulta'] == '2026-11-16'
    assert '24a7856025dd1e53' in norma['nota'] and 'pág. 4' in norma['nota']
    cargada = cargar_registro(REGISTRO).norma('RCD 232-2017-OS/CD')
    assert cargada.obligatoria_en('2026-11-16') and not cargada.obligatoria_en('2017-12-29')


def test_108_rf20_cada_regla_cita_su_articulo_su_pagina_y_sus_lineas():
    _, reglas = _reglas()
    for clave, r in reglas.items():
        assert r['cita_literal'].strip() and r['articulo_o_anexo'] and r['pagina'] and r['lineas'], clave


def test_108_rf20_formula_zonas_y_parametros_del_art_22():
    _, r = _reglas()
    assert r['vnr.formula']['valor'] == 'VNR = MIE * CEIE + MINE * CINE'
    assert r['vnr.formula']['articulo_o_anexo'] == 'art. 17.2'
    zonas = {z['zona']: (z['desde_mw_km2'], z['hasta_mw_km2']) for z in r['vnr.zonas.densidad']['valor']}
    assert zonas == {'Muy Alta': (4.0, None), 'Alta 1': (2.5, 4.0), 'Alta 2': (1.5, 2.5), 'Media': (0.25, 1.5),
                     'Baja': (None, 0.25)}
    assert r['vnr.corrosivo.ancho_km']['valor'] == 7
    assert r['vnr.cuadricula.lados_m']['valor'] == [1000, 500, 250]
    assert r['vnr.ap.factor_carga']['valor'] == 0.5 and r['vnr.ap.factor_coincidencia']['valor'] == 1.0
    assert r['vnr.valorizacion.costos_ie']['valor'] == 'costos_estandar_ultima_fijacion'
    assert 'última fijación del VNR' in r['vnr.valorizacion.costos_ie']['cita_literal']


def test_108_rf20_anexo6_con_huella_y_cada_fila_con_tantas_celdas_como_columnas():
    a6 = json.loads(ANEXO6.read_text(encoding='utf-8'))
    norma, _ = _reglas()
    assert a6['sha256_pdf'] == norma['sha256'] and a6['sha256_texto'] == norma['sha256_texto']
    assert [t['tabla'] for t in a6['tablas']] == list(range(1, 15))
    for t in a6['tablas']:
        if t['tipo'] == 'corrosivo_excepciones':
            continue  # la tabla 14: su forma se prueba aparte
        for f in t['filas']:
            assert len(f['valores']) == len(t['columnas']), (t['tabla'], f)
    assert a6['sin_filas_en_el_texto'] == [] and 'pendientes' not in norma and 'Pendiente:' not in norma['nota']


def test_108_rf20_tabla_14_de_provincias_corrosivas_leida_por_ocr_tal_como_la_imagen():
    """La Tabla N° 14 del Anexo 6 es una imagen (página 180): se lee por OCR celda a celda y se coteja aquí con la
    tabla vista en la imagen oficial."""
    t14 = json.loads(ANEXO6.read_text(encoding='utf-8'))['tablas'][-1]
    assert t14['tabla'] == 14 and t14['pagina'] == 180 and t14['origen_lectura'].startswith('OCR celda a celda')
    assert [(f['departamento'], f['provincia'], f['tramos_corrosivos_km']) for f in t14['filas']] == [
        ('Ancash', 'Santa', [[0, 3], [5, 7], [10, 16]]), ('La Libertad', 'Trujillo', [[0, 11]]),
        ('Lambayeque', 'Chiclayo', [[0, 14]]), ('Piura', 'Sechura', [[0, 6]]), ('Piura', 'Paita', []),
        ('Piura', 'Talara', []), ('Tumbes', 'Contralmirante Villar', []), ('Tumbes', 'Tumbes', []),
        ('Tumbes', 'Zarumilla', [])]


def test_108_rf20_las_franjas_de_la_tabla_14_se_leen_o_se_para():
    g = _generador()
    assert g._tramos('0-3km,5-7kmy 10-16 km') == [[0, 3], [5, 7], [10, 16]]
    assert g._tramos('O km') == [] and g._tramos('O-11km') == [[0, 11]]
    with pytest.raises(SystemExit):
        g._tramos('sin dato')
    with pytest.raises(SystemExit):
        g._tramos('7 - 3 km')


def test_108_rf20_valores_del_anexo6_tal_como_el_texto_oficial():
    t = {x['tabla']: x for x in json.loads(ANEXO6.read_text(encoding='utf-8'))['tablas']}
    fila = lambda n, origen, mm2: next(f for f in t[n]['filas'] if f['origen'] == origen and f['seccion_mm2'] == mm2)
    assert t[1]['tipo'] == 'tension' and fila(1, 'AA Desnudo', 185)['valores'] == [50, 95]
    assert t[4]['columnas'][:2] == ['AA Desnudo', 'CU Desnudo']
    assert fila(4, 'AA Desnudo', 185)['valores'] == [185, 120, 185, 400, 150, 185]
    # Sin equivalente en la columna, se conserva otro material: «CU Desnudo 185».
    assert fila(5, 'CU Desnudo', 185)['valores'][0] == {'material': 'CU Desnudo', 'seccion_mm2': 185}
    assert {f['origen']: f['valores'][0] for f in t[10]['filas']}['Mercurio'] == 'Sodio'


def test_108_rf20_el_lector_separa_celdas_con_material_y_para_si_una_fila_no_cuadra():
    g = _generador()
    texto = ('x\nTABLAS DE EQUIVALENCIA\nTabla N° 4\nOrigen Equivalencia en AA Desnudo Equivalencia en CU Desnudo\n'
             'AA Desnudo\n16 mm2 16 10\n185 mm2 CU Desnudo 185 120\n')
    a6 = g.anexo6(g.Texto(texto))
    (tabla,) = a6['tablas']
    assert tabla['columnas'] == ['AA Desnudo', 'CU Desnudo']
    assert tabla['filas'][1]['valores'] == [{'material': 'CU Desnudo', 'seccion_mm2': 185}, 120]
    with pytest.raises(SystemExit, match='trae 3 valores'):
        g.anexo6(g.Texto(texto + '240 mm2 240 150 95\n'))


def test_108_rf20_la_cita_es_literal_y_para_si_falta_la_marca():
    g = _generador()
    t = g.Texto('a\n22.1 El proceso\nde 7 km de ancho.\n22.2 Otro\n')
    c = t.cita('22.1 El proceso', '22.2')
    assert c['cita_literal'] == '22.1 El proceso de 7 km de ancho.' and c['lineas'] == '2-4'
    with pytest.raises(SystemExit, match='no está'):
        t.cita('23.1 Falta', '23.2')


def test_108_rf20_el_anexo_2_trae_los_equipos_de_proteccion_y_seccionamiento():
    """108:RF-20 — el componente C de la MT (interruptores, seccionadores, seccionalizadores y reconectadores) lleva
    códigos de 11 caracteres («RE005041011»); el lector solo aceptaba hasta 9 y el componente entero faltaba."""
    codigos = json.loads((RAIZ / 'config' / 'vnr' / 'anexo2_codigos.json').read_text(encoding='utf-8'))['codigos']
    c_mt = [c for c in codigos if c['grupo'].startswith('1') and c['componente'].startswith('C ')]
    assert {c['subcomponente'].split()[0] for c in c_mt} >= {'C2', 'C3'}
    assert any(c['codigo'].startswith('RE') and len(c['codigo']) == 11 for c in c_mt)
    assert any(c['codigo'].startswith('SC') for c in c_mt)


def test_108_rf20_un_codigo_repetido_por_la_guia_queda_anotado_y_no_se_pierde():
    """108:RF-20 — la Guía repite IN063311023 en C1 (la segunda vez «INTEGRADO»): vale la primera fila y la repetición
    queda anotada en ella con su línea y su descripción."""
    codigos = json.loads((RAIZ / 'config' / 'vnr' / 'anexo2_codigos.json').read_text(encoding='utf-8'))['codigos']
    (fila,) = [c for c in codigos if c['codigo'] == 'IN063311023']
    assert fila['repetido_en'] and 'INTEGRADO' in fila['repetido_en'][0]['descripcion']
