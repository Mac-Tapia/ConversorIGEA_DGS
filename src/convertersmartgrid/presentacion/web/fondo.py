"""Carril de fondo: el trabajo automático de la web cede siempre al operador (104:RF-30 a RF-33, RF-36, RF-37).

El 2026-11-12, en la web del operador, el reconocimiento de libros nuevos corría como un trabajo del motor: al abrir un
espacio sin índice anterior leyó los 22 libros con «22/22» durante más de 2 minutos, cancelarlo tardó 40 s (la
lectura de un libro con calamine no se corta a mitad) y «Cargar / listar alimentadores» quedó desactivado y luego en
cola. Lo de fondo no entra en la cola de trabajos: corre en su propio hilo, lee cada libro en un proceso de prioridad
baja y, en cuanto el operador lanza algo en el motor o en DIgSILENT, ese proceso se termina.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import time
from typing import Any, Callable

#: Los carriles del operador: lo de fondo no corre mientras haya un trabajo suyo en ellos, de cualquier espacio,
#: porque comparten la CPU, la memoria y el disco (104:RF-32).
CARRILES_DEL_OPERADOR = ('engine', 'powerfactory')
#: ``BELOW_NORMAL_PRIORITY_CLASS`` de Windows (104:RF-33).
BELOW_NORMAL = 0x00004000
#: Cada cuánto se mira si hay que ceder mientras corre el proceso de un libro: muy por debajo de los 2 s de RF-32.
ESPERA_S = 0.1


class Cedido(Exception):
    """El trabajo de fondo cedió el equipo al operador; se reanuda cuando el motor quede libre."""


def operador_trabajando(jobs) -> bool:
    """Hay un trabajo del operador en cola o en marcha en el motor o en DIgSILENT, de cualquier espacio."""
    from .jobs import FINISHED

    return any(j.lane in CARRILES_DEL_OPERADOR and j.status not in FINISHED for j in jobs.list())


def _kernel32():
    """Con los tipos declarados: sin ellos, el seudoidentificador del proceso se pasa truncado a 32 bits y Windows
    lo rechaza sin decir nada."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k32.SetPriorityClass.restype = wintypes.BOOL
    k32.GetPriorityClass.argtypes = (wintypes.HANDLE,)
    k32.GetPriorityClass.restype = wintypes.DWORD
    return k32


def bajar_prioridad() -> None:
    """El proceso que lo llama pasa a prioridad baja; si el sistema no lo permite, sigue igual."""
    try:
        if os.name == 'nt':
            k32 = _kernel32()
            k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL)
        else:
            os.nice(10)
    except Exception:  # noqa: BLE001 - sin permiso para cambiarla, el proceso se termina igual al ceder
        pass


def prioridad_del_proceso() -> str:
    """«baja» o «normal», para la prueba de que el proceso de fondo de verdad bajó su prioridad."""
    if os.name == 'nt':
        k32 = _kernel32()
        return 'baja' if k32.GetPriorityClass(k32.GetCurrentProcess()) == BELOW_NORMAL else 'normal'
    return 'baja' if os.nice(0) > 0 else 'normal'


def _hijo(fn: Callable[..., Any], args: tuple, kwargs: dict, cola) -> None:
    bajar_prioridad()
    try:
        cola.put(('fin', fn(*args, **kwargs)))
    except BaseException as exc:  # noqa: BLE001 - el padre lo vuelve a lanzar
        try:
            cola.put(('error', exc))
        except Exception:  # noqa: BLE001 - excepción que no se puede enviar
            cola.put(('error', RuntimeError(f'{type(exc).__name__}: {exc}')))


class ProcesoFondo:
    """Una función de nivel superior en un proceso ``spawn`` de prioridad baja, que se puede terminar en cualquier
    instante sin esperar a que acabe el libro que lee (104:RF-33)."""

    def __init__(self, fn: Callable[..., Any], *args: Any, nombre: str = 'csg-fondo', **kwargs: Any) -> None:
        contexto = mp.get_context('spawn')
        self._cola = contexto.Queue()
        self.proc = contexto.Process(target=_hijo, args=(fn, args, kwargs, self._cola), daemon=True, name=nombre)
        self.proc.start()

    def resultado(self, espera: float = 0.0) -> tuple[bool, Any]:
        """``(True, valor)`` si terminó; ``(False, None)`` si sigue. Un error del hijo se vuelve a lanzar aquí."""
        try:
            tipo, dato = self._cola.get(timeout=espera) if espera else self._cola.get_nowait()
        except queue.Empty:
            if not self.proc.is_alive() and self._cola.empty():
                raise RuntimeError(f'el proceso de fondo terminó sin resultado (código {self.proc.exitcode})')
            return False, None
        self.proc.join(timeout=2)
        if tipo == 'error':
            raise dato
        return True, dato

    def vivo(self) -> bool:
        return self.proc.is_alive()

    def terminar(self) -> None:
        if self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(timeout=2)
        if self.proc.is_alive():
            self.proc.kill()
            self.proc.join(timeout=2)


def ejecutar_en_proceso(fn: Callable[..., Any], *args: Any, ceder: Callable[[], bool], **kwargs: Any) -> Any:
    """``fn(*args)`` en un :class:`ProcesoFondo`; si ``ceder()`` se vuelve cierto, lo termina y lanza :class:`Cedido`."""
    if ceder():
        raise Cedido()
    proceso = ProcesoFondo(fn, *args, **kwargs)
    try:
        while True:
            listo, valor = proceso.resultado(ESPERA_S)
            if listo:
                return valor
            if ceder():
                raise Cedido()
    finally:
        proceso.terminar()


def ejecutar_aqui(fn: Callable[..., Any], *args: Any, ceder: Callable[[], bool], **kwargs: Any) -> Any:
    """Lo mismo en este proceso, para las pruebas que no necesitan terminar a mitad de un libro."""
    if ceder():
        raise Cedido()
    resultado = fn(*args, **kwargs)
    if ceder():
        raise Cedido()
    return resultado


class ContextoFondo:
    """Lo que los índices de ``services`` piden a un ``JobContext`` (avance, registro y cancelación), para el carril de
    fondo: cancelar es ceder al operador."""

    def __init__(self, ceder: Callable[[], bool], *, log: Callable[[str], None] = lambda _t: None,
                 progreso: Callable[[int, int, str], None] = lambda _i, _n, _m='': None) -> None:
        self._ceder, self._log, self._progreso = ceder, log, progreso
        self.inicio = time.monotonic()

    def log(self, text: str) -> None:
        if text:
            self._log(text)

    def progress(self, index: int, total: int, label: str = '') -> None:
        self._progreso(index, total, label)

    def check_cancel(self) -> None:
        if self._ceder():
            raise Cedido()
