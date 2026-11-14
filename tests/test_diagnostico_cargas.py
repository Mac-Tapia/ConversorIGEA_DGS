"""086:RF-48 ampliada: el diagnóstico de lo que provocan las cargas nuevas y si «Con proyecto» lo corrige."""

from __future__ import annotations

from convertersmartgrid.estudios_pf import Limites
from convertersmartgrid.informes import diagnostico_de_cargas

LIM = Limites(tension_min_pu=0.95, tension_max_pu=1.05, cargabilidad_max_pct=100.0)


def _medida(barras, elementos, converge=True):
    return {'converge': converge, 'barras': list(barras.items()),
            'elementos': [[n, 'ElmLne', c] for n, c in elementos.items()]}


# Cabecera C, y una línea C-B1-B2-B3; la carga nueva cuelga de B3.
GEO = {'cabecera': 'C', 'barras': [['C', -13.5, -76.0, 1.0, 10.0], ['B1', -13.51, -76.0, 1.0, 10.0],
                                   ['B2', -13.52, -76.0, 1.0, 10.0], ['B3', -13.53, -76.0, 1.0, 10.0]],
       'tramos': [['L1', [[-13.5, -76.0], [-13.51, -76.0]], 0, 'C', 'B1', 'T', 1.1],
                  ['L2', [[-13.51, -76.0], [-13.52, -76.0]], 0, 'B1', 'B2', 'T', 1.1],
                  ['L3', [[-13.52, -76.0], [-13.53, -76.0]], 0, 'B2', 'B3', 'T', 1.1]],
       'acoples': []}

SIN = _medida({'C': 1.0, 'B1': 0.99, 'B2': 0.97, 'B3': 0.94}, {'L1': 60.0, 'L2': 50.0, 'L3': 40.0})
CARGAS = _medida({'C': 1.0, 'B1': 0.97, 'B2': 0.93, 'B3': 0.91}, {'L1': 120.0, 'L2': 110.0, 'L3': 80.0})


def test_lo_que_provoca_la_carga_y_lo_que_ya_estaba_van_aparte():
    """086:RF-48 — B2 baja por la carga; B3 ya estaba baja sin ella. L1 y L2 se sobrecargan por la carga, en un
    trecho de C a B2."""
    d = diagnostico_de_cargas(SIN, CARGAS, None, LIM, GEO)
    assert [f['barra'] for f in d['tension']['provocadas']] == ['B2']
    assert [f['barra'] for f in d['tension']['previas']] == ['B3']
    assert [f['elemento'] for f in d['sobrecargas']['provocadas']] == ['L1', 'L2']
    [trecho] = d['trechos']
    assert (trecho['desde'], trecho['hasta'], trecho['tramos']) == ('C', 'B2', ['L1', 'L2'])
    assert trecho['carga_max'] == 120.0
    # Sin «Con proyecto» no se dice si se corrigió.
    assert d['con_proyecto'] is False and d['corregidos'] is None and trecho['estado'] is None
    assert d['provocados'] == 3


def test_con_proyecto_dice_que_se_corrigio_y_que_sigue():
    """086:RF-48 — con las obras, L1 y L2 quedan bajo el 100 % (corregido) y B2 sigue a 0,94 p.u. (sigue)."""
    con = _medida({'C': 1.0, 'B1': 0.98, 'B2': 0.94, 'B3': 0.96}, {'L1': 70.0, 'L2': 65.0, 'L3': 50.0})
    d = diagnostico_de_cargas(SIN, CARGAS, con, LIM, GEO)
    assert {f['elemento']: f['estado'] for f in d['sobrecargas']['provocadas']} == {'L1': 'corregido', 'L2': 'corregido'}
    assert d['trechos'][0]['estado'] == 'corregido'
    [b2] = d['tension']['provocadas']
    assert (b2['estado'], b2['con']) == ('sigue', 0.94)
    assert (d['corregidos'], d['siguen']) == (2, 1)
    assert d['tension_min'] == {'sin': 0.94, 'cargas': 0.91, 'con': 0.94}


def test_sin_flujo_de_cargas_no_se_evalua():
    """086:RF-48 — sin el flujo de «Cargas nuevas» convergido no hay diagnóstico que dar."""
    d = diagnostico_de_cargas(SIN, _medida({}, {}, converge=False), None, LIM, GEO)
    assert d['evaluado'] is False and d['provocados'] == 0


def test_el_diagnostico_de_42_sale_de_los_flujos_guardados(monkeypatch):
    """017:RF-106 ampliada — 4.2 muestra el diagnóstico con los flujos guardados de la última corrida de cada
    alimentador; sin flujo de «Cargas nuevas» no hay diagnóstico para ese alimentador."""
    from convertersmartgrid.web import services

    flujos = {'sin': {'medidas': {'AL01': SIN, 'AL02': SIN}, 'geo': {'AL01': GEO}},
              'cargas': {'medidas': {'AL01': CARGAS}, 'geo': {'AL01': GEO}}, 'con': None}
    monkeypatch.setattr(services, '_corridas_de_estudios', lambda _ws, _p: [])
    monkeypatch.setattr(services, '_ultimo_estudio', lambda _ws, rol, *_a: flujos[rol])
    monkeypatch.setattr('convertersmartgrid.estudios_pf.limites_de_perfil', lambda: LIM)
    d = services.diagnostico_cargas(None, 'P', ['AL01', 'AL02'])['diagnosticos']
    assert list(d) == ['AL01'] and d['AL01']['provocados'] == 3 and d['AL01']['trechos'][0]['desde'] == 'C'
