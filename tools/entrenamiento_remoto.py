"""Entrenar en Colab Pro como opción del entrenamiento local: preparar el paquete y traer los candidatos (spec 113).

Uso:
    python tools/entrenamiento_remoto.py opciones
    python tools/entrenamiento_remoto.py preparar --familia asistente_redaccion --dataset CARPETA [--drive CARPETA]
    python tools/entrenamiento_remoto.py traer [--drive CARPETA] [--destino CARPETA]

`preparar` deja el dataset, con su manifiesto y sin datos crudos ni conjuntos sellados, en la carpeta de Google Drive de
escritorio (`G:/Mi unidad/ConverterSmartGrid/colab`, o `CSG_DRIVE_COLAB`), y escribe el enlace de Colab del cuaderno en
la revisión exacta; avisa si hay cambios sin commit o si la revisión no está en GitHub, porque Colab no los vería.
`traer` copia a local los candidatos que cuadran (revisión, huellas y paquete) sin activarlos y dice la orden de su
puerta: la misma que examina lo entrenado en este equipo. Nada de esto es necesario para entrenar aquí (113:RF-16).

Códigos de salida: 0 hecho; 2 rechazado (paquete prohibido o candidatos que no cuadran); 1 error de uso o de E/S.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(['git', '-C', str(RAIZ), *args], capture_output=True, text=True, check=False).stdout


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='entrenamiento_remoto',
                                description='Entrenar en Colab Pro como opción del local (spec 113).')
    sub = p.add_subparsers(dest='orden', required=True)
    sub.add_parser('opciones', help='dónde se puede entrenar ahora')
    pr = sub.add_parser('preparar', help='deja el paquete del dataset en Drive y da el enlace de Colab')
    pr.add_argument('--familia', required=True, help='familia del modelo (p. ej. asistente_redaccion)')
    pr.add_argument('--dataset', type=Path, required=True, help='carpeta del dataset ya construido en local')
    pr.add_argument('--drive', type=Path, help='carpeta de Drive para Colab; por defecto la de escritorio')
    tr = sub.add_parser('traer', help='trae de Drive los candidatos que cuadran, sin activarlos')
    tr.add_argument('--drive', type=Path, help='carpeta de Drive para Colab; por defecto la de escritorio')
    tr.add_argument('--destino', type=Path, help='carpeta local; por defecto «colab/traidos» del almacén del asistente')
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = _argumentos(argv)
    from convertersmartgrid.aplicacion import entrenamiento_remoto as er

    drive = getattr(a, 'drive', None) or er.carpeta_drive()
    if a.orden == 'opciones':
        print(json.dumps(er.opciones_de_entrenamiento(drive), ensure_ascii=False, indent=2))
        return 0
    if drive is None:
        print('Sin carpeta de Google Drive para Colab: entrena en este equipo, o instala Drive para escritorio o '
              f'pon {er.VARIABLE_DRIVE}.', file=sys.stderr)
        return 1
    revision = _git('rev-parse', 'HEAD').strip()
    if a.orden == 'preparar':
        cambios = er.cambios_sin_commit(_git('status', '--porcelain'))
        if cambios:
            print(f'Aviso: {len(cambios)} ficheros con cambios sin commit; Colab clona {revision[:8]} y no los verá '
                  f'(p. ej. {", ".join(cambios[:3])}).', file=sys.stderr)
        if not _git('branch', '-r', '--contains', revision).strip():
            print(f'Aviso: {revision[:8]} no está en GitHub; súbelo antes de abrir Colab.', file=sys.stderr)
        try:
            repositorio = er.repositorio_de(_git('remote', 'get-url', 'origin'))
            m = er.preparar_paquete(a.dataset, familia=a.familia, revision=revision, destino=drive / 'paquetes',
                                    repositorio=repositorio)
        except er.PaqueteProhibido as e:
            print(str(e), file=sys.stderr)
            return 2
        except (OSError, ValueError) as e:
            print(f'No se preparó el paquete: {e}', file=sys.stderr)
            return 1
        from convertersmartgrid.aplicacion.asistente import almacen
        er.registrar_preparado(almacen.raiz() / 'colab' / er.REGISTRO_PREPARADOS, familia=a.familia, origen=a.dataset,
                               ejemplos=er.ejemplos_de(a.dataset), huella=m['huella'])
        print(json.dumps({'paquete': f'{a.familia}_{revision[:8]}_{m["huella"][:8]}', 'huella': m['huella'],
                          'ficheros': len(m['ficheros']), 'anonimizacion': m['anonimizacion']['modo'],
                          'carpeta': str(drive / 'paquetes'),
                          'colab': er.url_colab(revision, repositorio=repositorio)},
                         ensure_ascii=False, indent=2))
        return 0
    if a.destino is None:
        from convertersmartgrid.aplicacion.asistente import almacen
        a.destino = almacen.raiz() / 'colab' / 'traidos'
    resultados = er.traer_candidatos(drive / 'candidatos', a.destino, revision=revision,
                                     paquetes=er.paquetes_de(drive / 'paquetes'))
    print(json.dumps(resultados, ensure_ascii=False, indent=2))
    return 2 if any(not r['aceptado'] for r in resultados) else 0


if __name__ == '__main__':
    raise SystemExit(main())
