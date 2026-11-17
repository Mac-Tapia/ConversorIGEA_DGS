"""Demanda regulatoria del PIT, paso 3d (107 T30): la historia (F-104, F-105), los modelos comparados (F-106, F-107) y
los resúmenes (F-119 a F-122), llenados por el motor común de plantillas.

- F-104: las variables explicativas del Área de Demanda en los 20 años anteriores al representativo y en él (años −20 a
  0 de la plantilla), con su tasa de crecimiento; el PBI y la población salen del registro de exógenas de la spec 031
  (``historia_desde_exogenas``), con lo publicado hasta el corte, y el PBI va en millones de soles constantes;
- F-105: las ventas históricas de los usuarios regulados por nivel (AT, MT y BT, sin pérdidas) y su total;
- F-106 (método de tendencias, por sistema eléctrico) y F-107 (método econométrico, del área): las proyecciones de los
  modelos comparados, con su ecuación, su r², su t y su F (y su probabilidad) tal como los dio la proyección;
- F-119: la energía global por nivel (MAT, AT y MT) en GWh, suma de F-109 (regulados) y F-115 (libres); F-120 a F-122:
  por barra, la suma de F-110 a F-112 (regulados) con F-116 a F-118 (libres), y la tasa de crecimiento promedio (TC).

Nada se supone: sin una fuente, su formato sale como plantilla con la causa; sin la proyección de los usuarios libres,
los resúmenes no se suman (la nota de cada formato pide la suma de los dos) y lo dicen, salvo que el perfil declare que el
área no tiene usuarios libres. Las filas de totales por nivel de F-109 a F-112 y F-120 a F-122 se nombran como hueco.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError
from .plantillas import celdas_de_formato, horizonte_de_la_norma

__all__ = ['HISTORIA', 'HUECO_TOTALES', 'MAX_MODELOS', 'celdas_historia', 'celdas_modelos', 'celdas_resumen',
           'historia_desde_exogenas', 'resumen_demanda']

#: Años de la historia de F-104 y F-105: los trae escritos la plantilla (−20 a 0) y el mapeo los declara.
HISTORIA = range(-20, 1)
#: Columnas de modelos de F-106 y F-107 (Modelo 1, 2, 3, «…» y Modelo n).
MAX_MODELOS = 5
#: Variables de F-104 y su campo; ``otras`` lleva su nombre aparte (la columna «NOMINACIÓN»).
VARIABLES_F104 = ('pbi', 'clientes', 'poblacion', 'otras')
NIVELES_F105 = ('at', 'mt', 'bt')
HUECO_TOTALES = ('filas de totales por nivel (TOTAL MAT, AT, MT y del área): la plantilla los pone en la columna B y el '
                 'conversor aún no los escribe; cada barra lleva su valor')


def _tasa(actual: Any, previo: Any) -> float | None:
    if not isinstance(actual, (int, float)) or not isinstance(previo, (int, float)) or not previo:
        return None
    return (actual / previo - 1) * 100


def historia_desde_exogenas(registro_exo: Any, region: str, anio_representativo: int, corte: str) -> dict[str, Any]:
    """F-104 desde el registro de exógenas de la 031 (``proyeccion_anual.RegistroExogenas``): PBI y población del área
    con lo publicado hasta ``corte`` (031:RF-20). El PBI va a millones de soles solo si su unidad es de soles."""
    from ..proyeccion_anual import exogenas_al_corte

    al_corte = exogenas_al_corte(registro_exo, region, corte)
    unidades = {c.variable: c.unidad for c in registro_exo.cifras if c.tipo == 'nivel'}
    pbi_en_soles = 'soles' in str(unidades.get('pbi', ''))
    anios: dict[int, dict[str, Any]] = {}
    motivos: dict[str, str] = {}
    for k in HISTORIA:
        a = anio_representativo + k
        pbi = al_corte['niveles']['pbi'].get(a)
        anios[a] = {'pbi': pbi / 1e6 if pbi is not None and pbi_en_soles else None,
                    'poblacion': al_corte['niveles']['poblacion'].get(a)}
    if not pbi_en_soles:
        motivos['pbi'] = f'el PBI del registro va en «{unidades.get("pbi")}» y el F-104 lo pide en millones de soles'
    motivos.setdefault('clientes', 'el registro de exógenas de la 031 no trae el número de clientes')
    return {'anio_representativo': anio_representativo, 'exogenas': anios, 'motivos': motivos,
            'fuente_exogenas': {'region': al_corte['region'], 'corte': al_corte['corte'],
                                'registro': registro_exo.nombre, 'huella': registro_exo.huella}}


def _filas_historia(anio_rep: int, por_anio: Mapping[int, Mapping[str, Any]], campos: Sequence[str],
                    motivos: Mapping[str, str], con_tasa: bool) -> list[dict[str, Any]]:
    filas = []
    for k in HISTORIA:
        a = anio_rep + k
        actual, previo = por_anio.get(a) or {}, por_anio.get(a - 1) or {}
        fila: dict[str, Any] = {'_motivos': {}}
        for c in campos:
            fila[c] = actual.get(c)
            if fila[c] is None:
                fila['_motivos'][c] = motivos.get(c) or f'la fuente no trae {c} del año {a}'
            if con_tasa:
                fila[f'{c}_tasa'] = _tasa(actual.get(c), previo.get(c))
                if fila[f'{c}_tasa'] is None:
                    fila['_motivos'][f'{c}_tasa'] = f'sin {c} de {a} o de {a - 1}: la tasa no se supone'
        filas.append(fila)
    return filas


def celdas_historia(registro: RegistroNormativo, historia: Mapping[str, Any] | None, fuente: Mapping[str, str],
                    fecha: str | None = None) -> dict[str, Any]:
    """F-104 y F-105. ``historia``: ``area``, ``anio_representativo``, ``exogenas`` (año → pbi, clientes, poblacion,
    otras), ``nombre_otras``, ``ventas`` (año → at, mt, bt en MWh) y ``motivos`` (campo → por qué falta)."""
    if not historia:
        return {}
    anio = int(historia['anio_representativo'])
    motivos = historia.get('motivos') or {}
    salida = {}
    if historia.get('exogenas') is not None:
        filas = _filas_historia(anio, historia['exogenas'], VARIABLES_F104, motivos, True)
        cab = {'area': historia.get('area'), 'nombre_otras': historia.get('nombre_otras')}
        salida['F-104'] = celdas_de_formato(registro, 'F-104', {'fuente': fuente, 'cabecera': cab,
                                                                'bloques': {'anios': filas}}, fecha=fecha)
    if historia.get('ventas') is not None:
        filas = _filas_historia(anio, historia['ventas'], NIVELES_F105, motivos, False)
        for f in filas:
            vals = [f[n] for n in NIVELES_F105]
            f['total'] = sum(vals) if all(isinstance(v, (int, float)) for v in vals) else None
            if f['total'] is None:
                f['_motivos']['total'] = 'falta la venta de algún nivel: el total no se supone'
        salida['F-105'] = celdas_de_formato(registro, 'F-105', {'fuente': fuente, 'cabecera': {'area': historia.get('area')},
                                                                'bloques': {'anios': filas}}, fecha=fecha)
    return salida


def celdas_modelos(registro: RegistroNormativo, codigo: str, nombre: str, modelos: Sequence[Mapping[str, Any]],
                   fuente: Mapping[str, str], fecha: str | None = None) -> dict[str, Any]:
    """F-106 (``nombre`` = el sistema eléctrico) o F-107 (``nombre`` = el área): por modelo, su ``nombre``, su
    ``proyeccion`` (MWh, años 0..horizonte), ``ecuacion``, ``r2``, ``f`` y ``f_prob``, y ``t`` (F-106: valor y prob.;
    F-107: variable → valor y prob.). Un modelo de más no cabe en la plantilla y lo dice el hueco."""
    horizonte = horizonte_de_la_norma(registro, fecha)
    usados = list(modelos)[:MAX_MODELOS]
    cab: dict[str, Any] = {'nombre': nombre}
    filas = [{'_motivos': {}} for _ in range(horizonte + 1)]
    variables: list[str] = []
    for k, m in enumerate(usados, start=1):
        cab[f'modelo_{k}'] = m.get('nombre')
        serie = list(m.get('proyeccion') or ())
        for i, f in enumerate(filas):
            f[f'modelo_{k}'] = serie[i] if i < len(serie) else None
            if f[f'modelo_{k}'] is None:
                f['_motivos'][f'modelo_{k}'] = f'el modelo {m.get("nombre")} no trae el año {i}'
        cab[f'ecuacion_{k}'], cab[f'r2_{k}'] = m.get('ecuacion'), m.get('r2')
        cab[f'f_valor_{k}'], cab[f'f_prob_{k}'] = m.get('f'), m.get('f_prob')
        t = m.get('t') or {}
        if codigo == 'F-106':
            cab[f't_valor_{k}'], cab[f't_prob_{k}'] = (t.get('valor'), t.get('prob')) if isinstance(t, Mapping) else (None, None)
        else:
            for var in t:
                if var not in variables:
                    variables.append(var)
            for j, var in enumerate(variables[:4], start=1):
                valor, prob = (t.get(var) or (None, None)) if isinstance(t.get(var), (list, tuple)) else (None, None)
                cab[f'variable_{j}'] = var
                cab[f't_valor_{j}_{k}'], cab[f't_prob_{j}_{k}'] = valor, prob
    resultado = celdas_de_formato(registro, codigo, {'fuente': fuente, 'cabecera': cab, 'bloques': {'anios': filas}},
                                  fecha=fecha)
    if len(modelos) > MAX_MODELOS:
        resultado['huecos'].append({'bloque': 'anios', 'causa': f'{len(modelos)} modelos y la plantilla trae '
                                                                f'{MAX_MODELOS} columnas: van los {MAX_MODELOS} primeros'})
    if len(variables) > 4:
        resultado['huecos'].append({'bloque': 'estadisticos', 'causa': f'{len(variables)} variables y la plantilla trae 4'})
    return resultado


def _niveles(registro: RegistroNormativo, fecha: str | None) -> dict[str, list[float]]:
    """Las tensiones de cada nivel para efectos regulatorios (``pit.niveles_tension_kv``, num. 12.1.1)."""
    try:
        valor = registro.regla('pit.niveles_tension_kv', fecha).regla.valor
    except RegistroError as exc:
        raise PitError(f'falta la regla pit.niveles_tension_kv: sin ella no se suma la energía por nivel ({exc})') from exc
    return {nivel: [float(v) for v in kvs] for nivel, kvs in valor.items()}


def _nivel_de(kv: Any, niveles: Mapping[str, list[float]]) -> str | None:
    if not isinstance(kv, (int, float)):
        return None
    return next((n for n, kvs in niveles.items() if any(math.isclose(kv, v, rel_tol=1e-3) for v in kvs)), None)


def _clave(f: Mapping[str, Any]) -> tuple[Any, Any, Any, Any]:
    return f.get('sistema'), f.get('set'), f.get('barra'), f.get('tension_kv')


def _sumar(a: Sequence[Any], b: Sequence[Any] | None) -> list[float | None]:
    if b is None:
        return list(a)
    return [x + y if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None for x, y in zip(a, b)]


def resumen_demanda(registro: RegistroNormativo, cadena: Mapping[str, Any], libres: Mapping[str, Any] | None,
                    fecha: str | None = None) -> dict[str, Any]:
    """F-119 a F-122 desde la cadena de la 3c (``demanda_cadena.cadena_regulatoria``) y la proyección de los usuarios
    libres (``libres``: ``F-115`` → filas con ``energia_mwh``; ``F-116`` a ``F-118`` → filas con ``potencia_mw``; cada
    fila con sistema, set, barra y tension_kv). ``libres = {'sin_usuarios_libres': motivo}`` declara que el área no
    los tiene; ``libres = None`` deja los resúmenes sin sumar, con su causa."""
    horizonte = int(cadena['horizonte'])
    niveles = _niveles(registro, fecha)
    sin_libres = libres is not None and 'sin_usuarios_libres' in libres
    motivo = None
    if libres is None:
        motivo = ('sin la proyección de los usuarios libres y demandas incorporadas (F-113 a F-118): la nota del formato '
                  'pide la suma de regulados y libres, y no se supone')
    por_codigo = {'F-120': ('F-110', 'F-116'), 'F-121': ('F-111', 'F-117'), 'F-122': ('F-112', 'F-118')}
    salida: dict[str, Any] = {'horizonte': horizonte, 'motivo': motivo, 'filas': {}}
    for resumen, (regulado, libre) in por_codigo.items():
        # Varios usuarios en la misma barra se suman: la fila del resumen es de la barra, no del usuario.
        de_libres: dict[tuple[Any, Any, Any, Any], list[float | None]] = {}
        for f in ((libres or {}).get(libre) or ()):
            previa = de_libres.get(_clave(f))
            de_libres[_clave(f)] = list(f.get('potencia_mw') or ()) if previa is None else _sumar(previa, f.get('potencia_mw'))
        filas = []
        for f in cadena['filas'][regulado]:
            serie = [None] * (horizonte + 1) if motivo else _sumar(f['potencia_mw'], de_libres.pop(_clave(f), None))
            p0, pn = serie[0], serie[-1]
            tc = ((pn / p0) ** (1 / horizonte) - 1) * 100 if isinstance(p0, (int, float)) and isinstance(pn, (int, float)) \
                and p0 > 0 and pn > 0 and horizonte else None
            filas.append({**{k: f.get(k) for k in ('sistema', 'set', 'barra', 'tension_kv', 'devanado')},
                          'potencia_mw': serie, 'tc_pct': tc,
                          '_motivos': {'potencia_mw': motivo or 'falta el valor regulado o el libre de ese año',
                                       'tc_pct': motivo or 'sin potencia del año 0 o del último: la TC no se supone',
                                       '_calculo:potencia_mw': f'{regulado} + {libre}' + (' (el área no tiene usuarios libres)'
                                                                                          if sin_libres else '')}})
        for k, serie in de_libres.items():
            filas.append({'sistema': k[0], 'set': k[1], 'barra': k[2], 'tension_kv': k[3], 'potencia_mw': serie,
                          'tc_pct': None, '_motivos': {'tc_pct': 'barra solo de usuarios libres: TC sin calcular',
                                                       '_calculo:potencia_mw': libre}})
        salida['filas'][resumen] = filas
    energia = {n: [0.0] * (horizonte + 1) for n in ('MAT', 'AT', 'MT')}
    sin_nivel: list[str] = []
    fuentes = [('F-109', cadena['filas']['F-109'])] + ([('F-115', (libres or {}).get('F-115') or ())] if libres else [])
    for nombre, filas in fuentes:
        for f in filas:
            n = _nivel_de(f.get('tension_kv'), niveles)
            if n not in energia:
                sin_nivel.append(f'{nombre} {f.get("set")} {f.get("barra")}: tensión {f.get("tension_kv")} kV sin nivel')
                continue
            energia[n] = _sumar(energia[n], f.get('energia_mwh'))
    anios = []
    for i in range(horizonte + 1):
        fila: dict[str, Any] = {'anio': i, '_motivos': {}}
        for n in energia:
            v = None if motivo or sin_nivel else energia[n][i]
            fila[f'{n.lower()}_gwh'] = None if v is None else v / 1000
            if fila[f'{n.lower()}_gwh'] is None:
                fila['_motivos'][f'{n.lower()}_gwh'] = motivo or ('; '.join(sin_nivel) if sin_nivel else
                                                                  'falta la energía de alguna barra de ese año')
        vals = [fila[f'{n.lower()}_gwh'] for n in energia]
        fila['total_gwh'] = sum(vals) if all(isinstance(v, (int, float)) for v in vals) else None
        if fila['total_gwh'] is None:
            fila['_motivos']['total_gwh'] = 'falta algún nivel: el total no se supone'
        anios.append(fila)
    salida['f119'] = anios
    salida['sin_nivel'] = sin_nivel
    return salida


def celdas_resumen(registro: RegistroNormativo, resumen: Mapping[str, Any], area: str | None,
                   fuente: Mapping[str, str], fecha: str | None = None) -> dict[str, Any]:
    """F-119 a F-122 llenados por el motor común, con el hueco de las filas de totales de los de potencia."""
    salida = {'F-119': celdas_de_formato(registro, 'F-119', {'fuente': fuente, 'cabecera': {'area': area},
                                                              'bloques': {'anios': resumen['f119']}}, fecha=fecha)}
    for codigo, filas in resumen['filas'].items():
        r = celdas_de_formato(registro, codigo, {'fuente': fuente, 'cabecera': {'area': area},
                                                 'bloques': {'devanados': filas}}, fecha=fecha)
        r['huecos'].append({'bloque': 'totales', 'causa': HUECO_TOTALES})
        salida[codigo] = r
    return salida
