"""Spec 108 T3 — las tablas del estudio se validan contra los formatos del anexo 2, sin rellenar nada (108:RF-2, RF-3).

Las tablas de entrada son sintéticas y se sortean (``seed``); los formatos son los transcritos en
``config/vad/anexo2_formatos.json`` con su cita.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path

import pytest

from convertersmartgrid.vad.anexo2 import cargar_formatos, validar_tablas

RAIZ = Path(__file__).resolve().parents[1]
FORMATOS = RAIZ / 'config' / 'vad' / 'anexo2_formatos.json'
SEMILLAS = (3, 11, 29)


def _tabla(formato, semilla, periodo='2025'):
    """Una tabla completa del formato, con valores sorteados y las unidades del anexo."""
    rnd = random.Random(semilla)
    return {'formato': formato.id, 'periodo': periodo,
            'unidades': {c.id: c.unidad for c in formato.columnas},
            'filas': {f.id: {'unidad': f.unidad, **{c.id: round(rnd.uniform(0, 1e4), 3) for c in formato.columnas}}
                      for f in formato.filas}}


def _completas(formatos, semilla):
    return {f.id: _tabla(f, semilla + i) for i, f in enumerate(formatos.transcritos())}


def test_los_formatos_estan_transcritos_con_su_cita():
    """108:RF-2 — cada formato del anexo 2 lleva su cita (líneas o página); el que no se pudo leer lo dice."""
    formatos = cargar_formatos(FORMATOS)
    assert formatos.transcritos(), 'al menos un formato transcrito'
    for f in formatos.todos():
        assert f.lineas or f.pagina, f.id
        if f.transcrito:
            assert f.filas and f.columnas and all(c.unidad for c in f.columnas), f.id
        else:
            assert f.motivo, f'{f.id}: un formato sin transcribir dice por qué'
    datos = json.loads(FORMATOS.read_text(encoding='utf-8'))
    assert datos['fuente']['acto'] and datos['fuente']['sha256_texto']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tablas_completas_no_dejan_huecos_y_no_cambian(semilla):
    """108:RF-2 — con todas las tablas transcritas y sus unidades, no hay huecos y la salida es la entrada."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, semilla)
    entrada = copy.deepcopy(tablas)
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert not [h for h in res.huecos if h.tipo != 'sin_transcribir'], res.huecos
    assert res.tablas == entrada
    assert tablas == entrada, 'la validación no toca la entrada'


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tabla_obligatoria_que_falta(semilla):
    """108:RF-3 — una tabla obligatoria que falta se nombra y no se crea."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, semilla)
    quitada = random.Random(semilla).choice(sorted(tablas))
    del tablas[quitada]
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert any(h.tabla == quitada and h.tipo == 'falta_tabla' for h in res.huecos), res.huecos
    assert quitada not in res.tablas


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_campo_vacio_y_unidad_distinta_por_tabla_y_campo(semilla):
    """108:RF-3 — un campo vacío y una unidad distinta se dicen por tabla y campo, sin rellenar el valor."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, semilla)
    rnd = random.Random(semilla)
    t1, t2 = rnd.sample(sorted(tablas), 2)
    formato = formatos.formato(t1)
    fila = rnd.choice(sorted(f.id for f in formato.filas if f.obligatoria))
    columna = rnd.choice(sorted(c.id for c in formato.columnas if c.obligatoria))
    tablas[t1]['filas'][fila][columna] = None
    otra = rnd.choice(sorted(tablas[t2]['unidades']))
    tablas[t2]['unidades'][otra] = 'unidad-inventada'
    res = validar_tablas(tablas, formatos, periodo='2025')
    vacio = [h for h in res.huecos if h.tipo == 'campo_vacio' and h.tabla == t1]
    assert any(h.campo == f'{fila}.{columna}' for h in vacio), res.huecos
    assert res.tablas[t1]['filas'][fila][columna] is None, 'no se rellena'
    assert any(h.tipo == 'unidad_distinta' and h.tabla == t2 and h.campo == otra for h in res.huecos), res.huecos
    salida = json.dumps(res.tablas, sort_keys=True)
    assert salida == json.dumps({k: v for k, v in tablas.items()}, sort_keys=True), 'ningún valor nuevo'


def test_fila_que_falta_y_periodo_distinto():
    """108:RF-2, 108:RF-3 — una fila del formato que falta y una tabla de otro periodo se nombran."""
    formatos = cargar_formatos(FORMATOS)
    tablas = _completas(formatos, 5)
    t = sorted(tablas)[0]
    fila = sorted(f.id for f in formatos.formato(t).filas if f.obligatoria)[0]
    del tablas[t]['filas'][fila]
    t2 = sorted(tablas)[-1]
    tablas[t2]['periodo'] = '2019'
    res = validar_tablas(tablas, formatos, periodo='2025')
    assert any(h.tipo == 'falta_campo' and h.tabla == t and h.campo == fila for h in res.huecos), res.huecos
    assert any(h.tipo == 'periodo_distinto' and h.tabla == t2 for h in res.huecos), res.huecos


def test_formato_sin_transcribir_se_nombra_y_no_se_valida():
    """108:RF-3 — un formato que el anexo no deja leer en la copia local no se da por validado."""
    formatos = cargar_formatos(FORMATOS)
    pendientes = [f.id for f in formatos.todos() if not f.transcrito]
    res = validar_tablas(_completas(formatos, 1), formatos, periodo='2025')
    assert {h.tabla for h in res.huecos if h.tipo == 'sin_transcribir'} == set(pendientes)
    assert res.completo is (not pendientes)
