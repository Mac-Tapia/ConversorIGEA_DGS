"""Spec 086, T37: la obra basta para la carga, y lo que ya estaba bajo el límite se dice aparte.

Caso real: SI112 con su obra dejó la carga nueva a 0,963 p.u. y un ramal a 0,9449 p.u., con límite 0,95. La
escalera (025:RF-50) lo da por bueno porque ese ramal no empeora, y el informe decía «obras insuficientes».
"""
from __future__ import annotations

import random

import pytest

from convertersmartgrid import escalera_optima as eo
from convertersmartgrid.estudios_pf import Limites
from convertersmartgrid.informes import (Caso, Extremo, Potencia, Solicitud, baja_ajena_a_la_carga, bajo_limite,
                                         clasificar_bajo_limite, conclusion_factibilidad, conclusiones_factibilidad,
                                         frases_bajo_limite, queda_deficit, veredicto_factibilidad)

LIM = Limites(0.95, 1.05, 100.0)
TOL = 0.005
PERFIL = {
    'escalera': {'cumplimiento': 0.95, 'sorteos': 200, 'tolerancia_pu': TOL, 'tolerancia_carga_pct': 1.0},
    'planificacion': {'tasa_regulada': 0.12, 'vida_util_anios': 30},
    'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100},
}
P = eo.parametros(PERFIL)


def _medida(barras, **extra):
    """Lo que guarda un flujo de la web: lo que ``Caso.desde_medida`` lee."""
    vivas = sorted(barras.items())
    return {'converge': True, 'barras': vivas, 'vm_min': min(barras.values()),
            'vm_min_barra': min(barras, key=barras.get), 'vm_max': max(barras.values()),
            'vm_max_barra': max(barras, key=barras.get), 'cabecera_kw': 1000.0, 'cabecera_kvar': 100.0,
            'perdidas_kw': 10.0, 'perdidas_kvar': 5.0, 'elementos': [('L1', 'ElmLne', 60.0)], **extra}


def _casos(sin, con, cargas=None):
    return (Caso.desde_medida('Sin proyecto', _medida(sin), LIM),
            Caso.desde_medida('Cargas nuevas', _medida(cargas or con), LIM),
            Caso.desde_medida('Con proyecto', _medida(con), LIM))


def test_barra_baja_que_no_empeora_es_deficit_previo_con_su_barra_y_tension():
    """086:RF-48 — la de SI112: el ramal ya estaba bajo el límite y la obra no lo empeora."""
    d = clasificar_bajo_limite({'R1': 0.9452, 'C': 0.97}, {'R1': 0.9449, 'C': 0.963, 'NUEVA': 0.963}, ['NUEVA'], 0.95, TOL)
    assert d['previo'] == [{'barra': 'R1', 'u': 0.9449, 'sin': 0.9452}]
    assert d['causado'] == [] and d['sin_comparacion'] == []
    assert queda_deficit(d)
    texto = ' '.join(frases_bajo_limite(d))
    assert 'Déficit previo, fuera de esta obra' in texto and 'R1' in texto and '0,9449 p.u.' in texto


def test_barra_que_empeora_no_es_previa():
    """086:RF-49 — lo que causa la carga va aparte, y sigue sin pasar (025:RF-50)."""
    sin, con = {'R1': 0.946, 'R2': 0.96}, {'R1': 0.93, 'R2': 0.94}
    d = clasificar_bajo_limite(sin, con, [], 0.95, TOL)
    assert {f['barra'] for f in d['causado']} == {'R1', 'R2'} and not d['previo']
    assert not queda_deficit(d)
    assert not eo.cumple({'converge': True, 'u': sin}, {'converge': True, 'u': con}, [], P)[0]
    assert 'causa la carga' in frases_bajo_limite(d)[0]


def test_sin_dato_de_la_barra_no_se_afirma_que_sea_previa():
    """086:RF-48 — sin «Sin proyecto» para esa barra no se sabe: se dice así, y no bloquea."""
    d = clasificar_bajo_limite({'C': 0.97}, {'C': 0.97, 'T_NUEVO': 0.94}, [], 0.95, TOL)
    assert d['sin_comparacion'] == [{'barra': 'T_NUEVO', 'u': 0.94, 'sin': None}]
    texto = ' '.join(frases_bajo_limite(d))
    assert 'Bajo el límite, sin comparación disponible' in texto and 'revio' not in texto
    assert queda_deficit(d)


def test_sin_deficit_no_hay_nada_que_decir():
    """086:RF-50 — un alimentador sin barras bajas no lleva matiz."""
    d = clasificar_bajo_limite({'A': 0.97}, {'A': 0.96}, [], 0.95, TOL)
    assert frases_bajo_limite(d) == [] and not queda_deficit(d)
    assert frases_bajo_limite(None) == []


