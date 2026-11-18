"""Spec 023 — VNR-GIS desde la copia de SQL Server de cualquier concesionaria, sin motor.

El motor se sustituye por un doble de ODBC; las tablas son las del modelo VNR-GIS del
regulador, iguales para toda empresa. La copia real se prueba con ``CSG_VNR_BAK``.
"""
from __future__ import annotations

import itertools
import os
import random
from collections import defaultdict
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv


def _exige_capas():
    """080 T15 a T17: el paquete de capas en flujo (exporters/capas.py) es lo nuevo de la 080 v3; su ausencia es la falla de
    la aserción, no un error al importar (el rojo, sobre el código de antes, tiene que fallar por aserción)."""
    import importlib.util
    nombre = 'convertersmartgrid.adaptadores.entrada.vnr.exporters.capas'
    assert importlib.util.find_spec(nombre) is not None, 'falta adaptadores/entrada/vnr/exporters/capas.py (080 T15 a T17)'


@pytest.fixture(autouse=True)
def _catalogo_de_empresa_aislado(monkeypatch, tmp_path):
    """080:RF-49: el catálogo de cada empresa se crea al cargar; una prueba no toca el real."""
    monkeypatch.setattr('convertersmartgrid.reglas.project_root', lambda: tmp_path)


# --------------------------------------------------------------------------- doble del motor
class Cursor:
    def __init__(self, motor):
        self.motor = motor
        self._filas = []

    def execute(self, sql, *params):
        self.motor.sql.append(sql)
        self._filas = self.motor.responder(sql, params)
        return self

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return list(self._filas)

    def fetchmany(self, n):
        # 080:RF-60: la red BT se lee por bloques (DB-API).
        bloque, self._filas = list(self._filas[:n]), self._filas[n:]
        return bloque

    def nextset(self):
        return False


class Conexion:
    def __init__(self, motor, cadena):
        self.motor, self.cadena = motor, cadena

    def cursor(self):
        return Cursor(self.motor)

    def close(self):
        pass


class Motor:
    """Responde como SQL Server a lo que piden ``restaurar`` y ``leer_datos``."""

    def __init__(self, bases=(), tablas=None):
        # Nombre → estado de ``sys.databases.state_desc``; una lista de nombres vale como bases en línea.
        self.bases = dict(bases) if isinstance(bases, dict) else {b: 'ONLINE' for b in bases}
        self.tablas = tablas or {}
        self.sql: list[str] = []

    def conectar(self, cadena, autocommit=True):
        return Conexion(self, cadena)

    def responder(self, sql, params):
        if sql.startswith('SELECT name FROM sys.databases'):
            return [(params[0],)] if params[0] in self.bases else []
        if sql.startswith('SELECT state_desc FROM sys.databases'):
            return [(self.bases[params[0]],)] if params[0] in self.bases else []
        if sql.startswith('DROP DATABASE'):
            self.bases.pop(sql.split('[', 1)[1].split(']', 1)[0], None)
            return []
        if 'InstanceDefaultDataPath' in sql:
            return [('C:\\datos\\',)]
        if sql.startswith('RESTORE FILELISTONLY'):
            return [('VNR_dat', 'X', 'D'), ('VNR_log', 'X', 'L')]
        if sql.startswith('RESTORE DATABASE'):
            return []
        if 'INFORMATION_SCHEMA.COLUMNS' in sql:
            return [(t, c) for t, filas in self.tablas.items() for c in (filas[0] if filas else {})]
        if sql.startswith('SELECT COUNT(*) FROM ['):
            # 080:RF-60: la cuenta de la red BT antes de leerla; aquí, la tabla entera (cota por arriba).
            return [(len(self.tablas[sql.split('FROM [', 1)[1].split(']', 1)[0]]),)]
        if sql.startswith('SELECT ['):
            tabla = sql.rsplit('FROM [', 1)[1].rstrip(']')
            campos = [c.strip('[] ') for c in sql[len('SELECT '):sql.index(' FROM')].split(',')]
            return [tuple(f.get(c) for c in campos) for f in self.tablas[tabla]]
        raise AssertionError(f'SQL inesperado: {sql}')


# --------------------------------------------------------------------------- red de ejemplo
def _tablas():
    """Una salida de 10 kV: T1 sale de la SET, T2 cuelga de T1, T3 de T2 a 3 m (hueco)."""
    return {
        'empEmpresa': [{'CodEmpresa': 'EMP', 'Datum': 'WGS84', 'ZonaUTM': 18}],
        'mtSalida': [{'CodSalidaMT': 'F1', 'CodSet': 'S1', 'CodTenNomi': 'D',
                      'EtiquetaSalida': 'F1', 'CodSisElectrico': 'SE1'}],
        'CentroTransformacion': [{'CodSet': 'S1', 'Nombre': 'Uno', 'UTMEste': 0.0,
                                  'UTMNorte': 0.0}],
        'mtTramo': [
            {'CodTramoMT': 'T1', 'CodSalidaMT': 'F1', 'CodTramoMTPadre': '', 'CodNorma': 'AA05003'},
            {'CodTramoMT': 'T2', 'CodSalidaMT': 'F1', 'CodTramoMTPadre': 'T1', 'CodNorma': 'AA05003'},
            {'CodTramoMT': 'T3', 'CodSalidaMT': 'F1', 'CodTramoMTPadre': 'T2', 'CodNorma': 'CU01601'}],
        'verTramoMT': [
            {'CodTramoMT': 'T1', 'SecVertice': 1, 'UTMEste': 0.0, 'UTMNorte': 1.0},
            {'CodTramoMT': 'T1', 'SecVertice': 2, 'UTMEste': 50.0, 'UTMNorte': 1.0},
            {'CodTramoMT': 'T1', 'SecVertice': 3, 'UTMEste': 100.0, 'UTMNorte': 1.0},
            # T2 dibujado al revés: su final toca el final de T1.
            {'CodTramoMT': 'T2', 'SecVertice': 1, 'UTMEste': 200.0, 'UTMNorte': 1.0},
            {'CodTramoMT': 'T2', 'SecVertice': 2, 'UTMEste': 100.0, 'UTMNorte': 1.0},
            {'CodTramoMT': 'T3', 'SecVertice': 1, 'UTMEste': 203.0, 'UTMNorte': 1.0},
            {'CodTramoMT': 'T3', 'SecVertice': 2, 'UTMEste': 300.0, 'UTMNorte': 1.0}],
        'Sed': [{'CodSed': 'E1', 'CodSalidaMT': 'F1', 'PotInstalada': 250.0, 'UTMEste': 300.0,
                 'UTMNorte': 5.0, 'MaxDemTotal': 120.0}],
        'mtNodoEnlace': [{'CodNodoMT': 'N1', 'CodTramoMT': 'T3', 'CodSed': 'E1',
                          'UTMEste': 300.0, 'UTMNorte': 1.0}],
        'mtEquipo': [
            {'CodEqp': 'Q1', 'CodTramoMT': 'T2', 'CodTipoEquipoProteccion': 'SE',
             'CodEstadoOperacion': 'NA', 'CodNorma': 'X', 'UTMEste': 199.0, 'UTMNorte': 1.0},
            {'CodEqp': 'B1', 'CodTramoMT': 'T1', 'CodTipoEquipoProteccion': 'BC',
             'CodEstadoOperacion': 'NC', 'CodNorma': 'BC300', 'UTMEste': 99.0, 'UTMNorte': 1.0},
            {'CodEqp': 'P1', 'CodTramoMT': 'T1', 'CodTipoEquipoProteccion': 'PA',
             'CodEstadoOperacion': 'NC', 'CodNorma': 'X', 'UTMEste': 1.0, 'UTMNorte': 1.0}],
        'admCodigosNorma': [
            {'CodNorma': 'AA05003', 'Descripcion': 'RED AEREA CONDUCTOR DE AA O SIMIL. 3x50 mm2',
             'CodSubComponente': 'A1'},
            {'CodNorma': 'CU01601', 'Descripcion': 'RED AEREA CONDUCTOR DE COBRE 1x16 mm2',
             'CodSubComponente': 'A1'},
            {'CodNorma': 'BC300', 'Descripcion': 'BANCO DE CONDENSADORES 300 kVAR',
             'CodSubComponente': 'C4'}],
        'cfgCodigoSecundario': [
            {'CodSecundario': f'40{i}', 'CodTipSecundario': 'MT', 'Descripcion': d}
            for i, d in enumerate(['2.3 kV', '5.8 kV', '7.62 kV', '10 kV', '12 kV', '13.2 kV',
                                   '22.9 kV'], start=1)],
    }


def _datos(tablas=None):
    motor = Motor(tablas=tablas or _tablas())
    return sv.leer_datos(motor.conectar('red')), motor


# --------------------------------------------------------------------------- pruebas
def test_una_vista_rota_no_tumba_la_lectura():
    """023:RF-9 — una vista que nombra otra base que no vino en la copia (una distribuidora real 2025:
    «norEquipoMT» apunta a «VNRGISGART», su base de parámetros, que no se entregó) se anota y
    la lectura sigue con lo demás de la red."""
    class MotorRoto(Motor):
        def responder(self, sql, params):
            if sql.startswith('SELECT [') and sql.endswith('[admCodigosNorma]'):
                raise RuntimeError("[42S02] Invalid object name 'VNRGISGART.dbo.norEquipoMT'. (208)")
            return super().responder(sql, params)

    datos = sv.leer_datos(MotorRoto(tablas=_tablas()).conectar('red'))
    assert datos.normas == [] and datos.tramos and datos.seds
    (ilegible,) = datos.ilegibles
    assert ilegible['tabla'] == 'admCodigosNorma' and 'VNRGISGART' in ilegible['motivo']
    modelo, avisos = sv.modelo_canonico(datos)
    assert modelo.sections and any(a['code'] == 'BANCO_SIN_KVAR' for a in avisos)


def test_config_y_base_de_parametros_junto_al_original(tmp_path):
    """023:RF-2 — empresa y bases del ``ConfigBD.config``; la base de parámetros, la que
    dice o la otra ``.bak`` con «param», también donde estaba el original."""
    original = tmp_path / 'entrega'
    original.mkdir()
    (original / 'ConfigBD.config').write_text(
        '<Configuracion><valores><CodEmpresa>XYZ</CodEmpresa><nombreBD>XYZ_VNR</nombreBD>'
        '<nombreArchBD_param>param_XYZ.bak</nombreArchBD_param></valores></Configuracion>',
        encoding='utf-8')
    (original / 'param_XYZ.bak').write_bytes(b'p')
    custodia = tmp_path / 'run'
    custodia.mkdir()
    (custodia / 'XYZ_VNR.bak').write_bytes(b'r')
    assert sv.config_de(custodia / 'XYZ_VNR.bak') == {}
    assert sv.config_de(custodia / 'XYZ_VNR.bak', [original])['CodEmpresa'] == 'XYZ'
    assert sv.copia_de_parametros(custodia / 'XYZ_VNR.bak', [original]) == original / 'param_XYZ.bak'
    (original / 'ConfigBD.config').unlink()
    assert sv.copia_de_parametros(custodia / 'XYZ_VNR.bak', [original]) == original / 'param_XYZ.bak'


