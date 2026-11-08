"""Spec 080 — acceso directo a los paquetes VNR-GIS de cada distribuidora."""

from __future__ import annotations

import dataclasses
import json
import time
import zipfile
from html import escape
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.entrada.vnr.discovery import download as descarga
from convertersmartgrid.adaptadores.entrada.vnr.discovery.catalog import Publication, PublicationCatalog
from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import (
    DownloadCancelled,
    DownloadError,
    DownloadManager,
    extraer_copia_sql,
    preparar_unrar,
)
from convertersmartgrid.adaptadores.entrada.vnr.discovery.official import (
    PORTAL_VNR,
    paginas_de_ciclos,
    parse_official_publications,
    refresh_official_catalog,
    vigentes_por_empresa,
)

BASE = 'https://www.osinergmin.gob.pe/seccion/institucional/regulacion-tarifaria/procesos-regulatorios/'
PAGINA_2025 = BASE + 'actividades-relacionadas/resolucion-fijacion-vnr-adaptado-2025'
WWW2 = 'https://www2.osinergmin.gob.pe/GRT/Procesos-Regulatorios/VNR/2026/F/'

# La tabla con la forma del portal: dos empresas por fila, y otras secciones en la misma página.
TABLA = f'''<div class="reutilizable"><table><tr><td>
  <a href="/Resoluciones/pdf/2026/Osinergmin-154-2026-OS-CD.pdf">Resolución N° 154-2026-OS/CD</a>
  <a href="/Resoluciones/pdf/2026/Osinergmin-184-2026-OS-CD.pdf">Resolución N° 184-2026-OS/CD</a>
  <a href="/Resoluciones/pdf/2017/OSINERGMIN%20No.232-2017-OS-CD.pdf">Resolución N° 232-2017-OS/CD</a>
  </td></tr>
  <tr><td><a href="{WWW2}01%20VNRGIS/Luz%20del%20Sur.zip"> ​ Luz del Sur </a></td>
      <td><a href="{WWW2}01%20VNRGIS/Pluz%20Energia.zip"> Pluz Energía Perú </a></td></tr>
  <tr><td><a href="{WWW2}01%20VNRGIS/CVC%20Energia.zip">CVS Energía</a></td></tr>
  <tr><td><a href="{WWW2}02%20SICODI/Archivos_TXT_SICODI.zip">Archivos TXT de Costos</a></td></tr>
  <tr><td><a href="{WWW2}03%20MAPA_DENSIDAD/Mapa%20-%20Luz%20del%20Sur.zip">Luz del Sur</a></td></tr>
  <tr><td><a href="/Resoluciones/pdf/2026/Informe%20795%20Recurso%20VNR%20-%20Anexos.rar">Anexos digitales</a></td></tr>
  </table></div>
  <a href="{BASE}actividades-relacionadas/publicacion-proyecto-resolucion-vnr-adaptado-2025">Proyecto VNR</a>'''


def _por_nombre(publicaciones):
    return {p.file_name: p for p in publicaciones}


def test_lee_de_la_pagina_oficial_las_paginas_de_todos_sus_ciclos():
    """080:RF-1 — los ciclos salen de la página oficial, no de una lista de años."""
    html = f'''<a href="{BASE}actividades-relacionadas/resolucion-fijacion-vnr-adaptado-2031">a</a>
      <a href="/seccion/institucional/regulacion-tarifaria/procesos-regulatorios/actividades-relacionadas/resolucion-reconsideracion-vnr-adaptado-2029#x">b</a>
      <a href="{BASE}actividades-relacionadas/aprobacion-altas-bajas-2024">otra actividad</a>
      <a href="https://example.com/actividades-relacionadas/vnr-adaptado-2031">externa</a>'''
    assert paginas_de_ciclos(html) == [
        BASE + 'actividades-relacionadas/resolucion-fijacion-vnr-adaptado-2031',
        BASE + 'actividades-relacionadas/resolucion-reconsideracion-vnr-adaptado-2029',
    ]


def test_la_busqueda_recorre_los_ciclos_que_encuentra(tmp_path):
    """080:RF-1 — la búsqueda sin páginas fijadas parte de la página oficial."""
    def leer(url):
        return f'<a href="{PAGINA_2025}">ciclo</a>' if url == PORTAL_VNR else TABLA if url == PAGINA_2025 else ''

    catalogo, informe = refresh_official_catalog(tmp_path, fetcher=leer)

    assert PAGINA_2025 in informe['pages'] and not informe['errors']
    assert 'Luz del Sur' in {p.company for p in catalogo.publications()}


def test_un_fallo_de_la_pagina_oficial_se_informa_y_no_oculta_las_demas(tmp_path):
    """080:RF-17 — el fallo dice qué página falló."""
    def leer(url):
        if url == PORTAL_VNR:
            raise OSError('sin red')
        return ''

    _, informe = refresh_official_catalog(tmp_path, fetcher=leer)

    assert [e['page'] for e in informe['errors']] == [PORTAL_VNR]
    assert 'sin red' in informe['errors'][0]['error']


@pytest.mark.parametrize('html', [TABLA, f'<div>{escape(TABLA, quote=False)}</div>'],
                         ids=['normal', 'escapada'])
def test_lee_la_tabla_normal_y_la_escapada(html):
    """080:RF-2 — la tabla escapada del portal da los mismos paquetes."""
    paquetes = [p for p in parse_official_publications(PAGINA_2025, html)
                if p.publication_type == 'REGULATORY_VNRGIS_PACKAGE']
    assert {p.file_name for p in paquetes} == {'Luz del Sur.zip', 'Pluz Energia.zip', 'CVC Energia.zip'}


def test_solo_la_seccion_vnrgis_es_paquete():
    """080:RF-3, 080:RF-4 — costos, mapas y anexos no se ofrecen como red."""
    filas = _por_nombre(parse_official_publications(PAGINA_2025, TABLA))
    assert filas['Luz del Sur.zip'].publication_type == 'REGULATORY_VNRGIS_PACKAGE'
    assert filas['Archivos_TXT_SICODI.zip'].publication_type == 'SICODI'
    assert filas['Mapa - Luz del Sur.zip'].publication_type == 'MAP_DENSITY'
    assert filas['Informe 795 Recurso VNR - Anexos.rar'].publication_type == 'REGULATORY_VNR_PUBLICATION'


def test_cada_paquete_con_su_empresa_aunque_compartan_fila():
    """080:RF-5 — dos empresas en una fila no se mezclan."""
    filas = _por_nombre(parse_official_publications(PAGINA_2025, TABLA))
    assert filas['Luz del Sur.zip'].company == 'Luz del Sur'
    assert filas['Pluz Energia.zip'].company == 'Pluz Energía Perú'


