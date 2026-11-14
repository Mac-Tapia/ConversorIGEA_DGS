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
import json
import logging
import math
import os
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

#: «asistente» (spec 026) solo espera: sus pasos encolan en los otros dos carriles, así que
#: no compite con ellos por el motor ni por DIgSILENT.
#: 070:RF-33: «control» solo atiende órdenes de cancelar: con el carril del asistente ocupado la ruta da 409,
#: y es justo entonces cuando el operador quiere parar lo que corre (un «Recalibrar» de horas).
LANES = ('engine', 'powerfactory', 'asistente', 'control')

QUEUED = 'queued'
RUNNING = 'running'
DONE = 'done'
FAILED = 'failed'
CANCELLED = 'cancelled'
#: 081:RF-17, RF-18: terminó con resultado, y no todo quedó bien; un trabajo los pide con
#: ``estado_trabajo`` en su resultado. «done» solo decía que no hubo excepción: una calibración
#: con 17 alimentadores sin converger salía «done».
PARCIAL = 'parcial'
NO_CONVERGE = 'no_converge'
#: 086:RF-9: el servidor se detuvo con el trabajo a medias; solo sale de leer el diario al arrancar.
INTERRUMPIDO = 'interrumpido'
CON_RESULTADO = (DONE, PARCIAL, NO_CONVERGE)
FINISHED = (*CON_RESULTADO, FAILED, CANCELLED, INTERRUMPIDO)

#: Registro de un trabajo en su diario; un guion muy hablador no llena el disco por esto.
LIMITE_REGISTRO_BYTES = 50 * 2**20
#: Cada cuánto se sincroniza el registro y el avance: un corte de luz pierde a lo sumo esto.
INTERVALO_DIARIO_S = 2.0
#: 096:RF-2: menos que esto suspendido no cuenta (un parpadeo del reloj no es una suspensión).
SUSPENSION_MINIMA_S = 5.0
#: Últimos del residuo seguro; las identidades y cadenas protegidas quedan fuera de esta cap.
MAX_INTERRUMPIDOS = 50


#: Código con que ``run_process`` informa de un guion terminado por pasar su límite de
#: tiempo (spec 011, RF-40); el mismo que usa ``timeout`` de coreutils.
TIEMPO_AGOTADO = 124

#: Tiempo para que un guion de PowerFactory escriba su primera línea, que sale cuando
#: DIgSILENT ya ha dado el usuario (spec 005, RF-21). El arranque normal medido el
#: 2026-10-14 fue de unos 20 s; el margen cubre un equipo frío o la licencia lenta.
LIMITE_ARRANQUE_PF_S = 180.0


class MemoriaExcedida(RuntimeError):
    """Un trabajo del motor en su proceso pasó el límite de memoria (027:RF-27)."""


#: Límite de memoria de un trabajo del motor en su proceso, en MB (027:RF-27); se cambia con
#: ``CSG_LIMITE_MEMORIA_MB``. Con Nasca (2026-10-27) la web se quedó sin memoria al abrir
#: varias copias de los .xls de cabecera de ~400 MB.
LIMITE_MEMORIA_MB = 6000


def limite_memoria_mb() -> float:
    try:
        return float(os.environ.get('CSG_LIMITE_MEMORIA_MB') or LIMITE_MEMORIA_MB)
    except ValueError:
        return float(LIMITE_MEMORIA_MB)


def _en_hijo(fn, args, kwargs, cola, cancelado) -> None:
    """Lo que corre en el proceso del trabajo: la función con su avance y su Registro."""
    try:
        res = fn(*args, progreso=lambda i, n, m='': cola.put(('progreso', (i, n, m))),
                 log=lambda texto: cola.put(('log', texto)), cancelado=cancelado.is_set, **kwargs)
        cola.put(('fin', res))
    except BaseException as exc:  # noqa: BLE001 - el padre lo vuelve a lanzar
        try:
            cola.put(('error', exc))
        except Exception:  # noqa: BLE001 - excepción que no se puede enviar
            cola.put(('error', RuntimeError(f'{type(exc).__name__}: {exc}')))


