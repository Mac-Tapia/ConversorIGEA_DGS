"""043:RF-13 / 047:RF-3: contratos de recuperacion; fixtures no son evidencia electrica real."""
from __future__ import annotations

import json

import pytest

from convertersmartgrid.asistente.embeddings import (
    ParContraste,
    construir_dataset_contrastivo,
    construir_preguntas_extractivas,
    comparar_pareado,
    evaluar_recuperador,
    fusion_rrf,
    guardar_indice_versionado,
    reabrir_indice_versionado,
    ajustar_holm,
)
from convertersmartgrid.asistente.indice import Fragmento


FRAGMENTOS = [
    Fragmento(1, 'casos/CA101.md:10', 'CA101 aceptado: flujo convergente y reapertura correcta.'),
    Fragmento(2, 'casos/CA104.md:10', 'CA104 rechazado: flujo no convergente y tensión fuera de límite.'),
    Fragmento(3, 'casos/CA101-viejo.md:3', 'CA101 versión obsoleta, no usar para aceptación.'),
]


def test_rrf_fusiona_rangos_y_no_puntuaciones_incompatibles():
    fusion = fusion_rrf([['a', 'b', 'c'], ['b', 'c', 'a']], k=60)
    assert [x['id'] for x in fusion] == ['b', 'a', 'c']
    assert fusion[0]['score'] == 1 / 62 + 1 / 61


def test_dataset_contrastivo_incluye_negativo_dificil_obsoleto_y_abstencion():
    pares = construir_dataset_contrastivo(FRAGMENTOS, [
        {'pregunta': '¿Convergió y se reabrió CA101?', 'fuente': 'casos/CA101.md:10',
         'confirmada': True},
        {'pregunta': '¿Cuál es la receta del juane?', 'sin_respuesta': True, 'confirmada': True},
        {'pregunta': 'pregunta todavía no revisada', 'fuente': 'casos/CA104.md:10'},
    ])
    assert len(pares) == 2
    positivo = next(p for p in pares if p.answerable)
    assert positivo.positive_ids == ('casos/CA101.md:10',)
    assert {'casos/CA104.md:10', 'casos/CA101-viejo.md:3'} <= set(positivo.hard_negative_ids)
    assert any(not p.answerable and not p.positive_ids for p in pares)


def test_preguntas_extractivas_declaran_que_no_son_evaluacion_independiente():
    preguntas = construir_preguntas_extractivas(FRAGMENTOS)

    assert len(preguntas) == 3
    assert preguntas[0]['fuente'] == FRAGMENTOS[0].fuente
    assert preguntas[0]['verification'] == 'extractive_deterministic'
    assert preguntas[0]['independent_evaluation'] is False


def test_metricas_por_consulta_recall_mrr_ndcg_cita_y_abstencion():
    pares = [
        ParContraste('CA101', ('casos/CA101.md:10',), ('casos/CA104.md:10',), True, 'g1'),
        ParContraste('sin respuesta', (), (), False, 'g2'),
    ]

    def buscar(pregunta, _k):
        if pregunta == 'sin respuesta':
            return []
        return [{'fuente': 'casos/CA104.md:10'}, {'fuente': 'casos/CA101.md:10'}]

    metricas = evaluar_recuperador(pares, buscar)
    assert metricas['recall@1'] == 0.0 and metricas['recall@5'] == 1.0
    assert metricas['recall@10'] == 1.0 and metricas['mrr@10'] == 0.5
    assert 0.62 < metricas['ndcg@10'] < 0.64
    assert metricas['exact_citation@1'] == 0.0
    assert metricas['abstention_accuracy'] == 1.0
    assert len(metricas['per_query']) == 2


def test_indice_versionado_verifica_hashes_y_reabre_identico(tmp_path):
    vectores = [[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]]
    manifest = guardar_indice_versionado(
        FRAGMENTOS, vectores, tmp_path / 'indice', modelo='encoder-prueba@sha256:abc',
        segmentacion={'max_chars': 1500, 'estrategia': 'rf-docstring'})
    assert {'corpus_sha256', 'model_sha256', 'segmentation_sha256'} <= set(manifest)

    reabierto = reabrir_indice_versionado(tmp_path / 'indice')
    assert reabierto.buscar('CA101 convergente', 3, [1.0, 0.0]) == (
        reabrir_indice_versionado(tmp_path / 'indice').buscar('CA101 convergente', 3, [1.0, 0.0]))
    assert json.loads((tmp_path / 'indice' / 'manifest.json').read_text(encoding='utf-8')) == manifest

    filas = json.loads((tmp_path / 'indice' / 'fragmentos.json').read_text(encoding='utf-8'))
    filas[0]['texto'] = 'alterado'
    (tmp_path / 'indice' / 'fragmentos.json').write_text(json.dumps(filas), encoding='utf-8')
    with pytest.raises(ValueError, match='corpus_sha256'):
        reabrir_indice_versionado(tmp_path / 'indice')


