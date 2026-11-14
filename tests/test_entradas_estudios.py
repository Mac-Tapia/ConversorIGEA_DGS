"""Spec 012, RF-73 a RF-86: las entradas que faltan a los estudios, cargadas desde la web.

Usuario, 2026-11-13: «lo que falta se ingresará en TXT o en imagen» y «todo tiene que ser
cargado desde la web». Las tablas de prueba se escriben aquí, sorteadas: ninguna cifra, SET ni
moneda es de una empresa (constitución P13). La imagen se dibuja con Pillow y se lee con el OCR
de Tesseract si está instalado.
"""
from __future__ import annotations

import math
import random

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apoyo import cargar_herramienta
from convertersmartgrid import entradas_estudios as ee
from convertersmartgrid.estudios_pf import estudios_no_ofrecidos, estudios_ofrecidos, validar_estudios
from convertersmartgrid.studies import ESTUDIOS

SEMILLAS = [random.randrange(10**6) for _ in range(3)]
SEPARADORES = ('\t', ';', '|')


def _nombres(rng, n):
    return [f'S{rng.randrange(10**4)}_{i}' for i in range(n)]


def _tabla_pcc(rng, sep, barras):
    filas = [sep.join(['SET o barra de cabecera', 'Tensión (kV)', 'Pcc máxima (MVA)', 'R/X máxima', 'Pcc mínima (MVA)'])]
    datos = {}
    for b in barras:
        smax = round(rng.uniform(50, 2000), 2)
        smin = round(smax * rng.uniform(0.3, 0.95), 2)
        rx = round(rng.uniform(0.05, 0.9), 3)
        datos[b] = (smax, rx, smin)
        filas.append(sep.join([b, '10', f'{smax}'.replace('.', ','), f'{rx}', f'{smin}']))
    return '\n'.join(filas), datos


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_pcc_se_lee_con_cualquier_separador(semilla):
    """012:RF-73, 012:RF-76 — la tabla de Pcc se lee con tabulador, «;» o «|» y coma decimal."""
    rng = random.Random(semilla)
    barras = _nombres(rng, rng.randint(1, 6))
    texto, datos = _tabla_pcc(rng, rng.choice(SEPARADORES), barras)
    lec = ee.leer_entrada('impedancia', texto, fichero='pcc.txt')
    assert lec.errores == [], (semilla, lec.errores)
    g = ee.guardable('impedancia', lec.filas)
    assert g['completa'] and g['faltan'] == []
    for b, (smax, rx, smin) in datos.items():
        d = g['registro']['barras'][ee._norm(b)]
        assert math.isclose(d['scc_max_mva'], smax) and math.isclose(d['rx_max'], rx)
        assert math.isclose(d['scc_min_mva'], smin)


def test_pcc_desde_la_corriente_y_sin_minima():
    """012:RF-86, 012:RF-78 — Ik" con la tensión da la Pcc (√3·U·Ik); sin mínima se dice, sin bloquear."""
    texto = 'SET   Tensión (kV)   Ik" máxima (kA)   R/X máxima\nCABA   22,9   7,5   0,2\n'
    lec = ee.leer_entrada('impedancia', texto)
    assert lec.errores == []
    g = ee.guardable('impedancia', lec.filas)
    assert math.isclose(g['registro']['barras']['caba']['scc_max_mva'], math.sqrt(3) * 22.9 * 7.5, rel_tol=1e-6)
    assert g['completa'] and any('mínima de CABA' in f for f in g['faltan'])


