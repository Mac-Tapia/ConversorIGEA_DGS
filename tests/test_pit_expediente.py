"""Spec 107 T10 — expediente y cuadros: carpeta aparte, instantánea, traza de cada celda, modificatoria posterior y
determinismo (107:RF-1, 107:RF-7, 107:RF-8, 107:RF-9, 107:RF-14). Todo sintético: registro, costos y área sorteada."""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl
import pytest

from datos_pit import perfil_a

from convertersmartgrid.costos_fuentes import Costo, FuenteCostos, TablaCostos
from convertersmartgrid.perfil_esquema import validar_perfil
from convertersmartgrid.pit.alternativas import evaluar
from convertersmartgrid.pit.ambito import PitError, areas_del_perfil, reunir
from convertersmartgrid.pit.cuadros import celdas_de_cuadros, definiciones, escribir_libro_de_cuadros
from convertersmartgrid.pit.diagnostico import agregar_demanda, diagnosticar, limites_del_estudio
from convertersmartgrid.pit.expediente import (abrir, comprobar_modificatoria, emitir, escribir_informacion_general,
                                                filas_del_programa)
from convertersmartgrid.pit.programa import programar
from convertersmartgrid.pit.red_area import desde_ambito
from convertersmartgrid.registro_normativo import cargar_registro

MONEDA = 'XTS'
COLUMNAS = [{'nombre': 'N°', 'campo': 'numero'}, {'nombre': 'Año', 'campo': 'anio'},
            {'nombre': 'Titular', 'campo': 'titular'}, {'nombre': 'Proyecto', 'campo': 'descripcion'},
            {'nombre': 'Inversión', 'campo': 'inversion', 'moneda': MONEDA}]


def _regla(clave, valor):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave}»', 'pagina': '2'}


def _normas(modificatoria=False):
    normas = [{'acto': 'SINT-PIT', 'titulo': 'Norma sintética', 'estado_juridico': 'vigente_comprobada',
               'sha256': 'a' * 64, 'vigencia_desde': '2001-01-01', 'reglas': [
                   _regla('pit.tasa_actualizacion', 0.1), _regla('pit.vida_util_anios', 30),
                   _regla('pit.coym_pct', 2.5), _regla('pit.tension_min_pu', 0.9), _regla('pit.tension_max_pu', 1.1),
                   _regla('pit.factor_utilizacion_max', 1.0),
                   _regla('pit.cuadro.nuevas', {'titulo': 'Altas', 'filas': 'altas', 'columnas': COLUMNAS}),
                   _regla('pit.cuadro.bajas', {'titulo': 'Bajas', 'filas': 'bajas', 'columnas': COLUMNAS[:4]})]},
              {'acto': 'SINT-PRE', 'titulo': 'Prepublicada', 'estado_juridico': 'prepublicada',
               'reglas': [_regla('pit.precio_perdidas', 30.0), _regla('pit.horas_perdidas', 2500.0)]}]
    if modificatoria:
        normas.append({'acto': 'SINT-MOD', 'titulo': 'Modificatoria posterior', 'estado_juridico': 'vigente_comprobada',
                       'sha256': 'b' * 64, 'vigencia_desde': '2002-01-01', 'modifica': ['SINT-PIT'],
                       'reglas': [_regla('pit.cuadro.nuevas', {'titulo': 'Altas (mod.)', 'filas': 'altas',
                                                               'columnas': COLUMNAS})]})
    return normas


def _registro(carpeta: Path, modificatoria=False):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1',
                                                'normas': _normas(modificatoria)}), encoding='utf-8')
    return cargar_registro(carpeta)


def _tablas():
    f = FuenteCostos('Módulos sintéticos', 'transmision', 'SINT-001', 2001, MONEDA, 'https://ejemplo.invalid',
                     '2001-01-01', '9' * 64)
    return {'transmision': TablaCostos(f, {('TP-S', '', '', ''): Costo('TP-S', '', '', '', 'Trafo', {'total': 500.0},
                                                                        f, unidad='u')})}


def _piezas(raiz: Path, seed=27, fabrica=perfil_a, registro=None):
    """Diagnóstico, comparación, programa y celdas de un área sintética, y la carpeta abierta de su expediente."""
    caso = fabrica(seed)
    registro = registro or _registro(raiz / 'reg')
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, caso['elementos']))
    # Dos años con demanda (el perfil B tiene uno sin ella, que dejaría la alternativa incompleta).
    anios = [a for a in caso['anios'] if a != caso['pistas'].get('anio_sin_demanda')][:2]
    diag = diagnosticar(area, red, caso['proyeccion'], anios, limites_del_estudio(registro, caso['perfil']))
    t = red.de_tipo('trafo2')[0]
    s, titular = t['set'], t['titular']
    nuevo = {**t, 'id': f'{t["id"]}-2'}
    comp = evaluar(red, [{'nombre': 'refuerzo', 'cambios': [
        {'accion': 'alta', 'elemento': nuevo, 'costo': {'codigo': 'TP-S', 'cantidad': 1, 'unidad': 'u'}}]}],
        agregar_demanda(area, red, caso['proyeccion']), anios, registro, _tablas())
    cambios = [{'accion': 'alta', 'elemento': nuevo['id'], 'anio': anios[1], 'titular': titular,
                'descripcion': 'Transformador en paralelo', 'instalacion': s},
               {'accion': 'baja', 'elemento': f'C-{s}', 'anio': anios[1], 'titular': titular, 'instalacion': s}]
    prog = programar(area, cambios)
    celdas = celdas_de_cuadros(definiciones(registro), filas_del_programa(prog, comp, 'refuerzo'))
    carpeta = abrir(raiz / 'espacio', caso['area'], f'{anios[0]}-{anios[-1]}', registro, fecha_apertura='2001-06-01')
    return {'caso': caso, 'registro': registro, 'area': area, 'diag': diag, 'comp': comp, 'prog': prog,
            'cambios': cambios, 'celdas': celdas, 'carpeta': carpeta, 'anios': anios, 'nuevo': nuevo['id']}


