"""Spec 067 — el asistente opera desde la web: evidencia, avisos, planes, modelos, tareas y lista.

Rutas y cola reales con ``TestClient``. Solo se sustituyen, y se dice en cada prueba, los motores que
escriben en DIgSILENT y el transporte de Ollama: sin GPU, sin DIgSILENT y sin cargar modelos.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.asistente import almacen
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app

RAIZ = Path(__file__).resolve().parents[1]
VOCAB = {'alimentadores': ['F1', 'F2'], 'proyecto': ['P1'], 'sistema': ['S1'], 'subtipo': ['refuerzo de red']}


class Transformer:
    """Doble del modelo de órdenes: dice la tarea que se le pide."""

    tareas = ('estado',)

    def __init__(self, tarea='gemelo_entrenar', datos=None):
        self.tarea, self.datos = tarea, datos or {}

    def predecir(self, texto):
        return {'tarea': self.tarea, 'confianza': 1.0, 'datos': self.datos}


def obra_en(tarea):
    return Transformer(tarea, {'proyecto': [{'valor': 'P1'}], 'alimentadores': [{'valor': 'F1'}]})


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda ws: dict(VOCAB))
    services._ASISTENTE_PLANES.clear()
    yield tmp_path
    services._ASISTENTE_PLANES.clear()


@pytest.fixture
def api(entorno, monkeypatch):
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(), None))
    # 070:RF-14: el perfil para costear se comprueba al proponer; estas pruebas no traen ninguno.
    from convertersmartgrid.web import asistente_operacion

    monkeypatch.setattr(asistente_operacion, 'parametros_de_costeo', lambda _t: None)
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app


def esperar(cliente, id_trabajo):
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{id_trabajo}').json()
        if r['status'] in ('done', 'failed', 'cancelled'):
            return r
        time.sleep(0.02)
    pytest.fail('la cola no terminó')


def espacio(cliente, app):
    wid = cliente.post('/api/workspaces', json={'name': 'operativo'}).json()['id']
    return wid, app.state.store.get(wid)


def proponer(cliente, wid, texto='haz la orden'):
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    return fin['result']['plan']


def informe_del_motor(ws, ctx, formulario):
    """El motor del informe, sustituido: DIgSILENT no se abre en la suite."""
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.out_dir / 'informe.docx').write_bytes(b'documento real del trabajo')
    return {'project': formulario['project'], 'informe': 'informe.docx', 'huecos': [], 'factible': True}


def ollama_de_prueba(monkeypatch, decision='favorable'):
    """Solo el transporte es de prueba: el cliente, el adaptador y sus validaciones son los reales."""
    from convertersmartgrid.asistente import ollama

    peticiones = []

    def abrir(peticion, timeout):
        cuerpo = json.loads(peticion.data)
        peticiones.append(cuerpo)
        ids = list(json.loads(cuerpo['messages'][-1]['content'])['evidencia'])
        dictamen = {'decision': decision, 'evidencia_ids': ids, 'incertidumbres': [], 'contradicciones': []}
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(dictamen)}}).encode())

    monkeypatch.setattr(ollama, 'cliente_configurado', lambda **_k: ollama.ClienteOllama(abrir=abrir))
    return peticiones


def lanzar_informe(cliente, wid):
    r = cliente.post(f'/api/workspaces/{wid}/informes/estudio', json={'alimentador': 'F1', 'project': 'P1'})
    assert r.status_code == 202, r.text
    fin = esperar(cliente, r.json()['id'])
    # El estado cambia antes de avisar: el aviso, con la custodia, es lo último del trabajo.
    ws = cliente.app.state.store.get(wid)
    limite = time.monotonic() + 5
    while time.monotonic() < limite and not any(
            e['type'] == 'job' and e['data']['id'] == fin['id'] and e['data']['status'] == fin['status']
            for e in ws.events.since(0)):
        time.sleep(0.01)
    return fin


# ------------------------------------------------------------------ evidencia y revisión
def test_evidencia_del_trabajo_real_alimenta_la_revision_sin_registro_manual(api, monkeypatch):
    """067:RF-1 / 067:RF-2 / 067:RF-3 / 067:RF-5 — el informe sale de su ruta y la revisión lo encuentra."""
    cliente, app = api
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (obra_en('obras'), None))
    monkeypatch.setattr(services, 'informe_estudio', informe_del_motor)
    wid, ws = espacio(cliente, app)
    ws.loaded_source_fingerprint, ws.loaded_source_mode = 'huella-txt', 'txt'
    assert lanzar_informe(cliente, wid)['status'] == 'done'
    plan = proponer(cliente, wid)
    peticiones = ollama_de_prueba(monkeypatch)
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/revision", json={'max_rondas': 1})
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert fin['result']['aprobada'] and not fin['result']['autoriza_ejecucion']
    assert len(peticiones) == 4
    evidencia = json.loads(peticiones[0]['messages'][-1]['content'])['evidencia']
    fila = next(iter(evidencia.values()))
    # 047:RF-38 a RF-41: al LLM solo le llega el localizador y el fragmento; su proyecto y su fuente se cruzan antes,
    # porque el nombre del caso le decía la respuesta.
    assert 'proyecto' not in fila and 'fuente' not in fila
    assert hashlib.sha256(b'documento real del trabajo').hexdigest() in fila['fragmento']


def test_evidencia_usa_la_huella_del_vinculo_del_proyecto(api, monkeypatch):
    """067:RF-3 — tras reiniciar no hay fuente en memoria, pero el proyecto sigue vinculado a la suya."""
    from convertersmartgrid.asistente.observacion import leer_evidencias

    cliente, app = api
    monkeypatch.setattr(services, 'informe_estudio', informe_del_motor)
    wid, ws = espacio(cliente, app)
    ws.loaded_source_fingerprint = None
    ws.pf_project_bindings['P1'] = {'source_fingerprint': 'huella-vinculo'}
    assert lanzar_informe(cliente, wid)['status'] == 'done'
    contexto = leer_evidencias(ws.out_dir)[0]['informe']['contexto']
    assert contexto == {**contexto, 'project': 'P1', 'source_fingerprint': 'huella-vinculo'}


@pytest.mark.parametrize('resultado, fuente', [({'informe': 'x.docx'}, 'huella'), ({'project': 'P1'}, None)])
def test_evidencia_sin_proyecto_o_sin_fuente_no_se_inventa(api, monkeypatch, resultado, fuente):
    """067:RF-4 — sin proyecto o sin huella no se custodia y el Registro lo dice."""
    from convertersmartgrid.asistente.observacion import leer_evidencias

    cliente, app = api
    monkeypatch.setattr(services, 'informe_estudio', lambda *_a: resultado)
    wid, ws = espacio(cliente, app)
    ws.loaded_source_fingerprint = fuente
    assert lanzar_informe(cliente, wid)['status'] == 'done'
    assert leer_evidencias(ws.out_dir) == []
    assert any('no se custodia' in e['data'].get('text', '') for e in ws.events.since(0) if e['type'] == 'log')


def test_evidencia_de_trabajo_fallido_no_se_custodia(api, monkeypatch):
    """067:RF-1 — solo lo que terminó bien es evidencia."""
    from convertersmartgrid.asistente.observacion import leer_evidencias
    from convertersmartgrid.web.jobs import JobCancelled

    cliente, app = api

    def falla(*_a):
        raise JobCancelled()

    monkeypatch.setattr(services, 'informe_estudio', falla)
    wid, ws = espacio(cliente, app)
    ws.loaded_source_fingerprint = 'huella'
    assert lanzar_informe(cliente, wid)['status'] != 'done'
    assert leer_evidencias(ws.out_dir) == []


def test_evidencia_ausente_dice_que_busco_sin_llamar_al_modelo(api, monkeypatch):
    """067:RF-6 — el motivo nombra el proyecto y la fuente buscados; no se fabrica consenso."""
    cliente, app = api
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (obra_en('obras'), None))
    wid, ws = espacio(cliente, app)
    ws.loaded_source_fingerprint = 'huella-buscada'
    plan = proponer(cliente, wid)
    peticiones = ollama_de_prueba(monkeypatch)
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/revision", json={})
    fin = esperar(cliente, r.json()['id'])
    assert not fin['result']['aprobada'] and not peticiones
    assert 'P1' in fin['result']['motivo'] and 'huella-buscada' in fin['result']['motivo']


def test_evidencia_visible_en_el_equipo(api, monkeypatch):
    """067:RF-7 — el estado del equipo lista lo custodiado, sin el contenido del informe."""
    cliente, app = api
    monkeypatch.setattr(services, 'informe_estudio', informe_del_motor)
    wid, ws = espacio(cliente, app)
    ws.loaded_source_fingerprint = 'huella'
    assert lanzar_informe(cliente, wid)['status'] == 'done'
    filas = cliente.get(f'/api/workspaces/{wid}/asistente/equipo').json()['evidencias']
    assert len(filas) == 1 and filas[0]['proyecto'] == 'P1' and 'informe' not in filas[0]


# ------------------------------------------------------------------ modelo que respondió
class OllamaDoble:
    modelo = 'modelo-local'
    revisar_transformer = False

    def __init__(self, tarea='estado'):
        self.tarea = tarea

    def interpretar(self, texto, contexto=()):
        if self.tarea is None:
            return None
        return {'tarea': self.tarea, 'confianza': 0.9, 'modelo': self.modelo, 'datos': {}}


def test_aviso_sin_gpu_sigue_con_ollama_y_dice_el_motivo(entorno, monkeypatch):
    """067:RF-8 / 067:RF-9 / 067:RF-10 — sin GPU no se corta el servicio ni se calla."""
    from convertersmartgrid.asistente import ollama, transformer

    def sin_gpu(*_a):
        raise RuntimeError('No hay GPU CUDA para el gemelo digital')

    monkeypatch.setattr(transformer, 'cargar', sin_gpu)
    monkeypatch.setattr(ollama, 'cliente_configurado', lambda **_k: OllamaDoble())
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        wid, _ws = espacio(cliente, app)
        plan = proponer(cliente, wid, 'estado del espacio')
    assert plan['tarea'] == 'estado' and plan['interpretado_por'] == 'modelo-local'
    aviso = ' '.join(plan['avisos'])
    assert 'No hay GPU CUDA' in aviso and 'modelo-local' in aviso


def test_aviso_sin_ningun_modelo_lo_dice(entorno, monkeypatch):
    """067:RF-10 — si tampoco responde Ollama, el plan dice que no respondió ninguno."""
    from convertersmartgrid.asistente import ollama, transformer

    def sin_gpu(*_a):
        raise RuntimeError('No hay GPU CUDA')

    monkeypatch.setattr(transformer, 'cargar', sin_gpu)
    monkeypatch.setattr(ollama, 'cliente_configurado', lambda **_k: OllamaDoble(None))
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        wid, _ws = espacio(cliente, app)
        plan = proponer(cliente, wid, 'estado del espacio')
    assert plan['tarea'] is None and 'no respondió ninguno' in ' '.join(plan['avisos'])


def test_aviso_no_aparece_con_el_transformer_en_uso(api):
    """067:RF-9 — con el Transformer cargado no hay nada que avisar."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    assert proponer(cliente, wid)['avisos'] == []


