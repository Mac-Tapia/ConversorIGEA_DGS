"""Comprobación permanente (delta19, orden del auditor 28): ningún fichero de config/ guarda una ruta de la máquina.

El registro normativo y los mapeos van al repositorio y valen para cualquier instalación; las fuentes oficiales
viven fuera de git y se citan por su ruta RELATIVA a la carpeta de fuentes (``fichero_local``) o con el marcador
``<fuentes>/``. Spec 107 (107:RF-7) y principio de universalidad.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Una letra de unidad que no va pegada a otra letra, acentuada o no (así «https:/» y «proyección:\n» no cuentan),
# seguida de «/» o de la barra invertida DOBLADA (en el texto JSON una ruta de Windows lleva «\\»; una sola es un
# escape), «/d/» al inicio de una ruta de MSYS, el usuario de esta máquina y «Users/».
RUTA_DE_LA_MAQUINA = re.compile(r'(?<![^\W\d_])[A-Za-z]:(?:/|\\\\)|(?<![A-Za-z0-9_.-])/d/|Lenovo Legion|Users/')
# Plantillas de EJEMPLO para que cada usuario ponga sus rutas; se retiran de aquí con la tarjeta EJ, que las cambia
# por marcadores («<unidad>:/<carpeta>»).
EXCLUIDOS_DE_MOMENTO = {'archivo.example.json', 'suite_completa.example.json'}


def _versionados(carpeta: Path) -> list[Path]:
    """Los ficheros de ``carpeta`` que git versiona (en el índice). Lo local e ignorado (config/suite_completa.json, con
    las rutas de las 15 variables de ESTA máquina, .gitignore) no va al repositorio ni a otra instalación: no cuenta.
    FIX-D19 (puerta B, c2 15-11): con rglob en disco la prueba caía en cualquier checkout con su suite_completa.json."""
    salida = subprocess.run(['git', 'ls-files', '-z', '--cached', '--', '.'], cwd=carpeta, capture_output=True,
                            check=True)
    return [carpeta / r for r in sorted(salida.stdout.decode('utf-8').split('\0')) if r]


def _hallazgos(carpeta: Path) -> list[str]:
    salida = []
    for f in _versionados(carpeta):
        if not f.is_file() or f.name in EXCLUIDOS_DE_MOMENTO:
            continue
        try:
            texto = f.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for n, linea in enumerate(texto.splitlines(), start=1):
            m = RUTA_DE_LA_MAQUINA.search(linea)
            if m:
                salida.append(f'{f.relative_to(carpeta.parent).as_posix()}:{n}: «{linea[max(0, m.start() - 30):m.end() + 40]}»')
    return salida


def test_config_no_guarda_rutas_de_la_maquina():
    """107:RF-7 — ninguna ruta absoluta ni de usuario en config/ (salvo las plantillas de ejemplo de la tarjeta EJ)."""
    hallados = _hallazgos(RAIZ / 'config')
    assert not hallados, 'rutas de la máquina en config/:\n' + '\n'.join(hallados[:20])


def test_el_patron_distingue_una_url_de_una_ruta():
    """107:RF-7 — el patrón caza «D:/…», «C:\\…», «/d/…», el usuario y «Users/», pero no «https://» ni «a/d/b»."""
    barra = chr(92)
    for texto, ruta in (('D:/csg/x', True), ('C:' + barra * 2 + 'x', True), ('/d/csg/x', True), ('C:/Users/x', True),
                        ('https://www.osinergmin.gob.pe/x', False), ('a/d/b', False), ('mailto:x', False),
                        ('horizonte de proyección:' + barra + 'n- Para', False)):
        assert bool(RUTA_DE_LA_MAQUINA.search(texto)) is ruta, texto


def test_solo_cuenta_lo_versionado_no_lo_local_ignorado(tmp_path):
    """107:RF-7 — FIX-D19: un config/suite_completa.json LOCAL e ignorado por git, con las rutas de esta máquina, no es
    un hallazgo; la misma ruta en un fichero versionado de config/ sí lo es."""
    import subprocess as sp
    sp.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('config/suite_completa.json\n', encoding='utf-8')
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'suite_completa.json').write_text('{"CSG_X": "D:/datos/x"}\n', encoding='utf-8')
    (config / 'versionado.json').write_text('{"ruta": "D:/datos/y"}\n', encoding='utf-8')
    (config / 'limpio.json').write_text('{"url": "https://www.osinergmin.gob.pe/x"}\n', encoding='utf-8')
    sp.run(['git', 'add', '.gitignore', 'config/versionado.json', 'config/limpio.json'], cwd=tmp_path, check=True)
    hallados = _hallazgos(config)
    assert [h.split(':', 1)[0] for h in hallados] == ['config/versionado.json'], hallados
