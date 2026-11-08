"""001:RF-27 — el lanzador recompila el front cuando su código es más reciente."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from convertersmartgrid.web.runtime import front_desactualizado

RAIZ = Path(__file__).resolve().parents[1]


def _front(tmp_path, *, dist: bool = True) -> Path:
    frontend = tmp_path / 'frontend'
    (frontend / 'src' / 'features' / 'demo').mkdir(parents=True)
    (frontend / 'src' / 'features' / 'demo' / 'Panel.tsx').write_text('x', encoding='utf-8')
    (frontend / 'package.json').write_text('{}', encoding='utf-8')
    if dist:
        (frontend / 'dist').mkdir()
        (frontend / 'dist' / 'index.html').write_text('<html>', encoding='utf-8')
    return frontend


def _edad(path: Path, segundos: float) -> None:
    os.utime(path, (1_700_000_000 + segundos, 1_700_000_000 + segundos))


def test_sin_compilar_hay_que_compilar(tmp_path):
    """001:RF-27 — sin dist, hay que compilar."""
    assert front_desactualizado(_front(tmp_path, dist=False)) == 'no está compilado'


def test_dist_al_dia_no_recompila(tmp_path):
    """001:RF-27 — con dist posterior a todo el código, no se recompila."""
    frontend = _front(tmp_path)
    for fichero in frontend.rglob('*'):
        if fichero.is_file():
            _edad(fichero, 0)
    _edad(frontend / 'dist' / 'index.html', 10)
    assert front_desactualizado(frontend) == ''


def test_un_componente_cambiado_obliga_a_recompilar(tmp_path):
    """001:RF-27 — un fichero de src más reciente que dist obliga a recompilar y se nombra."""
    frontend = _front(tmp_path)
    _edad(frontend / 'package.json', 0)
    _edad(frontend / 'dist' / 'index.html', 10)
    _edad(frontend / 'src' / 'features' / 'demo' / 'Panel.tsx', 20)
    assert front_desactualizado(frontend) == (
        'src/features/demo/Panel.tsx es más reciente que la compilación')


def test_el_lanzador_usa_la_comprobacion():
    """001:RF-27 — run_gui.bat pregunta antes de abrir y compila si hace falta."""
    bat = (RAIZ / 'run_gui.bat').read_bytes().decode('ascii')
    comprobacion = bat.index('-m convertersmartgrid.web.runtime --front')
    compila = bat.index('call npm run build')
    abre = bat.index('-m convertersmartgrid.web\r\n')
    assert comprobacion < compila < abre
    # Ya no se compila solo cuando falta dist: la comprobación decide.
    assert 'if not exist "frontend\\dist\\index.html" (\r\n  where npm' not in bat


@pytest.mark.parametrize('referencia', [
    '/assets/falta.js', '../fuera.js', '/%2e%2e/fuera.js',
    'file://servidor/recurso.js', 'http://[direccion-invalida/recurso.js',
])
def test_rechaza_recurso_ausente_o_fuera_de_dist(tmp_path, referencia):
    """065:RF-3 — un index reciente no basta si falta un recurso o sale de dist."""
    frontend = _front(tmp_path)
    (frontend / 'dist/index.html').write_text(f'<script src="{referencia}"></script>')
    assert front_desactualizado(frontend)


def test_revisa_recursos_transitivos_css_e_importacion_js(tmp_path):
    """065:RF-3 — comprueba también los recursos cargados por CSS y chunks JS."""
    frontend = _front(tmp_path)
    dist = frontend / 'dist'
    (dist / 'index.html').write_text('<script src="/main.js"></script><link rel="stylesheet" href="/main.css">')
    (dist / 'main.js').write_text('import("./chunk.js");')
    (dist / 'main.css').write_text('body { background: url("./fondo.png"); }')
    assert front_desactualizado(frontend)
    (dist / 'chunk.js').write_text('export const x = 1;')
    assert front_desactualizado(frontend)
    (dist / 'fondo.png').write_bytes(b'imagen')
    for fichero in frontend.rglob('*'):
        if fichero.is_file():
            _edad(fichero, 0)
    _edad(dist / 'index.html', 10)
    assert front_desactualizado(frontend) == ''


def test_recursos_externos_y_fragmentos_no_se_buscan_en_disco(tmp_path):
    """065:RF-3 — CDN, data y fragmentos no son archivos de la compilación."""
    frontend = _front(tmp_path)
    (frontend / 'dist/index.html').write_text(
        '<script src="https://cdn.example/app.js"></script><img src="data:image/png;base64,AA==">'
        '<link rel="icon" href="#icono">')
    for fichero in frontend.rglob('*'):
        if fichero.is_file():
            _edad(fichero, 0)
    _edad(frontend / 'dist/index.html', 10)
    assert front_desactualizado(frontend) == ''


@pytest.mark.parametrize('contenido', [
    '<style>body { background: url("./falta.png"); }</style>',
    '<div style="background: url(./falta.png)"></div>',
    '<script type="module">import("./falta.js")</script>',
    '<svg><use href="./falta.svg#icono"></use></svg>',
])
def test_recursos_inline_ausentes_tambien_impiden_arranque(tmp_path, contenido):
    """065:RF-3 — CSS o módulos insertados en HTML no eluden el control de recursos."""
    frontend = _front(tmp_path)
    (frontend / 'dist/index.html').write_text(contenido)
    assert front_desactualizado(frontend)


def test_dependencia_preload_generada_por_vite_no_puede_faltar(tmp_path):
    """065:RF-3 — el CSS diferido de Vite también forma parte del build completo."""
    frontend = _front(tmp_path)
    (frontend / 'dist/index.html').write_text('<script src="./main.js"></script>')
    (frontend / 'dist/main.js').write_text(
        'const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/falta.css"])))=>i.map(i=>d[i]);')
    assert front_desactualizado(frontend)


def test_cli_valida_staging_explicito_antes_de_publicar(tmp_path, monkeypatch):
    """065:RF-3; 065:RF-4 — build puede rechazar su staging sin sustituir el publicado."""
    from convertersmartgrid.web import runtime

    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    staging = tmp_path / 'staging'
    staging.mkdir()
    (staging / 'index.html').write_text('<script src="./falta.js"></script>')
    assert runtime.main(['--validate-dist', str(staging)]) == 1
    (staging / 'falta.js').write_text('console.log("presente")')
    assert runtime.main(['--validate-dist', str(staging)]) == 0


def test_validacion_staging_se_ejecuta_directa_sin_paquete_instalado(tmp_path):
    """065:RF-4 — el publicador puede validar con stdlib y el runtime del checkout exacto."""
    staging = tmp_path / 'staging'
    staging.mkdir()
    (staging / 'index.html').write_text('<html>completo</html>')
    script = RAIZ / 'src/convertersmartgrid/web/runtime.py'
    resultado = subprocess.run([sys.executable, '-I', '-B', str(script), '--validate-dist', str(staging)],
                              cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
