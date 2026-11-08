"""Genera docs/ARQUITECTURA_CATALOGO.md desde el propio repositorio (spec 090).

    python tools/generar_arquitectura.py --escribir       # reescribe el catálogo
    python tools/generar_arquitectura.py --comprobar      # sale con 1 si no está al día
    python tools/generar_arquitectura.py --instalar-ganchos

La arquitectura escrita a mano decía 97 excepciones de capas cuando había 37, y tres carriles cuando había
cuatro, dos días después de revisarla. Aquí lo que cambia con el código sale del código. El producto se lee con
``ast``, sin importarlo: el gancho de git no carga FastAPI ni PyTorch, y puede leer del índice en vez del árbol,
donde puede haber cambios sin confirmar de otra sesión (090:RF-12).
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = 'docs/ARQUITECTURA_CATALOGO.md'
MAPA = 'docs/architecture/subsistemas.json'
RAICES = ('src/convertersmartgrid/', 'src/vnr_etl.py', 'tools/', 'frontend/src/', 'frontend/scripts/', 'frontend/test/')
OTROS = ('config/', 'instalador/', '.githooks/')
S = 'src/convertersmartgrid/'
#: Lo que el generador necesita leer, también para copiarlo a un repositorio de prueba.
FUENTES = ('pyproject.toml', 'CODIGO_FUENTE.md', MAPA, 'docs/implementacion065/deuda_arquitectura.json',
           S + 'asistente/tareas.py', S + 'asistente/equipo.py', S + 'asistente/revision_roles.py',
           S + 'asistente/orquestador.py', S + 'asistente/interprete.py', S + 'asistente/transformer.py',
           S + 'training_coordinator.py', S + 'edicion.py', S + 'web/jobs.py', S + 'web/app.py', S + 'web/services.py',
           'src/convertersmartgrid/adaptadores/entrada/vnr/web/app.py')
_RUTA = re.compile(r'@(?:router|app)\.(?:get|post|put|patch|delete|websocket)\(\s*f?[\'"]([^\'"]+)')
_FILA = re.compile(r'^\| `([^`]+)` \| (.*) \| ([^|]*) \|\s*$', re.M)
_RF = re.compile(r'^- (RF-\d+[a-z]?):', re.M)
_ESTADO = re.compile(r'^Estado: *(\w+)', re.M)
NOMBRES_CAPA = {'dominio': 'Dom', 'puertos': 'Pue', 'aplicacion': 'Apl', 'adaptadores': 'Ada', 'presentacion': 'Pre'}


class Fuente:
    """Lee del árbol o, en un commit, del índice: lo que de verdad entra en él (090:RF-12)."""

    def __init__(self, raiz: Path = RAIZ, indice: bool = False):
        self.raiz, self.indice = Path(raiz), indice

    def _git(self, *args: str) -> bytes:
        return subprocess.run(['git', '-C', str(self.raiz), *args], capture_output=True, check=True).stdout

    def ficheros(self) -> list[str]:
        """Solo lo versionado: un fichero suelto de otra sesión no es de este commit."""
        nombres = self._git('ls-files', '-c', '-z').decode('utf-8').split('\0')
        return sorted(n for n in nombres if n and (self.indice or (self.raiz / n).is_file()))

    def leer(self, ruta: str) -> str:
        crudo = self._git('show', f':{ruta}') if self.indice else (self.raiz / ruta).read_bytes()
        return crudo.decode('utf-8-sig').replace('\r\n', '\n')


# ------------------------------------------------------------------- lectura de constantes sin importar
def _valor(nodo: ast.AST, conocidas: dict) -> object:
    """Una constante del módulo: literales, tuplas con ``*OTRA`` y ``frozenset({...})``."""
    if isinstance(nodo, ast.Call) and getattr(nodo.func, 'id', '') == 'frozenset':
        return _valor(nodo.args[0], conocidas)
    if isinstance(nodo, ast.Name):
        return conocidas[nodo.id]
    if isinstance(nodo, (ast.Tuple, ast.List, ast.Set)):
        salida = []
        for e in nodo.elts:
            if isinstance(e, ast.Starred):
                salida.extend(_valor(e.value, conocidas))
            else:
                salida.append(_valor(e, conocidas))
        return tuple(salida)
    return ast.literal_eval(nodo)


def _asignaciones(texto: str) -> dict[str, ast.AST]:
    salida = {}
    for n in ast.parse(texto).body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            salida[n.targets[0].id] = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            salida[n.target.id] = n.value
    return salida


def constante(texto: str, nombre: str) -> object:
    asignadas = _asignaciones(texto)
    conocidas: dict = {}
    for n, v in asignadas.items():
        try:
            conocidas[n] = _valor(v, conocidas)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            continue
    return conocidas[nombre]


def _arg(llamada: ast.Call, posicion: int, nombre: str, defecto: object = None) -> ast.AST | object:
    for k in llamada.keywords:
        if k.arg == nombre:
            return k.value
    return llamada.args[posicion] if posicion < len(llamada.args) else defecto


def _literal(nodo: object, defecto: object = None) -> object:
    return ast.literal_eval(nodo) if isinstance(nodo, ast.AST) else (nodo if nodo is not None else defecto)


def _dato(llamada: ast.Call) -> dict:
    return {'nombre': _literal(_arg(llamada, 0, 'nombre')), 'obligatorio': _literal(_arg(llamada, 2, 'obligatorio'), True)}


def tareas(texto: str) -> list[dict]:
    """Las tareas de ``asistente/tareas.py``, una a una, tal como están escritas."""
    asignadas = _asignaciones(texto)
    datos = {n: _dato(v) for n, v in asignadas.items() if isinstance(v, ast.Call) and getattr(v.func, 'id', '') == 'Dato'}
    salida = []
    for t in asignadas['_TAREAS'].elts:
        propios = []
        contenedor = _arg(t, 2, 'datos')
        for nodo in ast.walk(contenedor):
            if isinstance(nodo, ast.Name) and nodo.id in datos:
                propios.append(datos[nodo.id])
            elif isinstance(nodo, ast.Call) and getattr(nodo.func, 'id', '') == 'Dato':
                propios.append(_dato(nodo))
        salida.append({'nombre': _literal(_arg(t, 0, 'nombre')), 'descripcion': _literal(_arg(t, 1, 'descripcion')),
                       'datos': propios, 'escribe': _literal(_arg(t, 3, 'escribe')), 'modo': _literal(_arg(t, 4, 'modo')),
                       'funcion': _literal(_arg(t, 5, 'funcion'))})
    return salida


def etapas(texto: str, nombre: str) -> list[dict]:
    salida = []
    for e in _asignaciones(texto)[nombre].elts:
        salida.append({'nombre': _literal(_arg(e, 0, 'nombre')), 'tarea': _literal(_arg(e, 1, 'tarea')),
                       'opcional': _literal(_arg(e, 99, 'opcional'), False), 'proceso': _literal(_arg(e, 99, 'proceso'), False),
                       'condicion': _literal(_arg(e, 99, 'condicion'), '')})
    return salida


def roles(equipo: str, revision: str) -> list[dict]:
    """El equipo: quién ejecuta lo dice ``inventario_equipo``; un modelo nunca concede autoridad."""
    revisores = constante(equipo, 'ROLES_REVISION')
    lectores = constante(equipo, 'ROLES_LECTURA')
    encargo = constante(revision, '_ENCARGO')
    fijos = {'operador': 'Confirma cada escritura y es el único que ejecuta.',
             'cliente_mcp': 'Un cliente MCP de esta máquina: solo las lecturas del proyecto.'}
    return [{'rol': r, 'ejecuta': r == 'operador', 'lee': r in lectores,
             'encargo': fijos.get(r) or 'Revisa ' + encargo[r]} for r in dict.fromkeys(('operador', *revisores, *lectores))]


def rutas(texto: str) -> Counter:
    """Rutas por familia. Una ruta de espacio cuenta por su primer segmento tras ``{id}``."""
    familias: Counter = Counter()
    for ruta in _RUTA.findall(texto):
        ruta = re.sub(r'^/api', '', ruta)
        espacio = re.match(r'/workspaces/\{[^}]+\}/?', ruta)
        resto = ruta[espacio.end():] if espacio else ruta
        nombre = resto.strip('/').split('/')[0] or '(raíz)'
        familias[('espacio' if espacio else 'general', nombre)] += 1
    return familias


# ------------------------------------------------------------------- del índice y de las capas
def indice_de_codigo(texto: str) -> dict[str, tuple[str, str]]:
    return {m[1]: (m[2].strip(), m[3].strip()) for m in _FILA.finditer(texto)}


def papel_corto(texto: str, tope: int = 150) -> str:
    """La primera frase: el detalle y los RF siguen en CODIGO_FUENTE.md."""
    corte = re.search(r'(?<=[^.\s])(\.\s|;\s|\.$)', texto)
    frase = texto[:corte.start() + 1] if corte and corte.group(1).startswith('.') else texto[:corte.start()] + '.' if corte else texto
    if len(frase) > tope:
        frase = frase[:tope].rsplit(' ', 1)[0] + '…'
    return frase


def specs_de(texto: str) -> str:
    return ', '.join(dict.fromkeys(re.findall(r'\b\d{3}\b', texto))) or '—'


def modulo_de(ruta: str) -> str | None:
    if not ruta.startswith('src/') or not ruta.endswith('.py'):
        return None
    nombre = ruta[4:-3].replace('/', '.')
    return nombre[:-9] if nombre.endswith('.__init__') else nombre


def _docstring(fuente: Fuente, ruta: str) -> str:
    if ruta.endswith('.py'):
        try:
            doc = ast.get_docstring(ast.parse(fuente.leer(ruta)))
        except SyntaxError:
            doc = None
        if doc:
            return doc.strip().split('\n')[0]
    return 'Sin descripción en `CODIGO_FUENTE.md`.'


def _tabla(cabecera: tuple[str, ...], filas: list[tuple]) -> list[str]:
    return ['| ' + ' | '.join(cabecera) + ' |', '| ' + ' | '.join('---' for _ in cabecera) + ' |',
            *('| ' + ' | '.join(str(c) for c in fila) + ' |' for fila in filas)]


def _si(valor: bool) -> str:
    return 'sí' if valor else 'no'


# ------------------------------------------------------------------- el documento
def documento(fuente: Fuente) -> str:
    """El catálogo entero. Sin fechas ni revisiones: el mismo contenido da el mismo fichero (090:RF-9)."""
    todos = fuente.ficheros()
    proyecto = tomllib.loads(fuente.leer('pyproject.toml'))
    capas = proyecto['tool']['convertersmartgrid']['capas']['modulos']
    deuda = json.loads(fuente.leer('docs/implementacion065/deuda_arquitectura.json'))
    indice = indice_de_codigo(fuente.leer('CODIGO_FUENTE.md'))
    mapa = json.loads(fuente.leer(MAPA))
    catalogables = [f for f in todos if f.startswith(RAICES)]
    modulos = [m for m in map(modulo_de, catalogables) if m]
    reparto = Counter(capas.get(m, 'sin capa') for m in modulos)

    salida = [
        '# Catálogo de la arquitectura', '',
        'Generado por `tools/generar_arquitectura.py` (spec 090): **no se edita a mano**. Un gancho de git lo regenera en cada',
        'commit y en cada fusión, y `tests/test_arquitectura_generada.py` falla si no está al día. Si hace falta a mano:',
        '`python tools/generar_arquitectura.py --escribir`. Lo que explica el porqué está en [`ARQUITECTURA.md`](ARQUITECTURA.md).', '',
        '## Cifras', '']
    grupos_tamano = (('Motor, web, gemelo y asistente', 'src/convertersmartgrid/'), ('Módulo VNR-GIS', 'src/convertersmartgrid/adaptadores/entrada/vnr/'),
                     ('Herramientas y guiones', 'tools/'), ('Interfaz', 'frontend/src/'), ('Pruebas de la interfaz', 'frontend/test/'),
                     ('Pruebas', 'tests/'), ('Pruebas de modelos', 'tests_ml/'), ('Specs', 'specs/'))
    salida += _tabla(('Parte', 'Carpeta', 'Ficheros'),
                     [(t, f'`{p}`', sum(f.startswith(p) for f in todos)) for t, p in grupos_tamano])
    servicios = fuente.leer(S + 'web/services.py')
    funciones = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.parse(servicios).body)
    salida += ['', f'`web/services.py` tiene {len(servicios.splitlines())} líneas y {funciones} funciones, pendiente de partir (002).', '']

    salida += ['### Specs', '']
    estados: Counter = Counter()
    requisitos = 0
    for f in todos:
        if re.fullmatch(r'specs/\d{3}-[^/]+/spec\.md', f):
            texto = fuente.leer(f)
            hallado = _ESTADO.search(texto)
            estados[hallado[1] if hallado else 'sin estado'] += 1
            requisitos += len(_RF.findall(texto))
    salida += _tabla(('Estado', 'Specs'), sorted(estados.items(), key=lambda e: (-e[1], e[0])))
    salida += ['', f'{sum(estados.values())} specs con {requisitos} RF. El detalle, en [`specs/README.md`](../specs/README.md).', '']

    salida += ['### Capas', '']
    salida += _tabla(('Capa', 'Abrev.', 'Módulos'), [(c, NOMBRES_CAPA.get(c, '—'), n) for c, n in sorted(reparto.items(), key=lambda e: (-e[1], e[0]))])
    salida += ['', f'{len(modulos)} módulos y {len(deuda["excepciones"])} excepciones en la deuda de `tools/arquitectura.py`.', '']

    salida += ['### Carriles de trabajos', '', ', '.join(f'`{c}`' for c in constante(fuente.leer(S + 'web/jobs.py'), 'LANES')) + '.', '']

    familias = rutas(fuente.leer(S + 'web/app.py'))
    vnr = len(_RUTA.findall(fuente.leer('src/convertersmartgrid/adaptadores/entrada/vnr/web/app.py')))
    salida += ['### Rutas de la API', '', f'{sum(familias.values())} en `web/app.py`, y {vnr} bajo `/api/vnr` en `adaptadores/entrada/vnr/web/app.py`.', '']
    salida += _tabla(('Familia', 'Ámbito', 'Rutas'), [(f'`{n}`', a, c) for (a, n), c in sorted(familias.items(), key=lambda e: (-e[1], e[0]))])

    salida += ['', '### Órdenes y módulos instalados', '']
    salida += _tabla(('Orden', 'Punto de entrada'), [(f'`{k}`', f'`{v}`') for k, v in sorted(proyecto['project']['scripts'].items())])
    salida += ['']
    salida += _tabla(('Módulo enchufable', 'Objeto'), [(f'`{k}`', f'`{v}`') for k, v in sorted(proyecto['project']['entry-points']['convertersmartgrid.modulos'].items())])

    salida += _asistente(fuente)

    salida += ['', '## Ficheros', '',
               'Papel, specs y capa salen de `CODIGO_FUENTE.md` y `pyproject.toml`. El subsistema, de `docs/architecture/subsistemas.json`.',
               'Las pruebas no se listan: cada una cita los `NNN:RF-n` que cubre.']
    vistos: set[str] = set()
    existentes = set(todos)

    def fila(ruta: str, nombre: str) -> tuple:
        papel, specs = indice.get(ruta, ('', ''))
        modulo = modulo_de(ruta)
        capa = NOMBRES_CAPA.get(capas.get(modulo, ''), '—') if modulo else '—'
        return (f'`{nombre}`', capa, specs_de(specs), papel_corto(papel) if papel else _docstring(fuente, ruta))

    cabecera = ('Fichero', 'Capa', 'Specs', 'Papel')
    for grupo in mapa['grupos']:
        propios = [grupo['base'] + f for f in grupo['ficheros'] if grupo['base'] + f in existentes]
        if not propios:
            continue
        vistos.update(propios)
        salida += ['', f"### {grupo['titulo']}", '', *_tabla(cabecera, [fila(r, r[len(grupo['base']):]) for r in propios])]
    sueltos = [f for f in catalogables if f not in vistos]
    if sueltos:
        salida += ['', '### Sin subsistema asignado', '', 'Ficheros nuevos: asígnelos en `docs/architecture/subsistemas.json`.', '',
                   *_tabla(cabecera, [fila(r, r) for r in sueltos])]
    otros = [f for f in todos if f.startswith(OTROS) or (PurePosixPath(f).parent == PurePosixPath('.') and re.match(r'(requirements|constraints|run_gui)', f))]
    salida += ['', '### Configuración, dependencias y entrega', '', *_tabla(('Fichero',), [(f'`{f}`',) for f in otros])]
    return '\n'.join(salida) + '\n'


def _asistente(fuente: Fuente) -> list[str]:
    catalogo = tareas(fuente.leer(S + 'asistente/tareas.py'))
    equipo = fuente.leer(S + 'asistente/equipo.py')
    nativas = constante(equipo, '_NATIVAS')
    fuera = constante(fuente.leer(S + 'edicion.py'), 'TAREAS_FUERA_DE_ALCANCE')
    interprete = fuente.leer(S + 'asistente/interprete.py')
    orquestador = fuente.leer(S + 'asistente/orquestador.py')
    salida = ['', '## El asistente y su equipo', '',
              f"El intérprete acepta al modelo de órdenes con confianza {constante(interprete, 'UMBRAL_TRANSFORMER')}, salvo que traiga su umbral calibrado, "
              f"y a Ollama con {constante(interprete, 'UMBRAL_OLLAMA')}.", '', '### Equipo', '']
    salida += _tabla(('Rol', 'Ejecuta', 'Lee el proyecto', 'Encargo'),
                     [(f"`{r['rol']}`", _si(r['ejecuta']), _si(r['lee']), r['encargo'])
                      for r in roles(equipo, fuente.leer(S + 'asistente/revision_roles.py'))])
    salida += ['', f'### Tareas ({len(catalogo)})', '',
               'Carril donde corre si se ejecuta; `opcional?` es un dato que no hace falta dar. «Producto» dice si queda en esa edición.', '']
    salida += _tabla(('Tarea', 'Modo', 'Escribe', 'Carril', 'Producto', 'Función', 'Datos', 'Qué hace'), [
        (f"`{t['nombre']}`", t['modo'], _si(t['escribe']), 'powerfactory' if t['nombre'] in nativas else 'engine',
         _si(t['nombre'] not in fuera), f"`{t['funcion']}`",
         ', '.join(d['nombre'] + ('' if d['obligatorio'] else '?') for d in t['datos']) or '—', t['descripcion'].replace('|', '/'))
        for t in catalogo])

    def tabla_etapas(nombre: str) -> list[str]:
        return _tabla(('Etapa', 'Tarea', 'Opcional', 'Proceso aparte', 'Condición'),
                      [(f"`{e['nombre']}`", f"`{e['tarea']}`", _si(e['opcional']), _si(e['proceso']), e['condicion'] or '—')
                       for e in etapas(orquestador, nombre)])

    salida += ['', '### Etapas del proyecto entero', '', *tabla_etapas('ETAPAS')]
    salida += ['', '### Etapas de una carga nueva', '', *tabla_etapas('ETAPAS_CARGA')]
    familias = constante(fuente.leer(S + 'asistente/transformer.py'), 'FAMILIAS_MODELOS')
    orden = constante(fuente.leer(S + 'training_coordinator.py'), 'ORDEN_MODELOS')
    salida += ['', '### Familias de modelos', '', 'Orden de entrenamiento: ' + ', '.join(f'`{m}`' for m in orden) + '.', '',
               'Con puntero en uso gobernado por `asistente/modelos_en_uso.py`: ' + ', '.join(f'`{k}` ({v})' for k, v in sorted(familias.items())) + '.',
               'Qué modelo está en uso vive en `output/`, fuera de git: ver [`ARQUITECTURA.md`](ARQUITECTURA.md#modelos-024-026-043-045-046-060-069-075-079-085).']
    return salida


# ------------------------------------------------------------------- órdenes
def _normalizado(ruta: Path) -> str | None:
    return ruta.read_bytes().decode('utf-8').replace('\r\n', '\n') if ruta.is_file() else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--escribir', action='store_true', help='reescribe el catálogo')
    grupo.add_argument('--comprobar', action='store_true', help='sale con 1 si el catálogo no está al día')
    grupo.add_argument('--instalar-ganchos', action='store_true', help='activa .githooks en este repositorio')
    p.add_argument('--desde-indice', action='store_true', help='lee del índice de git: lo usa el gancho de commit')
    p.add_argument('--anadir', action='store_true', help='añade el catálogo al índice: lo usa el gancho de commit')
    p.add_argument('--raiz', type=Path, default=RAIZ, help='raíz del repositorio')
    args = p.parse_args(argv)

    fuente = Fuente(args.raiz, indice=args.desde_indice)
    if args.instalar_ganchos:
        fuente._git('config', 'core.hooksPath', '.githooks')
        print('Ganchos activos: core.hooksPath = .githooks')
        return 0
    destino = args.raiz / SALIDA
    nuevo = documento(fuente)
    if args.comprobar:
        if _normalizado(destino) != nuevo:
            print(f'{SALIDA} no está al día: python tools/generar_arquitectura.py --escribir')
            return 1
        print(f'{SALIDA} al día')
        return 0
    if _normalizado(destino) != nuevo:
        destino.write_bytes(nuevo.encode('utf-8'))
    if args.anadir:
        fuente._git('add', '--', SALIDA)
    return 0


if __name__ == '__main__':
    sys.exit(main())
