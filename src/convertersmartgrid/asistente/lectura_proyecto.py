"""Las tres lecturas del proyecto que puede pedir el LLM, y qué puede leer (spec 077).

Una sola lógica para ``pregunta`` y para el servidor MCP: leer un fichero por rango, buscar un texto
literal y consultar una ruta en el OpenAPI generado. No hay ninguna operación de escritura ni ninguna
petición HTTP (077:RF-18, RF-25): la lista blanca dice lo que se lee, y la lista negra manda sobre ella.

Una ruta se comprueba por su forma y otra vez por lo que hay en disco, porque en Windows ``OUTPUT``,
``.env.``, ``.env::$DATA`` y una unión de directorios llegan todos al mismo fichero que ``output`` o ``.env``.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

OPENAPI = 'docs/asistente/openapi.json'
#: Por lectura: un fichero entero de la web son 9 000 líneas, y el contexto del LLM no llega a tanto.
TOPE_LINEAS = 200
TOPE_CARACTERES = 20_000
TOPE_RESULTADOS = 30
TOPE_TAMANO = 4_000_000
TOPE_RUTA = 400
#: Lecturas que el LLM puede pedir en una misma pregunta (077:RF-28).
MAX_LECTURAS_LLM = 3
MAX_NOMBRADAS = 3
LINEAS_NOMBRADO = 40

CARPETAS_BLANCAS = ('src/', 'tools/', 'tests/', 'tests_ml/', 'docs/', 'specs/', 'frontend/src/', '.claude/skills/')
FICHEROS_BLANCOS = ('claude.md', 'codigo_fuente.md', 'vnr-gis.md', 'pyproject.toml', 'run_gui.bat', 'readme*',
                    'requirements*.txt', 'constraints-*.txt', 'frontend/package.json', 'config/*.example.*',
                    'config/pide_universal_2017.json', 'config/vnr_dgs_profile.json')
EXTENSIONES = ('.py', '.md', '.ts', '.tsx', '.css', '.json', '.toml', '.txt', '.yaml', '.yml', '.bat', '')
SEGMENTOS_NEGROS = frozenset({'output', 'input', '.agents', '.git', '.venv', 'venv', 'node_modules', '__pycache__',
                              '.worktrees', 'referencia', 'maestro_real', 'dist', '.pytest_cache', '.cursor',
                              '.ruff_cache', '.mypy_cache', 'basedatoselectrodunas', 'referencia_retirada_20261102'})
NOMBRES_NEGROS = ('.env', '.env.*', '*.env', '*credential*', '*secret*', '*password*', '*.pem', '*.key', '*.pfx',
                  '*.p12', 'id_rsa*', '.npmrc', '.pypirc', '.netrc', 'perfil_empresa.json', 'line_type_aliases.json',
                  'demanda_medida_alias.json', 'costes_referenciales.json', 'vnr_settings.yaml')
#: Los conjuntos sellados y sus resultados: un modelo que los lea deja de medirse a ciegas (076:RF-16).
#: De `docs/asistente/` solo se lee el OpenAPI generado: lo demás es el conjunto de la 076, sin revisar.
RUTAS_NEGRAS = ('config/perfiles/*', 'docs/rag_*', 'docs/conjunto_*', 'docs/evaluacion_*', 'docs/calibracion_*', 'docs/asistente/*')
_NOMBRE_CORTO = re.compile(r'~\d')
_RESERVADOS = frozenset({'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))})


class RutaRechazada(ValueError):
    """La ruta no está permitida. El mensaje nunca lleva contenido del fichero."""


class ArgumentoInvalido(ValueError):
    """Los argumentos de una lectura no son los de su catálogo."""


def _en_lista(rel: str, nombre: str, lista: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(rel, p) or fnmatch.fnmatchcase(nombre, p) for p in lista)


def motivo_de_rechazo(rel: str) -> str | None:
    """Por qué las listas rechazan esta ruta relativa, o ``None`` si se puede leer (077:RF-19, RF-20, RF-23)."""
    # 077:RF-23: en NTFS, OUTPUT y output son la misma carpeta.
    plano = rel.casefold()
    partes = plano.split('/')
    nombre = partes[-1]
    if SEGMENTOS_NEGROS & set(partes) or _en_lista(nombre, nombre, NOMBRES_NEGROS):
        return 'lista negra'
    if plano != OPENAPI and any(fnmatch.fnmatchcase(plano, p) for p in RUTAS_NEGRAS):
        return 'lista negra'
    if PurePosixPath(plano).suffix not in EXTENSIONES:
        return 'extensión fuera de la lista blanca'
    if plano.startswith(CARPETAS_BLANCAS) or any(fnmatch.fnmatchcase(plano, p) for p in FICHEROS_BLANCOS):
        return None
    return 'fuera de la lista blanca'


def permitida(rel: str) -> bool:
    return motivo_de_rechazo(rel) is None


def _forma_valida(ruta: Any) -> str:
    """La ruta relativa con barras normales, o el motivo por el que su forma ya no vale (077:RF-21, RF-24)."""
    if not isinstance(ruta, str) or not ruta.strip() or len(ruta) > TOPE_RUTA:
        raise RutaRechazada('ruta vacía o demasiado larga')
    if any(ord(c) < 32 for c in ruta) or '%' in ruta:
        raise RutaRechazada('ruta con caracteres no admitidos')
    plana = ruta.replace('\\', '/')
    # Los dos puntos cubren a la vez la unidad (D:/, D:x) y los flujos alternativos (.env::$DATA).
    if ':' in plana or plana.startswith('/') or PureWindowsPath(ruta).is_absolute() or PureWindowsPath(ruta).drive:
        raise RutaRechazada('solo rutas relativas al repositorio')
    partes = plana.split('/')
    for parte in partes:
        if parte in ('', '.', '..'):
            raise RutaRechazada('ruta con segmentos no admitidos')
        if parte[-1] in ' .' or _NOMBRE_CORTO.search(parte) or parte.split('.')[0].casefold() in _RESERVADOS:
            raise RutaRechazada('nombre no admitido en Windows')
    return plana


def comprobar_ruta(repo: Path, ruta: Any) -> tuple[Path, str]:
    """El fichero y su ruta relativa, comprobados por su forma y por lo que hay en disco (077:RF-19 a RF-24)."""
    rel = _forma_valida(ruta)
    if (motivo := motivo_de_rechazo(rel)) is not None:
        raise RutaRechazada(f'{rel}: {motivo}')
    raiz = repo.resolve()
    destino = (raiz / rel).resolve()
    try:
        real = destino.relative_to(raiz).as_posix()
    except ValueError as exc:
        raise RutaRechazada(f'{rel}: un enlace lleva fuera del repositorio') from exc
    if (motivo := motivo_de_rechazo(real)) is not None:
        raise RutaRechazada(f'{rel}: un enlace lleva a una ruta rechazada ({motivo})')
    if not destino.is_file():
        raise RutaRechazada(f'{rel}: no existe o no es un fichero')
    # Un enlace duro no se distingue por su ruta: es el mismo fichero bajo otro nombre (077:RF-22).
    if destino.stat().st_nlink > 1:
        raise RutaRechazada(f'{rel}: es un enlace duro')
    return destino, rel


def _texto_de(destino: Path, rel: str) -> str:
    if destino.stat().st_size > TOPE_TAMANO:
        raise RutaRechazada(f'{rel}: demasiado grande para leerlo aquí')
    crudo = destino.read_bytes()
    if b'\x00' in crudo[:4096]:
        raise RutaRechazada(f'{rel}: no es un fichero de texto')
    return crudo.decode('utf-8', errors='replace')


def estado_de_spec(repo: Path, carpeta: str) -> str | None:
    """La palabra de la línea ``Estado:`` de esa spec (033), o ``None`` si no la tiene."""
    try:
        with (repo / 'specs' / carpeta / 'spec.md').open(encoding='utf-8', errors='replace') as f:
            for _, linea in zip(range(20), f, strict=False):
                if (m := re.match(r'^Estado:\s*(\w+)', linea)):
                    return m.group(1).casefold()
    except OSError:
        return None
    return None


def vigencia_de(repo: Path, rel: str) -> tuple[str, str | None]:
    """``(vigente|historico, estado de la spec o None)`` (077:RF-6, RF-7, RF-10)."""
    plano, estado = rel.casefold(), None
    partes = plano.split('/')
    if len(partes) >= 3 and partes[0] == 'specs':
        estado = estado_de_spec(repo, rel.split('/')[1])
    historico = (plano.startswith('docs/superpowers/') or estado == 'retirada'
                 or (partes[0] == 'docs' and len(partes) == 2
                     and (partes[1].startswith('diagnostico_') or re.search(r'\d{4}-\d{2}-\d{2}', partes[1]) is not None)))
    return ('historico' if historico else 'vigente'), estado


def leer_fichero(repo: Path, ruta: str, desde: int = 1, hasta: int | None = None) -> dict[str, Any]:
    """Las líneas ``desde``-``hasta`` de un fichero permitido, con un tope por lectura (077:RF-16)."""
    destino, rel = comprobar_ruta(repo, ruta)
    if type(desde) is not int or desde < 1 or (hasta is not None and (type(hasta) is not int or hasta < desde)):
        raise ArgumentoInvalido('rango de líneas no válido')
    lineas = _texto_de(destino, rel).splitlines()
    fin = min(len(lineas), desde + TOPE_LINEAS - 1, hasta if hasta is not None else len(lineas))
    texto = '\n'.join(lineas[desde - 1:fin])
    truncado = fin < (hasta if hasta is not None else len(lineas)) or len(texto) > TOPE_CARACTERES
    texto = texto[:TOPE_CARACTERES]
    vigencia, estado = vigencia_de(repo, rel)
    return {'herramienta': 'leer_fichero', 'fuente': f'{rel}:{desde}', 'ruta': rel, 'desde': desde, 'hasta': fin,
            'total_lineas': len(lineas), 'truncado': truncado, 'texto': texto, 'vigencia': vigencia,
            'estado_spec': estado, 'sha256': hashlib.sha256(texto.encode('utf-8')).hexdigest()}


def recorrer(repo: Path) -> Iterator[tuple[Path, str]]:
    """Los ficheros permitidos, sin seguir enlaces y en un orden fijo."""
    raiz = repo.resolve()
    for hijo in sorted(raiz.iterdir(), key=lambda p: p.name):
        if hijo.is_file() and not hijo.is_symlink() and permitida(hijo.name):
            yield hijo, hijo.name
    for carpeta in ('src', 'tools', 'tests', 'tests_ml', 'docs', 'specs', 'frontend/src', '.claude/skills'):
        for actual, dirs, nombres in os.walk(raiz / carpeta, followlinks=False):
            base = Path(actual)
            # La prueba de la 077 lo destapó: os.walk entra en una unión de directorios aunque no siga los enlaces,
            # e is_symlink no la reconoce. Se compara dónde está de verdad cada carpeta con dónde dice estar.
            dirs[:] = sorted(d for d in dirs if d.casefold() not in SEGMENTOS_NEGROS
                             and os.path.realpath(base / d).casefold() == str(base / d).casefold())
            for nombre in sorted(nombres):
                p = base / nombre
                rel = p.relative_to(raiz).as_posix()
                if not p.is_symlink() and permitida(rel):
                    yield p, rel


def buscar_texto(repo: Path, texto: str, dentro: str | None = None, tope: int = TOPE_RESULTADOS) -> dict[str, Any]:
    """Un texto literal en los ficheros permitidos (077:RF-17). Sin expresiones regulares: una pedida por un
    modelo puede colgar el carril, y ``re`` no tiene tiempo máximo."""
    if not isinstance(texto, str) or not 3 <= len(texto.strip()) <= 200:
        raise ArgumentoInvalido('el texto a buscar lleva entre 3 y 200 caracteres')
    if type(tope) is not int or not 1 <= tope <= TOPE_RESULTADOS:
        raise ArgumentoInvalido(f'tope de resultados entre 1 y {TOPE_RESULTADOS}')
    prefijo = None
    if dentro is not None:
        prefijo = _forma_valida(dentro).rstrip('/').casefold()
        if (motivo := motivo_de_rechazo(prefijo + '/x.py')) is not None:
            raise RutaRechazada(f'{dentro}: {motivo}')
    aguja, coincidencias, vistos, truncado = texto.strip().casefold(), [], 0, False
    for p, rel in recorrer(repo):
        if prefijo is not None and not rel.casefold().startswith(prefijo + '/'):
            continue
        try:
            if p.stat().st_nlink > 1 or p.stat().st_size > TOPE_TAMANO:
                continue
            contenido = _texto_de(p, rel)
        except (OSError, RutaRechazada):
            continue
        vistos += 1
        if aguja not in contenido.casefold():
            continue
        for n, linea in enumerate(contenido.splitlines(), 1):
            if aguja in linea.casefold():
                if len(coincidencias) >= tope:
                    truncado = True
                    break
                coincidencias.append({'fuente': f'{rel}:{n}', 'ruta': rel, 'linea': n, 'texto': linea.strip()[:240]})
        if truncado:
            break
    return {'herramienta': 'buscar_texto', 'texto_buscado': texto.strip(), 'ficheros_vistos': vistos,
            'coincidencias': coincidencias, 'truncado': truncado}


def documento_openapi(repo: Path) -> tuple[dict[str, Any], list[str]]:
    """El OpenAPI generado y sus líneas (077:RF-5). Nunca se pide a un servidor."""
    destino, rel = comprobar_ruta(repo, OPENAPI)
    texto = _texto_de(destino, rel)
    return json.loads(texto), texto.splitlines()


def linea_de_ruta(lineas: list[str], ruta: str) -> int:
    """La línea de esa ruta en el JSON, tal como lo escribe ``tools/generar_contrato_api.py``."""
    marca = f'    {json.dumps(ruta)}: {{'
    return next((i for i, linea in enumerate(lineas, 1) if linea == marca), 1)


def _esquema_corto(esquema: Any, documento: Mapping[str, Any]) -> Any:
    """Nombre y campos del esquema, a un nivel: la API entera no cabe en el contexto del LLM."""
    if not isinstance(esquema, Mapping):
        return None
    if '$ref' in esquema:
        nombre = str(esquema['$ref']).rsplit('/', 1)[-1]
        destino = ((documento.get('components') or {}).get('schemas') or {}).get(nombre) or {}
        return {'esquema': nombre, 'campos': sorted(destino.get('properties') or ()),
                'obligatorios': sorted(destino.get('required') or ())}
    if esquema.get('type') == 'array':
        return {'lista_de': _esquema_corto(esquema.get('items'), documento)}
    if esquema.get('properties'):
        return {'campos': sorted(esquema['properties']), 'obligatorios': sorted(esquema.get('required') or ())}
    return {k: esquema[k] for k in ('type', 'title', 'anyOf') if k in esquema} or None


def operaciones_de(documento: Mapping[str, Any], ruta: str) -> list[dict[str, Any]]:
    """Cada método de una ruta, con lo que pide y lo que devuelve."""
    salida = []
    for metodo, op in sorted((documento.get('paths') or {}).get(ruta, {}).items()):
        if metodo.startswith('x-') or not isinstance(op, Mapping):
            continue
        cuerpo = ((op.get('requestBody') or {}).get('content') or {})
        respuestas = op.get('responses') or {}
        exito = next((respuestas[c] for c in sorted(respuestas) if str(c).startswith('2')), {})
        salida.append({'metodo': metodo.upper(), 'resumen': op.get('summary') or '',
                       'descripcion': op.get('description') or '',
                       'parametros': [{'nombre': p.get('name'), 'en': p.get('in'), 'obligatorio': bool(p.get('required'))}
                                      for p in op.get('parameters') or () if isinstance(p, Mapping)],
                       'cuerpo': {t: _esquema_corto(c.get('schema'), documento) for t, c in sorted(cuerpo.items())},
                       'respuesta': {t: _esquema_corto(c.get('schema'), documento)
                                     for t, c in sorted((exito.get('content') or {}).items())}})
    return salida


def _casa_plantilla(plantilla: str, ruta: str) -> bool:
    return re.fullmatch(re.sub(r'\\\{[^/]+\\\}', '[^/]+', re.escape(plantilla)), ruta) is not None


def consultar_api(repo: Path, ruta: str, metodo: str | None = None) -> dict[str, Any]:
    """Una ruta en el OpenAPI generado, sin ninguna petición (077:RF-18). Admite la plantilla o una ruta concreta."""
    if not isinstance(ruta, str) or not ruta.startswith('/') or len(ruta) > TOPE_RUTA:
        raise ArgumentoInvalido('la ruta de la API empieza por «/»')
    if metodo is not None and (not isinstance(metodo, str) or not metodo.isalpha()):
        raise ArgumentoInvalido('método HTTP no válido')
    documento, lineas = documento_openapi(repo)
    rutas = documento.get('paths') or {}
    limpia = ruta.split('?', 1)[0].rstrip('/') or '/'
    hallada = limpia if limpia in rutas else next((r for r in sorted(rutas) if _casa_plantilla(r, limpia)), None)
    if hallada is None:
        parecidas = [r for r in sorted(rutas) if limpia.casefold() in r.casefold()][:20]
        return {'herramienta': 'consultar_api', 'ruta': limpia, 'existe': False, 'parecidas': parecidas,
                'fuente': OPENAPI + ':1', 'vigencia': 'vigente', 'estado_spec': None}
    ops = operaciones_de(documento, hallada)
    if metodo is not None:
        ops = [o for o in ops if o['metodo'] == metodo.upper()]
    texto = json.dumps(ops, ensure_ascii=False, sort_keys=True)
    return {'herramienta': 'consultar_api', 'ruta': hallada, 'existe': True, 'operaciones': ops,
            'fuente': f'{OPENAPI}:{linea_de_ruta(lineas, hallada)}', 'vigencia': 'vigente', 'estado_spec': None,
            'sha256': hashlib.sha256(texto.encode('utf-8')).hexdigest()}


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    esquema: dict[str, Any]
    funcion: Callable[..., dict[str, Any]]


def _objeto(propiedades: dict[str, Any], obligatorias: tuple[str, ...]) -> dict[str, Any]:
    return {'type': 'object', 'additionalProperties': False, 'required': list(obligatorias), 'properties': propiedades}


HERRAMIENTAS: dict[str, Herramienta] = {h.nombre: h for h in (
    Herramienta('leer_fichero',
                f'Lee un fichero del proyecto por rango de líneas, como mucho {TOPE_LINEAS} por lectura. Solo lectura.',
                _objeto({'ruta': {'type': 'string', 'description': 'Ruta relativa al repositorio, con barras normales.'},
                         'desde': {'type': 'integer', 'minimum': 1},
                         'hasta': {'type': 'integer', 'minimum': 1}}, ('ruta',)), leer_fichero),
    Herramienta('buscar_texto',
                f'Busca un texto literal en los ficheros permitidos, como mucho {TOPE_RESULTADOS} resultados. Solo lectura.',
                _objeto({'texto': {'type': 'string', 'minLength': 3, 'maxLength': 200},
                         'dentro': {'type': 'string', 'description': 'Carpeta relativa donde buscar.'},
                         'tope': {'type': 'integer', 'minimum': 1, 'maximum': TOPE_RESULTADOS}}, ('texto',)), buscar_texto),
    Herramienta('consultar_api',
                'Consulta una ruta de la API en el OpenAPI generado, sin hacer ninguna petición. Solo lectura.',
                _objeto({'ruta': {'type': 'string', 'description': 'Por ejemplo /api/jobs/{job_id}.'},
                         'metodo': {'type': 'string'}}, ('ruta',)), consultar_api),
)}


def ejecutar(repo: Path, nombre: str, argumentos: Mapping[str, Any]) -> dict[str, Any]:
    """La lectura pedida, con sus argumentos comprobados contra el catálogo."""
    herramienta = HERRAMIENTAS.get(nombre)
    if herramienta is None:
        raise ArgumentoInvalido(f'lectura fuera del catálogo: {nombre!r}')
    if not isinstance(argumentos, Mapping):
        raise ArgumentoInvalido('los argumentos van en un objeto')
    propiedades, obligatorias = herramienta.esquema['properties'], herramienta.esquema['required']
    if set(argumentos) - set(propiedades) or set(obligatorias) - set(argumentos):
        raise ArgumentoInvalido(f'argumentos de {nombre} distintos de su catálogo')
    return herramienta.funcion(repo, **dict(argumentos))


def catalogo() -> list[dict[str, Any]]:
    """Nombre, descripción y esquema de cada lectura: lo que ve el LLM y lo que publica el MCP."""
    return [{'nombre': h.nombre, 'descripcion': h.descripcion, 'esquema': h.esquema} for h in HERRAMIENTAS.values()]


_RUTA_API = re.compile(r'(?<![\w/.-])(/api/[\w/{}.\-]*)')
_ABSOLUTA = re.compile(r'(?<![\w/.-])([A-Za-z]:[\\/][^\s,;«»"\'`()]+)')
_RUTA = re.compile(r'(?<![\w/\\.-])((?:\.{0,2}[\w\-][\w.\-]*|\.{1,2})(?:[/\\][\w.\-{}]+)+|\.env[\w.]*|[\w\-]+\.(?:py|tsx?|md|toml|json))(?::(\d+))?(?![\w/\\-])',
                   re.IGNORECASE)


def nombradas_en(repo: Path, pregunta: str) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Las lecturas que pide por sí misma una pregunta que nombra un fichero o una ruta, y las rutas rechazadas.

    Un nombre suelto, como ``indice.py``, se resuelve si en el proyecto solo hay uno así; si hay varios o ninguno
    no se adivina (077:RF-26, RF-27)."""
    pedidas: list[tuple[str, dict[str, Any]]] = []
    rechazadas: list[str] = []
    texto = _ABSOLUTA.sub(lambda m: (rechazadas.append(m.group(1)), ' ')[1], pregunta or '')
    for ruta in _RUTA_API.findall(texto):
        pedidas.append(('consultar_api', {'ruta': ruta}))
    texto = _RUTA_API.sub(' ', texto)
    permitidos: list[str] | None = None
    for m in _RUTA.finditer(texto):
        nombre, linea = m.group(1).rstrip('.'), m.group(2)
        args: dict[str, Any] = {}
        if linea:
            args = {'desde': max(1, int(linea) - LINEAS_NOMBRADO // 2), 'hasta': int(linea) + LINEAS_NOMBRADO // 2}
        else:
            args = {'desde': 1, 'hasta': LINEAS_NOMBRADO}
        if '/' not in nombre and '\\' not in nombre:
            if motivo_de_rechazo(nombre) == 'lista negra':
                rechazadas.append(nombre)
                continue
            if permitidos is None:
                permitidos = [rel for _, rel in recorrer(repo)]
            iguales = [r for r in permitidos if r.rsplit('/', 1)[-1].casefold() == nombre.casefold()]
            if len(iguales) == 1:
                pedidas.append(('leer_fichero', {'ruta': iguales[0], **args}))
            continue
        try:
            comprobar_ruta(repo, nombre)
        except RutaRechazada:
            # Solo se avisa de lo que parece pedir algo vedado: «kV/km» o «y/o» también tienen forma de ruta.
            if motivo_de_rechazo(nombre.replace('\\', '/')) == 'lista negra' or '..' in nombre:
                rechazadas.append(nombre)
            continue
        pedidas.append(('leer_fichero', {'ruta': nombre.replace('\\', '/'), **args}))
    unicas = list({json.dumps(p, sort_keys=True): p for p in pedidas}.values())
    return {'pedidas': unicas[:MAX_NOMBRADAS], 'rechazadas': list(dict.fromkeys(rechazadas))}
