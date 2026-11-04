"""047:RF-13 y RF-16 a RF-18 — aceptación trazable por alcance, sin ejecutar acciones."""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
import time

from ..evaluacion_modelos import huella, texto_canonico
from .ajuste_condicionado import decidir_ajuste, evaluar_puertas_reales, manifiesto_de_humanas
from .tareas import TAREAS
from .sinteticos import normalizar


def auditar_propuestas(filas: list[dict], entrenamiento=()) -> dict:
    entrenamiento = list(entrenamiento)
    textos = [texto_canonico(r['texto']) for r in filas]
    prohibidos = {texto_canonico(r['texto']) for r in entrenamiento}
    grupos_train = {r['group_id'] for r in entrenamiento}
    fallos = []
    if len(filas) != 200 or len(set(textos)) != 200:
        fallos.append('se requieren 200 propuestas únicas')
    if {r['tarea'] for r in filas} != set(TAREAS):
        fallos.append('catálogo de tareas incompleto')
    if set(textos) & prohibidos or {r['group_id'] for r in filas} & grupos_train:
        fallos.append('solapamiento con entrenamiento')
    for r in filas:
        if (r.get('quality') != 'silver_teacher_verified' or r.get('del_maestro') is not True
                or r.get('particion') != 'prueba'
                or r.get('origen') != 'propuesta_maestro_codex_20261031_v1'):
            fallos.append('calidad u origen de propuesta inválidos')
        if r.get('record_id') != huella({k: v for k, v in r.items() if k != 'record_id'}):
            fallos.append('huella de registro inválida')
        if r.get('tarea') not in TAREAS:
            fallos.append('tarea inexistente'); continue
        tipos = set()
        for a, b, tipo in r.get('datos') or []:
            if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(r['texto']):
                fallos.append('span inválido')
            if tipo not in {d.tipo for d in TAREAS[r['tarea']].datos}:
                fallos.append('entidad ajena a la tarea')
            tipos.add(tipo)
        if not {d.tipo for d in TAREAS[r['tarea']].datos if d.obligatorio} <= tipos:
            fallos.append('propuesta sin entidades obligatorias')
    return {'valid': not fallos, 'fallos': sorted(set(fallos)), 'propuestas': len(filas),
            'unicas': len(set(textos)), 'tareas': len({r['tarea'] for r in filas}),
            'sin_fuga': not (set(textos) & prohibidos or {r['group_id'] for r in filas} & grupos_train),
            'dataset_hash': huella(filas)}


def decidir_aceptacion(propuestas: dict, humanas: dict) -> dict:
    fallos = []
    if not _casos_coherentes(propuestas):
        fallos.append('evidencia individual incompleta o contradictoria con las métricas')
    for k, esperado in (('ejemplos', 200), ('unicos', 200), ('tareas', len(TAREAS))):
        if propuestas.get(k) != esperado:
            fallos.append(f'{k}: se requieren {esperado}')
    for k, minimo in (('acierto_tarea', .98), ('f1_datos', .95)):
        v = propuestas.get(k)
        if type(v) not in (float, int) or not math.isfinite(v) or not minimo <= v <= 1:
            fallos.append(f'{k}: bajo {minimo} o inválido')
    if propuestas.get('confirmaciones_conservadas') is not True:
        fallos.append('confirmación de escrituras no acreditada')
    if propuestas.get('sin_fuga') is not True:
        fallos.append('ausencia de fuga no acreditada')
    familias = propuestas.get('familias')
    if not isinstance(familias, dict):
        familias = {}
    conteos = [m.get('ejemplos') for m in familias.values() if isinstance(m, dict)]
    if (set(familias) != set(TAREAS) or len(conteos) != len(TAREAS)
            or any(type(n) is not int or n <= 0 for n in conteos)
            or sum(n for n in conteos if type(n) is int) != 200):
        fallos.append('falta evidencia completa por tarea')
    for tarea, m in familias.items():
        if not isinstance(m, dict) or any(
                type(m.get(k)) not in (int, float) or not math.isfinite(m[k]) or not .95 <= m[k] <= 1
                for k in ('acierto_tarea', 'f1_datos')):
            fallos.append(f'{tarea}: puerta por tarea incumplida')
    n = humanas.get('ejemplos', 0)
    # 047:RF-8, RF-9: las puertas de 027:RF-18 se dicen sobre lo humano: las 200 propuestas no se prestan.
    manifiesto = manifiesto_de_humanas(humanas)
    return {'puertas_reales': evaluar_puertas_reales(humanas, manifiesto), 'ajuste': decidir_ajuste(humanas, manifiesto),
            'asistida': {'aprobada': not fallos, 'confirmacion_obligatoria': True, 'fallos': fallos},
            'humanas': dict(humanas),
            'autonoma': {'aprobada': False, 'motivo': f'{n} órdenes humanas; no se habilita ejecución autónoma'},
            'electrica': {'aprobada': False, 'motivo': 'sin ejecución ni relectura nativa de estos casos'},
            'integral': False, 'propuestas_no_son_humanas': True}


