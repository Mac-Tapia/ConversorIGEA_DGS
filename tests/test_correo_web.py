"""Spec 110: rutas del correo montadas en una FastAPI de prueba, con el proveedor y las credenciales simulados."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from correo_simulado import CompartidorSimulado, CredencialesSimuladas, ProveedorSimulado, sin_red  # noqa: F401
from test_correo_borrador import _informe_cerrado

from convertersmartgrid.aplicacion.asistente.equipo import PermisoDenegado
from convertersmartgrid.presentacion.web import correo_api
from convertersmartgrid.presentacion.web.jobs import LANES
from convertersmartgrid.presentacion.web.seguridad import _SinCorreoEnElRegistro, enmascarar_correo

ORIGEN = {'Origin': 'http://testserver'}
_DIRECCION = re.compile(r'[a-z0-9._%+-]{2,}@[a-z0-9.-]+\.[a-z]{2,}')


@pytest.fixture(autouse=True)
def _sin_red(sin_red):  # noqa: F811
    yield


def _job_publico(i, ws, kind, title, lane, resultado, status='done'):
    """Lo que publica ``jobs.Job.public()``, para que la ruta lo valide contra ``JobRespuesta``."""
    return {'id': f'j{i}', 'kind': kind, 'title': title, 'workspace_id': ws.id, 'lane': lane, 'status': status,
            'progress': None, 'result': resultado, 'error': None, 'created_at': 1.0, 'started_at': None,
            'finished_at': None, 'cancel_requested': False}


class Montaje:
    def __init__(self, tmp_path, modo='acepta', diferido=False, cola_rechaza=0, credenciales=None):
        out, self.destino = _informe_cerrado(tmp_path, {})
        self.ws = SimpleNamespace(id='a' * 12, root=tmp_path / 'ws', out_dir=out)
        self.ws.root.mkdir(exist_ok=True)
        self.proveedor = ProveedorSimulado(modo=modo)
        self.trabajos, self.registro = [], []
        self.en_curso = False
        app = FastAPI()

        def ws_or_404(wid):
            if wid != self.ws.id:
                raise HTTPException(404, 'no')
            return self.ws

        self.pendientes = []
        self.cola_rechaza = cola_rechaza

        def submit(ws, kind, title, fn, *, lane='engine', reanudar=None):
            assert reanudar is None, 'un envío nunca se relanza solo (110:RF-9)'
            if self.cola_rechaza:
                self.cola_rechaza -= 1
                raise HTTPException(409, 'La cola está ocupada.')
            ctx = SimpleNamespace(log=self.registro.append, progress=lambda *a, **k: None, check_cancel=lambda: None)
            if diferido:
                # Como la cola real: el trabajo corre después de responder (doble clic antes de que empiece).
                self.pendientes.append((fn, ctx))
                job = _job_publico(len(self.trabajos), ws, kind, title, lane, None, status='queued')
            else:
                job = _job_publico(len(self.trabajos), ws, kind, title, lane, fn(ctx))
            self.trabajos.append(job)
            return job

        correo_api.registrar_rutas_correo(app, ws_or_404=ws_or_404, submit=submit,
                                          credenciales_de=lambda ws: credenciales or CredencialesSimuladas(),
                                          compartidor_de=lambda ws: CompartidorSimulado(),
                                          informes_en_curso=lambda ws: self.en_curso,
                                          proveedor=lambda nombre: self.proveedor)
        self.cliente = TestClient(app)

    def base(self):
        return f'/api/workspaces/{self.ws.id}/correo'

    def vista(self, **cambios):
        cuerpo = {'informe': self.destino.name, 'cuenta': 'operador@empresa-a.test', 'proveedor': 'google',
                  'para': ['cliente@otra.test'], 'adjuntar': ['docx']}
        cuerpo.update(cambios)
        return self.cliente.post(f'{self.base()}/vista-previa', json=cuerpo, headers=ORIGEN)

    def confirmar(self, vista, firma=None, headers=ORIGEN):
        return self.cliente.post(f'{self.base()}/{vista["borrador"]}/confirmar',
                                 json={'firma': firma or vista['firma']}, headers=headers)


def test_vista_previa_devuelve_lo_que_vera_el_operador(tmp_path):
    """110:RF-1, RF-12, RF-14 — cuenta, destinatarios, asunto, cuerpo, adjuntos con huella, validez y avisos."""
    m = Montaje(tmp_path)
    r = m.vista(cc=['copia@otra.test'])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v['para'] == ['cliente@otra.test'] and v['cc'] == ['copia@otra.test'] and v['confirmado'] is False
    assert v['asunto'] and v['cuerpo'] and len(v['firma']) == 64
    assert [a['nombre'] for a in v['adjuntos']] == [m.destino.name] and len(v['adjuntos'][0]['sha256']) == 64
    assert v['validez']['valido'] is True
    assert set(v['avisos']) == {'cliente@otra.test', 'copia@otra.test'}
    assert m.proveedor.llamadas == [] and m.trabajos == []


def test_confirmar_envia_una_vez_y_el_doble_clic_no_encola_otro(tmp_path):
    """110:RF-5, RF-7 — un trabajo en el carril correo; el segundo clic devuelve el recibo sin otro trabajo."""
    m = Montaje(tmp_path)
    v = m.vista().json()
    r1 = m.confirmar(v)
    assert r1.status_code == 200, r1.text
    assert m.trabajos[0]['lane'] == 'correo' and 'correo' in LANES
    r2 = m.confirmar(v)
    assert r2.status_code == 200 and r2.json()['trabajo'] is None
    assert r2.json()['recibo']['estado'] == 'aceptado' and r2.json()['clave'] == r1.json()['clave']
    assert len(m.trabajos) == 1 and len(m.proveedor.llamadas) == 1


def test_confirmar_con_otra_firma_o_un_adjunto_cambiado_da_409(tmp_path):
    """110:RF-4, RF-5 — sin la firma que vio el operador, o con el adjunto cambiado, no sale nada."""
    m = Montaje(tmp_path)
    v = m.vista().json()
    assert m.confirmar(v, firma='0' * 64).status_code == 409
    m.destino.write_bytes(m.destino.read_bytes() + b'x')
    r = m.confirmar(v)
    assert r.status_code == 409 and 'revise' in r.json()['detail']
    assert m.trabajos == [] and m.proveedor.llamadas == []


@pytest.mark.parametrize('cabeceras', [{}, {**ORIGEN, 'X-CSG-Token': 'x'}, {**ORIGEN, 'Authorization': 'Bearer x'}])
def test_solo_la_ventana_del_navegador_confirma(tmp_path, cabeceras):
    """110:RF-5, RF-6 — sin Origin o con las cabeceras de un programa (el ejecutor del asistente): 403."""
    m = Montaje(tmp_path)
    v = m.vista().json()
    assert m.confirmar(v, headers=cabeceras).status_code == 403
    assert m.trabajos == [] and m.proveedor.llamadas == []


@pytest.mark.parametrize('origen', ['asistente', 'documento'])
def test_una_orden_del_asistente_o_un_documento_solo_dejan_un_borrador(tmp_path, origen):
    """110:RF-6 — el asistente o el texto de un documento piden enviar: un borrador sin confirmar y la ventana."""
    m = Montaje(tmp_path)
    v = m.vista(origen=origen).json()
    assert v['confirmado'] is False and v['ventana'].endswith(v['borrador'])
    assert m.trabajos == [] and m.proveedor.llamadas == []


def test_ningun_paso_del_asistente_alcanza_la_confirmacion(tmp_path, monkeypatch):
    """110:RF-6, 070:RF-81 — el asistente solo nombra la vista previa del correo (aclaración de 110:RF-6 del
    2026-11-16): ni el ejecutor ni las tareas nombran la ruta de confirmar, y el gobierno la niega."""
    import re

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'equipo'))
    raiz = Path(__file__).resolve().parents[1] / 'src' / 'convertersmartgrid' / 'aplicacion' / 'asistente'
    for fichero in raiz.rglob('*.py'):
        rutas = re.findall(r"/correo/[\w{}\-/]*", fichero.read_text(encoding='utf-8'))
        assert set(rutas) <= {'/correo/vista-previa'}, (fichero, rutas)
    from test_asistente_equipo import preparar

    _, _, gobierno = preparar()
    with pytest.raises(PermisoDenegado):
        gobierno.autorizar_peticion('POST', '/correo/' + 'b' * 32 + '/confirmar', {'json': {'firma': 'f' * 64}})


def test_estado_historial_y_resolver_un_desconocido(tmp_path):
    """110:RF-8, RF-9, RF-13 — el recibo, el historial del informe y «No llegó» que abre otro intento."""
    m = Montaje(tmp_path, modo='acepta_y_no_responde')
    v = m.vista().json()
    clave = m.confirmar(v).json()['clave']
    recibo = m.cliente.get(f'{m.base()}/envios/{clave}').json()
    assert recibo['estado'] == 'desconocido'
    hist = m.cliente.get(f'{m.base()}/historial', params={'informe': m.destino.name}).json()
    assert [r['clave'] for r in hist['envios']] == [clave]
    assert m.cliente.post(f'{m.base()}/envios/{clave}/resolver', json={'llego': False},
                          headers={**ORIGEN, 'X-CSG-Token': 'x'}).status_code == 403
    assert m.cliente.post(f'{m.base()}/envios/{clave}/resolver', json={'llego': False},
                          headers=ORIGEN).json()['estado'] == 'rechazado'
    m.proveedor.modo = 'acepta'
    otra = m.confirmar(v).json()
    assert otra['clave'] != clave and len(m.proveedor.llamadas) == 2
    assert m.cliente.get(f'{m.base()}/envios/{"0" * 64}').status_code == 404


def test_informe_no_cerrado_o_trabajo_en_curso_da_400(tmp_path):
    """110:RF-3 — la vista previa dice por qué no se puede adjuntar."""
    m = Montaje(tmp_path)
    m.en_curso = True
    assert m.vista().status_code == 400
    m.en_curso = False
    assert m.vista(informe='otro.docx').status_code == 400


def test_registro_y_eventos_sin_direcciones_ni_tokens(tmp_path, caplog):
    """110 (RNF) — título del trabajo, eventos y registro de la web sin ninguna dirección completa ni token."""
    m = Montaje(tmp_path)
    v = m.vista(cc=['copia.larga@otra.test']).json()
    m.confirmar(v)
    textos = [m.trabajos[0]['title'], *m.registro, json.dumps(m.trabajos[0]['result'])]
    for texto in textos:
        assert not _DIRECCION.search(texto), texto
        assert 'tok-simulado' not in texto
    registro = logging.getLogger('prueba.correo')
    registro.addFilter(_SinCorreoEnElRegistro())
    with caplog.at_level(logging.INFO, logger='prueba.correo'):
        registro.info('POST %s a %s con Bearer %s', '/x', 'cliente@otra.test', 'ya29.secreto')
    assert 'cliente@otra.test' not in caplog.text and 'ya29.secreto' not in caplog.text
    assert enmascarar_correo('a jose.perez@otra.test') == 'a j…@otra.test'


def test_doble_clic_antes_de_que_empiece_el_trabajo_no_encola_otro(tmp_path):
    """110:RF-7 — la ruta reserva la clave al encolar: un segundo clic con el trabajo aún en cola no encola otro."""
    m = Montaje(tmp_path, diferido=True)
    v = m.vista().json()
    r1, r2 = m.confirmar(v), m.confirmar(v)
    assert r1.status_code == 200 and r1.json()['trabajo']['lane'] == 'correo'
    assert r2.status_code == 200 and r2.json()['trabajo'] is None
    assert r2.json()['recibo']['estado'] == 'reservado' and r2.json()['clave'] == r1.json()['clave']
    assert len(m.trabajos) == 1 and m.proveedor.llamadas == []
    for fn, ctx in m.pendientes:
        fn(ctx)
    assert len(m.proveedor.llamadas) == 1
    assert m.cliente.get(f'{m.base()}/envios/{r1.json()["clave"]}').json()['estado'] == 'aceptado'


def test_si_la_cola_no_admite_el_envio_la_reserva_no_bloquea(tmp_path):
    """110:RF-7 — si el envío no entra en la cola, su reserva queda cancelada y la siguiente confirmación encola."""
    m = Montaje(tmp_path, cola_rechaza=1)
    v = m.vista().json()
    assert m.confirmar(v).status_code == 409
    segundo = m.confirmar(v)
    assert segundo.status_code == 200 and segundo.json()['trabajo'] is not None
    assert len(m.trabajos) == 1 and len(m.proveedor.llamadas) == 1
    estados = sorted(r['estado'] for r in m.cliente.get(
        f'{m.base()}/historial', params={'informe': m.destino.name}).json()['envios'])
    assert estados == ['aceptado', 'cancelado']


def test_enlace_sin_expediente_o_que_no_es_https_da_400(tmp_path):
    """110:RF-10 — un enlace necesita su expediente y una dirección https://; con ellos, sin adjuntos."""
    m = Montaje(tmp_path)
    assert m.vista(enlace='https://expediente.test/x').status_code == 400
    assert m.vista(enlace='http://expediente.test/x', expediente='EXP-1').status_code == 400
    r = m.vista(enlace='https://expediente.test/x', expediente='EXP-1')
    assert r.status_code == 200, r.text
    assert r.json()['adjuntos'] == [] and r.json()['enlace'] == 'https://expediente.test/x'


