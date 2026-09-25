from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import csv


#: Tablas del BD_Equipo que definen tipos de línea, por familia. Están aquí y no en
#: model.py porque las consultan también el inventario, el completado de catálogo y la
#: auditoría de estudios, y cuando cada una llevaba su propia lista se desincronizaron:
#: el catálogo del export completo trae los cables en [CABLE], no en [CONCENTRIC NEUTRAL
#: CABLE], y los 8.729 tramos subterráneos caían a DEFAULT sin que nada lo dijera.
TABLAS_TIPOS_AEREO: tuple[str, ...] = ('LINE',)
TABLAS_TIPOS_SUBTERRANEO: tuple[str, ...] = ('CONCENTRIC NEUTRAL CABLE', 'CABLE')
TABLAS_TIPOS_LINEA: tuple[str, ...] = TABLAS_TIPOS_AEREO + TABLAS_TIPOS_SUBTERRANEO


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

        # Cada fichero se comprueba por su CONTENIDO, no por su nombre. Los TXT que
        # entrega la distribuidora no siguen ninguna convención —el nombre lo pone
        # quien exporta y cambia de una entrega a otra—, así que el nombre no protege
        # de nada. Sin esto, poner el catálogo de equipos en la casilla de cargas
        # producía un dataset con 0 cargas y la conversión seguía adelante: un DGS que
        # converge, se importa y da un flujo perfecto de una red que no alimenta a
        # nadie. La peor clase de error es el que no falla.
        from .identify import CARGA, EQUIPOS, RED, comprobar_ranura

        problemas = [
            m for m in (
                comprobar_ranura(red_path, RED),
                comprobar_ranura(loads_path, CARGA),
                comprobar_ranura(equipment_path, EQUIPOS),
            ) if m
        ]
        if problemas:
            raise ValueError(
                'Los ficheros de entrada no corresponden con su casilla:\n\n'
                + '\n\n'.join(problemas)
            )

        headnodes: dict[str, str] = {}
        nodes: dict[str, dict[str, str]] = {}
        sources: dict[str, dict[str, str]] = {}
        line_configurations: dict[str, dict[str, str]] = {}
        #: Lo leído de [OVERHEADLINE SETTING] / [UNDERGROUNDLINE SETTING], aparte para
        #: que una tabla [LINE CONFIGURATION] explícita siga mandando si vienen ambas.
        line_settings: dict[str, dict[str, str]] = {}
        sections: dict[str, dict[str, str]] = {}
        section_owner: dict[str, str] = {}
        feeder_rows: dict[str, list[str]] = defaultdict(list)
        switch_settings: list[dict[str, str]] = []
        sectionalizer_settings: list[dict[str, str]] = []
        intermediate_nodes: list[dict[str, str]] = []

        section: str | None = None
        columns: list[str] | None = None
        # El FORMAT de cada tabla se recuerda por tabla. Hace falta porque los dos
        # exports de CYMDIST que se han visto lo colocan al revés: uno declara
        # FORMAT_SECTION *antes* del primer FEEDER= y no lo repite; el otro lo declara
        # después de cada FEEDER=. Con una sola variable, el primero perdía las columnas
        # al llegar el FEEDER= y descartaba en silencio los 38.753 tramos, dejando
        # alimentadores vacíos sin un solo error.
        columns_by_section: dict[str, list[str]] = {}
        active_feeder: str | None = None
        with red_path.open('r', encoding='utf-8', errors='replace', newline='') as fh:
            for lineno, raw in enumerate(fh, start=1):
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
                    # FORMAT_FEEDER describe esta línea, no las de tramo: se vuelve al
                    # formato de la tabla, si ya se había declarado.
                    columns = columns_by_section.get(section or '')
                    continue
                if line.startswith('FORMAT_') and '=' in line:
                    etiqueta, _, resto = line.partition('=')
                    columns = [x.strip() for x in _split(resto)]
                    # FORMAT_FEEDER es la excepción: describe las cabeceras FEEDER=, no
                    # las filas de la tabla, así que no debe quedar como formato de
                    # [SECTION].
                    if section and etiqueta.strip().upper() != 'FORMAT_FEEDER':
                        columns_by_section[section] = columns
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
                        raise ValueError(
                            f'{red_path.name}:{lineno}: SectionID duplicado en LINE '
                            f'CONFIGURATION: {sid!r}. Cada tramo debe aparecer una sola vez.'
                        )
                    line_configurations[sid] = row
                elif section == 'SECTION' and active_feeder:
                    sid = row['SectionID']
                    if sid in sections:
                        raise ValueError(
                            f'{red_path.name}:{lineno}: SectionID duplicado en SECTION: '
                            f'{sid!r} (ya declarado en el alimentador '
                            f'{section_owner[sid]!r}). Cada tramo debe aparecer una sola vez.'
                        )
                    sections[sid] = row
                    section_owner[sid] = active_feeder
                    feeder_rows[active_feeder].append(sid)
                elif section in ('OVERHEADLINE SETTING', 'UNDERGROUNDLINE SETTING'):
                    # La otra forma de decir lo mismo. El export reducido lleva una
                    # tabla [LINE CONFIGURATION] con el conductor de cada tramo; el
                    # export completo la parte en aérea y subterránea, con muchas más
                    # columnas. Se normalizan a la misma forma que ya usa el resto del
                    # programa —y que la vía Access produce desde CYMOVERHEADLINE y
                    # CYMUNDERGROUNDLINE—, así que nada más abajo tiene que enterarse.
                    sid = row.get('SectionID', '')
                    if not sid:
                        continue
                    ajuste = {
                        'SectionID': sid,
                        'LineCableID': row.get('LineCableID', ''),
                        'Length': row.get('Length', ''),
                        'Overhead': '1' if section.startswith('OVERHEAD') else '0',
                    }
                    previo = line_settings.get(sid)
                    if previo is not None and previo['LineCableID'] != ajuste['LineCableID']:
                        raise ValueError(
                            f'{red_path.name}:{lineno}: el tramo {sid!r} tiene dos '
                            f'conductores distintos ({previo["LineCableID"]!r} y '
                            f'{ajuste["LineCableID"]!r}). Cada tramo debe declararse una '
                            f'sola vez.'
                        )
                    line_settings[sid] = ajuste
                elif section == 'SWITCH SETTING':
                    switch_settings.append(row)
                elif section == 'SECTIONALIZER SETTING':
                    sectionalizer_settings.append(row)
                elif section == 'INTERMEDIATE NODES':
                    intermediate_nodes.append(row)

        for sid, ajuste in line_settings.items():
            line_configurations.setdefault(sid, ajuste)

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

        # Un RED vacío, truncado o con otro formato producía un dataset sin
        # alimentadores, y el lote terminaba «completado» con 0 convertidos y sin un
        # solo error: el operador veía éxito y no tenía salida. Fallar aquí, nombrando
        # lo que falta, es lo único honesto.
        # Solo se exige lo que ningún export válido puede omitir. [SECTION] y
        # [LINE CONFIGURATION] pueden venir vacías legítimamente: es el caso de un
        # export cuyos alimentadores son todos cabecera sin red MT modelada.
        missing = [name for name, found in (('NODE', nodes), ('SOURCE', sources)) if not found]
        if missing:
            raise ValueError(
                f'{red_path.name}: el RED no contiene filas en '
                + ' ni '.join(f'[{name}]' for name in missing)
                + '. Ningún export IGEA/CYMDIST válido puede omitirlas. Revise que el '
                'fichero esté completo y que sea el RED (no CARGA ni BD_Equipo).'
            )
        if not feeder_rows:
            raise ValueError(
                f'{red_path.name}: no se encontró ninguna cabecera FEEDER= en [SECTION]. '
                'Sin alimentadores no hay nada que convertir; el fichero puede estar '
                'truncado o no ser un export IGEA/CYMDIST.'
            )

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
