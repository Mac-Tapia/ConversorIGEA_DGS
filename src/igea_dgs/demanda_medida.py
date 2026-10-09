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

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

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
    'suministro_act': ('suministro act', 'suministro actual', 'sum act', 'nis actual'),
    'suministro': ('suministro', 'suministro anterior', 'nis anterior'),
    'sed': ('sed', 'subestacion', 'subestacion de distribucion'),
    'radial': ('radial', 'alimentador'),
    'cliente_codigo': ('nis', 'suministro', 'nro suministro', 'numero suministro'),
    'ea': ('ea', 'ea total', 'energia activa'),
    'eri': ('eri', 'eri total', 'energia reactiva inductiva'),
    'pot': ('pot max', 'pot', 'potencia maxima', 'potencia'),
}
MAGNITUDES = ('kw', 'kvar', 'kva', 'fp')


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


def medidores_de(medidores: Sequence[Medidor], alimentador: str) -> list[str]:
    """Cada medidor que el libro asigna al alimentador, sin repetir y en su orden (RF-22)."""
    clave = clave_codigo(alimentador)
    return list(dict.fromkeys(parte for m in medidores if clave_codigo(m.alimentador) == clave
                              for parte in partir_medidores(m.medidor)))


# =========================================================================== cabecera
def libros_de_cabecera(rutas: Iterable[Path | str]) -> list[Path]:
    """Ficheros de cabecera: cada ruta es un libro o una carpeta con libros (RF-39)."""
    out: list[Path] = []
    for ruta in rutas:
        p = Path(ruta)
        if p.is_dir():
            out += sorted(f for f in p.iterdir()
                          if f.is_file() and f.suffix.lower() in EXTENSIONES and not f.name.startswith('~$'))
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iso(fecha: Any) -> str | None:
    if isinstance(fecha, (datetime, date)):
        return fecha.isoformat(sep=' ') if isinstance(fecha, datetime) else fecha.isoformat()
    return None if fecha is None else str(fecha)


def maxima_de_registros(registros: Sequence[Registro], resultado: MaximaCabecera) -> MaximaCabecera:
    """kW máximo con su fecha; kVAR, kVA y FP del **mismo** registro (RF-27, RF-28, RF-30)."""
    mejor: Registro | None = None
    for r in registros:
        kw = r.valores.get('kw')
        if kw is None:
            continue                                    # RF-31: vacío o no numérico
        if (mejor is None or kw > mejor.valores['kw']
                or (kw == mejor.valores['kw'] and _antes(r.fecha, mejor.fecha))):
            mejor = r
    resultado.registros = len(registros)
    if mejor is None:
        resultado.error = 'ningún registro con kW numérico'
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
        # Con kVAR negativo (capacitivo) el FP lleva signo negativo, como en el medidor.
        resultado.fp = -fp if (resultado.kvar or 0) < 0 else fp
        resultado.fp_calculado = True
        resultado.columnas['fp'] = 'calculado con kW y kVA'
    return resultado


class Cabecera:
    """Libros de cabecera abiertos una vez por búsqueda: abrir un .xls de 400 MB cuesta ~1 s."""

    def __init__(self, rutas: Iterable[Path | str], alias=ALIAS) -> None:
        self.libros = libros_de_cabecera(rutas)
        self.alias = alias
        self._abiertos: dict[Path, Any] = {}

    def _libro(self, path: Path):
        if path not in self._abiertos:
            self._abiertos[path] = _abrir(path)
        return self._abiertos[path]

    def maxima(self, medidor: str, alimentador: str = '') -> MaximaCabecera:
        res = MaximaCabecera(medidor=medidor, alimentador=alimentador)
        hallados: list[tuple[Path, list[str], list[str]]] = []
        for path in self.libros:
            entera, partes = hojas_del_medidor(self._libro(path).sheet_names, medidor)
            if entera or partes:
                hallados.append((path, entera, partes))
        if not hallados:
            res.error = f'el medidor {medidor} no está en ningún libro de cabecera'
            return res
        # Mejor el libro con la hoja de su nombre; entre iguales, el primero por nombre.
        hallados.sort(key=lambda h: not h[1])
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
                return maxima_de_registros(registros, res)
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
            return maxima_de_registros(registros, res)
        if 'kw' not in res.columnas and completas:
            res.error = (f'{path.name}: {medidor} tiene varias hojas completas ('
                         + ', '.join(h for h, _r, _u in completas)
                         + '); escriba como medidor el nombre de la que quiere')
            return res
        if 'kw' not in res.columnas:
            res.error = f'{path.name} › {", ".join(entera + partes)}: sin columna de kW'
            return res
        return maxima_de_registros(_unir_por_fecha(trozos), res)


def maximas(rutas: Iterable[Path | str], medidores: Sequence[tuple[str, str]], *, alias=ALIAS,
            cancelado: Callable[[], bool] = lambda: False,
            progreso: Callable[[int, int, str], None] = lambda *_a: None) -> list[MaximaCabecera]:
    """Máxima de cada ``(alimentador, medidor)``, por separado, sin sumar (RF-29, RF-32).

    Se cancela entre medidores: un medidor se lee entero.
    """
    cabecera = Cabecera(rutas, alias)
    out = []
    for n, (alimentador, medidor) in enumerate(medidores, start=1):
        if cancelado():
            break
        progreso(n, len(medidores), medidor)
        try:
            out.append(cabecera.maxima(medidor, alimentador))
        except DemandaError as exc:
            out.append(MaximaCabecera(medidor=medidor, alimentador=alimentador, error=str(exc)))
    return out


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def leer_clientes(path: Path | str, alias=ALIAS) -> tuple[list[ClienteImportante], list[str]]:
    """Hoja resumen de clientes importantes, en cualquiera de sus dos formatos (RF-34)."""
    libro = _abrir(path)
    hojas = [h for h in libro.sheet_names if normalizar(h) == 'resumen']
    hojas += [h for h in libro.sheet_names if 'resumen' in normalizar(h) and h not in hojas]
    if not hojas:
        raise DemandaError(f'{Path(path).name}: no tiene hoja «resumen».')
    filas = _filas(libro, hojas[0])
    hallada = _buscar_cabecera(filas, ('cliente_codigo', 'ea', 'eri', 'pot'), alias, ('cliente_codigo',))
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
    ('codigo', 'Nis / Suministro'), ('cruzado_por', 'Cruzado por'),
    ('suministro_actual', 'Suministro Act'), ('suministro_anterior', 'Suministro'),
    ('sed', 'SED'), ('radial', 'Radial'), ('ea', 'EA'), ('eri', 'ERI'), ('pot', 'Pot'),
    ('motivo', 'Motivo'),
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
