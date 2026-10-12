"""Spec 011: estudios y obras de mejora sobre la red calibrada."""

from __future__ import annotations

import json
import random

import pytest

from apoyo import cargar_herramienta
from igea_dgs import estudios_pf as ep
from igea_dgs.studies import ESTUDIOS

#: Semillas de los sorteos: los alimentadores, sus nombres y el orden de llegada cambian.
SEMILLAS = (11, 23, 57, 101)


def test_licencia_comprueba_transferencia_y_herramienta_de_alimentador():
    """011:RF-124, 011:RF-81 — la comprobación de licencia prueba ``ComTransfer`` y
    ``ComFeedertool``.

    La capacidad del enlace usa ``ComTransfer``, de las herramientas de transmisión, y la
    migración de tensión usa ``ComFeedertool``. Si la licencia no los cubre, la spec
    prevé otra vía (RF-125); para elegirla hay que saberlo antes, y la única forma que
    no miente es ejecutar la orden (por eso no basta con ``LicenceHasModule``).
    """
    licencia = cargar_herramienta('check_pf_license.py')
    clases = {clase for clase, *_ in licencia.ORDENES}
    assert {'ComTransfer', 'ComFeedertool'} <= clases


# --------------------------------------------------------------------------- T3
def _medida(rng, *, barras=None, elementos=None):
    barras = barras if barras is not None else [
        (f'B{i}', round(rng.uniform(0.9, 1.08), 4)) for i in range(rng.randint(2, 6))]
    elementos = elementos if elementos is not None else [
        (f'L{i}', 'ElmLne', round(rng.uniform(10, 130), 2)) for i in range(rng.randint(1, 5))]
    vm_min = min(barras, key=lambda b: b[1])
    vm_max = max(barras, key=lambda b: b[1])
    peor = max(elementos, key=lambda e: e[2])
    return {
        'converge': True, 'vm_min': vm_min[1], 'vm_min_barra': vm_min[0],
        'vm_max': vm_max[1], 'vm_max_barra': vm_max[0],
        'mas_cargado': peor[0], 'cargabilidad_max': peor[2],
        'cabecera_kw': round(rng.uniform(500, 5000), 1),
        'cabecera_kvar': round(rng.uniform(100, 900), 1),
        'perdidas_kw': round(rng.uniform(5, 200), 1),
        'barras': barras, 'elementos': elementos,
    }


def _resultados(rng):
    alims = sorted({f'AL{rng.randint(100, 999)}' for _ in range(rng.randint(1, 6))})
    estudios = rng.sample(ep.ESTUDIOS_011, rng.randint(1, len(ep.ESTUDIOS_011)))
    out = []
    for caso in (ep.SIN_PROYECTO, ep.CON_PROYECTO):
        for a in alims:
            for e in estudios:
                out.append({'caso': caso, 'alimentador': a, 'estudio': e, **_medida(rng)})
    return out, alims, estudios


def test_estudios_que_se_ofrecen():
    """011:RF-23 — los siete de esta iteración, en el orden del catálogo, todos defendibles."""
    ofrecidos = ep.estudios_ofrecidos()
    assert [e.clave for e in ofrecidos] == list(ep.ESTUDIOS_011)
    assert set(ep.ESTUDIOS_011) == {'flujo', 'flujo_desequilibrado', 'contingencias', 'troncal',
                                    'punto_apertura', 'perfil_tension', 'balance_fases'}
    assert all(e.defendible for e in ofrecidos)


def test_los_demas_se_listan_con_lo_que_falta_y_no_se_ejecutan():
    """011:RF-24 — los no ofrecidos salen con su dato faltante, y pedirlos es un error."""
    otros = {o['clave']: o for o in ep.estudios_no_ofrecidos()}
    assert set(otros) == {e.clave for e in ESTUDIOS} - set(ep.ESTUDIOS_011)
    assert otros['cortocircuito']['falta'] and 'cortocircuito' in otros['cortocircuito']['falta'][0].lower()
    # Defendible pero fuera de esta iteración: se dice, sin inventar un dato faltante.
    assert otros['flujo_optimo']['falta'] == [] and 'iteración' in otros['flujo_optimo']['motivo']
    with pytest.raises(ep.EstudiosError, match='Cortocircuito'):
        ep.validar_estudios(['flujo', 'cortocircuito'])
    with pytest.raises(ep.EstudiosError):
        ep.validar_estudios([])
    # Sin repetidos y en el orden del catálogo, pida el operador en el orden que pida.
    assert ep.validar_estudios(['troncal', 'flujo', 'troncal']) == ('flujo', 'troncal')


