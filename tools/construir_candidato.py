"""Arma un candidato de la entrega: rueda propia, terceros con huella, documentos y manifiesto (spec 086, RF-36 a RF-39, RF-44).

Uso:
  python tools/construir_candidato.py rueda --salida DIR [--version 1.0.0rc2]
  python tools/construir_candidato.py lock [--salida requirements-nucleo.lock]
  python tools/construir_candidato.py candidato --salida DIR --python-embebido python-3.12.x-embed-amd64.zip
                                                [--ruedas-cache DIR] [--version 1.0.0rc2]

`rueda` construye el programa: lo que `config/entrega.json` deja entrar, con `tools/`, `config/` y `frontend/dist/`
dentro del paquete y los comentarios neutralizados (D5). `lock` fija con huella lo que necesita el núcleo, sin
pruebas ni torch. `candidato` reúne todo en la forma que lee `tools/instalar_candidato.py` y que comprueba
`tools/comprobar_entrega.py`, y al final lo comprueba. Compilar el front es un paso previo, con Node, que el cliente
no necesita: `cd frontend && npm ci && npm run build`.

La carpeta del candidato queda lista para el guion de Inno Setup, `instalador/ConverterSmartGrid.iss`.

Salida: 0 bien, 1 no se pudo armar, 2 armado pero rechazado por `comprobar_entrega`.
"""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
sys.path.insert(0, str(RAIZ / 'tools'))

import comprobar_entrega as CE  # noqa: E402  (herramienta hermana, sin instalar)

LOCK = RAIZ / 'requirements-nucleo.lock'
COMPLEMENTO_IA = RAIZ / 'requirements-complemento-ia.txt'
PROGRAMA_EN_PAQUETE = Path('src', 'convertersmartgrid', '_programa')
#: Lo que se copia a «documentos/» del candidato. Pasa por la misma lista de términos que el código.
DOCUMENTOS = ('docs/MANUAL_INSTALACION.md', 'docs/MANUAL_OPERADOR.md', 'docs/SEGURIDAD_Y_PRIVACIDAD.md', 'docs/PERFIL_EMPRESA.md',
              'src/convertersmartgrid/recursos/NOTAS_VERSION.md', 'requirements-complemento-ia.txt')
_LEEME_RUEDA = 'ConverterSmartGrid: conversor de redes de distribución a DIgSILENT PowerFactory.\n'
_MARCADOR = 'python_version == "3.12" and sys_platform == "win32" and platform_machine == "AMD64"'


