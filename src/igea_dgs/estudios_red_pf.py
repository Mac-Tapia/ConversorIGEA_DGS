"""Lo que los estudios de la spec 012 deciden sin DIgSILENT.

Los guiones ``tools/confiabilidad_pf.py`` y ``tools/capacidad_pf.py`` leen en DIgSILENT
los resultados de sus módulos (``ComRel3``, ``ComOpri``, ``ComHostcap``, ``ComPvcurves``,
``ComCapo``) y los devuelven en bruto. Aquí está lo que se hace con ellos, para probarlo
con datos sorteados: índices por alimentador y su comprobación con los de cada carga, ENS
total y diferencias entre casos, los elementos que más aportan, la capacidad por nodo con
su motivo, el margen de las curvas PV, el informe de los bancos y la comprobación de que
el estudio no dejó nada cambiado.

Los índices por alimentador los da ``ElmFeeder`` (``c:SAIFI``…, plan, «Lo que confirmó
DIgSILENT»); la suma por cargas (SAIFI = ΣTCIF/ΣN, SAIDI = ΣTCIT/ΣN, ENS = ΣLPENS,
manual §45.2) es la definición del manual y queda como comprobación cruzada.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from .estudios_pf import CON_PROYECTO, DIFERENCIA, ESTUDIOS_012, SIN_PROYECTO
#: Elementos que más aportan a la ENS que se informan por alimentador (RF-32).
TOP_APORTES = 5
#: ``c:ENS`` de DIgSILENT va en MWh/a; el regulador pide kWh/a (RF-67).
KWH_POR_MWH = 1000.0
#: Diferencia relativa admitida entre los índices del alimentador y la suma por cargas.
TOLERANCIA_SUMA = 1e-3
#: Código de ``CalcMaxHostedPower`` → motivo que limita (plan, «Lo que confirmó DIgSILENT»).
MOTIVOS_ALOJAMIENTO = {1: 'sobrecarga', 2: 'tensión', 3: 'sobrecarga y tensión'}
SIN_CARGA = 'sin carga conectada'
NO_CALCULADO = 'no calculado'

#: Variación propia de la spec 012 (RF-21), «Datos de confiabilidad»: la única que un estudio
#: puede dejar. Con «_», como ``cargas_pf.nombre_pf`` escribe todo nombre en DIgSILENT.
VARIACION_DATOS = 'Datos_de_confiabilidad'

COLUMNAS_RED = (
    'caso', 'alimentador', 'estudio', 'saifi', 'saidi', 'caidi', 'ens_kwh', 'maifi',
    'cargas_sin_clientes', 'reconectadores', 'mejora_kwh', 'capacidad_gd_min_kw',
    'capacidad_gd_min_nodo', 'capacidad_gd_max_kw', 'capacidad_gd_max_nodo',
    'capacidad_carga_min_kw', 'capacidad_carga_min_nodo', 'capacidad_carga_max_kw',
    'capacidad_carga_max_nodo', 'demanda_inicial_kw', 'demanda_critica_kw', 'margen_kw',
    'margen_pct', 'barra_critica', 'contingencia_critica', 'bancos', 'kvar_propuestos',
    'ahorro_anual', 'coste_anual', 'fiable', 'motivo')
COLUMNAS_CAPACIDAD = ('caso', 'alimentador', 'nodo', 'gd_kw', 'gd_limita', 'gd_motivo',
                      'carga_kw', 'carga_limita', 'carga_motivo', 'conjunto_kw', 'conjunto_motivo')
#: Índices que se restan entre «Con proyecto» y «Sin proyecto» (RF-31).
INDICES = ('saifi', 'saidi', 'caidi', 'ens_kwh', 'maifi')


def _f(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


# --------------------------------------------------------------------------- confiabilidad
def indices_de_cargas(cargas: Iterable[Mapping[str, Any]]) -> dict[str, float | None]:
    """SAIFI, SAIDI, CAIDI y ENS (kWh/a) por la suma del manual sobre las cargas."""
    n = tcif = tcit = ens = 0.0
    for c in cargas:
        n += _f(c.get('nrcust')) or 0.0
        tcif += _f(c.get('tcif')) or 0.0
        tcit += _f(c.get('tcit')) or 0.0
        ens += _f(c.get('lpens')) or 0.0
    saifi = tcif / n if n else None
    saidi = tcit / n if n else None
    return {'saifi': saifi, 'saidi': saidi,
            'caidi': saidi / saifi if saifi else None, 'ens_kwh': ens * KWH_POR_MWH}


def confiabilidad(f: str, leido: Mapping[str, Any]) -> dict[str, Any]:
    """Fila de un alimentador con lo que leyó el guion (RF-25, RF-30, RF-32, RF-33, RF-70, RF-71).

    Sin tensión antes de la falla, o con todas las tasas a cero, no hay índices: se dice
    por qué en vez de dar ceros, que pasarían por una red perfecta.
    """
    cargas = list(leido.get('cargas') or ())
    sin_clientes = sum(1 for c in cargas if not _f(c.get('nrcust')))
    fila: dict[str, Any] = {'alimentador': f, 'cargas_sin_clientes': sin_clientes, 'avisos': [],
                            'aportes': [], 'fiable': True, 'motivo': ''}
    if sin_clientes:
        fila['avisos'].append(f'{f}: {sin_clientes} cargas sin número de clientes; no pesan en '
                              'SAIFI ni en SAIDI.')
    if cargas and all(_f(c.get('nrcust')) == 1 for c in cargas):
        fila['avisos'].append(f'{f}: todas sus cargas tienen un solo cliente; el número de clientes '
                              'probablemente no llegó al proyecto y SAIFI y SAIDI quedan ponderados '
                              'por carga, no por cliente.')
    if leido.get('sin_tension'):
        return {**fila, **dict.fromkeys(INDICES), 'fiable': False,
                'motivo': 'sin tensión antes de la falla: su fuente está fuera de servicio o el '
                          'flujo no lo alimenta'}
    if leido.get('tasas_cero'):
        return {**fila, **dict.fromkeys(INDICES), 'fiable': False,
                'motivo': 'todas sus tasas de falla son cero tras aplicar el libro'}
    ind = leido.get('indices') or {}
    ens = _f(ind.get('ENS'))
    fila.update(saifi=_f(ind.get('SAIFI')), saidi=_f(ind.get('SAIDI')), caidi=_f(ind.get('CAIDI')),
                ens_kwh=ens * KWH_POR_MWH if ens is not None else None, maifi=_f(ind.get('MAIFI')))
    if fila['maifi'] is None:
        fila['avisos'].append(f'{f}: DIgSILENT no dio MAIFI; queda como no disponible.')
    suma = indices_de_cargas(cargas)
    for k in ('saifi', 'saidi', 'ens_kwh'):
        a, b = fila[k], suma[k]
        if a is not None and b is not None and abs(a - b) > TOLERANCIA_SUMA * max(1.0, abs(a)):
            fila['avisos'].append(f'{f}: {k} del alimentador ({a:.4f}) no coincide con la suma de '
                                  f'sus cargas ({b:.4f}).')
    fila['aportes'] = aportes(leido.get('aportes') or ())
    return fila


def aportes(elementos: Iterable[Mapping[str, Any]], n: int = TOP_APORTES) -> list[dict[str, Any]]:
    """Los ``n`` elementos que más aportan a la ENS, de mayor a menor (RF-32)."""
    filas = [{'elemento': e['elemento'], 'clase': e.get('clase'),
              'ens_kwh': (_f(e.get('ens_mwh')) or 0.0) * KWH_POR_MWH, 'pct': _f(e.get('pct'))}
             for e in elementos if (_f(e.get('ens_mwh')) or 0.0) > 0]
    return sorted(filas, key=lambda x: (-x['ens_kwh'], x['elemento']))[:n]


def comparar(sin: Mapping[str, Mapping[str, Any]], con: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Diferencias con − sin por alimentador y ENS total de los marcados (RF-31, RF-67, RF-68).

    El total suma solo los alimentadores con índices en el caso: uno sin tensión no cuenta
    como cero.
    """
    por_alim = {}
    for f in sorted(set(sin) | set(con)):
        a, b = con.get(f) or {}, sin.get(f) or {}
        d = {k: (a[k] - b[k]) if _f(a.get(k)) is not None and _f(b.get(k)) is not None else None
             for k in INDICES}
        base = _f(b.get('ens_kwh'))
        d['ens_pct'] = 100.0 * d['ens_kwh'] / base if d['ens_kwh'] is not None and base else None
        por_alim[f] = d

    def total(filas):
        vals = [x['ens_kwh'] for x in filas.values() if _f(x.get('ens_kwh')) is not None]
        return sum(vals) if vals else None

    t_sin, t_con = total(sin), total(con)
    dif = t_con - t_sin if t_sin is not None and t_con is not None else None
    return {'por_alimentador': por_alim, 'ens_total_kwh': {SIN_PROYECTO: t_sin, CON_PROYECTO: t_con},
            'ens_total_diferencia_kwh': dif,
            'ens_total_diferencia_pct': 100.0 * dif / t_sin if dif is not None and t_sin else None}


