"""Spec 112: la medición de escala de la web y su API con redes sintéticas (112:RF-20, 112:RF-21; 009), y el enlace con
el dibujo medido en navegador real (T19).

La prueba rápida mide 10 alimentadores con pocas repeticiones y solo comprueba la forma del resultado, no tiempos: un
tope de milisegundos dependería de la máquina y de lo que corra a la vez. La corrida de 10, 50 y 200 con sus
repeticiones es una corrida aparte, con su propio registro.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HERRAMIENTA = RAIZ / 'tools' / 'benchmark_escala_web.py'


def _correr(*args, cwd, timeout=600):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CSG_')}
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tools')])
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run([sys.executable, str(HERRAMIENTA), *args], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding='utf-8', timeout=timeout, check=False)


def _herramienta():
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    sys.path.insert(0, str(RAIZ / 'tools'))
    try:
        import benchmark_escala_web
    finally:
        sys.path.pop(0)
    return benchmark_escala_web


def test_help_sin_digsilent(tmp_path):
    """112:RF-20 — ``--help`` sale con 0, sin DIgSILENT, y dice que corre en local con redes sintéticas."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    r = _correr('--help', cwd=tmp_path, timeout=120)
    assert r.returncode == 0 and 'usage' in r.stdout.lower(), r.stderr
    assert 'local' in r.stdout and 'sintéticas' in r.stdout and '--tamanos' in r.stdout


def test_por_defecto_mide_10_50_y_200():
    """112:RF-20 — sin opciones, los tres tamaños del benchmark de escala, y ninguno grabado en otro sitio."""
    b = _herramienta()
    assert tuple(b._argumentos([]).tamanos) == (10, 50, 200)
    assert b._argumentos(['--tamanos', '7', '13']).tamanos == [7, 13]


def test_un_tamano_imposible_es_un_error_de_uso(tmp_path):
    """112:RF-20 — cero alimentadores o una sola repetición no miden nada: error de uso, sin traza ni resultado."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    for args in (('--tamanos', '0'), ('--tamanos', '10', '--repeticiones', '1')):
        r = _correr(*args, '--salida', 'r.json', cwd=tmp_path, timeout=120)
        assert r.returncode == 2 and 'Traceback' not in r.stderr, (args, r.stderr)
        assert not (tmp_path / 'r.json').exists()


def test_percentiles_con_interpolacion():
    """112:RF-20 — p50 y p95 con interpolación lineal, y sin valores no hay percentil (nunca un cero inventado)."""
    b = _herramienta()
    assert b.percentil([5.0, 1.0, 3.0, 2.0, 4.0], 50) == 3.0
    assert b.percentil([1.0, 2.0, 3.0, 4.0, 5.0], 95) == pytest.approx(4.8)
    assert b.percentil([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        b.percentil([], 50)


def test_diez_alimentadores_sinteticos_por_la_api(tmp_path):
    """112:RF-20, 112:RF-21 — de punta a punta con 10 alimentadores sintéticos: la API los lista todos, cada petición
    con su primera llamada aparte, su p50 ≤ p95 y su tamaño; la memoria pico del proceso; la revisión del código; y el
    dibujo de la pantalla «no medido» con su motivo, nunca un cero."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    salida = tmp_path / 'resultado' / 'escala.json'
    r = _correr('--tamanos', '10', '--repeticiones', '3', '--tramos', '20', '--cargas', '6', '--salida', str(salida),
                cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-3000:]
    datos = json.loads(salida.read_text(encoding='utf-8'))
    assert datos['revision']['commit'] and 'cambios_sin_registrar' in datos['revision']
    assert datos['red_sintetica']['semilla'] == 112 and datos['repeticiones'] == 3
    [medida] = datos['tamanos']
    assert medida['alimentadores'] == 10 and medida['alimentadores_listados'] == 10
    assert medida['tramos'] > 0 and medida['cargas'] > 0 and medida['carga_red_s'] > 0
    assert {'espacio', 'alimentadores', 'sed_de_un_alimentador'} <= set(medida['api'])
    for nombre, api in medida['api'].items():
        assert api['n'] == 3 and api['primera_ms'] > 0, nombre
        assert 0 < api['p50_ms'] <= api['p95_ms'] <= api['max_ms'], (nombre, api)
        assert api['bytes'] > 0, nombre
    assert 0 < medida['ram_base_mib'] <= medida['ram_pico_mib']
    render = medida['render']
    assert render['medido'] is False and render['motivo'].startswith('no medido')
    assert not [v for v in render.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]


# --- 112 T19: el dibujo en navegador real, enlazado con el resultado de la T18 -----------------------------------------

