"""Spec 026, T1: catálogo de tareas del asistente."""
from __future__ import annotations

import re
from pathlib import Path

from igea_dgs.asistente.tareas import TAREAS, TIPOS_DATO, descripcion_para_modelo
from igea_dgs.web import services

RAIZ = Path(__file__).resolve().parents[1]


def test_cada_tarea_apunta_a_algo_que_existe():
    """026:RF-10 — cada tarea se ejecuta por una función de la web o una herramienta de
    tools/ que existe: el asistente no tiene una vía propia."""
    for t in TAREAS.values():
        if t.modo == 'proceso':
            assert (RAIZ / 'tools' / f'{t.funcion}.py').is_file(), t.nombre
        else:
            assert callable(getattr(services, t.funcion, None)), t.nombre
        assert t.modo in ('consulta', 'trabajo', 'proceso')


def test_lo_que_escribe_pide_confirmacion():
    """026:RF-8 / 026:RF-9 — las consultas no escriben; todo lo que toca DIgSILENT o el disco
    está marcado como que escribe."""
    for t in TAREAS.values():
        if t.modo == 'consulta':
            assert not t.escribe, t.nombre
    for nombre in ('convertir', 'sistema_completo', 'pide', 'obras', 'cargas_nuevas', 'informe_estudio',
                   'informe_factibilidad', 'gemelo_aprender', 'gemelo_entrenar'):
        assert TAREAS[nombre].escribe, nombre


def test_atiende_las_tareas_de_la_spec():
    """026:RF-11 — convertir (alimentadores, unir, sistema), sistema completo, cargas, obras y
    estudios, PIDE y sus resultados, gemelo, informes y consultas de estado."""
    for nombre in ('convertir', 'unir', 'convertir_sistema', 'sistema_completo', 'cargas_nuevas', 'obras',
                   'estudios', 'transferencia', 'pide', 'resultados_pide', 'gemelo_aprender',
                   'gemelo_entrenar', 'evaluar_gemelo', 'gemelo_temporal', 'episodios', 'informe_estudio',
                   'informe_factibilidad', 'estado', 'proyectos'):
        assert nombre in TAREAS


def test_datos_tipados_y_plantillas_coherentes():
    """026:RF-2 — cada dato tiene un tipo conocido y las plantillas solo usan datos de su tarea."""
    for t in TAREAS.values():
        tipos = {d.tipo for d in t.datos}
        assert all(d.tipo in TIPOS_DATO for d in t.datos), t.nombre
        assert t.plantillas, t.nombre
        for p in t.plantillas:
            assert set(re.findall(r'\{(\w+)\}', p)) <= tipos, (t.nombre, p)
        for d in t.datos:
            if d.obligatorio:
                assert any(f'{{{d.tipo}}}' in p for p in t.plantillas), (t.nombre, d.nombre)
    herramientas = descripcion_para_modelo()
    assert {h['tarea'] for h in herramientas} == set(TAREAS)
