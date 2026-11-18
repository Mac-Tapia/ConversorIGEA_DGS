"""La 110 sobre las cuentas de la 109: el token con el permiso de enviar y el permiso de lectura de un expediente.

La 110 no guarda tokens propios ni abre otro OAuth: usa ``adaptadores.nube.cuentas.Cuentas`` de la 109, que es de cada
espacio de trabajo, y la traduce a los ``Protocol`` de ``correo/__init__.py`` (``FuenteDeCredenciales``, ``Compartidor``).

Interfaz de la 109 que se usa (109-R4, T5):

- ``oauth.PERMISOS[p]['enviar']``: Google ``gmail.send``; Microsoft ``Mail.Send`` (110:RF-2: solo enviar, nunca leer el
  buzón). La web lo pide con ``POST …/nube/{proveedor}/conectar {"alcance": "enviar"}``, es decir,
  ``Cuentas.iniciar(wid, p, alcance='enviar')``;
- ``Cuentas.cliente(p)``: el cliente OAuth registrado; ``NoRegistrado`` sin ``config/nube.json`` (109:RF-19);
- ``Cuentas.cuenta(wid, p)``: la cuenta conectada en el espacio, o ``None``;
- ``Cuentas.acceso(wid, p, renovar=False)``: el token de acceso en memoria; ``PermisoCaducado`` (un ``ErrorNube``) sin
  cuenta o con el permiso revocado.

Lo que la 109 trae en tarjetas posteriores se usa cuando exista, sin copiarlo aquí:

- ``Cuentas.permisos(wid, p)`` (109-R9, T10): con él, una cuenta conectada sin ``gmail.send``/``Mail.Send`` se rechaza
  aquí, sin llamar al proveedor. Hasta entonces el proveedor responde 403 y el recibo queda ``rechazado`` con «la cuenta
  no tiene permiso de enviar correo» (``proveedores._MOTIVOS``): no sale nada, y no se reintenta solo;
- ``Cuentas.proveedor(wid, p).conceder_lectura(item, destinatarios)`` (109-R5, T6): hasta entonces un enlace queda
  ``rechazado`` antes del correo (110:RF-10: sin permiso concedido no sale el correo).

Un expediente se nombra ``<proveedor>:<id del elemento>`` (el ``item_id`` de la 109).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..nube.cuentas import Cuentas
from ..nube.oauth import PERMISOS, NoRegistrado
from ..nube.proveedor import ErrorNube
from ...dominio.salidas_red import SalidaApagada
from ...puertos.correo import PROVEEDORES, CuentaNoConectada

#: El permiso que la 110 necesita en la cuenta: el último del alcance «enviar» de la 109 (P5: una vía).
PERMISO_ENVIAR = {p: PERMISOS[p]['enviar'][-1] for p in PROVEEDORES}
#: Lo que dice la ventana cuando la 109 todavía no comparte expedientes (su T6).
SIN_COMPARTIR = 'Compartir un expediente de la nube todavía no está disponible: envíe el informe como adjunto.'


def _tiene_permiso(concedidos: str, proveedor: str) -> bool:
    buscado = PERMISO_ENVIAR[proveedor]
    return any(p == buscado or p.endswith('/' + buscado) for p in str(concedidos or '').split())


class CredencialesDeLa109:
    """``FuenteDeCredenciales`` sobre la cuenta que el operador conectó en este espacio (109:RF-1, RF-2)."""

    def __init__(self, cuentas: Cuentas, wid: str):
        self.cuentas, self.wid = cuentas, wid

    def token(self, proveedor: str, cuenta: str, alcance: str) -> str:
        if proveedor not in PERMISO_ENVIAR:
            raise CuentaNoConectada(f'Proveedor de correo no admitido: {proveedor}.')
        try:
            # 109:RF-19: sin la aplicación registrada en este equipo, «Sin cuenta conectada: configure
            # config/nube.json» (``NoRegistrado``, un ``ErrorNube``), antes de leer el cofre.
            self.cuentas.cliente(proveedor)
            conectada = self.cuentas.cuenta(self.wid, proveedor)
            if not conectada or conectada.strip().lower() != str(cuenta).strip().lower():
                raise CuentaNoConectada(f'La cuenta {cuenta} no está conectada en este espacio: conéctela desde la '
                                        'web con el permiso de enviar.')
            permisos = getattr(self.cuentas, 'permisos', None)
            if callable(permisos) and not _tiene_permiso(permisos(self.wid, proveedor), proveedor):
                raise CuentaNoConectada('La cuenta no ha dado el permiso de enviar correo: conéctela con «enviar».')
            return self.cuentas.acceso(self.wid, proveedor)
        except (ErrorNube, SalidaApagada) as exc:  # el permiso caducó, se revocó, o la salida de la nube está apagada
            if isinstance(exc, NoRegistrado):
                raise CuentaNoConectada(str(exc)) from exc
            raise CuentaNoConectada(f'Vuelva a conectar la cuenta: {exc}') from exc
        except RuntimeError as exc:
            if isinstance(exc, CuentaNoConectada):
                raise
            # El cofre de la 109 (CofreIlegible, CofreNoDisponible) no se puede leer en este equipo.
            raise CuentaNoConectada(f'No se pudo leer la cuenta guardada: {exc}') from exc


class CompartidorDeLa109:
    """``Compartidor``: la 109 da la lectura del expediente a esos destinatarios exactos (109:RF-10)."""

    def __init__(self, cuentas: Cuentas, wid: str):
        self.cuentas, self.wid = cuentas, wid

    def conceder_lectura(self, expediente: str, destinatarios: Sequence[str]) -> Mapping[str, Any]:
        proveedor, _, item = str(expediente).partition(':')
        if proveedor not in PROVEEDORES or not item:
            return {'estado': 'rechazado', 'motivo': f'expediente sin proveedor: {expediente}', 'id': None}
        de_proveedor = getattr(self.cuentas, 'proveedor', None)
        if not callable(de_proveedor):
            return {'estado': 'rechazado', 'motivo': SIN_COMPARTIR, 'id': None}
        try:
            filas = de_proveedor(self.wid, proveedor).conceder_lectura(item, list(destinatarios))
        except (ErrorNube, SalidaApagada) as exc:
            return {'estado': 'rechazado', 'motivo': str(exc), 'id': None}
        concedidos = {str(f.get('destinatario', '')).lower() for f in filas}
        faltan = [d for d in destinatarios if d.lower() not in concedidos]
        if faltan:
            return {'estado': 'rechazado', 'motivo': f'sin permiso para {len(faltan)} destinatario(s)', 'id': None}
        return {'estado': 'concedido', 'motivo': '', 'id': ','.join(str(f.get('id_remoto') or '') for f in filas)}
