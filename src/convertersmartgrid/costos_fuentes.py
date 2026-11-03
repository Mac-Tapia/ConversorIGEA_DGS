"""Costos oficiales del PIDE: un contrato para cada fuente y el cruce con la red (spec 072).

El SICODI se publica en Procesos Regulatorios de Osinergmin como TXT separados por tabuladores.
Un costo depende de código, tensión, estructura y sector típico: `AA03503G` es el código `AA03503`
a 22,9 kV (`G`), y el mismo código cuesta distinto en madera que en concreto. Sin alguno de esos
datos no hay costo: se nombra el hueco, porque un costo supuesto se confunde con uno oficial. Por
eso tampoco hay factores por defecto: el informe de Electro Oriente aplicó 1,8 sobre mercado y la
carpeta de su cálculo estaba vacía.
"""
from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Iterable, Mapping
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

    @property
    def total(self) -> float:
        """El total oficial, con el factor solo si la fuente lo declaró con sustento."""
        return self.componentes['total'] * (self.fuente.factor if self.fuente.factor is not None else 1.0)


@dataclass
class TablaCostos:
    """Los costos de una fuente, indexados una sola vez: nada de recorrerla por tramo."""

    fuente: FuenteCostos
    filas: dict[tuple[str, str, str, str], Costo] = field(default_factory=dict)

    def __post_init__(self):
        self.codigos = {k[0] for k in self.filas}
        self.tensiones = {k[1] for k in self.filas}
        self.sectores = {k[3] for k in self.filas}

    def buscar(self, codigo: str, tension: str, estructura: str, sector: str) -> Costo | None:
        """El costo exacto, o ``None``: nunca el más parecido (072:RF-7)."""
        return self.filas.get((codigo, tension, estructura, sector))

    def motivo_sin_costo(self, codigo: str, tension: str, estructura: str, sector: str) -> str:
        """Por qué no hay costo, para nombrar el hueco (072:RF-7)."""
        if not sector or sector not in self.sectores:
            return f'sector típico «{sector}» no está en {self.fuente.nombre}'
        if tension not in self.tensiones:
            return f'tensión «{tension}» no está en {self.fuente.nombre}'
        if codigo not in self.codigos:
            return f'código {codigo} no está en {self.fuente.nombre}'
        return f'{codigo}{tension} sin estructura «{estructura}» en {sector}'


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
        filas[clave] = Costo(clave[0], clave[1], clave[2], clave[3], v[i['NOMBRE']], componentes, fuente)
    return TablaCostos(fuente, filas)


def partir_codigo_vnr(codigo: str) -> tuple[str, str]:
    """`AA03503G` → (`AA03503`, `G`): en la red, la letra final del código es la tensión."""
    codigo = str(codigo or '').strip()
    if len(codigo) < 2 or not codigo[-1].isalpha():
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
