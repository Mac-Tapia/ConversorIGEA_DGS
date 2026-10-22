"""Metodología del PIDE sobre la red calibrada (spec 024, T13; RF-49 a RF-53, RF-60 a RF-63).

Sigue la «Norma Criterios y Metodología de Planificación para la Elaboración del Plan de
Inversión en Distribución Eléctrica (PIDE)», prepublicada con la RM 428-2017-MEM/DM, en su
orden: análisis del mercado (art. 7), diagnóstico de lo existente (art. 8), formulación de
alternativas (art. 9 y 12) y resultados en sus formatos (art. 18). La evaluación económica
y la priorización (art. 14 y 15) están en ``pide_economia``.

Puro: recibe la lectura del flujo de DIgSILENT (la de ``tools/digital_twin_snapshot_pf.py``)
y los parámetros del perfil; no supone ninguna tasa ni tolerancia que el perfil no dé.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Tabla N.º 2 de la norma: zona por densidad de carga (MW/km²), de mayor a menor.
RANGOS_DENSIDAD = (('Muy Alta', 4.00, 'Rojo'), ('Alta 1', 2.50, 'Anaranjado'),
                   ('Alta 2', 1.50, 'Azul'), ('Media', 0.25, 'Verde'), ('Baja', 0.0, 'Amarillo'))

#: Lados de cuadrícula del art. 7.11, en metros.
LADOS_CUADRICULA = (1000, 500, 250)

#: Rubros del art. 9.3 y 12.4.
RUBROS = ('ampliacion_reforzamiento', 'mejoramiento', 'remodelacion', 'innovacion_eficiencia',
          'seguridad')

#: Alternativa del PIDE → rubro (art. 12.4: bancos y reguladores son mejoramiento de la
#: calidad de producto; el resto amplía o refuerza la red).
RUBRO_DE_ALTERNATIVA = {'bancos': 'mejoramiento', 'reguladores': 'mejoramiento',
                        'cambio_seccion': 'ampliacion_reforzamiento',
                        'nueva_terna': 'ampliacion_reforzamiento',
                        'refuerzo_red': 'ampliacion_reforzamiento',
                        'nueva_sed': 'ampliacion_reforzamiento',
                        'nuevo_alimentador': 'ampliacion_reforzamiento',
                        'nueva_set': 'ampliacion_reforzamiento'}

#: Carácter de cada alternativa (art. 12): general, lo pequeño o repetitivo; específico, lo
#: de gran envergadura como el reforzamiento de alimentadores.
CARACTER_DE_ALTERNATIVA = {'bancos': 'general', 'reguladores': 'general', 'nueva_sed': 'general',
                           'cambio_seccion': 'especifico', 'nueva_terna': 'especifico',
                           'refuerzo_red': 'especifico', 'nuevo_alimentador': 'especifico',
                           'nueva_set': 'especifico'}

#: Causa del diagnóstico → alternativas que la resuelven, de menor a mayor intervención.
ALTERNATIVAS_POR_CAUSA = {
    'caida_de_tension': ('bancos', 'reguladores', 'cambio_seccion', 'nueva_terna', 'nuevo_alimentador'),
    'factor_de_potencia': ('bancos',),
    'conductor_insuficiente': ('cambio_seccion', 'nueva_terna', 'nuevo_alimentador'),
    'transformador_sobrecargado': ('nueva_sed',),
    'isla_sin_fuente': ('refuerzo_red',),
    'perdidas_sobre_reconocidas': ('bancos', 'cambio_seccion'),
    'sobretension': ('reguladores',),
    'cabecera_sobrecargada': ('nuevo_alimentador', 'nueva_set'),
}


class PideError(ValueError):
    """Falta un dato que la norma pide y el perfil no da: se dice cuál, no se supone."""


# ------------------------------------------------------------------ mercado (art. 7)
def tasa_de_crecimiento(historico: Sequence[float]) -> float:
    """Tasa media anual compuesta de una serie histórica (art. 7.3), sin años nulos."""
    serie = [float(x) for x in historico if x is not None and float(x) > 0]
    if len(serie) < 2:
        raise PideError('hacen falta al menos dos años con demanda para estimar el crecimiento')
    return (serie[-1] / serie[0]) ** (1 / (len(serie) - 1)) - 1


def proyectar(base: float, tasa: float, horizonte: int = 20) -> list[float]:
    """Valor del año 00 al ``horizonte`` con la tasa anual compuesta (art. 7.4, 7.8)."""
    return [base * (1 + tasa) ** t for t in range(horizonte + 1)]


def zona_de_densidad(mw_km2: float) -> tuple[str, str]:
    """Zona y color de la Tabla N.º 2."""
    for zona, minimo, color in RANGOS_DENSIDAD:
        if mw_km2 >= minimo:
            return zona, color
    return RANGOS_DENSIDAD[-1][0], RANGOS_DENSIDAD[-1][2]


def cuadriculas(puntos: Iterable[tuple[float, float, float, bool]], lado_m: int) -> dict[tuple[int, int], dict]:
    """Densidad de carga por cuadrícula UTM alineada a múltiplos del lado (art. 7.9 a 7.11).

    ``puntos``: (este, norte, kW, concentrada). Cada celda da la demanda total y la de
    cargas concentradas en MW, su densidad y su zona.
    """
    if lado_m not in LADOS_CUADRICULA:
        raise PideError(f'la norma usa cuadrículas de {LADOS_CUADRICULA} m, no de {lado_m}')
    celdas: dict[tuple[int, int], dict] = {}
    area_km2 = (lado_m / 1000) ** 2
    for este, norte, kw, concentrada in puntos:
        clave = (math.floor(este / lado_m) * lado_m, math.floor(norte / lado_m) * lado_m)
        c = celdas.setdefault(clave, {'mw': 0.0, 'mw_concentradas': 0.0})
        c['mw'] += kw / 1000
        if concentrada:
            c['mw_concentradas'] += kw / 1000
    for c in celdas.values():
        c['densidad_mw_km2'] = c['mw'] / area_km2
        c['zona'], c['color'] = zona_de_densidad(c['densidad_mw_km2'])
    return celdas


# ------------------------------------------------------------------ diagnóstico (art. 8)
@dataclass(frozen=True)
class Problema:
    """Una condición inadecuada de operación (art. 8.5), con su ubicación y su causa."""

    tipo: str            # tension | cargabilidad | transformador | isla | perdidas
    elemento: str
    valor: float | None
    limite: float | None
    causa: str
    evidencia: str
    anio: int = 0        # primer año del horizonte en que incumple (RF-51)


def _nombre(ident: str, barras: Mapping[str, Mapping]) -> str:
    return str((barras.get(ident) or {}).get('nombre') or ident.rsplit('\\', 1)[-1])


def diagnosticar(lectura: Mapping[str, Any], *, tension_min_pu: float, tension_max_pu: float,
                 cargabilidad_max_pct: float, transformador_max_pct: float | None,
                 perdidas_reconocidas_pct: float | None = None,
                 fp_minimo: float | None = None) -> list[Problema]:
    """Diagnóstico de la red con lo que dio el flujo (RF-49, RF-50, RF-61).

    La causa sale de la evidencia del flujo: una barra de media tensión baja con el
    factor de potencia de cabecera bajo es compensación reactiva; sin eso, caída de
    tensión en el alimentador; una de baja tensión con su transformador sobre el umbral,
    el transformador; una línea sobre su capacidad, el conductor.
    """
    flujo = lectura.get('flujo') or {}
    topo = lectura.get('topologia') or {}
    barras = topo.get('barras') or {}
    tensiones = (flujo.get('tensiones') or {}).get('valores') or {}
    carga = (flujo.get('cargabilidad') or {}).get('valores') or {}
    fp_cab = (flujo.get('balance') or {}).get('fp_cabeceras') or {}
    fp_bajo = fp_minimo is not None and any(v is not None and v < fp_minimo for v in fp_cab.values())
    trafos_sobre = {k for k, v in (carga.get('transformadores') or {}).items()
                    if transformador_max_pct is not None and v > transformador_max_pct}
    problemas: list[Problema] = []
    for ident, v in sorted(tensiones.items()):
        kv = (barras.get(ident) or {}).get('kv')
        nombre = _nombre(ident, barras)
        if v < tension_min_pu:
            if kv is not None and kv < 1.0 and trafos_sobre:
                causa = 'transformador_sobrecargado'
                evidencia = f'barra de baja; transformadores sobre el umbral: {len(trafos_sobre)}'
            elif fp_bajo:
                causa, evidencia = 'factor_de_potencia', f'FP de cabecera bajo: {fp_cab}'
            else:
                causa, evidencia = 'caida_de_tension', 'caída a lo largo del alimentador'
            problemas.append(Problema('tension', nombre, v, tension_min_pu, causa, evidencia))
        elif v > tension_max_pu:
            problemas.append(Problema('tension', nombre, v, tension_max_pu, 'sobretension',
                                      'tensión sobre la banda de la norma'))
    for ident, pct in sorted((carga.get('lineas') or {}).items()):
        if pct > cargabilidad_max_pct:
            problemas.append(Problema('cargabilidad', ident.rsplit('\\', 1)[-1], pct,
                                      cargabilidad_max_pct, 'conductor_insuficiente',
                                      'corriente sobre la capacidad del conductor'))
    for ident in sorted(trafos_sobre):
        pct = carga['transformadores'][ident]
        problemas.append(Problema('transformador', ident.rsplit('\\', 1)[-1], pct,
                                  transformador_max_pct, 'transformador_sobrecargado',
                                  'máxima sobre el umbral de la NTP 370.400'))
    sin = (flujo.get('tensiones') or {}).get('sin_tension') or []
    if sin:
        problemas.append(Problema('isla', f'{len(sin)} barras', 0.0, None, 'isla_sin_fuente',
                                  'barras sin tensión: islas sin fuente'))
    perdidas = (flujo.get('perdidas') or {}).get('valores') or {}
    cabeceras = ((flujo.get('balance') or {}).get('valores') or {}).get('cabeceras') or {}
    entrada = sum(v for v in cabeceras.values() if v is not None)
    if perdidas_reconocidas_pct is not None and entrada > 0 and perdidas.get('total') is not None:
        pct = 100 * perdidas['total'] / entrada
        if pct > perdidas_reconocidas_pct:
            problemas.append(Problema('perdidas', 'red', pct, perdidas_reconocidas_pct,
                                      'perdidas_sobre_reconocidas',
                                      'pérdidas técnicas sobre las reconocidas en el VAD'))
    return problemas


def anio_de_incumplimiento(valor: float, limite: float, tipo: str, tasa: float,
                           horizonte: int = 20) -> int | None:
    """Primer año en que incumple con la demanda creciendo a ``tasa`` (RF-51).

    Aproximación de planificación: la caída de tensión (1 − V) y la cargabilidad crecen
    con la carga. Cada año candidato se confirma en DIgSILENT (RF-53, ``tools/pide_pf.py``).
    """
    for t in range(horizonte + 1):
        f = (1 + tasa) ** t
        if tipo == 'tension':
            if 1 - (1 - valor) * f < limite:
                return t
        elif valor * f > limite:
            return t
    return None


def problemas_futuros(lectura: Mapping[str, Any], *, tasa: float, horizonte: int,
                      tension_min_pu: float, cargabilidad_max_pct: float,
                      transformador_max_pct: float | None) -> list[Problema]:
    """Lo que hoy cumple y deja de cumplir dentro del horizonte, con su año (RF-51)."""
    flujo = lectura.get('flujo') or {}
    barras = (lectura.get('topologia') or {}).get('barras') or {}
    out = []
    for ident, v in sorted(((flujo.get('tensiones') or {}).get('valores') or {}).items()):
        if v >= tension_min_pu:
            t = anio_de_incumplimiento(v, tension_min_pu, 'tension', tasa, horizonte)
            if t is not None:
                out.append(Problema('tension', _nombre(ident, barras), v, tension_min_pu,
                                    'caida_de_tension', f'deja de cumplir en el año {t:02d}', t))
    carga = (flujo.get('cargabilidad') or {}).get('valores') or {}
    for grupo, limite, tipo, causa in (('lineas', cargabilidad_max_pct, 'cargabilidad', 'conductor_insuficiente'),
                                       ('transformadores', transformador_max_pct, 'transformador',
                                        'transformador_sobrecargado')):
        if limite is None:
            continue
        for ident, pct in sorted((carga.get(grupo) or {}).items()):
            if pct <= limite:
                t = anio_de_incumplimiento(pct, limite, 'carga', tasa, horizonte)
                if t is not None:
                    out.append(Problema(tipo, ident.rsplit('\\', 1)[-1], pct, limite, causa,
                                        f'deja de cumplir en el año {t:02d}', t))
    return out


# ------------------------------------------------------------------ plan por etapas (RF-52)
@dataclass
class ObraPropuesta:
    anio: int
    alternativa: str
    rubro: str
    elemento: str
    causa: str
    problemas: list[str] = field(default_factory=list)


def plan_por_etapas(problemas: Iterable[Problema], *, anios_pide: Sequence[int],
                    costo_relativo: Mapping[str, float] | None = None) -> list[ObraPropuesta]:
    """Una obra por causa y elemento, en el año en que hace falta (RF-52).

    Entre las alternativas que resuelven la causa se toma la de menor costo relativo
    (del libro CAPEX, ``pide_economia``) y, sin costos, la de menor intervención. Una obra
    no se adelanta: va en el año de su primer incumplimiento; uno anterior al periodo de
    fijación entra en su primer año (las de hoy, en el año 04). Las caídas de tensión del
    mismo alimentador se resuelven con una sola obra.
    """
    obras: dict[tuple[str, str], ObraPropuesta] = {}
    primero = min(anios_pide) if anios_pide else 0
    for p in sorted(problemas, key=lambda x: (x.anio, x.causa, x.elemento)):
        candidatas = ALTERNATIVAS_POR_CAUSA.get(p.causa)
        if not candidatas:
            continue
        if costo_relativo:
            alternativa = min(candidatas, key=lambda a: (costo_relativo.get(a, math.inf), candidatas.index(a)))
        else:
            alternativa = candidatas[0]
        clave = (p.causa, p.elemento if p.tipo != 'tension' else alternativa)
        anio = max(p.anio, primero)
        if clave in obras:
            obras[clave].anio = min(obras[clave].anio, anio)
            obras[clave].problemas.append(f'{p.elemento}: {p.evidencia}')
            continue
        obras[clave] = ObraPropuesta(anio, alternativa, RUBRO_DE_ALTERNATIVA[alternativa],
                                     p.elemento, p.causa, [f'{p.elemento}: {p.evidencia}'])
    return sorted(obras.values(), key=lambda o: (o.anio, o.rubro, o.alternativa, o.elemento))


# ------------------------------------------------------------------ formatos (art. 18)
#: Encabezados de los formatos del anexo de la norma (RF-63).
FORMATOS: dict[str, tuple[str, ...]] = {
    'F01 Proyección': ('Sistema', 'Año', 'Energía MT MW.h', 'Demanda MT MW', 'Tasa %'),
    'F02 Metrados': ('Sistema', 'Nivel', 'Elemento', 'Unidad', 'Cantidad'),
    'F03 Tensión MT': ('Centro de transformación', 'Alimentador', 'Nivel kV', 'Demanda MW',
                       'FP', 'FC', 'Longitud km', 'Caída máxima %'),
    'F04 Tensión BT': ('Centro de transformación', 'Alimentador', 'SED', 'Nivel kV', 'Demanda MW',
                       'FP', 'FC', 'Longitud km', 'Caída máxima %'),
    'F05 Pérdidas': ('Sistema', 'Nivel', 'Tipo', 'Componente', '%'),
    'F06 Calidad suministro': ('Centro de transformación', 'Alimentador', 'SAIFI', 'SAIDI', 'N', 'D'),
    'F07 Alternativas estudio': ('Año', 'Rubro', 'Código', 'Alternativa', 'Costo US$', 'US$/kW',
                                 'US$/kW.h', 'US$/usuario', 'US$/km'),
    'F08 Alternativas PIDE': ('Año', 'Rubro', 'Código', 'Alternativa', 'Usuarios', 'Demanda kW',
                              'Energía kW.h', 'km MT', 'kVA SED', 'km BT'),
    'F09 Evaluación económica': ('Año', 'Rubro', 'Código', 'Alternativa', 'Costo US$', 'US$/kW',
                                 'US$/kW.h', 'US$/usuario', 'US$/km', 'VAN US$', 'Costo anual US$', 'TIR'),
    'F10 Propuesta empresa': ('Año', 'Rubro', 'Usuarios', 'Demanda kW', 'Energía kW.h', 'Inversión US$',
                              'Anualidad US$', 'COyM US$', 'Costo anual US$'),
    'F11 Propuesta sistema': ('Sistema', 'Año', 'Rubro', 'Inversión US$', 'Anualidad US$', 'COyM US$',
                              'Costo anual US$'),
    'F12 Propuesta proyecto': ('Sistema', 'Año', 'Rubro', 'Código', 'Proyecto', 'Inversión US$',
                               'Anualidad US$', 'COyM US$', 'Costo anual US$'),
    'F13 Detalle de costos': ('Sistema', 'Año', 'Rubro', 'Código', 'Proyecto', 'LP', 'RP', 'Reforzamiento',
                              'EPyS', 'SED', 'Red SP', 'Red AP', 'Equipos AP', 'Conexiones', 'Total'),
    'F14 Ficha técnica': ('Código', 'Proyecto', 'Ubicación', 'Objetivo', 'Alcance',
                          'Especificaciones técnicas', 'Usuarios', 'Demanda kW', 'Energía kW.h'),
    'F15 Ficha económica': ('Código', 'Proyecto', 'Ítem', 'Costo US$'),
}


def escribir_formatos(ruta: Path, filas: Mapping[str, Sequence[Sequence[Any]]]) -> Path:
    """Los formatos 01 a 15 en un libro, una hoja por formato, con lo que haya (RF-63).

    Un formato sin filas queda con su encabezado y la nota de qué falta, para que se vea
    el hueco en vez de una hoja que parece completa.
    """
    from openpyxl import Workbook

    libro = Workbook()
    libro.remove(libro.active)
    for nombre, cabecera in FORMATOS.items():
        hoja = libro.create_sheet(nombre[:31])
        hoja.append(list(cabecera))
        datos = filas.get(nombre) or []
        for fila in datos:
            hoja.append(list(fila))
        if not datos:
            hoja.append(['sin datos en esta ejecución'])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix('.tmp.xlsx')
    libro.save(tmp)
    tmp.replace(ruta)
    return ruta
