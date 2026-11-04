"""Comprueba lo que se entregaría: su lista, los términos prohibidos y los pesos (086:RF-33, RF-34).

Sin opciones recorre el repositorio con lo que dice `config/entrega.json`; con `--candidato DIR` recorre un
paquete ya armado (o una rueda `.whl`, por dentro), y ahí cualquier hallazgo lo rechaza. En el repositorio, los comentarios con casos reales se
cuentan pero no rechazan: `CLAUDE.md` pide citar el caso y la decisión D5 los neutraliza al empaquetar.

Los términos salen de tres sitios: los perfiles excluidos de la entrega, que siguen en el repositorio; las huellas
con sal de `config/terminos_huellas.json`, las mismas de 076:RF-6; y la lista local, fuera de git, que nombra la
variable `CSG_TERMINOS_PROHIBIDOS`. La salida solo da cifras; `--detalle FICHERO`, fuera de git, da cada lugar.

Salida: 0 si se puede entregar, 2 si se rechaza, 1 si no se pudo comprobar.
"""
import argparse
import ast
import fnmatch
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import tokenize
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
MANIFIESTO = RAIZ / 'config' / 'entrega.json'
HUELLAS = RAIZ / 'config' / 'terminos_huellas.json'
VARIABLE_LISTA_LOCAL = 'CSG_TERMINOS_PROHIBIDOS'
#: Carpetas que nunca se recorren: en una raíz de desarrollo pesan gigas y ninguna se entrega.
_PODAR = {'.git', '.venv', '.worktrees', 'node_modules', 'output', '__pycache__', '.pytest_cache', '.pytest_tmp'}
#: Palabras corrientes que también son nombres de zonas o de barras: marcarlas taparía los hallazgos verdaderos.
COMUNES = frozenset({
    'norte', 'sur', 'este', 'oeste', 'centro', 'nueva', 'nuevo', 'rural', 'urbano', 'urbana', 'barra', 'sistema', 'sein', 'otros', 'todos',
    'independencia', 'puerto', 'puente', 'pueblo', 'parque', 'alto', 'bajo', 'santa', 'santo', 'san', 'grande', 'industrial', 'minera',
    'nodo', 'zona', 'carga', 'cargas', 'linea', 'lineas', 'central', 'prueba', 'fija', 'fijas', 'tramo', 'fase', 'real', 'libre', 'lote',
    'costa', 'llegada', 'salida', 'estacion', 'playa', 'campo', 'valle', 'cabecera', 'derivacion', 'sector', 'empresa', 'proyecto',
    'pausa',
})
_TOKEN = re.compile(r'[a-z0-9]+')
_EXT_TEXTO = {'.py', '.ts', '.tsx', '.js', '.mjs', '.css', '.html', '.json', '.md', '.txt', '.yaml', '.yml', '.toml', '.bat', '.ps1',
              '.ini', '.cfg', '.svg', '.map'}


class EntregaError(ValueError):
    """La lista de la entrega o la de términos no se puede usar."""


def normalizar(texto: Any) -> str:
    """Solo letras y cifras: un guion bajo, una tilde o una mayúscula no esconden un nombre (076:RF-6)."""
    plano = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(_TOKEN.findall(plano))


