"""Registro normativo común (tarjeta RN): la comprobación permanente de las tablas de factores de expansión (FE ≥ 1 y
FE = 1/(1−p)), con sus rojos (107:RF-7). Valores sintéticos.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from convertersmartgrid.dominio.registro_normativo import (
    RegistroError,
    cargar_registro,
)

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = json.loads((RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json')
                     .read_text(encoding='utf-8'))
H = 'b' * 64



def _regla(clave, valor, **kw):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave} es {valor}»', 'pagina': '3', **kw}


# --------------------------------------------------------------------------- 107-T19b 3a: factores de pérdidas
ORDEN_FE = ['PEMT', 'PPMT', 'PESED', 'PPSED', 'PEBT', 'PPBT', 'PEBTCO', 'PPBTCO']


def _tabla_fe(empresas):
    return {'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT-VAD', 'titulo': 'Fijación sintética', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
         'reglas': [_regla('vad.perdidas.factores_expansion', {'orden': ORDEN_FE, 'empresas': empresas})]}]}


def _cargar(tmp_path, datos):
    (tmp_path / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    return cargar_registro(tmp_path)


def test_factores_de_expansion_cuadran_con_su_porcentaje(tmp_path):
    """107:RF-7 (T19b 3a) — una tabla con % y FE carga si cada fila cumple FE = 1/(1−p) dentro del redondeo; el FE no es
    1+p (con p = 7,11 %, FE = 1,0765 y no 1,0711)."""
    fila = {'fe': {'PEBT': 1.0765, 'PEMT': 1.0154}, 'porcentaje': {'PEBT': 7.11, 'PEMT': 1.52}}
    registro = _cargar(tmp_path, _tabla_fe({'EMPRESA-X': fila}))
    assert registro.regla('vad.perdidas.factores_expansion').regla.valor['empresas']['EMPRESA-X']['fe']['PEBT'] == 1.0765
    mal = {'fe': {'PEBT': 1.0711}, 'porcentaje': {'PEBT': 7.11}}
    with pytest.raises(RegistroError, match='PEBT'):
        _cargar(tmp_path, _tabla_fe({'EMPRESA-X': mal}))


@pytest.mark.parametrize('fila, nombra', (
    ({'fe': {'PEMT': 1.0154, 'PPMT': 1.0212}, 'porcentaje': {'PEMT': 2.08, 'PPMT': 1.98}}, 'PEMT'),
    ({'fe': {'PPBT': 1.1125}, 'porcentaje': {'PPBT': 0.11}}, 'PPBT'),
    ({'fe': {'PEMT': 0.9798}}, 'PEMT'),
), ids=('tabla_desplazada', 'porcentaje_10_11_leido_0_11', 'factor_menor_que_uno'))
def test_tabla_de_factores_mal_transcrita_falla_nombrando_la_fila(tmp_path, fila, nombra):
    """107:RF-7 (T19b 3a) — los rojos de la comprobación permanente: la tabla desplazada una fila (cada FE con el % de
    la fila siguiente), un 10,11 % leído como 0,11 % y un FE < 1 no cargan, y el error nombra la empresa y la fila."""
    with pytest.raises(RegistroError, match=f'EMPRESA-X, fila {nombra}'):
        _cargar(tmp_path, _tabla_fe({'EMPRESA-X': fila}))
