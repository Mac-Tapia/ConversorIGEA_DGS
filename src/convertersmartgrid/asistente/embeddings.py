"""Dataset, evaluacion y persistencia auditable del recuperador hibrido."""
from __future__ import annotations

from ..runtime_paths import staging_publicacion

import hashlib
import json
import math
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable, Mapping, Sequence


def _json_canonico(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def _sha256(valor: Any) -> str:
    return hashlib.sha256(_json_canonico(valor).encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ParContraste:
    pregunta: str
    positive_ids: tuple[str, ...]
    hard_negative_ids: tuple[str, ...]
    answerable: bool
    group_id: str
    positive_texts: tuple[str, ...] = ()
    hard_negative_texts: tuple[str, ...] = ()


def fusion_rrf(rankings: Sequence[Sequence[Any]], *, k: int = 60) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion: combina posiciones, no escalas de score incompatibles."""
    puntos: dict[Any, float] = {}
    mejor_posicion: dict[Any, int] = {}
    for ranking in rankings:
        vistos = set()
        for posicion, identificador in enumerate(ranking, 1):
            if identificador in vistos:
                continue
            vistos.add(identificador)
            puntos[identificador] = puntos.get(identificador, 0.0) + 1.0 / (k + posicion)
            mejor_posicion[identificador] = min(mejor_posicion.get(identificador, posicion), posicion)
    orden = sorted(puntos, key=lambda x: (-puntos[x], mejor_posicion[x], str(x)))
    return [{'id': identificador, 'score': puntos[identificador]} for identificador in orden]


def _terminos(texto: str) -> set[str]:
    import re
    import unicodedata
    limpio = ''.join(unicodedata.normalize('NFD', c)[0].lower() for c in texto)
    return {p for p in re.findall(r'[a-z0-9_]+', limpio) if len(p) > 2}


def construir_dataset_contrastivo(fragmentos: Sequence[Any],
                                   preguntas: Iterable[Mapping[str, Any]]) -> list[ParContraste]:
    """Construye pares revisados y negativos léxicamente cercanos del mismo corpus."""
    por_fuente = {str(f.fuente): f for f in fragmentos}
    salida = []
    for fila in preguntas:
        if fila.get('confirmada') is not True:
            continue
        pregunta = str(fila.get('pregunta') or '').strip()
        fuente = str(fila.get('fuente') or '').strip()
        sin_respuesta = fila.get('sin_respuesta') is True
        if not pregunta or (not sin_respuesta and fuente not in por_fuente):
            continue
        positivos = () if sin_respuesta else (fuente,)
        tokens = _terminos(pregunta + ' ' + (por_fuente[fuente].texto if not sin_respuesta else ''))
        candidatos = []
        for otra, fragmento in por_fuente.items():
            if otra in positivos:
                continue
            solape = len(tokens & _terminos(fragmento.texto + ' ' + otra))
            obsoleto = int('obsolet' in fragmento.texto.casefold() or 'viejo' in otra.casefold())
            candidatos.append((-(solape + obsoleto), otra, str(fragmento.texto)))
        candidatos.sort()
        negativos = tuple(x[1] for x in candidatos[:8])
        grupo = _sha256({'pregunta': pregunta, 'positivos': positivos})
        salida.append(ParContraste(
            pregunta, positivos, negativos, not sin_respuesta, grupo,
            tuple(str(por_fuente[p].texto) for p in positivos),
            tuple(x[2] for x in candidatos[:8])))
    return salida


def construir_preguntas_extractivas(fragmentos: Sequence[Any], *,
                                     max_palabras: int = 24) -> list[dict[str, Any]]:
    """Crea consultas internas reproducibles sin introducir conocimiento sintético.

    Estas consultas sirven para ajuste y *smoke evaluation*. La procedencia explícita evita
    confundirlas con preguntas humanas o con una evaluación externa independiente.
    """
    import re

    salida = []
    for fragmento in fragmentos:
        palabras = re.findall(r'[^\s]+', str(fragmento.texto).strip())[:max_palabras]
        if len(palabras) < 5:
            continue
        salida.append({
            'pregunta': ' '.join(palabras),
            'fuente': str(fragmento.fuente),
            'confirmada': True,
            'verification': 'extractive_deterministic',
            'independent_evaluation': False,
        })
    return salida


def _fuente(resultado: Any) -> str:
    if isinstance(resultado, Mapping):
        return str(resultado.get('fuente') or resultado.get('id') or '')
    return str(resultado)


def evaluar_recuperador(pares: Sequence[ParContraste],
                        buscar: Callable[[str, int], Sequence[Any]]) -> dict[str, Any]:
    """Evalua por pregunta; una pregunta es la unidad experimental indivisible."""
    por_consulta = []
    for par in pares:
        ranking = [_fuente(x) for x in buscar(par.pregunta, 10)][:10]
        if not par.answerable:
            por_consulta.append({'group_id': par.group_id, 'answerable': False,
                                 'abstained': not ranking})
            continue
        relevantes = set(par.positive_ids)
        posiciones = [i + 1 for i, fuente in enumerate(ranking) if fuente in relevantes]
        primero = min(posiciones) if posiciones else None
        recalls = {k: sum(1 for p in posiciones if p <= k) / max(len(relevantes), 1)
                   for k in (1, 5, 10)}
        rr = 1.0 / primero if primero is not None and primero <= 10 else 0.0
        dcg = sum(1.0 / math.log2(p + 1) for p in posiciones if p <= 10)
        ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevantes), 10))) or 1.0
        por_consulta.append({
            'group_id': par.group_id, 'answerable': True,
            'recall@1': recalls[1], 'recall@5': recalls[5], 'recall@10': recalls[10],
            'reciprocal_rank@10': rr, 'ndcg@10': dcg / ideal,
            'exact_citation@1': float(bool(ranking) and ranking[0] in relevantes),
            'ranking': ranking,
        })
    respondibles = [x for x in por_consulta if x['answerable']]
    no_respondibles = [x for x in por_consulta if not x['answerable']]

    def promedio(clave: str, filas: Sequence[Mapping[str, Any]]) -> float:
        return mean(float(x[clave]) for x in filas) if filas else 0.0

    return {
        'queries': len(pares), 'answerable_queries': len(respondibles),
        'recall@1': promedio('recall@1', respondibles),
        'recall@5': promedio('recall@5', respondibles),
        'recall@10': promedio('recall@10', respondibles),
        'mrr@10': promedio('reciprocal_rank@10', respondibles),
        'ndcg@10': promedio('ndcg@10', respondibles),
        'exact_citation@1': promedio('exact_citation@1', respondibles),
        'abstention_accuracy': promedio('abstained', no_respondibles),
        'per_query': por_consulta,
    }


def comparar_pareado(base: Mapping[str, Any], candidato: Mapping[str, Any], *,
                     metrica: str, remuestreos: int = 4000, semilla: int = 0) -> dict[str, Any]:
    """Bootstrap y permutacion pareados por consulta, sin pseudorreplicar rankings."""
    clave = {'mrr@10': 'reciprocal_rank@10'}.get(metrica, metrica)
    b = {x['group_id']: x for x in base.get('per_query') or () if clave in x}
    c = {x['group_id']: x for x in candidato.get('per_query') or () if clave in x}
    ids = sorted(set(b) & set(c))
    diferencias = [float(c[i][clave]) - float(b[i][clave]) for i in ids]
    if len(diferencias) < 2:
        return {'status': 'BLOQUEADO_POR_DATOS', 'n': len(diferencias), 'metric': metrica}
    rnd = random.Random(semilla)
    observado = mean(diferencias)
    boot = sorted(mean(rnd.choice(diferencias) for _ in diferencias) for _ in range(remuestreos))
    inferior = boot[int(0.025 * (len(boot) - 1))]
    superior = boot[int(0.975 * (len(boot) - 1))]
    extremos = 0
    for _ in range(remuestreos):
        permutado = mean(d * (-1 if rnd.random() < 0.5 else 1) for d in diferencias)
        extremos += abs(permutado) >= abs(observado)
    # Rangos de magnitudes absolutas, promedio en empates y omision de ceros pareados.
    no_cero=sorted((abs(d),d) for d in diferencias if d!=0.)
    favor=contra=0.;i=0
    while i<len(no_cero):
        j=i+1
        while j<len(no_cero) and no_cero[j][0]==no_cero[i][0]:j+=1
        rango=((i+1)+j)/2
        favor+=rango*sum(d>0 for _,d in no_cero[i:j])
        contra+=rango*sum(d<0 for _,d in no_cero[i:j])
        i=j
    rango_biserial=(favor-contra)/(favor+contra) if favor+contra else 0.
    return {'status': 'OK', 'n': len(diferencias), 'metric': metrica, 'mean_difference': observado,
            'ci95_bootstrap': [inferior, superior],
            'p_permutation': (extremos + 1) / (remuestreos + 1),
            'rank_biserial': rango_biserial}


def ajustar_holm(p_values: Mapping[str, float]) -> dict[str, float]:
    """Ajuste de Holm para comparaciones múltiples predefinidas."""
    orden = sorted(p_values, key=lambda k: p_values[k])
    ajustados: dict[str, float] = {}
    anterior = 0.0
    m = len(orden)
    for i, clave in enumerate(orden):
        valor = min(1.0, (m - i) * float(p_values[clave]))
        anterior = max(anterior, valor)
        ajustados[clave] = anterior
    return ajustados


def manifiesto_indice(fragmentos: Sequence[Any], vectores: Sequence[Sequence[float]] | None,
                      *, modelo: str, segmentacion: Mapping[str, Any]) -> dict[str, Any]:
    corpus = [{'id': f.id, 'fuente': f.fuente, 'texto': f.texto} for f in fragmentos]
    dimension = len(vectores[0]) if vectores else 0
    return {'schema': 'convertersmartgrid-embedding-index-v1', 'fragments': len(fragmentos),
            'dimension': dimension, 'corpus_sha256': _sha256(corpus),
            'vectors_sha256': _sha256(vectores),
            'model_sha256': _sha256(identidad_encoder(modelo)),
            'segmentation_sha256': _sha256(dict(segmentacion)),
            'modelo': modelo, 'segmentacion': dict(segmentacion)}


def guardar_indice_versionado(fragmentos: Sequence[Any], vectores: Sequence[Sequence[float]] | None,
                              destino: Path | str, *, modelo: str,
                              segmentacion: Mapping[str, Any]) -> dict[str, Any]:
    """Guarda índice y manifiesto por reemplazo atómico."""
    raiz = Path(destino)
    raiz.mkdir(parents=True, exist_ok=True)
    frags = [{'id': f.id, 'fuente': f.fuente, 'texto': f.texto} for f in fragmentos]
    archivos = {'fragmentos.json': frags, 'vectores.json': list(vectores) if vectores is not None else None}
    manifest = manifiesto_indice(fragmentos, vectores, modelo=modelo, segmentacion=segmentacion)
    for nombre, contenido in [*archivos.items(), ('manifest.json', manifest)]:
        with staging_publicacion(raiz / nombre) as temporal:
            temporal.write_text(json.dumps(contenido, ensure_ascii=False, sort_keys=True), encoding='utf-8')
            os.replace(temporal, raiz / nombre)
    return manifest


def reabrir_indice_versionado(origen: Path | str):
    """Reabre únicamente si corpus, modelo y segmentación conservan sus hashes."""
    from .indice import Fragmento, Indice

    raiz = Path(origen)
    manifest = json.loads((raiz / 'manifest.json').read_text(encoding='utf-8'))
    filas = json.loads((raiz / 'fragmentos.json').read_text(encoding='utf-8'))
    vectores = json.loads((raiz / 'vectores.json').read_text(encoding='utf-8'))
    frags = [Fragmento(**x) for x in filas]
    actual = manifiesto_indice(frags, vectores, modelo=manifest['modelo'],
                               segmentacion=manifest['segmentacion'])
    for clave in ('corpus_sha256', 'vectors_sha256', 'model_sha256', 'segmentation_sha256', 'dimension'):
        if actual[clave] != manifest.get(clave):
            raise ValueError(f'indice alterado: {clave}')
    return Indice(frags, vectores)


def protocolo_encoder(modelo_id: str) -> dict:
    """El protocolo proviene de la base fijada o de metadata persistida, nunca del nombre de carpeta."""
    catalogo=json.loads((Path(__file__).resolve().parents[3]/'docs/MODELOS_IA_LOCK.json').read_text(encoding='utf-8'))
    ficha=next(m for m in catalogo['modelos'] if m['id']=='intfloat/multilingual-e5-base')
    esperado={'schema_version':1,'base_id':ficha['id'],'revision':ficha['revision'],
              'query_prefix':'query: ','passage_prefix':'passage: '}
    if Path(modelo_id).is_dir():
        archivo=Path(modelo_id)/'embedding_protocol.json'
        if not archivo.is_file():raise ValueError('encoder local sin protocolo persistido')
        actual=json.loads(archivo.read_text(encoding='utf-8'))
        if actual!=esperado:raise ValueError('protocolo del encoder local incompatible con la base fijada')
    elif modelo_id!=ficha['id']:raise ValueError('encoder no fijado en el catalogo')
    return esperado


def identidad_encoder(modelo_id: str) -> dict:
    """Identifica contenido real cuando es una carpeta; para HF contrasta el inventario fijado."""
    from ..trabajadores_ml import sha_archivo
    modelo=Path(modelo_id)
    if modelo.is_dir():
        archivos=[{'archivo':f.relative_to(modelo).as_posix(),'sha256':sha_archivo(f)}
                  for f in sorted(modelo.rglob('*')) if f.is_file()]
        if not archivos:raise ValueError('carpeta de encoder vacia')
        return {'archivos':archivos}
    catalogo=json.loads((Path(__file__).resolve().parents[3]/'docs/MODELOS_IA_LOCK.json').read_text(encoding='utf-8'))
    ficha=next((m for m in catalogo['modelos'] if m['id']==modelo_id and m['backend']=='huggingface'),None)
    if ficha:
        from huggingface_hub import hf_hub_download
        archivos=[]
        for f in ficha['files']:
            ruta=Path(hf_hub_download(ficha['id'],f['path'],revision=ficha['revision'],local_files_only=True))
            sha=sha_archivo(ruta)
            if f.get('sha256') and sha!=f['sha256']:raise ValueError('pesos del encoder difieren del catalogo')
            if f.get('git_blob_sha1'):
                contenido=ruta.read_bytes()
                if hashlib.sha1(f'blob {len(contenido)}\0'.encode()+contenido).hexdigest()!=f['git_blob_sha1']:
                    raise ValueError('configuracion o tokenizador difieren del catalogo')
            archivos.append({'archivo':f['path'],'sha256':sha})
        return {'id':ficha['id'],'revision':ficha['revision'],'archivos':archivos}
    # Identificadores externos solo sirven como metadata declarada; cargar_encoder los rechaza.
    return {'identificador_declarado_sin_verificacion_de_pesos':modelo_id}


def cargar_encoder(modelo_id: str):
    """Carga exclusivamente un candidato local o la revision E5 fijada, en CUDA."""
    from ..training_coordinator import exigir_memoria_ml
    protocolo_encoder(modelo_id)
    exigir_memoria_ml(3.,minimo_commit_gib=6.)
    from sentence_transformers import SentenceTransformer
    import torch
    if not torch.cuda.is_available():raise RuntimeError('CUDA requerida para el encoder')
    if Path(modelo_id).is_dir():
        return SentenceTransformer(modelo_id,device='cuda',local_files_only=True,
            model_kwargs={'device_map':{'':0}})
    catalogo=json.loads((Path(__file__).resolve().parents[3]/'docs/MODELOS_IA_LOCK.json').read_text(encoding='utf-8'))
    ficha=next((m for m in catalogo['modelos'] if m['id']==modelo_id and m['backend']=='huggingface'),None)
    if not ficha or modelo_id!='intfloat/multilingual-e5-base':raise ValueError('encoder no fijado en el catalogo')
    return SentenceTransformer(modelo_id,revision=ficha['revision'],device='cuda',local_files_only=True,
        model_kwargs={'device_map':{'':0}})


def entrenar_recuperador(pares: Sequence[ParContraste], destino: Path | str, *,
                         modelo_base: str = 'intfloat/multilingual-e5-base',
                         epocas: int = 1, minimo_pares: int = 20) -> dict[str, Any]:
    """Ajuste opcional con MNRL; nunca promueve sin una evaluación sellada posterior."""
    from ..trabajadores_ml import escribir_informe
    raiz = Path(destino)
    if epocas<1:raise ValueError('epocas positivas obligatorias')
    utiles = [p for p in pares if p.answerable and p.positive_texts]
    if len(utiles) < minimo_pares:
        raise ValueError(f'se requieren {minimo_pares} pares train; hay {len(utiles)}')
    else:
        modelo=cargar_encoder(modelo_base)
        import torch
        import random
        torch.manual_seed(11);rnd=random.Random(11)
        opt=torch.optim.AdamW(modelo.parameters(),lr=2e-5)
        protocolo=protocolo_encoder(modelo_base)
        prefijos=(protocolo['query_prefix'],protocolo['passage_prefix'])
        historia=[];modelo.train()
        for epoca in range(epocas):
            orden=list(utiles);rnd.shuffle(orden);perdidas=[]
            for i in range(0,len(orden),8):
                lote=orden[i:i+8]
                if len(lote)<2 and len(orden)>=2:lote=orden[-2:]
                q={k:v.to('cuda') for k,v in modelo.tokenize([prefijos[0]+p.pregunta for p in lote]).items()}
                positivos={k:v.to('cuda') for k,v in modelo.tokenize([prefijos[1]+p.positive_texts[0] for p in lote]).items()}
                a=torch.nn.functional.normalize(modelo(q)['sentence_embedding'],dim=-1)
                b=torch.nn.functional.normalize(modelo(positivos)['sentence_embedding'],dim=-1)
                objetivo=torch.arange(len(lote),device='cuda')
                loss=torch.nn.functional.cross_entropy(a@b.T/.05,objetivo)
                if not torch.isfinite(loss):raise RuntimeError('perdida contrastiva no finita')
                opt.zero_grad(set_to_none=True);loss.backward()
                norma=torch.nn.utils.clip_grad_norm_(modelo.parameters(),1.)
                if not torch.isfinite(norma):raise RuntimeError('gradientes contrastivos no finitos')
                opt.step();perdidas.append(float(loss.detach()))
                del q,positivos,a,b,loss
            historia.append({'epoca':epoca+1,'loss_media':sum(perdidas)/len(perdidas),'pares':len(utiles)})
        modelo.eval();modelo.save_pretrained(str(raiz/'modelo'))
        escribir_informe(raiz/'modelo/embedding_protocol.json',protocolo)
        decision={'status':'RECHAZADO','candidate_status':'CANDIDATO','pairs':len(utiles),'modelo_base':modelo_base,
            'training_completed':True,'entrenado':True,'promovido':False,'historia':historia,
            'gates':{'approved':False},'reason':'candidato conservado; requiere evaluacion reservada y recarga'}
    escribir_informe(raiz/'decision.json',decision)
    return decision
