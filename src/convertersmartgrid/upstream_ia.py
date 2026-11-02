"""043:RF-9 a RF-11 — custodia compartida de repositorios de IA reutilizados."""
from __future__ import annotations

from .runtime_paths import staging_publicacion

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
from collections.abc import Mapping

RAIZ = Path(__file__).resolve().parents[2]


def _git(argumentos: list[str], *, cwd: Path | None = None) -> bytes:
    proceso = subprocess.run(['git', '-c', 'core.longpaths=true', *argumentos], cwd=cwd,
        env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1'},
        capture_output=True, timeout=240, check=False)
    if proceso.returncode:
        raise ValueError(proceso.stderr.decode('utf-8', errors='replace')[-1500:])
    return proceso.stdout


def _validar_entrada(entrada: Mapping) -> None:
    for clave, patron in (
        ('id', r'[a-z0-9][a-z0-9_-]*'),
        ('url', r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?'),
        ('commit', r'[0-9a-f]{40}'), ('license_sha256', r'[0-9a-f]{64}'),
    ):
        if not isinstance(entrada.get(clave), str) or not re.fullmatch(patron, entrada[clave]):
            raise ValueError(f'entrada upstream inválida: {clave}')
    if entrada.get('license') not in {'MIT', 'Apache-2.0', 'BSD-3-Clause', 'BSD-2-Clause', 'EPL-2.0'}:
        raise ValueError('licencia no revisada para este catálogo')
    licencia = PurePosixPath(entrada.get('license_path', ''))
    if not licencia.parts or licencia.is_absolute() or '..' in licencia.parts or '\\' in str(licencia):
        raise ValueError('ruta de licencia inválida')


def _verificar(entrada: Mapping, carpeta: Path) -> dict:
    if not carpeta.is_dir() or not (carpeta / '.git').exists():
        raise ValueError('copia Git ausente')
    origen = _git(['config', '--get', 'remote.origin.url'], cwd=carpeta).decode().strip()
    if origen.removesuffix('.git').rstrip('/') != entrada['url'].removesuffix('.git').rstrip('/'):
        raise ValueError('origen distinto del catálogo')
    revision = _git(['rev-parse', 'HEAD'], cwd=carpeta).decode().strip()
    if revision != entrada['commit']:
        raise ValueError('revisión distinta de la fijada; se conserva la copia')
    if _git(['status', '--porcelain', '--untracked-files=all'], cwd=carpeta).strip():
        raise ValueError('copia con cambios locales; se conserva sin sobrescribir')
    licencia = _git(['show', f"{revision}:{entrada['license_path']}"], cwd=carpeta)
    if hashlib.sha256(licencia).hexdigest() != entrada['license_sha256']:
        raise ValueError('licencia distinta de la revisada')
    return {'id': entrada['id'], 'commit': revision, 'license': entrada['license'],
            'url': entrada['url'], 'path': str(carpeta), 'ok': True}


def preparar_catalogo(catalogo: Mapping, destino: Path, *, verificar: bool = False) -> dict:
    """Verifica antes de reutilizar; jamás hace pull/reset sobre una copia existente."""
    if catalogo.get('schema_version') != 1 or not isinstance(catalogo.get('repositorios'), list):
        raise ValueError('contrato de catálogo upstream no soportado')
    entradas = catalogo['repositorios']
    for entrada in entradas:
        _validar_entrada(entrada)
    if not entradas or len({e['id'] for e in entradas}) != len(entradas):
        raise ValueError('catálogo vacío o con identidades duplicadas')
    destino = Path(destino).resolve()
    resultados = []
    for entrada in entradas:
        carpeta = destino / entrada['id']
        try:
            if not carpeta.resolve().is_relative_to(destino):
                raise ValueError('copia resuelve fuera del directorio de terceros')
            if not carpeta.exists() and not verificar:
                destino.mkdir(parents=True, exist_ok=True)
                with staging_publicacion(carpeta) as temporal:
                    temporal.mkdir()
                    try:
                        _git(['init', str(temporal)])
                        _git(['remote', 'add', 'origin', entrada['url']], cwd=temporal)
                        _git(['fetch', '--depth', '1', '--filter=blob:none', 'origin', entrada['commit']], cwd=temporal)
                        _git(['checkout', '--detach', entrada['commit']], cwd=temporal)
                        _verificar(entrada, temporal)
                        # Un destino aparecido durante la descarga se conserva; no reemplazarlo.
                        if carpeta.exists():
                            raise ValueError('otra copia apareció durante la preparación')
                        temporal.rename(carpeta)
                    finally:
                        if temporal.exists():
                            limite = temporal.resolve()
                            def quitar_solo_lectura(funcion, ruta, exc):
                                if not isinstance(exc, PermissionError) or not Path(ruta).resolve().is_relative_to(limite):
                                    raise exc
                                os.chmod(ruta, stat.S_IWRITE)
                                funcion(ruta)
                            shutil.rmtree(temporal, onexc=quitar_solo_lectura)
            resultados.append(_verificar(entrada, carpeta))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            resultados.append({'id': entrada['id'], 'ok': False, 'error': str(exc)})
    return {'schema_version': 1, 'ok': all(r['ok'] for r in resultados), 'repositorios': resultados}


def verificar_repositorio(nombre: str, *, catalogo: Path | Mapping | None = None,
                          destino: Path | None = None) -> dict:
    if catalogo is None:
        catalogo = RAIZ / 'docs/UPSTREAM_IA_LOCK.json'
    if not isinstance(catalogo, Mapping):
        catalogo = json.loads(Path(catalogo).read_text(encoding='utf-8'))
    entradas = [e for e in catalogo.get('repositorios', []) if e.get('id') == nombre]
    if len(entradas) != 1:
        raise ValueError(f'repositorio no registrado: {nombre}')
    informe = preparar_catalogo({'schema_version': 1, 'repositorios': entradas},
        destino or RAIZ / 'external/upstream', verificar=True)
    resultado = informe['repositorios'][0]
    if not resultado['ok']:
        raise ValueError(resultado['error'])
    return resultado
