"""Spec 107 T21 — resumen ejecutivo del estudio del PIT, con cada cifra tomada del expediente (107:RF-13).

Los expedientes son los sintéticos de ``test_pit_expediente`` (registro, costos y áreas sorteadas), con los perfiles A
(un titular) y B (varios titulares, un año sin demanda y elementos sin parámetros)."""
from __future__ import annotations

import hashlib
import json

import pytest

from datos_pit import perfil_a, perfil_b
from test_pit_expediente import _piezas

from convertersmartgrid.dominio.pit.ambito import PitError
from convertersmartgrid.adaptadores.pit.expediente import emitir
from convertersmartgrid.adaptadores.pit.informe import desde_carpeta


def _emitido(tmp_path, fabrica, seed=27):
    x = _piezas(tmp_path, seed, fabrica)
    salidas = emitir(x['carpeta'], x['registro'], celdas=x['celdas'], diagnostico=x['diag'], comparacion=x['comp'],
                     programa=x['prog'], alternativa_elegida='refuerzo')
    return x, salidas


@pytest.mark.parametrize('fabrica', (perfil_a, perfil_b), ids=('A', 'B'))
def test_resumen_con_sus_tres_apartados_y_las_cifras_del_expediente(tmp_path, fabrica):
    """107:RF-13 — demanda por año, alternativa elegida y programa, cada apartado con el fichero del que sale y su
    huella, y cada cifra igual a la del expediente."""
    x, salidas = _emitido(tmp_path, fabrica)
    resumen = json.loads(salidas['resumen_ejecutivo'].read_text(encoding='utf-8'))
    assert {'demanda', 'alternativa', 'programa'} <= set(resumen)
    carpeta = x['carpeta']
    for apartado, fichero in (('demanda', 'diagnostico.json'), ('alternativa', 'alternativas.json'),
                              ('programa', 'programa.json')):
        assert resumen[apartado]['fuente'] == {
            'fichero': fichero, 'sha256': hashlib.sha256((carpeta / fichero).read_bytes()).hexdigest()}
    diag = json.loads((carpeta / 'diagnostico.json').read_text(encoding='utf-8'))
    assert resumen['demanda']['por_anio'] == [{'anio': a['anio'], 'demanda_mw': a['demanda_mw']} for a in diag['anios']]
    assert resumen['demanda']['sin_demanda'] == diag['sin_demanda']
    alt = next(a for a in json.loads((carpeta / 'alternativas.json').read_text(encoding='utf-8'))['alternativas']
               if a['nombre'] == 'refuerzo')
    assert resumen['alternativa']['inversion'] == alt['inversion'] and alt['inversion']
    assert resumen['alternativa']['valor_presente'] == alt['valor_presente'] and resumen['alternativa']['posicion'] == 1
    prog = json.loads((carpeta / 'programa.json').read_text(encoding='utf-8'))
    assert [f['elemento'] for f in resumen['programa']['filas']] == [f['elemento'] for f in prog['filas']]
    assert sum(resumen['programa']['por_titular'].values()) == len(prog['filas'])
    assert resumen == desde_carpeta(carpeta, 'refuerzo')
    relacion = {r['fichero'] for r in json.loads(salidas['relacion'].read_text(encoding='utf-8'))}
    assert 'resumen_ejecutivo.json' in relacion


def test_resumen_dice_lo_que_el_diagnostico_no_completa(tmp_path):
    """107:RF-13 — el perfil B tiene una línea sin parámetros y un compartido sin asignar: el resumen lo avisa."""
    _, salidas = _emitido(tmp_path, perfil_b)
    resumen = json.loads(salidas['resumen_ejecutivo'].read_text(encoding='utf-8'))
    assert any('no está completo' in a for a in resumen['avisos'])


def test_alternativa_que_no_esta_o_expediente_sin_sus_ficheros(tmp_path):
    """107:RF-13 — una alternativa elegida que no está en la comparación, o un expediente sin el fichero del que sale
    una cifra, es un error que lo nombra; no se emite nada a medias."""
    x = _piezas(tmp_path, 27, perfil_a)
    with pytest.raises(PitError, match='otra'):
        emitir(x['carpeta'], x['registro'], celdas=x['celdas'], diagnostico=x['diag'], comparacion=x['comp'],
               programa=x['prog'], alternativa_elegida='otra')
    assert not (x['carpeta'] / 'cuadros.json').exists()
    with pytest.raises(PitError, match='diagnóstico, la comparación y el programa'):
        emitir(x['carpeta'], x['registro'], celdas=x['celdas'], alternativa_elegida='refuerzo')
    with pytest.raises(PitError, match='diagnostico.json'):
        desde_carpeta(x['carpeta'], 'refuerzo')
    _, salidas = _emitido(tmp_path / 'b', perfil_a)
    with pytest.raises(PitError, match='no está en la comparación'):
        desde_carpeta(salidas['resumen'].parent, 'inexistente')