def test_restaura_con_su_huella_y_reutiliza(tmp_path):
    """023:RF-3 / 023:RF-4 — se restaura con la huella en el nombre y ``WITH MOVE`` a la
    carpeta de datos del motor; con la misma copia ya restaurada, no se vuelve a restaurar."""
    bak = tmp_path / 'red.bak'
    bak.write_bytes(b'copia')
    motor = Motor()
    nombre = sv.restaurar(bak, conectar_odbc=motor.conectar)
    assert nombre == f'CSG_VNR_{sv.huella(bak)[:16]}'
    restore = next(s for s in motor.sql if s.startswith('RESTORE DATABASE'))
    assert "MOVE N'VNR_dat' TO N'C:\\datos" in restore and '.ldf' in restore
    motor2 = Motor(bases={nombre})
    assert sv.restaurar(bak, conectar_odbc=motor2.conectar) == nombre
    assert not any(s.startswith('RESTORE') for s in motor2.sql)


@pytest.mark.parametrize('estado', ['RESTORING', 'RECOVERY_PENDING', 'SUSPECT', 'OFFLINE'])
def test_una_base_que_no_esta_en_linea_se_restaura_otra_vez(tmp_path, estado):
    """023:RF-4 — un RESTORE cortado deja la base de la huella en RESTORING: no se reutiliza. Se retira, se restaura
    de nuevo con REPLACE (los ficheros de una base fuera de línea siguen en disco) y queda anotado."""
    bak = tmp_path / 'red.bak'
    bak.write_bytes(b'copia')
    nombre = f'CSG_VNR_{sv.huella(bak)[:16]}'
    motor = Motor(bases={nombre: estado, 'OTRA_BASE': 'RESTORING'})
    avisos: list[dict] = []
    assert sv.restaurar(bak, conectar_odbc=motor.conectar, avisos=avisos) == nombre
    drop = [s for s in motor.sql if s.startswith('DROP DATABASE')]
    assert drop == [f'DROP DATABASE [{nombre}]']
    restore = next(s for s in motor.sql if s.startswith('RESTORE DATABASE'))
    assert motor.sql.index(drop[0]) < motor.sql.index(restore) and 'REPLACE' in restore
    assert 'OTRA_BASE' in motor.bases, 'solo se retira la base de esta huella'
    (aviso,) = avisos
    assert aviso['code'] == 'BASE_VNR_RESTAURADA_DE_NUEVO' and estado in aviso['detalle']


def test_sin_motor_se_dice_que_instalar():
    """023:RF-5 — sin motor de SQL Server, el error dice qué instalar."""
    def falla(*_a, **_k):
        raise OSError('servidor no encontrado')

    with pytest.raises(sv.MotorSqlNoDisponible, match='SQL Server Express'):
        sv.conectar(sv.SERVIDOR, conectar_odbc=falla)


def test_solo_lee():
    """023:RF-6 — la lectura solo hace SELECT."""
    _datos_, motor = _datos()
    assert motor.sql and all(s.lstrip().upper().startswith('SELECT') for s in motor.sql)


def test_tablas_por_sus_campos_y_no_por_su_nombre():
    """023:RF-7 — una tabla de tramos con otro nombre se reconoce por sus campos; con dos
    candidatas, la de menos columnas (la base trae copias «Ada» con más)."""
    tablas = _tablas()
    tablas['RedMT_Empresa'] = tablas.pop('mtTramo')
    tablas['mtTramoAda'] = [{**f, 'Proceso': 'x', 'SecTramo': 1} for f in tablas['RedMT_Empresa']]
    datos, _ = _datos(tablas)
    assert len(datos.tramos) == 3
    assert sv.tablas_por_campos({'a': CamposTramo, 'b': CamposTramo + ['X']})['tramo'] == 'a'


CamposTramo = ['CodTramoMT', 'CodSalidaMT', 'CodTramoMTPadre', 'CodNorma']


def test_tension_y_crs_salen_de_la_copia():
    """023:RF-8 — la letra de tensión, por el orden de los códigos MT de los parámetros
    (D = 10 kV, G = 22,9 kV); el CRS, del datum y la zona de la empresa."""
    datos, _ = _datos()
    kv = sv.tensiones_mt(datos.codigos_secundarios)
    assert kv['D'] == 10.0 and kv['G'] == 22.9
    assert sv.crs_de_empresa(datos.empresa) == 'EPSG:32718'
    assert sv.crs_de_empresa([{'Datum': 'PSAD56', 'ZonaUTM': 17}]) == 'EPSG:24877'
    assert sv.crs_de_empresa([{'Datum': '', 'ZonaUTM': None}]) is None


