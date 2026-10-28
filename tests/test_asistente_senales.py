"""Spec 027, T17: umbral de confianza por tarea calibrado con las órdenes reales."""
from __future__ import annotations

import random

from igea_dgs.asistente import almacen, senales
from igea_dgs.asistente.interprete import interpretar


def test_umbral_por_tarea_con_su_tasa_de_error():
    """027:RF-38 — con órdenes sorteadas en las que la confianza alta acierta más, el umbral
    elegido deja una tasa de error empírica ≤ 2 % en lo que pasa sin preguntar; con pocas
    órdenes de una tarea, no se calibra."""
    semilla = random.randrange(1 << 30)
    rnd = random.Random(semilla)
    filas = []
    for _ in range(600):
        c = rnd.random()
        filas.append(('convertir', round(c, 3), rnd.random() < 0.6 + 0.4 * c ** 0.2 if c < 0.9 else True))
    filas += [('pide', 0.99, True)] * 5
    u = senales.calibrar_umbrales(filas)
    assert 'pide' not in u, 'con menos de 10 no se calibra'
    t = u['convertir']
    pasan = [ok for tarea, c, ok in filas if tarea == 'convertir' and c >= t]
    assert len(pasan) >= 10 and pasan.count(False) / len(pasan) <= 0.02, (semilla, t)
    assert senales.calibrar_umbrales([('x', 0.5, False)] * 20) == {}


def test_filas_reales_y_umbral_en_el_interprete(tmp_path, monkeypatch):
    """027:RF-38 — las órdenes con su señal dan las filas (las fallidas no cuentan); el
    intérprete usa el umbral de la tarea y, si la confianza no llega, pregunta."""
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    for i, s in enumerate(('confirmada', 'corregida', 'fallida')):
        almacen.anotar('ordenes', {'plan': f'p{i}', 'texto': 't', 'tarea': 'convertir', 'confianza': 0.9})
        senales.anotar(s, plan=f'p{i}', texto='t', tarea='convertir')
    assert senales.filas_reales() == [('convertir', 0.9, True), ('convertir', 0.9, False)]
    assert senales.calibrar_y_guardar() == {} and almacen.leer_json('umbrales') == {}

    class T:
        def predecir(self, texto):
            return {'tarea': 'convertir', 'confianza': 0.9, 'datos': {}, 'alternativas': []}

    assert interpretar('convierte', transformer=T()).tarea == 'convertir'
    assert interpretar('convierte', transformer=T(), umbrales={'convertir': 0.95}).tarea is None
