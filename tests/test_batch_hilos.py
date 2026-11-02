"""065:RF-25: cada proceso del reparto con un hilo de cálculo, sin tocar lo que fijó el operador."""
from __future__ import annotations

import os

from convertersmartgrid.batch import _HILOS_DE_CALCULO, _un_hilo_de_calculo


def test_un_hilo_mientras_dura_y_entorno_restituido(monkeypatch):
    """065:RF-25 — los procesos heredan un hilo; al terminar, el entorno queda como estaba."""
    for v in _HILOS_DE_CALCULO:
        monkeypatch.delenv(v, raising=False)
    with _un_hilo_de_calculo():
        assert all(os.environ[v] == '1' for v in _HILOS_DE_CALCULO)
    assert not any(v in os.environ for v in _HILOS_DE_CALCULO)


def test_lo_que_fijo_el_operador_se_respeta(monkeypatch):
    """065:RF-25 — un valor ya fijado no se pisa, ni durante el reparto ni después."""
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '3')
    with _un_hilo_de_calculo():
        assert os.environ['OPENBLAS_NUM_THREADS'] == '3'
    assert os.environ['OPENBLAS_NUM_THREADS'] == '3'
