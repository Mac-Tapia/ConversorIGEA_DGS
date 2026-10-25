"""Mejoras del conversor que propone el agente, en una rama que el operador revisa
(spec 026, RF-26 a RF-28, RF-32).

Una propuesta de código lleva su cambio de spec y sus pruebas (P12); una de librería, su
ficha con licencia, mantenimiento y motivo. Se prepara en un ``git worktree`` aparte, no
en la copia de trabajo: el 2026-10-24 otra sesión trabajaba en el mismo repositorio y una
rama del agente no puede mezclarse con su trabajo. Allí se confirma el cambio y se corre la
suite. Nunca se fusiona ni se sube: esas órdenes de git ni siquiera se pueden pedir.

Cada propuesta y cada decisión del operador queda en ``mejoras.jsonl`` (RF-28).
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import almacen

PROHIBIDAS = {'merge', 'push', 'rebase', 'pull', 'reset', 'checkout'}


@dataclass
class Propuesta:
    titulo: str
    motivo: str
    tipo: str                                   # 'codigo' | 'libreria'
    cambios: dict[str, str]                     # ruta relativa → contenido nuevo
    evidencia: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


class PropuestaInvalida(ValueError):
    """La propuesta no trae lo que la constitución exige."""


def validar(p: Propuesta) -> None:
    """Código con spec y pruebas (P12); librería con su ficha; nada fuera del repositorio."""
    rutas = list(p.cambios)
    if not rutas:
        raise PropuestaInvalida('la propuesta no cambia nada')
    for r in rutas:
        if Path(r).is_absolute() or '..' in Path(r).parts:
            raise PropuestaInvalida(f'{r}: fuera del repositorio')
    if p.tipo == 'codigo':
        if not any(r.startswith('specs/') for r in rutas):
            raise PropuestaInvalida('una mejora de código empieza por su spec (P12): falta el cambio en specs/')
        if not any(r.startswith('tests/') for r in rutas):
            raise PropuestaInvalida('una mejora de código trae sus pruebas: falta el cambio en tests/')
    elif p.tipo == 'libreria':
        if not any(r.startswith('docs/propuestas/') for r in rutas):
            raise PropuestaInvalida('una librería se propone con su ficha en docs/propuestas/')
    else:
        raise PropuestaInvalida(f'tipo desconocido: {p.tipo}')


def _git(repo: Path, *args: str) -> str:
    if args and args[0] in PROHIBIDAS:
        raise PermissionError(f'el asistente no ejecuta «git {args[0]}»: nunca fusiona ni sube (RF-27)')
    r = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=300, check=False)
    if r.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)}: {r.stderr.strip()[:500]}')
    return r.stdout


def preparar_rama(repo: Path, p: Propuesta, *, suite: Sequence[str] | None = ('-q', '-x', '-p', 'no:cacheprovider'),
                  limite_s: float = 3 * 3600, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """La rama ``asistente/<id>`` en su worktree, con el cambio confirmado y la suite corrida."""
    validar(p)
    rama = f'asistente/{p.id}'
    destino = almacen.raiz() / 'ramas' / p.id
    destino.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, 'worktree', 'add', '-b', rama, str(destino), 'HEAD')
    for rel, contenido in p.cambios.items():
        f = destino / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenido, encoding='utf-8')
    _git(destino, 'add', '--', *p.cambios)
    _git(destino, '-c', 'user.name=Asistente IGEA-DGS', '-c', 'user.email=asistente@localhost',
         'commit', '-q', '-m', f'{p.titulo}\n\n{p.motivo}\n\nPropuesta {p.id} del asistente (spec 026), sin fusionar.')
    commit = _git(destino, 'rev-parse', 'HEAD').strip()
    resultado: dict[str, Any] = {'codigo': None, 'resumen': 'sin suite'}
    if suite is not None:
        inicio = time.monotonic()
        try:
            r = subprocess.run([sys.executable, '-m', 'pytest', *suite], cwd=destino, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=limite_s,
                               env=dict(env) if env is not None else None, check=False)
            salida, codigo = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            salida, codigo = 'la suite superó el tiempo máximo', -1
        resumen = next((linea for linea in reversed(salida.splitlines())
                        if re.search(r'\d+ (passed|failed)|no tests ran', linea)), salida[-300:])
        resultado = {'codigo': codigo, 'resumen': resumen.strip('= '), 'segundos': round(time.monotonic() - inicio)}
    fila = {'id': p.id, 'evento': 'propuesta', 'titulo': p.titulo, 'motivo': p.motivo, 'tipo': p.tipo,
            'rama': rama, 'worktree': str(destino), 'commit': commit, 'ficheros': sorted(p.cambios),
            'suite': resultado, 'evidencia': p.evidencia}
    almacen.anotar('mejoras', fila)
    return fila


def registrar_decision(propuesta_id: str, decision: str, comentario: str = '') -> dict[str, Any]:
    """Lo que el operador decidió de una propuesta: aceptada, rechazada o modificada (RF-28)."""
    if decision not in ('aceptada', 'rechazada', 'modificada'):
        raise ValueError(f'decisión desconocida: {decision}')
    return almacen.anotar('mejoras', {'id': propuesta_id, 'evento': 'decision', 'decision': decision,
                                      'comentario': comentario})


def historial() -> list[dict[str, Any]]:
    """Cada propuesta con su última decisión, para auditar qué se propuso y qué se aceptó."""
    por_id: dict[str, dict] = {}
    for f in almacen.leer('mejoras'):
        if f.get('evento') == 'propuesta':
            por_id[f['id']] = {**f, 'decision': None}
        elif f.get('evento') == 'decision' and f['id'] in por_id:
            por_id[f['id']]['decision'] = f['decision']
            por_id[f['id']]['comentario'] = f.get('comentario', '')
    return list(por_id.values())


def propuesta_de_libreria(info: Mapping[str, Any], motivo: str) -> Propuesta:
    """La ficha de una librería (RF-32): licencia, mantenimiento y por qué mejora el conversor."""
    nombre = re.sub(r'[^\w.-]', '_', str(info.get('nombre') or 'libreria'))
    ficha = '\n'.join([
        f'# Propuesta de librería: {info.get("nombre")}', '',
        f'- Motivo: {motivo}',
        f'- Licencia: {info.get("licencia") or "sin declarar: no se puede usar sin revisarla"}',
        f'- Última versión: {info.get("version") or "?"} ({info.get("publicada") or "fecha desconocida"})',
        f'- Repositorio: {info.get("url") or "?"}',
        f'- Estrellas: {info.get("estrellas", "?")}', '',
        'No se instala: si se acepta, entra en una spec y en `requirements.txt` con sus pruebas (P8, P12).', ''])
    return Propuesta(f'Propuesta de librería {info.get("nombre")}', motivo, 'libreria',
                     {f'docs/propuestas/libreria-{nombre}.md': ficha}, evidencia=dict(info))
