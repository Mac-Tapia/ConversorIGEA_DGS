"""Spec 107, P10c — el expediente del PIT se arma de punta a punta (107:RF-1 a RF-9, RF-13, RF-14; aclaración de
RF-5): red, diagnóstico, alternativas con sus costos vigentes, programa, cuadros, F-001 a F-003, libro F-000 y
emisión. Todo sintético: perfil y red sorteados, libro de módulos, libro «oficial» y Excel simulado con openpyxl."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from datos_pit import perfil_a
from test_pit_formatos import NORMATIVA

from convertersmartgrid.dominio.pit import PitError
from convertersmartgrid.adaptadores.pit.armado import armar_expediente, leer_alternativas
from convertersmartgrid.adaptadores.pit.expediente import TIPO_DIAGNOSTICO, TIPO_ESTUDIO, emitir
from convertersmartgrid.adaptadores.pit.plantillas import cargar_mapeo
from convertersmartgrid.dominio.registro_normativo import cargar_registro

COLUMNAS = {'codigo': 'Código Módulo', 'nombre': 'Descripción', 'unidad': 'Unidad', 'total': 'Costo Total'}


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _excel(orden):
    """Aplica el plan con openpyxl: inserta las filas y escribe las celdas, como el guion de Excel."""
    plan = json.loads(Path(re.search(r"-LiteralPath '([^']+)'", orden).group(1)).read_text(encoding='utf-8'))
    libro = openpyxl.load_workbook(plan['modelo'])
    for i in plan.get('insertar_filas') or ():
        libro[i['hoja']].insert_rows(i['fila'], i['filas'])
    for e in plan['escribir']:
        hoja, celda = e['celda'].rsplit('!', 1)
        libro[hoja][celda] = e['valor']
    libro.save(plan['destino'])
    return SimpleNamespace(returncode=0, stderr='')


def _caso(tmp_path, *, vigencia='2000-01-01'):
    """Espacio con el libro de la red y el de módulos, perfil con ``pit.costos``, registro real más las reglas
    económicas sintéticas, carpeta de fuentes con un libro «oficial» y su sha en el alias, y una alternativa."""
    caso = perfil_a(27)
    claves = sorted({k for e in caso['elementos'] for k in e})
    espacio = tmp_path / 'ws1'
    (espacio / 'costos').mkdir(parents=True)
    red = openpyxl.Workbook()
    hoja = red.active
    hoja.title = 'Red'
    hoja.append(claves)
    for e in caso['elementos']:
        hoja.append([', '.join(e[k]) if isinstance(e.get(k), list) else e.get(k) for k in claves])
    red.save(espacio / 'red.xlsx')
    modulos = openpyxl.Workbook()
    hoja = modulos.active
    hoja.title = 'Resumen'
    hoja.append(list(COLUMNAS.values()))
    hoja.append(['TP-S', 'Transformador sintético', 'u', 500.0])
    modulos.save(espacio / 'costos' / 'modulos.xlsx')
    perfil = copy.deepcopy(caso['perfil'])
    perfil['pit'].update(
        libro_red={'hoja': 'Red', 'columnas': {k: k for k in claves}},
        limites={'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100},
        costos={'transmision': [{'lector': 'modulos_transmision', 'fichero': 'costos/modulos.xlsx',
                                 'sha256': _sha(espacio / 'costos' / 'modulos.xlsx'), 'vigencia_desde': vigencia,
                                 'resolucion': 'SINT-COSTOS', 'anio': 2001, 'moneda': 'XTS',
                                 'url': 'https://ejemplo.invalid', 'fecha_descarga': '2001-01-01',
                                 'columnas': COLUMNAS, 'hoja': 'Resumen'}]})
    extra = tmp_path / 'reglas'
    extra.mkdir()

    def regla(clave, valor):
        return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave}»', 'pagina': '1'}

    # El registro real ya trae estas tres claves (la DL 25844, la RCD 217-2013 y la RCD 163-2021, desde P-REG y S1).
    # Desde RN-AMB, dos normas vigentes a la vez con la misma clave son ambiguas si la más reciente no modifica a la
    # otra: la sintética es la más reciente y las modifica, como una modificatoria publicada (RN-AMB, 107:RF-7).
    (extra / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT-ECO', 'titulo': 'Reglas económicas sintéticas', 'estado_juridico': 'vigente_comprobada',
         'sha256': 'a' * 64, 'vigencia_desde': '2022-01-01',
         'modifica': ['DL 25844', 'RCD 217-2013-OS/CD', 'RCD 163-2021-OS/CD'],
         'reglas': [regla('pit.tasa_actualizacion', 0.12), regla('pit.vida_util_anios', 30),
                    regla('pit.coym_pct', 2.0)]}]}), encoding='utf-8')
    fuentes = tmp_path / 'fuentes'
    (fuentes / 'libros').mkdir(parents=True)
    oficial = openpyxl.Workbook()
    oficial.active.title = 'F-001'
    oficial.create_sheet('F-002')
    oficial.create_sheet('F-003')
    oficial.save(fuentes / 'libros' / 'informacion_general.xlsx')
    mapeo = copy.deepcopy(cargar_mapeo())
    mapeo['alias']['F-000']['plantilla_oficial'] = {
        'ruta_relativa': 'libros/informacion_general.xlsx',
        'sha256': _sha(fuentes / 'libros' / 'informacion_general.xlsx')}
    t = next(e for e in caso['elementos'] if e.get('tipo') == 'trafo2')
    anios = caso['anios'][:2]
    alternativas = {'alternativas': [{'nombre': 'refuerzo', 'cambios': [
        {'accion': 'alta', 'elemento': {**t, 'id': f'{t["id"]}-2'},
         'costo': {'codigo': 'TP-S', 'cantidad': 1, 'unidad': 'u'}, 'anio': anios[1], 'titular': t['titular'],
         'instalacion': t['set'], 'descripcion': 'Transformador en paralelo'}]}]}
    return {'caso': caso, 'espacio': espacio, 'perfil': perfil, 'registro': cargar_registro(NORMATIVA, extra),
            'fuentes': fuentes, 'mapeo': mapeo, 'anios': anios, 'alternativas': alternativas}


def _armar(x, **cambios):
    pedido = dict(area=x['caso']['area'], periodo='2025-2029', anios=x['anios'], libro_red=x['espacio'] / 'red.xlsx',
                  proyeccion=x['caso']['proyeccion'], fecha_apertura='2001-06-01', fuentes=x['fuentes'],
                  ejecutar=_excel, mapeo=x['mapeo'], alternativas=x['alternativas'], alternativa_elegida='refuerzo')
    pedido.update(cambios)
    return armar_expediente(x['espacio'], x['perfil'], x['registro'], **pedido)


def test_expediente_de_punta_a_punta_con_el_f000_dentro(tmp_path):
    """107:RF-1 a RF-9, RF-13 y RF-14 (P10c) — con alternativas y costos vigentes, el expediente sale como estudio:
    diagnóstico, comparación, programa, cuadros, resumen ejecutivo, F-001 a F-003 y el libro F-000-<área>_<periodo>
    en la carpeta, que figura en la relación del num. 5.3, con el F-000 cumplido."""
    x = _caso(tmp_path)
    r = _armar(x)
    assert r['tipo'] == TIPO_ESTUDIO
    assert {'diagnostico', 'alternativas', 'programa', 'cuadros', 'resumen_ejecutivo', 'relacion'} <= set(r['salidas'])
    nombre = f'F-000-{x["caso"]["area"]}_2025-2029.xlsx'
    assert r['libro_f000']['nombre'] == nombre and Path(r['libro_f000']['libro']).is_file()
    relacion = {f['fichero'] for f in json.loads(Path(r['salidas']['relacion']).read_text(encoding='utf-8'))}
    assert nombre in relacion
    documentos = json.loads(Path(r['salidas']['relacion_documentos']).read_text(encoding='utf-8'))
    assert documentos['F-000']['cumplido'] is True
    cuadros = {c['cuadro'] for c in json.loads(Path(r['salidas']['cuadros']).read_text(encoding='utf-8'))}
    assert {'F-001', 'F-002', 'F-003'} <= cuadros


def test_sin_alternativas_es_de_diagnostico_y_nunca_completo(tmp_path):
    """Aclaración de 107:RF-5 (P10c; condición de 28) — sin alternativas, el expediente sale «DE DIAGNÓSTICO, no
    presentable a Osinergmin», en el resumen y en el resultado, con su pendiente; y no sale completo ni siquiera
    cuando la relación ya no tiene ningún hueco."""
    x = _caso(tmp_path)
    r = _armar(x, alternativas=None, alternativa_elegida=None)
    assert r['tipo'] == TIPO_DIAGNOSTICO == 'DE DIAGNÓSTICO, no presentable a Osinergmin'
    assert r['estado'] == 'incompleto'
    assert 'sin alternativas: no hay comparación ni programa' in {p['causa'] for p in r['pendientes']}
    resumen = json.loads(Path(r['salidas']['resumen']).read_text(encoding='utf-8'))
    assert resumen['tipo'] == TIPO_DIAGNOSTICO
    # Con todos los documentos en un volumen y con sus folios, la relación queda sin huecos: sigue sin ser completo.
    carpeta = Path(r['carpeta'])
    nombres = [f['fichero'] for f in json.loads(Path(r['salidas']['relacion']).read_text(encoding='utf-8'))]
    volumenes = {'volumenes': [{'volumen': 'I', 'titulo': 'Único'}],
                 'documentos': {n: {'volumen': 'I', 'folios': 1} for n in [*nombres, 'relacion_documentos.json']}}
    celdas = json.loads((carpeta / 'cuadros.json').read_text(encoding='utf-8'))
    salidas = emitir(carpeta, x['registro'], celdas=celdas, volumenes=volumenes)
    assert json.loads(salidas['relacion_documentos'].read_text(encoding='utf-8'))['completa'] is True
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    assert resumen['tipo'] == TIPO_DIAGNOSTICO and resumen['estado'] == 'incompleto'
    assert [p['campo'] for p in resumen['pendientes']] == ['alternativas']


@pytest.mark.parametrize('cambio, campo', [
    (lambda a: a['alternativas'][0]['cambios'][0]['costo'].update(cantidad=0),
     'alternativas[0].cambios[0].costo.cantidad'),
    (lambda a: a['alternativas'][0]['cambios'][0].pop('anio'), 'alternativas[0].cambios[0].anio'),
    (lambda a: a['alternativas'][0]['cambios'][0].update(accion='mueve'), 'alternativas[0].cambios[0].accion'),
    (lambda a: a['alternativas'][0]['cambios'][0].pop('descripcion'), 'alternativas[0].cambios[0].descripcion'),
    (lambda a: a['alternativas'].append(copy.deepcopy(a['alternativas'][0])), 'alternativas[1].nombre'),
])
def test_alternativas_mal_formadas_nombran_el_campo(tmp_path, cambio, campo):
    """Aclaración de 107:RF-5 (P10c) — el JSON de alternativas se valida campo a campo: el primero que falla es un
    error que lo nombra, con su ruta en el JSON."""
    alternativas = copy.deepcopy(_caso(tmp_path)['alternativas'])
    cambio(alternativas)
    with pytest.raises(PitError, match=re.escape(campo)):
        leer_alternativas(alternativas)


def test_sin_costos_vigentes_no_hay_comparacion_y_se_dice(tmp_path):
    """Aclaración de 107:RF-5 (P10c) — los costos van por vigencia (ficheros reemplazables por periodo): sin una
    fuente vigente en la fecha de apertura no se comparan las alternativas, el expediente sale de diagnóstico y el
    pendiente nombra el ámbito."""
    x = _caso(tmp_path, vigencia='2030-01-01')
    r = _armar(x)
    assert r['tipo'] == TIPO_DIAGNOSTICO
    assert any('pit.costos.transmision' in p and 'vigente' in p for p in r['pendientes_del_armado'])
    assert 'alternativas' not in r['salidas']


def test_costos_con_otro_sha_no_se_leen(tmp_path):
    """Aclaración de 107:RF-5 (P10c) — el fichero de costos se comprueba con el sha256 del perfil antes de leerlo:
    si no cuadra, es un error que lo dice y no se arma nada con él."""
    x = _caso(tmp_path)
    x['perfil']['pit']['costos']['transmision'][0]['sha256'] = '0' * 64
    with pytest.raises(PitError, match='sha256'):
        _armar(x)


def test_sin_carpeta_de_fuentes_no_sale_el_f000_y_se_dice(tmp_path):
    """Aclaración de 107:RF-14 (P10c) — sin carpeta de fuentes normativas no hay plantilla oficial: el libro F-000 no
    sale y el resultado dice por qué y qué variable falta; el expediente se emite igual."""
    x = _caso(tmp_path)
    r = _armar(x, fuentes=None)
    assert r['libro_f000']['libro'] is None and 'CSG_FUENTES_NORMATIVAS' in r['libro_f000']['motivo']
    assert 'resumen' in r['salidas']


def test_doctor_dice_si_falta_la_carpeta_de_fuentes_o_el_sha_no_cuadra(tmp_path):
    """107-P10c (condición de 28) — el doctor dice si falta CSG_FUENTES_NORMATIVAS y si el libro oficial de esa
    carpeta no cuadra con su sha256; con los dos bien, en verde."""
    from convertersmartgrid.presentacion.web.doctor import _fuentes_normativas
    x = _caso(tmp_path)
    sin = _fuentes_normativas({}, x['mapeo'])
    assert sin.ok is False and 'CSG_FUENTES_NORMATIVAS' in sin.detalle and sin.arreglo
    bien = _fuentes_normativas({'CSG_FUENTES_NORMATIVAS': str(x['fuentes'])}, x['mapeo'])
    assert bien.ok is True
    otro = copy.deepcopy(x['mapeo'])
    otro['alias']['F-000']['plantilla_oficial']['sha256'] = '0' * 64
    mal = _fuentes_normativas({'CSG_FUENTES_NORMATIVAS': str(x['fuentes'])}, otro)
    assert mal.ok is False and 'sha256' in mal.detalle and '0' * 64 in mal.detalle
