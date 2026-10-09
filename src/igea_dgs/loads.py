"""Cargas de las SED: actualización masiva y creación, por libro Excel/CSV.

Formato nativo — el de ``referencia/PA217.xlsx``, que es el que usa la empresa:

- **Una hoja por alimentador**, y el **nombre de la hoja es el alimentador**
  (``PA217``, ``IN111``, ``PA219``…). Un solo libro cubre varios alimentadores.
- Columnas: ``SED`` · ``Kw`` · ``Kvar`` · ``(kVA)`` · ``FP``.

Las cargas llegan medidas de tres formas, y cada fila trae **un par**, el que tenga:

    Kw y Kvar   → se usan tal cual
    Kw y FP     → Kvar = Kw · √(1 − FP²) / FP
    (kVA) y FP  → Kw = kVA · FP,  Kvar = kVA · √(1 − FP²)

El fichero real trae el tercer caso: ``Kw``/``Kvar`` vacías. Comprobado contra él: kVA
0,3633 con FP 0,936183 da Kw 0,3401 y Kvar 0,1277, cuyo módulo devuelve exactamente
0,3633.

Si la fila trae más de un par, tienen que coincidir: si no, es un error de fila. Antes
mandaba ``Kw``/``Kvar`` en silencio, y la plantilla venía con ``Kw``/``Kvar`` ya
rellenas con la carga actual: quien escribía solo ``(kVA)`` y ``FP`` veía que su dato
se ignoraba y la SED seguía igual. Por eso la plantilla deja vacías las columnas de
entrada y muestra la carga actual aparte, en ``Kw_actual``/``Kvar_actual``/``FP_actual``.

Una fila sin ningún valor no cambia la SED (la plantilla trae todas, y se rellenan solo
las que llegan). Una fila con ``FP = 0`` y ``kVA = 0`` escritos, que en el fichero real
son 58, deja la carga en cero y se registra como fila sin datos, no como error.

Este módulo solo lee y valida filas. Qué SED existe lo decide ``tools/cargas_pf.py``
en el proyecto de DIgSILENT; el libro lo lee ``igea_dgs.cargas_pf`` (spec 004). El cruce
con el modelo de la conversión y la plantilla rellenada con la carga actual se
retiraron con la vía vieja de tres guiones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

# Columnas del formato nativo, en su orden y con su grafía exacta.
SHEET_COLUMNS = ('SED', 'Kw', 'Kvar', '(kVA)', 'FP')
# Columnas extra que añade la plantilla generada: informativas, no obligatorias.
# La carga actual va en columnas propias, no en Kw/Kvar: si fuera en las de entrada,
# mandaría sobre el (kVA)/FP que escribe el operador.
EXTRA_COLUMNS = (
    'kVA_instalado', 'Kw_actual', 'Kvar_actual', 'FP_actual', 'accion', 'observaciones',
)
ENTRY_COLUMNS = ('Kw', 'Kvar', '(kVA)', 'FP')

# Margen para dar por iguales dos pares de la misma fila: el redondeo de una hoja a
# dos decimales (FP 0,92 por 0,9196) no es una contradicción.
CONFLICT_REL_TOL = 0.01
CONFLICT_FP_TOL = 0.01

# Nombres tolerados para cada columna. La cabecera se normaliza (minúsculas, sin
# espacios ni paréntesis) antes de buscar aquí, así que un fichero con «P (kW)» o
# «cos phi» se sigue entendiendo.
COLUMN_ALIASES = {
    'sed': 'SED', 'sedcode': 'SED', 'sed_code': 'SED', 'codigo': 'SED', 'code': 'SED',
    'kw': 'Kw', 'pkw': 'Kw', 'p': 'Kw', 'p_kw': 'Kw', 'potencia': 'Kw',
    'kvar': 'Kvar', 'qkvar': 'Kvar', 'q': 'Kvar', 'q_kvar': 'Kvar', 'reactiva': 'Kvar',
    'kva': '(kVA)', 'skva': '(kVA)', 's': '(kVA)', 's_kva': '(kVA)', 'aparente': '(kVA)',
    'fp': 'FP', 'pf': 'FP', 'cos': 'FP', 'cosphi': 'FP', 'factordepotencia': 'FP',
    'cosfi': 'FP', 'cosφ': 'FP', 'cosϕ': 'FP', 'fdp': 'FP',
    'kvainstalado': 'kVA_instalado', 'kvainst': 'kVA_instalado',
    'accion': 'accion', 'observaciones': 'observaciones', 'obs': 'observaciones',
}

ACTION_UPDATE = 'actualizar'
ACTION_SKIP = 'omitir'
VALID_ACTIONS = (ACTION_UPDATE, ACTION_SKIP, '')

SUPPORTED_SUFFIXES = ('.xlsx', '.csv')


class LoadTemplateError(ValueError):
    """El libro no se puede leer o su contenido no es utilizable."""


def _normalise(header: Any) -> str:
    text = ('' if header is None else str(header)).strip().lower()
    for ch in ' ()[]-_./\\':
        text = text.replace(ch, '')
    return text


def canonical_columns(header: Sequence[Any]) -> dict[int, str]:
    """Índice de columna → nombre canónico, tolerando variantes de grafía."""
    mapping: dict[int, str] = {}
    for index, raw in enumerate(header):
        key = _normalise(raw)
        if key in COLUMN_ALIASES:
            mapping[index] = COLUMN_ALIASES[key]
    return mapping


@dataclass(frozen=True)
class SedLoad:
    """Carga de una SED: la del modelo, o la que pide la hoja."""

    sed_code: str
    feeder: str = ''
    kw: float = 0.0
    kvar: float = 0.0
    kva: float = 0.0
    fp: float = 0.0
    installed_kva: float = 0.0
    # Identidad dentro del modelo; la hoja no la trae y se completa al cruzar.
    section_id: str = ''
    device_number: str = ''
    node_id: str = ''
    derived: bool = False          # Kw/Kvar calculados desde (kVA) y FP
    no_data: bool = False          # ni Kw/Kvar ni kVA/FP utilizables

    @property
    def p_mw(self) -> float:
        return self.kw / 1000.0

    @property
    def q_mvar(self) -> float:
        return self.kvar / 1000.0


@dataclass
class SheetRead:
    """Resultado de leer una hoja: lo utilizable, lo omitido y lo que está mal."""

    feeder: str = ''
    rows: list[SedLoad] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    no_data: list[str] = field(default_factory=list)


def _number(value: Any) -> float | None:
    text = ('' if value is None else str(value)).strip().replace(',', '.')
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return float('nan')
    return number if math.isfinite(number) else float('nan')


def _resolve_power(
    kw: float | None, kvar: float | None, kva: float | None, fp: float | None,
) -> tuple[float, float, float, float, bool, bool]:
    """Devuelve ``(kw, kvar, kva, fp, derivado, sin_datos)``.

    Pares, por orden: Kw y Kvar tal cual; Kw y FP; (kVA) y FP, que es el caso del
    fichero real. Si la fila trae más de un par, ``_power_conflict`` comprueba que
    coincidan. Sin ningún par, la carga queda en cero.
    """
    if kw is not None and kvar is None and fp is not None and 0 < fp <= 1:
        # Kw con cos φ: lo que da un medidor que no registra reactiva.
        q = kw * math.sqrt(max(1.0 - fp * fp, 0.0)) / fp
        return kw, q, math.hypot(kw, q), fp, True, kw == 0.0
    if kw is not None or kvar is not None:
        p = kw or 0.0
        q = kvar or 0.0
        s = math.hypot(p, q)
        factor = (p / s) if s > 0 else (fp or 0.0)
        return p, q, s, factor, False, (p == 0.0 and q == 0.0)
    s = kva or 0.0
    factor = fp or 0.0
    if s > 0 and 0 < factor <= 1:
        p = s * factor
        q = s * math.sqrt(max(1.0 - factor * factor, 0.0))
        return p, q, s, factor, True, False
    return 0.0, 0.0, s, factor, False, True


def _power_conflict(
    kva: float | None, fp: float | None, p: float, q: float,
) -> str | None:
    """Si la fila trae (kVA)/FP que no cuadran con la carga resuelta, dice en qué.

    Kw y Kvar ya están en ``p``/``q`` cuando vienen, así que basta mirar las otras dos.
    Un 0 en (kVA) o FP es «sin dato» en el fichero real, no un valor que comparar.
    """
    s = math.hypot(p, q)
    if s == 0.0:
        return None
    if kva and abs(s - kva) > CONFLICT_REL_TOL * max(s, kva):
        return f'(kVA)={kva:g} no coincide con Kw/Kvar, que dan {s:.4g} kVA'
    if fp and abs(p / s - fp) > CONFLICT_FP_TOL:
        return f'FP={fp:g} no coincide con Kw/Kvar, que dan FP {p / s:.4f}'
    return None


def read_sheet(header: Sequence[Any], data: Sequence[Sequence[Any]], feeder: str) -> SheetRead:
    """Lee una hoja ya materializada. Separada para poder probarla sin ficheros."""
    result = SheetRead(feeder=feeder)
    mapping = canonical_columns(header)
    if 'SED' not in mapping.values():
        raise LoadTemplateError(
            f'hoja {feeder!r}: no se encontró la columna de código de SED. '
            f'Cabecera leída: {[str(h) for h in header]}. '
            'Se esperaba una columna «SED».'
        )
    seen: dict[str, int] = {}
    for offset, values in enumerate(data):
        row_no = offset + 2                      # fila 1 = cabecera
        cell = {name: values[i] if i < len(values) else None for i, name in mapping.items()}
        code = ('' if cell.get('SED') is None else str(cell['SED'])).strip()
        if not code:
            continue                             # fila en blanco: no es un error
        if code in seen:
            result.errors.append(
                f'hoja {feeder}, fila {row_no}: SED {code!r} repetida '
                f'(ya en la fila {seen[code]})'
            )
            continue
        seen[code] = row_no
        action = ('' if cell.get('accion') is None else str(cell['accion'])).strip().lower()
        if action not in VALID_ACTIONS:
            result.errors.append(
                f'hoja {feeder}, fila {row_no}: accion={action!r} no válida '
                f'(use {ACTION_UPDATE!r}, {ACTION_SKIP!r} o vacío)'
            )
            continue
        if action == ACTION_SKIP:
            result.skipped.append(code)
            continue

        numbers = {}
        bad = False
        for name in ('Kw', 'Kvar', '(kVA)', 'FP', 'kVA_instalado'):
            value = _number(cell.get(name))
            if value is not None and math.isnan(value):
                result.errors.append(
                    f'hoja {feeder}, fila {row_no}: {name}={cell.get(name)!r} no es un número'
                )
                bad = True
                break
            numbers[name] = value
        if bad:
            continue
        fp = numbers['FP']
        if fp is not None and not (0.0 <= fp <= 1.0):
            result.errors.append(
                f'hoja {feeder}, fila {row_no}: FP={fp} fuera de [0, 1]'
            )
            continue
        for name in ('Kw', 'Kvar', '(kVA)', 'kVA_instalado'):
            if numbers[name] is not None and numbers[name] < 0:
                result.errors.append(
                    f'hoja {feeder}, fila {row_no}: {name}={numbers[name]} negativo'
                )
                bad = True
                break
        if bad:
            continue

        if all(numbers[name] is None for name in ENTRY_COLUMNS):
            # La plantilla trae todas las SED: la que se deja en blanco no se toca.
            # Ponerla en cero sería borrar la carga de todo lo que no se midió.
            continue
        kw, kvar, kva, factor, derived, no_data = _resolve_power(
            numbers['Kw'], numbers['Kvar'], numbers['(kVA)'], fp,
        )
        conflict = _power_conflict(numbers['(kVA)'], fp, kw, kvar)
        if conflict:
            result.errors.append(
                f'hoja {feeder}, fila {row_no}: {code}: {conflict}. '
                'Deje un solo par: Kw y Kvar, Kw y FP, o (kVA) y FP.'
            )
            continue
        if no_data:
            result.no_data.append(code)
        result.rows.append(SedLoad(
            sed_code=code, feeder=feeder,
            kw=kw, kvar=kvar, kva=kva, fp=factor,
            installed_kva=numbers['kVA_instalado'] or 0.0,
            derived=derived, no_data=no_data,
        ))
    return result


