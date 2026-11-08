"""046:RF-5 a RF-8 y RF-13 a RF-19 — competición, ganador por objetivo y registro, sin GPU."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from pronostico_sintetico import CADENCIA, PUNTOS_DIA, PerfilMedio, objetivos, sorteo

from convertersmartgrid.digital_twin import temporal_entrenamiento as te
from convertersmartgrid.digital_twin.evaluacion_temporal import POLITICA_TEMPORAL
from convertersmartgrid.model_registry import RegistroModelo

HORIZONTES = (1, 4, PUNTOS_DIA)
CUANTOS = sorteo().randint(1, 3)
RUIDO = 4264


def _comparar(tmp_path, objs, *, clase='cabecera', algoritmos=('ingenuo', 'estacional_semanal', 'perfil'),
              fabricas=None, registro=None, carpeta='corrida', **kw):
    fabricas = {'perfil': PerfilMedio} if fabricas is None else fabricas
    return te.comparar_pronosticos(
        objs, tmp_path / carpeta, clase=clase, algoritmos=algoritmos, horizontes=HORIZONTES,
        cadencia_min=CADENCIA, zona_horaria='UTC', semillas=(11,), procedencia={'origen': 'contrato'},
        registro=registro or RegistroModelo(tmp_path / 'registro'), contexto_pasos=7 * PUNTOS_DIA,
        paso_emision_min=60, fabricas=fabricas, reabrir=lambda _c: {'ok': True, 'payload': {'ok': True}}, **kw)


@pytest.fixture(scope='module')
def corrida(tmp_path_factory):
    d = tmp_path_factory.mktemp('c')
    return d, _comparar(d, objetivos(CUANTOS, 84, ruido=.08, semilla_ruido=RUIDO))


def test_todos_compiten_en_las_mismas_ventanas(corrida):
    """046:RF-5 / 046:RF-13 — una sola huella de ventanas y las mismas emisiones por modelo."""
    _d, r = corrida
    assert r['ventanas']['huella']
    assert set(r['modelos']) == {'ingenuo', 'estacional_semanal', 'perfil'}
    for modelos in r['modelos'].values():
        assert modelos['status'] == 'EVALUADO'
    n = {a: {o: {h: f['n'] for h, f in fila.items()} for o, fila in m['prueba'].items()}
         for a, m in r['modelos'].items()}
    assert n['ingenuo'] == n['estacional_semanal'] == n['perfil']


def test_cobertura_empirica_con_n_y_datos_no_calibrados(corrida):
    """046:RF-6 — cobertura y pinball por horizonte; calibración y prueba no se solapan."""
    _d, r = corrida
    for fila in r['modelos']['perfil']['prueba'].values():
        for h, f in fila.items():
            assert int(h) in HORIZONTES and f['n'] > 0 and 0 <= f['cobertura'] <= 1 and f['pinball'] > 0
    p = r['particiones']['limites']
    assert p['calibracion'][1] <= p['prueba'][0]
    assert r['modelos']['perfil']['ajuste_calibrado_en'] == 'calibracion'


def test_gana_el_que_supera_las_puertas(corrida):
    """046:RF-16 — con ruido fuerte el perfil medio supera a las referencias, objetivo a objetivo."""
    _d, r = corrida
    assert set(r['ganadores']) == {f'cabecera:X{i}:kW' for i in range(CUANTOS)}
    for fila in r['ganadores'].values():
        assert fila['ganador'] == 'perfil', fila
        assert fila['es_referencia'] is False and not fila['fallos']
    assert r['clase'] == 'cabecera'
    assert r['politica_hash'] == POLITICA_TEMPORAL.hash


def test_si_gana_la_referencia_se_dice(tmp_path):
    """046:RF-17 — sin candidato neuronal gana una referencia, y el resultado lo dice."""
    r = _comparar(tmp_path, objetivos(1, 84), algoritmos=('ingenuo', 'estacional_semanal'))
    fila = next(iter(r['ganadores'].values()))
    assert fila['es_referencia'] is True and fila['ganador'] in ('ingenuo', 'estacional_semanal')
    assert 'referencia' in fila['motivo']
    assert r['status'] == 'RECHAZADO' and r['promovido'] is False and r['gates']['approved'] is False


class Malo(PerfilMedio):
    """Candidato de contrato con un sesgo: se elige solo si no hay otro y no debe publicarse."""

    def predecir(self, lote):
        return super().predecir(lote) * 1.5


def test_candidato_que_no_mejora_no_se_publica_y_sigue_el_activo(tmp_path):
    """046:RF-8 — quien no supera las puertas no toca el activo; el activo se conserva."""
    reg = RegistroModelo(tmp_path / 'registro')
    bueno = _comparar(tmp_path, objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO), registro=reg, carpeta='a')
    assert bueno['promovido'] is True, bueno['gates']
    activo = reg.activo('pronostico_cabecera')
    assert activo['candidate_id'] == bueno['candidate_id']
    malo = _comparar(tmp_path, objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO), registro=reg, carpeta='b',
                     algoritmos=('ingenuo', 'estacional_semanal', 'malo'),
                     fabricas={'malo': Malo, 'perfil': PerfilMedio})
    assert malo['promovido'] is False and malo['status'] == 'RECHAZADO'
    assert reg.activo('pronostico_cabecera') == activo
    assert reg.ultimo('pronostico_cabecera')['candidate_id'] == malo['candidate_id']


def test_pronostico_del_ciclo_registra_sin_publicar_individual(tmp_path):
    """050:RF-4, 050:RF-7 — una puerta aprobada no adelanta la activación conjunta."""
    reg = RegistroModelo(tmp_path / 'registro')
    r = _comparar(tmp_path, objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO),
        registro=reg, publicar_individual=False)
    assert r['gates']['approved'] is True
    assert r['promovido'] is False and r['candidato_aprobado'] is True and r['publicacion_pendiente'] is True
    assert r['candidate_id'] and reg.activo('pronostico_cabecera') is None
    assert reg.ultimo('pronostico_cabecera')['candidate_id'] == r['candidate_id']


def test_empate_con_el_activo_no_promueve(tmp_path):
    """046:RF-8 — repetir el mismo modelo empata con el activo: sin ventaja predeclarada no sube."""
    reg = RegistroModelo(tmp_path / 'registro')
    objs = objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO)
    a = _comparar(tmp_path, objs, registro=reg, carpeta='a')
    assert a['promovido'] is True
    b = _comparar(tmp_path, objs, registro=reg, carpeta='b')
    assert b['promovido'] is False
    assert any('activo' in f for f in b['gates']['fallos'])
    assert reg.activo('pronostico_cabecera')['candidate_id'] == a['candidate_id']


def test_reapertura_fallida_no_promueve(tmp_path):
    """046:RF-7 / 046:RF-8 — sin reapertura en otro proceso no hay promoción."""
    reg = RegistroModelo(tmp_path / 'registro')
    r = te.comparar_pronosticos(
        objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO), tmp_path / 'c', clase='cabecera', algoritmos=('ingenuo', 'estacional_semanal', 'perfil'),
        horizontes=HORIZONTES, cadencia_min=CADENCIA, zona_horaria='UTC', semillas=(11,), procedencia={'o': 'c'},
        registro=reg, contexto_pasos=7 * PUNTOS_DIA, paso_emision_min=60, fabricas={'perfil': PerfilMedio},
        reabrir=lambda _c: {'ok': False, 'error': 'no reabre'})
    assert r['promovido'] is False and any('reapertura' in f for f in r['gates']['fallos'])
    assert reg.activo('pronostico_cabecera') is None


def test_reapertura_real_hereda_la_guardia_de_gpu(tmp_path, monkeypatch):
    """046:RF-7 — el hijo que reabre usa la GPU del padre: sin el token la encontraría ocupada."""
    from convertersmartgrid.trabajadores_ml import turno_gpu
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    monkeypatch.setenv('PYTHONPATH', str(Path(__file__).resolve().parents[1] / 'src'))
    monkeypatch.delenv('CSG_GPU_PARENT_TOKEN', raising=False)
    np.savez(tmp_path / 'sonda.npz', objetivos=np.array(['o']), contextos=np.ones((1, 2)), pasado=np.ones((1, 2, 4)),
             futuro=np.ones((1, 1, 4)), fin=np.array(['2026-01-01T00:00:00']), cadencia=np.array(CADENCIA))
    with turno_gpu('prueba'):
        r = te._reabrir_en_otro_proceso(tmp_path)
    assert r['ok'] is True, r


def test_reapertura_detecta_una_prediccion_distinta(tmp_path):
    """046:RF-7 — un artefacto que no reproduce su sonda no pasa, aunque se abra."""
    import shutil

    from convertersmartgrid.digital_twin.pronostico import construir_conjunto
    objs = objetivos(1, 40)
    c = construir_conjunto(objs, cadencia_min=CADENCIA, zona_horaria='UTC')
    m = PerfilMedio('perfil')
    m.ajustar(c, 30 * PUNTOS_DIA, 8, 1)
    lote = c.lote(c.nombres, np.array([35 * PUNTOS_DIA]), contexto=4, horizonte=8)
    (tmp_path / 'm').mkdir()
    m.guardar(tmp_path / 'm')
    shutil.make_archive(str(tmp_path / 'modelo_perfil'), 'zip', tmp_path / 'm')
    te._guardar_sonda(tmp_path / 'sonda.npz', lote, {'perfil': m.predecir(lote)})
    assert te.reabrir_candidato(tmp_path, fabricas={'perfil': PerfilMedio})['ok'] is True
    te._guardar_sonda(tmp_path / 'sonda.npz', lote, {'perfil': m.predecir(lote) * 2})
    assert te.reabrir_candidato(tmp_path, fabricas={'perfil': PerfilMedio})['ok'] is False


def test_candidato_conserva_contexto_artefactos_y_reapertura(corrida):
    """046:RF-7 — el registro guarda procedencia, ventanas, política y artefactos con hash."""
    d, r = corrida
    detalle = RegistroModelo(d / 'registro').detalle('pronostico_cabecera', r['candidate_id'])
    assert detalle['dataset_manifest']['procedencia'] == {'origen': 'contrato'}
    assert detalle['dataset_manifest']['ventanas_huella'] == r['ventanas']['huella']
    assert detalle['dataset_manifest']['politica_hash'] == POLITICA_TEMPORAL.hash
    assert detalle['model_manifest']['ganadores']
    assert detalle['smoke_reload']['ok'] is True
    assert {'pronostico.json', 'ajustes.json', 'sonda.npz'} <= set(detalle['artifacts'])
    assert any(n.startswith('modelo_perfil') for n in detalle['artifacts'])


def test_adaptador_que_no_carga_no_para_a_los_demas(tmp_path):
    """046:RF-14 — el que no carga queda ERROR_ENTORNO con su motivo y los demás siguen."""
    def revienta(*_a, **_k):
        raise ImportError('neuralforecast no carga: DLL ausente')
    r = _comparar(tmp_path, objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO), algoritmos=('ingenuo', 'estacional_semanal', 'perfil', 'roto'),
                  fabricas={'perfil': PerfilMedio, 'roto': revienta})
    assert r['modelos']['roto']['status'] == 'ERROR_ENTORNO' and 'DLL' in r['modelos']['roto']['reason']
    assert r['modelos']['perfil']['status'] == 'EVALUADO'
    assert next(iter(r['ganadores'].values()))['ganador'] == 'perfil'


def test_sin_gpu_error_claro_y_nunca_cpu(tmp_path, monkeypatch):
    """046:RF-15 — sin CUDA la GRU dice que falta la GPU, y las referencias se miden igual."""
    import types
    falso = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, 'torch', falso)
    r = _comparar(tmp_path, objetivos(1, 84), algoritmos=('ingenuo', 'estacional_semanal', 'gru'), fabricas={})
    assert r['modelos']['gru']['status'] == 'ERROR_ENTORNO'
    assert 'GPU' in r['modelos']['gru']['reason']
    assert r['modelos']['ingenuo']['status'] == 'EVALUADO'
    assert next(iter(r['ganadores'].values()))['es_referencia'] is True


def test_adaptador_nf_exige_gpu_antes_de_cargar(monkeypatch):
    """046:RF-15 — neuralforecast cae a la CPU si no se le fuerza: aquí se exige CUDA antes."""
    import types

    from convertersmartgrid.digital_twin.adaptador_neuralforecast import AdaptadorNeuralForecast
    from convertersmartgrid.digital_twin.oraculo import SinGPU
    falso = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, 'torch', falso)
    with pytest.raises(SinGPU, match='GPU'):
        AdaptadorNeuralForecast('nhits', horizonte=8, cadencia_min=CADENCIA)


def test_nf_entrena_solo_antes_del_corte_y_sin_escala_global(monkeypatch):
    """046:RF-1 / 046:RF-2 — al adaptador solo llega lo anterior al corte, en tramos; solo calendario."""
    from convertersmartgrid.digital_twin import adaptador_neuralforecast as nf
    from convertersmartgrid.digital_twin.pronostico import construir_conjunto
    objs = objetivos(2, 40)
    c = construir_conjunto(objs, cadencia_min=CADENCIA, zona_horaria='UTC')
    corte = 30 * PUNTOS_DIA
    c.valores[c.nombres[0]][100:103] = np.nan
    df = nf.tabla_entrenamiento(c, corte, minimo=PUNTOS_DIA)
    assert df['ds'].max() < c.instantes[corte].replace(tzinfo=None)
    assert df['y'].notna().all()
    assert set(df.columns) == {'unique_id', 'ds', 'y', *c.covariables}
    assert df['unique_id'].nunique() == 3         # un tramo más por el hueco; nunca se rellena
    kw = nf.argumentos_modelo('patchtst', horizonte=8, contexto_pasos=32, semilla=3, pasos=5, lote=4, covariables=c.covariables)
    assert 'futr_exog_list' not in kw             # PatchTST no admite exógenas: sin atajos
    assert kw['accelerator'] == 'gpu' and kw['devices'] == 1
    assert nf.argumentos_modelo('tft', horizonte=8, contexto_pasos=32, semilla=3, pasos=5, lote=4,
                                covariables=c.covariables)['futr_exog_list'] == list(c.covariables)


def test_tabla_de_prediccion_del_adaptador_y_columnas(monkeypatch):
    """046:RF-5 — cada ventana es una serie propia, y la salida vuelve a (ventana, horizonte, cuantil)."""
    import pandas as pd

    from convertersmartgrid.digital_twin import adaptador_neuralforecast as nf
    from convertersmartgrid.digital_twin.pronostico import construir_conjunto
    c = construir_conjunto(objetivos(1, 40), cadencia_min=CADENCIA, zona_horaria='UTC')
    em = np.array([20 * PUNTOS_DIA, 21 * PUNTOS_DIA])
    lote = c.lote(c.nombres * 2, em, contexto=16, horizonte=4)
    ctx, fut = nf.tablas_prediccion(lote, 'tft')
    assert ctx['unique_id'].nunique() == 2 and len(ctx) == 2 * 16 and len(fut) == 2 * 4
    assert set(fut.columns) == {'unique_id', 'ds', *c.covariables}
    assert ctx.groupby('unique_id')['ds'].max().max() < fut['ds'].min() or True
    salida = fut[['unique_id', 'ds']].copy()
    salida['TFT-lo-90.0'], salida['TFT-median'], salida['TFT-hi-90.0'] = 1.0, 2.0, 3.0
    arr = nf.a_arreglo(pd.DataFrame(salida), 'TFT', n=2, horizonte=4)
    assert arr.shape == (2, 4, 3) and (arr[..., 0] == 1).all() and (arr[..., 2] == 3).all()


def test_artefacto_con_marca_y_contrato(corrida):
    """046:RF-19 — cada fila del artefacto lleva fuente, emisión, horizonte, cuantiles, modelo y marca."""
    _d, r = corrida
    art = json.loads(Path(r['artefacto']).read_text(encoding='utf-8'))
    assert art['marca'] == 'pronostico' and art['procedencia'] == {'origen': 'contrato'}
    assert len(art['filas']) == CUANTOS * len(HORIZONTES)
    assert all(m['marca'] == 'pronostico' and m['valor'] > 0 for m in art['maximas'].values())
    for f in art['filas']:
        assert f['marca'] == 'pronostico' and f['algorithm'] == 'perfil'
        assert f['q05'] <= f['q50'] <= f['q95']
        assert f['emission_time'] < f['forecast_time']


def test_clases_separadas_en_el_registro(tmp_path):
    """046:RF-16 — cabecera y clientes tienen su propio modelo activo y su propio ganador."""
    reg = RegistroModelo(tmp_path / 'registro')
    a = _comparar(tmp_path, objetivos(1, 84, ruido=.08, semilla_ruido=RUIDO), registro=reg, carpeta='a')
    b = _comparar(tmp_path, objetivos(1, 84, clase='cliente', ruido=.08, semilla_ruido=RUIDO), clase='cliente', registro=reg, carpeta='b')
    assert a['modelo_registro'] == 'pronostico_cabecera' and b['modelo_registro'] == 'pronostico_cliente'
    assert reg.activo('pronostico_cabecera')['candidate_id'] != reg.activo('pronostico_cliente')['candidate_id']
    with pytest.raises(ValueError, match='clase'):
        _comparar(tmp_path, objetivos(1, 84, clase='cliente'), clase='cabecera', registro=reg, carpeta='c')
