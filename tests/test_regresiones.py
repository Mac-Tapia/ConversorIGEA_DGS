"""Spec 081: cada fallo real deja una entrada con su comprobación permanente y una prueba que exista."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / 'docs/regresiones'
ENTRADAS = sorted(p for p in CARPETA.glob('*.md') if p.name != 'README.md')
APARTADOS = ('## Síntoma', '## Causa', '## Comprobación permanente', '## Prueba')
#: Los siete fallos con los que nació la regla; una entrada puede cubrir uno solo.
DE_HOY = ('acoplador-trifasico', 'banco-trifasico', 'sed-de-una-fase', 'calibracion-done', 'caso-base-deja',
          'suite-nocturna', 'ok-y-verificado')


def _pruebas_de(texto: str) -> list[tuple[str, str]]:
    bloque = texto.split('## Prueba', 1)[-1]
    return re.findall(r'`(tests/[\w./-]+\.py)::(\w+)`', bloque)


def _existe(fichero: str, prueba: str) -> bool:
    ruta = RAIZ / fichero
    if not ruta.is_file():
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == prueba for n in ast.walk(ast.parse(ruta.read_text(encoding='utf-8'))))


def test_hay_entradas_y_la_regla_esta_escrita():
    """081:RF-46 — la regla para los próximos, y sus apartados."""
    regla = (CARPETA / 'README.md').read_text(encoding='utf-8')
    assert 'entra aquí en el mismo cambio que lo corrige' in regla and ENTRADAS
    for apartado in APARTADOS:
        assert apartado in regla


@pytest.mark.parametrize('entrada', ENTRADAS, ids=lambda p: p.stem)
def test_cada_entrada_tiene_sus_apartados(entrada):
    """081:RF-46, 081:RF-47 — en orden, y ninguno vacío; la causa se dice o se dice que no se sabe."""
    texto = entrada.read_text(encoding='utf-8')
    posiciones = [texto.find(a) for a in APARTADOS]
    assert -1 not in posiciones and posiciones == sorted(posiciones), f'{entrada.name}: faltan apartados'
    partes = re.split(r'^## .*$', texto, flags=re.MULTILINE)[1:]
    assert all(p.strip() for p in partes), f'{entrada.name}: apartado vacío'
    assert texto.startswith('# ')


@pytest.mark.parametrize('entrada', ENTRADAS, ids=lambda p: p.stem)
def test_cada_entrada_apunta_a_una_prueba_que_existe(entrada):
    """081:RF-47 — una entrada que no apunta a nada se queda en papel."""
    pruebas = _pruebas_de(entrada.read_text(encoding='utf-8'))
    assert pruebas, f'{entrada.name}: sin prueba'
    faltan = [f'{f}::{p}' for f, p in pruebas if not _existe(f, p)]
    assert not faltan, f'{entrada.name}: no existen {faltan}'


def test_la_comprobacion_detecta_una_prueba_que_no_existe():
    """081:RF-47 — la guarda misma: una prueba inventada no pasa."""
    assert not _existe('tests/test_regresiones.py', 'prueba_inventada')
    assert not _existe('tests/no_existe.py', 'x')
    assert _existe('tests/test_regresiones.py', 'test_la_comprobacion_detecta_una_prueba_que_no_existe')
    assert _pruebas_de('## Prueba\n- `tests/a.py::b`\n') == [('tests/a.py', 'b')] and _pruebas_de('## Prueba\nninguna') == []


def test_estan_los_fallos_de_hoy():
    """081:RF-48 — los siete con los que nació la regla."""
    nombres = ' '.join(p.stem for p in ENTRADAS)
    assert [x for x in DE_HOY if x not in nombres] == []


def _nombres_prohibidos() -> set[str]:
    """Códigos y empresas que no se escriben aquí: de los perfiles y de la estructura de cada empresa."""
    prohibidos = {'electro dunas', 'electro oriente', 'elor', 'eldu'}
    for ruta in (RAIZ / 'config/perfiles').glob('*.json'):
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except ValueError:
            continue
        prohibidos.update(str(datos.get(k)).lower() for k in ('nombre', 'empresa', 'codigo') if datos.get(k))
    return prohibidos


def test_sin_nombres_de_clientes_ni_empresas():
    """081:RF-49 — ni alimentadores (dos o tres letras y tres cifras), ni empresas: son documentos del conversor."""
    prohibidos = _nombres_prohibidos()
    for entrada in [CARPETA / 'README.md', *ENTRADAS]:
        texto = entrada.read_text(encoding='utf-8')
        # Las rutas de pruebas y los RF no son alimentadores.
        limpio = re.sub(r'`[^`]*`|\d{3}:RF-\d+', '', texto)
        assert not re.findall(r'\b[A-Z]{2,3}\d{3}\b', limpio), f'{entrada.name}: nombra un alimentador'
        bajo = limpio.lower()
        assert not [x for x in prohibidos if re.search(rf'\b{re.escape(x)}\b', bajo)], f'{entrada.name}: nombra una empresa'
