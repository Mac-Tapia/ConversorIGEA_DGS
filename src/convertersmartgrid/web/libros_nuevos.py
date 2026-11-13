"""La web reconoce sola los libros nuevos de demanda de cada espacio (spec 104).

Antes solo se reindexaba al pulsar «Actualizar índice»: el libro de octubre de 2026 de clientes importantes llegó a la
carpeta y lo revisó Claude a mano. Aquí se vigila al arrancar, al abrir un espacio y cada cierto tiempo; se reindexa lo
que cambió, se verifica cada libro nuevo con ``convertersmartgrid.libros_nuevos`` y se avisa en el registro y en un aviso
del espacio. El dataset del pronóstico se marca desactualizado y se regenera aparte, sin entrenar.

Comparar fotos solo lista ficheros (P7). Lo que abre libros va en el carril de fondo (``fondo.py``, 104:RF-30): no en
la cola de trabajos, que el 2026-11-12 dejó en cola el «Cargar / listar alimentadores» del operador mientras se leían 22
libros. Cada libro se lee en un proceso de prioridad baja que se termina en cuanto el operador lanza algo; lo terminado
queda guardado (la foto de cada fuente reindexada y la lista ``por_verificar``) y se sigue al quedar libre el motor.
Nada bloquea: lo que falla se dice y se sigue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .. import libros_nuevos as ln
from . import services
from .fondo import (
    CARRILES_DEL_OPERADOR,
    Cedido,
    ContextoFondo,
    ProcesoFondo,
    ejecutar_aqui,
    ejecutar_en_proceso,
    operador_trabajando,
)
from .jobs import inicio_de_proceso, proceso_pendiente
from .requisitos import UserError

log = logging.getLogger(__name__)

VARIABLE_INTERVALO = 'CSG_LIBROS_INTERVALO_MIN'
#: La pone ``__main__``: solo el servidor real vigila; las pruebas crean la aplicación a cientos (como 026:RF-22).
VARIABLE_ACTIVA = 'CSG_LIBROS_NUEVOS'
#: 104:RF-36: minutos sin trabajos del operador antes de regenerar el dataset.
VARIABLE_REPOSO = 'CSG_DATASET_REPOSO_MIN'
#: 104:RF-45: minutos que puede durar la regeneración del dataset. Aislada tardó 12 min el 2026-11-12; diez veces eso
#: cubre un equipo cargado sin dejarla colgada para siempre (el mismo criterio que ``activeDeadlineSeconds`` de un Job).
VARIABLE_PLAZO = 'CSG_DATASET_PLAZO_MIN'
PLAZO_MIN = 120.0
INTERVALO_MIN = 10.0
REPOSO_MIN = 5.0
#: RF-19: libros que se verifican por reconocimiento; los demás se dicen.
TOPE_VERIFICADOS = 3
#: Al abrir un espacio no se mira más de una vez por minuto.
ESPERA_AL_ABRIR_S = 60.0
#: 104:RF-40: la revisión periódica solo mira los espacios modificados o abiertos en estas horas.
VARIABLE_RECIENTES = 'CSG_LIBROS_RECIENTES_H'
RECIENTES_H = 24.0
#: 104:RF-41: un espacio pedido por la web hace menos de esto cuenta como abierto aunque no tenga su WebSocket.
ABIERTO_S = 600.0
#: Cada cuánto despierta el hilo de fondo para ver si el motor quedó libre o si hay que ceder.
PASO_FONDO_S = 0.25
TIPOS = ('cabecera', 'clientes', 'suministros', 'medidores')
VERIFICABLES = ('clientes', 'cabecera')
ETIQUETAS = {'cabecera': 'cabecera', 'clientes': 'clientes importantes', 'suministros': 'suministros',
             'medidores': 'medidores'}
#: Tipo del evento con que el espacio sabe que cambió el carril de fondo, un aviso o el dataset (104:RF-39).
EVENTO = 'libros_nuevos'


def _minutos(variable: str, defecto: float) -> float:
    try:
        return max(0.0, float(os.environ.get(variable, defecto)))
    except ValueError:
        return defecto


def intervalo_min() -> float:
    """RF-2: 10 minutos por defecto; ``0`` apaga la revisión periódica."""
    return _minutos(VARIABLE_INTERVALO, INTERVALO_MIN)


def reposo_min() -> float:
    """RF-36: 5 minutos sin trabajos del operador por defecto."""
    return _minutos(VARIABLE_REPOSO, REPOSO_MIN)


def plazo_min() -> float:
    """RF-45: 120 minutos por defecto; ``0`` lo quita."""
    return _minutos(VARIABLE_PLAZO, PLAZO_MIN)


def recientes_h() -> float:
    """RF-40: 24 horas por defecto."""
    return _minutos(VARIABLE_RECIENTES, RECIENTES_H)


def carpeta_estado(ws) -> Path:
    return ws.root / 'demanda'


def carpeta_dataset(ws) -> Path:
    return ws.out_dir / 'pronostico' / 'dataset'


def conocidos_del_indice(tipo: str, meta: dict, foto: ln.Foto) -> dict[str, tuple[int, int]]:
    """RF-6: sin foto anterior, lo que ya publica el índice cuenta como conocido.

    Cabecera guarda tamaño y fecha de cada libro; clientes, los nombres y la hora del índice (un libro modificado
    después cuenta como cambiado); suministros y medidores, sus nombres.
    """
    actual = {rel: (size, mtime) for rel, size, mtime in foto}
    if tipo == 'cabecera':
        return {x['relativa']: (int(x.get('size') or -1), int(x.get('mtime_ns') or -1))
                for x in meta.get('indice') or [] if x.get('relativa')}
    if tipo == 'clientes':
        hora = float(meta.get('indexado_en') or 0) * 1e9
        return {rel: (actual[rel] if rel in actual and actual[rel][1] <= hora else (-1, -1))
                for rel in meta.get('libros') or [] if hora}
    nombres = meta.get('libros') or [meta.get('name')]
    return {rel: actual[rel] for rel in nombres if rel in actual}


def _ultimo_trabajo_del_operador(jobs) -> float | None:
    """Cuándo terminó el último trabajo del operador en el motor o en DIgSILENT (104:RF-36)."""
    fines = [j.finished_at for j in jobs.list() if j.lane in CARRILES_DEL_OPERADOR and j.finished_at]
    return max(fines) if fines else None


class VigilanciaLibros:
    """Revisa las fuentes de demanda de los espacios y reconoce lo nuevo en el carril de fondo (RF-1 a RF-6, RF-30)."""

    def __init__(self, store, jobs, *, en_fondo: bool = True, ahora: Callable[[], float] = time.time):
        self.store, self.jobs, self.ahora = store, jobs, ahora
        #: El dataset en su proceso aparte (RF-36); las pruebas lo hacen en el hilo de fondo para no esperar al spawn.
        self.en_fondo = en_fondo
        #: Cada libro en su proceso que se termina al ceder (RF-33); ``False`` en las pruebas que no lo necesitan.
        self.en_proceso = True
        self.activa = os.environ.get(VARIABLE_ACTIVA) == '1'
        self._arranque = ahora()
        self._locks: dict[str, threading.Lock] = {}
        self._abierto_en: dict[str, float] = {}
        self._guard = threading.Lock()
        # Carril de fondo: un hilo que atiende las revisiones pedidas y los datasets pendientes, y se acaba sin nada.
        self._cv = threading.Condition()
        self._pedidos: dict[str, bool] = {}          # espacio -> «verificar todos» (RF-35)
        self._datasets: set[str] = set()             # espacios con el dataset desactualizado (RF-22)
        self._procesos: dict[str, tuple[ProcesoFondo, list[str]]] = {}
        self._lanzando: set[str] = set()             # datasets cuyo proceso está arrancando (RF-43)
        self._fondo: dict[str, dict] = {}            # lo que ve el operador del carril, por espacio (RF-31)
        self._hilo: threading.Thread | None = None
        self._detener = threading.Event()
        # RF-41: páginas con el WebSocket del espacio abierto, y cuándo lo pidió la web por última vez.
        self._paginas: dict[str, int] = {}
        self._visto_en: dict[str, float] = {}

    def pagina(self, wid: str, delta: int) -> None:
        """Una pestaña abre (+1) o cierra (-1) el WebSocket del espacio."""
        with self._guard:
            self._paginas[wid] = max(0, self._paginas.get(wid, 0) + delta)
            self._visto_en[wid] = self.ahora()

    def abierto(self, wid: str) -> bool:
        """RF-41: el operador tiene el espacio abierto (una pestaña conectada, o pedido hace menos de 10 min)."""
        with self._guard:
            return self._paginas.get(wid, 0) > 0 or self.ahora() - self._visto_en.get(wid, -1e18) < ABIERTO_S

    # ------------------------------------------------------------------ estado
    def _lock(self, ws) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(ws.id, threading.Lock())

    def _modificar(self, ws, fn: Callable[[dict], Any]) -> Any:
        with self._lock(ws):
            estado = ln.leer_estado(carpeta_estado(ws))
            resultado = fn(estado)
            ln.guardar_estado(carpeta_estado(ws), estado)
            return resultado

    def _publicar(self, ws) -> None:
        """RF-39: la web vuelve a leer el estado al ver este evento; un aviso no se queda desfasado."""
        try:
            ws.events.append(EVENTO, {'fondo': self._fondo_de(ws.id)})
        except Exception:  # noqa: BLE001 - un espacio sin registro de eventos no para el carril
            log.debug('evento de libros nuevos sin publicar en %s', ws.id)

    def _fondo_de(self, wid: str) -> dict:
        with self._cv:
            return dict(self._fondo.get(wid) or {'estado': 'libre', 'texto': None})

    def _poner_fondo(self, ws, estado: str, texto: str | None = None, **extra: Any) -> None:
        with self._cv:
            self._fondo[ws.id] = {'estado': estado, 'texto': texto, 'desde': self.ahora(), **extra}
        self._publicar(ws)

    def _plazo_del_dataset(self, ws) -> dict:
        """RF-38: cuándo se regenerará un dataset desactualizado."""
        demanda = ws.demanda or {}
        reposo = reposo_min()
        if not demanda.get('cabecera') or not demanda.get('medidores'):
            return {'espera': 'faltan_fuentes', 'previsto': None, 'reposo_min': reposo}
        if operador_trabajando(self.jobs):
            return {'espera': 'motor_ocupado', 'previsto': None, 'reposo_min': reposo}
        libre = max(self._arranque, _ultimo_trabajo_del_operador(self.jobs) or 0.0)
        return {'espera': 'reposo', 'previsto': max(libre + reposo * 60, self.ahora()), 'reposo_min': reposo}

    def estado(self, ws) -> dict[str, Any]:
        """Lo que ve el operador: los avisos sin dar por vistos, la última revisión, el carril de fondo y el dataset
        (RF-20, RF-22, RF-31, RF-38). Un «regenerando» sin proceso vivo se ve aquí como interrumpido (RF-43)."""
        self.comprobar_regenerando(ws)
        e = ln.leer_estado(carpeta_estado(ws))
        intervalo = intervalo_min()
        ultima = e.get('ultima_revision')
        dataset = e.get('dataset')
        if dataset and dataset.get('estado') == 'desactualizado':
            dataset = {**dataset, **self._plazo_del_dataset(ws)}
        return {
            'avisos': [a for a in e.get('avisos') or [] if not a.get('visto')],
            'ultima_revision': ultima,
            'proxima_revision': (ultima + intervalo * 60) if (ultima and intervalo) else None,
            'intervalo_min': intervalo,
            'repetidos': sorted(e.get('repetidos') or {}),
            'dataset': dataset,
            'fondo': {**self._fondo_de(ws.id), 'por_verificar': len(e.get('por_verificar') or [])},
        }

    def dar_por_visto(self, ws, aviso_id: str) -> dict[str, Any]:
        """RF-21."""
        def marcar(e):
            for a in e.get('avisos') or []:
                if a.get('id') == aviso_id:
                    a['visto'] = True
        self._modificar(ws, marcar)
        return self.estado(ws)

    # ------------------------------------------------------------------ comparar
    def _comparar(self, ws) -> tuple[dict[str, dict], dict[str, list]]:
        """Por fuente, los libros nuevos, cambiados y retirados frente al último reconocimiento (RF-1, RF-6), y las
        fuentes sin foto ni índice anterior, cuya foto es la base (RF-34)."""
        e = ln.leer_estado(carpeta_estado(ws))
        fotos = e.get('fotos') or {}
        pendientes, bases = {}, {}
        for tipo in TIPOS:
            meta = (ws.demanda or {}).get(tipo)
            if not meta or not meta.get('path'):
                continue
            foto = ln.foto_de_fuente(meta['path'])
            previa = fotos.get(tipo)
            if previa is None:
                conocidos = conocidos_del_indice(tipo, meta, foto)
                if not conocidos:
                    # RF-34: el 2026-11-12, un espacio sin índice dio por nuevos sus 22 libros y los leyó todos en el
                    # carril del motor. Sin nada con que comparar, lo que hay es la base; se verifica lo que llegue.
                    bases[tipo] = [list(x) for x in foto]
                    continue
            else:
                conocidos = {rel: (size, mtime) for rel, size, mtime in previa}
            c = ln.cambios(conocidos, foto)
            if any(c.values()):
                pendientes[tipo] = {**c, 'foto': [list(x) for x in foto]}
        return pendientes, bases

    def pendientes(self, ws) -> dict[str, dict]:
        """Lo que la próxima revisión reconocerá (RF-1, RF-6)."""
        return self._comparar(ws)[0]

    def _guardar_bases(self, ws, bases: dict[str, list]) -> None:
        if not bases:
            return
        self._modificar(ws, lambda e: e.setdefault('fotos', {}).update(bases))
        for tipo, foto in bases.items():
            ws.events.append('log', {'text': f'Libros de {ETIQUETAS[tipo]}: {len(foto)} tomados como base, sin '
                                              'abrirlos; se verificarán los que lleguen o cambien. «Verificar todos '
                                              'ahora» los revisa a mano (104:RF-34).'})

    def revisar(self, ws, *, todos: bool = False, leer: bool = True) -> bool:
        """Compara y, si hay algo que reconocer, lo pide al carril de fondo; devuelve si lo pidió (RF-3, RF-30).

        Con el motor ocupado lo pedido espera en el carril y se hace al quedar libre (aclaración de RF-4). Con
        ``leer=False`` (un espacio que el operador no tiene abierto, RF-41) solo se compara la foto: lo nuevo queda
        dicho en el estado y se lee al abrirlo.
        """
        self.comprobar_regenerando(ws)                                       # RF-43, RF-44
        try:
            pendientes, bases = self._comparar(ws)
        except OSError as exc:              # la unidad de los libros no está: se dirá en la próxima
            log.warning('libros nuevos de %s: %s', ws.id, exc)
            return False
        self._guardar_bases(ws, bases)

        def marcar(e):
            e['ultima_revision'] = self.ahora()
            return e
        e = self._modificar(ws, marcar)
        if (e.get('dataset') or {}).get('estado') == 'desactualizado':
            with self._cv:
                self._datasets.add(ws.id)
        if not (pendientes or e.get('por_verificar') or todos):
            self._asegurar_hilo()
            if bases:
                self._publicar(ws)
            return False
        if not leer:
            n = sum(len(c['nuevos']) + len(c['cambiados']) for c in pendientes.values())
            self._poner_fondo(ws, 'al_abrir', f'Hay {n} libro(s) nuevos o cambiados: se leen al abrir el espacio.')
            return False
        with self._cv:
            self._pedidos[ws.id] = self._pedidos.get(ws.id, False) or todos
        if operador_trabajando(self.jobs):
            self._poner_fondo(ws, 'en_espera', 'Revisión de libros en espera: empieza cuando el motor quede libre.')
        else:
            self._poner_fondo(ws, 'pendiente', 'Revisión de libros pedida; empieza enseguida.')
        self._asegurar_hilo()
        return True

    def al_abrir(self, ws) -> None:
        """RF-1: al abrir un espacio, sin hacer esperar a la página."""
        if not self.activa:
            return
        ahora = self.ahora()
        with self._guard:
            self._visto_en[ws.id] = ahora                                     # RF-41
        if ahora - self._abierto_en.get(ws.id, 0.0) < ESPERA_AL_ABRIR_S:
            return
        self._abierto_en[ws.id] = ahora
        threading.Thread(target=self._revisar_sin_fallar, args=(ws,), daemon=True, name='csg-libros-nuevos').start()

    def _revisar_sin_fallar(self, ws, leer: bool = True) -> None:
        try:
            self.revisar(ws, leer=leer)
        except Exception:  # noqa: BLE001 - un hilo de vigilancia no tumba la web; queda en el registro del servidor
            log.exception('revisión de libros nuevos de %s', ws.id)

    def revisar_todos(self) -> None:
        """RF-40, RF-41: solo los espacios modificados o abiertos en las últimas horas, y sin leer libros de los que
        el operador no tiene abiertos. El 2026-11-12 la web recorría los 43 espacios al arrancar y cada 10 min, y
        encolaba la lectura de uno detrás de otro en el motor común a todos."""
        desde = self.ahora() - recientes_h() * 3600
        for fila in self.store.list():
            if fila.get('estado', 'ok') != 'ok':
                continue
            if not self.abierto(fila['id']) and float(fila.get('modified_at') or 0) < desde:
                continue
            try:
                ws = self.store.get(fila['id'])
            except Exception:  # noqa: BLE001 - un espacio que no abre lo dice su propio aviso (086:RF-2)
                continue
            if ws is not None and ws.demanda:
                self._revisar_sin_fallar(ws, leer=self.abierto(ws.id))

    async def vigilar(self, detener: asyncio.Event) -> None:
        """Al arrancar y cada intervalo; la espera se corta al apagar la web (RF-1, RF-2).

        Al arrancar se miran los «regenerando» que dejó una web anterior, también con la vigilancia apagada (RF-46):
        el 2026-11-12 la web del operador tenía ``CSG_LIBROS_NUEVOS=0`` y nadie volvió a mirarlo en 11 h. Con ella
        encendida ya lo hace cada ``revisar`` de ``revisar_todos``.
        """
        if not self.activa:
            await asyncio.to_thread(self.recuperar_datasets)
            return
        while not detener.is_set():
            await asyncio.to_thread(self.revisar_todos)
            intervalo = intervalo_min()
            if not intervalo:
                return
            try:
                await asyncio.wait_for(detener.wait(), timeout=intervalo * 60)
            except asyncio.TimeoutError:
                pass

    def parar(self, timeout_s: float = 5.0) -> None:
        """Al apagar la web: lo de fondo cede como ante el operador y su proceso se termina."""
        self._detener.set()
        with self._cv:
            self._cv.notify_all()
            hilo = self._hilo
        if hilo is not None:
            hilo.join(timeout=timeout_s)
        for wid, (proc, _libros) in list(self._procesos.items()):
            proc.terminar()
            with self._cv:
                self._procesos.pop(wid, None)
            ws = self._espacio(wid)
            if ws is not None:
                # RF-46: si no, el disco se queda con «regenerando» y la próxima web no sabe que murió.
                self._interrumpir(ws, 'se cerró la web mientras se regeneraba', retomar=False)

    # ------------------------------------------------------------------ carril de fondo (RF-30 a RF-37)
    def _ceder(self) -> bool:
        return self._detener.is_set() or operador_trabajando(self.jobs)

    def _ejecutar(self, fn: Callable[..., Any], *args: Any) -> Any:
        return (ejecutar_en_proceso if self.en_proceso else ejecutar_aqui)(fn, *args, ceder=self._ceder)

    def _asegurar_hilo(self) -> None:
        with self._cv:
            if self._detener.is_set() or not (self._pedidos or self._datasets or self._procesos):
                return
            if self._hilo is None or not self._hilo.is_alive():
                self._hilo = threading.Thread(target=self._bucle, daemon=True, name='csg-fondo-libros')
                self._hilo.start()
            self._cv.notify_all()

    def ocupado(self) -> bool:
        """El carril de fondo tiene algo pedido, en marcha o esperando el reposo del motor."""
        with self._cv:
            return bool(self._pedidos or self._procesos) or any(
                f.get('estado') in ('pendiente', 'revisando', 'en_espera') for f in self._fondo.values())

    def _bucle(self) -> None:
        while not self._detener.is_set():
            try:
                ocupado = operador_trabajando(self.jobs)
                if ocupado:
                    self._cortar_datasets()                                    # RF-37
                self._recoger_datasets()
                if not ocupado:
                    with self._cv:
                        wid = next(iter(self._pedidos), None)
                        todos = self._pedidos.pop(wid) if wid is not None else False
                    if wid is not None:
                        self._atender(wid, todos)
                        continue
                    if self._reposo_cumplido():
                        for pendiente in sorted(self._datasets - set(self._procesos)):
                            self._lanzar_dataset(pendiente)
            except Exception:  # noqa: BLE001 - el carril de fondo no tumba la web; queda en el registro del servidor
                log.exception('carril de fondo de los libros nuevos')
            with self._cv:
                if not (self._pedidos or self._datasets or self._procesos):
                    self._hilo = None
                    return
                self._cv.wait(timeout=PASO_FONDO_S)

    def _reposo_cumplido(self) -> bool:
        libre = max(self._arranque, _ultimo_trabajo_del_operador(self.jobs) or 0.0)
        return self.ahora() - libre >= reposo_min() * 60

    def _espacio(self, wid: str):
        try:
            return self.store.get(wid)
        except Exception:  # noqa: BLE001 - un espacio que ya no abre no para el carril
            return None

    def _atender(self, wid: str, todos: bool) -> None:
        ws = self._espacio(wid)
        if ws is None:
            return
        self._poner_fondo(ws, 'revisando', 'Revisando libros de demanda en segundo plano…')
        try:
            self._reconocer(ws, todos)
        except Cedido:
            # RF-32: lo terminado ya se guardó; lo demás espera a que el motor quede libre.
            with self._cv:
                self._pedidos[wid] = self._pedidos.get(wid, False) or todos
            self._poner_fondo(ws, 'en_espera', 'Revisión de libros en pausa: cedió el equipo a un trabajo del '
                                               'operador y sigue cuando el motor quede libre.')
            return
        except Exception as exc:  # noqa: BLE001 - se dice y la web sigue (RF-18)
            log.exception('reconocimiento de libros de %s', wid)
            self._poner_fondo(ws, 'error', f'La revisión de libros falló: {exc}')
            return
        self._poner_fondo(ws, 'libre')

    def _reconocer(self, ws, todos: bool) -> list[str]:
        """Reindexa lo que cambió, verifica los libros nuevos y lo avisa (RF-5, RF-7 a RF-20, RF-35)."""
        pendientes, bases = self._comparar(ws)
        self._guardar_bases(ws, bases)
        if todos:                                                              # RF-35
            for tipo in VERIFICABLES:
                meta = (ws.demanda or {}).get(tipo)
                if meta and meta.get('path'):
                    foto = [list(x) for x in ln.foto_de_fuente(meta['path'])]
                    previo = pendientes.get(tipo) or {'nuevos': [], 'cambiados': [], 'retirados': []}
                    pendientes[tipo] = {**previo, 'foto': foto, 'todos': [x[0] for x in foto]}
        ctx = ContextoFondo(self._ceder, progreso=lambda i, n, m='': self._poner_fondo(
            ws, 'revisando', f'Leyendo libros de demanda en segundo plano: {i}/{n} {m}'.rstrip(), avance=[i, n]))
        for tipo, c in pendientes.items():
            ctx.check_cancel()
            self._reindexar(ws, ctx, tipo, c)
        self._verificar_pendientes(ws, ctx, todos)
        return sorted(pendientes)

    def _avisar(self, ws, avisos: list[dict], tipo: str, texto: str, libro: str | None = None,
                ficha: dict | None = None) -> None:
        ws.events.append('log', {'text': texto})
        avisos.append({'id': uuid.uuid4().hex[:12], 'tipo': tipo, 'libro': libro, 'texto': texto,
                       'cuando': self.ahora(), 'visto': False, 'ficha': ficha})

    def _guardar_avisos(self, ws, avisos: list[dict]) -> None:
        if avisos:
            self._modificar(ws, lambda e: e.update(avisos=[*(e.get('avisos') or []), *avisos][-100:]))
            self._publicar(ws)

    def _reindexar(self, ws, ctx: ContextoFondo, tipo: str, c: dict) -> None:
        """Una fuente: se reindexa y, publicado su índice, se guarda su foto y sus libros por verificar (RF-5, RF-32)."""
        avisos: list[dict] = []
        nuevos = c['nuevos'] + c['cambiados']
        try:
            if tipo == 'clientes':
                services.demanda_clientes_indexar(ws, ctx, ejecutar=self._ejecutar)
            elif tipo == 'cabecera':
                services.demanda_cabecera_indexar(ws, ctx, ejecutar=self._ejecutar)
            elif tipo == 'suministros':
                meta = ws.demanda['suministros']
                ctx.check_cancel()
                services.demanda_asignar(ws, 'suministros', Path(meta['path']), meta.get('origin', 'server'))
                elegido = ws.demanda['suministros'].get('seleccion')
                for rel in nuevos:
                    self._avisar(ws, avisos, tipo, f'Llegó {rel} a suministros; se usa {elegido or "ninguno"}.', rel)
            else:
                for rel in nuevos:
                    self._avisar(ws, avisos, tipo,
                                 f'Cambió el libro de medidores {rel}: las equivalencias se leen de él.', rel)
        except UserError as exc:
            self._avisar(ws, avisos, tipo, f'{ETIQUETAS[tipo].capitalize()}: no se pudo reindexar ({exc}); se sigue '
                                           'con el índice anterior.')
            self._guardar_avisos(ws, avisos)
            return
        for rel in c['retirados']:
            self._avisar(ws, avisos, tipo, f'Ya no está {rel} en la carpeta de {ETIQUETAS[tipo]}.', rel)
        verificar = c.get('todos') or nuevos

        def guardar(e):
            e.setdefault('fotos', {})[tipo] = c['foto']
            e['avisos'] = [*(e.get('avisos') or []), *avisos][-100:]
            if tipo in VERIFICABLES:
                ya = [tuple(x) for x in e.get('por_verificar') or []]
                e['por_verificar'] = [list(x) for x in dict.fromkeys([*ya, *((tipo, rel) for rel in verificar)])]
            if tipo in VERIFICABLES and nuevos:                               # RF-22
                previo = e.get('dataset') or {}
                antes = (previo.get('libros_nuevos') or []) if previo.get('estado') == 'desactualizado' else []
                e['dataset'] = {**previo, 'estado': 'desactualizado', 'desde': self.ahora(),
                                'libros_nuevos': sorted({*antes, *(f'{tipo}/{rel}' for rel in nuevos)})}
        self._modificar(ws, guardar)
        if tipo in VERIFICABLES and nuevos:
            with self._cv:
                self._datasets.add(ws.id)
        self._publicar(ws)

    def _verificar_pendientes(self, ws, ctx: ContextoFondo, todos: bool) -> None:
        """Los libros por verificar, del mes más reciente al más antiguo y como mucho tres (RF-19), uno a uno: cada uno
        verificado se guarda enseguida, y al ceder solo se pierde el que se estaba leyendo (RF-32)."""
        cola = [tuple(x) for x in ln.leer_estado(carpeta_estado(ws)).get('por_verificar') or []]
        cola.sort(key=lambda x: self._mes_de(ws, *x) or '', reverse=True)
        tope = len(cola) if todos else TOPE_VERIFICADOS
        total = min(tope, len(cola))
        for n, (tipo, rel) in enumerate(cola[:tope], start=1):
            ctx.check_cancel()
            self._poner_fondo(ws, 'revisando', f'Verificando {rel} en segundo plano ({n}/{total})…', avance=[n - 1, total])
            avisos: list[dict] = []
            if tipo == 'clientes':
                ficha = self._ejecutar(*self._verificacion_de_clientes(ws, rel))
                texto = ln.mensaje_de_clientes(ficha)
                if ficha.get('copia_de'):
                    self._marcar_repetido(ws, rel, texto)
            else:
                raiz = Path(ws.demanda['cabecera']['path'])
                ficha = self._ejecutar(ln.verificar_libro_cabecera, raiz / rel if raiz.is_dir() else raiz, rel,
                                       services.demanda_alias())
                texto = ln.mensaje_de_cabecera(ficha)
            self._avisar(ws, avisos, tipo, texto, rel, {k: v for k, v in ficha.items() if k != 'codigos'})

            def hecho(e, tipo=tipo, rel=rel, avisos=avisos):
                e['por_verificar'] = [x for x in e.get('por_verificar') or [] if tuple(x) != (tipo, rel)]
                e['avisos'] = [*(e.get('avisos') or []), *avisos][-100:]
            self._modificar(ws, hecho)
            self._publicar(ws)
        resto = [rel for _t, rel in cola[tope:]]
        if resto:
            avisos = []
            self._avisar(ws, avisos, 'clientes', f'Quedan {len(resto)} libros sin verificar ({", ".join(resto[:10])}): '
                                                 'se indexaron y se verifican en las próximas revisiones.')
            self._guardar_avisos(ws, avisos)

    def _mes_de(self, ws, tipo: str, rel: str) -> str | None:
        if tipo != 'clientes':
            return None
        catalogo = (ws.demanda.get('clientes') or {}).get('catalogo') or []
        return next((x.get('mes') for x in catalogo if x.get('nombre') == rel), None)

    def _verificacion_de_clientes(self, ws, rel: str) -> tuple:
        """La función y sus argumentos, para leerlo todo en el proceso de fondo (RF-33)."""
        meta = ws.demanda['clientes']
        suministros = Path(ws.demanda['suministros']['path']) if services.hay_suministros(ws) else None
        return (ln.verificar_clientes_de_fuente, Path(meta['path']), rel, list(meta.get('catalogo') or []),
                suministros, services.demanda_alias())

    def _marcar_repetido(self, ws, rel: str, texto: str) -> None:
        """RF-16: inactivo en el índice ya publicado y en los que vengan."""
        self._modificar(ws, lambda e: e.setdefault('repetidos', {}).update({rel: texto}))
        with ws.lock:
            for x in (ws.demanda.get('clientes') or {}).get('catalogo') or []:
                if x.get('nombre') == rel:
                    x['activo'] = False
                    if texto not in x.get('avisos', []):
                        x.setdefault('avisos', []).append(texto)
            ws.save()

    # ------------------------------------------------------------------ dataset
    def _lanzar_dataset(self, wid: str) -> None:
        """RF-23, RF-36: con el dataset desactualizado y el motor en reposo, se regenera aparte y sin entrenar."""
        ws = self._espacio(wid)
        dataset = (ln.leer_estado(carpeta_estado(ws)).get('dataset') or {}) if ws is not None else {}
        demanda = (ws.demanda or {}) if ws is not None else {}
        if dataset.get('estado') != 'desactualizado' or not demanda.get('cabecera') or not demanda.get('medidores'):
            with self._cv:
                self._datasets.discard(wid)       # RF-38 lo dice; la próxima revisión lo vuelve a mirar
            return
        from ..demanda_medida import DemandaError, descubrir_libro_suministros
        from ..pronostico_demanda import Fuentes

        suministros = None
        if services.hay_suministros(ws):
            try:
                ruta = Path(demanda['suministros']['path'])
                suministros = descubrir_libro_suministros(ruta, services.demanda_alias()) if ruta.is_dir() else ruta
            except (DemandaError, OSError, ValueError):
                suministros = None
        fuentes = Fuentes(cabecera=Path(demanda['cabecera']['path']), equivalencia=Path(demanda['medidores']['path']),
                          clientes=Path(demanda['clientes']['path']) if demanda.get('clientes') else None,
                          suministros=suministros, patron_clientes=services.perfil_de(ws).patron_libro_clientes,
                          # 089:RF-108, RF-110: los sinónimos de la empresa y las reglas de formato confirmadas.
                          alias=services.demanda_alias(),
                          formatos=dict((demanda.get('clientes') or {}).get('formatos') or {}) or None)
        libros = list(dataset.get('libros_nuevos') or [])
        with self._cv:
            self._lanzando.add(wid)          # RF-43: mientras arranca el proceso, el «regenerando» es de esta web
        self._modificar(ws, lambda e: e.setdefault('dataset', {}).update(estado='regenerando', inicio=self.ahora()))
        ws.events.append('log', {'text': 'Regenerando el dataset del pronóstico con los libros nuevos, en segundo '
                                         'plano y sin entrenar; se detiene si lanza un trabajo (104:RF-36, RF-37)…'})
        self._publicar(ws)
        try:
            if not self.en_fondo:
                with self._cv:
                    self._datasets.discard(wid)
                self._terminar_dataset(ws, libros, *_regenerar(fuentes, carpeta_dataset(ws)))
                return
            proc = ProcesoFondo(_regenerar, fuentes, carpeta_dataset(ws), nombre=f'csg-dataset-{wid[:6]}')
            with self._cv:
                self._procesos[wid] = (proc, libros)
        finally:
            with self._cv:
                self._lanzando.discard(wid)
        # RF-42: la identidad del proceso y de la web, como el diario de trabajos (096:RF-6): un pid solo no basta,
        # Windows los reutiliza; con su hora de arranque otra web sabe si sigue vivo.
        pid = proc.proc.pid
        identidad = {'proceso': {'pid': pid, 'inicio': inicio_de_proceso(pid) if pid else None},
                     'servidor': {'pid': os.getpid(), 'inicio': inicio_de_proceso(os.getpid())}}
        self._modificar(ws, lambda e: e.setdefault('dataset', {}).update(identidad))

    def _recoger_datasets(self) -> None:
        for wid, (proc, libros) in list(self._procesos.items()):
            try:
                listo, valor = proc.resultado()
            except Exception as exc:  # noqa: BLE001 - el motivo llega al aviso; la web sigue
                listo, valor = True, (None, f'{type(exc).__name__}: {exc}')
            if not listo:
                self._vigilar_plazo(wid, proc)
                continue
            with self._cv:
                self._procesos.pop(wid, None)
                self._datasets.discard(wid)
            ws = self._espacio(wid)
            if ws is not None:
                self._terminar_dataset(ws, libros, *valor)

    def _cortar_datasets(self) -> None:
        """RF-37: el operador lanzó algo; el dataset vuelve a desactualizado y espera al siguiente reposo."""
        for wid, (proc, _libros) in list(self._procesos.items()):
            proc.terminar()
            with self._cv:
                self._procesos.pop(wid, None)
            ws = self._espacio(wid)
            if ws is None:
                continue
            self._modificar(ws, lambda e: e.setdefault('dataset', {}).update(estado='desactualizado',
                                                                              interrumpido=self.ahora()))
            ws.events.append('log', {'text': 'Se detuvo la regeneración del dataset del pronóstico: lanzó un trabajo. '
                                             f'Se rehará tras {reposo_min():g} min sin trabajos (104:RF-37).'})
            self._publicar(ws)

    def _avisar_libros_del_dataset(self, ws, resumen: dict) -> None:
        """104:RF-47: cada libro apartado y lo dicho de cada libro, como aviso del paso de la demanda. El 2026-11-12
        «0225 Pulso e» y «0625 Pulso» quedaron fuera y solo constaban en la cuenta de «motivos_apartados»."""
        abiertos = {a.get('texto') for a in ln.leer_estado(carpeta_estado(ws)).get('avisos') or [] if not a.get('visto')}
        avisos: list[dict] = []
        for x in resumen.get('libros_apartados') or []:
            texto = f"{x['libro']}: queda fuera del dataset del pronóstico: {x['motivo']} (104:RF-47)."
            if texto not in abiertos:
                self._avisar(ws, avisos, 'apartado', texto, libro=x['libro'])
        from ..demanda_medida import huella_de_aviso

        for texto in resumen.get('avisos_de_libros') or []:
            if texto not in abiertos:
                # 089:RF-110: la huella y lo que falta, para que la web pida esas columnas y guarde la regla.
                falta = re.search(r'le falta ([^:.]+)', texto)
                ficha = {'huella': huella_de_aviso(texto),
                         'falta': [x.strip() for x in falta.group(1).split(',')] if falta else []}
                self._avisar(ws, avisos, 'formato', texto, libro=texto.split(':', 1)[0], ficha=ficha)
        self._guardar_avisos(ws, avisos)

    def formato_confirmado(self, ws, huella: str) -> None:
        """089:RF-110: una regla nueva cambia lo que se lee: el dataset queda desactualizado y se regenera en reposo."""
        def poner(e):
            d = e.setdefault('dataset', {})
            if d.get('estado') != 'regenerando':
                d.update(estado='desactualizado', desde=self.ahora(), formato_confirmado=huella)
        self._modificar(ws, poner)
        with self._cv:
            self._datasets.add(ws.id)
        self._asegurar_hilo()
        self._publicar(ws)

    # ------------------------------------------------------------------ dataset interrumpido (RF-42 a RF-46)
    def _vigilar_plazo(self, wid: str, proc: ProcesoFondo) -> None:
        """RF-45: el proceso propio que pasa su plazo se termina; se dice y espera al siguiente reposo."""
        plazo = plazo_min()
        ws = self._espacio(wid)
        if not plazo or ws is None:
            return
        dataset = ln.leer_estado(carpeta_estado(ws)).get('dataset') or {}
        inicio = dataset.get('inicio') or dataset.get('desde')
        if not isinstance(inicio, (int, float)) or self.ahora() - inicio <= plazo * 60:
            return
        proc.terminar()
        with self._cv:
            self._procesos.pop(wid, None)
        # Sin relanzarlo enseguida: lo retoma la próxima revisión de libros, que da tiempo a mirar el aviso.
        self._interrumpir(ws, f'pasó su plazo de {plazo:g} min sin terminar (CSG_DATASET_PLAZO_MIN)', retomar=False)

    @staticmethod
    def _vivo_en_otro_sitio(dataset: dict) -> bool:
        """RF-42: el proceso guardado sigue vivo con la misma hora de arranque (``proceso_pendiente`` de 096:RF-6).
        Sin identidad, un estado de antes de RF-42, no hay proceso que esperar."""
        proceso = dataset.get('proceso')
        if not isinstance(proceso, dict) or proceso.get('inicio') is None:
            return False
        return proceso_pendiente(proceso)

    def comprobar_regenerando(self, ws) -> bool:
        """RF-43: un «regenerando» que no es de esta web y cuyo proceso ya no vive pasa a interrumpido; devuelve si
        lo hizo. El 2026-11-12 la web se cerró de golpe 47 min después de lanzarlo y quedó así más de 11 h."""
        dataset = ln.leer_estado(carpeta_estado(ws)).get('dataset') or {}
        if dataset.get('estado') != 'regenerando':
            return False
        with self._cv:
            if ws.id in self._procesos or ws.id in self._lanzando:
                return False                     # es de esta web: lo vigila su plazo (RF-45)
        if self._vivo_en_otro_sitio(dataset):
            return False                         # otra web lo tiene en marcha; no se le envía ninguna señal
        self._interrumpir(ws, 'sin proceso vivo: la web que lo regeneraba se cerró o su proceso murió',
                          retomar=self.activa)
        return True

    def recuperar_datasets(self) -> None:
        """RF-46: al arrancar, los «regenerando» de los espacios recientes o abiertos, sin abrir ningún libro."""
        desde = self.ahora() - recientes_h() * 3600
        for fila in self.store.list():
            if fila.get('estado', 'ok') != 'ok':
                continue
            if not self.abierto(fila['id']) and float(fila.get('modified_at') or 0) < desde:
                continue
            ws = self._espacio(fila['id'])
            if ws is None:
                continue
            try:
                self.comprobar_regenerando(ws)
            except Exception:  # noqa: BLE001 - un espacio que no se puede revisar no para el arranque
                log.exception('dataset interrumpido de %s', ws.id)

    def _interrumpir(self, ws, motivo: str, *, retomar: bool = True) -> None:
        """RF-44: desactualizado con el motivo, un aviso en el paso de la demanda y, si se retoma, al carril de fondo."""
        ahora = self.ahora()
        previo: dict = {}

        def poner(e):
            d = e.setdefault('dataset', {})
            previo.update(d)
            d.update(estado='desactualizado', interrumpido=ahora, motivo_interrupcion=motivo)
            d.pop('proceso', None)
            d.pop('servidor', None)
        self._modificar(ws, poner)
        inicio = previo.get('inicio') or previo.get('desde')
        empezada = (time.strftime(' (empezada el %d/%m a las %H:%M)', time.localtime(inicio))
                    if isinstance(inicio, (int, float)) else '')
        sigue = (f'se retoma sola tras {reposo_min():g} min sin trabajos del operador' if retomar else
                 'se retoma al revisar los libros (al abrir el espacio o con «Revisar ahora»)')
        avisos: list[dict] = []
        self._avisar(ws, avisos, 'dataset', f'La regeneración del dataset del pronóstico{empezada} quedó interrumpida: '
                                            f'{motivo}; {sigue}. No se entrenó ningún modelo (104:RF-44).')
        self._guardar_avisos(ws, avisos)
        if retomar:
            with self._cv:
                self._datasets.add(ws.id)
            self._asegurar_hilo()

    def _terminar_dataset(self, ws, libros: list[str], resumen: dict | None, error: str | None) -> None:
        def poner(e):
            d = e.setdefault('dataset', {})
            if error:
                d.update(estado='error', error=error, terminado=self.ahora())
                return
            # Un libro llegado mientras se regeneraba deja el dataset desactualizado por él, no al día.
            llegados = ([x for x in d.get('libros_nuevos') or [] if x not in libros]
                        if d.get('estado') == 'desactualizado' else [])
            d.update(estado='desactualizado' if llegados else 'al_dia', error=None, terminado=self.ahora(),
                     carpeta=str(carpeta_dataset(ws)), libros_incluidos=libros, libros_nuevos=llegados, **resumen)
        self._modificar(ws, poner)
        if not error:
            self._avisar_libros_del_dataset(ws, resumen or {})
        texto = (f'El dataset del pronóstico no se pudo regenerar: {error}.' if error else
                 f"Dataset del pronóstico regenerado ({resumen['huella'][:12]}): {resumen['objetivos']} series, "
                 f"{resumen['apartados']} apartadas; no se entrenó ningún modelo (104:RF-23).")
        ws.events.append('log', {'text': texto})
        self._publicar(ws)


def _regenerar(fuentes, carpeta: Path) -> tuple[dict | None, str | None]:
    from ..pronostico_demanda import regenerar_dataset

    try:
        return regenerar_dataset(fuentes, carpeta), None
    except Exception as exc:  # noqa: BLE001 - el motivo llega al aviso; la web sigue
        return None, f'{type(exc).__name__}: {exc}'
