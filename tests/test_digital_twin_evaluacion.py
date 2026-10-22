"""Spec 024, T3: evaluación del episodio por caso y norma (sin DIgSILENT)."""
from __future__ import annotations

import pytest

from igea_dgs.digital_twin import evaluacion as ev
from igea_dgs.digital_twin.episode import Caso, Clase

#: Perfil de prueba con la forma del real: NTCSE en ``estudios``, transformadores al 80 %.
PERFIL = {
    'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100},
    'calibracion': {'transformadores_sed': {'umbral_carga_pct': 80, 'tablas': []}},
    'informes': {'norma': 'NTCSE'},
}
LIM = ev.limites_del_sistema(PERFIL, 'NTCSE')


def _flujo(v_min=0.97, linea=60.0, trafo=50.0, perdidas=25.0, saifi=None):
    conf = ({'ausente': 'spec 012 sin ejecutar'} if saifi is None
            else {'unidad': 'int/año', 'valores': {'SAIFI': saifi, 'SAIDI': saifi * 2}})
    return {
        'balance': {'unidad': 'kW', 'valores': {'cabecera': 1000.0}},
        'perdidas': {'unidad': 'kW', 'valores': {'total': perdidas}},
        'cargabilidad': {'unidad': '%', 'valores': {'lineas': {'L1': linea},
                                                    'transformadores': {'T1': trafo}}},
        'tensiones': {'unidad': 'p.u.', 'valores': {'B1': v_min, 'B2': 1.0}},
        'confiabilidad': conf,
    }


def _evaluar(caso, flujo=None, **kw):
    datos = {'convergio': True, 'revertido': False, 'reabierto': True, 'limites': LIM,
             'calibracion_cuadra': True, 'referencia': None}
    datos.update(kw)
    return ev.evaluar(caso, flujo or _flujo(), **datos)


def test_limites_del_perfil_por_norma():
    """024:RF-31 — los límites salen del perfil por la norma del sistema, no del código."""
    assert LIM == ev.Limites('NTCSE', 0.95, 1.05, 100, 80)
    perfil = dict(PERFIL, normas={'NTCSER': {'tension_min_pu': 0.92, 'tension_max_pu': 1.08}})
    rural = ev.limites_del_sistema(perfil, 'NTCSER')
    assert rural is not None
    assert (rural.tension_min_pu, rural.tension_max_pu) == (0.92, 1.08)
    assert rural.cargabilidad_max_pct == 100 and rural.transformador_max_pct == 80


def test_ntcser_sin_tolerancia_en_el_perfil_no_se_supone():
    """024:RF-31 — sin la tolerancia NTCSER en el perfil no hay límites: nada se inventa."""
    assert ev.limites_del_sistema(PERFIL, 'NTCSER') is None


@pytest.mark.parametrize('caso', list(Caso))
def test_revertido_o_sin_converger_es_rechazado(caso):
    """024:RF-4 — una acción revertida o que no converge es ``rejected``, con su causa."""
    r = _evaluar(caso, revertido=True)
    assert r.clase is Clase.REJECTED and any('revert' in b for b in r.bloqueos)
    r = _evaluar(caso, convergio=False)
    assert r.clase is Clase.REJECTED and any('converg' in b for b in r.bloqueos)


@pytest.mark.parametrize('caso', list(Caso))
def test_sin_reapertura_va_a_cuarentena(caso):
    """024:RF-4 — sin reabrir y releer no hay aceptación: cuarentena."""
    r = _evaluar(caso, reabierto=False)
    assert r.clase is Clase.QUARANTINE


def test_caso_base_con_violaciones_es_diagnostico():
    """024:RF-29 — el «Caso base» es la red como está: la subtensión y la sobrecarga son
    diagnóstico del estado real, no rechazo."""
    r = _evaluar(Caso.CASO_BASE, _flujo(v_min=0.8683, linea=130.0, trafo=95.0))
    assert r.clase is Clase.ACCEPTED
    assert any('B1' in d and '0.8683' in d for d in r.diagnostico)
    assert any('L1' in d for d in r.diagnostico) and any('T1' in d for d in r.diagnostico)


def test_sin_proyecto_con_violaciones_y_calibracion_que_cuadra():
    """024:RF-29 / 024:RF-30 — «Sin proyecto» calibrado se acepta; sus violaciones son
    diagnóstico, y un cambio manual no lo rechaza."""
    r = _evaluar(Caso.SIN_PROYECTO, _flujo(v_min=0.90), manual=True)
    assert r.clase is Clase.ACCEPTED
    assert r.diagnostico and any('manual' in d for d in r.diagnostico)


