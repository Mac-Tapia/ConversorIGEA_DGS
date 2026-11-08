"""043:RF-13: candidatos del clasificador pequeno usando exclusivamente el dataset indicado."""
from __future__ import annotations
from dataclasses import asdict
import math
from pathlib import Path
import uuid


def puertas_dataset(solo: str, prueba: dict, reales: dict | None,
                    en_uso: dict | None, reapertura: dict) -> dict:
    """Puertas de las arquitecturas existentes sobre prueba reservada y ejemplos reales."""
    from .transformer import Puertas

    puertas = Puertas()
    limites = ({'acierto_tarea': puertas.acierto_tarea, 'f1_datos': puertas.f1_datos}
               if solo == 'ordenes' else {'acierto_subtipo': .9})
    limites_reales = ({'acierto_tarea': puertas.acierto_real, 'f1_datos': puertas.f1_real}
                      if solo == 'ordenes' else limites)
    fallos = []
    def valida(m, clave):
        v = m.get(clave) if isinstance(m, dict) else None
        return type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1
    for nombre, medidas, umbrales in [('prueba', prueba, limites), ('reales', reales, limites_reales)]:
        if not medidas or type(medidas.get('ejemplos')) is not int or medidas['ejemplos'] < 1:
            fallos.append(f'{nombre}: faltan ejemplos medidos')
        for clave, minimo in umbrales.items():
            if not valida(medidas, clave) or medidas[clave] < minimo:
                fallos.append(f'{nombre}: {clave} ausente, inválido o bajo {minimo}')
    if en_uso is not None:
        for clave in limites:
            if not valida(en_uso, clave) or not valida(prueba, clave) or prueba[clave] < en_uso[clave] - 1e-9:
                fallos.append(f'retroceso o comparación inválida frente al modelo en uso: {clave}')
    if reapertura.get('ok') is not True:
        fallos.append('falló la reapertura en un proceso nuevo')
    return {'approved': not fallos, 'fallos': fallos, 'umbrales': limites, 'umbrales_reales': limites_reales}


def entrenar_dataset(dataset: Path,destino: Path,*,solo: str,semillas: tuple[int,...],epocas: int,
                      registro=None,reabrir=None) -> dict:
    from ..trabajadores_ml import leer_dataset_v2,escribir_informe,turno_gpu,sha_archivo
    partes,manifest=leer_dataset_v2(dataset)
    if solo not in ('ordenes','informes') or epocas<1:raise ValueError('familia y epocas invalidas')
    admitidas={'gold_human','gold_native','silver_deterministic','silver_teacher_verified'}
    vistas={};reales=[]
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
                ejemplo=Ejemplo(r['texto'],r['tarea'],spans)
                ejemplos.append(ejemplo)
                if p=='test' and r.get('quality') in {'gold_human','gold_native'}:reales.append(ejemplo)
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
                    ejemplo=(r['texto'],tipo,subtipo)
                    ejemplos.append(ejemplo)
                    if p=='test' and r.get('quality') in {'gold_human','gold_native'}:reales.append(ejemplo)
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
        prueba_real=modulo.evaluar(modelo,reales) if reales else None
        actual=modulo.cargar()
        en_uso=modulo.evaluar(actual,vistas['test']) if actual is not None else None
        carpeta=destino/('candidato_'+uuid.uuid4().hex);carpeta.mkdir(parents=True)
        modulo.modulo_torch().save({k:v.detach().cpu() for k,v in modelo.red.state_dict().items()},carpeta/'pesos.pt')
        meta={'cfg':asdict(modelo.cfg),'simbolos':modelo.simbolos,'semilla':semilla,'familia':solo,
              'dataset_manifest':manifest,'seleccion':candidatos,'prueba':prueba,'prueba_real':prueba_real,
              'en_uso':en_uso,
              'pesos_sha256':sha_archivo(carpeta/'pesos.pt')}
        if solo=='ordenes':meta.update({'tareas':modelo.tareas,'etiquetas':list(modulo.ETIQUETAS),'temperatura':modelo.temperatura})
        else:meta.update({'subtipos':modelo.subtipos,'tipos':list(modulo.TIPOS_INFORME)})
        escribir_informe(carpeta/'modelo.json',meta)
        textos=[e.texto if solo=='ordenes' else e[0] for e in vistas['test'][:32]]
        predecir=modelo.predecir if solo=='ordenes' else modelo.clasificar
        escribir_informe(carpeta/'readback.json',{'textos':textos,'predicciones':[predecir(t) for t in textos]})
        familia='transformer' if solo=='ordenes' else 'clasificador'
        if reabrir is None:
            import sys
            from ..model_registry import reabrir_en_subproceso
            from ..runtime_paths import raiz_programa
            from ..trabajadores_ml import entorno_hijo_gpu
            herramienta=raiz_programa()/'tools/asistente_destilar.py'
            reabrir=lambda c:reabrir_en_subproceso([sys.executable,str(herramienta),'verificar',
                '--familia',familia,'--modelo',str(c)],env=entorno_hijo_gpu())
        smoke=reabrir(carpeta)
        gates=puertas_dataset(solo,prueba,prueba_real,en_uso,smoke)
        from ..model_registry import RegistroModelo
        from . import almacen
        registro=registro or RegistroModelo(almacen.raiz()/'model_registry')
        aprobado=gates['approved']
        c=registro.registrar_candidato(familia,
            model_manifest={'algorithm':'transformer_'+solo,'cfg':asdict(modelo.cfg),'training_completed':True},
            dataset_manifest=manifest,metrics={'seleccion':candidatos,'prueba':prueba,'reales':prueba_real,'en_uso':en_uso},
            decision={'status':'PROMOVIDO' if aprobado else 'RECHAZADO','gates':gates},smoke_reload=smoke,
            artifacts=[carpeta/n for n in ('modelo.json','pesos.pt','readback.json')])
    return {'status':c['status'],'training_completed':True,'entrenado':True,'promovido':False,
        'candidate_id':c['candidate_id'],'modelo_registro':familia,
        'candidato_aprobado':aprobado,'publicacion_pendiente':aprobado,
        'candidate_dir':str(carpeta.resolve()),'seleccion':candidatos,'prueba':prueba,
        'gates':gates,'reason':'candidato registrado sin activación individual' if aprobado else '; '.join(gates['fallos'])}
