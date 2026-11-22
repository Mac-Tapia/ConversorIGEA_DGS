"""Benchmark de escala de la web y su API con redes sintéticas de 10, 50 y 200 alimentadores (spec 112).

Por qué existe: la web se probó siempre con las redes de prueba de una o pocas decenas de alimentadores, y nadie sabía
cuánto tarda la API ni cuánta memoria toma el proceso cuando una entrega trae 200. El motor ya tenía su guardia de
escala (``test_flexibility_and_scale``), la web no.

Qué mide, para cada tamaño y siempre en local, sin DIgSILENT, sin GPU y sin red:

- la carga de la red (el trabajo «Cargar / listar alimentadores», de punta a punta por la API);
- el tiempo de las peticiones que la pantalla hace al abrir el espacio (p50 y p95 de ``--repeticiones`` llamadas) y
  el tamaño de cada respuesta;
- la memoria pico del proceso (muestreada con psutil mientras corre la medición).

Cada tamaño corre en un proceso propio, así la memoria pico de 200 no arrastra la de 10. Las redes son sintéticas
(``dominio/benchmarks/sintetico.py``), con la misma semilla en todos los tamaños: ningún nombre, código ni coordenada
de una empresa. El resultado lleva la revisión del código con que se midió, para repetirlo sobre el mismo commit.

El dibujo del frontend necesita un navegador real: aquí queda «no medido», con su motivo, nunca como cero. Se mide
aparte con su guion de navegador (``frontend/e2e/escala_dibujo.mjs``, 112 T19), que deja un ``dibujo_<N>.json`` por
tamaño; con ``--dibujo CARPETA`` el resultado enlaza cada tamaño con el suyo, solo si se midió con el mismo commit y la
misma red sintética.

Uso: ``python tools/benchmark_escala_web.py --tamanos 10 50 200 --salida escala.json [--dibujo CARPETA]``
     ``python tools/benchmark_escala_web.py --salida escala.json --dibujo CARPETA --solo-enlazar``
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Self

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))
# La red de la medición, la misma que dibuja el guion de navegador (112 T19).
from convertersmartgrid.dominio.benchmarks.sintetico import (  # noqa: E402
    CARGAS_DE_ESCALA,
    SEMILLA_DE_ESCALA,
    TRAMOS_DE_ESCALA,
    spec_de_escala,
)

TAMANOS_POR_DEFECTO = (10, 50, 200)
FORMATO = 1
#: El dibujo del frontend no se puede medir sin un navegador real (lo que pinta y cuándo lo pinta lo decide él).
RENDER_NO_MEDIDO = ('no medido: el dibujo de la pantalla necesita un navegador real y se mide aparte, con su guion '
                    'de navegador sobre las mismas redes sintéticas')
#: Solo nombra el fichero de la sesión temporal (ningún socket se abre).
PUERTO_DE_LA_SESION = 8791
TERMINALES = ('done', 'parcial', 'no_converge', 'failed', 'cancelled', 'interrumpido')
#: El JSON que deja el guion de navegador de la T19 para cada tamaño, en la carpeta de ``--dibujo``.
NOMBRE_DIBUJO = 'dibujo_{n}.json'
#: Las magnitudes del dibujo que se copian al resultado: cada una con su p50 y su p95, en milisegundos.
MAGNITUDES_DEL_DIBUJO = ('tabla', 'plano')


def percentil(valores: list[float], p: float) -> float:
    """Percentil ``p`` (0-100) con interpolación lineal entre los valores ordenados (el método por defecto de numpy)."""
    if not valores:
        raise ValueError('sin valores')
    orden = sorted(valores)
    pos = (len(orden) - 1) * p / 100.0
    i = int(pos)
    if i + 1 >= len(orden):
        return float(orden[-1])
    return float(orden[i] + (pos - i) * (orden[i + 1] - orden[i]))


class MemoriaPico:
    """Muestrea la memoria residente del proceso en un hilo y guarda el máximo visto."""

    def __init__(self, intervalo_s: float = 0.02):
        import psutil

        self._proc = psutil.Process()
        self._intervalo = intervalo_s
        self._parar = threading.Event()
        self.base = self.pico = self._proc.memory_info().rss
        self._hilo = threading.Thread(target=self._muestrear, daemon=True)

    def _muestrear(self) -> None:
        while not self._parar.is_set():
            self.pico = max(self.pico, self._proc.memory_info().rss)
            self._parar.wait(self._intervalo)

    def __enter__(self) -> Self:
        self._hilo.start()
        return self

    def __exit__(self, *exc) -> None:
        self._parar.set()
        self._hilo.join()
        self.pico = max(self.pico, self._proc.memory_info().rss)


def _aislar_entorno(carpeta: Path) -> None:
    """La medición no toca nada de la máquina: perfil, salidas, turno de DIgSILENT, gemelo y asistente, en temporal.

    Sin perfil de empresa: la red sintética no es de ninguna y ``config/perfil_empresa.json`` no se lee ni se escribe.
    """
    from convertersmartgrid.adaptadores.digital_twin.integration import VARIABLE_CAPTURA
    from convertersmartgrid.adaptadores.pf_arnes import VARIABLE_TURNO
    from convertersmartgrid.aplicacion.obras_pf import VARIABLE_APERTURAS
    from convertersmartgrid.dominio.perfil_empresa import VARIABLE_RUTA
    from convertersmartgrid.dominio.salidas_red import VARIABLE_RUTA_GUARDADAS

    os.environ.update({
        VARIABLE_RUTA: str(carpeta / 'sin_perfil_empresa.json'),
        VARIABLE_RUTA_GUARDADAS: str(carpeta / 'salidas_guardadas.json'),
        VARIABLE_TURNO: str(carpeta / 'powerfactory.turno'),
        VARIABLE_CAPTURA: '0',
        VARIABLE_APERTURAS: str(carpeta / 'aperturas_pf'),
        'CSG_TWIN_DATA': str(carpeta / 'gemelo'),
        'CSG_ASISTENTE_DATA': str(carpeta / 'asistente'),
        'CSG_WEB_FRONTEND': str(carpeta / 'sin_front'),
    })


def _abrir_sesion(carpeta: Path) -> tuple[str, dict[str, str]]:
    """La API se mide con su puerta encendida, como la abre el lanzador: sesión propia en una carpeta temporal.

    El puerto solo nombra el fichero de la sesión: la app se llama en el mismo proceso y no se abre ningún socket, así
    que la web del equipo y su sesión no se tocan.
    """
    from convertersmartgrid.dominio import sesion_web

    os.environ[sesion_web.VARIABLE_CARPETA] = str(carpeta / 'sesiones')
    os.environ[sesion_web.VARIABLE_PUERTO] = str(PUERTO_DE_LA_SESION)
    sesion = sesion_web.crear_sesion(PUERTO_DE_LA_SESION)
    base = f'http://127.0.0.1:{PUERTO_DE_LA_SESION}'
    # Origin, como lo manda el navegador: la puerta rechaza una escritura sin él.
    return base, {sesion_web.CABECERA_TOKEN: sesion.token, 'Origin': base}


def _pedir(respuesta, que: str) -> dict:
    """El cuerpo de una respuesta correcta; si no, un error que dice qué petición fue y qué respondió la web."""
    if respuesta.status_code >= 300:
        raise RuntimeError(f'{que}: la web respondió {respuesta.status_code} {respuesta.text[:300]}')
    return respuesta.json()


def _esperar(cliente, trabajo: dict, tope_s: float) -> dict:
    inicio = time.monotonic()
    while True:
        estado = _pedir(cliente.get(f"/api/jobs/{trabajo['id']}"), 'estado del trabajo')
        if estado['status'] in TERMINALES:
            return estado
        if time.monotonic() - inicio > tope_s:
            raise RuntimeError(f"el trabajo «{trabajo.get('title', trabajo['id'])}» no terminó en {tope_s:.0f} s")
        time.sleep(0.02)


def _cronometrar(cliente, ruta: str, repeticiones: int) -> dict:
    """La primera llamada aparte (la fría: imports y cachés que se llenan) y el p50 y el p95 de las ``repeticiones``
    siguientes. Juntas, la fría se comía el p95 con 10 llamadas y no se sabía si la web era lenta o solo arrancaba."""
    tiempos, octetos = [], 0
    for _ in range(repeticiones + 1):
        t0 = time.perf_counter()
        r = cliente.get(ruta)
        tiempos.append((time.perf_counter() - t0) * 1000.0)
        _pedir(r, ruta)
        octetos = len(r.content)
    fria, calientes = tiempos[0], tiempos[1:]
    return {'n': repeticiones, 'primera_ms': round(fria, 3), 'p50_ms': round(percentil(calientes, 50), 3),
            'p95_ms': round(percentil(calientes, 95), 3), 'max_ms': round(max(calientes), 3),
            'media_ms': round(statistics.fmean(calientes), 3), 'bytes': octetos}


def medir_tamano(alimentadores: int, *, repeticiones: int, semilla: int, tramos: int, cargas: int,
                 tope_s: float) -> dict:
    """Mide un tamaño en este proceso: genera la red, levanta la app y llama a la API como la pantalla."""
    from convertersmartgrid.dominio.benchmarks.sintetico import write_export

    with tempfile.TemporaryDirectory(prefix='csg_escala_', ignore_cleanup_errors=True) as tmp:
        carpeta = Path(tmp)
        _aislar_entorno(carpeta)
        base, cabeceras = _abrir_sesion(carpeta)
        from fastapi.testclient import TestClient

        from convertersmartgrid.presentacion.web import services
        from convertersmartgrid.presentacion.web.app import create_app

        # Se mide la web y su API, no la carga de los modelos del asistente, que es aparte y depende de la máquina.
        services._asistente_modelos = lambda: (None, None)
        spec = spec_de_escala(alimentadores, semilla=semilla, tramos=tramos, cargas=cargas)
        red, carga, equipo = write_export(spec, carpeta / 'export')
        app = create_app(carpeta / 'web')
        # El cliente se presenta desde esta máquina, como el navegador del operador.
        with MemoriaPico() as memoria, TestClient(app, base_url=base, headers=cabeceras,
                                                client=('127.0.0.1', 50000)) as cliente:
            wid = _pedir(cliente.post('/api/workspaces', json={'name': f'escala {alimentadores}'}),
                         'crear el espacio')['id']
            for slot, ruta in (('red', red), ('loads', carga), ('equipment', equipo)):
                with ruta.open('rb') as fh:
                    _pedir(cliente.post(f'/api/workspaces/{wid}/inputs/{slot}', files={'file': (ruta.name, fh)}),
                           f'subir la casilla {slot}')
            t0 = time.perf_counter()
            estado = _esperar(cliente, _pedir(cliente.post(f'/api/workspaces/{wid}/load'), 'cargar la red'), tope_s)
            carga_s = time.perf_counter() - t0
            if estado['status'] != 'done':
                raise RuntimeError(f"la carga terminó «{estado['status']}»: {estado.get('error')}")
            filas = _pedir(cliente.get(f'/api/workspaces/{wid}/feeders'), 'listar los alimentadores')['feeders']
            primero = filas[0].get('network_id') if filas and isinstance(filas[0], dict) else None
            rutas = {'espacio': f'/api/workspaces/{wid}', 'alimentadores': f'/api/workspaces/{wid}/feeders'}
            if primero:
                rutas['sed_de_un_alimentador'] = f'/api/workspaces/{wid}/feeders/{primero}/sed'
            api = {nombre: _cronometrar(cliente, ruta, repeticiones) for nombre, ruta in rutas.items()}
        mib = 1024.0 ** 2
        return {
            'alimentadores': alimentadores,
            'alimentadores_listados': len(filas),
            'tramos': spec.total_sections,
            'cargas': spec.total_loads,
            'carga_red_s': round(carga_s, 3),
            'api': api,
            'ram_base_mib': round(memoria.base / mib, 1),
            'ram_pico_mib': round(memoria.pico / mib, 1),
            'render': {'medido': False, 'motivo': RENDER_NO_MEDIDO},
        }


def _no_medido(motivo: str) -> dict:
    return {'medido': False, 'motivo': f'no medido: {motivo}'}


def _dibujo_del_tamano(medida: dict, red: dict, commit: str | None, carpeta: Path) -> dict:
    """El ``render`` de un tamaño: el dibujo medido por el guion de navegador, o «no medido» con su motivo."""
    n = medida['alimentadores']
    ruta = carpeta / NOMBRE_DIBUJO.format(n=n)
    if not ruta.is_file():
        return _no_medido(f'falta {ruta.name} en {carpeta.as_posix()} (guion frontend/e2e/escala_dibujo.mjs)')
    try:
        dibujo = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:  # justificado: un JSON roto no es un dibujo medido; se dice cuál y por qué
        return _no_medido(f'{ruta.name} no se puede leer: {exc}')
    otro = (dibujo.get('revision') or {}).get('commit')
    if not commit or otro != commit:
        return _no_medido(f'{ruta.name} se midió con el commit {otro}, no con el de la API ({commit})')
    if dibujo.get('alimentadores') != n:
        return _no_medido(f'{ruta.name} es de {dibujo.get("alimentadores")} alimentadores, no de {n}')
    suya = dibujo.get('red_sintetica') or {}
    claves = ('semilla', 'tramos_tipicos', 'cargas_tipicas')
    if any(suya.get(c) != red.get(c) for c in claves):
        return _no_medido(f'{ruta.name} se midió con otra red sintética ({ {c: suya.get(c) for c in claves} })')
    render = {'medido': True, 'json': ruta.as_posix(), 'commit': otro, 'navegador': dibujo.get('navegador'),
              'repeticiones': dibujo.get('repeticiones')}
    for magnitud in MAGNITUDES_DEL_DIBUJO:
        valores = dibujo.get(magnitud) or {}
        p50, p95 = valores.get('p50_ms'), valores.get('p95_ms')
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in (p50, p95)):
            return _no_medido(f'{ruta.name} no trae p50 y p95 positivos de «{magnitud}»')
        render[f'{magnitud}_p50_ms'], render[f'{magnitud}_p95_ms'] = float(p50), float(p95)
    return render


def enlazar_dibujo(resultado: dict, carpeta: Path) -> dict:
    """112:RF-21 (T19): enlaza cada tamaño del resultado con el dibujo medido en el navegador real para ese tamaño.

    Solo se toma un ``dibujo_<N>.json`` medido con el mismo commit, el mismo número de alimentadores y la misma red
    sintética, con p50 y p95 positivos de la tabla y del plano; si no, el tamaño sigue «no medido», con el motivo, y
    nunca con un cero."""
    commit = (resultado.get('revision') or {}).get('commit')
    red = resultado.get('red_sintetica') or {}
    for medida in resultado.get('tamanos') or []:
        medida['render'] = _dibujo_del_tamano(medida, red, commit, carpeta)
    resultado['dibujo'] = carpeta.as_posix()
    return resultado


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(['git', *args], cwd=RAIZ, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def revision_del_codigo() -> dict:
    """Con qué código se midió: el commit, el árbol del índice y si había cambios sin registrar."""
    estado = _git('status', '--porcelain', '--untracked-files=no')
    return {'commit': _git('rev-parse', 'HEAD'), 'arbol_indice': _git('write-tree'),
            'cambios_sin_registrar': None if estado is None else bool(estado)}


def _medir_en_proceso_propio(n: int, args: argparse.Namespace) -> dict:
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), env.get('PYTHONPATH', '')]).rstrip(os.pathsep)
    env['PYTHONIOENCODING'] = 'utf-8'
    orden = [sys.executable, str(Path(__file__).resolve()), '--un-tamano', str(n), '--repeticiones',
             str(args.repeticiones), '--semilla', str(args.semilla), '--tramos', str(args.tramos), '--cargas',
             str(args.cargas), '--tope', str(args.tope)]
    r = subprocess.run(orden, capture_output=True, text=True, encoding='utf-8', env=env, timeout=args.tope * 2 + 120,
                       check=False)
    if r.returncode != 0:
        raise RuntimeError(f'la medición de {n} alimentadores falló:\n{r.stderr.strip()[-2000:]}')
    return json.loads(r.stdout.strip().splitlines()[-1])


def _tamano(texto: str) -> int:
    n = int(texto)
    if n < 1:
        raise argparse.ArgumentTypeError('el número de alimentadores es al menos 1')
    return n


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=('Benchmark de escala de la web y su API con redes sintéticas (sin datos de ninguna empresa): '
                     'carga de la red, p50 y p95 de las peticiones de la pantalla y memoria pico del proceso, para '
                     'cada número de alimentadores. Corre en local, sin DIgSILENT, sin GPU y sin red.'))
    p.add_argument('--tamanos', nargs='+', type=_tamano, default=list(TAMANOS_POR_DEFECTO),
                   help='números de alimentadores a medir (por defecto 10 50 200)')
    p.add_argument('--repeticiones', type=int, default=30,
                   help='llamadas por petición para el p50 y el p95, tras la primera, que se da aparte (30)')
    p.add_argument('--semilla', type=int, default=SEMILLA_DE_ESCALA,
                   help=f'semilla de las redes sintéticas, la misma en cada tamaño ({SEMILLA_DE_ESCALA})')
    p.add_argument('--tramos', type=int, default=TRAMOS_DE_ESCALA,
                   help=f'tramos típicos por alimentador ({TRAMOS_DE_ESCALA})')
    p.add_argument('--cargas', type=int, default=CARGAS_DE_ESCALA,
                   help=f'cargas típicas por alimentador ({CARGAS_DE_ESCALA})')
    p.add_argument('--tope', type=float, default=1800.0, help='segundos máximos de la carga de la red por tamaño')
    p.add_argument('--salida', type=Path, help='JSON del resultado; sin ella, se escribe en la salida estándar')
    p.add_argument('--dibujo', type=Path, help='carpeta con los dibujo_<N>.json del guion de navegador, que se enlazan')
    p.add_argument('--solo-enlazar', action='store_true',
                   help='no mide: enlaza el dibujo con el resultado que ya está en --salida')
    p.add_argument('--un-tamano', type=_tamano, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.repeticiones < 2:
        p.error('hacen falta al menos 2 repeticiones para un percentil')
    if args.solo_enlazar and not (args.salida and args.dibujo):
        p.error('--solo-enlazar necesita --salida (el resultado que ya existe) y --dibujo')
    return args


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.un_tamano is not None:
        resultado = medir_tamano(args.un_tamano, repeticiones=args.repeticiones, semilla=args.semilla,
                                 tramos=args.tramos, cargas=args.cargas, tope_s=args.tope)
        print(json.dumps(resultado, ensure_ascii=False))
        return 0
    from convertersmartgrid.dominio.util import write_json_atomic

    if args.solo_enlazar:
        try:
            resultado = json.loads(args.salida.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:  # justificado: sin resultado que enlazar no se escribe nada; se dice por qué
            print(f'Error: no se puede leer {args.salida}: {exc}', file=sys.stderr)
            return 1
        write_json_atomic(args.salida, enlazar_dibujo(resultado, args.dibujo))
        for medida in resultado['tamanos']:
            print(f"{medida['alimentadores']} alimentadores: dibujo "
                  f"{'medido' if medida['render']['medido'] else medida['render']['motivo']}", file=sys.stderr)
        return 0
    import psutil

    resultado = {
        'formato': FORMATO,
        'herramienta': 'tools/benchmark_escala_web.py',
        'medido': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'revision': revision_del_codigo(),
        'equipo': {'python': platform.python_version(), 'sistema': platform.platform(), 'cpu': os.cpu_count(),
                   'ram_total_mib': round(psutil.virtual_memory().total / 1024.0 ** 2)},
        'red_sintetica': {'semilla': args.semilla, 'tramos_tipicos': args.tramos, 'cargas_tipicas': args.cargas,
                          'generador': 'convertersmartgrid.dominio.benchmarks.sintetico'},
        'repeticiones': args.repeticiones,
        'tamanos': [],
    }
    for n in args.tamanos:
        try:
            medida = _medir_en_proceso_propio(n, args)
        except (RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            print(f'Error: {exc}', file=sys.stderr)
            return 1
        resultado['tamanos'].append(medida)
        print(f"{n} alimentadores: carga {medida['carga_red_s']} s, alimentadores p95 "
              f"{medida['api']['alimentadores']['p95_ms']} ms, memoria pico {medida['ram_pico_mib']} MiB",
              file=sys.stderr)
    if args.dibujo:
        enlazar_dibujo(resultado, args.dibujo)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(args.salida, resultado)
    else:
        print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
