"""Evaluación sellada de la recuperación: BM25, híbrido y reranker con las mismas preguntas (047:RF-4).

El conjunto es sintético del maestro de sesión, sobre fragmentos reales del índice: sirve para
contrastar métodos, nunca para acreditar órdenes de operadores (027:RF-42). La política de adopción
se declaró en el plan de la 047 antes de medir, y ``decidir`` la aplica sin ajustarse a lo medido.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from . import indice as modulo_indice
from .embeddings import ParContraste, comparar_pareado, evaluar_recuperador
from .reranker import ABSTENCION_MINIMA, reordenar, sha256_de

METRICA = 'mrr@10'
CANDIDATO_K = 10
LATENCIA_P95_MAX_MS = 5000.0


def cargar_conjunto(ruta: Path) -> dict[str, Any]:
    """El conjunto con su sello; rechaza el que no declara que es sintético."""
    datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    if not str(datos.get('procedencia') or '').startswith('sintetico'):
        raise ValueError('el conjunto debe declarar su procedencia sintética: no son preguntas de operadores')
    return {**datos, 'sha256': sha256_de(ruta)}


def _grupo(pregunta: str) -> str:
    return hashlib.sha256(pregunta.encode('utf-8')).hexdigest()


def _casa_ancla(ancla: str, fichero: str, texto: str) -> bool:
    """La 076 ancla un RF en la línea del fichero, «- RF-13:», y el índice lo guarda como «<spec> RF-13: …»."""
    if (rf := re.match(r'^- (RF-[\w-]+):$', ancla)) is not None:
        return texto.startswith(f"{fichero.split('/')[1]} {rf.group(1)}:")
    return ancla in texto


def _positivos_de(fila: Mapping[str, Any], por_fichero: Mapping[str, Sequence[Any]]) -> tuple[str, ...]:
    """Los fragmentos de una pregunta. Las de la 047 anclan por el comienzo; las de la 077 traen varias fuentes, y su
    ancla es una línea, que en el corpus ampliado puede ir dentro del trozo y no al principio (077:RF-44)."""
    if 'fuentes' not in fila:
        return tuple(str(f.fuente) for f in por_fichero.get(str(fila['fichero']), ())
                     if str(f.texto).startswith(str(fila['ancla'])))
    return tuple(dict.fromkeys(str(f.fuente) for fuente in fila['fuentes']
                               for f in por_fichero.get(str(fuente['fichero']), ())
                               if _casa_ancla(str(fuente['ancla']).strip(), str(fuente['fichero']), str(f.texto))))


class _SigueMovidos(dict):
    """Las fuentes por fichero, siguiendo al que cambió de carpeta con el mismo nombre (097:RF-18).

    Al medir la 097 el 2026-11-13: el frontend había pasado de ``frontend/src/components/`` a ``features/<área>/`` y ``src/vnr_etl``
    a ``src/convertersmartgrid/adaptadores/entrada/vnr``: 34 de 308 preguntas de la calibración del 077 perdían su
    ancla y la medición no se podía hacer (077:RF-49). Solo se sigue si el nombre es único en el corpus; el ancla se
    sigue buscando dentro del fichero, así que una línea editada sigue perdida. El conjunto ni su sello cambian."""

    def __init__(self, por_fichero: Mapping[str, Sequence[Any]]):
        super().__init__(por_fichero)
        nombres: dict[str, list[str]] = {}
        for k in por_fichero:
            nombres.setdefault(k.rsplit('/', 1)[-1], []).append(k)
        self._unico = {n: ks[0] for n, ks in nombres.items() if len(ks) == 1}
        self.seguidos: dict[str, str] = {}

    def get(self, clave: Any, defecto: Any = None) -> Any:
        if clave in self:
            return self[clave]
        nuevo = self._unico.get(str(clave).rsplit('/', 1)[-1])
        if nuevo is None:
            return defecto
        self.seguidos[str(clave)] = nuevo
        return self[nuevo]


def resolver_pares(conjunto: Mapping[str, Any], frags: Sequence[Any]) -> tuple[list[ParContraste], list[str], set[str]]:
    """Cada pregunta con los fragmentos reales que la responden, las que perdieron su ancla y las de código.

    Va por fichero y comienzo del texto, no por línea: una línea se mueve con cualquier edición ajena.
    """
    por_fichero: dict[str, list[Any]] = {}
    for f in frags:
        por_fichero.setdefault(str(f.fuente).rsplit(':', 1)[0], []).append(f)
    por_fichero = _SigueMovidos(por_fichero)                          # 097:RF-18
    pares, sin_ancla, codigos = [], [], set()
    for fila in conjunto['preguntas']:
        pregunta, grupo = str(fila['pregunta']), _grupo(str(fila['pregunta']))
        if fila.get('sin_respuesta') is True:
            pares.append(ParContraste(pregunta, (), (), False, grupo))
            continue
        positivos = _positivos_de(fila, por_fichero)
        if not positivos:
            sin_ancla.append(pregunta)
            continue
        pares.append(ParContraste(pregunta, positivos, (), True, grupo))
        if fila.get('tipo') == 'codigo':
            codigos.add(grupo)
    return pares, sin_ancla, codigos


#: Más filas sin ancla que esto y la medición ya no sería del conjunto que se selló (077:RF-49).
TOPE_SIN_ANCLA = 0.05


#: Lo que dice de sí mismo un conjunto formado sin las preguntas que su corpus ya lleva (097:RF-19).
ORIGEN_SIN_LAS_DEL_CORPUS = (
    'Filas del reparto «{reparto}» de la 076 sin ninguna pregunta de su grupo de paráfrasis, de ninguna longitud, literal '
    'en un fichero del corpus 077 que no sea su fuente (097:RF-19), y las preguntas ajenas al proyecto que tampoco están '
    'en él. Las demás filas del reparto no entran porque el corpus ya las lleva: el documento del maestro que el usuario '
    'decidió indexar (docs/PREGUNTAS_MAESTRO_076.md, 076:RF-29, 076 T8) copia las marcadas correctas, y no copia las '
    'marcadas incorrectas (076:RF-30), que son las que quedan; de esas no vale la respuesta esperada, pero sí la pregunta y '
    'sus anclas, que es lo único que mide la recuperación. Una sin respuesta entra solo si el maestro confirmó que el '
    'repositorio no la tiene: marcada incorrecta, dice que sí la tiene.')


def conjunto_de_entregables(filas: Sequence[Mapping[str, Any]], reparto: str, frags: Sequence[Any],
                            fuera: Sequence[str], *, sin_las_del_corpus: bool = False) -> dict[str, Any]:
    """Un conjunto de la 077 desde un reparto de la 076, más preguntas ajenas al proyecto (077:RF-44).

    Solo entran las filas con una fuente en el índice: una cuya única fuente es el cuerpo de una función no se puede
    recuperar por diseño, y medirla sería medir el troceado. Se cuentan, no se ocultan.

    Con ``sin_las_del_corpus`` (097:RF-19), tampoco las que el corpus ya contiene, ni las de su grupo de paráfrasis, ni las
    sin respuesta que el maestro no confirmó. Caso real (D077, 2026-11-13): la calibración del 077 salía del reparto
    «corpus» entero, y el documento del maestro que el corpus indexa (076:RF-29) copiaba 231 de sus 308 preguntas; cada una
    se encontraba a sí misma y no a su respuesta. El documento se queda (decisión del usuario, opción A): cambia el conjunto.
    """
    from . import fuga_evaluacion

    por_fichero: dict[str, list[Any]] = {}
    for f in frags:
        por_fichero.setdefault(str(f.fuente).rsplit(':', 1)[0], []).append(f)
    del_reparto = [f for f in filas if f['reparto'] == reparto]
    en_el_corpus: set[str] = set()
    fuera_copiadas: set[str] = set()
    if sin_las_del_corpus:
        textos = fuga_evaluacion.textos_por_fichero(frags)
        candidatas = [fuga_evaluacion.Pregunta(str(f['id']), str(f['pregunta']), frozenset(
            () if f['tipo'] == 'sin_respuesta' else (str(x['fichero']) for x in f['fuentes']))) for f in del_reparto]
        candidatas += [fuga_evaluacion.Pregunta('fuera', q) for q in fuera]
        halladas = fuga_evaluacion.fugas(textos, candidatas, min_palabras=1)['fugas']
        copiadas = {h['conjunto'] for h in halladas}
        en_el_corpus = {str(f.get('grupo_parafrasis') or f['id']) for f in del_reparto if str(f['id']) in copiadas}
        fuera_copiadas = {h['pregunta'] for h in halladas if h['conjunto'] == 'fuera'}
    preguntas, excluidas, copiadas_n, sin_confirmar = [], 0, 0, 0
    for fila in del_reparto:
        if str(fila.get('grupo_parafrasis') or fila['id']) in en_el_corpus:
            copiadas_n += 1
            continue
        if fila['tipo'] == 'sin_respuesta':
            if sin_las_del_corpus and (fila.get('revision') or {}).get('veredicto') != 'correcta':
                sin_confirmar += 1
                continue
            preguntas.append({'id': fila['id'], 'pregunta': fila['pregunta'], 'sin_respuesta': True, 'tipo': 'dominio'})
            continue
        fuentes = [{'fichero': x['fichero'], 'ancla': x['ancla']} for x in fila['fuentes']]
        if _positivos_de({'fuentes': fuentes}, por_fichero):
            preguntas.append({'id': fila['id'], 'pregunta': fila['pregunta'], 'tipo': 'entregable', 'fuentes': fuentes})
        else:
            excluidas += 1
    for q in fuera:
        if q in fuera_copiadas:
            copiadas_n += 1
            continue
        preguntas.append({'pregunta': q, 'sin_respuesta': True, 'tipo': 'fuera'})
    salida = {'esquema': 'csg-conjunto-rag-077-v1', 'procedencia': 'sintetico_maestro_076_y_077', 'corpus': '077',
              'reparto': reparto, 'excluidas_sin_fuente_indexada': excluidas, 'preguntas': preguntas}
    if sin_las_del_corpus:
        salida.update({'origen_de_las_preguntas': ORIGEN_SIN_LAS_DEL_CORPUS.format(reparto=reparto),
                       'excluidas_en_el_corpus': copiadas_n, 'excluidas_sin_respuesta_sin_confirmar': sin_confirmar})
    return salida


def sin_anclas_perdidas(conjunto: Mapping[str, Any], frags: Sequence[Any], tope: float = TOPE_SIN_ANCLA) -> dict[str, Any]:
    """El conjunto sin las filas cuya fuente ya cambió, o un error si son demasiadas (077:RF-49): las fuentes de la 076
    siguen moviéndose con cada rama, y una fila perdida no debe parar la medición ni tantas falsearla. No cambia el sello."""
    _, sin_ancla, _ = resolver_pares(conjunto, frags)
    total = len(conjunto['preguntas'])
    if total and len(sin_ancla) / total > tope:
        raise ValueError(f'{len(sin_ancla)} de {total} preguntas perdieron su ancla: no se mide')
    perdidas = set(sin_ancla)
    return {**conjunto, 'preguntas': [f for f in conjunto['preguntas'] if f['pregunta'] not in perdidas],
            'perdidas_al_medir': len(perdidas)}


#: Lo mínimo para calibrar una abstención de 0,95 (097:RF-19). Con n preguntas sin respuesta, el umbral es su cuantil
#: ⌈(n+1)(1−α)⌉/n (corrección de muestra finita de la calibración conformal; Angelopoulos y Bates, «A Gentle Introduction
#: to Conformal Prediction and Distribution-Free Uncertainty Quantification», arXiv 2107.07511): con n=25 sale el máximo,
#: y el umbral queda en manos de una sola pregunta. Con 100 lo fijan las cinco que el 0,95 deja pasar. Caso real (auditor
#: c7, 2026-11-13): la calibración del 077 sin las preguntas del corpus bajó de 308 a 58, con solo 25 sin respuesta.
MINIMO_SIN_RESPUESTA = 100
MINIMO_CON_RESPUESTA = 30


def muestra_suficiente(conjunto: Mapping[str, Any], minimo_sin: int = MINIMO_SIN_RESPUESTA,
                       minimo_con: int = MINIMO_CON_RESPUESTA) -> dict[str, int]:
    """Las preguntas con y sin respuesta del conjunto, o un error que dice cuántas faltan (097:RF-19): por debajo del
    mínimo el umbral no generaliza, y se niega a calibrar como con las anclas perdidas (077:RF-49)."""
    sin = sum(bool(f.get('sin_respuesta')) for f in conjunto['preguntas'])
    con = len(conjunto['preguntas']) - sin
    faltan = []
    if sin < minimo_sin:
        faltan.append(f'{minimo_sin - sin} sin respuesta')
    if con < minimo_con:
        faltan.append(f'{minimo_con - con} con respuesta')
    if faltan:
        raise ValueError(f'La calibración tiene {sin} preguntas sin respuesta y {con} con ella; faltan '
                         f'{" y ".join(faltan)} para un umbral que generalice (097:RF-19): no se calibra')
    return {'sin_respuesta': sin, 'con_respuesta': con}


def _medir(pares: Sequence[ParContraste], buscar: Callable[[str, int], Sequence[Any]]) -> dict[str, Any]:
    latencias: list[float] = []

    def cronometrado(pregunta: str, k: int) -> Sequence[Any]:
        inicio = time.perf_counter()
        salida = buscar(pregunta, k)
        latencias.append((time.perf_counter() - inicio) * 1000.0)
        return salida

    metricas = evaluar_recuperador(pares, cronometrado)
    metricas['latencia_p95_ms'] = _p95(latencias)
    metricas['latencias_ms'] = latencias                   # 097:RF-15: para el intervalo del p95, no solo su valor
    return metricas


def _p95(valores: Sequence[float]) -> float:
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(0.95 * len(orden)))] if orden else 0.0


def _pierden_codigo(base: Mapping[str, Any], candidato: Mapping[str, Any], codigos: set[str]) -> list[str]:
    antes = {x['group_id']: x for x in base.get('per_query') or ()}
    return [x['group_id'] for x in candidato.get('per_query') or ()
            if x['group_id'] in codigos and x['group_id'] in antes
            and float(x.get('exact_citation@1', 0)) < float(antes[x['group_id']].get('exact_citation@1', 0))]


def decidir(metodos: Mapping[str, Mapping[str, Any]], codigos: set[str]) -> dict[str, Any]:
    """La política declarada en el plan, aplicada a lo medido; no se ajusta a los resultados."""
    bm25, hibrido = metodos.get('bm25') or {}, metodos.get('hibrido') or {}
    motivos_h = []
    if not float(hibrido.get(METRICA, 0.0)) > float(bm25.get(METRICA, 0.0)):
        motivos_h.append(f'{METRICA} no supera a BM25: sin promover por empate')
    if float(hibrido.get('recall@10', 0.0)) < float(bm25.get('recall@10', 0.0)):
        motivos_h.append('Recall@10 baja')
    if _pierden_codigo(bm25, hibrido, codigos):
        motivos_h.append('una pregunta de código pierde su primer lugar')
    por_modelo: dict[str, Any] = {}
    aptos: list[tuple[float, str]] = []
    for nombre, medido in metodos.items():
        if not nombre.startswith('reranker:'):
            continue
        modelo = nombre.split(':', 1)[1]
        if medido.get('error'):
            por_modelo[modelo] = {'motivos': [f"error al medir: {medido['error']}"], 'frente_a': {}}
            continue
        motivos, frente = [], {}
        for etiqueta, base in (('bm25', bm25), ('hibrido', hibrido)):
            comp = comparar_pareado(base, medido, metrica=METRICA)
            frente[etiqueta] = comp
            if comp.get('status') != 'OK':
                motivos.append(f'frente a {etiqueta}: sin datos pareados')
            elif not (comp['mean_difference'] > 0 and comp['ci95_bootstrap'][0] > 0):
                motivos.append(f'frente a {etiqueta}: {METRICA} sin mejora con IC95 % sobre cero')
            if float(medido.get('recall@10', 0.0)) < float(base.get('recall@10', 0.0)):
                motivos.append(f'frente a {etiqueta}: Recall@10 baja')
            if _pierden_codigo(base, medido, codigos):
                motivos.append(f'frente a {etiqueta}: una pregunta de código pierde su primer lugar')
        if float(medido.get('latencia_p95_ms', 0.0)) > LATENCIA_P95_MAX_MS:
            motivos.append(f'percentil 95 de latencia sobre {LATENCIA_P95_MAX_MS:.0f} ms')
        por_modelo[modelo] = {'motivos': motivos, 'frente_a': frente}
        if not motivos:
            aptos.append((float(medido.get(METRICA, 0.0)), modelo))
    elegido = max(aptos)[1] if aptos else None
    return {'hibrido': {'adoptado': not motivos_h, 'motivos': motivos_h},
            'reranker': {'adoptado': elegido is not None, 'modelo': elegido, 'por_modelo': por_modelo,
                         'motivos': [] if elegido else ['ningún reranker cumple la política declarada']}}


def evaluar(indice: Any, conjunto: Mapping[str, Any], vector_de: Callable[[str], Sequence[float] | None],
            puntuadores: Mapping[str, Callable[[str, Sequence[str]], Sequence[float]]],
            revisiones: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Mide los tres métodos por la misma vía que usa la respuesta y aplica la decisión."""
    pares, sin_ancla, codigos = resolver_pares(conjunto, indice.frags)
    if sin_ancla:
        raise ValueError(f'preguntas sin ancla en el índice, medir falsearía la comparación: {sin_ancla}')
    vectores = {p.pregunta: vector_de(p.pregunta) for p in pares}

    def buscador(con_vector: bool, reordenador: Any = None) -> Callable[[str, int], list[dict]]:
        def buscar(pregunta: str, k: int) -> list[dict]:
            r = modulo_indice.recuperar(indice, pregunta, k, vector=vectores[pregunta] if con_vector else None,
                                        reordenador=reordenador)
            return r['hallados'] if r['sabe'] else []                 # abstenerse es no responder
        return buscar

    metodos: dict[str, Any] = {'bm25': _medir(pares, buscador(False)), 'hibrido': _medir(pares, buscador(True))}
    for modelo, puntuar in puntuadores.items():
        fallo: list[str] = []

        def reordenador(consulta: str, candidatos: Sequence[Mapping], *, _p: Any = puntuar, _m: str = modelo,
                        _f: list[str] = fallo) -> list[dict]:
            if _f:
                raise modulo_indice.RerankerNoDisponible(_f[0])
            try:
                return reordenar(consulta, candidatos, modelo=_m, revision='', puntuar=_p)
            except modulo_indice.RerankerNoDisponible as exc:
                _f.append(str(exc))
                raise

        medido = _medir(pares, buscador(True, reordenador))
        metodos[f'reranker:{modelo}'] = {'error': fallo[0]} if fallo else medido
        if hasattr(puntuar, 'liberar'):
            puntuar.liberar()
    decision = decidir(metodos, codigos)
    tipo = {_grupo(str(f['pregunta'])): f.get('tipo') for f in conjunto['preguntas']}
    for medido in metodos.values():
        if 'per_query' in medido:
            medido['intervalos'] = con_intervalos(medido, tipo)        # 097:RF-15
    if decision['reranker']['modelo'] and revisiones:
        decision['reranker']['revision'] = revisiones.get(decision['reranker']['modelo'])
    return {'esquema': 'csg-evaluacion-rag-v1', 'procedencia': conjunto['procedencia'],
            'conjunto_sha256': conjunto['sha256'], 'metrica_primaria': METRICA,
            'preguntas': len(pares), 'con_respuesta': sum(p.answerable for p in pares),
            'cobertura_vectores': indice.cobertura, 'metodos': metodos, 'decision': decision}


