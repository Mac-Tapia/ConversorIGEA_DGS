"""La disposición de un diagrama unifilar por anchura desde la fuente: nivel y orden de cada barra (111:RF-23; 107:RF-15).

Una sola regla para los dos unifilares del programa, el del PIT (DXF del formato F-212) y el del plano de la red:

- El nivel de una barra es su distancia, en conexiones, a la fuente (la red externa del PIT, la cabecera del
  alimentador en el plano), por recorrido a lo ancho. Lo que no se alcanza va al nivel siguiente al último, juntas.
- El orden dentro del nivel es determinista: el de entrada de las barras («entrada», el del PIT, que no cambia sus
  hojas) o el del descubrimiento en el recorrido («descubrimiento», el del plano: los hijos quedan junto a su padre
  y se cruzan menos líneas).

Solo coloca: no cambia geometrías, impedancias ni estados, y una maniobra abierta no corta el recorrido (el unifilar
enseña la topología de la red; el estado lo pinta quien dibuja).
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

__all__ = ['ORDENES', 'niveles_por_anchura', 'unifilar_de_vista']

ORDENES = ('entrada', 'descubrimiento')


def niveles_por_anchura(vecinos: Mapping[str, Sequence[str]], raices: Iterable[str], *,
                        orden: Literal['entrada', 'descubrimiento'] = 'entrada') -> dict[str, tuple[int, int]]:
    """Barra → (nivel, orden dentro del nivel). ``vecinos`` guarda, por barra y en orden, sus barras conectadas."""
    if orden not in ORDENES:
        raise ValueError(f'orden «{orden}» desconocido: {ORDENES}')
    nivel: dict[str, int] = {}
    descubiertas: list[str] = []
    cola: deque[str] = deque()
    for r in raices:
        if r in vecinos and r not in nivel:
            nivel[r] = 0
            descubiertas.append(r)
            cola.append(r)
    while cola:
        x = cola.popleft()
        for y in vecinos[x]:
            if y not in nivel:
                nivel[y] = nivel[x] + 1
                descubiertas.append(y)
                cola.append(y)
    ultimo = max(nivel.values(), default=-1) + 1
    for b in vecinos:
        nivel.setdefault(b, ultimo)
    secuencia = list(vecinos) if orden == 'entrada' else descubiertas + [b for b in vecinos if b not in set(descubiertas)]
    contador: dict[int, int] = {}
    pos: dict[str, tuple[int, int]] = {}
    for b in secuencia:
        n = nivel[b]
        pos[b] = (n, contador.get(n, 0))
        contador[n] = contador.get(n, 0) + 1
    return pos


def unifilar_de_vista(vista: Mapping[str, Any]) -> dict[str, Any]:
    """El unifilar de una vista del plano (111:RF-23): cada barra con su nivel y su orden, desde la fuente.

    Los tramos, las SED y las maniobras los pinta el navegador con sus códigos de la vista: aquí solo se colocan las
    barras, y con los mismos códigos (111:RF-2), sin tocar vértices ni datos eléctricos.
    """
    barras = [b['codigo'] for b in vista.get('barras', ())]
    vecinos: dict[str, list[str]] = {b: [] for b in barras}
    for t in vista.get('tramos', ()):
        a, z = t['desde'], t['hasta']
        vecinos.setdefault(a, []).append(z)
        vecinos.setdefault(z, []).append(a)
    fuente = vista.get('fuente')
    raices = [fuente] if fuente in vecinos else list(vecinos)[:1]
    pos = niveles_por_anchura(vecinos, raices, orden='descubrimiento')
    por_nivel: dict[int, int] = {}
    for n, _o in pos.values():
        por_nivel[n] = por_nivel.get(n, 0) + 1
    alcanzadas = _alcanzables(vecinos, raices)
    return {'fuente': raices[0] if raices else None,
            'barras': [{'codigo': b, 'nivel': n, 'orden': o} for b, (n, o) in pos.items()],
            'niveles': (max(por_nivel) + 1) if por_nivel else 0,
            'ancho': max(por_nivel.values(), default=0),
            'sin_alcanzar': sorted(b for b in vecinos if b not in alcanzadas)}


def _alcanzables(vecinos: Mapping[str, Sequence[str]], raices: Sequence[str]) -> set[str]:
    vistas: set[str] = set()
    cola = deque(r for r in raices if r in vecinos)
    vistas.update(cola)
    while cola:
        x = cola.popleft()
        for y in vecinos[x]:
            if y not in vistas:
                vistas.add(y)
                cola.append(y)
    return vistas
