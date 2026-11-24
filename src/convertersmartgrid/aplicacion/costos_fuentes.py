"""Costos oficiales del PIDE: un contrato para cada fuente y el cruce con la red (spec 072).

El SICODI se publica en Procesos Regulatorios de Osinergmin como TXT separados por tabuladores.
Un costo depende de código, tensión, estructura y sector típico: `AA03503G` es el código `AA03503`
a 22,9 kV (`G`), y el mismo código cuesta distinto en madera que en concreto. Sin alguno de esos
datos no hay costo: se nombra el hueco, porque un costo supuesto se confunde con uno oficial. Por
eso tampoco hay factores por defecto: el informe de otra distribuidora aplicó un factor sobre mercado y la
carpeta de su cálculo estaba vacía.

Las obras de transmisión se valoran con los módulos estándar de inversión (Res. 152-2026-OS/CD,
cuya base sustituyó la Res. 181-2026-OS/CD), por el mismo contrato y nunca con el SICODI: un
elemento de una obra lleva el ámbito de su fuente y solo esa lo valora (072:RF-6).

El SICODI también se publica como libro de cálculo (.xlsx, .xlsm, .xls o .xlsb): `leer_sicodi` lo
reconoce por su contenido, lee sus costos de inversión en la misma tabla y reconoce, por sus
cabeceras, cada una de sus hojas (072:RF-39, RF-40). En el libro un mismo código con su tensión,
estructura y sector puede tener dos costos, uno por subfamilia: no se elige ninguno sin ella (072:RF-41).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from itertools import chain, islice, pairwise
from pathlib import Path
from ..dominio.util import sha256_file

#: Componentes del costo total de una instalación, con el nombre de su columna en el SICODI.
COMPONENTES = {'material': 'COSTO MAT', 'stock': 'COSTO STOCK', 'mano_obra': 'COSTO MO', 'transporte': 'COSTO TRANS',
               'obra': 'COSTO OBRA', 'gastos_generales': 'COSTO GASTOS GNRAL', 'ingenieria': 'COSTO INGENIERIA',
               'intercalario': 'COSTO INTERCALARIO', 'total': 'TOTAL'}
_COLUMNAS = ('SECTOR TIPICO', 'GRUPO', 'FAMILIA', 'COD COSTINVER', 'COD TEN NOMI', 'DSC TEN NOMI',
             'COD SECUNDARIO', 'DSC SECUNDARIO', 'NOMBRE', *COMPONENTES.values())
_INSTALACION = 'Instalacion.txt'


class CostosError(ValueError):
    """Una fuente que no se puede leer o que no declara lo necesario."""


@dataclass(frozen=True)
class FuenteCostos:
    """De dónde sale un costo (072:RF-5, RF-9). La moneda se declara: el TXT no la dice."""

    nombre: str
    ambito: str
    resolucion: str
    anio: int
    moneda: str
    url: str
    fecha_descarga: str
    huella: str
    factor: float | None = None
    sustento_factor: str | None = None

    def __post_init__(self):
        faltan = [k for k in ('nombre', 'ambito', 'resolucion', 'moneda', 'url', 'fecha_descarga')
                  if not str(getattr(self, k) or '').strip()]
        if faltan:
            raise CostosError(f'la fuente de costos no declara: {", ".join(faltan)}')
        # 072:RF-8: un factor sobre el costo oficial solo con su sustento.
        if self.factor is not None and not str(self.sustento_factor or '').strip():
            raise CostosError(f'el factor {self.factor} no declara su sustento')


@dataclass(frozen=True)
class Costo:
    """El costo oficial de una instalación, con sus componentes y su fuente."""

    codigo: str
    tension: str
    estructura: str
    sector: str
    nombre: str
    componentes: Mapping[str, float | None]
    fuente: FuenteCostos
    familia: str = ''
    unidad: str = ''
    #: Subfamilia, hoja y fila de donde sale el costo cuando la fuente es un libro (072:RF-40, RF-41).
    subfamilia: str = ''
    hoja: str = ''
    fila: int = 0

    @property
    def total(self) -> float:
        """El total oficial, con el factor solo si la fuente lo declaró con sustento."""
        return self.componentes['total'] * (self.fuente.factor if self.fuente.factor is not None else 1.0)


@dataclass
class TablaCostos:
    """Los costos de una fuente, indexados una sola vez: nada de recorrerla por tramo."""

    fuente: FuenteCostos
    filas: dict[tuple[str, str, str, str], Costo] = field(default_factory=dict)
    #: Si la fuente distingue zona (módulos de transmisión): entonces el elemento la declara.
    con_zona: bool = False
    #: Columna de la fuente de cada componente del costo; ``None`` si la fuente no la trae (072:RF-39).
    columnas: dict[str, str | None] = field(default_factory=dict)
    #: Lo que se reconoció en cada hoja de un libro, por nombre de hoja (072:RF-40).
    hojas: dict[str, HojaSicodi] = field(default_factory=dict)
    #: Lo que la lectura no calla: hojas no reconocidas, columnas ausentes, claves ambiguas.
    avisos: list[str] = field(default_factory=list)
    #: Claves con dos o más costos distintos: solo la subfamilia los separa (072:RF-41).
    ambiguos: dict[tuple[str, str, str, str], tuple[Costo, ...]] = field(default_factory=dict)

    def __post_init__(self):
        claves = [*self.filas, *self.ambiguos]
        self.codigos = {k[0] for k in claves}
        self.tensiones = {k[1] for k in claves}
        self.sectores = {k[3] for k in claves}
        self._estructuras: dict[tuple[str, str, str], set[str]] = {}
        for k in claves:
            self._estructuras.setdefault((k[0], k[1], k[3]), set()).add(k[2])

    def buscar(self, codigo: str, tension: str, estructura: str, sector: str, subfamilia: str = '',
               tipo: str = '') -> Costo | None:
        """El costo exacto, o ``None``: nunca el más parecido (072:RF-7, RF-41)."""
        return self.resolver(codigo, tension, estructura, sector, subfamilia, tipo)[0]

    def resolver(self, codigo: str, tension: str, estructura: str, sector: str, subfamilia: str = '',
                 tipo: str = '') -> tuple[Costo | None, str]:
        """El costo y cómo se eligió, con su anotación (072:RF-41).

        Si la clave es ambigua, elige la subfamilia declarada, igual a la de la fuente; sin ella, la que
        deduce el tipo del elemento con ``SUBFAMILIA_POR_TIPO``, anotada como «subfamilia deducida por el
        tipo». Si el tipo no decide entre varias, no hay costo y ``motivo_sin_costo`` nombra la ambigüedad.
        """
        clave = (codigo, tension, estructura, sector)
        costo = self.filas.get(clave)
        candidatos = self.ambiguos.get(clave, ())
        if costo is not None or not candidatos:
            return costo, ''
        if str(subfamilia or '').strip():
            buscada = normalizar_cabecera(subfamilia)
            hallados = [c for c in candidatos if normalizar_cabecera(c.subfamilia) == buscada]
            return (hallados[0], 'subfamilia declarada') if len(hallados) == 1 else (None, '')
        hallados = subfamilias_del_tipo(tipo, candidatos)
        if len(hallados) == 1:
            return hallados[0], f'subfamilia deducida por el tipo «{tipo}»: {hallados[0].subfamilia}'
        return None, ''

    def estructura_unica(self, codigo: str, tension: str, sector: str) -> str | None:
        """La estructura si el costo solo existe con una: un cable subterráneo no lleva postes."""
        hallados = self._estructuras.get((codigo, tension, sector), ())
        return next(iter(hallados)) if len(hallados) == 1 else None

    def motivo_sin_costo(self, codigo: str, tension: str, estructura: str, sector: str, tipo: str = '') -> str:
        """Por qué no hay costo, para nombrar el hueco (072:RF-7, RF-41)."""
        ambiguos = self.ambiguos.get((codigo, tension, estructura, sector))
        if ambiguos:
            subfamilias = ', '.join(sorted({f'«{c.subfamilia}»' for c in ambiguos}))
            if not tipo:
                por_tipo = 'el elemento no declara su tipo'
            elif tipo not in SUBFAMILIA_POR_TIPO:
                por_tipo = f'el tipo «{tipo}» no está en la tabla de subfamilias por tipo'
            else:
                por_tipo = f'el tipo «{tipo}» no decide entre ellas'
            return (f'{codigo}{tension} con estructura «{estructura}» en {sector} es ambiguo: {len(ambiguos)} costos '
                    f'en {self.fuente.nombre} (subfamilias {subfamilias}) y {por_tipo}; declare la subfamilia')
        if not tension:
            return f'«{codigo}» no es un código de costo con su tensión'
        if not sector or sector not in self.sectores:
            return f'sector típico «{sector}» no está en {self.fuente.nombre}'
        if tension not in self.tensiones:
            return f'tensión «{tension}» no está en {self.fuente.nombre}'
        if codigo not in self.codigos:
            return f'código {codigo} no está en {self.fuente.nombre}'
        return f'{codigo}{tension} sin estructura «{estructura}» en {sector}'

    def modulos(self) -> set[str]:
        """Los códigos de módulo de la fuente."""
        return set(self.codigos)

    def buscar_modulo(self, codigo: str, zona: str = '') -> Costo | None:
        """El módulo exacto con su zona, o ``None``: su código ya dice tensión y configuración."""
        return self.filas.get((codigo, '', '', zona if self.con_zona else ''))

    def motivo_sin_modulo(self, codigo: str, zona: str) -> str:
        """Por qué un elemento de transmisión no tiene costo, para nombrar el hueco (072:RF-7)."""
        if self.con_zona and not zona:
            return f'{codigo}: la fuente {self.fuente.nombre} distingue zona y el elemento no la declara'
        if codigo not in self.codigos:
            return f'módulo {codigo} no está en {self.fuente.nombre} ({self.fuente.resolucion})'
        return f'módulo {codigo} no está en la zona «{zona}» de {self.fuente.nombre}'


def leer_sicodi(ruta: Path | str, *, resolucion: str, anio: int, moneda: str, url: str, fecha_descarga: str,
                factor: float | None = None, sustento_factor: str | None = None) -> TablaCostos:
    """Lee el SICODI: el zip público con `Instalacion.txt` o el libro de cálculo (072:RF-5, RF-9, RF-39).

    Se reconoce por el contenido, no por la extensión: un libro .xlsx, .xlsm o .xlsb también es un zip.
    """
    ruta = Path(ruta)
    huella = _huella(ruta)
    fuente = FuenteCostos('SICODI', 'distribucion', resolucion, anio, moneda, url, fecha_descarga, huella,
                          factor, sustento_factor)
    if _es_libro(ruta):
        return _leer_libro_sicodi(ruta, fuente)
    with zipfile.ZipFile(ruta) as z:
        nombre = next((n for n in z.namelist() if n.rsplit('/', 1)[-1] == _INSTALACION), None)
        if nombre is None:
            raise CostosError(f'{ruta.name} no trae {_INSTALACION}')
        lineas = z.read(nombre).decode('utf-8', errors='strict').splitlines()
    if not lineas:
        raise CostosError(f'{_INSTALACION} está vacío')
    cab = lineas[0].split('\t')
    faltan = [c for c in _COLUMNAS if c not in cab]
    if faltan:
        raise CostosError(f'{_INSTALACION} sin las columnas: {", ".join(faltan)}')
    i = {c: cab.index(c) for c in _COLUMNAS}
    filas: dict[tuple[str, str, str, str], Costo] = {}
    for n, linea in enumerate(lineas[1:], 2):
        v = linea.split('\t')
        if len(v) < len(cab):
            raise CostosError(f'{_INSTALACION}, fila {n}: {len(v)} columnas de {len(cab)}')
        clave = (v[i['COD COSTINVER']], v[i['COD TEN NOMI']], v[i['COD SECUNDARIO']], v[i['SECTOR TIPICO']])
        # 1 037 de 44 107 filas del SICODI de la Res. 184-2026 traen componentes en blanco y su total:
        # un componente en blanco es «sin dato», nunca cero; un total en blanco no es un costo.
        try:
            componentes = {k: (float(v[i[c]]) if v[i[c]].strip() else None) for k, c in COMPONENTES.items()}
        except ValueError as exc:
            raise CostosError(f'{_INSTALACION}, fila {n}: costo no numérico ({exc})') from exc
        if componentes['total'] is None:
            raise CostosError(f'{_INSTALACION}, fila {n}: sin total')
        filas[clave] = Costo(clave[0], clave[1], clave[2], clave[3], v[i['NOMBRE']], componentes, fuente,
                             v[i['FAMILIA']])
    return TablaCostos(fuente, filas, columnas={k: f'{_INSTALACION}: {c}' for k, c in COMPONENTES.items()})


# Auditoría D.2 (2026-11-24): la huella de un fichero es una sola, la de dominio/util; este nombre queda por quien lo llama.
_huella = sha256_file


def _es_libro(ruta: Path) -> bool:
    """Un libro .xls (OLE2) o un zip con `xl/workbook.*` (.xlsx, .xlsm, .xlsb), por sus bytes (072:RF-39)."""
    with ruta.open('rb') as f:
        firma = f.read(8)
    if firma == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return True
    if not zipfile.is_zipfile(ruta):
        raise CostosError(f'{ruta.name} no es ni el zip del SICODI con {_INSTALACION} ni un libro de cálculo '
                          '(.xlsx, .xlsm, .xls o .xlsb)')
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
    if any(n.rsplit('/', 1)[-1] == _INSTALACION for n in nombres):
        return False
    return any(n.startswith('xl/workbook.') for n in nombres)


def normalizar_cabecera(texto) -> str:
    """`COSTO_MAT`, `Costo Mat` y `COSTO MAT` dicen lo mismo: sin tildes, en minúsculas y sin signos."""
    t = unicodedata.normalize('NFKD', str(texto if texto is not None else ''))
    t = ''.join(c for c in t if not unicodedata.combining(c)).casefold()
    return ' '.join(re.sub(r'[^0-9a-z]+', ' ', t).split())


#: Subfamilia del SICODI que corresponde a cada tipo de elemento del modelo canónico (aclaración de 072:RF-41).
#: Universal: sale de las subfamilias de la guía del SICODI (red aérea, red subterránea, alumbrado público y
#: subestaciones de distribución), no de una empresa. Cada tipo da las palabras que la subfamilia, normalizada,
#: tiene que llevar y las que no puede llevar; si más de una candidata cumple, el tipo no decide.
SUBFAMILIA_POR_TIPO: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    'tramo_aereo': (('red aerea',), ('alumbrado',)),
    'tramo_subterraneo': (('red subterranea',), ('alumbrado',)),
    'tramo_alumbrado_aereo': (('red aerea', 'alumbrado publico'), ()),
    'tramo_alumbrado_subterraneo': (('red subterranea', 'alumbrado publico'), ()),
    'luminaria': (('alumbrado publico',), ('red',)),
    'sed_aerea': (('sed aerea',), ()),
    'sed_convencional': (('sed convencional',), ()),
    'sed_compacta': (('sed compacta',), ()),
    'sed': (('sed',), ()),
}


def subfamilias_del_tipo(tipo: str, candidatos: Iterable[Costo]) -> list[Costo]:
    """Los costos cuya subfamilia corresponde al tipo de elemento según ``SUBFAMILIA_POR_TIPO`` (072:RF-41)."""
    regla = SUBFAMILIA_POR_TIPO.get(str(tipo or '').strip())
    if regla is None:
        return []
    lleva, no_lleva = regla

    def cumple(subfamilia: str) -> bool:
        s = f' {normalizar_cabecera(subfamilia)} '
        return all(f' {p} ' in s for p in lleva) and not any(f' {p} ' in s for p in no_lleva)

    return [c for c in candidatos if cumple(c.subfamilia)]


#: Sinónimos de cada campo, ya normalizados, en orden de preferencia (072:RF-39, RF-40).
_SINONIMOS = {
    'sector': ('cod sector tipico', 'sector tipico', 'codigo sector tipico'),
    'codigo': ('cod costinver', 'codigo costinver', 'codigo costo de inversion', 'codigo de costo de inversion'),
    'tension': ('cod ten nomi', 'codigo tension nominal', 'codigo ten nomi'),
    'estructura': ('cod secundario', 'codigo secundario'),
    'tipo_secundario': ('cod tipo secundario', 'codigo tipo secundario'),
    'nombre': ('nombre ci', 'nombre', 'descripcion ci'),
    'familia': ('familia',),
    'subfamilia': ('subfamilia', 'sub familia'),
    'material': ('costo mat', 'costo material', 'costo materiales'),
    'stock': ('costo stock',),
    'mano_obra': ('costo mo', 'costo mano obra', 'costo mano de obra'),
    'transporte': ('costo trans', 'costo transporte', 'costo transporte y equipos'),
    'obra': ('costo obra', 'costo de obra'),
    'gastos_generales': ('costo gastos gnral', 'costo gastos generales'),
    'ingenieria': ('costo ingenieria',),
    'intercalario': ('costo intercalario', 'costo interes intercalario'),
    'total': ('total', 'costo total', 'costo total us'),
    'subtotal': ('sub total', 'subtotal'),
    'armado': ('cod armado', 'codigo armado', 'codigo de armado'),
    'nombre_armado': ('armado',),
    'cod_material': ('cod material', 'codigo material', 'codigo vnr', 'codigo de material'),
    'descripcion_material': ('material', 'descripcion'),
    'cod_recurso': ('cod recurso', 'codigo recurso', 'codigo de recurso'),
    'recurso': ('recurso',),
    'grupo': ('grupo',),
    'unidad': ('abreviatura um', 'unidad', 'unidad medida', 'unidad de medida'),
    'cantidad': ('cantidad', 'cantidad por km'),
    'costo_unitario': ('costo unitario', 'us unidad', 'costo unitario us'),
    'subtotal_armado': ('sub total us', 'sub total', 'subtotal', 'total'),
    'valor': ('valor us', 'valor', 'precio', 'precio unitario'),
    'valor_calculado': ('valor calc', 'valor calculado'),
    'sustento': ('sustento',),
    'cod_componente': ('cod componente', 'codigo componente', 'componente', 'codigo', 'cod costinver',
                       'codigo instalacion'),
    'costo_mantenimiento': ('costo mantenimiento', 'costo de mantenimiento', 'costo unitario de mantenimiento',
                            'costo estandar de mantenimiento', 'costo anual de mantenimiento', 'mantenimiento'),
    'descripcion': ('descripcion', 'nombre'),
    'transformador': ('transformador', 'tipo de transformador', 'tipo transformador', 'codigo transformador',
                      'cod transformador'),
    'potencia': ('potencia kva', 'potencia nominal kva', 'potencia nominal', 'kva', 'potencia'),
    'tension_trafo': ('tension primaria kv', 'tension primaria', 'relacion de transformacion', 'tension kv',
                      'tension'),
    'fases': ('fases', 'numero de fases', 'n fases'),
    'costo': ('costo', 'costo total', 'total'),
    'calibre': ('calibre', 'calibre mm2', 'seccion', 'seccion mm2', 'conductor'),
    'corriente_min': ('corriente minima', 'corriente minima a', 'i min', 'i min a', 'imin'),
    'corriente_max': ('corriente maxima', 'corriente maxima a', 'i max', 'i max a', 'imax'),
    'tension_nivel': ('tension', 'tension kv', 'nivel de tension'),
}


@dataclass(frozen=True)
class _Tipo:
    """Una clase de hoja: los campos que la reconocen, los opcionales y los numéricos."""

    nombre: str
    requeridos: tuple[str, ...]
    opcionales: tuple[str, ...] = ()
    numericos: tuple[str, ...] = ()


_COMPONENTES_LIBRO = tuple(COMPONENTES)
#: En orden: la primera clase cuyos campos están en una fila de cabecera es la de la hoja (072:RF-40).
_TIPOS_DE_HOJA = (
    _Tipo('costos_inversion_detalle', ('codigo', 'tension', 'estructura', 'sector', 'armado', 'total'),
          ('nombre', 'nombre_armado', 'unidad', 'cantidad', 'subtotal', *_COMPONENTES_LIBRO[:-1]),
          ('cantidad', 'subtotal', *_COMPONENTES_LIBRO)),
    _Tipo('costos_inversion', ('codigo', 'tension', 'estructura', 'sector', 'total'),
          ('nombre', 'familia', 'subfamilia', 'tipo_secundario', *_COMPONENTES_LIBRO[:-1]), _COMPONENTES_LIBRO),
    _Tipo('armados', ('armado', 'cod_material', 'cantidad'),
          ('sector', 'nombre_armado', 'descripcion_material', 'unidad', 'costo_unitario', 'subtotal_armado'),
          ('cantidad', 'costo_unitario', 'subtotal_armado')),
    _Tipo('materiales', ('cod_material', 'descripcion_material', 'valor'),
          ('unidad', 'familia', 'subfamilia', 'sustento'), ('valor',)),
    _Tipo('recursos', ('cod_recurso', 'recurso', 'valor'), ('grupo', 'unidad', 'valor_calculado', 'sustento'),
          ('valor', 'valor_calculado')),
    _Tipo('mantenimiento', ('cod_componente', 'costo_mantenimiento'), ('descripcion', 'unidad', 'sector'),
          ('costo_mantenimiento',)),
    _Tipo('transformadores', ('transformador', 'potencia', 'tension_trafo'), ('fases', 'costo'),
          ('potencia', 'costo')),
    _Tipo('rangos_corriente', ('calibre', 'corriente_min', 'corriente_max'), ('tension_nivel',),
          ('corriente_min', 'corriente_max')),
)
#: Cuántas filas se miran en una hoja sin cabecera para reconocer sus parámetros.
_FILAS_PARAMETROS = 60


@dataclass(frozen=True)
class HojaSicodi:
    """Lo leído de una hoja del libro del SICODI, con su hoja, sus filas y la huella del libro (072:RF-40)."""

    hoja: str
    tipo: str
    huella: str
    fila_cabecera: int
    #: Cabecera de la hoja de la que sale cada campo.
    columnas: Mapping[str, str]
    campos: tuple[str, ...]
    #: Una tupla por fila: su número de fila en la hoja y los campos, en el orden de ``campos``.
    filas: tuple[tuple, ...]
    #: Etiqueta y valor de encima de la cabecera («Familia: Pararrayos»): una tabla dinámica filtrada.
    filtros: Mapping[str, str] = field(default_factory=dict)

    def registros(self) -> Iterator[dict]:
        """Cada fila como diccionario, con `hoja`, `fila` y sus campos."""
        for f in self.filas:
            yield {'hoja': self.hoja, 'fila': f[0], **dict(zip(self.campos, f[1:]))}


def _texto(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _numero(v, donde: str) -> float | None:
    """Un número de la celda; una celda en blanco es «sin dato», nunca cero (072:RF-39)."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(' ', '')
    if not s:
        return None
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError as exc:
        raise CostosError(f'{donde}: costo no numérico «{v}»') from exc