def _pip(*argumentos: str) -> None:
    orden = [sys.executable, '-m', 'pip', '--disable-pip-version-check', *argumentos]
    r = subprocess.run(orden, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    if r.returncode:
        raise CE.EntregaError(f'pip falló: {" ".join(argumentos[:3])}…\n{r.stdout[-2500:]}\n{r.stderr[-2500:]}')


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


# --------------------------------------------------------------------------- rueda propia
def preparar_arbol(raiz: Path, arbol: Path, manifiesto: dict, terminos: CE.Terminos, *, version: str | None = None,
                   dist: Path | None = None) -> dict[str, int]:
    """Copia a ``arbol`` lo que la lista deja entrar, en la forma del paquete; devuelve qué hizo."""
    dist = raiz / 'frontend' / 'dist' if dist is None else dist
    if not (dist / 'index.html').is_file():
        raise CE.EntregaError('Falta la compilación del front: cd frontend && npm ci && npm run build.')
    from convertersmartgrid.web.runtime import integridad_del_front

    motivo = integridad_del_front(dist)
    if motivo:
        raise CE.EntregaError(f'La compilación del front no sirve: {motivo}.')
    memoria: dict[str, str | None] = {}
    cuenta = {'ficheros': 0, 'neutralizados': 0, 'lugares_neutralizados': 0}
    for ruta, rel in CE._recorrer(raiz):
        if not CE.entra(rel, manifiesto):
            continue
        destino = arbol / rel if rel.startswith('src/') else arbol / PROGRAMA_EN_PAQUETE / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        cuenta['ficheros'] += 1
        if ruta.suffix == '.py':
            # D5: nada de casos reales en lo entregado; el motivo del comentario se conserva.
            nuevo, n = CE.neutralizar(rel, ruta.read_text(encoding='utf-8'), terminos, memoria)
            if n:
                cuenta['neutralizados'] += 1
                cuenta['lugares_neutralizados'] += n
            destino.write_text(nuevo, encoding='utf-8', newline='')
        else:
            shutil.copyfile(ruta, destino)
    if dist != raiz / 'frontend' / 'dist':
        shutil.copytree(dist, arbol / PROGRAMA_EN_PAQUETE / 'frontend' / 'dist', dirs_exist_ok=True)
    front = _componentes_del_front(raiz)
    avisos = _avisos(front, _licencias_del_front(raiz, front))
    (arbol / PROGRAMA_EN_PAQUETE / 'frontend' / 'dist' / 'THIRD_PARTY_NOTICES.txt').write_text(avisos, encoding='utf-8')
    shutil.copyfile(raiz / 'pyproject.toml', arbol / 'pyproject.toml')
    (arbol / 'README.md').write_text(_LEEME_RUEDA, encoding='utf-8')
    if version:
        inicial = arbol / 'src' / 'convertersmartgrid' / '__init__.py'
        texto, n = re.subn(r"^__version__ = '[^']+'$", f"__version__ = '{version}'", inicial.read_text(encoding='utf-8'), flags=re.M)
        if n != 1:
            raise CE.EntregaError('No se encontró la versión en el paquete.')
        inicial.write_text(texto, encoding='utf-8', newline='')
    return cuenta


def construir_rueda(raiz: Path, salida: Path, manifiesto: dict, terminos: CE.Terminos, *, version: str | None = None,
                    dist: Path | None = None) -> tuple[Path, dict[str, int]]:
    """Sin aislamiento: con setuptools del entorno, para no salir a internet a por él en cada construcción."""
    salida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='csg-rueda-') as temporal:
        arbol = Path(temporal) / 'arbol'
        cuenta = preparar_arbol(raiz, arbol, manifiesto, terminos, version=version, dist=dist)
        _pip('wheel', '--no-deps', '--no-build-isolation', '--no-cache-dir', '-w', str(salida), str(arbol))
    ruedas = sorted(salida.glob('convertersmartgrid-*.whl'))
    if len(ruedas) != 1:
        raise CE.EntregaError(f'Se esperaba una rueda en {salida} y hay {len(ruedas)}.')
    return ruedas[0], cuenta


