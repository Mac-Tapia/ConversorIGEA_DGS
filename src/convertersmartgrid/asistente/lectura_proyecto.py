"""Las tres lecturas del proyecto que puede pedir el LLM, y qué puede leer (spec 077).

Una sola lógica para ``pregunta`` y para el servidor MCP: leer un fichero por rango, buscar un texto
literal y consultar una ruta en el OpenAPI generado. No hay ninguna operación de escritura ni ninguna
petición HTTP (077:RF-18, RF-25).

Dos políticas. El usuario, el 2026-11-02: «el LLM debe leer todos los archivos del proyecto, incluso del
local». Con un LLM de esta máquina se lee todo el árbol y las raíces configuradas, salvo secretos, lo sellado
y el examen humano (077:RF-51 a RF-55). Si el modelo no es local, o el lector es un cliente MCP que puede
estar en la nube, vale la restringida: lista blanca y lista negra (077:RF-19, RF-20, RF-57, RF-61).

Una ruta se comprueba por su forma y otra vez por lo que hay en disco, porque en Windows ``OUTPUT``,
``.env.``, ``.env::$DATA`` y una unión de directorios llegan todos al mismo fichero que ``output`` o ``.env``.
"""
from __future__ import annotations

import codecs
import fnmatch
import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

OPENAPI = 'docs/asistente/openapi.json'
#: Por lectura: un fichero entero de la web son 9 000 líneas, y el contexto del LLM no llega a tanto.
TOPE_LINEAS = 200
TOPE_CARACTERES = 20_000
TOPE_RESULTADOS = 30
#: Hasta este tamaño se cuentan las líneas del fichero; por encima no se recorre entero solo para decirlo (077:RF-68).
TOPE_TAMANO = 4_000_000
TOPE_RUTA = 400
#: Una raíz de datos puede tener miles de libros: la búsqueda corta aquí y lo dice (077:RF-67).
TOPE_SEGUNDOS_BUSQUEDA = 10.0
TOPE_SEGUNDOS_NOMBRE = 3.0
#: Lecturas que el LLM puede pedir en una misma pregunta (077:RF-28).
MAX_LECTURAS_LLM = 3
MAX_NOMBRADAS = 3
LINEAS_NOMBRADO = 40
#: Las raíces locales, sin ninguna ruta en el código (077:RF-52): separadas por ``os.pathsep``.
VARIABLE_RAICES = 'CSG_LLM_RAICES'
CLAVE_PERFIL_RAICES = 'raices_llm'

CARPETAS_BLANCAS = ('src/', 'tools/', 'tests/', 'tests_ml/', 'docs/', 'specs/', 'frontend/src/', '.claude/skills/')
FICHEROS_BLANCOS = ('claude.md', 'codigo_fuente.md', 'vnr-gis.md', 'pyproject.toml', 'run_gui.bat', 'readme*',
                    'requirements*.txt', 'constraints-*.txt', 'frontend/package.json', 'config/*.example.*',
                    'config/pide_universal_2017.json', 'config/vnr_dgs_profile.json')
EXTENSIONES = ('.py', '.md', '.ts', '.tsx', '.css', '.json', '.toml', '.txt', '.yaml', '.yml', '.bat', '')
SEGMENTOS_NEGROS = frozenset({'output', 'input', '.agents', '.git', '.venv', 'venv', 'node_modules', '__pycache__',
                              '.worktrees', 'referencia', 'maestro_real', 'dist', '.pytest_cache', '.cursor',
                              '.ruff_cache', '.mypy_cache'})
NOMBRES_NEGROS = ('perfil_empresa.json', 'line_type_aliases.json', 'demanda_medida_alias.json',
                  'costes_referenciales.json', 'vnr_settings.yaml')
RUTAS_NEGRAS = ('config/perfiles/*',)

#: No aportan a una búsqueda ni a un índice; se pueden leer si alguien los nombra (077:RF-56).
SIN_RECORRER = frozenset({'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.worktrees', '.pytest_cache',
                          '.ruff_cache', '.mypy_cache'})
#: Un secreto sirve para entrar en otro sitio, y no explica nada del proyecto: leerlo no aporta y puede acabar citado (077:RF-53).
SECRETOS = ('.env', '.env.*', '*.env', '*credential*', '*secret*', '*password*', '*.pem', '*.key', '*.pfx', '*.p12',
            'id_rsa*', '.npmrc', '.pypirc', '.netrc')
