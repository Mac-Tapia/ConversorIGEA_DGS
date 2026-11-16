"""Los formatos 01 a 15 con lo calculado y cada hueco con su nombre (072:RF-13, RF-14, RF-16).

Una celda vacía sin explicación se lee como un cero o como un descuido. Por eso cada campo que queda
sin dato lleva su motivo, y un costo que no se conoce queda vacío en vez de valer 0. Puro: recibe lo
que ya calcularon el diagnóstico, la propuesta, la proyección y los metrados; no lee DIgSILENT.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .costos_fuentes import partir_codigo_vnr
from .estudio_planeamiento import Estudio
from .pide import FORMATOS
from .proyeccion_mercado import METODOS, SerieMercado

#: Por qué falta un formato entero.
MOTIVO_DEL_FORMATO = {
    'F01 Proyección': 'el plan no trae el libro del Formato 01 de la empresa («formato_01»)',
    'F02 Metrados': 'no hay red cargada en este espacio de la que medir los tramos',
    'F03 Tensión MT': 'el diagnóstico no devolvió ningún año convergido',
    'F04 Tensión BT': 'el diagnóstico no trajo la tensión de las barras de baja de las SED',
    'F05 Pérdidas': 'el flujo no dio las pérdidas: falta la cabecera o el consumo de algún alimentador',
    'F06 Calidad suministro': 'no se pasaron los índices de confiabilidad (spec 012)',
    'F07 Alternativas estudio': 'el diagnóstico no encontró problemas que pidan obras',
    'F08 Alternativas PIDE': 'el diagnóstico no encontró problemas que pidan obras',
    'F09 Evaluación económica': 'el diagnóstico no encontró problemas que pidan obras',
    'F10 Propuesta empresa': 'ninguna obra quedó en la cartera',
    'F11 Propuesta sistema': 'ninguna obra quedó en la cartera',
    'F12 Propuesta proyecto': 'ninguna obra quedó en la cartera',
    'F13 Detalle de costos': 'ninguna obra quedó en la cartera',
    'F14 Ficha técnica': 'ninguna obra quedó en la cartera',
    'F15 Ficha económica': 'ninguna obra quedó en la cartera',
}

_SIN_CAPEX = 'sin libro CAPEX ni costo oficial para esta alternativa'
_SIN_DEMANDA = 'la obra no atiende demanda nueva medida entre años'
_MOTIVOS = {
    ('Sistema',): 'la estructura de la empresa no ubica este alimentador en un sistema eléctrico',
    ('Centro de transformación',): 'la estructura de la empresa no ubica este alimentador en una SET',
    ('Nivel',): 'el código del tramo no trae la letra de su tensión',
    ('Elemento', 'Unidad', 'Cantidad', 'Año', 'Rubro', 'Código', 'Alternativa', 'Proyecto', 'Ítem', 'Ubicación',
     'Objetivo', 'Alcance', 'Tipo', 'Componente', 'Alimentador'): 'la obra no trae este dato',
    ('Energía MT MW.h', 'Tasa %'): 'la serie del sistema no alcanza para proyectarlo',
    ('Demanda MT MW',): 'el perfil no declara el factor de carga con que se pasa de energía a demanda',
    ('Nivel kV',): 'el flujo no dio barras de media tensión en este alimentador',
    ('Demanda MW',): 'la cabecera no dio su potencia',
    ('FP',): 'la cabecera no dio su potencia activa y reactiva',
    ('FC',): 'el perfil no declara el factor de carga',
    ('Longitud km',): 'el diagnóstico no trajo la longitud del alimentador',
    ('Caída máxima %',): 'el flujo no dio tensiones en este alimentador',
    ('%',): 'la cabecera no dio su potencia',
    ('SAIFI', 'SAIDI'): 'el estudio de confiabilidad no dio este índice: DIgSILENT no lo calculó de forma fiable',
    ('N', 'D'): 'el estudio de confiabilidad da SAIFI y SAIDI, no el número y la duración de la NTCSE',
    ('Costo US$', 'Inversión US$', 'Anualidad US$', 'Total'): _SIN_CAPEX,
    # 072:RF-16 (H5): el costo anual del art. 14.4 suma tres cosas, y basta que falte una para no tenerlo.
    ('Costo anual US$',): ('el costo anual (art. 14.4) suma la anualidad, el COyM y el costo de las pérdidas, y a la '
                           'obra le falta alguno: el libro CAPEX, el COyM del perfil o las pérdidas valoradas de la obra'),
    ('COyM US$',): 'el perfil no da el costo de operación y mantenimiento',
    ('US$/kW',): f'{_SIN_CAPEX}, o {_SIN_DEMANDA}',
    ('US$/kW.h',): 'hacen falta el costo, la demanda nueva y el factor de carga',
    ('US$/usuario', 'Usuarios'): 'el diagnóstico no cuenta los usuarios que atiende cada obra',
    ('US$/km', 'km MT', 'km BT'): 'la obra no tiene metrado propio hasta que se diseñe su trazo',
    ('kVA SED',): 'la obra no tiene metrado propio hasta que se diseñe',
    ('Demanda kW',): _SIN_DEMANDA,
    ('Energía kW.h',): f'{_SIN_DEMANDA}, o el perfil no declara el factor de carga',
    ('VAN US$', 'TIR'): 'evaluación privada sin hacer: faltan tarifa, tasa privada, factor de carga o precio de compra',
    ('LP', 'RP', 'Reforzamiento', 'EPyS', 'SED', 'Red SP', 'Red AP', 'Equipos AP', 'Conexiones'):
        'el costo de la obra viene en un solo total: falta su desglose por componentes',
    ('Especificaciones técnicas',): 'las especificaciones salen del diseño de la obra',
}
MOTIVO_DEL_CAMPO: dict[str, str] = {campo: motivo for campos, motivo in _MOTIVOS.items() for campo in campos}
#: F04 va por SED: los mismos rótulos de F03 faltan allí por otra razón.
MOTIVO_EN_FORMATO = {('F04 Tensión BT', 'Demanda MW'): 'el diagnóstico no lee la demanda de cada SED en cada año',
                     ('F04 Tensión BT', 'FP'): 'el diagnóstico no lee el factor de potencia de cada SED',
                     ('F04 Tensión BT', 'Longitud km'): 'el modelo lleva la barra de baja de cada SED, no su red de baja'}
#: El alcance de lo que sí se midió en F04: no es el extremo de la red de baja, que no está modelada.
ALCANCE_F04 = 'medida en la barra de baja de cada SED; no incluye la caída en la red de baja, que no está modelada'
#: 072:RF-16 (H5): la VAN y la TIR de un flujo privado que no lleva todos sus costos se escriben, pero no como completas.
ALCANCE_DEL_FLUJO_PRIVADO = ('el flujo privado no lleva el COyM o el costo de las pérdidas de la obra: la VAN y la TIR '
                             'quedan por encima de las reales')

#: 025:RF-68 / 072:RF-16 (H4 y H5): lo que dice la celda cuando la evaluación no se hizo por falta del tipo de cambio,
#: en vez de un 0 o de un blanco que se confunda con otro motivo. ``huecos_de`` la cuenta como hueco con su motivo.
SIN_TIPO_DE_CAMBIO = 'sin tipo de cambio'
MOTIVO_DE_LA_MARCA = {
    SIN_TIPO_DE_CAMBIO: ('las tarifas y el precio de compra están en otra moneda que el CAPEX y no se dio el tipo de '
                         'cambio: la evaluación privada y el valor de las pérdidas no se hacen (025:RF-68)'),
}


def _vacia(celda: Any) -> bool:
    return celda is None or celda == ''


def _marca(celda: Any) -> str | None:
    return celda if isinstance(celda, str) and celda in MOTIVO_DE_LA_MARCA else None


def huecos_de(filas: Mapping[str, Sequence[Sequence[Any]]]) -> list[dict[str, Any]]:
    """Cada formato sin filas y cada campo con celdas vacías o marcadas, con su motivo (072:RF-16)."""
    huecos: list[dict[str, Any]] = []
    for nombre, cabecera in FORMATOS.items():
        datos = filas.get(nombre) or []
        if not datos:
            huecos.append({'formato': nombre, 'campo': None, 'filas': 0, 'motivo': MOTIVO_DEL_FORMATO[nombre]})
            continue
        for i, campo in enumerate(cabecera):
            n = sum(i >= len(fila) or _vacia(fila[i]) for fila in datos)
            if n:
                huecos.append({'formato': nombre, 'campo': campo, 'filas': n,
                               'motivo': MOTIVO_EN_FORMATO.get((nombre, campo), MOTIVO_DEL_CAMPO[campo])})
            marcas = [m for fila in datos if i < len(fila) and (m := _marca(fila[i]))]
            for m in dict.fromkeys(marcas):
                huecos.append({'formato': nombre, 'campo': campo, 'filas': marcas.count(m),
                               'motivo': MOTIVO_DE_LA_MARCA[m]})
    return huecos


def alcance_de_la_evaluacion(obras: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """F09: las VAN y TIR escritas de flujos privados incompletos, con su marca (072:RF-16, H5)."""
    n = sum(1 for o in obras if (o.get('privada') or {}).get('completo') is False)
    return [{'formato': 'F09 Evaluación económica', 'campo': campo, 'filas': n, 'motivo': ALCANCE_DEL_FLUJO_PRIVADO}
            for campo in ('VAN US$', 'TIR')] if n else []


def filas_de_obras(obras: Sequence[Mapping[str, Any]], anios: Sequence[Mapping[str, Any]],
                   sistema_de: Mapping[str, str] | None = None, centro_de: Mapping[str, str] | None = None,
                   factor_carga: float | None = None) -> dict[str, list]:
    """F03 y F07 a F15: lo que sale del diagnóstico y de las obras (024:RF-63, 072:RF-14).

    La inversión desconocida queda vacía: como 0 parecería una obra gratuita. Y el alimentador no se
    escribe en «Sistema»: F12 lo hacía, y un sistema eléctrico agrupa a varios alimentadores.
    """
    sistema_de, centro_de = sistema_de or {}, centro_de or {}
    f: dict[str, list] = {}
    if anios:
        cabeceras = anios[0].get('cabeceras_kw') or {}
        red = anios[0].get('por_alimentador') or {}
        vm = anios[0].get('vm_min')
        # vm_min es de toda la red: sin el resumen por alimentador, solo se atribuye si hay uno solo.
        global_ = vm if len(cabeceras) == 1 else None
        f['F03 Tensión MT'] = []
        for a, kw in sorted(cabeceras.items()):
            r = red.get(a) or {}
            v = r.get('vm_min', global_)
            f['F03 Tensión MT'].append([centro_de.get(a), a, r.get('kv'), kw / 1000 if kw else None, r.get('fp'), factor_carga,
                                        r.get('km'), round(100 * (1 - v), 2) if v else None])
    f['F07 Alternativas estudio'] = [[o['anio'], o['rubro'], o['codigo'], o['alternativa'], o['ci'] or None,
                                      o['indicadores'].get('costo_kw'), o['indicadores'].get('costo_kwh'),
                                      o['indicadores'].get('costo_usuario'), o['indicadores'].get('costo_km')]
                                     for o in obras]
    f['F08 Alternativas PIDE'] = [[o['anio'], o['rubro'], o['codigo'], o['alternativa'], None, o.get('kw_nuevos') or None,
                                   o.get('energia_kwh') or None, None, None, None] for o in obras]
    f['F09 Evaluación económica'] = [[o['anio'], o['rubro'], o['codigo'], o['alternativa'], o['ci'] or None,
                                      o['indicadores'].get('costo_kw'), o['indicadores'].get('costo_kwh'),
                                      o['indicadores'].get('costo_usuario'), o['indicadores'].get('costo_km'),
                                      _privada(o, 'van'), _costo_anual(o), _privada(o, 'tir')] for o in obras]
    cartera = [o for o in obras if not (o['descartada'] or o['sobredimensionada'])]
    f['F10 Propuesta empresa'] = _por_grupo(cartera, lambda o: (o['anio'], o['rubro']))
    por_sistema = _por_grupo(cartera, lambda o: (sistema_de.get(o['alimentador']), o['anio'], o['rubro']))
    # Tras la clave de tres campos van usuarios, demanda, energía, inversión, anualidad, COyM y costo anual.
    f['F11 Propuesta sistema'] = [[*fila[:3], *fila[6:]] for fila in por_sistema]
    f['F12 Propuesta proyecto'] = [[sistema_de.get(o['alimentador']), o['anio'], o['rubro'], o['codigo'], _proyecto(o),
                                    o['ci'] or None, _si_hay_costo(o, 'anualidad'), _si_hay_costo(o, 'coym'),
                                    _costo_anual(o)]
                                   for o in cartera]
    f['F13 Detalle de costos'] = [[sistema_de.get(o['alimentador']), o['anio'], o['rubro'], o['codigo'], _proyecto(o),
                                   *[None] * 9, o['ci'] or None] for o in cartera]
    f['F14 Ficha técnica'] = [[o['codigo'], _proyecto(o), o['alimentador'], o['causa'],
                               f"{o['alternativa']} en {o['elemento']}", None, None,
                               o.get('kw_nuevos') or None, o.get('energia_kwh') or None] for o in cartera]
    f['F15 Ficha económica'] = [[o['codigo'], _proyecto(o), item, valor] for o in cartera
                                for item, valor in (('Inversión', o['ci'] or None),
                                                    ('Anualidad', _si_hay_costo(o, 'anualidad')))]
    return f


def _si_hay_costo(obra: Mapping[str, Any], clave: str) -> float | None:
    """Sin inversión conocida, la anualidad y el costo anual valdrían 0 y parecerían un resultado."""
    return obra['regulada'].get(clave) if obra['ci'] else None


def _costo_anual(obra: Mapping[str, Any]) -> float | str | None:
    """El costo anual solo si está completo (072:RF-16, H5): anualidad + COyM sin las pérdidas no lo es.

    Sin tipo de cambio, las pérdidas no se pueden valorar y la celda lo dice (025:RF-68).
    """
    if obra['ci'] and obra['regulada'].get('completo') is True:
        return obra['regulada'].get('costo_anual')
    return SIN_TIPO_DE_CAMBIO if obra.get('sin_tipo_de_cambio') else None


def _privada(obra: Mapping[str, Any], clave: str) -> float | str | None:
    """VAN o TIR del flujo privado; sin tipo de cambio la celda lo dice en vez de quedar como otro hueco (025:RF-68)."""
    valor = (obra.get('privada') or {}).get(clave)
    return SIN_TIPO_DE_CAMBIO if valor is None and obra.get('sin_tipo_de_cambio') else valor


def _suma(valores: Sequence[float | None]) -> float | None:
    """La suma de un grupo, o nada si a una de sus obras le falta el dato: una suma parcial engañaría (H5)."""
    return None if not valores or any(v is None for v in valores) else sum(valores)


def _proyecto(obra: Mapping[str, Any]) -> str:
    return obra.get('denominacion') or obra['alternativa']


def _por_grupo(obras: Iterable[Mapping[str, Any]], clave) -> list[list]:
    """Filas de F10: la clave, y usuarios, demanda, energía, inversión, anualidad, COyM y costo anual.

    072:RF-16, RF-22 (H5, 2026-11-14): cada suma solo si todas las obras del grupo traen el dato, como ya hacía el
    COyM. Antes la demanda, la energía, la inversión, la anualidad y el costo anual sumaban «or 0.0», y un grupo
    con una obra sin costo salía con la inversión de las otras como si fuera la de todas.
    """
    grupos: dict[tuple, dict[str, list]] = {}
    for o in obras:
        g = grupos.setdefault(clave(o), {'kw': [], 'kwh': [], 'ci': [], 'anu': [], 'coym': [], 'costo': [],
                                         'sin_tc': []})
        g['kw'].append(o.get('kw_nuevos'))
        g['kwh'].append(o.get('energia_kwh'))
        g['ci'].append(o['ci'] or None)
        g['anu'].append(_si_hay_costo(o, 'anualidad'))
        g['coym'].append(_si_hay_costo(o, 'coym'))
        costo = _costo_anual(o)
        g['costo'].append(costo if not isinstance(costo, str) else None)
        g['sin_tc'].append(bool(o.get('sin_tipo_de_cambio')))
    filas = []
    for k, g in sorted(grupos.items(), key=lambda x: tuple(str(v) for v in x[0])):
        ci = _suma(g['ci']) or None
        costo = _suma(g['costo']) if ci else None
        if costo is None and any(g['sin_tc']):
            costo = SIN_TIPO_DE_CAMBIO
        filas.append([*k, None, _suma(g['kw']) or None, _suma(g['kwh']) or None, ci,
                      _suma(g['anu']) if ci else None, _suma(g['coym']) if ci else None, costo])
    return filas


def filas_de_proyeccion(series: Iterable[SerieMercado], estudio: Estudio | None, *, metodo: str,
                        factor_carga: float | None) -> list[list]:
    """F01: la historia y lo proyectado por sistema, con el método que ganó la medida (072:RF-10).

    El Formato 01 entregado solo trae la demanda en los años proyectados, y sale de la energía con un
    factor de carga declarado: aquí igual, sin factor no se inventa la demanda.
    """
    proyectar = METODOS[metodo]
    filas: list[list] = []
    for s in series:
        ultimo = max(s.historico)
        hasta = estudio.calendario(max(estudio.largo_plazo)) if estudio else ultimo
        energia = dict(s.historico)
        if hasta > ultimo:
            energia |= proyectar(s.historico, ultimo, range(ultimo + 1, hasta + 1))
        for anio in sorted(energia):
            previo = energia.get(anio - 1)
            filas.append([s.nombre or s.codigo, anio, energia[anio],
                          energia[anio] / (8760 * factor_carga) if factor_carga and anio > ultimo else None,
                          100 * (energia[anio] / previo - 1) if previo else None])
    return filas


def filas_de_metrados(medidas: Iterable[tuple[str | None, Mapping[str, Any]]]) -> tuple[list[list], list[dict[str, Any]]]:
    """F02 por sistema y código, y los tramos sin código como hueco, no repartidos (072:RF-15)."""
    km: dict[tuple, float] = {}
    huecos = []
    for sistema, m in medidas:
        for codigo, fila in m['por_codigo'].items():
            clave = (sistema, partir_codigo_vnr(codigo)[1] or None, codigo)
            km[clave] = km.get(clave, 0.0) + fila['km']
        if m['sin_codigo']:
            huecos.append({'formato': 'F02 Metrados', 'campo': 'Elemento', 'filas': len(m['sin_codigo']),
                           'motivo': f"{m['km_sin_codigo']:.2f} km de tramos sin código, fuera de los metrados"})
    filas = [[s, nivel, codigo, 'km', v] for (s, nivel, codigo), v in sorted(km.items(), key=lambda x: tuple(map(str, x[0])))]
    return filas, huecos


def filas_de_baja(anios: Sequence[Mapping[str, Any]], centro_de: Mapping[str, str] | None = None,
                  factor_carga: float | None = None) -> list[list]:
    """F04: cada SED por su barra de baja, las de mayor caída primero (el Word muestra solo las primeras)."""
    centro_de = centro_de or {}
    baja = sorted((anios[0].get('sed_bt') or []) if anios else [], key=lambda b: b['vm'])
    return [[centro_de.get(b['alimentador']), b['alimentador'], b['sed'], b.get('kv'), None, None, factor_carga, None,
             round(100 * (1 - b['vm']), 2)] for b in baja]


def filas_de_perdidas(anios: Sequence[Mapping[str, Any]], sistema: str | None) -> list[list]:
    """F05: las pérdidas técnicas que midió el flujo del año base, sobre la potencia de cabecera."""
    if not anios or anios[0].get('perdidas_kw') is None:
        return []
    cabecera = sum(v for v in (anios[0].get('cabeceras_kw') or {}).values() if v)
    return [[sistema, 'MT y SED', 'Técnicas', 'Red de los alimentadores (flujo del año base)',
             100 * anios[0]['perdidas_kw'] / cabecera if cabecera else None]]


def filas_de_calidad(indices: Mapping[str, Mapping[str, Any]] | None, centro_de: Mapping[str, str] | None = None) -> list[list]:
    """F06: los índices por alimentador del estudio de confiabilidad (spec 012)."""
    centro_de = centro_de or {}
    return [[centro_de.get(a), a, i.get('saifi'), i.get('saidi'), i.get('n'), i.get('d')]
            for a, i in sorted((indices or {}).items())]


def formatos_del_estudio(obras: Sequence[Mapping[str, Any]], anios: Sequence[Mapping[str, Any]], *,
                         estudio: Estudio | None = None, series: Iterable[SerieMercado] = (),
                         metodo: str = 'tasa_de_un_anio', factor_carga: float | None = None,
                         metrados: Iterable[tuple[str | None, Mapping[str, Any]]] = (),
                         calidad: Mapping[str, Mapping[str, Any]] | None = None,
                         sistema_de: Mapping[str, str] | None = None, centro_de: Mapping[str, str] | None = None,
                         ) -> dict[str, Any]:
    """Los quince formatos de un estudio y lo que les falta (072:RF-13, RF-14, RF-16)."""
    filas = filas_de_obras(obras, anios, sistema_de, centro_de, factor_carga)
    metrado, huecos_metrado = filas_de_metrados(metrados)
    sistemas = {v for v in (sistema_de or {}).values() if v}
    filas.update({'F01 Proyección': filas_de_proyeccion(series, estudio, metodo=metodo, factor_carga=factor_carga),
                  'F02 Metrados': metrado,
                  'F04 Tensión BT': filas_de_baja(anios, centro_de, factor_carga),
                  # Varios sistemas no se reparten una sola medida de pérdidas.
                  'F05 Pérdidas': filas_de_perdidas(anios, next(iter(sistemas)) if len(sistemas) == 1 else None),
                  'F06 Calidad suministro': filas_de_calidad(calidad, centro_de)})
    alcance = [{'formato': 'F04 Tensión BT', 'campo': 'Caída máxima %', 'filas': len(filas['F04 Tensión BT']),
                'motivo': ALCANCE_F04}] if filas['F04 Tensión BT'] else []
    return {'filas': filas, 'huecos': huecos_de(filas) + huecos_metrado + alcance + alcance_de_la_evaluacion(obras)}
