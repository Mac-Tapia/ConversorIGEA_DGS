"""Spec 108 T18 — verificación de la calidad de servicio con los indicadores y límites del registro (108:RF-18).

Indicadores y límites sintéticos («i_max», con límite máximo, e «i_min», con límite mínimo). Los límites reales de la
NTCSE y la NTCSER no están transcritos: con el registro real, cada indicador queda sin verificar y lo dice.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.calidad import indicadores, verificar_calidad

RAIZ = Path(__file__).resolve().parents[1]
INDICADORES = [{'clave': 'i_max', 'nombre': 'Indicador máximo', 'unidad': 'u/semestre', 'sentido': 'maximo'},
               {'clave': 'i_min', 'nombre': 'Indicador mínimo', 'unidad': '%', 'sentido': 'minimo'}]


def _registro(tmp_path, limites=None, estado='vigente_comprobada', lista=None):
    limites = {'i_max': 10.0, 'i_min': 95.0} if limites is None else limites
    reglas = [{'clave': 'vad.calidad.indicadores', 'valor': lista if lista is not None else INDICADORES,
               'cita_literal': '«indicadores»', 'lineas': '1'}]
    reglas += [{'clave': f'vad.calidad.limite.{k}', 'valor': v, 'cita_literal': f'«{k}»', 'lineas': '2'}
               for k, v in limites.items()]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'norma-calidad-sintetica', 'titulo': 'Norma sintética', 'estado_juridico': estado,
        'sha256': 'f' * 64, 'reglas': reglas}]}
    ruta = tmp_path / 'reg' / 'n.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(ruta.parent)


def test_un_caso_que_no_cumple_nombra_el_indicador(tmp_path):
    """108:RF-18 — un indicador por encima del máximo (o por debajo del mínimo) no cumple y se nombra con su valor y
    su límite; los demás cumplen."""
    r = verificar_calidad(_registro(tmp_path), {'S1': {'i_max': 12.5, 'i_min': 99.0},
                                                'S2': {'i_max': 3.0, 'i_min': 90.0}})
    assert r.estado == 'no_cumple'
    malos = {(v.sistema, v.indicador) for v in r.no_cumplen}
    assert malos == {('S1', 'i_max'), ('S2', 'i_min')}
    s1 = next(v for v in r.no_cumplen if v.sistema == 'S1')
    assert 'Indicador máximo' in s1.motivo and '12.5' in s1.motivo and '10.0' in s1.motivo


def test_un_caso_que_cumple(tmp_path):
    """108:RF-18 — en el límite exacto cumple; todo en norma da «cumple»."""
    r = verificar_calidad(_registro(tmp_path), {'S1': {'i_max': 10.0, 'i_min': 95.0}})
    assert r.estado == 'cumple' and not r.no_cumplen and not r.sin_verificar


def test_limite_sin_registrar_o_valor_sin_calcular_no_se_da_por_cumplido(tmp_path):
    """108:RF-18 — sin límite registrado, con un límite que no obliga o sin valor calculado, el indicador queda sin
    verificar y lo dice; nunca «cumple»."""
    sin_limite = verificar_calidad(_registro(tmp_path, limites={'i_max': 10.0}), {'S1': {'i_max': 1.0, 'i_min': 1.0}})
    assert sin_limite.estado == 'sin_verificar'
    assert 'vad.calidad.limite.i_min' in sin_limite.sin_verificar[0].motivo
    sin_valor = verificar_calidad(_registro(tmp_path), {'S1': {'i_max': 1.0}})
    assert sin_valor.estado == 'sin_verificar' and 'sin valor calculado' in sin_valor.sin_verificar[0].motivo
    no_obliga = verificar_calidad(_registro(tmp_path, estado='prepublicada'), {'S1': {'i_max': 1.0, 'i_min': 99.0}})
    assert no_obliga.estado == 'sin_verificar' and 'no obliga' in no_obliga.sin_verificar[0].motivo


def test_entradas_invalidas_se_rechazan(tmp_path):
    """108:RF-18 — sin sistemas, con un indicador que el registro no tiene, con un valor que no es número o con un
    registro mal formado, se rechaza con mensaje."""
    reg = _registro(tmp_path)
    with pytest.raises(VadError, match='ningún sistema'):
        verificar_calidad(reg, {})
    with pytest.raises(VadError, match='i_otro'):
        verificar_calidad(reg, {'S1': {'i_otro': 1.0}})
    with pytest.raises(VadError, match='no es un número'):
        verificar_calidad(reg, {'S1': {'i_max': 'alto'}})
    with pytest.raises(VadError, match='sentido'):
        indicadores(_registro(tmp_path, lista=[dict(INDICADORES[0], sentido='medio')]))


def test_con_el_registro_real_los_limites_quedan_sin_verificar():
    """108:RF-18 — el registro real trae los indicadores del TdR pero no los límites de la NTCSE ni de la NTCSER:
    cada indicador queda sin verificar y nombra la regla que falta (bloqueo B2)."""
    reg = cargar_registro(RAIZ / 'config' / 'vad')
    claves = [i.clave for i in indicadores(reg)]
    r = verificar_calidad(reg, {'S1': dict.fromkeys(claves, 1.0)})
    assert r.estado == 'sin_verificar' and len(r.sin_verificar) == len(claves)
    assert all('vad.calidad.limite.' in v.motivo for v in r.sin_verificar)
