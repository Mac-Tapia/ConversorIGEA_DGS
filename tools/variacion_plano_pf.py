#!/usr/bin/env python
"""Estudia en DIgSILENT una variación del plano de la red (spec 111), sin dejar nada en el proyecto.

La variación vive en el espacio de trabajo (``variacion_plano.py``); en DIgSILENT solo existe mientras dura el estudio
(111:RF-4, RF-10, RF-17; 011:RF-136; 086:RF-87). Lo que hace este guion, en orden:

1. Comprueba el contexto firmado del plan (el vínculo proyecto ↔ ejecución de la fuente, ``native_action``): sin él no
   abre DIgSILENT. La web elige DIgSILENT solo con licencia y con el proyecto vinculado; si no, usa el motor abierto.
2. Activa el proyecto, fotografía el estado activo y el del caso del operador (``pf_estado``).
3. Copia el caso del operador y activa la copia. Si la copia tiene un escenario de operación activo, lo copia también y
   activa la copia del escenario: una maniobra es dato de operación y caería en el escenario del operador.
4. Crea la variación temporal del conversor, con su marca, y aplica en ella las ediciones con los nombres de DIgSILENT
   que manda la web (``resultados_plano.plan_pf``): maniobras (``on_off``), tramos nuevos (``ElmLne`` con sus
   vértices y su longitud, y la barra nueva del extremo si hace falta) y equipos insertados (``StaSwitch`` en el
   cubículo del tramo). Si una edición no encuentra su objeto, no corre el flujo.
5. Corre ``ComLdf`` y lee la red con sus resultados (``estudios_pf.geografia``).
6. Siempre, también si revienta: borra la variación temporal, la copia del escenario y la copia del caso, devuelve el
   caso del operador y comprueba con la foto que quedó como estaba; si no, falla y lo dice.

    python tools/variacion_plano_pf.py --plan plan.json --output-json informe.json

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin la API de DIgSILENT.
"""
from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, crear_variacion, flujo_de_carga
from casos_pf import _desc
from estudios_pf import _salida, caso_por_nombre, geografia

from convertersmartgrid.adaptadores import pf_estado

#: Prefijo del nombre de la copia del caso, de la copia del escenario y de la variación temporal.
PREFIJO = 'Plano_conversor'
#: Marca (``desc``) de lo que crea este guion, como la de 086:RF-87.
MARCA = f'variacion:{PREFIJO}'
#: Clases de DIgSILENT que abren o cierran: el seccionador del cubículo y el acoplador.
CLASES_MANIOBRA = ('StaSwitch', 'ElmCoup')


class EdicionImposible(ValueError):
    """Una edición del plan que no encuentra en DIgSILENT el objeto que nombra."""


def _marcar(obj) -> None:
    obj.desc = [x for x in _desc(obj) if x != MARCA] + [MARCA]


def _por_nombre(app, clases: tuple[str, ...], creados: dict) -> dict[str, list]:
    """Nombre → objetos de esas clases en la red que se calcula, más los que creó este guion."""
    salida: dict[str, list] = {}
    for clase in clases:
        for o in app.GetCalcRelevantObjects(f'*.{clase}') or []:
            salida.setdefault(o.loc_name, []).append(o)
    for nombre, o in creados.items():
        if o.GetClassName() in clases and o not in salida.get(nombre, []):
            salida.setdefault(nombre, []).append(o)
    return salida


def _uno(objetos: dict[str, list], nombre: str, que: str):
    hallados = objetos.get(nombre) or []
    if not hallados:
        raise EdicionImposible(f'{que} «{nombre}» no está en el proyecto de DIgSILENT.')
    if len(hallados) > 1:
        raise EdicionImposible(f'Hay {len(hallados)} objetos «{nombre}» ({que}): no se sabe cuál editar.')
    return hallados[0]


def _cubiculo(barra, objeto, lado: int):
    cub = barra.CreateObject('StaCubic', f'Cub_{objeto.loc_name}_{lado}')
    cub.obj_id = objeto
    cub.obj_bus = lado
    return cub


def _maniobra(app, e: dict, creados: dict) -> None:
    sw = _uno(_por_nombre(app, CLASES_MANIOBRA, creados), e['nombre_pf'], 'La maniobra')
    sw.on_off = 1 if e['estado'] == 'cerrado' else 0


def _tramo(app, e: dict, creados: dict) -> None:
    barras = _por_nombre(app, ('ElmTerm',), creados)
    desde = _uno(barras, e['desde_pf'], 'La barra de origen')
    modelo = _uno(_por_nombre(app, ('ElmLne',), creados), e['tipo_de_tramo_pf'], 'El tramo con el mismo conductor')
    red = desde.GetParent()
    if e.get('hasta_nuevo'):
        hasta = red.CreateObject('ElmTerm', e['hasta_pf'])
        hasta.uknom = getattr(desde, 'uknom', None)
        hasta.GPSlat, hasta.GPSlon = (float(x) for x in e['vertices'][-1])
        creados[hasta.loc_name] = hasta
    else:
        hasta = _uno(barras, e['hasta_pf'], 'La barra de destino')
    linea = red.CreateObject('ElmLne', e['nombre_pf'])
    linea.typ_id = getattr(modelo, 'typ_id', None)
    linea.nlnum = 1
    linea.outserv = 0
    linea.dline = float(e['longitud_km'])
    linea.GPScoords = [[float(a), float(b)] for a, b in e['vertices']]
    linea.bus1 = _cubiculo(desde, linea, 0)
    linea.bus2 = _cubiculo(hasta, linea, 1)
    creados[linea.loc_name] = linea


