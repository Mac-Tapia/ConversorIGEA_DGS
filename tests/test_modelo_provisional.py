"""085:RF-26 a RF-33 — el modelo en uso por decisión del usuario, sin aprobarlo y sin ejecutar nada sin confirmación."""
from __future__ import annotations

import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.asistente import modelos_en_uso as meu
from convertersmartgrid.asistente import transformer
from convertersmartgrid.asistente.tareas import TAREAS
from convertersmartgrid.model_registry import EstadoModelo
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app

ANTERIOR = '20260101-000000-aaaa'
MOTIVO = 'El modelo en uso deja colarse lo que no es orden.'
MEDIDA = {'acierto_tarea': 0.964, 'f1_datos': 0.918, 'ejemplos': 110, 'familias': {}}


def _metricas():
    return {'examen_maestro': MEDIDA, 'sinteticas': {'acierto_tarea': 0.829, 'f1_datos': 0.82, 'ejemplos': 2104},
            'humanas': {'acierto_tarea': 0.72, 'f1_datos': 0.75, 'ejemplos': 43},
            'prueba_sellada': {'decide': False, 'medida': {'acierto_tarea': 0.86, 'f1_datos': 0.68, 'ejemplos': 2068}},
            'rechazo': {'rechazada': 0.92, 'se_cuela': 0.0, 'ejemplos': 206},
            'en_uso': {'version': ANTERIOR, 'rechazo': {'se_cuela': 0.67}}}


def _candidato(tmp_path, estado='RECHAZADO', reabre=True, marca=b'pesos'):
    (tmp_path / 'pesos.pt').write_bytes(marca)
    (tmp_path / 'modelo.json').write_text('{"version": "alumno"}', encoding='utf-8')
    decision = {'status': estado, 'gates': {'approved': estado == 'PROMOVIDO'}, 'fallos': ['estado: acierto_tarea bajo puerta']}
    return meu.registro().registrar_candidato(
        'transformer', model_manifest={'metodo': 'destilado'}, dataset_manifest={'hash': 'x'}, metrics=_metricas(),
        decision=decision, smoke_reload={'ok': reabre}, artifacts=[tmp_path / 'pesos.pt', tmp_path / 'modelo.json'])['candidate_id']


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Un modelo heredado en uso, como el del proyecto: está en el puntero y no en el registro."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    carpeta = transformer.raiz_modelos('ordenes') / ANTERIOR
    carpeta.mkdir(parents=True)
    (carpeta / 'modelo.json').write_text('{"cfg": {}}', encoding='utf-8')
    transformer.promover(ANTERIOR, 'heredado', 'ordenes')
    return tmp_path


def _poner(candidato, **cambios):
    return meu.poner_provisional('transformer', candidato, **{'decidido_por': 'usuario', 'motivo': MOTIVO,
                                                              'fecha': '2026-11-04', **cambios})


def _huellas(candidato):
    raiz = meu.registro().raiz / 'transformer' / 'candidates' / candidato
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raiz.rglob('*') if p.is_file()}


def test_guarda_la_decision_del_usuario_con_sus_cifras_y_el_anterior(datos):
    """085:RF-26 — el registro guarda quién, cuándo, por qué, las cifras del candidato y el modelo anterior."""
    candidato = _candidato(datos)
    fila = _poner(candidato)
    leida = meu.registro().uso_provisional('transformer', candidato)
    assert leida == fila and fila['decidido_por'] == 'usuario' and fila['fecha'] == '2026-11-04' and fila['motivo'] == MOTIVO
    assert fila['modelo_anterior'] == ANTERIOR
    assert fila['cifras']['examen_maestro'] == {'acierto_tarea': 0.964, 'f1_datos': 0.918, 'ejemplos': 110}
    assert fila['cifras']['prueba_sellada']['acierto_tarea'] == 0.86 and fila['cifras']['rechazo']['se_cuela'] == 0.0
    assert fila['cifras']['modelo_en_uso_al_decidir'] == {'version': ANTERIOR, 'sinteticas': None, 'humanas': None, 'se_cuela': 0.67}
    assert transformer.version_promovida('ordenes') == meu.version_provisional(candidato)


@pytest.mark.parametrize('cambio', [{'decidido_por': ' '}, {'motivo': ''}, {'fecha': ' '}])
def test_sin_autor_motivo_o_fecha_no_se_pone(datos, cambio):
    """085:RF-26 — sin quién, por qué o cuándo no hay decisión, y el puntero no se mueve."""
    with pytest.raises(ValueError, match='quién la decide'):
        _poner(_candidato(datos), **cambio)
    assert transformer.version_promovida('ordenes') == ANTERIOR


