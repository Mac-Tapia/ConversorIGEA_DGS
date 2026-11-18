"""Spec 112: prueba sellada antes de elegir modelo e informe con los resultados negativos (112:RF-7, RF-8, RF-9).

La prueba se sella antes de entrenar o elegir ningún modelo, como ``HUELLA`` en ``asistente/prueba_sellada*.py``: se
escribe con apertura exclusiva, su huella va al manifiesto y abrirla la recalcula. El informe publica todos los
candidatos y todas las cohortes, también los que pierden contra la base o no pasan la puerta: sin filtro previo.
"""
from __future__ import annotations

import importlib.util

import json
from datetime import timedelta

import pytest

from test_benchmarks_cohortes import INICIO, _registros


def _plan(empresas=('E1', 'E2')):
    from convertersmartgrid.aplicacion.benchmarks.cohortes import planificar
    return planificar(_registros(21, empresas), corte=INICIO + timedelta(days=70), horizonte=timedelta(days=14))


def test_la_prueba_se_sella_una_vez(tmp_path):
    """112:RF-7 — se escribe con apertura exclusiva: un segundo sellado no la sobrescribe."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.evaluacion'), 'falta convertersmartgrid.adaptadores.benchmarks.evaluacion'
    from convertersmartgrid.adaptadores.benchmarks.evaluacion import sellar_prueba
    plan = _plan()
    huella = sellar_prueba(plan.cohortes, tmp_path)
    assert len(huella) == 64 and (tmp_path / 'prueba_sellada.json').is_file()
    antes = (tmp_path / 'prueba_sellada.json').read_bytes()
    with pytest.raises(FileExistsError):
        sellar_prueba(plan.cohortes, tmp_path)
    assert (tmp_path / 'prueba_sellada.json').read_bytes() == antes


def test_abrir_la_prueba_comprueba_su_huella(tmp_path):
    """112:RF-7 — la huella no cambia después: si alguien toca la prueba sellada, abrirla la rechaza."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.evaluacion'), 'falta convertersmartgrid.adaptadores.benchmarks.evaluacion'
    from convertersmartgrid.adaptadores.benchmarks.evaluacion import PruebaAlterada, abrir_prueba, sellar_prueba
    plan = _plan()
    huella = sellar_prueba(plan.cohortes, tmp_path)
    prueba = abrir_prueba(tmp_path, huella)
    assert {c['nombre'] for c in prueba['cohortes']} == {c.nombre for c in plan.cohortes}
    ruta = tmp_path / 'prueba_sellada.json'
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    datos['cohortes'][0]['prueba'] = datos['cohortes'][0]['prueba'][1:]      # quitar un registro difícil
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(PruebaAlterada):
        abrir_prueba(tmp_path, huella)


def test_el_informe_publica_tambien_los_negativos(tmp_path):
    """112:RF-8 — un candidato peor que el ingenuo y otro que no pasa la puerta aparecen en el informe, con su motivo."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.evaluacion'), 'falta convertersmartgrid.adaptadores.benchmarks.evaluacion'
    from convertersmartgrid.adaptadores.benchmarks.evaluacion import Resultado, informe
    from convertersmartgrid.adaptadores.evaluacion_harness.publicacion import leer_informe
    plan = _plan()
    resultados = []
    for c in plan.cohortes:
        resultados += [
            Resultado(cohorte=c.nombre, candidato='ingenuo', metricas={'wape': 0.20}, es_base=True),
            Resultado(cohorte=c.nombre, candidato='mejor', metricas={'wape': 0.12}),
            Resultado(cohorte=c.nombre, candidato='peor_que_la_base', metricas={'wape': 0.31}),
            Resultado(cohorte=c.nombre, candidato='sin_puerta', metricas={'wape': 0.15}, puerta=False,
                      motivo='no pasa la puerta de cobertura'),
        ]
    ruta = tmp_path / 'informe.json'
    informe(resultados, ruta, plan=plan, metrica='wape')
    contenido = leer_informe(ruta)
    filas = contenido['resultados']
    assert len(filas) == len(resultados)
    peor = [f for f in filas if f['candidato'] == 'peor_que_la_base']
    assert len(peor) == len(plan.cohortes) and all(not f['gana_a_la_base'] for f in peor)
    assert all('peor que la base' in f['motivo'] for f in peor)
    sin = [f for f in filas if f['candidato'] == 'sin_puerta']
    assert all(f['puerta'] is False and 'puerta' in f['motivo'] for f in sin)
    assert contenido['negativos'] == len(peor) + len(sin)


def test_el_informe_con_una_empresa_lo_dice(tmp_path):
    """112:RF-9 — con datos de una sola empresa, el informe lleva la frase de que la generalización no está demostrada."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.evaluacion'), 'falta convertersmartgrid.adaptadores.benchmarks.evaluacion'
    from convertersmartgrid.aplicacion.benchmarks.cohortes import FRASE_UNA_EMPRESA
    from convertersmartgrid.adaptadores.benchmarks.evaluacion import Resultado, informe
    from convertersmartgrid.adaptadores.evaluacion_harness.publicacion import leer_informe
    plan = _plan(('E1',))
    c = plan.cohortes[0]
    informe([Resultado(cohorte=c.nombre, candidato='ingenuo', metricas={'wape': .2}, es_base=True)],
            tmp_path / 'informe.json', plan=plan, metrica='wape')
    assert FRASE_UNA_EMPRESA in leer_informe(tmp_path / 'informe.json')['avisos']


def test_el_informe_no_acepta_cohortes_que_no_existen(tmp_path):
    """112:RF-8 — un resultado de una cohorte que no está en el plan no se publica como si lo estuviera."""
    assert importlib.util.find_spec('convertersmartgrid.adaptadores.benchmarks.evaluacion'), 'falta convertersmartgrid.adaptadores.benchmarks.evaluacion'
    from convertersmartgrid.adaptadores.benchmarks.evaluacion import Resultado, informe
    with pytest.raises(ValueError, match='cohorte'):
        informe([Resultado(cohorte='inventada', candidato='x', metricas={'wape': .1})],
                tmp_path / 'informe.json', plan=_plan(), metrica='wape')
    assert not (tmp_path / 'informe.json').exists()