def test_lo_que_falta_se_dice_y_no_se_completa():
    """012:RF-78 — sin R/X, sin unidad o con la unidad cambiada: error con su fila, nada supuesto."""
    sin_rx = ee.leer_entrada('impedancia', 'SET;Pcc máxima (MVA)\nA1;300\n')
    assert any('R/X' in e and 'Fila 1' in e for e in sin_rx.errores)
    with pytest.raises(ee.EntradasError):
        ee.guardable('impedancia', sin_rx.filas)
    kva = ee.leer_entrada('impedancia', 'SET;Pcc máxima (kVA);R/X máxima\nA1;300000;0,1\n')
    assert any('kva' in e for e in kva.errores)
    perfil = ee.leer_entrada('perfiles', 'Hora;AL1\n' + ''.join(f'{h};{h + 1}\n' for h in range(24)))
    assert any('unidad' in e for e in perfil.errores)
    assert ee.leer_entrada('perfiles', '').errores


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_perfiles_en_columnas_o_en_filas(semilla):
    """012:RF-73, 012:RF-76 — perfiles horarios en columnas y de 15 minutos en filas, cada uno con su unidad."""
    rng = random.Random(semilla)
    nombres = _nombres(rng, rng.randint(1, 4))
    ancha = 'Hora\t' + '\t'.join(f'{n} (kW)' for n in nombres) + '\n' + ''.join(
        f'{h}\t' + '\t'.join(f'{rng.uniform(1, 900):.2f}' for _ in nombres) + '\n' for h in range(24))
    g = ee.guardable('perfiles', ee.leer_entrada('perfiles', ancha).filas)
    assert set(g['registro']['perfiles']) == {ee._norm(n) for n in nombres}
    for p in g['registro']['perfiles'].values():
        assert p['paso_min'] == 60 and len(p['valores']) == 24 and max(p['pu']) == 1.0 and p['unidad'] == 'kW'
    larga = 'perfil;instante;valor;unidad\n' + ''.join(
        f'{nombres[0]};{h:02d}:{m:02d};{rng.uniform(0.1, 1):.3f};p.u.\n' for h in range(24) for m in (0, 15, 30, 45))
    p = ee.guardable('perfiles', ee.leer_entrada('perfiles', larga).filas)['registro']['perfiles'][ee._norm(nombres[0])]
    assert p['paso_min'] == 15 and len(p['pu']) == 96 and p['horas'] == 24


def test_perfil_con_paso_irregular_no_se_guarda():
    """012:RF-77, 012:RF-78 — un instante que falta deja el paso irregular: no se guarda nada."""
    texto = 'Hora;AL1 (kW)\n' + ''.join(f'{h};{h + 1}\n' for h in range(24) if h != 7)
    with pytest.raises(ee.EntradasError) as e:
        ee.guardable('perfiles', ee.leer_entrada('perfiles', texto).filas)
    assert 'paso' in str(e.value)


def test_tasas_tiempos_y_costes_con_las_reglas_del_libro():
    """012:RF-81 — tasas, tiempos y costes cargados valen como las hojas del libro de la empresa."""
    from convertersmartgrid.datos_empresa import CLASES, que_falta

    tasas = 'Clase;Falla permanente (1/año);Tiempo de reparación (h)\n' + ''.join(
        f'{v};0,{i + 1};{i + 2}\n' for i, v in enumerate(CLASES.values()))
    tiempos = 'Concepto;Valor (min)\nLocalización de la falla;30\nManiobra manual;45\n'
    costes = 'Concepto;Valor;Unidad\nEnergía de pérdidas;0,5;XYZ/kWh\nTasa de descuento;9;%\n'
    g = {k: ee.guardable(k, ee.leer_entrada(k, t).filas)
         for k, t in (('tasas', tasas), ('maniobra', tiempos), ('coste_energia', costes))}
    libro = ee.combinar_con_libro(None, g)
    assert que_falta(libro, 'fiabilidad') == [] and que_falta(libro, 'reconectadores') == []
    assert libro.moneda == 'XYZ' and math.isclose(libro.tasa_descuento, 0.09)
    assert que_falta(libro, 'condensadores') == ['la hoja «Bancos de condensadores»']
    mala = ee.leer_entrada('tasas', 'Clase;Falla permanente;Tiempo de reparación\nMotor;1;2\n')
    assert any('no es una clase conocida' in e for e in mala.errores)
    assert ee.combinar_con_libro(None, {}) is None


def test_precios_etapas_proyeccion_y_espectros():
    """012:RF-73, 012:RF-78 — las entradas de la económica y de los armónicos, con lo que les falta."""
    precios = ee.guardable('precios', ee.leer_entrada(
        'precios', 'Elemento;Unidad;Precio unitario;Moneda\nConductor 70 mm2;km;1234,5;XYZ\n').filas)
    assert precios['completa'] and precios['registro']['precios'][0]['precio'] == 1234.5
    una = ee.guardable('etapas', ee.leer_entrada(
        'etapas', 'Alternativa;Año;Obra;Inversión;Moneda\nA;2027;Banco;100;XYZ\nA;2029;Recalibrado;300;XYZ\n').filas)
    assert una['completa'] and 'segunda alternativa' in una['faltan'][0]
    proy = ee.guardable('proyeccion', ee.leer_entrada('proyeccion', 'Alimentador;Año;Demanda (kW)\nX1;2027;900\n').filas)
    assert proy['registro']['proyeccion'] == {'X1': {'2027': 900.0}}
    esp = ee.leer_entrada('espectros', 'Tipo de carga;Orden armónico;Magnitud (%)\nVariador;5;30\nVariador;5,5;10\n')
    assert any('no es un orden entero' in e for e in esp.errores)


