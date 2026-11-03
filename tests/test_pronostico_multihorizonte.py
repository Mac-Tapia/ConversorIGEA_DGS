"""046:RF-1 a RF-5 y RF-14 — contrato multihorizonte y ventanas causales, sin GPU."""
from __future__ import annotations

import builtins
import sys
from datetime import datetime, timedelta

import numpy as np
import pytest
from pronostico_sintetico import CADENCIA, PUNTOS_DIA, objetivos, sorteo

from convertersmartgrid.digital_twin import pronostico as pr
from convertersmartgrid.digital_twin import series_causales as sc
from convertersmartgrid.digital_twin.evaluacion_temporal import POLITICA_TEMPORAL


def _conjunto(cuantos=2, dias=100):
    return pr.construir_conjunto(objetivos(cuantos, dias), cadencia_min=CADENCIA, zona_horaria='UTC')


def test_horizonte_exige_cadencia():
    """046:RF-4 — (1, 4, 96) solo se supone con 15 minutos; otra cadencia los declara."""
    assert sc.horizontes_validos(15) == (1, 4, 96)
    with pytest.raises(ValueError, match='horizontes'):
        sc.horizontes_validos(60)
    assert sc.horizontes_validos(60, (1, 24)) == (1, 24)
    with pytest.raises(ValueError, match='horizonte'):
        sc.horizontes_validos(15, (0, 4))


def test_contrato_de_cada_salida():
    """046:RF-4 — objetivo, emisión, instante previsto, horizonte en pasos y minutos y cuantiles."""
    c = _conjunto()
    nombre = c.nombres[0]
    e = len(c.instantes) - 1
    filas = pr.pronosticar({'conjunto': c, 'objetivo': nombre, 'emision': e, 'modelo': pr.Ingenuo(),
                            'ajuste': None}, horizontes=(1, 4), algoritmo='ingenuo')
    assert [f['horizon_steps'] for f in filas] == [1, 4]
    f = filas[1]
    for clave in ('target', 'emission_time', 'forecast_time', 'cadence_min', 'horizon_min', 'q05', 'q50', 'q95',
                  'algorithm', 'unit', 'marca'):
        assert clave in f, clave
    assert f['target'] == nombre and f['algorithm'] == 'ingenuo' and f['cadence_min'] == CADENCIA
    assert f['horizon_min'] == 4 * CADENCIA
    emision = datetime.fromisoformat(f['emission_time'])
    assert datetime.fromisoformat(f['forecast_time']) - emision == timedelta(minutes=4 * CADENCIA)
    assert f['q05'] <= f['q50'] <= f['q95']


def test_el_pronostico_no_ve_el_futuro():
    """046:RF-1 — cambiar lo posterior a la emisión no cambia la predicción de las referencias."""
    c = _conjunto()
    nombre = c.nombres[0]
    e = len(c.instantes) - PUNTOS_DIA - 1
    for modelo in (pr.Ingenuo(), pr.EstacionalSemanal(CADENCIA)):
        lote = c.lote([nombre], np.array([e]), contexto=7 * PUNTOS_DIA, horizonte=PUNTOS_DIA)
        antes = modelo.predecir(lote)
        c.valores[nombre][e + 1:] *= 1000
        despues = modelo.predecir(c.lote([nombre], np.array([e]), contexto=7 * PUNTOS_DIA, horizonte=PUNTOS_DIA))
        c.valores[nombre][e + 1:] /= 1000
        assert np.array_equal(antes, despues)


def test_estacional_semanal_usa_el_mismo_instante_conocido():
    """046:RF-13 — cada horizonte toma el mismo instante de la última semana ya observada."""
    c = _conjunto(1)
    nombre = c.nombres[0]
    semana = 7 * PUNTOS_DIA
    e = 30 * PUNTOS_DIA
    p = pr.EstacionalSemanal(CADENCIA).predecir(c.lote([nombre], np.array([e]), contexto=semana, horizonte=semana + 3))
    v = c.valores[nombre]
    assert p[0, 0, 1] == v[e + 1 - semana]
    assert p[0, semana - 1, 1] == v[e]                       # justo una semana: el valor de la emisión
    assert p[0, semana, 1] == v[e + 1 - semana]              # más de una semana: dos atrás
    assert pr.EstacionalSemanal(60).periodo == 7 * 24


def test_estacional_exige_cadencia_de_periodo_entero():
    """046:RF-3 — una cadencia que no divide la semana no se redondea."""
    with pytest.raises(ValueError, match='cadencia'):
        pr.EstacionalSemanal(7 * 1440 + 1)


def test_ventanas_purgan_objetivos_de_otra_particion():
    """046:RF-1 / 046:RF-5 — ningún objetivo de una ventana cruza a otra partición."""
    r = sorteo()
    dias, H = r.randint(95, 130), r.choice((4, 96))
    c = _conjunto(1, dias)
    v = c.valores[c.nombres[0]]
    p = sc.particionar_dias(c.instantes, 'UTC', POLITICA_TEMPORAL)
    usados = {}
    for parte, (i, f) in p['limites'].items():
        em = sc.ventanas_causales(v, inicio=i, fin=f, contexto_pasos=PUNTOS_DIA, horizonte_max=H, paso=4)
        assert len(em)
        assert (em + 1 >= i).all() and (em + H < f).all(), parte
        for e in em:
            for t in range(e + 1, e + H + 1):
                assert usados.setdefault(t, parte) == parte