def test_un_rotulo_que_no_corresponde_cede_al_nombre_del_archivo():
    """080:RF-6 — el portal rotula «CVS Energía» el fichero de CVC Energia."""
    assert _por_nombre(parse_official_publications(PAGINA_2025, TABLA))['CVC Energia.zip'].company == 'CVC Energia'


def test_ciclo_y_resolucion_salen_de_la_pagina():
    """080:RF-7 — el año del VNR y la resolución más reciente que cita la página."""
    paquete = _por_nombre(parse_official_publications(PAGINA_2025, TABLA))['Luz del Sur.zip']
    assert paquete.period_label == '2025'
    assert paquete.regulatory_reference == '184-2026-OS/CD'


def test_el_nombre_del_archivo_va_sin_codigos_de_url():
    """080:RF-8 — «Luz del Sur.zip», no «Luz%20del%20Sur.zip»."""
    assert 'Luz del Sur.zip' in _por_nombre(parse_official_publications(PAGINA_2025, TABLA))


def _paquete(pid, empresa, periodo, resolucion):
    return Publication(publication_id=pid, company=empresa, period_label=periodo,
                       regulatory_reference=resolucion, publication_type='REGULATORY_VNRGIS_PACKAGE',
                       download_url=f'https://www2.osinergmin.gob.pe/{pid}.zip')


def test_vigente_el_vnr_mas_reciente_y_su_ultima_resolucion():
    """080:RF-9 — manda la resolución, no el orden ni el título de la página."""
    grupos = vigentes_por_empresa([
        _paquete('a', 'Hidrandina', '2022', '186-2023-OS/CD'),
        _paquete('b', 'Hidrandina', '2022', '208-2023-OS/CD'),
        _paquete('c', 'Hidrandina', '2021', '999-2022-OS/CD'),
        _paquete('d', 'Seal', '2022', '186-2023-OS/CD'),
    ])
    assert {pid for pid, g in grupos.items() if g['vigente']} == {'b', 'd'}
    assert grupos['a']['empresa'] == grupos['c']['empresa'] == 'Hidrandina'


def test_dos_nombres_de_un_mismo_ciclo_son_una_empresa():
    """080:RF-10 — sin juntar empresas distintas que empiezan parecido en otro ciclo."""
    grupos = vigentes_por_empresa([
        _paquete('a', 'Pluz Energia Peru', '2025', '154-2026-OS/CD'),
        _paquete('b', 'Pluz Energia', '2025', '184-2026-OS/CD'),
        _paquete('c', 'Electro Sur', '2018', '100-2019-OS/CD'),
        _paquete('d', 'Electro Sur Este', '2022', '208-2023-OS/CD'),
    ])
    assert {pid for pid, g in grupos.items() if g['vigente']} == {'b', 'c', 'd'}
    assert grupos['a']['empresa'] == grupos['b']['empresa']


# ------------------------------------------------------------------ extracción de la copia
def _paquete_con_copia(ruta: Path) -> Path:
    with zipfile.ZipFile(ruta, 'w') as zf:
        zf.writestr('Empresa/DAT_VNR/EMPR_VNR_22.bak', b'TAPE' + b'x' * 500)
        zf.writestr('Empresa/DAT_VNR/paramVNRGISEMPR_22.bak', b'TAPE' + b'p' * 900)
        zf.writestr('Empresa/DAT_VNR/ConfigBD.config', b'config')
        zf.writestr('Empresa/DAT_VNR/leeme.exe', b'MZ')
        zf.writestr('Empresa/VNRGIS_InstaladorEmpresas.exe', b'MZ')
        zf.writestr('Empresa/Manual/Manual.pdf', b'%PDF')
    return ruta


def test_extrae_solo_la_carpeta_de_la_copia(tmp_path):
    """080:RF-18, 080:RF-19 — la copia de red, no la de parámetros aunque pese más; nada ejecutable."""
    destino = tmp_path / 'copia'

    bak = extraer_copia_sql(_paquete_con_copia(tmp_path / 'p.zip'), destino)

    assert bak == destino / 'EMPR_VNR_22.bak'
    assert sorted(p.name for p in destino.iterdir()) == [
        'ConfigBD.config', 'EMPR_VNR_22.bak', 'paramVNRGISEMPR_22.bak']


def test_un_paquete_sin_copia_no_extrae_nada(tmp_path):
    """080:RF-20 — sigue siendo un paquete de capas."""
    paquete = tmp_path / 'capas.zip'
    with zipfile.ZipFile(paquete, 'w') as zf:
        zf.writestr('Tramo_MT.geojson', '{}')

    assert extraer_copia_sql(paquete, tmp_path / 'copia') is None
    assert not (tmp_path / 'copia').exists()


def test_sin_espacio_lo_dice_y_no_deja_ficheros(tmp_path, monkeypatch):
    """080:RF-21 — se comprueba antes de escribir."""
    paquete = _paquete_con_copia(tmp_path / 'p.zip')
    monkeypatch.setattr(descarga.shutil, 'disk_usage',
                        lambda _ruta: type('U', (), {'free': 10})())

    with pytest.raises(DownloadError, match='espacio'):
        extraer_copia_sql(paquete, tmp_path / 'copia')

    assert not (tmp_path / 'copia').exists() or not list((tmp_path / 'copia').iterdir())


def test_cancelar_no_deja_ficheros_a_medias(tmp_path):
    """080:RF-22 — ni copias parciales ni temporales."""
    paquete = _paquete_con_copia(tmp_path / 'p.zip')
    destino = tmp_path / 'copia'

    with pytest.raises(DownloadCancelled):
        extraer_copia_sql(paquete, destino, cancelled=lambda: True)

    assert not destino.exists() or not list(destino.iterdir())


def test_encuentra_el_extractor_fuera_del_path(tmp_path, monkeypatch):
    """080:RF-23 — WinRAR no se añade al PATH al instalarse."""
    rarfile = pytest.importorskip('rarfile')
    herramienta = tmp_path / 'UnRAR.exe'
    herramienta.write_bytes(b'')
    llamadas = []
    monkeypatch.setattr(descarga.shutil, 'which', lambda _nombre: None)
    monkeypatch.setenv('CSG_UNRAR', str(herramienta))
    monkeypatch.setattr(rarfile, 'tool_setup', lambda **k: llamadas.append(k))
    original = rarfile.UNRAR_TOOL
    try:
        preparar_unrar()
        assert rarfile.UNRAR_TOOL == str(herramienta)
        assert llamadas and llamadas[0]['force'] is True
    finally:
        rarfile.UNRAR_TOOL = original