#: 086:RF-86: trabajos que corren solos. La copia de los datos guardaba una mezcla de antes y de después si otro
#: trabajo escribía a la vez; la ruta de la web lo comprobaba, pero VNR-GIS y los reintentos de la vigilancia
#: encolan sin pasar por ella, y entre la comprobación y el encolado podía entrar otro. Lo decide la cola.
EXCLUSIVOS = frozenset({'copia_datos'})


class TrabajoRechazado(RuntimeError):
    """La cola no admite el trabajo mientras corre uno exclusivo, ni uno exclusivo con otros en curso (086:RF-86)."""


class JobCancelled(Exception):
    """El operador canceló el trabajo."""


class PowerFactorySinRespuesta(RuntimeError):
    """Un guion de PowerFactory no llegó a conectar en ``LIMITE_ARRANQUE_PF_S``."""


def _es_sin_gpu(exc: BaseException) -> bool:
    """Si el trabajo falló por no haber GPU CUDA, o por pedir en el instalado lo que es de desarrollo (086:RF-15):
    se avisa sin traza, porque no es un fallo del programa."""
    from ..edicion import SoloDesarrollo
    from ..training_coordinator import SinGPU

    return isinstance(exc, (SinGPU, SoloDesarrollo))


class EventLog:
    """Registro de eventos numerados de un espacio de trabajo.

    El navegador pide «lo que haya después del número N», así que una reconexión del
    WebSocket no pierde líneas ni las duplica. Se acota para que un lote de 96
    alimentadores no crezca sin límite en memoria.
    """

    def __init__(self, maxlen: int = 5000) -> None:
        self._events: deque[dict] = deque(maxlen=maxlen)
        # 086:RF-9: la numeración sigue creciendo entre arranques. Empezaba en 1 en cada proceso, y una pestaña
        # abierta que volvía con ``since=67`` no veía nada hasta que el servidor nuevo pasaba de 67 eventos.
        # Un proceso no escribe más de un evento por microsegundo vivido: el siguiente siempre empieza por encima.
        # Y en microsegundos cabe entero en un número de JavaScript, que llega a 2^53.
        self._last = int(time.time() * 1_000_000)
        self._seq = itertools.count(self._last + 1)
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
    # 096:RF-5: la petición con que se puede repetir tras caer la web ({'tipo': ..., 'datos': ...}), o None.
    reanudar: dict | None = None
    # 096:RF-6, RF-7: el interrumpido del que viene, y si este ya se relanzó.
    relanzado_de: str | None = None
    relanzado: bool = False
    # 096:RF-6: el servidor puede morir antes que su trabajador; el PID solo se reutiliza.
    proceso: dict | None = None
    # 096:RF-4/6: una instantánea vieja no puede publicarse después de cancelar o finalizar.
    diario_gate: Any = field(default_factory=threading.RLock, repr=False, compare=False)

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

    def __init__(self, job: Job, emit: Emit, diario: 'DiarioTrabajos | None' = None) -> None:
        self.job = job
        self._emit = emit
        self._diario = diario

    @property
    def cancel(self) -> threading.Event:
        return self.job.cancel

    def log(self, text: str) -> None:
        if text:
            if self._diario is not None:
                self._diario.linea(self.job.id, text)
            self._emit(self.job.workspace_id, 'log', {'job': self.job.id, 'text': text})

    def progress(self, index: int, total: int, label: str = '') -> None:
        self.job.progress = {'index': index, 'total': total, 'label': label}
        if self._diario is not None:
            self._diario.avance(self.job)
        self._emit(self.job.workspace_id, 'job', self.job.public())

    def check_cancel(self) -> None:
        if self.job.cancel.is_set():
            raise JobCancelled()

    def anotar_proceso(self, pid: int) -> None:
        """096:RF-6: registrar inmediatamente el Popen propio para impedir un relanzamiento simultáneo."""
        self.job.proceso = {'pid': pid, 'inicio': inicio_de_proceso(pid)}
        if self._diario is not None:
            self._diario.anotar(self.job)

    def _reservar_proceso(self) -> None:
        # 096:RF-6: si el servidor muere tras spawn y antes del PID, queda una identidad incierta, no permiso.
        self.job.proceso = {'estado': 'lanzando'}
        if self._diario is not None and not self._diario.anotar(self.job):
            raise OSError('No se pudo guardar la reserva del proceso; no se crea un trabajador sin diario durable.')

    def _retirar_reserva(self) -> None:
        self.job.proceso = None
        if self._diario is not None:
            self._diario.anotar(self.job)

    def en_proceso(self, fn: Callable[..., Any], *args: Any, limite_mb: float | None = None,
                   **kwargs: Any) -> Any:
        """Ejecuta ``fn`` (de nivel superior, con argumentos que se puedan enviar) en un proceso
        aparte y devuelve su resultado (027:RF-25 a RF-27).

        Leer los libros de cabecera dentro del proceso de la API se llevaba el GIL y la memoria:
        con Chincha, ``/api/health`` tardaba segundos y Nasca agotó la memoria (2026-10-27).
        ``fn`` recibe ``progreso``, ``log`` y ``cancelado``, que llegan al Registro y a la
        cancelación de este trabajo. Si su proceso pasa de ``limite_mb``, se termina con
        :class:`MemoriaExcedida`; la API sigue.
        """
        import multiprocessing as mp

        limite = float(limite_mb if limite_mb is not None else limite_memoria_mb())
        ctx = mp.get_context('spawn')
        cola = ctx.Queue()
        cancelado = ctx.Event()
        proc = ctx.Process(target=_en_hijo, args=(fn, args, kwargs, cola, cancelado), daemon=True,
                           name=f'csg-motor-{self.job.id}')
        self._reservar_proceso()
        try:
            proc.start()
        except BaseException:
            self._retirar_reserva()
            raise
        self.anotar_proceso(proc.pid)
        try:
            import psutil

            vigilado = psutil.Process(proc.pid)
        except Exception:  # noqa: BLE001 - sin psutil no hay límite de memoria
            vigilado = None
        try:
            while True:
                try:
                    tipo, dato = cola.get(timeout=0.2)
                except queue.Empty:
                    tipo = None
                if tipo == 'fin':
                    return dato
                if tipo == 'error':
                    raise dato
                if tipo == 'log':
                    self.log(dato)
                elif tipo == 'progreso':
                    self.progress(*dato)
                if self.cancel.is_set():
                    cancelado.set()
                if vigilado is not None:
                    try:
                        mb = vigilado.memory_info().rss / 2**20
                    except Exception:  # noqa: BLE001 - el proceso ya terminó
                        mb = 0.0
                    if mb > limite:
                        proc.kill()
                        raise MemoriaExcedida(f'el trabajo usó {mb:,.0f} MB, más que su límite de '
                                              f'{limite:,.0f} MB; se detuvo y la web sigue (027:RF-27)')
                if tipo is None and not proc.is_alive() and cola.empty():
                    raise RuntimeError(f'el proceso del trabajo terminó sin resultado (código {proc.exitcode})')
        finally:
            if proc.is_alive():
                proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()

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
        # (primera línea, cancelación, límites) sigue igual. ``CSG_PF_SERVIDOR=0`` lo apaga.
        # El reintento parte de la orden tal como llegó: reescrita al cliente, ya no se
        # reconocía como guion servible y el segundo corte dejaba el servidor colgado.
        original = cmd
        orden = None
        if es_pf and full_env.get('CSG_PF_SERVIDOR', '1') != '0' and len(cmd) > 1:
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
        self._reservar_proceso()
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', env=full_env, cwd=cwd,
            )
        except BaseException:
            self._retirar_reserva()
            raise
        self.anotar_proceso(proc.pid)
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
        from ..pf_arnes import SIN_RESPUESTA

        if es_pf and proc.returncode == SIN_RESPUESTA:
            # 019:RF-25: el vigía lo terminó porque DIgSILENT no respondió al conectar; sin
            # conectar no hizo nada, y repetirlo es seguro, como sin primera línea.
            if not _reintento:
                self.log('Se reintenta una vez: DIgSILENT no respondió al conectar (019:RF-23).')
                self.check_cancel()
                return self.run_process(original, env=env, cwd=cwd, cancel_file=cancel_file,
                                        limite_s=limite_s, limite_arranque_s=None if limite_implicito
                                        else limite_arranque_s, _reintento=True)
            raise PowerFactorySinRespuesta(
                'DIgSILENT no respondió al conectar, tampoco al reintentar. Cierre la ventana de '
                'PowerFactory si está abierta o compruebe la licencia, y reintente.')
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


