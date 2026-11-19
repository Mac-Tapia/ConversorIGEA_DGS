"""Spec 026, RF-44 y RF-46: la prueba sellada propia de las tareas nuevas de la 026, con el criterio de la 070:RF-85.

Las selladas de la 070, la 079 y la 107-112 conservan su huella; estas tareas se miden aquí. Ninguna de sus frases puede
estar en lo que entrena: ``fuga_evaluacion.fugas_de_las_selladas`` lo cuenta, y sembrar una en el currículo lo delata.
"""
from __future__ import annotations

import importlib
import importlib.util


def _sellada():
    nombre = 'convertersmartgrid.aplicacion.asistente.prueba_sellada_026'
    assert importlib.util.find_spec(nombre) is not None, 'falta la prueba sellada de las tareas nuevas de la 026'
    return importlib.import_module(nombre)


def test_026_la_sellada_cubre_sus_tareas_con_su_huella_y_las_anteriores_no_se_mueven():
    """026:RF-44, RF-46 — seis frases por tarea, la huella fijada antes de medir y ningún texto de dos tareas; las tareas
    de la 026 quedan fuera de las selladas de la 070 y la 079, y la 107-112 conserva la suya."""
    s = _sellada()
    from convertersmartgrid.aplicacion.asistente import prueba_sellada_107_112 as s107
    from convertersmartgrid.aplicacion.asistente.tareas import (TAREAS, TAREAS_026, TAREAS_107_112,
                                                                TAREAS_SIN_SELLADA_070_079)

    assert set(s.FRASES) == set(TAREAS_026) <= set(TAREAS)
    assert {'vnr_estudio', 'clientes_fijos_evolucion', 'normativa_comprobar', 'normativa_agregar',
            'normativa_regenerar'} == set(TAREAS_026)
    assert all(len(set(v)) >= 6 for v in s.FRASES.values())
    filas = s.selladas()
    assert s.huella_de(filas) == s.HUELLA == '76e901845e43937d'
    assert {r['tarea'] for r in filas} == set(TAREAS_026)
    assert all(r['particion'] == 'prueba' and r['conjunto'] == s.CONJUNTO for r in filas)
    assert TAREAS_SIN_SELLADA_070_079 == TAREAS_107_112 | TAREAS_026
    assert s107.huella_de(s107.selladas()) == s107.HUELLA == '8de089d3e87366bf'


def test_026_ninguna_frase_sellada_esta_en_lo_que_entrena():
    """026:RF-44, RF-46 — ni la sellada de la 026 ni la de la 107-112 tienen frases en el currículo, las propuestas, las
    órdenes fijas ni las plantillas del catálogo."""
    from convertersmartgrid.aplicacion.asistente import fuga_evaluacion as fe

    _sellada()
    assert hasattr(fe, 'fugas_de_las_selladas'), 'la comprobación de fugas no mira las selladas de las tareas nuevas'
    assert fe.fugas_de_las_selladas() == {'sellada_107_112': 0, 'sellada_026': 0}


def test_026_una_frase_sellada_sembrada_en_el_curriculo_se_delata(monkeypatch):
    """026:RF-44, RF-46 — si una frase de la sellada entra en el currículo, la cuenta de fugas deja de ser cero."""
    from convertersmartgrid.aplicacion.asistente import curriculo_maestro as cm
    from convertersmartgrid.aplicacion.asistente import fuga_evaluacion as fe

    frase = _sellada().FRASES['normativa_regenerar'][0]
    monkeypatch.setitem(cm.ESTILO_REAL, 'normativa_regenerar', (*cm.ESTILO_REAL['normativa_regenerar'], frase))
    assert fe.fugas_de_las_selladas()['sellada_026'] == 1
