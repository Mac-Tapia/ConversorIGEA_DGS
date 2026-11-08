"""Spec 023 — VNR-GIS desde la copia de SQL Server de cualquier concesionaria, sin motor.

El motor se sustituye por un doble de ODBC; las tablas son las del modelo VNR-GIS del
regulador, iguales para toda empresa. La copia real se prueba con ``CSG_VNR_BAK``.
"""
from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv


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
        self.bases = set(bases)
        self.tablas = tablas or {}
        self.sql: list[str] = []

    def conectar(self, cadena, autocommit=True):
        return Conexion(self, cadena)

    def responder(self, sql, params):
        if sql.startswith('SELECT name FROM sys.databases'):
            return [(params[0],)] if params[0] in self.bases else []
        if 'InstanceDefaultDataPath' in sql:
            return [('C:\\datos\\',)]
        if sql.startswith('RESTORE FILELISTONLY'):
            return [('VNR_dat', 'X', 'D'), ('VNR_log', 'X', 'L')]
        if sql.startswith('RESTORE DATABASE'):
            return []
        if 'INFORMATION_SCHEMA.COLUMNS' in sql:
            return [(t, c) for t, filas in self.tablas.items() for c in (filas[0] if filas else {})]
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
    """023:RF-9 — una vista que nombra otra base que no vino en la copia (Electro Oriente 2025:
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
    """023:RF-9 — sin «cfgCodigoSecundario» (Electro Oriente 2025 no entregó su base de
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
    """023:RF-1 — una copia de SQL Server sin «.bak» (Electro Oriente entregó «ELOR25_V2») se
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
