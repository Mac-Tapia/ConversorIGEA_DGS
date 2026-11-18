"""Spec 108 T1 — el estudio VAD se guarda aparte del PIDE y del PIT (108:RF-1).

Dos empresas sintéticas con perfiles distintos: ningún nombre, grupo ni periodo de una empresa real.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from convertersmartgrid.dominio.perfil_empresa import PerfilEmpresa
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.aplicacion.vad.estudio import EstudioVad, cargar_estudio, crear_estudio

EMPRESAS = (
    PerfilEmpresa(nombre='Distribuidora Sintética Norte', crs_origen='EPSG:3857'),
    PerfilEmpresa(nombre='Eléctrica Ficticia del Sur', crs_origen='EPSG:4326'),
)


def _huellas(carpeta):
    return {str(p.relative_to(carpeta)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(carpeta.rglob('*')) if p.is_file()}


@pytest.mark.parametrize('perfil', EMPRESAS, ids=('norte', 'sur'))
def test_crear_y_cargar_el_estudio(tmp_path, perfil):
    """108:RF-1 — el estudio guarda su empresa (del perfil), su grupo, su periodo y la versión del TdR."""
    estudio = crear_estudio(tmp_path, perfil, grupo=2, periodo='2031-2035', version_tdr='tdr-sintetico-v1')
    assert isinstance(estudio, EstudioVad)
    ruta = tmp_path / 'vad' / estudio.id / 'estudio.json'
    assert ruta.is_file()
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    assert datos['empresa'] == perfil.nombre
    assert datos['grupo'] == 2 and datos['periodo'] == '2031-2035'
    assert datos['version_tdr'] == 'tdr-sintetico-v1'
    assert cargar_estudio(tmp_path, estudio.id) == estudio


def test_dos_empresas_no_comparten_carpeta(tmp_path):
    """108:RF-1 — dos empresas en el mismo espacio dan dos estudios separados."""
    a = crear_estudio(tmp_path, EMPRESAS[0], grupo=1, periodo='2030-2034', version_tdr='v1')
    b = crear_estudio(tmp_path, EMPRESAS[1], grupo=1, periodo='2030-2034', version_tdr='v1')
    assert a.id != b.id
    assert cargar_estudio(tmp_path, a.id).empresa != cargar_estudio(tmp_path, b.id).empresa


def test_no_toca_las_carpetas_del_pide_ni_del_pit(tmp_path):
    """108:RF-1 — crear un estudio VAD no cambia ningún fichero del PIDE ni del PIT."""
    for carpeta, nombre in (('pide', 'F01.json'), ('pit', 'expediente.json')):
        (tmp_path / carpeta / 'x').mkdir(parents=True)
        (tmp_path / carpeta / 'x' / nombre).write_text('{"intacto": true}', encoding='utf-8')
    antes = _huellas(tmp_path)
    estudio = crear_estudio(tmp_path, EMPRESAS[0], grupo=1, periodo='2030-2034', version_tdr='v1')
    despues = _huellas(tmp_path)
    nuevos = set(despues) - set(antes)
    assert {k: v for k, v in despues.items() if k in antes} == antes
    assert nuevos and all(n.replace('\\', '/').startswith(f'vad/{estudio.id}/') for n in nuevos)


@pytest.mark.parametrize('campos', (
    {'grupo': 0, 'periodo': '2030-2034'},
    {'grupo': 1, 'periodo': '2030'},
    {'grupo': 1, 'periodo': '2034-2030'},
))
def test_rechaza_grupo_o_periodo_imposibles(tmp_path, campos):
    """108:RF-1 — sin grupo o periodo válidos no hay estudio, y no se escribe nada."""
    with pytest.raises(VadError):
        crear_estudio(tmp_path, EMPRESAS[0], version_tdr='v1', **campos)
    assert not (tmp_path / 'vad').exists()


def test_sin_empresa_en_el_perfil_no_hay_estudio(tmp_path):
    """108:RF-1, 108:RF-13 — la empresa viene del perfil; sin perfil no se supone ninguna."""
    with pytest.raises(VadError):
        crear_estudio(tmp_path, PerfilEmpresa(), grupo=1, periodo='2030-2034', version_tdr='v1')


def test_un_estudio_repetido_no_se_sobrescribe(tmp_path):
    """108:RF-1 — el mismo estudio dos veces no pisa el primero."""
    crear_estudio(tmp_path, EMPRESAS[1], grupo=1, periodo='2030-2034', version_tdr='v1')
    with pytest.raises(VadError):
        crear_estudio(tmp_path, EMPRESAS[1], grupo=1, periodo='2030-2034', version_tdr='v2')
