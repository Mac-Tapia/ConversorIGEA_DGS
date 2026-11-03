"""046:RF-20 a RF-25 — el pronóstico, opcional y separado de la medición."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from openpyxl import Workbook
from pronostico_sintetico import curva

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'src/convertersmartgrid'
MODULOS_PROHIBIDOS = ('pronostico', 'adaptador_neuralforecast', 'evaluacion_temporal', 'temporal_entrenamiento')


def _importa_pronostico(ruta: Path) -> list[str]:
    fallos = []
    for n in ast.walk(ast.parse(ruta.read_text(encoding='utf-8'))):
        nombres = []
        if isinstance(n, ast.Import):
            nombres = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            nombres = [n.module or ''] + [f'{n.module}.{a.name}' for a in n.names]
        fallos += [x for x in nombres if x.split('.')[-1] in MODULOS_PROHIBIDOS]
    return fallos


def test_calibracion_caso_base_e_informes_no_leen_pronosticos():
    """046:RF-20 — ningún módulo de calibración, caso base o informes importa el pronóstico."""
    modulos = ['ajuste_cabecera.py', 'demanda_medida.py', 'cargas_pf.py', 'informes.py', 'reglas.py']
    presentes = [SRC / m for m in modulos if (SRC / m).is_file()]
    assert len(presentes) >= 3
    for ruta in presentes:
        assert not _importa_pronostico(ruta), ruta


def test_digsilent_no_recibe_pronosticos():
    """046:RF-21 — ningún guion de DIgSILENT importa el pronóstico ni nombra su artefacto."""
    for ruta in (RAIZ / 'tools').glob('*.py'):
        texto = ruta.read_text(encoding='utf-8')
        if 'pf_arnes' in texto or 'powerfactory' in texto.lower():
            assert not _importa_pronostico(ruta) and 'pronostico.json' not in texto, ruta


def test_crecimiento_sigue_sin_pronostico():
    """046:RF-22 — la tasa del PIDE sigue en ``crecimiento.py``, sin red ni pronóstico."""
    ruta = SRC / 'crecimiento.py'
    assert not _importa_pronostico(ruta)
    assert 'digital_twin' not in ruta.read_text(encoding='utf-8')


def test_ningun_camino_lo_lanza_por_defecto():
    """046:RF-23 — solo la ruta con ``modo: pronostico`` y el asistente con su formulario lo piden."""
    fuera = []
    for ruta in SRC.rglob('*.py'):
        if 'gemelo_pronostico' in ruta.read_text(encoding='utf-8'):
            fuera.append(ruta.relative_to(SRC).as_posix())
    assert sorted(fuera) == ['web/app.py', 'web/services.py']


def _xlsx(ruta: Path, dias: int) -> Path:
    libro = Workbook()
    libro.remove(libro.active)
    h = libro.create_sheet('MED1')
    h.append(['Fecha', 'kW', 'kVAR'])
    for t, v in curva(dias, base=800.0, semilla=5):
        h.append([t, v, v * .3])
    libro.save(ruta)
    return ruta


def _trabajador(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RAIZ / 'tools/digital_twin_temporal_entrenar.py'), *args],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=RAIZ,
                          env={**__import__('os').environ, 'PYTHONPATH': str(RAIZ / 'src'), 'OPENBLAS_NUM_THREADS': '1'})


def test_inventario_sin_entrenar(tmp_path):
    """046:RF-12 — el trabajador dice rango, cadencia y huecos de cada objetivo, sin GPU."""
    libro = _xlsx(tmp_path / 'c.xlsx', 3)
    salida = tmp_path / 'inv.json'
    p = _trabajador('--inventario', '--clase', 'cabecera', '--cabeceras', str(libro), '--par', 'A1=MED1',
                    '--zona-horaria', 'UTC', '--cadencia-min', '15', '--raiz', str(tmp_path), '--output-json', str(salida))
    assert p.returncode == 0, p.stderr
    r = json.loads(salida.read_text(encoding='utf-8'))
    assert {o['objetivo'] for o in r['objetivos']} == {'cabecera:A1:kW', 'cabecera:A1:kVAR'}
    assert r['objetivos'][0]['huecos'] == 0 and r['objetivos'][0]['cadencia_moda_min'] == 15
    assert r['status'] == 'INVENTARIO' and r['training_completed'] is False


def test_referencias_de_extremo_a_extremo_sin_gpu(tmp_path):
    """046:RF-13 / 046:RF-15 — sin candidatos neuronales el trabajador no pide GPU y dice quién gana."""
    libro = _xlsx(tmp_path / 'c.xlsx', 100)
    salida = tmp_path / 'r.json'
    p = _trabajador('--comparar', 'ingenuo,estacional_semanal', '--clase', 'cabecera', '--cabeceras', str(libro),
                    '--par', 'A1=MED1', '--zona-horaria', 'UTC', '--cadencia-min', '15', '--raiz', str(tmp_path),
                    '--output-json', str(salida), '--paso-emision-min', '360', '--semillas', '11')
    assert p.returncode == 0, p.stdout + p.stderr
    r = json.loads(salida.read_text(encoding='utf-8'))
    assert r['status'] == 'RECHAZADO' and r['training_completed'] is False and r['promovido'] is False
    assert r['evaluation_completed'] is True
    assert all(g['es_referencia'] for g in r['ganadores'].values())
    art = json.loads(Path(r['artefacto']).read_text(encoding='utf-8'))
    assert art['marca'] == 'pronostico' and {f['target'] for f in art['filas']} == set(r['ganadores'])


def test_config_nhits_ya_no_es_error_de_entorno_fijo(tmp_path):
    """046:RF-13 — ``reentrenar_modelos`` lanza el trabajador real, no un «pendiente de spec 046»."""
    texto = (RAIZ / 'tools/reentrenar_modelos.py').read_text(encoding='utf-8')
    assert 'pendiente de spec 046' not in texto
    sys.path.insert(0, str(RAIZ))
    from types import SimpleNamespace

    from tools.reentrenar_modelos import orden_temporal
    args = SimpleNamespace(cabeceras=Path('libro.xlsx'), twin=tmp_path, zona_horaria='UTC', pares_temporales=['A=M'],
                           clientes_temporales=None, clase_temporal='cabecera', cadencia_temporal=15, semillas='11')
    cmd = orden_temporal(args, tmp_path / 'r.json', 'nhits')
    assert '--comparar' in cmd and cmd[cmd.index('--comparar') + 1] == 'ingenuo,estacional_semanal,gru,nhits'
    assert '--par' in cmd and '--cadencia-min' in cmd


def test_servicio_lanza_otro_proceso_cancelable(tmp_path, monkeypatch):
    """046:RF-24 — la web lanza el trabajador con ``run_process`` y devuelve su informe."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services
    vistos = {}

    def correr(cmd, cwd=None, env=None):
        vistos['cmd'] = cmd
        destino = Path(cmd[cmd.index('--output-json') + 1])
        destino.write_text(json.dumps({'status': 'RECHAZADO', 'ganadores': {}, 'artefacto': 'a.json',
                                       'marca': 'pronostico'}), encoding='utf-8')
        return 0

    ws = SimpleNamespace(out_dir=tmp_path)
    ctx = SimpleNamespace(run_process=correr, log=lambda _m: None, job=SimpleNamespace(id='J'))
    r = services.gemelo_pronostico(ws, ctx, {'clase': 'cabecera', 'libros': [str(tmp_path)], 'zona_horaria': 'UTC',
                                             'cadencia_min': 15, 'pares': {'A': 'M'},
                                             'algoritmos': ['ingenuo', 'estacional_semanal']})
    assert r['status'] == 'RECHAZADO' and r['artefacto'] == 'a.json'
    assert '--comparar' in vistos['cmd'] and 'digital_twin_temporal_entrenar.py' in vistos['cmd'][1]
    with pytest.raises(services.UserError, match='zona'):
        services.gemelo_pronostico(ws, ctx, {'clase': 'cabecera', 'libros': [str(tmp_path)], 'pares': {'A': 'M'}})
    with pytest.raises(services.UserError, match='clase'):
        services.gemelo_pronostico(ws, ctx, {'clase': 'otro', 'libros': [str(tmp_path)], 'zona_horaria': 'UTC'})


