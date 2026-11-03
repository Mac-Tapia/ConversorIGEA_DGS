#!/usr/bin/env python
"""Trabajador de series observadas: GRU causal, inventario y competición de pronósticos (043/046).

``--inventario`` dice qué hay de verdad sin entrenar. ``--comparar`` hace competir a las referencias,
la GRU y los adaptadores en las mismas ventanas, para cabecera o para clientes fijos, y escribe un
artefacto con la marca ``pronostico``. La GPU solo se pide si compite un modelo neuronal.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))


def _objetivos(args):
    """Los objetivos de la clase pedida, con los lectores de la medición (046:RF-9 a RF-11)."""
    from convertersmartgrid.digital_twin.temporal_entrenamiento import objetivos_de_cabecera,objetivos_de_clientes
    rutas=([args.cabeceras] if args.cabeceras else [])+list(args.libro or [])
    if not rutas:raise ValueError('indique el libro de la medición')
    if not args.clase:raise ValueError('indique --clase cabecera o cliente')
    if not args.zona_horaria or not args.cadencia_min:raise ValueError('indique --zona-horaria y --cadencia-min de la medición')
    if args.clase=='cliente':return (*objetivos_de_clientes(rutas,args.cliente or None),rutas)
    pares=[tuple(v.split('=',1)) for v in args.par] or None
    centrales={}
    for v in args.central:
        alimentador,medidores=v.split('=',1)
        centrales[alimentador]=dict(zip(('generacion','llegada','salida'),medidores.split(','),strict=True))
    return (*objetivos_de_cabecera(rutas,pares,centrales=centrales),rutas)


def _pronostico(args):
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo,semillas_de,sha_archivo,turno_gpu
    if args.output_json.exists():print('Informe existente conservado');return 2
    try:
        objetivos,apartados,rutas=_objetivos(args)
        if args.inventario:
            from convertersmartgrid.digital_twin.temporal_entrenamiento import inventariar
            resultado={**inventariar(objetivos,cadencia_min=args.cadencia_min,zona_horaria=args.zona_horaria),'apartados':apartados}
        else:
            from convertersmartgrid.digital_twin.pronostico import NEURONALES
            from convertersmartgrid.digital_twin.temporal_entrenamiento import comparar_pronosticos
            from convertersmartgrid.model_registry import RegistroModelo
            algoritmos=tuple(a.strip() for a in args.comparar.split(',') if a.strip())
            if args.registro:registro=RegistroModelo(args.registro)
            else:
                from convertersmartgrid.asistente import almacen
                registro=RegistroModelo(almacen.raiz()/'model_registry')
            ajustes={k:v for k,v in (('pasos',args.pasos),('lote',args.lote),('contexto_pasos',args.contexto_modelo)) if v}
            hojas=[p for p in rutas if p.is_file()]
            procedencia={'rutas':[str(p.resolve()) for p in rutas],'sha256':{p.name:sha_archivo(p) for p in hojas},
                         'clase':args.clase,'zona_horaria':args.zona_horaria,'cadencia_min':args.cadencia_min}
            horizontes=tuple(int(v) for v in args.horizontes.split(',')) if args.horizontes else None
            def correr():
                return comparar_pronosticos(objetivos,args.raiz,clase=args.clase,algoritmos=algoritmos,horizontes=horizontes,
                    cadencia_min=args.cadencia_min,zona_horaria=args.zona_horaria,semillas=semillas_de(args.semillas),
                    procedencia=procedencia,registro=registro,contexto_pasos=args.contexto_pasos,
                    paso_emision_min=args.paso_emision_min,ajustes_modelo=ajustes,apartados_previos=apartados,log=print)
            if set(algoritmos)&set(NEURONALES):
                # La guardia y el margen de memoria, solo si compite una red: las referencias no los piden.
                from convertersmartgrid.training_coordinator import exigir_memoria_ml
                exigir_memoria_ml(3.,minimo_commit_gib=6.)
                with turno_gpu('pronostico-temporal'):resultado=correr()
            else:resultado=correr()
        codigo=0
    except Exception as exc:resultado=fallo(exc);codigo=2
    escribir_informe(args.output_json,resultado)
    print(json.dumps({k:resultado.get(k) for k in ('status','reason','promovido','artefacto','candidate_id')},ensure_ascii=True))
    return codigo


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    entrada=p.add_mutually_exclusive_group(required=True)
    entrada.add_argument('--cabeceras',type=Path)
    entrada.add_argument('--reabrir',type=Path)
    entrada.add_argument('--reabrir-candidato',type=Path,help='Carpeta de un candidato de pronóstico: comprueba su reapertura')
    entrada.add_argument('--libro',type=Path,action='append',help='Libro o carpeta de la medición; se puede repetir')
    p.add_argument('--raiz',type=Path)
    p.add_argument('--output-json',type=Path)
    p.add_argument('--inventario',action='store_true',help='Solo lista rango, cadencia y huecos de cada objetivo')
    p.add_argument('--comparar',help='Modelos que compiten, separados por coma: ingenuo, estacional_semanal, gru, nhits, tft, patchtst')
    p.add_argument('--clase',choices=('cabecera','cliente'),help='Objetivos: demanda de cabecera o clientes fijos; se deciden por separado')
    p.add_argument('--par',action='append',default=[],help='Cabecera: alimentador=medidor; se puede repetir. Sin ninguno, cada hoja con kW')
    p.add_argument('--central',action='append',default=[],help='Cabecera: alimentador=generación,llegada,salida; la demanda con la central descontada')
    p.add_argument('--cliente',action='append',default=[],help='Clientes: código de suministro; se puede repetir. Sin ninguno, todos los del maestro')
    p.add_argument('--cadencia-min',type=int,help='Cadencia declarada; un libro que no la cumpla se aparta')
    p.add_argument('--horizontes',help='Horizontes en pasos, separados por coma; (1,4,96) solo con 15 minutos')
    p.add_argument('--contexto-pasos',type=int,help='Ventana común de contexto; por defecto, una semana')
    p.add_argument('--paso-emision-min',type=int,default=60,help='Minutos entre emisiones evaluadas')
    p.add_argument('--pasos',type=int,help='Pasos de entrenamiento de los modelos neuronales')
    p.add_argument('--lote',type=int,help='Ventanas por lote de los modelos neuronales')
    p.add_argument('--contexto-modelo',type=int,help='Pasos de contexto que usan los modelos neuronales')
    p.add_argument('--registro',type=Path,help='Registro de modelos; por defecto el del almacén del asistente')
    p.add_argument('--semillas',default='11,23,37,53,71')
    p.add_argument('--epocas',type=int,default=40)
    p.add_argument('--zona-horaria')
    p.add_argument('--codigos',help='Codigos explicitos de las columnas del libro ancho, separados por coma')
    p.add_argument('--hoja',action='append',default=[],help='Hoja de medidor explícita; se puede repetir')
    p.add_argument('--desde',help='Inicio ISO inclusivo del alcance, fijado antes del ajuste')
    p.add_argument('--hasta',help='Fin ISO exclusivo del alcance, fijado antes del ajuste')
    args=p.parse_args(argv)
    if args.reabrir_candidato:
        from convertersmartgrid.digital_twin.temporal_entrenamiento import reabrir_candidato
        from convertersmartgrid.trabajadores_ml import fallo,turno_gpu
        try:
            with turno_gpu('pronostico-reapertura'):resultado=reabrir_candidato(args.reabrir_candidato)
        except Exception as exc:resultado={**fallo(exc),'ok':False}
        print(json.dumps(resultado,ensure_ascii=True))
        return 0 if resultado.get('ok') else 2
    if not args.raiz or not args.output_json:p.error('indique --raiz y --output-json')
    if args.inventario or args.comparar:return _pronostico(args)
    if not args.cabeceras and not args.reabrir:p.error('--libro solo vale con --inventario o --comparar')
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo,semillas_de,turno_gpu,sha_archivo
    if args.output_json.exists():print('Informe existente conservado');return 2
    try:
        from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras,entrenar_temporal,reabrir_temporal
        if args.cabeceras:
            series,procedencia=cargar_cabeceras(args.cabeceras,zona_horaria=args.zona_horaria,
                codigos=tuple(v.strip() for v in (args.codigos or '').split(',') if v.strip()),
                hojas=tuple(args.hoja),desde=args.desde,hasta=args.hasta)
            semillas=semillas_de(args.semillas)
            if args.epocas<1:raise ValueError('epocas positivas obligatorias')
        from convertersmartgrid.training_coordinator import exigir_memoria_ml
        exigir_memoria_ml(3.,minimo_commit_gib=6.)
        with turno_gpu('gru-temporal'):
            if args.reabrir:resultado=reabrir_temporal(args.reabrir)
            else:
                resultado=entrenar_temporal(series,args.raiz,semillas=semillas,procedencia=procedencia,epocas=args.epocas)
                if sha_archivo(args.cabeceras)!=procedencia['sha256']:raise ValueError('el libro cambio durante el ajuste')
        codigo=0
    except Exception as exc:resultado=fallo(exc);codigo=2
    escribir_informe(args.output_json,resultado)
    print(json.dumps({k:v for k,v in resultado.items() if k not in ('seleccion','prueba','baseline_estacional')},ensure_ascii=True))
    return codigo


if __name__=='__main__':raise SystemExit(main())
