"""Spec 108 T11 — las observaciones del regulador, con su respuesta y la tabla o el cálculo que afectan (108:RF-12).

Dos empresas sintéticas; las tablas salen del registro real del TdR (``config/vad``) y los formatos del anexo 2
transcrito. Ningún nombre, número de oficio ni periodo de una empresa real.
"""
from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path

import pytest

from convertersmartgrid.perfil_empresa import PerfilEmpresa
from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.anexo2 import cargar_formatos
from convertersmartgrid.vad.estudio import crear_estudio

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO = RAIZ / 'config' / 'vad'
EMPRESAS = (PerfilEmpresa(nombre='Distribuidora Sintética Norte'), PerfilEmpresa(nombre='Eléctrica Ficticia del Sur'))
USOS = {'vad.frc': ('anualidad del VNR',), 'vad.igv_costos': ('costos sin IGV',)}
SEMILLA = 108_11


def _modulo():
    assert importlib.util.find_spec('convertersmartgrid.vad.observaciones') is not None, \
        'falta vad/observaciones.py (108 T11)'
    from convertersmartgrid.vad import observaciones
    return observaciones


def _estudio(tmp_path, perfil=EMPRESAS[0]):
    registro = cargar_registro(REGISTRO)
    estudio = crear_estudio(tmp_path / 'espacio', perfil, grupo=1, periodo='2041-2045', version_tdr='tdr-sintetico',
                            usos=USOS)
    return tmp_path / 'espacio', estudio.id, registro


def _tabla_y_formato(registro, rng):
    from convertersmartgrid.vad.tablas_resultados import tablas_registradas
    tablas, _ = tablas_registradas(registro)
    formatos = cargar_formatos(REGISTRO / 'anexo2_formatos.json')
    return rng.choice(tablas)['numero'], rng.choice(formatos.todos()).id, formatos


@pytest.mark.parametrize('perfil', EMPRESAS, ids=('norte', 'sur'))
def test_108_rf12_la_observacion_se_guarda_con_su_respuesta_y_lo_que_afecta(tmp_path, perfil):
    """108:RF-12 — cada observación queda en <espacio>/vad/<id>/observaciones.json con su número, su fecha, su texto,
    lo que afecta (tabla del registro, formato del anexo 2 o cálculo del estudio) y, al responderla, la respuesta, su
    sustento y qué cambió en cada destino."""
    obs = _modulo()
    espacio, id_estudio, registro = _estudio(tmp_path, perfil)
    rng = random.Random(SEMILLA)
    tabla, formato, formatos = _tabla_y_formato(registro, rng)
    numero = f'OBS-{rng.randint(1, 999)}'
    afecta = [{'tipo': 'tabla', 'id': tabla}, {'tipo': 'formato', 'id': formato},
              {'tipo': 'calculo', 'id': 'anualidad del VNR'}]
    nueva = obs.registrar_observacion(espacio, id_estudio, numero=numero, fecha='2041-06-01',
                                      texto='Sustentar el metrado de la red aérea', afecta=afecta, registro=registro,
                                      formatos=formatos)
    assert nueva.estado == 'pendiente' and [o.numero for o in obs.pendientes(espacio, id_estudio)] == [numero]
    hecha = obs.responder(espacio, id_estudio, numero, respuesta='Se corrige el metrado',
                          sustento='plano de la red, hoja 3', cambios={f'tabla {tabla}': 'baja el total de km'})
    assert hecha.estado == 'respondida' and obs.pendientes(espacio, id_estudio) == []
    ruta = espacio / 'vad' / id_estudio / 'observaciones.json'
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    guardada = datos['observaciones'][0]
    assert guardada['numero'] == numero and guardada['fecha'] == '2041-06-01'
    assert guardada['respuesta'] == 'Se corrige el metrado' and guardada['sustento'] == 'plano de la red, hoja 3'
    assert guardada['cambios'] == {f'tabla {tabla}': 'baja el total de km'}
    assert [d['tipo'] for d in guardada['afecta']] == ['tabla', 'formato', 'calculo']
    assert obs.cargar_observaciones(espacio, id_estudio) == [hecha]


