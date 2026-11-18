"""Spec 108 T19 — VNR no eléctrico y costos de explotación por rubro del registro (108:RF-19).

Rubros, partidas, monedas y fuentes sintéticos; el registro real solo se usa para comprobar que trae sus rubros.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from convertersmartgrid.dominio.registro_normativo import cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.aplicacion.vad.costos_explotacion import ROTULO_REAL, CostoReal, Partida, costear, rubros

RAIZ = Path(__file__).resolve().parents[1]


def _registro(tmp_path, lista=None):
    lista = lista if lista is not None else [{'clave': 'r_a', 'nombre': 'Rubro A', 'numeral': '9.1'},
                                             {'clave': 'r_b', 'nombre': 'Rubro B', 'numeral': '9.2'},
                                             {'clave': 'r_c', 'nombre': 'Rubro C', 'numeral': '9.3'}]
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': 'vigente_comprobada',
        'sha256': 'e' * 64, 'reglas': [{'clave': 'vad.explotacion.rubros', 'valor': lista,
                                        'cita_literal': '«rubros»', 'lineas': '5'}]}]}
    ruta = tmp_path / 'reg' / 'tdr.json'
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(ruta.parent)


def _p(desc, cant, cu, moneda='XUS', fuente='catálogo sintético'):
    return Partida(desc, cant, cu, moneda, fuente)


def test_estandar_solo_con_partidas_dimensionadas_y_real_rotulado(tmp_path):
    """108:RF-19 — el total estándar suma solo lo dimensionado; el costo real va aparte, rotulado como referencia."""
    resultado = costear(_registro(tmp_path),
                        {'r_a': [_p('oficina', 2, 100), _p('vehículo', 3, 50)], 'r_b': [_p('sistema', 1, 70)]},
                        {'r_a': CostoReal(999.0, 'XUS', 'contabilidad sintética')})
    a, b, c = resultado.rubros
    assert a.estandar == pytest.approx(350) and a.referencia_real.importe == 999.0
    assert a.rotulo_referencia == ROTULO_REAL and 'no es costo estándar' in ROTULO_REAL
    assert b.estandar == pytest.approx(70) and b.referencia_real is None
    assert resultado.totales == {'XUS': pytest.approx(420)}
    assert c.estandar is None and resultado.sin_dimensionar == ['r_c']


def test_rubro_con_solo_el_costo_real_queda_sin_dimensionar(tmp_path):
    """108:RF-19 — el costo real nunca se toma como estándar: el rubro queda sin dimensionar y fuera del total."""
    resultado = costear(_registro(tmp_path), {}, {'r_b': CostoReal(500.0, 'XUS', 'contabilidad sintética')})
    b = resultado.rubros[1]
    assert b.estandar is None and 'no se toma como estándar' in b.motivo
    assert resultado.totales == {}


def test_dos_monedas_no_se_suman(tmp_path):
    """108:RF-19 — partidas en dos monedas dejan el rubro sin total, y los totales van por moneda."""
    resultado = costear(_registro(tmp_path), {'r_a': [_p('x', 1, 1, 'XUS'), _p('y', 1, 1, 'XPE')],
                                              'r_b': [_p('z', 1, 5, 'XPE')], 'r_c': [_p('w', 2, 3, 'XUS')]})
    assert resultado.rubros[0].estandar is None and 'XPE' in resultado.rubros[0].motivo
    assert resultado.totales == {'XPE': pytest.approx(5), 'XUS': pytest.approx(6)}


@pytest.mark.parametrize('kw,texto', [({'fuente': ''}, 'fuente'), ({'moneda': ' '}, 'moneda'),
                                      ({'cant': -1}, 'cantidad'), ({'cu': float('inf')}, 'costo_unitario')])
def test_partida_invalida_se_rechaza(kw, texto):
    """108:RF-19 — una partida sin fuente, sin moneda o con números inválidos se rechaza nombrando el campo."""
    args = {'desc': 'p', 'cant': 1, 'cu': 1, **kw}
    with pytest.raises(VadError, match=texto):
        _p(**args)


def test_rubro_desconocido_y_registro_sin_rubros(tmp_path):
    """108:RF-19 — un rubro que el registro no tiene se rechaza; un registro sin rubros o mal formado, también."""
    with pytest.raises(VadError, match='r_z'):
        costear(_registro(tmp_path), {'r_z': [_p('x', 1, 1)]})
    with pytest.raises(VadError, match='lista no vacía'):
        rubros(_registro(tmp_path, lista=[]))
    with pytest.raises(VadError, match='numeral'):
        rubros(_registro(tmp_path, lista=[{'clave': 'a', 'nombre': 'A'}]))


def test_los_rubros_salen_del_registro(tmp_path):
    """108:RF-19, 108:RF-13 — con otro registro salen otros rubros; el real trae los del TdR (6.8.3 y 6.13 a 6.15)."""
    otros = rubros(_registro(tmp_path, lista=[{'clave': 'solo', 'nombre': 'Único', 'numeral': '1'}]))
    assert [r.clave for r in otros] == ['solo']
    reales = rubros(cargar_registro(RAIZ / 'config' / 'vad'))
    assert len(reales) >= 1 and all(r.numeral for r in reales)
