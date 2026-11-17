"""070:RF-78 — ningún texto que la web enseña al operador cita requisitos, tareas ni specs.

Usuario (2026-11-14, aclaración de 070:RF-51): «en la web, ninguna cita de RF ni jerga». En el navegador real (15-11) salía
«… conviértalos e impórtelos antes (028:RF-23).». Se recorre lo que llega a la pantalla:
- en ``src/``, los mensajes de ``UserError`` (y de sus subclases) y el ``detail`` de ``HTTPException``, con ``ast``;
- en ``frontend/src/**/*.tsx``, los textos que se pintan (texto de JSX, atributos y cadenas), sin los comentarios ni los
  docstrings, que sí pueden citar requisitos;
- en los datos que van en la entrega (los ``config/**/*.json`` que deja entrar ``config/entrega.json`` y los que copia
  ``tools/construir_candidato.py``), todas sus cadenas: el cliente abre esos ficheros.
Lo que cuenta como cita: «RF-n», «NNN:RF», el código de una spec entre paréntesis («(028:…)», «(099)») y una tarea con su
spec o con la palabra («086 T40», «tarea T7»). «(T1, T2, T3)», transformadores de una SET, no es una tarea.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

from apoyo import cargar_herramienta

RAIZ = Path(__file__).resolve().parents[1]
CITA = re.compile(r'RF-\d|\b\d{3}:RF|\(\d{3}(?::[^)]*)?\)|\(spec \d{3}\b|(?:\b\d{3}[ :]|\btarea\s)T\d+\b')
_EXCEPCIONES_BASE = {'UserError'}


def _textos(nodo: ast.AST):
    """Las partes literales de un mensaje: cadena, f-string (sin lo interpolado), concatenación o condicional."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        yield nodo.value
    elif isinstance(nodo, ast.JoinedStr):
        yield ''.join(v.value if isinstance(v, ast.Constant) else '{}' for v in nodo.values)
    elif isinstance(nodo, ast.BinOp):
        yield from _textos(nodo.left)
        yield from _textos(nodo.right)
    elif isinstance(nodo, ast.IfExp):
        yield from _textos(nodo.body)
        yield from _textos(nodo.orelse)
    elif isinstance(nodo, (ast.List, ast.Tuple, ast.Set)):
        for e in nodo.elts:
            yield from _textos(e)


def _nombre(func: ast.AST) -> str:
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ''


def excepciones_de_usuario(arboles: list[ast.AST]) -> set[str]:
    """UserError y las clases que heredan de ella, en cualquier nivel."""
    nombres = set(_EXCEPCIONES_BASE)
    clases = [n for t in arboles for n in ast.walk(t) if isinstance(n, ast.ClassDef)]
    cambia = True
    while cambia:
        cambia = False
        for c in clases:
            if c.name not in nombres and any(_nombre(b) in nombres for b in c.bases):
                nombres.add(c.name)
                cambia = True
    return nombres


def citas_en_python(codigo: str, ruta: str, usuario: set[str]) -> list[str]:
    salida = []
    for n in ast.walk(ast.parse(codigo)):
        if not isinstance(n, ast.Call):
            continue
        nombre = _nombre(n.func)
        if nombre in usuario:
            args = list(n.args[:1]) + [k.value for k in n.keywords if k.arg in ('message', 'mensaje', 'msg')]
        elif nombre == 'HTTPException':
            args = list(n.args[1:2]) + [k.value for k in n.keywords if k.arg == 'detail']
        else:
            continue
        for a in args:
            for texto in _textos(a):
                if CITA.search(texto):
                    salida.append(f'{ruta}:{n.lineno}: {texto[:100]!r}')
    return salida


#: 070:RF-78 (v2): las funciones locales que añaden un aviso con su primer argumento (escalera_optima, demanda_medida).
FUNCIONES_DE_AVISO = {'avisar'}

#: 070:RF-78 (v2): los campos de las respuestas que la web o el informe enseñan al operador, aunque no sean una excepción.
CLAVES_PARA_EL_OPERADOR = {'mensaje', 'aviso', 'avisos', 'motivo', 'nota', 'texto'}


def _objeto(nodo: ast.AST) -> str:
    """El nombre del objeto: ``avisos``, ``self.avisos`` o ``informe['avisos']``."""
    if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant) and isinstance(nodo.slice.value, str):
        return nodo.slice.value
    return nodo.id if isinstance(nodo, ast.Name) else nodo.attr if isinstance(nodo, ast.Attribute) else ''


