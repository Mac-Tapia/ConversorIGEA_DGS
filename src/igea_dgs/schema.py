from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path


@dataclass(frozen=True)
class DgsSchema:
    profile: str
    dgs_export_compatibility: str
    powerfactory_major_compatibility: int
    general_version: str
    tables: dict[str, str]
    table_order: tuple[str, ...]
    source_path: str

    def header(self, table: str) -> str:
        try:
            return self.tables[table]
        except KeyError as exc:
            raise KeyError(f'DGS table not defined in profile {self.profile}: {table}') from exc

    def fields(self, table: str) -> list[str]:
        header = self.header(table)
        return [part.split('(')[0].replace(':MATRIX', '') for part in header[2:].split(';')[1:]]


def load_schema(profile: str = 'pf21_dgs_1_8_4') -> DgsSchema:
    resource = files('igea_dgs').joinpath('schemas', f'{profile}.json')
    if not resource.is_file():
        raise KeyError(f'Unknown DGS schema profile: {profile}')
    with resource.open('r', encoding='utf-8') as fh:
        data = json.load(fh)
    return DgsSchema(
        profile=data['profile'],
        dgs_export_compatibility=data['dgs_export_compatibility'],
        powerfactory_major_compatibility=int(data['powerfactory_major_compatibility']),
        general_version=str(data['general_version']),
        tables=dict(data['tables']),
        table_order=tuple(data.get('table_order', data['tables'].keys())),
        source_path=str(Path(str(resource))),
    )
