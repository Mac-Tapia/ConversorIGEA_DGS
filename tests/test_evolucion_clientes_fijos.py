"""Spec 105: evolución de los clientes fijos de un alimentador, su libro, su archivo y su API, con libros sintéticos."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('python_calamine')
openpyxl = pytest.importorskip('openpyxl')
pytest.importorskip('pandas')

from test_pronostico_demanda import _equivalencia, _libro_cabecera, _libro_clientes, _suministros  # noqa: E402

from convertersmartgrid import archivo_informes as ar  # noqa: E402
from convertersmartgrid.dominio import evolucion_mensual as em  # noqa: E402
from convertersmartgrid.dominio.meses_copiados import fraccion_repetida, mes_de_registro, meses_copiados  # noqa: E402
from convertersmartgrid.evolucion_clientes import (  # noqa: E402
    FuentesEvolucion, ambito, calcular_evolucion, escribir_libro, meses_del_rango)

PASO = timedelta(minutes=15)


def _mes(mes: str, base: float, dias: int | None = None) -> list[tuple[datetime, float, float]]:
    """Un mes de 15 minutos con la forma del día y la máxima exacta 1,5 × base a las 06:00."""
    inicio = datetime.strptime(mes, '%Y-%m')
    siguiente = (inicio + timedelta(days=32)).replace(day=1)
    fin = siguiente if dias is None else inicio + timedelta(days=dias)
    salida, t = [], inicio + PASO
    while t <= fin:
        p = base * (1 + .5 * math.sin(2 * math.pi * (t.hour * 60 + t.minute) / 1440))
        salida.append((t, p, p * .3))
        t += PASO
    return salida


def _arrays(curva):
    return (np.array([x[0] for x in curva], dtype='datetime64[m]'), np.array([x[1] for x in curva]),
            np.array([x[2] for x in curva]))


# Enero a mayo de 2026. Abril repite marzo día a día (como 0426clientesImportantes.xlsb).
# 111 se renumera a 900 desde febrero; 222 entra en marzo; 555 es de otro alimentador y en febrero solo trae 20 días;
# 333 es de F1 y no tiene medición; 444 está en los libros y no en los suministros.
BASES = {
    '2026-01': {'111': 100.0, '555': 10.0, '444': 1.0},
    '2026-02': {'900': 110.0, '555': 12.0},
    '2026-03': {'900': 121.0, '222': 50.0, '555': 14.0},
    '2026-04': {'900': 121.0, '222': 50.0, '555': 14.0},
    '2026-05': {'900': 133.1, '222': 60.0, '555': 16.0},
}


@pytest.fixture(scope='module')
def libros(tmp_path_factory):
    raiz = tmp_path_factory.mktemp('evolucion')
    for mes, clientes in BASES.items():
        curvas = {c: _mes(mes, b, 20 if (mes, c) == ('2026-02', '555') else None) for c, b in clientes.items()}
        if mes == '2026-04':
            # El libro copiado: los valores de marzo con las fechas de abril, mismo día y hora.
            curvas = {c: [(t + (datetime(2026, 4, 1) - datetime(2026, 3, 1)), p, q) for t, p, q in _mes('2026-03', b)
                          if (t - PASO).month == 3 and (t - PASO).day <= 30] for c, b in clientes.items()}
        _libro_clientes(raiz / 'cli' / '2026' / f'{mes[5:]}26clientes.xlsx', curvas)
    sumi = _suministros(raiz / 'sum.xlsx', [('111', '900', 'S1', 'F1'), ('222', '222', 'S2', 'F1'),
                                             ('333', '333', 'S3', 'F1'), ('555', '555', 'S5', 'F2')])
    cabecera = {m: [] for m in ('M1', 'M2')}
    for mes, clientes in BASES.items():
        fijos = [_mes(mes, b) for c, b in clientes.items() if c in ('111', '900', '222')]
        cabecera['M1'] += [(t, sum(f[i][1] for f in fijos) + 100.0, 0.0) for i, (t, _p, _q) in enumerate(fijos[0])]
        # F2 tiene una central: su cabecera va en los dos sentidos.
        cabecera['M2'] += [(t, 50.0 if i % 2 else -50.0, 0.0) for i, (t, _p, _q) in enumerate(fijos[0])]
    _libro_cabecera(raiz / 'cab' / 'c.xlsx', cabecera)
    eq = _equivalencia(raiz / 'eq.xlsx', [('F1', 'M1', 10.0, 'S1'), ('F2', 'M2', 10.0, 'S1')])
    return raiz, FuentesEvolucion(raiz / 'cli', sumi, medidores=eq, cabecera=(raiz / 'cab' / 'c.xlsx',))


@pytest.fixture(scope='module')
def evolucion(libros):
    _raiz, fuentes = libros
    pasos = []
    ev = calcular_evolucion(fuentes, ['F1', 'F2', 'F9'], '2026-01', '2026-05', avance=lambda i, n, l: pasos.append((i, n)))
    return ev, pasos


def _cliente(ev, codigo):
    return next(c for c in ev.datos['clientes'] if c['codigo'] == codigo)


def _por_mes(cliente):
    return {d['mes']: d for d in cliente['meses']}


# --------------------------------------------------------------------------- dominio
def test_mes_del_registro_cierra_con_las_00_del_dia_1():
    """105:RF-4 — el registro de las 00:00 del día 1 es del mes anterior."""
    t = np.array(['2026-02-01T00:00', '2026-02-01T00:15'], dtype='datetime64[m]')
    assert [str(m) for m in mes_de_registro(t)] == ['2026-01', '2026-02']


def test_indicadores_del_mes():
    """105:RF-5, 105:RF-6 — máximas con su instante, medias, energías, FP, factor de carga y registros."""
    d = em.indicadores_por_mes(*_arrays(_mes('2026-02', 100.0)))['2026-02']
    assert d['p_max'] == pytest.approx(150.0) and d['fecha_p_max'] == '2026-02-01T06:00'
    assert d['q_en_p_max'] == pytest.approx(45.0) and d['q_max'] == pytest.approx(45.0)
    assert d['fecha_q_max'] == '2026-02-01T06:00'
    assert d['p_media'] == pytest.approx(100.0, rel=1e-6) and d['q_media'] == pytest.approx(30.0, rel=1e-6)
    assert d['energia_p'] == pytest.approx(100.0 * 24 * 28 / 1000, rel=1e-6)
    assert d['energia_q'] == pytest.approx(30.0 * 24 * 28 / 1000, rel=1e-6)
    assert d['fp'] == pytest.approx(1 / math.hypot(1, .3))
    assert d['factor_carga'] == pytest.approx(100 / 150, rel=1e-6)
    assert (d['registros'], d['esperados'], d['completo']) == (2688, 2688, True)
    corto = em.indicadores_por_mes(*_arrays(_mes('2026-02', 100.0, dias=20)))['2026-02']
    assert (corto['registros'], corto['completo']) == (1920, False)


def test_crecimiento_desde_el_primer_mes_con_datos():
    """105:RF-7 — un cliente que entra a mitad crece desde su primer mes."""
    assert em.crecimiento({'2026-01': None, '2026-03': 50.0, '2026-05': 60.0}) == {
        'pct': pytest.approx(20.0), 'desde': '2026-03', 'hasta': '2026-05'}
    assert em.crecimiento({'2026-03': 50.0})['pct'] is None


def test_variacion_frente_al_mes_anterior_con_datos():
    """105:RF-8 — un mes sin datos no corta la variación: se compara con el anterior que tiene."""
    v = em.variaciones({'2026-01': 100.0, '2026-02': 110.0, '2026-04': 99.0})
    assert v['2026-02'] == {'pct': pytest.approx(10.0), 'respecto': '2026-01'}
    assert v['2026-04'] == {'pct': pytest.approx(-10.0), 'respecto': '2026-02'}


def test_tendencia_con_un_mes_faltante_usa_el_numero_real_del_mes():
    """105:RF-9 — sin rellenar el hueco: la pendiente es sobre el mes real, también entre años."""
    valores = {'2025-11': 100.0, '2025-12': 110.0, '2026-02': 130.0}
    x = [2025 * 12 + 11, 2025 * 12 + 12, 2026 * 12 + 2]
    esperado = np.polyfit(x, [100.0, 110.0, 130.0], 1)[0] / np.mean([100.0, 110.0, 130.0]) * 100
    assert em.tendencia(valores) == pytest.approx(esperado)
    assert em.tendencia(valores) != pytest.approx(np.polyfit([0, 1, 2], [100.0, 110.0, 130.0], 1)[0] / 113.33 * 100)
    assert em.tendencia({'2026-01': 1.0, '2026-02': 2.0}) is None


def test_mes_de_mayor_valor():
    """105:RF-10 — el mes de mayor valor, sin los excluidos."""
    meses = {'2026-01': {'p_max': 1.0, 'energia_p': 5.0, 'q_max': 3.0, 'energia_q': 1.0, 'fecha_p_max': 'a'},
             '2026-02': {'p_max': 2.0, 'energia_p': 4.0, 'q_max': 9.0, 'energia_q': 2.0, 'fecha_p_max': 'b'},
             '2026-03': {'p_max': 9.0, 'energia_p': 9.0, 'q_max': 9.0, 'energia_q': 9.0, 'fecha_p_max': 'c'}}
    r = em.resumen(meses, excluidos=['2026-03'])
    assert r['mes_mayor'] == {'p_max': '2026-02', 'energia_p': '2026-01', 'q_max': '2026-02', 'energia_q': '2026-02'}
    assert (r['p_max'], r['fecha_p_max']) == (2.0, 'b')


def test_mes_copiado_por_mayoria_de_las_series_comparables():
    """105:RF-13, 105:RF-14 — ≥ 95 % iguales en más de la mitad de las series con los dos meses."""
    marzo = _mes('2026-03', 10.0)
    copia = [(t + timedelta(days=31), p, q) for t, p, q in marzo if (t - PASO).day <= 30]
    otra = _mes('2026-04', 11.0)
    unir = lambda *cs: _arrays([x for c in cs for x in c])  # noqa: E731
    assert fraccion_repetida(*unir(marzo, copia), '2026-04')[0] == pytest.approx(1.0)
    assert fraccion_repetida(*unir(marzo, otra), '2026-04')[0] < .95
    assert fraccion_repetida(*unir(copia), '2026-04') is None          # sin marzo no se compara
    dos_de_tres = {'a': unir(marzo, copia), 'b': unir(marzo, copia), 'c': unir(marzo, otra)}
    cp = meses_copiados(dos_de_tres, ['2026-03', '2026-04'])['2026-04']
    assert (cp.de, cp.series, cp.comparables) == ('2026-03', ('a', 'b'), 3)
    assert not meses_copiados({'a': unir(marzo, copia), 'c': unir(marzo, otra)}, ['2026-04'])   # la mitad no basta


# --------------------------------------------------------------------------- con libros
def test_clientes_fijos_por_radial_y_renumeracion(evolucion):
    """105:RF-1, 105:RF-2, 105:RF-3 — los suministros de cada alimentador; 111 y 900 son un solo cliente."""
    ev, _ = evolucion
    assert sorted(c['codigo'] for c in ev.datos['clientes'] if c['alimentador'] == 'F1') == ['222', '900']
    assert [c['codigo'] for c in ev.datos['clientes'] if c['alimentador'] == 'F2'] == ['555']
    assert ev.datos['renumeraciones'] == [{'anterior': '111', 'actual': '900', 'alimentador': 'F1', 'meses': ['2026-01']}]
    novecientos = _por_mes(_cliente(ev, '900'))
    assert sorted(novecientos) == ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']
    assert novecientos['2026-01']['p_max'] == pytest.approx(150.0)       # enero, con su código anterior


def test_series_de_15_minutos_del_rango(evolucion):
    """105:RF-4 — la serie va del 00:15 del día 1 al 00:00 del mes siguiente al último."""
    ev, _ = evolucion
    t, p, q = ev.series['900']
    assert str(t[0]) == '2026-01-01T00:15' and str(t[-1]) == '2026-06-01T00:00'
    assert np.allclose(q, p * .3)


def test_mes_copiado_fuera_del_crecimiento_y_la_tendencia(evolucion):
    """105:RF-13 — abril se marca copia de marzo, queda en los meses y no cuenta."""
    ev, _ = evolucion
    assert [(c['mes'], c['de'], c['comparables']) for c in ev.datos['copias']] == [('2026-04', '2026-03', 3)]
    c = _cliente(ev, '900')
    assert _por_mes(c)['2026-04']['copia_de'] == '2026-03'
    assert '2026-04' not in c['resumen']['variacion']['p_max']
    assert c['resumen']['crecimiento']['p_max'] == {'pct': pytest.approx(33.1), 'desde': '2026-01', 'hasta': '2026-05'}
    assert any(a['tipo'] == 'copia' and '2026-04' in a['texto'] for a in ev.datos['avisos'])


def test_cliente_que_entra_a_mitad_crece_desde_su_primer_mes(evolucion):
    """105:RF-7 — 222 entra en marzo: su crecimiento es de marzo a mayo."""
    ev, _ = evolucion
    r = _cliente(ev, '222')['resumen']
    assert r['crecimiento']['p_max'] == {'pct': pytest.approx(20.0), 'desde': '2026-03', 'hasta': '2026-05'}
    assert r['tendencia']['p_max'] is None              # dos meses sin la copia: no hay tendencia


def test_mes_incompleto_se_dice(evolucion):
    """105:RF-6, 105:RF-16 — febrero de 555 tiene 20 días."""
    ev, _ = evolucion
    feb = _por_mes(_cliente(ev, '555'))['2026-02']
    assert (feb['registros'], feb['esperados'], feb['completo']) == (1920, 2688, False)
    assert any(a['tipo'] == 'incompleto' and '555 2026-02' in a['texto'] for a in ev.datos['avisos'])


def test_tendencia_y_meses_de_mayor_valor_del_cliente(evolucion):
    """105:RF-9, 105:RF-10 — con la copia fuera, sobre enero, febrero, marzo y mayo."""
    ev, _ = evolucion
    r = _cliente(ev, '900')['resumen']
    x = [2026 * 12 + m for m in (1, 2, 3, 5)]
    y = np.array([150.0, 165.0, 181.5, 199.65])
    assert r['tendencia']['p_max'] == pytest.approx(np.polyfit(x, y, 1)[0] / y.mean() * 100, rel=1e-6)
    assert r['mes_mayor'] == {'p_max': '2026-05', 'energia_p': '2026-05', 'q_max': '2026-05', 'energia_q': '2026-05'}
    assert r['variacion']['p_max']['2026-05'] == {'pct': pytest.approx(10.0), 'respecto': '2026-03'}


def test_suma_del_alimentador_y_maxima_coincidente(evolucion):
    """105:RF-11 — el total suma los clientes con datos en cada mes y da su máxima coincidente."""
    ev, _ = evolucion
    f1 = next(t for t in ev.datos['totales'] if t['alimentador'] == 'F1')
    meses = {d['mes']: d for d in f1['meses']}
    assert meses['2026-02']['clientes'] == 1 and meses['2026-03']['clientes'] == 2
    assert meses['2026-03']['p_max'] == pytest.approx(1.5 * (121 + 50))
    assert meses['2026-03']['p_max_coincidente'] == pytest.approx(1.5 * (121 + 50))
    assert f1['resumen']['crecimiento']['p_max']['pct'] == pytest.approx((1.5 * 193.1) / 150 * 100 - 100)
    # La P máx del periodo del total es la de la suma en un instante (mayo), no la suma de las máximas.
    assert (f1['resumen']['p_max'], f1['resumen']['fecha_p_max']) == (pytest.approx(1.5 * 193.1), '2026-05-01T06:00')


def test_participacion_en_la_maxima_de_cabecera(evolucion):
    """105:RF-12 — la cabecera es la suma de los fijos más 100 kW: su máxima y la P de los fijos en ese instante."""
    ev, _ = evolucion
    f1 = next(t for t in ev.datos['totales'] if t['alimentador'] == 'F1')
    marzo = next(c for c in f1['cabecera'] if c['mes'] == '2026-03')
    assert marzo['p_max'] == pytest.approx(1.5 * 171 + 100)
    assert marzo['fijas_kw'] == pytest.approx(1.5 * 171)
    assert marzo['participacion'] == pytest.approx(1.5 * 171 / (1.5 * 171 + 100) * 100)
    # Abril es copia: la cabecera se mide, pero los fijos de ese mes no son medición.
    abril = next(c for c in f1['cabecera'] if c['mes'] == '2026-04')
    assert (abril['fijas_kw'], abril['participacion'], abril['copia_de']) == (None, None, '2026-03')
    f2 = next(t for t in ev.datos['totales'] if t['alimentador'] == 'F2')
    assert f2['cabecera'] is None
    assert any(a['tipo'] == 'cabecera' and 'F2' in a['texto'] and 'dos sentidos' in a['texto'] for a in ev.datos['avisos'])


def test_sin_medicion_sin_clientes_y_sin_suministro_se_dicen(evolucion):
    """105:RF-15, 105:RF-16 — nada bloquea: cada cosa se dice y se sigue."""
    ev, _ = evolucion
    tipos = {(a['tipo'], a['texto'].split(':')[0].split(' ')[0]) for a in ev.datos['avisos']}
    assert ('sin_medicion', '333') in tipos
    assert ('sin_clientes', 'F9') in tipos
    sin_sum = next(a for a in ev.datos['avisos'] if a['tipo'] == 'sin_suministro')
    assert '444' in sin_sum['texto']


def test_avance_por_libro(evolucion):
    """105:RF-17 — un paso por libro del rango, que es donde se puede cancelar."""
    _ev, pasos = evolucion
    assert pasos == [(i, 5) for i in range(5)]


def test_rango_y_ambito():
    """105:RF-19, 105:RF-30 — un rango al revés no vale; muchos alimentadores no se nombran todos."""
    assert meses_del_rango('2025-11', '2026-02') == ['2025-11', '2025-12', '2026-01', '2026-02']
    with pytest.raises(ValueError):
        meses_del_rango('2026-03', '2026-02')
    assert ambito(['AL209']) == 'AL209' and ambito(['B', 'A']) == 'A+B'
    assert ambito([f'A{i}' for i in range(9)]) == 'A0+8_mas'


def test_libro_excel_con_sus_hojas_y_graficos(evolucion, tmp_path):
    """105:RF-27 — evolución, resumen, variación, cabecera, una hoja por cliente, notas y gráficos."""
    ev, _ = evolucion
    destino = escribir_libro(ev, tmp_path / 'salida' / 'libro.xlsx')
    wb = openpyxl.load_workbook(destino)
    assert wb.sheetnames == ['Evolución P máx (kW)', 'Evolución energía (MWh)', 'Evolución Q máx (kVAR)',
                             'Resumen mensual', 'Variación mes a mes (%)', 'Cabecera y fijos',
                             '222 (S2)', '900 (S1)', '555 (S5)', 'Notas']
    pmax = list(wb['Evolución P máx (kW)'].iter_rows(values_only=True))
    assert pmax[0][:5] == ('Cliente', '2026-01', '2026-02', '2026-03', '2026-05')      # abril, copia, fuera
    assert [f[0] for f in pmax[1:]] == ['222', '900', '555', 'TOTAL F1 (suma)', 'TOTAL F2 (suma)']
    assert all(len(wb[h]._charts) == 1 for h in wb.sheetnames[:3])
    resumen = list(wb['Resumen mensual'].iter_rows(values_only=True))
    obs = resumen[0].index('Observación')
    assert {f[obs] for f in resumen[1:] if f[2] == '2026-04'} == {'COPIA de 2026-03: el libro repite sus valores; no se usa'}
    serie = list(wb['900 (S1)'].iter_rows(values_only=True))
    assert serie[0] == ('Fecha', 'P (kW)', 'Q (kVAR)') and len(serie) - 1 == len(ev.series['900'][0])
    notas = ' '.join(str(f[0]) for f in wb['Notas'].iter_rows(values_only=True))
    assert '111 → 900' in notas and 'LIBRO DUDOSO' in notas
    assert not list(destino.parent.glob('.tmp-*'))


# --------------------------------------------------------------------------- archivo
@pytest.fixture()
def config_archivo(tmp_path, monkeypatch):
    ruta = tmp_path / 'config' / 'archivo.json'
    monkeypatch.setattr(ar, 'ruta_config', lambda: ruta)
    return ruta


def test_sin_carpeta_de_archivo_no_se_archiva(config_archivo, tmp_path):
    """105:RF-28 — sin `config/archivo.json` no hay ruta por defecto."""
    f = tmp_path / 'x.xlsx'
    f.write_bytes(b'1')
    assert ar.carpeta_archivo() is None
    assert ar.archivar(f, 'clientes_fijos', 'AL1', '2026-01_a_2026-02') is None


def test_guardar_y_quitar_la_carpeta(config_archivo, tmp_path):
    """105:RF-29 — se pone una carpeta existente, se rechaza otra cosa y se quita."""
    (tmp_path / 'archivo').mkdir()
    assert ar.guardar_carpeta(str(tmp_path / 'archivo')) == tmp_path / 'archivo'
    assert json.loads(config_archivo.read_text(encoding='utf-8')) == {'ruta': (tmp_path / 'archivo').as_posix()}
    with pytest.raises(ar.ArchivoError):
        ar.guardar_carpeta(str(tmp_path / 'no_existe'))
    assert ar.guardar_carpeta(None) is None and not config_archivo.exists()


def test_archivar_reemplaza_solo_el_mismo_fichero(config_archivo, tmp_path):
    """105:RF-30, 105:RF-32, 105:RF-33, 105:RF-40 — la ruta por tipo, ámbito y periodo; igual no se repite (RF-32); el mismo nombre se
    reemplaza por su versión vigente, sin copias «(2)»; los demás ficheros de la carpeta no se tocan."""
    raiz = tmp_path / 'archivo'
    raiz.mkdir()
    ar.guardar_carpeta(str(raiz))
    f = tmp_path / 'libro.xlsx'
    f.write_bytes(b'uno')
    primero = ar.archivar(f, 'clientes_fijos', 'AL209', '2026-01_a_2026-10')
    assert primero == raiz / 'informes' / 'clientes_fijos' / 'AL209' / '2026-01_a_2026-10' / 'libro.xlsx'
    assert ar.archivar(f, 'clientes_fijos', 'AL209', '2026-01_a_2026-10') == primero
    otro = primero.parent / 'hecho_a_mano.xlsx'
    otro.write_bytes(b'del usuario')
    f.write_bytes(b'dos')
    segundo = ar.archivar(f, 'clientes_fijos', 'AL209', '2026-01_a_2026-10')
    assert segundo == primero and primero.read_bytes() == b'dos'
    assert otro.read_bytes() == b'del usuario'
    assert sorted(p.name for p in primero.parent.iterdir()) == ['hecho_a_mano.xlsx', 'libro.xlsx']


def test_archivar_reintenta_un_bloqueo_y_dice_el_fallo(config_archivo, tmp_path, monkeypatch):
    """105:RF-30, 105:RF-31 — un bloqueo pasajero se reintenta; uno que no pasa es ArchivoError y no deja temporales."""
    raiz = tmp_path / 'archivo'
    raiz.mkdir()
    f = tmp_path / 'libro.xlsx'
    f.write_bytes(b'uno')
    real, fallos = os.replace, {'n': 0}

    def bloqueado(a, b):
        fallos['n'] += 1
        if fallos['n'] <= 2:
            raise PermissionError('el fichero lo usa otro proceso')
        real(a, b)

    monkeypatch.setattr(ar.os, 'replace', bloqueado)
    assert ar.archivar(f, 'clientes_fijos', 'A', 'p', raiz=raiz, espera=0).read_bytes() == b'uno'
    monkeypatch.setattr(ar.os, 'replace', lambda a, b: (_ for _ in ()).throw(PermissionError('bloqueado')))
    f.write_bytes(b'dos')
    with pytest.raises(ar.ArchivoError):
        ar.archivar(f, 'clientes_fijos', 'A', 'p', raiz=raiz, espera=0, reintentos=2)
    assert [p.name for p in (raiz / 'informes/clientes_fijos/A/p').iterdir()] == ['libro.xlsx']
    with pytest.raises(ar.ArchivoError):
        ar.archivar(f, 'clientes_fijos', 'A', 'p', raiz=tmp_path / 'desconectada')


# --------------------------------------------------------------------------- conciliación y búsqueda de códigos
from convertersmartgrid.dominio.conciliacion_clientes import (  # noqa: E402
    cadenas_de_renumeracion, fijos_sobre_cabecera, posibles_renumeraciones, veredicto)
from convertersmartgrid.evolucion_clientes import FilaMaestro, clientes_fijos, leer_maestro  # noqa: E402


def test_codigos_normalizados_y_cadenas_de_renumeracion():
    """105:RF-35 — «.0», ceros y espacios no cambian el código; A → B → C da C, en los dos sentidos."""
    canon, avisos = cadenas_de_renumeracion([('0111', '222.0'), (' 222 ', '333'), ('9', '9')])
    assert {k: canon[k] for k in ('111', '222', '333')} == {'111': '333', '222': '333', '333': '333'}
    assert not avisos
    bifurcada, bif = cadenas_de_renumeracion([('1', '2'), ('1', '3')])
    assert bif and 'varios códigos actuales' in bif[0] and bifurcada['1'] == '2'
    ciclo, aviso = cadenas_de_renumeracion([('1', '2'), ('2', '1')])
    assert ciclo['1'] == ciclo['2'] == '1' and 'ciclo' in aviso[0]


def test_veredicto_por_fuentes():
    """105:RF-34 — confirmado en dos o más, discrepa con quién dice qué, o una sola fuente."""
    v = veredicto('AL1', 'S1', {'suministros': {'alimentador': 'AL1', 'sed': 'S1'},
                                'libro de clientes 2026-10': {'alimentador': 'al1', 'sed': 'S1'}, 'red': None})
    assert (v['estado'], v['fuentes']) == ('confirmado', 2)
    v = veredicto('AL1', 'S1', {'suministros': {'alimentador': 'AL1', 'sed': 'S1'},
                                'libro de clientes 2026-10': {'alimentador': 'AL2', 'sed': 'S9'}})
    assert v['estado'] == 'discrepa' and 'dice AL2' in v['texto'] and 'SED S9' in v['texto']
    assert veredicto('AL1', 'S1', {'suministros': {'alimentador': 'AL1'}, 'otro': None})['estado'] == 'una_fuente'
    con_red = veredicto('AL1', 'S1', {'red': {'alimentador': {'AL1', 'AL3'}}, 'suministros': {'alimentador': 'AL1'}})
    assert con_red['estado'] == 'confirmado'


def test_posible_renumeracion_se_propone_sin_aplicar():
    """105:RF-36 — desaparece un código y aparece otro con el mismo CL o la misma SED: se propone."""
    presencia = {'2026-01': {'7': {'codigo': '7', 'cl': 'CL1', 'sed': 'S7'}, '8': {'codigo': '8', 'cl': '', 'sed': 'S8'}},
                 '2026-02': {'70': {'codigo': '70', 'cl': 'cl1', 'sed': ''}, '8': {'codigo': '8', 'cl': '', 'sed': 'S8'}}}
    assert posibles_renumeraciones(presencia, {'7'}) == [
        {'desaparece': '7', 'aparece': '70', 'mes': '2026-02', 'por': 'CL', 'valor': 'CL1'}]
    assert posibles_renumeraciones(presencia, {'99'}) == []          # de otro alimentador: no se propone


def _fila(codigo, alimentador, sed, nombre='x', cl=''):
    return FilaMaestro(codigo, cl, nombre, 'ED', alimentador, sed)


def test_conciliacion_de_tres_fuentes(tmp_path):
    """105:RF-34 — suministros, el resumen del libro y la red: nada por parecido de nombre."""
    sumi = _suministros(tmp_path / 's.xlsx', [('1', '10', 'S1', 'F1'), ('2', '2', 'S2', 'F1'), ('3', '3', 'S3', 'F2')])
    maestros = [('2026-01', {'1': _fila('1', 'F1', 'S1')}),
                ('2026-02', {'10': _fila('10', 'F1', 'S1'), '2': _fila('2', 'F9', 'S2'), '4': _fila('4', 'F1', 'S4'),
                             '5': _fila('5', 'F7', 'S5', nombre='Cliente de F1')})]
    fijos, conc = clientes_fijos(sumi, ['F1'], maestros, seds_red={'S1': {'F1'}, 'S2': {'F1'}})
    assert [c.codigo for c in fijos['F1']] == ['10', '2', '4']            # 5 dice «F1» en el nombre: no cuenta
    v = conc['veredictos']
    assert (v['10']['estado'], v['10']['fuentes']) == ('confirmado', 3)
    assert v['2']['estado'] == 'discrepa' and 'F9' in v['2']['texto']
    assert v['4']['estado'] == 'una_fuente' and 'no está en la red' in v['4']['texto']
    assert conc['renumeraciones'] == [{'anterior': '1', 'actual': '10', 'alimentador': 'F1', 'meses': ['2026-01']}]
    assert conc['sin_suministro'] == ['4', '5']


def test_leer_maestro_del_resumen_real(tmp_path):
    """105:RF-34, 105:RF-35 — la disposición de 2026: código como número, «nan» en el CL y el maestro aparte."""
    wb = openpyxl.Workbook()
    m = wb.active
    m.title = 'maestro_lib'
    m.append(['Referencia: maestro_lib.xlsx'])
    m.append([])
    m.append(['numero_suministro', 'numero_identificador', 'fm', 'cod_cl', 'nombre_cliente', 'suministrador'])
    m.append(['700000002', '1', '1', 'CL0002', 'Fundo Norte', 'ELECTRO'])
    r = wb.create_sheet('Resumen')
    r.append(['SPL - Exportación Pulso'])
    r.append(['Periodo', '2026-10'])
    r.append([])
    r.append(['SUMINISTRO', 'COD_CL', 'CLIENTE', 'SUMINISTRADOR', 'ALIMENTADOR', 'SUBESTACION', 'EA_TOTAL'])
    r.append([123000045.0, 'CL0003', 'Planta Sur', 'ED', 'AL1', 'SE1', 1.0])
    r.append(['700000002', 'nan', 'Fundo Norte unificado', 'ED', 'AL1', 'SE2', 1.0])
    wb.save(tmp_path / 'b.xlsx')
    d = leer_maestro(tmp_path / 'b.xlsx')
    assert d['123000045'] == FilaMaestro('123000045', 'CL0003', 'Planta Sur', 'ED', 'AL1', 'SE1')
    assert d['700000002'].cl == 'CL0002' and d['700000002'].alimentador == 'AL1'


def test_maxima_en_empate_y_q_del_mismo_instante():
    """105:RF-37 — a igual P máxima gana el primer instante, y la Q es la de ese registro."""
    t = np.array(['2026-03-01T00:15', '2026-03-01T00:30', '2026-03-01T00:45'], dtype='datetime64[m]')
    d = em.indicadores_por_mes(t[::-1], np.array([5.0, 9.0, 9.0])[::-1], np.array([1.0, 2.0, 3.0])[::-1])['2026-03']
    assert (d['fecha_p_max'], d['q_en_p_max']) == ('2026-03-01T00:30', 2.0)


def test_fijos_sobre_la_cabecera_se_avisan():
    """105:RF-38 — la suma de los fijos no puede superar la cabecera más el margen."""
    t = np.array(['2026-03-01T00:15', '2026-03-01T00:30'], dtype='datetime64[m]')
    assert fijos_sobre_cabecera(t, [100.0, 104.0], t, [100.0, 100.0], .05) is None
    sobre = fijos_sobre_cabecera(t, [100.0, 120.0], t, [100.0, 100.0], .05)
    assert sobre['registros'] == 1 and str(sobre['instante']) == '2026-03-01T00:30' and sobre['fijos_kw'] == 120.0


def test_sin_aviso_de_cabecera_si_los_fijos_caben(evolucion):
    """105:RF-38 — en el caso sintético la cabecera es la suma más 100 kW: ningún aviso."""
    ev, _ = evolucion
    assert not [a for a in ev.datos['avisos'] if a['tipo'] == 'fijos_sobre_cabecera']