def citas_en_avisos(codigo: str, ruta: str) -> list[str]:
    """Los avisos (``avisos.append/extend/add``, de cualquier lista cuyo nombre lleve «aviso») y los valores de las claves
    ``mensaje``, ``aviso``, ``avisos``, ``motivo``, ``nota`` y ``texto`` de un dict o de una llamada."""
    salida = []
    for n in ast.walk(ast.parse(codigo)):
        valores = []
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('append', 'extend', 'add')
                and 'aviso' in _objeto(n.func.value).lower()):
            valores = list(n.args)
        elif isinstance(n, ast.Call) and _objeto(n.func) in FUNCIONES_DE_AVISO:
            valores = list(n.args[:1])                           # avisar(f'…'): la función local que añade un aviso
        elif isinstance(n, ast.Dict):
            valores = [v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value in CLAVES_PARA_EL_OPERADOR]
        elif isinstance(n, ast.Call):
            valores = [k.value for k in n.keywords if k.arg in CLAVES_PARA_EL_OPERADOR]
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript) and _objeto(t) in CLAVES_PARA_EL_OPERADOR
                                               for t in n.targets):
            valores = [n.value]                                  # out['mensaje'] = f'…'
        for v in valores:
            for texto in _textos(v):
                if CITA.search(texto):
                    salida.append(f'{ruta}:{v.lineno}: {texto[:100]!r}')
    return salida


#: 070:RF-78 (v3): lo que la web enseña sin ser UserError ni un campo de respuesta. Toda excepción con texto (`raise X('…')`,
#: para cualquier X: la web enseña el mensaje del trabajo que cae), lo que un guion de tools/ escribe en su salida
#: (`print`) o en sus avisos, y el texto armado antes en una variable de la misma función.
CLAVES_DE_EXCEPCION = ('message', 'mensaje', 'msg', 'detail')


def _asignaciones(funcion: ast.AST) -> dict[str, list[ast.AST]]:
    """Lo asignado a cada nombre dentro de una función: `x = …`, `x: str = …` y `x += …`. Del módulo, solo lo de su
    nivel, no lo de dentro de sus funciones."""
    nombres: dict[str, list[ast.AST]] = {}
    nodos = (ast.walk(funcion) if not isinstance(funcion, ast.Module) else
             (n for s in funcion.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
              for n in ast.walk(s)))
    for n in nodos:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    nombres.setdefault(t.id, []).append(n.value)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)) and isinstance(n.target, ast.Name) and n.value is not None:
            nombres.setdefault(n.target.id, []).append(n.value)
    return nombres


def _textos_con_variables(nodo: ast.AST, nombres: dict[str, list[ast.AST]], vistos: frozenset = frozenset()):
    """Como `_textos`, y un nombre se sigue hasta lo que se le asignó en la misma función (sin dar vueltas)."""
    if isinstance(nodo, ast.Name) and nodo.id in nombres and nodo.id not in vistos:
        for valor in nombres[nodo.id]:
            yield from _textos_con_variables(valor, nombres, vistos | {nodo.id})
    elif isinstance(nodo, ast.BinOp):
        yield from _textos_con_variables(nodo.left, nombres, vistos)
        yield from _textos_con_variables(nodo.right, nombres, vistos)
    elif isinstance(nodo, ast.IfExp):
        yield from _textos_con_variables(nodo.body, nombres, vistos)
        yield from _textos_con_variables(nodo.orelse, nombres, vistos)
    elif isinstance(nodo, (ast.List, ast.Tuple, ast.Set)):
        for e in nodo.elts:
            yield from _textos_con_variables(e, nombres, vistos)
    else:
        yield from _textos(nodo)


def _ambitos(arbol: ast.AST):
    """El módulo y cada función, con sus asignaciones; un nodo de una función anidada se ve en las dos: se deduplica luego."""
    yield arbol, _asignaciones(arbol)
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n, _asignaciones(n)


#: 070:RF-78 (v3f): las claves de un dict, de un argumento con nombre o de `x['…'] =` que llegan al operador: las de la v2
#: y `error`, `origen` y `fuente` (el error de un trabajo, el origen de un costo, la fuente de un dato).
CLAVES_V3 = CLAVES_PARA_EL_OPERADOR | {'error', 'origen', 'fuente'}


