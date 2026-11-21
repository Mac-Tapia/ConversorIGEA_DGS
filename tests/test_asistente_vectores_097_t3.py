"""Spec 097 T3 (2026-11-13): elección del modelo de vectores con intervalo, puntero en uso y conjunto del operador."""
from __future__ import annotations

import inspect
import json
import random
from pathlib import Path

import pytest
from apoyo import cargar_herramienta

from convertersmartgrid.aplicacion.asistente import evaluacion_rag, indice, reranker

RAIZ = Path(__file__).resolve().parents[1]


def _filas_calibracion(rnd, n_con=37, n_sin=40, separacion=1.0):
    """Señales sorteadas: las preguntas con respuesta puntúan más, con solape según ``separacion``."""
    filas = []
    for i in range(n_con + n_sin):
        responde = i < n_con
        base = separacion if responde else 0.0
        filas.append({'grupo': f'g{i}', 'responde': responde, 'codigo': False, 'tipo': 'spec' if responde else 'fuera',
                      'bm25': rnd.gauss(10 + 4 * base, 3), 'coseno': rnd.gauss(0.5 + 0.1 * base, 0.08),
                      'reranker': rnd.gauss(base, 1)})
    return filas


def test_la_calibracion_guarda_las_senales_de_cada_pregunta_sin_su_texto():
    """097:RF-9 — con los umbrales van las señales por pregunta (huella, respuesta, tipo), nunca el texto."""
    rnd = random.Random(9)
    filas = [{**f, 'pregunta': f'¿pregunta {i}?'} for i, f in enumerate(_filas_calibracion(rnd))]
    informe = evaluacion_rag.calibracion_con_senales(filas)
    assert informe['umbrales'] == evaluacion_rag.calibrar(filas)['umbrales']
    assert len(informe['por_pregunta']) == len(filas)
    assert all('pregunta' not in x and {'grupo', 'responde', 'tipo', 'bm25', 'coseno', 'reranker'} <= set(x)
               for x in informe['por_pregunta'])


def test_leer_puntuaciones_lleva_la_huella_y_el_tipo_de_cada_pregunta():
    """097:RF-9 — cada fila de señales lleva la huella de la pregunta y su tipo para remuestrear y desglosar."""
    frags = [indice.Fragmento(id=i, fuente=f'specs/001-x/spec.md:{i}', texto=f'RF-{i}: calibrar barra {i}') for i in range(5)]
    conjunto = {'preguntas': [{'pregunta': 'como calibrar barra', 'fichero': 'specs/001-x/spec.md', 'ancla': 'RF-1:',
                               'tipo': 'spec'},
                              {'pregunta': 'receta de cocina', 'sin_respuesta': True, 'tipo': 'fuera'}]}
    filas = evaluacion_rag.leer_puntuaciones(indice.Indice(frags), conjunto, lambda q: None,
                                             lambda q, textos: [0.0 for _ in textos], 'm')
    assert [f['tipo'] for f in filas] == ['spec', 'fuera']
    assert filas[0]['grupo'] == evaluacion_rag._grupo('como calibrar barra')


def test_conserva_del_hibrido_con_su_intervalo_bootstrap_recalibrando():
    """097:RF-10 — la cifra puntual es la de ``calibrar`` y el IC95 % la contiene."""
    semilla = random.randint(0, 10**6)
    rnd = random.Random(semilla)
    filas = _filas_calibracion(rnd, n_con=rnd.randint(20, 40), n_sin=rnd.randint(20, 40))
    r = evaluacion_rag.conserva_con_intervalo(filas, remuestreos=300, semilla=semilla)
    assert r['conserva'] == pytest.approx(evaluacion_rag.calibrar(filas)['en_calibracion']['hibrido']['conserva'])
    assert r['ic95'][0] <= r['conserva'] <= r['ic95'][1]
    assert r['n_con'] == sum(f['responde'] for f in filas) and r['remuestreos'] == 300


