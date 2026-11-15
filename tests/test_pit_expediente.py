"""Spec 107 T10 — expediente y cuadros: carpeta aparte, instantánea, traza de cada celda, modificatoria posterior y
determinismo (107:RF-1, 107:RF-7, 107:RF-8, 107:RF-9). Todo sintético: registro, costos y área sorteada."""
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
from convertersmartgrid.pit.expediente import abrir, comprobar_modificatoria, emitir, filas_del_programa
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
