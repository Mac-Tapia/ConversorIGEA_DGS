"""Los dos proveedores de correo de la 110: Gmail (``gmail.send``) y Outlook (``Mail.Send``) (parte H del plan).

Una sola llamada REST cada uno, con ``requests`` (ya en el núcleo, P8): los SDK de Google y de Microsoft pesan y no
hacen falta. La sesión no lee el proxy del entorno (``trust_env=False``), no sigue redirecciones (una redirección
llevaría el token a otro sitio) y tiene plazo ``(10 s, 60 s)``. Antes de abrir la red se comprueba la salida
declarada en ``salidas_red`` (086:RF-22); en la edición de producto está apagada hasta que se encienda.

Solo se pide el permiso de enviar, nunca el de leer el buzón (110:RF-2): un desconocido lo resuelve el operador
mirando «Enviados», no el programa.

Tabla de resultados (plan de la 110, «Estado desconocido, y nunca un reenvío solo»):

- aceptado: Gmail 200 con ``id``; Graph 202 (sin ``id``: se guarda el ``request-id`` de la respuesta).
- rechazado (no salió): no se llegó a conectar (``ConnectTimeout``, DNS, TLS), 3xx, 400, 401, 403, 413, 429 y el
  resto de 4xx.
- desconocido: ``ReadTimeout``, conexión cortada tras enviar el cuerpo, cualquier 5xx o un 200 de Gmail sin ``id``.
"""
from __future__ import annotations

import base64
from typing import Any, Callable

import requests

from ..salidas_red import SalidaApagada, motivo_apagada, salida_permitida
from . import ResultadoEnvio

PLAZO_S = (10, 60)
MB = 1024 * 1024

#: Gmail: un correo con sus adjuntos hasta 25 MB (ayuda de Gmail, «Límites de tamaño de los adjuntos»); la subida de
#: ``messages.send`` admite hasta 35 MB, por encima de lo que acepta como correo. Comprobado el 2026-11-14 en
#: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send (alcance ``gmail.send``).
LIMITE_GMAIL = 25 * MB
#: Graph ``sendMail``: los adjuntos en la misma petición, hasta 3 MB; más grande exige la sesión de subida de un
#: borrador, que pide ``Mail.ReadWrite`` (acceso al buzón), así que con solo ``Mail.Send`` el tope es 3 MB
#: (https://learn.microsoft.com/graph/outlook-large-attachments). ``sendMail`` devuelve 202 sin cuerpo
#: (https://learn.microsoft.com/graph/api/user-sendmail, comprobado el 2026-11-14).
LIMITE_OUTLOOK = 3 * MB

_MOTIVOS = {
    400: 'el proveedor rechazó el mensaje',
    401: 'la cuenta ya no da permiso: vuelva a conectar la cuenta',
    403: 'la cuenta no tiene permiso de enviar correo',
    413: 'rechazado: demasiado grande',
    429: 'el proveedor pide esperar antes de enviar más',
}
_EN_ENVIADOS = 'compruebe en Enviados de su cuenta'


def _sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.trust_env = False
    return sesion


def _antes_de_conectar(exc: requests.RequestException) -> bool:
    """¿Falló antes de entregar el cuerpo? Entonces el correo seguro que no salió."""
    if isinstance(exc, (requests.exceptions.ConnectTimeout, requests.exceptions.SSLError,
                        requests.exceptions.InvalidURL, requests.exceptions.MissingSchema)):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        texto = repr(exc)
        return any(m in texto for m in ('NewConnectionError', 'NameResolutionError', 'getaddrinfo',
                                        'Failed to establish'))
    return False