def _expediente(raiz: Path, seed=27, **emision):
    x = _piezas(raiz, seed)
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], diagnostico=x['diag'], comparacion=x['comp'],
                     programa=x['prog'], no_transcritos=['pit.formatos_217'], **emision)
    return x['caso'], x['carpeta'], salidas, x['celdas']


def test_dos_corridas_dan_el_mismo_expediente(tmp_path):
    """107:RF-9 — mismo caso, misma norma y mismos costos: el mismo expediente byte a byte."""
    _, c1, s1, _ = _expediente(tmp_path / 'uno')
    _, c2, s2, _ = _expediente(tmp_path / 'dos')
    assert set(s1) == set(s2) >= {'cuadros', 'reglas', 'resumen', 'diagnostico', 'alternativas', 'programa'}
    for k in s1:
        assert s1[k].read_bytes() == s2[k].read_bytes(), k
    assert (c1 / 'expediente.json').read_bytes() == (c2 / 'expediente.json').read_bytes()


def test_carpeta_aparte_del_pide_y_sin_aprobacion(tmp_path):
    """107:RF-1 — el expediente va en su carpeta del PIT y ningún fichero dice que lo aprobó el regulador."""
    caso, carpeta, salidas, _ = _expediente(tmp_path)
    assert carpeta.relative_to(tmp_path / 'espacio').parts[:2] == ('expedientes_pit', caso['area'])
    for ruta in carpeta.iterdir():
        assert not re.search(r'aprobad[oa]s?\s+por\s+(el\s+)?osinergmin', ruta.read_text(encoding='utf-8'), re.I)


def test_cada_celda_con_su_traza_y_las_reglas_con_su_estado(tmp_path):
    """107:RF-7, 107:RF-9 — ninguna celda sin fuente con huella, cálculo, motor y regla; las reglas con su estado."""
    _, _, salidas, _ = _expediente(tmp_path)
    celdas = json.loads(salidas['cuadros'].read_text(encoding='utf-8'))
    assert celdas
    for c in celdas:
        t = c['traza']
        assert t['fuente']['huella'] and t['calculo']['funcion'] and t['motor'] == 'abierto'
        assert t['regla']['norma'] == 'SINT-PIT' and t['regla']['estado'] == 'vigente_comprobada'
    inv = [c for c in celdas if c['columna'] == 'Inversión']
    assert inv and inv[0]['valor'] == 500.0 and inv[0]['traza']['calculo']['funcion'] == 'costos_fuentes.valorar_obra'
    reglas = {r['clave']: r for r in json.loads(salidas['reglas'].read_text(encoding='utf-8'))}
    assert reglas['pit.tasa_actualizacion']['obligatoria'] and reglas['pit.tasa_actualizacion']['norma'] == 'SINT-PIT'
    assert reglas['pit.precio_perdidas']['estado'] == 'prepublicada'
    assert reglas['pit.precio_perdidas']['uso'].startswith('referencia')
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert 'pit.precio_perdidas' in resumen['reglas_como_referencia']
    assert resumen['cuadros_no_transcritos'] == ['pit.formatos_217']


def test_modificatoria_posterior_se_avisa_sin_recalcular(tmp_path):
    """107:RF-8 — una modificatoria publicada tras abrir el expediente se avisa con las celdas afectadas; nada cambia."""
    _, carpeta, salidas, _ = _expediente(tmp_path)
    antes = {k: p.read_bytes() for k, p in salidas.items()}
    nuevo = _registro(tmp_path / 'reg2', modificatoria=True)
    r = comprobar_modificatoria(carpeta, nuevo)
    assert r['cambiado'] and 'pit.cuadro.nuevas' in r['reglas'] and 'no se ha recalculado' in r['aviso']
    assert r['celdas_afectadas'] and all(c.startswith('pit.cuadro.nuevas!') for c in r['celdas_afectadas'])
    assert {k: p.read_bytes() for k, p in salidas.items()} == antes
    assert comprobar_modificatoria(carpeta, _registro(tmp_path / 'reg3'))['cambiado'] is False


def test_celda_sin_traza_o_frase_de_aprobacion_no_se_emite(tmp_path):
    """107:RF-9 — una celda sin traza, o un texto que se diga aprobado por el regulador, no se emite."""
    _, carpeta, _, celdas = _expediente(tmp_path)
    reg = _registro(tmp_path / 'reg')
    malas = [dict(celdas[0], traza={**celdas[0]['traza'], 'motor': ''})]
    with pytest.raises(PitError, match='sin traza'):
        emitir(carpeta, reg, celdas=malas)
    frase = [dict(celdas[0], valor='Proyecto aprobado por Osinergmin')]
    with pytest.raises(PitError, match='aprobado por el regulador'):
        emitir(carpeta, reg, celdas=frase)


