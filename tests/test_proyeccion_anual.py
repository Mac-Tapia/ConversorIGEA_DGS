"""Spec 031: pronosticar primero todos los años del PIDE, con el mejor modelo por métricas. Series sintéticas sorteadas: no son medición real."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

import numpy as np
import pytest

from convertersmartgrid import proyeccion_anual as pa
from convertersmartgrid.digital_twin.pronostico import Objetivo
from convertersmartgrid.pide import PideError, leer_proyeccion_anual
from convertersmartgrid.pronostico_demanda import CurvaCompacta, Dataset
from convertersmartgrid.proyeccion_mercado import REFERENCIA, SerieMercado, leer_formato_01

sys.path.insert(0, str(Path(__file__).parent))
from pronostico_sintetico import SEMILLA  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _curva(inicio: str, fin: str, base: float, tasa: float, semilla: int, ruido: float = .03, q: bool = False):
    """Forma diaria y semanal con la tasa anual dada: el nivel sale de la tasa y la forma no depende de ella."""
    t = np.arange(np.datetime64(inicio, 'ns'), np.datetime64(fin, 'ns'), np.timedelta64(15, 'm'))
    anios = (t - t[0]) / np.timedelta64(365, 'D')
    bloque = ((t - np.datetime64('2020-01-01', 'ns')) / np.timedelta64(15, 'm')).astype(int) % 96
    forma = 1 + .3 * np.sin(2 * np.pi * bloque / 96 - 1.2)
    rng = np.random.default_rng(SEMILLA + semilla)
    v = base * (1 + tasa) ** anios * forma * (1 + ruido * rng.standard_normal(len(t)))
    return t, v * (.3 if q else 1)


def _objetivo(clase: str, ident: str, magnitud: str, inicio: str, fin: str, base: float, tasa: float, semilla: int, alimentador: str | None = None, ruido: float = .03) -> Objetivo:
    t, v = _curva(inicio, fin, base, tasa, semilla, ruido, magnitud == 'kVAR')
    return Objetivo(clase, ident, magnitud, magnitud, CurvaCompacta(t, v), {'alimentador': alimentador} if alimentador else {})


def _dataset(tasa: float = .10, inicio: str = '2023-01-01', fin: str = '2026-01-01', ruido: float = .03, alimentadores: int | None = None) -> Dataset:
    """Cabecera, clientes y escaladas de varios alimentadores: el número sale del sorteo, no de una constante."""
    n = alimentadores if alimentadores is not None else 1 + SEMILLA % 3
    objetivos: list[Objetivo] = []
    for i in range(n):
        f = f'F{i}'
        for j, m in enumerate(('kW', 'kVAR')):
            objetivos.append(_objetivo('cabecera', f, m, inicio, fin, 3000.0 + 100 * i, tasa, 10 * i + j, ruido=ruido))
            objetivos.append(_objetivo('escaladas', f, m, inicio, fin, 2000.0 + 100 * i, tasa, 20 * i + j, ruido=ruido))
            objetivos.append(_objetivo('cliente', f'C{i}', m, inicio, fin, 1000.0, tasa, 30 * i + j, alimentador=f, ruido=ruido))
    return Dataset(objetivos, [], [], {})


def _plan(ref, proyecto='P', corto=4, fin=7, base=2026, feeders=None) -> dict:
    return {'project': proyecto, 'feeders': feeders or ['F0', 'F1', 'F2'], 'anio_fin': fin, 'corto_plazo': {'anio': corto, 'anio_base': base}, 'proyeccion_anual': ref}


@pytest.fixture(scope='module')
def crece():
    d = _dataset()
    return d, pa.competir(d, paso_meses=3)


# ------------------------------------------------------------------ T1
def test_competicion_todos_en_los_mismos_origenes_con_sus_metricas(crece):
    """031:RF-2, 031:RF-3 — referencias, métodos anuales y de la 089 en cada clase y magnitud, con WAPE, RMSE, sesgo y máxima a cada horizonte."""
    _d, c = crece
    assert set(c['grupos']) == {'cliente|kW', 'cliente|kVAR', 'escaladas|kW', 'escaladas|kVAR'}
    grupo = c['grupos']['escaladas|kW']
    evaluados = {n: e for n, e in grupo['candidatos'].items() if 'eleccion' in e}
    assert {'tasa_de_un_anio', 'sin_crecimiento', 'perfil_anclado', 'semanal', 'perfil_calendario'} <= set(evaluados)
    assert len({e['eleccion']['n'] for e in evaluados.values()}) == 1, 'los mismos datos y los mismos orígenes para todos'
    assert grupo['origenes_eleccion'] and grupo['origen_prueba'] not in grupo['origenes_eleccion']
    for e in evaluados.values():
        for m in ('wape', 'rmse_relativo', 'sesgo', 'error_maxima'):
            assert m in e['eleccion'] and m in e['prueba'] and all(m in x for x in e['por_horizonte_meses'].values()) and all(m in x for x in e['por_anio'].values())
    assert len(evaluados['tasa_de_un_anio']['por_horizonte_meses']) >= 12, 'cada horizonte que los datos permiten'


def test_eleccion_gana_quien_debe_por_las_metricas(crece):
    """031:RF-4 — con una tendencia real gana un método con crecimiento, nunca «sin crecimiento» ni los planos."""
    _d, c = crece
    for g in c['grupos'].values():
        assert g['status'] == 'EVALUADO'
        assert g['ganador'] in ('tasa_de_un_anio', 'tasa_media', 'tendencia_logaritmica'), g['motivo']


def test_eleccion_sin_mejora_gana_la_referencia():
    """031:RF-4 — si ninguno mejora a la referencia por la puerta declarada, gana la referencia."""
    medida = {'wape': .10, 'error_maxima': .05}
    assert pa.elegir({REFERENCIA: medida, 'otro': {'wape': .099, 'error_maxima': .05}}, REFERENCIA)[0] == REFERENCIA, 'un 1 % no pasa la puerta del 2 %'
    assert pa.elegir({REFERENCIA: medida, 'otro': {'wape': .05, 'error_maxima': .06}}, REFERENCIA)[0] == REFERENCIA, 'empeora la máxima'
    assert pa.elegir({REFERENCIA: medida, 'otro': {'wape': .05, 'error_maxima': .05}}, REFERENCIA)[0] == 'otro'
    d = _dataset(tasa=.10, inicio='2024-01-01', alimentadores=1)  # con dos años, la tasa media es la de un año: un empate no desplaza a la referencia
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'tasa_media', 'sin_crecimiento'], paso_meses=3, clases=['escaladas'])
    assert c['grupos']['escaladas|kW']['ganador'] == REFERENCIA, c['grupos']['escaladas|kW']['motivo']


def test_eleccion_la_regla_se_declara_antes_y_no_mira_la_prueba():
    """031:RF-4 — cambiar lo ocurrido tras el origen de prueba no cambia al ganador ni sus medidas de elección."""
    assert pa.REGLA['mejora_minima'] > 0 and pa.REGLA['referencia'] == REFERENCIA
    d = _dataset(alimentadores=1)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento', 'perfil_anclado'], paso_meses=3, clases=['escaladas'])
    assert c['regla'] == pa.REGLA
    g = c['grupos']['escaladas|kW']
    corte = np.datetime64(g['origen_prueba'], 'M') + 1
    alterados = []
    for o in d.objetivos:
        v = o.curva.columnas[0].copy()
        v[o.curva.t >= corte.astype('datetime64[ns]')] *= 3.0
        alterados.append(Objetivo(o.clase, o.ident, o.magnitud, o.unidad, CurvaCompacta(o.curva.t, v), o.fuente))
    c2 = pa.competir(Dataset(alterados, [], [], {}), candidatos=['tasa_de_un_anio', 'sin_crecimiento', 'perfil_anclado'], paso_meses=3, clases=['escaladas'])
    g2 = c2['grupos']['escaladas|kW']
    assert g2['ganador'] == g['ganador']
    assert g2['candidatos'][g['ganador']]['eleccion'] == g['candidatos'][g['ganador']]['eleccion']
    assert g2['candidatos'][g['ganador']]['prueba'] != g['candidatos'][g['ganador']]['prueba']


def test_competicion_modelo_sin_gpu_no_disponible_y_los_demas_siguen():
    """031:RF-2 — una red sin GPU se dice y no se lleva a los demás; un modelo disponible compite igual."""
    class Eco:
        def ajustar(self, objetivos, hasta, pasos, exogenas, semilla):
            pass

        def predecir_todos(self, objetivos, hasta, pasos, exogenas):
            futuro = pa.malla(hasta, hasta + np.timedelta64(pasos * 15, 'm'))
            return {o.nombre: np.full(len(futuro), float(np.median(o.curva.columnas[0]))) for o in objetivos}

    def fabrica(nombre, **_a):
        if nombre == 'nhits':
            raise RuntimeError('sin GPU')
        return Eco()

    d = _dataset(alimentadores=1)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], modelos=['nhits', 'eco'], paso_meses=6, clases=['escaladas'], fabrica=fabrica)
    g = c['grupos']['escaladas|kW']
    assert g['candidatos']['nhits']['status'] == 'NO_DISPONIBLE' and 'GPU' in g['candidatos']['nhits']['motivo']
    assert 'eleccion' in g['candidatos']['eco']


def test_competicion_formato_01_propio_mide_varios_anios_y_el_ajeno_no_se_usa():
    """031:RF-8 — el histórico de la empresa mide varios años; el de otra empresa u otro sistema no entra."""
    hist = {2010 + i: 100.0 * 1.04 ** i for i in range(10)}
    propia = SerieMercado('S1', 'Sistema Uno', 'ST2', hist, empresa='Empresa A')
    ajena = SerieMercado('S1', 'Sistema Uno', 'ST2', hist, empresa='Empresa B')
    otro = SerieMercado('S9', 'Otro', 'ST2', hist, empresa='Empresa A')
    series, notas = pa.formato_01_propio([propia, ajena, otro], empresa='Empresa A', sistemas=['S1'])
    assert series == [propia] and len(notas) == 2
    assert not pa.formato_01_propio([propia], empresa=None)[0], 'sin saber de quién es, no se usa'
    medido = pa.medir_formato_01(series)
    assert medido['usado'] and medido['anios_validados'] >= 2
    assert medido['por_anio']['tasa_de_un_anio']['2']['n'] >= 2
    assert not pa.medir_formato_01([SerieMercado('S', 'S', 'ST2', {2024: 1.0, 2025: 2.0}, empresa='A')])['usado'], 'dos años no dan para cortar'


def test_competicion_determinista_y_sin_nombres_fijos():
    """031:RF-13, 031:RF-14 — mismos datos y semilla, mismo resultado; ninguna empresa, año, libro ni ruta en el código."""
    d = _dataset(alimentadores=1)
    uno = pa.competir(d, candidatos=['tasa_de_un_anio', 'perfil_anclado'], paso_meses=6, semilla=3, clases=['cliente'])
    dos = pa.competir(d, candidatos=['tasa_de_un_anio', 'perfil_anclado'], paso_meses=6, semilla=3, clases=['cliente'])
    assert json.dumps(uno, sort_keys=True) == json.dumps(dos, sort_keys=True)
    for rel in ('src/convertersmartgrid/proyeccion_anual.py', 'tools/proyeccion_anual.py'):
        fuente = (RAIZ / rel).read_text(encoding='utf-8')
        assert not re.search(r'electro|dunas|pisco|osinergmin|\.xlsx?\b(?!\')', fuente.replace('formato_01_construido.xlsx', ''), re.I)
        assert not re.search(r'\b20[0-9]{2}\b', fuente.replace('--anio-base 2030', ''))
        assert 'powerfactory' not in fuente.lower() and 'pf_arnes' not in fuente, '031:RF-14: nada de DIgSILENT'


# ------------------------------------------------------------------ T6
@pytest.fixture
def incompleto():
    """Un año entero y el siguiente hasta octubre, con el 5 % de crecimiento: lo que traen los libros reales."""
    objetivos = []
    for i in range(2):
        f = f'F{i}'
        objetivos.append(_objetivo('cabecera', f, 'kW', '2025-01-01', '2026-11-01', 2000.0 + i, .05, i))
    # Un alimentador que solo aparece el segundo año: sumarlo en uno y no en el otro sería un crecimiento falso.
    objetivos.append(_objetivo('cabecera', 'NUEVO', 'kW', '2026-01-01', '2026-11-01', 5000.0, 0.0, 9))
    return objetivos


def test_formato_diez_meses_contra_doce_no_es_una_caida(incompleto, tmp_path):
    """031:RF-15, 031:RF-8 — el lector ve los mismos meses y alimentadores; cada año va marcado y ninguno pasa por entero si no lo es."""
    tablas = pa.formato_01_de_cabecera(incompleto, sistema_de={'F0': 'S1', 'F1': 'S1', 'NUEVO': 'S1'}, sistemas={'S1': {'nombre': 'Sistema Uno', 'sector': '2'}}, empresa='Empresa A')
    ruta = pa.escribir_formato_01(tmp_path / 'f01.xlsx', tablas)
    leidas = leer_formato_01(ruta)
    assert len(leidas) == 1 and leidas[0].codigo == 'S1' and leidas[0].nombre == 'Sistema Uno' and leidas[0].sector == 'ST2' and leidas[0].empresa == 'Empresa A'
    h = leidas[0].historico
    assert set(h) == {2025, 2026} and h[2026] / h[2025] == pytest.approx(1.05, abs=.01), 'crece el 5 %: ni la caída de 10 contra 12 ni el salto del alimentador nuevo'
    meses = pa.leer_meses_formato_01(ruta)['S1']
    assert not meses[2025]['completo'], 'sus 12 meses, pero sin un alimentador del sistema'
    assert not meses[2026]['completo'] and meses[2026]['meses'] == list(range(1, 11))
    assert meses[2025]['alimentadores'] == ['F0', 'F1'] and meses[2026]['alimentadores'] == ['F0', 'F1', 'NUEVO'] and meses[2026]['alimentadores_del_sistema'] == 3
    assert meses[2026]['mwh_medidos'] > meses[2026]['mwh_comparados'] > 0, 'lo medido se ve en su propia columna'
    assert 'no es el año entero' in meses[2026]['base'] and 'de 2 de 3 alimentadores' in meses[2026]['base']
    assert meses[2026]['tasa_pct'] == pytest.approx(5.0, abs=1.0)
    assert meses[2026]['meses_comparados'] == meses[2025]['meses_comparados'] == list(range(1, 11))


def test_formato_un_unico_anio_incompleto_no_se_presenta(tmp_path):
    """031:RF-15 — sin otro año con que compararlo, un año incompleto no da un histórico que parezca un año entero."""
    o = _objetivo('cabecera', 'F0', 'kW', '2026-01-01', '2026-11-01', 1000.0, 0.0, 0)
    ruta = pa.escribir_formato_01(tmp_path / 'f.xlsx', pa.formato_01_de_cabecera([o], sistema_de={'F0': 'S1'}, empresa='E'))
    from convertersmartgrid.proyeccion_mercado import MercadoError
    with pytest.raises(MercadoError):
        leer_formato_01(ruta)
    assert 'sin otro con que compararlo' in pa.leer_meses_formato_01(ruta)['S1'][2026]['base']


def test_formato_una_hoja_por_sistema_y_anios_enteros_comparables(tmp_path):
    """031:RF-15 — cada sistema con los suyos, y con años enteros el lector ve los dos."""
    objetivos = [_objetivo('cabecera', 'F0', 'kW', '2024-01-01', '2026-01-01', 1000.0, .10, 0), _objetivo('cabecera', 'F1', 'kW', '2024-01-01', '2026-01-01', 900.0, .0, 1),
                 _objetivo('cabecera', 'SIN', 'kW', '2024-01-01', '2026-01-01', 900.0, .0, 2)]
    tablas = pa.formato_01_de_cabecera(objetivos, sistema_de={'F0': 'S1', 'F1': 'S2'}, empresa='E')
    assert [t.codigo for t in tablas] == ['S1', 'S2'], 'un alimentador sin sistema no se cuela en ninguno'
    leidas = {s.codigo: s for s in leer_formato_01(pa.escribir_formato_01(tmp_path / 'f.xlsx', tablas))}
    assert leidas['S1'].historico[2025] / leidas['S1'].historico[2024] == pytest.approx(1.10, abs=.02)
    assert leidas['S2'].historico[2025] / leidas['S2'].historico[2024] == pytest.approx(1.0, abs=.02)


def test_formato_mes_sin_registros_suficientes_no_cuenta():
    """031:RF-15 — un mes con menos de la mitad de sus registros no es un mes medido, y el año no pasa por entero."""
    t, v = _curva('2025-01-01', '2026-01-01', 1000.0, 0.0, 1)
    hueco = (t >= np.datetime64('2025-06-01', 'ns')) & (t < np.datetime64('2025-06-25', 'ns'))
    o = Objetivo('cabecera', 'F0', 'kW', 'kW', CurvaCompacta(t[~hueco], v[~hueco]))
    a = pa.formato_01_de_cabecera([o], sistema_de={'F0': 'S1'}, empresa='E')[0].anios[0]
    assert 6 not in a.meses and not a.completo


def test_formato_el_crecimiento_del_grupo_compara_mismas_series_y_meses():
    """031:RF-15 — diez meses contra doce no son una caída, y un cliente nuevo no es crecimiento; el valor anual usa lo común."""
    uno = pa._serie(_objetivo('cliente', 'A', 'kW', '2025-01-01', '2026-11-01', 1000.0, 0.0, 1, ruido=0.0))
    nuevo = pa._serie(_objetivo('cliente', 'B', 'kW', '2026-01-01', '2026-11-01', 9000.0, 0.0, 2, ruido=0.0))
    hist = pa.historia_del_grupo([uno, nuevo])['media']
    assert set(hist) == {2025, 2026} and hist[2026] / hist[2025] == pytest.approx(1.0, abs=.001)
    corte = (2026 - 1970) * 12 + 2
    visible = pa.historia_del_grupo([uno, nuevo], corte)['media']
    assert visible[2026] / visible[2025] == pytest.approx(1.0, abs=.001), 'solo lo visible en el origen'


def test_competicion_el_crecimiento_es_del_grupo_y_no_explota_con_un_escalon():
    """031:RF-5, 031:RF-13 — una serie con un escalón no multiplica su demanda: medido en un caso real, una daba cifras sin sentido a 20 años."""
    objetivos = []
    for m in ('kW', 'kVAR'):
        objetivos.append(_objetivo('cliente', 'NORMAL', m, '2024-01-01', '2026-11-01', 1000.0, .03, 1, alimentador='F'))
        t, v = _curva('2024-01-01', '2026-11-01', 100.0, .03, 2, q=m == 'kVAR')
        v[t >= np.datetime64('2026-01-01', 'ns')] *= 8
        objetivos.append(Objetivo('cliente', 'ESCALON', m, m, CurvaCompacta(t, v), {'alimentador': 'F'}))
    d = Dataset(objetivos, [], [], {})
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=3)
    pro, _ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=20)
    p = {(f['carga'], f['anio']): f['p_kw'] for f in pro['filas']}
    assert p[('cliente:ESCALON', 20)] / p[('cliente:ESCALON', 5)] == pytest.approx(p[('cliente:NORMAL', 20)] / p[('cliente:NORMAL', 5)], rel=1e-3), 'el mismo crecimiento'


def test_competicion_sin_crecimiento_se_distingue_de_la_tasa():
    """031:RF-2 — repetir el último valor no es lo mismo que la tasa: con dos años, si lo fuera, la competición no mediría nada."""
    d = _dataset(tasa=.10, inicio='2025-01-01', fin='2026-11-01', alimentadores=1)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=1, clases=['escaladas'])
    g = c['grupos']['escaladas|kW']['candidatos']
    assert g['tasa_de_un_anio']['eleccion']['wape'] < g['sin_crecimiento']['eleccion']['wape']


# ------------------------------------------------------------------ T2
@pytest.fixture(scope='module')
def emitida(crece):
    d, c = crece
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=7)
    return d, c, pro, ev


def test_emision_todos_los_anios_con_banda_y_sin_negativas(emitida):
    """031:RF-5 — P y Q de cada carga en cada año, en valores absolutos, con su banda medida y ninguna P negativa."""
    d, _c, pro, _ev = emitida
    cargas = {f['carga'] for f in pro['filas']}
    assert {f['anio'] for f in pro['filas']} == {5, 6, 7} and {f['anio'] for f in pro['filas_corto_plazo']} == {1, 2, 3, 4}
    assert len(pro['filas']) == 3 * len(cargas) and len(cargas) == sum(o.clase in pa.CLASES and o.magnitud == 'kW' for o in d.objetivos)
    for f in (*pro['filas'], *pro['filas_corto_plazo']):
        assert f['p_kw'] >= 0 and f['p_q05_kw'] >= 0 and f['p_q05_kw'] <= f['p_q95_kw'] and f['q_q05_kvar'] <= f['q_q95_kvar']
        assert np.isfinite(f['q_kvar']) and f['modelo_p'] and f['modelo_q'] and f['instante_base']
    por = {(f['carga'], f['anio']): f['p_kw'] for f in pro['filas']}
    alguna = next(iter(cargas))
    assert por[(alguna, 7)] > por[(alguna, 5)], 'la demanda sigue la tendencia ganadora'


def test_emision_banda_de_los_errores_medidos():
    """031:RF-5 — más ruido medido, banda más ancha; sin errores medidos no se inventa."""
    grupo = {'banda': {'1': {'q05': -.1, 'q95': .2, 'n': 50}}}
    assert pa._banda_de(grupo, 1) == (-.1, .2, False)
    q05, q95, extrapolada = pa._banda_de(grupo, 4)
    assert extrapolada and q05 == pytest.approx(-.2) and q95 == pytest.approx(.4), 'más allá de lo medido se abre, y lo dice'
    assert pa._banda_de({'banda': {'1': {'q05': -.1, 'q95': .2, 'n': 2}}}, 1) is None
    assert pa._limites(10.0, None) == (None, None)


def test_emision_horizonte_validado_separado_y_honesto(emitida):
    """031:RF-6 — lo pronosticado y lo validado van aparte; un año sin validar no se presenta como validado."""
    _d, _c, pro, ev = emitida
    assert ev['horizonte_anios'] == 7 and 'horizonte_validado_anios' in ev and ev['horizonte_validado_anios'] <= 2, 'tres años de datos no validan siete'
    assert all(f['validado'] == (f['anios_adelante'] <= ev['horizonte_validado_anios']) for f in (*pro['filas'], *pro['filas_corto_plazo']))
    assert not any(f['validado'] for f in pro['filas'])


def test_emision_22_meses_validan_como_mucho_un_anio():
    """031:RF-6 — con menos de dos años de medición no se puede validar más de uno, y un candidato que no llega a 12 meses no valida ninguno."""
    d = _dataset(inicio='2025-01-01', fin='2026-11-01', alimentadores=1)
    c = pa.competir(d, paso_meses=2, clases=['escaladas', 'cliente'])
    for g in c['grupos'].values():
        v = g['validacion']
        assert v['anios'] <= 1 and v['meses'] <= 21
    _pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=20)
    assert ev['horizonte_anios'] == 20 and ev['horizonte_validado_anios'] <= 1 and ev['estado'] == 'sin_aceptar'
    assert ev['aceptacion']['anios_sin_validar'] >= 19


@pytest.mark.parametrize('validado,horizonte,orden,estado,via', [
    (1, 20, None, 'sin_aceptar', None),
    (1, 20, {'operador': 'J. Pérez', 'motivo': 'decisión del estudio'}, 'aceptado', 'orden_operador'),
    (20, 20, None, 'aceptado', 'validacion_completa'),
])
def test_contrato_aceptacion_dice_cual(validado, horizonte, orden, estado, via):
    """031:RF-7 — aceptado por orden expresa o por validación completa, y dice cuál; la orden no oculta lo que falta."""
    e, a = pa.aceptacion(validado, horizonte, orden)
    assert (e, a['via']) == (estado, via) and a['anios_sin_validar'] == horizonte - validado


def test_contrato_orden_sin_operador_no_vale():
    """031:RF-7 — una orden sin quién la da no acepta nada."""
    with pytest.raises(pa.ProyeccionError):
        pa.aceptacion(1, 20, {'operador': ' '})


def test_contrato_el_lector_acepta_solo_con_aceptacion(crece, tmp_path):
    """031:RF-9, 031:RF-7 — ``leer_proyeccion_anual`` lee lo emitido; sin aceptar lo rechaza, y su comprobación sigue intacta."""
    d, c = crece
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=7)
    ref = pa.escribir_proyeccion(tmp_path / 'sin', pro, ev)
    with pytest.raises(PideError, match='evaluación aceptada'):
        leer_proyeccion_anual(_plan(ref))
    pro2, ev2 = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=7, orden={'operador': 'J. Pérez', 'fecha': 'hoy'})
    ref2 = pa.escribir_proyeccion(tmp_path / 'con', pro2, ev2)
    leida = leer_proyeccion_anual(_plan(ref2))
    assert set(leida['por_anio']) == {5, 6, 7} and all(leida['por_anio'].values())
    assert ev2['aceptacion']['operador'] == 'J. Pérez' and ev2['aceptacion']['anios_sin_validar'] > 0
    assert ev2['horizonte_validado_anios'] == ev['horizonte_validado_anios'], 'aceptar no cambia lo validado'
    with pytest.raises(PideError):
        leer_proyeccion_anual(_plan(ref2, proyecto='OTRO'))
    with pytest.raises(PideError):
        leer_proyeccion_anual(_plan(ref2, fin=8))
    with pytest.raises(PideError):
        leer_proyeccion_anual(_plan(ref2, base=2025))
    with pytest.raises(PideError, match='huella'):
        leer_proyeccion_anual(_plan({**ref2, 'sha256': 'a' * 64}))


def test_contrato_validacion_completa_acepta_sola():
    """031:RF-7 — un horizonte validado por entero queda aceptado por validación, sin orden."""
    d = _dataset(alimentadores=1)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=3)
    _p, ev = pa.proyectar(d, c, proyecto='P', anio_base=2025, anio_corto=1, anio_fin=2)
    if ev['horizonte_validado_anios'] >= ev['anios_a_validar']:
        assert ev['estado'] == 'aceptado' and ev['aceptacion']['via'] == 'validacion_completa'
    else:
        assert ev['estado'] == 'sin_aceptar'


def test_emision_reparto_por_potencia_y_lo_anota(crece):
    """031:RF-12 — una carga sin serie propia se reparte con la de su alimentador por potencia instalada, y lo anota; la propia va con la suya."""
    d, c = crece
    cargas = [pa.Carga('\\P\\SED1.ElmLod', 'F0', 100.0), pa.Carga('\\P\\SED2.ElmLod', 'F0', 300.0), pa.Carga('\\P\\CLI.ElmLod', 'F0', 50.0, 'C0'),
              pa.Carga('\\P\\SIN_KVA.ElmLod', 'F0', None), pa.Carga('\\P\\OTRA.ElmLod', 'NO_EXISTE', 80.0)]
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5, cargas=cargas)
    por = {f['carga']: f for f in pro['filas']}
    assert por['\\P\\SED2.ElmLod']['p_kw'] == pytest.approx(3 * por['\\P\\SED1.ElmLod']['p_kw'], rel=1e-3)
    assert 'potencia instalada' in por['\\P\\SED1.ElmLod']['reparto'] and por['\\P\\SED1.ElmLod']['clase'] == 'escaladas'
    assert 'reparto' not in por['\\P\\CLI.ElmLod'] and por['\\P\\CLI.ElmLod']['clase'] == 'cliente' and por['\\P\\CLI.ElmLod']['objetivo'] == 'cliente:C0:kW'
    apartadas = {a['carga'] for a in ev['cargas_apartadas']}
    assert apartadas == {'\\P\\SIN_KVA.ElmLod', '\\P\\OTRA.ElmLod'} and not apartadas & set(por), 'ninguna fila imputada'


def test_emision_base_coincidente_con_la_maxima_del_alimentador():
    """031:RF-5 — la base es lo medido en la máxima de su alimentador, para que la suma cuadre con la cabecera y sin rellenar nada."""
    t, v = _curva('2025-01-01', '2026-01-01', 1000.0, 0.0, 3)
    cab = pa._serie(Objetivo('cabecera', 'F', 'kW', 'kW', CurvaCompacta(t, v)))
    instantes = pa._instantes_de_maxima(cab)
    assert instantes[0] == t[np.argmax(v)]
    otra = pa._serie(Objetivo('cliente', 'C', 'kW', 'kW', CurvaCompacta(t[::2], v[::2] / 2)))
    valor, instante, base = pa._base(otra, instantes)
    i = np.flatnonzero(t == np.datetime64(instante))[0]
    assert valor == pytest.approx(v[i] / 2) and 'coincidente' in base


def test_emision_determinista_y_q_negativa_permitida(crece):
    """031:RF-14 — mismos datos, mismas filas. La Q puede ser negativa por los bancos: lo negativo vetado es la P."""
    d, c = crece
    uno = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=6)
    dos = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=6)
    assert json.dumps(uno, sort_keys=True, default=str) == json.dumps(dos, sort_keys=True, default=str)
    t, v = _curva('2023-01-01', '2026-01-01', 500.0, 0.0, 4)
    objetivos = [Objetivo('escaladas', 'F', 'kW', 'kW', CurvaCompacta(t, v)), Objetivo('escaladas', 'F', 'kVAR', 'kVAR', CurvaCompacta(t, -.2 * v))]
    ds = Dataset(objetivos, [], [], {})
    c2 = pa.competir(ds, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=6)
    pro, _ev = pa.proyectar(ds, c2, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5)
    assert all(f['q_kvar'] < 0 and f['p_kw'] > 0 for f in pro['filas'])
    assert c2['grupos']['escaladas|kVAR']['candidatos']['tasa_de_un_anio']['status'] == 'NO_APLICA', 'una Q negativa no da tasa'


def test_emision_sin_clientes_se_proyecta_el_alimentador_entero():
    """031:RF-12 — sin libros de clientes no hay escaladas: se reparte la cabecera y la fila lo dice."""
    objetivos = [_objetivo('cabecera', 'F', m, '2023-01-01', '2026-01-01', 2000.0, .05, i) for i, m in enumerate(('kW', 'kVAR'))]
    d = Dataset(objetivos, [], [], {})
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=6)
    assert 'cabecera|kW' in c['grupos']
    pro, _ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5, cargas=[pa.Carga('\\P\\A.ElmLod', 'F', 10.0), pa.Carga('\\P\\B.ElmLod', 'F', 30.0)])
    filas = {f['carga']: f for f in pro['filas']}
    assert filas['\\P\\B.ElmLod']['p_kw'] == pytest.approx(3 * filas['\\P\\A.ElmLod']['p_kw'], rel=1e-3)
    assert 'cabecera' in filas['\\P\\A.ElmLod']['reparto'] and filas['\\P\\A.ElmLod']['clase'] == 'escaladas'


def test_emision_cola_del_formato_01_propio():
    """031:RF-8 — con Formato 01 propio, los años siguientes usan su método medido y validan lo que ese histórico mida."""
    hist = {2010 + i: 100.0 * 1.04 ** i for i in range(15)}
    serie = SerieMercado('S1', 'Uno', 'ST2', hist, empresa='E')
    d = _dataset(alimentadores=1)
    c = pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=6, formato_01=[serie])
    assert c['formato_01']['usado'] and c['formato_01']['anios_validados'] >= 5
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=2, anio_fin=5, sistema_de={'F0': 'S1'}, formato_01=[serie])
    por = {(f['carga'], f['anio']): f for f in pro['filas']}
    assert por[('escaladas:F0', 5)]['p_kw'] / por[('escaladas:F0', 4)]['p_kw'] == pytest.approx(1.04, abs=.002)
    assert 'Formato 01' in por[('escaladas:F0', 5)]['nota']
    assert ev['horizonte_validado_anios'] >= 1


# ------------------------------------------------------------------ T3
def test_obras_leen_la_proyeccion_aceptada_y_sin_ella_la_tasa_del_perfil(crece, tmp_path):
    """031:RF-11 — con proyección aceptada, su tasa; sin ella o sin aceptar, la del perfil, y lo dice."""
    d, c = crece
    carpeta = tmp_path / 'p'
    sin = pa.tasa_de_alcance(carpeta, 'P', ['F0'], .03)
    assert sin['tasa'] == .03 and sin['origen'] == 'perfil' and 'tasa del perfil' in sin['aviso']
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=7)
    pa.fijar_vigente(carpeta, pa.escribir_proyeccion(carpeta, pro, ev))
    assert pa.tasa_de_alcance(carpeta, 'P', ['F0'], .03)['origen'] == 'perfil', 'sin aceptar no vale aunque esté vigente'
    pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=7, orden={'operador': 'J. Pérez'}, tasa_cola=.10)
    pa.fijar_vigente(carpeta, pa.escribir_proyeccion(carpeta, pro, ev))
    con = pa.tasa_de_alcance(carpeta, 'P', ['F0'], .03)
    assert con['origen'] == 'proyeccion_aceptada' and con['tasa'] == pytest.approx(.10, abs=.03) and 'proyección aceptada' in con['aviso']
    assert pa.tasa_de_alcance(carpeta, 'OTRO', ['F0'], .03)['origen'] == 'perfil', 'la de otro proyecto no vale'
    assert pa.tasa_de_alcance(carpeta, 'P', ['NINGUNO'], .03)['origen'] == 'perfil'
    (carpeta / 'proyeccion.json').write_text('{}', encoding='utf-8')
    assert pa.tasa_de_alcance(carpeta, 'P', ['F0'], .03)['origen'] == 'perfil', 'una huella rota no se usa'


def test_obras_los_tres_sitios_del_alcance_pasan_por_la_proyeccion():
    """031:RF-11 — el alcance de las obras y el año en que vuelve a fallar leen la misma tasa, no la del perfil directamente."""
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert 'plan_de_corto_plazo(f, p.tasa_largo_plazo' not in fuente
    assert "alt['tasa_horizonte'] = p.tasa_largo_plazo" not in fuente
    assert 'tasa, horizonte = p.tasa_largo_plazo' not in fuente
    assert fuente.count('_tasa_de_alcance(ws, project, f, p.tasa_largo_plazo)') == 3


def test_pide_pronostica_primero_antes_de_abrir_los_casos(tmp_path, monkeypatch):
    """031:RF-1 — el pronóstico corre antes del guion de los años; sin aceptar, no cambia la tasa del estudio y lo dice."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as cliente:
        wid = cliente.post('/api/workspaces', json={'name': 'p'}).json()['id']
        ws = cliente.app.state.store.get(wid)
        orden: list[str] = []
        planes: list[dict] = []
        perfil = {'planificacion': {'crecimiento_demanda_anual': .03, 'tasa_regulada': .12, 'vida_util_anios': 30, 'anios_horizonte': [4, 8], 'anios_pide': [4]},
                  'estudios': {'tension_min_pu': .95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}, 'empresa': 'E'}
        monkeypatch.setattr(services, 'native_action_context', lambda _ws, project, feeders, action: {'feeders': ['F0'], 'project': project})
        monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda *a, **k: perfil)
        monkeypatch.setattr('convertersmartgrid.perfil_empresa.estructura_empresa', lambda *a, **k: None)
        monkeypatch.setattr(services, '_fuentes_de_demanda', lambda _ws, _f: object())

        def guion(_ws, _ctx, _nombre, plan, **_k):
            orden.append('guion')
            planes.append(plan)
            return 0, {'anios': [], 'error': 'parar aquí'}, tmp_path / 'pide.json'

        monkeypatch.setattr(services, '_guion_pf', guion)

        def proceso(_ctx, _avisos, _que, fn, *_a, **k):
            orden.append('pronostico')
            assert fn is pa.pronosticar_estudio and k['anio_fin'] == 20 and k['anio_corto'] == 4 and k['anio_base'] == 2030
            return {'referencia': {'ruta': 'x', 'sha256': 'y'}}

        monkeypatch.setattr(services, '_en_proceso_con_reintento', proceso)

        class Ctx:
            def log(self, _m):
                pass

        with pytest.raises(services.UserError, match='parar aquí'):
            services.pide_ejecutar(ws, Ctx(), 'P', ['F0'], implementar=False, anio_presentacion=2031)
        assert orden == ['pronostico', 'guion'], 'primero el pronóstico'
        assert planes[0]['tasa'] == .03, 'sin aceptar, lo ya entregado no cambia'


