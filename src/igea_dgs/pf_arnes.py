"""Arnés de DIgSILENT: un solo dueño del motor en la máquina y una conexión común (spec 019).

El motor de PowerFactory solo admite un proceso a la vez. El 2026-10-15, con CA101, una
sesión lanzaba guiones mientras otra tenía DIgSILENT y los suyos morían con «Exit with
error code 4002» sin esperar ni decir quién lo tenía; la web solo ponía en fila los
suyos. Aquí el turno es de la máquina: un fichero creado en exclusiva que dice qué
proceso, qué guion y desde cuándo (RF-1, RF-2), que se libera solo si su dueño murió
(RF-4); y una conexión que reintenta mientras el motor siga ocupado (RF-3) y escribe la
primera línea en cuanto DIgSILENT responde (RF-6, 005:RF-21).

    from igea_dgs.pf_arnes import conectar, PFNoDisponible
    app = conectar('ajuste_cabecera_pf.py')     # el turno se suelta al salir el proceso
"""

from __future__ import annotations

import atexit
import importlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

#: Espera máxima por el motor (usuario, 2026-10-15: «10 minutos es suficiente»).
ESPERA_S = 600.0
#: Cada cuánto se mira si el motor quedó libre y se reintenta la conexión.
PAUSA_S = 2.0
#: Cada cuánto se repite el aviso de espera.
AVISO_S = 30.0
#: Ruta del fichero de turno para las pruebas o para otra máquina.
VARIABLE_TURNO = 'IGEA_PF_TURNO'
#: Código de PowerFactory cuando otro proceso tiene el motor.
MOTOR_OCUPADO = '4002'


class PFNoDisponible(RuntimeError):
    """No se puede hablar con DIgSILENT: sin API, ocupado más del límite o abierto a mano."""


def ruta_turno() -> Path:
    """El fichero de turno de la máquina, común a la web, el CLI y otras sesiones."""
    if os.environ.get(VARIABLE_TURNO):
        return Path(os.environ[VARIABLE_TURNO])
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    return Path(base) / 'igea_dgs' / 'powerfactory.turno'


def pid_vivo(pid: int) -> bool:
    """Si el proceso ``pid`` sigue vivo, sin tocarlo.

    En Windows ``os.kill(pid, 0)`` no consulta: termina el proceso. Se pregunta su código
    de salida con la API de Windows.
    """
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        codigo = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(codigo))
        kernel.CloseHandle(handle)
        return bool(ok) and codigo.value == 259           # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def leer_turno(ruta: Path | None = None) -> dict | None:
    """Quién tiene el motor: ``{pid, guion, desde}``, o ``None`` si nadie."""
    try:
        return json.loads((ruta or ruta_turno()).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _abierto_a_mano() -> list[int]:
    from .powerfactory_env import powerfactory_abierto

    return powerfactory_abierto()


def tomar_turno(guion: str, *, espera_s: float = ESPERA_S,
                aviso: Callable[[str], None] = print,
                vivo: Callable[[int], bool] = pid_vivo,
                abierto: Callable[[], list[int]] = _abierto_a_mano,
                reloj: Callable[[], float] = time.monotonic,
                dormir: Callable[[float], None] = time.sleep) -> Path:
    """Toma el turno del motor para este proceso o lanza :class:`PFNoDisponible`.

    RF-13: con DIgSILENT abierto a mano no se lanza nada (usuario, 2026-10-15: «avisas»).
    RF-2: si otro proceso lo tiene, se espera hasta ``espera_s`` diciendo quién.
    RF-4: si su dueño ya no vive, se libera y se sigue.
    """
    manuales = abierto()
    if manuales:
        raise PFNoDisponible(
            f'DIgSILENT está abierto a mano (proceso {", ".join(map(str, manuales))}): '
            'ciérrelo para que la acción pueda usar el motor (019:RF-13).')
    ruta = ruta_turno()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    limite = reloj() + espera_s
    ultimo_aviso = None
    while True:
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            dueno = leer_turno(ruta)
            if dueno is None or not vivo(int(dueno.get('pid') or 0)):
                # RF-4: el dueño murió sin soltarlo (una sonda cortada, un guion matado).
                try:
                    ruta.unlink()
                except FileNotFoundError:
                    pass
                if dueno:
                    aviso(f"Turno de DIgSILENT liberado: {dueno.get('guion')} (proceso "
                          f"{dueno.get('pid')}) ya no estaba vivo.")
                continue
            if int(dueno['pid']) == os.getpid():
                return ruta
            quien = (f"{dueno.get('guion')} (proceso {dueno.get('pid')}, desde "
                     f"{dueno.get('desde')})")
            if reloj() >= limite:
                raise PFNoDisponible(
                    f'DIgSILENT sigue ocupado por {quien} tras esperar {espera_s / 60:.0f} '
                    'min (019:RF-2).')
            if ultimo_aviso is None or reloj() - ultimo_aviso >= AVISO_S:
                aviso(f'DIgSILENT ocupado por {quien}: esperando turno.')
                ultimo_aviso = reloj()
            dormir(PAUSA_S)
            continue
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'guion': guion,
                       'desde': datetime.now().isoformat(timespec='seconds')}, f)
        return ruta


def soltar_turno(ruta: Path | None = None) -> None:
    """Suelta el turno si es de este proceso."""
    ruta = ruta or ruta_turno()
    dueno = leer_turno(ruta)
    if dueno and int(dueno.get('pid') or 0) == os.getpid():
        try:
            ruta.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def turno_del_motor(guion: str, **kw: Any) -> Iterator[Path]:
    """El turno del motor mientras dura el bloque (RF-1)."""
    ruta = tomar_turno(guion, **kw)
    try:
        yield ruta
    finally:
        soltar_turno(ruta)


