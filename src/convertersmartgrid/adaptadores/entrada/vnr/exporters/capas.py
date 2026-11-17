"""El modelo canónico de VNR-GIS escrito como paquete de capas (GeoPackage), sin un segundo ETL (080:RF-55).

Una copia ``.bak`` de VNR-GIS solo se lee restaurada en SQL Server. Este módulo la deja en el
formato de archivo que lee la vía de capas: lee la base YA restaurada con el lector canónico de la
vía SQL (:func:`leer_base_restaurada`, el mismo ``leer_datos`` + ``modelo_canonico``) y SOLO
serializa el canónico. No hay reglas propias de estado, medio ni tipo: se escriben los valores de la
fuente tal como los guarda el canónico (``source_status``, ``source_network_type``) con los nombres
de campo que la vía de capas resuelve con ``resolve_alias`` (``ESTADOVNR``, ``CODTIPORED``…), y las
reglas las aplica la vía de capas al leerlos. :func:`comparar_tramos` comprueba que SQL → capas →
canónico da el mismo canónico.

Nunca restaura una copia: SQL Server es compartido. La base tiene que estar ya en línea.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from convertersmartgrid.adaptadores.entrada.vnr.models import CanonicalModel
from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import SIN_REGLA_BT

#: Capa de tramos: va la primera, porque la vía de capas lee la capa por defecto del GeoPackage.
CAPA_TRAMOS = 'Tramo_MT'
#: 080:RF-55: capa de tramos BT.
CAPA_TRAMOS_BT = 'Tramo_BT'


def leer_base_restaurada(base_red: str, base_parametros: str | None = None, *,
                         servidor: str | None = None, salidas=None, con_bt: bool = True
                         ) -> tuple[CanonicalModel, list[dict]]:
    """El modelo canónico de una base VNR-GIS ya en línea, con el lector de la vía SQL; sin restaurar.

    Solo lee (SELECT). Si la base no está ``ONLINE`` en el servidor, falla sin tocar nada. Con
    ``con_bt`` (por omisión) lee también la red BT, para que el paquete de capas lleve todos los objetos;
    con ``salidas``, solo la de esas salidas, por bloques (080:RF-60).
    """
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.sqlserver_vnr import (
        SERVIDOR, conectar, leer_datos, modelo_canonico)

    servidor = servidor or SERVIDOR
    _comprobar_en_linea(servidor, base_red, base_parametros)
    # 080:RF-60: las mismas salidas para la lectura (de la red BT se guarda solo la de las pedidas) y para el modelo.
    salidas = None if salidas is None else list(salidas)
    cn_red = conectar(servidor, base_red, autocommit=False)
    cn_param = conectar(servidor, base_parametros, autocommit=False) if base_parametros else None
    try:
        datos = leer_datos(cn_red, cn_param, con_bt=con_bt, salidas=salidas)
    finally:
        cn_red.close()
        if cn_param is not None:
            cn_param.close()
    return modelo_canonico(datos, salidas)


def _comprobar_en_linea(servidor: str, base_red: str, base_parametros: str | None) -> None:
    """Que las bases estén ``ONLINE`` en el servidor; si no, falla sin tocar nada (no se restaura desde aquí)."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.sqlserver_vnr import conectar

    maestro = conectar(servidor)
    try:
        cur = maestro.cursor()
        for base in (base_red, base_parametros):
            if not base:
                continue
            cur.execute('SELECT state_desc FROM sys.databases WHERE name = ?', base)
            fila = cur.fetchone()
            if fila is None or str(fila[0]).upper() != 'ONLINE':
                raise ValueError(f'La base {base!r} no está en línea en {servidor}: no se restaura nada '
                                 'desde aquí (SQL Server es compartido).')
    finally:
        maestro.close()


def _crs(modelo: CanonicalModel) -> str | None:
    meta = modelo.metadata or {}
    return meta.get('working_crs') or meta.get('source_crs')


def _fila_de_tramo(tramo, empresa: str) -> dict[str, Any]:
    """Los atributos de un tramo con los nombres de la vía de capas; los valores, los del canónico."""
    return {
        'CODTRAMOMT': tramo.section_id,
        'CODSALIDAMT': tramo.feeder_id,
        # 080:RF-55: los nodos de la fuente; sin ellos, la vía de capas uniría la red por cercanía.
        'CODNODOMT_INI': tramo.from_node,
        'CODNODOMT_FIN': tramo.to_node,
        'CODNORMA': tramo.conductor_code,
        'LONGITUD': tramo.length_m,
        'ESTADOVNR': tramo.source_status,
        'CODTIPORED': tramo.source_network_type,
        'FASES': tramo.phases,
        'TENSION_KV': tramo.nominal_kv,
        'CODEMP': empresa,
    }


def _fila_de_tramo_bt(tramo) -> dict[str, Any]:
    """080:RF-55: los atributos de un tramo BT con los nombres que lee la vía de capas; los valores, los del canónico."""
    return {
        'CODTRAMOBT': tramo.section_id,
        'CODSALIDABT': tramo.bt_feeder_id,
        'CODSED': tramo.sed_id,
        'CODSALIDAMT': tramo.feeder_id,
        'CODTRAMOBTPADRE': tramo.parent_id,
        'CODNORMA': tramo.conductor_code,
        'LONGITUD': tramo.length_m,
        'ESTADOVNR': tramo.source_status,
        'CODTIPORED': tramo.source_network_type,
    }


def capas_del_canonico(modelo: CanonicalModel) -> dict[str, tuple[list[dict], list]]:
    """``{capa: (atributos, geometrías)}`` del canónico, sin reglas: tramos MT y BT, nodos, SED y equipos."""
    return dict(capas_una_a_una(modelo))