def envolturas_de_salida(arbol: ast.AST) -> frozenset[str]:
    """Las funciones del módulo que imprimen su primer argumento (`_decir(texto)` → `print(f'{hora} {texto}')`), también
    a través de otra envoltura, y los métodos que lo hacen (sin contar `self`)."""
    funciones = [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    envolturas: set[str] = set()
    while True:
        antes = len(envolturas)
        for f in funciones:
            params = [a.arg for a in f.args.args if a.arg not in ('self', 'cls')]
            if not params or f.name in envolturas:
                continue
            for c in ast.walk(f):
                if not isinstance(c, ast.Call) or not c.args:
                    continue
                nombre = c.func.id if isinstance(c.func, ast.Name) else c.func.attr if isinstance(c.func, ast.Attribute) else ''
                argumentos = c.args if nombre == 'print' else c.args[:1] if nombre in envolturas else []
                if any(isinstance(x, ast.Name) and x.id == params[0] for arg in argumentos for x in ast.walk(arg)):
                    envolturas.add(f.name)
                    break
        if len(envolturas) == antes:
            return frozenset(envolturas)


def _valores_para_el_operador(n: ast.AST, *, salida: bool, envolturas: frozenset[str] = frozenset()) -> list[ast.AST]:
    """Los valores que llegan al operador desde un nodo: excepciones, avisos, campos de respuesta, el texto que devuelve
    una función (`return`) y, en tools/, print."""
    if isinstance(n, ast.Return) and n.value is not None:
        return [n.value]                                # 070:RF-78 (v3f): la función que devuelve el mensaje
    if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
        return list(n.exc.args[:1]) + [k.value for k in n.exc.keywords if k.arg in CLAVES_DE_EXCEPCION]
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('append', 'extend', 'add')
            and 'aviso' in _objeto(n.func.value).lower()):
        return list(n.args)
    if isinstance(n, ast.Call) and _objeto(n.func) in FUNCIONES_DE_AVISO:
        return list(n.args[:1])
    if salida and isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'print':
        return list(n.args)
    if salida and isinstance(n, ast.Call) and n.args and envolturas and (
            (isinstance(n.func, ast.Name) and n.func.id in envolturas)
            or (isinstance(n.func, ast.Attribute) and n.func.attr in envolturas)):
        return list(n.args[:1])                         # 070:RF-78: lo que pasa por `_decir` y similares se imprime
    if isinstance(n, ast.Dict):
        return [v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant) and k.value in CLAVES_V3]
    if isinstance(n, ast.Call):
        return [k.value for k in n.keywords if k.arg in CLAVES_V3]
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript) and _objeto(t) in CLAVES_V3 for t in n.targets):
        return [n.value]
    return []


def citas_para_el_operador(codigo: str, ruta: str, *, salida: bool = False) -> list[str]:
    """070:RF-78 (v3): todo lo de `_valores_para_el_operador`, siguiendo las variables de su función."""
    vistas: dict[tuple[int, str], str] = {}
    arbol = ast.parse(codigo)
    envolturas = envolturas_de_salida(arbol) if salida else frozenset()
    for ambito, nombres in _ambitos(arbol):
        for n in ast.walk(ambito):
            for v in _valores_para_el_operador(n, salida=salida, envolturas=envolturas):
                for texto in _textos_con_variables(v, nombres):
                    if CITA.search(texto):
                        vistas.setdefault((v.lineno, texto), f'{ruta}:{v.lineno}: {texto[:100]!r}')
    return sorted(vistas.values(), key=lambda c: (c.split(':')[0], int(c.split(':')[1])))


def sin_comentarios(codigo: str) -> str:
    """Quita los comentarios ``//`` y ``/* */`` (también ``{/* */}`` de JSX) fuera de las cadenas «"» y «`», y deja
    los saltos de línea para conservar los números. Las comillas simples no abren cadena: en el texto de JSX son un
    apóstrofo. Un «//» precedido de «:» es una URL, no un comentario."""
    out, i, n, q = [], 0, len(codigo), None
    while i < n:
        c = codigo[i]
        if q:
            out.append(c)
            if c == '\\':
                out.append(codigo[i + 1:i + 2])
                i += 2
                continue
            if c == q or (c == '\n' and q != '`'):
                q = None
            i += 1
            continue
        if codigo.startswith('//', i) and (i == 0 or codigo[i - 1] != ':'):
            j = codigo.find('\n', i)
            i = n if j < 0 else j
            continue
        if codigo.startswith('/*', i):
            j = codigo.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append('\n' * codigo.count('\n', i, j))
            i = j
            continue
        if c in '"`':
            q = c
        out.append(c)
        i += 1
    return ''.join(out)


def citas_en_tsx(codigo: str, ruta: str) -> list[str]:
    return [f'{ruta}:{k}: {linea.strip()[:100]}' for k, linea in enumerate(sin_comentarios(codigo).splitlines(), 1)
            if CITA.search(linea)]


