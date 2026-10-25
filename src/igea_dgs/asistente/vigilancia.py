"""Vigilancia de trabajos, modelos, resultados y pruebas (spec 026, RF-22 a RF-25).

Cada minuto, mientras la web está abierta, mira los trabajos (fallos, tiempos fuera de lo
habitual, colas paradas), los modelos (episodios u órdenes nuevas para reentrenar) y la
calidad de los resultados (flujos que no convergen, calibraciones fuera de tolerancia,
violaciones de la norma). Cada noche corre la suite y el inventario de la spec 009.

Lo que hace sola es lo que no toca la red ni el proyecto: reintentar un fallo transitorio
con remedio conocido (el 4002 de DIgSILENT, spec 019) y reentrenar los modelos con sus
puertas. Lo que escribe en DIgSILENT lo propone como una orden que el operador confirma
(RF-24 sigue a RF-8).
"""
from __future__ import annotations

import ast
import re
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import almacen

#: Fallos con remedio conocido: reintentar (el 4002 de la spec 019).
TRANSITORIOS = (
    re.compile(r'\b4002\b'),
    re.compile(r'licencia.*(ocupada|en uso)', re.IGNORECASE),
)
#: Un trabajo que tarda más que esto veces su mediana (y al menos el mínimo) se avisa.
VECES_MEDIANA = 3.0
MINIMO_LARGO_S = 600.0
COLA_PARADA_S = 600.0


@dataclass
class Aviso:
    clave: str
    nivel: str              # 'info' | 'aviso' | 'error'
    texto: str
    accion: str | None = None           # lo que hace sola: 'reintentar', 'entrenar_gemelo', 'entrenar_asistente'
    propuesta: str | None = None        # una orden que el operador confirma
    trabajo: str | None = None


def revisar_trabajos(trabajos: Iterable[Mapping[str, Any]], ahora: float,
                     reintentados: set[str] | None = None) -> list[Aviso]:
    """Fallos, trabajos largos para lo que suelen tardar y colas paradas (RF-22)."""
    trabajos = list(trabajos)
    reintentados = reintentados or set()
    duraciones: dict[str, list[float]] = {}
    for t in trabajos:
        if t.get('status') == 'done' and t.get('started_at') is not None and t.get('finished_at') is not None:
            duraciones.setdefault(t['kind'], []).append(t['finished_at'] - t['started_at'])
    ocupados = {t.get('lane') for t in trabajos if t.get('status') == 'running'}
    avisos = []
    for t in trabajos:
        estado = t.get('status')
        if estado == 'failed':
            error = str(t.get('error') or '')
            transitorio = any(p.search(error) for p in TRANSITORIOS)
            reintentar = transitorio and t['id'] not in reintentados and not t['title'].endswith('(reintento)')
            avisos.append(Aviso(f"fallo:{t['id']}", 'error', f"Falló «{t['title']}»: {error[:300]}",
                                'reintentar' if reintentar else None, trabajo=t['id']))
        elif estado == 'running' and t.get('started_at') is not None:
            pasado = ahora - t['started_at']
            previas = duraciones.get(t['kind']) or []
            if previas and pasado > max(MINIMO_LARGO_S, VECES_MEDIANA * statistics.median(previas)):
                avisos.append(Aviso(f"largo:{t['id']}", 'aviso',
                                    f"«{t['title']}» lleva {pasado / 60:.0f} min; suele tardar "
                                    f"{statistics.median(previas) / 60:.0f} min.", trabajo=t['id']))
        elif estado == 'queued' and t.get('created_at') is not None \
                and ahora - t['created_at'] > COLA_PARADA_S and t.get('lane') not in ocupados:
            avisos.append(Aviso(f"cola:{t['id']}", 'aviso',
                                f"«{t['title']}» espera desde hace {(ahora - t['created_at']) / 60:.0f} min "
                                'con su carril libre: la cola parece parada.', trabajo=t['id']))
    return avisos


