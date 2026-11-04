"""046:RF-1/3/7/8: entrenamiento causal y persistencia de candidatos GRU."""
from __future__ import annotations
import json
import math
from pathlib import Path
from datetime import timedelta
import uuid

import numpy as np
from ..runtime_paths import raiz_programa


def cargar_cabeceras(ruta: Path, *, zona_horaria: str, codigos: tuple[str,...] = (),
                     hojas: tuple[str,...] = (), desde: str | None = None,
                     hasta: str | None = None) -> tuple[dict,dict]:
    """Consume los lectores de cabecera existentes; nunca rellena huecos con cero."""
    from ..demanda_medida import abrir_libro,filas_de_hoja,registros_de_hoja,ALIAS
    from ..cabecera_ancha import instante
    from .series_causales import preparar_serie, instante_local
    from zoneinfo import ZoneInfo
    from ..trabajadores_ml import sha_archivo
    if not ruta.is_file():raise ValueError('no existe el libro de cabeceras')
    hash_antes=sha_archivo(ruta)
    if not zona_horaria:raise ValueError('indique --zona-horaria para las fechas del libro')
    zona=ZoneInfo(zona_horaria)
    if bool(desde)!=bool(hasta):raise ValueError('declare ambos límites desde/hasta')
    inicio=instante_local(desde,zona) if desde else None
    fin=instante_local(hasta,zona) if hasta else None
    if inicio is not None and inicio>=fin:raise ValueError('intervalo temporal vacío o invertido')
    if codigos and hojas:raise ValueError('seleccione códigos de libro ancho u hojas, no ambos')
    series={};fechas={};omitidas=[]
    if codigos:
        from ..cabecera_ancha import leer_ancho
        lectura=leer_ancho([ruta],codigos)
        crudas={n:[(t,pq[0],None) for t,pq in sorted(s.items())] for n,s in lectura.series.items()}
        if set(crudas)!=set(codigos):raise ValueError('faltan codigos solicitados en el libro ancho')
    else:
        libro=abrir_libro(ruta);crudas={}
        try:
            if set(hojas)-set(libro.sheet_names):raise ValueError('faltan hojas solicitadas en el libro')
            for nombre in hojas or libro.sheet_names:
                registros,usadas=registros_de_hoja(filas_de_hoja(libro,nombre),ALIAS)
                if 'kw' not in usadas:
                    if hojas:raise ValueError(f'{nombre}: hoja solicitada sin columna kW')
                    omitidas.append(nombre);continue
                pares=[]
                for registro in registros:
                    try:
                        t=instante(registro.fecha)
                    except (ValueError,TypeError,OverflowError) as exc:
                        raise ValueError(f'{nombre}: fila {registro.fila_origen}: fecha inválida') from exc
                    pares.append((t,registro.valores.get('kw'),registro.fila_origen))
                if pares:crudas[nombre]=pares
        finally:
            cerrar=getattr(libro,'close',None)
            if cerrar:cerrar()
    if not crudas:raise ValueError('sin series de fecha y kW; libro ancho requiere --codigos')
    fuera={}
    for nombre,lectura in crudas.items():
        pares=[];fuera[nombre]=0;vistos=set()
        for t,v,fila in lectura:
            if t is None:raise ValueError(f'{nombre}: fila {fila}: fecha ausente/inválida')
            try:
                utc=instante_local(t.isoformat(),zona)
            except ValueError as exc:
                raise ValueError(f'{nombre}: fila {fila}: fecha inválida: {exc}') from exc
            if inicio is not None and not inicio<=utc<fin:
                fuera[nombre]+=1;continue
            if utc in vistos:raise ValueError(f'{nombre}: fila {fila}: instante duplicado {utc.isoformat()}')
            vistos.add(utc)
            if v is None:raise ValueError(f'{nombre}: fila {fila}: potencia ausente/inválida')
            pares.append((t,v))
        if not pares:raise ValueError(f'{nombre}: sin observaciones en el intervalo declarado')
        registros=[{'instante':t.isoformat(),'valor':v,'unidad':'kW'} for t,v in pares]
        # La escala devuelta por este validador no se usa: la GRU la ajusta solo en train.
        try:
            preparada=preparar_serie(registros,corte=(max(t for t,_ in pares)+timedelta(minutes=15)).isoformat(),
                cadencia_min=15,zona_horaria=zona_horaria,covariables={})
        except ValueError as exc:
            raise ValueError(f'{nombre}: {exc}') from exc
        if not all(preparada['mascara']):raise ValueError(f'{nombre}: huecos; no se imputan objetivos')
        series[nombre]=[r['valor'] for r in preparada['filas']]
        fechas[nombre]=[r['instante'] for r in preparada['filas']]
    if len({tuple(v) for v in fechas.values()})!=1:raise ValueError('las series no comparten cronologia')
    if sha_archivo(ruta)!=hash_antes:raise ValueError('el libro cambió durante la lectura')
    return series,{'path':str(ruta.resolve()),'sha256':hash_antes,'zona_horaria':zona_horaria,
        'cadencia_min':15,'unidad':'kW','targets_imputed':False,'hojas_omitidas':omitidas,
        'alcance':{'hojas':list(hojas),'codigos':list(codigos),'desde':desde,'hasta_exclusivo':hasta,
                   'filas_fuera_intervalo':fuera},
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
        metas[nombre]={'archivo':archivo,'cfg':modelo.configuracion(),'escala':modelo.escala,
                       'validacion':modelo.validacion,'historial':modelo.historial,
                       'optimizer_updates':modelo.optimizer_updates,
                       'optimizador':{'nombre':'Adam','lr':.01,'lote':256,'scheduler':'CosineAnnealingLR','lr_min':.0001}}
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


# ---------------------------------------------------------------------- pronóstico (spec 046)
def _objetivos_kw_kvar(clase: str, ident: str, curva, fuente: dict):
    """kW y kVAR de una misma curva ``(t, kW, kVAR)``; el kVAR solo si el libro lo trae."""
    from .pronostico import Objetivo

    salida = [Objetivo(clase, ident, 'kW', 'kW', [(t, kw) for t, kw, _q in curva], fuente)]
    if any(q is not None for _t, _p, q in curva):
        salida.append(Objetivo(clase, ident, 'kVAR', 'kVAR', [(t, q) for t, _p, q in curva if q is not None], fuente))
    return salida


def objetivos_de_cabecera(rutas, pares=None, *, centrales=None) -> tuple[list, list[dict]]:
    """kW y kVAR de cada ``(alimentador, medidor)``, con ``maximas`` (046:RF-9).

    Sin pares, cada hoja con kW es un objetivo. Con los medidores de una central, la demanda es la
    de ``curva_de_demanda`` (046:RF-10): sin ella, una cabecera con generación aguas abajo daría
    la potencia del alimentador en vez de su demanda.
    """
    from ..demanda_medida import curva_de_demanda, indexar_libro_cabecera, libros_de_cabecera, maximas

    libros = libros_de_cabecera(rutas)
    if pares is None:
        pares = [(h, h) for p in libros for h in indexar_libro_cabecera(p)['hojas']]
    centrales = dict(centrales or {})
    pedidos = list(pares)
    for alimentador, c in centrales.items():
        pedidos += [(alimentador, c[k]) for k in ('generacion', 'llegada', 'salida')]
    leidos = {(r.alimentador, r.medidor): r for r in maximas(libros, pedidos)}
    objetivos, apartados = [], []
    for alimentador, medidor in pares:
        r = leidos.get((alimentador, medidor))
        if r is None or r.error or not r.curva:
            apartados.append({'objetivo': f'cabecera:{alimentador}',
                              'motivo': (r.error if r is not None and r.error else f'{medidor}: sin curva en los libros')})
            continue
        curva = r.curva
        central = centrales.get(alimentador)
        if central:
            otros = [leidos.get((alimentador, central[k])) for k in ('generacion', 'llegada', 'salida')]
            if any(o is None or not o.curva for o in otros):
                apartados.append({'objetivo': f'cabecera:{alimentador}',
                                  'motivo': 'falta la curva de un medidor de la central; no se pronostica sin descontarla'})
                continue
            curva, informe = curva_de_demanda(curva, otros[0].curva, otros[1].curva, otros[2].curva)
            if not curva:
                apartados.append({'objetivo': f'cabecera:{alimentador}', 'motivo': f'sin demanda con la central: {informe.error}'})
                continue
        objetivos += _objetivos_kw_kvar('cabecera', alimentador, curva, {
            'medidor': medidor, 'libros': [r.libro], 'central_descontada': bool(central), 'avisos': list(r.avisos)})
    return objetivos, apartados


def objetivos_de_clientes(rutas, codigos=None) -> tuple[list, list[dict]]:
    """kW y kVAR de cada cliente libre desde sus hojas de 15 minutos (046:RF-11).

    Un cliente viene repartido en un libro por mes. Dos valores distintos del mismo instante
    no se eligen: el objetivo se aparta y se dice (046:RF-12).
    """
    from ..cabecera_ancha import libros_de
    from ..demanda_medida import curvas_de_clientes

    por_cliente: dict[str, dict] = {}
    libros_de_cliente: dict[str, list[str]] = {}
    contradictorios: dict[str, str] = {}
    avisos: dict[str, list[str]] = {}
    apartados: list[dict] = []
    for libro in libros_de(rutas):
        curvas, notas = curvas_de_clientes(libro, codigos)
        if not curvas and not codigos:
            # Un mes que no se puede leer no se calla: el objetivo tendría un hueco sin explicar.
            apartados.append({'objetivo': f'libro:{libro.name}', 'motivo': '; '.join(notas) or 'sin curvas de clientes'})
        for codigo, curva in curvas.items():
            serie = por_cliente.setdefault(codigo, {})
            libros_de_cliente.setdefault(codigo, []).append(libro.name)
            for t, kw, kvar in curva:
                previo = serie.setdefault(t, (kw, kvar))
                if previo != (kw, kvar):
                    contradictorios[codigo] = f'{libro.name} da otro valor en el mismo instante ({t.isoformat()})'
        for nota in notas:
            avisos.setdefault(nota.split(':', 1)[0], []).append(nota)
    objetivos = []
    for codigo, serie in por_cliente.items():
        if codigo in contradictorios:
            apartados.append({'objetivo': f'cliente:{codigo}', 'motivo': contradictorios[codigo]})
            continue
        curva = [(t, *serie[t]) for t in sorted(serie)]
        objetivos += _objetivos_kw_kvar('cliente', codigo, curva, {
            'libros': libros_de_cliente[codigo], 'avisos': avisos.get(codigo, [])})
    for codigo in codigos or ():
        if not any(c == codigo for c in por_cliente):
            apartados.append({'objetivo': f'cliente:{codigo}', 'motivo': 'no está en el maestro de ningún libro'})
    return objetivos, apartados


def inventariar(objetivos, *, cadencia_min: int, zona_horaria: str) -> dict:
    """Qué hay de verdad, sin entrenar ni rellenar nada: rango, cadencia, huecos y ceros (046:RF-12)."""
    from .pronostico import construir_conjunto
    from .series_causales import cadencia_moda, tramos_observados

    filas = []
    for o in objetivos:
        fechas = sorted(t for t, _v in o.curva)
        fila = {'objetivo': o.nombre, 'clase': o.clase, 'magnitud': o.magnitud, 'puntos': len(fechas),
                'inicio': fechas[0].isoformat() if fechas else None, 'fin': fechas[-1].isoformat() if fechas else None,
                'cadencia_moda_min': cadencia_moda(fechas), 'ceros': sum(v == 0 for _t, v in o.curva),
                'libros': list(o.fuente.get('libros') or [])}
        c = construir_conjunto([o], cadencia_min=cadencia_min, zona_horaria=zona_horaria)
        if c.nombres:
            v = c.valores[c.nombres[0]]
            fila.update(huecos=int(np.isnan(v).sum()), dias=len(v) * cadencia_min / 1440,
                        tramos=len(tramos_observados(v, len(v), minimo=1)))
        else:
            fila['apartado'] = c.apartados[0]['motivo']
        filas.append(fila)
    return {'status': 'INVENTARIO', 'training_completed': False, 'promovido': False, 'objetivos': filas}


def _reabrir_en_otro_proceso(carpeta: Path) -> dict:
    """046:RF-7: reabrir en otro proceso, porque en este los pesos siguen en memoria."""
    import sys

    from ..model_registry import reabrir_en_subproceso
    from ..trabajadores_ml import entorno_hijo_gpu

    herramienta = raiz_programa() / 'tools' / 'digital_twin_temporal_entrenar.py'
    return reabrir_en_subproceso([sys.executable, str(herramienta), '--reabrir-candidato', str(carpeta)],
                                 timeout_s=600.0, env=entorno_hijo_gpu())


def _empaquetar(modelo, destino: Path, algoritmo: str) -> Path:
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory(dir=destino) as d:
        carpeta = Path(d) / 'modelo'
        modelo.guardar(carpeta)
        return Path(shutil.make_archive(str(destino / f'modelo_{algoritmo}'), 'zip', carpeta))


def _guardar_sonda(ruta: Path, lote, predicciones: dict) -> None:
    """Unas ventanas y lo que predijo cada modelo: con ellas se comprueba la reapertura."""
    np.savez(ruta, objetivos=np.array(lote.objetivos), contextos=lote.contextos, pasado=lote.calendario_pasado,
             futuro=lote.calendario_futuro, fin=np.array([t.isoformat() for t in lote.fin_contexto]),
             cadencia=np.array(lote.cadencia_min), **{f'pred_{a}': p for a, p in predicciones.items()})


def _abrir_zip(zipa: Path, algoritmo: str, fabricas: dict, destino: Path):
    import shutil

    from .pronostico import reabrir_modelo

    shutil.unpack_archive(str(zipa), destino, 'zip')
    if algoritmo in fabricas:
        return fabricas[algoritmo].reabrir(destino, algoritmo)
    return reabrir_modelo(algoritmo, destino)


def reabrir_candidato(carpeta: Path, *, fabricas: dict | None = None, tolerancia: float = 1e-3) -> dict:
    """Reabre los modelos de un candidato y exige la misma predicción sobre su sonda (046:RF-7)."""
    import tempfile
    from datetime import datetime as Fecha

    from .pronostico import LoteVentanas

    with np.load(carpeta / 'sonda.npz', allow_pickle=False) as z:
        datos = {k: z[k] for k in z.files}
    lote = LoteVentanas([str(o) for o in datos['objetivos']], datos['contextos'], datos['pasado'], datos['futuro'],
                        [Fecha.fromisoformat(str(t)) for t in datos['fin']], int(datos['cadencia']))
    errores = {}
    for clave, esperado in datos.items():
        if not clave.startswith('pred_'):
            continue
        algoritmo = clave.removeprefix('pred_')
        with tempfile.TemporaryDirectory() as d:
            modelo = _abrir_zip(carpeta / f'modelo_{algoritmo}.zip', algoritmo, fabricas or {}, Path(d))
            obtenido = modelo.predecir(lote)
        relativo = np.abs(obtenido - esperado) / np.maximum(np.abs(esperado), 1.0)
        errores[algoritmo] = float(relativo.max())
    malos = {a: e for a, e in errores.items() if not e <= tolerancia}
    return {'ok': not malos, 'errores_relativos': errores, 'reason': f'predicción recargada distinta: {sorted(malos)}' if malos else ''}


def _evaluar_modelo(conjunto, modelo, algoritmo, ventanas, contexto, H, horizontes, politica):
    """Selección, calibración y prueba de un modelo ya ajustado, en las ventanas comunes."""
    from .evaluacion_temporal import error_de_maxima, evaluar_pronosticos, pinball_de, sesgo_de_maxima
    from .pronostico import aplicar_ajuste, calibrar_intervalos, filas_pronostico

    resultado = {'status': 'EVALUADO', 'seleccion': {}, 'prueba': {}, 'ajuste': {}, 'sesgo_maxima': {},
                 'ajuste_calibrado_en': 'calibracion'}
    filas_por_objetivo = {}
    puntos_dia = min(H, 1440 // conjunto.cadencia_min)
    for nombre in conjunto.nombres:
        v = conjunto.valores[nombre]
        pares = {}
        for parte in ('seleccion', 'calibracion', 'prueba'):
            em = ventanas['partes'][parte][nombre]
            lote = conjunto.lote([nombre] * len(em), em, contexto=contexto, horizonte=H)
            p = modelo.predecir(lote)
            if not np.isfinite(p).all():
                raise RuntimeError(f'{algoritmo}: predicción no finita en {nombre}')
            pares[parte] = (em, p, np.stack([v[e + 1:e + H + 1] for e in em]) if len(em) else np.zeros((0, H)))
        ajuste = calibrar_intervalos(pares['calibracion'][1], pares['calibracion'][2], cobertura=politica.cobertura_objetivo)
        resultado['ajuste'][nombre] = ajuste.tolist()
        sesgo = sesgo_de_maxima(pares['calibracion'][2], aplicar_ajuste(pares['calibracion'][1], ajuste)[..., 1],
                                puntos_trayectoria=puntos_dia)
        resultado['sesgo_maxima'][nombre] = sesgo
        em, p, y = pares['seleccion']
        perdida = pinball_de(aplicar_ajuste(p, ajuste), y)
        resultado['seleccion'][nombre] = {'media': float(perdida.mean()),
                                          **{h: float(perdida[:, h - 1].mean()) for h in horizontes}}
        em, p, y = pares['prueba']
        calibrada = aplicar_ajuste(p, ajuste)
        filas = filas_pronostico(conjunto, nombre, em, calibrada, horizontes, algoritmo)
        real = [{'target': f['target'], 'forecast_time': f['forecast_time'],
                 'valor': float(y[i // len(horizontes), f['horizon_steps'] - 1])} for i, f in enumerate(filas)]
        fila = evaluar_pronosticos(real, filas, politica=politica)['contextos'][nombre]
        pico = error_de_maxima(y, calibrada[..., 1], cadencia_min=conjunto.cadencia_min, puntos_trayectoria=puntos_dia,
                               sesgo=sesgo, dias=[filas[i * len(horizontes)]['emission_time'][:10] for i in range(len(em))])
        resultado['prueba'][nombre] = {h: {**m, **{k: v for k, v in pico.items() if k != 'n'}} for h, m in fila.items()}
        filas_por_objetivo[nombre] = filas
    return resultado, filas_por_objetivo


def _decidir_objetivo(nombre, horizontes, modelos, politica, referencias):
    """El ganador de un objetivo: el neuronal mejor en selección, si pasa las puertas en prueba (046:RF-16 a RF-18).

    Solo uno se juzga en prueba: mirar en ella a todos y quedarse con el mejor daría un error optimista.
    """
    from ..evaluacion_modelos import verificar_familias
    from .evaluacion_temporal import familias_de

    refs = [a for a in referencias if modelos.get(a, {}).get('status') == 'EVALUADO']
    ref_global = min(refs, key=lambda a: modelos[a]['seleccion'][nombre]['media'])
    referencia = {}
    for h in horizontes:
        ref_h = min(refs, key=lambda a: modelos[a]['seleccion'][nombre][h])
        referencia[h] = {**modelos[ref_h]['prueba'][nombre][h],
                         **{k: modelos[ref_global]['prueba'][nombre][h][k] for k in
                            ('error_maxima', 'error_instante_min', 'por_dia_maxima', 'por_dia_instante')},
                         'referencia': ref_h}
    candidatos = [a for a, m in modelos.items() if a not in referencias and m.get('status') == 'EVALUADO']
    fila = {'referencia': ref_global, 'referencia_por_horizonte': {h: referencia[h]['referencia'] for h in horizontes},
            'candidato': None, 'fallos': [], 'familias': {}}
    if candidatos:
        candidato = min(candidatos, key=lambda a: modelos[a]['seleccion'][nombre]['media'])
        familias = familias_de(nombre, modelos[candidato]['prueba'][nombre], referencia, politica=politica)
        fallos = verificar_familias(familias, None, politica, esperadas=[f'{nombre}|h{h}' for h in horizontes])
        fila.update(candidato=candidato, fallos=fallos, familias=familias)
        if not fallos:
            return {**fila, 'ganador': candidato, 'es_referencia': False,
                    'motivo': f'{candidato} supera a la referencia en todas las puertas de cada horizonte'}
        motivo = f'gana la referencia {ref_global}: {candidato} no supera las puertas'
    else:
        motivo = f'gana la referencia {ref_global}: ningún modelo neuronal compitió'
    return {**fila, 'ganador': ref_global, 'es_referencia': True, 'motivo': motivo}


def _fallos_frente_al_activo(registro, nombre_registro, conjunto, ventanas, contexto, H, horizontes, politica,
                             ganadores, modelos, fabricas) -> list[str]:
    """046:RF-8: frente al activo se exige mejora en las mismas ventanas; se reabre y se mide en ellas."""
    import tempfile

    from .evaluacion_temporal import MARGEN_ACTIVO

    activo = registro.activo(nombre_registro)
    if activo is None:
        return []
    detalle = registro.detalle(nombre_registro, activo['candidate_id'])
    previos = detalle['model_manifest']['ganadores']
    fallos = []
    for nombre, g in ganadores.items():
        previo = previos.get(nombre)
        if previo is None or previo['es_referencia']:
            continue
        if g['es_referencia']:
            fallos.append(f'{nombre}: el modelo activo tiene un ganador neuronal y esta corrida no: se conserva el activo')
            continue
        algoritmo = previo['ganador']
        try:
            with tempfile.TemporaryDirectory() as d:
                modelo = _abrir_zip(Path(detalle['path']) / 'artifacts' / f'modelo_{algoritmo}.zip', algoritmo, fabricas, Path(d))
                unico = Conjunto1(conjunto, nombre)
                res, _f = _evaluar_modelo(unico, modelo, algoritmo, _ventanas_de(ventanas, nombre), contexto, H, horizontes, politica)
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            fallos.append(f'{nombre}: el modelo activo no reabre en estas ventanas: {exc}')
            continue
        # El activo se recalibra en estas mismas ventanas: se compara en igualdad con el candidato.
        for h in horizontes:
            nuevo = modelos[g['ganador']]['prueba'][nombre][h]['pinball']
            viejo = res['prueba'][nombre][h]['pinball']
            if not nuevo <= viejo * (1 - MARGEN_ACTIVO):
                fallos.append(f'{nombre}|h{h}: no mejora al modelo activo un {MARGEN_ACTIVO:.0%} de pinball')
    return fallos


class Conjunto1:
    """Vista de un solo objetivo de un conjunto: evaluar al activo no recorre los demás."""

    def __init__(self, conjunto, nombre: str):
        self._c, self._nombre = conjunto, nombre

    @property
    def nombres(self) -> list[str]:
        return [self._nombre]

    def __getattr__(self, atributo):
        return getattr(self._c, atributo)


def _ventanas_de(ventanas: dict, nombre: str) -> dict:
    return {'partes': {p: {nombre: filas[nombre]} for p, filas in ventanas['partes'].items()}}


def comparar_pronosticos(objetivos, destino: Path, *, clase: str, algoritmos, horizontes, cadencia_min: int,
                         zona_horaria: str, semillas, procedencia: dict, registro, contexto_pasos: int | None = None,
                         paso_emision_min: int = 60, fabricas: dict | None = None, reabrir=None,
                         ajustes_modelo: dict | None = None, apartados_previos=(), log=lambda _m: None) -> dict:
    """Compite cada modelo en las mismas ventanas y decide por objetivo (046:RF-5 a RF-8, RF-13 a RF-19).

    Las referencias siempre compiten y no piden GPU. Un modelo que no carga, o sin CUDA, queda
    ``ERROR_ENTORNO`` con su motivo y los demás siguen. Si ninguno neuronal pasa las puertas gana
    una referencia, se dice, y el modelo activo no cambia. Nada de aquí escribe en DIgSILENT ni
    pasa a la calibración: el resultado es un artefacto aparte con la marca ``pronostico``.
    """
    import math
    import uuid

    from ..model_registry import EstadoModelo
    from ..trabajadores_ml import escribir_informe, sha_archivo
    from .evaluacion_temporal import POLITICA_TEMPORAL, verificar_ventanas_identicas
    from .pronostico import (CLASES, REFERENCIAS, aplicar_ajuste, construir_conjunto, disponibilidad, fabrica,
                             filas_pronostico)
    from .series_causales import horizontes_validos

    politica = POLITICA_TEMPORAL
    fabricas = dict(fabricas or {})
    reabrir = reabrir or _reabrir_en_otro_proceso
    if clase not in CLASES:
        raise ValueError(f'clase desconocida: {clase}')
    otros = [o.nombre for o in objetivos if o.clase != clase]
    if otros:
        raise ValueError(f'objetivos de otra clase en una corrida de {clase}: cabecera y clientes se deciden por separado')
    horizontes = horizontes_validos(cadencia_min, horizontes)
    H = max(horizontes)
    conjunto = construir_conjunto(objetivos, cadencia_min=cadencia_min, zona_horaria=zona_horaria)
    apartados = list(apartados_previos) + conjunto.apartados
    if not conjunto.nombres:
        raise ValueError('ningún objetivo evaluable: ' + '; '.join(f"{a['objetivo']}: {a['motivo']}" for a in apartados))
    semana = 7 * 1440 // cadencia_min
    contexto = contexto_pasos or semana
    if contexto < semana:
        raise ValueError(f'la ventana común debe cubrir la semana del estacional: {semana} pasos')
    paso = paso_emision_min / cadencia_min
    if not paso.is_integer() or paso < 1:
        raise ValueError('el paso de emisión debe ser múltiplo de la cadencia')
    ventanas = conjunto.ventanas_comunes(politica, contexto_pasos=contexto, horizonte_max=H, paso=int(paso))
    for nombre in list(conjunto.nombres):
        vacia = [p for p, filas in ventanas['partes'].items() if not len(filas[nombre])]
        if vacia:
            apartados.append({'objetivo': nombre, 'motivo': f'sin ventanas completas en: {", ".join(vacia)}'})
            del conjunto.valores[nombre]
    if not conjunto.nombres:
        raise ValueError('ningún objetivo con ventanas completas: ' + '; '.join(a['objetivo'] for a in apartados))
    limites = ventanas['limites']
    fin_entrenamiento = limites['entrenamiento'][1]
    orden = list(REFERENCIAS) + [a for a in algoritmos if a not in REFERENCIAS]
    destino.mkdir(parents=True, exist_ok=True)
    carpeta = destino / ('candidato_' + uuid.uuid4().hex)
    carpeta.mkdir()
    modelos, ajustados, base_filas = {}, {}, {}
    for algoritmo in orden:
        try:
            if algoritmo not in fabricas:
                d = disponibilidad(algoritmo)
                if not d['disponible']:
                    modelos[algoritmo] = {'status': 'ERROR_ENTORNO', 'reason': d['motivo']}
                    log(f'{algoritmo}: no disponible: {d["motivo"]}')
                    continue
            crear = fabricas.get(algoritmo)
            mejor = None
            semillas_alg = semillas if algoritmo not in REFERENCIAS else semillas[:1]
            for semilla in semillas_alg:
                cfg = dict(ajustes_modelo or {})
                modelo = (crear(algoritmo, horizonte=H, cadencia_min=cadencia_min, semilla=semilla, **cfg) if crear
                          else fabrica(algoritmo, horizonte=H, cadencia_min=cadencia_min, semilla=semilla, **cfg))
                info = modelo.ajustar(conjunto, fin_entrenamiento, H, semilla)
                res, filas = _evaluar_modelo(conjunto, modelo, algoritmo, ventanas, contexto, H, horizontes, politica)
                media = float(np.mean([s['media'] for s in res['seleccion'].values()]))
                log(f'{algoritmo}, semilla {semilla}: pinball de selección {media:.4g}')
                if not math.isfinite(media):
                    raise RuntimeError(f'{algoritmo}: error de selección no finito')
                if mejor is None or media < mejor[0]:
                    mejor = (media, semilla, modelo, res, filas, info)
                else:
                    del modelo
            _m, semilla, modelo, res, filas, info = mejor
            if not base_filas:
                base_filas = filas
            for nombre in conjunto.nombres:
                verificar_ventanas_identicas({REFERENCIAS[0]: base_filas[nombre], algoritmo: filas[nombre]})
            modelos[algoritmo] = {**res, 'semilla': semilla, 'info': info, 'requiere_gpu': modelo.requiere_gpu}
            ajustados[algoritmo] = modelo
        except (ImportError, OSError, RuntimeError) as exc:
            # 046:RF-14 y RF-15: SinGPU es un RuntimeError; un OOM de CUDA, también.
            modelos[algoritmo] = {'status': 'ERROR_ENTORNO', 'reason': str(exc)}
            log(f'{algoritmo}: {exc}')
    ganadores = {n: _decidir_objetivo(n, horizontes, modelos, politica, REFERENCIAS) for n in conjunto.nombres}
    neuronales = [a for a in orden if a not in REFERENCIAS]
    evaluados = [a for a in neuronales if modelos.get(a, {}).get('status') == 'EVALUADO']

    # El artefacto: desde la última emisión posible, con el ganador de cada objetivo (046:RF-19).
    filas_artefacto, maximas = [], {}
    puntos_dia = min(H, 1440 // cadencia_min)
    for nombre, g in ganadores.items():
        e = conjunto.ultima_emision(nombre, contexto)
        lote = conjunto.lote([nombre], np.array([e]), contexto=contexto, horizonte=H)
        prediccion = aplicar_ajuste(ajustados[g['ganador']].predecir(lote), np.array(modelos[g['ganador']]['ajuste'][nombre]))
        filas_artefacto += filas_pronostico(conjunto, nombre, np.array([e]), prediccion, horizontes, g['ganador'])
        camino = prediccion[0, :puntos_dia, 1]
        k = int(camino.argmax())
        maximas[nombre] = {'valor': float(camino[k] + modelos[g['ganador']]['sesgo_maxima'][nombre]),
                           'horizon_steps': k + 1, 'algorithm': g['ganador'], 'unit': conjunto.objetivos[nombre].unidad,
                           'marca': 'pronostico'}
    artefacto = carpeta / 'pronostico.json'
    escribir_informe(artefacto, {
        'marca': 'pronostico', 'clase': clase, 'procedencia': procedencia, 'zona_horaria': zona_horaria,
        'cadencia_min': cadencia_min, 'aviso': 'Es un pronóstico: nunca sustituye a la medición en la calibración, '
        'en el «Caso base» ni en los informes.', 'politica_hash': politica.hash, 'filas': filas_artefacto,
        'maximas': maximas,
        'fuentes': {n: dict(conjunto.objetivos[n].fuente) for n in conjunto.nombres}})
    # Sin medición que comparar, los días de cada métrica no hacen falta en el registro.
    resumen = {a: ({**m, 'prueba': {o: {h: {k: v for k, v in f.items() if not k.startswith('por_dia')} for h, f in fila.items()}
                                     for o, fila in m['prueba'].items()}} if m.get('status') == 'EVALUADO' else m)
               for a, m in modelos.items()}
    gates = {'approved': False, 'fallos': [], 'politica_hash': politica.hash}
    decision = {'status': EstadoModelo.RECHAZADO.value, 'gates': gates}
    ganan_neuronales = [n for n, g in ganadores.items() if not g['es_referencia']]
    candidate_id = None
    modelo_registro = f'pronostico_{clase}'
    promovido = False
    if not ganan_neuronales:
        gates['fallos'].append('ningún modelo neuronal supera las puertas: el modelo activo sigue')
    if evaluados:
        # Registrar también al rechazado conserva su evidencia (046:RF-7).
        (carpeta / 'ajustes.json').write_text(json.dumps({a: {'intervalo': modelos[a]['ajuste'], 'sesgo_maxima': modelos[a]['sesgo_maxima']}
                                                            for a in orden if a in ajustados}), encoding='utf-8')
        artefactos = [artefacto, carpeta / 'ajustes.json']
        for a in evaluados:
            artefactos.append(_empaquetar(ajustados[a], carpeta, a))
        nombre0 = conjunto.nombres[0]
        em = ventanas['partes']['prueba'][nombre0][:4]
        sonda = conjunto.lote([nombre0] * len(em), em, contexto=contexto, horizonte=H)
        _guardar_sonda(carpeta / 'sonda.npz', sonda, {a: ajustados[a].predecir(sonda) for a in evaluados})
        artefactos.append(carpeta / 'sonda.npz')
        smoke = reabrir(carpeta)
        if smoke.get('ok') is not True:
            gates['fallos'].append(f"reapertura fallida: {smoke.get('error') or smoke.get('stderr') or 'sin detalle'}")
        gates['fallos'] += _fallos_frente_al_activo(registro, modelo_registro, conjunto, ventanas, contexto, H, horizontes,
                                                    politica, ganadores, modelos, fabricas)
        gates['approved'] = bool(ganan_neuronales) and not gates['fallos']
        decision['status'] = (EstadoModelo.PROMOVIDO if gates['approved'] else EstadoModelo.RECHAZADO).value
        limpios = {n: {k: v for k, v in g.items() if k != 'familias'} for n, g in ganadores.items()}
        hecho = registro.registrar_candidato(
            modelo_registro,
            model_manifest={'clase': clase, 'ganadores': limpios, 'horizontes': list(horizontes), 'contexto_pasos': contexto,
                            # 043:RF-8: lo que la web dice que ganó, dentro de la etapa ``gru``.
                            'algorithm': ','.join(sorted({g['ganador'] for g in limpios.values() if not g['es_referencia']})) or None,
                            'semillas': {a: modelos[a]['semilla'] for a in evaluados}, 'cadencia_min': cadencia_min,
                            'ajustes': dict(ajustes_modelo or {})},
            dataset_manifest={'procedencia': procedencia, 'ventanas_huella': ventanas['huella'], 'politica_hash': politica.hash,
                              'zona_horaria': zona_horaria, 'cadencia_min': cadencia_min, 'objetivos': conjunto.nombres,
                              'apartados': apartados, 'dias': {p: len(d) for p, d in ventanas['dias'].items()},
                              'limites': {p: list(v) for p, v in limites.items()},
                              'artefacto_sha256': sha_archivo(artefacto)},
            metrics={a: m.get('prueba') for a, m in resumen.items() if m.get('status') == 'EVALUADO'},
            decision=decision, smoke_reload=smoke, artifacts=artefactos)
        candidate_id = hecho['candidate_id']
        if gates['approved']:
            registro.promover(modelo_registro, candidate_id)
            promovido = True
    elif neuronales:
        decision['status'] = EstadoModelo.ERROR_ENTORNO.value
    status = decision['status']
    motivos = '; '.join(f"{a}: {modelos[a]['reason']}" for a in neuronales if modelos[a].get('status') == 'ERROR_ENTORNO')
    return {'status': status, 'reason': motivos or '; '.join(gates['fallos']), 'marca': 'pronostico', 'clase': clase,
            'training_completed': bool(evaluados), 'entrenado': bool(evaluados), 'evaluation_completed': True,
            'promovido': promovido, 'gates': gates, 'politica_hash': politica.hash, 'ganadores': ganadores,
            'modelos': resumen, 'horizontes': list(horizontes), 'apartados': apartados,
            'ventanas': {'huella': ventanas['huella'],
                         'n': {p: {n: len(ventanas['partes'][p][n]) for n in conjunto.nombres} for p in ventanas['partes']}},
            'particiones': {'limites': {p: list(v) for p, v in limites.items()},
                            'dias': {p: len(d) for p, d in ventanas['dias'].items()}},
            'artefacto': str(artefacto.resolve()), 'candidate_id': candidate_id, 'modelo_registro': modelo_registro}
