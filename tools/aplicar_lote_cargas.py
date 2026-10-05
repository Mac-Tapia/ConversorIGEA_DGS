#!/usr/bin/env python
"""Aplica cargas en varios alimentadores de un proyecto de PowerFactory, uno tras otro.

Recibe un lote preparado por la web (``igea_dgs.web.services.lote_plan``): el
proyecto que eligió el operador y, por alimentador, el plan de actualización de cargas
y el de SED nuevas, ya separados desde un único Excel con varios alimentadores.

Por cada alimentador, **en el orden elegido** y sin pasar al siguiente hasta acabar:

1. **Actualización de cargas → escenario de operación nuevo** (``IntScenario``
   ``Cargas_<alim>_<fecha>``). Las cargas son datos de operación: en un escenario
   quedan aparte y la red base no se toca. Antes se desactiva el escenario que hubiera,
   para que el nuevo parta de la red base y no de los cambios de otro alimentador.
   Al terminar se guarda y se desactiva: cada escenario lleva solo su alimentador.
2. **SED nuevas → variación nueva** (``IntScheme`` ``SED_nuevas_<alim>_<fecha>``) con
   una etapa activa en la fecha del caso de estudio. Crear objetos es un cambio de
   red, no de operación: va en una variación, que se puede desactivar o borrar sin
   rastrear objeto por objeto. La variación queda **activa**, para que la SED se vea
   dibujada en el unifilar.

Lo que dice el manual de PowerFactory 2024 y fija este orden (capítulos 12, 15 y 16):

- El **caso de estudio** activo guarda qué variaciones y qué escenario están activos;
  se usa el que el proyecto tenga activo, no el primero de la carpeta.
- Un **escenario** guarda solo datos de operación (cargas, despacho, interruptores); no
  se guarda solo, y ``Deactivate()`` sin argumento descarta los cambios.
- Una **variación** guarda altas, bajas y cambios de la red; graba en ella solo la
  etapa «que graba», y con varias etapas en la misma fecha no cambia sola.
- Los **tipos** (``TypTr2``/``TypLne``) no se registran en las etapas: los que se creen
  quedan en la biblioteca aunque se borre la variación.
- Los **gráficos** no van dentro de la variación sino en el diagrama; con la variación
  desactivada, PowerFactory los pinta en amarillo.

Si algo falla en un alimentador se informa y se sigue con el siguiente: uno malo no
deja a los demás sin aplicar.

    python tools/aplicar_lote_cargas.py --lote lote.json --output-json resultado.json

Códigos de salida: 0 todo aplicado, 2 algún alimentador con fallos, 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import apply_sed_loads as actualizar  # noqa: E402
import create_sed_loads as crear  # noqa: E402

# PowerFactory admite 40 caracteres en loc_name y no acepta . / \ ni otros signos.
MAX_NOMBRE = 40


def nombre_pf(*partes: str) -> str:
    texto = '_'.join(p for p in partes if p)
    texto = re.sub(r'[^A-Za-z0-9_\-]', '_', texto)
    return texto[:MAX_NOMBRE]


def nombre_escenario(feeder: str, stamp: str) -> str:
    return nombre_pf('Cargas', feeder, stamp)


def nombre_variacion(feeder: str, stamp: str) -> str:
    return nombre_pf('SED_nuevas', feeder, stamp)


def _misma(a, b) -> bool:
    if a is None or b is None:
        return False
    try:
        return a.GetFullName() == b.GetFullName()
    except Exception:
        return a == b


def _objetos_del_alimentador(feeders: dict, feeder: str, clase: str, todos):
    """Objetos ``clase`` del alimentador; si el proyecto no tiene su ElmFeeder, todos.

    En una red unida hay un ElmFeeder por alimentador, y ``GetObjs`` devuelve lo que
    cuelga de él: así una SED que se llame igual en dos alimentadores no se confunde.
    """
    elm = feeders.get(feeder)
    if elm is not None:
        try:
            objs = list(elm.GetObjs(clase))
            if objs:
                return objs, True
        except Exception:
            pass
    return list(todos()), False


def _actualizar(app, scen_folder, entry, stamp, feeders, run_ldf) -> dict:
    feeder = entry['feeder']
    plan = entry['update']
    out = {'escenario': nombre_escenario(feeder, stamp)}
    activo = app.GetActiveScenario()
    if activo is not None:
        # Sin guardar: este proceso acaba de abrir el proyecto y no tiene cambios
        # propios en él, y guardar escribiría en un escenario del operador. Se vuelve
        # a activar al final del lote (main).
        activo.Deactivate(0)
        print(f'  escenario «{activo.loc_name}» desactivado mientras dura el lote')
    # Un escenario se crea «guardando los datos de operación actuales» (manual, 15.2):
    # vacío, activado y guardado tras escribir las cargas, recoge la red base más
    # los cambios de este alimentador y nada de otro.
    escenario = scen_folder.CreateObject('IntScenario', out['escenario'])
    if escenario is None or escenario.Activate() != 0:
        out['error'] = f'no se pudo crear o activar el escenario {out["escenario"]}'
        return out
    print(f'  escenario nuevo: {escenario.loc_name}')

    objs, filtrado = _objetos_del_alimentador(
        feeders, feeder, 'ElmLod', lambda: app.GetCalcRelevantObjects('*.ElmLod'))
    cargas = {}
    for obj in objs:
        cargas.setdefault(obj.loc_name, []).append(obj)
    aplicados, no_halladas, ambiguas, fallos = actualizar.aplicar_actualizaciones(
        cargas, plan.get('updates') or [])
    print(f'  SED actualizadas: {len(aplicados)}  no halladas: {len(no_halladas)}  '
          f'ambiguas: {len(ambiguas)}  fallos: {len(fallos)}'
          + ('' if filtrado else '  (sin ElmFeeder: se buscó en todo el proyecto)'))
    out.update(
        applied=len(aplicados), not_found=no_halladas, ambiguous=ambiguas,
        write_errors=fallos,
        changes=[{
            'object': item['sed_code'],
            'before': item.get('antes'),
            'after': item.get('despues'),
        } for item in aplicados],
        _scenario_obj=escenario,
    )
    # apply_feeder_plan keeps it active through the combined ComLdf and only then
    # saves/deactivates it. Before that point Deactivate(0) is a true rollback.
    return out


def _crear(app, project, scheme_folder, entry, stamp, feeders, run_ldf) -> dict:
    feeder = entry['feeder']
    plan = entry['create']
    out = {'variacion': nombre_variacion(feeder, stamp)}
    variacion = scheme_folder.CreateObject('IntScheme', out['variacion'])
    if variacion is None:
        out['error'] = f'no se pudo crear la variación {out["variacion"]}'
        return out
    caso = app.GetActiveStudyCase()
    instante = int(getattr(caso, 'iStudyTime', 0) or 0)
    # NewStage(…, activate=1) activa la variación y deja la etapa nueva como la que
    # graba. Devuelve un entero, no la etapa: se busca por nombre.
    nombre_etapa = nombre_pf('Etapa', feeder, stamp)
    variacion.NewStage(nombre_etapa, instante, 1)
    etapa = next((s for s in variacion.GetContents('*.IntSstage') if s.loc_name == nombre_etapa), None)
    if etapa is not None and not _misma(app.GetRecordingStage(), etapa):
        # Todas las variaciones del lote tienen la misma fecha, y con fechas iguales
        # sigue grabando la etapa que ya grababa (manual, 16.5): sin esto, la SED
        # del segundo alimentador acabaría en la variación del primero.
        etapa.Activate(1)
    if etapa is None or not _misma(app.GetRecordingStage(), etapa):
        # Sin etapa que grabe, lo creado iría a la red base o a otra variación.
        out['error'] = f'no se pudo dejar grabando la etapa de {out["variacion"]}; no se creó nada'
        return out
    print(f'  variación nueva: {variacion.loc_name} (etapa {etapa.loc_name}, grabando)')

    terms, filtrado = _objetos_del_alimentador(
        feeders, feeder, 'ElmTerm', lambda: app.GetCalcRelevantObjects('*.ElmTerm'))
    creador = crear.Creador(
        app, project, crear._grid_of(app),
        nominal_kv=float(plan.get('nominal_kv') or 0) or 22.9,
        lv_kv=float(plan.get('lv_kv') or 0.22),
        terminals={t.loc_name: t for t in terms},
    )
    for spec in plan.get('create') or []:
        creador.crear(spec)
    print(f'  SED creadas: {len(creador.created)}  omitidas: {len(creador.skipped)}  '
          f'fallos: {len(creador.failed)}  sin dibujar: {len(creador.undrawn)}'
          + ('' if filtrado else '  (sin ElmFeeder: se buscó en todo el proyecto)'))
    out.update(created=creador.created, skipped=creador.skipped, failed=creador.failed,
               undrawn=creador.undrawn, line_types_created=sorted(set(creador.types_made)))
    eco = plan.get('economia')
    if eco and creador.created:
        # Datos económicos de la etapa (pestaña «Economical Data»): es lo que la
        # evaluación técnico-económica lee como inversión de esta parte del plan.
        for attr in ('InvCosts', 'OrigVal', 'ScrVal', 'AddCosts', 'LifeSpan'):
            etapa.SetAttribute(attr, eco[attr])
        out['economia'] = {k: eco[k] for k in ('InvCosts', 'OrigVal', 'ScrVal', 'AddCosts', 'LifeSpan')}
        print(f'  inversión de la etapa: {eco["InvCosts"]:.1f} kUSD, vida útil {eco["LifeSpan"]} años')
    if run_ldf:
        out['load_flow'] = actualizar.flujo_de_carga(app)
    out['_variation_obj'] = variacion
    out['_creator'] = creador
    return out


def tecnico_economico(app, tec: dict, informe_txt: Path | None) -> dict:
    """Lanza ``ComTececo`` sobre la estrategia: las variaciones activas del caso.

    La orden es una por caso de estudio (``GetFromStudyCase``) y conserva sus ajustes,
    como cualquier orden de cálculo (manual, 12.8). Se sobrescriben solo los que el
    lote decide; el resto queda como el operador lo dejó.
    """
    out: dict = {'parametros': tec.get('parametros')}
    orden = app.GetFromStudyCase('ComTececo')
    if orden is None:
        out['error'] = 'el caso de estudio no admite la orden ComTececo'
        return out
    for attr, valor in tec['comtececo'].items():
        orden.SetAttribute(attr, valor)
    caso = app.GetActiveStudyCase()
    anio = _anio_de_estudio(caso)
    p = tec.get('parametros') or {}
    if anio is not None and not int(p.get('inicio', anio)) <= anio <= int(p.get('fin', anio)):
        out['aviso'] = (f'las etapas se activan en {anio}, fuera del periodo '
                        f'{p.get("inicio")}-{p.get("fin")}: no entran en el VAN')
        print(f'  AVISO: {out["aviso"]}')
    ventana = app.GetOutputWindow()
    try:
        ventana.Clear()
    except Exception:
        pass
    print('\n== Evaluación técnico-económica (ComTececo)')
    rc = orden.Execute()
    out['return_code'] = rc
    out['ok'] = rc == 0
    lineas = [str(x) for x in (ventana.GetContent() or [])]
    # El informe va en la ventana de salida de PowerFactory: se guarda entero y se
    # muestran las líneas con el resultado.
    out['resumen'] = [ln for ln in lineas if any(k in ln for k in ('NPV', 'Net Present', 'Total', 'Error', 'error'))][-40:]
    for ln in out['resumen']:
        print('  ' + ln)
    if informe_txt is not None:
        try:
            ventana.Save(str(informe_txt))
            out['informe'] = informe_txt.name
        except Exception as exc:
            out['informe_error'] = str(exc)
    print(f'  ComTececo -> {rc}' + ('' if rc == 0 else '  (revise el informe de la ventana de salida)'))
    return out


def _anio_de_estudio(caso) -> int | None:
    import datetime

    try:
        t = int(caso.iStudyTime)
    except Exception:
        return None
    return datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).year if t > 0 else None


def con_fallos(r: dict) -> bool:
    """Un alimentador falla si algo no se aplicó; «sin dibujar» es aviso, no fallo."""
    for parte in (r.get('actualizacion'), r.get('creacion')):
        if not parte:
            continue
        if parte.get('error') or parte.get('not_found') or parte.get('ambiguous') \
                or parte.get('write_errors') or parte.get('failed'):
            return True
    return bool(r.get('error'))


def _delete_container(container, report: dict) -> None:
    if container is None:
        return
    name = str(getattr(container, 'loc_name', container))
    try:
        deactivate = getattr(container, 'Deactivate', None)
        if callable(deactivate):
            try:
                deactivate(0)
            except TypeError:
                deactivate()
        container.Delete()
        report['containers_deleted'].append(name)
    except Exception as exc:
        report['errors'].append(f'{name}: {type(exc).__name__}: {exc}')


def _rollback_feeder(update: dict | None, creation: dict | None) -> dict:
    report = {'status': 'RESTORED', 'attempted': True, 'containers_deleted': [], 'errors': []}
    creator = (creation or {}).get('_creator')
    # Types and graphic objects are not stage data in PowerFactory. Newer Creador
    # implementations expose them so a failed variation cannot leave library debris.
    for obj in reversed(list(getattr(creator, 'rollback_objects', []) or [])):
        _delete_container(obj, report)
    _delete_container((creation or {}).get('_variation_obj'), report)
    _delete_container((update or {}).get('_scenario_obj'), report)
    if report['errors']:
        report['status'] = 'PARTIAL'
    return report


def _public_part(part: dict | None) -> dict | None:
    if part is None:
        return None
    return {key: value for key, value in part.items() if not key.startswith('_')}


def _find_container(folder, class_name: str, name: str):
    try:
        return next(
            (item for item in folder.GetContents(f'*.{class_name}') if item.loc_name == name),
            None,
        )
    except Exception:
        return None


def apply_feeder_plan(
    app, project, scen_folder, scheme_folder, entry, stamp, feeders, run_ldf,
) -> dict:
    """Apply one feeder as a transaction and return reread/ComLdf/rollback evidence."""

    feeder = entry['feeder']
    update = creation = None
    error = None
    try:
        if entry.get('update'):
            update = _actualizar(app, scen_folder, entry, stamp, feeders, False)
        if entry.get('create'):
            creation = _crear(app, project, scheme_folder, entry, stamp, feeders, False)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        # A PF exception can happen after CreateObject but before the helper returns.
        # Resolve the named container so rollback still owns what this feeder created.
        if entry.get('update') and update is None:
            update = {
                'escenario': nombre_escenario(feeder, stamp),
                '_scenario_obj': _find_container(
                    scen_folder, 'IntScenario', nombre_escenario(feeder, stamp),
                ),
            }
        if entry.get('create') and creation is None:
            creation = {
                'variacion': nombre_variacion(feeder, stamp),
                '_variation_obj': _find_container(
                    scheme_folder, 'IntScheme', nombre_variacion(feeder, stamp),
                ),
            }

    comldf = (
        actualizar.flujo_de_carga(app)
        if run_ldf and error is None
        else {'requested': bool(run_ldf), 'converged': None if error else True}
    )
    changes = list((update or {}).get('changes') or [])
    before = {item['object']: item.get('before') for item in changes}
    after = {item['object']: item.get('after') for item in changes}
    created = [
        str(item.get('sed_code'))
        for item in (creation or {}).get('created') or []
        if item.get('sed_code')
    ]
    failed = bool(error or con_fallos({'actualizacion': update, 'creacion': creation}))
    if run_ldf and not comldf.get('converged'):
        failed = True

    if failed:
        rollback = _rollback_feeder(update, creation)
        status = 'ROLLED_BACK' if rollback['status'] == 'RESTORED' else 'ROLLBACK_FAILED'
    else:
        scenario = (update or {}).get('_scenario_obj')
        if scenario is not None:
            scenario.Save()
            try:
                scenario.Deactivate(0)
            except TypeError:
                scenario.Deactivate()
        rollback = {
            'status': 'NOT_REQUIRED', 'attempted': False,
            'containers_deleted': [], 'errors': [],
        }
        status = 'APPLIED'

    result = {
        'feeder': feeder,
        'status': status,
        'before': before,
        'after': after,
        'created': created,
        'comldf': comldf,
        'rollback': rollback,
        'actualizacion': _public_part(update),
        'creacion': _public_part(creation),
    }
    if error:
        result['error'] = error
    return result


def append_evidence(path: Path, result: dict) -> None:
    """Durably append a feeder result before the next feeder starts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, default=str) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Cargas por alimentador en un proyecto de PowerFactory')
    p.add_argument('--lote', required=True, help='JSON de igea_dgs.web.services.lote_plan')
    p.add_argument('--output-json', help='Informe del resultado')
    args = p.parse_args(argv)
    lote = json.loads(Path(args.lote).read_text(encoding='utf-8'))
    entradas = [e for e in lote.get('feeders') or [] if e.get('update') or e.get('create')]
    if not entradas:
        print('El lote no tiene nada que aplicar.')
        return 2

    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de PowerFactory no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:
        print(f'ERROR: no se pudo conectar a PowerFactory: {exc}')
        return 3

    project = crear._activate(app, lote['project'])
    if str(getattr(project, 'loc_name', '')) != str(lote['project']):
        print(
            f"ERROR: el proyecto activo {getattr(project, 'loc_name', None)!r} no "
            f"coincide exactamente con el plan {lote['project']!r}."
        )
        return 2
    print(f'proyecto: {project.loc_name}')
    print(f'caso activo: {app.GetActiveStudyCase()}')
    scen_folder = app.GetProjectFolder('scen')
    scheme_folder = app.GetProjectFolder('scheme')
    feeders = {f.loc_name: f for f in project.GetContents('*.ElmFeeder', 1)}
    stamp = lote.get('stamp') or ''
    run_ldf = bool(lote.get('run_load_flow'))

    # El caso de estudio guarda qué escenario está activo (manual, 12.7): se deja como
    # estaba, y las variaciones nuevas quedan activas en él.
    escenario_original = app.GetActiveScenario()

    resultados = []
    evidence_path = (
        Path(args.output_json).with_suffix('.evidence.jsonl')
        if args.output_json else Path(args.lote).with_suffix('.evidence.jsonl')
    )
    evidence_path.unlink(missing_ok=True)
    for n, entry in enumerate(entradas, start=1):
        feeder = entry['feeder']
        print(f'\n== {feeder} ({n}/{len(entradas)})')
        r = apply_feeder_plan(
            app, project, scen_folder, scheme_folder, entry, stamp, feeders, run_ldf,
        )
        if r.get('error'):
            print(f'  ERROR: {r["error"]}')
        resultados.append(r)
        append_evidence(evidence_path, r)

    if escenario_original is not None and app.GetActiveScenario() is None:
        if escenario_original.Activate() == 0:
            print(f'\nescenario «{escenario_original.loc_name}» activo de nuevo, como estaba')

    malos = [r['feeder'] for r in resultados if r.get('status') != 'APPLIED']
    print(f'\nAlimentadores procesados: {len(resultados)}  con fallos: {len(malos)}'
          + (f' ({", ".join(malos)})' if malos else ''))

    tec = None
    if lote.get('tec'):
        if any(
            r.get('status') == 'APPLIED' and (r.get('creacion') or {}).get('created')
            for r in resultados
        ):
            informe = Path(args.output_json).with_suffix('.tececo.txt') if args.output_json else None
            try:
                tec = tecnico_economico(app, lote['tec'], informe)
            except Exception as exc:
                tec = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
                print(f'  ERROR en la evaluación técnico-económica: {tec["error"]}')
        else:
            tec = {'ok': False, 'error': 'no se creó ninguna SED: no hay inversión que evaluar'}
            print(f'\nEvaluación técnico-económica omitida: {tec["error"]}')

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(
            {'project': project.loc_name, 'stamp': stamp, 'feeders': resultados,
             'tecnico_economico': tec, 'evidence_jsonl': str(evidence_path)},
            indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
        print(f'Informe: {args.output_json}')
    return 2 if malos or (tec is not None and not tec.get('ok')) else 0


if __name__ == '__main__':
    raise SystemExit(main())