def test_cuadros_en_el_libro_modelo(tmp_path):
    """107:RF-9 — los cuadros van al libro modelo del perfil por el mecanismo de libro_informe."""
    _, carpeta, salidas, celdas = _expediente(tmp_path)
    modelo = tmp_path / 'modelo.xlsx'
    wb = openpyxl.Workbook()
    wb.active.title = 'Cuadros'
    wb.save(modelo)
    config = {'modelo': str(modelo), 'cuadros': {'pit.cuadro.nuevas': {'hoja': 'Cuadros', 'celda': 'B4'},
                                                  'pit.cuadro.bajas': {'hoja': 'Cuadros', 'celda': 'B20'}}}
    destino = tmp_path / 'salida.xlsx'

    def excel_falso(orden):
        """En vez de Excel: aplica el plan que libro_informe deja en un fichero temporal."""
        plan = json.loads(Path(re.search(r"-LiteralPath '([^']+)'", orden).group(1)).read_text(encoding='utf-8'))
        libro = openpyxl.load_workbook(plan['modelo'])
        for e in plan['escribir']:
            hoja, ref = e['celda'].rsplit('!', 1)
            libro[hoja][ref] = e['valor']
        libro.save(plan['destino'])

    ruta, motivo = escribir_libro_de_cuadros(celdas, config, destino=destino, ejecutar=excel_falso)
    assert ruta == destino and motivo == ''
    hoja = openpyxl.load_workbook(destino)['Cuadros']
    assert hoja['F4'].value == 500.0 and hoja['D4'].value == hoja['D20'].value
    r = validar_perfil({'pit': {'libro_cuadros': config}})
    assert r.errores == [] and 'pit.libro_cuadros' not in r.desconocidas


# --- Memoria y relación de sustento (107:RF-14, T22) -----------------------------------------------------------------

def test_memoria_de_cada_seccion(tmp_path):
    """107:RF-14 — cada sección emitida lleva su memoria: criterios, metodología, entradas y resultados, tomados de lo
    que la produjo (los límites del diagnóstico, las reglas de las alternativas, el programa y los cuadros)."""
    _, _, salidas, celdas = _expediente(tmp_path)
    memoria = json.loads(salidas['memoria'].read_text(encoding='utf-8'))
    assert set(memoria) == {'diagnostico', 'alternativas', 'programa', 'cuadros'}
    for seccion, m in memoria.items():
        assert set(m) == {'criterios', 'metodologia', 'entradas', 'resultados'}, seccion
        assert all(m[k] for k in ('criterios', 'metodologia', 'entradas')), seccion
    diag = json.loads(salidas['diagnostico'].read_text(encoding='utf-8'))
    assert memoria['diagnostico']['criterios']['tension_min_pu']['valor'] == diag['limites']['tension_min_pu']['valor']
    assert memoria['diagnostico']['resultados']['anios_diagnosticados'] == len(diag['anios'])
    alts = json.loads(salidas['alternativas'].read_text(encoding='utf-8'))
    assert memoria['alternativas']['resultados']['orden'] == alts['orden']
    assert set(memoria['alternativas']['criterios']) == set(alts['reglas'])
    assert memoria['cuadros']['entradas']['celdas'] == len(celdas)
    assert memoria['cuadros']['resultados']['no_transcritos'] == ['pit.formatos_217']


def test_sin_diagnostico_ni_alternativas_la_memoria_no_inventa_secciones(tmp_path):
    """107:RF-14 — solo se describe lo que se emite: sin diagnóstico ni comparación no hay memoria de ellos."""
    x = _piezas(tmp_path)
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], programa=x['prog'])
    assert set(json.loads(salidas['memoria'].read_text(encoding='utf-8'))) == {'programa', 'cuadros'}


def test_relacion_de_sustento_con_cada_fichero_y_su_huella(tmp_path):
    """107:RF-14 — cada fichero del expediente figura en la relación con su descripción, su uso y su huella; un
    documento que la empresa añade sin describirlo detiene la emisión y se nombra, y descrito, entra."""
    import hashlib

    _, carpeta, salidas, _ = _expediente(tmp_path)
    relacion = json.loads(salidas['relacion'].read_text(encoding='utf-8'))
    ficheros = sorted(p.name for p in carpeta.iterdir() if p.name != 'relacion_sustento.json')
    assert [r['fichero'] for r in relacion] == ficheros
    for r in relacion:
        assert r['descripcion'] and r['uso']
        assert r['sha256'] == hashlib.sha256((carpeta / r['fichero']).read_bytes()).hexdigest()
    x = _piezas(tmp_path / 'otra')
    (x['carpeta'] / 'acta_de_campo.pdf').write_bytes(b'%PDF-1.4 sintetico')
    with pytest.raises(PitError, match='acta_de_campo.pdf'):
        emitir(x['carpeta'], x['registro'], celdas=x['celdas'])
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], sustento={
        'acta_de_campo.pdf': {'descripcion': 'Acta de la inspección de campo', 'uso': 'sustento del inventario'}})
    acta = next(r for r in json.loads(salidas['relacion'].read_text(encoding='utf-8'))
                if r['fichero'] == 'acta_de_campo.pdf')
    assert acta['descripcion'] == 'Acta de la inspección de campo'


# --- Relación de los documentos de sustento por volúmenes y el F-000 (107:RF-14, aclaración de RF-9, P10) ----------

def _relacion_por_volumenes(salidas):
    assert 'relacion_documentos' in salidas, 'el expediente no escribe la relación por volúmenes'
    return json.loads(salidas['relacion_documentos'].read_text(encoding='utf-8'))


