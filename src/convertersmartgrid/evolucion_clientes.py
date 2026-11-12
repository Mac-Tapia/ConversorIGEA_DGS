"""Evolución mensual de los clientes fijos de uno o varios alimentadores y su libro Excel (spec 105).

Lee con los lectores de la calibración y del pronóstico (``leer_suministros``, ``libros_con_mes``,
``curvas_por_cliente``), sin otro lector: las cifras de cada cliente son las mismas que en la calibración. El cálculo de
los indicadores es de dominio (``dominio.evolucion_mensual``) y la detección del mes copiado también
(``dominio.meses_copiados``), para que el reconocimiento de libros (spec 104) use la misma.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import astuple, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .demanda_medida import (
    ALIAS, DemandaError, abrir_libro, buscar_cabecera, filas_de_hoja, leer_suministros, normalizar,
    texto_de_celda)
from .dominio.conciliacion_clientes import (
    cadenas_de_renumeracion, clave_cliente, fijos_sobre_cabecera, posibles_renumeraciones, veredicto)
from .dominio import evolucion_mensual as em
from .dominio.meses_copiados import mes_de_registro, meses_copiados
from .pronostico_demanda import curvas_de_cabecera, curvas_por_cliente, equivalencias, libros_con_mes, sentido_de_serie

Serie = tuple[np.ndarray, np.ndarray, np.ndarray]
#: Más alimentadores que esto no se nombran uno a uno en la carpeta: la ruta de Windows tiene un tope.
NOMBRADOS_MAX = 4
#: 105:RF-38: margen sobre la cabecera para la suma de los fijos (relojes y redondeos de los medidores).
MARGEN_CABECERA = 0.05


@dataclass(frozen=True)
class FuentesEvolucion:
    """Los libros ya asignados en el espacio (105:RF-1)."""
    clientes: Path
    suministros: Path
    patron: str | Sequence[str] | None = None
    asignaciones: dict[str, str] | None = None
    medidores: Path | None = None
    cabecera: tuple[Path, ...] = ()
    #: SED → alimentadores de la red convertida del espacio; ``None`` si no hay red cargada (105:RF-34).
    seds_red: Mapping[str, Iterable[str]] | None = None


@dataclass(frozen=True)
class ClienteFijo:
    codigo: str
    alimentador: str
    sed: str
    anteriores: tuple[str, ...] = ()
    cl: str = ''
    nombre: str = ''
    suministrador: str = ''


@dataclass
class Evolucion:
    """El resultado para la web (``datos``, JSON) y las curvas de 15 minutos, que van aparte por su tamaño."""
    datos: dict[str, Any]
    series: dict[str, Serie] = field(default_factory=dict)


def meses_del_rango(desde: str, hasta: str) -> list[str]:
    """Los meses ``AAAA-MM`` de ``desde`` a ``hasta``, ambos incluidos."""
    a, b = np.datetime64(desde, 'M'), np.datetime64(hasta, 'M')
    if b < a:
        raise ValueError(f'el rango empieza en {desde} y termina antes, en {hasta}')
    return [str(m) for m in np.arange(a, b + 1)]


def ambito(alimentadores: Sequence[str]) -> str:
    """El nombre de los alimentadores en una carpeta o un fichero."""
    nombres = sorted(dict.fromkeys(str(a).strip() for a in alimentadores if str(a).strip()))
    if len(nombres) <= NOMBRADOS_MAX:
        return '+'.join(nombres)
    return f'{nombres[0]}+{len(nombres) - 1}_mas'


@dataclass(frozen=True)
class FilaMaestro:
    """Un cliente en el resumen de un libro mensual (105:RF-34)."""
    codigo: str
    cl: str
    nombre: str
    suministrador: str
    alimentador: str
    sed: str


#: Las columnas del resumen de clientes que no están en los alias de la calibración.
_ALIAS_MAESTRO = {**ALIAS, 'cod_cl': ('cod cl', 'codigo cl', 'cl'), 'suministrador': ('suministrador',)}
_VACIOS = {'', 'nan', 'none', '-'}
_CAMPOS_MAESTRO = ('cod_cl', 'cliente_nombre', 'suministrador', 'radial', 'sed')


def _texto(fila, indice) -> str:
    t = texto_de_celda(fila, indice)
    return '' if t.casefold() in _VACIOS else t


def leer_maestro(libro: Path) -> dict[str, FilaMaestro]:
    """``{clave: fila}`` del resumen de un libro de clientes: NIS, CL, nombre, suministrador, alimentador y SED.

    Se miran las hojas «resumen» y «maestro_lib»; lo que una no trae (el alimentador no está en el maestro) se toma de
    la otra. Un libro que no se puede leer no da nada: lo dice el lector de curvas.
    """
    try:
        wb = abrir_libro(libro)
    except (DemandaError, OSError, ValueError):
        return {}
    salida: dict[str, FilaMaestro] = {}
    hojas = sorted((h for h in wb.sheet_names if 'resumen' in normalizar(h) or normalizar(h) == 'maestro lib'),
                   key=lambda h: normalizar(h) != 'resumen')
    for hoja in hojas:
        filas = filas_de_hoja(wb, hoja)
        hallada = buscar_cabecera(filas, ('cliente_codigo', *_CAMPOS_MAESTRO), _ALIAS_MAESTRO, ('cliente_codigo',))
        if hallada is None:
            continue
        i, cols = hallada
        for fila in filas[i + 1:]:
            codigo = _texto(fila, cols['cliente_codigo'])
            if not codigo:
                continue
            nueva = FilaMaestro(codigo, *(_texto(fila, cols.get(k)) for k in _CAMPOS_MAESTRO))
            previa = salida.get(clave_cliente(codigo))
            salida[clave_cliente(codigo)] = nueva if previa is None else FilaMaestro(
                *(a or b for a, b in zip(astuple(previa), astuple(nueva))))
    return salida


def clientes_fijos(libro_suministros: Path, alimentadores: Iterable[str],
                   maestros: Sequence[tuple[str, dict[str, FilaMaestro]]] = (),
                   seds_red: Mapping[str, Iterable[str]] | None = None,
                   ) -> tuple[dict[str, list[ClienteFijo]], dict[str, Any]]:
    """Los clientes de cada alimentador conciliando las fuentes (105:RF-2, RF-3, RF-34, RF-35).

    Un cliente es de un alimentador si su radial en el libro de suministros lo dice o, si no está allí, el resumen del
    último libro mensual que lo trae; nunca por el parecido de su nombre. ``maestros``: ``[(mes, {clave: fila})]`` en
    orden de mes; ``seds_red``: SED → alimentadores de la red cargada, o ``None`` sin red. Devuelve los clientes y la
    conciliación: renumeraciones con sus meses, canon, veredictos, propuestas y códigos de los libros sin suministro.
    """
    suministros, _avisos = leer_suministros(libro_suministros)
    pedidos = {clave_cliente(a): str(a).strip() for a in alimentadores if str(a).strip()}
    canon, avisos = cadenas_de_renumeracion((s.anterior, s.actual) for s in suministros if s.anterior and s.actual)

    def actual_de(c: str) -> str:
        return canon.get(clave_cliente(c), str(c).strip())

    de_sumi: dict[str, Any] = {}
    for s in suministros:
        de_sumi.setdefault(clave_cliente(actual_de(s.actual or s.anterior)), s)
    todos = set(canon) | set(de_sumi)
    ultimo: dict[str, tuple[str, FilaMaestro]] = {}
    vistos: dict[str, dict[str, list[str]]] = {}            # clave actual → código del libro → meses
    presencia: dict[str, dict[str, dict[str, str]]] = {}
    for mes, filas in maestros:
        for k, f in filas.items():
            clave = clave_cliente(actual_de(f.codigo))
            ultimo[clave] = (mes, f)
            vistos.setdefault(clave, {}).setdefault(f.codigo, []).append(mes)
            presencia.setdefault(mes, {})[k] = {'codigo': f.codigo, 'cl': f.cl, 'sed': f.sed}
    candidatos: dict[str, str] = {}
    for clave, s in de_sumi.items():
        if clave_cliente(s.radial) in pedidos:
            candidatos[clave] = pedidos[clave_cliente(s.radial)]
    for clave, (_mes, f) in ultimo.items():
        if clave not in de_sumi and clave_cliente(f.alimentador) in pedidos:
            candidatos[clave] = pedidos[clave_cliente(f.alimentador)]
    por: dict[str, list[ClienteFijo]] = {a: [] for a in pedidos.values()}
    veredictos: dict[str, dict] = {}
    renumeraciones: list[dict] = []
    for clave, alimentador in candidatos.items():
        s = de_sumi.get(clave)
        mes, f = ultimo.get(clave, (None, None))
        codigo = actual_de(s.actual or s.anterior) if s else actual_de(f.codigo)
        sed = (s.sed if s else '') or (f.sed if f else '')
        otros: dict[str, str] = {}
        for c in [*(x.anterior for x in suministros if x.anterior and clave_cliente(actual_de(x.anterior)) == clave),
                  *vistos.get(clave, {})]:
            if clave_cliente(c) != clave_cliente(codigo):
                otros.setdefault(clave_cliente(c), c)
        anteriores = tuple(sorted(otros.values()))
        for c in anteriores:
            renumeraciones.append({'anterior': c, 'actual': codigo, 'alimentador': alimentador,
                                   'meses': vistos.get(clave, {}).get(c, [])})
        fuentes: dict[str, dict | None] = {
            'suministros': {'alimentador': s.radial, 'sed': s.sed} if s else None,
            f'libro de clientes {mes}': {'alimentador': f.alimentador, 'sed': f.sed} if f else None}
        if seds_red is not None and sed:
            en_red = set(seds_red.get(sed, ()))
            fuentes['red'] = {'alimentador': en_red} if en_red else None
        v = veredicto(alimentador, sed, fuentes)
        if seds_red is not None and sed and not seds_red.get(sed):
            v['texto'] += f'; la SED {sed} no está en la red cargada'
        veredictos[codigo] = v
        por[alimentador].append(ClienteFijo(codigo, alimentador, sed, anteriores, f.cl if f else '',
                                            f.nombre if f else '', f.suministrador if f else ''))
    relevantes = set(candidatos) | {k for k, c in canon.items() if clave_cliente(c) in candidatos}
    fuera = sorted({f.codigo for _m, filas in maestros for f in filas.values()
                    if clave_cliente(actual_de(f.codigo)) not in todos})
    return ({a: sorted(lista, key=lambda c: c.codigo) for a, lista in por.items()},
            {'renumeraciones': renumeraciones, 'veredictos': veredictos, 'avisos': avisos,
             'propuestas': posibles_renumeraciones(presencia, relevantes), 'sin_suministro': fuera})


def _recortar(curva, desde: str, hasta: str) -> Serie:
    """Los registros del rango: después de las 00:00 del primer día y hasta las 00:00 del mes siguiente."""
    t = np.asarray(curva.t, dtype='datetime64[m]')
    p = np.asarray(curva.columnas[0], dtype=float)
    q = np.asarray(curva.columnas[1], dtype=float) if len(curva.columnas) > 1 else np.full(len(t), np.nan)
    inicio = np.datetime64(desde, 'M').astype('datetime64[m]')
    fin = (np.datetime64(hasta, 'M') + 1).astype('datetime64[m]')
    sel = (t > inicio) & (t <= fin)
    return t[sel], p[sel], q[sel]


def _suma(series: Sequence[Serie]) -> Serie | None:
    """La suma de las curvas en cada instante con alguna medida (la máxima coincidente, 105:RF-11)."""
    if not series:
        return None
    t = np.unique(np.concatenate([s[0] for s in series]))
    p = np.zeros(len(t))
    q = np.zeros(len(t))
    for ts, ps, qs in series:
        i = np.searchsorted(t, ts)
        np.add.at(p, i, ps)
        np.add.at(q, i, np.nan_to_num(qs))
    return t, p, q


def _cabecera(fuentes: FuentesEvolucion, alimentadores: Sequence[str], desde: str, hasta: str,
              fijas: dict[str, Serie | None], avisos: list[dict], copiados: Iterable[str] = ()) -> dict[str, list[dict]]:
    """Máxima de cabecera de cada mes y la P de los fijos en su instante (105:RF-12)."""
    if not fuentes.medidores or not fuentes.cabecera:
        return {}
    try:
        puntos, _ap = equivalencias(fuentes.medidores)
    except (DemandaError, OSError, ValueError) as exc:
        avisos.append({'tipo': 'cabecera', 'texto': f'Sin la participación en la cabecera: {exc}'})
        return {}
    pedidos = {clave_cliente(a): a for a in alimentadores}
    pares = [(p.codigo, m) for p in puntos if p.clase == 'alimentador' and clave_cliente(p.codigo) in pedidos
             for m in p.medidores]
    sin_medidor = set(pedidos) - {clave_cliente(a) for a, _m in pares}
    for clave in sorted(sin_medidor):
        avisos.append({'tipo': 'cabecera', 'texto': f'{pedidos[clave]}: no está en el libro de medidores; '
                                                   'sin su participación en la cabecera.'})
    if not pares:
        return {}
    leidas, apartados = curvas_de_cabecera(list(fuentes.cabecera), pares)
    for a in apartados:
        avisos.append({'tipo': 'cabecera', 'texto': f"{a['objetivo']}: {a['motivo']}"})
    salida: dict[str, list[dict]] = {}
    for codigo, d in leidas.items():
        alimentador = pedidos[clave_cliente(codigo)]
        t = np.array([x[0] for x in d['curva']], dtype='datetime64[m]')
        p = np.array([x[1] for x in d['curva']], dtype=float)
        sentido = sentido_de_serie(p)
        if sentido == 'ambos':
            # 089:RF-20: NA205 (2026) va de +8 MW a −8 MW: con una central o una transferencia la cabecera no es la
            # demanda, y la comparación con los fijos daba 20 754 registros «por encima».
            avisos.append({'tipo': 'cabecera', 'texto': f'{alimentador}: su cabecera mide en los dos sentidos (central, '
                                                       'generación o transferencia): sin participación ni comprobación '
                                                       'con los fijos.'})
            continue
        if sentido == 'invertido':
            # 089:RF-18: un medidor instalado al revés mide la demanda en negativo.
            p = -p
        inicio = np.datetime64(desde, 'M').astype('datetime64[m]')
        fin = (np.datetime64(hasta, 'M') + 1).astype('datetime64[m]')
        sel = (t > inicio) & (t <= fin)
        t, p = t[sel], p[sel]
        suma = fijas.get(alimentador)
        if suma is not None:
            # Un mes copiado no es medición de los fijos: AL209, abril de 2026, daba 2 397 kW «de fijos» (los de marzo)
            # frente a 214 kW de cabecera medidos ese día.
            medido = ~np.isin(mes_de_registro(suma[0]).astype(str), list(copiados))
            sobre = fijos_sobre_cabecera(suma[0][medido], suma[1][medido], t, p, MARGEN_CABECERA)
            if sobre:
                avisos.append({'tipo': 'fijos_sobre_cabecera', 'texto': (
                    f"{alimentador}: la suma de los fijos supera la cabecera más un {MARGEN_CABECERA:.0%} en "
                    f"{sobre['registros']} registro(s); el mayor, {em.iso_minuto(sobre['instante'])}: "
                    f"{sobre['fijos_kw']:.1f} kW de fijos con {sobre['cabecera_kw']:.1f} kW de cabecera; por mes: "
                    + ', '.join(f'{m}: {k}' for m, k in sobre['por_mes'].items())
                    + '. Revise la asignación de clientes, el medidor o un corte de la cabecera.')})
        meses = mes_de_registro(t)
        filas = []
        for m in np.unique(meses):
            idx = np.flatnonzero(meses == m)
            i = idx[int(np.nanargmax(p[idx]))]
            fijo = None
            copia = str(m) in set(copiados)
            if suma is not None and not copia:       # los fijos de un mes copiado son los del mes anterior
                j = np.searchsorted(suma[0], t[i])
                if j < len(suma[0]) and suma[0][j] == t[i]:
                    fijo = float(suma[1][j])
            maxima = float(p[i])
            filas.append({'mes': str(m), 'p_max': maxima, 'fecha': em.iso_minuto(t[i]), 'fijas_kw': fijo,
                          'participacion': fijo / maxima * 100 if fijo is not None and maxima else None,
                          'copia_de': str(m - 1) if copia else None})
        salida[alimentador] = filas
    return salida


def calcular_evolucion(fuentes: FuentesEvolucion, alimentadores: Sequence[str], desde: str, hasta: str, *,
                       avance: Callable[[int, int, str], None] | None = None) -> Evolucion:
    """Indicadores por cliente y mes, por alimentador y su calidad (105:RF-1 a RF-16)."""
    rango = meses_del_rango(desde, hasta)
    avisos: list[dict] = []
    catalogo, sin_uso = libros_con_mes(fuentes.clientes, fuentes.patron, fuentes.asignaciones)
    libros = sorted(((p, m) for p, m in catalogo if m in set(rango)), key=lambda x: (x[1], x[0].name))
    avisos += [{'tipo': 'lectura', 'texto': f'{n}: sin mes; no se usa en el rango.'}
               for n in (p.name for p, m in catalogo if m is None)]
    maestros = [(m, leer_maestro(p)) for p, m in libros]
    fijos, conc = clientes_fijos(fuentes.suministros, alimentadores, maestros, fuentes.seds_red)
    renumeraciones = conc['renumeraciones']
    avisos += [{'tipo': 'lectura', 'texto': a} for a in conc['avisos']]
    for alimentador, lista in fijos.items():
        if not lista:
            avisos.append({'tipo': 'sin_clientes', 'texto': f'{alimentador}: ni el libro de suministros '
                                                          f'{fuentes.suministros.name} ni los libros de clientes lo dan '
                                                          'como alimentador de ningún cliente.'})
    for codigo, v in conc['veredictos'].items():
        if v['estado'] == 'discrepa':
            avisos.append({'tipo': 'discrepancia', 'texto': f"{codigo}: {v['texto']}"})
    for x in conc['propuestas']:
        avisos.append({'tipo': 'posible_renumeracion', 'texto': f"{x['desaparece']} deja de estar en {x['mes']} y aparece "
                       f"{x['aparece']} con el mismo {x['por']} ({x['valor']}): ¿renumeración? No se aplica sin el libro "
                       'de suministros.'})
    canon = {}
    for lista in fijos.values():
        for c in lista:
            for codigo in (c.codigo, *c.anteriores):
                canon[clave_cliente(codigo)] = c.codigo
    avisos += [{'tipo': 'lectura', 'texto': t} for t in sin_uso]
    sin_libro = [m for m in rango if m not in {x for _p, x in libros}]
    if sin_libro:
        avisos.append({'tipo': 'sin_libro', 'texto': 'Sin libro de clientes: ' + ', '.join(sin_libro) + '.'})
    codigos = sorted(set(canon) | set(canon.values()))
    por, de_libro, contradictorios, avisos_lectura, _ap = curvas_por_cliente(
        libros, codigos, canonico=lambda c: canon.get(clave_cliente(c), c), avance=avance,
        apartar_copias=False) if codigos and libros \
        else ({}, {}, {}, {}, [])
    for codigo, texto in contradictorios.items():
        avisos.append({'tipo': 'contradiccion', 'texto': f'{codigo}: {texto}; se conserva el primero.'})
    for clave, notas in avisos_lectura.items():
        actual = canon.get(clave_cliente(clave))
        if actual is not None:
            quien = clave if clave_cliente(clave) == clave_cliente(actual) else f'{clave} (hoy {actual})'
            avisos.append({'tipo': 'lectura', 'texto': f'{quien}: ' + ' '.join(n.split(':', 1)[-1].strip() for n in notas)})

    series: dict[str, Serie] = {}
    for lista in fijos.values():
        for c in lista:
            curva = por.get(c.codigo)
            serie = _recortar(curva, desde, hasta) if curva is not None else None
            if serie is None or not len(serie[0]):
                avisos.append({'tipo': 'sin_medicion', 'texto': f'{c.codigo} ({c.alimentador}, {c.sed}): sin registros '
                                                               f'de {desde} a {hasta} en los libros de clientes.'})
                continue
            series[c.codigo] = serie
    copias = meses_copiados(series, rango)
    for m, cp in copias.items():
        avisos.append({'tipo': 'copia', 'texto': f'{m}: el libro repite los valores de {cp.de} (mismo día y hora) en '
                                                 f'{len(cp.series)} de {cp.comparables} clientes; queda fuera del '
                                                 'crecimiento, la variación y la tendencia.'})

    clientes, totales, sumas = [], [], {}
    for alimentador, lista in fijos.items():
        de_alim = []
        for c in lista:
            if c.codigo not in series:
                continue
            meses = em.indicadores_por_mes(*series[c.codigo])
            for m, d in meses.items():
                d['copia_de'] = copias[m].de if m in copias else None
                if not d['completo'] and m not in copias:
                    avisos.append({'tipo': 'incompleto', 'texto': f"{c.codigo} {m}: {d['registros']} de "
                                                                  f"{d['esperados']} registros."})
            de_alim.append(meses)
            clientes.append({'codigo': c.codigo, 'alimentador': alimentador, 'sed': c.sed,
                             'cl': c.cl, 'nombre': c.nombre, 'suministrador': c.suministrador,
                             'veredicto': conc['veredictos'][c.codigo],
                             'anteriores': list(c.anteriores), 'libros': de_libro.get(c.codigo, []),
                             'meses': list(meses.values()), 'resumen': em.resumen(meses, list(copias))})
        suma = _suma([series[c.codigo] for c in lista if c.codigo in series])
        sumas[alimentador] = suma
        if suma is None:
            continue                     # sin clientes con medición ya se dijo (RF-15): no hay total
        meses_t = em.suma_por_mes(de_alim)
        coincidente = em.indicadores_por_mes(*suma) if suma is not None else {}
        for m, d in meses_t.items():
            d['p_max_coincidente'] = coincidente.get(m, {}).get('p_max')
            d['fecha_coincidente'] = coincidente.get(m, {}).get('fecha_p_max')
            d['copia_de'] = copias[m].de if m in copias else None
        sin_copias = {m: d for m, d in meses_t.items() if m not in copias}
        # La P máxima del alimentador es la de la suma de sus fijos en un mismo instante, no la suma de sus máximas.
        pico = max((d for d in sin_copias.values() if d.get('p_max_coincidente') is not None),
                   key=lambda d: d['p_max_coincidente'], default=None)
        totales.append({'alimentador': alimentador, 'clientes': sum(1 for c in lista if c.codigo in series),
                        'meses': list(meses_t.values()), 'resumen': {
                            'p_max': pico['p_max_coincidente'] if pico else None,
                            'fecha_p_max': pico['fecha_coincidente'] if pico else None,
                            'crecimiento': {k: em.crecimiento({m: d.get(k) for m, d in sin_copias.items()})
                                            for k in ('p_max', 'energia_p', 'q_max', 'p_max_coincidente')},
                            'tendencia': {k: em.tendencia({m: d.get(k) for m, d in sin_copias.items()})
                                          for k in ('p_max', 'energia_p', 'q_max', 'p_max_coincidente')},
                            'variacion': {k: em.variaciones({m: d.get(k) for m, d in sin_copias.items()})
                                          for k in ('p_max', 'energia_p')},
                            'mes_mayor': {k: em.mes_mayor({m: d.get(k) for m, d in sin_copias.items()})
                                          for k in em.MAGNITUDES},
                        }})
    cabecera = _cabecera(fuentes, list(fijos), desde, hasta, sumas, avisos, copias)
    for t in totales:
        t['cabecera'] = cabecera.get(t['alimentador'])
    fuera = conc['sin_suministro']
    if fuera:
        avisos.append({'tipo': 'sin_suministro', 'texto': f'{len(fuera)} cliente(s) de los libros no están en el libro de '
                       f'suministros y no se sabe su alimentador: ' + ', '.join(fuera[:10]) + (' …' if len(fuera) > 10 else '')})
    meses_con_datos = sorted({d['mes'] for c in clientes for d in c['meses']})
    datos = {
        'alimentadores': list(fijos), 'desde': desde, 'hasta': hasta, 'meses': meses_con_datos,
        'libros': [{'libro': p.name, 'mes': m} for p, m in libros],
        'suministros': fuentes.suministros.name, 'renumeraciones': renumeraciones,
        'propuestas': conc['propuestas'],
        'conciliacion': {e: sum(1 for c in clientes if c['veredicto']['estado'] == e)
                         for e in ('confirmado', 'discrepa', 'una_fuente')},
        'red': fuentes.seds_red is not None,
        'copias': [{'mes': c.mes, 'de': c.de, 'clientes': list(c.series), 'comparables': c.comparables}
                   for c in copias.values()],
        'clientes': clientes, 'totales': totales, 'avisos': avisos,
    }
    return Evolucion(datos, series)


# --------------------------------------------------------------------------- libro Excel (105:RF-27)
def _evolucion(datos: dict, clave: str, excluidos: set[str]) -> 'Any':
    import pandas as pd

    meses = [m for m in datos['meses'] if m not in excluidos]
    filas = []
    for c in datos['clientes']:
        v = {d['mes']: d.get(clave) for d in c['meses']}
        crec = c['resumen']['crecimiento'][clave]
        filas.append({'Cliente': c['codigo'], **{m: v.get(m) for m in meses},
                      'Crecimiento (%)': crec['pct'], 'Desde→hasta': f"{crec['desde']}→{crec['hasta']}" if crec['pct'] is not None else '',
                      'Tendencia mensual (%)': c['resumen']['tendencia'][clave]})
    for t in datos['totales']:
        v = {d['mes']: d.get(clave) for d in t['meses']}
        crec = t['resumen']['crecimiento'][clave]
        filas.append({'Cliente': f"TOTAL {t['alimentador']} (suma)", **{m: v.get(m) for m in meses},
                      'Crecimiento (%)': crec['pct'], 'Desde→hasta': f"{crec['desde']}→{crec['hasta']}" if crec['pct'] is not None else '',
                      'Tendencia mensual (%)': t['resumen']['tendencia'][clave]})
    return pd.DataFrame(filas, columns=['Cliente', *meses, 'Crecimiento (%)', 'Desde→hasta', 'Tendencia mensual (%)'])


def _fecha(texto: str | None):
    from datetime import datetime
    return datetime.fromisoformat(texto) if texto else None


def escribir_libro(evolucion: Evolucion, destino: Path) -> Path:
    """El libro de la evolución, como el de AL209 hecho a mano, con sus gráficos (105:RF-27)."""
    import pandas as pd
    from openpyxl.chart import LineChart, Reference
    from openpyxl.chart.series import SeriesLabel
    from openpyxl.utils import get_column_letter

    datos = evolucion.datos
    copias = {c['mes']: c['de'] for c in datos['copias']}
    sed = {c['codigo']: c['sed'] for c in datos['clientes']}
    alim = {c['codigo']: c['alimentador'] for c in datos['clientes']}
    resumen = pd.DataFrame([{
        'Cliente': c['codigo'], 'SED': c['sed'], 'Mes': d['mes'], 'P máx (kW)': d['p_max'],
        'Fecha P máx': _fecha(d['fecha_p_max']), 'Q en la P máx (kVAR)': d['q_en_p_max'], 'P media (kW)': d['p_media'],
        'Q máx (kVAR)': d['q_max'], 'Fecha Q máx': _fecha(d['fecha_q_max']), 'Q media (kVAR)': d['q_media'],
        'Energía activa (MWh)': d['energia_p'], 'Energía reactiva (MVARh)': d['energia_q'], 'FP medio': d['fp'],
        'Factor de carga': d['factor_carga'], 'Registros': d['registros'], 'Esperados': d['esperados'],
        'Completo': 'sí' if d['completo'] else 'NO',
        'Observación': f"COPIA de {d['copia_de']}: el libro repite sus valores; no se usa" if d['copia_de'] else '',
        'Alimentador': c['alimentador'],
    } for c in datos['clientes'] for d in c['meses']])
    variacion = pd.DataFrame([{
        'Cliente': c['codigo'], 'Magnitud': nombre,
        **{m: (c['resumen']['variacion'][k].get(m) or {}).get('pct') for m in datos['meses'] if m not in copias},
    } for c in datos['clientes'] for k, nombre in (('p_max', 'P máx'), ('energia_p', 'Energía activa'))])
    cabecera = pd.DataFrame([{'Alimentador': t['alimentador'], 'Mes': f['mes'], 'Máxima de cabecera (kW)': f['p_max'],
                              'Instante': _fecha(f['fecha']), 'Fijos en ese instante (kW)': f['fijas_kw'],
                              'Participación de los fijos (%)': f['participacion']}
                             for t in datos['totales'] for f in (t.get('cabecera') or [])])
    renumerados = '; '.join(f"{r['anterior']} → {r['actual']}" for r in datos['renumeraciones']) or 'ninguno'
    entran = [f"{c['codigo']} entra en {c['meses'][0]['mes']}" for c in datos['clientes']
              if c['meses'] and c['meses'][0]['mes'] != datos['meses'][0]]
    notas = pd.DataFrame({'Nota': [
        f"Clientes fijos de {', '.join(datos['alimentadores'])} según el libro de suministros {datos['suministros']} "
        '(columna radial).',
        f'Renumerados: {renumerados}. Sus meses se unen bajo el código actual.',
        'Libros: ' + ', '.join(x['libro'] for x in datos['libros']) + '.',
        'P (kW) = EA × 4 y Q (kVAR) = ERI × 4 de cada registro de 15 minutos, como en la calibración. El registro de las '
        '00:00 del día 1 cierra el mes anterior.',
        'Energía = suma de la potencia de 15 minutos / 4. FP medio = energía activa / aparente del mes. Factor de carga = '
        'P media / P máx.',
        'Crecimiento: del primer al último mes con datos del cliente (columna Desde→hasta). Tendencia mensual: pendiente de '
        'la recta sobre los meses con datos, en % de la media del cliente por mes. El total suma solo los clientes de cada '
        'mes' + (': ' + '; '.join(entran) if entran else '') + '.',
        *[f"{a['tipo']}: {a['texto']}" for a in datos['avisos']],
        ('LIBRO DUDOSO: ' + '; '.join(f"{c['mes']}: repite los valores de {c['de']} (mismo día y hora) en "
                                      f"{len(c['clientes'])} de {c['comparables']} clientes; se deja en «Resumen "
                                      'mensual» marcado y fuera de las hojas de evolución y del crecimiento'
                                      for c in datos['copias'])) if datos['copias'] else 'Ningún mes repite al anterior.',
        'Datos de la distribuidora: uso interno.']})

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f'.tmp-{destino.name}')
    hojas_evolucion = (('Evolución P máx (kW)', 'p_max', 'P máxima mensual por cliente fijo', 'kW'),
                       ('Evolución energía (MWh)', 'energia_p', 'Energía activa mensual por cliente fijo', 'MWh'),
                       ('Evolución Q máx (kVAR)', 'q_max', 'Q máxima mensual por cliente fijo', 'kVAR'))
    usadas: set[str] = set()
    with pd.ExcelWriter(temporal, engine='openpyxl') as xl:
        for hoja, clave, _t, _e in hojas_evolucion:
            _evolucion(datos, clave, set(copias)).to_excel(xl, sheet_name=hoja, index=False)
        resumen.to_excel(xl, sheet_name='Resumen mensual', index=False)
        variacion.to_excel(xl, sheet_name='Variación mes a mes (%)', index=False)
        if not cabecera.empty:
            cabecera.to_excel(xl, sheet_name='Cabecera y fijos', index=False)
        for codigo, (t, p, q) in evolucion.series.items():
            nombre = f'{codigo} ({sed.get(codigo)})'[:31]
            n = 2
            while nombre in usadas:
                nombre = f'{codigo} {alim.get(codigo)} {n}'[:31]
                n += 1
            usadas.add(nombre)
            pd.DataFrame({'Fecha': t.astype('datetime64[ns]'), 'P (kW)': p, 'Q (kVAR)': q}).to_excel(
                xl, sheet_name=nombre, index=False)
        notas.to_excel(xl, sheet_name='Notas', index=False)
        # Formato y gráficos sobre el libro que se está escribiendo: volver a abrirlo para darle formato costaba más que
        # escribirlo (AL209 y NA205, 22 hojas de 29 185 registros: más de 5 minutos).
        wb = xl.book
        for ws in wb.worksheets:
            ws.freeze_panes = 'B2'
            for i, col in enumerate(ws.iter_cols(min_row=1, max_row=min(ws.max_row, 50)), start=1):
                largo = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[get_column_letter(i)].width = min(max(10, largo + 2), 45)
            for fila in ws.iter_rows(min_row=2):
                for c in fila:
                    if isinstance(c.value, float):
                        c.number_format = '0.00'
                    elif hasattr(c.value, 'year'):
                        c.number_format = 'yyyy-mm-dd hh:mm'
        for hoja, _clave, titulo, eje in hojas_evolucion:
            ws = wb[hoja]
            n_meses = sum(1 for c in ws[1] if str(c.value)[:4].isdigit())
            filas = [r for r in range(2, ws.max_row + 1) if not str(ws.cell(r, 1).value).startswith('TOTAL ')]
            if not n_meses or not filas:
                continue
            ch = LineChart()
            ch.title, ch.y_axis.title, ch.x_axis.title, ch.height, ch.width = (
                f"{titulo} — {', '.join(datos['alimentadores'])}", eje, 'Mes', 9, 22)
            for r in filas:
                ch.add_data(Reference(ws, min_col=2, max_col=1 + n_meses, min_row=r), from_rows=True, titles_from_data=False)
                ch.series[-1].tx = SeriesLabel(v=str(ws.cell(r, 1).value))
            ch.set_categories(Reference(ws, min_col=2, max_col=1 + n_meses, min_row=1))
            ws.add_chart(ch, f'A{ws.max_row + 3}')
    temporal.replace(destino)
    return destino