def test_eleccion_declarada_fuera_el_superado_y_luego_latencia_o_memoria():
    """097:RF-11 — fuera el superado con IC pareado sobre cero; entre los no separados, latencia (>20 %) o memoria."""
    rnd = random.Random(11)
    buenas = _filas_calibracion(rnd, separacion=3.0)
    flojas = [{**f, 'coseno': f['coseno'] - (0.4 if f['responde'] else 0.0), 'bm25': f['bm25'] - (12 if f['responde'] else 0)}
              for f in buenas]
    por_corpus = {c: {'a': buenas, 'b': [dict(f) for f in buenas], 'malo': flojas} for c in ('047', '077')}
    recursos = {'a': {'latencia_p95_ms': 30.0, 'memoria_gpu_mib': 1500}, 'b': {'latencia_p95_ms': 32.0, 'memoria_gpu_mib': 900},
                'malo': {'latencia_p95_ms': 5.0, 'memoria_gpu_mib': 100}}
    # 097:RF-24: los tres con el mismo Recall@10 sellado que el en uso («b»), para que decida la regla de RF-11.
    sellados = {m: _medicion(m, random.Random(11)) for m in ('a', 'b', 'malo')}
    elegir = {'sellados': sellados, 'en_uso': 'b'}
    d = evaluacion_rag.elegir_con_intervalo(por_corpus, recursos, remuestreos=300, **elegir)
    assert 'malo' in d['fuera'] and d['elegido'] == 'b'                 # latencia a menos del 20 %: decide la memoria
    recursos['a']['latencia_p95_ms'] = 10.0
    assert evaluacion_rag.elegir_con_intervalo(por_corpus, recursos, remuestreos=300, **elegir)['elegido'] == 'a'
    sin_077 = {'047': por_corpus['047'], '077': {'a': buenas}}
    assert set(evaluacion_rag.elegir_con_intervalo(sin_077, recursos, remuestreos=50, **elegir)['compiten']) == {'a'}


class _Ollama:
    modelo = 'x'

    def __init__(self):
        self.pedidos = []

    def embeddings(self, textos, modelo='nomic-embed-text'):
        self.pedidos.append((modelo, list(textos)))
        return [[1.0, 0.0] for _ in textos]

    def responder(self, *a, **k):
        return None


def test_el_modelo_en_uso_sale_del_puntero_y_la_consulta_lleva_su_prefijo(tmp_path, monkeypatch):
    """097:RF-12, 097:RF-3 — con el puntero en e5, la consulta va a e5 con «query: »; sin ficha o sin puntero, nomic."""
    import numpy as np

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.delenv(indice.VARIABLE_MODELO, raising=False)
    assert indice.modelo_vectores() == 'nomic-embed-text'
    e5 = 'jeffh/intfloat-multilingual-e5-large:f16'
    (tmp_path / indice.PUNTERO_VECTORES).write_text(json.dumps({'modelo': e5}), encoding='utf-8')
    assert indice.modelo_vectores() == e5 and indice.prefijos() == ('query: ', 'passage: ')
    i = indice.Indice([indice.Fragmento(id=0, fuente='a.md:1', texto='calibrar una barra sin medidor')],
                      np.asarray([[1.0, 0.0]], dtype='float32'), [0])
    o = _Ollama()
    indice.responder(i, 'cómo se calibra una barra', o)
    assert o.pedidos == [(e5, ['query: cómo se calibra una barra'])]
    (tmp_path / indice.PUNTERO_VECTORES).write_text(json.dumps({'modelo': 'bge-m3'}), encoding='utf-8')
    o = _Ollama()
    indice.responder(i, 'cómo se calibra una barra', o)
    assert o.pedidos == [('bge-m3', ['cómo se calibra una barra'])]           # bge-m3 sin instrucción
    (tmp_path / indice.PUNTERO_VECTORES).write_text(json.dumps({'modelo': 'inventado-sin-ficha'}), encoding='utf-8')
    assert indice.modelo_vectores() == 'nomic-embed-text'


