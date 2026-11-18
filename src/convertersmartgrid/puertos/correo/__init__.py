"""Envío de informes por correo desde la web, con la cuenta Gmail u Outlook del operador (spec 110).

Este paquete solo usa la biblioteca estándar y ``requests``, que ya están en el núcleo (P8). Aquí viven los contratos
que el resto del paquete consume, para que ningún módulo dependa de una implementación concreta:

- ``ProveedorCorreo``: lo que cumplen ``correo/proveedores.py`` (Gmail y Outlook) y el simulado de las pruebas.
- ``FuenteDeCredenciales`` y ``Compartidor``: lo que la 110 pide a la spec 109 (token del proveedor con solo el permiso
  de enviar, 109:RF-1 y RF-2, y el permiso de lectura de un expediente, 109:RF-10). Cuando la 109 publique sus
  interfaces, se adapta este ``Protocol`` sin cambiar ningún RF de la 110 (plan de la 110, «Credenciales y
  consentimiento son de la 109»).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol, Sequence

#: Los dos proveedores admitidos; nada de SMTP con contraseña (spec 110, «Fuera de alcance»).
PROVEEDORES = ('google', 'microsoft')

EstadoProveedor = Literal['aceptado', 'rechazado', 'desconocido']


class CuentaNoConectada(RuntimeError):
    """No hay token para esa cuenta, o el proveedor lo revocó: el operador vuelve a conectarla (109:RF-1)."""


@dataclass(frozen=True)
class ResultadoEnvio:
    """Lo que dijo el proveedor, ya traducido por la tabla del adaptador (110:RF-8, RF-9).

    ``aceptado`` solo prueba que el proveedor lo aceptó, no que llegó ni que se leyó (spec 110, «Fuera de alcance»).
    """
    estado: EstadoProveedor
    id_proveedor: str | None = None
    codigo: int | None = None
    motivo: str = ''


class ProveedorCorreo(Protocol):
    """Un proveedor que envía un mensaje MIME ya construido con el token de la cuenta."""
    nombre: str
    #: El permiso que se pide al proveedor: solo enviar, nunca leer el buzón (110:RF-2).
    alcance: str
    #: Tope de los adjuntos, en bytes, según la documentación del proveedor.
    limite_adjuntos: int

    def enviar(self, mensaje: bytes, *, token: str) -> ResultadoEnvio: ...


class FuenteDeCredenciales(Protocol):
    """La 109 guarda los tokens cifrados (109:RF-2); la 110 solo pide uno con el alcance de enviar."""

    def token(self, proveedor: str, cuenta: str, alcance: str) -> str: ...


class Compartidor(Protocol):
    """La 109 da a unos destinatarios exactos el permiso de lectura de un expediente (109:RF-10).

    Devuelve su recibo: ``{'estado': 'concedido' | 'rechazado', 'motivo': str, 'id': str | None}``.
    """

    def conceder_lectura(self, expediente: str, destinatarios: Sequence[str]) -> Mapping[str, Any]: ...
