"""Rutas del envío de informes por correo (spec 110, partes J, K y L del plan).

Se montan desde ``create_app`` con una llamada, como ``registrar_rutas_copia`` (pactado con el integrador); hasta
entonces las pruebas las montan en una ``FastAPI()`` propia. Los modelos de petición y de respuesta están en
``api_contract.py``, como los de las demás rutas.

- ``POST …/correo/vista-previa``: prepara el borrador (sin enviar nada) y devuelve su firma, los adjuntos con su
  huella, la validez del estudio (RF-12) y los avisos de los contactos (RF-14). Es lo único que puede pedir el
  asistente: un borrador sin confirmar y el enlace a la ventana (RF-6).
- ``POST …/correo/{borrador}/confirmar``: con la firma que vio el operador; solo desde la sesión del navegador (el
  ejecutor del asistente manda ``X-CSG-Token``, el navegador su cookie). Reserva la clave en el disco **antes** de
  encolar, así que un doble clic, aunque el primer trabajo no haya empezado, encuentra la reserva y no encola otro.
  Encola el envío en el carril ``correo``, sin ``reanudar``, para que la 096 nunca lo relance solo tras un reinicio
  (RF-5, RF-7, RF-9). Responde 200 con la clave y el trabajo (o el recibo que ya había), no 202: lo que se admite
  es la confirmación, y su forma es ``CorreoConfirmacion``.
- ``GET …/correo/envios/{clave}``, ``GET …/correo/historial?informe=…`` y ``POST …/correo/envios/{clave}/resolver``
  (RF-8, RF-9, RF-13).

Ningún correo ni token va al registro: el título del trabajo nombra el informe, no a quién va, y los eventos del
trabajo enmascaran las direcciones (``seguridad.enmascarar_correo``).
"""
from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from ..correo import Compartidor, CuentaNoConectada, FuenteDeCredenciales, ProveedorCorreo
from ..correo import borrador as b
from ..correo import envios as e
from ..correo.mensaje import construir_mensaje
from ..correo.proveedores import proveedor_de
from ..sesion_web import CABECERA_TOKEN
from ..util import publicar_duradero
from .api_contract import (CorreoConfirmacion, CorreoConfirmacionPeticion, CorreoEnvio, CorreoHistorial,
                           CorreoResolucionPeticion, CorreoVistaPrevia, CorreoVistaPreviaPeticion)
from .seguridad import enmascarar_correo

KIND = 'correo_envio'
#: Sin las cuentas de la 109 (o sin registrar la aplicación): lo que dice el recibo, sin fallar (110:RF-2; 109:RF-19).
SIN_CUENTA = ('Sin cuenta conectada: configure config/nube.json y conecte su cuenta de Google o de Microsoft con el '
              'permiso de enviar (ver docs/CORREO_OAUTH.md).')
LANE = 'correo'
_ES_ID = frozenset('0123456789abcdef')


def _ruta_borrador(ws, bid: str) -> Path:
    if len(bid) != 32 or not set(bid) <= _ES_ID:
        raise HTTPException(404, 'Borrador no encontrado.')
    return Path(ws.root) / e.CARPETA / 'borradores' / f'{bid}.json'


def _desde_la_ventana(request: Request) -> None:
    """La confirmación solo la da el operador en la ventana del navegador (110:RF-5, RF-6).

    El navegador manda ``Origin`` y su token en una cookie; un programa (el ejecutor del asistente, con
    ``cabeceras_locales``) manda ``X-CSG-Token`` o ``Authorization``. Con eso, ningún paso de ningún plan del
    asistente alcanza esta ruta aunque tuviera permiso de escritura.
    """
    cab = request.headers
    if not cab.get('origin') or cab.get(CABECERA_TOKEN.lower()) or cab.get('authorization'):
        raise HTTPException(403, 'El envío solo se confirma en la ventana de la web, a la vista del operador.')


class SinCuentas:
    """``FuenteDeCredenciales`` mientras la 109 no esté montada: ninguna cuenta conectada (plan de la 110, P8).

    Sin las cuentas de la 109, la web arranca igual y cada envío queda rechazado con «Sin cuenta conectada…», sin abrir la
    red. Cuando la 109 se integre, ``create_app`` pasa sus adaptadores (``credenciales_de``) y esto deja de usarse.
    """

    def token(self, proveedor: str, cuenta: str, alcance: str) -> str:
        raise CuentaNoConectada(SIN_CUENTA)


