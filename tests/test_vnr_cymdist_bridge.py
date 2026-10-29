"""Pruebas del motor base de conversión.

Spec 034: 034:RF-4, 034:RF-12.
"""
from pathlib import Path


def test_vnr_bridge_preserves_capacitor_source_fields():
    from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
    from vnr_etl.models import Capacitor, CanonicalModel, ConductorType, Load, Node, Section, Source

    model = CanonicalModel(
        metadata={'working_crs_is_projected': True},
        nodes=[Node('N1', 0, 0), Node('N2', 100, 0)],
        sections=[Section('S1', 'N1', 'N2', conductor_code='AA', phases='ABC',
                          length_m=100, feeder_id='CA101')],
        sources=[Source('SRC', 'N1', nominal_kv=10, feeder_id='CA101')],
        loads=[Load('L1', 'N2', kw=10, kvar=2, phases='ABC', feeder_id='CA101')],
        conductor_types=[ConductorType('AA', r1_ohm_km=.2, x1_ohm_km=.3,
                                       r0_ohm_km=.4, x0_ohm_km=.5, ampacity_a=200)],
        capacitors=[Capacitor('BC1', 'N2', kvar=450, feeder_id='CA101',
                              phases='ABC', steps=3, nominal_kv=10, status='in_service')],
    )

    result = canonical_to_cymdist(model, source_path=Path('fuente.gpkg'))
    row = result.dataset.capacitor_settings[0]

    assert row['DeviceNumber'] == 'BC1'
    assert row['NetworkID'] == 'CA101'
    assert row['NodeID'] == 'N2'
    assert row['TotalKVAR'] == '450'
    assert row['NumberOfSteps'] == '3'
    assert row['Phase'] == 'ABC'


def test_vnr_bridge_retains_capacitor_without_capacity_for_audit():
    from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
    from vnr_etl.models import Capacitor, CanonicalModel

    result = canonical_to_cymdist(
        CanonicalModel(capacitors=[Capacitor('BC_SIN_Q', 'N0', kvar=0)]),
        source_path=Path('fuente.json'),
    )

    assert len(result.dataset.capacitor_settings) == 1
    assert result.dataset.capacitor_settings[0]['TotalKVAR'] == ''
