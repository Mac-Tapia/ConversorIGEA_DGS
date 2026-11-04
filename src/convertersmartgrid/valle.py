"""El valle de un alcance: el periodo de menor energía registrada, desde la medición (spec 073).

Usuario, 2026-11-02: «el valle es registro de energía menos sin incluir valores ceros, eso sale de
los registros de mediciones, este término es usado en demandas eléctricas; el tiempo lo vas a sacar
de lo histórico registrado usando optimización; las demandas no son valle». Un banco fijo sigue
conectado cuando baja el consumo; la máxima no lo ve.

Puro y determinista. Leer es de ``demanda_medida``; medir la tensión, de quien llama. Un cero, un
hueco o una salida de servicio no son valle: se apartan con su motivo, porque un dato dudoso
definiría el número de bancos.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from .ajuste_cabecera import AjusteError, objetivo_de
from .demanda_medida import ALIAS, en_periodo, maximas

#: Lo que se aparta de la energía, con la frase que lo dice (RF-6).
MOTIVOS = {
    'hueco': 'a otro medidor del alcance le falta ese registro: la suma saldría baja sin serlo',
    'duplicado': 'la misma fecha y hora con valores distintos',
    'no_numerico': 'valor no finito',
    'signo': 'signo contrario al del medidor (desborde del contador o generación sin medir)',
    'cero': 'registro en cero: salida de servicio o medidor parado, no un valle',
    'congelado': 'el mismo valor repetido: medidor congelado',
    'sin_kvar': 'registro sin kVAR en un medidor que sí lo mide',
    'franja': 'muy por debajo de su misma hora en los demás días: salida de servicio o transferencia',
    'aislada': 'caída de un solo registro frente a sus vecinos: disparo o maniobra',
}
#: Con menos días por franja, su mediana no distingue una salida de un valle.
MUESTRAS_FRANJA_MINIMAS = 3
#: Un valle más corto que una semana no se distingue del ciclo semanal, y fuera de él hace falta
#: otro tanto con que compararlo (RF-35). Es el calendario, no una convención de empresa.
CICLO_SEMANAL = 7
#: Por debajo, el ruido de la serie es la precisión del medidor: en una serie limpia, ruido cero
#: quitaría toda la penalización y ganaría cualquier día suelto (RF-35).
RUIDO_RELATIVO_MINIMO = 0.005
#: Un día a más de tantas σ de la mediana de su semana es suelto: el corte habitual de Hampel es 3,
#: y aquí los festivos, que no llegan a un valle, también deben caer.
SIGMAS_DIA_SUELTO = 3.0
#: σ = mediana(|Δ|) / (0,6745·√2): robusto frente a los escalones de la propia ventana.
_NORMAL_MAD = 0.6745 * math.sqrt(2)

#: En valle, sin las cargas nuevas (el peor caso para la sobretensión) y con ellas: pueden ingresar
#: en cualquier momento (RF-39). Cada caso, con el factor que les aplica.
CASOS_CARGAS = (('sin_cargas', 0.0), ('con_cargas', 1.0))
NOMBRE_CASO = {'sin_cargas': 'sin cargas nuevas', 'con_cargas': 'con cargas nuevas'}


class ValleError(ValueError):
    """Un dato de ``valle`` en el perfil no vale: se dice cuál."""


@dataclass(frozen=True)
class Ajustes:
    """De ``valle`` en el perfil. No hay duración que dar: sale de los registros (RF-2).

    Son umbrales de limpieza y la penalización de la optimización, no convenciones de una empresa, y
    lo apartado siempre se ve con su valor.
    """
    cobertura_dia: float = 0.9              # fracción de registros de un día, y de días de la ventana (RF-7)
    cobertura_medidor: float = 0.5          # por debajo, el medidor sale de la suma (RF-8)
    fraccion_franja: float = 0.25           # frente a la mediana de su misma hora (RF-6)
    fraccion_aislada: float = 0.5           # frente al menor de sus dos vecinos (RF-6)
    registros_congelados: int = 8           # dos horas iguales, a 15 minutos (RF-6)
    penalizacion: float | None = None       # β de RF-35; sin él, 2·ln(días)


def ajustes_de(perfil: Mapping[str, Any]) -> Ajustes:
    """Los de ``valle`` del perfil; lo que no da, el valor de :class:`Ajustes`."""
    datos = dict(perfil.get('valle') or {})
    campos = {k: datos[k] for k in Ajustes.__dataclass_fields__ if datos.get(k) is not None}
    if 'penalizacion' in campos and float(campos['penalizacion']) < 0:
        raise ValleError(f"valle.penalizacion no puede ser negativa: {campos['penalizacion']} (073:RF-35)")
    return Ajustes(**campos)


@dataclass
class Valle:
    """El valle de un alcance. Sin ``comprobado``, el motivo y nada de instante (RF-10).

    ``ventana``: la del año que manda, el último con ella; ``ventanas``, la de cada año (RF-38).
    ``instante``: el punto para el flujo, el registro mínimo de la ventana (RF-1).
    """
    alcance: str
    comprobado: bool = False
    motivo: str = ''
    instante: dict[str, Any] | None = None
    ventana: dict[str, Any] | None = None
    ventanas: list[dict[str, Any]] = field(default_factory=list)
    coinciden: bool | None = None
    apartados: dict[str, dict[str, Any]] = field(default_factory=dict)
    excluidos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    registros: int = 0
    periodo: str | None = None
    anios: list[int] = field(default_factory=list)


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


#: Los medidores de una central en el perfil (021:RF-27), en el orden de ``curva_de_demanda``.
MEDIDORES_CENTRAL = ('generacion', 'llegada', 'salida')


def curva_con_central(curvas: Mapping[str, Sequence], cabecera: str,
                      central: Mapping[str, str]) -> tuple[list, str | None]:
    """La demanda de un alimentador con central, registro a registro, para buscarle el valle (073:RF-12, T9).

    Su cabecera no es su demanda: con la central generando, la cabecera baja y daría un valle que el
    alimentador no tiene. Se toma la de ``curva_de_demanda`` (021:RF-47), la misma con que se calibra.
    Devuelve ``(puntos, None)`` o ``([], motivo)``; nunca un error, porque el valle no bloquea (RF-24).
    """
    from .demanda_medida import clave_codigo, curva_de_demanda

    def de(medidor: str) -> Sequence | None:
        return next((c for m, c in curvas.items() if clave_codigo(m) == clave_codigo(medidor)), None)

    nombres = [cabecera, *((central.get(k) or '').strip() for k in MEDIDORES_CENTRAL)]
    leidas = [de(m) if m else None for m in nombres]
    faltan = [m or k for m, c, k in zip(nombres, leidas, ('cabecera', *MEDIDORES_CENTRAL)) if not c]
    if faltan:
        return [], f"sin curva de {', '.join(faltan)} para la demanda con la central"
    cab, gen, lle, sal = (list(c or ()) for c in leidas)
    puntos, res = curva_de_demanda(cab, gen, lle, sal)
    if not puntos:
        return [], f'sin demanda con la central ({res.error or "sin registros comunes"})'
    return puntos, None


def _registro(apartados: dict, clave: str, fecha: datetime | None, kw: float | None) -> None:
    fila = apartados.setdefault(clave, {'motivo': MOTIVOS[clave], 'registros': 0, 'menor_kw': None, 'primera': None})
    fila['registros'] += 1
    if kw is not None and (fila['menor_kw'] is None or kw < fila['menor_kw']):
        fila['menor_kw'] = kw
    if fecha is not None and (fila['primera'] is None or fecha < fila['primera']):
        fila['primera'] = fecha


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
        if kw == 0:                              # antes que congelado: días en cero son un cero (RF-6)
            _registro(apartados, 'cero', t, kw)
        elif t in congelados:
            _registro(apartados, 'congelado', t, kw)
        elif kw < 0:
            _registro(apartados, 'signo', t, kw)
        elif mide_q and q is None:
            _registro(apartados, 'sin_kvar', t, kw)
        else:
            validos[t] = (kw, q)
    return _sin_caidas(validos, aj, apartados), mide_q


def _paso(fechas: Sequence[datetime]) -> timedelta | None:
    """El intervalo del medidor: la mediana de sus diferencias, sin suponer 15 minutos."""
    if len(fechas) < 2:
        return None
    return statistics.median(b - a for a, b in pairwise(fechas))


def _sin_caidas(validos: dict, aj: Ajustes, apartados: dict) -> dict:
    """Sin lo que cae frente a su misma hora o a sus vecinos (RF-6).

    La noche baja todas las noches y su franja baja con ella; una salida de servicio baja una vez.
    """
    franjas: dict[tuple[int, int], list[float]] = {}
    for t, (kw, _q) in validos.items():
        franjas.setdefault((t.hour, t.minute), []).append(kw)
    medianas = {k: statistics.median(v) for k, v in franjas.items() if len(v) >= MUESTRAS_FRANJA_MINIMAS}
    fechas = sorted(validos)
    quedan = []
    for t in fechas:
        kw, ref = validos[t][0], medianas.get((t.hour, t.minute))
        if ref is not None and kw < aj.fraccion_franja * ref:
            _registro(apartados, 'franja', t, kw)
        else:
            quedan.append(t)
    paso = _paso(quedan)
    aisladas = set()
    for a, t, b in zip(quedan, quedan[1:], quedan[2:], strict=False):
        if paso is None or b - a > 2 * paso:             # sin los dos vecinos no se sabe
            continue
        if validos[t][0] < aj.fraccion_aislada * min(validos[a][0], validos[b][0]):
            aisladas.add(t)
            _registro(apartados, 'aislada', t, validos[t][0])
    return {t: validos[t] for t in quedan if t not in aisladas}


def _instante(fecha: datetime, kw: float, kvar: float | None) -> dict[str, Any]:
    return {'fecha': fecha, 'kw': kw, 'kvar': kvar, 'por_medidor': {}}


# =========================================================================== la optimización (RF-35)
def _sin_ciclo_semanal(fechas: Sequence[date], x: Sequence[float]) -> list[float]:
    """La serie sin el ciclo de la semana, solo para buscar: un domingo no es un valle."""
    centro = statistics.median(x)
    por_dia: dict[int, list[float]] = {}
    for d, v in zip(fechas, x, strict=True):
        por_dia.setdefault(d.weekday(), []).append(v)
    if not centro or min((len(v) for v in por_dia.values()), default=0) < MUESTRAS_FRANJA_MINIMAS or len(por_dia) < CICLO_SEMANAL:
        return list(x)
    factor = {k: statistics.median(v) / centro for k, v in por_dia.items()}
    return [v / factor[d.weekday()] if factor[d.weekday()] else v for d, v in zip(fechas, x, strict=True)]


def _ruido(fechas: Sequence[date], y: Sequence[float]) -> float:
    """El ruido de un día a otro; no el escalón de la ventana, que solo son dos diferencias."""
    saltos = [abs(b - a) for a, b, d0, d1 in zip(y, y[1:], fechas, fechas[1:], strict=False)
              if d1 - d0 == timedelta(days=1)]
    medido = statistics.median(saltos) / _NORMAL_MAD if saltos else 0.0
    return max(medido, RUIDO_RELATIVO_MINIMO * statistics.median(y))


def _sin_dias_sueltos(y: Sequence[float], sigma: float) -> list[float]:
    """Un día raro, solo para buscar, pasa a la mediana de su semana (filtro de Hampel).

    Un día al 30 % en una serie plana compensaba toda la penalización: la ventana mínima lo contenía y
    ganaba. Un periodo de una semana o más sobrevive: dentro de él, la mediana es la suya.
    """
    medio = CICLO_SEMANAL // 2
    out = list(y)
    for i, v in enumerate(y):
        ref = statistics.median(y[max(0, i - medio):i + medio + 1])
        if abs(v - ref) > SIGMAS_DIA_SUELTO * sigma:
            out[i] = ref
    return out


def _serie_de_busqueda(fechas: Sequence[date], kwh: Sequence[float]) -> tuple[list[float], float]:
    """La serie con la que se busca, sin el ciclo semanal ni los días sueltos, y su ruido."""
    y = _sin_ciclo_semanal(fechas, kwh)
    sigma = _ruido(fechas, y)
    return _sin_dias_sueltos(y, sigma), sigma


def optimizar_ventana(fechas: Sequence[date], kwh: Sequence[float], *, cobertura: float,
                      penalizacion: float | None = None) -> dict[str, Any] | None:
    """Inicio y duración del valle en una serie diaria de energía, por búsqueda exacta (RF-35).

    Parte la serie en dos niveles, dentro y fuera de la ventana, y minimiza

        J(i, j) = SSE dentro + SSE fuera + β·σ²·D/L

    entre todas las ventanas de días contiguos, con L días dentro de D, β = 2·ln(D) (o el del perfil)
    y σ el ruido de la serie. La penalización crece al acortar la ventana, para que no gane un día
    raro, y el resultado tiene que mejorar la serie sin ventana; si no, no hay valle diferenciado.
    Con sumas acumuladas cuesta O(D²) en una serie de un año, unos milisegundos: la búsqueda exacta
    cabe, y da el óptimo sin sortear nada, así que no lleva semilla ni necesita un genético.
    """
    d = len(fechas)
    if d < 2 * CICLO_SEMANAL:
        return None
    y, sigma = _serie_de_busqueda(fechas, kwh)
    beta = 2 * math.log(d) if penalizacion is None else float(penalizacion)
    suma = [0.0]
    cuad = [0.0]
    for v in y:
        suma.append(suma[-1] + v)
        cuad.append(cuad[-1] + v * v)
    total_sse = cuad[d] - suma[d] ** 2 / d
    mejor, evaluadas = None, 0
    for i in range(d):
        for j in range(i + CICLO_SEMANAL - 1, d):
            n = j - i + 1
            if d - n < CICLO_SEMANAL:
                break
            span = (fechas[j] - fechas[i]).days + 1
            if (span - n) > (1 - cobertura) * span:
                continue
            evaluadas += 1
            s_in, s_out = suma[j + 1] - suma[i], suma[d] - suma[j + 1] + suma[i]
            if s_in / n >= s_out / (d - n):
                continue
            c_in = cuad[j + 1] - cuad[i]
            sse = c_in - s_in ** 2 / n + (cuad[d] - c_in) - s_out ** 2 / (d - n)
            costo = sse + beta * sigma ** 2 * d / n
            # A igual costo, la primera y la más corta: determinismo.
            if mejor is None or costo < mejor[0] - 1e-9 * max(total_sse, 1.0):
                mejor = (costo, i, j)
    if mejor is None or mejor[0] >= total_sse:
        return None
    costo, i, j = mejor
    dentro = kwh[i:j + 1]
    fuera = [*kwh[:i], *kwh[j + 1:]]
    return {'inicio': fechas[i], 'fin': fechas[j], 'duracion_dias': (fechas[j] - fechas[i]).days + 1,
            'dias_con_dato': j - i + 1, 'kwh_dia_dentro': statistics.fmean(dentro),
            'kwh_dia_fuera': statistics.fmean(fuera),
            'optimizacion': {'metodo': 'búsqueda exacta de la ventana de días contiguos, dos niveles con penalización',
                             'objetivo': costo, 'objetivo_sin_ventana': total_sse, 'penalizacion_beta': beta,
                             'ruido_kwh_dia': sigma, 'dias_minimos': CICLO_SEMANAL, 'ventanas_evaluadas': evaluadas,
                             'semilla': None}}


def _energia_por_dia(puntos: Mapping[datetime, tuple]) -> dict[date, list]:
    """kWh por día: la media del kW del día por 24 h; un día con un 5 % de huecos no parece valle."""
    dias: dict[date, list] = {}
    for t in sorted(puntos):
        kw = puntos[t][0]
        fila = dias.setdefault(t.date(), [0, 0.0, None])
        fila[0] += 1
        fila[1] += kw
        if fila[2] is None or (kw, t) < fila[2]:
            fila[2] = (kw, t)
    return dias


def _ventana_del_anio(anio: int, puntos: Mapping[datetime, tuple], aj: Ajustes, paso: timedelta,
                      avisos: list[str]) -> dict[str, Any] | None:
    """La ventana de un año, con los días que tienen registros bastantes (RF-2, RF-7, RF-35)."""
    esperados = timedelta(days=1) / paso
    dias = _energia_por_dia(puntos)
    validos = [d for d in sorted(dias) if dias[d][0] >= aj.cobertura_dia * esperados]
    if len(validos) < 2 * CICLO_SEMANAL:
        avisos.append(f'{anio}: {len(validos)} días con registros bastantes: no alcanzan para buscar un valle (073:RF-37).')
        return None
    kwh = [dias[d][1] / dias[d][0] * 24.0 for d in validos]
    v = optimizar_ventana(validos, kwh, cobertura=aj.cobertura_dia, penalizacion=aj.penalizacion)
    if v is None:
        avisos.append(f'{anio}: la energía de sus registros no da un periodo diferenciado de menor energía (073:RF-37).')
        return None
    dentro = [d for d in validos if v['inicio'] <= d <= v['fin']]
    _kw, t = min(dias[d][2] for d in dentro)
    v.update(anio=anio, instante=_instante(t, *puntos[t]))
    if v['kwh_dia_dentro'] < aj.fraccion_aislada * v['kwh_dia_fuera']:
        # En la medición real, alimentadores con una ventana de meses al 4 % del resto: una baja así no
        # sale del consumo, y puede ser una transferencia o una salida larga que los filtros no ven.
        avisos.append(f"{anio}: dentro del valle hay {v['kwh_dia_dentro']:,.0f} kWh/día y fuera {v['kwh_dia_fuera']:,.0f}: "
                      'revise si es una transferencia o una salida larga (073:RF-36).')
    if v['inicio'] == validos[0] or v['fin'] == validos[-1]:
        avisos.append(f"{anio}: el valle toca el borde de los registros ({v['inicio']} a {v['fin']}): puede seguir en el "
                      'periodo contiguo, que aquí no se ve (073:RF-36).')
    return v


def _se_solapan(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Por el día del año: 2025 y 2026 no comparten fechas, pero sí la época."""
    def tramos(v):
        i, f = v['inicio'].timetuple().tm_yday, v['fin'].timetuple().tm_yday
        return [(i, f)] if i <= f else [(i, 366), (1, f)]
    return any(x0 <= y1 and y0 <= x1 for x0, x1 in tramos(a) for y0, y1 in tramos(b))


