"""Arma un candidato de la entrega: rueda propia, terceros con huella, documentos y manifiesto (spec 086, RF-36 a RF-39, RF-44).

Uso:
  python tools/construir_candidato.py rueda --salida DIR [--version 1.0.0rc2]
  python tools/construir_candidato.py lock [--salida requirements-nucleo.lock]
  python tools/construir_candidato.py candidato --salida DIR --python-embebido python-3.12.x-embed-amd64.zip
                                                [--ruedas-cache DIR] [--version 1.0.0rc2]
  python tools/construir_candidato.py complemento-ia --salida DIR --ruedas-cache DIR (--modelos DIR | --sin-modelos)
      [--version VERSION]
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
import os
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
              'src/convertersmartgrid/recursos/NOTAS_VERSION.md', 'requirements-complemento-ia.txt', 'LICENSE')
#: U8 (2026-11-14): MANUAL_DE_USO no se entrega: es del 2026-10-31, remite a specs/, a MANUAL_COMANDOS y a tools/ del
#: repositorio, y no cubre la 1.0 instalada (instalador, todo activo, perfil desde la web, copia de datos, asistente).
#: Lo que falta está en specs/086-puesta-en-operacion-comercial/tasks.md, T23.
#: LIC-MIT (usuario, 2026-11-15, «MIT + comercial opcional»; sustituye a U1): la licencia del programa que se entrega es la
#: MIT del repositorio. Va a «documentos/» como LICENSE.txt y el .iss la muestra.
LICENCIA_DE_LA_ENTREGA = 'LICENSE'
#: El acuerdo comercial de soporte y garantía es OPCIONAL: se copia si está y no es condición de la entrega ni del uso.
ACUERDO_COMERCIAL_OPCIONAL = 'docs/LICENCIA_COMERCIAL.txt'
#: 086:RF-89: además, lo que el operador encuentra instalado, porque el .iss copia «documentos/» a «{app}\\documentos». El rc5
#: dejaba el candidato en «{app}\\_entrega» y lo borraba al terminar: los manuales se iban con él. Las notas de la
#: publicación no van aquí: su nombre sale de la versión, en ``documentos_del_candidato``.
#: Aclaración de 086:RF-89 (auditoría de lanzamiento, 2026-11-14): el manual de órdenes que se instala es el del programa
#: instalado (MANUAL_ORDENES); MANUAL_COMANDOS es de desarrollo, y la guía de la persona ajena es de la aceptación interna (T41).
MANUALES_INSTALADOS = ('docs/MANUAL_INSTALACION.md', 'docs/MANUAL_ORDENES.md')
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


def nombre_en_documentos(rel: str) -> str:
    """El nombre con que ``rel`` queda en «documentos/»: la MIT (``LICENSE``, sin extensión) va como LICENSE.txt."""
    return 'LICENSE.txt' if rel == LICENCIA_DE_LA_ENTREGA else Path(rel).name


def sin_secciones_de_desarrollo(texto: str, titulos: Iterable[str]) -> str:
    """Quita de un manual los apartados ``## <título>`` que son de quien construye, hasta el siguiente ``## `` (L6).

    El manual de instalación llevaba «Para quien prepara una versión» al cliente, con rutas y órdenes del repositorio.
    """
    quitar = set(titulos)
    salida, fuera = [], False
    for linea in texto.splitlines(keepends=True):
        if linea.startswith('## '):
            fuera = linea[3:].strip() in quitar
        if not fuera:
            salida.append(linea)
    return ''.join(salida).rstrip().rstrip('-').rstrip() + chr(10)


def comprobar_documentos_de_la_entrega(pedidos: Iterable[str], manifiesto: dict) -> None:
    """L6: lo que ``config/entrega.json`` dice que no va al cliente no entra en «documentos/» (manuales de desarrollo)."""
    vedados = set((manifiesto.get('documentos') or {}).get('no_se_entregan') or ())
    dentro = sorted(vedados & set(pedidos))
    if dentro:
        raise CE.EntregaError('Van a «documentos/» ficheros que config/entrega.json no deja entregar: ' + ', '.join(dentro) + '.')


def copiar_documentos(raiz: Path, destino: Path, version: str, manifiesto: dict | None = None) -> list[str]:
    """086:RF-91: copia todos o ninguno; si falta alguno, el error los nombra y no se arma el candidato."""
    pedidos = documentos_del_candidato(version)
    faltan = [rel for rel in pedidos if not (raiz / rel).is_file()]
    if faltan:
        raise CE.EntregaError('Faltan documentos que se instalan con el programa: ' + ', '.join(faltan) + '.')
    documentos = (manifiesto or {}).get('documentos') or {}
    comprobar_documentos_de_la_entrega(pedidos, manifiesto or {})
    destino.mkdir(parents=True, exist_ok=True)
    for rel in pedidos:
        secciones = (documentos.get('secciones_de_desarrollo') or {}).get(rel)
        if secciones:
            texto = sin_secciones_de_desarrollo((raiz / rel).read_text(encoding='utf-8'), secciones)
            (destino / Path(rel).name).write_text(texto, encoding='utf-8', newline='')
        elif rel == LICENCIA_DE_LA_ENTREGA:
            # LIC-MIT: la MIT va como LICENSE.txt, que es lo que muestra LicenseFile=; Inno Setup solo lee como UTF-8 un
            # .txt con su BOM.
            texto = (raiz / rel).read_text(encoding='utf-8').lstrip(chr(0xFEFF))
            (destino / nombre_en_documentos(rel)).write_text(texto, encoding='utf-8-sig', newline='')
        else:
            shutil.copyfile(raiz / rel, destino / Path(rel).name)
    copiados = [nombre_en_documentos(rel) for rel in pedidos]
    # El acuerdo comercial opcional de soporte y garantía: si está, se copia (con BOM, como la MIT); si no, la entrega vale.
    for rel in (documentos.get('opcionales') or ()):
        if (raiz / rel).is_file():
            texto = (raiz / rel).read_text(encoding='utf-8').lstrip(chr(0xFEFF))
            (destino / Path(rel).name).write_text(texto, encoding='utf-8-sig', newline='')
            copiados.append(Path(rel).name)
    return copiados


def comprobar_notas(texto: str, version: str) -> None:
    """086:RF-93: las notas del paquete empiezan por el apartado de su versión, que es lo que enseña «Acerca de»."""
    from convertersmartgrid import seccion_de_notas

    apartados = re.findall(r'^## (\S+)', texto, flags=re.M)
    if not apartados or apartados[0] != version or seccion_de_notas(texto, version) is None:
        raise CE.EntregaError(f'Las notas del paquete ({NOTAS_DEL_PAQUETE.as_posix()}) no empiezan por el apartado '
                              f'«## {version}»: «Acerca de» enseñaría las de otra versión.')


# --------------------------------------------------------------------------- rueda propia
CONJUNTO_PREGUNTA = Path('config', 'pregunta_entregada', 'CONJUNTO_ABSTENCION_ENTREGA.json')


def _secciones_de_desarrollo(raiz: Path) -> dict[str, list[str]]:
    """Las secciones de desarrollo de cada manual según config/entrega.json de ``raiz`` (vacío si no hay lista)."""
    try:
        datos = json.loads((raiz / 'config' / 'entrega.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return (datos.get('documentos') or {}).get('secciones_de_desarrollo') or {}


def documentos_de_pregunta(raiz: Path, programa: Path, version: str, *, calibrar: bool) -> dict[str, Any] | None:
    """Los manuales y notas que se entregan, dentro del paquete, para que «pregunta» los lea en el instalado.

    Con ``calibrar``, además la abstención sobre ellos (asistente/pregunta_entregada.py, 097:RF-19): se arma sin
    internet y sin GPU, con BM25. El candidato la exige; una rueda suelta de ensayo no.
    """
    from convertersmartgrid.asistente import pregunta_entregada as PE

    carpeta = programa / PE.CARPETA
    carpeta.mkdir(parents=True, exist_ok=True)
    # Los manuales y notas del operador; MANUAL_COMANDOS y la guía de la persona ajena no, porque describen el entorno de
    # desarrollo y la aceptación interna, y el primero aún nombra alimentadores reales (auditoría de lanzamiento, 6).
    # Lo que «pregunta» lee y calibra es lo que llega al cliente: sin las secciones de desarrollo de un manual, que
    # copiar_documentos ya quita (086:RF-91). Entraban en su corpus y en su calibración: «Para quien prepara una versión»
    # era un fragmento casi vacío con el que casaban preguntas ajenas («¿Cómo se prepara…?»).
    secciones = _secciones_de_desarrollo(raiz)
    for rel in (*DOCUMENTOS, f'docs/NOTAS_VERSION_{publicacion(version)}.md'):
        if rel.endswith('.md') and (raiz / rel).is_file():
            if secciones.get(rel):
                texto = sin_secciones_de_desarrollo((raiz / rel).read_text(encoding='utf-8'), secciones[rel])
                (carpeta / Path(rel).name).write_text(texto, encoding='utf-8', newline='')
            else:
                shutil.copyfile(raiz / rel, carpeta / Path(rel).name)
    if (raiz / CONJUNTO_PREGUNTA).is_file():
        shutil.copyfile(raiz / CONJUNTO_PREGUNTA, carpeta / PE.CONJUNTO)
    if not calibrar:
        return None
    try:
        return PE.calibrar(programa)
    except (ImportError, AttributeError) as exc:
        raise CE.EntregaError(f'La calibración de «pregunta» necesita la muestra mínima y la comprobación de fugas de la '
                              f'evaluación del asistente, que no están en este árbol: {exc}') from exc
    except ValueError as exc:
        raise CE.EntregaError(f'No se pudo calibrar «pregunta» sobre los documentos que se entregan: {exc}') from exc


def preparar_arbol(raiz: Path, arbol: Path, manifiesto: dict, terminos: CE.Terminos, *, version: str | None = None,
                   dist: Path | None = None, calibrar_pregunta: bool = False) -> dict[str, int]:
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
    calibrado = documentos_de_pregunta(raiz, arbol / PROGRAMA_EN_PAQUETE, version or version_del_paquete(raiz),
                                       calibrar=calibrar_pregunta)
    if calibrado:
        cuenta['pregunta_umbral_bm25'] = calibrado['umbrales']['bm25_solo']
    return cuenta


def construir_rueda(raiz: Path, salida: Path, manifiesto: dict, terminos: CE.Terminos, *, version: str | None = None,
                    dist: Path | None = None, calibrar_pregunta: bool = False) -> tuple[Path, dict[str, int]]:
    """Sin aislamiento: con setuptools del entorno, para no salir a internet a por él en cada construcción."""
    salida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='csg-rueda-') as temporal:
        arbol = Path(temporal) / 'arbol'
        cuenta = preparar_arbol(raiz, arbol, manifiesto, terminos, version=version, dist=dist,
                                calibrar_pregunta=calibrar_pregunta)
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


def _avisos(componentes: list[dict[str, Any]], textos: dict[str, list[tuple[str, str]]], anexo: str = '') -> str:
    partes = ['THIRD_PARTY_NOTICES: ConverterSmartGrid incluye estos componentes de terceros.',
              'Inventario técnico generado de sus metadatos: no es una opinión legal (086, D7).', '']
    partes += [f'{c["name"]} {c["version"]} [{c.get("origen", "python")}]: {c.get("license", "desconocida")}' for c in componentes]
    for nombre, lista in sorted(textos.items()):
        for ruta, texto in lista:
            partes += ['', '=' * 78, f'{nombre}: {ruta}', '=' * 78, texto.strip()]
    if anexo:
        partes += ['', anexo.strip()]
    return '\n'.join(partes) + '\n'


# --------------------------------------------------------------------------- avisos que no vienen en una rueda
#: 086:RF-44: textos de los modelos, de Ollama, de NVIDIA y de vcruntime, con su huella y su fuente (auditoría de
#: lanzamiento, 2026-11-14: el rc6 no traía el texto de NVIDIA de las 37 DLL de CUDA de torch, ni los de OpenSSL, SQLite,
#: expat, liblzma y zlib del Python propio, ni dónde está el código fuente de GEOS, iconv, libpq, moocore y FFmpeg).
LICENCIAS_TERCEROS = Path('config', 'licencias_terceros', 'manifest.json')


def _con_licencias(raiz: Path) -> Path:
    """Los textos son de la herramienta que construye: un árbol de ensayo sin ellos usa los de este checkout."""
    return raiz if (raiz / LICENCIAS_TERCEROS).is_file() else RAIZ


def textos_de_terceros(raiz: Path) -> dict[str, dict[str, Any]]:
    """Cada texto por su id, comprobado por sus bytes; uno que no permite redistribuir no entra en ningún paquete."""
    raiz = _con_licencias(raiz)
    try:
        datos = json.loads((raiz / LICENCIAS_TERCEROS).read_text(encoding='utf-8'))
        salida = {}
        for t in datos['textos']:
            ruta = raiz / LICENCIAS_TERCEROS.parent / t['fichero']
            if _sha256(ruta) != t['sha256']:
                raise ValueError(f'{t["fichero"]} no tiene la huella declarada')
            if t.get('redistribuir') is not True:
                raise ValueError(f'{t["id"]}: su licencia no permite redistribuirlo, no se empaqueta')
            salida[t['id']] = {**t, 'texto': ruta.read_text(encoding='utf-8')}
        return salida
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CE.EntregaError(f'Licencias de terceros incompletas o alteradas ({LICENCIAS_TERCEROS.as_posix()}): {exc}') from exc


def _manifiesto_terceros(raiz: Path) -> dict[str, Any]:
    raiz = _con_licencias(raiz)
    try:
        return json.loads((raiz / LICENCIAS_TERCEROS).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CE.EntregaError(f'No se puede leer {LICENCIAS_TERCEROS.as_posix()}: {exc}') from exc


def _con_cita(t: dict[str, Any]) -> list[tuple[str, str]]:
    return [(t['fichero'], f'Licencia: {t["licencia"]}. Fuente: {t["fuente"]}\n{t["cita"]}\n\n{t["texto"]}')]


def _nativas(nombres: Iterable[str]) -> list[str]:
    return sorted({PureWindowsPath(n).name for n in nombres if n.lower().endswith(('.dll', '.pyd', '.so'))})


def dll_de_rueda(rueda: Path) -> list[str]:
    with zipfile.ZipFile(rueda) as z:
        return _nativas(z.namelist())


def avisos_nvidia(raiz: Path, contenedores: dict[str, list[str]]) -> dict[str, list[tuple[str, str]]]:
    """El texto de NVIDIA de cada DLL de CUDA o cuDNN, con qué contenedor la trae (086:RF-44)."""
    reglas = _manifiesto_terceros(raiz)['nvidia']
    halladas: dict[str, list[str]] = {}
    for contenedor, dlls in sorted(contenedores.items()):
        for dll in dlls:
            for id_texto, patron in reglas.items():
                if re.search(patron, PureWindowsPath(dll).name, re.I):
                    halladas.setdefault(id_texto, []).append(f'{contenedor}: {dll}')
                    break
    if not halladas:
        return {}
    textos = textos_de_terceros(raiz)
    salida = {}
    for id_texto, lista in sorted(halladas.items()):
        t = textos[id_texto]
        salida[f'NVIDIA {t["licencia"]}'] = [(t['fichero'], 'Se aplica a:\n' + '\n'.join(f'  {x}' for x in lista) + '\n\n'
                                              + _con_cita(t)[0][1])]
    return salida


def avisos_nativos(raiz: Path, python: Path) -> dict[str, list[tuple[str, str]]]:
    """Las licencias de las bibliotecas que trae el Python propio, su procedencia y vcruntime (086:RF-44)."""
    salida: dict[str, list[tuple[str, str]]] = {}
    for texto in sorted((python / 'native_licenses').glob('*.txt')):
        salida[f'Python: {texto.stem}'] = [(f'native_licenses/{texto.name}', texto.read_text(encoding='utf-8', errors='replace'))]
    procedencia = python / 'RUNTIME_PROVENANCE.json'
    if procedencia.is_file():
        salida['Python: procedencia del runtime'] = [('RUNTIME_PROVENANCE.json', procedencia.read_text(encoding='utf-8', errors='replace'))]
    if any(python.glob('vcruntime140*.dll')):
        salida['Microsoft vcruntime'] = _con_cita(textos_de_terceros(raiz)['vcruntime'])
    return salida


def fuentes_lgpl(raiz: Path, ruedas: Iterable[Path]) -> str:
    """El apartado «Código fuente de componentes LGPL» de los avisos, de las DLL que de verdad van en el paquete.

    Una DLL de una biblioteca LGPL en una rueda o versión que no está declarada para el paquete: no se arma, en vez de
    entregar una LGPL sin decir dónde está su fuente.
    """
    datos = _manifiesto_terceros(raiz)
    patrones = {e['dll'] for e in datos['lgpl']}
    filas, faltan = [], []
    for rueda in sorted(ruedas, key=lambda r: r.name):
        nombre, version = _nombre_y_version(rueda.name)
        for dll in dll_de_rueda(rueda):
            for patron in sorted(patrones):
                if not dll.lower().startswith(patron.lower()):
                    continue
                e = next((e for e in datos['lgpl'] if e['rueda'] == nombre and e['version_rueda'] == version
                          and e['dll'] == patron), None)
                if e is None:
                    faltan.append(f'{nombre} {version}: {dll}')
                elif e not in filas:
                    filas.append(e)
    if faltan:
        raise CE.EntregaError('Bibliotecas LGPL sin su fuente declarada en ' + LICENCIAS_TERCEROS.as_posix() + ': '
                              + ', '.join(faltan) + '.')
    if not filas:
        return ''
    lineas = ['=' * 78, 'Código fuente de componentes LGPL', '=' * 78, datos['oferta_lgpl'], '']
    lineas += [f'- {e["componente"]} ({e["licencia"]}), en {e["rueda"]} {e["version_rueda"]}: {e["fuente"]}' for e in filas]
    return '\n'.join(lineas)


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


# --------------------------------------------------------------------------- lanzamiento: final, Python oficial, firma, auditoría y sumas
class Avisos(list):
    """Lo que en un candidato de prueba solo se avisa y en el final es un error (086:RF-33, RF-39; U2, U3, L1, L5)."""

    def __init__(self, final: bool):
        super().__init__()
        self.final = final

    def falta(self, mensaje: str) -> None:
        if self.final:
            raise CE.EntregaError(mensaje)
        self.append(mensaje)


def firmas_authenticode(rutas: Iterable[Path]) -> dict[str, tuple[str, str]]:
    """Estado y firmante Authenticode de cada fichero, con PowerShell (``Get-AuthenticodeSignature``), sin instalar nada."""
    rutas = [str(Path(r).resolve()) for r in rutas]
    if not rutas:
        return {}
    orden = ('$ErrorActionPreference="Stop"; $r=@(); foreach($f in ($env:CSG_RUTAS_FIRMA -split [char]10)){$s=Get-AuthenticodeSignature -LiteralPath $f; '
             '$r+=[pscustomobject]@{ruta=$f;estado=[string]$s.Status;firmante=[string]$s.SignerCertificate.Subject}}; '
             'ConvertTo-Json -InputObject $r -Compress')
    import os

    # Las rutas van por el entorno: con «-Command», PowerShell no pasa a $args lo que sigue a la orden.
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', orden],
                       env={**os.environ, 'CSG_RUTAS_FIRMA': chr(10).join(rutas)},
                       capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    if r.returncode:
        raise CE.EntregaError(f'No se pudo leer la firma Authenticode: {r.stderr.strip()[-500:]}')
    datos = json.loads(r.stdout or '[]')
    datos = datos if isinstance(datos, list) else [datos]
    return {Path(d['ruta']).name: (d['estado'], d['firmante'] or '') for d in datos}


def verificar_python_oficial(zip_python: Path, carpeta: Path, fijado: dict[str, Any], avisos: Avisos, *,
                             leer_firmas=firmas_authenticode) -> None:
    """U3: el Python del programa es el oficial de python.org que fija la lista, con la firma de la PSF en sus binarios.

    El rc6 llevaba un 3.12.16 compilado aquí, sin firma: el intérprete que ejecuta todo el programa iba sin firmar
    (auditoría de lanzamiento, 2026-11-14). En un candidato de prueba se avisa; en el final es un error.
    """
    if not fijado:
        avisos.falta('config/entrega.json no fija el Python del programa (python_programa).')
        return
    if zip_python.name != fijado['zip'] or _sha256(zip_python) != fijado['sha256']:
        avisos.falta(f'El Python del programa no es el fijado ({fijado["zip"]}, de {fijado.get("origen", "python.org")}).')
        return
    firmas = leer_firmas([carpeta / n for n in fijado.get('firmados') or ()])
    malas = [n for n in fijado.get('firmados') or ()
             if firmas.get(n, ('', ''))[0] != 'Valid' or f'CN={fijado["firmante"]}' not in firmas.get(n, ('', ''))[1]]
    if malas:
        avisos.falta(f'Sin la firma válida de {fijado["firmante"]}: {", ".join(malas)}.')


def auditar_dependencias(raiz: Path, lock: Path, destino: Path, configuracion: dict[str, Any], avisos: Avisos, *,
                         ejecutar=subprocess.run, entorno: dict[str, str] | None = None) -> dict[str, Any]:
    """L5: pip-audit sobre el lock final, con el pip-audit de un entorno aparte (nunca el .venv del desarrollo).

    Una vulnerabilidad sin justificar en el fichero declarado rechaza el candidato, de prueba o final; sin pip-audit,
    el de prueba lo avisa y el final no se arma. El resultado queda en ``destino`` (va en «documentos/»).
    """
    import os

    entorno = dict(os.environ) if entorno is None else entorno
    variable = configuracion.get('variable') or 'CSG_PIP_AUDIT'
    programa = entorno.get(variable, '').strip()
    justificadas_rel = configuracion.get('justificadas') or 'config/vulnerabilidades_justificadas.json'
    justificadas = {(j['id'], j['paquete'].lower()) for j in
                    json.loads((raiz / justificadas_rel).read_text(encoding='utf-8')).get('justificadas') or ()}
    if not programa:
        avisos.falta(f'Falta pip-audit: indique en {variable} el pip-audit de un entorno aparte (L5, 086:RF-39).')
        return {'auditado': False}
    with tempfile.TemporaryDirectory(prefix='csg-audit-') as temporal:
        # Sin la rueda propia, que no está en PyPI; con huellas y sin resolver, como se instala.
        pedido = Path(temporal) / 'lock.txt'
        pedido.write_text(lock.read_text(encoding='utf-8'), encoding='utf-8')
        r = ejecutar([programa, '-r', str(pedido), '--require-hashes', '--no-deps', '--disable-pip', '--strict',
                      '--progress-spinner', 'off', '-f', 'json'], capture_output=True, text=True, encoding='utf-8',
                     errors='replace', check=False)
    try:
        datos = json.loads(r.stdout or '{}')
    except ValueError as exc:
        raise CE.EntregaError(f'pip-audit no dio un JSON: {r.stderr.strip()[-800:]}') from exc
    dependencias = datos.get('dependencies') or []
    if not dependencias:
        raise CE.EntregaError(f'pip-audit no auditó nada: {r.stderr.strip()[-800:]}')
    halladas = [(v['id'], d['name'].lower(), d.get('version', '')) for d in dependencias for v in d.get('vulns') or ()]
    sin_justificar = sorted({h for h in halladas if (h[0], h[1]) not in justificadas})
    resumen = {'auditado': True, 'fecha': time.strftime('%Y-%m-%d', time.gmtime()), 'herramienta': 'pip-audit',
               'dependencias': len(dependencias), 'vulnerabilidades': len(halladas),
               'justificadas': len(halladas) - len(sin_justificar), 'sin_justificar': [list(h) for h in sin_justificar]}
    destino.write_text(json.dumps({'resumen': resumen, 'pip_audit': datos}, ensure_ascii=False, indent=1), encoding='utf-8')
    if sin_justificar:
        raise CE.EntregaError('pip-audit halló vulnerabilidades sin justificar en el lock: '
                              + ', '.join(f'{p} {v} ({i})' for i, p, v in sin_justificar) + f'; justifíquelas en {justificadas_rel}.')
    return resumen


#: U2: el certificado nunca va en git. ``CSG_FIRMA_ARGUMENTOS`` lleva lo que identifica el certificado para signtool
#: (``/sha1 <huella>`` de uno instalado o en un token, o ``/dlib … /dmdf …`` de un servicio de firma en la nube).
VARIABLES_FIRMA = {'signtool': 'CSG_FIRMA_SIGNTOOL', 'argumentos': 'CSG_FIRMA_ARGUMENTOS', 'sello': 'CSG_FIRMA_SELLO'}


def firmar(ficheros: Iterable[Path], avisos: Avisos, *, entorno: dict[str, str] | None = None, ejecutar=subprocess.run,
           leer_firmas=firmas_authenticode) -> list[str]:
    """U2: firma con signtool el setup.exe y los ejecutables propios, con sello de tiempo, y comprueba la firma.

    Sin certificado, un candidato de prueba lo avisa y sigue sin firmar; el final no se entrega sin firma.
    """
    import os
    import shlex

    entorno = dict(os.environ) if entorno is None else entorno
    ficheros = [Path(f) for f in ficheros]
    argumentos = entorno.get(VARIABLES_FIRMA['argumentos'], '').strip()
    if not argumentos:
        avisos.falta(f'Sin certificado de firma ({VARIABLES_FIRMA["argumentos"]}): {", ".join(f.name for f in ficheros)} '
                     'quedan sin firmar.')
        return []
    signtool = entorno.get(VARIABLES_FIRMA['signtool'], '').strip() or 'signtool'
    sello = entorno.get(VARIABLES_FIRMA['sello'], '').strip() or 'http://timestamp.digicert.com'
    for f in ficheros:
        r = ejecutar([signtool, 'sign', '/fd', 'SHA256', '/tr', sello, '/td', 'SHA256', *shlex.split(argumentos, posix=False),
                      str(f)], capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
        if r.returncode:
            raise CE.EntregaError(f'signtool no firmó {f.name}: {(r.stdout + r.stderr).strip()[-800:]}')
    firmas = leer_firmas(ficheros)
    malas = [f.name for f in ficheros if firmas.get(f.name, ('', ''))[0] != 'Valid']
    if malas:
        raise CE.EntregaError(f'Firmados, pero Windows no da la firma por válida: {", ".join(malas)}.')
    return [f.name for f in ficheros]


def escribir_sumas(carpeta: Path) -> Path:
    """U4 (L2): ``SHA256SUMS`` de todo lo que se entrega en ``carpeta`` (instalador, complemento, notas, licencias).

    Formato de ``sha256sum``, con «*» de binario y rutas con «/», para comprobarlo con ``sha256sum -c`` o a mano con
    ``Get-FileHash``. Se envía por un canal distinto del instalador. El rc6 tenía uno, pero hecho a mano.
    """
    filas = [f'{_sha256(r)} *{rel}' for r, rel in CE._recorrer(carpeta) if rel != 'SHA256SUMS']
    if not filas:
        raise CE.EntregaError(f'No hay nada que sumar en {carpeta}.')
    destino = carpeta / 'SHA256SUMS'
    destino.write_text('\n'.join(filas) + '\n', encoding='utf-8', newline='\n')
    return destino


def construir_candidato(raiz: Path, salida: Path, zip_python: Path, *, cache: Path | None = None, version: str | None = None,
                        lista_local: Path | None = None, python_pf: Path | None = None,
                        final: bool = False) -> tuple[dict[str, Any], CE.Informe]:
    """``final``: la entrega del cliente. Sin lista local, sin el Python oficial firmado o sin pip-audit no se arma;
    en un candidato de prueba esas faltas quedan en ``avisos`` del manifiesto (L1, L5, U3)."""
    if salida.exists() and any(salida.iterdir()):
        raise CE.EntregaError(f'La carpeta {salida} no está vacía: un candidato no se arma sobre otro.')
    if final and version is not None:
        raise CE.EntregaError('Un candidato final lleva la versión del paquete: «--version» solo es para ensayar.')
    avisos = Avisos(final)
    manifiesto = CE.leer_manifiesto(raiz / 'config' / 'entrega.json')
    terminos = CE.cargar_terminos(raiz, manifiesto, lista_local=lista_local, final=final)
    if not any(o == 'lista local' for o in terminos.origenes):
        avisos.append(f'Sin lista local de términos ({CE.VARIABLE_LISTA_LOCAL}): solo vale para un candidato de prueba.')
    if not LOCK.is_file():
        raise CE.EntregaError(f'Falta {LOCK.name}: genérelo con la orden «lock».')
    # 086:RF-92: sin «--version», la del paquete; con ella es un ensayo de actualización, que no tiene notas propias.
    prevista = version or version_del_paquete(raiz)
    if version is None:
        comprobar_notas((raiz / NOTAS_DEL_PAQUETE).read_text(encoding='utf-8'), prevista)        # 086:RF-93
    faltan = [rel for rel in documentos_del_candidato(prevista) if not (raiz / rel).is_file()]
    if faltan:                                                                                  # 086:RF-91, antes de construir
        raise CE.EntregaError('Faltan documentos que se instalan con el programa: ' + ', '.join(faltan) + '.')
    rueda, cuenta = construir_rueda(raiz, salida / 'programa', manifiesto, terminos, version=version,
                                    calibrar_pregunta=True)
    version_final = rueda.name.split('-')[1]
    if version_final != prevista:
        raise CE.EntregaError(f'La rueda salió con la versión {version_final} y el paquete dice {prevista}.')
    ruedas = salida / 'terceros' / 'wheels'
    traer_ruedas(raiz, ruedas, raiz / LOCK.name, cache)
    version_python = extraer_python(zip_python, salida / 'terceros' / 'python')
    verificar_python_oficial(zip_python, salida / 'terceros' / 'python', manifiesto.get('python_programa') or {},
                             avisos)                                                            # U3
    # 103:RF-6: sin los Python de PowerFactory 2021 a 2023 no se arma el candidato: el operador no instala nada.
    fijados = manifiesto['candidato'].get('python_pf') or {}
    if fijados and python_pf is None:
        raise CE.EntregaError('Faltan los Python de PowerFactory: indique su carpeta con --python-pf.')
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
    copiar_documentos(raiz, documentos, version_final, manifiesto)                             # 086:RF-89, U1, L6
    auditar_dependencias(raiz, raiz / LOCK.name, documentos / 'auditoria_dependencias.json',
                         manifiesto.get('auditoria_dependencias') or {}, avisos)                # L5
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
    # 086:RF-44: lo que no viene en el METADATA de una rueda: las nativas del Python propio, NVIDIA y las fuentes LGPL.
    textos.update(avisos_nativos(raiz, salida / 'terceros' / 'python'))
    terceras = sorted(ruedas.glob('*.whl'))
    textos.update(avisos_nvidia(raiz, {r.name: dll_de_rueda(r) for r in terceras}))
    revision = _revision(raiz)
    (documentos / 'THIRD_PARTY_NOTICES.txt').write_text(_avisos(componentes, textos, fuentes_lgpl(raiz, terceras)), encoding='utf-8')
    (documentos / 'sbom.cdx.json').write_text(json.dumps(sbom(componentes, version_final, revision), ensure_ascii=False, indent=2), encoding='utf-8')
    ficheros = [{'ruta': rel, 'sha256': _sha256(r), 'bytes': r.stat().st_size} for r, rel in CE._recorrer(salida)]
    salida_manifiesto = {'version': version_final, 'revision': revision, 'python': version_python, 'creado': time.time(),
                         'final': final, 'avisos': list(avisos), 'neutralizados': cuenta, 'bytes_total': sum(f['bytes'] for f in ficheros), 'ficheros': ficheros}
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


# --------------------------------------------------------------------------- modelos del complemento
#: Dónde quedan, dentro del complemento, los modelos y Ollama; el instalador los copia a «{app}\\complemento_ia».
MODELOS_EN_COMPLEMENTO = Path('modelos')
CATALOGO_MODELOS = Path('docs', 'MODELOS_IA_LOCK.json')


def _blob_git(ruta: Path) -> str:
    """El SHA-1 de blob de git: Hugging Face identifica así los ficheros pequeños de una revisión (los del catálogo)."""
    h = hashlib.sha1(f'blob {ruta.stat().st_size}\0'.encode())
    with ruta.open('rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


def _copiar_fijado(origen: Path, destino: Path) -> None:
    """Un enlace duro si se puede (los pesos ocupan gigas), si no una copia; la huella se comprueba antes."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(origen, destino)
    except OSError:
        shutil.copyfile(origen, destino)