def test_comparacion_pareada_bootstrap_permutacion_efecto_y_holm():
    base = {'per_query': [{'group_id': f'g{i}', 'reciprocal_rank@10': 0.25} for i in range(20)]}
    candidato = {'per_query': [{'group_id': f'g{i}', 'reciprocal_rank@10': 0.75} for i in range(20)]}
    prueba = comparar_pareado(base, candidato, metrica='mrr@10', remuestreos=1000, semilla=7)
    ajustados = ajustar_holm({'mrr': prueba['p_permutation'], 'ndcg': 0.04, 'recall': 0.2})

    assert prueba['status'] == 'OK' and prueba['n'] == 20
    assert prueba['mean_difference'] == 0.5 and prueba['ci95_bootstrap'] == [0.5, 0.5]
    assert prueba['rank_biserial'] == 1.0
    assert set(ajustados) == {'mrr', 'ndcg', 'recall'}


def test_cambiar_pesos_en_misma_ruta_no_conserva_identidad(tmp_path):
    """043:RF-13: el nombre del directorio no acredita los pesos que codificaron el corpus."""
    from convertersmartgrid.asistente.embeddings import manifiesto_indice
    modelo=tmp_path/'modelo';modelo.mkdir();pesos=modelo/'weights.bin';pesos.write_bytes(b'pesos contrato A')
    a=manifiesto_indice(FRAGMENTOS,None,modelo=str(modelo),segmentacion={})
    pesos.write_bytes(b'pesos contrato B')
    b=manifiesto_indice(FRAGMENTOS,None,modelo=str(modelo),segmentacion={})
    assert a['model_sha256']!=b['model_sha256']


def test_prefijos_de_encoder_local_no_dependen_del_nombre_de_carpeta(tmp_path):
    """043:RF-13: el candidato local conserva el mismo contrato query/passage de su base E5."""
    from convertersmartgrid.asistente.embeddings import protocolo_encoder
    base=protocolo_encoder('intfloat/multilingual-e5-base')
    local=tmp_path/'modelo';local.mkdir()
    (local/'embedding_protocol.json').write_text(json.dumps(base),encoding='utf-8')
    assert protocolo_encoder(str(local))==base


def test_biserial_por_rangos_no_es_conteo_de_signos():
    """043:RF-13 / 044:RF-6: el nombre del efecto debe corresponder a su estadistico."""
    base={'per_query':[{'group_id':str(i),'reciprocal_rank@10':0.5} for i in range(3)]}
    candidato={'per_query':[{'group_id':str(i),'reciprocal_rank@10':v} for i,v in enumerate((0.6,0.7,0.1))]}
    r=comparar_pareado(base,candidato,metrica='mrr@10',remuestreos=100)
    assert r['rank_biserial']==pytest.approx(0.)


def test_tensores_en_cuda_deja_los_textos():
    """047:RF-4 — los valores sin ``.to`` de ``tokenize`` no tumban el ajuste; los tensores sí se mueven."""
    from convertersmartgrid.asistente.embeddings import _tensores_en_cuda

    class Tensor:
        def to(self, destino):
            return destino
    assert _tensores_en_cuda({'input_ids': Tensor(), 'modality': 'text'}) == {'input_ids': 'cuda', 'modality': 'text'}


def test_hit_a_10_dice_si_hay_algun_positivo_y_recall_no_cambia():
    """097:RF-23 — con 4 positivos y uno en el puesto 3, Recall@10 = 0,25 y hit@10 = 1; sin ninguno, los dos 0."""
    from convertersmartgrid.asistente import evaluacion_rag

    pares = [ParContraste('q1', ('a', 'b', 'c', 'd'), (), True, 'g1'), ParContraste('q2', ('z',), (), True, 'g2'),
             ParContraste('q3', (), (), False, 'g3')]
    rankings = {'q1': ['x', 'y', 'b', 'w'], 'q2': ['x', 'y'], 'q3': []}
    m = evaluar_recuperador(pares, lambda q, k: rankings[q])
    fila = {x['group_id']: x for x in m['per_query']}
    assert fila['g1']['recall@10'] == 0.25 and fila['g1']['hit@10'] == 1.0
    assert fila['g2']['recall@10'] == 0.0 and fila['g2']['hit@10'] == 0.0
    assert m['recall@10'] == 0.125 and m['hit@10'] == 0.5 and 'hit@10' not in fila['g3']
    assert evaluacion_rag.con_intervalos(m, {'g1': 'spec', 'g2': 'spec'})['global']['hit@10']['valor'] == 0.5


def test_hit_a_10_no_decide_ninguna_puerta():
    """097:RF-23 — la decisión de la 047 y la puerta de la abstención dan lo mismo con cualquier hit@10."""
    from convertersmartgrid.asistente import evaluacion_rag

    def medido(rr, hit):
        filas = [{'group_id': f'g{i}', 'answerable': True, 'reciprocal_rank@10': rr, 'exact_citation@1': rr,
                  'recall@10': .5, 'hit@10': hit} for i in range(6)]
        return {'mrr@10': rr, 'recall@10': .5, 'hit@10': hit, 'abstention_accuracy': .97, 'latencia_p95_ms': 10.0,
                'per_query': filas}

    base = {'bm25': medido(.5, 1.0), 'hibrido': medido(.6, 1.0), 'reranker:m': medido(.7, 1.0)}
    otra = {k: {**v, 'hit@10': 0.0, 'per_query': [{**f, 'hit@10': 0.0} for f in v['per_query']]} for k, v in base.items()}
    assert evaluacion_rag.decidir(base, set()) == evaluacion_rag.decidir(otra, set())
    assert evaluacion_rag._puerta(base['hibrido'], base['bm25']) == evaluacion_rag._puerta(otra['hibrido'], otra['bm25'])
