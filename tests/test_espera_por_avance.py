"""Spec 106, T6 — las pruebas esperan el trabajo real por su estado y por su avance, nunca con un tope fijo corto
(106:RF-20; lección B17). Un cliente sintético hace de la web: sin red, sin la cola y sin esperar de verdad minutos."""
from __future__ import annotations

import time

import pytest

from apoyo import esperar_trabajo


class _Web:
    """Responde ``/api/jobs/<id>`` con lo que diga ``estado(t)``, siendo ``t`` los segundos desde el primer GET."""

    def __init__(self, estado):
        self.estado, self.inicio = estado, None

    def get(self, _url):
        if self.inicio is None:
            self.inicio = time.monotonic()
        estado = self.estado(time.monotonic() - self.inicio)
        return type('R', (), {'json': lambda _self: estado})()


def _avanza(dura: float):
    """Un trabajo lento que avanza: su progreso cambia cada décima y termina a los ``dura`` segundos."""
    def estado(t):
        if t >= dura:
            return {'id': 'j', 'status': 'done', 'progress': None}
        return {'id': 'j', 'status': 'running', 'progress': {'done': int(t * 10), 'total': int(dura * 10)}}
    return estado


def test_106_rf20_un_trabajo_lento_que_avanza_no_falla_por_tiempo():
    """106:RF-20 — con una ventana sin avance corta, un trabajo que tarda más que ella pero avanza llega a su fin; la
    espera de tope fijo lo daba por fallido a los mismos segundos."""
    final = esperar_trabajo(_Web(_avanza(0.6)), {'id': 'j', 'title': 'lento'}, timeout=0.2)
    assert final['status'] == 'done'


def test_106_rf20_un_trabajo_parado_falla_diciendo_en_que_se_quedo():
    """106:RF-20 — un trabajo que deja de avanzar falla en su ventana, diciendo su estado y su progreso."""
    parado = _Web(lambda t: {'id': 'j', 'status': 'running', 'progress': {'done': 3, 'total': 9}})
    with pytest.raises(AssertionError) as fallo:
        esperar_trabajo(parado, {'id': 'j', 'title': 'parado'}, timeout=0.15)
    assert 'no avanzó en 0.15 s' in str(fallo.value) and "'done': 3" in str(fallo.value)


def test_106_rf20_interrumpido_tambien_termina_la_espera():
    """106:RF-20 — «interrumpido» es un final: la espera devuelve el estado en lugar de esperar al tope."""
    final = esperar_trabajo(_Web(lambda t: {'id': 'j', 'status': 'interrumpido', 'progress': None}),
                            {'id': 'j'}, timeout=0.2)
    assert final['status'] == 'interrumpido'
