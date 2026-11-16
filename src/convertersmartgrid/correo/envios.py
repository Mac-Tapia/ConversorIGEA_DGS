"""Diario durable de los envíos de correo de un espacio (spec 110, parte F del plan).

Cada envío confirmado tiene una **clave** (``sha256(espacio, borrador, firma, intento)``) y un recibo en
``<espacio>/envios/<clave>.json``. La reserva es la creación exclusiva de ese fichero (``O_CREAT | O_EXCL``) **antes**
de llamar al proveedor (110:RF-7): un doble clic o un segundo POST con la misma firma encuentra la clave y devuelve su
recibo sin otra llamada. Ni ``messages.send`` de Gmail ni ``sendMail`` de Graph admiten una clave de idempotencia, y
confiar en un indicador en memoria (como ``guardado['en_curso']`` del asistente) no resiste dos POST a la vez.

Estados: ``reservado → enviando → aceptado | rechazado | desconocido``, y ``cancelado`` si se cancela antes de llamar.
Un ``desconocido`` (el proveedor no respondió a tiempo, un 5xx o un trabajo cortado por un reinicio) no se reenvía
nunca solo (110:RF-9): el operador mira «Enviados» de su cuenta y dice «Llegó» o «No llegó»; solo «No llegó», o un
rechazo, abre el intento siguiente, con otra clave y una confirmación nueva. Resolverlo leyendo el buzón pediría
``gmail.readonly`` o ``Mail.Read``, que la spec prohíbe (110:RF-2).

Los recibos llevan direcciones personales: viven fuera de la salida del espacio (no aparecen en ``GET …/outputs``),
viajan con la copia de datos de la 086 y la limpieza de la 062 no los toca.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..salidas_red import SalidaApagada
from ..util import publicar_duradero
from . import Compartidor, CuentaNoConectada, FuenteDeCredenciales, ProveedorCorreo, ResultadoEnvio
from .borrador import Borrador, ConfirmacionAnulada, comprobar_firma

CARPETA = 'envios'
ESTADOS = ('reservado', 'enviando', 'aceptado', 'rechazado', 'desconocido', 'cancelado')
#: Sin resultado del proveedor todavía: tras un reinicio no se sabe si salió.
SIN_RESULTADO = ('reservado', 'enviando')
#: Admiten otro intento con una confirmación nueva: el correo no salió (o el operador dice que no llegó).
REINTENTABLES = ('rechazado', 'cancelado')
_ES_CLAVE = frozenset('0123456789abcdef')
#: Dominio reservado (RFC 2606): el ``Message-ID`` es único sin nombrar ninguna máquina ni empresa.
DOMINIO_MESSAGE_ID = 'csg.invalid'


class EnvioError(RuntimeError):
    """Una operación que el estado del envío no admite; el mensaje lo lee el operador."""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


_RELOJ = threading.Lock()
_ULTIMO_ORDEN = 0


def _orden() -> int:
    """El orden de una reserva: nanosegundos de reloj, estrictamente creciente en el proceso (110:RF-13).

    ``hora`` va en segundos, y dos envíos del mismo segundo quedaban ordenados por su clave, que es un hash: el
    historial salía en un orden al azar en vez de «del más antiguo al más reciente».
    """
    global _ULTIMO_ORDEN
    with _RELOJ:
        _ULTIMO_ORDEN = max(time.time_ns(), _ULTIMO_ORDEN + 1)
        return _ULTIMO_ORDEN


def clave_envio(espacio: str, borrador_id: str, firma: str, intento: int) -> str:
    """La clave única de un intento de envío (110:RF-7)."""
    return hashlib.sha256(f'{espacio}\x1f{borrador_id}\x1f{firma}\x1f{int(intento)}'.encode('utf-8')).hexdigest()


def message_id(clave: str) -> str:
    """El ``Message-ID`` del correo sale de la clave, para encontrarlo en «Enviados» de la cuenta."""
    return f'<{clave}@{DOMINIO_MESSAGE_ID}>'


def huella_del_informe(borrador: Borrador) -> str | None:
    """La huella del informe que se envía: la del adjunto que lo nombra, o la que trae el borrador de un enlace."""
    informe = borrador.extra.get('informe')
    for adjunto in borrador.adjuntos:
        if adjunto.nombre == informe:
            return adjunto.sha256
    if borrador.extra.get('huella_informe'):
        return str(borrador.extra['huella_informe'])
    return borrador.adjuntos[0].sha256 if borrador.adjuntos else None


class DiarioEnvios:
    """Los recibos de un espacio, en ``<raiz>/envios``. Una escritura por clave a la vez (el trabajo de ese envío)."""

    def __init__(self, raiz: Path | str):
        self.carpeta = Path(raiz) / CARPETA
        self._lock = threading.Lock()

    def _ruta(self, clave: str) -> Path:
        if len(clave) != 64 or not set(clave) <= _ES_CLAVE:
            raise EnvioError('Clave de envío no válida.')
        return self.carpeta / f'{clave}.json'

    # -------------------------------------------------------------- lectura
    def recibo(self, clave: str) -> dict[str, Any] | None:
        try:
            datos = json.loads(self._ruta(clave).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return datos if isinstance(datos, dict) else None

    def recibos(self) -> list[dict[str, Any]]:
        """Todos los recibos legibles, del más antiguo al más reciente; uno roto se salta."""
        filas = []
        if self.carpeta.is_dir():
            for ruta in self.carpeta.glob('*.json'):
                datos = self.recibo(ruta.stem) if len(ruta.stem) == 64 else None
                if datos is not None:
                    filas.append(datos)
        return sorted(filas, key=lambda r: (str(r.get('hora') or ''), int(r.get('orden') or 0),
                                            int(r.get('intento') or 0), r['clave']))

    def historial(self, informe: str) -> list[dict[str, Any]]:
        """110:RF-13: los envíos de un informe, por su nombre en la salida del espacio."""
        return [r for r in self.recibos() if r.get('informe') == informe]

    # -------------------------------------------------------------- escritura
    def reservar(self, clave: str, borrador: Borrador, *, espacio: str, borrador_id: str,
                 intento: int) -> tuple[dict[str, Any], bool]:
        """Crea el recibo en exclusiva (110:RF-7). Si ya existía, devuelve el que hay y ``False``."""
        ruta = self._ruta(clave)
        recibo = {
            'clave': clave, 'espacio': espacio, 'borrador': borrador_id, 'intento': int(intento),
            'estado': 'reservado', 'hora': _ahora(), 'orden': _orden(), 'hora_resultado': None,
            'proveedor': borrador.proveedor, 'cuenta': borrador.cuenta,
            'destinatarios': {'para': list(borrador.para), 'cc': list(borrador.cc), 'cco': list(borrador.cco)},
            'informe': borrador.extra.get('informe'), 'huella_informe': huella_del_informe(borrador),
            'adjuntos': [{'nombre': a.nombre, 'tamano': a.tamano, 'sha256': a.sha256} for a in borrador.adjuntos],
            'enlace': borrador.enlace, 'message_id': message_id(clave), 'id_proveedor': None, 'codigo': None,
            'motivo': '', 'resolucion': None, 'pasos': [],
        }
        self.carpeta.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
        except FileExistsError:
            # Puede estar a medio escribir por el otro hilo: se espera a leerlo entero.
            for _ in range(200):
                existente = self.recibo(clave)
                if existente is not None:
                    return existente, False
                threading.Event().wait(0.01)
            raise EnvioError('El envío está reservado y su recibo no se puede leer.') from None
        try:
            os.write(fd, (json.dumps(recibo, ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
            os.fsync(fd)
        finally:
            os.close(fd)
        return recibo, True

    def marcar(self, clave: str, estado: str, **campos: Any) -> dict[str, Any]:
        if estado not in ESTADOS:
            raise ValueError(estado)
        with self._lock:
            recibo = self.recibo(clave)
            if recibo is None:
                raise EnvioError('No hay recibo de ese envío.')
            recibo.update(campos, estado=estado)
            if estado not in SIN_RESULTADO:
                recibo['hora_resultado'] = _ahora()
            publicar_duradero(self._ruta(clave), json.dumps(recibo, ensure_ascii=False, indent=1) + '\n')
            return recibo

    def anotar_paso(self, clave: str, paso: dict[str, Any]) -> dict[str, Any]:
        """110:RF-10: cada paso de un envío con enlace (el permiso, luego el correo) con su propio recibo."""
        recibo = self.recibo(clave)
        if recibo is None:
            raise EnvioError('No hay recibo de ese envío.')
        return self.marcar(clave, recibo['estado'], pasos=[*recibo.get('pasos', []), {**paso, 'hora': _ahora()}])

    def cancelar(self, clave: str) -> dict[str, Any]:
        """Antes de llamar al proveedor se puede cancelar; durante la llamada, no a medias (P7)."""
        recibo = self.recibo(clave)
        if recibo is None or recibo['estado'] != 'reservado':
            raise EnvioError('Este envío ya no se puede cancelar: el proveedor ya lo tiene o ya terminó.')
        return self.marcar(clave, 'cancelado', motivo='cancelado antes de enviarlo')

    def resolver(self, clave: str, *, llego: bool) -> dict[str, Any]:
        """El operador dice si un desconocido llegó (lo vio en «Enviados») o no (110:RF-9)."""
        recibo = self.recibo(clave)
        if recibo is None or recibo['estado'] != 'desconocido':
            raise EnvioError('Solo se resuelve un envío cuyo resultado se desconoce.')
        if llego:
            return self.marcar(clave, 'aceptado', resolucion='llego',
                               motivo='el operador lo vio en Enviados de su cuenta')
        return self.marcar(clave, 'rechazado', resolucion='no_llego', motivo='el operador dice que no llegó')

    def reconciliar_al_arrancar(self) -> list[str]:
        """Lo que quedó sin resultado por un reinicio pasa a desconocido; nunca se relanza solo (110:RF-9)."""
        cambiados = []
        for recibo in self.recibos():
            if recibo.get('estado') in SIN_RESULTADO:
                self.marcar(recibo['clave'], 'desconocido',
                            motivo='el envío se interrumpió: compruebe en Enviados de su cuenta si salió')
                cambiados.append(recibo['clave'])
        return cambiados

    def contactos_habituales(self, cuenta: str) -> set[str]:
        """110:RF-14: las direcciones con algún envío aceptado desde este espacio, más la cuenta del operador."""
        habituales = {str(cuenta).strip().lower()}
        for recibo in self.recibos():
            if recibo.get('estado') == 'aceptado':
                for lista in (recibo.get('destinatarios') or {}).values():
                    habituales.update(str(d) for d in lista or ())
        return habituales

    def intento_para(self, espacio: str, borrador_id: str, firma: str) -> int:
        """El intento que toca: el mismo mientras el último no admita otro; el siguiente tras un rechazo."""
        intento = 1
        while True:
            recibo = self.recibo(clave_envio(espacio, borrador_id, firma, intento))
            if recibo is None or recibo.get('estado') not in REINTENTABLES:
                return intento
            intento += 1



def excede_limite(borrador: Borrador, proveedor: ProveedorCorreo) -> bool:
    """110:RF-10: si los adjuntos pasan del límite del proveedor; la vista previa ofrece entonces el enlace."""
    return sum(a.tamano for a in borrador.adjuntos) > proveedor.limite_adjuntos


def _resultado_a_recibo(diario: DiarioEnvios, clave: str, resultado: ResultadoEnvio) -> dict[str, Any]:
    return diario.marcar(clave, resultado.estado, id_proveedor=resultado.id_proveedor, codigo=resultado.codigo,
                         motivo=resultado.motivo)


def enviar(diario: DiarioEnvios, borrador: Borrador, firma: str, *, espacio: str, borrador_id: str,
           proveedor: ProveedorCorreo, credenciales: FuenteDeCredenciales,
           construir: Callable[[Borrador, str], bytes], compartidor: Compartidor | None = None,
           reservada: str | None = None) -> dict[str, Any]:
    """Envía un borrador confirmado una sola vez y devuelve su recibo (110:RF-4, RF-5, RF-7, RF-8, RF-9, RF-10).

    1. La firma que vio el operador se comprueba otra vez con los adjuntos del disco; si no vale, ni reserva ni
       llamada (``ConfirmacionAnulada``).
    2. Se reserva la clave del intento que toca; si ya estaba, se devuelve su recibo sin llamar a nadie. Si la ruta
       de confirmar ya la reservó al encolar (``reservada``), se usa esa y solo sigue si sigue en ``reservado``.
    3. Con un enlace, primero el permiso de lectura a esos destinatarios exactos (109:RF-10); si no queda concedido,
       el correo no sale.
    4. Se pide el token con solo el permiso de enviar y se llama al proveedor; su respuesta, ya traducida, es el
       estado del recibo. Una salida a la red apagada no deja salir nada: rechazado. Una excepción inesperada del
       proveedor, con el cuerpo quizá entregado, es un desconocido.
    """
    if reservada is None:
        comprobar_firma(borrador, firma)
        intento = diario.intento_para(espacio, borrador_id, firma)
        clave = clave_envio(espacio, borrador_id, firma, intento)
        recibo, nuevo = diario.reservar(clave, borrador, espacio=espacio, borrador_id=borrador_id, intento=intento)
        if not nuevo:
            return recibo
    else:
        clave = reservada
        recibo = diario.recibo(clave)
        if recibo is None:
            raise EnvioError('No hay recibo de ese envío.')
        if recibo.get('estado') != 'reservado':
            # Ya lo atendió otro trabajo, o se canceló: nunca una segunda llamada (110:RF-7).
            return recibo
        try:
            comprobar_firma(borrador, firma)
        except ConfirmacionAnulada as exc:
            diario.marcar(clave, 'cancelado', motivo=str(exc))
            raise
    if borrador.enlace:
        expediente = str(borrador.extra.get('expediente') or '')
        if compartidor is None or not expediente:
            return diario.marcar(clave, 'rechazado', motivo='no hay cómo dar acceso al expediente del enlace')
        permiso = dict(compartidor.conceder_lectura(expediente, borrador.destinatarios()))
        diario.anotar_paso(clave, {'paso': 'permiso', 'expediente': expediente, 'estado': permiso.get('estado'),
                                   'id': permiso.get('id'), 'motivo': permiso.get('motivo', '')})
        if permiso.get('estado') != 'concedido':
            return diario.marcar(clave, 'rechazado',
                                 motivo=f'no se dio acceso al expediente: {permiso.get("motivo") or "sin motivo"}; '
                                        'el correo no se envió')
    try:
        token = credenciales.token(borrador.proveedor, borrador.cuenta, proveedor.alcance)
    except CuentaNoConectada:
        return diario.marcar(clave, 'rechazado', motivo='la cuenta no está conectada: vuelva a conectar la cuenta')
    try:
        mensaje = construir(borrador, clave)
    except ConfirmacionAnulada as exc:
        # 110:RF-4: un adjunto cambió entre la confirmación y este instante: no sale, y se pide revisarlo.
        diario.marcar(clave, 'cancelado', motivo=str(exc))
        raise
    diario.marcar(clave, 'enviando')
    try:
        resultado = proveedor.enviar(mensaje, token=token)
    except SalidaApagada as exc:
        # 086:RF-22: el adaptador se cortó antes de abrir la red; el correo seguro que no salió.
        return diario.marcar(clave, 'rechazado', motivo=str(exc))
    except Exception as exc:  # noqa: BLE001  (borde: el cuerpo pudo llegar, se dice desconocido y se informa)
        return diario.marcar(clave, 'desconocido', motivo=f'el envío falló sin respuesta clara ({type(exc).__name__}): '
                                                          'compruebe en Enviados de su cuenta')
    recibo = _resultado_a_recibo(diario, clave, resultado)
    if borrador.enlace:
        recibo = diario.anotar_paso(clave, {'paso': 'correo', 'estado': resultado.estado,
                                            'id': resultado.id_proveedor})
    return recibo
