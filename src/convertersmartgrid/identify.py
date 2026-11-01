"""Reconoce qué es cada TXT del export por su contenido, no por su nombre.

Por qué importa. Los TXT que entrega la distribuidora no tienen por qué llamarse
``RED_030826(1).txt`` ni seguir ninguna convención: el nombre lo pone quien hace la
exportación y cambia de una entrega a otra. El conversor ya funciona con cualquier
nombre —comprobado con ``exportacion_enero.txt``, ``demanda.txt`` y ``catalogo.txt``—,
pero precisamente por eso **el nombre no protege de nada**.

Y una de las tres confusiones posibles pasaba sin ruido: poner el catálogo de equipos
en la casilla de cargas producía un dataset con **0 cargas** y la conversión seguía
adelante, entregando una red sin demanda. Un DGS así converge, se importa en DigSILENT
y da un flujo de potencia perfecto de una red que no alimenta a nadie. Es la peor clase
de error: el que no falla.

Cómo se reconoce. Cada fichero del export declara sus tablas entre corchetes y sus
cabeceras ``FORMAT_*``. Basta leer las primeras líneas:

``red``
    Trae ``[NODE]`` y ``[SECTION]``: la topología y la geometría.
``carga``
    Trae ``[CUSTOMER LOADS]`` o ``[LOADS]``: la demanda.
``equipos``
    Trae ``[LINE]``, ``[CONDUCTOR]`` o ``[CONCENTRIC NEUTRAL CABLE]``: el catálogo.

Solo se leen las primeras líneas, así que reconocer los tres ficheros de un export de
150 MB cuesta milisegundos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RED = 'red'
CARGA = 'carga'
EQUIPOS = 'equipos'
DESCONOCIDO = ''

#: Nombre legible de cada tipo, para los mensajes.
NOMBRES = {
    RED: 'RED (topología: nodos, tramos y fuentes)',
    CARGA: 'CARGA (demanda: cargas por cliente)',
    EQUIPOS: 'BD_Equipo (catálogo: conductores, cables y equipos)',
    DESCONOCIDO: 'no reconocido',
}

#: Tablas que identifican cada tipo. Se exige **al menos una** de las de su fila.
#:
#: El orden de comprobación importa: el RED se mira primero porque es el único que trae
#: ``[NODE]``, y el catálogo antes que la carga porque un BD_Equipo no tiene ninguna
#: tabla de demanda pero sí muchas tablas propias.
MARCADORES: tuple[tuple[str, frozenset[str]], ...] = (
    (RED, frozenset({'NODE', 'SECTION', 'HEADNODES', 'INTERMEDIATE NODES'})),
    (EQUIPOS, frozenset({'LINE', 'CONDUCTOR', 'CONCENTRIC NEUTRAL CABLE',
                         'SPACING TABLE FOR LINE', 'SUBSTATION', 'TRANSFORMER'})),
    (CARGA, frozenset({'CUSTOMER LOADS', 'LOADS'})),
)

#: Cuántas líneas se leen. Las tablas aparecen en la cabecera del fichero; leer más solo
#: gastaría tiempo en exports de cientos de megas.
LINEAS_A_MIRAR = 4000


@dataclass(frozen=True)
class Identificacion:
    """Qué resultó ser un fichero, y con qué evidencia."""

    ruta: Path
    tipo: str
    tablas: frozenset[str]

    @property
    def nombre(self) -> str:
        return NOMBRES[self.tipo]

    def evidencia(self, limite: int = 6) -> str:
        vistas = sorted(self.tablas)[:limite]
        cola = '' if len(self.tablas) <= limite else f' (+{len(self.tablas) - limite})'
        return ', '.join(f'[{t}]' for t in vistas) + cola if vistas else 'ninguna tabla'


def tablas_de(path: Path | str, *, limite: int = LINEAS_A_MIRAR) -> frozenset[str]:
    """Nombres de tabla que declara el fichero, en mayúsculas."""
    encontradas: set[str] = set()
    ruta = Path(path)
    try:
        with ruta.open('r', encoding='utf-8', errors='replace', newline='') as fh:
            for i, linea in enumerate(fh):
                if i >= limite:
                    break
                s = linea.strip()
                if s.startswith('[') and s.endswith(']'):
                    encontradas.add(s[1:-1].strip().upper())
    except OSError:
        return frozenset()
    return frozenset(encontradas)


def identificar(path: Path | str) -> Identificacion:
    """Qué es este fichero, mirando lo que trae dentro."""
    ruta = Path(path)
    tablas = tablas_de(ruta)
    for tipo, marcadores in MARCADORES:
        if tablas & marcadores:
            return Identificacion(ruta, tipo, tablas)
    return Identificacion(ruta, DESCONOCIDO, tablas)


def comprobar_ranura(path: Path | str, esperado: str) -> str:
    """Mensaje de error si el fichero no es lo que esa casilla espera; '' si encaja.

    Devuelve texto en lugar de lanzar para que lo use igual la interfaz —que quiere
    avisar al elegir el fichero— y el motor, que quiere abortar.
    """
    ident = identificar(path)
    if ident.tipo == esperado:
        return ''
    ruta = Path(path)
    if ident.tipo == DESCONOCIDO:
        return (
            f'«{ruta.name}» no parece un export de CYMDIST: no declara ninguna de '
            f'las tablas conocidas. Tablas que trae: {ident.evidencia()}.'
        )
    return (
        f'«{ruta.name}» es el {ident.nombre}, y aquí va el {NOMBRES[esperado]}.\n'
        f'Lo delatan sus tablas: {ident.evidencia()}.\n'
        f'El nombre del fichero no importa —puede llamarse como quiera—, pero el '
        f'contenido tiene que corresponder con la casilla.'
    )


def repartir(rutas) -> dict[str, Path]:
    """Asigna cada fichero a su papel por el contenido, sin mirar el nombre.

    Sirve para cuando llegan tres ficheros sueltos de una entrega nueva y nadie sabe
    cuál es cuál. Si dos resultan ser lo mismo, se queda el primero y el otro no se
    asigna: es preferible dejar una casilla vacía a rellenarla con el fichero
    equivocado.
    """
    reparto: dict[str, Path] = {}
    for ruta in rutas:
        ident = identificar(ruta)
        if ident.tipo and ident.tipo not in reparto:
            reparto[ident.tipo] = Path(ruta)
    return reparto


#: Las tres fuentes del conversor (spec 059). Cada fichero dice a cuál pertenece.
FUENTE_TXT = 'txt'
FUENTE_MDB = 'mdb'
FUENTE_VNR = 'vnr'

#: Lo que Access escribe a partir del byte 4 de toda base: Jet (.mdb) o ACE (.accdb).
_FIRMAS_ACCESS = (b'Standard Jet DB', b'Standard ACE DB')


@dataclass(frozen=True)
class Fuente:
    """A qué fuente pertenece un fichero y, si es un TXT, cuál de los tres es."""

    fuente: str  # FUENTE_TXT, FUENTE_MDB, FUENTE_VNR o DESCONOCIDO
    tipo: str = DESCONOCIDO  # RED, CARGA o EQUIPOS, solo para los TXT
    motivo: str = ''


def es_base_access(path: Path | str) -> bool:
    """¿Es una base de Access? Por su cabecera, no por la extensión."""
    try:
        with Path(path).open('rb') as fh:
            cabecera = fh.read(32)
    except OSError:
        return False
    return any(cabecera[4:4 + len(f)] == f for f in _FIRMAS_ACCESS)


#: Extensiones que VNR-GIS admite y que también son de las otras fuentes o genéricas: un .txt
#: o un .csv cualquiera no es un paquete VNR-GIS por llamarse así.
_EXTENSIONES_COMPARTIDAS = frozenset({'.txt', '.csv', '.tsv', '.json', '.mdb', '.accdb'})


def fuente_de(path: Path | str) -> Fuente:
    """La fuente del fichero por su contenido (059:RF-3).

    El 2026-11-01 la web abrió un espacio vacío como «Tres TXT de CYMDIST» por un valor por
    defecto, con el de Electro Oriente, que es VNR-GIS: nada se supone, lo dice el fichero.
    El orden importa: Access por su cabecera y CYMDIST por sus tablas antes que VNR-GIS, que
    por extensión admite también .txt y .mdb.
    """
    ruta = Path(path)
    if es_base_access(ruta):
        return Fuente(FUENTE_MDB)
    ident = identificar(ruta)
    if ident.tipo != DESCONOCIDO:
        return Fuente(FUENTE_TXT, ident.tipo)
    try:
        from vnr_etl.connectors.sqlserver_vnr import es_copia_sql
        from vnr_etl.discovery.official import (
            OfficialDiscoveryError, validate_vnr_package_file,
        )
    except ImportError:  # sin el módulo VNR no se reconoce un paquete
        pass
    else:
        if es_copia_sql(ruta) or ruta.suffix.lower() not in _EXTENSIONES_COMPARTIDAS:
            try:
                validate_vnr_package_file(ruta)
            except OfficialDiscoveryError:
                pass
            else:
                return Fuente(FUENTE_VNR)
    return Fuente(DESCONOCIDO, motivo=(
        f'«{ruta.name}» no es un TXT de CYMDIST (no declara tablas conocidas), ni una base '
        'Access, ni un paquete VNR-GIS'))
