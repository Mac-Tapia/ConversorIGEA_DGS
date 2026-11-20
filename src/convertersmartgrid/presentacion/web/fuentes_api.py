"""Las fuentes de la empresa del espacio en la web: listar, subir y la red convertida (109:RF-25 y RF-26).

Cada módulo (VNR, PIT, VAD, corto plazo, PIDE, largo plazo…) elige aquí el libro que ya cargó la empresa en lugar de
pedirlo otra vez; una subida desde cualquier módulo se registra para todos (``fuentes_empresa``).
"""
from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ...aplicacion import fuentes_empresa as fe


class MiembroRespuesta(BaseModel):
    nombre: str
    huella: str


class FuenteRespuesta(BaseModel):
    id: str
    clase: str
    periodo: str
    nombre: str
    huella: str
    ruta_rel: str
    registrada: str
    vigente: bool
    miembros: list[MiembroRespuesta] = Field(default_factory=list)


class FuentesRespuesta(BaseModel):
    fuentes: list[FuenteRespuesta]
    clases: list[str]


class RedDelEspacioRespuesta(BaseModel):
    #: 109:RF-26 (revisión web del 19-11): un espacio sin red es un estado esperado, no un error: 200 con «disponible»
    #: falso y su motivo; antes era un 404 que el navegador apuntaba como error en Estudio VNR y Estudio PIT.
    disponible: bool = True
    motivo: str = ''
    fuente: str = ''
    empresa: str = ''
    alimentadores: list[str] = Field(default_factory=list)
    canonical: bool = False
    huella: str = ''


def fuente_o_subida(ws, clase: str, fuente_id: str | None, subida: UploadFile | None,
                    guardar_subida: Callable[[Path, UploadFile], None], *, periodo: str = '') -> Path:
    """La ruta del libro de ``clase`` que pide un módulo: la subida (que además se registra en la empresa), la fuente
    ``fuente_id`` o, si no se da ninguna, la vigente de la empresa. Sin ninguna, 400 con lo que falta."""
    raiz = Path(ws.root)
    if subida is not None and subida.filename:
        with tempfile.TemporaryDirectory() as tmp:
            temporal = Path(tmp) / Path(subida.filename).name
            guardar_subida(temporal, subida)
            f = fe.registrar(raiz, clase, temporal, nombre=subida.filename, periodo=periodo)
        return fe.ruta(raiz, f.id)
    try:
        if fuente_id:
            return fe.ruta(raiz, fuente_id)
    except fe.FuenteError as exc:
        raise HTTPException(404, str(exc)) from exc
    vig = fe.vigente(raiz, clase)
    if vig is None:
        raise HTTPException(400, f'Falta el libro «{clase}» de la empresa: súbalo una vez y lo usan todos los módulos.')
    return fe.ruta(raiz, vig.id)


def registrar_rutas_fuentes(app: FastAPI, *, ws_or_404, guardar_subida: Callable[[Path, UploadFile], None]) -> None:
    base = '/api/workspaces/{wid}/fuentes'

    @app.get(base, response_model=FuentesRespuesta, response_model_exclude_unset=True)
    def fuentes_listar(wid: str, clase: str | None = None) -> dict:
        """109:RF-25: los libros de la empresa del espacio, de una clase o de todas."""
        ws = ws_or_404(wid)
        return {'fuentes': [f.__dict__ for f in fe.listar(Path(ws.root), clase)], 'clases': list(fe.CLASES)}

    @app.post(base, response_model=FuenteRespuesta, response_model_exclude_unset=True)
    def fuentes_subir(wid: str, clase: str = Form(...), periodo: str = Form(''), file: UploadFile = File(...)) -> dict:
        """109:RF-25: registra un libro en la empresa; queda vigente en su clase y periodo y lo ven todos los módulos."""
        ws = ws_or_404(wid)
        if clase not in fe.CLASES:
            raise HTTPException(422, f'Clase desconocida: {clase}.')
        with tempfile.TemporaryDirectory() as tmp:
            temporal = Path(tmp) / Path(file.filename or 'fichero').name
            guardar_subida(temporal, file)
            return fe.registrar(Path(ws.root), clase, temporal, nombre=file.filename or '', periodo=periodo).__dict__

    @app.get(f'{base}/red', response_model=RedDelEspacioRespuesta, response_model_exclude_unset=True)
    def fuentes_red(wid: str) -> dict:
        """109:RF-26: la red convertida del espacio, de qué fuente, empresa y alimentadores."""
        red = fe.red_del_espacio(Path(ws_or_404(wid).root))
        if red is None:
            return {'disponible': False, 'motivo': 'El espacio aún no tiene una red cargada.'}
        return {**red, 'canonical': bool(red.get('canonical'))}
