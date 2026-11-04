"""Retención de ejecuciones y temporales de la web, sin borrar fuentes ni modelos.

Solo se retiran árboles reconocidos y sin referencias. El reloj y el resultado se
persisten para no ejecutar otra limpieza diaria por cada reinicio del servidor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import stat
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .source_runs import valid_run_id
from .workspace import expandir_rutas

RUN_EN_TEXTO = re.compile(r'\d{8}T\d{6}-[a-f0-9]{12}')
PESOS = {'.pt', '.pth', '.onnx', '.gguf', '.safetensors', '.bin'}
_DOCUMENTOS = {'.pdf', '.docx', '.xlsx', '.xls', '.html'}


def es_valioso(path: Path) -> bool:
    """Un modelo o un informe: ni la limpieza lo retira ni la copia lo deja fuera (086:RF-10)."""
    name = path.name.lower()
    return path.suffix.lower() in (PESOS | _DOCUMENTOS) or any(
        token in name for token in ('informe', 'aceptacion', 'acceptance', 'native_report', 'modelo', 'checkpoint')
    )


class RetencionDiaria:
    """Política elegida por el operador: siete días, revisión cada24 horas."""

    def __init__(self, store, jobs, *, ahora: Callable[[], float] = time.time):
        self.store, self.jobs, self.ahora = store, jobs, ahora
        self.root = store.root.resolve()
        self.path = self.root / '_mantenimiento' / 'retencion.json'
        self._lock = threading.Lock()
        self._ultimo_en_memoria: dict | None = None

    def estado(self) -> dict:
        ultimo = None
        error = None
        try:
            if self.path.parent.exists() and (not self.path.parent.is_dir() or not self._sin_redireccion(self.path.parent)):
                raise ValueError('No se puede custodiar el resumen de limpieza en esa carpeta')
            if self.path.exists():
                if not self._sin_redireccion(self.path):
                    raise ValueError('Resumen de limpieza con redirección')
                ultimo = json.loads(self.path.read_text(encoding='utf-8'))
                fecha = ultimo.get('terminada') if isinstance(ultimo, dict) else None
                if type(fecha) not in (int, float) or not math.isfinite(fecha):
                    raise ValueError('Resumen de retención no válido')
        except (OSError, ValueError) as exc:
            error = str(exc)
            ultimo = None
        if self._ultimo_en_memoria is not None:
            ultimo = self._ultimo_en_memoria
            if ultimo['errores']:
                error = '; '.join(ultimo['errores'])
        return {
            'retencion_dias': 7, 'intervalo_horas': 24,
            'ultima_revision': ultimo,
            'proxima_revision': ultimo['terminada'] + 86400 if ultimo else None,
            'error': error,
            'alcance': 'Ejecuciones y temporales obsoletos; originales, modelos e informes protegidos.',
        }

    async def vigilar(self, detener: asyncio.Event) -> None:
        """La espera se interrumpe al apagar la web; no crea un hilo huérfano."""
        while not detener.is_set():
            await asyncio.to_thread(self.revisar_si_vence)
            try:
                await asyncio.wait_for(detener.wait(), timeout=60)
            except TimeoutError:
                pass

    def revisar_si_vence(self) -> dict | None:
        with self._lock:
            estado = self.estado()
            if estado['proxima_revision'] and self.ahora() < estado['proxima_revision']:
                return None
            resultado = self.jobs.mantenimiento_si_libre(self._revisar)
            return resultado if resultado is not None else {'estado': 'aplazada', 'motivo': 'Hay trabajos en cola o en curso.'}

    def _sin_redireccion(self, path: Path) -> bool:
        """Comprueba todos los componentes antes de resolver o recorrer la ruta."""
        try:
            relative = path.absolute().relative_to(self.root)
            current = self.root
            if self.root.is_symlink():
                return False
            for part in relative.parts:
                current = current / part
                s = current.lstat()
                if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 1024:
                    return False
            return path.resolve().is_relative_to(self.root) and path.resolve() != self.root
        except (ValueError, OSError):
            return False

    def _referencias(self) -> tuple[list, set[str], set[str]]:
        espacios, runs, rutas = [], set(), set()

        def recoger(value):
            if isinstance(value, dict):
                for item in value.values():
                    recoger(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    recoger(item)
            elif isinstance(value, str):
                runs.update(RUN_EN_TEXTO.findall(value))
                if Path(value).is_absolute():
                    rutas.add(os.path.normcase(os.path.abspath(value)))

        for folder in self.root.iterdir() if self.root.exists() else ():
            if not re.fullmatch('[a-f0-9]{16}', folder.name):
                continue
            if not self._sin_redireccion(folder):
                raise ValueError(f'Espacio con redirección o inaccesible: {folder.name}')
            for name in ('workspace.json', 'conversiones.json'):
                p = folder / name
                if p.exists():
                    if not self._sin_redireccion(p):
                        raise ValueError(f'Metadatos con redirección: {p}')
                    data = json.loads(p.read_text(encoding='utf-8'))
                    if not isinstance(data, dict):
                        raise ValueError(f'Metadatos no válidos: {p}')
                    # 086:RF-6: guardadas son relativas; sin esto, un temporal en uso parecería libre.
                    recoger(expandir_rutas(data, folder))
            ws = self.store.get(folder.name)
            if ws is None:
                raise ValueError(f'No se pudo leer el espacio: {folder.name}')
            with ws.lock:
                for name in ('active_run_id', 'loaded_run_id', 'reconstruction_run_id',
                             'plans', 'cargas_planes', 'conversions', 'demanda', 'informes', 'inputs'):
                    recoger(getattr(ws, name, None))
            espacios.append(ws)
        return espacios, runs, rutas

    def _arbol(self, path: Path) -> list[Path]:
        pending, items = [path], []
        while pending:
            current = pending.pop()
            if not self._sin_redireccion(current):
                raise ValueError(f'Ruta con redirección o inaccesible: {current}')
            items.append(current)
            if current.is_dir():
                pending.extend(current.iterdir())
        return items

    def _revisar(self) -> dict:
        ahora = self.ahora()
        report = {'estado': 'completada', 'iniciada': ahora, 'terminada': ahora,
                  'eliminados': [], 'conservados': [], 'errores': [], 'bytes_logicos_retirados': 0}
        try:
            if self.path.parent.exists() and (not self.path.parent.is_dir() or not self._sin_redireccion(self.path.parent)):
                raise ValueError('No se puede custodiar el resumen de limpieza en esa carpeta')
            espacios, referidos, rutas = self._referencias()
            for ws in espacios:
                with ws.lock:
                    runs = ws.root / 'runs'
                    if runs.exists():
                        if not self._sin_redireccion(runs):
                            raise ValueError(f'Carpeta de ejecuciones con redirección: {runs}')
                        for run in sorted(runs.iterdir()):
                            if not valid_run_id(run.name):
                                continue
                            try:
                                if run.name in referidos:
                                    report['conservados'].append({'ruta': str(run), 'motivo': 'referencia vigente'})
                                    continue
                                items = self._arbol(run)
                                manifest = json.loads((run / 'source_manifest.json').read_text(encoding='utf-8'))
                                if manifest.get('run_id') != run.name or manifest.get('mode') not in ('txt', 'mdb', 'vnr'):
                                    raise ValueError(f'Ejecución no reconocida: {run}')
                                if any(es_valioso(p) for p in items if p.is_file()):
                                    report['conservados'].append({'ruta': str(run), 'motivo': 'modelo o informe'})
                                    continue
                                if any(p.stat().st_mtime >= ahora - 7 * 86400 for p in items):
                                    report['conservados'].append({'ruta': str(run), 'motivo': 'actividad en los últimos siete días'})
                                    continue
                                size = sum(p.stat().st_size for p in items if p.is_file())
                                # El árbol completo y su ruta absoluta se validaron antes del borrado.
                                shutil.rmtree(run)
                                report['eliminados'].append(str(run))
                                report['bytes_logicos_retirados'] += size
                            except (OSError, ValueError, TypeError, AttributeError) as exc:
                                report['errores'].append(str(exc))
                    for folder in (ws.root / 'tmp', ws.inputs_dir / '_auto'):
                        if not folder.exists():
                            continue
                        if not self._sin_redireccion(folder):
                            raise ValueError(f'Temporales con redirección: {folder}')
                        for p in folder.iterdir():
                            if not self._sin_redireccion(p):
                                report['errores'].append(f'Temporal con redirección: {p}')
                                continue
                            if not p.is_file() or os.path.normcase(os.path.abspath(p)) in rutas or es_valioso(p):
                                continue
                            if p.stat().st_mtime < ahora - 7 * 86400:
                                size = p.stat().st_size
                                p.unlink()
                                report['eliminados'].append(str(p))
                                report['bytes_logicos_retirados'] += size
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            report['errores'].append(str(exc))
        report['terminada'] = self.ahora()
        from ..runtime_paths import revisar_temporales_runtime

        report['temporales_externos'] = revisar_temporales_runtime(ahora=self.ahora())
        for result in report['temporales_externos']:
            report['errores'].extend(str(item) for item in result['errores'])
        report['estado'] = 'incompleta' if report['errores'] else 'completada'
        for campo in ('eliminados', 'conservados', 'errores'):
            report[f'total_{campo}'] = len(report[campo])
            report[campo] = report[campo][-200:]
        try:
            # Un único resumen sustituido atómicamente: la limpieza no genera otro histórico ilimitado.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self._sin_redireccion(self.path.parent):
                raise ValueError('Carpeta de resumen con redirección')
            from ..util import write_json_atomic

            write_json_atomic(self.path, report)
        except (OSError, ValueError) as exc:
            report['errores'].append(str(exc))
            report['estado'] = 'incompleta'
            report['total_errores'] = len(report['errores'])
            logging.getLogger(__name__).error('No se pudo guardar la revisión de retención: %s', exc)
        self._ultimo_en_memoria = report
        return report
