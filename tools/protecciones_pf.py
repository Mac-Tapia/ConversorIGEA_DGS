#!/usr/bin/env python
"""Protecciones de la spec 049 en DIgSILENT: capacidades de la versión conectada y fallas.

Dos usos, los dos con el plan que prepara la web (contexto nativo firmado, acción
``protecciones``):

``--capacidades``: inventario sin estudiar nada. Qué órdenes hay en la versión conectada
(``ComShc``, ``ComShctrace``, ``ComProtgraphic``) y qué métodos de la referencia de Python de
PowerFactory 2024 tienen; qué atributos de ``ComShc`` existen (``HasAttribute``); cuántos
``ElmRelay``, ``RelFuse``, ``StaCt`` y ``StaVt`` tiene el proyecto, y la generación del caso
activo con su estado. Con ``ejecutar_ordenes`` en el plan ejecuta ``ComShc`` para saber si la
licencia lo cubre: es la única prueba que no miente (``tools/check_pf_license.py``).
``GetFromStudyCase`` crea la orden en el caso si no estaba, como hace DIgSILENT al abrir su
diálogo; no toca la red.

Sin ``--capacidades``: las fallas del plan (``protecciones.plan_protecciones``). Por cada una
define la falla en ``ComShc`` con los atributos que el inventario comprobó, relee el tipo con
``GetFaultType`` y corre la traza de cortocircuito (``ComShctrace``): al arrancar, el tiempo
previsto de cada dispositivo (``GetDeviceTime``), y paso a paso cuál dispara. Así salen los
tiempos de primaria y respaldo sin adivinar nombres de variables de resultado. La generación
del caso se compara con la del plan antes de empezar: si cambió, no se estudia otra red.
Los ajustes propuestos se escriben solo en una variación nueva (049:RF-8) que se deja
desactivada al terminar, y la configuración de ``ComShc`` y el caso activo se restituyen.

Lo que este guion **no** hace: dar por coordinada la red. Eso lo decide
``protecciones.evaluar_coordinacion`` con los criterios del perfil. ``ComProtgraphic`` solo
refresca páginas de gráficos en PF 2024 (``AddToUpdatePages``) y se inventaría sin usarlo.

    python tools/protecciones_pf.py --capacidades --plan plan.json --output-json informe.json
    python tools/protecciones_pf.py --plan plan.json --output-json informe.json

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, crear_variacion

from convertersmartgrid import protecciones as pr

#: Órdenes que se inventarían y los métodos documentados de cada una (referencia 2024, 5.4).
METODOS_DOCUMENTADOS = {
    'ComShc': ('GetFaultType', 'ExecuteRXSweep', 'GetOverLoadedBranches', 'GetOverLoadedBuses'),
    'ComShctrace': ('ExecuteInitialStep', 'ExecuteNextStep', 'ExecuteAllSteps', 'NextStepAvailable',
                    'GetCurrentTimeStep', 'GetDeviceTime', 'GetTrippedDevices', 'GetStartedDevices',
                    'GetNonStartedDevices', 'GetDeviceSwitches', 'GetSwitchTime', 'BlockSwitch'),
    'ComProtgraphic': ('AddToUpdatePages', 'ClearUpdatePages'),
}
#: Clases de dispositivos y medida del proyecto, con los métodos documentados (5.2.23, 5.3.1).
CLASES_DISPOSITIVO = {
    'ElmRelay': ('IsStarted', 'GetMaxFdetectCalcI', 'CheckRanges', 'CalculateMaxFaultCurrents', 'SetTime',
                 'SetOutOfService', 'GetSlot'),
    'RelFuse': (),
    'StaCt': ('SetPrimaryTap',),
    'StaVt': (),
}


def _nombres(objs) -> list[str]:
    return sorted({o.loc_name for o in objs})


def _metodos(obj, metodos) -> dict[str, bool]:
    return {m: obj is not None and callable(getattr(obj, m, None)) for m in metodos}


def _generacion(app) -> list[dict]:
    """La generación del caso activo con su estado (049:RF-4); las cargas negativas, marcadas."""
    out = []
    for clase in pr.GENERACION_PF:
        for g in app.GetCalcRelevantObjects(f'*.{clase}'):
            out.append({'nombre': g.loc_name, 'clase': clase, 'en_servicio': not getattr(g, 'outserv', 0)})
    for carga in app.GetCalcRelevantObjects('*.ElmLod'):
        p = getattr(carga, 'plini', None)
        if isinstance(p, (int, float)) and p < 0:
            out.append({'nombre': carga.loc_name, 'clase': 'ElmLod', 'modelo': 'carga_negativa',
                        'en_servicio': not getattr(carga, 'outserv', 0)})
    return sorted(out, key=lambda g: (g['clase'], g['nombre']))


def _activar(app, plan):
    return activar_proyecto(app, plan['project'], plan.get('folder'))


def capacidades(app, plan: dict, version: str | None = None) -> tuple[dict, int]:
    """El inventario de la versión conectada (049:RF-1), sin estudiar nada."""
    informe = {'project': plan.get('project'), 'modo': 'capacidades', 'version': version, 'avisos': []}
    if _activar(app, plan) is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    caso = app.GetActiveStudyCase()
    informe['caso'] = getattr(caso, 'loc_name', None)
    comandos = {}
    for clase, metodos in METODOS_DOCUMENTADOS.items():
        orden = app.GetFromStudyCase(clase)
        c = {'existe': orden is not None, 'ejecuta': None, 'metodos': _metodos(orden, metodos)}
        if orden is not None and clase == 'ComShc':
            c['atributos'] = {a: bool(orden.HasAttribute(a)) for a in pr.ATRIBUTOS_COMSHC.values()}
        if orden is not None and clase in pr.LICENCIA_PREVIA and plan.get('ejecutar_ordenes'):
            rc = orden.Execute()
            c['ejecuta'], c['rc'] = rc == 0, rc
        comandos[clase] = c
    informe['comandos'] = comandos
    clases = {}
    for clase, metodos in CLASES_DISPOSITIVO.items():
        objs = list(app.GetCalcRelevantObjects(f'*.{clase}'))
        clases[clase] = {'cuantos': len(objs), 'nombres': _nombres(objs),
                         'metodos': _metodos(objs[0] if objs else None, metodos)}
    informe['clases'] = clases
    informe['generacion'] = _generacion(app)
    if comandos.get('ComProtgraphic', {}).get('existe'):
        informe['avisos'].append('ComProtgraphic está, pero en PF 2024 solo refresca páginas de gráficos: no '
                                 'evalúa la coordinación')
    return informe, 0


# --------------------------------------------------------------------------- fallas
def _caso(app, nombre):
    carpeta = app.GetProjectFolder('study')
    return next((c for c in (carpeta.GetContents('*.IntCase') if carpeta else ()) if c.loc_name == nombre), None)


def _por_nombre(app, clases) -> dict:
    return {o.loc_name: o for clase in clases for o in app.GetCalcRelevantObjects(f'*.{clase}')}


def _capturar(traza, dispositivos: dict) -> dict:
    """Arranca la traza y lee tiempos previstos y la secuencia de disparos (049:RF-4)."""
    rc = traza.ExecuteInitialStep()
    if rc != 0:
        return {'estado': 'no_evaluada', 'motivo': f'la traza de cortocircuito no arrancó (código {rc}); si es la '
                                                    'licencia, DIgSILENT lo dice en la ventana de salida'}
    arrancados = list(traza.GetStartedDevices()) + list(traza.GetTrippedDevices())
    previstos = {d.loc_name: traza.GetDeviceTime(d) for d in arrancados}
    secuencia, pasos = [], 0
    while traza.NextStepAvailable() and pasos < 1000:
        if traza.ExecuteNextStep() != 0:
            break
        pasos += 1
        disparados = _nombres(traza.GetTrippedDevices())
        secuencia.append({'t_s': traza.GetCurrentTimeStep(), 'disparados': disparados})
    disparados = set(_nombres(traza.GetTrippedDevices()))
    filas = []
    for nombre in sorted(dispositivos):
        obj = dispositivos[nombre]
        t = previstos.get(nombre)
        corriente = None
        if callable(getattr(obj, 'GetMaxFdetectCalcI', None)):
            err, valor = obj.GetMaxFdetectCalcI(0, 0)          # fase, A primarios (5.2.23)
            corriente = None if err else valor
        filas.append({'id': nombre, 'tiempo_s': t, 'corriente_a': corriente,
                      'estado': 'disparo' if nombre in disparados else ('arranco' if t is not None else 'no_arranco')})
    return {'estado': 'evaluada', 'dispositivos': filas, 'secuencia': secuencia}


def _definir_falla(app, shc, falla: dict, atributos: dict) -> str | None:
    """Escribe la falla en ``ComShc``; el motivo si no quedó como se pidió."""
    barra = _por_nombre(app, ('ElmTerm',)).get(falla['ubicacion'])
    if barra is None:
        return f"la barra {falla['ubicacion']} no está en la red del caso"
    shc.SetAttribute(atributos['seleccion'], 0)          # solo la ubicación elegida
    shc.SetAttribute(atributos['ubicacion'], barra)
    shc.SetAttribute(atributos['tipo'], falla['iopt_shc'])
    shc.SetAttribute(atributos['r_ohm'], falla['r_ohm'])
    shc.SetAttribute(atributos['x_ohm'], falla['x_ohm'])
    leido = shc.GetFaultType()
    if leido != falla['codigo_tipo']:
        return f"ComShc quedó con el tipo {leido} y se pidió {falla['codigo_tipo']} ({falla['tipo']})"
    return None


def ejecutar(app, plan: dict, cancelar=lambda: False) -> tuple[dict, int]:
    """Las fallas del plan en el caso vinculado; cada falla, independiente de las demás.

    ``cancelar`` se mira entre fallas: la que está en marcha termina y se conserva.
    """
    informe = {'project': plan.get('project'), 'modo': 'fallas', 'caso': plan.get('caso'), 'rol': plan.get('rol'),
               'clave_contexto': plan.get('clave_contexto'), 'avisos': [], 'fallas': []}
    if plan.get('schema') != pr.ESQUEMA_PLAN:
        return {**informe, 'error': 'el plan no es un plan de protecciones de la spec 049'}, 2
    if _activar(app, plan) is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    caso = _caso(app, plan['caso'])
    if caso is None:
        return {**informe, 'error': f"el proyecto no tiene el caso «{plan['caso']}»"}, 2
    from convertersmartgrid.pf_arnes import caso_restituido

    with caso_restituido(app):
        caso.Activate()
        ahora = [{k: g[k] for k in ('nombre', 'clase', 'en_servicio')} for g in _generacion(app)
                 if g.get('modelo') != 'carga_negativa']
        if ahora != plan['aportes']:
            return {**informe, 'error': 'la generación del caso cambió desde que se preparó el plan: vuelva a '
                                        'comprobar las capacidades', 'generacion': ahora}, 2
        informe['aportes'] = plan['aportes']
        shc, traza = app.GetFromStudyCase('ComShc'), app.GetFromStudyCase('ComShctrace')
        if shc is None or traza is None:
            return {**informe, 'error': 'el caso no tiene ComShc o ComShctrace'}, 2
        atributos = plan['atributos_comshc']
        previos = {a: shc.GetAttribute(a) for a in atributos.values()}
        dispositivos = _por_nombre(app, ('ElmRelay', 'RelFuse'))
        faltan = [d['id'] for d in plan['dispositivos'] if d['id'] not in dispositivos]
        if faltan:
            return {**informe, 'error': 'no están en el proyecto: ' + ', '.join(faltan)}, 2
        dispositivos = {d['id']: dispositivos[d['id']] for d in plan['dispositivos']}
        variacion = None
        try:
            ajustes = plan['escritura']['ajustes']
            if ajustes:

                variacion, _etapa = crear_variacion(app, plan['escritura']['variacion'], 'ajustes')
                informe['variacion'] = variacion.loc_name
                # 049:RF-9: escribir no es aceptar. Se aceptan tras guardar, reabrir y releer en
                # DIgSILENT (T4); hasta entonces el informe no los da por persistidos.
                informe['persistencia'] = {'estado': 'sin_verificar',
                                           'motivo': 'falta guardar, reabrir el proyecto y releer los ajustes'}
                for a in ajustes:
                    dispositivos[a['dispositivo']].SetAttribute(a['atributo'], a['valor'])
            for falla in plan['fallas']:
                if cancelar():
                    informe['cancelado'] = True
                    break
                fila = {k: falla[k] for k in ('id', 'tipo', 'ubicacion', 'fase', 'r_ohm', 'x_ohm', 'escenario',
                                              'protegen')}
                try:
                    motivo = _definir_falla(app, shc, falla, atributos)
                    fila.update({'estado': 'no_evaluada', 'motivo': motivo} if motivo
                                else _capturar(traza, dispositivos))
                except Exception as exc:  # noqa: BLE001 - una falla que revienta no tumba las demás
                    fila.update(estado='no_evaluada', motivo=f'{type(exc).__name__}: {exc}')
                informe['fallas'].append(fila)
        finally:
            for a, v in previos.items():
                shc.SetAttribute(a, v)
            if variacion is not None:
                # 049:RF-8: los ajustes quedan en su variación, desactivada hasta validarlos.
                variacion.Deactivate()
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Protecciones de la spec 049 en DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    p.add_argument('--capacidades', action='store_true',
                   help='Solo inventariar órdenes, métodos, atributos, dispositivos y generación')
    p.add_argument('--cancel-file', help='Fichero que pide cancelar (se mira entre fallas)')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    from convertersmartgrid.native_action import native_action_block_report

    bloqueado = native_action_block_report(plan, 'protecciones')
    if bloqueado:
        Path(args.output_json).write_text(json.dumps(bloqueado, indent=2, ensure_ascii=False) + '\n',
                                          encoding='utf-8')
        print(bloqueado['error'])
        return 2
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar, importar_api

    try:
        app = conectar('protecciones_pf.py')
        version = getattr(importar_api(), '__version__', None)
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        cancelar = (lambda: Path(args.cancel_file).exists()) if args.cancel_file else (lambda: False)
        informe, codigo = capacidades(app, plan, version) if args.capacidades else ejecutar(app, plan, cancelar)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = {'project': plan.get('project'), 'error': f'error inesperado del guion: '
                                                                     f'{type(exc).__name__}: {exc}'}, 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(informe.get('error') or f"Protecciones ({informe.get('modo')}) en {informe.get('project')}")
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
