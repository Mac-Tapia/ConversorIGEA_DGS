"""Utilidades de E/S y de números compartidas por el motor y la web.

Estaban copiadas hasta en siete sitios (diagnóstico del 2026-10-07, B5): el hash de
fichero en cuatro, la escritura atómica de JSON en tres con formatos que ya divergían.
``tests/test_util.py`` falla si alguna vuelve a copiarse en ``src/convertersmartgrid``.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
import os
import tempfile
import uuid
from pathlib import Path
from types import ModuleType
from collections.abc import Callable, Iterable, Mapping
from typing import Any


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sincronizar_carpeta(carpeta: Path | str) -> None:
    """Hace duradero un ``replace`` en POSIX; Windows no deja abrir una carpeta para sincronizarla."""
    if os.name == 'nt':
        return
    descriptor = os.open(carpeta, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publicar_duradero(path: Path | str, contenido: str | bytes) -> None:
    """Escribe en un temporal, lo sincroniza y solo entonces sustituye el fichero (086:RF-1).

    ``replace`` sin ``fsync`` es atómico frente a un proceso que muere, pero no frente a un corte
    de luz: el sistema puede grabar el cambio de nombre antes que los datos, y deja un
    ``workspace.json`` vacío donde había uno bueno.
    """
    from .runtime_paths import staging_publicacion

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(path) as temporary:
        if isinstance(contenido, str):
            temporary.write_text(contenido, encoding='utf-8')
        else:
            temporary.write_bytes(contenido)
        with temporary.open('rb+') as escrito:
            os.fsync(escrito.fileno())
        _sustituir(temporary, path)
    sincronizar_carpeta(path.parent)


#: Esperas antes de cada reintento de ``replace`` (086:RF-54): en total, menos de dos segundos.
ESPERAS_SUSTITUIR_S = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8)


def _sustituir(temporal: Path, destino: Path) -> None:
    """``replace`` con reintentos ante un bloqueo pasajero de Windows (086:RF-54).

    En Windows, ``replace`` falla con ``PermissionError`` (WinError 5 o 32) si otro proceso tiene abierto el destino en
    ese instante, como el antivirus que lee cada JSON nuevo. Con la suite completa en marcha (2026-11-10) un trabajo de la
    web no llegó a encolarse una vez de 8 613 pruebas, y corrida suelta pasaba. Pasado el último intento, el error sube.
    """
    import time

    for espera in (*ESPERAS_SUSTITUIR_S, None):
        try:
            temporal.replace(destino)
            return
        except PermissionError:
            if espera is None or os.name != 'nt':
                raise
            time.sleep(espera)


def ruta_copia_anterior(path: Path | str) -> Path:
    """Dónde queda la versión anterior de un fichero de estado: ``workspace.json.bak``."""
    path = Path(path)
    return path.with_name(path.name + '.bak')


def _guardar_copia_anterior(path: Path) -> None:
    """Conserva la versión buena: un fichero ya dañado nunca pisa la copia que lo puede arreglar."""
    try:
        actual = path.read_bytes()
    except FileNotFoundError:
        return
    try:
        json.loads(actual)
    except ValueError:
        return
    publicar_duradero(ruta_copia_anterior(path), actual)


def write_json_atomic(path: Path, payload: Any, *, copia: bool = False) -> None:
    """Prepara fuera del checkout, sincroniza y publica en el mismo volumen con ``replace``.

    Se serializa antes de abrir el temporal, así que un error de serialización deja el
    fichero anterior intacto. ``default=str`` admite rutas y fechas en los manifiestos.
    Con ``copia``, la versión anterior queda en ``<nombre>.bak`` (086:RF-2).
    """
    contenido = json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n'
    path = Path(path)
    if copia:
        _guardar_copia_anterior(path)
    publicar_duradero(path, contenido)


def finite_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def importar_opcional(modulo: str, error: Exception) -> ModuleType:
    """Importa una dependencia opcional o lanza ``error``, que elige quien llama.

    Cada vía conserva su excepción (``DownloadError``, ``ArcGISError``…) porque sus
    llamadores la capturan por tipo; lo común es solo el intento de importar.
    """
    try:
        return importlib.import_module(modulo)
    except ImportError as exc:
        raise error from exc


def nombre_seguro(texto: str, *, maximo: int | None = None, defecto: str = 'GRUPO') -> str:
    """Nombre apto para fichero y para PowerFactory: letras, dígitos, ``-`` y ``_``."""
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in texto)
    return limpio[:maximo] or defecto


#: Prefijo de los esquemas guardados antes del cambio de nombre (058:RF-6, RF-9).
PREFIJO_ESQUEMA_ANTERIOR = 'igea-dgs-'  # legado-058

#: Lo que el sistema dejó dentro de los proyectos de DIgSILENT con el nombre anterior, que no se
#: renombra (058:RF-9): nombre de hoy → el de antes. El 2026-11-01, la optimización de NA203 +
#: NA205 no encontraba su «Con proyecto» ni la biblioteca de tipos de sus obras.
NOMBRES_ANTERIORES_PF = {
    'CSG_Biblioteca_tipos': 'IGEA_Biblioteca_tipos',  # legado-058
    'CSG_confiabilidad': 'IGEA_confiabilidad',  # legado-058
}


def esquema_vigente(valor: object) -> object:
    """El esquema de un fichero guardado, con el nombre de hoy (058:RF-6).

    El 2026-11-01, tras el cambio de nombre, la importación de un alimentador VNR-GIS falló con
    «vinculos_pf.json no tiene el esquema esperado»: el registro compartido y los vínculos de
    cada espacio, escritos antes, llevaban el prefijo anterior. Se lee cualquiera de los dos y
    se escribe siempre el nuevo; lo guardado no se reescribe, para que sus huellas sigan valiendo.
    """
    if isinstance(valor, str) and valor.startswith(PREFIJO_ESQUEMA_ANTERIOR):
        return 'convertersmartgrid-' + valor[len(PREFIJO_ESQUEMA_ANTERIOR):]
    return valor


def _texto_csv(v: Any) -> str:
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'sí' if v else 'no'
    if isinstance(v, float):
        return f'{v:.4f}'
    return str(v)


def escribir_csv(filas: Iterable[Mapping[str, Any]], columnas: tuple[str, ...], destino: Path) -> Path:
    """CSV con «;» y BOM, como las plantillas de cargas: Excel en español lo abre bien.

    Los decimales van con cuatro cifras fijas: así dos ejecuciones con las mismas medidas
    dan el mismo fichero byte a byte.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(columnas)
        for f in filas:
            w.writerow([_texto_csv(f.get(c)) for c in columnas])
    return destino


