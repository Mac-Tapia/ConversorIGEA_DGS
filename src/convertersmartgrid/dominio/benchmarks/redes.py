"""Benchmark de redes: el trío TXT de CYMDIST con una lista cerrada de secciones y columnas (112:RF-1, RF-2, RF-3, RF-10).

El benchmark es un export que el conversor ya lee, así que prueba también el lector y las reglas (plan de la 112). Se
escribe solo lo que figura en ``SECCIONES``: cada columna con su clase (identificador de un tipo, coordenada, número o
código corto). Lo que no figura se omite y se anota por nombre, nunca por valor; por eso las columnas de texto libre
(etiquetas, descripciones, el comentario de ``[GENERAL]``) no salen nunca (RF-10). Una columna que nadie previó no se
publica: es la razón de una lista cerrada frente a «quitar lo que se detecte».

La disposición del origen se conserva línea a línea (constitución P3): el ``FORMAT_SECTION`` antes del primer
``FEEDER=`` en la completa y tras cada ``FEEDER=`` en la reducida. Todo es local: ni red ni proveedores (RF-1).
"""
from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..dataset import TABLAS_TIPOS_AEREO, TABLAS_TIPOS_LINEA, TABLAS_TIPOS_SUBTERRANEO
from ..model import extract_sed_code, suggest_catalog_code
from ..perfil_empresa import PerfilEmpresa
from .seudonimos import Mapa, ORIGEN_NEUTRO, origen_lejano, transformar_coordenadas

#: Clases de columna. ``('id', tipo)`` pasa por el mapa; ``('sed', tipo)`` además conserva el código de SED que el
#: modelo saca de su sufijo; ``x``/``y`` son coordenadas; ``num`` un número; ``cod`` un código corto (fase, estado).
ID_ = 'id'
SED_ = 'sed'
_X, _Y, _NUM, _COD = 'x', 'y', 'num', 'cod'

_TRAMO = (SED_, 'tramo')
_NODO = (ID_, 'nodo')
_RED = (ID_, 'alimentador')
_EQUIPO = (ID_, 'equipo')
_TIPO = (ID_, 'tipo_equipo')

_MANIOBRA = {'SectionID': _TRAMO, 'Location': _COD, 'EqType': _COD, 'EqID': _TIPO, 'EqNumber': _EQUIPO,
             'EqPhase': _COD, 'Status': _COD, 'Locked': _COD, 'EqState': _COD}
_AJUSTE_LINEA = {'SectionID': _TRAMO, 'LineCableID': _TIPO, 'Length': _NUM}
_TIPO_LINEA = {'ID': _TIPO, 'R1': _NUM, 'R0': _NUM, 'X1': _NUM, 'X0': _NUM, 'B1': _NUM, 'B0': _NUM,
               'Amps': _NUM, 'Amps_2': _NUM}

