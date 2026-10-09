"""001:RF-27 — el lanzador recompila el front cuando su código es más reciente."""
from __future__ import annotations

import os
from pathlib import Path

from igea_dgs.web.runtime import front_desactualizado

RAIZ = Path(__file__).resolve().parents[1]


def _front(tmp_path, *, dist: bool = True) -> Path:
    frontend = tmp_path / 'frontend'
    (frontend / 'src' / 'components').mkdir(parents=True)
    (frontend / 'src' / 'components' / 'Panel.tsx').write_text('x', encoding='utf-8')
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
    _edad(frontend / 'src' / 'components' / 'Panel.tsx', 20)
    assert front_desactualizado(frontend) == (
        'src/components/Panel.tsx es más reciente que la compilación')


def test_el_lanzador_usa_la_comprobacion():
    """001:RF-27 — run_gui.bat pregunta antes de abrir y compila si hace falta."""
    bat = (RAIZ / 'run_gui.bat').read_bytes().decode('ascii')
    comprobacion = bat.index('-m igea_dgs.web.runtime --front')
    compila = bat.index('call npm run build')
    abre = bat.index('-m igea_dgs.web\r\n')
    assert comprobacion < compila < abre
    # Ya no se compila solo cuando falta dist: la comprobación decide.
    assert 'if not exist "frontend\\dist\\index.html" (\r\n  where npm' not in bat
