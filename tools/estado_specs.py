"""Estado de las specs: lee cada `specs/NNN-*/` con sus tareas y las citas de las pruebas.

Es el único lector de specs del repositorio (spec 033): la suite lo usa para comprobar la
numeración, las tareas y el estado, y escribe con él `specs/README.md`, la tabla de estado
que antes se mantenía a mano en `CLAUDE.md` y se desfasaba (revisión del 2026-10-29).

Uso:
    python tools/estado_specs.py                 # imprime la tabla
    python tools/estado_specs.py --escribir      # reescribe specs/README.md
    python tools/estado_specs.py --comprobar     # sale con 1 si specs/README.md no está al día
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESTADOS = ('borrador', 'aprobada', 'implementada', 'cumplida', 'reservada', 'retirada')
#: Una tarea de DIgSILENT (033:RF-7); la frase antigua sigue valiendo para las de la 009.
DIGSILENT = re.compile(r'\[DIgSILENT\]|a cargo del usuario|la hace el usuario', re.I)
_DEF = re.compile(r'^- RF-(\d+[a-z]?):(?! no se usan?\b)', re.M)
_HUECO = re.compile(r'^- RF-(\d+)(?: a RF-(\d+))?: no se usan?\b', re.M)
_TAREA = re.compile(r'^- \[( |x)\] (T\S*?)\.? (.*)$', re.M)


def clave_rf(rf: str) -> tuple[int, str]:
    m = re.match(r'(\d+)([a-z]?)$', rf)
    return (int(m.group(1)), m.group(2)) if m else (0, rf)


def rf_de_texto(texto: str) -> set[str]:
    """RF nombrados en un texto: sueltos, en rango «RF-a a RF-b» y en «RF-2/6/7».

    Las citas a otra spec («014:RF-5») no cuentan: son de esa spec.
    """
    texto = re.sub(r'\b\d{3}:RF-\d+[a-z]?(?:\s+a\s+(?:RF-)?\d+[a-z]?)?', ' ', texto)
    salida: set[str] = set()
    # «RF-35 a RF-40d» cubre también los de letra de en medio (RF-36b…) y los del final
    # hasta su letra: así se escribieron los rangos de la 017 y la 024.
    letras = 'abcdefghijklmnopqrstuvwxyz'
    for a, la, b, lb in re.findall(r'RF-(\d+)([a-z]?)\s+a\s+(?:RF-)?(\d+)([a-z]?)', texto):
        a, b = int(a), int(b)
        if a > b or (a == b and not (la and lb and la < lb)):
            continue
        for i in range(a, b + 1):
            hasta = letras.index(lb) + 1 if i == b and lb else (0 if i == b else len(letras))
            desde = letras.index(la) if i == a and la else 0
            if not (i == a and la):
                salida.add(str(i))
            salida |= {f'{i}{c}' for c in letras[desde:hasta]}
    for rf, resto in re.findall(r'RF-(\d+[a-z]?)((?:/\d+[a-z]?)*)', texto):
        salida.add(rf)
        salida |= {x for x in resto.split('/') if x}
    return salida


def citas_de_pruebas(raiz: Path = RAIZ) -> dict[str, set[str]]:
    """RF citados como ``NNN:RF-n`` en tests/ y frontend/src, con sus rangos y barras."""
    citas: dict[str, set[str]] = {}
    fuentes = list((raiz / 'tests').rglob('*.py')) + list((raiz / 'frontend' / 'src').rglob('*.ts*'))
    for p in fuentes:
        texto = p.read_text(encoding='utf-8', errors='replace')
        for n, rf in re.findall(r'\b(\d{3}):RF-(\d+[a-z]?)', texto):
            citas.setdefault(n, set()).add(rf)
        for n, a, b in re.findall(r'\b(\d{3}):RF-(\d+)\s+a\s+(?:RF-)?(\d+)(?![\d:])', texto):
            if int(a) < int(b):
                citas.setdefault(n, set()).update(str(i) for i in range(int(a), int(b) + 1))
        for n, _, resto in re.findall(r'\b(\d{3}):RF-(\d+[a-z]?)((?:/\d+[a-z]?)+)', texto):
            citas.setdefault(n, set()).update(x for x in resto.split('/') if x)
    return citas


class Tarea:
    """Una casilla de ``tasks.md`` con su bloque sangrado."""

    def __init__(self, id: str, hecha: bool, texto: str):
        self.id, self.hecha, self.texto = id, hecha, texto

    @property
    def digsilent(self) -> bool:
        return bool(DIGSILENT.search(self.texto.splitlines()[0]))


class Spec:
    """Una carpeta ``specs/NNN-*/``: estado, RF definidos, huecos declarados y tareas."""

    def __init__(self, numero: str, carpeta: Path, estado: str, titulo: str,
                 definiciones: list[str], huecos_declarados: set[int], tareas: list[Tarea]):
        self.numero, self.carpeta, self.estado, self.titulo = numero, carpeta, estado, titulo
        self.definiciones, self.huecos_declarados, self.tareas = definiciones, huecos_declarados, tareas

    @property
    def rf(self) -> set[str]:
        return set(self.definiciones)

    @property
    def abiertas(self) -> list[Tarea]:
        return [t for t in self.tareas if not t.hecha]

    def huecos(self) -> list[int]:
        numeros = {clave_rf(r)[0] for r in self.definiciones}
        tope = max(numeros, default=0)
        return [i for i in range(1, tope + 1) if i not in numeros and i not in self.huecos_declarados]

    def rf_de_tareas(self) -> set[str]:
        return set().union(*(rf_de_texto(t.texto) for t in self.tareas)) if self.tareas else set()


def _bloques_de_tareas(texto: str) -> list[Tarea]:
    marcas = list(_TAREA.finditer(texto))
    tareas = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        cuerpo = texto[m.start():fin]
        # El bloque acaba en la primera línea sin sangría que no sea otra tarea.
        lineas = cuerpo.splitlines()
        propio = [lineas[0]] + [l for l in _hasta_sin_sangria(lineas[1:])]
        tareas.append(Tarea(m.group(2), m.group(1) == 'x', m.group(3) + '\n' + '\n'.join(propio[1:])))
    return tareas


def _hasta_sin_sangria(lineas: list[str]):
    for l in lineas:
        if l and not l.startswith(' '):
            return
        yield l


def leer_spec(carpeta: Path) -> Spec:
    texto = (carpeta / 'spec.md').read_text(encoding='utf-8')
    est = re.search(r'^Estado:\s*(\S+)', texto, re.M)
    titulo = re.search(r'^# (.*)$', texto, re.M)
    huecos: set[int] = set()
    for a, b in _HUECO.findall(texto):
        huecos |= set(range(int(a), int(b or a) + 1))
    tareas = []
    if (carpeta / 'tasks.md').is_file():
        tareas = _bloques_de_tareas((carpeta / 'tasks.md').read_text(encoding='utf-8'))
    return Spec(carpeta.name[:3], carpeta, est.group(1).strip('.,;·') if est else '',
                titulo.group(1) if titulo else carpeta.name, _DEF.findall(texto), huecos, tareas)


def leer_specs(raiz: Path = RAIZ) -> list[Spec]:
    return [leer_spec(d) for d in sorted((raiz / 'specs').iterdir()) if (d / 'spec.md').is_file()]


def tabla(raiz: Path = RAIZ) -> str:
    """El contenido de ``specs/README.md``."""
    citas = citas_de_pruebas(raiz)
    filas = []
    for s in leer_specs(raiz):
        nombre = s.titulo.split('—', 1)[-1].strip()
        con_prueba = len(s.rf & citas.get(s.numero, set()))
        abiertas = ', '.join(t.id + (' (DIgSILENT)' if t.digsilent else '') for t in s.abiertas) or '—'
        filas.append(f'| [{s.numero}]({s.carpeta.name}/spec.md) | {nombre} | {s.estado} | '
                     f'{len(s.rf)} | {con_prueba} | {abiertas} |')
    return '\n'.join([
        '# Estado de las specs',
        '',
        'Generado por `tools/estado_specs.py --escribir` (spec 033, RF-14); no se edita a mano:',
        'la suite falla si no coincide. Estados: borrador, aprobada (con trabajo de código',
        'pendiente), implementada (solo faltan pruebas en DIgSILENT), cumplida, reservada y',
        'retirada.',
        '',
        '| Spec | Nombre | Estado | RF | RF con prueba | Tareas abiertas |',
        '| --- | --- | --- | --- | --- | --- |',
        *filas,
        '',
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Estado de las specs de specs/ (spec 033).')
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument('--escribir', action='store_true', help='reescribe specs/README.md')
    grupo.add_argument('--comprobar', action='store_true',
                       help='sale con 1 si specs/README.md no coincide con lo generado')
    args = parser.parse_args(argv)
    contenido = tabla()
    destino = RAIZ / 'specs' / 'README.md'
    if args.escribir:
        destino.write_text(contenido, encoding='utf-8', newline='\n')
        print(f'Escrito {destino.relative_to(RAIZ)}')
        return 0
    if args.comprobar:
        actual = destino.read_text(encoding='utf-8') if destino.is_file() else ''
        if actual != contenido:
            print('specs/README.md no está al día: python tools/estado_specs.py --escribir')
            return 1
        return 0
    sys.stdout.reconfigure(encoding='utf-8')
    print(contenido)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
