"""Spec 110: el mensaje MIME y los adaptadores de Gmail y Outlook, con un transporte de prueba y sin red."""
from __future__ import annotations

import base64
import email
import io
import zipfile
from email import policy

import pytest
import requests

from correo_simulado import sin_red  # noqa: F401

from convertersmartgrid.correo import borrador as b
from convertersmartgrid.correo import envios as e
from convertersmartgrid.correo import mensaje as m
from convertersmartgrid.correo import proveedores as p
from convertersmartgrid.salidas_red import SALIDAS, SalidaApagada


@pytest.fixture(autouse=True)
def _sin_red(sin_red, monkeypatch):  # noqa: F811
    for nombre in ('correo_google', 'correo_microsoft'):
        monkeypatch.setenv(SALIDAS[nombre].variable, '1')
    yield


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<x>informe</x>')
    return buf.getvalue()


def _borrador(tmp_path, **cambios):
    ruta = tmp_path / 'informe.docx'
    if not ruta.exists():
        ruta.write_bytes(_docx())
    datos = dict(cuenta='operador@empresa-a.test', proveedor='google', para=['cliente@otra.test'],
                 cc=['copia@otra.test'], cco=['oculta@otra.test'], asunto='Informe de factibilidad',
                 cuerpo='Adjunto el informe.', adjuntos=[ruta])
    datos.update(cambios)
    return b.crear_borrador(**datos)


class Respuesta:
    def __init__(self, codigo, datos=None, cabeceras=None):
        self.status_code, self._datos, self.headers = codigo, datos, cabeceras or {}

    def json(self):
        if self._datos is None:
            raise ValueError('sin cuerpo')
        return self._datos


class Transporte:
    """Una ``requests.Session`` de prueba: guarda cada petición y responde lo que se le diga, sin red."""

    def __init__(self, respuesta=None, excepcion=None):
        self.respuesta, self.excepcion, self.peticiones = respuesta, excepcion, []
        self.trust_env = True

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, **kwargs):
        self.peticiones.append({'url': url, **kwargs})
        if self.excepcion is not None:
            raise self.excepcion
        return self.respuesta


def test_mime_con_cabeceras_message_id_de_la_clave_y_adjuntos(tmp_path):
    """110:RF-8 — el MIME lleva a quién va, el asunto, el Message-ID derivado de la clave y el adjunto firmado."""
    borr = _borrador(tmp_path)
    clave = 'a' * 64
    crudo = m.construir_mensaje(borr, clave)
    msg = email.message_from_bytes(crudo, policy=policy.default)
    assert msg['To'] == 'cliente@otra.test' and msg['Cc'] == 'copia@otra.test' and msg['Bcc'] == 'oculta@otra.test'
    assert msg['From'] == 'operador@empresa-a.test' and msg['Subject'] == 'Informe de factibilidad'
    assert msg['Message-ID'] == e.message_id(clave) == f'<{clave}@csg.invalid>'
    (adjunto,) = list(msg.iter_attachments())
    assert adjunto.get_filename() == 'informe.docx' and adjunto.get_content() == _docx()


def test_el_enlace_va_en_el_cuerpo(tmp_path):
    """110:RF-10 — con un enlace, el cuerpo lo lleva."""
    borr = _borrador(tmp_path, adjuntos=[], enlace='https://expediente.test/abc')
    msg = email.message_from_bytes(m.construir_mensaje(borr, 'b' * 64), policy=policy.default)
    assert 'https://expediente.test/abc' in msg.get_body().get_content()


def test_un_adjunto_cambiado_justo_antes_de_construir_anula(tmp_path):
    """110:RF-4 — el adjunto se relee y compara con su huella al construir el mensaje."""
    borr = _borrador(tmp_path)
    (tmp_path / 'informe.docx').write_bytes(_docx() + b'x')
    with pytest.raises(b.ConfirmacionAnulada):
        m.construir_mensaje(borr, 'c' * 64)


def test_gmail_url_alcance_sin_redirecciones_ni_entorno_y_con_plazo():
    """110:RF-2 — Gmail con solo gmail.send, la subida media del MIME, sin seguir redirecciones y con plazo."""
    t = Transporte(Respuesta(200, {'id': 'g-1'}))
    prov = p.EnvioGmail(sesion=t)
    r = prov.enviar(b'MIME', token='tok')
    assert r.estado == 'aceptado' and r.id_proveedor == 'g-1'
    assert prov.alcance == 'https://www.googleapis.com/auth/gmail.send'
    (pet,) = t.peticiones
    assert pet['url'] == 'https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send?uploadType=media'
    assert pet['allow_redirects'] is False and pet['timeout'] == (10, 60) and pet['data'] == b'MIME'
    assert pet['headers'] == {'Authorization': 'Bearer tok', 'Content-Type': 'message/rfc822'}


def test_outlook_url_alcance_y_mime_en_base64():
    """110:RF-2 — Outlook con solo Mail.Send, el MIME en base64; 202 es aceptado con el request-id."""
    t = Transporte(Respuesta(202, None, {'request-id': 'req-9'}))
    prov = p.EnvioOutlook(sesion=t)
    r = prov.enviar(b'MIME', token='tok')
    assert r.estado == 'aceptado' and r.id_proveedor == 'req-9'
    assert prov.alcance.endswith('Mail.Send') and 'Read' not in prov.alcance
    (pet,) = t.peticiones
    assert pet['url'] == 'https://graph.microsoft.com/v1.0/me/sendMail'
    assert base64.b64decode(pet['data']) == b'MIME' and pet['allow_redirects'] is False
    assert pet['headers']['Content-Type'] == 'text/plain'


