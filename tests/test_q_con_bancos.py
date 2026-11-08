"""Spec 035: la Q de cabecera se cuadra con las escaladas cuando la red tiene bancos."""
from __future__ import annotations

import math

import pytest

from convertersmartgrid.ajuste_cabecera import (
    Fija, Medida, MedidaConjunta, Objetivo, Q_CUADRADA, Q_INCOHERENTE_ALTA, Q_INCOHERENTE_BAJA, Q_SIN_BASE, cuadrar,
    cuadrar_conjunto, reparto_inicial)

TOL = 0.01


def _red(bancos_kvar: float, perdidas: float = 0.04):
    """Flujo de una red pasiva: cabecera = cargas + pérdidas − bancos (kvar)."""
    def flujo(rep):
        p, q = rep.totales()
        return Medida(True, kw=p * (1 + perdidas), kvar=q + 2.5 * perdidas * p - bancos_kvar,
                      carga_kw=p, carga_kvar=q)
    return flujo


def _reparto(objetivo, fp=0.98, fija_kvar=200.0):
    cargas = {f'S{i}': (0.0, 0.0) for i in range(1, 6)}
    kva = {'S1': 100, 'S2': 250, 'S3': 400, 'S4': 630, 'S5': 160}
    fijas = {'S1': Fija('S1', kw=300.0, kvar=fija_kvar)}
    return reparto_inicial(objetivo, fijas, cargas, kva, fp=fp)


def test_con_bancos_cuadra_p_y_q_moviendo_solo_las_escaladas():
    """035:RF-5, 035:RF-6, 035:RF-28 — con bancos y una medida coherente (alcanzable con las
    escaladas entre su FP mínimo del perfil y 1), la Q de cabecera llega a la medida en el mismo
    cuadre; las fijas conservan su P y su Q y las escaladas comparten un factor de P y otro de Q."""
    objetivo = Objetivo(kw=1200.0, kvar=150.0, medidor='M')
    res = cuadrar(_reparto(objetivo), objetivo, _red(bancos_kvar=900.0), tolerancia=TOL, con_q=True,
                  fp_minimo_escaladas=0.7)
    assert res.cuadrado and res.q_estado == Q_CUADRADA and res.reparto.fp_escaladas() >= 0.7 - 1e-9
    assert abs(res.medida.kw - objetivo.kw) <= TOL * objetivo.kw
    assert abs(res.medida.kvar - objetivo.kvar) <= TOL * abs(objetivo.kvar)
    rep = res.reparto
    assert not rep.solo_kw and not math.isclose(rep.a, rep.b)
    assert rep.demandas['S1'].kw == 300.0 and rep.demandas['S1'].kvar == 200.0
    # 035:RF-12: el FP que resultó de las escaladas, el mismo en todas.
    fps = {s: d.kw / math.hypot(d.kw, d.kvar) for s, d in rep.demandas.items() if s in rep.base}
    assert max(fps.values()) - min(fps.values()) < 1e-9
    assert rep.fp_escaladas() == pytest.approx(next(iter(fps.values())))


def test_sin_bancos_la_q_sigue_informada():
    """035:RF-10 — sin bancos, como 006:RF-12: solo P, la Q de las escaladas con el FP del perfil."""
    objetivo = Objetivo(kw=1200.0, kvar=150.0, medidor='M')
    res = cuadrar(_reparto(objetivo), objetivo, _red(bancos_kvar=0.0), tolerancia=TOL)
    assert res.cuadrado and res.q_estado is None and not res.con_q
    assert res.reparto.solo_kw and res.reparto.a == res.reparto.b
    assert res.reparto.fp_escaladas() == pytest.approx(0.98)


