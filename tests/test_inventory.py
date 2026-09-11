"""Inventory analysis tests (uses referencia TXT when available)."""

from __future__ import annotations

from igea_dgs.inventory import build_dataset_inventory, format_inventory_report, write_inventory


def test_inventory_on_referencia_dataset(ds):
    inv = build_dataset_inventory(ds)
    assert inv['format'] == 'igea-dgs-dataset-inventory-v1'
    totals = inv['totals']
    assert totals['feeders'] == len(ds.feeder_ids())
    assert totals['sections'] == len(ds.sections)
    assert totals['customer_loads'] == len(ds.customer_loads)
    assert totals['convertible_feeders'] + totals['stub_feeders'] == totals['feeders']
    assert inv['conversion']['expected_dgs_files'] == totals['convertible_feeders']
    assert len(inv['feeders']) == totals['feeders']
    # Referencia ElectroDunas lote: 96 feeders, 3 stubs, 38657 sections
    if totals['feeders'] == 96:
        assert totals['convertible_feeders'] == 93
        assert totals['stub_feeders'] == 3
        assert totals['sections'] == 38657
        assert set(inv['conversion']['skipped_stub_feeders']) == {'CA103', 'PI101', 'PN208'}
    report = format_inventory_report(inv)
    assert 'INVENTARIO TXT' in report
    assert str(totals['feeders']) in report


def test_write_inventory_json(ds, tmp_path):
    inv = build_dataset_inventory(ds)
    path = write_inventory(inv, tmp_path / 'dataset_inventory.json')
    assert path.is_file()
    text = path.read_text(encoding='utf-8')
    assert '"igea-dgs-dataset-inventory-v1"' in text
    assert '"expected_dgs_files"' in text