def _columnas_de(cabecera: Sequence[str], tipo: _Tipo) -> dict[str, int] | None:
    """Índice de cada campo en una fila de cabecera, o ``None`` si falta un requerido."""
    normal = [normalizar_cabecera(c) for c in cabecera]
    usados: set[int] = set()
    out: dict[str, int] = {}
    for campo in (*tipo.requeridos, *tipo.opcionales):
        for sinonimo in _SINONIMOS[campo]:
            i = next((j for j, c in enumerate(normal) if c == sinonimo and j not in usados), None)
            if i is not None:
                out[campo] = i
                usados.add(i)
                break
        else:
            if campo in tipo.requeridos:
                return None
    return out


def _cabeceras_vistas(primeras: Sequence[Sequence]) -> list[str]:
    """La fila con más textos de las primeras: lo que se cita de una hoja no reconocida."""
    mejor = max(primeras, key=lambda f: sum(1 for c in f if isinstance(c, str) and c.strip()), default=[])
    return [str(c).strip() for c in mejor if isinstance(c, str) and c.strip()]


def _faltan_costos(primeras: Sequence[Sequence]) -> list[str]:
    """Los campos de costos de inversión que faltan en la fila de cabecera más cercana a serlo."""
    tipo = _TIPOS_DE_HOJA[1]
    mejor: list[str] | None = None
    for f in primeras:
        normal = {normalizar_cabecera(c) for c in f}
        faltan = [c for c in tipo.requeridos if not normal.intersection(_SINONIMOS[c])]
        if mejor is None or len(faltan) < len(mejor):
            mejor = faltan
    return mejor if mejor is not None else list(tipo.requeridos)


