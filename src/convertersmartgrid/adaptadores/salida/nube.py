"""La salida a la nube: paquete cerrado, publicación sin sobrescribir, permisos y recibos (109:RF-9 a RF-13, RF-20).

El ZIP lo arma la web con ``web/operaciones_lentas.preparar_zip`` (aquí no se puede importar la capa de
presentación); este módulo lo cierra: calcula el manifiesto (SHA-256 de cada entrada y del ZIP, que por eso va fuera
del ZIP) y lo guarda inmutable en ``<espacio>/nube/paquetes/<id>/``. El id sale del contenido (nombres y huellas de
las entradas), así que un reintento con las mismas salidas reutiliza el mismo ZIP, byte a byte, y su clave.

Idempotencia en dos niveles (RF-13): el recibo local por clave, ``sha256(zip) | proveedor | carpeta``, y la
comprobación remota (``appProperties.csg_clave`` en Google; en Graph, el nombre con la misma huella). Cubre el corte
entre la subida y el recibo: el reintento devuelve el recibo sin subir otra vez.

Compartir (RF-10, RF-11, RF-20): primero la previa, con quién tendrá acceso y una confirmación de un solo uso, ligada
al espacio, al paquete, a los destinatarios y a si hay enlace público; «cualquiera con el enlace» solo con
``autorizo_enlace_publico`` en ese envío; y nunca un paquete con datos crudos de la distribuidora (TXT de CYMDIST,
bases Access o paquetes VNR-GIS), reconocidos por su contenido aunque vayan renombrados.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ...identify import FUENTE_MDB, FUENTE_TXT, FUENTE_VNR, fuente_de
from ...util import publicar_duradero
from ..nube.proveedor import ErrorNube, ProveedorNube, YaExiste, huellas_de

MANIFIESTO = 'manifiesto.json'
PAQUETE = 'paquete.zip'
#: 5 min para confirmar lo que se vio en la previa.
CADUCIDAD_CONFIRMACION_S = 300
_CORREO = re.compile(r'^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$')
#: Formatos de las fuentes VNR-GIS dentro de un comprimido (spec 023), por si el paquete va renombrado.
_EXT_VNR = frozenset({'.shp', '.shx', '.dbf', '.gdb', '.gpkg', '.geojson', '.mdb', '.accdb', '.bak', '.sqlite', '.db'})
_FIRMAS_COMPRIMIDO = (b'PK\x03\x04', b'7z\xbc\xaf\x27\x1c', b'Rar!\x1a\x07')
#: Tope de lo que se lee de cada entrada para reconocerla.
_TOPE_EXAMEN = 512 * 1024 * 1024


class Rechazo(ErrorNube):
    causa = 'envío rechazado'


@dataclass(frozen=True)
class Paquete:
    id: str
    carpeta: Path
    zip: Path
    manifiesto: dict


# --------------------------------------------------------------------------- paquete
def _entradas(zip_path: Path) -> list[dict]:
    filas = []
    with zipfile.ZipFile(zip_path) as z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            sha = hashlib.sha256()
            with z.open(info) as fh:
                while bloque := fh.read(1024 * 1024):
                    sha.update(bloque)
            filas.append({'ruta': info.filename, 'tamano': info.file_size, 'sha256': sha.hexdigest()})
    return filas


def cerrar_paquete(zip_preparado: Path, raiz: Path, *, origen: str) -> Paquete:
    """El ZIP de ``preparar_zip`` con su manifiesto, guardado inmutable; uno ya cerrado con el mismo contenido, igual."""
    entradas = _entradas(zip_preparado)
    if not entradas:
        raise Rechazo('El expediente está vacío: no hay nada que publicar.')
    pid = hashlib.sha256(json.dumps(entradas, sort_keys=True).encode('utf-8')).hexdigest()
    carpeta = Path(raiz) / pid
    if (carpeta / MANIFIESTO).is_file() and (carpeta / PAQUETE).is_file():
        return Paquete(pid, carpeta, carpeta / PAQUETE, json.loads((carpeta / MANIFIESTO).read_text('utf-8')))
    carpeta.mkdir(parents=True, exist_ok=True)
    zip_final = carpeta / PAQUETE
    temporal = carpeta / f'.{PAQUETE}.{secrets.token_hex(4)}'
    shutil.copyfile(zip_preparado, temporal)
    os.replace(temporal, zip_final)
    huellas = huellas_de(zip_final)
    # Sin horas dentro: el manifiesto es el mismo en cada reintento, y su huella también (RF-13).
    manifiesto = {'version': 1, 'paquete': pid, 'origen': origen, 'zip': {'nombre': PAQUETE, **huellas,
                  'tamano': zip_final.stat().st_size}, 'entradas': entradas}
    publicar_duradero(carpeta / MANIFIESTO, json.dumps(manifiesto, ensure_ascii=False, indent=1, sort_keys=True))
    return Paquete(pid, carpeta, zip_final, manifiesto)


def leer_paquete(raiz: Path, pid: str) -> Paquete:
    if not re.fullmatch(r'[0-9a-f]{64}', pid or ''):
        raise Rechazo('Paquete no válido.')
    carpeta = Path(raiz) / pid
    try:
        manifiesto = json.loads((carpeta / MANIFIESTO).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Rechazo('Ese paquete no existe en este espacio.') from exc
    return Paquete(pid, carpeta, carpeta / PAQUETE, manifiesto)


def clave_de(sha256_zip: str, proveedor: str, carpeta_id: str) -> str:
    return hashlib.sha256(f'{sha256_zip}|{proveedor}|{carpeta_id}'.encode('utf-8')).hexdigest()


def _ahora() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


# --------------------------------------------------------------------------- publicar
def _subir_una(proveedor: ProveedorNube, carpeta_id: str, nombre: str, ruta: Path, clave: str) -> tuple[dict, bool]:
    huellas = huellas_de(ruta)
    hallado = proveedor.buscar_por_clave(carpeta_id, nombre, clave, huellas)
    if hallado is not None:
        return {'id': hallado.id, 'nombre': hallado.nombre}, False
    with ruta.open('rb') as fh:
        item = proveedor.subir(carpeta_id, nombre, fh, ruta.stat().st_size, clave=clave)
    return {'id': item.id, 'nombre': item.nombre}, True


def publicar(proveedor: ProveedorNube, paquete: Paquete, carpeta_id: str, recibos: Path, *, nombre: str,
             wid: str) -> dict:
    """109:RF-9, RF-12, RF-13: sube el ZIP y su manifiesto a la carpeta, sin pisar nada, y deja el recibo."""
    sha_zip = paquete.manifiesto['zip']['sha256']
    clave = clave_de(sha_zip, proveedor.nombre, carpeta_id)
    ruta_recibo = Path(recibos) / f'publicacion-{clave}.json'
    if ruta_recibo.is_file():
        return {**json.loads(ruta_recibo.read_text(encoding='utf-8')), 'reintento': True}
    base = re.sub(r'\.zip$', '', nombre_paquete(nombre), flags=re.I)
    manifiesto_local = paquete.carpeta / MANIFIESTO
    # Primero el ZIP: si su nombre ya existe, no se sube nada (ni el manifiesto suelto).
    remoto, subido = _subir_una(proveedor, carpeta_id, f'{base}.zip', paquete.zip, clave)
    remoto_m, subido_m = _subir_una(proveedor, carpeta_id, f'{base}.manifiesto.json', manifiesto_local, clave + '-m')
    recibo = {'version': 1, 'tipo': 'publicacion', 'clave': clave, 'espacio': wid, 'paquete': paquete.id,
              'sha256': sha_zip, 'proveedor': proveedor.nombre, 'destino': carpeta_id, 'destinatarios': [],
              'hora': _ahora(), 'id_remoto': remoto['id'], 'nombre_remoto': remoto['nombre'],
              'id_remoto_manifiesto': remoto_m['id'], 'subido_ahora': subido or subido_m}
    publicar_duradero(ruta_recibo, json.dumps(recibo, ensure_ascii=False, indent=1))
    return {**recibo, 'reintento': False}


def nombre_paquete(nombre: str) -> str:
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(nombre or '').strip()).strip(' .')
    if not limpio:
        raise Rechazo('Ponga un nombre al expediente.')
    return limpio[:120]


def recibos(raiz: Path) -> list[dict]:
    filas = []
    for ruta in sorted(Path(raiz).glob('*.json')):
        try:
            filas.append(json.loads(ruta.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            continue
    return sorted(filas, key=lambda r: r.get('hora', ''))


def recibo_de_publicacion(raiz: Path, clave: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{64}', clave or ''):
        raise Rechazo('Publicación no válida.')
    try:
        return json.loads((Path(raiz) / f'publicacion-{clave}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Rechazo('Esa publicación no tiene recibo en este espacio: publíquela antes de compartirla.') from exc


# --------------------------------------------------------------------------- datos crudos (RF-20)
def _es_crudo(ruta: Path, profundidad: int = 0) -> bool:
    fuente = fuente_de(ruta).fuente
    if fuente in (FUENTE_TXT, FUENTE_MDB, FUENTE_VNR):
        return True
    try:
        with ruta.open('rb') as fh:
            cabecera = fh.read(8)
    except OSError:
        return False
    if cabecera.startswith(b'TAPE'):                 # copia de SQL Server de VNR-GIS, sin extensión (spec 023)
        return True
    if not cabecera.startswith(_FIRMAS_COMPRIMIDO):
        return False
    if not cabecera.startswith(b'PK') or not zipfile.is_zipfile(ruta):
        return True                                  # 7z, RAR o un ZIP ilegible: como un paquete VNR, no se comparte
    with zipfile.ZipFile(ruta) as z:
        if '[Content_Types].xml' in z.namelist():
            return False                             # un .docx o .xlsx del informe (Office Open XML), no una fuente
    return bool(datos_crudos(ruta, profundidad + 1)) if profundidad < 2 else True


def datos_crudos(zip_path: Path, profundidad: int = 0) -> list[str]:
    """109:RF-20: las entradas del ZIP que son datos crudos de la distribuidora, por su contenido y no por su nombre."""
    halladas = []
    with zipfile.ZipFile(zip_path) as z, tempfile.TemporaryDirectory(prefix='csg-crudos-') as tmp:
        for info in z.infolist():
            if info.is_dir():
                continue
            if Path(info.filename).suffix.lower() in _EXT_VNR or '.gdb/' in info.filename.lower():
                halladas.append(info.filename)
                continue
            if info.file_size > _TOPE_EXAMEN:
                halladas.append(info.filename)       # no se pudo examinar: no se comparte a ciegas
                continue
            # Con su nombre de verdad, en una carpeta propia: el reconocimiento lee también la extensión.
            destino = Path(tmp) / f'{len(halladas)}-{secrets.token_hex(3)}' / Path(info.filename).name
            destino.parent.mkdir(parents=True)
            with z.open(info) as origen, destino.open('wb') as fh:
                shutil.copyfileobj(origen, fh)
            if _es_crudo(destino, profundidad):
                halladas.append(info.filename)
            destino.unlink(missing_ok=True)
    return halladas


# --------------------------------------------------------------------------- compartir
def destinatarios_validos(destinatarios: list[str]) -> list[str]:
    vistos, salida = set(), []
    for d in destinatarios or []:
        correo = str(d or '').strip()
        if not _CORREO.fullmatch(correo):
            raise Rechazo(f'«{correo}» no es un correo válido.')
        if correo.lower() not in vistos:
            vistos.add(correo.lower())
            salida.append(correo)
    return salida


@dataclass(frozen=True)
class _Confirmacion:
    wid: str
    tipo: str
    sujeto: str
    destinatarios: tuple[str, ...]
    publico: bool
    creada: float


@dataclass
class Confirmaciones:
    """Confirmaciones de un solo uso: lo que el operador vio en la previa es lo único que se puede enviar."""

    caducidad_s: float = CADUCIDAD_CONFIRMACION_S
    reloj: object = time.monotonic
    _pendientes: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def emitir(self, wid: str, tipo: str, sujeto: str, destinatarios: list[str] = (), publico: bool = False) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._pendientes[token] = _Confirmacion(wid, tipo, sujeto, tuple(sorted(d.lower() for d in destinatarios)),
                                                    publico, self.reloj())
        return token

    def consumir(self, token: str, wid: str, tipo: str, sujeto: str, destinatarios: list[str] = (),
                 publico: bool = False) -> None:
        with self._lock:
            c = self._pendientes.pop(token or '', None)
        if c is None:
            raise Rechazo('Falta la confirmación del operador, o ya se usó: vuelva a revisar el envío.')
        if self.reloj() - c.creada > self.caducidad_s:
            raise Rechazo('La confirmación caducó: vuelva a revisar el envío.')
        if (c.wid, c.tipo, c.sujeto, c.destinatarios, c.publico) != (
                wid, tipo, sujeto, tuple(sorted(d.lower() for d in destinatarios)), publico):
            raise Rechazo('Lo que se envía no es lo que se confirmó: vuelva a revisar el envío.')


def previa_compartir(paquete: Paquete, recibo: dict, destinatarios: list[str], publico: bool) -> dict:
    """109:RF-10, RF-11, RF-20: quién tendrá acceso, y lo que impide compartir, antes de confirmar nada."""
    lista = destinatarios_validos(destinatarios)
    if not lista and not publico:
        raise Rechazo('Nombre al menos un destinatario.')
    crudos = datos_crudos(paquete.zip)
    acceso = [{'destinatario': d, 'rol': 'lectura'} for d in lista]
    if publico:
        acceso.append({'destinatario': 'cualquiera con el enlace', 'rol': 'lectura'})
    return {'paquete': paquete.id, 'publicacion': recibo['clave'], 'nombre': recibo.get('nombre_remoto'),
            'proveedor': recibo['proveedor'], 'acceso': acceso, 'destinatarios': lista, 'publico': publico,
            'aviso_publico': ('Cualquiera que tenga el enlace podrá verlo, sin iniciar sesión.' if publico else None),
            'bloqueo': crudos}


def compartir(proveedor: ProveedorNube, paquete: Paquete, recibo: dict, destinatarios: list[str], recibos_dir: Path,
              *, publico: bool, autorizo_enlace_publico: bool, wid: str) -> list[dict]:
    """109:RF-10 a RF-12, RF-20: solo lectura a los nombrados; un recibo por permiso."""
    lista = destinatarios_validos(destinatarios)
    if publico and not autorizo_enlace_publico:
        raise Rechazo('«Cualquiera con el enlace» necesita su autorización expresa en este envío.')
    crudos = datos_crudos(paquete.zip)
    if crudos:
        raise Rechazo('El expediente lleva datos crudos de la distribuidora y no se comparte: ' + ', '.join(crudos))
    concedidos = proveedor.conceder_lectura(recibo['id_remoto'], lista) if lista else []
    if publico:
        concedidos.append(proveedor.enlace_publico(recibo['id_remoto']))
    salida = []
    for permiso in concedidos:
        fila = {'version': 1, 'tipo': 'permiso', 'espacio': wid, 'paquete': paquete.id, 'publicacion': recibo['clave'],
                'proveedor': proveedor.nombre, 'destino': recibo['id_remoto'],
                'destinatarios': [permiso['destinatario']], 'rol': permiso['rol'], 'hora': _ahora(),
                'id_remoto': permiso['id_remoto'], 'enlace': permiso.get('enlace')}
        nombre = hashlib.sha256(f"{recibo['clave']}|{permiso['destinatario']}|{permiso['id_remoto']}".encode()
                                ).hexdigest()
        publicar_duradero(Path(recibos_dir) / f'permiso-{nombre}.json', json.dumps(fila, ensure_ascii=False, indent=1))
        salida.append(fila)
    return salida


__all__ = ['Confirmaciones', 'Paquete', 'Rechazo', 'YaExiste', 'cerrar_paquete', 'clave_de', 'compartir',
           'datos_crudos', 'leer_paquete', 'previa_compartir', 'publicar', 'recibo_de_publicacion', 'recibos']
