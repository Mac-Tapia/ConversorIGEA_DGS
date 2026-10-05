"""Trabajador de PowerFactory: importa y mide, o ejecuta UN estudio. Devuelve JSON.

Por qué un proceso por estudio. ``Execute()`` de la API es bloqueante y no se puede
interrumpir desde el mismo hilo: si un análisis de contingencias sobre 53.000 barras se
va a varias horas, no hay forma de cortarlo sin matar el proceso. Medido: una ejecución
del diagnóstico completo se quedó colgada más de una hora y hubo que terminarla a mano,
llevándose por delante todo lo que faltaba.

Aislando cada estudio, un cuelgue cuesta ese estudio y no el informe entero. El
orquestador (``tools/base_scenario.py``) le pone un límite de tiempo y sigue con el
siguiente, anotando cuál se pasó del presupuesto —que es, en sí, un resultado del
diagnóstico: un estudio que no termina en un tiempo razonable no sirve para un ciclo de
planificación.

    py -3.12 tools\\run_one_study.py --project PIDE_A0 --clase ComLdf
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PF_DIR = Path(r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12')

#: Opciones documentadas que hacen converger una red grande desde un arranque frío
#: (manual §24.3.1 y §24.6.5). Sin ellas el primer Newton se estanca aunque el modelo
#: esté bien; es un problema de punto de arranque, no de capacidad de la red.
LDF_RELAJADO = (
    ('iopt_lim', 0), ('iopt_plim', 0), ('iopt_at', 0), ('iopt_asht', 0),
    ('iPST_at', 0), ('iopt_pq', 0), ('iopt_fl', 1), ('iopt_lev', 1),
    ('iopt_noinit', 0),
)



def _importar_y_medir(args) -> int:
    """Importa el DGS, prepara el caso del ano 0, converge y mide el estado base.

    Vive aqui, en el trabajador, y no en el orquestador, por una razon que costo
    descubrir: **PowerFactory solo admite un proceso con el motor a la vez**. Mientras
    el orquestador mantenia la conexion para importar, cada estudio lanzado como hijo
    recibia «PowerFactory no respondio» y el informe salia entero en blanco sin que
    nada explicara por que. Ahora el orquestador no toca la API: reparte trabajo.
    """
    import random

    salida: dict = {'modo': 'importar', 'proyecto': args.project}
    try:
        sys.path.insert(0, str(PF_DIR))
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import powerfactory  # type: ignore
        from powerfactory_acceptance import (  # type: ignore
            import_dgs_file, run_load_flow_until_converged,
        )

        app = powerfactory.GetApplication()
        if app is None:
            raise RuntimeError('PowerFactory no respondio; motor tomado por otro proceso')

        import_dgs_file(app, Path(args.importar).resolve(), project_name=args.project)
        proyecto = app.GetActiveProject()
        casos = proyecto.GetContents('*.IntCase', 1)
        caso = next((c for c in casos if c.loc_name == args.caso), None)
        if caso is None and casos:
            caso = casos[0]
            caso.loc_name = args.caso
        if caso is not None:
            caso.Activate()

        escenario = None
        try:
            carpeta = app.GetProjectFolder('scen')
            if carpeta is not None:
                previos = carpeta.GetContents(args.escenario + '.IntScenario')
                escenario = previos[0] if previos else carpeta.CreateObject(
                    'IntScenario', args.escenario)
                if escenario is not None:
                    escenario.Activate()
                    if not previos:
                        # Nuevo: se define al guardarlo (manual PF 2024, 15.2); sin
                        # Save quedaba vacío para la próxima vez que se abriera.
                        escenario.Save()
        except Exception:  # noqa: BLE001 - la API varia entre versiones
            pass
        salida['caso'] = caso.loc_name if caso is not None else None
        salida['escenario'] = escenario.loc_name if escenario is not None else None

        flujo = run_load_flow_until_converged(app)
        salida['converge'] = bool(flujo.get('pass'))
        if not salida['converge']:
            salida['ok'] = True
            print(json.dumps(salida, ensure_ascii=False))
            return 5

        barras = app.GetCalcRelevantObjects('ElmTerm')
        lineas = app.GetCalcRelevantObjects('ElmLne')
        cargas = app.GetCalcRelevantObjects('ElmLod')
        rnd = random.Random(0)
        m_b = rnd.sample(barras, min(args.muestra, len(barras)))
        m_l = rnd.sample(lineas, min(args.muestra, len(lineas)))

        tension = sorted(
            x for x in (b.GetAttribute('m:u') for b in m_b if b.HasResults())
            if x is not None
        )
        carga = []
        for ln in m_l:
            if not ln.HasResults():
                continue
            try:
                v = ln.GetAttribute('c:loading')
                if v is not None:
                    carga.append(v)
            except Exception:  # noqa: BLE001
                pass

        perdidas = 0.0
        for red in app.GetCalcRelevantObjects('ElmNet'):
            try:
                v = red.GetAttribute('c:LossP')
                if v:
                    perdidas += v * 1000.0
            except Exception:  # noqa: BLE001
                pass

        demanda = 0.0
        clientes = 0
        for c in cargas:
            try:
                if not c.GetAttribute('outserv'):
                    demanda += (c.GetAttribute('plini') or 0.0)
                clientes += int(c.GetAttribute('NrCust') or 0)
            except Exception:  # noqa: BLE001
                pass

        n = len(tension)
        escala = (len(barras) / len(m_b)) if m_b else 1.0
        salida['estado'] = {
            'barras': len(barras),
            'barras_muestreadas': len(m_b),
            'tension_min': tension[0] if n else None,
            'tension_p5': tension[n // 20] if n else None,
            'tension_mediana': tension[n // 2] if n else None,
            'tension_max': tension[-1] if n else None,
            'pct_bajo_095': (sum(1 for x in tension if x < 0.95) / n * 100.0) if n else None,
            'pct_bajo_094': (sum(1 for x in tension if x < 0.94) / n * 100.0) if n else None,
            'pct_sobre_105': (sum(1 for x in tension if x > 1.05) / n * 100.0) if n else None,
            'barras_bajo_095_estimadas': round(
                sum(1 for x in tension if x < 0.95) * escala) if n else None,
            'tramos': len(lineas),
            'tramos_muestreados': len(m_l),
            'cargabilidad_max_muestra': max(carga) if carga else None,
            'pct_sobre_80': (sum(1 for x in carga if x > 80.0) / len(carga) * 100.0) if carga else None,
            'perdidas_kw': perdidas,
            'demanda_mw': demanda,
            'perdidas_pct': (perdidas / 1000.0 / demanda * 100.0) if demanda else None,
            'clientes_en_el_modelo': clientes,
        }
        salida['ok'] = True
        print(json.dumps(salida, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - la API lanza tipos propios
        salida.update(ok=False, motivo=(type(exc).__name__ + ': ' + str(exc))[:300])
        print(json.dumps(salida, ensure_ascii=False))
        return 5


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--project', required=True)
    p.add_argument('--clase', default='', help='Clase de la orden, p. ej. ComRel3.')
    p.add_argument('--desequilibrado', action='store_true',
                   help='Solo para ComLdf: iopt_net=1.')
    p.add_argument('--importar', metavar='DGS',
                   help='En vez de un estudio: importa el DGS, prepara el caso del '
                        'ano 0, hace converger el flujo y mide el estado base.')
    p.add_argument('--caso', default='ANIO_0_BASE')
    p.add_argument('--escenario', default='ANIO_0_OPERACION')
    p.add_argument('--muestra', type=int, default=6000)
    args = p.parse_args(argv)
    if args.importar:
        return _importar_y_medir(args)
    if not args.clase:
        p.error('indique --clase, o bien --importar')

    salida: dict = {'clase': args.clase, 'proyecto': args.project}
    try:
        sys.path.insert(0, str(PF_DIR))
        import powerfactory  # type: ignore

        app = powerfactory.GetApplication()
        if app is None:
            salida.update(ok=False, motivo='PowerFactory no respondió')
            print(json.dumps(salida, ensure_ascii=False))
            return 3
        ventana = app.GetOutputWindow()
        app.ActivateProject(args.project)
        proyecto = app.GetActiveProject()
        if proyecto is None:
            salida.update(ok=False, motivo=f'no existe el proyecto {args.project}')
            print(json.dumps(salida, ensure_ascii=False))
            return 3
        casos = proyecto.GetContents('*.IntCase', 1)
        if casos:
            casos[0].Activate()

        orden = app.GetFromStudyCase(args.clase)
        if orden is None or orden.GetClassName() != args.clase:
            # GetFromStudyCase con un nombre que no existe NO falla: crea una IntFolder.
            # Sin esta comprobación se confunde «la clase se llama de otra forma» con
            # «el módulo no está», y además se ensucia el caso de estudio.
            if orden is not None and orden.GetClassName() == 'IntFolder':
                try:
                    orden.Delete()
                except Exception:  # noqa: BLE001
                    pass
            salida.update(ok=False, motivo='la clase no existe en esta versión')
            print(json.dumps(salida, ensure_ascii=False))
            return 4

        if args.clase == 'ComLdf':
            for nombre, valor in LDF_RELAJADO:
                try:
                    orden.SetAttribute(nombre, valor)
                except Exception:  # noqa: BLE001
                    pass
            orden.SetAttribute('iopt_net', 1 if args.desequilibrado else 0)

        ventana.Clear()
        t0 = time.perf_counter()
        rc = orden.Execute()
        segundos = time.perf_counter() - t0

        mensajes = ventana.GetContent()
        errores = [m.replace('\n', ' ')[:200] for m in mensajes
                   if m.split(' - ')[0].strip() == 'err']
        salida.update(
            ok=True, rc=rc, segundos=round(segundos, 2),
            mensajes=len(mensajes), errores=errores[:5],
        )
        print(json.dumps(salida, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - la API lanza tipos propios
        salida.update(ok=False, motivo=f'{type(exc).__name__}: {exc}'[:300])
        print(json.dumps(salida, ensure_ascii=False))
        return 5


if __name__ == '__main__':
    raise SystemExit(main())