def test_ningun_mensaje_al_usuario_cita_requisitos_ni_tareas():
    """070:RF-78 — los mensajes de error de src/ y los textos de la web no llevan «RF-», specs ni tareas."""
    fuentes = {p: p.read_text(encoding='utf-8') for p in sorted((RAIZ / 'src').rglob('*.py'))}
    usuario = excepciones_de_usuario([ast.parse(t) for t in fuentes.values()])
    citas = [c for p, t in fuentes.items() for c in citas_en_python(t, p.relative_to(RAIZ).as_posix(), usuario)]
    citas += [c for p in sorted((RAIZ / 'frontend' / 'src').rglob('*.tsx'))
              for c in citas_en_tsx(p.read_text(encoding='utf-8'), p.relative_to(RAIZ).as_posix())]
    assert citas == [], f'{len(citas)} texto(s) para el operador con citas internas:\n' + '\n'.join(citas)


def test_el_detector_ve_cada_cita_sembrada_y_no_los_comentarios():
    """070:RF-78 — cada forma de cita se detecta; los comentarios, los docstrings y «(T1, T2)» de una SET, no."""
    py = '''
class Propia(UserError):
    """Docstring con 028:RF-23: no se enseña."""

def f(x):
    # comentario con 086:RF-1
    if x == 1:
        raise UserError('Falta el libro (028:RF-23).')
    if x == 2:
        raise Propia(f'{x} no es del sistema (spec 019, RF-12).')
    if x == 3:
        raise HTTPException(400, detail='Se hace en la 086 T40.')
    if x == 4:
        raise HTTPException(status_code=409, detail='Lo pide la 099 ' + '(099).')
    raise UserError('La suma de sus transformadores (T1, T2, T3) en alta.')
'''
    usuario = excepciones_de_usuario([ast.parse(py)])
    assert usuario == {'UserError', 'Propia'}
    lineas = sorted(int(c.split(':')[1]) for c in citas_en_python(py, 'x.py', usuario))
    assert lineas == [8, 10, 12, 14]
    tsx = '''// 028:RF-43: comentario
/** 039:RF-17: docstring */
const A = 'Suba los libros (028:RF-23).';
<th title="035:RF-1: el registro">Registro</th>
{/* 004:RF-63: comentario de JSX */}
<small>los demás conservan su calibración (028:RF-40, RF-41).</small>
<a href="https://x.org/a//b">enlace</a>
<p>sus transformadores (T1, T2) y la tarea T7 del plan</p>
'''
    assert [int(c.split(':')[1]) for c in citas_en_tsx(tsx, 'x.tsx')] == [3, 4, 6, 8]


#: Carpetas con dueño propio en vuelo, que esta prueba no reescribe: su dueño quita sus citas. Cada entrada dice quién y por
#: qué, y `test_la_lista_de_en_vuelo_no_esconde_nada` obliga a quitarla en cuanto la carpeta quede limpia.
EN_VUELO = {
    'src/convertersmartgrid/pit/': 'spec 107 (PIT), en vuelo con su subagente S-107/108: 7 avisos con «107:RF-8/12» (2026-11-15)',
}


def _citas_de_avisos(con_en_vuelo: bool) -> list[str]:
    citas = []
    for p in sorted((RAIZ / 'src').rglob('*.py')):
        ruta = p.relative_to(RAIZ).as_posix()
        if con_en_vuelo == any(ruta.startswith(c) for c in EN_VUELO):
            citas += citas_en_avisos(p.read_text(encoding='utf-8'), ruta)
    return citas


def test_la_lista_de_en_vuelo_no_esconde_nada():
    """070:RF-78 (v2) — una carpeta de EN_VUELO sigue en la lista solo mientras tenga citas que quitar su dueño."""
    for carpeta in EN_VUELO:
        quedan = [c for c in _citas_de_avisos(True) if c.startswith(carpeta)]
        assert quedan, f'{carpeta} ya no tiene citas: quítela de EN_VUELO'


def test_ningun_aviso_ni_mensaje_de_las_respuestas_cita_requisitos():
    """070:RF-78 (v2) — en todo src/, los avisos y los mensajes que no son excepciones, y que la web o el informe enseñan,
    tampoco citan requisitos, specs ni tareas."""
    citas = _citas_de_avisos(False)
    assert citas == [], f'{len(citas)} aviso(s) o mensaje(s) para el operador con citas internas:\n' + '\n'.join(citas)