def test_medida_incoherente_por_encima_queda_la_q_real_con_el_fp_de_perfil():
    """035:RF-8, 035:RF-26, 035:RF-28, 035:RF-29, 035:RF-30 — si ni con las escaladas a FP 1 la cabecera
    baja a la medida (NA203: le haría falta reactiva negativa), la medida no es coherente: no se
    cuadra la Q, las escaladas vuelven a su FP de perfil (nunca reactiva negativa) y la Q es la
    del flujo; el cuadre guarda el flujo a FP 1 que lo demostró. Las fijas, intactas."""
    objetivo = Objetivo(kw=1200.0, kvar=50.0, medidor='M')
    res = cuadrar(_reparto(objetivo, fija_kvar=600.0), objetivo, _red(bancos_kvar=300.0),
                  tolerancia=TOL, con_q=True)
    assert res.cuadrado and res.q_estado == Q_INCOHERENTE_ALTA
    assert res.q_extremo['fp_escaladas'] == 1.0 and res.q_extremo['cabecera_kvar'] > objetivo.kvar
    assert res.reparto.fp_escaladas() == pytest.approx(0.98) and res.reparto.solo_kw
    assert res.medida.kvar == pytest.approx(_red(300.0)(res.reparto).kvar)
    assert all(d.kvar >= 0 for s, d in res.reparto.demandas.items() if s in res.reparto.base)
    assert res.reparto.demandas['S1'].kw == 300.0 and res.reparto.demandas['S1'].kvar == 600.0


def test_medida_incoherente_por_debajo_y_el_fp_minimo_del_perfil():
    """035:RF-28, 035:RF-29 — si la Q medida pide a las escaladas un FP más bajo que su mínimo
    (sin ``factor_potencia_minimo_escaladas``, el de perfil), tampoco es coherente y queda la Q
    real; con un mínimo de 0,85 la misma medida sí se alcanza y se cuadra, con su FP entre 0,85
    y el de perfil."""
    objetivo = Objetivo(kw=1200.0, kvar=700.0, medidor='M')
    res = cuadrar(_reparto(objetivo), objetivo, _red(bancos_kvar=0.0), tolerancia=TOL, con_q=True)
    assert res.cuadrado and res.q_estado == Q_INCOHERENTE_BAJA
    assert res.q_extremo['cabecera_kvar'] < objetivo.kvar
    assert res.reparto.fp_escaladas() == pytest.approx(0.98)
    res = cuadrar(_reparto(objetivo), objetivo, _red(bancos_kvar=0.0), tolerancia=TOL, con_q=True,
                  fp_minimo_escaladas=0.85)
    assert res.cuadrado and res.q_estado == Q_CUADRADA
    assert abs(res.medida.kvar - objetivo.kvar) <= TOL * objetivo.kvar
    assert 0.85 - 1e-9 <= res.reparto.fp_escaladas() < 0.98


def test_sin_base_de_q_no_se_puede_cuadrar():
    """035:RF-9 — escaladas a FP 1: no hay Q que mover; se acepta por kW y se dice."""
    objetivo = Objetivo(kw=1200.0, kvar=150.0, medidor='M')
    res = cuadrar(_reparto(objetivo, fp=1.0), objetivo, _red(bancos_kvar=900.0),
                  tolerancia=TOL, con_q=True)
    assert res.cuadrado and res.q_estado == Q_SIN_BASE


def test_por_proyecto_solo_el_alimentador_con_bancos_cuadra_su_q():
    """035:RF-5, 035:RF-10 — en el cuadre del proyecto, cada alimentador con bancos cuadra su
    Q en el mismo flujo; el que no tiene sigue solo con P."""
    objetivos = {'A': Objetivo(kw=1200.0, kvar=150.0, medidor='A'),
                 'B': Objetivo(kw=900.0, kvar=300.0, medidor='B')}
    repartos = {k: _reparto(o) for k, o in objetivos.items()}
    bancos = {'A': 900.0, 'B': 0.0}

    def flujo(reps):
        kw, kvar = {}, {}
        for k, r in reps.items():
            m = _red(bancos[k])(r)
            kw[k], kvar[k] = m.kw, m.kvar
        return MedidaConjunta(True, kw=kw, kvar=kvar)

    res = cuadrar_conjunto(repartos, objetivos, flujo, tolerancia=TOL, con_q=['A'],
                           fp_minimo_escaladas=0.7)
    assert res.cuadrado and res.q_estado == {'A': Q_CUADRADA}
    assert abs(res.medida.kvar['A'] - 150.0) <= TOL * 150.0
    assert res.repartos['B'].solo_kw and not res.repartos['A'].solo_kw


