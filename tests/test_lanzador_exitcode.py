"""065:RF-2 — ejecución aislada del batch Windows y códigos del proceso web."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.name != 'nt', reason='El lanzador usa cmd.exe en Windows.')
@pytest.mark.parametrize('codigo', [0, 1, 2, 3])
def test_batch_propaga_codigo_real_del_hijo(tmp_path, codigo):
    """065:RF-2 — pause, timeout y endlocal no ocultan el estado real del hijo."""
    shutil.copyfile(RAIZ / 'run_gui.bat', tmp_path / 'run_gui.bat')
    entorno = tmp_path / '.venv'
    scripts = entorno / 'Scripts'
    scripts.mkdir(parents=True)
    shutil.copyfile(sys.executable, scripts / 'python.exe')
    shutil.copyfile(Path(sys.prefix) / 'pyvenv.cfg', entorno / 'pyvenv.cfg')
    paquete = tmp_path / 'src/convertersmartgrid/web'
    paquete.mkdir(parents=True)
    (paquete.parent / '__init__.py').write_text('')
    (paquete / '__init__.py').write_text('')
    (paquete / 'runtime.py').write_text('raise SystemExit(0)\n')
    (paquete / '__main__.py').write_text(f'raise SystemExit({codigo})\n')
    (scripts / 'timeout.cmd').write_text('@exit /b 0\n')
    resultado = subprocess.run(
        [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', '.\\run_gui.bat'],
        cwd=tmp_path, env={**os.environ, 'PATH': str(scripts) + os.pathsep + os.environ['PATH']},
        input='\n\n\n', capture_output=True, text=True, timeout=30)
    assert resultado.returncode == codigo, resultado.stdout + resultado.stderr
