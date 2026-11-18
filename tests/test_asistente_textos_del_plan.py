"""Lo que el operador lee del plan del asistente no cita requisitos ni nombres internos (070:RF-51).

La consola de la web enseña ``faltan``, ``dudas``, ``razonamiento`` y ``avisos`` tal cual: el plan del largo plazo
terminaba en «Dígalo en la orden (072:RF-29).» y el del PIDE nombraba «planificacion.anio_presentacion». La cita va
en el comentario del código y en el registro, nunca en el texto. Esta prueba arma el plan de cada tarea del catálogo
por la ruta real de la web, con dos espacios (calibrado y sin calibrar), y falla con el primer texto que cite o use jerga.
"""
from __future__ import annotations

import re
import sys
import time

import pytest

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient

from convertersmartgrid.aplicacion.asistente.tareas import TAREAS
from convertersmartgrid.presentacion.web import services
from convertersmartgrid.presentacion.web.app import create_app

#: Un valor de ejemplo por tipo de dato, inventado y de ninguna empresa (P13).
EJEMPLO = {'proyecto': 'Ensayo Alfa', 'alimentadores': 'QX511', 'sistema': 'Meseta', 'periodo': '2026-07', 'sed': 'SX4411',
           'subtipo': 'mejora de tensión', 'texto': 'el reparto de la demanda', 'set': 'SET Quinua', 'numero': '5',
           'estudio': 'tension', 'alcance': 'alimentadores', 'anio': '2027', 'caso': 'Caso base'}
VOCABULARIO = {'proyecto': ['Ensayo Alfa'], 'alimentadores': ['QX511'], 'sistema': ['Meseta'], 'set': ['SET Quinua']}

#: Una cita de requisito o de spec: «(072:RF-29)», «RF-8», «spec 017», «T13».
_CITA = re.compile(r'\b\d{3}\s*:\s*RF-\d+|\bRF-\d+\b|\bspecs?\s+\d{3}\b|\bT\d+[a-z]?\b', re.IGNORECASE)
#: Un nombre interno: ``claves_con_guion_bajo``, ``seccion.clave`` o texto entre comillas de código.
_INTERNO = re.compile(r'`|(?<![\w/\\.:-])[a-z]+(?:_[a-z0-9]+)+(?![\w/\\.-])|\b[a-z]+\.[a-z]+_[a-z_]+\b')
#: Lo que no es texto del plan sino un dato: rutas y ficheros, que pueden llevar guiones bajos.
_RUTA = re.compile(r'[A-Za-z]:[\\/]\S*|\S+\.(?:json|xlsx|xls|csv|txt|docx|pdf|mdb|bak|dgs|zip)\b')


class Modelo:
    """El modelo de órdenes, sustituido: dice la tarea pedida con un dato de ejemplo de cada uno de sus tipos."""

    def __init__(self, tarea):
        self.tarea, self.tareas = tarea, (tarea,)
        self.datos = {d.tipo: [{'valor': EJEMPLO[d.tipo]}] for d in TAREAS[tarea].datos if d.tipo in EJEMPLO}

    def predecir(self, texto):
        return {'tarea': self.tarea, 'confianza': 1.0, 'datos': self.datos}


def _orden(tarea: str) -> str:
    """La primera plantilla de la tarea, con la primera variante y el dato de ejemplo."""
    texto = re.sub(r'\[([^|\]]*)[^\]]*\]', r'\1', TAREAS[tarea].plantillas[0])
    return re.sub(r'\{(\w+)\}', lambda m: EJEMPLO.get(m.group(1), m.group(1)), texto)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda ws: VOCABULARIO)
    # Lo que se comprueba es el PLAN; la respuesta de las consultas («pregunta» carga el índice y los pesos del reranker,
    # «buscar_internet» sale a la red) va aparte en el resultado y no se mira aquí. Se sustituye, como el modelo de órdenes,
    # para que la prueba no dependa de lo que tarde la máquina en cargar modelos (P4 v2: en la puerta de 7d, la primera
    # carga de pesos agotó la espera de «pregunta»).
    monkeypatch.setattr(services, '_asistente_respuesta', lambda ws, plan, trabajos: {'texto': 'respuesta sustituida'})
    services._ASISTENTE_PLANES.clear()
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app
    services._ASISTENTE_PLANES.clear()