#: Lo que decide una puerta: un modelo que lo lea deja de medirse a ciegas (076:RF-16, 077:RF-54).
SELLADOS = ('rag_*.json', 'conjunto_*.json', 'evaluacion_*.json', 'calibracion_*.json', '*sellad*', 'ordenes_fijas.py')
#: Las órdenes que confirmó el operador son la prueba `gold_human`, y las etiquetas guardan su parte reservada (077:RF-55).
EXAMEN_HUMANO = ('ejemplos.jsonl', 'etiquetas*.jsonl')
#: De `docs/asistente/` solo se lee el OpenAPI: el resto mezcla filas de los dos repartos de la 076, también las selladas.
_CONJUNTO_076 = 'docs/asistente/*'

EXCEL = ('.xlsx', '.xls', '.xlsb', '.xlsm')
PDF = '.pdf'
#: Binarios conocidos y qué hacer con ellos, en vez de devolver basura (077:RF-65).
_ACCESS = ('.mdb', '.accdb')
_SIN_LECTOR = ('.bak', '.pfd', '.docx', '.doc', '.pptx', '.zip', '.7z', '.rar', '.gz', '.png', '.jpg', '.jpeg', '.gif',
               '.ico', '.exe', '.dll', '.pyd', '.pyc', '.so', '.npy', '.npz', '.pt', '.pth', '.safetensors', '.gguf', '.bin',
               '.parquet', '.sqlite', '.db', '.woff', '.woff2', '.ttf', '.mp4')
