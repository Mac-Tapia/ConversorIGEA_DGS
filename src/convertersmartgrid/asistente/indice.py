"""Índice local del proyecto para responder cómo funciona el conversor (spec 026, RF-17, RF-18).

Trozos de ``CODIGO_FUENTE.md`` (cada fichero con su spec), de las specs (cada RF), de los
docstrings de ``src/`` y ``tools/`` (cada módulo, función y clase), del manual de órdenes y
de la constitución. Se busca por palabras (BM25, sin dependencias) y, si hay vectores, también
por significado, fusionando las dos listas por posición (047:RF-21); la respuesta cita de dónde
sale cada cosa, dice con qué métodos se halló (047:RF-26) y, si nada responde, que no lo sabe.

Los vectores del corpus nunca se calculan al responder (047:RF-23): tardan minutos y son un
trabajo aparte, cancelable (``calcular_vectores``).

Se reconstruye cuando cambia algún fichero (huella de fechas y tamaños): el índice nunca
habla de un código que ya no existe.

Hay dos corpus (spec 077): el de la 047, con el que se midieron sus umbrales y que no cambia, y el ampliado, con
skills, documentos, planes, tareas, frontend y API, que no se sirve hasta pasar su propia medición.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..runtime_paths import staging_publicacion
from . import almacen, corpus_proyecto, lectura_proyecto
from .ollama import MODELO_EMBEDDINGS
from .sinteticos import normalizar

_VACIAS = {
    'de', 'la', 'el', 'en', 'y', 'a', 'los', 'las', 'del', 'que', 'se', 'un', 'una', 'por',
    'con', 'para', 'es', 'al', 'lo', 'como', 'su', 'sus', 'o', 'no', 'si', 'cada', 'sin',
    'hay', 'mas', 'más', 'este', 'esta', 'esto', 'ese', 'esa',
}
#: Por debajo de esta puntuación BM25 ningún trozo responde la pregunta.
UMBRAL_BM25 = 2.0
UMBRAL_COSENO = 0.55
#: Política de 047 T2, fijada antes de medir: ver el plan de la spec.
K_RRF = 60
CANDIDATOS = 30
#: Cada lista aporta a lo sumo esto a la fusión: con todo el corpus con coseno positivo, la cola
#: de la lista de vectores sumaría puntos a fragmentos que nada tienen que ver.
TOPE_LISTA = 100
#: ``nomic-embed-text`` distingue consulta y documento por el prefijo de la tarea (su ficha).
PREFIJO_CONSULTA = 'search_query: '
PREFIJO_DOCUMENTO = 'search_document: '
_LARGO_EMBEDDING = 2000
#: Códigos de red o de equipo: letras seguidas de cifras (SE50106, TM106).
_CODIGO = re.compile(r'\b[A-Za-z]{1,8}\d{2,}[A-Za-z0-9]*\b')
CORPUS_047 = '047'
CORPUS_AMPLIADO = corpus_proyecto.CORPUS
#: Cambia cuando cambia lo que se guarda de cada trozo: un índice viejo no traía su vigencia.
_VERSION_INDICE = 'v2'
#: De lo leído pasa al LLM a lo sumo esto por lectura: su contexto es de un modelo en 8 GB de GPU.
_LARGO_LECTURA = 4000


def fusion_rrf(rankings: Sequence[Sequence[Any]], *, k: int = 60) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion: combina posiciones, no escalas de score incompatibles."""
    puntos: dict[Any, float] = {}
    mejor_posicion: dict[Any, int] = {}
    for ranking in rankings:
        vistos = set()
        for posicion, identificador in enumerate(ranking, 1):
            if identificador in vistos:
                continue
            vistos.add(identificador)
            puntos[identificador] = puntos.get(identificador, 0.0) + 1.0 / (k + posicion)
            mejor_posicion[identificador] = min(mejor_posicion.get(identificador, posicion), posicion)
    orden = sorted(puntos, key=lambda x: (-puntos[x], mejor_posicion[x], str(x)))
    return [{'id': identificador, 'score': puntos[identificador]} for identificador in orden]


class RerankerNoDisponible(RuntimeError):
    """El reranker no puede correr; se aparta y queda el orden anterior (047:RF-30)."""


@dataclass
class Fragmento:
    id: int
    fuente: str
    texto: str
    vigencia: str = 'vigente'
    estado_spec: str | None = None


def palabras(texto: str) -> list[str]:
    return [p for p in re.findall(r'[a-z0-9_]+', normalizar(texto)) if len(p) > 2 and p not in _VACIAS]


def _ficheros(repo: Path) -> list[Path]:
    out = [repo / 'CODIGO_FUENTE.md', repo / 'docs' / 'MANUAL_COMANDOS.md', repo / 'docs' / 'constitution.md']
    out += sorted((repo / 'specs').glob('*/spec.md'))
    out += sorted((repo / 'src').rglob('*.py')) + sorted((repo / 'tools').glob('*.py'))
    return [p for p in out if p.is_file()]


