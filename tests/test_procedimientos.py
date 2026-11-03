"""077:RF-3 — los procedimientos que lee el asistente: cada cita existe y casa con su línea (petición del usuario, 2026-11-02).

Mismo criterio que `tools/preguntas_entregables.py verificar` de la 076 (fichero, línea con su ancla y RF definido), sobre
markdown en vez de filas. Cuando la 076 se integre, esta comprobación puede pasar a usar su función.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / 'docs' / 'procedimientos'
CITA = re.compile(r'`([^`\s]+):(\d+)`\s*\(«(.+?)»\)', re.DOTALL)
RF = re.compile(r'\b(\d{3}):RF-(\d+[a-z]?)\b')
#: Líneas que una cita puede haberse movido sin dejar de valer: otros cambios corren los ficheros.
HOLGURA = 40
PROCEDIMIENTOS = ('reiniciar_la_web.md', 'reconstruir.md', 'completar_lo_que_falta.md', 'hacer_converger.md',
                  'reemplazar_con_el_catalogo.md')


def _textos():
    return {p.name: p.read_text(encoding='utf-8') for p in sorted(CARPETA.glob('*.md'))}


def test_estan_los_cinco_procedimientos_y_cada_uno_cita():
    """Los cinco que pidió el usuario, y ninguno sin citas."""
    textos = _textos()
    for nombre in PROCEDIMIENTOS:
        assert nombre in textos and CITA.search(textos[nombre]), nombre


@pytest.mark.parametrize('nombre', PROCEDIMIENTOS)
def test_cada_cita_casa_con_su_linea(nombre):
    """Una cita desfasada se ve aquí, no en una respuesta del asistente."""
    errores = []
    for fichero, linea, ancla in CITA.findall(_textos()[nombre]):
        ancla = ' '.join(ancla.split())
        ruta = RAIZ / fichero
        if not ruta.is_file():
            errores.append(f'{fichero} no existe')
            continue
        lineas = ruta.read_text(encoding='utf-8', errors='replace').splitlines()
        n = int(linea)
        cerca = range(max(n - 1 - HOLGURA, 0), min(n + HOLGURA, len(lineas)))
        if not any(ancla in lineas[i] for i in cerca):
            errores.append(f'{fichero}:{linea} no contiene «{ancla}» ni cerca')
    assert not errores, '\n'.join(errores)


@pytest.mark.parametrize('nombre', PROCEDIMIENTOS)
def test_cada_rf_citado_esta_definido(nombre):
    """Un RF citado tiene que existir en su spec."""
    faltan = []
    for spec, n in RF.findall(_textos()[nombre]):
        carpetas = list((RAIZ / 'specs').glob(f'{spec}-*'))
        texto = (carpetas[0] / 'spec.md').read_text(encoding='utf-8') if carpetas else ''
        if not re.search(rf'^- RF-{n}:', texto, re.MULTILINE):
            faltan.append(f'{spec}:RF-{n}')
    assert not faltan, faltan


def test_sin_nombres_de_alimentadores_ni_empresas():
    """Marcadores, no datos de una distribuidora."""
    reales = re.compile(r'\b[A-Z]{2}\d{3}\b|electro ?(dunas|oriente)|\bELOR\b|\bELD\b', re.IGNORECASE)
    for nombre, texto in _textos().items():
        sin_codigo = re.sub(r'`[^`]*`|\(«.+?»\)', '', texto, flags=re.DOTALL)
        assert not reales.search(sin_codigo), nombre


def test_lo_que_hace_el_operador_esta_dicho():
    """El acceso directo y lo manual en DIgSILENT los pide el asistente, no los ejecuta."""
    textos = _textos()
    assert 'Lo hace el operador' in textos['reiniciar_la_web.md']
    assert 'Lo hace el operador' in textos['hacer_converger.md']
