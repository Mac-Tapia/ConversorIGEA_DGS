"""Spec 024, T8: caso dorado IN111–TA225, sin licencia (la aceptación nativa es aparte)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from apoyo import cargar_herramienta

from igea_dgs.digital_twin.capture import construir_episodio
from igea_dgs.digital_twin.episode import Caso, Clase
from igea_dgs.digital_twin.evaluacion import Limites
from igea_dgs.native_action import build_native_action_context

FIXTURE = Path(__file__).parent / 'fixtures' / 'digital_twin' / 'in111_ta225_topology_episode.json'
ESPERADO = json.loads(FIXTURE.read_text(encoding='utf-8'))
H = '1' * 64


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('accept_digital_twin_in111_ta225.py', 'aceptacion_gemelo')


def _lectura():
    """Lo que dejaría la lectura nativa del caso dorado: islas de 10 y 22,9 kV."""
    barras = {'ElmTerm:3091': {'nombre': '3091', 'kv': 10.0},
              'ElmTerm:IN_A': {'nombre': 'IN_A', 'kv': 10.0},
              'ElmTerm:3092': {'nombre': '3092', 'kv': 22.9},
              'ElmTerm:TA_B': {'nombre': 'TA_B', 'kv': 22.9},
              'ElmTerm:SE41154_BT': {'nombre': 'SE41154_BT', 'kv': 0.38}}
    return {
        'project': ESPERADO['project'], 'folder': ESPERADO['folder'],
        'feeders': list(ESPERADO['feeders']), 'reopen_verified': True, 'pf_version': '2024',
        'topologia': {
            'barras': barras,
            'componentes': [['ElmTerm:3091', 'ElmTerm:IN_A'], ['ElmTerm:3092', 'ElmTerm:TA_B'],
                            ['ElmTerm:SE41154_BT']],
            'frontera': [], 'huellas_gps': {ESPERADO['enlace']: 'a' * 64},
            'estados': {ESPERADO['frontera_cerrada']: {'clase': 'StaSwitch', 'en_servicio': True, 'cerrado': True},
                        ESPERADO['enlace']: {'clase': 'ElmLne', 'en_servicio': True, 'cerrado': True}}},
        'flujo': {
            'balance': {'unidad': 'kW', 'valores': {'cabeceras': {'IN111': 1.0, 'TA225': 1.0}}},
            'perdidas': {'unidad': 'kW', 'valores': {'total': 1.0}},
            'cargabilidad': {'unidad': '%', 'valores': {'lineas': {}, 'transformadores': {}}},
            'tensiones': {'unidad': 'p.u.', 'valores': {
                'ElmTerm:3091': 0.9521694512, 'ElmTerm:3092': 0.9604280727,
                'ElmTerm:IN_A': 0.99, 'ElmTerm:TA_B': 0.98, 'ElmTerm:SE41154_BT': 0.8683284313}},
            'confiabilidad': {'ausente': 'sin calcular'}},
    }


def test_el_caso_dorado_no_lleva_coordenadas_ni_clientes():
    """024:RF-24 — el fixture solo trae identificadores, tensiones y la clase esperada."""
    def claves(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield k.lower()
                yield from claves(v)
        elif isinstance(x, list):
            for v in x:
                yield from claves(v)

    prohibidas = ('gps', 'lat', 'lon', 'coord', 'cliente', 'suministro')
    assert not [k for k in claves(ESPERADO) if any(p in k for p in prohibidas)]


def test_hechos_del_caso_dorado(guion):
    """024:RF-24 / 024:RF-25 / 024:RF-27 — 3091 en la isla de 10 kV, 3092 en la de 22,9 kV,
    sin continuidad; seccionador cerrado; enlace igual en dos lecturas; tensiones medidas."""
    resultado = guion.comprobar(_lectura(), _lectura(), ESPERADO)
    assert all(v['pass'] for v in resultado.values()), resultado


@pytest.mark.parametrize(('cambio', 'clave'), [
    (lambda b: b['topologia']['componentes'].__setitem__(0, ['ElmTerm:3091', 'ElmTerm:3092']),
     'sin_continuidad'),
    (lambda b: b['topologia']['huellas_gps'].__setitem__(ESPERADO['enlace'], 'b' * 64), 'enlace_conservado'),
    (lambda b: b['topologia']['estados'][ESPERADO['frontera_cerrada']].__setitem__('cerrado', False),
     'frontera_corregida'),
    (lambda b: b.__setitem__('reopen_verified', False), 'dos_lecturas_iguales'),
    (lambda b: b['flujo']['tensiones']['valores'].__setitem__('ElmTerm:SE41154_BT', 0.95), 'minima'),
])
def test_cada_hecho_que_falla_se_nota(guion, cambio, clave):
    """024:RF-25 / 024:RF-26 / 024:RF-27 — cambiar el trazado, abrir el seccionador, unir las
    islas, no reabrir u ocultar la subtensión falla su comprobación."""
    b = copy.deepcopy(_lectura())
    cambio(b)
    assert not guion.comprobar(_lectura(), b, ESPERADO)[clave]['pass']


def test_la_subtension_queda_como_violacion():
    """024:RF-26 — tras reabrir, 0,8683 p.u. en SE41154_BT hace del episodio de «Con
    proyecto» una violación, aunque converja."""
    binding = {'project': ESPERADO['project'], 'source_run_id': 'r', 'source_mode': 'vnr',
               'source_fingerprint': H}
    plan = {'project': ESPERADO['project'], 'feeders': list(ESPERADO['feeders']),
            'native_action_context': build_native_action_context(
                binding, ESPERADO['project'], ESPERADO['feeders'], 'digital_twin_aceptacion')}
    e = construir_episodio(plan, {'status': 'OK', 'converged': True}, _lectura(), [],
                           caso=Caso.CON_PROYECTO, limites=Limites('NTCSE', 0.95, 1.05, 100, 80),
                           referencia=None, calibracion_cuadra=None, creado='2026-10-21T00:00:00+00:00')
    assert e.clase is Clase.CONVERGED_WITH_VIOLATIONS
    assert any('SE41154_BT' in v for v in e.aceptacion['violaciones'])


def test_sin_vinculo_no_se_acepta(guion, tmp_path):
    """024:RF-1 — sin vínculo de la fuente no se sabe de dónde viene: código 2, sin DIgSILENT."""
    from igea_dgs.powerfactory_binding import REGISTRO_SCHEMA

    registro = tmp_path / 'vinculos.json'
    registro.write_text(json.dumps({'schema': REGISTRO_SCHEMA, 'vinculos': {}}), encoding='utf-8')
    salida = tmp_path / 'informe.json'
    assert guion.main(['--esperado', str(FIXTURE), '--output-json', str(salida),
                       '--vinculos', str(registro)]) == 2
    assert 'vínculo' in json.loads(salida.read_text(encoding='utf-8'))['error']