def _ficha(raiz: Path, backend: str, identificador: str) -> dict[str, Any]:
    catalogo = json.loads((raiz / CATALOGO_MODELOS).read_text(encoding='utf-8'))
    ficha = next((m for m in catalogo['modelos'] if m['backend'] == backend and m['id'] == identificador), None)
    if ficha is None:
        raise CE.EntregaError(f'{identificador} no está en {CATALOGO_MODELOS.as_posix()}: no se entrega un modelo sin su revisión fijada.')
    return ficha


def _modelo_huggingface(origen: Path, destino: Path, ficha: dict[str, Any]) -> list[str]:
    """Los ficheros de la revisión fijada, en la forma de la caché de Hugging Face, para leerlos sin internet.

    El codificador de órdenes los abre con ``local_files_only=True`` y su revisión (codificador_ordenes); así no hace
    falta ni ``CSG_SALIDA_HUGGING_FACE`` ni red en el cliente (decisión del usuario, 2026-11-13).
    """
    carpeta = 'models--' + ficha['id'].replace('/', '--')
    fuente = origen / 'huggingface' / 'hub' / carpeta / 'snapshots' / ficha['revision']
    copia = destino / 'huggingface' / 'hub' / carpeta
    hechos = []
    for f in ficha['files']:
        ruta = fuente / f['path']
        if not ruta.is_file() or ruta.stat().st_size != f['size']:
            raise CE.EntregaError(f'Falta {ficha["id"]}/{f["path"]} de la revisión {ficha["revision"]} en {fuente}, o tiene otro tamaño.')
        if (f['sha256'] and _sha256(ruta) != f['sha256']) or (not f['sha256'] and _blob_git(ruta) != f.get('git_blob_sha1')):
            raise CE.EntregaError(f'{ficha["id"]}/{f["path"]} no tiene la huella de la revisión {ficha["revision"]}.')
        _copiar_fijado(ruta, copia / 'snapshots' / ficha['revision'] / f['path'])
        hechos.append(f['path'])
    (copia / 'refs').mkdir(parents=True, exist_ok=True)
    (copia / 'refs' / 'main').write_text(ficha['revision'], encoding='utf-8', newline='')
    return hechos


