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
