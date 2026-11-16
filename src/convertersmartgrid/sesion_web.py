"""El token de la sesión de la web: lo crea el lanzador y lo leen los clientes locales (086:RF-19).

Una página cualquiera del navegador podía llamar a la API en 127.0.0.1: la revisión de la spec
086 lo vio en cada ruta. Con un puesto local por licencia (D2) no hacen falta usuarios, sino
un secreto por arranque que solo tenga quien ya es este usuario en esta máquina.

Va en un fichero por puerto, en la carpeta local del usuario y no en la raíz de datos: la raíz
cambia con cada worktree, y un lanzador tiene que poder hablar con la web de otra carpeta que
ocupe el puerto para no tumbarla (081:RF-44); además los datos pueden estar en una unidad con
permisos para todos. Solo la librería estándar: este módulo lo importan guiones y herramientas.
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

VARIABLE_CARPETA = 'CSG_WEB_SESIONES'
#: El puerto de este servidor: ``create_app`` corre con ``factory=True`` y no recibe argumentos.
VARIABLE_PUERTO = 'CSG_WEB_PUERTO'
CABECERA_TOKEN = 'X-CSG-Token'
#: El parámetro con el que el lanzador abre la primera página (lo cambia por una cookie).
PARAMETRO_ACCESO = 'acceso'
HOSTS_LOCALES = frozenset({'127.0.0.1', 'localhost', '::1'})

#: Las pruebas crean la aplicación a cientos con su cliente de pruebas; ``tests/conftest.py`` lo
#: apaga y las de seguridad lo encienden. No es una variable de entorno a propósito: nada de
#: fuera de este proceso puede abrir la web.
EXIGIR_SEGURIDAD = True

#: Lo que vale una credencial tras su nombre: ``acceso=``, ``token: ``, ``"password": "…"``, la cabecera propia
#: o ``Authorization``. ``acceso`` solo con ``=``: es el parámetro del lanzador, y «acceso:» es castellano corriente.
_NOMBRES_DE_SECRETO = (r'access_token|api[_-]?key|apikey|client_secret|secret|token|password|passwd|pwd'
                       r'|contraseña|contrasena|authorization')
_COMILLAS = '"\''
_SECRETO_CON_NOMBRE = re.compile(
    r'(?i)(\b' + PARAMETRO_ACCESO + r'=|(?:\b(?:' + _NOMBRES_DE_SECRETO + r')\b|' + re.escape(CABECERA_TOKEN) + ')'
    + '[' + _COMILLAS + r']?\s*[:=]\s*[' + _COMILLAS + ']?)'
    + r'(?!(?:bearer|basic)\s)[^\s&,;)' + _COMILLAS + ']+')
#: El valor de un ``Bearer`` o ``Basic`` aunque no lleve delante el nombre de la cabecera.
_SECRETO_DE_ESQUEMA = re.compile(r'(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{4,}')


def depurar_secretos(texto: str) -> str:
    """``texto`` con el valor de cada credencial cambiado por ``***`` (086:RF-19); el resto, igual."""
    if not isinstance(texto, str) or not texto:
        return texto
    return _SECRETO_CON_NOMBRE.sub(r'\1***', _SECRETO_DE_ESQUEMA.sub(r'\1 ***', texto))


class FiltroSecretos(logging.Filter):
    """Ningún registro guarda una credencial, venga en el mensaje o en sus argumentos (086:RF-19).

    El de antes iba solo en ``uvicorn.access`` y solo miraba ``args``: el asistente escribía la orden entera en el
    mensaje, con el token si el operador lo pegaba (auditoría b4, H8). Los argumentos se depuran uno a uno, porque
    el formateador de accesos de uvicorn los lee por posición; si el secreto aún aparece al unirlos (``'%s: %s'``
    con la cabecera y su valor), el mensaje queda ya formado y depurado.
    """

    #: Lo que se escribe en lugar de un registro que no se pudo depurar: falla cerrado, nunca deja pasar el crudo.
    SUSTITUTO = 'registro omitido: no se pudo depurar de credenciales (086:RF-19)'

    def __init__(self, name: str = '') -> None:
        super().__init__(name)
        #: Registros sustituidos porque la depuración falló; los revisa quien diagnostica el registro.
        self.fallos = 0

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            self._depurar(record)
        except Exception:  # noqa: BLE001 - falla cerrado: ningún error de la depuración deja salir el registro crudo
            self.fallos += 1
            record.msg, record.args = self.SUSTITUTO, ()
            record.exc_info = record.exc_text = record.stack_info = None
        return True

    @staticmethod
    def _depurar(record: logging.LogRecord) -> None:
        if isinstance(record.args, tuple):
            record.args = tuple(depurar_secretos(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: depurar_secretos(v) if isinstance(v, str) else v for k, v in record.args.items()}
        try:
            completo = record.getMessage()
        except (TypeError, ValueError, KeyError):
            # Un mensaje que no casa con sus argumentos: logging lo imprimiría crudo en handleError. Sale el mensaje
            # depurado, sin los argumentos, y dice por qué.
            record.msg = depurar_secretos(str(record.msg)) + ' (argumentos omitidos: no casaban con el mensaje)'
            record.args = ()
            return
        limpio = depurar_secretos(completo)
        if limpio != completo:
            record.msg, record.args = limpio, ()


@dataclass(frozen=True)
class Sesion:
    token: str
    #: El del arranque anterior, para que una pestaña abierta se reconecte (001:RF-35).
    anterior: str | None = None
    puerto: int | None = None
    #: Lo que había en el fichero: se devuelve si este arranque no llega a escuchar.
    previo: str | None = None


def carpeta_sesiones() -> Path:
    env = os.environ.get(VARIABLE_CARPETA, '').strip()
    if env:
        return Path(env)
    local = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    return Path(local) / 'convertersmartgrid' / 'sesiones_web'


def ruta_sesion(puerto: int) -> Path:
    return carpeta_sesiones() / f'{int(puerto)}.json'


def _solo_este_usuario(ruta: Path) -> None:
    """En Windows ``chmod`` no restringe nada: los permisos se quitan con ``icacls``."""
    if os.name != 'nt':
        os.chmod(ruta, 0o600)
        return
    try:
        subprocess.run(['icacls', str(ruta), '/inheritance:r', '/grant:r', f'{getpass.getuser()}:F'],
                       capture_output=True, timeout=15, check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError) as exc:
        # No impide abrir la web: queda con los permisos de la carpeta local del usuario, y se dice.
        print(f'AVISO: no se pudieron restringir los permisos de {ruta}: {exc}', file=sys.stderr)


def _escribir(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix='.sesion-')
    os.close(fd)
    try:
        # Los permisos antes que el secreto: el fichero nunca tiene token y permisos abiertos.
        _solo_este_usuario(Path(temporal))
        Path(temporal).write_text(contenido, encoding='utf-8')
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def crear_sesion(puerto: int) -> Sesion:
    """El token de este arranque, que sustituye al anterior en el fichero del puerto."""
    ruta = ruta_sesion(puerto)
    try:
        previo = ruta.read_text(encoding='utf-8')
        anterior = json.loads(previo).get('token')
    except (OSError, ValueError, AttributeError):
        previo, anterior = None, None
    sesion = Sesion(secrets.token_urlsafe(32), anterior if isinstance(anterior, str) else None, int(puerto), previo)
    _escribir(ruta, json.dumps({'token': sesion.token, 'anterior': sesion.anterior,
                                'pid': os.getpid()}, ensure_ascii=False))
    return sesion


def devolver_sesion(sesion: Sesion) -> None:
    """Este arranque no llegó a escuchar: el fichero vuelve a ser del servidor que sí escucha."""
    if sesion.puerto is not None and sesion.previo is not None:
        _escribir(ruta_sesion(sesion.puerto), sesion.previo)


def leer_sesion(puerto: int) -> Sesion | None:
    try:
        datos = json.loads(ruta_sesion(puerto).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    token = datos.get('token') if isinstance(datos, dict) else None
    if not isinstance(token, str) or not token:
        return None
    anterior = datos.get('anterior')
    return Sesion(token, anterior if isinstance(anterior, str) else None, int(puerto))


def _puerto_local(url: str) -> int | None:
    """El puerto de una dirección de esta máquina; None si es de otra: allí el token no va nunca."""
    partes = urlsplit(url)
    if (partes.hostname or '').lower() not in HOSTS_LOCALES:
        return None
    return partes.port or (443 if partes.scheme == 'https' else 80)


def cabeceras_locales(url: str) -> dict[str, str]:
    """Lo que un cliente de esta máquina añade a sus peticiones a la web de ``url``.

    Un programa no manda ``Origin`` por su cuenta, y la web lo exige en todo lo que cambia algo.
    """
    puerto = _puerto_local(url)
    if puerto is None:
        return {}
    partes = urlsplit(url)
    cabeceras = {'Origin': f'{partes.scheme}://{partes.netloc}'}
    sesion = leer_sesion(puerto)
    if sesion is not None:
        cabeceras[CABECERA_TOKEN] = sesion.token
    return cabeceras


def url_de_entrada(url: str) -> str:
    """La dirección con la que el lanzador abre el navegador: la web la cambia por una cookie."""
    puerto = _puerto_local(url)
    sesion = leer_sesion(puerto) if puerto is not None else None
    if sesion is None:
        return url
    partes = urlsplit(url)
    consulta = parse_qsl(partes.query) + [(PARAMETRO_ACCESO, sesion.token)]
    return urlunsplit(partes._replace(query=urlencode(consulta)))
