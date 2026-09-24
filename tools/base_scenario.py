"""Escenario base (año 0) del PIDE: lo construye, lo hace converger y lo diagnostica.

Qué es el año 0. Es la foto de la red tal como está, y es el punto de partida contra el
que se mide todo lo demás: sin un año 0 defendible, los años 4, 8, 12, 16 y 20 no miden
nada. Por eso esta fase se cierra antes de pasar a las siguientes.

Qué hace, en orden:

1. Une los 96 alimentadores en una sola grid, con la tensión de cada uno, su fuente
   tomada del ``SOURCE`` de su TXT, y los enlaces entre alimentadores como
   interruptores **normalmente abiertos** (ver :mod:`igea_dgs.combine`).
2. La importa en PowerFactory como proyecto nuevo y crea el caso de estudio
   **AÑO_0_BASE** con su escenario de operación.
3. Hace converger el flujo de potencia y comprueba que el resultado es utilizable:
   cuántas barras tienen resultado, cuántas fuera de límites, cuánta pérdida.
4. Ejecuta **todos** los módulos licenciados y anota, de cada uno, si se ejecutó y si
   el resultado significa algo.
5. Escribe el diagnóstico y **la lista de datos que faltan**, ordenada por cuántos
   estudios desbloquea cada uno.

La distinción del punto 4 es la razón de ser de este guion. ``ComRel3`` se ejecuta
igual de bien con todas las tasas de falla a cero y devuelve SAIDI = 0. No falla:
miente. El informe separa «se ejecutó» de «el resultado es defendible».

    py -3.12 tools\\base_scenario.py --red R.txt --cargas C.txt --equipos E.txt
    py -3.12 tools\\base_scenario.py --mdb BaseDatos.mdb --solo-datos

``--solo-datos`` no toca PowerFactory: solo audita el export y lista lo que falta.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from igea_dgs.combine import build_combined  # noqa: E402
from igea_dgs.dgs import write_dgs  # noqa: E402
from igea_dgs.studies import (  # noqa: E402
    ESTUDIOS,
    auditar_datos,
    datos_que_faltan,
    entradas_por_nombre,
    estudios_bloqueados,
    estudios_ejecutables,
)

#: Nombre del caso de estudio del año base. Los años siguientes seguirán el patrón
#: AÑO_4_..., AÑO_8_..., que es como PowerFactory organiza un plan multianual
#: (Study Cases + Operation Scenarios, manual cap. 12 y 15).
CASO_BASE = 'ANIO_0_BASE'
ESCENARIO_BASE = 'ANIO_0_OPERACION'

#: Límites con los que se juzga el flujo del año 0. Los de tensión son los del TdR del
#: VAD para zona rural; la cargabilidad es el criterio habitual de planificación.
LIMITE_TENSION_MIN = 0.95
LIMITE_TENSION_MAX = 1.05
LIMITE_TENSION_RURAL = 0.94   # 6 % de caída
LIMITE_CARGABILIDAD = 80.0


def _cargar_dataset(args):
    if args.mdb:
        from igea_dgs.access import read_access_dataset
        return read_access_dataset(args.mdb, equipment_path=args.equipment_mdb)
    from igea_dgs.dataset import CymdistDataset
    return CymdistDataset.from_files(args.red, args.cargas, args.equipos)


# --------------------------------------------------------------------------------
# Informe de datos (no necesita PowerFactory)
# --------------------------------------------------------------------------------

def informe_de_datos(dataset) -> dict:
    """Qué estudios están listos, cuáles no, y qué dato desbloquea cada cosa."""
    listos = estudios_ejecutables()
    bloqueados = estudios_bloqueados()
    faltantes = datos_que_faltan()
    entradas = entradas_por_nombre()

    print('=' * 78)
    print('DATOS DE ENTRADA — qué hay y qué falta para el año 0')
    print('=' * 78)
    print()
    aud = auditar_datos(dataset)
    for linea in aud.hallazgos:
        print(f'  · {linea}')
    print()
    print(f'Estudios con resultado defendible hoy : {len(listos)} de {len(ESTUDIOS)}')
    for e in listos:
        print(f'    ✓ {e.nombre} ({e.clase_pf}, cap. {e.capitulo})')
    print()
    print(f'Estudios que se ejecutan pero NO son defendibles: {len(bloqueados)}')
    for e in bloqueados:
        print(f'    ✗ {e.nombre} — le falta: '
              f'{", ".join(x.nombre for x in e.bloqueantes)}')
    print()
    print('-' * 78)
    print('LO QUE HAY QUE CONSEGUIR, por cuántos estudios desbloquea')
    print('-' * 78)
    for i, (dato, estudios) in enumerate(faltantes.items(), start=1):
        entrada = entradas[dato]
        print()
        print(f'{i}. {dato}   [{entrada.estado}]  → desbloquea {len(estudios)} estudio(s)')
        print(f'   De dónde sale : {entrada.donde}')
        print(f'   Sin esto      : {entrada.sin_esto}')
        print(f'   Afecta a      : {", ".join(estudios)}')
    return {
        'listos': [e.clave for e in listos],
        'bloqueados': {e.clave: [x.nombre for x in e.bloqueantes] for e in bloqueados},
        'faltantes': {
            dato: {
                'estado': entradas[dato].estado,
                'donde': entradas[dato].donde,
                'sin_esto': entradas[dato].sin_esto,
                'estudios': estudios,
            }
            for dato, estudios in faltantes.items()
        },
        'auditoria': {
            'cargas_totales': aud.cargas_totales,
            'cargas_con_energia': aud.cargas_con_energia,
            'energia_kwh': aud.energia_kwh,
            'tasas_falla_no_cero': aud.tasas_falla_no_cero,
        },
    }


# --------------------------------------------------------------------------------
# PowerFactory
# --------------------------------------------------------------------------------

def _conectar():
    pf = Path(r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12')
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(
            f'Intérprete {sys.version_info.major}.{sys.version_info.minor}; la API pide '
            '3.12. Use .venv\\Scripts\\python.exe, que es el entorno del proyecto.')
    sys.path.insert(0, str(pf))
    import powerfactory  # type: ignore

    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError('PowerFactory no respondió. ¿Abierto en otra sesión?')
    return app


def preparar_caso_base(app, nombre_proyecto: str) -> dict:
    """Crea el caso de estudio y el escenario de operación del año 0.

    PowerFactory organiza un plan multianual con **Study Cases** y **Operation
    Scenarios** (manual cap. 12 y 15): el caso fija qué se calcula y el escenario fija
    el estado de la red —cargas, maniobras, tomas— de ese año. Dejar el año 0 con su
    caso y su escenario propios es lo que permite que el año 4 sea una copia con otra
    demanda en lugar de otro proyecto entero.
    """
    proyecto = app.GetActiveProject()
    casos = proyecto.GetContents('*.IntCase', 1)
    caso = next((c for c in casos if c.loc_name == CASO_BASE), None)
    if caso is None and casos:
        caso = casos[0]
        caso.loc_name = CASO_BASE
    if caso is not None:
        caso.Activate()

    escenario = None
    try:
        carpeta = app.GetProjectFolder('scen')
        if carpeta is not None:
            existentes = carpeta.GetContents(f'{ESCENARIO_BASE}.IntScenario')
            escenario = existentes[0] if existentes else carpeta.CreateObject(
                'IntScenario', ESCENARIO_BASE)
            if escenario is not None:
                escenario.Activate()
    except Exception as exc:  # noqa: BLE001 - la API varía entre versiones
        print(f'  aviso: no se pudo crear el escenario de operación ({exc})')

    return {
        'caso': caso.loc_name if caso is not None else None,
        'escenario': escenario.loc_name if escenario is not None else None,
    }


def medir_estado_base(app, *, muestra: int = 6000) -> dict:
    """Las cifras que definen si el año 0 es utilizable.

    Se muestrea. Cada ``GetAttribute`` es una llamada a la API y cuesta del orden de
    diez milisegundos: recorrer las 53.000 barras y los 38.000 tramos son más de
    130.000 llamadas y unos veinte minutos, para responder a una pregunta que una
    muestra de seis mil contesta con holgura. Lo que no se muestrea es lo que tiene que
    ser exacto —el recuento de elementos y las pérdidas totales, que PowerFactory ya
    agrega por su cuenta—.
    """
    import random

    barras = app.GetCalcRelevantObjects('ElmTerm')
    lineas = app.GetCalcRelevantObjects('ElmLne')
    cargas = app.GetCalcRelevantObjects('ElmLod')

    rnd = random.Random(0)
    m_barras = rnd.sample(barras, min(muestra, len(barras)))
    m_lineas = rnd.sample(lineas, min(muestra, len(lineas)))

    tensiones, sin_resultado = [], 0
    for b in m_barras:
        if not b.HasResults():
            sin_resultado += 1
            continue
        u = b.GetAttribute('m:u')
        if u is None:
            sin_resultado += 1
        else:
            tensiones.append(u)

    carga_pct = []
    for ln in m_lineas:
        if not ln.HasResults():
            continue
        try:
            v = ln.GetAttribute('c:loading')
            if v is not None:
                carga_pct.append(v)
        except Exception:  # noqa: BLE001
            pass

    # Pérdidas totales: las agrega la propia red, sin recorrer tramo a tramo.
    perdidas_kw = 0.0
    for red in app.GetCalcRelevantObjects('ElmNet'):
        for atributo in ('c:LossP', 'c:losses'):
            try:
                v = red.GetAttribute(atributo)
                if v:
                    perdidas_kw += v * (1000.0 if atributo == 'c:LossP' else 1.0)
                    break
            except Exception:  # noqa: BLE001
                continue

    p_total = 0.0
    for c in cargas:
        try:
            if not c.GetAttribute('outserv'):
                p_total += (c.GetAttribute('plini') or 0.0)
        except Exception:  # noqa: BLE001
            pass

    tensiones.sort()
    n = len(tensiones)
    escala = len(barras) / len(m_barras) if m_barras else 1.0
    return {
        'barras': len(barras),
        'barras_muestreadas': len(m_barras),
        'barras_sin_resultado_muestra': sin_resultado,
        'tension_min': tensiones[0] if n else None,
        'tension_p5': tensiones[n // 20] if n else None,
        'tension_mediana': tensiones[n // 2] if n else None,
        'tension_max': tensiones[-1] if n else None,
        'pct_bajo_095': (sum(1 for u in tensiones if u < LIMITE_TENSION_MIN) / n * 100.0) if n else None,
        'pct_bajo_094': (sum(1 for u in tensiones if u < LIMITE_TENSION_RURAL) / n * 100.0) if n else None,
        'pct_sobre_105': (sum(1 for u in tensiones if u > LIMITE_TENSION_MAX) / n * 100.0) if n else None,
        'barras_bajo_095_estimadas': round(sum(1 for u in tensiones if u < LIMITE_TENSION_MIN) * escala),
        'tramos': len(lineas),
        'tramos_muestreados': len(m_lineas),
        'pct_sobre_80': (sum(1 for x in carga_pct if x > LIMITE_CARGABILIDAD) / len(carga_pct) * 100.0) if carga_pct else None,
        'cargabilidad_max_muestra': max(carga_pct) if carga_pct else None,
        'perdidas_kw': perdidas_kw,
        'demanda_mw': p_total,
        'perdidas_pct': (perdidas_kw / 1000.0 / p_total * 100.0) if p_total else None,
    }


def ejecutar_estudios(app, *, saltar: set[str]) -> list[dict]:
    """Ejecuta cada módulo y anota si corrió y si el resultado es defendible."""
    resultados = []
    for estudio in ESTUDIOS:
        if estudio.clave in saltar:
            continue
        fila = {
            'clave': estudio.clave,
            'nombre': estudio.nombre,
            'clase_pf': estudio.clase_pf,
            'capitulo': estudio.capitulo,
            'defendible': estudio.defendible,
            'le_falta': [e.nombre for e in estudio.bloqueantes],
        }
        try:
            orden = app.GetFromStudyCase(estudio.clase_pf)
            if orden is None or orden.GetClassName() != estudio.clase_pf:
                fila.update(ejecutado=False, motivo='la clase no existe en esta versión')
                resultados.append(fila)
                continue
            if estudio.clave == 'flujo_desequilibrado':
                orden.SetAttribute('iopt_net', 1)
            t0 = time.perf_counter()
            rc = orden.Execute()
            fila.update(ejecutado=True, rc=rc, segundos=round(time.perf_counter() - t0, 2))
            if estudio.clave == 'flujo_desequilibrado':
                orden.SetAttribute('iopt_net', 0)
        except Exception as exc:  # noqa: BLE001
            fila.update(ejecutado=False, motivo=str(exc)[:160])
        resultados.append(fila)
    return resultados


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--red')
    p.add_argument('--cargas')
    p.add_argument('--equipos')
    p.add_argument('--mdb')
    p.add_argument('--equipment-mdb')
    p.add_argument('--nombre', default='PIDE_ANIO_0')
    p.add_argument('--out-dir', default='output/anio0')
    p.add_argument('--source-crs', default='EPSG:32718')
    p.add_argument('--sin-geografia', action='store_true')
    p.add_argument('--solo-datos', action='store_true',
                   help='Solo auditar el export y listar lo que falta. No usa PowerFactory.')
    p.add_argument('--sin-estudios', action='store_true',
                   help='Construir y hacer converger, sin ejecutar los demás módulos.')
    args = p.parse_args(argv)

    if not args.mdb and not (args.red and args.cargas and args.equipos):
        p.error('indique --mdb, o bien --red, --cargas y --equipos')

    ds = _cargar_dataset(args)
    salida = Path(args.out_dir)
    salida.mkdir(parents=True, exist_ok=True)

    datos = informe_de_datos(ds)
    if args.solo_datos:
        (salida / 'datos_faltantes.json').write_text(
            json.dumps(datos, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print()
        print(f'Informe: {salida / "datos_faltantes.json"}')
        return 0

    print()
    print('=' * 78)
    print('ESCENARIO BASE — construcción')
    print('=' * 78)
    modelo, informe = build_combined(
        ds, strict=False, include_geography=not args.sin_geografia, name=args.nombre)
    print(informe.text())

    geografia = None
    if not args.sin_geografia:
        from igea_dgs.geography import assert_metre_source_crs, build_geography
        assert_metre_source_crs(args.source_crs)
        geografia = build_geography(ds, modelo, source_crs=args.source_crs)

    dgs = salida / f'{args.nombre}.dgs'
    write_dgs(modelo, dgs, geography=geografia)
    print(f'\nDGS: {dgs}  ({dgs.stat().st_size / 1e6:.1f} MB)')

    try:
        app = _conectar()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    from powerfactory_acceptance import import_dgs_file, run_load_flow_until_converged

    print(f'\nImportando como «{args.nombre}»…')
    import_dgs_file(app, dgs.resolve(), project_name=args.nombre)
    caso = preparar_caso_base(app, args.nombre)
    print(f'Caso de estudio: {caso["caso"]}   escenario: {caso["escenario"]}')

    print('\nFlujo de potencia del año 0…')
    flujo = run_load_flow_until_converged(app)
    if not flujo.get('pass'):
        print('El año 0 NO converge. No se ejecutan los demás estudios.', file=sys.stderr)
        return 5

    estado = medir_estado_base(app)
    print()
    print('=' * 78)
    print('ESTADO DEL AÑO 0')
    print('=' * 78)
    print(f'  Barras                  : {estado["barras"]:,}  '
          f'(muestra de {estado["barras_muestreadas"]:,})')
    if estado['tension_min'] is not None:
        print(f'  Tensión                 : min {estado["tension_min"]:.4f}  '
              f'p5 {estado["tension_p5"]:.4f}  mediana {estado["tension_mediana"]:.4f}  '
              f'max {estado["tension_max"]:.4f} p.u.')
        print(f'  Bajo 0,95 p.u.          : {estado["pct_bajo_095"]:.1f} % de la muestra '
              f'(~{estado["barras_bajo_095_estimadas"]:,} barras)')
        print(f'  Bajo 0,94 p.u.          : {estado["pct_bajo_094"]:.1f} %  '
              f'(límite del TdR en zona rural: 6 % de caída)')
        print(f'  Sobre 1,05 p.u.         : {estado["pct_sobre_105"]:.1f} %')
    if estado['cargabilidad_max_muestra'] is not None:
        print(f'  Cargabilidad            : máx {estado["cargabilidad_max_muestra"]:.1f} %  '
              f'({estado["pct_sobre_80"]:.1f} % de los tramos sobre el 80 %)')
    print(f'  Demanda                 : {estado["demanda_mw"]:.2f} MW')
    if estado['perdidas_pct'] is not None:
        print(f'  Pérdidas en líneas MT   : {estado["perdidas_kw"]:,.1f} kW  '
              f'({estado["perdidas_pct"]:.2f} % de la demanda)')

    estudios = []
    if not args.sin_estudios:
        print()
        print('=' * 78)
        print('ESTUDIOS DEL MÓDULO DE DIGSILENT')
        print('=' * 78)
        estudios = ejecutar_estudios(app, saltar={'flujo'})
        for f in estudios:
            if not f.get('ejecutado'):
                marca, detalle = 'NO CORRE ', f.get('motivo', '')
            elif f.get('rc') != 0:
                marca, detalle = 'rc!=0    ', f'código {f.get("rc")}'
            elif f['defendible']:
                marca, detalle = 'OK       ', f'{f.get("segundos")} s'
            else:
                marca, detalle = 'SIN DATOS', 'corre, pero el resultado no significa nada'
            print(f'  [{marca}] {f["nombre"]:40s} {detalle}')
            if f['le_falta'] and f.get('ejecutado'):
                print(f'             le falta: {", ".join(f["le_falta"])}')

    informe_json = salida / 'anio0_diagnostico.json'
    informe_json.write_text(json.dumps({
        'proyecto': args.nombre,
        'caso': caso,
        'construccion': {
            'alimentadores': informe.feeders,
            'nodos': informe.nodes_out,
            'tramos': informe.lines,
            'cargas': informe.loads,
            'seds': informe.seds,
            'enlaces_abiertos': informe.tie_switches,
            'fuera_de_servicio_nodos': informe.de_energised_nodes,
            'tensiones': {str(k): v for k, v in informe.voltages.items()},
        },
        'estado': estado,
        'estudios': estudios,
        'datos': datos,
    }, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print()
    print(f'Diagnóstico completo: {informe_json}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
