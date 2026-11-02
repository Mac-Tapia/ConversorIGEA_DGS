"""Comprueba las capas, ciclos y accesos privados sin importar el producto.

Uso: python tools/arquitectura.py [--raiz REPOSITORIO] [--json].
La tabla explícita vive en pyproject.toml; no existe una opción para aceptar deuda
automáticamente. Las excepciones retiradas también fallan para reducir el registro.
"""
from __future__ import annotations

import argparse
import ast
import json
import tomllib
from dataclasses import dataclass, field
from importlib.util import resolve_name
from pathlib import Path

CAPAS = ('dominio', 'puertos', 'aplicacion', 'adaptadores', 'presentacion')
BORDE_Y_DRIVERS = frozenset(('fastapi', 'tkinter', 'powerfactory', 'pyodbc', 'pymssql',
                             'sqlalchemy', 'psycopg', 'psycopg2', 'pymysql', 'sqlite3', 'adodbapi'))


@dataclass
class Informe:
    modulos: dict[str, Path]
    violaciones: set[str] = field(default_factory=set)
    errores: list[str] = field(default_factory=list)


def inventario(raiz: Path) -> dict[str, Path]:
    """Incluye paquetes y todos los módulos Python, también vnr_etl y anidados."""
    resultado = {}
    for archivo in sorted(raiz.rglob('*.py')):
        partes = archivo.relative_to(raiz).with_suffix('').parts
        if '__pycache__' in partes:
            continue
        nombre = '.'.join(partes[:-1] if partes[-1] == '__init__' else partes)
        if nombre:
            resultado[nombre] = archivo
    return resultado


def _atributo(nodo: ast.AST) -> str:
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        padre = _atributo(nodo.value)
        return f'{padre}.{nodo.attr}' if padre else ''
    return ''