VARIABLE_REGISTRO = 'CSG_REGISTRO_TRABAJOS'


def registro_de_trabajos(pid: int) -> Path | None:
    """El fichero donde el servidor ``pid`` anota sus trabajos en curso (spec 001, RF-34).

    Solo lo tiene el servidor que arranca el lanzador (``CSG_REGISTRO_TRABAJOS`` con la
    carpeta): las pruebas que crean la app no escriben en la del operador.
    """
    carpeta = os.environ.get(VARIABLE_REGISTRO)
    return Path(carpeta) / f'{pid}.json' if carpeta else None


def trabajos_anotados(pid: int) -> int | None:
    """Los trabajos en curso que anotó el servidor ``pid``, o None si no anotó nada."""
    ruta = registro_de_trabajos(pid)
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8')) if ruta else None
    except (OSError, ValueError):
        return None
    return datos.get('en_curso') if isinstance(datos, dict) and datos.get('pid') == pid else None


def _estado_del_resultado(resultado: Any) -> str:
    """El estado con que termina un trabajo que no falló (081:RF-17, RF-18, RF-20)."""
    estado = resultado.get('estado_trabajo') if isinstance(resultado, dict) else None
    return estado if estado in (PARCIAL, NO_CONVERGE) else DONE


def inicio_de_proceso(pid: int) -> float | None:
    """Cuándo arrancó ``pid``, o None si ya no existe: un pid solo no basta, Windows los reutiliza."""
    try:
        import psutil

        return psutil.Process(pid).create_time()
    except Exception:  # noqa: BLE001 - ni el proceso ni psutil: se da por muerto
        return None


