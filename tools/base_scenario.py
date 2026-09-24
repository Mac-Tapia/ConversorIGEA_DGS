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
    PESADO,
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

GUION_TRABAJADOR = Path(__file__).resolve().parent / 'run_one_study.py'


def _trabajador(argumentos: list[str], *, limite_s: float) -> dict:
    """Lanza el trabajador de PowerFactory y devuelve su JSON.

    El orquestador **no toca la API**. PowerFactory solo admite un proceso con el motor
    a la vez: mientras este mantenía la conexión para importar, cada estudio lanzado
    como hijo recibía «PowerFactory no respondió» y el informe salía entero en blanco.
    """
    import subprocess

    orden = [sys.executable, str(GUION_TRABAJADOR)] + argumentos
    try:
        proc = subprocess.run(
            orden, capture_output=True, text=True, timeout=limite_s, check=False,
            encoding='utf-8', errors='replace',
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'agotado': True,
                'motivo': f'superó el límite de {limite_s:.0f} s'}
    lineas = [x for x in (proc.stdout or '').strip().splitlines() if x.startswith('{')]
    if not lineas:
        detalle = ((proc.stderr or '') + (proc.stdout or '')).strip()[-200:]
        return {'ok': False, 'motivo': f'sin respuesta del trabajador: {detalle}'}
    try:
        return json.loads(lineas[-1])
    except json.JSONDecodeError as exc:
        return {'ok': False, 'motivo': f'salida ilegible: {exc}'}


def ejecutar_estudios(
    proyecto: str, *, incluir_pesados: bool, limite_s: float, saltar: set[str],
) -> list[dict]:
    """Ejecuta cada módulo en su propio proceso, con presupuesto de tiempo.

    ``Execute()`` es bloqueante y no se puede interrumpir desde el mismo hilo. Aislarlo
    es lo que permite ponerle límite: si el análisis de contingencias sobre 53.000
    barras no termina, cuesta ese estudio y no el informe entero. Antes, un cuelgue de
    más de una hora se llevó por delante todo lo que faltaba.

    Que un estudio agote el presupuesto **es un resultado**, no un fallo del programa:
    un cálculo que no cabe en un tiempo razonable no sirve para un ciclo de
    planificación, y el informe lo dice con el número delante.
    """
    resultados: list[dict] = []
    for estudio in ESTUDIOS:
        if estudio.clave in saltar:
            continue
        fila = {
            'clave': estudio.clave, 'nombre': estudio.nombre,
            'clase_pf': estudio.clase_pf, 'capitulo': estudio.capitulo,
            'coste': estudio.coste, 'defendible': estudio.defendible,
            'le_falta': [e.nombre for e in estudio.bloqueantes],
        }
        if estudio.coste == PESADO and not incluir_pesados:
            fila.update(ejecutado=False, motivo='pesado; use --pesados')
            resultados.append(fila)
            continue

        argumentos = ['--project', proyecto, '--clase', estudio.clase_pf]
        if estudio.clave == 'flujo_desequilibrado':
            argumentos.append('--desequilibrado')
        presupuesto = limite_s if estudio.coste == PESADO else max(limite_s, 180.0)
        datos = _trabajador(argumentos, limite_s=presupuesto)
        fila.update(
            ejecutado=bool(datos.get('ok')),
            **{k: v for k, v in datos.items()
               if k in ('rc', 'segundos', 'errores', 'motivo', 'agotado')},
        )
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
    p.add_argument('--pesados', action='store_true',
                   help='Incluir los estudios que resuelven la red muchas veces '
                        '(N-1, fiabilidad, optimizaciones). Pueden tardar mucho.')
    p.add_argument('--limite-importacion', type=float, default=1800.0,
                   help='Presupuesto para importar y hacer converger el año 0.')
    p.add_argument('--limite-segundos', type=float, default=300.0,
                   help='Presupuesto por estudio. Al agotarse se pasa al siguiente.')
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

    print(f'\nImportando y haciendo converger como «{args.nombre}»…')
    datos = _trabajador(
        ['--project', args.nombre, '--importar', str(dgs.resolve()),
         '--caso', CASO_BASE, '--escenario', ESCENARIO_BASE],
        limite_s=args.limite_importacion,
    )
    if not datos.get('ok'):
        print(f'No se pudo preparar el año 0: {datos.get("motivo")}', file=sys.stderr)
        return 3
    if not datos.get('converge'):
        print('El año 0 NO converge. No se ejecutan los demás estudios.', file=sys.stderr)
        return 5
    caso = {'caso': datos.get('caso'), 'escenario': datos.get('escenario')}
    estado = datos['estado']
    print(f'Caso de estudio: {caso["caso"]}   escenario: {caso["escenario"]}')

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
    print(f'  Clientes en el modelo   : {estado.get("clientes_en_el_modelo", 0):,}  '
          f'(denominador de SAIFI y SAIDI)')

    estudios = []
    if not args.sin_estudios:
        print()
        print('=' * 78)
        print('ESTUDIOS DEL MÓDULO DE DIGSILENT')
        print('=' * 78)
        print(f'Cada estudio corre en su propio proceso, con {args.limite_segundos:.0f} s '
              f'de presupuesto.')
        if not args.pesados:
            print('Los que resuelven la red muchas veces quedan fuera; use --pesados.')
        print()
        estudios = ejecutar_estudios(
            args.nombre, incluir_pesados=args.pesados,
            limite_s=args.limite_segundos, saltar={'flujo'})
        for f in estudios:
            if f.get('agotado'):
                marca, detalle = 'SIN TIEMPO', f.get('motivo', '')
            elif not f.get('ejecutado'):
                marca, detalle = 'NO CORRE  ', f.get('motivo', '')
            elif f.get('rc') != 0:
                marca, detalle = 'rc!=0     ', f'código {f.get("rc")}, {f.get("segundos")} s'
            elif f['defendible']:
                marca, detalle = 'OK        ', f'{f.get("segundos")} s'
            else:
                marca, detalle = 'SIN DATOS ', f'{f.get("segundos")} s — corre, pero el resultado no significa nada'
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
