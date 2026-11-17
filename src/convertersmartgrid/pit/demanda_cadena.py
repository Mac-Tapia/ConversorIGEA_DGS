"""Demanda regulatoria del PIT, paso 3c (107 T29): F-108 a F-112 desde las ventas proyectadas y los factores de la 3b.

La cadena de la norma vigente (RCD 217-2013, regla ``pit.demanda.potencia_desde_energia``, art. 8.1):
  - F-108: las ventas proyectadas de cada sistema eléctrico por nivel (AT, MT y BT), sin pérdidas (nota 1 del formato);
  - F-109: la energía de cada barra con las pérdidas estándar de la fijación del VAD vigente DE LA EMPRESA, en cascada
    por nivel con sus factores de expansión de energía (FE = 1/(1−p), nunca 1+p): la venta en MT sube por la red de MT
    (PEMT) y la de BT por la red de BT, la SED y la red de MT (PEBT · PESED · PEMT); la de AT va sin pérdidas (%p = 0
    para MAT y AT, art. 8.1). La energía del sistema se reparte entre sus devanados con su FPMWHS (F-103), que es la
    participación de cada devanado en la energía del sistema del año representativo;
  - F-110, F-111 y F-112: la fórmula del art. 8.1, Potencia = Energía / (t · FC) · factor, con el FC del devanado (F-101)
    y t las horas del año representativo; el factor es 1 en la no coincidente (F-110), el FCP en la coincidente con el
    sistema (F-111) y el FS en la coincidente con el SEIN (F-112).

Sin fijación vigente de la empresa en el registro, sus pérdidas quedan «no transcritas» y F-109 a F-112 salen vacíos con
ese motivo: nunca se toman las de otra empresa. Una SET cuya medición centralizada no separa sus devanados lleva la
marca «aproximado» en sus filas, con el motivo que declara el perfil. La potencia de diagnóstico (la suma de los
alimentadores) no se mezcla con la regulatoria: un aviso las compara por SET y año, con la diferencia en %, y no
corrige ninguna (aclaración de 107:RF-9).
"""
from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError
from .demanda_regulatoria import barra_y_tension
from .plantillas import celdas_de_formato, horizonte_de_la_norma
from .red_area import RedArea

__all__ = ['CLAVE_FE', 'CLAVE_FORMULA', 'cadena_regulatoria', 'celdas_cadena', 'factores_de_perdidas']

CLAVE_FE = 'vad.perdidas.factores_expansion'
CLAVE_FORMULA = 'pit.demanda.potencia_desde_energia'
NIVELES = ('at', 'mt', 'bt')
#: Factores de expansión de ENERGÍA de la tabla de la fijación que usa la cascada (filas de la tabla de la norma).
FILAS_FE = ('PEMT', 'PESED', 'PEBT')
FORMATOS_POTENCIA = {'F-110': None, 'F-111': 'fcp', 'F-112': 'fs'}
APROXIMADO = 'aproximado'


def factores_de_perdidas(registro: RegistroNormativo, empresa: str, fecha: str | None
                         ) -> tuple[dict[str, Any] | None, str | None]:
    """Los FE de energía de la fijación vigente de ``empresa``, con su traza; o None y el motivo «no transcrita»."""
    try:
        rv = registro.regla_de_empresa(CLAVE_FE, empresa, fecha)
    except RegistroError as exc:
        return None, (f'pérdidas estándar de la empresa: no transcritas en el registro normativo ({exc}); '
                      'no se toman las de otra empresa')
    fe = ((rv.regla.valor.get('empresas') or {}).get(empresa) or {}).get('fe') or {}
    faltan = [k for k in FILAS_FE if not isinstance(fe.get(k), (int, float))]
    if faltan:
        return None, f'la fijación {rv.norma.acto} no trae el FE de {", ".join(faltan)} de la empresa'
    malos = [k for k in FILAS_FE if fe[k] < 1]
    if malos:
        raise PitError(f'{rv.norma.acto}: FE menor que 1 en {", ".join(malos)}; la tabla está mal transcrita')
    return {**{k: float(fe[k]) for k in FILAS_FE},
            'traza': {'regla': CLAVE_FE, 'norma': rv.norma.acto, 'estado': rv.estado, 'huella': rv.huella(),
                      'cascada': 'AT sin pérdidas; MT · PEMT; BT · PEBT · PESED · PEMT (FE = 1/(1−p))'}}, None