def capas_una_a_una(modelo: CanonicalModel) -> Iterator[tuple[str, tuple[list[dict], list]]]:
    """080:RF-60 (MEM-BT v2): las capas de :func:`capas_del_canonico`, en el mismo orden, armadas de una en una: quien
    escribe cada una antes de pedir la siguiente no tiene todas a la vez en memoria."""
    from shapely.geometry import LineString, Point

    empresa = _empresa(modelo.metadata)
    nodos = {n.node_id: n for n in modelo.nodes}
    tramos = ([], [])
    for tramo in modelo.sections:
        puntos = _puntos_del_tramo(tramo)
        if puntos is None:
            a, b = nodos.get(tramo.from_node), nodos.get(tramo.to_node)
            if a is None or b is None or None in (a.x, a.y, b.x, b.y):
                continue
            puntos = [(a.x, a.y), (b.x, b.y)]
        tramos[0].append(_fila_de_tramo(tramo, empresa))
        tramos[1].append(LineString(puntos))
    yield CAPA_TRAMOS, tramos
    del tramos
    nodo = ([], [])
    for n in modelo.nodes:
        if n.x is None or n.y is None:
            continue
        nodo[0].append(_fila_de_nodo(n))
        nodo[1].append(Point(n.x, n.y))
    yield 'Nodo_MT', nodo
    del nodo
    sed = ([], [])
    for carga in modelo.loads:
        n = nodos.get(carga.connection_node)
        if n is None or n.x is None or n.y is None:
            continue
        sed[0].append(_fila_de_sed(carga))
        sed[1].append(Point(n.x, n.y))
    yield 'Sed', sed
    del sed
    equipo = ([], [])
    for _orden, e, fila in _equipos_del_canonico(modelo):
        n = nodos.get(e.connection_node)
        if n is None or n.x is None or n.y is None:
            continue
        equipo[0].append(fila)
        equipo[1].append(Point(n.x, n.y))
    yield 'Equipo_MT', equipo
    del equipo
    yield CAPA_TRAMOS_BT, capa_de_tramos_bt(modelo.sections_bt)


def _empresa(metadata: dict | None) -> str:
    return str((metadata or {}).get('company') or '')


def _puntos_del_tramo(tramo) -> list[tuple] | None:
    """Los vértices de un tramo MT, o ``None`` si tiene menos de dos (se dibuja entonces entre sus nodos)."""
    puntos = [tuple(p) for p in (tramo.geometry or [])]
    return puntos if len(puntos) >= 2 else None


def _fila_de_nodo(n) -> dict[str, Any]:
    return {'CODNODOMT': n.node_id, 'TENSION_KV': n.nominal_kv, 'FASES': n.phases, 'CAPA_FUENTE': n.source_layer}


def _fila_de_sed(carga) -> dict[str, Any]:
    return {'CODSED': carga.load_id, 'ETIQUETA': carga.etiqueta, 'CODNODOMT': carga.connection_node,
            'ALIMENTADOR': carga.feeder_id, 'KW': carga.kw, 'KVAR': carga.kvar,
            'POTINSTALADA': carga.connected_kva, 'FASES': carga.phases,
            'CAPA_FUENTE': carga.source_layer}


def _equipos_del_canonico(modelo: CanonicalModel) -> Iterator[tuple[int, Any, dict[str, Any]]]:
    """``(orden, equipo, fila)`` de la capa de equipos: las maniobras, después los bancos y después los reguladores."""
    for orden, (tipo, lista, campo) in enumerate((('MANIOBRA', modelo.switches, 'switch_id'),
                                                  ('BANCO', modelo.capacitors, 'capacitor_id'),
                                                  ('REGULADOR', modelo.regulators, 'regulator_id'))):
        for e in lista:
            yield orden, e, {'CODEQP': getattr(e, campo), 'TIPO': tipo, 'CODNODOMT': e.connection_node,
                             'TRAMO': getattr(e, 'section_id', ''), 'ON_OFF': getattr(e, 'on_off', None),
                             'KVAR': getattr(e, 'kvar', None), 'ESTADO': getattr(e, 'status', ''),
                             'CAPA_FUENTE': e.source_layer}


def capa_de_tramos_bt(secciones: Iterable) -> tuple[list[dict], list]:
    """080:RF-55: ``(atributos, geometrías)`` de la capa de tramos BT; los de menos de dos vértices no se dibujan."""
    from shapely.geometry import LineString

    tramos_bt = ([], [])
    for tramo in secciones:
        puntos = [tuple(p) for p in (tramo.geometry or [])]
        if len(puntos) < 2:
            continue
        tramos_bt[0].append(_fila_de_tramo_bt(tramo))
        tramos_bt[1].append(LineString(puntos))
    return tramos_bt


#: 080:RF-60 (MEM-BT v2): las columnas de la capa de tramos BT, en el orden de :func:`_fila_de_tramo_bt`; la longitud es
#: un número y las demás, textos.
COLUMNAS_TRAMO_BT = ('CODTRAMOBT', 'CODSALIDABT', 'CODSED', 'CODSALIDAMT', 'CODTRAMOBTPADRE', 'CODNORMA', 'LONGITUD',
                     'ESTADOVNR', 'CODTIPORED')


def _arrow():
    """``(pyarrow, shapely, pyogrio.write_arrow)``, o ``None`` si falta alguno (pyarrow no va en todos los extras)."""
    try:
        import pyarrow
        import shapely
        from pyogrio import write_arrow
    except ImportError:
        return None
    return pyarrow, shapely, write_arrow