# --------------------------------------------------------------------------- reconectadores
_REDUCE = re.compile(r'reduced by\s+([\d.,]+)\s*MWh/a.*Before:\s*([\d.,]+).*After:\s*([\d.,]+)', re.I)


def numero_pf(texto: str) -> float:
    """Un número de la ventana de salida, con coma decimal (y punto de miles) o con punto."""
    t = texto.strip()
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    return float(t)


def mejora_de_salida(lineas: Iterable[str]) -> dict[str, float] | None:
    """«The ENS is reduced by X MWh/a (Before: …, After: …)» de ``ComOpri``, en kWh/a."""
    for linea in lineas:
        m = _REDUCE.search(linea)
        if m:
            x, antes, despues = (numero_pf(g) * KWH_POR_MWH for g in m.groups())
            return {'reduccion_kwh': x, 'antes_kwh': antes, 'despues_kwh': despues}
    return None


def reconectadores(propuestos: Iterable[Mapping[str, Any]], candidatos: Mapping[str, int],
                   feeders: Iterable[str]) -> dict[str, Any]:
    """Propuesta por alimentador (RF-39) y los que no tenían candidato, dicho."""
    por: dict[str, list] = {f: [] for f in feeders}
    for p in propuestos:
        por.setdefault(p['alimentador'], []).append(dict(p))
    avisos = [f'{f}: sin interruptor ni reconectador candidato (los fusibles, seccionadores, los '
              'interruptores internos de las SED y los que protegen solo cables no cuentan).'
              for f in por if not candidatos.get(f)]
    return {'por_alimentador': {f: sorted(v, key=lambda x: x['elemento']) for f, v in sorted(por.items())},
            'avisos': avisos}