def test_calibracion_de_otro_modelo_de_vectores_no_vale(tmp_path, monkeypatch):
    """097:RF-13 — los umbrales de coseno de bge-m3 no sirven a nomic; sin modelo anotado, la calibración es de nomic."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.delenv(indice.VARIABLE_MODELO, raising=False)
    conjunto = tmp_path / 'conjunto.json'
    conjunto.write_text('{"preguntas": []}', encoding='utf-8')
    modelo = reranker.MODELOS[1]
    base = {'conjunto_sha256': reranker.sha256_de(conjunto), 'modelo_reranker': modelo,
            'revision': reranker.ficha_modelo(modelo)['revision'], 'umbrales': {'coseno': 0.6, 'bm25': 15.0}}
    cal = tmp_path / 'cal.json'
    cal.write_text(json.dumps(base), encoding='utf-8')
    assert reranker.abstencion(cal, conjunto).calibrada is True             # la histórica, sin modelo anotado: nomic
    cal.write_text(json.dumps({**base, 'modelo_vectores': 'bge-m3'}), encoding='utf-8')
    assert reranker.abstencion(cal, conjunto).calibrada is False
    monkeypatch.setenv(indice.VARIABLE_MODELO, 'bge-m3')
    assert reranker.abstencion(cal, conjunto).calibrada is True


def _medicion(modelo, rnd, recall=0.95, abst=0.95, n=40):
    filas = [{'group_id': f'q{i}', 'answerable': True, 'reciprocal_rank@10': rnd.choice((1.0, 0.5)),
              'recall@10': 1.0 if i < recall * n else 0.0} for i in range(n)]
    metodo = {'recall@10': recall, 'mrr@10': sum(f['reciprocal_rank@10'] for f in filas) / n,
              'abstention_accuracy': abst, 'per_query': filas}
    # 097:RF-25: la misma huella y los mismos denominadores, o la puerta no compara.
    return {'modelo_vectores': modelo, 'corpus': '047', 'conjunto_sha256': 'c' * 64, 'preguntas': n, 'con_respuesta': n,
            'metodos': {'reranker': metodo}}


def test_poner_en_uso_solo_si_pasa_la_puerta_frente_al_en_uso(tmp_path, monkeypatch):
    """097:RF-14, 097:RF-5, 097:RF-6 — el puntero se escribe solo si la sellada del elegido pasa frente a la del en uso."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.delenv(indice.VARIABLE_MODELO, raising=False)
    en_uso = _medicion(None, random.Random(14))
    peor = _medicion('bge-m3', random.Random(14), recall=0.80)
    r = evaluacion_rag.poner_en_uso('bge-m3', peor, en_uso, calibraciones={'047': 'c.json'}, escribir=True)
    assert r['puesto'] is False and any('Recall@10' in m for m in r['motivos'])
    assert not (tmp_path / indice.PUNTERO_VECTORES).exists() and indice.modelo_vectores() == 'nomic-embed-text'
    otro = evaluacion_rag.poner_en_uso('bge-m3', _medicion('e5', random.Random(14)), en_uso, calibraciones={}, escribir=True)
    assert otro['puesto'] is False and any('modelo' in m for m in otro['motivos'])
    bien = _medicion('bge-m3', random.Random(14))
    seco = evaluacion_rag.poner_en_uso('bge-m3', bien, en_uso, calibraciones={'047': 'c.json'}, escribir=False)
    assert seco['puesto'] is False and seco['motivos'] == [] and not (tmp_path / indice.PUNTERO_VECTORES).exists()
    hecho = evaluacion_rag.poner_en_uso('bge-m3', bien, en_uso, calibraciones={'047': 'c.json'}, escribir=True)
    assert hecho['puesto'] is True and indice.modelo_vectores() == 'bge-m3'
    assert json.loads((tmp_path / indice.PUNTERO_VECTORES).read_text(encoding='utf-8'))['calibraciones'] == {'047': 'c.json'}