def test_el_detector_de_avisos_ve_cada_forma_sembrada():
    """070:RF-78 (v2) — avisos por append, extend y add; claves de un dict y argumentos con nombre; lo demás no cuenta."""
    py = '''
def f(avisos, informe, x):
    avisos.append(f'{x}: sin hora (051:RF-2).')
    informe['avisos'].extend(['sin año (051:RF-9)'])
    vistos_avisos.add('no se ponen (054:RF-10)')
    r = {'mensaje': f'{x}: a 3 m del nodo (004:RF-72).', 'otro': 'campo interno 004:RF-72'}
    g(motivo='se repite (104:RF-26)', clave='interna (104:RF-26)')
    avisos.append('Transformadores (T1, T2) en alta.')
    out['mensaje'] = f'{x}: a 2 m del nodo (004:RF-72).'
    out['interno'] = 'clave interna (004:RF-72)'
    avisar(f'{x}: la terna se añade de su mismo tipo (042:RF-99).')
    registrar('interno (042:RF-99)')
    return {'nota': 'Contexto, no norma.'}
'''
    assert sorted(int(c.split(':')[1]) for c in citas_en_avisos(py, 'x.py')) == [3, 4, 5, 6, 7, 9, 11]


#: 070:RF-78 (v3): guiones de tools/ cuyas citas quita una tarjeta siguiente (v3b…); cada uno con su tarjeta. La prueba
#: de abajo obliga a sacarlo de aquí en cuanto quede limpio.
PENDIENTES_V3: dict[str, str] = {
}


#: 070:RF-78 (v3f): guiones que no hablan al operador sino al repositorio; cada uno con su motivo.
NO_SON_DEL_OPERADOR: dict[str, str] = {
    'tools/generar_arquitectura.py': 'escribe docs/ARQUITECTURA_CATALOGO.md, un documento del repositorio para quien '
                                     'desarrolla, que sí cita specs; la web no lo enseña',
}


def _citas_v3(raiz: str, salida: bool) -> list[str]:
    citas = []
    for p in sorted((RAIZ / raiz).rglob('*.py')):
        ruta = p.relative_to(RAIZ).as_posix()
        if any(ruta.startswith(c) for c in EN_VUELO) or ruta in PENDIENTES_V3 or ruta in NO_SON_DEL_OPERADOR:
            continue
        citas += citas_para_el_operador(p.read_text(encoding='utf-8'), ruta, salida=salida)
    return citas


def test_ninguna_excepcion_ni_aviso_de_src_cita_requisitos():
    """070:RF-78 (v3) — en src/, ninguna excepción con texto (de cualquier clase), aviso ni campo para el operador cita
    requisitos, specs ni tareas, tampoco si el texto se arma antes en una variable de la misma función."""
    citas = _citas_v3('src', salida=False)
    assert citas == [], f'{len(citas)} texto(s) de src/ con citas internas:\n' + '\n'.join(citas)


def test_ningun_texto_de_los_guiones_cita_requisitos():
    """070:RF-78 (v3) — lo que un guion de tools/ escribe en su salida o en sus avisos lo enseña la web en el trabajo."""
    citas = _citas_v3('tools', salida=True)
    assert citas == [], f'{len(citas)} texto(s) de tools/ con citas internas:\n' + '\n'.join(citas)


def test_la_lista_de_pendientes_v3_no_esconde_nada():
    """070:RF-78 (v3) — un guion sigue en PENDIENTES_V3 solo mientras tenga citas."""
    for ruta in PENDIENTES_V3:
        assert citas_para_el_operador((RAIZ / ruta).read_text(encoding='utf-8'), ruta, salida=True), \
            f'{ruta} ya no tiene citas: quítelo de PENDIENTES_V3'


def test_el_detector_v3_ve_excepciones_variables_y_salida_de_los_guiones():
    """070:RF-78 (v3) — cualquier excepción, el texto de una variable de la misma función y, en tools/, el print; no un
    print de src/, ni una variable de otra función, ni un comentario."""
    py = '''
def f(x):
    raise AjusteError(f'{x}: sin dispersión (041:RF-3).')

def g(x):
    msg = f'{x}: no converge'
    msg += ' (042:RF-49).'
    raise EscaleraError(msg)

def h(avisos):
    texto = 'sin año (051:RF-9)'
    avisos.append(texto)
    print('Resumen (015:RF-46)')

def i():
    raise ValueError(msg)   # la msg de g no es de esta función (042:RF-49)
'''
    sin_salida = sorted(int(c.split(':')[1]) for c in citas_para_el_operador(py, 'x.py'))
    con_salida = sorted(int(c.split(':')[1]) for c in citas_para_el_operador(py, 'x.py', salida=True))
    assert sin_salida == [3, 8, 12]
    assert con_salida == [3, 8, 12, 13]