def _casos_coherentes(m):
    """El resumen no puede ocultar casos perdidos ni cambiar sus denominadores."""
    try:
        casos = m['casos']
        if not isinstance(casos, list) or len(casos) != 200:
            return False
        ids = set()
        grupos = defaultdict(list)
        for c in casos:
            if (not isinstance(c, dict) or not re.fullmatch('[0-9a-f]{64}', c['record_id'])
                    or c['record_id'] in ids or c['esperado'] not in TAREAS
                    or type(c['correcto']) is not bool or type(c['confirmacion']) is not bool
                    or c['correcto'] != (c['esperado'] == c['obtenido'])
                    or any(type(c[k]) is not int or c[k] < 0 for k in ('vp', 'fp', 'fn'))):
                return False
            ids.add(c['record_id']); grupos[c['esperado']].append(c)
        def coincide(resumen, filas):
            vp, fp, fn = (sum(c[k] for c in filas) for k in ('vp', 'fp', 'fn'))
            f1 = 2*vp/(2*vp+fp+fn) if vp+fp+fn else 1.
            acierto = sum(c['correcto'] for c in filas)/len(filas)
            return (resumen['ejemplos'] == len(filas)
                    and math.isclose(resumen['acierto_tarea'], acierto, abs_tol=1e-12)
                    and math.isclose(resumen['f1_datos'], f1, abs_tol=1e-12))
        return (coincide(m, casos) and set(grupos) == set(TAREAS)
                and all(coincide(m['familias'][t], filas) for t, filas in grupos.items())
                and m['confirmaciones_conservadas'] == all(c['confirmacion'] for c in casos))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def _normalizar_slot(tipo, valor):
    from .plan import trozos_lista
    from .interprete import numero_de, periodo_de
    valores = valor if isinstance(valor, list) else [valor]
    salida = set()
    for v in valores:
        if isinstance(v, dict):
            v = v.get('valor', '')
        s = normalizar(str(v)).strip(' «»"\'.,;')
        if not s:
            continue
        if tipo == 'alimentadores':
            if re.search(r'\btodos?\b', s):
                salida.add((tipo, '*')); continue
            salida.update((tipo, normalizar(x)) for x in trozos_lista(s))
        elif tipo == 'periodo':
            salida.add((tipo, periodo_de(s) or s))
        elif tipo == 'numero':
            salida.add((tipo, str(numero_de(s)) if numero_de(s) is not None else s))
        else:
            salida.add((tipo, ' '.join(s.split())))
    return salida