#: El margen de calibración, declarado en el plan de la 047 antes de medir, como la puerta (``ABSTENCION_MINIMA``).
OBJETIVO_CALIBRACION = 0.95
_POR_ENCIMA = 1e-6


def leer_puntuaciones(indice: Any, conjunto: Mapping[str, Any], vector_de: Callable[[str], Sequence[float] | None],
                      puntuar: Callable[[str, Sequence[str]], Sequence[float]], modelo: str) -> list[dict[str, Any]]:
    """La mejor señal de cada método en cada pregunta, por la misma búsqueda que la respuesta."""
    pares, sin_ancla, _ = resolver_pares(conjunto, indice.frags)
    if sin_ancla:
        raise ValueError(f'preguntas sin ancla en el índice, calibrar con ellas falsearía el umbral: {sin_ancla}')
    tipo = {_grupo(str(f['pregunta'])): f.get('tipo') for f in conjunto['preguntas']}
    filas = []
    for par in pares:
        candidatos = indice.buscar(par.pregunta, modulo_indice.CANDIDATOS, vector_de(par.pregunta))
        puntuados = reordenar(par.pregunta, candidatos, modelo=modelo, revision='', puntuar=puntuar) if candidatos else []
        filas.append({'grupo': par.group_id, 'tipo': tipo.get(par.group_id), 'responde': par.answerable,
                      'codigo': indice.nombra_codigo(par.pregunta, candidatos),
                      'bm25': max((c['bm25'] for c in candidatos), default=float('-inf')),
                      'coseno': max((c['coseno'] for c in candidatos), default=float('-inf')),
                      'reranker': max((c['reranker'] for c in puntuados), default=float('-inf'))})
    return filas


