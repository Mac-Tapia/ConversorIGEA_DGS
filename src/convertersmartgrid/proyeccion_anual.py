"""Proyección de la demanda para todos los años del PIDE, con el mejor modelo por métricas (spec 031).

Una capa aparte de la 089: las curvas de 28 días no se extrapolan en silencio a años, y la tasa del perfil no sustituye a lo medido.
Cada candidato ve solo lo anterior a su origen y se mide contra lo ocurrido, mes a mes. Se mide por meses porque la cabecera real trae
22 meses, no años: con ellos, un año incompleto sumado contra uno entero parecía una caída de la demanda.

Solo emite ficheros; no escribe en la calibración, el «Caso base» ni DIgSILENT (RF-14).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
from typing import Any

import numpy as np

from .demanda_medida import clave_codigo, normalizar
from .digital_twin.pronostico import Objetivo
from .pide import PideError, leer_json_con_huella, leer_proyeccion_anual
from .pronostico_demanda import (
    CON_TEMPERATURA,
    HISTORIA_MINIMA_DIAS,
    PUERTA,
    Dataset,
    Exogenas,
    Fuentes,
    armar_dataset,
    arreglos,
    error_de_maxima,
    fabrica_modelo,
    guardar_dataset,
    huella_de_objetivos,
    malla,
    medir,
    predecir,
    sin_infinitos,
)
from .pronostico_demanda import METODOS as METODOS_089
from .proyeccion_mercado import METODOS as METODOS_ANUALES
from .proyeccion_mercado import REFERENCIA, MercadoError, SerieMercado, comparar_metodos, leer_formato_01, perfiles_distintos
from .runtime_paths import staging_publicacion

CLASES, MAGNITUDES = ('cliente', 'escaladas'), ('kW', 'kVAR')
#: Sin crecimiento: lo que queda de referencia si la historia no alcanza ni para comparar dos años.
REFERENCIA_SIN_DOS_ANIOS = 'sin_crecimiento'
#: Un mes con menos de la mitad de sus registros no es un mes medido: la limpieza de la 089 quita cortes y medidores congelados.
COBERTURA_MES = .5
#: Un horizonte con un solo origen es una anécdota: dos como mínimo para decir que se midió.
MIN_ORIGENES = 2
MIN_ERRORES_BANDA = 8
#: Una tasa de un alimentador real salió en 16,5 %/año (042:RF-86): por encima de este factor se avisa, no se recorta.
FACTOR_DE_AVISO = 3.0
#: Instantes más altos del alimentador en que se busca el dato de cada carga: unos diez días de máximas.
INSTANTES_DE_MAXIMA = 1000

#: 031:RF-4 — fijada antes de la primera medición y escrita en la evaluación antes de medir. Cambiarla exige otra versión.
REGLA = {'version': 1,
         'metrica': 'WAPE de la demanda media mensual, ponderado por energía, en los orígenes de elección',
         'mejora_minima': PUERTA['mejora_wape'], 'maxima_no_peor': True,
         'referencia': REFERENCIA, 'referencia_sin_dos_anios': REFERENCIA_SIN_DOS_ANIOS,
         'desempate': 'el menor WAPE; si ninguno pasa la puerta, gana la referencia',
         'prueba': 'el último tercio de los orígenes comunes no elige: solo informa',
         'validado': f'un año se da por validado con {MIN_ORIGENES} orígenes o más que midan sus 12 meses, en la mitad de las series',
         'cobertura_minima_mes': COBERTURA_MES, 'origenes_minimos': MIN_ORIGENES}


class ProyeccionError(ValueError):
    """Falta un dato que la proyección exige: se dice cuál, no se supone."""


# --------------------------------------------------------------------------- meses
def _mes(t) -> np.ndarray:
    return np.asarray(t, dtype='datetime64[M]').astype(int)


def _inicio(mes: int) -> np.datetime64:
    return np.datetime64(int(mes), 'M').astype('datetime64[ns]')


def _anio(mes: int) -> int:
    return 1970 + int(mes) // 12


def _calendario(mes: int) -> int:
    return int(mes) % 12 + 1


def _registros_del_mes(mes: int) -> int:
    return int((np.datetime64(int(mes) + 1, 'M') - np.datetime64(int(mes), 'M')).astype('timedelta64[D]').astype(int)) * 96


@dataclass
class SerieMensual:
    """Los meses medidos de un objetivo: su demanda media, su máxima y la parte de sus registros."""

    media: dict[int, float]
    maxima: dict[int, float]
    cobertura: dict[int, float]


def serie_mensual(t: np.ndarray, y: np.ndarray) -> SerieMensual:
    """Solo los meses con registros suficientes (031:RF-3): sin rellenar, lo que falta no se compara."""
    salida = SerieMensual({}, {}, {})
    ok = np.isfinite(y)
    t, y = t[ok], y[ok]
    if not len(t):
        return salida
    meses = _mes(t)
    cambios = np.r_[0, np.flatnonzero(np.diff(meses)) + 1, len(t)]
    for a, b in zip(cambios[:-1], cambios[1:], strict=True):
        mes = int(meses[a])
        cobertura = (b - a) / _registros_del_mes(mes)
        if cobertura >= COBERTURA_MES:
            salida.media[mes], salida.maxima[mes], salida.cobertura[mes] = float(y[a:b].mean()), float(y[a:b].max()), float(cobertura)
    return salida


@dataclass
class _Serie:
    objetivo: Objetivo
    t: np.ndarray
    y: np.ndarray
    meses: SerieMensual

    @property
    def nombre(self) -> str:
        return self.objetivo.nombre


def _serie(o: Objetivo) -> _Serie:
    t, y = arreglos(o)
    return _Serie(o, t, y, serie_mensual(t, y))


def historia_del_grupo(series: Iterable[_Serie], origen: int | None = None) -> dict[str, dict[int, float]]:
    """La demanda de cada año de una clase, con las mismas series y los mismos meses en todos (031:RF-15).

    Diez meses de un año contra los doce del anterior parecían una caída del 17 %; un cliente nuevo, un salto. Y el crecimiento es
    del grupo, no de cada serie: medido en un sistema real, la tasa de un cliente con un escalón multiplicaba por más de cien mil su demanda a
    20 años, y la suma pasaba de 78 MW a cifras sin sentido. Solo la serie de cada carga da su nivel.
    """
    salida: dict[str, dict[int, float]] = {}
    for campo in ('media', 'maxima'):
        por_anio: dict[int, dict[tuple[str, int], float]] = {}
        for x in series:
            for m, v in getattr(x.meses, campo).items():
                if origen is None or m <= origen:
                    por_anio.setdefault(_anio(m), {})[(x.nombre, _calendario(m))] = v
        anios = sorted(por_anio)
        salida[campo] = {}
        while anios:
            comunes = set.intersection(*(set(por_anio[a]) for a in anios))
            if comunes:
                salida[campo] = {a: float(sum(por_anio[a][k] for k in comunes)) for a in anios}
                break
            anios = anios[1:]                                # el año más viejo no comparte nada con los demás
    return salida


# --------------------------------------------------------------------------- candidatos
def _razones_anuales(metodo: str, hist: Mapping[int, float], hasta: int) -> dict[int, float]:
    """Lo que proyecta un método anual, para el factor sobre el año base. ``MercadoError`` si no le alcanza."""
    if not hist:
        raise MercadoError('sin años comparables')
    if any(v <= 0 for v in hist.values()):
        raise MercadoError('un año sin demanda positiva no da tasa')      # la Q cruza el cero con los bancos
    ultimo = max(hist)
    return dict(METODOS_ANUALES[metodo](dict(hist), ultimo, range(ultimo, hasta + 1)))


def _predecir_anual(metodo: str, s: SerieMensual, origen: int, futuros: Sequence[int], historia: Mapping[str, Mapping[int, float]]) -> dict[int, tuple[float, float]] | None:
    """El mismo mes de su último año por el crecimiento del grupo que da el método, en demanda media y en máxima.

    «Sin crecimiento» es repetir el último valor: con los dos años de la cabecera real, anclarlo al año en curso lo hacía idéntico a
    la tasa en todos los orígenes, y entonces la competición no distinguía nada.
    """
    salida: dict[int, list[float]] = {m: [] for m in futuros}
    for campo, valores in (('media', s.media), ('maxima', s.maxima)):
        visibles = {m: v for m, v in valores.items() if m <= origen}
        if not visibles:
            return None
        razones, hist = {}, historia[campo]
        if metodo != REFERENCIA_SIN_DOS_ANIOS:
            try:
                razones = _razones_anuales(metodo, hist, _anio(max(futuros)))
            except MercadoError:
                return None
        por_calendario: dict[int, int] = {}
        for m in sorted(visibles):
            por_calendario[_calendario(m)] = m
        nivel = statistics.fmean(visibles.values())
        for m in futuros:
            previo = por_calendario.get(_calendario(m))
            base = visibles[previo] if previo is not None else nivel
            if metodo == REFERENCIA_SIN_DOS_ANIOS:
                salida[m].append(base)
                continue
            de = _anio(previo) if previo is not None else max(hist)
            salida[m].append(base * razones[_anio(m)] / hist.get(de, hist[max(hist)]))
    return {m: (v[0], v[1]) for m, v in salida.items()}


def _agregar_curva(futuro: np.ndarray, p: np.ndarray, futuros: Sequence[int]) -> dict[int, tuple[float, float]]:
    meses = _mes(futuro)
    salida = {}
    for m in futuros:
        a, b = np.searchsorted(meses, [m, m + 1])
        if b > a:
            salida[m] = (float(np.mean(p[a:b])), float(np.max(p[a:b])))
    return salida


def _predecir_perfil(metodo: str, s: _Serie, origen: int, futuros: Sequence[int], exogenas: Exogenas | None) -> dict[int, tuple[float, float]] | None:
    """Los métodos de la 089 sobre la malla de 15 minutos del futuro, resumidos por mes."""
    corte = _inicio(origen + 1)
    antes = s.t < corte
    if not antes.any() or corte - s.t[antes][0] < np.timedelta64(HISTORIA_MINIMA_DIAS, 'D'):
        return None
    futuro = malla(corte - np.timedelta64(15, 'm'), _inicio(max(futuros) + 1) - np.timedelta64(15, 'm'))
    return _agregar_curva(futuro, predecir(metodo, s.t[antes], s.y[antes], futuro, exogenas), futuros)


def _familia(nombre: str) -> str:
    if nombre in METODOS_ANUALES:
        return 'anual'
    return 'perfil' if nombre in (*METODOS_089, CON_TEMPERATURA) else 'modelo'


def _medir_grupo(pares: Sequence[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]) -> dict[str, Any]:
    """WAPE, RMSE relativo, sesgo y error de la máxima de unas predicciones (031:RF-3), con las medidas de la 089."""
    pares = [p for p in pares if len(p[0])]
    if not pares:
        return {'wape': float('inf'), 'rmse_relativo': float('inf'), 'sesgo': float('nan'), 'sesgo_relativo': float('nan'),
                'error_maxima': float('inf'), 'n': 0}
    medida = medir(np.concatenate([p[0] for p in pares]), np.concatenate([p[1] for p in pares]))
    maximas = [x for x in (error_de_maxima(p[2], p[3]) for p in pares) if math.isfinite(x)]
    return {'wape': medida['wape'], 'rmse_relativo': medida['rmse_relativo'], 'sesgo': medida['sesgo'],
            'sesgo_relativo': medida['sesgo'] * medida['n'] / medida['energia'] if medida.get('energia') else float('nan'),
            'error_maxima': float(np.median(maximas)) if maximas else float('inf'), 'n': medida['n']}


def _pares(pred: Mapping[tuple[str, int], Mapping[int, tuple[float, float]]], series: Mapping[str, _Serie], claves: Iterable[tuple[str, int]],
           dejar: Callable[[int, int], bool] = lambda _o, _m: True) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Real y predicho de cada ``(objetivo, origen)``, con los meses que deja pasar ``dejar(origen, mes)``."""
    salida = []
    for nombre, origen in claves:
        p = pred.get((nombre, origen))
        if p is None:
            continue
        meses = [m for m in sorted(p) if dejar(origen, m)]
        s = series[nombre].meses
        salida.append((np.array([s.media[m] for m in meses]), np.array([p[m][0] for m in meses]),
                       np.array([s.maxima[m] for m in meses]), np.array([p[m][1] for m in meses])))
    return salida


