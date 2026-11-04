"""Órdenes que redacta el maestro en el estilo del operador, con grupos apartados para examinar (spec 085).

Hay 43 órdenes confirmadas y 12 de las 16 tareas medidas tienen un solo texto (2026-11-03): la validación cruzada de la 075
no puede medir fuera de grupo y nadie va a escribir las 200 de 027:RF-19. El usuario ordenó que el maestro cumpla ese rol.
Sus órdenes viven en el almacén local, fuera de git, y nunca son humanas: entrenan, y una parte de sus familias examina.
Con una forma a cada lado se examinaría al modelo con lo que acaba de leer: por eso se agrupan antes por familia (075).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any

from ..evaluacion_modelos import huella, texto_canonico
from .maestro_real import NINGUNA, clave_texto, con_erratas, firma_familia
from .sinteticos import Ejemplo
from .tareas import TAREAS
from .validacion_cruzada import agrupar_familias, clave_de_familia

ORIGEN = 'maestro'
ARCHIVO = 'ordenes_maestro.jsonl'
CONJUNTO = 'examen_maestro_085'
#: 085:RF-7: declarado antes de redactar ni medir.
FRACCION_EXAMEN = .25
FAMILIAS_MINIMAS = 2
#: 085:RF-11: menos que las 8 de un texto real: el maestro ya da varias formas por tarea.
VARIANTES_ERRATAS = 4
CALIDAD = 'silver_teacher_verified'
#: 027:RF-19: con menos órdenes humanas distintas decide el examen del maestro (085:RF-19).
MIN_HUMANAS = 200
_SAL = '085-examen'


def leer(raiz: Path | str | None = None) -> tuple[list[dict[str, Any]], Counter]:
    """Las órdenes válidas del maestro y la cuenta de las rechazadas, por motivo (085:RF-1 a RF-4)."""
    if raiz is None:
        from . import almacen
        raiz = almacen.raiz()
    ruta = Path(raiz) / ARCHIVO
    filas, cuenta = [], Counter()
    if not ruta.is_file():
        return filas, cuenta
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        if not linea.strip():
            continue
        try:
            f = json.loads(linea)
            texto, tarea = str(f['texto']), f['tarea']
            datos = [tuple(d) for d in f.get('datos') or ()]
        except (ValueError, KeyError, TypeError):
            cuenta['ilegibles'] += 1
            continue
        motivo = _motivo_de_rechazo(f, texto, tarea, datos)
        if motivo:
            cuenta[motivo] += 1
            continue
        cuenta['validas'] += 1
        filas.append({'texto': texto, 'tarea': tarea, 'datos': [list(d) for d in sorted(datos)], 'forma': str(f.get('forma') or ''),
                      'autor': str(f.get('autor') or ''), 'revision': str(f.get('revision') or ''), 'origen': ORIGEN})
    return filas, cuenta


def _motivo_de_rechazo(f: Mapping, texto: str, tarea: str, datos: Sequence[tuple]) -> str:
    if f.get('origen') != ORIGEN:
        return 'rechazadas_origen'                                                    # 085:RF-2
    if tarea != NINGUNA and tarea not in TAREAS:
        return 'rechazadas_tarea'                                                     # 085:RF-3
    admitidos = set() if tarea == NINGUNA else {d.tipo for d in TAREAS[tarea].datos}
    obligatorios = set() if tarea == NINGUNA else {d.tipo for d in TAREAS[tarea].datos if d.obligatorio}
    tipos, ocupado = set(), []
    for d in datos:
        if len(d) != 3 or type(d[0]) is not int or type(d[1]) is not int or not 0 <= d[0] < d[1] <= len(texto):
            return 'rechazadas_datos'
        if d[2] not in admitidos or any(a < d[1] and d[0] < b for a, b in ocupado):
            return 'rechazadas_datos'
        ocupado.append((d[0], d[1]))
        tipos.add(d[2])
    return '' if obligatorios <= tipos else 'rechazadas_datos'                       # 085:RF-4


def _identidad(familia: Sequence[dict]) -> str:
    return huella(sorted(clave_de_familia(r['texto'], r['datos']) for r in familia))


def repartir(filas: Sequence[dict]) -> tuple[list[dict], list[dict], dict[str, dict]]:
    """Examen y entrenamiento por familias; por tarea, el 25 % de sus familias examina (085:RF-6 a RF-9, RF-12).

    Las familias son transitivas y pueden juntar dos tareas: la familia va a la tarea más frecuente en ella, y a igualdad a la
    primera por nombre. Dentro de cada tarea se ordenan por la huella de su identidad: añadir una forma no mueve las demás.
    """
    ordenes = [r for r in filas if r['tarea'] != NINGUNA]
    familias = agrupar_familias(ordenes)
    por_tarea: dict[str, list[list[dict]]] = defaultdict(list)
    for familia in familias:
        cuenta = Counter(r['tarea'] for r in familia)
        por_tarea[min(cuenta, key=lambda t: (-cuenta[t], t))].append(familia)
    examen, entrenar, estado = [], [r for r in filas if r['tarea'] == NINGUNA], {}
    for tarea in sorted(TAREAS):
        grupos = sorted(por_tarea.get(tarea, ()), key=lambda f: hashlib.sha256(f'{_SAL}|{_identidad(f)}'.encode()).hexdigest())
        apartar = math.ceil(FRACCION_EXAMEN * len(grupos)) if len(grupos) >= FAMILIAS_MINIMAS else 0
        for i, familia in enumerate(grupos):
            identidad = _identidad(familia)
            for r in familia:
                (examen if i < apartar else entrenar).append({**r, 'familia': identidad})
        estado[tarea] = {'familias': len(grupos), 'familias_examen': apartar, 'estado': 'con_examen' if apartar else 'sin_examen'}
    for r in entrenar:
        r.setdefault('familia', huella({'ninguna': clave_texto(r['texto'])}) if r['tarea'] == NINGUNA else '')
    return examen, entrenar, estado


def ampliar(filas: list[dict], maestro: Sequence[dict], vedados_texto: Iterable[str], vedadas_familias: Iterable[str]) -> dict:
    """Añade el examen a la prueba y el resto al entrenamiento, sin tocar lo que mide (085:RF-10 a RF-15).

    ``vedados_texto`` y ``vedadas_familias`` son la clave y la firma de selección, calibración, prueba, humanas, fijas de prueba y
    mensajes reservados. Va tras sellar y antes del currículo de la 068: lo que este añada se aparta solo si toca el examen.
    """
    vedados, firmas = set(vedados_texto), set(vedadas_familias)
    cuenta = Counter()

    def choca(texto: str, datos) -> bool:
        return clave_texto(texto) in vedados or firma_familia(texto, datos) in firmas

    limpias = []
    for r in maestro:
        if choca(r['texto'], r['datos']):
            cuenta['descartadas_por_lo_que_mide'] += 1                               # 085:RF-13
        else:
            limpias.append(r)
    examen, entrenar, estado = repartir(limpias)
    claves_examen = {clave_texto(r['texto']) for r in examen}
    firmas_examen = {firma_familia(r['texto'], r['datos']) for r in examen}

    def toca_examen(texto: str, datos) -> bool:
        return clave_texto(texto) in claves_examen or firma_familia(texto, datos) in firmas_examen

    antes = len(filas)
    filas[:] = [r for r in filas if r['particion'] != 'entrenamiento' or not toca_examen(r['texto'], r['datos'])]
    cuenta['entrenamiento_quitado_por_examen'] = antes - len(filas)                  # 085:RF-14
    vistos = {texto_canonico(r['texto']) for r in filas}

    def agregar(e: Ejemplo, parte: str, grupo: str, **extra) -> bool:
        clave = texto_canonico(e.texto)
        if clave in vistos:
            cuenta[f'{parte}_repetidas'] += 1
            return False
        vistos.add(clave)
        r = {'texto': e.texto, 'tarea': e.tarea, 'datos': [list(d) for d in sorted(e.datos)], 'group_id': grupo, 'particion': parte,
             'quality': CALIDAD, 'del_maestro': True, 'origen': ORIGEN, **extra}
        r['record_id'] = huella(r)
        filas.append(r)
        cuenta[f'{parte}_filas'] += 1
        return True

    for r in sorted(examen, key=lambda x: clave_texto(x['texto'])):
        agregar(Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r['datos']]), 'prueba',
                huella({CONJUNTO: r['familia']}), conjunto=CONJUNTO)                 # 085:RF-10
    for r in sorted(entrenar, key=lambda x: clave_texto(x['texto'])):
        e = Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r['datos']])
        grupo = huella({'maestro_085': r['familia']})
        if toca_examen(e.texto, e.datos):
            cuenta['entrenamiento_maestro_apartado_por_examen'] += 1
            continue
        if not agregar(e, 'entrenamiento', grupo, origen_curriculo='ordenes_maestro_085'):
            continue
        if r['tarea'] == NINGUNA:
            continue                                                                  # 085:RF-12: sin erratas, como 069:RF-10
        rnd = random.Random(int(huella({'erratas_maestro_085': clave_texto(e.texto)})[:8], 16))
        for _ in range(VARIANTES_ERRATAS):                                            # 085:RF-11
            v = con_erratas(e, rnd)
            if choca(v.texto, v.datos) or toca_examen(v.texto, v.datos):
                cuenta['variantes_apartadas'] += 1
                continue
            agregar(v, 'entrenamiento', grupo, origen_curriculo='ordenes_maestro_085', aumentado='erratas')
    return {'leidas': len(maestro), 'conjunto': CONJUNTO, 'examen': len(examen), 'entrenamiento': len(entrenar),
            'por_tarea': estado, 'sin_examen': sorted(t for t, d in estado.items() if d['estado'] == 'sin_examen'),
            'examen_por_tarea': dict(sorted(Counter(r['tarea'] for r in examen).items())), **dict(sorted(cuenta.items())),
            'examen_hash': huella(sorted(clave_texto(r['texto']) for r in examen)), 'no_son_humanas': True}


def puerta_de_ordenes(humanas: Mapping, humanas_distintas: int, maestro: Mapping | None) -> dict:
    """Qué conjunto decide la puerta de órdenes de 0,98 y 0,95 (085:RF-19 a RF-22)."""
    n_maestro = (maestro or {}).get('ejemplos') or 0
    if humanas_distintas < MIN_HUMANAS and n_maestro:
        return {'conjunto': ORIGEN, 'medida': dict(maestro), 'denominador': n_maestro, 'humanas_distintas': humanas_distintas,
                'humanas_que_faltan': MIN_HUMANAS - humanas_distintas, 'humanas_deciden': False,
                'motivo': (f'{humanas_distintas} órdenes humanas distintas de las {MIN_HUMANAS}: decide el examen del maestro '
                           f'({n_maestro} órdenes, conjunto {CONJUNTO}); no son órdenes humanas')}
    return {'conjunto': 'humanas', 'medida': dict(humanas), 'denominador': humanas.get('ejemplos', 0),
            'humanas_distintas': humanas_distintas, 'humanas_deciden': True,
            'motivo': (f'{humanas_distintas} órdenes humanas distintas: deciden las humanas' if humanas_distintas >= MIN_HUMANAS
                       else 'sin examen del maestro: deciden las humanas, como antes de la 085')}
