"""Procedencia por alimentador para objetos de una Grid DGS conjunta."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .util import sha256_file, write_json_atomic

SCHEMA_VERSION = 'igea-dgs-feeder-metadata-v1'
TARGET_CLASSES = frozenset({'ElmLod', 'ElmShnt', 'ElmSubstat', 'ElmSym', 'ElmXnet'})


@dataclass(frozen=True)
class FeederAssignment:
    class_name: str
    dgs_fid: str
    loc_name: str
    feeder: str
    network_id: str
    terminal: str
    substation: str
    section_id: str = ''
    node_id: str = ''
    grid: str = ''


def _loc_name(value: str) -> str:
    return str(value or '').replace(';', ',').replace('\r', ' ').replace('\n', ' ').strip()[:40]


def validate_assignments(records: Iterable[FeederAssignment]) -> None:
    seen_fids: set[tuple[str, str]] = set()
    seen_identities: set[tuple[str, str, str, str]] = set()
    count = 0
    for record in records:
        count += 1
        if record.class_name not in TARGET_CLASSES:
            raise ValueError(f'clase no permitida en metadata: {record.class_name!r}')
        if not all((record.dgs_fid, record.loc_name, record.feeder, record.network_id)):
            raise ValueError('metadata con FID, loc_name, feeder o NetworkID vacío')
        fid_key = (record.class_name, record.dgs_fid)
        if fid_key in seen_fids:
            raise ValueError(f'FID duplicado en metadata: {fid_key!r}')
        seen_fids.add(fid_key)
        identity = (record.class_name, record.loc_name, record.terminal, record.substation)
        if identity in seen_identities:
            raise ValueError(f'identidad PowerFactory duplicada: {identity!r}')
        seen_identities.add(identity)
    if not count:
        raise ValueError('metadata de alimentadores vacía')


def assignments_from_model(model: Any, dgs_manifest: Any) -> list[FeederAssignment]:
    """Relaciona FIDs DGS con la propiedad eléctrica retenida en cada objeto."""
    loads_by_key = {(load.section_id, load.device_number): load for load in model.loads}
    seds_by_key = {sed.load_key: sed for sed in model.seds}
    assignments: list[FeederAssignment] = []
    # Spec 022: en la red unida por SET cada objeto está en la red de su zonal, o de su SET
    # en un zonal dividido (RF-64, RF-69).
    from .combine import red_de_nodos

    zonales = red_de_nodos(model)

    def grid(node_id: str) -> str:
        return _loc_name(zonales.get(node_id) or model.name)

    for key, fid in dgs_manifest.load_fids.items():
        load = loads_by_key[key]
        sed = seds_by_key.get(key)
        load_name = load.display_name or load.customer_number or load.device_number or load.section_id
        assignments.append(FeederAssignment(
            class_name='ElmLod', dgs_fid=fid, loc_name=_loc_name(load_name),
            feeder=load.feeder, network_id=load.network_id,
            terminal=_loc_name(f'{sed.loc_name}_BT') if sed else _loc_name(load.node_id),
            substation=_loc_name(sed.loc_name) if sed else '',
            section_id=load.section_id, node_id=load.node_id,
            grid=grid(load.node_id),
        ))

    for key, fid in dgs_manifest.sed_fids.items():
        sed = next((item for item in model.seds
                    if (item.section_id, item.device_number) == key), None)
        if sed is None:
            raise ValueError(f'FID de SED sin objeto fuente: {key!r}')
        assignments.append(FeederAssignment(
            class_name='ElmSubstat', dgs_fid=fid, loc_name=_loc_name(sed.loc_name),
            feeder=sed.feeder, network_id=sed.network_id,
            terminal='', substation=_loc_name(sed.loc_name),
            section_id=sed.section_id, node_id=sed.node_id,
            grid=grid(sed.node_id),
        ))

    capacitors_by_key = {
        (bank.network_id, bank.capacitor_id): bank for bank in model.capacitors
    }
    for key, fid in dgs_manifest.shunt_fids.items():
        bank = capacitors_by_key.get(key)
        if bank is None:
            raise ValueError(f'FID de ElmShnt sin objeto fuente: {key!r}')
        assignments.append(FeederAssignment(
            class_name='ElmShnt', dgs_fid=fid, loc_name=_loc_name(bank.capacitor_id),
            feeder=bank.feeder, network_id=bank.network_id,
            terminal=_loc_name(bank.node_id), substation='', node_id=bank.node_id,
            grid=grid(bank.node_id),
        ))

    combined = getattr(model, 'combined', None)
    feeder_refs = getattr(combined, 'feeders', ()) if combined is not None else ()
    barras = list(getattr(combined, 'barras_set', None) or []) if combined is not None else []
    if barras:
        # Spec 022: la red externa es de la barra de SET y la comparten sus alimentadores:
        # se registra una vez, con todos ellos y la SET como red (RF-11).
        from .naming import sufijo_tension

        sin_set = set(combined.sin_set)
        sources = [(f'{b.set_codigo} {sufijo_tension(b.nominal_kv)}', ' + '.join(b.feeders),
                    b.set_codigo, b.node_id) for b in barras]
        sources += [(ref.name, ref.name, ref.network_id, ref.source_node)
                    for ref in feeder_refs if ref.name in sin_set]
    elif feeder_refs:
        sources = [(ref.name, ref.name, ref.network_id, ref.source_node) for ref in feeder_refs]
    else:
        sources = [(model.name, model.name, model.network_id, model.source_node)]
    for fuente, feeder, network_id, node_id in sources:
        fid = dgs_manifest.source_fids.get(fuente)
        if not fid:
            raise ValueError(f'FID de ElmXnet ausente para {fuente!r}')
        assignments.append(FeederAssignment(
            class_name='ElmXnet', dgs_fid=fid,
            loc_name=_loc_name(f'External Grid {fuente}'), feeder=feeder,
            network_id=network_id, terminal=_loc_name(node_id), substation='', node_id=node_id,
            grid=grid(node_id),
        ))

    validate_assignments(assignments)
    return assignments


def write_feeder_metadata(
    records: Iterable[FeederAssignment],
    dgs_path: Path | str,
    output_path: Path | str,
    *,
    capacitor_banks: Iterable[dict[str, Any]] = (),
    capacitor_issues: Iterable[dict[str, Any]] = (),
) -> Path:
    dgs_path, output_path = Path(dgs_path), Path(output_path)
    assignments = list(records)
    validate_assignments(assignments)
    payload = {
        'schema_version': SCHEMA_VERSION,
        'dgs_file': dgs_path.name,
        'dgs_sha256': sha256_file(dgs_path),
        'classes': sorted({row.class_name for row in assignments}),
        'assignments': [asdict(row) for row in assignments],
        'capacitor_banks': list(capacitor_banks),
        'capacitor_issues': list(capacitor_issues),
    }
    write_json_atomic(output_path, payload)
    return output_path


def read_feeder_metadata(
    path: Path | str,
    *,
    expected_dgs: Path | str | None = None,
) -> dict[str, Any]:
    metadata_path = Path(path)
    payload = json.loads(metadata_path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'esquema de metadata desconocido: {payload.get("schema_version")!r}')
    assignments = [FeederAssignment(**row) for row in payload.get('assignments', [])]
    validate_assignments(assignments)
    if expected_dgs is not None:
        dgs_path = Path(expected_dgs)
        if payload.get('dgs_file') != dgs_path.name:
            raise ValueError('la metadata pertenece a otro DGS')
        if payload.get('dgs_sha256') != sha256_file(dgs_path):
            raise ValueError('SHA-256 de DGS no coincide con feeder metadata')
    return payload
