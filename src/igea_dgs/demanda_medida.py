"""Demanda medida: cabecera de alimentador y clientes importantes (spec 004, RF-22 a RF-39).

El operador preparaba las demandas cruzando a mano cuatro libros del área comercial y
de medición:

1. **Medidor por alimentador** (código de alimentador → código de medidor).
2. **Medición de cabecera**: una hoja por medidor, con un registro cada 15 min. Es la
   exportación de los medidores: columnas en cualquier orden y con nombres que cambian
   de un medidor a otro (``kW tot`` o ``kW tot mean``; ``PF sign tot us`` o ``PF lag
   mean``; a veces sin kVA). Algunos medidores salen partidos en una hoja por magnitud.
3. **Suministros**: código actual (``Suministro Act``), el anterior (``Suministro``),
   SED y radial.
4. **Clientes importantes del mes**, hoja resumen, en dos formatos: ``Nis/EA/ERI/Pot``
   (hasta abril) y ``SUMINISTRO/EA_TOTAL/ERI_TOTAL/POT_MAX`` (desde mayo).

Aquí solo se extrae y se cruza; no se reparte entre SED ni se aplica en DIgSILENT.

Un único lector, ``python-calamine``, abre ``.xls``, ``.xlsx`` y ``.xlsb``. Las columnas
se reconocen por su nombre normalizado (sin mayúsculas, tildes ni ``_-.``), con alias
genéricos y, delante, los que traiga la empresa en ``config/demanda_medida_alias.json``
(P13).
"""

from __future__ import annotations

import bisect
import copy
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

EXTENSIONES = ('.xls', '.xlsx', '.xlsb', '.xlsm')
FILAS_CABECERA = 30          # dónde se busca la fila de cabecera de un libro
FILAS_DATOS_MINIMAS = 2      # una hoja de medición con menos no es un medidor

# Alias genéricos por campo, en orden de preferencia. Son nombres de los medidores y de
# los libros comerciales, no de una empresa: los de una empresa van en el JSON de config.
ALIAS: dict[str, tuple[str, ...]] = {
    'alimentador': ('codigo alimentador', 'cod alimentador', 'alimentador', 'feeder'),
    'medidor': ('medidor', 'codigo medidor', 'cod medidor', 'meter'),
    # «Local Time» antes que «Timestamp»: es la hora del lugar. En algunas hojas trae solo
    # la fecha, y entonces se usa la otra columna (ver ``_fecha_de``).
    'fecha': ('local time', 'fecha hora', 'fecha y hora', 'fecha', 'timestamp', 'hora'),
    'kw': ('kw tot', 'kw tot mean', 'kw total', 'kw', 'p kw', 'potencia activa'),
    'kvar': ('kvar tot', 'kvar tot mean', 'kvar total', 'kvar', 'q kvar', 'potencia reactiva'),
    'kva': ('kva tot', 'kva tot mean', 'kva total', 'kva', 'pot aparente', 'potencia aparente'),
    # «PF sign tot us» va el último: en los libros de Electro Dunas casi todos sus valores
    # pasan de ±100, con una codificación del medidor que no es un FP. Se usa solo si su
    # valor cabe en un FP (ver ``fp_decimal``); si no, el FP se calcula.
    'fp': ('pf lag mean', 'pf lead mean', 'fp', 'factor de potencia', 'pf', 'pf tot',
           'pf sign tot', 'pf sign tot us'),
    'suministro_act': (
        'suministro act', 'suministro actual', 'sum act', 'nis actual', 'nis act', 'nis [act]',
    ),
    'suministro': ('suministro', 'suministro anterior', 'nis anterior'),
    'sed': ('sed', 'subestacion', 'subestacion de distribucion'),
    'radial': ('radial', 'alimentador'),
    'cliente_codigo': ('nis', 'suministro', 'nro suministro', 'numero suministro'),
    'ea': ('ea', 'ea total', 'energia activa'),
    'eri': ('eri', 'eri total', 'energia reactiva inductiva'),
    'pot': ('pot max', 'pot', 'potencia maxima', 'potencia'),
    # 022:RF-37: las filas de barra del libro de medidores, con su nivel y sus siglas.
    'nivel': ('nivel tension', 'nivel de tension', 'tension kv', 'kv'),
    # 022:RF-85: la columna «SET» del libro (siglas, código o nombre de la SET).
    'siglas': ('siglas', 'set', 'siglas set', 'sigla set', 'codigo set', 'cod set'),
    # 004:RF-56: el nombre del cliente; en los libros de julio de 2026, «CLIENTE». Los de
    # enero a abril no lo traen.
    'cliente_nombre': ('cliente', 'nombre cliente', 'nombre del cliente', 'razon social', 'nombre'),
}
MAGNITUDES = ('kw', 'kvar', 'kva', 'fp')
NOMBRE = {'kw': 'kW', 'kvar': 'kVAR', 'kva': 'kVA', 'fp': 'FP'}


class DemandaError(ValueError):
    """Error de usuario: libro que falta, hoja o columna que no está."""


# =========================================================================== normalizar
def normalizar(texto: Any) -> str:
    """Cabecera o nombre de hoja comparable: sin mayúsculas, tildes ni ``_-.``."""
    t = unicodedata.normalize('NFKD', '' if texto is None else str(texto))
    t = ''.join(c for c in t if not unicodedata.combining(c)).casefold()
    return ' '.join(re.sub(r'[_\-.]+', ' ', t).split())


def clave_codigo(valor: Any) -> str:
    """Código comparable entre libros: ``1234.0``, ``'1234'`` y ``' 001234'`` son el mismo.

    El mismo suministro llega como número en un libro y como texto en otro; y un medidor
    se escribe ``X-AB12`` en uno y ``x ab12`` en otro.
    """
    if valor is None or isinstance(valor, bool):
        return ''
    if isinstance(valor, float):
        if not math.isfinite(valor):
            return ''
        if valor.is_integer():
            valor = int(valor)
    texto = re.sub(r'[\s_\-.]+', '', str(valor).strip()).casefold()
    if texto.isdigit():
        texto = texto.lstrip('0') or '0'
    return texto


