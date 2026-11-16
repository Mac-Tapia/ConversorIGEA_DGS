"""Las cuentas de nube conectadas: OAuth, cofre y transporte de cada espacio (109:RF-1, RF-2, RF-14, RF-17, RF-19).

Un objeto por servidor. Lee el cliente OAuth de ``config/nube.json`` en cada consulta (se registra sin rearrancar),
guarda el token de refresco en el cofre DPAPI del espacio y deja el de acceso solo en memoria. Cada espacio ve solo
sus cuentas: la clave es siempre (espacio, proveedor) (P13). ``transporte`` y ``proveedor`` dan el adaptador de Google
Drive o de OneDrive de un espacio, con su token de acceso renovado desde el cofre (T6).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from ... import nube_cofre
from ...salidas_red import SalidaApagada, motivo_apagada, salida_permitida
from .google_drive import HOSTS as HOSTS_GOOGLE
from .google_drive import GoogleDrive
from .http import Transporte
from .oauth import (ALCANCE_SELECTOR, ALCANCES, PERMISOS, Clientes, ClienteOAuth, Estados, NoRegistrado, Tokens, intercambiar,
                    leer_clientes, motivo_sin_registro, refrescar, revocar, ruta_config, transporte_oauth,
                    url_autorizacion)
from .onedrive import HOSTS as HOSTS_MICROSOFT
from .onedrive import OneDrive
from .proveedor import NOMBRES_VISIBLES, PROVEEDORES, ErrorNube, PermisoCaducado, ProveedorNube

#: 109:RF-16: los hosts de la API de cada proveedor; el de OAuth va aparte, en ``oauth.transporte_oauth``.
HOSTS_API = {'google': HOSTS_GOOGLE, 'microsoft': HOSTS_MICROSOFT}

#: Lo que se le dice al operador en la ventana de conexión (RF-1): qué se pide y por qué.
DESCRIPCION_PERMISOS = {
    'google': 'Solo los ficheros que usted elija y los que publique el conversor.',
    'microsoft': 'Leer sus ficheros de OneDrive; escribir solo cuando publique un expediente.',
}
AVISO_MICROSOFT = ('Microsoft no permite revocar el acceso desde aquí: se borró la credencial de este equipo. Para '
                   'retirar el permiso, entre en su cuenta de Microsoft, «Privacidad» → «Aplicaciones y servicios».')


def _concede(concedidos: list[str] | None, proveedor: str, alcance: str) -> bool | None:
    """Si los permisos concedidos cubren los del alcance (``publicar`` o ``enviar``); ``None`` si no se saben."""
    if concedidos is None:
        return None
    pedidos = {p for p in PERMISOS[proveedor][alcance] if p not in ('openid', 'email', 'offline_access')}
    return pedidos <= set(concedidos)


class Cuentas:
    def __init__(self, *, config: Path | None = None, cofre: Path | None = None, adaptador=None,
                 dormir: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.cofre = cofre
        self.adaptador = adaptador
        self.dormir = dormir
        self.estados = Estados()
        self._acceso: dict[tuple[str, str], Tokens] = {}
        self._lock = threading.Lock()

    # --------------------------------------------------------------- clientes
    def clientes(self) -> Clientes:
        return leer_clientes(self.config if self.config is not None else ruta_config())

    def cliente(self, proveedor: str) -> ClienteOAuth:
        if proveedor not in PROVEEDORES:
            raise NoRegistrado(f'Proveedor de nube desconocido: {proveedor!r}.')
        leidos = self.clientes()
        if proveedor not in leidos.clientes:
            raise NoRegistrado(leidos.errores.get(proveedor) or motivo_sin_registro(proveedor))
        return leidos.clientes[proveedor]

    def proveedores(self) -> list[dict]:
        """109:RF-19: cada proveedor con si está registrado y se puede conectar; nunca el identificador ni el secreto."""
        leidos = self.clientes()
        encendida = salida_permitida('nube')
        filas = []
        for p in PROVEEDORES:
            registrado = p in leidos.clientes
            motivo = None if registrado else (leidos.errores.get(p) or motivo_sin_registro(p))
            if registrado and not encendida:
                motivo = motivo_apagada('nube')
            filas.append({'nombre': p, 'visible': NOMBRES_VISIBLES[p], 'registrado': registrado,
                          'se_puede_conectar': registrado and encendida, 'motivo': motivo,
                          'permisos': DESCRIPCION_PERMISOS[p]})
        return filas

    # --------------------------------------------------------------- conexión
    def iniciar(self, wid: str, proveedor: str, *, publicar: bool = False, alcance: str | None = None) -> str:
        """109:RF-1: la URL del proveedor, con los permisos mínimos de la tarea y un ``state`` de un solo uso.

        ``alcance``: 'leer', 'publicar' o 'enviar' (110); sin él, ``publicar`` elige entre los dos primeros.
        """
        cliente = self.cliente(proveedor)
        if not salida_permitida('nube'):
            raise SalidaApagada(motivo_apagada('nube'))
        alcance = alcance or ('publicar' if publicar else 'leer')
        if alcance not in ALCANCES:
            raise ValueError(f'Permiso desconocido: {alcance!r}.')
        state, desafio = self.estados.emitir(wid, proveedor, alcance)
        return url_autorizacion(cliente, state, desafio, alcance)

    def completar(self, state: str, codigo: str) -> dict:
        pendiente = self.estados.consumir(state)
        cliente = self.cliente(pendiente.proveedor)
        tokens = intercambiar(cliente, self._transporte_oauth(pendiente.proveedor), codigo, pendiente.verificador)
        nube_cofre.guardar(pendiente.wid, pendiente.proveedor, tokens.cuenta, tokens.refresco, raiz=self.cofre)
        with self._lock:
            self._acceso[(pendiente.wid, pendiente.proveedor)] = tokens
        return {'wid': pendiente.wid, 'proveedor': pendiente.proveedor, 'cuenta': tokens.cuenta,
                'permisos': ' '.join(PERMISOS[pendiente.proveedor][pendiente.alcance])}

    def _transporte_oauth(self, proveedor: str) -> Transporte:
        return transporte_oauth(proveedor, adaptador=self.adaptador, dormir=self.dormir)

    def cuenta(self, wid: str, proveedor: str) -> str | None:
        cred = nube_cofre.leer(wid, proveedor, raiz=self.cofre)
        return cred.cuenta if cred else None

    def estado(self, wid: str) -> list[dict]:
        """Las cuentas de este espacio (solo el correo, nunca un token)."""
        filas = []
        for fila in self.proveedores():
            cuenta = self.cuenta(wid, fila['nombre']) if fila['registrado'] else None
            concedidos = self._concedidos(wid, fila['nombre']) if cuenta is not None else None
            filas.append({**fila, 'conectada': cuenta is not None, 'cuenta': cuenta,
                          'permisos_concedidos': concedidos,
                          'puede_publicar': _concede(concedidos, fila['nombre'], 'publicar'),
                          'puede_enviar': _concede(concedidos, fila['nombre'], 'enviar')})
        return filas

    def _concedidos(self, wid: str, proveedor: str) -> list[str] | None:
        """Los permisos concedidos, del último token; sin token en memoria se renueva una vez y, si no se puede,
        ``None`` (desconocido): el estado de las cuentas nunca falla por la red (109:RF-17)."""
        try:
            return sorted(self.permisos(wid, proveedor).split())
        except (ErrorNube, SalidaApagada, NoRegistrado):
            return None

    def permisos(self, wid: str, proveedor: str) -> str:
        """Los permisos que concedió la cuenta, según el último token (para pedir escritura en Microsoft)."""
        self.acceso(wid, proveedor)
        with self._lock:
            return self._acceso[(wid, proveedor)].permisos

    def acceso(self, wid: str, proveedor: str, renovar: bool = False) -> str:
        """El token de acceso vigente del espacio y el proveedor, renovado desde el cofre si caducó (lo usa la 110).

        Nunca se guarda: vive en memoria. ``PermisoCaducado`` si la cuenta no está conectada en este espacio.
        """
        with self._lock:
            vigente = self._acceso.get((wid, proveedor))
        if vigente is not None and not renovar and vigente.caduca > time.monotonic():
            return vigente.acceso
        cred = nube_cofre.leer(wid, proveedor, raiz=self.cofre)
        if cred is None:
            raise PermisoCaducado(f'La cuenta de {NOMBRES_VISIBLES[proveedor]} no está conectada en este espacio: '
                                  'conéctela desde la web.')
        tokens = refrescar(self.cliente(proveedor), self._transporte_oauth(proveedor), cred.refresco)
        if tokens.refresco and tokens.refresco != cred.refresco:
            nube_cofre.guardar(wid, proveedor, cred.cuenta, tokens.refresco, raiz=self.cofre)
        with self._lock:
            self._acceso[(wid, proveedor)] = tokens
        return tokens.acceso

    def desconectar(self, wid: str, proveedor: str) -> dict:
        """109:RF-14: revoca en el proveedor si se puede y borra la credencial; copias y recibos no se tocan."""
        cred = nube_cofre.leer(wid, proveedor, raiz=self.cofre)
        revocado, aviso = False, None
        if cred is not None:
            try:
                revocado = revocar(self.cliente(proveedor), self._transporte_oauth(proveedor), cred.refresco)
            except (ErrorNube, SalidaApagada) as exc:
                aviso = f'No se pudo avisar al proveedor ({exc}); la credencial de este equipo sí se borró.'
            if not revocado and aviso is None and proveedor == 'microsoft':
                aviso = AVISO_MICROSOFT
        nube_cofre.borrar(wid, proveedor, raiz=self.cofre)
        with self._lock:
            self._acceso.pop((wid, proveedor), None)
        return {'proveedor': proveedor, 'desconectada': True, 'revocado': revocado, 'aviso': aviso}

    # --------------------------------------------------------------- la API de cada proveedor (T6)
    def transporte(self, wid: str, proveedor: str) -> Transporte:
        """109:RF-16, RF-17: el transporte de la API del proveedor para este espacio, con su lista de hosts.

        El token de acceso lo da ``acceso`` en cada petición; un 401 lo renueva una vez desde el cofre.
        """
        self.cliente(proveedor)
        return Transporte(HOSTS_API[proveedor], autorizacion=lambda renovar: self.acceso(wid, proveedor, renovar),
                          adaptador=self.adaptador, dormir=self.dormir)

    def proveedor(self, wid: str, proveedor: str) -> ProveedorNube:
        """El adaptador de Google Drive o de OneDrive del espacio, detrás del contrato ``ProveedorNube``."""
        t = self.transporte(wid, proveedor)
        return GoogleDrive(t) if proveedor == 'google' else OneDrive(t)

    def token_selector(self, wid: str, proveedor: str) -> dict:
        """109:RF-2 (aclaración): un token de ACCESO nuevo, de corta duración y alcance de leer, para el selector.

        Nunca el de refresco ni el secreto del cliente. No se guarda en ningún sitio: ni en el cofre (el de refresco
        no cambia), ni en el espacio, ni en el navegador, que lo pide cada vez que abre el selector.
        """
        cliente = self.cliente(proveedor)
        cred = nube_cofre.leer(wid, proveedor, raiz=self.cofre)
        if cred is None:
            raise PermisoCaducado(f'La cuenta de {NOMBRES_VISIBLES[proveedor]} no está conectada en este espacio: '
                                  'conéctela desde la web.')
        alcance = ALCANCE_SELECTOR[proveedor]
        tokens = refrescar(cliente, self._transporte_oauth(proveedor), cred.refresco, alcance=alcance)
        if tokens.refresco and tokens.refresco != cred.refresco:
            nube_cofre.guardar(wid, proveedor, cred.cuenta, tokens.refresco, raiz=self.cofre)
        caduca = max(0, int(tokens.caduca - time.monotonic()))
        salida = {'proveedor': proveedor, 'token_acceso': tokens.acceso, 'caduca_en_s': min(caduca, 3600),
                  'alcance': tokens.permisos or alcance, 'id_cliente': cliente.id_cliente,
                  'clave_api': None, 'id_aplicacion': None}
        if proveedor == 'google':
            salida.update(clave_api=cliente.clave_api, id_aplicacion=cliente.id_aplicacion)
        return salida
