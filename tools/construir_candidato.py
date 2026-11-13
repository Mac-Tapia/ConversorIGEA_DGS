"""Arma un candidato de la entrega: rueda propia, terceros con huella, documentos y manifiesto (spec 086, RF-36 a RF-39, RF-44).

Uso:
  python tools/construir_candidato.py rueda --salida DIR [--version 1.0.0rc2]
  python tools/construir_candidato.py lock [--salida requirements-nucleo.lock]
  python tools/construir_candidato.py candidato --salida DIR --python-embebido python-3.12.x-embed-amd64.zip
                                                [--ruedas-cache DIR] [--version 1.0.0rc2]
  python tools/construir_candidato.py complemento-ia --salida DIR --ruedas-cache DIR [--version VERSION]
      [--capacidades integrales --versiones-capturadas FREEZE --procedencias JSON --licencias-suplementarias JSON]

`rueda` construye el programa: lo que `config/entrega.json` deja entrar, con `tools/`, `config/` y `frontend/dist/`
dentro del paquete y los comentarios neutralizados (D5). `lock` fija con huella lo que necesita el núcleo, sin
pruebas ni torch. `candidato` reúne todo en la forma que lee `tools/instalar_candidato.py` y que comprueba
`tools/comprobar_entrega.py`, y al final lo comprueba. Compilar el front es un paso previo, con Node, que el cliente
no necesita: `cd frontend && npm ci && npm run build`.

La carpeta del candidato queda lista para el guion de Inno Setup, `instalador/ConverterSmartGrid.iss`.

La versión es la de ``__version__`` del paquete (086:RF-92): la rueda la lleva en su nombre y el .iss la saca de ahí.
``--version`` solo sirve para ensayar una actualización. El candidato lleva en «documentos/» los manuales que se instalan
y las notas de su publicación, ``docs/NOTAS_VERSION_<x.y.z>.md`` (086:RF-89); si falta alguno, no se arma (086:RF-91).

Salida: 0 bien, 1 no se pudo armar, 2 armado pero rechazado por `comprobar_entrega`.
"""
from __future__ import annotations

import argparse
import email
from email import policy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from collections import deque
from collections.abc import Iterable
from pathlib import Path, PureWindowsPath
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
#: 086:RF-89: además, lo que el operador encuentra instalado, porque el .iss copia «documentos/» a «{app}\\documentos». El rc5
#: dejaba el candidato en «{app}\\_entrega» y lo borraba al terminar: los manuales se iban con él. Las notas de la
#: publicación no van aquí: su nombre sale de la versión, en ``documentos_del_candidato``.
MANUALES_INSTALADOS = ('docs/MANUAL_INSTALACION.md', 'docs/MANUAL_COMANDOS.md', 'docs/GUIA_PRUEBA_PERSONA_AJENA.md')
INICIAL_DEL_PAQUETE = Path('src', 'convertersmartgrid', '__init__.py')
NOTAS_DEL_PAQUETE = Path('src', 'convertersmartgrid', 'recursos', 'NOTAS_VERSION.md')
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


# --------------------------------------------------------------------------- versión y documentos (086:RF-89 a RF-93)
def version_del_paquete(raiz: Path) -> str:
    """086:RF-92: la versión, leída del único sitio donde se escribe, ``__version__`` del paquete de ``raiz``."""
    texto = (raiz / INICIAL_DEL_PAQUETE).read_text(encoding='utf-8')
    hallada = re.search(r"^__version__ = '([^']+)'$", texto, flags=re.M)
    if not hallada:
        raise CE.EntregaError(f'No se encontró la versión en {INICIAL_DEL_PAQUETE.as_posix()}.')
    return hallada.group(1)


def publicacion(version: str) -> str:
    """La publicación de una versión, sin su marca de candidata: ``1.0.0rc6`` → ``1.0.0``."""
    hallada = re.match(r'\d+(?:\.\d+)*', version)
    if not hallada:
        raise CE.EntregaError(f'La versión «{version}» no empieza por su número de publicación.')
    return hallada.group(0)


def documentos_del_candidato(version: str) -> tuple[str, ...]:
    """Lo que va a «documentos/» del candidato: los de siempre, los manuales que se instalan y las notas de su publicación."""
    pedidos = [*DOCUMENTOS, *MANUALES_INSTALADOS, f'docs/NOTAS_VERSION_{publicacion(version)}.md']
    return tuple(dict.fromkeys(pedidos))


def copiar_documentos(raiz: Path, destino: Path, version: str) -> list[str]:
    """086:RF-91: copia todos o ninguno; si falta alguno, el error los nombra y no se arma el candidato."""
    pedidos = documentos_del_candidato(version)
    faltan = [rel for rel in pedidos if not (raiz / rel).is_file()]
    if faltan:
        raise CE.EntregaError('Faltan documentos que se instalan con el programa: ' + ', '.join(faltan) + '.')
    destino.mkdir(parents=True, exist_ok=True)
    for rel in pedidos:
        shutil.copyfile(raiz / rel, destino / Path(rel).name)
    return [Path(rel).name for rel in pedidos]


def comprobar_notas(texto: str, version: str) -> None:
    """086:RF-93: las notas del paquete empiezan por el apartado de su versión, que es lo que enseña «Acerca de»."""
    from convertersmartgrid import seccion_de_notas

    apartados = re.findall(r'^## (\S+)', texto, flags=re.M)
    if not apartados or apartados[0] != version or seccion_de_notas(texto, version) is None:
        raise CE.EntregaError(f'Las notas del paquete ({NOTAS_DEL_PAQUETE.as_posix()}) no empiezan por el apartado '
                              f'«## {version}»: «Acerca de» enseñaría las de otra versión.')


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


