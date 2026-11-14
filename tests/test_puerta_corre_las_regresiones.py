"""106:RF-13 — la puerta de commit corre siempre las comprobaciones de regresiones (081:RF-47) con su gobierno.

Está en su propio módulo, y no en test_puerta_calidad.py, para no pedir el turno de la máquina (106:RF-6): esta prueba
no usa la tarjeta y no tiene por qué esperar a otra sesión de pytest que la tenga.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _puerta():
    spec = importlib.util.spec_from_file_location('puerta_calidad_regresiones', RAIZ / 'tools' / 'puerta_calidad.py')
    modulo = importlib.util.module_from_spec(spec)
    sys.modules['puerta_calidad_regresiones'] = modulo
    try:
        spec.loader.exec_module(modulo)
    finally:
        sys.modules.pop('puerta_calidad_regresiones', None)
    return modulo


def test_un_commit_que_no_toca_docs_regresiones_corre_test_regresiones():
    """106:RF-13 — 2026-11-13: la edición ccb81aa8 quitó cuatro pruebas que citaba una entrada de docs/regresiones/ y
    ninguna puerta lo vio: el commit no tocaba docs/regresiones ni nada que nombrara test_regresiones. Ahora va en el
    gobierno, que la puerta de commit corre siempre."""
    puerta = _puerta()
    # Un commit como aquel: borra pruebas de un fichero de tests/ y cambia un módulo de src/, sin docs/regresiones.
    elegidas = puerta.pruebas_del_commit(['tests/test_ya_no_existe_rf13.py', 'src/convertersmartgrid/naming.py'], RAIZ)
    assert 'tests/test_regresiones.py' in elegidas
    # Y también un commit sin código: solo un documento.
    assert 'tests/test_regresiones.py' in puerta.pruebas_del_commit(['docs/NOTA.md'], RAIZ)
    assert 'tests/test_regresiones.py' in puerta.GOBIERNO


def test_106_rf13_lo_que_mira_el_arbol_entero_va_en_el_gobierno():
    """106:RF-13 — capas, ciclos y el nombre (002:RF-2/3, 058) los rompe un commit que no los nombra. 2026-11-14: cad225d0
    y 38dc1581 dejaron ciclos, módulos sin capa y una ruta con el nombre anterior, y ninguna de sus puertas eligió esas
    pruebas."""
    puerta = _puerta()
    for prueba in ('tests/test_capas.py', 'tests/test_dominio_numeros_medidos.py',
                   'tests/test_nombre_converter_smart_grid.py'):
        assert prueba in puerta.GOBIERNO
        assert prueba in puerta.pruebas_del_commit(['docs/NOTA.md'], RAIZ)