def test_sin_extractor_lo_dice_antes_de_descargar(tmp_path, monkeypatch):
    """080:RF-24 — no se bajan cientos de MB para acabar fallando, ni se reintenta."""
    import sys
    import types

    def sin_herramienta():
        raise DownloadError('Falta un extractor de RAR.')

    pedidas = []
    monkeypatch.setattr(descarga, 'preparar_unrar', sin_herramienta)
    monkeypatch.setitem(sys.modules, 'requests', types.SimpleNamespace(
        get=lambda *a, **k: pedidas.append(a)))

    with pytest.raises(DownloadError, match='extractor de RAR'):
        DownloadManager(tmp_path / 'c', retries=3).download(
            'https://www2.osinergmin.gob.pe/x.rar', tmp_path / 'x.rar')

    assert pedidas == []


# ------------------------------------------------------------------ restauración
class _Motor:
    """Un motor que no puede abrir la copia hasta que se le da permiso."""

    def __init__(self):
        self.puede_leer = False
        self._filas = []

    def conectar(self, *_a, **_k):
        return self

    def cursor(self):
        return self

    def execute(self, sql, *_p):
        if sql.startswith('RESTORE') and not self.puede_leer:
            raise RuntimeError("[42000] Cannot open backup device. Operating system error 5. (3201)")
        if 'sys.databases' in sql:
            self._filas = []
        elif 'InstanceDefaultDataPath' in sql:
            self._filas = [('C:\\datos',)]
        elif 'FILELISTONLY' in sql:
            self._filas = [('dat', '', 'D')]
        elif 'dm_server_services' in sql:
            self._filas = [('NT Service\\MSSQL$PRUEBA',)]
        else:
            self._filas = []
        return self

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return self._filas

    def nextset(self):
        return False


def test_el_motor_recibe_lectura_solo_sobre_la_copia(tmp_path, monkeypatch):
    """080:RF-25 — a su cuenta y a ese fichero; luego restaura."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    bak = tmp_path / 'EMPR.bak'
    bak.write_bytes(b'TAPE')
    motor = _Motor()
    ordenes = []

    def icacls(orden, **_k):
        ordenes.append(orden)
        motor.puede_leer = True
        return type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()

    monkeypatch.setattr(sv.subprocess, 'run', icacls)

    assert sv.restaurar(bak, conectar_odbc=motor.conectar).startswith('CSG_VNR_')
    assert ordenes == [['icacls', str(bak.resolve()), '/grant', 'NT Service\\MSSQL$PRUEBA:R']]


def test_sin_poder_dar_permiso_dice_fichero_y_cuenta(tmp_path, monkeypatch):
    """080:RF-26 — no un error de ODBC sin explicación."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    bak = tmp_path / 'EMPR.bak'
    bak.write_bytes(b'TAPE')
    monkeypatch.setattr(sv.subprocess, 'run', lambda *_a, **_k: type(
        'R', (), {'returncode': 5, 'stdout': '', 'stderr': 'Acceso denegado'})())

    with pytest.raises(sv.MotorSqlNoDisponible, match=r'EMPR\.bak.*MSSQL\$PRUEBA'):
        sv.restaurar(bak, conectar_odbc=_Motor().conectar)


# ------------------------------------------------------------------ carga completa
def test_una_salida_de_tramo_nulo_se_carga_con_su_sed():
    """080:RF-27 — 47 salidas de Electro Sur Este desaparecían con su SED."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtSalida'].append({'CodSalidaMT': 'F2', 'CodSet': 'S1', 'CodTenNomi': 'D',
                               'EtiquetaSalida': 'F2', 'CodSisElectrico': 'SE1'})
    tablas['mtTramo'].append({'CodTramoMT': 'N1', 'CodSalidaMT': 'F2', 'CodTramoMTPadre': '',
                              'CodNorma': 'AA05003'})
    tablas['verTramoMT'] += [
        {'CodTramoMT': 'N1', 'SecVertice': 1, 'UTMEste': 900.0, 'UTMNorte': 9.0},
        {'CodTramoMT': 'N1', 'SecVertice': 2, 'UTMEste': 900.1, 'UTMNorte': 9.0}]
    tablas['Sed'].append({'CodSed': 'E2', 'CodSalidaMT': 'F2', 'PotInstalada': 50.0,
                          'UTMEste': 900.0, 'UTMNorte': 9.0, 'MaxDemTotal': 7.0})
    tablas['mtNodoEnlace'].append({'CodNodoMT': 'N2', 'CodTramoMT': 'N1', 'CodSed': 'E2',
                                   'UTMEste': 900.0, 'UTMNorte': 9.0})

    modelo, avisos = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))

    (tramo,) = [s for s in modelo.sections if s.feeder_id == 'F2']
    assert tramo.from_node != tramo.to_node and tramo.length_m > 0
    (carga,) = [c for c in modelo.loads if c.feeder_id == 'F2']
    assert carga.load_id == 'E2' and carga.connection_node in (tramo.from_node, tramo.to_node)
    assert {n.node_id for n in modelo.nodes} >= {tramo.from_node, tramo.to_node}
    assert [a['source_id'] for a in avisos if a['code'] == 'SALIDA_DE_TRAMO_NULO'] == ['F2']


def test_una_salida_con_sed_y_sin_tramos_se_carga():
    """080:RF-32 — 748055397 de Luz del Sur: su demanda no se pierde."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtSalida'].append({'CodSalidaMT': 'F2', 'CodSet': 'S1', 'CodTenNomi': 'D',
                               'EtiquetaSalida': 'F2', 'CodSisElectrico': 'SE1'})
    tablas['Sed'].append({'CodSed': 'E2', 'CodSalidaMT': 'F2', 'PotInstalada': 50.0,
                          'UTMEste': 900.0, 'UTMNorte': 9.0, 'MaxDemTotal': 7.0})

    modelo, avisos = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))

    (tramo,) = [s for s in modelo.sections if s.feeder_id == 'F2']
    assert tramo.conductor_code == 'AA05003D'
    assert [c.load_id for c in modelo.loads if c.feeder_id == 'F2'] == ['E2']
    assert [a['source_id'] for a in avisos if a['code'] == 'SALIDA_SIN_TRAMOS_CON_SED'] == ['F2']