def _escribir_tramos_bt_en_flujo(stage: Path, piezas: Iterable[list], crs: str | None) -> tuple[int, int, str]:
    """080:RF-60 (MEM-BT v2): la capa de tramos BT escrita pieza a pieza; da ``(tramos, escrituras, cómo)``.

    Con pyarrow, en UNA escritura (``pyogrio.write_arrow``) que va pidiendo las piezas como lotes de Arrow: la capa se
    crea una vez y su índice espacial se arma al cerrarla, como con :func:`exportar_canonico_a_capas`, y en memoria hay
    una pieza. Sin pyarrow (no va en todos los extras), cada pieza se añade a la capa (``mode='a'``): el mismo
    GeoPackage, más despacio, porque cada tramo añadido actualiza el índice espacial. Sin tramos, no hay capa (como
    antes)."""
    modulos = _arrow()
    if modulos is None:
        return _anadir_tramos_bt(stage, piezas, crs)
    pa, shapely, write_arrow = modulos
    esquema = pa.schema([(c, pa.float64() if c == 'LONGITUD' else pa.string()) for c in COLUMNAS_TRAMO_BT]
                        + [('geometry', pa.binary())])
    cuenta = [0, 0]

    def lotes():
        for pieza in piezas:
            filas, geometrias = capa_de_tramos_bt(pieza)
            del pieza
            if not filas:
                continue
            columnas = [pa.array([f[c] for f in filas], tipo) for c, tipo in zip(COLUMNAS_TRAMO_BT, esquema.types)]
            columnas.append(pa.array(shapely.to_wkb(geometrias), pa.binary()))
            cuenta[0] += len(filas)
            cuenta[1] += 1
            del filas, geometrias
            yield pa.record_batch(columnas, schema=esquema)

    todos = lotes()
    primero = next(todos, None)
    if primero is None:
        return 0, 0, 'arrow'

    def con_el_primero():
        yield primero
        yield from todos

    write_arrow(pa.RecordBatchReader.from_batches(esquema, con_el_primero()), stage, layer=CAPA_TRAMOS_BT,
                driver='GPKG', geometry_name='geometry', geometry_type='LineString', crs=crs)
    return cuenta[0], 1, 'arrow'


def _juntar(piezas: Iterable[list], tamano: int) -> Iterator[list]:
    """080:RF-60 (MEM-BT v2): las piezas de tramos BT juntadas hasta ``tamano`` tramos, aunque sean de lotes distintos:
    cada escritura tiene un coste fijo. En memoria, como mucho, dos piezas."""
    pendientes: list = []
    for pieza in piezas:
        pendientes.extend(pieza)
        del pieza
        if len(pendientes) >= tamano:
            yield pendientes
            pendientes = []
    if pendientes:
        yield pendientes


def _anadir_tramos_bt(stage: Path, piezas: Iterable[list], crs: str | None) -> tuple[int, int, str]:
    """080:RF-60 (MEM-BT v2): sin pyarrow, cada pieza de tramos BT se añade a la capa (``mode='a'``)."""
    tramos = escrituras = 0
    for pieza in piezas:
        filas, geometrias = capa_de_tramos_bt(pieza)
        del pieza
        if filas:
            _escribir_capa(stage, CAPA_TRAMOS_BT, filas, geometrias, crs, anadir=tramos > 0)
            tramos += len(filas)
            escrituras += 1
        del filas, geometrias
    return tramos, escrituras, 'por añadidos'


def _escribir_capa(stage: Path, capa: str, filas: list[dict], geometrias: list, crs: str | None, *,
                   anadir: bool = False) -> None:
    """Una capa al GeoPackage; con ``anadir``, sus filas van detrás de las que ya tiene (080:RF-60, MEM-BT v2)."""
    import geopandas as gpd

    gdf = gpd.GeoDataFrame(filas, geometry=geometrias, crs=crs)
    if anadir:
        gdf.to_file(stage, layer=capa, driver='GPKG', engine='pyogrio', mode='a')
    else:
        gdf.to_file(stage, layer=capa, driver='GPKG', engine='pyogrio')


def exportar_canonico_a_capas(modelo: CanonicalModel, destino: Path | str) -> Path:
    """Escribe el canónico como GeoPackage en ``destino`` (``.gpkg``), con publicación atómica (001:RF-5)."""
    from convertersmartgrid.runtime_paths import staging_publicacion

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    crs = _crs(modelo)
    with staging_publicacion(destino) as stage:
        stage = stage.with_suffix('.gpkg')
        for capa, (filas, geometrias) in capas_una_a_una(modelo):
            if filas:
                _escribir_capa(stage, capa, filas, geometrias, crs)
            del filas, geometrias
        os.replace(stage, destino)
    return destino


@dataclass
class ExportacionEnFlujo:
    """080:RF-60 (MEM-BT v2): lo que da :func:`exportar_base_a_capas_en_flujo`."""

    destino: Path
    #: Lo anotado, en el orden de ``modelo_canonico``: los avisos de memoria y disco, los de la red MT y los de la BT.
    avisos: list[dict]
    #: :func:`resumen_de_tramos` del canónico MT (el que imprime el CLI).
    resumen: dict[str, Any]
    #: Tablas o vistas que el motor no pudo leer, con su motivo.
    ilegibles: list[dict] = field(default_factory=list)
    tramos_bt: int = 0
    #: Lotes de salidas MT en que se armó la red BT, y escrituras de su capa (una con pyarrow).
    lotes: int = 0
    escrituras: int = 0
    #: Cómo se escribió la capa BT: ``'arrow'`` (una escritura en flujo) o ``'por añadidos'`` (sin pyarrow).
    escritura: str = ''
    #: Los metadatos del canónico, con los valores BT sin regla (``valores_sin_regla_bt``).
    metadata: dict = field(default_factory=dict)
    #: El canónico MT (sin la red BT), solo si se pide con ``con_modelo_mt``.
    modelo_mt: CanonicalModel | None = None
    #: 080:RF-60 (MEM-MT): lotes de salidas MT en que se armó el canónico MT.
    lotes_mt: int = 0


