"""Spec 026, T10: mejoras en una rama aparte que el operador revisa."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from igea_dgs.asistente import mejoras


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'datos'))
    r = tmp_path / 'repo'
    (r / 'tests').mkdir(parents=True)
    (r / 'tests' / 'test_base.py').write_text('def test_base():\n    assert True\n', encoding='utf-8')
    _git(r, 'init', '-q', '-b', 'main')
    _git(r, 'add', '.')
    _git(r, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'base')
    return r


def test_codigo_con_spec_y_pruebas(repo):
    """026:RF-26 — una mejora de código sin su spec o sin sus pruebas no se prepara."""
    with pytest.raises(mejoras.PropuestaInvalida, match='spec'):
        mejoras.validar(mejoras.Propuesta('t', 'm', 'codigo', {'src/x.py': '', 'tests/test_x.py': ''}))
    with pytest.raises(mejoras.PropuestaInvalida, match='pruebas'):
        mejoras.validar(mejoras.Propuesta('t', 'm', 'codigo', {'src/x.py': '', 'specs/099/spec.md': ''}))
    with pytest.raises(mejoras.PropuestaInvalida, match='fuera'):
        mejoras.validar(mejoras.Propuesta('t', 'm', 'libreria', {'../docs/propuestas/x.md': ''}))


def test_rama_aparte_con_su_suite_sin_fusionar(repo):
    """026:RF-26 / 026:RF-27 — la mejora va en su rama y su worktree, con la suite corrida; la
    rama principal no cambia y fusionar o subir no se puede ni pedir."""
    p = mejoras.Propuesta('Mejora de prueba', 'motivo', 'codigo', {
        'specs/099-x/spec.md': '- RF-1: EL SISTEMA hará x.\n',
        'tests/test_x.py': 'def test_x():\n    """099:RF-1 — x."""\n    assert 1 + 1 == 2\n'})
    fila = mejoras.preparar_rama(repo, p)
    assert fila['rama'] == f'asistente/{p.id}' and fila['suite']['codigo'] == 0 and '2 passed' in fila['suite']['resumen']
    assert Path(fila['worktree'], 'tests', 'test_x.py').is_file()
    assert not (repo / 'tests' / 'test_x.py').exists()
    assert _git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip() == 'main'
    assert _git(repo, 'log', '--oneline', 'main').count('\n') == 1
    for orden in ('merge', 'push'):
        with pytest.raises(PermissionError):
            mejoras._git(repo, orden, fila['rama'])


def test_decisiones_auditables(repo):
    """026:RF-28 — cada propuesta y la decisión del operador quedan registradas."""
    p = mejoras.propuesta_de_libreria({'nombre': 'pandapower', 'licencia': 'BSD', 'version': '3.5',
                                       'publicada': '2026-09-01', 'url': 'https://x'}, 'flujo de carga independiente')
    fila = mejoras.preparar_rama(repo, p, suite=None)
    mejoras.registrar_decision(fila['id'], 'rechazada', 'ya la usamos')
    h = {x['id']: x for x in mejoras.historial()}
    assert h[fila['id']]['decision'] == 'rechazada' and h[fila['id']]['tipo'] == 'libreria'
    with pytest.raises(ValueError):
        mejoras.registrar_decision(fila['id'], 'fusionada')


def test_ficha_de_libreria():
    """026:RF-32 — la librería se propone con licencia, mantenimiento y motivo, sin instalarla."""
    p = mejoras.propuesta_de_libreria({'nombre': 'deap', 'licencia': None, 'version': '1.4'}, 'algoritmos evolutivos')
    ficha = p.cambios['docs/propuestas/libreria-deap.md']
    assert 'sin declarar' in ficha and 'algoritmos evolutivos' in ficha and 'No se instala' in ficha