def test_una_salida_sin_tramos_ni_sed_sigue_sin_cargarse():
    """080:RF-32 — sin red ni demanda no se inventa nada, y se anota."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtSalida'].append({'CodSalidaMT': 'F2', 'CodSet': 'S1', 'CodTenNomi': 'D',
                               'EtiquetaSalida': 'F2', 'CodSisElectrico': 'SE1'})

    modelo, avisos = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))

    assert not [s for s in modelo.sections if s.feeder_id == 'F2']
    assert [a['source_id'] for a in avisos if a['code'] == 'SALIDA_SIN_TRAMOS'] == ['F2']


def test_dos_raices_en_un_mismo_punto_no_rompen_la_carga():
    """080:RF-33 — 11953196 de Luz del Sur, con sus dos tramos raíz en un punto."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtSalida'].append({'CodSalidaMT': 'F2', 'CodSet': 'S1', 'CodTenNomi': 'D',
                               'EtiquetaSalida': 'F2', 'CodSisElectrico': 'SE1'})
    for cod in ('R1', 'R2'):
        tablas['mtTramo'].append({'CodTramoMT': cod, 'CodSalidaMT': 'F2', 'CodTramoMTPadre': '0',
                                  'CodNorma': 'AA05003'})
        tablas['verTramoMT'] += [
            {'CodTramoMT': cod, 'SecVertice': 1, 'UTMEste': 900.0, 'UTMNorte': 9.0},
            {'CodTramoMT': cod, 'SecVertice': 2, 'UTMEste': 900.1, 'UTMNorte': 9.0}]

    modelo, _ = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))

    assert len([s for s in modelo.sections if s.feeder_id == 'F2']) == 1


def _con_equipo(tipo: str, norma: str, descripcion: str):
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtEquipo'].append({'CodEqp': 'X1', 'CodTramoMT': 'T1', 'CodTipoEquipoProteccion': tipo,
                               'CodEstadoOperacion': 'NC', 'CodNorma': norma,
                               'UTMEste': 50.0, 'UTMNorte': 1.0})
    tablas['admCodigosNorma'].append({'CodNorma': norma, 'Descripcion': descripcion,
                                      'CodSubComponente': 'C4'})
    return sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))


@pytest.mark.parametrize('tipo', ['CE', 'DB', 'DP'])
def test_celdas_y_derivaciones_son_maniobras(tipo):
    """080:RF-35 — 190 equipos de Luz del Sur se perdían."""
    modelo, avisos = _con_equipo(tipo, f'{tipo}1', 'CELDA O DERIVACION 10 kV')

    assert tipo in {s.kind for s in modelo.switches if s.switch_id == 'X1'}
    assert not [a for a in avisos if a['code'] == 'EQUIPO_SIN_MODELAR' and a['source_id'] == 'X1']


@pytest.mark.parametrize('descripcion, kvar', [
    ('BANCO DE CONDENSADORES FIJO, MONOFASICO, 3x200 kVAR, 10-15 kV', 600.0),
    ('BANCO DE CONDENSADORES FIJO, MONOFASICO, 6x150 kVAR, 10-15 kV', 900.0),
    ('BANCO DE CONDENSADORES FIJO, TRIPOLAR, 300 kVAR, 10-15 kV', 300.0),
    ('BANCO DE CONDENSADORES FIJO, MONOFASICO, 100 kVAR, 10-15 kV', 100.0),
])
def test_los_kvar_del_banco_son_el_total_de_sus_unidades(descripcion, kvar):
    """080:RF-36 — «3x200 kVAR» son 600 kvar."""
    modelo, _ = _con_equipo('BC', 'BCX', descripcion)

    assert {c.capacitor_id: c.kvar for c in modelo.capacitors}['X1'] == kvar


def test_un_tipo_sin_modelar_se_anota():
    """080:RF-37 — ningún equipo se pierde en silencio, sea cual sea su tipo."""
    _, avisos = _con_equipo('ZZ', 'ZZ1', 'EQUIPO DESCONOCIDO')

    assert [a['tipo'] for a in avisos
            if a['code'] == 'EQUIPO_SIN_MODELAR' and a['source_id'] == 'X1'] == ['ZZ']


@pytest.mark.parametrize('tipo', ['PA', 'SE', 'SF', 'SC'])
def test_pararrayos_y_seccionadores_cerrados_no_se_modelan(tipo):
    """080:RF-39 — no se modelan, y se dice cuántos quedaron fuera."""
    modelo, avisos = _con_equipo(tipo, f'{tipo}1', 'SECCIONADOR O PARARRAYOS 10 kV')

    assert 'X1' not in {s.switch_id for s in modelo.switches}
    assert modelo.metadata['equipos_no_modelados'][tipo] >= 1
    assert not [a for a in avisos if a['code'] == 'EQUIPO_SIN_MODELAR' and a['source_id'] == 'X1']


