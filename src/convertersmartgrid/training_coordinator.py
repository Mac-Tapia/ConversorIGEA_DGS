"""Coordinador secuencial, reanudable y con exclusión mutua de GPU."""
from __future__ import annotations

from .runtime_paths import staging_publicacion

import json
import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .model_registry import EstadoModelo


ORDEN_MODELOS = ('transformer', 'clasificador', 'gru', 'pinn', 'evolutivos', 'embeddings', 'qlora')


def _memoria_sistema() -> dict[str, float | None]:
    """Consulta ligera: en Windows el error 1455 depende del margen de compromiso."""
    if os.name != 'nt':
        import psutil
        return {'fisica_gib': psutil.virtual_memory().available / 1024**3, 'commit_gib': None}
    import ctypes
    from ctypes import wintypes

    class EstadoMemoria(ctypes.Structure):
        _fields_ = [('longitud', wintypes.DWORD), ('carga', wintypes.DWORD)] + [
            (nombre, ctypes.c_ulonglong) for nombre in (
                'total_fisica', 'libre_fisica', 'total_commit', 'libre_commit',
                'total_virtual', 'libre_virtual', 'libre_extendida')]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes = (ctypes.POINTER(EstadoMemoria),)
    kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
    estado = EstadoMemoria(); estado.longitud = ctypes.sizeof(estado)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(estado)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'fisica_gib': estado.libre_fisica / 1024**3, 'commit_gib': estado.libre_commit / 1024**3}


class MemoriaMLInsuficiente(ValueError):
    """El entorno no tiene margen de memoria; no es una ausencia de datos de entrenamiento."""


def exigir_memoria_ml(minimo_fisico_gib: float, *, minimo_commit_gib: float) -> dict:
    """Exige margen previo; permite paginación Windows sin fingir que la carga pasó."""
    import math
    estado = _memoria_sistema()
    fisica, commit = estado['fisica_gib'], estado['commit_gib']
    valores = [fisica, minimo_fisico_gib, minimo_commit_gib] + ([] if commit is None else [commit])
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in valores):
        raise ValueError('Contadores o limites de memoria invalidos')
    insuficiente = fisica < minimo_fisico_gib if commit is None else fisica < .5 or commit < minimo_commit_gib
    if insuficiente:
        raise MemoriaMLInsuficiente(f'Memoria insuficiente: fisica={fisica:.2f} GiB, comprometible={commit}; '
                         f'requiere {minimo_fisico_gib} GiB fisicos o, en Windows, '
                         f'0.5 GiB fisicos y {minimo_commit_gib} GiB comprometibles')
    return estado


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == 'nt':
        # En Windows `os.kill(pid, 0)` puede terminar el proceso; OpenProcess consulta
        # existencia/permisos sin enviar señal alguna.
        import ctypes
        acceso_consulta_limitada = 0x1000
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(acceso_consulta_limitada, False, pid)
        if handle:
            kernel.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == 5  # acceso denegado también implica que existe
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


#: Lectura pública para otros módulos de aplicación (050: marca de un ciclo en curso).
pid_vivo = _pid_vivo