def test_ningun_alcance_lee_el_buzon():
    """110:RF-2 — ni gmail.readonly, ni gmail.modify, ni Mail.Read, ni Mail.ReadWrite."""
    for prov in (p.EnvioGmail(), p.EnvioOutlook()):
        assert not any(x in prov.alcance for x in ('readonly', 'modify', 'Read', 'mail.google.com/'))


@pytest.mark.parametrize('codigo,estado', [(400, 'rechazado'), (401, 'rechazado'), (403, 'rechazado'),
                                           (413, 'rechazado'), (429, 'rechazado'), (302, 'rechazado'),
                                           (500, 'desconocido'), (503, 'desconocido')])
@pytest.mark.parametrize('clase', [p.EnvioGmail, p.EnvioOutlook])
def test_tabla_de_codigos(clase, codigo, estado):
    """110:RF-9 — cada código del proveedor a su estado; un 3xx no se sigue."""
    t = Transporte(Respuesta(codigo, {}, {'Location': 'https://otro.test/'}))
    r = clase(sesion=t).enviar(b'MIME', token='tok')
    assert (r.estado, r.codigo) == (estado, codigo) and len(t.peticiones) == 1
    if codigo == 401:
        assert 'vuelva a conectar' in r.motivo
    if codigo == 413:
        assert 'demasiado grande' in r.motivo


def test_gmail_200_sin_id_es_desconocido():
    """110:RF-9 — un 200 sin identificador no prueba que se aceptó."""
    assert p.EnvioGmail(sesion=Transporte(Respuesta(200, {}))).enviar(b'M', token='t').estado == 'desconocido'


@pytest.mark.parametrize('excepcion,estado', [
    (requests.exceptions.ConnectTimeout('x'), 'rechazado'),
    (requests.exceptions.ConnectionError('NewConnectionError: Failed to establish a new connection'), 'rechazado'),
    (requests.exceptions.SSLError('x'), 'rechazado'),
    (requests.exceptions.ReadTimeout('x'), 'desconocido'),
    (requests.exceptions.ConnectionError('Connection aborted. RemoteDisconnected'), 'desconocido'),
    (requests.exceptions.ChunkedEncodingError('x'), 'desconocido'),
])
def test_tabla_de_errores_de_red(excepcion, estado):
    """110:RF-9 — sin conectar no salió; con el cuerpo quizá entregado, desconocido."""
    r = p.EnvioGmail(sesion=Transporte(excepcion=excepcion)).enviar(b'M', token='t')
    assert r.estado == estado


@pytest.mark.parametrize('clase,nombre', [(p.EnvioGmail, 'correo_google'), (p.EnvioOutlook, 'correo_microsoft')])
def test_salida_apagada_no_abre_la_red(monkeypatch, clase, nombre):
    """110:RF-2 — con su salida apagada (086:RF-22), el adaptador no abre ninguna conexión."""
    monkeypatch.setenv(SALIDAS[nombre].variable, '0')
    t = Transporte(Respuesta(200, {'id': 'x'}))
    with pytest.raises(SalidaApagada, match=SALIDAS[nombre].variable):
        clase(sesion=t).enviar(b'M', token='t')
    assert t.peticiones == []


def test_los_limites_de_cada_proveedor_y_el_exceso_no_sale():
    """110:RF-10 — por encima del límite del proveedor no se llama y se ofrece el enlace."""
    assert p.EnvioGmail.limite_adjuntos == 25 * 1024 * 1024
    assert p.EnvioOutlook.limite_adjuntos == 3 * 1024 * 1024
    t = Transporte(Respuesta(202))
    r = p.EnvioOutlook(sesion=t).enviar(b'x' * (3 * 1024 * 1024 + 1), token='t')
    assert r.estado == 'rechazado' and 'enlace' in r.motivo and t.peticiones == []


def test_la_sesion_real_no_lee_el_entorno():
    """110:RF-2 — la sesión por defecto no toma proxies ni certificados del entorno."""
    assert p._sesion().trust_env is False


def test_las_salidas_del_correo_estan_declaradas():
    """110:RF-2 — las dos salidas existen, con su variable y el módulo que las abre."""
    for nombre, host in (('correo_google', 'gmail'), ('correo_microsoft', 'Graph')):
        s = SALIDAS[nombre]
        assert s.variable == f'CSG_SALIDA_{nombre.upper()}'
        assert s.modulos == ('src/convertersmartgrid/correo/proveedores.py',) and host in s.destino


def test_el_guardian_de_red_niega_lo_de_fuera_y_deja_el_bucle_local():
    """110:RF-2 — ninguna prueba sale de la máquina: DNS y conexiones de fuera fallan; el bucle local no."""
    import socket

    with pytest.raises(AssertionError, match='abrir la red'):
        socket.getaddrinfo('gmail.googleapis.com', 443)
    with pytest.raises(AssertionError, match='abrir la red'):
        socket.create_connection(('graph.microsoft.com', 443), timeout=0.1)
    with socket.socket() as s:
        with pytest.raises(AssertionError, match='abrir la red'):
            s.connect(('192.0.2.1', 9))
    a, b = socket.socketpair()
    a.close()
    b.close()