#: Lista cerrada, por fichero y sección: lo único que el benchmark lleva. Son las columnas que lee el conversor.
SECCIONES: dict[str, dict[str, dict[str, object]]] = {
    'RED.txt': {
        'HEADNODES': {'NodeID': _NODO, 'NetworkID': _RED},
        'NODE': {'NodeID': _NODO, 'CoordX': _X, 'CoordY': _Y},
        'SOURCE': {'SourceID': _EQUIPO, 'DeviceNumber': _EQUIPO, 'NodeID': _NODO, 'NetworkID': _RED,
                   'DesiredVoltage': _NUM, 'OperatingVoltageA': _NUM, 'OperatingVoltageB': _NUM,
                   'OperatingVoltageC': _NUM},
        'LINE CONFIGURATION': {'SectionID': _TRAMO, 'LineCableID': _TIPO, 'Length': _NUM, 'Overhead': _COD},
        'OVERHEADLINE SETTING': _AJUSTE_LINEA,
        'UNDERGROUNDLINE SETTING': _AJUSTE_LINEA,
        'SECTION': {'SectionID': _TRAMO, 'FromNodeID': _NODO, 'FromNodeIndex': _COD, 'ToNodeID': _NODO,
                    'ToNodeIndex': _COD, 'Phase': _COD},
        'SWITCH SETTING': _MANIOBRA,
        'SECTIONALIZER SETTING': _MANIOBRA,
        'INTERMEDIATE NODES': {'SectionID': _TRAMO, 'SeqNumber': _NUM, 'CoordX': _X, 'CoordY': _Y},
        'SHUNT CAPACITOR SETTING': {
            'SectionID': _TRAMO, 'DeviceNumber': _EQUIPO, 'EqID': _TIPO, 'NodeID': _NODO, 'NetworkID': _RED,
            'Location': _COD, 'Phase': _COD, 'EqPhase': _COD, 'Status': _COD, 'Connection': _COD,
            'NumberOfSteps': _NUM, 'KVARPerStep': _NUM, 'TotalKVAR': _NUM, 'KVAR': _NUM, 'RatedKVAR': _NUM,
            'NominalKV': _NUM, 'KVLN': _NUM},
    },
    'CARGA.txt': {
        'LOADS': {'SectionID': _TRAMO, 'DeviceNumber': (SED_, 'equipo'), 'LoadType': _COD, 'Connection': _COD,
                  'Location': _COD},
        'CUSTOMER LOADS': {
            'SectionID': _TRAMO, 'DeviceNumber': (SED_, 'equipo'), 'LoadType': _COD,
            'CustomerNumber': (SED_, 'cliente'), 'CustomerType': _COD, 'Status': _COD, 'Year': _NUM,
            'ValueType': _COD, 'Phase': _COD, 'Value1': _NUM, 'Value2': _NUM, 'ConnectedKVA': _NUM, 'KWH': _NUM,
            'NumberOfCustomer': _NUM, 'SedCode': (SED_, 'sed')},
    },
    'BD_Equipo.txt': {
        'LINE': {**_TIPO_LINEA, 'LockImpedance': _COD},
        'CONCENTRIC NEUTRAL CABLE': _TIPO_LINEA,
        'CABLE': _TIPO_LINEA,
    },
}
#: Las cabeceras ``FEEDER=`` de ``[SECTION]``: el resto de sus columnas (descripción, color, año) no sale.
COLUMNAS_FEEDER = {'NetworkID': _RED, 'HeadNodeID': _NODO}
FEEDER_CYMDIST = ('NetworkID', 'HeadNodeID', 'CoordSet', 'Year', 'Description', 'Color', 'LoadFactor')
#: Palabra de CYMDIST, no de ninguna empresa: el marcador de los puentes (reglas.py) se conserva tal cual.
PALABRAS_RESERVADAS = frozenset({'DEFAULT'})
_CODIGO_CORTO = re.compile(r'^[A-Za-z0-9.+_-]{0,12}$')


class ColumnaNoAdmitida(ValueError):
    """Un valor de una columna de la lista cerrada no tiene la forma de su clase: no se publica."""


@dataclass
class Fichero:
    nombre: str
    #: ('seccion', nombre) | ('formato', etiqueta, columnas) | ('feeder', columnas, valores) | ('fila', seccion, fila)
    entradas: list[tuple] = field(default_factory=list)


@dataclass
class InformeRed:
    """Lo que hizo el benchmark de redes. El mapa va aparte y no sale en la representación (112:RF-2)."""

    ficheros: list[str]
    columnas_omitidas: dict[str, dict[str, list[str]]]
    secciones_omitidas: dict[str, list[str]]
    perfil_neutro: PerfilEmpresa
    mapa: Mapa = field(repr=False, compare=False)


def _valores(linea: str) -> list[str]:
    return [v.strip() for v in next(csv.reader([linea]))]