def _por_horizonte(pred, series) -> tuple[dict[str, dict], dict[str, dict]]:
    """Cada métrica a cada horizonte que los datos permitan: por mes adelante y por año adelante (031:RF-3)."""
    horizontes = sorted({m - o for (_n, o), p in pred.items() for m in p})
    por_mes = {str(h): _medir_grupo(_pares(pred, series, pred, lambda o, m, h=h: m - o == h)) for h in horizontes}
    anios = sorted({(h - 1) // 12 + 1 for h in horizontes})
    por_anio = {str(k): _medir_grupo(_pares(pred, series, pred, lambda o, m, k=k: (m - o - 1) // 12 + 1 == k)) for k in anios}
    return por_mes, por_anio


def _validacion(pred, series) -> dict[str, Any]:
    """Años y meses medidos de verdad (031:RF-6): un año, solo si varios orígenes miden sus 12 meses en la mitad de las series."""
    por_origen: dict[int, list[tuple[str, Mapping]]] = {}
    for (nombre, origen), p in pred.items():
        por_origen.setdefault(origen, []).append((nombre, p))
    horizontes = sorted({m - o for (_n, o), p in pred.items() for m in p})
    meses = 0
    for h in horizontes:
        if sum(any(o + h in p for _n, p in filas) for o, filas in por_origen.items()) >= MIN_ORIGENES and h == meses + 1:
            meses = h
    anios, por_anio = 0, {}
    for k in range(1, (max(horizontes) - 1) // 12 + 2 if horizontes else 1):
        completos = 0
        for origen, filas in por_origen.items():
            bastan = sum(all(origen + 12 * (k - 1) + d in p for d in range(1, 13)) for _n, p in filas)
            completos += bastan >= max(1, len(filas) / 2)
        por_anio[str(k)] = completos
        if completos >= MIN_ORIGENES and anios == k - 1:
            anios = k
    return {'anios': anios, 'meses': meses, 'origenes_con_el_anio_entero': por_anio}


def _banda(pred, series) -> dict[str, dict]:
    """Cuantiles del error relativo de la máxima mensual, por año adelante (031:RF-5): la banda sale de lo medido, no de una fórmula."""
    errores: dict[int, list[float]] = {}
    for (nombre, origen), p in pred.items():
        reales = series[nombre].meses.maxima
        for m, (_media, maxima) in p.items():
            if abs(maxima) > 1e-9:
                errores.setdefault((m - origen - 1) // 12 + 1, []).append((reales[m] - maxima) / abs(maxima))
    return {str(k): {'q05': float(np.quantile(v, .05)), 'q95': float(np.quantile(v, .95)), 'n': len(v)} for k, v in sorted(errores.items())}


def _factor_primer_anio(media_max: Mapping[int, tuple[float, float]], s: SerieMensual) -> float:
    """Lo que el método da para los próximos 12 meses frente a los 12 últimos medidos, en la máxima."""
    ultimos = sorted(s.maxima)[-12:]
    base = max((s.maxima[m] for m in ultimos), default=0.0)
    previsto = max((x[1] for x in media_max.values()), default=0.0)
    return previsto / base if base > 0 and previsto > 0 else 1.0


def _competir_grupo(objetivos: Sequence[Objetivo], candidatos: Sequence[str], modelos: Sequence[str], *, paso_meses: int, semilla: int,
                    exogenas: Exogenas | None, ajustes: Mapping | None, fabrica: Callable, log: Callable) -> dict[str, Any]:
    """Todos los candidatos en una clase y magnitud, sobre los mismos datos y orígenes (031:RF-2 a RF-4)."""
    series = {s.nombre: s for s in (_serie(o) for o in objetivos) if s.meses.media}
    resultado: dict[str, Any] = {'objetivos': len(series), 'regla_version': REGLA['version'], 'candidatos': {}, 'historia_anual': historia_del_grupo(series.values())}
    if not series:
        return {**resultado, 'status': 'HISTORIA_INSUFICIENTE', 'ganador': REFERENCIA_SIN_DOS_ANIOS, 'motivo': 'ningún objetivo con meses medidos',
                'validacion': {'anios': 0, 'meses': 0, 'origenes_con_el_anio_entero': {}}, 'banda': {}, 'factor_primer_anio': {}}
    ultimo = max(max(s.meses.media) for s in series.values())
    primero = min(min(s.meses.media) for s in series.values())
    origenes = list(range(ultimo - 1, primero - 1, -max(1, paso_meses)))[::-1]
    pred: dict[str, dict] = {c: {} for c in (*candidatos, *modelos)}
    estados: dict[str, dict] = {c: {'status': 'EVALUADO', 'familia': _familia(c)} for c in pred}
    historias = {origen: historia_del_grupo(series.values(), origen) for origen in origenes}
    for nombre, s in series.items():
        observados = sorted(s.meses.media)
        for origen in origenes:
            futuros = [m for m in observados if m > origen]
            if not futuros or observados[0] > origen:
                continue
            for c in candidatos:
                p = _predecir_anual(c, s.meses, origen, futuros, historias[origen]) if c in METODOS_ANUALES else _predecir_perfil(c, s, origen, futuros, exogenas)
                if p:
                    pred[c][(nombre, origen)] = {m: p[m] for m in futuros if m in p}
    log(f'{len(series)} objetivos y {len(origenes)} orígenes medidos')
    finales: dict[str, dict] = {}
    for c in modelos:
        try:
            finales[c] = _competir_modelo(c, series, origenes, pred[c], semilla=semilla, exogenas=exogenas, ajustes=ajustes, fabrica=fabrica, log=log)
        except Exception as exc:  # noqa: BLE001 - la librería lanza Exception a secas; un modelo roto o sin GPU no se lleva a los demás (089:RF-61)
            pred[c] = {}
            estados[c] = {'status': 'NO_DISPONIBLE', 'familia': 'modelo', 'motivo': f'{type(exc).__name__}: {exc}'[:300]}
            log(f'{c}: no disponible ({exc})')
    # Un candidato sin predicciones o con muy pocos orígenes no compite: no puede estrechar la comparación de los demás a casi nada.
    aplicables = [c for c in pred if len({o for _n, o in pred[c]}) > MIN_ORIGENES]
    for c in pred:
        if c not in aplicables and estados[c]['status'] == 'EVALUADO':
            estados[c] = {'status': 'NO_APLICA', 'familia': _familia(c), 'motivo': f'no alcanza {MIN_ORIGENES + 1} orígenes con esta historia'}
    referencia = REFERENCIA if REFERENCIA in aplicables else REFERENCIA_SIN_DOS_ANIOS
    resultado.update(referencia=referencia)
    comunes = _claves_comunes(pred, aplicables, referencia)
    origenes_comunes = sorted({o for _n, o in comunes})
    for c in pred:
        if pred[c]:
            por_mes, por_anio = _por_horizonte(pred[c], series)
            estados[c].update(por_horizonte_meses=por_mes, por_anio=por_anio, origenes=len({o for _n, o in pred[c]}), validacion=_validacion(pred[c], series))
    resultado['candidatos'] = estados
    if len(origenes_comunes) < 2:
        return {**resultado, 'status': 'HISTORIA_INSUFICIENTE', 'ganador': referencia, 'motivo': 'no hay dos orígenes comunes: queda la referencia',
                'validacion': _validacion(pred.get(referencia) or {}, series), 'banda': _banda(pred.get(referencia) or {}, series),
                'factor_primer_anio': _factores_finales(referencia, series, ultimo, finales, exogenas)}
    i = max(1, (2 * len(origenes_comunes)) // 3)
    corte = origenes_comunes[i] if i < len(origenes_comunes) else origenes_comunes[-1]
    eleccion_origenes = [o for o in origenes_comunes if o < corte]
    claves_eleccion = [k for k in comunes if k[1] < corte]
    claves_prueba = [k for k in comunes if k[1] == corte]
    eleccion = {c: _medir_grupo(_pares(pred[c], series, claves_eleccion, lambda _o, m: m <= corte)) for c in aplicables}
    prueba = {c: _medir_grupo(_pares(pred[c], series, claves_prueba, lambda _o, m: m > corte)) for c in aplicables}
    ganador, motivo, puertas = elegir(eleccion, referencia)
    for c in aplicables:
        estados[c].update(eleccion=eleccion[c], prueba=prueba[c], puerta=puertas.get(c))
    return {**resultado, 'status': 'EVALUADO', 'ganador': ganador, 'motivo': motivo,
            'origenes_eleccion': [_rotulo(o) for o in eleccion_origenes], 'origen_prueba': _rotulo(corte), 'meses_de_prueba_hasta': _rotulo(ultimo),
            'validacion': _validacion(pred[ganador], series), 'banda': _banda(pred[ganador], series),
            'factor_primer_anio': _factores_finales(ganador, series, ultimo, finales, exogenas)}


def _rotulo(mes: int) -> str:
    return f'{_anio(mes)}-{_calendario(mes):02d}'


def _claves_comunes(pred: Mapping[str, dict], aplicables: list[str], referencia: str) -> set[tuple[str, int]]:
    """Las mismas series y orígenes para todos (RF-2); si no hay ninguna, sale el que menos cubre, nunca la referencia."""
    vivos = list(aplicables)
    while vivos:
        comunes = set.intersection(*(set(pred[c]) for c in vivos))
        if comunes:
            return comunes
        sobran = [c for c in vivos if c != referencia]
        if not sobran:
            break
        vivos.remove(min(sobran, key=lambda c: len(pred[c])))
    return set()


def elegir(eleccion: Mapping[str, Mapping[str, float]], referencia: str) -> tuple[str, str, dict[str, dict]]:
    """La regla de ``REGLA``, sobre los orígenes de elección (031:RF-4); sin mejora, la referencia."""
    base = eleccion.get(referencia)
    if base is None or not math.isfinite(base['wape']):
        return referencia, 'la referencia no se pudo medir: queda ella, sin más evidencia', {}
    puertas = {}
    for c, m in eleccion.items():
        if c != referencia:
            puertas[c] = {'wape': m['wape'] <= base['wape'] * (1 - REGLA['mejora_minima']), 'maxima': m['error_maxima'] <= base['error_maxima']}
    pasan = [c for c, p in puertas.items() if all(p.values())]
    if not pasan:
        return referencia, f'ningún candidato mejora a {referencia} según la regla: gana la referencia', puertas
    ganador = min(pasan, key=lambda c: (eleccion[c]['wape'], c))
    return ganador, f"{ganador} mejora a {referencia}: WAPE {eleccion[ganador]['wape']:.4f} frente a {base['wape']:.4f}", puertas


def _competir_modelo(nombre: str, series, origenes, destino: dict, *, semilla: int, exogenas, ajustes, fabrica, log) -> dict[str, dict]:
    """Un modelo global de la clase y magnitud, reentrenado en cada origen sin ver el futuro; devuelve lo que da tras el último dato."""
    meses_finales = 12
    objetos = [s.objetivo for s in series.values()]
    modelo_final: dict[str, dict] = {}
    for origen in (*origenes, None):
        hasta_mes = max(max(s.meses.media) for s in series.values()) if origen is None else origen
        hasta = _inicio(hasta_mes + 1) - np.timedelta64(15, 'm')
        vivos = [s for s in series.values() if s.t[0] <= hasta]
        if origen is None:
            futuros_de = {s.nombre: list(range(hasta_mes + 1, hasta_mes + 1 + meses_finales)) for s in vivos}
        else:
            futuros_de = {s.nombre: [m for m in sorted(s.meses.media) if m > origen] for s in vivos}
            vivos = [s for s in vivos if futuros_de[s.nombre]]
        if not vivos:
            continue
        fin = max(max(futuros_de[s.nombre]) for s in vivos)
        pasos = int((_inicio(fin + 1) - _inicio(hasta_mes + 1)) / np.timedelta64(15, 'm'))
        modelo = fabrica(nombre, semilla=semilla, **dict(ajustes or {}))
        objs = [o for o in objetos if o.nombre in {s.nombre for s in vivos}]
        try:
            modelo.ajustar(objs, hasta, pasos, exogenas, semilla)
        except ValueError as exc:                    # en los primeros orígenes ninguna serie llega a su historia mínima: ese origen no cuenta
            log(f'{nombre}: {"emisión" if origen is None else "origen " + _rotulo(origen)} sin entrenar ({exc})')
            continue
        futuro = malla(hasta, hasta + np.timedelta64(pasos * 15, 'm'))
        for clave, p in modelo.predecir_todos(objs, hasta, pasos, exogenas).items():
            if origen is None:
                modelo_final[clave] = _agregar_curva(futuro, np.asarray(p, dtype=float), futuros_de[clave])
            else:
                destino[(clave, origen)] = _agregar_curva(futuro, np.asarray(p, dtype=float), futuros_de[clave])
        del modelo
        log(f'{nombre}: {"emisión" if origen is None else "origen " + _rotulo(origen)} listo')
    return modelo_final


def _factores_finales(ganador: str, series, ultimo: int, finales: Mapping[str, dict], exogenas) -> dict[str, float]:
    """031:RF-5: los perfiles y modelos dan el año que sigue; los métodos anuales traen su crecimiento y no pasan por aquí."""
    if _familia(ganador) == 'anual':
        return {}
    salida = {}
    for nombre, s in series.items():
        ultimo_s = max(s.meses.media)
        if _familia(ganador) == 'perfil':
            p = _predecir_perfil(ganador, s, ultimo_s, list(range(ultimo_s + 1, ultimo_s + 13)), exogenas)
        else:
            p = (finales.get(ganador) or {}).get(nombre)
        salida[nombre] = _factor_primer_anio(p, s.meses) if p else 1.0
    return salida


def formato_01_propio(series: Iterable[SerieMercado], *, empresa: str | None, sistemas: Iterable[str] | None = None) -> tuple[list[SerieMercado], list[str]]:
    """Solo el histórico de esta empresa y de estos sistemas (031:RF-8).

    El Formato 01 de otra distribuidora es del mismo aspecto: sin decirlo, sus años validarían una proyección ajena.
    """
    propias, notas = [], []
    pedidos = None if sistemas is None else {normalizar(x) for x in sistemas}
    for s in series:
        if not empresa or not s.empresa or normalizar(s.empresa) != normalizar(empresa):
            notas.append(f'{s.codigo or s.nombre}: el Formato 01 es de «{s.empresa or "sin empresa"}», no de la empresa del estudio; no se usa')
        elif pedidos is not None and not {normalizar(s.codigo), normalizar(s.nombre)} & pedidos:
            notas.append(f'{s.codigo or s.nombre}: no es un sistema del estudio; no se usa')
        else:
            propias.append(s)
    return propias, notas


def medir_formato_01(series: Sequence[SerieMercado]) -> dict[str, Any]:
    """Cada método anual a cada año adelante, cortando la historia completa de la empresa (031:RF-3, RF-8)."""
    errores: dict[str, dict[int, list[tuple[float, float]]]] = {m: {} for m in METODOS_ANUALES}
    cortes: dict[str, dict[int, int]] = {m: {} for m in METODOS_ANUALES}
    for s in perfiles_distintos(x for x in series if x.historico):
        anios = sorted(s.historico)
        for corte in anios[2:-1]:
            visible = {a: v for a, v in s.historico.items() if a <= corte}
            futuros = [a for a in anios if a > corte]
            for nombre, metodo in METODOS_ANUALES.items():
                pronostico = metodo(visible, corte, futuros)
                for a in futuros:
                    errores[nombre].setdefault(a - corte, []).append((abs(pronostico[a] - s.historico[a]), abs(s.historico[a])))
                    cortes[nombre][a - corte] = cortes[nombre].get(a - corte, 0) + 1
    por_anio = {m: {str(k): {'wape': sum(e for e, _r in v) / sum(r for _e, r in v), 'n': len(v)} for k, v in sorted(d.items())} for m, d in errores.items()}
    horizonte = max((k for d in cortes.values() for k in d), default=0)
    if not horizonte:
        return {'usado': False, 'motivo': 'el Formato 01 no tiene tres años completos para cortar', 'por_anio': por_anio, 'anios_validados': 0}
    ganador = comparar_metodos(series, horizonte=horizonte)['ganador']
    validados = 0
    for k in range(1, horizonte + 1):
        if cortes[ganador].get(k, 0) >= MIN_ORIGENES and validados == k - 1:
            validados = k
    return {'usado': True, 'ganador': ganador, 'por_anio': por_anio, 'anios_validados': validados, 'series': [s.codigo or s.nombre for s in series]}


def competir(dataset: Dataset, *, candidatos: Sequence[str] | None = None, modelos: Sequence[str] = (), formato_01: Sequence[SerieMercado] = (),
             semilla: int = 0, paso_meses: int = 1, ajustes: Mapping | None = None, fabrica: Callable = fabrica_modelo,
             clases: Sequence[str] | None = None, log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Compite y elige por clase y magnitud, con la regla escrita antes de medir (031:RF-2 a RF-4, RF-8, RF-14).

    Sin GPU, un modelo neuronal queda ``NO_DISPONIBLE`` con su motivo y compiten los demás.
    """
    nombres = list(candidatos) if candidatos is not None else [*METODOS_ANUALES, *METODOS_089]
    exogenas = dataset.exogenas
    if candidatos is None and exogenas is not None and len(exogenas.temperatura):
        nombres.append(CON_TEMPERATURA)
    salida: dict[str, Any] = {'regla': dict(REGLA), 'semilla': semilla, 'paso_meses': paso_meses, 'candidatos': nombres, 'modelos': list(modelos), 'grupos': {}}
    salida['formato_01'] = medir_formato_01(formato_01) if formato_01 else {'usado': False, 'motivo': 'la empresa no da Formato 01 con años completos', 'anios_validados': 0}
    if clases is None:
        # Sin libros de clientes no hay escaladas (089:RF-73): se proyecta el alimentador entero y sus cargas se reparten (RF-12).
        clases = CLASES if any(o.clase == 'escaladas' for o in dataset.objetivos) else (*CLASES, 'cabecera')
    por_grupo: dict[tuple[str, str], list[Objetivo]] = {}
    for o in dataset.objetivos:
        if o.clase in clases and o.magnitud in MAGNITUDES and len(o.curva):
            por_grupo.setdefault((o.clase, o.magnitud), []).append(o)
    for (clase, magnitud), objetivos in sorted(por_grupo.items()):
        log(f'Competición {clase}|{magnitud}: {len(objetivos)} objetivos')
        grupo = _competir_grupo(objetivos, nombres, modelos, paso_meses=paso_meses, semilla=semilla, exogenas=exogenas, ajustes=ajustes, fabrica=fabrica, log=log)
        salida['grupos'][f'{clase}|{magnitud}'] = {'clase': clase, 'magnitud': magnitud, **grupo}
    return sin_infinitos(salida)


# --------------------------------------------------------------------------- Formato 01 desde la cabecera
@dataclass(frozen=True)
class AnioFormato:
    """Un año de un sistema: sus meses medidos dicen si se puede leer como año entero (031:RF-15)."""

    anio: int
    meses: tuple[int, ...]
    completo: bool
    mwh_medidos: float
    mw: float | None
    alimentadores: tuple[str, ...]
    mwh_mismos_meses: float | None = None
    mismos_meses: tuple[int, ...] = ()
    tasa_mismos_meses: float | None = None
    alimentadores_del_sistema: int = 0
    comparados: int = 0


@dataclass(frozen=True)
class SistemaFormato:
    codigo: str
    nombre: str
    sector: str
    empresa: str
    anios: tuple[AnioFormato, ...]


def _energia_mensual(serie: _Serie) -> dict[int, float]:
    """La media medida por las horas del mes: un tramo limpiado no cuenta como cero, y el libro dice la cobertura."""
    return {m: v * _registros_del_mes(m) / 4 / 1000 for m, v in serie.meses.media.items()}


def _mw_coincidente(series: Sequence[_Serie], anio: int, medidos: Mapping[str, set[int]]) -> float | None:
    """La máxima de la suma, solo en instantes con todos los alimentadores medidos en ese mes: con uno de menos, la suma no es el sistema."""
    import pandas as pd

    maximo = None
    for cal in range(1, 13):
        mes = (anio - 1970) * 12 + cal - 1
        vivos = [s for s in series if mes in medidos[s.nombre]]
        if not vivos:
            continue
        partes = []
        for s in vivos:
            a, b = np.searchsorted(s.t, [_inicio(mes), _inicio(mes + 1)])
            partes.append(pd.Series(s.y[a:b], index=s.t[a:b]))
        suma = pd.concat(partes, axis=1, join='inner').sum(axis=1)
        if len(suma):
            maximo = max(maximo or 0.0, float(suma.max()))
    return None if maximo is None else maximo / 1000


def formato_01_de_cabecera(objetivos: Iterable[Objetivo], *, sistema_de: Mapping[str, str], sistemas: Mapping[str, Mapping[str, str]] | None = None,
                           empresa: str = '') -> list[SistemaFormato]:
    """La tabla del Formato 01 de cada sistema con la medición de cabecera, sin decir nunca más de lo medido (031:RF-15).

    La comparación entre años va por pares (alimentador, mes) comunes: en un sistema real, 3 de sus 18 alimentadores traían dos
    años y los demás solo el último, y sumar lo de cada año daba +334 %. Por eso tampoco es «año completo» el que tiene sus 12 meses
    con solo una parte de los alimentadores del sistema.
    """
    por_sistema: dict[str, list[_Serie]] = {}
    for o in objetivos:
        if o.clase == 'cabecera' and o.magnitud == 'kW' and sistema_de.get(o.ident):
            s = _serie(o)
            if s.meses.media:
                por_sistema.setdefault(sistema_de[o.ident], []).append(s)
    salida = []
    for codigo in sorted(por_sistema):
        series = por_sistema[codigo]
        energia = {s.nombre: _energia_mensual(s) for s in series}
        medidos = {s.nombre: set(s.meses.media) for s in series}
        pares: dict[int, dict[tuple[str, int], float]] = {}
        for nombre, valores in energia.items():
            for m, v in valores.items():
                pares.setdefault(_anio(m), {})[(nombre, _calendario(m))] = v
        anios_lista = sorted(pares)
        todos = set.intersection(*(set(pares[a]) for a in anios_lista))
        del_sistema = max(1, sum(1 for c in sistema_de.values() if c == codigo))
        filas = []
        for i, anio in enumerate(anios_lista):
            de_este = pares[anio]
            meses = tuple(sorted({c for _n, c in de_este}))
            alimentadores = tuple(sorted({n.split(':')[1] for n, _c in de_este}))
            completo = len(meses) == 12 and len(de_este) == 12 * del_sistema
            tasa = None
            if i:
                comunes = set(pares[anios_lista[i - 1]]) & set(de_este)
                previo = sum(pares[anios_lista[i - 1]][k] for k in comunes)
                if comunes and previo > 0:
                    tasa = (sum(de_este[k] for k in comunes) / previo) ** (1 / (anio - anios_lista[i - 1])) - 1
            filas.append(AnioFormato(anio, meses, completo, sum(de_este.values()), _mw_coincidente(series, anio, medidos), alimentadores,
                                     sum(de_este[k] for k in todos) if todos else None, tuple(sorted({c for _n, c in todos})), tasa,
                                     del_sistema, len({n for n, _c in todos})))
        datos = dict((sistemas or {}).get(codigo) or {})
        salida.append(SistemaFormato(codigo, str(datos.get('nombre') or codigo), str(datos.get('sector') or ''), empresa, tuple(filas)))
    return salida


COLUMNAS_FORMATO = ('Año', 'N.°', 'MW.h', 'Tasa (%)', 'MW', 'Base de los MW.h', 'Meses medidos', 'N.° de meses', 'Año completo', 'MW.h de los meses medidos',
                    'Meses comparados', 'MW.h de los meses comparados', 'Alimentadores medidos', 'Alimentadores del sistema')


def _lista_de_meses(meses: Iterable[int]) -> str:
    return ','.join(f'{m:02d}' for m in meses)


def escribir_formato_01(ruta: Path | str, sistemas: Sequence[SistemaFormato]) -> Path:
    """Una hoja por sistema, con los rótulos que lee ``leer_formato_01``.

    Si todos los años son enteros, «MW.h» es la energía de cada año. Si alguno no lo es, «MW.h» es la de los mismos meses y
    alimentadores en todos, y la columna de la base lo dice: es lo único que se puede comparar, y el lector no ve una caída ni un salto
    que no ocurrieron. Un único año incompleto, sin nada con que compararlo, va vacío. Lo medido de cada año sigue en su propia columna.
    """
    from openpyxl import Workbook

    if not sistemas:
        raise ProyeccionError('ningún sistema con medición de cabecera para el Formato 01')
    libro = Workbook()
    libro.remove(libro.active)
    for s in sistemas:
        hoja = libro.create_sheet(re.sub(r'[\\/*?:\[\]]', '_', s.codigo)[:31])
        for fila in (('Formato N.° 01 construido con la medición de cabecera (031:RF-15)',), ('Empresa',), ('Nombre:', s.empresa),
                     ('Sistema Eléctrico',), ('Código:', s.codigo), ('Nombre:', s.nombre), ('Sector:', s.sector),
                     ('Energía de cada mes: media medida por las horas del mes; un mes con menos de la mitad de sus registros no cuenta.',), COLUMNAS_FORMATO, ('Histórico',)):
            hoja.append(list(fila))
        enteros = all(a.completo for a in s.anios)
        for i, a in enumerate(s.anios, start=1):
            if enteros:
                mwh, base = a.mwh_medidos, 'año entero'
            elif len(s.anios) >= 2 and a.mwh_mismos_meses:
                mwh, base = a.mwh_mismos_meses, f'solo meses {_lista_de_meses(a.mismos_meses)}, de {a.comparados} de {a.alimentadores_del_sistema} alimentadores: no es el año entero'
            else:
                mwh, base = None, 'año incompleto sin otro con que compararlo'
            hoja.append([str(a.anio), i, mwh, None if a.tasa_mismos_meses is None else 100 * a.tasa_mismos_meses, a.mw if a.completo else None, base,
                         _lista_de_meses(a.meses), len(a.meses), 'sí' if a.completo else 'no', a.mwh_medidos, _lista_de_meses(a.mismos_meses), a.mwh_mismos_meses,
                         ','.join(a.alimentadores), a.alimentadores_del_sistema])
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(ruta) as tmp:
        libro.save(tmp)
        tmp.replace(ruta)
    return ruta


def leer_meses_formato_01(ruta: Path | str) -> dict[str, dict[int, dict[str, Any]]]:
    """Los meses y lo comparable de cada año de un libro construido: lo que ``SerieMercado`` no guarda."""
    from openpyxl import load_workbook

    libro = load_workbook(ruta, read_only=True, data_only=True)
    salida: dict[str, dict[int, dict[str, Any]]] = {}
    for nombre in libro.sheetnames:
        filas = list(libro[nombre].iter_rows(values_only=True))
        cab = next((f for f in filas if f and f[0] == 'Año' and 'Meses medidos' in f), None)
        if cab is None:
            continue
        pos = {c: i for i, c in enumerate(cab) if c}
        for f in filas:
            if f and re.fullmatch('(19|20)[0-9]{2}', str(f[0] or '')):
                salida.setdefault(nombre, {})[int(f[0])] = {
                    'meses': [int(x) for x in str(f[pos['Meses medidos']] or '').split(',') if x], 'completo': f[pos['Año completo']] == 'sí',
                    'mwh_medidos': f[pos['MW.h de los meses medidos']], 'meses_comparados': [int(x) for x in str(f[pos['Meses comparados']] or '').split(',') if x],
                    'mwh_comparados': f[pos['MW.h de los meses comparados']], 'tasa_pct': f[pos['Tasa (%)']], 'base': f[pos['Base de los MW.h']],
                    'alimentadores': str(f[pos['Alimentadores medidos']] or '').split(','), 'alimentadores_del_sistema': f[pos['Alimentadores del sistema']]}
    return salida


# --------------------------------------------------------------------------- emisión
@dataclass(frozen=True)
class Carga:
    """Una carga del estudio con su identidad completa; ``serie`` es su código de cliente, si lo tiene (031:RF-12)."""

    carga: str
    alimentador: str
    potencia_kva: float | None = None
    serie: str | None = None


def _instantes_de_maxima(cabecera: _Serie | None) -> np.ndarray:
    """Los instantes más altos del alimentador en sus 12 últimos meses, de mayor a menor."""
    if cabecera is None or not len(cabecera.t):
        return np.zeros(0, dtype='datetime64[ns]')
    desde = cabecera.t[-1] - np.timedelta64(365, 'D')
    t, y = cabecera.t[cabecera.t >= desde], cabecera.y[cabecera.t >= desde]
    orden = np.lexsort((t, -y))
    return t[orden][:INSTANTES_DE_MAXIMA]


def _base(serie: _Serie, instantes: np.ndarray) -> tuple[float, str, str] | None:
    """El valor medido en el primer instante de máxima del alimentador que la serie tiene; ninguno se rellena (031:RF-5)."""
    if not len(serie.t):
        return None
    pos = np.searchsorted(serie.t, instantes)
    pos = np.minimum(pos, len(serie.t) - 1)
    aciertos = np.flatnonzero(serie.t[pos] == instantes) if len(instantes) else np.zeros(0, dtype=int)
    if len(aciertos):
        i = pos[aciertos[0]]
        return float(serie.y[i]), str(serie.t[i])[:19], 'coincidente con la máxima del alimentador'
    desde = serie.t[-1] - np.timedelta64(365, 'D')
    ventana = np.flatnonzero(serie.t >= desde)
    i = ventana[int(np.argmax(np.abs(serie.y[ventana])))]
    return float(serie.y[i]), str(serie.t[i])[:19], 'máxima propia: no tiene dato en las máximas del alimentador'


def _factores_de(nombre: str, grupo: Mapping[str, Any], formato: Mapping[str, Any] | None, serie_formato: SerieMercado | None,
                 hasta: int) -> tuple[dict[int, float], str, bool]:
    """El factor de cada año adelante: el crecimiento del grupo con el ganador o, sin él, el nivel del año que sigue y lo que diga el Formato 01."""
    ganador = grupo['ganador']
    usar_cola = bool(formato and formato.get('usado') and serie_formato is not None)
    nota = ''
    if ganador == REFERENCIA_SIN_DOS_ANIOS:
        factores = dict.fromkeys(range(1, hasta + 1), 1.0)
    elif _familia(ganador) == 'anual':
        hist = {int(a): v for a, v in (grupo.get('historia_anual') or {}).get('maxima', {}).items()}
        try:
            ultimo = max(hist)
            razones = _razones_anuales(ganador, hist, ultimo + hasta)
            factores = {k: razones[ultimo + k] / hist[ultimo] for k in range(1, hasta + 1)}
        except (MercadoError, ValueError):
            factores = dict.fromkeys(range(1, hasta + 1), 1.0)
            nota = f'el grupo de {nombre} no da para {ganador}: su nivel se mantiene'
    else:
        primero = float((grupo.get('factor_primer_anio') or {}).get(nombre, 1.0))
        factores = dict.fromkeys(range(1, hasta + 1), primero)
        nota = f'{ganador} no trae tendencia: después del primer año su nivel se mantiene'
    if usar_cola:
        hist = dict(serie_formato.historico)
        ultimo = max(hist)
        cola = METODOS_ANUALES[formato['ganador']](hist, ultimo, range(ultimo, ultimo + hasta + 1))
        for k in range(2, hasta + 1):
            factores[k] = factores[1] * cola[ultimo + k] / cola[ultimo + 1]
        nota = f"desde el segundo año, {formato['ganador']} del Formato 01 de la empresa"
    return factores, nota, usar_cola


def tasa_de_largo_plazo() -> float:
    """La tasa del perfil, o la de referencia: la que el usuario eligió para el largo plazo (042:RF-86)."""
    from .perfil_empresa import TASA_CRECIMIENTO_DE_REFERENCIA, datos_perfil

    return float((datos_perfil().get('planificacion') or {}).get('crecimiento_demanda_anual') or TASA_CRECIMIENTO_DE_REFERENCIA)


def _con_cola(factores: Mapping[int, float], validados: int, tasa: float) -> dict[int, float]:
    """031:RF-16: tras el último año validado, la tasa de largo plazo sobre lo pronosticado.

    Un sistema real: la tasa medida de un solo cruce entre años, seguida 20 años, daba 13 365 MW y multiplicaba por 261 la
    demanda. Las métricas eligen hasta donde hay con qué medir; más allá no hay nada que las respalde.
    """
    ancla = max(1, validados)
    return {k: f if k <= ancla else factores[ancla] * (1 + tasa) ** (k - ancla) for k, f in factores.items()}


def _banda_de(grupo: Mapping[str, Any], k: int) -> tuple[float, float, bool] | None:
    """Los cuantiles medidos a ese año o, sin ellos, los del último año medido abiertos con la raíz del tiempo, y lo dice."""
    banda = grupo.get('banda') or {}
    propia = banda.get(str(k))
    if propia and propia['n'] >= MIN_ERRORES_BANDA:
        return propia['q05'], propia['q95'], False
    medidos = [int(a) for a, v in banda.items() if v['n'] >= MIN_ERRORES_BANDA]
    if not medidos:
        return None
    ultimo = max(medidos)
    escala = math.sqrt(k / ultimo)
    return banda[str(ultimo)]['q05'] * escala, banda[str(ultimo)]['q95'] * escala, True


def _limites(valor: float, banda: tuple[float, float, bool] | None) -> tuple[float | None, float | None]:
    if banda is None:
        return None, None
    a, b = valor + abs(valor) * banda[0], valor + abs(valor) * banda[1]
    return min(a, b), max(a, b)


def aceptacion(validado: int, horizonte: int, orden: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """031:RF-7 — aceptada por orden expresa o por validar todo el horizonte, y dice cuál; una orden no oculta lo que falta."""
    if validado >= horizonte:
        return 'aceptado', {'via': 'validacion_completa', 'anios_sin_validar': 0}
    if orden:
        if not str(orden.get('operador') or '').strip():
            raise ProyeccionError('la orden de aceptar debe decir quién la da')
        return 'aceptado', {'via': 'orden_operador', 'operador': str(orden['operador']).strip(), 'motivo': str(orden.get('motivo') or ''),
                            'fecha': str(orden.get('fecha') or ''), 'anios_sin_validar': horizonte - validado}
    return 'sin_aceptar', {'via': None, 'anios_sin_validar': horizonte - validado,
                           'falta': f'validados {validado} de {horizonte} años: hace falta la orden expresa del operador'}


def proyectar(dataset: Dataset, competencia: Mapping[str, Any], *, proyecto: str, anio_base: int, anio_corto: int, anio_fin: int,
              cargas: Sequence[Carga] | None = None, sistema_de: Mapping[str, str] | None = None, formato_01: Sequence[SerieMercado] = (),
              orden: Mapping[str, Any] | None = None, extra: Mapping[str, Any] | None = None,
              tasa_cola: float | None = None) -> tuple[dict, dict]:
    """P y Q de cada carga en cada año, con su banda, y su evaluación (031:RF-5 a RF-7, RF-9, RF-12).

    ``filas`` son los años que continúan el corto plazo, los únicos que admite ``leer_proyeccion_anual``; los anteriores, en
    ``filas_corto_plazo``. ``horizonte_anios`` es lo pronosticado y ``horizonte_validado_anios`` lo medido contra lo ocurrido.
    """
    if not str(proyecto).strip():
        raise ProyeccionError('falta el proyecto de la proyección')
    if any(type(x) is not int for x in (anio_base, anio_corto, anio_fin)) or anio_base < 1 or anio_corto < 1 or anio_fin <= anio_corto:
        raise ProyeccionError('el año base y el horizonte deben ser enteros, y el último año mayor que el corto plazo')
    huella = dataset.huella or huella_de_objetivos(dataset.objetivos)
    grupos = competencia['grupos']
    tasa_cola = tasa_de_largo_plazo() if tasa_cola is None else float(tasa_cola)
    # La Q de cabecera solo hace falta si no hay escaladas con que repartir.
    sin_escaladas = not any(o.clase == 'escaladas' for o in dataset.objetivos)
    series = {o.nombre: _serie(o) for o in dataset.objetivos if len(o.curva) and (o.clase != 'cabecera' or o.magnitud == 'kW' or sin_escaladas)}
    fin_datos = max((max(s.meses.media) for s in series.values() if s.meses.media), default=None)
    if fin_datos is None:
        raise ProyeccionError('ningún objetivo con meses medidos')
    anio_datos = _anio(fin_datos)
    adelante_fin = max(1, anio_base + anio_fin - anio_datos)
    formato = competencia.get('formato_01') or {}
    por_codigo_formato = {normalizar(s.codigo): s for s in formato_01}
    avisos: list[str] = []
    cargas_apartadas: list[dict] = []

    def alimentador_de(o: Objetivo) -> str:
        return str(o.fuente.get('alimentador') or o.ident) if o.clase == 'cliente' else o.ident

    def demanda(clase: str, ident: str) -> dict[str, Any] | None:
        """Base, factores y banda de un objetivo en P y Q; ``None`` si le falta alguna magnitud."""
        salida: dict[str, Any] = {}
        p, q = series.get(f'{clase}:{ident}:kW'), series.get(f'{clase}:{ident}:kVAR')
        if p is None or q is None:
            return None
        alimentador = str(p.objetivo.fuente.get('alimentador') or ident) if clase == 'cliente' else ident
        instantes = _instantes_de_maxima(series.get(f'cabecera:{alimentador}:kW'))
        base_p = _base(p, instantes)
        if base_p is None:
            return None
        base_q = _base(q, np.r_[np.datetime64(base_p[1]).astype('datetime64[ns]'), instantes])
        if base_q is None:
            return None
        sistema = (sistema_de or {}).get(alimentador)
        serie_formato = por_codigo_formato.get(normalizar(sistema)) if sistema else None
        grupo_de = {m: grupos.get(f'{clase}|{m}') for m in MAGNITUDES}
        if grupo_de['kW'] is None or grupo_de['kVAR'] is None:
            return None
        fp, nota_p, cola = _factores_de(p.nombre, grupo_de['kW'], formato, serie_formato, adelante_fin)
        fq, nota_q, _c = _factores_de(q.nombre, grupo_de['kVAR'], formato, serie_formato, adelante_fin)
        validados = _validados(grupo_de['kW'], grupo_de['kVAR'], formato, cola)
        salida.update(p=base_p, q=base_q, fp=_con_cola(fp, validados, tasa_cola), fq=_con_cola(fq, validados, tasa_cola),
                      nota=' · '.join(x for x in (nota_p, nota_q) if x), grupo_p=grupo_de['kW'], grupo_q=grupo_de['kVAR'],
                      validados=validados, objetivo=p.nombre)
        return salida

    # Cada carga con su serie propia o, sin ella, con la de su alimentador en proporción a su potencia instalada (RF-12).
    planes: list[tuple[str, str, str, dict, float, str]] = []
    if cargas is None:
        vistos = sorted({(o.clase, o.ident) for o in dataset.objetivos if (o.clase in CLASES or (sin_escaladas and o.clase == 'cabecera'))
                         and o.magnitud == 'kW' and len(o.curva)})
        for clase, ident in vistos:
            d = demanda(clase, ident)
            if d is None:
                cargas_apartadas.append({'carga': f'{clase}:{ident}', 'motivo': 'no tiene P y Q medidas: no se imputa'})
                continue
            planes.append((f'{clase}:{ident}', alimentador_de(series[d['objetivo']].objetivo), 'cliente' if clase == 'cliente' else 'escaladas', d, 1.0,
                           '' if clase != 'cabecera' else f'{ident} sin clientes medidos: su cabecera entera'))
    else:
        clientes = {clave_codigo(o.ident): o for o in dataset.objetivos if o.clase == 'cliente' and o.magnitud == 'kW' and len(o.curva)}
        sin_serie: dict[str, list[Carga]] = {}
        for c in cargas:
            o = clientes.get(clave_codigo(c.serie)) if c.serie else None
            d = demanda('cliente', o.ident) if o is not None else None
            if d is None:
                sin_serie.setdefault(c.alimentador, []).append(c)
            else:
                planes.append((c.carga, c.alimentador, 'cliente', d, 1.0, ''))
        for alimentador, lista in sorted(sin_serie.items()):
            d = demanda('escaladas', alimentador)
            origen = 'escaladas'
            if d is None:
                # Sin clientes no hay escaladas: el alimentador entero se reparte, y la fila lo dice.
                d = demanda('cabecera', alimentador)
                origen = 'cabecera'
            total = sum(float(c.potencia_kva or 0) for c in lista)
            for c in lista:
                if d is None:
                    cargas_apartadas.append({'carga': c.carga, 'motivo': f'{alimentador} no tiene serie de P y Q: no se imputa'})
                elif not c.potencia_kva or c.potencia_kva <= 0 or total <= 0:
                    cargas_apartadas.append({'carga': c.carga, 'motivo': 'sin potencia instalada no se reparte: no se imputa'})
                else:
                    planes.append((c.carga, c.alimentador, 'escaladas', d, float(c.potencia_kva) / total,
                                   f'repartida con la serie de {origen} de {alimentador} en proporción a su potencia instalada'))
    if not planes:
        raise ProyeccionError('ninguna carga con demanda medida: no hay proyección que emitir')
    filas, filas_corto = [], []
    for carga, alimentador, clase, d, parte, reparto in sorted(planes, key=lambda x: x[0]):
        for k in range(1, anio_fin + 1):
            delante = max(1, anio_base + k - anio_datos)
            p = max(0.0, d['p'][0] * d['fp'][delante] * parte)
            q = d['q'][0] * d['fq'][delante] * parte
            bp, bq = _banda_de(d['grupo_p'], delante), _banda_de(d['grupo_q'], delante)
            p05, p95 = _limites(p, bp)
            q05, q95 = _limites(q, bq)
            fila = {'anio': k, 'anio_calendario': anio_base + k, 'anios_adelante': delante, 'alimentador': alimentador, 'carga': carga, 'clase': clase,
                    'objetivo': d['objetivo'], 'p_kw': round(p, 3), 'q_kvar': round(q, 3),
                    'p_q05_kw': None if p05 is None else round(max(0.0, p05), 3), 'p_q95_kw': None if p95 is None else round(p95, 3),
                    'q_q05_kvar': None if q05 is None else round(q05, 3), 'q_q95_kvar': None if q95 is None else round(q95, 3),
                    'modelo_p': d['grupo_p']['ganador'], 'modelo_q': d['grupo_q']['ganador'], 'validado': delante <= d['validados'],
                    'origen_anio': 'modelo' if delante <= max(1, d['validados']) else 'tasa_de_largo_plazo',
                    'banda_extrapolada': bool((bp and bp[2]) or (bq and bq[2])), 'instante_base': d['p'][1], 'base': d['p'][2]}
            if reparto:
                fila.update(reparto=reparto, parte=round(parte, 6))
            if d['nota']:
                fila['nota'] = d['nota']
            if d['fp'][delante] > FACTOR_DE_AVISO and k == anio_fin and delante > d['validados']:
                avisos.append(f"{clase}: {d['grupo_p']['ganador']} multiplica la demanda por {d['fp'][delante]:.1f} en el año {k}, sin validar")
            (filas if k > anio_corto else filas_corto).append(fila)
    modelo = 'proyeccion_anual_v{}[{}]'.format(REGLA['version'], ';'.join(f"{g}={v['ganador']}" for g, v in sorted(grupos.items())))
    validado = min((_validados(v, v, formato, bool(formato.get('usado') and formato_01)) for v in grupos.values()), default=0)
    meses = min((int((v.get('validacion') or {}).get('meses') or 0) for v in grupos.values()), default=0)
    estado, via = aceptacion(validado, adelante_fin, orden)
    evaluacion = {'estado': estado, 'aceptacion': via, 'uso': 'planeamiento_anual', 'modelo': modelo, 'dataset_sha256': huella,
                  'horizonte_anios': anio_fin, 'anios_a_validar': adelante_fin, 'horizonte_validado_anios': validado, 'horizonte_validado_meses': meses,
                  'anio_base': anio_base, 'anio_corto': anio_corto, 'anio_fin': anio_fin, 'anio_ultimo_dato': anio_datos, 'ultimo_mes_medido': _rotulo(fin_datos),
                  'tasa_de_largo_plazo': tasa_cola,
                  'regla': competencia['regla'], 'semilla': competencia.get('semilla'), 'ganadores': {g: v['ganador'] for g, v in grupos.items()},
                  'competencia': competencia, 'cargas_apartadas': cargas_apartadas, 'avisos': sorted(set(avisos)) + list(dataset.avisos), 'apartados': dataset.apartados,
                  **dict(extra or {})}
    proyeccion = {'proyecto': str(proyecto), 'anio_base': anio_base, 'anio_corto': anio_corto, 'anio_fin': anio_fin, 'modelo': modelo, 'dataset_sha256': huella,
                  'filas': filas, 'filas_corto_plazo': filas_corto}
    return proyeccion, sin_infinitos(evaluacion)


def _validados(grupo_p: Mapping, grupo_q: Mapping, formato: Mapping, cola: bool) -> int:
    """Lo validado de P y Q: el nivel, y los años que el Formato 01 midió si la cola sale de él."""
    nivel = min(int((g.get('validacion') or {}).get('anios') or 0) for g in (grupo_p, grupo_q))
    if cola and nivel >= 1:
        return max(nivel, int(formato.get('anios_validados') or 0))
    return nivel


def _escribir_json(ruta: Path, valor: Any) -> dict[str, str]:
    contenido = (json.dumps(valor, ensure_ascii=False, indent=1, sort_keys=True, default=str) + '\n').encode('utf-8')
    with staging_publicacion(ruta) as tmp:
        tmp.write_bytes(contenido)
        tmp.replace(ruta)
    return {'ruta': str(ruta), 'sha256': hashlib.sha256(contenido).hexdigest()}


def escribir_proyeccion(carpeta: Path | str, proyeccion: Mapping[str, Any], evaluacion: Mapping[str, Any]) -> dict[str, str]:
    """Evaluación y proyección con sus huellas, como las lee ``leer_proyeccion_anual`` (031:RF-9); la referencia de la proyección."""
    carpeta = Path(carpeta).resolve()
    carpeta.mkdir(parents=True, exist_ok=True)
    referencia = _escribir_json(carpeta / 'evaluacion.json', evaluacion)
    return _escribir_json(carpeta / 'proyeccion.json', {**proyeccion, 'evaluacion': referencia})


# --------------------------------------------------------------------------- uso en el PIDE y las obras
def fijar_vigente(carpeta: Path | str, referencia: Mapping[str, str]) -> Path:
    """La proyección que usan el PIDE y las obras de un proyecto: una, con su huella."""
    ruta = Path(carpeta) / 'vigente.json'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    _escribir_json(ruta, {'ruta': referencia['ruta'], 'sha256': referencia['sha256']})
    return ruta


def proyeccion_aceptada(carpeta: Path | str | None, proyecto: str) -> dict | None:
    """La vigente solo si el mismo lector del PIDE la admite (072:RF-24, 031:RF-11); si no, ``None``: nunca a medias."""
    if carpeta is None or not (Path(carpeta) / 'vigente.json').is_file():
        return None
    try:
        referencia = json.loads((Path(carpeta) / 'vigente.json').read_text(encoding='utf-8'))
        datos = leer_json_con_huella(referencia, 'proyección vigente')
        plan = {'project': proyecto, 'anio_fin': datos['anio_fin'], 'corto_plazo': {'anio': datos['anio_corto'], 'anio_base': datos['anio_base']},
                'proyeccion_anual': referencia, 'feeders': sorted({f['alimentador'] for f in datos['filas']})}
        leida = leer_proyeccion_anual(plan)
        return {**leida, 'evaluacion_leida': leer_json_con_huella(datos['evaluacion'], 'evaluación anual')}
    except (PideError, KeyError, OSError, TypeError, ValueError):
        return None


def tasas_de_la_proyeccion(datos: Mapping[str, Any]) -> dict[str, float]:
    """La tasa anual equivalente de cada alimentador entre el primer y el último año emitido, en su P."""
    por: dict[str, dict[int, float]] = {}
    for fila in (*datos.get('filas_corto_plazo', ()), *datos['filas']):
        d = por.setdefault(fila['alimentador'], {})
        d[fila['anio']] = d.get(fila['anio'], 0.0) + fila['p_kw']
    salida = {}
    for alimentador, valores in sorted(por.items()):
        a, b = min(valores), max(valores)
        if b > a and valores[a] > 0 and valores[b] > 0:
            salida[alimentador] = (valores[b] / valores[a]) ** (1 / (b - a)) - 1
    return salida


def tasa_de_alcance(carpeta: Path | str | None, proyecto: str, alimentadores: Sequence[str], tasa_perfil: float) -> dict[str, Any]:
    """La tasa del alcance de las obras: la de la proyección aceptada o, sin ella, la del perfil, y lo dice (031:RF-11, 042:RF-86)."""
    datos = proyeccion_aceptada(carpeta, proyecto)
    tasas = tasas_de_la_proyeccion(datos) if datos else {}
    propias = [tasas[a] for a in alimentadores if a in tasas]
    if propias:
        return {'tasa': statistics.median(propias), 'origen': 'proyeccion_aceptada', 'modelo': datos['modelo'],
                'aviso': f"el alcance usa la proyección aceptada ({datos['modelo']}): {100 * statistics.median(propias):.2f} %/año equivalente (031:RF-11)."}
    return {'tasa': tasa_perfil, 'origen': 'perfil', 'aviso': f'sin proyección aceptada de estos alimentadores, el alcance sigue con la tasa del perfil, {100 * tasa_perfil:.2f} %/año (031:RF-11).'}


def _firma_de_fuentes(fuentes: Fuentes, parametros: Mapping[str, Any]) -> str:
    """Si los libros y lo pedido no cambian, lo pronosticado sigue valiendo: leerlos otra vez cuesta horas."""
    from .cabecera_ancha import libros_de

    rutas = [r for r in (*([fuentes.cabecera] if isinstance(fuentes.cabecera, (str, Path)) else fuentes.cabecera), fuentes.clientes) if r]
    fichas = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in libros_de(rutas)]
    return hashlib.sha256(json.dumps({'libros': sorted(fichas), 'pedido': parametros}, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def pronostico_al_dia(carpeta: Path | str, firma: str) -> dict[str, str] | None:
    """La proyección ya emitida con estos mismos libros y parámetros, aunque aún esté sin aceptar."""
    try:
        ruta = Path(carpeta) / 'proyeccion.json'
        raw = ruta.read_bytes()
        datos = json.loads(raw)
        if leer_json_con_huella(datos['evaluacion'], 'evaluación').get('firma_fuentes') == firma:
            return {'ruta': str(ruta.resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}
    except (KeyError, OSError, TypeError, ValueError):
        pass
    return None


def pronosticar_estudio(fuentes: Fuentes, *, carpeta: Path | str, proyecto: str, anio_base: int, anio_corto: int, anio_fin: int, empresa: str | None = None,
                        sistema_de: Mapping[str, str] | None = None, sistemas: Mapping[str, Mapping[str, str]] | None = None,
                        formato_01: Path | str | None = None, cargas: Sequence[Carga] | None = None, modelos: Sequence[str] = (), semilla: int = 0,
                        paso_meses: int = 1, ajustes: Mapping | None = None, orden: Mapping[str, Any] | None = None, dataset: Dataset | None = None,
                        log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """De los libros a la proyección y su evaluación, de nivel superior para correr en el proceso del trabajo (031:RF-1, RF-13, RF-15).

    Sin Formato 01 de la empresa, lo construye con la cabecera; una proyección ya hecha con los mismos libros se devuelve tal cual.
    """
    carpeta = Path(carpeta).resolve()
    pedido = {'regla': REGLA['version'], 'proyecto': proyecto, 'anio_base': anio_base, 'anio_corto': anio_corto, 'anio_fin': anio_fin, 'modelos': list(modelos), 'semilla': semilla, 'paso_meses': paso_meses}
    firma = _firma_de_fuentes(fuentes, pedido) if dataset is None else (dataset.huella + json.dumps(pedido, sort_keys=True))
    hecha = None if orden else pronostico_al_dia(carpeta, firma)
    if hecha is not None:
        return {'referencia': hecha, 'reutilizada': True}
    if dataset is None:
        log('Leyendo los libros de demanda…')
        dataset = armar_dataset(fuentes)
        dataset.huella = guardar_dataset(dataset, carpeta / 'dataset')
    series: list[SerieMercado] = []
    notas: list[str] = []
    construido = None
    if formato_01:
        series, notas = formato_01_propio(leer_formato_01(formato_01), empresa=empresa, sistemas=None if not sistema_de else sorted(set(sistema_de.values())))
    else:
        tablas = formato_01_de_cabecera(dataset.objetivos, sistema_de=sistema_de or {}, sistemas=sistemas, empresa=empresa or '')
        if tablas:
            construido = escribir_formato_01(carpeta / 'formato_01_construido.xlsx', tablas)
            try:
                series = formato_01_propio(leer_formato_01(construido), empresa=empresa)[0]
            except MercadoError as exc:
                notas.append(f'Formato 01 construido: {exc}')
    competencia = competir(dataset, modelos=modelos, formato_01=series, semilla=semilla, paso_meses=paso_meses, ajustes=ajustes, log=log)
    extra = {'firma_fuentes': firma, 'notas_formato_01': notas, 'formato_01_construido': None if construido is None else construido.name}
    proyeccion, evaluacion = proyectar(dataset, competencia, proyecto=proyecto, anio_base=anio_base, anio_corto=anio_corto, anio_fin=anio_fin, cargas=cargas,
                                       sistema_de=sistema_de, formato_01=series, orden=orden, extra=extra)
    referencia = escribir_proyeccion(carpeta, proyeccion, evaluacion)
    if evaluacion['estado'] == 'aceptado':
        fijar_vigente(carpeta, referencia)
    return {'referencia': referencia, 'reutilizada': False, 'evaluacion': evaluacion}
