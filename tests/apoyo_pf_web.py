"""Guion falso de DIgSILENT para las pruebas web de la spec 011.

Hace de ``casos_pf.py``, ``estudios_pf.py``, ``obras_pf.py`` y ``transferencia_pf.py``
según el nombre con que se le llame, y devuelve lo que recibió en el plan: las pruebas
web comprueban qué manda la web y qué hace con la respuesta. Los guiones de verdad se
prueban contra ``fake_pf`` en sus ``test_*_guion.py``.
"""
from __future__ import annotations

import sys

import pytest

GUION_FALSO = r'''
import argparse, json, sys, time
from pathlib import Path
herramienta = Path(sys.argv[0]).name.removeprefix('falso_')
p = argparse.ArgumentParser()
for opcion in ('--plan', '--output-json', '--cancel-file', '--fichero'):
    p.add_argument(opcion)
p.add_argument('--simular', action='store_true')
p.add_argument('--bibliotecas', action='store_true')
p.add_argument('--guion', action='store_true')
a = p.parse_args()
plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
proyecto = plan['project']
informe = {'recibido': plan}
if herramienta == 'casos_pf.py':
    if proyecto == 'BASE_BORRADA':
        informe = {'error': 'Ya no están en el proyecto estas variaciones de la base: Ajuste_A1_1'}
    else:
        informe.update(feeders=plan['feeders'], avisos=[],
                       casos={'con': {'estudiable': proyecto != 'SIN_CARGAS'}})
elif herramienta == 'estudios_pf.py' and a.guion and not plan.get('guion'):
    informe.update(guiones=[{'nombre': 'Revisar', 'clase': 'ComDpl', 'origen': 'proyecto',
                             'casos': ['sin', 'con'], 'objetos': ['barra'],
                             'parametros': [{'nombre': 'umbral', 'tipo': 'double', 'valor': '0.95',
                                             'unidad': 'p.u.', 'descripcion': ''}]}])
elif herramienta == 'estudios_pf.py' and a.guion:
    nombre = plan['guion']['nombre']
    if nombre == 'FALLA' and plan['caso'] == 'sin':
        informe.update(codigo_guion=3, salida=['algo salió mal'],
                       error='el guion FALLA terminó con el código 3 en «Sin proyecto»')
    else:
        informe.update(codigo_guion=0, salida=[f"{plan['caso']}: {json.dumps(plan['parametros'], sort_keys=True)}"])
elif herramienta == 'estudios_pf.py':
    if proyecto == 'LENTO' and plan['estudio'] == 'contingencias':
        time.sleep(60)
    informe.update(caso=plan['caso'], estudio=plan['estudio'], avisos=[],
                   obras_activas=['Obra_terna_A1'] if plan['caso'] == 'con' else [], medidas={
        f: {'converge': True, 'vm_min': 0.97, 'vm_min_barra': 'B1', 'vm_max': 1.0,
            'vm_max_barra': 'B0', 'mas_cargado': 'L1', 'cargabilidad_max': 50.0,
            'cabecera_kw': 1000.0, 'cabecera_kvar': 300.0, 'perdidas_kw': 20.0,
            'barras': [['B0', 1.0], ['B1', 0.97]], 'elementos': [['L1', 'ElmLne', 50.0]]}
        for f in plan['feeders']})
elif herramienta == 'obras_pf.py' and a.bibliotecas:
    informe.update(alimentadores={f: {'kv': 10.0, 'barras': [], 'tramos': []} for f in plan['feeders']},
                   tipos=[{'nombre': 'AAAC_70', 'clase': 'TypLne', 'origen': 'proyecto', 'proyecto': '',
                           'datos': {'uline': 10.0}, 'resumen': '10 kV'}], avisos=[])
elif herramienta == 'obras_pf.py':
    filas = []
    for i, obra in enumerate(plan['obras'], 1):
        falla = obra.get('barra') == 'NO_EXISTE'
        filas.append({'obra': i, 'clase': obra['clase'], 'alimentador': obra['alimentador'],
                      'variacion': '' if falla else f"Obra_{obra['clase']}_{i}",
                      'error': 'La barra NO_EXISTE no es del alimentador.' if falla else '',
                      'elementos': [], 'tipos': [], 'avisos': []})
    informe.update(modo='simular' if a.simular else 'aplicar', obras=filas)
elif herramienta == 'transferencia_pf.py':
    resultados = [{'caso': c, 'cede': x, 'recibe': y, 'enlace': 'NA_1', 'pasos': [
        {'paso': 1, 'punto': 'N1', 'tipo': 'nodo', 'carga_kw': 100.0, 'viable': True}]}
        for c in plan['casos'] for x, y in (plan['feeders'], plan['feeders'][::-1])]
    informe.update(resultados=resultados, avisos=[])
    if a.fichero:
        Path(a.fichero).write_text('caso;cede\n', encoding='utf-8')
Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
'''


@pytest.fixture()
def guion_falso(tmp_path, monkeypatch):
    """Sustituye los guiones de DIgSILENT por el falso y devuelve la carpeta de los planes."""
    from igea_dgs.web import services

    carpeta = tmp_path / 'guiones'
    carpeta.mkdir()
    for nombre in ('casos_pf.py', 'estudios_pf.py', 'obras_pf.py', 'transferencia_pf.py'):
        (carpeta / f'falso_{nombre}').write_text(GUION_FALSO, encoding='utf-8')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, sys.executable))
    monkeypatch.setattr(services, '_script', lambda nombre: carpeta / f'falso_{nombre}')
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _d: None)
    return carpeta
