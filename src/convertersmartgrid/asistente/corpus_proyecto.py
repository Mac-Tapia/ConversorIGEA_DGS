"""El corpus ampliado del índice: skills, documentos, planes, tareas, frontend y API (spec 077).

Solo decide qué ficheros entran y cómo se parten; buscar sigue en ``indice.py``. El corpus de la 047 no pasa por
aquí: sus trozos son los que se midieron, y cambiarlos invalidaría sus umbrales (077:RF-47).

Se parte sin perder texto (077:RF-11): el troceado de la 047 cortaba cada párrafo en 1 500 caracteres, y una tabla
de `CLAUDE.md` es un solo párrafo, de modo que las últimas filas no existían para el índice.
"""
from __future__ import annotations

import json
import re
import time
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import lectura_proyecto as lp

#: Identificador del corpus: las mediciones lo guardan, y otro corpus no hereda sus umbrales.
CORPUS = '077'
MAX_TROZO = 1200
#: ``nomic-embed-text`` da 768 dimensiones; en float32 cada vector ocupa 3 072 bytes.
DIMENSION_VECTOR = 768
_ESQUEMA_GENERADO = 'frontend/src/api/esquema.ts'
_DECLARACION = re.compile(r'^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|const|let|class|interface|type|enum)\s+([\w$]+)')
_INICIO_LISTA_TAREAS = re.compile(r'^- \[[ xX]\]')
_SEPARADOR_TABLA = re.compile(r'^\|?[\s:|-]+\|?$')


def ficheros_extra(repo: Path) -> list[Path]:
    """Lo que el corpus ampliado añade al de la 047, sin nada que la lista negra rechace (077:RF-1 a RF-5, RF-15)."""
    candidatos: list[Path] = [repo / 'CLAUDE.md', repo / 'VNR-GIS.md', *sorted(repo.glob('README*'))]
    candidatos += sorted((repo / '.claude' / 'skills').glob('*/SKILL.md'))
    candidatos += sorted((repo / 'docs').glob('*.md'))
    candidatos += sorted((repo / 'docs' / 'procedimientos').glob('*.md'))
    candidatos += sorted((repo / 'docs' / 'runbooks').glob('*.md'))
    candidatos += sorted((repo / 'docs' / 'superpowers').rglob('*.md'))
    candidatos += sorted((repo / 'specs').glob('*/plan.md')) + sorted((repo / 'specs').glob('*/tasks.md'))
    candidatos += [repo / lp.OPENAPI]
    fuente = repo / 'frontend' / 'src'
    candidatos += sorted(p for p in fuente.rglob('*') if p.suffix in ('.ts', '.tsx'))
    salida = []
    for p in candidatos:
        rel = p.relative_to(repo).as_posix()
        if rel == _ESQUEMA_GENERADO or not p.is_file():
            continue
        try:
            lp.comprobar_ruta(repo, rel)
        except lp.RutaRechazada:
            continue
        salida.append(p)
    return list(dict.fromkeys(salida))


def _partir(texto: str, largo: int = MAX_TROZO) -> list[str]:
    """Una línea que no cabe se parte en ventanas: se pierde el contexto de la frase, pero no sus palabras."""
    return [texto[i:i + largo] for i in range(0, len(texto), largo)] or ['']


def _bloque(rel: str, titulo: str, inicio: int, lineas: Sequence[str]) -> list[tuple[str, str]]:
    """Las líneas seguidas en trozos que caben, cada uno con la línea donde empieza."""
    cabecera = f'{rel} · {titulo}: '
    sitio = MAX_TROZO - len(cabecera)
    out, actual, desde, largo = [], [], inicio, 0
    for n, linea in enumerate(lineas, inicio):
        if len(linea) > sitio:
            if actual:
                out.append((f'{rel}:{desde}', cabecera + ' '.join(actual)))
                actual, largo = [], 0
            out += [(f'{rel}:{n}', cabecera + parte) for parte in _partir(linea, sitio)]
            desde = n + 1
            continue
        if actual and largo + len(linea) + 1 > sitio:
            out.append((f'{rel}:{desde}', cabecera + ' '.join(actual)))
            actual, largo = [], 0
        if not actual:
            desde = n
        actual.append(linea)
        largo += len(linea) + 1
    if actual:
        out.append((f'{rel}:{desde}', cabecera + ' '.join(actual)))
    return out


def _de_tabla(rel: str, titulo: str, inicio: int, lineas: Sequence[str]) -> list[tuple[str, str]]:
    """Una fila, un trozo, con la cabecera delante: «falta T5» no dice nada sin el título de su columna."""
    filas = [(n, x) for n, x in enumerate(lineas, inicio) if not _SEPARADOR_TABLA.match(x)]
    if len(filas) <= 1:
        return _bloque(rel, titulo, inicio, [x for _, x in filas])
    cabecera = filas[0][1]
    out = _bloque(rel, titulo, filas[0][0], [cabecera])
    for n, fila in filas[1:]:
        out += _bloque(rel, titulo, n, [f'{cabecera} {fila}'])
    return out


