"""Costos oficiales del PIDE: un contrato para cada fuente y el cruce con la red (spec 072).

El SICODI se publica en Procesos Regulatorios de Osinergmin como TXT separados por tabuladores.
Un costo depende de código, tensión, estructura y sector típico: `AA03503G` es el código `AA03503`
a 22,9 kV (`G`), y el mismo código cuesta distinto en madera que en concreto. Sin alguno de esos
datos no hay costo: se nombra el hueco, porque un costo supuesto se confunde con uno oficial. Por
eso tampoco hay factores por defecto: el informe de Electro Oriente aplicó 1,8 sobre mercado y la
carpeta de su cálculo estaba vacía.

Las obras de transmisión se valoran con los módulos estándar de inversión (Res. 152-2026-OS/CD,
cuya base sustituyó la Res. 181-2026-OS/CD), por el mismo contrato y nunca con el SICODI: un
elemento de una obra lleva el ámbito de su fuente y solo esa lo valora (072:RF-6).
"""
from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

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

    def __post_init__(self):
        self.codigos = {k[0] for k in self.filas}
        self.tensiones = {k[1] for k in self.filas}
        self.sectores = {k[3] for k in self.filas}
        self._estructuras: dict[tuple[str, str, str], set[str]] = {}
        for k in self.filas:
            self._estructuras.setdefault((k[0], k[1], k[3]), set()).add(k[2])

    def buscar(self, codigo: str, tension: str, estructura: str, sector: str) -> Costo | None:
        """El costo exacto, o ``None``: nunca el más parecido (072:RF-7)."""
        return self.filas.get((codigo, tension, estructura, sector))

    def estructura_unica(self, codigo: str, tension: str, sector: str) -> str | None:
        """La estructura si el costo solo existe con una: un cable subterráneo no lleva postes."""
        hallados = self._estructuras.get((codigo, tension, sector), ())
        return next(iter(hallados)) if len(hallados) == 1 else None

    def motivo_sin_costo(self, codigo: str, tension: str, estructura: str, sector: str) -> str:
        """Por qué no hay costo, para nombrar el hueco (072:RF-7)."""
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
    """Lee `Instalacion.txt` del zip público del SICODI (072:RF-5, RF-9)."""
    ruta = Path(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    fuente = FuenteCostos('SICODI', 'distribucion', resolucion, anio, moneda, url, fecha_descarga, huella,
                          factor, sustento_factor)
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
    return TablaCostos(fuente, filas)


#: Lo que un libro de módulos debe declarar, con el nombre de su columna en esa resolución.
COLUMNAS_MODULOS = ('codigo', 'nombre', 'unidad', 'total')
_COLUMNAS_MODULOS_OPCIONALES = ('zona', 'familia')
#: Cuántas filas se miran para hallar la cabecera: los anexos llevan títulos encima.
_FILAS_CABECERA = 30


def leer_modulos_transmision(ruta: Path | str, *, columnas: Mapping[str, str], resolucion: str, anio: int,
                             moneda: str, url: str, fecha_descarga: str, hoja: str | Sequence[str] | None = None,
                             unidad: str | Mapping[str, str] | None = None, factor: float | None = None,
                             sustento_factor: str | None = None) -> TablaCostos:
    """Lee un libro de módulos estándar de transmisión (072:RF-5, RF-6, RF-9).

    ``columnas`` lleva el nombre de cada columna en el libro: `codigo`, `nombre`, `unidad` y
    `total`, y si la base distingue zona, `zona`. Se declaran porque la disposición es de cada
    resolución (la 8-2026 publicó un `.xlsm` y la 59-2026 lo reemplazó por otro): suponer una
    sería leer mal la siguiente sin avisar.

    La base de la Res. 152-2026-OS/CD (`REST_MOD_INV_2025_PU.xlsm`) trae una hoja de resumen por tipo
    de módulo (líneas, celdas, transformadores…) y ninguna columna de unidad: el costo de una línea es
    por km y el de una celda por unidad. Por eso ``hoja`` admite varias hojas y ``unidad`` declara la
    de todas o la de cada hoja en lugar de la columna; sin declararla de ninguna forma, se rechaza.
    """
    from openpyxl import load_workbook

    faltan = [k for k in COLUMNAS_MODULOS if not str(columnas.get(k) or '').strip()
              and not (k == 'unidad' and unidad)]
    if faltan:
        raise CostosError(f'los módulos de transmisión no declaran la columna de: {", ".join(faltan)}')
    hojas = [hoja] if isinstance(hoja, str) or hoja is None else list(hoja)
    if isinstance(unidad, Mapping):
        sin_unidad = [str(h) for h in hojas if not str(unidad.get(h) or '').strip()]
        if sin_unidad:
            raise CostosError(f'sin unidad declarada para la hoja: {", ".join(sin_unidad)}')
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
        con_zona |= _modulos_de_hoja(ruta.name, titulo, filas, columnas, fija, fuente, tabla)
    if not tabla:
        raise CostosError(f'{ruta.name}: la hoja no trae ningún módulo bajo la cabecera')
    return TablaCostos(fuente, tabla, con_zona)


def _modulos_de_hoja(nombre: str, titulo: str, filas: list, columnas: Mapping[str, str], fija: str | None,
                     fuente: FuenteCostos, tabla: dict) -> bool:
    """Añade a ``tabla`` los módulos de una hoja y dice si la hoja distingue zona."""
    usadas = {k: str(v).strip() for k, v in columnas.items()
              if k in COLUMNAS_MODULOS + _COLUMNAS_MODULOS_OPCIONALES and str(v or '').strip()
              and not (k == 'unidad' and fija)}
    buscadas = set(usadas.values())
    n_cab = next((n for n, f in enumerate(filas[:_FILAS_CABECERA])
                  if buscadas <= {str(c).strip() for c in f if c is not None}), None)
    if n_cab is None:
        vistas = {str(c).strip() for f in filas[:_FILAS_CABECERA] for c in f if c is not None}
        faltan = sorted(buscadas - vistas)
        raise CostosError(f'{nombre}, hoja «{titulo}»: ninguna fila trae las columnas declaradas; faltan: '
                          f'{", ".join(faltan) or "todas en una misma fila"}')
    cab = [str(c).strip() if c is not None else '' for c in filas[n_cab]]
    i = {k: cab.index(v) for k, v in usadas.items()}
    con_zona = 'zona' in i

    def celda(f, k):
        v = f[i[k]] if k in i and i[k] < len(f) else None
        return '' if v is None else str(v).strip()

    for n, f in enumerate(filas[n_cab + 1:], n_cab + 2):
        codigo = celda(f, 'codigo')
        # Las filas sin código son títulos o subtotales del anexo, no módulos.
        if not codigo:
            continue
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
                             celda(f, 'familia'), fija or celda(f, 'unidad'))
    return con_zona


