"""046:RF-1/3/7/8: entrenamiento causal y persistencia de candidatos GRU."""
from __future__ import annotations
import json
import math
from pathlib import Path
from datetime import timedelta
import uuid


def cargar_cabeceras(ruta: Path, *, zona_horaria: str, codigos: tuple[str,...] = ()) -> tuple[dict,dict]:
    """Consume los lectores de cabecera existentes; nunca rellena huecos con cero."""
    from ..demanda_medida import _abrir,_filas,_registros_hoja,_como_datetime,ALIAS
    from .series_causales import preparar_serie
    from ..trabajadores_ml import sha_archivo
    if not ruta.is_file():raise ValueError('no existe el libro de cabeceras')
    if not zona_horaria:raise ValueError('indique --zona-horaria para las fechas del libro')
    series={};fechas={};omitidas=[]
    if codigos:
        from ..cabecera_ancha import leer_ancho
        lectura=leer_ancho([ruta],codigos)
        crudas={n:[(t,pq[0]) for t,pq in sorted(s.items())] for n,s in lectura.series.items()}
        if set(crudas)!=set(codigos):raise ValueError('faltan codigos solicitados en el libro ancho')
    else:
        libro=_abrir(ruta);crudas={}
        try:
            for nombre in libro.sheet_names:
                registros,usadas=_registros_hoja(_filas(libro,nombre),ALIAS)
                if 'kw' not in usadas:omitidas.append(nombre);continue
                pares=[(_como_datetime(r.fecha),r.valores.get('kw')) for r in registros]
                if pares:crudas[nombre]=pares
        finally:
            cerrar=getattr(libro,'close',None)
            if cerrar:cerrar()
    if not crudas:raise ValueError('sin series de fecha y kW; libro ancho requiere --codigos')
    for nombre,pares in crudas.items():
        if any(t is None or v is None for t,v in pares):raise ValueError(f'{nombre}: fecha o potencia ausente')
        registros=[{'instante':t.isoformat(),'valor':v,'unidad':'kW'} for t,v in pares]
        # La escala devuelta por este validador no se usa: la GRU la ajusta solo en train.
        preparada=preparar_serie(registros,corte=(max(t for t,_ in pares)+timedelta(minutes=15)).isoformat(),
            cadencia_min=15,zona_horaria=zona_horaria,covariables={})
        if not all(preparada['mascara']):raise ValueError(f'{nombre}: huecos; no se imputan objetivos')
        series[nombre]=[r['valor'] for r in preparada['filas']]
        fechas[nombre]=[r['instante'] for r in preparada['filas']]
    if len({tuple(v) for v in fechas.values()})!=1:raise ValueError('las series no comparten cronologia')
    return series,{'path':str(ruta.resolve()),'sha256':sha_archivo(ruta),'zona_horaria':zona_horaria,
        'cadencia_min':15,'unidad':'kW','targets_imputed':False,'hojas_omitidas':omitidas,
        'instantes':next(iter(fechas.values()))}


