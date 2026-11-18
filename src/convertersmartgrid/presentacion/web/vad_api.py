"""Rutas del estudio de costos del VAD con la empresa modelo eficiente (spec 108; 070:RF-86).

Aparte del Estudio VNR (``web/vnr_api.py``): el VAD tiene su estudio, su TdR y sus entregables (108:RF-1). La web y el
asistente usan las mismas rutas (P5); el armado es largo y va como trabajo del motor, con progreso y cancelación (P7).

- ``GET …/vad/estudios``: los estudios del espacio, con su estado y el de su último armado.
- ``POST …/vad/estudios``: crea el estudio con la empresa del perfil, el grupo, el periodo y la versión del TdR (un acto
  del registro normativo). Un estudio que ya existe no se sobrescribe.
- ``POST …/vad/{estudio}/armar``: recibe el caso (``sistemas.json`` y las tablas que nombra), lo deja en la carpeta del
  estudio y encola el armado de la empresa modelo sistema por sistema. Lo que se puede comprobar antes (el estudio, el
  caso y cada fichero que nombra) da 422 antes de encolar.
- ``GET …/vad/{estudio}``: el estudio con su último armado, sus observaciones, lo que pueden afectar y sus salidas, con
  rutas del espacio para descargarlas (108 T29).
- ``POST …/vad/{estudio}/observaciones`` y ``POST …/vad/{estudio}/observaciones/{numero}/respuesta``: registrar y
  responder las observaciones del regulador (108:RF-26 sobre ``vad/observaciones``).
- ``POST …/vad/{estudio}/informe-definitivo``: arma el Informe Definitivo como trabajo, con las respuestas registradas.
  Un documento sin fuente sale como hueco nombrado, nunca vacío; con observaciones sin responder da 422 antes de encolar.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ...dominio.util import nombre_seguro, publicar_duradero
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


class DestinoVad(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tipo: str = Field(min_length=1, max_length=20)
    id: str = Field(min_length=1, max_length=120)


class ObservacionVad(BaseModel):
    """108:RF-26 (T11): una observación del regulador, con su número, su fecha, su texto y lo que afecta."""
    model_config = ConfigDict(extra='forbid')
    numero: str = Field(min_length=1, max_length=60)
    fecha: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    texto: str = Field(min_length=1, max_length=20_000)
    afecta: list[DestinoVad] = Field(min_length=1)


class RespuestaVad(BaseModel):
    """108:RF-26 (T11): la respuesta con su sustento y, por destino afectado, qué cambió."""
    model_config = ConfigDict(extra='forbid')
    respuesta: str = Field(min_length=1, max_length=20_000)
    sustento: str = Field(min_length=1, max_length=20_000)
    cambios: dict[str, str] = Field(default_factory=dict)


def nombre_del_caso(nombre: str) -> str:
    """El nombre de un fichero del caso, si vale tal cual: sin carpetas, con letras, dígitos, ``-`` y ``_``, en .json y
    sin los nombres reservados de Windows. ``sistemas.json`` lo nombra así: renombrarlo rompería sus referencias."""
    base = Path(nombre or '').name
    raiz, extension = Path(base).stem, Path(base).suffix.lower()
    if extension != '.json' or not raiz or nombre_seguro(raiz) != raiz or _RESERVADOS.match(raiz):
        raise HTTPException(422, f'{base or "un fichero sin nombre"}: el caso del VAD admite ficheros .json con letras, '
                                 'dígitos, «-» y «_» en su nombre')
    return raiz + extension


def _miembros_del_caso(paquete: Path) -> dict[str, bytes]:
    """Los JSON de un caso empaquetado en .zip, en la raíz del zip y con los mismos nombres que se admiten sueltos."""
    import zipfile

    try:
        with zipfile.ZipFile(paquete) as z:
            miembros = {}
            for info in z.infolist():
                if info.is_dir():
                    continue
                nombre = nombre_del_caso(info.filename)
                if Path(info.filename).name != info.filename:
                    raise HTTPException(422, f'{info.filename}: el caso empaquetado lleva sus JSON en la raíz del zip')
                if info.file_size > TOPE_CASO:
                    raise HTTPException(413, f'{nombre}: pasa de {TOPE_CASO // 2 ** 20} MiB')
                miembros[nombre] = z.read(info)
    except zipfile.BadZipFile:
        raise HTTPException(422, f'{paquete.name}: no es un zip') from None
    return miembros


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


def registrar_rutas_vad(app, *, ws_or_404: Callable, submit: Callable, raiz_config: Path,
                        guardar_subida: Callable | None = None) -> None:
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
        from ...dominio.perfil_empresa import cargar_perfil
        from ...dominio.registro_normativo import cargar_registro
        from ...aplicacion.vad import VadError
        from ...aplicacion.vad.estudio import crear_estudio

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
    async def vad_armar(wid: str, estudio: str, files: list[UploadFile] | None = File(None),
                        fuente_vad_caso: str | None = Form(None)) -> dict:
        """108:RF-1, RF-5, RF-7: el caso en la carpeta del estudio y el armado de la empresa modelo como trabajo.

        El caso llega como sus JSON sueltos, como un .zip (que queda en las fuentes de la empresa, clase «vad_caso») o,
        sin fichero, de las fuentes de la empresa: la que nombra ``fuente_vad_caso`` o la vigente (109:RF-25)."""
        from ...aplicacion.vad import VadError
        from ...aplicacion.vad.estudio import cargar_estudio, carpeta_estudio
        from ...aplicacion.vad.trabajo import leer_caso

        ws = ws_or_404(wid)
        raiz, estudio = Path(ws.root), _id(estudio)
        try:
            cargar_estudio(raiz, estudio)
        except VadError as exc:
            raise HTTPException(404, str(exc)) from None
        caso = carpeta_estudio(raiz, estudio) / 'caso'
        recibidos = {}
        files = [f for f in (files or []) if f.filename]
        zips = [f for f in files if Path(f.filename).suffix.lower() == '.zip']
        if zips or not files:
            # 109:RF-25: el caso como un solo paquete de la empresa; el subido queda registrado para los demás estudios.
            if guardar_subida is None:
                raise HTTPException(422, 'el caso del VAD se sube como sus ficheros .json')
            from .fuentes_api import fuente_o_subida
            paquete = fuente_o_subida(ws, 'vad_caso', fuente_vad_caso, zips[0] if zips else None, guardar_subida)
            recibidos = _miembros_del_caso(paquete)
            files = []
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
        from ...adaptadores.vad.linea import leer_estudio_del_caso

        try:
            # 108 T30: las entradas del estudio (PIDE y calidad), dentro del caso y presentes, antes de encolar.
            del_estudio = leer_estudio_del_caso(caso)
        except (VadError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        faltan = sorted(Path(r).name for r in del_estudio.values() if not Path(r).is_file())
        if faltan:
            raise HTTPException(422, 'el caso nombra ficheros que no se subieron: ' + ', '.join(faltan))

        def trabajo(ctx) -> dict[str, Any]:
            from ...dominio.registro_normativo import cargar_registro
            from ...aplicacion.vad.anexo2 import cargar_formatos
            from ...aplicacion.vad.estudio import comprobar_estudio
            from ...adaptadores.vad.linea import armar_linea
            from ...aplicacion.vad.trabajo import armar_empresa_modelo, pasos_del_caso

            registro = cargar_registro(*registros)
            comprobado = comprobar_estudio(raiz, estudio, registro)
            m = armar_empresa_modelo(ctx, raiz, estudio, entradas,
                                     pasos_del_caso(cargar_formatos(formatos), comprobado.periodo))
            # 108 T30: la línea del VAD tras la empresa modelo: resultados, PIDE, calidad, explotación, tablas e informes.
            linea = armar_linea(ctx, raiz, estudio, entradas, del_estudio, registro)
            return {'estudio': estudio, 'estado_estudio': comprobado.estado, 'motivos': list(comprobado.motivos),
                    'sistemas': {s: r.get('estado') for s, r in m['sistemas'].items()},
                    'linea': {p: r.get('estado') for p, r in linea['pasos'].items()},
                    'manifiesto': str(carpeta_estudio(raiz, estudio) / 'manifiesto.json')}

        return submit(ws, 'vad_empresa_modelo', f'Empresa modelo del VAD {estudio}', trabajo)

    def _estudio_o_404(raiz: Path, estudio: str):
        from ...aplicacion.vad import VadError
        from ...aplicacion.vad.estudio import cargar_estudio

        try:
            return cargar_estudio(raiz, _id(estudio))
        except VadError as exc:
            raise HTTPException(404, str(exc)) from None

    def _relativa(raiz: Path, ruta: str | Path | None) -> str | None:
        if not ruta:
            return None
        try:
            return Path(ruta).resolve().relative_to(raiz.resolve()).as_posix()
        except ValueError:
            return None

    def _leer(ruta: Path) -> Any:
        try:
            return json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else None
        except (OSError, ValueError):
            return None

    @app.get('/api/workspaces/{wid}/vad/{estudio}')
    def vad_detalle(wid: str, estudio: str) -> dict[str, Any]:
        """108:RF-26 (T29): el estudio, su último armado, sus observaciones, lo que pueden afectar y sus salidas."""
        from ...dominio.registro_normativo import cargar_registro
        from ...aplicacion.vad import VadError
        from ...aplicacion.vad.anexo2 import cargar_formatos
        from ...aplicacion.vad.estudio import carpeta_estudio
        from ...adaptadores.vad.observaciones import cargar_observaciones, destinos_validos

        raiz = Path(ws_or_404(wid).root)
        e = _estudio_o_404(raiz, estudio)
        carpeta = carpeta_estudio(raiz, e.id)
        observaciones = [{'numero': o.numero, 'fecha': o.fecha, 'texto': o.texto, 'estado': o.estado,
                          'afecta': [{'tipo': d.tipo, 'id': d.id} for d in o.afecta], 'respuesta': o.respuesta,
                          'sustento': o.sustento, 'cambios': dict(o.cambios)} for o in cargar_observaciones(raiz, e.id)]
        try:
            validos = destinos_validos(e.usos, cargar_registro(*registros), cargar_formatos(formatos))
            destinos = sorted(({'tipo': d.tipo, 'id': d.id} for d in validos), key=lambda d: (d['tipo'], d['id']))
        except (VadError, OSError, ValueError, KeyError) as exc:  # el registro ilegible se dice; no tumba el detalle
            destinos, aviso_destinos = [], f'no se pudieron leer los destinos del registro: {exc}'
        else:
            aviso_destinos = ''
        salidas = sorted(_relativa(raiz, p) for p in carpeta.rglob('*')
                         if p.is_file() and 'caso' not in p.relative_to(carpeta).parts[:1])
        return {'estudio': {'id': e.id, 'empresa': e.empresa, 'grupo': e.grupo, 'periodo': e.periodo,
                            'version_tdr': e.version_tdr, 'estado': e.estado},
                'armado': _leer(carpeta / 'manifiesto.json'), 'observaciones': observaciones,
                'pendientes': [o['numero'] for o in observaciones if o['estado'] == 'pendiente'],
                'destinos': destinos, 'aviso_destinos': aviso_destinos,
                'informe_definitivo': _leer(carpeta / 'informe_definitivo' / 'informe.json'),
                'linea': _leer(carpeta / 'linea.json'),
                'salidas': [s for s in salidas if s]}

    @app.post('/api/workspaces/{wid}/vad/{estudio}/observaciones')
    def vad_observacion(wid: str, estudio: str, body: ObservacionVad) -> dict[str, Any]:
        """108:RF-26 (T11): registra una observación del regulador; lo que afecta tiene que existir en el estudio."""
        from ...dominio.registro_normativo import cargar_registro
        from ...aplicacion.vad import VadError
        from ...aplicacion.vad.anexo2 import cargar_formatos
        from ...adaptadores.vad.observaciones import registrar_observacion

        raiz = Path(ws_or_404(wid).root)
        e = _estudio_o_404(raiz, estudio)
        try:
            o = registrar_observacion(raiz, e.id, numero=body.numero, fecha=body.fecha, texto=body.texto,
                                      afecta=[d.model_dump() for d in body.afecta],
                                      registro=cargar_registro(*registros), formatos=cargar_formatos(formatos))
        except VadError as exc:
            raise HTTPException(422, str(exc)) from None
        return {'numero': o.numero, 'estado': o.estado}

    @app.post('/api/workspaces/{wid}/vad/{estudio}/observaciones/{numero}/respuesta')
    def vad_responder(wid: str, estudio: str, numero: str, body: RespuestaVad) -> dict[str, Any]:
        """108:RF-26 (T11): la respuesta con su sustento y lo que cambió en cada destino que la observación afecta."""
        from ...aplicacion.vad import VadError
        from ...adaptadores.vad.observaciones import cargar_observaciones, responder

        raiz = Path(ws_or_404(wid).root)
        e = _estudio_o_404(raiz, estudio)
        if not any(o.numero == numero for o in cargar_observaciones(raiz, e.id)):
            raise HTTPException(404, f'el estudio {e.id} no tiene la observación {numero}')
        try:
            o = responder(raiz, e.id, numero, respuesta=body.respuesta, sustento=body.sustento, cambios=body.cambios)
        except VadError as exc:
            raise HTTPException(422, str(exc)) from None
        return {'numero': o.numero, 'estado': o.estado}

    @app.post('/api/workspaces/{wid}/vad/{estudio}/informe-definitivo', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def vad_informe_definitivo(wid: str, estudio: str) -> dict:
        """108:RF-26 (T22, T29): el Informe Definitivo como trabajo, con las respuestas registradas. Lo que el estudio
        todavía no tiene (los contenidos de los informes, el libro de tablas) sale como hueco nombrado."""
        from ...aplicacion.vad import VadError
        from ...aplicacion.vad.estudio import carpeta_estudio
        from ...adaptadores.vad.informes import comprobar_respuestas
        from ...adaptadores.vad.observaciones import cargar_observaciones

        ws = ws_or_404(wid)
        raiz = Path(ws.root)
        e = _estudio_o_404(raiz, estudio)
        try:
            # La misma regla que el informe: cada observación respondida, con su sustento y lo que cambió en cada
            # destino que afecta. Se comprueba antes de encolar.
            comprobar_respuestas(cargar_observaciones(raiz, e.id))
        except VadError as exc:
            raise HTTPException(422, str(exc)) from None
        carpeta = carpeta_estudio(raiz, e.id) / 'informe_definitivo'
        tablas = carpeta_estudio(raiz, e.id) / 'tablas_resultados.xlsx'

        def trabajo(ctx) -> dict[str, Any]:
            from ...dominio.registro_normativo import cargar_registro
            from ...adaptadores.vad.informes import armar_informe_definitivo
            from ...adaptadores.vad.linea import contenido_guardado

            # 108 T30: lo que la línea dejó para los informes; sin línea, los documentos salen como huecos nombrados.
            resultados, del_estudio_informe = contenido_guardado(raiz, e.id)

            ctx.progress(0, 1, 'Informe Definitivo')
            inf = armar_informe_definitivo(cargar_registro(*registros), raiz, e.id, carpeta, empresa=e.empresa,
                                           resultados=resultados, estudio=del_estudio_informe,
                                           tablas_excel=tablas if tablas.is_file() else None)
            documentos = [{**d, 'ruta_relativa': _relativa(raiz, d.get('ruta')),
                           'pdf_relativa': _relativa(raiz, d.get('pdf'))} for d in inf.documentos]
            resumen = {'estudio': e.id, 'documentos': documentos, 'huecos': list(inf.huecos), 'regla': inf.regla,
                       'acto': inf.acto}
            publicar_duradero(carpeta / 'informe.json', json.dumps(resumen, ensure_ascii=False, indent=1) + '\n')
            ctx.progress(1, 1, 'terminado')
            return resumen

        return submit(ws, 'vad_informe_definitivo', f'Informe Definitivo del VAD {e.id}', trabajo)