def test_aviso_se_muestra_en_la_consola():
    """067:RF-11 — el plan de la consola enseña sus avisos como alerta."""
    fuente = (RAIZ / 'frontend/src/components/Asistente.tsx').read_text(encoding='utf-8')
    assert 'plan.avisos' in fuente and 'alert alert-warn' in fuente


# ------------------------------------------------------------------ planes guardados
def reiniciar_web(entorno):
    """Otra aplicación sobre los mismos datos y sin nada en memoria: lo que hace un reinicio."""
    services._ASISTENTE_PLANES.clear()
    return create_app(entorno / 'web')


def test_guardado_atomico_por_espacio_no_deja_medias(entorno, monkeypatch):
    """067:RF-12 — si falla la publicación, el fichero anterior queda intacto."""
    from convertersmartgrid.asistente.equipo import GobiernoEquipo
    from convertersmartgrid.asistente.plan import Plan
    from convertersmartgrid.asistente.planes_guardados import PlanesGuardados
    from convertersmartgrid.web.workspace import WorkspaceStore

    ws = WorkspaceStore(entorno / 'w').create()
    otro = WorkspaceStore(entorno / 'w').create()
    plan = Plan('a' * 12, 'orden', 'gemelo_entrenar', True, 'trabajo')
    guardados = PlanesGuardados(ws.root)
    guardados.guardar(plan, {}, GobiernoEquipo.desde_plan(ws, plan))
    antes = (ws.root / 'asistente_planes' / f'{plan.id}.json').read_bytes()
    assert PlanesGuardados(otro.root).listar() == []

    def falla(*_a):
        raise OSError('disco lleno')

    monkeypatch.setattr(os, 'replace', falla)
    plan.razonamiento.append('cambio')
    with pytest.raises(OSError):
        guardados.guardar(plan, {}, GobiernoEquipo.desde_plan(ws, plan))
    assert (ws.root / 'asistente_planes' / f'{plan.id}.json').read_bytes() == antes


