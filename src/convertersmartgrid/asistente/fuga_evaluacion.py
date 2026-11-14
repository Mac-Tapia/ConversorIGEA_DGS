"""Ninguna pregunta ni orden de un conjunto de evaluación en lo que la juzga (097:RF-19 a RF-22).

Caso real (2026-11-13, diagnóstico D077): 231 de las 308 preguntas de `docs/CONJUNTO_ABSTENCION_CALIBRACION_077.json`
estaban literales en `docs/PREGUNTAS_MAESTRO_076.md`, que entraba en el corpus 077 por `docs/*.md` desde b61ef376
(076:RF-29). La calibración del 077 se construye del reparto «corpus» de la 076, y 076:RF-31 solo apartaba el «sellado».
BM25 encontraba la pregunta copiada y no su respuesta: el umbral de abstención subía con ella, y Recall@10 del sellado con
la puerta calibrada caía a ~0,05 (sin la copia, 0,125, lo medido el 2026-11-03). Nadie lo vio, porque ninguna prueba
miraba qué textos del corpus son también preguntas del examen. El usuario decidió el 2026-11-13 (opción A) que el
documento se queda en el corpus, como en la 076 T8: lo que cambia es de dónde salen las preguntas que lo miden (097:RF-19,
`evaluacion_rag.conjunto_de_entregables`), y este módulo comprueba que no se repita (RF-20).

Las mismas comprobaciones valen para el intérprete de órdenes (085): ninguna orden de entrenamiento con el texto de una
que lo examina. Este módulo solo compara textos; leer el corpus o preparar el del intérprete lo hace quien lo llama.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Una pregunta más corta no se comprueba, se cuenta aparte. Medido el 2026-11-13 en el corpus 077: las coincidencias
#: que no son copia llegan a cinco palabras («¿Y «Con proyecto»?» en 38 ficheros, «si no se puede deducir» en un
#: procedimiento, «como va el avance» citada en la 075), y la copia del maestro traía 280 preguntas de seis o más. Una
#: copia de un conjunto lleva siempre preguntas largas: con ellas basta para verla.
MIN_PALABRAS = 6

#: Los conjuntos de evaluación de la recuperación y el corpus que miden cada uno (047:RF-4, 077:RF-44, 097:RF-16). Las
#: filas de la 076 que miden el 077 ya están en sus dos conjuntos (077:RF-44); el JSONL de la 076 no se nombra aquí
#: porque nada de `src/` lo lee (076:RF-16): lo compara entero la prueba de gobierno.
CONJUNTOS_RAG: dict[str, tuple[str, ...]] = {
    '047': ('docs/RAG_PREGUNTAS_SINTETICAS_047.json', 'docs/RAG_ABSTENCION_CALIBRACION_047.json',
            'docs/RAG_ABSTENCION_SELLADO_047.json', 'docs/RAG_PREGUNTAS_OPERADOR_097.json'),
    '077': ('docs/CONJUNTO_ABSTENCION_CALIBRACION_077.json', 'docs/CONJUNTO_ABSTENCION_SELLADO_077.json',
            'docs/CONJUNTO_FUERA_077.json', 'docs/RAG_PREGUNTAS_OPERADOR_097.json'),
}


@dataclass(frozen=True)
class Pregunta:
    conjunto: str
    texto: str
    #: Los ficheros que la propia pregunta cita como respuesta: ahí puede aparecer, porque se escribió desde ellos.
    fuentes: frozenset[str] = frozenset()


def palabras(texto: str) -> list[str]:
    """Sin tildes, mayúsculas ni signos: «¿Qué es…?» en la pregunta y «Pregunta: que es…» en la copia son lo mismo."""
    plano = unicodedata.normalize('NFKD', str(texto).casefold())
    return re.findall(r'[a-z0-9]+', ''.join(c for c in plano if not unicodedata.combining(c)))


def _fuentes(fila: Mapping[str, Any]) -> frozenset[str]:
    out = [str(fila['fichero'])] if fila.get('fichero') else []
    out += [str(f.get('fichero')) for f in fila.get('fuentes') or () if isinstance(f, Mapping) and f.get('fichero')]
    return frozenset(out)


def preguntas_de(repo: Path, rel: str, reparto: str | None = None) -> list[Pregunta]:
    """Las preguntas de un conjunto del repositorio, de cualquiera de sus formas (lista ``preguntas``, listas de
    preguntas sueltas como el de las ajenas al proyecto, o el JSONL de la 076, entero o de un ``reparto``)."""
    ruta = Path(repo) / rel
    texto = ruta.read_text(encoding='utf-8')
    if rel.endswith('.jsonl'):
        filas: list[Any] = [json.loads(x) for x in texto.splitlines() if x.strip()]
        filas = [f for f in filas if reparto is None or f.get('reparto') == reparto]
    else:
        datos = json.loads(texto)
        filas = list(datos.get('preguntas') or ())
        if not filas:                                                  # CONJUNTO_FUERA_077: {'calibracion': [...], ...}
            filas = [x for v in datos.values() if isinstance(v, list) for x in v]
    out = []
    for f in filas:
        if isinstance(f, str):
            out.append(Pregunta(rel, f))
        elif isinstance(f, Mapping) and f.get('pregunta'):
            sin = f.get('sin_respuesta') is True or f.get('tipo') == 'sin_respuesta'
            out.append(Pregunta(rel, str(f['pregunta']), frozenset() if sin else _fuentes(f)))
    return out


def _exenta(p: Pregunta, fichero: str) -> bool:
    """Su propia fuente, también si cambió de carpeta con el mismo nombre (097:RF-18)."""
    nombre = fichero.rsplit('/', 1)[-1]
    return fichero in p.fuentes or any(f.rsplit('/', 1)[-1] == nombre for f in p.fuentes)


def fugas(textos: Mapping[str, str], preguntas: Iterable[Pregunta], min_palabras: int = MIN_PALABRAS) -> dict[str, Any]:
    """Qué preguntas aparecen literales en qué ficheros que no son su fuente (097:RF-20).

    Va por palabras, buscando cada pregunta por sus primeras (hasta ``MIN_PALABRAS``), no por subcadena: el corpus 077
    tiene más de 20 000 trozos y hay cientos de preguntas; buscar cada una en cada fichero tardaba más que construir el
    índice. La comprobación permanente mira desde seis palabras; quien forma un conjunto las mira todas
    (``min_palabras=1``, 097:RF-19): ahí una coincidencia que no es copia solo quita una pregunta, y el documento del
    maestro trae 67 de menos de seis."""
    por_inicio: dict[tuple[str, ...], list[tuple[Pregunta, list[str]]]] = defaultdict(list)
    cortas = 0
    for p in preguntas:
        ps = palabras(p.texto)
        if not ps or len(ps) < min_palabras:
            cortas += 1
            continue
        por_inicio[tuple(ps[:MIN_PALABRAS])].append((p, ps))
    largos = sorted({len(k) for k in por_inicio})
    halladas: dict[tuple[str, str, str], None] = {}
    for fichero in sorted(textos):
        ps = palabras(textos[fichero])
        for i in range(len(ps)):
            for n in largos:
                for p, q in por_inicio.get(tuple(ps[i:i + n])) or ():
                    if ps[i:i + len(q)] == q and not _exenta(p, fichero):
                        halladas[(p.conjunto, p.texto, fichero)] = None
    lista = [{'conjunto': c, 'pregunta': t, 'fichero': f} for c, t, f in halladas]
    return {'fugas': lista, 'comprobadas': sum(len(v) for v in por_inicio.values()), 'cortas_sin_comprobar': cortas}


def textos_por_fichero(frags: Sequence[Any]) -> dict[str, str]:
    """Los trozos del índice juntos por fichero, en su orden: una pregunta partida entre dos trozos también se ve."""
    out: dict[str, list[str]] = defaultdict(list)
    for f in frags:
        out[str(f.fuente).rsplit(':', 1)[0]].append(str(f.texto))
    return {k: '\n'.join(v) for k, v in out.items()}


def fugas_del_corpus(repo: Path, corpus: str, frags: Sequence[Any],
                     otros: Sequence[tuple[str, str]] = ()) -> dict[str, Any]:
    """Las preguntas de los conjuntos que miden ``corpus`` (y de ``otros``, pares de JSONL y reparto) que el propio corpus
    contiene (097:RF-20). Del JSONL de la 076 se examina el reparto ``sellado``: el ``corpus`` es corpus por decisión del
    usuario (076:RF-29), y lo que de él mide al 077 ya está en su calibración."""
    rels = [(r, None) for r in CONJUNTOS_RAG[corpus]] + [(r, rep) for r, rep in otros]
    rels = [(r, rep) for r, rep in rels if (Path(repo) / r).is_file()]
    preguntas = [p for rel, rep in rels for p in preguntas_de(repo, rel, rep)]
    return {'corpus': corpus, 'conjuntos': [r if rep is None else f'{r}#{rep}' for r, rep in rels],
            **fugas(textos_por_fichero(frags), preguntas)}


def fugas_del_interprete(filas: Sequence[Mapping[str, Any]], vedadas: Mapping[str, Iterable[str]]) -> dict[str, int]:
    """Cuántos textos de cada conjunto que examina al intérprete están también en su entrenamiento (097:RF-21, 085).

    Devuelve solo cuentas: las órdenes humanas no salen del almacén ni en el mensaje de una prueba (075:RF-21)."""
    from .maestro_real import clave_texto

    entrena = {clave_texto(r['texto']) for r in filas if r['particion'] == 'entrenamiento'}
    examina: dict[str, set[str]] = defaultdict(set)
    for r in filas:
        if r['particion'] != 'entrenamiento':
            examina[str(r.get('conjunto') or r['particion'])].add(clave_texto(r['texto']))
    for nombre, textos in vedadas.items():
        examina[nombre] |= {clave_texto(t) for t in textos if str(t).strip()}
    return {nombre: len(textos & entrena) for nombre, textos in sorted(examina.items())}
