"""Las rutas de la nube en la web: proveedores, cuentas, conectar, retorno, desconectar e importar (spec 109).

Se montan con ``registrar_rutas_nube(...)`` al final de ``create_app``, como ``registrar_rutas_copia``, y reciben las
funciones de la web para que la copia de la nube entre por el mismo camino que una subida (109:RF-4, P5):
``asignar_entrada`` (``_assign``), ``validar_entrada`` (``_validar_entrada``) y ``reemplazar_libros``
(``_reemplazar_carpeta``). No se copia su lógica. El cableado en ``web/app.py`` se pacta con el integrador.

- T3 (109:RF-19): ``GET /api/nube/proveedores`` dice qué proveedor está registrado en este equipo y, si no, «Sin cuenta
  conectada: configure config/nube.json». Sin el registro, conectar responde 409 y lo local sigue igual.
- T5: el retorno de OAuth va en ``GET /nube/retorno``, fuera de ``/api/``: la cookie de la sesión es ``SameSite=Strict``
  y no viaja en la vuelta desde el proveedor. Lo protegen el ``state`` de un solo uso y PKCE.
- T9: vínculos, comprobar versiones, traer y aceptar con confirmación (``web/nube.py``).
- T10 y T11: publicar y compartir exigen además la confirmación de un solo uso que da su previa.
- T8: importar es un trabajo del carril ``engine`` (P7), que se bloquea con una conversión como una subida.
- 109:RF-15: conectar, importar y desconectar exigen la sesión del navegador; una petición con el token de un programa
  (el asistente, una herramienta) se rechaza aunque traiga un plan confirmado.
- T19 (109:RF-21, RF-22): importar para una ``entrada`` de la web guarda solo la copia fija, sin asignarla, y
  ``GET …/nube/copias/{sha256}`` la devuelve al navegador, que la carga por la subida propia de esa entrada (RF-4).
- Cada ruta declara su ``response_model`` (``extra='forbid'``): el OpenAPI da la forma de cada respuesta y un campo que
  no esté en el contrato, como un token, no puede salir.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from ...adaptadores.entrada.nube import Copia, importar
from ...adaptadores.nube.cuentas import Cuentas
from ...adaptadores.nube.oauth import EstadoInvalido, NoRegistrado
from ...adaptadores.nube.proveedor import PROVEEDORES, ErrorNube, SinAcceso, YaExiste
from ...adaptadores.salida.nube import (Confirmaciones, Rechazo, cerrar_paquete, compartir, destinatarios_validos,
                                       leer_paquete, previa_compartir, publicar, recibo_de_publicacion, recibos)
from ...dominio.salidas_red import SalidaApagada, es_ruta_de_la_nube
from ...dominio.sesion_web import CABECERA_TOKEN
from . import nube as vinculos_nube
from .api_contract import JobRespuesta, Respuesta
from .nube_selector import pagina_selector
from .workspace import SLOTS

#: 109:RF-15: el asistente la usa (``asistente/equipo.py``) para no pedir ninguna ruta de la nube.
__all__ = ['es_ruta_de_la_nube', 'registrar_rutas_nube']
Proveedor = Literal['google', 'microsoft']
LibroTipo = Literal['cabecera', 'suministros', 'clientes', 'perdidas', 'coincidente']
KIND_IMPORTAR = 'nube_importar'
#: T19: el nombre de una entrada de la web (``estudios``, ``informe_pdf``…): una palabra, nunca una ruta.
_ENTRADA = re.compile(r'[a-z][a-z0-9_]{0,63}')
_HUELLA = re.compile(r'[0-9a-f]{64}')


# ---------------------------------------------------------------------- peticiones
class _Peticion(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ConectarPeticion(_Peticion):
    publicar: bool = False
    #: 110: 'enviar' pide solo el permiso de enviar correo; sin él, leer o publicar según ``publicar``.
    alcance: Literal['leer', 'publicar', 'enviar'] | None = None


class ImportarPeticion(_Peticion):
    proveedor: Proveedor
    ids: list[str] = Field(min_length=1, max_length=500)
    casilla: str | None = None
    libro: LibroTipo | None = None
    #: T19: la entrada de la web que la carga por su propia subida; solo se guarda la copia fija.
    entrada: str | None = None


# ---------------------------------------------------------------------- respuestas (109:RF-2: ningún token)
class NubeProveedorRespuesta(Respuesta):
    nombre: Proveedor
    visible: str
    registrado: bool
    se_puede_conectar: bool
    motivo: str | None
    permisos: str


class NubeProveedoresRespuesta(Respuesta):
    proveedores: list[NubeProveedorRespuesta]


class NubeCuentaRespuesta(NubeProveedorRespuesta):
    conectada: bool
    cuenta: str | None
    #: Lo que la cuenta concedió de verdad (del último token); ``None`` si no se sabe sin red.
    permisos_concedidos: list[str] | None
    puede_publicar: bool | None
    puede_enviar: bool | None


class NubeCuentasRespuesta(Respuesta):
    cuentas: list[NubeCuentaRespuesta]


class NubeConectarRespuesta(Respuesta):
    url: str
    proveedor: Proveedor


class NubeVinculoRespuesta(Respuesta):
    id: str
    destino: dict
    proveedor: Proveedor
    item_id: str
    nombre_remoto: str
    vigente: dict
    historial: list[dict]
    estado: Literal['al_dia', 'nueva', 'sin_comprobar']
    comprobado: str
    motivo: str | None
    nueva: dict | None
    candidata: dict | None


class NubeVinculosRespuesta(Respuesta):
    vinculos: list[NubeVinculoRespuesta]


class AceptarPeticion(_Peticion):
    confirmar: bool = False


class PublicarPrevia(_Peticion):
    proveedor: Proveedor
    carpeta_destino: str = Field(min_length=1)
    nombre: str = Field(min_length=1, max_length=120)
    salida: str = ''
    seleccion: list[str] = []


class PublicarPeticion(PublicarPrevia):
    confirmacion: str


class CompartirPrevia(_Peticion):
    publicacion: str
    destinatarios: list[str] = []
    publico: bool = False


class CompartirPeticion(CompartirPrevia):
    autorizo_enlace_publico: bool = False
    confirmacion: str


class NubePublicarPreviaRespuesta(Respuesta):
    proveedor: Proveedor
    carpeta_destino: str
    nombre: str
    ficheros: int
    sobrescribe: bool
    confirmacion: str


class NubeAccesoRespuesta(Respuesta):
    destinatario: str
    rol: Literal['lectura']


class NubeCompartirPreviaRespuesta(Respuesta):
    paquete: str
    publicacion: str
    nombre: str | None
    proveedor: Proveedor
    acceso: list[NubeAccesoRespuesta]
    destinatarios: list[str]
    publico: bool
    aviso_publico: str | None
    #: 109:RF-20: los datos crudos que impiden compartir; con alguno, ``confirmacion`` es ``None``.
    bloqueo: list[str]
    confirmacion: str | None


class NubeRecibosRespuesta(Respuesta):
    recibos: list[dict]


class NubeTokenSelectorRespuesta(Respuesta):
    """109:RF-2 (aclaración): lo único que recibe el selector; nunca el token de refresco ni el secreto."""

    proveedor: Proveedor
    token_acceso: str
    caduca_en_s: int
    alcance: str
    id_cliente: str
    clave_api: str | None
    id_aplicacion: str | None


#: El token del selector no se guarda en el navegador ni en un proxy (aclaración de 109:RF-2).
_SIN_CACHE = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}


class NubeDesconectarRespuesta(Respuesta):
    proveedor: Proveedor
    desconectada: bool
    revocado: bool
    aviso: str | None


def _http(exc: BaseException) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, (NoRegistrado, SalidaApagada, YaExiste)):
        return HTTPException(409, str(exc))
    if isinstance(exc, (EstadoInvalido, Rechazo, ValueError)) or type(exc).__name__ == 'UserError':
        return HTTPException(400, str(exc))
    if isinstance(exc, SinAcceso):
        return HTTPException(403, str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(404, 'No existe ese vínculo con la nube en este espacio.')
    return HTTPException(502, str(exc))


class _SinCodigoEnElRegistro(logging.Filter):
    """109:RF-2: el registro de accesos escribe la URL entera; la de ``/nube/retorno`` lleva el código de OAuth y el
    ``state``. Se tapan antes de escribirse, en el de uvicorn y en el de httpx (el cliente de las pruebas)."""

    _CODIGO = re.compile(r'((?:code|state)=)[^&\s"]+')

    def _tapar(self, texto: str) -> str:
        return self._CODIGO.sub(lambda m: m.group(1) + '***', texto)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._tapar(a) if isinstance(a, str) else
                                (self._tapar(str(a)) if '/nube/retorno' in str(a) else a) for a in record.args)
        if isinstance(record.msg, str):
            record.msg = self._tapar(record.msg)
        return True


def _instalar_filtro_registro() -> None:
    for nombre in ('uvicorn.access', 'httpx', 'httpx2'):   # httpx2: el registro del cliente httpx de esta versión
        registro = logging.getLogger(nombre)
        if not any(isinstance(f, _SinCodigoEnElRegistro) for f in registro.filters):
            registro.addFilter(_SinCodigoEnElRegistro())


class _Subida:
    """Lo que ``_reemplazar_carpeta`` lee de un ``UploadFile``: el nombre y el fichero abierto (la copia)."""

    def __init__(self, ruta: Path) -> None:
        self.filename = ruta.name
        self.file = ruta.open('rb')

    def cerrar(self) -> None:
        self.file.close()


class _SalvoNube(frozenset):
    """Para ``_reemplazar_carpeta(lectores=...)``: cualquier trabajo lee los libros, salvo esta misma importación."""

    def __contains__(self, kind: object) -> bool:
        return kind != KIND_IMPORTAR


def registrar_rutas_nube(app: FastAPI, *, ws_or_404, submit, asignar_entrada, validar_entrada, reemplazar_libros,
                         cuentas: Cuentas | None = None, confirmaciones: Confirmaciones | None = None) -> Cuentas:
    """Monta las rutas de la nube con la cola, los espacios y la asignación de entradas del único servidor."""
    cuentas = cuentas or Cuentas()
    confirmaciones = confirmaciones or Confirmaciones()
    _instalar_filtro_registro()

    def solo_operador(request: Request) -> None:
        """109:RF-15: solo la sesión del navegador; un programa con el token de la web no conecta ni importa."""
        if request.headers.get(CABECERA_TOKEN) or request.headers.get('authorization', '').lower().startswith('bearer'):
            raise HTTPException(403, 'La nube solo se maneja desde la web, con el operador delante: el asistente y '
                                     'los programas no conectan cuentas, ni importan, ni publican, ni comparten.')

    def _proveedor(nombre: str) -> str:
        if nombre not in PROVEEDORES:
            raise HTTPException(404, f'Proveedor de nube desconocido: {nombre}.')
        return nombre

    def _asignar(ws, destino: dict, copias: list[Copia]) -> dict:
        """109:RF-4: la copia entra por la misma validación y asignación que una subida."""
        if 'entrada' in destino:
            # 109:RF-22: la carga el navegador por la subida propia de esa entrada, con su misma validación.
            return {}
        if 'casilla' in destino:
            copia = copias[0]
            warning = validar_entrada(destino['casilla'], copia.ruta)
            return asignar_entrada(ws, destino['casilla'], copia.ruta, 'nube', warning=warning)
        from . import services

        tipo = destino['libro']
        carpeta = services.demanda_carpeta(ws, tipo)

        def asignar(destinos: list[Path]) -> dict:
            fuente = (carpeta if tipo in {'cabecera', 'suministros'} or (tipo == 'clientes' and len(destinos) > 1)
                      else destinos[0])
            return services.demanda_asignar(ws, tipo, fuente, 'nube')

        subidas = [_Subida(c.ruta) for c in copias]
        try:
            return reemplazar_libros(ws, carpeta, subidas, f'{tipo}.xlsx', asignar, conservar=tipo == 'cabecera',
                                     lectores=_SalvoNube())
        finally:
            for s in subidas:
                s.cerrar()

    # ------------------------------------------------------------------ cuentas
    @app.get('/api/nube/proveedores', response_model=NubeProveedoresRespuesta)
    def nube_proveedores() -> dict:
        """109:RF-19: qué proveedores están registrados en este equipo y si se pueden conectar."""
        return {'proveedores': cuentas.proveedores()}

    @app.get('/api/workspaces/{wid}/nube/cuentas', response_model=NubeCuentasRespuesta)
    def nube_cuentas(wid: str) -> dict:
        ws = ws_or_404(wid)
        return {'cuentas': cuentas.estado(ws.id)}

    @app.post('/api/workspaces/{wid}/nube/{proveedor}/conectar', response_model=NubeConectarRespuesta)
    def nube_conectar(wid: str, proveedor: str, request: Request, body: ConectarPeticion | None = None) -> dict:
        """109:RF-1: la URL del proveedor con los permisos mínimos; la contraseña la escribe el operador allí."""
        solo_operador(request)
        ws = ws_or_404(wid)
        try:
            url = cuentas.iniciar(ws.id, _proveedor(proveedor), publicar=bool(body and body.publicar),
                                  alcance=body.alcance if body else None)
        except (ErrorNube, SalidaApagada, ValueError) as exc:
            raise _http(exc) from exc
        return {'url': url, 'proveedor': proveedor}

    @app.get('/nube/retorno', include_in_schema=False)
    def nube_retorno(state: str = '', code: str = '', error: str = '') -> RedirectResponse:
        """La vuelta del proveedor: canjea el código y vuelve a la web; un ``state`` ajeno o repetido no conecta."""
        if error or not code:
            return RedirectResponse('/?nube=cancelada', status_code=303)
        try:
            hecho = cuentas.completar(state, code)
        except (ErrorNube, SalidaApagada, RuntimeError, OSError):
            # Sin detalle en la URL: nunca un token ni un código; la web ofrece volver a conectar.
            return RedirectResponse('/?nube=error', status_code=303)
        return RedirectResponse(f"/?nube=conectada&proveedor={hecho['proveedor']}", status_code=303)

    @app.delete('/api/workspaces/{wid}/nube/{proveedor}', response_model=NubeDesconectarRespuesta)
    def nube_desconectar(wid: str, proveedor: str, request: Request) -> dict:
        """109:RF-14: revoca y borra la credencial; las copias importadas y los recibos se quedan."""
        solo_operador(request)
        ws = ws_or_404(wid)
        return cuentas.desconectar(ws.id, _proveedor(proveedor))

    # ------------------------------------------------------------------ importar
    @app.post('/api/workspaces/{wid}/nube/importar', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def nube_importar(wid: str, body: ImportarPeticion, request: Request) -> dict:
        """109:RF-3, RF-4: descarga la copia fija y la asigna por la misma vía que una subida."""
        solo_operador(request)
        ws = ws_or_404(wid)
        if sum(d is not None for d in (body.casilla, body.libro, body.entrada)) != 1:
            raise HTTPException(422, 'Diga la casilla, el libro o la entrada donde entra lo importado.')
        if body.entrada is not None and not _ENTRADA.fullmatch(body.entrada):
            raise HTTPException(422, 'La entrada se nombra con una palabra en minúsculas, sin rutas.')
        if body.casilla is not None and body.casilla not in SLOTS:
            raise HTTPException(404, f'Casilla desconocida: {body.casilla}')
        if body.casilla is not None and len(body.ids) != 1:
            raise HTTPException(422, 'Una casilla admite un solo fichero.')
        if body.libro not in (None, 'cabecera', 'suministros', 'clientes') and len(body.ids) != 1:
            raise HTTPException(422, 'Ese libro admite un solo fichero.')
        try:
            cuentas.cliente(body.proveedor)
        except ErrorNube as exc:
            raise _http(exc) from exc
        destino = ({'casilla': body.casilla} if body.casilla is not None else
                   {'libro': body.libro} if body.libro is not None else {'entrada': body.entrada})

        def trabajo(ctx) -> dict:
            prov = cuentas.proveedor(ws.id, body.proveedor)
            copias = []
            for item_id in body.ids:
                ctx.check_cancel()
                copias.append(importar(prov, item_id, vinculos_nube.carpeta_copias(ws), ctx))
            _asignar(ws, destino, copias)
            vinculos = []
            for copia in copias:
                propio = destino if len(copias) == 1 else {**destino, 'nombre': copia.ficha['nombre']}
                vinculos.append(vinculos_nube.registrar_vinculo(ws, propio, copia)['id'])
            return {'copias': [vinculos_nube.vinculo(ws, v)['vigente'] for v in vinculos], 'vinculos': vinculos,
                    'destino': destino}

        # El kind va literal: frontend/test/avisosEnSuPaso.test.mjs lee cada submit para exigir su fila en la web.
        return submit(ws, 'nube_importar', 'Importar de la nube', trabajo)

    @app.get('/api/workspaces/{wid}/nube/copias/{huella}', response_class=FileResponse)
    def nube_copia(wid: str, huella: str, request: Request) -> FileResponse:
        """109:RF-22: la copia fija ya importada, tal cual, para que el navegador la cargue en su entrada."""
        solo_operador(request)
        ws = ws_or_404(wid)
        if not _HUELLA.fullmatch(huella):
            raise HTTPException(404, 'No hay una copia de la nube con esa huella.')
        carpeta = vinculos_nube.carpeta_copias(ws) / huella
        try:
            ficha = json.loads((carpeta / 'copia.json').read_text(encoding='utf-8'))
            ruta = (carpeta / str(ficha['nombre'])).resolve()
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(404, 'No hay una copia de la nube con esa huella.') from None
        if ruta.parent != carpeta.resolve() or not ruta.is_file():
            raise HTTPException(404, 'No hay una copia de la nube con esa huella.')
        return FileResponse(ruta, filename=ruta.name, headers={'Cache-Control': 'no-store'})

    # ------------------------------------------------------------------ versiones (T9)
    @app.get('/api/workspaces/{wid}/nube/vinculos', response_model=NubeVinculosRespuesta)
    def nube_vinculos(wid: str) -> dict:
        ws = ws_or_404(wid)
        return {'vinculos': sorted(vinculos_nube.leer_vinculos(ws).values(), key=lambda v: v['id'])}

    @app.post('/api/workspaces/{wid}/nube/versiones', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def nube_versiones(wid: str) -> dict:
        """109:RF-7, RF-17: comprueba las revisiones; sin conexión dice que no pudo comprobar."""
        ws = ws_or_404(wid)
        return submit(ws, 'nube_versiones', 'Comprobar versiones en la nube',
                      lambda ctx: vinculos_nube.comprobar_versiones(ws, lambda p: cuentas.proveedor(ws.id, p), ctx))

    @app.post('/api/workspaces/{wid}/nube/vinculos/{vid}/traer', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def nube_traer(wid: str, vid: str) -> dict:
        """109:RF-7: trae la versión nueva como otra copia, sin asignarla, y la compara con la vigente."""
        ws = ws_or_404(wid)
        try:
            vinculos_nube.vinculo(ws, vid)
        except KeyError as exc:
            raise _http(exc) from exc

        def trabajo(ctx) -> dict:
            return vinculos_nube.traer_nueva(ws, vid, lambda p, item: importar(
                cuentas.proveedor(ws.id, p), item, vinculos_nube.carpeta_copias(ws), ctx))

        return submit(ws, 'nube_traer', 'Traer la versión nueva de la nube', trabajo)

    @app.post('/api/workspaces/{wid}/nube/vinculos/{vid}/aceptar', response_model=NubeVinculoRespuesta)
    def nube_aceptar(wid: str, vid: str, body: AceptarPeticion, request: Request) -> dict:
        """109:RF-8: la versión nueva entra solo con la confirmación del operador; la anterior se conserva."""
        solo_operador(request)
        ws = ws_or_404(wid)
        from .services import UserError

        try:
            return vinculos_nube.aceptar(ws, vid, body.confirmar, lambda destino, copia: _asignar(ws, destino, [copia]))
        except (KeyError, ValueError, UserError) as exc:
            raise _http(exc) from exc

    # ------------------------------------------------------------------ publicar (T10)
    def _raiz_salida(ws, salida: str) -> Path:
        base = Path(ws.out_dir).resolve()
        raiz = (base / salida).resolve() if salida else base
        if raiz != base and base not in raiz.parents:
            raise HTTPException(400, 'La carpeta del expediente tiene que estar dentro de la salida del espacio.')
        if not raiz.is_dir():
            raise HTTPException(404, 'Esa carpeta del expediente no existe en la salida del espacio.')
        return raiz

    # 109:RF-24 (revisión web W9): el PIT y el VAD guardan sus entregables en su carpeta del espacio, no en la salida.
    CARPETAS_DE_MODULO = ('expedientes_pit', 'vad')

    def _raiz_publicacion(ws, body: PublicarPrevia) -> tuple[Path, tuple[str, ...]]:
        """La raíz del ZIP y la selección dentro de ella: la salida o, si todo lo elegido es de una carpeta de módulo
        del espacio, esa carpeta (sin salir del espacio ni seguir redirecciones)."""
        primeros = {s.split('/', 1)[0] for s in body.seleccion}
        if not body.salida and body.seleccion and len(primeros) == 1 and primeros <= set(CARPETAS_DE_MODULO):
            carpeta = Path(ws.root) / primeros.pop()
            base = Path(ws.root).resolve()
            if carpeta.is_symlink() or carpeta.is_junction() or carpeta.resolve().parent != base or not carpeta.is_dir():
                raise HTTPException(404, 'Esa carpeta del módulo no existe en el espacio.')
            return carpeta.resolve(), tuple(s.split('/', 1)[1] for s in body.seleccion if '/' in s)
        return _raiz_salida(ws, body.salida), tuple(body.seleccion)

    def _origen(ws, raiz: Path) -> str:
        """De dónde sale el paquete: su ruta en la salida o, para una carpeta de módulo, su ruta en el espacio."""
        salida = Path(ws.out_dir).resolve()
        if raiz == salida or salida in raiz.parents:
            return raiz.relative_to(salida).as_posix() or '.'
        return raiz.relative_to(Path(ws.root).resolve()).as_posix()

    def _contar(raiz: Path, seleccion: tuple[str, ...]) -> int:
        n = 0
        for d, _s, nombres in os.walk(raiz):
            for nombre in nombres:
                rel = (Path(d) / nombre).relative_to(raiz).as_posix()
                if not seleccion or any(rel in (f, f'{f}.dgs') or rel.startswith((f'{f}_', f'{f}/')) for f in seleccion):
                    n += 1
        return n

    def _sujeto_publicar(body: PublicarPrevia) -> str:
        return json.dumps([body.proveedor, body.carpeta_destino, body.nombre, body.salida, sorted(body.seleccion)])

    @app.post('/api/workspaces/{wid}/nube/publicar/previa', response_model=NubePublicarPreviaRespuesta)
    def nube_publicar_previa(wid: str, body: PublicarPrevia) -> dict:
        """109:RF-9: qué se va a subir y adónde, con la confirmación de un solo uso que exige publicar."""
        ws = ws_or_404(wid)
        raiz, seleccion = _raiz_publicacion(ws, body)
        ficheros = _contar(raiz, seleccion)
        return {'proveedor': body.proveedor, 'carpeta_destino': body.carpeta_destino, 'nombre': body.nombre,
                'ficheros': ficheros, 'sobrescribe': False,
                'confirmacion': confirmaciones.emitir(ws.id, 'publicar', _sujeto_publicar(body))}

    @app.post('/api/workspaces/{wid}/nube/publicar', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def nube_publicar(wid: str, body: PublicarPeticion, request: Request) -> dict:
        """109:RF-9, RF-12, RF-13: ZIP cerrado con su manifiesto, sin pisar nada, y su recibo."""
        solo_operador(request)
        ws = ws_or_404(wid)
        raiz, seleccion = _raiz_publicacion(ws, body)
        try:
            confirmaciones.consumir(body.confirmacion, ws.id, 'publicar', _sujeto_publicar(body))
        except Rechazo as exc:
            raise _http(exc) from exc

        def trabajo(ctx) -> dict:
            from .operaciones_lentas import preparar_zip, retirar_zip

            prov = cuentas.proveedor(ws.id, body.proveedor)
            if body.proveedor == 'microsoft' and 'Files.ReadWrite' not in cuentas.permisos(ws.id, body.proveedor):
                raise SinAcceso('Para publicar en OneDrive hace falta el permiso de escritura: vuelva a conectar la '
                                'cuenta con «Publicar».')
            hecho = preparar_zip(ws.id, raiz, seleccion, ctx)
            zip_preparado = ctx.job._archivo_zip
            try:
                paquete = cerrar_paquete(zip_preparado, vinculos_nube.carpeta_paquetes(ws),
                                         origen=_origen(ws, raiz))
            finally:
                retirar_zip(zip_preparado, ctx.job.id, ws.id)
            ctx.check_cancel()
            recibo = publicar(prov, paquete, body.carpeta_destino, vinculos_nube.carpeta_recibos(ws),
                              nombre=body.nombre, wid=ws.id)
            return {'recibo': recibo, 'archivos': hecho['archivos']}

        return submit(ws, 'nube_publicar', 'Publicar el expediente en la nube', trabajo)

    # ------------------------------------------------------------------ compartir (T11)
    def _paquete_y_recibo(ws, clave: str):
        recibo = recibo_de_publicacion(vinculos_nube.carpeta_recibos(ws), clave)
        return leer_paquete(vinculos_nube.carpeta_paquetes(ws), recibo['paquete']), recibo

    @app.post('/api/workspaces/{wid}/nube/compartir/previa', response_model=NubeCompartirPreviaRespuesta)
    def nube_compartir_previa(wid: str, body: CompartirPrevia) -> dict:
        """109:RF-10, RF-11, RF-20: quién tendrá acceso y qué lo impide, antes de confirmar."""
        ws = ws_or_404(wid)
        try:
            paquete, recibo = _paquete_y_recibo(ws, body.publicacion)
            previa = previa_compartir(paquete, recibo, body.destinatarios, body.publico)
        except Rechazo as exc:
            raise _http(exc) from exc
        if previa['bloqueo']:
            return {**previa, 'confirmacion': None}
        return {**previa, 'confirmacion': confirmaciones.emitir(ws.id, 'compartir', body.publicacion,
                                                                previa['destinatarios'], body.publico)}

    @app.post('/api/workspaces/{wid}/nube/compartir', status_code=202, response_model=JobRespuesta,
              response_model_exclude_unset=True)
    def nube_compartir(wid: str, body: CompartirPeticion, request: Request) -> dict:
        """109:RF-10 a RF-12, RF-20: solo lectura a los nombrados, con la confirmación de la previa; un recibo cada uno."""
        solo_operador(request)
        ws = ws_or_404(wid)
        try:
            paquete, recibo = _paquete_y_recibo(ws, body.publicacion)
            if body.publico and not body.autorizo_enlace_publico:
                raise Rechazo('«Cualquiera con el enlace» necesita su autorización expresa en este envío.')
            confirmaciones.consumir(body.confirmacion, ws.id, 'compartir', body.publicacion,
                                    destinatarios_validos(body.destinatarios), body.publico)
        except Rechazo as exc:
            raise _http(exc) from exc

        def trabajo(_ctx) -> dict:
            prov = cuentas.proveedor(ws.id, recibo['proveedor'])
            return {'permisos': compartir(prov, paquete, recibo, body.destinatarios,
                                          vinculos_nube.carpeta_recibos(ws), publico=body.publico,
                                          autorizo_enlace_publico=body.autorizo_enlace_publico, wid=ws.id)}

        return submit(ws, 'nube_compartir', 'Compartir el expediente', trabajo)

    # ------------------------------------------------------------------ selector de ficheros (T18)
    @app.post('/api/workspaces/{wid}/nube/{proveedor}/selector/token', response_model=NubeTokenSelectorRespuesta)
    def nube_selector_token(wid: str, proveedor: str, request: Request) -> JSONResponse:
        """109:RF-1, RF-3 y aclaración de RF-2: el token de ACCESO de corta duración para abrir el selector.

        Solo el de acceso, con el alcance de leer (``drive.file`` o ``Files.Read``); nunca el de refresco ni el
        secreto del cliente. ``no-store``: ni el navegador ni un proxy lo guardan; el selector lo pide cada vez.
        """
        solo_operador(request)
        ws = ws_or_404(wid)
        try:
            datos = cuentas.token_selector(ws.id, _proveedor(proveedor))
        except (ErrorNube, SalidaApagada) as exc:
            raise _http(exc) from exc
        return JSONResponse(NubeTokenSelectorRespuesta(**datos).model_dump(), headers=_SIN_CACHE)

    @app.get('/nube/selector/{proveedor}', include_in_schema=False)
    def nube_selector(proveedor: str, espacio: str, modo: Literal['ficheros', 'carpeta'] = 'ficheros') -> HTMLResponse:
        """La página del selector del proveedor, con su propia CSP; devuelve los ids elegidos por ``postMessage``."""
        ws = ws_or_404(espacio)
        try:
            cliente = cuentas.cliente(_proveedor(proveedor))
        except ErrorNube as exc:
            raise _http(exc) from exc
        nonce = secrets.token_urlsafe(18)
        html, csp = pagina_selector(proveedor, ws.id, modo, nonce, cliente.url_selector)
        return HTMLResponse(html, headers={**_SIN_CACHE, 'Content-Security-Policy': csp,
                                           'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/api/workspaces/{wid}/nube/recibos', response_model=NubeRecibosRespuesta)
    def nube_recibos(wid: str) -> dict:
        """109:RF-12: los recibos de este espacio; nunca los de otro."""
        ws = ws_or_404(wid)
        return {'recibos': recibos(vinculos_nube.carpeta_recibos(ws))}

    return cuentas