def _todos_en_dos_volumenes(x):
    """Emite una vez para saber qué documentos tiene el expediente y los reparte en dos volúmenes, con sus folios."""
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], diagnostico=x['diag'], comparacion=x['comp'],
                     programa=x['prog'])
    nombres = [r['fichero'] for r in json.loads(salidas['relacion'].read_text(encoding='utf-8'))]
    nombres = sorted({*nombres, 'relacion_documentos.json'})
    mitad = len(nombres) // 2
    colocados = {n: {'volumen': 'I' if i < mitad else 'II', 'folios': i + 2} for i, n in enumerate(nombres)}
    volumenes = {'volumenes': [{'volumen': 'I', 'titulo': 'Resumen y diagnóstico'},
                               {'volumen': 'II', 'titulo': 'Sustento y formatos'}], 'documentos': colocados}
    return nombres, colocados, volumenes


def test_relacion_de_sustento_con_sus_seis_campos(tmp_path):
    """107:RF-14 — num. 5.3: cada documento de sustento figura con su n.º, su fichero, su tipo, la descripción de su
    contenido, su aplicación y su volumen con sus folios, en la tabla legible y por volumen; la lista de
    ``relacion_sustento.json`` sigue ordenada por fichero, con su descripción, su uso y su huella."""
    import hashlib

    x = _piezas(tmp_path)
    nombres, _, volumenes = _todos_en_dos_volumenes(x)
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], diagnostico=x['diag'], comparacion=x['comp'],
                     programa=x['prog'], volumenes=volumenes)
    rel = _relacion_por_volumenes(salidas)
    assert rel['tabla']['columnas'] == ['n.º', 'fichero', 'tipo', 'descripción', 'aplicación', 'volumen', 'folios']
    assert sorted(f[1] for f in rel['tabla']['filas']) == nombres
    for fila in rel['tabla']['filas']:
        assert all(fila), fila
        assert fila[2] == 'electrónico'
    for v in rel['volumenes']:
        for d in v['documentos']:
            assert d['descripcion'] and d['aplicacion'] and d['volumen'] == v['volumen'] and d['folio_desde']
    assert rel['huecos'] == [h for h in rel['huecos'] if h['campo'] == 'F-000']
    lista = json.loads(salidas['relacion'].read_text(encoding='utf-8'))
    assert [r['fichero'] for r in lista] == nombres
    for r in lista:
        assert r['descripcion'] and r['uso'] and r['aplicacion'] and r['volumen'] in {'I', 'II'}
        assert r['sha256'] == hashlib.sha256((x['carpeta'] / r['fichero']).read_bytes()).hexdigest()


def test_relacion_agrupada_por_volumenes_con_foliado_consecutivo(tmp_path):
    """107:RF-14 — num. 5.5: los volúmenes salen en su orden, el n.º corre de uno a otro y los folios son
    consecutivos sin reiniciar en cada volumen; cada volumen dice su primer y su último folio."""
    x = _piezas(tmp_path)
    _, colocados, volumenes = _todos_en_dos_volumenes(x)
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], diagnostico=x['diag'], comparacion=x['comp'],
                     programa=x['prog'], volumenes=volumenes)
    rel = _relacion_por_volumenes(salidas)
    assert [v['volumen'] for v in rel['volumenes']] == ['I', 'II']
    docs = [d for v in rel['volumenes'] for d in v['documentos']]
    assert [d['numero'] for d in docs] == list(range(1, len(colocados) + 1))
    assert [d['fichero'] for d in docs] == list(colocados)
    folio = 1
    for d in docs:
        assert (d['folio_desde'], d['folio_hasta']) == (folio, folio + colocados[d['fichero']]['folios'] - 1)
        folio = d['folio_hasta'] + 1
    primero, segundo = rel['volumenes']
    assert primero['folio_desde'] == 1 and segundo['folio_desde'] == primero['folio_hasta'] + 1
    assert segundo['folio_hasta'] == folio - 1
    with pytest.raises(PitError, match='III'):
        emitir(x['carpeta'], x['registro'], celdas=x['celdas'], volumenes={
            'volumenes': volumenes['volumenes'], 'documentos': {'expediente.json': {'volumen': 'III', 'folios': 1}}})


def test_relacion_sin_folios_o_sin_volumen_lleva_su_hueco(tmp_path):
    """107:RF-14 — un documento sin sus folios interrumpe el foliado de los que siguen, y uno sin volumen no se folia:
    cada uno lo dice en su hueco, sin inventar folios; sin organización por volúmenes, todos llevan ese hueco."""
    x = _piezas(tmp_path)
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], volumenes={
        'volumenes': [{'volumen': 'I', 'titulo': 'Único'}],
        'documentos': {'expediente.json': {'volumen': 'I', 'folios': 3}, 'cuadros.json': {'volumen': 'I'},
                       'resumen.json': {'volumen': 'I', 'folios': 2}}})
    rel = _relacion_por_volumenes(salidas)
    assert [v['volumen'] for v in rel['volumenes']] == ['I', None]
    docs = {d['fichero']: d for d in rel['volumenes'][0]['documentos']}
    assert (docs['expediente.json']['folio_desde'], docs['expediente.json']['folio_hasta']) == (1, 3)
    assert docs['cuadros.json']['folio_desde'] is None and docs['resumen.json']['folio_desde'] is None
    causas = {(h['fichero'], h['campo']): h['causa'] for h in rel['huecos']}
    assert 'cuadros.json' in causas[('cuadros.json', 'folios')]
    assert 'interrumpido' in causas[('resumen.json', 'folios')]
    assert ('reglas_aplicadas.json', 'volumen') in causas and not rel['completa']
    rel = _relacion_por_volumenes(emitir(x['carpeta'], x['registro'], celdas=x['celdas']))
    assert all(d['volumen'] is None for v in rel['volumenes'] for d in v['documentos'])
    assert {f for f, c in ((h['fichero'], h['campo']) for h in rel['huecos']) if c == 'volumen'} == {
        f[1] for f in rel['tabla']['filas']}


