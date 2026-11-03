"""Spec 072: años del estudio calculados y costos oficiales que no se suponen."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from convertersmartgrid.costos_fuentes import (CostosError, FuenteCostos, cruzar_codigos, leer_sicodi,
                                               partir_codigo_vnr)
from convertersmartgrid.estudio_planeamiento import EstudioError, aviso_del_anio_medido, estudio_de

RAIZ = Path(__file__).resolve().parents[1]
HORIZONTE = json.loads((RAIZ / 'config/pide_universal_2017.json').read_text(encoding='utf-8'))['horizonte']
CAB = ('EMPRESA\tSECTOR TIPICO\tCOD GRUPO\tGRUPO\tCOD FAMILIA\tFAMILIA\tCOD SUBFAMILIA\tSUBFAMILIA\tCOD COSTINVER\t'
       'COD TEN NOMI\tDSC TEN NOMI\tCOD SECUNDARIO\tDSC SECUNDARIO\tNOMBRE\tCOSTO MAT\tCOSTO STOCK\tCOSTO MO\t'
       'COSTO TRANS\tCOSTO OBRA\tCOSTO GASTOS GNRAL\tCOSTO INGENIERIA\tCOSTO INTERCALARIO\tTOTAL')


def _fila(codigo, ten, sec, sector, total):
    return (f'E\t{sector}\t1\tMT\tA\tRED\tA1\tRED\t{codigo}\t{ten}\tkV\t{sec}\tEST\tRED {codigo}\t1\t1\t1\t1\t4\t1\t1\t1\t{total}')


@pytest.fixture
def zip_sicodi(tmp_path):
    ruta = tmp_path / 's.zip'
    texto = '\n'.join([CAB, _fila('AA03503', 'G', 'C', 'ST2', 100.0), _fila('AA03503', 'G', 'A', 'ST2', 90.0),
                       _fila('AA03503', 'D', 'C', 'ST2', 80.0), _fila('AA03503', 'G', 'C', 'ST3', 70.0)])
    with zipfile.ZipFile(ruta, 'w') as z:
        z.writestr('Archivos/Instalacion.txt', texto)
    return ruta


def _tabla(ruta, **kw):
    return leer_sicodi(ruta, resolucion='R-1', anio=2030, moneda='M', url='https://x', fecha_descarga='F', **kw)


@pytest.mark.parametrize('presentacion', [2027, 2031, 2099])
def test_los_anios_salen_de_la_presentacion_sin_fijos(presentacion):
    """072:RF-1, 072:RF-2 — cualquier ciclo: año 00 = presentación − 1, y los años desde él."""
    e = estudio_de(presentacion, HORIZONTE)
    assert e.anio_base == presentacion - 1
    assert [e.calendario(a) for a in e.detalle_pide] == [presentacion - 1 + a for a in (4, 5, 6, 7)]
    assert [e.calendario(a) for a in e.largo_plazo] == [presentacion - 1 + a for a in (4, 8, 12, 16, 20)]
    s = e.siguiente()
    assert s.anio_presentacion == presentacion + 4 and s.anio_base == presentacion + 3
    assert e.resumen()['detalle_pide']['04'] == presentacion + 3


def test_el_caso_de_2027_es_el_del_usuario():
    """072:RF-1 — presentación 2027: año 00 = 2026 y detalle 2030-2033."""
    e = estudio_de(2027, HORIZONTE)
    assert e.anio_base == 2026 and [e.calendario(a) for a in e.detalle_pide] == [2030, 2031, 2032, 2033]


def test_sin_anio_escrito_en_el_codigo():
    """072:RF-1 — ningún año de calendario fijo en el módulo del estudio, salvo su procedencia."""
    codigo = (RAIZ / 'src/convertersmartgrid/estudio_planeamiento.py').read_text(encoding='utf-8')
    cuerpo = codigo.split('"""', 2)[2]
    assert not re.search(r'\b20\d\d\b', cuerpo)


@pytest.mark.parametrize('anio, horizonte', [
    (None, HORIZONTE), ('2027', HORIZONTE), (2027, {}), (2027, {**HORIZONTE, 'largo_plazo': []}),
    (2027, {**HORIZONTE, 'detalle_pide': [4.5]}),
])
def test_estudio_invalido_lo_dice(anio, horizonte):
    """072:RF-1 — no se supone ningún año."""
    with pytest.raises(EstudioError):
        estudio_de(anio, horizonte)


def test_aviso_si_el_caso_base_no_es_del_anio_00():
    """072:RF-3 — lo dice y sigue."""
    e = estudio_de(2027, HORIZONTE)
    assert aviso_del_anio_medido(e, 2026) is None
    assert '2025' in aviso_del_anio_medido(e, 2025) and '2026' in aviso_del_anio_medido(e, 2025)
    assert 'no consta' in aviso_del_anio_medido(e, None)