def valle_de_alcance(alcance: str, curvas: Mapping[str, Iterable[Sequence]], aj: Ajustes,
                     periodo: str | None = None) -> Valle:
    """El valle de un alcance (alimentadores, SET o sistema), con sus medidores sumados (RF-1 a RF-10).

    ``curvas``: medidor → ``(fecha, kW, kVAR)``, de una sola fuente. Con una central, su demanda y no
    su cabecera. Quién entra lo decide quien llama, por el análisis elegido en la web (028:RF-27).
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
        v.avisos.append('Un medidor no mide kVAR: el punto de valle va sin su potencia reactiva (073:RF-4).')
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
    v.comprobado = True
    v.registros = len(puntos)
    # RF-38: cada año por su cuenta: con varios, un año de más consumo no es «fuera del valle».
    v.anios = sorted({t.year for t in puntos})
    paso = _paso(sorted(puntos))
    for anio in v.anios:
        del_anio = {t: x for t, x in puntos.items() if t.year == anio}
        ventana = _ventana_del_anio(anio, del_anio, aj, paso, v.avisos) if paso else None
        if ventana:
            v.ventanas.append(ventana)
    if len(v.ventanas) > 1:
        v.coinciden = all(_se_solapan(a, b) for i, a in enumerate(v.ventanas) for b in v.ventanas[i + 1:])
        v.avisos.append(('Las ventanas de ' if v.coinciden else 'Las ventanas NO coinciden entre ')
                        + ', '.join(str(x['anio']) for x in v.ventanas)
                        + (' coinciden en la época del año (073:RF-38).' if v.coinciden else ' (073:RF-38).'))
    menor = min(puntos, key=lambda t: (puntos[t][0], t))
    if v.ventanas:
        v.ventana = v.ventanas[-1]
        v.instante = v.ventana['instante']
        if menor != v.instante['fecha']:
            v.avisos.append(f"El registro menor, {puntos[menor][0]:,.1f} kW el {menor}, queda fuera del valle: el punto para "
                            f"el flujo es el mínimo del valle, {v.instante['kw']:,.1f} kW el {v.instante['fecha']} (073:RF-1).")
    else:
        v.instante = _instante(menor, *puntos[menor])
        v.avisos.append(f'Sin periodo diferenciado de menor energía: se usa el registro menor, el {menor} (073:RF-37).')
    for ventana in v.ventanas:
        ventana['instante']['por_medidor'] = {m: c[ventana['instante']['fecha']] for m, c in limpias.items()}
    v.instante['por_medidor'] = {m: c[v.instante['fecha']] for m, c in limpias.items()}
    return v


def _factor(valor: float | None, maxima: float | None) -> float | None:
    return None if valor is None or not maxima else valor / maxima


def _punto(etiqueta: str, inst: Mapping[str, Any], maximas: Mapping[str, Mapping[str, Any]], kw_max: float,
           kvar_max: float | None) -> dict[str, Any]:
    """Un instante medido con sus factores sobre la máxima, en la forma del plan del guion (RF-22)."""
    por_alim: dict[str, list[float]] = {}
    for m, (kw, _q) in inst['por_medidor'].items():
        fila = por_alim.setdefault(str(maximas[m].get('alimentador') or m), [0.0, 0.0])
        fila[0] += kw
        fila[1] += float(maximas[m]['kw'])
    factor_p = inst['kw'] / kw_max
    factor_q = _factor(inst['kvar'], kvar_max)
    return {'etiqueta': etiqueta, 'fecha': inst['fecha'].isoformat(sep=' '), 'kw': inst['kw'], 'kvar': inst['kvar'],
            'factor_p': factor_p, 'factor_q': factor_p if factor_q is None else factor_q, 'origen': 'medicion',
            'factores': {a: x / y for a, (x, y) in sorted(por_alim.items()) if y}}


def _ventana_para_informe(v: Mapping[str, Any]) -> dict[str, Any]:
    return {'anio': v['anio'], 'inicio': str(v['inicio']), 'fin': str(v['fin']), 'duracion_dias': v['duracion_dias'],
            'dias_con_dato': v['dias_con_dato'], 'kwh_dia_dentro': v['kwh_dia_dentro'], 'kwh_dia_fuera': v['kwh_dia_fuera'],
            'optimizacion': v['optimizacion']}


def puntos_de_valle(v: Valle, maximas: Mapping[str, Mapping[str, Any]],
                    pronostico: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Lo que mide la escalera: el registro mínimo del valle, con sus factores (RF-1, RF-22).

    ``maximas``: medidor → ``alimentador``, ``kw`` y ``kvar`` de su calibración. ``pronostico``: el
    valle de un año futuro de la spec 046, que viaja como dato: un pronóstico nunca sustituye a una
    medición, así que sin medición sigue sin comprobarse (RF-33).
    """
    base = {'comprobado': False, 'motivo': v.motivo, 'avisos': list(v.avisos), 'puntos': [], 'pronostico': pronostico,
            'anios': list(v.anios), 'coinciden': v.coinciden, 'ventanas': [_ventana_para_informe(x) for x in v.ventanas],
            'apartados': {k: {**x, 'primera': str(x['primera']) if x['primera'] else None}
                          for k, x in v.apartados.items()}}
    if not v.comprobado or v.instante is None:
        return base
    usados = {m: maximas.get(m) or {} for m in v.instante['por_medidor']}
    if any(not d.get('kw') for d in usados.values()):
        return {**base, 'motivo': 'sin la máxima de todos los medidores del alcance para comparar el valle'}
    kw_max = sum(float(d['kw']) for d in usados.values())
    kvar_max = (sum(float(d['kvar']) for d in usados.values())
                if all(d.get('kvar') is not None for d in usados.values()) else None)
    if v.instante['kvar'] is None or not kvar_max:
        base['avisos'].append('Sin el kVAR del valle o el de la máxima: la Q se escala como la P (073:RF-22).')
    etiqueta = (f"mínimo del valle del {v.ventana['inicio']} al {v.ventana['fin']}" if v.ventana
                else 'registro menor, sin periodo diferenciado')
    punto = _punto(etiqueta, v.instante, usados, kw_max, kvar_max)
    # RF-8: el alimentador de un medidor fuera de la suma no se queda en su máxima: en el valle del
    # conjunto baja como los demás.
    for d in maximas.values():
        punto['factores'].setdefault(str(d.get('alimentador')), punto['factor_p'])
    return {**base, 'comprobado': True, 'puntos': [punto]}