def test_documento_sin_descripcion_o_sin_aplicacion_es_un_hueco_nombrado(tmp_path):
    """107:RF-14 — un documento que la empresa declara sin descripción o sin aplicación entra en la relación con su
    hueco nombrado, nunca con un texto inventado; uno que nadie declara sigue deteniendo la emisión."""
    x = _piezas(tmp_path)
    (x['carpeta'] / 'plano_sin_texto.pdf').write_bytes(b'%PDF-1.4 sintetico')
    (x['carpeta'] / 'hoja_sin_uso.xlsx').write_bytes(b'PK sintetico')
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], volumenes=None, sustento={
        'plano_sin_texto.pdf': {'descripcion': '', 'aplicacion': 'sustenta el F-101', 'tipo': 'físico'},
        'hoja_sin_uso.xlsx': {'descripcion': 'Hoja de cálculo de la demanda'}})
    rel = _relacion_por_volumenes(salidas)
    filas = {f[1]: f for f in rel['tabla']['filas']}
    assert {'plano_sin_texto.pdf', 'hoja_sin_uso.xlsx'} <= set(filas)
    assert filas['plano_sin_texto.pdf'][2:5] == ['físico', '', 'sustenta el F-101']
    assert filas['hoja_sin_uso.xlsx'][3:5] == ['Hoja de cálculo de la demanda', '']
    causas = {(h['fichero'], h['campo']) for h in rel['huecos']}
    assert {('plano_sin_texto.pdf', 'descripcion'), ('hoja_sin_uso.xlsx', 'aplicacion')} <= causas
    assert ('plano_sin_texto.pdf', 'aplicacion') not in causas and not rel['completa']
    with pytest.raises(PitError, match='tipo'):
        emitir(x['carpeta'], x['registro'], celdas=x['celdas'], sustento={
            'plano_sin_texto.pdf': {'descripcion': 'x', 'uso': 'y', 'tipo': 'otro'},
            'hoja_sin_uso.xlsx': {'descripcion': 'x', 'uso': 'y'}})


def test_documento_declarado_sin_descripcion_deja_el_expediente_incompleto(tmp_path):
    """Aclaración de 107:RF-14 — un documento declarado sin descripción o sin uso no detiene la emisión: el resumen del
    expediente dice que sale «incompleto» y lleva ese hueco en sus pendientes, los mismos que la relación."""
    x = _piezas(tmp_path)
    (x['carpeta'] / 'memoria_de_campo.pdf').write_bytes(b'%PDF-1.4 sintetico')
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], sustento={
        'memoria_de_campo.pdf': {'descripcion': '', 'uso': ''}})
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert resumen.get('estado') == 'incompleto'
    faltan = {(h['fichero'], h['campo']) for h in resumen['pendientes']}
    assert {('memoria_de_campo.pdf', 'descripcion'), ('memoria_de_campo.pdf', 'aplicacion')} <= faltan
    # Sin alternativas, el resumen añade el pendiente del expediente de diagnóstico (aclaración de 107:RF-5, P10c).
    relacion = [h for h in resumen['pendientes'] if h['campo'] != 'alternativas']
    assert relacion == _relacion_por_volumenes(salidas)['huecos']


def _celdas_de_informacion_general(x, codigos):
    """Celdas sintéticas de los formatos ``codigos``, con la traza de una celda real del expediente."""
    base = x['celdas'][0]
    return [*x['celdas'], *({**base, 'id': f'{c}!sintetica', 'cuadro': c} for c in codigos)]


def test_f000_incompleto_nombra_el_formato_del_grupo_que_falta(tmp_path):
    """Aclaración de 107:RF-14 — el «F-000» no es una plantilla: es el grupo «Formatos de Información General», que la
    RCD 217-2013 (art. 30.1, Tabla 1 y art. 31) forma con F-001, F-002 y F-003. Si al expediente le falta uno, el F-000
    sale con el hueco «F-000 incompleto: falta F-00x», y el expediente, «incompleto» con ese hueco en sus pendientes."""
    x = _piezas(tmp_path)
    salidas = emitir(x['carpeta'], x['registro'], celdas=_celdas_de_informacion_general(x, ['F-001', 'F-003']))
    rel = _relacion_por_volumenes(salidas)
    f000 = rel['F-000']
    assert f000.get('cumplido') is False
    assert f000['equivale_a'] == ['F-001', 'F-002', 'F-003'] and f000['faltan'] == ['F-002']
    assert f000['nombre'] == 'F-000 (grupo: F-001 a F-003)' and any('30.1' in c['donde'] for c in f000['citas'])
    assert f000['hueco'] == 'F-000 incompleto: falta F-002'
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert resumen['estado'] == 'incompleto'
    assert {'campo': 'F-000', 'causa': 'F-000 incompleto: falta F-002', 'fichero': None, 'numero': None} in \
        resumen['pendientes']