class BloqueoGPU:
    def __init__(self, ruta: Path | str, model: str):
        self.ruta, self.model = Path(ruta), model
        self.token = uuid.uuid4().hex
        self._guardia = None

    def __enter__(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        # 043:RF-6: la guardia OS permanece en disco; cerrar el descriptor libera
        # el bloqueo incluso al morir el proceso. Nunca se borra su inode.
        guardia = self.ruta.with_name(self.ruta.name + '.guard').open('a+b')
        if guardia.seek(0, os.SEEK_END) == 0:
            guardia.write(b'1')
            guardia.flush()
        guardia.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(guardia.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(guardia.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            guardia.close()
            raise RuntimeError('GPU ocupada: otro proceso conserva la guardia') from None
        self._guardia = guardia
        try:
            return self._entrar_con_guardia()
        except BaseException:
            self._guardia.close()
            self._guardia = None
            raise

    def _entrar_con_guardia(self):
        for _ in range(2):
            try:
                fd = os.open(self.ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError:
                try:
                    previo = json.loads(self.ruta.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    raise RuntimeError('GPU ocupada: lock ilegible; se conserva fail-closed') from None
                if not isinstance(previo, dict) or type(previo.get('pid')) is not int or previo['pid'] <= 0:
                    raise RuntimeError('GPU ocupada: lock sin propietario válido; se conserva')
                if _pid_vivo(previo['pid']):
                    raise RuntimeError(f'GPU ocupada por PID {previo.get("pid")} ({previo.get("model")})')
                try:
                    self.ruta.unlink()
                except FileNotFoundError:
                    pass
                continue
            else:
                payload = {'pid': os.getpid(), 'model': self.model, 'token': self.token,
                           'started_at': datetime.now(timezone.utc).isoformat()}
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(payload, f)
                return self
        raise RuntimeError('GPU ocupada: no se pudo adquirir el lock')

    def __exit__(self, _tipo, _valor, _traza):
        try:
            payload = json.loads(self.ruta.read_text(encoding='utf-8'))
            if payload.get('pid') == os.getpid() and payload.get('token') == self.token:
                self.ruta.unlink()
        except (OSError, ValueError):
            pass
        finally:
            if self._guardia is not None:
                self._guardia.close()
                self._guardia = None


@dataclass(frozen=True)
class TrainingStage:
    name: str
    run: Callable[[], dict[str, Any]]
    uses_gpu: bool = True

    def __init__(self, name: str, run: Callable[[], dict[str, Any]], uses_gpu: bool = True, **kw):
        # Alias español para que los consumidores puedan declarar `nombre=` sin adaptar callbacks.
        object.__setattr__(self, 'name', kw.pop('nombre', name) if kw else name)
        object.__setattr__(self, 'run', run)
        object.__setattr__(self, 'uses_gpu', uses_gpu)


class TrainingCoordinator:
    def __init__(self, stages: Sequence[TrainingStage], run_dir: Path | str, *,
                 liberar_ollama: Callable[[], Any] = lambda: None,
                 liberar_cuda: Callable[[], Any] = lambda: None,
                 config_hash: str | None = None):
        indice = {n: i for i, n in enumerate(ORDEN_MODELOS)}
        desconocidas = [s.name for s in stages if s.name not in indice]
        if desconocidas:
            raise ValueError(f'etapas desconocidas: {desconocidas}')
        if len({s.name for s in stages}) != len(stages):
            raise ValueError('etapas duplicadas')
        self.stages = sorted(stages, key=lambda s: indice[s.name])
        self.run_dir = Path(run_dir)
        self.config_hash = config_hash or hashlib.sha256(json.dumps(
            [(s.name, s.uses_gpu) for s in self.stages]).encode()).hexdigest()
        # 043:RF-6: el recurso compartido es la GPU, no el directorio de cada corrida.
        self.gpu_lock = Path(os.environ.get('CSG_ML_GPU_LOCK') or
                             str(Path(tempfile.gettempdir()) / 'convertersmartgrid-gpu.lock'))
        self.liberar_ollama, self.liberar_cuda = liberar_ollama, liberar_cuda

    def _escribir(self, ruta: Path, payload: dict[str, Any]) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with staging_publicacion(ruta) as tmp:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
            os.replace(tmp, ruta)

    def run(self, *, resume: bool = True) -> dict[str, Any]:
        estado_ruta, reporte_ruta = self.run_dir / 'state.json', self.run_dir / 'report.json'
        if reporte_ruta.is_file():
            anterior = json.loads(reporte_ruta.read_text(encoding='utf-8'))
            if not resume or anterior.get('config_hash') != self.config_hash:
                raise ValueError('configuración incompatible: use otro directorio de ejecución')
            return anterior
        estado = json.loads(estado_ruta.read_text(encoding='utf-8')) if resume and estado_ruta.is_file() else {
            'stages': {}, 'config_hash': self.config_hash}
        if estado.get('config_hash') != self.config_hash:
            raise ValueError('configuración incompatible con las etapas guardadas')
        terminales = {e.value for e in EstadoModelo}
        resultados = []
        for etapa in self.stages:
            previo = estado['stages'].get(etapa.name)
            if previo and previo.get('status') in terminales:
                resultados.append(previo)
                continue
            try:
                if etapa.uses_gpu:
                    with BloqueoGPU(self.gpu_lock, etapa.name):
                        try:
                            self.liberar_ollama()
                            resultado = etapa.run()
                        finally:
                            self.liberar_cuda()
                else:
                    resultado = etapa.run()
                if resultado.get('status') not in terminales:
                    raise ValueError(f'estado no terminal: {resultado.get("status")}')
            except ValueError as exc:
                resultado = {'status': EstadoModelo.BLOQUEADO_POR_DATOS.value,
                             'model': etapa.name, 'reason': str(exc)}
            except Exception as exc:  # frontera: una fase no impide registrar las siguientes
                resultado = {'status': EstadoModelo.ERROR_ENTORNO.value,
                             'model': etapa.name, 'reason': str(exc)}
            resultado = {'model': etapa.name, **resultado}
            estado['stages'][etapa.name] = resultado
            self._escribir(estado_ruta, estado)
            resultados.append(resultado)
        reporte = {'schema': 'convertersmartgrid-training-report-v1', 'stages': resultados,
                   'config_hash': self.config_hash, 'complete': len(resultados) == len(self.stages)}
        self._escribir(reporte_ruta, reporte)
        return reporte