def _candidatos_umbral(filas: Sequence[Mapping], senal: str) -> list[float]:
    """Justo por encima de cada pregunta sin respuesta: los únicos umbrales que cambian la abstención."""
    return sorted({float(f[senal]) + _POR_ENCIMA for f in filas if not f['responde'] and f[senal] != float('-inf')})


def calibrar(filas: Sequence[Mapping[str, Any]], objetivo: float = OBJETIVO_CALIBRACION) -> dict[str, Any]:
    """Los umbrales de cada método (047:RF-34): el más bajo con abstención ≥ ``objetivo``; en el par
    coseno-BM25, el que más preguntas con respuesta conserve y, a igualdad, los más bajos."""
    utiles = [f for f in filas if not f['codigo']]                     # el código se decide aparte (RF-37)
    sin = [f for f in utiles if not f['responde']]
    con = [f for f in utiles if f['responde']]
    if not sin or not con:
        raise ValueError('calibrar exige preguntas con respuesta y sin ella')

    def tasas(cumple: Callable[[Mapping], bool]) -> tuple[float, float]:
        return sum(not cumple(f) for f in sin) / len(sin), sum(cumple(f) for f in con) / len(con)

    umbrales: dict[str, float | None] = {}
    resumen: dict[str, Any] = {}
    for clave, senal in (('reranker', 'reranker'), ('bm25_solo', 'bm25')):
        for t in _candidatos_umbral(utiles, senal):
            abstiene, conserva = tasas(lambda f, t=t, s=senal: f[s] >= t)
            if abstiene >= objetivo:
                umbrales[clave], resumen[clave] = t, {'abstencion': abstiene, 'conserva': conserva}
                break
    mejor = None
    for ub in [*_candidatos_umbral(utiles, 'bm25'), None]:
        for uc in [*_candidatos_umbral(utiles, 'coseno'), None]:
            if ub is None and uc is None:
                continue
            abstiene, conserva = tasas(lambda f, ub=ub, uc=uc: (ub is not None and f['bm25'] >= ub)
                                       or (uc is not None and f['coseno'] >= uc))
            if abstiene < objetivo:
                continue
            clave = (-conserva, float('inf') if ub is None else ub, float('inf') if uc is None else uc)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, ub, uc, abstiene, conserva)
    if mejor is not None:
        umbrales['bm25'], umbrales['coseno'] = mejor[1], mejor[2]
        resumen['hibrido'] = {'abstencion': mejor[3], 'conserva': mejor[4]}
    return {'objetivo': objetivo, 'umbrales': umbrales, 'en_calibracion': resumen,
            'preguntas': {'con_respuesta': len(con), 'sin_respuesta': len(sin)}}


