"""043:RF-16 (T10): el harness acota cada llamada al proveedor y la campaña (auditoría del 18-11, H09).

Solo contratos en CPU con dobles: un proveedor que no vuelve no deja la evaluación sin estado final ni abre la
promoción, y ningún caso programado sale del denominador. La evaluación runtime real sigue en 043 T9.
"""
from __future__ import annotations

import inspect
import math
import threading
import time

import pytest
from test_harness_ejecucion import evaluadores, preparar, proveedor

from convertersmartgrid.aplicacion.evaluacion_harness import ejecucion
from convertersmartgrid.aplicacion.evaluacion_harness.ejecucion import (
    ejecutar,
    validar_integridad,
    validar_promocion,
)


def _con_presupuesto():
    params = inspect.signature(ejecutar).parameters
    assert 'plazo_caso_s' in params and 'presupuesto_s' in params, 'ejecutar no acepta plazo ni presupuesto'


def _programados(cfg) -> int:
    return sum(1 for s in cfg['suites'] for c in s['casos'] if c['particion'] == 'prueba') * len(cfg['modelos'])


def test_proveedor_bloqueado_no_da_promocion():
    _con_presupuesto()
    cfg = preparar()
    soltar, llamadas = threading.Event(), []

    def atascado(modelo, suite, entrada):
        llamadas.append(suite['id'])
        if len(llamadas) == 2:
            soltar.wait(10)          # no vuelve dentro del plazo
        return proveedor(modelo, suite, entrada)

    inicio = time.monotonic()
    try:
        informe = ejecutar(cfg, atascado, modo='runtime', evaluadores=evaluadores(cfg), plazo_caso_s=0.3)
    finally:
        soltar.set()
    assert time.monotonic() - inicio < 5, 'la campaña no espera al proveedor atascado'
    assert len(llamadas) == 2, 'al proveedor atascado no se le piden más casos'
    filas = informe['casos']
    assert len(filas) == informe['programados'] == _programados(cfg)
    assert filas[1]['estado'] == 'error' and 'plazo' in filas[1]['error']
    assert all(f['estado'] == 'cancelado' for f in filas[2:])
    assert informe['estado'] in ('CANCELADA', 'INCOMPLETA')
    assert informe['promocion_permitida'] is False and informe['modelo_promovido'] is False
    assert informe['proveedor_sin_respuesta'] == [
        {'suite_id': filas[1]['suite_id'], 'record_id': filas[1]['record_id'], 'rol': filas[1]['rol']}]
    validar_integridad(informe)
    with pytest.raises(ValueError):
        validar_promocion(informe, cfg)


def test_cancelacion_conserva_todos_los_casos_programados():
    _con_presupuesto()
    cfg = preparar()
    pedida = threading.Event()

    def lento(modelo, suite, entrada):
        threading.Timer(0.1, pedida.set).start()
        time.sleep(2)                # la cancelación llega a mitad de la llamada
        return proveedor(modelo, suite, entrada)

    inicio = time.monotonic()
    informe = ejecutar(cfg, lento, modo='runtime', evaluadores=evaluadores(cfg), cancelar=pedida.is_set,
                       plazo_caso_s=30)
    assert time.monotonic() - inicio < 1.5, 'la cancelación se atiende durante la llamada'
    filas = informe['casos']
    assert len(filas) == informe['programados'] == _programados(cfg)
    assert [f['estado'] for f in filas] == ['cancelado'] * len(filas)
    assert 'durante la llamada' in filas[0]['error']
    assert informe['estado'] == 'CANCELADA' and informe['promocion_permitida'] is False
    assert informe['proveedor_sin_respuesta'][0]['record_id'] == filas[0]['record_id']
    validar_integridad(informe)


def test_presupuesto_agotado_cancela_lo_que_falta():
    _con_presupuesto()
    cfg = preparar()

    def medio(modelo, suite, entrada):
        time.sleep(0.15)
        return proveedor(modelo, suite, entrada)

    informe = ejecutar(cfg, medio, modo='runtime', evaluadores=evaluadores(cfg), presupuesto_s=0.2)
    estados = [f['estado'] for f in informe['casos']]
    assert len(estados) == _programados(cfg)
    assert 'ok' in estados and estados[-1] == 'cancelado'
    assert all('presupuesto' in f['error'] for f in informe['casos'] if f['estado'] == 'cancelado')
    assert informe['estado'] == 'CANCELADA' and informe['promocion_permitida'] is False
    en_vuelo = [f for f in informe['casos'] if 'durante la llamada' in f.get('error', '')]
    assert [{'suite_id': f['suite_id'], 'record_id': f['record_id'], 'rol': f['rol']} for f in en_vuelo] ==         informe['proveedor_sin_respuesta'], 'el caso cortado a mitad se dice como posible cálculo en marcha'
    validar_integridad(informe)


def test_sin_topes_el_contrato_no_cambia():
    _con_presupuesto()
    cfg = preparar()
    informe = ejecutar(cfg, proveedor, modo='contract', evaluadores=evaluadores(cfg))
    assert informe['completados'] == _programados(cfg) and informe['proveedor_sin_respuesta'] == []
    validar_integridad(informe)


@pytest.mark.parametrize('valor', ['', 'nada', '0', '-5', 'nan', 'inf'])
def test_topes_no_validos_dejan_los_de_por_defecto(monkeypatch, valor):
    from convertersmartgrid.adaptadores.evaluacion_harness import integracion

    leer = getattr(ejecucion, 'segundos_de_entorno', None)
    assert callable(leer), 'los topes del harness se leen del entorno'
    assert (getattr(integracion, 'PLAZO_CASO_S', None), getattr(integracion, 'PRESUPUESTO_S', None)) == (900, 14400)
    monkeypatch.setenv('CSG_HARNESS_PLAZO_CASO_S', valor)
    assert leer('CSG_HARNESS_PLAZO_CASO_S', 900) == 900
    monkeypatch.setenv('CSG_HARNESS_PLAZO_CASO_S', '12.5')
    assert math.isclose(leer('CSG_HARNESS_PLAZO_CASO_S', 900), 12.5)


def test_la_etapa_del_coordinador_pasa_los_topes():
    from convertersmartgrid.adaptadores.evaluacion_harness import integracion

    fuente = inspect.getsource(integracion.crear_etapa)
    assert 'plazo_caso_s=' in fuente and 'presupuesto_s=' in fuente, 'la etapa runtime llama sin tope'