_NOMBRE_CORTO = re.compile(r'~\d')
_RESERVADOS = frozenset({'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))})
_UNIDAD = re.compile(r'^[A-Za-z]:/')


class RutaRechazada(ValueError):
    """La ruta no está permitida. El mensaje nunca lleva contenido del fichero."""


class ArgumentoInvalido(ValueError):
    """Los argumentos de una lectura no son los de su catálogo."""


@dataclass(frozen=True)
class Politica:
    """Qué se puede leer. Por defecto la restringida: abrirla es una decisión del servidor, nunca del modelo."""
    datos_locales: bool = False
    raices: tuple[Path, ...] = ()
    #: El lector de PDF es un adaptador: lo pasa quien arranca la lectura, porque esta capa no puede importarlo.
    lector_pdf: Callable[[Path], tuple[str, int, str, list[str]]] | None = None


RESTRINGIDA = Politica()


def raices_configuradas() -> tuple[Path, ...]:
    """Las raíces locales: ``CSG_LLM_RAICES``, ``CSG_DEMANDA_DIR`` y ``raices_llm`` del perfil local (077:RF-52)."""
    from ..perfil_empresa import datos_perfil

    candidatas = [x for x in os.environ.get(VARIABLE_RAICES, '').split(os.pathsep) if x.strip()]
    if os.environ.get('CSG_DEMANDA_DIR', '').strip():
        candidatas.append(os.environ['CSG_DEMANDA_DIR'])
    try:
        del_perfil = datos_perfil().get(CLAVE_PERFIL_RAICES)
    except (ValueError, OSError):                                       # un perfil roto no quita lo demás
        del_perfil = None
    if isinstance(del_perfil, (list, tuple)):
        candidatas += [str(x) for x in del_perfil if isinstance(x, str)]
    return tuple(dict.fromkeys(p for p in (Path(x.strip()).expanduser() for x in candidatas) if p.is_dir()))


def politica_local(lector_pdf: Callable[[Path], tuple[str, int, str, list[str]]] | None = None) -> Politica:
    return Politica(True, raices_configuradas(), lector_pdf)


def excluido_siempre(rel: str) -> str | None:
    """Lo que no se lee con ninguna política, y por qué (077:RF-53 a RF-56). Va por nombre, en cualquier carpeta."""
    plano = rel.casefold()
    partes = plano.split('/')
    nombre = partes[-1]
    if any(fnmatch.fnmatchcase(nombre, p) for p in SECRETOS):
        return 'credencial o secreto'
    # La dirección del remoto de Git puede llevar un token.
    if nombre == 'config' and len(partes) >= 2 and partes[-2] == '.git':
        return 'credencial o secreto'
    if any(fnmatch.fnmatchcase(nombre, p) for p in SELLADOS):
        return 'conjunto sellado o su resultado'
    if plano != OPENAPI and fnmatch.fnmatchcase(plano, _CONJUNTO_076):
        return 'conjunto sellado o su resultado'
    if any(fnmatch.fnmatchcase(nombre, p) for p in EXAMEN_HUMANO):
        return 'examen humano'
    return None


def motivo_de_rechazo(rel: str, politica: Politica = RESTRINGIDA) -> str | None:
    """Por qué se rechaza esta ruta relativa, o ``None`` si se puede leer (077:RF-19, RF-20, RF-23, RF-51)."""
    # 077:RF-23: en NTFS, OUTPUT y output son la misma carpeta.
    if (motivo := excluido_siempre(rel)) is not None:
        return f'lista negra: {motivo}'
    if politica.datos_locales:
        return None
    plano = rel.casefold()
    partes = plano.split('/')
    nombre = partes[-1]
    if SEGMENTOS_NEGROS & set(partes) or nombre in NOMBRES_NEGROS or any(fnmatch.fnmatchcase(plano, p) for p in RUTAS_NEGRAS):
        return 'lista negra'
    if PurePosixPath(plano).suffix not in EXTENSIONES:
        return 'extensión fuera de la lista blanca'
    if plano.startswith(CARPETAS_BLANCAS) or any(fnmatch.fnmatchcase(plano, p) for p in FICHEROS_BLANCOS):
        return None
    return 'fuera de la lista blanca'


def _es_vedada(motivo: str | None) -> bool:
    return motivo is not None and motivo.startswith('lista negra')


def permitida(rel: str, politica: Politica = RESTRINGIDA) -> bool:
    return motivo_de_rechazo(rel, politica) is None


def _forma_valida(ruta: Any, *, absoluta: bool = False) -> str:
    """La ruta con barras normales, o el motivo por el que su forma ya no vale (077:RF-21, RF-24)."""
    if not isinstance(ruta, str) or not ruta.strip() or len(ruta) > TOPE_RUTA:
        raise RutaRechazada('ruta vacía o demasiado larga')
    if any(ord(c) < 32 for c in ruta) or '%' in ruta:
        raise RutaRechazada('ruta con caracteres no admitidos')
    plana = ruta.replace('\\', '/')
    cuerpo = plana
    if absoluta and _UNIDAD.match(plana):
        cuerpo = plana[3:]
    elif absoluta and plana.startswith('~/'):
        cuerpo = plana[2:]
    # Los dos puntos cubren a la vez la unidad (D:/, D:x) y los flujos alternativos (.env::$DATA).
    if ':' in cuerpo or cuerpo.startswith('/') or (cuerpo == plana and (PureWindowsPath(ruta).is_absolute() or PureWindowsPath(ruta).drive)):
        raise RutaRechazada('solo rutas relativas al proyecto o dentro de una raíz configurada')
    for parte in cuerpo.split('/'):
        if parte in ('', '.', '..'):
            raise RutaRechazada('ruta con segmentos no admitidos')
        if parte[-1] in ' .' or _NOMBRE_CORTO.search(parte) or parte.split('.')[0].casefold() in _RESERVADOS:
            raise RutaRechazada('nombre no admitido en Windows')
    return plana


def _raices_de(repo: Path, politica: Politica) -> tuple[Path, ...]:
    return (repo.resolve(), *(r.resolve() for r in politica.raices))


def _relativa_a(destino: Path, raices: tuple[Path, ...]) -> str | None:
    """La ruta dentro del proyecto, o la absoluta si está en otra raíz; ``None`` si no está en ninguna."""
    try:
        return destino.relative_to(raices[0]).as_posix()
    except ValueError:
        pass
    for raiz in raices[1:]:
        if destino.is_relative_to(raiz):
            return destino.as_posix()
    return None


def comprobar_ruta(repo: Path, ruta: Any, politica: Politica = RESTRINGIDA) -> tuple[Path, str]:
    """El fichero y su ruta, comprobados por su forma y por lo que hay en disco (077:RF-19 a RF-24, RF-51, RF-52)."""
    plana = _forma_valida(ruta, absoluta=politica.datos_locales)
    es_absoluta = bool(_UNIDAD.match(plana)) or plana.startswith('~/')
    if not es_absoluta and (motivo := motivo_de_rechazo(plana, politica)) is not None:
        raise RutaRechazada(f'{plana}: {motivo}')
    raices = _raices_de(repo, politica)
    destino = (Path(plana).expanduser() if es_absoluta else raices[0] / plana).resolve()
    real = _relativa_a(destino, raices)
    if real is None:
        raise RutaRechazada(f'{plana}: fuera del proyecto y de las raíces configuradas')
    if (motivo := motivo_de_rechazo(real, politica)) is not None:
        raise RutaRechazada(f'{plana}: lleva a una ruta rechazada ({motivo})')
    if es_absoluta and excluido_siempre(plana) is not None:
        raise RutaRechazada(f'{plana}: {motivo_de_rechazo(plana, politica)}')
    if not destino.is_file():
        raise RutaRechazada(f'{plana}: no existe o no es un fichero')
    # Un enlace duro no se distingue por su ruta: es el mismo fichero bajo otro nombre (077:RF-22).
    if destino.stat().st_nlink > 1:
        raise RutaRechazada(f'{plana}: es un enlace duro')
    return destino, real if es_absoluta else plana


def _codificacion(destino: Path) -> str | None:
    """Cómo leerlo, o ``None`` si no es texto. Los TXT de un exportador suelen venir en ANSI, no en UTF-8."""
    with destino.open('rb') as f:
        muestra = f.read(65536)
    if muestra.startswith(codecs.BOM_UTF8):
        return 'utf-8-sig'
    if muestra.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return 'utf-16'
    if b'\x00' in muestra[:4096]:
        return None
    try:
        codecs.getincrementaldecoder('utf-8')().decode(muestra)
    except UnicodeDecodeError:
        return 'cp1252'
    return 'utf-8'


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


def _salida_lineas(repo: Path, rel: str, lineas: list[str], desde: int, fin: int, total: int | None, hay_mas: bool,
                   **extra: Any) -> dict[str, Any]:
    texto = '\n'.join(lineas)
    truncado = hay_mas or len(texto) > TOPE_CARACTERES
    texto = texto[:TOPE_CARACTERES]
    vigencia, estado = vigencia_de(repo, rel)
    return {'herramienta': 'leer_fichero', 'fuente': f'{rel}:{desde}', 'ruta': rel, 'desde': desde, 'hasta': fin,
            'total_lineas': total, 'truncado': truncado, 'texto': texto, 'vigencia': vigencia, 'estado_spec': estado,
            'es_dato': motivo_de_rechazo(rel) is not None, 'sha256': hashlib.sha256(texto.encode('utf-8')).hexdigest(), **extra}


def _rango(desde: int, hasta: int | None) -> int:
    """La última línea que se devuelve, con el tope por lectura."""
    return min(desde + TOPE_LINEAS - 1, hasta if hasta is not None else desde + TOPE_LINEAS - 1)


def _trozo(repo: Path, rel: str, todas: list[str], desde: int, hasta: int | None, **extra: Any) -> dict[str, Any]:
    fin = min(_rango(desde, hasta), len(todas))
    return _salida_lineas(repo, rel, todas[desde - 1:fin], desde, fin, len(todas),
                          fin < (hasta if hasta is not None else len(todas)), **extra)


def _indicacion(repo: Path, rel: str, formato: str, que_hacer: str) -> dict[str, Any]:
    """Un binario sin lector directo: dice qué ruta usar, en vez de devolver basura (077:RF-65)."""
    vigencia, estado = vigencia_de(repo, rel)
    return {'herramienta': 'leer_fichero', 'fuente': f'{rel}:1', 'ruta': rel, 'formato': formato, 'texto': '',
            'indicacion': f'{rel} es {formato}, no texto: {que_hacer}', 'vigencia': vigencia, 'estado_spec': estado,
            'es_dato': motivo_de_rechazo(rel) is not None}


def _leer_excel(repo: Path, destino: Path, rel: str, desde: int, hasta: int | None, hoja: str | None) -> dict[str, Any]:
    """Con el lector del proyecto, ``python-calamine``, una fila por línea (077:RF-63)."""
    try:
        from ..demanda_medida import DemandaError, hojas_del_libro
    except ImportError:
        return _indicacion(repo, rel, 'un libro de Excel', 'en este entorno falta su lector (requirements.txt).')
    try:
        hojas, elegida, filas = hojas_del_libro(destino, hoja)
    except DemandaError as exc:
        return _indicacion(repo, rel, 'un libro de Excel', str(exc))
    if elegida not in hojas:
        raise ArgumentoInvalido(f'{rel} no tiene la hoja {elegida!r}; tiene: {", ".join(hojas)}')
    todas = [' | '.join('' if c is None else str(c) for c in fila) for fila in filas]
    return _trozo(repo, rel, todas, desde, hasta, formato='excel', hojas=hojas, hoja=elegida)


def _leer_pdf(repo: Path, destino: Path, rel: str, desde: int, hasta: int | None, lector: Callable | None) -> dict[str, Any]:
    """Con el lector del proyecto, que usa la capa de texto y el OCR de las páginas sin ella (077:RF-64)."""
    if lector is None:
        return _indicacion(repo, rel, 'un PDF', 'esta vía no tiene lector de PDF.')
    try:
        texto, paginas, metodo, avisos = lector(destino)
    except ImportError:
        return _indicacion(repo, rel, 'un PDF', 'en este entorno falta pypdf (requirements.txt).')
    except (OSError, ValueError, RuntimeError) as exc:
        return _indicacion(repo, rel, 'un PDF', f'no se pudo abrir ({exc}).')
    if not texto.strip():
        return _indicacion(repo, rel, 'un PDF sin texto legible', '; '.join(avisos) or 'no tiene capa de texto.')
    return _trozo(repo, rel, texto.splitlines(), desde, hasta, formato='pdf', paginas=paginas, metodo=metodo, avisos=avisos)


def leer_fichero(repo: Path, ruta: str, desde: int = 1, hasta: int | None = None, hoja: str | None = None, *,
                 politica: Politica = RESTRINGIDA) -> dict[str, Any]:
    """Las líneas ``desde``-``hasta`` de un fichero permitido, con un tope por lectura (077:RF-16).

    Sin cargarlo entero: los TXT de una entrega pesan decenas de MB (077:RF-68). Excel y PDF van por sus lectores."""
    destino, rel = comprobar_ruta(repo, ruta, politica)
    if type(desde) is not int or desde < 1 or (hasta is not None and (type(hasta) is not int or hasta < desde)):
        raise ArgumentoInvalido('rango de líneas no válido')
    if hoja is not None and not isinstance(hoja, str):
        raise ArgumentoInvalido('el nombre de la hoja es un texto')
    extension = destino.suffix.casefold()
    if extension in EXCEL:
        return _leer_excel(repo, destino, rel, desde, hasta, hoja)
    if extension == PDF:
        return _leer_pdf(repo, destino, rel, desde, hasta, politica.lector_pdf)
    if extension in _ACCESS:
        return _indicacion(repo, rel, 'una base de Access', 'cárguela en un espacio (POST /api/workspaces/{wid}/load) '
                           'y pregunte por sus datos con la orden de consulta de datos; no se abre aquí.')
    codificacion = None if extension in _SIN_LECTOR else _codificacion(destino)
    if codificacion is None:
        return _indicacion(repo, rel, 'un fichero binario', 'el asistente no tiene un lector para este formato.')
    grande = destino.stat().st_size > TOPE_TAMANO
    fin, lineas, total, sobran = _rango(desde, hasta), [], 0, False
    with destino.open(encoding=codificacion, errors='replace') as f:
        for n, linea in enumerate(f, 1):
            total = n
            if n > fin:
                sobran = True
                if grande:
                    break
                continue
            if n >= desde:
                lineas.append(linea.rstrip('\r\n'))
    return _salida_lineas(repo, rel, lineas, desde, desde + len(lineas) - 1 if lineas else desde, None if grande and sobran else total,
                          sobran and (hasta is None or hasta > fin), codificacion=codificacion)


def _recorrer_carpeta(raiz: Path, carpeta: Path, nombrar: Callable[[Path], str]) -> Iterator[tuple[Path, str]]:
    for actual, dirs, nombres in os.walk(carpeta, followlinks=False):
        base = Path(actual)
        # La prueba de la 077 lo destapó: os.walk entra en una unión de directorios aunque no siga los enlaces,
        # e is_symlink no la reconoce. Se compara dónde está de verdad cada carpeta con dónde dice estar.
        dirs[:] = sorted(d for d in dirs if d.casefold() not in SIN_RECORRER
                         and os.path.realpath(base / d).casefold() == str(base / d).casefold())
        for nombre in sorted(nombres):
            p = base / nombre
            if not p.is_symlink():
                yield p, nombrar(p)


def recorrer(repo: Path, politica: Politica = RESTRINGIDA, *, con_raices: bool = True) -> Iterator[tuple[Path, str]]:
    """Los ficheros permitidos, sin seguir enlaces y en un orden fijo; lo que ``SIN_RECORRER`` nombra se salta."""
    raiz = repo.resolve()

    def del_proyecto(p: Path) -> str:
        return p.relative_to(raiz).as_posix()

    if politica.datos_locales:
        for p, rel in _recorrer_carpeta(raiz, raiz, del_proyecto):
            if permitida(rel, politica):
                yield p, rel
        for otra in (r.resolve() for r in politica.raices if con_raices):
            if otra.is_relative_to(raiz):
                continue
            for p, rel in _recorrer_carpeta(otra, otra, lambda q: q.as_posix()):
                if permitida(rel, politica):
                    yield p, rel
        return
    for hijo in sorted(raiz.iterdir(), key=lambda p: p.name):
        if hijo.is_file() and not hijo.is_symlink() and permitida(hijo.name):
            yield hijo, hijo.name
    for carpeta in ('src', 'tools', 'tests', 'tests_ml', 'docs', 'specs', 'frontend/src', '.claude/skills'):
        for p, rel in _recorrer_carpeta(raiz, raiz / carpeta, del_proyecto):
            if permitida(rel):
                yield p, rel


def _prefijo_de_busqueda(repo: Path, dentro: str, politica: Politica) -> str:
    plana = _forma_valida(dentro, absoluta=politica.datos_locales).rstrip('/')
    prueba = plana + '/x.py'
    if (motivo := motivo_de_rechazo(prueba, politica)) is not None:
        raise RutaRechazada(f'{dentro}: {motivo}')
    if _UNIDAD.match(plana) or plana.startswith('~/'):
        real = Path(plana).expanduser().resolve()
        if _relativa_a(real, _raices_de(repo, politica)) is None:
            raise RutaRechazada(f'{dentro}: fuera del proyecto y de las raíces configuradas')
        return real.as_posix().casefold()
    return plana.casefold()


def buscar_texto(repo: Path, texto: str, dentro: str | None = None, tope: int = TOPE_RESULTADOS, *,
                 politica: Politica = RESTRINGIDA) -> dict[str, Any]:
    """Un texto literal en los ficheros permitidos, con tope de resultados y de tiempo, y dice si corta (077:RF-17, RF-67).

    Sin expresiones regulares: una pedida por un modelo puede colgar el carril, y ``re`` no tiene tiempo máximo.
    Va línea a línea, porque una raíz de datos trae ficheros de cientos de MB."""
    if not isinstance(texto, str) or not 3 <= len(texto.strip()) <= 200:
        raise ArgumentoInvalido('el texto a buscar lleva entre 3 y 200 caracteres')
    if type(tope) is not int or not 1 <= tope <= TOPE_RESULTADOS:
        raise ArgumentoInvalido(f'tope de resultados entre 1 y {TOPE_RESULTADOS}')
    prefijo = None if dentro is None else _prefijo_de_busqueda(repo, dentro, politica)
    limite = time.monotonic() + TOPE_SEGUNDOS_BUSQUEDA
    aguja, coincidencias, vistos, binarios, cortada = texto.strip().casefold(), [], 0, 0, None
    for p, rel in recorrer(repo, politica):
        if time.monotonic() >= limite:
            cortada = 'tiempo'
            break
        if prefijo is not None and not rel.casefold().startswith(prefijo + '/'):
            continue
        extension = p.suffix.casefold()
        try:
            if p.stat().st_nlink > 1:
                continue
            codificacion = None if extension in (*EXCEL, PDF, *_ACCESS, *_SIN_LECTOR) else _codificacion(p)
            if codificacion is None:
                binarios += 1
                continue
            vistos += 1
            with p.open(encoding=codificacion, errors='replace') as f:
                for n, linea in enumerate(f, 1):
                    if aguja in linea.casefold():
                        if len(coincidencias) >= tope:
                            cortada = 'resultados'
                            break
                        coincidencias.append({'fuente': f'{rel}:{n}', 'ruta': rel, 'linea': n, 'texto': linea.strip()[:240],
                                              'es_dato': motivo_de_rechazo(rel) is not None})
                    if n % 2000 == 0 and time.monotonic() >= limite:
                        cortada = 'tiempo'
                        break
        except OSError:
            continue
        if cortada:
            break
    aviso = {'tiempo': f'Búsqueda cortada a los {TOPE_SEGUNDOS_BUSQUEDA:.0f} s: acote con «dentro».',
             'resultados': f'Búsqueda cortada en {tope} resultados.', None: ''}[cortada]
    return {'herramienta': 'buscar_texto', 'texto_buscado': texto.strip(), 'ficheros_vistos': vistos, 'binarios_omitidos': binarios,
            'coincidencias': coincidencias, 'truncado': cortada is not None, 'cortada': cortada, 'aviso': aviso}


def documento_openapi(repo: Path) -> tuple[dict[str, Any], list[str]]:
    """El OpenAPI generado y sus líneas (077:RF-5). Nunca se pide a un servidor."""
    destino, _ = comprobar_ruta(repo, OPENAPI)
    texto = destino.read_text(encoding='utf-8')
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


def consultar_api(repo: Path, ruta: str, metodo: str | None = None, *, politica: Politica = RESTRINGIDA) -> dict[str, Any]:
    """Una ruta en el OpenAPI generado, sin ninguna petición (077:RF-18). Admite la plantilla o una ruta concreta.

    La política no cambia nada: el OpenAPI se lee con cualquiera."""
    del politica
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
                f'Lee un fichero del proyecto por rango de líneas, como mucho {TOPE_LINEAS} por lectura. Excel y PDF van por su lector. Solo lectura.',
                _objeto({'ruta': {'type': 'string', 'description': 'Ruta relativa al proyecto, o absoluta dentro de una raíz configurada.'},
                         'desde': {'type': 'integer', 'minimum': 1},
                         'hasta': {'type': 'integer', 'minimum': 1},
                         'hoja': {'type': 'string', 'description': 'Hoja de un libro de Excel; sin ella, la primera.'}}, ('ruta',)), leer_fichero),
    Herramienta('buscar_texto',
                f'Busca un texto literal en los ficheros permitidos, como mucho {TOPE_RESULTADOS} resultados y {TOPE_SEGUNDOS_BUSQUEDA:.0f} s; dice si corta. Solo lectura.',
                _objeto({'texto': {'type': 'string', 'minLength': 3, 'maxLength': 200},
                         'dentro': {'type': 'string', 'description': 'Carpeta donde buscar.'},
                         'tope': {'type': 'integer', 'minimum': 1, 'maximum': TOPE_RESULTADOS}}, ('texto',)), buscar_texto),
    Herramienta('consultar_api',
                'Consulta una ruta de la API en el OpenAPI generado, sin hacer ninguna petición. Solo lectura.',
                _objeto({'ruta': {'type': 'string', 'description': 'Por ejemplo /api/jobs/{job_id}.'},
                         'metodo': {'type': 'string'}}, ('ruta',)), consultar_api),
)}


