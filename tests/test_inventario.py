"""Spec 009: cada fichero en su sitio, cada herramienta usable y cada spec al día.

La revisión del 2026-10-10 encontró 16 herramientas sueltas, un índice del código con
12 de más de 100 módulos y una spec con la validación sin marcar. Estas pruebas hacen
que un fichero nuevo sin índice, una herramienta que no arranca o una spec que miente
sobre su estado dejen la suite en rojo.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
INDICE = (RAIZ / 'CODIGO_FUENTE.md').read_text(encoding='utf-8')
#: Lo que el índice lista: los ficheros versionados de estas carpetas.
CARPETAS = ('src/', 'tools/', 'frontend/src/')
#: Retiradas por RF-4: campañas pasadas que nada usaba.
RETIRADAS = (
    '_enrich_production_readiness_retry.py', '_publish_to_github.py', '_retry_pf_gaps.py',
    '_retry_pf_timeouts.py', '_run_production_pf_batch.py', '_write_production_readiness.py',
    'prod_readiness_sample.py', 'audit_ternas_backbone.py', 'audit_ternas_classify.py',
    'audit_ternas_ug.py',
    # 2026-10-14: emparejaba TXT y bases «de la misma foto» para comparar una fuente con
    # otra; las fuentes son independientes y esas comparaciones se retiraron.
    'emparejar_entradas.py',
)
#: Tareas que no son de código: la prueba en DIgSILENT la hace el usuario.
DEL_USUARIO = re.compile(r'a cargo del usuario|la hace el usuario', re.I)


def _versionados() -> list[str]:
    salida = subprocess.run(['git', 'ls-files', *CARPETAS], cwd=RAIZ, capture_output=True,
                            text=True, encoding='utf-8', check=True).stdout
    return sorted(f for f in salida.splitlines() if '__pycache__' not in f)


def _herramientas() -> list[Path]:
    return sorted((RAIZ / 'tools').glob('*.py'))


def test_el_indice_lista_cada_fichero():
    """009:RF-1 / 009:RF-2 — cada módulo de src/, herramienta de tools/ y fichero del front
    versionado está en CODIGO_FUENTE.md."""
    faltan = [f for f in _versionados() if f'`{f}`' not in INDICE]
    assert not faltan, f'Sin entrada en CODIGO_FUENTE.md: {faltan}'


def test_el_indice_no_nombra_ficheros_que_no_existen():
    """009:RF-3 — cada ruta de la primera columna del índice existe."""
    rutas = re.findall(r'^\| `([^`]+)` \|', INDICE, re.M)
    assert len(rutas) > 100
    # «specs/NNN-*/» y «docs/DIAGNOSTICO_*.md» son patrones: basta con que casen con algo.
    fantasmas = [r for r in rutas if not any(RAIZ.glob(r.replace('NNN', '[0-9]' * 3).rstrip('/')))]
    assert not fantasmas, f'El índice nombra ficheros que no existen: {fantasmas}'


def test_herramientas_retiradas():
    """009:RF-4 — las herramientas de campañas pasadas ya no están."""
    quedan = [n for n in RETIRADAS if (RAIZ / 'tools' / n).exists()]
    assert not quedan, quedan


def _importados(path: Path) -> set[str]:
    arbol = ast.parse(path.read_text(encoding='utf-8'))
    nombres = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            nombres |= {a.name.split('.')[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            nombres.add(n.module.split('.')[0])
    return nombres


def test_ninguna_herramienta_importa_de_tests():
    """009:RF-5 — una herramienta que importa de tests/ solo arranca con tests/ en la ruta."""
    de_tests = {p.stem for p in (RAIZ / 'tests').glob('*.py')}
    malas = {p.name: sorted(_importados(p) & de_tests) for p in _herramientas()}
    assert not {k: v for k, v in malas.items() if v}


def test_cada_herramienta_dice_para_que_sirve():
    """009:RF-6 — docstring en español con para qué sirve y cómo se invoca."""
    for p in _herramientas():
        doc = ast.get_docstring(ast.parse(p.read_text(encoding='utf-8'))) or ''
        assert doc, f'{p.name} sin docstring'
        assert re.search(r'\b(de|la|el|que|en|los|las)\b', doc), f'{p.name}: docstring sin español'


@pytest.mark.parametrize('herramienta', [p.name for p in _herramientas()])
def test_help_sin_powerfactory_ni_datos(herramienta, tmp_path):
    """009:RF-7 — ``--help`` termina con 0 sin DIgSILENT ni datos de la distribuidora."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('IGEA_')}
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tools')])
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run([sys.executable, str(RAIZ / 'tools' / herramienta), '--help'], cwd=tmp_path,
                       env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'usage' in r.stdout.lower()


def test_ninguna_herramienta_fija_rutas_de_datos():
    """009:RF-8 — las rutas de los datos de la distribuidora llegan por argumentos."""
    patron = re.compile(r'referencia[/\\]|BaseDatosElectroDunas|RED_\d{6}\(|BD_Equipo_V\d', re.I)
    for p in _herramientas():
        arbol = ast.parse(p.read_text(encoding='utf-8'))
        doc = ast.get_docstring(arbol, clean=False)
        for n in ast.walk(arbol):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc:
                assert not patron.search(n.value), f'{p.name}:{n.lineno}: {n.value!r}'


# ----------------------------------------------------------------- specs

def _specs():
    for d in sorted((RAIZ / 'specs').iterdir()):
        if (d / 'spec.md').is_file():
            yield d.name[:3], d


def _citas() -> str:
    fuentes = list((RAIZ / 'tests').rglob('*.py')) + list((RAIZ / 'frontend' / 'src').rglob('*.ts*'))
    return '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in fuentes)


def _rf(spec: str) -> set[int]:
    return {int(x) for x in re.findall(r'^- RF-(\d+)', spec, re.M)}


def _tareas(d: Path) -> list[tuple[bool, str]]:
    if not (d / 'tasks.md').is_file():
        return []
    return [(m.group(1) == 'x', m.group(2))
            for m in re.finditer(r'^- \[( |x)\] (.*)$', (d / 'tasks.md').read_text(encoding='utf-8'), re.M)]


def test_una_spec_cumplida_no_tiene_tareas_abiertas():
    """009:RF-9 — «cumplida» con tareas sin marcar es mentira."""
    for n, d in _specs():
        estado = re.search(r'^Estado: (.*)$', (d / 'spec.md').read_text(encoding='utf-8'), re.M)
        if estado and estado.group(1).startswith('cumplida'):
            abiertas = [t for hecha, t in _tareas(d) if not hecha]
            assert not abiertas, f'spec {n} dice «cumplida» con tareas abiertas: {abiertas}'


def test_las_pruebas_solo_citan_rf_que_existen():
    """009:RF-10 — una cita a un RF que su spec no define apunta a nada."""
    citas = _citas()
    for n, d in _specs():
        definidos = _rf((d / 'spec.md').read_text(encoding='utf-8'))
        citados = {int(x) for x in re.findall(rf'\b{n}:RF-(\d+)', citas)}
        assert citados <= definidos, f'spec {n}: se citan RF que no define: {sorted(citados - definidos)}'


def test_una_spec_implementada_tiene_cada_rf_probado():
    """009:RF-11 — con sus tareas de código marcadas, cada RF de la spec lo cita una prueba."""
    citas = _citas()
    for n, d in _specs():
        tareas = _tareas(d)
        de_codigo = [hecha for hecha, t in tareas if not DEL_USUARIO.search(t)]
        if not tareas or not all(de_codigo):
            continue
        definidos = _rf((d / 'spec.md').read_text(encoding='utf-8'))
        citados = {int(x) for x in re.findall(rf'\b{n}:RF-(\d+)', citas)}
        assert definidos <= citados, f'spec {n}: RF sin prueba: {sorted(definidos - citados)}'


# ----------------------------------------------------------------- documentación

def test_documentacion_del_manual_de_ordenes():
    """009:RF-12 — el manual describe cada orden de ``igea-dgs`` y cada herramienta."""
    manual = (RAIZ / 'docs' / 'MANUAL_COMANDOS.md').read_text(encoding='utf-8')
    for orden in ('igea-dgs list', 'igea-dgs convert', 'igea-dgs web'):
        assert orden in manual, orden
    faltan = [p.name for p in _herramientas() if p.name not in manual]
    faltan += [p.name for p in (RAIZ / 'tools').glob('*.bat') if p.name not in manual]
    assert not faltan, f'El manual no describe: {faltan}'


def test_documentacion_del_readme():
    """009:RF-13 — el README explica la pestaña de cargas en tres pasos y el perfil de empresa."""
    readme = (RAIZ / 'README.md').read_text(encoding='utf-8')
    for pieza in ('Cargas en DIgSILENT', '1 · Proyecto de DIgSILENT', '2 · Alimentadores y calibración',
                  '3 · Integración de nuevas', 'perfil_empresa.json'):
        assert pieza in readme, pieza


def test_config_sin_datos_de_una_empresa():
    """009:RF-14 — en config/ solo se versionan ejemplos, perfiles genéricos y perfiles de
    empresa con convenciones (los de config/perfiles, que comprueba 002:RF-35)."""
    salida = subprocess.run(['git', 'ls-files', 'config'], cwd=RAIZ, capture_output=True,
                            text=True, encoding='utf-8', check=True).stdout.split()
    genericos = {'config/vnr_dgs_profile.json'}
    malos = [f for f in salida if '.example.' not in f and f not in genericos
             and not (f.startswith('config/perfiles/') and f.endswith('.json'))]
    assert not malos, f'config/ con datos de una empresa en git: {malos}'


_RUTAS = {'get', 'post', 'put', 'delete', 'patch', 'websocket', 'on_event', 'exception_handler', 'middleware'}


def test_sin_definiciones_que_nada_use():
    """009:RF-15 — cada función o clase de nivel superior de src/ la usa algo."""
    salida = subprocess.run(['git', 'ls-files', 'src', 'tools', 'tests', 'frontend/src'], cwd=RAIZ,
                            capture_output=True, text=True, encoding='utf-8', check=True).stdout.split()
    textos = {f: (RAIZ / f).read_text(encoding='utf-8', errors='replace')
              for f in salida if f.endswith(('.py', '.ts', '.tsx')) and (RAIZ / f).is_file()}
    todo = '\n'.join(textos.values())
    muertas = []
    for f, texto in textos.items():
        if not (f.startswith('src/') and f.endswith('.py')):
            continue
        for n in ast.parse(texto).body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or n.name.startswith('__'):
                continue
            if any(isinstance(d, ast.Call) and getattr(d.func, 'attr', '') in _RUTAS for d in n.decorator_list):
                continue
            # La definición cuenta una vez; cualquier otra aparición es un uso.
            if len(re.findall(rf'\b{re.escape(n.name)}\b', todo)) <= 1:
                muertas.append(f'{f}:{n.lineno} {n.name}')
    assert not muertas, f'Sin uso: {muertas}'