def revisar_modelos(*, episodios_nuevos: int, ordenes_nuevas: int, minimo_episodios: int = 10,
                    minimo_ordenes: int = 20) -> list[Aviso]:
    """Reentrenar cuando hay bastante nuevo (RF-23); las puertas deciden si se promueve."""
    avisos = []
    if episodios_nuevos >= minimo_episodios:
        avisos.append(Aviso(f'gemelo:{episodios_nuevos}', 'info',
                            f'{episodios_nuevos} episodios nuevos del gemelo: se reentrena la PINN.',
                            'entrenar_gemelo'))
    if ordenes_nuevas >= minimo_ordenes:
        avisos.append(Aviso(f'asistente:{ordenes_nuevas}', 'info',
                            f'{ordenes_nuevas} órdenes nuevas confirmadas o corregidas: se reentrena el asistente.',
                            'entrenar_asistente'))
    return avisos


def _recorrer(x: Any, ruta: str = ''):
    if isinstance(x, Mapping):
        for k, v in x.items():
            yield from _recorrer(v, f'{ruta}.{k}' if ruta else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x[:200]):
            yield from _recorrer(v, f'{ruta}[{i}]')
    else:
        yield ruta, x


def revisar_calidad(trabajos: Iterable[Mapping[str, Any]], tolerancia_pct: float = 1.0) -> list[Aviso]:
    """Flujos que no convergen, calibraciones fuera de tolerancia y violaciones en los resultados
    de los trabajos terminados; cada uno con la orden que lo trataría (RF-24)."""
    avisos = []
    for t in trabajos:
        if t.get('status') != 'done' or not isinstance(t.get('result'), Mapping):
            continue
        r = t['result']
        proyecto = r.get('project') or ''
        feeders = ' '.join(r.get('feeders') or [])
        no_converge = [ruta for ruta, v in _recorrer(r) if ruta.split('.')[-1] in ('converge', 'converged')
                       and v is False]
        if no_converge:
            avisos.append(Aviso(f"converge:{t['id']}", 'error',
                                f"«{t['title']}»: {len(no_converge)} flujo(s) sin converger.", trabajo=t['id'],
                                propuesta=f'verifica el caso base de {proyecto} {feeders}'.strip()
                                if proyecto else None))
        fuera = [abs(v) for ruta, v in _recorrer(r) if re.search(r'error_pct$', ruta)
                 and isinstance(v, (int, float)) and abs(v) > tolerancia_pct]
        if fuera:
            avisos.append(Aviso(f"calibracion:{t['id']}", 'aviso',
                                f"«{t['title']}»: {len(fuera)} calibración(es) fuera de ±{tolerancia_pct:g} % "
                                f'(peor {max(fuera):.2f} %).', trabajo=t['id']))
        violaciones = r.get('violaciones')
        if isinstance(violaciones, list) and violaciones and proyecto:
            avisos.append(Aviso(f"norma:{t['id']}", 'aviso',
                                f"«{t['title']}»: {len(violaciones)} violación(es) de la norma.",
                                trabajo=t['id'], propuesta=f'haz el pide de {proyecto} {feeders}'.strip()))
    return avisos


def toca_suite(ahora: datetime, ultima: str | None, hora: int = 22) -> bool:
    """Una vez por noche, a partir de ``hora`` (RF-25)."""
    if ahora.hour < hora:
        return False
    return ultima is None or ultima[:10] != ahora.date().isoformat()