def test_ruta_web_con_modo_pronostico(tmp_path, monkeypatch):
    """046:RF-23 / 046:RF-24 — la ruta temporal lo encola solo con ``modo: pronostico``; sin él, todo sigue igual."""
    import time

    from fastapi.testclient import TestClient

    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app
    pedidos = []
    monkeypatch.setattr(services, 'gemelo_pronostico',
                        lambda _ws, _ctx, pedido: pedidos.append(pedido) or {'status': 'RECHAZADO', 'marca': 'pronostico'})
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        wid = c.post('/api/workspaces').json()['id']
        assert c.post(f'/api/workspaces/{wid}/digital-twin/temporal', json={'clase': 'cabecera'}).status_code == 422
        assert not pedidos
        r = c.post(f'/api/workspaces/{wid}/digital-twin/temporal', json={'modo': 'pronostico', 'clase': 'cliente'})
        assert r.status_code == 202
        for _ in range(100):
            trabajo = c.get(f"/api/jobs/{r.json()['id']}").json()
            if trabajo['status'] not in ('queued', 'running', 'pending'):
                break
            time.sleep(.05)
    assert pedidos and pedidos[0]['clase'] == 'cliente'
    assert trabajo['result']['marca'] == 'pronostico'


def test_reconstruccion_dice_que_no_es_pronostico():
    """046:RF-25 — ``gemelo_temporal`` dice que reconstruye a un paso, no que pronostica."""
    from threading import Lock
    from types import SimpleNamespace

    from convertersmartgrid.web import services
    inicio = datetime(2026, 7, 1)
    t = [inicio + timedelta(minutes=15 * i) for i in range(3 * 96)]
    ws = SimpleNamespace(lock=Lock(), curvas_cabecera={'J': {'M': {'curva': [(x, 10.0 + i % 96, 0.0) for i, x in enumerate(t)]}}})
    # La GRU pide CUDA: el resultado se comprueba con el estacional, sin GPU.
    import unittest.mock as mock

    from convertersmartgrid.digital_twin import temporal
    with mock.patch.object(temporal, 'modelo_temporal', lambda **_k: temporal.ModeloEstacional()):
        r = services.gemelo_temporal(ws, SimpleNamespace(log=lambda _m: None), 'J', {'A': 'M'})
    assert r['salida'] == 'reconstruccion_un_paso' and 'no es un pronóstico' in r['aviso']


def test_asistente_pide_el_pronostico_solo_con_su_formulario():
    """046:RF-23 — el asistente reutiliza la tarea temporal; el pronóstico solo con su formulario."""
    from convertersmartgrid.asistente.ejecutor import pasos
    normal = pasos('gemelo_temporal', {}, {'ultima_maxima': {'id': 'J', 'result': {'resultados': []}}})
    assert 'modo' not in normal[0].cuerpo
    pedido = {'clase': 'cliente', 'libros': ['x'], 'zona_horaria': 'UTC', 'cadencia_min': 15}
    p = pasos('gemelo_temporal', {}, {'pronostico': pedido})
    assert p[0].ruta == '/digital-twin/temporal' and p[0].cuerpo['modo'] == 'pronostico' and p[0].cuerpo['clase'] == 'cliente'
