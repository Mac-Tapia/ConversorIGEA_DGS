"""Contrato auditable entre el DGS exportado y sus objetos en PowerFactory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
from pathlib import Path
from collections.abc import Sequence


SCHEMA_VERSION = 1
TARGET_CLASSES = ('ElmLod', 'ElmSym', 'ElmXnet')


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

    @property
    def runtime_key(self) -> tuple[str, str, str, str]:
        return (self.class_name, self.loc_name, self.terminal, self.substation)


@dataclass(frozen=True)
class FeederMetadata:
    schema_version: int
    dgs_file: str
    dgs_sha256: str
    target_classes: tuple[str, ...]
    assignments: tuple[FeederAssignment, ...]


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_assignments(records: Sequence[FeederAssignment]) -> None:
    runtime_keys: set[tuple[str, str, str, str]] = set()
    fid_keys: set[tuple[str, str]] = set()
    for index, record in enumerate(records, start=1):
        if record.class_name not in TARGET_CLASSES:
            raise ValueError(f'asignación {index}: clase PowerFactory no permitida: {record.class_name!r}')
        for field_name, label in (
            ('dgs_fid', 'FID'), ('loc_name', 'nombre'), ('feeder', 'alimentador'),
            ('network_id', 'NetworkID'), ('terminal', 'terminal'),
        ):
            if not str(getattr(record, field_name)).strip():
                raise ValueError(f'asignación {index}: {label} vacío')
        if record.runtime_key in runtime_keys:
            raise ValueError(f'identidad PowerFactory duplicada: {record.runtime_key!r}')
        runtime_keys.add(record.runtime_key)
        fid_key = (record.class_name, record.dgs_fid)
        if fid_key in fid_keys:
            raise ValueError(f'FID duplicado para {record.class_name}: {record.dgs_fid}')
        fid_keys.add(fid_key)


def write_feeder_metadata(
    records: Sequence[FeederAssignment], dgs_path: Path | str, output_path: Path | str,
) -> Path:
    records = tuple(records)
    validate_assignments(records)
    dgs = Path(dgs_path)
    output = Path(output_path)
    payload = {
        'schema_version': SCHEMA_VERSION,
        'dgs_file': dgs.name,
        'dgs_sha256': sha256_file(dgs),
        'target_classes': list(TARGET_CLASSES),
        'assignments': [asdict(record) for record in records],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return output


def write_name_feeder_mapping_csv(
    records: Sequence[FeederAssignment], output_path: Path | str,
) -> Path:
    """Publica la relación humana ``Name -> Alimentador`` del DGS unido.

    ``Grid`` identifica el contenedor común de PowerFactory y, por diseño, tiene
    el mismo valor para todos sus objetos. Este fichero conserva la pertenencia
    individual de cargas, generadores y fuentes para cualquier cantidad de
    alimentadores dentro de ese único Grid/DGS.
    """

    records = tuple(records)
    validate_assignments(records)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        records,
        key=lambda record: (
            record.feeder.casefold(), record.class_name, record.loc_name.casefold(),
            record.terminal.casefold(), record.dgs_fid,
        ),
    )
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(('Name', 'Alimentador', 'Clase', 'NetworkID', 'Terminal', 'Substation'))
        for record in ordered:
            writer.writerow((
                record.loc_name, record.feeder, record.class_name, record.network_id,
                record.terminal, record.substation,
            ))
    return output


def read_feeder_metadata(
    path: Path | str, *, expected_dgs: Path | str | None = None,
) -> FeederMetadata:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'No se pudo leer metadata de alimentadores: {source}: {exc}') from exc
    if not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'Versión de metadata no compatible: {raw.get("schema_version")!r}')
    if tuple(raw.get('target_classes') or ()) != TARGET_CLASSES:
        raise ValueError('Las clases objetivo de la metadata no coinciden con el contrato')
    try:
        assignments = tuple(FeederAssignment(**item) for item in raw['assignments'])
        metadata = FeederMetadata(
            schema_version=raw['schema_version'], dgs_file=str(raw['dgs_file']),
            dgs_sha256=str(raw['dgs_sha256']), target_classes=TARGET_CLASSES,
            assignments=assignments,
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Metadata de alimentadores incompleta: {exc}') from exc
    validate_assignments(metadata.assignments)
    if expected_dgs is not None:
        actual = sha256_file(expected_dgs)
        if actual != metadata.dgs_sha256:
            raise ValueError(
                f'SHA-256 del DGS no coincide: metadata={metadata.dgs_sha256}, actual={actual}')
    return metadata