def _equipo(app, e: dict, creados: dict) -> None:
    linea = _uno(_por_nombre(app, ('ElmLne',), creados), e['tramo_pf'], 'El tramo del equipo')
    cub = getattr(linea, 'bus1' if e['extremo'] == 'desde' else 'bus2', None)
    if cub is None:
        raise EdicionImposible(f'El tramo «{e["tramo_pf"]}» no tiene cubículo en su extremo {e["extremo"]}.')
    sw = cub.CreateObject('StaSwitch', e['nombre_pf'])
    sw.on_off = 1 if e['estado'] == 'cerrado' else 0
    creados[sw.loc_name] = sw


APLICAR = {'maniobra': _maniobra, 'tramo': _tramo, 'equipo': _equipo}


def aplicar(app, ediciones: list[dict]) -> list[str]:
    """Aplica las ediciones en la red activa, en su orden; devuelve sus nombres en DIgSILENT."""
    creados: dict = {}
    hechas = []
    for e in ediciones:
        funcion = APLICAR.get(e.get('tipo'))
        if funcion is None:
            raise EdicionImposible(f'Edición desconocida: {e.get("tipo")!r}.')
        funcion(app, e, creados)
        hechas.append(e['nombre_pf'])
    return hechas


def _copia_del_caso(app, caso, stamp: str):
    carpeta = caso.GetParent()
    copia = carpeta.AddCopy(caso, f'{PREFIJO}_{stamp}')
    if copia is None:
        raise RuntimeError(f'DIgSILENT no copió el caso «{caso.loc_name}».')
    _marcar(copia)
    if copia.Activate() not in (0, None):
        raise RuntimeError(f'DIgSILENT no activó la copia del caso «{caso.loc_name}».')
    return copia


def _copia_del_escenario(app, stamp: str):
    esc = app.GetActiveScenario()
    if esc is None:
        return None
    copia = esc.GetParent().AddCopy(esc, f'{PREFIJO}_{stamp}')
    if copia is None:
        raise RuntimeError(f'DIgSILENT no copió el escenario «{esc.loc_name}».')
    _marcar(copia)
    copia.Activate()
    return copia


def _retirar(app, temporal, esc_copia, caso_copia, foto_caso, foto_inicial, informe: dict) -> None:
    """Borra lo temporal en orden inverso y comprueba el estado del operador con sus fotos (pf_estado)."""
    if temporal is not None:
        temporal.Deactivate()
        temporal.Delete()
    if esc_copia is not None:
        esc_copia.Deactivate()
        esc_copia.Delete()
    hecho = pf_estado.restituir(app, foto_caso) if foto_caso is not None else []
    if caso_copia is not None:
        caso_copia.Delete()
    hecho += pf_estado.restituir(app, foto_inicial) if foto_inicial is not None else []
    informe['restitucion'] = hecho
    informe['restitucion_ok'] = True


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """La variación del plan, estudiada en una copia del caso. Devuelve (informe, código de salida)."""
    v = plan.get('variacion') or {}
    informe = {'project': plan.get('project'), 'caso': plan.get('caso'), 'motor': 'DIgSILENT',
               'variacion': v.get('id'), 'version': v.get('version'), 'revision': v.get('revision'),
               'convergio': False, 'aplicadas': [], 'avisos': [], 'mensajes': [], 'escenario_copiado': False}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    foto_inicial = pf_estado.fotografiar(app)
    caso, aviso = caso_por_nombre(app, str(plan.get('caso') or ''))
    if aviso:
        informe['avisos'].append(aviso)
    if caso is None:
        return {**informe, 'error': f'el proyecto no tiene el caso «{plan.get("caso")}»'}, 2
    temporal = esc_copia = caso_copia = foto_caso = None
    stamp = str(plan.get('stamp') or 'plano')
    try:
        caso.Activate()
        foto_caso = pf_estado.fotografiar(app)
        caso_copia = _copia_del_caso(app, caso, stamp)
        esc_copia = _copia_del_escenario(app, stamp)
        informe['escenario_copiado'] = esc_copia is not None
        temporal, _etapa = crear_variacion(app, PREFIJO, stamp)
        _marcar(temporal)
        try:
            informe['aplicadas'] = aplicar(app, list(plan.get('ediciones') or []))
        except EdicionImposible as exc:
            informe['error'] = str(exc)         # el informe es el mismo objeto que completa la restitución
            return informe, 2
        flujo = flujo_de_carga(app)
        informe['mensajes'] = _salida(app)
        informe['convergio'] = bool(flujo['converged'])
        if flujo['converged']:
            informe['geo'] = geografia(None, app)
        else:
            informe['avisos'].append('El flujo de carga de la variación no converge: no hay resultados que pintar.')
    finally:
        _retirar(app, temporal, esc_copia, caso_copia, foto_caso, foto_inicial, informe)
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='La variación del plano de la red, estudiada en DIgSILENT sin dejar rastro')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    args = p.parse_args(argv)
    from convertersmartgrid.dominio.native_action import native_action_block_report
    from convertersmartgrid.dominio.util import write_json_atomic

    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    bloqueo = native_action_block_report(plan, 'plano')
    if bloqueo:
        write_json_atomic(Path(args.output_json), bloqueo)
        print(bloqueo['error'])
        return 2
    from convertersmartgrid.adaptadores.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('variacion_plano_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        informe, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe = {'project': plan.get('project'), 'motor': 'DIgSILENT', 'convergio': False,
                   'error': f'error inesperado del guion: {type(exc).__name__}: {exc}'}
        codigo = 1
    write_json_atomic(Path(args.output_json), informe)
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