# --------------------------------------------------------------------------- lock del núcleo
def requisitos_del_nucleo(raiz: Path, fuera: Iterable[str]) -> list[str]:
    """Lo de ``requirements.txt`` sin el paquete propio y sin lo de desarrollo (RF-36: sin pytest)."""
    fuera = {f.lower() for f in fuera}
    salida = []
    for linea in (raiz / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        limpia = linea.split('#')[0].strip()
        if not limpia or limpia.startswith('-'):
            continue
        nombre = re.split(r'[\s<>=!~;\[]', limpia, maxsplit=1)[0].lower().replace('_', '-')
        if nombre not in fuera:
            salida.append(limpia)
    return salida


def _nombre_y_version(rueda: str) -> tuple[str, str]:
    partes = rueda.split('-')
    return partes[0].replace('_', '-').lower(), partes[1]


def escribir_lock(ruedas: Path, destino: Path) -> list[tuple[str, str, str]]:
    filas = sorted((*_nombre_y_version(r.name), _sha256(r)) for r in ruedas.glob('*.whl'))
    nombres = [f[0] for f in filas]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise CE.EntregaError(f'En {ruedas} hay más de una versión de {", ".join(repetidos)}: un lock no puede llevar las dos.')
    cuerpo = ''.join(f'{n}=={v} \\\n    --hash=sha256:{h}\n' for n, v, h in filas)
    destino.write_text('# Generado por tools/construir_candidato.py lock. El núcleo de la entrega (086:RF-37, RF-39), sin pruebas ni torch.\n'
                       '# CPython 3.12, Windows AMD64. Cada rueda con su huella: otra rueda con el mismo nombre no se instala.\n' + cuerpo,
                       encoding='utf-8', newline='\n')
    return filas


def _descargar_nucleo(raiz: Path, ruedas: Path, manifiesto: dict) -> None:
    """Resuelve con las versiones fijadas de ``constraints``; la primera vez, del índice."""
    ruedas.mkdir(parents=True, exist_ok=True)
    pedido = ruedas.parent / 'pedido-nucleo.txt'
    limites = ruedas.parent / 'limites-nucleo.txt'
    pedido.write_text('\n'.join(['pip', *requisitos_del_nucleo(raiz, manifiesto['candidato']['fuera_del_nucleo'])]) + '\n', encoding='utf-8')
    limites.write_text(limites_con_seguridad((raiz / 'constraints-python312-win.txt').read_text(encoding='utf-8'), manifiesto['candidato'].get('versiones_de_seguridad') or {}),
                       encoding='utf-8')
    try:
        _pip('download', '--only-binary', ':all:', '-d', str(ruedas), '-c', str(limites), '-r', str(pedido))
    finally:
        pedido.unlink(missing_ok=True)
        limites.unlink(missing_ok=True)


def limites_con_seguridad(texto: str, seguridad: dict[str, str]) -> str:
    """Las versiones fijadas, con las de seguridad encima: solo esas cambian respecto al entorno probado."""
    lineas = [l for l in texto.splitlines() if l.split('==')[0].strip().lower() not in seguridad]
    return '\n'.join([*lineas, *(f'{n}=={v}' for n, v in sorted(seguridad.items()))]) + '\n'


def traer_ruedas(raiz: Path, destino: Path, lock: Path, cache: Path | None) -> None:
    """Con huella también al construir: lo que entra es lo que se fijó, venga de la caché o del índice."""
    destino.mkdir(parents=True, exist_ok=True)
    fuentes = ['--no-index', '--find-links', str(cache)] if cache else []
    _pip('download', '--only-binary', ':all:', '--no-deps', '--require-hashes', '-d', str(destino), *fuentes, '-r', str(lock))


# --------------------------------------------------------------------------- inventario de terceros
def leer_metadatos_de_rueda(rueda: Path) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Nombre, versión, licencia y los textos de licencia que trae la propia rueda."""
    with zipfile.ZipFile(rueda) as z:
        nombres = z.namelist()
        meta = next(n for n in nombres if n.endswith('.dist-info/METADATA') and n.count('/') == 1)
        m = email.message_from_bytes(z.read(meta))
        # Si no, un paquete que declara su licencia en clasificadores quedaba como «desconocida» en el inventario.
        clasificadas = [v.split('::')[-1].strip() for v in (m.get_all('Classifier') or ()) if v.startswith('License ::')]
        cabecera = (m.get('License') or '').strip().splitlines()
        licencia = m.get('License-Expression') or '; '.join(clasificadas) or (cabecera[0][:120] if cabecera else '') or 'desconocida'
        textos = [(n, z.read(n).decode('utf-8', 'replace')) for n in nombres
                  if '.dist-info/' in n and re.search(r'(^|/)(?:[^/]*[-_.])?(licen[cs]e|copying|notice)[^/]*$', n, re.I) and not n.endswith('/')]
    return {'name': m['Name'], 'version': m['Version'], 'license': licencia, 'summary': m.get('Summary') or ''}, textos


def sbom(componentes: list[dict[str, Any]], version: str, revision: str) -> dict[str, Any]:
    """CycloneDX 1.5, generado sin dependencias nuevas: solo lista lo que de verdad se entrega."""
    def fila(c: dict[str, Any]) -> dict[str, Any]:
        lic = c.get('license') or 'desconocida'
        return {'type': c.get('tipo', 'library'), 'name': c['name'], 'version': c['version'],
                **({'purl': f'pkg:pypi/{c["name"].lower()}@{c["version"]}'} if c.get('tipo', 'library') == 'library' and not c.get('sin_purl') else {}),
                **({'hashes': [{'alg': 'SHA-256', 'content': c['sha256']}]} if c.get('sha256') else {}),
                'licenses': [{'license': {'name': lic[:200]}}]}

    return {'bomFormat': 'CycloneDX', 'specVersion': '1.5', 'version': 1,
            'metadata': {'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                         'component': {'type': 'application', 'name': 'convertersmartgrid', 'version': version,
                                       'properties': [{'name': 'revision', 'value': revision}]}},
            'components': [fila(c) for c in componentes]}


def _componentes_del_front(raiz: Path) -> list[dict[str, Any]]:
    """Solo lo que acaba en la compilación: las dependencias de ejecución del front, no sus herramientas."""
    lock = json.loads((raiz / 'frontend' / 'package-lock.json').read_text(encoding='utf-8'))['packages']
    salida = []
    # npm marca el árbol exclusivamente de desarrollo con dev=true. También se
    # entregan transitivas y opcionales de producción (devOptional no significa dev).
    for ruta, fila in sorted(lock.items()):
        if not ruta.startswith('node_modules/') or fila.get('dev'):
            continue
        nombre = ruta.rsplit('node_modules/', 1)[-1]
        salida.append({'name': nombre, 'version': fila.get('version', '?'), 'license': fila.get('license') or 'desconocida', 'origen': 'front', 'sin_purl': True})
    return salida


def _avisos(componentes: list[dict[str, Any]], textos: dict[str, list[tuple[str, str]]]) -> str:
    partes = ['THIRD_PARTY_NOTICES: ConverterSmartGrid incluye estos componentes de terceros.',
              'Inventario técnico generado de sus metadatos: no es una opinión legal (086, D7).', '']
    partes += [f'{c["name"]} {c["version"]} [{c.get("origen", "python")}]: {c.get("license", "desconocida")}' for c in componentes]
    for nombre, lista in sorted(textos.items()):
        for ruta, texto in lista:
            partes += ['', '=' * 78, f'{nombre}: {ruta}', '=' * 78, texto.strip()]
    return '\n'.join(partes) + '\n'


def _licencias_del_front(raiz: Path, componentes: list[dict[str, Any]]) -> dict[str, list[tuple[str, str]]]:
    """086:RF-39 — textos revisados del mismo tarball que fija npm; construcción sin red."""
    carpeta = raiz / 'frontend' / 'licencias'
    try:
        manifest = json.loads((carpeta / 'manifest.json').read_text(encoding='utf-8'))
        lock = json.loads((raiz / 'frontend' / 'package-lock.json').read_text(encoding='utf-8'))['packages']
        paquetes = {(p['name'], p['version'], p['integrity']): p for p in manifest['packages']}
        textos = {}
        for c in componentes:
            coincidencias = [p for ruta, p in lock.items()
                            if ruta.startswith('node_modules/') and not p.get('dev')
                            and ruta.rsplit('node_modules/', 1)[-1] == c['name'] and p['version'] == c['version']]
            if not coincidencias:
                raise ValueError(f'componente ausente del lock: {c["name"]}')
            for fila in coincidencias:
                p = paquetes[(c['name'], c['version'], fila['integrity'])]
                ruta = (carpeta / p['license_file']).resolve()
                if not ruta.is_relative_to(carpeta.resolve()):
                    raise ValueError('licencia fuera de su carpeta')
                if _sha256(ruta) != p['license_sha256']:
                    raise ValueError(f'huella de licencia distinta: {c["name"]}')
                texto = ruta.read_text(encoding='utf-8')
                if not texto.strip():
                    raise ValueError(f'licencia vacía: {c["name"]}')
                textos[f'{c["name"]} {c["version"]}'] = [(p['license_file'], texto)]
        return textos
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CE.EntregaError(f'Licencias del front incompletas o distintas del lock: {exc}') from exc


# --------------------------------------------------------------------------- candidato
def _revision(raiz: Path) -> str:
    r = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz, capture_output=True, text=True, check=False)
    return r.stdout.strip() or 'sin revisión'


def extraer_python(zip_embebido: Path, destino: Path) -> str:
    """Sin el ``._pth``: con él, Python no leería PYTHONPATH, y así es como un guion encuentra la API de DIgSILENT."""
    if not re.fullmatch(r'python-3\.12\.\d+-embed-amd64\.zip', zip_embebido.name):
        raise CE.EntregaError(f'Se espera el Python 3.12 embebido de 64 bits, y esto es {zip_embebido.name}: la API de DIgSILENT solo carga en 3.12.')
    with zipfile.ZipFile(zip_embebido) as z:
        z.extractall(destino)
    for pth in destino.glob('*._pth'):
        pth.unlink()
    (destino / 'Lib' / 'site-packages').mkdir(parents=True, exist_ok=True)
    return zip_embebido.name.split('-')[1]


def construir_candidato(raiz: Path, salida: Path, zip_python: Path, *, cache: Path | None = None, version: str | None = None,
                        lista_local: Path | None = None) -> tuple[dict[str, Any], CE.Informe]:
    if salida.exists() and any(salida.iterdir()):
        raise CE.EntregaError(f'La carpeta {salida} no está vacía: un candidato no se arma sobre otro.')
    manifiesto = CE.leer_manifiesto(raiz / 'config' / 'entrega.json')
    terminos = CE.cargar_terminos(raiz, manifiesto, lista_local=lista_local)
    if not LOCK.is_file():
        raise CE.EntregaError(f'Falta {LOCK.name}: genérelo con la orden «lock».')
    rueda, cuenta = construir_rueda(raiz, salida / 'programa', manifiesto, terminos, version=version)
    version_final = rueda.name.split('-')[1]
    ruedas = salida / 'terceros' / 'wheels'
    traer_ruedas(raiz, ruedas, raiz / LOCK.name, cache)
    version_python = extraer_python(zip_python, salida / 'terceros' / 'python')
    # El lock más la rueda propia: pip la instala por su huella como a las demás.
    (salida / 'terceros' / 'instalacion.lock').write_text(
        (raiz / LOCK.name).read_text(encoding='utf-8')
        + f'convertersmartgrid=={version_final} \\\n    --hash=sha256:{_sha256(rueda)}\n', encoding='utf-8', newline='\n')
    instalador = salida / 'instalador'
    instalador.mkdir()
    shutil.copyfile(raiz / 'tools' / 'instalar_candidato.py', instalador / 'instalar_candidato.py')
    shutil.copyfile(raiz / 'instalador' / 'ConverterSmartGrid.iss', instalador / 'ConverterSmartGrid.iss')
    documentos = salida / 'documentos'
    documentos.mkdir()
    for rel in DOCUMENTOS:
        shutil.copyfile(raiz / rel, documentos / Path(rel).name)
    componentes: list[dict[str, Any]] = []
    textos: dict[str, list[tuple[str, str]]] = {}
    for r in sorted(ruedas.glob('*.whl')):
        meta, licencias = leer_metadatos_de_rueda(r)
        componentes.append({**meta, 'sha256': _sha256(r), 'origen': 'python'})
        textos[f'{meta["name"]} {meta["version"]}'] = licencias
    componentes.append({'name': 'CPython', 'version': version_python, 'license': 'PSF-2.0', 'origen': 'embebido', 'sha256': _sha256(zip_python), 'sin_purl': True})
    licencia_python = salida / 'terceros' / 'python' / 'LICENSE.txt'
    if licencia_python.is_file():
        textos[f'CPython {version_python}'] = [('LICENSE.txt', licencia_python.read_text(encoding='utf-8', errors='replace'))]
    front = _componentes_del_front(raiz)
    componentes += front
    textos.update(_licencias_del_front(raiz, front))
    leaflet = raiz / 'src' / 'convertersmartgrid' / 'recursos' / 'leaflet' / 'LICENSE'
    componentes.append({'name': 'leaflet', 'version': 'en recursos/leaflet', 'license': 'BSD-2-Clause', 'origen': 'web', 'sin_purl': True})
    textos['leaflet'] = [('LICENSE', leaflet.read_text(encoding='utf-8'))]
    revision = _revision(raiz)
    (documentos / 'THIRD_PARTY_NOTICES.txt').write_text(_avisos(componentes, textos), encoding='utf-8')
    (documentos / 'sbom.cdx.json').write_text(json.dumps(sbom(componentes, version_final, revision), ensure_ascii=False, indent=2), encoding='utf-8')
    ficheros = [{'ruta': rel, 'sha256': _sha256(r), 'bytes': r.stat().st_size} for r, rel in CE._recorrer(salida)]
    salida_manifiesto = {'version': version_final, 'revision': revision, 'python': version_python, 'creado': time.time(),
                         'neutralizados': cuenta, 'bytes_total': sum(f['bytes'] for f in ficheros), 'ficheros': ficheros}
    (salida / 'manifiesto_candidato.json').write_text(json.dumps(salida_manifiesto, ensure_ascii=False, indent=1), encoding='utf-8')
    return salida_manifiesto, CE.comprobar(raiz, manifiesto, terminos, candidato=salida)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    orden = parser.add_subparsers(dest='orden', required=True)
    p_rueda = orden.add_parser('rueda', help='Solo la rueda del programa.')
    p_rueda.add_argument('--salida', type=Path, required=True)
    p_rueda.add_argument('--version', help='Otra versión, para ensayar una actualización.')
    p_lock = orden.add_parser('lock', help='Fija con huella las ruedas del núcleo; descarga del índice.')
    p_lock.add_argument('--salida', type=Path, default=LOCK)
    p_lock.add_argument('--ruedas', type=Path, help='Carpeta donde dejar las ruedas; por defecto, una temporal.')
    p_cand = orden.add_parser('candidato', help='El paquete entero.')
    p_cand.add_argument('--salida', type=Path, required=True)
    p_cand.add_argument('--python-embebido', type=Path, required=True, help='python-3.12.x-embed-amd64.zip de python.org')
    p_cand.add_argument('--ruedas-cache', type=Path, help='Carpeta con las ruedas ya descargadas; sin ella, del índice.')
    p_cand.add_argument('--version', help='Otra versión, para ensayar una actualización.')
    p_cand.add_argument('--lista-local', type=Path, help='Lista de términos fuera de git; si no, CSG_TERMINOS_PROHIBIDOS.')
    args = parser.parse_args(argv)
    try:
        manifiesto = CE.leer_manifiesto(RAIZ / 'config' / 'entrega.json')
        if args.orden == 'rueda':
            rueda, cuenta = construir_rueda(RAIZ, args.salida, manifiesto, CE.cargar_terminos(RAIZ, manifiesto), version=args.version)
            print(json.dumps({'rueda': str(rueda), 'bytes': rueda.stat().st_size, **cuenta}, ensure_ascii=False, indent=2))
            return 0
        if args.orden == 'lock':
            with tempfile.TemporaryDirectory(prefix='csg-lock-') as temporal:
                ruedas = args.ruedas or Path(temporal) / 'ruedas'
                _descargar_nucleo(RAIZ, ruedas, manifiesto)
                filas = escribir_lock(ruedas, args.salida)
            print(json.dumps({'lock': str(args.salida), 'ruedas': len(filas)}, ensure_ascii=False, indent=2))
            return 0
        resultado, informe = construir_candidato(RAIZ, args.salida, args.python_embebido, cache=args.ruedas_cache, version=args.version, lista_local=args.lista_local)
        print(json.dumps({k: resultado[k] for k in ('version', 'revision', 'python', 'neutralizados', 'bytes_total')} | {'ficheros': len(resultado['ficheros'])},
                         ensure_ascii=False, indent=2))
        print(json.dumps(informe.resumen(), ensure_ascii=False, indent=2))
        return 2 if informe.rechazado else 0
    except (CE.EntregaError, OSError, ValueError) as exc:
        print(f'No se pudo armar: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