def test_catalogo_ofrece_con_lo_cargado():
    """012:RF-79, 012:RF-80 — lo guardado deja de faltar; cortocircuito y cuasi-dinámica pasan a ofrecerse."""
    sin = {e['clave']: e for e in estudios_no_ofrecidos()}
    assert 'cortocircuito' in sin and 'Potencia e impedancia' in sin['cortocircuito']['motivo']
    g = {'impedancia': ee.guardable('impedancia', ee.leer_entrada(
        'impedancia', 'SET;Pcc máxima (MVA);R/X máxima\nA1;300;0,1\n').filas),
         'perfiles': ee.guardable('perfiles', ee.leer_entrada(
             'perfiles', 'Hora;A1 (kW)\n' + ''.join(f'{h};{h + 1}\n' for h in range(24))).filas),
         'espectros': ee.guardable('espectros', ee.leer_entrada(
             'espectros', 'Tipo de carga;Orden armónico;Magnitud (%)\nVariador;5;30\n').filas)}
    cargadas = ee.cumplidas(g)
    ofrecidos = {e.clave for e in estudios_ofrecidos(entradas=cargadas)}
    assert {'cortocircuito', 'cuasi_dinamica'} <= ofrecidos
    no = {e['clave']: e for e in estudios_no_ofrecidos(entradas=cargadas)}
    assert 'siguiente iteración' in no['armonicos']['motivo'] and no['armonicos']['falta'] == []
    assert no['economico']['falta'] and 'cortocircuito' not in no
    assert validar_estudios(['cortocircuito'], entradas=cargadas) == ('cortocircuito',)
    assert 'protecciones' in no                       # le siguen faltando sus dispositivos


def test_cada_entrada_nombra_una_del_catalogo():
    """012:RF-79 — el nombre de cada esquema es el ``Entrada.nombre`` de ``studies.py``."""
    nombres = {x.nombre for e in ESTUDIOS for x in e.entradas}
    assert {e.nombre for e in ee.ESQUEMAS.values()} <= nombres
    publico = {e['clave']: e for e in ee.esquemas_publicos()}
    assert 'cortocircuito' in publico['impedancia']['estudios'] and 'armonicos' in publico['espectros']['estudios']


def test_imagen_por_ocr(tmp_path):
    """012:RF-74 — una foto de la tabla se lee por OCR y da las mismas filas que el TXT."""
    from PIL import Image, ImageDraw, ImageFont

    from convertersmartgrid import documentos_solicitud as ds

    if not ds.tesseract():
        pytest.skip('sin Tesseract en este equipo')
    try:
        letra = ImageFont.truetype('arial.ttf', 40)
    except OSError:
        letra = ImageFont.load_default()
    lineas = ['SET      Pcc_max (MVA)      R/X_max', 'BARRA1      450      0.15', 'BARRA2      320      0.25']
    img = Image.new('RGB', (1400, 60 + 80 * len(lineas)), 'white')
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lineas):
        d.text((40, 30 + 80 * i), ln, fill='black', font=letra)
    png = tmp_path / 'tabla.png'
    img.save(png)
    texto, metodo, avisos = ee.texto_de(png)
    assert metodo == 'ocr' and avisos
    g = ee.guardable('impedancia', ee.leer_entrada('impedancia', texto, metodo=metodo).filas)
    assert g['registro']['barras']['barra1']['scc_max_mva'] == 450.0
    assert g['registro']['barras']['barra2']['rx_max'] == 0.25


# --------------------------------------------------------------------------- web
@pytest.fixture
def cliente(tmp_path):
    from convertersmartgrid.web.entradas_estudios_api import registrar_rutas_entradas
    from convertersmartgrid.web.jobs import Job, JobContext
    from convertersmartgrid.web.workspace import WorkspaceStore

    ws = WorkspaceStore(tmp_path / 'web').create()

    def submit(w, kind, title, fn, *, lane='engine'):
        job = Job(kind, title, w.id, lane, fn)
        job.result, job.status = fn(JobContext(job, lambda *a: None)), 'done'
        return job.public()

    def guardar(destino, subida):
        destino.write_bytes(subida.file.read())

    app = FastAPI()
    registrar_rutas_entradas(app, ws_or_404=lambda wid: ws, submit=submit, guardar_subida=guardar)
    with TestClient(app) as c:
        yield c, ws