# ------------------------------------------------------------------ el guion de DIgSILENT
from apoyo import cargar_herramienta  # noqa: E402
from test_ajuste_cabecera_guion import _app, _banco, _carga, _plan  # noqa: E402


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_cabecera_pf_q', tools_en_path=True)


def test_con_un_banco_en_servicio_el_guion_cuadra_la_q_con_un_solo_scale0(guion):
    """035:RF-5, 035:RF-7, 035:RF-11, 035:RF-12 — con un banco en servicio en el alimentador, la
    cabecera da la P y la Q medidas; cada escalada lleva su Q base por b/a y el mismo scale0
    (= a); la validación nativa pasa con el FP que resultó y el informe lo dice."""
    app = _app()
    _banco(app, 'F1', 'Banco F1', 300.0)
    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=40.0), 'recalibracion': 1})
    assert rc == 0, informe
    assert informe['criterio_cuadre'] == 'KW_Y_KVAR' and informe['bancos_en_servicio'] == ['Banco F1']
    assert informe['tipo_ajuste'] == {'tipo': 'RECALIBRACION', 'numero': 1, 'cuadra': 'P_Y_Q'}
    q = informe['cuadre_q']
    assert q['estado'] == 'CUADRADA' and informe['status'] == 'OK'
    assert abs(informe['cabecera']['kvar'] - 40.0) <= 0.01 * 40.0
    assert q['fp_escaladas'] is not None and q['factor_q'] != pytest.approx(q['factor_p'])
    escaladas = [_carga(app, s['sed']) for s in informe['sed'] if s['origen'] == 'escala']
    assert {round(c.scale0, 9) for c in escaladas} == {round(q['factor_p'], 9)}
    for c in escaladas:
        if c.plini:
            fp = c.plini / math.hypot(c.plini, c.qlini)
            assert fp == pytest.approx(q['fp_escaladas'], abs=1e-6)
    assert informe['validacion_posterior_nativa']['correcta'], informe['validacion_posterior_nativa']


def test_sin_bancos_el_guion_solo_cuadra_kw(guion):
    """035:RF-10 — sin bancos, el criterio sigue siendo kW y la Q se informa (006:RF-14)."""
    informe, rc = guion.ejecutar(_app(), _plan(kw=300.0, kvar=40.0))
    assert rc == 0, informe
    assert informe['criterio_cuadre'] == 'KW_ONLY' and 'cuadre_q' not in informe
    assert informe['bancos_en_servicio'] == []


def test_la_q_que_ya_estaba_sin_cuadrar_se_vuelve_a_calibrar(guion):
    """035:RF-13, 035:RF-23 — calibrado antes solo por kW; con un banco nuevo en servicio, la relectura
    previa no lo da por bueno porque la Q no es la medida, y vuelve a cuadrar."""
    app = _app()
    informe, rc = guion.ejecutar(app, _plan(kw=300.0, kvar=40.0))
    assert rc == 0 and informe['criterio_cuadre'] == 'KW_ONLY'
    _banco(app, 'F1', 'Banco nuevo', 150.0)
    informe, rc = guion.ejecutar(app, {**_plan(kw=300.0, kvar=40.0), 'recalibracion': 1})
    assert rc == 0, informe
    previa = informe['validacion_previa_nativa']
    assert not previa['correcta'] and any(f['tipo'] == 'Q_CABECERA_SIN_CUADRAR' for f in previa['fallos'])
    assert informe['cuadre_q']['estado'] == 'CUADRADA'


