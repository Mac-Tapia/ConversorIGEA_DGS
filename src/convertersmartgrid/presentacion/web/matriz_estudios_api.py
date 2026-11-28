"""100:RF-10, RF-13, RF-21 a RF-23: la matriz estudio × motor en la web, con el estado de las specs del repositorio o,
en el programa instalado, el del recurso que viaja en la entrega, y el sello de la aceptación de la versión que corre.

Por qué el recurso. ``config/entrega.json`` excluye ``specs/``: el programa que abre el acceso directo del operador no
tiene las specs, y leer solo de ahí ponía «sin validar» también a lo validado (auditoría de d8, 2026-11-19). El recurso
lo escribe ``tools/estado_specs.py --escribir`` junto a ``specs/README.md``, con la huella del README del que sale.

Por qué el sello. El 26-11 pasaron todos los casos de la aceptación y la web siguió en «Sin validar»: las celdas que
citan la 100 esperaban a que alguien cerrara a mano su T4. El sello lo deja ``tools/aceptacion_version.py`` al dar la
versión por aceptada; aquí solo vale el de la versión que corre esta web (100:RF-22).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from ...aplicacion.asistente.lectura_proyecto import estado_de_spec
from ...aplicacion.sello_aceptacion import carpeta_aceptacion, sello_vigente, version_en_uso
from ...dominio.matriz_estudios import matriz
from .api_contract import MatrizEstudiosRespuesta

#: El recurso de la entrega, dentro del paquete.
RECURSO = Path(__file__).resolve().parents[2] / 'recursos' / 'estado_specs.json'

Lector = Callable[[str], str | None]


def _de_specs(raiz: Path) -> Lector | None:
    carpeta = raiz / 'specs'
    if not carpeta.is_dir():
        return None
    nombres = {d.name[:3]: d.name for d in carpeta.iterdir() if (d / 'spec.md').is_file()}
    if not nombres:
        return None
    return lambda n: estado_de_spec(raiz, nombres[n]) if n in nombres else None


def _de_recurso(recurso: Path) -> Lector | None:
    try:
        estados = json.loads(recurso.read_text(encoding='utf-8'))['estados']
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(estados, dict) or not estados:
        return None
    return lambda n: estados.get(n) if isinstance(estados.get(n), str) else None


def estados_de_specs(raiz: Path, recurso: Path = RECURSO) -> tuple[Lector, str]:
    """El lector del estado de la spec ``NNN`` y su origen: ``specs/`` si está; si no, el recurso; si no, ninguno.

    Se relee en cada petición: son unas cien líneas y así una spec que se cierra o se reabre se ve sin reiniciar.
    """
    if (lector := _de_specs(raiz)) is not None:
        return lector, 'specs'
    if (lector := _de_recurso(recurso)) is not None:
        return lector, 'recurso'
    return (lambda _n: None), 'ninguno'


def aceptacion_de_la_version(raiz: Path, carpeta: Path | None = None) -> dict | None:
    """100:RF-21, RF-22: el sello aceptado de la versión que corre el programa de ``raiz``, o None.

    Se busca en cada petición, como el estado de las specs: una aceptación que termina se ve sin reiniciar la web.
    """
    return sello_vigente(version_en_uso(raiz), carpeta if carpeta is not None else carpeta_aceptacion(raiz))


def registrar_rutas_matriz(app: FastAPI, *, raiz: Path, recurso: Path = RECURSO, sellos: Path | None = None) -> None:
    """Monta ``GET /api/estudios/matriz``; ``raiz`` es la del programa, donde está ``specs/`` en el repositorio, y
    ``sellos``, otra carpeta de los sellos de la aceptación (las pruebas)."""

    @app.get('/api/estudios/matriz', response_model=MatrizEstudiosRespuesta)
    def matriz_estudios() -> dict:
        """100:RF-8 a RF-10, RF-13, RF-21 a RF-23: cada estudio de la web con cada motor, de dónde salen sus estados
        y la aceptación de esta versión, si la hay."""
        lector, origen = estados_de_specs(raiz, recurso)
        return matriz(lector, origen, aceptacion_de_la_version(raiz, sellos))
