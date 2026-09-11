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
