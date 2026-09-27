"""Inventario de cargas con propiedad eléctrica explícita por alimentador."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .dgs import NA205_SED_LV_KV, NA205_TR2_UK_PCT, _tr2_losses_kw
from .model import FeederModel, build_feeder_model
from .reglas import Reglas, aplicar_reglas, preparar_dataset


@dataclass(frozen=True)
class LoadInventoryRow:
    name: str
    class_name: str
    alimentador: str
    network_id: str
    grid: str
    sed: str
    section_id: str
    device_number: str
    terminal_substation: str
    terminal: str
    kw: float
    kvar: float
    kva: float
    power_factor: float
    voltage_mt_kv: float
    voltage_bt_kv: float | None
    transformer_kva: float | None
    uk_pct: float | None
    copper_losses_kw: float | None
    core_losses_kw: float | None
    vector_group: str
    status: str
    diagnostic: str
    provenance: dict[str, str] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LoadInventoryPage:
    total: int
    offset: int
    limit: int
    rows: tuple[LoadInventoryRow, ...]


def _status_for_load(
    *, model: FeederModel, feeder: str, network_id: str, device_number: str,
    duplicate_owners: set[tuple[str, str]], section_id: str,
) -> tuple[str, str]:
    islands = model.islands or {}
    if device_number in set(islands.get('loads') or ()):
        return 'DESCONECTADO', 'La carga no tiene camino eléctrico hasta el SOURCE.'
    if not feeder or not network_id:
        return 'NO_IDENTIFICADO', 'La carga no conserva alimentador y NetworkID de origen.'
    if feeder != model.name or network_id != model.network_id:
        return 'AMBIGUO', 'La propiedad de la carga contradice el modelo que la contiene.'
    if (section_id, device_number) in duplicate_owners:
        return 'AMBIGUO', 'La misma clave de carga aparece con más de un alimentador propietario.'
    return 'OK', ''


def rows_from_models(
    models: Sequence[FeederModel], *, grid_name: str | None = None,
) -> tuple[LoadInventoryRow, ...]:
    owners: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for model in models:
        for load in model.loads:
            key = (load.section_id, load.device_number)
            owners.setdefault(key, set()).add((load.feeder, load.network_id))
    duplicates = {key for key, values in owners.items() if len(values) > 1}

    rows: list[LoadInventoryRow] = []
    for model in models:
        sed_by_key = {sed.load_key: sed for sed in model.seds}
        grid = grid_name or model.name
        for load in model.loads:
            key = (load.section_id, load.device_number)
            sed = sed_by_key.get(key)
            status, diagnostic = _status_for_load(
                model=model,
                feeder=load.feeder,
                network_id=load.network_id,
                device_number=load.device_number,
                duplicate_owners=duplicates,
                section_id=load.section_id,
            )
            transformer_kva = float(sed.design_kva) if sed is not None else None
            copper = core = None
            if transformer_kva is not None:
                copper, core = _tr2_losses_kw(
                    transformer_kva, uk_pct=NA205_TR2_UK_PCT,
                )
            sed_name = sed.loc_name if sed is not None else ''
            rows.append(LoadInventoryRow(
                name=load.display_name or load.customer_number or load.device_number,
                class_name='ElmLod',
                alimentador=load.feeder,
                network_id=load.network_id,
                grid=grid,
                sed=sed_name,
                section_id=load.section_id,
                device_number=load.device_number,
                terminal_substation=sed_name,
                terminal=f'{sed_name}_BT' if sed_name else load.node_id,
                kw=float(load.p_mw) * 1000.0,
                kvar=float(load.q_mvar) * 1000.0,
                kva=float(load.connected_kva),
                power_factor=float(load.pf),
                voltage_mt_kv=float(model.nominal_kv),
                voltage_bt_kv=NA205_SED_LV_KV if sed is not None else None,
                transformer_kva=transformer_kva,
                uk_pct=NA205_TR2_UK_PCT if sed is not None else None,
                copper_losses_kw=copper,
                core_losses_kw=core,
                vector_group='Dyn5' if sed is not None else '',
                status=status,
                diagnostic=diagnostic,
                provenance={
                    'network_id': load.network_id,
                    'section_id': load.section_id,
                    'device_number': load.device_number,
                },
            ))
    rows.sort(key=lambda row: (
        row.alimentador, row.name, row.section_id, row.device_number,
    ))
    return tuple(rows)


def build_load_inventory(
    dataset,
    networks: Iterable[str],
    *,
    reglas: Reglas,
    catalogo: Path | str | None,
    grid_name: str | None = None,
) -> tuple[LoadInventoryRow, ...]:
    preparar_dataset(dataset, catalogo=catalogo)
    models: list[FeederModel] = []
    for network in networks:
        model = build_feeder_model(
            dataset, network, strict=False, include_geography=False,
        )
        aplicar_reglas(model, reglas)
        models.append(model)
    return rows_from_models(models, grid_name=grid_name)


def query_load_inventory(
    rows: Sequence[LoadInventoryRow],
    *,
    feeder: str | None = None,
    status: str | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> LoadInventoryPage:
    if offset < 0:
        raise ValueError('offset debe ser mayor o igual que 0')
    if limit < 1 or limit > 500:
        raise ValueError('limit debe estar entre 1 y 500')
    selected = list(rows)
    if feeder:
        wanted = feeder.casefold()
        selected = [row for row in selected if row.alimentador.casefold() == wanted]
    if status:
        wanted = status.casefold()
        selected = [row for row in selected if row.status.casefold() == wanted]
    if search:
        wanted = search.strip().casefold()
        selected = [
            row for row in selected
            if wanted in row.name.casefold()
            or wanted in row.sed.casefold()
            or wanted in row.section_id.casefold()
        ]
    page = tuple(selected[offset:offset + limit])
    return LoadInventoryPage(
        total=len(selected), offset=offset, limit=limit, rows=page,
    )
