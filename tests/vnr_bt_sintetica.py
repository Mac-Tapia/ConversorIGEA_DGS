"""080:RF-60 (MEM-BT v2): apoyo de las pruebas de la exportación de la red BT en flujo. Sin SQL Server ni base real.

- :class:`EmpresaGrande`: una empresa VNR-GIS sintética de ``salidas`` salidas MT, cada una con ``tramos`` tramos BT
  (y, MEM-MT, ``tramos_mt`` tramos MT, con equipos y los casos de la red MT si ``mt_rica``), generada fila a fila al
  leerla (la tabla no ocupa memoria antes de leerla) y con las filas de cada tabla barajadas.
- :class:`MotorSinMars`: un SQL Server de mentira que da esas filas a medida que se piden, anota cada consulta y cómo
  se leyó, responde a ``COUNT`` y, como SQL Server sin MARS, no deja abrir una consulta con otra a medio leer.
- :func:`huella_gpkg`: lo que tiene un GeoPackage, tabla a tabla (esquema, filas y sha256 de las filas ordenadas).
- Como guion, mide en un proceso hijo el pico de memoria (``peak_wset``) de la cadena entera del CLI ``bak-a-capas``
  (lectura, modelo y GeoPackage) sobre una :class:`EmpresaGrande`:
  ``python vnr_bt_sintetica.py <src> <salidas> <tramos> <semilla> <destino.gpkg> [lote|-] [tramos_mt] [rica]`` →
  última línea ``MEDIDA {json}``.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

CAMPOS = {
    'empEmpresa': ('CodEmpresa', 'Datum', 'ZonaUTM'),
    'mtSalida': ('CodSalidaMT', 'CodSet', 'CodTenNomi', 'EtiquetaSalida', 'CodSisElectrico'),
    'CentroTransformacion': ('CodSet', 'Nombre', 'UTMEste', 'UTMNorte'),
    'mtTramo': ('CodTramoMT', 'CodSalidaMT', 'CodTramoMTPadre', 'CodNorma', 'CodTenNomi', 'EstadoVNR', 'CodTipoRed'),
    'verTramoMT': ('CodTramoMT', 'SecVertice', 'UTMEste', 'UTMNorte'),
    'Sed': ('CodSed', 'CodSalidaMT', 'PotInstalada', 'UTMEste', 'UTMNorte', 'MaxDemTotal', 'CodNorma',
            'EtiquetaCampo'),
    'mtNodoEnlace': ('CodNodoMT', 'CodTramoMT', 'CodSed', 'UTMEste', 'UTMNorte'),
    # MEM-MT: solo con ``mt_rica``.
    'mtEquipo': ('CodEqp', 'CodTramoMT', 'CodTipoEquipoProteccion', 'CodEstadoOperacion', 'CodNorma', 'UTMEste',
                 'UTMNorte'),
    'admCodigosNorma': ('CodNorma', 'Descripcion', 'CodSubComponente'),
    'cfgCodigoSecundario': ('CodSecundario', 'CodTipSecundario', 'Descripcion'),
    'btSalida': ('CodSalidaBT', 'CodSed', 'EtiquetaSalida', 'CodTenNomi3', 'UTMEste', 'UTMNorte'),
    'btTramo': ('CodTramoBT', 'CodSalidaBT', 'CodTramoBTPadre', 'CodNormaFase', 'CodTipoRed', 'Longitud', 'EstadoVNR'),
    'verTramoBT': ('CodTramoBT', 'SecVertice', 'UTMEste', 'UTMNorte'),
}


def _barajado(n: int, semilla: int):
    """``range(n)`` en un orden barajado sin guardarlo: i → (a·i + b) mód n, con a primo con n."""
    if n <= 1:
        yield from range(n)
        return
    a = 1 + (semilla * 2654435761) % (n - 1)
    while math.gcd(a, n) != 1:
        a += 1
    b = semilla % n
    for i in range(n):
        yield (a * i + b) % n


class EmpresaGrande:
    """``salidas`` salidas MT de 10 kV, cada una con ``tramos_mt`` tramos MT en cadena (dos por omisión), una SED con su
    enlace, de 1 a 3 salidas BT y ``tramos`` tramos BT de 2 a 4 vértices; con un tramo BT sin vértices y otro sin salida
    MT cada 97 salidas.

    MEM-MT: con ``mt_rica``, además, la tabla de equipos (una maniobra por salida, un banco cada 3, un regulador cada 5,
    un pararrayos cada 7 y un tipo sin modelar cada 19), una salida sin tramos cada 11 (con su SED), una SED con la
    etiqueta de otra cada 13 y una sin etiqueta cada 17. Con los valores por omisión, las mismas filas que antes."""

    def __init__(self, salidas: int, tramos: int, semilla: int = 0, tramos_mt: int = 2, mt_rica: bool = False):
        self.salidas, self.tramos, self.semilla = salidas, tramos, semilla
        self.tramos_mt, self.mt_rica = tramos_mt, mt_rica
        #: La separación entre salidas, para que sus tramos MT no se toquen (2 000 m con dos tramos, como antes).
        self.paso = max(2000.0, 100.0 * tramos_mt + 1000.0)
        #: Donde acaba el último tramo MT de la salida (y está su SED), desde su origen.
        self.fin = 100.0 * tramos_mt

    def _sin_tramos(self, i: int) -> bool:
        return self.mt_rica and i % 11 == 4

    def _bt_de(self, i: int) -> int:
        return 1 + (i + self.semilla) % 3

    def _vertices_de(self, i: int, t: int) -> int:
        return 0 if (i % 97 == 5 and t == 0) else 2 + (i + t + self.semilla) % 3

    def _mt(self, nombre: str):
        n = self.salidas
        if nombre == 'empEmpresa':
            yield {'CodEmpresa': 'EMP', 'Datum': 'WGS84', 'ZonaUTM': 18}
        elif nombre == 'CentroTransformacion':
            yield {'CodSet': 'S1', 'Nombre': 'Uno', 'UTMEste': 0.0, 'UTMNorte': 0.0}
        elif nombre == 'admCodigosNorma':
            yield {'CodNorma': 'AA05003', 'Descripcion': 'RED AEREA CONDUCTOR DE AA O SIMIL. 3x50 mm2',
                   'CodSubComponente': 'A1'}
            if self.mt_rica:
                yield {'CodNorma': 'BC300', 'Descripcion': 'BANCO DE CONDENSADORES 300 kVAR', 'CodSubComponente': 'C4'}
                yield {'CodNorma': 'BR200', 'Descripcion': 'BANCO DE REGULACION DE TENSION x 3, MONOFASICO, In = 200 A, '
                                                           '10 kV', 'CodSubComponente': 'C5'}
                yield {'CodNorma': 'CU01601', 'Descripcion': 'RED AEREA CONDUCTOR DE COBRE 1x16 mm2',
                       'CodSubComponente': 'A1'}
        elif nombre == 'cfgCodigoSecundario':
            for k, d in enumerate(['2.3 kV', '5.8 kV', '7.62 kV', '10 kV'], start=1):
                yield {'CodSecundario': f'40{k}', 'CodTipSecundario': 'MT', 'Descripcion': d}
        elif nombre == 'mtSalida':
            for i in _barajado(n, self.semilla + 1):
                yield {'CodSalidaMT': f'F{i:05d}', 'CodSet': 'S1', 'CodTenNomi': 'D', 'EtiquetaSalida': f'AL{i:05d}',
                       'CodSisElectrico': 'SE1'}
        elif nombre == 'mtTramo':
            for i in _barajado(n, self.semilla + 2):
                if self._sin_tramos(i):
                    continue
                for k in range(1, self.tramos_mt + 1):
                    rica = self.mt_rica and (i + k) % 9 == 0
                    yield {'CodTramoMT': f'T{i:05d}_{k}', 'CodSalidaMT': f'F{i:05d}',
                           'CodTramoMTPadre': '' if k == 1 else f'T{i:05d}_{k - 1}',
                           'CodNorma': 'CU01601' if rica else 'AA05003', 'CodTenNomi': 'D',
                           'EstadoVNR': 'N' if rica else 'E', 'CodTipoRed': 'S' if rica else 'A'}
        elif nombre == 'verTramoMT':
            for i in _barajado(n, self.semilla + 3):
                if self._sin_tramos(i):
                    continue
                x0 = self.paso * i
                for k in range(1, self.tramos_mt + 1):
                    a, b = 100.0 * (k - 1), 100.0 * k
                    yield {'CodTramoMT': f'T{i:05d}_{k}', 'SecVertice': 1, 'UTMEste': x0 + a, 'UTMNorte': 1.0}
                    yield {'CodTramoMT': f'T{i:05d}_{k}', 'SecVertice': 2, 'UTMEste': x0 + b, 'UTMNorte': 1.0}
        elif nombre == 'Sed':
            for i in _barajado(n, self.semilla + 4):
                etiqueta = f'SED{i:05d}'
                if self.mt_rica and i % 13 == 6:
                    etiqueta = 'SED00000'
                elif self.mt_rica and i % 17 == 8:
                    etiqueta = ''
                yield {'CodSed': f'E{i:05d}', 'CodSalidaMT': f'F{i:05d}', 'PotInstalada': 250.0,
                       'UTMEste': self.paso * i + self.fin, 'UTMNorte': 5.0, 'MaxDemTotal': 120.0, 'CodNorma': 'SED03',
                       'EtiquetaCampo': etiqueta}
        elif nombre == 'mtNodoEnlace':
            for i in _barajado(n, self.semilla + 5):
                yield {'CodNodoMT': f'N{i:05d}', 'CodTramoMT': f'T{i:05d}_{self.tramos_mt}', 'CodSed': f'E{i:05d}',
                       'UTMEste': self.paso * i + self.fin, 'UTMNorte': 1.0}
        elif nombre == 'mtEquipo':
            yield from self._equipos()

    def _equipos(self):
        k_max = self.tramos_mt
        for i in _barajado(self.salidas, self.semilla + 9):
            if self._sin_tramos(i):
                continue
            x0 = self.paso * i
            casos = [('IN', 1, 'NC' if i % 4 else 'NA', 'X', 10.0)]
            if i % 3 == 0:
                casos.append(('BC', k_max, 'NC', 'BC300', self.fin - 1.0))
            if i % 5 == 0 and k_max >= 2:
                casos.append(('BR', 2, 'NC', 'BR200', 110.0))
            if i % 7 == 0:
                casos.append(('PA', 1, 'NC', 'X', 1.0))
            if i % 19 == 0:
                casos.append(('ZZ', 1, 'NC', 'X', 50.0))
            for j, (tipo, k, estado, norma, x) in enumerate(casos):
                yield {'CodEqp': f'Q{i:05d}_{j}', 'CodTramoMT': f'T{i:05d}_{k}', 'CodTipoEquipoProteccion': tipo,
                       'CodEstadoOperacion': estado, 'CodNorma': norma, 'UTMEste': x0 + x, 'UTMNorte': 1.0}

    def _salidas_bt(self):
        for i in _barajado(self.salidas, self.semilla + 6):
            for k in range(self._bt_de(i)):
                yield {'CodSalidaBT': f'SB{i:05d}_{k}', 'CodSed': f'E{i:05d}', 'EtiquetaSalida': f'C{k}',
                       'CodTenNomi3': 'B', 'UTMEste': self.paso * i + self.fin, 'UTMNorte': 5.0}

    def _tramos_bt(self):
        for j in _barajado(self.salidas * self.tramos, self.semilla + 7):
            i, t = divmod(j, self.tramos)
            salida = 'SB_NO_HAY' if (i % 97 == 7 and t == 0) else f'SB{i:05d}_{t % self._bt_de(i)}'
            yield {'CodTramoBT': f'B{i:05d}_{t:05d}', 'CodSalidaBT': salida,
                   'CodTramoBTPadre': '' if t == 0 else f'B{i:05d}_{t - 1:05d}',
                   'CodNormaFase': 'CAAI35' if t % 2 else 'NYY16', 'CodTipoRed': 'A' if t % 3 else 'S',
                   'Longitud': 10.0, 'EstadoVNR': 'E' if t % 5 else 'N'}

    def _vertices_bt(self):
        for j in _barajado(self.salidas * self.tramos, self.semilla + 8):
            i, t = divmod(j, self.tramos)
            for k in range(self._vertices_de(i, t)):
                yield {'CodTramoBT': f'B{i:05d}_{t:05d}', 'SecVertice': k + 1,
                       'UTMEste': self.paso * i + self.fin + 3.0 * t + k, 'UTMNorte': 5.0 + 2.0 * k}

    def filas(self, nombre: str):
        if nombre == 'btSalida':
            return self._salidas_bt()
        if nombre == 'btTramo':
            return self._tramos_bt()
        if nombre == 'verTramoBT':
            return self._vertices_bt()
        return self._mt(nombre)

    def tablas(self) -> dict:
        """Nombre → (campos, función que da sus filas), como lo lee :class:`MotorSinMars`."""
        return {n: (campos, lambda n=n: self.filas(n)) for n, campos in CAMPOS.items()
                if n != 'mtEquipo' or self.mt_rica}


class _CursorSinMars:
    def __init__(self, motor: MotorSinMars):
        self.motor, self.tabla, self.sql = motor, None, ''
        self._filas, self.pendiente = iter(()), False

    def execute(self, sql, *params):
        abiertas = [c.sql for c in self.motor.cursores if c.pendiente and c is not self]
        assert not abiertas, f'dos consultas abiertas a la vez (SQL Server sin MARS): {abiertas[:1]} y {sql}'
        self.motor.consultas.append((sql, params))
        self.sql, self.tabla = sql, None
        if sql.startswith('SELECT state_desc FROM sys.databases'):
            filas = [('ONLINE',)]
        elif 'INFORMATION_SCHEMA.COLUMNS' in sql:
            filas = [(t, c) for t, (campos, _f) in self.motor.tablas.items() for c in campos]
        elif sql.startswith('SELECT COUNT(*) FROM ['):
            tabla = sql.split('FROM [', 1)[1].split(']', 1)[0]
            filas = [(self.motor.cuenta if self.motor.cuenta is not None
                      else sum(1 for _f in self.motor.tablas[tabla][1]()),)]
        elif sql.startswith('SELECT ['):
            self.tabla = sql.rsplit('FROM [', 1)[1].split(']', 1)[0]
            campos = [c.strip('[] ') for c in sql[len('SELECT '):sql.index(' FROM')].split(',')]
            self._filas = (tuple(f.get(c) for c in campos) for f in self.motor.tablas[self.tabla][1]())
            self.pendiente = True
            return self
        else:
            raise AssertionError(f'SQL inesperado: {sql}')
        self._filas = iter(filas)
        self._quedan = list(filas)
        self.pendiente = bool(filas)
        return self

    def fetchone(self):
        fila = next(self._filas, None)
        if self.tabla is None:
            self._quedan = self._quedan[1:]
            self.pendiente = bool(self._quedan)
        return fila

    def fetchall(self):
        self.motor.lecturas.append((self.tabla, 'fetchall', None, self.sql))
        self.pendiente = False
        return list(self._filas)

    def fetchmany(self, n):
        self.motor.lecturas.append((self.tabla, 'fetchmany', n, self.sql))
        bloque = list(itertools.islice(self._filas, n))
        if not bloque:
            self.pendiente = False
        return bloque

    def close(self):
        self.pendiente = False


class MotorSinMars:
    """Un SQL Server de mentira: ``tablas`` es nombre → (campos, función que da sus filas). Anota las consultas
    (``consultas``: sql y parámetros) y las lecturas (``lecturas``: tabla, 'fetchall' | 'fetchmany', tamaño, sql).
    ``cuenta`` es lo que responde a cada ``COUNT`` (``None``: las filas de verdad)."""

    def __init__(self, tablas: dict, cuenta: int | None = None):
        self.tablas, self.cuenta = tablas, cuenta
        self.consultas: list[tuple[str, tuple]] = []
        self.lecturas: list[tuple] = []
        self.cursores: list[_CursorSinMars] = []

    def conectar(self, *_args, **_kw):
        motor = self

        class _Conexion:
            def cursor(self):
                cur = _CursorSinMars(motor)
                motor.cursores.append(cur)
                return cur

            def close(self):
                pass

        return _Conexion()


def huella_gpkg(ruta: Path | str) -> dict:
    """Lo que tiene un GeoPackage, para compararlo con otro: las tablas, índices y disparadores (por nombre), y de cada
    capa su fila de ``gpkg_contents`` (sin la hora), su ``gpkg_geometry_columns``, su esquema, sus filas y la sha256 de
    sus filas ordenadas (sin el ``fid``, que es el orden de escritura; la geometría, en hexadecimal)."""
    cn = sqlite3.connect(f'file:{Path(ruta).as_posix()}?mode=ro', uri=True)
    try:
        objetos = sorted(cn.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        capas = {}
        for (nombre,) in cn.execute('SELECT table_name FROM gpkg_contents ORDER BY table_name').fetchall():
            contenido = cn.execute('SELECT table_name, data_type, identifier, description, min_x, min_y, max_x, max_y, '
                                   'srs_id FROM gpkg_contents WHERE table_name = ?', (nombre,)).fetchone()
            geometria = cn.execute('SELECT * FROM gpkg_geometry_columns WHERE table_name = ?', (nombre,)).fetchone()
            esquema = [tuple(c[1:]) for c in cn.execute(f'PRAGMA table_info("{nombre}")')]
            columnas = [c[0] for c in esquema if c[0] != 'fid']
            filas = sorted(json.dumps([v.hex() if isinstance(v, bytes) else v for v in f], default=str)
                           for f in cn.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in columnas)} '
                                               f'FROM "{nombre}"'))
            capas[nombre] = {'contenido': contenido, 'geometria': geometria, 'esquema': esquema, 'filas': len(filas),
                             'sha256': hashlib.sha256('\n'.join(filas).encode('utf-8')).hexdigest()}
        srs = sorted(cn.execute('SELECT srs_id, organization, organization_coordsys_id FROM gpkg_spatial_ref_sys'))
        return {'objetos': objetos, 'capas': capas, 'srs': srs}
    finally:
        cn.close()


def _pico_del_proceso() -> int:
    """El pico de memoria de este proceso, en bytes: ``peak_wset`` en Windows, ``ru_maxrss`` en los demás."""
    try:
        import psutil

        info = psutil.Process().memory_info()
        if hasattr(info, 'peak_wset'):
            return int(info.peak_wset)
    except ImportError:
        pass
    import resource

    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def medir_cli(salidas: int, tramos: int, semilla: int, destino: str, lote: int | None = None, tramos_mt: int = 2,
              mt_rica: bool = False) -> dict:
    """La cadena entera del CLI ``bak-a-capas`` sobre una :class:`EmpresaGrande`, con su pico y su tiempo."""
    from convertersmartgrid.adaptadores.entrada.vnr import cli
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    motor = MotorSinMars(EmpresaGrande(salidas, tramos, semilla, tramos_mt, mt_rica).tablas())
    sv.conectar = motor.conectar
    argv = ['bak-a-capas', 'CSG_VNR_SINTETICA', destino] + ([] if lote is None else ['--lote-salidas', str(lote)])
    t0 = time.perf_counter()
    rc = cli.main(argv)
    segundos = time.perf_counter() - t0
    return {'rc': rc, 'pico': _pico_del_proceso(), 'segundos': round(segundos, 3), 'salidas': salidas,
            'tramos': tramos, 'tramos_mt': tramos_mt, 'mt_rica': mt_rica, 'huella': hashlib.sha256(json.dumps(huella_gpkg(destino), default=str)
                                                         .encode('utf-8')).hexdigest()}


if __name__ == '__main__':
    src, n, b, semilla, destino = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    lote = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] != '-' else None
    tramos_mt = int(sys.argv[7]) if len(sys.argv) > 7 else 2
    mt_rica = len(sys.argv) > 8 and sys.argv[8] == 'rica'
    sys.path.insert(0, src)
    medida = medir_cli(n, b, semilla, destino, lote, tramos_mt, mt_rica)
    print('MEDIDA ' + json.dumps(medida), flush=True)