def leer_fichero(ruta: Path | str, nombre: str) -> Fichero:
    """Lee un TXT de CYMDIST como secuencia de secciones, formatos, cabeceras ``FEEDER=`` y filas, en su orden."""
    f = Fichero(nombre)
    seccion: str | None = None
    columnas: list[str] | None = None
    por_seccion: dict[str, list[str]] = {}
    # Sin FORMAT_FEEDER (la disposición reducida no lo declara), las columnas de CYMDIST, que no son de ninguna empresa.
    feeder: list[str] = list(FEEDER_CYMDIST)
    with Path(ruta).open('r', encoding='utf-8', errors='replace', newline='') as fh:
        for crudo in fh:
            linea = crudo.strip()
            if not linea:
                continue
            if linea.startswith('[') and linea.endswith(']'):
                seccion, columnas = linea[1:-1].strip().upper(), None
                f.entradas.append(('seccion', seccion))
                continue
            if seccion is None:
                continue
            if linea.startswith('FORMAT_') and '=' in linea:
                etiqueta, _, resto = linea.partition('=')
                cols = _valores(resto)
                if etiqueta.strip().upper() == 'FORMAT_FEEDER':
                    feeder = cols
                else:
                    columnas = por_seccion[seccion] = cols
                f.entradas.append(('formato', etiqueta.strip(), cols))
                continue
            if seccion == 'SECTION' and linea.startswith('FEEDER='):
                f.entradas.append(('feeder', feeder, _valores(linea.split('=', 1)[1])))
                columnas = por_seccion.get(seccion)
                continue
            if columnas is None:
                continue
            valores = _valores(linea)
            f.entradas.append(('fila', seccion, dict(zip(columnas, valores + [''] * (len(columnas) - len(valores))))))
    return f


def _columnas_de(fichero: str, seccion: str, etiqueta: str) -> dict[str, object] | None:
    if etiqueta.upper() == 'FORMAT_FEEDER':
        return COLUMNAS_FEEDER
    return SECCIONES[fichero].get(seccion)


def _es_medicion(codigo: str, perfil: PerfilEmpresa | None) -> bool:
    patron = perfil.patron_sed_medicion if perfil else None
    return bool(patron and re.search(patron, codigo))


def registrar(ficheros: list[Fichero], mapa: Mapa, perfil: PerfilEmpresa | None = None) -> None:
    """Apunta en el mapa cada identificador del trío, antes de congelarlo (el mismo original, el mismo seudónimo)."""
    for f in ficheros:
        for e in f.entradas:
            if e[0] == 'fila':
                clases, fila = SECCIONES[f.nombre].get(e[1]), e[2]
            elif e[0] == 'feeder':
                clases, fila = COLUMNAS_FEEDER, dict(zip(e[1], e[2]))
            else:
                continue
            for col, clase in (clases or {}).items():
                valor = fila.get(col, '')
                if not isinstance(clase, tuple) or not valor or valor in PALABRAS_RESERVADAS:
                    continue
                mapa.registrar(clase[1], valor)
                if clase[0] == SED_ and (codigo := extract_sed_code(valor)):
                    mapa.registrar('medidor' if _es_medicion(codigo, perfil) else 'sed', codigo)


def _con_guion(seudonimo: str) -> str:
    """``BT012`` → ``BT-012``: el extractor de SED del modelo no ve en él ningún código (no hay letra seguida de cifra)."""
    return re.sub(r'^(B[A-Z])(\d+)$', r'\1-\2', seudonimo)


def _traductor(mapa: Mapa, perfil: PerfilEmpresa | None,
               con_ficha: frozenset[str] = frozenset()) -> Callable[[tuple, str], str]:
    def traducir(clase: tuple, valor: str) -> str:
        if not valor or valor in PALABRAS_RESERVADAS:
            return valor
        if clase[0] == ID_:
            seudonimo = str(mapa(clase[1], valor))
            # Un tipo sin ficha en el BD_Equipo lo resuelve el modelo por el parecido del nombre (suggest_catalog_code):
            # con guion, su seudónimo no se parece a ningún otro y cae igual que en el original (a DEFAULT).
            return _con_guion(seudonimo) if clase[1] == 'tipo_equipo' and valor not in con_ficha else seudonimo
        # Con sufijo de SED: el seudónimo conserva un sufijo con el seudónimo de su SED, para que el modelo agrupe las
        # mismas cargas en la misma SED. Sin sufijo, un seudónimo en el que no se reconoce ninguno.
        codigo = extract_sed_code(valor)
        if not codigo:
            return _con_guion(str(mapa(clase[1], valor)))
        sed = str(mapa('medidor' if _es_medicion(codigo, perfil) else 'sed', codigo))
        return sed if codigo == valor else f'{_con_guion(str(mapa(clase[1], valor)))}_{sed}'
    return traducir