def ejecutar(repo: Path, nombre: str, argumentos: Mapping[str, Any], politica: Politica = RESTRINGIDA) -> dict[str, Any]:
    """La lectura pedida, con sus argumentos comprobados contra el catálogo. La política no es un argumento del modelo."""
    herramienta = HERRAMIENTAS.get(nombre)
    if herramienta is None:
        raise ArgumentoInvalido(f'lectura fuera del catálogo: {nombre!r}')
    if not isinstance(argumentos, Mapping):
        raise ArgumentoInvalido('los argumentos van en un objeto')
    propiedades, obligatorias = herramienta.esquema['properties'], herramienta.esquema['required']
    if set(argumentos) - set(propiedades) or set(obligatorias) - set(argumentos):
        raise ArgumentoInvalido(f'argumentos de {nombre} distintos de su catálogo')
    return herramienta.funcion(repo, **dict(argumentos), politica=politica)


def catalogo() -> list[dict[str, Any]]:
    """Nombre, descripción y esquema de cada lectura: lo que ve el LLM y lo que publica el MCP."""
    return [{'nombre': h.nombre, 'descripcion': h.descripcion, 'esquema': h.esquema} for h in HERRAMIENTAS.values()]


def terminos_de_dato(texto: str, ruta: str) -> set[str]:
    """Lo que no puede salir en una búsqueda tras leer un dato local (077:RF-59): la ruta, los códigos, las siglas y los
    nombres propios. Una palabra en minúsculas se queda: bloquearlas todas dejaría la búsqueda sin uso."""
    terminos = {x for x in re.split(r'[/\\]', ruta) if len(x) >= 3}
    for palabra in re.findall(r"[^\W_][\w.\-]*", texto):
        limpia = palabra.strip('.-')
        if len(limpia) >= 3 and (any(c.isdigit() for c in limpia) or limpia[0].isupper()):
            terminos.add(limpia)
    return terminos