def escribir_lock(ruedas: Path | Iterable[Path], destino: Path, *, complemento: bool = False) -> list[tuple[str, str, str]]:
    rutas = ruedas.glob('*.whl') if isinstance(ruedas, Path) else ruedas
    filas = sorted((*_nombre_y_version(r.name), _sha256(r)) for r in rutas)
    nombres = [f[0] for f in filas]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise CE.EntregaError(f'En {ruedas} hay más de una versión de {", ".join(repetidos)}: un lock no puede llevar las dos.')
    cuerpo = ''.join(f'{n}=={v} \\\n    --hash=sha256:{h}\n' for n, v, h in filas)
    titulo = 'Complemento de IA separado' if complemento else 'El núcleo de la entrega, sin pruebas ni torch'
    destino.write_text(f'# Generado por tools/construir_candidato.py. {titulo} (086:RF-37, RF-39).\n'
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
def _licencias_suplementarias(archivo: Path) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    """086:RF-39/44: una sola validación de destinos Windows, recibos y textos para leer y copiar."""
    from packaging.utils import canonicalize_name

    try:
        packages = json.loads(archivo.read_text(encoding='utf-8'))['packages']
        if not isinstance(packages, list):
            raise ValueError('inventario de licencias sin lista de paquetes')
        base = archivo.parent.resolve()
        nombres, destinos, textos = set(), {}, {}
        for package in packages:
            if (not isinstance(package, dict) or any(not isinstance(package.get(k), str) or not package[k].strip()
                    for k in ('name', 'version', 'license', 'wheel_sha256'))
                    or not re.fullmatch('[0-9a-f]{64}', package['wheel_sha256'])
                    or package['license'] == 'desconocida' or not isinstance(package.get('texts'), list)
                    or not package['texts']):
                raise ValueError('metadatos de licencia incompletos')
            nombre = canonicalize_name(package['name'])
            if nombre in nombres:
                raise ValueError('licencias suplementarias duplicadas')
            nombres.add(nombre)
            for entry in package['texts']:
                raw = entry['path']
                if not isinstance(raw, str) or not raw:
                    raise ValueError('ruta de licencia vacía')
                relativa = PureWindowsPath(raw)
                partes = raw.replace('\\', '/').split('/')
                if (relativa.drive or relativa.root or any(p in ('', '.', '..') or p.endswith(('.', ' '))
                        or re.search(r'[<>:"|?*\x00-\x1f]', p) or PureWindowsPath(p).is_reserved() for p in partes)
                        or partes[0].casefold() == 'manifest.json'):
                    raise ValueError(f'ruta de licencia Windows inválida: {raw}')
                clave = '/'.join(partes).casefold()
                digest = entry['sha256']
                if (not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                        or not isinstance(entry.get('source_sha256'), str)
                        or not re.fullmatch('[0-9a-f]{64}', entry['source_sha256'])
                        or not isinstance(entry.get('source_url'), str) or not entry['source_url'].startswith('https://')):
                    raise ValueError(f'huella o procedencia de licencia inválida: {raw}')
                if clave in destinos and destinos[clave] != (raw, digest):
                    raise ValueError(f'colisión Windows de licencias: {raw}')
                if any(clave.startswith(k + '/') or k.startswith(clave + '/') for k in destinos):
                    raise ValueError(f'colisión archivo/carpeta de licencia: {raw}')
                destinos[clave] = (raw, digest)
                ruta = base.joinpath(*partes).resolve()
                if not ruta.is_relative_to(base) or not ruta.is_file():
                    raise ValueError(f'ruta de licencia fuera del inventario o sin fichero: {raw}')
                # Varias ruedas pueden compartir exactamente el mismo texto; no se duplica ni se renombra.
                if raw not in textos:
                    if _sha256(ruta) != digest or not ruta.read_text(encoding='utf-8').strip():
                        raise ValueError(f'huella de licencia distinta o texto vacío: {raw}')
                    textos[raw] = ruta
        return packages, textos
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CE.EntregaError(f'Licencias suplementarias incompletas o alteradas: {exc}') from exc


def leer_metadatos_de_rueda(rueda: Path, *, licencias: Path | None = None) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Nombre, versión, licencia y los textos de licencia que trae la propia rueda."""
    with zipfile.ZipFile(rueda) as z:
        nombres = z.namelist()
        meta = next(n for n in nombres if n.endswith('.dist-info/METADATA') and n.count('/') == 1)
        m = email.message_from_bytes(z.read(meta), policy=policy.default)
        # Si no, un paquete que declara su licencia en clasificadores quedaba como «desconocida» en el inventario.
        clasificadas = [v.split('::')[-1].strip() for v in (m.get_all('Classifier') or ()) if v.startswith('License ::')]
        cabecera = (m.get('License') or '').strip().splitlines()
        licencia = m.get('License-Expression') or '; '.join(clasificadas) or (cabecera[0][:120] if cabecera else '') or 'desconocida'
        textos = [(n, z.read(n).decode('utf-8', 'replace')) for n in nombres
                  if '.dist-info/' in n and re.search(r'(^|/)(?:[^/]*[-_.])?(licen[cs]e|copying|notice)[^/]*$', n, re.I) and not n.endswith('/')]
    if licencias is not None:
        try:
            packages, fuentes = _licencias_suplementarias(licencias)
            matching = [p for p in packages if p['name'].lower().replace('_', '-') == m['Name'].lower().replace('_', '-')]
            if len(matching) > 1:
                raise ValueError('licencias suplementarias duplicadas')
            if matching:
                package = matching[0]
                if package['version'] != m['Version'] or package['wheel_sha256'] != _sha256(rueda):
                    raise ValueError(f'versión o huella de rueda distinta: {m["Name"]}')
                if not package['license'].strip() or package['license'] == 'desconocida' or not package['texts']:
                    raise ValueError('identificador o textos de licencia ausentes')
                for entry in package['texts']:
                    text = fuentes[entry['path']].read_text(encoding='utf-8')
                    textos.append((f'suplementaria/{entry["path"]}', text))
                if licencia == 'desconocida':
                    licencia = package['license']
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CE.EntregaError(f'Licencias suplementarias incompletas o alteradas: {exc}') from exc
    return {'name': m['Name'], 'version': m['Version'], 'license': licencia, 'summary': m.get('Summary') or ''}, textos


def sbom(componentes: list[dict[str, Any]], version: str, revision: str) -> dict[str, Any]:
    """CycloneDX 1.5, generado sin dependencias nuevas: solo lista lo que de verdad se entrega."""
    def fila(c: dict[str, Any]) -> dict[str, Any]:
        lic = c.get('license') or 'desconocida'
        return {'type': c.get('tipo', 'library'), 'name': c['name'], 'version': c['version'],
                **({'purl': f'pkg:pypi/{c["name"].lower()}@{c["version"]}'} if c.get('tipo', 'library') == 'library' and not c.get('sin_purl') else {}),
                **({'hashes': [{'alg': 'SHA-256', 'content': c['sha256']}]} if c.get('sha256') else {}),
                **({'externalReferences': [{'type': 'vcs' if c.get('commit_id') else 'distribution', 'url': c['source_url']}]} if c.get('source_url') else {}),
                **({'properties': [{'name': 'git_commit', 'value': c['commit_id']}]} if c.get('commit_id') else {}),
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


def extraer_python_pf(zip_embebido: Path, destino: Path, *, sha_zip: str) -> str:
    """103:RF-6: un Python de PowerFactory (3.9 a 3.11) como el del programa: sin ``._pth``.

    Con el ``._pth`` el Python embebido ignora PYTHONPATH y el guion no encuentra ni la API ni el paquete del conversor
    (2026-11-11, con el 3.9 de PowerFactory 2021). Se comprueba con su SHA-256 antes de usarlo.
    """
    if _sha256(zip_embebido) != sha_zip:
        raise CE.EntregaError(f'{zip_embebido.name} no tiene el SHA-256 fijado en config/entrega.json.')
    m = re.fullmatch(r'python-(3\.\d+)\.\d+-embed-amd64\.zip', zip_embebido.name)
    if not m:
        raise CE.EntregaError(f'Se espera un Python embebido de 64 bits de python.org, y esto es {zip_embebido.name}.')
    with zipfile.ZipFile(zip_embebido) as z:
        z.extractall(destino)
    for pth in destino.glob('*._pth'):
        pth.unlink()
    (destino / 'Lib' / 'site-packages').mkdir(parents=True, exist_ok=True)
    return m.group(1)


def preparar_python_pf(zip_embebido: Path, rueda_numpy: Path, destino: Path, *, sha_zip: str, sha_rueda: str) -> str:
    """El Python de PowerFactory con su ``numpy`` ya puesto: lo que deja el instalador (para la máquina de pruebas)."""
    version = extraer_python_pf(zip_embebido, destino, sha_zip=sha_zip)
    if _sha256(rueda_numpy) != sha_rueda:
        raise CE.EntregaError(f'{rueda_numpy.name} no tiene el SHA-256 fijado en config/entrega.json.')
    with zipfile.ZipFile(rueda_numpy) as z:
        z.extractall(destino / 'Lib' / 'site-packages')
    return version


def empaquetar_python_pf(origen: Path, terceros: Path, fijados: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """103:RF-6: cada Python de PowerFactory en ``terceros/python_pf/<versión>`` y su ``numpy`` como rueda.

    ``numpy`` va como rueda y se descomprime al instalar: descomprimido trae datos ``.npz`` de sus pruebas, que el
    manifiesto veda como pesos, y así se instala igual que las ruedas del Python del programa (por su huella).
    """
    destino = terceros / 'python_pf'
    ruedas = destino / 'ruedas'
    ruedas.mkdir(parents=True, exist_ok=True)
    componentes, huellas = [], {}
    for version, f in sorted(fijados.items()):
        zip_embebido = origen / f['zip']
        rueda = next((c for c in (origen / f['numpy'], origen / 'ruedas' / f['numpy']) if c.is_file()), origen / f['numpy'])
        if not zip_embebido.is_file() or not rueda.is_file():
            raise CE.EntregaError(f'Falta en {origen} el Python {version} o su numpy ({f["zip"]}, {f["numpy"]}).')
        if _sha256(rueda) != f['numpy_sha256']:
            raise CE.EntregaError(f'{rueda.name} no tiene el SHA-256 fijado en config/entrega.json.')
        completa = extraer_python_pf(zip_embebido, destino / version, sha_zip=f['sha256'])
        shutil.copyfile(rueda, ruedas / rueda.name)
        huellas[version] = {'numpy': rueda.name, 'sha256': f['numpy_sha256']}
        componentes.append({'name': 'CPython', 'version': f['zip'].split('-')[1], 'license': 'PSF-2.0', 'origen': 'embebido',
                            'sha256': f['sha256'], 'sin_purl': True, 'uso': f'API de PowerFactory con Python {completa}'})
        componentes.append({'name': 'numpy', 'version': rueda.name.split('-')[1], 'license': 'BSD-3-Clause', 'origen': 'python',
                            'sha256': f['numpy_sha256'], 'uso': f'Python {completa} de PowerFactory'})
    (destino / 'huellas.json').write_text(json.dumps(huellas, ensure_ascii=False, indent=1), encoding='utf-8')
    return componentes


def construir_candidato(raiz: Path, salida: Path, zip_python: Path, *, cache: Path | None = None, version: str | None = None,
                        lista_local: Path | None = None, python_pf: Path | None = None) -> tuple[dict[str, Any], CE.Informe]:
    if salida.exists() and any(salida.iterdir()):
        raise CE.EntregaError(f'La carpeta {salida} no está vacía: un candidato no se arma sobre otro.')
    manifiesto = CE.leer_manifiesto(raiz / 'config' / 'entrega.json')
    terminos = CE.cargar_terminos(raiz, manifiesto, lista_local=lista_local)
    if not LOCK.is_file():
        raise CE.EntregaError(f'Falta {LOCK.name}: genérelo con la orden «lock».')
    # 086:RF-92: sin «--version», la del paquete; con ella es un ensayo de actualización, que no tiene notas propias.
    prevista = version or version_del_paquete(raiz)
    if version is None:
        comprobar_notas((raiz / NOTAS_DEL_PAQUETE).read_text(encoding='utf-8'), prevista)        # 086:RF-93
    faltan = [rel for rel in documentos_del_candidato(prevista) if not (raiz / rel).is_file()]
    if faltan:                                                                                  # 086:RF-91, antes de construir
        raise CE.EntregaError('Faltan documentos que se instalan con el programa: ' + ', '.join(faltan) + '.')
    rueda, cuenta = construir_rueda(raiz, salida / 'programa', manifiesto, terminos, version=version)
    version_final = rueda.name.split('-')[1]
    if version_final != prevista:
        raise CE.EntregaError(f'La rueda salió con la versión {version_final} y el paquete dice {prevista}.')
    ruedas = salida / 'terceros' / 'wheels'
    traer_ruedas(raiz, ruedas, raiz / LOCK.name, cache)
    version_python = extraer_python(zip_python, salida / 'terceros' / 'python')
    # 103:RF-6: sin los Python de PowerFactory 2021 a 2023 no se arma el candidato: el operador no instala nada.
    fijados = manifiesto['candidato'].get('python_pf') or {}
    if fijados and python_pf is None:
        raise CE.EntregaError('Faltan los Python de PowerFactory: indique su carpeta con --python-pf (103:RF-6).')
    componentes_pf = empaquetar_python_pf(python_pf, salida / 'terceros', fijados) if fijados else []
    # El lock más la rueda propia: pip la instala por su huella como a las demás.
    (salida / 'terceros' / 'instalacion.lock').write_text(
        (raiz / LOCK.name).read_text(encoding='utf-8')
        + f'convertersmartgrid=={version_final} \\\n    --hash=sha256:{_sha256(rueda)}\n', encoding='utf-8', newline='\n')
    instalador = salida / 'instalador'
    instalador.mkdir()
    shutil.copyfile(raiz / 'tools' / 'instalar_candidato.py', instalador / 'instalar_candidato.py')
    shutil.copyfile(raiz / 'instalador' / 'ConverterSmartGrid.iss', instalador / 'ConverterSmartGrid.iss')
    documentos = salida / 'documentos'
    copiar_documentos(raiz, documentos, version_final)                                         # 086:RF-89
    componentes: list[dict[str, Any]] = []
    textos: dict[str, list[tuple[str, str]]] = {}
    for r in sorted(ruedas.glob('*.whl')):
        meta, licencias = leer_metadatos_de_rueda(r)
        componentes.append({**meta, 'sha256': _sha256(r), 'origen': 'python'})
        textos[f'{meta["name"]} {meta["version"]}'] = licencias
    componentes.append({'name': 'CPython', 'version': version_python, 'license': 'PSF-2.0', 'origen': 'embebido', 'sha256': _sha256(zip_python), 'sin_purl': True})
    componentes += componentes_pf                                                     # 103:RF-6
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


def _leer_lock_nucleo(ruta: Path) -> dict[str, tuple[str, set[str]]]:
    """086:RF-39: la autoridad es el lock previo, incluidos todos sus SHA256 permitidos."""
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    env = {**default_environment(), 'extra': ''}
    try:
        texto = '\n'.join(l.split('#', 1)[0].rstrip() for l in ruta.read_text(encoding='utf-8').splitlines())
        filas = re.sub(r'\\\s*\n', ' ', texto).splitlines()
        core = {}
        for linea in filas:
            if not linea.strip():
                continue
            patron = r'--hash=sha256:([0-9a-fA-F]{64})(?=\s|$)'
            hashes = {h.lower() for h in re.findall(patron, linea)}
            req = Requirement(re.sub(patron, '', linea).strip())
            if req.marker and not req.marker.evaluate(env):
                continue
            specs = list(req.specifier)
            nombre = canonicalize_name(req.name)
            if (req.url or req.extras or len(specs) != 1 or specs[0].operator != '=='
                    or '*' in specs[0].version or not hashes or nombre in core):
                raise ValueError(f'requisito sin versión/huellas SHA256 únicas: {linea}')
            core[nombre] = (specs[0].version, hashes)
        if not core:
            raise ValueError('lock sin requisitos activos')
        return core
    except (OSError, ValueError) as exc:
        raise CE.EntregaError(f'Lock del núcleo incompatible o incompleto: {exc}') from exc


def _comprobar_rueda_nucleo(nombre: str, version: str, digest: str,
                            core: dict[str, tuple[str, set[str]]]) -> None:
    if nombre in core:
        pin, hashes = core[nombre]
        if version != pin:
            raise CE.EntregaError(f'Versión incompatible con el núcleo de {nombre}: {version}, esperada {pin}.')
        if digest not in hashes:
            raise CE.EntregaError(f'Huella del núcleo incompatible para {nombre}=={version}; no se autoriza otro binario.')


def seleccionar_capacidades_integrales(raiz: Path, caches: Iterable[Path], versiones: Path,
                                      procedencias: Path, *, licencias: Path | None = None) -> tuple[list[Path], dict[str, Any]]:
    """086:RF-37/39 — cierre fijado al entorno probado; no resuelve ni consulta URLs remotas.

    Las versiones capturadas no convierten un entorno de desarrollo en entrega: solo
    entran las raíces declaradas y sus transitivas con markers/extras aplicables.
    pip verifica después este cálculo por una vía independiente, sin instalar.
    """
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.tags import sys_tags
    from packaging.utils import canonicalize_name, parse_wheel_filename

    env = default_environment()
    env['extra'] = ''
    grupos = tomllib.loads((raiz / 'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies']
    grupos = {k: list(v) for k, v in grupos.items() if k != 'dev'}
    for grupo in ('motores', 'madrl', 'mcp', 'drivers'):
        grupos.setdefault(grupo, []).extend(l.split('#')[0].strip() for l in
            (raiz / f'requirements-{grupo}.txt').read_text(encoding='utf-8').splitlines()
            if l.split('#')[0].strip())
    origins_list = json.loads(procedencias.read_text(encoding='utf-8'))
    origins = {canonicalize_name(o['name']): o for o in origins_list}
    if len(origins) != len(origins_list):
        raise CE.EntregaError('Hay procedencias duplicadas para el mismo paquete.')
    pins, urls = {}, {}
    for line in versiones.read_text(encoding='utf-8').splitlines():
        line = line.split(' #')[0].strip()
        if not line or line.startswith('#'):
            continue
        req = Requirement(line)
        name = canonicalize_name(req.name)
        if req.url:
            if name not in origins:
                raise CE.EntregaError(f'Falta procedencia para {name}.')
            pin = origins[name]['version']
            urls[name] = req.url
        else:
            specs = list(req.specifier)
            if len(specs) != 1 or specs[0].operator != '==' or '*' in specs[0].version:
                raise CE.EntregaError(f'La versión capturada no es exacta: {line}')
            pin = specs[0].version
        if name in pins:
            raise CE.EntregaError(f'Versión capturada duplicada: {name}')
        pins[name] = pin
    core = _leer_lock_nucleo(raiz / LOCK.name)
    inventory = {}
    tags = set(sys_tags())
    for cache in caches:
        if not cache.is_dir():
            raise CE.EntregaError(f'Falta caché de ruedas: {cache}')
        for wheel in cache.rglob('*.whl'):
            name, ver, _, wheel_tags = parse_wheel_filename(wheel.name)
            if pins.get(name) == str(ver) and tags & wheel_tags:
                inventory.setdefault(name, set()).add(wheel.resolve())
    roots = [Requirement(r) for values in grupos.values() for r in values]
    queue = deque(roots)
    selected, extras_seen, hashes, used_origins = {}, {}, {}, {}
    while queue:
        req = queue.popleft()
        if req.marker and not req.marker.evaluate(env):
            continue
        name = canonicalize_name(req.name)
        if name not in pins:
            raise CE.EntregaError(f'Falta versión capturada para {name}.')
        pin = pins[name]
        if pin not in req.specifier or (name in core and core[name][0] != pin):
            raise CE.EntregaError(f'Versión incompatible de {name}: {pin}, requisito {req}, núcleo {core.get(name)}.')
        source_url = req.url or urls.get(name)
        if req.url and name in urls and req.url != urls[name]:
            raise CE.EntregaError(f'URL capturada incompatible con requisito para {name}.')
        if source_url or ('+' in pin and name == 'torch'):
            origin = origins.get(name, {})
            if origin.get('version') != pin or not re.fullmatch(r'[0-9a-f]{64}', origin.get('sha256', '')):
                raise CE.EntregaError(f'Falta procedencia trazable para {name} {pin}.')
            if source_url:
                git = re.fullmatch(r'git\+(https://[^@]+)@([0-9a-f]{40})', source_url)
                if not git or origin.get('url') != git[1] or origin.get('commit_id') != git[2]:
                    raise CE.EntregaError(f'URL o commit de procedencia incompatible para {name}.')
            elif not origin.get('url', '').startswith(('https://download.pytorch.org/whl/', 'https://download-r2.pytorch.org/whl/')):
                raise CE.EntregaError('Falta URL oficial de procedencia de torch CUDA.')
            used_origins[name] = origin
        if name not in selected:
            candidates = inventory.get(name, set())
            if name in used_origins:
                candidates = {w for w in candidates if w.name == used_origins[name].get('wheel')}
            if len(candidates) > 1:
                # Las caches ya existentes pueden contener la misma rueda; no se
                # exige copiarlas para deduplicar, pero dos binarios distintos fallan.
                fingerprints = {_sha256(w) for w in candidates}
                if len(fingerprints) == 1:
                    candidates = {min(candidates, key=str)}
            if len(candidates) != 1:
                raise CE.EntregaError(f'Falta rueda compatible única para {name}=={pin}: {len(candidates)} candidatas.')
            wheel = next(iter(candidates))
            meta, licenses = leer_metadatos_de_rueda(wheel, licencias=licencias)
            if canonicalize_name(meta['name']) != name or meta['version'] != pin:
                raise CE.EntregaError(f'Metadatos incompatibles con nombre de rueda: {wheel.name}')
            if meta['license'] == 'desconocida' or not licenses or not any(text.strip() for _, text in licenses):
                raise CE.EntregaError(f'Falta licencia declarada o texto de licencia de {name}.')
            with zipfile.ZipFile(wheel) as archive:
                metadata = email.message_from_bytes(archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA') and n.count('/') == 1)))
            if metadata.get('Requires-Python') and env['python_full_version'] not in SpecifierSet(metadata['Requires-Python']):
                raise CE.EntregaError(f'Python incompatible para {name}: {metadata["Requires-Python"]}')
            hashes[name] = _sha256(wheel)
            _comprobar_rueda_nucleo(name, pin, hashes[name], core)
            if name in used_origins and hashes[name] != used_origins[name]['sha256']:
                raise CE.EntregaError(f'Huella de procedencia incompatible para {name}.')
            selected[name] = (wheel, metadata)
        elif name in used_origins and hashes[name] != used_origins[name]['sha256']:
            raise CE.EntregaError(f'Huella de procedencia incompatible para {name}.')
        solicitados = {canonicalize_name(e) for e in req.extras}
        declarados = {canonicalize_name(e) for e in selected[name][1].get_all('Provides-Extra') or []}
        if faltan := solicitados - declarados:
            raise CE.EntregaError(f'Extra no declarado de {name}=={pin}: {", ".join(sorted(faltan))}.')
        extras = solicitados | {''}
        unseen = extras - extras_seen.get(name, set())
        if not unseen:
            continue
        extras_seen.setdefault(name, set()).update(unseen)
        for dependency in selected[name][1].get_all('Requires-Dist') or []:
            child = Requirement(dependency)
            if not child.marker or any(child.marker.evaluate({**env, 'extra': extra}) for extra in unseen):
                if child.url:
                    raise CE.EntregaError(f'Dependencia con URL remota no admitida: {name}: {dependency}')
                child.marker = None
                queue.append(child)
    resolved_roots = []
    for root in roots:
        if not root.marker or root.marker.evaluate(env):
            extra = '[' + ','.join(sorted(root.extras)) + ']' if root.extras else ''
            resolved_roots.append(f'{canonicalize_name(root.name)}{extra}=={pins[canonicalize_name(root.name)]}')
    coverage = {'destino': {'python': env['python_full_version'], 'plataforma': 'win_amd64'},
        'grupos': grupos, 'versiones_capturadas_sha256': _sha256(versiones),
        'raices_resueltas': sorted(set(resolved_roots)),
        'procedencias_sha256': _sha256(procedencias), 'core_lock_sha256': _sha256(raiz / LOCK.name),
        **({'licencias_suplementarias_sha256': _sha256(licencias)} if licencias else {}),
        'procedencias': [used_origins[n] for n in sorted(used_origins)],
        'ruedas': [{'name': n, 'version': pins[n], 'wheel': selected[n][0].name, 'sha256': hashes[n]}
                   for n in sorted(selected)], 'aceptacion_cientifica': False, 'proyecto_completo': False}
    return [selected[n][0] for n in sorted(selected)], coverage


def _procedencia_publicada(origen: dict[str, Any], base_recibos: Path) -> dict[str, Any]:
    """086:RF-39/44: publica identidad verificable, sin rutas privadas del constructor.

    El SHA del recibo identifica sus bytes originales, no este descriptor. El JSON
    de procedencias de entrada conserva la ruta externa y su propia huella.
    """
    publica = {key: origen[key] for key in
               ('name', 'version', 'url', 'commit_id', 'wheel', 'sha256', 'receipt_sha256') if key in origen}
    if 'commit_id' in origen and (not isinstance(origen['commit_id'], str)
                                  or not re.fullmatch(r'[0-9a-f]{40}', origen['commit_id'])):
        raise CE.EntregaError('El commit de procedencia declarado no es un SHA40 válido.')
    if 'official_index_hash_verified' in origen:
        if type(origen['official_index_hash_verified']) is not bool:
            raise CE.EntregaError('Indicador de procedencia del índice oficial no booleano.')
        publica['official_index_hash_verified'] = origen['official_index_hash_verified']
    if 'receipt' in origen or 'receipt_sha256' in origen:
        raw, expected = origen.get('receipt'), origen.get('receipt_sha256')
        if (not isinstance(raw, str) or not raw.strip() or not isinstance(expected, str)
                or not re.fullmatch(r'[0-9a-f]{64}', expected)):
            raise CE.EntregaError('Recibo de procedencia incompleto o sin huella SHA256 válida.')
        path = Path(raw)
        if not path.is_absolute():
            path = base_recibos / path
        try:
            actual = _sha256(path)
        except OSError as exc:
            raise CE.EntregaError('No se puede leer el recibo de procedencia autorizado.') from exc
        if actual != expected:
            raise CE.EntregaError('Recibo de procedencia alterado: su huella no coincide con la autorizada.')
        publica['receipt'] = {'kind': 'external-file', 'sha256': actual}
    return publica


def construir_complemento_ia(raiz: Path, salida: Path, *, cache: Path, version: str,
                            capacidades: str = 'inferencia', versiones: Path | None = None,
                            procedencias: Path | None = None, caches_adicionales: Iterable[Path] = (),
                            licencias: Path | None = None) -> dict[str, Any]:
    """086:RF-37/39 — cierre offline de inferencia, independiente del núcleo y sin pesos propios."""
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        raise CE.EntregaError('El complemento requiere construir con CPython3.12 Windows64.')
    if salida.exists() and any(salida.iterdir()):
        raise CE.EntregaError(f'La carpeta {salida} no está vacía: no se pisa otro paquete.')
    if not cache.is_dir():
        raise CE.EntregaError('Falta la caché explícita de ruedas del complemento.')
    if capacidades not in ('inferencia', 'integrales'):
        raise CE.EntregaError(f'Capacidades desconocidas: {capacidades}')
    seleccion, cobertura = [], None
    if capacidades == 'integrales':
        if versiones is None or procedencias is None:
            raise CE.EntregaError('Las capacidades integrales requieren versiones capturadas y procedencias explícitas.')
        seleccion, cobertura = seleccionar_capacidades_integrales(raiz, [cache, *caches_adicionales], versiones, procedencias, licencias=licencias)
        from packaging.requirements import Requirement
        # También se publican las raíces inactivas en grupos/requisitos-declarados:
        # sus URLs deben ser fuentes públicas fijadas, aunque no entren al cierre Win.
        for declarations in cobertura['grupos'].values():
            for declaration in declarations:
                url = Requirement(declaration).url
                if url and not re.fullmatch(r'git\+https://[^@\s\\]+@[0-9a-f]{40}', url):
                    raise CE.EntregaError('Fuente URL declarada no publicable: requiere Git HTTPS y commit completo.')
    cobertura_publicada = ({**cobertura, 'procedencias': [
        _procedencia_publicada(origin, procedencias.parent) for origin in cobertura['procedencias']]}
        if cobertura else None)
    core = _leer_lock_nucleo(raiz / LOCK.name)
    limites = [f'{nombre}=={pin}' for nombre, (pin, _hashes) in core.items()]
    _, textos_suplementarios = _licencias_suplementarias(licencias) if licencias else ([], {})
    salida.mkdir(parents=True, exist_ok=True)
    if licencias:
        # Se conserva el mismo recibo y sus textos para poder releer la procedencia
        # sin el checkout ni la carpeta desde la que se construyó el complemento.
        for relativa, path in textos_suplementarios.items():
            target = salida / 'licencias' / relativa
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (salida / 'licencias').mkdir(exist_ok=True)
        shutil.copyfile(licencias, salida / 'licencias' / 'manifest.json')
    ruedas = salida / 'wheels'
    ruedas.mkdir()
    if cobertura:
        (salida / 'requisitos-declarados.txt').write_text('\n'.join(r for values in cobertura['grupos'].values() for r in values) + '\n', encoding='utf-8')
        (salida / 'requisitos-resueltos.txt').write_text('\n'.join(cobertura['raices_resueltas']) + '\n', encoding='utf-8')
        (salida / 'cobertura.json').write_text(json.dumps(cobertura_publicada, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        shutil.copyfile(raiz / COMPLEMENTO_IA.name, salida / 'requisitos-declarados.txt')
    (salida / 'limites-nucleo.txt').write_text('\n'.join(limites) + '\n', encoding='utf-8')
    if cobertura:
        for wheel in seleccion:
            shutil.copyfile(wheel, ruedas / wheel.name)
    else:
        _pip('download', '--only-binary', ':all:', '--no-index', '--find-links', str(cache),
             '-c', str(salida / 'limites-nucleo.txt'), '-r', str(salida / 'requisitos-declarados.txt'), '-d', str(ruedas))
    filas = escribir_lock(ruedas, salida / 'instalacion.lock', complemento=True)
    for nombre, pin, digest in filas:
        _comprobar_rueda_nucleo(nombre, pin, digest, core)
    if not filas or not any(n == 'torch' for n, _, _ in filas):
        raise CE.EntregaError('El complemento no contiene torch; construcción incompleta.')
    if cobertura:
        if {(n, v, h) for n, v, h in filas} != {(r['name'], r['version'], r['sha256']) for r in cobertura['ruedas']}:
            raise CE.EntregaError('Las ruedas copiadas no coinciden con el cierre declarado.')
        _pip('install', '--dry-run', '--ignore-installed', '--no-index', '--no-cache-dir', '--only-binary', ':all:',
             '--require-hashes', '--find-links', str(ruedas), '-r', str(salida / 'instalacion.lock'),
             '-r', str(salida / 'requisitos-resueltos.txt'))
    componentes, textos = [], {}
    origenes = {o['name'].lower().replace('_', '-'): o for o in cobertura['procedencias']} if cobertura else {}
    for rueda in sorted(ruedas.glob('*.whl')):
        meta, textos_licencia = leer_metadatos_de_rueda(rueda, licencias=salida / 'licencias/manifest.json' if licencias else None)
        origin = origenes.get(meta['name'].lower().replace('_', '-'))
        componentes.append({**meta, 'sha256': _sha256(rueda), 'origen': 'git' if origin and origin.get('commit_id') else 'python',
            **({'sin_purl': True, 'source_url': origin['url'], 'commit_id': origin.get('commit_id')} if origin else {})})
        textos[f'{meta["name"]} {meta["version"]}'] = textos_licencia
    revision = _revision(raiz)
    inventario = sbom(componentes, version, revision)
    inventario['metadata']['component']['name'] = 'convertersmartgrid-complemento-ia'
    (salida / 'sbom.cdx.json').write_text(json.dumps(inventario, ensure_ascii=False, indent=2), encoding='utf-8')
    (salida / 'THIRD_PARTY_NOTICES.txt').write_text(_avisos(componentes, textos), encoding='utf-8')
    (salida / 'LEEME.txt').write_text(
        f'Complemento de IA para ConverterSmartGrid {version}, CPython3.12 Windows64.\n'
        'No incluye ni activa pesos de modelos del proyecto.\n'
        f'Capacidades: {capacidades}; véase requisitos-declarados.txt y, para integrales, cobertura.json.\n'
        'Con el programa cerrado, pruebe primero sobre una copia separada de la instalación.\n'
        'Use su Python entregado, desde esta carpeta, para instalar sin red y con huellas:\n'
        'python.exe -m pip install --no-index --require-hashes --find-links wheels -r instalacion.lock\n'
        'python.exe -m pip check\n'
        'La construcción no acredita carga de modelos, GPU ni aceptación científica.\n', encoding='utf-8')
    archivos = [{'ruta': rel, 'sha256': _sha256(r), 'bytes': r.stat().st_size} for r, rel in CE._recorrer(salida)]
    resultado = {'tipo': 'complemento-ia', 'version': version, 'revision': revision, 'python': '3.12',
                 'capacidades': capacidades, 'proyecto_completo': False,
                 'plataforma': 'win_amd64', 'pesos_del_proyecto_incluidos': False, 'modelos_activados': False,
                 'core_lock_sha256': _sha256(raiz / LOCK.name), 'ficheros': archivos,
                 'bytes_total': sum(f['bytes'] for f in archivos)}
    (salida / 'manifiesto_candidato.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    orden = parser.add_subparsers(dest='orden', required=True)
    p_rueda = orden.add_parser('rueda', help='Solo la rueda del programa.')
    p_rueda.add_argument('--salida', type=Path, required=True)
    p_rueda.add_argument('--version', help='Solo para ensayar una actualización; la de entrega es la de __version__ (086:RF-92).')
    p_lock = orden.add_parser('lock', help='Fija con huella las ruedas del núcleo; descarga del índice.')
    p_lock.add_argument('--salida', type=Path, default=LOCK)
    p_lock.add_argument('--ruedas', type=Path, help='Carpeta donde dejar las ruedas; por defecto, una temporal.')
    p_cand = orden.add_parser('candidato', help='El paquete entero.')
    p_cand.add_argument('--salida', type=Path, required=True)
    p_cand.add_argument('--python-embebido', type=Path, required=True, help='python-3.12.x-embed-amd64.zip de python.org')
    p_cand.add_argument('--python-pf', type=Path,
                        help='Carpeta con los Python embebidos y las ruedas de numpy de config/entrega.json (103:RF-6)')
    p_cand.add_argument('--ruedas-cache', type=Path, help='Carpeta con las ruedas ya descargadas; sin ella, del índice.')
    p_cand.add_argument('--version', help='Solo para ensayar una actualización; la de entrega es la de __version__ (086:RF-92).')
    p_cand.add_argument('--lista-local', type=Path, help='Lista de términos fuera de git; si no, CSG_TERMINOS_PROHIBIDOS.')
    p_ia = orden.add_parser('complemento-ia', help='Complemento separado, de inferencia o capacidades integrales, offline con lock y avisos.')
    p_ia.add_argument('--salida', type=Path, required=True)
    p_ia.add_argument('--ruedas-cache', type=Path, required=True)
    p_ia.add_argument('--version', help='Versión del núcleo compatible; por defecto, la del paquete (086:RF-92).')
    p_ia.add_argument('--capacidades', choices=('inferencia', 'integrales'), default='inferencia')
    p_ia.add_argument('--versiones-capturadas', type=Path, help='Freeze exacto del entorno integral ya verificado.')
    p_ia.add_argument('--procedencias', type=Path, help='JSON de recibos Git/CUDA: name, version, url, commit_id (Git), wheel, sha256.')
    p_ia.add_argument('--licencias-suplementarias', type=Path, help='Recibos y textos de origen versionado, fijados a las huellas de rueda y licencia.')
    p_ia.add_argument('--ruedas-cache-adicional', action='append', type=Path, default=[], help='Otra caché de ruedas existente, sin copiarla previamente.')
    args = parser.parse_args(argv)
    try:
        if args.orden == 'complemento-ia':
            resultado = construir_complemento_ia(RAIZ, args.salida, cache=args.ruedas_cache, version=args.version or version_del_paquete(RAIZ),
                capacidades=args.capacidades, versiones=args.versiones_capturadas, procedencias=args.procedencias,
                caches_adicionales=args.ruedas_cache_adicional, licencias=args.licencias_suplementarias)
            print(json.dumps({k: resultado[k] for k in ('tipo', 'version', 'revision', 'bytes_total')}
                             | {'ficheros': len(resultado['ficheros'])}, ensure_ascii=False, indent=2))
            return 0
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
        resultado, informe = construir_candidato(RAIZ, args.salida, args.python_embebido, cache=args.ruedas_cache, version=args.version, lista_local=args.lista_local,
                                                 python_pf=args.python_pf)
        print(json.dumps({k: resultado[k] for k in ('version', 'revision', 'python', 'neutralizados', 'bytes_total')} | {'ficheros': len(resultado['ficheros'])},
                         ensure_ascii=False, indent=2))
        print(json.dumps(informe.resumen(), ensure_ascii=False, indent=2))
        return 2 if informe.rechazado else 0
    except (CE.EntregaError, OSError, ValueError) as exc:
        print(f'No se pudo armar: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