def _tipos_por_codigo(ficheros: list[Fichero]) -> dict[str, list[tuple[str, dict[str, str]]]]:
    """Las fichas de conductor del BD_Equipo por código, en el orden de tablas del modelo."""
    por_codigo: dict[str, list[tuple[str, dict[str, str]]]] = {}
    equipo = next((f for f in ficheros if f.nombre == 'BD_Equipo.txt'), None)
    filas = [(e[1], e[2]) for e in (equipo.entradas if equipo else ()) if e[0] == 'fila' and e[1] in TABLAS_TIPOS_LINEA]
    for tabla in TABLAS_TIPOS_LINEA:
        for t, fila in filas:
            if t == tabla and fila.get('ID'):
                por_codigo.setdefault(fila['ID'], []).append((t, fila))
    return por_codigo


def _elegir(candidatos: list[tuple[str, dict[str, str]]], aereo: bool) -> tuple[str, dict[str, str]] | None:
    """La ficha que tomaría el modelo entre las de un código: la única, o la de la tabla de su clase."""
    if len(candidatos) == 1:
        return candidatos[0]
    for tabla in (TABLAS_TIPOS_AEREO if aereo else TABLAS_TIPOS_SUBTERRANEO):
        for c in candidatos:
            if c[0] == tabla:
                return c
    return None


def resolver_tipos(ficheros: list[Fichero]) -> list[str]:
    """Escribe en el BD_Equipo, con su propio código, la ficha que el modelo tomaría por parecido de nombre (112:RF-3).

    El modelo resuelve un conductor sin ficha por el código más parecido del catálogo. Con los seudónimos, el parecido
    sería otro (en la red real, tres alimentadores cambiaban su carga máxima de líneas un 3 %): por eso se resuelve en el
    original y la ficha elegida se copia con el código del tramo. Devuelve los códigos completados, por nombre.
    """
    por_codigo = _tipos_por_codigo(ficheros)
    usados: set[tuple[str, bool]] = set()
    for f in ficheros:
        if f.nombre != 'RED.txt':
            continue
        for e in f.entradas:
            if e[0] != 'fila' or not e[2].get('LineCableID'):
                continue
            if e[1] == 'LINE CONFIGURATION':
                usados.add((e[2]['LineCableID'], e[2].get('Overhead', '1') == '1'))
            elif e[1] in ('OVERHEADLINE SETTING', 'UNDERGROUNDLINE SETTING'):
                usados.add((e[2]['LineCableID'], e[1].startswith('OVERHEAD')))
    nuevas: dict[tuple[str, str], dict[str, str]] = {}
    for codigo, aereo in sorted(usados):
        if codigo in por_codigo or codigo in PALABRAS_RESERVADAS:
            continue
        parecido = suggest_catalog_code(codigo, list(por_codigo))
        elegida = _elegir(por_codigo[parecido], aereo) if parecido and parecido != codigo else None
        if elegida is not None:
            nuevas.setdefault((elegida[0], codigo), {**elegida[1], 'ID': codigo})
    if not nuevas:
        return []
    equipo = next(f for f in ficheros if f.nombre == 'BD_Equipo.txt')
    for (tabla, _codigo), fila in sorted(nuevas.items()):
        ultima = max((i for i, e in enumerate(equipo.entradas) if e[0] == 'fila' and e[1] == tabla), default=None)
        if ultima is None:     # la tabla no estaba: se abre con las columnas de la lista cerrada
            equipo.entradas += [('seccion', tabla),
                                ('formato', 'FORMAT_' + tabla.replace(' ', ''), list(SECCIONES['BD_Equipo.txt'][tabla])),
                                ('fila', tabla, fila)]
        else:
            equipo.entradas.insert(ultima + 1, ('fila', tabla, fila))
    return sorted({c for _t, c in nuevas})