GUION_DIBUJO = RAIZ / 'frontend' / 'e2e' / 'escala_dibujo.mjs'
RESUMEN_DIBUJO = RAIZ / 'frontend' / 'e2e' / 'escala_resumen.mjs'
COMMIT = 'c' * 40
RED = {'semilla': 112, 'tramos_tipicos': 200, 'cargas_tipicas': 60}


def _resultado(*tamanos: int) -> dict:
    return {'formato': 1, 'revision': {'commit': COMMIT, 'cambios_sin_registrar': False}, 'red_sintetica': dict(RED),
            'tamanos': [{'alimentadores': n, 'render': {'medido': False, 'motivo': 'no medido: x'}} for n in tamanos]}


def _dibujo(carpeta: Path, n: int, **cambios) -> Path:
    datos = {'formato': 1, 'revision': {'commit': COMMIT}, 'red_sintetica': dict(RED), 'alimentadores': n,
             'repeticiones': 10, 'navegador': {'canal': 'msedge', 'version': '1'},
             'tabla': {'p50_ms': 12.5, 'p95_ms': 20.0}, 'plano': {'p50_ms': 300.0, 'p95_ms': 410.0}}
    for clave, valor in cambios.items():
        datos[clave] = valor
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f'dibujo_{n}.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return ruta


def test_112_rf21_el_dibujo_se_enlaza_solo_con_su_commit_y_su_red(tmp_path):
    """112:RF-21 (T19) — el resultado de la T18 enlaza cada tamaño con el dibujo medido en el navegador para él: el p50 y
    el p95 de la tabla y del plano, el navegador y la ruta del JSON. Un dibujo de otro commit, de otra red, de otro
    tamaño, sin un tiempo positivo o que falta deja el tamaño «no medido» con su motivo, nunca con un cero."""
    b = _herramienta()
    assert hasattr(b, 'enlazar_dibujo'), 'falta enlazar_dibujo en tools/benchmark_escala_web.py'
    carpeta = tmp_path / 'dibujo'
    _dibujo(carpeta, 10)
    _dibujo(carpeta, 50, revision={'commit': 'd' * 40})
    _dibujo(carpeta, 7, red_sintetica=dict(RED, tramos_tipicos=20))
    _dibujo(carpeta, 9, plano={'p50_ms': 0, 'p95_ms': 410.0})
    _dibujo(carpeta, 11, alimentadores=12)
    resultado = b.enlazar_dibujo(_resultado(10, 50, 7, 9, 11, 200), carpeta)
    render = {m['alimentadores']: m['render'] for m in resultado['tamanos']}
    assert render[10]['medido'] is True and render[10]['commit'] == COMMIT, render[10]
    assert render[10]['tabla_p50_ms'] == 12.5 and render[10]['tabla_p95_ms'] == 20.0, render[10]
    assert render[10]['plano_p50_ms'] == 300.0 and render[10]['plano_p95_ms'] == 410.0, render[10]
    assert render[10]['json'].endswith('dibujo/dibujo_10.json') and render[10]['navegador']['canal'] == 'msedge'
    for n, causa in ((50, 'commit'), (7, 'otra red'), (9, 'positivos'), (11, 'no de 11'), (200, 'falta dibujo_200')):
        assert render[n]['medido'] is False and render[n]['motivo'].startswith('no medido') and causa in \
            render[n]['motivo'], (n, render[n])
        assert not [v for v in render[n].values() if isinstance(v, (int, float)) and not isinstance(v, bool)], render[n]
    assert resultado['dibujo'] == carpeta.as_posix()


def test_112_rf21_solo_enlazar_reescribe_el_resultado_sin_medir(tmp_path, capsys):
    """112:RF-21 (T19) — «--solo-enlazar» no vuelve a medir: lee el resultado de la T18, lo enlaza con el dibujo y lo
    reescribe; sin --salida o sin --dibujo es un error de uso."""
    b = _herramienta()
    assert hasattr(b, 'enlazar_dibujo'), 'falta enlazar_dibujo en tools/benchmark_escala_web.py'
    escala = tmp_path / 'escala.json'
    escala.write_text(json.dumps(_resultado(10, 50)), encoding='utf-8')
    _dibujo(tmp_path / 'dibujo', 10)
    _dibujo(tmp_path / 'dibujo', 50)
    assert b.main(['--salida', str(escala), '--dibujo', str(tmp_path / 'dibujo'), '--solo-enlazar']) == 0
    datos = json.loads(escala.read_text(encoding='utf-8'))
    assert [m['render']['medido'] for m in datos['tamanos']] == [True, True], datos
    assert datos['revision']['commit'] == COMMIT, 'no se vuelve a medir: la revisión es la del resultado'
    with pytest.raises(SystemExit) as salida:
        b.main(['--salida', str(escala), '--solo-enlazar'])
    assert salida.value.code == 2 and '--dibujo' in capsys.readouterr().err


