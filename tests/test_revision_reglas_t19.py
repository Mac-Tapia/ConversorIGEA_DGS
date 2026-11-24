"""047:RF-93 — otras formas corrientes de prohibir, y lo prohibido «sin» algo, leídas por el código.

Con el 047j (2026-11-23), «las reglas de seguridad no permiten trabajar … sin puesta a tierra temporal» no se leía como
prohibición y en los dos modos se aprobó la acción que lo hacía. Sin LLM: valores sintéticos, que no copian el caso.
"""
from __future__ import annotations

import pytest

from convertersmartgrid.aplicacion.asistente import contradicciones as C


def _prohibe(accion, fragmento):
    comprobar = getattr(C, 'comprobar_prohibiciones', None)
    assert comprobar is not None, 'el código no comprueba las prohibiciones de la evidencia'
    return comprobar({'accion': accion, 'coste_usd': 0}, {'e1': {'fragmento': fragmento}})


@pytest.mark.parametrize('fragmento', [
    'El reglamento interno no autoriza podar árboles junto a la red energizada.',
    'Las normas de la empresa no permiten podar cerca de conductores con tensión.',
    'El procedimiento no admite podar con la línea en servicio.',
    'Queda prohibido podar en la franja de servidumbre durante la lluvia.',
    'En ningún caso se debe podar con la red energizada.',
    'Jamás podar sin el permiso de trabajo firmado.',
])
def test_047_rf93_formas_corrientes_de_prohibir(fragmento):
    c = _prohibe('podar sin el permiso de trabajo los árboles del vano V3', fragmento)
    assert c and not c[0]['coincide'], f'no se leyó como prohibición: {fragmento}'


def test_047_rf93_lo_prohibido_sin_algo_no_prohibe_hacerlo_con_ello():
    regla = 'Las reglas de seguridad no permiten podar sin corte de energía en el vano.'
    assert _prohibe('podar sin corte de energía los árboles del vano V3', regla), 'la acción hace lo prohibido'
    assert _prohibe('podar con corte de energía los árboles del vano V3', regla) == [], \
        'hacerlo con lo que la regla exige no está prohibido'