#: 080:RF-60 (MEM-MT): las capas de la red MT, en el orden en que se escriben, con su tipo de geometría.
CAPAS_MT: tuple[tuple[str, str], ...] = ((CAPA_TRAMOS, 'LineString'), ('Nodo_MT', 'Point'), ('Sed', 'Point'),
                                         ('Equipo_MT', 'Point'))


def _tipo_de_columna(tipos: set[type]) -> str:
    """080:RF-60 (MEM-MT): el tipo de una columna de la capa por los tipos de Python de TODOS sus valores, como lo
    deduce la escritura de antes (``GeoDataFrame`` + pyogrio): solo enteros → ``int64`` (INTEGER); números con algún
    real o algún ``None`` → ``float64`` (REAL); solo booleanos → ``bool`` (BOOLEAN); lo demás (textos, mezclas o
    todo ``None``) → ``string`` (TEXT, con ``str`` de lo que no sea texto)."""
    sin_none = tipos - {type(None)}
    if sin_none == {bool}:
        return 'bool' if type(None) not in tipos else 'string'
    if sin_none and sin_none <= {int, float}:
        return 'int64' if tipos == {int} else 'float64'
    return 'string'


def _wkb_de_lineas(lineas: list[list[tuple]]) -> list[bytes]:
    """El WKB de cada línea (sus vértices), armadas de una vez (``shapely.linestrings`` con índices): las mismas
    coordenadas que ``LineString`` una a una, sin un objeto de Python por tramo. Con vértices que no sean (x, y), una a
    una."""
    import numpy as np
    import shapely

    if not lineas:
        return []
    if any(len(p) != 2 for puntos in lineas for p in puntos):
        from shapely.geometry import LineString

        return list(shapely.to_wkb([LineString(puntos) for puntos in lineas]))
    coordenadas = np.array([p for puntos in lineas for p in puntos], dtype=float)
    indices = np.repeat(np.arange(len(lineas)), [len(puntos) for puntos in lineas])
    return list(shapely.to_wkb(shapely.linestrings(coordenadas, indices=indices)))


