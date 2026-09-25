from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict, deque
import math
import re
from typing import Mapping, Sequence

from .dataset import CymdistDataset
from .dataset import (TABLAS_TIPOS_AEREO, TABLAS_TIPOS_LINEA,
                       TABLAS_TIPOS_SUBTERRANEO)
from .naming import feeder_short_name

# Optional equipment/substation suffix in customer/device IDs (utility-specific
# coding). Matches a trailing token like SE40699, M40699, TR12, SUB-01 — not
# limited to one company's SE_/M_ convention.
_EQUIP_SUFFIX_RE = re.compile(r'(?:^|[_/\-])(([A-Za-z]{1,8})\d[\w-]*)\s*$')


class ModelBuildError(ValueError):
    pass


class IslandWithLoadsError(ModelBuildError):
    """Hay carga eléctricamente inalcanzable desde el SOURCE.

    Lleva la isla estructurada en ``islands`` para que el lote y la interfaz puedan
    mostrar qué tramos y cargas están afectados sin volver a analizar la topología.
    """

    def __init__(self, feeder: str, islands: dict, message: str):
        self.feeder = feeder
        self.islands = islands
        super().__init__(message)


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
    # Posición deducida del grafo (igea_dgs.coordenadas), no leída del TXT. Sirve para
    # dibujar; no para medir: un tramo con un extremo inferido conserva su Length.
    coord_inferida: bool = False


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
    txt_length_m: float | None = None
    length_source: str = 'txt'  # 'txt' | 'georef'

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
    customers: int = 0
    """Suministros que dependen de esta carga (NumberOfCustomer del CARGA).

    Es el denominador de SAIFI y SAIDI: los índices de la NTCSE se ponderan por
    cliente, no por carga. Sin este número, el análisis de fiabilidad de PowerFactory
    devuelve índices que no son los que la norma define.
    """
    customer_type: str = ''
    """Tipo de suministro (CustomerType). Va a ElmLod.classif y sirve para agrupar
    resultados por tipo de cliente, que es como el VAD los pide."""
    year: int = 0
    """Año de alta del suministro. Único apoyo del export para la proyección."""


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


@dataclass(frozen=True)
class Coupler:
    """Interruptor entre dos barras, sin tramo de línea que lo sostenga (``ElmCoup``).

    Nace de un tramo «puente» de CYMDIST —un ``DEFAULT`` de 2 m que solo existe para
    colgar un seccionador— cuando ese tramo se funde (ver :mod:`igea_dgs.puentes`). El
    seccionador no se pierde: pasa a ser un elemento propio entre las dos barras, que
    es como PowerFactory modela una maniobra sin línea.
    """

    name: str
    node_a: str
    node_b: str
    on_off: int
    kind: str
    eq_id: str
    eq_number: str
    section_id: str
    phase: str


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
    # Elementos sin camino al SOURCE (ver find_topology_islands). Vacío = red conexa.
    islands: dict = field(default_factory=dict)
    # Relleno solo cuando el modelo es la unión de varios alimentadores en una sola
    # red (ver igea_dgs.combine). Entonces la tensión ya no es única —conviven 10 kV y
    # 22,9 kV— y hay una fuente por alimentador en lugar de una sola. Va en un campo
    # aparte para que un modelo de un alimentador siga siendo idéntico a lo que era.
    combined: object | None = None
    # Interruptores entre barras sin tramo propio (ver Coupler). Vacío salvo que se
    # hayan fundido los tramos puente.
    couplers: list[Coupler] = field(default_factory=list)
    # Tramos punta hasta esta longitud no se dibujan (quedan en el modelo eléctrico):
    # a escala real son polvo. Negativo = dibujar todos (ver dgs.diagram_line_sections).
    diagram_max_stub_m: float = 1.0
    # Hoja normalizada (``A0``…) en la que encajar el diagrama. None = escala NA205
    # (2,08 u/m, hoja a la medida de la red). Ver dgs._diagram_mapper_hoja.
    diagram_sheet: str | None = None


