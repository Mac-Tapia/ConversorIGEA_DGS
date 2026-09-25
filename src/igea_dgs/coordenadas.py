"""Coordenadas que faltan: se completan con el grafo de la red.

Un nodo sin ``CoordX/CoordY`` no se puede dibujar ni georreferenciar, y con la
geografía activa el modelo lo rechaza. Pero su posición no es desconocida del todo:
el grafo dice entre qué nodos está y los tramos dicen a qué distancia. Este módulo
usa eso, y nada más.

* **Nodos entre nodos conocidos** (una derivación sin coordenadas, una cadena de
  apoyos): cada uno queda en el promedio de sus vecinos ponderado por 1/longitud del
  tramo. En una cadena entre dos anclas eso los reparte en proporción exacta a la
  longitud acumulada, como caería una tensión a lo largo de resistencias en serie.
* **Ramas terminales con un solo ancla**: se prolongan desde el ancla con la
  longitud de cada tramo del TXT, en la dirección en que la red llega al ancla. Si
  la rama se abre, sus hijos se reparten en abanico.
* **Componentes sin ningún ancla**: no se inventa su posición. Quedan sin coordenada
  y se informan; con geografía activa el alimentador fallará con ese mensaje.

Cada coordenada inferida lleva ``CoordOrigen='grafo'`` en el nodo del dataset. El
modelo no la usa para recalcular longitudes eléctricas (un tramo con un extremo
inferido conserva la longitud del TXT): la posición es para dibujar, no para medir.

Coste lineal en nodos más tramos: se hace una vez por dataset, no por alimentador.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

ORIGEN_GRAFO = 'grafo'


@dataclass
class InformeCoordenadas:
    nodos_sin_coordenada: int = 0
    interpolados: int = 0
    prolongados: int = 0
    sin_ancla: list[str] = field(default_factory=list)

    @property
    def completados(self) -> int:
        return self.interpolados + self.prolongados

    def texto(self) -> str:
        if not self.nodos_sin_coordenada:
            return 'Coordenadas: todos los nodos traen CoordX/CoordY en la entrada.'
        base = (f'Coordenadas completadas por el grafo: {self.completados} de '
                f'{self.nodos_sin_coordenada} nodos sin CoordX/CoordY '
                f'({self.interpolados} interpolados entre nodos conocidos, '
                f'{self.prolongados} en ramas terminales).')
        if self.sin_ancla:
            base += (f' {len(self.sin_ancla)} sin ningún nodo con coordenadas en su '
                     f'componente: quedan sin posición ({", ".join(self.sin_ancla[:5])}…).')
        return base


def _num(v) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def tiene_coordenada(fila: dict) -> bool:
    return _num(fila.get('CoordX')) is not None and _num(fila.get('CoordY')) is not None


def completar_coordenadas(dataset, *, iteraciones: int = 2000, tolerancia_m: float = 0.01,
                          ) -> InformeCoordenadas:
    """Completa en el sitio las coordenadas de ``dataset.nodes`` que falten."""
    longitud = {}
    for sid, cfg in dataset.line_configurations.items():
        m = _num(cfg.get('Length'))
        longitud[sid] = m if m and m > 0 else None

    vecinos: dict[str, list[tuple[str, float]]] = defaultdict(list)
    # Tramo que une cada par de nodos, para seguir su trazado dibujado (INTERMEDIATE
    # NODES) al prolongar una rama terminal.
    tramo_de: dict[tuple[str, str], str] = {}
    for sid, sec in dataset.sections.items():
        a, b = sec.get('FromNodeID', ''), sec.get('ToNodeID', '')
        if not a or not b or a == b:
            continue
        # Un tramo sin longitud útil cuenta como 1 m: basta para ordenar, no para medir.
        m = longitud.get(sid) or 1.0
        vecinos[a].append((b, m))
        vecinos[b].append((a, m))
        tramo_de[(a, b)] = sid
        tramo_de[(b, a)] = sid

    usados = set(vecinos)
    conocidos: dict[str, tuple[float, float]] = {}
    faltan: set[str] = set()
    for n in usados:
        fila = dataset.nodes.get(n)
        if fila is None:
            # Un tramo que apunta a un nodo que NO existe en [NODE] es un error de datos
            # y debe hacer fallar a su alimentador; no se inventa el nodo. Tampoco se
            # usa como paso intermedio para colocar a otros.
            continue
        if tiene_coordenada(fila):
            conocidos[n] = (_num(fila['CoordX']), _num(fila['CoordY']))
        else:
            faltan.add(n)
    vecinos = defaultdict(list, {
        n: [(v, m) for v, m in vs if v in dataset.nodes] for n, vs in vecinos.items()
        if n in dataset.nodes})
    informe = InformeCoordenadas(nodos_sin_coordenada=len(faltan))
    if not faltan:
        return informe

    # Componentes de nodos desconocidos y sus anclas (vecinos conocidos).
    visto: set[str] = set()
    for inicio in sorted(faltan):
        if inicio in visto:
            continue
        comp, anclas = [], set()
        cola = deque([inicio])
        visto.add(inicio)
        while cola:
            n = cola.popleft()
            comp.append(n)
            for v, _ in vecinos[n]:
                if v in conocidos:
                    anclas.add(v)
                elif v not in visto:
                    visto.add(v)
                    cola.append(v)
        if not anclas:
            informe.sin_ancla.extend(sorted(comp))
            continue
        if len(anclas) >= 2:
            _interpolar(comp, vecinos, conocidos, iteraciones, tolerancia_m)
            informe.interpolados += len(comp)
        else:
            _prolongar(comp, next(iter(anclas)), vecinos, conocidos,
                       trazado=_trazados(dataset, tramo_de))
            informe.prolongados += len(comp)

    for n in faltan:
        if n in conocidos:
            fila = dataset.nodes[n]
            x, y = conocidos[n]
            fila['CoordX'] = repr(x)
            fila['CoordY'] = repr(y)
            fila['CoordOrigen'] = ORIGEN_GRAFO
    return informe


def _interpolar(comp, vecinos, conocidos, iteraciones, tolerancia_m) -> None:
    """Promedio ponderado por 1/longitud (Gauss-Seidel sobre el laplaciano del grafo)."""
    anclas = [v for n in comp for v, _ in vecinos[n] if v in conocidos]
    cx = sum(conocidos[a][0] for a in anclas) / len(anclas)
    cy = sum(conocidos[a][1] for a in anclas) / len(anclas)
    pos = {n: (cx, cy) for n in comp}
    miembros = set(comp)
    for _ in range(iteraciones):
        cambio = 0.0
        for n in comp:
            sx = sy = sw = 0.0
            for v, m in vecinos[n]:
                p = conocidos.get(v) if v not in miembros else pos[v]
                w = 1.0 / m
                sx += w * p[0]
                sy += w * p[1]
                sw += w
            nuevo = (sx / sw, sy / sw)
            cambio = max(cambio, abs(nuevo[0] - pos[n][0]) + abs(nuevo[1] - pos[n][1]))
            pos[n] = nuevo
        if cambio < tolerancia_m:
            break
    conocidos.update(pos)


def _trazados(dataset, tramo_de):
    """``(desde, hasta) → vértices del trazado`` en ese sentido, si el tramo los trae."""
    por_tramo = getattr(dataset, 'intermediate_by_section', {}) or {}
    secciones = dataset.sections

    def trazado(desde: str, hasta: str) -> list[tuple[float, float]]:
        sid = tramo_de.get((desde, hasta))
        filas = por_tramo.get(sid, ()) if sid else ()
        puntos = []
        for f in sorted(filas, key=lambda r: _num(r.get('SeqNumber')) or 0.0):
            x, y = _num(f.get('CoordX')), _num(f.get('CoordY'))
            if x is not None and y is not None:
                puntos.append((x, y))
        if puntos and secciones[sid].get('FromNodeID') != desde:
            puntos.reverse()
        return puntos

    return trazado


def _prolongar(comp, ancla, vecinos, conocidos, trazado=None) -> None:
    """Rama terminal: se desarrolla desde el ancla con las longitudes del TXT.

    Si el tramo trae vértices intermedios, el nodo se coloca siguiendo su trazado: al
    final de la polilínea, prolongada lo que falte hasta la longitud del TXT en la
    dirección de su último segmento. Sin vértices, en línea recta en la dirección con
    la que la red llega al nodo padre.
    """
    ax, ay = conocidos[ancla]
    # Dirección con la que la red conocida llega al ancla; la rama la continúa.
    dx = dy = 0.0
    for v, _ in vecinos[ancla]:
        if v in conocidos and v != ancla:
            vx, vy = conocidos[v]
            norma = math.hypot(ax - vx, ay - vy) or 1.0
            dx += (ax - vx) / norma
            dy += (ay - vy) / norma
    angulo_base = math.atan2(dy, dx) if (dx or dy) else 0.0
    miembros = set(comp)
    angulo = {ancla: angulo_base}
    cola = deque([ancla])
    while cola:
        n = cola.popleft()
        hijos = [(v, m) for v, m in vecinos[n] if v in miembros and v not in conocidos]
        if not hijos:
            continue
        # Abanico de ±30° alrededor de la dirección del padre.
        abertura = math.radians(60.0)
        for i, (v, m) in enumerate(sorted(hijos)):
            px, py = conocidos[n]
            vertices = trazado(n, v) if trazado else []
            if vertices:
                camino = [(px, py)] + vertices
                recorrido = sum(math.dist(p, q) for p, q in zip(camino, camino[1:]))
                (x0, y0), (x1, y1) = camino[-2], camino[-1]
                a = math.atan2(y1 - y0, x1 - x0) if (x1, y1) != (x0, y0) else angulo[n]
                resto = max(m - recorrido, 0.0)
                conocidos[v] = (x1 + resto * math.cos(a), y1 + resto * math.sin(a))
            else:
                desvio = 0.0 if len(hijos) == 1 else -abertura / 2 + abertura * i / (len(hijos) - 1)
                a = angulo[n] + desvio
                conocidos[v] = (px + m * math.cos(a), py + m * math.sin(a))
            angulo[v] = a
            cola.append(v)
