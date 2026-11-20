"""100:RF-10, RF-13: la matriz estudio × motor en la web, con el estado de las specs del repositorio o, en el programa
instalado, el del recurso que viaja en la entrega.

Por qué el recurso. ``config/entrega.json`` excluye ``specs/``: el programa que abre el acceso directo del operador no
tiene las specs, y leer solo de ahí ponía «sin validar» también a lo validado (auditoría de d8, 2026-11-19). El recurso
lo escribe ``tools/estado_specs.py --escribir`` junto a ``specs/README.md``, con la huella del README del que sale.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from ...aplicacion.asistente.lectura_proyecto import estado_de_spec
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


def registrar_rutas_matriz(app: FastAPI, *, raiz: Path, recurso: Path = RECURSO) -> None:
    """Monta ``GET /api/estudios/matriz``; ``raiz`` es la del programa, donde está ``specs/`` en el repositorio."""

    @app.get('/api/estudios/matriz', response_model=MatrizEstudiosRespuesta)
    def matriz_estudios() -> dict:
        """100:RF-8 a RF-10, RF-13: cada estudio de la web con cada motor, y de dónde salen sus estados."""
        lector, origen = estados_de_specs(raiz, recurso)
        return matriz(lector, origen)
