"""047 T5 — destilación de respuestas con selección independiente y custodia común."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import random
import sys
import time
import platform

from ..evaluacion_modelos import (PARTES, PoliticaEvaluacion, huella, particionar_registros,
                                  texto_canonico, verificar_familias)
from .curriculo_maestro import FAMILIAS, MAESTRO
from .sinteticos import Ejemplo, expandir
from .tareas import TAREAS


def preparar_corpus(vocab: dict, reales: list[dict], *, por_familia: int = 40) -> tuple[list[dict], dict]:
    """Expande familias declaradas; todos los ejemplos humanos quedan fuera del ajuste."""
    if type(por_familia) is not int or por_familia < 1 or set(FAMILIAS) != set(TAREAS):
        raise ValueError('currículo incompleto o tamaño inválido')
    filas, vistos, cuarentena = [], {}, set()
    humanos = {texto_canonico(str(r.get('texto') or '')) for r in reales}

    def agregar(e, grupo, parte, calidad, maestro=False):
        clave = texto_canonico(e.texto)
        if clave in humanos and calidad != 'gold_human':
            return
        if clave in vistos:
            firma = (e.tarea, sorted((tipo, texto_canonico(e.texto[a:b])) for a, b, tipo in e.datos))
            if vistos[clave][1] != firma:
                if calidad == 'gold_human':
                    raise ValueError('etiquetas humanas contradictorias para el mismo texto')
                # El generador tiene variantes literales «todos» sin span y otras
                # con span. No elegir en silencio una anotación arbitraria.
                cuarentena.add(clave)
                return
            if vistos[clave][0] != parte:
                raise ValueError('solapamiento de familias de currículo; revisar antes de entrenar')
            return
        vistos[clave] = (parte, (e.tarea, sorted((tipo, texto_canonico(e.texto[a:b]))
                                               for a, b, tipo in e.datos)))
        r = {'texto': e.texto, 'tarea': e.tarea, 'datos': [list(d) for d in e.datos],
             'group_id': grupo, 'particion': parte, 'quality': calidad, 'del_maestro': maestro}
        if maestro:
            r['justificacion_verificable'] = TAREAS[e.tarea].descripcion
        r['record_id'] = huella(r)
        filas.append(r)

    for tarea in sorted(TAREAS):
        # Baseline y alumno comparten exactamente este entrenamiento supervisado.
        for j, plantilla in enumerate(TAREAS[tarea].plantillas):
            rnd = random.Random(1701 + j + int(huella(tarea)[:8], 16))
            grupo = huella({'plantilla': plantilla, 'tarea': tarea})
            for _ in range(por_familia):
                agregar(expandir(plantilla, tarea, rnd, vocab, ruido=.08), grupo,
                        'entrenamiento', 'silver_deterministic')
        from .ordenes_fijas import FRASES
        for j, plantilla in enumerate(FRASES[tarea]):
            rnd = random.Random(3103 + j + int(huella(tarea)[:8], 16))
            grupo = huella({'plantilla': plantilla, 'tarea': tarea})
            for _ in range(por_familia):
                agregar(expandir(plantilla, tarea, rnd, vocab, ruido=.06), grupo,
                        'entrenamiento', 'silver_teacher_verified', maestro=True)
        for j, (parte, plantilla) in enumerate(zip(PARTES, FAMILIAS[tarea], strict=True)):
            rnd = random.Random(991 + j + int(huella(tarea)[:8], 16))
            grupo = huella({'plantilla': plantilla, 'tarea': tarea})
            for _ in range(por_familia):
                agregar(expandir(plantilla, tarea, rnd, vocab, ruido=.06), grupo,
                        parte, 'silver_teacher_verified', maestro=True)
    for r in reales:
        if r.get('tarea') not in TAREAS or not str(r.get('texto') or '').strip():
            continue
        # Solo el almacén local de confirmaciones/correcciones se acepta como origen humano.
        if r.get('origen') not in {'confirmado', 'corregido'}:
            continue
        e = Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r.get('datos') or []])
        agregar(e, huella({'humana': texto_canonico(e.texto)}), 'prueba', 'gold_human')
    filas = sorted((r for r in filas if texto_canonico(r['texto']) not in cuarentena),
                   key=lambda r: r['record_id'])
    meta = {'schema_version': 1, 'maestro': MAESTRO, 'dataset_hash': huella(filas),
            'curriculo_hash': huella({'sesion': FAMILIAS, 'catalogo_revisado': FRASES}),
            'calidades': dict(Counter(r['quality'] for r in filas)),
            'particiones': dict(Counter(r['particion'] for r in filas)),
            'vocabulario_hash': huella(vocab), 'por_familia': por_familia,
            'eventos_humanos_leidos': len(reales),
            'cuarentena_sintetica_conflictos': len(cuarentena),
            'cuarentena_hash': huella(sorted(cuarentena)),
            'ordenes_humanas_independientes': sum(r['quality'] == 'gold_human' for r in filas),
            'metodo': 'response_distillation; CE de tareas y entidades; no logits ni racionales privados'}
    particionar_registros(filas, PoliticaEvaluacion(modo='agente'))
    return filas, meta


def guardar_corpus(destino: Path, registros: list[dict], manifiesto: dict) -> None:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, datos in (('corpus.json', registros), ('dataset_manifest.json', manifiesto)):
        ruta = destino / nombre
        contenido = json.dumps(datos, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        if ruta.exists() and ruta.read_text(encoding='utf-8') != contenido:
            raise ValueError('se conserva el corpus existente; use otro destino para otra revisión')
        ruta.write_text(contenido, encoding='utf-8')


def leer_corpus(destino: Path) -> tuple[list[dict], dict]:
    filas = json.loads((Path(destino) / 'corpus.json').read_text(encoding='utf-8'))
    meta = json.loads((Path(destino) / 'dataset_manifest.json').read_text(encoding='utf-8'))
    if meta.get('schema_version') != 1 or huella(filas) != meta.get('dataset_hash'):
        raise ValueError('integridad de corpus o manifiesto inválida')
    for r in filas:
        identidad = r.get('record_id')
        if identidad != huella({k: v for k, v in r.items() if k != 'record_id'}):
            raise ValueError('integridad de registro inválida')
        if r.get('tarea') not in TAREAS or r.get('quality') not in {
                'gold_human', 'silver_deterministic', 'silver_teacher_verified'}:
            raise ValueError('etiqueta o calidad no admitida')
        texto = r['texto']
        for a, b, tipo in r.get('datos') or []:
            from .tareas import TIPOS_DATO
            if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(texto) or tipo not in TIPOS_DATO:
                raise ValueError('span de entidad inválido')
    return filas, meta


def elegir_candidato(candidatos: list[dict]) -> dict:
    if not candidatos:
        raise ValueError('sin candidatos evaluados en selección')
    for r in candidatos:
        if any(type(r['seleccion'].get(k)) not in (float, int) or
               not math.isfinite(r['seleccion'][k]) for k in ('macro_tarea', 'f1_datos')):
            raise ValueError('métrica de selección inválida')
    # Empate: conservar el método supervisado de menor complejidad de datos.
    return max(candidatos, key=lambda r: (r['seleccion']['macro_tarea'], r['seleccion']['f1_datos'],
                                          r['metodo'] == 'supervisado', -r['semilla']))


def decidir_promocion(sinteticas: dict, humanas: dict, familias: dict, referencia: dict | None) -> dict:
    politica = PoliticaEvaluacion(modo='agente')
    fallos = verificar_familias(familias, referencia, politica, esperadas=tuple(TAREAS))
    for k, minimo in politica.puertas_por_familia:
        valor = sinteticas.get(k)
        if type(valor) not in (float, int) or not math.isfinite(valor) or valor < minimo:
            fallos.append(f'prueba sintética: {k} bajo puerta o inválido')
    n = humanas.get('ejemplos', 0)
    if type(n) is not int or n < 1:
        return {'status': 'BLOQUEADO_POR_DATOS', 'gates': {'approved': False},
                'ordenes_humanas': n, 'alcance': 'asistido', 'confirmacion_obligatoria': True,
                'fallos': ['sin evaluación humana disponible', *fallos]}
    for k, minimo in (('acierto_tarea', .98), ('f1_datos', .95)):
        valor = humanas.get(k)
        if type(valor) not in (float, int) or not math.isfinite(valor) or valor < minimo:
            fallos.append(f'prueba humana: {k} bajo puerta o inválido')
    # La comparación con el modelo activo es obligatoria antes de habilitar promoción.
    if referencia is None:
        fallos.append('falta comparación por familia con el modelo activo')
    return {'status': 'RECHAZADO' if fallos else 'PROMOVIDO',
            'gates': {'approved': not fallos}, 'fallos': fallos, 'ordenes_humanas': n,
            'alcance': 'asistido', 'confirmacion_obligatoria': True,
            'muestra_humana_amplia': n >= 200}


def _ejemplos(registros):
    return [Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r['datos']]) for r in registros]


def evaluar_alumno(modelo, registros: list[dict]) -> dict:
    from .transformer import evaluar
    por_tarea = defaultdict(list)
    for r in registros:
        por_tarea[r['tarea']].append(r)
    familias = {t: evaluar(modelo, _ejemplos(rs)) for t, rs in sorted(por_tarea.items())}
    m = evaluar(modelo, _ejemplos(registros))
    return {**m, 'macro_tarea': sum(v['acierto_tarea'] for v in familias.values()) / max(1, len(familias)),
            'familias': familias}


def _guardar_alumno(modelo, carpeta: Path, meta: dict):
    from . import transformer as tr
    carpeta.mkdir(parents=True, exist_ok=False)
    tr._torch().save({k: v.detach().cpu() for k, v in modelo.red.state_dict().items()}, carpeta / 'pesos.pt')
    datos = {**meta, 'cfg': asdict(modelo.cfg), 'simbolos': modelo.simbolos,
             'tareas': modelo.tareas, 'etiquetas': list(tr.ETIQUETAS),
             'temperatura': modelo.temperatura}
    (carpeta / 'modelo.json').write_text(json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def cargar_alumno(carpeta: Path):
    from . import transformer as tr
    meta = json.loads((Path(carpeta) / 'modelo.json').read_text(encoding='utf-8'))
    if meta.get('etiquetas') != list(tr.ETIQUETAS) or meta.get('tareas') != sorted(TAREAS):
        raise ValueError('contrato de tareas o entidades incompatible')
    cfg = tr.Configuracion(**meta['cfg'])
    red = tr.construir_red(len(meta['simbolos']) + 3, {'tarea': len(meta['tareas'])}, cfg, len(tr.ETIQUETAS))
    red.load_state_dict(tr._torch().load(Path(carpeta) / 'pesos.pt', weights_only=True, map_location='cpu'))
    red.to(tr._dispositivo()).eval()
    temperatura = meta.get('temperatura', 1.)
    if type(temperatura) not in (int, float) or not math.isfinite(temperatura) or temperatura <= 0:
        raise ValueError('temperatura de calibración inválida')
    return tr.ModeloOrdenes(red, meta['simbolos'], meta['tareas'], cfg,
                           version=meta.get('version', 'candidato'), temperatura=temperatura)


def calibrar_temperatura(modelo, registros: list[dict]) -> dict:
    """Ajusta una sola temperatura usando únicamente la partición de calibración."""
    from . import transformer as tr
    torch = tr._torch()
    if not registros or any(r['particion'] != 'calibracion' for r in registros):
        raise ValueError('calibración independiente obligatoria')
    disp = next(modelo.red.parameters()).device
    zs, ys = [], []
    modelo.red.eval()
    with torch.no_grad():
        for inicio in range(0, len(registros), 64):
            filas = registros[inicio:inicio + 64]
            x = tr.rellenar(tr.codificar([r['texto'] for r in filas], modelo.simbolos)).to(disp)
            clases, _ = modelo.red(x)
            zs.append(clases['tarea']); ys.extend(modelo.tareas.index(r['tarea']) for r in filas)
        z, y = torch.cat(zs), torch.tensor(ys, device=disp)
        perdida = {t: float(torch.nn.functional.cross_entropy(z / t, y)) for t in (.5, .75, 1., 1.5, 2., 3., 5.)}
    modelo.temperatura = min(perdida, key=perdida.get)
    return {'temperatura': modelo.temperatura, 'nll_por_temperatura': perdida, 'ejemplos': len(ys),
            'record_ids_hash': huella(sorted(r['record_id'] for r in registros)),
            'garantia_de_cobertura': False}


def ensayar_funcionamiento(modelo, *, ollama=None) -> dict:
    """Usa intérprete y plan reales, sin ejecutar maniobras o escribir en PowerFactory."""
    from .interprete import Interpretacion, interpretar
    from .plan import resolver
    vocab = {'alimentadores': ['AB101', 'CD202'], 'proyecto': ['Proyecto demostracion'], 'sistema': ['Sistema prueba']}
    positivos = [('muestrame lo que hay', 'estado'), ('convierte AB101 a dgs', 'convertir'),
                 ('une AB101 y CD202 en un solo dgs', 'unir')]
    resultados = []
    for texto, esperado in positivos:
        i = interpretar(texto, transformer=modelo, ollama=ollama)
        p = resolver(i, vocab)
        resultados.append({'texto': texto, 'esperado': esperado, 'tarea': p.tarea,
                           'correcto': p.tarea == esperado, 'plan': p.publico()})
    # Entrada adversa estructurada: comprueba la barrera del plan, sin fingir una
    # evaluación estadística de rechazo OOD del alumno.
    negativo = resolver(Interpretacion('convierte ZZ999', 'convertir', 1., 'ensayo',
                        {'alimentadores': [{'valor': 'ZZ999'}]}), vocab)
    consulta = resolver(Interpretacion('estado', 'estado', 1., 'ensayo', {}), vocab)
    escritura = resolver(Interpretacion('convierte AB101', 'convertir', 1., 'ensayo',
                        {'alimentadores': [{'valor': 'AB101'}]}), vocab)
    barreras = {'entidad_ajena_bloqueada': not negativo.listo,
                'consulta_no_escribe': not consulta.escribe,
                'escritura_pide_confirmacion': escritura.escribe and
                    any('confirmación' in r for r in escritura.razonamiento)}
    return {'ok': all(r['correcto'] for r in resultados) and all(barreras.values()),
            'positivos': resultados, 'barreras': barreras, 'escrituras_nativas': 0,
            'modo': 'agente_hibrido' if ollama is not None else 'alumno_solo',
            'rechazo_ood_estadistico_validado': False}


def casos_funcionales(registros: list[dict], *, por_tarea: int = 1) -> list[dict]:
    """Una muestra fija por tarea de prueba, más todas las humanas únicas reservadas."""
    if type(por_tarea) is not int or por_tarea < 1:
        raise ValueError('cantidad positiva por tarea obligatoria')
    casos, cuenta = [], Counter()
    for r in sorted(registros, key=lambda r: r['record_id']):
        if r['particion'] != 'prueba':
            continue
        if r['quality'] == 'gold_human':
            casos.append(r)
        elif cuenta[r['tarea']] < por_tarea:
            casos.append(r)
            cuenta[r['tarea']] += 1
    if set(cuenta) != set(TAREAS):
        raise ValueError('BLOQUEADO_POR_DATOS: faltan tareas en la prueba funcional')
    return casos


def evaluar_agente(modelo, registros: list[dict], *, ollama=None, por_tarea: int = 1) -> dict:
    """Diagnóstico de intérprete/plan con contextos sintéticos; no ejecuta sus acciones."""
    from .interprete import interpretar
    from .plan import resolver, _trozos_lista
    resultados = []
    for r in casos_funcionales(registros, por_tarea=por_tarea):
        vocab = defaultdict(list)
        # El contexto viene de la fixture de evaluación, no de la predicción LLM.
        for a, b, tipo in r['datos']:
            valor = r['texto'][a:b]
            if tipo == 'alimentadores':
                vocab[tipo].extend(_trozos_lista(valor))
            else:
                vocab[tipo].append(valor)
        i = interpretar(r['texto'], transformer=modelo, ollama=ollama)
        p = resolver(i, vocab)
        resultados.append({'record_id': r['record_id'], 'quality': r['quality'],
            'esperado': r['tarea'], 'tarea': p.tarea, 'correcto': p.tarea == r['tarea'],
            'abstuvo': p.tarea is None, 'interprete': p.interpretado_por,
            'consulta_ollama': any(c.startswith('Ollama') for c in i.consultados),
            'listo': p.listo, 'escribe': p.escribe,
            'confirmacion_exigida': not p.escribe or any('confirmación' in x for x in p.razonamiento),
            'faltan': p.faltan})
    sinteticos = [r for r in resultados if r['quality'] != 'gold_human']
    humanos = [r for r in resultados if r['quality'] == 'gold_human']
    def resumen(filas):
        return {'ejemplos': len(filas), 'acierto_tarea': sum(r['correcto'] for r in filas) / max(1, len(filas)),
                'abstenciones': sum(r['abstuvo'] for r in filas),
                'consultas_ollama': sum(r['consulta_ollama'] for r in filas)}
    return {'schema_version': 1, 'sinteticos': resumen(sinteticos), 'humanos': resumen(humanos),
            'cobertura_tareas': len({r['esperado'] for r in resultados}),
            'record_ids_hash': huella([r['record_id'] for r in resultados]), 'casos': resultados,
            'escrituras_nativas': 0, 'confirmaciones_conservadas': all(r['confirmacion_exigida'] for r in resultados),
            'contextos': 'fixtures sinteticas; no vinculos nativos reales',
            'otra_prueba_independiente': False}


def entrenar_destilacion(dataset: Path, destino: Path, *, cfg=None, semillas=(11, 23, 37),
                         registro: Path | None = None, log=print) -> dict:
    from . import transformer as tr
    from ..model_registry import RegistroModelo, reabrir_en_subproceso
    filas, meta = leer_corpus(dataset)
    politica = PoliticaEvaluacion(modo='agente', semillas=tuple(semillas))
    particiones = particionar_registros(filas, politica)
    destino = Path(destino)
    if destino.exists() and any(destino.iterdir()):
        raise ValueError('se conserva una ejecución existente; use otro destino')
    destino.mkdir(parents=True, exist_ok=True)
    cfg = cfg or tr.Configuracion()
    por_parte = {p: [r for r in filas if r['particion'] == p] for p in PARTES}
    base = [r for r in por_parte['entrenamiento'] if not r['del_maestro']]
    maestro = [r for r in por_parte['entrenamiento'] if r['del_maestro']]
    if not base or not maestro:
        raise ValueError('comparación requiere supervisados y respuestas del maestro')
    protocolo = {'policy': asdict(politica), 'policy_hash': politica.hash,
                 'particiones': asdict(particiones), 'dataset': meta, 'cfg': asdict(cfg),
                 'semillas': list(semillas), 'metodos': ['supervisado', 'destilado'],
                 'codigo_hashes': {p.name: huella(p.read_text(encoding='utf-8')) for p in
                     (Path(__file__), Path(tr.__file__), Path(__file__).with_name('curriculo_maestro.py'))},
                 'entorno': {'python': platform.python_version(), 'torch': tr._torch().__version__,
                             'cuda': tr._torch().version.cuda, 'gpu': tr._torch().cuda.get_device_name(0)}}
    codigo = destino / 'codigo'
    codigo.mkdir()
    for archivo in (Path(__file__), Path(tr.__file__), Path(__file__).with_name('curriculo_maestro.py'),
                    Path(__file__).with_name('ordenes_fijas.py'), Path(__file__).parents[1] / 'evaluacion_modelos.py'):
        (codigo / archivo.name).write_text(archivo.read_text(encoding='utf-8'), encoding='utf-8')
    (destino / 'protocolo.json').write_text(json.dumps(protocolo, ensure_ascii=False, indent=2), encoding='utf-8')
    candidatos = []
    inicio = time.monotonic()
    for semilla in semillas:
        for metodo in ('supervisado', 'destilado'):
            log(f'{metodo}, semilla {semilla}: ajuste CUDA; prueba sellada', flush=True)
            datos = base if metodo == 'supervisado' else [*base, *maestro]
            modelo = tr.entrenar(_ejemplos(datos), replace(cfg, semilla=semilla),
                                 log=lambda m: log(m, flush=True))
            seleccion = evaluar_alumno(modelo, por_parte['seleccion'])
            carpeta = destino / f'{metodo}-{semilla}'
            _guardar_alumno(modelo, carpeta, {'version': carpeta.name, 'metodo': metodo,
                'policy_hash': politica.hash, 'dataset_hash': meta['dataset_hash']})
            candidatos.append({'semilla': semilla, 'metodo': metodo, 'path': str(carpeta.resolve()),
                               'seleccion': seleccion})
            (destino / 'seleccion.json').write_text(json.dumps(candidatos, ensure_ascii=False, indent=2), encoding='utf-8')
            del modelo
            tr._torch().cuda.empty_cache()
    elegido = elegir_candidato(candidatos)
    # El ganador queda registrado antes de leer calibración o prueba.
    (destino / 'ganador_seleccion.json').write_text(json.dumps(elegido, ensure_ascii=False, indent=2), encoding='utf-8')
    modelo = cargar_alumno(Path(elegido['path']))
    calibracion = calibrar_temperatura(modelo, por_parte['calibracion'])
    final = destino / 'alumno'
    _guardar_alumno(modelo, final, {'version': final.name, 'seleccion': elegido,
        'calibracion': calibracion, 'dataset_hash': meta['dataset_hash'], 'policy_hash': politica.hash})
    sinteticas = evaluar_alumno(modelo, [r for r in por_parte['prueba'] if r['quality'] != 'gold_human'])
    humanas = evaluar_alumno(modelo, [r for r in por_parte['prueba'] if r['quality'] == 'gold_human'])
    decision = decidir_promocion(sinteticas, humanas, sinteticas['familias'], None)
    funcionamiento = ensayar_funcionamiento(modelo)
    if not funcionamiento['ok']:
        decision['gates']['approved'] = False
        decision['fallos'].append('el ensayo de funcionamiento no pasó completo')
        if decision['status'] == 'PROMOVIDO':
            decision['status'] = 'RECHAZADO'
    textos = [r['texto'] for r in por_parte['seleccion'][:3]]
    esperado = [modelo.predecir(t) for t in textos]
    (final / 'readback.json').write_text(json.dumps({'textos': textos, 'predicciones': esperado}, ensure_ascii=False), encoding='utf-8')
    del modelo
    tr._torch().cuda.empty_cache()
    herramienta = Path(__file__).resolve().parents[3] / 'tools/asistente_destilar.py'
    smoke = reabrir_en_subproceso([sys.executable, str(herramienta), 'verificar', '--modelo', str(final.resolve())])
    if not smoke['ok']:
        decision = {'status': 'ERROR_ENTORNO', 'gates': {'approved': False}, 'fallos': ['falló reapertura en proceso nuevo']}
    reg = RegistroModelo(registro or destino / 'model_registry')
    candidato = reg.registrar_candidato('transformer', model_manifest={
        'metodo': elegido['metodo'], 'maestro': MAESTRO, 'cfg_base': asdict(cfg),
        'cfg_elegida': json.loads((final / 'modelo.json').read_text(encoding='utf-8'))['cfg'],
        'policy_hash': politica.hash, 'training_completed': True, 'semillas': list(semillas)},
        dataset_manifest=protocolo, metrics={'sinteticas': sinteticas, 'humanas': humanas,
        'seleccion': candidatos, 'calibracion': calibracion, 'funcionamiento': funcionamiento},
        decision=decision, smoke_reload=smoke, artifacts=[final / n for n in ('pesos.pt', 'modelo.json', 'readback.json')])
    # La activación es una operación explícita del registro, no un efecto del ensayo.
    reporte = {'schema_version': 1, 'training_completed': True, 'entrenado': True,
        'status': decision['status'], 'promovido': False, 'decision': decision,
        'elegido': elegido, 'candidato': candidato, 'sinteticas': sinteticas, 'humanas': humanas,
        'smoke_reload': smoke, 'funcionamiento': funcionamiento,
        'calibracion': calibracion, 'duracion_s': time.monotonic() - inicio}
    (destino / 'decision.json').write_text(json.dumps(reporte, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return reporte


def verificar_reapertura(carpeta: Path) -> dict:
    prueba = json.loads((Path(carpeta) / 'readback.json').read_text(encoding='utf-8'))
    if (not isinstance(prueba, dict) or not isinstance(prueba.get('textos'), list)
            or not isinstance(prueba.get('predicciones'), list) or not prueba['textos']
            or len(prueba['textos']) != len(prueba['predicciones'])):
        raise ValueError('predicciones de reapertura ausentes o incompatibles')
    modelo = cargar_alumno(carpeta)
    obtenidas = [modelo.predecir(t) for t in prueba['textos']]
    iguales = len(obtenidas) == len(prueba['predicciones']) and all(
        a['tarea'] == b['tarea'] and a['datos'] == b['datos'] and
        abs(a['confianza'] - b['confianza']) < 1e-6
        for a, b in zip(obtenidas, prueba['predicciones'], strict=True))
    return {'ok': iguales, 'dispositivo': str(next(modelo.red.parameters()).device),
            'ejemplos': len(obtenidas), 'proceso_nuevo': True}
