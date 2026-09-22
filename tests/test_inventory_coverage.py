from dataclasses import replace

import pytest

from igea_dgs.dataset import CymdistDataset
from igea_dgs.inventory import build_dataset_inventory
from igea_dgs.quality.inventory import build_strict_inventory


@pytest.fixture
def mini_dataset(tmp_path):
    red = tmp_path / "RED.txt"
    loads = tmp_path / "CARGA.txt"
    equipment = tmp_path / "BD_Equipo.txt"
    red.write_text(
        "[NODE]\nFORMAT_NODE=NodeID,CoordX,CoordY\nN1,0,0\n"
        "[SOURCE]\nFORMAT_SOURCE=NetworkID,NodeID,DesiredVoltage\nNET_A,N1,13.2\n"
        "[SECTION]\nFEEDER=NET_A\nFORMAT_SECTION=SectionID,FromNodeID,ToNodeID,Phase\n"
        "S1,N1,N1,ABC\n[LINE CONFIGURATION]\n"
        "FORMAT_LINE CONFIGURATION=SectionID,LineCableID,Length,Overhead\nS1,L1,1,1\n",
        encoding="utf-8",
    )
    loads.write_text(
        "[LOADS]\nFORMAT_LOADS=SectionID,DeviceNumber\n"
        "[CUSTOMER LOADS]\nFORMAT_CUSTOMERLOADS=SectionID,DeviceNumber\n",
        encoding="utf-8",
    )
    equipment.write_text(
        "[LINE]\nFORMAT_LINE=ID,R1,R0,X1,X0,B1,B0,Amps\n"
        "L1,0.1,0.2,0.3,0.4,0,0,100\n",
        encoding="utf-8",
    )
    return CymdistDataset.from_files(red, loads, equipment)


def test_unknown_populated_section_blocks_conversion(mini_dataset):
    sections = dict(mini_dataset.parsed_sections)
    sections["equipment"] = sections["equipment"] + ("UNKNOWN EQUIPMENT",)
    dataset = replace(mini_dataset, parsed_sections=sections)

    inventory = build_strict_inventory(dataset)

    assert inventory.gate.blocked
    assert inventory.coverage["UNKNOWN EQUIPMENT"].status == "unsupported"
    assert any(item.code == "UNSUPPORTED_SECTION" for item in inventory.gate.diagnostics)


def test_known_sections_report_full_coverage(mini_dataset):
    inventory = build_strict_inventory(mini_dataset)

    assert inventory.coverage_percent == 100.0
    assert not inventory.gate.blocked
    legacy_report = build_dataset_inventory(mini_dataset)
    assert legacy_report["strict_coverage"]["percent"] == 100.0
    assert legacy_report["strict_coverage"]["blocked"] is False


def test_validate_input_returns_two_for_unknown_section(mini_dataset, capsys):
    from igea_dgs.cli import main

    with mini_dataset.red_path.open("a", encoding="utf-8") as stream:
        stream.write("[UNKNOWN EQUIPMENT]\nFORMAT_UNKNOWN=ID\nX1\n")

    result = main(
        [
            "validate-input",
            "--red",
            str(mini_dataset.red_path),
            "--loads",
            str(mini_dataset.loads_path),
            "--equipment",
            str(mini_dataset.equipment_path),
        ]
    )

    assert result == 2
    assert "UNSUPPORTED_SECTION" in capsys.readouterr().out