def proceso_pendiente(identidad: dict | None) -> bool:
    """096:RF-6: un hijo vivo o de identidad ilegible bloquea repetir; nunca se le envían señales."""
    if identidad is None:
        return False
    try:
        import psutil
    except ImportError:
        return True
    try:
        pid, inicio = identidad['pid'], identidad['inicio']
        if type(pid) is not int or pid <= 0:
            return True
        actual = psutil.Process(pid).create_time()
        if type(inicio) not in (int, float) or not math.isfinite(inicio) or inicio <= 0:
            return True
        return actual == inicio
    except psutil.NoSuchProcess:
        return False
    except (ImportError, OSError, psutil.AccessDenied, KeyError, TypeError):
        return True


class DiarioTrabajos:
    """Lo que sobrevive a un reinicio de los trabajos sin terminar (086:RF-9).

    Los trabajos vivían solo en memoria: al caer la web, una calibración de horas desaparecía, sin
    rastro de hasta dónde llegó ni de qué dijo DIgSILENT. Cada trabajo sin terminar tiene aquí
    ``<id>.json`` y ``<id>.log``. Terminado con normalidad, los borra, salvo el recibo JSON de un sucesor
    relanzado: impide volver al ancestro si el servidor muere antes de marcarlo. Su resultado y su registro ya
    están donde siempre. Un fallo del diario se avisa en el log del servidor; si impide persistir
    la reserva de lanzamiento, el trabajo falla antes de crear un hijo sin recibo durable.
    """

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self._lock = threading.Lock()
        self._ficheros: dict[str, Any] = {}
        self._sincronizado: dict[str, float] = {}
        self._avance: dict[str, float] = {}
        self._mi_pid = os.getpid()
        self._mi_inicio = inicio_de_proceso(self._mi_pid)

    def _ruta(self, job_id: str, extension: str) -> Path:
        return self.carpeta / f'{job_id}.{extension}'

    def anotar(self, job: Job) -> bool:
        from ..util import write_json_atomic

        # El cerrojo cubre la lectura de TODOS los campos y su publicación durable.
        # Bloquear solo replace permitía que un avance restaurara cancel_requested=False.
        with job.diario_gate:
            try:
                write_json_atomic(self._ruta(job.id, 'json'), {
                    'id': job.id, 'kind': job.kind, 'title': job.title, 'workspace_id': job.workspace_id,
                    'lane': job.lane, 'status': job.status, 'progress': job.progress, 'error': job.error,
                    'result': job.result,
                    'created_at': job.created_at, 'started_at': job.started_at, 'finished_at': job.finished_at,
                    'pid': self._mi_pid, 'inicio_proceso': self._mi_inicio,
                    'reanudar': job.reanudar, 'relanzado': job.relanzado,
                    'relanzado_de': job.relanzado_de, 'cancel_requested': job.cancel.is_set(),
                    'proceso': job.proceso,
                })
                return True
            except (OSError, ValueError) as exc:
                logging.getLogger(__name__).warning('Diario de trabajos sin anotar %s: %s', job.id, exc)
                return False

    def avance(self, job: Job) -> None:
        ahora = time.monotonic()
        if ahora - self._avance.get(job.id, 0.0) >= INTERVALO_DIARIO_S:
            self._avance[job.id] = ahora
            self.anotar(job)

    def linea(self, job_id: str, texto: str) -> None:
        try:
            with self._lock:
                fichero = self._ficheros.get(job_id)
                if fichero is None:
                    self.carpeta.mkdir(parents=True, exist_ok=True)
                    fichero = self._ficheros[job_id] = self._ruta(job_id, 'log').open('a', encoding='utf-8')
                if fichero.tell() >= LIMITE_REGISTRO_BYTES:
                    return
                fichero.write(texto + '\n')
                # flush: sobrevive a matar el proceso; fsync de vez en cuando: a un corte de luz.
                fichero.flush()
                ahora = time.monotonic()
                if ahora - self._sincronizado.get(job_id, 0.0) >= INTERVALO_DIARIO_S:
                    self._sincronizado[job_id] = ahora
                    os.fsync(fichero.fileno())
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).warning('Registro del trabajo %s sin escribir: %s', job_id, exc)

    def _cerrar_registro(self, job_id: str) -> None:
        with self._lock:
            fichero = self._ficheros.pop(job_id, None)
            self._sincronizado.pop(job_id, None)
            self._avance.pop(job_id, None)
        if fichero is not None:
            fichero.close()

    def terminar(self, job: Job) -> None:
        """096:RF-6: conservar el recibo final de un sucesor; el registro largo ya no hace falta."""
        with job.diario_gate:
            if not job.relanzado_de:
                self.olvidar(job.id)
                return
            if self.anotar(job):
                try:
                    self._cerrar_registro(job.id)
                    self._ruta(job.id, 'log').unlink(missing_ok=True)
                except OSError as exc:
                    logging.getLogger(__name__).warning('Registro final de %s sin retirar: %s', job.id, exc)

    def olvidar(self, job_id: str) -> None:
        """El trabajo terminó: Windows no deja borrar un fichero abierto, primero se cierra."""
        try:
            self._cerrar_registro(job_id)
            self._ruta(job_id, 'json').unlink(missing_ok=True)
            self._ruta(job_id, 'log').unlink(missing_ok=True)
        except OSError as exc:
            logging.getLogger(__name__).warning('Diario del trabajo %s sin retirar: %s', job_id, exc)

    def registro(self, job_id: str, ultimas: int = 2000) -> list[str] | None:
        """Las últimas líneas del registro, o None si este trabajo no tiene."""
        with self._lock:
            fichero = self._ficheros.get(job_id)
            if fichero is not None:
                fichero.flush()
        try:
            lineas = self._ruta(job_id, 'log').read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            return None
        return lineas[-ultimas:]

    def recuperar(self) -> list[Job]:
        """Lo que quedó a medias de un servidor anterior, como interrumpido.

        El de un servidor que sigue vivo no se toca: sigue en marcha, y marcarlo interrumpido
        sería mentira; por eso se compara también la hora de arranque del proceso.
        """
        if not self.carpeta.is_dir():
            return []
        trabajos: list[Job] = []
        leidos: dict[str, Job] = {}
        servidores_vivos: set[str] = set()
        for ruta in sorted(self.carpeta.glob('*.json')):
            try:
                datos = json.loads(ruta.read_text(encoding='utf-8'))
                job = Job(kind=str(datos['kind']), title=str(datos['title']),
                          workspace_id=str(datos['workspace_id']), lane=str(datos['lane']),
                          fn=lambda _ctx: None, id=str(datos['id']), status=str(datos['status']),
                          progress=datos.get('progress'), error=datos.get('error'), result=datos.get('result'),
                          created_at=float(datos['created_at']), started_at=datos.get('started_at'),
                          finished_at=datos.get('finished_at'),
                          reanudar=datos.get('reanudar') if isinstance(datos.get('reanudar'), dict) else None,
                          relanzado_de=datos.get('relanzado_de'), proceso=datos.get('proceso'),
                          relanzado=bool(datos.get('relanzado')))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logging.getLogger(__name__).warning('Diario de trabajos ilegible, %s: %s', ruta.name, exc)
                continue
            if datos.get('cancel_requested'):
                job.cancel.set()
            leidos[job.id] = job
            if job.lane not in LANES:
                job.lane = 'engine'  # de una versión con otros carriles: se ve igual
            if job.status not in FINISHED:
                pid, inicio = datos.get('pid'), datos.get('inicio_proceso')
                if type(pid) is int and (inicio_de_proceso(pid) == inicio if inicio is not None
                                         else pid == self._mi_pid):
                    servidores_vivos.add(job.id)
                    continue
                registro = self._ruta(job.id, 'log')
                job.finished_at = registro.stat().st_mtime if registro.is_file() else ruta.stat().st_mtime
                job.error = ('El servidor se detuvo con este trabajo a medias: no terminó y su resultado no '
                             'vale. Su registro se conserva; retómelo si hace falta.')
                if isinstance(job.proceso, dict) and job.proceso.get('estado') == 'lanzando':
                    job.error += (' No se confirmó la identidad del trabajador que se estaba lanzando; '
                                  'requiere revisión antes de repetir, sin terminar procesos ambiguos.')
                job.status = INTERRUMPIDO
                self.anotar(job)
            trabajos.append(job)
        trabajos.sort(key=lambda j: j.created_at)
        ancestros_con_sucesor = {j.relanzado_de for j in leidos.values() if j.relanzado_de}
        for job in trabajos:
            if job.id in ancestros_con_sucesor:
                # El sucesor puede pertenecer a un servidor vivo y no aparecer en list().
                # Derivar su exclusión no reescribe el recibo ni se adjudica ese trabajo.
                job.relanzado = True
        enlaces = {identidad: set() for identidad in leidos}
        for j in leidos.values():
            if j.relanzado_de in enlaces:
                enlaces[j.id].add(j.relanzado_de)
                enlaces[j.relanzado_de].add(j.id)

        def cadena(semillas: set[str]) -> set[str]:
            conservar, pendientes = set(semillas), list(semillas)
            while pendientes:
                for relacionado in enlaces[pendientes.pop()] - conservar:
                    conservar.add(relacionado)
                    pendientes.append(relacionado)
            return conservar

        protegidos = cadena(servidores_vivos | {j.id for j in trabajos
            if (j.status == INTERRUMPIDO or j.status not in FINISHED) and proceso_pendiente(j.proceso)})
        residuo = [j for j in trabajos if j.id not in protegidos]
        conservar = cadena(protegidos | {j.id for j in residuo[-MAX_INTERRUMPIDOS:]})
        # La cap es para el residuo seguro: un reloj atrasado o un hijo vivo no autorizan
        # romper una cadena que impide duplicar, ni borrar su log para cumplir una cifra.
        for viejo in trabajos:
            if viejo.id not in conservar:
                self.olvidar(viejo.id)
        return [j for j in trabajos if j.id in conservar]