def test_un_seccionador_abierto_se_conserva():
    """080:RF-40 — Q1 de la tabla de ejemplo, abierto: define dónde termina la red."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    modelo, _ = sv.modelo_canonico(sv.leer_datos(Motor(tablas=_tablas()).conectar('red')))

    (q1,) = [s for s in modelo.switches if s.switch_id == 'Q1']
    assert q1.on_off == 0


LEYENDA_BR = 'BANCO DE REGULACION DE TENSION x 3, MONOFASICO, In = 200 A, 10 kV, CONTROL ELECTRONICO'


def test_el_regulador_sale_de_la_leyenda_y_va_en_serie():
    """080:RF-38, 080:RF-41 — unidades y corriente de la leyenda; rango y pasos, anotados."""
    modelo, avisos = _con_equipo('BR', 'BR1', LEYENDA_BR)

    (reg,) = modelo.regulators
    assert (reg.regulator_id, reg.unidades, reg.corriente_a, reg.on_off) == ('X1', 3, 200.0, 1)
    assert reg.feeder_id == 'F1'
    (serie,) = [s for s in modelo.sections if s.section_id == reg.section_id]
    assert {serie.from_node, serie.to_node} == {reg.from_node, reg.to_node}
    (tramo,) = [s for s in modelo.sections if s.section_id == 'T1']
    assert {tramo.from_node, tramo.to_node} & {reg.from_node, reg.to_node}
    assert {n.node_id for n in modelo.nodes} >= {reg.from_node, reg.to_node}
    assert [a['source_id'] for a in avisos if a['code'] == 'REGULADOR_DEDUCIDO'] == ['X1']


def test_el_regulador_llega_al_dgs_como_elmvoltreg(tmp_path):
    """080:RF-38 — con su tipo y la toma neutra, y la red sigue conexa y convierte."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.dgs import write_dgs
    from convertersmartgrid.model import build_feeder_model
    from convertersmartgrid.puentes import fundir_reguladores
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtEquipo'].append({'CodEqp': 'X1', 'CodTramoMT': 'T1', 'CodTipoEquipoProteccion': 'BR',
                               'CodEstadoOperacion': 'NC', 'CodNorma': 'BR1',
                               'UTMEste': 50.0, 'UTMNorte': 1.0})
    tablas['admCodigosNorma'].append({'CodNorma': 'BR1', 'Descripcion': LEYENDA_BR,
                                      'CodSubComponente': 'C4'})
    canonico, _ = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))
    puente = canonical_to_cymdist(canonico, source_path=tmp_path / 'copia.bak')
    modelo = build_feeder_model(puente.dataset, 'F1', strict=False)
    assert not modelo.islands.get('disconnected_nodes') if isinstance(modelo.islands, dict) else True

    assert fundir_reguladores(modelo) == ['X1']

    (acoplador,) = [c for c in modelo.couplers if c.kind == 'BR']
    assert acoplador.regulador.corriente_a == 200.0
    # El modelo se guarda para la verificación previa: C+æ02 de Luz del Sur fallaba aquí.
    from convertersmartgrid.preflight_contract import _restaurar, snapshot_model

    copia = _restaurar(json.loads(json.dumps(snapshot_model(modelo))))
    assert [c.regulador for c in copia.couplers if c.kind == 'BR'] == [acoplador.regulador]
    assert 'X1_BR' not in {ln.section_id for ln in modelo.lines}
    destino = tmp_path / 'F1.dgs'
    write_dgs(modelo, destino)
    texto = destino.read_text(encoding='utf-8', errors='replace')
    assert '$$ElmVoltreg' in texto and '$$TypVoltreg' in texto
    # Los validadores reales: C+æ02 de Luz del Sur se paraba en estos dos, no en la escritura.
    from convertersmartgrid.reglas import auditar_completitud
    from convertersmartgrid.validate import parse_dgs, validate_dgs

    assert 'missing object' not in json.dumps(validate_dgs(modelo, destino), ensure_ascii=False)
    auditoria = auditar_completitud(puente.dataset, ['F1'], modelo, parse_dgs(destino), [])
    assert not [f for f in auditoria.get('fallos', []) if f.startswith('tramos')]


def _modelo_de_sed(pares):
    """Un doble mínimo: {(kva, kw)} de cada SED, con lo que lee ``demanda_fuera_de_escala``."""
    from types import SimpleNamespace as N

    seds = [N(load_key=('F', f'S{i}'), design_kva=k, section_id='', node_id='') for i, (k, _p) in enumerate(pares)]
    cargas = [N(p_mw=p / 1000, q_mvar=0.0, key=('F', f'S{i}'), load_key=('F', f'S{i}'))
              for i, (_k, p) in enumerate(pares)]
    return N(seds=seds, loads=cargas)


def test_una_demanda_proporcional_es_relleno(monkeypatch):
    """080:RF-42 — Electro Sur Este: 0,87, 0,88, 0,90 y 0,80 de la potencia instalada."""
    from convertersmartgrid import sed_potencia as sp

    pares = [(k, k * r) for k, r in zip((100, 160, 250, 400, 630, 50, 75, 25) * 3, (.87, .88, .9, .8) * 6)]
    modelo = _modelo_de_sed(pares)
    monkeypatch.setattr(sp, '_demanda_por_sed', lambda m: {c.load_key: [c] for c in m.loads})

    assert len(sp.demanda_fuera_de_escala(modelo)) == len(pares)


def test_una_demanda_medida_no_es_relleno(monkeypatch):
    """080:RF-42 — Luz del Sur: razones repartidas y dentro de su potencia, sin tocar."""
    from convertersmartgrid import sed_potencia as sp

    pares = [(100 + i, (100 + i) * (.30 + i * .05)) for i in range(12)]
    modelo = _modelo_de_sed(pares)
    monkeypatch.setattr(sp, '_demanda_por_sed', lambda m: {c.load_key: [c] for c in m.loads})

    assert sp.demanda_fuera_de_escala(modelo) == []


def test_el_factor_no_deja_tensiones_imposibles(monkeypatch):
    """080:RF-43 — converger con 0,68 p.u. no vale: la importación lo rechazaría."""
    from types import SimpleNamespace as N

    from convertersmartgrid import oraculo, sed_potencia as sp

    factor = {'f': None}
    modelo = N(loads=[])
    monkeypatch.setattr(sp, 'demanda_fuera_de_escala', lambda _m: [('F', 'S0')])
    monkeypatch.setattr(sp, 'regla_de', lambda _m, _k: 'relleno')

    def corregir(_m, _claves, f, reglas=None):
        factor['f'] = f
        return [N(p_nuevo_kw=f, p_fuente_kw=1, q_nuevo_kvar=0, q_fuente_kvar=0, linea=lambda: '')]

    def validar(_m, **_):
        f = factor['f']
        if f is None:
            return N(disponible=True, convergio=False, motivo_no_disponible='',
                     errores=[N(codigo='no_converge')])
        # Hasta 0,7 converge, pero solo por debajo de 0,3 lo hace sin tensiones imposibles.
        return N(disponible=True, convergio=f <= .7,
                 errores=[] if f <= .3 else [N(codigo='tension_imposible')])

    monkeypatch.setattr(sp, 'corregir_demanda', corregir)
    monkeypatch.setattr(oraculo, 'validar', validar)

    res = oraculo.corregir_para_converger(modelo)

    assert res.convergio is True and res.factor <= .3


