"""Spec 006: reparto de la máxima de cabecera entre las SED, sin DIgSILENT."""
from __future__ import annotations

import math
import random

import pytest

from convertersmartgrid.dominio.ajuste_cabecera import (
    ESCALERA,
    MedidaConjunta,
    MedidaZonas,
    cuadrar_conjunto,
    cuadrar_zonas,
    objetivo_zonas_de,
    MITADES,
    AjusteError,
    Medida,
    cuadrar,
    fijas_de,
    objetivo_de,
    reparto_inicial,
)
from convertersmartgrid.dominio import ajuste_cabecera as ac

CALIBRACION_IMPOSIBLE = getattr(ac, 'CALIBRACION_IMPOSIBLE', 'IMPOSIBLE')
NO_CALIBRABLE = getattr(ac, 'NO_CALIBRABLE', 'NO_CALIBRABLE')
SEMILLA = random.SystemRandom().randrange(1, 2 ** 31)


def _maxima(**kw):
    base = {'medidor': 'M1', 'alimentador': 'A1', 'kw': 1000.0, 'kvar': 300.0,
            'fp': None, 'error': None}
    base.update(kw)
    return base


def _cliente(codigo, sed, pot, ea=None, eri=None):
    return {'codigo': codigo, 'sed': sed, 'pot': pot, 'ea': ea, 'eri': eri}


def test_objetivo_es_la_maxima_mostrada():
    """006:RF-1 — el kW y el kVAR del registro de la máxima."""
    o = objetivo_de(_maxima())
    assert (o.kw, o.kvar, o.medidor) == (1000.0, 300.0, 'M1')
    assert o.tan_phi == pytest.approx(0.3)


def test_objetivo_sin_kvar_lo_saca_del_fp():
    """006:RF-1 — si el registro no trae kVAR pero sí FP, el kVAR sale del FP."""
    o = objetivo_de(_maxima(kvar=None, fp=0.8))
    assert o.kvar == pytest.approx(750.0)


@pytest.mark.parametrize('maxima', [_maxima(kw=None, error='M1 no está en ningún libro'),
                                    _maxima(kw=None), _maxima(kw=0.0),
                                    _maxima(kvar=None, fp=None)])
def test_sin_maxima_no_se_ajusta(maxima):
    """006:RF-3 — un medidor sin máxima (o sin kVAR ni FP) no da objetivo."""
    with pytest.raises(AjusteError):
        objetivo_de(maxima)


def test_fijas_suman_sus_clientes():
    """006:RF-5 / 006:RF-6 — kW suma de Pot; kVAR con la relación ERI/EA de sus clientes."""
    o = objetivo_de(_maxima())
    fijas = fijas_de([_cliente('1', 'E1', 100.0, ea=1000.0, eri=500.0),
                      _cliente('2', 'e 1', 50.0, ea=3000.0, eri=0.0),
                      _cliente('3', 'E2', 20.0, ea=10.0, eri=10.0)], o)
    assert set(fijas) == {'E1', 'E2'}
    assert fijas['E1'].kw == 150.0
    # Cada cliente con su propia relación: 100 × 500/1000 + 50 × 0/3000.
    assert fijas['E1'].kvar == pytest.approx(50.0)
    assert fijas['E1'].clientes == ['1', '2']
    assert fijas['E2'].kvar == pytest.approx(20.0)


def test_cliente_sin_energias_usa_el_fp_del_objetivo():
    """006:RF-7 — sin EA o ERI, su kVAR con el FP del objetivo, y se dice."""
    o = objetivo_de(_maxima())
    fijas = fijas_de([_cliente('1', 'E1', 100.0, ea=None, eri=5.0)], o)
    assert fijas['E1'].kvar == pytest.approx(30.0)
    assert any('1' in a and 'FP' in a for a in fijas['E1'].avisos)


@pytest.mark.parametrize('native_q', [-250.0, 0.0, 300.0, 900.0])
def test_kw_acceptance_never_depends_on_native_q(native_q):
    from convertersmartgrid.dominio.ajuste_cabecera import Medida, cuadrado_kw

    objetivo = objetivo_de(_maxima(kw=1000.0, kvar=300.0))
    assert cuadrado_kw(Medida(True, 1005.0, native_q), objetivo, 0.01)
    assert not cuadrado_kw(Medida(True, 1011.0, native_q), objetivo, 0.01)
    assert not cuadrado_kw(Medida(False, 1000.0, native_q), objetivo, 0.01)


def test_kvar_difference_is_complete_and_never_blocks_including_zero_target():
    from convertersmartgrid.dominio.ajuste_cabecera import Medida, kvar_difference

    objetivo = objetivo_de(_maxima(kw=1000.0, kvar=300.0))
    aviso = kvar_difference(Medida(True, 1000.0, 450.0), objetivo, 0.01)
    assert aviso == {
        'status': 'AVISO_KVAR', 'objetivo_kvar': 300.0, 'red_nativa_kvar': 450.0,
        'diferencia_kvar': 150.0, 'diferencia_relativa': pytest.approx(0.5),
        'tolerancia': 0.01, 'supera_tolerancia': True, 'bloquea': False,
    }
    cero = objetivo_de(_maxima(kw=1000.0, kvar=0.0))
    dato = kvar_difference(Medida(True, 1000.0, -5.0), cero, 0.01)
    assert dato['diferencia_relativa'] == pytest.approx(-0.005)
    assert dato['status'] == 'OK' and dato['bloquea'] is False


def test_cuadrar_preserves_initial_q_factor_and_stops_when_kw_matches():
    from convertersmartgrid.dominio.ajuste_cabecera import Medida

    objetivo, _kva, reparto = _caso(n=2, kw=1000.0, kvar=300.0)
    vistos = []

    def flujo(actual):
        vistos.append((actual.a, actual.b))
        p, _q = actual.totales()
        return Medida(True, p + 20.0, 9999.0)

    resultado = cuadrar(reparto, objetivo, flujo, tolerancia=0.001)
    assert resultado.cuadrado
    assert len(vistos) >= 2
    # 015:RF-44: el factor de escala mueve P y Q juntas.
    assert all(a == b for a, b in vistos)


def test_pot_is_active_power_and_ea_eri_derive_q_and_fp_with_evidence():
    o = objetivo_de(_maxima())
    fija = fijas_de([_cliente('NIS-1', 'SED-1', 100.0, ea=400.0, eri=120.0)], o)['SED-1']
    assert fija.kw == 100.0
    assert fija.kvar == pytest.approx(30.0)
    assert fija.fp == pytest.approx(100.0 / math.hypot(100.0, 30.0))
    assert fija.derivaciones == [{
        'cliente': 'NIS-1', 'p_kw': 100.0, 'q_kvar': 30.0,
        'fp': pytest.approx(100.0 / math.hypot(100.0, 30.0)),
        'metodo': 'ERI/EA', 'ea': 400.0, 'eri': 120.0,
    }]


def test_fijas_con_su_demanda_y_las_demas_con_un_mismo_factor():
    """006:RF-5 / 006:RF-8 / 015:RF-43 / 015:RF-44 — fijas con sus clientes; las demás, por su
    potencia instalada y todas por el mismo factor (usuario, 2026-10-15). La demanda del
    archivo de las escaladas no cuenta: E3 trae 300 kW y tiene la mitad de kVA que E2."""
    o = objetivo_de(_maxima())
    fijas = fijas_de([_cliente('1', 'E1', 200.0, ea=1.0, eri=0.5)], o)
    r = reparto_inicial(o, fijas, {'E1': (50.0, 10.0), 'E2': (100.0, 20.0), 'E3': (300.0, 150.0)},
                        {'E1': 50.0, 'E2': 200.0, 'E3': 100.0})
    d = r.demandas
    assert (d['E1'].kw, d['E1'].origen) == (200.0, 'cliente')
    assert d['E2'].origen == d['E3'].origen == 'escala'
    assert d['E2'].kw == pytest.approx(800.0 * 200 / 300)
    assert d['E3'].kw == pytest.approx(800.0 * 100 / 300)
    assert r.base['E2'][0] == pytest.approx(200.0 * o.fp), 'P base = kVA × FP'
    assert d['E2'].kw / r.base['E2'][0] == pytest.approx(d['E3'].kw / r.base['E3'][0]) \
        == pytest.approx(r.a)
    assert sum(x.kw for x in d.values()) == pytest.approx(1000.0)
    assert not r.todo_escala and r.solo_kw


