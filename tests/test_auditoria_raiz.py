"""Spec 036: instalación consistente y fallo real del lanzador ante errores de npm."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

import pytest
from packaging.requirements import Requirement

from convertersmartgrid.web.runtime import missing_dependencies

RAIZ = Path(__file__).resolve().parents[1]


def _nombres(declaraciones):
    return {Requirement(linea).name.lower().replace('_', '-') for linea in declaraciones
            if linea.strip() and not linea.lstrip().startswith(('#', '-'))}


def test_la_instalacion_conserva_la_vigilancia_de_memoria():
    """036:RF-1 — la instalación documentada y ambos extras web instalan el vigilante."""
    requisitos = _nombres((RAIZ / 'requirements.txt').read_text(encoding='utf-8').splitlines())
    extras = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies']
    assert 'psutil' in requisitos
    assert all('psutil' in _nombres(extras[grupo]) for grupo in ('web', 'all'))


def test_el_arranque_detecta_que_falta_el_vigilante():
    """036:RF-1 — faltar psutil obliga al lanzador a preparar el entorno, no a degradarlo."""
    def importar(nombre):
        if nombre == 'psutil':
            raise ModuleNotFoundError(nombre)
        return object()

    assert missing_dependencies(importar) == ('psutil',)


def test_el_corpus_pdf_tiene_su_dependencia_declarada():
    """036:RF-2 — el extractor que usa PdfReader se puede instalar desde el contrato."""
    requisitos = _nombres((RAIZ / 'requirements.txt').read_text(encoding='utf-8').splitlines())
    extras = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))['project']['optional-dependencies']
    assert 'pypdf' in requisitos
    assert all('pypdf' in _nombres(extras[grupo]) for grupo in ('pide', 'all'))


def _lanzar_aislado(tmp_path, fallo):
    """Ejecuta cmd.exe y el batch real; los servicios externos quedan fuera del ensayo."""
    shutil.copyfile(RAIZ / 'run_gui.bat', tmp_path / 'run_gui.bat')
    entorno = tmp_path / '.venv'
    scripts = entorno / 'Scripts'
    scripts.mkdir(parents=True)
    # El launcher CPython de Windows usa el home real indicado por pyvenv.cfg.
    shutil.copyfile(sys.executable, scripts / 'python.exe')
    shutil.copyfile(Path(sys.prefix) / 'pyvenv.cfg', entorno / 'pyvenv.cfg')
    paquete = tmp_path / 'src' / 'convertersmartgrid' / 'web'
    paquete.mkdir(parents=True)
    (paquete.parent / '__init__.py').write_text('', encoding='ascii')
    (paquete / '__init__.py').write_text('', encoding='ascii')
    (paquete / 'runtime.py').write_text(
        'import sys\nraise SystemExit(1 if "--front" in sys.argv else 0)\n', encoding='ascii')
    (paquete / '__main__.py').write_text(
        'from pathlib import Path\nPath("servidor_iniciado").write_text("iniciado")\n', encoding='ascii')
    front = tmp_path / 'frontend'
    (front / 'dist').mkdir(parents=True)
    (front / 'dist' / 'index.html').write_text('compilacion anterior', encoding='ascii')
    (scripts / 'npm.cmd').write_text(
        '@echo off\n'
        'echo %1>>"%~dp0npm_calls.txt"\n'
        f'if "%1"=="{fallo}" exit /b 23\n'
        'exit /b 0\n', encoding='ascii')
    env = {**os.environ, 'PATH': str(scripts) + os.pathsep + os.environ['PATH'],
           'PYTHONDONTWRITEBYTECODE': '1'}
    resultado = subprocess.run(
        [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', r'.\run_gui.bat'],
        cwd=tmp_path, env=env, input='\n', text=True, capture_output=True, timeout=30)
    registro = scripts / 'npm_calls.txt'
    llamadas = registro.read_text(encoding='ascii').splitlines() if registro.exists() else []
    return resultado, llamadas


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
@pytest.mark.parametrize('fallo,esperadas', [('ci', ['ci']), ('run', ['ci', 'run'])])
def test_un_fallo_de_npm_no_abre_una_interfaz_anterior(tmp_path, fallo, esperadas):
    """036:RF-3; 065:RF-8 — el batch real no inicia servidor si falla ci o build."""
    resultado, llamadas = _lanzar_aislado(tmp_path, fallo)
    assert llamadas == esperadas, resultado.stdout + resultado.stderr
    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert not (tmp_path / 'servidor_iniciado').exists()


@pytest.mark.skipif(os.name != 'nt', reason='El acceso directo usa cmd.exe en Windows.')
def test_el_lanzador_sigue_abriendo_tras_npm_correcto(tmp_path):
    """036:RF-3 — controlar el error no bloquea el camino que compila correctamente."""
    resultado, llamadas = _lanzar_aislado(tmp_path, 'ninguno')
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert llamadas == ['ci', 'run']
    assert (tmp_path / 'servidor_iniciado').is_file()
