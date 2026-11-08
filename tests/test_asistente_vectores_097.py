"""Spec 097: el modelo de los vectores del índice del asistente y sus prefijos, sin mezclar modelos."""
from __future__ import annotations

import random

from convertersmartgrid.asistente import indice


def test_prefijos_por_ficha_y_modelo_elegible(monkeypatch):
    """097:RF-3 — cada modelo con los prefijos de su ficha; el modelo en uso se puede elegir para medir otro."""
    assert indice.prefijos('nomic-embed-text') == ('search_query: ', 'search_document: ')
    assert indice.prefijos('bge-m3:latest') == ('', '')
    monkeypatch.delenv(indice.VARIABLE_MODELO, raising=False)
    assert indice.modelo_vectores() == 'nomic-embed-text'
    monkeypatch.setenv(indice.VARIABLE_MODELO, 'bge-m3')
    assert indice.modelo_vectores() == 'bge-m3'


def test_vectores_de_otro_modelo_no_cuentan_y_se_recalculan(tmp_path, monkeypatch):
    """097:RF-1, 097:RF-2 — guardados con un modelo, con otro valen como no tenerlos y se vuelven a pedir con el nuevo."""
    rnd = random.Random(97)
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    monkeypatch.setenv(indice.VARIABLE_MODELO, 'nomic-embed-text')
    claves = {f'c{i}': [rnd.random() for _ in range(4)] for i in range(rnd.randint(3, 9))}
    indice._guardar_vectores(claves)
    matriz, filas = indice._leer_vectores()
    assert matriz is not None and set(filas) == set(claves)
    monkeypatch.setenv(indice.VARIABLE_MODELO, 'bge-m3')
    assert indice._leer_vectores() == (None, {})

    class Ollama:
        def __init__(self):
            self.pedidos = []

        def embeddings(self, textos, modelo='nomic-embed-text'):
            self.pedidos.append((modelo, list(textos)))
            return [[1.0, 0.0, 0.0, 0.0] for _ in textos]

    o = Ollama()
    monkeypatch.setattr(indice, 'cargar_o_construir', lambda repo, corpus=indice.CORPUS_047: indice.Indice(
        [indice.Fragmento(id=i, fuente='a.md', texto=f'texto {i}') for i in range(3)], corpus=corpus))
    r = indice.calcular_vectores(tmp_path, o)
    assert r['estado'] == 'completo' and r['con_vector'] == 3
    assert {m for m, _ in o.pedidos} == {'bge-m3'}
    assert all(not t.startswith('search_document: ') for _, ts in o.pedidos for t in ts)      # bge-m3, sin prefijo


def test_se_elige_el_de_mayor_mrr_y_a_igualdad_el_de_mayor_recall():
    """097:RF-4 — el de mayor MRR@10 con la calibración; a igualdad, Recall@10; sin cifras no compite."""
    rnd = random.Random(974)
    medidas = {f'm{i}': {'mrr@10': rnd.uniform(0.2, 0.6), 'recall@10': rnd.uniform(0.3, 0.8)} for i in range(5)}
    mejor = max(medidas, key=lambda m: medidas[m]['mrr@10'])
    assert indice.elegir_modelo_vectores(medidas) == mejor
    empate = {'a': {'mrr@10': 0.4, 'recall@10': 0.5}, 'b': {'mrr@10': 0.4, 'recall@10': 0.7}, 'c': {'error': 'sin vectores'}}
    assert indice.elegir_modelo_vectores(empate) == 'b'
    assert indice.elegir_modelo_vectores({'c': {'error': 'no instalado'}}) is None


def test_la_herramienta_compara_los_informes_de_cada_modelo(tmp_path, capsys):
    """097:RF-4 — `asistente_evaluar_rag.py --comparar` lee el híbrido de cada informe y dice cuál se elige."""
    import json

    from apoyo import cargar_herramienta

    herramienta = cargar_herramienta('asistente_evaluar_rag.py')
    rutas = []
    for modelo, mrr in (('nomic-embed-text', 0.31), ('bge-m3', 0.44)):
        ruta = tmp_path / f'{modelo}.json'
        ruta.write_text(json.dumps({'modelo_vectores': modelo, 'metodos': {'hibrido': {'mrr@10': mrr, 'recall@10': 0.5}}}),
                        encoding='utf-8')
        rutas.append(str(ruta))
    assert herramienta.main(['--comparar', *rutas]) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida['elegido'] == 'bge-m3' and set(salida['medidas']) == {'nomic-embed-text', 'bge-m3'}


def test_las_anclas_perdidas_no_paran_ninguno_de_los_dos_corpus():
    """097:RF-8 — el apartado de filas sin ancla (077:RF-49) vale para el corpus 047, no solo para el 077."""
    from pathlib import Path

    fuente = (Path(__file__).resolve().parents[1] / 'tools' / 'asistente_evaluar_rag.py').read_text(encoding='utf-8')
    assert 'evaluacion_rag.sin_anclas_perdidas(conjunto, i.frags)' in fuente
    antes = fuente.split('evaluacion_rag.sin_anclas_perdidas(conjunto, i.frags)')[0].rstrip().splitlines()
    assert antes[-2].strip() == 'try:' and 'if ampliado' not in antes[-3]