def numero(valor: Any) -> float | None:
    """Número finito, o ``None`` si la celda está vacía o no es un número (RF-31)."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if math.isfinite(valor) else None
    texto = str(valor).strip().replace(',', '.')
    try:
        v = float(texto)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def fp_decimal(valor: float | None) -> float | None:
    """FP en tanto por uno y con su signo: ``98.5`` → ``0.985``, ``-97`` → ``-0.97``.

    ``PF lag mean`` y ``PF lead mean`` vienen en porcentaje. Un valor de más de ±100 no
    es un FP (``PF sign tot us`` lo codifica de otra forma): se descarta y el FP se
    calcula con kW y kVA.
    """
    if valor is None:
        return None
    if abs(valor) <= 1:
        return valor
    if abs(valor) <= 100:
        return valor / 100.0
    return None


def cargar_alias(path: Path | str | None) -> dict[str, tuple[str, ...]]:
    """Alias de la empresa (``{campo: [cabeceras]}``) delante de los genéricos."""
    alias = dict(ALIAS)
    if path is None or not Path(path).is_file():
        return alias
    try:
        extra = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DemandaError(f'{Path(path).name}: no es un JSON válido ({exc}).') from exc
    if not isinstance(extra, dict):
        raise DemandaError(f'{Path(path).name}: debe ser un objeto {{campo: [cabeceras]}}.')
    for campo, nombres in extra.items():
        if campo not in ALIAS:
            raise DemandaError(f'{Path(path).name}: campo desconocido {campo!r}. '
                               f'Válidos: {", ".join(ALIAS)}.')
        if isinstance(nombres, str):
            nombres = [nombres]
        alias[campo] = tuple(dict.fromkeys([normalizar(n) for n in nombres] + list(ALIAS[campo])))
    return alias


def columnas(cabecera: Sequence[Any], campos: Iterable[str],
             alias: dict[str, tuple[str, ...]] = ALIAS) -> dict[str, int]:
    """``{campo: índice}`` de los campos que estén, por alias y no por posición (RF-26).

    Un campo toma el primer alias de su lista que aparezca, y una columna no se asigna a
    dos campos (``Suministro`` no puede ser a la vez el actual y el anterior).
    """
    norm = [normalizar(c) for c in cabecera]
    usadas: set[int] = set()
    out: dict[str, int] = {}
    for campo in campos:
        for nombre in alias[campo]:
            hallado = next((i for i, c in enumerate(norm) if c == nombre and i not in usadas), None)
            if hallado is not None:
                out[campo] = hallado
                usadas.add(hallado)
                break
    return out


def _abrir(path: Path | str):
    try:
        from python_calamine import CalamineWorkbook
    except ImportError as exc:
        raise DemandaError('Leer .xls/.xlsx/.xlsb necesita python-calamine: '
                           'pip install -r requirements.txt') from exc
    src = Path(path)
    if not src.is_file():
        raise DemandaError(f'No se encuentra el fichero: {src}')
    if src.suffix.lower() not in EXTENSIONES:
        raise DemandaError(f'{src.name}: extensión no soportada; use ' + ', '.join(EXTENSIONES))
    try:
        return CalamineWorkbook.from_path(str(src))
    except Exception as exc:  # noqa: BLE001 - calamine da errores propios; se nombra el libro
        raise DemandaError(f'{src.name}: no se pudo abrir ({exc}).') from exc


def _filas(libro, hoja: str) -> list[list[Any]]:
    return libro.get_sheet_by_name(hoja).to_python(skip_empty_area=False)


@dataclass(frozen=True)
class LibroClientesMes:
    """Un libro mensual indexado, incluida la evidencia de cómo se obtuvo su mes."""

    path: str
    #: Ruta relativa a la carpeta elegida («2025/0125 Pulso e.xlsx», 025:RF-3).
    nombre: str
    mes: str | None
    origen_mes: Literal['nombre', 'contenido', 'manual', 'sin_mes']
    mtime_ns: int
    size: int
    activo: bool
    avisos: tuple[str, ...] = ()
    #: Año de su carpeta, o None si está suelto (025:RF-1).
    anio: int | None = None


@dataclass(frozen=True)
class ClientPeriodEvidence:
    status: str
    period: str | None
    file: str | None
    sheet: str | None
    fingerprint: str | None
    period_origin: str | None
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_MES_VALIDO = re.compile(r'^(?P<anio>\d{4})-(?P<mes>0[1-9]|1[0-2])$')


def periodo_de_fecha(value: Any) -> str | None:
    """Mes ``AAAA-MM`` de una fecha de medición, sin depender del formato fuente."""
    if isinstance(value, datetime):
        return f'{value.year:04d}-{value.month:02d}'
    if isinstance(value, date):
        return f'{value.year:04d}-{value.month:02d}'
    text = str(value or '').strip()
    if not text:
        return None
    iso = re.match(r'^(?P<anio>\d{4})-(?P<mes>0[1-9]|1[0-2])(?:-\d{2})?', text)
    if iso:
        return f"{iso.group('anio')}-{iso.group('mes')}"
    local = re.match(
        r'^\d{1,2}[/.-](?P<mes>0?[1-9]|1[0-2])[/.-](?P<anio>\d{4})(?:\s|$)', text,
    )
    if local:
        return f"{local.group('anio')}-{int(local.group('mes')):02d}"
    return None


def en_periodo(fecha: Any, periodo: str | None) -> bool:
    """La fecha está en el periodo: un mes ``AAAA-MM`` o un año ``AAAA`` (025:RF-7).

    Sin periodo, cualquier fecha. El año entero es para calibrar con la máxima de un año
    de medición (2025, junto a la de 2026) sin elegir un mes.
    """
    if not periodo:
        return True
    mes = periodo_de_fecha(fecha)
    if mes is None:
        return False
    return mes[:4] == periodo if len(periodo) == 4 else mes == periodo


def _mes_valido(valor: str) -> str:
    mes = str(valor).strip()
    if not _MES_VALIDO.fullmatch(mes):
        raise DemandaError(f'Mes no válido {valor!r}; use AAAA-MM.')
    return mes


def mes_de_nombre(nombre: str, patron: str | Sequence[str] | None) -> str | None:
    """Mes AAAA-MM extraído con los grupos mes y anio del perfil.

    El perfil puede dar varios patrones (025:RF-6b): la empresa que cambia la forma del
    nombre de un año a otro. Vale el primero que casa.
    """
    if not patron:
        return None
    for uno in ([patron] if isinstance(patron, str) else list(patron)):
        mes = _mes_de_un_patron(nombre, uno)
        if mes:
            return mes
    return None


def _mes_de_un_patron(nombre: str, patron: str) -> str | None:
    try:
        expresion = re.compile(patron)
    except re.error as exc:
        raise DemandaError(f'patron_libro_clientes no es válido: {exc}.') from exc
    if {'mes', 'anio'} - set(expresion.groupindex):
        raise DemandaError('patron_libro_clientes debe tener grupos «mes» y «anio».')
    hallado = expresion.fullmatch(Path(nombre).name)
    if hallado is None:
        return None
    mes, anio = hallado.group('mes'), hallado.group('anio')
    if not mes.isdigit() or not anio.isdigit() or not 1 <= int(mes) <= 12:
        return None
    if len(anio) == 2:
        anio = f'{2000 + int(anio):04d}'
    elif len(anio) != 4:
        return None
    return f'{int(anio):04d}-{int(mes):02d}'


#: Nombres de mes que se reconocen en un nombre de libro (025:RF-6): enteros y abreviados,
#: en español y en inglés; «set» es la abreviatura de septiembre en Perú.
_NOMBRES_MES: dict[str, int] = {}
for _n, (_es, _en) in enumerate(zip(
        ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre'),
        ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
         'september', 'october', 'november', 'december')), start=1):
    for _clave in (_es, _es[:3], _en, _en[:3]):
        _NOMBRES_MES[_clave] = _n
_NOMBRES_MES.update({'setiembre': 9, 'set': 9, 'sept': 9})


def mes_generico(nombre: str, anio: int) -> str | None:
    """Mes ``AAAA-MM`` del nombre de un libro de la carpeta de ``anio`` (025:RF-6).

    Sin patrón de la empresa: Electro Dunas pasó de «0126clientesImportantes» en 2026 a
    «0125 Pulso e» en 2025, y otra empresa nombrará de otra forma. Se aceptan ``MMAA``,
    ``AAMM``, ``AAAAMM``, ``MMAAAA``, ``AAAA-MM``, ``MM-AAAA`` y el nombre del mes, solo
    del año de la carpeta. Con ningún mes o con dos distintos no se supone nada: queda
    la fecha dentro del libro (013:RF-4).
    """
    base = Path(nombre).stem.casefold()
    corto = anio % 100
    meses: set[int] = set()

    def poner(mes: int) -> None:
        if 1 <= mes <= 12:
            meses.add(mes)

    for m in re.finditer(r'(?<!\d)(\d{4})[-_. ](\d{1,2})(?!\d)', base):          # AAAA-MM
        if int(m.group(1)) == anio:
            poner(int(m.group(2)))
    for m in re.finditer(r'(?<!\d)(\d{1,2})[-_. ](\d{4})(?!\d)', base):          # MM-AAAA
        if int(m.group(2)) == anio:
            poner(int(m.group(1)))
    for m in re.finditer(r'(?<!\d)(\d{6})(?!\d)', base):                         # AAAAMM, MMAAAA
        t = m.group(1)
        if int(t[:4]) == anio:
            poner(int(t[4:]))
        if int(t[2:]) == anio:
            poner(int(t[:2]))
    for m in re.finditer(r'(?<!\d)(\d{4})(?!\d)', base):                         # MMAA, AAMM
        t = m.group(1)
        if int(t[2:]) == corto:
            poner(int(t[:2]))
        if int(t[:2]) == corto:
            poner(int(t[2:]))
    for palabra in re.findall(r'[^\W\d_]+', base):
        if palabra in _NOMBRES_MES:
            poner(_NOMBRES_MES[palabra])
    if len(meses) != 1:
        return None
    return f'{anio:04d}-{next(iter(meses)):02d}'


def _mes_de_valor(valor: Any, *, columna_fecha: bool) -> str | None:
    if isinstance(valor, datetime):
        return f'{valor.year:04d}-{valor.month:02d}'
    if isinstance(valor, date):
        return f'{valor.year:04d}-{valor.month:02d}'
    if not columna_fecha or not isinstance(valor, str):
        return None
    texto = valor.strip()
    iso = re.fullmatch(r'(?P<anio>\d{4})-(?P<mes>0[1-9]|1[0-2])(?:-\d{2})?', texto)
    if iso:
        return f"{int(iso.group('anio')):04d}-{int(iso.group('mes')):02d}"
    periodo = re.fullmatch(r'(?P<mes>0[1-9]|1[0-2])[/.-](?P<anio>\d{4})', texto)
    if periodo:
        return f"{int(periodo.group('anio')):04d}-{int(periodo.group('mes')):02d}"
    return None


def meses_de_contenido(path: Path | str, alias=ALIAS) -> set[str]:
    """Meses explícitos dentro del libro; no interpreta números ni texto ambiguo."""
    libro = _abrir(path)
    nombres_fecha = {normalizar(n) for n in alias.get('fecha', ())}
    nombres_fecha.update({'mes', 'periodo'})
    meses: set[str] = set()
    for hoja in libro.sheet_names:
        filas = _filas(libro, hoja)
        # Una celda que el motor ya tipó como fecha es evidencia aun fuera de una tabla.
        for fila in filas:
            for valor in fila:
                mes = _mes_de_valor(valor, columna_fecha=False)
                if mes:
                    meses.add(mes)
        # Las cadenas solo se aceptan bajo una columna que diga fecha, mes o periodo.
        for i, fila in enumerate(filas[:FILAS_CABECERA]):
            indices = [j for j, valor in enumerate(fila) if normalizar(valor) in nombres_fecha]
            if not indices:
                continue
            for datos in filas[i + 1:]:
                for j in indices:
                    valor = datos[j] if j < len(datos) else None
                    mes = _mes_de_valor(valor, columna_fecha=True)
                    if mes:
                        meses.add(mes)
            break
    return meses


def catalogar_libros_clientes(carpeta: Path | str, patron: str | Sequence[str] | None,
                              asignaciones: dict[str, str] | None = None,
                              alias=ALIAS) -> list[LibroClientesMes]:
    """Indexa una carpeta o un libro y activa uno solo por mes (013:RF-1 a RF-5).

    Una carpeta se recorre con sus subcarpetas de año (025:RF-1): cada libro lleva su ruta
    relativa y su año, y su mes sale del patrón del perfil, de la regla general del nombre
    dentro de su año (025:RF-6) o de la fecha de dentro (013:RF-4).
    """
    from .libros_por_anio import arbol_de_libros

    fuente = Path(carpeta)
    if fuente.is_file():
        if fuente.suffix.lower() not in EXTENSIONES:
            raise DemandaError(f'{fuente.name}: extensión no soportada; use ' + ', '.join(EXTENSIONES))
        rutas = [(fuente, fuente.name, None)]
    elif fuente.is_dir():
        rutas = [(x.ruta, x.relativa, x.anio) for x in arbol_de_libros(fuente)]
    else:
        raise DemandaError(f'No se encuentra la fuente de clientes: {fuente}')

    manuales = asignaciones or {}
    catalogo: list[LibroClientesMes] = []
    for path, relativa, anio in rutas:
        manual = next((manuales[k] for k in (str(path), path.as_posix(), relativa, path.name)
                       if k in manuales), None)
        if manual is not None:
            mes, origen = _mes_valido(manual), 'manual'
        else:
            mes = mes_de_nombre(path.name, patron)
            if mes is None and anio is not None:
                mes = mes_generico(path.name, anio)
            origen = 'nombre' if mes else 'sin_mes'
        avisos: tuple[str, ...] = ()
        if mes is None and manual is None:
            # Sin mes en el nombre el libro se abre de todos modos: «0926 Clientes_spl.xlsx»
            # (el de suministros) tiene fechas de septiembre y se activaba como clientes de
            # ese mes. Sin hoja «resumen» no es de clientes (004:RF-65).
            if not _hojas_resumen(_abrir(path).sheet_names):
                avisos = ('sin hoja «resumen»: no es un libro de clientes importantes '
                          '(¿es el de suministros?); no se usa.',)
            else:
                internos = meses_de_contenido(path, alias)
                if len(internos) == 1:
                    mes, origen = next(iter(internos)), 'contenido'
        activo = mes is not None
        if (mes is not None and anio is not None and origen != 'manual'
                and mes[:4] != f'{anio:04d}'):
            # 025:RF-5: un libro de 2026 dejado en la carpeta de 2025 mezclaría los años.
            activo = False
            avisos = (*avisos, f'su mes es {mes} y está en la carpeta {anio}: no se usa; '
                               'muévalo a la carpeta de su año o asígnele el mes.')
        stat = path.stat()
        catalogo.append(LibroClientesMes(
            path=str(path), nombre=relativa, mes=mes, origen_mes=origen,
            mtime_ns=stat.st_mtime_ns, size=stat.st_size, activo=activo, avisos=avisos,
            anio=anio,
        ))

    por_mes: dict[str, list[int]] = {}
    for i, libro in enumerate(catalogo):
        if libro.mes and libro.activo:
            por_mes.setdefault(libro.mes, []).append(i)
    for mes, indices in por_mes.items():
        if len(indices) < 2:
            continue
        ganador = max(indices, key=lambda i: (catalogo[i].mtime_ns, catalogo[i].nombre))
        nombres = ', '.join(catalogo[i].nombre for i in indices)
        aviso = (f'{mes}: hay libros duplicados ({nombres}); '
                 f'se usa {catalogo[ganador].nombre}, el más reciente.')
        for i in indices:
            catalogo[i] = replace(
                catalogo[i], activo=i == ganador, avisos=(*catalogo[i].avisos, aviso))
    return catalogo


def _buscar_cabecera(filas: Sequence[Sequence[Any]], campos: Sequence[str], alias,
                     obligatorios: Sequence[str]) -> tuple[int, dict[str, int]] | None:
    for i, fila in enumerate(filas[:FILAS_CABECERA]):
        cols = columnas(fila, campos, alias)
        if all(c in cols for c in obligatorios):
            return i, cols
    return None


def _texto(fila: Sequence[Any], indice: int | None) -> str:
    if indice is None or indice >= len(fila) or fila[indice] is None:
        return ''
    v = fila[indice]
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _celda(fila: Sequence[Any], indice: int | None) -> Any:
    return fila[indice] if indice is not None and indice < len(fila) else None


# =========================================================================== medidores
@dataclass(frozen=True)
class Medidor:
    alimentador: str
    medidor: str
    fila: int


def leer_medidores(path: Path | str, alias=ALIAS) -> list[Medidor]:
    """Filas del libro medidor por alimentador, de su primera hoja con esas columnas."""
    libro = _abrir(path)
    for hoja in libro.sheet_names:
        filas = _filas(libro, hoja)
        hallada = _buscar_cabecera(filas, ('alimentador', 'medidor'), alias, ('alimentador', 'medidor'))
        if hallada is None:
            continue
        i, cols = hallada
        out = []
        for n, fila in enumerate(filas[i + 1:], start=i + 2):
            ali, med = _texto(fila, cols['alimentador']), _texto(fila, cols['medidor'])
            if ali and med:
                out.append(Medidor(ali, med, n))
        return out
    raise DemandaError(f'{Path(path).name}: ninguna hoja tiene columnas de alimentador y medidor.')


def partir_medidores(celda: str) -> list[str]:
    """Una celda puede traer dos medidores: «IN111_V18 Y IN111_V119» en el libro real."""
    return [m.strip() for m in re.split(r'\s+(?:y|e)\s+|\s*[,;/+]\s*', celda, flags=re.I) if m.strip()]


def alimentadores_de(medidores: Sequence[Medidor]) -> list[str]:
    """Alimentadores del libro, sin repetir y ordenados, para elegir de una lista (RF-42).

    El libro real repite el código con otra grafía («PA217» y «pa 217»): se queda la
    primera que aparece.
    """
    vistos: dict[str, str] = {}
    for m in medidores:
        vistos.setdefault(clave_codigo(m.alimentador), m.alimentador)
    return sorted(vistos.values(), key=clave_codigo)


def medidores_de(medidores: Sequence[Medidor], alimentador: str,
                 equivalentes: Iterable[str] = ()) -> list[str]:
    """Cada medidor que el libro asigna al alimentador, sin repetir y en su orden (RF-22).

    ``equivalentes``: otras grafías del mismo alimentador según la estructura (022:RF-81),
    CHN101 en el libro para el CN101 de la red.
    """
    claves = {clave_codigo(alimentador)} | {clave_codigo(e) for e in equivalentes}
    return list(dict.fromkeys(parte for m in medidores if clave_codigo(m.alimentador) in claves
                              for parte in partir_medidores(m.medidor)))


# =========================================================================== cabecera
def libros_de_cabecera(rutas: Iterable[Path | str]) -> list[Path]:
    """Ficheros de cabecera: cada ruta es un libro o una carpeta con libros (RF-39).

    Una carpeta se recorre entera, con sus subcarpetas de año (025:RF-1): elegir los del
    año de la máxima es de quien busca (``libros_por_anio.libros_del_periodo``).
    """
    from .libros_por_anio import arbol_de_libros

    out: list[Path] = []
    for ruta in rutas:
        p = Path(ruta)
        if p.is_dir():
            out += [x.ruta for x in arbol_de_libros(p)]
        elif p.is_file():
            out.append(p)
        else:
            raise DemandaError(f'No existe: {p}')
    if not out:
        raise DemandaError('No hay libros de medición de cabecera (.xls, .xlsx, .xlsb).')
    return list(dict.fromkeys(out))


def hojas_del_medidor(hojas: Sequence[str], medidor: str) -> tuple[list[str], list[str]]:
    """Hojas del medidor en un libro: la de su nombre y sus partes (RF-24, RF-25).

    La entera es la que se llama como el medidor. Las partes son ``<medidor>_<sufijo>``,
    una por magnitud: el sufijo va tras un separador, para que ``X1`` no encuentre
    ``X10``. En los libros de Ica hay medidores con las dos: una hoja con su nombre sin kW
    y el kW en una de sus partes.
    """
    clave = clave_codigo(medidor)
    enteras = [h for h in hojas if clave_codigo(h) == clave]
    patron = re.compile(r'^\s*' + r'[\s_\-.]*'.join(map(re.escape, medidor.strip()))
                        + r'[\s_\-.]+\S', re.I)
    partes = [h for h in hojas if patron.match(h) and h not in enteras]
    return enteras[:1], partes


def indexar_libro_cabecera(path: Path | str, alias=ALIAS) -> dict[str, Any]:
    """Hojas de medición de un libro y los meses con registro (025:RF-28, RF-29).

    Para el índice por año de la web: qué trae cada libro, sin buscar ninguna máxima. Un
    libro que no se abre o sin ninguna hoja con fecha y kW no se rechaza: queda con su
    motivo, y los demás siguen.
    """
    try:
        libro = _abrir(path)
        hojas, meses = [], set()
        for hoja in libro.sheet_names:
            registros, usadas = _registros_hoja(_filas(libro, hoja), alias)
            if 'kw' not in usadas or not registros:
                continue
            hojas.append(hoja)
            meses.update(m for m in (periodo_de_fecha(r.fecha) for r in registros) if m)
    except Exception as exc:  # noqa: BLE001 - calamine da errores propios; no se calla: es el motivo (RF-29)
        return {'hojas': [], 'meses': [], 'error': str(exc) or exc.__class__.__name__}
    error = None if hojas else 'ninguna hoja tiene columnas de fecha y kW: no es una medición de cabecera'
    return {'hojas': hojas, 'meses': sorted(meses), 'error': error}


def hojas_del_alimentador(hojas: Sequence[str], alimentador: str) -> list[str]:
    """Hojas que se llaman como el alimentador, solo o tras un prefijo separado (025:RF-12).

    «L-PA217», «ALIM PA217» o «PA217»; no «PA2170» ni «PA217_kW»: el código va al final y
    entero. Sin prefijos de una empresa: cualquiera separado por guion, espacio, punto o
    subrayado.
    """
    codigo = alimentador.strip()
    if not codigo:
        return []
    patron = re.compile(r'^(?:.*[\s_\-.])?' + re.escape(codigo) + r'\s*$', re.I)
    return [h for h in hojas if patron.match(h.strip())]


def base_del_medidor(medidor: str) -> str | None:
    """Medidor del que ``medidor`` es un canal: ``IN111_V18`` → ``IN111`` (RF-44).

    En Ica el libro de medidores nombra canales sueltos de un medidor (``IN111_V18``, el
    kW) y su kVAR está en la hoja hermana ``IN111_V19``. La base ha de tener un dígito:
    sin él, ``L-6613`` daría ``L`` y juntaría hojas de medidores distintos.
    """
    m = re.match(r'^(.+?)[\s_\-.]+[^\s_\-.]+$', medidor.strip())
    if m is None or not any(c.isdigit() for c in m.group(1)):
        return None
    return m.group(1)


@dataclass
class Registro:
    fecha: Any
    valores: dict[str, float | None] = field(default_factory=dict)
    # Columna de la que salió el FP de este registro: «lag» o «lead» según el registro.
    fuente_fp: str | None = None


def _fecha_de(fila: Sequence[Any], cols_fecha: Sequence[int]) -> Any:
    """La primera columna de fecha que trae hora; si ninguna, la primera con algo."""
    valores = [_celda(fila, i) for i in cols_fecha]
    for v in valores:
        if isinstance(v, datetime):
            return v
    return next((v for v in valores if v not in (None, '')), None)


def _registros_hoja(filas: Sequence[Sequence[Any]], alias) -> tuple[list[Registro], dict[str, str]]:
    """Registros de una hoja de medición y qué cabecera se usó para cada magnitud."""
    hallada = None
    for i, fila in enumerate(filas[:FILAS_CABECERA]):
        cols = columnas(fila, MAGNITUDES, alias)
        if cols and any(normalizar(c) in alias['fecha'] for c in fila):
            hallada = (i, cols)
            break
    if hallada is None:
        return [], {}
    i, cols = hallada
    cabecera = filas[i]
    norm = [normalizar(c) for c in cabecera]
    cols_fecha = [norm.index(a) for a in alias['fecha'] if a in norm]
    # Las dos de FP de los medidores: «lag» (inductivo) y «lead» (capacitivo); se toma
    # la que tenga valor en el registro.
    cols_fp = [norm.index(a) for a in alias['fp'] if a in norm]
    usadas = {k: str(cabecera[v]).strip() for k, v in cols.items()}
    registros = []
    for fila in filas[i + 1:]:
        fecha = _fecha_de(fila, cols_fecha)
        valores = {k: numero(_celda(fila, v)) for k, v in cols.items() if k != 'fp'}
        fp, fuente = None, None
        for c in cols_fp:
            fp = fp_decimal(numero(_celda(fila, c)))
            if fp is not None:
                fuente = str(cabecera[c]).strip()
                break
        if 'fp' in cols:
            valores['fp'] = fp
        if fecha is None and not any(v is not None for v in valores.values()):
            continue
        registros.append(Registro(fecha, valores, fuente))
    # python-calamine devuelve una fecha sin hora (``date``) para el registro de las 00:00
    # y con hora para los demás: la máxima a medianoche salía sin su hora y, en un medidor
    # partido en hojas, no casaba por fecha con la misma hora de otra hoja. En una hoja con
    # hora, esa fecha es la medianoche de ese día.
    if any(isinstance(r.fecha, datetime) for r in registros):
        for r in registros:
            if type(r.fecha) is date:
                r.fecha = datetime(r.fecha.year, r.fecha.month, r.fecha.day)
    return registros, usadas


def _unir_por_fecha(partes: Sequence[list[Registro]]) -> list[Registro]:
    """Un medidor partido en una hoja por magnitud: un registro por fecha y hora (RF-25)."""
    por_fecha: dict[Any, Registro] = {}
    for registros in partes:
        for r in registros:
            if r.fecha is None:
                continue
            destino = por_fecha.setdefault(r.fecha, Registro(r.fecha))
            for k, v in r.valores.items():
                if v is not None or k not in destino.valores:
                    destino.valores[k] = v
            destino.fuente_fp = destino.fuente_fp or r.fuente_fp
    return list(por_fecha.values())


def _antes(a: Any, b: Any) -> bool:
    """``a`` es anterior a ``b``; con fechas no comparables, conserva el orden de lectura."""
    try:
        return a is not None and b is not None and a < b
    except TypeError:
        return False


@dataclass
class MaximaCabecera:
    medidor: str
    alimentador: str = ''
    libro: str = ''
    hojas: list[str] = field(default_factory=list)
    fecha: str | None = None
    kw: float | None = None
    kvar: float | None = None
    kva: float | None = None
    fp: float | None = None
    kva_calculado: bool = False
    fp_calculado: bool = False
    registros: int = 0
    columnas: dict[str, str] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    error: str | None = None
    # Medidor sin hoja que se leyó como el medidor del que es canal (RF-45).
    canal_de: str = ''
    # Spec 006, RF-31 y RF-37: registros que no entran en la curva (sin fecha o sin kW).
    fuera_de_curva: int = 0
    # Curva entera ``(fecha, kW, kVAR)`` en orden. Fuera de ``to_dict``: el resultado del
    # trabajo viaja al navegador por el WebSocket, y un año de lecturas cada 15 min son
    # unos 35 000 registros por medidor. La web la sirve aparte y reducida (RF-39).
    curva: list[tuple[datetime, float, float | None]] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self) if f.name != 'curva'}


def _iso(fecha: Any) -> str | None:
    if isinstance(fecha, (datetime, date)):
        return fecha.isoformat(sep=' ') if isinstance(fecha, datetime) else fecha.isoformat()
    return None if fecha is None else str(fecha)


def maxima_de_registros(registros: Sequence[Registro], resultado: MaximaCabecera,
                        periodo: str | None = None,
                        instante: datetime | None = None) -> MaximaCabecera:
    """kW máximo con su fecha; kVAR, kVA y FP del **mismo** registro (RF-27, RF-28, RF-30).

    Con ``periodo`` (``AAAA-MM``, o ``AAAA`` para el año entero, 025:RF-7), la máxima de
    ese mes o año (013:RF-11): NA205 da la suya en
    agosto de 2026 y la empresa solo tiene libros de clientes hasta julio; se calibra en el
    mes que tiene libro. La curva sigue siendo la del registro entero (006:RF-32).

    Con ``instante``, no la máxima sino el registro de esa fecha y hora (021:RF-50): con
    varios alimentadores se calibra a la vez, en la máxima de uno de ellos (NA203 + NA205
    y su central, 2026-10-17).
    """
    mejor: Registro | None = None
    corruptos = 0
    for r in registros:
        kw = r.valores.get('kw')
        if kw is None:
            continue                                    # RF-31: vacío o no numérico
        kva = r.valores.get('kva')
        if kva is not None and kva < 0:
            # Un kVA negativo no es físico: L-LL123 el 2026-10-18 dio 32 765 kW (el tope de
            # un contador de 16 bits) con −30 818 kVA y ganaba como máxima de LL203.
            corruptos += 1
            continue
        if instante is not None:
            if _como_datetime(r.fecha) == instante:
                mejor = r
                break
            continue
        if not en_periodo(r.fecha, periodo):
            continue
        if (mejor is None or kw > mejor.valores['kw']
                or (kw == mejor.valores['kw'] and _antes(r.fecha, mejor.fecha))):
            mejor = r
    resultado.registros = len(registros)
    resultado.curva, resultado.fuera_de_curva = curva_de_registros(registros)
    if corruptos:
        resultado.avisos.append(f'{corruptos} registro(s) con kVA negativo descartados: no son '
                                'físicos (desborde del contador del medidor).')
    if mejor is None:
        resultado.error = (f'sin registro con kW numérico el {_iso(instante)}' if instante
                           else f'ningún registro con kW numérico en {periodo}' if periodo
                           else 'ningún registro con kW numérico')
        return resultado
    v = mejor.valores
    resultado.fecha = _iso(mejor.fecha)
    resultado.columnas.pop('fp', None)
    if mejor.fuente_fp:
        resultado.columnas['fp'] = mejor.fuente_fp
    resultado.kw, resultado.kvar = v['kw'], v.get('kvar')
    resultado.kva, resultado.fp = v.get('kva'), v.get('fp')
    if resultado.kva is None and resultado.kvar is not None:
        resultado.kva = math.hypot(resultado.kw, resultado.kvar)
        resultado.kva_calculado = True
    if resultado.fp is None and resultado.kva:
        fp = abs(resultado.kw) / resultado.kva
        if fp > 1.0:
            # Un kVA menor que el kW no es físico: el medidor integra cada magnitud por su
            # lado (L-LL123, octubre de 2026: FP calculado 1,06). Vale 1 y se dice.
            resultado.avisos.append(f'kVA {resultado.kva:g} menor que |kW| {abs(resultado.kw):g} '
                                    'en el registro: FP calculado acotado a 1.')
            fp = 1.0
        # Con kVAR negativo (capacitivo) el FP lleva signo negativo, como en el medidor.
        resultado.fp = -fp if (resultado.kvar or 0) < 0 else fp
        resultado.fp_calculado = True
        resultado.columnas['fp'] = 'calculado con kW y kVA'
    return resultado


def _como_datetime(fecha: Any) -> datetime | None:
    if isinstance(fecha, datetime):
        return fecha
    if isinstance(fecha, date):
        return datetime(fecha.year, fecha.month, fecha.day)
    return None


def curva_de_registros(registros: Sequence[Registro]) -> tuple[list[tuple[datetime, float, float | None]], int]:
    """Curva ``(fecha, kW, kVAR)`` en orden de fecha y cuántos registros quedan fuera (006:RF-31, RF-37).

    Un registro sin fecha o con el kW vacío o de texto («n/d») no se puede dibujar: se
    cuenta para decirlo, en vez de pintarlo como un cero que parecería un corte de servicio.
    """
    curva, fuera = [], 0
    for r in registros:
        fecha, kw = _como_datetime(r.fecha), r.valores.get('kw')
        if fecha is None or kw is None:
            fuera += 1
            continue
        curva.append((fecha, kw, r.valores.get('kvar')))
    curva.sort(key=lambda p: p[0])
    return curva, fuera


def reducir_curva(curva: Sequence[tuple[datetime, float, float | None]], desde: datetime | None = None,
                  hasta: datetime | None = None, max_puntos: int = 2000) -> list:
    """El tramo ``[desde, hasta]`` de una curva ordenada, con ``max_puntos`` como mucho (006:RF-39).

    Se parte el tramo en intervalos de tiempo iguales y de cada uno se conservan el
    registro de kW mínimo y el de kW máximo. Así la máxima de cabecera, que es el máximo
    de su intervalo, nunca desaparece de la vista general; con la media diaria se
    aplanaba el pico y el punto marcado quedaba fuera de la línea.
    """
    fechas = [p[0] for p in curva]
    i = 0 if desde is None else bisect.bisect_left(fechas, desde)
    j = len(curva) if hasta is None else bisect.bisect_right(fechas, hasta)
    tramo = list(curva[i:j])
    if len(tramo) <= max_puntos:
        return tramo
    intervalos = max(1, max_puntos // 2)
    t0 = tramo[0][0]
    ancho = (tramo[-1][0] - t0).total_seconds() / intervalos or 1.0
    extremos: dict[int, list[int]] = {}
    for k, (fecha, kw, _kvar) in enumerate(tramo):
        n = min(intervalos - 1, int((fecha - t0).total_seconds() / ancho))
        e = extremos.get(n)
        if e is None:
            extremos[n] = [k, k]
        else:
            if kw < tramo[e[0]][1]:
                e[0] = k
            if kw > tramo[e[1]][1]:
                e[1] = k
    return [tramo[k] for k in sorted({k for e in extremos.values() for k in e})]


class Cabecera:
    """Libros de cabecera abiertos una vez por búsqueda: abrir un .xls de 400 MB cuesta ~1 s."""

    def __init__(self, rutas: Iterable[Path | str], alias=ALIAS) -> None:
        self.libros = libros_de_cabecera(rutas)
        self.alias = alias
        self._abiertos: dict[Path, Any] = {}
        #: Libros que no se pudieron abrir, con el motivo (025:RF-29): uno roto en la carpeta
        #: del año no impide buscar en los demás.
        self.rotos: dict[Path, str] = {}

    def _libro(self, path: Path):
        if path not in self._abiertos:
            self._abiertos[path] = _abrir(path)
        return self._abiertos[path]

    def _hojas(self, path: Path) -> list[str]:
        """Las hojas del libro, o ninguna si no se abre (queda en ``rotos``)."""
        if path in self.rotos:
            return []
        try:
            return list(self._libro(path).sheet_names)
        except DemandaError as exc:
            self.rotos[path] = str(exc)
            return []

    def _completar(self, path: Path, medidor: str, registros: list[Registro],
                   res: MaximaCabecera) -> list[Registro]:
        """kVAR y kVA que le faltan a la hoja del kW, de hojas de una sola magnitud (RF-44).

        Se buscan entre las partes del medidor y las de su base: ``IN111_V18`` trae solo el
        kW y su kVAR está en ``IN111_V19``. Se unen por fecha y hora, así que el kVAR es el
        del mismo registro que el kW máximo (RF-28). Si dos hojas dan la misma magnitud no
        se elige ninguna: se avisa.
        """
        faltan = [m for m in ('kvar', 'kva') if m not in res.columnas]
        if not faltan:
            return registros
        hojas = self._hojas(path)
        candidatas = hojas_del_medidor(hojas, medidor)[1]
        base = base_del_medidor(medidor)
        if base:
            candidatas += sum(hojas_del_medidor(hojas, base), [])
        por_magnitud: dict[str, list[tuple[str, list[Registro], str]]] = {}
        for hoja in dict.fromkeys(candidatas):
            if hoja in res.hojas:
                continue
            regs, usadas = _registros_hoja(_filas(self._libro(path), hoja), self.alias)
            if len(usadas) == 1 and next(iter(usadas)) in faltan:
                m = next(iter(usadas))
                por_magnitud.setdefault(m, []).append((hoja, regs, usadas[m]))
        trozos, de_donde = [registros], []
        for m in faltan:
            opciones = por_magnitud.get(m, [])
            if len(opciones) > 1:
                res.avisos.append(f'{NOMBRE[m]} en varias hojas ('
                                  + ', '.join(h for h, _r, _c in opciones) + '); no se toma ninguna')
            elif opciones:
                hoja, regs, col = opciones[0]
                res.hojas.append(hoja)
                res.columnas[m] = col
                trozos.append(regs)
                de_donde.append(f'{NOMBRE[m]} de {hoja}')
        if not de_donde:
            return registros
        res.avisos.append(', '.join(de_donde) + ', del mismo registro que el kW máximo')
        return _unir_por_fecha(trozos)

    def _por_alimentador(self, res: MaximaCabecera, medidor: str, alimentador: str,
                         periodo: str | None, instante: datetime | None) -> MaximaCabecera:
        """La hoja con el código del alimentador, si la del medidor no está (025:RF-12).

        En la cabecera de 2025 de Electro Dunas, cuatro hojas se llaman como su alimentador
        («L-PA217») y no como el medidor que da el libro de medidores («L-PA235»).
        """
        if alimentador:
            casan = [(p, h) for p in self.libros
                     for h in hojas_del_alimentador(self._hojas(p), alimentador)]
            if len(casan) > 1:
                res.error = (f'sin hoja {medidor}; varias hojas con el código {alimentador} ('
                             + ', '.join(f'{p.name} › {h}' for p, h in casan)
                             + '): escriba como medidor el nombre de la que quiere (025:RF-12b)')
                return res
            if casan:
                path, hoja = casan[0]
                res.libro = path.name
                registros, usadas = _registros_hoja(_filas(self._libro(path), hoja), self.alias)
                res.hojas, res.columnas = [hoja], dict(usadas)
                res.avisos.append(f'no hay hoja {medidor}; se usa {hoja}, la del código del '
                                  f'alimentador {alimentador} (025:RF-12)')
                if 'kw' not in usadas:
                    res.error = f'{path.name} › {hoja}: sin columna de kW'
                    return res
                return maxima_de_registros(registros, res, periodo, instante)
        res.error = (f'el medidor {medidor} no está en ningún libro de cabecera'
                     + (f', ni una hoja con el código {alimentador}' if alimentador else ''))
        return res

    def maxima(self, medidor: str, alimentador: str = '', periodo: str | None = None,
               instante: datetime | None = None) -> MaximaCabecera:
        res = MaximaCabecera(medidor=medidor, alimentador=alimentador)
        hallados: list[tuple[Path, list[str], list[str]]] = []
        for path in self.libros:
            entera, partes = hojas_del_medidor(self._hojas(path), medidor)
            if entera or partes:
                hallados.append((path, entera, partes))
        if not hallados:
            # «IN111_V119» en el libro de medidores, sin hoja: es un canal de IN111, que sí
            # está (RF-45). Se lee IN111; ``maximas`` lo junta con IN111_V18 si también se pidió.
            base = base_del_medidor(medidor)
            if base and any(any(hojas_del_medidor(self._hojas(p), base))
                            for p in self.libros):
                res = self.maxima(base, alimentador, periodo, instante)
                res.medidor, res.canal_de = medidor, base
                res.avisos.insert(0, f'no hay hoja {medidor}; se usa {base}, el medidor del que es canal')
                return res
            return self._por_alimentador(res, medidor, alimentador, periodo, instante)
        # Mejor el libro con la hoja de su nombre; entre iguales, el modificado más tarde
        # (025:RF-30: un año con un libro corregido junto al primero) y luego por nombre.
        hallados.sort(key=lambda h: (not h[1], -h[0].stat().st_mtime_ns))
        path, entera, partes = hallados[0]
        if len(hallados) > 1:
            res.avisos.append('también está en ' + ', '.join(p.name for p, _e, _x in hallados[1:])
                              + f'; se usa {path.name}')
        res.libro = path.name
        if entera:
            registros, usadas = _registros_hoja(_filas(self._libro(path), entera[0]), self.alias)
            if 'kw' in usadas or not partes:
                res.hojas, res.columnas = list(entera), dict(usadas)
                if 'kw' not in usadas:
                    res.error = f'{path.name} › {entera[0]}: sin columna de kW'
                    return res
                return maxima_de_registros(self._completar(path, medidor, registros, res), res, periodo, instante)
            res.avisos.append(f'{entera[0]}: sin columna de kW; se usan sus hojas por magnitud')
        trozos, completas = [], []
        for hoja in partes:
            registros, usadas = _registros_hoja(_filas(self._libro(path), hoja), self.alias)
            if len(usadas) > 1:
                # «L-6613_PE» y «L-6613_TM» en Chincha: hojas completas, cada una un punto
                # de medida, no magnitudes sueltas del mismo medidor.
                if 'kw' in usadas:
                    completas.append((hoja, registros, usadas))
                continue
            if len(usadas) == 1:
                for k, c in usadas.items():
                    res.columnas.setdefault(k, c)
                res.hojas.append(hoja)
                trozos.append(registros)
        if 'kw' not in res.columnas and len(completas) == 1:
            hoja, registros, usadas = completas[0]
            res.hojas, res.columnas = [hoja], dict(usadas)
            res.avisos.append(f'sin hoja {medidor}: se usa {hoja}, la única con su código')
            return maxima_de_registros(registros, res, periodo, instante)
        if 'kw' not in res.columnas and completas:
            res.error = (f'{path.name}: {medidor} tiene varias hojas completas ('
                         + ', '.join(h for h, _r, _u in completas)
                         + '); escriba como medidor el nombre de la que quiere')
            return res
        if 'kw' not in res.columnas:
            res.error = f'{path.name} › {", ".join(entera + partes)}: sin columna de kW'
            return res
        return maxima_de_registros(_unir_por_fecha(trozos), res, periodo, instante)


def maximas(rutas: Iterable[Path | str], medidores: Sequence[tuple[str, str]], *, alias=ALIAS,
            periodo: str | None = None, instante: datetime | None = None,
            cancelado: Callable[[], bool] = lambda: False,
            progreso: Callable[[int, int, str], None] = lambda *_a: None,
            cabecera: Cabecera | None = None) -> list[MaximaCabecera]:
    """Máxima de cada ``(alimentador, medidor)``, por separado, sin sumar (RF-29, RF-32).

    Se cancela entre medidores: un medidor se lee entero. ``cabecera``: los libros ya
    abiertos, para no abrirlos otra vez en cada instante de la máxima por barra (022:RF-84):
    con un hilo por instante, cada uno abría su copia de los .xls de ~400 MB y la web se
    quedó sin memoria con Nasca (2026-10-27).
    """
    cabecera = cabecera or Cabecera(rutas, alias)
    out = []
    for n, (alimentador, medidor) in enumerate(medidores, start=1):
        if cancelado():
            break
        progreso(n, len(medidores), medidor)
        try:
            out.append(cabecera.maxima(medidor, alimentador, periodo, instante))
        except DemandaError as exc:
            out.append(MaximaCabecera(medidor=medidor, alimentador=alimentador, error=str(exc)))
    if cabecera.rotos:
        # 025:RF-29: se busca en los demás, y cada resultado dice qué libros no se leyeron.
        aviso = 'no se pudo abrir ' + '; '.join(cabecera.rotos.values())
        for r in out:
            r.avisos.append(aviso)
    return _unir_canales(out)


def _unir_canales(resultados: list[MaximaCabecera]) -> list[MaximaCabecera]:
    """Un canal sin hoja cuyo medidor ya da otro resultado del alimentador no se repite (RF-45).

    «IN111_V18 Y IN111_V119»: V18 ya trae el kW y, por RF-44, el kVAR de IN111; V119
    leería el mismo medidor y daría una segunda fila igual.
    """
    def da(r: MaximaCabecera, base: str) -> bool:
        return (not r.canal_de and r.error is None
                and clave_codigo(base) in (clave_codigo(r.medidor),
                                           clave_codigo(base_del_medidor(r.medidor) or '')))

    out = []
    for r in resultados:
        otro = None
        if r.canal_de and r.error is None:
            otro = next((s for s in resultados if s is not r and s.libro == r.libro and da(s, r.canal_de)
                         and clave_codigo(s.alimentador) == clave_codigo(r.alimentador)), None)
            if otro is None:
                # 025: en el libro de 2025 de IN111 ningún canal tiene hoja; los dos se leen
                # como IN111, y el segundo es la misma fila que el primero.
                otro = next((s for s in out if s.canal_de and s.error is None
                             and clave_codigo(s.canal_de) == clave_codigo(r.canal_de)
                             and s.libro == r.libro
                             and clave_codigo(s.alimentador) == clave_codigo(r.alimentador)), None)
        if otro is None:
            out.append(r)
        else:
            otro.avisos.append(f'{r.medidor}: no tiene hoja; es otro canal de {r.canal_de}, ya incluido aquí')
    return out


# =========================================================================== central térmica
#: Desbalance de la barra de la central admitido, sobre su generación máxima (021:RF-30).
DESBALANCE_MAXIMO = 0.05
#: Rangos intercuartílicos fuera de los cuales un registro de aguas arriba no es demanda
#: sino una maniobra o una transferencia de carga (021:RF-32).
RANGOS_IQR = 3.0

Curva = Sequence[tuple[datetime, float, 'float | None']]


@dataclass
class MaximaConCentral:
    """La máxima de un alimentador con una central en serie en su troncal (spec 021).

    NA205 tiene en su troncal la central de Nasca: la cabecera solo ve lo que entra
    desde la SET, que con la central generando es casi nada (1 123 kW frente a una
    demanda de 10 753 kW el 2026-08-20 16:45). La demanda son dos zonas: aguas arriba
    de la central (cabecera + llegada) y aguas abajo (la salida).
    """

    fecha: str | None = None
    demanda_kw: float | None = None
    arriba_kw: float | None = None
    arriba_kvar: float | None = None
    abajo_kw: float | None = None
    abajo_kvar: float | None = None
    generacion_kw: float | None = None
    generacion_kvar: float | None = None
    cabecera_kw: float | None = None
    cabecera_kvar: float | None = None
    signo_llegada: int = 1
    signo_salida: int = 1
    desbalance_mediana_kw: float | None = None
    generacion_max_kw: float | None = None
    descartados: int = 0
    registros_comunes: int = 0
    registros_cabecera: int = 0
    maxima_cabecera: dict[str, Any] | None = None
    # 021:RF-50: el registro es el coincidente con los demás alimentadores, no la máxima.
    coincidente: bool = False
    periodo: str | None = None
    avisos: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _por_fecha(curva: Curva) -> dict[datetime, tuple[float, float | None]]:
    return {f: (kw, kvar) for f, kw, kvar in curva}


def _mediana(xs: Sequence[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _cuartiles(xs: Sequence[float]) -> tuple[float, float]:
    s = sorted(xs)
    n = len(s)
    return s[n // 4], s[(3 * n) // 4]


def _suma(*xs: float | None) -> float | None:
    return None if any(x is None for x in xs) else sum(xs)  # type: ignore[arg-type]


def demanda_con_central(cabecera: Curva, generacion: Curva, llegada: Curva,
                        salida: Curva, periodo: str | None = None,
                        instante: datetime | None = None) -> MaximaConCentral:
    """Máxima de demanda de un alimentador con una central en su troncal (021:RF-28 a RF-34).

    Las cuatro son curvas ``(fecha, kW, kVAR)``: la cabecera del alimentador, la
    generación de la central, la llegada (el tramo hacia la SET) y la salida (hacia la
    carga). Solo se usan los registros que están en las cuatro.

    El balance de la barra de la central es generación = salida + llegada, con los
    flujos que salen de ella positivos. Cada medidor exporta con su convención: en NA205
    CTNA_BH2 (llegada) es negativo cuando la central está parada y la SET la alimenta.
    Los signos son la combinación que deja la menor mediana de desbalance (RF-29); si ni
    esa queda bajo el 5 % de la generación máxima, la central no se usa (RF-30).
    """
    res = MaximaConCentral(coincidente=instante is not None, periodo=periodo)
    cab, gen, lle, sal = (_por_fecha(c) for c in (cabecera, generacion, llegada, salida))
    res.registros_cabecera = len(cab)
    # La de cabecera con la que se compara, del mismo mes de análisis (013:RF-11).
    del_mes = {f: v for f, v in cab.items() if not periodo or periodo_de_fecha(f) == periodo}
    if del_mes:
        f, kw = max(((f, v[0]) for f, v in del_mes.items()), key=lambda p: (p[1], -p[0].timestamp()))
        res.maxima_cabecera = {'fecha': _iso(f), 'kw': kw}
    comunes = sorted(set(cab) & set(gen) & set(lle) & set(sal))
    res.registros_comunes = len(comunes)
    if len(comunes) < FILAS_DATOS_MINIMAS:
        res.error = (f'solo {len(comunes)} registro(s) con fecha y hora en los cuatro medidores '
                     '(cabecera, generación, llegada y salida)')
        return res

    # RF-29: el orden fija el desempate (determinismo): primero los signos tal cual.
    mejor = None
    for sl, ss in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d = _mediana([abs(gen[t][0] - ss * sal[t][0] - sl * lle[t][0]) for t in comunes])
        if mejor is None or d < mejor[0]:
            mejor = (d, sl, ss)
    desbalance, sl, ss = mejor  # type: ignore[misc]
    res.signo_llegada, res.signo_salida = sl, ss
    res.desbalance_mediana_kw = desbalance
    res.generacion_max_kw = max(gen[t][0] for t in comunes)
    if desbalance > DESBALANCE_MAXIMO * max(res.generacion_max_kw, 1.0):
        res.error = (f'el balance de la barra de la central no cuadra: generación − salida − '
                     f'llegada tiene una mediana de {desbalance:,.1f} kW, más del '
                     f'{DESBALANCE_MAXIMO:.0%} de la generación máxima '
                     f'({res.generacion_max_kw:,.1f} kW); se calibra sin la central')
        return res

    # RF-31: aguas arriba, lo que entra por la cabecera y por la llegada; aguas abajo, la salida.
    arriba = {t: cab[t][0] + sl * lle[t][0] for t in comunes}
    q1, q3 = _cuartiles(list(arriba.values()))
    margen = RANGOS_IQR * (q3 - q1)
    validos = [t for t in comunes if q1 - margen <= arriba[t] <= q3 + margen]
    res.descartados = len(comunes) - len(validos)
    if res.descartados:
        res.avisos.append(f'{res.descartados} registro(s) con la zona aguas arriba a más de '
                          f'{RANGOS_IQR:g} rangos intercuartílicos de su mediana '
                          '(maniobras o transferencias de carga): no cuentan para la máxima')
    if instante is not None:
        # 021:RF-51: el registro coincidente con los demás alimentadores, aunque sea raro.
        if instante not in cab or instante not in comunes:
            res.error = f'sin registro de los cuatro medidores el {_iso(instante)}'
            return res
        if instante not in validos:
            res.avisos.append(f'el registro del {_iso(instante)} tiene la zona aguas arriba fuera '
                              'de lo normal (posible transferencia); se usa por ser el coincidente')
        validos = [instante]
    elif periodo:
        # 013:RF-11: la máxima del mes elegido; el balance y el rango normal, de todo el registro.
        validos = [t for t in validos if periodo_de_fecha(t) == periodo]
    if not validos:
        res.error = ('ningún registro con la zona aguas arriba dentro de lo normal'
                     + (f' en {periodo}' if periodo else ''))
        return res
    # RF-33: el registro de mayor demanda; a igual demanda, el primero.
    t = max(validos, key=lambda x: (arriba[x] + ss * sal[x][0], -x.timestamp()))
    res.fecha = _iso(t)
    res.arriba_kw, res.abajo_kw = arriba[t], ss * sal[t][0]
    res.demanda_kw = res.arriba_kw + res.abajo_kw
    res.arriba_kvar = _suma(cab[t][1], None if lle[t][1] is None else sl * lle[t][1])
    res.abajo_kvar = None if sal[t][1] is None else ss * sal[t][1]
    res.generacion_kw, res.generacion_kvar = gen[t]
    res.cabecera_kw, res.cabecera_kvar = cab[t]
    return res


def curva_de_demanda(cabecera: Curva, generacion: Curva, llegada: Curva, salida: Curva,
                     periodo: str | None = None, instante: datetime | None = None) -> tuple[list[tuple[datetime, float, float | None]], MaximaConCentral]:
    """La demanda del alimentador registro a registro (aguas arriba + aguas abajo), con
    los signos del balance (021:RF-47). Se calcula aquí, con todos los registros: las
    curvas que ve la web van reducidas y sus puntos no caen en las mismas fechas."""
    res = demanda_con_central(cabecera, generacion, llegada, salida, periodo, instante)
    if res.error and res.desbalance_mediana_kw is None:
        return [], res
    cab, lle, sal = (_por_fecha(c) for c in (cabecera, llegada, salida))
    gen = _por_fecha(generacion)
    sl, ss = res.signo_llegada, res.signo_salida
    puntos = []
    for t in sorted(set(cab) & set(gen) & set(lle) & set(sal)):
        q = _suma(cab[t][1], None if lle[t][1] is None else sl * lle[t][1],
                  None if sal[t][1] is None else ss * sal[t][1])
        puntos.append((t, cab[t][0] + sl * lle[t][0] + ss * sal[t][0], q))
    return puntos, res


# =========================================================================== clientes
@dataclass(frozen=True)
class Suministro:
    actual: str
    anterior: str
    sed: str
    radial: str
    fila: int


def leer_suministros(path: Path | str, alias=ALIAS) -> tuple[list[Suministro], list[str]]:
    """Código actual, anterior, SED y radial de cada suministro (RF-33)."""
    libro = _abrir(path)
    campos = ('suministro_act', 'suministro', 'sed', 'radial')
    for hoja in libro.sheet_names:
        filas = _filas(libro, hoja)
        hallada = _buscar_cabecera(filas, campos, alias, ('sed',))
        if hallada is None or not ({'suministro_act', 'suministro'} & set(hallada[1])):
            continue
        i, cols = hallada
        out, avisos = [], []
        if 'suministro_act' not in cols:
            avisos.append(f'{Path(path).name}: sin columna «Suministro Act»; se cruza solo por «Suministro».')
        for n, fila in enumerate(filas[i + 1:], start=i + 2):
            act, ant = _texto(fila, cols.get('suministro_act')), _texto(fila, cols.get('suministro'))
            if act or ant:
                out.append(Suministro(act, ant, _texto(fila, cols['sed']),
                                      _texto(fila, cols.get('radial')), n))
        return out, avisos
    raise DemandaError(f'{Path(path).name}: ninguna hoja tiene «Suministro Act» o «Suministro» y «SED».')


def libros_de_suministros(carpeta: Path | str, alias=ALIAS) -> tuple[dict[Path, tuple], list[str]]:
    """Libros compatibles de una carpeta, por nombre, con su puntaje (004:RF-58/RF-59), y
    los de clientes importantes que había en ella (RF-62/RF-63).

    Los nombres no forman parte del contrato: el guion fijaba «ML_1225.xlsx» y dejaba de
    encontrar la entrega en cuanto cambiaba de mes. Puntaje: códigos actuales, registros
    y, a igual cobertura, el modificado más recientemente.
    """
    candidatos: dict[Path, tuple] = {}
    de_clientes: list[str] = []
    for libro in sorted(Path(carpeta).iterdir(), key=lambda p: (p.name.casefold(), p.name)):
        if (not libro.is_file() or libro.name.startswith('~$')
                or libro.suffix.lower() not in EXTENSIONES):
            continue
        try:
            suministros, _avisos = leer_suministros(libro, alias)
        except (DemandaError, OSError, ValueError):
            continue
        # Los de clientes de mayo a septiembre traen SUMINISTRO y SED en una hoja de
        # detalle: subidos aquí, uno ganaba como tabla de suministros (RF-62).
        if es_libro_clientes(libro, alias):
            de_clientes.append(libro.name)
            continue
        actuales = sum(bool(suministro.actual) for suministro in suministros)
        candidatos[libro] = (actuales, len(suministros), libro.stat().st_mtime_ns,
                             libro.name.casefold())
    return candidatos, de_clientes


def aviso_libros_de_clientes(nombres: Sequence[str]) -> str:
    """El aviso del hueco de suministros con libros de clientes (004:RF-63)."""
    return (f'{", ".join(nombres)}: libro(s) de clientes importantes (hoja «resumen»); '
            'no se usan como suministros: van en «Clientes importantes».')


def descubrir_libro_suministros(fuente: Path | str, alias=ALIAS) -> Path:
    """Elige por contenido el libro de suministros vigente (004:RF-58 a RF-64).

    Un archivo explícito se valida y se conserva (RF-60); en una carpeta gana el de
    mayor puntaje de ``libros_de_suministros``, sin bloquear con varios candidatos.
    """
    path = Path(fuente)
    if path.is_file():
        if es_libro_clientes(path, alias):
            raise DemandaError(f'{path.name} es un libro de clientes importantes (hoja «resumen»): '
                               'va en «Clientes importantes», no en «Suministros».')
        leer_suministros(path, alias)
        return path
    if not path.is_dir():
        raise DemandaError(f'No existe la fuente de suministros: {path}')
    candidatos, de_clientes = libros_de_suministros(path, alias)
    if not candidatos:
        detalle = f' {aviso_libros_de_clientes(de_clientes)}' if de_clientes else ''
        raise DemandaError(f'No hay un libro de suministros compatible en {path.name}.{detalle}')
    return max(candidatos, key=candidatos.__getitem__)


@dataclass
class ClienteImportante:
    codigo: str
    fila: int
    ea: float | None = None
    eri: float | None = None
    pot: float | None = None
    cruzado_por: str = ''           # 'actual' | 'anterior' | ''
    suministro_actual: str = ''
    suministro_anterior: str = ''
    sed: str = ''
    radial: str = ''
    motivo: str = ''
    nombre: str = ''                # 004:RF-56; vacío si el libro no lo trae
    # 004:RF-66: el registro de 15 minutos de su hoja en que se dio su POT, y la reactiva de
    # ese mismo registro (kVAR = ERI × 4), en vez del cociente ERI/EA del mes.
    fecha_registro: str = ''
    q_registro_kvar: float | None = None
    p_registro_kw: float | None = None   # con el instante de su alimentador (004:RF-67)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def registros_de_maxima(path: Path | str, pot_de: Mapping[str, float | None],
                        instante: datetime | None = None,
                        ) -> tuple[dict[str, tuple[str, float, float | None]], list[str]]:
    """El registro de 15 minutos en que cada cliente dio su POT, con su kVAR (004:RF-66).

    El libro de clientes trae, además del resumen, una hoja de 15 minutos por cliente libre
    («maestro_lib» dice cuál: ``numero_suministro`` → ``nombre_hoja_exportacion``) con
    FECHA, HORA, EA, ERI y POT (kW = EA × 4). El usuario, el 2026-10-28: «ubicar la hoja de
    ese cliente y buscar la fecha en que pasó esa EA, y de esa misma fecha sacar el ERI».
    Devuelve ``{código: (fecha y hora, kVAR = ERI × 4, kW = EA × 4 o None)}`` y los avisos;
    un cliente sin hoja o sin ese registro no está, y sigue con su ERI/EA del mes.

    Con ``instante`` (el de la barra de 60 kV de su alimentador, 022:RF-84), el registro de esa
    fecha y hora, con su kW y su kVAR: tomar la POT de cada cliente, cada una de un día, sumaba
    en NA203 9 261 kW de fijas frente a 7 876 medidos y 4 432 kVAR frente a 483, y Nasca dejó
    de cuadrar (2026-10-28). Sin ``instante``, el registro de su POT, sin kW.
    """
    libro = _abrir(path)
    avisos: list[str] = []
    maestro = next((h for h in libro.sheet_names if normalizar(h) == 'maestro lib'), None)
    if maestro is None:
        return {}, []
    filas = _filas(libro, maestro)
    cab = next((i for i, f in enumerate(filas[:FILAS_CABECERA])
                if {'numero suministro', 'nombre hoja exportacion'} <= {normalizar(c) for c in f}), None)
    if cab is None:
        return {}, [f'{Path(path).name} › {maestro}: sin «numero_suministro» ni «nombre_hoja_exportacion».']
    norm = [normalizar(c) for c in filas[cab]]
    i_sum, i_hoja = norm.index('numero suministro'), norm.index('nombre hoja exportacion')
    hoja_de = {clave_codigo(_texto(f, i_sum)): _texto(f, i_hoja) for f in filas[cab + 1:]
               if _texto(f, i_sum) and _texto(f, i_hoja)}
    out: dict[str, tuple[str, float]] = {}
    for codigo, pot in pot_de.items():
        hoja = hoja_de.get(clave_codigo(codigo))
        if not hoja or pot is None or hoja not in libro.sheet_names:
            continue
        datos = _filas(libro, hoja)
        cols = next(({n: j for j, n in enumerate(normalizar(c) for c in f)}
                     for f in datos[:FILAS_CABECERA]
                     if {'fecha', 'hora', 'eri', 'pot'} <= {normalizar(c) for c in f}), None)
        if cols is None:
            avisos.append(f'{codigo}: la hoja «{hoja}» no tiene FECHA, HORA, ERI y POT.')
            continue
        if instante is not None:
            buscado = (instante.strftime('%d/%m/%Y'), instante.strftime('%H:%M'))
            fila = next((f for f in datos if (_texto(f, cols['fecha']), _texto(f, cols['hora'])[:5]) == buscado),
                        None)
        else:
            tol = max(1e-6, 1e-4 * abs(pot))
            fila = next((f for f in datos if numero(_celda(f, cols['pot'])) is not None
                         and abs(numero(_celda(f, cols['pot'])) - pot) <= tol), None)
        eri = numero(_celda(fila, cols['eri'])) if fila is not None else None
        if fila is None or eri is None:
            que = f'el registro del {instante}' if instante is not None else f'su POT {pot:g} kW'
            avisos.append(f'{codigo}: {que} no está en la hoja «{hoja}»; '
                          'su kVAR con el ERI/EA del mes (004:RF-66).')
            continue
        ea = numero(_celda(fila, cols['ea'])) if 'ea' in cols else None
        kw = ea * 4.0 if instante is not None and ea is not None else None
        out[codigo] = (f"{_texto(fila, cols['fecha'])} {_texto(fila, cols['hora'])}".strip(), eri * 4.0, kw)
    return out, avisos


def _hojas_resumen(nombres: Sequence[str]) -> list[str]:
    """Hojas «resumen» de un libro de clientes: la exacta primero (RF-34)."""
    hojas = [h for h in nombres if normalizar(h) == 'resumen']
    return hojas + [h for h in nombres if 'resumen' in normalizar(h) and h not in hojas]


def es_libro_clientes(path: Path | str, alias=ALIAS) -> bool:
    """Hoja «resumen» con el código del cliente: es de clientes importantes (004:RF-62)."""
    try:
        libro = _abrir(path)
        hojas = _hojas_resumen(libro.sheet_names)
        return bool(hojas) and _buscar_cabecera(
            _filas(libro, hojas[0]), ('cliente_codigo',), alias, ('cliente_codigo',)) is not None
    except (DemandaError, OSError, ValueError):
        return False


#: Los cuatro libros de la demanda medida y cómo se nombran en un aviso (025:RF-25b).
TIPOS_DEMANDA = {'medidores': 'libro de medidores por alimentador',
                 'cabecera': 'medición de cabecera', 'clientes': 'clientes importantes',
                 'suministros': 'libro de suministros'}
_HOJAS_A_MIRAR = 3          # hojas de un libro que se miran para saber de qué es


def tipo_de_libro(path: Path | str, alias=ALIAS) -> str | None:
    """De qué es un libro por su contenido: medidores, cabecera, clientes o suministros.

    Solo la cabecera de sus primeras hojas (``nrows``): un libro de cabecera de 400 MB no
    se lee entero para saber qué es. ``None`` si no se abre o no es de ninguno.
    """
    try:
        libro = _abrir(path)
    except DemandaError:
        return None
    if _hojas_resumen(libro.sheet_names):
        return 'clientes'
    for hoja in libro.sheet_names[:_HOJAS_A_MIRAR]:
        try:
            filas = libro.get_sheet_by_name(hoja).to_python(
                skip_empty_area=False, nrows=FILAS_CABECERA + FILAS_DATOS_MINIMAS)
        except Exception:  # noqa: BLE001 - una hoja ilegible no dice de qué es el libro
            continue
        if _buscar_cabecera(filas, ('alimentador', 'medidor'), alias, ('alimentador', 'medidor')):
            return 'medidores'
        hallada = _buscar_cabecera(filas, ('suministro_act', 'suministro', 'sed'), alias, ('sed',))
        if hallada and {'suministro_act', 'suministro'} & set(hallada[1]):
            return 'suministros'
        for fila in filas[:FILAS_CABECERA]:
            if 'kw' in columnas(fila, MAGNITUDES, alias) and any(
                    normalizar(c) in alias['fecha'] for c in fila):
                return 'cabecera'
    return None


def clasificar_carpeta_demanda(carpeta: Path | str, alias=ALIAS) -> tuple[dict[str, Path], list[str]]:
    """Qué es cada carpeta (o libro suelto) de la carpeta de demanda, por su contenido
    (025:RF-25b, RF-25c).

    Cada empresa, y el mismo usuario, organiza las carpetas a su manera: en Electro Dunas
    son «1.-medidoralimentador», «2.-medicioncabecera»…, y nada en el código puede contar
    con esos nombres. De cada carpeta se mira un libro de cada año (o el primero). El de
    medidores es un libro; los demás, su carpeta, con sus años. Un tipo en dos sitios, o en
    ninguno, no se elige: se dice.
    """
    from .libros_por_anio import arbol_de_libros, es_libro

    raiz = Path(carpeta)
    if not raiz.is_dir():
        raise DemandaError(f'No existe la carpeta de demanda: {raiz}')
    halladas: dict[str, list[Path]] = {}
    for hijo in sorted(raiz.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
        if hijo.is_dir():
            libros = arbol_de_libros(hijo)
            muestra = list({x.anio: x for x in reversed(libros)}.values()) or libros[:1]
            tipos = {t for t in (tipo_de_libro(x.ruta, alias) for x in muestra) if t}
            if len(tipos) != 1:
                continue
            tipo = tipos.pop()
            destino = hijo
            if tipo == 'medidores':
                # El de medidores es uno: el más reciente si la carpeta trae varios.
                destino = max((x.ruta for x in libros), key=lambda p: p.stat().st_mtime_ns)
        elif es_libro(hijo):
            tipo, destino = tipo_de_libro(hijo, alias), hijo
            if tipo is None:
                continue
        else:
            continue
        halladas.setdefault(tipo, []).append(destino)
    out, avisos = {}, []
    for tipo, nombre in TIPOS_DEMANDA.items():
        sitios = halladas.get(tipo, [])
        if len(sitios) == 1:
            out[tipo] = sitios[0]
        elif sitios:
            avisos.append(f'{nombre} ({tipo}) en varias carpetas: '
                          + ', '.join(p.relative_to(raiz).parts[0] for p in sitios)
                          + '; indique cuál por opción.')
        else:
            avisos.append(f'Ninguna carpeta trae {nombre} ({tipo}).')
    return out, avisos


def leer_clientes(path: Path | str, alias=ALIAS) -> tuple[list[ClienteImportante], list[str]]:
    """Hoja resumen de clientes importantes, en cualquiera de sus dos formatos (RF-34)."""
    libro = _abrir(path)
    hojas = _hojas_resumen(libro.sheet_names)
    if not hojas:
        raise DemandaError(f'{Path(path).name}: no tiene hoja «resumen».')
    filas = _filas(libro, hojas[0])
    hallada = _buscar_cabecera(filas, ('cliente_codigo', 'ea', 'eri', 'pot', 'cliente_nombre'), alias,
                               ('cliente_codigo',))
    if hallada is None:
        raise DemandaError(f'{Path(path).name} › {hojas[0]}: sin columna «Nis» ni «Suministro».')
    i, cols = hallada
    faltan = [c.upper() for c in ('ea', 'eri', 'pot') if c not in cols]
    avisos = [f'{Path(path).name} › {hojas[0]}: sin columna de {", ".join(faltan)}.'] if faltan else []
    vistos: dict[str, int] = {}
    out: list[ClienteImportante] = []
    for n, fila in enumerate(filas[i + 1:], start=i + 2):
        codigo = _texto(fila, cols['cliente_codigo'])
        if not codigo:
            continue
        clave = clave_codigo(codigo)
        if clave in vistos:
            avisos.append(f'{codigo}: repetido en la fila {n} (se usa la fila {vistos[clave]}).')
            continue
        vistos[clave] = n
        out.append(ClienteImportante(
            codigo=codigo, fila=n, ea=numero(_celda(fila, cols.get('ea'))),
            eri=numero(_celda(fila, cols.get('eri'))), pot=numero(_celda(fila, cols.get('pot'))),
            nombre=_texto(fila, cols.get('cliente_nombre')) if 'cliente_nombre' in cols else '',
        ))
    return out, avisos


def cruzar(clientes: Sequence[ClienteImportante], suministros: Sequence[Suministro],
           ) -> tuple[list[ClienteImportante], list[ClienteImportante]]:
    """Cada cliente con su suministro: por el código actual y, si no, por el anterior (RF-35).

    En los libros de enero a abril el ``Nis`` casa con ``Suministro`` y no con
    ``Suministro Act``; en los de mayo a julio, al revés: el libro de suministros es la
    tabla de renumeración. Se dice por cuál cruzó cada uno.
    """
    por_actual: dict[str, Suministro] = {}
    por_anterior: dict[str, Suministro] = {}
    for s in suministros:
        if s.actual:
            por_actual.setdefault(clave_codigo(s.actual), s)
        if s.anterior:
            por_anterior.setdefault(clave_codigo(s.anterior), s)
    cruzados, aparte = [], []
    for c in clientes:
        clave = clave_codigo(c.codigo)
        s, via = por_actual.get(clave), 'actual'
        if s is None:
            s, via = por_anterior.get(clave), 'anterior'
        if s is None:
            c.motivo = 'no está en el libro de suministros (ni como actual ni como anterior)'
            aparte.append(c)
            continue
        c.cruzado_por, c.suministro_actual, c.suministro_anterior = via, s.actual, s.anterior
        c.sed, c.radial = s.sed, s.radial
        if not s.sed:
            c.motivo = f'cruza por el código {via} pero el suministro no tiene SED'
            aparte.append(c)
        else:
            cruzados.append(c)
    return cruzados, aparte


def del_alimentador(cruzados: Sequence[ClienteImportante], aparte: Sequence[ClienteImportante],
                    alimentadores: Iterable[str],
                    ) -> tuple[list[ClienteImportante], list[ClienteImportante], int]:
    """Solo los clientes cuyo suministro cuelga de esos alimentadores, por su radial (RF-43).

    El operador cruza los clientes para repartir la máxima de un alimentador: los 257
    cruzados de toda la empresa le sobran. De los no cruzados quedan los que cruzan sin
    SED pero con ese radial, y los que no están en el libro de suministros, porque de
    esos no se sabe el alimentador y podrían ser suyos. Devuelve también cuántos
    cruzados quedaron fuera por ser de otro alimentador.
    """
    claves = {clave_codigo(a) for a in alimentadores if str(a).strip()}
    suyo = [c for c in cruzados if clave_codigo(c.radial) in claves]
    otros = [c for c in aparte if not c.cruzado_por or clave_codigo(c.radial) in claves]
    return suyo, otros, len(cruzados) - len(suyo)


# =========================================================================== salida
CABECERA_COLUMNAS = (
    ('alimentador', 'Alimentador'), ('medidor', 'Medidor'), ('libro', 'Libro'), ('hojas', 'Hoja(s)'),
    ('fecha', 'Fecha y hora del kW máximo'), ('kw', 'kW máximo'), ('kvar', 'kVAR'), ('kva', 'kVA'),
    ('fp', 'FP'), ('kva_calculado', 'kVA calculado'), ('fp_calculado', 'FP calculado'),
    ('error', 'Error'), ('avisos', 'Avisos'),
)
CLIENTE_COLUMNAS = (
    ('codigo', 'Nis / Suministro'), ('nombre', 'Cliente'), ('cruzado_por', 'Cruzado por'),
    ('suministro_actual', 'Suministro Act'), ('suministro_anterior', 'Suministro'),
    ('sed', 'SED'), ('radial', 'Radial'), ('ea', 'EA'), ('eri', 'ERI'), ('pot', 'Pot'),
    ('motivo', 'Motivo'),
    # 004:RF-66, al final: las columnas de siempre no cambian de letra en el Excel.
    ('fecha_registro', 'Registro de su Pot'), ('q_registro_kvar', 'kVAR en él'),
)


def escribir_excel(destino: Path | str, *, cabecera: Sequence[dict] = (),
                   clientes: Sequence[dict] = (), no_cruzados: Sequence[dict] = ()) -> Path:
    """Libro con la máxima de cabecera, los clientes cruzados y los no cruzados (RF-38)."""
    from openpyxl import Workbook

    def valor(v: Any) -> Any:
        if isinstance(v, (list, tuple)):
            return '; '.join(map(str, v))
        if isinstance(v, bool):
            return 'sí' if v else ''
        return v

    wb = Workbook()
    wb.remove(wb.active)
    for titulo, filas, cols in (('Cabecera', cabecera, CABECERA_COLUMNAS),
                                ('Clientes', clientes, CLIENTE_COLUMNAS),
                                ('No cruzados', no_cruzados, CLIENTE_COLUMNAS)):
        hoja = wb.create_sheet(titulo)
        hoja.append([t for _k, t in cols])
        for fila in filas:
            hoja.append([valor(fila.get(k)) for k, _t in cols])
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


# =========================================================================== barras de SET
@dataclass(frozen=True)
class MedidorBarra:
    """Una fila «Barra» del libro de medidores por alimentador (022:RF-37).

    En Electro Dunas: «Barra», B-PA2T1, 22,9, PA es la barra de 22,9 kV del transformador 1
    de la SET Paracas; «Barra CT», CT_PEDREG, 10, PE, la central en la barra de 10 kV de
    Pedregal (RF-44).
    """

    medidor: str
    kv: float | None
    siglas: str
    central: bool
    fila: int
    alimentador: str = ''           # «Barra/CHI201»: la barra suelta de ese alimentador
    rotulo: str = ''                # lo que dice la columna: «Barra60KV_T1», «Barra CT10KV»


def _es_central(tipo: str) -> bool:
    """«Barra CT10KV», «CT_Barra10KV», «Barra CT», «CTBarra»: la barra de una central (RF-44).
    Antes solo valía «ct» como palabra suelta o al principio, y CT_PEDREG del libro real
    («Barra CT10KV») se sumaba como un transformador más de Pedregal (2026-10-27)."""
    return re.search(r'(?:^|\s)ct', tipo) is not None


def _partir_medidores_de_barra(celda: str) -> list[str]:
    """Una celda con varios medidores de barra: los de siempre (``partir_medidores``) y los
    pegados con «Y» entre un número y el siguiente: B1T1_V18YB1T1_V19YB1T1_V8, la barra
    de 10 kV del T1 de Ica Norte, son tres medidores (libro real, 2026-10-27)."""
    return [p for parte in partir_medidores(celda) for p in re.split(r'(?<=\d)Y(?=[A-Z])', parte) if p]


def leer_medidores_de_barra(path: Path | str, alias=ALIAS) -> list[MedidorBarra]:
    """Las filas de barra del libro: las que en «código alimentador» dicen «Barra»."""
    libro = _abrir(path)
    for hoja in libro.sheet_names:
        filas = _filas(libro, hoja)
        hallada = _buscar_cabecera(filas, ('alimentador', 'medidor', 'nivel', 'siglas'), alias,
                                   ('alimentador', 'medidor'))
        if hallada is None:
            continue
        i, cols = hallada
        out = []
        for n, fila in enumerate(filas[i + 1:], start=i + 2):
            crudo = _texto(fila, cols['alimentador'])
            tipo = normalizar(crudo.split('/')[0])
            med = ' '.join(_texto(fila, cols['medidor']).split())
            if 'barra' not in tipo or not med:
                continue
            for parte in _partir_medidores_de_barra(med):
                # 022:RF-44: un medidor que empieza por CT es de una central térmica
                # (CT_PEDREG, CT_LUREN, CT_BH4 NA), diga lo que diga su rótulo.
                out.append(MedidorBarra(parte, numero(_celda(fila, cols.get('nivel'))),
                                        ' '.join(_texto(fila, cols.get('siglas')).split()).upper(),
                                        _es_central(tipo) or parte.upper().startswith('CT'), n,
                                        crudo.split('/', 1)[1].strip().upper() if '/' in crudo else '',
                                        crudo))
        return out
    return []


def transformador_de(medidor: str, rotulo: str = '') -> str:
    """El transformador de la SET que mide un medidor de barra (022:RF-87): «T1», «T2» o
    «T3». Lo dice el rótulo («Barra60KV_T2») o el nombre del medidor (B-PA6T2, CAB1T2,
    TA6TR2: la última «T» o «TR» con su número). Vacío si no se sabe."""
    for texto in (rotulo, medidor):
        m = re.search(r'T(?:R)?\s*(\d)\s*$', ' '.join(str(texto or '').split()).upper())
        if m:
            return f'T{m.group(1)}'
    return ''


def _kv_del_rotulo(rotulo: str) -> float | None:
    """La tensión que dice el rótulo de la fila: «Barra22,9KV_T2» → 22,9; sin ella, ``None``."""
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*kv', rotulo, re.I)
    return float(m.group(1).replace(',', '.')) if m else None


def maxima_de_barra(curvas: Sequence[Sequence[tuple[datetime, float, float | None]]],
                    periodo: str | None = None) -> dict[str, Any] | None:
    """La máxima de la suma, registro a registro, de los medidores de una barra (022:RF-39).

    Solo cuentan las fechas que tienen todos (los dos transformadores de Pueblo Nuevo
    suman a la vez); con ``periodo``, las de ese mes (013:RF-11).
    """
    por_fecha: list[dict[datetime, tuple[float, float | None]]] = [
        {f: (kw, kvar) for f, kw, kvar in c if f is not None and kw is not None} for c in curvas]
    if not por_fecha:
        return None
    comunes = set(por_fecha[0]).intersection(*por_fecha[1:])
    if periodo:
        comunes = {f for f in comunes if en_periodo(f, periodo)}
    if not comunes:
        return None
    suma = {f: (sum(d[f][0] for d in por_fecha),
                sum((d[f][1] or 0.0) for d in por_fecha)) for f in comunes}
    fecha = max(suma, key=lambda f: (suma[f][0], -f.timestamp()))
    return {'fecha': fecha, 'kw': suma[fecha][0], 'kvar': suma[fecha][1], 'registros': len(comunes)}


#: Por encima de esta tensión un medidor de barra es de alta (60 kV, 220 kV) (022:RF-43).
KV_MAX_MEDIA = 35.0
#: Hasta esta tensión, la alta es la barra de 60 kV de la SET, que fija el instante de todos
#: sus alimentadores (022:RF-84); por encima (220 kV) no se usa: es la red de transmisión.
KV_MAX_SUBTRANSMISION = 72.5


@dataclass
class BarraMedida:
    """Una barra de SET (o suelta) con sus medidores y sus alimentadores (022:RF-38)."""

    clave: str                      # «SET 32 22,9 kV», «Suelta CHN 10 kV»…
    set_codigo: str
    kv: float
    medidores: list[str] = field(default_factory=list)
    centrales: list[str] = field(default_factory=list)
    alimentadores: list[str] = field(default_factory=list)
    suelta: bool = False
    alta: bool = False              # 022:RF-84: la barra de 60 kV de la SET
    de_alta: str = ''
    """La barra de 60 kV que da el instante a esta de media (022:RF-84): su valor y sus
    alimentadores, en la fecha y hora de la máxima de la de 60 kV, no en la suya."""
    transformadores: dict[str, str] = field(default_factory=dict)
    """El transformador de la SET de cada medidor (022:RF-87): una SET tiene 1, 2 o 3, y la
    barra suma los de todos, registro a registro."""


def barras_de_calibracion(estructura, medidores: Sequence[MedidorBarra],
                          alimentadores: Sequence[str],
                          kv_de: dict[str, float],
                          centrales_en_tramo: Mapping[str, str] | None = None,
                          ) -> tuple[list[BarraMedida], list[str]]:
    """Las barras con medidor y los alimentadores marcados de cada una (022:RF-38, RF-42 a RF-46).

    Un medidor de barra va a la barra de su SET (por sus siglas, código o nombre, RF-85) y
    de su nivel; uno de 220 kV no se usa (RF-43). Unas siglas sin SET en media son una barra
    suelta propia, de los alimentadores con ese prefijo, y «Barra/CHI201», la de ese
    alimentador (RF-45). Cada alimentador marcado va a la barra de su SET y su tensión; si
    su tensión no se sabe y su SET tiene una sola barra con medidor, a esa.

    Con barra de 60 kV en la SET (RF-84), sus barras de 22,9 y 10 kV llevan ``de_alta``: se
    leen y calibran en el instante de la máxima de la de 60 kV; los alimentadores de la SET
    sin barra de media con medidor van a la de 60 kV, con el mismo instante. Sin ninguna
    barra con medidor, se calibran con su propia máxima (RF-42).
    """
    barras: dict[str, BarraMedida] = {}
    avisos: list[str] = []
    set_de_medidor: dict[str, str] = {}
    en_tramo = {clave_codigo(k): v for k, v in (centrales_en_tramo or {}).items() if v}
    pedidas = {st.codigo for f in alimentadores if (st := estructura.set_de(f)) is not None}
    del_libro: list[tuple[str, set[str]]] = []

    def avisar(texto: str, *sets: str) -> None:
        del_libro.append((texto, {s for s in sets if s}))
    for m in medidores:
        if m.central and clave_codigo(m.medidor) in en_tramo:
            # RF-88: la central conectada en un tramo de media de su alimentador (CT_BH4 NA
            # en la troncal de 22,9 kV de NA205) no va a la barra de la SET: se mide con su
            # alimentador, en su mismo instante (021:RF-28).
            avisos.append(f'{m.medidor}: central en el tramo de {en_tramo[clave_codigo(m.medidor)]}'
                          f' ({m.kv:g} kV), no en la barra; se mide con su alimentador (022:RF-88).'
                          if m.kv is not None else
                          f'{m.medidor}: central en el tramo de {en_tramo[clave_codigo(m.medidor)]} (022:RF-88).')
            continue
        if m.kv is None or m.kv > KV_MAX_SUBTRANSMISION:
            continue
        st = estructura.set_de_texto(m.siglas) if m.siglas else None
        if st is None and not m.alimentador:
            # RF-85: sin SET en su columna (TMB6T2, B-PU6T1), la del nombre del medidor.
            st = estructura.set_de_medidor(m.medidor)
            if st is not None:
                avisar(f'{m.medidor}: su columna SET '
                       + (f'«{m.siglas}» no es de la estructura' if m.siglas else 'está vacía')
                       + f'; por su nombre, {st.rotulo} (022:RF-85).', st.codigo)
        kv_rotulo = _kv_del_rotulo(m.rotulo)
        if kv_rotulo is not None and abs(kv_rotulo - m.kv) > 0.05 * m.kv:
            avisar(f'{m.medidor}: «{m.rotulo}» dice {kv_rotulo:g} kV y su nivel {m.kv:g} kV; '
                   'vale el nivel (022:RF-85).', st.codigo if st else '')
        if st is not None:
            antes = set_de_medidor.setdefault(m.medidor, st.codigo)
            if antes != st.codigo:
                avisar(f'{m.medidor}: en dos SET del libro, {antes} y {st.codigo}; '
                       'revise el libro (022:RF-85).', antes, st.codigo)
        if m.kv > KV_MAX_MEDIA:
            # RF-84: la barra de 60 kV de la SET; sin SET no se usa, ni suelta (RF-86).
            if st is None or m.central:
                avisos.append(f'{m.medidor}: medidor de {m.kv:g} kV '
                              + ('de una central' if st is not None else
                                 f'cuya SET «{m.siglas or "(vacía)"}» no está en la estructura')
                              + '; no se usa (022:RF-86).')
                continue
            clave = f'{st.codigo} {m.kv:g} kV'
            b = barras.setdefault(clave, BarraMedida(clave, st.codigo, float(m.kv), alta=True))
            b.medidores.append(m.medidor)
            b.transformadores[m.medidor] = transformador_de(m.medidor, m.rotulo)
            continue
        if m.alimentador:
            clave, codigo, suelta = f'Suelta {m.alimentador} {m.kv:g} kV', m.alimentador, True
        elif st is not None:
            clave, codigo, suelta = f'{st.codigo} {m.kv:g} kV', st.codigo, False
        else:
            clave, codigo, suelta = f'Suelta {m.siglas} {m.kv:g} kV', m.siglas, True
            avisos.append(f'{m.medidor}: las siglas {m.siglas or "(vacías)"} no son de ninguna SET '
                          'de la estructura; barra suelta propia (022:RF-45).')
        b = barras.setdefault(clave, BarraMedida(clave, codigo, float(m.kv), suelta=suelta))
        (b.centrales if m.central else b.medidores).append(m.medidor)
        if not m.central:
            b.transformadores[m.medidor] = transformador_de(m.medidor, m.rotulo)
    alta_de = {b.set_codigo: b for b in barras.values() if b.alta}
    for alta in alta_de.values():
        # RF-87: los transformadores medidos en 60 kV y en media deberían ser los mismos;
        # si no, la suma de una barra deja fuera lo que pasa por el que falta.
        arriba = {t for t in alta.transformadores.values() if t}
        abajo = {t for b in barras.values() if not b.alta and not b.suelta
                 and b.set_codigo == alta.set_codigo for t in b.transformadores.values() if t}
        if arriba and abajo and arriba != abajo:
            avisar(f'{alta.set_codigo}: transformadores medidos en 60 kV '
                   f'{", ".join(sorted(arriba))} y en media {", ".join(sorted(abajo))} (022:RF-87).',
                   alta.set_codigo)
    # Los avisos del libro, solo de las SET de los alimentadores pedidos: al calibrar Nasca
    # salían los de Tambo de Mora o Ica (2026-10-27); los que no son de ninguna SET, siempre.
    avisos[:0] = [t for t, sets in del_libro if not sets or not pedidas or sets & pedidas]
    for b in barras.values():
        if not b.alta and not b.suelta and b.set_codigo in alta_de:
            b.de_alta = alta_de[b.set_codigo].clave                         # RF-84
    for f in alimentadores:
        st = estructura.set_de(f)
        alta = alta_de.get(st.codigo) if st is not None else None
        candidatas = []
        if st is not None:
            # Con la de 60 kV, también la de media con solo su central: la central se mide
            # en el instante de la de 60 kV y se pone en su barra (RF-44).
            candidatas = [b for b in barras.values() if not b.suelta and not b.alta
                          and b.set_codigo == st.codigo and (b.medidores or (alta and b.centrales))]
        if not candidatas and alta is None:
            candidatas = [b for b in barras.values() if b.suelta and b.medidores and (
                b.set_codigo == f.upper() or (len(b.set_codigo) < len(f) and f.upper().startswith(b.set_codigo)))]
        kv = kv_de.get(f)
        if kv is not None:
            candidatas = [b for b in candidatas if abs(b.kv - kv) <= 0.05 * kv]
        elif len(candidatas) > 1:
            if alta is None:
                avisos.append(f'{f}: no se sabe su tensión y su SET tiene varias barras con medidor; '
                              'se calibra con su propia máxima.')
                continue
            candidatas = []                                  # RF-84: a la de 60 kV, mismo instante
        if candidatas:
            candidatas[0].alimentadores.append(f)
        elif alta is not None:
            alta.alimentadores.append(f)
    usadas = {b.de_alta for b in barras.values() if b.alimentadores and b.de_alta}
    return [b for b in barras.values() if b.alimentadores or b.clave in usadas], avisos


def valor_de_barra_en(curvas: Sequence[Sequence[tuple[datetime, float, float | None]]],
                      fecha: datetime) -> dict[str, Any] | None:
    """La suma de los medidores de una barra en una fecha y hora dada (022:RF-84): la de 22,9
    o 10 kV en el instante de la máxima de su barra de 60 kV. ``None`` si alguno no tiene
    ese registro: la barra no se suma a medias."""
    puntos = [next(((kw, kvar) for f, kw, kvar in c if f == fecha and kw is not None), None)
              for c in curvas]
    if not puntos or any(p is None for p in puntos):
        return None
    return {'fecha': fecha, 'kw': sum(p[0] for p in puntos),
            'kvar': sum((p[1] or 0.0) for p in puntos), 'registros': 1}


def maximas_por_barra(libros, alias, barras, pares, periodo, avisos, *, progreso=lambda *_a: None,
                      log=lambda _t: None, cancelado=lambda: False):
    """La máxima de cada barra de SET y sus alimentadores en ese instante (022:RF-37 a RF-46,
    RF-84 a RF-91), sin nada de la web: corre en el proceso de su trabajo (027:RF-25). Devuelve
    ``(resultados, barras_informe, avisos, maximas_de_barra, instantes)``."""
    from collections import defaultdict

    def duenio(a: str) -> str:
        return a[len('Central '):].strip() if a.lower().startswith('central ') else a

    avisos = list(avisos)
    # Los libros se abren una vez para la barra y todos sus instantes (022:RF-84).
    cabecera = Cabecera(libros, alias)
    de_barra = maximas(libros, [(b.clave, m) for b in barras for m in b.medidores + b.centrales],
                       alias=alias, cancelado=cancelado, cabecera=cabecera)
    # Las curvas de los alimentadores de las SET con barra de 60 kV, con los libros ya
    # abiertos: su instante tiene que tener registro en todos (022:RF-91).
    con_alta = {f for b in barras if b.alta or b.de_alta for f in b.alimentadores}
    de_alimentador = maximas(libros, [(a, m) for a, m in pares if duenio(a).upper() in con_alta],
                             alias=alias, periodo=periodo, cancelado=cancelado,
                             cabecera=cabecera) if con_alta else []
    curva_de = {(r.alimentador, r.medidor): r.curva for r in de_barra if r.curva}
    fechas_de: dict[str, list[set]] = defaultdict(list)
    for r in de_alimentador:
        if r.curva:
            fechas_de[duenio(r.alimentador).upper()].append({f for f, kw, _q in r.curva if kw is not None})

    def comunes_de_la_set(alta_clave: str) -> set | None:
        """Los registros que tienen todos los medidores de los alimentadores de la SET de
        esa barra de 60 kV (022:RF-91), o ``None`` si ninguno tiene curva."""
        feeders = {f for b in barras if b.clave == alta_clave or b.de_alta == alta_clave
                   for f in b.alimentadores}
        conjuntos = [s for f in feeders for s in fechas_de.get(f, [])]
        return set.intersection(*conjuntos) if conjuntos else None
    instantes: dict[str, datetime] = {}
    info = []
    maxima_alta: dict[str, dict] = {}
    # 022:RF-84: primero la máxima de cada barra de 60 kV; sus barras de 22,9 y 10 kV se
    # leen después, en esa misma fecha y hora, y no en la suya.
    for b in sorted(barras, key=lambda x: not x.alta):
        # Un transformador sin registros en el periodo (B-PA6T1 en julio de 2026) no entra
        # en la suma: con él, ninguna fecha era común y la barra se quedaba sin instante.
        sin_curva = [m for m in b.medidores if not curva_de.get((b.clave, m))]
        if sin_curva and len(sin_curva) < len(b.medidores):
            avisos.append(f'{b.clave}: {", ".join(sin_curva)} sin registros'
                          + (f' en {periodo}' if periodo else '')
                          + '; la barra se suma con los demás (022:RF-84).')
        curvas = [curva_de[(b.clave, m)] for m in b.medidores if curva_de.get((b.clave, m))]
        alta = maxima_alta.get(b.de_alta) if b.de_alta else None
        if alta is not None:
            mx = valor_de_barra_en(curvas, alta['fecha']) if curvas else None
            if mx is None and b.medidores:
                avisos.append(f'{b.clave}: sin el registro de {", ".join(b.medidores)} el '
                              f'{alta["fecha"]}, el de la máxima de {b.de_alta}; sus alimentadores '
                              'se calibran igual en esa fecha y hora (022:RF-84).')
            mx = mx or {'fecha': alta['fecha'], 'kw': None, 'kvar': None, 'registros': 0}
        else:
            mx = maxima_de_barra(curvas, periodo) if curvas else None
            comunes = comunes_de_la_set(b.clave) if b.alta and mx is not None else None
            if comunes is not None and mx['fecha'] not in comunes:
                # 022:RF-91: CHNB6T1 dio su máxima el 2026-07-24 11:45 y CHN101, CHN102 y
                # CHN201 no tienen ese registro: se quedaban sin calibrar. La máxima de la
                # barra, entre los registros que tienen también todos sus alimentadores.
                filtradas = [[x for x in c if x[0] in comunes] for c in curvas]
                otra = maxima_de_barra(filtradas, periodo) if all(filtradas) else None
                if otra is not None:
                    avisos.append(f"{b.clave}: su máxima del {mx['fecha']} no tiene registro en todos "
                                  f"sus alimentadores; se toma la del {otra['fecha']}, la mayor con "
                                  'registro en todos (022:RF-91).')
                    mx = otra
                else:
                    avisos.append(f'{b.clave}: ningún registro común con sus alimentadores'
                                  + (f' en {periodo}' if periodo else '')
                                  + '; los que no tengan su registro, con su propia máxima (022:RF-91).')
            if mx is None:
                avisos.append(f'{b.clave}: sin registros comunes de {", ".join(b.medidores)}'
                              + (f' en {periodo}' if periodo else '')
                              + ('; sus barras de media, con su propia máxima (022:RF-84).' if b.alta else
                                 '; sus alimentadores, con su propia máxima (022:RF-42).'))
                continue
        if b.alta:
            maxima_alta[b.clave] = mx
        centrales = []
        for m in b.centrales:
            punto = next((x for x in curva_de.get((b.clave, m)) or [] if x[0] == mx['fecha']), None)
            centrales.append({'medidor': m, 'kw': punto[1] if punto else None,
                              'kvar': punto[2] if punto else None})
        for f in b.alimentadores:
            instantes[f] = mx['fecha']
        info.append({'clave': b.clave, 'set': b.set_codigo, 'kv': b.kv, 'suelta': b.suelta,
                     'alta': b.alta, 'de_alta': b.de_alta if alta is not None else '',  # RF-84
                     'transformadores': b.transformadores,                         # RF-87
                     'medidores': b.medidores, 'centrales': centrales,
                     'alimentadores': b.alimentadores, 'fecha': mx['fecha'].isoformat(sep=' '),
                     'kw': mx['kw'], 'kvar': mx['kvar'], 'registros': mx['registros']})
        valor = f'{mx["kw"]:,.1f} kW' if mx['kw'] is not None else 'sin registro'
        suma = ' + '.join(f'{m} ({b.transformadores[m]})' if b.transformadores.get(m) else m
                          for m in b.medidores)
        log(f'  {b.clave}: {valor} el {mx["fecha"]} ({suma})'
                + (f', instante de {b.de_alta}' if alta is not None else '')
                + (f'; {", ".join(b.alimentadores)} en esa fecha y hora' if b.alimentadores else ''))
    # 022:RF-89: la barra de 60 kV tiene que dar al menos lo que dan sus barras de media en
    # su instante, menos la generación de sus centrales. CHNB6T1 (Chincha Nueva) marcó 8,3
    # frente a ~3 300 kW de media (2026-10-28): otra unidad (MW) o un medidor mal
    # configurado. El instante se usa igual (la máxima no cambia con la unidad), y se avisa.
    for alta in (x for x in info if x['alta'] and x['kw'] is not None):
        media = [x for x in info if x.get('de_alta') == alta['clave'] and x['kw'] is not None]
        neto = (sum(x['kw'] for x in media)
                - sum(c['kw'] or 0.0 for x in media for c in x['centrales']))
        if media and neto > 0 and alta['kw'] < 0.5 * neto:
            avisos.append(f"{alta['clave']}: {alta['kw']:,.1f} kW frente a {neto:,.1f} kW de sus barras de "
                          f"media en ese instante; revise la unidad (¿MW?) o el medidor "
                          f"{', '.join(alta['medidores'])}. El instante se usa igual (022:RF-89).")
    grupos: dict[Any, list[tuple[str, str]]] = defaultdict(list)
    for a, m in pares:
        grupos[instantes.get(duenio(a).upper())].append((a, m))
    # Cada instante (uno por SET con barra de 60 kV) con los mismos libros ya abiertos: un
    # hilo por instante abría cada uno su copia de los .xls de ~400 MB y la web se quedó sin
    # memoria con Nasca (2026-10-27); abrir es lo que cuesta, no buscar un registro.
    res = []
    for inst, ps in grupos.items():
        res += maximas(libros, ps, alias=alias, periodo=None if inst else periodo,
                       instante=inst, cancelado=cancelado, cabecera=cabecera)
    orden = {m: i for i, (_a, m) in enumerate(pares)}
    res.sort(key=lambda r: orden.get(r.medidor, len(orden)))
    return res, info, avisos, de_barra, instantes
