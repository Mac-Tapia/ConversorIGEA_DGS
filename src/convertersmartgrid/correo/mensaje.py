"""El mensaje MIME de un envío de la 110 (parte G del plan), con la biblioteca estándar (``email.message``).

El ``Message-ID`` sale de la clave del envío (``envios.message_id``), para que el operador encuentre el correo en
«Enviados» de su cuenta y lo distinga de otro intento. Cada adjunto se lee otra vez justo antes de construirlo y se
compara con la huella firmada: si cambió entre la confirmación y este instante, el mensaje no se construye
(110:RF-4). Así, ni un informe regenerado en ese hueco sale sin revisar.
"""
from __future__ import annotations

import hashlib
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path

from .borrador import Borrador, ConfirmacionAnulada
from .envios import message_id

#: Tipo MIME de cada extensión admitida (las mismas de ``borrador.EXTENSIONES``).
TIPOS = {
    '.docx': ('application', 'vnd.openxmlformats-officedocument.wordprocessingml.document'),
    '.pdf': ('application', 'pdf'),
    '.xlsx': ('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
}


def _leer_firmado(ruta: Path, sha256: str, tamano: int, nombre: str) -> bytes:
    try:
        datos = ruta.read_bytes()
    except OSError:
        raise ConfirmacionAnulada(f'El adjunto {nombre} ya no está: revise otra vez.') from None
    if len(datos) != tamano or hashlib.sha256(datos).hexdigest() != sha256:
        raise ConfirmacionAnulada(f'El adjunto {nombre} cambió desde la vista previa: revise otra vez.')
    return datos


def construir_mensaje(borrador: Borrador, clave: str, *, ahora: datetime | None = None) -> bytes:
    """El correo listo para el proveedor: cabeceras, cuerpo (con el enlace, si lo hay) y los adjuntos firmados."""
    msg = EmailMessage(policy=SMTP)
    msg['From'] = borrador.cuenta
    msg['To'] = ', '.join(borrador.para)
    if borrador.cc:
        msg['Cc'] = ', '.join(borrador.cc)
    if borrador.cco:
        # Gmail y Graph leen el Bcc del MIME, lo entregan y lo quitan del correo que ven los demás.
        msg['Bcc'] = ', '.join(borrador.cco)
    msg['Subject'] = borrador.asunto
    msg['Date'] = format_datetime(ahora or datetime.now(timezone.utc))
    msg['Message-ID'] = message_id(clave)
    cuerpo = borrador.cuerpo
    if borrador.enlace:
        cuerpo = f'{cuerpo.rstrip()}\n\n{borrador.enlace}\n'
    msg.set_content(cuerpo)
    for adjunto in borrador.adjuntos:
        ruta = Path(adjunto.ruta)
        datos = _leer_firmado(ruta, adjunto.sha256, adjunto.tamano, adjunto.nombre)
        principal, secundario = TIPOS.get(ruta.suffix.lower(), ('application', 'octet-stream'))
        msg.add_attachment(datos, maintype=principal, subtype=secundario, filename=adjunto.nombre)
    return msg.as_bytes()
