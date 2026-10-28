"""Ejemplos del agente desde el corpus PIDE entregado (spec 027, T20; RF-47, RF-48, RF-50).

El corpus de ``pide_dataset`` (manifiesto, fragmentos y hojas) es contexto, nunca norma
(RF-47): ilustra cómo se hizo cada cosa en los PIDE entregados; lo que manda es el contrato de
2017. De él salen, por cada artículo, sus evidencias y entregables en cada PIDE (2021, 2026);
por cada formato F01 a F15, las hojas y columnas tal como se entregaron; y las secciones de los
informes 4.1 (Largo Plazo) y 4.2 (PIDE), para redactar los del proyecto con la misma estructura.

El 2026-10-28, el 64 % de los fragmentos no tenía artículo: la clasificación miraba solo la
ruta. Aquí el artículo sale también del texto, por los términos de cada artículo del contrato.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..pide_dataset import ContratoPide
from .sinteticos import normalizar

#: Ejemplos que se guardan por artículo y PIDE, y fragmentos de cada uno que se citan.
POR_ARTICULO = 5
LARGO_CITA = 300
#: Términos de un artículo que tiene que nombrar un fragmento para ser suyo.
MIN_TERMINOS = 2
#: Filas del principio de cada hoja de formato donde están sus encabezados, y celdas guardadas.
FILAS_CABECERA = 15
MAX_CELDAS = 400
_CON_LETRAS = re.compile(r'[^\W\d_]{3}')
#: Unidades que se comparan entre un campo producido y el entregado (027:RF-49).
_UNIDADES = re.compile(r'us\$|kw\.?h|mw\.?h|kva|kvar|kw|mw|kv|km|%', re.I)

_VACIAS = {'para', 'como', 'sobre', 'desde', 'entre', 'cada', 'todos', 'todas', 'según', 'segun', 'este',
           'esta', 'estos', 'estas', 'del', 'los', 'las', 'con', 'por', 'una', 'uno', 'sus'}
_FORMATO = re.compile(r'formato\s*(?:n\s*[°º.]?\s*)?0?(\d{1,2})(?!\d)', re.I)
_RANGO = re.compile(r'\(f\)\s*(\d{1,2})\s*-\s*(\d{1,2})|formatos?\s*n?\s*[°º]?\s*0?(\d{1,2})\s*al\s*n?\s*[°º]?\s*0?(\d{1,2})',
                    re.I)
_SECCION = re.compile(r'^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÁÉÍÓÚÑ][^\n]{3,90})$')


def _terminos(texto: str) -> set[str]:
    return {w for w in re.findall(r'[a-z0-9]{5,}', normalizar(texto)) if w not in _VACIAS}


def terminos_de_articulos(contrato: ContratoPide) -> dict[int, set[str]]:
    """Los términos con que se reconoce cada artículo: título, entradas, evidencias y entregables."""
    return {a.numero: _terminos(' '.join([a.titulo, *a.entradas, *a.procedimiento, *a.evidencias,
                                          *a.entregables]))
            for a in contrato.articulos}


def articulos_de_texto(texto: str, terminos: Mapping[int, set[str]], minimo: int = MIN_TERMINOS) -> list[int]:
    """Los artículos cuyo vocabulario nombra el texto al menos ``minimo`` veces distintas."""
    t = _terminos(texto)
    puntos = {n: len(t & ts) for n, ts in terminos.items()}
    return sorted(n for n, p in puntos.items() if p >= minimo)


def formatos_de_ruta(ruta: str) -> list[str]:
    """Los formatos F01 a F15 que nombra una ruta: «FORMATO 3», «Formato N° 10», «(F) 8-13»,
    «Formatos N° 08 al N° 15»."""
    out: set[int] = set()
    for m in _RANGO.finditer(ruta):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        out |= set(range(int(a), int(b) + 1))
    if not out:
        out = {int(m.group(1)) for m in _FORMATO.finditer(ruta)}
    return [f'F{n:02d}' for n in sorted(out) if 1 <= n <= 15]


def titulo_de_seccion(linea: str) -> tuple[str, str] | None:
    """``(número, título)`` de una línea de índice o encabezado («3.1 CRITERIOS 9»), o ``None``.

    En el 4.1 de 2026 las filas de las tablas del BCRP («1 Producto bruto interno 3,3 3,1»)
    pasaban por títulos: un título es casi todo letras, en mayúsculas, sin cifras sueltas.
    """
    m = _SECCION.match(linea)
    if not m:
        return None
    titulo = re.sub(r'[\s.…]+\d{1,3}$', '', m.group(2)).strip().rstrip('.:')
    letras = [c for c in titulo if c.isalpha()]
    if (len(letras) < 4 or re.search(r'\d', titulo) or len(letras) / max(len(titulo.replace(' ', '')), 1) < 0.85
            or sum(c.isupper() for c in letras) / len(letras) < 0.8):
        return None
    return m.group(1), titulo


def _informe(ruta: str) -> str | None:
    bajo = ruta.lower()
    if '4.1' in bajo and 'largo plazo' in bajo:
        return '4.1'
    if '4.2' in bajo and 'informe pide' in bajo:
        return '4.2'
    return None


def _jsonl(path: Path) -> Iterator[dict]:
    if not path.is_file():
        return
    with path.open(encoding='utf-8') as f:
        for linea in f:
            if linea.strip():
                yield json.loads(linea)


def construir(dataset: Path | str, contrato: ContratoPide) -> dict[str, Any]:
    """Los ejemplos del agente y su cobertura (RF-48, RF-50), recorriendo el corpus una vez."""
    dataset = Path(dataset)
    terminos = terminos_de_articulos(contrato)
    por_articulo: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    secciones: dict[str, Counter] = {'4.1': Counter(), '4.2': Counter()}
    fuentes_informe: dict[str, set[str]] = {'4.1': set(), '4.2': set()}
    con_articulo = total = 0
    celdas: dict[str, set[str]] = defaultdict(set)
    for f in _jsonl(dataset / 'fragments.jsonl'):
        total += 1
        ruta, texto = f.get('relative_path') or '', f.get('text') or ''
        if str(f.get('location') or '').startswith('sheet:'):
            for codigo in formatos_de_ruta(ruta):
                if len(celdas[codigo]) < MAX_CELDAS:
                    for linea in texto.splitlines()[:FILAS_CABECERA]:
                        # Solo las que tienen texto: las cifras llenaban las 400 (F02, F05).
                        celdas[codigo] |= {c.strip() for c in linea.split('|') if _CON_LETRAS.search(c)}
        arts = sorted(set(f.get('articulos') or []) | set(articulos_de_texto(texto, terminos)))
        con_articulo += bool(arts)
        periodo = f.get('periodo') or 'sin periodo'
        for n in arts:
            lista = por_articulo[n][periodo]
            if len(lista) < POR_ARTICULO and all(x['fuente'] != ruta for x in lista):
                lista.append({'fuente': ruta, 'entregable': f.get('entregable') or '',
                              'texto': re.sub(r'\s+', ' ', texto)[:LARGO_CITA]})
        informe = _informe(ruta)
        if informe and ruta.lower().endswith(('.docx', '.pdf')):
            fuentes_informe[informe].add(ruta)
            for linea in texto.splitlines():
                titulo = titulo_de_seccion(linea)
                if titulo:
                    secciones[informe][titulo] += 1
    formatos: dict[str, list[dict]] = defaultdict(list)
    for a in _jsonl(dataset / 'assets.jsonl'):
        if a.get('kind') != 'xlsx_sheet':
            continue
        for codigo in formatos_de_ruta(a.get('relative_path') or ''):
            formatos[codigo].append({'fuente': a['relative_path'], 'hoja': a.get('sheet'),
                                     'columnas': list(a.get('cabecera') or []), 'periodo': a.get('periodo') or ''})
    articulos = {}
    for art in contrato.articulos:
        ej = por_articulo.get(art.numero, {})
        articulos[str(art.numero)] = {'titulo': art.titulo, 'evidencias': list(art.evidencias),
                                      'entregables': list(art.entregables),
                                      'ejemplos': {p: v for p, v in sorted(ej.items())},
                                      'cubierto': bool(ej)}
    salida_formatos = {}
    for fmt in contrato.formatos:
        hojas = formatos.get(fmt.codigo, [])
        salida_formatos[fmt.codigo] = {'nombre': fmt.nombre, 'campos_contrato': list(fmt.campos),
                                       'entregado': hojas[:20], 'hojas': len(hojas), 'ausente': not hojas,
                                       'celdas': sorted(celdas.get(fmt.codigo, set()))[:MAX_CELDAS]}
    informes = {k: {'fuentes': len(fuentes_informe[k]),
                    'secciones': [{'numero': n, 'titulo': t, 'veces': c}
                                  for (n, t), c in sorted(v.items(), key=lambda x: _orden(x[0][0]))]}
                for k, v in secciones.items()}
    return {'schema': 'igea-pide-ejemplos-v1', 'contrato': contrato.version, 'nota': (
                'Contexto, no norma (027:RF-47): manda el contrato de 2017.'),
            'fragmentos': total, 'fragmentos_con_articulo': con_articulo,
            'articulos': articulos, 'formatos': salida_formatos, 'informes': informes,
            'cobertura': {'articulos': sum(a['cubierto'] for a in articulos.values()),
                          'articulos_ausentes': [n for n, a in articulos.items() if not a['cubierto']],
                          'formatos': sum(not f['ausente'] for f in salida_formatos.values()),
                          'formatos_ausentes': [c for c, f in salida_formatos.items() if f['ausente']]}}


def _orden(numero: str) -> tuple[int, ...]:
    return tuple(int(x) for x in numero.split('.') if x.isdigit())


def resumen(datos: Mapping[str, Any]) -> Iterable[str]:
    """Las líneas del informe de cobertura (Hecho cuando de T20)."""
    c = datos['cobertura']
    yield (f"Fragmentos con artículo: {datos['fragmentos_con_articulo']} de {datos['fragmentos']}")
    yield f"Artículos con ejemplos: {c['articulos']} de 20" + (
        f"; sin ejemplos: {', '.join(c['articulos_ausentes'])}" if c['articulos_ausentes'] else '')
    yield f"Formatos entregados: {c['formatos']} de 15" + (
        f"; ausentes: {', '.join(c['formatos_ausentes'])}" if c['formatos_ausentes'] else '')
    for k, v in datos['informes'].items():
        yield f"Informe {k}: {v['fuentes']} fichero(s), {len(v['secciones'])} secciones"


def _palabras(texto: str) -> set[str]:
    return {w for w in re.findall(r'[a-z]{3,}', normalizar(_UNIDADES.sub(' ', texto))) if w not in _VACIAS}


def _unidades(texto: str) -> set[str]:
    return {u.lower().replace('.', '') for u in _UNIDADES.findall(texto)}


def comparar_formatos(producidos: Mapping[str, Sequence[str]], filas: Mapping[str, Sequence[Any]],
                      ejemplos: Mapping[str, Any]) -> dict[str, Any]:
    """Cada formato producido frente al entregado del mismo código (027:RF-49): qué campos
    tienen una celda de encabezado entregada con sus palabras, si la unidad coincide y la
    fracción de campos que coinciden. ``producidos``: ``{'F01 Proyección': (campos…)}``."""
    out = {}
    for nombre, campos in producidos.items():
        codigo = nombre.split()[0]
        entregado = (ejemplos.get('formatos') or {}).get(codigo) or {}
        celdas = [(c, _palabras(c)) for c in entregado.get('celdas') or []]
        detalle = []
        for campo in campos:
            p, u = _palabras(campo), _unidades(campo)
            iguales = [c for c, pc in celdas if p and (p <= pc or len(p & pc) / len(p | pc) >= 0.5)]
            unidad = not u or any(u <= _unidades(c) for c in iguales)
            detalle.append({'campo': campo, 'coincide': bool(iguales) and unidad,
                            'entregado': iguales[0] if iguales else None,
                            **({'unidad_distinta': True} if iguales and not unidad else {})})
        n = sum(d['coincide'] for d in detalle)
        out[codigo] = {'formato': nombre, 'campos': len(campos), 'coinciden': n,
                       'fraccion': n / len(campos) if campos else None,
                       'filas_producidas': len(filas.get(nombre) or []),
                       'entregado': not entregado.get('ausente', True), 'detalle': detalle}
    return out


def ultimo_ejemplos(raiz: Path | str) -> Path | None:
    """El ``ejemplos_agente.json`` más reciente bajo ``output/pide_dataset`` de ``raiz``."""
    candidatos = sorted(Path(raiz).glob('output/pide_dataset/*/ejemplos_agente.json'),
                        key=lambda p: p.stat().st_mtime)
    return candidatos[-1] if candidatos else None
