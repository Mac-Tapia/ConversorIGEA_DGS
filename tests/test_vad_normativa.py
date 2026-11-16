"""Spec 108 T2 — el registro normativo común y la conformidad del estudio VAD (108:RF-9, 108:RF-10).

Los registros de las pruebas son sintéticos (normas y valores inventados para la prueba, sin ninguna empresa).
El registro real del TdR (``config/vad/tdr_vad_2026.json``) se comprueba solo en su forma: cada regla citada,
su esquema y sus estados.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from convertersmartgrid.perfil_empresa import PerfilEmpresa
from convertersmartgrid.registro_normativo import ESTADOS, RegistroError, cargar_registro
from convertersmartgrid.vad.estudio import cargar_estudio, comprobar_estudio, crear_estudio

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json'
TDR = RAIZ / 'config' / 'vad' / 'tdr_vad_2026.json'
EMPRESAS = (PerfilEmpresa(nombre='Distribuidora Sintética Norte'), PerfilEmpresa(nombre='Eléctrica Ficticia del Sur'))
USOS = {'vad.frc': ('tabla A',), 'vad.igv_costos': ('tabla B', 'costos')}


def _norma(estado='vigente_comprobada', igv='excluido', cita='«texto literal»', valor=0.5):
    return {
        'esquema': 'registro_normativo_v1',
        'normas': [{
            'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': estado,
            'sha256': 'a' * 64, 'version': 'v1', 'vigencia_desde': '2001-01-01',
            'reglas': [
                {'clave': 'vad.grupo.3.periodo', 'valor': '2041-2045', 'cita_literal': '«grupo 3»',
                 'lineas': '10-12'},
                {'clave': 'vad.frc', 'valor': valor, 'unidad': 'adimensional', 'cita_literal': cita,
                 'lineas': '20'},
                {'clave': 'vad.igv_costos', 'valor': 'sin IGV', 'cita_literal': '«sin IGV»', 'lineas': '30',
                 'moneda': 'XUS', 'igv': igv},
            ]}]}


def _registro(tmp_path, **kw):
    ruta = tmp_path / 'reg' / 'tdr.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(_norma(**kw)), encoding='utf-8')
    return cargar_registro(ruta.parent)


def _estudio(tmp_path, registro, perfil=EMPRESAS[0]):
    return crear_estudio(tmp_path / 'espacio', perfil, grupo=3, periodo='2041-2045', version_tdr='tdr-sintetico',
                         registro=registro, usos=USOS)


@pytest.mark.parametrize('perfil', EMPRESAS, ids=('norte', 'sur'))
def test_conforme_con_todo_vigente_y_citado(tmp_path, perfil):
    """108:RF-10 — con el TdR vigente y comprobado, sus reglas citadas y el IGV leído, el estudio es conforme."""
    registro = _registro(tmp_path)
    estudio = comprobar_estudio(tmp_path / 'espacio', _estudio(tmp_path, registro, perfil).id, registro)
    assert estudio.estado == 'conforme', estudio.motivos
    assert cargar_estudio(tmp_path / 'espacio', estudio.id).estado == 'conforme'


@pytest.mark.parametrize('estado', ('prepublicada', 'no_verificada', 'derogada'))
def test_tdr_no_vigente_deja_no_conforme(tmp_path, estado):
    """108:RF-10 — un TdR en proyecto, pendiente de verificar o derogado deja el estudio no_conforme y lo nombra."""
    datos = _norma(estado=estado)
    datos['normas'][0]['sha256'] = '' if estado == 'no_verificada' else 'a' * 64
    (tmp_path / 'reg').mkdir()
    (tmp_path / 'reg' / 't.json').write_text(json.dumps(datos), encoding='utf-8')
    registro = cargar_registro(tmp_path / 'reg')
    estudio = comprobar_estudio(tmp_path / 'espacio', _estudio(tmp_path, registro).id, registro)
    assert estudio.estado == 'no_conforme'
    assert any('tdr-sintetico' in m and estado in m for m in estudio.motivos), estudio.motivos


def test_igv_sin_leer_deja_no_conforme(tmp_path):
    """108:RF-9, 108:RF-10 — una cifra con el IGV sin leer no se emite como conforme."""
    registro = _registro(tmp_path, igv='sin_leer')
    estudio = comprobar_estudio(tmp_path / 'espacio', _estudio(tmp_path, registro).id, registro)
    assert estudio.estado == 'no_conforme'
    assert any('vad.igv_costos' in m and 'IGV' in m for m in estudio.motivos), estudio.motivos


def test_regla_sin_cita_deja_no_conforme(tmp_path):
    """108:RF-9 — una regla sin cita literal no obliga, y el estudio que la usa queda no_conforme."""
    registro = _registro(tmp_path, cita='')
    assert not registro.regla('vad.frc').obligatoria
    estudio = comprobar_estudio(tmp_path / 'espacio', _estudio(tmp_path, registro).id, registro)
    assert estudio.estado == 'no_conforme'
    assert any('vad.frc' in m and 'cita' in m for m in estudio.motivos), estudio.motivos


def test_grupo_o_periodo_que_el_tdr_no_registra(tmp_path):
    """108:RF-10 — si el TdR no registra el grupo del estudio con ese periodo, el estudio no es conforme."""
    registro = _registro(tmp_path)
    estudio = crear_estudio(tmp_path / 'espacio', EMPRESAS[1], grupo=3, periodo='2046-2050',
                            version_tdr='tdr-sintetico', registro=registro, usos=USOS)
    estudio = comprobar_estudio(tmp_path / 'espacio', estudio.id, registro)
    assert estudio.estado == 'no_conforme'
    assert any('grupo 3' in m for m in estudio.motivos), estudio.motivos


def test_cambio_del_tdr_a_mitad_deja_desactualizado(tmp_path):
    """108:RF-9 — el estudio conserva su versión; si el registro cambia, queda desactualizado y nombra lo afectado."""
    registro = _registro(tmp_path)
    estudio = _estudio(tmp_path, registro)
    nuevo = _registro(tmp_path, valor=0.6)
    assert nuevo.instantanea() != registro.instantanea()
    estudio = comprobar_estudio(tmp_path / 'espacio', estudio.id, nuevo)
    assert estudio.estado == 'desactualizado'
    assert any('vad.frc' in m and 'tabla A' in m for m in estudio.motivos), estudio.motivos
    assert not any('vad.igv_costos' in m for m in estudio.motivos), estudio.motivos
    assert cargar_estudio(tmp_path / 'espacio', estudio.id).instantanea_registro == registro.instantanea()


def test_vigente_comprobada_sin_huella_no_se_admite(tmp_path):
    """108:RF-9 — «comprobada» exige la huella del texto leído."""
    datos = _norma()
    datos['normas'][0]['sha256'] = ''
    (tmp_path / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    with pytest.raises(RegistroError):
        cargar_registro(tmp_path / 'r.json')


def test_regla_prepublicada_o_no_verificada_no_obliga(tmp_path):
    """108:RF-10 — solo obliga lo vigente y comprobado (contrato común con la 107)."""
    for estado in ('prepublicada', 'no_verificada'):
        datos = _norma(estado=estado)
        (tmp_path / f'{estado}.json').write_text(json.dumps(datos), encoding='utf-8')
        regla = cargar_registro(tmp_path / f'{estado}.json').regla('vad.frc')
        assert regla.estado == estado and not regla.obligatoria


def test_el_registro_del_tdr_cumple_el_esquema_y_cada_regla_esta_citada():
    """108:RF-9 — el registro transcrito del TdR valida contra su esquema; cada regla trae cita y líneas, y su moneda
    e IGV cuando es una cifra monetaria."""
    esquema = json.loads(ESQUEMA.read_text(encoding='utf-8'))
    datos = json.loads(TDR.read_text(encoding='utf-8'))
    jsonschema.validate(datos, esquema)
    registro = cargar_registro(TDR)
    assert {n.estado_juridico for n in registro.normas.values()} <= set(ESTADOS)
    reglas = [r for n in registro.normas.values() for r in n.reglas]
    assert reglas
    assert all(r.citada for r in reglas), [r.clave for r in reglas if not r.citada]
    for norma in registro.normas.values():
        for otra in norma.modificada_por:
            assert norma.acto in registro.norma(otra).modifica


def test_el_tdr_registra_los_dos_grupos_con_su_periodo():
    """108:RF-10 — los grupos y sus periodos salen del registro (Cuadro N° 1 del TdR), no del código."""
    registro = cargar_registro(TDR)
    periodos = {registro.regla(f'vad.grupo.{g}.periodo').regla.valor for g in (1, 2)}
    assert len(periodos) == 2 and all('-' in p for p in periodos)
