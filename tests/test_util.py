"""Utilidades comunes de ``igea_dgs.util`` (spec 001, T2).

Estaban copiadas hasta en siete sitios (diagnóstico del 2026-10-07, B5). Además de su
comportamiento, aquí se prueba que no vuelvan a copiarse: el detector compara el árbol
sintáctico normalizado de cada función de ``src/`` con el de las de ``util``.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from igea_dgs import util
from igea_dgs.util import finite_or_none, nombre_seguro, sha256_file, write_json_atomic

SRC = Path(__file__).resolve().parents[1] / 'src'


# --- SHA-256 ---------------------------------------------------------------------------

@pytest.mark.parametrize('tamano', [0, 1, (1 << 20) - 1, 1 << 20, (1 << 20) + 7, 3 * (1 << 20)])
def test_sha256_file_igual_que_hashlib_en_los_bordes_de_bloque(tmp_path, tamano):
    """001:RF-4 — el hash por bloques coincide con el del contenido entero."""
    datos = bytes((i * 31 + 7) % 256 for i in range(tamano))
    ruta = tmp_path / 'f.bin'
    ruta.write_bytes(datos)
    assert sha256_file(ruta) == hashlib.sha256(datos).hexdigest()
    assert sha256_file(str(ruta)) == hashlib.sha256(datos).hexdigest()


# --- JSON atómico ----------------------------------------------------------------------

def test_write_json_atomic_formato_y_carpetas(tmp_path):
    """001:RF-5 — crea las carpetas, conserva acentos y termina en salto de línea."""
    ruta = tmp_path / 'a' / 'b' / 'manifiesto.json'
    write_json_atomic(ruta, {'nombre': 'Señal Ñ', 'ruta': Path('x/y')})
    texto = ruta.read_text(encoding='utf-8')
    assert texto == json.dumps({'nombre': 'Señal Ñ', 'ruta': str(Path('x/y'))}, indent=2,
                               ensure_ascii=False) + '\n'
    assert not list(ruta.parent.glob('*.tmp'))


def test_write_json_atomic_reemplaza_el_anterior(tmp_path):
    """001:RF-5 — sobrescribe un fichero existente sin dejar el temporal."""
    ruta = tmp_path / 'm.json'
    write_json_atomic(ruta, {'v': 1})
    write_json_atomic(ruta, {'v': 2})
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'v': 2}
    assert [p.name for p in tmp_path.iterdir()] == ['m.json']


def test_write_json_atomic_no_toca_el_anterior_si_falla(tmp_path):
    """001:RF-5 — si no se puede serializar, el fichero anterior queda intacto."""
    ruta = tmp_path / 'm.json'
    write_json_atomic(ruta, {'v': 1})
    circular: dict = {}
    circular['yo'] = circular
    with pytest.raises(ValueError):
        write_json_atomic(ruta, circular)
    assert json.loads(ruta.read_text(encoding='utf-8')) == {'v': 1}
    assert [p.name for p in tmp_path.iterdir()] == ['m.json']


# --- Número finito ---------------------------------------------------------------------

@pytest.mark.parametrize('valor, esperado', [
    ('1.5', 1.5), (3, 3.0), ('-0', 0.0), (' 2 ', 2.0),
    ('nan', None), ('inf', None), ('-inf', None), (float('nan'), None),
    (None, None), ('', None), ('x', None), ([], None),
])
def test_finite_or_none(valor, esperado):
    """001:T2 — número finito, o ``None`` para todo lo demás."""
    assert finite_or_none(valor) == esperado


# --- Nombre seguro ---------------------------------------------------------------------

@pytest.mark.parametrize('texto, maximo, esperado', [
    ('Red Sur/1', None, 'Red_Sur_1'),
    ('ÁREA-2_b', None, 'ÁREA-2_b'),
    ('', None, 'GRUPO'),
    ('a' * 80, 60, 'a' * 60),
    ('x.y', 2, 'x_'),
])
def test_nombre_seguro(texto, maximo, esperado):
    """001:T2 — solo letras, dígitos, guion y guion bajo; nunca vacío."""
    assert nombre_seguro(texto, maximo=maximo) == esperado


# --- Detector de copias ----------------------------------------------------------------

class _Normaliza(ast.NodeTransformer):
    """Quita nombres, anotaciones y docstrings: dos copias con otras variables coinciden."""

    def __init__(self) -> None:
        self.nombres: dict[str, str] = {}

    def _marca(self, nombre: str) -> str:
        return self.nombres.setdefault(nombre, f'v{len(self.nombres)}')

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id=self._marca(node.id), ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg=self._marca(node.arg)), node)


def _huella(funcion: ast.FunctionDef) -> str:
    cuerpo = list(funcion.body)
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
        cuerpo = cuerpo[1:]
    copia = ast.Module(body=[ast.parse(ast.unparse(n)).body[0] for n in cuerpo], type_ignores=[])
    return ast.dump(_Normaliza().visit(copia))


def _funciones(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding='utf-8'))
    return [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)]


def test_ninguna_utilidad_esta_copiada_en_igea_dgs():
    """001:RF-4, 001:RF-5 — las utilidades viven solo en ``util``."""
    ruta_util = Path(util.__file__)
    propias = {_huella(f): f.name for f in _funciones(ruta_util) if not f.name.startswith('_')}
    copias = [
        f'{ruta.relative_to(SRC).as_posix()}:{f.lineno} {f.name} = util.{propias[h]}'
        for ruta in sorted((SRC / 'igea_dgs').rglob('*.py')) if ruta != ruta_util
        for f in _funciones(ruta) if (h := _huella(f)) in propias
    ]
    assert not copias, copias
