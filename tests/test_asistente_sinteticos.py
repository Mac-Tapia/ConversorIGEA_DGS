"""Spec 026, T2: órdenes sintéticas para entrenar el Transformer."""
from __future__ import annotations

import random
from collections import Counter

from igea_dgs.asistente.sinteticos import expandir, generar, normalizar
from igea_dgs.asistente.tareas import TAREAS

VOCAB = {'alimentadores': ['IN111', 'TA225', 'PA217'], 'proyecto': ['20261015-170359_IGEA_IN111_TA225'],
         'sistema': ['Pisco', 'Ica']}


def test_genera_todas_las_tareas_con_nombres_reales():
    """026:RF-21 — frases de cada tarea con los nombres reales del espacio y sus datos
    marcados en su sitio, deterministas con la semilla."""
    a = generar(VOCAB, por_tarea=40, semilla=1)
    b = generar(VOCAB, por_tarea=40, semilla=1)
    assert [e.texto for e in a] == [e.texto for e in b]
    assert Counter(e.tarea for e in a) == {t: 40 for t in TAREAS}
    reales = [v for e in a for v in e.valor('alimentadores')]
    assert any('IN111' in v.upper() for v in reales)
    for e in a:
        for ini, fin, tipo in e.datos:
            assert 0 <= ini < fin <= len(e.texto) and e.texto[ini:fin].strip() == e.texto[ini:fin]
            assert tipo in {d.tipo for d in TAREAS[e.tarea].datos}


def test_sin_nombres_reales_inventa_la_forma():
    """026:RF-21 — sin vocabulario se inventan códigos con la forma habitual (universal)."""
    ej = [e for e in generar({}, por_tarea=30, semilla=2) if e.valor('alimentadores')]
    assert ej and all(any(c.isdigit() for c in v) or 'todo' in v for e in ej for v in e.valor('alimentadores'))


def test_ruido_en_la_plantilla_nunca_en_los_datos():
    """026:RF-21 — las erratas caen en las palabras de la plantilla y los datos quedan intactos."""
    rnd = random.Random(3)
    for _ in range(200):
        e = expandir('convierte los alimentadores {alimentadores} del proyecto {proyecto}', 'convertir',
                     rnd, VOCAB, ruido=1.0)
        assert e.valor('alimentadores') and e.valor('proyecto')
        for v in e.valor('alimentadores'):
            assert all(p.strip().upper() in {'IN111', 'TA225', 'PA217'} or any(c.isdigit() for c in p)
                       for p in v.replace(' y ', ',').split(',') if p.strip()) or 'todo' in v


def test_normalizar_conserva_las_posiciones():
    """026:RF-2 — sin tildes ni mayúsculas y con la misma longitud."""
    t = 'Calibración de PISCO en julio'
    assert normalizar(t) == 'calibracion de pisco en julio' and len(normalizar(t)) == len(t)
