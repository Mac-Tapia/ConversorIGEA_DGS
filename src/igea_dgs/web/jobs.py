"""Trabajos largos fuera de la petición HTTP, con progreso y cancelación.

Una conversión de 96 alimentadores o un escenario base sobre 53.000 barras no caben
en una petición. Se encolan aquí y el navegador sigue su avance por WebSocket.

Hay **dos carriles**, cada uno con un único hilo que atiende su cola en orden:

* ``engine`` — el motor en este proceso: leer TXT, convertir, auditar. Es CPU pura;
  dos a la vez solo se estorbarían, y compartirían el mismo dataset en memoria.
* ``powerfactory`` — guiones que hablan con DIgSILENT. PowerFactory admite **un solo
  proceso con el motor a la vez**: si dos guiones lo intentan, el segundo falla con
  un error que no dice por qué. Serializarlos aquí es lo que lo evita.

Separarlos permite seguir convirtiendo mientras PowerFactory importa la red unida, que
son minutos. La cola es de este proceso: si hiciera falta repartir el trabajo entre
máquinas (el *worker* de PowerFactory en Windows y el resto en contenedores), este
módulo es el que se sustituye por Redis/RQ sin tocar las rutas de la API.
"""

from __future__ import annotations

import itertools
import queue
import subprocess
import threading
import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

LANES = ('engine', 'powerfactory')

QUEUED = 'queued'
RUNNING = 'running'
DONE = 'done'
FAILED = 'failed'
CANCELLED = 'cancelled'
FINISHED = (DONE, FAILED, CANCELLED)


class JobCancelled(Exception):
    """El operador canceló el trabajo."""


class EventLog:
    """Registro de eventos numerados de un espacio de trabajo.

    El navegador pide «lo que haya después del número N», así que una reconexión del
    WebSocket no pierde líneas ni las duplica. Se acota para que un lote de 96
    alimentadores no crezca sin límite en memoria.
    """

    def __init__(self, maxlen: int = 5000) -> None:
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._seq = itertools.count(1)
        self._last = 0
        self._cond = threading.Condition()

    @property
    def last_seq(self) -> int:
        return self._last

    def append(self, kind: str, data: dict) -> dict:
        with self._cond:
            seq = next(self._seq)
            event = {'seq': seq, 'ts': time.time(), 'type': kind, 'data': data}
            self._events.append(event)
            self._last = seq
            self._cond.notify_all()
            return event

    def since(self, seq: int) -> list[dict]:
        with self._cond:
            return [e for e in self._events if e['seq'] > seq]

    def wait(self, seq: int, timeout: float) -> list[dict]:
        """Bloquea hasta que haya eventos posteriores a ``seq`` o venza el plazo."""
        with self._cond:
            if self._last <= seq:
                self._cond.wait(timeout)
            return [e for e in self._events if e['seq'] > seq]


@dataclass
class Job:
    kind: str
    title: str
    workspace_id: str
    lane: str
    fn: Callable[['JobContext'], Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = QUEUED
    progress: dict | None = None
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {
            'id': self.id,
            'kind': self.kind,
            'title': self.title,
            'workspace_id': self.workspace_id,
            'lane': self.lane,
            'status': self.status,
            'progress': self.progress,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'cancel_requested': self.cancel.is_set(),
        }


Emit = Callable[[str, str, dict], None]
"""``emit(workspace_id, tipo, datos)``: publica un evento en el registro del espacio."""


class JobContext:
    """Lo que un trabajo puede hacer: escribir en el Registro, avanzar, cancelarse."""

    def __init__(self, job: Job, emit: Emit) -> None:
        self.job = job
        self._emit = emit

    @property
    def cancel(self) -> threading.Event:
        return self.job.cancel

    def log(self, text: str) -> None:
        if text:
            self._emit(self.job.workspace_id, 'log', {'job': self.job.id, 'text': text})

    def progress(self, index: int, total: int, label: str = '') -> None:
        self.job.progress = {'index': index, 'total': total, 'label': label}
        self._emit(self.job.workspace_id, 'job', self.job.public())

    def check_cancel(self) -> None:
        if self.job.cancel.is_set():
            raise JobCancelled()

    def run_process(
        self, cmd: list[str], *, env: dict[str, str] | None = None, cwd: str | None = None,
        cancel_file: str | None = None,
    ) -> int:
        """Ejecuta un guion volcando su salida al Registro **línea a línea**.

        La implementación anterior esperaba al final para volcar toda la salida: en un
        escenario base de media hora, el operador no veía nada. Aquí
        cada línea llega al navegador en cuanto el guion la escribe.

        Al cancelar se termina el proceso. Para PowerFactory eso es seguro: los
        guiones trabajan sobre el proyecto activo, y un import cortado no deja un DGS
        a medias en la carpeta de salida porque el DGS ya estaba escrito.
        """
        import os

        full_env = dict(env if env is not None else os.environ)
        # Sin esto Python hace búfer de la salida del hijo y las líneas llegan en
        # bloques de 8 KB; y en Windows la consola por defecto no es UTF-8.
        full_env.setdefault('PYTHONUNBUFFERED', '1')
        full_env.setdefault('PYTHONIOENCODING', 'utf-8')
        self.log('$ ' + ' '.join(cmd))
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding='utf-8', errors='replace', env=full_env, cwd=cwd,
        )

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                self.log(line.rstrip('\r\n'))

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        cooperative_cancel_sent = False
        while proc.poll() is None:
            if self.job.cancel.is_set():
                if cancel_file:
                    if not cooperative_cancel_sent:
                        from pathlib import Path

                        Path(cancel_file).write_text('cancel\n', encoding='utf-8')
                        cooperative_cancel_sent = True
                else:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    reader.join(timeout=5)
                    raise JobCancelled()
            time.sleep(0.2)
        reader.join(timeout=5)
        return proc.returncode


