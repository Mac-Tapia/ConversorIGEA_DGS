"""OneDrive y SharePoint por Microsoft Graph v1.0 en REST (109:RF-3, RF-6, RF-7, RF-9, RF-10).

``driveItem`` con ``eTag``, ``cTag`` y ``file.hashes``: la revisión es el ``cTag``, que cambia solo con el contenido
(el ``eTag`` cambia también con los metadatos). La descarga va por ``@microsoft.graph.downloadUrl``, que se compara
con los hosts antes de pedirla y no lleva el token (es una URL ya autorizada); la subida, por ``createUploadSession``
con ``@microsoft.graph.conflictBehavior=fail`` (RF-9); y el permiso por ``invite`` con ``roles=["read"]`` y
``requireSignIn=true`` (RF-10). Referencia: https://learn.microsoft.com/graph/api/resources/driveitem
"""
from __future__ import annotations

from typing import BinaryIO
from urllib.parse import quote

from .http import Hosts, Transporte
from .proveedor import ErrorNube, Item, NoEncontrado, Pagina, SinConexion, YaExiste

#: ``*.sharepoint.com`` (OneDrive de empresa y su sesión de subida) y ``*.1drv.com`` (la descarga de la personal).
HOSTS = Hosts(frozenset({'graph.microsoft.com', 'api.onedrive.com'}), ('.sharepoint.com', '.1drv.com'))
API = 'https://graph.microsoft.com/v1.0'
#: Graph exige bloques múltiplos de 320 KiB.
BLOQUE_SUBIDA = 32 * 320 * 1024


class OneDrive:
    nombre = 'microsoft'

    def __init__(self, transporte: Transporte, *, tam_pagina: int = 200, bloque: int = BLOQUE_SUBIDA) -> None:
        self.t = transporte
        self.tam_pagina = tam_pagina
        self.bloque = bloque

    @staticmethod
    def _item(d: dict) -> Item:
        fichero = d.get('file') or {}
        hashes = fichero.get('hashes') or {}
        huellas = {}
        if hashes.get('sha256Hash'):
            huellas['sha256'] = str(hashes['sha256Hash']).lower()
        if hashes.get('quickXorHash'):
            huellas['quickxor'] = str(hashes['quickXorHash'])
        return Item('microsoft', str(d['id']), str(d.get('name') or d['id']), str(d.get('cTag') or d.get('eTag') or ''),
                    int(d['size']) if d.get('size') is not None else None, str(fichero.get('mimeType') or ''),
                    huellas, str(d.get('lastModifiedDateTime') or ''), 'folder' in d, False,
                    str((d.get('parentReference') or {}).get('id') or ''))

    def _url_item(self, item_id: str) -> str:
        return f'{API}/me/drive/items/{quote(item_id, safe="")}'

    def metadatos(self, item_id: str) -> Item:
        return self._item(self.t.json('GET', self._url_item(item_id)))

    def listar(self, carpeta_id: str, siguiente: str | None = None) -> Pagina:
        # 109:RF-16: el «@odata.nextLink» viene del servidor; el transporte lo compara con los hosts antes de pedirlo.
        url = siguiente or f'{self._url_item(carpeta_id)}/children?$top={self.tam_pagina}'
        d = self.t.json('GET', url)
        return Pagina(tuple(self._item(x) for x in d.get('value') or []), d.get('@odata.nextLink'))

    def descargar(self, item: Item, destino: BinaryIO, *, desde: int = 0) -> int:
        d = self.t.json('GET', self._url_item(item.id))
        url = d.get('@microsoft.graph.downloadUrl')
        if not url:
            raise ErrorNube(f'OneDrive no dio la dirección de descarga de «{item.nombre}».')
        cabeceras = {'Range': f'bytes={desde}-'} if desde else None
        return self.t.bajar(self.t.comprobar(url), destino, cabeceras=cabeceras, autenticar=False, ya=desde)

    def exportar(self, item: Item, destino: BinaryIO) -> tuple[str, str]:
        raise ErrorNube(f'«{item.nombre}» no es un fichero que OneDrive deje exportar.')

    def buscar_por_clave(self, carpeta_id: str, nombre: str, clave: str, huellas: dict[str, str]) -> Item | None:
        """109:RF-13: el fichero con ese nombre en la carpeta, si su huella es la del paquete (lo subió este envío)."""
        try:
            d = self.t.json('GET', f'{self._url_item(carpeta_id)}:/{quote(nombre, safe="")}')
        except NoEncontrado:
            return None
        item = self._item(d)
        comunes = [k for k in ('sha256', 'quickxor') if k in item.huellas and k in huellas]
        if comunes and all(item.huellas[k].lower() == huellas[k].lower() for k in comunes):
            return item
        return None

    def subir(self, carpeta_id: str, nombre: str, origen: BinaryIO, tamano: int, *, clave: str) -> Item:
        """109:RF-9: sesión de subida que falla si el nombre existe (nunca sobrescribe) y se reanuda tras un corte."""
        try:
            d = self.t.json('POST', f'{self._url_item(carpeta_id)}:/{quote(nombre, safe="")}:/createUploadSession',
                            json={'item': {'@microsoft.graph.conflictBehavior': 'fail', 'name': nombre}})
        except YaExiste as exc:
            raise YaExiste(f'En la carpeta de destino ya hay un «{nombre}»; no se pisa.') from exc
        sesion = self.t.comprobar(str(d.get('uploadUrl') or ''))
        hecho, cortes = 0, 0
        while True:
            origen.seek(hecho)
            trozo = origen.read(self.bloque)
            try:
                # La URL de la sesión ya está autorizada: Graph pide no mandarle el token.
                r = self.t.pedir('PUT', sesion, data=trozo, autenticar=False,
                                 cabeceras={'Content-Range': f'bytes {hecho}-{hecho + len(trozo) - 1}/{tamano}'})
            except SinConexion:
                cortes += 1
                if cortes > 3:
                    raise
                estado = self.t.json('GET', sesion, autenticar=False)
                hecho = int(str((estado.get('nextExpectedRanges') or ['0-'])[0]).split('-')[0])
                continue
            if r.status_code in (200, 201):
                return self._item(r.json())
            siguiente = (r.json().get('nextExpectedRanges') or [f'{hecho + len(trozo)}-'])[0]
            hecho = int(str(siguiente).split('-')[0])

    def conceder_lectura(self, item_id: str, destinatarios: list[str]) -> list[dict]:
        """109:RF-10: solo lectura, con inicio de sesión obligatorio, a cada destinatario nombrado."""
        d = self.t.json('POST', f'{self._url_item(item_id)}/invite',
                        json={'recipients': [{'email': c} for c in destinatarios], 'roles': ['read'],
                              'requireSignIn': True, 'sendInvitation': True})
        salida = []
        for correo, permiso in zip(destinatarios, d.get('value') or []):
            salida.append({'destinatario': correo, 'id_remoto': str(permiso.get('id') or ''), 'rol': 'lectura'})
        return salida

    def enlace_publico(self, item_id: str) -> dict:
        """109:RF-11: enlace anónimo de solo lectura, solo con la autorización del operador en ese envío."""
        d = self.t.json('POST', f'{self._url_item(item_id)}/createLink', json={'type': 'view', 'scope': 'anonymous'})
        return {'destinatario': 'cualquiera con el enlace', 'id_remoto': str(d.get('id') or ''), 'rol': 'lectura',
                'enlace': str((d.get('link') or {}).get('webUrl') or '')}