@pytest.mark.parametrize('codigo', ['004SED000188', '12027990', 'SE41837', 'W2874335'])
def test_toda_carga_de_la_tabla_sed_es_una_sed(tmp_path, codigo):
    """080:RF-44 — con el formato de cualquier empresa, y con su potencia instalada."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.model import build_feeder_model
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['Sed'][0]['CodSed'] = codigo
    tablas['mtNodoEnlace'][0]['CodSed'] = codigo
    canonico, _ = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))
    puente = canonical_to_cymdist(canonico, source_path=tmp_path / 'copia.bak')

    modelo = build_feeder_model(puente.dataset, 'F1', strict=False)

    (sed,) = modelo.seds
    assert codigo in sed.code or sed.code in codigo
    assert sed.design_kva == 250.0


def test_la_demanda_propia_se_reduce_por_igual(monkeypatch):
    """080:RF-45 — C+æ02: conserva el reparto entre SED y anota el factor."""
    from types import SimpleNamespace as N

    from convertersmartgrid import model as modelo_mod, oraculo, sed_potencia as sp

    def carga(sed, kw):
        return dataclasses.replace(CARGA_BASE, device_number=sed, p_mw=kw / 1000, q_mvar=kw / 2000)

    CARGA_BASE = modelo_mod.Load(
        section_id='T', device_number='', customer_number='', location='', node_id='n', p_mw=0.0,
        q_mvar=0.0, pf=1.0, connected_kva=100.0, kwh=0.0, phase='ABC', sed_code='', display_name='',
        customers=1, customer_type='VNR', year=0, feeder='F', network_id='F')
    modelo = N(loads=[carga('A', 300.0), carga('B', 100.0)])
    monkeypatch.setattr(sp, 'demanda_fuera_de_escala', lambda _m: [])

    def validar(m, **_):
        total = sum(c.p_mw for c in m.loads)
        if total > .2:
            return N(disponible=True, convergio=False, motivo_no_disponible='', errores=[N(codigo='no_converge')])
        return N(disponible=True, convergio=True, motivo_no_disponible='', errores=[])

    monkeypatch.setattr(oraculo, 'validar', validar)

    res = oraculo.corregir_para_converger(modelo)

    assert res.convergio is True and res.regla == 'por_igual' and 0 < res.factor <= .5
    (a, b) = modelo.loads
    assert a.p_mw / b.p_mw == pytest.approx(3.0)
    assert sum(c.p_mw for c in modelo.loads) <= .2
    assert {c.sed for c in res.cambios} == {'A', 'B'}
    assert res.as_dict()['delta_kw'] == pytest.approx(sum(c.p_mw for c in modelo.loads) * 1000 - 400)


def test_sin_problema_de_demanda_no_se_reduce(monkeypatch):
    """080:RF-45 — lo que converge queda como lo trae la fuente; un error de red no se tapa."""
    from types import SimpleNamespace as N

    from convertersmartgrid import oraculo, sed_potencia as sp

    carga = N(p_mw=1.0, q_mvar=0.0)
    modelo = N(loads=[carga])
    monkeypatch.setattr(sp, 'demanda_fuera_de_escala', lambda _m: [])
    monkeypatch.setattr(oraculo, 'validar', lambda _m, **_: N(disponible=True, convergio=True, errores=[], motivo_no_disponible=''))
    assert oraculo.corregir_para_converger(modelo).cambios == [] and modelo.loads == [carga]

    monkeypatch.setattr(oraculo, 'validar', lambda _m, **_: N(
        disponible=True, convergio=False, motivo_no_disponible='',
        errores=[N(codigo='impedancia_nula', linea=lambda: 'tramo sin impedancia')]))
    res = oraculo.corregir_para_converger(modelo)
    assert res.convergio is False and 'impedancia' in res.motivo and modelo.loads == [carga]


def test_la_sed_lleva_su_codigo_operativo(tmp_path):
    """080:RF-46 — con «65335X» y no con el interno 12027990; la clave interna se conserva."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.model import build_feeder_model
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['Sed'][0].update(CodSed='12027990', EtiquetaCampo='65335X')
    tablas['mtNodoEnlace'][0]['CodSed'] = '12027990'
    canonico, _ = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))
    puente = canonical_to_cymdist(canonico, source_path=tmp_path / 'copia.bak')

    (sed,) = build_feeder_model(puente.dataset, 'F1', strict=False).seds

    assert sed.code == '65335X' and sed.loc_name == '65335X'
    assert sed.device_number == '12027990'