#: Código de fase de CYMDIST → letras. **No es una máscara de bits**: el 7 no es
#: «1|2|4», es el séptimo valor de una enumeración. Tratarlo como máscara da ABC para
#: el 7 por casualidad y disparates para el 4, el 5 y el 6.
#:
#: Vive aquí, y no en el lector de Access, porque las dos vías de entrada —el TXT y la
#: base— traen el mismo código y deben decodificarlo igual. Tenerlo en un solo sitio es
#: lo que evita que una de las dos se desvíe sin que nadie lo note.
PHASE_CODES = {1: 'A', 2: 'B', 3: 'C', 4: 'AB', 5: 'AC', 6: 'BC', 7: 'ABC'}

#: Orden de fases de PowerFactory: r, s, t ≙ A, B, C.
FASES_PF = ('A', 'B', 'C')


def decode_phase(code) -> str:
    """Código de fase de CYMDIST → las letras que usa el resto del motor.

    Acepta ya el resultado decodificado ('ABC') para que dé igual si el dato viene del
    TXT en crudo o de una capa que ya lo tradujo.
    """
    if isinstance(code, str):
        limpio = code.strip().upper()
        if limpio in set(PHASE_CODES.values()):
            return limpio
    try:
        return PHASE_CODES.get(int(code), '')
    except (TypeError, ValueError):
        return ''


def split_by_phase(total: float, phase: str) -> tuple[float, float, float]:
    """Reparte una potencia entre las fases (r, s, t) que la carga de verdad ocupa.

    Una carga monofásica escrita como trifásica equilibrada reparte su corriente entre
    tres conductores en lugar de uno: subestima la caída de tensión de ese ramal y borra
    el desequilibrio, que es justo uno de los parámetros que el TdR del VAD manda
    evaluar. Con fase desconocida se reparte entre las tres, que es lo que se venía
    haciendo para todo.
    """
    letras = decode_phase(phase) or 'ABC'
    activas = [f for f in FASES_PF if f in letras] or list(FASES_PF)
    por_fase = total / len(activas)
    return tuple(por_fase if f in activas else 0.0 for f in FASES_PF)  # type: ignore[return-value]


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


def _tension_de_fuente(source: Mapping[str, str]) -> float:
    """Tensión nominal de la fuente en kV entre fases, de donde la traiga el export.

    Los dos exports de CYMDIST que se han visto la dan de forma distinta:

    * el reducido, en ``DesiredVoltage``, ya entre fases (``10.0``);
    * el completo, en ``OperatingVoltageA/B/C``, **entre fase y neutro**
      (``5.773503``, que es 10/√3).

    Sin esto, el export completo abortaba con «invalid SOURCE.DesiredVoltage=None» en
    los 96 alimentadores. Tomar el valor fase-neutro sin multiplicar sería peor que
    fallar: el modelo se construiría entero a 5,77 kV y convergería.
    """
    entre_fases = _float(source.get('DesiredVoltage'), float('nan'))
    if math.isfinite(entre_fases) and entre_fases > 0:
        return entre_fases
    fase_neutro = [
        v for v in (
            _float(source.get(f'OperatingVoltage{f}'), float('nan')) for f in 'ABC')
        if math.isfinite(v) and v > 0
    ]
    if fase_neutro:
        return max(fase_neutro) * math.sqrt(3.0)
    return float('nan')


def _line_type_from_row(table: str, row: Mapping[str, str]) -> LineType:
    code = row.get('ID', '')
    prefix = 'CABLE' if table in TABLAS_TIPOS_SUBTERRANEO else 'LINE'
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
    for table in TABLAS_TIPOS_LINEA:
        for row in dataset.equipment_tables.get(table, ()):
            code = row.get('ID', '')
            if not code:
                continue
            typ = _line_type_from_row(table, row)
            by_key[typ.key] = typ
            by_code.setdefault(code, []).append(typ)
    return by_key, by_code


def _shared_prefix_len(a: str, b: str) -> int:
    n = 0
    for left, right in zip(a, b):
        if left != right:
            break
        n += 1
    return n


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _code_number(code: str) -> int | None:
    matches = re.findall(r'\d+', code)
    if not matches:
        return None
    return int(matches[-1])