@pytest.mark.parametrize('estado, reabre, mensaje', [('PROMOVIDO', True, 'candidato rechazado'), ('BLOQUEADO_POR_DATOS', True, 'candidato rechazado'),
                                                     ('RECHAZADO', False, 'no reabrió')])
def test_solo_un_rechazado_que_reabre(datos, estado, reabre, mensaje):
    """085:RF-27 — ni uno aprobado, que entra por su vía, ni uno sin datos, ni uno que no reabre."""
    candidato = _candidato(datos, estado, reabre)
    with pytest.raises(ValueError, match=mensaje):
        _poner(candidato)
    assert transformer.version_promovida('ordenes') == ANTERIOR
    assert meu.registro().uso_provisional('transformer', candidato) is None


def test_un_candidato_alterado_no_se_pone(datos):
    """085:RF-27 — con los pesos tocados, la integridad del registro lo para."""
    candidato = _candidato(datos)
    (meu.registro().raiz / 'transformer' / 'candidates' / candidato / 'artifacts' / 'pesos.pt').write_bytes(b'otros')
    with pytest.raises(ValueError, match='integridad'):
        _poner(candidato)
    assert transformer.version_promovida('ordenes') == ANTERIOR


def test_no_falsifica_la_decision_de_las_puertas(datos):
    """085:RF-28 — el candidato sigue rechazado y sin una coma cambiada, sin activo en el registro, y promoverlo se sigue negando."""
    candidato = _candidato(datos)
    antes = _huellas(candidato)
    _poner(candidato)
    reg = meu.registro()
    assert _huellas(candidato) == antes
    detalle = reg.detalle('transformer', candidato)
    assert detalle['decision']['status'] == EstadoModelo.RECHAZADO.value and detalle['decision']['gates'] == {'approved': False}
    assert reg.activo('transformer') is None
    with pytest.raises(ValueError, match='no aprobado'):
        reg.promover('transformer', candidato)
    with pytest.raises(ValueError, match='no aprobado'):
        meu.activar('transformer', candidato)
    assert meu.aplicar_decision('transformer', {'candidate_id': candidato, 'status': 'RECHAZADO'})['promovido'] is False


def test_volver_al_anterior_y_de_nuevo(datos):
    """085:RF-29 — volver funciona con el modelo heredado, y lo provisional sale del puntero, no de una marca aparte."""
    candidato = _candidato(datos)
    _poner(candidato)
    assert meu.uso_provisional('transformer')['version'] == meu.version_provisional(candidato)
    assert meu.volver_al_anterior('transformer') == ANTERIOR
    assert transformer.version_promovida('ordenes') == ANTERIOR and meu.uso_provisional('transformer') is None
    assert meu.registro().activo('transformer') is None
    # Volver otra vez deja de nuevo el provisional, con su aviso: ni se aprueba ni se esconde.
    assert meu.volver_al_anterior('transformer') == meu.version_provisional(candidato)
    assert meu.uso_provisional('transformer')['decidido_por'] == 'usuario'


def test_repetirla_no_borra_el_anterior(datos):
    """085:RF-29 — ponerlo dos veces haría de él su propio anterior y «volver» no volvería."""
    candidato = _candidato(datos)
    _poner(candidato)
    with pytest.raises(ValueError, match='ya está en uso'):
        _poner(candidato)
    assert meu.volver_al_anterior('transformer') == ANTERIOR


def test_uno_aprobado_lo_sustituye_y_deja_de_ser_provisional(datos, tmp_path):
    """085:RF-29 — el siguiente que pase las puertas entra por su vía de siempre, y volver regresa al provisional."""
    provisional = _candidato(datos)
    _poner(provisional)
    aprobado = _candidato(datos, 'PROMOVIDO', marca=b'otros pesos')
    assert meu.activar('transformer', aprobado) == meu.version_de(aprobado)
    assert meu.uso_provisional('transformer') is None
    assert meu.volver_al_anterior('transformer') == meu.version_provisional(provisional)
    assert meu.registro().activo('transformer') is None and meu.uso_provisional('transformer') is not None


