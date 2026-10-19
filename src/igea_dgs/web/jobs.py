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
from pathlib import Path
from typing import Any, Callable

LANES = ('engine', 'powerfactory')

QUEUED = 'queued'
RUNNING = 'running'
DONE = 'done'
FAILED = 'failed'
CANCELLED = 'cancelled'
FINISHED = (DONE, FAILED, CANCELLED)



#: Código con que ``run_process`` informa de un guion terminado por pasar su límite de
#: tiempo (spec 011, RF-40); el mismo que usa ``timeout`` de coreutils.
TIEMPO_AGOTADO = 124

#: Tiempo para que un guion de PowerFactory escriba su primera línea, que sale cuando
#: DIgSILENT ya ha dado el usuario (spec 005, RF-21). El arranque normal medido el
#: 2026-10-14 fue de unos 20 s; el margen cubre un equipo frío o la licencia lenta.
LIMITE_ARRANQUE_PF_S = 180.0


class JobCancelled(Exception):
    """El operador canceló el trabajo."""


class PowerFactorySinRespuesta(RuntimeError):
    """Un guion de PowerFactory no llegó a conectar en ``LIMITE_ARRANQUE_PF_S``."""


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
    # Ver ``JobContext.sin_retorno``: a partir de ahí, cancelar no hace nada.
    irrevocable: bool = field(default=False, repr=False)
    gate: threading.Lock = field(default_factory=threading.Lock, repr=False)

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

    def sin_retorno(self) -> None:
        """Punto sin retorno: la cancelación llega antes o ya no llega.

        Al publicar una reconstrucción se sustituye el dataset activo del espacio. Si la
        cancelación pudiera entrar después, el trabajo acabaría «cancelado» con la
        reconstrucción ya publicada, y el operador creería conservar la anterior
        (spec 001, RF-9). La comprobación y la marca van bajo el mismo cerrojo que
        ``JobManager.cancel``, así que no hay hueco entre las dos.
        """
        with self.job.gate:
            self.check_cancel()
            self.job.irrevocable = True

    def run_process(
        self, cmd: list[str], *, env: dict[str, str] | None = None, cwd: str | None = None,
        cancel_file: Path | str | None = None, limite_s: float | None = None,
        limite_arranque_s: float | None = None, _reintento: bool = False,
    ) -> int:
        """Ejecuta un guion volcando su salida al Registro **línea a línea**.

        La GUI de escritorio, ya retirada, esperaba a que terminara y lo volcaba todo: en un
        escenario base de media hora, el operador no veía nada hasta el final. Aquí
        cada línea llega al navegador en cuanto el guion la escribe.

        Al cancelar se termina el proceso. Para PowerFactory eso es seguro: los
        guiones trabajan sobre el proyecto activo, y un import cortado no deja un DGS
        a medias en la carpeta de salida porque el DGS ya estaba escrito.

        Con ``cancel_file`` no se mata: se crea el fichero y se espera a que el guion
        acabe el alimentador en curso y salga, y se devuelve su código. Matarlo dejaba un
        alimentador con la mitad de sus cargas escritas en la variación (spec 004, RF-19).

        Con ``limite_s``, un guion que pasa ese tiempo se termina y se devuelve
        ``TIEMPO_AGOTADO``: un estudio de contingencias colgado cuesta ese estudio, no el
        trabajo entero (spec 011, RF-39, RF-40).

        Con ``limite_arranque_s``, un guion que en ese tiempo no ha escrito ni una línea se
        termina y se devuelve ``TIEMPO_AGOTADO`` (spec 005, RF-21). El 2026-10-14, tras
        reiniciar la web con sesiones de PowerFactory cortadas, «Leer proyectos» se quedó
        parado en ``GetCurrentUser`` sin escribir nada, y el carril de PowerFactory —con
        todos sus botones— quedó ocupado sin aviso hasta matar el proceso a mano.
        Todo guion de PowerFactory lleva ese límite aunque quien lo lanza no lo pida: el
        mismo cuelgue en el flujo, las cargas o el ajuste dejaba el carril igual de
        ocupado. Si quien lo lanza no lo pidió, el corte es un error con su motivo en vez
        de un código que no esperaba.
        """
        import os

        full_env = dict(env if env is not None else os.environ)
        # Sin esto Python hace búfer de la salida del hijo y las líneas llegan en
        # bloques de 8 KB; y en Windows la consola por defecto no es UTF-8.
        full_env.setdefault('PYTHONUNBUFFERED', '1')
        full_env.setdefault('PYTHONIOENCODING', 'utf-8')
        es_pf = 'PF_PYTHON' in full_env
        limite_implicito = es_pf and limite_arranque_s is None
        if limite_implicito:
            limite_arranque_s = LIMITE_ARRANQUE_PF_S
        if es_pf:
            from ..powerfactory_env import cerrar_guiones_pf_huerfanos

            for h in cerrar_guiones_pf_huerfanos():
                self.log(f"Se cierra un guion de PowerFactory de una sesión anterior que "
                         f"seguía vivo (proceso {h['pid']}): {h['cmd']}")
        # 019:RF-7: un guion de DIgSILENT va al proceso que se queda abierto, por medio de
        # ``tools/pf_cliente.py``, que reescribe su salida y devuelve su código: lo demás
        # (primera línea, cancelación, límites) sigue igual. ``IGEA_PF_SERVIDOR=0`` lo apaga.
        # El reintento parte de la orden tal como llegó: reescrita al cliente, ya no se
        # reconocía como guion servible y el segundo corte dejaba el servidor colgado.
        original = cmd
        orden = None
        if es_pf and full_env.get('IGEA_PF_SERVIDOR', '1') != '0' and len(cmd) > 1:
            from ..pf_arnes import GUIONES_SERVIBLES, VARIABLE_ORDEN

            if Path(cmd[1]).name in GUIONES_SERVIBLES:
                cmd = [cmd[0], str(Path(cmd[1]).with_name('pf_cliente.py')), *cmd[1:]]
                # 019:RF-20: la orden lleva un nombre conocido para cortar solo la suya.
                orden = uuid.uuid4().hex[:12]
                full_env[VARIABLE_ORDEN] = orden

        def cortar() -> None:
            self._terminar(proc)
            if orden is not None:
                # 019:RF-8, RF-9, RF-20: se retira la orden de la cola y, si el servidor la
                # atendía o sigue sin conectar, se cierra; si atiende la de otro, sigue.
                from ..pf_arnes import cerrar_servidor

                if cerrar_servidor(orden):
                    self.log('Se cierra el proceso de DIgSILENT que atendía la orden.')

        self.log('$ ' + ' '.join(cmd))
        # Sin consola de entrada: una pregunta del guion o de PowerFactory recibe EOF y
        # falla, en vez de esperar una respuesta que nadie puede dar desde la web.
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', env=full_env, cwd=cwd,
        )
        primera_linea = threading.Event()

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                primera_linea.set()
                self.log(line.rstrip('\r\n'))

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        avisado = False
        inicio = time.monotonic()
        while proc.poll() is None:
            transcurrido = time.monotonic() - inicio
            sin_arrancar = (limite_arranque_s is not None and not primera_linea.is_set()
                            and transcurrido > limite_arranque_s)
            if sin_arrancar or (limite_s is not None and transcurrido > limite_s):
                self.log(f'El guion no escribió nada en {limite_arranque_s:g} s: se termina.'
                         if sin_arrancar else
                         f'El guion pasó su límite de {limite_s:g} s: se termina.')
                cortar()
                reader.join(timeout=5)
                if es_pf and sin_arrancar:
                    from ..powerfactory_env import powerfactory_abierto

                    for pid in powerfactory_abierto():
                        self.log(f'PowerFactory está abierto (proceso {pid}) y tiene el '
                                 'usuario de DIgSILENT: ciérrelo y reintente.')
                if limite_implicito and sin_arrancar and not _reintento:
                    # Sin conectar, el guion no ha escrito nada: repetirlo es seguro. El
                    # 2026-10-14, 3 de 15 conexiones se quedaron paradas sin causa a la
                    # vista y las tres conectaron al primer reintento.
                    self.log('Se reintenta una vez: DIgSILENT a veces no entrega el '
                             'usuario a la primera.')
                    self.check_cancel()
                    return self.run_process(original, env=env, cwd=cwd, cancel_file=cancel_file,
                                            limite_s=limite_s, _reintento=True)
                if limite_implicito and sin_arrancar:
                    raise PowerFactorySinRespuesta(
                        f'DIgSILENT no respondió en {limite_arranque_s:g} s: no entregó el '
                        'usuario. Cierre la ventana de PowerFactory si está abierta o '
                        'compruebe la licencia, y reintente.')
                return TIEMPO_AGOTADO
            # Un guion que aún no ha escrito nada no ha conectado ni empezado ningún
            # alimentador: con el fichero de cancelación esperaría a que conecte, y si
            # está colgado en la conexión, el botón Cancelar no haría nada.
            if (self.job.cancel.is_set() and cancel_file is not None
                    and primera_linea.is_set()):
                if not avisado:
                    Path(cancel_file).parent.mkdir(parents=True, exist_ok=True)
                    Path(cancel_file).write_text('cancelar\n', encoding='utf-8')
                    self.log('Cancelación pedida: se termina el alimentador en curso '
                             'y no se empieza otro.')
                    avisado = True
            elif self.job.cancel.is_set():
                cortar()
                reader.join(timeout=5)
                raise JobCancelled()
            time.sleep(0.2)
        reader.join(timeout=5)
        return proc.returncode

    @staticmethod
    def _terminar(proc: subprocess.Popen) -> None:
        """Termina el guion y sus hijos: el lanzador del venv deja vivo al Python real."""
        from ..powerfactory_env import terminar_arbol

        try:
            terminar_arbol(proc.pid)
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


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
        # Copia bajo el cerrojo: las peticiones llegan en hilos distintos y recorrer el
        # diccionario mientras otra encola un trabajo lanza «changed size during iteration».
        with self._lock:
            todos = list(self._jobs.values())
        jobs = [j for j in todos
                if workspace_id is None or j.workspace_id == workspace_id]
        return sorted(jobs, key=lambda j: j.created_at)

    def active(self, workspace_id: str) -> list[Job]:
        return [j for j in self.list(workspace_id) if j.status not in FINISHED]

    def en_curso(self) -> int:
        """Trabajos sin terminar en todos los espacios: el lanzador no cierra un servidor con ellos."""
        return sum(1 for j in self.list() if j.status not in FINISHED)

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
        with job.gate:
            if job.irrevocable:
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