def _modelo_ollama(origen: Path, destino: Path, ficha: dict[str, Any], licencia_sha: str) -> list[str]:
    """El manifiesto del registro (su SHA-256 es la revisión del catálogo) y sus capas, cada una por su huella."""
    nombre, etiqueta = ficha['id'].split(':', 1)
    rel_manifiesto = Path('manifests', 'registry.ollama.ai', 'library', nombre, etiqueta)
    manifiesto = origen / 'ollama_modelos' / rel_manifiesto
    if not manifiesto.is_file() or _sha256(manifiesto) != ficha['revision']:
        raise CE.EntregaError(f'El manifiesto de {ficha["id"]} falta en {manifiesto} o no es el de la revisión {ficha["revision"]}.')
    capas = json.loads(manifiesto.read_text(encoding='utf-8'))
    _copiar_fijado(manifiesto, destino / 'ollama' / rel_manifiesto)
    hechos = [rel_manifiesto.as_posix()]
    licencias = [c['digest'] for c in capas['layers'] if c['mediaType'] == 'application/vnd.ollama.image.license']
    if licencias != [f'sha256:{licencia_sha}']:
        raise CE.EntregaError(f'La capa de licencia de {ficha["id"]} no es la declarada en {LICENCIAS_TERCEROS.as_posix()}.')
    for capa in [capas['config'], *capas['layers']]:
        digest = capa['digest'].split(':', 1)[1]
        blob = origen / 'ollama_modelos' / 'blobs' / f'sha256-{digest}'
        if not blob.is_file() or blob.stat().st_size != capa['size'] or _sha256(blob) != digest:
            raise CE.EntregaError(f'Falta la capa {digest[:12]} de {ficha["id"]} o no tiene su huella.')
        _copiar_fijado(blob, destino / 'ollama' / 'blobs' / blob.name)
        hechos.append(f'blobs/{blob.name}')
    return hechos