def _filtros(encima: Sequence[Sequence]) -> dict[str, str]:
    """Pares etiqueta y valor encima de la cabecera: los filtros de una tabla dinámica."""
    out = {}
    for f in encima:
        celdas = [_texto(c) for c in f if _texto(c)]
        if len(celdas) == 2:
            out[celdas[0].rstrip(':').strip()] = celdas[1]
    return out


def _parametros(primeras: Sequence[Sequence]) -> list[tuple]:
    """Filas «Porcentaje del contratista (%): | 25»: una etiqueta que acaba en «:» y un número.

    Un texto con «%» sin los dos puntos es el renglón de un informe («Ingeniería (11,17% de E)»), no un parámetro.
    """
    out = []
    for n, f in enumerate(primeras, 1):
        celdas = [c for c in f if c is not None and str(c).strip() != '']
        for a, b in pairwise(celdas):
            if isinstance(a, str) and a.strip().endswith(':') and isinstance(b, (int, float)) \
                    and not isinstance(b, bool):
                out.append((n, a.strip().rstrip(':').strip(), float(b)))
                break
    return out if len(out) >= 2 else []


def _leer_libro_sicodi(ruta: Path, fuente: FuenteCostos) -> TablaCostos:
    """Recorre cada hoja del libro y reconoce por su contenido qué es (072:RF-39, RF-40, RF-41)."""
    from .demanda_medida import abrir_libro, iterar_filas_de_hoja
    from .libros_por_anio import DemandaError

    try:
        libro = abrir_libro(ruta)
    except DemandaError as exc:
        raise CostosError(f'{ruta.name} es un libro de cálculo, pero no se pudo abrir: {exc}') from exc
    por_clave: dict[tuple[str, str, str, str], list[Costo]] = {}
    hojas: dict[str, HojaSicodi] = {}
    avisos: list[str] = []
    columnas: dict[str, str | None] = {}
    vistas: list[tuple[str, list[str], list[str]]] = []
    try:
        for hoja in libro.sheet_names:
            filas = iterar_filas_de_hoja(libro, hoja)
            primeras = list(islice(filas, _FILAS_CABECERA))
            hallado = next(((t, n, idx) for n, f in enumerate(primeras) for t in _TIPOS_DE_HOJA
                            if (idx := _columnas_de([_texto(c) for c in f], t)) is not None), None)
            if hallado is None:
                params = _parametros([*primeras, *islice(filas, max(0, _FILAS_PARAMETROS - len(primeras)))])
                if params:
                    hojas[hoja] = HojaSicodi(hoja, 'parametros', fuente.huella, 0, {}, ('nombre', 'valor'),
                                             tuple(params))
                    continue
                cab = _cabeceras_vistas(primeras)
                vistas.append((hoja, cab, _faltan_costos(primeras)))
                avisos.append(f'hoja «{hoja}» no reconocida; cabeceras: ' + (', '.join(cab[:25]) or 'ninguna'))
                continue
            tipo, n_cab, idx = hallado
            cab = [_texto(c) for c in primeras[n_cab]]
            resto = chain(primeras[n_cab + 1:], filas)
            if tipo.nombre == 'costos_inversion':
                _costos_de_hoja(hoja, n_cab + 2, resto, idx, cab, fuente, por_clave, columnas, avisos)
            else:
                hojas[hoja] = _hoja_auxiliar(hoja, tipo, n_cab + 2, resto, idx, cab, fuente.huella,
                                             _filtros(primeras[:n_cab]))
                if hojas[hoja].filtros:
                    avisos.append(f'hoja «{hoja}» ({tipo.nombre}): tabla con filtros encima de la cabecera ('
                                  + ', '.join(f'{k}: {v}' for k, v in hojas[hoja].filtros.items())
                                  + '); es una vista de otra hoja')
    finally:
        libro.close()
    if not por_clave:
        detalle = '; '.join(f'«{h}»: faltan {", ".join(f) or "filas de costo"}; cabeceras: '
                            f'{", ".join(c[:15]) or "ninguna"}' for h, c, f in vistas)
        raise CostosError(f'{ruta.name}: ninguna hoja trae los costos de inversión (código de costo, tensión, '
                          f'estructura, sector típico y total); se encontró: {detalle or "ninguna hoja sin reconocer"}')
    filas_tabla: dict[tuple[str, str, str, str], Costo] = {}
    ambiguos: dict[tuple[str, str, str, str], tuple[Costo, ...]] = {}
    for clave, costos in por_clave.items():
        if len({tuple(sorted(c.componentes.items())) for c in costos}) == 1:
            filas_tabla[clave] = costos[0]
        else:
            ambiguos[clave] = tuple(costos)
    if ambiguos:
        avisos.append(f'{len(ambiguos)} combinaciones de código, tensión, estructura y sector traen costos '
                      'distintos (una por subfamilia): no se elige ninguna sin la subfamilia del elemento')
    return TablaCostos(fuente, filas_tabla, columnas=columnas, hojas=hojas, avisos=avisos, ambiguos=ambiguos)


