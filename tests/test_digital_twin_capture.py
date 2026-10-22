"""Spec 024, T4: ensamblaje del episodio desde el contexto firmado, el resultado nativo y la
lectura tras reabrir (sin DIgSILENT)."""
from __future__ import annotations

import copy

import pytest

from igea_dgs.digital_twin import capture as cp
from igea_dgs.digital_twin.episode import Caso, Clase
from igea_dgs.digital_twin.evaluacion import Limites
from igea_dgs.native_action import build_native_action_context

H = 'f' * 64
LIM = Limites('NTCSE', 0.95, 1.05, 100, 80)


def _plan(action='obras_ejecutar', feeders=('TA225', 'IN111')):
    binding = {'project': 'P_IN111', 'source_run_id': 'run-7', 'source_mode': 'vnr',
               'source_fingerprint': H}
    return {'project': 'P_IN111', 'feeders': list(feeders),
            'native_action_context': build_native_action_context(binding, 'P_IN111', feeders, action)}


def _flujo(v=0.97):
    return {'balance': {'unidad': 'kW', 'valores': {'cabecera': 900.0}},
            'perdidas': {'unidad': 'kW', 'valores': {'total': 20.0}},
            'cargabilidad': {'unidad': '%', 'valores': {'lineas': {'L1': 50.0}}},
            'tensiones': {'unidad': 'p.u.', 'valores': {'3091': 0.9522, 'SE41154_BT': v}},
            'confiabilidad': {'ausente': 'spec 012 sin ejecutar'}}


def _lectura(v=0.97, **cambios):
    base = {'project': 'P_IN111', 'folder': 'sistemaeletricoELD', 'pf_version': '2024',
            'feeders': ['IN111', 'TA225'], 'reopen_verified': True,
            'topologia': {'frontera': ['SEC_1091_1055021(1)'],
                          'huellas_gps': {'Enlace_TA225_IN111': 'a' * 64}},
            'flujo': _flujo(v)}
    base.update(cambios)
    return base


def _art():
    return [cp.Artefacto('resultado', 'salida/r.json', 'b' * 64, 120)]


def _construir(plan=None, resultado=None, lectura='def', caso=Caso.CON_PROYECTO, **kw):
    datos = {'limites': LIM, 'referencia': _flujo(), 'calibracion_cuadra': True,
             'creado': '2026-10-21T12:00:00+00:00'}
    datos.update(kw)
    return cp.construir_episodio(plan or _plan(), resultado or {'status': 'OK', 'converged': True},
                                 _lectura() if lectura == 'def' else lectura, _art(), caso=caso,
                                 **datos)


def test_episodio_liga_fuente_proyecto_y_orientacion():
    """024:RF-1 / 024:RF-2 — el episodio lleva la fuente y el proyecto del contexto firmado
    y el orden de alimentadores de la lectura, que expresa la orientación."""
    e = _construir()
    assert e.fuente == {'source_run_id': 'run-7', 'source_mode': 'vnr', 'source_fingerprint': H}
    assert e.nativo['project'] == 'P_IN111' and e.nativo['feeders'] == ['IN111', 'TA225']
    assert e.accion['tipo'] == 'obras_ejecutar' and e.accion['context_sha256']
    assert e.topologia['frontera'] == ['SEC_1091_1055021(1)']
    assert e.clase is Clase.ACCEPTED


def test_contexto_sin_firma_no_da_episodio():
    """024:RF-1 — sin contexto firmado no se sabe de qué fuente viene: no hay episodio."""
    plan = _plan()
    plan['native_action_context']['project'] = 'OTRO'
    with pytest.raises(cp.CapturaImposible):
        _construir(plan=plan)


def test_sin_lectura_nativa_va_a_cuarentena():
    """024:RF-9 — si la lectura tras la acción falla, el episodio queda en cuarentena con lo
    que hay, nunca como aceptado."""
    e = _construir(lectura=None)
    assert e.clase is Clase.QUARANTINE
    assert any('lectura' in b for b in e.aceptacion['bloqueos'])
    assert all('ausente' in e.flujo[k] for k in e.flujo)


def test_lectura_de_otro_proyecto_va_a_cuarentena():
    """024:RF-7 — una lectura de otro proyecto o con otros alimentadores no se mezcla."""
    assert _construir(lectura=_lectura(project='X')).clase is Clase.QUARANTINE
    assert _construir(lectura=_lectura(feeders=['IN111'])).clase is Clase.QUARANTINE


def test_trazado_manual_cambiado_bloquea_el_positivo():
    """024:RF-3 — si la huella del trazado manual cambió sin autorización, el episodio no es
    positivo."""
    plan = _plan()
    plan['huellas_gps_esperadas'] = {'Enlace_TA225_IN111': 'c' * 64}
    e = _construir(plan=plan)
    assert e.clase is Clase.QUARANTINE
    assert any('Enlace_TA225_IN111' in b for b in e.aceptacion['bloqueos'])
    plan['huellas_gps_esperadas'] = {'Enlace_TA225_IN111': 'a' * 64}
    assert _construir(plan=plan).clase is Clase.ACCEPTED


@pytest.mark.parametrize('resultado', [
    {'status': 'NO_CONVERGE', 'converged': False},
    {'status': 'OK', 'converged': True, 'rollback': {'restored': True}},
])
def test_no_converge_o_revertido_es_rechazado(resultado):
    """024:RF-4 — no converge o se revirtió: ``rejected`` con su causa; poner
    ``converged`` a mano no lo vuelve aceptado."""
    e = _construir(resultado=resultado)
    assert e.clase is Clase.REJECTED
    assert e.aceptacion['estado_nativo'] in {'NO_CONVERGE', 'OK'}


def test_sin_reapertura_no_es_aceptado():
    """024:RF-4 / 024:RF-27 — una lectura en la misma sesión que escribió no vale."""
    e = _construir(lectura=_lectura(reopen_verified=False))
    assert e.clase is Clase.QUARANTINE


def test_simulacion_validada_es_contrafactual():
    """024:RF-40 — lo simulado en una copia, sin aplicar, es ``counterfactual``."""
    e = _construir(resultado={'status': 'OK', 'converged': True, 'aplicada': False})
    assert e.clase is Clase.COUNTERFACTUAL and e.accion['aplicada'] is False


def test_caso_dorado_con_subtension():
    """024:RF-26 — IN111–TA225 tras reabrir: 0,8683 p.u. queda como violación."""
    e = _construir(lectura=_lectura(v=0.8683284313))
    assert e.clase is Clase.CONVERGED_WITH_VIOLATIONS
    assert any('SE41154_BT' in v for v in e.aceptacion['violaciones'])


def test_obras_del_resultado_pasan_con_su_alternativa():
    """024:RF-32 — las obras que informa el guion entran con su alternativa del PIDE."""
    resultado = {'status': 'OK', 'converged': True, 'obras': [
        {'alternativa': 'nueva_terna', 'elemento': 'L_3091_3092', 'coste': None}]}
    e = _construir(resultado=resultado)
    assert e.obras[0]['alternativa'] == 'nueva_terna'


def test_misma_evidencia_misma_huella():
    """024:RF-6 — construir dos veces con lo mismo da el mismo episodio."""
    assert _construir().episode_id == _construir().episode_id
    otra = _lectura()
    otra = copy.deepcopy(otra)
    otra['flujo']['perdidas']['valores']['total'] = 21.0
    assert _construir(lectura=otra).episode_id != _construir().episode_id