_RUTA_API = re.compile(r'(?<![\w/.-])(/api/[\w/{}.\-]*)')
_ENTRE_COMILLAS = re.compile(r'["`«]([^"`»\n]*[\\/][^"`»\n]*)["`»]')
_ABSOLUTA = re.compile(r'(?<![\w/.-])((?:[A-Za-z]:[\\/]|~[\\/])[^\s,;«»"\'`]+)')
_RUTA = re.compile(r'(?<![\w/\\.-])((?:\.{0,2}[\w\-][\w.\-]*|\.{1,2})(?:[/\\][\w.\-{}]+)+|\.env[\w.]*|[\w\-]+\.(?:py|tsx?|md|toml|json|jsonl|xlsx?|pdf|mdb|txt))(?::(\d+))?(?![\w/\\-])',
                   re.IGNORECASE)


def _argumentos_de_rango(linea: str | None) -> dict[str, Any]:
    if linea:
        return {'desde': max(1, int(linea) - LINEAS_NOMBRADO // 2), 'hasta': int(linea) + LINEAS_NOMBRADO // 2}
    return {'desde': 1, 'hasta': LINEAS_NOMBRADO}


def _unicos_por_nombre(repo: Path, politica: Politica) -> dict[str, list[str]]:
    """Las rutas del proyecto por nombre, con un tope de tiempo: un nombre suelto no recorre las raíces de datos."""
    limite, salida = time.monotonic() + TOPE_SEGUNDOS_NOMBRE, {}
    for _, rel in recorrer(repo, politica, con_raices=False):
        salida.setdefault(rel.rsplit('/', 1)[-1].casefold(), []).append(rel)
        if time.monotonic() >= limite:
            break
    return salida


def nombradas_en(repo: Path, pregunta: str, politica: Politica = RESTRINGIDA) -> dict[str, Any]:
    """Las lecturas que pide por sí misma una pregunta que nombra un fichero o una ruta, y las rutas rechazadas.

    Un nombre suelto, como ``indice.py``, se resuelve si en el proyecto solo hay uno así; si hay varios o ninguno
    no se adivina (077:RF-26, RF-27)."""
    pedidas: list[tuple[str, dict[str, Any]]] = []
    rechazadas: list[str] = []

    def intentar(nombre: str, linea: str | None, avisar: bool) -> None:
        try:
            comprobar_ruta(repo, nombre, politica)
        except RutaRechazada:
            if avisar:
                rechazadas.append(nombre)
            return
        pedidas.append(('leer_fichero', {'ruta': nombre.replace('\\', '/'), **_argumentos_de_rango(linea)}))

    def absoluta(m: re.Match) -> str:
        intentar(m.group(1), None, True)
        return ' '

    texto = _ENTRE_COMILLAS.sub(absoluta, pregunta or '')
    texto = _ABSOLUTA.sub(absoluta, texto)
    pedidas += [('consultar_api', {'ruta': r}) for r in _RUTA_API.findall(texto)]
    texto = _RUTA_API.sub(' ', texto)
    por_nombre: dict[str, list[str]] | None = None
    for m in _RUTA.finditer(texto):
        nombre, linea = m.group(1).rstrip('.'), m.group(2)
        if '/' not in nombre and '\\' not in nombre:
            if _es_vedada(motivo_de_rechazo(nombre, politica)):
                rechazadas.append(nombre)
                continue
            if por_nombre is None:
                por_nombre = _unicos_por_nombre(repo, politica)
            iguales = por_nombre.get(nombre.casefold(), [])
            if len(iguales) == 1:
                pedidas.append(('leer_fichero', {'ruta': iguales[0], **_argumentos_de_rango(linea)}))
            continue
        # Solo se avisa de lo que parece pedir algo vedado: «kV/km» o «y/o» también tienen forma de ruta.
        intentar(nombre, linea, _es_vedada(motivo_de_rechazo(nombre.replace('\\', '/'), politica)) or '..' in nombre)
    unicas = list({json.dumps(p, sort_keys=True): p for p in pedidas}.values())
    return {'pedidas': unicas[:MAX_NOMBRADAS], 'rechazadas': list(dict.fromkeys(rechazadas))}
