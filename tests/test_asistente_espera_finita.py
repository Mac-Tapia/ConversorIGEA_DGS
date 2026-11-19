"""Spec 070, RF-87 (C2 del diagnóstico del 18-11, H03): el asistente nunca espera sin fin a la web.

- Un trabajo «interrumpido» (la web cayó con él en marcha, 096) termina la espera y el paso falla con su motivo; antes
  el cliente lo seguía consultando sin fin (sonda H03b).
- Cada petición lleva su límite de espera (sonda H03a).
- La espera de un trabajo tiene un plazo total, y si la web deja de responder varias veces seguidas se dice.

El cliente HTTP es de la prueba: anota lo que recibe y responde lo que se le pide; nada sale de la máquina.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from convertersmartgrid.aplicacion.asistente import ejecutor


class _Http:
    """Responde cada GET de un trabajo con el estado que toca y anota los kwargs de cada petición."""

    def __init__(self, estados):
        self.estados, self.llamadas = list(estados), []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        assert len(self.llamadas) <= 50, 'el asistente consulta la web sin fin'
        actual = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        if isinstance(actual, Exception):
            raise actual
        return SimpleNamespace(status_code=200, content=b'x', json=lambda: {'id': 't1', 'status': actual},
                               text='')


def _cliente(http, **kw):
    return ejecutor.ClienteWeb(http=http, base='http://127.0.0.1:1', espacio='e1', intervalo_s=0.0, **kw)


def test_cada_peticion_lleva_su_limite_de_espera():
    """070:RF-87 (H03a) — ninguna petición del asistente a la web espera sin límite."""
    http = _Http(['done'])
    _cliente(http).pedir('GET', '/api/jobs/t1')
    assert http.llamadas and http.llamadas[0][2].get('timeout'), http.llamadas


def test_un_trabajo_interrumpido_termina_la_espera_y_el_paso_falla_con_su_motivo():
    """070:RF-87 (H03b) — «interrumpido» termina la espera (antes se consultaba sin fin) y el paso no se da por bueno."""
    http = _Http(['running', 'interrumpido'])
    estado = _cliente(http).esperar({'id': 't1'})
    assert estado['status'] == 'interrumpido' and len(http.llamadas) == 2, http.llamadas
    pasos = [ejecutor.Paso('un trabajo', 'POST', '/convert', {})]
    http = _Http(['queued', 'interrumpido'])
    with pytest.raises(ejecutor.PasoFallido, match='interrumpido'):
        ejecutor.ejecutar(pasos, _cliente(http))


def test_la_espera_tiene_plazo_y_la_web_caida_se_dice():
    """070:RF-87 — un trabajo que no termina deja de esperarse al pasar el plazo, y una web que no responde varias
    veces seguidas da un fallo que lo dice, en vez de seguir consultando."""
    assert getattr(ejecutor, 'FALLOS_SEGUIDOS', 0) >= 1, 'la espera no se rinde ante una web que no responde'
    with pytest.raises(ejecutor.PasoFallido, match='no terminó'):
        _cliente(_Http(['running']), plazo_trabajo_s=0.0).esperar({'id': 't1'})
    caida = _Http([ConnectionError('rechazada')])
    with pytest.raises(ejecutor.PasoFallido, match='no responde'):
        _cliente(caida).esperar({'id': 't1'})
    assert len(caida.llamadas) == ejecutor.FALLOS_SEGUIDOS
