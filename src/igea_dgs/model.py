from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Mapping

from .dataset import CymdistDataset

# Operational SED / transformer codes embedded in IGEA customer/device IDs
# (e.g. CUST_2010_1042900_SE40699-2, DEV_..._M40699).
_SED_CODE_RE = re.compile(r'(?:^|_)((?:SE|M)\d[\w-]*)\s*$', re.IGNORECASE)


class ModelBuildError(ValueError):
    pass


class UnresolvedLineTypesError(ModelBuildError):
    def __init__(self, feeder: str, types: set[str]):
        self.feeder = feeder
        self.types = frozenset(types)
        super().__init__(f'{feeder}: unresolved line types: {", ".join(sorted(types))}')


@dataclass(frozen=True)
class LineType:
    key: str
    code: str
    source_table: str
    r1_ohm_km: float
    r0_ohm_km: float
    x1_ohm_km: float
    x0_ohm_km: float
    b1_source: float
    b0_source: float
    ampacity_a: float


@dataclass(frozen=True)
class Node:
    node_id: str
    x: float | None
    y: float | None


@dataclass(frozen=True)
class Line:
    section_id: str
    from_node: str
    to_node: str
    phase: str
    type_key: str
    source_type_code: str
    length_m: float
    overhead: bool

    @property
    def length_km(self) -> float:
        return self.length_m / 1000.0


@dataclass(frozen=True)
class Load:
    section_id: str
    device_number: str
    customer_number: str
    location: str
    node_id: str
    p_mw: float
    q_mvar: float
    pf: float
    connected_kva: float
    kwh: float
    phase: str
    sed_code: str = ''
    display_name: str = ''


@dataclass(frozen=True)
class Sed:
    """Distribution substation identified from TXT customer/device codes."""

    code: str
    loc_name: str
    node_id: str
    design_kva: float
    section_id: str
    device_number: str
    load_key: tuple[str, str]


@dataclass(frozen=True)
class SwitchingDevice:
    kind: str
    section_id: str
    location: str
    terminal_side: int
    node_id: str
    eq_id: str
    eq_number: str
    phase: str
    on_off: int
    locked: int
    eq_state: int


@dataclass
class FeederModel:
    name: str
    network_id: str
    nominal_kv: float
    source_node: str
    nodes: dict[str, Node]
    lines: list[Line]
    loads: list[Load]
    devices: list[SwitchingDevice]
    line_types: dict[str, LineType]
    line_type_aliases: dict[str, str] = field(default_factory=dict)
    unresolved_line_types: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    section_by_id: dict[str, Line] = field(default_factory=dict)
    seds: list[Sed] = field(default_factory=list)


def _float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, '') else default
    except (ValueError, TypeError):
        return default


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value not in (None, '') else default
    except (ValueError, TypeError):
        return default


def _line_type_from_row(table: str, row: Mapping[str, str]) -> LineType:
    code = row.get('ID', '')
    prefix = 'CABLE' if table == 'CONCENTRIC NEUTRAL CABLE' else 'LINE'
    return LineType(
        key=f'{prefix}:{code}',
        code=code,
        source_table=table,
        r1_ohm_km=_float(row.get('R1')),
        r0_ohm_km=_float(row.get('R0')),
        x1_ohm_km=_float(row.get('X1')),
        x0_ohm_km=_float(row.get('X0')),
        b1_source=_float(row.get('B1')),
        b0_source=_float(row.get('B0')),
        ampacity_a=_float(row.get('Amps')),
    )


def _catalog(dataset: CymdistDataset) -> tuple[dict[str, LineType], dict[str, list[LineType]]]:
    by_key: dict[str, LineType] = {}
    by_code: dict[str, list[LineType]] = {}
    for table in ('LINE', 'CONCENTRIC NEUTRAL CABLE'):
        for row in dataset.equipment_tables.get(table, ()):
            code = row.get('ID', '')
            if not code:
                continue
            typ = _line_type_from_row(table, row)
            by_key[typ.key] = typ
            by_code.setdefault(code, []).append(typ)
    return by_key, by_code


def _resolve_type(
    raw_code: str,
    overhead: bool,
    by_code: dict[str, list[LineType]],
    aliases: Mapping[str, str],
) -> tuple[LineType | None, str | None]:
    requested = aliases.get(raw_code, raw_code)
    candidates = by_code.get(requested, [])
    if not candidates:
        return None, aliases.get(raw_code)
    if len(candidates) == 1:
        return candidates[0], aliases.get(raw_code)
    desired_table = 'LINE' if overhead else 'CONCENTRIC NEUTRAL CABLE'
    for candidate in candidates:
        if candidate.source_table == desired_table:
            return candidate, aliases.get(raw_code)
    return None, aliases.get(raw_code)


