"""Índice local del proyecto para responder cómo funciona el conversor (spec 026, RF-17, RF-18).

Trozos de ``CODIGO_FUENTE.md`` (cada fichero con su spec), de las specs (cada RF), de los
docstrings de ``src/`` y ``tools/`` (cada módulo, función y clase), del manual de órdenes y
de la constitución. Se busca por palabras (BM25, sin dependencias) y, si el modelo de
embeddings local está instalado, también por significado; la respuesta cita de dónde sale
cada cosa y, si nada responde, dice que no lo sabe.

Se reconstruye cuando cambia algún fichero (huella de fechas y tamaños): el índice nunca
habla de un código que ya no existe.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import almacen
from .sinteticos import normalizar

_VACIAS = {
    'de', 'la', 'el', 'en', 'y', 'a', 'los', 'las', 'del', 'que', 'se', 'un', 'una', 'por',
    'con', 'para', 'es', 'al', 'lo', 'como', 'su', 'sus', 'o', 'no', 'si', 'cada', 'sin',
    'hay', 'mas', 'más', 'este', 'esta', 'esto', 'ese', 'esa',
}
#: Por debajo de esta puntuación BM25 ningún trozo responde la pregunta.
UMBRAL_BM25 = 2.0
UMBRAL_COSENO = 0.55


@dataclass
class Fragmento:
    id: int
    fuente: str
    texto: str


def palabras(texto: str) -> list[str]:
    return [p for p in re.findall(r'[a-z0-9_]+', normalizar(texto)) if len(p) > 2 and p not in _VACIAS]


def _ficheros(repo: Path) -> list[Path]:
    out = [repo / 'CODIGO_FUENTE.md', repo / 'docs' / 'MANUAL_COMANDOS.md', repo / 'docs' / 'constitution.md']
    out += sorted((repo / 'specs').glob('*/spec.md'))
    out += sorted((repo / 'src').rglob('*.py')) + sorted((repo / 'tools').glob('*.py'))
    return [p for p in out if p.is_file()]


def huella(repo: Path) -> str:
    h = hashlib.sha256()
    for p in _ficheros(repo):
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


def fragmentos(repo: Path) -> list[Fragmento]:
    """Los trozos del proyecto, cada uno con su fuente ``fichero:línea``."""
    trozos: list[tuple[str, str]] = []
    for p in _ficheros(repo):
        rel = p.relative_to(repo).as_posix()
        texto = p.read_text(encoding='utf-8', errors='replace')
        if p.suffix == '.py':
            trozos += _de_python(rel, texto)
        elif rel == 'CODIGO_FUENTE.md':
            for i, linea in enumerate(texto.splitlines(), 1):
                m = re.match(r'^\| `([^`]+)` \| (.+) \| (.+) \|$', linea)
                if m:
                    trozos.append((f'{rel}:{i}', f'{m.group(1)}: {m.group(2)} (spec {m.group(3)})'))
        elif rel.startswith('specs/'):
            trozos += _de_spec(rel, p.parent.name, texto)
        else:
            trozos += _de_markdown(rel, texto)
    return [Fragmento(i, f, t) for i, (f, t) in enumerate(trozos)]


class Indice:
    def __init__(self, frags: Sequence[Fragmento], vectores: list[list[float]] | None = None):
        self.frags = list(frags)
        self.tokens = [palabras(f.texto) for f in self.frags]
        self.df = Counter(t for toks in self.tokens for t in set(toks))
        self.largo_medio = sum(len(t) for t in self.tokens) / max(len(self.tokens), 1)
        self.vectores = vectores

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

    def buscar(self, consulta: str, k: int = 6, vector: list[float] | None = None) -> list[dict[str, Any]]:
        """Los ``k`` trozos que mejor responden, por palabras y, si hay vectores, por significado."""
        lexico = self.bm25(consulta)
        semantico = [0.0] * len(self.frags)
        con_vectores = vector is not None and bool(self.vectores)
        if con_vectores:
            nq = math.sqrt(sum(x * x for x in vector)) or 1.0
            for i, v in enumerate(self.vectores):
                nv = math.sqrt(sum(x * x for x in v)) or 1.0
                semantico[i] = sum(a * c for a, c in zip(vector, v, strict=False)) / (nq * nv)
        tope = max(lexico, default=0.0) or 1.0
        puntos = [0.5 * (lx / tope) + 0.5 * sm if con_vectores else lx
                  for lx, sm in zip(lexico, semantico, strict=True)]
        orden = sorted(range(len(self.frags)), key=lambda i: -puntos[i])[:k]
        return [{'fuente': self.frags[i].fuente, 'texto': self.frags[i].texto, 'bm25': lexico[i],
                 'coseno': semantico[i], 'puntos': puntos[i]} for i in orden]


def _carpeta() -> Path:
    return almacen.raiz() / 'indice'


def _clave(texto: str) -> str:
    return hashlib.sha1(texto.encode('utf-8')).hexdigest()


def construir(repo: Path, ollama: Any = None) -> Indice:
    """El índice desde los ficheros, con embeddings si el modelo local los da (reutiliza los
    de los trozos que no cambiaron)."""
    frags = fragmentos(repo)
    carpeta = _carpeta()
    carpeta.mkdir(parents=True, exist_ok=True)
    previos: dict[str, list[float]] = {}
    if (carpeta / 'vectores.json').is_file():
        try:
            previos = json.loads((carpeta / 'vectores.json').read_text(encoding='utf-8'))
        except ValueError:
            previos = {}
    vectores = None
    if ollama is not None:
        claves = [_clave(f.texto) for f in frags]
        faltan = [i for i, c in enumerate(claves) if c not in previos]
        for i in range(0, len(faltan), 64):
            lote = faltan[i:i + 64]
            emb = ollama.embeddings([frags[j].texto[:2000] for j in lote])
            if not emb or len(emb) != len(lote):
                break
            previos.update({claves[j]: v for j, v in zip(lote, emb, strict=True)})
        if all(c in previos for c in claves):
            vectores = [previos[c] for c in claves]
            (carpeta / 'vectores.json').write_text(json.dumps({c: previos[c] for c in claves}), encoding='utf-8')
    (carpeta / 'fragmentos.json').write_text(json.dumps([asdict(f) for f in frags], ensure_ascii=False),
                                             encoding='utf-8')
    (carpeta / 'huella.txt').write_text(huella(repo), encoding='utf-8')
    return Indice(frags, vectores)


def cargar_o_construir(repo: Path, ollama: Any = None) -> Indice:
    """El índice guardado si el código no cambió; si cambió, se reconstruye (RF-17)."""
    carpeta = _carpeta()
    guardada = carpeta / 'huella.txt'
    if guardada.is_file() and guardada.read_text(encoding='utf-8') == huella(repo):
        frags = [Fragmento(**f) for f in json.loads((carpeta / 'fragmentos.json').read_text(encoding='utf-8'))]
        vectores = None
        if (carpeta / 'vectores.json').is_file():
            guardados = json.loads((carpeta / 'vectores.json').read_text(encoding='utf-8'))
            claves = [_clave(f.texto) for f in frags]
            if all(c in guardados for c in claves):
                vectores = [guardados[c] for c in claves]
        return Indice(frags, vectores)
    return construir(repo, ollama)


def responder(indice: Indice, pregunta: str, ollama: Any = None, k: int = 6) -> dict[str, Any]:
    """La respuesta con sus citas; si ningún trozo responde, «No lo sé» (RF-18)."""
    vector = None
    if ollama is not None and indice.vectores:
        emb = ollama.embeddings([pregunta])
        vector = emb[0] if emb else None
    hallados = indice.buscar(pregunta, k, vector)
    sabe = bool(hallados) and (hallados[0]['bm25'] >= UMBRAL_BM25 or hallados[0]['coseno'] >= UMBRAL_COSENO)
    if not sabe:
        return {'respuesta': 'No lo sé: nada del código, las specs ni el manual responde a eso.', 'citas': [],
                'sabe': False}
    citas = [{'n': i + 1, 'fuente': h['fuente'], 'texto': h['texto']} for i, h in enumerate(hallados)]
    redactada = ollama.responder(pregunta, [c['texto'] for c in citas]) if ollama is not None else None
    # Con cita y con texto: llama3.1:8b respondió solo «[5]» a «¿cómo se calibra una barra sin
    # medidor?» (2026-10-24); sin 40 letras de explicación vale más dar los trozos citados.
    explicacion = re.sub(r'\[\d+\]', '', redactada or '')
    if redactada and 'no lo sé' not in redactada.lower() and re.search(r'\[\d+\]', redactada) \
            and len(re.findall(r'\w', explicacion)) >= 40:
        return {'respuesta': redactada, 'citas': citas, 'sabe': True, 'redactada_por': ollama.modelo}
    resumen = ' '.join(f'[{c["n"]}] {c["texto"][:300]}' for c in citas[:3])
    return {'respuesta': resumen, 'citas': citas, 'sabe': True, 'redactada_por': None}