# --------------------------------------------------------------------------- capacidad
def motivo_alojamiento(codigo: Any, elemento: str | None, objetivo: str) -> str:
    """El motivo que limita un nodo; sin elemento, no hay límite calculado (RF-47, RF-72)."""
    if elemento is None:
        return SIN_CARGA if objetivo == 'carga' else NO_CALCULADO
    return MOTIVOS_ALOJAMIENTO.get(int(codigo) if _f(codigo) is not None else -1, NO_CALCULADO)


def nodo_de_capacidad(f: str, nodo: str, gd: Iterable[Any] | None, carga: Iterable[Any] | None) -> dict[str, Any]:
    """Fila de un nodo con ``[código, P MW, Q, elemento]`` de cada objetivo (RF-47, RF-72)."""
    fila: dict[str, Any] = {'alimentador': f, 'nodo': nodo}
    for clave, res in (('gd', gd), ('carga', carga)):
        codigo, p, _q, elem = (list(res) + [None] * 4)[:4] if res is not None else (None,) * 4
        calculado = elem is not None
        fila[f'{clave}_kw'] = (_f(p) or 0.0) * 1000.0 if calculado else None
        fila[f'{clave}_limita'] = elem if calculado else None
        fila[f'{clave}_motivo'] = motivo_alojamiento(codigo, elem, clave) if res is not None else NO_CALCULADO
    return fila


