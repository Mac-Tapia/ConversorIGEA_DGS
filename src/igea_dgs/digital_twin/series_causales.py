"""046:RF-1 a RF-3 — preparación temporal con disponibilidad conocida al emitir."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo


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
    if unidad not in {'kW', 'MW'}:
        raise ValueError(f'unidad temporal no soportada: {unidad}')
    return numero * (1000 if unidad == 'MW' else 1)


def preparar_serie(registros: Sequence[Mapping], *, corte: str, cadencia_min: int,
                   zona_horaria: str, covariables: Mapping) -> dict:
    """El corte no se infiere del futuro; sus valores tampoco ajustan la escala."""
    if type(cadencia_min) is not int or cadencia_min <= 0:
        raise ValueError('cadencia_min debe ser un entero positivo')
    zona = ZoneInfo(zona_horaria)
    emision = _instante(corte, zona)
    medidas = {}
    paso = timedelta(minutes=cadencia_min)
    for fila in registros:
        instante = _instante(fila['instante'], zona)
        if instante in medidas:
            raise ValueError(f'instante duplicado: {instante.isoformat()}')
        medidas[instante] = _valor(fila.get('valor'), fila.get('unidad'))
    if not medidas:
        raise ValueError('serie vacía')
    inicio, fin = min(medidas), max(medidas)
    if any((t - inicio) % paso != timedelta(0) for t in medidas):
        raise ValueError('medidas incompatibles con la cadencia declarada')
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
            'zona_horaria': zona_horaria, 'unidad': 'kW',
            'filas': [{'instante': t.isoformat(), 'valor': medidas.get(t)} for t in tiempos],
            'mascara': [medidas.get(t) is not None for t in tiempos],
            'covariables': valores_cov, 'disponibilidad_asof': disponibles,
            'transformaciones': {'escala': max(abs(v) for v in entrenamiento) or 1.0,
                                'ajustada_hasta_exclusivo': emision.isoformat(),
                                'observaciones': len(entrenamiento)}}