def test_el_detector_ve_la_salida_de_las_envolturas_de_print():
    """070:RF-78 — en tools/, lo que pasa por una función propia que lo imprime (como `_decir` del servidor de PF, que se
    le escapó al detector hasta la puerta E del 16-11) es salida del guion: la envoltura, la que llama a otra envoltura y
    el método; no una función que imprime otra cosa, ni lo que no es su primer argumento."""
    py = '''
def _decir(texto):
    print(f'{hora()} {texto}', flush=True)

def _avisar(texto, nivel=1):
    _decir('AVISO: ' + texto)

def _contar(n, etiqueta):
    print(f'{n} hechas')

class Servidor:
    def decir(self, texto):
        print(texto)

    def servir(self, orden):
        self.decir(f'Orden {orden}: vuelve a la cola (019:RF-27).')

def servir(orden):
    _decir(f'Orden {orden} descartada (019:RF-17).')
    _avisar('Sin órdenes: se cierra (019:RF-8).')
    _contar(3, 'etiqueta interna 019:RF-14')
'''
    sin_salida = sorted(int(c.split(':')[1]) for c in citas_para_el_operador(py, 'x.py'))
    con_salida = sorted(int(c.split(':')[1]) for c in citas_para_el_operador(py, 'x.py', salida=True))
    assert sin_salida == [], f'fuera de tools/ las envolturas de print no cuentan: {sin_salida}'
    assert con_salida == [16, 19, 20], f'el detector no ve la salida de las envolturas de print: {con_salida}'


def decisiones_por_cita(codigo: str, ruta: str) -> list[str]:
    """070:RF-78 (v3): un `in`, un `startswith` o un `re` que busca una cita dentro de un texto. Al quitar las citas de los
    mensajes, esa condición deja de cumplirse en silencio: pasó con «051:RF-9» en tools/cabecera_ancha.py desde v2a."""
    salida = []
    for n in ast.walk(ast.parse(codigo)):
        textos = []
        if isinstance(n, ast.Compare) and any(isinstance(o, (ast.In, ast.NotIn)) for o in n.ops):
            textos = [n.left]
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ('startswith', 'endswith', 'find', 'count', 'search', 'match', 'fullmatch')):
            textos = list(n.args[:1])
        for t in textos:
            if isinstance(t, ast.Constant) and isinstance(t.value, str) and CITA.search(t.value):
                salida.append(f'{ruta}:{n.lineno}: {t.value!r}')
    return salida


def test_ningun_codigo_decide_por_una_cita_dentro_de_un_texto():
    """070:RF-78 (v3) — en src/ y tools/, ninguna condición busca una cita dentro de un aviso o de la salida de un guion: se
    busca su sentido. Lo de EN_VUELO y PENDIENTES_V3 lo trata su tarjeta."""
    malas = []
    for raiz in ('src', 'tools'):
        for p in sorted((RAIZ / raiz).rglob('*.py')):
            ruta = p.relative_to(RAIZ).as_posix()
            if any(ruta.startswith(c) for c in EN_VUELO) or ruta in PENDIENTES_V3:
                continue
            malas += decisiones_por_cita(p.read_text(encoding='utf-8'), ruta)
    assert malas == [], f'{len(malas)} condición(es) que buscan una cita dentro de un texto:\n' + '\n'.join(malas)


def test_el_detector_de_decisiones_por_cita_ve_cada_forma():
    """070:RF-78 (v3) — `in`, `not in`, `startswith` y `re.search` con una cita; no una comparación con otro texto."""
    py = '''
def f(a, avisos):
    x = [v for v in avisos if '051:RF-9' in v]
    y = '064:RF-5' not in a
    z = a.startswith('(083:RF-31)')
    w = re.search('042:RF-6', a)
    return 'como estaba al empezar' in a
'''
    lineas = sorted(int(c.split(':')[1]) for c in decisiones_por_cita(py, 'x.py'))
    assert lineas == [3, 4, 5, 6], lineas


def test_el_detector_v3f_ve_lo_devuelto_y_las_claves_error_origen_fuente():
    """070:RF-78 (v3f) — el texto que devuelve una función (también en una tupla) y las claves error, origen y fuente;
    no un return sin texto ni otra clave."""
    py = '''
def f(x):
    if x:
        return None, (f'{x}: sin reparto (041:RF-3).')
    return x

def g(base):
    return base + ' (098:RF-8).'

def h(p):
    c = {'origen': 'por confirmar (098:RF-35)', 'interno': 'clave (098:RF-35)'}
    r = dict(fuente=f'perfil {p} (095:RF-3)', otra='x (095:RF-3)')
    out['error'] = 'no aplicada (042:RF-6)'
    return c, r
'''
    lineas = sorted(int(c.split(':')[1]) for c in citas_para_el_operador(py, 'x.py'))
    assert lineas == [4, 8, 11, 12, 13], lineas


