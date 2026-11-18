"""F-113 a F-118: usuarios libres y demandas incorporadas del área (107:RF-9; tarjeta PIT-F113-118).

Fuentes, sin suponer ninguna:
- **demandas incorporadas**: el libro de cargas nuevas de planificación (``cargas_pf.leer_nuevas``: la carga, su
  alimentador —la «TRONCAL»—, su kW, su año de ingreso y sus etapas si entra fraccionada);
- **usuarios libres**: los que declara el perfil en ``pit.usuarios_libres`` (nombre, alimentador, kW y, si lo tiene,
  su año de ingreso); el perfil se edita en la web como cualquier otra clave.

Cada usuario se ubica por su alimentador en la topología de la 3b (sistema, SET, devanado) y en la red del área (barra
y tensión). Su máxima demanda de cada año es la de su libro (o la del perfil) desde su año de ingreso. Lo que su
medición no da se deduce con los factores de su devanado, y se anota así: la energía con el FC (F-101), la coincidente
con la SET con el FCP, la coincidente con el SEIN con el FS y la participación con el FPHMS (F-103). La demanda de
energía (F-115) lleva las pérdidas de la fijación vigente de la empresa por su nivel (AT sin pérdidas; MT · PEMT; BT ·
PEBT · PESED · PEMT); sin fijación, «no transcrita». Sin usuarios en las fuentes, los formatos salen vacíos con su aviso.
"""
from __future__ import annotations

import calendar
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit import PitError
from .demanda_cadena import factores_de_perdidas
from .demanda_regulatoria import Topologia, barra_y_tension
from .plantillas import celdas_de_formato, horizonte_de_la_norma
from ...aplicacion.pit.red_area import RedArea

__all__ = ['DEDUCIDO', 'celdas_usuarios', 'proyeccion_usuarios', 'ubicacion_de_alimentadores', 'usuarios_del_perfil']

DEDUCIDO = 'deducido con el factor de su devanado (F-101/F-103): el usuario no tiene medición propia en el estudio'
FORMATOS_SERIE = ('F-114', 'F-115', 'F-116', 'F-117', 'F-118')


def ubicacion_de_alimentadores(topologia: Topologia, red: RedArea) -> dict[str, dict[str, Any]]:
    """Alimentador → sistema, SET, devanado, barra y tensión, desde la topología de la 3b y la red del área."""
    salida = {}
    for devanado, alimentadores in topologia.devanados.items():
        s = topologia.set_de(devanado)
        barra, kv, motivo = barra_y_tension(red, devanado)
        for a in alimentadores:
            salida[a] = {'sistema': topologia.sistema_de(s), 'set': s, 'devanado': devanado, 'barra': barra,
                         'tension_kv': kv, 'motivo': motivo}
    return salida