# --- Cerrojos de fichero (019:RF-4, 106:RF-2) -------------------------------------------------------

#: Cuánto se respeta un cerrojo ilegible antes de darlo por muerto (019:RF-4, 106:RF-2).
#:
#: Solo hace falta para los cerrojos con estado a medias: los del método antiguo (``os.open(O_EXCL)`` y después
#: ``json.dump``) y los del camino de respaldo de :func:`crear_exclusivo` en un volumen sin enlaces duros. La vía
#: ``os.link`` no la necesita: el nombre aparece con el contenido ya entero y sincronizado, nunca a medias.
#:
#: Medido en esta máquina el 2026-11-14, con la suite completa en marcha: entre ``os.open(O_EXCL)`` y el cierre
#: tras ``json.dump``, el BloqueoGPU antiguo (que importaba psutil dentro) tardó como máximo 29 ms en 8 procesos
#: nuevos; el turno antiguo de DIgSILENT (inicio del proceso y carpeta del código dentro), 77 ms; el respaldo nuevo,
#: con el contenido ya serializado y ``fsync``, 5,7 ms en 500 vueltas. 10 s deja más de cien veces de margen para
#: un equipo cargado o un antivirus que retenga el fichero.
GRACIA_CERROJO_S = 10.0


#: Cuántas vueltas sin esperar (el cerrojo cambió entretanto, otro se llevó el apartado) admite quien toma un
#: cerrojo antes de rendirse con :func:`describir_cerrojo`: ningún bucle de toma es sin fin (019:RF-4, 106:RF-2).
TOPE_INTENTOS_CERROJO = 50