# ------------------------------------------------------------------ datos que van en la entrega
#: 070:RF-78 (datos): ficheros de datos entregados que pueden citar, cada uno con su motivo. Hoy ninguno: todos se limpiaron.
#: `test_la_lista_de_datos_declarados_no_esconde_nada` obliga a quitar una entrada en cuanto su fichero quede limpio.
DATOS_DECLARADOS: dict[str, str] = {}

#: Las funciones con que tools/construir_candidato.py copia un fichero del repositorio dentro del candidato.
COPIAS = {'copyfile', 'copy', 'copy2', '_copiar_fijado'}


def copiados_por_el_candidato(codigo: str) -> set[str]:
    """Los ``config/…`` que el constructor copia al candidato: las constantes ``X = Path('config', …)`` del módulo que
    aparecen en el origen de una copia (``shutil.copyfile(raiz / X, …)``)."""
    arbol = ast.parse(codigo)
    constantes = {}
    for n in arbol.body:
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and _nombre(n.value.func) == 'Path'
                and n.value.args and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in n.value.args)
                and n.value.args[0].value == 'config'):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    constantes[t.id] = '/'.join(a.value for a in n.value.args)
    return {constantes[m.id] for n in ast.walk(arbol) if isinstance(n, ast.Call) and _nombre(n.func) in COPIAS and n.args
            for m in ast.walk(n.args[0]) if isinstance(m, ast.Name) and m.id in constantes}


def citas_en_datos(datos, ruta: str, camino: str = '') -> list[str]:
    """Cada cadena de un JSON con una cita, también las claves: «ruta:/camino: 'texto'»."""
    salida = []
    if isinstance(datos, str):
        if CITA.search(datos):
            salida.append(f'{ruta}:{camino or "/"}: {datos[:100]!r}')
    elif isinstance(datos, dict):
        for k, v in datos.items():
            salida += citas_en_datos(k, ruta, f'{camino}/{k}') if isinstance(k, str) and CITA.search(k) else []
            salida += citas_en_datos(v, ruta, f'{camino}/{k}')
    elif isinstance(datos, list):
        for i, v in enumerate(datos):
            salida += citas_en_datos(v, ruta, f'{camino}[{i}]')
    return salida


def datos_entregados() -> list[str]:
    """Los ``config/**/*.json`` del repositorio que entran en la entrega según ``config/entrega.json``, y los que copia el
    constructor del candidato."""
    ce = cargar_herramienta('comprobar_entrega.py')
    manifiesto = ce.leer_manifiesto(RAIZ / 'config' / 'entrega.json')
    copiados = copiados_por_el_candidato((RAIZ / 'tools' / 'construir_candidato.py').read_text(encoding='utf-8'))
    del_repositorio = subprocess.run(['git', 'ls-files', '--', 'config'], cwd=RAIZ, capture_output=True, text=True,
                                     check=True).stdout.split()
    return sorted(r for r in del_repositorio if r.endswith('.json') and (ce.entra(r, manifiesto) or r in copiados))


def _citas_de_datos(declarados: bool) -> list[str]:
    citas = []
    for rel in datos_entregados():
        if (rel in DATOS_DECLARADOS) == declarados:
            citas += citas_en_datos(json.loads((RAIZ / rel).read_text(encoding='utf-8')), rel)
    return citas


def test_ningun_dato_que_va_en_la_entrega_cita_requisitos():
    """070:RF-78 (datos) — un dato entregado también lo ve el cliente: ni sus valores, ni sus claves, ni sus «_comentario»
    citan requisitos, specs ni tareas."""
    citas = _citas_de_datos(False)
    assert citas == [], f'{len(citas)} texto(s) de datos entregados con citas internas:\n' + '\n'.join(citas)


def test_la_lista_de_datos_declarados_no_esconde_nada():
    """070:RF-78 (datos) — un fichero sigue en DATOS_DECLARADOS solo mientras se entregue y tenga citas."""
    entregados = set(datos_entregados())
    for rel in DATOS_DECLARADOS:
        assert rel in entregados, f'{rel} ya no se entrega: quítelo de DATOS_DECLARADOS'
        assert citas_en_datos(json.loads((RAIZ / rel).read_text(encoding='utf-8')), rel), \
            f'{rel} ya no tiene citas: quítelo de DATOS_DECLARADOS'


