"""Genera un informe de la spec 017 desde la línea de órdenes, por la web (RF-105).

Cada informe que genera la página deja su plan junto al Word (``<informe>.plan.json``, con
el tipo y el formulario tal como lo envió la página). Esta herramienta lo envía a la misma
API, espera el trabajo y descarga el Word: el operador repite un informe —por ejemplo tras
volver a correr los estudios de 4.2— sin escribir de nuevo el formulario. Va por la web, no
por su cuenta, porque el informe se arma con lo que el espacio guardó al ejecutar los casos.

    python tools/informe_web.py --espacio 5f11283a33c94ea5 --plan informe_estudio_SM218_x.plan.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sistema_web import Web  # noqa: E402  (herramienta vecina: su cliente ya reintenta)

TIPOS = ('estudio', 'factibilidad')


def leer_plan(ruta: Path, tipo: str | None = None) -> tuple[str, dict]:
    """(tipo, formulario) del plan. Admite el plan que guarda la web (``{tipo, formulario}``)
    o el formulario solo, con ``tipo`` indicado aparte."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'No se pudo leer el plan {ruta}: {exc}') from exc
    if not isinstance(datos, dict):
        raise ValueError('El plan tiene que ser un objeto JSON.')
    if 'formulario' in datos:
        tipo = tipo or datos.get('tipo')
        datos = datos['formulario']
    if tipo not in TIPOS:
        raise ValueError(f'Indique el tipo de informe ({" o ".join(TIPOS)}) con --tipo.')
    if not isinstance(datos, dict) or not datos.get('project'):
        raise ValueError('El formulario del plan no dice el proyecto («project»).')
    return tipo, datos


def generar(web, tipo: str, formulario: dict, salida: Path) -> dict:
    """Envía el plan, espera el trabajo y descarga el Word; devuelve el resultado del trabajo."""
    trabajo = web.post(f'/informes/{tipo}', json=formulario)
    estado = web.esperar(trabajo)
    if estado.get('status') != 'done':
        raise RuntimeError(f"El informe no se generó ({estado.get('status')}): {estado.get('error') or ''}")
    resultado = estado.get('result') or {}
    salida.mkdir(parents=True, exist_ok=True)
    for clave in ('informe', 'plan'):
        nombre = resultado.get(clave)
        if nombre:
            (salida / nombre).write_bytes(web.descargar(nombre))
    return resultado


class WebConDescarga(Web):
    """El cliente de ``sistema_web.py`` y la descarga de un fichero del espacio."""

    def descargar(self, nombre: str) -> bytes:
        r = self.http.get(f'{self.url}/api/workspaces/{self.espacio}/files/{quote(nombre)}?download=1',
                          timeout=300)
        r.raise_for_status()
        return r.content


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Genera un informe de estudio o de factibilidad por la web '
                                            'con el plan que guardó la página (spec 017, RF-105)')
    p.add_argument('--espacio', required=True, help='Id del espacio de trabajo de la web')
    p.add_argument('--plan', type=Path, required=True,
                   help='El «.plan.json» que la web dejó junto al Word, o un formulario JSON')
    p.add_argument('--tipo', choices=TIPOS, help='Solo si el plan es un formulario sin su tipo')
    p.add_argument('--salida', type=Path, default=Path('.'), help='Carpeta donde dejar el Word')
    p.add_argument('--url', default='http://127.0.0.1:8765', help='Dirección de la web')
    args = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    try:
        tipo, formulario = leer_plan(args.plan, args.tipo)
        resultado = generar(WebConDescarga(args.url, args.espacio), tipo, formulario, args.salida)
    except (ValueError, RuntimeError, TimeoutError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(f"Informe de {tipo}: {args.salida / resultado['informe']}")
    if resultado.get('factible') is not None:
        print('Factible.' if resultado['factible'] else f"No factible: {'; '.join(resultado.get('excesos') or [])}.")
    for hueco in resultado.get('huecos') or []:
        print(f'  hueco: {hueco}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