class _ProveedorREST:
    nombre = ''
    alcance = ''
    limite_adjuntos = 0
    salida = ''
    url = ''

    def __init__(self, sesion: Callable[[], Any] = _sesion):
        self._sesion = sesion

    def _peticion(self, mensaje: bytes, token: str) -> tuple[dict[str, str], bytes]:
        raise NotImplementedError

    def _aceptado(self, respuesta: Any) -> ResultadoEnvio | None:
        raise NotImplementedError

    def enviar(self, mensaje: bytes, *, token: str) -> ResultadoEnvio:
        # 086:RF-22: se corta aquí, antes de abrir ninguna conexión.
        if not salida_permitida(self.salida):
            raise SalidaApagada(motivo_apagada(self.salida))
        if len(mensaje) > self.limite_adjuntos:
            return ResultadoEnvio('rechazado', motivo=f'rechazado: demasiado grande para {self.nombre} '
                                                      f'({self.limite_adjuntos // MB} MB); envíe el enlace')
        cabeceras, cuerpo = self._peticion(mensaje, token)
        try:
            with self._sesion() as sesion:
                respuesta = sesion.post(self.url, data=cuerpo, headers=cabeceras, timeout=PLAZO_S,
                                        allow_redirects=False)
        except requests.RequestException as exc:
            if _antes_de_conectar(exc):
                return ResultadoEnvio('rechazado', motivo='no se pudo conectar con el proveedor')
            return ResultadoEnvio('desconocido', motivo=f'el proveedor no respondió a tiempo: {_EN_ENVIADOS}')
        codigo = int(respuesta.status_code)
        aceptado = self._aceptado(respuesta)
        if aceptado is not None:
            return aceptado
        if 300 <= codigo < 400:
            return ResultadoEnvio('rechazado', codigo=codigo, motivo='el proveedor pidió una redirección y no se sigue')
        if codigo >= 500:
            return ResultadoEnvio('desconocido', codigo=codigo, motivo=f'el proveedor falló al recibirlo: {_EN_ENVIADOS}')
        if 200 <= codigo < 300:
            return ResultadoEnvio('desconocido', codigo=codigo, motivo=f'respuesta inesperada del proveedor: {_EN_ENVIADOS}')
        return ResultadoEnvio('rechazado', codigo=codigo, motivo=_MOTIVOS.get(codigo, 'el proveedor rechazó el envío'))


class EnvioGmail(_ProveedorREST):
    """``messages.send`` con subida ``media`` del MIME entero (``message/rfc822``)."""
    nombre = 'google'
    alcance = 'https://www.googleapis.com/auth/gmail.send'
    limite_adjuntos = LIMITE_GMAIL
    salida = 'correo_google'
    url = 'https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send?uploadType=media'

    def _peticion(self, mensaje: bytes, token: str) -> tuple[dict[str, str], bytes]:
        return {'Authorization': f'Bearer {token}', 'Content-Type': 'message/rfc822'}, mensaje

    def _aceptado(self, respuesta: Any) -> ResultadoEnvio | None:
        if respuesta.status_code != 200:
            return None
        try:
            ident = (respuesta.json() or {}).get('id')
        except ValueError:
            ident = None
        return ResultadoEnvio('aceptado', id_proveedor=str(ident), codigo=200) if ident else None


class EnvioOutlook(_ProveedorREST):
    """``sendMail`` de Microsoft Graph con el MIME en base64 (``text/plain``), cuentas personales y de empresa."""
    nombre = 'microsoft'
    alcance = 'https://graph.microsoft.com/Mail.Send'
    limite_adjuntos = LIMITE_OUTLOOK
    salida = 'correo_microsoft'
    url = 'https://graph.microsoft.com/v1.0/me/sendMail'

    def _peticion(self, mensaje: bytes, token: str) -> tuple[dict[str, str], bytes]:
        return {'Authorization': f'Bearer {token}', 'Content-Type': 'text/plain'}, base64.b64encode(mensaje)

    def _aceptado(self, respuesta: Any) -> ResultadoEnvio | None:
        if respuesta.status_code != 202:
            return None
        cabeceras = getattr(respuesta, 'headers', {}) or {}
        return ResultadoEnvio('aceptado', id_proveedor=cabeceras.get('request-id') or None, codigo=202)


def proveedor_de(nombre: str, **kwargs: Any) -> _ProveedorREST:
    """El adaptador de cada proveedor admitido por su nombre (``correo.PROVEEDORES``)."""
    return {'google': EnvioGmail, 'microsoft': EnvioOutlook}[nombre](**kwargs)
