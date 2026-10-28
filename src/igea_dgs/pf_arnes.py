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
import subprocess
import sys
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
#: Lo que se espera a un proceso que soltó el turno al salir y aún cierra DIgSILENT
#: (019:RF-19); pasado, se le toma el turno igual.
CIERRE_S = 120.0
#: Plazo para que ``GetApplicationExt`` responda (RF-23). Menor que el de la primera línea
#: de la web (180 s, ``jobs.LIMITE_ARRANQUE_PF_S``) para que el motivo lo dé el arnés
#: (RF-24); las conexiones normales tardan de 12 a 55 s (2026-10-24).
CONEXION_S = 150.0
#: Código de salida de un guion que el vigía terminó porque DIgSILENT no respondió (RF-23);
#: el de «fallo temporal, reintente» de ``sysexits.h``.
SIN_RESPUESTA = 75
#: Cada cuánto mira el vigía si ya conectó.
VIGIA_PAUSA_S = 0.25


class PFNoDisponible(RuntimeError):
    """No se puede hablar con DIgSILENT: sin API, ocupado más del límite o abierto a mano."""


def _terminar_proceso(pid: int, codigo: int) -> None:
    """Termina ``pid`` con ``codigo``: en Windows con ``TerminateProcess``, que lo deja como
    código de salida; en otro sistema, con ``SIGKILL``."""
    if os.name == 'nt':
        import ctypes

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x0001, False, int(pid))                     # PROCESS_TERMINATE
        if h:
            k32.TerminateProcess(h, int(codigo))
            k32.CloseHandle(h)
        return
    import signal

    os.kill(int(pid), signal.SIGKILL)


def vigilar_conexion(pid: int, plazo_s: float, marca: str | Path, turno: str | Path, *,
                     reloj: Callable[[], float] = time.monotonic,
                     dormir: Callable[[float], None] = time.sleep,
                     vivo: Callable[[int], bool] | None = None,
                     terminar: Callable[[int, int], None] = _terminar_proceso,
                     salida=None) -> bool:
    """El vigía de una conexión (RF-23), en un proceso aparte del guion.

    Corre fuera porque una llamada colgada a DIgSILENT puede retener el intérprete del
    guion, y entonces ningún hilo suyo llega a actuar. ``conectar`` escribe en ``marca``
    cada vez que DIgSILENT responde (un 4002 que se reintenta, RF-3, vuelve a contar el
    plazo) y «fin» al terminar de conectar. Si pasan ``plazo_s`` sin respuesta y el guion
    sigue vivo, escribe el motivo en la salida que comparten, lo termina con
    :data:`SIN_RESPUESTA` y suelta su turno. Devuelve si tuvo que terminarlo.
    """
    vivo = pid_vivo if vivo is None else vivo
    marca = Path(marca)

    def leida() -> tuple[str, float] | None:
        try:
            return marca.read_text(encoding='utf-8').strip(), marca.stat().st_mtime
        except OSError:
            return None

    ultima, limite = leida(), reloj() + plazo_s
    while True:
        actual = leida()
        if (actual and actual[0] == 'fin') or not vivo(pid):
            return False
        if actual != ultima:
            ultima, limite = actual, reloj() + plazo_s                    # respondió: otra vez
        if reloj() >= limite:
            break
        dormir(VIGIA_PAUSA_S)
    print(f'ERROR: DIgSILENT no respondió al conectar en {plazo_s:g} s (proceso {pid}): se termina '
          'el guion y se suelta su turno. Suele pasar justo después de cerrarse otro proceso de '
          'DIgSILENT; reintente (019:RF-23).', file=salida or sys.stdout, flush=True)
    terminar(pid, SIN_RESPUESTA)
    ruta = Path(turno)
    dueno = leer_turno(ruta)
    if dueno and int(dueno.get('pid') or 0) == int(pid):
        _borrar_si_sigue(ruta, dueno)
    return True


def _anotar(marca: Path, texto: str) -> None:
    try:
        marca.parent.mkdir(parents=True, exist_ok=True)
        marca.write_text(texto, encoding='utf-8')
    except OSError:
        pass


