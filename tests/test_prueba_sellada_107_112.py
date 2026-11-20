"""Spec 070, T21: la prueba sellada de las tareas de las specs 107 a 112 (RF-85)."""
from __future__ import annotations

import importlib

from convertersmartgrid.aplicacion.evaluacion_modelos import texto_canonico


def _sellada():
    import importlib.util

    nombre = 'convertersmartgrid.aplicacion.asistente.prueba_sellada_107_112'
    assert importlib.util.find_spec(nombre) is not None, 'falta la prueba sellada de las specs 107 a 112 (070 T21)'
    return importlib.import_module(nombre)


def test_070_rf85_la_sellada_nueva_cubre_las_tareas_de_107_a_112_con_su_huella():
    """070:RF-85 — una prueba sellada propia para las tareas que la 070 y la 079 dejan fuera, con su huella fijada antes
    de medir: las mismas filas con cualquier espacio, seis frases por tarea y ningún texto de dos tareas."""
    from convertersmartgrid.aplicacion.asistente.tareas import TAREAS_107_112

    s = _sellada()
    assert set(s.FRASES) == set(TAREAS_107_112)
    assert all(len(set(v)) >= 6 for v in s.FRASES.values())
    filas = s.selladas()
    assert s.huella_de(filas) == s.HUELLA == '8de089d3e87366bf'
    assert {r['tarea'] for r in filas} == set(TAREAS_107_112)
    assert all(r['particion'] == 'prueba' and r['conjunto'] == s.CONJUNTO for r in filas)


def test_070_rf85_ninguna_frase_sellada_esta_en_lo_que_entrena():
    """070:RF-85 — ninguna plantilla de la sellada nueva está en el currículo, las propuestas ni las plantillas del
    catálogo: si lo estuviera, el modelo la habría visto y la prueba no sería ciega."""
    from convertersmartgrid.aplicacion.asistente import curriculo_maestro as cm
    from convertersmartgrid.aplicacion.asistente import propuestas_maestro as pm
    from convertersmartgrid.aplicacion.asistente.tareas import TAREAS

    entrena = {texto_canonico(x) for d in (cm.FAMILIAS, cm.ESTILO_REAL, pm.PLANTILLAS) for v in d.values() for x in v}
    entrena |= {texto_canonico(p) for t in TAREAS.values() for p in t.plantillas}
    assert not [p for v in _sellada().FRASES.values() for p in v if texto_canonico(p) in entrena]


def test_070_rf85_la_destilacion_mide_las_selladas_nuevas_con_su_huella_y_no_deciden():
    """070:RF-85 (T21) — el candidato del reentrenamiento se mide también en las selladas nuevas (la de 107 a 112 y la de
    la 026), cada una con su huella y sus tareas; informan y no deciden: la anterior queda como histórica hasta que la
    070 T22 incorpore sus tareas. Con un alumno de prueba que acierta siempre, la medida es completa."""
    from convertersmartgrid.aplicacion.asistente import destilacion_integral as di
    from convertersmartgrid.aplicacion.asistente import prueba_sellada_026 as s026
    from convertersmartgrid.aplicacion.asistente.tareas import TAREAS_026, TAREAS_107_112

    assert hasattr(di, 'medir_selladas_nuevas'), 'la destilación no mide las selladas nuevas (070 T21)'
    s107 = _sellada()
    respuestas = {texto_canonico(r['texto']): r for s in (s107, s026) for r in s.selladas()}

    class AlumnoQueAcierta:
        def predecir(self, texto):
            r = respuestas[texto_canonico(texto)]
            datos: dict = {}
            for a, b, t in r['datos']:
                datos.setdefault(t, []).append({'valor': texto[a:b].strip()})
            return {'tarea': r['tarea'], 'confianza': 1.0, 'datos': datos}

    medidas = di.medir_selladas_nuevas(AlumnoQueAcierta())
    assert set(medidas) == {s107.CONJUNTO, s026.CONJUNTO}
    assert medidas[s107.CONJUNTO]['huella'] == s107.HUELLA and medidas[s026.CONJUNTO]['huella'] == s026.HUELLA
    assert set(medidas[s107.CONJUNTO]['tareas']) == set(TAREAS_107_112)
    assert set(medidas[s026.CONJUNTO]['tareas']) == set(TAREAS_026)
    for m in medidas.values():
        assert m['decide'] is False and m['filas'] == m['medida']['ejemplos'] > 0
        assert m['medida']['acierto_tarea'] == 1.0 and m['medida']['f1_datos'] == 1.0


def test_070_rf85_una_frase_tocada_para_la_medida_de_las_selladas_nuevas(monkeypatch):
    """070:RF-85 — si alguien toca una frase de la sellada nueva, su huella lo delata y la destilación no la mide."""
    import pytest

    from convertersmartgrid.aplicacion.asistente import destilacion_integral as di

    assert hasattr(di, 'medir_selladas_nuevas'), 'la destilación no mide las selladas nuevas (070 T21)'
    s = _sellada()
    tocadas = {**s.FRASES, 'benchmark_anonimo': (*s.FRASES['benchmark_anonimo'][:-1], 'otra frase del benchmark')}
    monkeypatch.setattr(s, 'FRASES', tocadas)
    with pytest.raises(ValueError, match='huella'):
        di.medir_selladas_nuevas(object())
