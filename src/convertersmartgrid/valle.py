"""La ventana de valle de un alcance, desde la medición real (spec 073).

Usuario, 2026-11-02, al preguntarle cuántos bancos probar: «eso lo debe definir las demandas en
ventanas de valle donde podría ocurrir sobretensiones». Un banco fijo sigue conectado cuando baja
la demanda; la máxima no lo ve.

Puro, de una pasada por los registros: una búsqueda exacta, sin sorteos. Leer es de
``demanda_medida``; medir la tensión, de quien llama. Un cero, un hueco o una salida de servicio
no son valle: se apartan con su motivo, porque un dato dudoso definiría el número de bancos.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .demanda_medida import ALIAS, en_periodo, maximas

#: Lo que se aparta del mínimo, con la frase que lo dice (RF-6).
MOTIVOS = {
    'hueco': 'a otro medidor del alcance le falta ese registro: la suma saldría baja sin serlo',
    'duplicado': 'la misma fecha y hora con valores distintos',
    'no_numerico': 'valor no finito',
    'signo': 'signo contrario al del medidor (desborde del contador o generación sin medir)',
    'cero': 'kW en cero: salida de servicio o medidor parado, no un valle',
    'congelado': 'el mismo valor repetido: medidor congelado',
    'sin_kvar': 'registro sin kVAR en un medidor que sí lo mide',
    'franja': 'muy por debajo de su misma hora en los demás días: salida de servicio o transferencia',
    'aislada': 'caída de un solo registro frente a sus vecinos: disparo o maniobra',
}
#: Con menos días por franja, su mediana no distingue una salida de un valle.
MUESTRAS_FRANJA_MINIMAS = 3


class ValleError(ValueError):
    """Un dato de ``valle`` en el perfil no vale: se dice cuál."""


@dataclass(frozen=True)
class Ajustes:
    """De ``valle`` en el perfil. Los días no tienen valor por defecto: los pone cada empresa (RF-3).

    Los umbrales sí: no son una convención de empresa, y lo apartado siempre se ve con su valor.
    """
    dias_ventana: int | None = None
    cobertura_dia: float = 0.9              # fracción de los registros de un día para contarlo (RF-7)
    cobertura_medidor: float = 0.5          # por debajo, el medidor sale de la suma (RF-8)
    fraccion_franja: float = 0.25           # frente a la mediana de su misma hora (RF-6)
    fraccion_aislada: float = 0.5           # frente al menor de sus dos vecinos (RF-6)
    registros_congelados: int = 8           # dos horas iguales, a 15 minutos (RF-6)
    factor_cargas_nuevas: float = 0.0       # de ellas no hay medición y el banco sigue ahí (RF-23)


def ajustes_de(perfil: Mapping[str, Any]) -> Ajustes:
    """Los de ``valle`` del perfil; lo que no da, el valor de :class:`Ajustes`."""
    datos = dict(perfil.get('valle') or {})
    campos = {k: datos[k] for k in Ajustes.__dataclass_fields__ if datos.get(k) is not None}
    if 'dias_ventana' in campos and int(campos['dias_ventana']) < 1:
        raise ValleError(f"valle.dias_ventana es al menos 1 día, no {campos['dias_ventana']} (073:RF-2)")
    return Ajustes(**campos)


@dataclass
class Valle:
    """El valle de un alcance. Sin ``comprobado``, el motivo y nada de instante (RF-10)."""
    alcance: str
    comprobado: bool = False
    motivo: str = ''
    instante: dict[str, Any] | None = None
    ventana: dict[str, Any] | None = None
    apartados: dict[str, dict[str, Any]] = field(default_factory=dict)
    excluidos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    registros: int = 0
    periodo: str | None = None


def curvas_medidas(rutas: Iterable[Path | str], medidores: Sequence[tuple[str, str]], *, alias=ALIAS,
                   cancelado: Callable[[], bool] = lambda: False, cabecera=None) -> tuple[dict[str, list], list[str]]:
    """Las curvas ``(fecha, kW, kVAR)`` de cada ``(alimentador, medidor)`` con los lectores de
    ``demanda_medida`` (RF-11). Un medidor que no se lee no impide los demás: se dice."""
    curvas, avisos = {}, []
    for r in maximas(rutas, list(medidores), alias=alias, cancelado=cancelado, cabecera=cabecera):
        if r.curva:
            curvas[r.medidor] = list(r.curva)
        else:
            avisos.append(f'{r.medidor}: sin curva para el valle ({r.error or "sin registros"}).')
    return curvas, avisos


def _registro(apartados: dict, clave: str, fecha: datetime | None, kva: float | None) -> None:
    fila = apartados.setdefault(clave, {'motivo': MOTIVOS[clave], 'registros': 0, 'menor_kva': None, 'primera': None})
    fila['registros'] += 1
    if kva is not None and (fila['menor_kva'] is None or kva < fila['menor_kva']):
        fila['menor_kva'] = kva
    if fecha is not None and (fila['primera'] is None or fecha < fila['primera']):
        fila['primera'] = fecha


def _kva(kw: float, kvar: float | None) -> float:
    return abs(kw) if kvar is None else math.hypot(kw, kvar)


def _una_por_fecha(curva: Iterable[Sequence], periodo: str | None, apartados: dict) -> dict[datetime, tuple]:
    """Un registro por fecha; dos que no cuadran no se pueden creer, ninguno de los dos."""
    por: dict[datetime, tuple] = {}
    malas: set[datetime] = set()
    for t, kw, kvar in curva:
        if t is None or kw is None or (periodo and not en_periodo(t, periodo)):
            continue
        if not math.isfinite(kw) or (kvar is not None and not math.isfinite(kvar)):
            _registro(apartados, 'no_numerico', t, None)
        elif t in por and por[t] != (kw, kvar):
            malas.add(t)
        else:
            por[t] = (kw, kvar)
    for t in sorted(malas):
        _registro(apartados, 'duplicado', t, None)
        del por[t]
    return por


def _limpiar(curva: Iterable[Sequence], periodo: str | None, aj: Ajustes, apartados: dict) -> tuple[dict, bool]:
    """Los registros válidos de un medidor con el kW en positivo y si mide kVAR (RF-6)."""
    por = _una_por_fecha(curva, periodo, apartados)
    if not por:
        return {}, False
    # El signo de su mediana: hay medidores que exportan al revés, y no es un error.
    signo = -1.0 if statistics.median(v[0] for v in por.values()) < 0 else 1.0
    mide_q = any(v[1] is not None for v in por.values())
    fechas = sorted(por)
    # Congelado: sobre la serie entera, antes de quitar nada que parta la racha.
    racha_ini = 0
    congelados: set[datetime] = set()
    for i in range(1, len(fechas) + 1):
        if i == len(fechas) or por[fechas[i]] != por[fechas[racha_ini]]:
            if i - racha_ini >= aj.registros_congelados:
                congelados.update(fechas[racha_ini:i])
            racha_ini = i
    validos: dict[datetime, tuple[float, float | None]] = {}
    for t in fechas:
        kw, q = por[t]
        kw, q = signo * kw, (None if q is None else signo * q)
        if t in congelados:
            _registro(apartados, 'congelado', t, _kva(kw, q))
        elif kw < 0:
            _registro(apartados, 'signo', t, _kva(kw, q))
        elif kw == 0:
            _registro(apartados, 'cero', t, _kva(kw, q))
        elif mide_q and q is None:
            _registro(apartados, 'sin_kvar', t, _kva(kw, q))
        else:
            validos[t] = (kw, q)
    return _sin_caidas(validos, aj, apartados), mide_q


def _paso(fechas: Sequence[datetime]) -> timedelta | None:
    """El intervalo del medidor: la mediana de sus diferencias, sin suponer 15 minutos."""
    if len(fechas) < 2:
        return None
    return statistics.median(b - a for a, b in zip(fechas, fechas[1:], strict=False))


def _sin_caidas(validos: dict, aj: Ajustes, apartados: dict) -> dict:
    """Sin lo que cae frente a su misma hora o a sus vecinos (RF-6).

    La noche baja todas las noches y su franja baja con ella; una salida de servicio baja una vez.
    """
    franjas: dict[tuple[int, int], list[float]] = {}
    for t, (kw, q) in validos.items():
        franjas.setdefault((t.hour, t.minute), []).append(_kva(kw, q))
    medianas = {k: statistics.median(v) for k, v in franjas.items() if len(v) >= MUESTRAS_FRANJA_MINIMAS}
    fechas = sorted(validos)
    quedan = []
    for t in fechas:
        kva, ref = _kva(*validos[t]), medianas.get((t.hour, t.minute))
        if ref is not None and kva < aj.fraccion_franja * ref:
            _registro(apartados, 'franja', t, kva)
        else:
            quedan.append(t)
    paso = _paso(quedan)
    aisladas = set()
    for a, t, b in zip(quedan, quedan[1:], quedan[2:], strict=False):
        if paso is None or b - a > 2 * paso:             # sin los dos vecinos no se sabe
            continue
        kva = _kva(*validos[t])
        if kva < aj.fraccion_aislada * min(_kva(*validos[a]), _kva(*validos[b])):
            aisladas.add(t)
            _registro(apartados, 'aislada', t, kva)
    return {t: validos[t] for t in quedan if t not in aisladas}


def _instante(fecha: datetime, kw: float, kvar: float | None) -> dict[str, Any]:
    return {'fecha': fecha, 'kw': kw, 'kvar': kvar, 'kva': _kva(kw, kvar)}


def _ventana(puntos: Mapping[datetime, tuple[float, float | None]], aj: Ajustes, paso: timedelta | None,
             avisos: list[str]) -> dict[str, Any] | None:
    """Los N días contiguos de menor kVA medio, con sumas acumuladas de una pasada (RF-2, RF-7)."""
    n = aj.dias_ventana
    if n is None:
        avisos.append('El perfil no da valle.dias_ventana: se usa solo el instante mínimo (073:RF-3).')
        return None
    if paso is None or paso.total_seconds() <= 0:
        avisos.append(f'Sin registros bastantes para una ventana de {n} días (073:RF-7).')
        return None
    esperados = timedelta(days=1) / paso
    dias: dict[date, list] = {}
    for t in sorted(puntos):
        kw, q = puntos[t]
        fila = dias.setdefault(t.date(), [0, 0.0, 0.0, 0.0, None])
        kva = _kva(kw, q)
        fila[0] += 1
        fila[1] += kva
        fila[2] += kw
        fila[3] += q or 0.0
        if fila[4] is None or (kva, t) < fila[4]:
            fila[4] = (kva, t)
    mejor = None
    racha: list[date] = []
    for d in sorted(dias):
        if dias[d][0] < aj.cobertura_dia * esperados or (racha and d - racha[-1] != timedelta(days=1)):
            racha = []
        if dias[d][0] >= aj.cobertura_dia * esperados:
            racha.append(d)
        if len(racha) > n:
            racha.pop(0)
        if len(racha) == n:
            cuenta = sum(dias[x][0] for x in racha)
            media = sum(dias[x][1] for x in racha) / cuenta
            if mejor is None or media < mejor[0] - 1e-12:            # a igual media, la primera
                mejor = (media, list(racha), cuenta)
    if mejor is None:
        avisos.append(f'No hay {n} días contiguos con registros bastantes: sin ventana, solo el instante '
                      'mínimo (073:RF-7).')
        return None
    media, trozo, cuenta = mejor
    _kv, t = min(dias[x][4] for x in trozo)
    return {'desde': trozo[0], 'hasta': trozo[-1], 'dias': n, 'kva': media,
            'kw': sum(dias[x][2] for x in trozo) / cuenta, 'kvar': sum(dias[x][3] for x in trozo) / cuenta,
            'instante': _instante(t, *puntos[t])}


def valle_de_alcance(alcance: str, curvas: Mapping[str, Iterable[Sequence]], aj: Ajustes,
                     periodo: str | None = None) -> Valle:
    """El valle de un alcance (alimentadores, SET o sistema), con sus medidores sumados (RF-1 a RF-10).

    ``curvas``: medidor → ``(fecha, kW, kVAR)``. Con una central, su demanda y no su cabecera. Quién
    entra lo decide quien llama, por el análisis elegido en la web (028:RF-27).
    """
    v = Valle(alcance=alcance, periodo=periodo)
    limpias: dict[str, dict] = {}
    con_q = True
    for medidor in sorted(curvas):
        limpia, mide_q = _limpiar(curvas[medidor], periodo, aj, v.apartados)
        if limpia:
            limpias[medidor] = limpia
            con_q = con_q and mide_q
        else:
            v.excluidos.append(medidor)
            v.avisos.append(f'{medidor}: sin ningún registro válido: fuera de la suma (073:RF-8).')
    if not limpias:
        v.motivo = 'sin ningún registro válido de medición' + (f' en {periodo}' if periodo else '')
        return v
    # RF-8: un medidor con pocos registros dejaría sin instantes a todos; con varios, sale.
    todas = sorted({t for c in limpias.values() for t in c})
    paso = _paso(todas)
    if paso is not None and len(limpias) > 1:
        esperados = (todas[-1] - todas[0]) / paso + 1
        pobres = [m for m, c in limpias.items() if len(c) < aj.cobertura_medidor * esperados]
        if len(pobres) < len(limpias):
            for m in pobres:
                v.avisos.append(f'{m}: {len(limpias[m])} de {esperados:.0f} registros: fuera de la suma, para no '
                                'dejar sin instantes a los demás (073:RF-8).')
                v.excluidos.append(m)
                del limpias[m]
    v.excluidos.sort()
    if not con_q:
        v.avisos.append('Un medidor no mide kVAR: el valle va en kW, sin la potencia reactiva (073:RF-4).')
    comunes = set.intersection(*(set(c) for c in limpias.values()))
    for t in sorted({t for c in limpias.values() for t in c} - comunes):
        _registro(v.apartados, 'hueco', t, None)
    puntos: dict[datetime, tuple[float, float | None]] = {}
    for t in comunes:
        filas = [c[t] for c in limpias.values()]
        puntos[t] = (sum(f[0] for f in filas), sum(f[1] for f in filas) if con_q else None)
    if not puntos:
        v.motivo = 'ningún instante con registro de todos los medidores del alcance'
        return v
    t = min(puntos, key=lambda x: (_kva(*puntos[x]), x))
    v.comprobado = True
    v.registros = len(puntos)
    v.instante = _instante(t, *puntos[t])
    v.ventana = _ventana(puntos, aj, _paso(sorted(puntos)), v.avisos)
    return v
