"""Evaluación sellada de la recuperación: BM25, híbrido y reranker con las mismas preguntas (047:RF-4).

El conjunto es sintético del maestro de sesión, sobre fragmentos reales del índice: sirve para
contrastar métodos, nunca para acreditar órdenes de operadores (027:RF-42). La política de adopción
se declaró en el plan de la 047 antes de medir, y ``decidir`` la aplica sin ajustarse a lo medido.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from . import indice as modulo_indice
from .embeddings import ParContraste, comparar_pareado, evaluar_recuperador
from .reranker import reordenar, sha256_de

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


def resolver_pares(conjunto: Mapping[str, Any], frags: Sequence[Any]) -> tuple[list[ParContraste], list[str], set[str]]:
    """Cada pregunta con los fragmentos reales que la responden, las que perdieron su ancla y las de código.

    Va por fichero y comienzo del texto, no por línea: una línea se mueve con cualquier edición ajena.
    """
    por_fichero: dict[str, list[Any]] = {}
    for f in frags:
        por_fichero.setdefault(str(f.fuente).rsplit(':', 1)[0], []).append(f)
    pares, sin_ancla, codigos = [], [], set()
    for fila in conjunto['preguntas']:
        pregunta, grupo = str(fila['pregunta']), _grupo(str(fila['pregunta']))
        if fila.get('sin_respuesta') is True:
            pares.append(ParContraste(pregunta, (), (), False, grupo))
            continue
        positivos = tuple(str(f.fuente) for f in por_fichero.get(str(fila['fichero']), ())
                          if str(f.texto).startswith(str(fila['ancla'])))
        if not positivos:
            sin_ancla.append(pregunta)
            continue
        pares.append(ParContraste(pregunta, positivos, (), True, grupo))
        if fila.get('tipo') == 'codigo':
            codigos.add(grupo)
    return pares, sin_ancla, codigos


def _medir(pares: Sequence[ParContraste], buscar: Callable[[str, int], Sequence[Any]]) -> dict[str, Any]:
    latencias: list[float] = []

    def cronometrado(pregunta: str, k: int) -> Sequence[Any]:
        inicio = time.perf_counter()
        salida = buscar(pregunta, k)
        latencias.append((time.perf_counter() - inicio) * 1000.0)
        return salida

    metricas = evaluar_recuperador(pares, cronometrado)
    orden = sorted(latencias)
    metricas['latencia_p95_ms'] = orden[min(len(orden) - 1, int(0.95 * len(orden)))] if orden else 0.0
    return metricas


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
    if decision['reranker']['modelo'] and revisiones:
        decision['reranker']['revision'] = revisiones.get(decision['reranker']['modelo'])
    return {'esquema': 'csg-evaluacion-rag-v1', 'procedencia': conjunto['procedencia'],
            'conjunto_sha256': conjunto['sha256'], 'metrica_primaria': METRICA,
            'preguntas': len(pares), 'con_respuesta': sum(p.answerable for p in pares),
            'cobertura_vectores': indice.cobertura, 'metodos': metodos, 'decision': decision}


#: La puerta y el margen de calibración, declarados en el plan de la 047 antes de medir.
ABSTENCION_MINIMA = 0.90
OBJETIVO_CALIBRACION = 0.95
_POR_ENCIMA = 1e-6


def leer_puntuaciones(indice: Any, conjunto: Mapping[str, Any], vector_de: Callable[[str], Sequence[float] | None],
                      puntuar: Callable[[str, Sequence[str]], Sequence[float]], modelo: str) -> list[dict[str, Any]]:
    """La mejor señal de cada método en cada pregunta, por la misma búsqueda que la respuesta."""
    pares, sin_ancla, _ = resolver_pares(conjunto, indice.frags)
    if sin_ancla:
        raise ValueError(f'preguntas sin ancla en el índice, calibrar con ellas falsearía el umbral: {sin_ancla}')
    filas = []
    for par in pares:
        candidatos = indice.buscar(par.pregunta, modulo_indice.CANDIDATOS, vector_de(par.pregunta))
        puntuados = reordenar(par.pregunta, candidatos, modelo=modelo, revision='', puntuar=puntuar) if candidatos else []
        filas.append({'responde': par.answerable, 'codigo': indice.nombra_codigo(par.pregunta, candidatos),
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
    return {'esquema': 'csg-abstencion-rag-v1', 'procedencia': conjunto['procedencia'],
            'conjunto_sha256': conjunto['sha256'], 'modelo_reranker': modelo, 'preguntas': len(pares),
            'con_respuesta': sum(p.answerable for p in pares), 'cobertura_vectores': indice.cobertura,
            'abstencion_minima': ABSTENCION_MINIMA, 'metodos': metodos, 'puerta': puertas,
            'cumple_todos': all(x['cumple'] for x in puertas.values())}