def analizar(raiz: Path, capas: dict[str, str]) -> Informe:
    """Resuelve imports absolutos y relativos, incluso dentro de funciones/TYPE_CHECKING.

    Las aristas de cada componente fuertemente conexa se registran por separado:
    una arista nueva falla aunque sus extremos ya pertenecieran al mismo ciclo.
    Los imports dinámicos cuyo destino no es literal quedan fuera del análisis AST.
    """
    modulos = inventario(raiz)
    informe = Informe(modulos)
    informe.violaciones.update(f'sin_capa|{m}' for m in modulos.keys() - capas.keys())
    informe.violaciones.update(f'sin_modulo|{m}' for m in capas.keys() - modulos.keys())
    informe.violaciones.update(f'capa_invalida|{m}|{c}' for m, c in capas.items() if c not in CAPAS)
    grafo: dict[str, set[str]] = {m: set() for m in modulos}

    def destino(nombre: str) -> str | None:
        while nombre:
            if nombre in modulos:
                return nombre
            nombre = nombre.rpartition('.')[0]
        return None

    for origen, archivo in modulos.items():
        arbol = ast.parse(archivo.read_text(encoding='utf-8-sig'), filename=str(archivo))
        paquete = origen if archivo.name == '__init__.py' else origen.rpartition('.')[0]
        alias_modulos: dict[str, str] = {}

        def agregar(nombre: str) -> None:
            externo = nombre.split('.')[0]
            if capas.get(origen) == 'dominio' and externo in BORDE_Y_DRIVERS:
                informe.violaciones.add(f'dominio_externo|{origen}|{externo}')
            objetivo = destino(nombre)
            if objetivo and objetivo != origen:
                grafo[origen].add(objetivo)

        def privado(modulo: str, nombre: str) -> None:
            objetivo = destino(modulo)
            especial = nombre.startswith('__') and nombre.endswith('__')
            if objetivo and objetivo != origen and nombre.startswith('_') and not especial:
                informe.violaciones.add(f'privado|{origen}|{objetivo}|{nombre}')

        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    agregar(alias.name)
                    alias_modulos[alias.asname or alias.name] = alias.name
            elif isinstance(nodo, ast.ImportFrom):
                try:
                    base = resolve_name('.' * nodo.level + (nodo.module or ''), paquete) if nodo.level else (nodo.module or '')
                except (ImportError, ValueError):
                    informe.violaciones.add(f'import_relativo_invalido|{origen}|{nodo.lineno}')
                    continue
                for alias in nodo.names:
                    completo = f'{base}.{alias.name}'
                    objetivo = completo if completo in modulos else base
                    agregar(objetivo)
                    if completo in modulos:
                        alias_modulos[alias.asname or alias.name] = completo
                    privado(base, alias.name)
                    if alias.name == '*' and destino(base):
                        informe.violaciones.add(f'comodin|{origen}|{base}')
            elif isinstance(nodo, ast.Call) and nodo.args:
                # También se incluyen import_module('paquete.modulo') y __import__
                # literales; no se ejecuta código para inferir destinos calculados.
                funcion = _atributo(nodo.func)
                if funcion in ('importlib.import_module', 'import_module', '__import__'):
                    argumento = nodo.args[0]
                    if isinstance(argumento, ast.Constant) and isinstance(argumento.value, str):
                        agregar(argumento.value)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Attribute):
                ruta = _atributo(nodo.value)
                if ruta in alias_modulos:
                    privado(alias_modulos[ruta], nodo.attr)
        for objetivo in grafo[origen]:
            a, b = capas.get(origen), capas.get(objetivo)
            if a in CAPAS and b in CAPAS and CAPAS.index(a) < CAPAS.index(b):
                informe.violaciones.add(f'capa|{origen}|{objetivo}')

    # Tarjan: O(módulos + imports), sin enumerar todos los caminos de un ciclo.
    indices: dict[str, int] = {}
    bajos: dict[str, int] = {}
    pila: list[str] = []
    en_pila: set[str] = set()

    def visitar(modulo: str) -> None:
        indices[modulo] = bajos[modulo] = len(indices)
        pila.append(modulo)
        en_pila.add(modulo)
        for siguiente in sorted(grafo[modulo]):
            if siguiente not in indices:
                visitar(siguiente)
                bajos[modulo] = min(bajos[modulo], bajos[siguiente])
            elif siguiente in en_pila:
                bajos[modulo] = min(bajos[modulo], indices[siguiente])
        if bajos[modulo] == indices[modulo]:
            componente = set()
            while True:
                siguiente = pila.pop()
                en_pila.remove(siguiente)
                componente.add(siguiente)
                if siguiente == modulo:
                    break
            if len(componente) > 1:
                informe.violaciones.update(f'ciclo|{a}|{b}' for a in componente
                                           for b in grafo[a] & componente)

    for modulo in sorted(grafo):
        if modulo not in indices:
            visitar(modulo)
    return informe


def comparar_deuda(actuales: set[str], excepciones: dict[str, str]) -> list[str]:
    """Falla tanto al crecer la deuda como al conservar dispensas ya resueltas."""
    errores = [f'Violación nueva: {v}' for v in sorted(actuales - excepciones.keys())]
    errores += [f'Excepción retirada: {v}; elimínela del registro' for v in sorted(excepciones.keys() - actuales)]
    errores += [f'Excepción sin justificación: {v}' for v, motivo in excepciones.items()
                if not isinstance(motivo, str) or not motivo.strip()]
    return errores


def comprobar(raiz: Path) -> Informe:
    """Lee la política versionada; ninguna clasificación ni excepción se autogenera."""
    config = tomllib.loads((raiz / 'pyproject.toml').read_text(encoding='utf-8'))
    politica = config['tool']['convertersmartgrid']['capas']
    informe = analizar(raiz / 'src', politica['modulos'])
    deuda = json.loads((raiz / politica['deuda']).read_text(encoding='utf-8'))
    informe.errores.extend(comparar_deuda(informe.violaciones, deuda['excepciones']))
    return informe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--json', action='store_true', help='Emite el informe legible por máquina')
    args = parser.parse_args(argv)
    informe = comprobar(args.raiz)
    if args.json:
        print(json.dumps({'modulos': len(informe.modulos), 'violaciones': sorted(informe.violaciones),
                          'errores': informe.errores}, ensure_ascii=False, indent=2))
    else:
        print(f'{len(informe.modulos)} módulos, {len(informe.violaciones)} excepciones de deuda')
        for error in informe.errores:
            print(error)
    return int(bool(informe.errores))


if __name__ == '__main__':
    raise SystemExit(main())
