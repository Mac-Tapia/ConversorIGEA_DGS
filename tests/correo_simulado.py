"""Proveedor de correo simulado para la spec 110, como ``tests/fake_pf.py`` para DIgSILENT.

Imita lo que el adaptador real (``correo/proveedores.py``) devuelve tras su tabla de errores: acepta, rechaza con 400,
401 (cuenta revocada), 403, 413 y 429, cae en un 5xx, no llega a conectar (``ConnectTimeout``) o acepta el cuerpo y no
responde (``ReadTimeout`` tras recibirlo). Cuenta las llamadas: «una sola llamada» es la afirmación de cada prueba de
idempotencia (110:RF-7). Nunca abre la red: el guardián ``sin_red`` corta cualquier conexión de la prueba.

También simula las dos interfaces que la 110 pide a la 109 (credenciales y compartir un expediente), hasta que la
109 publique las suyas.
"""
from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field

import pytest

from convertersmartgrid.correo import ResultadoEnvio

#: Modo → (estado, código HTTP, motivo). Lo mismo que traduce la tabla del adaptador real (plan de la 110).
MODOS: dict[str, tuple[str, int | None, str]] = {
    'acepta': ('aceptado', 200, ''),
    '400': ('rechazado', 400, 'el proveedor rechazó el mensaje'),
    '401': ('rechazado', 401, 'la cuenta ya no da permiso: vuelva a conectar la cuenta'),
    '403': ('rechazado', 403, 'la cuenta no tiene permiso de enviar correo'),
    '413': ('rechazado', 413, 'rechazado: demasiado grande'),
    '429': ('rechazado', 429, 'el proveedor pide esperar antes de enviar más'),
    '500': ('desconocido', 500, 'el proveedor falló al recibirlo: compruebe en Enviados de su cuenta'),
    'connect_timeout': ('rechazado', None, 'no se pudo conectar con el proveedor'),
    'acepta_y_no_responde': ('desconocido', None, 'el proveedor no respondió a tiempo: compruebe en Enviados de su cuenta'),
}


@dataclass
class ProveedorSimulado:
    """Implementa ``ProveedorCorreo``. ``modo`` se puede cambiar entre llamadas."""
    nombre: str = 'google'
    modo: str = 'acepta'
    limite_adjuntos: int = 25 * 1024 * 1024
    llamadas: list[dict] = field(default_factory=list)
    #: Si se pone, la llamada espera a este evento antes de responder (carreras de doble clic).
    esperar: threading.Event | None = None

    alcance: str = 'https://www.googleapis.com/auth/gmail.send'

    def enviar(self, mensaje: bytes, *, token: str) -> ResultadoEnvio:
        self.llamadas.append({'mensaje': mensaje, 'token': token})
        if self.esperar is not None:
            self.esperar.wait(5)
        estado, codigo, motivo = MODOS[self.modo]
        ident = f'sim-{len(self.llamadas)}' if estado == 'aceptado' else None
        return ResultadoEnvio(estado=estado, id_proveedor=ident, codigo=codigo, motivo=motivo)


@dataclass
class CredencialesSimuladas:
    """Implementa ``FuenteDeCredenciales``: un token falso por (proveedor, cuenta, alcance)."""
    revocada: bool = False
    pedidos: list[tuple[str, str, str]] = field(default_factory=list)

    def token(self, proveedor: str, cuenta: str, alcance: str) -> str:
        self.pedidos.append((proveedor, cuenta, alcance))
        if self.revocada:
            from convertersmartgrid.correo import CuentaNoConectada
            raise CuentaNoConectada('Vuelva a conectar la cuenta.')
        return f'tok-simulado-{proveedor}'


@dataclass
class CompartidorSimulado:
    """Implementa ``Compartidor``: concede (o no) la lectura de un expediente y deja su recibo."""
    falla: bool = False
    concesiones: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    orden: list[str] | None = None

    def conceder_lectura(self, expediente: str, destinatarios) -> dict:
        destinatarios = tuple(destinatarios)
        self.concesiones.append((expediente, destinatarios))
        if self.orden is not None:
            self.orden.append('permiso')
        if self.falla:
            return {'estado': 'rechazado', 'motivo': 'el proveedor no concedió el permiso', 'id': None}
        return {'estado': 'concedido', 'motivo': '', 'id': f'perm-{len(self.concesiones)}'}


@pytest.fixture
def sin_red(monkeypatch):
    """Ninguna prueba de la 110 sale de la máquina: cualquier conexión fuera del bucle local falla aquí.

    El bucle local (127.0.0.1, ::1) se deja: en Windows, ``socket.socketpair`` se emula conectando dos sockets locales,
    y lo usa el bucle de eventos de ``asyncio`` con el que corre ``TestClient``. Nada de eso sale a la red.
    """
    conectar, conectar_ex, crear = socket.socket.connect, socket.socket.connect_ex, socket.create_connection
    resolver = socket.getaddrinfo

    def _local(direccion) -> bool:
        if isinstance(direccion, (str, bytes)):
            return True  # AF_UNIX: un fichero local
        host = str(direccion[0]).strip('[]').lower() if direccion else ''
        return host in _LOCALES

    def _negar(direccion):
        raise AssertionError(f'Una prueba de la 110 intentó abrir la red ({direccion!r}).')

    def connect(self, direccion, *a, **k):
        return conectar(self, direccion, *a, **k) if _local(direccion) else _negar(direccion)

    def connect_ex(self, direccion, *a, **k):
        return conectar_ex(self, direccion, *a, **k) if _local(direccion) else _negar(direccion)

    def create_connection(direccion, *a, **k):
        return crear(direccion, *a, **k) if _local(direccion) else _negar(direccion)

    def getaddrinfo(host, *a, **k):
        # Ni siquiera la consulta DNS de un nombre de fuera: también es abrir la red.
        return resolver(host, *a, **k) if host is None or _local((host,)) else _negar(host)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'create_connection', create_connection)
    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)
    yield


#: Lo único a lo que una prueba puede conectar: el bucle local de la propia máquina.
_LOCALES = frozenset({'127.0.0.1', '::1', 'localhost'})
