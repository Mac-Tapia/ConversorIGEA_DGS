"""Fixture discovery helpers (no TXT required)."""

from igea_paths import SKIP_MSG, resolve_igea_txt_paths


def test_resolve_returns_none_or_triplet(monkeypatch, tmp_path):
    monkeypatch.delenv('IGEA_TXT_DIR', raising=False)
    monkeypatch.delenv('IGEA_RED', raising=False)
    monkeypatch.delenv('IGEA_LOADS', raising=False)
    monkeypatch.delenv('IGEA_EQUIPMENT', raising=False)
    assert resolve_igea_txt_paths(roots=[tmp_path]) is None
    assert 'IGEA_TXT_DIR' in SKIP_MSG

    red = tmp_path / 'RED_demo.txt'
    loads = tmp_path / 'CARGA_demo.txt'
    equip = tmp_path / 'BD_Equipo_demo.txt'
    for path in (red, loads, equip):
        path.write_text('x', encoding='utf-8')
    found = resolve_igea_txt_paths(roots=[tmp_path])
    assert found == (red, loads, equip)
