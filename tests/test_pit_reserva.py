"""Spec 107 T24 — transformadores de reserva compartida con el procedimiento vigente del registro (107:RF-16).

La regla de decisión no está en el código: el horizonte, el umbral de beneficio/costo, el costo de la energía no
servida y la exclusión por tensión salen del registro normativo. Dos registros sintéticos con umbrales distintos dan
decisiones distintas, y sin la regla sale el aviso que la nombra. Todo sintético: actos, SET y cifras inventados.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from convertersmartgrid.pit.ambito import PitError
from convertersmartgrid.pit.reserva import evaluar_reserva
from convertersmartgrid.registro_normativo import cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = {'nombre': 'modelo_confiabilidad_sintetico.xlsx', 'huella': 'e' * 64}


def _regla(clave, valor):
    return {'clave': clave, 'valor': valor, 'cita_literal': f'«{clave}»', 'pagina': '7'}


def _registro(carpeta: Path, *, umbral=1, horizonte=3, limite_kv=100, sin=()):
    reglas = {'pit.reserva.beneficio_costo_minimo': umbral, 'pit.reserva.horizonte_pns_anios': horizonte,
              'pit.reserva.excluye_trifasicos_mayor_kv': limite_kv,
              'pit.reserva.costo_ens_falla': {'base': 'costo_racionamiento', 'factor_numerador_usd_mwh': 2.0,
                                              'factor_denominador_usd_mwh': 1.0},
              'pit.reserva.tipo': 'compartida'}
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [
        {'acto': 'SINT-RESERVA', 'titulo': 'Procedimiento sintético', 'estado_juridico': 'vigente_comprobada',
         'sha256': 'a' * 64, 'reglas': [_regla(k, v) for k, v in reglas.items() if k not in sin]}]}),
        encoding='utf-8')
    return cargar_registro(carpeta)


def _candidato(nombre, inversion, ens, **kw):
    return {'subestacion': nombre, 'titular': 'TITULAR-X', 'capacidad_mva': 25.0, 'tension_max_kv': 60.0,
            'trifasico': True, 'transportable': True, 'inversion_usd': inversion, 'ens_evitada_mwh': ens, **kw}


RED = {'area': 'AREA-X', 'anios': [2001, 2002, 2003], 'huella': 'f' * 64}


def _area(candidatos, tasa=0.0, red=None, de_la_fuente=None):
    """El área con su red vigente y la fuente del modelo de confiabilidad, hecha sobre esa misma red."""
    red = dict(RED if red is None else red)
    fuente = {**FUENTE, **({'area': RED['area'], 'anios': RED['anios'], 'huella_red': RED['huella']}
                           if de_la_fuente is None else de_la_fuente)}
    return {'nombre': 'AREA-X', 'fuente': fuente, 'red': red, 'costo_racionamiento_usd_mwh': 100.0, 'tasa': tasa,
            'candidatos': candidatos}


def test_la_reserva_se_elige_con_la_regla_del_registro(tmp_path):
    """107:RF-16 — B/C con el costo de la ENS de la regla (100 × 2/1 = 200 USD/MWh) y el umbral registrado; se elige
    la viable de mayor beneficio neto."""
    registro = _registro(tmp_path / 'r')
    area = _area([_candidato('SET-A', 1000.0, [2, 2, 2]),     # B = 1200, B/C 1,2, neto 200
                  _candidato('SET-B', 3000.0, [6, 6, 6]),     # B = 3600, B/C 1,2, neto 600
                  _candidato('SET-C', 1000.0, [1, 1, 1])])    # B = 600, B/C 0,6
    resultado = evaluar_reserva(registro, area)
    por_set = {c['subestacion']: c for c in resultado['candidatos']}
    assert por_set['SET-A']['beneficio_vp_usd'] == pytest.approx(1200.0)
    assert por_set['SET-C']['viable'] is False and 'B/C' in por_set['SET-C']['motivo']
    assert resultado['elegida']['subestacion'] == 'SET-B'
    assert not resultado['avisos'] or all('modelo oficial' in a for a in resultado['avisos'])
    claves = {r['clave'] for r in resultado['reglas']}
    assert {'pit.reserva.beneficio_costo_minimo', 'pit.reserva.horizonte_pns_anios',
            'pit.reserva.costo_ens_falla'} <= claves
    assert all(r['huella'] and r['pagina'] for r in resultado['reglas'])


def test_otro_umbral_en_el_registro_cambia_la_decision(tmp_path):
    """107:RF-16 — la cifra sale del registro: con umbral 1,5 ninguna de las dos es viable."""
    area = _area([_candidato('SET-A', 1000.0, [2, 2, 2]), _candidato('SET-B', 3000.0, [6, 6, 6])])
    assert evaluar_reserva(_registro(tmp_path / 'a', umbral=1), area)['elegida'] is not None
    resultado = evaluar_reserva(_registro(tmp_path / 'b', umbral=1.5), area)
    assert resultado['elegida'] is None
    assert all(not c['viable'] for c in resultado['candidatos'])


def test_beneficio_costo_igual_al_umbral_no_justifica(tmp_path):
    """107:RF-16 — la norma pide B/C MAYOR que el umbral: igual no basta."""
    resultado = evaluar_reserva(_registro(tmp_path / 'r'), _area([_candidato('SET-A', 1200.0, [2, 2, 2])]))
    assert resultado['candidatos'][0]['bc'] == pytest.approx(1.0)
    assert resultado['elegida'] is None


def test_la_tasa_actualiza_el_beneficio(tmp_path):
    """107:RF-16 — el beneficio de cada año se trae a valor presente con la tasa declarada."""
    resultado = evaluar_reserva(_registro(tmp_path / 'r'), _area([_candidato('SET-A', 100.0, [1, 1, 1])], tasa=0.1))
    esperado = sum(200.0 / 1.1 ** i for i in (1, 2, 3))
    assert resultado['candidatos'][0]['beneficio_vp_usd'] == pytest.approx(esperado)


def test_trifasico_de_mas_tension_que_el_limite_y_no_transportable_se_excluye(tmp_path):
    """107:RF-16 — la exclusión del registro se aplica con su motivo; si es transportable, sigue."""
    area = _area([_candidato('SET-A', 1000.0, [6, 6, 6], tension_max_kv=138.0, transportable=False),
                  _candidato('SET-B', 1000.0, [6, 6, 6], tension_max_kv=138.0, transportable=True)])
    por_set = {c['subestacion']: c for c in evaluar_reserva(_registro(tmp_path / 'r'), area)['candidatos']}
    assert por_set['SET-A']['excluida'] and '100' in por_set['SET-A']['motivo']
    assert not por_set['SET-B']['excluida'] and por_set['SET-B']['viable']


@pytest.mark.parametrize('falta', ('pit.reserva.beneficio_costo_minimo', 'pit.reserva.horizonte_pns_anios',
                                   'pit.reserva.costo_ens_falla'))
def test_sin_la_regla_sale_el_aviso_que_la_nombra(tmp_path, falta):
    """107:RF-16 — sin la regla no se elige ninguna reserva y el aviso la nombra; no se supone ninguna cifra."""
    resultado = evaluar_reserva(_registro(tmp_path / 'r', sin=(falta,)),
                                _area([_candidato('SET-A', 1000.0, [6, 6, 6])]))
    assert resultado['elegida'] is None
    assert any(falta in a for a in resultado['avisos'])


@pytest.mark.parametrize('cambio, mensaje', (
    ({'ens_evitada_mwh': [1, 1]}, 'horizonte'),
    ({'ens_evitada_mwh': [1, -1, 1]}, 'ens_evitada_mwh'),
    ({'inversion_usd': 0}, 'inversion_usd'),
), ids=('ens_de_otro_horizonte', 'ens_negativa', 'inversion_cero'))
def test_candidato_invalido_es_un_error_que_lo_nombra(tmp_path, cambio, mensaje):
    """107:RF-16 — una serie de otro largo que el horizonte, una ENS negativa o una inversión nula se rechazan."""
    with pytest.raises(PitError, match=mensaje):
        evaluar_reserva(_registro(tmp_path / 'r'), _area([_candidato('SET-A', 1000.0, [1, 1, 1], **cambio)]))


def test_area_sin_fuente_o_sin_candidatos_es_un_error(tmp_path):
    """107:RF-16 — sin la huella de la fuente o sin candidatos no hay decisión que sustentar."""
    registro = _registro(tmp_path / 'r')
    with pytest.raises(PitError, match='fuente'):
        evaluar_reserva(registro, {**_area([_candidato('SET-A', 1.0, [1, 1, 1])]), 'fuente': {}})
    with pytest.raises(PitError, match='candidatos'):
        evaluar_reserva(registro, _area([]))


def test_area_sorteada_elige_la_de_mayor_beneficio_neto(tmp_path):
    """107:RF-16 — con candidatos sorteados, la elegida es la viable de mayor beneficio neto, sin depender del orden."""
    registro = _registro(tmp_path / 'r')
    rnd = random.Random(20261114)
    candidatos = [_candidato(f'SET-{i}', rnd.uniform(500, 5000), [rnd.uniform(0, 10) for _ in range(3)])
                  for i in range(8)]
    a = evaluar_reserva(registro, _area(candidatos))
    b = evaluar_reserva(registro, _area(list(reversed(candidatos))))
    viables = [c for c in a['candidatos'] if c['viable']]
    if viables:
        mejor = max(viables, key=lambda c: c['beneficio_vp_usd'] - c['inversion_usd'])
        assert a['elegida']['subestacion'] == mejor['subestacion'] == b['elegida']['subestacion']
    else:
        assert a['elegida'] is None and b['elegida'] is None


@pytest.mark.parametrize('de_la_fuente, causa', (
    ({'area': 'AREA-Y', 'anios': RED['anios'], 'huella_red': RED['huella']}, 'área'),
    ({'area': 'AREA-X', 'anios': [2002, 2003, 2004], 'huella_red': RED['huella']}, 'años'),
    ({'area': 'AREA-X', 'anios': RED['anios'], 'huella_red': '0' * 64}, 'red'),
    ({}, 'no declara'),
), ids=('otra_area', 'otros_anios', 'otra_red', 'sin_declarar'))
def test_resultado_de_confiabilidad_de_otra_area_anios_o_red_no_decide(tmp_path, de_la_fuente, causa):
    """107:RF-16 (condición de ca) — la ENS evitada tiene que ser de la misma área, los mismos años y la misma red,
    con la huella comparada con la red vigente; si no coincide o falta, no hay decisión y el aviso dice la causa."""
    area = _area([_candidato('SET-B', 3000.0, [6, 6, 6])], de_la_fuente=de_la_fuente)
    area['fuente'] = {'nombre': FUENTE['nombre'], 'huella': FUENTE['huella'], **de_la_fuente}
    resultado = evaluar_reserva(_registro(tmp_path / 'r'), area)
    assert resultado['elegida'] is None
    assert any(causa in a for a in resultado['avisos']), resultado['avisos']


def test_area_sin_red_vigente_no_decide(tmp_path):
    """107:RF-16 — sin la huella de la red vigente no hay con qué comparar: no se decide y se avisa."""
    area = _area([_candidato('SET-B', 3000.0, [6, 6, 6])])
    del area['red']
    resultado = evaluar_reserva(_registro(tmp_path / 'r'), area)
    assert resultado['elegida'] is None and any('red vigente' in a for a in resultado['avisos'])


def test_registro_real_trae_las_reglas_de_la_094_2022():
    """107:RF-16 — con el registro real, la decisión usa las reglas de la RCD 094-2022 y avisa del modelo oficial."""
    registro = cargar_registro(RAIZ / 'config' / 'normativa')
    ens = [1.0] * registro.regla('pit.reserva.horizonte_pns_anios').regla.valor
    resultado = evaluar_reserva(registro, _area([_candidato('SET-A', 1000.0, ens)]))
    assert {r['norma'] for r in resultado['reglas']} == {'RCD 094-2022-OS/CD'}
    assert any('modelo oficial' in a for a in resultado['avisos'])
