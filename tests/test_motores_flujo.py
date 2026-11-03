"""Spec 083: los motores de flujo del oráculo dan lo mismo en la misma red."""
from __future__ import annotations

import numpy as np
import pytest

from convertersmartgrid.digital_twin import motores_flujo as mf
from convertersmartgrid.digital_twin.flujo import SistemaMallado

EXTERNOS = ('newton', 'pgm', 'dss')


def _red(n=40, z=complex(0.004, 0.003), lazo=True):
    """Una línea de ``n`` barras con un lazo, fuente en la 0 y carga en cada barra."""
    pares = [(i, i + 1) for i in range(n - 1)] + ([(5, 15)] if lazo else [])
    a = np.array([p for par in pares for p in par], dtype=np.int64)
    b = np.array([q for p, q in pares for q in (q, p)], dtype=np.int64)
    aristas = np.vstack([a, b])
    zs = np.full(len(a), z, dtype=complex)
    fuente = np.zeros(n, dtype=bool)
    fuente[0] = True
    consigna = np.ones(n)
    return SistemaMallado(aristas, zs, fuente, consigna, np.ones(n, dtype=bool)), np.full(n, 0.002 + 0.0005j)


def _disponible(motor):
    sis, s = _red(6, lazo=False)
    try:
        mf.MOTORES[motor](sis, s)
    except mf.MotorNoDisponible as exc:
        pytest.skip(str(exc))


@pytest.mark.parametrize('motor', ('anderson', *EXTERNOS))
def test_todos_dan_las_mismas_tensiones(motor):
    """083:RF-16, 083:RF-19 — la misma red, la misma respuesta que el Z-bus."""
    _disponible(motor)
    sis, s = _red()
    ref = sis.resolver(s)
    sol = mf.MOTORES[motor](sis, s)
    assert sol.convergio
    assert sol.v == pytest.approx(ref.v, abs=1e-3)
    assert sol.perdidas_pu == pytest.approx(ref.perdidas_pu, rel=0.05)


def test_auto_usa_newton_si_el_zbus_se_rinde(monkeypatch):
    """083:RF-17 — dice cuál decidió."""
    sis, s = _red()
    assert mf.resolver_con(sis, s)[1] == 'zbus'
    monkeypatch.setitem(mf.MOTORES, 'zbus', lambda si, ca: mf._sin_converger(si, ca))
    _disponible('newton')
    sol, nombre = mf.resolver_con(sis, s)
    assert nombre == 'newton' and sol.convergio


def test_la_variable_elige_el_motor_y_uno_desconocido_se_dice(monkeypatch):
    """083:RF-17."""
    sis, s = _red()
    monkeypatch.setenv(mf.VARIABLE_MOTOR, 'anderson')
    assert mf.resolver_con(sis, s)[1] == 'anderson'
    with pytest.raises(ValueError, match='desconocido'):
        mf.resolver_con(sis, s, 'otro')


def test_sin_el_motor_no_se_bloquea(monkeypatch):
    """083:RF-18 — cede a otro."""
    def no_esta(_si, _ca):
        raise mf.MotorNoDisponible('no está')

    monkeypatch.setitem(mf.MOTORES, 'newton', no_esta)
    monkeypatch.setitem(mf.MOTORES, 'zbus', no_esta)
    sis, s = _red()
    sol, nombre = mf.resolver_con(sis, s)
    assert sol.convergio and nombre == 'zbus'