def test_pide_usa_la_proyeccion_aceptada_en_cada_anio(crece, tmp_path, monkeypatch):
    """031:RF-1, 031:RF-6, 031:RF-7, 031:RF-11 — aceptada, la tasa de cada alimentador sale de ella y los avisos dicen lo validado y lo pronosticado."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app

    d, c = crece
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as cliente:
        wid = cliente.post('/api/workspaces', json={'name': 'p'}).json()['id']
        ws = cliente.app.state.store.get(wid)
        carpeta = services._carpeta_de_proyeccion(ws, 'P')
        pro, ev = pa.proyectar(d, c, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=7, orden={'operador': 'J. Pérez'}, tasa_cola=.10)
        pa.fijar_vigente(carpeta, pa.escribir_proyeccion(carpeta, pro, ev))
        avisos: list[str] = []
        tasas = services._pronostico_primero(ws, None, 'P', ['F0'], None, {}, avisos)
        assert set(tasas) == {'F0'} and tasas['F0'] == pytest.approx(.10, abs=.03)
        assert 'pronosticados 7 años' in avisos[0] and f"validados contra lo ocurrido {ev['horizonte_validado_anios']}" in avisos[0] and 'orden_operador' in avisos[0]
        alcance = services._tasa_de_alcance(ws, 'P', 'F0', .03)
        assert alcance['origen'] == 'proyeccion_aceptada'


def test_pide_sin_libros_ni_estudio_sigue_con_la_tasa_y_lo_dice(tmp_path, monkeypatch):
    """031:RF-1, 031:RF-11 — sin año de presentación o sin libros no se pronostica ni se para: se dice."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as cliente:
        wid = cliente.post('/api/workspaces', json={'name': 'p'}).json()['id']
        ws = cliente.app.state.store.get(wid)
        avisos: list[str] = []
        assert services._pronostico_primero(ws, None, 'P', ['F0'], None, {}, avisos) is None and '031:RF-1' in avisos[-1]
        estudio = type('E', (), {'anio_base': 2030, 'largo_plazo': (4, 8)})()
        assert services._pronostico_primero(ws, None, 'P', ['F0'], estudio, {}, avisos) is None and 'libros' in avisos[-1]


