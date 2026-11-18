"""103:RF-5 — el paquete lo importa el Python 3.9 embebido de DIgSILENT 2021–2023: ninguna sintaxis posterior.

Comprobación permanente, sin variables: corre en cada commit y en la CI. La prueba real con ``CSG_PF_PYTHON_39``
(tests/test_powerfactory_versiones.py) sigue importando el paquete de verdad; esta caza lo mismo sin ese intérprete.
Caso real (2026-11-14): ``src/convertersmartgrid/__init__.py:16`` de bd4cc7d2 anotaba ``-> str | None`` sin
``from __future__ import annotations``, y ningún guion de DIgSILENT 2021–2023 cargaba el paquete; solo lo vio el ensayo
de la puerta entera con ``CSG_PF_PYTHON_39``.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'src' / 'convertersmartgrid'


def _tiene_future_annotations(arbol: ast.Module) -> bool:
    return any(isinstance(n, ast.ImportFrom) and n.module == '__future__' and any(a.name == 'annotations' for a in n.names)
               for n in arbol.body)


def _union_pep604(nodo: ast.AST | None) -> bool:
    """``X | Y`` en una anotación: Python 3.9 lo evalúa y falla con TypeError."""
    return nodo is not None and any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(nodo))


def _anotaciones_evaluadas(arbol: ast.Module):
    """Las anotaciones que Python 3.9 evalúa al importar: firmas de funciones y las del módulo o de una clase.

    Las de variables locales dentro de una función no se evalúan y no cuentan.
    """
    def recorrer(cuerpo, dentro_de_funcion: bool):
        for nodo in cuerpo:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                argumentos = nodo.args
                for arg in [*argumentos.posonlyargs, *argumentos.args, *argumentos.kwonlyargs,
                            *([argumentos.vararg] if argumentos.vararg else []),
                            *([argumentos.kwarg] if argumentos.kwarg else [])]:
                    yield arg.annotation, arg.lineno
                yield nodo.returns, nodo.lineno
                yield from recorrer(nodo.body, True)
            elif isinstance(nodo, ast.ClassDef):
                yield from recorrer(nodo.body, dentro_de_funcion)
            elif isinstance(nodo, ast.AnnAssign) and not dentro_de_funcion:
                yield nodo.annotation, nodo.lineno
            else:
                for campo in ('body', 'orelse', 'finalbody', 'handlers'):
                    hijos = getattr(nodo, campo, None)
                    if isinstance(hijos, list):
                        yield from recorrer([h for h in hijos if isinstance(h, ast.AST)], dentro_de_funcion)
    yield from recorrer(arbol.body, False)


def incompatibles_con_python39(texto: str, nombre: str = '<texto>') -> list[str]:
    """Lo que impide importar ``texto`` en Python 3.9, con su línea; vacío si nada lo impide."""
    hallados: list[str] = []
    try:
        # La gramática de 3.9: caza match, except*, parámetros de tipo (PEP 695), «type X = …» y los
        # gestores de contexto entre paréntesis.
        ast.parse(texto, filename=nombre, feature_version=(3, 9))
    except SyntaxError as exc:
        hallados.append(f'{nombre}:{exc.lineno}: sintaxis posterior a 3.9 ({exc.msg})')
    arbol = ast.parse(texto, filename=nombre)
    for nodo in ast.walk(arbol):
        if type(nodo).__name__ in ('Match', 'TryStar', 'TypeAlias'):
            hallados.append(f'{nombre}:{getattr(nodo, "lineno", 0)}: {type(nodo).__name__} no existe en 3.9')
        if getattr(nodo, 'type_params', None):
            hallados.append(f'{nombre}:{getattr(nodo, "lineno", 0)}: parámetros de tipo (PEP 695) no existen en 3.9')
    if not _tiene_future_annotations(arbol):
        for anotacion, linea in _anotaciones_evaluadas(arbol):
            if _union_pep604(anotacion):
                hallados.append(f'{nombre}:{linea}: «X | Y» en una anotación evaluada al importar, sin '
                                '«from __future__ import annotations»')
    return sorted(set(hallados))


def test_103_rf5_ningun_modulo_usa_sintaxis_posterior_a_python_39():
    """103:RF-5 — todo src/convertersmartgrid se importa en el Python 3.9 de DIgSILENT 2021–2023."""
    hallados = []
    for ruta in sorted(SRC.rglob('*.py')):
        hallados += incompatibles_con_python39(ruta.read_text(encoding='utf-8'), str(ruta.relative_to(RAIZ)))
    assert not hallados, 'sintaxis que Python 3.9 no importa (103:RF-5):\n' + '\n'.join(hallados[:40])


def _guiones_de_digsilent() -> list[Path]:
    """Los guiones de ``tools/`` que corren dentro de DIgSILENT, del MISMO registro que usa el lanzador (los que atiende
    el servidor y los que van en su propio proceso, ``pf_arnes``), y los de ``tools/`` que ellos importan."""
    from convertersmartgrid.adaptadores.pf_arnes import GUIONES_EN_SU_PROCESO, GUIONES_SERVIBLES

    herramientas = RAIZ / 'tools'
    pendientes = [herramientas / nombre for nombre in sorted(GUIONES_SERVIBLES | GUIONES_EN_SU_PROCESO)]
    faltan = [p.name for p in pendientes if not p.is_file()]
    assert not faltan, f'el registro de guiones de pf_arnes nombra ficheros que no están en tools/: {faltan}'
    vistos: set[Path] = set()
    while pendientes:
        guion = pendientes.pop()
        if guion in vistos:
            continue
        vistos.add(guion)
        for nodo in ast.walk(ast.parse(guion.read_text(encoding='utf-8'))):
            nombres = ([a.name for a in nodo.names] if isinstance(nodo, ast.Import)
                       else [nodo.module] if isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level else [])
            for nombre in nombres:
                candidato = herramientas / f"{nombre.split('.')[0]}.py"
                if candidato.is_file() and candidato not in vistos:
                    pendientes.append(candidato)
    return sorted(vistos)


def test_103_rf5_los_guiones_de_digsilent_en_tools_tampoco():
    """103:RF-5 — los guiones de tools/ que lanza DIgSILENT (del registro de pf_arnes, y lo que importan de tools/)
    corren con el mismo Python 3.9 y pasan la misma comprobación que src/."""
    guiones = _guiones_de_digsilent()
    assert len(guiones) >= 20
    hallados = []
    for ruta in guiones:
        hallados += incompatibles_con_python39(ruta.read_text(encoding='utf-8'), str(ruta.relative_to(RAIZ)))
    assert not hallados, 'sintaxis que Python 3.9 no importa en los guiones de DIgSILENT (103:RF-5):\n' + '\n'.join(hallados)


def test_103_rf5_el_detector_ve_cada_forma():
    """103:RF-5 — el detector caza cada forma y no se queja de lo que 3.9 sí importa."""
    malo = 'def f(x: int) -> str | None:\n    return None\n'
    assert incompatibles_con_python39(malo)
    assert not incompatibles_con_python39('from __future__ import annotations\n' + malo)
    assert incompatibles_con_python39('class C:\n    a: int | None = None\n')
    assert not incompatibles_con_python39('def f():\n    a: int | None = None\n    return a\n')   # local: no se evalúa
    assert incompatibles_con_python39('match x:\n    case 1:\n        pass\n')
    assert incompatibles_con_python39('try:\n    pass\nexcept* ValueError:\n    pass\n')
    assert incompatibles_con_python39('def f[T](x: T) -> T:\n    return x\n')
    assert not incompatibles_con_python39('from typing import Optional\n\ndef f() -> Optional[str]:\n    return None\n')