def sin_comprobar(motivo: str | None = None) -> dict[str, Any]:
    """Lo que se sabe de una variante sin puntos de valle: nada (RF-24, RF-31)."""
    return {'valle': None, 'valle_motivos': [], 'valle_u_max': None, 'valle_nodo': None, 'valle_fecha': None,
            'valle_sin_comprobar': motivo or None, 'valle_casos': {}}


def anotar_punto(fila: dict[str, Any], punto: Mapping[str, Any], caso: str, ok: bool, motivos: Sequence[str],
                 tensiones: Mapping[str, float]) -> None:
    """Suma a ``fila`` lo medido en un punto y un caso: oráculo y guion lo cuentan igual (RF-17, RF-30, RF-39)."""
    if fila.get('valle') is None:
        fila.update(valle=True, valle_sin_comprobar=None)
    de_caso = fila['valle_casos'].setdefault(caso, {'cumple': True, 'u_max': None, 'nodo': None, 'fecha': None})
    if not ok:
        fila['valle'] = False
        de_caso['cumple'] = False
        fila['valle_motivos'] = (fila['valle_motivos']
                                 + [f"{m} ({NOMBRE_CASO.get(caso, caso)}, {punto.get('etiqueta')}, {punto.get('fecha')})"
                                    for m in motivos])[:5]
    if tensiones:
        nodo = max(sorted(tensiones), key=tensiones.__getitem__)
        if de_caso['u_max'] is None or tensiones[nodo] > de_caso['u_max']:
            de_caso.update(u_max=tensiones[nodo], nodo=nodo, fecha=punto.get('fecha'))
        if fila['valle_u_max'] is None or tensiones[nodo] > fila['valle_u_max']:
            fila.update(valle_u_max=tensiones[nodo], valle_nodo=nodo, valle_fecha=punto.get('fecha'))


