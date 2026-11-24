"""047:RF-92 — las formas corrientes de un precio unitario o por km, leídas por el código del coste.

Con el 047i (2026-11-23), el código daba por malo el coste de propuestas sanas: leía como totales «… dólares la
unidad», «… USD por equipo» y «… USD el kilómetro», y no hallaba la cantidad de un precio «cada uno» cuyo fragmento no
nombra la pieza con la palabra del campo. Sin LLM: valores sintéticos, que no copian los casos del 047i.
"""
from __future__ import annotations

from convertersmartgrid.aplicacion.asistente.contradicciones import comprobar_coste


def _coste(propuesta, *fragmentos):
    c = comprobar_coste(propuesta, {f'e{i}': {'fragmento': f} for i, f in enumerate(fragmentos, 1)})
    assert c, 'el código no calculó el coste'
    return c[0]


def test_047_rf92_la_unidad_y_por_equipo_son_precios_unitarios():
    p = {'accion': 'cambiar 7 aisladores de la estructura X3', 'aisladores': 7, 'coste_usd': 840}
    assert _coste(p, 'Aislador de suspensión, colocado: 120 dólares la unidad.')['coincide']
    p = {'accion': 'montar 2 reguladores en el ramal Z5', 'reguladores': 2, 'coste_usd': 31000}
    assert _coste(p, 'Regulador monofásico con su montaje: 15.500 USD por equipo.')['coincide']
    assert not _coste({**p, 'coste_usd': 15500}, 'Regulador monofásico con su montaje: 15.500 USD por equipo.')['coincide'], \
        'un coste que es solo el precio de un equipo pasó por bueno'


def test_047_rf92_el_kilometro_es_precio_por_km():
    p = {'accion': 'tender 3,5 km de red aérea en el ramal Z9', 'coste_usd': 24500}
    assert _coste(p, 'Red aérea de 22,9 kV sobre postes nuevos: 7.000 USD el kilómetro.')['coincide']
    assert not _coste({**p, 'coste_usd': 7000}, 'Red aérea de 22,9 kV sobre postes nuevos: 7.000 USD el kilómetro.')['coincide']


def test_047_rf92_una_sola_cantidad_de_piezas_ancla_el_precio_unitario():
    p = {'accion': 'instalar 5 registradores en la SET Y2', 'registradores': 5, 'coste_usd': 9000}
    assert _coste(p, 'Analizador de red clase A, instalado: USD 1.800 cada uno.')['coincide']
    dos = {**p, 'tableros': 2}
    assert comprobar_coste(dos, {'e1': {'fragmento': 'Analizador de red clase A, instalado: USD 1.800 cada uno.'}}) == [], \
        'con dos cantidades de piezas el código eligió una al azar'