def exigir_ambito(tabla: TablaCostos, ambito: str) -> None:
    """Una fuente solo valora su ámbito: el SICODI no es de transmisión ni los módulos de distribución (072:RF-6)."""
    if tabla.fuente.ambito != ambito:
        raise CostosError(f'{tabla.fuente.nombre} es de ámbito «{tabla.fuente.ambito}», no de «{ambito}»')


def _costo_del_elemento(e: Mapping, tabla: TablaCostos) -> tuple[Costo | None, str]:
    codigo_red = str(e.get('codigo') or '').strip()
    if tabla.fuente.ambito == 'distribucion':
        codigo, tension = partir_codigo_vnr(codigo_red)
        sector, estructura = str(e.get('sector') or ''), str(e.get('estructura') or '')
        costo = tabla.buscar(codigo, tension, estructura, sector)
        return costo, ('' if costo else tabla.motivo_sin_costo(codigo, tension, estructura, sector))
    zona = str(e.get('zona') or '').strip()
    costo = tabla.buscar_modulo(codigo_red, zona)
    return costo, ('' if costo else tabla.motivo_sin_modulo(codigo_red, zona))


def valorar_obra(elementos: Iterable[Mapping], tablas: Mapping[str, TablaCostos]) -> dict:
    """Metrado × costo de cada elemento de una obra, con la fuente de su ámbito (072:RF-6, RF-7, RF-15).

    Cada elemento declara `elemento`, `ambito` (`distribucion` o `transmision`), `codigo` y
    `cantidad`; los de distribución, además, `sector` y `estructura`; los de transmisión, `zona`
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
            costo, motivo = _costo_del_elemento(e, tabla)
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
                                  'factor': tabla.fuente.factor, 'nombre': costo.nombre})
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