def _lanzar_vigia(plazo_s: float, marca: Path, turno: Path):
    """El vigía en su propio intérprete, con la salida del guion para que el motivo llegue
    al Registro de la web o a la consola."""
    src = str(Path(__file__).resolve().parents[1])
    codigo = (f'import sys; sys.path.insert(0, {src!r}); from igea_dgs.pf_arnes import vigilar_conexion; '
              f'vigilar_conexion({os.getpid()}, {float(plazo_s)!r}, {str(marca)!r}, {str(turno)!r})')
    banderas = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        return subprocess.Popen([sys.executable, '-c', codigo], stdin=subprocess.DEVNULL,
                                creationflags=banderas)
    except OSError:
        return None                       # sin vigía, la conexión sigue como antes


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


def inicio_proceso(pid: int) -> int | None:
    """Instante de creación del proceso ``pid`` (unidades del sistema), o ``None``.

    El par (pid, inicio) identifica un proceso aunque Windows reutilice su número: un
    turno de un proceso muerto cuyo pid tomó otro no debe parecer vivo (esperas de 10 min)
    ni llevar a cerrar un proceso ajeno (019:RF-19).
    """
    if pid <= 0:
        return None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            tiempos = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in tiempos)):
                return None
            creado = tiempos[0]
            return (creado.dwHighDateTime << 32) | creado.dwLowDateTime
        finally:
            kernel.CloseHandle(handle)
    try:
        campos = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return int(campos[19])
    except (OSError, IndexError, ValueError):
        return None


def dueno_vivo(dueno: dict | None, vivo: Callable[[int], bool] = pid_vivo,
               inicio: Callable[[int], int | None] = inicio_proceso) -> bool:
    """Si el proceso que escribió ``dueno`` sigue vivo: su pid y, si se anotó, su inicio."""
    if not dueno:
        return False
    pid = int(dueno.get('pid') or 0)
    if not vivo(pid):
        return False
    anotado = dueno.get('inicio')
    if anotado is None:
        return True
    actual = inicio(pid)
    return actual is None or actual == anotado