#: El reloj de la espera; una prueba lo sustituye para simular una carga lenta sin esperarla de verdad.
_RELOJ = time.monotonic
#: Tope holgado de la espera: con el modelo y las respuestas sustituidos, armar un plan tarda décimas de segundo. Solo
#: evita colgar la suite si la cola se rompe; se cuenta desde ANTES de mandar la orden.
PLAZO_S = 30


def _plan(cliente, wid, monkeypatch, tarea) -> dict:
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Modelo(tarea), None))
    limite = _RELOJ() + PLAZO_S
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': _orden(tarea)})
    assert r.status_code == 202, (tarea, r.text)
    estado = 'sin consultar'
    while _RELOJ() < limite:
        fin = cliente.get(f"/api/jobs/{r.json()['id']}").json()
        estado = fin['status']
        if estado in ('done', 'failed', 'cancelled'):
            assert estado == 'done', (tarea, fin.get('error'))
            return fin['result']['plan']
        time.sleep(0.02)
    pytest.fail(f'{tarea}: la cola no terminó en {PLAZO_S} s; el trabajo quedó en estado «{estado}»')


def _jerga(texto: str) -> list[str]:
    limpio = _RUTA.sub(' ', texto)
    return [m.group(0) for p in (_CITA, _INTERNO) for m in p.finditer(limpio)]


@pytest.mark.parametrize('calibrado', [True, False], ids=['calibrado', 'sin_calibrar'])
def test_ningun_plan_cita_requisitos_ni_usa_nombres_internos(api, monkeypatch, calibrado):
    """070:RF-51 — los faltantes, dudas, razonamientos, avisos y pasos de los planes de todas las tareas del catálogo se leen
    sin citas de requisitos ni claves internas: la cita es del código y del registro, no del operador."""
    cliente, app = api
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: (
        {'id': 'disco:t1', 'project': 'Ensayo Alfa', 'feeders': ['QX511'], 'informes': []} if calibrado else None))
    hallados = {}
    for tarea in sorted(TAREAS):
        # Un espacio por tarea: las que se lanzan solas ocupan el suyo hasta terminar.
        wid = cliente.post('/api/workspaces', json={'name': tarea}).json()['id']
        app.state.store.get(wid).informes.setdefault('formularios', {})['Ensayo Alfa'] = {
            'estudio': {'solicitante': 'c'}, 'factibilidad': {'solicitud': {'cliente': 'c'}}}
        plan = _plan(cliente, wid, monkeypatch, tarea)
        for campo in ('faltan', 'dudas', 'razonamiento', 'avisos', 'pasos'):
            for texto in plan.get(campo) or []:
                if jerga := _jerga(texto):
                    hallados.setdefault(tarea, []).append(f'{campo}: «{texto}» → {jerga}')
    assert not hallados, '\n'.join(f'{t}: {x}' for t, xs in hallados.items() for x in xs)


