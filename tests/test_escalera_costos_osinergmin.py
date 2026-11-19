"""072:RF-46 — los costos de la escalera y del PIDE: libro CAPEX real → SICODI vigente de Osinergmin → perfil → deducido
o de referencia, por confirmar (042:RF-54 se conserva como último escalón).

Una alternativa que el libro no traía salía del perfil o de una referencia «por confirmar», aunque el espacio tuviera el
costo estándar oficial de Osinergmin. El SICODI de estas pruebas es sintético, con la forma de su Instalacion.txt y
costos ficticios; ningún precio ni código de una empresa real.
"""
from __future__ import annotations

import hashlib
import inspect
import zipfile
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion import escalera_optima as eo
from convertersmartgrid.aplicacion.costos_fuentes import leer_sicodi
from convertersmartgrid.presentacion.web import services

CAB = ('EMPRESA\tSECTOR TIPICO\tCOD GRUPO\tGRUPO\tCOD FAMILIA\tFAMILIA\tCOD SUBFAMILIA\tSUBFAMILIA\tCOD COSTINVER\t'
       'COD TEN NOMI\tDSC TEN NOMI\tCOD SECUNDARIO\tDSC SECUNDARIO\tNOMBRE\tCOSTO MAT\tCOSTO STOCK\tCOSTO MO\t'
       'COSTO TRANS\tCOSTO OBRA\tCOSTO GASTOS GNRAL\tCOSTO INGENIERIA\tCOSTO INTERCALARIO\tTOTAL')