def test_limites_del_perfil_y_del_operador(tmp_path):
    """011:RF-35 — límites del perfil de empresa; el operador los cambia; sin perfil, neutros."""
    ruta = tmp_path / 'perfil_empresa.json'
    sin = ep.limites_de_perfil(ruta)
    assert sin.origen == 'por defecto' and sin.tension_min_pu < 1 < sin.tension_max_pu
    ruta.write_text(json.dumps({'estudios': {'tension_min_pu': 0.94, 'tension_max_pu': 1.06,
                                             'cargabilidad_max_pct': 80}}), encoding='utf-8')
    perfil = ep.limites_de_perfil(ruta)
    assert (perfil.tension_min_pu, perfil.tension_max_pu, perfil.cargabilidad_max_pct) == (0.94, 1.06, 80)
    assert perfil.origen == 'perfil'
    op = perfil.con(cargabilidad_max_pct=90)
    assert op.cargabilidad_max_pct == 90 and op.tension_min_pu == 0.94 and op.origen == 'operador'
    with pytest.raises(ep.EstudiosError):
        perfil.con(tension_min_pu=1.1)
    ruta.write_text(json.dumps({'estudios': {'cargabilidad_max_pct': -5}}), encoding='utf-8')
    with pytest.raises(ep.EstudiosError, match='perfil'):
        ep.limites_de_perfil(ruta)


def test_violaciones_de_tension_y_carga():
    """011:RF-33 — barras fuera de límites y elementos por encima de la cargabilidad."""
    lim = ep.Limites(0.95, 1.05, 100.0)
    medida = _medida(random.Random(0), barras=[('B2', 0.93), ('B1', 1.0), ('B3', 1.07)],
                     elementos=[('L2', 'ElmLne', 120.0), ('T1', 'ElmTr2', 99.9),
                                ('L1', 'ElmLne', 101.0)])
    v = ep.violaciones(medida, lim)
    assert [(x['tipo'], x['elemento']) for x in v] == [
        ('sobrecarga', 'L1'), ('sobrecarga', 'L2'), ('tension_alta', 'B3'), ('tension_baja', 'B2')]
    assert v[-1]['valor'] == 0.93 and v[-1]['limite'] == 0.95
    assert ep.violaciones({'converge': False}, lim) == []


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_diferencia_con_menos_sin(semilla):
    """011:RF-32 — por alimentador, con proyecto menos sin proyecto, valor a valor."""
    rng = random.Random(semilla)
    sin, con = _medida(rng), _medida(rng)
    d = ep.diferencia(con, sin)
    for k in ep.VALORES:
        assert d[k] == pytest.approx(con[k] - sin[k])
    assert ep.diferencia({**con, 'perdidas_kw': None}, sin)['perdidas_kw'] is None
    assert ep.diferencia(con, None) is None


def test_violaciones_nuevas_con_proyecto():
    """011:RF-34 — se marcan las que solo aparecen con proyecto."""
    lim = ep.Limites(0.95, 1.05, 100.0)
    rng = random.Random(1)
    base = dict(caso=ep.SIN_PROYECTO, alimentador='A', estudio='flujo')
    sin = {**base, **_medida(rng, barras=[('B1', 0.94)], elementos=[('L1', 'ElmLne', 50.0)])}
    con = {**base, 'caso': ep.CON_PROYECTO,
           **_medida(rng, barras=[('B1', 0.93), ('B2', 0.92)], elementos=[('L1', 'ElmLne', 110.0)])}
    filas = ep.filas_violaciones([con, sin], lim)
    nuevas = {(f['caso'], f['elemento']): f['nueva'] for f in filas}
    assert nuevas == {(ep.SIN_PROYECTO, 'B1'): '', (ep.CON_PROYECTO, 'B1'): '',
                      (ep.CON_PROYECTO, 'B2'): 'sí', (ep.CON_PROYECTO, 'L1'): 'sí'}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_ficheros_deterministas(semilla, tmp_path):
    """011:RF-37 — una fila por caso, alimentador y estudio (más la diferencia), otra por
    violación; el mismo contenido llegue en el orden que llegue."""
    rng = random.Random(semilla)
    res, alims, estudios = _resultados(rng)
    lim = ep.Limites(0.95, 1.05, 100.0)
    filas = ep.filas_resultados(res, lim)
    assert len(filas) == 3 * len(alims) * len(estudios)
    assert {f['caso'] for f in filas} == {ep.SIN_PROYECTO, ep.CON_PROYECTO, ep.DIFERENCIA}
    barajado = list(res)
    rng.shuffle(barajado)
    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    ep.escribir_csv(ep.filas_resultados(res, lim), ep.COLUMNAS_RESULTADOS, a)
    ep.escribir_csv(ep.filas_resultados(barajado, lim), ep.COLUMNAS_RESULTADOS, b)
    assert a.read_bytes() == b.read_bytes()
    va, vb = tmp_path / 'va.csv', tmp_path / 'vb.csv'
    ep.escribir_csv(ep.filas_violaciones(res, lim), ep.COLUMNAS_VIOLACIONES, va)
    ep.escribir_csv(ep.filas_violaciones(barajado, lim), ep.COLUMNAS_VIOLACIONES, vb)
    assert va.read_bytes() == vb.read_bytes()
    total = sum(len(ep.violaciones(r, lim)) for r in res)
    assert len(va.read_text(encoding='utf-8-sig').splitlines()) == total + 1