def _puerta(con: Mapping[str, Any], sin: Mapping[str, Any]) -> dict[str, Any]:
    """La puerta declarada en el plan, con y sin los umbrales calibrados (047:RF-36)."""
    if con.get('error') or sin.get('error'):
        return {'cumple': False, 'motivos': [f"error al medir: {con.get('error') or sin.get('error')}"]}
    comparacion = comparar_pareado(sin, con, metrica=METRICA)
    motivos = []
    if float(con['abstention_accuracy']) < ABSTENCION_MINIMA:
        motivos.append(f"abstención {con['abstention_accuracy']:.3f} bajo {ABSTENCION_MINIMA}")
    if float(con['recall@10']) < float(sin['recall@10']):
        motivos.append(f"Recall@10 baja de {sin['recall@10']:.3f} a {con['recall@10']:.3f}")
    if comparacion.get('status') != 'OK':
        motivos.append(f'{METRICA}: sin datos pareados')
    elif comparacion['ci95_bootstrap'][1] < 0:
        motivos.append(f"{METRICA} peor de forma significativa: IC95 % {comparacion['ci95_bootstrap']}")
    return {'cumple': not motivos, 'motivos': motivos, METRICA: comparacion}


def medir_sellado(indice: Any, conjunto: Mapping[str, Any], vector_de: Callable[[str], Sequence[float] | None],
                  puntuar: Callable[[str, Sequence[str]], Sequence[float]], modelo: str,
                  abstencion: modulo_indice.Abstencion) -> dict[str, Any]:
    """Una medición del conjunto sellado: cada método con la abstención calibrada y con la histórica."""
    pares, sin_ancla, _ = resolver_pares(conjunto, indice.frags)
    if sin_ancla:
        raise ValueError(f'preguntas sin ancla en el índice, medir falsearía la comparación: {sin_ancla}')
    vectores = {p.pregunta: vector_de(p.pregunta) for p in pares}
    fallo: list[str] = []

    def reordenador(consulta: str, candidatos: Sequence[Mapping]) -> list[dict]:
        if fallo:
            raise modulo_indice.RerankerNoDisponible(fallo[0])
        try:
            return reordenar(consulta, candidatos, modelo=modelo, revision='', puntuar=puntuar)
        except modulo_indice.RerankerNoDisponible as exc:
            fallo.append(str(exc))
            raise

    reordenador.etiqueta = f'reranker:{modelo}'

    def medir(con_vector: bool, reordena: Any, umbrales: Any) -> dict[str, Any]:
        def buscar(pregunta: str, k: int) -> list[dict]:
            r = modulo_indice.recuperar(indice, pregunta, k, vector=vectores[pregunta] if con_vector else None,
                                        reordenador=reordena, abstencion=umbrales)
            return r['hallados'] if r['sabe'] else []
        return _medir(pares, buscar)

    metodos, puertas = {}, {}
    for nombre, con_vector, reordena in (('reranker', True, reordenador), ('hibrido', True, None), ('bm25', False, None)):
        for sufijo, umbrales in (('', abstencion), ('_sin_puerta', None)):
            medido = medir(con_vector, reordena, umbrales)
            metodos[nombre + sufijo] = {'error': fallo[0]} if reordena is not None and fallo else medido
        puertas[nombre] = _puerta(metodos[nombre], metodos[nombre + '_sin_puerta'])
    if hasattr(puntuar, 'liberar'):
        puntuar.liberar()
    tipo = {_grupo(str(f['pregunta'])): f.get('tipo') for f in conjunto['preguntas']}
    for medido in metodos.values():
        filas = [x for x in medido.get('per_query') or () if not x['answerable']]
        medido['abstencion_por_tipo'] = {t: sum(x['abstained'] for x in filas if tipo[x['group_id']] == t)
                                         / max(sum(tipo[x['group_id']] == t for x in filas), 1)
                                         for t in ('dominio', 'fuera')}
        con = [x for x in medido.get('per_query') or () if x['answerable']]
        medido['con_respuesta_abstenidas'] = sum(not x['ranking'] for x in con)
        if 'per_query' in medido:
            medido['intervalos'] = con_intervalos(medido, tipo)        # 097:RF-15
    return {'esquema': 'csg-abstencion-rag-v1', 'procedencia': conjunto['procedencia'],
            'corpus': getattr(indice, 'corpus', None), 'perdidas_al_medir': conjunto.get('perdidas_al_medir', 0),
            'conjunto_sha256': conjunto['sha256'], 'modelo_reranker': modelo, 'preguntas': len(pares),
            'con_respuesta': sum(p.answerable for p in pares), 'cobertura_vectores': indice.cobertura,
            'abstencion_minima': ABSTENCION_MINIMA, 'metodos': metodos, 'puerta': puertas,
            'cumple_todos': all(x['cumple'] for x in puertas.values())}