def _numero(valor: str) -> bool:
    try:
        float(valor)
    except ValueError:
        return valor in ('', 'None')
    return True


def _coordenadas(ficheros: list[Fichero], semilla: int) -> dict[tuple[float, float], tuple[float, float]]:
    """Todas las coordenadas a la vez, para que el centroide y el giro sean los mismos para toda la red."""
    puntos: set[tuple[float, float]] = set()
    for f in ficheros:
        for e in f.entradas:
            if e[0] != 'fila':
                continue
            clases = SECCIONES[f.nombre].get(e[1]) or {}
            cx = next((c for c, k in clases.items() if k == _X), None)
            cy = next((c for c, k in clases.items() if k == _Y), None)
            if cx and cy and e[2].get(cx) and e[2].get(cy):
                try:
                    puntos.add((float(e[2][cx]), float(e[2][cy])))
                except ValueError:
                    raise ColumnaNoAdmitida(f'{f.nombre} [{e[1]}]: una coordenada no es un número') from None
    orden = sorted(puntos)
    if not orden:
        return {}
    # Lejos del original (T7): con la red girada en el primer origen neutro se mide su extensión, y se elige el
    # primer origen de la lista con el que no cae a menos de 100 km de su recuadro.
    recuadro = (min(x for x, _ in orden), min(y for _, y in orden), max(x for x, _ in orden),
                max(y for _, y in orden))
    ox, oy = ORIGEN_NEUTRO
    girados = transformar_coordenadas(orden, semilla=semilla)
    extension = (min(x for x, _ in girados) - ox, min(y for _, y in girados) - oy,
                 max(x for x, _ in girados) - ox, max(y for _, y in girados) - oy)
    origen = origen_lejano(recuadro, extension)
    return dict(zip(orden, transformar_coordenadas(orden, semilla=semilla, origen=origen)))


def geometria_del_trio(ficheros: list[Fichero]) -> tuple[list[tuple[str, str, list[tuple[str, str, str]]]],
                                                         dict[str, tuple[float, str]],
                                                         tuple[float, float, float, float] | None]:
    """Lo que el trazado sintético necesita del trío leído (112:RF-13): los alimentadores con su cabecera y sus tramos,
    la longitud y el tipo de cada tramo, y el recuadro de las coordenadas originales (para situar el trazado lejos)."""
    red = next(f for f in ficheros if f.nombre == 'RED.txt')
    cabeceras: dict[str, str] = {}
    tramos: dict[str, list[tuple[str, str, str]]] = {}
    largos: dict[str, tuple[float, str]] = {}
    xs: list[float] = []
    ys: list[float] = []
    actual = None
    for e in red.entradas:
        if e[0] == 'feeder':
            fila = dict(zip(e[1], e[2]))
            actual = fila.get('NetworkID')
            cabeceras.setdefault(actual, fila.get('HeadNodeID', ''))
            tramos.setdefault(actual, [])
        elif e[0] != 'fila':
            continue
        elif e[1] == 'SOURCE' and e[2].get('NetworkID'):
            cabeceras[e[2]['NetworkID']] = e[2].get('NodeID') or cabeceras.get(e[2]['NetworkID'], '')
        elif e[1] == 'SECTION' and actual:
            tramos[actual].append((e[2]['SectionID'], e[2]['FromNodeID'], e[2]['ToNodeID']))
        elif e[1] in ('LINE CONFIGURATION', 'OVERHEADLINE SETTING', 'UNDERGROUNDLINE SETTING'):
            try:
                largos.setdefault(e[2]['SectionID'], (float(e[2].get('Length') or 'nan'), e[2].get('LineCableID', '')))
            except ValueError:
                raise ColumnaNoAdmitida(f'RED.txt [{e[1]}]: una longitud no es un número') from None
        elif e[1] == 'NODE' and e[2].get('CoordX') and e[2].get('CoordY'):
            xs.append(float(e[2]['CoordX']))
            ys.append(float(e[2]['CoordY']))
    alimentadores = [(r, cabeceras.get(r, ''), tramos[r]) for r in tramos if cabeceras.get(r)]
    recuadro = (min(xs), min(ys), max(xs), max(ys)) if xs and ys else None
    return alimentadores, largos, recuadro


