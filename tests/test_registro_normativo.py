"""Registro normativo común (tarjeta RN; dueña la 108, lo usan la 107 y la 108): las pruebas genéricas del módulo con
registros sintéticos (107:RF-7, 107:RF-8, 107:RF-11). Actos, valores y fechas inventados para la prueba, sin ninguna
empresa ni periodo real.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from convertersmartgrid.registro_normativo import (
    ESTADOS,
    RegistroError,
    cargar_registro,
)

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = json.loads((RAIZ / 'src' / 'convertersmartgrid' / 'schemas' / 'registro_normativo_v1.schema.json')
                     .read_text(encoding='utf-8'))
H = 'b' * 64


def _regla(clave, valor, **kw):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave} es {valor}»', 'pagina': '3', **kw}


def _registro_uno():
    """Una norma en cada estado, cada una con su regla de prueba."""
    return {'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'N-VC', 'titulo': 'Comprobada', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
         'vigencia_desde': '2001-01-01', 'reglas': [_regla('pit.tasa', 0.1)]},
        {'acto': 'N-PRE', 'titulo': 'Proyecto', 'estado_juridico': 'prepublicada',
         'reglas': [_regla('pit.coym', 0.03)]},
        {'acto': 'N-NV', 'titulo': 'Sin leer', 'estado_juridico': 'no_verificada',
         'reglas': [_regla('pit.vida', 30)]},
        {'acto': 'N-DER', 'titulo': 'Derogada', 'estado_juridico': 'derogada', 'vigencia_hasta': '2002-01-01',
         'reglas': [_regla('pit.viejo', 1)]},
    ]}


def _registro_dos():
    """Una norma modificada por otra posterior: la regla vigente cambia con la fecha."""
    return {'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'M-BASE', 'titulo': 'Base', 'estado_juridico': 'modificada', 'sha256': H,
         'vigencia_desde': '2010-01-01', 'vigencia_hasta': '2020-01-01', 'modificada_por': ['M-MOD'],
         'reglas': [_regla('pit.limite', 100)]},
        {'acto': 'M-MOD', 'titulo': 'Modificatoria', 'estado_juridico': 'vigente_comprobada', 'sha256': H,
         'vigencia_desde': '2020-01-01', 'modifica': ['M-BASE'], 'reglas': [_regla('pit.limite', 90)]},
    ]}


def _escribir(tmp_path, nombre, datos):
    carpeta = tmp_path / nombre
    carpeta.mkdir()
    (carpeta / 'r.json').write_text(json.dumps(datos), encoding='utf-8')
    return carpeta


@pytest.mark.parametrize('datos', (_registro_uno(), _registro_dos()), ids=('estados', 'modificatoria'))
def test_registros_sinteticos_validan_contra_el_esquema(datos):
    """107:RF-7 — cada norma con su estado jurídico y su vigencia, según el esquema común."""
    jsonschema.validate(datos, ESQUEMA)


def test_los_cinco_estados():
    """107:RF-7 — el registro distingue vigente comprobada, modificada, prepublicada, no verificada y derogada."""
    assert set(ESTADOS) == {'vigente_comprobada', 'modificada', 'prepublicada', 'no_verificada', 'derogada'}


def test_prepublicada_y_no_verificada_no_obligan(tmp_path):
    """107:RF-8 — una regla prepublicada o no verificada sale como no obligatoria, con su estado."""
    registro = cargar_registro(_escribir(tmp_path, 'uno', _registro_uno()))
    assert registro.regla('pit.tasa', '2030-01-01').obligatoria
    for clave, estado in (('pit.coym', 'prepublicada'), ('pit.vida', 'no_verificada')):
        r = registro.regla(clave, '2030-01-01')
        assert r.estado == estado and not r.obligatoria
        assert r.norma.acto and r.regla.pagina and r.regla.cita_literal


def test_modificatoria_por_fecha(tmp_path):
    """107:RF-7 — la regla de cada fecha es la de la norma vigente entonces, con su acto."""
    registro = cargar_registro(_escribir(tmp_path, 'dos', _registro_dos()))
    antes, despues = registro.regla('pit.limite', '2015-06-01'), registro.regla('pit.limite', '2025-06-01')
    assert (antes.regla.valor, antes.norma.acto, antes.obligatoria) == (100, 'M-BASE', True)
    assert (despues.regla.valor, despues.norma.acto, despues.obligatoria) == (90, 'M-MOD', True)
    assert antes.huella() != despues.huella()


def test_instantanea_cambia_con_una_modificatoria_y_no_con_el_orden(tmp_path):
    """107:RF-7 — la huella del registro fija lo que se usó; una norma nueva la cambia."""
    datos = _registro_dos()
    a = cargar_registro(_escribir(tmp_path, 'a', datos)).instantanea()
    datos['normas'].reverse()
    assert cargar_registro(_escribir(tmp_path, 'b', datos)).instantanea() == a
    datos['normas'].append({'acto': 'M-NUEVA', 'titulo': 'Posterior', 'estado_juridico': 'no_verificada'})
    assert cargar_registro(_escribir(tmp_path, 'c', datos)).instantanea() != a


def test_sin_regla_es_un_error_que_la_nombra(tmp_path):
    """107:RF-11 — un valor que no está en el registro no se supone: el error nombra la clave."""
    registro = cargar_registro(_escribir(tmp_path, 'uno', _registro_uno()))
    with pytest.raises(RegistroError, match='pit.inexistente'):
        registro.regla('pit.inexistente')