class _CapasMtEnDisco:
    """080:RF-60 (MEM-MT): las filas de las capas MT, lote a lote, en el SQLite temporal, para escribir después cada
    capa de una vez y en el mismo orden que :func:`capas_una_a_una` con el canónico entero.

    De cada lote se guardan sus filas (con :func:`_fila_de_tramo`, :func:`_fila_de_nodo`, :func:`_fila_de_sed` y
    :func:`_equipos_del_canonico`, las de la vía de antes) y la posición de sus nodos. La geometría de una SED, de un
    equipo o de un tramo sin vértices sale al escribir de la posición de su nodo, la del último nodo con ese código,
    como el diccionario de :func:`capas_una_a_una`; lo que no tiene nodo con posición no se escribe. El tipo de cada
    columna se deduce de todos los valores que se escriben (:func:`_tipo_de_columna`)."""

    def __init__(self, cn):
        self.cn = cn
        self.columnas: dict[str, list[str]] = {}
        self.tipos: dict[str, list[set[type]]] = {}
        self._seq = 0
        cn.executescript('''
            CREATE TABLE capa_nodo_xy (nodo TEXT PRIMARY KEY, x REAL, y REAL);
        ''')

    def _tabla(self, capa: str, fila: dict, extra: str) -> None:
        if capa not in self.columnas:
            self.columnas[capa] = list(fila)
            self.tipos[capa] = [set() for _c in fila]
            valores = ', '.join(f'v{i}' for i in range(len(fila)))
            self.cn.execute(f'CREATE TABLE "capa_{capa}" (seq INTEGER PRIMARY KEY, orden INTEGER NOT NULL, {extra}, '
                            f'{valores})')

    def _guardar(self, capa: str, filas: list[tuple[int, dict, tuple]], extra: tuple[str, ...]) -> None:
        if not filas:
            return
        self._tabla(capa, filas[0][1], ', '.join(extra))
        tipos = self.tipos[capa]
        n = len(self.columnas[capa])
        lineas = []
        for orden, fila, de_mas in filas:
            valores = tuple(fila.values())
            for conjunto, v in zip(tipos, valores):
                conjunto.add(type(v))
            self._seq += 1
            lineas.append((self._seq, orden, *de_mas, *valores))
        marcas = ', '.join('?' * (2 + len(extra) + n))
        self.cn.executemany(f'INSERT INTO "capa_{capa}" VALUES ({marcas})', lineas)

    def agregar(self, modelo: CanonicalModel) -> None:
        """Las filas de las capas MT de un lote del canónico (:meth:`RedMtEnDisco.canonico_por_lotes`)."""
        empresa = _empresa(modelo.metadata)
        tramos = []
        lineas, con_vertices = [], []
        for tramo in modelo.sections:
            puntos = _puntos_del_tramo(tramo)
            if puntos is not None:
                lineas.append(puntos)
                con_vertices.append(len(tramos))
            tramos.append([0, _fila_de_tramo(tramo, empresa), [None, tramo.from_node, tramo.to_node]])
        for i, wkb in zip(con_vertices, _wkb_de_lineas(lineas)):
            tramos[i][2][0] = wkb
        self._guardar(CAPA_TRAMOS, [(o, f, tuple(e)) for o, f, e in tramos], ('geom', 'ini', 'fin'))
        del tramos, lineas
        self._guardar('Nodo_MT', [(0, _fila_de_nodo(n), (n.x, n.y)) for n in modelo.nodes
                                  if n.x is not None and n.y is not None], ('x', 'y'))
        # La posición de cada nodo, también de los que no tienen: el último con su código manda.
        self.cn.executemany('INSERT OR REPLACE INTO capa_nodo_xy (nodo, x, y) VALUES (?, ?, ?)',
                            ((n.node_id, n.x, n.y) for n in modelo.nodes))
        self._guardar('Sed', [(0, _fila_de_sed(c), (c.connection_node,)) for c in modelo.loads], ('nodo',))
        self._guardar('Equipo_MT', [(o, f, (e.connection_node,)) for o, e, f in _equipos_del_canonico(modelo)],
                      ('nodo',))

    def _consulta(self, capa: str) -> tuple[str, str]:
        """``(SELECT de las filas que se escriben, en su orden; condición de las que no)``."""
        valores = ', '.join(f't.v{i}' for i in range(len(self.columnas[capa])))
        tabla = f'"capa_{capa}" t'
        if capa == CAPA_TRAMOS:
            unir = ('LEFT JOIN capa_nodo_xy a ON a.nodo = t.ini LEFT JOIN capa_nodo_xy b ON b.nodo = t.fin')
            entra = ('(t.geom IS NOT NULL OR (a.x IS NOT NULL AND a.y IS NOT NULL AND b.x IS NOT NULL '
                     'AND b.y IS NOT NULL))')
            return (f'SELECT {valores}, t.geom, a.x, a.y, b.x, b.y FROM {tabla} {unir} WHERE {entra} '
                    'ORDER BY t.orden, t.seq', f'FROM {tabla} {unir} WHERE NOT {entra}')
        if capa == 'Nodo_MT':
            return f'SELECT {valores}, t.x, t.y FROM {tabla} ORDER BY t.orden, t.seq', f'FROM {tabla} WHERE 0'
        unir = 'LEFT JOIN capa_nodo_xy n ON n.nodo = t.nodo'
        entra = '(n.x IS NOT NULL AND n.y IS NOT NULL)'
        return (f'SELECT {valores}, n.x, n.y FROM {tabla} {unir} WHERE {entra} ORDER BY t.orden, t.seq',
                f'FROM {tabla} {unir} WHERE NOT {entra}')

    def _bloques(self, capa: str) -> Iterator[tuple[list[tuple], list[bytes]]]:
        """Las filas que se escriben de ``capa`` y sus geometrías (WKB), por bloques de ``FILAS_POR_BLOQUE``."""
        import shapely

        from convertersmartgrid.adaptadores.entrada.vnr.connectors.sqlserver_vnr import FILAS_POR_BLOQUE

        n = len(self.columnas[capa])
        cur = self.cn.execute(self._consulta(capa)[0])
        while True:
            bloque = cur.fetchmany(FILAS_POR_BLOQUE)
            if not bloque:
                return
            filas = [f[:n] for f in bloque]
            if capa == CAPA_TRAMOS:
                geometrias = [f[n] if f[n] is not None else
                              shapely.to_wkb(shapely.linestrings([(f[n + 1], f[n + 2]), (f[n + 3], f[n + 4])]))
                              for f in bloque]
            else:
                geometrias = list(shapely.to_wkb(shapely.points([(f[n], f[n + 1]) for f in bloque])))
            yield filas, geometrias

    def _tipos_de(self, capa: str) -> list[str]:
        """El tipo de cada columna: con los valores guardados si se escriben todas las filas; si no, con los que se
        escriben (otra pasada, solo cuando alguna fila se queda fuera)."""
        fuera = self.cn.execute(f'SELECT COUNT(*) {self._consulta(capa)[1]}').fetchone()[0]
        tipos = self.tipos[capa]
        if fuera:
            tipos = [set() for _c in tipos]
            for filas, _g in self._bloques(capa):
                for fila in filas:
                    for conjunto, v in zip(tipos, fila):
                        conjunto.add(type(v))
        return [_tipo_de_columna(t) for t in tipos]

    def escribir(self, stage: Path, crs: str | None) -> dict[str, int]:
        """Cada capa MT en una escritura, en el orden de :data:`CAPAS_MT`; da sus filas. Sin filas, no hay capa."""
        escritas = {}
        for capa, geometria in CAPAS_MT:
            if capa not in self.columnas:
                continue
            tipos = self._tipos_de(capa)
            escritas[capa] = _escribir_capa_en_flujo(stage, capa, self.columnas[capa], tipos, self._bloques(capa),
                                                     geometria, crs)
        return escritas


def _columna_arrow(pa, valores: list, tipo: str):
    if tipo == 'string':
        valores = [v if v is None or isinstance(v, str) else str(v) for v in valores]
        return pa.array(valores, pa.string())
    return pa.array(valores, {'int64': pa.int64(), 'float64': pa.float64(), 'bool': pa.bool_()}[tipo])