PERFIL = {'escalera': {'moneda': 'M', 'escala_capex': 1, 'costos_unitarios': {'bancos': 7.0}, 'cumplimiento': 0.95,
                       'sorteos': 200, 'tolerancia_pu': 0.005, 'tolerancia_carga_pct': 1.0},
          'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
          'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
CODIGOS = {'cambio_seccion': 'XX00001G', 'nueva_terna': 'XX00002G'}


def _fila(codigo, ten, est, sector, total):
    return f'E\t{sector}\t1\tMT\tA\tRED\tA1\tRED\t{codigo}\t{ten}\tkV\t{est}\tEST\tRED {codigo}\t1\t1\t1\t1\t4\t1\t1\t1\t{total}'


def _zip(ruta: Path) -> Path:
    texto = '\n'.join([CAB, _fila('XX00001', 'G', 'C', 'ST9', 111.0), _fila('XX00002', 'G', 'C', 'ST9', 222.0),
                       _fila('XX00002', 'G', 'A', 'ST9', 333.0)])
    with zipfile.ZipFile(ruta, 'w') as z:
        z.writestr('Archivos/Instalacion.txt', texto)
    return ruta


def _tabla(tmp_path, moneda='M'):
    return leer_sicodi(_zip(tmp_path / 's.zip'), resolucion='R-sintetica', anio=2030, moneda=moneda,
                       url='https://ejemplo.invalid', fecha_descarga='2030-01-01')


def _osinergmin(tabla, codigos, **kw):
    assert hasattr(eo, 'costos_osinergmin'), '072:RF-46: la escalera no lee el costo estándar de Osinergmin'
    return eo.costos_osinergmin(tabla, codigos, **kw)


def _alternativas(capex, p, oficiales):
    assert 'oficiales' in inspect.signature(eo.costos_de_alternativas).parameters, \
        '072:RF-46: costos_de_alternativas no recibe los costos oficiales'
    return eo.costos_de_alternativas(capex, p, oficiales)


def _web(raiz, perfil, moneda):
    assert hasattr(services, '_escalera_costos_osinergmin'), '072:RF-46: la web no declara los costos de Osinergmin'
    return services._escalera_costos_osinergmin(raiz, perfil, moneda)


def test_072_rf46_el_sicodi_va_entre_el_libro_y_el_perfil(tmp_path):
    """072:RF-46: el libro manda; lo que no trae sale del SICODI; después el perfil; y lo demás, por confirmar."""
    oficiales, avisos = _osinergmin(_tabla(tmp_path), CODIGOS, sector='ST9', estructura='C', moneda='M')
    assert avisos == [] and oficiales['nueva_terna']['costo_unitario'] == pytest.approx(222.0)
    libro = {'cambio_seccion': {'costo_unitario': 50.0, 'unidad': 'km'}}
    costos = _alternativas(libro, eo.parametros(PERFIL), oficiales)
    assert costos['cambio_seccion']['costo_unitario'] == pytest.approx(50.0) and costos['cambio_seccion']['origen'] == 'capex'
    assert costos['nueva_terna']['costo_unitario'] == pytest.approx(222.0)
    assert costos['nueva_terna']['origen'].startswith('Osinergmin, SICODI R-sintetica (2030), XX00002G')
    assert costos['bancos']['origen'] == 'perfil'
    assert 'por confirmar' in costos['cambio_tension']['origen']


def test_072_rf46_solo_el_costo_exacto_y_lo_que_no_cruza_se_dice(tmp_path):
    """072:RF-46 con RF-7: sin la estructura o el sector exactos no hay costo oficial; el aviso lo dice."""
    oficiales, avisos = _osinergmin(_tabla(tmp_path), {**CODIGOS, 'cambio_tension': 'XX00009G'}, sector='ST9',
                                    estructura='C', moneda='M')
    assert set(oficiales) == {'cambio_seccion', 'nueva_terna'}
    assert len(avisos) == 1 and '«cambio_tension» (XX00009G) sin costo' in avisos[0]
    ninguno, avisos = _osinergmin(_tabla(tmp_path), CODIGOS, sector='ST1', estructura='C', moneda='M')
    assert ninguno == {} and len(avisos) == 2


def test_072_rf46_otra_moneda_no_se_usa_sin_tipo_de_cambio(tmp_path):
    """072:RF-46: un SICODI en otra moneda que la de trabajo no se usa ni se convierte suponiendo 1."""
    oficiales, avisos = _osinergmin(_tabla(tmp_path, moneda='OTRA'), CODIGOS, sector='ST9', estructura='C', moneda='M')
    assert oficiales == {} and 'sin tipo de cambio no se usa' in avisos[0]


def test_072_rf46_sin_osinergmin_la_referencia_sigue_por_confirmar():
    """072:RF-46 con 042:RF-54: sin costos oficiales, nada cambia: ninguna obra queda sin costo."""
    p = eo.parametros(PERFIL)
    assert _alternativas({}, p, None) == eo.costos_de_alternativas({}, p)
    costos = _alternativas({}, p, {})
    assert all(c.get('costo_unitario') for c in costos.values())
    assert all('por confirmar' in c['origen'] for k, c in costos.items() if k != 'bancos')


def _perfil_web(raiz: Path, sha: str | None = None, **cambio) -> dict:
    ruta = _zip(raiz / 'sicodi_sintetico.zip')
    fuente = {'lector': 'sicodi', 'fichero': ruta.name, 'sha256': sha or hashlib.sha256(ruta.read_bytes()).hexdigest(),
              'vigencia_desde': '2000-01-01', 'resolucion': 'R-sintetica', 'anio': 2030, 'moneda': 'M',
              'url': 'https://ejemplo.invalid', 'fecha_descarga': '2030-01-01'}
    conf = {'fuentes': [fuente], 'sector_tipico': 'ST9', 'estructura': 'C', 'codigos': CODIGOS, **cambio}
    return {**PERFIL, 'escalera': {**PERFIL['escalera'], 'costos_osinergmin': conf}}


def test_072_rf46_la_web_lee_el_sicodi_vigente_del_espacio_por_su_huella(tmp_path):
    """072:RF-46: la declaración del perfil, con el fichero del espacio comprobado por su sha256 y su vigencia."""
    costos, avisos = _web(tmp_path, _perfil_web(tmp_path), 'M')
    assert avisos == [] and set(costos) == {'cambio_seccion', 'nueva_terna'}
    assert 'huella' in costos['cambio_seccion']['origen']


def test_072_rf46_la_web_no_usa_una_fuente_alterada_ni_incompleta(tmp_path):
    """072:RF-46: otra huella, otro lector o sin sector: no se usa y el aviso lo dice; sin declaración, nada cambia."""
    assert _web(tmp_path, PERFIL, 'M') == ({}, [])
    costos, avisos = _web(tmp_path, _perfil_web(tmp_path, sha='0' * 64), 'M')
    assert costos == {} and 'sha256' in avisos[0] and 'no se usan' in avisos[0]
    perfil = _perfil_web(tmp_path)
    perfil['escalera']['costos_osinergmin']['fuentes'][0]['lector'] = 'modulos_transmision'
    costos, avisos = _web(tmp_path, perfil, 'M')
    assert costos == {} and 'lector' in avisos[0]
    costos, avisos = _web(tmp_path, _perfil_web(tmp_path, sector_tipico=''), 'M')
    assert costos == {} and 'sector_tipico' in avisos[0]
    sin_vigente = _perfil_web(tmp_path)
    sin_vigente['escalera']['costos_osinergmin']['fuentes'][0]['vigencia_desde'] = '2999-01-01'
    costos, avisos = _web(tmp_path, sin_vigente, 'M')
    assert costos == {} and 'ninguna fuente vigente' in avisos[0]