def test_pide_lo_ya_pronosticado_no_se_repite(crece, tmp_path):
    """031:RF-1, 031:RF-14 — con los mismos datos y lo mismo pedido, se devuelve lo emitido: leer los libros cuesta horas."""
    d, _c = crece
    d = Dataset(d.objetivos, [], [], {}, huella='a' * 64)
    uno = pa.pronosticar_estudio(None, carpeta=tmp_path, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5, dataset=d, paso_meses=6)
    assert not uno['reutilizada'] and uno['evaluacion']['estado'] == 'sin_aceptar'
    dos = pa.pronosticar_estudio(None, carpeta=tmp_path, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5, dataset=d, paso_meses=6)
    assert dos['reutilizada'] and dos['referencia'] == uno['referencia']
    tres = pa.pronosticar_estudio(None, carpeta=tmp_path, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5, dataset=d, paso_meses=6, orden={'operador': 'J. Pérez'})
    assert not tres['reutilizada'] and tres['evaluacion']['estado'] == 'aceptado'
    assert pa.proyeccion_aceptada(tmp_path, 'P') is not None, 'aceptada queda vigente'


def test_pide_construye_el_formato_01_si_la_empresa_no_lo_tiene(crece, tmp_path):
    """031:RF-15, 031:RF-13 — sin Formato 01, se construye con la cabecera y se dice en la evaluación."""
    d, _c = crece
    ds = Dataset(d.objetivos, [], [], {}, huella='b' * 64)
    hecho = pa.pronosticar_estudio(None, carpeta=tmp_path, proyecto='P', anio_base=2026, anio_corto=4, anio_fin=5, dataset=ds, paso_meses=6, empresa='E', sistema_de={'F0': 'S1'})
    assert hecho['evaluacion']['formato_01_construido'] == 'formato_01_construido.xlsx'
    series = leer_formato_01(tmp_path / 'formato_01_construido.xlsx')
    assert series[0].codigo == 'S1' and series[0].empresa == 'E'