# --- 097 T3: elección del modelo de vectores con intervalo, métricas con intervalo y conjunto del operador -----------

_SENALES = ('grupo', 'responde', 'codigo', 'tipo', 'bm25', 'coseno', 'reranker')


def calibracion_con_senales(filas: Sequence[Mapping[str, Any]], objetivo: float = OBJETIVO_CALIBRACION) -> dict[str, Any]:
    """La calibración y, con ella, las señales de cada pregunta sin su texto (097:RF-9): sin ellas no hay intervalo.

    Una señal sin candidatos (-inf) se guarda como ``None``: JSON no tiene infinito y ``_senal`` la devuelve a -inf."""
    def valor(v: Any) -> Any:
        return None if isinstance(v, float) and v == float('-inf') else v
    return {**calibrar(filas, objetivo),
            'por_pregunta': [{k: valor(f.get(k)) for k in _SENALES if k in f} for f in filas]}


def _senal(v: Any) -> float:
    return float('-inf') if v is None else float(v)


def _conserva_hibrido(bm_con: Any, cos_con: Any, bm_sin: Any, cos_sin: Any, objetivo: float) -> float:
    """El par coseno-BM25 de ``calibrar``, vectorizado para remuestrear miles de veces: la mayor fracción de preguntas con
    respuesta que pasa algún umbral, con la abstención objetivo en las que no la tienen."""
    import numpy as np

    if len(bm_con) == 0 or len(bm_sin) == 0:
        return 0.0
    cand = [np.concatenate([np.unique(v[np.isfinite(v)]) + _POR_ENCIMA, [np.inf]]) for v in (bm_sin, cos_sin)]
    ub, uc = cand[0][None, :, None], cand[1][None, None, :]

    def pasan(bm: Any, cos: Any) -> Any:
        return (bm[:, None, None] >= ub) | (cos[:, None, None] >= uc)

    abstiene = 1.0 - pasan(bm_sin, cos_sin).mean(axis=0)
    conserva = pasan(bm_con, cos_con).mean(axis=0)
    conserva[-1, -1] = -1.0                                            # sin ningún umbral no es una calibración
    validos = abstiene >= objetivo - 1e-12
    return float(max(conserva[validos].max(), 0.0)) if validos.any() else 0.0