def test_modelo_canonico_de_una_salida():
    """023:RF-9 / 023:RF-10 — tramos unidos por su padre y orientados desde la SET, el hueco
    con el padre anotado, la SED en su nodo con su kVA, la maniobra abierta en su lado, el
    banco con los kvar de su norma, el pararrayos fuera; el puente lleva maniobras y
    vértices intermedios."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    datos, _ = _datos()
    modelo, avisos = sv.modelo_canonico(datos)
    secciones = {s.section_id: s for s in modelo.sections}
    assert set(secciones) == {'T1', 'T2', 'T3'}
    fuente = modelo.sources[0]
    assert fuente.nominal_kv == 10.0 and secciones['T1'].from_node == fuente.node_id
    assert secciones['T2'].from_node == secciones['T1'].to_node, 'unido por su padre, al revés'
    assert secciones['T2'].geometry[0] == (100.0, 1.0), 'geometría orientada desde el origen'
    assert secciones['T3'].from_node == secciones['T2'].to_node
    assert any(a['code'] == 'HUECO_CON_SU_PADRE' and a['source_id'] == 'T3' for a in avisos)
    assert secciones['T3'].phases == 'A' and secciones['T1'].phases == 'ABC'
    (carga,) = modelo.loads
    assert carga.connection_node == secciones['T3'].to_node and carga.connected_kva == 250.0
    (maniobra,) = modelo.switches
    assert (maniobra.switch_id, maniobra.on_off, maniobra.section_id) == ('Q1', 0, 'T2')
    (banco,) = modelo.capacitors
    assert banco.kvar == 300.0
    tipos = {c.conductor_code: c for c in modelo.conductor_types}
    assert (tipos['AA05003D'].material, tipos['AA05003D'].section_mm2) == ('AL', 50.0), (
        'la norma con la letra de tensión, como en las otras fuentes')
    assert secciones['T1'].conductor_code == 'AA05003D'
    puente = canonical_to_cymdist(modelo, source_path=Path('red.bak'))
    assert [s['EqNumber'] for s in puente.dataset.switch_settings] == ['Q1']
    assert puente.dataset.switch_settings[0]['Status'] == '0'
    assert [(n['SectionID'], n['CoordX']) for n in puente.dataset.intermediate_nodes] == [('T1', '50.0')]
    carga_dgs = next(iter(puente.dataset.customer_loads.values()))
    assert carga_dgs['ConnectedKVA'] == '250.0'


def test_la_fuente_vnr_acepta_la_copia(monkeypatch, tmp_path):
    """023:RF-1 — la casilla VNR-GIS acepta ``.bak`` y la fuente la lleva por la copia de SQL
    Server, buscando sus vecinas donde estaba el original."""
    from convertersmartgrid.sources.snapshot import snapshot_from_paths
    from convertersmartgrid.sources.vnr import VnrSourceAdapter
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.registry import FORMATOS_PAQUETE_VNR

    assert '.bak' in FORMATOS_PAQUETE_VNR
    bak = tmp_path / 'red.bak'
    bak.write_bytes(b'r')
    datos, _ = _datos()
    vistos = {}

    def cargar(path, *, servidor, vecinas):
        vistos.update(path=Path(path), vecinas=list(vecinas))
        modelo, avisos = sv.modelo_canonico(datos)
        return modelo, avisos, {'company': 'EMP', 'period': 'VNR'}

    monkeypatch.setattr(sv, 'cargar_copia', cargar)
    snap = snapshot_from_paths('vnr', {'vnr_package': bak}, tmp_path, origin='prueba')
    res = VnrSourceAdapter().load(snap, aliases={})
    assert vistos['path'] == bak and vistos['vecinas'] == [tmp_path]
    assert res.provenance['package_format'] == 'sqlserver_bak'
    assert 'F1' in res.dataset.feeders


def test_sin_base_de_parametros_la_tension_sale_de_la_tabla_tensiones():
    """023:RF-9 — sin «cfgCodigoSecundario» (una distribuidora real 2025 no entregó su base de
    parámetros) la tensión de cada letra sale de la tabla «Tensiones» de la red; si vienen las
    dos, manda la del regulador."""
    tablas = _tablas()
    del tablas['cfgCodigoSecundario']
    tablas['Tensiones'] = [{'CodTenNomi': 'D         ', 'Tension': 10.0},
                           {'CodTenNomi': 'G         ', 'Tension': 22.899999618530273}]
    datos, _ = _datos(tablas)
    assert sv.tensiones_de_tabla(datos.tensiones) == {'D': 10.0, 'G': 22.9}
    modelo, _avisos = sv.modelo_canonico(datos)
    assert modelo.sections and all(s.nominal_kv == 10.0 for s in modelo.sections), \
        {s.nominal_kv for s in modelo.sections}
    tablas = _tablas()
    tablas['Tensiones'] = [{'CodTenNomi': 'D', 'Tension': 99.0}]
    datos, _ = _datos(tablas)
    modelo, _avisos = sv.modelo_canonico(datos)
    assert all(s.nominal_kv == 10.0 for s in modelo.sections), 'manda la del regulador'


def test_la_copia_sin_extension_se_reconoce_por_su_cabecera(monkeypatch, tmp_path):
    """023:RF-1 — una copia de SQL Server sin «.bak» (una distribuidora real entregó «<paquete>») se
    reconoce por su cabecera MTF «TAPE»; un fichero sin extensión que no lo es, no."""
    from convertersmartgrid.sources.snapshot import snapshot_from_paths
    from convertersmartgrid.sources.vnr import VnrSourceAdapter
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.official import OfficialDiscoveryError, validate_vnr_package_file

    copia = tmp_path / 'ELOR25_V2'
    copia.write_bytes(b'TAPE\x00\x00\x03\x00' + b'\x00' * 64)
    otro = tmp_path / 'NOTAS'
    otro.write_bytes(b'hola mundo')
    assert sv.es_copia_sql(copia) and not sv.es_copia_sql(otro)
    validate_vnr_package_file(copia)
    with pytest.raises(OfficialDiscoveryError):
        validate_vnr_package_file(otro)
    datos, _ = _datos()
    vistos = {}

    def cargar(path, *, servidor, vecinas):
        vistos['path'] = Path(path)
        modelo, avisos = sv.modelo_canonico(datos)
        return modelo, avisos, {'company': 'EMP', 'period': 'VNR'}

    monkeypatch.setattr(sv, 'cargar_copia', cargar)
    snap = snapshot_from_paths('vnr', {'vnr_package': copia}, tmp_path, origin='prueba')
    res = VnrSourceAdapter().load(snap, aliases={})
    assert res.provenance['package_format'] == 'sqlserver_bak' and 'F1' in res.dataset.feeders


@pytest.mark.skipif(not os.environ.get('CSG_VNR_BAK'), reason='sin CSG_VNR_BAK')
def test_copia_real_de_vnr_gis():
    """023:RF-3 / 023:RF-9 — la copia real se restaura y da sus salidas con tramos y SED."""
    modelo, _avisos, alcance = sv.cargar_copia(os.environ['CSG_VNR_BAK'])
    assert alcance['base_red'].startswith('CSG_VNR_') and modelo.sections and modelo.loads


def test_fichas_del_catalogo_del_proyecto(tmp_path):
    """023:RF-10 — VNR-GIS no trae R ni X: se completan del catálogo de parámetros por el
    mismo código; la ficha si su estado lo permite, si no el valor del modelo; lo que no
    está en el catálogo se dice."""
    from openpyxl import Workbook

    from convertersmartgrid.sources.vnr import fichas_del_catalogo

    wb = Workbook()
    hoja = wb.active
    hoja.title = 'conductores_aereos'
    hoja.append(['codigo', 'R1_modelo_ohm_km', 'R1_ficha_ohm_km', 'X1_modelo_ohm_km',
                 'X1_ficha_ohm_km', 'R0_modelo_ohm_km', 'R0_ficha_ohm_km', 'X0_modelo_ohm_km',
                 'X0_ficha_ohm_km', 'ampacidad_modelo_A', 'ampacidad_ficha_A', 'estado'])
    hoja.append(['AA05003D', 0.7, 0.6755, 0.47, None, 0.7, None, 0.47, None, 190, 195, 'ficha'])
    hoja.append(['CU01601D', 1.2, 9.9, 0.5, None, 1.2, None, 0.5, None, 100, None, 'por_confirmar'])
    ruta = tmp_path / 'catalogo.xlsx'
    wb.save(ruta)
    datos, _ = _datos()
    tablas = _tablas()
    modelo, _ = sv.modelo_canonico(datos)
    modelo.conductor_types.append(type(modelo.conductor_types[0])(conductor_code='ZZ09903D'))
    # Otra tensión u otras fases, mismo material y sección: la misma ficha.
    modelo.conductor_types.append(type(modelo.conductor_types[0])(conductor_code='AA05001G'))
    cuenta = fichas_del_catalogo(modelo, ruta)
    tipos = {c.conductor_code: c for c in modelo.conductor_types}
    assert tipos['AA05003D'].r1_ohm_km == 0.6755 and tipos['AA05003D'].ampacity_a == 195.0
    assert tipos['AA05003D'].x1_ohm_km == 0.47, 'sin ficha de X1, la del modelo'
    assert tipos['CU01601D'].r1_ohm_km == 1.2, 'por confirmar: la del modelo, no la ficha'
    assert tipos['ZZ09903D'].r1_ohm_km is None
    assert tipos['AA05001G'].r1_ohm_km == 0.6755, 'misma familia AA050'
    assert cuenta == {'completados': 3, 'sin_ficha': 1}
    assert tablas


def test_una_isla_se_une_a_la_red_y_se_anota():
    """023:RF-10 — una parte cuya cadena de padres no llega a la cabecera (T4 y T5 son padre
    uno del otro, como SM117) se une a la red por su par de nodos más cercano y se anota."""
    tablas = _tablas()
    tablas['mtTramo'] += [
        {'CodTramoMT': 'T4', 'CodSalidaMT': 'F1', 'CodTramoMTPadre': 'T5', 'CodNorma': 'AA05003'},
        {'CodTramoMT': 'T5', 'CodSalidaMT': 'F1', 'CodTramoMTPadre': 'T4', 'CodNorma': 'AA05003'}]
    tablas['verTramoMT'] += [
        {'CodTramoMT': 'T4', 'SecVertice': 1, 'UTMEste': 310.0, 'UTMNorte': 1.0},
        {'CodTramoMT': 'T4', 'SecVertice': 2, 'UTMEste': 400.0, 'UTMNorte': 1.0},
        {'CodTramoMT': 'T5', 'SecVertice': 1, 'UTMEste': 400.0, 'UTMNorte': 1.0},
        {'CodTramoMT': 'T5', 'SecVertice': 2, 'UTMEste': 500.0, 'UTMNorte': 1.0}]
    datos, _ = _datos(tablas)
    modelo, avisos = sv.modelo_canonico(datos)
    (isla,) = [a for a in avisos if a['code'] == 'ISLA_UNIDA']
    assert isla['distancia_m'] == 10.0
    secciones = {s.section_id: s for s in modelo.sections}
    adyacentes = defaultdict(set)
    for s in modelo.sections:
        adyacentes[s.from_node].add(s.to_node)
        adyacentes[s.to_node].add(s.from_node)
    vistos, pila = set(), [modelo.sources[0].node_id]
    while pila:
        n = pila.pop()
        if n not in vistos:
            vistos.add(n)
            pila.extend(adyacentes[n])
    assert {secciones['T5'].to_node, secciones['T4'].from_node} <= vistos


# --------------------------------------------------------------------------- tramos BT (080:RF-55)
def _tablas_con_bt():
    """La salida de ejemplo con la red BT de su SED, con los nombres de VNR-GIS (``btSalida``,
    ``btTramo``, ``verTramoBT``) y una tabla de reportes que también trae ``CodSalidaBT`` y ``CodSed``."""
    tablas = _tablas()
    tablas['btSalida'] = [{'CodSalidaBT': 'SB1', 'CodSed': 'E1', 'EtiquetaSalida': 'C1', 'CodTenNomi3': 'B',
                           'UTMEste': 300.0, 'UTMNorte': 5.0}]
    tablas['btTramo'] = [
        {'CodTramoBT': 'B1', 'CodSalidaBT': 'SB1', 'CodTramoBTPadre': '', 'CodNormaFase': 'CAAI35',
         'CodTipoRed': 'A', 'Longitud': 41.0, 'EstadoVNR': 'E'},
        {'CodTramoBT': 'B2', 'CodSalidaBT': 'SB1', 'CodTramoBTPadre': 'B1', 'CodNormaFase': 'NYY16',
         'CodTipoRed': 'S', 'Longitud': 9.0, 'EstadoVNR': 'Z'},
        # Sin vértices: no se dibuja, pero no se calla.
        {'CodTramoBT': 'B3', 'CodSalidaBT': 'SB1', 'CodTramoBTPadre': 'B1', 'CodNormaFase': 'CAAI35',
         'CodTipoRed': 'A', 'Longitud': 5.0, 'EstadoVNR': 'P'}]
    tablas['verTramoBT'] = [
        {'CodTramoBT': 'B1', 'SecVertice': 2, 'UTMEste': 330.0, 'UTMNorte': 5.0},
        {'CodTramoBT': 'B1', 'SecVertice': 1, 'UTMEste': 300.0, 'UTMNorte': 5.0},
        {'CodTramoBT': 'B1', 'SecVertice': 3, 'UTMEste': 340.0, 'UTMNorte': 5.0},
        {'CodTramoBT': 'B2', 'SecVertice': 1, 'UTMEste': 340.0, 'UTMNorte': 5.0},
        {'CodTramoBT': 'B2', 'SecVertice': 2, 'UTMEste': 340.0, 'UTMNorte': 14.0}]
    tablas['CB7_0'] = [{'CodSalidaBT': 'SB1', 'CodSed': 'E1', 'EtiquetaSalida': 'F1', 'Cantidad': 3}]
    return tablas


def test_leer_datos_lee_los_tramos_bt_solo_si_se_piden():
    """080:RF-55 — las tablas BT se hallan por sus campos y se leen solo con ``con_bt``.

    La conversión a DIgSILENT no las usa: leerlas siempre cargaría la red BT entera en memoria.
    La tabla de reportes con ``CodSalidaBT`` y ``CodSed`` no pasa por salida BT.
    """
    motor = Motor(tablas=_tablas_con_bt())
    sin_bt = sv.leer_datos(motor.conectar('red'))
    assert sin_bt.tramos_bt == [] and sin_bt.vertices_bt == [] and sin_bt.salidas_bt == []
    assert not any('btTramo' in s or 'verTramoBT' in s or 'btSalida' in s for s in motor.sql)

    con_bt = sv.leer_datos(Motor(tablas=_tablas_con_bt()).conectar('red'), con_bt=True)
    assert [t['CodTramoBT'] for t in con_bt.tramos_bt] == ['B1', 'B2', 'B3']
    assert len(con_bt.vertices_bt) == 5
    assert [(s['CodSalidaBT'], s['CodSed']) for s in con_bt.salidas_bt] == [('SB1', 'E1')]
    assert sv.tablas_por_campos({t: list(f[0]) for t, f in _tablas_con_bt().items()})['salida_bt'] == 'btSalida'


def test_modelo_canonico_lee_los_tramos_bt_de_sus_sed():
    """080:RF-55 — cada tramo BT entra al canónico con su SED, su salida BT y el alimentador de la SED.

    El estado y el tipo de red pasan por las mismas reglas que en MT, pero lo que no tiene regla se
    anota aparte (``valores_sin_regla_bt``): el puente a CYMDIST solo cuenta tramos MT. Un tramo BT
    sin vértices se anota; los de una SED de otra salida no entran cuando se pide una salida.
    """
    datos = sv.leer_datos(Motor(tablas=_tablas_con_bt()).conectar('red'), con_bt=True)
    modelo, avisos = sv.modelo_canonico(datos)
    bt = {t.section_id: t for t in modelo.sections_bt}
    assert set(bt) == {'B1', 'B2'}
    b1, b2 = bt['B1'], bt['B2']
    assert (b1.sed_id, b1.bt_feeder_id, b1.feeder_id, b1.parent_id) == ('E1', 'SB1', 'F1', '')
    assert b1.geometry == [(300.0, 5.0), (330.0, 5.0), (340.0, 5.0)] and b1.length_m == 40.0
    assert (b1.status, b1.overhead, b1.conductor_code, b1.source_status) == ('in_service', True, 'CAAI35', 'E')
    assert (b2.parent_id, b2.status, b2.overhead, b2.source_network_type) == ('B1', 'in_service', False, 'S')
    assert modelo.metadata['valores_sin_regla_bt'] == {'estado': {'Z': 1}}
    assert 'Z' not in (modelo.metadata.get('valores_sin_regla') or {}).get('estado', {})
    (sin_geo,) = [a for a in avisos if a['code'] == 'TRAMO_BT_SIN_GEOMETRIA']
    assert sin_geo['tramos'] == 1 and sin_geo['ejemplos'] == ['B3']
    assert {s.section_id for s in modelo.sections} == {'T1', 'T2', 'T3'}, 'la red MT no cambia'

    otra, _ = sv.modelo_canonico(datos, salidas=['OTRA'])
    assert otra.sections_bt == []


# --------------------------------------------------------------------------- escala (080:RF-59)
class _ListaQueCuenta(list):
    """Una tabla que cuenta cuántas veces se recorre entera."""

    def __init__(self, filas, cuenta, nombre):
        super().__init__(filas)
        self._cuenta, self._nombre = cuenta, nombre

    def __iter__(self):
        self._cuenta[self._nombre] += 1
        return super().__iter__()


def _red_de_salidas(k):
    """La salida de ejemplo repetida ``k`` veces, cada copia con sus códigos, y una salida sin tramos con su SED."""
    base = _tablas()
    tablas = {n: list(f) for n, f in base.items()
              if n not in ('mtSalida', 'mtTramo', 'verTramoMT', 'Sed', 'mtNodoEnlace', 'mtEquipo')}
    for n in ('mtSalida', 'mtTramo', 'verTramoMT', 'Sed', 'mtNodoEnlace', 'mtEquipo'):
        tablas[n] = []
    claves = ('CodSalidaMT', 'EtiquetaSalida', 'CodTramoMT', 'CodTramoMTPadre', 'CodSed', 'CodNodoMT', 'CodEqp')
    for i in range(k):
        for n in ('mtSalida', 'mtTramo', 'verTramoMT', 'Sed', 'mtNodoEnlace', 'mtEquipo'):
            for f in base[n]:
                tablas[n].append({c: (f'{v}_{i}' if c in claves and v else v) for c, v in f.items()})
        # 080:RF-32: una salida sin tramos con una SED ubicada (la rama que mira las normas de su tensión).
        tablas['mtSalida'].append({'CodSalidaMT': f'G_{i}', 'CodSet': 'S1', 'CodTenNomi': 'D',
                                   'EtiquetaSalida': f'G_{i}', 'CodSisElectrico': 'SE1'})
        tablas['Sed'].append({'CodSed': f'EG_{i}', 'CodSalidaMT': f'G_{i}', 'PotInstalada': 100.0,
                              'UTMEste': 500.0 + i, 'UTMNorte': 5.0, 'MaxDemTotal': 50.0})
    return tablas


def _recorridos(k):
    from collections import Counter

    datos, _ = _datos(_red_de_salidas(k))
    cuenta: Counter = Counter()
    for nombre in ('salidas', 'tramos', 'vertices', 'seds', 'enlaces', 'equipos', 'normas'):
        setattr(datos, nombre, _ListaQueCuenta(getattr(datos, nombre), cuenta, nombre))
    modelo, _avisos = sv.modelo_canonico(datos)
    assert len(modelo.sources) == 2 * k, 'todas las salidas, también las de solo una SED'
    return cuenta


def test_modelo_canonico_no_recorre_las_tablas_por_cada_salida():
    """080:RF-59 — las tablas de la copia se recorren un número fijo de veces, no una vez por salida (O(F·N)).

    Medir tiempos no lo detecta con una red pequeña; contar los recorridos sí: con 2 y con 6 copias de la red
    (cada una con su salida sin tramos), cada tabla se recorre las mismas veces."""
    pocas, muchas = _recorridos(2), _recorridos(6)
    crecen = {t: (pocas[t], muchas[t]) for t in muchas if muchas[t] != pocas[t]}
    assert not crecen, f'tablas recorridas una vez por salida (2 → 6 copias): {crecen}'


def _red_de_equivalencia():
    """080:RF-59: la red de la prueba de equivalencia, con los casos en los que un índice podría cambiar el resultado.

    - Tres copias de la salida de ejemplo, cada una con su salida sin tramos.
    - Un equipo con el mismo ``CodEqp`` en tramos de dos salidas distintas.
    - Una SED con el mismo ``CodSed`` en dos salidas.
    - Una salida repetida en ``mtSalida``: vale la primera fila, como con el ``next`` de antes.
    """
    tablas = _red_de_salidas(3)
    otro = dict(tablas['mtEquipo'][0])
    otro.update({'CodEqp': tablas['mtEquipo'][3]['CodEqp'], 'CodTramoMT': 'T1_2', 'UTMEste': 2.0})
    tablas['mtEquipo'].append(otro)
    sed = dict(tablas['Sed'][0])
    sed.update({'CodSalidaMT': 'F1_1', 'UTMEste': 150.0, 'MaxDemTotal': 33.0})
    tablas['Sed'].append(sed)
    repetida = dict(tablas['mtSalida'][0])
    repetida.update({'CodSet': 'S_OTRA', 'CodTenNomi': 'G'})
    tablas['mtSalida'].append(repetida)
    return tablas


def _modelo_en_json(modelo, avisos):
    """El modelo canónico y lo anotado como JSON canónico: claves ordenadas, tuplas como listas."""
    import dataclasses
    import json

    return json.dumps({'modelo': dataclasses.asdict(modelo), 'avisos': avisos},
                      sort_keys=True, ensure_ascii=False, indent=1, default=str)


REFERENCIA_EQUIVALENCIA = Path(__file__).parent / 'fixtures' / 'vnr_sqlserver_modelo_antes_rf59.json'


def test_los_indices_por_salida_dan_el_mismo_modelo_que_antes():
    """080:RF-59 — los índices por salida no cambian nada: el modelo canónico y sus avisos son, byte a byte, los que
    daba el lector anterior (51895566 + H2+H3, guardados en ``fixtures/vnr_sqlserver_modelo_antes_rf59.json``) sobre
    una red con un equipo de código repetido, una SED en dos salidas y una salida repetida."""
    datos, _ = _datos(_red_de_equivalencia())
    actual = _modelo_en_json(*sv.modelo_canonico(datos))
    assert actual == REFERENCIA_EQUIVALENCIA.read_text(encoding='utf-8')


# --------------------------------------------------------------------------- memoria de la red BT (080:RF-60)
SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
#: 080:RF-60: lo que puede crecer la memoria por cada salida BT de más que NO se pide, con sus tramos y sus vértices.
#: De ella solo queda dónde cae su SED: su código y un entero en un diccionario, de 135 a 220 bytes medidos. Antes se
#: guardaban todas sus filas como diccionarios: unos 4,1 KB por salida BT en esta red, con sus tramos y vértices.
BYTES_POR_SALIDA_BT_NO_PEDIDA = 256

_CAMPOS_BT = {
    'btSalida': ('CodSalidaBT', 'CodSed', 'EtiquetaSalida', 'CodTenNomi3', 'UTMEste', 'UTMNorte'),
    'btTramo': ('CodTramoBT', 'CodSalidaBT', 'CodTramoBTPadre', 'CodNormaFase', 'CodTipoRed', 'Longitud',
                'EstadoVNR'),
    'verTramoBT': ('CodTramoBT', 'SecVertice', 'UTMEste', 'UTMNorte'),
}


class _EmpresaSintetica:
    """La salida de ejemplo F1, que es la que se pide, y otra salida F2 con ``sed`` SED, con la red BT generada fila a
    fila al leerla, como la da el motor: ``pedidas`` salidas BT en la SED de F1 con ``tramos`` tramos cada una, y
    ``otras`` salidas BT en las SED de F2 (una de cada diez, en una SED que no está en la copia), de 1 a 5 tramos y de
    1 a 4 vértices cada uno. Cada fila trae sus propios textos y la tabla no ocupa memoria antes de leerla."""

    def __init__(self, pedidas: int, tramos: int, otras: int, sed: int = 5):
        self.pedidas, self.tramos, self.otras, self.sed = pedidas, tramos, otras, sed
        fijas = _tablas()
        fijas['mtSalida'].append({'CodSalidaMT': 'F2', 'CodSet': 'S1', 'CodTenNomi': 'D', 'EtiquetaSalida': 'F2',
                                  'CodSisElectrico': 'SE1'})
        fijas['Sed'] += [{'CodSed': f'EO{k}', 'CodSalidaMT': 'F2', 'PotInstalada': 100.0, 'UTMEste': 900.0 + k,
                          'UTMNorte': 5.0, 'MaxDemTotal': 50.0} for k in range(sed)]
        self.fijas = fijas

    def _salidas(self):
        for j in range(self.pedidas):
            yield {'CodSalidaBT': f'SBP{j}', 'CodSed': 'E1', 'EtiquetaSalida': f'P{j}', 'CodTenNomi3': 'B',
                   'UTMEste': 300.0, 'UTMNorte': 5.0}
        for i in range(self.otras):
            yield {'CodSalidaBT': f'SBO{i}', 'CodSed': f'EO{i % self.sed}' if i % 10 else f'XX{i}',
                   'EtiquetaSalida': f'C{i}', 'CodTenNomi3': 'B', 'UTMEste': 900.0, 'UTMNorte': 5.0}

    def _codigos(self):
        """(tramo, salida BT, vértices), en el orden de la tabla."""
        for j in range(self.pedidas):
            for t in range(self.tramos):
                yield f'BP{j}_{t}', f'SBP{j}', 2 + (j + t) % 3
        for i in range(self.otras):
            for t in range(1 + i % 5):
                yield f'BO{i}_{t}', f'SBO{i}', 1 + (i + t) % 4

    def _tramos(self):
        for cod, salida, _n in self._codigos():
            yield {'CodTramoBT': cod, 'CodSalidaBT': salida, 'CodTramoBTPadre': '', 'CodNormaFase': 'CAAI35',
                   'CodTipoRed': 'A', 'Longitud': 10.0, 'EstadoVNR': 'E'}

    def _vertices(self):
        for cod, _salida, n in self._codigos():
            for k in range(n):
                yield {'CodTramoBT': cod, 'SecVertice': k + 1, 'UTMEste': 300.0 + 10.0 * k, 'UTMNorte': 5.0}

    def filas_de_vertices(self) -> int:
        return sum(n for _c, _s, n in self._codigos())

    def tablas(self) -> dict:
        """Nombre → (campos, función que da sus filas)."""
        out = {n: (tuple(filas[0]), lambda filas=filas: iter(filas)) for n, filas in self.fijas.items()}
        out['btSalida'] = (_CAMPOS_BT['btSalida'], self._salidas)
        out['btTramo'] = (_CAMPOS_BT['btTramo'], self._tramos)
        out['verTramoBT'] = (_CAMPOS_BT['verTramoBT'], self._vertices)
        return out


class _MotorQueAnota:
    """Un SQL Server de mentira que da las filas a medida que se piden y anota cada consulta con sus parámetros y
    cómo se leyeron sus filas: ``(tabla, 'fetchall' | 'fetchmany', tamaño, sql)``."""

    def __init__(self, tablas: dict):
        self.tablas = tablas
        self.consultas: list[tuple[str, tuple]] = []
        self.lecturas: list[tuple] = []
        #: Lo que responde a cada ``SELECT COUNT(*)``.
        self.cuenta = 0

    def conectar(self, *_args, **_kw):
        motor = self

        class _Conexion:
            def cursor(self):
                return _CursorQueAnota(motor)

            def close(self):
                pass

        return _Conexion()


class _CursorQueAnota:
    def __init__(self, motor: _MotorQueAnota):
        self.motor, self.tabla, self.sql, self._filas = motor, None, '', iter(())

    def execute(self, sql, *params):
        self.motor.consultas.append((sql, params))
        self.sql, self.tabla = sql, None
        if sql.startswith('SELECT state_desc FROM sys.databases'):
            self._filas = iter([('ONLINE',)])
        elif 'INFORMATION_SCHEMA.COLUMNS' in sql:
            self._filas = iter([(t, c) for t, (campos, _f) in self.motor.tablas.items() for c in campos])
        elif sql.startswith('SELECT COUNT(*) FROM ['):
            self._filas = iter([(self.motor.cuenta,)])
        elif sql.startswith('SELECT ['):
            self.tabla = sql.rsplit('FROM [', 1)[1].split(']', 1)[0]
            campos = [c.strip('[] ') for c in sql[len('SELECT '):sql.index(' FROM')].split(',')]
            self._filas = (tuple(f.get(c) for c in campos) for f in self.motor.tablas[self.tabla][1]())
        else:
            raise AssertionError(f'SQL inesperado: {sql}')
        return self

    def fetchone(self):
        return next(self._filas, None)

    def fetchall(self):
        self.motor.lecturas.append((self.tabla, 'fetchall', None, self.sql))
        return list(self._filas)

    def fetchmany(self, n):
        self.motor.lecturas.append((self.tabla, 'fetchmany', n, self.sql))
        return list(itertools.islice(self._filas, n))


def _leer_por_la_web(monkeypatch, conectar, salidas):
    """La lectura de una base ya restaurada que usa el paquete de capas (``leer_base_restaurada``), con la red BT."""
    _exige_capas()
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import leer_base_restaurada

    monkeypatch.setattr(sv, 'conectar', conectar)
    return leer_base_restaurada('CSG_VNR_SINTETICA', salidas=salidas, con_bt=True)


def test_memoria_de_la_red_bt_no_crece_con_las_salidas_que_no_se_piden(monkeypatch):
    """080:RF-60 — con 4N salidas BT de otras salidas MT, el pico de memoria (tracemalloc) de leer una salida con su
    red BT no pasa de 1,1 veces el de N más ``BYTES_POR_SALIDA_BT_NO_PEDIDA`` por cada salida BT de más. Antes,
    ``leer_datos(con_bt=True)`` guardaba btTramo, verTramoBT y btSalida enteras aunque se pidieran tres salidas, así
    que la memoria crecía con la empresa. Salidas, tramos y tamaño, sorteados."""
    import gc
    import tracemalloc

    rng = random.Random(SEMILLA)
    pedidas, tramos, n = rng.randint(2, 4), rng.randint(5, 15), rng.randint(2000, 3000)

    def pico(otras: int) -> int:
        motor = _MotorQueAnota(_EmpresaSintetica(pedidas, tramos, otras).tablas())
        gc.collect()
        tracemalloc.start()
        try:
            modelo, _avisos = _leer_por_la_web(monkeypatch, motor.conectar, ['F1'])
            medido = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert len(modelo.sections_bt) == pedidas * tramos, 'la red BT de la salida pedida, entera'
        assert {t.feeder_id for t in modelo.sections_bt} == {'F1'}
        return medido

    # Una lectura pequeña antes de medir: lo que se importa la primera vez (psutil) no cuenta en el pico de N.
    _leer_por_la_web(monkeypatch, _MotorQueAnota(_EmpresaSintetica(1, 1, 1).tablas()).conectar, ['F1'])
    uno, cuatro = pico(n), pico(4 * n)
    cota = int(1.1 * uno) + 3 * n * BYTES_POR_SALIDA_BT_NO_PEDIDA
    assert cuatro <= cota, (f'pico con {4 * n} salidas BT no pedidas: {cuatro / 2**20:.2f} MB; con {n}: '
                            f'{uno / 2**20:.2f} MB; cota {cota / 2**20:.2f} MB (semilla {SEMILLA})')


def test_la_red_bt_no_se_lee_entera_de_una_vez(monkeypatch):
    """080:RF-60 — btSalida, btTramo y verTramoBT se leen por bloques (``fetchmany``) de un tamaño que no depende de
    la empresa, o con un WHERE con parámetros; nunca con un ``fetchall`` de la tabla entera, y la salida pedida no se
    escribe en el texto del SQL. El doble del motor anota cada consulta, sus parámetros y cómo se leyó."""
    rng = random.Random(SEMILLA)
    n = rng.randint(1500, 2500)
    bloques = {}
    for otras in (n, 4 * n):
        empresa = _EmpresaSintetica(2, 5, otras)
        motor = _MotorQueAnota(empresa.tablas())
        _leer_por_la_web(monkeypatch, motor.conectar, ['F1'])
        bt = [x for x in motor.lecturas if x[0] in _CAMPOS_BT]
        enteras = sorted({t for t, modo, _k, sql in bt if modo == 'fetchall' and ' WHERE ' not in sql.upper()})
        assert not enteras, f'tablas BT leídas enteras de una vez: {enteras} ({otras} salidas BT de otras salidas)'
        assert {x[0] for x in bt} == set(_CAMPOS_BT), 'se leen las tres tablas BT'
        assert not [sql for sql, _p in motor.consultas if 'F1' in sql], 'la salida pedida va en parámetros, no en SQL'
        bloques[otras] = {k for _t, modo, k, _sql in bt if modo == 'fetchmany'}
        assert all(k < empresa.filas_de_vertices() for k in bloques[otras]), bloques
    assert bloques[n] == bloques[4 * n], f'el bloque cambia con la empresa: {bloques}'


def test_la_lectura_bt_avisa_si_su_memoria_estimada_no_cabe(monkeypatch):
    """080:RF-60 — antes de leer la red BT, su memoria se estima con las filas de las salidas pedidas contadas en el
    motor (``COUNT``, con las salidas como parámetros) por los bytes por fila medidos. Si no cabe en la memoria libre
    sale el aviso ``MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE`` con las filas, los bytes estimados y los libres, y la lectura
    sigue; si cabe, no sale. Antes se leía a ciegas."""
    import types

    import psutil

    libres = 1 << 30
    monkeypatch.setattr(psutil, 'virtual_memory', lambda: types.SimpleNamespace(available=libres))

    def leer_con(cuenta):
        motor = _MotorQueAnota(_EmpresaSintetica(2, 5, 50).tablas())
        motor.cuenta = cuenta
        modelo, avisos = _leer_por_la_web(monkeypatch, motor.conectar, ['F1'])
        return [a for a in avisos if a['code'] == 'MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE'], modelo, motor

    grande, modelo, motor = leer_con(10**8)
    assert len(grande) == 1, f'sin aviso con 10^8 filas BT y {libres / 2**20:.0f} MB libres'
    (aviso,) = grande
    assert aviso['bytes_libres'] == libres and aviso['bytes_estimados'] > libres, aviso
    assert aviso['filas']['tramos'] == 10**8 and aviso['filas']['vertices'] == 10**8, aviso
    assert len(modelo.sections_bt) == 10, 'es un aviso: la red BT se lee igual'
    cuentas = [(sql, params) for sql, params in motor.consultas if sql.startswith('SELECT COUNT(')]
    assert not [sql for sql, _p in cuentas if 'F1' in sql], 'la salida pedida va en parámetros, no en el SQL'
    assert any('F1' in params for _sql, params in cuentas), cuentas

    pequeno, _modelo, _motor = leer_con(10)
    assert pequeno == [], pequeno


def _red_bt_enrevesada(rng):
    """080:RF-60: la red de la prueba de igualdad, con los casos en los que leer por bloques podría cambiar algo.

    - Dos copias de la salida de ejemplo (F1_0, F1_1, la segunda con un código operativo distinto) y sus salidas
      sin tramos (G_0, G_1), cada una con su SED.
    - Salidas BT repetidas que acaban en otra SED (manda la última fila), con espacios o sin SED.
    - Tramos cuya salida BT no está en btSalida, con el código repetido, vacío o con espacios, y más de 20 tramos sin
      salida MT, en cualquier orden.
    - Vértices sin coordenadas, desordenados o de tramos que no existen.
    """
    tablas = _red_de_salidas(2)
    tablas['mtSalida'][1]['EtiquetaSalida'] = 'OPER1'
    seds = ['E1_0', 'E1_1', 'EG_0', 'EG_1', 'NO_ESTA', None, ' E1_0 ']
    salidas_bt = [{'CodSalidaBT': f'SB{i}', 'CodSed': rng.choice(seds), 'EtiquetaSalida': f'C{i}',
                   'CodTenNomi3': 'B'} for i in range(rng.randint(15, 30))]
    for _ in range(rng.randint(3, 8)):
        repetida = dict(rng.choice(salidas_bt))
        repetida['CodSed'] = rng.choice(seds)
        salidas_bt.insert(rng.randrange(len(salidas_bt) + 1), repetida)
    salidas_bt.append({'CodSalidaBT': ' SB0 ', 'CodSed': 'E1_1', 'EtiquetaSalida': 'C', 'CodTenNomi3': 'B'})
    codigos_bt = [s['CodSalidaBT'] for s in salidas_bt] + ['SB_SIN_FILA', None, '']
    tramos = []
    for i in range(rng.randint(60, 120)):
        cod = rng.choice([f'BT{rng.randrange(10**4):04d}', f'BT{i:04d}', f'  BT{i:04d}', None])
        tramos.append({'CodTramoBT': cod, 'CodSalidaBT': rng.choice(codigos_bt),
                       'CodTramoBTPadre': rng.choice(['', None, f'BT{rng.randrange(i + 1):04d}']),
                       'CodNormaFase': rng.choice(['CAAI35', 'NYY16']), 'CodTipoRed': rng.choice(['A', 'S', 'Q']),
                       'Longitud': rng.uniform(1, 80), 'EstadoVNR': rng.choice(['E', 'P', 'Z', None])})
    tramos += [{'CodTramoBT': f'HZ{rng.randrange(10**4):04d}', 'CodSalidaBT': 'NO_HAY', 'CodTramoBTPadre': '',
                'CodNormaFase': 'CAAI35', 'CodTipoRed': 'A', 'Longitud': 5.0, 'EstadoVNR': 'E'}
               for _ in range(rng.randint(21, 40))]
    rng.shuffle(tramos)
    vertices = []
    for t in tramos + [{'CodTramoBT': 'NO_EXISTE'}]:
        for k in rng.sample(range(1, 6), rng.randint(0, 4)):
            vertices.append({'CodTramoBT': t['CodTramoBT'], 'SecVertice': k,
                             'UTMEste': None if rng.random() < 0.05 else rng.uniform(0, 500),
                             'UTMNorte': rng.uniform(0, 50)})
    rng.shuffle(vertices)
    tablas.update({'btSalida': salidas_bt, 'btTramo': tramos, 'verTramoBT': vertices})
    return tablas


def _datos_con_las_tablas_bt_enteras(tablas):
    """Lo que daba ``leer_datos(con_bt=True)`` antes de 080:RF-60: las tres tablas BT enteras, como diccionarios."""
    datos, _ = _datos({n: f for n, f in tablas.items() if n not in _CAMPOS_BT})
    datos.salidas_bt = [dict(f) for f in tablas['btSalida']]
    datos.tramos_bt = [dict(f) for f in tablas['btTramo']]
    datos.vertices_bt = [dict(f) for f in tablas['verTramoBT']]
    return datos


def test_la_red_bt_por_bloques_da_el_mismo_modelo_que_las_tablas_enteras(monkeypatch):
    """080:RF-60 — leer la red BT por bloques y guardar solo la de las salidas pedidas no cambia nada: la huella
    sha256 del modelo canónico y sus avisos, serializados con las claves ordenadas, es la de leer las tablas enteras,
    con todas las salidas, con una, con otra por su código operativo, con dos, con espacios y con una que no existe.
    Pedir después a ``modelo_canonico`` una salida cuya red BT no se leyó es un error, no una red BT vacía."""
    import hashlib

    def huella(modelo, avisos):
        return hashlib.sha256(_modelo_en_json(modelo, avisos).encode('utf-8')).hexdigest()

    rng = random.Random(SEMILLA)
    tablas = _red_bt_enrevesada(rng)
    enteras = _datos_con_las_tablas_bt_enteras(tablas)
    motor = Motor(bases=['CSG_VNR_SINTETICA'], tablas=tablas)
    vistos = set()
    for salidas in (None, ['F1_0'], ['OPER1'], ['F1_0', 'G_1'], [' F1_1 ', 'EG_0'], ['NO_EXISTE']):
        antes = sv.modelo_canonico(enteras, salidas)
        ahora = _leer_por_la_web(monkeypatch, lambda *a, **k: Conexion(motor, ''), salidas)
        assert huella(*ahora) == huella(*antes), f'salidas {salidas}, semilla {SEMILLA}'
        vistos |= {a['code'] for a in ahora[1]} | ({'BT'} if ahora[0].sections_bt else set())
    assert {'BT', 'TRAMO_BT_SIN_SALIDA_MT', 'TRAMO_BT_SIN_GEOMETRIA'} <= vistos, f'red sin sus casos: {vistos}'

    datos = sv.leer_datos(Conexion(motor, ''), con_bt=True, salidas=['F1_0'])
    with pytest.raises(ValueError, match='red BT'):
        sv.modelo_canonico(datos, ['F1_1'])


# --------------------------------------------------------------------------- red BT en flujo (080:RF-60, MEM-BT v2)
#: 080:RF-60 (MEM-BT v2): lo que la cadena entera en flujo puede crecer, además del 10 %, al pasar de N a 4N salidas MT.
#: Sigue en memoria lo de cada salida MT (MEM-MT: su fila, su código operativo y su estructura; con la v2, su red MT
#: entera): en la empresa de la prueba, con dos tramos, una SED y su enlace por salida, medidos en 2,5–4 KB; se toman
#: 8 KB. Y la caché de páginas del SQLite
#: temporal (``cache_size=-8192``, 8 MiB), que puede no llenarse con N y sí con 4N. La red BT no cuenta: va por piezas
#: de tamaño fijo. En la vía de antes, cada tramo BT de más ocupaba unos 2,2 KB en la cadena entera.
BYTES_MT_POR_SALIDA = 8 * 1024
CACHE_DEL_SQLITE = 8 * 2**20
RAIZ = Path(__file__).resolve().parents[1]


def _pico_de_la_cadena(tmp_path, salidas: int, tramos: int, semilla: int, *, tramos_mt: int = 2,
                       rica: bool = False) -> dict:
    """080:RF-60: el pico de memoria (``peak_wset``) y el tiempo de la cadena entera del CLI ``bak-a-capas`` (lectura,
    modelo y GeoPackage), en un proceso hijo nuevo, sobre la empresa sintética de ``salidas`` × ``tramos`` tramos BT
    (MEM-MT: y ``tramos_mt`` tramos MT por salida, con los casos de la red MT si ``rica``)."""
    import json
    import subprocess
    import sys

    carpeta = tmp_path / f'cadena_{salidas}_{tramos_mt}'
    carpeta.mkdir()
    entorno = dict(os.environ, CUDA_VISIBLE_DEVICES='-1', PYTHONPATH=str(RAIZ / 'src'),
                   CSG_RUNTIME_HOME=str(carpeta / 'runtime'), CSG_CACHE_HOME=str(carpeta / 'cache'))
    hijo = subprocess.run([sys.executable, str(RAIZ / 'tests' / 'vnr_bt_sintetica.py'), str(RAIZ / 'src'),
                           str(salidas), str(tramos), str(semilla), str(carpeta / 'red.gpkg'), '-', str(tramos_mt),
                           'rica' if rica else 'simple'],
                          capture_output=True, text=True, encoding='utf-8', env=entorno, timeout=1200, check=False)
    medidas = [x for x in hijo.stdout.splitlines() if x.startswith('MEDIDA ')]
    assert hijo.returncode == 0 and medidas, f'el proceso hijo falló (rc={hijo.returncode}): {hijo.stderr[-2000:]}'
    return json.loads(medidas[-1][len('MEDIDA '):])


def test_la_cadena_entera_no_crece_con_la_red_bt_de_la_empresa(tmp_path):
    """080:RF-60 (MEM-BT v2) — el pico de memoria de la cadena ENTERA del CLI ``bak-a-capas`` (lectura de la base,
    modelo canónico y GeoPackage), medido como ``peak_wset`` de un proceso hijo nuevo, no pasa con 4N salidas MT de
    1,1 veces el de N más lo que crece la red MT (``BYTES_MT_POR_SALIDA`` por salida de más) y la caché del SQLite
    temporal.

    Antes, con todas las salidas, el CLI armaba el canónico entero (MT y BT) y lo escribía de una vez: el pico crecía
    con la red BT de la empresa (en una distribuidora, 1,4 GiB). En flujo, la red BT va al disco y se arma y se escribe
    por lotes de salidas, y el GeoPackage es el mismo. Salidas, tramos BT por salida y semilla, sorteados."""
    rng = random.Random(SEMILLA)
    n, tramos = rng.randint(30, 50), rng.randint(400, 600)
    uno = _pico_de_la_cadena(tmp_path, n, tramos, SEMILLA % 1000)
    cuatro = _pico_de_la_cadena(tmp_path, 4 * n, tramos, SEMILLA % 1000)
    cota = int(1.1 * uno['pico']) + 3 * n * BYTES_MT_POR_SALIDA + CACHE_DEL_SQLITE
    assert cuatro['pico'] <= cota, (
        f'pico de la cadena con {4 * n} salidas ({4 * n * tramos} tramos BT): {cuatro["pico"] / 2**20:.1f} MiB; '
        f'con {n}: {uno["pico"] / 2**20:.1f} MiB; cota {cota / 2**20:.1f} MiB (semilla {SEMILLA})')


def _memoria_libre_falsa(monkeypatch, libres: int) -> None:
    import types

    import psutil

    monkeypatch.setattr(psutil, 'virtual_memory', lambda: types.SimpleNamespace(available=libres))


def test_el_aviso_de_memoria_bt_se_ve_en_el_registro(monkeypatch, caplog):
    """080:RF-60 (MEM-BT v2) — el aviso de memoria por COUNT no se queda en la lista de avisos: deja en el registro
    (``logging.warning``) la línea «estimado X GiB, libre Y GiB», y la misma línea va en el aviso. Antes, el aviso solo
    iba en la lista y nadie lo veía hasta abrir el modelo."""
    import logging
    import re

    _memoria_libre_falsa(monkeypatch, 1 << 30)
    caplog.set_level(logging.INFO, logger=sv.__name__)
    motor = _MotorQueAnota(_EmpresaSintetica(2, 5, 50).tablas())
    motor.cuenta = 10**8
    _modelo, avisos = _leer_por_la_web(monkeypatch, motor.conectar, ['F1'])
    lineas = [r.getMessage() for r in caplog.records if r.name == sv.__name__ and r.levelno >= logging.WARNING]
    assert any(re.search(r'estimado \d+\.\d\d GiB, libre 1\.00 GiB', x) for x in lineas), (
        f'sin línea de aviso en el registro: {lineas}')
    (aviso,) = [a for a in avisos if a['code'] == 'MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE']
    assert aviso['linea'] in lineas, aviso


def test_el_cli_bak_a_capas_imprime_la_estimacion_de_memoria(monkeypatch, tmp_path, capsys):
    """080:RF-60 (MEM-BT v2) — el CLI ``bak-a-capas`` imprime en la pantalla, antes del resumen, la estimación de
    memoria y de disco de la red BT con «estimado X GiB, libre Y GiB» y, si no cabe, el aviso con su código. Con 10⁸
    filas BT contadas y 1 MiB libre de memoria y de disco salen los dos avisos; la exportación sigue (rc=0). Antes no
    imprimía nada de la memoria."""
    import re
    import shutil
    import types

    from convertersmartgrid.adaptadores.entrada.vnr import cli
    from vnr_bt_sintetica import EmpresaGrande, MotorSinMars

    _memoria_libre_falsa(monkeypatch, 1 << 20)
    monkeypatch.setattr(shutil, 'disk_usage', lambda *_a, **_k: types.SimpleNamespace(free=1 << 20))
    motor = MotorSinMars(EmpresaGrande(3, 5).tablas(), cuenta=10**8)
    monkeypatch.setattr(sv, 'conectar', motor.conectar)
    import inspect
    assert "'bak-a-capas'" in inspect.getsource(cli) or '"bak-a-capas"' in inspect.getsource(cli), (
        'el CLI de VNR no tiene el subcomando bak-a-capas (080 T15 a T17)')
    assert cli.main(['bak-a-capas', 'CSG_VNR_SINTETICA', str(tmp_path / 'red.gpkg')]) == 0
    salida = capsys.readouterr().out
    for codigo in ('MEMORIA_BT_ESTIMADA_SUPERA_LA_LIBRE', 'DISCO_BT_ESTIMADO_SUPERA_EL_LIBRE'):
        avisos = [x for x in salida.splitlines() if x.startswith(f'AVISO {codigo}')]
        assert avisos and re.search(r'estimado \d+\.\d\d GiB, libre 0\.00 GiB', avisos[0]), (
            f'el CLI no imprime {codigo} con su estimación: {salida[:800]}')
        assert salida.index(avisos[0]) < salida.index('"destino"'), 'la estimación va antes del resumen'
    assert (tmp_path / 'red.gpkg').is_file(), 'es un aviso: el GeoPackage se escribe igual'


def test_la_exportacion_en_flujo_da_el_mismo_geopackage(monkeypatch, tmp_path):
    """080:RF-60 (MEM-BT v2) — exportar la base en flujo (la red MT entera una vez, la BT por lotes de salidas) da el
    MISMO GeoPackage que la vía de antes con el canónico entero: las mismas tablas, índices y disparadores, y en cada
    capa su fila de ``gpkg_contents`` (con su extensión), su geometría, su esquema, el número de filas y la sha256 de
    sus filas ordenadas. También los mismos avisos y los mismos valores BT sin regla. Sobre la red enrevesada y una
    empresa sintética, con lotes de 1, 2 y 1 000 salidas, piezas de 3, 7 y 5 000 tramos, y con y sin pyarrow."""
    _exige_capas()
    from convertersmartgrid.adaptadores.entrada.vnr.exporters import capas
    from vnr_bt_sintetica import EmpresaGrande, MotorSinMars, huella_gpkg

    con_arrow = capas._arrow
    assert con_arrow() is not None, 'pyarrow y pyogrio.write_arrow, en el entorno de las pruebas'

    rng = random.Random(SEMILLA)
    enrevesada = Motor(bases=['CSG_VNR_SINTETICA'], tablas=_red_bt_enrevesada(random.Random(SEMILLA)))
    empresa = MotorSinMars(EmpresaGrande(rng.randint(5, 12), rng.randint(5, 20), SEMILLA).tablas())
    redes = {'enrevesada': lambda *a, **k: Conexion(enrevesada, ''), 'empresa': empresa.conectar}
    vistas = set()
    for nombre, conectar in redes.items():
        monkeypatch.setattr(sv, 'conectar', conectar)
        antes = capas.exportar_copia_a_capas('CSG_VNR_SINTETICA', tmp_path / f'{nombre}_antes.gpkg')[1]
        _modelo, avisos_antes = capas.leer_base_restaurada('CSG_VNR_SINTETICA')
        referencia = huella_gpkg(tmp_path / f'{nombre}_antes.gpkg')
        assert referencia['capas']['Tramo_BT']['filas'] > 0, 'la red tiene tramos BT'
        for lote, pieza, sin_arrow in ((1, 3, False), (2, 7, True), (1000, 5000, False)):
            monkeypatch.setattr(sv, 'TRAMOS_BT_POR_PIEZA', pieza)
            monkeypatch.setattr(capas, '_arrow', (lambda: None) if sin_arrow else con_arrow)
            destino = tmp_path / f'{nombre}_{lote}.gpkg'
            hecho = capas.exportar_base_a_capas_en_flujo('CSG_VNR_SINTETICA', None, destino, lote_salidas=lote)
            caso = f'{nombre}, lote {lote}, pieza {pieza}, {hecho.escritura} (semilla {SEMILLA})'
            assert huella_gpkg(destino) == referencia, f'otro GeoPackage: {caso}'
            assert hecho.avisos == avisos_antes, f'otros avisos: {caso}'
            assert hecho.metadata.get('valores_sin_regla_bt') == antes.metadata.get('valores_sin_regla_bt'), caso
            assert hecho.tramos_bt == referencia['capas']['Tramo_BT']['filas'], caso
            vistas.add(hecho.escritura)
            vistas |= {a['code'] for a in hecho.avisos if a['code'].startswith('TRAMO_BT')}
    assert vistas >= {'arrow', 'por añadidos', 'TRAMO_BT_SIN_SALIDA_MT', 'TRAMO_BT_SIN_GEOMETRIA'}, vistas


def test_la_exportacion_en_flujo_lee_cada_tabla_una_vez(monkeypatch, tmp_path):
    """080:RF-60 (MEM-BT v2) — en flujo no hay una consulta por salida ni por lote: con N y con 4N salidas MT se hacen
    las mismas consultas, cada tabla BT se pide una sola vez, por bloques del mismo tamaño (``fetchmany``) y nunca con
    ``fetchall``, sin escribir ninguna salida en el SQL, y nunca hay dos consultas abiertas a la vez en la conexión
    (SQL Server sin MARS no lo deja: el doble del motor falla si pasa). Un lote de 0 salidas es un error."""
    from collections import Counter

    _exige_capas()
    from convertersmartgrid.adaptadores.entrada.vnr.exporters import capas
    from vnr_bt_sintetica import EmpresaGrande, MotorSinMars

    rng = random.Random(SEMILLA)
    n, tramos = rng.randint(10, 25), rng.randint(20, 60)
    consultas, bloques = {}, {}
    for salidas in (n, 4 * n):
        motor = MotorSinMars(EmpresaGrande(salidas, tramos, SEMILLA).tablas())
        monkeypatch.setattr(sv, 'conectar', motor.conectar)
        hecho = capas.exportar_base_a_capas_en_flujo('CSG_VNR_SINTETICA', None, tmp_path / f'r{salidas}.gpkg',
                                                     lote_salidas=2)
        assert hecho.lotes > 1, 'varios lotes'
        consultas[salidas] = sorted(sql for sql, _p in motor.consultas)
        bt = [x for x in motor.lecturas if x[0] in _CAMPOS_BT]
        assert not [x for x in bt if x[1] == 'fetchall'], 'una tabla BT leída con fetchall'
        por_tabla = Counter(sql for sql, _p in motor.consultas if sql.startswith('SELECT [')
                            and sql.rsplit('FROM [', 1)[1].split(']', 1)[0] in _CAMPOS_BT)
        assert sorted(por_tabla.values()) == [1, 1, 1], f'cada tabla BT, una vez: {por_tabla}'
        assert not [sql for sql, _p in motor.consultas if 'F000' in sql], 'ninguna salida en el texto del SQL'
        bloques[salidas] = {k for _t, modo, k, _sql in bt}
    assert consultas[n] == consultas[4 * n], 'las consultas cambian con el número de salidas'
    assert bloques[n] == bloques[4 * n] == {sv.FILAS_POR_BLOQUE}, bloques
    with pytest.raises(ValueError, match='lote'):
        capas.exportar_base_a_capas_en_flujo('CSG_VNR_SINTETICA', None, tmp_path / 'x.gpkg', lote_salidas=0)


# --------------------------------------------------------------------------- red MT en flujo (080:RF-60, MEM-MT)
#: 080:RF-60 (MEM-MT): las tablas de la red MT de la empresa sintética, con sus equipos.
_TABLAS_MT = ('empEmpresa', 'mtSalida', 'CentroTransformacion', 'mtTramo', 'verTramoMT', 'Sed', 'mtNodoEnlace',
              'mtEquipo', 'admCodigosNorma', 'cfgCodigoSecundario')
_TABLAS_MT_GRANDES = ('mtTramo', 'verTramoMT', 'Sed', 'mtNodoEnlace', 'mtEquipo')


def test_la_cadena_entera_no_crece_con_la_red_mt_de_la_empresa(tmp_path):
    """080:RF-60 (MEM-MT) — el pico de memoria de la cadena ENTERA del CLI ``bak-a-capas`` (``peak_wset`` de un proceso
    hijo nuevo) no pasa con 4N salidas MT de 1,1 veces el de N más ``BYTES_MT_POR_SALIDA`` por salida de más y la caché
    del SQLite temporal, con cientos de tramos MT por salida (y sus equipos, reguladores, bancos, salidas sin tramos y
    etiquetas repetidas).

    Con la v2, la red BT ya iba en flujo, pero la MT se leía entera de una vez (``fetchall``) y su canónico y sus capas
    se tenían enteros en memoria: el pico crecía con cada tramo MT de la empresa. En flujo, la red MT va al disco y su
    canónico se arma y sus capas se escriben por lotes de salidas: lo que queda por salida son su fila, su código y su
    estructura. Salidas, tramos MT por salida y semilla, sorteados."""
    rng = random.Random(SEMILLA)
    n, tramos_mt = rng.randint(30, 45), rng.randint(150, 250)
    uno = _pico_de_la_cadena(tmp_path, n, 20, SEMILLA % 1000, tramos_mt=tramos_mt, rica=True)
    cuatro = _pico_de_la_cadena(tmp_path, 4 * n, 20, SEMILLA % 1000, tramos_mt=tramos_mt, rica=True)
    assert uno['huella'] != cuatro['huella'], 'dos redes distintas'
    cota = int(1.1 * uno['pico']) + 3 * n * BYTES_MT_POR_SALIDA + CACHE_DEL_SQLITE
    assert cuatro['pico'] <= cota, (
        f'pico de la cadena con {4 * n} salidas ({4 * n * tramos_mt} tramos MT): {cuatro["pico"] / 2**20:.1f} MiB; '
        f'con {n}: {uno["pico"] / 2**20:.1f} MiB; cota {cota / 2**20:.1f} MiB (semilla {SEMILLA})')


def test_la_red_mt_en_flujo_se_lee_por_bloques(monkeypatch, tmp_path):
    """080:RF-60 (MEM-MT) — en flujo, ninguna tabla de la red se lee con ``fetchall``: todas, también las de la red MT,
    se piden una sola vez y por bloques de ``FILAS_POR_BLOQUE`` filas (``fetchmany``), sin una consulta por salida ni
    por lote (las mismas consultas con N y con 4N salidas), y nunca hay dos consultas abiertas a la vez (el doble del
    motor, como SQL Server sin MARS, falla si pasa). Con la v2, las tablas MT se leían enteras con ``fetchall``."""
    from collections import Counter

    _exige_capas()
    from convertersmartgrid.adaptadores.entrada.vnr.exporters import capas
    from vnr_bt_sintetica import EmpresaGrande, MotorSinMars

    rng = random.Random(SEMILLA)
    n, tramos_mt = rng.randint(10, 25), rng.randint(3, 12)
    consultas, bloques = {}, {}
    for salidas in (n, 4 * n):
        motor = MotorSinMars(EmpresaGrande(salidas, 5, SEMILLA, tramos_mt, True).tablas())
        monkeypatch.setattr(sv, 'conectar', motor.conectar)
        capas.exportar_base_a_capas_en_flujo('CSG_VNR_SINTETICA', None, tmp_path / f'mt{salidas}.gpkg', lote_salidas=2)
        enteras = sorted({x[0] for x in motor.lecturas if x[1] == 'fetchall' and x[0] is not None})
        assert not enteras, f'tablas leídas enteras con fetchall: {enteras}'
        por_tabla = Counter(sql.rsplit('FROM [', 1)[1].split(']', 1)[0] for sql, _p in motor.consultas
                            if sql.startswith('SELECT ['))
        assert {t: por_tabla[t] for t in _TABLAS_MT_GRANDES} == dict.fromkeys(_TABLAS_MT_GRANDES, 1), por_tabla
        consultas[salidas] = sorted(sql for sql, _p in motor.consultas)
        bloques[salidas] = {k for t, modo, k, _sql in motor.lecturas if t in _TABLAS_MT}
    assert consultas[n] == consultas[4 * n], 'las consultas cambian con el número de salidas'
    assert bloques[n] == bloques[4 * n] == {sv.FILAS_POR_BLOQUE}, bloques


def _red_mt_sucia():
    """080:RF-60 (MEM-MT): dos copias de la salida de ejemplo con lo que el motor puede dar en las tablas MT y el
    canónico limpia al leerlo: códigos con espacios, enteros y ``None``, números como texto o ``Decimal``, un real
    no finito y un booleano."""
    from decimal import Decimal

    tablas = _red_de_salidas(2)
    tramos, vertices, seds = tablas['mtTramo'], tablas['verTramoMT'], tablas['Sed']
    tramos[0]['CodSalidaMT'] = '  ' + tramos[0]['CodSalidaMT'] + ' '
    tramos[1]['CodTramoMTPadre'] = tramos[1]['CodTramoMTPadre'] + '   '
    tramos[2]['CodNorma'] = None
    tramos[3]['CodTenNomi'] = ' d '
    vertices[0]['SecVertice'] = ' 1 '
    vertices[1]['UTMEste'] = Decimal('50.000')
    vertices[2]['UTMNorte'] = float('nan')
    vertices[3]['SecVertice'] = True
    seds[0]['MaxDemTotal'] = Decimal('120.5')
    seds[1]['CodSed'] = ' ' + seds[1]['CodSed']
    seds[1]['EtiquetaCampo'] = 7
    tablas['mtNodoEnlace'][1]['CodSed'] = seds[1]['CodSed'].strip() + '  '
    tablas['mtEquipo'][0]['CodTramoMT'] = ' ' + tablas['mtEquipo'][0]['CodTramoMT']
    tablas['mtEquipo'][1]['UTMEste'] = '98.0'
    tablas['mtEquipo'][2]['CodEqp'] = 12345
    return tablas


def _sin_bt_en_los_metadatos(modelo):
    from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import SIN_REGLA_BT

    modelo.metadata = {k: v for k, v in modelo.metadata.items() if k != SIN_REGLA_BT}
    return modelo


def test_la_red_mt_en_flujo_da_el_mismo_geopackage_y_el_mismo_modelo(monkeypatch, tmp_path):
    """080:RF-60 (MEM-MT) — armar la red MT por lotes de salidas desde el disco da el MISMO GeoPackage que el canónico
    entero (tablas, índices, ``gpkg_contents`` con su extensión, esquema de cada capa, filas y sha256 de las filas
    ordenadas), los mismos avisos y el mismo resumen; y el canónico MT juntado por lotes (``con_modelo_mt``) es, en JSON,
    el de ``modelo_canonico`` sobre las tablas enteras. Sobre la red enrevesada, la red de equivalencia de 080:RF-59
    (equipo de código repetido, SED en dos salidas, salida repetida, sin red BT), una red MT con los valores sucios que
    puede dar el motor (espacios, enteros, ``None``, ``Decimal``, números como texto, NaN) y una empresa sintética con equipos,
    reguladores, salidas sin tramos y etiquetas repetidas; con lotes de 1, 3 y 1 000 salidas, y con y sin pyarrow."""
    _exige_capas()
    from convertersmartgrid.adaptadores.entrada.vnr.exporters import capas
    from vnr_bt_sintetica import EmpresaGrande, MotorSinMars, huella_gpkg

    con_arrow = capas._arrow
    rng = random.Random(SEMILLA)
    redes = {
        'enrevesada': Motor(bases=['CSG_VNR_SINTETICA'], tablas=_red_bt_enrevesada(random.Random(SEMILLA))),
        'equivalencia': Motor(bases=['CSG_VNR_SINTETICA'], tablas=_red_de_equivalencia()),
        'sucia': Motor(bases=['CSG_VNR_SINTETICA'], tablas=_red_mt_sucia()),
        'empresa': EmpresaGrande(rng.randint(25, 45), rng.randint(2, 6), SEMILLA, rng.randint(3, 9), True)}
    vistos = set()
    for nombre, red in redes.items():
        def conectar(*_a, red=red, **_k):
            return Conexion(red, '') if isinstance(red, Motor) else MotorSinMars(red.tablas()).conectar()

        monkeypatch.setattr(sv, 'conectar', conectar)
        antes = capas.exportar_copia_a_capas('CSG_VNR_SINTETICA', tmp_path / f'{nombre}_antes.gpkg')[1]
        _modelo, avisos_antes = capas.leer_base_restaurada('CSG_VNR_SINTETICA')
        mt_antes = _modelo_en_json(sv.modelo_canonico(sv.leer_datos(conectar()))[0], [])
        referencia = huella_gpkg(tmp_path / f'{nombre}_antes.gpkg')
        for lote, sin_arrow in ((1, False), (3, True), (1000, False)):
            monkeypatch.setattr(capas, '_arrow', (lambda: None) if sin_arrow else con_arrow)
            destino = tmp_path / f'{nombre}_{lote}.gpkg'
            hecho = capas.exportar_base_a_capas_en_flujo('CSG_VNR_SINTETICA', None, destino, lote_salidas=lote,
                                                         con_modelo_mt=True)
            caso = f'{nombre}, lote {lote}, {"sin" if sin_arrow else "con"} pyarrow (semilla {SEMILLA})'
            ahora = huella_gpkg(destino)
            assert ahora == referencia, f'otro GeoPackage: {caso}: ' + str(
                {k: (v, ahora['capas'].get(k)) for k, v in referencia['capas'].items() if ahora['capas'].get(k) != v})
            assert hecho.avisos == avisos_antes, f'otros avisos: {caso}'
            assert hecho.resumen == capas.resumen_de_tramos(antes), f'otro resumen: {caso}'
            assert 1 <= hecho.lotes_mt <= -(-len(sv.leer_datos(conectar()).salidas) // lote), caso
            ahora_mt = _modelo_en_json(_sin_bt_en_los_metadatos(hecho.modelo_mt), [])
            assert ahora_mt == mt_antes, f'otro canónico MT: {caso}'
            vistos |= {a['code'] for a in hecho.avisos} | set(ahora['capas'])
    esperados = {'Equipo_MT', 'Sed', 'Nodo_MT', 'Tramo_MT', 'Tramo_BT', 'REGULADOR_DEDUCIDO', 'SALIDA_SIN_TRAMOS_CON_SED',
                 'ETIQUETA_SED_REPETIDA', 'SED_SIN_ETIQUETA', 'EQUIPO_SIN_MODELAR', 'SALIDA_DE_TRAMO_NULO'}
    assert esperados <= vistos, f'faltan casos: {esperados - vistos}'


def test_las_capas_mt_por_lotes_dan_las_capas_del_canonico_entero(monkeypatch, tmp_path):
    """080:RF-60 (MEM-MT) — las capas MT guardadas lote a lote y escritas después dan el mismo GeoPackage que el canónico
    entero también en los casos que la red de VNR-GIS no suele traer: un nodo repetido en dos lotes (manda el último,
    como el diccionario de antes), uno sin posición, una SED y un equipo sin nodo (no se escriben, y el tipo de su
    columna sale de las filas que sí), un tramo sin vértices (se dibuja entre sus nodos), una tensión sin dato en toda la
    capa (columna de texto vacía) y ``ON_OFF`` y ``KVAR`` con enteros, reales y ``None``. Con y sin pyarrow."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.sqlserver_vnr import _sqlite_temporal
    _exige_capas()
    from convertersmartgrid.adaptadores.entrada.vnr.exporters import capas
    from convertersmartgrid.adaptadores.entrada.vnr.models import (Capacitor, CanonicalModel, Load, Node, Regulator,
                                                                 Section, Switch)
    from vnr_bt_sintetica import huella_gpkg

    def lote(i: int) -> CanonicalModel:
        m = CanonicalModel(metadata={'company': 'EMP', 'working_crs': 'EPSG:32718'})
        m.nodes += [Node('N0', x=float(i), y=0.0), Node(f'A{i}', x=10.0 + i, y=1.0), Node(f'B{i}', x=20.0, y=2.0 + i),
                    Node(f'S{i}', x=None, y=None)]
        m.sections += [Section(f'T{i}', f'A{i}', f'B{i}', geometry=[(10.0 + i, 1.0), (20.0, 2.0 + i)], length_m=10.0,
                               feeder_id='F'),
                       Section(f'U{i}', 'N0', f'A{i}', geometry=None, length_m=float(i), feeder_id='F'),
                       Section(f'V{i}', f'S{i}', f'A{i}', geometry=[(1.0, 1.0)], feeder_id='F')]
        m.loads += [Load(f'L{i}', 'N0', kw=1.5, connected_kva=None if i else 30.0, etiqueta=f'E{i}'),
                    Load(f'M{i}', 'NO_HAY', kw=2.0), Load(f'P{i}', f'S{i}', kw='sin nodo')]
        m.switches += [Switch(f'Q{i}', f'A{i}', on_off=i % 2, section_id=f'T{i}'), Switch(f'R{i}', 'NO_HAY')]
        m.capacitors += [Capacitor(f'C{i}', f'B{i}', kvar=300 if i else 150.5, status='in_service')]
        m.regulators += [Regulator(f'G{i}', f'B{i}', section_id=f'T{i}', on_off=1)]
        return m

    con_arrow = capas._arrow
    lotes = [lote(0), lote(1), lote(2)]
    entero = CanonicalModel(metadata=dict(lotes[0].metadata))
    for m in lotes:
        capas._sumar_al_modelo(entero, m)
    capas.exportar_canonico_a_capas(entero, tmp_path / 'entero.gpkg')
    referencia = huella_gpkg(tmp_path / 'entero.gpkg')
    assert referencia['capas']['Sed']['filas'] == 3, 'solo las SED del nodo con posición'
    for sin_arrow in (False, True):
        monkeypatch.setattr(capas, '_arrow', (lambda: None) if sin_arrow else con_arrow)
        destino = tmp_path / f'lotes_{sin_arrow}.gpkg'
        cn = _sqlite_temporal(tmp_path / f'lotes_{sin_arrow}.sqlite')
        guardadas = capas._CapasMtEnDisco(cn)
        for m in lotes:
            guardadas.agregar(m)
        guardadas.escribir(destino, 'EPSG:32718')
        cn.close()
        assert huella_gpkg(destino) == referencia, f'sin pyarrow: {sin_arrow}'
