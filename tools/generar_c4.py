"""Pone al día las cifras del C4 de ``docs/architecture/`` desde el catálogo generado (spec 090, RF-19).

``workspace.dsl`` y su página interactiva se escriben a mano, salvo sus cifras: los ficheros de cada componente
(la suma de los grupos de ``subsistemas.json`` que nombra su propiedad «Subsistemas»), los módulos y los
subsistemas de la cabecera, las rutas de la API, las tareas del asistente, los carriles de trabajos y la marca
«en implementación» de cada elemento con su «Spec», según el Estado de esa spec. Todo sale de
``docs/ARQUITECTURA_CATALOGO.md``, así que esta orden va después de ``generar_arquitectura.py --escribir``.

Además (090:RF-20, RF-22, RF-24) exige en el DSL una propiedad «Carril <nombre>» por cada carril y una «Motor <nombre>»
por cada motor abierto del catálogo, y en la página un nodo ``lane_<nombre>`` y ``motor_<nombre>``: sin ellos sale con 2
y los nombra, porque su texto se escribe a mano. Y copia a la página, entre sus marcas, el pseudocódigo de
``docs/architecture/pseudocodigo.md``.

Uso: python tools/generar_c4.py --escribir | --comprobar
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DSL = 'docs/architecture/workspace.dsl'
HTML = 'docs/architecture/arquitectura-interactiva-c4.html'
CATALOGO = 'docs/ARQUITECTURA_CATALOGO.md'
MAPA = 'docs/architecture/subsistemas.json'
PSEUDO = 'docs/architecture/pseudocodigo.md'
PSEUDO_INICIO, PSEUDO_FIN = '<!-- pseudocodigo:inicio -->', '<!-- pseudocodigo:fin -->'
#: Motores del C4 que no están en ``MOTORES``: pandapower calcula el preflight, el VAD y el PIT por su cuenta.
MOTORES_APARTE = ('pandapower',)
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
    linea_motores = _busca(r'^### Motores abiertos de flujo\n\n(.+)$', cat, 'los motores abiertos en el catálogo').group(1)
    motores = re.findall(r'`([^`/]+)`', linea_motores.split(' en `', 1)[0])
    if not motores:
        raise SinCifra('el catálogo no nombra ningún motor abierto')
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
        'lista_carriles': carriles, 'motores': motores,
        'pseudocodigo': pseudocodigo((raiz / PSEUDO).read_text(encoding='utf-8')),
        'estados': estados,
    }


def pseudocodigo(texto: str) -> list[tuple[str, str, str]]:
    """Los bloques ``## <id> — <título>`` de ``pseudocodigo.md`` con su código entre vallas (090:RF-23)."""
    bloques = re.findall(r'^## ([a-z0-9-]+) — ([^\n]+)\n\n```text\n(.*?)\n```$', texto, flags=re.M | re.S)
    if not bloques:
        raise SinCifra(f'{PSEUDO} sin bloques «## <id> — <título>» con su código')
    return bloques


def _exige_nombres(prefijo: str, esperados: list[str], hallados: list[str], donde: str, extra: tuple[str, ...] = ()) -> None:
    """090:RF-20, RF-22: cada nombre del código está en el C4, y el C4 no trae uno que el código ya no tiene."""
    faltan = [n for n in esperados if n not in hallados]
    sobran = [n for n in hallados if n not in esperados and n not in extra]
    if faltan or sobran:
        raise SinCifra(f'{donde}: {prefijo} que faltan {faltan} y que sobran {sobran}; '
                       f'añádalos o quítelos a mano, y luego {ORDEN}')


def comprobar_nombres(dsl: str, pagina: str, c: dict) -> None:
    _exige_nombres('carriles', c['lista_carriles'], re.findall(r'^\s*"Carril ([^"]+)" ', dsl, flags=re.M), DSL)
    _exige_nombres('motores', c['motores'], re.findall(r'^\s*"Motor ([^"]+)" ', dsl, flags=re.M), DSL, MOTORES_APARTE)
    _exige_nombres('carriles', c['lista_carriles'], re.findall(r"^\s*lane_(\w+): \{ label:", pagina, flags=re.M), HTML)
    _exige_nombres('motores', c['motores'], re.findall(r"^\s*motor_(\w+): \{ label:", pagina, flags=re.M), HTML, MOTORES_APARTE)


_CITA = re.compile(r'((?:src|tools)/[\w/]+\.py)::([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)')


def citas(texto: str) -> list[tuple[str, str]]:
    """Las citas ``ruta.py::función`` (o ``ruta.py::Clase.método``) del pseudocódigo, sin repetir."""
    return sorted(set(_CITA.findall(texto)))


def citas_sin_codigo(texto: str, raiz: Path) -> list[str]:
    """090:RF-23: las citas cuyo fichero no existe o no define esa función, clase o método en su nivel superior."""
    faltan = []
    for ruta, nombre in citas(texto):
        fichero = raiz / ruta
        if not fichero.is_file():
            faltan.append(f'{ruta}::{nombre}')
            continue
        cuerpo = ast.parse(fichero.read_text(encoding='utf-8')).body
        for parte in nombre.split('.'):
            nodo = next((d for d in cuerpo if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                         and d.name == parte), None)
            if nodo is None:
                faltan.append(f'{ruta}::{nombre}')
                break
            cuerpo = nodo.body
    return faltan


def vistas_sin_pestana(pagina: str) -> list[str]:
    """Pestañas de la página (``data-view``) sin su vista en ``views``: la exportación (RF-26) no podría dibujarlas."""
    vistas = set(re.findall(r'^ {8}(\w+): \{\n {10}(?:pseudo|title):', pagina, flags=re.M))
    return [v for v in dict.fromkeys(re.findall(r'data-view="([^"]+)"', pagina)) if v not in vistas]


def _pseudocodigo_html(bloques: list[tuple[str, str, str]]) -> str:
    partes = [PSEUDO_INICIO, '  <section class="c4-pseudo" aria-label="Pseudocódigo de cada flujo">',
              f'    <h3 class="c4-pseudo-title">Pseudocódigo de cada flujo <small>(copiado de {PSEUDO})</small></h3>']
    for ident, titulo, codigo in bloques:
        partes += [f'    <details id="pseudo-{ident}" class="c4-pseudo-block">',
                   f'      <summary>{html.escape(titulo)}</summary>',
                   f'      <pre><code>{html.escape(codigo)}</code></pre>',
                   '    </details>']
    return '\n'.join(partes + ['  </section>', PSEUDO_FIN])


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
    if texto.count(PSEUDO_INICIO) != 1 or texto.count(PSEUDO_FIN) != 1:
        raise SinCifra(f'la página sin una sola pareja de marcas {PSEUDO_INICIO} … {PSEUDO_FIN}')
    antes, resto = texto.split(PSEUDO_INICIO, 1)
    texto = antes + _pseudocodigo_html(c['pseudocodigo']) + resto.split(PSEUDO_FIN, 1)[1]

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
    pagina = html_al_dia((raiz / HTML).read_text(encoding='utf-8'), dsl, c)
    comprobar_nombres(dsl, pagina, c)
    faltan = citas_sin_codigo((raiz / PSEUDO).read_text(encoding='utf-8'), raiz)
    if faltan:
        raise SinCifra(f'{PSEUDO} cita funciones que no existen: {faltan}; corrija la cita y luego {ORDEN}')
    sin_vista = vistas_sin_pestana(pagina)
    if sin_vista:
        raise SinCifra(f'{HTML}: pestañas sin su vista en «views»: {sin_vista}')
    return {DSL: dsl, HTML: pagina}


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
