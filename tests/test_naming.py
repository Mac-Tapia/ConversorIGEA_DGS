"""Universal NetworkID / selector naming (no company-specific patterns)."""

from convertersmartgrid.dominio.naming import feeder_short_name, feeder_tokens, sort_key_feeder


def test_feeder_short_name_handles_varied_utility_patterns():
    assert feeder_short_name('NET_2030_142_IN191') == 'IN191'
    # 080:RF-28: un número solo no identifica al alimentador; queda el NetworkID entero.
    assert feeder_short_name('ALIMENTADOR-12') == 'ALIMENTADOR-12'
    assert feeder_short_name('Feeder.A1') == 'A1'
    assert feeder_short_name('CIRCUITO/NORTE') == 'NORTE'
    assert feeder_short_name('SIMPLE') == 'SIMPLE'
    assert feeder_tokens('NET_2030_142_IN191') == ['NET', '2030', '142', 'IN191']
    assert sort_key_feeder('NET_Z') == 'z'


def test_sufijo_de_tension_es_uno_para_el_dgs_y_las_obras():
    """011:RF-61 — la copia de un tipo de una obra lleva el mismo sufijo de tensión que
    el conversor pone a los TypLne de una red unida, porque la regla vive en un solo
    sitio: el mismo conductor a 22,9 kV no puede salir con dos nombres."""
    from convertersmartgrid.adaptadores.dgs import _type_name
    from convertersmartgrid.dominio.naming import nombre_con_tension, sufijo_tension

    assert sufijo_tension(22.9) == '22_9kV'
    assert sufijo_tension(10.0) == '10kV'
    assert nombre_con_tension('AA12003D', 22.9) == 'AA12003D_22_9kV'
    # El conversor ya cambiaba también los puntos del código; se conserva para que el
    # DGS siga idéntico byte a byte.
    assert nombre_con_tension('AAAC 35.5', 10.0) == 'AAAC 35_5_10kV'
    assert _type_name('LINE:AA12003D', 'AA12003D', 22.9) == nombre_con_tension('AA12003D', 22.9)
    assert _type_name('LINE:X', 'DEFAULT', 13.2) == 'DEFAULT_OH_13_2kV'
    assert _type_name('CABLE:X', 'DEFAULT') == 'DEFAULT_UG'


def test_siglas_canonicas_del_perfil(monkeypatch):
    """022:RF-90 — con la estructura que declara ``["CHN", "CN"]``, CN191 de la red se llama
    CHN191 desde la carga; las demás siglas y los nombres sin número, tal cual; sin perfil,
    nada cambia."""
    from convertersmartgrid.dominio import naming

    monkeypatch.setattr(naming, 'siglas_canonicas', lambda: {'CN': 'CHN'})
    assert naming.feeder_short_name('NET_2030_1192582_CN191') == 'CHN191'
    assert naming.feeder_short_name('NET_2030_1192601_cn291') == 'CHN291'
    assert naming.feeder_short_name('NET_2030_131_CA191') == 'CA191'
    assert naming.feeder_short_name('ALIMENTADOR-CN') == 'CN'
    monkeypatch.setattr(naming, 'siglas_canonicas', lambda: {})
    assert naming.feeder_short_name('NET_2030_1192582_CN191') == 'CN191'


def test_nombre_canonico_de_los_trozos():
    """022:RF-90 / 027:T23 — cada trozo «sigla + número» con la sigla canónica; lo demás igual."""
    from convertersmartgrid.dominio.naming import nombre_canonico

    canon = {'CN': 'CHN'}
    assert nombre_canonico('NODE_2030_1192582_CN191', canon) == 'NODE_2030_1192582_CHN191'
    assert nombre_canonico('NET_2030_1192598_CN193', canon) == 'NET_2030_1192598_CHN193'
    assert nombre_canonico('CN291', canon) == 'CHN291'
    assert nombre_canonico('SE20859', canon) == 'SE20859'
    assert nombre_canonico('ACN191', canon) == 'ACN191' and nombre_canonico('CHN191', canon) == 'CHN191'
    assert nombre_canonico('NODE_1_CN191', {}) == 'NODE_1_CN191'
