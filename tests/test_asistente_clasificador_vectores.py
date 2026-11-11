"""Spec 026, T15: el clasificador de informes por vectores, elegible junto al de siempre (RF-36 a RF-41).

Los vectores del codificador se sustituyen por unos de palabras con huella (``Falso``): las pruebas no necesitan la GPU
ni el codificador de la caché. La medida real, con los informes de la distribuidora, se hace aparte (ver la tarea T15).
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('sklearn')

from convertersmartgrid.asistente import almacen
from convertersmartgrid.asistente import clasificador as cl
from convertersmartgrid.asistente import clasificador_vectores as cv

RAIZ = Path(__file__).resolve().parents[1]
DIM = 64


class Falso:
    """Vectores de palabras con huella: deterministas y sin GPU."""

    def __init__(self, nombre: str = 'falso/codificador', revision: str = 'r0'):
        self.nombre, self.revision = nombre, revision

    @staticmethod
    def _bolsa(texto: str) -> np.ndarray:
        v = np.zeros(DIM)
        for palabra in cl.normalizar(texto).split():
            v[int(hashlib.sha256(palabra.encode()).hexdigest(), 16) % DIM] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def informe(self, texto: str) -> np.ndarray:
        trozos = [self._bolsa(t) for t in cv.trozos_de_pasaje(texto)]
        return np.concatenate([trozos[0], np.mean(trozos, axis=0)])

    def asunto(self, texto: str) -> np.ndarray:
        return self._bolsa(cv.asunto(texto))


@pytest.fixture
def falso(monkeypatch):
    monkeypatch.setattr(cv, 'FABRICA', Falso)
    monkeypatch.setattr(cv, '_abiertos', {})
    monkeypatch.setattr(cv, 'codificador_por_defecto', lambda: ('falso/codificador', 'r0'))
    from convertersmartgrid.asistente import transformer
    monkeypatch.setattr(transformer, 'liberar_gpu', lambda: None)
    return Falso()


def _reales(semilla: int = 99, por_subtipo: int = 3) -> list[tuple[str, str, str, str]]:
    return [(t, tp, s, f'g{i}') for i, (t, tp, s) in
            enumerate(cl.generar(cl.subtipos_del_perfil(), por_subtipo=por_subtipo, semilla=semilla))]


def _entrenado(falso, elegir_hiper=False):
    plantillas = cl.generar(cl.subtipos_del_perfil(), por_subtipo=15, semilla=cv.SEMILLA_PLANTILLAS)
    return cv.entrenar(_reales(), plantillas, cl.subtipos_del_perfil(), vectorizador=falso, elegir_hiper=elegir_hiper)


def test_026_rf36_segunda_arquitectura_sin_quitar_la_actual(falso):
    """026:RF-36 — se entrena y clasifica en los dos niveles; la red por símbolos sigue elegible."""
    assert set(cl.ARQUITECTURAS) == {'transformer', 'vectores'} and callable(cl.entrenar)
    modelo, info = _entrenado(falso)
    r = modelo.clasificar('informe de factibilidad: solicitud de factibilidad de suministro para 900 kW en el fundo')
    assert r['tipo'] == 'factibilidad' and r['subtipo'] == 'alimentación de carga nueva', r
    assert modelo.clasificar('migración del alimentador QW150 de 10 kV a 22,9 kV')['subtipo'] == 'migración de tensión'
    assert set(r) >= {'tipo', 'confianza_tipo', 'subtipo', 'confianza_subtipo', 'alternativas', 'version'}
    assert all(a != r['subtipo'] for a, _p in r['alternativas']) and len(r['alternativas']) == 2
    assert info['hiper'] == {'tipo': {'C': 50.0, 'peso_plantillas': 0.15}, 'subtipo': {'C': 50.0, 'peso_plantillas': 0.15}}


@pytest.mark.parametrize('clases', [2, 4])
def test_026_rf36_las_matrices_dan_lo_mismo_que_scikit_learn(clases):
    """026:RF-36 — al clasificar no hace falta scikit-learn: las matrices dan sus mismas probabilidades."""
    from sklearn.linear_model import LogisticRegression

    rnd = np.random.default_rng(clases)
    x = rnd.normal(size=(60, 8))
    y = [f'c{i % clases}' for i in range(60)]
    x[:, 0] += [i % clases for i in range(60)]
    clf = LogisticRegression(max_iter=cv.MAX_ITER, C=5.0).fit(x, y)
    propia = cv.ajustar(x, y, [1.0] * 60, cv.Hiper(5.0, 1.0))
    assert propia.clases == list(clf.classes_)
    assert np.allclose(propia.probabilidades(x), clf.predict_proba(x), atol=1e-10)


def test_026_rf37_guarda_sin_pickle_con_su_codificador(falso, tmp_path):
    """026:RF-37 — matrices en pesos.npz (se leen sin pickle), codificador y revisión en modelo.json; reabre igual."""
    modelo, _ = _entrenado(falso)
    carpeta = tmp_path / 'candidato'
    cl.guardar_candidato(modelo, carpeta)
    assert {p.name for p in carpeta.iterdir()} == {'pesos.npz', 'modelo.json', 'readback.json'}
    with np.load(carpeta / 'pesos.npz', allow_pickle=False) as npz:
        assert all(npz[k].dtype == np.float64 for k in npz.files)
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    assert meta['arquitectura'] == cv.ARQUITECTURA and meta['codificador'] == {'nombre': 'falso/codificador', 'revision': 'r0'}
    reabierto = cv.abrir(carpeta)
    for texto in ('estudio de refuerzo de red del tramo SE12345', 'transferencia de carga entre AB101 y AB102'):
        a, b = modelo.clasificar(texto), reabierto.clasificar(texto)
        assert (a['tipo'], a['subtipo']) == (b['tipo'], b['subtipo'])
        assert abs(a['confianza_subtipo'] - b['confianza_subtipo']) < 1e-12
    assert cl.verificar_reapertura(carpeta) == {'ok': True, 'ejemplos': 3, 'proceso_nuevo': True,
                                               'arquitectura': cv.ARQUITECTURA}


def test_026_rf38_rechaza_otros_rasgos_o_matrices_que_no_cuadran(falso, tmp_path):
    """026:RF-38 — otros rasgos, una matriz con objetos (pickle) o de otra forma: error que lo dice."""
    modelo, _ = _entrenado(falso)
    carpeta = tmp_path / 'c'
    cv.guardar(modelo, carpeta)
    ruta_meta = carpeta / 'modelo.json'
    original = ruta_meta.read_text(encoding='utf-8')
    meta = json.loads(original)
    ruta_meta.write_text(json.dumps({**meta, 'rasgos': {**meta['rasgos'], 'trozo': 800}}), encoding='utf-8')
    with pytest.raises(ValueError, match='rasgos'):
        cv.abrir(carpeta)
    ruta_meta.write_text(original, encoding='utf-8')
    with np.load(carpeta / 'pesos.npz', allow_pickle=False) as npz:
        matrices = {k: npz[k] for k in npz.files}
    np.savez(carpeta / 'pesos.npz', **{**matrices, 'tipo_coef': np.array([{'a': 1}], dtype=object)})
    with pytest.raises(ValueError):
        cv.abrir(carpeta)
    np.savez(carpeta / 'pesos.npz', **{**matrices, 'subtipo_coef': matrices['subtipo_coef'][:2]})
    with pytest.raises(ValueError, match='no cuadran'):
        cv.abrir(carpeta)


def test_026_rf40_un_grupo_fuera_no_se_ve_a_si_mismo(monkeypatch):
    """026:RF-40 — cada grupo se predice con un modelo que no vio ninguna de sus versiones; empate, la preferida."""
    vistos: list[set[float]] = []
    original = cv.ajustar

    def espia(x, y, pesos, hiper):
        vistos.append({float(f[0]) for f in x})
        return original(x, y, pesos, hiper)

    monkeypatch.setattr(cv, 'ajustar', espia)
    grupos = [f'g{i // 2}' for i in range(12)]                 # dos versiones por grupo
    x = np.array([[float(i // 2), (i // 2) % 2] for i in range(12)])
    y = ['a' if (i // 2) % 2 else 'b' for i in range(12)]
    acierto = cv.validacion_por_grupo(x, y, grupos, np.zeros((0, 2)), [], cv.PREFERIDO)
    assert 0.0 <= acierto <= 1.0 and len(vistos) == 6
    for g, visto in zip(sorted(set(grupos)), vistos, strict=True):
        assert float(g[1:]) not in visto
    monkeypatch.setattr(cv, 'validacion_por_grupo', lambda *_a: 0.5)
    elegido, medidas = cv.elegir(x, y, grupos, np.zeros((0, 2)), [])
    assert elegido == cv.PREFERIDO and len(medidas) == len(cv.REJILLA)


@pytest.fixture
def almacen_temporal(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    monkeypatch.setattr(cl, '_cache', {})
    for texto, tipo, subtipo, grupo in _reales(semilla=99, por_subtipo=4):
        cl.registrar(texto, tipo, subtipo, 'corregido', grupo=grupo)
    return tmp_path


def test_026_rf39_rf40_rf41_via_gobernada_con_las_mismas_puertas(falso, almacen_temporal, monkeypatch):
    """026:RF-39 — mismas puertas y reapertura; 026:RF-40 — sin los de prueba y con su medida aparte;
    026:RF-41 — el aprobado se abre y clasifica por la carga de siempre."""
    from convertersmartgrid.model_registry import RegistroModelo

    entrada = {}
    entrenar_original = cv.entrenar

    def espia(reales, *a, **k):
        entrada['reales'] = list(reales)
        return entrenar_original(reales, *a, **k)

    monkeypatch.setattr(cv, 'entrenar', espia)
    registro = RegistroModelo(almacen.raiz() / 'model_registry')
    reabiertos = []
    r = cl.entrenar_gobernado(registro, almacen_temporal / 'cand', minimo_subtipo=0.0, arquitectura='vectores',
                              reabrir=lambda c: reabiertos.append(c) or cl.verificar_reapertura(c))
    assert r['arquitectura'] == 'vectores' and r['status'] == 'PROMOVIDO' and r['promovido'] is True, r
    assert reabiertos and r['candidato']['status'] == 'PROMOVIDO'
    detalle = registro.detalle('clasificador', r['candidato']['candidate_id'])
    assert detalle['model_manifest']['algorithm'] == 'vectores_e5_logistica'
    assert detalle['model_manifest']['codificador'] == {'nombre': 'falso/codificador', 'revision': 'r0'}
    assert set(detalle['artifacts']) == {'pesos.npz', 'modelo.json', 'readback.json'}
    assert {'candidato', 'reales', 'eleccion_grupo_fuera'} <= set(detalle['metrics'])
    assert 'tipo|subtipo' in detalle['metrics']['eleccion_grupo_fuera']['grupo_fuera']
    _ent, prueba = cl.reales()
    textos_prueba = {t for t, _tp, _s in prueba}
    assert entrada['reales'] and not textos_prueba & {t for t, *_ in entrada['reales']}
    assert not cl._grupos_de_prueba(cl._validos()) & {g for *_r, g in entrada['reales']}
    modelo = cl.cargar()
    assert isinstance(modelo, cv.ClasificadorVectores) and modelo.version == r['version']
    assert modelo.clasificar('migración del alimentador ZX201 de 10 kV a 22,9 kV')['subtipo'] == 'migración de tensión'

    # Las puertas de siempre: la de reales (RF-35) rechaza aunque la prueba mezclada pase.
    monkeypatch.setattr(cl, 'evaluar', lambda _m, ej: {'acierto_tipo': 1.0, 'acierto_subtipo': 1.0 if len(ej) > 20 else 0.5,
                                                       'ejemplos': len(ej)})
    r2 = cl.entrenar_gobernado(registro, almacen_temporal / 'cand2', minimo_subtipo=0.9, arquitectura='vectores',
                               reabrir=cl.verificar_reapertura)
    assert r2['status'] == 'RECHAZADO' and any(f.startswith('reales: acierto_subtipo') for f in r2['fallos'])
    assert cl.cargar().version == r['version']
    with pytest.raises(ValueError, match='desconocida'):
        cl.entrenar_gobernado(registro, almacen_temporal / 'cand3', arquitectura='otra')


def test_026_rf39_herramienta_lleva_la_arquitectura(tmp_path, monkeypatch):
    """026:RF-39 — ``--arquitectura vectores`` va con ``--solo informes`` hasta la vía gobernada; sola, es un error."""
    especificacion = importlib.util.spec_from_file_location('asistente_entrenar_026', RAIZ / 'tools/asistente_entrenar.py')
    herramienta = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(herramienta)
    with pytest.raises(SystemExit):
        herramienta.main(['--output-json', str(tmp_path / 'x.json'), '--arquitectura', 'vectores'])
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))
    import convertersmartgrid.digital_twin.oraculo as oraculo
    import convertersmartgrid.trabajadores_ml as tml

    monkeypatch.setattr(oraculo, 'dispositivo', lambda: 'cuda')
    monkeypatch.setattr(tml, 'turno_gpu', lambda _n: contextlib.nullcontext())
    llamadas = []
    monkeypatch.setattr(cl, 'entrenar_gobernado', lambda *_a, **k: llamadas.append(k['arquitectura']) or {'status': 'X'})
    salida = tmp_path / 'informes.json'
    assert herramienta.main(['--output-json', str(salida), '--solo', 'informes', '--arquitectura', 'vectores']) == 0
    assert herramienta.main(['--output-json', str(salida), '--solo', 'informes']) == 0
    assert llamadas == ['vectores', 'transformer']