def evaluar_ordenes(filas: list[dict], *, cliente, alumno=None, vocabulario=None, log=print) -> dict:
    from .interprete import interpretar
    from .plan import resolver
    resultados = []
    total_vp = total_fp = total_fn = 0
    familias = defaultdict(lambda: {'ejemplos': 0, 'correctos': 0, 'vp': 0, 'fp': 0, 'fn': 0})
    inicio = time.monotonic()
    for i, r in enumerate(filas, 1):
        interp = interpretar(r['texto'], transformer=alumno, ollama=cliente)
        plan = resolver(interp, vocabulario or {})
        esperados, vistos = set(), set()
        for a, b, tipo in r['datos']:
            esperados |= _normalizar_slot(tipo, r['texto'][a:b])
        if plan.tarea in TAREAS:
            for d in TAREAS[plan.tarea].datos:
                valor = plan.datos.get(d.nombre)
                if valor is None:
                    valor = interp.datos.get(d.tipo) or []
                vistos |= _normalizar_slot(d.tipo, valor)
        vp, fp, fn = len(esperados & vistos), len(vistos - esperados), len(esperados - vistos)
        total_vp += vp; total_fp += fp; total_fn += fn
        f = familias[r['tarea']]; f['ejemplos'] += 1; f['correctos'] += plan.tarea == r['tarea']
        f['vp'] += vp; f['fp'] += fp; f['fn'] += fn
        resultados.append({'record_id': r['record_id'], 'esperado': r['tarea'], 'obtenido': plan.tarea,
            'correcto': plan.tarea == r['tarea'], 'vp': vp, 'fp': fp, 'fn': fn,
            'modelo': interp.modelo, 'confianza': interp.confianza,
            'esperados': sorted(esperados), 'vistos': sorted(vistos), 'faltan': plan.faltan,
            'confirmacion': not plan.escribe or any('confirmación' in x for x in plan.razonamiento)})
        log(f'{i}/{len(filas)}: {r["tarea"]}: {"correcto" if resultados[-1]["correcto"] else "fallo"}', flush=True)
    def f1(vp, fp, fn):
        return 2 * vp / (2 * vp + fp + fn) if vp + fp + fn else 1.
    por_tarea = {t: {'ejemplos': m['ejemplos'], 'acierto_tarea': m['correctos'] / m['ejemplos'],
                     'f1_datos': f1(m['vp'], m['fp'], m['fn'])} for t, m in familias.items()}
    return {'ejemplos': len(filas), 'unicos': len({texto_canonico(r['texto']) for r in filas}),
        'tareas': len(familias), 'acierto_tarea': sum(r['correcto'] for r in resultados) / max(1, len(filas)),
        'f1_datos': f1(total_vp, total_fp, total_fn), 'familias': por_tarea, 'casos': resultados,
        'confirmaciones_conservadas': all(r['confirmacion'] for r in resultados), 'escrituras_nativas': 0,
        'duracion_s': time.monotonic() - inicio, 'modelo_llm': cliente.modelo,
        'revision_obligatoria': bool(cliente.revisar_transformer),
        'dos_etapas': bool(cliente.dos_etapas), 'pensar': cliente.pensar}


def estado_aceptacion() -> dict:
    """Lee custodia y resultados sin cargar modelos ni llamar a un servicio externo."""
    import json
    from pathlib import Path
    from . import almacen
    originales = [r for r in almacen.leer('ejemplos') if r.get('origen') in ('confirmado', 'corregido')
                  and r.get('tarea') in TAREAS and str(r.get('texto') or '').strip()]
    unicas = len({texto_canonico(normalizar(r['texto'])) for r in originales})
    puntero = almacen.leer_json('aceptacion_agente') or {}
    out = {'schema_version': 1, 'propuestas': {'definidas': 200, 'materializadas': 0,
            'unicas': 0, 'huella': None, 'filas': []},
           'humanas': {'eventos': len(originales), 'unicas': unicas},
           'evaluacion': None, 'bloqueos': [], 'integral': False}
    if not isinstance(puntero, dict):
        out['bloqueos'].append('puntero de aceptación inválido')
        return out
    filas = []
    try:
        if puntero.get('corpus'):
            carpeta = Path(puntero['corpus'])
            filas = json.loads((carpeta / 'propuestas.json').read_text(encoding='utf-8'))
            meta = json.loads((carpeta / 'manifest.json').read_text(encoding='utf-8'))
            if huella(filas) != meta['dataset_hash'] or not auditar_propuestas(filas)['valid']:
                raise ValueError('integridad de propuestas inválida')
            out['propuestas'] = {'definidas': 200, 'materializadas': len(filas),
                'unicas': len({texto_canonico(r['texto']) for r in filas}), 'huella': meta['dataset_hash'],
                'filas': [{'texto': r['texto'], 'tarea': r['tarea']} for r in filas]}
        if puntero.get('evaluacion'):
            r = json.loads(Path(puntero['evaluacion']).read_text(encoding='utf-8'))
            if r['manifest']['dataset_hash'] != out['propuestas']['huella']:
                raise ValueError('evaluación de otro corpus')
            esperados = {f['record_id']: f['tarea'] for f in filas}
            observados = {c['record_id']: c['esperado'] for c in r['metricas'].get('casos', [])}
            if observados != esperados:
                raise ValueError('casos de evaluación distintos del corpus')
            out['evaluacion'] = {'modelo': r['metricas']['modelo_llm'], 'ejemplos': r['metricas']['ejemplos'],
                'acierto_tarea': r['metricas']['acierto_tarea'], 'f1_datos': r['metricas']['f1_datos'],
                'aceptacion': decidir_aceptacion(r['metricas'], r.get('humanas') or {})}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        out['bloqueos'].append(str(exc))
    return out