SECCIONES_LARGO = ('LINE CONFIGURATION', 'OVERHEADLINE SETTING', 'UNDERGROUNDLINE SETTING')


def _filas_intermedias(columnas: list[str], intermedios: dict[str, list[tuple[float, float]]], traducir) -> list[str]:
    filas = []
    for tramo in sorted(intermedios):
        for k, (x, y) in enumerate(intermedios[tramo], start=1):
            valores = {'SectionID': traducir(_TRAMO, tramo), 'SeqNumber': str(k), 'CoordX': f'{x:.3f}',
                       'CoordY': f'{y:.3f}'}
            filas.append(','.join(valores.get(c, '') for c in columnas))
    return filas


def escribir(ficheros: list[Fichero], destino: Path, mapa: Mapa, *, semilla: int,
             perfil: PerfilEmpresa | None = None, coordenadas: dict[str, tuple[float, float]] | None = None,
             intermedios: dict[str, list[tuple[float, float]]] | None = None,
             largos: dict[str, str] | None = None) -> tuple[dict[str, dict[str, list[str]]], dict[str, list[str]]]:
    """Escribe el trío con la lista cerrada; devuelve las columnas y secciones omitidas, por nombre.

    Con ``coordenadas`` (por NodeID) e ``intermedios`` (por tramo), NODE e INTERMEDIATE NODES salen del trazado
    sintético, no de la red girada; con ``largos`` (por tramo), las longitudes perturbadas (112:RF-13). Sin ellos, la
    red girada en un origen neutro, para el uso local de T2 y T7.
    """
    destino.mkdir(parents=True, exist_ok=True)
    traducir = _traductor(mapa, perfil, frozenset(_tipos_por_codigo(ficheros)))
    coords = _coordenadas(ficheros, semilla)
    omitidas: dict[str, dict[str, list[str]]] = {}
    secciones_fuera: dict[str, list[str]] = {}
    columnas_formato: dict[str, list[str]] = {}
    intermedios_hechos = False
    for f in ficheros:
        lineas: list[str] = []
        fuera = omitidas.setdefault(f.nombre, {})
        seccion_fuera = False
        seccion = ''
        for e in f.entradas:
            if e[0] == 'seccion':
                seccion = e[1]
                seccion_fuera = seccion not in SECCIONES[f.nombre]
                if seccion_fuera:
                    if seccion not in secciones_fuera.setdefault(f.nombre, []):
                        secciones_fuera[f.nombre].append(seccion)
                    continue
                lineas.append(f'[{seccion}]')
                continue
            if seccion_fuera:
                continue
            if e[0] == 'formato':
                clases = _columnas_de(f.nombre, seccion, e[1]) or {}
                for c in e[2]:
                    if c not in clases and c not in fuera.setdefault(seccion, []):
                        fuera[seccion].append(c)
                columnas_formato[seccion] = [c for c in e[2] if c in clases]
                lineas.append(f'{e[1]}=' + ','.join(columnas_formato[seccion]))
                continue
            if e[0] == 'feeder':
                fila = dict(zip(e[1], e[2]))
                for c in e[1][:len(e[2])]:
                    if c not in COLUMNAS_FEEDER and c not in fuera.setdefault(seccion, []):
                        fuera[seccion].append(c)
                lineas.append('FEEDER=' + ','.join(traducir(COLUMNAS_FEEDER[c], fila.get(c, ''))
                                                   for c in e[1] if c in COLUMNAS_FEEDER))
                continue
            clases = SECCIONES[f.nombre][seccion]
            fila = e[2]
            if coordenadas is not None and seccion == 'INTERMEDIATE NODES':
                if not intermedios_hechos:      # las del trazado, una vez, en lugar de las originales
                    intermedios_hechos = True
                    lineas.extend(_filas_intermedias(columnas_formato.get(seccion) or list(clases),
                                                     intermedios or {}, traducir))
                continue
            salida = []
            for col in fila:
                clase = clases.get(col)
                if clase is None:
                    continue
                valor = fila[col]
                if isinstance(clase, tuple):
                    valor = traducir(clase, valor)
                elif clase in (_X, _Y) and coordenadas is not None and seccion == 'NODE':
                    punto = coordenadas.get(fila.get('NodeID', ''))
                    valor = '' if punto is None else f'{punto[0] if clase == _X else punto[1]:.3f}'
                elif clase in (_X, _Y):
                    if valor:
                        cx = next(c for c, k in clases.items() if k == _X)
                        cy = next(c for c, k in clases.items() if k == _Y)
                        if fila.get(cx) and fila.get(cy):
                            nuevo = coords[(float(fila[cx]), float(fila[cy]))]
                            valor = f'{nuevo[0] if clase == _X else nuevo[1]:.3f}'
                        else:
                            valor = ''
                elif clase == _NUM:
                    if largos is not None and col == 'Length' and seccion in SECCIONES_LARGO:
                        valor = largos.get(fila.get('SectionID', ''), valor)
                    if not _numero(valor):
                        raise ColumnaNoAdmitida(f'{f.nombre} [{seccion}] {col}: un valor que no es un número')
                elif not _CODIGO_CORTO.match(valor):
                    raise ColumnaNoAdmitida(f'{f.nombre} [{seccion}] {col}: un valor que no es un código corto')
                salida.append(valor)
            lineas.append(','.join(salida))
        if f.nombre == 'RED.txt' and coordenadas is not None and intermedios and not intermedios_hechos:
            intermedios_hechos = True
            lineas += ['[INTERMEDIATE NODES]', 'FORMAT_INTERMEDIATENODE=SectionID,SeqNumber,CoordX,CoordY',
                       *_filas_intermedias(['SectionID', 'SeqNumber', 'CoordX', 'CoordY'], intermedios, traducir)]
        (destino / f.nombre).write_text('\n'.join(lineas) + '\n', encoding='utf-8', newline='\n')
    return ({n: {s: cols for s, cols in d.items() if cols} for n, d in omitidas.items()},
            secciones_fuera)