def test_metricas_de_recuperacion_con_intervalo_y_desglose_por_tipo():
    """097:RF-15 — cada métrica con su IC95 % y su desglose por tipo de pregunta."""
    rnd = random.Random(15)
    filas = []
    for i in range(rnd.randint(30, 60)):
        r = rnd.random()
        filas.append({'group_id': f'q{i}', 'answerable': True, 'recall@1': float(r > 0.5), 'recall@5': float(r > 0.3),
                      'recall@10': float(r > 0.1), 'reciprocal_rank@10': r, 'ndcg@10': r, 'exact_citation@1': float(r > 0.5)})
    filas.append({'group_id': 'x', 'answerable': False, 'abstained': True})
    medido = {'per_query': filas, 'latencias_ms': [rnd.uniform(5, 50) for _ in filas]}
    tipo = {f['group_id']: ('spec' if i % 2 else 'funcion') for i, f in enumerate(filas)}
    r = evaluacion_rag.con_intervalos(medido, tipo, remuestreos=200)
    for m in ('recall@1', 'recall@5', 'recall@10', 'mrr@10', 'ndcg@10', 'exact_citation@1', 'latencia_p95_ms'):
        assert r['global'][m]['ic95'][0] <= r['global'][m]['valor'] <= r['global'][m]['ic95'][1], m
    assert set(r['por_tipo']) == {'spec', 'funcion'} and sum(x['n'] for x in r['por_tipo'].values()) == len(filas) - 1


def test_las_latencias_de_cada_pregunta_quedan_en_la_medicion():
    """097:RF-15 — ``_medir`` guarda la latencia de cada pregunta para su intervalo, no solo el p95."""
    pares = [evaluacion_rag.ParContraste(f'p{i}', ('a',), (), True, f'g{i}') for i in range(7)]
    medido = evaluacion_rag._medir(pares, lambda q, k: [{'fuente': 'a'}])
    assert len(medido['latencias_ms']) == 7 and medido['latencia_p95_ms'] == max(medido['latencias_ms'])


def test_preguntas_del_operador_en_conjunto_propio_y_medidas_aparte(tmp_path):
    """097:RF-16, 097:RF-17 — el conjunto del operador declara su procedencia y nunca se mezcla con el sintético."""
    real = RAIZ / 'docs' / 'RAG_PREGUNTAS_OPERADOR_097.json'
    conjunto = evaluacion_rag.cargar_conjunto_operador(real)
    assert conjunto['procedencia'] == evaluacion_rag.PROCEDENCIA_OPERADOR and conjunto['sha256']
    assert conjunto['preguntas'] and all(f.get('origen') == 'operador' for f in conjunto['preguntas'])
    with pytest.raises(ValueError):
        evaluacion_rag.cargar_conjunto(real)                             # no pasa por sintético (027:RF-42)
    sintetico = tmp_path / 's.json'
    sintetico.write_text(json.dumps({'procedencia': 'sintetico_maestro', 'preguntas': []}), encoding='utf-8')
    with pytest.raises(ValueError):
        evaluacion_rag.cargar_conjunto_operador(sintetico)
    partes = evaluacion_rag.por_procedencia({'sintetico': {'recall@10': 0.9, 'n': 40}, 'operador': {'recall@10': 0.5, 'n': 6}})
    assert set(partes) == {'sintetico', 'operador'} and all('total' not in str(k) for k in partes)
    with pytest.raises(ValueError):
        evaluacion_rag.por_procedencia({'sintetico': {}, 'operador': {}, 'total': {}})


def test_la_herramienta_calibra_con_senales_y_sella_con_la_calibracion_de_su_modelo():
    """097:RF-9, 097:RF-13 — la herramienta guarda las señales y el sellado usa ``--calibracion`` del mismo modelo."""
    fuente = (RAIZ / 'tools' / 'asistente_evaluar_rag.py').read_text(encoding='utf-8')
    assert 'evaluacion_rag.calibracion_con_senales(' in fuente
    assert "'--calibracion'" in fuente and 'latencia_consulta_p95_ms' in fuente and 'memoria_gpu_mib' in fuente


def test_una_fuente_movida_de_carpeta_se_sigue_por_su_nombre_unico():
    """097:RF-18 — el fichero que cambió de carpeta se sigue si su nombre es único; si hay dos, la fila queda perdida."""
    frags = [indice.Fragmento(id=0, fuente='frontend/src/features/conversion/InputsPanel.tsx:10', texto='x <FileDrop y'),
             indice.Fragmento(id=1, fuente='frontend/src/features/a/Panel.tsx:3', texto='<FileDrop'),
             indice.Fragmento(id=2, fuente='frontend/src/features/b/Panel.tsx:3', texto='<FileDrop')]
    conjunto = {'preguntas': [
        {'pregunta': 'movida', 'fuentes': [{'fichero': 'frontend/src/components/InputsPanel.tsx', 'ancla': '<FileDrop'}]},
        {'pregunta': 'ambigua', 'fuentes': [{'fichero': 'frontend/src/components/Panel.tsx', 'ancla': '<FileDrop'}]},
        {'pregunta': 'editada', 'fuentes': [{'fichero': 'frontend/src/components/InputsPanel.tsx', 'ancla': '<Otra'}]}]}
    antes = json.dumps(conjunto, sort_keys=True)
    pares, sin_ancla, _ = evaluacion_rag.resolver_pares(conjunto, frags)
    assert [p.positive_ids for p in pares] == [('frontend/src/features/conversion/InputsPanel.tsx:10',)]
    assert sin_ancla == ['ambigua', 'editada'] and json.dumps(conjunto, sort_keys=True) == antes


