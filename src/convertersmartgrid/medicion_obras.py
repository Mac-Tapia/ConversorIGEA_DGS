"""Cuánto mejora una versión: tiempo, recursos, soluciones, obras y normas de cada «Con proyecto» (spec 087, RF-21 a RF-27).

Pisco (2026-11-02 a 04) tardó dos días y dos noches y no había forma de demostrar qué cambio ayudaba. Cada corrida deja aquí
una fila con lo que costó y lo que dio; comparar dos métodos o dos versiones del mismo sistema sale de esas filas. Lo que no se midió
se dice como «sin dato», en vez de contar como cumplido. Puro, salvo leer y añadir su fichero.
"""
from __future__ import annotations

import json
import re
import statistics as st
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REGISTRO = 'corridas_obras.jsonl'
#: Con menos corridas por grupo no se declara ninguna mejora (087:RF-26).
MINIMO_CORRIDAS = 5
NORMAS = ('tension', 'carga', 'seccion_normalizada', 'valle', 'ternas', 'set_area_libre', 'coordenadas')
MEDIDAS = ('tiempo_s', 'oraculo_s', 'digsilent_s', 'flujos_oraculo', 'ordenes', 'ordenes_fallidas', 'memoria_mb', 'resueltos', 'sin_resolver',
           'obras', 'km', 'inversion', 'costo_anual', 'perdidas_kw', 'u_min', 'carga_max_pct')
_KM = re.compile(r'\(([\d.]+) km\)')
_SECCION = re.compile(r'sección (\S+)')


def _elegidas(resultado: Mapping[str, Any]) -> list[dict[str, Any]]:
    """La fila de la tabla de cada obra elegida, de lo que devolvió la escalera."""
    escalera = ((resultado.get('escalera_por_cargas') or {}).get('escalera') or {})
    out = []
    for a in escalera.get('alimentadores') or []:
        fila = next((t for t in a.get('tabla') or [] if t.get('nombre') == a.get('elegida')), None)
        if fila is not None:
            out.append({**fila, 'alimentador': a.get('alimentador'), 'aplicada': list(a.get('aplicada') or []),
                        'coordenadas': a.get('coordenadas'), 'instalaciones': a.get('instalaciones')})
    return out


def _obras_por_clase(elegidas: Sequence[Mapping[str, Any]], set_nueva: Mapping[str, Any]) -> dict[str, int]:
    clases: dict[str, int] = {}
    for e in elegidas:
        for nombre in e['aplicada']:
            m = re.match(r'Obra_([a-z_]+?)_', str(nombre))
            clases[m.group(1) if m else 'otra'] = clases.get(m.group(1) if m else 'otra', 0) + 1
    for o in (set_nueva or {}).get('obras') or []:
        clase = str(o.get('clase') or 'otra')
        clases[clase] = clases.get(clase, 0) + 1
    return clases


def comprobar_normas(elegidas: Sequence[Mapping[str, Any]], set_nueva: Mapping[str, Any], *, tension_min: float, tension_max: float,
                     carga_max: float, secciones: Sequence[str] = ()) -> dict[str, dict[str, int]]:
    """087:RF-23, RF-24: por norma, cuántas obras la cumplen, cuántas no y de cuántas no hay dato."""
    cuenta = {n: {'cumplen': 0, 'no_cumplen': 0, 'sin_dato': 0} for n in NORMAS}

    def anota(norma: str, valor: bool | None) -> None:
        cuenta[norma]['sin_dato' if valor is None else 'cumplen' if valor else 'no_cumplen'] += 1

    for e in elegidas:
        u = e.get('u_min_mt')
        anota('tension', None if u is None else tension_min <= float(u) <= tension_max)
        c = e.get('carga_max_pct')
        anota('carga', None if c is None else float(c) <= carga_max)
        usadas = _SECCION.findall(str(e.get('nombre') or ''))
        if usadas:
            anota('seccion_normalizada', None if not secciones else all(any(s.upper().startswith(x.upper()) for x in secciones) for s in usadas))
        if 'kvar' in str(e.get('nombre') or ''):
            anota('valle', None if e.get('valle') is None else bool(e['valle']))
        if 'terna' in str(e.get('nombre') or ''):
            anota('ternas', None if not e.get('instalaciones') else not any(i.get('avisos') for i in e['instalaciones']))
        coordenadas = e.get('coordenadas')
        anota('coordenadas', None if coordenadas is None else bool(coordenadas) and all(u.get('puntos') for u in coordenadas))
    for z in (set_nueva or {}).get('zonas') or []:
        if z.get('solucion') == 'set_nueva':
            final = z.get('ubicacion_final') or {}
            anota('set_area_libre', None if 'cumple' not in final else bool(final['cumple']))
    return cuenta


