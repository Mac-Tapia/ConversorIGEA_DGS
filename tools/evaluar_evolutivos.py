#!/usr/bin/env python
"""Benchmark calculado de GA, NSGA-II y DE (y los de pymoo si está) con el mismo presupuesto de
evaluaciones, las mismas semillas y la misma reparación; no contiene mediciones eléctricas (043/048)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
if str(REPO/'src') not in sys.path:sys.path.insert(0,str(REPO/'src'))


def problemas_analiticos():
    """Los tres problemas de óptimo conocido que ya usaba esta etapa, ahora declarados (048:RF-1).

    Antes cada algoritmo corría con sus generaciones y poblaciones: el genético evaluaba más que
    NSGA-II y la comparación medía el presupuesto. Con ``comparar_optimizadores`` todos gastan lo
    mismo (048:RF-3).
    """
    from convertersmartgrid.digital_twin import problema_optimizacion as po
    ctx=lambda d:po.ContextoSintetico('benchmark_analitico_no_red_electrica',d)
    objetivo=(3,0,2,1,4)

    def entero(v):
        return {'convergio':True,'objetivos':{'distancia':float(sum((v[f'x{i}']-o)**2 for i,o in enumerate(objetivo)))},
                'violaciones':{},'demanda_referencia_kw':0.0,'demanda_atendida_kw':0.0}

    def schaffer(v):
        x=v['x']
        return {'convergio':True,'objetivos':{'f1':x*x,'f2':(x-2)**2},'violaciones':{},
                'demanda_referencia_kw':0.0,'demanda_atendida_kw':0.0}

    def rosenbrock(v):
        x=[v['x0'],v['x1'],v['x2']]
        f=sum(100*(x[i+1]-x[i]**2)**2+(1-x[i])**2 for i in range(2))
        return {'convergio':True,'objetivos':{'rosenbrock':float(f)},'violaciones':{},
                'demanda_referencia_kw':0.0,'demanda_atendida_kw':0.0}

    var=lambda n,t,a,b:po.Variable(n,t,'adimensional',inferior=a,superior=b,origen='función de prueba analítica')
    return [
        po.ProblemaOptimizacion('entero_cuadratico',tuple(var(f'x{i}','entera',0,4) for i in range(5)),(),
            (po.Objetivo('distancia','adimensional'),),ctx('distancia entera a (3,0,2,1,4) en [0,4]^5'),
            'analitico@1',entero,normalizacion={'distancia':(0.0,54.0)}),
        po.ProblemaOptimizacion('schaffer_n1',(var('x','continua',-5,5),),(),
            (po.Objetivo('f1','adimensional'),po.Objetivo('f2','adimensional')),ctx('Schaffer N.1, frente en [0, 2]'),
            'analitico@1',schaffer,normalizacion={'f1':(0.0,4.0),'f2':(0.0,4.0)}),
        po.ProblemaOptimizacion('rosenbrock_3',tuple(var(f'x{i}','continua',-2,2) for i in range(3)),(),
            (po.Objetivo('rosenbrock','adimensional'),),ctx('Rosenbrock en [-2,2]^3, óptimo 0 en (1,1,1)'),
            'analitico@1',rosenbrock,normalizacion={'rosenbrock':(0.0,7300.0)})]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds',type=int,default=30)
    p.add_argument('--presupuesto',type=int,default=300,help='evaluaciones reales por ejecución, iguales para todos')
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args(argv)
    from convertersmartgrid.trabajadores_ml import escribir_informe,fallo
    if args.report.exists():print('Informe existente conservado');return 2
    inicio=time.monotonic()
    try:
        if args.seeds<30:raise ValueError('el benchmark requiere al menos 30 semillas')
        from convertersmartgrid.digital_twin.benchmark_optimizacion import comparar_optimizadores
        hechas=[0]

        def avance():
            hechas[0]+=1
            if hechas[0]%1000==0:print(f'benchmark: {hechas[0]} evaluaciones',flush=True)
            return False

        comparacion=comparar_optimizadores(problemas_analiticos(),semillas=tuple(range(args.seeds)),
                                           presupuesto=args.presupuesto,cancelado=avance)
        if comparacion['estado']!='completo':raise RuntimeError(f"benchmark {comparacion['estado']}")
        errores=[f"{pr['nombre']}/{n}: {e['error']}" for pr in comparacion['problemas']
                 for n,a in pr['algoritmos'].items() for e in a['ejecuciones'] if e['estado']=='error']
        if errores:raise RuntimeError('; '.join(errores[:5]))
        resumen={pr['nombre']:{n:a.get('resumen',{'estado':a['estado'],'motivo':a.get('motivo')})
                               for n,a in pr['algoritmos'].items()} for pr in comparacion['problemas']}
        resultado={'schema_version':2,'status':'RECHAZADO','promovido':False,'training_completed':False,
            'evaluation_completed':True,'dominio':'benchmark_analitico_no_red_electrica',
            'reason':'benchmark de algoritmos ejecutado; no acredita aceptacion electrica ni promocion',
            'metodo':comparacion['metodo'],'algoritmos':comparacion['metodo']['algoritmos'],'resumen':resumen,
            'comparacion':comparacion,'avisos':comparacion['avisos'],'duracion_s':time.monotonic()-inicio,
            'gates':{'approved':False},'escrituras_nativas':0}
        codigo=0
    except Exception as exc:resultado=fallo(exc);codigo=2
    escribir_informe(args.report,resultado)
    print(json.dumps({k:resultado[k] for k in ('status','training_completed','promovido')},ensure_ascii=True))
    return codigo


if __name__=='__main__':raise SystemExit(main())