def _ficheros_de(repo: Path, corpus: str) -> list[Path]:
    base = _ficheros(repo)
    if corpus == CORPUS_047:
        return base
    return list(dict.fromkeys(base + corpus_proyecto.ficheros_extra(repo)))


def huella(repo: Path, corpus: str = CORPUS_047) -> str:
    h = hashlib.sha256(_VERSION_INDICE.encode())
    for p in _ficheros_de(repo, corpus):
        st = p.stat()
        h.update(f'{p.relative_to(repo).as_posix()}|{st.st_mtime_ns}|{st.st_size}\n'.encode())
    return h.hexdigest()


def _de_python(rel: str, texto: str) -> list[tuple[str, str]]:
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return []
    out = []
    if (doc := ast.get_docstring(arbol)):
        out.append((f'{rel}:1', f'{rel}: {doc}'))
    for n in arbol.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and (doc := ast.get_docstring(n)):
            out.append((f'{rel}:{n.lineno}', f'{rel} · {n.name}: {doc}'))
    return out


def _de_spec(rel: str, spec: str, texto: str) -> list[tuple[str, str]]:
    out = []
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        m = re.match(r'^- (RF-[\w-]+): (.*)', linea)
        if not m:
            continue
        cuerpo = [m.group(2)]
        for siguiente in lineas[i + 1:]:
            if not siguiente.startswith('  ') or not siguiente.strip():
                break
            cuerpo.append(siguiente.strip())
        out.append((f'{rel}:{i + 1}', f'{spec} {m.group(1)}: {" ".join(cuerpo)}'))
    return out


def _de_markdown(rel: str, texto: str) -> list[tuple[str, str]]:
    out, titulo, inicio, bloque = [], '', 1, []
    for i, linea in enumerate(texto.splitlines() + [''], 1):
        if linea.startswith('#'):
            titulo = linea.lstrip('# ').strip()
        if linea.strip():
            if not bloque:
                inicio = i
            bloque.append(linea.strip())
        elif bloque:
            out.append((f'{rel}:{inicio}', f'{rel} · {titulo}: {" ".join(bloque)}'[:1500]))
            bloque = []
    return out


def _trozos_de(p: Path, rel: str) -> list[tuple[str, str]]:
    texto = p.read_text(encoding='utf-8', errors='replace')
    if p.suffix == '.py':
        return _de_python(rel, texto)
    if rel == 'CODIGO_FUENTE.md':
        out = []
        for i, linea in enumerate(texto.splitlines(), 1):
            m = re.match(r'^\| `([^`]+)` \| (.+) \| (.+) \|$', linea)
            if m:
                out.append((f'{rel}:{i}', f'{m.group(1)}: {m.group(2)} (spec {m.group(3)})'))
        return out
    if rel.startswith('specs/'):
        return _de_spec(rel, p.parent.name, texto)
    return _de_markdown(rel, texto)


def _trozos_ampliado(p: Path, rel: str) -> list[tuple[str, str]]:
    """Lo que ya tiene forma en la 047 conserva su texto y sus vectores (077:RF-13); lo demás, sin perder líneas (RF-11)."""
    if p.suffix == '.py' or rel == 'CODIGO_FUENTE.md' or (rel.startswith('specs/') and p.name == 'spec.md'):
        return _trozos_de(p, rel)
    return corpus_proyecto.trozos(rel, p.read_text(encoding='utf-8', errors='replace'))


def _trozos_segun(p: Path, rel: str, corpus: str) -> list[tuple[str, str]]:
    return _trozos_de(p, rel) if corpus == CORPUS_047 else _trozos_ampliado(p, rel)


def _con_vigencia(repo: Path, trozos: Sequence[tuple[str, str]]) -> list[Fragmento]:
    """Cada trozo con su vigencia y el estado de su spec (077:RF-6, RF-7, RF-10), mirados una vez por fichero."""
    por_fichero: dict[str, tuple[str, str | None]] = {}
    out = []
    for i, (fuente, texto) in enumerate(trozos):
        rel = fuente.rsplit(':', 1)[0]
        if rel not in por_fichero:
            por_fichero[rel] = lectura_proyecto.vigencia_de(repo, rel)
        out.append(Fragmento(i, fuente, texto, *por_fichero[rel]))
    return out


def fragmentos(repo: Path, corpus: str = CORPUS_047) -> list[Fragmento]:
    """Los trozos del proyecto, cada uno con su fuente ``fichero:línea``."""
    trozos: list[tuple[str, str]] = []
    for p in _ficheros_de(repo, corpus):
        trozos += _trozos_segun(p, p.relative_to(repo).as_posix(), corpus)
    return _con_vigencia(repo, trozos)


