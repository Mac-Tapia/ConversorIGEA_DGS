"""031:RF-27 a RF-29 — horizonte largo del PIDE: las redes aprenden la serie diaria del objetivo (media y máxima del resto
sobre su perfil anclado), la curva de 15 minutos se reconstruye con el perfil del propio objetivo y las cuatro redes del PIDE
compiten con la misma resolución, el mismo contexto y el mismo horizonte.

Sin GPU real: neuralforecast se sustituye por un doble que anota con qué frecuencia, horizonte, contexto y series entrena
cada red, y que predice un resto fijo por serie. Las series son sintéticas y pequeñas; la cuenta de memoria usa la función
de la librería del proyecto (``bytes_ventanas_entrenamiento``) con las dimensiones medidas en la corrida del PIDE del
2026-11-20 (325 series, 64 223 registros de historia, un año de horizonte).
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from convertersmartgrid.adaptadores import pronostico_demanda as pd_
from convertersmartgrid.adaptadores import proyeccion_anual as pa
from convertersmartgrid.adaptadores.digital_twin import oraculo
from convertersmartgrid.adaptadores.digital_twin.pronostico import Objetivo
from convertersmartgrid.adaptadores.pronostico_demanda import CurvaCompacta, Dataset

GIB = 1024 ** 3
SUFIJO = getattr(pd_, 'SUFIJO_MAXIMA', '|maxima_diaria')
#: Lo que anota el doble de la librería en cada prueba.
_DOBLE: dict = {}


class _RedFalsa:
    def __init__(self, loss=None, **kw):
        self.kw = kw

    def parameters(self):
        return [types.SimpleNamespace(numel=lambda: 1000 + int(self.kw['h']))]


class _NeuralForecastFalso:
    def __init__(self, models, freq, local_scaler_type=None):
        self.models, self.freq = models, freq

    def fit(self, df):
        kw = self.models[0].kw
        _DOBLE['ajustes'].append({'red': type(self.models[0]).__name__, 'freq': self.freq, 'h': int(kw['h']),
                                  'contexto': int(kw['input_size']), 'paso': int(kw['step_size']),
                                  'relleno': bool(kw.get('start_padding_enabled')),
                                  'series': tuple(sorted(df['unique_id'].unique())), 'columnas': tuple(df.columns),
                                  'tipos': {c: str(df[c].dtype) for c in df.columns if c not in ('unique_id', 'ds')}})

    def predict(self, df, futr_df=None):
        import pandas as pd

        h = int(self.models[0].kw['h'])
        if futr_df is not None:
            salida = futr_df[['unique_id', 'ds']].copy()
        else:
            paso = pd.tseries.frequencies.to_offset(self.freq)
            salida = pd.concat([pd.DataFrame({'unique_id': u, 'ds': pd.date_range(g['ds'].max() + paso, periods=h, freq=self.freq)})
                                for u, g in df.groupby('unique_id')], ignore_index=True)
        cuantos = salida.groupby('unique_id').size()
        assert (cuantos == h).all(), f'el futuro no tiene el horizonte de la red: {dict(cuantos)} frente a {h}'
        salida[type(self.models[0]).__name__] = [_DOBLE['resto'](u) for u in salida['unique_id']]
        return salida


@pytest.fixture
def doble(monkeypatch):
    _DOBLE.clear()
    _DOBLE.update(ajustes=[], resto=lambda _u: 0.0)
    nf = types.ModuleType('neuralforecast')
    modelos = types.ModuleType('neuralforecast.models')
    perdidas = types.ModuleType('neuralforecast.losses')
    torch_perdidas = types.ModuleType('neuralforecast.losses.pytorch')
    for clase in ('NHITS', 'TFT', 'PatchTST', 'TiDE'):
        setattr(modelos, clase, type(clase, (_RedFalsa,), {}))
    nf.models, nf.NeuralForecast = modelos, _NeuralForecastFalso
    torch_perdidas.MAE = lambda **_k: None
    for nombre, modulo in (('neuralforecast', nf), ('neuralforecast.models', modelos), ('neuralforecast.losses', perdidas),
                           ('neuralforecast.losses.pytorch', torch_perdidas)):
        monkeypatch.setitem(sys.modules, nombre, modulo)
    monkeypatch.setattr(oraculo, 'dispositivo', lambda *_a, **_k: 'cuda')
    monkeypatch.setattr(pd_, 'memoria_gpu_libre', lambda: 7 * GIB, raising=False)
    monkeypatch.setattr(pd_, '_liberar_gpu', lambda: None)
    return _DOBLE


def _objetivos(n: int = 3, dias: int = 400, clase: str = 'escaladas', hueco_dia: int | None = None) -> list[Objetivo]:
    """Forma diaria con su punta de la tarde, semana con domingo bajo y un crecimiento suave; sin datos reales."""
    t = np.arange(np.datetime64('2025-01-01T00:00', 'ns'), np.datetime64('2025-01-01T00:00', 'ns') + np.timedelta64(dias, 'D'),
                  np.timedelta64(15, 'm'))
    bloque = np.arange(len(t)) % 96
    dia = np.arange(len(t)) // 96
    rng = np.random.default_rng(31)
    forma = 1 + .35 * np.exp(-((bloque - 76) / 8.0) ** 2) - .2 * np.cos(2 * np.pi * bloque / 96)
    semana = np.where(dia % 7 == 6, .85, 1.0)
    salida = []
    for i in range(n):
        v = (100.0 + 15 * i) * forma * semana * (1 + .0004 * dia) * (1 + .02 * rng.standard_normal(len(t)))
        tt = t
        if hueco_dia is not None:
            fuera = dia == hueco_dia
            tt, v = t[~fuera], v[~fuera]
        salida.append(Objetivo(clase, f'S{i}', 'kW', 'kW', CurvaCompacta(tt, v), {}))
    return salida


def test_031_rf27_hasta_31_dias_a_15_minutos_y_mas_alla_la_serie_diaria(doble):
    """031:RF-27 — una red pronostica a 15 minutos hasta HORIZONTE_CORTO_DIAS (la 089 sigue igual) y, con un horizonte mayor,
    entrena con la serie diaria: horizonte en días, una ventana por día y un contexto de un año como mucho. Una resolución
    desconocida se dice al crear la red."""
    resolucion = getattr(pd_, 'resolucion_de_horizonte', None)
    assert resolucion is not None, 'no hay una regla de resolución por horizonte'
    corto = pd_.HORIZONTE_CORTO_DIAS
    assert resolucion(corto * 96) == '15min' and resolucion(corto * 96 + 96) == 'diaria'
    assert resolucion(96, 'diaria') == 'diaria' and resolucion(400 * 96, '15min') == '15min'
    objs = _objetivos(n=2, dias=120)
    hasta = objs[0].curva.t[90 * 96 - 1]
    pd_.fabrica_modelo('nhits', pasos=2, lote=8).ajustar(objs, hasta, 28 * 96, None, 0)
    a = doble['ajustes'][-1]
    assert (a['freq'], a['h'], a['paso'], a['contexto']) == ('15min', 28 * 96, 96, 28 * 96), a
    pd_.fabrica_modelo('nhits', pasos=2, lote=8).ajustar(objs, hasta, 365 * 96, None, 0)
    a = doble['ajustes'][-1]
    assert (a['freq'], a['h'], a['paso']) == ('D', 365, 1), a
    # 031:RF-30 (2026-11-23): el contexto diario es de un año aunque la historia sea más corta; lo que falta va rellenado.
    assert a['contexto'] == pd_.CONTEXTO_DIARIO_DIAS and a['relleno'], a
    assert len(a['series']) == 4 and {s for s in a['series'] if s.endswith(SUFIJO)} == {o.nombre + SUFIJO for o in objs}
    try:
        pd_.fabrica_modelo('nhits', resolucion='horaria')
    except ValueError as exc:
        assert 'horaria' in str(exc)
    else:
        raise AssertionError('una resolución desconocida se aceptó en silencio')


def test_031_rf27_la_cuenta_de_memoria_justifica_la_serie_diaria():
    """031:RF-27 — con la función de la cuenta de RF-24 y las dimensiones de la corrida del PIDE (64 223 registros de
    historia, un año de horizonte, 8 canales a 15 minutos): un lote de 32 series a 15 minutos pide más de 8 GiB solo en
    ventanas, y a 31 días cabe en la mitad de 7,5 GiB libres; en la serie diaria, con dos series por objetivo y un año de
    contexto, las 650 series del grupo más grande caben juntas."""
    b = pd_.bytes_ventanas_entrenamiento
    assert round(b(1, 64223, 2688, 35040, 8, 96) / GIB, 3) == .721, 'la emisión medida: 0,72 GiB por serie'
    contexto = getattr(pd_, 'CONTEXTO_DIARIO_DIAS', None)
    assert contexto is not None, 'no hay serie diaria para el horizonte largo'
    libre = 7.5 * GIB * pd_.FRACCION_VRAM_VENTANAS
    assert b(32, 64223, 2688, 35040, 8, 96) > 8 * GIB
    assert b(32, 64223, 2688, pd_.HORIZONTE_CORTO_DIAS * 96, 8, 96) <= libre
    canales = 2 + len(pd_.COVARIABLES_DIARIAS)
    assert b(2 * 325, 64223 // 96, contexto, 396, canales, pd_.PASO_VENTANAS_DIARIAS) <= libre


def test_031_rf28_la_tabla_diaria_lleva_la_media_y_la_maxima_del_resto():
    """031:RF-28 — dos series por objetivo: la media del resto de cada día y la máxima del día menos la del perfil anclado, en
    la escala del objetivo; un día sin registros va enmascarado sin rellenar, el día del origen solo entra completo y todo va
    en float32."""
    tabla_diaria = getattr(pd_, 'tabla_diaria', None)
    assert tabla_diaria is not None, 'no hay tabla diaria'
    o = _objetivos(n=1, dias=60, hueco_dia=10)[0]
    hasta = o.curva.t[np.searchsorted(o.curva.t, np.datetime64('2025-02-20T09:45', 'ns'))]
    tabla = tabla_diaria([o], hasta, None)
    assert set(tabla['unique_id']) == {o.nombre, o.nombre + SUFIJO}
    assert set(tabla.drop(columns=['unique_id', 'ds']).dtypes.astype(str)) == {'float32'}
    media = tabla[tabla['unique_id'] == o.nombre].set_index('ds')
    maxima = tabla[tabla['unique_id'] == o.nombre + SUFIJO].set_index('ds')
    assert media.index.max() == np.datetime64('2025-02-19', 'ns'), 'el día del origen, a medias, ya es futuro'
    hueco = np.datetime64('2025-01-11', 'ns')
    assert media.loc[hueco, 'available_mask'] == 0 and maxima.loc[hueco, 'available_mask'] == 0
    malla, resto, escala, t, y = pd_._resto_normalizado(o, hasta, None)
    perfil = y - resto[np.searchsorted(malla, t)] * escala
    for d in ('2025-01-20', '2025-02-02', '2025-02-19'):
        dentro = (t >= np.datetime64(d, 'ns')) & (t < np.datetime64(d, 'ns') + np.timedelta64(1, 'D'))
        assert media.loc[np.datetime64(d, 'ns'), 'y'] == pytest.approx(np.mean(resto[np.searchsorted(malla, t[dentro])]), abs=1e-5)
        assert maxima.loc[np.datetime64(d, 'ns'), 'y'] == pytest.approx((y[dentro].max() - perfil[dentro].max()) / escala, abs=1e-4)


def _dias(futuro: np.ndarray, x: np.ndarray, f):
    dias = np.asarray(futuro, dtype='datetime64[D]')
    return np.array([f(x[dias == d]) for d in np.unique(dias)])


def test_031_rf28_la_curva_de_15_minutos_sale_del_perfil_del_objetivo(doble):
    """031:RF-28 — la red da la media y la máxima de cada día; la curva de 15 minutos tiene en cada día esa media y esa máxima
    y la forma del perfil anclado del propio objetivo. Con restos nulos, la curva es el perfil tal cual."""
    objs = _objetivos(n=2, dias=200)
    hasta = objs[0].curva.t[150 * 96 - 1]
    horizonte = 60 * 96
    futuro = pd_._malla(hasta, hasta + np.timedelta64(horizonte * 15, 'm'))
    doble['resto'] = lambda u: .3 if u.endswith(SUFIJO) else .1
    m = pd_.fabrica_modelo('nhits', pasos=2, lote=8, resolucion='diaria')
    m.ajustar(objs, hasta, horizonte, None, 0)
    p = m.predecir_todos(objs, hasta, horizonte, None)
    assert doble['ajustes'][-1]['freq'] == 'D', 'la red no entrenó con la serie diaria'
    for o in objs:
        _malla, _resto, escala, t, y = pd_._resto_normalizado(o, hasta, None)
        perfil = pd_._anclado(t, y, futuro, None)
        assert len(p[o.nombre]) == horizonte
        assert np.allclose(_dias(futuro, p[o.nombre], np.mean), _dias(futuro, perfil, np.mean) + .1 * escala)
        assert np.allclose(_dias(futuro, p[o.nombre], np.max), _dias(futuro, perfil, np.max) + .3 * escala)
        dias = np.asarray(futuro, dtype='datetime64[D]')
        primero = dias == dias[0]
        assert np.corrcoef(p[o.nombre][primero], perfil[primero])[0, 1] > .999, 'la forma del día es la del perfil'
        meses = pa._agregar_curva(futuro, p[o.nombre], sorted(set(pa._mes(futuro).tolist())))
        assert all(mx >= md for md, mx in meses.values())
    doble['resto'] = lambda _u: 0.0
    m.ajustar(objs, hasta, horizonte, None, 0)
    p = m.predecir_todos(objs, hasta, horizonte, None)
    _malla, _resto, _escala, t, y = pd_._resto_normalizado(objs[0], hasta, None)
    assert np.allclose(p[objs[0].nombre], pd_._anclado(t, y, futuro, None))


def test_031_rf27_las_cuatro_redes_del_pide_compiten_con_la_misma_serie_diaria(doble):
    """031:RF-27, 031:RF-29 — en la competición del PIDE, N-HiTS, TFT, PatchTST y TiDE entrenan en cada origen y en la emisión
    con la serie diaria, el mismo horizonte en días, el mismo contexto y las mismas series; la evaluación anota por origen la
    resolución, la unidad, el horizonte a 15 minutos y los parámetros de la red."""
    redes = ('nhits', 'tft', 'patchtst', 'tide')
    c = pa.competir(Dataset(_objetivos(), [], [], {}), candidatos=['tasa_de_un_anio', 'sin_crecimiento'], modelos=list(redes),
                    paso_meses=3, clases=['escaladas'], ajustes={'pasos': 2})
    candidatos = c['grupos']['escaladas|kW']['candidatos']
    ajustes = doble['ajustes']
    assert ajustes and {a['freq'] for a in ajustes} == {'D'}, sorted({(a['red'], a['freq'], a['h']) for a in ajustes})
    assert max(a['h'] for a in ajustes) <= 400, 'un año de horizonte son 365 o 366 días, no 35 040 registros'
    por_red: dict[str, list] = {}
    for a in ajustes:
        por_red.setdefault(a['red'], []).append((a['h'], a['contexto'], a['series']))
    assert len(por_red) == 4 and len({tuple(v) for v in por_red.values()}) == 1, 'las cuatro redes no se midieron igual'
    for red in redes:
        cand = candidatos[red]
        assert cand.get('status') != 'NO_DISPONIBLE', cand
        memoria = cand.get('memoria_gpu') or []
        assert memoria and memoria[-1]['origen'] == 'emisión'
        for r in memoria:
            assert r['resolucion'] == 'diaria' and r['unidad'] == 'días' and r['horizonte_15min'] % 96 == 0
            assert r['parametros'] == 1000 + r['horizonte'], 'la evaluación no anota los parámetros de la red'


def test_031_rf30_un_anio_de_contexto_tambien_para_las_series_cortas(doble):
    """031:RF-30 — en la 031 T5 (2026-11-22) ninguna red emitió el PIDE porque la serie más corta tenía 100 días y el
    contexto era de 364. Con una serie de 400 días y otra de 100, la red diaria entrena con un año de contexto, el relleno
    inicial activo y las dos series dentro."""
    largos = _objetivos(n=1, dias=400)
    corta = _objetivos(n=2, dias=100)[1]
    inicio = largos[0].curva.t[-1] - np.timedelta64(100, 'D')
    corta = Objetivo(corta.clase, 'S9', 'kW', 'kW', CurvaCompacta(corta.curva.t - corta.curva.t[0] + inicio, corta.curva.columnas[0]), {})
    objs = [*largos, corta]
    hasta = largos[0].curva.t[-1 - 96]
    pd_.fabrica_modelo('nhits', pasos=2, lote=8).ajustar(objs, hasta, 365 * 96, None, 0)
    a = doble['ajustes'][-1]
    assert a['freq'] == 'D' and a['contexto'] == pd_.CONTEXTO_DIARIO_DIAS and a['relleno'], a
    # El nombre de la serie es «clase:SED:magnitud», con «|maxima_diaria» en la de la máxima.
    assert {p for s in a['series'] for p in s.replace('|', ':').split(':')} >= {'S0', 'S9'}, 'la serie corta quedó fuera'
