"""102:RF-31 a RF-33 (T22 a T24): la CI corre los dos arneses de navegador, conserva sus evidencias aunque falle y audita
las dependencias (auditoría del 18-11, H06, H07 y H14).

- RF-31: un solo punto de entrada (``npm run e2e:todo``) corre ``frontend/test/e2e`` y ``frontend/e2e``; falla si falla
  cualquiera, aunque el otro pase, y ninguno se salta en silencio. Un trabajo de la CI lo corre sin modelo ni teselas.
- RF-32: ``puerta_calidad --ci`` deja su JUnit y su veredicto en una ruta fija, y la CI los sube con ``if: always()``,
  como las evidencias de las e2e.
- RF-33: la CI audita las dependencias de npm y de Python con herramientas de versión fijada.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / 'frontend'
TODOS = FRONT / 'test' / 'e2e' / 'todos.mjs'


def _flujo() -> dict:
    import yaml

    return yaml.safe_load((RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8'))


def _pasos(trabajo: str) -> list[dict]:
    return _flujo()['jobs'][trabajo]['steps']


def _ordenes(trabajo: str) -> str:
    return '\n'.join(str(p.get('run', '')) for p in _pasos(trabajo))


def _puerta():
    spec = importlib.util.spec_from_file_location('puerta_calidad_rf32', RAIZ / 'tools' / 'puerta_calidad.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# ------------------------------------------------------------------ RF-31
def test_102_rf31_un_solo_punto_de_entrada_corre_los_dos_arneses():
    scripts = json.loads((FRONT / 'package.json').read_text(encoding='utf-8'))['scripts']
    assert scripts.get('e2e:todo') == 'node test/e2e/todos.mjs', '102:RF-31: falta «npm run e2e:todo»'
    texto = TODOS.read_text(encoding='utf-8')
    assert 'test/e2e/playwright.config.mjs' in texto and 'e2e/playwright.config.ts' in texto


def _correr_todos(tmp_path, codigos: dict[str, int], plano: Path | None = None) -> tuple[int, str, list[str]]:
    """``todos.mjs`` con un Playwright falso que sale con el código pedido por configuración y anota cada llamada.

    La evidencia va a ``tmp_path/evidencia`` (CSG_E2E_EVIDENCIA), nunca al ``output/e2e`` del checkout."""
    anotadas = tmp_path / 'llamadas.txt'
    falso = tmp_path / 'playwright_falso.mjs'
    falso.write_text(
        "import { appendFileSync } from 'node:fs';\n"
        "const c = process.argv[process.argv.indexOf('-c') + 1];\n"
        f"appendFileSync({json.dumps(str(anotadas))}, c + '\\n');\n"
        f"const codigos = {json.dumps(codigos)};\n"
        "process.exit(codigos[c] ?? 0);\n", encoding='utf-8')
    env = {**os.environ, 'CSG_E2E_PLAYWRIGHT': str(falso), 'CSG_E2E_EVIDENCIA': str(tmp_path / 'evidencia'),
           'CSG_E2E_RESULTADOS_PLANO': str(plano or tmp_path / 'sin_plano')}
    r = subprocess.run(['node', str(TODOS)], cwd=FRONT, env=env, capture_output=True, text=True, timeout=60,
                       encoding='utf-8', errors='replace')
    llamadas = anotadas.read_text(encoding='utf-8').split() if anotadas.exists() else []
    return r.returncode, r.stdout + r.stderr, llamadas


def test_102_rf31_falla_si_falla_cualquiera_y_corre_los_dos_igual(tmp_path):
    assert TODOS.is_file(), '102:RF-31: falta frontend/test/e2e/todos.mjs'
    rc, salida, llamadas = _correr_todos(tmp_path, {'test/e2e/playwright.config.mjs': 1})
    assert rc != 0, f'un arnés en rojo no dejó la corrida en rojo:\n{salida}'
    assert llamadas == ['test/e2e/playwright.config.mjs', 'e2e/playwright.config.ts'], \
        f'no corrió los dos arneses: {llamadas}'
    rc, salida, _ = _correr_todos(tmp_path, {'e2e/playwright.config.ts': 1})
    assert rc != 0, f'el segundo arnés en rojo no dejó la corrida en rojo:\n{salida}'
    rc, salida, llamadas = _correr_todos(tmp_path, {})
    assert rc == 0 and len(llamadas) == 6, salida  # las tres corridas anotan en el mismo fichero: 3 × 2 arneses


def _sello(carpeta: Path) -> dict[str, str]:
    lineas = (carpeta / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
    return {ruta: huella for huella, ruta in (linea.split('  ', 1) for linea in lineas)}


def test_086_rf107_e2e_todo_sella_su_evidencia_por_revision_solo_en_verde(tmp_path):
    """086:RF-107 (086 T79) — «npm run e2e:todo» deja la evidencia de los dos arneses en output/e2e/<sha>/, la del
    plano en plano/, y solo una corrida en verde la sella con SHA256SUMS; una que cae no hereda el sello anterior."""
    import hashlib
    plano = tmp_path / 'resultados_plano'
    (plano / 'artefactos').mkdir(parents=True)
    (plano / 'informe.json').write_text('{"suites": []}', encoding='utf-8')
    (plano / 'artefactos' / 'captura.png').write_bytes(b'png falso')
    rc, salida, _ = _correr_todos(tmp_path, {}, plano)
    assert rc == 0, salida
    assert (tmp_path / 'evidencia').is_dir(), f'e2e:todo no dejó su evidencia en CSG_E2E_EVIDENCIA: {salida}'
    revisiones = [d for d in (tmp_path / 'evidencia').iterdir() if d.is_dir()]
    assert len(revisiones) == 1, f'una carpeta por revisión: {revisiones}'
    carpeta = revisiones[0]
    assert (carpeta / 'SHA256SUMS').is_file(), f'la corrida en verde no selló su evidencia: {salida}'
    sello = _sello(carpeta)
    assert {'resumen_e2e.json', 'plano/informe.json', 'plano/artefactos/captura.png'} <= set(sello), sello
    for ruta, h in sello.items():
        assert hashlib.sha256((carpeta / ruta).read_bytes()).hexdigest() == h, ruta
    resumen = json.loads((carpeta / 'resumen_e2e.json').read_text(encoding='utf-8'))
    assert resumen['verde'] is True and [a['codigo'] for a in resumen['arneses']] == [0, 0]
    assert resumen['revision'] == carpeta.name
    rc, salida, _ = _correr_todos(tmp_path, {'e2e/playwright.config.ts': 1}, plano)
    assert rc != 0
    assert not (carpeta / 'SHA256SUMS').exists(), 'una corrida que cae heredó el sello de la anterior'
    assert json.loads((carpeta / 'resumen_e2e.json').read_text(encoding='utf-8'))['verde'] is False


def test_102_rf31_la_ci_corre_las_e2e_sin_modelo_ni_teselas():
    flujo = _flujo()
    assert 'e2e' in flujo['jobs'], '102:RF-31: la CI no tiene trabajo de e2e'
    trabajo = flujo['jobs']['e2e']
    assert trabajo['runs-on'] == 'windows-latest'
    ordenes = _ordenes('e2e')
    assert 'npm run e2e:todo' in ordenes and 'npx playwright install chromium' in ordenes
    assert 'npm run build' in ordenes, 'las e2e prueban el frontend compilado de esta revisión'
    paso = next(p for p in _pasos('e2e') if 'npm run e2e:todo' in str(p.get('run', '')))
    env = {**trabajo.get('env', {}), **paso.get('env', {})}
    assert env.get('CSG_E2E_SIN_MODELO') == '1' and env.get('CSG_SALIDA_TESELAS') == '0'
    assert env.get('CSG_ASISTENTE_OLLAMA') == '0'
    assert 'continue-on-error' not in json.dumps(trabajo)


# ------------------------------------------------------------------ RF-32
def _subidas(trabajo: str) -> list[dict]:
    return [p for p in _pasos(trabajo) if str(p.get('uses', '')).startswith('actions/upload-artifact@')]


def test_102_rf32_la_ci_sube_el_junit_y_las_evidencias_aunque_falle():
    for trabajo, ruta in (('backend', 'resultados_ci'), ('e2e', 'frontend/e2e/resultados')):
        subidas = _subidas(trabajo)
        assert subidas, f'102:RF-32: el trabajo {trabajo} no sube sus evidencias'
        assert all(p.get('if') == 'always()' for p in subidas), f'{trabajo}: la evidencia se pierde si falla'
        assert any(ruta in str(p.get('with', {}).get('path', '')) for p in subidas), (trabajo, ruta)
        assert all(p['with'].get('if-no-files-found') == 'error' for p in subidas), \
            f'{trabajo}: sin JUnit la subida no puede pasar por buena'


def test_102_rf32_puerta_ci_conserva_su_junit_en_una_ruta_fija(tmp_path, monkeypatch):
    PC = _puerta()
    vistas = {}

    def falso_pytest(argumentos, entorno, raiz, exigidas=(), *, conservar=None, procesos=1):
        vistas['conservar'] = conservar
        return {'total': 3, 'fallidas': [], 'omitidas': [], 'lentas': [], 'mas_de_umbral': []}

    monkeypatch.setattr(PC, '_pytest', falso_pytest)
    monkeypatch.setattr(PC, '_procesos_de_la_suite_entera', lambda: 1)
    monkeypatch.setenv('CSG_CI_EVIDENCIA', str(tmp_path / 'ci'))
    assert PC.puerta_ci(tmp_path) == 0
    assert vistas['conservar'] is not None, '102:RF-32: puerta_ci no conserva su JUnit'
    assert Path(vistas['conservar']).parent == tmp_path / 'ci'
    veredicto = json.loads((tmp_path / 'ci' / 'veredicto.json').read_text(encoding='utf-8'))
    assert veredicto['total'] == 3 and veredicto['fallidas'] == [] and veredicto['ok'] is True


def test_102_rf32_puerta_ci_deja_el_veredicto_tambien_si_falla(tmp_path, monkeypatch):
    PC = _puerta()
    monkeypatch.setattr(PC, '_pytest', lambda *a, **k: {'total': 2, 'fallidas': [{'prueba': 't', 'motivo': 'x'}],
                                                        'omitidas': [], 'lentas': [], 'mas_de_umbral': []})
    monkeypatch.setattr(PC, '_procesos_de_la_suite_entera', lambda: 1)
    monkeypatch.setenv('CSG_CI_EVIDENCIA', str(tmp_path / 'ci'))
    assert PC.puerta_ci(tmp_path) == 1
    assert (tmp_path / 'ci' / 'veredicto.json').is_file(), '102:RF-32: una suite en rojo no deja su veredicto'
    veredicto = json.loads((tmp_path / 'ci' / 'veredicto.json').read_text(encoding='utf-8'))
    assert veredicto['ok'] is False and veredicto['fallidas']


# ------------------------------------------------------------------ RF-33
def test_102_rf33_la_ci_audita_las_dependencias_con_versiones_fijadas():
    import re

    assert 'npm audit --audit-level=high' in _ordenes('frontend'), '102:RF-33: falta npm audit'
    backend = _ordenes('backend')
    assert re.search(r'pip install pip-audit==\d+\.\d+\.\d+', backend), '102:RF-33: pip-audit sin versión fijada'
    assert re.search(r'pip_audit .*--skip-editable', backend), '102:RF-33: falta la auditoría del .venv del flujo'
    assert 'pip install --upgrade pip-audit' not in backend and 'npm audit fix' not in _ordenes('frontend'), \
        '102:RF-33: la CI no actualiza paquetes sola para borrar un aviso'


def test_102_rf32_las_evidencias_de_la_ci_no_van_al_repositorio():
    ignorado = (RAIZ / '.gitignore').read_text(encoding='utf-8')
    assert '/resultados_ci/' in ignorado.splitlines()


if __name__ == '__main__':  # pragma: no cover
    sys.exit(subprocess.call([sys.executable, '-m', 'pytest', __file__, '-q']))