def _escribir_capa_en_flujo(stage: Path, capa: str, columnas: list[str], tipos: list[str],
                            bloques: Iterable[tuple[list[tuple], list[bytes]]], geometria: str, crs: str | None) -> int:
    """080:RF-60 (MEM-MT): una capa escrita por bloques de filas ``(valores, WKB)`` con los ``tipos`` de sus columnas;
    da sus filas. Con pyarrow, en UNA escritura (``pyogrio.write_arrow``): la capa se crea una vez y su índice espacial
    se arma al cerrarla. Sin pyarrow, el primer bloque crea la capa y los demás se añaden (``mode='a'``), con las
    columnas ya en su tipo: el mismo GeoPackage, más despacio."""
    modulos = _arrow()
    cuenta = [0]
    if modulos is None:
        import geopandas as gpd
        import pandas as pd
        import shapely

        for filas, geometrias in bloques:
            datos = {}
            for i, (c, tipo) in enumerate(zip(columnas, tipos)):
                valores = [f[i] for f in filas]
                if tipo == 'string':
                    datos[c] = pd.Series([v if v is None or isinstance(v, str) else str(v) for v in valores],
                                         dtype=object)
                else:
                    datos[c] = pd.Series(valores, dtype=tipo)
            gdf = gpd.GeoDataFrame(datos, geometry=shapely.from_wkb(geometrias), crs=crs)
            if cuenta[0]:
                gdf.to_file(stage, layer=capa, driver='GPKG', engine='pyogrio', mode='a')
            else:
                gdf.to_file(stage, layer=capa, driver='GPKG', engine='pyogrio')
            cuenta[0] += len(filas)
            del gdf, datos
        return cuenta[0]
    pa, _shapely, write_arrow = modulos
    tipos_arrow = {'string': pa.string(), 'int64': pa.int64(), 'float64': pa.float64(), 'bool': pa.bool_()}
    esquema = pa.schema([(c, tipos_arrow[t]) for c, t in zip(columnas, tipos)] + [('geometry', pa.binary())])

    def lotes():
        for filas, geometrias in bloques:
            arrays = [_columna_arrow(pa, [f[i] for f in filas], t) for i, t in enumerate(tipos)]
            arrays.append(pa.array(geometrias, pa.binary()))
            cuenta[0] += len(filas)
            yield pa.record_batch(arrays, schema=esquema)

    write_arrow(pa.RecordBatchReader.from_batches(esquema, lotes()), stage, layer=capa, driver='GPKG',
                geometry_name='geometry', geometry_type=geometria, crs=crs)
    return cuenta[0]


class _CuentaDeTramos:
    """080:RF-60 (MEM-MT): :func:`resumen_de_tramos` sumado lote a lote."""

    def __init__(self):
        self.tramos = self.fuera = 0
        self.medio, self.estado, self.tipo_red = Counter(), Counter(), Counter()

    def sumar(self, secciones: Iterable) -> None:
        for t in secciones:
            self.tramos += 1
            self.fuera += t.status == 'out_of_service'
            self.medio[{True: 'aereo', False: 'cable', None: 'sin_dato'}[t.overhead]] += 1
            self.estado[t.source_status] += 1
            self.tipo_red[t.source_network_type] += 1

    def resumen(self, metadata: dict | None) -> dict[str, Any]:
        return {'tramos': self.tramos, 'fuera_de_servicio': self.fuera, 'medio': dict(sorted(self.medio.items())),
                'estado_fuente': dict(sorted(self.estado.items())),
                'tipo_red_fuente': dict(sorted(self.tipo_red.items())),
                'valores_sin_regla': (metadata or {}).get('valores_sin_regla') or {}}


def _sumar_al_modelo(total: CanonicalModel, lote: CanonicalModel) -> None:
    """080:RF-60 (MEM-MT): las listas de un lote del canónico, detrás de las del total (solo con ``con_modelo_mt``)."""
    import dataclasses

    for campo in dataclasses.fields(total):
        if isinstance(getattr(total, campo.name), list):
            getattr(total, campo.name).extend(getattr(lote, campo.name))


