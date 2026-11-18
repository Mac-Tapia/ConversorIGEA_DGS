"""HARNESS: métricas con soporte explícito y remuestreo por grupos."""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from statistics import fmean


def conteos(vp: int, fp: int, fn: int) -> dict:
    if any(type(v) is not int or v < 0 for v in (vp, fp, fn)):
        raise ValueError('VP/FP/FN deben ser enteros no negativos')
    return {'vp': vp, 'fp': fp, 'fn': fn, 'soporte': vp + fn,
            'predichos': vp + fp, 'precision': vp/(vp+fp) if vp+fp else None,
            'recall': vp/(vp+fn) if vp+fn else None,
            'f1': 2*vp/(2*vp+fp+fn) if 2*vp+fp+fn else None}


def _media(valores):
    validos = [v for v in valores if v is not None]
    return fmean(validos) if validos else None


def clasificacion(casos: list[dict], clases: list[str]) -> dict:
    if not clases or len(set(clases)) != len(clases) or any(
            not isinstance(c, str) or not c or c == '__abstencion__' for c in clases):
        raise ValueError('catálogo de clases inválido')
    matriz = {c: {p: 0 for p in [*clases, '__abstencion__']} for c in clases}
    for caso in casos:
        esperado, visto = caso['esperado'], caso.get('obtenido')
        if esperado not in matriz or (visto is not None and visto not in clases):
            raise ValueError('clase ajena al catálogo')
        matriz[esperado][visto if visto is not None else '__abstencion__'] += 1
    metricas = {}
    for c in clases:
        vp = matriz[c][c]
        fp = sum(matriz[otra][c] for otra in clases if otra != c)
        fn = sum(matriz[c].values()) - vp
        metricas[c] = conteos(vp, fp, fn)
    total = conteos(*(sum(m[k] for m in metricas.values()) for k in ('vp', 'fp', 'fn')))
    return {'ejemplos': len(casos), 'matriz': matriz, 'clases': metricas,
            'micro': total, 'macro': {k: _media(m[k] for m in metricas.values())
                                     for k in ('precision', 'recall', 'f1')},
            'clases_con_soporte': sum(m['soporte'] > 0 for m in metricas.values()),
            'acierto': sum(matriz[c][c] for c in clases)/len(casos) if casos else None}


def _entidades(valores):
    if not isinstance(valores, list) or any(
            not isinstance(v, (list, tuple)) or len(v) != 2
            or any(not isinstance(x, str) or not x for x in v) for v in valores):
        raise ValueError('entidad requiere [tipo, valor] normalizados')
    resultado = {tuple(v) for v in valores}
    if len(resultado) != len(valores):
        raise ValueError('entidades duplicadas')
    return resultado


def entidades(casos: list[dict]) -> dict:
    totales = Counter(vp=0, fp=0, fn=0)
    por_tipo = defaultdict(lambda: Counter(vp=0, fp=0, fn=0))
    for caso in casos:
        gold, pred = _entidades(caso['esperados']), _entidades(caso['vistos'])
        conjuntos = {'vp': gold & pred, 'fp': pred-gold, 'fn': gold-pred}
        for nombre, valores in conjuntos.items():
            if nombre in caso and (type(caso[nombre]) is not int or caso[nombre] != len(valores)):
                raise ValueError('conteos contradictorios con las entidades')
            totales[nombre] += len(valores)
            for tipo, _valor in valores:
                por_tipo[tipo][nombre] += 1
    return {**conteos(**totales), 'ejemplos': len(casos),
            'tipos': {t: conteos(**m) for t, m in sorted(por_tipo.items())},
            'convencion': 'conteos_v1_null_sin_denominador'}