def test_guardado_tras_reinicio_pide_confirmacion_y_no_reanuda(entorno, monkeypatch):
    """067:RF-13 / 067:RF-14 / 067:RF-19 — tras reiniciar se ofrece, no se ejecuta, y confirmado corre."""
    llamadas = []
    monkeypatch.setattr(services, 'gemelo_entrenar', lambda *_a, **_k: llamadas.append(1) or {'entrenado': False})
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(), None))
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        wid, _ws = espacio(cliente, app)
        plan = proponer(cliente, wid)
    app2 = reiniciar_web(entorno)
    with TestClient(app2) as cliente:
        app2.state.asistente_http = cliente
        filas = cliente.get(f'/api/workspaces/{wid}/asistente/planes').json()['planes']
        assert [f['id'] for f in filas] == [plan['id']]
        assert filas[0]['guardado']['vigente'] is True and not filas[0]['equipo']['confirmada']
        assert not llamadas
        fin = esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert llamadas == [1]


def test_guardado_con_contexto_cambiado_se_rechaza(entorno, monkeypatch):
    """067:RF-15 — el plan guardado no vale sobre otra fuente; lo que sigue vigente lo dice el listado."""
    llamadas = []
    monkeypatch.setattr(services, 'gemelo_entrenar', lambda *_a, **_k: llamadas.append(1))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(), None))
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        wid, ws = espacio(cliente, app)
        ws.loaded_source_fingerprint = 'fuente-al-proponer'
        plan = proponer(cliente, wid)
    app2 = reiniciar_web(entorno)
    with TestClient(app2) as cliente:
        app2.state.asistente_http = cliente
        fila = cliente.get(f'/api/workspaces/{wid}/asistente/planes').json()['planes'][0]
        assert fila['guardado']['vigente'] is False and 'contexto' in fila['guardado']['motivo']
        fin = esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'failed' and 'contexto' in fin['error'] and not llamadas


def test_guardado_interrumpido_se_ofrece_sin_confirmacion(entorno, monkeypatch):
    """067:RF-16 — lo que se cortó a mitad se dice y hay que volver a confirmarlo."""
    from convertersmartgrid.asistente.planes_guardados import PlanesGuardados

    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(), None))
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        wid, ws = espacio(cliente, app)
        plan = proponer(cliente, wid)
    PlanesGuardados(ws.root).marcar(plan['id'], 'ejecutando')
    app2 = reiniciar_web(entorno)
    with TestClient(app2) as cliente:
        fila = cliente.get(f'/api/workspaces/{wid}/asistente/planes').json()['planes'][0]
    assert fila['guardado']['estado'] == 'interrumpido' and not fila['equipo']['confirmada']


def test_guardado_se_retira_al_terminar_y_no_se_repite(api, monkeypatch):
    """067:RF-17 / 067:RF-18 — la escritura hecha no queda ofrecida ni se puede confirmar otra vez."""
    llamadas = []
    monkeypatch.setattr(services, 'gemelo_entrenar', lambda *_a, **_k: llamadas.append(1) or {'entrenado': False})
    cliente, app = api
    wid, ws = espacio(cliente, app)
    plan = proponer(cliente, wid)
    ruta = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert esperar(cliente, ruta.json()['id'])['status'] == 'done'
    assert llamadas == [1] and not (ws.root / 'asistente_planes' / f"{plan['id']}.json").exists()
    assert cliente.get(f'/api/workspaces/{wid}/asistente/planes').json()['planes'] == []
    segunda = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    if segunda.status_code == 202:
        assert esperar(cliente, segunda.json()['id'])['status'] == 'failed'
    assert llamadas == [1]


