"""Proveedor de nube simulado para la spec 109: Drive v3 y Graph v1.0 en memoria, montados en ``requests``.

Es un ``requests.adapters.BaseAdapter``: ``Transporte(..., adaptador=sim)`` lo monta y ninguna petición sale de la
máquina. Imita lo que el conversor usa de cada API (metadatos con revisión y huella, ``alt=media`` con ``Range``,
exportación, paginación, subidas reanudables, permisos, token y revocación) y admite fallos inyectables: 401, 403,
404, 429 con ``Retry-After``, corte a mitad, cambio de revisión a mitad, redirección a otro host, ``nextLink`` ajeno y
token revocado. Como ``tests/fake_pf.py`` con DIgSILENT: la prueba con el simulado no acredita la integración real
(spec 109, criterio de finalización).

``sin_sockets`` es el guardián: falla ante cualquier socket real que abra una prueba.
"""
from __future__ import annotations

import base64
import hashlib
import io
import itertools
import json
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

import pytest
import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict

GOOGLE_API = 'www.googleapis.com'
GOOGLE_TOKEN = 'oauth2.googleapis.com'
GRAPH = 'graph.microsoft.com'
MS_LOGIN = 'login.microsoftonline.com'
DESCARGA_MS = 'sim-descarga.files.1drv.com'
SUBIDA_MS = 'sim-my.sharepoint.com'


# --------------------------------------------------------------------------- guardián
_LOCALES = frozenset({'127.0.0.1', '::1', 'localhost'})


@pytest.fixture
def sin_sockets(monkeypatch):
    """Ninguna prueba de la 109 sale de la máquina: un socket a otra dirección hace fallar la prueba.

    La conexión de bucle local se deja: en Windows, ``socket.socketpair`` (el «self-pipe» de asyncio, que usa el cliente
    de pruebas de FastAPI) conecta dos sockets por 127.0.0.1.
    """
    conectar, conectar_ex, crear = socket.socket.connect, socket.socket.connect_ex, socket.create_connection

    def _comprobar(direccion) -> None:
        host = direccion[0] if isinstance(direccion, tuple) and direccion else direccion
        if str(host) not in _LOCALES:
            raise AssertionError(f'Una prueba de la nube intentó abrir un socket real ({host}).')

    def connect(self, direccion):
        _comprobar(direccion)
        return conectar(self, direccion)

    def connect_ex(self, direccion):
        _comprobar(direccion)
        return conectar_ex(self, direccion)

    def create_connection(direccion, *a, **k):
        _comprobar(direccion)
        return crear(direccion, *a, **k)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex)
    monkeypatch.setattr(socket, 'create_connection', create_connection)
    yield


# --------------------------------------------------------------------------- utilidades
def quickxor(datos: bytes) -> str:
    """QuickXorHash de OneDrive (documentación de Microsoft Graph), en base64."""
    ancho, h = 160, 0
    mascara = (1 << ancho) - 1
    for i, b in enumerate(datos):
        p = (i * 11) % ancho
        v = b << p
        h ^= (v | (v >> ancho)) & mascara
    h ^= len(datos) << 96
    return base64.b64encode((h & mascara).to_bytes(20, 'little')).decode('ascii')


def _jwt(carga: dict) -> str:
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return f"{b64({'alg': 'none'})}.{b64(carga)}.firma"


class _Cuerpo(io.RawIOBase):
    """Cuerpo de una respuesta que puede cortarse a mitad o ejecutar algo al leer un bloque."""

    def __init__(self, datos: bytes, corte: int | None = None, al_leer=None) -> None:
        self._b = io.BytesIO(datos)
        self._corte = corte
        self._al_leer = al_leer

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        pos = self._b.tell()
        if self._corte is not None and pos >= self._corte:
            raise requests.ConnectionError('corte simulado')
        if self._corte is not None and n and n > 0:
            n = min(n, self._corte - pos)
        elif self._corte is not None:
            n = self._corte - pos
        bloque = self._b.read(n)
        if self._al_leer is not None and bloque:
            self._al_leer()
        return bloque


@dataclass
class Fichero:
    proveedor: str
    id: str
    nombre: str
    contenido: bytes = b''
    padre: str = 'raiz'
    tipo: str = 'application/octet-stream'
    revision: int = 1
    carpeta: bool = False
    nativo: bool = False
    solo_lectura: bool = False
    exportado: bytes = b''
    propiedades: dict = field(default_factory=dict)
    permisos: list = field(default_factory=list)