def _vectores_de_filas(filas: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, tuple[float, float]]]:
    """Por pregunta útil (sin las de código, como ``calibrar``): (bm25, coseno), con y sin respuesta por separado."""
    out: dict[str, dict[str, tuple[float, float]]] = {'con': {}, 'sin': {}}
    for i, f in enumerate(filas):
        if f.get('codigo'):
            continue
        out['con' if f['responde'] else 'sin'][str(f.get('grupo', i))] = (_senal(f.get('bm25')), _senal(f.get('coseno')))
    return out


def _conserva_de(datos: Mapping[str, Mapping[str, tuple[float, float]]], con_ids: Sequence[str], sin_ids: Sequence[str],
                 objetivo: float) -> float:
    import numpy as np

    con = np.asarray([datos['con'][g] for g in con_ids if g in datos['con']], dtype=float).reshape(-1, 2)
    sin = np.asarray([datos['sin'][g] for g in sin_ids if g in datos['sin']], dtype=float).reshape(-1, 2)
    return _conserva_hibrido(con[:, 0], con[:, 1], sin[:, 0], sin[:, 1], objetivo)


def _remuestras(con_ids: Sequence[str], sin_ids: Sequence[str], remuestreos: int, semilla: int):
    """Remuestreo estratificado por pregunta (097:RF-10): con y sin respuesta por separado, como se calibra."""
    rnd = random.Random(semilla)
    for _ in range(remuestreos):
        yield [rnd.choice(con_ids) for _ in con_ids], [rnd.choice(sin_ids) for _ in sin_ids]


