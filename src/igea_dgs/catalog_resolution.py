"""Evidence-ranked equipment resolution without renaming source asset codes."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from .reconstruction import EvidenceLevel, ReconstructionPolicy, ReconstructionResult


PARAMETER_FIELDS = ('R1', 'R0', 'X1', 'X0', 'B1', 'B0', 'Amps')
CATALOG_KINDS = ('source', 'manufacturer', 'global')


@dataclass(frozen=True)
class CatalogSource:
    name: str
    kind: str
    version: str
    manufacturer: str
    locator: str
    sha256: str
    rows: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in CATALOG_KINDS:
            raise ValueError(f'unsupported catalog kind: {self.kind}')
        if not all((self.name, self.version, self.locator, self.sha256)):
            raise ValueError('catalog name, version, locator and sha256 are required')
        if len(self.sha256) != 64 or any(char not in '0123456789abcdefABCDEF' for char in self.sha256):
            raise ValueError('catalog sha256 must contain 64 hexadecimal characters')

    def descriptor(self) -> dict[str, str]:
        return {
            'name': self.name,
            'kind': self.kind,
            'version': self.version,
            'manufacturer': self.manufacturer,
            'locator': self.locator,
            'sha256': self.sha256.lower(),
        }


@dataclass(frozen=True)
class EquipmentQuery:
    original_code: str
    equipment_class: str
    material: str | None
    section_mm2: float | None
    voltage_kv: float | None
    overhead: bool
    manufacturer: str = ''
    physical: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedParameters:
    original_code: str
    source_code: str
    parameters: Mapping[str, float]
    rule: str
    level: EvidenceLevel
    confidence: float
    candidates: tuple[str, ...] = ()
    catalog: CatalogSource | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def materialize_row(self) -> dict[str, str]:
        row = {'ID': self.original_code}
        row.update({key: format(float(value), '.12g') for key, value in self.parameters.items()})
        return row


def resolve_equipment(
    query: EquipmentQuery,
    catalogs: Iterable[CatalogSource],
    policy: ReconstructionPolicy,
) -> ResolvedParameters:
    """Resolve parameters by explicit evidence hierarchy, never fuzzy code distance."""

    catalog_list = tuple(catalogs)
    exact = _exact_candidates(query, catalog_list)
    if exact:
        ranked_exact = sorted(
            exact, key=lambda item: (_kind_rank(item[0].kind), item[0].name, _code(item[1])),
        )
        catalog, row = ranked_exact[0]
        parameters: dict[str, float] = {}
        contributors: list[dict[str, str]] = []
        for candidate_catalog, candidate_row in ranked_exact:
            supplied = []
            for key, value in _parameters(candidate_row).items():
                if key not in parameters:
                    parameters[key] = value
                    supplied.append(key)
            if supplied:
                contributors.append({
                    **candidate_catalog.descriptor(), 'fields': ','.join(supplied),
                })
        if _parameters_complete(parameters):
            rule = {
                'source': 'EXACT_SOURCE',
                'manufacturer': 'EXACT_MANUFACTURER',
                'global': 'EXACT_GLOBAL',
            }[catalog.kind]
            return ResolvedParameters(
                original_code=query.original_code,
                source_code=_code(row),
                parameters=parameters,
                rule=rule,
                level=EvidenceLevel.CATALOG_MATCH,
                confidence=1.0 if catalog.kind == 'source' else 0.95,
                catalog=catalog,
                provenance={'catalog': catalog.descriptor(), 'contributors': contributors},
            )

    compatible = _compatible_candidates(query, catalog_list)
    if compatible:
        best_rank = min(_kind_rank(item[0].kind) for item in compatible)
        preferred = [item for item in compatible if _kind_rank(item[0].kind) == best_rank]
        preferred.sort(key=lambda item: (item[0].name, _code(item[1])))
        candidate_codes = tuple(sorted({_code(row) for _catalog, row in preferred}))
        if len(candidate_codes) == 1:
            catalog, row = preferred[0]
            return ResolvedParameters(
                original_code=query.original_code,
                source_code=_code(row),
                parameters=_parameters(row),
                rule='COMPATIBLE_ATTRIBUTES',
                level=EvidenceLevel.CATALOG_MATCH,
                confidence=max(policy.minimum_catalog_confidence, 0.8),
                candidates=candidate_codes,
                catalog=catalog,
                provenance={'catalog': catalog.descriptor(), 'matched_attributes': [
                    'equipment_class', 'material', 'section_mm2', 'voltage_kv', 'overhead',
                ]},
            )
        return _provisional(query, policy, candidates=candidate_codes, reason='ambiguous_catalog_tie')

    physical = _derive_physical(query)
    if physical is not None:
        if not policy.allow_engineering_assumptions:
            raise ValueError('physical derivation is disabled by reconstruction policy')
        return ResolvedParameters(
            original_code=query.original_code,
            source_code=query.original_code,
            parameters=physical,
            rule='PHYSICAL_DERIVATION',
            level=EvidenceLevel.ENGINEERING_ASSUMPTION,
            confidence=0.65,
            provenance={
                'physical_inputs': dict(query.physical),
                'formula': 'R1 = resistivity_ohm_mm2_m * 1000 / section_mm2',
            },
        )
    return _provisional(query, policy, reason='no_compatible_catalog_or_physical_data')


def resolve_dataset_equipment(
    result: ReconstructionResult,
    catalogs: Iterable[CatalogSource],
) -> dict[str, ResolvedParameters]:
    """Materialize exact rows for unresolved codes in the derived dataset."""

    dataset = result.dataset
    external = tuple(catalogs)
    source_catalog = _catalog_from_dataset(dataset)
    all_catalogs = (source_catalog, *external) if source_catalog.rows else external
    resolved: dict[str, ResolvedParameters] = {}
    existing = {
        table: {(row.get('ID') or '').strip() for row in rows}
        for table, rows in dataset.equipment_tables.items()
    }
    for section_id in sorted(dataset.line_configurations):
        config = dataset.line_configurations[section_id]
        overhead = str(config.get('Overhead', '1')).strip() not in {'0', 'false', 'False'}
        table = 'LINE' if overhead else 'CONCENTRIC NEUTRAL CABLE'
        code = (config.get('LineCableID') or '').strip()
        if not code:
            code = f'UNSPECIFIED_{section_id}'
            config['LineCableID'] = code
            result.record_change(
                entity_type='line_configuration', entity_id=section_id,
                field='LineCableID', original_value='', applied_value=code,
                level=EvidenceLevel.ENGINEERING_ASSUMPTION,
                rule='PROVISIONAL_PROFILE',
                reason='The section had no equipment code; a deterministic derived ID was required.',
                confidence=0.1,
            )
        if code in existing.get(table, set()):
            continue
        owner = dataset.section_owner.get(section_id, '')
        source = dataset.sources.get(owner, {})
        query = EquipmentQuery(
            original_code=code,
            equipment_class=table,
            material=_text(config, 'Material', 'ConductorMaterial'),
            section_mm2=_float_from(config, 'SectionMM2', 'Section', 'CrossSectionMM2'),
            voltage_kv=_source_voltage(source),
            overhead=overhead,
            manufacturer=_text(config, 'Manufacturer', 'Fabricante') or '',
            physical={
                key: value for key, value in {
                    'resistivity_ohm_mm2_m': _float_from(
                        config, 'ResistivityOhmMM2M', 'resistivity_ohm_mm2_m',
                    ),
                    'x1_ohm_km': _float_from(config, 'X1', 'x1_ohm_km'),
                    'x0_ohm_km': _float_from(config, 'X0', 'x0_ohm_km'),
                    'ampacity_a': _float_from(config, 'Amps', 'ampacity_a'),
                }.items() if value is not None
            },
        )
        resolution = resolve_equipment(query, all_catalogs, result.policy)
        row = resolution.materialize_row()
        dataset.equipment_tables[table] = tuple(dataset.equipment_tables.get(table, ())) + (row,)
        existing.setdefault(table, set()).add(code)
        resolved[code] = resolution
        result.record_change(
            entity_type='equipment', entity_id=code, field='__row__',
            original_value=None, applied_value=row,
            level=resolution.level, rule=resolution.rule,
            reason='Missing equipment parameters were materialized under the original asset code.',
            confidence=resolution.confidence,
            candidates=resolution.candidates,
            provenance={
                **dict(resolution.provenance),
                'source_code': resolution.source_code,
                'section_id': section_id,
                'equipment_table': table,
            },
        )
    return resolved


def _exact_candidates(query, catalogs):
    result = []
    for catalog in catalogs:
        if catalog.kind == 'manufacturer' and query.manufacturer and (
            catalog.manufacturer.casefold() != query.manufacturer.casefold()
        ):
            continue
        for row in catalog.rows:
            if (
                _code(row).casefold() == query.original_code.casefold()
                and _row_matches_medium(query, row)
            ):
                result.append((catalog, row))
    return result


def _compatible_candidates(query, catalogs):
    if None in (query.material, query.section_mm2, query.voltage_kv):
        return []
    result = []
    for catalog in catalogs:
        if catalog.kind == 'manufacturer' and query.manufacturer and (
            catalog.manufacturer.casefold() != query.manufacturer.casefold()
        ):
            continue
        for row in catalog.rows:
            if not _parameters_complete(_parameters(row)):
                continue
            row_class = _text(row, 'EquipmentClass', 'Class', 'Table')
            row_material = _text(row, 'Material', 'ConductorMaterial')
            row_section = _float_from(row, 'SectionMM2', 'Section', 'CrossSectionMM2')
            row_voltage = _float_from(row, 'VoltageKV', 'NominalVoltageKV', 'kV')
            row_overhead = _bool_from(row, 'Overhead', 'Aerial')
            if (
                row_class and _class_equal(row_class, query.equipment_class)
                and row_material and row_material.casefold() == str(query.material).casefold()
                and row_section is not None and math.isclose(row_section, query.section_mm2)
                and row_voltage is not None and math.isclose(row_voltage, query.voltage_kv)
                and row_overhead is query.overhead
            ):
                result.append((catalog, row))
    return result


def _provisional(query, policy, *, candidates=(), reason=''):
    if not policy.allow_engineering_assumptions:
        raise ValueError('provisional equipment profiles are disabled by reconstruction policy')
    parameters = (
        {'R1': 0.8, 'R0': 0.8, 'X1': 0.4, 'X0': 1.2,
         'B1': 0.0, 'B0': 0.0, 'Amps': 100.0}
        if query.overhead else
        {'R1': 0.5, 'R0': 0.5, 'X1': 0.1, 'X0': 0.3,
         'B1': 0.0, 'B0': 0.0, 'Amps': 150.0}
    )
    return ResolvedParameters(
        original_code=query.original_code,
        source_code=query.original_code,
        parameters=parameters,
        rule='PROVISIONAL_PROFILE',
        level=EvidenceLevel.ENGINEERING_ASSUMPTION,
        confidence=0.1,
        candidates=tuple(candidates),
        provenance={'reason': reason, 'profile': 'generic_overhead' if query.overhead else 'generic_cable'},
    )


def _derive_physical(query):
    rho = _number(query.physical.get('resistivity_ohm_mm2_m'))
    if rho is None or query.section_mm2 is None or query.section_mm2 <= 0:
        return None
    r1 = rho * 1000.0 / query.section_mm2
    return {
        'R1': r1,
        'R0': _number(query.physical.get('r0_ohm_km')) or r1,
        'X1': _number(query.physical.get('x1_ohm_km')) or (0.4 if query.overhead else 0.1),
        'X0': _number(query.physical.get('x0_ohm_km')) or (1.2 if query.overhead else 0.3),
        'B1': _number(query.physical.get('b1')) or 0.0,
        'B0': _number(query.physical.get('b0')) or 0.0,
        'Amps': _number(query.physical.get('ampacity_a')) or 100.0,
    }


def _parameters(row):
    return {key: value for key in PARAMETER_FIELDS if (value := _number(row.get(key))) is not None}


def _parameters_complete(parameters):
    return all(key in parameters for key in PARAMETER_FIELDS)


def _row_matches_medium(query, row):
    row_class = _text(row, 'EquipmentClass', 'Class', 'Table')
    if row_class and not _class_equal(row_class, query.equipment_class):
        return False
    row_overhead = _bool_from(row, 'Overhead', 'Aerial')
    return row_overhead is None or row_overhead is query.overhead


def _code(row):
    return _text(row, 'ID', 'Code', 'codigo') or ''


def _kind_rank(kind):
    return CATALOG_KINDS.index(kind)


def _class_equal(left, right):
    normalize = lambda value: ''.join(char for char in value.upper() if char.isalnum())
    return normalize(left) == normalize(right)


def _text(row, *keys):
    for key in keys:
        value = str(row.get(key) or '').strip()
        if value:
            return value
    return None


def _float_from(row, *keys):
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _bool_from(row, *keys):
    for key in keys:
        if key not in row or row.get(key) in (None, ''):
            continue
        value = row.get(key)
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {'1', 'true', 'yes', 'si', 'sí', 'aerial', 'overhead'}
    return None


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _source_voltage(source):
    desired = _float_from(source, 'DesiredVoltage', 'NominalVoltageKV')
    if desired is not None:
        return desired
    phase = _float_from(source, 'OperatingVoltageA')
    return phase * math.sqrt(3) if phase is not None else None


def _catalog_from_dataset(dataset) -> CatalogSource:
    rows = []
    for table, table_rows in sorted(dataset.equipment_tables.items()):
        if table not in {'LINE', 'CONCENTRIC NEUTRAL CABLE', 'CABLE'}:
            continue
        for row in table_rows:
            rows.append({
                **dict(row),
                'EquipmentClass': table,
                'Overhead': table == 'LINE',
            })
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')
    return CatalogSource(
        name='source-equipment', kind='source', version='source-snapshot',
        manufacturer='', locator=str(dataset.equipment_path),
        sha256=hashlib.sha256(encoded).hexdigest(), rows=tuple(rows),
    )
