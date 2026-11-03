"""046:RF-1 a RF-3 — preparación temporal con disponibilidad conocida al emitir."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

import numpy as np

from ..evaluacion_modelos import PARTES, PoliticaEvaluacion, particionar_registros

#: Cuantiles de cada salida: q05–q95 es un intervalo nominal del 90 %.
CUANTILES = (.05, .5, .95)
#: Fracción de días de entrenamiento, selección, calibración y prueba (spec 046, puertas).
FRACCIONES_DIAS = (.6, .15, .1, .15)
#: Unidades admitidas, con su factor a la unidad base. kW y kVAR no se mezclan en una serie.
UNIDADES = {'kW': ('kW', 1.0), 'MW': ('kW', 1000.0), 'kVAR': ('kVAR', 1.0), 'MVAR': ('kVAR', 1000.0)}


def _instante(valor: str, zona: ZoneInfo) -> datetime:
    instante = datetime.fromisoformat(valor)
    if instante.tzinfo is None:
        if instante.replace(tzinfo=zona, fold=0).utcoffset() != instante.replace(tzinfo=zona, fold=1).utcoffset():
            raise ValueError('hora local ambigua o inexistente: indique su offset explícito')
        instante = instante.replace(tzinfo=zona)
    return instante.astimezone(timezone.utc)


def _valor(valor, unidad: str):
    if valor is None:
        return None
    try:
        numero = float(valor) if not isinstance(valor, bool) else math.nan
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('medición no numérica') from exc
    if not math.isfinite(numero):
        raise ValueError('medición no finita')
    if unidad not in UNIDADES:
        raise ValueError(f'unidad temporal no soportada: {unidad}')
    return numero * UNIDADES[unidad][1]


def preparar_serie(registros: Sequence[Mapping], *, corte: str, cadencia_min: int,
                   zona_horaria: str, covariables: Mapping) -> dict:
    """El corte no se infiere del futuro; sus valores tampoco ajustan la escala."""
    if type(cadencia_min) is not int or cadencia_min <= 0:
        raise ValueError('cadencia_min debe ser un entero positivo')
    zona = ZoneInfo(zona_horaria)
    emision = _instante(corte, zona)
    medidas = {}
    paso = timedelta(minutes=cadencia_min)
    bases = set()
    for fila in registros:
        instante = _instante(fila['instante'], zona)
        if instante in medidas:
            raise ValueError(f'instante duplicado: {instante.isoformat()}')
        medidas[instante] = _valor(fila.get('valor'), fila.get('unidad'))
        if medidas[instante] is not None:
            bases.add(UNIDADES[fila['unidad']][0])
    if not medidas:
        raise ValueError('serie vacía')
    if len(bases) > 1:
        raise ValueError('una serie no mezcla kW con kVAR')
    inicio, fin = min(medidas), max(medidas)
    if any((t - inicio) % paso != timedelta(0) for t in medidas):
        raise ValueError('medidas incompatibles con la cadencia declarada')
    # Un libro horario declarado de 15 minutos encaja en la rejilla y parecería tener un 75 %
    # de huecos: la cadencia real es la que más se repite, y si no es la declarada se dice.
    # Con pocos registros un solo hueco sería la moda: entonces es un hueco, no otra cadencia.
    moda = cadencia_moda(sorted(medidas)) if len(medidas) >= 4 else None
    if moda is not None and moda != cadencia_min:
        raise ValueError(f'la cadencia real es de {moda:g} min, no los {cadencia_min} min declarados')
    tiempos = [inicio + i * paso for i in range((fin - inicio) // paso + 1)]
    entrenamiento = [v for t, v in medidas.items() if t < emision and v is not None]
    if not entrenamiento:
        raise ValueError('sin datos anteriores al corte para ajustar transformaciones')
    disponibles, valores_cov = {}, {}
    for nombre, filas in covariables.items():
        indice = {}
        for fila in filas:
            instante = _instante(fila['instante'], zona)
            if instante in indice:
                raise ValueError(f'covariable {nombre}: instante duplicado')
            desde = _instante(fila['disponible_desde'], zona) if fila.get('disponible_desde') else None
            valor = fila.get('valor')
            if valor is not None and (isinstance(valor, bool) or not math.isfinite(float(valor))):
                raise ValueError(f'covariable {nombre} no finita')
            indice[instante] = (valor, desde)
        serie, asof = [], []
        for instante in tiempos:
            valor, desde = indice.get(instante, (None, None))
            admisible = desde is not None and desde <= min(instante, emision)
            serie.append(float(valor) if admisible and valor is not None else None)
            asof.append(desde.isoformat() if admisible else None)
        valores_cov[nombre], disponibles[nombre] = serie, asof
    return {'schema_version': 1, 'corte': emision.isoformat(), 'cadencia_min': cadencia_min,
            'zona_horaria': zona_horaria, 'unidad': next(iter(bases), 'kW'),
            'filas': [{'instante': t.isoformat(), 'valor': medidas.get(t)} for t in tiempos],
            'mascara': [medidas.get(t) is not None for t in tiempos],
            'covariables': valores_cov, 'disponibilidad_asof': disponibles,
            'transformaciones': {'escala': max(abs(v) for v in entrenamiento) or 1.0,
                                'ajustada_hasta_exclusivo': emision.isoformat(),
                                'observaciones': len(entrenamiento)}}


def cadencia_moda(instantes: Sequence[datetime]) -> float | None:
    """Los minutos entre registros que más se repiten en instantes ordenados."""
    if len(instantes) < 2:
        return None
    pasos = Counter((b - a).total_seconds() / 60 for a, b in zip(instantes, instantes[1:]))
    return pasos.most_common(1)[0][0]


def horizontes_validos(cadencia_min: int, horizontes: Sequence[int] | None = None) -> tuple[int, ...]:
    """046:RF-4: (1, 4, 96) son 15 min, 1 h y 1 día solo con 15 minutos; otra cadencia los declara.

    96 pasos de una serie horaria son cuatro días, y rotularlos «un día» falsearía el error.
    """
    if horizontes is None:
        if cadencia_min != 15:
            raise ValueError(f'con cadencia de {cadencia_min} min declare los horizontes en pasos')
        return (1, 4, 96)
    salida = tuple(horizontes)
    if not salida or any(type(h) is not int or h <= 0 for h in salida) or sorted(set(salida)) != list(salida):
        raise ValueError('cada horizonte debe ser un entero positivo, sin repetir y en orden creciente')
    return salida


def particionar_dias(instantes: Sequence[datetime], zona_horaria: str, politica: PoliticaEvaluacion,
                     fracciones: Sequence[float] = FRACCIONES_DIAS) -> dict:
    """Cortes por día local completo, validados por el particionador de 044.

    Se asigna el día, no la fila: los registros de un mismo día comparten clima y operación,
    y repartirlos entre particiones dejaría ver el día que se quiere evaluar.
    """
    zona = ZoneInfo(zona_horaria)
    primero: dict[str, int] = {}
    for i, t in enumerate(instantes):
        primero.setdefault(t.astimezone(zona).date().isoformat(), i)
    dias = sorted(primero)
    limites_dia, acumulado = [], 0
    for fraccion in fracciones[:-1]:
        acumulado += math.floor(fraccion * len(dias) + 1e-9)
        limites_dia.append(acumulado)
    inicios, fines = [0] + limites_dia, limites_dia + [len(dias)]
    registros, por_parte, limites = [], {}, {}
    for parte, a, b in zip(PARTES, inicios, fines, strict=True):
        por_parte[parte] = dias[a:b]
        registros += [{'record_id': d, 'group_id': d, 'texto': '', 'particion': parte, 'sistema': ''}
                      for d in dias[a:b]]
        limites[parte] = (primero[dias[a]] if a < len(dias) else len(instantes),
                          primero[dias[b]] if b < len(dias) else len(instantes))
    valido = particionar_registros(registros, politica)
    return {'dias': por_parte, 'limites': limites, 'politica_hash': valido.politica_hash}


def ventanas_causales(valores: np.ndarray, *, inicio: int, fin: int, contexto_pasos: int,
                      horizonte_max: int, paso: int) -> np.ndarray:
    """Emisiones cuyos objetivos caen enteros en ``[inicio, fin)`` y sin huecos (046:RF-1, RF-3, RF-5).

    Con la emisión ``e`` se conoce hasta ``e`` y se predice de ``e+1`` a ``e+horizonte_max``: un
    objetivo no se comparte con otra partición, aunque el contexto sí mire a la anterior, porque
    lo observado antes de emitir es legítimo. Dependen del dato, nunca del modelo.
    """
    observado = np.isfinite(valores)
    faltan = np.concatenate(([0], np.cumsum(~observado)))
    primera = max(contexto_pasos - 1, inicio - 1)
    ultima = min(fin, len(valores)) - horizonte_max - 1
    if ultima < primera or paso < 1:
        return np.zeros(0, dtype=int)
    em = np.arange(primera + (-primera) % paso, ultima + 1, paso)
    sin_huecos = (faltan[em + horizonte_max + 1] - faltan[em - contexto_pasos + 1]) == 0
    return em[sin_huecos]


def tramos_observados(valores: np.ndarray, fin: int, *, minimo: int) -> list[tuple[int, int]]:
    """Tramos continuos antes de ``fin`` con ``minimo`` puntos: los huecos no se rellenan (046:RF-1)."""
    ok = np.isfinite(np.asarray(valores)[:fin])
    cambios = np.flatnonzero(np.diff(np.concatenate(([False], ok, [False])).astype(int)))
    return [(int(a), int(b)) for a, b in zip(cambios[::2], cambios[1::2], strict=True) if b - a >= minimo]