def _serie(valores: Sequence[Any] | None, horizonte: int) -> list[float | None]:
    v = list(valores or ())
    return [float(v[i]) if i < len(v) and isinstance(v[i], (int, float)) else None for i in range(horizonte + 1)]


def _energia_sistema(ventas: Mapping[str, list[float | None]], fe: Mapping[str, float], i: int) -> float | None:
    at, mt, bt = (ventas[n][i] for n in NIVELES)
    if None in (at, mt, bt):
        return None
    return at + mt * fe['PEMT'] + bt * fe['PEBT'] * fe['PESED'] * fe['PEMT']


def _por(filas: Sequence[Mapping[str, Any]], clave: str) -> dict[str, Mapping[str, Any]]:
    return {str(f.get(clave)): f for f in filas if f.get(clave) is not None}


def cadena_regulatoria(registro: RegistroNormativo, empresa: str, salida_3b: Mapping[str, Any], red: RedArea,
                       ventas: Mapping[str, Mapping[str, Sequence[float]]], *, fecha: str | None = None,
                       centralizadas: Mapping[str, str] | None = None,
                       diagnostico_mw: Mapping[str, Sequence[float | None]] | None = None) -> dict[str, Any]:
    """F-108 a F-112 de un área: ``ventas`` (sistema → nivel ``at``/``mt``/``bt`` → MWh por año 0..horizonte),
    ``salida_3b`` (``demanda_regulatoria``: F-101, F-102 y F-103), la red del área (barra y tensión de cada devanado),
    ``centralizadas`` (SET → motivo de la marca «aproximado») y ``diagnostico_mw`` (SET → MW de diagnóstico por año)."""
    horizonte = horizonte_de_la_norma(registro, fecha)
    try:
        formula = registro.regla(CLAVE_FORMULA, fecha)
    except RegistroError as exc:
        raise PitError(f'falta la regla {CLAVE_FORMULA} (art. 8.1): sin ella no hay cadena ({exc})') from exc
    cita = {'regla': CLAVE_FORMULA, 'norma': formula.norma.acto, 'huella': formula.huella()}
    fe, motivo_fe = factores_de_perdidas(registro, empresa, fecha)
    anio = int(salida_3b['anio'])
    t = 8784 if calendar.isleap(anio) else 8760
    series = {s: {n: _serie((v or {}).get(n), horizonte) for n in NIVELES} for s, v in ventas.items()}
    f108 = {s: [{'at_mwh': v['at'][i], 'mt_mwh': v['mt'][i], 'bt_mwh': v['bt'][i],
                 'total_mwh': None if None in (v['at'][i], v['mt'][i], v['bt'][i])
                 else v['at'][i] + v['mt'][i] + v['bt'][i],
                 '_motivos': {f'{n}_mwh': f'las ventas proyectadas no traen el año {i} en {n.upper()}'
                              for n in NIVELES if v[n][i] is None}} for i in range(horizonte + 1)]
            for s, v in series.items()}
    f101 = {str(f['nombre']): f for f in salida_3b['f101']['filas'] if f.get('nivel') == 'devanado'}
    f103 = _por(salida_3b['f103']['filas'], 'devanado')
    centralizadas = dict(centralizadas or {})
    filas: dict[str, list[dict[str, Any]]] = {c: [] for c in ('F-109', *FORMATOS_POTENCIA)}
    avisos: list[str] = []
    por_set: dict[str, list[float | None]] = {}
    for f in salida_3b['f102']['filas']:
        dev, sis, s = f['devanado'], f['sistema'], f['set']
        barra, kv, motivo_red = barra_y_tension(red, dev)
        base = {'sistema': sis, 'set': s, 'barra': barra, 'tension_kv': kv, 'devanado': dev,
                '_motivos': {} if not motivo_red else {'barra': motivo_red, 'tension_kv': motivo_red}}
        if s in centralizadas:
            base[APROXIMADO] = f'{APROXIMADO}: {centralizadas[s]}'
        fpmwhs = (f103.get(dev) or {}).get('fpmwhs')
        if motivo_fe:
            motivo = motivo_fe
        elif sis not in series:
            motivo = f'sin ventas proyectadas del sistema {sis}'
        elif fpmwhs is None:
            motivo = (f103.get(dev) or {}).get('motivo') or 'sin FPMWHS del devanado en el F-103'
        else:
            motivo = None
        del_sistema = [None if motivo else _energia_sistema(series[sis], fe, i) for i in range(horizonte + 1)]
        energia = [None if e is None else e * fpmwhs for e in del_sistema]
        filas['F-109'].append({**base, 'energia_mwh': energia, '_motivos': {
            **base['_motivos'], 'energia_mwh': motivo or 'las ventas proyectadas no traen ese año',
            '_calculo:energia_mwh': 'energía del sistema con los FE de la fijación en cascada × FPMWHS (F-103)'}})
        fac = f101.get(dev) or {}
        for codigo, factor in FORMATOS_POTENCIA.items():
            mot = motivo or (None if fac.get('fc') else (fac.get('motivo') or 'sin FC del devanado en el F-101'))
            if not mot and factor and fac.get(factor) is None:
                mot = fac.get(f'motivo_{factor}') or f'sin {factor.upper()} del devanado en el F-101'
            k = 1.0 if factor is None or mot else float(fac[factor])
            serie = [None if mot or e is None else e / (t * float(fac['fc'])) * k for e in energia]
            filas[codigo].append({**base, 'potencia_mw': serie, '_motivos': {
                **base['_motivos'], 'potencia_mw': mot or 'sin energía de ese año en el F-109',
                '_calculo:potencia_mw': f'art. 8.1: energía F-109 / ({t} h · FC)'
                                        + (f' · {factor.upper()}' if factor else '')}})
            if codigo == 'F-112':
                acum = por_set.setdefault(s, [0.0] * (horizonte + 1))
                por_set[s] = [None if a is None or p is None else a + p for a, p in zip(acum, serie)]
    for s, diag in (diagnostico_mw or {}).items():
        reg = por_set.get(s)
        for i, d in enumerate(_serie(diag, horizonte)):
            r = None if reg is None else reg[i]
            if r is None or d is None or d == 0:
                continue
            avisos.append(f'SET {s}, año {i}: potencia regulatoria (F-112) {r:.3f} MW frente a la de diagnóstico '
                          f'{d:.3f} MW ({100 * (r - d) / d:+.1f} %); las dos se informan y ninguna se corrige')
    return {'horizonte': horizonte, 'horas': t, 'f108': f108, 'filas': filas, 'avisos': avisos,
            'perdidas': fe['traza'] if fe else {'motivo': motivo_fe}, 'formula': cita}