def test_un_puntero_provisional_sin_anotacion_no_pasa_por_aprobado(datos):
    """085:RF-30 — si falta la anotación, se dice, y sigue siendo provisional."""
    candidato = _candidato(datos)
    _poner(candidato)
    (meu.registro().raiz / 'transformer' / 'usos_provisionales.jsonl').unlink()
    uso = meu.uso_provisional('transformer')
    assert uso['sin_anotacion'] is True and uso['puertas_aprobadas'] is False
    assert 'no pasa las puertas' in meu.aviso_provisional(uso)


# ------------------------------------------------------------------- la web y el asistente
class InterpreteSeguro:
    """Confianza máxima: justo el caso en que no debe bastar."""
    version = 'prov-prueba'
    umbral = 0.5

    def __init__(self, tarea):
        self.tarea = tarea

    def predecir(self, texto):
        return {'tarea': self.tarea, 'confianza': 1.0, 'datos': {}}


@pytest.fixture
def api(datos, tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente


def _esperar(cliente, trabajo):
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{trabajo}').json()
        if r['status'] in ('done', 'failed', 'cancelled'):
            return r
        time.sleep(0.02)
    pytest.fail('la cola no terminó')


def _orden(cliente, wid, tarea, monkeypatch, texto='haz esto ahora mismo'):
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (InterpreteSeguro(tarea), None))
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202
    fin = _esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    return fin['result']


def test_ninguna_tarea_que_escribe_tiene_otra_via_que_la_confirmacion():
    """085:RF-31 — toda tarea que escribe es de un modo que espera, y ninguna responde como consulta."""
    from convertersmartgrid.asistente.plan import Plan

    que_escriben = [n for n, t in TAREAS.items() if t.escribe]
    assert que_escriben and not [n for n in que_escriben if TAREAS[n].modo == 'consulta']
    for n in que_escriben:
        assert Plan('x', 't', n, True, TAREAS[n].modo, confianza=1.0).espera_confirmacion is True


def test_con_confianza_maxima_lo_que_escribe_espera_y_la_escritura_exige_el_clic(api, datos, monkeypatch):
    """085:RF-31, 085:RF-24 — con el modelo provisional y confianza 1,0 no se lanza ningún trabajo, el gobierno niega el permiso,
    y solo la ruta de confirmación ejecuta la herramienta."""
    candidato = _candidato(datos)
    _poner(candidato)
    llamadas = []
    monkeypatch.setattr(services, 'gemelo_entrenar', lambda *_a, **_k: llamadas.append(True) or {'entrenado': False})
    wid = api.post('/api/workspaces', json={'name': 'p'}).json()['id']
    r = _orden(api, wid, 'gemelo_entrenar', monkeypatch)
    plan = r['plan']
    assert TAREAS['gemelo_entrenar'].escribe and plan['listo'] and plan['confianza'] == 1.0
    assert plan['espera_confirmacion'] is True and 'trabajo' not in r and not r.get('respuesta')
    assert plan['equipo']['permiso_efectivo'] is False and not llamadas
    time.sleep(0.1)
    assert not llamadas, 'nada se ejecuta solo'
    hecho = api.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert hecho.status_code == 202
    assert _esperar(api, hecho.json()['id'])['status'] == 'done' and llamadas == [True]


def test_con_modelo_provisional_tampoco_se_lanza_solo_un_trabajo_de_lectura(api, datos, monkeypatch):
    """085:RF-32 — sin provisional la lectura se lanza sola como siempre; con él, espera su clic."""
    lectura = next(n for n, t in TAREAS.items() if not t.escribe and t.modo == 'trabajo' and not [d for d in t.datos if d.obligatorio])
    wid = api.post('/api/workspaces', json={'name': 'p'}).json()['id']
    monkeypatch.setattr(services, '_asistente_requisitos', lambda *_a, **_k: None)
    monkeypatch.setattr(services, '_asistente_ejecutar_plan', lambda *_a, **_k: {'texto': 'hecho', 'completo': True})
    sin = _orden(api, wid, lectura, monkeypatch)
    assert sin['plan']['espera_confirmacion'] is False and 'trabajo' in sin
    _esperar(api, sin['trabajo']['id'])
    _poner(_candidato(datos))
    con = _orden(api, wid, lectura, monkeypatch, texto='hazlo otra vez ahora')
    assert con['plan']['espera_confirmacion'] is True and 'trabajo' not in con
    assert any('provisional' in a for a in con['plan']['avisos'])
    hecho = api.post(f"/api/workspaces/{wid}/asistente/{con['plan']['id']}/confirmar")
    assert _esperar(api, hecho.json()['id'])['status'] == 'done'