def perfil_neutro(perfil: PerfilEmpresa | None) -> PerfilEmpresa:
    """El perfil del benchmark: los prefijos traducidos a los seudónimos y nada que sitúe a la empresa.

    Sin CRS (las coordenadas están en un origen neutro) y sin escala del diagrama; las SED de medición, si el perfil
    las tenía, son las de tipo «medidor» del mapa, que tienen forma fija: ``BM<n>``.
    """
    medicion = r'^BM\d+$' if perfil is not None and perfil.patron_sed_medicion else None
    return PerfilEmpresa(nombre='benchmark', patron_sed_medicion=medicion, forma_alimentador=r'^BA\d+$')


NOMBRES = ('RED.txt', 'CARGA.txt', 'BD_Equipo.txt')


def anonimizar_red(red: Path | str, carga: Path | str, equipo: Path | str, destino: Path | str, *, semilla: int,
                   perfil: PerfilEmpresa | None = None, mapa: Mapa | None = None) -> InformeRed:
    """Escribe en ``destino`` el trío anonimizado de la red. Con ``mapa`` ya congelado, usa ese (series y red juntas)."""
    ficheros = [leer_fichero(r, n) for r, n in zip((red, carga, equipo), NOMBRES)]
    resolver_tipos(ficheros)
    if mapa is None:
        mapa = Mapa(semilla)
        registrar(ficheros, mapa, perfil)
        mapa.congelar()
    omitidas, fuera = escribir(ficheros, Path(destino), mapa, semilla=semilla, perfil=perfil)
    return InformeRed(list(NOMBRES), omitidas, fuera, perfil_neutro(perfil), mapa)
