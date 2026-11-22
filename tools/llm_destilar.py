"""Destila al LLM local con fuentes reales y conserva el protocolo (spec 047 T7).

    python tools/llm_destilar.py preparar --help
    python tools/llm_destilar.py sellar --custodia CORPUS_REUBICADO/dataset_manifest.json --destino NUEVO
    python tools/llm_destilar.py preparar-contrato --base CORPUS_V6 --destino FUENTE_V7
    python tools/llm_destilar.py sellar --dataset FUENTE_V7 --destino CORPUS_V7

No envia datos a servicios externos ni ejecuta maniobras o estudios electricos.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import time


def detector_de_nombres(carpeta: Path | None = None):
    """047:RF-70: busca nombres reales con la lista de la entrega (huellas en git, perfiles excluidos y lista local).

    Mira el texto tal cual y partido por mayúsculas («ConversorEmpresa» → «Conversor Empresa»), como el barrido del
    repositorio (086:RF-33). Devuelve la función y de dónde salieron los términos, sin escribir ninguno.

    086:RF-36: ``comprobar_entrega.py`` es de desarrollo y no va en el paquete; esta herramienta sí. ``preparar-contrato``
    (lo corre el maestro en el repositorio) la carga por su ruta y, si no está, lo dice en vez de caer con
    ``ModuleNotFoundError`` en casa del cliente.
    """
    import importlib.util
    ruta = Path(carpeta or Path(__file__).resolve().parent) / 'comprobar_entrega.py'
    if not ruta.is_file():
        raise ValueError('preparar-contrato se ejecuta en el repositorio: el programa instalado no lleva '
                         'tools/comprobar_entrega.py, la lista de nombres de la entrega')
    especificacion = importlib.util.spec_from_file_location('comprobar_entrega', ruta)
    CE = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(CE)
    terminos = CE.cargar_terminos()
    memoria: dict = {}

    def nombres(texto: str) -> list[str]:
        partido = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', texto)
        return [h.categoria for t in (texto, partido) for h in CE.buscar_en_texto('corpus_v7.txt', t, terminos, memoria)]
    return nombres, list(terminos.origenes)


def vedados_sellados() -> list[str]:
    """Los textos de las pruebas selladas del intérprete: no entran en el corpus v7 (047:RF-71), sin redactar con ellos."""
    from convertersmartgrid.aplicacion.asistente import (prueba_sellada, prueba_sellada_026, prueba_sellada_079,
                                                         prueba_sellada_107_112)
    filas = [*prueba_sellada.filas(), *prueba_sellada_079.filas(), *prueba_sellada_107_112.filas(),
             *prueba_sellada_026.filas(), *prueba_sellada_026.filas_control()]
    return [r['texto'] for r in filas]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='accion',required=True)
    a=sub.add_parser('preparar')
    for n in ('red','cargas','equipos','estructura-pdf','mediciones','nuevos-clientes'):
        a.add_argument('--'+n,type=Path,required=True)
    a.add_argument('--workspace',type=Path,action='append',required=True)
    a.add_argument('--destino',type=Path,required=True)
    a.add_argument('--max-train-por-tarea',type=int,default=64)
    a=sub.add_parser('exportar')
    a.add_argument('--adaptador',type=Path)
    a.add_argument('--destino',type=Path,required=True)
    a=sub.add_parser('publicar')
    a.add_argument('--checkpoint',type=Path,required=True)
    a.add_argument('--destino',type=Path,required=True)
    a.add_argument('--modelo',required=True)
    a.add_argument('--redaccion',action='store_true',
                   help='publica el modelo de redacción del PIDE con su decodificación: penaliza repetir frases')
    a=sub.add_parser('sellar')
    a.add_argument('--dataset',type=Path)
    a.add_argument('--custodia',type=Path)
    a.add_argument('--destino',type=Path,required=True)
    a=sub.add_parser('preparar-contrato')
    a.add_argument('--base',type=Path,required=True,help='corpus sellado v6 (su dataset_manifest.json y sus contextos)')
    a.add_argument('--destino',type=Path,required=True)
    a.add_argument('--sin-almacen',action='store_true',help='no reservar las órdenes humanas del almacén del asistente')
    a=sub.add_parser('auditar')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--destino',type=Path,required=True)
    a=sub.add_parser('entrenar-epoca')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--destino',type=Path,required=True)
    a.add_argument('--desde',type=Path)
    a.add_argument('--epoca',type=int,default=1)
    a.add_argument('--semilla',type=int,default=11)
    a.add_argument('--rango',type=int,default=8)
    a.add_argument('--lr',type=float,default=2e-4)
    a.add_argument('--acumulacion',type=int,default=8)
    a.add_argument('--max-tokens',type=int,default=None,help='sin él, el del perfil que selló el corpus')
    a=sub.add_parser('evaluar')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--destino',type=Path,required=True)
    a.add_argument('--modelo',required=True)
    a.add_argument('--parte',choices=('seleccion','calibracion','prueba'),default='seleccion')
    a.add_argument('--seleccion',type=Path)
    a=sub.add_parser('elegir')
    a.add_argument('--informe',type=Path,action='append',required=True)
    a.add_argument('--dataset',type=Path)
    a.add_argument('--destino',type=Path,required=True)
    args=p.parse_args(argv)
    creado=False
    try:
        if args.destino.exists():
            raise ValueError('destino existente conservado; use una ruta nueva')
        if args.accion=='preparar-contrato':
            # 047:RF-69 a RF-74: el maestro es esta sesión (plantillas por tarea); se mide lo que cuesta generarlo.
            from convertersmartgrid.aplicacion.asistente.corpus_contrato_llm import preparar_v7
            inicio,cpu=time.perf_counter(),time.process_time()
            nombres,origenes=detector_de_nombres()
            humanas=[]
            if not args.sin_almacen:
                from convertersmartgrid.aplicacion.asistente import almacen
                humanas=almacen.leer('ejemplos') or []
            meta=preparar_v7(args.base,args.destino,nombres=nombres,humanas_extra=humanas,vedados=vedados_sellados())
            medicion={'segundos':round(time.perf_counter()-inicio,3),'cpu_s':round(time.process_time()-cpu,3),
                      'gpu_s':0,'llamadas_a_modelos':0,'coste_externo':0,'terminos_de':origenes,
                      'maestro':'sesion Claude: redaccion de plantillas; generacion determinista local'}
            from convertersmartgrid.dominio.util import publicar_duradero
            meta['medicion_construccion']=medicion
            publicar_duradero(args.destino/'dataset_manifest.json',json.dumps(meta,ensure_ascii=False,indent=2))
            print(json.dumps({'ok':True,'dataset_hash':meta['dataset_hash'],'por_particion':meta['por_particion'],
                              'tareas':len(meta['contrato_tareas']),'por_origen':meta['por_origen'],
                              'medicion':{k:medicion[k] for k in ('segundos','cpu_s','gpu_s')}},ensure_ascii=True))
            return 0
        if args.accion=='auditar':
            from convertersmartgrid.aplicacion.asistente.llm_destilacion import auditar_fuentes_corpus
            from convertersmartgrid.aplicacion.asistente.corpus_contrato_llm import auditar_v7,es_v7
            resultado=auditar_v7(args.dataset) if es_v7(args.dataset) else auditar_fuentes_corpus(args.dataset)
            args.destino.mkdir(parents=True);creado=True
            (args.destino/'auditoria.json').write_text(json.dumps(resultado,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps(resultado,ensure_ascii=True));return 0
        if args.accion=='publicar':
            from convertersmartgrid.aplicacion.asistente.llm_runtime import publicar
            parametros=None
            if args.redaccion:
                from convertersmartgrid.aplicacion.asistente.corpus_redaccion import DECODIFICACION
                parametros=dict(DECODIFICACION)  # 072:RF-59
            resultado=publicar(args.checkpoint,args.destino,args.modelo,parametros=parametros)
            print(json.dumps({k:resultado[k] for k in ('publicado','activado','modelo','modelo_digest','sha256_gguf')}))
            return 0
        if args.accion=='elegir':
            from convertersmartgrid.aplicacion.asistente.llm_destilacion import elegir_version_llm
            if args.dataset is None:
                raise ValueError('elegir pide --dataset: el corpus sellado con el que se midio la seleccion')
            resultado=elegir_version_llm([json.loads(p.read_text(encoding='utf-8')) for p in args.informe],
                manifiesto=json.loads((args.dataset/'dataset_manifest.json').read_text(encoding='utf-8')))
            args.destino.mkdir(parents=True);creado=True
            (args.destino/'seleccion.json').write_text(json.dumps(resultado,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps({'ok':True,'modelo':resultado['modelo'],'criterio':'seleccion',
                              'tareas_selladas':len(resultado['tareas_selladas']),
                              'no_cubiertas':resultado['no_cubiertas_por_este_sellado']['cuantas']}));return 0
        if args.accion=='evaluar':
            from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu  # 071:RF-8
            from convertersmartgrid.aplicacion.asistente.llm_destilacion import evaluar_version_llm
            args.destino.mkdir(parents=True);creado=True
            with turno_gpu('evaluacion-llm-generativo'):
                resultado=evaluar_version_llm(args.dataset,args.modelo,parte=args.parte,seleccion=args.seleccion,
                    log=print)
            (args.destino/'resultado.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            print(json.dumps({k:v for k,v in resultado.items() if k!='metricas'},ensure_ascii=True));return 0
        if args.accion=='entrenar-epoca':
            from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu  # 071:RF-8
            from convertersmartgrid.aplicacion.asistente.llm_destilacion import entrenar_epoca
            creado=True
            with turno_gpu('destilacion-llm-generativo'):
                resultado=entrenar_epoca(args.dataset,args.destino,epoca=args.epoca,desde=args.desde,
                    semilla=args.semilla,rango=args.rango,lr=args.lr,acumulacion=args.acumulacion,
                    max_tokens=args.max_tokens)
            print(json.dumps(resultado,ensure_ascii=True));return 0
        if args.accion=='sellar':
            from convertersmartgrid.aplicacion.asistente.llm_destilacion import sellar_particiones
            if (args.custodia is None)==(args.dataset is None):
                raise ValueError('sellar pide --dataset o --custodia, uno de los dos')
            creado=True
            if args.custodia is not None:
                from convertersmartgrid.aplicacion.asistente.llm_destilacion import resellar_con_custodia
                resultado=resellar_con_custodia(args.custodia,args.destino)
                print(json.dumps({'ok':True,'dataset_hash':resultado['dataset_hash'],
                                  'prompt_hash':resultado.get('prompt_hash'),'por_particion':resultado.get('por_particion'),
                                  'dataset_hash_anterior':(resultado.get('resellado') or {}).get('dataset_hash_anterior')},
                                 ensure_ascii=True));return 0
            from convertersmartgrid.aplicacion.asistente.corpus_contrato_llm import es_v7,sellar_v7
            # 047:RF-69: el v7 se sella con su validador y el prompt del contrato vigente.
            resultado=sellar_v7(args.dataset,args.destino) if es_v7(args.dataset) else sellar_particiones(args.dataset,args.destino)
            print(json.dumps({'ok':True,'dataset_hash':resultado['dataset_hash'],
                              'por_particion':resultado['por_particion'],'prompt_hash':resultado.get('prompt_hash'),
                              'perfil_prompt':resultado.get('perfil_prompt','llm_destilado_v1')},ensure_ascii=True));return 0
        if args.accion=='exportar':
            from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu  # 071:RF-8
            from convertersmartgrid.aplicacion.asistente.llm_destilacion import exportar_fusionado
            creado=True
            with turno_gpu('exportar-alumno-llm'):
                resultado=exportar_fusionado(args.destino,args.adaptador)
            print(json.dumps(resultado,ensure_ascii=True));return 0
        args.destino.mkdir(parents=True)
        creado=True
        from convertersmartgrid.aplicacion.asistente.llm_destilacion import extraer_referencia, construir_corpus_real, custodiar
        fuentes=args.destino/'fuentes';fuentes.mkdir()
        copias=[];originales=[]
        for i,entrada in enumerate(args.workspace):
            original=custodiar(entrada,localizador='workspace registrado')
            copia=fuentes/f'workspace_{i:03d}.json'
            shutil.copyfile(entrada,copia)
            if custodiar(copia,localizador='workspace registrado')['sha256']!=original['sha256']:
                raise ValueError('el workspace cambio durante la copia de custodia')
            copias.append(copia);originales.append(original)
        # 002:RF-1: el caso de uso recibe el dataset ya leído; el lector de los TXT es un adaptador.
        from convertersmartgrid.adaptadores.dataset import CymdistDataset
        dataset=CymdistDataset.from_files(args.red,args.cargas,args.equipos)
        contextos,manifest=extraer_referencia(dataset=dataset,red=args.red,cargas=args.cargas,equipos=args.equipos,
            estructura_pdf=args.estructura_pdf,mediciones=args.mediciones,nuevos_clientes=args.nuevos_clientes,
            workspaces=copias)
        manifest['workspaces_originales']=originales
        from convertersmartgrid.aplicacion.asistente import almacen
        from convertersmartgrid.aplicacion.asistente.llm_destilacion import reservar_humanas
        humanas=reservar_humanas(almacen.leer('ejemplos'))
        from convertersmartgrid.aplicacion.asistente.llm_destilacion import custodiar_politica
        politica=custodiar_politica(Path(__file__).resolve().parents[1]/'docs/constitution.md',args.destino)
        filas,meta=construir_corpus_real(contextos,manifest,max_train_por_tarea=args.max_train_por_tarea,
            humanas=humanas,politica=Path(politica['copia']['ruta']))
        meta['politica_custodiada']=politica
        for nombre,datos in (('corpus.json',filas),('dataset_manifest.json',meta),('contextos.json',contextos),
                             ('humanas_reservadas.json',humanas)):
            (args.destino/nombre).write_text(json.dumps(datos,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({'ok':True,'dataset_hash':meta['dataset_hash'],'por_particion':meta['por_particion'],
                          'conteos_fuente':manifest['conteos_reales'],'observaciones_humanas':0},ensure_ascii=True))
        return 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        fallo={'ok':False,'error':str(exc),'accion':args.accion,'training_completed':False}
        if creado and args.destino.is_dir() and not (args.destino/'error.json').exists():
            (args.destino/'error.json').write_text(json.dumps(fallo,ensure_ascii=True,indent=2),encoding='utf-8')
        print(json.dumps(fallo,ensure_ascii=True));return 2


if __name__=='__main__':
    raise SystemExit(main())