def test_108_rf12_una_observacion_que_apunta_a_una_tabla_que_no_existe_se_rechaza(tmp_path):
    """108:RF-12 — una tabla que el registro no lista, un formato que el anexo 2 no tiene o un cálculo que el estudio
    no declara se rechazan nombrándolos, y no se guarda nada."""
    obs = _modulo()
    espacio, id_estudio, registro = _estudio(tmp_path)
    formatos = cargar_formatos(REGISTRO / 'anexo2_formatos.json')
    for destino in ({'tipo': 'tabla', 'id': '999'}, {'tipo': 'formato', 'id': 'A-XCIX'},
                    {'tipo': 'calculo', 'id': 'cálculo que no existe'}):
        with pytest.raises(VadError, match=destino['id']):
            obs.registrar_observacion(espacio, id_estudio, numero='1', fecha='2041-06-01', texto='x',
                                      afecta=[destino], registro=registro, formatos=formatos)
    assert not (espacio / 'vad' / id_estudio / 'observaciones.json').exists()


def test_108_rf12_la_respuesta_necesita_sustento_y_solo_cambia_lo_que_la_observacion_afecta(tmp_path):
    """108:RF-12 — sin sustento no hay respuesta; un cambio en una tabla que la observación no afecta, o un cambio sin
    decir qué cambió, se rechaza; un número repetido o una fecha que no es AAAA-MM-DD también."""
    obs = _modulo()
    espacio, id_estudio, registro = _estudio(tmp_path)
    tabla, _, formatos = _tabla_y_formato(registro, random.Random(SEMILLA + 1))
    obs.registrar_observacion(espacio, id_estudio, numero='7', fecha='2041-06-01', texto='x',
                              afecta=[{'tipo': 'tabla', 'id': tabla}], registro=registro, formatos=formatos)
    with pytest.raises(VadError, match='ya está registrada'):
        obs.registrar_observacion(espacio, id_estudio, numero='7', fecha='2041-06-02', texto='y',
                                  afecta=[{'tipo': 'tabla', 'id': tabla}], registro=registro, formatos=formatos)
    with pytest.raises(VadError, match='AAAA-MM-DD'):
        obs.registrar_observacion(espacio, id_estudio, numero='8', fecha='01/06/2041', texto='y',
                                  afecta=[{'tipo': 'tabla', 'id': tabla}], registro=registro, formatos=formatos)
    with pytest.raises(VadError, match='sustento'):
        obs.responder(espacio, id_estudio, '7', respuesta='se acepta', sustento='')
    with pytest.raises(VadError, match='no afecta'):
        obs.responder(espacio, id_estudio, '7', respuesta='se acepta', sustento='s',
                      cambios={'formato A-VI': 'otra cosa'})
    with pytest.raises(VadError, match='no dice qué cambió'):
        obs.responder(espacio, id_estudio, '7', respuesta='se acepta', sustento='s', cambios={f'tabla {tabla}': ''})
    assert [o.estado for o in obs.cargar_observaciones(espacio, id_estudio)] == ['pendiente']


def test_108_rf12_los_formatos_b_son_los_de_la_empresa_modelo(tmp_path):
    """108:RF-12 — una observación puede afectar al formato B de la empresa modelo (los mismos cuadros del anexo 2 con
    prefijo B), y el estudio de otra empresa no ve sus observaciones."""
    obs = _modulo()
    espacio, id_a, registro = _estudio(tmp_path, EMPRESAS[0])
    id_b = crear_estudio(espacio, EMPRESAS[1], grupo=1, periodo='2041-2045', version_tdr='tdr-sintetico').id
    formatos = cargar_formatos(REGISTRO / 'anexo2_formatos.json')
    b = 'B-' + formatos.todos()[0].id.split('-', 1)[1]
    obs.registrar_observacion(espacio, id_a, numero='1', fecha='2041-06-01', texto='x',
                              afecta=[{'tipo': 'formato', 'id': b}], registro=registro, formatos=formatos)
    guardadas = obs.cargar_observaciones(espacio, id_a)
    # Antes de indexar: sin la observación guardada, la prueba cae por su aserción, no por un IndexError.
    assert len(guardadas) == 1, f'la observación con el formato B no se guarda: {guardadas}'
    assert [d.id for d in guardadas[0].afecta] == [b]
    assert obs.cargar_observaciones(espacio, id_b) == []
