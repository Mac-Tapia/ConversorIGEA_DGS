from pathlib import Path


def test_production_source_has_no_fixed_reference_dgs_dependency():
    root = Path(__file__).resolve().parents[1] / 'src' / 'igea_dgs'
    forbidden = ('na205.dgs', 'reference_dgs', 'reference-dgs', '/mnt/data/na205')
    text = '\n'.join(p.read_text(encoding='utf-8', errors='replace').lower() for p in root.rglob('*') if p.is_file() and p.suffix in {'.py','.json'})
    for token in forbidden:
        assert token not in text


def test_schema_profile_defines_30_versioned_dgs_tables():
    from igea_dgs.schema import load_schema
    schema = load_schema()
    assert len(schema.tables) == 30
    assert len(schema.table_order) == 30