def test_peticiones_mal_formadas_dan_422_o_404(tmp_path):
    """110:RF-1 — sin destinatarios, con un proveedor desconocido, un campo de más o una firma corta: 422."""
    m = Montaje(tmp_path)
    assert m.vista(para=[]).status_code == 422
    assert m.vista(proveedor='smtp').status_code == 422
    assert m.vista(campo_de_mas=1).status_code == 422
    v = m.vista().json()
    assert m.confirmar(v, firma='abc').status_code == 422
    assert m.cliente.post(f'{m.base()}/{"z" * 32}/confirmar', json={'firma': 'f' * 64},
                          headers=ORIGEN).status_code == 404
    assert m.cliente.post(f'/api/workspaces/{"b" * 12}/correo/vista-previa', json={}, headers=ORIGEN).status_code \
        in (404, 422)
    assert m.trabajos == [] and m.proveedor.llamadas == []


# ------------------------------------------------------------------ T9: servidas por create_app (110:RF-1)
RUTAS_CORREO = {
    ('POST', '/api/workspaces/{wid}/correo/vista-previa'),
    ('POST', '/api/workspaces/{wid}/correo/{bid}/confirmar'),
    ('GET', '/api/workspaces/{wid}/correo/envios/{clave}'),
    ('GET', '/api/workspaces/{wid}/correo/historial'),
    ('POST', '/api/workspaces/{wid}/correo/envios/{clave}/resolver'),
}