def raices_de(bases: Iterable[Path]) -> Iterable[Path]:
    """Las carpetas de los espacios de trabajo (con su ``workspace.json``), sin seguir enlaces ni uniones."""
    for base in bases:
        if not Path(base).is_dir():
            continue
        for carpeta in Path(base).iterdir():
            if carpeta.is_symlink() or carpeta.is_junction() or not carpeta.is_dir():
                continue
            if (carpeta / 'workspace.json').is_file():
                yield carpeta


def registrar_rutas_correo(app: FastAPI, *, ws_or_404, submit,
                           credenciales_de: Callable[[Any], FuenteDeCredenciales] = lambda ws: SinCuentas(),
                           compartidor_de: Callable[[Any], Compartidor | None] = lambda ws: None,
                           informes_en_curso: Callable[[Any], bool] = lambda ws: False,
                           raices_espacios: Callable[[], Iterable[Path]] = lambda: (),
                           proveedor: Callable[[str], ProveedorCorreo] = proveedor_de) -> None:
    """Monta las rutas del correo y deja en «desconocido» lo que un reinicio cortó (110:RF-9).

    Las cuentas de la 109 son de cada espacio de trabajo: ``credenciales_de(ws)`` y ``compartidor_de(ws)`` dan las de
    ese espacio (en la app, los adaptadores de ``correo.de_la_109`` sobre ``Cuentas`` de la 109).
    """
    for raiz in raices_espacios():
        try:
            e.DiarioEnvios(raiz).reconciliar_al_arrancar()
        except OSError:
            continue

    @app.post('/api/workspaces/{wid}/correo/vista-previa', response_model=CorreoVistaPrevia)
    def correo_vista_previa(wid: str, body: CorreoVistaPreviaPeticion) -> dict:
        """110:RF-1, RF-3, RF-6, RF-11, RF-12, RF-14: el borrador que verá el operador; no envía nada."""
        ws = ws_or_404(wid)
        prov = proveedor(body.proveedor)
        try:
            if body.enlace and not (body.expediente or '').strip():
                # 110:RF-10: sin expediente no hay a quién dar acceso, y el enlace no se enviaría.
                raise b.BorradorInvalido('Para enviar un enlace, elija el expediente que se comparte.')
            docx, resumen = b.resumen_del_informe(ws.out_dir, body.informe)
            rutas = [] if body.enlace else b.adjuntos_del_informe(
                ws.out_dir, body.informe, proyecto=body.proyecto, escenario=body.escenario,
                informes_en_curso=informes_en_curso(ws), elegidos=body.adjuntar)
            validez = b.validez_del_estudio(resumen)
            asunto = body.asunto or docx.stem
            cuerpo = body.cuerpo if body.cuerpo is not None else b.cuerpo_propuesto(asunto, validez)
            extra = {'informe': body.informe, 'validez': validez, 'origen': body.origen,
                     'huella_informe': b.adjunto_de(docx).sha256 if body.enlace else None,
                     'expediente': body.expediente}
            borr = b.crear_borrador(cuenta=body.cuenta, proveedor=body.proveedor, para=body.para, cc=body.cc,
                                    cco=body.cco, asunto=asunto, cuerpo=cuerpo, adjuntos=rutas,
                                    enlace=body.enlace, extra=extra)
        except b.BorradorInvalido as exc:
            raise HTTPException(400, str(exc)) from exc
        habituales = e.DiarioEnvios(ws.root).contactos_habituales(borr.cuenta)
        bid = secrets.token_hex(16)
        publicar_duradero(_ruta_borrador(ws, bid), json.dumps(borr.como_dict(), ensure_ascii=False) + '\n')
        return {'borrador': bid, 'firma': borr.firma(), 'cuenta': borr.cuenta, 'proveedor': borr.proveedor,
                'para': list(borr.para), 'cc': list(borr.cc), 'cco': list(borr.cco), 'asunto': borr.asunto,
                'cuerpo': borr.cuerpo, 'enlace': borr.enlace,
                'adjuntos': [{'nombre': a.nombre, 'tamano': a.tamano, 'sha256': a.sha256} for a in borr.adjuntos],
                'validez': validez, 'avisos': b.avisos_de_contactos(borr, habituales),
                'limite_bytes': prov.limite_adjuntos, 'excede_limite': e.excede_limite(borr, prov),
                'confirmado': False, 'ventana': f'/espacios/{ws.id}/correo/{bid}'}

    @app.post('/api/workspaces/{wid}/correo/{bid}/confirmar', response_model=CorreoConfirmacion)
    def correo_confirmar(wid: str, bid: str, body: CorreoConfirmacionPeticion, request: Request) -> dict:
        """110:RF-4, RF-5, RF-7: confirma ese contenido y esos destinatarios exactos y encola un solo envío."""
        _desde_la_ventana(request)
        ws = ws_or_404(wid)
        try:
            borr = b.Borrador.desde_dict(json.loads(_ruta_borrador(ws, bid).read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(404, 'Borrador no encontrado.') from None
        try:
            b.comprobar_firma(borr, body.firma)
        except b.ConfirmacionAnulada as exc:
            raise HTTPException(409, str(exc)) from exc
        diario = e.DiarioEnvios(ws.root)
        intento = diario.intento_para(ws.id, bid, body.firma)
        clave = e.clave_envio(ws.id, bid, body.firma, intento)
        recibo, nuevo = diario.reservar(clave, borr, espacio=ws.id, borrador_id=bid, intento=intento)
        if not nuevo:
            # Doble clic o segundo POST: el recibo que ya hay, sin otro trabajo (110:RF-7).
            return {'clave': clave, 'trabajo': None, 'recibo': recibo}
        prov = proveedor(borr.proveedor)

        def trabajo(ctx) -> dict:
            ctx.log(enmascarar_correo(f'Envío a {", ".join(borr.destinatarios())} con {borr.proveedor}.'))
            recibo = e.enviar(diario, borr, body.firma, espacio=ws.id, borrador_id=bid, proveedor=prov,
                              credenciales=credenciales_de(ws), construir=construir_mensaje,
                              compartidor=compartidor_de(ws), reservada=clave)
            ctx.log(enmascarar_correo(f'Resultado: {recibo["estado"]}. {recibo.get("motivo") or ""}'.strip()))
            return {'clave': recibo['clave'], 'estado': recibo['estado']}

        informe = borr.extra.get('informe') or 'informe'
        try:
            # 086:RF-70: el kind va literal en submit, para que la web le encuentre su paso (avisosEnSuPaso.test.mjs).
            job = submit(ws, 'correo_envio', f'Envío de correo de {informe}', trabajo, lane=LANE)
        except Exception:
            # Sin trabajo, la reserva no debe bloquear otro intento: queda cancelada y se dice por qué.
            diario.marcar(clave, 'cancelado', motivo='no se pudo poner el envío en cola')
            raise
        publico = job.public() if hasattr(job, 'public') else job
        return {'clave': clave, 'trabajo': publico, 'recibo': None}

    @app.get('/api/workspaces/{wid}/correo/envios/{clave}', response_model=CorreoEnvio)
    def correo_envio(wid: str, clave: str) -> dict:
        """110:RF-8: el recibo de un envío."""
        ws = ws_or_404(wid)
        try:
            recibo = e.DiarioEnvios(ws.root).recibo(clave)
        except e.EnvioError:
            recibo = None
        if recibo is None:
            raise HTTPException(404, 'Envío no encontrado.')
        return recibo

    @app.get('/api/workspaces/{wid}/correo/historial', response_model=CorreoHistorial)
    def correo_historial(wid: str, informe: str) -> dict:
        """110:RF-13: los envíos de un informe."""
        ws = ws_or_404(wid)
        return {'informe': informe, 'envios': e.DiarioEnvios(ws.root).historial(informe)}

    @app.post('/api/workspaces/{wid}/correo/envios/{clave}/resolver', response_model=CorreoEnvio)
    def correo_resolver(wid: str, clave: str, body: CorreoResolucionPeticion, request: Request) -> dict:
        """110:RF-9: el operador dice si un desconocido llegó; solo «No llegó» abre otro intento."""
        _desde_la_ventana(request)
        ws = ws_or_404(wid)
        try:
            return e.DiarioEnvios(ws.root).resolver(clave, llego=body.llego)
        except e.EnvioError as exc:
            raise HTTPException(409, str(exc)) from exc