def test_guardado_rechazo_y_correccion_lo_retiran(api):
    """067:RF-17 — rechazar o corregir revoca también el plan del disco."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    primero = proponer(cliente, wid)
    nuevo = cliente.post(f"/api/workspaces/{wid}/asistente/{primero['id']}/corregir", json={'tarea': 'gemelo_entrenar'}).json()['plan']
    ids = [f['id'] for f in cliente.get(f'/api/workspaces/{wid}/asistente/planes').json()['planes']]
    assert ids == [nuevo['id']]
    assert cliente.post(f"/api/workspaces/{wid}/asistente/{nuevo['id']}/rechazar").status_code == 200
    assert cliente.get(f'/api/workspaces/{wid}/asistente/planes').json()['planes'] == []


def test_guardado_no_sale_de_su_carpeta_por_el_identificador(entorno):
    """067:RF-12 — el identificador llega por la URL: nunca compone una ruta fuera de la carpeta."""
    from convertersmartgrid.asistente.planes_guardados import PlanesGuardados

    assert PlanesGuardados(entorno).leer('../../secreto') is None


def test_guardado_en_la_consola():
    """067:RF-19 — la consola pide los planes guardados del espacio."""
    fuente = (RAIZ / 'frontend/src/components/Asistente.tsx').read_text(encoding='utf-8')
    assert 'asistentePlanes' in fuente and 'asistentePlanes' in (RAIZ / 'frontend/src/api.ts').read_text(encoding='utf-8')


# ------------------------------------------------------------------ modelos en uso
def candidato(entorno, nombre='uno', estado='PROMOVIDO', familia='transformer'):
    from convertersmartgrid.model_registry import RegistroModelo

    origen = entorno / f'origen-{nombre}'
    origen.mkdir()
    (origen / 'pesos.pt').write_bytes(f'pesos-{nombre}'.encode())
    (origen / 'modelo.json').write_text(json.dumps({'version': 'alumno', 'nombre': nombre}), encoding='utf-8')
    aprobado = estado == 'PROMOVIDO'
    registro = RegistroModelo(almacen.raiz() / 'model_registry')
    return registro, registro.registrar_candidato(
        familia, model_manifest={'algorithm': nombre}, dataset_manifest={}, metrics={},
        decision={'status': estado, 'gates': {'approved': aprobado}, 'fallos': [] if aprobado else ['no pasa']},
        smoke_reload={'ok': True}, artifacts=[origen / 'pesos.pt', origen / 'modelo.json'])


def en_uso(nombre='ordenes'):
    from convertersmartgrid.asistente import transformer

    return transformer.version_promovida(nombre)


def carpeta_legada(version, nombre='ordenes'):
    from convertersmartgrid.asistente import transformer

    carpeta = transformer.raiz_modelos(nombre) / version
    carpeta.mkdir(parents=True)
    (carpeta / 'modelo.json').write_text('{}', encoding='utf-8')
    (carpeta / 'pesos.pt').write_bytes(b'pesos del modelo heredado')
    transformer.promover(version, 'heredado', nombre)


def test_uso_candidato_aprobado_cambia_el_puntero_y_conserva_el_anterior(entorno):
    """067:RF-20 / 067:RF-22 — el puntero apunta a una copia verificada y el anterior sigue en disco."""
    from convertersmartgrid.asistente import modelos_en_uso, transformer

    carpeta_legada('heredado')
    registro, c = candidato(entorno)
    r = modelos_en_uso.aplicar_decision('transformer', c)
    assert r['promovido'] is True and en_uso() == r['version'] != 'heredado'
    assert registro.activo('transformer')['candidate_id'] == c['candidate_id']
    assert (transformer.raiz_modelos() / r['version'] / 'pesos.pt').read_bytes() == b'pesos-uno'
    assert (transformer.raiz_modelos() / 'heredado' / 'pesos.pt').is_file()
    puntero = json.loads((transformer.raiz_modelos() / 'promovido.json').read_text(encoding='utf-8'))
    assert puntero['anterior'] == 'heredado'


def test_uso_artefacto_alterado_no_entra(entorno):
    """067:RF-21 — el registro compara huellas antes de tocar el puntero."""
    from convertersmartgrid.asistente import modelos_en_uso

    carpeta_legada('heredado')
    _registro, c = candidato(entorno)
    (Path(c['path']) / 'artifacts' / 'pesos.pt').write_bytes(b'manipulado')
    r = modelos_en_uso.aplicar_decision('transformer', c)
    assert r['promovido'] is False and 'integridad' in r['motivo'] and en_uso() == 'heredado'


def test_uso_vuelve_al_anterior_con_puntero_y_registro_de_acuerdo(entorno):
    """067:RF-23 — volver a un candidato o a un modelo heredado deja las dos piezas coherentes."""
    from convertersmartgrid.asistente import modelos_en_uso

    carpeta_legada('heredado')
    registro, uno = candidato(entorno, 'uno')
    _r, dos = candidato(entorno, 'dos')
    primera = modelos_en_uso.aplicar_decision('transformer', uno)
    modelos_en_uso.aplicar_decision('transformer', dos)
    assert modelos_en_uso.volver_al_anterior('transformer') == primera['version']
    assert en_uso() == primera['version']
    assert registro.activo('transformer')['candidate_id'] == uno['candidate_id']
    # Ahora, hasta el modelo heredado, que no está en el registro: no queda ningún activo falso.
    from convertersmartgrid.asistente import transformer
    puntero = transformer.raiz_modelos() / 'promovido.json'
    fila = json.loads(puntero.read_text(encoding='utf-8'))
    puntero.write_text(json.dumps({**fila, 'anterior': 'heredado'}), encoding='utf-8')
    assert modelos_en_uso.volver_al_anterior('transformer') == 'heredado'
    assert en_uso() == 'heredado' and registro.activo('transformer') is None


def test_uso_servicio_vuelve_por_la_misma_via(entorno):
    """067:RF-23 — el botón de volver de la web no deja el registro atrás."""
    from convertersmartgrid.asistente import modelos_en_uso

    carpeta_legada('heredado')
    registro, c = candidato(entorno)
    modelos_en_uso.aplicar_decision('transformer', c)
    assert services.volver_al_modelo_anterior('asistente')['version'] == 'heredado'
    assert registro.activo('transformer') is None


@pytest.mark.parametrize('estado', ['RECHAZADO', 'BLOQUEADO_POR_DATOS', 'ERROR_ENTORNO'])
def test_uso_candidato_no_aprobado_deja_el_modelo_actual(entorno, estado):
    """067:RF-24 — solo PROMOVIDO del registro pasa a uso."""
    from convertersmartgrid.asistente import modelos_en_uso

    carpeta_legada('heredado')
    registro, c = candidato(entorno, estado=estado)
    r = modelos_en_uso.aplicar_decision('transformer', c)
    assert r['promovido'] is False and r['en_uso'] == 'heredado' == en_uso()
    assert registro.activo('transformer') is None


def test_uso_puerta_de_comparacion_mide_el_modelo_activo(entorno, monkeypatch):
    """067:RF-25 — la puerta recibe la medida real por familia, y una regresión sigue rechazando."""
    from convertersmartgrid.asistente import destilacion_integral as di
    from convertersmartgrid.asistente import transformer
    from convertersmartgrid.asistente.tareas import TAREAS

    class Activo:
        def predecir(self, texto):
            return {'tarea': texto, 'datos': {}}

    monkeypatch.setattr(transformer, 'cargar', lambda *_a: Activo())
    filas = [{'texto': t, 'tarea': t, 'datos': []} for t in sorted(TAREAS)]
    referencia = di._referencia_activa(filas)
    assert set(referencia) == set(TAREAS) and referencia['estado']['acierto_tarea'] == 1

    perfecto = {'ejemplos': 3, 'acierto_tarea': 1.0, 'f1_datos': 1.0}
    familias = {t: dict(perfecto) for t in TAREAS}
    rechazo = {'ejemplos': 200, 'rechazada': 1., 'se_cuela': 0.}                     # 069:RF-17: puerta adicional
    assert di.decidir_promocion(perfecto, perfecto, familias, referencia, rechazo)['status'] == 'PROMOVIDO'
    assert di.decidir_promocion(perfecto, perfecto, familias, None, rechazo)['status'] == 'RECHAZADO'
    peor = {**familias, 'estado': {'ejemplos': 3, 'acierto_tarea': 0.96, 'f1_datos': 1.0}}
    d = di.decidir_promocion(perfecto, perfecto, peor, referencia, rechazo)
    assert d['status'] == 'RECHAZADO' and any('regresión' in f for f in d['fallos'])


def test_uso_sin_modelo_activo_no_inventa_referencia(entorno, monkeypatch):
    """067:RF-25 — si el modelo no se puede medir, la puerta sigue sin aprobar."""
    from convertersmartgrid.asistente import destilacion_integral as di
    from convertersmartgrid.asistente import transformer

    def falla(*_a):
        raise RuntimeError('sin GPU')

    monkeypatch.setattr(transformer, 'cargar', falla)
    assert di._referencia_activa([{'texto': 'x', 'tarea': 'estado', 'datos': []}]) is None


def herramienta_entrenar():
    spec = importlib.util.spec_from_file_location('asistente_entrenar_prueba', RAIZ / 'tools/asistente_entrenar.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def preparar_integral(entorno, monkeypatch, estado):
    """El entrenamiento, sustituido: se comprueba lo que la herramienta hace con su decisión."""
    from convertersmartgrid.asistente import clasificador, destilacion_integral as di

    _registro, c = candidato(entorno, estado=estado)
    monkeypatch.setattr(di, 'preparar_corpus', lambda *_a, **_k: ([], {}))
    monkeypatch.setattr(di, 'guardar_corpus', lambda *_a, **_k: None)
    monkeypatch.setattr(di, 'entrenar_destilacion', lambda *_a, **_k: {
        'status': estado, 'promovido': False, 'candidato': c, 'decision': {'fallos': ['no pasa']}})
    monkeypatch.setattr(clasificador, 'entrenar', lambda *_a, **_k: pytest.fail('sin informes reales no se entrena'))


@pytest.mark.parametrize('estado, entra', [('PROMOVIDO', True), ('BLOQUEADO_POR_DATOS', False)])
def test_uso_reentrenar_aplica_la_decision_del_registro(entorno, monkeypatch, estado, entra):
    """067:RF-20 / 067:RF-24 / 067:RF-26 / 067:RF-27 — la herramienta de la web pone en uso solo lo aprobado."""
    carpeta_legada('heredado')
    preparar_integral(entorno, monkeypatch, estado)
    salida = entorno / 'informe.json'
    codigo = herramienta_entrenar().main(['--output-json', str(salida), '--integral'])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert codigo == 0, informe
    assert informe['ordenes']['promovido'] is entra and (en_uso() != 'heredado') is entra
    assert informe['informes']['status'] == 'BLOQUEADO_POR_DATOS' and informe['informes']['entrenado'] is False


@pytest.mark.parametrize('rechazado', [
    {'acierto_tipo':1.,'acierto_subtipo':.5,'ejemplos':9},
    {'acierto_tipo':.2,'acierto_subtipo':.99,'ejemplos':9},
])
def test_uso_clasificador_con_informes_reales_va_por_el_registro(entorno, monkeypatch, rechazado):
    """067:RF-26 — con prueba real se entrena, se registra y se pone en uso por la misma vía."""
    from convertersmartgrid.asistente import clasificador as cl
    from convertersmartgrid.model_registry import RegistroModelo

    carpeta_legada('heredado', 'informes')
    for i in range(5):
        cl.registrar(f'informe real {i}', 'estudio', 'refuerzo de red', 'generado')

    class Candidato:
        red = None
        subtipos = ['refuerzo de red']
        version = ''

    def guardar(modelo, carpeta):
        carpeta.mkdir(parents=True)
        (carpeta / 'pesos.pt').write_bytes(b'pesos')
        (carpeta / 'modelo.json').write_text('{}', encoding='utf-8')

    monkeypatch.setattr(cl, 'entrenar', lambda *_a, **_k: Candidato())
    monkeypatch.setattr(cl, 'evaluar', lambda *_a: {'acierto_tipo': 1.0, 'acierto_subtipo': 0.97, 'ejemplos': 9})
    monkeypatch.setattr(cl, 'cargar', lambda: None)
    monkeypatch.setattr(cl, 'guardar_candidato', guardar)
    registro = RegistroModelo(almacen.raiz() / 'model_registry')
    r = cl.entrenar_gobernado(registro, entorno / 'candidato', reabrir=lambda _c: {'ok': True})
    assert r['status'] == 'PROMOVIDO' and r['promovido'] is True and en_uso('informes') != 'heredado'
    monkeypatch.setattr(cl, 'evaluar', lambda *_a: rechazado)
    antes = en_uso('informes')
    r = cl.entrenar_gobernado(registro, entorno / 'candidato2', reabrir=lambda _c: {'ok': True})
    assert r['status'] == 'RECHAZADO' and r['promovido'] is False and en_uso('informes') == antes


def test_clasificador_heredado_no_activa_un_tipo_incorrecto(monkeypatch):
    """026:RF-16: la compatibilidad heredada conserva también la puerta del primer nivel."""
    from types import SimpleNamespace
    from convertersmartgrid.asistente import clasificador as cl
    muestra=('texto de entrenamiento','estudio','refuerzo de red')
    monkeypatch.setattr(cl,'reales',lambda:([muestra],[('texto reservado','estudio','refuerzo de red')]))
    monkeypatch.setattr(cl,'subtipos_del_perfil',lambda:['refuerzo de red'])
    monkeypatch.setattr(cl,'generar',lambda *a,**k:[muestra])
    monkeypatch.setattr(cl,'entrenar',lambda *a,**k:SimpleNamespace(
        red=None,cfg=cl.Configuracion(epocas=1),simbolos={},subtipos=['refuerzo de red'],version=''))
    monkeypatch.setattr(cl,'evaluar',lambda *a:{'acierto_tipo':.2,'acierto_subtipo':.99,'ejemplos':1})
    monkeypatch.setattr(cl,'cargar',lambda:None)
    monkeypatch.setattr(cl,'guardar_pesos',lambda *a:'candidato-de-contrato')
    activaciones=[]
    monkeypatch.setattr(cl,'promover',lambda *a:activaciones.append(a))
    result=cl.entrenar_y_promover()
    assert result['promovido'] is False and not activaciones


def test_uso_descripcion_de_reentrenar_dice_la_verdad():
    """067:RF-28 — el clasificador solo se entrena con informes reales, y la tarea lo dice."""
    from convertersmartgrid.asistente.tareas import TAREAS

    assert 'informes reales' in TAREAS['entrenar_asistente'].descripcion


def test_uso_estado_de_modelos_dice_la_version(entorno):
    """067:RF-29 — la versión en uso se lee, y un activo del registro no se presenta como heredado."""
    from convertersmartgrid.asistente import modelos_en_uso

    carpeta_legada('heredado')
    _registro, c = candidato(entorno)
    version = modelos_en_uso.aplicar_decision('transformer', c)['version']
    fila = next(f for f in services.asistente_estado_modelos()['familias'] if f['familia'] == 'transformer')
    assert fila['en_uso'] == version and fila['estado'] == 'PROMOVIDO'
    assert fila['heredado'] is None and not any('heredado' in b for b in fila['bloqueos'])


# ------------------------------------------------------------------ tareas
@pytest.mark.parametrize('tarea, funcion, ruta_titulo', [
    ('obras_escalera', 'obras_escalera', 'escalera'),
    ('optimizar_con_proyecto', 'con_proyecto_optimizar', 'Con proyecto')])
def test_tarea_nueva_por_su_ruta_con_confirmacion(api, monkeypatch, tarea, funcion, ruta_titulo):
    """067:RF-30 / 067:RF-31 / 067:RF-32 — la orden espera confirmación y luego va por la ruta de la web."""
    llamadas = []
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (obra_en(tarea), None))
    monkeypatch.setattr(services, funcion, lambda ws, ctx, project, feeders, **kw: (
        llamadas.append((project, feeders)) or {'project': project}))
    cliente, app = api
    wid, ws = espacio(cliente, app)
    plan = proponer(cliente, wid)
    assert plan['tarea'] == tarea and plan['escribe'] and plan['listo'] and not llamadas
    assert not plan['equipo']['permiso_efectivo']
    fin = esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert llamadas == [('P1', ['F1'])]
    trabajos = [j.public() for j in app.state.jobs.list(wid)]
    hijo = next(j for j in trabajos if ruta_titulo in j['title'] and j['kind'] != 'asistente')
    assert hijo['lane'] == 'powerfactory'


def test_tarea_nueva_con_otra_fuente_no_se_ejecuta(api, monkeypatch):
    """067:RF-32 — el contexto sellado también vale para las tareas nuevas."""
    llamadas = []
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (obra_en('obras_escalera'), None))
    monkeypatch.setattr(services, 'obras_escalera', lambda *_a, **_k: llamadas.append(1))
    cliente, app = api
    wid, ws = espacio(cliente, app)
    plan = proponer(cliente, wid)
    ws.loaded_source_fingerprint = 'otra-fuente'
    fin = esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'failed' and 'contexto' in fin['error'] and not llamadas


def test_tarea_carril_declarado_de_digsilent():
    """067:RF-33 — el inventario dice el carril real de las tres."""
    from convertersmartgrid.asistente.equipo import inventario_equipo

    carriles = {h['herramienta']: h['carril'] for h in inventario_equipo()['herramientas']}
    for t in ('obras_escalera', 'optimizar_con_proyecto', 'informe_factibilidad'):
        assert carriles[t] == 'powerfactory', t


def test_tarea_factibilidad_avisa_de_la_carga_inexistente(api, monkeypatch):
    """067:RF-34 — lo que la ruta rechazaría se dice antes de ofrecer confirmar."""
    from convertersmartgrid.web.services import UserError

    def no_existe(*_a):
        raise UserError('S1 no es una carga nueva aplicada')

    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer('informe_factibilidad', {
        'proyecto': [{'valor': 'P1'}], 'alimentadores': [{'valor': 'F1'}], 'sed': [{'valor': 'S1'}]}), None))
    monkeypatch.setattr(services, 'carga_del_informe', no_existe)
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'lugar': 'x'}}
    plan = proponer(cliente, wid)
    assert not plan['listo'] and any('no es una carga nueva' in f for f in plan['faltan'])


def test_tarea_factibilidad_llega_a_su_ruta(api, monkeypatch):
    """067:RF-33 — la tarea de factibilidad ya existía: su cuerpo pasa la validación real de la ruta."""
    llamadas = []
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer('informe_factibilidad', {
        'proyecto': [{'valor': 'P1'}], 'alimentadores': [{'valor': 'F1'}], 'sed': [{'valor': 'S1'}]}), None))
    monkeypatch.setattr(services, 'carga_del_informe', lambda *_a: {'sola': True})
    monkeypatch.setattr(services, 'informe_factibilidad', lambda ws, ctx, f: (
        llamadas.append(f['sed']) or {'project': f['project'], 'informe': 'f.docx'}))
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'solicitud': {
        'cliente': 'c', 'ubicacion': 'u', 'tipo_solicitud': 't', 'potencia_kw': 10, 'fecha_solicitud': '2026-11-02',
        'set_nombre': 's', 'tension_kv': 10}}}
    plan = proponer(cliente, wid)
    assert plan['listo'], plan['faltan']
    fin = esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert llamadas == ['S1']


def test_tarea_ejemplos_en_todos_los_conjuntos_sin_tocar_pesos():
    """067:RF-35 — plantillas, frases del maestro, currículo y propuestas cubren las tareas nuevas."""
    from convertersmartgrid.asistente.curriculo_llm_real import PRUEBA_NUEVA
    from convertersmartgrid.asistente.curriculo_maestro import FAMILIAS
    from convertersmartgrid.asistente.ordenes_fijas import FRASES
    from convertersmartgrid.asistente.propuestas_maestro import PLANTILLAS, generar_propuestas
    from convertersmartgrid.asistente.tareas import TAREAS

    for tarea in ('obras_escalera', 'optimizar_con_proyecto'):
        assert TAREAS[tarea].plantillas and FRASES[tarea] and PLANTILLAS[tarea] and PRUEBA_NUEVA[tarea]
        assert len(FAMILIAS[tarea]) == 4
    filas, _meta = generar_propuestas()
    assert {r['tarea'] for r in filas} == set(TAREAS)


@pytest.mark.parametrize('texto, esperada', [
    ('haz la escalera de obras en P1 F1', 'obras_escalera'),
    ('Optimiza «Con proyecto» de P1 F1', 'optimizar_con_proyecto'),
    ('optimizar con proyecto P1', 'optimizar_con_proyecto'),
    ('¿qué es la escalera de obras?', 'estado'),
    ('como funciona la escalera', 'estado')])
def test_tarea_por_frase_literal_con_modelo_que_no_la_conoce(texto, esperada):
    """067:RF-36 — el modelo en uso no aprendió la tarea nueva: la frase literal lleva a un plan por confirmar."""
    from convertersmartgrid.asistente.interprete import interpretar

    i = interpretar(texto, transformer=Transformer('estado'))
    assert i.tarea == esperada


def test_tarea_conocida_decide_el_modelo():
    """067:RF-36 — cuando el modelo ya conoce la tarea, la regla no interviene."""
    from convertersmartgrid.asistente.interprete import interpretar

    m = Transformer('obras')
    m.tareas = ('obras', 'obras_escalera', 'optimizar_con_proyecto')
    assert interpretar('la escalera de obras', transformer=m).tarea == 'obras'


# ------------------------------------------------------------------ lista del proyecto entero
DATOS_PROYECTO = {'sistema': 'S1', 'periodo': '2026-07'}


def pedir_lista(cliente, wid, **extra):
    r = cliente.post(f'/api/workspaces/{wid}/agente/proyecto/lista', json={**DATOS_PROYECTO, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_lista_de_etapas_antes_del_clic(api):
    """067:RF-37 — las que escriben, las ya hechas y las que se omitirán, sin ejecutar nada."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    lista = pedir_lista(cliente, wid)
    por_nombre = {e['nombre']: e for e in lista['etapas']}
    assert por_nombre['estudios']['escribe'] is True and por_nombre['estudios']['estado'] == 'pendiente'
    assert por_nombre['cargas_nuevas']['estado'] == 'se_omitira' and 'ruta_cargas' in por_nombre['cargas_nuevas']['falta']
    assert 'proyecto' not in por_nombre['caso_base']['falta']
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.out_dir / 'agente_proyecto.json').write_text(json.dumps({'etapas': {'fuente': {'estado': 'hecha'}}}), encoding='utf-8')
    otra = pedir_lista(cliente, wid)
    assert next(e for e in otra['etapas'] if e['nombre'] == 'fuente')['estado'] == 'hecha'
    assert otra['confirmacion'] != lista['confirmacion']
    assert not [j for j in app.state.jobs.list(wid) if j.kind == 'agente_proyecto']