def test_reparto_sorteado_suma_el_objetivo():
    """006:RF-8 — con un número sorteado de SED, la suma sin pérdidas es el objetivo en kW."""
    rnd = random.Random(6)
    n = rnd.randint(5, 300)
    cargas = {f'S{i}': (rnd.uniform(5, 200), rnd.uniform(1, 60)) for i in range(n)}
    kva = {s: rnd.choice([10.0, 50.0, 100.0, 250.0]) for s in cargas}
    fijas_sed = rnd.sample(sorted(cargas), k=n // 10)
    total = sum(p for p, _ in cargas.values())
    o = objetivo_de(_maxima(kw=total * 1.6, kvar=total * 0.2))
    fijas = fijas_de([_cliente(str(i), s, 10.0, 1.0, 0.3) for i, s in enumerate(fijas_sed)], o)
    r = reparto_inicial(o, fijas, cargas, kva)
    assert len(r.demandas) == n
    assert sum(x.kw for x in r.demandas.values()) == pytest.approx(o.kw)


def test_sed_cliente_fuera_del_alimentador_se_omite():
    """006:RF-9 — la SED de un cliente que no está en el alimentador se lista y se sigue."""
    o = objetivo_de(_maxima())
    fijas = fijas_de([_cliente('1', 'ZZ', 100.0, 1.0, 0.1)], o)
    r = reparto_inicial(o, fijas, {'E1': (400.0, 100.0)}, {'E1': 100.0})
    assert [x['sed'] for x in r.omitidas] == ['ZZ'] and 'ZZ' not in r.demandas
    assert r.demandas['E1'].kw == pytest.approx(1000.0)


def test_sed_sin_demanda_queda_en_cero_y_se_avisa():
    """006:RF-24 / 015:RF-44 / 015:RF-45 — una SED escalada sin demanda en el archivo recibe la
    suya por su kVA (CA101: 98 de 160 estaban en cero); la que no tiene kVA conocido queda
    en cero y se dice."""
    o = objetivo_de(_maxima())
    r = reparto_inicial(o, {}, {'E1': (400.0, 100.0), 'E2': (0.0, 0.0), 'E3': (50.0, 5.0)},
                        {'E1': 100.0, 'E2': 100.0, 'E3': None})
    assert r.demandas['E2'].kw == pytest.approx(500.0) == r.demandas['E1'].kw
    assert r.demandas['E3'].kw == 0.0
    assert any('E3' in a and 'cero' in a and 'potencia instalada' in a for a in r.avisos)


def _escaladas(n, kva_total):
    """``n`` SED escaladas que suman ``kva_total`` kVA, sorteadas con la semilla del módulo."""
    rnd = random.Random(SEMILLA)
    pesos = [rnd.uniform(1.0, 5.0) for _ in range(n)]
    kva = {f'S{i}': kva_total * w / sum(pesos) for i, w in enumerate(pesos, 1)}
    return {s: (0.0, 0.0) for s in kva}, kva


def _flujo_con_perdidas(r):
    """Una red sintética: entra por la cabecera lo que consumen sus cargas más un 2 %."""
    p, q = r.totales()
    return Medida(True, kw=p * 1.02, kvar=q * 1.02, carga_kw=p, carga_kvar=q)


@pytest.mark.parametrize('fijas_kw', (5010.0, 5000.0, 7300.0))
def test_006_rf46_fijas_que_llenan_la_cabecera_no_escalan_y_es_imposible(fijas_kw):
    """006:RF-46 (cambia 006:RF-13; 086:RF-124) — cabecera 5 000 kW, escaladas 10 000 kVA y fijas que llenan o pasan la
    cabecera: las fijas siguen con su P y Q (escala 1), las escaladas al mínimo y el alimentador sale imposible con su
    causa, en un flujo. Antes se escalaban también las fijas: con 5 010 kW quedaban en 1 691 kW."""
    o = objetivo_de(_maxima(kw=5000.0, kvar=1000.0))
    cargas, kva = _escaladas(40, 10000.0)
    fijas = fijas_de([_cliente('1', 'F1', fijas_kw, ea=1.0, eri=0.3)], o)
    r = reparto_inicial(o, fijas, {'F1': (1.0, 0.1), **cargas}, kva)
    assert not r.todo_escala and r.fijas == {'F1': (fijas_kw, pytest.approx(0.3 * fijas_kw))}, r
    assert r.causa and r.causa['estado'] == CALIBRACION_IMPOSIBLE and r.a == 0.0, r.causa
    assert r.demandas['F1'].kw == fijas_kw and r.demandas['F1'].origen == 'cliente'
    res = cuadrar(r, o, _flujo_con_perdidas, tolerancia=0.01)
    assert not res.cuadrado and res.imposible and res.flujos == 1, (res.flujos, res.motivo)
    assert res.reparto.demandas['F1'].kw == fijas_kw and res.imposible['fijas_kw'] == fijas_kw
    assert res.imposible['dominante']['sed'] == 'F1' and res.motivo == res.imposible['texto']
    assert '(s)' not in res.motivo and 'RF-' not in res.motivo


def test_006_rf46_no_hay_salto_entre_fijas_justo_por_debajo_y_justo_por_encima():
    """006:RF-46 — con 4 990 kW de fijas las escaladas toman lo que falta; con 5 010 kW las fijas no bajan a 1 691 kW: en
    los dos lados las fijas quedan con su P."""
    o = objetivo_de(_maxima(kw=5000.0, kvar=1000.0))
    cargas, kva = _escaladas(40, 10000.0)
    for fijas_kw in (4990.0, 5010.0):
        fijas = fijas_de([_cliente('1', 'F1', fijas_kw, ea=1.0, eri=0.3)], o)
        r = reparto_inicial(o, fijas, {'F1': (1.0, 0.1), **cargas}, kva)
        assert r.demandas['F1'].kw == fijas_kw, (fijas_kw, r.demandas['F1'])
        assert sum(d.kw for s, d in r.demandas.items() if s != 'F1') == pytest.approx(max(0.0, 5000.0 - fijas_kw))


@pytest.mark.parametrize('kva', ({}, {'E1': 100.0, 'E2': None}))
def test_006_rf46_sin_escaladas_con_kva_no_se_calibra_y_las_fijas_no_cambian(kva):
    """006:RF-46 — todas las SED con clientes, o las escaladas sin kVA conocido: no se puede repartir. Sale no
    calibrable con su causa, sin flujos, y ningún factor se aplica a las fijas (antes escalaban hasta el objetivo)."""
    o = objetivo_de(_maxima(kw=1000.0, kvar=300.0))
    fijas = fijas_de([_cliente('1', 'E1', 100.0, 1.0, 0.3)], o)
    r = reparto_inicial(o, fijas, {'E1': (5.0, 1.0), 'E2': (40.0, 4.0)} if kva else {'E1': (5.0, 1.0)}, kva)
    assert not r.todo_escala and r.causa and r.causa['estado'] == NO_CALIBRABLE, r
    assert r.demandas['E1'].kw == 100.0 and r.fijas['E1'][0] == 100.0
    res = cuadrar(r, o, lambda _r: pytest.fail('un alimentador no calibrable no ejecuta flujos'))
    assert not res.cuadrado and res.flujos == 0 and res.no_calibrable == r.causa
    assert 'no se puede repartir' in res.motivo and '(s)' not in res.motivo


def test_006_rf46_sorteado_las_fijas_nunca_cambian():
    """006:RF-46 — con fijas y escaladas sorteadas, por encima o por debajo de la cabecera, ninguna fija cambia su P."""
    rnd = random.Random(SEMILLA)
    for _ in range(200):
        o = objetivo_de(_maxima(kw=rnd.uniform(500.0, 8000.0), kvar=rnd.uniform(-500.0, 2000.0)))
        cargas, kva = _escaladas(rnd.randint(1, 30), rnd.uniform(100.0, 20000.0))
        clientes = [_cliente(str(i), f'F{i}', rnd.uniform(10.0, 6000.0), 1.0, rnd.uniform(0.0, 0.6))
                    for i in range(rnd.randint(1, 4))]
        fijas = fijas_de(clientes, o)
        r = reparto_inicial(o, fijas, {**{f.sed: (1.0, 0.1) for f in fijas.values()}, **cargas}, kva)
        assert all(r.demandas[f.sed].kw == pytest.approx(f.kw) for f in fijas.values()), (SEMILLA, o, r.avisos)


def test_el_kvar_de_las_escaladas_sigue_su_propio_fp():
    """006:RF-14 / 015:RF-55 — se cuadra el kW; el factor de escala mueve P y Q juntas. Sin
    factor de potencia en el perfil, las escaladas llevan el de la máxima de cabecera."""
    o = objetivo_de(_maxima(kw=1000.0, kvar=100.0))
    fijas = fijas_de([_cliente('1', 'E1', 200.0, ea=1.0, eri=1.0)], o)
    r = reparto_inicial(o, fijas, {'E1': (1.0, 1.0), 'E2': (400.0, 120.0)}, {'E2': 500.0})
    assert r.solo_kw
    e2 = r.demandas['E2']
    assert e2.kvar / e2.kw == pytest.approx(100.0 / 1000.0)
    assert sum(x.kw for x in r.demandas.values()) == pytest.approx(1000.0)


class RedDeJuguete:
    """Flujo de carga de mentira: pérdidas cuadráticas, reactiva de los cables y un
    límite de carga por encima del cual «no converge». Cada remedio sube el límite."""

    def __init__(self, rp=2e-5, rq=4e-5, cables=0.0, limite=math.inf, por_remedio=0.0):
        self.rp, self.rq, self.cables = rp, rq, cables
        self.limite, self.por_remedio = limite, por_remedio
        self.escritos = []
        self.ajustes = []
        self.flujos_antes = []

    def flujo(self, reparto):
        p, q = reparto.totales()
        self.escritos.append((p, q))
        if p > self.limite:
            return Medida(False, motivo='Newton-Raphson no converge')
        s2 = p * p + q * q
        return Medida(True, p + self.rp * s2, q + self.rq * s2 - self.cables)

    def remedio(self, nombre, ajustes):
        self.ajustes.append(nombre)
        self.flujos_antes.append(len(self.escritos))
        self.limite += self.por_remedio
        return [f'{k} = {v}' for k, v in ajustes.items()]


def _caso(n=40, seed=7, kw=3000.0, kvar=900.0):
    rnd = random.Random(seed)
    # P y Q del archivo original de cada SED: la mitad de su kVA, con FP 0,96.
    kva = {f'S{i}': rnd.choice([50.0, 100.0, 160.0, 250.0]) for i in range(n)}
    cargas = {s: (k * 0.5, k * 0.14) for s, k in kva.items()}
    o = objetivo_de(_maxima(kw=kw, kvar=kvar))
    fijas = fijas_de([_cliente('1', 'S0', 150.0, 1.0, 0.4)], o)
    return o, fijas, reparto_inicial(o, fijas, cargas, kva)


def test_cuadra_con_las_perdidas_al_uno_por_ciento():
    """006:RF-11 / 006:RF-12 — se corrige con la cabecera de cada flujo hasta el 1 %."""
    o, _fijas, r = _caso()
    red = RedDeJuguete()
    res = cuadrar(r, o, red.flujo)
    assert res.cuadrado and res.flujos < 20
    e_kw, e_kvar = res.errores()
    assert abs(e_kw) <= 0.01
    assert abs(e_kvar) > 0.01, 'el kVAR nativo se informa, pero no decide el cuadre'
    p, q = res.perdidas()
    assert p > 0 and q > 0
    # Las SED fijas no se tocan; las escaladas suben todas por el mismo factor (015:RF-44).
    d = res.reparto.demandas
    assert d['S0'].kw == 150.0
    ratios = {round(x.kw / res.reparto.base[s][0], 9) for s, x in d.items() if x.origen == 'escala'}
    assert ratios == {round(res.reparto.a, 9)}


def test_no_acepta_cabecera_parcial_con_perdidas_activas_negativas():
    """006:RF-11 — coincidir en kW no basta si la cabecera omite otra troncal."""
    objetivo, _, reparto = _caso(kw=6000.0, kvar=900.0)
    reparto = reparto.con_factores(reparto.a * 2.1, reparto.b)

    res = cuadrar(
        reparto, objetivo,
        lambda _reparto: Medida(True, objetivo.kw, objetivo.kvar),
        max_flujos=2,
    )

    assert not res.cuadrado
    assert 'pérdidas activas negativas' in res.motivo
    assert res.perdidas()[0] < 0


def test_perdidas_usan_consumo_efectivo_nativo_si_esta_disponible():
    """006:RF-11 — el modelo de carga puede consumir menos que su entrada nominal."""
    objetivo, _, reparto = _caso(kw=6000.0, kvar=900.0)
    reparto = reparto.con_factores(reparto.a * 2.1, reparto.b)

    res = cuadrar(
        reparto, objetivo,
        lambda _reparto: Medida(
            True, objetivo.kw, objetivo.kvar,
            carga_kw=5500.0, carga_kvar=700.0,
        ),
        max_flujos=2,
    )

    assert res.cuadrado
    assert res.perdidas() == pytest.approx((500.0, 200.0))


@pytest.mark.parametrize('tol', [0.001, 0.05])
def test_tolerancia_elegida(tol):
    """006:RF-11 — la tolerancia es la que se pide."""
    o, _, r = _caso(seed=3)
    res = cuadrar(r, o, RedDeJuguete().flujo, tolerancia=tol)
    assert res.cuadrado and abs(res.errores()[0]) <= tol


def test_perdidas_reactivas_mayores_no_cambian_q_y_cuadran_kw():
    """015:RF-44 / 015:RF-55 — el FP de las escaladas (aquí el de la cabecera, sin perfil) se
    conserva al escalar y el resultado reactivo nativo no bloquea el kW."""
    o, _, r = _caso(kvar=100.0)
    # 3000 kW en la red dan unos 1800 kVAR de pérdidas: más que los 100 de la cabecera.
    res = cuadrar(r, o, RedDeJuguete(rq=2e-4).flujo)
    assert res.cuadrado and res.reparto.solo_kw
    assert all(abs(d.kvar / d.kw - o.tan_phi) < 1e-9 for s, d in res.reparto.demandas.items()
               if d.origen == 'escala' and d.kw)
    assert res.medida.kvar > o.kvar


def test_no_converge_se_acerca_en_pasos():
    """006:RF-16 / 006:RF-17 — primero medio camino desde el último que convergió."""
    o, _, r = _caso()
    red = RedDeJuguete(limite=2500.0)        # el reparto sin pérdidas ya pasa del límite
    res = cuadrar(r, o, red.flujo, remedio=red.remedio, max_flujos=60)
    assert res.remedios[0] == {'remedio': ESCALERA[0][0], 'cambios': []}
    # 083:RF-7: el primer flujo no converge y el segundo prueba las escaladas casi en cero.
    assert res.historial[1]['a'] == pytest.approx(res.historial[0]['a'] * 1e-3)
    # Solo después de MITADES flujos sin converger se toca el flujo de carga.
    fallidos = [i for i, h in enumerate(res.historial, 1) if not h['converge']]
    assert red.flujos_antes[0] >= fallidos[MITADES - 1]
    assert not res.cuadrado and res.reparto is not None
    assert res.reparto.totales()[0] <= 2500.0


def test_remedios_por_orden_hasta_que_converge():
    """006:RF-16 / 006:RF-17 — la escalera, por orden, y el informe dice qué cambió."""
    o, _, r = _caso()
    red = RedDeJuguete(limite=2000.0, por_remedio=600.0)
    res = cuadrar(r, o, red.flujo, remedio=red.remedio, max_flujos=60)
    assert res.cuadrado
    assert red.ajustes == [n for n, _ in ESCALERA[1:len(red.ajustes) + 1]]
    assert all(x['cambios'] for x in res.remedios[1:])


def test_sin_cuadrar_deja_el_ultimo_que_convergio():
    """006:RF-18 — agotados los remedios, la red queda con el último reparto que convergió."""
    o, _, r = _caso()
    red = RedDeJuguete(limite=1500.0)
    res = cuadrar(r, o, red.flujo, remedio=red.remedio, max_flujos=60)
    assert not res.cuadrado and 'sin cuadrar' in res.motivo
    assert red.ajustes == [n for n, _ in ESCALERA[1:]]
    assert red.escritos[-1] == pytest.approx(res.reparto.totales())
    assert res.medida.converge


def test_nunca_converge():
    """006:RF-18 — si no converge con nada, se dice y no hay reparto."""
    o, _, r = _caso()
    res = cuadrar(r, o, RedDeJuguete(limite=-1.0).flujo, max_flujos=60)
    assert not res.cuadrado and res.reparto is None and 'no converge' in res.motivo


def test_cancelar_deja_el_ultimo_que_convergio():
    """006:RF-22 — al cancelar, se termina el flujo en curso y queda el último bueno."""
    o, _, r = _caso()
    red = RedDeJuguete()
    vistos = []
    res = cuadrar(r, o, red.flujo, cancelado=lambda: len(vistos) >= 1,
                  progreso=lambda n, m, t: vistos.append(t))
    assert res.cancelado and res.flujos == 1 and res.reparto is not None


@pytest.mark.parametrize('con_q', [False, True])
def test_cancelar_durante_el_flujo_que_cuadra_conserva_su_reparto(con_q):
    """006:RF-22 — un flujo ya en objetivo no puede ocultar la cancelación recibida durante él."""
    objetivo, _, reparto = _caso()
    solicitud, escritos, remedios = [], [], []
    medida = Medida(True, objetivo.kw, objetivo.kvar)

    def flujo(actual):
        escritos.append(actual)
        solicitud.append(True)
        return medida

    resultado = cuadrar(reparto, objetivo, flujo, con_q=con_q, max_flujos=1,
                        cancelado=lambda: bool(solicitud),
                        remedio=lambda *args: remedios.append(args) or [])

    assert resultado.cancelado and not resultado.cuadrado
    assert resultado.flujos == len(escritos) == 1
    assert resultado.reparto is escritos[0] and resultado.medida is medida
    assert resultado.historial[-1]['kw'] == objetivo.kw
    assert 'cancelado' in resultado.motivo and remedios == resultado.remedios == []


def test_ningun_remedio_hace_las_cargas_dependientes_de_la_tension():
    """015:RF-42 — las cargas son PQ: la escalera de remedios no activa ``iopt_pq``."""
    assert all('iopt_pq' not in ajustes for _nombre, ajustes in ESCALERA)


def test_escaladas_con_el_fp_del_perfil_y_fijas_con_su_ea_eri():
    """015:RF-53 / 015:RF-54 — usuario, 2026-10-15: las fijas, el factor de potencia de su
    EA/ERI de la tabla cruzada; las escaladas, el del perfil (0,98) sobre su P del archivo,
    y las dos magnitudes escalan con el mismo factor."""
    o = objetivo_de(_maxima())
    fijas = fijas_de([_cliente('1', 'E1', 200.0, ea=1.0, eri=0.5)], o)
    r = reparto_inicial(o, fijas, {'E1': (50.0, 10.0), 'E2': (100.0, 60.0), 'E3': (300.0, 150.0)},
                        {'E1': 50.0, 'E2': 100.0, 'E3': 300.0}, fp=0.98)
    d = r.demandas
    assert d['E1'].kvar == pytest.approx(100.0), 'la fija conserva su EA/ERI (FP 0,894)'
    tan98 = math.tan(math.acos(0.98))
    for sed, kva in (('E2', 100.0), ('E3', 300.0)):
        assert r.base[sed] == pytest.approx((kva * 0.98, kva * 0.98 * tan98))
        assert d[sed].kw / math.hypot(d[sed].kw, d[sed].kvar) == pytest.approx(0.98)
    assert sum(x.kw for x in d.values()) == pytest.approx(1000.0)


def test_sin_fp_en_el_perfil_las_escaladas_con_el_de_la_cabecera():
    """015:RF-55 — sin factor de potencia en el perfil, el de la máxima de cabecera."""
    o = objetivo_de(_maxima(kw=1000.0, kvar=300.0))
    r = reparto_inicial(o, {}, {'E2': (100.0, 60.0)}, {'E2': 100.0}, fp=None)
    assert r.base['E2'] == pytest.approx((100.0 * o.fp, 100.0 * o.fp * 0.3))


def test_fp_del_perfil_no_cambia_una_demanda_puesta_a_mano():
    """015:RF-58 — una carga cambiada a mano entra como fija con su P y Q (014:RF-10) y el
    factor de las escaladas no la toca."""
    from convertersmartgrid.dominio.ajuste_cabecera import Fija

    o = objetivo_de(_maxima())
    manual = {'E1': Fija('E1', 120.0, 90.0)}
    r = reparto_inicial(o, manual, {'E1': (50.0, 10.0), 'E2': (100.0, 20.0)},
                        {'E1': 50.0, 'E2': 100.0}, fp=0.98)
    assert (r.demandas['E1'].kw, r.demandas['E1'].kvar) == (120.0, 90.0)


def test_fija_con_fp_bajo_se_compensa_al_minimo_del_perfil():
    """015:RF-62 / 015:RF-63 / 015:RF-64 — usuario, 2026-10-15: el cliente fijo cuyo EA/ERI
    da un factor menor que el mínimo del perfil (0,98) se escribe a 0,98, como compensado
    por su banco propio, y queda dicho; el que ya está por encima conserva el suyo."""
    o = objetivo_de(_maxima())
    fijas = fijas_de([_cliente('BAJO', 'E1', 100.0, ea=1.0, eri=2.1),      # FP 0,430
                      _cliente('ALTO', 'E2', 200.0, ea=1.0, eri=0.19)], o,  # FP 0,982
                     fp_minimo=0.98)
    bajo, alto = fijas['E1'], fijas['E2']
    assert bajo.fp == pytest.approx(0.98)
    (d,) = bajo.derivaciones
    assert d['compensado']['fp_ea_eri'] == pytest.approx(1 / math.hypot(1, 2.1))
    assert d['compensado']['q_ea_eri_kvar'] == pytest.approx(210.0)
    assert d['compensado']['q_escrita_kvar'] == pytest.approx(100.0 * math.tan(math.acos(0.98)))
    assert any('BAJO' in a and 'banco propio' in a for a in bajo.avisos)
    assert alto.kvar == pytest.approx(38.0) and 'compensado' not in alto.derivaciones[0]
    assert fijas_de([_cliente('BAJO', 'E1', 100.0, ea=1.0, eri=2.1)], o)['E1'].kvar \
        == pytest.approx(210.0), 'sin mínimo en el perfil, su EA/ERI'


# ---------------------------------------------------------------- spec 021: dos zonas
def _con_central(**kw):
    """La máxima de demanda de un alimentador con central, como la da la web (021:RF-34)."""
    base = {'alimentador': 'NA205', 'fecha': '2026-08-20 16:45:00', 'demanda_kw': 10753.0,
            'arriba_kw': 1131.0, 'arriba_kvar': 380.0, 'abajo_kw': 9622.0, 'abajo_kvar': 2100.0,
            'generacion_kw': 9605.0, 'generacion_kvar': -593.0, 'cabecera_kw': 1123.0,
            'cabecera_kvar': 4199.0, 'error': None}
    base.update(kw)
    return base


class RedDeDosZonas:
    """Flujo de carga de mentira con una central en serie: cada zona con sus pérdidas
    cuadráticas; la cabecera es lo de aguas arriba menos lo que la central exporta."""

    def __init__(self, generacion_kw=9605.0, limite=math.inf, por_remedio=0.0):
        self.g, self.limite, self.por_remedio = generacion_kw, limite, por_remedio
        self.flujos = []

    def flujo(self, arriba, abajo):
        pa, qa = arriba.totales()
        pb, qb = abajo.totales()
        self.flujos.append((arriba.a, abajo.a))
        if pa + pb > self.limite:
            return MedidaZonas(False, motivo='Newton-Raphson no converge')
        sa, sb = 3e-5 * (pa * pa + qa * qa), 2e-5 * (pb * pb + qb * qb)
        llegada = self.g - (pb + sb)
        return MedidaZonas(True, arriba_kw=pa + sa, arriba_kvar=qa, abajo_kw=pb + sb,
                           abajo_kvar=qb, cabecera_kw=pa + sa - llegada, cabecera_kvar=qa)

    def remedio(self, nombre, ajustes):
        self.limite += self.por_remedio
        return [nombre]


def _zonas(n=30, seed=11, sin_escaladas_arriba=False):
    rnd = random.Random(seed)
    o = objetivo_zonas_de(_con_central())
    kva = {f'S{i}': rnd.choice([50.0, 100.0, 160.0, 250.0, 630.0]) for i in range(n)}
    cargas = {s: (k * 0.5, k * 0.1) for s, k in kva.items()}
    corte = n // 5
    de_arriba = {s: cargas[s] for s in list(cargas)[:corte]}
    de_abajo = {s: cargas[s] for s in list(cargas)[corte:]}
    fijas_arriba = fijas_de([_cliente('1', 'S0', 200.0, 1.0, 0.3)], o.arriba)
    if sin_escaladas_arriba:
        de_arriba = {'S0': de_arriba['S0']}
    ra = reparto_inicial(o.arriba, fijas_arriba, de_arriba, kva)
    rb = reparto_inicial(o.abajo, {}, de_abajo, kva)
    return o, ra, rb


def test_objetivo_de_dos_zonas():
    """021:RF-33, 021:RF-40, 021:RF-41 — el objetivo con central: aguas arriba, aguas abajo y la
    generación del mismo registro, el de la máxima de demanda."""
    o = objetivo_zonas_de(_con_central())
    assert (o.arriba.kw, o.arriba.kvar) == (1131.0, 380.0)
    assert (o.abajo.kw, o.abajo.kvar) == (9622.0, 2100.0)
    assert (o.generacion_kw, o.generacion_kvar) == (9605.0, -593.0)
    assert o.fecha == '2026-08-20 16:45:00' and o.alimentador == 'NA205'
    with pytest.raises(AjusteError, match='balance'):
        objetivo_zonas_de(_con_central(error='el balance de la barra de la central no cuadra'))


def test_cuadra_las_dos_zonas_con_un_factor_cada_una():
    """021:RF-40, 021:RF-41, 021:RF-42, 021:RF-43 — cada zona sube con su propio factor hasta su
    medida; las fijas no se tocan; cuadrado solo con las dos dentro de la tolerancia."""
    o, ra, rb = _zonas()
    red = RedDeDosZonas()
    res = cuadrar_zonas(ra, rb, o, red.flujo, tolerancia=0.01)
    assert res.cuadrado, res.motivo
    assert abs(res.medida.arriba_kw - o.arriba.kw) <= 0.01 * o.arriba.kw
    assert abs(res.medida.abajo_kw - o.abajo.kw) <= 0.01 * o.abajo.kw
    assert res.arriba.a != pytest.approx(res.abajo.a), 'un factor por zona'
    assert res.arriba.demandas['S0'].kw == 200.0
    d = res.resumen()
    assert d['cabecera_calculada_kw'] == pytest.approx(res.medida.cabecera_kw)
    assert d['cabecera_medida_kw'] == 1123.0
    assert d['factor_arriba'] == res.arriba.a and d['factor_abajo'] == res.abajo.a


def test_una_zona_sin_escaladas_se_avisa_y_no_decide():
    """021:RF-45 — aguas arriba solo con un cliente fijo: sus fijas quedan como están, se
    avisa y el cuadre lo decide la otra zona."""
    o, ra, rb = _zonas(sin_escaladas_arriba=True)
    res = cuadrar_zonas(ra, rb, o, RedDeDosZonas().flujo, tolerancia=0.01)
    assert res.cuadrado
    assert any('aguas arriba' in a and 'no se puede ajustar' in a for a in res.avisos)
    assert res.arriba.demandas['S0'].kw == 200.0
    assert abs(res.medida.abajo_kw - o.abajo.kw) <= 0.01 * o.abajo.kw


def test_dos_zonas_sin_converger_usa_los_remedios():
    """021:RF-43 — si el flujo no converge se acerca a medio camino y luego aplica los
    remedios del flujo de carga, como el ajuste de una zona (006:RF-15, RF-16)."""
    o, ra, rb = _zonas()
    red = RedDeDosZonas(limite=9000.0, por_remedio=3000.0)
    res = cuadrar_zonas(ra, rb, o, red.flujo, tolerancia=0.01, remedio=red.remedio)
    assert res.cuadrado, res.motivo
    assert [r['remedio'] for r in res.remedios][0] == ESCALERA[0][0]
    assert len(res.remedios) >= 2


def test_sin_central_el_ajuste_es_el_de_siempre():
    """021:RF-46 — sin central, ``cuadrar`` con un solo objetivo de cabecera, sin zonas."""
    o, _fijas, r = _caso()
    res = cuadrar(r, o, RedDeJuguete().flujo)
    assert res.cuadrado and not hasattr(res, 'arriba')


# --------------------------------------------------------------- 021:RF-54 a RF-58
class RedDeVariosAlimentadores:
    """Flujo de mentira de un proyecto: cada alimentador con sus pérdidas cuadráticas y un
    acople por la tensión de la barra de la SET (lo que consume uno sube las pérdidas de
    los demás), para que cuadrar uno y después otro descuadre al primero."""

    def __init__(self, acople=2e-6, limite=math.inf, por_remedio=0.0):
        self.acople, self.limite, self.por_remedio = acople, limite, por_remedio
        self.flujos = 0

    def medir(self, reps):
        self.flujos += 1
        p = {k: r.totales()[0] for k, r in reps.items()}
        total = sum(p.values())
        if total > self.limite:
            return MedidaConjunta(False, motivo='Newton-Raphson no converge')
        kw = {k: x + 2e-5 * x * x + self.acople * x * total for k, x in p.items()}
        return MedidaConjunta(True, kw=kw, kvar={k: r.totales()[1] for k, r in reps.items()},
                              carga_kw=p)

    def remedio(self, nombre, ajustes):
        self.limite += self.por_remedio
        return [nombre]


def _proyecto(n_alim, seed=5):
    rnd = random.Random(seed)
    repartos, objetivos = {}, {}
    for i in range(n_alim):
        kva = {f'A{i}_S{j}': rnd.choice([50.0, 100.0, 250.0, 630.0]) for j in range(rnd.randint(5, 40))}
        o = objetivo_de(_maxima(alimentador=f'A{i}', medidor=f'M{i}',
                                kw=rnd.uniform(800.0, 6000.0), kvar=rnd.uniform(100.0, 900.0)))
        repartos[f'A{i}'] = reparto_inicial(o, {}, {s: (k * 0.5, k * 0.1) for s, k in kva.items()}, kva)
        objetivos[f'A{i}'] = o
    return repartos, objetivos


@pytest.mark.parametrize('n_alim', [2, 3, 7])
def test_cuadre_conjunto_todos_en_el_mismo_flujo(n_alim):
    """021:RF-54, 021:RF-55 — un factor por alimentador, todos en los mismos flujos; cuadra
    solo cuando todos cumplen en el mismo flujo, con el acople entre ellos."""
    repartos, objetivos = _proyecto(n_alim, seed=n_alim)
    red = RedDeVariosAlimentadores()
    res = cuadrar_conjunto(repartos, objetivos, red.medir, tolerancia=0.001)
    assert res.cuadrado, res.motivo
    assert red.flujos == res.flujos <= 10
    m = red.medir(res.repartos)
    for k, o in objetivos.items():
        assert abs(m.kw[k] - o.kw) / o.kw <= 0.001
        assert res.desvio(k) == pytest.approx((res.medida.kw[k] - o.kw) / o.kw)
    assert set(res.historial[0]['a']) == set(objetivos)


def test_cuadre_conjunto_no_converge_remedios_una_vez():
    """021:RF-56 — sin converger, medio camino y los remedios, una vez para el proyecto; la
    red queda con el último reparto común que convergió."""
    repartos, objetivos = _proyecto(2)
    total = sum(o.kw for o in objetivos.values())
    red = RedDeVariosAlimentadores(limite=total * 0.9, por_remedio=total)
    res = cuadrar_conjunto(repartos, objetivos, red.medir, tolerancia=0.001, remedio=red.remedio)
    assert res.cuadrado, res.motivo
    assert [r['remedio'] for r in res.remedios] == [ESCALERA[0][0], ESCALERA[1][0]]
    red = RedDeVariosAlimentadores(limite=total * 0.5)
    vistos = []
    res = cuadrar_conjunto(repartos, objetivos, lambda r: (vistos.append(r), red.medir(r))[1],
                           tolerancia=0.001)
    assert not res.cuadrado and res.repartos is not None
    assert vistos[-1] == res.repartos, 'queda con el último reparto común que convergió'


def test_cuadre_conjunto_cancelado_y_quietas():
    """021:RF-58, 021:RF-45 — cancelar termina sin otro flujo; una clave quieta se escribe
    pero no se ajusta ni decide; sin ninguna ajustable, error."""
    repartos, objetivos = _proyecto(2)
    llamadas = []
    res = cuadrar_conjunto(repartos, objetivos, lambda r: llamadas.append(r) or
                           RedDeVariosAlimentadores().medir(r), cancelado=lambda: len(llamadas) >= 2)
    assert res.cancelado and len(llamadas) == 2
    res = cuadrar_conjunto(repartos, objetivos, RedDeVariosAlimentadores().medir,
                           quietas={'A1'}, tolerancia=0.001)
    assert res.cuadrado and res.ajustables == ('A0',)
    assert res.repartos['A1'].a == repartos['A1'].a
    with pytest.raises(AjusteError):
        cuadrar_conjunto(repartos, objetivos, RedDeVariosAlimentadores().medir, quietas={'A0', 'A1'})


@pytest.mark.parametrize('con_q', [False, True])
def test_cancelar_durante_flujo_conjunto_que_cuadra_conserva_todos(con_q):
    """021:RF-58 — todos cumplen, pero cancelar durante el flujo conserva el reparto sin seguir."""
    repartos, objetivos = _proyecto(2)
    solicitud, escritos, remedios = [], [], []
    medida = MedidaConjunta(True, kw={k: o.kw for k, o in objetivos.items()},
                           kvar={k: o.kvar for k, o in objetivos.items()})

    def flujo(actual):
        escritos.append(dict(actual))
        solicitud.append(True)
        return medida

    resultado = cuadrar_conjunto(repartos, objetivos, flujo, max_flujos=1,
                                con_q=tuple(objetivos) if con_q else (),
                                cancelado=lambda: bool(solicitud),
                                remedio=lambda *args: remedios.append(args) or [])

    assert resultado.cancelado and not resultado.cuadrado
    assert resultado.flujos == len(escritos) == 1
    assert all(resultado.repartos[k] is escritos[0][k] for k in repartos)
    assert resultado.medida is medida and resultado.historial[-1]['kw'] == medida.kw
    assert 'cancelado' in resultado.motivo and remedios == resultado.remedios == []


def test_cuadre_conjunto_perdidas_negativas():
    """021:RF-55 — como en un alimentador solo: cuadrado con pérdidas negativas no vale."""
    repartos, objetivos = _proyecto(2)

    def medir(reps):
        m = RedDeVariosAlimentadores(acople=0).medir(reps)
        return MedidaConjunta(True, kw=m.kw, kvar=m.kvar,
                              carga_kw={k: v * 1.5 for k, v in m.kw.items()})

    res = cuadrar_conjunto(repartos, objetivos, medir, tolerancia=0.001)
    assert not res.cuadrado and 'pérdidas activas negativas' in res.motivo


def test_bancos_que_faltan_y_donde():
    """021:RF-64, 021:RF-65, 021:RF-66 — el déficit entre el tamaño, redondeado; sin
    déficit, sin medida o sin tamaño, ninguno; los n bancos a 2k/(2n+1) del largo; el
    tamaño de la tensión más cercana del perfil, si está a menos del 10 %."""
    from convertersmartgrid.dominio.ajuste_cabecera import bancos_que_faltan, distancias_de_bancos, tamano_de_banco

    assert bancos_que_faltan(2645.0, 1560.0, 450.0) == 2
    assert bancos_que_faltan(3117.0, 3120.0, 450.0) == 0
    assert bancos_que_faltan(None, 1560.0, 450.0) == bancos_que_faltan(2645.0, 1560.0, None) == 0
    assert distancias_de_bancos(9000.0, 1) == [6000.0]
    assert distancias_de_bancos(5000.0, 2) == [2000.0, 4000.0]
    tamanos = {10.0: 300.0, 22.9: 450.0}
    assert tamano_de_banco(tamanos, 22.9) == 450.0 and tamano_de_banco(tamanos, 10.0) == 300.0
    assert tamano_de_banco(tamanos, 60.0) is None and tamano_de_banco(None, 22.9) is None


def test_tamano_de_banco_en_el_perfil():
    """021:RF-65 — ``calibracion.bancos_kvar_por_tension`` del perfil; sin él, None."""
    from convertersmartgrid.dominio.perfil_empresa import PerfilError, bancos_kvar_por_tension

    assert bancos_kvar_por_tension({'calibracion': {'bancos_kvar_por_tension': {'10': 300, '22.9': 450}}}) == {
        10.0: 300.0, 22.9: 450.0}
    assert bancos_kvar_por_tension({}) is None
    with pytest.raises(PerfilError):
        bancos_kvar_por_tension({'calibracion': {'bancos_kvar_por_tension': {'22.9': 0}}})


def _casi_cero_ejemplo(fijas_kw):
    """Un alimentador como el alimentador del ejemplo (2026-11-06): 69 escaladas con 10 675 kVA y cabecera de 6 272 kW."""
    o = objetivo_de(_maxima(alimentador='el alimentador del ejemplo', kw=6272.0, kvar=1200.0))
    cargas, kva = _escaladas(69, 10675.0)
    fijas = fijas_de([_cliente('1', 'F1', fijas_kw, 1.0, 0.3)], o)
    return o, reparto_inicial(o, fijas, {'F1': (1.0, 0.1), **cargas}, kva)


def test_015_rf71_escaladas_casi_en_cero_se_avisan_con_sus_sed_y_su_causa():
    """015:RF-71 — con las fijas del máximo de cada mes (6 174 kW) el factor queda en 0,0094 y varias escaladas bajo
    1 kW: se cuentan, se nombran por alimentador con la causa (las fijas casi igualan la cabecera) y el reparto no es
    válido. Con las fijas coincidentes (5 124 kW) ninguna escalada queda casi en cero y no hay aviso."""
    assert getattr(ac, 'ESCALADA_CASI_CERO_KW', None) == 1.0, 'sin umbral de 1 kW con nombre'
    o, r = _casi_cero_ejemplo(6174.0)
    casi = ac.escaladas_casi_cero_del_reparto(r, o)
    assert r.a == pytest.approx(98.0 / (10675.0 * o.fp)) and casi is not None
    bajo = sorted(s for s, d in r.demandas.items() if d.origen == 'escala' and d.kw < 1.0)
    assert bajo and casi['cantidad'] == len(bajo) and sorted(casi['sed']) == bajo
    assert casi['factor_anormal'] and casi['invalida'] and casi['fijas_kw'] == 6174.0
    for parte in ('el alimentador del ejemplo', 'por debajo de 1 kW', 'fijas suman 6,174.0 kW', '6,272.0 kW', bajo[0]):
        assert parte in casi['aviso'], (parte, casi['aviso'])
    assert '(s)' not in casi['aviso'] and 'RF-' not in casi['aviso']
    o, r = _casi_cero_ejemplo(5124.0)
    assert ac.escaladas_casi_cero_del_reparto(r, o) is None, r.a


def test_015_rf71_una_sed_pequena_bajo_1_kw_con_factor_normal_se_avisa_sin_invalidar():
    """015:RF-71 — una SED de 2 kVA con el factor común normal queda bajo 1 kW: se nombra, pero el factor no es anormal y
    el reparto sigue siendo válido."""
    assert hasattr(ac, 'escaladas_casi_cero_del_reparto'), 'sin recuento de escaladas casi en cero'
    o = objetivo_de(_maxima(alimentador='A1', kw=1000.0, kvar=200.0))
    r = reparto_inicial(o, {}, {'S1': (0.0, 0.0), 'S2': (0.0, 0.0)}, {'S1': 2.0, 'S2': 4000.0})
    casi = ac.escaladas_casi_cero_del_reparto(r, o)
    assert casi and casi['sed'] == ['S1'] and not casi['factor_anormal'] and not casi['invalida'], casi


def test_088_rf13_fija_sin_ea_eri_no_hereda_la_q_negativa_de_una_cabecera_capacitiva():
    """088:RF-13 — cabecera de 5 000 kW y −500 kvar: una fija de 300 kW sin EA/ERI no queda capacitiva (antes −30 kvar);
    toma el FP de las fijas del perfil o, sin él, el de la cabecera como inductivo, y se avisa."""
    o = objetivo_de(_maxima(kw=5000.0, kvar=-500.0))
    sin_perfil = fijas_de([_cliente('7', 'E1', 300.0)], o)['E1']
    assert sin_perfil.kvar == pytest.approx(30.0) and any('inductivo' in a for a in sin_perfil.avisos), sin_perfil
    con_perfil = fijas_de([_cliente('7', 'E1', 300.0)], o, fp_minimo=0.98)['E1']
    assert con_perfil.kvar == pytest.approx(300.0 * math.tan(math.acos(0.98)))
    inductiva = objetivo_de(_maxima(kw=5000.0, kvar=500.0))
    assert fijas_de([_cliente('7', 'E1', 300.0)], inductiva)['E1'].kvar == pytest.approx(30.0)


@pytest.mark.parametrize('fp, columna, signo', ((-0.8, None, -1), (0.8, 'PF lead mean', -1), (0.8, 'PF lag mean', 1),
                                                (0.8, None, 1)))
def test_088_rf14_maxima_sin_kvar_respeta_el_signo_de_su_fp(fp, columna, signo):
    """088:RF-14 (088:RF-2, RF-3) — una máxima sin kVAR saca la Q de su FP con el signo que da su medida (FP negativo) o su
    FP declarado (`lead` capacitivo, `lag` inductivo); antes siempre salía positiva."""
    o = objetivo_de(_maxima(kvar=None, fp=fp, columnas={'fp': columna} if columna else {}))
    assert o.kvar == pytest.approx(signo * 750.0)


# =========================================================================== MEJ10-FIJAS (orden del 20-11)
def _funcion(nombre):
    """La función del dominio, o una aserción que dice que falta (rojo por aserción sobre el árbol de antes)."""
    f = getattr(ac, nombre, None)
    assert f is not None, f'falta ajuste_cabecera.{nombre}'
    return f


def _fija(sed, codigo, kw, kvar=0.0, ea=None):
    f = ac.Fija(sed, kw, kvar, clientes=[codigo])
    f.derivaciones.append({'cliente': codigo, 'p_kw': kw, 'q_kvar': kvar, 'ea': ea})
    return f


def test_015_rf73_cliente_por_encima_de_su_cabecera_queda_a_revisar():
    """015:RF-73 (a), 006:RF-47 — un cliente que mide más que su cabecera en un registro del mes es imposible: la fija
    queda FIJA_A_REVISAR con su evidencia antes de ningún flujo. Hoy se acepta y se reparte."""
    from datetime import datetime as dt

    supera = _funcion('cliente_supera_cabecera')
    plaus = _funcion('plausibilidad_fijas')
    t0, t1, t2 = dt(2026, 10, 15, 15, 0), dt(2026, 10, 15, 15, 15), dt(2026, 10, 15, 15, 30)
    cabecera = [(t0, 2000.0, 500.0), (t1, 1700.0, 450.0), (t2, 0.0, 0.0)]
    cliente = [(t0, 1500.0, 300.0), (t1, 1806.5, 320.0), (t2, 900.0, 100.0)]
    evid = supera(cliente, cabecera)
    assert evid == {'registros': 1, 'exceso_max_kw': pytest.approx(106.5), 'fecha': '2026-10-15 15:15:00'}, \
        'con la cabecera en 0 no se compara'
    objetivo = ac.Objetivo(2503.0, 800.0, 'M1', 'A1', '2026-10-15 15:15:00')
    r = plaus(objetivo, {'S1': _fija('S1', '900001', 1806.5, 960.0)}, p_base_escaladas=6000.0,
              evidencia={'900001': {'supera_cabecera': evid}}, horas_mes=744.0)
    assert r['estado'] == 'FIJA_A_REVISAR' and r['a_revisar'] == ['S1']
    assert r['fijas'][0]['motivos'][0]['codigo'] == 'SUPERA_LA_CABECERA'
    # 039:RF-25: ya no para; la fija imposible se libera y el alimentador se calibra con el resto.
    assert 'S1' in r['texto'] and 'se reparte con las escaladas' in r['texto'] and r['liberadas'] == ['S1']


def test_015_rf73_fijas_que_dejan_casi_nada_a_las_escaladas_quedan_a_revisar():
    """015:RF-73 (c) — Σfijas/cabecera > 0,9 con un factor inicial < 0,05: la fija que más pesa, a revisar; con el
    factor normal o con las fijas por debajo del 90 %, nada."""
    plaus = _funcion('plausibilidad_fijas')
    objetivo = ac.Objetivo(2503.0, 800.0, 'M1', 'A1', '2026-10-15 15:15:00')
    fijas = {'S1': _fija('S1', '900001', 1806.5), 'S2': _fija('S2', '900002', 518.0)}
    r = plaus(objetivo, fijas, p_base_escaladas=6741.0 * 0.98)
    assert r['estado'] == 'FIJA_A_REVISAR' and r['a_revisar'] == ['S1'], r
    assert r['factor_inicial'] == pytest.approx((2503.0 - 2324.5) / (6741.0 * 0.98))
    assert r['fijas'][0]['motivos'][0]['codigo'] == 'FIJAS_DEJAN_SIN_ESCALADAS'
    sanas = {'S1': _fija('S1', '900001', 542.0), 'S2': _fija('S2', '900002', 518.0)}
    assert plaus(objetivo, sanas, p_base_escaladas=6741.0 * 0.98)['estado'] is None
    assert plaus(objetivo, fijas, p_base_escaladas=1000.0)['estado'] is None, 'factor inicial normal'
    # Las fijas del operador cuentan en la suma, pero no se ponen en duda: si pesan más que la fija del cliente, nada.
    op = plaus(objetivo, {'S2': fijas['S2']}, p_base_escaladas=6741.0 * 0.98, otras_fijas_kw=1806.5)
    assert op['fraccion_fijas'] == pytest.approx(2324.5 / 2503.0) and op['estado'] is None


def test_015_rf73_kva_de_la_fuente_incoherente_se_anota_sin_parar():
    """015:RF-73 (b), 020:RF-64 — si la media del mes no cabe en los kVA del grupo, el dudoso es el kVA: se anota y no
    para; si la media cabe y la fija pide más de cuatro veces el grupo, la fija queda a revisar."""
    plaus = _funcion('plausibilidad_fijas')
    horas = _funcion('horas_del_mes')
    objetivo = ac.Objetivo(4452.0, 900.0, 'M1', 'A1', '2026-10-15 15:15:00')
    kva = {'S1': 125.0, 'S2': 100.0}
    fijas = {'S1': _fija('S1', '900001', 366.7, 0.0, ea=204.0 * 744),
             'S2': _fija('S2', '900002', 450.0, 0.0, ea=50.0 * 744)}
    assert horas('2026-10-15') == 744.0 and horas('2026-02') == 672.0 and horas('') is None
    r = plaus(objetivo, fijas, p_base_escaladas=20000.0, kva_grupo=kva, horas_mes=744.0)
    s1, s2 = r['fijas']
    assert s1['kva_fuente_incoherente']['p_media_kw'] == pytest.approx(204.0) and not s1['a_revisar']
    assert r['kva_fuente_incoherente'] == ['S1']
    assert s2['a_revisar'] and s2['motivos'][0]['codigo'] == 'SUPERA_SU_GRUPO' and r['estado'] == 'FIJA_A_REVISAR'


def test_015_rf74_hermanas_de_una_fija_son_del_cliente_y_no_se_escalan():
    """015:RF-74 — SE1-2 y SE1-3 del mismo alimentador son de la instalación del cliente de SE1: su P y Q se reparten
    en el grupo por kVA y no se escalan. Hoy quedan ``origen='escala'`` con a·kVA·0,98."""
    objetivo = ac.Objetivo(1000.0, 200.0, 'M1', 'A1')
    fijas = fijas_de([_cliente('900001', 'SE1', 300.0, 1.0, 0.25)], objetivo)
    cargas = {s: (0.0, 0.0) for s in ('SE1', 'SE1-2', 'SE1-3', 'SE12', 'SE9')}
    kva = {'SE1': 100.0, 'SE1-2': 100.0, 'SE1-3': 800.0, 'SE12': 500.0, 'SE9': 500.0}
    r = reparto_inicial(objetivo, fijas, cargas, kva, fp=0.98)
    assert r.origen['SE1-2'] == 'cliente' and r.origen['SE1-3'] == 'cliente', r.origen
    assert r.origen['SE12'] == 'escala', '«SE12» no es «SE1-2»'
    d = r.demandas
    assert d['SE1'].kw == pytest.approx(30.0) and d['SE1-3'].kw == pytest.approx(240.0)
    assert sum(d[s].kw for s in ('SE1', 'SE1-2', 'SE1-3')) == pytest.approx(300.0)
    assert set(r.base) == {'SE12', 'SE9'} and r.a == pytest.approx(700.0 / (1000.0 * 0.98))
    assert getattr(r, 'grupos', None) == {'SE1': ['SE1-2', 'SE1-3']}


def test_015_rf74_una_hermana_con_energia_en_la_fuente_es_otro_cliente():
    """015:RF-74 — con la energía de la fuente, la hermana que consume es de otro cliente y sigue escalada."""
    objetivo = ac.Objetivo(1000.0, 200.0, 'M1', 'A1')
    fijas = fijas_de([_cliente('900001', 'SE1', 300.0, 1.0, 0.25)], objetivo)
    cargas = {s: (0.0, 0.0) for s in ('SE1', 'SE1-2', 'SE1-3', 'SE9')}
    kva = {'SE1': 100.0, 'SE1-2': 100.0, 'SE1-3': 800.0, 'SE9': 500.0}
    try:
        r = reparto_inicial(objetivo, fijas, cargas, kva, fp=0.98, kwh={'SE1-2': 0.0, 'SE1-3': 1200.0})
    except TypeError:
        r = None
    assert r is not None, '015:RF-74: reparto_inicial no recibe la energía de la fuente'
    assert r.origen['SE1-2'] == 'cliente' and r.origen['SE1-3'] == 'escala'


def test_015_rf75_kva_del_grupo_de_la_fuente():
    """015:RF-75 — los kVA de la SED y de sus hermanas «<sed>-n» en la fuente."""
    grupo = _funcion('kva_de_grupo')
    kva = {'SE1': 100.0, 'SE1-2': 100.0, 'SE1-3': 1130.0, 'SE12': 50.0}
    assert grupo('SE1', kva, kva) == pytest.approx(1330.0)
    assert grupo('SE12', kva, kva) == pytest.approx(50.0) and grupo('SE7', kva, kva) is None


def test_035_rf32_fija_sin_consumo_en_el_instante_es_su_registro():
    """035:RF-32 — con P = 0 y Q = 0 en el registro del instante, el método es REGISTRO_DEL_INSTANTE (no ERI/EA), con
    su Q del registro y el aviso «fija sin consumo en el instante» con la EA del mes."""
    d = ac.derivacion_cliente({'codigo': '900003', 'pot': 0.23, 'ea': 60.0, 'eri': 10.0, 'p_registro_kw': 0.0,
                               'q_registro_kvar': 0.0, 'fecha_registro': '15/10/2026 15:15'}, 0.3, 0.95)
    assert d['metodo'] == 'REGISTRO_DEL_INSTANTE', d
    assert d['p_kw'] == 0.0 and d['q_kvar'] == 0.0 and d.get('sin_consumo') is True
    assert 'sin consumo en el instante' in d.get('aviso', '') and '60' in d['aviso']
    q = ac.derivacion_cliente({'codigo': '900003', 'pot': 0.23, 'ea': 60.0, 'eri': 10.0, 'p_registro_kw': 0.0,
                               'q_registro_kvar': 1.5, 'fecha_registro': '15/10/2026 15:15'}, 0.3, 0.95)
    assert q['q_kvar'] == pytest.approx(1.5) and q['metodo'] == 'REGISTRO_DEL_INSTANTE'