def suggest_catalog_code(raw_code: str, catalog_codes: Sequence[str]) -> str | None:
    """Pick a unique nearest ID from the loaded BD_Equipo catalog, or None if ambiguous/absent."""
    if raw_code in catalog_codes:
        return raw_code
    scored: list[tuple[int, int, str]] = []
    for code in catalog_codes:
        prefix = _shared_prefix_len(raw_code, code)
        if prefix < 4:
            continue
        scored.append((prefix, _edit_distance(raw_code, code), code))
    if not scored:
        return None
    # Prefer longer shared prefix, then smaller edit distance.
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_prefix, best_edit, _ = scored[0]
    ties = [c for p, e, c in scored if p == best_prefix and e == best_edit]
    if len(ties) == 1:
        return ties[0]
    # Break remaining ties with numeric closeness (AA05001D -> AA05002D, not DEFAULT).
    raw_num = _code_number(raw_code)
    if raw_num is None:
        return None
    ranked: list[tuple[int, str]] = []
    for code in ties:
        num = _code_number(code)
        if num is None:
            continue
        ranked.append((abs(num - raw_num), code))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    best_delta = ranked[0][0]
    nearest = [code for delta, code in ranked if delta == best_delta]
    return nearest[0] if len(nearest) == 1 else None


def _pick_type(
    code: str,
    overhead: bool,
    by_code: dict[str, list[LineType]],
) -> LineType | None:
    candidates = by_code.get(code, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    deseadas = TABLAS_TIPOS_AEREO if overhead else TABLAS_TIPOS_SUBTERRANEO
    for tabla in deseadas:
        for candidate in candidates:
            if candidate.source_table == tabla:
                return candidate
    return None


def _resolve_type(
    raw_code: str,
    overhead: bool,
    by_code: dict[str, list[LineType]],
    aliases: Mapping[str, str],
) -> tuple[LineType | None, str | None]:
    """Resolve a LineCableID using explicit aliases, exact catalog ID, nearest catalog ID, then DEFAULT.

    Never leaves a section without a type when BD_Equipo contains DEFAULT (or a near match).
    Auto-aliases and DEFAULT fallbacks are returned via the second tuple element for audit.
    """
    requested = aliases.get(raw_code, raw_code)
    typ = _pick_type(requested, overhead, by_code)
    if typ is not None:
        return typ, aliases.get(raw_code)

    auto = suggest_catalog_code(raw_code, list(by_code))
    if auto is not None and auto != raw_code:
        typ = _pick_type(auto, overhead, by_code)
        if typ is not None:
            return typ, auto

    default_typ = _pick_type('DEFAULT', overhead, by_code)
    if default_typ is not None:
        return default_typ, 'DEFAULT'
    return None, aliases.get(raw_code)


def _calc_p_q(row: Mapping[str, str]) -> tuple[float, float, float]:
    value_type = row.get('ValueType', '')
    value1 = _float(row.get('Value1'))
    value2 = _float(row.get('Value2'))
    # CYMDIST guarda el factor de potencia EN PORCENTAJE (97.0), tanto en la base como
    # en el export TXT. Solo se aceptaba en por unidad, así que un 97 no pasaba el
    # filtro y todas las cargas salían con Q = 0: el flujo daba tensiones optimistas y
    # pérdidas reactivas nulas sin ningún aviso.
    if value_type == '2' and 1 < abs(value2) <= 100:
        value2 = value2 / 100.0
    if value_type == '2' and 0 < abs(value2) <= 1:
        p_mw = value1 / 1000.0
        pf = min(max(abs(value2), 1e-12), 1.0)
        q_mvar = abs(p_mw) * math.tan(math.acos(pf))
        if value2 < 0:
            q_mvar = -q_mvar
        return p_mw, q_mvar, pf
    return value1 / 1000.0, 0.0, abs(value2) if 0 < abs(value2) <= 1 else 0.0


#: Hasta qué longitud de tramo se acepta una carga declarada en el punto medio
#: (``Location='2'``) colgándola del nudo final. PowerFactory no tiene nudo a mitad de
#: línea, así que la alternativa sería partir el tramo y cambiar la topología.
#:
#: El umbral no es arbitrario. En el export completo de la distribuidora las 7.287
#: cargas con ``Location='2'`` están **todas** sobre derivaciones virtuales de 0,300 m
#: —mínimo y máximo coinciden—, de modo que el punto medio dista 0,15 m del extremo:
#: unos 6·10⁻⁵ Ω en cable de 120 mm². A 10 m sigue siendo 2·10⁻³ Ω, despreciable. Por
#: encima de eso el atajo dejaría de ser inocuo y es mejor fallar que falsear.
LARGO_MAXIMO_CARGA_CENTRAL_M = 10.0


def _load_node(location: str, line: Line, strict: bool) -> str | None:
    if location == '0':
        return line.from_node
    if location == '1':
        return line.to_node
    if location == '2':
        # Punto medio del tramo. Ver LARGO_MAXIMO_CARGA_CENTRAL_M.
        if line.length_km * 1000.0 <= LARGO_MAXIMO_CARGA_CENTRAL_M:
            return line.to_node
        if strict:
            raise ModelBuildError(
                f'{line.section_id}: la carga está declarada en el punto medio '
                f'(LOADS.Location=2) de un tramo de {line.length_km * 1000:.1f} m. '
                f'Por encima de {LARGO_MAXIMO_CARGA_CENTRAL_M:.0f} m colgarla de un '
                f'extremo falsearía la caída de tensión; habría que partir el tramo.')
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
    """Return an optional equipment/substation code embedded in TXT identifiers.

    This is a best-effort heuristic for any utility coding. If nothing matches,
    loads keep their original customer/device names — conversion never depends
    on a specific company denomination.
    """
    for raw in candidates:
        text = (raw or '').strip()
        if not text:
            continue
        match = _EQUIP_SUFFIX_RE.search(text)
        if match:
            return match.group(1)
    return ''


def sed_loc_name(code: str) -> str:
    """Short display name for an optional equipment/substation code."""
    return (code or '').strip()[:40]


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


def _reachable_from_source(source_node: str, lines: list[Line]) -> set[str]:
    adj: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        adj[line.from_node].add(line.to_node)
        adj[line.to_node].add(line.from_node)
    seen = {source_node}
    queue: deque[str] = deque([source_node])
    while queue:
        node = queue.popleft()
        for neighbor in adj[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen


def _intermediate_seq(value: str | None) -> tuple[int, str]:
    try:
        return int(value or '0'), value or ''
    except ValueError:
        return 10**9, value or ''


def _polyline_length_m(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def _section_projected_path(
    dataset: CymdistDataset,
    section_id: str,
    from_node: str,
    to_node: str,
    nodes: Mapping[str, Node],
    *,
    intermediate_by_section: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
) -> list[tuple[float, float]] | None:
    """Projected (CoordX, CoordY) polyline: FromNode → intermediate → ToNode.

    Returns None when either electrical end lacks finite georeferenced coordinates.
    """
    start = nodes.get(from_node)
    end = nodes.get(to_node)
    if start is None or end is None:
        return None
    if start.x is None or start.y is None or end.x is None or end.y is None:
        return None
    if start.coord_inferida or end.coord_inferida:
        # Una posición deducida del grafo no mide nada: vale la longitud del TXT.
        return None
    path: list[tuple[float, float]] = [(start.x, start.y)]
    if intermediate_by_section is None:
        rows = list(dataset.intermediate_by_section.get(section_id, ()))
    else:
        rows = list(intermediate_by_section.get(section_id, ()))
    for row in sorted(rows, key=lambda r: _intermediate_seq(r.get('SeqNumber'))):
        x = _float(row.get('CoordX'), float('nan'))
        y = _float(row.get('CoordY'), float('nan'))
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        path.append((x, y))
    path.append((end.x, end.y))
    return path


def apply_georeferenced_lengths(model: FeederModel, dataset: CymdistDataset) -> FeederModel:
    """Replace LINE CONFIGURATION lengths with polyline meters from georeferenced nodes.

    Uses NODE.CoordX/Y (projected CRS, typically metres) plus INTERMEDIATE NODES when
    present. Sections without coordinates keep the TXT length.
    """
    intermediate_by_section = dataset.intermediate_by_section

    new_lines: list[Line] = []
    updated = 0
    kept_txt = 0
    for line in model.lines:
        txt_m = line.txt_length_m if line.txt_length_m is not None else line.length_m
        path = _section_projected_path(
            dataset,
            line.section_id,
            line.from_node,
            line.to_node,
            model.nodes,
            intermediate_by_section=intermediate_by_section,
        )
        if path is None:
            new_lines.append(Line(
                **{**line.__dict__, 'txt_length_m': txt_m, 'length_source': 'txt'},
            ))
            kept_txt += 1
            continue
        geo_m = _polyline_length_m(path)
        if not math.isfinite(geo_m) or geo_m < 0:
            new_lines.append(Line(
                **{**line.__dict__, 'txt_length_m': txt_m, 'length_source': 'txt'},
            ))
            kept_txt += 1
            continue
        new_lines.append(Line(
            section_id=line.section_id,
            from_node=line.from_node,
            to_node=line.to_node,
            phase=line.phase,
            type_key=line.type_key,
            source_type_code=line.source_type_code,
            length_m=geo_m,
            overhead=line.overhead,
            txt_length_m=txt_m,
            length_source='georef',
        ))
        updated += 1

    model.lines = new_lines
    model.section_by_id = {line.section_id: line for line in new_lines}
    if updated:
        model.warnings.append(
            f'Longitudes de {updated} tramo(s) MT actualizadas desde nodos georreferenciados '
            f'(FromNode/ToNode + intermedios); {kept_txt} conservaron Length del TXT.'
        )
    return model


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return float('nan')
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def check_length_scale_agreement(
    model: FeederModel,
    *,
    warn_band: tuple[float, float] = (0.8, 1.25),
    error_band: tuple[float, float] = (0.1, 10.0),
) -> dict:
    """Compare georeferenced lengths against the TXT ``Length`` of the same sections.

    An independent scale oracle. ``assert_metre_source_crs`` checks what the CRS
    *declares*; this checks what the coordinates actually *are*. They catch
    different faults: coordinates supplied in centimetres, or a TXT ``Length`` in
    feet, pass the CRS check and fail here.

    A legitimate export can differ by some percent (sag, slack, as-built vs
    as-drawn), so only an order-of-magnitude divergence is treated as an error —
    that can only be a unit or projection mistake, never physical.
    """
    # Degenerate stubs whose two endpoints share the same coordinates measure 0 m by
    # geometry; their TXT Length is the only information available, so comparing them
    # would only add a meaningless 0.0 ratio.
    ratios = [
        line.length_m / line.txt_length_m
        for line in model.lines
        if line.length_source == 'georef'
        and line.txt_length_m is not None
        and line.txt_length_m > 0
        and math.isfinite(line.length_m)
        and line.length_m > 0
    ]
    compared = len(ratios)
    if not compared:
        return {
            'compared': 0, 'median_ratio': None, 'mad': None,
            'outside_warn_band': 0, 'ok': True, 'error': None, 'warning': None,
        }

    median_ratio = _median(ratios)
    mad = _median([abs(r - median_ratio) for r in ratios])
    outside = sum(1 for r in ratios if not (warn_band[0] <= r <= warn_band[1]))

    detail = (
        f'{compared} tramo(s) comparados: razón georreferencia/TXT mediana '
        f'{median_ratio:.4g} (MAD {mad:.3g}); {outside} fuera de '
        f'[{warn_band[0]:g}, {warn_band[1]:g}]'
    )
    error = None
    warning = None
    if not (error_band[0] <= median_ratio <= error_band[1]):
        error = (
            f'Escala de coordenadas incoherente con las longitudes del TXT. {detail}. '
            'Una discrepancia de este orden solo puede venir de unidades o proyección '
            'equivocadas (p. ej. CoordX/CoordY en grados o centímetros, o Length en '
            'otra unidad), no de holgura física. Revise --source-crs y las unidades '
            'del export antes de usar el modelo.'
        )
    elif outside:
        warning = f'Longitudes georreferenciadas y del TXT no coinciden en todos los tramos. {detail}.'

    return {
        'compared': compared,
        'median_ratio': median_ratio,
        'mad': mad,
        'outside_warn_band': outside,
        'ok': error is None,
        'error': error,
        'warning': warning,
    }


def prove_mt_connections(
    model: FeederModel,
    dataset: CymdistDataset,
    *,
    require_coordinates: bool = True,
) -> dict:
    """Prove each MT section matches TXT From/To and each SED matches TXT Location.

    Topology is always proven. ``require_coordinates`` controls only the
    georeferencing part: with geography disabled an export without CoordX/CoordY
    must still convert, so missing coordinates are counted instead of failing.
    """
    errors: list[str] = []
    line_ok = 0
    sed_ok = 0
    georef_lengths = 0
    lines_without_coords = 0
    seds_without_coords = 0

    for line in model.lines:
        sec = dataset.sections.get(line.section_id)
        if sec is None:
            errors.append(f'{line.section_id}: SECTION ausente en RED')
            continue
        txt_from = sec.get('FromNodeID', '')
        txt_to = sec.get('ToNodeID', '')
        if line.from_node != txt_from or line.to_node != txt_to:
            errors.append(
                f'{line.section_id}: From/To del modelo ({line.from_node}->{line.to_node}) '
                f'no coinciden con TXT ({txt_from}->{txt_to})'
            )
            continue
        start = model.nodes.get(line.from_node)
        end = model.nodes.get(line.to_node)
        if start is None or end is None:
            errors.append(f'{line.section_id}: nodos From/To no están en el modelo')
            continue
        if start.x is None or start.y is None:
            if require_coordinates:
                errors.append(f'{line.section_id}: FromNode {line.from_node} sin CoordX/CoordY georreferenciadas')
                continue
            lines_without_coords += 1
            continue
        if end.x is None or end.y is None:
            if require_coordinates:
                errors.append(f'{line.section_id}: ToNode {line.to_node} sin CoordX/CoordY georreferenciadas')
                continue
            lines_without_coords += 1
            continue
        line_ok += 1
        if line.length_source == 'georef':
            georef_lengths += 1

    loads_by_key = {(load.section_id, load.device_number): load for load in model.loads}
    for sed in model.seds:
        placement = dataset.load_placements.get(sed.load_key)
        if placement is None:
            errors.append(f'SED {sed.code}: falta LOADS.Location para {sed.load_key}')
            continue
        line = model.section_by_id.get(sed.section_id)
        if line is None:
            errors.append(f'SED {sed.code}: tramo {sed.section_id} no está en el alimentador')
            continue
        location = placement.get('Location', '')
        expected = _load_node(location, line, strict=False)
        if expected is None:
            errors.append(
                f'SED {sed.code}: LOADS.Location={location!r} inválida en {sed.section_id} '
                f'(debe ser 0=FromNode o 1=ToNode)'
            )
            continue
        if sed.node_id != expected:
            errors.append(
                f'SED {sed.code}: conectada a {sed.node_id} pero TXT Location={location} '
                f'exige {expected} (sección {sed.section_id})'
            )
            continue
        load = loads_by_key.get(sed.load_key)
        if load is not None and load.node_id != sed.node_id:
            errors.append(
                f'SED {sed.code}: carga {sed.device_number} en nodo {load.node_id} '
                f'difiere del nodo SED {sed.node_id}'
            )
            continue
        node = model.nodes.get(sed.node_id)
        if node is None or node.x is None or node.y is None:
            if require_coordinates:
                errors.append(f'SED {sed.code}: nodo {sed.node_id} sin georreferencia CoordX/CoordY')
                continue
            seds_without_coords += 1
            continue
        sed_ok += 1

    return {
        'ok': not errors,
        'errors': errors,
        'lines_checked': line_ok,
        'lines_total': len(model.lines),
        'seds_checked': sed_ok,
        'seds_total': len(model.seds),
        'lines_with_georef_length': georef_lengths,
        'lines_without_coords': lines_without_coords,
        'seds_without_coords': seds_without_coords,
        'coordinates_required': require_coordinates,
        'errors_total': len(errors),
    }


def find_topology_islands(
    source_node: str,
    lines: list[Line],
    loads: list[Load],
    seds: list[Sed],
) -> dict:
    """Elementos del alimentador sin ningún camino eléctrico hasta el SOURCE.

    Devuelve la isla de forma **estructurada**, no como texto: quien decide la política
    necesita saber si la isla arrastra cargas. Una isla vacía suele ser ruido del GIS
    (un fragmento dibujado y nunca conectado); una isla **con cargas** es un error de
    modelo, porque esas cargas no pueden recibir energía y PowerFactory las presenta a
    0,0 p.u. como si fuese un resultado válido.
    """
    if not lines:
        return {'sections': [], 'nodes': [], 'loads': [], 'seds': [], 'has_loads': False}
    reachable = _reachable_from_source(source_node, lines)
    island_lines = [
        line for line in lines
        if line.from_node not in reachable or line.to_node not in reachable
    ]
    if not island_lines:
        return {'sections': [], 'nodes': [], 'loads': [], 'seds': [], 'has_loads': False}
    island_nodes = sorted({
        node
        for line in island_lines
        for node in (line.from_node, line.to_node)
        if node not in reachable
    })
    island_loads = sorted(load.device_number for load in loads if load.node_id not in reachable)
    island_seds = sorted(sed.code for sed in seds if sed.node_id not in reachable)
    return {
        'sections': sorted(line.section_id for line in island_lines),
        'nodes': island_nodes,
        'loads': island_loads,
        'seds': island_seds,
        'has_loads': bool(island_loads or island_seds),
    }


def describe_islands(name: str, source_node: str, islands: dict) -> str:
    """Mensaje legible de una isla, para aviso o para error."""
    sections = islands['sections']
    sample = ', '.join(sections[:8])
    more = '' if len(sections) <= 8 else f' (+{len(sections) - 8} más)'
    detalle = (
        f'{name}: {len(sections)} tramo(s), {len(islands["nodes"])} nodo(s), '
        f'{len(islands["loads"])} carga(s) y {len(islands["seds"])} SED desconectados '
        f'del SOURCE ({source_node}). Revise SECTION/FromNode/ToNode en el RED. '
        f'Ejemplos: {sample}{more}'
    )
    if islands['has_loads']:
        return (
            detalle + ' Esas cargas no pueden recibir energía: PowerFactory las '
            'importará en servicio y su flujo devolverá 0,0 p.u. como si fuese un '
            'resultado válido. Corrija la topología del RED, o convierta con '
            '--non-strict aceptando que el modelo tiene carga no alimentable.'
        )
    return detalle + ' La isla no arrastra cargas ni SED; se convierte igualmente.'


def build_feeder_model(
    dataset: CymdistDataset,
    selector: str,
    *,
    aliases: Mapping[str, str] | None = None,
    strict: bool = True,
    include_geography: bool = True,
) -> FeederModel:
    """Build one feeder's isolated electrical model.

    ``include_geography`` mirrors the converter flag. With geography enabled every
    node must carry CoordX/CoordY, as before. With it disabled the export may lack
    coordinates entirely and still convert: sections that *do* have them keep using
    the georeferenced polyline length, so a complete export produces exactly the
    same model either way.
    """
    aliases = dict(aliases or {})
    network_id = dataset.resolve_feeder(selector)
    name = feeder_short_name(network_id)
    source = dataset.sources.get(network_id)
    if source is None:
        raise ModelBuildError(f'{network_id}: source not found')
    source_node = source.get('NodeID', '')
    if not source_node:
        raise ModelBuildError(f'{network_id}: SOURCE.NodeID is empty')
    nominal_kv = _tension_de_fuente(source)
    if not math.isfinite(nominal_kv) or nominal_kv <= 0:
        raise ModelBuildError(
            f'{network_id}: la fuente no declara una tensión utilizable. '
            f'Se buscó DesiredVoltage y OperatingVoltageA/B/C, y se encontró '
            f'DesiredVoltage={source.get("DesiredVoltage")!r}, '
            f'OperatingVoltageA={source.get("OperatingVoltageA")!r}.')

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
            raise ModelBuildError(
                f'{network_id}: cannot resolve LineCableID {raw_code!r} and BD_Equipo has no usable DEFAULT'
            )
        if alias_target is not None:
            applied_aliases[raw_code] = alias_target
            if alias_target == 'DEFAULT' and raw_code != 'DEFAULT':
                unresolved.add(raw_code)
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
            txt_length_m=length_m,
            length_source='txt',
        )
        lines.append(line)
        used_types[typ.key] = typ
        used_nodes.update((from_node, to_node))

    # Un alimentador sin filas SECTION no es un error del export: es una cabecera
    # real (SOURCE + headnode + nodo georreferenciado) cuya red MT todavía no está
    # modelada. Se convierte igual, dibujando lo único que existe — el nodo de
    # cabecera — en vez de omitirlo. No se inventa ningún elemento.
    source_only = not lines
    if source_only and source_node not in dataset.nodes:
        raise ModelBuildError(
            f'{name}: el RED no tiene filas SECTION y el nodo de cabecera '
            f'{source_node!r} tampoco está en la tabla NODE. No hay nada que convertir '
            f'para {network_id}; revise el export IGEA.'
        )

    section_by_id = {line.section_id: line for line in lines}
    loads: list[Load] = []
    for key, row in dataset.customer_loads_by_feeder.get(network_id, ()):
        section_id, device_number = key
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
            customers=_int(row.get('NumberOfCustomer')),
            customer_type=(row.get('CustomerType') or '').strip()[:20],
            year=_int(row.get('Year')),
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
    for kind, row in dataset.switching_by_feeder.get(network_id, ()):
        section_id = row.get('SectionID', '')
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
            coord_inferida=raw.get('CoordOrigen') == 'grafo',
        )

    warnings: list[str] = []
    auto_aliased = {
        src: dst
        for src, dst in applied_aliases.items()
        if src != dst and dst != 'DEFAULT' and src not in aliases
    }
    defaulted = sorted(code for code in unresolved if applied_aliases.get(code) == 'DEFAULT')
    if auto_aliased:
        detail = ', '.join(f'{src}->{dst}' for src, dst in sorted(auto_aliased.items()))
        warnings.append(
            'Line types missing from BD_Equipo were auto-mapped to the nearest catalog ID: ' + detail
        )
    if defaulted:
        warnings.append(
            'Line types without a unique BD_Equipo match used media DEFAULT (sections kept): '
            + ', '.join(defaulted)
        )
    if any(d.eq_state != 0 for d in devices):
        warnings.append('One or more switching devices have EqState != 0; EqState is preserved in the model but DGS StaSwitch has no equivalent field in this profile.')

    if source_only:
        warnings.append(
            f'{name}: el RED solo trae la cabecera (SOURCE + nodo {source_node}) sin '
            f'filas SECTION en {network_id}. Se genera un DGS con la barra de cabecera '
            'y su red externa —lo único que el export contiene— sin tramos, cargas ni '
            'SED. NO es un alimentador modelado: no lo use para flujo ni estudios.'
        )

    # Política de islas: una isla vacía es ruido del GIS y solo se avisa; una isla
    # **con cargas** bloquea en modo estricto, porque esas cargas no pueden recibir
    # energía y nadie aguas abajo lo detecta (ver describe_islands).
    islands = find_topology_islands(source_node, lines, loads, seds)
    if islands['sections']:
        message = describe_islands(name, source_node, islands)
        if islands['has_loads'] and strict:
            raise IslandWithLoadsError(name, islands, message)
        warnings.append(message)

    model = FeederModel(
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
        islands=islands,
    )

    # Electrical lengths follow the georeferenced polyline (From + intermediates + To)
    # wherever coordinates exist; sections without them keep the TXT Length.
    apply_georeferenced_lengths(model, dataset)

    # Independent scale oracle: the coordinates must agree with the TXT lengths.
    # A wrong unit or projection shows up here even when the CRS declares metres.
    scale = check_length_scale_agreement(model)
    if scale['error']:
        if strict:
            raise ModelBuildError(f'{name}: {scale["error"]}')
        model.warnings.append(f'{name}: {scale["error"]}')
    elif scale['warning']:
        model.warnings.append(f'{name}: {scale["warning"]}')

    proof = prove_mt_connections(model, dataset, require_coordinates=include_geography)
    if proof['errors']:
        detail = '; '.join(proof['errors'][:12])
        more = '' if len(proof['errors']) <= 12 else f' (+{len(proof["errors"]) - 12} más)'
        message = (
            f'{name}: prueba de conexión MT/SED falló '
            f'({proof["errors_total"]} error(es)): {detail}{more}'
        )
        if strict:
            raise ModelBuildError(message)
        model.warnings.append(message)
    else:
        summary = (
            f'Prueba OK: {proof["lines_checked"]}/{proof["lines_total"]} tramos MT '
            f'conectados a From/To georreferenciados; '
            f'{proof["seds_checked"]}/{proof["seds_total"]} SED en el nodo TXT; '
            f'{proof["lines_with_georef_length"]} longitudes actualizadas por georreferencia.'
        )
        if proof['lines_without_coords'] or proof['seds_without_coords']:
            summary += (
                f' Sin georreferencia (geografía desactivada): '
                f'{proof["lines_without_coords"]} tramo(s) y '
                f'{proof["seds_without_coords"]} SED conservan la longitud del TXT.'
            )
        if scale['compared']:
            summary += f' Escala georreferencia/TXT: mediana {scale["median_ratio"]:.4g}.'
        model.warnings.append(summary)

    return model