def _ic95(muestras: Sequence[float]) -> list[float]:
    orden = sorted(muestras)
    return [orden[int(0.025 * (len(orden) - 1))], orden[int(0.975 * (len(orden) - 1))]] if orden else [0.0, 0.0]


def conserva_con_intervalo(filas: Sequence[Mapping[str, Any]], *, remuestreos: int = 2000, semilla: int = 0,
                           objetivo: float = OBJETIVO_CALIBRACION) -> dict[str, Any]:
    """«Conserva» del híbrido con la abstención objetivo y su IC95 % bootstrap, recalibrando cada vez (097:RF-10).

    Recalibrar en cada remuestreo cuenta también la incertidumbre de fijar el umbral con pocas preguntas, que un umbral
    fijo escondería (Efron y Tibshirani, *An Introduction to the Bootstrap*, 1993, intervalos percentiles)."""
    datos = _vectores_de_filas(filas)
    con_ids, sin_ids = list(datos['con']), list(datos['sin'])
    muestras = [_conserva_de(datos, c, s, objetivo) for c, s in _remuestras(con_ids, sin_ids, remuestreos, semilla)]
    return {'conserva': _conserva_de(datos, con_ids, sin_ids, objetivo), 'ic95': _ic95(muestras),
            'n_con': len(con_ids), 'n_sin': len(sin_ids), 'remuestreos': remuestreos, 'objetivo': objetivo}


#: 097:RF-11: entre los que no se separan, la latencia decide solo si la diferencia pasa de esto; si no, la memoria.
MARGEN_LATENCIA = 0.20
REGLA_ELECCION = ('Compite el modelo con calibración en el 047 y en el 077. Queda fuera el que otro supera en un corpus '
                  'con el IC95 % pareado de la diferencia de «conserva» (híbrido, abstención 0,95) por encima de cero '
                  'sin quedar por debajo en el otro. Entre los que quedan, el de menor p95 de latencia de la consulta '
                  'si la diferencia pasa del 20 %; si no, el de menor memoria de GPU medida (097:RF-11).')


def elegir_con_intervalo(por_corpus: Mapping[str, Mapping[str, Sequence[Mapping[str, Any]]]],
                         recursos: Mapping[str, Mapping[str, float]], *, remuestreos: int = 2000, semilla: int = 0,
                         objetivo: float = OBJETIVO_CALIBRACION) -> dict[str, Any]:
    """La regla declarada de 097:RF-11 sobre las señales de calibración de cada modelo en cada corpus.

    Las diferencias son pareadas: los mismos remuestreos de preguntas para todos los modelos de un corpus."""
    corpus = sorted(por_corpus)
    compiten = sorted(set.intersection(*(set(por_corpus[c]) for c in corpus))) if corpus else []
    detalle: dict[str, Any] = {}
    for c in corpus:
        datos = {m: _vectores_de_filas(por_corpus[c][m]) for m in compiten}
        con_ids = sorted(set.intersection(*(set(d['con']) for d in datos.values()))) if datos else []
        sin_ids = sorted(set.intersection(*(set(d['sin']) for d in datos.values()))) if datos else []
        muestras: dict[str, list[float]] = {m: [] for m in compiten}
        for cs, ss in _remuestras(con_ids, sin_ids, remuestreos, semilla):
            for m in compiten:
                muestras[m].append(_conserva_de(datos[m], cs, ss, objetivo))
        detalle[c] = {'modelos': {m: {'conserva': _conserva_de(datos[m], con_ids, sin_ids, objetivo),
                                      'ic95': _ic95(muestras[m])} for m in compiten},
                      'diferencias': {f'{a} - {b}': _ic95([x - y for x, y in zip(muestras[a], muestras[b], strict=True)])
                                      for a in compiten for b in compiten if a != b},
                      'n_con': len(con_ids), 'n_sin': len(sin_ids)}
    fuera: dict[str, str] = {}
    for m in compiten:
        for o in compiten:
            if o == m:
                continue
            gana = [c for c in corpus if detalle[c]['diferencias'][f'{o} - {m}'][0] > 0]
            pierde = [c for c in corpus if detalle[c]['diferencias'][f'{o} - {m}'][1] < 0]
            if gana and not pierde:
                fuera[m] = f'{o} lo supera en {", ".join(gana)} con el IC95 % pareado sobre cero'
                break
    quedan = [m for m in compiten if m not in fuera]
    elegido, motivo = None, 'ningún modelo compite: falta la calibración de algún corpus'
    if quedan:
        lat = {m: float(recursos.get(m, {}).get('latencia_p95_ms', float('inf'))) for m in quedan}
        mejor = min(lat.values())
        cerca = [m for m in quedan if lat[m] <= mejor * (1 + MARGEN_LATENCIA)]
        elegido = min(cerca, key=lambda m: (float(recursos.get(m, {}).get('memoria_gpu_mib', float('inf'))), lat[m], m))
        motivo = ('único que queda' if len(quedan) == 1 else 'latencia p95 de la consulta' if len(cerca) == 1
                  else 'memoria de GPU, con la latencia a menos del 20 %')
    return {'regla': REGLA_ELECCION, 'compiten': compiten, 'fuera': fuera, 'quedan': quedan, 'elegido': elegido,
            'decide': motivo, 'por_corpus': detalle, 'recursos': {m: dict(recursos.get(m, {})) for m in compiten},
            'remuestreos': remuestreos, 'semilla': semilla, 'objetivo': objetivo}