def _marcar(resultado: dict[str, Any], filas: Sequence[Mapping[str, Any]], bloque: str) -> dict[str, Any]:
    for c in resultado['celdas']:
        if c.get('bloque') == bloque and isinstance(c.get('fila'), int):
            marca = filas[c['fila'] - 1].get(APROXIMADO)
            if marca:
                c['traza'] = {**c['traza'], 'marca': APROXIMADO, 'motivo_marca': marca}
    return resultado


def celdas_cadena(registro: RegistroNormativo, cadena: Mapping[str, Any], fuente: Mapping[str, str],
                  fecha: str | None = None) -> dict[str, Any]:
    """F-108 (uno por sistema eléctrico) y F-109 a F-112 llenados por el motor común de plantillas."""
    salida: dict[str, Any] = {'F-108': {s: celdas_de_formato(registro, 'F-108', {
        'fuente': fuente, 'cabecera': {'sistema': s}, 'bloques': {'anios': filas}}, fecha=fecha)
        for s, filas in cadena['f108'].items()}}
    for codigo, filas in cadena['filas'].items():
        salida[codigo] = _marcar(celdas_de_formato(registro, codigo, {'fuente': fuente, 'bloques': {
            'devanados': filas}}, fecha=fecha), filas, 'devanados')
    return salida
