"""Rutas de la API sin modelo de respuesta, con una lista que solo baja (002:RF-38; H13, auditoría del 2026-11-14).

La 002 T10 se cerró el 2026-11-03 con «quedan 7 de 133 rutas de /api sin modelo» y nada impedía que crecieran. Esta
herramienta lista las de ``/api`` sin ``response_model`` (salvo las que declaran que devuelven HTML, un fichero o un flujo,
o responden 204) y escribe la lista que la prueba usa como tope. La cifra la da esa lista, no un número del texto
(aclaración de RF-38): cada ruta lleva su motivo, y la lista solo baja.

Uso:
    python tools/rutas_sin_modelo.py              # lista las rutas sin modelo
    python tools/rutas_sin_modelo.py --escribir   # rehace docs/architecture/rutas_sin_modelo.json: solo quita rutas

No necesita DIgSILENT ni red: crea la aplicación sobre una carpeta temporal.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LISTA = RAIZ / 'docs' / 'architecture' / 'rutas_sin_modelo.json'
#: Respuestas que no son JSON: no llevan modelo de respuesta y no cuentan.
CLASES_SIN_MODELO = ('HTMLResponse', 'FileResponse', 'StreamingResponse', 'PlainTextResponse', 'RedirectResponse')


def rutas_sin_modelo(app) -> list[str]:
    """«MÉTODO /ruta» de cada ruta de ``/api`` sin ``response_model`` que devuelve JSON, en orden estable."""
    from fastapi.routing import APIRoute

    salida = set()
    for r in app.routes:
        if not isinstance(r, APIRoute) or not r.path.startswith('/api') or r.response_model is not None:
            continue
        clase = getattr(r.response_class, '__name__', '')
        if clase in CLASES_SIN_MODELO or (r.status_code or 200) == 204:
            continue
        for metodo in sorted(r.methods or ()):
            salida.add(f'{metodo} {r.path}')
    return sorted(salida)


def de_la_aplicacion() -> list[str]:
    """Crea la aplicación sobre una carpeta temporal y devuelve sus rutas sin modelo."""
    sys.path.insert(0, str(RAIZ / 'src'))
    from convertersmartgrid.web.app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        return rutas_sin_modelo(create_app(Path(tmp) / 'web'))


def leer_lista(ruta: Path | None = None) -> dict[str, str]:
    """La lista guardada, ``{"MÉTODO /ruta": "motivo"}``. ``ValueError`` con un mensaje claro si falta o está rota."""
    ruta = LISTA if ruta is None else ruta
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError(f'{ruta.name} no existe: créela con «tools/rutas_sin_modelo.py --escribir»') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'{ruta.name} no es JSON válido: {exc}') from exc
    rutas = datos.get('rutas') if isinstance(datos, dict) else None
    if not isinstance(rutas, dict):
        raise ValueError(f'{ruta.name}: «rutas» tiene que ser un objeto {{"MÉTODO /ruta": "motivo"}}')
    sin_motivo = sorted(r for r, m in rutas.items() if not isinstance(m, str))
    if sin_motivo:
        raise ValueError(f'{ruta.name}: estas rutas no llevan su motivo como texto: {sin_motivo}')
    return dict(rutas)


def lista_nueva(medidas: list[str], anterior: dict[str, str]) -> dict[str, str]:
    """La lista que corresponde a lo medido, con los motivos de antes. Solo baja: una ruta medida que no estaba es un
    ``ValueError``, porque esa ruta tiene que llevar su modelo de respuesta (002:RF-38)."""
    nuevas = sorted(set(medidas) - set(anterior))
    if nuevas:
        raise ValueError(f'rutas de /api sin response_model que no estaban en la lista; póngales su modelo, la lista solo '
                         f'baja: {nuevas}')
    return {r: anterior[r] for r in sorted(set(medidas))}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--escribir', action='store_true', help=f'rehace {LISTA.name}: solo quita rutas, nunca añade')
    args = p.parse_args(argv)
    rutas = de_la_aplicacion()
    if args.escribir:
        try:
            nueva = lista_nueva(rutas, leer_lista(LISTA))
        except ValueError as exc:
            print(f'No se escribe {LISTA.name}: {exc}', file=sys.stderr)
            return 1
        LISTA.write_text(json.dumps({'_comentario': '002:RF-38: rutas de /api sin response_model, cada una con su motivo; '
                                                    'esta lista solo baja.', 'rutas': nueva},
                                    ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'Escrito {LISTA.name}: {len(nueva)} rutas sin modelo.')
    else:
        print('\n'.join(rutas))
        print(f'{len(rutas)} rutas sin modelo.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
