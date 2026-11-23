"""Genera en local un benchmark anonimizado de una red (y de sus series del 089) para comparar métodos (spec 112).

Uso:
    python tools/benchmark_anonimo.py --red RED.txt --carga CARGA.txt --equipo BD_Equipo.txt --destino CARPETA
        [--dataset-089 CARPETA_089] [--perfil perfil_empresa.json] [--tolerancia tolerancia.json]
        [--carpeta-semilla CARPETA] [--geometria-publica CARPETA_DEL_TRIO_DEL_VNR]

Todo corre en esta máquina: no abre la red ni llama a ningún servicio (112:RF-1). La semilla de los seudónimos se sortea
y se guarda solo en la carpeta local de la instalación; el manifiesto lleva la pública (RF-12). El benchmark derivado de
una red real es de uso local (aclaración de RF-13 y RF-14). Si el estudio no se reproduce o el control encuentra una
fuga, no se emite nada y se dice por qué. No necesita DIgSILENT.

Códigos de salida: 0 emitido; 2 no se emite (fuga o sin reproducir); 1 error de uso o de E/S.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='benchmark_anonimo',
                                description='Benchmark anonimizado y reproducible de una red, en local (spec 112).')
    p.add_argument('--red', type=Path, required=True, help='RED de los TXT')
    p.add_argument('--carga', type=Path, required=True, help='CARGA de los TXT')
    p.add_argument('--equipo', type=Path, required=True, help='BD_Equipo de los TXT')
    p.add_argument('--destino', type=Path, required=True, help='carpeta nueva donde se emite el benchmark')
    p.add_argument('--dataset-089', type=Path, help='carpeta del dataset de pronóstico del 089, si se quieren series')
    p.add_argument('--perfil', type=Path, help='perfil de empresa (JSON); por defecto, el perfil activo')
    p.add_argument('--tolerancia', type=Path, help='JSON con v_pu, corriente_rel, metrica_rel y fuente del estudio')
    p.add_argument('--carpeta-semilla', type=Path,
                   help='carpeta local donde se guarda la semilla secreta; por defecto, la de la instalación')
    p.add_argument('--geometria-publica', type=Path,
                   help='carpeta con el trío TXT de la red publicada en el VNR-GIS (tools/vnr_publico_empresa.py)')
    return p.parse_args(argv)


def _trio(carpeta: Path | None) -> list[Path] | None:
    if carpeta is None:
        return None
    trio = [carpeta / n for n in ('RED.txt', 'CARGA.txt', 'BD_Equipo.txt')]
    faltan = [p.name for p in trio if not p.is_file()]
    if faltan:
        raise FileNotFoundError(f'a la geometría pública le falta {", ".join(faltan)}')
    return trio


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    from convertersmartgrid.adaptadores.benchmarks import generar_benchmark
    from convertersmartgrid.adaptadores.benchmarks.reidentificacion import FugaDetectada
    from convertersmartgrid.adaptadores.benchmarks.reproduccion import ReproduccionFallida
    from convertersmartgrid.dominio.perfil_empresa import PerfilError, cargar_perfil, ruta_perfil_activo

    for ruta in (args.red, args.carga, args.equipo):
        if not ruta.is_file():
            print(f'No existe {ruta.name}.', file=sys.stderr)
            return 1
    try:
        ruta_perfil = args.perfil or ruta_perfil_activo()
        perfil = cargar_perfil(ruta_perfil)
        tolerancia = json.loads(args.tolerancia.read_text(encoding='utf-8')) if args.tolerancia else None
        manifiesto = generar_benchmark(args.red, args.carga, args.equipo, args.destino,
                                       dataset_089=args.dataset_089, perfil=perfil,
                                       ruta_perfil=ruta_perfil if ruta_perfil.is_file() else None,
                                       tolerancia=tolerancia, raiz=args.carpeta_semilla,
                                       geometria_publica=_trio(args.geometria_publica))
    except (FugaDetectada, ReproduccionFallida) as exc:
        print(f'No se emite el benchmark: {exc}', file=sys.stderr)
        return 2
    except (OSError, ValueError, PerfilError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    print(f'Benchmark emitido en {args.destino.name}: {len(manifiesto["ficheros"])} ficheros, '
          f'huella del origen {manifiesto["origen"]["huella"][:12]}…, uso local.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