def test_112_rf21_la_api_y_el_navegador_miden_la_misma_red(monkeypatch):
    """112:RF-20, 112:RF-21 (T19) — la web de prueba del navegador, con CSG_E2E_ESCALA=1, genera la misma red que mide
    la API (spec_de_escala, con la semilla, los tramos y las cargas de la medición); sin la variable, la sorteada."""
    import importlib.util

    from convertersmartgrid.dominio.benchmarks import sintetico

    assert hasattr(sintetico, 'spec_de_escala'), 'falta spec_de_escala en dominio/benchmarks/sintetico.py'
    b = _herramienta()
    args = b._argumentos([])
    assert (args.semilla, args.tramos, args.cargas) == (sintetico.SEMILLA_DE_ESCALA, sintetico.TRAMOS_DE_ESCALA,
                                                        sintetico.CARGAS_DE_ESCALA)
    assert b.spec_de_escala is sintetico.spec_de_escala, 'la API mide con spec_de_escala'
    monkeypatch.syspath_prepend(str(RAIZ / 'tests'))
    spec = importlib.util.spec_from_file_location('web_de_prueba_112', RAIZ / 'frontend' / 'e2e' / 'web_de_prueba.py')
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)
    assert hasattr(web, 'spec_de_la_red'), 'falta spec_de_la_red en frontend/e2e/web_de_prueba.py'
    for n in (10, 50, 200):
        red, disposicion = web.spec_de_la_red(n, 112, {'CSG_E2E_ESCALA': '1'})
        assert red == sintetico.spec_de_escala(n) and disposicion == red.layout, n
    red, _ = web.spec_de_la_red(50, 112, {'CSG_E2E_ESCALA': '1', 'CSG_E2E_TRAMOS': '20', 'CSG_E2E_CARGAS': '6'})
    assert red == sintetico.spec_de_escala(50, tramos=20, cargas=6)
    assert sintetico.spec_de_escala(200).total_sections == 20 * sintetico.spec_de_escala(10).total_sections, \
        'los mismos tramos por alimentador en 10 y en 200'
    sorteada, disposicion = web.spec_de_la_red(5, 7, {})
    assert sorteada.size_cycle == 0 and sorteada.layout == disposicion and sorteada.sections_per_feeder == 4


def test_112_rf21_el_guion_resume_igual_que_la_api_y_no_usa_las_webs_del_operador():
    """112:RF-21 (T19) — el guion del navegador calcula el p50 y el p95 con la misma interpolación que la API, nunca con
    un tiempo nulo, nombra cada JSON como lo busca «--dibujo» y no arranca su web en 8765 ni en 8766 (con node)."""
    import shutil

    b = _herramienta()
    assert RESUMEN_DIBUJO.is_file() and GUION_DIBUJO.is_file(), 'falta el guion del dibujo de escala (112 T19)'
    node = shutil.which('node')
    assert node, 'hace falta node para comprobar el guion del dibujo'
    valores = [41.0, 12.5, 30.25, 18.0, 55.5, 20.0, 27.0, 33.0, 19.5, 60.0]
    guion = ('const m = await import(process.argv[1]); const v = JSON.parse(process.argv[2]);\n'
             'let cero = null; try { m.resumen([1, 0]); } catch (e) { cero = e.message; }\n'
             'console.log(JSON.stringify({ r: m.resumen(v), nombre: m.nombreDibujo(10), cero,\n'
             '  puertos: [8765, 8766, 50123, 0].map(m.puertoPermitido) }));')
    r = subprocess.run([node, '--input-type=module', '-e', guion, RESUMEN_DIBUJO.as_uri(), json.dumps(valores)],
                       capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res['r']['p50_ms'] == pytest.approx(b.percentil(valores, 50), abs=1e-3), res
    assert res['r']['p95_ms'] == pytest.approx(b.percentil(valores, 95), abs=1e-3), res
    assert res['r']['n'] == 10 and res['r']['max_ms'] == 60.0, res
    assert res['nombre'] == b.NOMBRE_DIBUJO.format(n=10) and res['cero'] and '0' in res['cero'], res
    assert res['puertos'] == [False, False, True, False], res
    texto = GUION_DIBUJO.read_text(encoding='utf-8')
    for necesario in ("canal: 'msedge'", 'channel: a.canal', 'PerformanceObserver', 'performance.mark',
                      "CSG_E2E_ESCALA: '1'", 'puertoPermitido(p)', 'nombreDibujo(n)', 'revision()', "tipo === 'listo'"):
        assert necesario in texto, necesario
    r = subprocess.run([node, '--check', str(GUION_DIBUJO)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