def _costos_de_hoja(hoja: str, primera: int, filas: Iterable, idx: Mapping[str, int], cab: Sequence[str],
                    fuente: FuenteCostos, por_clave: dict, columnas: dict, avisos: list) -> None:
    """Los costos de inversión de una hoja, con la columna de cada componente (072:RF-39)."""
    for k in COMPONENTES:
        if k in idx:
            columnas.setdefault(k, f'{hoja}: {cab[idx[k]]}')
        else:
            columnas.setdefault(k, None)
            avisos.append(f'hoja «{hoja}»: sin columna de {k}; ese componente queda sin dato')

    def celda(f, campo):
        j = idx.get(campo)
        return f[j] if j is not None and j < len(f) else None

    for n, f in enumerate(filas, primera):
        codigo = _texto(celda(f, 'codigo'))
        # Las filas sin código son títulos o subtotales, no costos.
        if not codigo or normalizar_cabecera(codigo).startswith('total'):
            continue
        donde = f'hoja «{hoja}», fila {n}'
        componentes = {k: _numero(celda(f, k), donde) for k in COMPONENTES}
        if componentes['total'] is None:
            raise CostosError(f'{donde}: {codigo} sin total')
        clave = (codigo, _texto(celda(f, 'tension')), _texto(celda(f, 'estructura')), _texto(celda(f, 'sector')))
        por_clave.setdefault(clave, []).append(
            Costo(*clave, _texto(celda(f, 'nombre')), componentes, fuente, _texto(celda(f, 'familia')),
                  subfamilia=_texto(celda(f, 'subfamilia')), hoja=hoja, fila=n))


