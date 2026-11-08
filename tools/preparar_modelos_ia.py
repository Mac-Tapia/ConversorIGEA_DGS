#!/usr/bin/env python
"""043:RF-12: audita pesos locales; --descargar obtiene revisiones fijas sin activarlas.

    python tools/preparar_modelos_ia.py --output-json output/modelos_auditados.json
    python tools/preparar_modelos_ia.py --descargar --backend huggingface --output-json output/modelos_descargados.json

No importa Torch, ejecuta codigo de modelos ni modifica pesos existentes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
from convertersmartgrid.salidas_red import motivo_apagada, salida_permitida  # noqa: E402


def validar_catalogo(catalogo):
    if catalogo.get('schema_version') != 1 or not catalogo.get('modelos'):
        raise ValueError('catalogo vacio o version no admitida')
    vistos = set()
    for m in catalogo['modelos']:
        backend, nombre = m.get('backend'), m.get('id')
        if backend not in ('huggingface', 'ollama') or not isinstance(nombre, str) or nombre in vistos:
            raise ValueError('modelo o backend invalido/duplicado')
        vistos.add(nombre)
        if backend == 'huggingface' and (not re.fullmatch(r'[\w.-]+/[\w.-]+', nombre)
                                         or any(p in ('.', '..') for p in nombre.split('/'))):
            raise ValueError('identidad de repositorio invalida')
        if not re.fullmatch('[0-9a-f]{40}' if backend == 'huggingface' else '[0-9a-f]{64}', m.get('revision', '')):
            raise ValueError('revision mutable o invalida')
        if not m.get('licencia'):
            raise ValueError('licencia no registrada')
        if backend == 'huggingface':
            if not m.get('files'):
                raise ValueError('modelo sin inventario de archivos')
            rutas = set()
            for f in m['files']:
                p = PurePosixPath(f['path'])
                if (not p.parts or p.is_absolute() or PureWindowsPath(f['path']).drive
                        or '..' in p.parts or '\\' in f['path'] or ':' in f['path'] or '\0' in f['path']
                        or f['path'] in rutas):
                    raise ValueError('ruta de archivo invalida/duplicada')
                rutas.add(f['path'])
                if type(f.get('size')) is not int or f['size'] <= 0:
                    raise ValueError('tamano de archivo invalido')
                if f['path'].endswith('.safetensors') and not re.fullmatch('[0-9a-f]{64}', f.get('sha256') or ''):
                    raise ValueError('pesos sin SHA-256')
                if f.get('sha256') is not None and not re.fullmatch('[0-9a-f]{64}', f['sha256']):
                    raise ValueError('SHA-256 de archivo invalido')
                if f.get('git_blob_sha1') is not None and not re.fullmatch('[0-9a-f]{40}', f['git_blob_sha1']):
                    raise ValueError('SHA-1 de blob Git invalido')
                if not f.get('sha256') and not f.get('git_blob_sha1'):
                    raise ValueError('archivo sin hash de integridad')
    return catalogo


def verificar_archivo(ruta, ficha):
    ruta = Path(ruta)
    if not ruta.is_file() or ruta.stat().st_size != ficha['size']:
        return False
    if ficha.get('sha256'):
        with ruta.open('rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest() == ficha['sha256']
    if ficha.get('git_blob_sha1'):
        contenido = ruta.read_bytes()
        return hashlib.sha1(f'blob {len(contenido)}\0'.encode() + contenido).hexdigest() == ficha['git_blob_sha1']
    return True


def descargar_por_partes(url, destino, ficha, *, tamano_parte=32 * 1024 * 1024):
    """Reanuda fragmentos pequenos y publica solo tras verificar el SHA-256 completo."""
    destino = Path(destino)
    partes = destino.parent / ('.csg-' + ficha['sha256'] + '-partes')
    if destino.exists():
        return _publicado(destino, ficha, partes)
    partes.mkdir(parents=True, exist_ok=True)
    total = (ficha['size'] + tamano_parte - 1) // tamano_parte
    import requests
    import urllib3.util.connection as conexion
    def uno(i):
        inicio = i * tamano_parte
        fin = min(ficha['size'], inicio + tamano_parte) - 1
        ruta = partes / f'{i:05d}.part'
        if ruta.exists() and ruta.stat().st_size == fin-inicio+1:
            return ruta
        temporal = ruta.with_suffix('.incomplete')
        with requests.Session() as sesion:
            sesion.trust_env = False
            for intento in range(12):
                recibidos = temporal.stat().st_size if temporal.exists() else 0
                if recibidos == fin-inicio+1:
                    break
                if recibidos > fin-inicio+1:
                    return None
                try:
                    with sesion.get(url, headers={'Range': f'bytes={inicio+recibidos}-{fin}'},
                                    stream=True, timeout=(15, 60)) as respuesta:
                        respuesta.raise_for_status()
                        esperado = f'bytes {inicio+recibidos}-{fin}/{ficha["size"]}'
                        if respuesta.status_code != 206 or respuesta.headers.get('Content-Range') != esperado:
                            return None
                        with temporal.open('ab') as archivo:
                            for bloque in respuesta.iter_content(256*1024):
                                if archivo.tell() + len(bloque) > fin-inicio+1:
                                    return None
                                archivo.write(bloque)
                except requests.RequestException:
                    time.sleep(min(intento+1, 5))
        if not temporal.is_file() or temporal.stat().st_size != fin-inicio+1:
            return None
        os.replace(temporal, ruta)
        print(json.dumps({'blob': ficha['sha256'][:12], 'parte': i+1, 'total': total}), flush=True)
        return ruta
    familia_anterior = conexion.allowed_gai_family
    try:
        # Solo este proceso de descarga; no modifica DNS, proxy ni servicio del usuario.
        conexion.allowed_gai_family = lambda: socket.AF_INET
        with ThreadPoolExecutor(max_workers=8) as pool:
            rutas = list(pool.map(uno, range(total)))
    finally:
        conexion.allowed_gai_family = familia_anterior
    if any(r is None for r in rutas):
        return False
    ensamblado = partes / 'ensamblado.incomplete'
    with ensamblado.open('wb') as f:
        for ruta in rutas:
            with ruta.open('rb') as parte:
                shutil.copyfileobj(parte, f, length=1024*1024)
    if not verificar_archivo(ensamblado, ficha):
        return False
    if destino.exists():
        return _publicado(destino, ficha, partes)
    os.replace(ensamblado, destino)
    return _publicado(destino, ficha, partes, verificado=True)


def _publicado(destino, ficha, partes, verificado=False):
    """Con el blob publicado y verificado, los fragmentos sobran (043:RF-12).

    Se quedaban para siempre: el 2026-11-06 había 8,6 GB de fragmentos temporales de versiones antiguas y actuales
    junto a sus blobs ya completos en las cachés de C:. Si la verificación falla se conservan,
    porque son la descarga parcial que el siguiente intento reanuda.
    """
    if not (verificado or verificar_archivo(destino, ficha)):
        return False
    shutil.rmtree(partes, ignore_errors=True)
    return True


def preparar_hf(modelo, descargar=False):
    from huggingface_hub import hf_hub_download
    from huggingface_hub import constants
    def uno(f):
        error = None
        for intento in range(3 if descargar else 1):
            try:
                if descargar and f.get('sha256'):
                    raiz = Path(constants.HF_HUB_CACHE) / ('models--' + modelo['id'].replace('/', '--'))
                    blob = raiz / 'blobs' / f['sha256']
                    url = f'https://huggingface.co/{modelo["id"]}/resolve/{modelo["revision"]}/{f["path"]}'
                    if not descargar_por_partes(url, blob, f):
                        raise OSError('transferencia incompleta; fragmentos conservados')
                    ruta = raiz / 'snapshots' / modelo['revision'] / f['path']
                    ruta.parent.mkdir(parents=True, exist_ok=True)
                    if not ruta.exists():
                        os.link(blob, ruta)
                else:
                    ruta = hf_hub_download(modelo['id'], f['path'], revision=modelo['revision'],
                                           local_files_only=not descargar)
                if not verificar_archivo(ruta, f):
                    raise ValueError('archivo incompleto o hash distinto; copia conservada')
                print(json.dumps({'modelo': modelo['id'], 'archivo': f['path'], 'ok': True}), flush=True)
                return {'archivo': f['path'], 'ok': True, 'ruta': str(ruta)}
            except Exception as exc:
                # No persistir URLs firmadas ni credenciales presentes en errores HTTP.
                error = type(exc).__name__
                if descargar and intento < 2:
                    time.sleep(2 * (intento + 1))
        return {'archivo': f['path'], 'ok': False, 'error': error}
    # Cada peso ya usa ocho conexiones reanudables; evitar cambios de resolver concurrentes.
    with ThreadPoolExecutor(max_workers=1) as pool:
        archivos = list(pool.map(uno, modelo['files']))
    return {'id': modelo['id'], 'revision': modelo['revision'], 'archivos': archivos,
            'ok': all(f['ok'] for f in archivos)}


def preparar_ollama(modelo, descargar=False):
    abrir = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    def instalado_local():
        with abrir('http://127.0.0.1:11434/api/tags', timeout=10) as r:
            modelos = json.load(r).get('models', [])
        return next((m for m in modelos if m.get('name') == modelo['id']), {})
    instalado = instalado_local()
    if instalado:
        return {'id': modelo['id'], 'revision': instalado.get('digest'),
                'ok': instalado.get('digest') == modelo['revision'], 'conservado': True}
    if descargar:
        # Una etiqueta remota distinta de la revisada no habilita una descarga.
        repo, tag = modelo['id'].split(':', 1)
        with abrir(f'https://registry.ollama.ai/v2/library/{repo}/manifests/{tag}', timeout=30) as r:
            contenido = r.read()
            digest = hashlib.sha256(contenido).hexdigest()
        if digest != modelo['revision']:
            return {'id': modelo['id'], 'ok': False, 'error': 'etiqueta remota modificada; descarga bloqueada'}
        # Reanudar fragmentos por IPv4 conserva los prefijos tras los cortes remotos.
        cache = Path(os.environ.get('OLLAMA_MODELS') or Path.home() / '.ollama/models') / 'blobs'
        cache.mkdir(parents=True, exist_ok=True)
        manifiesto = json.loads(contenido)
        for ficha in [manifiesto['config'], *manifiesto['layers']]:
            sha = ficha['digest'].removeprefix('sha256:')
            if not re.fullmatch('[0-9a-f]{64}', sha):
                raise ValueError('digest de blob invalido')
            destino = cache / ('sha256-' + sha)
            esperado = {'size': ficha['size'], 'sha256': sha}
            if destino.exists():
                if not verificar_archivo(destino, esperado):
                    raise ValueError('blob existente invalido; se conserva sin sobrescribir')
                continue
            url = f'https://registry.ollama.ai/v2/library/{repo}/blobs/sha256:{sha}'
            if not descargar_por_partes(url, destino, esperado):
                return {'id': modelo['id'], 'ok': False, 'error': 'blob incompleto; parcial conservado'}
        proceso = subprocess.run(['ollama', 'pull', modelo['id']], check=False)
        if proceso.returncode:
            return {'id': modelo['id'], 'ok': False, 'error': 'fallo de descarga Ollama'}
        instalado = instalado_local()
    return {'id': modelo['id'], 'revision': instalado.get('digest'),
            'ok': instalado.get('digest') == modelo['revision']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalogo', type=Path, default=RAIZ / 'docs/MODELOS_IA_LOCK.json')
    p.add_argument('--descargar', action='store_true')
    p.add_argument('--backend', choices=('huggingface', 'ollama'))
    # 070:RF-77: la web lee su propia caché; preparar solo el modelo que falta, no los varios GB del catálogo.
    p.add_argument('--id', dest='solo_id', help='Solo este modelo del catálogo')
    p.add_argument('--output-json', type=Path, required=True)
    args = p.parse_args(argv)
    if args.descargar and not salida_permitida('hugging_face'):                # 086:RF-22
        print(motivo_apagada('hugging_face'), file=sys.stderr)
        return 1
    informe = {'schema_version': 1, 'modelos': [], 'ok': False, 'activaciones': 0}
    try:
        catalogo = validar_catalogo(json.loads(args.catalogo.read_text(encoding='utf-8')))
        for m in catalogo['modelos']:
            if args.backend and m['backend'] != args.backend:
                continue
            if args.solo_id and m['id'] != args.solo_id:
                continue
            try:
                r = (preparar_hf if m['backend'] == 'huggingface' else preparar_ollama)(m, args.descargar)
            except Exception as exc:
                r = {'id': m['id'], 'ok': False, 'error': type(exc).__name__}
            informe['modelos'].append(r)
            print(json.dumps({'id': m['id'], 'ok': r['ok']}), flush=True)
        informe['ok'] = bool(informe['modelos']) and all(m['ok'] for m in informe['modelos'])
    except Exception as exc:
        informe['error'] = str(exc)
    finally:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        temporal = args.output_json.with_suffix(f'.{os.getpid()}.tmp')
        temporal.write_text(json.dumps(informe, indent=2, ensure_ascii=True), encoding='utf-8')
        os.replace(temporal, args.output_json)
    return 0 if informe['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