def test_097_rf19_no_calibra_por_debajo_de_la_muestra_minima_y_dice_cuantas_faltan():
    """097:RF-19 — con 25 sin respuesta (la calibración real del 077 sin las del corpus) el umbral sería el máximo: se niega."""
    rnd = random.Random()
    sin, con = rnd.randint(1, evaluacion_rag.MINIMO_SIN_RESPUESTA - 1), rnd.randint(evaluacion_rag.MINIMO_CON_RESPUESTA, 200)
    conjunto = {'preguntas': [{'pregunta': f's{i}', 'sin_respuesta': True} for i in range(sin)]
                + [{'pregunta': f'c{i}', 'fuentes': []} for i in range(con)]}
    with pytest.raises(ValueError, match=f'faltan {evaluacion_rag.MINIMO_SIN_RESPUESTA - sin} sin respuesta'):
        evaluacion_rag.muestra_suficiente(conjunto)
    conjunto['preguntas'] += [{'pregunta': f'n{i}', 'sin_respuesta': True}
                              for i in range(evaluacion_rag.MINIMO_SIN_RESPUESTA - sin)]
    assert evaluacion_rag.muestra_suficiente(conjunto) == {
        'sin_respuesta': evaluacion_rag.MINIMO_SIN_RESPUESTA, 'con_respuesta': con}


def test_097_rf19_la_herramienta_comprueba_la_muestra_antes_de_ocupar_la_gpu():
    """097:RF-19 — la comprobación va antes del turno de GPU, como la de las anclas perdidas (077:RF-49)."""
    fuente = (RAIZ / 'tools' / 'asistente_evaluar_rag.py').read_text(encoding='utf-8')
    assert -1 < fuente.index('evaluacion_rag.muestra_suficiente(conjunto)') < fuente.index("with turno_gpu('rag')")


# --- T6 (2026-11-21): la elección y la puerta comparan el Recall@10 sellado sobre las mismas preguntas --------------------

HUELLA = '2faeb8c3' + '0' * 56
EN_USO = 'nomic-embed-text'
BGE = 'bge-m3'
E5 = 'jeffh/intfloat-multilingual-e5-large:f16'


def _sellada(modelo, recall, *, con=39, preguntas=79, huella=HUELLA, corpus='047'):
    """Una medición sellada del 047 con sus denominadores, como las de la T5: 79 preguntas, 39 con respuesta."""
    aciertos = round(recall * con)
    filas = [{'group_id': f'q{i}', 'answerable': True, 'reciprocal_rank@10': 1.0 if i < aciertos else 0.0,
              'recall@10': 1.0 if i < aciertos else 0.0} for i in range(con)]
    metodo = {'recall@10': aciertos / con, 'mrr@10': aciertos / con, 'abstention_accuracy': 0.95, 'per_query': filas}
    return {'modelo_vectores': modelo, 'corpus': corpus, 'conjunto_sha256': huella, 'preguntas': preguntas,
            'con_respuesta': con, 'metodos': {'reranker': metodo}}


def _calibraciones_sin_separar(semilla):
    """Las tres con las mismas señales: ninguno queda fuera por «conserva» y decide la latencia, como en la T5."""
    filas = _filas_calibracion(random.Random(semilla))
    return {c: {m: [dict(f) for f in filas] for m in (BGE, E5, EN_USO)} for c in ('047', '077')}