def test_herramienta_responde_al_help():
    """031:RF-13 — la orden con su ayuda, sin DIgSILENT ni GPU."""
    import subprocess

    r = subprocess.run([sys.executable, str(RAIZ / 'tools/proyeccion_anual.py'), '--help'], capture_output=True, text=True, encoding='utf-8', timeout=120, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    assert r.returncode == 0 and '--aceptar' in r.stdout and '--anio-fin' in r.stdout


def test_competicion_mide_el_crecimiento_de_todo_el_grupo(monkeypatch):
    """031:RF-2, 031:RF-5 — lo que se mide es lo que se emite: en cada origen, la tasa sale de todas las series del grupo, y a cada serie se le aplica esa."""
    vistos = []
    original = pa.historia_del_grupo

    def espia(series, origen=None):
        series = list(series)
        vistos.append(len(series))
        return original(series, origen)

    monkeypatch.setattr(pa, 'historia_del_grupo', espia)
    d = _dataset(alimentadores=2)
    pa.competir(d, candidatos=['tasa_de_un_anio', 'sin_crecimiento'], paso_meses=6, clases=['escaladas'])
    assert vistos and set(vistos) == {2}
    enero = (2026 - 1970) * 12
    s = pa.SerieMensual({enero - 12: 100.0}, {enero - 12: 200.0}, {})
    historia = {'media': {2025: 10.0, 2026: 11.0}, 'maxima': {2025: 10.0, 2026: 11.0}}
    assert pa._predecir_anual('tasa_de_un_anio', s, enero, [enero + 12], historia)[enero + 12] == pytest.approx((121.0, 242.0)), 'el mes de su último año por dos años de la tasa del grupo'


def test_emision_cola_con_la_tasa_de_largo_plazo():
    """031:RF-16 — tras el último año validado no se sigue la tendencia medida: crece con la tasa de largo plazo."""
    assert pa._con_cola({1: 1.5, 2: 2.25, 3: 3.375}, 0, 0.03) == pytest.approx({1: 1.5, 2: 1.545, 3: 1.59135})
    assert pa._con_cola({1: 1.5, 2: 2.25, 3: 3.375}, 2, 0.03) == pytest.approx({1: 1.5, 2: 2.25, 3: 2.3175})
    assert pa._con_cola({1: 1.0, 2: 1.0}, 5, 0.03) == {1: 1.0, 2: 1.0}


def test_ciclo_compiten_todos_los_modelos_de_pronostico(tmp_path):
    """031:RF-2 — la orden temporal lleva las referencias y los modelos pedidos, una sola vez cada uno."""
    from types import SimpleNamespace

    from tools.reentrenar_modelos import orden_temporal

    args = SimpleNamespace(cabeceras='l.xlsx', clase_temporal='cabecera', twin='t', semillas='11', cadencia_temporal=15,
                           zona_horaria='UTC', pares_temporales=None, clientes_temporales=None)
    cmd = orden_temporal(args, tmp_path / 'r.json', 'gru', 'nhits', 'tft', 'patchtst')
    assert cmd[cmd.index('--comparar') + 1] == 'ingenuo,estacional_semanal,gru,nhits,tft,patchtst'

