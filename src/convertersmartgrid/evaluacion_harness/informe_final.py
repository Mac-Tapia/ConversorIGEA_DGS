"""Informe único de la evaluación final de una versión (044:RF-10, RF-11): ``docs/EVALUACION_FINAL_1.0.json``.

Cada bloque del plan de la evaluación final (intérprete, RAG, pronóstico, PINN, obras, razonamiento, roles, efectividad)
mide por su cuenta y deja sus medidas con la rev en que corrió y la huella de su conjunto sellado. Este consolidador las
reúne en un solo fichero, aplica Holm dentro de cada bloque (044:RF-12) y separa los resultados negativos, que se
publican igual que los positivos (044:RF-8). Se niega a escribir si algo no cuadra: una medida de otra rev, un árbol con
cambios sin commit o un conjunto que cambió después de sellarlo (044:RF-11). Sin eso, una cifra podía venir de un
modelo o de un conjunto distinto del que dice el informe, y la tesis la citaría igual.

Cada medida va como ``{"valor", "ic95": [inf, sup], "n", ...}`` bajo su nombre: es la forma de intervalo que ya lee
el recolector de la tesis (``intervalo_de``: ``valor`` más ``ic95``), y que no se toca desde aquí.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .estadistica import ajustar_holm

ESQUEMA = 'csg-evaluacion-final-v1'
#: Ruta del informe dentro del repositorio; es lo único que puede cambiar después de la rev medida.
DESTINO = 'docs/EVALUACION_FINAL_1.0.json'
_REV = re.compile(r'[0-9a-f]{40}')
_SHA = re.compile(r'[0-9a-f]{64}')
OBLIGATORIOS = ('valor', 'ic95', 'n', 'conjunto', 'negativo')


class InformeRechazado(ValueError):
    """La evaluación no corresponde a la revisión o a los conjuntos que declara (044:RF-11)."""


def huella_fichero(ruta: Path | str) -> str:
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8')
    if r.returncode:
        raise InformeRechazado(f'git {" ".join(args)} falló en {repo}: {r.stderr.strip()}')
    return r.stdout


def estado_git(repo: Path) -> tuple[str, list[str]]:
    """El HEAD y los ficheros con cambios (incluidos los no seguidos), sin contar el propio informe."""
    rev = _git(repo, 'rev-parse', 'HEAD').strip()
    sucios = []
    for linea in _git(repo, 'status', '--porcelain', '--untracked-files=all').splitlines():
        ruta = linea[3:].strip().strip('"').replace('\\', '/')
        if ruta != DESTINO:
            sucios.append(ruta)
    return rev, sucios


def _ruta_conjunto(repo: Path, ruta: str) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else repo / p


def _comprobar_conjuntos(conjuntos: dict, repo: Path, *, releer: bool = True) -> None:
    if not isinstance(conjuntos, dict) or not conjuntos:
        raise InformeRechazado('sin conjuntos declarados: cada medida dice sobre qué conjunto sellado se midió')
    for nombre, c in conjuntos.items():
        if not isinstance(c, dict) or not _SHA.fullmatch(str(c.get('sha256', ''))):
            raise InformeRechazado(f'el conjunto {nombre} no trae su huella SHA-256')
        if not releer:
            continue
        ruta = _ruta_conjunto(repo, str(c.get('ruta') or ''))
        if not c.get('ruta') or not ruta.is_file():
            raise InformeRechazado(f'el conjunto {nombre} no está en {ruta}')
        real = huella_fichero(ruta)
        if real != c['sha256']:
            raise InformeRechazado(f'la huella del conjunto {nombre} no cuadra: declarada {c["sha256"][:16]}…, '
                                   f'en disco {real[:16]}… ({ruta})')


def _finito(v: Any) -> bool:
    return type(v) in (int, float) and math.isfinite(v)


def _comprobar_medida(bloque: str, nombre: str, m: Any, conjuntos: dict) -> None:
    donde = f'{bloque}.{nombre}'
    if not isinstance(m, dict):
        raise InformeRechazado(f'{donde}: la medida no es un objeto')
    faltan = [k for k in OBLIGATORIOS if k not in m]
    if faltan:
        raise InformeRechazado(f'{donde}: faltan {", ".join(faltan)}')
    if not _finito(m['valor']):
        raise InformeRechazado(f'{donde}: valor no finito')
    if type(m['n']) is not int or m['n'] < 1:
        raise InformeRechazado(f'{donde}: n debe ser un entero positivo')
    ic = m['ic95']
    if not (isinstance(ic, list) and len(ic) == 2 and all(map(_finito, ic)) and ic[0] <= ic[1]):
        raise InformeRechazado(f'{donde}: ic95 debe ser [inf, sup] finitos con inf <= sup')
    if m['conjunto'] not in conjuntos:
        raise InformeRechazado(f'{donde}: el conjunto {m["conjunto"]} no está declarado')
    if type(m['negativo']) is not bool:
        raise InformeRechazado(f'{donde}: negativo debe decir true o false (044:RF-8)')
    if 'p' in m:
        if not (_finito(m['p']) and 0 <= m['p'] <= 1):
            raise InformeRechazado(f'{donde}: p fuera de [0, 1]')
        if not isinstance(m.get('prueba'), str) or not m['prueba']:
            raise InformeRechazado(f'{donde}: un p sin la prueba que lo dio')


def consolidar(entrada: dict, *, repo: Path | str, rev: str,
               git: Callable[[Path], tuple[str, list[str]]] = estado_git) -> dict:
    """044:RF-10, RF-11: el informe único, o ``InformeRechazado`` si la rev, el árbol, una huella o una medida no cuadran."""
    repo = Path(repo)
    if not _REV.fullmatch(str(rev or '')):
        raise InformeRechazado('rev debe ser el SHA-1 completo de la revisión candidata')
    cabeza, sucios = git(repo)
    if cabeza != rev:
        raise InformeRechazado(f'la rev {rev[:12]} no es el HEAD {cabeza[:12]} del repositorio')
    if entrada.get('rev') != rev:
        raise InformeRechazado(f'la entrada declara la rev {str(entrada.get("rev"))[:12]}, no {rev[:12]}')
    if sucios:
        raise InformeRechazado(f'el árbol no está limpio ({len(sucios)} cambios: {", ".join(sucios[:5])})')
    conjuntos = entrada.get('conjuntos') or {}
    _comprobar_conjuntos(conjuntos, repo)
    bloques = entrada.get('bloques')
    if not isinstance(bloques, dict) or not bloques:
        raise InformeRechazado('sin bloques medidos')
    medidas: dict[str, dict] = {}
    negativos = []
    for bloque, contenido in bloques.items():
        if not isinstance(contenido, dict) or contenido.get('rev') != rev:
            raise InformeRechazado(f'el bloque {bloque} se midió en la rev {str((contenido or {}).get("rev"))[:12]}, '
                                   f'no en {rev[:12]}')
        propias = contenido.get('medidas')
        if not isinstance(propias, dict) or not propias:
            raise InformeRechazado(f'el bloque {bloque} no trae medidas')
        for nombre, m in propias.items():
            _comprobar_medida(bloque, nombre, m, conjuntos)
        ajustadas = ajustar_holm({k: m['p'] for k, m in propias.items() if 'p' in m})
        medidas[bloque] = {k: {**m, 'p_holm': ajustadas.get(k)} for k, m in propias.items()}
        negativos += [{'bloque': bloque, 'metrica': k, 'hipotesis': m.get('hipotesis'), 'valor': m['valor'],
                       'ic95': m['ic95'], 'n': m['n'], 'p_holm': medidas[bloque][k]['p_holm']}
                      for k, m in propias.items() if m['negativo']]
    return {'esquema': ESQUEMA, 'rev': rev, 'arbol_limpio': True,
            'generado': datetime.now().isoformat(timespec='seconds'),
            'conjuntos': {k: {'sha256': c['sha256'], 'fichero': Path(str(c['ruta'])).name,
                              **({'n': c['n']} if type(c.get('n')) is int else {})} for k, c in conjuntos.items()},
            'correccion_multiple': 'holm_por_bloque', 'medidas': medidas, 'negativos': negativos,
            'rutas_conjuntos': {k: str(c['ruta']) for k, c in conjuntos.items()}}


def escribir(informe: dict, repo: Path | str) -> Path:
    """Escribe el informe en ``docs/EVALUACION_FINAL_1.0.json`` por reemplazo atómico."""
    destino = Path(repo) / DESTINO
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(informe, ensure_ascii=False, indent=1, allow_nan=False) + '\n'
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix='.evaluacion_final_', suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        f.write(texto)
    os.replace(tmp, destino)
    return destino


def validar(informe: dict, *, repo: Path | str) -> None:
    """044:RF-11: relee un informe ya escrito; desde su rev solo puede haber cambiado el propio informe."""
    repo = Path(repo)
    if informe.get('esquema') != ESQUEMA or not _REV.fullmatch(str(informe.get('rev') or '')):
        raise InformeRechazado('no es un informe de la evaluación final con su rev')
    if informe.get('arbol_limpio') is not True:
        raise InformeRechazado('el informe no se midió sobre un árbol limpio')
    rev = informe['rev']
    cabeza, sucios = estado_git(repo)
    cambiados = [] if cabeza == rev else _git(repo, 'diff', '--name-only', rev, cabeza).split()
    otros = [r for r in cambiados + sucios if r != DESTINO]
    if otros:
        raise InformeRechazado(f'desde la rev {rev[:12]} cambiaron otros ficheros: {", ".join(otros[:5])}')
    rutas = informe.get('rutas_conjuntos') or {}
    conjuntos = {k: {**c, 'ruta': rutas.get(k)} for k, c in (informe.get('conjuntos') or {}).items()}
    _comprobar_conjuntos(conjuntos, repo)
    for bloque, propias in (informe.get('medidas') or {}).items():
        for nombre, m in propias.items():
            _comprobar_medida(bloque, nombre, m, conjuntos)