def describir_cerrojo(ruta: Path | str, ahora: Callable[[], float] | None = None) -> str:
    """Quién tiene el cerrojo, para el error de quien se rinde: su contenido o «ilegible desde hace N s»."""
    import time

    estado, valor = leer_cerrojo(ruta)
    if estado == 'legible':
        return json.dumps(valor, ensure_ascii=False, default=str)[:300]
    if estado == 'ausente':
        return 'nadie: el cerrojo ya no está'
    visto = identidad_fichero(ruta)
    edad = f'desde hace {(ahora or time.time)() - visto[2] / 1e9:.0f} s' if visto else 'y ya no está'
    return f'{"ilegible" if estado == "ilegible" else "no se deja leer"} {edad}'


def identidad_fichero(ruta: Path | str) -> tuple[int, int, int] | None:
    """``(st_ino, st_size, st_mtime_ns)`` del fichero, o ``None`` si no existe; en NTFS ``st_ino`` es su índice."""
    try:
        st = os.stat(ruta)
    except FileNotFoundError:
        return None
    return st.st_ino, st.st_size, st.st_mtime_ns


def leer_cerrojo(ruta: Path | str) -> tuple[str, Any]:
    """``('legible', valor)``, ``('ilegible', None)``, ``('sin_acceso', None)`` o ``('ausente', None)``.

    Un fichero que no se deja abrir (otro lo está sustituyendo en Windows) no es ilegible: solo se espera.
    """
    try:
        crudo = Path(ruta).read_bytes()
    except FileNotFoundError:
        return 'ausente', None
    except OSError:
        return 'sin_acceso', None
    try:
        return 'legible', json.loads(crudo)
    except ValueError:
        return 'ilegible', None


def crear_exclusivo(ruta: Path | str, contenido: str | bytes) -> bool:
    """Crea ``ruta`` con ``contenido`` ya entero solo si no existe; ``False`` si ya existía (019:RF-4, 106:RF-2).

    El contenido va primero a un temporal del mismo directorio, se sincroniza y se enlaza con ``os.link``, que falla
    si el nombre ya existe: es una creación exclusiva sin estado a medias. Si el volumen no admite enlaces duros
    (una unidad de Drive, FAT), se recurre a ``os.open(O_EXCL)``, que sí tiene un instante a medias: lo cubre
    :data:`GRACIA_CERROJO_S`.
    """
    ruta = Path(ruta)
    datos = contenido.encode('utf-8') if isinstance(contenido, str) else contenido
    fd, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=f'.{ruta.name}.', suffix='.nuevo')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temporal, ruta)
            return True
        except FileExistsError:
            return False
        except OSError:
            pass                                # sin enlaces duros en este volumen: el respaldo
    finally:
        try:
            os.unlink(temporal)
        except FileNotFoundError:
            pass
    try:
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
        return False
    with os.fdopen(fd, 'wb') as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())
    return True


def _devolver_cerrojo(muerto: Path, ruta: Path) -> bool:
    """``False`` solo si otro ocupó el nombre antes de devolverlo; uno que ya no está lo devuelve quien lo tenga."""
    try:
        os.link(muerto, ruta)
        return True
    except FileExistsError:
        return False
    except FileNotFoundError:
        return True
    except OSError:
        try:
            return crear_exclusivo(ruta, muerto.read_bytes())
        except FileNotFoundError:
            return True