def _rutas_correo(app) -> set[tuple[str, str]]:
    return {(m, r.path) for r in app.routes if '/correo/' in getattr(r, 'path', '') for m in r.methods}


def test_registrar_rutas_correo_monta_exactamente_las_cinco(tmp_path):
    """110:RF-1, RF-8, RF-13 — el cliente web (``api/correo.ts``) llama a estas rutas y solo a estas."""
    assert _rutas_correo(Montaje(tmp_path).cliente.app) == RUTAS_CORREO


def test_create_app_sirve_el_correo_y_sin_cuentas_de_la_109_no_envia(tmp_path, monkeypatch):
    """110:RF-1, RF-5, RF-7 — create_app monta las rutas; sin cuentas conectadas el envío se rechaza sin abrir la red."""
    from apoyo import esperar_trabajo
    from test_informe_docx import _config, _factibilidad

    from convertersmartgrid.adaptadores.informe_docx import escribir_informe_factibilidad
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    assert _rutas_correo(app) == RUTAS_CORREO
    with TestClient(app) as c:
        wid = c.post('/api/workspaces').json()['id']
        ws = app.state.store.get(wid)
        Path(ws.out_dir).mkdir(parents=True, exist_ok=True)
        destino = Path(ws.out_dir) / 'informe_factibilidad_AL02_X.docx'
        escribir_informe_factibilidad(_config(tmp_path), destino, _factibilidad(tmp_path))
        v = c.post(f'/api/workspaces/{wid}/correo/vista-previa', headers=ORIGEN,
                   json={'informe': destino.name, 'cuenta': 'operador@empresa-a.test', 'proveedor': 'google',
                         'para': ['cliente@otra.test'], 'adjuntar': ['docx']})
        assert v.status_code == 200, v.text
        r = c.post(f'/api/workspaces/{wid}/correo/{v.json()["borrador"]}/confirmar', headers=ORIGEN,
                   json={'firma': v.json()['firma']})
        assert r.status_code == 200, r.text
        assert r.json()['trabajo']['lane'] == 'correo'
        assert esperar_trabajo(c, r.json()['trabajo'])['status'] == 'done'
        recibo = c.get(f'/api/workspaces/{wid}/correo/envios/{r.json()["clave"]}').json()
        assert recibo['estado'] == 'rechazado' and 'conect' in recibo['motivo']
        hist = c.get(f'/api/workspaces/{wid}/correo/historial', params={'informe': destino.name}).json()
        assert [e['clave'] for e in hist['envios']] == [r.json()['clave']]
        assert 'cliente@otra.test' not in r.json()['trabajo']['title']


