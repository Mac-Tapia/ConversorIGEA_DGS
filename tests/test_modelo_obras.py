"""087:RF-17 a RF-20 — el modelo de árboles, con su puerta: si no supera al orden por costo en otro sistema, no se usa."""
from __future__ import annotations

import random

from convertersmartgrid import modelo_obras as mo
from convertersmartgrid.escalera_optima import Variante


def _fila(sistema, grupo, km, costo, cumple):
    rasgos = {k: 0.0 for k in mo.RASGOS}
    rasgos.update(km_terna=km, costo_anual=costo)
    return mo.fila_medida(sistema, grupo, rasgos, cumple)


def _datos(sistemas, *, aprende=True, semilla=1):
    rnd = random.Random(semilla)
    filas = []
    for s in range(sistemas):
        for g in range(6):
            for i in range(8):
                km = float(i)
                # Las baratas no cumplen; cumple la de más km, que es de las más caras: el orden por costo mide de más.
                cumple = km >= 6 if aprende else rnd.random() < 0.3
                filas.append(_fila(f'S{s}', f'S{s}/G{g}', km, 10.0 + km, cumple))
    return filas


def test_los_rasgos_son_numeros():
    """087:RF-17 — de la variante y del oráculo; sin dato, 0."""
    v = Variante('terna hasta NODE_T_CLIENTE', ('terna',), [{'clase': 'terna'}], {'terna': 3.5})
    r = mo.rasgos_de(v, {'costo_anual': 7.0, 'cumple': True, 'v_min': 0.97})
    assert r['km_terna'] == 3.5 and r['oraculo_cumple'] == 1.0 and r['n_obras'] == 1.0
    assert set(r) == set(mo.RASGOS) and all(isinstance(x, float) for x in r.values())
    assert mo.rasgos_de(v, None)['costo_anual'] == 0.0


def test_el_fichero_ida_y_vuelta(tmp_path):
    """087:RF-17 — añadir y leer; una línea rota no tumba la lectura, y sin fichero no hay nada."""
    ruta = tmp_path / 'm.jsonl'
    assert mo.leer(ruta) == []
    fila = _fila('S', 'S/G', 1.0, 2.0, True)
    mo.anadir(ruta, [fila])
    with open(ruta, 'a', encoding='utf-8') as f:
        f.write('roto\n')
    assert mo.leer(ruta) == [fila]


def test_con_pocos_sistemas_no_se_entrena():
    """087:RF-18 — hacen falta varios sistemas, para poder dejar uno fuera."""
    r = mo.entrenar(_datos(2), 3)
    assert not r['pasa'] and r['modelo'] is None and '2 sistemas' in r['motivo']


def test_el_modelo_que_acierta_en_otro_sistema_pasa():
    """087:RF-18, 087:RF-19 — validado dejando fuera un sistema entero: mide menos que el orden por costo."""
    r = mo.entrenar(_datos(3), 3)
    assert r['pasa'] and r['modelo'] is not None and r['mediciones_modelo'] < r['mediciones_costo']


def test_el_modelo_al_azar_no_se_usa():
    """087:RF-19 — con resultados al azar no hay qué aprender: no pasa la puerta."""
    r = mo.entrenar(_datos(3, aprende=False, semilla=4), 3)
    assert not r['pasa'] and r['modelo'] is None


def test_ordenar_no_descarta_ninguna():
    """087:RF-20 — las mismas variantes, otro orden; sin modelo, el suyo."""
    vs = [Variante(f'v{i}', ('terna',), [{'clase': 'terna'}], {'terna': float(i)}) for i in range(8)]
    r = mo.entrenar(_datos(3), 3)
    ordenadas = mo.ordenar(r['modelo'], vs, {})
    assert sorted(v.nombre for v in ordenadas) == sorted(v.nombre for v in vs)
    assert ordenadas[0].nombre in ('v6', 'v7')
    assert mo.ordenar(None, vs, {}) == vs