def test_lista_sin_confirmacion_no_encola(api, monkeypatch):
    """067:RF-38 — sin la huella de la lista, ni con otra, no se encola."""
    llamadas = []
    monkeypatch.setattr(services, 'agente_proyecto', lambda *_a, **_k: llamadas.append(1))
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    ruta = f'/api/workspaces/{wid}/agente/proyecto'
    assert cliente.post(ruta, json=DATOS_PROYECTO).status_code == 422
    assert cliente.post(ruta, json={**DATOS_PROYECTO, 'confirmacion': '0' * 64}).status_code == 409
    assert not llamadas


def test_lista_vigente_confirma_y_queda_anotada(api, monkeypatch):
    """067:RF-37 — con la huella mostrada se encola una vez, y la decisión queda con sus etapas."""
    llamadas = []
    monkeypatch.setattr(services, 'agente_proyecto', lambda ws, ctx, datos, base, http=None, reiniciar=False: (
        llamadas.append(datos) or {'completo': True}))
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    lista = pedir_lista(cliente, wid)
    r = cliente.post(f'/api/workspaces/{wid}/agente/proyecto', json={**DATOS_PROYECTO, 'confirmacion': lista['confirmacion']})
    assert r.status_code == 202, r.text
    assert esperar(cliente, r.json()['id'])['status'] == 'done'
    assert llamadas == [DATOS_PROYECTO]
    decision = almacen.leer('decisiones')[-1]
    assert decision['decision'] == 'lista_confirmada' and 'estudios' in decision['etapas_escritura']


