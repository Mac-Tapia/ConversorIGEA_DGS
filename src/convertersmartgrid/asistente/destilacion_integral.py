"""047 T5 — destilación de respuestas con selección independiente y custodia común."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
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
from .curriculo_maestro import ESTILO_REAL, FAMILIAS, MAESTRO, MAESTRO_ESTILO_REAL
from .maestro_real import CALIDAD, CONFIANZA_MINIMA, clave_texto, con_erratas, firma_familia
from .ordenes_fijas import generar as generar_fijas, repartir
from .sinteticos import Ejemplo, expandir
from .tareas import TAREAS

#: Variantes con erratas de cada texto real etiquetado (068:RF-38).
VARIANTES_POR_TEXTO_REAL = 8


def _ampliar_entrenamiento(filas: list[dict], vocab: dict, etiquetas: Sequence[dict], por_familia: int,
                           cuarentena: set[str], humanos: set[str]) -> dict:
    """068:RF-25 a RF-27: añade lo nuevo solo al ajuste, después de sellar lo demás.

    Va en una pasada aparte porque en la primera un texto en conflicto manda la fila de prueba a
    cuarentena: la prueba cambiaría en silencio y dejaría de ser comparable con el candidato anterior.
    """
    apartadas = [r for r in filas if r['particion'] != 'entrenamiento']
    vedados = {clave_texto(t) for t in (*humanos, *cuarentena)} | {clave_texto(r['texto']) for r in apartadas}
    vedados |= {clave_texto(e.texto) for e in repartir(generar_fijas(vocab))[1]}   # 027:RF-66
    familias = {firma_familia(r['texto'], r['datos']) for r in apartadas}
    vistos = {texto_canonico(r['texto']) for r in filas}
    cuenta = Counter()

    def agregar(e: Ejemplo, grupo: str, calidad: str, tipo: str, *, aumentado: bool = False, **extra) -> str:
        if clave_texto(e.texto) in vedados or firma_familia(e.texto, e.datos) in familias:
            cuenta[f'{tipo}_fuga'] += 1
            return 'fuga'
        clave = texto_canonico(e.texto)
        if clave in vistos:
            cuenta[f'{tipo}_repetidas'] += 1
            return 'repetida'
        vistos.add(clave)
        r = {'texto': e.texto, 'tarea': e.tarea, 'datos': [list(d) for d in sorted(e.datos)], 'group_id': grupo,
             'particion': 'entrenamiento', 'quality': calidad, 'del_maestro': True,
             'justificacion_verificable': TAREAS[e.tarea].descripcion, 'origen_curriculo': tipo, **extra}
        if aumentado:
            r['aumentado'] = 'erratas'
        r['record_id'] = huella(r)
        filas.append(r)
        cuenta[f'{tipo}_filas'] += 1
        return 'nueva'

    def erratas(e: Ejemplo, grupo: str, calidad: str, tipo: str, rnd: random.Random, n: int = 1, **extra) -> None:
        for _ in range(n):
            agregar(con_erratas(e, rnd), grupo, calidad, tipo, aumentado=True, **extra)

    def semilla_de(texto: str) -> random.Random:
        # Sale del texto: añadir una etiqueta no cambia las variantes de las demás.
        return random.Random(int(huella({'erratas': texto})[:8], 16))

    for r in sorted((r for r in filas if r['particion'] == 'entrenamiento'), key=lambda r: r['record_id']):
        erratas(Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r['datos']]), r['group_id'], r['quality'], 'catalogo',
                semilla_de(r['texto']))
    for tarea in sorted(TAREAS):
        for j, plantilla in enumerate(ESTILO_REAL[tarea]):
            rnd = random.Random(4231 + j + int(huella(tarea)[:8], 16))
            grupo = huella({'estilo_real': plantilla, 'tarea': tarea})
            for _ in range(max(1, por_familia // 2)):
                e = expandir(plantilla, tarea, rnd, vocab, ruido=.08)
                # Una frase sin datos se repite enseguida («como vamos») y su tarea se quedaría con
                # pocas filas frente a las que llevan códigos: las erratas se añaden igual.
                if agregar(e, grupo, 'silver_teacher_verified', 'estilo_real', maestro='claude') != 'fuga':
                    erratas(e, grupo, 'silver_teacher_verified', 'estilo_real', rnd, maestro='claude')
    por_tarea, leidas = Counter(), 0
    for f in sorted(etiquetas, key=lambda x: clave_texto(x['texto'])):
        leidas += 1
        if f.get('tarea') not in TAREAS or float(f.get('confianza', 0)) < CONFIANZA_MINIMA:
            cuenta['texto_real_apartadas'] += 1
            continue
        e = Ejemplo(f['texto'], f['tarea'], [tuple(d) for d in f.get('spans') or ()])
        grupo = huella({'texto_real': clave_texto(e.texto)})
        extra = {'maestro': str(f.get('maestro') or 'claude')}
        resultado = agregar(e, grupo, CALIDAD, 'texto_real', **extra)
        por_tarea[e.tarea] += resultado == 'nueva'
        if resultado != 'fuga':
            # Son pocas frente a las sintéticas: sus variantes les dan peso sin duplicar el texto.
            erratas(e, grupo, CALIDAD, 'texto_real', semilla_de(e.texto), VARIANTES_POR_TEXTO_REAL, **extra)
    return {'etiquetas_reales': {'leidas': leidas, 'usadas': sum(por_tarea.values()), 'filas': cuenta['texto_real_filas'],
                                 'excluidas_por_fuga': cuenta['texto_real_fuga'], 'repetidas': cuenta['texto_real_repetidas'],
                                 'apartadas': cuenta['texto_real_apartadas'], 'por_tarea': dict(sorted((t, n) for t, n in por_tarea.items() if n))},
            'estilo_real': {'frases': sum(len(v) for v in ESTILO_REAL.values()), 'filas': cuenta['estilo_real_filas'],
                            'excluidas_por_fuga': cuenta['estilo_real_fuga'], 'maestro': MAESTRO_ESTILO_REAL},
            'erratas_del_catalogo': {'filas': cuenta['catalogo_filas'], 'excluidas_por_fuga': cuenta['catalogo_fuga']}}


def preparar_corpus(vocab: dict, reales: list[dict], *, por_familia: int = 40, etiquetas_reales: Sequence[dict] = (),
                    ampliar: bool = True) -> tuple[list[dict], dict]:
    """Expande familias declaradas; todos los ejemplos humanos quedan fuera del ajuste.

    ``etiquetas_reales`` (068) son plata del maestro sobre textos del operador; nunca cuentan como humanas.
    Con ``ampliar=False`` da el corpus sellado de antes de la 068, para compararlo con lo que se añade.
    """
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
    ampliacion = (_ampliar_entrenamiento(filas, vocab, etiquetas_reales, por_familia, cuarentena, humanos)
                  if ampliar else {})
    filas.sort(key=lambda r: r['record_id'])
    denominadores = defaultdict(Counter)
    for r in filas:
        denominadores[r['particion']][r['quality']] += 1
    meta = {'schema_version': 1, 'maestro': MAESTRO, 'dataset_hash': huella(filas), **ampliacion,
            'denominadores': {p: dict(sorted(c.items())) for p, c in sorted(denominadores.items())},
            'curriculo_hash': huella({'sesion': FAMILIAS, 'catalogo_revisado': FRASES, 'estilo_real': ESTILO_REAL}),
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
                'gold_human', 'silver_deterministic', 'silver_teacher_verified', CALIDAD}:
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


def _referencia_activa(registros: list[dict]) -> dict | None:
    """El modelo en uso medido por familia sobre la misma prueba sellada (067:RF-25).

    Se pasaba ``None`` y la puerta «falta comparación» fallaba siempre: ningún candidato podía
    aprobarse jamás. Si el modelo en uso no se puede medir, se devuelve ``None`` y la puerta no aprueba.
    """
    from . import transformer as tr
    try:
        activo = tr.cargar()
        if activo is None:
            return None
        return evaluar_alumno(activo, registros)['familias']
    except (ImportError, RuntimeError, OSError, ValueError, KeyError):
        return None


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
                     (Path(__file__), Path(tr.__file__), Path(__file__).with_name('curriculo_maestro.py'),
                      Path(__file__).with_name('maestro_real.py'))},
                 'entorno': {'python': platform.python_version(), 'torch': tr._torch().__version__,
                             'cuda': tr._torch().version.cuda, 'gpu': tr._torch().cuda.get_device_name(0)}}
    codigo = destino / 'codigo'
    codigo.mkdir()
    for archivo in (Path(__file__), Path(tr.__file__), Path(__file__).with_name('curriculo_maestro.py'),
                    Path(__file__).with_name('maestro_real.py'),
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
    prueba_sintetica = [r for r in por_parte['prueba'] if r['quality'] != 'gold_human']
    decision = decidir_promocion(sinteticas, humanas, sinteticas['familias'], _referencia_activa(prueba_sintetica))
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
    # La activación es una operación explícita del registro, no un efecto del ensayo: la hace quien
    # lanza el reentrenamiento con ``modelos_en_uso.aplicar_decision`` (067:RF-20).
    reporte = {'schema_version': 1, 'training_completed': True, 'entrenado': True,
        'status': decision['status'], 'promovido': False, 'decision': decision,
        'denominadores': meta.get('denominadores'),                                       # 068:RF-29, 047:RF-13
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