def test_el_plan_no_espera_a_la_respuesta_de_la_consulta(api, monkeypatch):
    """070:RF-51 (P4 v2) — el plan de una consulta lenta de RESPONDER se lee igual: la espera de la prueba es la del plan,
    no la de la respuesta. Una respuesta que tarda diez veces el plazo (la carga de pesos de la puerta, simulada con el
    reloj sin esperarla) no agota la espera, y el plan de «pregunta» [calibrado] sigue sin citas ni claves."""
    cliente, app = api
    salto = [0.0]
    monkeypatch.setattr(sys.modules[__name__], '_RELOJ', lambda: time.monotonic() + salto[0])

    def pregunta_lenta(*_a, **_k):
        salto[0] += 10 * PLAZO_S
        return {'texto': 'respuesta lenta'}

    monkeypatch.setattr(services, 'asistente_pregunta', pregunta_lenta)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: (
        {'id': 'disco:t1', 'project': 'Ensayo Alfa', 'feeders': ['QX511'], 'informes': []}))
    wid = cliente.post('/api/workspaces', json={'name': 'pregunta'}).json()['id']
    app.state.store.get(wid).informes.setdefault('formularios', {})['Ensayo Alfa'] = {
        'estudio': {'solicitante': 'c'}, 'factibilidad': {'solicitud': {'cliente': 'c'}}}
    plan = _plan(cliente, wid, monkeypatch, 'pregunta')
    jerga = [f'{campo}: {j}' for campo in ('faltan', 'dudas', 'razonamiento', 'avisos', 'pasos')
             for texto in plan.get(campo) or [] for j in _jerga(texto)]
    assert not jerga, jerga


@pytest.mark.parametrize('texto, malo', [('Dígalo en la orden (072:RF-29).', True), ('Vea la spec 017.', True),
                                         ('en «planificacion.anio_presentacion» del perfil', True),
                                         ('la tarea evaluar_carga_nueva', True),
                                         ('el libro D:/datos/libro_uno.xlsx no existe.', False),
                                         ('la calibración: Ensayo Alfa no tiene ninguna aplicada.', False)])
def test_el_detector_de_jerga_distingue(texto, malo):
    """070:RF-51 — la prueba de arriba no se queda muda: reconoce citas y claves, y deja pasar rutas y texto llano."""
    assert bool(_jerga(texto)) is malo


#: Lo que el aviso sin Transformer enseñaba en la prueba del auditor (2026-11-14), tal cual.
MOTIVO_REAL = ("El codificador intfloat/multilingual-e5-base (revisión d128750597153bb5987e10b1c3493a34e5a4502a) no está en la "
               "caché local de Hugging Face que usa este proceso, o faltan sus librerías; se prepara con: python "
               "tools/preparar_modelos_ia.py --descargar --backend huggingface --id intfloat/multilingual-e5-base --output-json "
               "preparar.json: We couldn't connect to 'https://huggingface.co' to load the files.")


def test_el_aviso_sin_transformer_no_ensena_la_consola_ni_el_ingles():
    """070:RF-51 / 067:RF-9 — el aviso dice por qué falta el modelo, sin la orden de consola, la revisión ni el error en
    inglés de la librería; un motivo ya en palabras del operador se queda como está."""
    from convertersmartgrid.aplicacion.asistente.plan import aviso_sin_transformer

    aviso = aviso_sin_transformer(MOTIVO_REAL, 'ninguno')
    assert 'caché local' in aviso and not _jerga(aviso)
    for malo in ('python', '--descargar', 'huggingface.co', "couldn't", 'd1287505'):
        assert malo not in aviso, malo
    assert 'No hay GPU CUDA para el gemelo digital' in aviso_sin_transformer('No hay GPU CUDA para el gemelo digital', 'x')


def test_la_etapa_que_falta_se_dice_en_palabras():
    """070:RF-51 — «falta ruta_cargas» enseñaba el campo; las etapas se nombran y se explican sin claves."""
    from convertersmartgrid.presentacion.web.asistente_operacion import _etapas_en_palabras

    lista = {'etapas': [{'nombre': 'cargas_nuevas', 'estado': 'se_omitira', 'falta': ['ruta_cargas'], 'motivo': ''},
                        {'nombre': 'informe', 'estado': 'falta_dato', 'falta': ['formulario'], 'motivo': ''},
                        {'nombre': 'caso_base', 'estado': 'hecha', 'falta': [], 'motivo': ''}]}
    palabras = _etapas_en_palabras(lista)
    assert palabras == ['cargas nuevas (se omitirá: falta el libro de cargas nuevas)',
                        'informe (falta el formulario del informe)', 'caso base (ya hecha)']
    assert not any(_jerga(p) for p in palabras)