def test_la_q_de_cabecera_a_mas_o_menos_uno_por_ciento():
    """035:RF-25 — la Q se da por cuadrada dentro de ±1 % de la medida, aparte del kW."""
    from convertersmartgrid.ajuste_cabecera import TOLERANCIA_Q, cuadrado_kvar

    objetivo = Objetivo(kw=1000.0, kvar=500.0, medidor='M')
    assert TOLERANCIA_Q == 0.01
    assert cuadrado_kvar(504.0, objetivo) and cuadrado_kvar(496.0, objetivo)
    assert not cuadrado_kvar(506.0, objetivo) and not cuadrado_kvar(494.0, objetivo)


def test_recalibrar_sin_bancos_cuadra_la_q_y_si_no_baja_se_recomienda_revisar(guion):
    """035:RF-24, 035:RF-27, 035:RF-28, 035:RF-31 — al recalibrar sin bancos la Q también se
    cuadra con las escaladas; si la medida no es coherente (ni a FP 1 baja), queda la Q real con
    el FP de perfil, se acepta por kW y el informe lo dice y recomienda revisar los bancos."""
    informe, rc = guion.ejecutar(_app(), {**_plan(kw=300.0, kvar=5.0), 'recalibracion': 1})
    assert rc == 0, informe
    assert informe['bancos_en_servicio'] == [] and informe['criterio_cuadre'] == 'KW_Y_KVAR'
    assert informe['cuadre_q']['estado'] == 'CUADRADA'
    # Con una Q medida por debajo de la que dan las fijas y las pérdidas, no hay margen.
    informe, rc = guion.ejecutar(_app(), {**_plan(kw=300.0, kvar=-60.0), 'recalibracion': 1})
    assert rc == 0, informe
    q = informe['cuadre_q']
    assert q['estado'] == 'MEDIDA_INCOHERENTE_ALTA' and not q['coherente']
    assert q['extremo']['fp_escaladas'] == 1.0 and q['fp_escaladas'] == pytest.approx(0.98, abs=1e-3)
    assert q['diferencia_kvar'] > 0 and any('no coherente' in a for a in informe['avisos'])
    rev = informe['revision_bancos']
    assert rev['motivo'] == 'MEDIDA_INCOHERENTE' and rev['diferencia_kvar'] > 0
    assert any('evaluador' in a and '035:RF-20' in a for a in informe['avisos'])


def test_con_bancos_que_no_alcanzan_tambien_se_recomienda(guion):
    """035:RF-20, 035:RF-31 — con bancos y la medida incoherente, la misma recomendación."""
    from types import SimpleNamespace

    med = SimpleNamespace(converge=True, kvar=3553.1)
    objetivo = Objetivo(kw=10436.0, kvar=2903.0, medidor='M')
    rev = guion.revision_de_bancos('SM218', med, objetivo, True, 'MEDIDA_INCOHERENTE_ALTA')
    assert rev['motivo'] == 'MEDIDA_INCOHERENTE' and rev['diferencia_kvar'] == pytest.approx(650.1)
    assert guion.revision_de_bancos('SM218', med, objetivo, True, 'CUADRADA') is None


