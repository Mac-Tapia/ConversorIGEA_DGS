"""Universal NetworkID / selector naming (no company-specific patterns)."""

from igea_dgs.naming import feeder_short_name, feeder_tokens, sort_key_feeder


def test_feeder_short_name_handles_varied_utility_patterns():
    assert feeder_short_name('NET_2030_142_IN111') == 'IN111'
    assert feeder_short_name('ALIMENTADOR-12') == '12'
    assert feeder_short_name('Feeder.A1') == 'A1'
    assert feeder_short_name('CIRCUITO/NORTE') == 'NORTE'
    assert feeder_short_name('SIMPLE') == 'SIMPLE'
    assert feeder_tokens('NET_2030_142_IN111') == ['NET', '2030', '142', 'IN111']
    assert sort_key_feeder('NET_Z') == 'z'


def test_sufijo_de_tension_es_uno_para_el_dgs_y_las_obras():
    """011:RF-61 — la copia de un tipo de una obra lleva el mismo sufijo de tensión que
    el conversor pone a los TypLne de una red unida, porque la regla vive en un solo
    sitio: el mismo conductor a 22,9 kV no puede salir con dos nombres."""
    from igea_dgs.dgs import _type_name
    from igea_dgs.naming import nombre_con_tension, sufijo_tension

    assert sufijo_tension(22.9) == '22_9kV'
    assert sufijo_tension(10.0) == '10kV'
    assert nombre_con_tension('AA12003D', 22.9) == 'AA12003D_22_9kV'
    # El conversor ya cambiaba también los puntos del código; se conserva para que el
    # DGS siga idéntico byte a byte.
    assert nombre_con_tension('AAAC 35.5', 10.0) == 'AAAC 35_5_10kV'
    assert _type_name('LINE:AA12003D', 'AA12003D', 22.9) == nombre_con_tension('AA12003D', 22.9)
    assert _type_name('LINE:X', 'DEFAULT', 13.2) == 'DEFAULT_OH_13_2kV'
    assert _type_name('CABLE:X', 'DEFAULT') == 'DEFAULT_UG'