def leer_turno(ruta: Path | None = None) -> dict | None:
    """Quién tiene el motor: ``{pid, inicio, guion, desde}``, o ``None`` si nadie."""
    try:
        return json.loads((ruta or ruta_turno()).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _escribir_turno(ruta: Path, datos: dict) -> None:
    """Reescribe el turno de golpe: quien lo lee nunca ve un fichero a medias."""
    tmp = ruta.with_name(f'{ruta.name}.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(datos), encoding='utf-8')
    # En Windows ``os.replace`` falla con «acceso denegado» si otro proceso lee el turno
    # en ese instante: se reintenta unas veces antes de rendirse.
    for intento in range(20):
        try:
            os.replace(tmp, ruta)
            return
        except PermissionError:
            if intento == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def marcar_turno(ruta: Path | None = None, **campos: Any) -> None:
    """Añade ``campos`` al turno si es de este proceso (p. ej. ``conectado``)."""
    ruta = ruta or ruta_turno()
    dueno = leer_turno(ruta)
    if dueno and int(dueno.get('pid') or 0) == os.getpid():
        _escribir_turno(ruta, {**dueno, **campos})


def _borrar_si_sigue(ruta: Path, dueno: dict) -> None:
    """Borra el turno solo si sigue siendo ``dueno``.

    Dos procesos que ven a la vez un dueño muerto lo borraban los dos: el segundo
    borraba el turno recién tomado por el primero y entraban ambos (019:RF-19).
    """
    if leer_turno(ruta) == dueno:
        try:
            ruta.unlink()
        except FileNotFoundError:
            pass


def _abierto_a_mano() -> list[int]:
    from .powerfactory_env import powerfactory_abierto

    return powerfactory_abierto()


def tomar_turno(guion: str, *, espera_s: float = ESPERA_S,
                aviso: Callable[[str], None] = print,
                vivo: Callable[[int], bool] = pid_vivo,
                abierto: Callable[[], list[int]] = _abierto_a_mano,
                reloj: Callable[[], float] = time.monotonic,
                dormir: Callable[[float], None] = time.sleep,
                inicio: Callable[[int], int | None] = inicio_proceso,
                ahora: Callable[[], float] = time.time) -> Path:
    """Toma el turno del motor para este proceso o lanza :class:`PFNoDisponible`.

    RF-13: con DIgSILENT abierto a mano no se lanza nada (usuario, 2026-10-15: «avisas»).
    RF-2: si otro proceso lo tiene, se espera hasta ``espera_s`` diciendo quién.
    RF-4: si su dueño ya no vive, se libera y se sigue.
    RF-19: un dueño que soltó el turno al salir sigue con el motor hasta morir; se le
    espera hasta ``CIERRE_S``.
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
    cierre_pedido = False
    while True:
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            dueno = leer_turno(ruta)
            if dueno is None and ruta.exists():
                dormir(0.05)          # se está reescribiendo (``_escribir_turno``)
                dueno = leer_turno(ruta)
            muerto = dueno is None or not dueno_vivo(dueno, vivo, inicio)
            cerrado = (dueno is not None and dueno.get('liberado') is not None
                       and ahora() - float(dueno['liberado']) > CIERRE_S)
            if muerto or cerrado:
                # RF-4: el dueño murió sin soltarlo (una sonda cortada, un guion matado).
                # RF-19: o soltó al salir y lleva más de ``CIERRE_S`` sin acabar de cerrarse.
                if dueno is None:
                    try:
                        ruta.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    _borrar_si_sigue(ruta, dueno)
                    aviso(f"Turno de DIgSILENT liberado: {dueno.get('guion')} (proceso "
                          f"{dueno.get('pid')}) "
                          + ('ya no estaba vivo.' if muerto else
                             f'no terminó de cerrarse en {CIERRE_S:g} s.'))
                continue
            assert dueno is not None
            if int(dueno['pid']) == os.getpid():
                return ruta
            quien = (f"{dueno.get('guion')} (proceso {dueno.get('pid')}, desde "
                     f"{dueno.get('desde')})")
            if dueno.get('liberado') is not None:
                quien += ', cerrando DIgSILENT'
            if reloj() >= limite:
                raise PFNoDisponible(
                    f'DIgSILENT sigue ocupado por {quien} tras esperar {espera_s / 60:.0f} '
                    'min (019:RF-2).')
            if not cierre_pedido and pedir_cierre_si_ocioso(dueno):
                # RF-14: el servidor sin órdenes cede el motor en vez de esperar sus 2 min.
                cierre_pedido = True
                aviso(f'DIgSILENT lo tiene {quien} sin órdenes: se le pide que se cierre '
                      '(019:RF-14).')
                ultimo_aviso = reloj()
            if ultimo_aviso is None or reloj() - ultimo_aviso >= AVISO_S:
                aviso(f'DIgSILENT ocupado por {quien}: esperando turno.')
                ultimo_aviso = reloj()
            dormir(PAUSA_S)
            continue
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({'pid': os.getpid(), 'inicio': inicio(os.getpid()), 'guion': guion,
                       'desde': datetime.now().isoformat(timespec='seconds')}, f)
        return ruta


def soltar_turno(ruta: Path | None = None, *, al_salir: bool = False) -> None:
    """Suelta el turno si es de este proceso.

    Con ``al_salir`` (``atexit``, final del servidor) el motor de DIgSILENT aún se está
    cerrando dentro del proceso: se anota la hora y el turno sigue suyo hasta que muera
    (019:RF-19). 2026-10-19: tras importar CA101_PE104 el turno quedó libre antes de que
    el motor terminase de cerrarse, y el servidor que entró 11 s después no conectó en
    180 s; medido en DIgSILENT, un proceso sigue vivo tras soltarlo.
    """
    ruta = ruta or ruta_turno()
    dueno = leer_turno(ruta)
    if not dueno or int(dueno.get('pid') or 0) != os.getpid():
        return
    if al_salir:
        _escribir_turno(ruta, {**dueno, 'liberado': time.time()})
        return
    try:
        ruta.unlink()
    except FileNotFoundError:
        pass


def _soltar_al_salir(ruta: Path) -> None:
    soltar_turno(ruta, al_salir=True)


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
             dormir: Callable[[float], None] = time.sleep,
             plazo_conexion_s: float = CONEXION_S, vigia: Callable | None = None,
             **turno: Any) -> Any:
    """Turno + conexión a DIgSILENT: la única llamada a ``GetApplicationExt`` (RF-5).

    El turno se suelta al salir el proceso; si muere sin soltarlo, el siguiente lo libera
    (RF-4). Lanza :class:`PFNoDisponible` sin API, con el motor ocupado más del límite o
    con DIgSILENT abierto a mano. Un vigía en otro proceso termina este si DIgSILENT no
    responde en ``plazo_conexion_s`` (RF-23); ``vigia`` lo cambia en las pruebas.
    """
    if _APP_COMPARTIDA is not None:
        # 019:RF-7: dentro del servidor, la conexión y el turno ya son suyos.
        usuario = getattr(_APP_COMPARTIDA.GetCurrentUser(), 'loc_name', '?')
        print(f'Conectado a DIgSILENT como {usuario} (proceso que se queda abierto).',
              flush=True)
        return _APP_COMPARTIDA
    salida_sin_bufer()                                                     # RF-15
    if modulo is None:
        modulo = importar_api()
    ruta = tomar_turno(guion, espera_s=espera_s, aviso=aviso, reloj=reloj, dormir=dormir,
                       **turno)
    atexit.register(_soltar_al_salir, ruta)                               # RF-19
    limite = reloj() + espera_s
    inicio = reloj()
    marca = ruta.with_name(f'{ruta.stem}.conexion_{os.getpid()}')
    _anotar(marca, 'conectando')
    proc_vigia = (vigia or _lanzar_vigia)(plazo_conexion_s, marca, ruta)   # RF-23
    try:
        while True:
            try:
                app = modulo.GetApplicationExt()
                break
            except Exception as exc:  # noqa: BLE001 - PowerFactory lanza su propio ExitError
                # RF-3: otro proceso de fuera del turno (DIgSILENT recién cerrado, un guion
                # de una versión anterior) aún tiene el motor: se reintenta hasta el límite.
                if MOTOR_OCUPADO in str(exc) and reloj() < limite:
                    _anotar(marca, f'reintento {reloj():.1f}')
                    aviso(f'DIgSILENT aún ocupado ({exc}); reintento.')
                    dormir(PAUSA_S)
                    continue
                soltar_turno(ruta)
                raise PFNoDisponible(f'no se pudo conectar a DIgSILENT: {exc}') from exc
    finally:
        _anotar(marca, 'fin')
        if proc_vigia is not None:
            try:
                proc_vigia.wait(timeout=5)
                marca.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001, S110 - si sigue vivo, aún tiene que ver el «fin»
                pass
    usuario = getattr(app.GetCurrentUser(), 'loc_name', '?')
    # RF-20: quien corta una orden distingue un servidor que conecta de uno que atiende.
    marcar_turno(ruta, conectado=True)
    # Primera línea solo con DIgSILENT ya respondiendo: la web la espera un tiempo
    # limitado y, si no llega, corta el guion (005:RF-21, 019:RF-6).
    print(f'Conectado a DIgSILENT como {usuario} ({reloj() - inicio:.0f} s).', flush=True)
    return app


def salida_sin_bufer() -> None:
    """La salida del guion línea a línea también cuando va a un fichero (RF-15).

    Redirigida, Python la guarda en bloques: la limpieza de Chincha (2026-10-18) no mostró
    nada en 10 minutos y no se sabía si esperaba turno o borraba.
    """
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass                       # un flujo sustituido (pruebas, servidor): ya va así


def importar_api(importar: Callable[[str], Any] = importlib.import_module,
                 carpeta: Callable[[], Path | None] | None = None) -> Any:
    """El módulo ``powerfactory``, buscado también en la instalación de DIgSILENT (RF-16).

    Cada sonda de esta sesión (2026-10-18) fallaba con «No module named 'powerfactory'»
    hasta poner el ``PYTHONPATH`` a mano; la web ya lo ponía a sus guiones.
    """
    try:
        return importar('powerfactory')
    except ImportError as primero:
        if carpeta is None:
            from .powerfactory_env import pf_python_dir as carpeta
        ruta = carpeta()
        if ruta is None or str(ruta) in sys.path:
            raise PFNoDisponible(f'API de DIgSILENT no disponible ({primero}).') from primero
        sys.path.insert(0, str(ruta))
        try:
            return importar('powerfactory')
        except ImportError as exc:
            raise PFNoDisponible(f'API de DIgSILENT no disponible en {ruta} ({exc}).') from exc


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
# Los de la spec 024 también: fuera de la lista, la lectura del gemelo tras cada acción
# cerraba el servidor y abría DIgSILENT por su cuenta (AL105 + AL108, 2026-10-23: 2,5 min
# más por ajuste y 73 s de conexión en la acción siguiente).
GUIONES_SERVIBLES = frozenset({
    'ajuste_cabecera_pf.py', 'cargas_pf.py', 'casos_pf.py', 'digital_twin_snapshot_pf.py', 'escanear_alimentador_pf.py',
    'escenarios_pf.py', 'estudios_pf.py', 'obras_pf.py', 'pf_proyectos.py', 'pide_pf.py',
    'transferencia_pf.py', 'transformador_set_pf.py', 'verificar_pf.py'})

_APP_COMPARTIDA: Any = None


def compartir_app(app: Any) -> None:
    """El servidor deja su conexión para los guiones que atiende en su proceso (RF-7)."""
    global _APP_COMPARTIDA
    _APP_COMPARTIDA = app


def ruta_cola() -> Path:
    if os.environ.get(VARIABLE_COLA):
        return Path(os.environ[VARIABLE_COLA])
    return ruta_turno().parent / 'cola_pf'


#: Fichero de la cola con el que se pide al servidor ocioso que se cierre (RF-14).
CIERRE = 'cerrar.pedido'


def pedir_cierre_si_ocioso(dueno: dict | None) -> bool:
    """Pide al servidor que tiene el turno que se cierre si no tiene órdenes (RF-14).

    Devuelve si lo pidió. Con una orden en curso o en fila no se toca: es trabajo de otro.
    """
    if not dueno or dueno.get('guion') != SERVIDOR:
        return False
    cola = ruta_cola()
    if not cola.is_dir() or any(cola.glob('*.en_curso.json')) or any(cola.glob('*.orden.json')):
        return False
    (cola / CIERRE).write_text(str(os.getpid()), encoding='utf-8')
    return True


def servidor_vivo(ruta: Path | None = None) -> dict | None:
    """El servidor que tiene el turno y atiende órdenes: ``{pid, guion, desde, ...}``.

    Uno que ya se despidió (``liberado``) no atiende nada aunque su proceso siga vivo
    mientras cierra DIgSILENT (019:RF-19).
    """
    dueno = leer_turno(ruta)
    if (dueno and dueno.get('guion') == SERVIDOR and dueno.get('liberado') is None
            and dueno_vivo(dueno)):
        return dueno
    return None


#: Variable con la que la web da al cliente el identificador de su orden (019:RF-20).
VARIABLE_ORDEN = 'IGEA_PF_ORDEN'


def cerrar_servidor(orden: str | None = None) -> dict | None:
    """Cierra el servidor y libera el turno (019:RF-8, RF-9); devuelve el que cerró.

    Con ``orden`` (019:RF-20) solo se cierra si el corte es suyo: si atiende esa orden, o
    si sigue sin conectar (colgado en DIgSILENT, no atiende a nadie). Si la orden aún
    espera en la cola, se retira. Antes se cerraba siempre: el corte de una acción de un
    espacio tumbaba la orden que el servidor atendía para otro.
    """
    cola = ruta_cola()
    dueno = servidor_vivo()
    if orden is not None:
        (cola / f'{orden}.orden.json').unlink(missing_ok=True)
        if dueno is None:
            return None
        if dueno.get('conectado') and not (cola / f'{orden}.en_curso.json').exists():
            return None
    if dueno is None:
        return None
    from .powerfactory_env import terminar_arbol

    try:
        terminar_arbol(int(dueno['pid']))
    except (OSError, subprocess.SubprocessError):
        pass
    _borrar_si_sigue(ruta_turno(), dueno)
    return dueno