def _hoja_auxiliar(hoja: str, tipo: _Tipo, primera: int, filas: Iterable, idx: Mapping[str, int],
                   cab: Sequence[str], huella: str, filtros: Mapping[str, str]) -> HojaSicodi:
    """Materiales, recursos, armados, mantenimiento…: cada fila con su número y sus campos (072:RF-40)."""
    campos = tuple(c for c in (*tipo.requeridos, *tipo.opcionales) if c in idx)
    valores = [c for c in tipo.numericos if c in idx]
    out = []
    for n, f in enumerate(filas, primera):
        celdas = {c: (f[idx[c]] if idx[c] < len(f) else None) for c in campos}
        cod = _texto(celdas[tipo.requeridos[0]])
        if not cod or normalizar_cabecera(cod).startswith('total'):
            continue
        # Una fila sin ningún valor es un título de grupo de la tabla dinámica.
        if valores and all(_texto(celdas[c]) == '' for c in valores):
            continue
        donde = f'hoja «{hoja}», fila {n}'
        out.append((n, *(_numero(celdas[c], donde) if c in tipo.numericos else _texto(celdas[c]) for c in campos)))
    return HojaSicodi(hoja, tipo.nombre, huella, primera - 1, {c: cab[idx[c]] for c in campos}, campos, tuple(out),
                      dict(filtros))


