"""Spec 101: la calibración cambia sola los transformadores que impiden converger.

CA101 + CHN102 (2026-11-09): SE20701 pedía 1 506 kVA con 50 kVA y la calibración quedaba en
FALLO_VALIDACION_NATIVA a la espera de que el operador pulsara «Implementar transformadores».
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from convertersmartgrid.web import services


def _tr(sed, kva=50.0, unidades=1):
    return [{'transformador': f'TR_{sed}', 'tipo': f'TR_{kva:g}kVA', 'kva': kva, 'unidades': unidades}]


def _prop(kva, unidades=1):
    return {'kva': kva, 'unidades': unidades, 'tipo_nuevo': f'TR_{kva}kVA_NTP'}


def _informe(feeder, status='FALLO_VALIDACION_NATIVA', fijas=(), umbral=(), cuadrado=False):
    return {'feeder': feeder, 'status': status, 'cuadrado': cuadrado, 'avisos': [],
            'fijas_sobre_su_transformador': list(fijas), 'sed_sobre_umbral': {'sed': list(umbral)}}


def _fija(sed, kva=630, unidades=3, transformadores=None):
    return {'sed': sed, 'transformadores': transformadores or _tr(sed), 'propuesta': _prop(kva, unidades)}


def test_se_cambian_las_sed_sobre_el_100_con_propuesta():
    """101:RF-1, 101:RF-12 — fijas y escaladas sobre el 100 %; las del umbral al 100 % quedan para el operador."""
    informes = [_informe('CA101', fijas=[_fija('SE20701')],
                         umbral=[{**_fija('SE20701'), 'nivel': 'sobre_100'},
                                 {**_fija('SE30000', 400, 1), 'nivel': 'sobre_100', 'tipo': 'escalada'},
                                 {**_fija('SE20531', 400, 1), 'nivel': 'sobre_umbral'}]),
                _informe('CHN102', fijas=[_fija('SE20049', 630, 6)])]
    cambios, sin = services.cambios_automaticos(informes, {})
    assert {f: [c['sed'] for c in cs] for f, cs in cambios.items()} == {
        'CA101': ['SE20701', 'SE30000'], 'CHN102': ['SE20049']}
    assert cambios['CA101'][0] == {'sed': 'SE20701', 'transformador': 'TR_SE20701',
                                   'propuesta': _prop(630, 3)}
    assert sin == []


def test_calibracion_valida_no_cambia_nada():
    """101:RF-1 — solo cuando la calibración no queda válida."""
    ok = _informe('CA101', status='OK', cuadrado=True, fijas=[_fija('SE20701')])
    assert services.cambios_automaticos([ok], {}) == ({}, [])


def test_no_se_repite_lo_ya_aplicado():
    """101:RF-4, 101:RF-6 — una propuesta igual a la aplicada no es un cambio nuevo; una mayor, sí."""
    hechos = {('CA101', 'SE20701'): (630, 3)}
    assert services.cambios_automaticos([_informe('CA101', fijas=[_fija('SE20701')])], hechos) == ({}, [])
    cambios, _ = services.cambios_automaticos([_informe('CA101', fijas=[_fija('SE20701', 630, 4)])], hechos)
    assert cambios['CA101'][0]['propuesta']['unidades'] == 4


def test_sin_propuesta_se_dice_por_que():
    """101:RF-7 — sin propuesta (sin tabla, más de un transformador), el motivo de cada SED."""
    sin_tabla = {'sed': 'SE1', 'transformadores': _tr('SE1'),
                 'propuesta': {'kva': None, 'motivo': 'falta la tabla de fichas en el perfil'}}
    dos = {'sed': 'SE2', 'transformadores': _tr('SE2') + _tr('SE2b'), 'propuesta': _prop(400)}
    cambios, sin = services.cambios_automaticos([_informe('A', fijas=[sin_tabla, dos])], {})
    assert cambios == {}
    assert sin[0].startswith('A: SE1: falta la tabla') and 'SE2' in sin[1] and 'transformador' in sin[1]


class _Job:
    def __init__(self):
        self.cancel = threading.Event()


class _Ctx:
    def __init__(self):
        self.job = _Job()
        self.registro: list[str] = []

    def log(self, m):
        self.registro.append(m)


class _Ws:
    def __init__(self, tmp: Path):
        self.plans_dir = tmp / 'planes'
        self.out_dir = tmp / 'salida'
        self.plans_dir.mkdir()
        self.out_dir.mkdir()
        self.calibraciones = {}
        plan = self.plans_dir / 'ajuste_cabecera_t_1.json'
        plan.write_text('{}', encoding='utf-8')
        self.cargas_planes = {'t': {'kind': 'ajuste_cabecera', 'project': 'P', 'feeders': ['CA101'],
                                    'path': str(plan), 'paths': [str(plan)]}}


@pytest.fixture()
def corrida(tmp_path, monkeypatch):
    """``_correr_guion_ajuste`` sustituido por una secuencia de informes, uno por llamada."""
    secuencia: list[list[dict]] = []
    planes: list[list[str]] = []

    def guion(_ws, _ctx, _project, _feeders, paths, _reports, _flag, *, simular):
        planes.append(list(paths))
        return secuencia.pop(0), 0

    monkeypatch.setattr(services, '_correr_guion_ajuste', guion)
    monkeypatch.setattr(services, '_require_pf', lambda: (None, None))
    monkeypatch.setattr(services, '_escanear_sin_bloquear', lambda *a, **k: None)
    monkeypatch.setattr(services, '_verdad_de_la_calibracion',
                        lambda _ctx, inf: {'estado_trabajo': 'done' if all(i.get('cuadrado') for i in inf)
                                           else 'parcial'})
    return _Ws(tmp_path), _Ctx(), secuencia, planes


def test_cambia_y_recalibra_hasta_quedar_valida(corrida):
    """101:RF-2, 101:RF-3, 101:RF-8, 101:RF-9 — sin pulsar nada: cambio, recalibración del proyecto y su resultado."""
    ws, ctx, secuencia, planes = corrida
    secuencia += [[_informe('CA101', fijas=[_fija('SE20701')])],
                  [_informe('CA101', status='OK', cuadrado=True)]]
    out = services.ajuste_ejecutar(ws, ctx, 't', simular=False)
    assert out['estado_trabajo'] == 'done' and out['informe']['cuadrado']
    assert planes[1][0].endswith('_transformadores.json')
    assert out['transformadores_automaticos'] == [
        {'ronda': 1, 'cambios': {'CA101': [{'sed': 'SE20701', 'antes_kva': 50.0, 'antes_unidades': 1,
                                            'kva': 630, 'unidades': 3}]}}]
    assert any('SE20701' in m and '50 kVA' in m and '3 × 630 kVA' in m for m in ctx.registro)


def test_no_mas_de_tres_rondas(corrida):
    """101:RF-4, 101:RF-5 — cada ronda pide más potencia; a la tercera se para con el fallo."""
    ws, ctx, secuencia, _ = corrida
    secuencia += [[_informe('CA101', fijas=[_fija('SE20701', 630, n)])] for n in (1, 2, 3, 4)]
    out = services.ajuste_ejecutar(ws, ctx, 't', simular=False)
    assert len(out['transformadores_automaticos']) == 3 and not secuencia
    assert out['estado_trabajo'] == 'parcial'


def test_ronda_sin_cambio_nuevo_para(corrida):
    """101:RF-6 — la misma propuesta que ya se aplicó no abre otra ronda."""
    ws, ctx, secuencia, _ = corrida
    secuencia += [[_informe('CA101', fijas=[_fija('SE20701')])], [_informe('CA101', fijas=[_fija('SE20701')])]]
    out = services.ajuste_ejecutar(ws, ctx, 't', simular=False)
    assert len(out['transformadores_automaticos']) == 1 and not secuencia


def test_cancelado_no_empieza_otra_ronda(corrida):
    """101:RF-10, 101:RF-11 — cancelar no deshace lo cambiado ni abre otra ronda."""
    ws, ctx, secuencia, _ = corrida
    secuencia += [[_informe('CA101', fijas=[_fija('SE20701')])]]
    ctx.job.cancel.set()
    out = services.ajuste_ejecutar(ws, ctx, 't', simular=False)
    assert out['transformadores_automaticos'] == [] and not secuencia
    assert any('cancel' in m for m in ctx.registro)


def test_simular_no_cambia_transformadores(corrida):
    """101:RF-13 — simulando no se escribe nada en DIgSILENT."""
    ws, ctx, secuencia, _ = corrida
    secuencia += [[_informe('CA101', fijas=[_fija('SE20701')])]]
    out = services.ajuste_ejecutar(ws, ctx, 't', simular=True)
    assert 'transformadores_automaticos' not in out and not secuencia