def exportar_base_a_capas_en_flujo(base_red: str, base_parametros: str | None, destino: Path | str, *,
                                   servidor: str | None = None, lote_salidas: int | None = None,
                                   mostrar: Callable[[str], None] | None = None,
                                   con_modelo_mt: bool = False) -> ExportacionEnFlujo:
    """080:RF-60 (MEM-BT v2, MEM-MT): una base VNR-GIS ya en línea → GeoPackage en ``destino``, EN FLUJO.

    Da el mismo GeoPackage que :func:`exportar_copia_a_capas` con todas las salidas (mismas capas, filas y atributos),
    sin tener nunca el canónico entero en memoria, ni el de la red MT ni el de la BT:

    1. la red MT se lee una vez por tabla y por bloques, y sus tablas grandes se vuelcan a un SQLite temporal junto al
       GeoPackage (:func:`~convertersmartgrid.adaptadores.entrada.vnr.connectors.sqlserver_vnr.volcar_red_mt`);
    2. la red BT, igual, al mismo SQLite (``volcar_red_bt``), con su estimación de memoria y de disco antes de leerla;
    3. el canónico MT se arma por lotes de ``lote_salidas`` salidas (``LOTE_SALIDAS`` por omisión), con la misma función
       por salida que ``modelo_canonico``; las filas de sus capas se guardan en el SQLite y cada capa MT se escribe
       después en una escritura;
    4. la capa de tramos BT se arma y se escribe por lotes de ``lote_salidas`` salidas MT y en piezas de
       ``TRAMOS_BT_POR_PIEZA`` tramos como mucho; cada pieza se libera antes de la siguiente.

    En memoria quedan las tablas pequeñas (empresa, salidas, SET, sistemas, normas y tensiones), un lote de salidas MT
    con sus filas y su canónico, un bloque de filas de una capa y una pieza de tramos BT. ``mostrar`` recibe las líneas
    de la estimación (el CLI las imprime). ``con_modelo_mt`` devuelve también el canónico MT entero, juntando los lotes,
    para comparar las vías: ese sí crece con la empresa.
    """
    import gc

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv
    from convertersmartgrid.runtime_paths import staging_publicacion

    lote_salidas = sv.LOTE_SALIDAS if lote_salidas is None else int(lote_salidas)
    if lote_salidas < 1:
        raise ValueError(f'El lote de salidas tiene que ser de 1 o más (se pidió {lote_salidas}).')
    servidor = servidor or sv.SERVIDOR
    _comprobar_en_linea(servidor, base_red, base_parametros)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cn_red = sv.conectar(servidor, base_red, autocommit=False)
    cn_param = None
    try:
        cn_param = sv.conectar(servidor, base_parametros, autocommit=False) if base_parametros else None
        with staging_publicacion(destino) as stage:
            stage = stage.with_suffix('.gpkg')
            red_mt = sv.volcar_red_mt(cn_red, cn_param, stage.with_name(stage.stem + '_red.sqlite'))
            try:
                datos = red_mt.datos
                red_bt = sv.volcar_red_bt(cn_red, datos, red_mt.ruta, mostrar=mostrar, seds=red_mt.seds(),
                                          cn=red_mt.cn)
                cn_red.close()
                if cn_param is not None:
                    cn_param.close()
                cn_red = cn_param = None
                capas_mt = _CapasMtEnDisco(red_mt.cn)
                cuenta = _CuentaDeTramos()
                # Las salidas MT que entraron al canónico, por su código de VNR-GIS (como en ``_tramos_bt``).
                cargadas: set[str] = set()
                modelo_mt = CanonicalModel() if con_modelo_mt else None
                for modelo in red_mt.canonico_por_lotes(lote_salidas=lote_salidas):
                    capas_mt.agregar(modelo)
                    cuenta.sumar(modelo.sections)
                    cargadas |= {f.source_sid for f in modelo.sources}
                    if modelo_mt is not None:
                        _sumar_al_modelo(modelo_mt, modelo)
                    del modelo
                metadata = red_mt.metadata
                avisos = red_mt.avisos
                codigo_de = red_mt.codigo_de
                ilegibles = list(datos.ilegibles)
                if modelo_mt is not None:
                    modelo_mt.metadata = metadata
                    modelo_mt.conductor_types = list(red_mt.conductores)
                crs = metadata.get('working_crs') or metadata.get('source_crs')
                capas_mt.escribir(stage, crs)
                red_mt.cn.commit()
                resumen = cuenta.resumen(metadata)
                lotes_mt = red_mt.lotes
                gc.collect()
                piezas = _juntar(red_bt.secciones(cargadas, codigo_de, metadata, lote_salidas=lote_salidas),
                                 sv.TRAMOS_BT_POR_PIEZA)
                tramos_bt, escrituras, como = _escribir_tramos_bt_en_flujo(stage, piezas, crs)
                avisos.extend(red_bt.avisos())
                red_bt.cerrar()
            finally:
                red_mt.cerrar()
            os.replace(stage, destino)
    finally:
        for cn in (cn_red, cn_param):
            if cn is not None:
                cn.close()
    lotes = -(-len(cargadas) // lote_salidas)
    return ExportacionEnFlujo(destino=destino, avisos=avisos, resumen=resumen, ilegibles=ilegibles,
                              tramos_bt=tramos_bt, lotes=lotes, escrituras=escrituras, escritura=como,
                              metadata=metadata, modelo_mt=modelo_mt, lotes_mt=lotes_mt)


def exportar_copia_a_capas(base_red: str, destino: Path | str, *, base_parametros: str | None = None,
                           servidor: str | None = None, salidas=None, con_bt: bool = True
                           ) -> tuple[Path, CanonicalModel]:
    """Una base VNR-GIS ya restaurada → paquete de capas ``destino`` (080:RF-55). Devuelve el canónico leído."""
    modelo, _avisos = leer_base_restaurada(base_red, base_parametros, servidor=servidor, salidas=salidas,
                                           con_bt=con_bt)
    return exportar_canonico_a_capas(modelo, destino), modelo


def resumen_de_tramos(modelo: CanonicalModel) -> dict[str, Any]:
    """Lo que se compara entre vías: tramos, estado, medio, valores sin regla."""
    return {
        'tramos': len(modelo.sections),
        'fuera_de_servicio': sum(t.status == 'out_of_service' for t in modelo.sections),
        'medio': dict(sorted(Counter({True: 'aereo', False: 'cable', None: 'sin_dato'}[t.overhead]
                                     for t in modelo.sections).items())),
        'estado_fuente': dict(sorted(Counter(t.source_status for t in modelo.sections).items())),
        'tipo_red_fuente': dict(sorted(Counter(t.source_network_type for t in modelo.sections).items())),
        'valores_sin_regla': (modelo.metadata or {}).get('valores_sin_regla') or {},
    }


def comparar_tramos(origen: CanonicalModel, leido: CanonicalModel, *, tolerancia_m: float = 0.01
                    ) -> dict[str, Any]:
    """Las diferencias, tramo a tramo, entre el canónico de la vía SQL y el de la vía de capas.

    Vacío si son el mismo canónico en lo que la vía de capas lee: alimentador, norma, estado, medio,
    valores de la fuente y longitud (a ``tolerancia_m``), más los valores sin regla.
    """
    a = {t.section_id: t for t in origen.sections}
    b = {t.section_id: t for t in leido.sections}
    difs: dict[str, Any] = {}
    if set(a) != set(b):
        difs['solo_en_sql'] = sorted(set(a) - set(b))[:20]
        difs['solo_en_capas'] = sorted(set(b) - set(a))[:20]
    distintos: list[dict[str, Any]] = []
    for sid in sorted(set(a) & set(b)):
        x, y = a[sid], b[sid]
        for campo in ('feeder_id', 'conductor_code', 'status', 'overhead', 'source_status',
                      'source_network_type'):
            if getattr(x, campo) != getattr(y, campo):
                distintos.append({'tramo': sid, 'campo': campo, 'sql': getattr(x, campo),
                                  'capas': getattr(y, campo)})
        if x.length_m is not None and y.length_m is not None and abs(x.length_m - y.length_m) > tolerancia_m:
            distintos.append({'tramo': sid, 'campo': 'length_m', 'sql': x.length_m, 'capas': y.length_m})
    if distintos:
        difs['distintos'] = len(distintos)
        difs['ejemplos'] = distintos[:20]
    # Las demás capas del paquete: cada una con todos sus registros (la vía de capas las inventaría).
    leidas = {str(c.get('capa', '')).rsplit(':', 1)[-1]: c.get('registros')
              for c in (leido.metadata or {}).get('capas') or []}
    if leidas:
        esperadas = {capa: len(filas) for capa, (filas, _g) in capas_del_canonico(origen).items() if filas}
        if {k: leidas.get(k) for k in esperadas} != esperadas:
            difs['capas'] = {'canonico': esperadas, 'paquete': leidas}
    sa = (origen.metadata or {}).get('valores_sin_regla') or {}
    sb = (leido.metadata or {}).get('valores_sin_regla') or {}
    if sa != sb:
        difs['valores_sin_regla'] = {'sql': sa, 'capas': sb}
    return difs


#: 080:RF-55: lo que se compara, por objeto, entre la vía SQL y la de capas: ``(objeto, lista, id, campos)``.
OBJETOS_COMPARADOS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ('tramo', 'sections', 'section_id', ('from_node', 'to_node')),
    ('nodo', 'nodes', 'node_id', ('nominal_kv',)),
    ('sed', 'loads', 'load_id', ('connection_node', 'kw', 'kvar', 'connected_kva', 'feeder_id', 'phases',
                                 'etiqueta')),
    ('maniobra', 'switches', 'switch_id', ('connection_node', 'section_id', 'on_off')),
    ('banco', 'capacitors', 'capacitor_id', ('connection_node', 'kvar')),
    ('regulador', 'regulators', 'regulator_id', ('connection_node', 'section_id', 'on_off')),
    ('tramo_bt', 'sections_bt', 'section_id', ('sed_id', 'bt_feeder_id', 'feeder_id', 'parent_id', 'conductor_code',
                                               'length_m', 'status', 'overhead', 'source_status',
                                               'source_network_type')),
)