def apartar_cerrojo(ruta: Path | str, visto: tuple[int, int, int], aviso: Callable[[str], None]) -> Path | None:
    """Aparta el cerrojo ``ruta`` si sigue siendo el observado ``visto``; devuelve dónde quedó o ``None``.

    Solo lo libera quien lo renombra: un segundo proceso recibe ``FileNotFoundError`` y vuelve a empezar. Si entre la
    observación y el renombrado otro ya lo había sustituido por uno nuevo, se ha apartado uno vivo: se devuelve con
    ``os.link`` y, si alguien entró entretanto, se dice con un aviso fuerte. Quien llama borra el apartado.

    En Windows, ``os.replace`` renombra por el descriptor que abrió antes: dos renombrados simultáneos pueden «salir
    bien» los dos y el segundo se lleva el apartado del primero (medido con dos hilos el 2026-11-14). Por eso, si el
    apartado ya no está, se lo llevó otro y se vuelve a empezar; y aunque dos crean tenerlo, solo uno entra, porque
    el cerrojo nuevo se crea con :func:`crear_exclusivo`.
    """
    ruta = Path(ruta)
    muerto = ruta.with_name(f'{ruta.name}.muerto-{os.getpid()}-{uuid.uuid4().hex}')
    try:
        os.replace(ruta, muerto)
    except (FileNotFoundError, PermissionError):
        return None                             # otro lo apartó o lo tiene abierto: se vuelve a mirar
    actual = identidad_fichero(muerto)
    if actual is None:
        return None                             # otro renombrado simultáneo se lo llevó: él decide
    if actual == visto:
        return muerto
    try:
        if not _devolver_cerrojo(muerto, ruta):
            aviso(f'AVISO GRAVE: se apartó por error el cerrojo vivo {ruta.name} y otro proceso entró antes de '
                  'devolverlo: puede haber dos dueños; compruebe los procesos que usan el recurso.')
    finally:
        muerto.unlink(missing_ok=True)
    return None


def intentar_cerrojo(ruta: Path | str, contenido: str | bytes, *, valido: Callable[[Any], bool],
                     aviso: Callable[[str], None], gracia_s: float = GRACIA_CERROJO_S,
                     ahora: Callable[[], float] | None = None) -> tuple[str, Any]:
    """Un intento de tomar el cerrojo ``ruta`` (019:RF-4, 106:RF-2).

    Devuelve ``('tomado', None)``; ``('ocupado', dueño)`` con un dueño legible, que decide quien llama (vivo, muerto,
    cerrándose); ``('espera', motivo)`` con uno ilegible de menos de ``gracia_s`` o que no se deja leer; o
    ``('otra_vez', None)`` si cambió entretanto. Uno ilegible más antiguo se libera con aviso y se toma.
    """
    import time

    ruta = Path(ruta)
    if crear_exclusivo(ruta, contenido):
        return 'tomado', None
    visto = identidad_fichero(ruta)
    if visto is None:
        return 'otra_vez', None
    estado, valor = leer_cerrojo(ruta)
    if estado == 'ausente':
        return 'otra_vez', None
    if estado == 'sin_acceso':
        return 'espera', f'{ruta.name} no se deja leer'
    if estado == 'legible' and valido(valor):
        return 'ocupado', valor
    edad = (ahora or time.time)() - visto[2] / 1e9
    if edad < gracia_s:
        return 'espera', f'cerrojo ilegible de hace {max(edad, 0):.0f} s: puede estar escribiéndose'
    muerto = apartar_cerrojo(ruta, visto, aviso)
    if muerto is None:
        return 'otra_vez', None
    try:
        tomado = crear_exclusivo(ruta, contenido)
        try:
            previo = muerto.read_bytes()[:120].decode('utf-8', 'replace')
        except OSError:
            previo = '?'                        # se lo llevó otro renombrado simultáneo
        aviso(f'Cerrojo ilegible de hace {edad:.0f} s: se libera ({ruta.name}, contenía {previo!r}).')
    finally:
        muerto.unlink(missing_ok=True)
    return ('tomado', None) if tomado else ('otra_vez', None)
