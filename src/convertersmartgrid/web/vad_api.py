"""Rutas del estudio de costos del VAD con la empresa modelo eficiente (spec 108; 070:RF-86).

Aparte del Estudio VNR (``web/vnr_api.py``): el VAD tiene su estudio, su TdR y sus entregables (108:RF-1). La web y el
asistente usan las mismas rutas (P5); el armado es largo y va como trabajo del motor, con progreso y cancelación (P7).

- ``GET …/vad/estudios``: los estudios del espacio, con su estado y el de su último armado.
- ``POST …/vad/estudios``: crea el estudio con la empresa del perfil, el grupo, el periodo y la versión del TdR (un acto
  del registro normativo). Un estudio que ya existe no se sobrescribe.
- ``POST …/vad/{estudio}/armar``: recibe el caso (``sistemas.json`` y las tablas que nombra), lo deja en la carpeta del
  estudio y encola el armado de la empresa modelo sistema por sistema. Lo que se puede comprobar antes (el estudio, el
  caso y cada fichero que nombra) da 422 antes de encolar.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ..util import nombre_seguro, publicar_duradero
from .api_contract import JobRespuesta

#: Lo que admite el caso: JSON, con nombres que valen en cualquier sistema de ficheros.
TOPE_CASO = 50 * 2 ** 20
_RESERVADOS = re.compile(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])$', re.IGNORECASE)
_ID_ESTUDIO = re.compile(r'^[\w-]{1,120}$')


class CrearEstudioVad(BaseModel):
    """108:RF-1: el estudio de la empresa del perfil para un grupo, un periodo y una versión del TdR."""
    model_config = ConfigDict(extra='forbid')
    grupo: int = Field(ge=1, le=9)
    periodo: str = Field(pattern=r'^\d{4}-\d{4}$')
    version_tdr: str = Field(min_length=1, max_length=120)


def nombre_del_caso(nombre: str) -> str:
    """El nombre de un fichero del caso, si vale tal cual: sin carpetas, con letras, dígitos, ``-`` y ``_``, en .json y
    sin los nombres reservados de Windows. ``sistemas.json`` lo nombra así: renombrarlo rompería sus referencias."""
    base = Path(nombre or '').name
    raiz, extension = Path(base).stem, Path(base).suffix.lower()
    if extension != '.json' or not raiz or nombre_seguro(raiz) != raiz or _RESERVADOS.match(raiz):
        raise HTTPException(422, f'{base or "un fichero sin nombre"}: el caso del VAD admite ficheros .json con letras, '
                                 'dígitos, «-» y «_» en su nombre')
    return raiz + extension


def _estudios(raiz: Path) -> list[dict[str, Any]]:
    salida = []
    for f in sorted((raiz / 'vad').glob('*/estudio.json')):
        try:
            e = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        fila = {k: e.get(k) for k in ('id', 'empresa', 'grupo', 'periodo', 'version_tdr', 'estado')}
        m = f.parent / 'manifiesto.json'
        if m.is_file():
            try:
                man = json.loads(m.read_text(encoding='utf-8'))
                fila['armado'] = {'terminado': man.get('terminado'), 'cancelado': man.get('cancelado'),
                                  'sistemas': {s: r.get('estado') for s, r in (man.get('sistemas') or {}).items()}}
            except (OSError, ValueError):
                fila['armado'] = None
        salida.append(fila)
    return salida


def registrar_rutas_vad(app, *, ws_or_404: Callable, submit: Callable, raiz_config: Path) -> None:
    """Monta las rutas del VAD sobre la cola y los espacios del único servidor."""
    registros = (raiz_config / 'vad', raiz_config / 'normativa')
    formatos = raiz_config / 'vad' / 'anexo2_formatos.json'

    def _id(estudio: str) -> str:
        if not _ID_ESTUDIO.match(estudio):
            raise HTTPException(404, 'Estudio del VAD no encontrado.')
        return estudio

    @app.get('/api/workspaces/{wid}/vad/estudios')
    def vad_estudios(wid: str) -> dict[str, Any]:
        """108:RF-1: los estudios del espacio y el estado de su último armado."""
        return {'estudios': _estudios(Path(ws_or_404(wid).root))}

    @app.post('/api/workspaces/{wid}/vad/estudios')
    def vad_crear(wid: str, body: CrearEstudioVad) -> dict[str, Any]:
        """108:RF-1, RF-9: crea el estudio con la empresa del perfil y la instantánea del registro."""
        from ..perfil_empresa import cargar_perfil
        from ..registro_normativo import cargar_registro
        from ..vad import VadError
        from ..vad.estudio import crear_estudio

        raiz = Path(ws_or_404(wid).root)
        try:
            registro = cargar_registro(*registros)
            registro.norma(body.version_tdr)
            e = crear_estudio(raiz, cargar_perfil(), grupo=body.grupo, periodo=body.periodo,
                              version_tdr=body.version_tdr, registro=registro)
        except (VadError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        return {'id': e.id, 'empresa': e.empresa, 'grupo': e.grupo, 'periodo': e.periodo, 'version_tdr': e.version_tdr,
                'estado': e.estado}

    @app.post('/api/workspaces/{wid}/vad/{estudio}/armar', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    async def vad_armar(wid: str, estudio: str, files: list[UploadFile] = File(...)) -> dict:
        """108:RF-1, RF-5, RF-7: el caso en la carpeta del estudio y el armado de la empresa modelo como trabajo."""
        from ..vad import VadError
        from ..vad.estudio import cargar_estudio, carpeta_estudio
        from ..vad.trabajo import leer_caso

        ws = ws_or_404(wid)
        raiz, estudio = Path(ws.root), _id(estudio)
        try:
            cargar_estudio(raiz, estudio)
        except VadError as exc:
            raise HTTPException(404, str(exc)) from None
        caso = carpeta_estudio(raiz, estudio) / 'caso'
        recibidos = {}
        for f in files:
            nombre = nombre_del_caso(f.filename or '')
            datos = await f.read(TOPE_CASO + 1)
            if len(datos) > TOPE_CASO:
                raise HTTPException(413, f'{nombre}: pasa de {TOPE_CASO // 2 ** 20} MiB')
            recibidos[nombre] = datos
        if 'sistemas.json' not in recibidos:
            raise HTTPException(422, 'el caso necesita su sistemas.json')
        caso.mkdir(parents=True, exist_ok=True)
        for nombre, datos in recibidos.items():
            publicar_duradero(caso / nombre, datos)
        try:
            entradas = leer_caso(caso)
        except (VadError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        faltan = sorted({Path(r).name for pasos in entradas.values() for r in pasos.values() if not Path(r).is_file()})
        fuera = sorted({r for pasos in entradas.values() for r in pasos.values()
                        if not Path(r).resolve().is_relative_to(caso.resolve())})
        if faltan or fuera:
            raise HTTPException(422, 'el caso nombra ficheros que no se subieron: ' + ', '.join(faltan or fuera))

        def trabajo(ctx) -> dict[str, Any]:
            from ..registro_normativo import cargar_registro
            from ..vad.anexo2 import cargar_formatos
            from ..vad.estudio import comprobar_estudio
            from ..vad.trabajo import armar_empresa_modelo, pasos_del_caso

            comprobado = comprobar_estudio(raiz, estudio, cargar_registro(*registros))
            m = armar_empresa_modelo(ctx, raiz, estudio, entradas,
                                     pasos_del_caso(cargar_formatos(formatos), comprobado.periodo))
            return {'estudio': estudio, 'estado_estudio': comprobado.estado, 'motivos': list(comprobado.motivos),
                    'sistemas': {s: r.get('estado') for s, r in m['sistemas'].items()},
                    'manifiesto': str(carpeta_estudio(raiz, estudio) / 'manifiesto.json')}

        return submit(ws, 'vad_empresa_modelo', f'Empresa modelo del VAD {estudio}', trabajo)