def test_ventanas_excluyen_huecos_sin_rellenar():
    """046:RF-3 — con un hueco en el contexto o en el objetivo, esa emisión no existe."""
    v = np.arange(200.0)
    v[100] = np.nan
    em = sc.ventanas_causales(v, inicio=0, fin=200, contexto_pasos=10, horizonte_max=5, paso=1)
    assert 100 not in em and 95 not in em and 104 not in em
    assert 94 in em and 110 in em and 109 not in em


def test_particion_por_dias_usa_el_particionador_de_044():
    """046:RF-5 — días enteros y sin solape; pocos días bloquean por datos, no se reparten igual."""
    c = _conjunto(1, 100)
    p = sc.particionar_dias(c.instantes, 'UTC', POLITICA_TEMPORAL)
    assert set(p['dias']) == {'entrenamiento', 'seleccion', 'calibracion', 'prueba'}
    assert p['politica_hash'] == POLITICA_TEMPORAL.hash
    assert len({d for ds in p['dias'].values() for d in ds}) == sum(len(ds) for ds in p['dias'].values())
    corto = pr.construir_conjunto(objetivos(1, 12), cadencia_min=CADENCIA, zona_horaria='UTC')
    with pytest.raises(ValueError, match='BLOQUEADO_POR_DATOS'):
        sc.particionar_dias(corto.instantes, 'UTC', POLITICA_TEMPORAL)


def test_ventanas_identicas_por_modelo():
    """046:RF-5 — las ventanas dependen del dato y de la política, nunca del modelo."""
    c = _conjunto(2, 100)
    a = c.ventanas_comunes(POLITICA_TEMPORAL, contexto_pasos=7 * PUNTOS_DIA, horizonte_max=PUNTOS_DIA, paso=4)
    b = c.ventanas_comunes(POLITICA_TEMPORAL, contexto_pasos=7 * PUNTOS_DIA, horizonte_max=PUNTOS_DIA, paso=4)
    assert a['huella'] == b['huella']
    for nombre in c.nombres:
        assert len(a['partes']['prueba'][nombre])
        assert np.array_equal(a['partes']['prueba'][nombre], b['partes']['prueba'][nombre])


def test_calendario_conocido_y_en_hora_local():
    """046:RF-2 — la única covariable es el calendario local, conocido al emitir."""
    c = pr.construir_conjunto(objetivos(1, 40), cadencia_min=CADENCIA, zona_horaria='America/Lima')
    assert c.calendario.shape == (len(c.instantes), 4)
    assert c.covariables == ('hora_sin', 'hora_cos', 'dia_sin', 'dia_cos')
    # En Lima las 00:00 locales son las 05:00 UTC: el mismo instante local, el mismo calendario.
    i = next(k for k, t in enumerate(c.instantes) if t.hour == 5 and t.minute == 0)
    assert c.calendario[i, 0] == pytest.approx(0.0) and c.calendario[i, 1] == pytest.approx(1.0)


def test_tramos_de_entrenamiento_no_pasan_del_corte():
    """046:RF-1 — el entrenamiento son tramos continuos antes del corte, sin rellenar huecos."""
    v = np.arange(100.0)
    v[40:42] = np.nan
    assert sc.tramos_observados(v, 80, minimo=10) == [(0, 40), (42, 80)]
    assert sc.tramos_observados(v, 80, minimo=39) == [(0, 40)]


def test_adaptador_opcional_no_rompe_gru(monkeypatch):
    """046:RF-14 — sin neuralforecast, ese candidato queda no disponible con su motivo; lo demás sigue."""
    importar = builtins.__import__

    def sin_nf(nombre, *a, **k):
        if nombre.split('.')[0] == 'neuralforecast':
            raise ImportError('neuralforecast no está instalado')
        return importar(nombre, *a, **k)

    for m in [m for m in sys.modules if m.split('.')[0] == 'neuralforecast']:
        monkeypatch.delitem(sys.modules, m)
    monkeypatch.setattr(builtins, '__import__', sin_nf)
    for algoritmo in ('nhits', 'tft', 'patchtst'):
        d = pr.disponibilidad(algoritmo)
        assert d['disponible'] is False and 'neuralforecast' in d['motivo']
    assert pr.disponibilidad('estacional_semanal')['disponible'] is True
    assert pr.disponibilidad('ingenuo')['disponible'] is True
    assert pr.disponibilidad('otro')['disponible'] is False


def test_el_nucleo_arranca_sin_neuralforecast_ni_torch():
    """046:RF-14 — importar el contrato no carga las dependencias opcionales."""
    import subprocess
    codigo = ("import sys;"
              "import convertersmartgrid.digital_twin.pronostico;"
              "import convertersmartgrid.digital_twin.adaptador_neuralforecast;"
              "import convertersmartgrid.digital_twin.evaluacion_temporal;"
              "print(any(m.split('.')[0] in ('neuralforecast','torch','lightning') for m in sys.modules))")
    salida = subprocess.run([sys.executable, '-c', codigo], capture_output=True, text=True, check=True,
                            env={**__import__('os').environ, 'PYTHONPATH': 'src', 'OPENBLAS_NUM_THREADS': '1'})
    assert salida.stdout.strip() == 'False'
