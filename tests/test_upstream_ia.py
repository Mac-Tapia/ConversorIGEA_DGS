"""043:RF-9 a RF-11 — clones fijados y custodia con Git real, sin ejecutar terceros."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


@pytest.fixture
def catalogo(tmp_path, monkeypatch):
    origen = tmp_path / 'remotos/origen.git'
    origen.mkdir(parents=True)
    git('init', cwd=origen)
    git('config', 'user.email', 'prueba@example.test', cwd=origen)
    git('config', 'user.name', 'Prueba', cwd=origen)
    (origen / 'LICENSE').write_text('MIT License\nCopyright prueba\n', encoding='utf-8')
    git('add', 'LICENSE', cwd=origen)
    git('commit', '-m', 'licencia de prueba', cwd=origen)
    revision = git('rev-parse', 'HEAD', cwd=origen)
    blob = subprocess.check_output(['git', 'show', revision + ':LICENSE'], cwd=origen)
    config = tmp_path / 'gitconfig'
    config.write_text(f'[url "{(tmp_path / "remotos").as_uri()}/"]\n'
                      '    insteadOf = https://github.com/prueba/\n', encoding='utf-8')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(config))
    return {'schema_version': 1, 'repositorios': [{
        'id': 'ejemplo', 'url': 'https://github.com/prueba/origen.git',
        'commit': revision, 'license': 'MIT', 'license_path': 'LICENSE',
        'license_sha256': hashlib.sha256(blob).hexdigest()}]}


def test_clona_revision_y_verifica_licencia(tmp_path, catalogo):
    """043:RF-9 — SHA y blob de licencia coinciden, aun con autocrlf del equipo."""
    from tools.preparar_upstream_ia import preparar_catalogo
    destino = tmp_path / 'clones'
    informe = preparar_catalogo(catalogo, destino)
    assert informe['ok'], informe
    assert git('rev-parse', 'HEAD', cwd=destino / 'ejemplo') == catalogo['repositorios'][0]['commit']
    assert preparar_catalogo(catalogo, destino, verificar=True)['ok']


def test_no_sobrescribe_copia_modificada(tmp_path, catalogo):
    """043:RF-10 — cambios locales se conservan y bloquean la preparación."""
    from tools.preparar_upstream_ia import preparar_catalogo
    destino = tmp_path / 'clones'
    assert preparar_catalogo(catalogo, destino)['ok']
    licencia = destino / 'ejemplo/LICENSE'
    licencia.write_text('cambio local', encoding='utf-8')
    informe = preparar_catalogo(catalogo, destino)
    assert not informe['ok']
    assert licencia.read_text(encoding='utf-8') == 'cambio local'


def test_licencia_incorrecta_rechaza(tmp_path, catalogo):
    """043:RF-9 — una licencia diferente de la revisada impide validar el clon."""
    from tools.preparar_upstream_ia import preparar_catalogo
    catalogo['repositorios'][0]['license_sha256'] = '0' * 64
    assert not preparar_catalogo(catalogo, tmp_path / 'clones')['ok']


def test_verificar_no_clona_ausentes(tmp_path, catalogo):
    """043:RF-11 — verificar no descarga ni instala nada en el núcleo."""
    from tools.preparar_upstream_ia import preparar_catalogo
    destino = tmp_path / 'ausente'
    assert not preparar_catalogo(catalogo, destino, verificar=True)['ok']
    assert not destino.exists()


def test_verificador_publico_para_adaptadores(tmp_path, catalogo):
    """043:RF-9 — adaptadores y CLI usan la misma verificación del código reutilizado."""
    from tools.preparar_upstream_ia import preparar_catalogo
    from convertersmartgrid.upstream_ia import verificar_repositorio
    destino = tmp_path / 'clones'
    assert preparar_catalogo(catalogo, destino)['ok']
    assert verificar_repositorio('ejemplo', catalogo=catalogo, destino=destino)['ok']


def test_revision_diferente_no_reemplaza_copia(tmp_path, catalogo):
    """043:RF-10 — un cambio del catálogo no mueve el HEAD de una copia existente."""
    from convertersmartgrid.upstream_ia import preparar_catalogo
    destino = tmp_path / 'clones'
    assert preparar_catalogo(catalogo, destino)['ok']
    revision = catalogo['repositorios'][0]['commit']
    catalogo['repositorios'][0]['commit'] = '0' * 40
    informe = preparar_catalogo(catalogo, destino)
    assert not informe['ok']
    assert git('rev-parse', 'HEAD', cwd=destino / 'ejemplo') == revision


def test_importar_sin_cargar_dependencias_ml(tmp_path):
    """043:RF-11 — importar el núcleo y los adaptadores no carga frameworks opcionales."""
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    programa = '''
import sys
import convertersmartgrid.upstream_ia
import convertersmartgrid.digital_twin.oraculo
import convertersmartgrid.digital_twin.adaptador_pyg
assert not ({'torch', 'torch_geometric', 'neuralforecast', 'pymoo', 'pyomo'} & sys.modules.keys())
'''
    resultado = subprocess.run([sys.executable, '-c', programa], cwd=tmp_path,
                              env=env, capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
