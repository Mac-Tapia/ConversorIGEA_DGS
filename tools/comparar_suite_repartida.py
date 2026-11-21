"""La suite entera con N = 1, 2 y 3 procesos sobre el MISMO árbol, y la comparación prueba a prueba (102:RF-5, T20).

``PROCESOS_MAXIMOS`` de ``tools/puerta_calidad.py`` sigue en 1 hasta que esta comparación diga «iguales» con los datos
reales: con -n 2 hubo pruebas que caían (ensayos de la 106:RF-16 del 2026-11-13) y ``GIB_POR_PROCESO`` es provisional.
Cada N corre por la propia puerta del árbol (``_pytest(..., procesos=N)``, las mismas sesiones «serie», «reparto» y
«a_solas» y las mismas variables que ``--arbol``), sin escribir ningún veredicto en ``.git``. Mientras corre:

- un hilo mide cada ``--intervalo`` segundos el árbol de procesos con psutil: la memoria PRIVADA de cada proceso (en
  Windows el conjunto de trabajo, el RSS, se recorta y engaña: el 20-11 la puerta daba 1,9 GiB de RSS y 4,2 de
  privada), la suma del árbol y la memoria libre mínima del equipo; deja ``n<N>_memoria.csv``;
- un complemento de pytest, escrito en la salida y cargado con ``-p``, anota la memoria, los hilos vivos y, con
  ``--objetos``, los objetos de Python de cada proceso de pytest al acabar cada fichero (``n<N>_por_fichero.tsv``):
  dice qué fichero deja memoria o hilos sin soltar.

Uso:

    python tools/comparar_suite_repartida.py --salida CARPETA [--n 1 2 3] [--pruebas "tests/a.py tests/b.py"]
        [--candado CARPETA --quien TEXTO] [--no-lanzar-si-existe RUTA ...] [--objetos] [--sin-memoria-por-fichero]
    python tools/comparar_suite_repartida.py --salida CARPETA --solo-comparar

``--pruebas`` corre solo esas (los ensayos cortos); sin ella, la suite entera. ``--candado`` crea la carpeta (falla si
ya existe), escribe en ella ``quien`` y la retira al terminar. ``--no-lanzar-si-existe`` no empieza, ni empieza la N
siguiente, si existe esa ruta (la pausa de una puerta, por ejemplo). Deja en la salida ``n<N>.json`` (resumen y el
veredicto de cada prueba), los junit de cada sesión, ``comparacion.json`` y ``comparacion.txt``.

«iguales» exige, para cada N corrida frente a la menor: las mismas pruebas con el mismo veredicto, 0 fallidas, 0
omitidas, la libre mínima ≥ 1,5 GiB, el mismo árbol y el disco del worktree sin ficheros nuevos ni cambiados (una
prueba que escribe en el árbol estorba a las sesiones que corren a la vez). Propone ``GIB_POR_PROCESO``: la mayor
memoria privada de un proceso de pytest con N ≥ 2 (o con N = 1 si es la única), con un 15 % de margen, redondeada a
0,25 GiB por arriba. Sale con 0 si son iguales, 1 si no y 2 si no pudo empezar.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import sys
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
#: Condición de 0d del 15-11 para la suite repartida: el pico deja al menos esto libre.
LIBRE_MINIMA_GIB = 1.5
MARGEN_POR_PROCESO = 1.15
#: Lo que no es un cambio del árbol: lo que Python compila al importar.
NO_CUENTA_EN_EL_ARBOL = ('__pycache__', '.pyc')
#: El trabajador de xdist arranca con esta orden (execnet, popen).
ORDEN_DE_TRABAJADOR = 'exec(eval(sys.stdin.readline()))'
VARIABLE_MEMORIA = 'CSG_T20_MEMORIA'
VARIABLE_OBJETOS = 'CSG_T20_OBJETOS'
NOMBRE_COMPLEMENTO = 'csg_t20_memoria_por_fichero'

COMPLEMENTO = '''"""Memoria de cada proceso de pytest al acabar cada fichero (tools/comparar_suite_repartida.py, 102 T20)."""
import gc
import json
import os
import threading
import time

import psutil

_DESTINO = os.environ.get('{variable}')
_OBJETOS = os.environ.get('{objetos}') == '1'
_ESTADO = {{'fichero': None, 'controlador': False}}
_PROCESO = psutil.Process()


def _anotar(fichero):
    if not _DESTINO or fichero is None or _ESTADO['controlador']:
        return
    m = _PROCESO.memory_info()
    fila = {{'t': round(time.time(), 1), 'pid': os.getpid(), 'trabajador': os.environ.get('PYTEST_XDIST_WORKER', ''),
            'fichero': fichero, 'rss_mib': round(m.rss / 2**20),
            'privada_mib': round(getattr(m, 'private', m.rss) / 2**20), 'hilos': threading.active_count()}}
    if _OBJETOS:
        fila['objetos'] = len(gc.get_objects())
    with open(os.path.join(_DESTINO, f'memoria_{{os.getpid()}}.jsonl'), 'a', encoding='utf-8') as f:
        f.write(json.dumps(fila) + chr(10))


def pytest_configure(config):
    # El controlador de xdist recibe los informes de sus trabajadores: su memoria no es la de esos ficheros.
    _ESTADO['controlador'] = bool(getattr(config.option, 'numprocesses', None)) and not os.environ.get(
        'PYTEST_XDIST_WORKER')


def pytest_runtest_logstart(nodeid, location):
    fichero = nodeid.split('::', 1)[0]
    if fichero != _ESTADO['fichero']:
        _anotar(_ESTADO['fichero'])
        _ESTADO['fichero'] = fichero


def pytest_sessionfinish(session, exitstatus):
    _anotar(_ESTADO['fichero'])
'''.format(variable=VARIABLE_MEMORIA, objetos=VARIABLE_OBJETOS)


def cargar_puerta(raiz: Path):
    """La puerta del árbol que se compara, no la de quien lanza."""
    if str(raiz / 'src') not in sys.path:
        sys.path.insert(0, str(raiz / 'src'))
    spec = importlib.util.spec_from_file_location('puerta_calidad_t20', raiz / 'tools' / 'puerta_calidad.py')
    modulo = importlib.util.module_from_spec(spec)
    sys.modules['puerta_calidad_t20'] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _privada(memoria) -> int:
    """La memoria privada (Windows: ``private``); en otros sistemas, el RSS."""
    return int(getattr(memoria, 'private', 0) or memoria.rss)


def etiqueta_de(argumentos: list[str], etiqueta_del_padre: str | None) -> str:
    """La sesión de un proceso por su orden: ``--junitxml=…junit.<sesión>.xml`` (``suite`` con N = 1), un trabajador de
    xdist de la sesión de su padre, o un hijo que lanzó una prueba."""
    for a in argumentos:
        if a.startswith('--junitxml='):
            nombre = Path(a.split('=', 1)[1]).name
            partes = nombre.split('.')
            return partes[1] if len(partes) == 3 else 'suite'
    # El python del .venv de Windows es un lanzador que abre el intérprete real con la misma orden: el hijo del lanzador
    # lleva su misma etiqueta, no una más.
    padre = etiqueta_del_padre or '?'
    tipo = '/trabajador' if any(ORDEN_DE_TRABAJADOR in a for a in argumentos) else '/hijo'
    return padre if padre.endswith(tipo) else padre + tipo


def es_de_pytest(etiqueta: str) -> bool:
    return not etiqueta.endswith('/hijo')


class Medidor(threading.Thread):
    """El árbol de procesos de este proceso, cada ``intervalo`` segundos, con su memoria privada."""

    def __init__(self, csv_salida: Path, intervalo: float = 2.0):
        super().__init__(daemon=True)
        import psutil

        self.psutil = psutil
        self.fin = threading.Event()
        self.intervalo = intervalo
        self.csv = csv_salida
        self.pico_arbol = 0
        self.pico_por_etiqueta: dict[str, int] = {}
        self.libre_min = psutil.virtual_memory().available
        self.procesos_max = 0
        self._etiquetas: dict[tuple[int, float], str] = {}

    def _etiqueta(self, pid: int, vivos: dict) -> str | None:
        """La del proceso y, antes, la de su padre si es del árbol (en Windows los pid no crecen con la edad, y un pid
        se reutiliza: la clave lleva la hora de creación)."""
        proceso = vivos.get(pid)
        if proceso is None:
            return None
        try:
            clave = (pid, proceso.create_time())
            if clave not in self._etiquetas:
                self._etiquetas[clave] = etiqueta_de(proceso.cmdline(), self._etiqueta(proceso.ppid(), vivos))
        except self.psutil.Error:
            return '?'
        return self._etiquetas[clave]

    def run(self):
        yo = self.psutil.Process()
        inicio = time.monotonic()
        with self.csv.open('w', newline='', encoding='utf-8') as f:
            escritor = csv.writer(f)
            escritor.writerow(['t_s', 'pid', 'etiqueta', 'rss_mib', 'privada_mib', 'libre_mib'])
            while not self.fin.is_set():
                try:
                    hijos = yo.children(recursive=True)
                except self.psutil.Error:
                    hijos = []
                libre = self.psutil.virtual_memory().available
                self.libre_min = min(self.libre_min, libre)
                suma = 0
                t = round(time.monotonic() - inicio, 1)
                vivos = {h.pid: h for h in hijos}
                for h in hijos:
                    try:
                        m = h.memory_info()
                    except self.psutil.Error:
                        continue
                    etiqueta = self._etiqueta(h.pid, vivos) or '?'
                    privada = _privada(m)
                    suma += privada
                    if es_de_pytest(etiqueta):
                        self.pico_por_etiqueta[etiqueta] = max(self.pico_por_etiqueta.get(etiqueta, 0), privada)
                    escritor.writerow([t, h.pid, etiqueta, m.rss >> 20, privada >> 20, libre >> 20])
                self.pico_arbol = max(self.pico_arbol, suma)
                self.procesos_max = max(self.procesos_max, len(hijos))
                f.flush()
                self.fin.wait(self.intervalo)


def veredictos_de(junits: list[Path]) -> dict[str, str]:
    """``classname::name`` → passed, failed, error o skipped, de todos los junit de una corrida."""
    salida: dict[str, str] = {}
    for junit in junits:
        for caso in ET.parse(junit).iter('testcase'):
            nombre = f"{caso.get('classname', '')}::{caso.get('name', '')}"
            estado = next((e for e in ('failure', 'error', 'skipped') if caso.find(e) is not None), 'passed')
            salida[nombre] = 'failed' if estado == 'failure' else estado
    return salida


def segundos_por_sesion(junits: list[Path]) -> dict[str, float]:
    """El tiempo de pruebas de cada sesión, del ``time`` de su junit (``<nombre>.<sesión>.junit.xml``)."""
    salida = {}
    for junit in junits:
        raiz = ET.parse(junit).getroot()
        suite = raiz if raiz.tag == 'testsuite' else raiz.find('testsuite')
        salida[junit.name.split('.')[-3]] = round(float((suite.get('time') if suite is not None else 0) or 0), 1)
    return salida


#: Carpetas que no se recorren: git, los entornos (en un worktree, uniones al del checkout) y las dependencias del
#: frontend. Lo demás, también lo ignorado (output/, input/), cuenta: es lo que comparten las sesiones a la vez.
NO_SE_RECORRE = frozenset({'.git', '.venv', '.venv_mcp', '.venv-ml', 'node_modules', '__pycache__', '.ruff_cache'})


def estado_del_arbol(raiz: Path, fuera: Path | None = None) -> dict[str, tuple[int, int]]:
    """Cada fichero del disco del worktree con su tamaño y su fecha, sin lo que compila Python ni ``fuera`` (la salida
    de esta herramienta, si se pone dentro del worktree)."""
    estado = {}
    fuera_txt = os.path.normcase(str(fuera)) if fuera is not None else None
    for carpeta, subcarpetas, ficheros in os.walk(raiz):
        subcarpetas[:] = [d for d in subcarpetas if d not in NO_SE_RECORRE
                          and not os.path.isjunction(os.path.join(carpeta, d))
                          and os.path.normcase(os.path.join(carpeta, d)) != fuera_txt]
        for nombre in ficheros:
            if nombre.endswith(NO_CUENTA_EN_EL_ARBOL):
                continue
            ruta = os.path.join(carpeta, nombre)
            try:
                s = os.stat(ruta)
            except OSError:
                continue
            estado[os.path.relpath(ruta, raiz).replace(os.sep, '/')] = (s.st_size, s.st_mtime_ns)
    return estado


def cambios_del_disco(antes: dict, despues: dict) -> list[str]:
    """Lo que apareció, desapareció o cambió en el disco durante la corrida."""
    return sorted([f'+ {r}' for r in despues.keys() - antes.keys()] + [f'- {r}' for r in antes.keys() - despues.keys()]
                  + [f'~ {r}' for r in antes.keys() & despues.keys() if antes[r] != despues[r]])


def memoria_por_fichero(carpeta: Path) -> list[dict]:
    """Las filas del complemento, con lo que cada fichero añadió a su proceso frente al fichero anterior."""
    filas = []
    for ruta in sorted(carpeta.glob('memoria_*.jsonl')):
        propias = [json.loads(linea) for linea in ruta.read_text(encoding='utf-8').splitlines() if linea.strip()]
        propias.sort(key=lambda x: x['t'])
        # El primer fichero de cada proceso carga además los módulos y el conftest: su delta es 0 y su memoria, la
        # columna privada_mib.
        anterior = propias[0] if propias else None
        for fila in propias:
            fila['delta_privada_mib'] = fila['privada_mib'] - anterior['privada_mib']
            fila['delta_hilos'] = fila['hilos'] - anterior['hilos']
            if 'objetos' in fila:
                fila['delta_objetos'] = fila['objetos'] - anterior.get('objetos', fila['objetos'])
            filas.append(fila)
            anterior = fila
    return filas


def escribir_por_fichero(filas: list[dict], destino: Path) -> None:
    columnas = ['pid', 'trabajador', 'fichero', 'privada_mib', 'delta_privada_mib', 'rss_mib', 'hilos', 'delta_hilos',
                'objetos', 'delta_objetos']
    with destino.open('w', newline='', encoding='utf-8') as f:
        escritor = csv.writer(f, delimiter='\t')
        escritor.writerow(columnas)
        for fila in sorted(filas, key=lambda x: -x['delta_privada_mib']):
            escritor.writerow([fila.get(c, '') for c in columnas])


def comparar(corridas: dict[int, dict]) -> tuple[list[str], float | None]:
    """Los problemas que impiden «iguales» y el ``GIB_POR_PROCESO`` propuesto."""
    hechas = [corridas[n] for n in sorted(corridas) if corridas[n].get('corrida')]
    problemas = [c['motivo'] for c in corridas.values() if not c.get('corrida')]
    if len(hechas) < 2:
        problemas.append(f'solo se corrió N={[c["n"] for c in hechas]}: no hay con qué comparar')
    referencia = hechas[0]['veredictos'] if hechas else {}
    for c in hechas:
        v = c['veredictos']
        fallidas = sorted(p for p, e in v.items() if e in ('failed', 'error'))
        omitidas = sorted(p for p, e in v.items() if e == 'skipped')
        if fallidas or omitidas:
            problemas.append(f"N={c['n']}: {len(fallidas)} fallidas y {len(omitidas)} omitidas "
                             f"(p. ej. {(fallidas + omitidas)[:5]})")
        if c['libre_min_gib'] < LIBRE_MINIMA_GIB:
            problemas.append(f"N={c['n']}: libre mínima {c['libre_min_gib']} GiB < {LIBRE_MINIMA_GIB}")
        if c.get('arbol_cambiado'):
            problemas.append(f"N={c['n']}: el árbol cambió durante la corrida")
        if c.get('disco_cambiado'):
            problemas.append(f"N={c['n']}: la suite dejó cambios en el disco del worktree: {c['disco_cambiado'][:10]}")
        if c is hechas[0]:
            continue
        faltan, sobran = sorted(set(referencia) - set(v)), sorted(set(v) - set(referencia))
        distintas = sorted(p for p in set(referencia) & set(v) if referencia[p] != v[p])
        if faltan or sobran or distintas:
            problemas.append(f"N={c['n']} frente a N={hechas[0]['n']}: {len(faltan)} faltan, {len(sobran)} de más y "
                             f"{len(distintas)} con otro veredicto (p. ej. "
                             f"{[f'{p}: {referencia[p]} → {v[p]}' for p in distintas[:5]] + (faltan + sobran)[:5]})")
    repartidas = [c for c in hechas if c['n'] >= 2] or hechas
    pico = max((max(c['pico_por_sesion_gib'].values(), default=0.0) for c in repartidas), default=0.0)
    propuesta = math.ceil(pico * MARGEN_POR_PROCESO * 4) / 4 if pico else None
    return problemas, propuesta


def informe(arbol: str, corridas: dict[int, dict], salida: Path) -> int:
    problemas, propuesta = comparar(corridas)
    resumen = {n: {k: v for k, v in c.items() if k != 'veredictos'} for n, c in sorted(corridas.items())}
    datos = {'arbol': arbol, 'ns': sorted(corridas), 'iguales': not problemas, 'problemas': problemas,
             'gib_por_proceso_propuesto': propuesta, 'resumen': resumen}
    (salida / 'comparacion.json').write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding='utf-8')
    lineas = [f'árbol {arbol}']
    for n, r in resumen.items():
        if not r.get('corrida'):
            lineas.append(f"N={n}: no corrida ({r['motivo']})")
            continue
        lineas.append(f"N={n}: {r['total']} pruebas, {r['fallidas']} F, {r['omitidas']} S, {r['segundos'] / 60:.1f} min "
                      f"(sesiones {r['segundos_por_sesion']}), pico del árbol {r['pico_arbol_gib']} GiB, por sesión "
                      f"{r['pico_por_sesion_gib']} GiB, libre mínima {r['libre_min_gib']} GiB")
    lineas.append(f'GIB_POR_PROCESO propuesto: {propuesta} (mayor memoria privada de un proceso de pytest × '
                  f'{MARGEN_POR_PROCESO}, a 0,25 GiB por arriba)')
    lineas += problemas + ['iguales' if not problemas else 'DISTINTAS']
    (salida / 'comparacion.txt').write_text('\n'.join(lineas) + '\n', encoding='utf-8')
    print('\n'.join(lineas), flush=True)
    return 0 if not problemas else 1


def correr_una(PC, n: int, raiz: Path, entorno: dict[str, str], salida: Path, argumentos: list[str], *,
               intervalo: float, por_fichero: bool, objetos: bool) -> dict:
    """Una corrida con N procesos; su resumen y el veredicto de cada prueba."""
    entorno = dict(entorno)
    carpeta_memoria = salida / f'n{n}_memoria_por_fichero'
    if por_fichero:
        complemento = salida / '_complemento'
        complemento.mkdir(exist_ok=True)
        (complemento / f'{NOMBRE_COMPLEMENTO}.py').write_text(COMPLEMENTO, encoding='utf-8')
        carpeta_memoria.mkdir(exist_ok=True)
        previo = entorno.get('PYTHONPATH', os.environ.get('PYTHONPATH', ''))
        entorno['PYTHONPATH'] = os.pathsep.join([p for p in (previo, str(complemento)) if p])
        entorno[VARIABLE_MEMORIA] = str(carpeta_memoria)
        entorno[VARIABLE_OBJETOS] = '1' if objetos else '0'
        argumentos = ['-p', NOMBRE_COMPLEMENTO, *argumentos]
    arbol = PC.arbol_del_indice(raiz)
    disco_antes = estado_del_arbol(raiz, salida)
    medidor = Medidor(salida / f'n{n}_memoria.csv', intervalo)
    medidor.start()
    inicio = time.monotonic()
    try:
        juicio = PC._pytest(argumentos, entorno, raiz, procesos=n, conservar=salida / f'n{n}')
    finally:
        medidor.fin.set()
        medidor.join()
    segundos = time.monotonic() - inicio
    junits = [salida / j['fichero'] for j in juicio.get('junits') or []]
    veredictos = veredictos_de(junits)
    disco_despues = estado_del_arbol(raiz, salida)
    if por_fichero:
        escribir_por_fichero(memoria_por_fichero(carpeta_memoria), salida / f'n{n}_por_fichero.tsv')
    corrida = {'n': n, 'corrida': True, 'segundos': round(segundos), 'total': len(veredictos),
               'fallidas': sum(e in ('failed', 'error') for e in veredictos.values()),
               'omitidas': sum(e == 'skipped' for e in veredictos.values()),
               'fallidas_de_la_puerta': juicio['fallidas'], 'segundos_por_sesion': segundos_por_sesion(junits),
               'pico_arbol_gib': round(medidor.pico_arbol / 2**30, 2),
               'pico_por_sesion_gib': {k: round(v / 2**30, 2) for k, v in sorted(medidor.pico_por_etiqueta.items())},
               'libre_min_gib': round(medidor.libre_min / 2**30, 2), 'procesos_max': medidor.procesos_max,
               'arbol_cambiado': PC.arbol_del_indice(raiz) != arbol,
               'disco_cambiado': cambios_del_disco(disco_antes, disco_despues),
               'junits': [j.name for j in junits], 'veredictos': veredictos}
    (salida / f'n{n}.json').write_text(json.dumps(corrida, indent=2, ensure_ascii=False), encoding='utf-8')
    return corrida


def _argumentos() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument('--salida', type=Path, required=True, help='carpeta de los resultados (se crea)')
    p.add_argument('--worktree', type=Path, default=RAIZ, help='el árbol que se prueba (por omisión, el de esta '
                   'herramienta)')
    p.add_argument('--n', type=int, nargs='+', default=[1, 2, 3], help='los procesos de cada corrida (1 2 3)')
    p.add_argument('--pruebas', default='', help='solo estas pruebas, separadas por espacios (ensayo corto)')
    p.add_argument('--intervalo', type=float, default=2.0, help='segundos entre medidas del árbol de procesos')
    p.add_argument('--candado', type=Path, help='carpeta que se crea al empezar y se retira al terminar')
    p.add_argument('--quien', default='comparar_suite_repartida', help='lo que se escribe en el candado')
    p.add_argument('--no-lanzar-si-existe', type=Path, action='append', default=[], metavar='RUTA')
    p.add_argument('--objetos', action='store_true', help='cuenta también los objetos de Python por fichero')
    p.add_argument('--sin-memoria-por-fichero', action='store_true', help='sin el complemento de pytest')
    p.add_argument('--solo-comparar', action='store_true', help='compara lo que ya está en la salida, sin correr')
    return p


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows escribe en cp1252: «≥» y «→» de la ayuda y del informe la tumbaban.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, 'reconfigure'):
            flujo.reconfigure(encoding='utf-8', errors='replace')
    a = _argumentos().parse_args(argv)
    salida = a.salida.resolve()
    if a.solo_comparar:
        corridas = {}
        for ruta in sorted(salida.glob('n*.json')):
            c = json.loads(ruta.read_text(encoding='utf-8'))
            corridas[c['n']] = c
        if not corridas:
            print(f'NO HAY CORRIDAS en {salida}')
            return 2
        arbol = json.loads((salida / 'comparacion.json').read_text(encoding='utf-8'))['arbol'] \
            if (salida / 'comparacion.json').is_file() else '?'
        return informe(arbol, corridas, salida)
    bloqueos = [r for r in a.no_lanzar_si_existe if r.exists()]
    if bloqueos:
        print(f'NO SE LANZA: existe {bloqueos[0]}')
        return 2
    raiz = a.worktree.resolve()
    if a.candado is not None:
        try:
            a.candado.mkdir()
        except FileExistsError:
            print(f'NO SE LANZA: el candado {a.candado} ya existe ({_leer(a.candado / "quien")})')
            return 2
        (a.candado / 'quien').write_text(a.quien + '\n', encoding='utf-8')
    try:
        return _comparar_n(a, raiz, salida)
    finally:
        if a.candado is not None:
            (a.candado / 'quien').unlink(missing_ok=True)
            a.candado.rmdir()


def _leer(ruta: Path) -> str:
    try:
        return ruta.read_text(encoding='utf-8').strip()
    except OSError:
        return '?'


def _comparar_n(a, raiz: Path, salida: Path) -> int:
    salida.mkdir(parents=True, exist_ok=True)
    os.chdir(raiz)
    PC = cargar_puerta(raiz)
    if not PC.indice_igual_al_disco(raiz):
        print('NO SE LANZA: el disco del worktree no es su índice.')
        return 2
    arbol = PC.arbol_del_indice(raiz)
    try:
        entorno = {**PC._variables_del_fichero(raiz), **PC.variables_de_la_suite(raiz)}
    except PC.PuertaError as exc:
        print(f'NO SE LANZA: {exc}')
        return 2
    argumentos = a.pruebas.split()
    print(f'árbol {arbol}; N = {a.n}; pruebas: {argumentos or "la suite entera"}; variables: {sorted(entorno)}',
          flush=True)
    corridas: dict[int, dict] = {}
    for n in a.n:
        bloqueos = [r for r in a.no_lanzar_si_existe if r.exists()]
        posibles, motivo = PC.procesos_de_la_suite({**os.environ, PC.VARIABLE_PROCESOS: str(n)})
        if bloqueos or posibles < n:
            razon = f'existe {bloqueos[0]}' if bloqueos else f'no hay memoria o CPU para N={n}: {motivo}'
            corridas[n] = {'n': n, 'corrida': False, 'motivo': razon}
            print(f'N={n} no se corre: {razon}', flush=True)
            continue
        print(f'N={n}: empieza a las {time.strftime("%H:%M:%S")} ({motivo})', flush=True)
        corridas[n] = correr_una(PC, n, raiz, entorno, salida, argumentos, intervalo=a.intervalo,
                                 por_fichero=not a.sin_memoria_por_fichero, objetos=a.objetos)
        c = corridas[n]
        print(f"N={n}: {c['total']} pruebas, {c['fallidas']} F, {c['omitidas']} S, {c['segundos'] / 60:.1f} min, "
              f"pico del árbol {c['pico_arbol_gib']} GiB, libre mínima {c['libre_min_gib']} GiB", flush=True)
    return informe(arbol, corridas, salida)


if __name__ == '__main__':
    sys.exit(main())