def test_codigos_operativos_repetidos_o_vacios():
    """080:RF-47 — únicos y deterministas, con su aviso."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    avisos = []
    codigos = sv.codigos_operativos_sed([
        {'CodSed': 'B', 'EtiquetaCampo': '01515S'}, {'CodSed': 'A', 'EtiquetaCampo': '01515S'},
        {'CodSed': 'C', 'EtiquetaCampo': ''}, {'CodSed': 'D', 'EtiquetaCampo': '7'},
    ], avisos)

    assert codigos == {'A': '01515S', 'B': '01515S_2', 'C': 'C', 'D': '7'}
    assert {a['code']: a['source_id'] for a in avisos} == {
        'ETIQUETA_SED_REPETIDA': 'B', 'SED_SIN_ETIQUETA': 'C'}


def test_lo_esperado_en_digsilent_cuenta_los_reguladores():
    """080:RF-48 — C+æ02: «regulators count mismatch: expected 0, actual 3»."""
    fuente = (Path(__file__).resolve().parents[1] / 'src/convertersmartgrid/geography.py'
              ).read_text(encoding='utf-8')
    assert "'regulators': 0," not in fuente
    assert 'regulador' in fuente


def _filas_del_catalogo(ruta):
    import openpyxl

    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    filas = []
    for hoja in libro.worksheets:
        valores = list(hoja.iter_rows(values_only=True))
        filas += [dict(zip(valores[0], v)) for v in valores[1:] if v and v[0]]
    libro.close()
    return filas


def test_la_semilla_no_lleva_datos_de_ninguna_empresa(tmp_path):
    """080:RF-50 — solo fichas: sin valores de modelo ni uso de una red."""
    from convertersmartgrid.catalog import asegurar_catalogo_empresa

    ruta = asegurar_catalogo_empresa(tmp_path / 'E' / 'catalogo.xlsx')

    filas = _filas_del_catalogo(ruta)
    assert {'AA', 'CU', 'N2'} == {str(f['codigo'])[:2] for f in filas}
    for fila in filas:
        assert fila['estado'] == 'ficha' and fila['R1_ficha_ohm_km'] and fila['ampacidad_ficha_A']
        assert not any(fila.get(c) for c in ('R1_modelo_ohm_km', 'X1_modelo_ohm_km', 'tramos', 'km', 'alimentadores'))
        texto = str(fila.get('fuente')) + str(fila.get('observaciones'))
        assert not any(e in texto for e in ('Electro', 'ELOR', 'ELDU', 'ELSE', 'LDS', 'Luz del Sur'))


def test_la_x_aerea_sale_de_la_geometria():
    """080:RF-51 — crece al bajar la sección y da el orden de magnitud de una línea de MT."""
    from convertersmartgrid.catalog import reactancia_aerea_ohm_km

    assert reactancia_aerea_ohm_km(50.0) > reactancia_aerea_ohm_km(120.0)
    assert 0.35 < reactancia_aerea_ohm_km(120.0) < reactancia_aerea_ohm_km(25.0) < 0.55


def test_cada_empresa_amplia_solo_su_catalogo(tmp_path, monkeypatch):
    """080:RF-49 — un código de una empresa no aparece en el fichero de la otra."""
    from convertersmartgrid import reglas
    from convertersmartgrid.catalog import ampliar_catalogo

    monkeypatch.setattr(reglas, 'project_root', lambda: tmp_path)
    uno, otro = reglas.catalogo_de_empresa('ELSE'), reglas.catalogo_de_empresa('LDS')
    assert uno != otro and 'ELSE' in str(uno) and 'LDS' in str(otro)

    ampliar_catalogo(uno, ['AA08501G'], origen='ELSE')

    assert 'AA08501G' in {f['codigo'] for f in _filas_del_catalogo(uno)}
    assert 'AA08501G' not in {f['codigo'] for f in _filas_del_catalogo(otro)}


def test_una_empresa_nueva_completa_sus_conductores_sin_otro_catalogo(tmp_path):
    """080:RF-49, 080:RF-50 — con la semilla se deducen las familias de la leyenda."""
    from convertersmartgrid.adaptadores.entrada.vnr.models.canonical import CanonicalModel, ConductorType

    from convertersmartgrid.catalog import asegurar_catalogo_empresa
    from convertersmartgrid.sources import vnr

    ruta = asegurar_catalogo_empresa(tmp_path / 'catalogo.xlsx')
    codigos = ['AA05003G', 'AA03501G', 'CU01603D', 'N207003D', 'NK05003D', 'AS05003G', 'CS05003F']
    modelo = CanonicalModel()
    modelo.conductor_types += [ConductorType(conductor_code=c) for c in codigos]

    vnr.ampliar_con_lo_que_falta(modelo, origen='Empresa', catalogo=ruta)

    assert vnr.fichas_del_catalogo(modelo, ruta) == {'completados': len(codigos), 'sin_ficha': 0}
    assert all(t.r1_ohm_km and t.x1_ohm_km for t in modelo.conductor_types)


def test_el_catalogo_de_la_fuente(tmp_path, monkeypatch):
    """080:RF-49 — la copia VNR-GIS usa el de su empresa; las demás fuentes, el del proyecto."""
    from convertersmartgrid import reglas

    monkeypatch.setattr(reglas, 'project_root', lambda: tmp_path)
    proyecto = tmp_path / 'proyecto.xlsx'
    monkeypatch.setattr(reglas, 'catalogo_del_proyecto', lambda: proyecto)

    assert 'LDS' in str(reglas.catalogo_de_fuente({'sqlserver': {'company': 'LDS'}}))
    assert reglas.catalogo_de_fuente({}) == proyecto
    assert reglas.catalogo_de_fuente(None) == proyecto


def test_el_regulador_va_a_60_hz():
    """080:RF-52 — el catálogo Eaton es de 50 Hz; la red peruana, de 60."""
    fuente = (Path(__file__).resolve().parents[1] / 'src/convertersmartgrid/dgs.py').read_text(encoding='utf-8')
    fila = fuente[fuente.index('def _fila_regulador'):fuente.index('def _make_row')]
    assert 'frnom=60' in fila and 'FRECUENCIA_HZ' not in fila


def test_un_tramo_cerrado_en_una_salida_con_red_sigue_descartandose():
    """080:RF-27 — solo cambia la salida que se quedaría sin red."""
    from test_vnr_sqlserver import Motor, _tablas

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    tablas = _tablas()
    tablas['mtTramo'].append({'CodTramoMT': 'T9', 'CodSalidaMT': 'F1', 'CodTramoMTPadre': 'T3',
                              'CodNorma': 'AA05003'})
    tablas['verTramoMT'] += [
        {'CodTramoMT': 'T9', 'SecVertice': 1, 'UTMEste': 300.0, 'UTMNorte': 1.0},
        {'CodTramoMT': 'T9', 'SecVertice': 2, 'UTMEste': 300.1, 'UTMNorte': 1.0}]

    modelo, avisos = sv.modelo_canonico(sv.leer_datos(Motor(tablas=tablas).conectar('red')))

    assert 'T9' not in {s.section_id for s in modelo.sections}
    assert not [a for a in avisos if a['code'] == 'SALIDA_DE_TRAMO_NULO']


@pytest.mark.parametrize('red, nombre', [
    ('AN01-642-001', 'AN01-642-001'),   # el último trozo no identifica: hay 498 «001»
    ('NET_2030_142_IN111', 'IN111'),    # los nombres de siempre no cambian
    ('Feeder.A1', 'A1'),
    ('TI01', 'TI01'),
    ('0205', '0205'),
    ('NET_2030_150_NA205', 'NA205'),
])
def test_no_se_recorta_a_un_ultimo_trozo_numerico(red, nombre):
    """080:RF-28 — sin tocar los nombres que sí identifican al alimentador."""
    from convertersmartgrid.naming import feeder_short_name

    assert feeder_short_name(red) == nombre


def _validador():
    import importlib.util

    ruta = Path(__file__).resolve().parents[1] / 'tools' / 'validar_totalidad_vnr.py'
    espec = importlib.util.spec_from_file_location('validar_totalidad_vnr', ruta)
    modulo = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(modulo)
    return modulo


_BASE = {
    'salidas': {'F1': (2, 1), 'F2': (1, 1), 'VACIA': (0, 0)},   # {salida: (tramos, SED)}
    'tramos': 3,
    'seds': 2,
}


def test_el_cruce_da_ok_si_esta_todo():
    """080:RF-29, 080:RF-31 — la salida sin red se nombra y no es un fallo."""
    web = [{'network_id': 'F1', 'sections': 2, 'loads': 1}, {'network_id': 'F2', 'sections': 1, 'loads': 1}]

    informe = _validador().cruzar(_BASE, web)

    assert informe['ok'] is True
    assert informe['sin_red'] == ['VACIA']
    assert informe['faltan'] == [] and informe['sobran'] == []


@pytest.mark.parametrize('elegido, fuente, perfil, esperado', [
    (None, 'EPSG:24878', 'EPSG:32718', 'EPSG:24878'),   # la fuente antes que el perfil
    ('EPSG:32719', 'EPSG:24878', 'EPSG:32718', 'EPSG:32719'),   # el operador manda
    (None, None, 'EPSG:32718', 'EPSG:32718'),           # TXT sin CRS: el perfil, como siempre
    (None, None, None, None),                           # sin nada no se supone ninguno
])
def test_el_crs_de_la_fuente(monkeypatch, elegido, fuente, perfil, esperado):
    """080:RF-34 — Luz del Sur es PSAD56 y Electro Sur Este WGS84: ninguno se supone."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    monkeypatch.setattr(services, 'perfil_de', lambda _ws: SimpleNamespace(crs_origen=perfil))
    espacio = SimpleNamespace(
        options={'source_crs': elegido},
        inventory={'provenance': {'crs': fuente}} if fuente else None)

    assert services.crs_origen(espacio) == esperado


