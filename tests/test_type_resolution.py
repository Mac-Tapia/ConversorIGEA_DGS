"""Unit tests for catalog type resolution (no TXT fixtures required)."""

from igea_dgs.model import suggest_catalog_code, _resolve_type, LineType


def _lt(code: str, table: str = 'LINE') -> LineType:
    prefix = 'CABLE' if table == 'CONCENTRIC NEUTRAL CABLE' else 'LINE'
    return LineType(f'{prefix}:{code}', code, table, 0.1, 0.1, 0.1, 0.1, 0, 0, 100)


def test_suggest_catalog_code_unique_nearest():
    catalog = ['TYPE02A', 'TYPE03A', 'CU02501D', 'DEFAULT']
    # Numeric closeness breaks TYPE02A vs TYPE03A for TYPE01A.
    assert suggest_catalog_code('TYPE01A', catalog) == 'TYPE02A'
    assert suggest_catalog_code('CU02502D', ['CU02501D', 'TYPE03A', 'DEFAULT']) == 'CU02501D'
    # Symmetric neighbors stay ambiguous.
    assert suggest_catalog_code('N203506D', ['N203505D', 'N203507D', 'DEFAULT']) is None
    assert suggest_catalog_code('N203506D', ['N203505D', 'DEFAULT']) == 'N203505D'
    assert suggest_catalog_code('AA05001D', ['AA05002D', 'AA05003D', 'DEFAULT']) == 'AA05002D'


def test_resolve_uses_explicit_alias_then_auto_then_default():
    by_code = {
        'TYPE03A': [_lt('TYPE03A')],
        'DEFAULT': [_lt('DEFAULT'), _lt('DEFAULT', 'CONCENTRIC NEUTRAL CABLE')],
    }
    typ, alias = _resolve_type('TYPE01A', True, by_code, {'TYPE01A': 'TYPE03A'})
    assert typ is not None and typ.code == 'TYPE03A'
    assert alias == 'TYPE03A'

    typ, alias = _resolve_type('TYPE01A', True, by_code, {})
    assert typ is not None and typ.code == 'TYPE03A'
    assert alias == 'TYPE03A'

    typ, alias = _resolve_type('MISSING99', True, by_code, {})
    assert typ is not None and typ.code == 'DEFAULT'
    assert alias == 'DEFAULT'