@pytest.mark.parametrize('cambio', ['fuente', 'datos', 'etapas'])
def test_lista_que_cambio_se_rechaza(api, monkeypatch, cambio):
    """067:RF-39 — fuente, datos o etapas distintos de lo que vio el operador invalidan la huella."""
    monkeypatch.setattr(services, 'agente_proyecto', lambda *_a, **_k: pytest.fail('no debía encolarse'))
    cliente, app = api
    wid, ws = espacio(cliente, app)
    lista = pedir_lista(cliente, wid)
    cuerpo = {**DATOS_PROYECTO, 'confirmacion': lista['confirmacion']}
    if cambio == 'fuente':
        ws.loaded_source_fingerprint = 'otra'
    elif cambio == 'datos':
        cuerpo['periodo'] = '2026-08'
    else:
        ws.out_dir.mkdir(parents=True, exist_ok=True)
        (ws.out_dir / 'agente_proyecto.json').write_text(json.dumps({'etapas': {'fuente': {'estado': 'hecha'}}}), encoding='utf-8')
    assert cliente.post(f'/api/workspaces/{wid}/agente/proyecto', json=cuerpo).status_code == 409


def test_lista_inventario_dice_la_verdad():
    """067:RF-40 — el inventario declara la lista única y qué herramientas cubre."""
    from convertersmartgrid.asistente.equipo import inventario_equipo
    from convertersmartgrid.asistente.orquestador import ETAPAS

    inventario = inventario_equipo()
    proyecto = inventario['proyecto_entero']
    assert proyecto['confirmacion'] == 'lista_unica_mostrada' and proyecto['confirmacion_por_etapa'] is False
    assert set(proyecto['etapas_escritura']) == {e.nombre for e in ETAPAS}
    filas = {h['herramienta']: h for h in inventario['herramientas']}
    assert filas['estudios']['confirmacion_en_proyecto'] == 'lista_unica_mostrada'
    assert filas['convertir']['confirmacion_en_proyecto'] is None


def test_lista_en_la_consola():
    """067:RF-37 — la consola enseña la lista antes del botón y manda su huella."""
    fuente = (RAIZ / 'frontend/src/components/Asistente.tsx').read_text(encoding='utf-8')
    assert 'agenteProyectoLista' in fuente and 'confirmacion: lista.confirmacion' in fuente
