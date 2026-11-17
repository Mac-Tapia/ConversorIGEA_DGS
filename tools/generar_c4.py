"""Pone al día las cifras del C4 de ``docs/architecture/`` desde el catálogo generado (spec 090, RF-19).

``workspace.dsl`` y su página interactiva se escriben a mano, salvo sus cifras: los ficheros de cada componente
(la suma de los grupos de ``subsistemas.json`` que nombra su propiedad «Subsistemas»), los módulos y los
subsistemas de la cabecera, las rutas de la API, las tareas del asistente, los carriles de trabajos y la marca
«en implementación» de cada elemento con su «Spec», según el Estado de esa spec. Todo sale de
``docs/ARQUITECTURA_CATALOGO.md``, así que esta orden va después de ``generar_arquitectura.py --escribir``.

Uso: python tools/generar_c4.py --escribir | --comprobar
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DSL = 'docs/architecture/workspace.dsl'
HTML = 'docs/architecture/arquitectura-interactiva-c4.html'
CATALOGO = 'docs/ARQUITECTURA_CATALOGO.md'
MAPA = 'docs/architecture/subsistemas.json'
EN_IMPL = 'en implementación'
ORDEN = 'python tools/generar_c4.py --escribir'


class SinCifra(ValueError):
    """El catálogo, el DSL o la página no traen algo que esta orden necesita."""


def _busca(patron: str, texto: str, que: str, flags: int = re.M) -> re.Match:
    m = re.search(patron, texto, flags)
    if not m:
        raise SinCifra(f'no encuentro {que}')
    return m


def cifras(raiz: Path) -> dict:
    """Lo que el C4 copia del catálogo generado y de las specs."""
    cat = (raiz / CATALOGO).read_text(encoding='utf-8')
    if '\n## Ficheros\n' not in cat:
        raise SinCifra(f'{CATALOGO} sin la sección «## Ficheros»')
    partes = re.split(r'^### (.+)$', cat.split('\n## Ficheros\n', 1)[1], flags=re.M)
    ficheros = {partes[i].strip(): len(re.findall(r'^\| `', partes[i + 1], flags=re.M)) for i in range(1, len(partes), 2)}
    rutas = _busca(r'^(\d+) en `web/app.py`, y (\d+) bajo', cat, 'las rutas de la API en el catálogo')
    carriles = re.findall(r'`([^`]+)`', _busca(r'^### Carriles de trabajos\n\n(.+)$', cat, 'los carriles en el catálogo').group(1))
    if not carriles:
        raise SinCifra('el catálogo no nombra ningún carril')
    estados = {}
    for spec in sorted((raiz / 'specs').glob('[0-9][0-9][0-9]-*/spec.md')):
        m = re.search(r'^Estado: *(\w+)', spec.read_text(encoding='utf-8'), flags=re.M)
        if m:
            estados[spec.parent.name[:3]] = m.group(1)
    return {
        'ficheros': ficheros,
        'grupos': [g['titulo'] for g in json.loads((raiz / MAPA).read_text(encoding='utf-8'))['grupos']],
        'modulos': _busca(r'^(\d+) módulos y \d+ excepciones', cat, 'los módulos en el catálogo').group(1),
        'rutas': rutas.group(1), 'rutas_vnr': rutas.group(2),
        'tareas': _busca(r'^### Tareas \((\d+)\)', cat, 'las tareas del asistente en el catálogo').group(1),
        'carriles': ', '.join(carriles[:-1]) + (' y ' if len(carriles) > 1 else '') + carriles[-1],
        'estados': estados,
    }


def _cambia(patron: str, nuevo, texto: str, que: str) -> str:
    texto2, n = re.subn(patron, nuevo, texto, count=1, flags=re.M)
    if not n:
        raise SinCifra(f'no encuentro {que}')
    return texto2


def _marca_por_estado(lineas: list[str], estados: dict) -> list[str]:
    """Añade o quita «en implementación» (etiqueta y propiedad «Estado») de cada elemento con «Spec»."""
    salida = list(lineas)
    for h, linea in enumerate(lineas):
        cab = re.match(r'^( *)\w+ = (?:softwareSystem|container|component) ".*\{\s*$', linea)
        if not cab:
            continue
        ind = len(cab.group(1))
        hijo, cierre = ' ' * (ind + 4), ' ' * ind + '}'
        tags = props = spec = None
        k = h + 1
        while k < len(lineas) and lineas[k].rstrip() != cierre:
            if lineas[k].startswith(hijo + 'tags "'):
                tags = k
            elif lineas[k].rstrip() == hijo + 'properties {':
                props = k
                j = k + 1
                while lineas[j].rstrip() != hijo + '}':
                    s = re.search(r'"Spec" "(\d{3})"', lineas[j])
                    spec = s.group(1) if s else spec
                    j += 1
            k += 1
        if spec is None or tags is None or spec not in estados:
            continue
        pendiente = estados[spec] != 'cumplida'
        actuales = re.search(r'tags "([^"]*)"', salida[tags]).group(1).split(',')
        nuevos = [t for t in actuales if t != EN_IMPL] + ([EN_IMPL] if pendiente else [])
        salida[tags] = re.sub(r'tags "[^"]*"', f'tags "{",".join(nuevos)}"', salida[tags])
        j = props + 1
        estado_en = None
        while salida[j].rstrip() != hijo + '}':
            if re.search(r'^\s*"Estado" ', salida[j]):
                estado_en = j
            j += 1
        if pendiente and estado_en is None:
            # Se añade a la misma línea de «properties {» para no mover los índices de las líneas de abajo.
            salida[props] = salida[props] + '\n' + ' ' * (ind + 8) + f'"Estado" "{EN_IMPL}"'
        elif not pendiente and estado_en is not None:
            salida[estado_en] = None
    return [x for x in salida if x is not None]


def dsl_al_dia(texto: str, c: dict) -> str:
    """El DSL con sus cifras al día; lo escrito a mano no se toca."""
    texto = _cambia(r'(\d+) módulos de Python en (\d+) subsistemas', f'{c["modulos"]} módulos de Python en {len(c["grupos"])} subsistemas',
                    texto, 'la cabecera «N módulos de Python en M subsistemas» del DSL')
    texto = _cambia(r'REST y WebSocket: \d+ rutas y \d+ del VNR-GIS', f'REST y WebSocket: {c["rutas"]} rutas y {c["rutas_vnr"]} del VNR-GIS',
                    texto, 'las rutas de la API en el DSL')
    texto = _cambia(r'^(\s*assistant = container "[^"]+" ")\d+ tareas;', rf'\g<1>{c["tareas"]} tareas;', texto,
                    'las tareas del asistente en el DSL')
    texto = _cambia(r'^(\s*jobs = container "[^"]+" ")Carriles [^;"]+;', rf'\g<1>Carriles {c["carriles"]};', texto,
                    'los carriles en el DSL')

    def ficheros(m: re.Match) -> str:
        sub = re.search(r'"Subsistemas" "([^"]+)"', texto[m.end():])
        if not sub:
            raise SinCifra(f'el componente «{m.group(2)}» no tiene «Subsistemas»')
        faltan = [g for g in sub.group(1).split(' | ') if g not in c['ficheros']]
        if faltan:
            raise SinCifra(f'«Subsistemas» de «{m.group(2)}» que no están en el catálogo: {faltan}')
        return f'{m.group(1)}({sum(c["ficheros"][g] for g in sub.group(1).split(" | "))} ficheros)'

    texto = re.sub(r'(component "([^"]+)" "[^"]*?)\(\d+ ficheros\)', ficheros, texto)
    return '\n'.join(_marca_por_estado(texto.split('\n'), c['estados']))


def _rango(specs: list[str]) -> str:
    if not specs:
        return 'ninguna'
    numeros = sorted(int(s) for s in specs)
    if numeros == list(range(numeros[0], numeros[-1] + 1)) and len(numeros) > 1:
        return f'{numeros[0]} a {numeros[-1]}'
    return ', '.join(str(n) for n in numeros)


def html_al_dia(texto: str, dsl: str, c: dict) -> str:
    """La página con las cifras del DSL y del catálogo."""
    marcadas = sorted({s for cuerpo in re.findall(r'tags "[^"]*en implementación[^"]*"(.*?)\n {8,12}\}', dsl, flags=re.S)
                       for s in re.findall(r'"Spec" "(\d{3})"', cuerpo)})
    texto = _cambia(r'en implementación \(specs [^)]*\)\. \d+ módulos de Python en \d+ subsistemas',
                    f'en implementación (specs {_rango(marcadas)}). {c["modulos"]} módulos de Python en {len(c["grupos"])} subsistemas',
                    texto, 'la leyenda de la página')
    texto = _cambia(r"tech: 'FastAPI, \d+ \+ \d+ rutas'", f"tech: 'FastAPI, {c['rutas']} + {c['rutas_vnr']} rutas'", texto,
                    'las rutas de la API en la página')
    texto = _cambia(r"^(\s*assistant: \{.*detail: ')\d+ tareas;", rf"\g<1>{c['tareas']} tareas;", texto,
                    'las tareas del asistente en la página')
    texto = _cambia(r"^(\s*jobs: \{.*detail: ')Carriles [^;']+;", rf"\g<1>Carriles {c['carriles']};", texto,
                    'los carriles en la página')
    componentes = {n: f for n, f in re.findall(r'component "([^"]+)" "[^"]*\((\d+) ficheros\)', dsl)}

    def nodo(m: re.Match) -> str:
        if m.group(2) not in componentes:
            raise SinCifra(f'el componente «{m.group(2)}» de la página no está en el DSL')
        return f"{m.group(1)}{componentes[m.group(2)]} ficheros'"

    texto = re.sub(r"^( +c[A-Z]\w*: \{ label: '([^']+)', tech: ')\d+ ficheros'", nodo, texto, flags=re.M)

    def plan(m: re.Match) -> str:
        spec = m.group(1)
        if c['estados'].get(spec) != 'cumplida':
            return m.group(0)
        return m.group(0).replace(f"tech: '{EN_IMPL} · {spec}'", f"tech: 'spec {spec} cumplida'").replace(', status: PLAN', '')

    return re.sub(rf"^ +\w+: \{{ label: '[^']+', tech: '{EN_IMPL} · (\d{{3}})'.*$", plan, texto, flags=re.M)


def generar(raiz: Path) -> dict[str, str]:
    c = cifras(raiz)
    dsl = dsl_al_dia((raiz / DSL).read_text(encoding='utf-8'), c)
    return {DSL: dsl, HTML: html_al_dia((raiz / HTML).read_text(encoding='utf-8'), dsl, c)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--escribir', action='store_true', help='reescribe las cifras del DSL y de la página')
    grupo.add_argument('--comprobar', action='store_true', help='sale con 1 si alguna cifra no está al día')
    p.add_argument('--raiz', type=Path, default=RAIZ, help='raíz del repositorio')
    args = p.parse_args(argv)
    try:
        nuevos = generar(args.raiz)
    except SinCifra as exc:
        print(f'generar_c4: {exc}')
        return 2
    distintos = [r for r, t in nuevos.items() if (args.raiz / r).read_text(encoding='utf-8') != t]
    if args.comprobar:
        if distintos:
            print(f'{", ".join(distintos)} no está al día con {CATALOGO}: {ORDEN}')
            return 1
        print('C4 al día')
        return 0
    for ruta in distintos:
        (args.raiz / ruta).write_text(nuevos[ruta], encoding='utf-8', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