def nombre_caso_valle(anio: int | None) -> str:
    """El caso y el escenario de la calibración a valle, como ``tools/casos_pf.nombre_caso`` (RF-13)."""
    return f'Valle {anio}' if anio else 'Valle'


def filas_de_calibracion(rutas: Iterable[Path | str], pares: Sequence[tuple[str, str]], instante: datetime, *,
                         alias=ALIAS, cabecera=None) -> list[dict[str, Any]]:
    """La cabecera de cada medidor en el instante de valle, con la lectura de la máxima coincidente
    (021:RF-50), en la forma que recibe la calibración (RF-16)."""
    return [r.to_dict() for r in maximas(rutas, list(pares), alias=alias, instante=instante, cabecera=cabecera)]


def plan_calibracion_valle(v: Valle, filas: Sequence[Mapping[str, Any]], anio: int | None) -> dict[str, Any]:
    """El contrato de la calibración a valle (RF-13, RF-14, RF-16): la misma máquina, en otro instante.

    No se ejecuta aún (T8): el guion de la calibración lee «Sin proyecto» y guarda la última
    calibración de la que vive la escalera, y a ciegas machacaría la de la máxima. Las fijas van
    coincidentes con esa hora (039:RF-1): el máximo del mes no es valle.
    """
    nombre = nombre_caso_valle(anio)
    plan = {'rol': 'valle', 'caso': nombre, 'escenario': nombre, 'copia_de': f'Sin proyecto {anio}' if anio else 'Sin proyecto',
            'criterio_fijas': 'coincidente', 'ejecutable': False,
            'pendiente': 'separar en el guion la calibración a valle de la de la máxima y probarla en DIgSILENT (073 T8)',
            'motivo': v.motivo, 'instante': None, 'objetivos': [], 'avisos': []}
    if not v.comprobado or v.instante is None:
        return plan
    plan['instante'] = v.instante['fecha'].isoformat(sep=' ')
    for fila in filas:
        try:
            o = objetivo_de(fila)
        except AjusteError as exc:
            plan['avisos'].append(str(exc))
            continue
        plan['objetivos'].append({'alimentador': o.alimentador, 'medidor': o.medidor, 'kw': o.kw, 'kvar': o.kvar,
                                  'fecha': o.fecha})
    return plan


def _coma(u: float) -> str:
    return f'{u:.3f}'.replace('.', ',')


def frase_valle(fila: Mapping[str, Any] | None) -> str:
    """La tensión en valle de una alternativa, en una frase, con los dos casos de las cargas nuevas
    (RF-30, RF-31, RF-39): sin medición, nunca «cumple»."""
    fila = fila or {}
    u = fila.get('valle_u_max')
    if fila.get('valle') is None or u is None:
        motivo = fila.get('valle_sin_comprobar')
        return 'no comprobado en valle' + (f' ({motivo})' if motivo else '')
    texto = f"tensión máxima en valle de {_coma(u)} p.u. en {fila.get('valle_nodo')} el {fila.get('valle_fecha')}"
    casos = fila.get('valle_casos') or {}
    detalle = [f"{NOMBRE_CASO.get(c, c)} {_coma(casos[c]['u_max'])} p.u. en {casos[c]['nodo']}"
               + ('' if casos[c]['cumple'] else ', no cumple')
               for c, _f in CASOS_CARGAS if (casos.get(c) or {}).get('u_max') is not None]
    if detalle:
        texto += f" ({'; '.join(detalle)})"
    return texto + ('' if fila.get('valle') else ': no admisible')