def _calc_p_q(row: Mapping[str, str]) -> tuple[float, float, float]:
    value_type = row.get('ValueType', '')
    value1 = _float(row.get('Value1'))
    value2 = _float(row.get('Value2'))
    if value_type == '2' and 0 < abs(value2) <= 1:
        p_mw = value1 / 1000.0
        pf = min(max(abs(value2), 1e-12), 1.0)
        q_mvar = abs(p_mw) * math.tan(math.acos(pf))
        if value2 < 0:
            q_mvar = -q_mvar
        return p_mw, q_mvar, pf
    return value1 / 1000.0, 0.0, abs(value2) if 0 < abs(value2) <= 1 else 0.0


def _load_node(location: str, line: Line, strict: bool) -> str | None:
    if location == '0':
        return line.from_node
    if location == '1':
        return line.to_node
    if strict:
        raise ModelBuildError(f'{line.section_id}: unsupported LOADS.Location={location!r}')
    return None


def _device_side(location: str, section_id: str, strict: bool) -> int | None:
    if location.upper() == 'S':
        return 0
    if location.upper() == 'L':
        return 1
    if strict:
        raise ModelBuildError(f'{section_id}: unsupported switching Location={location!r}')
    return None


def extract_sed_code(*candidates: str) -> str:
    """Return the operational SED code when it is present in TXT identifiers."""
    for raw in candidates:
        text = (raw or '').strip()
        if not text:
            continue
        match = _SED_CODE_RE.search(text)
        if match:
            return match.group(1)
    return ''


def sed_loc_name(code: str) -> str:
    """NA205-style short name: SE_M50144, or SE40699 when the code already starts with SE."""
    code = (code or '').strip()
    if not code:
        return ''
    if code.upper().startswith('SE'):
        return code[:40]
    return f'SE_{code}'[:40]


def _assign_load_display_names(loads: list[Load]) -> list[Load]:
    """Shorten load names to the connected SED name (with (n) suffixes when shared)."""
    by_name: dict[str, list[int]] = {}
    for index, load in enumerate(loads):
        base = load.display_name or load.customer_number or load.device_number or load.section_id
        by_name.setdefault(base, []).append(index)
    renamed = list(loads)
    for base, indexes in by_name.items():
        if len(indexes) == 1:
            idx = indexes[0]
            load = renamed[idx]
            renamed[idx] = Load(**{**load.__dict__, 'display_name': base[:40]})
            continue
        for order, idx in enumerate(indexes, start=1):
            load = renamed[idx]
            suffix = f'({order})'
            name = f'{base[:40 - len(suffix)]}{suffix}'
            renamed[idx] = Load(**{**load.__dict__, 'display_name': name})
    return renamed


