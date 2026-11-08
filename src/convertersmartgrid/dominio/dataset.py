"""El dataset común de una red de CYMDIST, sin su lector (002:RF-1).

Lo que leen los TXT, la .mdb y los paquetes VNR-GIS acaba en esta estructura: tablas por
sección, nodos, alimentadores y catálogo, con los índices por alimentador. Está en el
dominio porque la usan el modelo, la reconstrucción y los casos de uso, que no deben
depender del lector: antes ``model`` (dominio) importaba ``dataset`` (adaptador de
entrada) solo para anotar sus parámetros, y la guarda de capas lo tenía por deuda. El
lector de los TXT sigue en ``convertersmartgrid.dataset``, que extiende esta clase.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path


#: Tablas del BD_Equipo que definen tipos de línea, por familia. Están aquí y no en
#: model.py porque las consultan también el inventario, el completado de catálogo y la
#: auditoría de estudios, y cuando cada una llevaba su propia lista se desincronizaron:
#: el catálogo del export completo trae los cables en [CABLE], no en [CONCENTRIC NEUTRAL
#: CABLE], y los 8.729 tramos subterráneos caían a DEFAULT sin que nada lo dijera.
TABLAS_TIPOS_AEREO: tuple[str, ...] = ('LINE',)
TABLAS_TIPOS_SUBTERRANEO: tuple[str, ...] = ('CONCENTRIC NEUTRAL CABLE', 'CABLE')
TABLAS_TIPOS_LINEA: tuple[str, ...] = TABLAS_TIPOS_AEREO + TABLAS_TIPOS_SUBTERRANEO


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
    capacitor_settings: tuple[dict[str, str], ...] = ()
    #: De qué fuente vienen: «txt», «mdb» o «vnr» (056:RF-3). Los TXT, por defecto, para que su DGS no cambie.
    fuente: str = 'txt'
    #: Lo que la fuente dice de cada alimentador: sistema y SET (055:RF-1). Los TXT y la .mdb no lo traen.
    estructura_fuente: dict[str, dict[str, str]] = field(default_factory=dict)
    regulator_settings: tuple[dict[str, str], ...] = ()

    # ------------------------------------------------------------------ índices
    # Se construyen una vez, la primera vez que se piden, y valen para todo el lote.
    # Antes cada alimentador recorría CUSTOMER LOADS, las maniobras y los INTERMEDIATE
    # NODES *enteros* para quedarse con lo suyo: O(alimentadores × filas). Con pocos
    # alimentadores no se notaba; con 200 de tamaño medio, cada uno costaba casi cuatro
    # veces más que con 50 y el lote crecía de forma cuadrática. Agrupados aquí, el
    # coste de un alimentador depende solo de su propio tamaño.
    #
    # Conservan el orden de lectura dentro de cada grupo: el DGS debe salir idéntico
    # al que salía recorriendo las tablas completas (regla de determinismo).

    @cached_property
    def customer_loads_by_feeder(self) -> dict[str, tuple[tuple[tuple[str, str], dict[str, str]], ...]]:
        """NetworkID → ((SectionID, DeviceNumber), fila) de CUSTOMER LOADS."""
        grouped: dict[str, list] = defaultdict(list)
        for key, row in self.customer_loads.items():
            owner = self.section_owner.get(key[0])
            if owner is not None:
                grouped[owner].append((key, row))
        return {owner: tuple(rows) for owner, rows in grouped.items()}

    @cached_property
    def switching_by_feeder(self) -> dict[str, tuple[tuple[str, dict[str, str]], ...]]:
        """NetworkID → (``'SWITCH'`` | ``'SECTIONALIZER'``, fila), interruptores primero."""
        grouped: dict[str, list] = defaultdict(list)
        for kind, rows in (
            ('SWITCH', self.switch_settings),
            ('SECTIONALIZER', self.sectionalizer_settings),
        ):
            for row in rows:
                owner = self.section_owner.get(row.get('SectionID', ''))
                if owner is not None:
                    grouped[owner].append((kind, row))
        return {owner: tuple(rows) for owner, rows in grouped.items()}

    @cached_property
    def intermediate_by_section(self) -> dict[str, tuple[dict[str, str], ...]]:
        """SectionID → filas de INTERMEDIATE NODES en orden de lectura (sin ordenar por SeqNumber)."""
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.intermediate_nodes:
            grouped[row.get('SectionID', '')].append(row)
        return {sid: tuple(rows) for sid, rows in grouped.items()}

    def feeder_ids(self) -> tuple[str, ...]:
        return tuple(self.feeders.keys())

    def feeder_section_ids(self, network_id: str) -> frozenset[str]:
        return frozenset(self.feeders[network_id])

    def resolve_feeder(self, selector: str) -> str:
        from ..naming import feeder_short_name, feeder_tokens

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