class JobManager:
    def __init__(self, emit: Emit, *, diario: Path | None = None) -> None:
        self._emit = emit
        self._jobs: dict[str, Job] = {}
        self._queues = {lane: queue.Queue() for lane in LANES}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._closing = False
        self._admision = threading.RLock()
        self._diario = DiarioTrabajos(diario) if diario is not None else None
        if self._diario is not None:
            for job in self._diario.recuperar():
                self._jobs[job.id] = job
                # Un recibo final se consulta, no vuelve a disparar custodia/capturas al arrancar.
                if job.status != INTERRUMPIDO:
                    continue
                try:
                    self._emit(job.workspace_id, 'job', job.public())
                except Exception as exc:  # noqa: BLE001 - un espacio que ya no está no impide arrancar
                    logging.getLogger(__name__).warning('Trabajo interrumpido %s sin publicar: %s', job.id, exc)

    def registro(self, job_id: str, ultimas: int = 2000) -> list[str] | None:
        """El registro guardado de un trabajo, también de uno interrumpido en otra ejecución."""
        return self._diario.registro(job_id, ultimas) if self._diario is not None else None

    def reanudables(self) -> list[Job]:
        """096:RF-5, RF-6: por espacio, el último interrumpido que se puede repetir y aún no se relanzó."""
        ultimos: dict[str, Job] = {}
        todos = self.list()
        ancestros = {j.relanzado_de for j in todos if j.relanzado_de}
        bloqueados = {j.workspace_id for j in todos if (j.status == INTERRUMPIDO or j.status not in FINISHED)
                      and proceso_pendiente(j.proceso)}
        for job in sorted(todos, key=lambda j: j.created_at):
            if job.status == INTERRUMPIDO:
                ultimos[job.workspace_id] = job
            elif job.status not in FINISHED:
                ultimos.pop(job.workspace_id, None)
        return [j for j in ultimos.values() if j.reanudar and not j.relanzado and not j.cancel.is_set()
                and j.id not in ancestros
                and j.workspace_id not in bloqueados]

    def marcar_relanzado(self, job: Job) -> None:
        """096:RF-6: un interrumpido se relanza una sola vez, también tras otro reinicio."""
        with job.diario_gate:
            anterior = job.relanzado
            job.relanzado = True
            if self._diario is not None and not self._diario.anotar(job):
                job.relanzado = anterior
                raise OSError('No se pudo guardar el relanzado durable; la recuperación requiere revisión.')

    def mantenimiento_si_libre(self, fn: Callable[[], Any]) -> Any:
        """062:RF-3: comprobar inactividad y limpiar excluye nuevas admisiones."""
        with self._admision:
            if self.en_curso():
                return None
            return fn()

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

    def comprobar_exclusivo(self) -> None:
        """086:RF-86: ``TrabajoRechazado`` si corre un trabajo exclusivo (la copia de los datos)."""
        exclusivo = next((j for j in self.list() if j.kind in EXCLUSIVOS and j.status not in FINISHED), None)
        if exclusivo is not None:
            raise TrabajoRechazado(f'Se está haciendo la copia de los datos («{exclusivo.title}»): espere a que '
                                   'termine o cancélela.')

    def en_curso(self) -> int:
        """Trabajos sin terminar en todos los espacios: el lanzador no cierra un servidor con ellos."""
        return sum(1 for j in self.list() if j.status not in FINISHED)

    # -------------------------------------------------------------- acciones
    def submit(
        self, workspace_id: str, kind: str, title: str,
        fn: Callable[[JobContext], Any], *, lane: str = 'engine',
        reanudar: dict | None = None, relanzado_de: str | None = None,
    ) -> Job:
        with self._admision:
            return self._admitir(workspace_id, kind, title, fn, lane=lane, reanudar=reanudar,
                                 relanzado_de=relanzado_de)

    def _admitir(
        self, workspace_id: str, kind: str, title: str,
        fn: Callable[[JobContext], Any], *, lane: str,
        reanudar: dict | None = None, relanzado_de: str | None = None,
    ) -> Job:
        if lane not in LANES:
            raise ValueError(f'carril desconocido: {lane}')
        if self._closing:
            raise RuntimeError('el servidor se está cerrando')
        self.comprobar_exclusivo()
        activos = [j for j in self.list() if j.status not in FINISHED]
        if kind in EXCLUSIVOS and activos:
            raise TrabajoRechazado(f'Hay {len(activos)} trabajo(s) en curso: la copia se hace con la web en reposo.')
        job = Job(kind=kind, title=title, workspace_id=workspace_id, lane=lane, fn=fn,
                  reanudar=reanudar, relanzado_de=relanzado_de)
        if relanzado_de and self._diario is not None and not self._diario.anotar(job):
            raise OSError('No se pudo guardar el recibo durable del sucesor; no se admite ni ejecuta.')
        with self._lock:
            self._jobs[job.id] = job
            self._ensure_worker(lane)
        self._anotar()
        try:
            self._emit(workspace_id, 'job', job.public())
        except Exception:
            # 061:RF-10: un fallo del registro inicial no deja reservado el carril
            # ni permite ejecutar un trabajo cuya admisión no se pudo observar.
            with self._lock:
                self._jobs.pop(job.id,None)
            if relanzado_de and self._diario is not None:
                self._diario.olvidar(job.id)  # Aún no entró en la cola ni pudo ejecutar efectos.
            self._anotar()
            raise
        if self._diario is not None and not relanzado_de:
            self._diario.anotar(job)
        self._queues[lane].put(job)
        return job

    def _anotar(self) -> None:
        """Los trabajos en curso, en el registro que lee el lanzador (spec 001, RF-34)."""
        ruta = registro_de_trabajos(os.getpid())
        if ruta is None:
            return
        try:
            from ..util import write_json_atomic

            write_json_atomic(ruta, {'pid': os.getpid(), 'en_curso': self.en_curso(),
                                     'hora': time.time()})
        except OSError:
            pass

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.status in FINISHED:
            return job
        with job.gate:
            if job.irrevocable:
                return job
            job.cancel.set()
            if self._diario is not None and not self._diario.anotar(job):
                raise OSError('No se pudo guardar la cancelación durable; sigue pedida en memoria y requiere revisión.')
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
        # Toda admisión que pasó la guardia termina antes de cerrar; las posteriores
        # se rechazan. No esperar a workers bajo _admision: pueden encolar otros pasos.
        with self._admision:
            self._closing = True
            trabajos = self.list()
            hilos = tuple(self._threads.values())
        errores = []
        for job in trabajos:
            if job.status not in FINISHED:
                try:
                    self.cancel(job.id)
                except Exception as exc:  # el cierre debe liberar el resto aunque falle persistir o notificar
                    errores.append(f'{job.id}: {exc}')
        for lane in LANES:
            self._queues[lane].put(None)
        deadline = time.time() + timeout_s
        for thread in hilos:
            thread.join(timeout=max(0.0, deadline - time.time()))
        if errores:
            raise OSError('El cierre terminó con cancelaciones sin confirmar: ' + '; '.join(errores))

    # -------------------------------------------------------------- interno
    def _ensure_worker(self, lane: str) -> None:
        thread = self._threads.get(lane)
        if thread is not None and thread.is_alive():
            return
        thread = threading.Thread(target=self._worker, args=(lane,),
                                  name=f'csg-{lane}', daemon=True)
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
        if self._diario is not None:
            self._diario.anotar(job)
        self._emit(job.workspace_id, 'job', job.public())
        ctx = JobContext(job, self._emit, self._diario)
        if job.relanzado_de:
            ctx.log(f'Se relanza solo el trabajo {job.relanzado_de}, interrumpido al caer la web (096:RF-5, RF-7).')
        from .suspension import sin_suspender, suspendido_s

        repetido = False
        while True:
            dormido_antes = suspendido_s()
            try:
                with sin_suspender():                                                   # 096:RF-1
                    job.result = job.fn(ctx)
                break
            except JobCancelled:
                ctx.log(f'--- {job.title}: cancelado ---')
                self._finish(job, CANCELLED)
                return
            except Exception as exc:  # noqa: BLE001 - borde: el trabajo informa, no tumba el hilo
                # 086:RF-15: sin GPU no es un fallo del programa: el Registro lo dice en una línea, sin la traza.
                ctx.log(str(exc) if _es_sin_gpu(exc) else traceback.format_exc())
                dormido = suspendido_s() - dormido_antes
                # 096:RF-2 a RF-4: tras una suspensión, una vez; nunca cancelado ni sin suspensión.
                if not repetido and dormido >= SUSPENSION_MINIMA_S and not job.cancel.is_set():
                    repetido = True
                    ctx.log(f'El equipo estuvo suspendido {dormido / 60:.1f} min durante «{job.title}» y falló: '
                            f'se repite una vez, solo (096:RF-2). Error: {str(exc) or exc.__class__.__name__}')
                    continue
                job.error = str(exc) or exc.__class__.__name__
                self._finish(job, FAILED)
                return
        # Un lote cancelado devuelve igual su manifiesto: se conserva como resultado.
        self._finish(job, CANCELLED if job.cancel.is_set() else _estado_del_resultado(job.result))

    def _finish(self, job: Job, status: str) -> None:
        job.status = status
        job.finished_at = time.time()
        if self._diario is not None:
            self._diario.terminar(job)
        self._anotar()
        self._emit(job.workspace_id, 'job', job.public())
