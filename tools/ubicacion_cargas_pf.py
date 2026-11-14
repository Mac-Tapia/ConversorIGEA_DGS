#!/usr/bin/env python
"""Lee en DIgSILENT, sin escribir nada, dónde está conectada hoy cada carga nueva (017:RF-124).

Usuario, 2026-11-13: «debe haber un botón para actualizar la imagen de la ubicación y el punto de fijación de
diseño cuando el usuario verificó en DIgSILENT, corrigió o asignó otro punto». La web guarda la barra en que
``cargas_pf.py`` conectó cada carga (``cargas_pf_aplicacion_*.json``); si después el operador mueve en DIgSILENT
la línea de enlace ``LNE_<SED>`` a otro nodo, o la SED a otro punto, la imagen y el informe seguían con la barra
de entonces. Este guion solo lee: activa «Con proyecto» (donde están activas las variaciones de las cargas), recorre
desde cada carga hacia la red hasta el primer nodo que no es de la propia carga y deja el caso activo como estaba.
Los cambios del operador son intencionales: se leen, nunca se deshacen (memoria del proyecto, cambios manuales).

    python tools/ubicacion_cargas_pf.py --plan plan.json --output-json ubicacion.json

El plan: ``project``, ``folder``, ``feeders``, ``anio_casos`` (opcional) y ``cargas``, las que guardó la web, cada una
con ``sed``, ``alimentador`` y ``variacion``. También se leen las variaciones ``Carga_…`` activas que la web no tiene.

Códigos de salida: 0 bien, 1 error inesperado, 2 proyecto que no existe, 3 API de PowerFactory no disponible.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / 'src'), str(RAIZ / 'tools')]

#: Lados de los elementos de rama por los que se sube de la carga a la red.
LADOS = ('bus1', 'bus2', 'bushv', 'buslv', 'busmv')
#: Clases por las que se sube: transformador de la SED, seccionador, línea de enlace.
RAMAS = frozenset({'ElmTr2', 'ElmTr3', 'ElmCoup', 'ElmLne', 'ElmZpu', 'ElmBreaker'})
#: Pasos como mucho de la carga al nodo de la red: carga → BT → trafo → MT → seccionador → nodo propio → enlace.
#: Con más, no es la estructura que crea ``cargas_pf.py`` y se dice en vez de adivinar.
MAX_PASOS = 8
#: El «(1)» o «(2)» que DIgSILENT añade a un nombre repetido en su carpeta.
_COPIA = re.compile(r'\(\d+\)$')


def sin_copia(nombre: str) -> str:
    """El nombre sin el «(n)» de DIgSILENT.

    CA101, 2026-11-13: la carga de SECA0001 se llama «SECA0001(1)» en la red y «SECA0001(2)» en su etapa, porque
    la barra de media de la SED ya se llama «SECA0001» en la misma SED; buscarla por su nombre no la encontraba.
    """
    return _COPIA.sub('', nombre)


class Cubiculos:
    """Barras de cada elemento por sus cubículos, para los objetos sin ``bus1``…

    El doble de las pruebas, y algún elemento antiguo, solo tienen el cubículo en la barra. Se arma una vez y solo si
    hace falta: recorrer todas las barras por carga sería O(cargas · barras).
    """

    def __init__(self, app):
        self.app = app
        self._de: dict[str, list] | None = None

    def barras(self, obj) -> list:
        from cargas_pf import clave_pf

        if self._de is None:
            self._de = {}
            for t in self.app.GetCalcRelevantObjects('*.ElmTerm') or []:
                for cub in t.GetContents('*.StaCubic') or []:
                    o = getattr(cub, 'obj_id', None)
                    if o is not None:
                        self._de.setdefault(clave_pf(o), []).append(t)
        return self._de.get(clave_pf(obj), [])


def extremos(obj, cubiculos: Cubiculos) -> list:
    """Las barras de un elemento: por sus lados (la API), o por los cubículos (el doble y los antiguos)."""
    out = []
    for lado in LADOS:
        barra = getattr(getattr(obj, lado, None), 'cterm', None)
        if barra is not None:
            out.append(barra)
    return out or cubiculos.barras(obj)


def _gps_lista(obj) -> list[list[float]]:
    """El trazado ``GPScoords`` de una línea, si lo tiene."""
    try:
        valor = obj.GetAttribute('GPScoords')
    except Exception:  # noqa: BLE001 - una línea sin trazado no lo tiene
        valor = getattr(obj, 'GPScoords', None)
    out = []
    for p in valor or []:
        try:
            lat, lon = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (lat == 0 and lon == 0):
            out.append([lat, lon])
    return out


def conexion_de(carga, sed: str, cubiculos: Cubiculos) -> dict:
    """Desde la carga hacia la red, el primer nodo que no es de la propia carga, y la línea por la que se llega.

    «De la carga» son las barras de su SED (``ElmSubstat``) y su nodo ``NODE_<SED>``: lo que crea ``cargas_pf.py``.
    Si el operador colgó la carga de otra barra, esa barra es el nodo; si movió el enlace, el nodo es el del otro
    extremo de la línea, sea cual sea su nombre.
    """
    from cargas_pf import _num, clave_pf, gps_de, nombre_pf

    sub = carga.GetParent()
    clave_sub = clave_pf(sub) if sub is not None and sub.GetClassName() == 'ElmSubstat' else None
    nodo_propio = nombre_pf(f'NODE_{sed}')

    def propia(barra) -> bool:
        padre = barra.GetParent()
        return (clave_sub is not None and padre is not None and clave_pf(padre) == clave_sub) \
            or barra.loc_name == nodo_propio

    inicio = extremos(carga, cubiculos)
    if not inicio:
        return {'error': 'la carga no está conectada a ninguna barra'}
    pendientes = [(inicio[0], [], 0)]
    vistas = {clave_pf(inicio[0])}
    if not propia(inicio[0]):
        pendientes = []
        hallado = (inicio[0], [])
    else:
        hallado = None
    while pendientes and hallado is None:
        barra, camino, pasos = pendientes.pop(0)
        if pasos >= MAX_PASOS:
            continue
        for cub in barra.GetContents('*.StaCubic') or []:
            elem = getattr(cub, 'obj_id', None)
            if elem is None or elem.GetClassName() not in RAMAS:
                continue
            for otra in extremos(elem, cubiculos):
                k = clave_pf(otra)
                if k in vistas:
                    continue
                vistas.add(k)
                siguiente = camino + [elem] if elem.GetClassName() == 'ElmLne' else camino
                if not propia(otra):
                    hallado = (otra, siguiente)
                    break
                pendientes.append((otra, siguiente, pasos + 1))
            if hallado is not None:
                break
    if hallado is None:
        return {'error': f'no se llega desde {sed} a ninguna barra de la red en {MAX_PASOS} pasos'}
    nodo, lineas = hallado
    gps = gps_de(nodo)
    out = {'nodo': {'nombre': nodo.loc_name, 'gps': list(gps) if gps else None, 'kv': _num(nodo, 'uknom')},
           'enlace': None}
    if lineas:
        ln = lineas[-1]
        km = sum(_num(x, 'dline') or 0.0 for x in lineas)
        out['enlace'] = {'nombre': ln.loc_name, 'km': round(km, 6), 'gps': _gps_lista(ln),
                         'tramos': [x.loc_name for x in lineas]}
    return out


def _punto_de_la_carga(carga, sed: str, app):
    """El punto de la carga: el GPS de su ``ElmLod``, de su SED o de su ``NODE_<SED>``, el primero que lo tenga."""
    from cargas_pf import gps_de, nombre_pf

    for obj in (carga, carga.GetParent()):
        gps = gps_de(obj) if obj is not None else None
        if gps is not None:
            return list(gps)
    nodo = nombre_pf(f'NODE_{sed}')
    for t in app.GetCalcRelevantObjects('*.ElmTerm') or []:
        if t.loc_name == nodo and gps_de(t) is not None:
            return list(gps_de(t))
    return None


def _de_variaciones(app, feeders: list[str]) -> dict[str, dict]:
    """Las cargas nuevas de las variaciones ``Carga_…`` activas, por variación: lo que hay hoy en DIgSILENT."""
    from casos_pf import _de_alimentador, es_de_carga_nueva, objetos_de_variacion

    out = {}
    for v in app.GetActiveNetworkVariations() or []:
        if not es_de_carga_nueva(v):
            continue
        objetos = objetos_de_variacion(v)
        # La SED da el nombre: la carga puede llevar el «(n)» de DIgSILENT (CA101, 2026-11-13).
        cargas = sorted({nombre for clase, nombre in objetos if clase == 'ElmSubstat'}) or sorted(
            {sin_copia(nombre) for clase, nombre in objetos if clase == 'ElmLod'})
        out[v.loc_name] = {'variacion': v.loc_name, 'cargas': cargas,
                           'alimentador': _de_alimentador(v.loc_name, 'Carga_', feeders)}
    return out


def leer_cargas(app, plan: dict, informe: dict) -> None:
    """Cada carga del plan y cada una de las variaciones activas que la web no tiene, con su conexión de hoy."""
    from cargas_pf import _num, nombre_pf

    feeders = [str(f) for f in plan.get('feeders') or []]
    activas = _de_variaciones(app, feeders)
    por_nombre: dict[str, list] = {}
    for c in app.GetCalcRelevantObjects('*.ElmLod') or []:
        padre = c.GetParent()
        claves = {sin_copia(c.loc_name)}
        if padre is not None and padre.GetClassName() == 'ElmSubstat':
            claves.add(padre.loc_name)
        for k in claves:
            por_nombre.setdefault(k, []).append(c)
    cubiculos = Cubiculos(app)
    pedidas = [dict(c) for c in plan.get('cargas') or []]
    conocidas = {str(c.get('variacion') or '') for c in pedidas}
    for v, datos in sorted(activas.items()):
        if v in conocidas:
            continue
        for nombre in datos['cargas']:
            pedidas.append({'sed': nombre, 'alimentador': datos['alimentador'], 'variacion': v,
                            'solo_en_digsilent': True})
    for c in pedidas:
        sed = str(c.get('sed') or '')
        fila = {'sed': sed, 'alimentador': c.get('alimentador'), 'variacion': c.get('variacion'),
                'solo_en_digsilent': bool(c.get('solo_en_digsilent')),
                'variacion_activa': str(c.get('variacion') or '') in activas}
        candidatas = por_nombre.get(nombre_pf(sed)) or []
        if not candidatas:
            fila['error'] = (f'{sed} no está en la red del caso leído'
                             + ('' if fila['variacion_activa'] else
                                f' (su variación {c.get("variacion")} no está activa)'))
            informe['cargas'].append(fila)
            continue
        # La de su SED primero: una carga existente puede llamarse como la SED nueva.
        propias = [x for x in candidatas if getattr(x.GetParent(), 'loc_name', None) == nombre_pf(sed)]
        if len(propias or candidatas) > 1:
            informe['avisos'].append(f'{sed}: {len(propias or candidatas)} cargas con ese nombre; se lee la primera')
        carga = (propias or candidatas)[0]
        try:
            fila['punto'] = _punto_de_la_carga(carga, sed, app)
            p, q = _num(carga, 'plini'), _num(carga, 'qlini')
            fila['kw'] = None if p is None else round(p * 1000.0, 3)
            fila['kvar'] = None if q is None else round(q * 1000.0, 3)
            fila.update(conexion_de(carga, sed, cubiculos))
        except Exception as exc:  # noqa: BLE001 - una carga no tumba la lectura de las demás
            fila['error'] = f'{type(exc).__name__}: {exc}'
        informe['cargas'].append(fila)


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """La lectura del plan. Devuelve (informe, código)."""
    from casos_pf import anio_del_plan
    from casos_pf import caso as caso_del_sistema
    from cargas_pf import activar_proyecto

    from convertersmartgrid.pf_arnes import caso_restituido

    informe = {'project': plan.get('project'), 'caso': None, 'cargas': [], 'avisos': [], 'solo_lectura': True}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    with caso_restituido(app):
        caso = caso_del_sistema(app, 'con', anio_del_plan(plan))
        if caso is None:
            informe['avisos'].append('el proyecto no tiene «Con proyecto»: se lee el caso activo')
            actual = app.GetActiveStudyCase()
            informe['caso'] = getattr(actual, 'loc_name', None)
        else:
            caso.Activate()
            informe['caso'] = caso.loc_name
        leer_cargas(app, plan, informe)
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Lectura, sin escribir, de dónde está conectada hoy en DIgSILENT cada '
                                            'carga nueva: su nodo de media, la línea de enlace y su GPS (017:RF-124)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('ubicacion_cargas_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for c in informe.get('cargas') or []:
        if c.get('error'):
            print(f"  {c['sed']}: {c['error']}", flush=True)
        else:
            enlace = (c.get('enlace') or {}).get('nombre') or 'sin línea de enlace'
            print(f"  {c['sed']} ({c.get('alimentador')}): nodo {c['nodo']['nombre']}, {enlace}", flush=True)
    print(f"Ubicación de las cargas nuevas de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
