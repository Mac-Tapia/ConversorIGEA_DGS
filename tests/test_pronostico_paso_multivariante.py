"""089:RF-119 — un multivariante que no cabe en la GPU espacia sus ventanas antes de quedarse sin medir.

Caso que lo motivó (089 T7, 2026-11-23): iTransformer con las 84 series de la cabecera, contexto y horizonte de 28 días a
15 minutos, pedía 6,69 GiB y quedaban 6,68. Sus series no se parten (046:RF-26); con el doble del paso caben.
"""
from convertersmartgrid.adaptadores import pronostico_demanda as pd_
from convertersmartgrid.adaptadores.pronostico_demanda import PASO_VENTANAS, bytes_ventanas_entrenamiento

#: Hasta siete veces el paso (089:RF-119); se lee del módulo para que falte por aserción, no al importar.
VECES_PASO_MAXIMO = getattr(pd_, 'VECES_PASO_MAXIMO', 7)


def paso_de_ventanas_que_cabe(*a, **k):
    assert hasattr(pd_, 'paso_de_ventanas_que_cabe'), 'un multivariante que no cabe no espacia sus ventanas (RF-119)'
    return pd_.paso_de_ventanas_que_cabe(*a, **k)


GIB = 1024 ** 3


def _pide(paso, series=84, largo=2688 * 4, contexto=2688, horizonte=2688, canales=4):
    return bytes_ventanas_entrenamiento(series, largo, contexto, horizonte, canales, paso)


def test_089_rf119_el_doble_del_paso_cuando_falta_poco():
    disponible = _pide(PASO_VENTANAS) - 10 * 1024 ** 2
    otro = paso_de_ventanas_que_cabe(84, 2688 * 4, 2688, 2688, 4, PASO_VENTANAS, disponible,
                                     tope=PASO_VENTANAS * VECES_PASO_MAXIMO)
    assert otro == 2 * PASO_VENTANAS
    assert _pide(otro) <= disponible < _pide(PASO_VENTANAS)


def test_089_rf119_el_menor_multiplo_que_cabe():
    disponible = _pide(3 * PASO_VENTANAS)
    assert _pide(2 * PASO_VENTANAS) > disponible
    assert paso_de_ventanas_que_cabe(84, 2688 * 4, 2688, 2688, 4, PASO_VENTANAS, disponible,
                                     tope=PASO_VENTANAS * VECES_PASO_MAXIMO) == 3 * PASO_VENTANAS


def test_089_rf119_sin_caber_ni_con_el_tope_no_inventa_un_paso():
    tope = PASO_VENTANAS * VECES_PASO_MAXIMO
    disponible = _pide(tope) - 1
    assert paso_de_ventanas_que_cabe(84, 2688 * 4, 2688, 2688, 4, PASO_VENTANAS, disponible, tope=tope) is None