#: Lo que un libro de módulos debe declarar, con el nombre de su columna en esa resolución.
COLUMNAS_MODULOS = ('codigo', 'nombre', 'unidad', 'total')
_COLUMNAS_MODULOS_OPCIONALES = ('zona', 'familia')
#: Cuántas filas se miran para hallar la cabecera: los anexos llevan títulos encima.
_FILAS_CABECERA = 30


def leer_modulos_transmision(ruta: Path | str, *, columnas: Mapping[str, str], resolucion: str, anio: int,
                             moneda: str, url: str, fecha_descarga: str, hoja: str | Sequence[str] | None = None,
                             unidad: str | Mapping[str, str] | None = None, factor: float | None = None,
                             sustento_factor: str | None = None,
                             unidades_por_codigo: Mapping[str, str] | None = None) -> TablaCostos:
    """Lee un libro de módulos estándar de transmisión (072:RF-5, RF-6, RF-9).

    ``columnas`` lleva el nombre de cada columna en el libro: `codigo`, `nombre`, `unidad` y
    `total`, y si la base distingue zona, `zona`. Se declaran porque la disposición es de cada
    resolución (la 8-2026 publicó un `.xlsm` y la 59-2026 lo reemplazó por otro): suponer una
    sería leer mal la siguiente sin avisar.

    La base de la Res. 152-2026-OS/CD (`REST_MOD_INV_2025_PU.xlsm`) trae una hoja de resumen por tipo
    de módulo y ninguna columna de unidad. ``unidad`` conserva la declaración explícita del operador,
    global o por hoja; no certifica que una hoja sea homogénea. En tablas mixtas se declara
    ``unidades_por_codigo``, con cobertura de todos los códigos leídos. Las declaraciones no pueden
    contradecir una unidad no vacía de la columna auténtica ni contradecirse entre sí.
    No se infieren unidades por prefijo ni se convierten precios, longitudes o cantidades.
    """
    from openpyxl import load_workbook

    faltan = [k for k in COLUMNAS_MODULOS if not str(columnas.get(k) or '').strip()
              and not (k == 'unidad' and (unidad or unidades_por_codigo is not None))]
    if faltan:
        raise CostosError(f'los módulos de transmisión no declaran la columna de: {", ".join(faltan)}')
    hojas = [hoja] if isinstance(hoja, str) or hoja is None else list(hoja)
    if isinstance(unidad, Mapping):
        sin_unidad = [str(h) for h in hojas if not str(unidad.get(h) or '').strip()]
        if sin_unidad:
            raise CostosError(f'sin unidad declarada para la hoja: {", ".join(sin_unidad)}')
    if unidades_por_codigo is not None and (not isinstance(unidades_por_codigo, Mapping) or any(
            not isinstance(c, str) or not c.strip() or not isinstance(u, str) or not u.strip()
            for c, u in unidades_por_codigo.items())):
        raise CostosError('unidades_por_codigo debe declarar códigos y unidades de texto no vacíos')
    ruta = Path(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    fuente = FuenteCostos('Módulos estándar de transmisión', 'transmision', resolucion, anio, moneda, url,
                          fecha_descarga, huella, factor, sustento_factor)
    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        por_hoja = []
        for h in hojas:
            if h is not None and h not in wb.sheetnames:
                raise CostosError(f'{ruta.name} no trae la hoja «{h}»')
            ws = wb[h] if h is not None else wb.worksheets[0]
            fija = unidad.get(h) if isinstance(unidad, Mapping) else unidad
            por_hoja.append((ws.title, list(ws.iter_rows(values_only=True)), fija))
    finally:
        wb.close()
    tabla: dict[tuple[str, str, str, str], Costo] = {}
    con_zona = False
    for titulo, filas, fija in por_hoja:
        con_zona |= _modulos_de_hoja(ruta.name, titulo, filas, columnas, fija, fuente, tabla,
                                    unidades_por_codigo=unidades_por_codigo)
    if not tabla:
        raise CostosError(f'{ruta.name}: la hoja no trae ningún módulo bajo la cabecera')
    return TablaCostos(fuente, tabla, con_zona)


def _modulos_de_hoja(nombre: str, titulo: str, filas: list, columnas: Mapping[str, str], fija: str | None,
                     fuente: FuenteCostos, tabla: dict, *,
                     unidades_por_codigo: Mapping[str, str] | None = None) -> bool:
    """Añade a ``tabla`` los módulos de una hoja y dice si la hoja distingue zona."""
    usadas = {k: str(v).strip() for k, v in columnas.items()
              if k in COLUMNAS_MODULOS + _COLUMNAS_MODULOS_OPCIONALES and str(v or '').strip()}
    # Un fallback explícito permite que falte esa columna, pero nunca oculta
    # la columna si existe: su unidad debe contrastarse, no sobrescribirse.
    buscadas = {v for k, v in usadas.items()
                if k != 'unidad' or not (fija or unidades_por_codigo is not None)}
    n_cab = next((n for n, f in enumerate(filas[:_FILAS_CABECERA])
                  if buscadas <= {str(c).strip() for c in f if c is not None}), None)
    if n_cab is None:
        vistas = {str(c).strip() for f in filas[:_FILAS_CABECERA] for c in f if c is not None}
        faltan = sorted(buscadas - vistas)
        raise CostosError(f'{nombre}, hoja «{titulo}»: ninguna fila trae las columnas declaradas; faltan: '
                          f'{", ".join(faltan) or "todas en una misma fila"}')
    cab = [str(c).strip() if c is not None else '' for c in filas[n_cab]]
    i = {k: cab.index(v) for k, v in usadas.items() if v in cab}
    con_zona = 'zona' in i

    def celda(f, k):
        v = f[i[k]] if k in i and i[k] < len(f) else None
        return '' if v is None else str(v).strip()

    for n, f in enumerate(filas[n_cab + 1:], n_cab + 2):
        codigo = celda(f, 'codigo')
        # Las filas sin código son títulos o subtotales del anexo, no módulos.
        if not codigo:
            continue
        if fija is not None and (not isinstance(fija, str) or not fija.strip()):
            raise CostosError(f'{nombre}, fila {n}: unidad fija inválida de {codigo}')
        declaraciones = [celda(f, 'unidad')]
        if fija:
            declaraciones.append(fija.strip())
        if unidades_por_codigo is not None:
            if codigo not in unidades_por_codigo:
                raise CostosError(f'{nombre}, fila {n}: sin unidad por código para {codigo}')
            declaraciones.append(unidades_por_codigo[codigo].strip())
        conocidas = [u for u in declaraciones if u]
        if not conocidas:
            raise CostosError(f'{nombre}, fila {n}: módulo {codigo} sin unidad declarada')
        if any(u.casefold() != conocidas[0].casefold() for u in conocidas[1:]):
            raise CostosError(f'{nombre}, fila {n}: unidad contradictoria de {codigo}: '
                              + ' / '.join(conocidas))
        bruto = f[i['total']] if i['total'] < len(f) else None
        if bruto is None or str(bruto).strip() == '':
            raise CostosError(f'{nombre}, fila {n}: módulo {codigo} sin total')
        try:
            total = float(bruto)
        except (TypeError, ValueError) as exc:
            raise CostosError(f'{nombre}, fila {n}: costo no numérico de {codigo} ({exc})') from exc
        clave = (codigo, '', '', celda(f, 'zona') if con_zona else '')
        if clave in tabla:
            # Dos costos para un mismo módulo: elegir uno sería suponer cuál es el oficial.
            raise CostosError(f'{nombre}, fila {n}: módulo {codigo} repetido'
                              + (f' en la zona «{clave[3]}»' if con_zona else ''))
        tabla[clave] = Costo(codigo, '', '', clave[3], celda(f, 'nombre'), {'total': total}, fuente,
                             celda(f, 'familia'), conocidas[0])
    return con_zona


def exigir_ambito(tabla: TablaCostos, ambito: str) -> None:
    """Una fuente solo valora su ámbito: el SICODI no es de transmisión ni los módulos de distribución (072:RF-6)."""
    if tabla.fuente.ambito != ambito:
        raise CostosError(f'{tabla.fuente.nombre} es de ámbito «{tabla.fuente.ambito}», no de «{ambito}»')


def _costo_del_elemento(e: Mapping, tabla: TablaCostos) -> tuple[Costo | None, str, str]:
    """El costo, el motivo si no lo hay y la anotación de cómo se eligió (072:RF-41)."""
    codigo_red = str(e.get('codigo') or '').strip()
    if tabla.fuente.ambito == 'distribucion':
        codigo, tension = partir_codigo_vnr(codigo_red)
        sector, estructura = str(e.get('sector') or ''), str(e.get('estructura') or '')
        tipo = str(e.get('tipo') or '').strip()
        costo, anotacion = tabla.resolver(codigo, tension, estructura, sector, str(e.get('subfamilia') or ''), tipo)
        return costo, ('' if costo else tabla.motivo_sin_costo(codigo, tension, estructura, sector, tipo)), anotacion
    zona = str(e.get('zona') or '').strip()
    costo = tabla.buscar_modulo(codigo_red, zona)
    return costo, ('' if costo else tabla.motivo_sin_modulo(codigo_red, zona)), ''


def valorar_obra(elementos: Iterable[Mapping], tablas: Mapping[str, TablaCostos]) -> dict:
    """Metrado × costo de cada elemento de una obra, con la fuente de su ámbito (072:RF-6, RF-7, RF-15).

    Cada elemento declara `elemento`, `ambito` (`distribucion` o `transmision`), `codigo` y
    `cantidad`; los de distribución, además, `sector` y `estructura`, y `tipo` o `subfamilia` cuando el
    código es ambiguo en la fuente (072:RF-41); los de transmisión, `zona`
    si la fuente la distingue, y `unidad` para comprobar la del módulo. Lo que no cruza queda
    nombrado y fuera del total (072:RF-16). Los totales van por moneda: sumar dos monedas
    exigiría un tipo de cambio, que sería un factor no declarado (072:RF-8).
    """
    for ambito, tabla in tablas.items():
        exigir_ambito(tabla, ambito)
    valorados, sin_costo = [], []
    for e in elementos:
        nombre, ambito = str(e.get('elemento') or e.get('codigo') or ''), str(e.get('ambito') or '')
        tabla = tablas.get(ambito)
        cantidad = e.get('cantidad')
        if tabla is None:
            motivo = (f'sin fuente de costos de {ambito}' if ambito in ('distribucion', 'transmision')
                      else f'ámbito «{ambito}» no es distribucion ni transmision')
        elif cantidad is None or float(cantidad) <= 0:
            motivo = f'{e.get("codigo")}: sin metrado no hay costo supuesto'
        else:
            costo, motivo, anotacion = _costo_del_elemento(e, tabla)
            unidad = str(e.get('unidad') or '').strip()
            if costo is not None and unidad and costo.unidad and unidad.lower() != costo.unidad.lower():
                # Un metrado en m contra un costo por km daría mil veces el costo: no se convierte solo.
                motivo = (f'{e.get("codigo")}: la unidad del metrado «{unidad}» no es la del módulo '
                          f'«{costo.unidad}»; no se convierte')
            elif costo is not None:
                valorados.append({'elemento': nombre, 'ambito': ambito, 'codigo': e.get('codigo'),
                                  'cantidad': float(cantidad), 'unidad': costo.unidad,
                                  'costo_unitario': costo.total, 'costo': float(cantidad) * costo.total,
                                  'moneda': tabla.fuente.moneda, 'fuente': tabla.fuente.resolucion,
                                  'factor': tabla.fuente.factor, 'nombre': costo.nombre,
                                  **({'anotacion': anotacion} if anotacion else {})})
                continue
        sin_costo.append({'elemento': nombre, 'ambito': ambito, 'codigo': e.get('codigo'), 'motivo': motivo})
    total_por_moneda: dict[str, float] = {}
    for x in valorados:
        total_por_moneda[x['moneda']] = total_por_moneda.get(x['moneda'], 0.0) + x['costo']
    return {'fuentes': {a: asdict(t.fuente) for a, t in tablas.items()}, 'total_por_moneda': total_por_moneda,
            'completa': not sin_costo, 'valorados': valorados, 'sin_costo': sin_costo}


def partir_codigo_vnr(codigo: str) -> tuple[str, str]:
    """`AA03503G` → (`AA03503`, `G`): en la red, la letra final del código es la tensión."""
    codigo = str(codigo or '').strip()
    # Un nombre como DEFAULT no es un código de costo: partido daba la tensión falsa «T».
    if len(codigo) < 2 or not codigo[-1].isalpha() or not any(c.isdigit() for c in codigo):
        return codigo, ''
    return codigo[:-1], codigo[-1]


def cruzar_codigos(usos: Iterable[tuple[str, float]], tabla: TablaCostos, *, sector: str, estructura: str) -> dict:
    """Cuánto de una red cruza con los costos, por peso de uso (072:RF-7).

    ``usos``: pares de código de la red y su peso (tramos o km). Lo que no cruza se nombra con su
    motivo; no recibe ningún costo.
    """
    con_costo, sin_costo = [], []
    for codigo_red, peso in usos:
        codigo, tension = partir_codigo_vnr(codigo_red)
        costo = tabla.buscar(codigo, tension, estructura, sector)
        if costo is None:
            sin_costo.append({'codigo': codigo_red, 'peso': peso,
                              'motivo': tabla.motivo_sin_costo(codigo, tension, estructura, sector)})
        else:
            con_costo.append({'codigo': codigo_red, 'peso': peso, 'total': costo.total, 'nombre': costo.nombre})
    total = sum(x['peso'] for x in con_costo) + sum(x['peso'] for x in sin_costo)
    return {'fuente': asdict(tabla.fuente), 'sector': sector, 'estructura': estructura,
            'codigos': len(con_costo) + len(sin_costo), 'codigos_con_costo': len(con_costo),
            'peso_total': total, 'peso_con_costo': sum(x['peso'] for x in con_costo),
            'fraccion_con_costo': (sum(x['peso'] for x in con_costo) / total) if total else None,
            'con_costo': con_costo, 'sin_costo': sin_costo}
