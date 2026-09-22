"""Contratos explicitos de las tablas TXT IGEA admitidas."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TableContract:
    name: str
    key_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileContract:
    name: str
    tables: tuple[TableContract, ...]

    def table(self, name: str) -> TableContract | None:
        normalized = name.strip().upper()
        return next((item for item in self.tables if item.name == normalized), None)


RED_CONTRACT = FileContract(
    "RED",
    (
        TableContract("HEADNODES", ("NodeID",)),
        TableContract("NODE", ("NodeID",)),
        TableContract("SOURCE", ("NetworkID",)),
        TableContract("SECTION", ("SectionID",)),
        TableContract("LINE CONFIGURATION", ("SectionID",)),
        TableContract("SWITCH SETTING", ("SectionID", "DeviceNumber")),
        TableContract("SECTIONALIZER SETTING", ("SectionID", "DeviceNumber")),
        TableContract("INTERMEDIATE NODES", ("SectionID", "SeqNumber")),
    ),
)

LOADS_CONTRACT = FileContract(
    "CARGAS",
    (
        TableContract("LOADS", ("SectionID", "DeviceNumber")),
        TableContract("CUSTOMER LOADS", ("SectionID", "DeviceNumber")),
    ),
)
