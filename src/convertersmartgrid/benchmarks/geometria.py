"""Geometría del benchmark: trazado sintético, longitudes perturbadas y el control del atacante (112:RF-3, RF-13, RF-14).

Un giro y una traslación conservan la forma de la red, y la forma se cuadra contra la geometría pública. Por eso el
benchmark no lleva coordenadas reales giradas: lleva un trazado sintético por el grafo, en el que cada tramo es un
segmento recto de su longitud eléctrica (el modelo calcula la longitud por la polilínea y la cuadra con la del TXT), y
unas longitudes perturbadas, ε ~ U(−a, a) con la semilla secreta, recortadas hasta que el estudio se reproduce.

Control (aclaración de RF-13 y RF-14): un atacante que conoce el margen ordena las longitudes de un alimentador y las
empareja, rango a rango, con las de otro; con el 50 % o más de los tramos dentro del margen, el alimentador está
«identificado». Con ±5 % una red real perturbada SÍ queda identificada: lo que deriva de una red real es de uso local.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence

import numpy as np

from ..model import CODIGOS_PUENTE, LARGO_MAXIMO_PUENTE_M
from .seudonimos import ORIGENES_NEUTROS, origen_lejano

AMPLITUD_POR_DEFECTO = 0.05
INTENTOS_RECORTE = 4
UMBRAL_IDENTIFICADO = 0.5
#: Los tramos de menos de 1 m, y los de código de puente que con la perturbación podrían cruzar su umbral
#: (``model.LARGO_MAXIMO_PUENTE_M``), no se perturban: cruzarlo cambiaría el modelo, no solo sus números.
LARGO_MINIMO_PERTURBADO_M = 1.0
#: Separación entre las cabeceras de los alimentadores del trazado, y abanico de los hijos de un nudo.
SEPARACION_M = 20_000.0
ABANICO_RAD = math.radians(25.0)


def fraccion_emparejada(original: Sequence[float], benchmark: Sequence[float], margen: float) -> float:
    """La parte de los tramos del original que el atacante empareja, rango a rango, dentro de ±margen."""
    a = np.sort(np.asarray(original, dtype=float))
    b = np.sort(np.asarray(benchmark, dtype=float))
    if not len(a) or not len(b):
        return 0.0
    if len(b) != len(a):
        b = np.quantile(b, (np.arange(len(a)) + 0.5) / len(a))
    escala = np.maximum(np.abs(a), 1e-9)
    return float(np.mean(np.abs(b - a) / escala <= margen + 1e-12))


def identificados(original: dict[str, Sequence[float]], benchmark: dict[str, Sequence[float]], margen: float, *,
                  pares: dict[str, str] | None = None) -> list[str]:
    """Los alimentadores del original que el atacante identifica en el benchmark.

    Con ``pares`` (original → seudónimo, uso local) se compara cada uno con el suyo; sin ellos (publicable), con todos
    los del benchmark: el atacante no sabe cuál es cuál.
    """
    salida = []
    for red, largos in original.items():
        candidatos = [benchmark[pares[red]]] if pares is not None and pares.get(red) in benchmark else (
            list(benchmark.values()) if pares is None else [])
        if any(fraccion_emparejada(largos, c, margen) >= UMBRAL_IDENTIFICADO for c in candidatos):
            salida.append(red)
    return salida


def perturbar(largos: dict[str, tuple[float, str]], *, semilla: int, amplitud: float) -> dict[str, str]:
    """Longitudes × (1 + ε), ε ~ U(−a, a) con la semilla SECRETA (con la pública, se desharía la perturbación)."""
    salida = {}
    for tramo, (largo, tipo) in largos.items():
        # Un tramo de código de puente solo se perturba si ni con −a cruza el umbral de los puentes: fundirlo o no
        # cambiaría el modelo, no solo sus números.
        if largo < LARGO_MINIMO_PERTURBADO_M or (
                tipo.upper() in CODIGOS_PUENTE and largo * (1 - amplitud) <= LARGO_MAXIMO_PUENTE_M):
            continue
        eps = random.Random(f'{int(semilla)}:largo:{tramo}').uniform(-amplitud, amplitud)
        salida[tramo] = f'{largo * (1 + eps):.3f}'
    return salida


def trazar(alimentadores: Iterable[tuple[str, str, list[tuple[str, str, str]]]], largos: dict[str, float],
           recuadro_original: tuple[float, float, float, float] | None
           ) -> tuple[dict[str, tuple[float, float]], dict[str, list[tuple[float, float]]]]:
    """Coordenadas de un trazado sintético por el grafo: cada tramo, un segmento de su longitud.

    ``alimentadores``: (red, nudo de cabecera, [(tramo, nudo desde, nudo hasta)]). Un recorrido en anchura desde la
    cabecera reparte los hijos de cada nudo en abanico. Un tramo que cierra un lazo (sus dos nudos ya colocados) lleva
    un punto intermedio que le da su longitud. Devuelve las coordenadas por nudo y los intermedios por tramo.
    """
    coords: dict[str, tuple[float, float]] = {}
    angulo: dict[str, float] = {}
    intermedios: dict[str, list[tuple[float, float]]] = {}
    for k, (_red, cabecera, tramos) in enumerate(alimentadores):
        vecinos: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for tramo, a, b in tramos:
            vecinos[a].append((tramo, b))
            vecinos[b].append((tramo, a))
        if cabecera not in coords:
            coords[cabecera] = (k * SEPARACION_M, 0.0)
            angulo[cabecera] = 0.0
        hechos: set[str] = set()
        cola = deque([cabecera])
        while cola:
            nudo = cola.popleft()
            hijos = [(t, otro) for t, otro in vecinos[nudo] if t not in hechos]
            nuevos = [(t, o) for t, o in hijos if o not in coords]
            for j, (t, otro) in enumerate(nuevos):
                theta = angulo[nudo] + ABANICO_RAD * (j - (len(nuevos) - 1) / 2)
                largo = largos.get(t, 0.0)
                x, y = coords[nudo]
                coords[otro] = (x + largo * math.cos(theta), y + largo * math.sin(theta))
                angulo[otro] = theta
                cola.append(otro)
            for t, otro in hijos:
                hechos.add(t)
                if (t, otro) in nuevos:
                    continue
                # Lazo: los dos nudos ya tienen sitio; un vértice a un lado da a la polilínea su longitud.
                (x0, y0), (x1, y1) = coords[nudo], coords[otro]
                d = math.dist((x0, y0), (x1, y1))
                largo = largos.get(t, d)
                if largo > d + 1e-6:
                    h = math.sqrt(max(largo * largo / 4 - d * d / 4, 0.0))
                    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                    nx, ny = ((y0 - y1) / d, (x1 - x0) / d) if d > 0 else (0.0, 1.0)
                    intermedios[t] = [(mx + h * nx, my + h * ny)]
        for _t, a, b in tramos:          # nudos sueltos del alimentador, junto a su cabecera
            for n in (a, b):
                coords.setdefault(n, coords[cabecera])
    origen = _origen_neutro(coords, recuadro_original)
    mover = lambda p: (p[0] + origen[0], p[1] + origen[1])     # noqa: E731
    return ({n: mover(p) for n, p in coords.items()},
            {t: [mover(p) for p in ps] for t, ps in intermedios.items()})


def _origen_neutro(coords: dict[str, tuple[float, float]],
                   recuadro: tuple[float, float, float, float] | None) -> tuple[float, float]:
    if not coords:
        return ORIGENES_NEUTROS[0]
    xs = [p[0] for p in coords.values()]
    ys = [p[1] for p in coords.values()]
    return origen_lejano(recuadro, (min(xs), min(ys), max(xs), max(ys)))


def largos_por_alimentador(ficheros) -> dict[str, list[float]]:
    """Las longitudes de los tramos de cada alimentador del trío leído (``redes.leer_fichero``): la huella que mira el
    atacante (aclaración de RF-13 y RF-14)."""
    red = next(f for f in ficheros if f.nombre == 'RED.txt')
    duenio: dict[str, str] = {}
    actual = None
    largos: dict[str, float] = {}
    for e in red.entradas:
        if e[0] == 'feeder':
            actual = dict(zip(e[1], e[2])).get('NetworkID')
        elif e[0] == 'fila' and e[1] == 'SECTION' and actual:
            duenio[e[2].get('SectionID', '')] = actual
        elif e[0] == 'fila' and e[1] in ('LINE CONFIGURATION', 'OVERHEADLINE SETTING', 'UNDERGROUNDLINE SETTING'):
            try:
                largos.setdefault(e[2].get('SectionID', ''), float(e[2].get('Length') or 'nan'))
            except ValueError:
                continue
    salida: dict[str, list[float]] = {}
    for tramo, red_id in duenio.items():
        if tramo in largos and np.isfinite(largos[tramo]):
            salida.setdefault(red_id, []).append(largos[tramo])
    return salida


# --------------------------------------------------------------------------- T14: cuadre contra la geometría pública
#: Residuo medio, en metros, por debajo del cual un alimentador del benchmark cuadra con uno de la geometría pública.
RESIDUO_ICP_M = 25.0
GIROS_INICIALES = 12
ITERACIONES_ICP = 15


def _kabsch(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Giro y traslación que mejor llevan los puntos ``a`` sobre ``b`` (mínimos cuadrados, sin escala ni reflexión)."""
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    u, _s, vt = np.linalg.svd((a - ca).T @ (b - cb))
    if np.linalg.det(u @ vt) < 0:
        vt[-1] *= -1
    r = (u @ vt).T
    return r, cb - ca @ r.T