def test_f000_cumplido_con_los_tres_formatos_del_grupo(tmp_path):
    """Aclaración de 107:RF-14 — con F-001, F-002 y F-003 en el expediente, el «F-000» (el grupo «Formatos de
    Información General» de la RCD 217-2013, art. 30.1) se da por cumplido, sin hueco, y no deja el expediente
    incompleto por sí mismo; la relación del num. 5.3 sigue siendo una exigencia aparte, sin plantilla."""
    x = _piezas(tmp_path)
    salidas = emitir(x['carpeta'], x['registro'],
                     celdas=_celdas_de_informacion_general(x, ['F-001', 'F-002', 'F-003']))
    rel = _relacion_por_volumenes(salidas)
    f000 = rel['F-000']
    assert f000.get('cumplido') is True
    assert f000['presentes'] == ['F-001', 'F-002', 'F-003'] and f000['faltan'] == [] and 'hueco' not in f000
    assert 'práctica de las empresas' in f000['nombre_de_fichero']['nota']
    assert not [h for h in rel['huecos'] if h['campo'] == 'F-000']
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert not [h for h in resumen['pendientes'] if h['campo'] == 'F-000']
    assert all(h['campo'] in {'volumen', 'folios', 'alternativas'} for h in resumen['pendientes'])


# --- Libro de Información General de la entrega, el «F-000» (107-P10b; aclaración de 107:RF-14) ---------------------

AREA_IG, PERIODO_IG = 'AD-X', '2025-2029'
NOMBRE_IG = 'F-000-AD-X_2025-2029.xlsx'


def _excel_simulado(orden_de_pasos):
    """Aplica el plan con openpyxl, como el Excel de las pruebas de los informes, anotando el orden de los pasos."""
    import re
    from types import SimpleNamespace

    def ejecutar(orden):
        plan = json.loads(Path(re.search(r"-LiteralPath '([^']+)'", orden).group(1)).read_text(encoding='utf-8'))
        libro = openpyxl.load_workbook(plan['modelo'])
        for i in plan.get('insertar_filas') or ():
            libro[i['hoja']].insert_rows(i['fila'], i['filas'])
            orden_de_pasos.append(('insertar', i['hoja'], i['fila']))
        for e in plan['escribir']:
            hoja, celda = e['celda'].rsplit('!', 1)
            libro[hoja][celda] = e['valor']
            orden_de_pasos.append(('escribir', hoja, celda))
        orden_de_pasos.append(('modelo', plan['modelo']))
        libro.save(plan['destino'])
        return SimpleNamespace(returncode=0, stderr='')
    return ejecutar


def _informacion_general(tmp_path, codigos=('F-001', 'F-002', 'F-003'), lineas_extra=6, sha=None):
    """Registro real, red sintética (8 líneas en F-002: 3 filas que insertar), un libro «oficial» sintético con sus
    tres hojas y una marca bajo las líneas de F-002, el alias con su sha y el expediente abierto."""
    import copy
    import hashlib

    from test_pit_formatos import FUENTE_RED, NORMATIVA, _red

    from convertersmartgrid.pit.formatos_red import datos_f001, datos_f002, datos_f003
    from convertersmartgrid.pit.plantillas import cargar_mapeo, celdas_de_formato
    registro = cargar_registro(NORMATIVA)
    red = _red(lineas_extra)
    datos = {'F-001': datos_f001(red, registro, FUENTE_RED)[0], 'F-002': datos_f002(red, FUENTE_RED),
             'F-003': datos_f003(red, FUENTE_RED)}
    resultados = [celdas_de_formato(registro, c, datos[c]) for c in codigos]
    fuentes = tmp_path / 'fuentes'
    (fuentes / 'libros').mkdir(parents=True)
    oficial = fuentes / 'libros' / 'informacion_general.xlsx'
    libro = openpyxl.Workbook()
    libro.active.title = 'F-001'
    libro.create_sheet('F-002')
    libro.create_sheet('F-003')
    libro['F-002']['A15'] = 'bajo las líneas de ejemplo'
    libro['F-003']['A1'] = 'F-003 de la plantilla'
    libro.save(oficial)
    mapeo = copy.deepcopy(cargar_mapeo())
    mapeo['alias']['F-000']['plantilla_oficial'] = {
        'ruta_relativa': 'libros/informacion_general.xlsx',
        'sha256': sha or hashlib.sha256(oficial.read_bytes()).hexdigest()}
    carpeta = abrir(tmp_path / 'espacio', AREA_IG, PERIODO_IG, registro, fecha_apertura='2001-06-01')
    return {'registro': registro, 'resultados': resultados, 'fuentes': fuentes, 'oficial': oficial, 'mapeo': mapeo,
            'carpeta': carpeta}