def huella(termino: str, sal: str = '086') -> str:
    """La misma forma de 076:RF-6: sha256('sal:texto normalizado')[:16]; la lista se versiona sin los nombres."""
    return hashlib.sha256(f'{sal}:{normalizar(termino)}'.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- manifiesto
def leer_manifiesto(ruta: Path | str = MANIFIESTO) -> dict[str, Any]:
    try:
        datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise EntregaError(f'No se pudo leer la lista de la entrega {ruta}: {exc}') from exc
    faltan = [c for c in ('incluir', 'excluir', 'extensiones_pesos', 'pesos_permitidos', 'extensiones_datos') if c not in datos]
    if faltan:
        raise EntregaError(f'A la lista de la entrega le falta: {", ".join(faltan)}.')
    return datos


def _casa(ruta: str, patrones: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(ruta, p) for p in patrones)


def entra(ruta: str, manifiesto: Mapping[str, Any]) -> bool:
    """Si la ruta relativa entra en el paquete, según la lista declarativa; excluir manda."""
    return not _casa(ruta, manifiesto['excluir']) and _casa(ruta, manifiesto['incluir'])


def _recorrer(raiz: Path) -> Iterator[tuple[Path, str]]:
    for carpeta, subcarpetas, ficheros in os.walk(raiz):
        subcarpetas[:] = sorted(s for s in subcarpetas if s not in _PODAR)
        for nombre in sorted(ficheros):
            ruta = Path(carpeta) / nombre
            yield ruta, ruta.relative_to(raiz).as_posix()


def ficheros_de_la_entrega(raiz: Path, manifiesto: Mapping[str, Any]) -> list[tuple[Path, str]]:
    """Lo que el instalador metería, y en vez de lo compilado, su fuente: el árbol puede no tenerlo compilado."""
    fuentes = manifiesto.get('fuente_de_lo_compilado') or {}
    compilados = list(fuentes)
    de_compilado = [p for lista in fuentes.values() for p in lista]
    return [(r, rel) for r, rel in _recorrer(raiz)
            if (entra(rel, manifiesto) and not _casa(rel, compilados))
            or (_casa(rel, de_compilado) and not _casa(rel, manifiesto['excluir']))]


# --------------------------------------------------------------------------- términos
@dataclass
class Terminos:
    planos: dict[str, str] = field(default_factory=dict)
    #: (sal, huella) → categoría.
    huellas: dict[tuple[str, str], str] = field(default_factory=dict)
    origenes: list[str] = field(default_factory=list)

    def anadir(self, termino: Any, categoria: str) -> None:
        n = normalizar(termino)
        if len(n) < 4 or n.isdigit() or n in COMUNES:
            return
        self.planos.setdefault(n, categoria)
        # «Compania Ejemplo» también puede estar escrita junta, o en un identificador.
        if ' ' in n:
            self.planos.setdefault(n.replace(' ', ''), categoria)

    @property
    def sales(self) -> tuple[str, ...]:
        return tuple(sorted({s for s, _ in self.huellas}))


def _nombres_de_estructura(x: Any, clave: str = '') -> Iterator[tuple[str, str]]:
    """Los nombres de una estructura de red: los mismos campos que lee 076:RF-6."""
    if isinstance(x, Mapping):
        for k, v in x.items():
            if str(k).startswith('_'):
                continue
            if clave == 'sistemas':
                yield str(k), 'sistema'
            yield from _nombres_de_estructura(v, str(k))
    elif isinstance(x, list):
        for v in x:
            yield from _nombres_de_estructura(v, clave)
    elif isinstance(x, str) and clave in ('nombre', 'codigo', 'sistema'):
        yield x, clave


def terminos_de_los_perfiles_excluidos(raiz: Path, manifiesto: Mapping[str, Any], terminos: Terminos) -> None:
    """Los perfiles que no se entregan dicen qué no se puede entregar: no hay que volver a escribir sus nombres."""
    carpeta = raiz / 'config' / 'perfiles'
    excluidos = 0
    for ruta in sorted(carpeta.glob('*.json')) if carpeta.is_dir() else ():
        if entra(f'config/perfiles/{ruta.name}', manifiesto):
            continue
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise EntregaError(f'No se pudo leer el perfil excluido {ruta.name}: {exc}') from exc
        if ruta.name.endswith('.estructura.json'):
            for nombre, tipo in _nombres_de_estructura(datos):
                terminos.anadir(nombre, 'codigo de alimentador o SET' if tipo == 'codigo' else 'zona, SET o sistema')
            continue
        for clave in ('empresa', 'codigo_empresa'):
            terminos.anadir(datos.get(clave), 'empresa')
        libro = (datos.get('informes') or {}).get('libro_informe') or {}
        for nombre in libro.get('prohibidos') or ():
            terminos.anadir(nombre, 'cliente o expediente')
        excluidos += 1
    # Sin su nombre: esta línea sale en la orden y se pega en las entregas.
    terminos.origenes.append(f'perfiles excluidos: {excluidos}')


def leer_huellas(ruta: Path, terminos: Terminos) -> None:
    """Sin lista local también se comprueba: por eso una lista mínima va en git, y solo como huellas."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise EntregaError(f'No se pudo leer la lista de huellas {ruta}: {exc}') from exc
    n = 0
    for sal, categorias in (datos.get('huellas') or {}).items():
        for categoria, lista in categorias.items():
            for h in lista:
                terminos.huellas[(sal, h)] = categoria
                n += 1
    terminos.origenes.append(f'huellas en git: {n}')


def leer_lista_local(ruta: Path, terminos: Terminos) -> None:
    """Un JSON ``{categoría: [términos]}`` o un texto con un término por línea; vive fuera de git (RF-33)."""
    try:
        texto = Path(ruta).read_text(encoding='utf-8')
    except OSError as exc:
        raise EntregaError(f'No se pudo leer la lista local de términos {ruta}: {exc}') from exc
    if Path(ruta).suffix.lower() == '.json':
        try:
            datos = json.loads(texto)
        except ValueError as exc:
            raise EntregaError(f'La lista local de términos {ruta} no es un JSON válido: {exc}') from exc
        if not isinstance(datos, Mapping):
            raise EntregaError('La lista local de términos debe ser {categoría: [términos]}.')
        for categoria, lista in datos.items():
            for t in lista:
                terminos.anadir(t, str(categoria))
    else:
        for linea in texto.splitlines():
            if linea.strip() and not linea.lstrip().startswith('#'):
                terminos.anadir(linea, 'lista local')
    terminos.origenes.append('lista local')


def cargar_terminos(raiz: Path = RAIZ, manifiesto: Mapping[str, Any] | None = None, *, huellas: Path | None = None,
                    lista_local: Path | str | None = None) -> Terminos:
    manifiesto = leer_manifiesto() if manifiesto is None else manifiesto
    terminos = Terminos()
    terminos_de_los_perfiles_excluidos(raiz, manifiesto, terminos)
    leer_huellas(HUELLAS if huellas is None else huellas, terminos)
    local = lista_local if lista_local is not None else os.environ.get(VARIABLE_LISTA_LOCAL, '').strip()
    if local:
        leer_lista_local(Path(local), terminos)
    else:
        terminos.origenes.append(f'sin lista local ({VARIABLE_LISTA_LOCAL})')
    return terminos


# --------------------------------------------------------------------------- comentarios
def _codigo_py(texto: str) -> list[str]:
    """Las líneas sin comentarios ni docstrings: D5 los neutraliza al empaquetar; lo demás se ve o se ejecuta."""
    lineas = texto.splitlines()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
            if tok.type == tokenize.COMMENT:
                fila = tok.start[0] - 1
                lineas[fila] = lineas[fila][:tok.start[1]]
        for nodo in ast.walk(ast.parse(texto)):
            if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant) and isinstance(nodo.value.value, str):
                for fila in range(nodo.lineno - 1, nodo.end_lineno or nodo.lineno):
                    lineas[fila] = ''
    except (SyntaxError, tokenize.TokenError, IndentationError, ValueError):
        # Lo que no se puede analizar cuenta entero como código: mejor un aviso de más que uno de menos.
        return texto.splitlines()
    return lineas


_COMENTARIO_TS = re.compile(r'''("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)|(/\*.*?\*/|(?<![:\w])//[^\n]*)''', re.S)


def _codigo_ts(texto: str) -> list[str]:
    return _COMENTARIO_TS.sub(lambda m: m.group(1) or '\n' * m.group(2).count('\n'), texto).splitlines()


def lineas_de_codigo(nombre: str, texto: str) -> list[str]:
    """Cada línea del fichero con sus comentarios en blanco; en un JSON o un texto, lo escrito cuenta entero."""
    sufijo = Path(nombre).suffix.lower()
    if sufijo == '.py':
        return _codigo_py(texto)
    if sufijo in ('.ts', '.tsx', '.js', '.mjs', '.css'):
        return _codigo_ts(texto)
    return texto.splitlines()


# --------------------------------------------------------------------------- búsqueda
def _buscar(linea: str, terminos: Terminos, memoria: dict[str, str | None]) -> Iterator[tuple[str, str]]:
    """(término o huella, categoría) de cada ventana de una a cuatro palabras de la línea."""
    palabras = _TOKEN.findall(unicodedata.normalize('NFKD', linea).encode('ascii', 'ignore').decode().lower())
    for n in range(1, 5):
        for i in range(len(palabras) - n + 1):
            trozo = ' '.join(palabras[i:i + n])
            if trozo not in memoria:
                categoria = terminos.planos.get(trozo)
                if categoria is None:
                    for sal in terminos.sales:
                        categoria = terminos.huellas.get((sal, hashlib.sha256(f'{sal}:{trozo}'.encode()).hexdigest()[:16]))
                        if categoria:
                            break
                memoria[trozo] = categoria
            if memoria[trozo]:
                yield trozo, memoria[trozo]


@dataclass(frozen=True)
class Hallazgo:
    ruta: str
    linea: int
    categoria: str
    #: «codigo» o «comentario». Lo escrito en una lista o en un JSON cuenta como código.
    clase: str
    termino: str


def buscar_en_texto(rel: str, texto: str, terminos: Terminos, memoria: dict[str, str | None] | None = None) -> list[Hallazgo]:
    memoria = {} if memoria is None else memoria
    codigo = lineas_de_codigo(rel, texto)
    salida = []
    for n, linea in enumerate(texto.splitlines(), 1):
        vistos = set()
        for termino, categoria in _buscar(codigo[n - 1] if n <= len(codigo) else '', terminos, memoria):
            vistos.add(termino)
            salida.append(Hallazgo(rel, n, categoria, 'codigo', termino))
        for termino, categoria in _buscar(linea, terminos, memoria):
            if termino not in vistos:
                salida.append(Hallazgo(rel, n, categoria, 'comentario', termino))
    return salida


def _es_peso_por_contenido(ruta: Path) -> bool:
    """Un peso renombrado sigue siendo un peso: GGUF y los ZIP de PyTorch se reconocen por dentro."""
    try:
        with ruta.open('rb') as f:
            cabeza = f.read(8)
        if cabeza.startswith(b'GGUF'):
            return True
        if cabeza.startswith(b'PK') and ruta.suffix.lower() not in ('.docx', '.xlsx', '.whl', '.zip'):
            with zipfile.ZipFile(ruta) as z:
                return any(n.endswith('data.pkl') for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return False


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


def motivo_de_peso(ruta: Path, rel: str, manifiesto: Mapping[str, Any]) -> str | None:
    """RF-34: un peso solo entra declarado, con su huella y con datos que no sean de otra empresa."""
    if Path(rel).suffix.lower() not in manifiesto['extensiones_pesos'] and not _es_peso_por_contenido(ruta):
        return None
    admitidos = manifiesto.get('entrenados_admitidos') or ()
    for p in manifiesto['pesos_permitidos']:
        if p.get('ruta') == rel:
            if p.get('entrenado_con') not in admitidos:
                return f'peso entrenado con «{p.get("entrenado_con")}», que no se admite'
            return None if _sha256(ruta) == p.get('sha256') else 'peso con otra huella que la declarada'
    return 'peso no declarado en la lista de la entrega'


@dataclass
class Informe:
    ficheros: int = 0
    hallazgos: list[Hallazgo] = field(default_factory=list)
    #: Ficheros que no pueden entrar, con su motivo: pesos, datos y lo que la lista no admite.
    rechazos: list[tuple[str, str]] = field(default_factory=list)
    binarios_sin_leer: list[str] = field(default_factory=list)
    candidato: bool = False
    origenes: list[str] = field(default_factory=list)
    #: Del paquete armado: ficheros de terceros (solo huella) y pesos que traen sus ruedas, para mirarlos.
    terceros: int = 0
    pesos_terceros: list[str] = field(default_factory=list)
    ruedas_propias: int = 0

    @property
    def en_codigo(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.clase == 'codigo']

    @property
    def en_comentarios(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.clase == 'comentario']

    @property
    def rechazado(self) -> bool:
        # En un paquete ya no debe quedar ni un comentario con el caso real (D5); en el repositorio sí se escriben.
        return bool(self.rechazos or self.en_codigo or (self.candidato and self.hallazgos))

    def resumen(self) -> dict[str, Any]:
        """Solo cifras: este resumen se puede pegar en una entrega sin escribir ningún nombre."""
        def zona(rel: str) -> str:
            partes = rel.split('/')
            return '/'.join(partes[:2]) if partes[0] in ('src', 'frontend') and len(partes) > 1 else partes[0]

        return {
            'rechazado': self.rechazado,
            'modo': 'candidato' if self.candidato else 'repositorio',
            'ficheros': self.ficheros,
            'terminos': {'total': len(self.hallazgos), 'en_codigo': len(self.en_codigo), 'en_comentarios': len(self.en_comentarios)},
            'por_categoria_y_clase': {f'{c} / {k}': n for (c, k), n in sorted(Counter((h.categoria, h.clase) for h in self.hallazgos).items())},
            'por_zona_y_clase': {f'{z} / {k}': n for (z, k), n in sorted(Counter((zona(h.ruta), h.clase) for h in self.hallazgos).items())},
            'ficheros_con_terminos': len({h.ruta for h in self.hallazgos}),
            'rechazos': [{'ruta': r, 'motivo': m} for r, m in self.rechazos],
            'binarios_sin_leer': len(self.binarios_sin_leer),
            'listas': self.origenes,
            'terceros': {'ficheros': self.terceros, 'pesos_en_sus_ruedas': self.pesos_terceros},
        }


def _revisar_fichero(ruta: Path, rel: str, manifiesto: Mapping[str, Any], terminos: Terminos, informe: Informe,
                     memoria: dict[str, str | None]) -> None:
    motivo = motivo_de_peso(ruta, rel, manifiesto)
    if motivo:
        informe.rechazos.append((rel, motivo))
        return
    sufijo = ruta.suffix.lower()
    if sufijo in manifiesto['extensiones_datos']:
        informe.rechazos.append((rel, f'fichero de datos {sufijo}'))
        return
    # METADATA lleva el README del proyecto entero: si contara como binario, un nombre pasaría por ahí.
    if sufijo not in _EXT_TEXTO and Path(rel).name not in ('LICENSE', 'METADATA', 'RECORD', 'WHEEL'):
        informe.binarios_sin_leer.append(rel)
        return
    informe.hallazgos += buscar_en_texto(rel, ruta.read_text(encoding='utf-8', errors='replace'), terminos, memoria)


#: De la rueda propia a la ruta del repositorio, que es en lo que está escrita la lista.
_RUEDA_A_REPOSITORIO = (('convertersmartgrid/_programa/', ''), ('convertersmartgrid/', 'src/convertersmartgrid/'),
                        ('vnr_etl/', 'src/vnr_etl/'))


def ruta_en_el_repositorio(nombre: str) -> str | None:
    """Dónde estaría en el repositorio un fichero de la rueda; None en sus metadatos («…dist-info/»)."""
    for prefijo, destino in _RUEDA_A_REPOSITORIO:
        if nombre.startswith(prefijo):
            return destino + nombre[len(prefijo):]
    return None


def comprobar_rueda(rueda: Path, manifiesto: Mapping[str, Any], terminos: Terminos, informe: Informe,
                    memoria: dict[str, str | None]) -> None:
    """La rueda se abre y se mira por dentro: si no, un perfil o un peso metidos en ella pasarían como un binario."""
    try:
        with tempfile.TemporaryDirectory(prefix='csg-rueda-') as temporal, zipfile.ZipFile(rueda) as z:
            carpeta = Path(temporal)
            for entrada in z.infolist():
                if entrada.is_dir():
                    continue
                informe.ficheros += 1
                rel = ruta_en_el_repositorio(entrada.filename)
                if rel is not None and not entra(rel, manifiesto):
                    informe.rechazos.append((f'{rueda.name}!{entrada.filename}', 'no está en la lista de la entrega'))
                    continue
                destino = carpeta / f'{informe.ficheros}{Path(entrada.filename).suffix}'
                destino.write_bytes(z.read(entrada))
                # El nombre real es el que se informa y el que decide si un peso está declarado.
                _revisar_fichero(destino, rel if rel is not None else entrada.filename, manifiesto, terminos, informe, memoria)
                destino.unlink()
    except (OSError, zipfile.BadZipFile) as exc:
        informe.rechazos.append((rueda.name, f'la rueda no se puede abrir: {exc}'))


def _nombre_de_rueda(nombre: str) -> str:
    return nombre.split('-')[0].replace('_', '-').lower()


def _comprobar_huellas(candidato: Path, informe: Informe) -> None:
    """RF-39: cada fichero del paquete, con la huella que anotó quien lo armó, y ninguno sin anotar."""
    try:
        datos = json.loads((candidato / 'manifiesto_candidato.json').read_text(encoding='utf-8'))
        anotados = {f['ruta']: f['sha256'] for f in datos['ficheros']}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        informe.rechazos.append(('manifiesto_candidato.json', f'no se puede leer: {exc}'))
        return
    presentes = {rel: ruta for ruta, rel in _recorrer(candidato) if rel != 'manifiesto_candidato.json'}
    for rel in sorted(set(anotados) - set(presentes)):
        informe.rechazos.append((rel, 'anotado en el manifiesto y ausente'))
    for rel in sorted(set(presentes) - set(anotados)):
        informe.rechazos.append((rel, 'presente y sin anotar en el manifiesto'))
    for rel in sorted(set(presentes) & set(anotados)):
        if _sha256(presentes[rel]) != anotados[rel]:
            informe.rechazos.append((rel, 'huella distinta de la del manifiesto'))


def comprobar_paquete(candidato: Path, manifiesto: Mapping[str, Any], terminos: Terminos, informe: Informe) -> None:
    """El paquete que arma tools/construir_candidato.py, con su rueda, sus terceros y su manifiesto (086:RF-36, RF-37)."""
    forma = manifiesto.get('candidato') or {}
    memoria: dict[str, str | None] = {}
    _comprobar_huellas(candidato, informe)
    fuera = set(forma.get('fuera_del_nucleo') or ())
    for ruta, rel in _recorrer(candidato):
        if rel == 'manifiesto_candidato.json':
            continue
        if _casa(rel, forma.get('terceros') or ()):
            informe.terceros += 1
            if ruta.suffix == '.whl':
                if _nombre_de_rueda(ruta.name) in fuera:
                    informe.rechazos.append((rel, 'esta rueda no forma parte del núcleo'))
                try:
                    with zipfile.ZipFile(ruta) as z:
                        informe.pesos_terceros += [f'{ruta.name}!{n}' for n in z.namelist()
                                                   if Path(n).suffix.lower() in manifiesto['extensiones_pesos']]
                except zipfile.BadZipFile as exc:
                    informe.rechazos.append((rel, f'la rueda no se puede abrir: {exc}'))
            continue
        if fnmatch.fnmatchcase(rel, forma.get('rueda_propia') or ''):
            informe.ruedas_propias += 1
            comprobar_rueda(ruta, manifiesto, terminos, informe, memoria)
            continue
        informe.ficheros += 1
        if not _casa(rel, forma.get('raices') or ()):
            informe.rechazos.append((rel, 'no está en la lista de la entrega'))
            continue
        _revisar_fichero(ruta, rel, manifiesto, terminos, informe, memoria)
    if informe.ruedas_propias != 1:
        informe.rechazos.append(('programa', f'se esperaba una rueda propia y hay {informe.ruedas_propias}'))


def comprobar(raiz: Path, manifiesto: Mapping[str, Any], terminos: Terminos, *, candidato: Path | None = None) -> Informe:
    """Recorre el repositorio según la lista o un paquete armado; no escribe nada."""
    informe = Informe(candidato=candidato is not None, origenes=list(terminos.origenes))
    if candidato is not None and candidato.is_file():
        comprobar_rueda(candidato, manifiesto, terminos, informe, {})
        return informe
    if candidato is not None and (candidato / 'manifiesto_candidato.json').is_file():
        comprobar_paquete(candidato, manifiesto, terminos, informe)
        return informe
    pares = list(_recorrer(candidato)) if candidato is not None else ficheros_de_la_entrega(raiz, manifiesto)
    memoria: dict[str, str | None] = {}
    for ruta, rel in pares:
        informe.ficheros += 1
        if candidato is not None and not entra(rel, manifiesto):
            informe.rechazos.append((rel, 'no está en la lista de la entrega'))
            continue
        _revisar_fichero(ruta, rel, manifiesto, terminos, informe, memoria)
    return informe


# --------------------------------------------------------------------------- neutralizar (D5)
_MARCA_NEUTRA = '[caso]'


def _palabras_con_posicion(linea: str) -> list[tuple[str, int, int]]:
    """Las mismas palabras que ``_buscar``, con dónde están: un carácter sin ASCII no corta la palabra."""
    salida: list[tuple[str, int, int]] = []
    actual, inicio = '', 0
    for i, caracter in enumerate(linea):
        plano = unicodedata.normalize('NFKD', caracter).encode('ascii', 'ignore').decode().lower()
        if plano and not _TOKEN.fullmatch(plano):
            if actual:
                salida.append((actual, inicio, i))
            actual = ''
            continue
        if plano:
            if not actual:
                inicio = i
            actual += plano
    if actual:
        salida.append((actual, inicio, len(linea)))
    return salida


def _sustituir_termino(linea: str, termino: str) -> str:
    palabras = _palabras_con_posicion(linea)
    n = len(termino.split(' '))
    for i in range(len(palabras) - n, -1, -1):
        if ' '.join(p[0] for p in palabras[i:i + n]) == termino:
            linea = linea[:palabras[i][1]] + _MARCA_NEUTRA + linea[palabras[i + n - 1][2]:]
    return linea


def _forma_del_codigo(texto: str) -> str:
    arbol = ast.parse(texto)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Constant) and isinstance(nodo.value.value, str):
            nodo.value.value = ''
    return ast.dump(arbol)


def neutralizar(rel: str, texto: str, terminos: Terminos, memoria: dict[str, str | None] | None = None) -> tuple[str, int]:
    """Quita de los comentarios y docstrings los términos prohibidos, conservando el motivo (D5).

    Solo lo no ejecutable: un término en el código sigue siendo un hallazgo, que es un fallo que hay que
    arreglar y no tapar. En un .py se comprueba además que el programa compilado no cambia de forma.
    """
    memoria = {} if memoria is None else memoria
    hallazgos = [h for h in buscar_en_texto(rel, texto, terminos, memoria) if h.clase == 'comentario']
    if not hallazgos:
        return texto, 0
    lineas = texto.splitlines(keepends=True)
    for h in hallazgos:
        lineas[h.linea - 1] = _sustituir_termino(lineas[h.linea - 1], h.termino)
    nuevo = ''.join(lineas)
    if rel.endswith('.py') and _forma_del_codigo(nuevo) != _forma_del_codigo(texto):
        raise EntregaError(f'Neutralizar {rel} cambiaría su código.')
    return nuevo, len(hallazgos)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--candidato', type=Path, help='paquete ya armado, en carpeta o una rueda .whl: rechaza cualquier hallazgo, también en comentarios')
    parser.add_argument('--manifiesto', type=Path, default=MANIFIESTO, help='lista de la entrega (config/entrega.json)')
    parser.add_argument('--lista-local', type=Path, help=f'lista de términos fuera de git; por defecto, {VARIABLE_LISTA_LOCAL}')
    parser.add_argument('--detalle', type=Path, help='escribe cada lugar con su término: fuera de git, porque lleva los nombres')
    args = parser.parse_args(argv)
    try:
        manifiesto = leer_manifiesto(args.manifiesto)
        terminos = cargar_terminos(RAIZ, manifiesto, lista_local=args.lista_local)
        if args.candidato is not None and not (args.candidato.is_dir() or args.candidato.suffix == '.whl' and args.candidato.is_file()):
            raise EntregaError(f'El candidato {args.candidato} no es una carpeta ni una rueda.')
        informe = comprobar(RAIZ, manifiesto, terminos, candidato=args.candidato)
    except EntregaError as exc:
        print(f'No se pudo comprobar la entrega: {exc}', file=sys.stderr)
        return 1
    if args.detalle:
        args.detalle.write_text('\n'.join(f'{h.ruta}:{h.linea}\t{h.clase}\t{h.categoria}\t{h.termino}' for h in informe.hallazgos) + '\n',
                                encoding='utf-8')
    print(json.dumps(informe.resumen(), ensure_ascii=False, indent=2))
    return 2 if informe.rechazado else 0


if __name__ == '__main__':
    raise SystemExit(main())