def usuarios_del_perfil(perfil: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Los usuarios libres de ``pit.usuarios_libres``, validados: nombre, alimentador y kW mayores que cero."""
    lista = ((perfil.get('pit') or {}).get('usuarios_libres') or []) if isinstance(perfil, Mapping) else []
    if not isinstance(lista, list):
        raise PitError('pit.usuarios_libres tiene que ser una lista de {nombre, alimentador, kw, anio_ingreso}')
    salida = []
    for i, u in enumerate(lista):
        donde = f'pit.usuarios_libres[{i}]'
        if not isinstance(u, Mapping) or not str(u.get('nombre') or '').strip() or not str(u.get('alimentador') or '').strip():
            raise PitError(f'{donde}: necesita su nombre y su alimentador')
        kw = u.get('kw')
        if isinstance(kw, bool) or not isinstance(kw, (int, float)) or kw <= 0:
            raise PitError(f'{donde}.kw: tiene que ser la máxima demanda en kW, mayor que cero')
        salida.append({'tipo': 'libre', 'nombre': str(u['nombre']).strip(), 'alimentador': str(u['alimentador']).strip(),
                       'kw': float(kw), 'anio_ingreso': u.get('anio_ingreso'), 'etapas': (), 'nivel': u.get('nivel')})
    return salida


def _de_cargas_nuevas(cargas: Iterable[Any]) -> list[dict[str, Any]]:
    return [{'tipo': 'incorporada', 'nombre': (c.descripcion or c.sed), 'alimentador': c.alimentador, 'kw': c.kw,
             'anio_ingreso': c.anio_ingreso, 'etapas': tuple(c.etapas),
             'nivel': 'BT' if getattr(c, 'tension_bt_kv', None) else None} for c in cargas]


def _anio(valor: Any, anio_0: int) -> int:
    """Un año de ingreso calendario (≥ 1900) o del PIDE (pequeño, contado desde el año 0); sin él, el año 0."""
    if not isinstance(valor, int) or isinstance(valor, bool):
        return anio_0
    return valor if valor >= 1900 else anio_0 + valor


def _serie_kw(u: Mapping[str, Any], anio_0: int, horizonte: int) -> list[float]:
    """kW de cada año 0..horizonte: las etapas acumuladas, o el total desde su año de ingreso."""
    etapas = [(_anio(a, anio_0), float(kw)) for a, kw in u.get('etapas') or ()] or [(_anio(u.get('anio_ingreso'), anio_0),
                                                                                      float(u['kw']))]
    return [sum(kw for a, kw in etapas if a <= anio_0 + i) for i in range(horizonte + 1)]


def _nivel(kv: Any, niveles: Mapping[str, Sequence[float]]) -> str | None:
    if not isinstance(kv, (int, float)):
        return None
    return next((n for n, kvs in niveles.items() if any(math.isclose(kv, float(v), rel_tol=1e-3) for v in kvs)), None)


def proyeccion_usuarios(registro: RegistroNormativo, empresa: str, salida_3b: Mapping[str, Any],
                        ubicacion: Mapping[str, Mapping[str, Any]], *, anio_0: int,
                        cargas_nuevas: Iterable[Any] = (), libres: Iterable[Mapping[str, Any]] = (),
                        fecha: str | None = None) -> dict[str, Any]:
    """F-113 a F-118 de los usuarios del área, y su forma para los resúmenes (``demanda_resumen.resumen_demanda``)."""
    horizonte = horizonte_de_la_norma(registro, fecha)
    t = 8784 if calendar.isleap(int(salida_3b['anio'])) else 8760
    try:
        niveles = {n: list(v) for n, v in registro.regla('pit.niveles_tension_kv', fecha).regla.valor.items()}
    except RegistroError as exc:
        raise PitError(f'falta la regla pit.niveles_tension_kv ({exc})') from exc
    fe, motivo_fe = factores_de_perdidas(registro, empresa, fecha)
    f101 = {str(f['nombre']): f for f in salida_3b['f101']['filas'] if f.get('nivel') == 'devanado'}
    f103 = {str(f['devanado']): f for f in salida_3b['f103']['filas'] if f.get('devanado')}
    usuarios = [*_de_cargas_nuevas(cargas_nuevas), *libres]
    filas: dict[str, list[dict[str, Any]]] = {c: [] for c in ('F-113', *FORMATOS_SERIE)}
    avisos = [] if usuarios else [('ni el libro de cargas nuevas ni el perfil (pit.usuarios_libres) traen usuarios '
                                   'libres o demandas incorporadas: F-113 a F-118 salen vacíos')]
    for u in usuarios:
        ub = ubicacion.get(u['alimentador'])
        base = {'nombre': u['nombre'], 'tipo': u['tipo'], 'sistema': None, 'set': None, 'barra': None, 'tension_kv': None,
                '_motivos': {}}
        if ub is None:
            motivo = f'el alimentador {u["alimentador"]} no está en la topología del área'
            avisos.append(f'{u["nombre"]}: {motivo}')
            for campo in ('sistema', 'set', 'barra', 'tension_kv'):
                base['_motivos'][campo] = motivo
        else:
            base.update({k: ub[k] for k in ('sistema', 'set', 'barra', 'tension_kv')})
            if ub.get('motivo'):
                base['_motivos'].update(barra=ub['motivo'], tension_kv=ub['motivo'])
        fac = f101.get((ub or {}).get('devanado') or '') or {}
        part = f103.get((ub or {}).get('devanado') or '') or {}
        mw = [kw / 1000 for kw in _serie_kw(u, anio_0, horizonte)]
        nivel = u.get('nivel') or _nivel(base['tension_kv'], niveles)
        def por(factor: Any, serie: Sequence[float]) -> list[float | None]:
            return [None if factor is None else v * float(factor) for v in serie]
        fc, fcp, fs = fac.get('fc'), fac.get('fcp'), fac.get('fs')
        energia = [None if fc is None else v * t * float(fc) for v in mw]
        if motivo_fe:
            con_perdidas, motivo_perdidas = [None] * len(energia), motivo_fe
        else:
            k = {'MAT': 1.0, 'AT': 1.0, 'MT': fe['PEMT'], 'BT': fe['PEBT'] * fe['PESED'] * fe['PEMT']}.get(nivel)
            con_perdidas = [None if k is None or e is None else e * k for e in energia]
            motivo_perdidas = None if k is not None else f'nivel de tensión del usuario no reconocido ({base["tension_kv"]} kV)'
        sin = f'sin factores del devanado del usuario en el F-101: {fac.get("motivo") or "no está en la 3b"}'
        series = {'F-114': ('energia_mwh', energia, sin if fc is None else None, 'P · t · FC'),
                  'F-115': ('energia_mwh', con_perdidas, motivo_perdidas or (sin if fc is None else None),
                            'P · t · FC · FE de su nivel (fijación vigente)'),
                  'F-116': ('potencia_mw', mw, None, 'máxima demanda del libro o del perfil, desde su año de ingreso'),
                  'F-117': ('potencia_mw', por(fcp, mw), sin if fcp is None else None, 'P · FCP'),
                  'F-118': ('potencia_mw', por(fs, mw), sin if fs is None else None, 'P · FS')}
        for codigo, (campo, valores, motivo, calculo) in series.items():
            fila = {**base, campo: valores, '_motivos': {**base['_motivos'], campo: motivo or 'sin valor ese año',
                                                         '_calculo:' + campo: f'{calculo}; {DEDUCIDO}'}}
            filas[codigo].append(fila)
        p0 = mw[0] if mw[0] else next((v for v in mw if v), None)
        uno = {**base, 'maxima_mw': p0, 'coincidente_set_mw': None if p0 is None or fcp is None else p0 * float(fcp),
               'coincidente_sein_mw': None if p0 is None or fs is None else p0 * float(fs),
               'energia_mwh': None if p0 is None or fc is None else p0 * t * float(fc), 'fphms': part.get('fphms'),
               'fcp': fcp, 'fs': fs}
        uno['_motivos'] = {**base['_motivos'], **{c: sin for c in ('coincidente_set_mw', 'coincidente_sein_mw',
                                                                   'energia_mwh', 'fcp', 'fs') if uno[c] is None},
                           'fphms': part.get('motivo') or 'sin FPHMS del devanado en el F-103',
                           '_calculo:energia_mwh': DEDUCIDO, '_calculo:coincidente_set_mw': DEDUCIDO,
                           '_calculo:coincidente_sein_mw': DEDUCIDO}
        filas['F-113'].append(uno)
    libres_resumen = {'F-115': filas['F-115'], 'F-116': filas['F-116'], 'F-117': filas['F-117'], 'F-118': filas['F-118']}
    if not usuarios:
        libres_resumen = {'sin_usuarios_libres': avisos[0]}
    return {'horizonte': horizonte, 'filas': filas, 'avisos': avisos, 'para_resumen': libres_resumen,
            'perdidas': fe['traza'] if fe else {'motivo': motivo_fe}}


def celdas_usuarios(registro: RegistroNormativo, proyeccion: Mapping[str, Any], area: str | None,
                    fuente: Mapping[str, str], fecha: str | None = None) -> dict[str, Any]:
    """F-113 a F-118 por el motor común de plantillas."""
    from .demanda_resumen import HUECO_TOTALES
    salida = {}
    for codigo, filas in proyeccion['filas'].items():
        r = celdas_de_formato(registro, codigo, {'fuente': fuente, 'cabecera': {'area': area},
                                                 'bloques': {'usuarios': filas}}, fecha=fecha)
        r['avisos'] = list(r.get('avisos') or []) + list(proyeccion['avisos'])
        if codigo != 'F-113':
            r['huecos'].append({'bloque': 'totales', 'causa': HUECO_TOTALES})
        salida[codigo] = r
    return salida