def _geometria_distinta(a: Any, b: Any, tolerancia_m: float) -> bool:
    """080:RF-55: otro número de vértices, o un vértice a más de ``tolerancia_m``."""
    a, b = list(a or []), list(b or [])
    return len(a) != len(b) or any(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 > tolerancia_m
                                   for p, q in zip(a, b))


def _distinto(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) > 1e-9
    return a != b


def comparar_red(origen: CanonicalModel, leido: CanonicalModel, *, tolerancia_m: float = 0.01) -> dict[str, Any]:
    """080:RF-55: las diferencias entre la vía SQL y la de capas en TODA la red, no solo en los tramos.

    Lo de :func:`comparar_tramos` más los nodos de cada tramo, los nodos (posición a ``tolerancia_m`` y
    tensión), las SED, los equipos y los tramos BT (con su geometría a ``tolerancia_m`` y sus valores sin
    regla). Cada diferencia es ``{'objeto', 'id', 'campo', 'sql', 'capas'}``. Vacío si las dos vías dan el
    mismo canónico.
    """
    de_tramos = comparar_tramos(origen, leido, tolerancia_m=tolerancia_m)
    difs: dict[str, Any] = {k: v for k, v in de_tramos.items() if k not in ('distintos', 'ejemplos')}
    distintos = [{'objeto': 'tramo', 'id': d['tramo'], 'campo': d['campo'], 'sql': d['sql'], 'capas': d['capas']}
                 for d in de_tramos.get('ejemplos') or []]
    for objeto, lista, clave, campos in OBJETOS_COMPARADOS:
        a = {getattr(o, clave): o for o in getattr(origen, lista)}
        b = {getattr(o, clave): o for o in getattr(leido, lista)}
        if set(a) != set(b):
            difs.setdefault('faltan', {})[objeto] = {'solo_en_sql': sorted(set(a) - set(b))[:20],
                                                      'solo_en_capas': sorted(set(b) - set(a))[:20]}
        for ident in sorted(set(a) & set(b)):
            x, y = a[ident], b[ident]
            for campo in campos:
                if _distinto(getattr(x, campo), getattr(y, campo)):
                    distintos.append({'objeto': objeto, 'id': ident, 'campo': campo,
                                      'sql': getattr(x, campo), 'capas': getattr(y, campo)})
            if objeto == 'nodo' and None not in (x.x, x.y, y.x, y.y) and (
                    ((x.x - y.x) ** 2 + (x.y - y.y) ** 2) ** 0.5 > tolerancia_m):
                distintos.append({'objeto': objeto, 'id': ident, 'campo': 'xy', 'sql': (x.x, x.y),
                                  'capas': (y.x, y.y)})
            if objeto == 'tramo_bt' and _geometria_distinta(x.geometry, y.geometry, tolerancia_m):
                distintos.append({'objeto': objeto, 'id': ident, 'campo': 'geometria', 'sql': x.geometry,
                                  'capas': y.geometry})
    sa = (origen.metadata or {}).get(SIN_REGLA_BT) or {}
    sb = (leido.metadata or {}).get(SIN_REGLA_BT) or {}
    if sa != sb:
        difs[SIN_REGLA_BT] = {'sql': sa, 'capas': sb}
    if distintos:
        difs['distintos'] = len(distintos)
        difs['ejemplos'] = distintos[:20]
    return difs
