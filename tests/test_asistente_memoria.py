"""027:RF-73 a 027:RF-76 — memoria a largo plazo del asistente, por espacio.

Cada orden se interpretaba sola: «y ahora con el otro alimentador» no sabía de qué alimentador se hablaba, porque el
contexto que recibía el intérprete era global (ejemplos y notas de reflexión) y no recordaba la conversación. Aquí cada
espacio guarda su hilo en su carpeta, la orden recibe los últimos turnos y los recuerdos parecidos de conversaciones
anteriores, el operador puede verla y olvidarla, y el fichero tiene topes.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

import inspect

from convertersmartgrid.aplicacion.asistente import senales
from convertersmartgrid.presentacion.web import services
from convertersmartgrid.presentacion.web.app import create_app

_VARIABLES = ('CSG_ASISTENTE_MEMORIA_TURNOS', 'CSG_ASISTENTE_MEMORIA_RECUERDOS', 'CSG_ASISTENTE_MEMORIA_FILAS')


def MemoriaConversacion(raiz):
    assert hasattr(senales, 'MemoriaConversacion'), '027:RF-73: el asistente no tiene memoria de conversación por espacio'
    return senales.MemoriaConversacion(raiz)


def topes_memoria():
    assert hasattr(senales, 'topes_memoria'), '027:RF-76: la memoria no tiene topes'
    return senales.topes_memoria()


def contexto_para(texto, **kw):
    if 'memoria' in kw:
        assert 'memoria' in inspect.signature(senales.contexto_para).parameters, \
            '027:RF-73: contexto_para no recibe la memoria del espacio'
    return senales.contexto_para(texto, **kw)


@pytest.fixture(autouse=True)
def _sin_topes_del_entorno(tmp_path, monkeypatch):
    for v in _VARIABLES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))


def _lineas(mem: MemoriaConversacion) -> list[dict]:
    return [json.loads(x) for x in mem.ruta.read_text(encoding='utf-8').splitlines() if x.strip()]


def test_027_rf73_la_orden_recibe_los_ultimos_turnos_de_su_espacio(tmp_path):
    """027:RF-73: los turnos anteriores del espacio, en orden, con su tarea y sus datos, llegan al intérprete."""
    mem = MemoriaConversacion(tmp_path / 'espacio_a')
    mem.recordar(plan='p1', texto='calibra el alimentador AL01', tarea='calibrar', datos={'alimentador': 'AL01'})
    mem.recordar(plan='p2', texto='dame las pérdidas', tarea='consultar_datos', datos={},
                 respuesta='Pérdidas del AL01: 3,1 %.')
    lineas = contexto_para('y ahora con el otro alimentador', memoria=mem)
    turnos = [x for x in lineas if x.startswith('Turno anterior')]
    assert len(turnos) == 2
    assert 'calibra el alimentador AL01' in turnos[0] and 'alimentador=AL01' in turnos[0]
    assert 'dame las pérdidas' in turnos[1] and 'Pérdidas del AL01' in turnos[1]
    assert mem.ruta.parent.name == 'asistente_memoria' and mem.ruta.parent.parent == tmp_path / 'espacio_a'


def test_027_rf73_la_memoria_de_un_espacio_no_entra_en_otro(tmp_path):
    """027:RF-73: cada espacio tiene su conversación; la de otro espacio nunca es contexto."""
    a = MemoriaConversacion(tmp_path / 'a')
    b = MemoriaConversacion(tmp_path / 'b')
    a.recordar(plan='p1', texto='convierte la red de prueba', tarea='convertir', datos={})
    assert not any('convierte la red de prueba' in x for x in contexto_para('convierte la red', memoria=b))
    assert b.turnos() == []


def test_027_rf73_sin_memoria_el_contexto_es_el_de_siempre(tmp_path):
    """027:RF-73: sin memoria de espacio, contexto_para da lo mismo que antes (ejemplos y reflexiones)."""
    senales.reflexion('calibra el AL01', 'calibrar', 'falló', 'repetir')
    assert contexto_para('calibra el AL01') == contexto_para('calibra el AL01', memoria=None)
    assert not any(x.startswith(('Turno anterior', 'Recuerdo')) for x in contexto_para('calibra el AL01'))


def test_027_rf74_recuerda_las_conversaciones_anteriores_parecidas(tmp_path, monkeypatch):
    """027:RF-74: de los turnos que ya salieron de la ventana reciente, vuelven los más parecidos a la orden."""
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_TURNOS', '2')
    mem = MemoriaConversacion(tmp_path / 'e')
    mem.recordar(plan='p0', texto='informe de factibilidad del alimentador AL07', tarea='informe_factibilidad',
                 datos={'alimentador': 'AL07'})
    for i in range(5):
        mem.recordar(plan=f'q{i}', texto=f'entrena el gemelo número {i}', tarea='gemelo_entrenar', datos={})
    lineas = contexto_para('otro informe de factibilidad del alimentador AL07', memoria=mem)
    recuerdos = [x for x in lineas if x.startswith('Recuerdo')]
    assert len(recuerdos) == 1 and 'AL07' in recuerdos[0]
    assert len([x for x in lineas if x.startswith('Turno anterior')]) == 2
    # Lo que está en la ventana reciente no se repite como recuerdo.
    assert not any('entrena el gemelo' in x for x in recuerdos)


def test_027_rf74_el_tope_de_recuerdos_se_respeta(tmp_path, monkeypatch):
    """027:RF-74: nunca más recuerdos que CSG_ASISTENTE_MEMORIA_RECUERDOS."""
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_TURNOS', '1')
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_RECUERDOS', '2')
    mem = MemoriaConversacion(tmp_path / 'e')
    for i in range(6):
        mem.recordar(plan=f'p{i}', texto=f'calibra el alimentador AL0{i}', tarea='calibrar', datos={})
    mem.recordar(plan='z', texto='hola', tarea=None, datos={})
    recuerdos = [x for x in contexto_para('calibra el alimentador AL03', memoria=mem) if x.startswith('Recuerdo')]
    assert len(recuerdos) == 2


def test_027_rf73_la_correccion_cambia_lo_recordado(tmp_path):
    """027:RF-73: si el operador corrige un plan, la memoria recuerda la tarea corregida, no la que se entendió."""
    mem = MemoriaConversacion(tmp_path / 'e')
    mem.recordar(plan='p1', texto='haz el estudio del AL02', tarea='transferencia', datos={})
    mem.corregir(plan='p1', nuevo='p2', tarea='informe_estudio', datos={'alimentador': 'AL02'})
    (t,) = mem.turnos()
    assert t['tarea'] == 'informe_estudio' and t['datos'] == {'alimentador': 'AL02'} and t['plan'] == 'p2'


def test_027_rf73_solo_datos_sencillos_y_sin_credenciales(tmp_path):
    """027:RF-73: se guardan textos, números y listas cortas de textos; una credencial pegada no se guarda."""
    mem = MemoriaConversacion(tmp_path / 'e')
    mem.recordar(plan='p1', texto='usa password=clave1 en la nube', tarea='nube',
                 datos={'proyecto': 'P1', 'anio': 2026, 'lista': ['A', 'B'], 'objeto': {'x': 1}, 'nada': None})
    (t,) = mem.turnos()
    assert 'clave1' not in t['texto']
    assert t['datos'] == {'proyecto': 'P1', 'anio': 2026, 'lista': ['A', 'B']}


def test_027_rf75_olvidar_borra_la_conversacion_y_queda_el_evento(tmp_path):
    """027:RF-75: olvidar deja la conversación vacía; el olvido queda como evento con su fecha y los textos
    olvidados ya no están en el fichero."""
    mem = MemoriaConversacion(tmp_path / 'e')
    mem.recordar(plan='p1', texto='calibra el alimentador AL01', tarea='calibrar', datos={})
    mem.recordar(plan='p2', texto='convierte la red', tarea='convertir', datos={})
    r = mem.olvidar()
    assert r['olvidados'] == 2
    assert mem.turnos() == []
    assert not any(x.startswith(('Turno anterior', 'Recuerdo')) for x in contexto_para('calibra', memoria=mem))
    filas = _lineas(mem)
    assert [f['evento'] for f in filas] == ['olvido'] and filas[0]['fecha']
    assert 'AL01' not in mem.ruta.read_text(encoding='utf-8')
    mem.recordar(plan='p3', texto='nueva conversación', tarea=None, datos={})
    assert [t['texto'] for t in mem.turnos()] == ['nueva conversación']


def test_027_rf76_el_fichero_no_crece_sin_limite(tmp_path, monkeypatch):
    """027:RF-76: con más turnos que CSG_ASISTENTE_MEMORIA_FILAS se compacta y quedan los más recientes, en orden."""
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_FILAS', '5')
    mem = MemoriaConversacion(tmp_path / 'e')
    for i in range(12):
        mem.recordar(plan=f'p{i}', texto=f'orden {i}', tarea=None, datos={})
    assert len(_lineas(mem)) <= 5
    assert [t['texto'] for t in mem.turnos()] == [f'orden {i}' for i in range(7, 12)]


def test_027_rf76_topes_con_valor_por_defecto_y_variable(monkeypatch):
    """027:RF-76: topes por defecto 6 turnos, 3 recuerdos y 500 filas; una variable inválida da el de defecto y
    un valor por debajo de 1 queda en 1."""
    assert topes_memoria() == {'turnos': 6, 'recuerdos': 3, 'filas': 500}
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_TURNOS', 'muchos')
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_RECUERDOS', '0')
    monkeypatch.setenv('CSG_ASISTENTE_MEMORIA_FILAS', '40')
    assert topes_memoria() == {'turnos': 6, 'recuerdos': 1, 'filas': 40}


def test_027_rf73_una_linea_rota_no_borra_la_memoria(tmp_path):
    """027:RF-73: una línea cortada a mitad (corte de luz) se salta; el resto de la conversación sigue."""
    mem = MemoriaConversacion(tmp_path / 'e')
    mem.recordar(plan='p1', texto='primera', tarea=None, datos={})
    with open(mem.ruta, 'a', encoding='utf-8') as f:
        f.write('{"evento": "turno", "tex')
    mem.recordar(plan='p2', texto='segunda', tarea=None, datos={})
    assert [t['texto'] for t in mem.turnos()] == ['primera', 'segunda']


# --- por la web: orden real, API de la memoria y olvido -------------------------------------------------------

class _InterpretePrueba:
    def predecir(self, texto):
        return {'tarea': 'gemelo_entrenar', 'confianza': 1.0, 'datos': {}}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (_InterpretePrueba(), None))
    vistos: list[list[str]] = []
    original = senales.contexto_para

    def espia(texto, **kw):
        out = original(texto, **kw)
        vistos.append(out)
        return out

    monkeypatch.setattr(senales, 'contexto_para', espia)
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, vistos, tmp_path / 'web'


def _orden(cliente, wid, texto):
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        j = cliente.get(f"/api/jobs/{r.json()['id']}").json()
        if j['status'] in ('done', 'failed', 'cancelled'):
            assert j['status'] == 'done', j['error']
            return j['result']['plan']
        time.sleep(0.02)
    pytest.fail('la orden no terminó')


def test_027_rf73_la_segunda_orden_recibe_la_primera_por_la_web(api):
    """027:RF-73: por la ruta real, la segunda orden del espacio llega al intérprete con la primera como turno y
    la conversación vive en la carpeta del espacio, no en git."""
    cliente, vistos, web = api
    wid = cliente.post('/api/workspaces', json={'name': 'memoria'}).json()['id']
    _orden(cliente, wid, 'reentrena la pinn')
    _orden(cliente, wid, 'otra vez lo mismo')
    assert any('reentrena la pinn' in x and x.startswith('Turno anterior') for x in vistos[-1])
    (ruta,) = list(web.rglob('asistente_memoria/conversacion.jsonl'))
    assert wid in ruta.parts


def test_027_rf75_la_web_ensena_y_olvida_la_memoria_de_un_espacio(api):
    """027:RF-75: GET de la memoria con sus topes y POST de olvidar, sin tocar la de otro espacio."""
    cliente, _vistos, _web = api
    a = cliente.post('/api/workspaces', json={'name': 'uno'}).json()['id']
    b = cliente.post('/api/workspaces', json={'name': 'dos'}).json()['id']
    _orden(cliente, a, 'reentrena la pinn')
    _orden(cliente, b, 'reentrena la pinn otra vez')
    r = cliente.get(f'/api/workspaces/{a}/asistente/memoria')
    assert r.status_code == 200, '027:RF-75: la web no enseña la memoria del espacio'
    m = r.json()
    assert [t['texto'] for t in m['turnos']] == ['reentrena la pinn'] and m['topes']['turnos'] == 6
    r = cliente.post(f'/api/workspaces/{a}/asistente/memoria/olvidar')
    assert r.status_code == 200 and r.json()['olvidados'] == 1
    assert cliente.get(f'/api/workspaces/{a}/asistente/memoria').json()['turnos'] == []
    assert len(cliente.get(f'/api/workspaces/{b}/asistente/memoria').json()['turnos']) == 1
