"""Spec 011: estudios y obras de mejora sobre la red calibrada."""

from __future__ import annotations

import json
import random

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid import estudios_pf as ep
from convertersmartgrid.studies import ESTUDIOS

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
    # 012:RF-19: sin libro de la empresa, de la 012 solo los que no lo necesitan.
    assert [e.clave for e in ofrecidos if e.clave in ep.ESTUDIOS_011] == list(ep.ESTUDIOS_011)
    assert {e.clave for e in ofrecidos} - set(ep.ESTUDIOS_011) == {'alojamiento', 'curvas_pv'}
    assert set(ep.ESTUDIOS_011) == {'flujo', 'flujo_desequilibrado', 'contingencias', 'troncal',
                                    'punto_apertura', 'perfil_tension', 'balance_fases'}
    assert all(e.defendible for e in ofrecidos)


def test_los_demas_se_listan_con_lo_que_falta_y_no_se_ejecutan():
    """011:RF-24 — los no ofrecidos salen con su dato faltante, y pedirlos es un error."""
    otros = {o['clave']: o for o in ep.estudios_no_ofrecidos()}
    assert set(otros) == {e.clave for e in ESTUDIOS} - set(ep.ESTUDIOS_011) - {'alojamiento', 'curvas_pv'}
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


def test_diagnostico_conserva_medidas_y_violaciones_sin_cambiar_la_diferencia(tmp_path):
    """037:RF-6 — el CSV contiene el diagnóstico y con−sin mantiene su significado."""
    lim = ep.Limites(0.95, 1.05, 100.0)
    medida = _medida(random.Random(1), barras=[('B1', 1.0)], elementos=[('L1', 'ElmLne', 50)])
    comun = {'alimentador': 'A', 'estudio': 'flujo'}
    sin = {**comun, **medida, 'caso': ep.SIN_PROYECTO, 'cabecera_kw': 1000}
    diag = {**comun, **medida, 'caso': 'Cargas nuevas', 'cabecera_kw': 1400,
            'barras': [('B1', 0.90)], 'vm_min': 0.90}
    con = {**comun, **medida, 'caso': ep.CON_PROYECTO, 'cabecera_kw': 1300}
    resultados = ep.filas_resultados([sin, diag, con], lim)
    assert next(r for r in resultados if r['caso'] == 'Cargas nuevas')['violaciones'] == 1
    assert next(r for r in resultados if r['caso'] == ep.DIFERENCIA)['cabecera_kw'] == 300
    violaciones = ep.filas_violaciones([sin, diag, con], lim)
    assert len(violaciones) == 1 and violaciones[0]['caso'] == 'Cargas nuevas'
    ruta = ep.escribir_csv(violaciones, ep.COLUMNAS_VIOLACIONES, tmp_path / 'violaciones.csv')
    assert 'Cargas nuevas' in ruta.read_text(encoding='utf-8-sig')


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


def test_los_de_la_012_dependen_del_libro_y_de_la_licencia():
    """012:RF-1, 012:RF-4, 012:RF-19, 012:RF-63 — sin libro, confiabilidad, reconectadores y
    condensadores se listan con el dato que les falta; con libro completo se ofrecen; un
    módulo que la licencia no cubre se lista como no disponible con su nombre."""
    from convertersmartgrid import datos_empresa as de

    no = {o['clave']: o for o in ep.estudios_no_ofrecidos()}
    for clave in ('fiabilidad', 'reconectadores', 'condensadores'):
        assert 'libro de la empresa' in no[clave]['motivo']
    libro = de.Libro(tasas={'linea': de.Tasa('linea', 0.1, None, 2.0)}, tiempos_min={'localizacion': 5, 'manual': 9},
                     bancos=[de.Banco(150, 2, True, 10.0, 20, 1.0)], coste_energia_kwh=0.1, tasa_descuento=0.1)
    claves = {e.clave for e in ep.estudios_ofrecidos(libro)}
    assert set(ep.ESTUDIOS_012) <= claves
    sin_bancos = de.Libro(**{**libro.__dict__, 'bancos': [], 'hojas_que_faltan': ['Bancos de condensadores']})
    no = {o['clave']: o for o in ep.estudios_no_ofrecidos(sin_bancos)}
    assert 'Bancos de condensadores' in no['condensadores']['motivo'] and 'fiabilidad' not in no
    no = {o['clave']: o for o in ep.estudios_no_ofrecidos(libro, sin_licencia=['ComHostcap'])}
    assert 'ComHostcap' in no['alojamiento']['motivo'] and 'licencia' in no['alojamiento']['motivo']
    with pytest.raises(ep.EstudiosError, match='ComHostcap'):
        ep.validar_estudios(['alojamiento'], libro, ['ComHostcap'])
    assert ep.validar_estudios(['curvas_pv', 'flujo', 'fiabilidad'], libro) == ('flujo', 'fiabilidad', 'curvas_pv')
