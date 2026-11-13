"""Copia y restauración de los datos del conversor, con manifiesto (spec 086, RF-7, RF-10, RF-47).

Uso:
  python tools/copia_datos.py calcular --destino E:/copias [--sin-modelos]
  python tools/copia_datos.py crear --destino E:/copias [--sin-modelos] [--forzar] [--programa D:/otra/instalacion]
  python tools/copia_datos.py verificar --copia E:/copias/csg-copia-...
  python tools/copia_datos.py restaurar --copia E:/copias/csg-copia-... [--raiz-datos D:/otra/web]
  python tools/copia_datos.py estado
  python tools/copia_datos.py identidad [--fijar]

Restaurar comprueba cada huella antes de tocar nada y aparta lo que hubiera, sin borrarlo. Con la web
en marcha o con trabajos a medias se niega salvo con ``--forzar``: la web guarda sus espacios en
memoria, y al guardar pisaría lo restaurado. ``identidad --fijar`` deja escrita la identidad antes de
renombrar la carpeta, para no depender de que la web haya arrancado una vez con este código.

Cada fichero físico se guarda una vez, aunque tenga varios nombres por enlaces duros o el mismo contenido
(086:RF-78 a RF-80). Antes de escribir, ``crear`` dice cuánto ocupará y cuánto hay libre, y no empieza si no
cabe (RF-83); ``calcular`` lo dice sin copiar. Un destino que sincroniza (Google Drive, OneDrive) se escribe
fichero a fichero con reintentos (RF-81). Con la web en marcha avisa: no lance trabajos mientras se copia.

Códigos de salida: 0 bien, 1 error o copia no válida, 2 copia hecha con errores.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))


def _web_escuchando(puerto: int) -> bool:
    with socket.socket() as conexion:
        conexion.settimeout(0.5)
        return conexion.connect_ex(('127.0.0.1', puerto)) == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    orden = parser.add_subparsers(dest='orden', required=True)
    crear = orden.add_parser('crear', help='Copia los datos a una carpeta, con su manifiesto.')
    calcular = orden.add_parser('calcular', help='Cuánto ocupará la copia y cuánto hay libre, sin copiar.')
    for sub in (crear, calcular):
        sub.add_argument('--destino', type=Path, required=True)
        sub.add_argument('--sin-modelos', action='store_true', help='Sin los pesos de los modelos, que pesan mucho.')
        sub.add_argument('--raiz-datos', type=Path, help='Otra carpeta de espacios en lugar de la de esta instalación.')
        sub.add_argument('--programa', type=Path,
                         help='La instalación cuyos datos se copian, si no es la de esta orden (otro árbol).')
    crear.add_argument('--forzar', action='store_true', help='Aunque haya trabajos a medias.')
    crear.add_argument('--puerto', type=int, default=8765, help='Puerto donde se mira si la web está en marcha.')
    verificar = orden.add_parser('verificar', help='Comprueba cada fichero contra su huella.')
    verificar.add_argument('--copia', type=Path, required=True)
    restaurar = orden.add_parser('restaurar', help='Devuelve los datos al estado de la copia.')
    restaurar.add_argument('--copia', type=Path, required=True)
    restaurar.add_argument('--raiz-datos', type=Path, help='Restaurar en otra carpeta de espacios, para ensayar.')
    restaurar.add_argument('--puerto', type=int, default=8765, help='Puerto donde se mira si la web está en marcha.')
    restaurar.add_argument('--forzar', action='store_true', help='Aunque la web esté en marcha.')
    orden.add_parser('estado', help='Cuándo fue la última copia y si toca avisar.')
    identidad = orden.add_parser('identidad', help='La identidad estable de esta instalación.')
    identidad.add_argument('--fijar', action='store_true', help='La deja escrita si aún no lo está.')
    args = parser.parse_args(argv)

    from convertersmartgrid.runtime_paths import fijar_identidad, rutas_runtime
    from convertersmartgrid.web import copia_datos as copia
    from convertersmartgrid.web.workspace import data_root

    def salida(datos) -> None:
        print(json.dumps(datos, indent=2, ensure_ascii=False))

    try:
        if args.orden in ('crear', 'calcular'):
            raices = ({'datos': args.raiz_datos} if args.raiz_datos
                      else copia.raices_de_datos(args.programa.resolve() if args.programa else None))
            if args.orden == 'calcular':
                plan = copia.planificar_copia(args.destino, raices=raices, sin_modelos=args.sin_modelos)
                print(copia.texto_plan(plan), file=sys.stderr)
                salida(plan)
                return 0 if plan['cabe'] else 1
            en_marcha = copia.trabajos_en_marcha(raices['datos'])
            if en_marcha and not args.forzar:
                print(f'Hay trabajos a medias: {en_marcha}. Espere o use --forzar.', file=sys.stderr)
                return 1
            if _web_escuchando(args.puerto):
                print(f'Aviso: la web está en marcha en el puerto {args.puerto}. No lance trabajos mientras se copia.',
                      file=sys.stderr)
            manifiesto = copia.crear_copia(
                args.destino, raices=raices, sin_modelos=args.sin_modelos,
                avisar=lambda plan: print(copia.texto_plan(plan), file=sys.stderr, flush=True))
            salida({k: manifiesto[k] for k in ('ruta', 'bytes_total', 'bytes_logicos', 'nombres', 'errores',
                                                'rutas_externas_sin_copiar')}
                   | {'ficheros': len(manifiesto['ficheros']), 'omitidos': len(manifiesto['omitidos'])})
            return 2 if manifiesto['errores'] else 0
        if args.orden == 'verificar':
            resultado = copia.verificar_copia(args.copia)
            salida(resultado)
            return 0 if resultado['ok'] else 1
        if args.orden == 'restaurar':
            # Con otra carpeta es un ensayo, y la web de esta instalación no la tiene abierta.
            if not args.raiz_datos and not args.forzar and _web_escuchando(args.puerto):
                print(f'La web está en marcha en el puerto {args.puerto}: párela o use --forzar.', file=sys.stderr)
                return 1
            raices = {**copia.raices_de_datos(), 'datos': args.raiz_datos} if args.raiz_datos else None
            salida(copia.restaurar_copia(args.copia, raices=raices))
            return 0
        if args.orden == 'estado':
            salida(copia.estado_copia(data_root()))
            return 0
        if args.fijar:
            fijar_identidad(rutas_runtime())
        salida(copia.identidad_instalacion())
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