def empaquetar_modelos(raiz: Path, origen: Path, salida: Path, manifiesto: dict[str, Any]
                       ) -> tuple[list[dict[str, Any]], dict[str, list[tuple[str, str]]], list[dict[str, Any]]]:
    """086:RF-34, RF-37: e5-base, qwen3:8b y Ollama, sin internet, con sus licencias; ningún peso sin declarar.

    Devuelve los componentes para el SBOM, sus textos de licencia y lo que el manifiesto del complemento cuenta de ellos.
    """
    pedido = manifiesto.get('complemento_ia') or {}
    if not pedido.get('modelos') or not pedido.get('ollama'):
        raise CE.EntregaError('config/entrega.json no declara los modelos ni Ollama del complemento («complemento_ia»).')
    textos_licencia = textos_de_terceros(raiz)
    destino = salida / MODELOS_EN_COMPLEMENTO
    componentes, textos, resumen = [], {}, []
    for m in pedido['modelos']:
        ficha = _ficha(raiz, m['backend'], m['id'])
        lic = textos_licencia[m['licencia']]
        if m['backend'] == 'huggingface':
            ficheros = _modelo_huggingface(origen, destino, ficha)
        elif m['backend'] == 'ollama':
            ficheros = _modelo_ollama(origen, destino, ficha, lic['sha256'])
        else:
            raise CE.EntregaError(f'Backend de modelo desconocido: {m["backend"]}')
        componentes.append({'tipo': 'machine-learning-model', 'name': ficha['id'], 'version': ficha['revision'],
                            'license': lic['licencia'], 'origen': m['backend'], 'sin_purl': True, 'source_url': lic['fuente']})
        textos[f'{ficha["id"]} (modelo)'] = _con_cita(lic)
        resumen.append({'id': ficha['id'], 'backend': m['backend'], 'revision': ficha['revision'], 'licencia': lic['licencia'],
                        'ficheros': len(ficheros)})
    o = pedido['ollama']
    zip_ollama = origen / 'ollama' / o['fichero']
    if not zip_ollama.is_file() or _sha256(zip_ollama) != o['sha256']:
        raise CE.EntregaError(f'Falta {o["fichero"]} de Ollama {o["version"]} en {zip_ollama.parent} o no tiene la huella publicada.')
    _copiar_fijado(zip_ollama, destino / 'ollama_runtime' / o['fichero'])
    with zipfile.ZipFile(zip_ollama) as z:
        nombres = z.namelist()
        propias = [(n, z.read(n).decode('utf-8', 'replace')) for n in nombres
                   if re.search(r'(licen[cs]e|notice|copying)[^/]*$', n, re.I) and not n.endswith('/')]
    componentes.append({'tipo': 'application', 'name': 'ollama', 'version': o['version'], 'license': 'MIT', 'origen': 'ollama',
                        'sha256': o['sha256'], 'sin_purl': True, 'source_url': o['url']})
    textos[f'Ollama {o["version"]}'] = [t for i in o['licencias'] for t in _con_cita(textos_licencia[i])] + propias
    textos.update({f'{k} (Ollama)': v for k, v in avisos_nvidia(raiz, {f'ollama {o["version"]}': [n for n in nombres if n.lower().endswith('.dll')]}).items()})
    resumen.append({'id': 'ollama', 'backend': 'runtime', 'revision': o['version'], 'licencia': 'MIT', 'sha256': o['sha256']})
    # RF-34: todo peso que va en el complemento está en la lista, con su huella y entrenado con datos públicos.
    for ruta, rel in CE._recorrer(salida):
        if not rel.startswith(MODELOS_EN_COMPLEMENTO.as_posix() + '/') or rel.endswith('.zip'):
            continue
        motivo = CE.motivo_de_peso(ruta, rel, manifiesto)
        if motivo:
            raise CE.EntregaError(f'{rel}: {motivo}.')
    return componentes, textos, resumen


