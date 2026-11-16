"""El único transporte HTTP hacia la nube (109:RF-6, RF-16, RF-17).

Es el único fichero del paquete con una sesión de ``requests``. Así RF-16 se demuestra en un solo sitio, como en
``asistente/ejecutor.py``:

- ``trust_env=False``: el proxy y los certificados del entorno no se leen por su cuenta;
- ``allow_redirects=False``: una redirección a otro host es ``HostNoPermitido`` y no se sigue; una a un host del
  proveedor tampoco se sigue sola, porque cada API dice qué URL toca pedir;
- cada URL se compara con la lista del proveedor antes de pedirla, también las que llegan en una respuesta
  (``@odata.nextLink``, ``@microsoft.graph.downloadUrl`` o la URL de una sesión de subida);
- solo se reintentan el 429 y los 5xx, esperando el ``Retry-After`` con un tope, y la espera es inyectable;
- antes de cada petición se mira si la salida ``nube`` está encendida (086:RF-22).

El 308 de una subida reanudable de Google no trae ``Location``: no es una redirección, es «sigue subiendo».
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, BinaryIO
from urllib.parse import urlsplit

import requests
from requests.adapters import BaseAdapter

from ...salidas_red import SalidaApagada, motivo_apagada, salida_permitida
from .proveedor import (DemasiadoGrande, DescargaCortada, ErrorNube, HostNoPermitido, Limitado, NoEncontrado,
                        PermisoCaducado, SinAcceso, SinConexion, YaExiste)

#: 16 GiB, como la cuota de subida de la web (``CSG_UPLOAD_MAX_BYTES``).
TOPE_POR_DEFECTO = 16 * 1024 ** 3
VARIABLE_TOPE = 'CSG_NUBE_MAX_BYTES'
TIEMPO_ESPERA_S = (10.0, 120.0)


def tope_de_bytes(environ: Mapping[str, str] | None = None) -> int:
    """El tope de una descarga; un valor inválido no lo desactiva en silencio."""
    env = os.environ if environ is None else environ
    texto = str(env.get(VARIABLE_TOPE) or TOPE_POR_DEFECTO)
    try:
        valor = int(texto)
    except ValueError as exc:
        raise ValueError(f'{VARIABLE_TOPE} debe ser un entero positivo en bytes.') from exc
    if valor <= 0:
        raise ValueError(f'{VARIABLE_TOPE} debe ser un entero positivo en bytes.')
    return valor


@dataclass(frozen=True)
class Hosts:
    """Los hosts de un proveedor: exactos y por sufijo (``.sharepoint.com``), siempre con HTTPS."""

    exactos: frozenset[str]
    sufijos: tuple[str, ...] = ()

    def admite(self, host: str) -> bool:
        host = (host or '').lower().rstrip('.')
        return host in self.exactos or any(host.endswith(s) and len(host) > len(s) for s in self.sufijos)


def _salida_nube() -> bool:
    return salida_permitida('nube')


class Transporte:
    """Una sesión por cuenta conectada; ``autorizacion(renovar)`` da el token de acceso vigente."""

    def __init__(self, hosts: Hosts, *, autorizacion: Callable[[bool], str] | None = None,
                 adaptador: BaseAdapter | None = None, dormir: Callable[[float], None] = time.sleep,
                 reintentos: int = 3, espera_max_s: float = 60.0, permitida: Callable[[], bool] | None = None,
                 environ: Mapping[str, str] | None = None) -> None:
        self.hosts = hosts
        self._autorizacion = autorizacion
        self._dormir = dormir
        self._reintentos = reintentos
        self._espera_max_s = espera_max_s
        self._permitida = permitida or _salida_nube
        self._environ = environ
        self.sesion = requests.Session()
        self.sesion.trust_env = False
        self.sesion.max_redirects = 0
        if adaptador is not None:
            # Las pruebas montan el proveedor simulado; nunca hay otro adaptador en producción.
            self.sesion.mount('https://', adaptador)
            self.sesion.mount('http://', adaptador)

    # ------------------------------------------------------------------ hosts
    def comprobar(self, url: str) -> str:
        """109:RF-16: solo HTTPS y solo los hosts del proveedor; si no, ``HostNoPermitido`` con el host."""
        partes = urlsplit(url)
        if partes.scheme != 'https' or not self.hosts.admite(partes.hostname or ''):
            raise HostNoPermitido(f'La nube respondió con una dirección de otro sitio ({partes.hostname or url!r}); '
                                  'no se sigue.')
        return url

    def _cabeceras(self, cabeceras: Mapping[str, str] | None, autenticar: bool, renovar: bool) -> dict[str, str]:
        salida = dict(cabeceras or {})
        if autenticar and self._autorizacion is not None:
            salida['Authorization'] = f'Bearer {self._autorizacion(renovar)}'
        return salida

    # ------------------------------------------------------------------ peticiones
    def pedir(self, metodo: str, url: str, *, cabeceras: Mapping[str, str] | None = None, autenticar: bool = True,
              aceptar: tuple[int, ...] = (), stream: bool = False, **kw: Any) -> requests.Response:
        """Una petición con la política de RF-16; ``aceptar`` son estados que no son error (el 308 de Google)."""
        renovado = False
        intento = 0
        while True:
            if not self._permitida():
                raise SalidaApagada(motivo_apagada('nube'))
            self.comprobar(url)
            try:
                r = self.sesion.request(metodo, url, headers=self._cabeceras(cabeceras, autenticar, renovado),
                                        allow_redirects=False, timeout=TIEMPO_ESPERA_S, stream=stream, **kw)
            except requests.TooManyRedirects as exc:
                # Con ``max_redirects = 0``, ``requests`` lanza esto ante cualquier 3xx con ``Location`` aunque no la
                # siga; la respuesta viene dentro y se juzga abajo, sin pedir el destino.
                r = exc.response
                if r is None:
                    raise ErrorNube('La nube respondió con una redirección; no se sigue.') from exc
            except (requests.ConnectionError, requests.Timeout) as exc:
                raise SinConexion(f'No se pudo hablar con la nube: {type(exc).__name__}.') from exc
            estado = r.status_code
            if estado in aceptar or 200 <= estado < 300:
                return r
            if 300 <= estado < 400:
                destino = r.headers.get('Location')
                if not destino:
                    return r
                host = urlsplit(destino).hostname or destino
                r.close()
                if not self.hosts.admite(host):
                    raise HostNoPermitido(f'La nube quiso redirigir a {host}, que no es del proveedor; no se sigue.')
                raise ErrorNube(f'La nube respondió con una redirección inesperada ({estado}); no se sigue.')
            if estado == 401 and autenticar and self._autorizacion is not None and not renovado:
                r.close()
                renovado = True
                continue
            if estado == 429 or estado >= 500:
                if intento >= self._reintentos:
                    r.close()
                    raise Limitado(f'La nube sigue respondiendo {estado} tras {intento} reintentos; '
                                   'inténtelo más tarde.')
                espera = self._espera(r.headers.get('Retry-After'), intento)
                r.close()
                intento += 1
                self._dormir(espera)
                continue
            raise self._error(r)

    def _espera(self, retry_after: str | None, intento: int) -> float:
        try:
            espera = float(retry_after) if retry_after is not None else 2.0 ** intento
        except ValueError:
            espera = 2.0 ** intento
        return max(0.0, min(espera, self._espera_max_s))

    @staticmethod
    def _detalle(r: requests.Response) -> str:
        try:
            datos = r.json()
        except ValueError:
            return ''
        error = datos.get('error') if isinstance(datos, dict) else None
        if isinstance(error, dict):
            return str(error.get('code') or error.get('message') or error.get('status') or '')
        return str(error or '')

    def _error(self, r: requests.Response) -> ErrorNube:
        detalle = self._detalle(r)
        r.close()
        texto = f' ({detalle})' if detalle else ''
        if r.status_code in (400, 401) and detalle in ('invalid_grant', 'invalid_token') or r.status_code == 401:
            return PermisoCaducado(f'El permiso de la cuenta caducó o se revocó{texto}: vuelva a conectarla.')
        if r.status_code == 403:
            return SinAcceso(f'La cuenta no tiene permiso para esto{texto}.')
        if r.status_code == 404:
            return NoEncontrado(f'El fichero ya no está en la nube{texto}.')
        if r.status_code == 409:
            return YaExiste(f'Ya hay un fichero con ese nombre{texto}; no se pisa.')
        return ErrorNube(f'La nube respondió {r.status_code}{texto}.')

    def json(self, metodo: str, url: str, **kw: Any) -> dict:
        r = self.pedir(metodo, url, **kw)
        try:
            return r.json() if r.content else {}
        except ValueError as exc:
            raise ErrorNube('La nube devolvió una respuesta que no es JSON.') from exc

    def bajar(self, url: str, destino: BinaryIO, *, cabeceras: Mapping[str, str] | None = None,
              autenticar: bool = True, tope: int | None = None, ya: int = 0) -> int:
        """Copia el cuerpo en ``destino`` por bloques, con el tope; un corte es ``DescargaCortada`` (109:RF-6)."""
        limite = tope if tope is not None else tope_de_bytes(self._environ)
        r = self.pedir('GET', url, cabeceras=cabeceras, autenticar=autenticar, stream=True)
        if ya and r.status_code != 206:
            # Pidió reanudar y el servidor mandó el fichero entero: añadirlo duplicaría lo ya escrito.
            r.close()
            raise DescargaCortada(f'La nube no reanudó la descarga desde el byte {ya}.')
        escritos = 0
        try:
            for bloque in r.iter_content(chunk_size=1024 * 1024):
                if not bloque:
                    continue
                escritos += len(bloque)
                if ya + escritos > limite:
                    raise DemasiadoGrande(f'El fichero supera el tope de {limite} bytes ({VARIABLE_TOPE}).')
                destino.write(bloque)
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, OSError) as exc:
            raise DescargaCortada(f'La descarga se cortó tras {ya + escritos} bytes.') from exc
        finally:
            r.close()
        return escritos

    def cerrar(self) -> None:
        self.sesion.close()