class JobManager:
    def __init__(self, emit: Emit) -> None:
        self._emit = emit
        self._jobs: dict[str, Job] = {}
        self._queues = {lane: queue.Queue() for lane in LANES}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._closing = False

    # -------------------------------------------------------------- consultas
    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, workspace_id: str | None = None) -> list[Job]:
        jobs = [j for j in self._jobs.values()
                if workspace_id is None or j.workspace_id == workspace_id]
        return sorted(jobs, key=lambda j: j.created_at)

    def active(self, workspace_id: str) -> list[Job]:
        return [j for j in self.list(workspace_id) if j.status not in FINISHED]

    # -------------------------------------------------------------- acciones
    def submit(
        self, workspace_id: str, kind: str, title: str,
        fn: Callable[[JobContext], Any], *, lane: str = 'engine',
    ) -> Job:
        if lane not in LANES:
            raise ValueError(f'carril desconocido: {lane}')
        if self._closing:
            raise RuntimeError('el servidor se está cerrando')
        job = Job(kind=kind, title=title, workspace_id=workspace_id, lane=lane, fn=fn)
        with self._lock:
            self._jobs[job.id] = job
            self._ensure_worker(lane)
        self._emit(workspace_id, 'job', job.public())
        self._queues[lane].put(job)
        return job

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.status in FINISHED:
            return job
        job.cancel.set()
        if job.status == QUEUED:
            # Aún no empezó: se da por cancelado ya; el hilo lo saltará al sacarlo.
            self._finish(job, CANCELLED)
        else:
            self._emit(job.workspace_id, 'job', job.public())
        return job

    def shutdown(self, timeout_s: float = 30.0) -> None:
        """Cancela lo pendiente y espera a que lo que corre cierre limpio.

        Es la misma regla que el cierre de la ventana de escritorio: matar el hilo a
        mitad de un alimentador dejaba ficheros truncados indistinguibles de válidos.
        El motor, al ver la cancelación, descarta el alimentador en curso entero.
        """
        self._closing = True
        for job in list(self._jobs.values()):
            if job.status not in FINISHED:
                self.cancel(job.id)
        for lane in LANES:
            self._queues[lane].put(None)
        deadline = time.time() + timeout_s
        for thread in self._threads.values():
            thread.join(timeout=max(0.0, deadline - time.time()))

    # -------------------------------------------------------------- interno
    def _ensure_worker(self, lane: str) -> None:
        thread = self._threads.get(lane)
        if thread is not None and thread.is_alive():
            return
        thread = threading.Thread(target=self._worker, args=(lane,),
                                  name=f'igea-{lane}', daemon=True)
        self._threads[lane] = thread
        thread.start()

    def _worker(self, lane: str) -> None:
        q = self._queues[lane]
        while True:
            job = q.get()
            if job is None:
                return
            if job.status != QUEUED:
                continue
            self._run(job)

    def _run(self, job: Job) -> None:
        job.status = RUNNING
        job.started_at = time.time()
        self._emit(job.workspace_id, 'job', job.public())
        ctx = JobContext(job, self._emit)
        try:
            job.result = job.fn(ctx)
        except JobCancelled:
            ctx.log(f'--- {job.title}: cancelado ---')
            self._finish(job, CANCELLED)
            return
        except Exception as exc:  # noqa: BLE001 - borde: el trabajo informa, no tumba el hilo
            job.error = str(exc) or exc.__class__.__name__
            ctx.log(traceback.format_exc())
            self._finish(job, FAILED)
            return
        # Un lote cancelado devuelve igual su manifiesto: se conserva como resultado.
        self._finish(job, CANCELLED if job.cancel.is_set() else DONE)

    def _finish(self, job: Job, status: str) -> None:
        job.status = status
        job.finished_at = time.time()
        self._emit(job.workspace_id, 'job', job.public())