def recuperacion(casos: list[dict], *, k: int) -> dict:
    if type(k) is not int or k < 1:
        raise ValueError('k debe ser entero positivo')
    filas = []
    for caso in casos:
        gold, pred = caso['relevantes'], caso['recuperados']
        if any(not isinstance(ids, list) or any(not isinstance(x, str) or not x for x in ids)
               or len(set(ids)) != len(ids) for ids in (gold, pred)):
            raise ValueError('ids inválidos o duplicados')
        if type(caso.get('gold_completo')) is not bool:
            raise ValueError('declarar alcance del gold')
        gold_set, elegidos = set(gold), pred[:k]
        aciertos = len(gold_set.intersection(elegidos))
        filas.append({'precision@k': aciertos/k,
                      'recall@k': aciertos/len(gold) if gold and caso['gold_completo'] else None,
                      'mrr@k': next((1/i for i, x in enumerate(elegidos, 1) if x in gold_set), 0.),
                      'sin_respuesta': not gold and caso['gold_completo'],
                      'abstencion': not pred, 'aciertos': aciertos})
    sin = [f for f in filas if f['sin_respuesta']]
    completos = all(c['gold_completo'] for c in casos)
    return {'ejemplos': len(casos), 'k': k, 'denominador_precision': k,
            'precision@k': _media(f['precision@k'] for f in filas) if completos else None,
            'precision_positivos_conocidos@k': _media(f['precision@k'] for f in filas),
            # Un promedio de los pocos gold completos tampoco es recall de la suite entera.
            'recall@k': _media(f['recall@k'] for f in filas) if completos else None,
            'consultas_con_recall': sum(f['recall@k'] is not None for f in filas),
            'gold_completo': completos,
            'mrr@k': _media(f['mrr@k'] for f in filas) if completos else None,
            'mrr_positivos_conocidos@k': _media(f['mrr@k'] for f in filas),
            'sin_respuesta': len(sin),
            'abstencion_correcta': _media(float(f['abstencion']) for f in sin),
            'recuperacion_indebida': sum(not f['abstencion'] for f in sin), 'casos': filas}


def comparar_pareado(casos: list[dict], *, metrica: str, margen: float,
                     semilla: int, remuestras: int, confianza: float, min_grupos: int,
                     direccion: str = 'mayor_mejor') -> dict:
    """Mejora de medias por grupo; no es un IC de un ratio global."""
    if (type(semilla) is not int or type(remuestras) is not int or remuestras < 100
            or type(min_grupos) is not int or min_grupos < 2
            or type(margen) not in (int, float) or not math.isfinite(margen) or margen < 0
            or type(confianza) not in (int, float) or not 0 < confianza < 1
            or direccion not in {'mayor_mejor', 'menor_mejor'}):
        raise ValueError('protocolo de comparación inválido')
    grupos = defaultdict(list)
    for caso in casos:
        if not isinstance(caso.get('group_id'), str) or not caso['group_id']:
            raise ValueError('grupo ausente')
        if any(type(caso.get(k)) not in (int, float) or not math.isfinite(caso[k])
               for k in ('referencia', 'candidato')):
            raise ValueError('par no finito')
        signo = 1 if direccion == 'mayor_mejor' else -1
        grupos[caso['group_id']].append(signo*(caso['candidato']-caso['referencia']))
    diferencias = [fmean(grupos[g]) for g in sorted(grupos)]
    salida = {'metrica': metrica, 'estimando': 'mejora_media_grupos', 'direccion': direccion,
              'grupos': len(grupos), 'ejemplos': len(casos), 'margen': margen,
              'confianza': confianza, 'semilla': semilla, 'remuestras': remuestras,
              'diferencia': fmean(diferencias) if diferencias else None,
              'intervalo': None, 'mejora_demostrada': False}
    if len(grupos) < min_grupos:
        return {**salida, 'motivo': 'grupos independientes insuficientes'}
    rnd = random.Random(semilla)
    muestras = sorted(fmean(rnd.choices(diferencias, k=len(diferencias))) for _ in range(remuestras))
    alfa = (1-confianza)/2
    intervalo = [muestras[int(alfa*(remuestras-1))], muestras[math.ceil((1-alfa)*(remuestras-1))]]
    return {**salida, 'intervalo': intervalo, 'mejora_demostrada': intervalo[0] > margen}