def residuo_icp(benchmark: np.ndarray, publica: np.ndarray) -> float:
    """El menor residuo medio (m) de un ICP rígido de ``benchmark`` sobre ``publica``, desde varios giros iniciales.

    El vecino más cercano va por un árbol k-d (``scipy.spatial.cKDTree``): con miles de vértices, la matriz de
    distancias entera no cabría en memoria.
    """
    from scipy.spatial import cKDTree

    a, b = np.asarray(benchmark, float), np.asarray(publica, float)
    if len(a) < 3 or len(b) < 3:
        return float('inf')
    arbol = cKDTree(b)
    mejor = float('inf')
    for k in range(GIROS_INICIALES):
        t = 2 * math.pi * k / GIROS_INICIALES
        r0 = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
        x = (a - a.mean(axis=0)) @ r0.T + b.mean(axis=0)
        for _ in range(ITERACIONES_ICP):
            _d, i = arbol.query(x)
            r, tr = _kabsch(x, b[i])
            x = x @ r.T + tr
        d, _i = arbol.query(x)
        mejor = min(mejor, float(d.mean()))
    return mejor


def cuadre_publico(benchmark: dict[str, np.ndarray], publica: dict[str, np.ndarray]) -> list[str]:
    """Alimentadores del benchmark que cuadran (ICP) con alguno de la geometría pública: se identificarían (RF-14).

    Solo se comparan los de tamaño parecido (±50 % de vértices): el atacante también sabe contar.
    """
    salida = []
    for nombre, puntos in sorted(benchmark.items()):
        for otro in publica.values():
            if 0.5 * len(otro) <= len(puntos) <= 1.5 * len(otro) and residuo_icp(puntos, otro) <= RESIDUO_ICP_M:
                salida.append(nombre)
                break
    return salida