def entrenar_temporal(series: dict, destino: Path, *, semillas: tuple[int,...], procedencia: dict,
                       epocas: int = 40, ventana: int = 96) -> dict:
    from .temporal import GemeloGRU,ModeloEstacional,metricas
    from ..trabajadores_ml import escribir_informe,sha_archivo
    if not series or epocas<1 or ventana<1 or not semillas:raise ValueError('series y parametros de ajuste obligatorios')
    largos={len(s) for s in series.values()}
    if len(largos)!=1 or min(largos)<30*96:raise ValueError('se requieren al menos 30 dias comunes de 15 minutos')
    import numpy as np
    for nombre,s in series.items():
        if not np.isfinite(s).all():raise ValueError(f'{nombre}: serie no finita')
    n=largos.pop();fin_train=int(.7*n);inicio_val=fin_train+ventana
    fin_val=int(.85*n);inicio_test=fin_val+ventana
    if fin_val<=inicio_val or n<=inicio_test:raise ValueError('particiones insuficientes tras separar ventanas')
    candidatos=[];mejor=None
    for semilla in semillas:
        modelos={};val={}
        for nombre,s in sorted(series.items()):
            modelo=GemeloGRU(ventana=ventana,epocas=epocas,semilla=semilla)
            modelo.entrenar(s[:fin_train]);modelo.red.eval()
            pred=modelo.reproducir(s[:fin_val])
            val[nombre]=metricas(s[inicio_val:fin_val],pred[inicio_val:fin_val]);modelos[nombre]=modelo
        score=float(np.mean([m['mae_kw'] for m in val.values()]))
        if not math.isfinite(score):raise RuntimeError('error de seleccion no finito')
        candidatos.append({'semilla':semilla,'mae_kw':score,'seleccion':val})
        if mejor is None or score<mejor[0]:mejor=(score,semilla,modelos)
    _,semilla,modelos=mejor
    carpeta=destino/('candidato_'+uuid.uuid4().hex);carpeta.mkdir(parents=True)
    import torch
    prueba={};base={};metas={};sondas={};hashes={}
    for i,(nombre,modelo) in enumerate(sorted(modelos.items())):
        s=series[nombre]
        prueba[nombre]=metricas(s[inicio_test:],modelo.reproducir(s)[inicio_test:])
        base[nombre]=metricas(s[inicio_test:],ModeloEstacional().reproducir(s)[inicio_test:])
        archivo=f'modelo_{i:04d}.pt'
        torch.save({k:v.detach().cpu() for k,v in modelo.red.state_dict().items()},carpeta/archivo)
        hashes[archivo]=sha_archivo(carpeta/archivo)
        metas[nombre]={'archivo':archivo,'cfg':{'ventana':ventana,'epocas':epocas,'semilla':semilla},'escala':modelo.escala}
        sonda=s[:ventana+4];esperado=modelo.reproducir(sonda)[ventana:].tolist()
        sondas[nombre]={'serie':sonda,'prediccion':esperado}
    meta={'semilla':semilla,'modelos':metas,'sondas':sondas,'hashes':hashes,
        'procedencia':procedencia,'seleccion':candidatos,'prueba':prueba,'estacional':base,
        'particiones':{'fin_train':fin_train,'inicio_seleccion':inicio_val,'fin_seleccion':fin_val,'inicio_prueba':inicio_test,'n':n}}
    escribir_informe(carpeta/'modelo.json',meta)
    return {'status':'RECHAZADO','candidate_status':'CANDIDATO','training_completed':True,'entrenado':True,
        'promovido':False,'gates':{'approved':False},'candidate_dir':str(carpeta.resolve()),
        'reason':'candidato conservado; faltan recarga independiente y puertas conjuntas',
        'seleccion':candidatos,'prueba':prueba,'baseline_estacional':base}


def reabrir_temporal(carpeta: Path) -> dict:
    from .temporal import GemeloGRU
    from ..trabajadores_ml import sha_archivo
    import numpy as np
    import torch
    meta=json.loads((carpeta/'modelo.json').read_text(encoding='utf-8'));errores={}
    for nombre,m in meta['modelos'].items():
        f=carpeta/m['archivo']
        if f.resolve().parent!=carpeta.resolve() or sha_archivo(f)!=meta['hashes'][m['archivo']]:raise ValueError('pesos temporales alterados')
        modelo=GemeloGRU(**m['cfg']);modelo.escala=m['escala']
        modelo.red.load_state_dict(torch.load(f,weights_only=True,map_location=modelo.disp));modelo.red.eval()
        sonda=meta['sondas'][nombre]
        obtenido=modelo.reproducir(sonda['serie'])[modelo.ventana:]
        error=float(np.max(np.abs(obtenido-np.asarray(sonda['prediccion']))))
        if not math.isfinite(error) or error>1e-4:raise RuntimeError('prediccion recargada distinta')
        errores[nombre]=error
    return {'status':'RECHAZADO','training_completed':False,'promovido':False,
        'smoke_reload':{'ok':True,'errores_max_kw':errores},'reason':'recarga comprobada, no es un nuevo entrenamiento'}