def fila_de_corrida(*, sistema: str, revision: str, metodo: str, estado: str, resultado: Mapping[str, Any], tiempo_s: float,
                    fecha: str = '', oraculo: Mapping[str, Any] | None = None, ordenes: Sequence[Mapping[str, Any]] = (),
                    memoria_mb: float | None = None, tension_min: float = 0.95, tension_max: float = 1.05, carga_max: float = 100.0,
                    secciones: Sequence[str] = (), pruebas: Mapping[str, int] | None = None) -> dict[str, Any]:
    """087:RF-21, RF-22, RF-23: lo que costó y lo que dio una corrida; lo no medido queda en ``None``."""
    por = (resultado.get('escalera_por_cargas') or {}).get('por_alimentador') or {}
    set_nueva = resultado.get('set_nueva') or {}
    elegidas = _elegidas(resultado)

    def suma(clave: str) -> float | None:
        valores = [float(e[clave]) for e in elegidas if e.get(clave) is not None]
        return sum(valores) if valores else None

    us = [float(e['u_min_mt']) for e in elegidas if e.get('u_min_mt') is not None]
    cs = [float(e['carga_max_pct']) for e in elegidas if e.get('carga_max_pct') is not None]
    clases = _obras_por_clase(elegidas, set_nueva)
    return {'fecha': fecha, 'sistema': sistema, 'revision': revision, 'metodo': metodo, 'estado': estado, 'tiempo_s': round(float(tiempo_s), 1),
            'oraculo_s': (oraculo or {}).get('oraculo_s'), 'digsilent_s': round(sum(float(o.get('segundos') or 0) for o in ordenes), 1),
            'flujos_oraculo': (oraculo or {}).get('flujos'), 'ordenes': len(ordenes),
            'ordenes_fallidas': sum(1 for o in ordenes if int(o.get('codigo') or 0)), 'memoria_mb': memoria_mb,
            'resueltos': sum(1 for x in por.values() if x.get('cumple')), 'sin_resolver': sum(1 for x in por.values() if not x.get('cumple')),
            'obras': sum(clases.values()), 'obras_por_clase': clases,
            'km': round(sum(float(k) for e in elegidas for k in _KM.findall(str(e.get('nombre') or ''))), 2),
            'inversion': suma('inversion'), 'costo_anual': suma('costo_anual'), 'perdidas_kw': suma('perdidas_kw'),
            'u_min': min(us) if us else None, 'carga_max_pct': max(cs) if cs else None,
            'normas': comprobar_normas(elegidas, set_nueva, tension_min=tension_min, tension_max=tension_max, carga_max=carga_max, secciones=secciones),
            'pruebas': dict(pruebas) if pruebas else None}


def anadir(ruta: Path | str, fila: Mapping[str, Any]) -> None:
    """Medir no puede hacer fallar el trabajo que mide."""
    try:
        with open(ruta, 'a', encoding='utf-8') as f:
            f.write(json.dumps(fila, ensure_ascii=False, default=str) + '\n')
    except OSError:
        pass


def leer(ruta: Path | str) -> list[dict[str, Any]]:
    filas = []
    try:
        for ln in Path(ruta).read_text(encoding='utf-8').splitlines():
            try:
                filas.append(json.loads(ln))
            except ValueError:
                continue
    except OSError:
        pass
    return filas


def pruebas_de_junit(ruta: Path | str) -> dict[str, int]:
    """087:RF-27: aprobadas, fallidas y omitidas de un informe JUnit de pytest."""
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == 'testsuite' else list(raiz.iter('testsuite'))
    total = fallidas = omitidas = 0
    for s in suites:
        total += int(s.get('tests') or 0)
        fallidas += int(s.get('failures') or 0) + int(s.get('errors') or 0)
        omitidas += int(s.get('skipped') or 0)
    return {'aprobadas': total - fallidas - omitidas, 'fallidas': fallidas, 'omitidas': omitidas}


def _media(filas: Sequence[Mapping[str, Any]], clave: str) -> float | None:
    v = [float(f[clave]) for f in filas if f.get(clave) is not None]
    return st.mean(v) if v else None


def comparar(filas: Sequence[Mapping[str, Any]], sistema: str, campo: str, a: str, b: str, alfa: float = 0.05) -> dict[str, Any]:
    """087:RF-25, RF-26: B frente a A en un mismo sistema: la diferencia de cada medida y el contraste si hay corridas para ello."""
    from .estadistica_ordenes import contrastar

    del_sistema = [f for f in filas if f.get('sistema') == sistema and f.get('estado') not in ('cancelled', 'cancelado')]
    fa = [f for f in del_sistema if f.get(campo) == a]
    fb = [f for f in del_sistema if f.get(campo) == b]
    medidas = {}
    for m in MEDIDAS:
        x, y = _media(fa, m), _media(fb, m)
        medidas[m] = {'a': x, 'b': y, 'diferencia': None if x is None or y is None else y - x,
                      'porcentaje': None if not x or y is None else 100.0 * (y - x) / x}
    normas = {}
    for n in NORMAS:
        normas[n] = {g: {k: sum(int(((f.get('normas') or {}).get(n) or {}).get(k) or 0) for f in fs) for k in ('cumplen', 'no_cumplen', 'sin_dato')}
                     for g, fs in (('a', fa), ('b', fb))}
    salida: dict[str, Any] = {'sistema': sistema, 'campo': campo, 'a': a, 'b': b, 'corridas_a': len(fa), 'corridas_b': len(fb),
                              'medidas': medidas, 'normas': normas, 'minimo_corridas': MINIMO_CORRIDAS}
    if min(len(fa), len(fb)) < MINIMO_CORRIDAS:
        salida['contraste'] = None
        salida['motivo'] = f'hacen falta {MINIMO_CORRIDAS} corridas por grupo para contrastar: son diferencias observadas, no una mejora demostrada'
        return salida

    def por_orden(fs):
        return [{'segundos': 0.0, 'codigo': int(i < int(f.get('ordenes_fallidas') or 0))} for f in fs for i in range(int(f.get('ordenes') or 0))]

    tiempos = contrastar([{'segundos': f['tiempo_s'], 'codigo': 0} for f in fa], [{'segundos': f['tiempo_s'], 'codigo': 0} for f in fb], alfa)
    ordenes = contrastar(por_orden(fa), por_orden(fb), alfa)
    salida['contraste'] = {'tiempo': tiempos['duracion'], 'ordenes_fallidas': ordenes.get('fallos'), 'alfa': alfa}
    return salida
