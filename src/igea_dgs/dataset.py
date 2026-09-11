from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import csv


def _split(line: str) -> list[str]:
    return next(csv.reader([line], skipinitialspace=False))


def _row(columns: list[str], line: str) -> dict[str, str]:
    values = [value.strip() for value in _split(line)]
    if len(values) < len(columns):
        values.extend([''] * (len(columns) - len(values)))
    return dict(zip(columns, values[:len(columns)]))


def _parse_simple(path: Path | str) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = defaultdict(list)
    section: str | None = None
    columns: list[str] | None = None
    with Path(path).open('r', encoding='utf-8', errors='replace', newline='') as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                section = line[1:-1].strip().upper()
                columns = None
                continue
            if line.startswith('FORMAT_') and '=' in line:
                columns = [x.strip() for x in _split(line.split('=', 1)[1])]
                continue
            if section is None or columns is None or line.startswith('FEEDER='):
                continue
            tables[section].append(_row(columns, line))
    return dict(tables)


@dataclass(frozen=True)
class CymdistDataset:
    red_path: Path
    loads_path: Path
    equipment_path: Path
    headnodes: dict[str, str]
    nodes: dict[str, dict[str, str]]
    sources: dict[str, dict[str, str]]
    line_configurations: dict[str, dict[str, str]]
    sections: dict[str, dict[str, str]]
    section_owner: dict[str, str]
    feeders: dict[str, tuple[str, ...]]
    switch_settings: tuple[dict[str, str], ...]
    sectionalizer_settings: tuple[dict[str, str], ...]
    intermediate_nodes: tuple[dict[str, str], ...]
    load_placements: dict[tuple[str, str], dict[str, str]]
    customer_loads: dict[tuple[str, str], dict[str, str]]
    equipment_tables: dict[str, tuple[dict[str, str], ...]]

    @classmethod
    def from_files(cls, red: Path | str, loads: Path | str, equipment: Path | str) -> 'CymdistDataset':
        red_path = Path(red)
        loads_path = Path(loads)
        equipment_path = Path(equipment)

        headnodes: dict[str, str] = {}
        nodes: dict[str, dict[str, str]] = {}
        sources: dict[str, dict[str, str]] = {}
        line_configurations: dict[str, dict[str, str]] = {}
        sections: dict[str, dict[str, str]] = {}
        section_owner: dict[str, str] = {}
        feeder_rows: dict[str, list[str]] = defaultdict(list)
        switch_settings: list[dict[str, str]] = []
        sectionalizer_settings: list[dict[str, str]] = []
        intermediate_nodes: list[dict[str, str]] = []

        section: str | None = None
        columns: list[str] | None = None
        active_feeder: str | None = None
        with red_path.open('r', encoding='utf-8', errors='replace', newline='') as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith('[') and line.endswith(']'):
                    section = line[1:-1].strip().upper()
                    columns = None
                    active_feeder = None
                    continue
                if section == 'SECTION' and line.startswith('FEEDER='):
                    values = [x.strip() for x in _split(line.split('=', 1)[1])]
                    active_feeder = values[0]
                    feeder_rows.setdefault(active_feeder, [])
                    columns = None
                    continue
                if line.startswith('FORMAT_') and '=' in line:
                    columns = [x.strip() for x in _split(line.split('=', 1)[1])]
                    continue
                if columns is None:
                    continue
                row = _row(columns, line)
                if section == 'HEADNODES':
                    headnodes[row['NodeID']] = row['NetworkID']
                elif section == 'NODE':
                    nodes[row['NodeID']] = row
                elif section == 'SOURCE':
                    sources[row['NetworkID']] = row
                elif section == 'LINE CONFIGURATION':
                    sid = row['SectionID']
                    if sid in line_configurations:
                        raise ValueError(f'Duplicate LINE CONFIGURATION SectionID: {sid}')
                    line_configurations[sid] = row
                elif section == 'SECTION' and active_feeder:
                    sid = row['SectionID']
                    if sid in sections:
                        raise ValueError(f'Duplicate SECTION SectionID: {sid}')
                    sections[sid] = row
                    section_owner[sid] = active_feeder
                    feeder_rows[active_feeder].append(sid)
                elif section == 'SWITCH SETTING':
                    switch_settings.append(row)
                elif section == 'SECTIONALIZER SETTING':
                    sectionalizer_settings.append(row)
                elif section == 'INTERMEDIATE NODES':
                    intermediate_nodes.append(row)

        load_tables = _parse_simple(loads_path)
        load_placements = {
            (row.get('SectionID', ''), row.get('DeviceNumber', '')): row
            for row in load_tables.get('LOADS', [])
        }
        customer_loads = {
            (row.get('SectionID', ''), row.get('DeviceNumber', '')): row
            for row in load_tables.get('CUSTOMER LOADS', [])
        }
        equipment_tables_raw = _parse_simple(equipment_path)
        equipment_tables = {name: tuple(rows) for name, rows in equipment_tables_raw.items()}

        return cls(
            red_path=red_path,
            loads_path=loads_path,
            equipment_path=equipment_path,
            headnodes=headnodes,
            nodes=nodes,
            sources=sources,
            line_configurations=line_configurations,
            sections=sections,
            section_owner=section_owner,
            feeders={key: tuple(value) for key, value in feeder_rows.items()},
            switch_settings=tuple(switch_settings),
            sectionalizer_settings=tuple(sectionalizer_settings),
            intermediate_nodes=tuple(intermediate_nodes),
            load_placements=load_placements,
            customer_loads=customer_loads,
            equipment_tables=equipment_tables,
        )

    def feeder_ids(self) -> tuple[str, ...]:
        return tuple(self.feeders.keys())

    def feeder_section_ids(self, network_id: str) -> frozenset[str]:
        return frozenset(self.feeders[network_id])

    def resolve_feeder(self, selector: str) -> str:
        from .naming import feeder_short_name, feeder_tokens

        normalized = selector.strip().lower()
        if not normalized:
            raise KeyError('Empty feeder selector')
        direct = {network.lower(): network for network in self.feeders}
        if normalized in direct:
            return direct[normalized]
        # Last-token short name (works for NET_…_IN111, ALIM-12, Feeder.A1, …)
        short_matches = [
            network for network in self.feeders
            if feeder_short_name(network).lower() == normalized
        ]
        if len(short_matches) == 1:
            return short_matches[0]
        if len(short_matches) > 1:
            raise KeyError(f'Ambiguous feeder selector {selector}: {short_matches}')
        # Unique token match anywhere in the NetworkID
        token_matches = [
            network for network in self.feeders
            if normalized in {token.lower() for token in feeder_tokens(network)}
        ]
        if len(token_matches) == 1:
            return token_matches[0]
        if len(token_matches) > 1:
            raise KeyError(f'Ambiguous feeder selector {selector}: {token_matches}')
        raise KeyError(f'Feeder not found: {selector}')