def test_libro_de_informacion_general_con_el_nombre_del_patron_y_sus_tres_hojas(tmp_path):
    """Aclaración de 107:RF-14 (P10b) — el «F-000» se entrega como libro aparte, con el nombre del alias del mapeo
    (``F-000-{area}_{periodo}.xlsx``, de la ficha) y las hojas F-001, F-002 y F-003 de la plantilla oficial (RCD
    217-2013, art. 30.1), escrito en una copia: el original no cambia."""
    import hashlib

    x = _informacion_general(tmp_path)
    antes = hashlib.sha256(x['oficial'].read_bytes()).hexdigest()
    pasos = []
    r = escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=_excel_simulado(pasos),
                                     mapeo=x['mapeo'])
    assert r['nombre'] == NOMBRE_IG
    assert r['libro'] is not None and r['libro'].resolve() == (x['carpeta'] / NOMBRE_IG).resolve()
    assert r['libro'].is_file() and r['motivo'] == ''
    assert openpyxl.load_workbook(r['libro']).sheetnames == ['F-001', 'F-002', 'F-003']
    modelo = next(p[1] for p in pasos if p[0] == 'modelo')
    assert Path(modelo) != x['oficial'] and hashlib.sha256(x['oficial'].read_bytes()).hexdigest() == antes


def test_cada_hoja_lleva_las_celdas_de_su_formato(tmp_path):
    """Aclaración de 107:RF-14 (P10b) — cada hoja lleva las celdas de su formato en su referencia, con las filas que
    sobran de la plantilla insertadas antes de escribir (lo de debajo baja, no se pisa)."""
    x = _informacion_general(tmp_path)
    pasos = []
    r = escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=_excel_simulado(pasos),
                                     mapeo=x['mapeo'])
    assert r['libro'] is not None and r['libro'].is_file()
    libro = openpyxl.load_workbook(r['libro'])
    for resultado in x['resultados']:
        for c in resultado['celdas']:
            hoja, celda = c['celda'].rsplit('!', 1)
            if c['valor'] not in (None, ''):
                assert libro[hoja][celda].value == c['valor'], c['id']
    assert ('insertar', 'F-002', 15) in pasos
    assert max(i for i, p in enumerate(pasos) if p[0] == 'insertar') < min(
        i for i, p in enumerate(pasos) if p[0] == 'escribir')
    assert libro['F-002']['A18'].value == 'bajo las líneas de ejemplo'


def test_falta_un_formato_el_libro_sale_con_lo_que_hay_y_sigue_el_hueco(tmp_path):
    """Aclaración de 107:RF-14 (P10b) — si falta un formato del grupo, el libro sale con lo que hay: la hoja que falta
    queda como la plantilla oficial, sin nada inventado, y sigue el hueco «F-000 incompleto: falta F-00x». El art.
    30.1 de la RCD 217-2013 forma el grupo con los tres; el regulador observa como incompleto un F-000 a medias (IT
    438-2024, pág. 28) y uno no remitido deja la observación parcialmente subsanada (IT 599-2026, obs. 1.1)."""
    x = _informacion_general(tmp_path, codigos=('F-001', 'F-002'))
    r = escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=_excel_simulado([]),
                                     mapeo=x['mapeo'])
    assert r['F-000'].get('hueco') == 'F-000 incompleto: falta F-003'
    assert r['libro'] is not None and r['libro'].is_file()
    hoja = openpyxl.load_workbook(r['libro'])['F-003']
    assert [(c.coordinate, c.value) for fila in hoja.iter_rows() for c in fila if c.value is not None] == [
        ('A1', 'F-003 de la plantilla')]
    emitidos = emitir(x['carpeta'], x['registro'], celdas=[c for res in x['resultados'] for c in res['celdas']])
    resumen = json.loads(emitidos['resumen'].read_text(encoding='utf-8'))
    assert 'F-000 incompleto: falta F-003' in {h['causa'] for h in resumen['pendientes']}


def test_el_libro_figura_en_la_relacion_del_5_3(tmp_path):
    """Aclaración de 107:RF-14 (P10b) — escrito antes de emitir, el libro de Información General figura en la relación
    de sustento del num. 5.3 con su descripción, su aplicación y su huella; con los tres formatos, el F-000 se cumple."""
    import hashlib

    x = _informacion_general(tmp_path)
    escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=_excel_simulado([]),
                                 mapeo=x['mapeo'])
    salidas = emitir(x['carpeta'], x['registro'], celdas=[c for res in x['resultados'] for c in res['celdas']])
    lista = {r['fichero']: r for r in json.loads(salidas['relacion'].read_text(encoding='utf-8'))}
    assert NOMBRE_IG in lista
    fila = lista[NOMBRE_IG]
    assert 'Información General' in fila['descripcion'] and '30.1' in fila['aplicacion']
    assert fila['sha256'] == hashlib.sha256((x['carpeta'] / NOMBRE_IG).read_bytes()).hexdigest()
    assert _relacion_por_volumenes(salidas)['F-000']['cumplido'] is True


def test_plantilla_oficial_alterada_no_se_usa(tmp_path):
    """Aclaración de 107:RF-14 (P10b) — la plantilla oficial se comprueba con su sha256 antes de copiarla: si no
    coincide con el declarado, se para con el fichero y los dos sha, y no sale ningún libro."""
    x = _informacion_general(tmp_path, sha='0' * 64)
    with pytest.raises(PitError, match='FUENTE ALTERADA'):
        escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=_excel_simulado([]),
                                     mapeo=x['mapeo'])
    assert not (x['carpeta'] / NOMBRE_IG).exists()


def test_plan_de_formatos_no_escribe_sin_saber_donde_insertar(tmp_path):
    """107-P10b — un formato con filas que insertar sin su sitio (un grupo repetido) no se escribe: insertar a ciegas
    pisaría las filas de abajo, y el error lo nombra."""
    from convertersmartgrid.pit.cuadros import plan_de_formatos

    resultado = {'codigo': 'F-101', 'celdas': [], 'filas_a_insertar': {'sistemas:1': 2}, 'insertar_en': [],
                 'grupos_a_insertar': {'sistemas': 1}}
    with pytest.raises(PitError, match='F-101'):
        plan_de_formatos([resultado], modelo=tmp_path / 'm.xls', destino=tmp_path / 'd.xlsx')


