#!/usr/bin/env python
"""Benchmark calculado de GA, NSGA-II y DE; no contiene mediciones electricas (043/048)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds',type=int,default=30)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args(argv)
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo
    if args.report.exists():print('Informe existente conservado');return 2
    inicio=time.monotonic()
    try:
        if args.seeds<30:raise ValueError('el benchmark requiere al menos 30 semillas')
        import numpy as np
        from convertersmartgrid.digital_twin.evolutivo import algoritmo_genetico,nsga2,evolucion_diferencial
        algoritmos={k:[] for k in ('ga','nsga2','de')}
        for semilla in range(args.seeds):
            objetivo=np.array([3,0,2,1,4])
            f=lambda x:float(np.sum((x-objetivo)**2))
            ga=algoritmo_genetico(f,[0]*5,[4]*5,poblacion=30,generaciones=100,paciencia=30,semilla=semilla,iniciales=[[0]*5])
            frente=nsga2(lambda x:([float(x[0]**2),float((x[0]-2)**2)],0.),[-5.],[5.],
                         enteros=False,poblacion=30,generaciones=40,semilla=semilla)
            rosen=lambda x:float(np.sum(100*(x[1:]-x[:-1]**2)**2+(1-x[:-1])**2))
            de=evolucion_diferencial(rosen,[-2.]*3,[2.]*3,poblacion=30,generaciones=250,paciencia=80,semilla=semilla)
            algoritmos['ga'].append({'semilla':semilla,'objetivo':ga.aptitud,'evaluaciones':ga.evaluaciones,'solucion':ga.mejor.tolist()})
            algoritmos['de'].append({'semilla':semilla,'objetivo':de.aptitud,'evaluaciones':de.evaluaciones,'solucion':de.mejor.tolist()})
            if not len(frente.soluciones):raise RuntimeError('NSGA-II no produjo frente')
            distancia=float(np.mean([max(0.,-x[0],x[0]-2.) for x in frente.soluciones]))
            algoritmos['nsga2'].append({'semilla':semilla,'distancia_al_frente_analitico':distancia,
                'evaluaciones':frente.evaluaciones,'factibles':int(np.sum(frente.violacion==0)),
                'puntos':len(frente.soluciones)})
            print(f'benchmark: semilla {semilla+1}/{args.seeds}',flush=True)
        resumen={}
        for nombre,filas in algoritmos.items():
            valores=[r['objetivo'] if nombre!='nsga2' else r['distancia_al_frente_analitico'] for r in filas]
            if not np.isfinite(valores).all():raise RuntimeError('objetivo no finito')
            resumen[nombre]={'semillas':len(filas),'mediana':float(np.median(valores)),
                'q25':float(np.quantile(valores,.25)),'q75':float(np.quantile(valores,.75)),
                'evaluaciones':sum(r['evaluaciones'] for r in filas)}
        resultado={'schema_version':1,'status':'RECHAZADO','promovido':False,'training_completed':False,
            'evaluation_completed':True,'dominio':'benchmark_analitico_no_red_electrica',
            'reason':'benchmark de algoritmos ejecutado; no acredita aceptacion electrica ni promocion',
            'algoritmos':algoritmos,'resumen':resumen,'duracion_s':time.monotonic()-inicio,
            'gates':{'approved':False},'escrituras_nativas':0}
        codigo=0
    except Exception as exc:resultado=fallo(exc);codigo=2
    escribir_informe(args.report,resultado)
    print(json.dumps({k:resultado[k] for k in ('status','training_completed','promovido')},ensure_ascii=True))
    return codigo


if __name__=='__main__':raise SystemExit(main())