@dataclass
class Fallo:
    estado: int
    contiene: str
    metodo: str | None
    veces: int
    cabeceras: dict
    cuerpo: dict | None


class NubeSimulada(BaseAdapter):
    """Google Drive v3 y Microsoft Graph v1.0 en memoria."""

    def __init__(self) -> None:
        super().__init__()
        self.ficheros: dict[str, Fichero] = {}
        self.peticiones: list[tuple[str, str]] = []
        self.fallos: list[Fallo] = []
        self.acceso: dict[str, tuple[str, str]] = {}
        self.refresco: dict[str, tuple[str, str, str]] = {}
        self.codigos: dict[str, dict] = {}
        self.revocados: list[str] = []
        self.sesiones: dict[str, dict] = {}
        self.subidas_completadas = 0
        self.cortes: dict[str, int] = {}
        self.cambia_a_mitad: set[str] = set()
        self.revoca_a_mitad: set[str] = set()
        self.next_link_ajeno = False
        self.host_descarga = DESCARGA_MS
        self.corta_subida_tras: int | None = None
        self._n = itertools.count(1)
        for prov in ('google', 'microsoft'):
            self.ficheros[f'raiz-{prov}'] = Fichero(prov, f'raiz-{prov}', 'Mi unidad', carpeta=True, padre='')

    # ------------------------------------------------------------- preparación
    def crear(self, proveedor: str, nombre: str, contenido: bytes = b'', *, padre: str | None = None,
              tipo: str = 'application/octet-stream', carpeta: bool = False, nativo: bool = False,
              solo_lectura: bool = False, exportado: bytes = b'') -> str:
        fid = f'{proveedor[0]}{next(self._n):05d}'
        self.ficheros[fid] = Fichero(proveedor, fid, nombre, contenido, padre or f'raiz-{proveedor}', tipo,
                                     carpeta=carpeta, nativo=nativo, solo_lectura=solo_lectura, exportado=exportado)
        return fid

    def modificar(self, fid: str, contenido: bytes) -> None:
        f = self.ficheros[fid]
        f.contenido = contenido
        f.revision += 1

    def fallar(self, estado: int, *, contiene: str = '', metodo: str | None = None, veces: int = 1,
               cabeceras: dict | None = None, cuerpo: dict | None = None) -> None:
        self.fallos.append(Fallo(estado, contiene, metodo, veces, cabeceras or {}, cuerpo))

    def dar_token(self, proveedor: str, cuenta: str = 'operador@ejemplo.org') -> str:
        token = f'acc-{proveedor}-{next(self._n)}'
        self.acceso[token] = (proveedor, cuenta)
        return token

    def revocar_todo(self) -> None:
        self.acceso.clear()
        self.refresco.clear()

    def autorizar(self, url_autorizacion: str, cuenta: str = 'operador@ejemplo.org') -> dict:
        """Lo que haría el operador en la página del proveedor: consiente y vuelve con ``code`` y ``state``."""
        q = {k: v[0] for k, v in parse_qs(urlsplit(url_autorizacion).query).items()}
        codigo = f'cod-{next(self._n)}'
        prov = 'google' if 'google' in url_autorizacion else 'microsoft'
        self.codigos[codigo] = {'proveedor': prov, 'cuenta': cuenta, 'desafio': q.get('code_challenge'),
                                'retorno': q.get('redirect_uri'), 'alcance': q.get('scope', ''),
                                'cliente': q.get('client_id')}
        return {'code': codigo, 'state': q.get('state')}

    def hijos(self, padre: str) -> list[Fichero]:
        return [f for f in self.ficheros.values() if f.padre == padre]

    # ------------------------------------------------------------- respuesta
    @staticmethod
    def _resp(peticion, estado: int, datos=None, *, contenido: bytes | None = None, cabeceras: dict | None = None,
              corte: int | None = None, al_leer=None) -> requests.Response:
        r = requests.Response()
        r.status_code = estado
        r.headers = CaseInsensitiveDict(cabeceras or {})
        if datos is not None:
            contenido = json.dumps(datos).encode('utf-8')
            r.headers.setdefault('Content-Type', 'application/json')
        r.raw = _Cuerpo(contenido or b'', corte, al_leer)
        r.url = peticion.url
        r.request = peticion
        r.encoding = 'utf-8'
        r.reason = str(estado)
        return r

    def close(self) -> None:
        pass

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):  # noqa: D401
        metodo, url = request.method, request.url
        self.peticiones.append((metodo, url))
        for fallo in self.fallos:
            if fallo.veces > 0 and fallo.contiene in url and (fallo.metodo in (None, metodo)):
                fallo.veces -= 1
                return self._resp(request, fallo.estado, fallo.cuerpo if fallo.cuerpo is not None
                                  else {'error': {'code': f'simulado{fallo.estado}'}}, cabeceras=fallo.cabeceras)
        partes = urlsplit(url)
        host = partes.hostname or ''
        q = {k: v[0] for k, v in parse_qs(partes.query, keep_blank_values=True).items()}
        if host == GOOGLE_TOKEN:
            return self._token(request, 'google', partes.path)
        if host == MS_LOGIN:
            return self._token(request, 'microsoft', partes.path)
        if host == DESCARGA_MS or host == self.host_descarga:
            return self._media_ms(request, partes.path, q)
        if host == SUBIDA_MS:
            return self._subida_ms(request, partes.path)
        if host == GOOGLE_API and partes.path.startswith('/upload/'):
            if not self._autenticado(request, 'google'):
                return self._resp(request, 401, {'error': {'code': 401, 'status': 'UNAUTHENTICATED'}})
            return self._subida_google(request, q)
        if host in (GOOGLE_API, GRAPH):
            prov = 'google' if host == GOOGLE_API else 'microsoft'
            if not self._autenticado(request, prov):
                return self._resp(request, 401, {'error': {'code': 'InvalidAuthenticationToken'}})
            return self._google(request, partes.path, q) if prov == 'google' else self._graph(request, partes.path, q)
        return self._resp(request, 404, {'error': {'code': 'hostDesconocido'}})

    def _autenticado(self, request, prov: str) -> bool:
        token = (request.headers.get('Authorization') or '').removeprefix('Bearer ')
        return self.acceso.get(token, ('', ''))[0] == prov

    def _cuerpo_json(self, request) -> dict:
        cuerpo = request.body or b'{}'
        return json.loads(cuerpo.decode('utf-8') if isinstance(cuerpo, bytes) else cuerpo)

    # ------------------------------------------------------------- OAuth
    def _token(self, request, prov: str, ruta: str):
        cuerpo = request.body.decode() if isinstance(request.body, bytes) else (request.body or '')
        f = {k: v[0] for k, v in parse_qs(cuerpo).items()}
        if ruta.endswith('/revoke'):
            self.revocados.append(f.get('token', ''))
            self.refresco.pop(f.get('token', ''), None)
            return self._resp(request, 200, {})
        if f.get('grant_type') == 'authorization_code':
            datos = self.codigos.pop(f.get('code', ''), None)
            desafio = base64.urlsafe_b64encode(hashlib.sha256(f.get('code_verifier', '').encode()).digest()
                                               ).decode().rstrip('=')
            if (not datos or datos['proveedor'] != prov or datos['desafio'] != desafio
                    or datos['retorno'] != f.get('redirect_uri')):
                return self._resp(request, 400, {'error': 'invalid_grant'})
            refresco = f'ref-{prov}-{next(self._n)}'
            self.refresco[refresco] = (prov, datos['cuenta'], datos['alcance'])
            clave = 'email' if prov == 'google' else 'preferred_username'
            return self._resp(request, 200, {'access_token': self.dar_token(prov, datos['cuenta']),
                                             'refresh_token': refresco, 'expires_in': 3599,
                                             'scope': datos['alcance'], 'token_type': 'Bearer',
                                             'id_token': _jwt({clave: datos['cuenta'], 'sub': datos['cuenta']})})
        if f.get('grant_type') == 'refresh_token':
            datos = self.refresco.get(f.get('refresh_token', ''))
            if not datos or datos[0] != prov:
                return self._resp(request, 400, {'error': 'invalid_grant'})
            pedido = f.get('scope')
            if pedido and not set(pedido.split()) <= set(datos[2].split()):
                return self._resp(request, 400, {'error': 'invalid_scope'})
            return self._resp(request, 200, {'access_token': self.dar_token(prov, datos[1]), 'expires_in': 3599,
                                             'scope': pedido or datos[2], 'token_type': 'Bearer'})
        return self._resp(request, 400, {'error': 'unsupported_grant_type'})

    # ------------------------------------------------------------- medios
    def _rango(self, request, datos: bytes) -> tuple[int, bytes, dict]:
        rango = request.headers.get('Range')
        if not rango:
            return 200, datos, {}
        a, _, b = rango.removeprefix('bytes=').partition('-')
        ini, fin = int(a), (int(b) if b else len(datos) - 1)
        trozo = datos[ini:fin + 1]
        return 206, trozo, {'Content-Range': f'bytes {ini}-{ini + len(trozo) - 1}/{len(datos)}'}

    def _media(self, request, f: Fichero, datos: bytes):
        estado, trozo, cab = self._rango(request, datos)
        corte = self.cortes.pop(f.id, None)
        al_leer = None
        if f.id in self.cambia_a_mitad:
            self.cambia_a_mitad.discard(f.id)

            def al_leer():
                f.revision += 1
        elif f.id in self.revoca_a_mitad:
            self.revoca_a_mitad.discard(f.id)
            corte = max(1, len(trozo) // 2) if corte is None else corte
            al_leer = self.revocar_todo
        return self._resp(request, estado, contenido=trozo, cabeceras=cab, corte=corte, al_leer=al_leer)

    # ------------------------------------------------------------- Google Drive v3
    def _meta_google(self, f: Fichero) -> dict:
        datos = {'id': f.id, 'name': f.nombre, 'parents': [f.padre] if f.padre else [],
                 'mimeType': ('application/vnd.google-apps.folder' if f.carpeta else
                              'application/vnd.google-apps.spreadsheet' if f.nativo else f.tipo),
                 'version': str(f.revision), 'modifiedTime': f'2026-11-14T10:00:{f.revision % 60:02d}Z',
                 'capabilities': {'canEdit': not f.solo_lectura, 'canAddChildren': not f.solo_lectura},
                 'appProperties': dict(f.propiedades)}
        if not f.carpeta and not f.nativo:
            datos.update(size=str(len(f.contenido)), headRevisionId=f'rev{f.revision}',
                         md5Checksum=hashlib.md5(f.contenido).hexdigest(),
                         sha256Checksum=hashlib.sha256(f.contenido).hexdigest())
        return datos

    def _google(self, request, ruta: str, q: dict):
        partes = [unquote(p) for p in ruta.split('/') if p]
        if partes[:3] != ['drive', 'v3', 'files']:
            return self._resp(request, 404, {'error': {'code': 404}})
        if len(partes) == 3 and request.method == 'GET':
            return self._lista_google(request, q)
        f = self.ficheros.get(partes[3]) if len(partes) > 3 else None
        if f is None or f.proveedor != 'google':
            return self._resp(request, 404, {'error': {'code': 404, 'message': 'File not found'}})
        if len(partes) == 4 and request.method == 'GET':
            if q.get('alt') == 'media':
                if f.nativo:
                    return self._resp(request, 403, {'error': {'code': 'fileNotDownloadable'}})
                return self._media(request, f, f.contenido)
            return self._resp(request, 200, self._meta_google(f))
        if len(partes) == 5 and partes[4] == 'export':
            return self._media(request, f, f.exportado)
        if len(partes) == 5 and partes[4] == 'permissions' and request.method == 'POST':
            c = self._cuerpo_json(request)
            permiso = {'id': f'perm-{next(self._n)}', 'role': c.get('role'), 'type': c.get('type'),
                       'emailAddress': c.get('emailAddress')}
            f.permisos.append(permiso)
            return self._resp(request, 200, permiso)
        return self._resp(request, 404, {'error': {'code': 404}})

    def _lista_google(self, request, q: dict):
        consulta = q.get('q', '')
        candidatos = [f for f in self.ficheros.values() if f.proveedor == 'google' and f.padre]
        prop = re.search(r"appProperties has \{ key='([^']*)' and value='([^']*)' \}", consulta)
        if prop:
            candidatos = [f for f in candidatos if f.propiedades.get(prop.group(1)) == prop.group(2)]
            consulta = consulta.replace(prop.group(0), 'trashed = false')
        for trozo in consulta.split(' and '):
            trozo = trozo.strip()
            if trozo.endswith("in parents"):
                padre = trozo.split("'")[1]
                candidatos = [f for f in candidatos if f.padre == padre]
            elif trozo.startswith('name ='):
                nombre = trozo.split("'")[1].replace("\\'", "'")
                candidatos = [f for f in candidatos if f.nombre == nombre]
        candidatos.sort(key=lambda f: f.id)
        tam = int(q.get('pageSize') or 100)
        ini = int(q.get('pageToken') or 0)
        pagina = candidatos[ini:ini + tam]
        datos = {'files': [self._meta_google(f) for f in pagina]}
        if ini + tam < len(candidatos):
            datos['nextPageToken'] = str(ini + tam)
        return self._resp(request, 200, datos)

    def _subida_google(self, request, q: dict):
        if request.method == 'POST' and q.get('uploadType') == 'resumable':
            c = self._cuerpo_json(request)
            padre = self.ficheros.get((c.get('parents') or ['raiz-google'])[0])
            if padre is None:
                return self._resp(request, 404, {'error': {'code': 404}})
            if padre.solo_lectura:
                return self._resp(request, 403, {'error': {'code': 'insufficientFilePermissions'}})
            sid = f'up{next(self._n)}'
            self.sesiones[sid] = {'prov': 'google', 'meta': c, 'datos': b''}
            return self._resp(request, 200, {}, cabeceras={
                'Location': f'https://{GOOGLE_API}/upload/drive/v3/files?uploadType=resumable&upload_id={sid}'})
        if request.method == 'PUT' and q.get('upload_id') in self.sesiones:
            return self._trozo(request, self.sesiones[q['upload_id']])
        return self._resp(request, 404, {'error': {'code': 404}})

    def _trozo(self, request, sesion: dict):
        rango = request.headers.get('Content-Range', '')
        total = int(rango.rsplit('/', 1)[1]) if '/' in rango else 0
        cuerpo = request.body or b''
        if hasattr(cuerpo, 'read'):
            cuerpo = cuerpo.read()
        if not rango.startswith('bytes */'):
            ini = int(rango.removeprefix('bytes ').split('-')[0])
            if ini != len(sesion['datos']):
                return self._resp(request, 416, {'error': {'code': 'rangoInvalido'}})
            if self.corta_subida_tras is not None and len(sesion['datos']) + len(cuerpo) > self.corta_subida_tras:
                guardar = self.corta_subida_tras - len(sesion['datos'])
                sesion['datos'] += cuerpo[:max(0, guardar)]
                self.corta_subida_tras = None
                raise requests.ConnectionError('corte simulado de la subida')
            sesion['datos'] += cuerpo
        hecho = len(sesion['datos'])
        if total and hecho >= total:
            return self._completar(request, sesion)
        if sesion['prov'] == 'google':
            cab = {'Range': f'bytes=0-{hecho - 1}'} if hecho else {}
            return self._resp(request, 308, contenido=b'', cabeceras=cab)
        return self._resp(request, 202, {'nextExpectedRanges': [f'{hecho}-']})

    def _completar(self, request, sesion: dict):
        meta = sesion['meta']
        self.subidas_completadas += 1
        if sesion['prov'] == 'google':
            fid = self.crear('google', meta['name'], sesion['datos'], padre=(meta.get('parents') or [None])[0])
            self.ficheros[fid].propiedades = dict(meta.get('appProperties') or {})
            return self._resp(request, 200, self._meta_google(self.ficheros[fid]))
        fid = self.crear('microsoft', meta['name'], sesion['datos'], padre=meta['padre'])
        return self._resp(request, 201, self._meta_graph(self.ficheros[fid]))

    # ------------------------------------------------------------- Microsoft Graph v1.0
    def _meta_graph(self, f: Fichero) -> dict:
        datos = {'id': f.id, 'name': f.nombre, 'eTag': f'"{f.id},{f.revision}x"', 'cTag': f'"c:{f.id},{f.revision}"',
                 'lastModifiedDateTime': f'2026-11-14T10:00:{f.revision % 60:02d}Z',
                 'parentReference': {'id': f.padre}}
        if f.carpeta:
            datos['folder'] = {'childCount': len(self.hijos(f.id))}
        else:
            datos.update(size=len(f.contenido), file={'mimeType': f.tipo, 'hashes': {
                'sha256Hash': hashlib.sha256(f.contenido).hexdigest().upper(), 'quickXorHash': quickxor(f.contenido)}})
            datos['@microsoft.graph.downloadUrl'] = f'https://{self.host_descarga}/descarga/{f.id}?t={next(self._n)}'
        if f.solo_lectura:
            datos['shared'] = {'scope': 'users'}
        return datos

    def _graph(self, request, ruta: str, q: dict):
        ruta = unquote(ruta)
        base = '/v1.0/me/drive/items/'
        if not ruta.startswith(base):
            return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
        resto = ruta[len(base):]
        if ':/' in resto:                                       # items/{padre}:/{nombre}:/createUploadSession
            padre_id, _, cola = resto.partition(':/')
            nombre, _, accion = cola.partition(':')
            padre = self.ficheros.get(padre_id)
            if padre is None:
                return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
            existente = next((f for f in self.hijos(padre_id) if f.nombre == nombre), None)
            if accion == '/createUploadSession' and request.method == 'POST':
                if padre.solo_lectura:
                    return self._resp(request, 403, {'error': {'code': 'accessDenied'}})
                c = self._cuerpo_json(request)
                conflicto = (c.get('item') or {}).get('@microsoft.graph.conflictBehavior')
                if existente is not None and conflicto == 'fail':
                    return self._resp(request, 409, {'error': {'code': 'nameAlreadyExists'}})
                sid = f'up{next(self._n)}'
                self.sesiones[sid] = {'prov': 'microsoft', 'meta': {'name': nombre, 'padre': padre_id}, 'datos': b''}
                return self._resp(request, 200, {'uploadUrl': f'https://{SUBIDA_MS}/subida/{sid}',
                                                 'expirationDateTime': '2026-11-15T00:00:00Z'})
            if accion == '' and request.method == 'GET':
                if existente is None:
                    return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
                return self._resp(request, 200, self._meta_graph(existente))
            return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
        item_id, _, accion = resto.partition('/')
        f = self.ficheros.get(item_id)
        if f is None or f.proveedor != 'microsoft':
            return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
        if not accion and request.method == 'GET':
            return self._resp(request, 200, self._meta_graph(f))
        if accion == 'children' and request.method == 'GET':
            hijos = sorted(self.hijos(f.id), key=lambda x: x.id)
            tam = int(q.get('$top') or 200)
            ini = int(q.get('$skiptoken') or 0)
            datos = {'value': [self._meta_graph(x) for x in hijos[ini:ini + tam]]}
            if ini + tam < len(hijos):
                host = 'malo.example.net' if self.next_link_ajeno else GRAPH
                datos['@odata.nextLink'] = (f'https://{host}/v1.0/me/drive/items/{f.id}/children?'
                                            + urlencode({'$top': tam, '$skiptoken': ini + tam}))
            return self._resp(request, 200, datos)
        if accion == 'invite' and request.method == 'POST':
            c = self._cuerpo_json(request)
            valor = []
            for r in c.get('recipients') or []:
                permiso = {'id': f'perm-{next(self._n)}', 'roles': list(c.get('roles') or []),
                           'invitation': {'email': r.get('email')}, 'requireSignIn': c.get('requireSignIn')}
                f.permisos.append(permiso)
                valor.append(permiso)
            return self._resp(request, 200, {'value': valor})
        if accion == 'createLink' and request.method == 'POST':
            c = self._cuerpo_json(request)
            permiso = {'id': f'perm-{next(self._n)}', 'roles': ['read'], 'link': {
                'scope': c.get('scope'), 'type': c.get('type'), 'webUrl': f'https://1drv.ms/x/{quote(f.id)}'}}
            f.permisos.append(permiso)
            return self._resp(request, 201, permiso)
        if accion == 'content' and request.method == 'GET':
            return self._resp(request, 302, contenido=b'', cabeceras={
                'Location': f'https://{self.host_descarga}/descarga/{f.id}'})
        return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})

    def _media_ms(self, request, ruta: str, q: dict):
        fid = ruta.rsplit('/', 1)[-1]
        f = self.ficheros.get(fid)
        if f is None:
            return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
        if not self.acceso and not self.refresco and 't' in q:
            return self._resp(request, 401, {'error': {'code': 'unauthenticated'}})
        return self._media(request, f, f.contenido)

    def _subida_ms(self, request, ruta: str):
        sid = ruta.rsplit('/', 1)[-1]
        sesion = self.sesiones.get(sid)
        if sesion is None:
            return self._resp(request, 404, {'error': {'code': 'itemNotFound'}})
        if request.method == 'GET':
            return self._resp(request, 200, {'nextExpectedRanges': [f"{len(sesion['datos'])}-"]})
        return self._trozo(request, sesion)