def corpus_neutro(salida: Path, terminos: CE.Terminos) -> dict[str, Any]:
    """086:RF-34: un corpus de órdenes sin datos de ninguna empresa, de las plantillas del catálogo con nombres inventados.

    Es lo mismo que el intérprete genera al entrenar en el cliente (transformer.entrenar_y_promover) con un vocabulario
    vacío: queda escrito para que se pueda revisar, y se comprueba contra la lista de términos de la entrega.
    """
    from convertersmartgrid.asistente import ordenes_fijas, sinteticos

    memoria: dict[str, str | None] = {}

    def fila(e) -> dict[str, Any]:
        return {'texto': e.texto, 'tarea': e.tarea, 'datos': [list(d) for d in e.datos]}

    def limpia(e) -> bool:
        return not any(True for _ in CE._buscar(e.texto, terminos, memoria))

    # Las sintéticas inventan códigos con la forma de los reales (el intérprete aprende a reconocerlos): una que coincide
    # por azar con un término de la lista se descarta y se sustituye por otra de su misma tarea, sorteada con la semilla
    # siguiente. Así el corpus no lleva ningún término y conserva su tamaño por tarea (PUERTA3, 16-11: un código de alimentador real).
    sorteadas = sinteticos.generar({}, por_tarea=40, semilla=0)
    validas = [e for e in sorteadas if limpia(e)]
    faltan: dict[str, int] = {}
    for e in sorteadas:
        if not limpia(e):
            faltan[e.tarea] = faltan.get(e.tarea, 0) + 1
    descartadas = sum(faltan.values())
    semilla = 1
    while faltan and semilla <= 50:
        for e in sinteticos.generar({}, por_tarea=40, semilla=semilla):
            if faltan.get(e.tarea) and limpia(e) and all(e.texto != v.texto for v in validas):
                validas.append(e)
                faltan[e.tarea] -= 1
                if not faltan[e.tarea]:
                    del faltan[e.tarea]
        semilla += 1
    if faltan:
        raise CE.EntregaError(f'El corpus neutro no completa {sum(faltan.values())} orden(es) sin términos de la lista '
                              'de la entrega: no se entrega.')
    fijas = ordenes_fijas.generar({})
    # Las órdenes fijas están escritas a mano: una con un término de la lista es un defecto y rechaza la entrega.
    halladas = sorted({t for e in fijas for t, _ in CE._buscar(e.texto, terminos, memoria)})
    if halladas:
        raise CE.EntregaError(f'El corpus neutro lleva {len(halladas)} término(s) de la lista de la entrega: no se entrega.')
    filas = [fila(e) for e in [*validas, *fijas]]
    ruta = salida / 'corpus' / 'ordenes_neutras.json'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({'origen': 'sintetico', 'vocabulario': 'vacío: nombres inventados', 'empresa': None,
                                'filas': filas}, ensure_ascii=False, indent=0), encoding='utf-8')
    return {'filas': len(filas), 'sha256': _sha256(ruta), 'terminos_hallados': 0, 'sinteticas_resorteadas': descartadas}


