"""070:RF-93 — el currículo de la T28: paráfrasis solo de entrenamiento para las tareas vecinas que el candidato de la T22
confundía, sin tocar nada de lo que mide.

El 2026-11-24 el candidato de la T22 confundía proyecto_entero con sistema_completo (0,44 en selección), leer_solicitud con
pit_expediente y subir_fuente_empresa, y en calibración buscar_maxima → sistema_completo, cruzar_clientes →
alimentadores_completo y descargar_resultados → unir. Las pruebas son las mismas que fijaron el currículo de la 079.
"""
from __future__ import annotations

import random

import pytest

from convertersmartgrid.aplicacion.asistente import curriculo_maestro as cm                 # noqa: E402
from convertersmartgrid.aplicacion.asistente import destilacion_integral as di              # noqa: E402
from convertersmartgrid.aplicacion.asistente import fuga_evaluacion as fe                   # noqa: E402
from convertersmartgrid.aplicacion.asistente import validacion_cruzada as vc                # noqa: E402
from convertersmartgrid.aplicacion.asistente.maestro_real import clave_texto, firma_familia  # noqa: E402
from convertersmartgrid.aplicacion.asistente.sinteticos import expandir                     # noqa: E402
from convertersmartgrid.aplicacion.asistente.tareas import TAREAS                           # noqa: E402

VOCAB = {'alimentadores': ['AB101', 'CD202'], 'proyecto': ['Proyecto X'], 'sistema': ['Valle'], 'set': ['Puerto']}
ORIGEN = 'parafrasis_070_t28'
#: Las tareas que la selección y la calibración de la T22 dieron flojas o confundidas, y sus vecinas.
VECINAS = {'proyecto_entero', 'sistema_completo', 'leer_solicitud', 'pit_expediente', 'subir_fuente_empresa',
           'pit_diagnostico', 'carga_nueva_sola', 'evaluar_carga_nueva', 'buscar_maxima', 'cruzar_clientes',
           'alimentadores_completo', 'descargar_resultados', 'unir', 'estado'}


@pytest.fixture(scope='module')
def corpus():
    return di.preparar_corpus(VOCAB, [], por_familia=4)


def test_070_rf93_las_vecinas_declaradas_con_doce_frases_distintas():
    assert set(cm.PARAFRASIS_070_T28) == VECINAS and VECINAS <= set(TAREAS)
    assert all(len(set(v)) >= 12 for v in cm.PARAFRASIS_070_T28.values())
    # Ninguna repite una de las cuatro columnas de su tarea (entrenamiento, selección, calibración y prueba).
    assert not [p for t, v in cm.PARAFRASIS_070_T28.items() for p in v if p in cm.FAMILIAS[t]]


def test_070_rf93_solo_entrena_y_marca_su_origen(corpus):
    filas, meta = corpus
    nuevas = [r for r in filas if r.get('origen_curriculo') == ORIGEN]
    assert nuevas and {r['particion'] for r in nuevas} == {'entrenamiento'}
    assert {r['tarea'] for r in nuevas} == VECINAS
    assert meta[ORIGEN]['filas'] == len(nuevas) and meta[ORIGEN]['maestro'] == cm.MAESTRO_070_T28
    assert all(r['maestro'] == 'claude' and r['del_maestro'] for r in nuevas)


def test_070_rf93_no_toca_lo_que_mide(corpus):
    filas, meta = corpus
    assert meta[ORIGEN]['excluidas_por_fuga'] == 0
    apartadas = [r for r in filas if r['particion'] != 'entrenamiento']
    textos = {clave_texto(r['texto']) for r in apartadas}
    familias = {firma_familia(r['texto'], r['datos']) for r in apartadas}
    for r in (r for r in filas if r.get('origen_curriculo') == ORIGEN):
        assert clave_texto(r['texto']) not in textos and firma_familia(r['texto'], r['datos']) not in familias


def test_070_rf93_no_se_parece_ni_con_la_familia_ancha(corpus):
    filas, _ = corpus
    medido = vc.Claves(vc.clave_de_familia(r['texto'], r['datos']) for r in filas
                       if r['particion'] in ('seleccion', 'calibracion') or r.get('conjunto'))
    expandidas = {p: expandir(p, t, random.Random(1), VOCAB) for t, v in cm.PARAFRASIS_070_T28.items() for p in v}
    parecidas = [p for p, e in expandidas.items() if medido.toca(vc.clave_de_familia(e.texto, e.datos))]
    assert not parecidas, parecidas


def test_070_rf93_deja_identicas_selección_calibración_e_histórica(monkeypatch, corpus):
    filas, meta = corpus
    monkeypatch.setattr(di, 'PARAFRASIS_070_T28', {})
    sin, meta_sin = di.preparar_corpus(VOCAB, [], por_familia=4)
    assert meta['prueba_historica'] == meta_sin['prueba_historica']
    for parte in ('seleccion', 'calibracion'):
        a = sorted(r['record_id'] for r in filas if r['particion'] == parte)
        assert a and a == sorted(r['record_id'] for r in sin if r['particion'] == parte)
    assert meta['dataset_hash'] != meta_sin['dataset_hash'] and meta['curriculo_hash'] != meta_sin['curriculo_hash']


def test_070_rf93_las_paráfrasis_cuentan_en_la_fuga_de_las_selladas(monkeypatch):
    """Las paráfrasis que solo entrenan entran en lo que se compara con las selladas: antes no estaba ninguna."""
    entrena = fe.textos_que_entrenan()
    from convertersmartgrid.aplicacion.evaluacion_modelos import texto_canonico
    for d in (cm.PARAFRASIS_070, cm.PARAFRASIS_079, cm.PARAFRASIS_070_T28):
        assert all(texto_canonico(p) in entrena for v in d.values() for p in v)
    assert all(n == 0 for n in fe.fugas_de_las_selladas().values()), fe.fugas_de_las_selladas()
    # Una paráfrasis igual a una frase sellada se cuenta.
    from convertersmartgrid.aplicacion.asistente import prueba_sellada_107_112 as s
    tarea, frases = next(iter(s.FRASES.items()))
    monkeypatch.setitem(cm.PARAFRASIS_070_T28, 'estado', (frases[0],))
    assert fe.fugas_de_las_selladas()[s.CONJUNTO] >= 1
