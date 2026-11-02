"""Genera o comprueba el contrato TypeScript desde el OpenAPI real de la aplicación.

Uso: python -B tools/generar_contrato_api.py [--check].
Requiere npm ci en frontend; usa exclusivamente openapi-typescript del lock local.
El servidor no arranca, no invoca motores ni consulta espacios del operador.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def esquema_publico(raiz: Path, datos: Path) -> dict:
    """Construye rutas sin lifespan ni lectura de los espacios reales del usuario."""
    sys.path.insert(0, str(raiz / 'src'))
    from convertersmartgrid.web.app import create_app

    return create_app(datos).openapi()


def generar(esquema: dict, raiz: Path, temporal: Path) -> str:
    """Ejecuta el generador fijado y liga los bytes al esquema completo mediante SHA-256."""
    node = shutil.which('node')
    paquete = raiz / 'frontend/node_modules/openapi-typescript'
    manifest = raiz / 'frontend/package.json'
    if not node or not (paquete / 'bin/cli.js').is_file():
        raise RuntimeError('Falta Node o openapi-typescript local; ejecute npm ci en frontend.')
    esperado = json.loads(manifest.read_text(encoding='utf-8'))['devDependencies']['openapi-typescript']
    instalado = json.loads((paquete / 'package.json').read_text(encoding='utf-8'))['version']
    if esperado != instalado:
        raise RuntimeError(f'openapi-typescript instalado {instalado}; el contrato exige {esperado}.')
    temporal.mkdir(parents=True, exist_ok=True)
    canonico = json.dumps(esquema, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n'
    entrada, salida = temporal / 'openapi.json', temporal / 'esquema.ts'
    entrada.write_text(canonico, encoding='utf-8', newline='\n')
    resultado = subprocess.run(
        [node, str(paquete / 'bin/cli.js'), './openapi.json', '--output', './esquema.ts',
         '--alphabetize'],
        cwd=temporal, capture_output=True, encoding='utf-8', timeout=120,
    )
    if resultado.returncode:
        raise RuntimeError(resultado.stdout + resultado.stderr)
    huella = hashlib.sha256(canonico.encode('utf-8')).hexdigest()
    cabecera = ('// Generado por tools/generar_contrato_api.py; no editar.\n'
                f'// OpenAPI SHA-256: {huella}; openapi-typescript {instalado}.\n')
    return cabecera + salida.read_text(encoding='utf-8').replace('\r\n', '\n')


def comprobar(generado: str, destino: Path) -> list[str]:
    """Una deriva requiere regeneración deliberada, nunca se corrige al comprobar."""
    if not destino.is_file():
        return [f'No existe el contrato generado: {destino}']
    if generado != destino.read_text(encoding='utf-8'):
        return ['El contrato API diverge; ejecute tools/generar_contrato_api.py y revise el diff.']
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Comprueba sin modificar tipos publicados')
    parser.add_argument('--raiz', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.raiz / 'src'))
    from convertersmartgrid.runtime_paths import temporal_administrado, rutas_runtime

    destino = args.raiz / 'frontend/src/api/esquema.ts'
    with temporal_administrado(rutas_runtime(args.raiz), propietario='contrato-api') as temporal:
        generado = generar(esquema_publico(args.raiz, temporal / 'web'), args.raiz, temporal)
    if args.check:
        errores = comprobar(generado, destino)
        for error in errores:
            print(error)
        if not errores:
            print('Contrato API sin deriva.')
        return int(bool(errores))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(generado, encoding='utf-8', newline='\n')
    print(f'Contrato generado: {destino}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
