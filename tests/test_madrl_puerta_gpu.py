"""Spec 074 T8 con la política real: entrenar en cpu con una iteración, guardar y aplicar la puerta en una red no vista.

Usa torch y torch_geometric, así que lleva la marca de la GPU (106:RF-6) aunque corra en cpu: comprueba el montaje, no es
una medida del piloto. Las redes son sintéticas, con nombres inventados.
"""
from __future__ import annotations

import json

import pytest
from apoyo import cargar_herramienta
from test_madrl_puerta import _sistema

from convertersmartgrid.adaptadores.madrl_puerta import PREFIJO_PRUEBA, SEPARACION


def test_entrenar_guardar_y_aplicar_en_no_vistos(tmp_path, capsys):
    """074:RF-6 / 074:RF-13 / 074:RF-14 — entrenar y guardar, sellar, medir y decidir con los pesos reales."""
    pytest.importorskip('torch')
    pytest.importorskip('torch_geometric')
    entrenar = cargar_herramienta('madrl_entrenar.py', tools_en_path=True)
    puerta = cargar_herramienta('madrl_puerta.py', tools_en_path=True)
    vista, nueva = tmp_path / 'entreno.json', tmp_path / 'nueva.json'
    vista.write_text(json.dumps(_sistema(('ALIM_A', 'ALIM_B'))), encoding='utf-8')
    nueva.write_text(json.dumps(_sistema(('ALIM_C',), carga=0.35)), encoding='utf-8')
    modelo = tmp_path / 'modelo'
    comunes = ['--tension-min', '0.95', '--tension-max', '1.05', '--carga-max', '100', '--banco-mvar', '0.3',
               '--costo-banco', '10', '--candidatos', '3', '--dispositivo', 'cpu']
    assert entrenar.main(['--grafo', str(vista), *comunes, '--politica', 'gatv2', '--iteraciones', '1',
                          '--modelo-salida', str(modelo)]) == 0
    manifiesto = json.loads((modelo / 'modelo.json').read_text(encoding='utf-8'))
    assert manifiesto['entrenamiento'][0]['nombre'] == 'entreno.json' and manifiesto['parametros']['candidatos'] == 3

    base = ['aplicar', '--modelo', str(modelo), '--dispositivo', 'cpu', '--generaciones', '3', '--poblacion', '8']
    salida = tmp_path / 'puerta'
    rc = puerta.main([*base, '--no-vistos', str(nueva), '--salida', str(salida), '--espacio', 'ws1',
                      '--proyecto', f'{PREFIJO_PRUEBA}074_C'])
    informe = json.loads((salida / 'informe.json').read_text(encoding='utf-8'))
    sep = json.loads((salida / SEPARACION).read_text(encoding='utf-8'))
    assert informe['sello_separacion'] == sep['sello'] and informe['medidas'][0]['nombre'] == 'nueva.json'
    assert informe['medidas'][0]['aprendido']['control'] == 'gatv2'
    if informe['decision'] == 'pasa':
        assert rc == 0 and json.loads((salida / 'orden_confirmacion.json').read_text(encoding='utf-8'))[
            'proyecto'] == f'{PREFIJO_PRUEBA}074_C'
    else:
        assert rc == 3 and json.loads((salida / 'ARCHIVADO.json').read_text(encoding='utf-8'))['integrado_en_flujo'] is False
    assert f"Decisión: {informe['decision']}" in capsys.readouterr().out
