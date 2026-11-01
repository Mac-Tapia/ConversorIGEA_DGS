"""Destilación del modelo local de Ollama (maestro) al Transformer de órdenes (alumno).

Spec 027, RF-56 a RF-62. El usuario, el 2026-10-28: «no te olvides de verificar e implementar
la técnica y metodología de destilación para el entrenamiento de LLM». El Transformer se
entrenaba sobre todo con órdenes sintéticas (5 reales); las órdenes que el operador escribe y
no confirma no enseñaban nada. El maestro las interpreta k veces con temperatura y la
proporción de votos por tarea es su distribución blanda (autoconsistencia; destilación de
secuencia como en Hsieh et al., 2023, y Xu et al., 2024): el alumno aprende de ella con
α·CE + (1 − α)·T²·KL, y solo se usa si no acierta menos que sin destilar (RF-60).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from . import almacen
from .sinteticos import normalizar
from .tareas import TAREAS


@dataclass
class Destilacion:
    """Configuración de la destilación (RF-56 a RF-58, RF-62)."""

    k: int = 5
    """Interpretaciones del maestro por orden."""
    temperatura_maestro: float = 0.7
    acuerdo_min: float = 0.6
    """Fracción mínima de votos de la tarea más votada (RF-57)."""
    alfa: float = 0.5
    """Peso de la entropía cruzada con la etiqueta; 1 − α, el de la KL con el maestro."""
    T: float = 2.0
    """Temperatura del alumno en la KL (RF-58)."""
    maximo: int = 400
    """Órdenes sin etiqueta que se le piden al maestro como mucho."""


@dataclass
class EjemploBlando:
    """Una orden con la distribución del maestro y los datos que marcó en el texto."""

    texto: str
    distribucion: dict[str, float]
    datos: list[tuple[int, int, str]] = field(default_factory=list)
    acuerdo: float = 0.0

    @property
    def tarea(self) -> str:
        return max(self.distribucion, key=self.distribucion.get)


class Maestro(Protocol):
    modelo: str

    def interpretar(self, texto: str, *, temperatura: float = 0.0, semilla: int = 0) -> dict | None: ...


def sin_etiqueta(excluir: Iterable[str] = ()) -> list[str]:
    """Las órdenes del registro que el operador no confirmó ni corrigió (RF-59), sin las de
    ``excluir`` (la prueba fija), sin repetir y en el orden en que llegaron."""
    vistos = {normalizar(t) for t in excluir}
    vistos |= {normalizar(f.get('texto') or '') for f in almacen.leer('ejemplos')}
    out = []
    for f in almacen.leer('ordenes'):
        t = (f.get('texto') or '').strip()
        n = normalizar(t)
        if t and n not in vistos:
            vistos.add(n)
            out.append(t)
    return out


def _spans(texto: str, datos: dict[str, list[dict]]) -> list[tuple[int, int, str]]:
    """Los datos del maestro que aparecen tal cual en el texto, como trozos (sin solaparse)."""
    out: list[tuple[int, int, str]] = []
    bajo = texto.lower()
    for tipo, valores in (datos or {}).items():
        for v in valores or []:
            valor = str(v.get('valor') if isinstance(v, dict) else v).strip().lower()
            if not valor:
                continue
            m = re.search(re.escape(valor), bajo)
            if m and not any(a < m.end() and m.start() < b for a, b, _ in out):
                out.append((m.start(), m.end(), tipo))
    return sorted(out)


def etiquetar(textos: Sequence[str], maestro: Maestro, cfg: Destilacion | None = None
              ) -> dict[str, Any]:
    """Los votos del maestro por orden (RF-56) y el filtro por acuerdo (RF-57).

    Devuelve ``{'blandos', 'descartados', 'respondio'}``; ``respondio`` es falso si el maestro
    no dio ninguna respuesta (RF-61).
    """
    cfg = cfg or Destilacion()
    blandos, descartados, alguna = [], [], False
    for texto in list(textos)[:cfg.maximo]:
        votos: Counter = Counter()
        por_tarea: dict[str, dict] = {}
        for s in range(cfg.k):
            r = maestro.interpretar(texto, temperatura=cfg.temperatura_maestro, semilla=s)
            if r is None:
                continue
            alguna = True
            if r.get('tarea') in TAREAS:
                votos[r['tarea']] += 1
                por_tarea.setdefault(r['tarea'], r.get('datos') or {})
        total = sum(votos.values())
        if not total:
            descartados.append({'texto': texto, 'motivo': 'el maestro no dio una tarea'})
            continue
        tarea, n = votos.most_common(1)[0]
        acuerdo = n / cfg.k
        if acuerdo < cfg.acuerdo_min:
            descartados.append({'texto': texto, 'motivo': f'acuerdo {acuerdo:.2f} bajo {cfg.acuerdo_min}'})
            continue
        blandos.append(EjemploBlando(texto, {t: c / total for t, c in votos.items()},
                                     _spans(texto, por_tarea[tarea]), acuerdo))
    return {'blandos': blandos, 'descartados': descartados, 'respondio': alguna}


def registro(cfg: Destilacion, maestro: Maestro | None, resultado: dict[str, Any] | None) -> dict[str, Any]:
    """Lo que se guarda con el modelo (RF-62)."""
    return {**asdict(cfg), 'maestro': getattr(maestro, 'modelo', None),
            'etiquetadas': len((resultado or {}).get('blandos') or []),
            'descartadas': len((resultado or {}).get('descartados') or []),
            'respondio': bool((resultado or {}).get('respondio'))}


# ------------------------------------------------------------------ maestros (RF-56, RF-63, RF-64)
class MaestroArchivo:
    """Las etiquetas que dejó Claude en el registro ``etiquetas_maestro`` (RF-64): por orden, sus
    votos (una tarea por voto) y sus datos. Cada semilla toma el voto siguiente."""

    def __init__(self, filas: Iterable[Mapping[str, Any]] | None = None):
        filas = list(filas if filas is not None else almacen.leer('etiquetas_maestro'))
        self.por_texto = {normalizar(f['texto']): f for f in filas if f.get('texto')}
        self.modelo = next((str(f.get('maestro')) for f in filas if f.get('maestro')), 'claude')

    def interpretar(self, texto: str, *, temperatura: float = 0.0, semilla: int = 0, **_kw) -> dict | None:
        f = self.por_texto.get(normalizar(texto))
        if f is None or not f.get('votos'):
            return None
        votos = list(f['votos'])
        tarea = votos[semilla % len(votos)]
        datos = {tipo: [{'valor': v, 'confianza': 1.0} for v in (vs if isinstance(vs, list) else [vs])]
                 for tipo, vs in (f.get('datos') or {}).items()} if tarea == votos[0] else {}
        return {'tarea': tarea, 'confianza': f.get('confianza', 0.9), 'datos': datos, 'modelo': self.modelo}


def enmascarar(texto: str, vocab: Mapping[str, Sequence[str]]) -> tuple[str, dict[str, str]]:
    """El texto con cada nombre del vocabulario cambiado por un marcador (``<ALIMENTADORES1>``…) y
    la tabla para reponerlos (RF-63). Los nombres largos primero, sin distinguir mayúsculas."""
    tabla: dict[str, str] = {}
    nombres = sorted({(str(n), tipo) for tipo, ns in vocab.items() for n in ns if n and len(str(n)) >= 3},
                     key=lambda x: (-len(x[0]), x[0]))
    salida = texto
    for nombre, tipo in nombres:
        patron = re.compile(re.escape(nombre), re.I)
        if patron.search(salida):
            previas = sum(1 for k in tabla if k.startswith('<' + tipo.upper()))
            marca = f'<{tipo.upper()}{previas + 1}>'
            tabla[marca] = nombre
            salida = patron.sub(marca, salida)
    return salida, tabla


def reponer(valor: str, tabla: Mapping[str, str]) -> str:
    for marca, nombre in tabla.items():
        valor = valor.replace(marca, nombre)
    return valor


class MaestroCodex:
    """Codex por su CLI (``codex exec``) como maestro (RF-56, RF-63): la orden sale enmascarada, la
    respuesta es un JSON con la tarea y los datos, y cada envío queda anotado."""

    def __init__(self, vocab: Mapping[str, Sequence[str]], *, modelo: str | None = None,
                 tiempo_max_s: float = 180.0, ejecutar=None):
        self.vocab, self.tiempo_max_s = vocab, tiempo_max_s
        self.modelo = f"codex:{modelo or 'predeterminado'}"
        self._modelo_cli = modelo
        self._ejecutar = ejecutar or self._codex

    def _codex(self, prompt: str) -> str | None:
        import shutil
        import subprocess
        import tempfile

        exe = shutil.which('codex')
        if exe is None:
            return None
        with tempfile.TemporaryDirectory() as d:
            salida = Path(d) / 'respuesta.txt'
            cmd = [exe, 'exec', '--skip-git-repo-check', '-s', 'read-only', '-o', str(salida)]
            if self._modelo_cli:
                cmd += ['-m', self._modelo_cli]
            try:
                subprocess.run(cmd + ['-'], input=prompt, text=True, encoding='utf-8', cwd=d,
                               capture_output=True, timeout=self.tiempo_max_s, check=False)
            except (OSError, subprocess.SubprocessError):
                return None
            return salida.read_text(encoding='utf-8') if salida.is_file() else None

    def interpretar(self, texto: str, *, temperatura: float = 0.0, semilla: int = 0, **_kw) -> dict | None:
        from .tareas import descripcion_para_modelo

        oculto, tabla = enmascarar(texto, self.vocab)
        almacen.anotar('internet', {'destino': 'codex', 'consulta': oculto,
                                    'motivo': 'maestro de destilación (027:RF-63)'})
        prompt = ('Eres el maestro que etiqueta órdenes de un operador de redes eléctricas. Responde SOLO un '
                  'JSON {"tarea": <nombre>, "datos": {<nombre del dato>: <valor o lista>}} con una tarea de '
                  'esta lista: ' + json.dumps(descripcion_para_modelo(), ensure_ascii=False)
                  + f'\nVariante {semilla}: piensa la orden de nuevo antes de decidir.\nOrden: {oculto}')
        bruto = self._ejecutar(prompt)
        m = re.search(r'\{.*\}', bruto or '', re.S)
        if not m:
            return None
        try:
            r = json.loads(m.group(0))
        except ValueError:
            return None
        datos = {}
        for nombre, valor in (r.get('datos') or {}).items():
            valores = valor if isinstance(valor, list) else [valor]
            datos[nombre] = [{'valor': reponer(str(v), tabla), 'confianza': 0.8} for v in valores if v not in (None, '')]
        return {'tarea': r.get('tarea'), 'confianza': 0.8, 'datos': datos, 'modelo': self.modelo}
