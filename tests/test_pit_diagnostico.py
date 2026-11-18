"""Spec 107 T7 — diagnóstico por año con N-1, año sin demanda y cancelación (107:RF-3, 107:RF-4)."""
from __future__ import annotations

import threading

import pytest

from datos_pit import perfil_a, perfil_b

from convertersmartgrid.dominio.pit.ambito import PitError, areas_del_perfil, reunir
from convertersmartgrid.adaptadores.pit.diagnostico import agregar_demanda, diagnosticar, limites_del_estudio
from convertersmartgrid.aplicacion.pit.red_area import desde_ambito

LIMITES_PERFIL = {'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100.0}


def _preparar(caso, limites=LIMITES_PERFIL):
    caso['perfil']['pit']['limites'] = dict(limites)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, caso['elementos']))
    return area, red, limites_del_estudio(None, caso['perfil'])


@pytest.mark.parametrize('seed', (6, 31))
def test_n_1_del_anillo_y_de_la_radial(seed):
    """107:RF-3 — en el anillo ninguna contingencia deja carga sin servir; sin la radial, sí, y se nombra."""
    caso = perfil_b(seed)
    area, red, limites = _preparar(caso)
    diag = diagnosticar(area, red, caso['proyeccion'], caso['anios'], limites)
    assert diag.anios and all(a.base.converge for a in diag.anios)
    for anio in diag.anios:
        por_caso = {c.fuera[0]: c for c in anio.contingencias}
        assert set(caso['pistas']['anillo']) <= set(por_caso)
        for lid in caso['pistas']['anillo']:
            assert por_caso[lid].converge and por_caso[lid].p_sin_servir_mw == 0, lid
        radial = por_caso[caso['pistas']['radial']]
        assert radial.p_sin_servir_mw > 0
        assert any(v['magnitud'] == 'sin_tension' for v in radial.violaciones)


@pytest.mark.parametrize('seed', (6, 31))
def test_anio_sin_demanda_se_nombra_y_no_se_extrapola(seed):
    """107:RF-3 — el año sin proyección queda nombrado, sin diagnóstico inventado, y el diagnóstico no es completo."""
    caso = perfil_b(seed)
    area, red, limites = _preparar(caso)
    diag = diagnosticar(area, red, caso['proyeccion'], caso['anios'], limites)
    sin = caso['pistas']['anio_sin_demanda']
    assert diag.sin_demanda == [sin] and sin not in [a.anio for a in diag.anios]
    assert any(str(sin) in a for a in diag.avisos) and not diag.completo


def test_faltantes_e_incompletos_no_se_dan_por_completos():
    """107:RF-4 — la línea sin parámetros y el compartido sin asignar quedan en el diagnóstico como no completos."""
    caso = perfil_b(9)
    area, red, limites = _preparar(caso)
    diag = diagnosticar(area, red, caso['proyeccion'], caso['anios'][:1], limites)
    assert caso['pistas']['sin_parametros'] in {f['id'] for f in diag.faltantes}
    assert caso['pistas']['compartida'] in diag.incompletos
    assert not diag.completo and diag.como_dict()['completo'] is False


def test_cancelacion_a_mitad_del_horizonte():
    """107:RF-3 — cancelar entre años detiene el trabajo y dice qué años quedan."""
    caso = perfil_a(13)
    area, red, limites = _preparar(caso)
    cancel = threading.Event()
    vistos = []

    def progreso(hechos, total, anio):
        vistos.append(anio)
        if hechos == 1:
            cancel.set()

    diag = diagnosticar(area, red, caso['proyeccion'], caso['anios'], limites, cancel=cancel, on_progress=progreso)
    assert diag.cancelado and [a.anio for a in diag.anios] == caso['anios'][:1] and vistos == caso['anios'][:1]
    assert any('cancelado' in a for a in diag.avisos) and not diag.completo


def test_violacion_de_cargabilidad_contra_el_limite_del_perfil():
    """107:RF-3 — con un límite bajo, la cargabilidad de los transformadores sale como violación con su límite."""
    caso = perfil_a(13)
    area, red, limites = _preparar(caso, {**LIMITES_PERFIL, 'cargabilidad_max_pct': 1.0})
    assert limites['cargabilidad_max_pct']['origen'] == 'perfil'
    diag = diagnosticar(area, red, caso['proyeccion'], caso['anios'][:1], limites)
    malas = [v for v in diag.anios[0].base.violaciones if v['magnitud'] == 'cargabilidad_pct']
    assert {v['elemento'] for v in malas} >= {f'T-{s}' for s in caso['pistas']['sets']}
    assert all(v['limite'] == 1.0 for v in malas)


def test_sin_limite_es_un_error_que_lo_nombra():
    """107:RF-11 — ningún límite por defecto: sin registro ni perfil, el error nombra el límite. Cambiada en la
    tarjeta PIT-TEN (107 T7): la tensión sale por barra de la norma y el límite que se exige aquí es la cargabilidad;
    el error sin ningún límite de tensión está en test_pit_tension_norma.py."""
    with pytest.raises(PitError, match='cargabilidad_max_pct'):
        limites_del_estudio(None, {'pit': {}})
    caso = perfil_a(13)
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, caso['elementos']))
    limites = limites_del_estudio(None, {'pit': {'limites': {'cargabilidad_max_pct': 100.0}}})
    assert 'tension_min_pu' not in limites
    with pytest.raises(PitError, match='tension_min_pu'):  # sin tensión por barra ni del perfil, no hay diagnóstico
        diagnosticar(area, red, caso['proyeccion'], caso['anios'][:1], limites)


def test_demanda_por_barra_de_set():
    """107:RF-3 — la demanda de cada SET es la suma de sus alimentadores, en MW, por año."""
    caso = perfil_a(21)
    area, red, _ = _preparar(caso)
    dem = agregar_demanda(area, red, caso['proyeccion'])
    anio = caso['anios'][0]
    s = caso['pistas']['sets'][0]
    esperado = sum(f['p_kw'] for f in caso['proyeccion']
                   if f['anio_calendario'] == anio and f['alimentador'] in area.set_alimentadores[s]) / 1000
    assert dem[anio][f'B-{s}-MT'][0] == pytest.approx(esperado)
