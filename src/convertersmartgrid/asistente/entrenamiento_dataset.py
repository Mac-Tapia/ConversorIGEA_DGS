"""043:RF-13: candidatos del clasificador pequeno usando exclusivamente el dataset indicado."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import uuid


def entrenar_dataset(dataset: Path,destino: Path,*,solo: str,semillas: tuple[int,...],epocas: int) -> dict:
    from ..trabajadores_ml import leer_dataset_v2,escribir_informe,turno_gpu,sha_archivo
    partes,manifest=leer_dataset_v2(dataset)
    if solo not in ('ordenes','informes') or epocas<1:raise ValueError('familia y epocas invalidas')
    admitidas={'gold_human','gold_native','silver_deterministic','silver_teacher_verified'}
    vistas={}
    if solo=='ordenes':
        from .sinteticos import Ejemplo
        from .tareas import TAREAS,TIPOS_DATO
        from . import transformer as modulo
        for p,filas in partes.items():
            ejemplos=[]
            for r in filas:
                if r.get('quality') not in admitidas or r.get('tarea') not in TAREAS:continue
                spans=[]
                for dato in r.get('datos') or []:
                    if len(dato)!=2:raise ValueError('dataset v2 requiere pares tipo/valor')
                    tipo,valor=dato
                    if tipo not in TIPOS_DATO or not isinstance(valor,str) or not valor:raise ValueError('entidad v2 invalida')
                    a=r['texto'].find(valor)
                    if a<0:raise ValueError('entidad v2 no literal; requiere revision')
                    spans.append((a,a+len(valor),tipo))
                ejemplos.append(Ejemplo(r['texto'],r['tarea'],spans))
            vistas[p]=ejemplos
    else:
        from . import clasificador as modulo
        for p,filas in partes.items():
            ejemplos=[]
            for r in filas:
                if r.get('quality') not in admitidas:continue
                etiquetas=r.get('resultado') or {}
                tipo=etiquetas.get('tipo_informe');subtipo=etiquetas.get('subtipo')
                if tipo in modulo.TIPOS_INFORME and isinstance(subtipo,str) and subtipo.strip():
                    ejemplos.append((r['texto'],tipo,subtipo))
            vistas[p]=ejemplos
    if any(not v for v in vistas.values()):raise ValueError('faltan ejemplos etiquetados de la familia en train/validation/test')
    from ..training_coordinator import exigir_memoria_ml
    exigir_memoria_ml(3.,minimo_commit_gib=6.)
    candidatos=[];mejor=None
    with turno_gpu('asistente-dataset-v2'):
        for semilla in semillas:
            cfg=modulo.Configuracion(epocas=epocas,semilla=semilla)
            if solo=='ordenes':modelo=modulo.entrenar(vistas['train'],cfg)
            else:
                subtipos=sorted({s for _,_,s in vistas['train']})
                modelo=modulo.entrenar(vistas['train'],subtipos,cfg)
            metricas=modulo.evaluar(modelo,vistas['validation'])
            score=metricas['acierto_tarea' if solo=='ordenes' else 'acierto_subtipo']
            candidatos.append({'semilla':semilla,'seleccion':metricas})
            if mejor is None or score>mejor[0]:mejor=(score,semilla,modelo)
        _,semilla,modelo=mejor
        prueba=modulo.evaluar(modelo,vistas['test'])
        carpeta=destino/('candidato_'+uuid.uuid4().hex);carpeta.mkdir(parents=True)
        import torch
        torch.save({k:v.detach().cpu() for k,v in modelo.red.state_dict().items()},carpeta/'pesos.pt')
        meta={'cfg':asdict(modelo.cfg),'simbolos':modelo.simbolos,'semilla':semilla,'familia':solo,
              'dataset_manifest':manifest,'seleccion':candidatos,'prueba':prueba,
              'pesos_sha256':sha_archivo(carpeta/'pesos.pt')}
        if solo=='ordenes':meta.update({'tareas':modelo.tareas,'etiquetas':list(modulo.ETIQUETAS),'temperatura':modelo.temperatura})
        else:meta.update({'subtipos':modelo.subtipos,'tipos':list(modulo.TIPOS_INFORME)})
        escribir_informe(carpeta/'modelo.json',meta)
    return {'status':'RECHAZADO','training_completed':True,'entrenado':True,'promovido':False,
        'candidate_dir':str(carpeta.resolve()),'seleccion':candidatos,'prueba':prueba,
        'gates':{'approved':False},'reason':'candidato de dataset conservado; faltan recarga y puertas comunes'}