# --------------------------------------------------------------------------- web de prueba
CONFIG_PRUEBA = {
    'google': {'id_cliente': 'cliente-prueba.apps.googleusercontent.com',
               'uri_retorno': 'http://127.0.0.1:8765/nube/retorno'},
    'microsoft': {'id_cliente': '00000000-0000-0000-0000-000000000109', 'inquilino': 'common',
                  'uri_retorno': 'http://127.0.0.1:8765/nube/retorno'},
}


def cierres_de(app) -> dict:
    """Las funciones internas de ``create_app`` (``_assign``, ``_validar_entrada``, ``_reemplazar_carpeta``…).

    La spec 109 cablea el router con dos líneas en ``web/app.py`` (las pacta el integrador). Hasta entonces, la prueba
    lo monta sobre las MISMAS funciones de la web real, sacadas de los cierres de sus rutas: así lo importado de la
    nube recorre de verdad la validación y la asignación de una subida (109:RF-4), sin copiarlas.
    """
    vistos: dict = {}
    pendientes = [getattr(r, 'endpoint', None) for r in app.routes]
    while pendientes:
        f = pendientes.pop()
        codigo, celdas = getattr(f, '__code__', None), getattr(f, '__closure__', None)
        if codigo is None or not celdas:
            continue
        for nombre, celda in zip(codigo.co_freevars, celdas):
            try:
                valor = celda.cell_contents
            except ValueError:
                continue
            if nombre not in vistos:
                vistos[nombre] = valor
                if callable(valor) and hasattr(valor, '__code__'):
                    pendientes.append(valor)
    return vistos