def verificables(repo: Path, hallados: Sequence[dict], corpus: str = CORPUS_047) -> list[dict]:
    """Los hallados cuyo trozo sigue en su fichero (047:RF-29): el fichero puede cambiar bajo un
    índice ya cargado, y una cita a un texto que ya no está no se puede comprobar."""
    por_fichero: dict[str, set[tuple[str, str]]] = {}
    out = []
    for h in hallados:
        rel = str(h['fuente']).rsplit(':', 1)[0]
        if rel not in por_fichero:
            p = repo / rel
            try:
                por_fichero[rel] = set(_trozos_segun(p, rel, corpus)) if p.is_file() else set()
            except OSError:
                por_fichero[rel] = set()
        if (h['fuente'], h['texto']) in por_fichero[rel]:
            out.append(h)
    return out


@dataclass(frozen=True)
class Abstencion:
    """Cuándo hay respuesta, con umbrales calibrados (047:RF-31 a RF-34). «No lo sé» antes que citar
    un trozo que no responde: con el coseno fijo en 0,55, las diez preguntas ajenas al proyecto salían con citas."""
    calibrada: bool = False
    modelo_reranker: str | None = None
    umbral_reranker: float | None = None
    umbral_coseno: float | None = None
    umbral_bm25: float | None = None
    umbral_bm25_solo: float | None = None

    def decide(self, candidatos: Sequence[dict], *, etiqueta: str | None, con_vectores: bool,
               con_codigo: bool) -> tuple[bool, str]:
        """Si hay respuesta y con qué señal se decidió."""
        if not self.calibrada or not candidatos:
            return False, 'sin_calibrar' if not self.calibrada else 'sin_candidatos'
        if con_codigo:
            return True, 'codigo'                                       # 047:RF-37
        if (etiqueta and self.umbral_reranker is not None and etiqueta == f'reranker:{self.modelo_reranker}'
                and all('reranker' in c for c in candidatos)):
            return max(c['reranker'] for c in candidatos) >= self.umbral_reranker, 'reranker'
        if con_vectores:
            if self.umbral_bm25 is None and self.umbral_coseno is None:
                return False, 'sin_calibrar'
            return ((self.umbral_bm25 is not None and max(c['bm25'] for c in candidatos) >= self.umbral_bm25)
                    or (self.umbral_coseno is not None
                        and max(c['coseno'] for c in candidatos) >= self.umbral_coseno)), 'hibrido'
        if self.umbral_bm25_solo is None:
            return False, 'sin_calibrar'
        return max(c['bm25'] for c in candidatos) >= self.umbral_bm25_solo, 'bm25'


class Indice:
    def __init__(self, frags: Sequence[Fragmento], vectores: Any = None, filas: Sequence[int] | None = None,
                 corpus: str = CORPUS_047):
        """``vectores``: uno por trozo, con ``None`` donde falte, o una matriz cuyas ``filas`` dicen de qué trozo es cada una."""
        self.corpus = corpus
        self.frags = list(frags)
        self.tokens = [palabras(f.texto) for f in self.frags]
        self.df = Counter(t for toks in self.tokens for t in set(toks))
        self.largo_medio = sum(len(t) for t in self.tokens) / max(len(self.tokens), 1)
        self.vectores = vectores
        self._matriz, self._filas = _normalizada(vectores, filas)

    @property
    def cobertura(self) -> float:
        """La fracción de trozos con vector: un trozo editado se queda sin él hasta el siguiente trabajo."""
        return len(self._filas) / len(self.frags) if self.frags else 0.0

    @property
    def con_vector(self) -> int:
        return len(self._filas)

    def bm25(self, consulta: str, k1: float = 1.4, b: float = 0.75) -> list[float]:
        q = palabras(consulta)
        n = len(self.frags)
        out = []
        for toks in self.tokens:
            tf = Counter(toks)
            s = 0.0
            for t in q:
                if t in tf:
                    idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(toks) / self.largo_medio))
            out.append(s)
        return out

    def cosenos(self, vector: Sequence[float] | None) -> list[float] | None:
        """El coseno de cada trozo, o ``None`` si no hay con qué: otro modelo da otra dimensión."""
        if vector is None or self._matriz is None:
            return None
        import numpy as np

        q = np.asarray(vector, dtype=np.float32)
        if q.ndim != 1 or q.shape[0] != self._matriz.shape[1]:
            return None
        q = q / (float(np.linalg.norm(q)) or 1.0)
        semantico = [0.0] * len(self.frags)
        for fila, valor in zip(self._filas, (self._matriz @ q).tolist(), strict=True):
            semantico[fila] = valor
        return semantico

    def nombra_codigo(self, consulta: str, hallados: Sequence[dict]) -> bool:
        """¿Algún trozo hallado trae tal cual un código de la consulta (047:RF-37)?"""
        codigos = {c.lower() for c in _CODIGO.findall(consulta)}
        return bool(codigos) and any(codigos & set(palabras(h['texto'])) for h in hallados)

    def primero_los_codigos(self, consulta: str, hallados: Sequence[dict]) -> list[dict]:
        """Los trozos con un código pedido, por delante y en su orden (047:RF-28): SE50106 es esa
        SED y no otra; ni el significado ni un cross-encoder saben que el parecido no vale."""
        codigos = {c.lower() for c in _CODIGO.findall(consulta)}
        if not codigos:
            return list(hallados)

        def con(h: dict) -> bool:
            return bool(codigos & set(palabras(h['texto'])))

        return [h for h in hallados if con(h)] + [h for h in hallados if not con(h)]

    def buscar(self, consulta: str, k: int = 6, vector: list[float] | None = None) -> list[dict[str, Any]]:
        """Los ``k`` trozos que mejor responden: BM25 y, si hay vectores, también el coseno, fusionados
        por posición (047:RF-21). Sus escalas no se comparan: un BM25 de 30 aplastaba al coseno."""
        lexico = self.bm25(consulta)
        semantico = self.cosenos(vector)

        def lista(puntos: Sequence[float]) -> list[int]:
            return sorted((i for i, x in enumerate(puntos) if x > 0), key=lambda i: (-puntos[i], i))[:TOPE_LISTA]

        fusion = fusion_rrf([lista(lexico)] + ([lista(semantico)] if semantico is not None else []), k=K_RRF)
        hallados = [{'id': x['id'], 'fuente': self.frags[x['id']].fuente, 'texto': self.frags[x['id']].texto,
                     'vigencia': self.frags[x['id']].vigencia, 'estado_spec': self.frags[x['id']].estado_spec,
                     'bm25': lexico[x['id']], 'coseno': semantico[x['id']] if semantico is not None else 0.0,
                     'puntos': x['score']} for x in fusion]
        return self.primero_los_codigos(consulta, hallados)[:k]


