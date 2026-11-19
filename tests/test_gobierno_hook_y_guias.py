"""102:RF-34 (T25): el arnés de trabajo de Claude no deja pasar Python roto ni lleva a rutas que ya no existen
(auditoría del 18-11, H10 y H11).

- El hook ``.claude/hooks/check_py.py`` rechaza (sale con 2) un .py con sintaxis inválida del proyecto en ``src``,
  ``tools``, ``tests``, ``tests_ml`` y ``.claude/hooks``; deja pasar (0) lo correcto, lo de fuera del proyecto, un fichero
  ausente y un payload inválido; compila en memoria, sin dejar ``__pycache__``. No sustituye a la puerta de calidad.
- Cada ruta del repositorio que citan las skills del proyecto existe.
- El principio 9 de la constitución cita las pruebas que ya comprueban el envío a terceros (109 y 110) y no dice que no
  haya vía de envío.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HOOK = RAIZ / '.claude' / 'hooks' / 'check_py.py'
ROTO = 'def roto(:\n'


def _hook(ruta: Path | str, proyecto: Path, *, payload: str | None = None) -> int:
    entrada = payload if payload is not None else json.dumps({'tool_input': {'file_path': str(ruta)}})
    env = {**os.environ, 'CLAUDE_PROJECT_DIR': str(proyecto)}
    return subprocess.run([sys.executable, str(HOOK)], input=entrada, text=True, capture_output=True, env=env,
                          timeout=20).returncode


@pytest.mark.parametrize('carpeta', ['src/pkg', 'tools', 'tests', 'tests_ml', '.claude/hooks'])
def test_102_rf34_el_hook_rechaza_sintaxis_invalida_en_el_codigo_del_proyecto(tmp_path, carpeta):
    proyecto = tmp_path / 'proyecto con espacios'
    ruta = proyecto / carpeta / 'roto.py'
    ruta.parent.mkdir(parents=True)
    ruta.write_text(ROTO, encoding='utf-8')
    assert _hook(ruta, proyecto) == 2, f'102:RF-34: el hook dejó pasar sintaxis inválida en {carpeta}/'
    assert not (ruta.parent / '__pycache__').exists(), 'el hook escribió __pycache__'


def test_102_rf34_el_hook_deja_pasar_lo_correcto_y_lo_que_no_es_del_proyecto(tmp_path):
    proyecto = tmp_path / 'proyecto'
    bien = proyecto / 'tools' / 'bien.py'
    bien.parent.mkdir(parents=True)
    bien.write_text('x = 1\n', encoding='utf-8')
    assert _hook(bien, proyecto) == 0
    ajeno = tmp_path / 'otro' / 'src' / 'roto.py'      # una carpeta «src» de otro proyecto no se compila
    ajeno.parent.mkdir(parents=True)
    ajeno.write_text(ROTO, encoding='utf-8')
    assert _hook(ajeno, proyecto) == 0
    assert _hook(proyecto / 'tools' / 'no_existe.py', proyecto) == 0
    assert _hook('', proyecto, payload='no es json') == 0
    datos = proyecto / 'docs' / 'roto.py'               # fuera de las carpetas de código
    datos.parent.mkdir(parents=True)
    datos.write_text(ROTO, encoding='utf-8')
    assert _hook(datos, proyecto) == 0


def test_102_rf34_las_skills_citan_rutas_que_existen():
    citas = []
    for skill in sorted((RAIZ / '.claude' / 'skills').glob('*/SKILL.md')):
        for ruta in re.findall(r'(?:src|frontend|tools|tests|docs|specs)/[A-Za-z0-9_./-]+', skill.read_text(encoding='utf-8')):
            ruta = ruta.rstrip('.,/')
            if any(c in ruta for c in '*<>') or 'NNN' in ruta or not ruta:   # comodines y plantillas («specs/NNN-…»)
                continue
            if not (RAIZ / ruta).exists():
                citas.append(f'{skill.parent.name}: {ruta}')
    assert not citas, f'102:RF-34: las skills llevan a rutas que no existen: {citas}'


def test_102_rf34_el_principio_9_cita_las_pruebas_del_envio_a_terceros():
    texto = (RAIZ / 'docs' / 'constitution.md').read_text(encoding='utf-8')
    assert 'Mientras tanto no hay vía de publicación ni de envío a terceros en el código' not in texto, \
        '102:RF-34: P9 dice que no hay vía de envío, y 109 y 110 ya la tienen'
    assert '*Se comprueba*' in texto.split('10. **Idioma')[0].split('*Cambio del 2026-11-14:*')[1]