def test_la_barra_de_la_carga_nueva_nunca_es_deficit_previo():
    """086:RF-49 — si la carga no llega a su tensión es cosa de la carga, aunque ya estuviera baja."""
    d = clasificar_bajo_limite({'B': 0.94}, {'B': 0.94}, ['B'], 0.95, TOL)
    assert [f['barra'] for f in d['causado']] == ['B'] and not queda_deficit(d)


def test_una_isla_sin_tension_no_es_un_deficit():
    """086:RF-48 — 063:RF-43: 8674 y 8675 de SM218 estaban a 0 p.u.: no es caída, es que no tienen fuente."""
    d = clasificar_bajo_limite({'I': 0.0, 'V': 0.0}, {'I': 0.0, 'V': 0.94}, [], 0.95, TOL)
    assert d['previo'] == [] and d['causado'] == []
    assert d['sin_comparacion'] == [{'barra': 'V', 'u': 0.94, 'sin': None}]


@pytest.mark.parametrize('semilla', (3, 17, 41, 88))
def test_la_clasificacion_dice_lo_mismo_que_el_criterio_de_la_escalera(semilla):
    """086:RF-49 — el criterio no cambia: lo que la escalera rechaza por tensión es «causado», y solo eso."""
    rng = random.Random(semilla)
    for _ in range(200):
        n = rng.randint(1, 8)
        sin = {f'B{i}': rng.uniform(0.90, 1.04) for i in range(n)}
        con = {b: max(0.90, s + rng.uniform(-0.03, 0.03)) for b, s in sin.items()}
        con = {b: min(u, 1.05) for b, u in con.items()}
        bien = eo.cumple({'converge': True, 'u': sin}, {'converge': True, 'u': con}, [], P)[0]
        d = clasificar_bajo_limite(sin, con, [], 0.95, TOL)
        assert bien == (not d['causado']), (sin, con, d)


def test_bajo_limite_lee_las_medidas_como_los_nodos_fuera():
    """086:RF-48 — solo media tensión y sin islas (063:RF-43, RF-44): si no, el recuento y la lista no cuadran."""
    con = _medida({'MT1': 0.94, 'BT1': 0.90, 'ISLA': 0.0}, barras_mt=['MT1', 'ISLA'], sin_tension=['ISLA'])
    d = bajo_limite(_medida({'MT1': 0.942, 'BT1': 0.91}), con, LIM, tolerancia_pu=TOL)
    assert [f['barra'] for f in d['previo']] == ['MT1'] and not d['causado'] and not d['sin_comparacion']


def test_bajo_limite_sin_flujo_previo_no_afirma_nada():
    """086:RF-48 — «Sin proyecto» sin converger: todas sin comparación; con el flujo con obra sin converger, nada."""
    d = bajo_limite({'converge': False}, _medida({'A': 0.94}), LIM, tolerancia_pu=TOL)
    assert [f['barra'] for f in d['sin_comparacion']] == ['A']
    assert bajo_limite(_medida({'A': 0.94}), {'converge': False}, LIM, tolerancia_pu=TOL) is None


def test_conclusion_factible_con_barra_baja_que_no_empeora():
    """086:RF-48, 086:RF-50 — la reproducción de SI112: antes, «obras insuficientes»; la obra basta para la carga."""
    sin, con = {'R1': 0.9452, 'C': 0.97}, {'R1': 0.9449, 'C': 0.97, 'NUEVA': 0.963}
    actual, cargas, proyectado = _casos(sin, con, {'R1': 0.92, 'C': 0.95, 'NUEVA': 0.93})
    d = bajo_limite(_medida(sin), _medida(con), LIM, barras_cargas=['NUEVA'], tolerancia_pu=TOL)
    assert conclusion_factibilidad(actual, cargas, proyectado, LIM).clave == 'obras_insuficientes'
    c = conclusion_factibilidad(actual, cargas, proyectado, LIM, bajo_limite=d)
    assert c.factible and c.clave == 'con_obras_deficit'


def test_conclusion_con_barra_que_empeora_sigue_sin_pasar():
    """086:RF-49 — y lo que hay que corregir es lo que causa la carga, no el déficit que ya estaba."""
    sin, con = {'R1': 0.946, 'R2': 0.96, 'C': 0.97}, {'R1': 0.945, 'R2': 0.94, 'C': 0.97}
    actual, cargas, proyectado = _casos(sin, con)
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)
    c = conclusion_factibilidad(actual, cargas, proyectado, LIM, bajo_limite=d)
    assert not c.factible and c.clave == 'obras_insuficientes'
    assert 'R2' in c.elementos and 'R1' not in c.elementos


def test_conclusion_sin_dato_de_la_barra_no_bloquea():
    """086:RF-48 — una barra sin comparación no impide concluir: se lista como tal."""
    sin, con = {'C': 0.97}, {'C': 0.97, 'T_NUEVO': 0.94}
    actual, _cargas, proyectado = _casos(sin, con)
    cargas = Caso.desde_medida('Cargas nuevas', _medida({'C': 0.90}), LIM)
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)
    c = conclusion_factibilidad(actual, cargas, proyectado, LIM, bajo_limite=d)
    assert c.factible and c.clave == 'con_obras_deficit'