def test_el_detector_de_datos_ve_cada_forma_sembrada():
    """070:RF-78 (datos) — caso sembrado: un «_comentario», una lista, una clave y un valor anidado con su cita se ven; un
    número, «(T1, T2)» de una SET y un texto sin cita, no. Y la selección: lo que deja entrar la lista de la entrega y lo
    que copia el constructor, no lo que la lista excluye."""
    datos = {'_comentario': '086:RF-32: la plantilla', 'n': 3, 'lista': ['sin cita', 'las rutas (spec 102)'],
             'clave (097:RF-19)': 1, 'perfil': {'nota': 'Transformadores (T1, T2) en alta', 'origen': 'la 086 T40'}}
    assert [c.split(': ', 1)[0] for c in citas_en_datos(datos, 'x.json')] == [
        'x.json:/_comentario', 'x.json:/lista[1]', 'x.json:/clave (097:RF-19)', 'x.json:/perfil/origen']
    codigo = ("from pathlib import Path\nimport shutil\nCONJUNTO = Path('config', 'a', 'b.json')\n"
              "OTRO = Path('config', 'c.json')\nNO_CONFIG = Path('docs', 'd.json')\n"
              "def f(raiz, destino):\n    shutil.copyfile(raiz / CONJUNTO, destino)\n    leer(raiz / OTRO)\n"
              "    shutil.copyfile(raiz / NO_CONFIG, destino)\n")
    assert copiados_por_el_candidato(codigo) == {'config/a/b.json'}
    entregados = set(datos_entregados())
    assert {'config/perfiles/plantilla.json', 'config/entrega.json',
            'config/pregunta_entregada/CONJUNTO_ABSTENCION_ENTREGA.json'} <= entregados
    assert not {'config/perfil_empresa.json', 'config/licencias_terceros/manifest.json'} & entregados


# ------------------------------------------------------------------ textos del esquema que ve el operador
#: Las claves del esquema cuyo texto llega al operador: ``perfil_esquema`` las pone en ``Falta.funcion`` y
#: ``Falta.si_falta``, que enseñan el doctor y la web.
CLAVES_DE_TEXTO_DEL_ESQUEMA = ('x-funcion', 'x-si-falta')
ESQUEMAS = RAIZ / 'src' / 'convertersmartgrid' / 'schemas'


def citas_en_esquema(datos, ruta: str, camino: str = '') -> list[str]:
    """Cada ``x-funcion`` o ``x-si-falta`` con una cita, a cualquier profundidad: «ruta:/camino/clave: 'texto'»."""
    salida = []
    if isinstance(datos, dict):
        for k, v in datos.items():
            if k in CLAVES_DE_TEXTO_DEL_ESQUEMA and isinstance(v, str):
                if CITA.search(v):
                    salida.append(f'{ruta}:{camino}/{k}: {v[:100]!r}')
            else:
                salida += citas_en_esquema(v, ruta, f'{camino}/{k}')
    elif isinstance(datos, list):
        for i, v in enumerate(datos):
            salida += citas_en_esquema(v, ruta, f'{camino}[{i}]')
    return salida


def test_ningun_texto_del_esquema_que_ve_el_operador_cita_requisitos():
    """070:RF-78 (datos) — lo que el doctor y la web dicen de una clave que falta en el perfil (su ``x-funcion`` y su
    ``x-si-falta``) no cita requisitos, specs ni tareas."""
    citas = []
    for f in sorted(ESQUEMAS.glob('*.json')):
        citas += citas_en_esquema(json.loads(f.read_text(encoding='utf-8')), f'src/convertersmartgrid/schemas/{f.name}')
    assert citas == [], f'{len(citas)} texto(s) del esquema con citas internas:\n' + '\n'.join(citas)


def test_el_detector_del_esquema_ve_cada_forma_sembrada():
    """070:RF-78 (datos) — caso sembrado: un ``x-funcion`` anidado y un ``x-si-falta`` dentro de una lista con su cita se
    ven; una descripción técnica (``description``) con cita no es de esta prueba, y un texto sin cita no se ve."""
    esquema = {'properties': {'pit': {'properties': {'areas': {'x-funcion': 'Áreas del PIT (107:RF-9)',
                                                               'x-si-falta': 'sin áreas no hay expediente'}}},
                              'lista': {'items': [{'x-si-falta': 'no se calcula (spec 049)'}]},
                              'otra': {'description': 'interna (086:RF-3)', 'x-funcion': 'Bancos por tensión'}}}
    vistas = [c.split(': ', 1)[0] for c in citas_en_esquema(esquema, 'x.json')]
    assert vistas == ['x.json:/properties/pit/properties/areas/x-funcion', 'x.json:/properties/lista/items[0]/x-si-falta']