def test_el_costo_depende_de_cuatro_datos(zip_sicodi):
    """072:RF-5, 072:RF-7 — cambia con tensión, estructura y sector; la fuente queda declarada."""
    t = _tabla(zip_sicodi)
    assert t.buscar('AA03503', 'G', 'C', 'ST2').total == 100.0
    assert t.buscar('AA03503', 'G', 'A', 'ST2').total == 90.0
    assert t.buscar('AA03503', 'D', 'C', 'ST2').total == 80.0
    assert t.buscar('AA03503', 'G', 'C', 'ST3').total == 70.0
    f = t.buscar('AA03503', 'G', 'C', 'ST2').fuente
    assert f.resolucion == 'R-1' and f.moneda == 'M' and len(f.huella) == 64 and f.url and f.fecha_descarga


def test_lo_que_no_cruza_se_nombra_sin_costo(zip_sicodi):
    """072:RF-7 — nunca el más parecido; con su motivo."""
    r = cruzar_codigos([('AA03503G', 30), ('AA03503H', 10), ('ZZ99999G', 5)], _tabla(zip_sicodi),
                       sector='ST2', estructura='C')
    assert r['codigos_con_costo'] == 1 and r['fraccion_con_costo'] == pytest.approx(30 / 45)
    motivos = {x['codigo']: x['motivo'] for x in r['sin_costo']}
    assert 'tensión «H»' in motivos['AA03503H'] and 'código ZZ99999' in motivos['ZZ99999G']
    sin_sector = cruzar_codigos([('AA03503G', 1)], _tabla(zip_sicodi), sector='', estructura='C')
    assert 'sector' in sin_sector['sin_costo'][0]['motivo']
    sin_est = cruzar_codigos([('AA03503G', 1)], _tabla(zip_sicodi), sector='ST2', estructura='B')
    assert 'estructura' in sin_est['sin_costo'][0]['motivo']


@pytest.mark.parametrize('codigo, partes', [('AA03503G', ('AA03503', 'G')), ('12345', ('12345', '')), ('', ('', ''))])
def test_partir_codigo(codigo, partes):
    """072:RF-7 — la letra final es la tensión; sin ella, no se inventa."""
    assert partir_codigo_vnr(codigo) == partes


def test_sin_factor_salvo_con_sustento(zip_sicodi):
    """072:RF-8 — por defecto, el costo oficial; un factor sin sustento se rechaza."""
    assert _tabla(zip_sicodi).buscar('AA03503', 'G', 'C', 'ST2').total == 100.0
    with pytest.raises(CostosError, match='sustento'):
        _tabla(zip_sicodi, factor=1.8)
    con = _tabla(zip_sicodi, factor=1.5, sustento_factor='Informe X')
    assert con.buscar('AA03503', 'G', 'C', 'ST2').total == pytest.approx(150.0)


def test_la_fuente_declara_su_procedencia():
    """072:RF-9 — sin resolución o moneda no hay fuente: el TXT no dice la moneda."""
    with pytest.raises(CostosError, match='moneda'):
        FuenteCostos('SICODI', 'distribucion', 'R', 2030, '', 'u', 'f', 'h')
    with pytest.raises(CostosError, match='resolucion'):
        FuenteCostos('SICODI', 'distribucion', '', 2030, 'M', 'u', 'f', 'h')


def test_fichero_incompleto_falla_cerrado(tmp_path):
    """072:RF-5 — columnas que faltan o costo no numérico se dicen."""
    malo = tmp_path / 'm.zip'
    with zipfile.ZipFile(malo, 'w') as z:
        z.writestr('Instalacion.txt', 'A\tB\n1\t2')
    with pytest.raises(CostosError, match='columnas'):
        _tabla(malo)
    otro = tmp_path / 'o.zip'
    with zipfile.ZipFile(otro, 'w') as z:
        z.writestr('Otro.txt', 'x')
    with pytest.raises(CostosError, match='no trae'):
        _tabla(otro)
    texto = tmp_path / 't.zip'
    with zipfile.ZipFile(texto, 'w') as z:
        z.writestr('Instalacion.txt', CAB + '\n' + _fila('AA', 'G', 'C', 'ST2', 'x'))
    with pytest.raises(CostosError, match='no numérico'):
        _tabla(texto)
    sin_total = tmp_path / 'st.zip'
    with zipfile.ZipFile(sin_total, 'w') as z:
        z.writestr('Instalacion.txt', CAB + '\n' + _fila('AA', 'G', 'C', 'ST2', ''))
    with pytest.raises(CostosError, match='sin total'):
        _tabla(sin_total)


def test_componente_en_blanco_es_sin_dato_no_cero(tmp_path):
    """072:RF-5 — como en el SICODI real: hay total, y el componente que falta no se vuelve cero."""
    ruta = tmp_path / 'b.zip'
    fila = 'E	ST2	1	MT	A	RED	A1	RED	AA	G	kV	C	EST	RED					4	1	1	1	50'
    with zipfile.ZipFile(ruta, 'w') as z:
        z.writestr('Instalacion.txt', CAB + '\n' + fila)
    c = _tabla(ruta).buscar('AA', 'G', 'C', 'ST2')
    assert c.total == 50.0 and c.componentes['material'] is None and c.componentes['obra'] == 4.0


def test_datos_del_plan_activan_el_estudio():
    """072:RF-1 — el servicio del PIDE forma los años desde el plan, no de una lista fija."""
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert "estudio_de(plan_pide['anio_presentacion']" in fuente