def test_el_motor_abre_una_copia_fuera_de_las_fuentes_y_el_original_se_comprueba_dos_veces(tmp_path, monkeypatch):
    """Aclaración de 107:RF-14 (P10b; condición de 28) — el motor recibe una copia en un directorio temporal, fuera de
    la carpeta de fuentes, y el sha256 del original se comprueba dos veces: antes de copiarlo y después de la corrida."""
    import hashlib

    from convertersmartgrid.pit import expediente
    x = _informacion_general(tmp_path)
    comprobados = []

    def sha_contado(ruta):
        comprobados.append(Path(ruta).resolve())
        return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()

    monkeypatch.setattr(expediente, '_sha_de', sha_contado, raising=False)
    pasos = []
    escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=_excel_simulado(pasos),
                                 mapeo=x['mapeo'])
    assert comprobados.count(x['oficial'].resolve()) == 2
    modelo = Path(next(p[1] for p in pasos if p[0] == 'modelo')).resolve()
    assert x['fuentes'].resolve() not in modelo.parents and modelo != x['oficial'].resolve()


def test_original_alterado_durante_la_corrida_es_un_error(tmp_path):
    """Aclaración de 107:RF-14 (P10b; condición de 28) — si el original de la carpeta de fuentes cambia durante la
    corrida, la segunda comprobación de su sha256 lo dice con los dos sha y se para."""
    x = _informacion_general(tmp_path)
    aplicar = _excel_simulado([])

    def excel_que_toca_el_original(orden):
        hecho = aplicar(orden)
        with x['oficial'].open('ab') as f:
            f.write(b'reescrito por el programa de hojas')
        return hecho

    with pytest.raises(PitError, match='FUENTE ALTERADA tras la corrida'):
        escribir_informacion_general(x['carpeta'], x['resultados'], x['fuentes'], ejecutar=excel_que_toca_el_original,
                                     mapeo=x['mapeo'])


# --- Modificación del plan vigente en el expediente (107:RF-17, T25) ------------------------------------------------

def _vigente_y_nuevo(tmp_path):
    vig = _piezas(tmp_path / 'vigente')
    emitir(vig['carpeta'], vig['registro'], celdas=vig['celdas'], diagnostico=vig['diag'], comparacion=vig['comp'],
           programa=vig['prog'])
    nue = _piezas(tmp_path / 'nuevo')
    adelantado = [{**c, 'anio': nue['anios'][0]} if c['elemento'] == nue['nuevo'] else c for c in nue['cambios']]
    return vig, nue, programar(nue['area'], adelantado)


def test_modificacion_en_el_expediente_con_razones_y_mismos_criterios(tmp_path):
    """107:RF-17 — el expediente de la modificación lista lo que cambia del vigente con su razón, y lo rehace con los
    mismos criterios (reglas) que el vigente."""
    vig, nue, prog = _vigente_y_nuevo(tmp_path)
    salidas = emitir(nue['carpeta'], nue['registro'], celdas=nue['celdas'], diagnostico=nue['diag'],
                     comparacion=nue['comp'], programa=prog,
                     modificacion={'vigente': vig['carpeta'], 'razones': {nue['nuevo']: 'se adelanta por la demanda'}})
    mod = json.loads(salidas['modificacion'].read_text(encoding='utf-8'))
    assert [(c['elemento'], c['cambio'], c['razon']) for c in mod['cambios']] == [
        (nue['nuevo'], 'cambia', 'se adelanta por la demanda')]
    assert 'pit.tasa_actualizacion' in mod['criterios_comunes'] and mod['vigente']['area'] == nue['caso']['area']
    assert 'modificacion.json' in {r['fichero'] for r in json.loads(salidas['relacion'].read_text(encoding='utf-8'))}


def test_modificacion_sin_razon_con_otros_criterios_o_sobre_el_vigente_no_se_emite(tmp_path):
    """107:RF-17 — sin la razón de un cambio, con otra tasa que la del vigente, o sobre su misma carpeta, la
    modificación es un error que lo nombra y no escribe nada."""
    vig, nue, prog = _vigente_y_nuevo(tmp_path)
    base = {'celdas': nue['celdas'], 'diagnostico': nue['diag'], 'comparacion': nue['comp'], 'programa': prog}
    with pytest.raises(PitError, match=nue['nuevo']):
        emitir(nue['carpeta'], nue['registro'], **base, modificacion={'vigente': vig['carpeta'], 'razones': {}})
    assert not (nue['carpeta'] / 'cuadros.json').exists()
    normas = _normas()
    normas[0]['reglas'][0] = _regla('pit.tasa_actualizacion', 0.12)
    otra = tmp_path / 'reg_otra'
    otra.mkdir()
    (otra / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': normas}), encoding='utf-8')
    with pytest.raises(PitError, match='pit.tasa_actualizacion'):
        emitir(nue['carpeta'], cargar_registro(otra), **base,
               modificacion={'vigente': vig['carpeta'], 'razones': {nue['nuevo']: 'x'}})
    with pytest.raises(PitError, match='expediente nuevo'):
        emitir(vig['carpeta'], vig['registro'], **base, modificacion={'vigente': vig['carpeta'], 'razones': {}})