@pytest.mark.parametrize(('cuadra', 'clase'), [(False, Clase.REJECTED), (None, Clase.QUARANTINE)])
def test_sin_proyecto_sin_cuadre(cuadra, clase):
    """024:RF-30 — «Sin proyecto» que no cuadra con la medida no se acepta; sin medida para
    comprobarlo, cuarentena con la causa."""
    r = _evaluar(Caso.SIN_PROYECTO, calibracion_cuadra=cuadra)
    assert r.clase is clase and r.bloqueos


def test_con_proyecto_que_cumple_y_no_empeora():
    """024:RF-31 — «Con proyecto» que cumple la norma y no empeora pérdidas ni
    confiabilidad frente a «Sin proyecto» se acepta."""
    ref = _flujo(perdidas=30.0, saifi=3.0)
    r = _evaluar(Caso.CON_PROYECTO, _flujo(perdidas=25.0, saifi=2.5), referencia=ref)
    assert r.clase is Clase.ACCEPTED and not r.bloqueos


@pytest.mark.parametrize(('flujo', 'texto'), [
    (_flujo(v_min=0.8683), 'B1'),
    (_flujo(linea=101.0), 'L1'),
    (_flujo(trafo=81.0), 'T1'),
    (_flujo(perdidas=31.0), 'pérdidas'),
    (_flujo(saifi=3.5), 'SAIFI'),
])
def test_con_proyecto_con_violaciones(flujo, texto):
    """024:RF-5 / 024:RF-31 — en «Con proyecto», fuera de norma o peor que «Sin proyecto» en
    pérdidas o confiabilidad es ``converged_with_violations``, nunca aceptado."""
    ref = _flujo(perdidas=30.0, saifi=3.0)
    r = _evaluar(Caso.CON_PROYECTO, flujo, referencia=ref)
    assert r.clase is Clase.CONVERGED_WITH_VIOLATIONS
    assert any(texto in v for v in r.violaciones)


def test_con_proyecto_sin_referencia_o_sin_limites_va_a_cuarentena():
    """024:RF-31 — sin el «Sin proyecto» de referencia o sin los límites de su norma, el
    episodio de «Con proyecto» no se puede juzgar: cuarentena con la causa."""
    r = _evaluar(Caso.CON_PROYECTO, referencia=None)
    assert r.clase is Clase.QUARANTINE and any('Sin proyecto' in b for b in r.bloqueos)
    r = _evaluar(Caso.CON_PROYECTO, referencia=_flujo(), limites=None)
    assert r.clase is Clase.QUARANTINE and any('perfil' in b for b in r.bloqueos)


def test_con_proyecto_fuera_de_norma_sin_referencia_es_violacion():
    """024:RF-5 / 024:RF-31 — si ya incumple la norma, no hace falta «Sin proyecto» para
    saberlo: es violación, no cuarentena."""
    r = _evaluar(Caso.CON_PROYECTO, _flujo(v_min=0.8683), referencia=None)
    assert r.clase is Clase.CONVERGED_WITH_VIOLATIONS
    assert any('Sin proyecto' in d for d in r.diagnostico)


def test_barras_sin_tension_no_son_subtension():
    """024:RF-29 / 024:RF-31 — una isla sin fuente no es subtensión: en el «Caso base» queda
    como diagnóstico y en «Con proyecto» es violación, con su número de barras."""
    flujo = _flujo()
    flujo['tensiones']['sin_tension'] = ['ElmTerm:Red\\3092.ElmTerm', 'ElmTerm:Red\\3093.ElmTerm']
    base = _evaluar(Caso.CASO_BASE, flujo)
    assert base.clase is Clase.ACCEPTED and any('2 barra(s) sin tensión' in d for d in base.diagnostico)
    con = _evaluar(Caso.CON_PROYECTO, flujo, referencia=_flujo())
    assert con.clase is Clase.CONVERGED_WITH_VIOLATIONS
    assert any('3092.ElmTerm' in v for v in con.violaciones)


def test_confiabilidad_ausente_no_bloquea():
    """024:RF-28 / 024:RF-31 — sin índices de confiabilidad, el criterio no se evalúa y se
    anota; no bloquea."""
    r = _evaluar(Caso.CON_PROYECTO, _flujo(), referencia=_flujo())
    assert r.clase is Clase.ACCEPTED
    assert any('confiabilidad' in d for d in r.diagnostico)


def test_caso_dorado_in111_ta225_con_proyecto():
    """024:RF-26 — la subtensión de 0,8683 p.u. tras reabrir IN111–TA225 («Con proyecto»)
    no se oculta por converger."""
    r = _evaluar(Caso.CON_PROYECTO, _flujo(v_min=0.8683284313), referencia=_flujo())
    assert r.clase is Clase.CONVERGED_WITH_VIOLATIONS