def test_cada_plan_lo_dice_con_sus_cifras_y_tambien_una_consulta(api, datos, monkeypatch):
    """085:RF-30 — el asistente muestra «provisional, no pasa las puertas» y las cifras; una consulta sigue respondiendo al momento."""
    _poner(_candidato(datos))
    wid = api.post('/api/workspaces', json={'name': 'p'}).json()['id']
    r = _orden(api, wid, 'estado', monkeypatch)
    assert TAREAS['estado'].modo == 'consulta' and r['respuesta'] and r['plan']['espera_confirmacion'] is False
    (aviso,) = [a for a in r['plan']['avisos'] if 'provisional' in a]
    for texto in ('no pasa las puertas', '0,964 de 0,98', '0,918 de 0,95', '110 órdenes', '0,860', '0,829', '0,0 %', 'usuario', '2026-11-04'):
        assert texto in aviso, texto
    guardados = api.get(f'/api/workspaces/{wid}/asistente/planes').json()
    assert isinstance(guardados['planes'], list)


def test_sin_modelo_provisional_nada_cambia(api, monkeypatch):
    """085:RF-30 — con un modelo normal, ningún aviso."""
    wid = api.post('/api/workspaces', json={'name': 'p'}).json()['id']
    r = _orden(api, wid, 'estado', monkeypatch)
    assert not [a for a in r['plan']['avisos'] if 'provisional' in a] and r['plan']['espera_confirmacion'] is False


def test_el_estado_de_modelos_lo_muestra_como_rechazado_y_provisional(api, datos):
    """085:RF-30, 085:RF-28 — la web: en uso, provisional y con su estado RECHAZADO; nada de aprobado ni de heredado."""
    candidato = _candidato(datos)
    _poner(candidato)
    familia = next(f for f in api.get('/api/asistente/modelos').json()['familias'] if f['familia'] == 'transformer')
    assert familia['estado'] == 'RECHAZADO' and familia['gates'].get('approved') is not True
    assert familia['en_uso'] == meu.version_provisional(candidato) and familia['heredado'] is None
    assert familia['provisional']['decidido_por'] == 'usuario'
    assert any('no pasa las puertas' in b for b in familia['bloqueos'])
    # 027:RF-24: por la API de siempre también se vuelve.
    r = api.post('/api/modelos/asistente/volver')
    assert r.status_code == 200 and r.json()['version'] == ANTERIOR
    familia = next(f for f in api.get('/api/asistente/modelos').json()['familias'] if f['familia'] == 'transformer')
    assert familia['provisional'] is None and familia['en_uso'] == ANTERIOR


# ------------------------------------------------------------------- la herramienta
def _herramienta():
    from apoyo import cargar_herramienta

    return cargar_herramienta('asistente_modelo_provisional.py', 'modelo_provisional_085')


def test_herramienta_ver_poner_y_volver(datos, capfdbinary):
    """085:RF-33 — sin el candidato o el motivo no se cambia nada; `ver` no toca el puntero; `poner` y `volver` funcionan."""
    h = _herramienta()
    candidato = _candidato(datos)
    assert h.main(['ver']) == 0
    assert transformer.version_promovida('ordenes') == ANTERIOR
    visto = json.loads(capfdbinary.readouterr().out.decode('utf-8'))
    assert visto['ultimo_candidato']['candidate_id'] == candidato and visto['provisional'] is None
    assert visto['ultimo_candidato']['cifras']['examen_maestro']['acierto_tarea'] == 0.964
    with pytest.raises(SystemExit):
        h.main(['poner', '--candidato', candidato])
    assert transformer.version_promovida('ordenes') == ANTERIOR
    assert h.main(['poner', '--candidato', candidato, '--decidido-por', 'usuario', '--motivo', MOTIVO, '--fecha', '2026-11-04']) == 0
    assert meu.uso_provisional('transformer')['fecha'] == '2026-11-04'
    assert h.main(['volver']) == 0
    assert transformer.version_promovida('ordenes') == ANTERIOR


def test_herramienta_rechaza_lo_que_no_puede_y_lo_dice(datos, capfd):
    """085:RF-33 — un candidato aprobado o inexistente no mueve el puntero y termina con código 1."""
    h = _herramienta()
    aprobado = _candidato(datos, 'PROMOVIDO')
    assert h.main(['poner', '--candidato', aprobado, '--decidido-por', 'usuario', '--motivo', MOTIVO]) == 1
    assert 'No se cambió' in capfd.readouterr().err and transformer.version_promovida('ordenes') == ANTERIOR