def test_conclusion_sin_deficit_es_la_de_siempre():
    """086:RF-50 — sin barras bajas, la conclusión y el texto de siempre."""
    sin, con = {'C': 0.97}, {'C': 0.96}
    actual, proyectado = (Caso.desde_medida(n, _medida(b), LIM) for n, b in (('Sin', sin), ('Con', con)))
    cargas = Caso.desde_medida('Cargas nuevas', _medida({'C': 0.90}), LIM)
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)
    assert conclusion_factibilidad(actual, cargas, proyectado, LIM, bajo_limite=d).clave == 'con_obras'


@pytest.mark.parametrize('cambio', ({'elementos': [('L1', 'ElmLne', 130.0)]}, {'vm_max': 1.08, 'vm_max_barra': 'ALTA'}))
def test_otra_violacion_no_se_disculpa_con_el_deficit(cambio):
    """086:RF-50 — el matiz es solo de la tensión baja: una sobrecarga o una sobretensión siguen sin pasar."""
    sin, con = {'R1': 0.945, 'C': 0.97}, {'R1': 0.945, 'C': 0.97}
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)
    proyectado = Caso.desde_medida('Con proyecto', _medida(con, **cambio), LIM)
    actual = Caso.desde_medida('Sin proyecto', _medida(sin), LIM)
    assert not baja_ajena_a_la_carga(proyectado, actual, d, LIM)
    assert not conclusion_factibilidad(actual, actual, proyectado, LIM, bajo_limite=d).factible


def test_barra_fuera_por_arriba_no_se_disculpa():
    """086:RF-50 — un nodo sobre la banda no está en la lista de bajas: el recuento no cuadra y no pasa."""
    sin, con = {'R1': 0.945, 'ALTA': 1.0}, {'R1': 0.945, 'ALTA': 1.06}
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)
    proyectado = Caso.desde_medida('Con proyecto', _medida(con, vm_max=1.0, vm_max_barra='C'), LIM)
    assert proyectado.nodos_fuera == 2
    assert not baja_ajena_a_la_carga(proyectado, Caso.desde_medida('Sin', _medida(sin), LIM), d, LIM)


def test_desequilibrado_que_empeora_en_su_fase_no_pasa():
    """086:RF-50 — la lista va por barra y la mínima por fase: que baje la fase no lo disculpa la barra."""
    sin, con = {'R1': 0.945, 'C': 0.97}, {'R1': 0.945, 'C': 0.97}
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)

    def caso(fase_a):
        return Caso('Con', True, fuente=Potencia(1000, 100), nodos_fuera=1, tension_max=Extremo(1.0, 'C'),
                    tension_min={'A': Extremo(fase_a, 'R1'), 'B': Extremo(0.945, 'R1'), 'C': Extremo(0.95, 'C')})

    assert baja_ajena_a_la_carga(caso(0.944), caso(0.944), d, LIM)
    assert not baja_ajena_a_la_carga(caso(0.92), caso(0.944), d, LIM)


SOLICITUD = Solicitud(cliente='CLIENTE', ubicacion='X', tipo_solicitud='Factibilidad', potencia_kw=100,
                      fecha_solicitud=__import__('datetime').date(2026, 8, 1), alimentador='AL1', set_nombre='S',
                      tension_kv=10, transformador='T', expediente='E', en_concesion=True)


def test_el_veredicto_sin_cargas_nuevas_tampoco_dice_que_quede_dentro_de_la_banda():
    """086:RF-50 — sin el flujo de «Cargas nuevas», el apartado b) del modelo decía «dentro de la banda admitida»."""
    sin, con = {'R1': 0.945, 'C': 0.97}, {'R1': 0.9449, 'C': 0.97}
    actual, _c, proyectado = _casos(sin, con)
    d = bajo_limite(_medida(sin), _medida(con), LIM, tolerancia_pu=TOL)
    assert not veredicto_factibilidad(proyectado, None, LIM, exigir_transformador=False).factible
    v = veredicto_factibilidad(proyectado, None, LIM, exigir_transformador=False, actual=actual, bajo_limite=d)
    assert v.factible
    b = conclusiones_factibilidad(SOLICITUD, v, 'NMT', None, bajo_limite=d)[1]
    assert 'admite la carga' in b and 'dentro de la banda' not in b and 'bajo el límite' in b
    sin_deficit = conclusiones_factibilidad(SOLICITUD, v, 'NMT', None)[1]
    assert 'dentro de la banda admitida' in sin_deficit


def test_los_textos_no_llevan_codigos_ni_rutas():
    """086:RF-48 — los lee el operador y el destinatario del Word."""
    d = clasificar_bajo_limite({'R1': 0.945}, {'R1': 0.945, 'T': 0.94, 'N': 0.93}, ['N'], 0.95, TOL)
    for texto in frases_bajo_limite(d):
        assert 'RF-' not in texto and '/' not in texto and '\\' not in texto
