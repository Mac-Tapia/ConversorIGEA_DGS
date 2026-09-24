"""Creación de cargas y SED nuevas, por formulario o por plantilla.

Unifica los módulos 2 y 4 del pedido: **crear una SED o crear varias es el mismo
problema** con una fila o con N. Lo único que cambia es de dónde salen los datos —el
formulario de la interfaz o una plantilla Excel/CSV—, y las dos vías construyen las
mismas filas :class:`NewSedLoad`, que es lo que se valida y se aplica.

Por qué la plantilla de creación pide más que la de actualización: crear una SED en
PowerFactory no es escribir tres atributos. Hay que crear ``ElmSubstat``, sus dos barras
internas (MT y BT), ``TypTr2`` + ``ElmTr2``, un ``ElmCoup`` al nodo del alimentador,
el ``ElmLod`` y cuatro ``StaCubic``. Para eso hacen falta tres datos que la carga no
lleva: **a qué nodo se conecta**, **en qué extremo** y **los kVA del transformador**.

La plantilla se precarga con las SED que la actualización masiva no reconoció
(``LoadUpdatePlan.unknown``), con su carga ya puesta: el operador no vuelve a teclear
códigos, solo indica dónde conectarlas.

Este módulo tampoco habla con PowerFactory: valida y produce el plan.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .loads import (
    SUPPORTED_SUFFIXES,
    LoadTemplateError,
    SedLoad,
    _normalise,
    _number,
    _resolve_power,
    canonical_columns,
)

CREATE_COLUMNS = (
    'SED', 'CoordX', 'CoordY', 'nodo_conexion', 'tramo', 'ubicacion',
    'kVA_instalado', 'Kw', 'Kvar', '(kVA)', 'FP', 'conductor', 'observaciones',
)

# Columnas propias de la creación, con sus variantes de grafía.
CREATE_ALIASES = {
    'nodoconexion': 'nodo_conexion', 'nodo': 'nodo_conexion', 'nodeid': 'nodo_conexion',
    'barra': 'nodo_conexion',
    'coordx': 'CoordX', 'x': 'CoordX', 'este': 'CoordX', 'easting': 'CoordX',
    'coordy': 'CoordY', 'y': 'CoordY', 'norte': 'CoordY', 'northing': 'CoordY',
    'tramo': 'tramo', 'seccion': 'tramo', 'sectionid': 'tramo', 'sec': 'tramo',
    'ubicacion': 'ubicacion', 'location': 'ubicacion', 'extremo': 'ubicacion',
    'kvainstalado': 'kVA_instalado', 'kvainst': 'kVA_instalado', 'trafo': 'kVA_instalado',
    'conductor': 'conductor', 'cable': 'conductor', 'tipolinea': 'conductor',
}

# Se puede indicar el nodo directamente, o dar CoordX/CoordY y dejar que el módulo
# busque el nodo más cercano. Una de las dos cosas es obligatoria.
REQUIRED_COLUMNS = ('SED', 'CoordX', 'CoordY', 'kVA_instalado')

# Margen sobre la corriente nominal al elegir conductor.
AMPACITY_MARGIN = 1.25
# Caída de tensión máxima admisible en la derivación, en por ciento.
MAX_VOLTAGE_DROP_PCT = 3.0


@dataclass(frozen=True)
class ConductorChoice:
    """Conductor elegido y los números que lo justifican."""

    type_key: str
    code: str
    ampacity_a: float
    current_a: float
    voltage_drop_pct: float
    length_m: float
    reason: str
    binding: str          # qué criterio decidió: 'ampacidad', 'caida', 'minimo', 'impuesto'


def find_nearest_node(model, x: float, y: float) -> tuple[str, float]:
    """Nodo del modelo más cercano al punto, y su distancia en metros.

    Las coordenadas están en el CRS proyectado del export (metros), el mismo que usa
    ``--source-crs``. Por eso la distancia euclidiana **es** metros, sin conversión.
    """
    best_node, best_d2 = '', float('inf')
    for node_id, node in model.nodes.items():
        if node.x is None or node.y is None:
            continue
        d2 = (node.x - x) ** 2 + (node.y - y) ** 2
        if d2 < best_d2:
            best_node, best_d2 = node_id, d2
    if not best_node:
        raise LoadTemplateError(
            f'{getattr(model, "name", "")}: ningún nodo del modelo tiene coordenadas, '
            'así que no se puede buscar el más cercano. Convierta con georreferenciación.'
        )
    return best_node, math.sqrt(best_d2)


def _voltage_drop_pct(
    current_a: float, length_km: float, r_ohm_km: float, x_ohm_km: float,
    fp: float, nominal_kv: float,
) -> float:
    """Caída de tensión aproximada en la derivación, en por ciento.

    ΔV = √3 · I · L · (R·cosφ + X·senφ), y el porcentaje sobre la tensión nominal.
    Es la fórmula habitual de línea corta: para una derivación de SED, de decenas o
    centenas de metros, el error de despreciar la capacitancia es irrelevante.
    """
    if nominal_kv <= 0:
        return 0.0
    cos_phi = min(max(fp if fp else 0.95, 0.0), 1.0)
    sin_phi = math.sqrt(max(1.0 - cos_phi * cos_phi, 0.0))
    drop_v = math.sqrt(3.0) * current_a * length_km * (r_ohm_km * cos_phi + x_ohm_km * sin_phi)
    return 100.0 * drop_v / (nominal_kv * 1000.0)


def select_conductor(
    model,
    *,
    kva: float,
    length_m: float,
    fp: float = 0.95,
    forced_code: str = '',
    ampacity_margin: float = AMPACITY_MARGIN,
    max_drop_pct: float = MAX_VOLTAGE_DROP_PCT,
) -> ConductorChoice:
    """Elige el conductor aéreo más adecuado para la derivación.

    Dos criterios, en este orden:

    1. **Ampacidad** — el conductor debe soportar la corriente con margen.
    2. **Caída de tensión** — la derivación no debe superar ``max_drop_pct``.

    Entre los que cumplen, gana el de **menor ampacidad**: el menos cobre, que es lo
    correcto cuando lo demás da igual.

    Un aviso honesto sobre esto: para una SED de distribución la corriente es de unos
    pocos amperios (100 kVA a 10 kV son 5,8 A) y el conductor más pequeño de un catálogo
    típico ya es de 100 A. Es decir, **en la práctica ninguno de los dos criterios
    discrimina** y sale siempre el menor del catálogo. Lo que decide de verdad es la
    normalización de la empresa, que el módulo no puede adivinar: para eso está la
    columna ``conductor``, que impone el código y se respeta sin discutir.
    """
    catalog = [
        typ for typ in model.line_types.values()
        if typ.source_table == 'LINE' and typ.ampacity_a > 0
    ]
    if not catalog:
        # El modelo solo trae los tipos que usa; si no hay aéreo, se dice claramente.
        raise LoadTemplateError(
            f'{getattr(model, "name", "")}: el modelo no tiene ningún conductor aéreo '
            'con ampacidad en su catálogo, así que no se puede elegir sección.'
        )
    length_km = max(length_m, 0.0) / 1000.0
    current = kva / (math.sqrt(3.0) * model.nominal_kv) if model.nominal_kv > 0 else 0.0

    if forced_code:
        chosen = next((t for t in catalog if t.code == forced_code), None)
        if chosen is None:
            raise LoadTemplateError(
                f'conductor {forced_code!r} no está entre los tipos aéreos del modelo '
                f'({", ".join(sorted({t.code for t in catalog})[:8])}…)'
            )
        drop = _voltage_drop_pct(current, length_km, chosen.r1_ohm_km, chosen.x1_ohm_km, fp, model.nominal_kv)
        return ConductorChoice(
            type_key=chosen.key, code=chosen.code, ampacity_a=chosen.ampacity_a,
            current_a=current, voltage_drop_pct=drop, length_m=length_m,
            reason=f'impuesto por el operador ({chosen.code})', binding='impuesto',
        )

    # DEFAULT no es un conductor: es el comodín del catálogo. No se elige solo.
    candidates = sorted(
        (t for t in catalog if t.code != 'DEFAULT'),
        key=lambda t: (t.ampacity_a, t.code),
    ) or sorted(catalog, key=lambda t: (t.ampacity_a, t.code))

    required_a = current * ampacity_margin
    por_ampacidad = [t for t in candidates if t.ampacity_a >= required_a]
    if not por_ampacidad:
        mayor = candidates[-1]
        drop = _voltage_drop_pct(current, length_km, mayor.r1_ohm_km, mayor.x1_ohm_km, fp, model.nominal_kv)
        return ConductorChoice(
            type_key=mayor.key, code=mayor.code, ampacity_a=mayor.ampacity_a,
            current_a=current, voltage_drop_pct=drop, length_m=length_m,
            reason=(
                f'ningún conductor del catálogo cubre {required_a:.1f} A '
                f'({current:.1f} A × {ampacity_margin:g}); se usa el mayor disponible'
            ),
            binding='ampacidad',
        )

    for typ in por_ampacidad:
        drop = _voltage_drop_pct(current, length_km, typ.r1_ohm_km, typ.x1_ohm_km, fp, model.nominal_kv)
        if drop <= max_drop_pct:
            binding = 'minimo' if typ is por_ampacidad[0] else 'caida'
            return ConductorChoice(
                type_key=typ.key, code=typ.code, ampacity_a=typ.ampacity_a,
                current_a=current, voltage_drop_pct=drop, length_m=length_m,
                reason=(
                    f'{current:.2f} A con margen {ampacity_margin:g} → {required_a:.1f} A; '
                    f'{typ.code} da {typ.ampacity_a:.0f} A y {drop:.3f} % de caída '
                    f'en {length_m:.1f} m'
                ),
                binding=binding,
            )

    mayor = por_ampacidad[-1]
    drop = _voltage_drop_pct(current, length_km, mayor.r1_ohm_km, mayor.x1_ohm_km, fp, model.nominal_kv)
    return ConductorChoice(
        type_key=mayor.key, code=mayor.code, ampacity_a=mayor.ampacity_a,
        current_a=current, voltage_drop_pct=drop, length_m=length_m,
        reason=(
            f'ningún conductor baja de {max_drop_pct:g} % de caída en {length_m:.1f} m; '
            f'se usa {mayor.code} con {drop:.3f} %'
        ),
        binding='caida',
    )


@dataclass(frozen=True)
class NewSedLoad:
    """SED que hay que crear: su carga, más lo necesario para anclarla a la red."""

    sed_code: str
    node_id: str = ''
    section_id: str = ''
    location: str = '1'          # '0' = FromNode del tramo, '1' = ToNode
    installed_kva: float = 0.0
    kw: float = 0.0
    kvar: float = 0.0
    kva: float = 0.0
    fp: float = 0.0
    feeder: str = ''
    derived: bool = False
    # Ubicación en el CRS proyectado del export. Si viene, el nodo de conexión y la
    # longitud de la derivación se deducen de aquí.
    coord_x: float | None = None
    coord_y: float | None = None
    conductor: str = ''          # código impuesto por el operador; vacío = se elige


@dataclass(frozen=True)
class ResolvedNewSed:
    """SED nueva ya resuelta contra la red: dónde se conecta y con qué."""

    load: NewSedLoad
    node_id: str
    distance_m: float
    conductor: ConductorChoice
    new_node_id: str
    new_section_id: str
    nearest_from_coords: bool

    @property
    def p_mw(self) -> float:
        return self.load.kw / 1000.0

    @property
    def q_mvar(self) -> float:
        return self.load.kvar / 1000.0


@dataclass
class CreatePlan:
    """Qué SED se crean, cuáles ya existen y qué filas no se pueden usar."""

    feeder: str
    create: list['ResolvedNewSed'] = field(default_factory=list)
    already_exists: list[str] = field(default_factory=list)
    row_errors: list[str] = field(default_factory=list)

    @property
    def is_applicable(self) -> bool:
        """Igual que en la actualización: o entra todo, o no entra nada."""
        return not self.row_errors and bool(self.create)

    def summary(self) -> dict:
        return {
            'feeder': self.feeder,
            'create': len(self.create),
            'already_exists': len(self.already_exists),
            'row_errors': len(self.row_errors),
            'applicable': self.is_applicable,
        }

    def report(self) -> str:
        lines = [
            f'PLAN DE CREACIÓN DE CARGAS — {self.feeder}',
            '=' * 70,
            f'  SED a crear                     : {len(self.create)}',
            f'  SED que ya existen en el modelo : {len(self.already_exists)}',
            f'  Filas con error                 : {len(self.row_errors)}',
        ]
        if self.already_exists:
            lines += ['', 'Ya existen — use la actualización masiva, no la creación:']
            lines.append('  ' + ', '.join(self.already_exists[:20]))
        if self.row_errors:
            lines += ['', 'ERRORES (no se crea nada hasta corregirlos):']
            for err in self.row_errors[:20]:
                lines.append(f'  - {err}')
            if len(self.row_errors) > 20:
                lines.append(f'  … y {len(self.row_errors) - 20} más')
        if self.create:
            lines += ['', 'A crear (primeras 10):']
            for item in self.create[:10]:
                origen = 'del punto' if item.nearest_from_coords else 'nodo indicado'
                lines.append(
                    f'  + {item.load.sed_code:14s} {item.load.installed_kva:6.0f} kVA  '
                    f'{item.load.kw:9.3f} kW / {item.load.kvar:8.3f} kvar'
                )
                lines.append(
                    f'      conecta a {item.node_id[:32]:32s} a {item.distance_m:8.1f} m ({origen})'
                )
                lines.append(
                    f'      conductor {item.conductor.code:10s} {item.conductor.ampacity_a:5.0f} A  '
                    f'I={item.conductor.current_a:6.2f} A  caída={item.conductor.voltage_drop_pct:.4f} %  '
                    f'[{item.conductor.binding}]'
                )
            bindings: dict[str, int] = {}
            for item in self.create:
                bindings[item.conductor.binding] = bindings.get(item.conductor.binding, 0) + 1
            lines += ['', 'Criterio que decidió el conductor: ' + ', '.join(
                f'{k}={v}' for k, v in sorted(bindings.items())
            )]
            if bindings.get('minimo'):
                lines.append(
                    '  «minimo» = ni la ampacidad ni la caída discriminan, y se toma el '
                    'menor del catálogo. Para una SED de distribución es lo normal: use la '
                    'columna «conductor» si su empresa tiene una sección normalizada.'
                )
        return '\n'.join(lines)


def write_create_template(
    pending: Sequence[SedLoad] | Sequence[NewSedLoad],
    path: Path | str,
    *,
    feeder: str = '',
    node_choices: Sequence[str] = (),
) -> Path:
    """Plantilla de creación, precargada con las SED pendientes.

    ``node_choices`` añade una hoja auxiliar con los nodos válidos del alimentador, para
    que el operador copie y pegue en lugar de adivinar el identificador.
    """
    out = Path(path)
    if out.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise LoadTemplateError(
            f'Extensión no soportada: {out.suffix!r}. Use ' + ' o '.join(SUPPORTED_SUFFIXES)
        )
    out.parent.mkdir(parents=True, exist_ok=True)

    def record(row) -> list[Any]:
        return [
            row.sed_code,
            getattr(row, 'coord_x', None) if getattr(row, 'coord_x', None) is not None else '',
            getattr(row, 'coord_y', None) if getattr(row, 'coord_y', None) is not None else '',
            getattr(row, 'node_id', '') or '',
            getattr(row, 'section_id', '') or '',
            getattr(row, 'location', '1') or '1',
            round(row.installed_kva, 3) if row.installed_kva else '',
            round(row.kw, 6),
            round(row.kvar, 6),
            round(row.kva, 6),
            round(row.fp, 6),
            getattr(row, 'conductor', '') or '',
            '',
        ]

    if out.suffix.lower() == '.csv':
        with out.open('w', encoding='utf-8-sig', newline='') as fh:
            writer = csv.writer(fh, delimiter=';')
            writer.writerow(list(CREATE_COLUMNS))
            writer.writerows(record(r) for r in pending)
        return out

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError as exc:
        raise LoadTemplateError(
            'La plantilla .xlsx necesita openpyxl. Instale con: '
            'pip install -r requirements.txt  — o use .csv.'
        ) from exc

    wb = Workbook()
    ws = wb.active
    title = (feeder or 'CREAR')[:31]
    for ch in ':\\/?*[]':
        title = title.replace(ch, '-')
    ws.title = title
    ws.append(list(CREATE_COLUMNS))
    for col, name in enumerate(CREATE_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True)
        # Naranja = obligatorio para poder crear; verde = datos de carga.
        cell.fill = PatternFill(
            'solid', fgColor='FCE4D6' if name in REQUIRED_COLUMNS else 'DFF0D8',
        )
        ws.column_dimensions[cell.column_letter].width = max(len(name) + 3, 14)
    for row in pending:
        ws.append(record(row))
    ws.freeze_panes = 'A2'
    if node_choices:
        ayuda = wb.create_sheet('nodos_validos')
        ayuda.append(['nodo_conexion'])
        for node in node_choices:
            ayuda.append([node])
        ayuda.column_dimensions['A'].width = 44
    wb.save(out)
    return out


def _mapping(header: Sequence[Any]) -> dict[int, str]:
    mapping = dict(canonical_columns(header))
    for index, raw in enumerate(header):
        key = _normalise(raw)
        if key in CREATE_ALIASES:
            mapping[index] = CREATE_ALIASES[key]
    return mapping


def read_create_sheet(
    header: Sequence[Any], data: Sequence[Sequence[Any]], feeder: str,
) -> tuple[list[NewSedLoad], list[str]]:
    """Lee una hoja de creación. Devuelve ``(filas, errores)``."""
    mapping = _mapping(header)
    if 'SED' not in mapping.values():
        raise LoadTemplateError(
            f'hoja {feeder!r}: falta la columna «SED». '
            f'Cabecera leída: {[str(h) for h in header]}'
        )
    rows: list[NewSedLoad] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    for offset, values in enumerate(data):
        row_no = offset + 2
        cell = {name: values[i] if i < len(values) else None for i, name in mapping.items()}
        code = ('' if cell.get('SED') is None else str(cell['SED'])).strip()
        if not code:
            continue
        if code in seen:
            errors.append(f'hoja {feeder}, fila {row_no}: SED {code!r} repetida (fila {seen[code]})')
            continue
        seen[code] = row_no

        node = ('' if cell.get('nodo_conexion') is None else str(cell['nodo_conexion'])).strip()
        coord_x = _number(cell.get('CoordX'))
        coord_y = _number(cell.get('CoordY'))
        if (coord_x is not None and math.isnan(coord_x)) or (coord_y is not None and math.isnan(coord_y)):
            errors.append(
                f'hoja {feeder}, fila {row_no}: {code} con CoordX/CoordY no numéricas '
                f'({cell.get("CoordX")!r}, {cell.get("CoordY")!r})'
            )
            continue
        tiene_punto = coord_x is not None and coord_y is not None
        if not node and not tiene_punto:
            errors.append(
                f'hoja {feeder}, fila {row_no}: {code} sin CoordX/CoordY ni nodo_conexion. '
                'Indique la ubicación del punto (preferible: se conecta al nodo más '
                'cercano) o el nodo al que se conecta.'
            )
            continue
        location = ('' if cell.get('ubicacion') is None else str(cell['ubicacion'])).strip() or '1'
        if location not in ('0', '1'):
            errors.append(
                f'hoja {feeder}, fila {row_no}: ubicacion={location!r} no válida '
                "(use '0' = FromNode o '1' = ToNode)"
            )
            continue

        numbers: dict[str, float | None] = {}
        bad = False
        # CoordX/CoordY quedan fuera: pueden ser negativas (hemisferio, husos UTM).
        for name in ('Kw', 'Kvar', '(kVA)', 'FP', 'kVA_instalado'):
            value = _number(cell.get(name))
            if value is not None and math.isnan(value):
                errors.append(
                    f'hoja {feeder}, fila {row_no}: {name}={cell.get(name)!r} no es un número'
                )
                bad = True
                break
            if value is not None and value < 0:
                errors.append(f'hoja {feeder}, fila {row_no}: {name}={value} negativo')
                bad = True
                break
            numbers[name] = value
        if bad:
            continue
        fp = numbers.get('FP')
        if fp is not None and not (0.0 <= fp <= 1.0):
            errors.append(f'hoja {feeder}, fila {row_no}: FP={fp} fuera de [0, 1]')
            continue
        if not numbers.get('kVA_instalado'):
            errors.append(
                f'hoja {feeder}, fila {row_no}: {code} sin kVA_instalado. Sin la potencia '
                'del transformador no se puede crear la SED.'
            )
            continue

        kw, kvar, kva, factor, derived, _no_data = _resolve_power(
            numbers.get('Kw'), numbers.get('Kvar'), numbers.get('(kVA)'), fp,
        )
        rows.append(NewSedLoad(
            sed_code=code, node_id=node,
            section_id=('' if cell.get('tramo') is None else str(cell['tramo'])).strip(),
            location=location,
            installed_kva=numbers['kVA_instalado'] or 0.0,
            kw=kw, kvar=kvar, kva=kva, fp=factor, feeder=feeder, derived=derived,
            coord_x=coord_x if tiene_punto else None,
            coord_y=coord_y if tiene_punto else None,
            conductor=('' if cell.get('conductor') is None else str(cell['conductor'])).strip(),
        ))
    return rows, errors


def read_create_workbook(path: Path | str) -> dict[str, tuple[list[NewSedLoad], list[str]]]:
    """Lee el libro de creación: ``{hoja: (filas, errores)}``."""
    src = Path(path)
    if not src.is_file():
        raise LoadTemplateError(f'No se encuentra el fichero: {src}')
    suffix = src.suffix.lower()

    if suffix == '.csv':
        with src.open('r', encoding='utf-8-sig', newline='') as fh:
            reader = csv.reader(fh, delimiter=';')
            try:
                header = next(reader)
            except StopIteration:
                raise LoadTemplateError(f'{src.name}: fichero vacío.') from None
            body = [r for r in reader if any((c or '').strip() for c in r)]
        return {src.stem: read_create_sheet(header, body, src.stem)}

    if suffix != '.xlsx':
        raise LoadTemplateError(
            f'Extensión no soportada: {src.suffix!r}. Use ' + ' o '.join(SUPPORTED_SUFFIXES)
        )
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise LoadTemplateError(
            'Leer .xlsx necesita openpyxl. Instale con: pip install -r requirements.txt'
        ) from exc

    wb = load_workbook(src, data_only=True, read_only=True)
    out: dict[str, tuple[list[NewSedLoad], list[str]]] = {}
    try:
        for name in wb.sheetnames:
            if name == 'nodos_validos':       # hoja auxiliar de la propia plantilla
                continue
            ws = wb[name]
            it = ws.iter_rows(values_only=True)
            try:
                header = list(next(it))
            except StopIteration:
                continue
            body = [
                list(v) for v in it
                if v and any(c is not None and str(c).strip() for c in v)
            ]
            if not body:
                continue
            try:
                out[name] = read_create_sheet(header, body, name)
            except LoadTemplateError as exc:
                out[name] = ([], [str(exc)])
    finally:
        wb.close()
    if not out:
        raise LoadTemplateError(
            f'{src.name}: ninguna hoja con datos. Se esperaba una hoja con columnas '
            + ', '.join(CREATE_COLUMNS[:5]) + '…'
        )
    return out


def single_new_load(
    *,
    sed_code: str,
    installed_kva: float,
    node_id: str = '',
    coord_x: float | None = None,
    coord_y: float | None = None,
    conductor: str = '',
    kw: float | None = None,
    kvar: float | None = None,
    kva: float | None = None,
    fp: float | None = None,
    section_id: str = '',
    location: str = '1',
    feeder: str = '',
) -> tuple[list[NewSedLoad], list[str]]:
    """Una sola carga desde el formulario de la interfaz.

    Comparte validación con la plantilla construyendo una hoja de una fila: así el
    formulario y el fichero no pueden divergir en las reglas.
    """
    header = list(CREATE_COLUMNS)
    row = [
        sed_code,
        '' if coord_x is None else coord_x,
        '' if coord_y is None else coord_y,
        node_id, section_id, location,
        '' if installed_kva is None else installed_kva,
        '' if kw is None else kw,
        '' if kvar is None else kvar,
        '' if kva is None else kva,
        '' if fp is None else fp,
        conductor,
        '',
    ]
    return read_create_sheet(header, [row], feeder or 'FORMULARIO')


def build_create_plan(
    model, rows: Sequence[NewSedLoad], errors: Sequence[str] = (),
    *,
    max_distance_m: float = 2000.0,
) -> CreatePlan:
    """Resuelve cada SED nueva contra la red y valida que se pueda crear.

    Por cada fila:

    1. La SED **no** debe existir ya (si existe, va a actualización, no a creación).
    2. El punto de conexión sale del **nodo más cercano** a ``CoordX``/``CoordY``, o del
       nodo indicado a mano si se dio.
    3. La distancia a ese nodo es la **longitud de la derivación**, y con ella se elige
       el **conductor aéreo**.

    ``max_distance_m`` es una salvaguarda: un punto a kilómetros del nodo más cercano
    suele ser un error de coordenadas (CRS equivocado, ejes invertidos), no una
    derivación larga. Bloquea en lugar de crear una línea absurda.
    """
    plan = CreatePlan(feeder=getattr(model, 'name', ''))
    plan.row_errors = list(errors)
    existentes = {sed.code for sed in model.seds}
    nodos = set(model.nodes)
    for row in rows:
        if row.sed_code in existentes:
            plan.already_exists.append(row.sed_code)
            continue

        desde_coords = False
        if row.coord_x is not None and row.coord_y is not None:
            try:
                node_id, distance = find_nearest_node(model, row.coord_x, row.coord_y)
            except LoadTemplateError as exc:
                plan.row_errors.append(f'{row.sed_code}: {exc}')
                continue
            desde_coords = True
            if row.node_id and row.node_id != node_id:
                # El operador dio nodo y coordenadas y no coinciden: manda el nodo,
                # pero se avisa porque una de las dos cosas está mal.
                if row.node_id in nodos:
                    node = model.nodes[row.node_id]
                    if node.x is not None and node.y is not None:
                        distance = math.hypot(node.x - row.coord_x, node.y - row.coord_y)
                    node_id = row.node_id
                    desde_coords = False
            if distance > max_distance_m:
                plan.row_errors.append(
                    f'{row.sed_code}: el nodo más cercano ({node_id}) está a '
                    f'{distance:.0f} m, más de {max_distance_m:.0f} m. Revise CoordX/CoordY '
                    'y el CRS: suele ser un error de coordenadas, no una derivación larga.'
                )
                continue
        elif row.node_id:
            node_id = row.node_id
            node = model.nodes.get(node_id)
            distance = 0.0
            if node is None:
                plan.row_errors.append(
                    f'{row.sed_code}: el nodo {node_id!r} no existe en {plan.feeder}. '
                    'Debe ser un nodo del modelo (vea la hoja «nodos_validos»).'
                )
                continue
        else:
            plan.row_errors.append(
                f'{row.sed_code}: sin CoordX/CoordY ni nodo_conexion. Indique la ubicación '
                'del punto (preferible) o el nodo al que se conecta.'
            )
            continue

        if node_id not in nodos:
            plan.row_errors.append(
                f'{row.sed_code}: el nodo {node_id!r} no existe en {plan.feeder}.'
            )
            continue
        if row.section_id and row.section_id not in model.section_by_id:
            plan.row_errors.append(
                f'{row.sed_code}: el tramo {row.section_id!r} no existe en {plan.feeder}.'
            )
            continue

        try:
            conductor = select_conductor(
                model,
                kva=row.installed_kva,
                length_m=distance,
                fp=row.fp or 0.95,
                forced_code=row.conductor,
            )
        except LoadTemplateError as exc:
            plan.row_errors.append(f'{row.sed_code}: {exc}')
            continue

        plan.create.append(ResolvedNewSed(
            load=row,
            node_id=node_id,
            distance_m=distance,
            conductor=conductor,
            new_node_id=f'NODE_{row.sed_code}',
            new_section_id=f'SEC_{row.sed_code}',
            nearest_from_coords=desde_coords,
        ))
    return plan


def _to_gps(points: Sequence[tuple[float, float]], source_crs: str) -> list[tuple[float, float] | None]:
    """Proyectadas → (lat, lon) WGS84, para que PowerFactory sitúe el punto en el mapa.

    Sin ``pyproj`` o sin CRS se devuelve ``None`` por punto: la SED se crea igual, solo
    que sin GPS. Perder el mapa no justifica bloquear la creación.
    """
    if not points or not source_crs:
        return [None] * len(points)
    try:
        from pyproj import Transformer
    except ImportError:
        return [None] * len(points)
    try:
        transformer = Transformer.from_crs(source_crs, 'EPSG:4326', always_xy=True)
    except Exception:
        return [None] * len(points)
    out: list[tuple[float, float] | None] = []
    for x, y in points:
        try:
            lon, lat = transformer.transform(x, y)
        except Exception:
            out.append(None)
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            out.append(None)
        else:
            out.append((lat, lon))
    return out


def create_plan_to_payload(
    plan: CreatePlan, *, nominal_kv: float, lv_kv: float = 0.22, source_crs: str = '',
) -> dict:
    """Plan de creación serializable para el proceso que habla con PowerFactory.

    ``lv_kv`` es la tensión de baja del transformador. Sale del perfil de red, no de
    aquí: 0,22 kV es el valor peruano por defecto y debe parametrizarse (Task 12 del
    plan de comercialización).
    """
    gps = _to_gps(
        [
            (item.load.coord_x or 0.0, item.load.coord_y or 0.0)
            if item.load.coord_x is not None and item.load.coord_y is not None
            else (float('nan'), float('nan'))
            for item in plan.create
        ],
        source_crs,
    )
    return {
        'feeder': plan.feeder,
        'nominal_kv': nominal_kv,
        'lv_kv': lv_kv,
        'source_crs': source_crs,
        'summary': plan.summary(),
        'create': [
            {
                'sed_code': item.load.sed_code,
                'gps_lat': gps[index][0] if gps[index] else None,
                'gps_lon': gps[index][1] if gps[index] else None,
                # Dónde se engancha y con qué: resuelto desde las coordenadas.
                'connect_to_node': item.node_id,
                'distance_m': item.distance_m,
                'nearest_from_coords': item.nearest_from_coords,
                'new_node_id': item.new_node_id,
                'new_section_id': item.new_section_id,
                'coord_x': item.load.coord_x,
                'coord_y': item.load.coord_y,
                # Conductor de la derivación, con los números que lo justifican.
                'conductor_code': item.conductor.code,
                'conductor_ampacity_a': item.conductor.ampacity_a,
                'current_a': item.conductor.current_a,
                'voltage_drop_pct': item.conductor.voltage_drop_pct,
                'conductor_reason': item.conductor.reason,
                'conductor_binding': item.conductor.binding,
                'length_km': item.distance_m / 1000.0,
                # Transformador y carga.
                'installed_kva': item.load.installed_kva,
                'strn_mva': max(item.load.installed_kva, 1.0) / 1000.0,
                'plini_mw': item.p_mw,
                'qlini_mvar': item.q_mvar,
                'coslini': item.load.fp,
                'slini_mva': math.hypot(item.p_mw, item.q_mvar),
                'derived_from_kva_fp': item.load.derived,
                'section_id': item.load.section_id,
                'location': item.load.location,
            }
            for index, item in enumerate(plan.create)
        ],
        'already_exists': plan.already_exists,
        'row_errors': plan.row_errors,
    }
