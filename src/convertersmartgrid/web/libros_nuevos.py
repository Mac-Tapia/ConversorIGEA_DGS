"""La web reconoce sola los libros nuevos de demanda de cada espacio (spec 104).

Antes solo se reindexaba al pulsar «Actualizar índice»: el libro de octubre de 2026 de clientes importantes llegó a la
carpeta y lo revisó Claude a mano. Aquí se vigila al arrancar, al abrir un espacio y cada cierto tiempo; se reindexa lo
que cambió, se verifica cada libro nuevo con ``convertersmartgrid.libros_nuevos`` y se avisa en el registro y en un aviso
del espacio. El dataset del pronóstico se marca desactualizado y se regenera en un proceso aparte, sin entrenar.

Comparar fotos solo lista ficheros (P7); lo que abre libros va en un trabajo de la cola (RF-3) o en el proceso del
dataset. Nada bloquea: lo que falla se dice y se sigue.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .. import libros_nuevos as ln
from . import services
from .requisitos import UserError

log = logging.getLogger(__name__)

VARIABLE_INTERVALO = 'CSG_LIBROS_INTERVALO_MIN'
#: La pone ``__main__``: solo el servidor real vigila; las pruebas crean la aplicación a cientos (como 026:RF-22).
VARIABLE_ACTIVA = 'CSG_LIBROS_NUEVOS'
INTERVALO_MIN = 10.0
#: RF-19: libros que se verifican por reconocimiento; los demás se dicen.
TOPE_VERIFICADOS = 3
#: Al abrir un espacio no se mira más de una vez por minuto.
ESPERA_AL_ABRIR_S = 60.0
TIPOS = ('cabecera', 'clientes', 'suministros', 'medidores')
ETIQUETAS = {'cabecera': 'cabecera', 'clientes': 'clientes importantes', 'suministros': 'suministros',
             'medidores': 'medidores'}
KIND = 'libros_nuevos'


def intervalo_min() -> float:
    """RF-2: 10 minutos por defecto; ``0`` apaga la revisión periódica."""
    try:
        return max(0.0, float(os.environ.get(VARIABLE_INTERVALO, INTERVALO_MIN)))
    except ValueError:
        return INTERVALO_MIN


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


class VigilanciaLibros:
    """Revisa las fuentes de demanda de los espacios y reconoce lo nuevo (RF-1 a RF-6)."""

    def __init__(self, store, jobs, *, en_fondo: bool = True, ahora: Callable[[], float] = time.time):
        self.store, self.jobs, self.ahora = store, jobs, ahora
        self.en_fondo = en_fondo
        self.activa = os.environ.get(VARIABLE_ACTIVA) == '1'
        self._locks: dict[str, threading.Lock] = {}
        self._abierto_en: dict[str, float] = {}
        self._procesos: dict[str, Any] = {}
        self._guard = threading.Lock()

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

    def estado(self, ws) -> dict[str, Any]:
        """Lo que ve el operador: los avisos sin dar por vistos, la última revisión y el dataset (RF-20, RF-22)."""
        e = ln.leer_estado(carpeta_estado(ws))
        intervalo = intervalo_min()
        ultima = e.get('ultima_revision')
        return {
            'avisos': [a for a in e.get('avisos') or [] if not a.get('visto')],
            'ultima_revision': ultima,
            'proxima_revision': (ultima + intervalo * 60) if (ultima and intervalo) else None,
            'intervalo_min': intervalo,
            'repetidos': sorted(e.get('repetidos') or {}),
            'dataset': e.get('dataset'),
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
    def pendientes(self, ws) -> dict[str, dict]:
        """Por fuente, los libros nuevos, cambiados y retirados frente al último reconocimiento (RF-1, RF-6)."""
        e = ln.leer_estado(carpeta_estado(ws))
        fotos = e.get('fotos') or {}
        salida = {}
        for tipo in TIPOS:
            meta = (ws.demanda or {}).get(tipo)
            if not meta or not meta.get('path'):
                continue
            foto = ln.foto_de_fuente(meta['path'])
            previa = fotos.get(tipo)
            conocidos = ({rel: (size, mtime) for rel, size, mtime in previa} if previa is not None
                         else conocidos_del_indice(tipo, meta, foto))
            c = ln.cambios(conocidos, foto)
            if any(c.values()):
                salida[tipo] = {**c, 'foto': [list(x) for x in foto]}
        return salida

    def revisar(self, ws) -> dict | None:
        """Compara y, si hay algo nuevo y el motor está libre, encola el reconocimiento (RF-3 a RF-5)."""
        try:
            pendientes = self.pendientes(ws)
        except OSError as exc:              # la unidad de los libros no está: se dirá en la próxima
            log.warning('libros nuevos de %s: %s', ws.id, exc)
            return None
        self._modificar(ws, lambda e: e.update(ultima_revision=self.ahora()))
        if not pendientes:
            self._regenerar_si_toca(ws)
            return None
        if any(j.lane == 'engine' for j in self.jobs.active(ws.id)):
            return None                    # RF-4: se intenta en la revisión siguiente
        job = self.jobs.submit(ws.id, KIND, 'Reconocer libros nuevos de demanda',
                               lambda ctx: self.reconocer(ws, ctx, pendientes), lane='engine')
        return job.public()

    def al_abrir(self, ws) -> None:
        """RF-1: al abrir un espacio, sin hacer esperar a la página."""
        if not self.activa:
            return
        ahora = self.ahora()
        if ahora - self._abierto_en.get(ws.id, 0.0) < ESPERA_AL_ABRIR_S:
            return
        self._abierto_en[ws.id] = ahora
        threading.Thread(target=self._revisar_sin_fallar, args=(ws,), daemon=True, name='csg-libros-nuevos').start()

    def _revisar_sin_fallar(self, ws) -> None:
        try:
            self.revisar(ws)
        except Exception:  # noqa: BLE001 - un hilo de vigilancia no tumba la web; queda en el registro del servidor
            log.exception('revisión de libros nuevos de %s', ws.id)

    def revisar_todos(self) -> None:
        for fila in self.store.list():
            if fila.get('estado', 'ok') != 'ok':
                continue
            try:
                ws = self.store.get(fila['id'])
            except Exception:  # noqa: BLE001 - un espacio que no abre lo dice su propio aviso (086:RF-2)
                continue
            if ws is not None and ws.demanda:
                self._revisar_sin_fallar(ws)

    async def vigilar(self, detener: asyncio.Event) -> None:
        """Al arrancar y cada intervalo; la espera se corta al apagar la web (RF-1, RF-2)."""
        if not self.activa:
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

    def parar(self) -> None:
        for proc in list(self._procesos.values()):
            if proc.is_alive():
                proc.terminate()

    # ------------------------------------------------------------------ reconocer (en un trabajo)
    def reconocer(self, ws, ctx, pendientes: dict[str, dict]) -> dict[str, Any]:
        """Reindexa lo que cambió, verifica los libros nuevos y lo avisa (RF-5, RF-7 a RF-20)."""
        avisos: list[dict] = []

        def avisar(tipo: str, texto: str, libro: str | None = None, ficha: dict | None = None) -> None:
            ctx.log(texto)
            avisos.append({'id': uuid.uuid4().hex[:12], 'tipo': tipo, 'libro': libro, 'texto': texto,
                           'cuando': self.ahora(), 'visto': False, 'ficha': ficha})

        hechos: dict[str, list] = {}
        for tipo, c in pendientes.items():
            ctx.check_cancel()
            nuevos = c['nuevos'] + c['cambiados']
            for rel in c['retirados']:
                avisar(tipo, f'Ya no está {rel} en la carpeta de {ETIQUETAS[tipo]}.', rel)
            try:
                if tipo == 'clientes':
                    services.demanda_clientes_indexar(ws, ctx)
                elif tipo == 'cabecera':
                    services.demanda_cabecera_indexar(ws, ctx)
                elif tipo == 'suministros':
                    meta = ws.demanda['suministros']
                    services.demanda_asignar(ws, 'suministros', Path(meta['path']), meta.get('origin', 'server'))
                    elegido = ws.demanda['suministros'].get('seleccion')
                    for rel in nuevos:
                        avisar(tipo, f'Llegó {rel} a suministros; se usa {elegido or "ninguno"}.', rel)
                else:
                    for rel in nuevos:
                        avisar(tipo, f'Cambió el libro de medidores {rel}: las equivalencias se leen de él.', rel)
            except UserError as exc:
                avisar(tipo, f'{ETIQUETAS[tipo].capitalize()}: no se pudo reindexar ({exc}); se sigue con el índice anterior.')
                continue
            hechos[tipo] = nuevos
        verificar = [('clientes', rel) for rel in hechos.get('clientes', [])] + [('cabecera', rel) for rel in hechos.get('cabecera', [])]
        verificar.sort(key=lambda x: self._mes_de(ws, *x) or '', reverse=True)     # RF-19: lo más reciente primero
        for tipo, rel in verificar[:TOPE_VERIFICADOS]:
            ctx.check_cancel()
            ctx.log(f'Verificando {rel}…')
            if tipo == 'clientes':
                ficha = self._verificar_clientes(ws, rel)
                texto = ln.mensaje_de_clientes(ficha)
                if ficha.get('copia_de'):
                    self._marcar_repetido(ws, rel, texto)
            else:
                ficha = ln.verificar_libro_cabecera(Path(ws.demanda['cabecera']['path']) / rel
                                                    if Path(ws.demanda['cabecera']['path']).is_dir()
                                                    else Path(ws.demanda['cabecera']['path']), rel, services.demanda_alias())
                texto = ln.mensaje_de_cabecera(ficha)
            avisar(tipo, texto, rel, {k: v for k, v in ficha.items() if k != 'codigos'})
        if len(verificar) > TOPE_VERIFICADOS:
            resto = [rel for _t, rel in verificar[TOPE_VERIFICADOS:]]
            avisar('clientes', f'Quedan {len(resto)} libros sin verificar ({", ".join(resto[:10])}): se indexaron y '
                               'se verifican en las próximas revisiones.')
        nuevos_dataset = [f'{t}/{rel}' for t in ('cabecera', 'clientes') for rel in hechos.get(t, [])]

        def guardar(e):
            fotos = e.setdefault('fotos', {})
            # RF-19: los que quedan sin verificar no entran en la foto: la próxima revisión los vuelve a ver.
            sin_verificar = {rel for _t, rel in verificar[TOPE_VERIFICADOS:]}
            for tipo in hechos:
                fotos[tipo] = [x for x in pendientes[tipo]['foto'] if x[0] not in sin_verificar]
            e['avisos'] = [*(e.get('avisos') or []), *avisos][-100:]
            if nuevos_dataset:                       # RF-22
                previo = e.get('dataset') or {}
                e['dataset'] = {**previo, 'estado': 'desactualizado', 'desde': self.ahora(),
                                'libros_nuevos': sorted({*(previo.get('libros_nuevos') or [] if previo.get('estado') == 'desactualizado' else []),
                                                         *nuevos_dataset})}
        self._modificar(ws, guardar)
        self._regenerar_si_toca(ws)
        return {'fuentes': sorted(hechos), 'avisos': [a['texto'] for a in avisos]}

    def _mes_de(self, ws, tipo: str, rel: str) -> str | None:
        if tipo != 'clientes':
            return None
        return next((x.get('mes') for x in (ws.demanda.get('clientes') or {}).get('catalogo') or [] if x.get('nombre') == rel), None)

    def _verificar_clientes(self, ws, rel: str) -> dict:
        from ..demanda_medida import DemandaError, curvas_de_clientes, descubrir_libro_suministros

        meta = ws.demanda['clientes']
        raiz = Path(meta['path'])
        catalogo = meta.get('catalogo') or []
        fila = next((x for x in catalogo if x.get('nombre') == rel), {})
        mes = fila.get('mes')
        path = raiz / rel if raiz.is_dir() else raiz
        otros = {x['mes']: x['nombre'] for x in catalogo if x.get('activo') and x.get('mes') and x.get('nombre') != rel}
        anterior, mes_previo = None, None
        if mes:
            mes_previo = ln.mes_anterior(mes)
            previo = otros.get(mes_previo)
            if previo:
                try:
                    anterior, _notas = curvas_de_clientes(raiz / previo, None, mes=mes_previo)
                except Exception as exc:  # noqa: BLE001 - sin el mes anterior se verifica lo demás (RF-18)
                    log.warning('mes anterior %s: %s', previo, exc)
        suministros, nombre_sum = None, None
        sumi = (ws.demanda or {}).get('suministros')
        if services.hay_suministros(ws):
            try:
                libro = Path(sumi['path'])
                libro = descubrir_libro_suministros(libro, services.demanda_alias()) if libro.is_dir() else libro
                suministros, nombre_sum = ln.suministros_del_libro(libro, services.demanda_alias()), libro.name
            except (DemandaError, OSError, ValueError) as exc:
                log.warning('suministros: %s', exc)
        return ln.verificar_libro_clientes(path, mes, origen=fila.get('origen_mes'), anio=fila.get('anio'),
                                           anterior=anterior, mes_previo=mes_previo, suministros=suministros,
                                           nombre_suministros=nombre_sum, meses_de_otros=otros)

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
    def _regenerar_si_toca(self, ws) -> None:
        """RF-23: con el dataset desactualizado, se regenera aparte y sin entrenar."""
        e = ln.leer_estado(carpeta_estado(ws))
        dataset = e.get('dataset') or {}
        if dataset.get('estado') != 'desactualizado':
            return
        proc = self._procesos.get(ws.id)
        if proc is not None and proc.is_alive():
            return
        demanda = ws.demanda or {}
        if not demanda.get('cabecera') or not demanda.get('medidores'):
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
                          suministros=suministros, patron_clientes=services.perfil_de(ws).patron_libro_clientes)
        libros = list(dataset.get('libros_nuevos') or [])
        self._modificar(ws, lambda e: e.setdefault('dataset', {}).update(estado='regenerando', inicio=self.ahora()))
        ws.events.append('log', {'text': 'Regenerando el dataset del pronóstico con los libros nuevos (sin entrenar)…'})
        if not self.en_fondo:
            self._terminar_dataset(ws, libros, *_regenerar(fuentes, carpeta_dataset(ws)))
            return
        contexto = mp.get_context('spawn')
        cola = contexto.Queue()
        proc = contexto.Process(target=_regenerar_en_hijo, args=(fuentes, carpeta_dataset(ws), cola), daemon=True,
                                name=f'csg-dataset-{ws.id[:6]}')
        proc.start()
        self._procesos[ws.id] = proc

        def esperar():
            resultado = (None, 'el proceso terminó sin resultado')
            while True:
                try:
                    resultado = cola.get(timeout=5)
                    break
                except Exception:  # noqa: BLE001 - queue.Empty: sigue esperando mientras viva
                    if not proc.is_alive():
                        break
            proc.join(timeout=5)
            self._terminar_dataset(ws, libros, *resultado)
        threading.Thread(target=esperar, daemon=True, name='csg-dataset-espera').start()

    def _terminar_dataset(self, ws, libros: list[str], resumen: dict | None, error: str | None) -> None:
        def poner(e):
            d = e.setdefault('dataset', {})
            if error:
                d.update(estado='error', error=error, terminado=self.ahora())
            else:
                d.update(estado='al_dia', error=None, terminado=self.ahora(), carpeta=str(carpeta_dataset(ws)),
                         libros_incluidos=libros, libros_nuevos=[], **resumen)
        self._modificar(ws, poner)
        texto = (f'El dataset del pronóstico no se pudo regenerar: {error}.' if error else
                 f"Dataset del pronóstico regenerado ({resumen['huella'][:12]}): {resumen['objetivos']} series, "
                 f"{resumen['apartados']} apartadas; no se entrenó ningún modelo (104:RF-23).")
        ws.events.append('log', {'text': texto})


def _regenerar(fuentes, carpeta: Path) -> tuple[dict | None, str | None]:
    from ..pronostico_demanda import regenerar_dataset

    try:
        return regenerar_dataset(fuentes, carpeta), None
    except Exception as exc:  # noqa: BLE001 - el motivo llega al aviso; la web sigue
        return None, f'{type(exc).__name__}: {exc}'


def _regenerar_en_hijo(fuentes, carpeta: Path, cola) -> None:
    cola.put(_regenerar(fuentes, carpeta))