def construir_complemento_ia(raiz: Path, salida: Path, *, cache: Path, version: str,
                            capacidades: str = 'inferencia', versiones: Path | None = None,
                            procedencias: Path | None = None, caches_adicionales: Iterable[Path] = (),
                            licencias: Path | None = None, modelos: Path | None = None,
                            lista_local: Path | None = None) -> dict[str, Any]:
    """086:RF-37/39 — cierre offline de inferencia, independiente del núcleo y sin pesos propios del proyecto.

    Con ``modelos`` (una caché fuera del repositorio con lo de ``complemento_ia`` de ``config/entrega.json``) trae además
    e5-base en su revisión fijada, qwen3:8b y Ollama, para usarlos sin internet, con sus licencias (086:RF-34, RF-44), y
    un corpus de órdenes neutro. Su instalador propio lo pone junto al programa (``instalador/ComplementoIA.iss``).
    """
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
    # 086:RF-44: NVIDIA de las DLL de CUDA y cuDNN de torch, y dónde está el código fuente de cada LGPL.
    terceras = sorted(ruedas.glob('*.whl'))
    textos.update(avisos_nvidia(raiz, {r.name: dll_de_rueda(r) for r in terceras}))
    anexo = fuentes_lgpl(raiz, terceras)
    resumen_modelos, corpus = [], None
    if modelos is not None:
        manifiesto_entrega = CE.leer_manifiesto(raiz / 'config' / 'entrega.json')
        de_modelos, textos_modelos, resumen_modelos = empaquetar_modelos(raiz, modelos, salida, manifiesto_entrega)
        componentes += de_modelos
        textos.update(textos_modelos)
        for clave, lista in textos_modelos.items():                     # cada licencia también como fichero propio
            for i, (nombre, texto) in enumerate(lista):
                destino = salida / 'licencias' / 'modelos' / re.sub(r'[^\w.-]+', '_', f'{clave}_{i}_{Path(nombre).name}')
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(texto, encoding='utf-8')
        corpus = corpus_neutro(salida, CE.cargar_terminos(raiz, manifiesto_entrega, lista_local=lista_local))
    instalador = salida / 'instalador'
    instalador.mkdir(exist_ok=True)
    # 086:RF-37: el complemento se instala con su propio instalador, sin pip a mano, como el programa.
    shutil.copyfile(RAIZ / 'tools' / 'instalar_candidato.py', instalador / 'instalar_candidato.py')
    shutil.copyfile(RAIZ / 'instalador' / 'ComplementoIA.iss', instalador / 'ComplementoIA.iss')
    revision = _revision(raiz)
    inventario = sbom(componentes, version, revision)
    inventario['metadata']['component']['name'] = 'convertersmartgrid-complemento-ia'
    (salida / 'sbom.cdx.json').write_text(json.dumps(inventario, ensure_ascii=False, indent=2), encoding='utf-8')
    (salida / 'THIRD_PARTY_NOTICES.txt').write_text(_avisos(componentes, textos, anexo), encoding='utf-8')
    con_modelos = ('Trae e5-base (revisión fijada), qwen3:8b y Ollama para usarlos sin internet; sus licencias están en\n'
                   'licencias/modelos y en THIRD_PARTY_NOTICES.txt. No trae pesos entrenados por el proyecto.\n'
                   if resumen_modelos else
                   'No trae modelos: el asistente usa las frases del catálogo y el Ollama que tenga el equipo.\n')
    (salida / 'LEEME.txt').write_text(
        f'Complemento de IA para ConverterSmartGrid {version}, CPython3.12 Windows64.\n' + con_modelos +
        f'Capacidades: {capacidades}; véase requisitos-declarados.txt y, para integrales, cobertura.json.\n'
        'Se instala con su propio instalador (ConverterSmartGrid-complemento-ia-<versión>-setup.exe), con el programa de\n'
        'la misma versión ya instalado y cerrado: comprueba cada huella, instala sin red y deja los modelos junto al\n'
        'programa. Sin ese instalador, con el Python del programa y desde esta carpeta:\n'
        'python.exe instalador\\instalar_candidato.py complemento --complemento . --destino <carpeta del programa>\n'
        'La construcción no acredita GPU ni aceptación científica.\n', encoding='utf-8')
    (salida / 'version.txt').write_text(f'{version}\n', encoding='utf-8', newline='\n')       # la lee ComplementoIA.iss
    archivos = [{'ruta': rel, 'sha256': _sha256(r), 'bytes': r.stat().st_size} for r, rel in CE._recorrer(salida)]
    resultado = {'tipo': 'complemento-ia', 'version': version, 'revision': revision, 'python': '3.12',
                 'capacidades': capacidades, 'proyecto_completo': False,
                 'plataforma': 'win_amd64', 'pesos_del_proyecto_incluidos': False, 'modelos_activados': bool(resumen_modelos),
                 'modelos': resumen_modelos, 'corpus_neutro': corpus,
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
    p_cand.add_argument('--final', action='store_true',
                        help='La entrega del cliente: sin lista local, sin el Python oficial firmado o sin pip-audit es un error.')
    p_firma = orden.add_parser('firmar', help='Firma con signtool el setup.exe y los ejecutables propios (U2); certificado por variable.')
    p_firma.add_argument('ficheros', type=Path, nargs='+')
    p_firma.add_argument('--final', action='store_true', help='Sin certificado es un error; si no, se avisa y quedan sin firmar.')
    p_sumas = orden.add_parser('sumas', help='Escribe SHA256SUMS de la carpeta de la entrega (U4).')
    p_sumas.add_argument('carpeta', type=Path)
    p_ia = orden.add_parser('complemento-ia', help='Complemento separado, de inferencia o capacidades integrales, offline con lock y avisos.')
    p_ia.add_argument('--salida', type=Path, required=True)
    p_ia.add_argument('--ruedas-cache', type=Path, required=True)
    p_ia.add_argument('--version', help='Versión del núcleo compatible; por defecto, la del paquete (086:RF-92).')
    p_ia.add_argument('--capacidades', choices=('inferencia', 'integrales'), default='inferencia')
    p_ia.add_argument('--versiones-capturadas', type=Path, help='Freeze exacto del entorno integral ya verificado.')
    p_ia.add_argument('--procedencias', type=Path, help='JSON de recibos Git/CUDA: name, version, url, commit_id (Git), wheel, sha256.')
    p_ia.add_argument('--licencias-suplementarias', type=Path, help='Recibos y textos de origen versionado, fijados a las huellas de rueda y licencia.')
    p_ia.add_argument('--ruedas-cache-adicional', action='append', type=Path, default=[], help='Otra caché de ruedas existente, sin copiarla previamente.')
    p_ia.add_argument('--modelos', type=Path, help='Caché fuera del repositorio con e5-base, qwen3:8b y Ollama (complemento_ia de config/entrega.json).')
    p_ia.add_argument('--sin-modelos', action='store_true', help='Solo ruedas: el complemento no trae modelos y lo dice.')
    p_ia.add_argument('--lista-local', type=Path, help='Lista de términos fuera de git para revisar el corpus neutro.')
    args = parser.parse_args(argv)
    try:
        if args.orden == 'complemento-ia':
            if (args.modelos is None) == (not args.sin_modelos):
                raise CE.EntregaError('Indique --modelos con la caché de los modelos, o --sin-modelos para un complemento sin ellos.')
            resultado = construir_complemento_ia(RAIZ, args.salida, cache=args.ruedas_cache, version=args.version or version_del_paquete(RAIZ),
                capacidades=args.capacidades, versiones=args.versiones_capturadas, procedencias=args.procedencias,
                caches_adicionales=args.ruedas_cache_adicional, licencias=args.licencias_suplementarias,
                modelos=args.modelos, lista_local=args.lista_local)
            print(json.dumps({k: resultado[k] for k in ('tipo', 'version', 'revision', 'bytes_total')}
                             | {'ficheros': len(resultado['ficheros'])}, ensure_ascii=False, indent=2))
            return 0
        if args.orden == 'firmar':
            avisos = Avisos(args.final)
            firmados = firmar(args.ficheros, avisos)
            print(json.dumps({'firmados': firmados, 'avisos': list(avisos)}, ensure_ascii=False, indent=2))
            return 0
        if args.orden == 'sumas':
            print(escribir_sumas(args.carpeta))
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
                                                 python_pf=args.python_pf, final=args.final)
        print(json.dumps({k: resultado[k] for k in ('version', 'revision', 'python', 'final', 'avisos', 'neutralizados', 'bytes_total')} | {'ficheros': len(resultado['ficheros'])},
                         ensure_ascii=False, indent=2))
        print(json.dumps(informe.resumen(), ensure_ascii=False, indent=2))
        return 2 if informe.rechazado else 0
    except (CE.EntregaError, OSError, ValueError) as exc:
        print(f'No se pudo armar: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
