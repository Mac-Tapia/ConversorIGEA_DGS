"""Destila al LLM local con fuentes reales y conserva el protocolo (spec 047 T7).

    python tools/llm_destilar.py preparar --help

No envia datos a servicios externos ni ejecuta maniobras o estudios electricos.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil


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
    a=sub.add_parser('sellar')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--destino',type=Path,required=True)
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
    a.add_argument('--max-tokens',type=int,default=2048)
    a=sub.add_parser('evaluar')
    a.add_argument('--dataset',type=Path,required=True)
    a.add_argument('--destino',type=Path,required=True)
    a.add_argument('--modelo',required=True)
    a.add_argument('--parte',choices=('seleccion','calibracion','prueba'),default='seleccion')
    a.add_argument('--seleccion',type=Path)
    a=sub.add_parser('elegir')
    a.add_argument('--informe',type=Path,action='append',required=True)
    a.add_argument('--destino',type=Path,required=True)
    args=p.parse_args(argv)
    creado=False
    try:
        if args.destino.exists():
            raise ValueError('destino existente conservado; use una ruta nueva')
        if args.accion=='auditar':
            from igea_dgs.asistente.llm_destilacion import auditar_fuentes_corpus
            resultado=auditar_fuentes_corpus(args.dataset)
            args.destino.mkdir(parents=True);creado=True
            (args.destino/'auditoria.json').write_text(json.dumps(resultado,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps(resultado,ensure_ascii=True));return 0
        if args.accion=='publicar':
            from igea_dgs.asistente.llm_runtime import publicar
            resultado=publicar(args.checkpoint,args.destino,args.modelo)
            print(json.dumps({k:resultado[k] for k in ('publicado','activado','modelo','modelo_digest','sha256_gguf')}))
            return 0
        if args.accion=='elegir':
            from igea_dgs.asistente.llm_destilacion import elegir_version_llm
            resultado=elegir_version_llm([json.loads(p.read_text(encoding='utf-8')) for p in args.informe])
            args.destino.mkdir(parents=True);creado=True
            (args.destino/'seleccion.json').write_text(json.dumps(resultado,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps({'ok':True,'modelo':resultado['modelo'],'criterio':'seleccion'}));return 0
        if args.accion=='evaluar':
            import tempfile
            from igea_dgs.training_coordinator import BloqueoGPU
            from igea_dgs.asistente.llm_destilacion import evaluar_version_llm
            args.destino.mkdir(parents=True);creado=True
            with BloqueoGPU(Path(tempfile.gettempdir())/'igea-dgs-gpu.lock','evaluacion-llm-generativo'):
                resultado=evaluar_version_llm(args.dataset,args.modelo,parte=args.parte,seleccion=args.seleccion,
                    log=print)
            (args.destino/'resultado.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            print(json.dumps({k:v for k,v in resultado.items() if k!='metricas'},ensure_ascii=True));return 0
        if args.accion=='entrenar-epoca':
            import tempfile
            from igea_dgs.training_coordinator import BloqueoGPU
            from igea_dgs.asistente.llm_destilacion import entrenar_epoca
            creado=True
            with BloqueoGPU(Path(tempfile.gettempdir())/'igea-dgs-gpu.lock','destilacion-llm-generativo'):
                resultado=entrenar_epoca(args.dataset,args.destino,epoca=args.epoca,desde=args.desde,
                    semilla=args.semilla,rango=args.rango,lr=args.lr,acumulacion=args.acumulacion,
                    max_tokens=args.max_tokens)
            print(json.dumps(resultado,ensure_ascii=True));return 0
        if args.accion=='sellar':
            from igea_dgs.asistente.llm_destilacion import sellar_particiones
            creado=True
            resultado=sellar_particiones(args.dataset,args.destino)
            print(json.dumps({'ok':True,'dataset_hash':resultado['dataset_hash'],
                              'por_particion':resultado['por_particion']},ensure_ascii=True));return 0
        if args.accion=='exportar':
            import tempfile
            from igea_dgs.training_coordinator import BloqueoGPU
            from igea_dgs.asistente.llm_destilacion import exportar_fusionado
            creado=True
            with BloqueoGPU(Path(tempfile.gettempdir())/'igea-dgs-gpu.lock','exportar-alumno-llm'):
                resultado=exportar_fusionado(args.destino,args.adaptador)
            print(json.dumps(resultado,ensure_ascii=True));return 0
        args.destino.mkdir(parents=True)
        creado=True
        from igea_dgs.asistente.llm_destilacion import extraer_referencia, construir_corpus_real, custodiar
        fuentes=args.destino/'fuentes';fuentes.mkdir()
        copias=[];originales=[]
        for i,entrada in enumerate(args.workspace):
            original=custodiar(entrada,localizador='workspace registrado')
            copia=fuentes/f'workspace_{i:03d}.json'
            shutil.copyfile(entrada,copia)
            if custodiar(copia,localizador='workspace registrado')['sha256']!=original['sha256']:
                raise ValueError('el workspace cambio durante la copia de custodia')
            copias.append(copia);originales.append(original)
        contextos,manifest=extraer_referencia(red=args.red,cargas=args.cargas,equipos=args.equipos,
            estructura_pdf=args.estructura_pdf,mediciones=args.mediciones,nuevos_clientes=args.nuevos_clientes,
            workspaces=copias)
        manifest['workspaces_originales']=originales
        from igea_dgs.asistente import almacen
        from igea_dgs.asistente.llm_destilacion import reservar_humanas
        humanas=reservar_humanas(almacen.leer('ejemplos'))
        filas,meta=construir_corpus_real(contextos,manifest,max_train_por_tarea=args.max_train_por_tarea,humanas=humanas)
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