def test_la_copia_dice_su_crs_en_el_alcance():
    """080:RF-34 — el alcance de la carga lleva el CRS que declara ``empEmpresa``."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr as sv

    assert sv.crs_de_empresa([{'ZonaUTM': 18, 'Datum': 'PSAD56'}]) == 'EPSG:24878'
    assert sv.crs_de_empresa([{'ZonaUTM': 18, 'Datum': 'WGS84'}]) == 'EPSG:32718'
    # 055:RF-7: lo lleva la procedencia de la fuente, que es de donde lo lee la web.
    from convertersmartgrid.sources import vnr as adaptador

    fuente = Path(adaptador.__file__).read_text(encoding='utf-8')
    assert "'crs': modelo.metadata.get('source_crs')" in fuente


def test_el_cruce_reconoce_la_etiqueta_operativa():
    """080:RF-29 — Luz del Sur: la web lista «A01» y la base dice 100683102."""
    base = {**_BASE, 'etiquetas': {'F1': 'A01', 'F2': 'A02', 'VACIA': ''}}
    web = [{'network_id': 'A01', 'sections': 2, 'loads': 1}, {'network_id': 'A02', 'sections': 1, 'loads': 1}]

    informe = _validador().cruzar(base, web)

    assert informe['ok'] is True and informe['faltan'] == [] and informe['sobran'] == []


def test_el_cruce_lee_la_forma_real_de_la_api(cliente):
    """080:RF-29 — la lista simulada de estas pruebas no probaba la respuesta de ``/feeders``."""
    wid = cliente.post('/api/workspaces').json()['id']
    respuesta = cliente.get(f'/api/workspaces/{wid}/feeders').json()

    assert isinstance(_validador().alimentadores_de(respuesta), list)


def test_el_cruce_falla_y_nombra_lo_que_falta():
    """080:RF-30 — una salida con red fuera de la web, y una SED perdida."""
    web = [{'network_id': 'F1', 'sections': 2, 'loads': 0}]

    informe = _validador().cruzar(_BASE, web)

    assert informe['ok'] is False
    assert informe['faltan'] == [{'salida': 'F2', 'tramos': 1, 'sed': 1}]
    assert informe['sed']['base'] == 2 and informe['sed']['web'] == 0


def test_el_cruce_detecta_lo_que_la_base_no_tiene():
    """080:RF-30 — un alimentador en la web que la base no conoce tampoco cuadra."""
    web = [{'network_id': 'F1', 'sections': 2, 'loads': 1}, {'network_id': 'F2', 'sections': 1, 'loads': 1},
           {'network_id': 'OTRO', 'sections': 1, 'loads': 0}]

    informe = _validador().cruzar(_BASE, web)

    assert informe['ok'] is False and informe['sobran'] == ['OTRO']


# ------------------------------------------------------------------ API
@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    pytest.importorskip('httpx2')
    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'no-front'))
    raiz = tmp_path / 'web'
    catalogo = PublicationCatalog()
    for pid, resolucion in (('viejo', '186-2023-OS/CD'), ('nuevo', '208-2023-OS/CD')):
        catalogo.upsert_publication(Publication(
            publication_id=pid, title=f'VNR-GIS Empresa {resolucion}', company='Empresa',
            period_label='2022', regulatory_reference=resolucion,
            publication_type='REGULATORY_VNRGIS_PACKAGE', official_page=PAGINA_2025,
            download_url=f'https://www2.osinergmin.gob.pe/{pid}/Empresa.zip', file_name='Empresa.zip',
        ))
    catalogo.save(raiz / '_vnr_catalog')
    with TestClient(create_app(raiz, host='127.0.0.1')) as valor:
        yield valor


def test_la_api_marca_el_vigente_y_da_el_portal(cliente):
    """080:RF-9, 080:RF-14 — la interfaz no decide la vigencia; recibe enlaces oficiales."""
    cuerpo = cliente.get('/api/vnr/publications').json()
    filas = {f['publication_id']: f for f in cuerpo['publications']}
    assert filas['nuevo']['vigente'] is True and filas['viejo']['vigente'] is False
    assert filas['nuevo']['empresa'] == 'Empresa'
    assert filas['nuevo']['official_page'] == PAGINA_2025
    assert filas['nuevo']['regulatory_reference'] == '208-2023-OS/CD'
    assert cuerpo['portal'] == PORTAL_VNR


def _espera(cliente, trabajo):
    limite = time.monotonic() + 10
    while time.monotonic() < limite:
        estado = cliente.get('/api/jobs/' + trabajo).json()
        if estado['status'] in ('done', 'failed', 'cancelled'):
            return estado
        time.sleep(.02)
    raise AssertionError('el trabajo no terminó')


def test_descargar_asigna_la_copia_y_no_el_comprimido(cliente, monkeypatch):
    """080:RF-13, 080:RF-18 — la entrada queda con la copia de red, lista para cargar."""
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import DownloadManifest

    def bajar(self, url, destino, **_k):
        del self
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        _paquete_con_copia(destino)
        return DownloadManifest('nuevo', 'Empresa', '2022', url, '', 200, 'application/zip',
                                destino.stat().st_size, 'f' * 64, 'PASS')

    monkeypatch.setattr(DownloadManager, 'download', bajar)
    wid = cliente.post('/api/workspaces').json()['id']

    r = cliente.post(f'/api/workspaces/{wid}/vnr/download', json={'publication_id': 'nuevo'})

    assert r.status_code == 202, r.text
    estado = _espera(cliente, r.json()['id'])
    assert estado['status'] == 'done', estado
    entrada = estado['result']['workspace']['inputs']['vnr_package']
    assert entrada['name'] == 'EMPR_VNR_22.bak'
    assert estado['result']['workspace']['options']['input_mode'] == 'vnr'
    assert (Path(entrada['path']).parent / 'ConfigBD.config').is_file()
    assert not list(Path(entrada['path']).parent.glob('*.exe'))


def test_el_panel_elige_por_distribuidora_con_el_enlace_oficial():
    """080:RF-11, 080:RF-12, 080:RF-13, 080:RF-14, 080:RF-15, 080:RF-16, 080:RF-17 — los textos y acciones del panel; su comportamiento se prueba en el navegador (T4)."""
    panel = (Path(__file__).resolve().parents[1] / 'frontend/src/features/conversion/InputsPanel.tsx'
             ).read_text(encoding='utf-8')
    for texto in ('Distribuidora', 'Descargar y usar', 'Enlace oficial', 'Versiones anteriores',
                  'catalog?.portal', 'item.official_page', 'vigente', 'autoBuscada'):
        assert texto in panel, texto
