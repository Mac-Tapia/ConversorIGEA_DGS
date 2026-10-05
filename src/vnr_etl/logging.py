"""Registro estructurado (sección 23 de VNR-GIS.md).

Cada evento lleva ``run_id, timestamp, source, object_type, source_id, stage,
severity, code, message``. El Registro se puede emitir a stdout, a un fichero
JSONL o recogerse en una lista (para las pruebas y la web).
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO


@dataclass
class LogEvent:
    run_id: str
    timestamp: float
    source: str
    object_type: str
    source_id: str
    stage: str
    severity: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


class EventSink:
    """Destino de los eventos del Registro."""

    def emit(self, event: LogEvent) -> None:  # pragma: no cover - abstracto
        raise NotImplementedError


class StreamSink(EventSink):
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def emit(self, event: LogEvent) -> None:
        print(
            f'{time.strftime("%H:%M:%S", time.localtime(event.timestamp))} '
            f'[{event.stage}:{event.severity}] {event.code} '
            f'{event.object_type}:{event.source_id} {event.message}',
            file=self.stream,
        )


class JsonlSink(EventSink):
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: LogEvent) -> None:
        with self.path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(event.as_dict(), ensure_ascii=False) + '\n')


class MemorySink(EventSink):
    def __init__(self) -> None:
        self.events: list[LogEvent] = []

    def emit(self, event: LogEvent) -> None:
        self.events.append(event)


class Logger:
    """Escribe a uno o varios destinos con un ``run_id`` común por ejecución."""

    def __init__(self, run_id: str | None = None, sinks: list[EventSink] | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.sinks = sinks or [StreamSink()]

    def log(
        self,
        source: str,
        object_type: str,
        source_id: str,
        stage: str,
        severity: str,
        code: str,
        message: str,
    ) -> None:
        event = LogEvent(
            run_id=self.run_id,
            timestamp=time.time(),
            source=source,
            object_type=object_type,
            source_id=source_id,
            stage=stage,
            severity=severity,
            code=code,
            message=message,
        )
        for sink in self.sinks:
            sink.emit(event)

    # --- atajos -----------------------------------------------------------
    def info(self, stage: str, code: str, message: str, *,
             source: str = '', object_type: str = '', source_id: str = '') -> None:
        self.log(source, object_type, source_id, stage, 'info', code, message)

    def warning(self, stage: str, code: str, message: str, *,
                source: str = '', object_type: str = '', source_id: str = '') -> None:
        self.log(source, object_type, source_id, stage, 'warning', code, message)

    def error(self, stage: str, code: str, message: str, *,
              source: str = '', object_type: str = '', source_id: str = '') -> None:
        self.log(source, object_type, source_id, stage, 'error', code, message)