"""El controlador de NVIDIA no tumba el proceso al iniciar CUDA (106:RF-18, RF-19).

Caso real (2026-11-13, controlador 560.94 de una RTX 4060 de portátil): ``cuInit``, que pide
``torch.cuda.is_available()`` y cualquier uso de la GPU, carga ``nvdxgdmal64.dll`` del DriverStore y la descarga
enseguida, pero deja un hilo nativo que, en el siguiente aviso del sistema (cada ~90 s), ejecuta código dentro de esa
DLL ya descargada. El proceso muere con 0xC0000005 (violación de DEP en el desplazamiento +0x8190), sin traza de
Python, también con ``CUDA_VISIBLE_DEVICES=-1``: la suite caía a mitad y una sesión de la web con el asistente también.
Lo mismo cuentan FluidVoice (github.com/altic-dev/FluidVoice/issues/585, controlador 555.85) y chia-gigahorse
(github.com/madMAx43v3r/chia-gigahorse/issues/336, «nvdxgdmal64.dll_unloaded»).

La corrección: antes del primer ``cuInit``, cargar esa DLL desde la carpeta del controlador y fijarla con
``GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN)``, que la deja en memoria hasta que acaba el proceso. El
``FreeLibrary`` del controlador ya no la saca y el hilo encuentra su código. Sin Windows, sin NVIDIA o sin la DLL no se
hace nada. El paquete instala un buscador de módulos (``instalar_antes_de_torch``) que la fija la primera vez que
alguien importa ``torch``: un solo punto para todos los modelos del producto, sin repetir la llamada en cada uno.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import importlib.abc
import os
import sys
import threading
from typing import Any, Callable

#: La clase de dispositivos de pantalla del registro de Windows: una subclave por adaptador.
CLASE_PANTALLA = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
#: La DLL que el controlador descarga con un hilo suyo aún vivo.
DLL_NVIDIA = 'nvdxgdmal64.dll'
#: La última versión del controlador con el fallo comprobado (esta máquina). NVIDIA no ha publicado en qué versión lo
#: corrige; hasta saberlo, el doctor recomienda actualizar a cualquiera que no pase de esta.
ULTIMA_VERSION_AFECTADA = (560, 94)

#: ``GET_MODULE_HANDLE_EX_FLAG_PIN``: el módulo queda cargado hasta que termina el proceso.
_FLAG_PIN = 0x1
#: ``LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32``: sus dependencias, de su carpeta y de System32,
#: nunca de la carpeta de trabajo.
_BUSQUEDA_SEGURA = 0x100 | 0x800


@dataclass(frozen=True)
class Adaptador:
    descripcion: str
    #: ``DriverVersion`` del registro, p. ej. ``32.0.15.6094``.
    version_windows: str
    #: La carpeta del DriverStore donde están sus DLL de modo usuario.
    carpeta: str


@dataclass(frozen=True)
class EstadoFijado:
    """Qué hizo ``fijar_dll_nvidia``, para el doctor y los registros."""
    #: ``no_windows``, ``sin_nvidia``, ``sin_dll``, ``fijada`` o ``error``.
    accion: str
    detalle: str
    rutas: tuple[str, ...] = field(default=())

    @property
    def activa(self) -> bool:
        return self.accion == 'fijada'


_estado: EstadoFijado | None = None
_cerrojo = threading.Lock()


def version_nvidia(version_windows: str) -> tuple[int, int] | None:
    """La versión de NVIDIA (560.94) a partir de la de Windows (32.0.15.6094): las cinco últimas cifras."""
    partes = str(version_windows).strip().split('.')
    if len(partes) != 4 or not all(p.isdigit() for p in partes):
        return None
    cifras = (partes[2] + partes[3])[-5:]
    if len(cifras) < 5:
        return None
    return int(cifras[:3]), int(cifras[3:])


def _valor(winreg: Any, clave: Any, nombre: str) -> Any:
    try:
        return winreg.QueryValueEx(clave, nombre)[0]
    except OSError:
        return None


def adaptadores_nvidia(winreg: Any = None) -> list[Adaptador]:
    """Los adaptadores NVIDIA del registro, con la carpeta de su controlador; vacío sin Windows o sin la clave."""
    if winreg is None:
        if sys.platform != 'win32':
            return []
        import winreg
    adaptadores: list[Adaptador] = []
    try:
        clase = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLASE_PANTALLA)
    except OSError:
        return []
    with clase:
        try:
            subclaves = winreg.QueryInfoKey(clase)[0]
        except OSError:
            return []
        for i in range(subclaves):
            try:
                nombre = winreg.EnumKey(clase, i)
                clave = winreg.OpenKey(clase, nombre)
            except OSError:
                continue  # «Properties» no se deja abrir sin ser administrador.
            with clave:
                descripcion = str(_valor(winreg, clave, 'DriverDesc') or '')
                proveedor = str(_valor(winreg, clave, 'ProviderName') or '')
                if 'nvidia' not in f'{descripcion} {proveedor}'.lower():
                    continue
                umd = _valor(winreg, clave, 'UserModeDriverName') or ()
                version = str(_valor(winreg, clave, 'DriverVersion') or '')
            for ruta in ([umd] if isinstance(umd, str) else list(umd)):
                carpeta = os.path.dirname(str(ruta))
                if carpeta and all(a.carpeta.lower() != carpeta.lower() for a in adaptadores):
                    adaptadores.append(Adaptador(descripcion, version, carpeta))
    return adaptadores


def _kernel32() -> Any:
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    k32.GetModuleHandleExW.restype = wintypes.BOOL
    k32.GetModuleHandleExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, ctypes.POINTER(wintypes.HMODULE)]
    return k32


def _fijar(ruta: str, k32: Any) -> str | None:
    """Carga y fija ``ruta``; ``None`` si quedó fijada, o el motivo si no."""
    import ctypes
    from ctypes import wintypes

    if not k32.LoadLibraryExW(ruta, None, _BUSQUEDA_SEGURA):
        return f'LoadLibraryExW falló (error {ctypes.get_last_error()})'
    modulo = wintypes.HMODULE()
    if not k32.GetModuleHandleExW(_FLAG_PIN, ruta, ctypes.byref(modulo)):
        return f'GetModuleHandleExW falló (error {ctypes.get_last_error()})'
    return None


def fijar_dll_nvidia(*, plataforma: str | None = None, winreg: Any = None, kernel32: Callable[[], Any] = _kernel32,
                     existe: Callable[[str], bool] = os.path.isfile) -> EstadoFijado:
    """Fija ``nvdxgdmal64.dll`` del controlador NVIDIA antes del primer ``cuInit`` (106:RF-18).

    Nunca lanza: sin Windows, sin NVIDIA, sin la clave del registro o sin la DLL en la carpeta del controlador no hace
    nada y lo dice. Es idempotente: la primera llamada decide y las siguientes devuelven lo mismo sin volver a cargar
    nada. Las dependencias se inyectan para probarla sin el registro ni el kernel reales.
    """
    global _estado
    with _cerrojo:
        if _estado is not None:
            return _estado
        _estado = _decidir(plataforma or sys.platform, winreg, kernel32, existe)
        return _estado


def _decidir(plataforma: str, winreg: Any, kernel32: Callable[[], Any], existe: Callable[[str], bool]) -> EstadoFijado:
    if plataforma != 'win32':
        return EstadoFijado('no_windows', 'Solo hace falta en Windows.')
    adaptadores = adaptadores_nvidia(winreg)
    if not adaptadores:
        return EstadoFijado('sin_nvidia', 'Sin adaptador NVIDIA en el registro.')
    rutas = [os.path.join(a.carpeta, DLL_NVIDIA) for a in adaptadores]
    presentes = [r for r in rutas if existe(r)]
    if not presentes:
        return EstadoFijado('sin_dll', f'El controlador no trae {DLL_NVIDIA}: no hay nada que fijar.')
    try:
        k32 = kernel32()
    except OSError as exc:
        return EstadoFijado('error', f'Sin kernel32: {exc}')
    fijadas, fallos = [], []
    for ruta in presentes:
        try:
            motivo = _fijar(ruta, k32)
        except OSError as exc:
            motivo = str(exc)
        if motivo is None:
            fijadas.append(ruta)
        else:
            fallos.append(f'{ruta}: {motivo}')
    if fijadas:
        return EstadoFijado('fijada', f'{DLL_NVIDIA} fijada en memoria antes de iniciar CUDA.', tuple(fijadas))
    return EstadoFijado('error', 'No se pudo fijar: ' + '; '.join(fallos))


def estado_fijado() -> EstadoFijado | None:
    """Lo que hizo ``fijar_dll_nvidia`` en este proceso, o ``None`` si aún no se llamó."""
    return _estado


class _AntesDeTorch(importlib.abc.MetaPathFinder):
    """Fija la DLL la primera vez que se importa ``torch``, y se retira: no encuentra nada, solo mira el nombre."""

    def find_spec(self, nombre, ruta=None, objetivo=None):
        if nombre == 'torch':
            try:
                sys.meta_path.remove(self)
            except ValueError:
                pass
            fijar_dll_nvidia()
        return None


def instalar_antes_de_torch() -> bool:
    """Deja la fijación lista para el primer ``import torch`` de este proceso; ``True`` si la dejó (106:RF-18).

    Si ``torch`` ya estaba importado, fija ahora: puede que CUDA aún no se haya iniciado.
    """
    if sys.platform != 'win32':
        return False
    if 'torch' in sys.modules:
        fijar_dll_nvidia()
        return True
    if not any(isinstance(b, _AntesDeTorch) for b in sys.meta_path):
        sys.meta_path.insert(0, _AntesDeTorch())
    return True


def antes_de_torch_instalado() -> bool:
    """Si este proceso fijará la DLL al importar ``torch`` (o ya la fijó)."""
    return (_estado is not None and _estado.activa) or any(isinstance(b, _AntesDeTorch) for b in sys.meta_path)