def de_markdown(rel: str, texto: str) -> list[tuple[str, str]]:
    """Por títulos y párrafos, con las tablas fila a fila y las tareas una a una (077:RF-11)."""
    out: list[tuple[str, str]] = []
    titulo, inicio, bloque = '', 1, []

    def cerrar() -> None:
        if not bloque:
            return
        if all(x.startswith('|') for x in bloque):
            out.extend(_de_tabla(rel, titulo, inicio, bloque))
        elif any(_INICIO_LISTA_TAREAS.match(x) for x in bloque):
            desde, parte = inicio, []
            for n, x in enumerate(bloque, inicio):
                if _INICIO_LISTA_TAREAS.match(x) and parte:
                    out.extend(_bloque(rel, titulo, desde, parte))
                    desde, parte = n, []
                parte.append(x)
            out.extend(_bloque(rel, titulo, desde, parte))
        else:
            out.extend(_bloque(rel, titulo, inicio, bloque))
        bloque.clear()

    for n, cruda in enumerate(texto.splitlines(), 1):
        linea = cruda.strip()
        if linea.startswith('#'):
            cerrar()
            titulo = linea.lstrip('# ').strip()
            out.extend(_bloque(rel, titulo, n, [titulo]))
            inicio = n + 1
        elif linea:
            if not bloque:
                inicio = n
            bloque.append(linea)
        else:
            cerrar()
    cerrar()
    return out


def de_frontend(rel: str, texto: str) -> list[tuple[str, str]]:
    """Por declaración de primer nivel, con el comentario que la precede y sin perder ninguna línea."""
    out: list[tuple[str, str]] = []
    nombre, inicio, bloque = 'cabecera', 1, []
    lineas = texto.splitlines()
    for n, cruda in enumerate(lineas, 1):
        m = _DECLARACION.match(cruda)
        if m and bloque and any(x.strip() for x in bloque):
            comentario: list[str] = []
            while bloque and bloque[-1].lstrip().startswith(('//', '/*', '*')):
                comentario.insert(0, bloque.pop())
            out += _bloque(rel, nombre, inicio, [x.strip() for x in bloque if x.strip()]) if bloque else []
            bloque, inicio = comentario, n - len(comentario)
        if m:
            nombre = m.group(1)
        bloque.append(cruda)
    out += _bloque(rel, nombre, inicio, [x.strip() for x in bloque if x.strip()])
    return out


def _texto_operacion(ruta: str, op: dict[str, Any]) -> str:
    partes = [f"API {op['metodo']} {ruta}: {op['resumen']}".rstrip(': ')]
    if op['descripcion']:
        partes.append(op['descripcion'])
    if op['parametros']:
        partes.append('Parámetros: ' + ', '.join(str(p['nombre']) for p in op['parametros']) + '.')
    if op['cuerpo']:
        partes.append('Cuerpo: ' + json.dumps(op['cuerpo'], ensure_ascii=False, sort_keys=True))
    if op['respuesta']:
        partes.append('Respuesta: ' + json.dumps(op['respuesta'], ensure_ascii=False, sort_keys=True))
    return ' '.join(partes)


def de_openapi(rel: str, texto: str) -> list[tuple[str, str]]:
    """Una ruta y un método, un trozo o varios si no cabe (077:RF-5)."""
    documento, lineas = json.loads(texto), texto.splitlines()
    out = []
    for ruta in sorted(documento.get('paths') or {}):
        linea = lp.linea_de_ruta(lineas, ruta)
        for op in lp.operaciones_de(documento, ruta):
            out += [(f'{rel}:{linea}', parte) for parte in _partir(_texto_operacion(ruta, op))]
    return out


def trozos(rel: str, texto: str) -> list[tuple[str, str]]:
    """Los trozos de un fichero que el corpus de la 047 no parte por su cuenta."""
    if rel == lp.OPENAPI:
        return de_openapi(rel, texto)
    if rel.endswith(('.ts', '.tsx')):
        return de_frontend(rel, texto)
    return de_markdown(rel, texto)


def con_cache(ficheros: Sequence[Path], repo: Path, carpeta: Path, trocear: Callable[[Path, str], list[tuple[str, str]]],
              guardar: Callable[[Path, str], None]) -> tuple[list[tuple[str, str]], list[str]]:
    """Los trozos de todos los ficheros, volviendo a partir solo los que cambiaron (077:RF-12)."""
    ruta = carpeta / 'por_fichero.json'
    try:
        previo = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        previo = {}
    actual, trozados, todos = {}, [], []
    for p in ficheros:
        rel = p.relative_to(repo).as_posix()
        st = p.stat()
        anterior = previo.get(rel) if isinstance(previo, dict) else None
        if anterior and anterior.get('mtime_ns') == st.st_mtime_ns and anterior.get('size') == st.st_size:
            suyos = [(a, b) for a, b in anterior['trozos']]
        else:
            suyos = trocear(p, rel)
            trozados.append(rel)
        actual[rel] = {'mtime_ns': st.st_mtime_ns, 'size': st.st_size, 'trozos': suyos}
        todos += suyos
    guardar(ruta, json.dumps(actual, ensure_ascii=False))
    return todos, trozados


def medir_tamano(hacer: Callable[[], Any], textos_de: Callable[[Any], Sequence[str]]) -> dict[str, Any]:
    """Trozos, caracteres, bytes de los vectores previstos, memoria y tiempo de lo construido (077:RF-14).

    La memoria es la que ve ``tracemalloc``, de objetos de Python; no cuenta el intérprete ni los vectores, que van aparte."""
    tracemalloc.start()
    inicio = time.perf_counter()
    objeto = hacer()
    segundos = time.perf_counter() - inicio
    _, pico = tracemalloc.get_traced_memory()
    actual, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    textos = textos_de(objeto)
    vectores = len(textos) * DIMENSION_VECTOR * 4
    return {'trozos': len(textos), 'caracteres': sum(map(len, textos)), 'largo_maximo': max(map(len, textos), default=0),
            'vectores_previstos_mib': round(vectores / 2**20, 2), 'dimension_vector': DIMENSION_VECTOR,
            'memoria_python_mib': round(actual / 2**20, 2), 'memoria_pico_mib': round(pico / 2**20, 2),
            'segundos_construir': round(segundos, 3)}
