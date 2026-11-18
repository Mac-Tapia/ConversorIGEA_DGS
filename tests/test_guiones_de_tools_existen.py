"""Cada guion de ``tools/`` que nombran las pruebas y la aplicación existe (002:RF-39, amplía RF-21).

CAPAS-002 v5 (b0f95bdc, 17-11) reescribió 116 nombres sueltos de guiones de ``tools/`` como si fueran módulos de su
capa: ``cargar_herramienta('aplicacion/estudios_pf.py')`` en las pruebas, ``_guion_pf(…, 'aplicacion/obras_pf.py')``
en la web. Los ficheros seguían en ``tools/``: las pruebas no se recogían y la web no habría encontrado los guiones
de DIgSILENT. Aquí se leen, sin ejecutar nada, todos los sitios que nombran un guion de ``tools/`` y se exige que
cada uno exista, con la lista entera de los que faltan.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
SRC = ROOT / 'src' / 'convertersmartgrid'
#: Llamadas de la aplicación cuyo argumento de texto «x.py» es un guion de tools/ (``_script`` hace
#: ``tools_dir() / name``; ``guion_pf``/``_guion_pf`` lo lanza con el Python de DIgSILENT).
_LANZADORES = {'_script', 'guion_pf', '_guion_pf'}
#: Listas de nombres de guiones de tools/ en el arnés de DIgSILENT.
_LISTAS_DEL_ARNES = ('GUIONES_SERVIBLES', 'GUIONES_EN_SU_PROCESO', 'SERVIDOR')
_TOOLS_EN_TEXTO = re.compile(r"""['"]tools/([A-Za-z0-9_/]+\.py)['"]|['"]tools['"]\s*/\s*['"]([A-Za-z0-9_/]+\.py)['"]""")


def _nombre(func: ast.expr) -> str:
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ''


def _textos_py(nodos) -> list[str]:
    return [n.value for n in nodos if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith('.py')]


def _arbol(f: Path) -> tuple[ast.AST, str]:
    texto = f.read_text(encoding='utf-8')
    return ast.parse(texto, filename=str(f)), texto


def guiones_nombrados_en_pruebas(raiz: Path = ROOT) -> list[tuple[str, str]]:
    """(«fichero:línea», guion relativo a tools/) de cada ``cargar_herramienta('x.py')`` y de cada
    ``spec_from_file_location(…, … 'tools' / 'x.py')`` o ``'tools/x.py'`` de ``tests/``."""
    salida = []
    for f in sorted((raiz / 'tests').rglob('*.py')):
        arbol, texto = _arbol(f)
        rel = f.relative_to(raiz).as_posix()
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Call):
                continue
            nombre = _nombre(n.func)
            if nombre == 'cargar_herramienta' and n.args:
                salida += [(f'{rel}:{n.lineno}', g) for g in _textos_py(n.args[:1])]
            elif nombre == 'spec_from_file_location':
                trozo = ast.get_source_segment(texto, n) or ''
                salida += [(f'{rel}:{n.lineno}', a or b) for a, b in _TOOLS_EN_TEXTO.findall(trozo)]
    return salida


def guiones_nombrados_en_la_aplicacion(raiz: Path = ROOT) -> list[tuple[str, str]]:
    """Los de ``_script``/``guion_pf``/``_guion_pf`` en ``src/`` y las listas del arnés (``pf_arnes``)."""
    salida = []
    src = raiz / 'src' / 'convertersmartgrid'
    for f in sorted(src.rglob('*.py')):
        arbol, _texto = _arbol(f)
        rel = f.relative_to(raiz).as_posix()
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call) and _nombre(n.func) in _LANZADORES:
                salida += [(f'{rel}:{n.lineno}', g) for g in _textos_py(list(n.args) + [k.value for k in n.keywords])]
            elif isinstance(n, ast.Assign) and f.name == 'pf_arnes.py' and any(
                    isinstance(t, ast.Name) and t.id in _LISTAS_DEL_ARNES for t in n.targets):
                salida += [(f'{rel}:{n.lineno}', g) for g in _textos_py(ast.walk(n.value))]
    return salida


def _faltan(nombrados: list[tuple[str, str]], raiz: Path = ROOT) -> list[str]:
    return [f'{donde}: tools/{g}' for donde, g in nombrados if not (raiz / 'tools' / g).is_file()]


def test_002_rf39_los_guiones_que_cargan_las_pruebas_existen_en_tools():
    nombrados = guiones_nombrados_en_pruebas()
    # Sin esto la prueba pasaría en vacío si cambiara la forma de cargarlos (hoy son más de 200).
    assert len(nombrados) > 100, f'solo {len(nombrados)} cargas de guiones de tools/ en tests/: ¿cambió la forma?'
    faltan = _faltan(nombrados)
    assert faltan == [], f'{len(faltan)} cargas de tests/ a un guion que no está en tools/:\n' + '\n'.join(faltan)


def test_002_rf39_los_guiones_que_lanza_la_aplicacion_existen_en_tools():
    nombrados = guiones_nombrados_en_la_aplicacion()
    arnes = [g for d, g in nombrados if 'pf_arnes.py' in d]
    assert len(arnes) > 20, f'solo {len(arnes)} guiones en las listas de pf_arnes: ¿cambió su forma?'
    assert any('services.py' in d for d, _g in nombrados), 'ningún _script ni _guion_pf en la web: ¿cambió su forma?'
    faltan = _faltan(nombrados)
    assert faltan == [], f'{len(faltan)} guiones que la aplicación lanza y no están en tools/:\n' + '\n'.join(faltan)


def test_002_rf39_el_comprobador_ve_un_guion_que_falta(tmp_path):
    """Sembrado: una prueba, la web y el arnés que nombran un guion con la capa delante; el comprobador los ve."""
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools' / 'obras_pf.py').write_text('', encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_x.py').write_text(
        "a = cargar_herramienta('obras_pf.py')\nb = cargar_herramienta('aplicacion/obras_pf.py')\n"
        "c = importlib.util.spec_from_file_location('m', RAIZ / 'tools' / 'aplicacion/obras_pf.py')\n", encoding='utf-8')
    web = tmp_path / 'src' / 'convertersmartgrid' / 'presentacion' / 'web'
    web.mkdir(parents=True)
    (web / 'services.py').write_text("_guion_pf(ws, ctx, 'aplicacion/obras_pf.py', {})\n_script('obras_pf.py')\n",
                                     encoding='utf-8')
    arnes = tmp_path / 'src' / 'convertersmartgrid' / 'adaptadores'
    arnes.mkdir(parents=True)
    (arnes / 'pf_arnes.py').write_text("GUIONES_SERVIBLES = frozenset({'obras_pf.py', 'aplicacion/cargas_pf.py'})\n",
                                       encoding='utf-8')
    assert _faltan(guiones_nombrados_en_pruebas(tmp_path), tmp_path) == [
        'tests/test_x.py:2: tools/aplicacion/obras_pf.py', 'tests/test_x.py:3: tools/aplicacion/obras_pf.py']
    assert _faltan(guiones_nombrados_en_la_aplicacion(tmp_path), tmp_path) == [
        'src/convertersmartgrid/adaptadores/pf_arnes.py:1: tools/aplicacion/cargas_pf.py',
        'src/convertersmartgrid/presentacion/web/services.py:1: tools/aplicacion/obras_pf.py']