@dataclass
class WebNube:
    """La web real (``real``) y, sobre sus mismas funciones, el router de la nube (``nube``)."""

    real: object
    nube: object
    sim: NubeSimulada
    cuentas: object
    store: object

    def espacio(self) -> str:
        r = self.real.post('/api/workspaces')
        assert r.status_code == 201, r.text
        return r.json()['id']

    def conectar(self, wid: str, proveedor: str, cuenta: str = 'operador@ejemplo.org', *, publicar: bool = False):
        url = self.nube.post(f'/api/workspaces/{wid}/nube/{proveedor}/conectar', json={'publicar': publicar})
        assert url.status_code == 200, url.text
        r = self.nube.get('/nube/retorno', params=self.sim.autorizar(url.json()['url'], cuenta),
                          follow_redirects=False)
        assert 'nube=conectada' in r.headers['location'], r.headers['location']

    def esperar(self, trabajo: dict, timeout: float = 60.0) -> dict:
        from apoyo import esperar_trabajo

        return esperar_trabajo(self.real, trabajo, timeout)


def montar_web_nube(tmp_path, sim: NubeSimulada | None = None, config: dict | None = None):
    """Context manager: la web real y el router de la nube sobre sus funciones, con el proveedor simulado."""
    from contextlib import contextmanager

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from convertersmartgrid.adaptadores.nube.cuentas import Cuentas
    from convertersmartgrid.presentacion.web.app import create_app
    from convertersmartgrid.presentacion.web.nube_api import registrar_rutas_nube

    @contextmanager
    def gestor():
        simulada = sim or NubeSimulada()
        ruta = tmp_path / 'config' / 'nube.json'
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(config or CONFIG_PRUEBA), encoding='utf-8')
        real_app = create_app(tmp_path / 'web')
        c = cierres_de(real_app)
        cuentas = Cuentas(config=ruta, cofre=tmp_path / 'cofre', adaptador=simulada, dormir=lambda _s: None)
        app = FastAPI()
        registrar_rutas_nube(app, ws_or_404=c['ws_or_404'], submit=c['submit'], asignar_entrada=c['_assign'],
                             validar_entrada=c['_validar_entrada'], reemplazar_libros=c['_reemplazar_carpeta'],
                             cuentas=cuentas)
        with TestClient(real_app) as real, TestClient(app) as nube:
            yield WebNube(real, nube, simulada, cuentas, c['store'])

    return gestor()
