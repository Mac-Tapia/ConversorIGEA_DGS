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
from itertools import pairwise
from pathlib import Path
from typing import Any

from .ajuste_cabecera import AjusteError, objetivo_de
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
    return statistics.median(b - a for a, b in pairwise(fechas))


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
    return {'fecha': fecha, 'kw': kw, 'kvar': kvar, 'kva': _kva(kw, kvar), 'por_medidor': {}}


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
    for inst in (v.instante, (v.ventana or {}).get('instante')):
        if inst:
            inst['por_medidor'] = {m: c[inst['fecha']] for m, c in limpias.items()}
    return v


def _factor(valor: float | None, maxima: float | None) -> float | None:
    return None if valor is None or not maxima else valor / maxima


def _punto(etiqueta: str, inst: Mapping[str, Any], maximas: Mapping[str, Mapping[str, Any]], kw_max: float,
           kvar_max: float | None, aj: Ajustes) -> dict[str, Any]:
    """Un instante medido con sus factores sobre la máxima, en la forma del plan del guion (RF-22)."""
    por_alim: dict[str, list[float]] = {}
    for m, (kw, _q) in inst['por_medidor'].items():
        fila = por_alim.setdefault(str(maximas[m].get('alimentador') or m), [0.0, 0.0])
        fila[0] += kw
        fila[1] += float(maximas[m]['kw'])
    factor_p = inst['kw'] / kw_max
    factor_q = _factor(inst['kvar'], kvar_max)
    return {'etiqueta': etiqueta, 'fecha': inst['fecha'].isoformat(sep=' '), 'kw': inst['kw'], 'kvar': inst['kvar'],
            'kva': inst['kva'], 'factor_p': factor_p, 'factor_q': factor_p if factor_q is None else factor_q,
            'factor_nuevas': aj.factor_cargas_nuevas, 'origen': 'medicion',
            'factores': {a: x / y for a, (x, y) in sorted(por_alim.items()) if y}}


def puntos_de_valle(v: Valle, maximas: Mapping[str, Mapping[str, Any]], aj: Ajustes,
                    pronostico: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Lo que mide la escalera: el instante mínimo y el mínimo de la ventana, si es otro (RF-22).

    ``maximas``: medidor → ``alimentador``, ``kw`` y ``kvar`` de su calibración. ``pronostico``: el
    valle de un año futuro de la spec 046, que viaja como dato: un pronóstico nunca sustituye a una
    medición, así que sin medición sigue sin comprobarse (RF-33).
    """
    base = {'comprobado': False, 'motivo': v.motivo, 'avisos': list(v.avisos), 'puntos': [], 'pronostico': pronostico,
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
    puntos = [_punto('instante mínimo', v.instante, usados, kw_max, kvar_max, aj)]
    if v.ventana and v.ventana['instante']['fecha'] != v.instante['fecha']:
        puntos.append(_punto(f"mínimo de la ventana del {v.ventana['desde']} al {v.ventana['hasta']}",
                             v.ventana['instante'], usados, kw_max, kvar_max, aj))
    # RF-8: el alimentador de un medidor fuera de la suma no se queda en su máxima: en el valle del
    # conjunto baja como los demás.
    for d in maximas.values():
        for pt in puntos:
            pt['factores'].setdefault(str(d.get('alimentador')), pt['factor_p'])
    return {**base, 'comprobado': True, 'puntos': puntos}


def sin_comprobar(motivo: str | None = None) -> dict[str, Any]:
    """Lo que se sabe de una variante sin puntos de valle: nada (RF-24, RF-31)."""
    return {'valle': None, 'valle_motivos': [], 'valle_u_max': None, 'valle_nodo': None, 'valle_fecha': None,
            'valle_sin_comprobar': motivo or None}


def anotar_punto(fila: dict[str, Any], punto: Mapping[str, Any], ok: bool, motivos: Sequence[str],
                 tensiones: Mapping[str, float]) -> None:
    """Suma a ``fila`` lo medido en un punto: oráculo y guion lo cuentan igual (RF-17, RF-30)."""
    if fila.get('valle') is None:
        fila.update(valle=True, valle_sin_comprobar=None)
    if not ok:
        fila['valle'] = False
        fila['valle_motivos'] = (fila['valle_motivos']
                                 + [f"{m} ({punto.get('etiqueta')}, {punto.get('fecha')})" for m in motivos])[:5]
    if tensiones:
        nodo = max(sorted(tensiones), key=tensiones.__getitem__)
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


def frase_valle(fila: Mapping[str, Any] | None) -> str:
    """La tensión en valle de una alternativa, en una frase (RF-30, RF-31): sin medición, nunca «cumple»."""
    fila = fila or {}
    u = fila.get('valle_u_max')
    if fila.get('valle') is None or u is None:
        motivo = fila.get('valle_sin_comprobar')
        return 'no comprobado en valle' + (f' ({motivo})' if motivo else '')
    texto = f"tensión máxima en valle de {u:.3f}".replace('.', ',')
    return (f"{texto} p.u. en {fila.get('valle_nodo')} el {fila.get('valle_fecha')}"
            + ('' if fila.get('valle') else ': sobrepasa lo admisible'))