def extremos(nodos: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Por alimentador, el nodo de menor y el de mayor capacidad en cada objetivo (RF-48).

    Con empate gana el primero por nombre, para que el fichero no dependa del orden de
    DIgSILENT.
    """
    por: dict[str, list] = {}
    for n in nodos:
        por.setdefault(n['alimentador'], []).append(n)
    out = {}
    for f, lista in sorted(por.items()):
        d: dict[str, Any] = {}
        for clave in ('gd', 'carga'):
            con = sorted((x for x in lista if x.get(f'{clave}_kw') is not None), key=lambda x: x['nodo'])
            mn = min(con, key=lambda x: x[f'{clave}_kw'], default=None)
            mx = max(con, key=lambda x: x[f'{clave}_kw'], default=None)
            d[f'capacidad_{clave}_min_kw'] = mn and mn[f'{clave}_kw']
            d[f'capacidad_{clave}_min_nodo'] = mn and mn['nodo']
            d[f'capacidad_{clave}_max_kw'] = mx and mx[f'{clave}_kw']
            d[f'capacidad_{clave}_max_nodo'] = mx and mx['nodo']
        out[f] = d
    return out


_INICIAL = re.compile(r'Initial scalable demand.*?:\s*([\d.,]+)\s*MW', re.I)
_CRITICA = re.compile(r'Total critical demand.*?:\s*([\d.,]+)\s*MW', re.I)
_TABLA = re.compile(r'^\s*(?:info\s*-\s*)?\s*(.+?)\s{2,}(\S+)\s+([\d.,]+)\s*$', re.I)


def resumen_pv(lineas: Iterable[str]) -> dict[str, Any]:
    """Demanda inicial y crítica, barra y contingencia crítica de la ventana de salida (RF-52, RF-53).

    El ``ElmRes`` de ``ComPvcurves`` queda vacío y ``FindCriticalBus`` no da nada sobre él
    (prueba en DIgSILENT del 2026-10-12): el resumen es lo que escribe la ventana de salida,
    con la coma decimal de la configuración regional. Con contingencias, la crítica es la
    fila de menor demanda crítica de la tabla.
    """
    out: dict[str, Any] = {'inicial_kw': None, 'critica_kw': None, 'barra_critica': None,
                           'contingencia_critica': None}
    filas, tabla = [], False
    for linea in lineas:
        if (m := _INICIAL.search(linea)) and out['inicial_kw'] is None:
            out['inicial_kw'] = numero_pf(m.group(1)) * 1000.0
        elif (m := _CRITICA.search(linea)) and out['critica_kw'] is None:
            out['critica_kw'] = numero_pf(m.group(1)) * 1000.0
        elif 'Critical bus' in linea:
            tabla = True
        elif tabla and (m := _TABLA.match(linea)):
            try:
                filas.append((numero_pf(m.group(3)) * 1000.0, m.group(1).strip(), m.group(2)))
            except ValueError:
                continue
    if filas:
        kw, cont, barra = min(filas)
        out['barra_critica'] = barra
        out['contingencia_critica'] = None if cont.lower() == 'base case' else cont
        out['critica_kw'] = kw if out['critica_kw'] is None or len(filas) > 1 else out['critica_kw']
    return out


def margen_pv(inicial_kw: float | None, critica_kw: float | None) -> dict[str, float | None]:
    """Margen hasta el colapso, en kW y en % de la demanda inicial (RF-52)."""
    if inicial_kw is None or critica_kw is None:
        return {'margen_kw': None, 'margen_pct': None}
    m = critica_kw - inicial_kw
    return {'margen_kw': m, 'margen_pct': 100.0 * m / inicial_kw if inicial_kw else None}


def informe_bancos(f: str, instalados: Iterable[Mapping[str, Any]], bancos: Sequence[Mapping[str, Any]],
                   coste_antes: float | None, coste_despues: float | None, moneda: str,
                   tasa: float | None) -> dict[str, Any]:
    """Cada banco propuesto con su nodo, kvar y pasos, y el ahorro frente a su coste (RF-56, RF-57, RF-66).

    El banco del libro se reconoce por su potencia por paso (``qcapn``): así el informe da
    su inversión, vida útil, tasa y coste anual.
    """
    propuestos = []
    for s in instalados:
        q = _f(s.get('kvar_paso')) or 0.0
        de_libro = next((b for b in bancos if abs(float(b['potencia_kvar']) - q) < 1e-6), None) or {}
        pasos = int(s.get('pasos') or 0)
        propuestos.append({
            'nodo': s['nodo'], 'kvar_paso': q, 'pasos': pasos, 'kvar': q * pasos,
            'inversion': de_libro.get('inversion'), 'vida_anios': de_libro.get('vida_anios'),
            'tasa_descuento': tasa, 'coste_anual': de_libro.get('coste_anual')})
    propuestos.sort(key=lambda x: x['nodo'])
    ahorro = (coste_antes - coste_despues) if coste_antes is not None and coste_despues is not None else None
    return {'alimentador': f, 'bancos': propuestos, 'kvar_propuestos': sum(p['kvar'] for p in propuestos),
            'ahorro_anual': ahorro if propuestos else None,
            'coste_anual': sum(p['coste_anual'] or 0.0 for p in propuestos) if propuestos else None,
            'moneda': moneda,
            'aviso': (None if propuestos else
                      f'{f}: ningún banco se paga con las pérdidas que ahorra; no se propone ninguno.')}


# --------------------------------------------------------------------------- estado
def cambios_de_estado(antes: Mapping[str, Any], despues: Mapping[str, Any]) -> list[str]:
    """Lo que un estudio dejó cambiado (RF-60): demanda de cargas, variaciones nuevas salvo
    «Datos de confiabilidad», hora de estudio del caso y etapa que graba."""
    out = []
    for nombre, pq in sorted((antes.get('demandas') or {}).items()):
        ahora = (despues.get('demandas') or {}).get(nombre)
        if ahora is not None and any(abs(a - b) > 1e-6 for a, b in zip(pq, ahora)):
            out.append(f'la demanda de {nombre}')
    nuevas = sorted(set(despues.get('variaciones') or ()) - set(antes.get('variaciones') or ())
                    - {VARIACION_DATOS})
    out += [f'la variación {v}' for v in nuevas]
    if antes.get('hora') != despues.get('hora'):
        out.append('la hora de estudio del caso')
    if antes.get('etapa') != despues.get('etapa'):
        out.append('la etapa de grabación')
    return out


# --------------------------------------------------------------------------- ficheros
def filas_red(resultados: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por caso, alimentador y estudio, y la de la diferencia de la confiabilidad (RF-59)."""
    resultados = list(resultados)
    filas = [{c: r.get(c) for c in COLUMNAS_RED} for r in resultados]
    sin = {(r['alimentador'], r['estudio']): r for r in resultados if r['caso'] == SIN_PROYECTO}
    for r in resultados:
        b = sin.get((r['alimentador'], r['estudio']))
        if r['caso'] != CON_PROYECTO or r['estudio'] != 'fiabilidad' or b is None:
            continue
        d = comparar({r['alimentador']: b}, {r['alimentador']: r})['por_alimentador'][r['alimentador']]
        filas.append({c: None for c in COLUMNAS_RED} | {k: d[k] for k in INDICES} | {
            'caso': DIFERENCIA, 'alimentador': r['alimentador'], 'estudio': r['estudio'],
            'fiable': bool(r.get('fiable') and b.get('fiable'))})
    orden = {e: i for i, e in enumerate(ESTUDIOS_012)}
    return sorted(filas, key=lambda f: (f['caso'], f['alimentador'], orden.get(f['estudio'], 99)))


def filas_capacidad(caso: str, nodos: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Capacidad por nodo para el fichero descargable, una fila por caso y nodo (RF-49)."""
    return sorted(({'caso': caso, **{c: n.get(c) for c in COLUMNAS_CAPACIDAD if c != 'caso'}} for n in nodos),
                  key=lambda x: (x['alimentador'], x['nodo']))
