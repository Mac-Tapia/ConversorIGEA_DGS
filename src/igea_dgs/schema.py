"""Perfiles de esquema DGS versionados: tablas y campos que se escriben.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
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

    def con_puntos_por_conector(self, n: int) -> 'DgsSchema':
        """El mismo perfil con ``IntGrfcon`` declarando ``n`` puntos ``rX``/``rY``.

        El perfil trae 4 columnas, como la referencia NA205, y el escritor recortaba cada
        conector a 4 puntos: en IN111 + TA225 (2026-10-14) la grid dibujaba hasta 7
        vértices por línea donde el mapa geográfico, con el GPS completo, tenía 74, y las
        curvas se separaban hasta 257 m. La cabecera crece con el conector más largo.
        """
        n = max(4, int(n))
        cabecera = self.tables.get('IntGrfcon')
        if cabecera is None or n == 4:
            return self
        partes = []
        for parte in cabecera.split(';'):
            campo = parte.split('(')[0]
            if campo in ('rX:SIZEROW', 'rY:SIZEROW'):
                eje = campo[:2]
                partes.append(parte)
                partes.extend(f'{eje}:{i}(r)' for i in range(n))
            elif not (campo.startswith(('rX:', 'rY:'))):
                partes.append(parte)
        return replace(self, tables={**self.tables, 'IntGrfcon': ';'.join(partes)})

    def con_zonas(self) -> 'DgsSchema':
        """El mismo perfil con ``cpZone`` en ``ElmTerm``: la zona de cada barra (022:RF-15).

        Solo en un DGS con zonas: en los demás la cabecera queda como estaba y el DGS es el
        mismo byte a byte que antes de la spec 022 (RF-6, línea base de la 001).
        """
        cabecera = self.tables.get('ElmTerm', '')
        if 'cpZone' in cabecera:
            return self
        return replace(self, tables={**self.tables, 'ElmTerm': cabecera + ';cpZone(p)'})

    def header(self, table: str) -> str:
        try:
            return self.tables[table]
        except KeyError as exc:
            raise KeyError(f'DGS table not defined in profile {self.profile}: {table}') from exc

    def fields(self, table: str) -> list[str]:
        # Se llama una vez por fila escrita: cientos de miles en un lote grande.
        return list(_fields_of(self.header(table)))


@lru_cache(maxsize=None)
def _fields_of(header: str) -> tuple[str, ...]:
    return tuple(part.split('(')[0].replace(':MATRIX', '') for part in header[2:].split(';')[1:])


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