_METRICAS_IC = {'recall@1': 'recall@1', 'recall@5': 'recall@5', 'recall@10': 'recall@10', 'mrr@10': 'reciprocal_rank@10',
                'ndcg@10': 'ndcg@10', 'exact_citation@1': 'exact_citation@1', 'hit@10': 'hit@10'}   # 097:RF-23


def _con_ic(valores: Sequence[float], remuestreos: int, rnd: random.Random,
            estadistico: Callable[[Sequence[float]], float] | None = None) -> dict[str, Any]:
    estadistico = estadistico or (lambda xs: sum(xs) / len(xs))
    if not valores:
        return {'valor': None, 'ic95': [None, None], 'n': 0}
    muestras = [estadistico([rnd.choice(valores) for _ in valores]) for _ in range(remuestreos)]
    return {'valor': estadistico(list(valores)), 'ic95': _ic95(muestras), 'n': len(valores)}


def con_intervalos(medido: Mapping[str, Any], tipo_de: Mapping[str, Any], *, remuestreos: int = 2000,
                   semilla: int = 0) -> dict[str, Any]:
    """Cada métrica de recuperación con su IC95 % bootstrap por pregunta, también por tipo de pregunta (097:RF-15).

    Las métricas son las de BEIR y MTEB (nDCG@10 como principal, MRR@10, Recall@k); la unidad que se remuestrea es la
    pregunta, como en ``comparar_pareado``."""
    rnd = random.Random(semilla)
    filas = [x for x in medido.get('per_query') or () if x.get('answerable')]
    sin = [x for x in medido.get('per_query') or () if not x.get('answerable')]

    def bloque(fs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {m: _con_ic([float(f[c]) for f in fs if c in f], remuestreos, rnd)
                               for m, c in _METRICAS_IC.items()}
        out['n'] = len(fs)
        return out

    glob = bloque(filas)
    glob['latencia_p95_ms'] = _con_ic([float(x) for x in medido.get('latencias_ms') or ()], remuestreos, rnd, _p95)
    if sin:
        glob['abstencion'] = _con_ic([float(bool(x.get('abstained'))) for x in sin], remuestreos, rnd)
    tipos = sorted({str(tipo_de.get(f['group_id'])) for f in filas})
    return {'global': glob, 'remuestreos': remuestreos,
            'por_tipo': {t: bloque([f for f in filas if str(tipo_de.get(f['group_id'])) == t]) for t in tipos}}


#: 097:RF-16: las preguntas que el operador hizo al asistente desde la web, con su ancla puesta por el maestro.
PROCEDENCIA_OPERADOR = 'operador_web'


def cargar_conjunto_operador(ruta: Path) -> dict[str, Any]:
    """El conjunto de preguntas reales del operador, con su sello; rechaza el sintético (097:RF-16, 027:RF-42)."""
    datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    if datos.get('procedencia') != PROCEDENCIA_OPERADOR:
        raise ValueError(f'el conjunto del operador debe declarar procedencia {PROCEDENCIA_OPERADOR!r}')
    if any(f.get('origen') != 'operador' for f in datos.get('preguntas') or ()):
        raise ValueError('cada pregunta del conjunto del operador lleva origen «operador»')
    return {**datos, 'sha256': sha256_de(ruta)}


def por_procedencia(partes: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Lo medido de cada procedencia por separado, nunca sumado (097:RF-17, como 085:RF-23)."""
    ajenas = set(partes) - {'sintetico', 'operador'}
    if ajenas:
        raise ValueError(f'solo se informan las procedencias por separado, sin agregados: {sorted(ajenas)}')
    return {k: dict(v) for k, v in partes.items()}
