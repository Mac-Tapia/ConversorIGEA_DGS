"""Spec 027, T32: la búsqueda de hiperparámetros la limitan los ensayos, no el reloj (027:RF-70, RF-71).

En la suite del 2026-11-12, con el acelerador compartido, ``test_busqueda_de_hiperparametros_solo_en_validacion``
falló con «ningún ensayo terminó dentro del presupuesto»: los tres ensayos habían fallado en 0,2 s por
«out of memory» del acelerador, que ``catch=(RuntimeError,)`` tragaba, y el mensaje culpaba al presupuesto.
Aquí el entrenamiento es un doble en el procesador: el error de cada ensayo sale solo de su configuración, así que
la búsqueda es determinista y se puede medir sin el acelerador (106:RF-6 lo
reconoce por el texto: este módulo no nombra la librería ni el acelerador).
"""
from __future__ import annotations

import math
import random
import time
from types import SimpleNamespace

import numpy as np
import pytest

from convertersmartgrid.digital_twin import hiperparametros as hp
from convertersmartgrid.digital_twin import oraculo as orc


def _error(cfg) -> float:
    """Error de validación que depende solo de la configuración: el mínimo, en lr 3·10⁻³ y 7 pasos."""
    return (math.log10(cfg.lr) + 2.5) ** 2 + 0.01 * abs(cfg.pasos - 7) + 1e-3 * cfg.recorte


def _muestras():
    return [SimpleNamespace(ids=['a', 'b'], x=np.zeros((2, 5)), familia=f'f{i}') for i in range(8)]


def _doble(monkeypatch, *, duracion=lambda _n: 0.0, falla=lambda _n: False):
    """Sustituye partición, entrenamiento y medida; ``duracion`` y ``falla`` reciben el número de ensayo."""
    muestras = _muestras()
    grupos = {'entrenamiento': muestras[:4], 'validacion': muestras[4:], 'prueba': []}
    monkeypatch.setattr(hp, 'particionar', lambda _ms: grupos)
    monkeypatch.setattr(hp, 'separar_calibracion', lambda g: {**g, 'calibracion': []})
    llamadas = []

    def entrenar(entrenamiento, cfg, inicial, *, validacion, al_validar):
        n = len(llamadas)
        llamadas.append(cfg)
        if falla(n):
            raise RuntimeError('error del acelerador: out of memory')
        for epoca in range(cfg.epocas):
            al_validar(epoca, _error(cfg) * (1 + 1.0 / (epoca + 1)))
        time.sleep(duracion(n))
        return cfg

    monkeypatch.setattr(hp, 'entrenar_miembro', entrenar)
    monkeypatch.setattr(hp, 'OraculoPINN', lambda estados, cfg, dominio: estados[0])
    monkeypatch.setattr(hp, 'mae', lambda modelo, _ms: _error(modelo))
    return muestras


BASE = orc.Entrenamiento(epocas=12, ocultas=32, pasos=4)


def test_027_rf70_el_tope_de_reloj_no_recorta_la_busqueda(monkeypatch):
    """027:RF-70 — con ensayos lentos y un tope de reloj corto, la búsqueda no devuelve una elección
    hecha con menos ensayos de los pedidos: se para y lo dice, con el tope y los ensayos hechos."""
    muestras = _doble(monkeypatch, duracion=lambda _n: 0.3)
    with pytest.raises(TimeoutError, match=r'tope de seguridad.*027:RF-70'):
        hp.buscar(muestras, base=BASE, ensayos=4, limite_s=0.5, semilla=3)


def test_027_rf70_mismos_ensayos_y_mismo_resultado_con_cualquier_duracion(monkeypatch):
    """027:RF-70 — con la misma semilla, los ensayos pedidos y la misma elección, tarden lo que tarden."""
    muestras = _doble(monkeypatch)
    rapida = hp.buscar(muestras, base=BASE, ensayos=6, limite_s=3600, semilla=5)
    rnd = random.Random(7)
    _doble(monkeypatch, duracion=lambda _n: rnd.uniform(0.0, 0.05))
    lenta = hp.buscar(muestras, base=BASE, ensayos=6, limite_s=3600, semilla=5)
    assert len(rapida['ensayos']) == len(lenta['ensayos']) == 6
    assert rapida['ensayos'] == lenta['ensayos'] and rapida['mejor'] == lenta['mejor']
    assert rapida['cfg'] == lenta['cfg']
    assert rapida['presupuesto'] == {'unidad': 'ensayos', 'ensayos': 6, 'tope_seguridad_s': 3600}


def test_027_rf71_un_ensayo_que_falla_para_la_busqueda_con_su_error(monkeypatch):
    """027:RF-71 — un ensayo que falla (la memoria del acelerador) para la búsqueda con su error; no se elige
    entre los que quedaron, porque la elección dependería de la memoria libre y no de los datos."""
    muestras = _doble(monkeypatch, falla=lambda n: n == 1)
    with pytest.raises(RuntimeError, match=r'ensayo 1.*out of memory.*027:RF-71'):
        hp.buscar(muestras, base=BASE, ensayos=3, limite_s=3600, semilla=3)


def test_027_rf71_si_fallan_todos_dice_el_error_y_no_el_presupuesto(monkeypatch):
    """027:RF-71 — el caso de la suite del 2026-11-12: todos los ensayos sin memoria en el acelerador.
    El mensaje nombra el error del ensayo, no un presupuesto que no se agotó."""
    muestras = _doble(monkeypatch, falla=lambda _n: True)
    with pytest.raises(RuntimeError, match='out of memory') as exc:
        hp.buscar(muestras, base=BASE, ensayos=3, limite_s=600, semilla=3)
    assert 'presupuesto' not in str(exc.value)
