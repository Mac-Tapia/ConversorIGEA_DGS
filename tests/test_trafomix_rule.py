from types import SimpleNamespace

from igea_dgs.rules.trafomix import apply_trafomix_rule


def _dataset(*placements):
    load_placements = {
        (row["SectionID"], row["DeviceNumber"]): row for row in placements
    }
    customer_loads = {
        key: {"SectionID": key[0], "DeviceNumber": key[1]}
        for key in load_placements
    }
    return SimpleNamespace(load_placements=load_placements, customer_loads=customer_loads)


def test_trafomix_and_its_load_are_excluded_but_sed_load_remains():
    dataset = _dataset(
        {"SectionID": "SEC1", "DeviceNumber": "TRAFOMIX-01", "EquipmentType": "TRAFOMIX"},
        {"SectionID": "SEC1", "DeviceNumber": "LOAD-TM-01", "ParentDevice": "TRAFOMIX-01"},
        {"SectionID": "SEC1", "DeviceNumber": "LOAD-SED-01", "EquipmentType": "SED_LOAD"},
    )

    result = apply_trafomix_rule(dataset)

    assert result.excluded_keys == {("SEC1", "TRAFOMIX-01"), ("SEC1", "LOAD-TM-01")}
    assert ("SEC1", "LOAD-SED-01") in result.retained_load_keys
    assert not result.gate.blocked


def test_ambiguous_trafomix_relation_blocks():
    dataset = _dataset(
        {"SectionID": "SEC1", "DeviceNumber": "TRAFOMIX-01", "EquipmentType": "TRAFOMIX"},
        {"SectionID": "SEC1", "DeviceNumber": "LOAD-TM-01", "ParentDevice": "TRAFOMIX-01"},
        {"SectionID": "SEC1", "DeviceNumber": "LOAD-TM-02", "ParentDevice": "TRAFOMIX-01"},
    )

    result = apply_trafomix_rule(dataset)

    assert result.gate.blocked
    assert "TRAFOMIX_AMBIGUOUS_RELATION" in {item.code for item in result.gate.diagnostics}