def rf_de_prueba(repo: Path, nodo: str) -> list[str]:
    """Los RF que cita la docstring de una prueba ``tests/x.py::test_y``."""
    fichero, _, nombre = nodo.partition('::')
    nombre = nombre.split('[')[0]
    try:
        arbol = ast.parse((repo / fichero).read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return []
    for n in ast.walk(arbol):
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            return re.findall(r'\d{3}:RF-[\w-]+', ast.get_docstring(n) or '')
    return []


def correr_suite(repo: Path, *, argumentos: Iterable[str] = ('-q', '-rs', '-p', 'no:cacheprovider'),
                 limite_s: float = 4 * 3600, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """La suite en otro proceso; lo que falla, con el RF que cita cada prueba (RF-25)."""
    inicio = time.monotonic()
    try:
        # «-rfE»: sin él, pytest no lista lo que falló y no habría RF que avisar.
        r = subprocess.run([sys.executable, '-m', 'pytest', *argumentos, '-rfE'], cwd=repo, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=limite_s,
                           env=dict(env) if env is not None else None, check=False)
        salida, codigo = r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired as exc:
        salida, codigo = str(exc.stdout or ''), -1
    fallidas = re.findall(r'^(?:FAILED|ERROR) (\S+)', salida, re.MULTILINE)
    resumen = next((linea for linea in reversed(salida.splitlines())
                    if re.search(r'\d+ (passed|failed)', linea)), '')
    fila = {'codigo': codigo, 'resumen': resumen.strip('= '), 'segundos': round(time.monotonic() - inicio),
            'fallidas': [{'prueba': f, 'rf': rf_de_prueba(repo, f)} for f in fallidas],
            'omitidas': len(re.findall(r'^SKIPPED', salida, re.MULTILINE))}
    almacen.anotar('suite', fila)
    return fila


@dataclass
class Vigilante:
    """El ciclo de la web: cada ``intervalo_s``, revisa y actúa con las funciones que le pasan."""

    listar_trabajos: Callable[[], list[dict]]
    reintentar: Callable[[str], Any]
    entrenar_gemelo: Callable[[], Any]
    entrenar_asistente: Callable[[], Any]
    contar_nuevos: Callable[[], tuple[int, int]]
    repo: Path
    intervalo_s: float = 60.0
    hora_suite: int = 22
    reintentados: set[str] = field(default_factory=set)
    vistos: set[str] = field(default_factory=set)
    _parar: threading.Event = field(default_factory=threading.Event)

    def tic(self, ahora: float | None = None, fecha: datetime | None = None) -> list[Aviso]:
        """Una vuelta de vigilancia; devuelve los avisos nuevos (los ya dados no se repiten)."""
        ahora = time.time() if ahora is None else ahora
        trabajos = self.listar_trabajos()
        avisos = revisar_trabajos(trabajos, ahora, self.reintentados) + revisar_calidad(trabajos)
        episodios, ordenes = self.contar_nuevos()
        avisos += revisar_modelos(episodios_nuevos=episodios, ordenes_nuevas=ordenes)
        nuevos = []
        for a in avisos:
            if a.clave in self.vistos:
                continue
            self.vistos.add(a.clave)
            if a.accion == 'reintentar' and a.trabajo:
                self.reintentados.add(a.trabajo)
                self.reintentar(a.trabajo)
            elif a.accion == 'entrenar_gemelo':
                self.entrenar_gemelo()
            elif a.accion == 'entrenar_asistente':
                self.entrenar_asistente()
            almacen.anotar('avisos', asdict(a))
            nuevos.append(a)
        fecha = fecha or datetime.now().astimezone()
        ultima = (almacen.leer('suite', 1) or [{}])[-1].get('fecha')
        if toca_suite(fecha, ultima, self.hora_suite):
            almacen.anotar('suite', {'codigo': None, 'resumen': 'empezada'})
            threading.Thread(target=correr_suite, args=(self.repo,), name='igea-suite', daemon=True).start()
        return nuevos

    def arrancar(self) -> threading.Thread:
        def bucle():
            while not self._parar.wait(self.intervalo_s):
                try:
                    self.tic()
                except Exception as exc:  # noqa: BLE001 - la vigilancia no puede tumbar la web
                    almacen.anotar('avisos', {'clave': 'vigilancia', 'nivel': 'error',
                                              'texto': f'la vigilancia falló: {exc!r}'})

        hilo = threading.Thread(target=bucle, name='igea-vigilancia', daemon=True)
        hilo.start()
        return hilo

    def parar(self) -> None:
        self._parar.set()