RECURSOS_T5 = {BGE: {'latencia_p95_ms': 69.1, 'memoria_gpu_mib': 657.3},
               E5: {'latencia_p95_ms': 87.0, 'memoria_gpu_mib': 595.7},
               EN_USO: {'latencia_p95_ms': 86.1, 'memoria_gpu_mib': 320.2}}


def _cli(argv, capsys):
    """La herramienta con ``argv``: su código de salida (también el de argparse) y lo que escribió."""
    guion = cargar_herramienta('asistente_evaluar_rag.py', 'asistente_evaluar_rag_t6')
    try:
        rc = guion.main(argv)
    except SystemExit as exc:
        rc = exc.code
    salida = capsys.readouterr()
    return rc, salida.out, salida.err


def _escribir(ruta, datos):
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return ruta


def _calibracion_fichero(tmp_path, modelo, corpus, filas):
    nombre = modelo.replace('/', '_').replace(':', '_')
    return _escribir(tmp_path / f'calibra_{corpus}_{nombre}.json',
                     {'modelo_vectores': modelo, 'corpus': corpus, 'por_pregunta': filas,
                      'recursos': {'latencia_consulta_p95_ms': RECURSOS_T5[modelo]['latencia_p95_ms'],
                                   'memoria_gpu_mib': RECURSOS_T5[modelo]['memoria_gpu_mib']}})


