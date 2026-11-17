"""La biblioteca normativa general en la web (107:RF-21): las normas con su estado en una fecha, las reglas de cada una
con su cita, y la subida de una norma a la capa del usuario. Es la misma biblioteca para toda empresa, estudio y
módulo; no depende del espacio de trabajo.
"""
from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import biblioteca_normativa as bn
from ..registro_normativo import RegistroError


class NormaResumen(BaseModel):
    acto: str
    titulo: str
    estado: str
    obliga: bool
    reglas: int
    url: str = ''
    vigencia_desde: str = ''
    vigencia_hasta: str = ''
    solo_referencia: str = ''
    sustituida_por_el_usuario: bool = False


class BibliotecaRespuesta(BaseModel):
    fecha: str
    huella: str
    capa_usuario: str
    normas: list[NormaResumen] = Field(default_factory=list)


class ReglaRespuesta(BaseModel):
    clave: str
    valor: str
    unidad: str = ''
    articulo_o_anexo: str = ''
    pagina: str = ''
    lineas: str = ''
    cita_literal: str = ''
    interpretacion: str = ''
    citada: bool = False


class ReglasRespuesta(BaseModel):
    acto: str
    reglas: list[ReglaRespuesta] = Field(default_factory=list)


class AgregadaRespuesta(BaseModel):
    actos: list[str]
    huella: str


def registrar_rutas_normativa(app: FastAPI, *, guardar_subida: Callable[[Path, UploadFile], None],
                              hoy: Callable[[], str]) -> None:
    base = '/api/normativa'

    @app.get(base, response_model=BibliotecaRespuesta)
    def normativa_listar(fecha: str | None = None) -> dict:
        """107:RF-21: cada norma de la biblioteca, su estado y si obliga en ``fecha`` (hoy, si no se da)."""
        dia = fecha or hoy()
        try:
            r = bn.cargar_biblioteca(dia)
        except RegistroError as exc:
            raise HTTPException(500, f'La biblioteca normativa no carga: {exc}') from exc
        sustituidas = getattr(r, 'sustituidas', {})
        normas = [{'acto': n.acto, 'titulo': n.titulo, 'estado': n.estado_juridico, 'obliga': n.obligatoria_en(dia),
                   'reglas': len(n.reglas), 'url': n.url, 'vigencia_desde': n.vigencia_desde,
                   'vigencia_hasta': n.vigencia_hasta, 'solo_referencia': n.solo_referencia,
                   'sustituida_por_el_usuario': n.acto in sustituidas} for n in (r.normas[a] for a in sorted(r.normas))]
        return {'fecha': dia, 'huella': bn.huella_biblioteca(), 'capa_usuario': str(bn.ruta_capa_usuario()),
                'normas': normas}

    @app.get(f'{base}/reglas', response_model=ReglasRespuesta)
    def normativa_reglas(acto: str) -> dict:
        """107:RF-21: las reglas de una norma, cada una con su artículo, página, líneas y cita literal."""
        r = bn.cargar_biblioteca()
        if acto not in r.normas:
            raise HTTPException(404, f'La biblioteca no tiene la norma {acto}.')
        reglas = [{'clave': x.clave, 'valor': str(x.valor), 'unidad': str(x.unidad),
                   'articulo_o_anexo': str(x.articulo_o_anexo), 'pagina': str(x.pagina), 'lineas': str(x.lineas),
                   'cita_literal': str(x.cita_literal), 'interpretacion': str(x.interpretacion), 'citada': x.citada}
                  for x in r.normas[acto].reglas]
        return {'acto': acto, 'reglas': reglas}

    @app.post(base, response_model=AgregadaRespuesta)
    def normativa_agregar(file: UploadFile = File(...)) -> dict:
        """107:RF-21: añade o actualiza una norma en la capa del usuario; lo que no cumple el esquema no entra."""
        nombre = Path(file.filename or '').name
        if not nombre.lower().endswith('.json'):
            raise HTTPException(422, 'La norma se sube como un fichero .json del esquema registro_normativo_v1.')
        with tempfile.TemporaryDirectory() as tmp:
            temporal = Path(tmp) / nombre
            guardar_subida(temporal, file)
            try:
                actos = bn.agregar_norma(temporal)
            except RegistroError as exc:
                raise HTTPException(422, str(exc)) from exc
        return {'actos': actos, 'huella': bn.huella_biblioteca()}