def test_sin_cuenta_conectada_la_web_dice_que_configure_la_nube_y_no_falla(tmp_path):
    """110:RF-2, RF-8 — sin la cuenta de la 109 (versión de prueba sin registro): la vista previa sale, el envío queda
    rechazado con «Sin cuenta conectada: configure config/nube.json», con su recibo, y no llama al proveedor."""
    m = Montaje(tmp_path, credenciales=correo_api.SinCuentas())
    v = m.vista()
    assert v.status_code == 200, v.text
    r = m.confirmar(v.json())
    assert r.status_code == 200, r.text
    recibo = m.cliente.get(f'{m.base()}/envios/{r.json()["clave"]}').json()
    assert recibo['estado'] == 'rechazado', recibo
    assert 'Sin cuenta conectada: configure config/nube.json' in (recibo.get('motivo') or ''), recibo
    assert m.proveedor.llamadas == []


def test_el_registro_no_escribe_el_token_bearer_dado_como_argumento():
    """110 (RNF), 110:RF-13 — un token de portador que va en un ARGUMENTO del registro («Bearer %s») no llega al
    registro: la línea SE ESCRIBE (un error de formato no cuenta como «sin token») con el token enmascarado. Determinista:
    un handler propio sobre un registrador propio, con los dos filtros que la web pone en uvicorn.access."""
    import io

    from convertersmartgrid.presentacion.web import seguridad

    salida = io.StringIO()
    manejador = logging.StreamHandler(salida)
    manejador.setFormatter(logging.Formatter('%(message)s'))
    registro = logging.getLogger('prueba.token_bearer_determinista')
    registro.propagate = False
    registro.setLevel(logging.INFO)
    for viejo in list(registro.handlers):
        registro.removeHandler(viejo)
    for viejo in list(registro.filters):
        registro.removeFilter(viejo)
    registro.addHandler(manejador)
    for nombre in ('_SinTokenEnElRegistro', '_SinCorreoEnElRegistro'):
        clase = getattr(seguridad, nombre, None)
        if clase is not None:
            registro.addFilter(clase())
    secreto = 'ya29.token-de-prueba-0123456789'
    errores = []
    anterior = logging.raiseExceptions
    logging.raiseExceptions = False  # un registro mal formado no debe romper la prueba: se comprueba lo escrito
    manejador.handleError = lambda record: errores.append(record)
    try:
        registro.info('GET %s con Bearer %s', '/api/correo', secreto)
        registro.info('Bearer %s', secreto)
    finally:
        logging.raiseExceptions = anterior
        registro.removeHandler(manejador)
    escrito = salida.getvalue()
    assert not errores, f'el registro no se pudo escribir (error de formato): {len(errores)} líneas perdidas'
    assert escrito.count('Bearer') == 2, f'no se escribieron las dos líneas: {escrito!r}'
    assert secreto not in escrito, f'el token de portador llegó al registro: {escrito!r}'