def _normalizada(vectores: Any, filas: Sequence[int] | None) -> tuple[Any, list[int]]:
    """Matriz float32 de vectores unidad y el trozo de cada fila; sin numpy, sin vectores: el BM25 no lo necesita."""
    if vectores is None or len(vectores) == 0:
        return None, []
    try:
        import numpy as np
    except ImportError:
        return None, []
    if filas is None:
        filas = [i for i, v in enumerate(vectores) if v is not None and len(v)]
        vectores = [vectores[i] for i in filas]
    if not len(filas):
        return None, []
    matriz = np.asarray(vectores, dtype=np.float32)
    normas = np.linalg.norm(matriz, axis=1, keepdims=True)
    normas[normas == 0] = 1.0
    return matriz / normas, list(filas)


def _carpeta(corpus: str = CORPUS_047) -> Path:
    return almacen.raiz() / 'indice' if corpus == CORPUS_047 else almacen.raiz() / 'indice' / corpus


def _clave(texto: str) -> str:
    return hashlib.sha1(texto.encode('utf-8')).hexdigest()


def _escribir(ruta: Path, escribir: Callable[[Path], None]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(ruta) as temporal:
        escribir(temporal)
        os.replace(temporal, ruta)


def _leer_vectores(corpus: str = CORPUS_047) -> tuple[Any, dict[str, int]]:
    """La matriz guardada y la fila de cada clave. Rotos o de otro modelo equivalen a no tenerlos:
    una respuesta nunca cae por un fichero de vectores."""
    carpeta = _carpeta(corpus)
    try:
        import numpy as np

        meta = json.loads((carpeta / 'vectores_meta.json').read_text(encoding='utf-8'))
        matriz = np.load(carpeta / 'vectores.npy', allow_pickle=False)
    except (ImportError, OSError, ValueError, EOFError):
        return None, {}
    claves = meta.get('claves') if isinstance(meta, dict) else None
    if (not isinstance(claves, list) or meta.get('modelo') != MODELO_EMBEDDINGS
            or meta.get('prefijo') != PREFIJO_DOCUMENTO or matriz.ndim != 2 or matriz.shape[0] != len(claves)):
        return None, {}
    return matriz, {c: i for i, c in enumerate(claves)}


def _guardar_vectores(por_clave: dict[str, Any], corpus: str = CORPUS_047) -> None:
    """float32 en ``.npy``: miles de trozos en JSON ocupan cientos de MB al cargarlos, en un equipo de 16 GB."""
    import numpy as np

    claves = list(por_clave)
    matriz = np.asarray([por_clave[c] for c in claves], dtype=np.float32)

    def npy(temporal: Path) -> None:
        with temporal.open('wb') as f:
            np.save(f, matriz, allow_pickle=False)

    def meta(temporal: Path) -> None:
        temporal.write_text(json.dumps({'modelo': MODELO_EMBEDDINGS, 'prefijo': PREFIJO_DOCUMENTO,
                                        'claves': claves}), encoding='utf-8')

    _escribir(_carpeta(corpus) / 'vectores.npy', npy)
    _escribir(_carpeta(corpus) / 'vectores_meta.json', meta)


def _con_vectores(frags: list[Fragmento], corpus: str = CORPUS_047) -> Indice:
    matriz, fila_de = _leer_vectores(corpus)
    if matriz is None:
        return Indice(frags, corpus=corpus)
    pares = [(i, fila_de[c]) for i, c in enumerate(_clave(f.texto) for f in frags) if c in fila_de]
    if not pares:
        return Indice(frags, corpus=corpus)
    return Indice(frags, matriz[[fila for _, fila in pares]], [i for i, _ in pares], corpus=corpus)


def _fragmentos_con_cache(repo: Path, corpus: str, carpeta: Path) -> list[Fragmento]:
    """El corpus ampliado solo vuelve a partir los ficheros que cambiaron (077:RF-12)."""
    def guardar(ruta: Path, texto: str) -> None:
        _escribir(ruta, lambda temporal: temporal.write_text(texto, encoding='utf-8'))

    trozos, _ = corpus_proyecto.con_cache(_ficheros_de(repo, corpus), repo, carpeta,
                                          lambda p, rel: _trozos_segun(p, rel, corpus), guardar)
    return _con_vigencia(repo, trozos)


def construir(repo: Path, corpus: str = CORPUS_047) -> Indice:
    """El índice desde los ficheros, con los vectores ya calculados de los trozos que no cambiaron."""
    carpeta = _carpeta(corpus)
    carpeta.mkdir(parents=True, exist_ok=True)
    frags = fragmentos(repo) if corpus == CORPUS_047 else _fragmentos_con_cache(repo, corpus, carpeta)
    (carpeta / 'fragmentos.json').write_text(json.dumps([asdict(f) for f in frags], ensure_ascii=False),
                                             encoding='utf-8')
    (carpeta / 'huella.txt').write_text(huella(repo, corpus), encoding='utf-8')
    return _con_vectores(frags, corpus)


def cargar_o_construir(repo: Path, corpus: str = CORPUS_047) -> Indice:
    """El índice guardado si el código no cambió; si cambió, se reconstruye (RF-17)."""
    carpeta = _carpeta(corpus)
    guardada = carpeta / 'huella.txt'
    if guardada.is_file() and guardada.read_text(encoding='utf-8') == huella(repo, corpus):
        frags = [Fragmento(**f) for f in json.loads((carpeta / 'fragmentos.json').read_text(encoding='utf-8'))]
        return _con_vectores(frags, corpus)
    return construir(repo, corpus)


def vectores_pendientes(repo: Path, ollama: Any, corpus: str = CORPUS_047) -> bool:
    """¿Hay vectores por calcular y quién los calcule (047:RF-22)? No calcula ninguno."""
    modelos = ollama.modelos()
    if not modelos or not any(str(m).split(':')[0] == MODELO_EMBEDDINGS for m in modelos):
        return False
    return cargar_o_construir(repo, corpus).cobertura < 1.0


def calcular_vectores(repo: Path, ollama: Any, *, progreso: Callable[[int, int], None] | None = None,
                      cancelar: Callable[[], None] | None = None, ceder: Callable[[], bool] | None = None,
                      lote: int = 16, cada: int = 8, corpus: str = CORPUS_047) -> dict[str, Any]:
    """Los vectores que faltan, por lotes (047:RF-22). Guarda cada ``cada`` lotes y al salir por
    cualquier motivo (047:RF-24): cancelar, ceder el carril o caerse Ollama no pierde lo hecho."""
    frags = cargar_o_construir(repo, corpus).frags
    try:
        import numpy  # noqa: F401
    except ImportError:
        return {'estado': 'sin_numpy', 'con_vector': 0, 'total': len(frags)}
    claves = [_clave(f.texto) for f in frags]
    vigentes = set(claves)
    por_clave: dict[str, Any] = {}
    # 077:RF-13: los trozos que el corpus ampliado comparte con la 047 no se vuelven a calcular.
    for origen in dict.fromkeys((CORPUS_047, corpus)):
        matriz, fila_de = _leer_vectores(origen)
        if matriz is not None:
            por_clave.update({c: matriz[i] for c, i in fila_de.items() if c in vigentes})
    faltan = list({c: f.texto for c, f in zip(claves, frags, strict=True) if c not in por_clave}.items())
    estado, hechos, nuevos = 'completo', 0, False
    try:
        if cancelar:
            cancelar()
        for n, i in enumerate(range(0, len(faltan), lote), 1):
            if ceder and ceder():
                estado = 'cedido'
                break
            parte = faltan[i:i + lote]
            emb = ollama.embeddings([PREFIJO_DOCUMENTO + t[:_LARGO_EMBEDDING] for _, t in parte])
            if not emb or len(emb) != len(parte):
                estado = 'fallo'
                break
            por_clave.update({c: v for (c, _), v in zip(parte, emb, strict=True)})
            hechos += len(parte)
            nuevos = True
            if progreso:
                progreso(hechos, len(faltan))
            if cancelar:
                cancelar()
            if n % cada == 0:
                _guardar_vectores(por_clave, corpus)
                nuevos = False
    finally:
        if nuevos:
            _guardar_vectores(por_clave, corpus)
    return {'estado': estado, 'con_vector': sum(c in por_clave for c in claves), 'total': len(frags)}


def _terminos(texto: str) -> set[str]:
    return {w for w in re.findall(r'\w{4,}', normalizar(texto)) if w not in _VACIAS}


def citas_que_no_apoyan(redactada: str, citas: Sequence[dict]) -> list[str]:
    """Cada cita de la respuesta que no existe o no comparte ningún término con la frase que la
    lleva (027:RF-41): un modelo pequeño citaba [5] tras una frase que no salía de ese trozo."""
    por_n = {c['n']: c for c in citas}
    problemas = []
    for frase in re.split(r'(?<=[.!?;])\s+', redactada or ''):
        for n in map(int, re.findall(r'\[(\d+)\]', frase)):
            cita = por_n.get(n)
            if cita is None:
                problemas.append(f'[{n}] no está entre los trozos hallados')
            elif not _terminos(re.sub(r'\[\d+\]', '', frase)) & _terminos(cita['texto']):
                problemas.append(f'[{n}] no apoya «{frase.strip()[:80]}»')
    return problemas


def medir(indice: Indice, preguntas: Sequence[dict], ollama: Any = None) -> dict[str, Any]:
    """Las consultas medidas con preguntas reales del operador (027:RF-42): ``{'pregunta',
    'fuente'}``, con ``fuente`` el fichero que la responde o ``None`` si no hay respuesta en el
    proyecto. Da la fracción con una cita de la fuente esperada y la de «No lo sé» acertados."""
    con, sin = [p for p in preguntas if p.get('fuente')], [p for p in preguntas if not p.get('fuente')]
    aciertos_cita = 0
    for p in con:
        r = responder(indice, p['pregunta'], ollama)
        aciertos_cita += r['sabe'] and any(str(p['fuente']) in str(c['fuente']) for c in r['citas'])
    no_lo_se = sum(not responder(indice, p['pregunta'], ollama)['sabe'] for p in sin)
    return {'preguntas': len(preguntas),
            'con_cita_correcta': aciertos_cita / len(con) if con else None,
            'no_lo_se_acertados': no_lo_se / len(sin) if sin else None}


def recuperar(indice: Indice, consulta: str, k: int = 6, *, vector: Sequence[float] | None = None,
              reordenador: Callable[[str, Sequence[dict]], list[dict]] | None = None,
              repo: Path | None = None, abstencion: Abstencion | None = None) -> dict[str, Any]:
    """Los trozos, si alguno responde, y con qué métodos: la misma vía para responder y para medir (047:RF-4).

    ``abstencion=None`` conserva los umbrales históricos, con los que se midió el conjunto de 76; la
    web siempre pasa la calibrada (047:RF-31 a RF-33)."""
    candidatos = indice.buscar(consulta, CANDIDATOS, vector)
    metodos, avisos = ['bm25'], []
    if indice.cosenos(vector) is not None:
        metodos.append('vectores')
        if indice.cobertura < 1.0:
            avisos.append(f'vectores de {indice.con_vector} de {len(indice.frags)} trozos')
    if repo is not None:
        candidatos = verificables(repo, candidatos, indice.corpus)      # 047:RF-29
    historico = bool(candidatos) and (max(c['bm25'] for c in candidatos) >= UMBRAL_BM25
                                      or max(c['coseno'] for c in candidatos) >= UMBRAL_COSENO)
    etiqueta = None
    if reordenador is not None and candidatos and (abstencion is not None or historico):
        try:
            candidatos = indice.primero_los_codigos(consulta, reordenador(consulta, candidatos))  # 047:RF-28
            etiqueta = getattr(reordenador, 'etiqueta', 'reranker')
            metodos.append(etiqueta)
        except RerankerNoDisponible as exc:                             # 047:RF-30
            avisos.append(f'reranker apartado: {exc}')
    if abstencion is None:
        sabe, senal = historico, 'historico'
    else:
        sabe, senal = abstencion.decide(candidatos, etiqueta=etiqueta, con_vectores='vectores' in metodos,
                                        con_codigo=indice.nombra_codigo(consulta, candidatos))
        if senal == 'sin_calibrar':
            avisos.append('abstención sin calibrar para este método')   # 047:RF-33
    # 077:RF-9: al final de todo, también tras los códigos: lo histórico nunca adelanta a lo vigente.
    ordenados = ([c for c in candidatos if c.get('vigencia') != 'historico']
                 + [c for c in candidatos if c.get('vigencia') == 'historico'])
    return {'hallados': ordenados[:k], 'sabe': sabe, 'metodos': metodos, 'avisos': avisos, 'senal': senal}


def _nombre_metodo(m: str) -> str:
    return {'bm25': 'BM25', 'vectores': f'vectores ({MODELO_EMBEDDINGS})', 'lectura': 'lectura directa'}.get(m, m)


def _recuperacion(metodos: Sequence[str], avisos: Sequence[str], motivo_sin_vectores: str | None) -> str:
    """La línea que ve el operador (047:RF-26): qué se usó y qué faltó."""
    notas = ([f'sin vectores: {motivo_sin_vectores}'] if motivo_sin_vectores else []) + list(avisos)
    return ('Recuperación: ' + ' + '.join(_nombre_metodo(m) for m in metodos)
            + (f" ({'; '.join(notas)})" if notas else '') + '.')


def _marca(h: dict) -> str:
    """Cómo se presenta un trozo que no es lo vigente y cumplido (077:RF-8, RF-10); vacío si lo es."""
    if h.get('vigencia') == 'historico':
        return 'histórico, no vigente'
    estado = h.get('estado_spec')
    return f'spec {estado}, no cumplida' if estado and estado != 'cumplida' else ''


def _con_marca(c: dict, texto: str) -> str:
    return f"({c['marca']}) {texto}" if c.get('marca') else texto


def _cita_de_lectura(salida: dict) -> dict | None:
    """Lo leído como cita: su fuente es el fichero que se acaba de abrir, así que ya está comprobada."""
    if salida['herramienta'] == 'leer_fichero':
        texto = salida['texto']
    elif salida['herramienta'] == 'consultar_api':
        if not salida.get('existe'):
            return None
        texto = f"API {salida['ruta']}: {json.dumps(salida['operaciones'], ensure_ascii=False, sort_keys=True)}"
    else:
        if not salida['coincidencias']:
            return None
        texto = '\n'.join(f"{c['fuente']}: {c['texto']}" for c in salida['coincidencias'])
        salida = {**salida, 'fuente': salida['coincidencias'][0]['fuente'], 'vigencia': 'vigente', 'estado_spec': None}
    texto = texto[:_LARGO_LECTURA]
    if not texto.strip():
        return None
    cita = {'fuente': salida['fuente'], 'texto': texto, 'verificada': True, 'origen': 'lectura',
            'vigencia': salida['vigencia'], 'estado_spec': salida['estado_spec'],
            'sha256': hashlib.sha256(texto.encode('utf-8')).hexdigest()}
    return {**cita, 'marca': _marca(cita)}


def _leer_nombradas(lector: Any, pregunta: str) -> tuple[list[dict], list[str]]:
    """Lo que la propia pregunta nombra (077:RF-26), y lo que nombra y no se puede leer (RF-27)."""
    plan = lectura_proyecto.nombradas_en(lector.repo, pregunta)
    citas, rechazadas = [], list(plan['rechazadas'])
    for nombre, argumentos in plan['pedidas']:
        try:
            cita = _cita_de_lectura(lector.ejecutar(nombre, argumentos))
        except (ValueError, OSError):
            rechazadas.append(str(argumentos.get('ruta')))
            continue
        if cita is not None:
            citas.append(cita)
    return citas, rechazadas


def _lecturas_del_llm(lector: Any, ollama: Any, pregunta: str, citas: Sequence[dict]) -> tuple[list[dict], int]:
    """Lo que el LLM pide leer, cuando ya hay respuesta (077:RF-28, RF-32); lo que no vale se descarta (RF-29)."""
    pedir = getattr(ollama, 'pedir_lecturas', None)
    if lector is None or pedir is None:
        return [], 0
    pedidas = pedir(pregunta, [_con_marca(c, c['texto']) for c in citas], lectura_proyecto.catalogo(),
                    lectura_proyecto.MAX_LECTURAS_LLM) or []
    nuevas, descartadas = [], 0
    for pedida in pedidas[:lectura_proyecto.MAX_LECTURAS_LLM]:
        try:
            cita = _cita_de_lectura(lector.ejecutar(pedida.get('herramienta'), pedida.get('argumentos')))
        except (ValueError, OSError, AttributeError, TypeError):
            descartadas += 1
            continue
        if cita is None:
            descartadas += 1
        elif all(cita['sha256'] != c['sha256'] for c in citas):
            nuevas.append(cita)
    return nuevas, descartadas


def responder(indice: Indice, pregunta: str, ollama: Any = None, k: int = 6, *, repo: Path | None = None,
              reordenador: Callable[[str, Sequence[dict]], list[dict]] | None = None,
              usar_vectores: bool = True, abstencion: Abstencion | None = None, lector: Any = None) -> dict[str, Any]:
    """La respuesta con sus citas y sus métodos; si ningún trozo responde, «No lo sé» (RF-18).

    Con ``repo``, cada cita se comprueba contra su fichero (047:RF-3, RF-29). Solo pide el vector
    de la consulta, nunca los del corpus (047:RF-23). Con ``lector`` (una ``LecturaGobernada``), lo que la
    pregunta nombra se lee y el LLM puede pedir más lecturas si el índice ya respondió (077:RF-26, RF-28)."""
    vector, motivo = None, None
    if not usar_vectores:
        motivo = 'la evaluación sellada no los adoptó'
    elif indice.con_vector == 0:
        motivo = 'el índice aún no los tiene' if ollama is not None else 'Ollama no responde'
    elif ollama is None:
        motivo = 'Ollama no responde'
    else:
        emb = ollama.embeddings([PREFIJO_CONSULTA + pregunta])
        vector = emb[0] if emb else None
        if indice.cosenos(vector) is None:
            vector, motivo = None, 'Ollama no dio un vector válido de la consulta'
    r = recuperar(indice, pregunta, k, vector=vector, reordenador=reordenador, repo=repo, abstencion=abstencion)
    hallados = r['hallados'] if r['sabe'] else []
    leidas, rechazadas = _leer_nombradas(lector, pregunta) if lector is not None else ([], [])
    nota = (f" No se lee {', '.join(rechazadas)}: queda fuera de lo que el asistente puede consultar." if rechazadas else '')
    metodos = [*r['metodos'], 'lectura'] if leidas else r['metodos']
    avisos = list(r['avisos'])
    base = {'metodos': metodos, 'recuperacion': _recuperacion(metodos, avisos, motivo)}
    if rechazadas:
        base['rechazadas'] = rechazadas
    if not hallados and not leidas:
        return {'respuesta': 'No lo sé: nada del código, las specs ni el manual responde a eso.' + nota, 'citas': [],
                'sabe': False, **base}
    citas = leidas + [{'fuente': h['fuente'], 'texto': h['texto'], 'verificada': repo is not None,
                       'vigencia': h.get('vigencia', 'vigente'), 'estado_spec': h.get('estado_spec'), 'marca': _marca(h),
                       'sha256': hashlib.sha256(h['texto'].encode('utf-8')).hexdigest()} for h in hallados]
    if hallados and ollama is not None:                                 # 077:RF-32: nunca convierte un «No lo sé»
        pedidas, descartadas = _lecturas_del_llm(lector, ollama, pregunta, citas)
        citas += pedidas
        if pedidas and 'lectura' not in metodos:
            metodos = [*metodos, 'lectura']
        if descartadas:
            avisos.append(f'{descartadas} lectura(s) pedidas por el modelo, descartadas')
        base.update(metodos=metodos, recuperacion=_recuperacion(metodos, avisos, motivo))
    citas = [{'n': i + 1, **c} for i, c in enumerate(citas)]
    if all(c.get('vigencia') == 'historico' for c in citas):
        base['recuperacion'] += ' Solo hay documentos históricos: no es lo vigente.'     # 077:RF-8
    redactada = ollama.responder(pregunta, [_con_marca(c, c['texto']) for c in citas]) if ollama is not None else None
    # Con cita y con texto: llama3.1:8b respondió solo «[5]» a «¿cómo se calibra una barra sin
    # medidor?» (2026-10-24); sin 40 letras de explicación vale más dar los trozos citados.
    explicacion = re.sub(r'\[\d+\]', '', redactada or '')
    if redactada and 'no lo sé' not in redactada.lower() and re.search(r'\[\d+\]', redactada) \
            and len(re.findall(r'\w', explicacion)) >= 40:
        problemas = citas_que_no_apoyan(redactada, citas)                  # 027:RF-41
        if not problemas:
            marcas = list(dict.fromkeys(c['marca'] for c in citas if c.get('marca')))
            aviso_marcas = f" Citas con reservas: {'; '.join(marcas)}." if marcas else ''   # 077:RF-8, RF-10
            return {'respuesta': redactada + aviso_marcas + nota, 'citas': citas, 'sabe': True,
                    'redactada_por': ollama.modelo, **base}
    else:
        problemas = []
    resumen = ' '.join(f'[{c["n"]}] {_con_marca(c, c["texto"][:300])}' for c in citas[:3]) + nota
    return {'respuesta': resumen, 'citas': citas, 'sabe': True, 'redactada_por': None,
            **({'citas_sin_apoyo': problemas} if problemas else {}), **base}