def test_la_recalibracion_se_numera_desde_la_primera_calibracion(tmp_path):
    """035:RF-21 — la primera calibración es la 0 y cada una después, la recalibración n.º k; el
    espacio la publica sin la demanda por SED, y la web activa con ella la recalibración."""
    from pathlib import Path

    from convertersmartgrid.web import services
    from convertersmartgrid.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path / 'ws')
    informe = {'cuadrado': True, 'escenario': 'Sin proyecto', 'escenarios': [{'escenario': 'Sin proyecto'}],
               'sed': [{'sed': 'SE1', 'despues': {'kw': 10.0, 'kvar': 2.0}, 'derivaciones': []}]}
    services._guardar_calibracion(ws, 'P', 'A1', informe)
    assert ws.calibraciones['P']['A1']['recalibracion'] == 0
    services._guardar_calibracion(ws, 'P', 'A1', informe)
    assert ws.calibraciones['P']['A1']['recalibracion'] == 1
    assert 'recalibración n.º 1' in ws.calibraciones['P']['A1']['nombre']
    publico = ws.public()['calibraciones']
    assert publico == {'P': {'A1': {'recalibracion': 1, 'nombre': ws.calibraciones['P']['A1']['nombre'],
                                    'caso': None}}}
    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'features' / 'powerfactory'
    ajuste = (raiz / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    demanda = (raiz / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    assert 'numeroDeRecalibracion(ws.calibraciones, project' in ajuste and 'Recalibrar ${' in ajuste
    assert "const listo = calibrado &&" in demanda and 'Se activa con la primera calibración' in demanda


def test_la_primera_calibracion_solo_cuadra_la_p_aunque_haya_bancos(guion):
    """035:RF-22, 035:RF-10 — la primera calibración cuadra solo la P, con bancos o sin ellos; la
    recalibración, P y Q. El informe lo dice, y sin recalibrar no hay revisión de bancos."""
    app = _app()
    _banco(app, 'F1', 'Banco F1', 300.0)
    informe, rc = guion.ejecutar(app, _plan(kw=300.0, kvar=5.0))
    assert rc == 0, informe
    assert informe['tipo_ajuste'] == {'tipo': 'CALIBRACION', 'numero': 0, 'cuadra': 'P'}
    assert informe['criterio_cuadre'] == 'KW_ONLY' and 'cuadre_q' not in informe
    assert 'revision_bancos' not in informe


def test_la_web_dice_que_cuadra_cada_una(tmp_path):
    """035:RF-22 — el plan numera la recalibración por la calibración anterior de esos casos, y el
    paso 2.4 dice «solo P» o «P y Q»."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    servicios = (raiz / 'src' / 'convertersmartgrid' / 'web' / 'services.py').read_text(encoding='utf-8')
    assert "plan['recalibracion'] = 0 if not previa else int(previa.get('recalibracion') or 0) + 1" in servicios
    ajuste = (raiz / 'frontend' / 'src' / 'features' / 'powerfactory' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    assert 'Calibración: solo se cuadra la P (kW).' in ajuste
    assert 'se cuadran la P (kW) y la Q (kvar)' in ajuste and "'P (kW) y Q (kvar)' : 'solo la P (kW)'" in ajuste


@pytest.mark.parametrize('criterio', ['coincidente', 'maximo_mes'])
def test_el_informe_dice_el_criterio_de_las_fijas(guion, criterio):
    """039:RF-6 — el informe de la calibración dice el criterio de las fijas del plan."""
    informe, rc = guion.ejecutar(_app(), {**_plan(kw=300.0, kvar=5.0), 'criterio_fijas': criterio})
    assert rc == 0, informe
    assert informe['criterio_fijas'] == criterio


def test_el_informe_lista_los_clientes_a_su_maxima_y_la_cabecera_cuadra(guion):
    """039:RF-18, 039:RF-19 — el cliente a su máxima llega en ``clientes`` con el registro de su POT: su SED es una fija
    con esa P, las escaladas llenan el resto hasta la cabecera, y el informe lo lista con su registro, kW y kvar."""
    lista = [{'codigo': '11', 'nombre': 'Cliente', 'sed': 'F1_S2', 'p_kw': 40.0, 'q_kvar': 12.0,
              'fecha': '01/03/2026 09:00', 'metodo': 'ERI_DEL_REGISTRO 01/03/2026 09:00'}]
    plan = {**_plan(kw=300.0, kvar=90.0, clientes=[
        {'codigo': '11', 'sed': 'F1_S2', 'pot': 40.0, 'ea': 1.0, 'eri': 0.25, 'criterio': 'a_su_maxima',
         'fecha_registro': '01/03/2026 09:00', 'q_registro_kvar': 12.0, 'p_registro_kw': None}]),
        'fijas_a_su_maxima': lista}
    informe, rc = guion.ejecutar(_app(), plan)
    assert rc == 0, informe
    assert informe['fijas_a_su_maxima'] == lista
    fija = next(x for x in informe['sed'] if x['sed'] == 'F1_S2')
    assert fija['despues']['kw'] == pytest.approx(40.0) and fija['despues']['kvar'] == pytest.approx(12.0)
    assert informe['cuadrado'] and abs(informe['desvio']['kw']) <= 0.01