def build_feeder_model(
    dataset: CymdistDataset,
    selector: str,
    *,
    aliases: Mapping[str, str] | None = None,
    strict: bool = True,
) -> FeederModel:
    aliases = dict(aliases or {})
    network_id = dataset.resolve_feeder(selector)
    name = network_id.rsplit('_', 1)[-1]
    source = dataset.sources.get(network_id)
    if source is None:
        raise ModelBuildError(f'{network_id}: source not found')
    source_node = source.get('NodeID', '')
    if not source_node:
        raise ModelBuildError(f'{network_id}: SOURCE.NodeID is empty')
    nominal_kv = _float(source.get('DesiredVoltage'), float('nan'))
    if not math.isfinite(nominal_kv) or nominal_kv <= 0:
        raise ModelBuildError(f'{network_id}: invalid SOURCE.DesiredVoltage={source.get("DesiredVoltage")!r}')

    _, by_code = _catalog(dataset)
    lines: list[Line] = []
    used_types: dict[str, LineType] = {}
    unresolved: set[str] = set()
    applied_aliases: dict[str, str] = {}
    used_nodes: set[str] = {source_node}

    for section_id in dataset.feeders[network_id]:
        sec = dataset.sections[section_id]
        cfg = dataset.line_configurations.get(section_id)
        if cfg is None:
            raise ModelBuildError(f'{network_id}: missing LINE CONFIGURATION for {section_id}')
        from_node = sec.get('FromNodeID', '')
        to_node = sec.get('ToNodeID', '')
        if from_node not in dataset.nodes or to_node not in dataset.nodes:
            raise ModelBuildError(f'{network_id}: {section_id} references missing node')
        overhead = cfg.get('Overhead', '1') == '1'
        raw_code = cfg.get('LineCableID') or 'DEFAULT'
        typ, alias_target = _resolve_type(raw_code, overhead, by_code, aliases)
        if typ is None:
            unresolved.add(raw_code)
            continue
        if alias_target is not None:
            applied_aliases[raw_code] = alias_target
        length_m = _float(cfg.get('Length'), float('nan'))
        if not math.isfinite(length_m) or length_m < 0:
            raise ModelBuildError(f'{network_id}: invalid length on {section_id}: {cfg.get("Length")!r}')
        line = Line(
            section_id=section_id,
            from_node=from_node,
            to_node=to_node,
            phase=sec.get('Phase') or 'ABC',
            type_key=typ.key,
            source_type_code=raw_code,
            length_m=length_m,
            overhead=overhead,
        )
        lines.append(line)
        used_types[typ.key] = typ
        used_nodes.update((from_node, to_node))

    if unresolved and strict:
        raise UnresolvedLineTypesError(name, unresolved)

    section_by_id = {line.section_id: line for line in lines}
    loads: list[Load] = []
    for key, row in dataset.customer_loads.items():
        section_id, device_number = key
        if dataset.section_owner.get(section_id) != network_id:
            continue
        line = section_by_id.get(section_id)
        if line is None:
            if strict:
                raise ModelBuildError(f'{network_id}: load {device_number} is on an unresolved section {section_id}')
            continue
        placement = dataset.load_placements.get(key)
        if placement is None:
            if strict:
                raise ModelBuildError(f'{network_id}: load placement missing for {section_id}/{device_number}')
            continue
        location = placement.get('Location', '')
        node_id = _load_node(location, line, strict)
        if node_id is None:
            continue
        p_mw, q_mvar, pf = _calc_p_q(row)
        customer_number = row.get('CustomerNumber', '')
        sed_code = extract_sed_code(customer_number, device_number, section_id)
        display = sed_loc_name(sed_code) if sed_code else (customer_number or device_number or section_id)
        loads.append(Load(
            section_id=section_id,
            device_number=device_number,
            customer_number=customer_number,
            location=location,
            node_id=node_id,
            p_mw=p_mw,
            q_mvar=q_mvar,
            pf=pf,
            connected_kva=_float(row.get('ConnectedKVA')),
            kwh=_float(row.get('KWH')),
            phase=row.get('Phase', ''),
            sed_code=sed_code,
            display_name=display[:40],
        ))

    loads = _assign_load_display_names(loads)

    seds: list[Sed] = []
    for load in loads:
        if not load.sed_code:
            continue
        seds.append(Sed(
            code=load.sed_code,
            loc_name=(load.display_name or sed_loc_name(load.sed_code))[:40],
            node_id=load.node_id,
            design_kva=load.connected_kva,
            section_id=load.section_id,
            device_number=load.device_number,
            load_key=(load.section_id, load.device_number),
        ))

    devices: list[SwitchingDevice] = []
    for kind, rows in (
        ('SWITCH', dataset.switch_settings),
        ('SECTIONALIZER', dataset.sectionalizer_settings),
    ):
        for row in rows:
            section_id = row.get('SectionID', '')
            if dataset.section_owner.get(section_id) != network_id:
                continue
            line = section_by_id.get(section_id)
            if line is None:
                if strict:
                    raise ModelBuildError(f'{network_id}: {kind} is on unresolved section {section_id}')
                continue
            location = row.get('Location', '')
            side = _device_side(location, section_id, strict)
            if side is None:
                continue
            node_id = line.from_node if side == 0 else line.to_node
            status = _int(row.get('Status'), 1)
            if status not in (0, 1):
                raise ModelBuildError(f'{section_id}: invalid switching Status={row.get("Status")!r}')
            devices.append(SwitchingDevice(
                kind=kind,
                section_id=section_id,
                location=location.upper(),
                terminal_side=side,
                node_id=node_id,
                eq_id=row.get('EqID', ''),
                eq_number=row.get('EqNumber', ''),
                phase=row.get('EqPhase', ''),
                on_off=status,
                locked=_int(row.get('Locked'), 0),
                eq_state=_int(row.get('EqState'), 0),
            ))

    nodes: dict[str, Node] = {}
    for node_id in sorted(used_nodes):
        raw = dataset.nodes[node_id]
        x = _float(raw.get('CoordX'), float('nan'))
        y = _float(raw.get('CoordY'), float('nan'))
        nodes[node_id] = Node(
            node_id=node_id,
            x=x if math.isfinite(x) else None,
            y=y if math.isfinite(y) else None,
        )

    warnings: list[str] = []
    if unresolved:
        warnings.append('Unresolved line types omitted in non-strict mode: ' + ', '.join(sorted(unresolved)))
    if any(d.eq_state != 0 for d in devices):
        warnings.append('One or more switching devices have EqState != 0; EqState is preserved in the model but DGS StaSwitch has no equivalent field in this profile.')

    return FeederModel(
        name=name,
        network_id=network_id,
        nominal_kv=nominal_kv,
        source_node=source_node,
        nodes=nodes,
        lines=lines,
        loads=loads,
        devices=devices,
        line_types=used_types,
        line_type_aliases=applied_aliases,
        unresolved_line_types=unresolved,
        warnings=warnings,
        section_by_id=section_by_id,
        seds=seds,
    )
