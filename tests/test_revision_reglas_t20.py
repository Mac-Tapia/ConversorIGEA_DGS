"""047:RF-94 — una negación con un participio de permiso, leída por el código como prohibición.

Con el 047k (2026-11-24), «ninguna cuadrilla está autorizada a maniobrar con carga los seccionadores unipolares» no se
leía como prohibición y en el modo equipo el caso quedó sin respuesta. Sin LLM: valores sintéticos, que no copian el caso.
"""
from __future__ import annotations

import pytest

from convertersmartgrid.aplicacion.asistente import contradicciones as C


def _prohibe(accion, fragmento):
    comprobar = getattr(C, 'comprobar_prohibiciones', None)
    assert comprobar is not None, 'el código no comprueba las prohibiciones de la evidencia'
    return comprobar({'accion': accion, 'coste_usd': 0}, {'e1': {'fragmento': fragmento}})


@pytest.mark.parametrize('fragmento', [
    'Ningún operario está habilitado a desconectar puentes con la línea en servicio.',
    'Nadie se encuentra facultado para desconectar puentes con la línea en servicio.',
    'Ninguna contratista queda autorizada a desconectar puentes en la red energizada.',
    'El personal de turno no está acreditado para desconectar puentes de media tensión.',
    'Los técnicos nuevos no son autorizados a desconectar puentes solos.',
])
def test_047_rf94_negacion_con_participio_de_permiso(fragmento):
    c = _prohibe('desconectar los puentes del vano V8 con la línea en servicio', fragmento)
    assert c and not c[0]['coincide'], f'no se leyó como prohibición: {fragmento}'


@pytest.mark.parametrize('fragmento', [
    'Ningún vano tiene conductores dañados; el operario está habilitado y lleva su equipo.',
    'La cuadrilla está autorizada a desconectar puentes con la orden del despacho.',
])
def test_047_rf94_un_permiso_o_una_negacion_sueltos_no_prohiben(fragmento):
    assert _prohibe('desconectar los puentes del vano V8 con la orden del despacho', fragmento) == [], fragmento


def test_047_rf95_precio_por_la_pieza_que_la_accion_cuenta():
    """047:RF-95 — «… por banco» con «instalar 2 bancos…» es por unidad: 2 × 8 800, no un total de 8 800."""
    from convertersmartgrid.aplicacion.asistente import contradicciones as C
    propuesta = {'accion': 'instalar 3 reconectadores en el ramal R9', 'coste_usd': 27600}
    sano = C.comprobar_coste(propuesta, {'e1': {'fragmento': 'Reconectador de 27 kV montado: USD 9 200 por reconectador.'}})
    assert sano and sano[0]['coincide'], sano
    caro = C.comprobar_coste({**propuesta, 'coste_usd': 9200},
                             {'e1': {'fragmento': 'Reconectador de 27 kV montado: USD 9 200 cada reconectador.'}})
    assert caro and not caro[0]['coincide'], caro
    otra = C.comprobar_coste({**propuesta, 'coste_usd': 9200},
                             {'e1': {'fragmento': 'Obra civil del ramal R9: USD 9 200 por la zanja completa.'}})
    assert otra and otra[0]['coincide'], 'una pieza que la acción no cuenta no hace el precio unitario'