def test_web_leer_corregir_y_guardar(cliente):
    """012:RF-75, 012:RF-77, 012:RF-82 — subir deja un borrador; guardar lo corregido lo da por cumplido."""
    c, ws = cliente
    base = f'/api/workspaces/{ws.id}/pf/entradas-estudios'
    r = c.post(base + '/impedancia/leer', data={'project': 'P1'},
               files=[('files', ('pcc.txt', 'SET;Pcc máxima (MVA);R/X máxima\nA1;300;\nA2;250;0,2\n'.encode(), 'text/plain'))])
    assert r.status_code == 202 and r.json()['result']['errores'] == 1
    estado = c.get(base, params={'project': 'P1'}).json()
    borrador = estado['borradores']['impedancia']
    assert estado['cumplidas'] == [] and len(borrador['filas']) == 2
    mal = c.put(base + '/impedancia', json={'project': 'P1', 'filas': borrador['filas']})
    assert mal.status_code == 400 and 'R/X' in mal.json()['detail']
    filas = [dict(f) for f in borrador['filas']]
    filas[0]['rx_max'] = '0,1'                                 # el operador corrige la celda
    bien = c.put(base + '/impedancia', json={'project': 'P1', 'filas': filas}).json()
    assert bien['cumplidas'] == [ee.ESQUEMAS['impedancia'].nombre] and 'impedancia' not in bien['borradores']
    carpeta = ws.root / 'entradas_estudios' / 'P1'
    assert (carpeta / 'impedancia.json').is_file() and any((carpeta / 'originales').iterdir())
    from convertersmartgrid.web.entradas_estudios_api import entradas_cargadas, registros_para_plan

    assert entradas_cargadas(ws, 'P1') == {ee.ESQUEMAS['impedancia'].nombre} and entradas_cargadas(ws, 'P2') == set()
    assert registros_para_plan(ws, 'P1')['impedancia']['registro']['barras']['a1']['rx_max'] == 0.1


def test_web_rechaza_lo_que_no_se_lee(cliente):
    """012:RF-73 — solo TXT, CSV, PDF o imágenes; una entrada que no existe, 404."""
    c, ws = cliente
    base = f'/api/workspaces/{ws.id}/pf/entradas-estudios'
    r = c.post(base + '/impedancia/leer', data={'project': 'P1'}, files=[('files', ('x.exe', b'MZ', 'application/octet-stream'))])
    assert r.status_code == 400
    assert c.put(base + '/protecciones', json={'project': 'P1', 'filas': []}).status_code == 404
    assert c.delete(base + '/impedancia/borrador', params={'project': 'P1'}).status_code == 200


# --------------------------------------------------------------------------- guion
class _Obj:
    def __init__(self, nombre, clase='ElmTerm', padre=None, **attrs):
        self.loc_name, self._clase, self._padre = nombre, clase, padre
        self.__dict__.update(attrs)

    def GetClassName(self):
        return self._clase

    def GetParent(self):
        return self._padre


def test_red_externa_se_reconoce_por_su_alimentador_o_su_set():
    """012:RF-83, 012:RF-85 — la fila de la SET o del alimentador encuentra su red externa; sin fila, falta."""
    guion = cargar_herramienta('estudios_entradas_pf.py', tools_en_path=True)
    set_ = _Obj('SET_X', 'ElmSubstat')
    term = _Obj('NODE_1', padre=set_)
    x = _Obj('External Grid AL7', 'ElmXnet', bus1=_Obj('cub', 'StaCubic', cterm=term))
    reg = ee.guardable('impedancia', ee.leer_entrada('impedancia', 'SET;Pcc máxima (MVA);R/X máxima\nSET_X;300;0,1\n').filas)
    assert ee.impedancia_para(reg['registro'], guion.nombres_xnet(x))['scc_max_mva'] == 300
    assert 'AL7' in guion.nombres_xnet(x)
    assert ee.atributos_xnet(reg['registro']['barras'][ee._norm('SET_X')]) == {'snss': 300.0, 'rntxn': 0.1}
    otro = _Obj('External Grid AL8', 'ElmXnet', bus1=None)
    assert ee.impedancia_para(reg['registro'], guion.nombres_xnet(otro)) is None


def test_guion_sin_datos_no_estudia():
    """012:RF-83, 012:RF-84, 012:RF-85 — sin Pcc ni perfiles cargados, el guion dice qué falta y no toca la red."""
    guion = cargar_herramienta('estudios_entradas_pf.py', tools_en_path=True)
    informe = {'avisos': []}
    assert 'potencia de cortocircuito' in guion.cortocircuito(None, {}, None, [], informe)
    assert 'perfiles' in guion.cuasi_dinamica(None, {}, None, [], informe)
    largo = {'entradas': {'perfiles': {'registro': {'perfiles': {'a': {'perfil': 'A', 'horas': 48}}}}}}
    assert 'un día' in guion.cuasi_dinamica(None, largo, None, [], informe)
