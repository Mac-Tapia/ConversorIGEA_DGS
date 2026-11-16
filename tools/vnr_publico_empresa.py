"""Baja bajo demanda el paquete VNR-GIS vigente de UNA empresa, de lo publicado por Osinergmin (spec 112, T14).

Uso:
    python tools/vnr_publico_empresa.py --empresa "Nombre de la empresa" --destino CARPETA_ABSOLUTA [--plan]
        [--catalogo CARPETA_DEL_CATALOGO]

Primero lee el catálogo oficial de publicaciones del VNR (páginas de Osinergmin) y elige el paquete vigente de esa
empresa por su resolución. Con ``--plan`` solo dice qué bajaría, de qué URL y adónde. Sin él, lo baja con el gestor de
descargas del VNR (solo hosts de Osinergmin, SHA-256 y manifiesto). El destino tiene que ser una carpeta absoluta fuera
del programa y de sus datos locales, para que el paquete no entre en el corpus ni en los datasets del asistente
(112:RF-14). Nada masivo: una empresa cada vez. No necesita DIgSILENT. No ejecuta nada de lo que trae el paquete.

Después, el paquete se convierte con ``vnr-etl`` al trío TXT de CYMDIST, y ese trío es la geometría pública que se pasa a
``tools/benchmark_anonimo.py --geometria-publica``.

Códigos de salida: 0 hecho; 2 la empresa no tiene paquete vigente o la descarga falló; 1 error de uso.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='vnr_publico_empresa',
                                description='Paquete VNR-GIS vigente de una empresa, bajado bajo demanda (spec 112).')
    p.add_argument('--empresa', required=True, help='nombre de la empresa como lo publica Osinergmin')
    p.add_argument('--destino', type=Path, required=True,
                   help='carpeta absoluta fuera del programa y de sus datos locales')
    p.add_argument('--plan', action='store_true', help='solo dice qué bajaría, de dónde y adónde')
    p.add_argument('--catalogo', type=Path, help='carpeta del catálogo de publicaciones; por defecto, junto al destino')
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import DownloadError
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.official import refresh_official_catalog
    from convertersmartgrid.benchmarks.geometria_publica import DestinoNoPermitido, comprobar_destino, descargar, \
        plan_descarga

    try:
        destino = comprobar_destino(args.destino)
        catalogo_dir = args.catalogo or destino / 'catalogo'
        catalogo, informe = refresh_official_catalog(catalogo_dir)
        for error in informe.get('errors', []):
            print(f'Aviso: no se pudo leer {error["page"]}: {error["error"]}', file=sys.stderr)
        plan = plan_descarga(args.empresa, destino, catalogo.publications())
    except DestinoNoPermitido as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    except LookupError as exc:
        print(f'No se baja nada: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.plan:
        return 0
    try:
        manifiesto = descargar(plan)
    except (DownloadError, OSError, ValueError) as exc:
        print(f'La descarga falló: {exc}', file=sys.stderr)
        return 2
    print(f'Bajado {Path(plan["destino"]).name}: sha256 {str(manifiesto.get("sha256", ""))[:12]}…')
    return 0


if __name__ == '__main__':
    sys.exit(main())
