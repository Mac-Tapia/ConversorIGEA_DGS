"""OAuth 2.0 de Google y de Microsoft: cliente local, PKCE y ``state`` de un solo uso (109:RF-1, RF-14, RF-18, RF-19).

El cliente OAuth de cada proveedor lo registra el usuario con su cuenta (``docs/NUBE_REGISTRO_OAUTH.md``) y va en
``config/nube.json`` de este equipo, en ``.gitignore`` (RF-18). Sin él, la web dice «Sin cuenta conectada: configure
config/nube.json» y no ofrece conectar (RF-19). Para la 1.0 basta una aplicación en modo de prueba: Google Cloud en
«Testing», con hasta 100 usuarios de prueba y sin verificación, o Azure con cuentas personales. Son clientes públicos
con PKCE (S256) y retorno por la interfaz de bucle local, como piden Google y Microsoft para las aplicaciones de
escritorio: el secreto, si el proveedor lo da, no se trata como confidencial.

Permisos mínimos (RF-1): en Google, ``drive.file`` (solo lo que el operador elige o la aplicación crea) y
``openid email``; en Microsoft, ``Files.Read`` al conectar y ``Files.ReadWrite`` solo al publicar, con
``offline_access``. Nunca se pide ni se guarda una contraseña: el operador la escribe en la página del proveedor.

Microsoft no tiene un punto de revocación OAuth estándar para estos clientes: desconectar borra el token del cofre y
el instructivo dice cómo retirar el consentimiento en la cuenta (decisión del 2026-11-14).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from ...dominio.runtime_paths import raiz_local
from .http import Hosts, Transporte
from .proveedor import NOMBRES_VISIBLES, PROVEEDORES, ErrorNube, PermisoCaducado

VARIABLE_CONFIG = 'CSG_NUBE_CONFIG'
#: 10 min: lo que tarda el operador en iniciar sesión y consentir; un ``state`` más viejo no vale.
CADUCIDAD_ESTADO_S = 600
_BUCLE_LOCAL = frozenset({'127.0.0.1', 'localhost', '::1'})
RUTA_RETORNO = '/nube/retorno'

PERMISOS: dict[str, dict[str, tuple[str, ...]]] = {
    'google': {'leer': ('openid', 'email', 'https://www.googleapis.com/auth/drive.file'),
               'publicar': ('openid', 'email', 'https://www.googleapis.com/auth/drive.file'),
               # 110: enviar informes por correo, solo enviar (ni leer ni borrar el buzón).
               'enviar': ('openid', 'email', 'https://www.googleapis.com/auth/gmail.send')},
    'microsoft': {'leer': ('openid', 'email', 'offline_access', 'Files.Read'),
                  # Con Files.Read también: el selector pide al refrescar solo leer, y tiene que estar consentido.
                  'publicar': ('openid', 'email', 'offline_access', 'Files.Read', 'Files.ReadWrite'),
                  'enviar': ('openid', 'email', 'offline_access', 'Mail.Send')},
}
ALCANCES = ('leer', 'publicar', 'enviar')
_AUTORIZACION = {'google': 'https://accounts.google.com/o/oauth2/v2/auth',
                 'microsoft': 'https://login.microsoftonline.com/{inquilino}/oauth2/v2.0/authorize'}
_TOKEN = {'google': 'https://oauth2.googleapis.com/token',
          'microsoft': 'https://login.microsoftonline.com/{inquilino}/oauth2/v2.0/token'}
_REVOCACION = {'google': 'https://oauth2.googleapis.com/revoke'}
HOSTS_OAUTH = {'google': Hosts(frozenset({'oauth2.googleapis.com'})),
               'microsoft': Hosts(frozenset({'login.microsoftonline.com'}))}


class NoRegistrado(ErrorNube):
    causa = 'falta registrar la aplicación'


class EstadoInvalido(ErrorNube):
    causa = 'la vuelta del proveedor no es de esta conexión'


def ruta_config(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    otra = str(env.get(VARIABLE_CONFIG) or '').strip()
    return Path(otra) if otra else raiz_local(environ=env) / 'config' / 'nube.json'


@dataclass(frozen=True)
class ClienteOAuth:
    proveedor: str
    id_cliente: str
    uri_retorno: str
    secreto: str = field(default='', repr=False)
    inquilino: str = 'common'
    #: Google Picker: la clave de API y el número del proyecto. Son públicas por diseño (van en la página del
    #: selector); el secreto del cliente, no.
    clave_api: str = ''
    id_aplicacion: str = ''
    #: OneDrive de empresa: la dirección del selector de SharePoint del inquilino (vacía: OneDrive personal).
    url_selector: str = ''


@dataclass
class Clientes:
    clientes: dict[str, ClienteOAuth] = field(default_factory=dict)
    errores: dict[str, str] = field(default_factory=dict)


def motivo_sin_registro(proveedor: str) -> str:
    return (f'Sin cuenta conectada: configure config/nube.json (falta registrar la aplicación de '
            f'{NOMBRES_VISIBLES[proveedor]} en este equipo; ver docs/NUBE_REGISTRO_OAUTH.md).')


def _retorno_valido(uri: str) -> bool:
    partes = urlsplit(uri)
    return (partes.scheme == 'http' and (partes.hostname or '') in _BUCLE_LOCAL
            and partes.path == RUTA_RETORNO and not partes.query)


def leer_clientes(ruta: Path | None = None) -> Clientes:
    """109:RF-18: los clientes de ``config/nube.json``; cada uno que falte o no valga, con su motivo (nunca falla)."""
    ruta = ruta_config() if ruta is None else Path(ruta)
    salida = Clientes()
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError:
        datos = {}
    except (OSError, ValueError) as exc:
        for p in PROVEEDORES:
            salida.errores[p] = f'No se pudo leer {ruta.name}: {type(exc).__name__}. {motivo_sin_registro(p)}'
        return salida
    if not isinstance(datos, dict):
        datos = {}
    for p in PROVEEDORES:
        bloque = datos.get(p)
        if not isinstance(bloque, dict):
            salida.errores[p] = motivo_sin_registro(p)
            continue
        ident = str(bloque.get('id_cliente') or '').strip()
        uri = str(bloque.get('uri_retorno') or '').strip()
        if not ident or ident.startswith('<'):
            salida.errores[p] = f'Falta el identificador del cliente de {NOMBRES_VISIBLES[p]} en {ruta.name}.'
        elif not _retorno_valido(uri):
            salida.errores[p] = (f'El retorno de {NOMBRES_VISIBLES[p]} tiene que ser de esta máquina: '
                                 f'http://127.0.0.1:<puerto>{RUTA_RETORNO}.')
        else:
            salida.clientes[p] = ClienteOAuth(p, ident, uri, str(bloque.get('secreto') or ''),
                                              str(bloque.get('inquilino') or 'common'),
                                              str(bloque.get('clave_api') or ''), str(bloque.get('id_aplicacion') or ''),
                                              str(bloque.get('url_selector') or ''))
    return salida


# --------------------------------------------------------------------------- PKCE y state
def pkce() -> tuple[str, str]:
    """RFC 7636: el verificador (43-128 caracteres) y su desafío S256."""
    verificador = secrets.token_urlsafe(64)[:96]
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode('ascii')).digest()).decode().rstrip('=')
    return verificador, desafio


@dataclass(frozen=True)
class Pendiente:
    wid: str
    proveedor: str
    verificador: str = field(repr=False)
    alcance: str
    creado: float


class Estados:
    """Los ``state`` emitidos: un solo uso, ligados al espacio y al proveedor, y con caducidad."""

    def __init__(self, caducidad_s: float = CADUCIDAD_ESTADO_S, reloj=time.monotonic) -> None:
        self._pendientes: dict[str, Pendiente] = {}
        self._lock = threading.Lock()
        self._caducidad_s = caducidad_s
        self._reloj = reloj

    def emitir(self, wid: str, proveedor: str, alcance: str) -> tuple[str, str]:
        verificador, desafio = pkce()
        state = secrets.token_urlsafe(32)
        with self._lock:
            ahora = self._reloj()
            for clave in [k for k, v in self._pendientes.items() if ahora - v.creado > self._caducidad_s]:
                del self._pendientes[clave]
            self._pendientes[state] = Pendiente(wid, proveedor, verificador, alcance, ahora)
        return state, desafio

    def consumir(self, state: str, *, wid: str | None = None, proveedor: str | None = None) -> Pendiente:
        with self._lock:
            pendiente = self._pendientes.pop(state or '', None)
        if pendiente is None:
            raise EstadoInvalido('Esta vuelta del proveedor no corresponde a ninguna conexión en curso, o ya se '
                                 'usó: vuelva a conectar desde la web.')
        if self._reloj() - pendiente.creado > self._caducidad_s:
            raise EstadoInvalido('La conexión tardó demasiado y caducó: vuelva a conectar desde la web.')
        if (wid is not None and wid != pendiente.wid) or (proveedor is not None and proveedor != pendiente.proveedor):
            raise EstadoInvalido('Esta vuelta del proveedor es de otro espacio de trabajo: no se conecta.')
        return pendiente


def url_autorizacion(cliente: ClienteOAuth, state: str, desafio: str, alcance: str) -> str:
    """La página del proveedor donde el operador inicia sesión y consiente; la contraseña nunca pasa por aquí."""
    parametros = {'client_id': cliente.id_cliente, 'redirect_uri': cliente.uri_retorno, 'response_type': 'code',
                  'scope': ' '.join(PERMISOS[cliente.proveedor][alcance]), 'state': state,
                  'code_challenge': desafio, 'code_challenge_method': 'S256'}
    if cliente.proveedor == 'google':
        # Sin «prompt=consent» Google no vuelve a dar el token de refresco tras la primera vez.
        parametros.update(access_type='offline', prompt='consent', include_granted_scopes='true')
    else:
        parametros.update(response_mode='query', prompt='select_account')
    return _AUTORIZACION[cliente.proveedor].format(inquilino=cliente.inquilino) + '?' + urlencode(parametros)


# --------------------------------------------------------------------------- tokens
@dataclass(frozen=True)
class Tokens:
    acceso: str = field(repr=False)
    caduca: float
    refresco: str = field(default='', repr=False)
    cuenta: str = ''
    permisos: str = ''


def cuenta_de(id_token: str) -> str:
    """El correo de la cuenta, del ``id_token`` que el propio proveedor acaba de dar por TLS."""
    try:
        carga = id_token.split('.')[1]
        datos = json.loads(base64.urlsafe_b64decode(carga + '=' * (-len(carga) % 4)))
    except (IndexError, ValueError):
        return ''
    return str(datos.get('email') or datos.get('preferred_username') or '')


def transporte_oauth(proveedor: str, **kw) -> Transporte:
    return Transporte(HOSTS_OAUTH[proveedor], **kw)


def _pedir_token(cliente: ClienteOAuth, transporte: Transporte, formulario: dict) -> dict:
    formulario = {**formulario, 'client_id': cliente.id_cliente}
    if cliente.secreto:
        formulario['client_secret'] = cliente.secreto
    return transporte.json('POST', _TOKEN[cliente.proveedor].format(inquilino=cliente.inquilino),
                           data=formulario, autenticar=False,
                           cabeceras={'Content-Type': 'application/x-www-form-urlencoded'})


def _tokens(datos: dict, refresco: str = '') -> Tokens:
    acceso = str(datos.get('access_token') or '')
    if not acceso:
        raise PermisoCaducado('El proveedor no dio un token de acceso: vuelva a conectar la cuenta.')
    return Tokens(acceso, time.monotonic() + float(datos.get('expires_in') or 3600) - 60,
                  str(datos.get('refresh_token') or refresco), cuenta_de(str(datos.get('id_token') or '')),
                  str(datos.get('scope') or ''))


def intercambiar(cliente: ClienteOAuth, transporte: Transporte, codigo: str, verificador: str) -> Tokens:
    tokens = _tokens(_pedir_token(cliente, transporte, {'grant_type': 'authorization_code', 'code': codigo,
                                                        'redirect_uri': cliente.uri_retorno,
                                                        'code_verifier': verificador}))
    if not tokens.refresco:
        raise PermisoCaducado('El proveedor no dio un token de refresco: vuelva a conectar y acepte el acceso.')
    return tokens


def refrescar(cliente: ClienteOAuth, transporte: Transporte, refresco: str, *, alcance: str | None = None) -> Tokens:
    """Un token de acceso nuevo; con ``alcance``, reducido a esos permisos (Microsoft lo admite al refrescar)."""
    formulario = {'grant_type': 'refresh_token', 'refresh_token': refresco}
    if alcance and cliente.proveedor == 'microsoft':
        formulario['scope'] = alcance
    return _tokens(_pedir_token(cliente, transporte, formulario), refresco)


def revocar(cliente: ClienteOAuth, transporte: Transporte, token: str) -> bool:
    """109:RF-14: revoca en Google; Microsoft no tiene un punto estándar y se dice cómo retirarlo en la cuenta."""
    url = _REVOCACION.get(cliente.proveedor)
    if not url:
        return False
    transporte.pedir('POST', url, data={'token': token}, autenticar=False,
                     cabeceras={'Content-Type': 'application/x-www-form-urlencoded'})
    return True


#: 109:RF-2 (aclaración del 2026-11-14): el selector recibe solo un token de acceso de este alcance, el de leer.
ALCANCE_SELECTOR = {'google': 'https://www.googleapis.com/auth/drive.file', 'microsoft': 'Files.Read'}
