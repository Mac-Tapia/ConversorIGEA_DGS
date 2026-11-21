"""031:RF-24 a RF-26 — las redes del PIDE caben en la tarjeta: lote de series por la VRAM libre medida, reintento sin
memoria y causa escrita, y una predicción que solo lleva su contexto.

Sin GPU real: neuralforecast se sustituye por un doble que pide la misma memoria que la librería (``_create_windows`` de
neuralforecast 3.3: todas las ventanas de las series del lote, de contexto + horizonte, copiadas al aplanarlas) y que
falla como CUDA cuando lo pedido pasa de una tarjeta simulada. La cuenta del doble se ancla en las dos peticiones medidas
en la corrida del PIDE del 2026-11-20 (9,51 GiB y 23,06 GiB); las series son sintéticas y pequeñas.
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

MIB2 = 2 * 1024 ** 2
#: El doble, como la librería: sus peticiones y la tarjeta simulada de cada prueba.
_TARJETA: dict = {}


def _pide(series: int, largo: int, contexto: int, horizonte: int, canales: int, paso: int) -> int:
    """Bytes que neuralforecast 3.3 copia al entrenar un lote: series × ventanas × (contexto + horizonte) × canales × 4."""
    return series * ((largo - contexto) // paso + 1) * (contexto + horizonte) * canales * 4


def _redondeo_cuda(n: int) -> int:
    return -(-n // MIB2) * MIB2


class _ParametroFalso:
    def __init__(self, n: int):
        self.n = n

    def numel(self) -> int:
        return self.n


class _RedFalsa:
    def __init__(self, loss=None, **kw):
        self.kw = kw

    def parameters(self):
        return [_ParametroFalso(_TARJETA.get('parametros', 0))]


class _NeuralForecastFalso:
    def __init__(self, models, freq, local_scaler_type=None):
        self.models = models

    def fit(self, df):
        kw = self.models[0].kw
        largos = df.groupby('unique_id').size()
        lote = min(int(kw['batch_size']), len(largos))
        pide = _pide(lote, int(largos.max()), kw['input_size'], kw['h'], len(df.columns) - 2, kw['step_size'])
        _TARJETA['pedidos'].append((lote, pide))
        _TARJETA['tipos'].append({c: str(df[c].dtype) for c in df.columns if c not in ('unique_id', 'ds')})
        if pide > _TARJETA['capacidad']:
            raise RuntimeError(f'CUDA out of memory. Tried to allocate {pide / 1024 ** 3:.2f} GiB')

    def predict(self, df, futr_df=None):
        import pandas as pd

        _TARJETA['filas_prediccion'].append(int(df.groupby('unique_id').size().max()))
        salida = futr_df[['unique_id', 'ds']].copy() if futr_df is not None else pd.DataFrame(columns=['unique_id', 'ds'])
        salida['NHITS'] = 0.0
        return salida


@pytest.fixture
def tarjeta(monkeypatch):
    """Una tarjeta simulada: ``capacidad`` es lo que cabe de verdad y ``libre`` lo que CUDA dice que hay libre."""
    _TARJETA.clear()
    _TARJETA.update(capacidad=0, libre=None, pedidos=[], tipos=[], filas_prediccion=[], liberada=0, parametros=0)
    nf = types.ModuleType('neuralforecast')
    modelos = types.ModuleType('neuralforecast.models')
    perdidas = types.ModuleType('neuralforecast.losses')
    torch_perdidas = types.ModuleType('neuralforecast.losses.pytorch')
    modelos.NHITS = _RedFalsa
    nf.models, nf.NeuralForecast = modelos, _NeuralForecastFalso
    torch_perdidas.MAE = lambda **_k: None
    for nombre, modulo in (('neuralforecast', nf), ('neuralforecast.models', modelos), ('neuralforecast.losses', perdidas),
                           ('neuralforecast.losses.pytorch', torch_perdidas)):
        monkeypatch.setitem(sys.modules, nombre, modulo)
    monkeypatch.setattr(oraculo, 'dispositivo', lambda *_a, **_k: 'cuda')
    monkeypatch.setattr(pd_, 'memoria_gpu_libre', lambda: _TARJETA['libre'], raising=False)

    def liberar():
        _TARJETA['liberada'] += 1

    monkeypatch.setattr(pd_, '_liberar_gpu', liberar)
    return _TARJETA


def _objetivos(n: int = 6, dias: int = 60, clase: str = 'cabecera') -> list[Objetivo]:
    t = np.arange(np.datetime64('2025-01-01T00:15', 'ns'), np.datetime64('2025-01-01T00:15', 'ns') + np.timedelta64(dias, 'D'),
                  np.timedelta64(15, 'm'))
    bloque = np.arange(len(t)) % 96
    rng = np.random.default_rng(7)
    return [Objetivo(clase, f'S{i}', 'kW', 'kW', CurvaCompacta(t, (100.0 + 10 * i) * (1 + .3 * np.sin(2 * np.pi * bloque / 96))
                                                              * (1 + .02 * rng.standard_normal(len(t)))), {})
            for i in range(n)]


def _por_serie(objs, hasta, contexto: int, horizonte: int) -> int:
    tabla = pd_.tabla_de_entrenamiento(objs, hasta, None)
    return _pide(1, int(tabla.groupby('unique_id').size().max()), contexto, horizonte, len(tabla.columns) - 2, 96)


def _ajustar(m, objs, hasta, horizonte) -> str | None:
    try:
        m.ajustar(objs, hasta, horizonte, None, 0)
    except RuntimeError as exc:
        return str(exc)
    return None


def test_031_rf24_la_cuenta_reproduce_las_peticiones_medidas():
    """031:RF-24 — la cuenta de las ventanas da, redondeada como CUDA, lo que pidió la corrida real del PIDE: N-HiTS con 32
    clientes y un horizonte de 396 días (9,51 GiB) y la emisión de las escaladas a 365 días (23,06 GiB)."""
    assert _redondeo_cuda(_pide(32, 2688 + 244 * 96, 2688, 396 * 96, 8, 96)) == 10_213_130_240
    assert _redondeo_cuda(_pide(32, 2688 + 640 * 96, 2688, 365 * 96, 8, 96)) == 24_765_267_968


def test_031_rf24_el_lote_de_series_sale_de_la_vram_libre_medida(tarjeta):
    """031:RF-24 — con la VRAM libre medida justa para dos series, la red entrena con las que caben en vez de pedir el lote
    entero; las ventanas por paso y los pasos no cambian."""
    objs = _objetivos()
    hasta = np.datetime64(objs[0].curva.t[50 * 96 - 1])
    horizonte = 30 * 96
    por_serie = _por_serie(objs, hasta, 192, horizonte)
    tarjeta.update(capacidad=int(2.2 * por_serie), libre=int(2.2 * por_serie))
    m = pd_.fabrica_modelo('nhits', pasos=2, lote=64, contexto_dias=2)
    fallo = _ajustar(m, objs, hasta, horizonte)
    assert fallo is None, f'pidió más de lo que había libre: {fallo}; peticiones {tarjeta["pedidos"]}'
    lote, pide = tarjeta['pedidos'][-1]
    assert 1 <= lote < len(objs) and pide <= tarjeta['libre'] * pd_.FRACCION_VRAM_VENTANAS
    assert m.memoria['series_por_lote'] == lote and m.memoria['vram_libre'] == tarjeta['libre']
    assert m.lote == 64, 'las ventanas de cada paso de entrenamiento siguen siendo las pedidas'


def test_031_rf24_la_red_con_sus_gradientes_se_descuenta_de_lo_libre(tarjeta):
    """031:RF-24 — el lote de series sale de lo que queda libre después de la red con sus gradientes y Adam (N-HiTS con el
    horizonte del PIDE: 4,37 GiB), no de toda la memoria libre."""
    objs = _objetivos()
    hasta = np.datetime64(objs[0].curva.t[50 * 96 - 1])
    horizonte = 30 * 96
    por_serie = _por_serie(objs, hasta, 192, horizonte)
    tarjeta.update(capacidad=10 ** 15, libre=10 * por_serie, parametros=6 * por_serie // 16)
    m = pd_.fabrica_modelo('nhits', pasos=2, lote=64, contexto_dias=2)
    fallo = _ajustar(m, objs, hasta, horizonte)
    assert fallo is None, fallo
    assert [lote for lote, _p in tarjeta['pedidos']] == [2], 'con 4 series libres tras la red y la mitad para ventanas, 2'
    assert m.memoria['bytes_red_entrenando'] == 6 * por_serie // 16 * 16


def test_031_rf25_una_red_que_sola_no_cabe_ni_se_intenta(tarjeta):
    """031:RF-25 — si la red sola, con sus gradientes y Adam, pide más que lo libre (TiDE y PatchTST con el horizonte del
    PIDE: 22,7 y 24,4 GiB), no se entrena ni se deja pasar a la memoria compartida: se dice con la cuenta."""
    objs = _objetivos()
    hasta = np.datetime64(objs[0].curva.t[50 * 96 - 1])
    tarjeta.update(capacidad=10 ** 15, libre=1024 ** 3, parametros=100_000_000)
    m = pd_.fabrica_modelo('nhits', pasos=2, lote=64, contexto_dias=2)
    fallo = _ajustar(m, objs, hasta, 30 * 96)
    assert fallo is not None and 'la red sola' in fallo and 'M de parámetros' in fallo, fallo
    assert tarjeta['pedidos'] == [], 'ni se intenta entrenar'


def test_031_rf25_sin_memoria_reintenta_con_menos_series(tarjeta):
    """031:RF-25 — si CUDA dice que hay sitio y el ajuste se queda sin memoria, se libera y se reintenta con la mitad de series
    por lote hasta que cabe, y queda anotado cuántas veces."""
    objs = _objetivos()
    hasta = np.datetime64(objs[0].curva.t[50 * 96 - 1])
    horizonte = 30 * 96
    por_serie = _por_serie(objs, hasta, 192, horizonte)
    tarjeta.update(capacidad=int(1.5 * por_serie), libre=100 * por_serie)
    m = pd_.fabrica_modelo('nhits', pasos=2, lote=64, contexto_dias=2)
    fallo = _ajustar(m, objs, hasta, horizonte)
    assert fallo is None, f'se quedó en el primer «out of memory»: {fallo}'
    assert [lote for lote, _p in tarjeta['pedidos']] == [6, 3, 1]
    assert m.memoria['reintentos'] == 2 and m.memoria['series_por_lote'] == 1 and 'out of memory' in m.memoria['fallo']
    assert tarjeta['liberada'] >= 2, 'entre un intento y otro se suelta la caché de la GPU'


def _dataset_escaladas() -> Dataset:
    return Dataset(_objetivos(n=3, dias=400, clase='escaladas'), [], [], {})


def test_031_rf25_si_no_cabe_ni_con_una_serie_la_evaluacion_dice_la_causa(tarjeta):
    """031:RF-25 — una red que no cabe ni con una serie por lote queda NO_DISPONIBLE con causa «memoria_gpu», lo que pedía y
    lo que había libre, y los demás candidatos siguen."""
    tarjeta.update(capacidad=1024, libre=1024)
    c = pa.competir(_dataset_escaladas(), candidatos=['tasa_de_un_anio', 'sin_crecimiento'], modelos=['nhits'], paso_meses=3,
                    clases=['escaladas'], ajustes={'pasos': 2, 'contexto_dias': 2})
    nhits = c['grupos']['escaladas|kW']['candidatos']['nhits']
    assert nhits['status'] == 'NO_DISPONIBLE'
    assert nhits.get('causa') == 'memoria_gpu', nhits
    assert 'GiB' in nhits['motivo'] and 'no cabe en la GPU' in nhits['motivo']
    detalle = nhits['memoria_gpu'][-1]
    assert detalle['bytes_por_serie'] > detalle['vram_libre'] == 1024
    assert 'eleccion' in c['grupos']['escaladas|kW']['candidatos']['sin_crecimiento']


def test_031_rf24_cada_origen_suelta_la_gpu_y_anota_su_lote(tarjeta):
    """031:RF-24 — en la competición del PIDE, cada origen y la emisión entrenan con el lote que cabe, lo anotan en la
    evaluación y sueltan la red y la caché de la GPU antes del siguiente."""
    tarjeta.update(capacidad=10 ** 12, libre=10 ** 12)
    c = pa.competir(_dataset_escaladas(), candidatos=['tasa_de_un_anio', 'sin_crecimiento'], modelos=['nhits'], paso_meses=3,
                    clases=['escaladas'], ajustes={'pasos': 2, 'contexto_dias': 2})
    nhits = c['grupos']['escaladas|kW']['candidatos']['nhits']
    memoria = nhits.get('memoria_gpu') or []
    assert memoria, f'la evaluación no anota la memoria de la GPU: {sorted(nhits)}'
    assert memoria[-1]['origen'] == 'emisión' and all(r['series_por_lote'] >= 1 for r in memoria)
    assert len(memoria) == len(tarjeta['pedidos'])
    assert tarjeta['liberada'] >= len(memoria), 'cada origen suelta la GPU'
    # Con orígenes anuales y poco más de un año de historia la red no compite (NO_APLICA), pero lo que entrenó en la GPU
    # sigue en la evaluación: el ensayo del 2026-11-20 lo perdía al cambiar su estado.
    c = pa.competir(_dataset_escaladas(), candidatos=['tasa_de_un_anio', 'sin_crecimiento'], modelos=['nhits'], paso_meses=12,
                    clases=['escaladas'], ajustes={'pasos': 2, 'contexto_dias': 2})
    nhits = c['grupos']['escaladas|kW']['candidatos']['nhits']
    assert nhits['status'] == 'NO_APLICA' and nhits.get('memoria_gpu'), nhits


def test_031_rf26_el_dataset_se_abre_sin_un_texto_por_registro(tmp_path, monkeypatch):
    """031:RF-26 — el nombre del objetivo se lee del Parquet como diccionario, no como un objeto de Python por registro (abrir
    el dataset de la T12 ocupaba unos 5 GiB), y las curvas reabiertas son las guardadas, con su huella."""
    import pandas as pd

    objs = _objetivos(n=4, dias=20)
    d = Dataset(objs, [], [], {})
    pd_.guardar_dataset(d, tmp_path / 'ds')
    leidas = []
    original = pd.read_parquet

    def leer(ruta, *a, **k):
        tabla = original(ruta, *a, **k)
        leidas.append((k, str(tabla['objetivo'].dtype)))
        return tabla

    monkeypatch.setattr(pd, 'read_parquet', leer)
    otro = pd_.abrir_dataset(tmp_path / 'ds')
    assert leidas and leidas[0][1] == 'category', f'el objetivo se leyó como {leidas[0][1] if leidas else "nada"}'
    por = {o.nombre: o for o in otro.objetivos}
    for o in objs:
        assert np.array_equal(por[o.nombre].curva.t, o.curva.t) and np.array_equal(por[o.nombre].curva.columnas[0], o.curva.columnas[0])


def test_031_rf26_la_prediccion_lleva_solo_su_contexto_y_la_tabla_va_en_float32(tarjeta):
    """031:RF-26 — la predicción recibe solo el contexto de cada serie (la red no mira más atrás) y la tabla de entrenamiento
    va en float32, como la guarda la librería: la corrida del 2026-11-20 ocupaba 7,7 GiB de RAM."""
    objs = _objetivos()
    hasta = np.datetime64(objs[0].curva.t[50 * 96 - 1])
    tarjeta.update(capacidad=10 ** 12, libre=10 ** 12)
    m = pd_.fabrica_modelo('nhits', pasos=2, lote=64, contexto_dias=2)
    m.ajustar(objs, hasta, 96, None, 0)
    p = m.predecir_todos(objs, hasta, 96, None)
    assert set(p) == {o.nombre for o in objs} and all(len(v) == 96 for v in p.values())
    assert tarjeta['filas_prediccion'] == [192], f'la predicción llevó {tarjeta["filas_prediccion"]} registros por serie'
    assert set(tarjeta['tipos'][-1].values()) == {'float32'}, tarjeta['tipos'][-1]
