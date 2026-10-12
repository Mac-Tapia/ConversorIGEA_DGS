"""Spec 012: confiabilidad y capacidad de la red calibrada."""

from __future__ import annotations

from apoyo import cargar_herramienta


def test_licencia_comprueba_los_modulos_de_la_012():
    """012:RF-4 — la comprobación de licencia prueba los cinco módulos de la spec.

    `ComOpri` (reconectadores), `ComHostcap` (capacidad de alojamiento) y `ComPvcurves`
    (curvas PV) no estaban en la lista; `ComRel3` y `ComCapo` sí. Un estudio cuyo módulo
    no cubre la licencia se lista como no disponible, y para saberlo hay que ejecutar la
    orden, igual que en la spec 011.
    """
    licencia = cargar_herramienta('check_pf_license.py')
    clases = {clase for clase, *_ in licencia.ORDENES}
    assert {'ComRel3', 'ComOpri', 'ComHostcap', 'ComPvcurves', 'ComCapo'} <= clases