def test_097_rf24_la_eleccion_deja_fuera_al_que_baja_el_recall_sellado_frente_al_en_uso(tmp_path, capsys, monkeypatch):
    """097:RF-24 — el caso de la T5: bge-m3 gana por latencia, pero su sellado baja de 0,974 a 0,949 frente a nomic
    sobre las mismas 79 preguntas, y e5 no tiene sellado: se queda nomic-embed-text."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.delenv(indice.VARIABLE_MODELO, raising=False)
    semilla = random.randint(0, 10**6)
    por_corpus = _calibraciones_sin_separar(semilla)
    calibraciones = [_calibracion_fichero(tmp_path, m, c, por_corpus[c][m]) for c in por_corpus for m in por_corpus[c]]
    sellados = [_escribir(tmp_path / 'sel_nomic.json', _sellada(EN_USO, 38 / 39)),
                _escribir(tmp_path / 'sel_bge.json', _sellada(BGE, 37 / 39))]
    salida = tmp_path / 'eleccion.json'
    rc, _, err = _cli(['--elegir', *map(str, calibraciones), '--sellados', *map(str, sellados), '--remuestreos', '200',
                       '--salida', str(salida)], capsys)
    assert rc == 0, (semilla, err)
    d = json.loads(salida.read_text(encoding='utf-8'))
    assert d['elegido'] == EN_USO and d['en_uso'] == EN_USO, semilla
    assert 'Recall@10 sellado del reranker baja de 0.974 a 0.949' in d['fuera'][BGE], d['fuera']
    assert '39 con respuesta de 79' in d['fuera'][BGE] and 'sin medición sellada' in d['fuera'][E5]
    assert '097:RF-24' in d['regla']


def test_097_rf24_sin_bajar_el_recall_sellado_decide_la_latencia_como_antes():
    """097:RF-24, 097:RF-11 — si el sellado de bge-m3 no baja, la regla de siempre lo elige por latencia; sin el
    sellado del en uso, ninguno distinto de él pasa."""
    assert 'sellados' in inspect.signature(evaluacion_rag.elegir_con_intervalo).parameters, 'la elección no lee sellados'
    semilla = random.randint(0, 10**6)
    por_corpus = _calibraciones_sin_separar(semilla)
    iguales = {EN_USO: _sellada(EN_USO, 38 / 39), BGE: _sellada(BGE, 38 / 39), E5: _sellada(E5, 39 / 39)}
    d = evaluacion_rag.elegir_con_intervalo(por_corpus, RECURSOS_T5, remuestreos=100, semilla=semilla, sellados=iguales,
                                            en_uso=EN_USO)
    assert d['fuera'] == {} and d['elegido'] == BGE and d['decide'] == 'latencia p95 de la consulta', semilla
    sin_uso = {BGE: iguales[BGE], E5: iguales[E5]}
    d = evaluacion_rag.elegir_con_intervalo(por_corpus, RECURSOS_T5, remuestreos=50, semilla=semilla, sellados=sin_uso,
                                            en_uso=EN_USO)
    assert set(d['fuera']) == {BGE, E5} and d['elegido'] == EN_USO, semilla
    assert all('modelo en uso' in m for m in d['fuera'].values())


def test_097_rf24_un_sellado_de_otros_denominadores_no_cuenta_para_elegir():
    """097:RF-24, 097:RF-25 — con 80 y 40 frente a 79 y 39, el Recall@10 no se compara y el candidato queda fuera."""
    assert 'sellados' in inspect.signature(evaluacion_rag.elegir_con_intervalo).parameters, 'la elección no lee sellados'
    semilla = random.randint(0, 10**6)
    por_corpus = _calibraciones_sin_separar(semilla)
    sellados = {EN_USO: _sellada(EN_USO, 0.95, con=40, preguntas=80), BGE: _sellada(BGE, 38 / 39),
                E5: _sellada(E5, 38 / 39, huella='otra' + '0' * 60)}
    d = evaluacion_rag.elegir_con_intervalo(por_corpus, RECURSOS_T5, remuestreos=50, semilla=semilla, sellados=sellados,
                                            en_uso=EN_USO)
    assert d['elegido'] == EN_USO, semilla
    assert 'denominadores distintos' in d['fuera'][BGE] and '40 con respuesta de 80' in d['fuera'][BGE]
    assert 'mismo conjunto sellado' in d['fuera'][E5]


def test_097_rf25_la_puerta_compara_con_el_en_uso_sobre_las_mismas_preguntas_y_dice_los_denominadores(tmp_path,
                                                                                                    monkeypatch):
    """097:RF-25, 097:RF-14 — el caso de la T5: frente al documento de 80 y 40 la puerta no compara (lo dice con los dos
    denominadores); frente a nomic con las mismas 79 y 39, rechaza porque baja de 0,974 a 0,949."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.delenv(indice.VARIABLE_MODELO, raising=False)
    bge = _sellada(BGE, 37 / 39)
    documento = _sellada(None, 0.95, con=40, preguntas=80)
    r = evaluacion_rag.poner_en_uso(BGE, bge, documento, calibraciones={'047': 'c.json'}, escribir=True)
    assert r['puesto'] is False
    assert not any(m.startswith('Recall@10 baja de 0.950') for m in r['motivos']), r['motivos']
    assert any('39 con respuesta de 79' in m and '40 con respuesta de 80' in m for m in r['motivos']), r['motivos']
    mismas = _sellada(EN_USO, 38 / 39)
    r = evaluacion_rag.poner_en_uso(BGE, bge, mismas, calibraciones={'047': 'c.json'}, escribir=True)
    assert r['puesto'] is False and not (tmp_path / indice.PUNTERO_VECTORES).exists()
    esperado = ('Recall@10 baja de 0.974 a 0.949 (nomic-embed-text: 39 con respuesta de 79; '
                'bge-m3: 39 con respuesta de 79)')
    assert r['motivos'] == [esperado], r['motivos']
    otra = evaluacion_rag.poner_en_uso(BGE, bge, _sellada(E5, 38 / 39), calibraciones={'047': 'c.json'}, escribir=True)
    assert any('no del en uso' in m for m in otra['motivos']) and otra['puesto'] is False


def test_097_rf25_la_herramienta_pide_la_medicion_del_en_uso_y_no_toma_el_documento_por_defecto(tmp_path, capsys,
                                                                                               monkeypatch):
    """097:RF-25 — ``--poner-en-uso`` sin ``--sellado-en-uso`` no se compara con docs/EVALUACION_ABSTENCION_047.json."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.setenv(indice.VARIABLE_MODELO, EN_USO)                  # la herramienta lo cambia: se restaura al salir
    sel = _escribir(tmp_path / 'sel_bge.json', _sellada(BGE, 37 / 39))
    rc, _, err = _cli(['--poner-en-uso', BGE, '--sellado-047', str(sel)], capsys)
    assert rc == 2 and '--sellado-en-uso' in err, err
    rc, _, err = _cli(['--elegir', str(sel)], capsys)
    assert rc == 2 and '--sellados' in err, err
