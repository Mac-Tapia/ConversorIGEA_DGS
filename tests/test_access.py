"""Pruebas del motor base de conversión.

Spec 034: 034:RF-3, 034:RF-12.
"""
def test_access_capacitor_rows_keep_database_values():
    from igea_dgs.access import capacitor_rows_from_access

    rows = [
        ('BC1', 'CA101', 'N2', 7, 150, 3, 450, 10, 1),
        ('BC2', 'CA101', 'N3', 1, None, None, None, 10, 0),
    ]

    mapped = capacitor_rows_from_access(rows, wanted={'CA101'})

    assert mapped[0] == {
        'DeviceNumber': 'BC1', 'NetworkID': 'CA101', 'NodeID': 'N2',
        'Phase': 'ABC', 'KVARPerStep': '150', 'NumberOfSteps': '3',
        'TotalKVAR': '450', 'NominalKV': '10', 'Status': '1',
        'SourceTable': 'CYMSHUNTCAPACITOR',
    }
    assert mapped[1]['KVARPerStep'] == ''
    assert mapped[1]['TotalKVAR'] == ''