def conectar(guion: str, *, espera_s: float = ESPERA_S, modulo: Any = None,
             aviso: Callable[[str], None] = print,
             reloj: Callable[[], float] = time.monotonic,
             dormir: Callable[[float], None] = time.sleep, **turno: Any) -> Any:
    """Turno + conexión a DIgSILENT: la única llamada a ``GetApplicationExt`` (RF-5).

    El turno se suelta al salir el proceso; si muere sin soltarlo, el siguiente lo libera
    (RF-4). Lanza :class:`PFNoDisponible` sin API, con el motor ocupado más del límite o
    con DIgSILENT abierto a mano.
    """
    if _APP_COMPARTIDA is not None:
        # 019:RF-7: dentro del servidor, la conexión y el turno ya son suyos.
        usuario = getattr(_APP_COMPARTIDA.GetCurrentUser(), 'loc_name', '?')
        print(f'Conectado a DIgSILENT como {usuario} (proceso que se queda abierto).',
              flush=True)
        return _APP_COMPARTIDA
    if modulo is None:
        try:
            modulo = importlib.import_module('powerfactory')
        except ImportError as exc:
            raise PFNoDisponible(f'API de DIgSILENT no disponible ({exc}).') from exc
    ruta = tomar_turno(guion, espera_s=espera_s, aviso=aviso, reloj=reloj, dormir=dormir,
                       **turno)
    atexit.register(soltar_turno, ruta)
    limite = reloj() + espera_s
    inicio = reloj()
    while True:
        try:
            app = modulo.GetApplicationExt()
            break
        except Exception as exc:  # noqa: BLE001 - PowerFactory lanza su propio ExitError
            # RF-3: otro proceso de fuera del turno (DIgSILENT recién cerrado, un guion
            # de una versión anterior) aún tiene el motor: se reintenta hasta el límite.
            if MOTOR_OCUPADO in str(exc) and reloj() < limite:
                aviso(f'DIgSILENT aún ocupado ({exc}); reintento.')
                dormir(PAUSA_S)
                continue
            soltar_turno(ruta)
            raise PFNoDisponible(f'no se pudo conectar a DIgSILENT: {exc}') from exc
    usuario = getattr(app.GetCurrentUser(), 'loc_name', '?')
    # Primera línea solo con DIgSILENT ya respondiendo: la web la espera un tiempo
    # limitado y, si no llega, corta el guion (005:RF-21, 019:RF-6).
    print(f'Conectado a DIgSILENT como {usuario} ({reloj() - inicio:.0f} s).', flush=True)
    return app


@contextmanager
def caso_restituido(app: Any) -> Iterator[Any]:
    """Deja activo, al terminar, el caso de estudio que lo estaba al empezar (RF-10)."""
    inicial = app.GetActiveStudyCase()
    try:
        yield inicial
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            try:
                inicial.Activate()
            except Exception:  # noqa: BLE001 - el proyecto pudo cerrarse; no tapa el error
                pass


@contextmanager
def paso(que: str, reloj: Callable[[], float] = time.monotonic) -> Iterator[None]:
    """Escribe la duración de un paso largo: activar, flujo, guardar (RF-6)."""
    inicio = reloj()
    try:
        yield
    finally:
        print(f'  {que}: {reloj() - inicio:.1f} s', flush=True)


# --------------------------------------------------------------------------- proceso que se queda
#: Guion del proceso que mantiene DIgSILENT abierto entre órdenes (019:RF-7).
SERVIDOR = 'pf_servidor.py'
#: Sin órdenes durante este tiempo, el servidor se cierra (usuario, 2026-10-15: 2 minutos).
INACTIVIDAD_S = 120.0
#: Carpeta de la cola de órdenes para las pruebas o para otra máquina.
VARIABLE_COLA = 'IGEA_PF_COLA'
#: Guiones que el servidor puede atender: los que conectan con :func:`conectar`. La
#: aceptación (importa DGS y cambia de proyecto) sigue en su propio proceso.
GUIONES_SERVIBLES = frozenset({
    'ajuste_cabecera_pf.py', 'cargas_pf.py', 'casos_pf.py', 'estudios_pf.py', 'obras_pf.py',
    'pf_proyectos.py', 'transferencia_pf.py', 'transformador_set_pf.py', 'verificar_pf.py'})

_APP_COMPARTIDA: Any = None


def compartir_app(app: Any) -> None:
    """El servidor deja su conexión para los guiones que atiende en su proceso (RF-7)."""
    global _APP_COMPARTIDA
    _APP_COMPARTIDA = app


def ruta_cola() -> Path:
    if os.environ.get(VARIABLE_COLA):
        return Path(os.environ[VARIABLE_COLA])
    return ruta_turno().parent / 'cola_pf'


def servidor_vivo(ruta: Path | None = None) -> dict | None:
    """El servidor que tiene el turno, si está vivo: ``{pid, guion, desde}``."""
    dueno = leer_turno(ruta)
    if dueno and dueno.get('guion') == SERVIDOR and pid_vivo(int(dueno.get('pid') or 0)):
        return dueno
    return None


def cerrar_servidor() -> dict | None:
    """Cierra el servidor y libera el turno (019:RF-8, RF-9); devuelve el que cerró."""
    dueno = servidor_vivo()
    if dueno is None:
        return None
    from .powerfactory_env import terminar_arbol

    try:
        terminar_arbol(int(dueno['pid']))
    except OSError:
        pass
    try:
        ruta_turno().unlink()
    except FileNotFoundError:
        pass
    return dueno
