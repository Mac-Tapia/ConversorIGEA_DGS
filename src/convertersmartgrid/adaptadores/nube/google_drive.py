"""Google Drive por la API v3 en REST (109:RF-3, RF-5, RF-6, RF-9, RF-10).

``files.get`` con ``headRevisionId``, ``version``, ``md5Checksum``, ``sha256Checksum`` y ``size``; ``alt=media`` con
``Range``; ``files.export`` de las hojas nativas a XLSX (RF-5); subida ``uploadType=resumable`` con la clave de
idempotencia en ``appProperties`` (RF-13); y ``permissions.create`` con ``role=reader`` y ``type=user`` (RF-10).
Con el permiso ``drive.file`` solo se ve lo que el operador eligió o lo que la aplicación creó.
Referencia: https://developers.google.com/workspace/drive/api/reference/rest/v3
"""
from __future__ import annotations

from typing import BinaryIO
from urllib.parse import quote

from .http import Hosts, Transporte
from .proveedor import ErrorNube, Item, Pagina, SinConexion, YaExiste

HOSTS = Hosts(frozenset({'www.googleapis.com'}))
API = 'https://www.googleapis.com/drive/v3'
SUBIDA = 'https://www.googleapis.com/upload/drive/v3/files'
CARPETA = 'application/vnd.google-apps.folder'
#: Las nativas que se exportan, con su formato explícito (109:RF-5).
EXPORTACIONES = {'application/vnd.google-apps.spreadsheet':
                 ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx')}
_CAMPOS = ('id,name,mimeType,size,md5Checksum,sha256Checksum,headRevisionId,version,modifiedTime,parents,'
           'capabilities(canEdit,canAddChildren),appProperties')
#: Bloques de subida: múltiplo de 256 KiB, como exige la subida reanudable de Drive.
BLOQUE_SUBIDA = 32 * 256 * 1024


def _literal(texto: str) -> str:
    return texto.replace('\\', '\\\\').replace("'", "\\'")


class GoogleDrive:
    nombre = 'google'

    def __init__(self, transporte: Transporte, *, tam_pagina: int = 100, bloque: int = BLOQUE_SUBIDA) -> None:
        self.t = transporte
        self.tam_pagina = tam_pagina
        self.bloque = bloque

    def _item(self, d: dict) -> Item:
        tipo = str(d.get('mimeType') or '')
        carpeta = tipo == CARPETA
        nativo = tipo.startswith('application/vnd.google-apps.') and not carpeta
        huellas = {k: str(d[c]).lower() for k, c in (('sha256', 'sha256Checksum'), ('md5', 'md5Checksum')) if d.get(c)}
        capacidades = d.get('capabilities') or {}
        return Item('google', str(d['id']), str(d.get('name') or d['id']),
                    str(d.get('headRevisionId') or f"v{d.get('version', '')}"),
                    int(d['size']) if d.get('size') not in (None, '') else None, tipo, huellas,
                    str(d.get('modifiedTime') or ''), carpeta, nativo, str((d.get('parents') or [''])[0]),
                    solo_lectura=not capacidades.get('canEdit', True) or not capacidades.get('canAddChildren', True)
                    if carpeta else not capacidades.get('canEdit', True))

    def metadatos(self, item_id: str) -> Item:
        return self._item(self.t.json('GET', f'{API}/files/{quote(item_id, safe="")}',
                                      params={'fields': _CAMPOS, 'supportsAllDrives': 'true'}))

    def _consulta(self, q: str, token: str | None = None, tam: int | None = None) -> dict:
        params = {'q': q, 'fields': f'nextPageToken,files({_CAMPOS})', 'pageSize': str(tam or self.tam_pagina),
                  'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
        if token:
            params['pageToken'] = token
        return self.t.json('GET', f'{API}/files', params=params)

    def listar(self, carpeta_id: str, siguiente: str | None = None) -> Pagina:
        d = self._consulta(f"'{_literal(carpeta_id)}' in parents and trashed = false", siguiente)
        return Pagina(tuple(self._item(x) for x in d.get('files') or []), d.get('nextPageToken'))

    def descargar(self, item: Item, destino: BinaryIO, *, desde: int = 0) -> int:
        if item.nativo:
            raise ErrorNube(f'«{item.nombre}» es un documento nativo de Google: se exporta, no se descarga.')
        cabeceras = {'Range': f'bytes={desde}-'} if desde else None
        return self.t.bajar(f'{API}/files/{quote(item.id, safe="")}?alt=media&supportsAllDrives=true', destino,
                            cabeceras=cabeceras, ya=desde)

    def exportar(self, item: Item, destino: BinaryIO) -> tuple[str, str]:
        """109:RF-5: la hoja nativa, a XLSX; devuelve el formato de origen y el exportado."""
        if item.tipo not in EXPORTACIONES:
            raise ErrorNube(f'«{item.nombre}» es un documento nativo de Google ({item.tipo}) que no se sabe exportar '
                            'a un formato que lea el conversor.')
        formato, _ext = EXPORTACIONES[item.tipo]
        self.t.bajar(f'{API}/files/{quote(item.id, safe="")}/export?mimeType={quote(formato, safe="")}', destino)
        return item.tipo, formato

    def buscar_nombre(self, carpeta_id: str, nombre: str) -> Item | None:
        d = self._consulta(f"name = '{_literal(nombre)}' and '{_literal(carpeta_id)}' in parents and trashed = false",
                           tam=1)
        return self._item(d['files'][0]) if d.get('files') else None

    def buscar_por_clave(self, carpeta_id: str, nombre: str, clave: str, huellas: dict[str, str]) -> Item | None:
        """109:RF-13: lo ya subido con esta clave, por ``appProperties``, aunque el recibo local no llegara."""
        d = self._consulta(f"appProperties has {{ key='csg_clave' and value='{_literal(clave)}' }} and "
                           f"'{_literal(carpeta_id)}' in parents and trashed = false", tam=1)
        return self._item(d['files'][0]) if d.get('files') else None

    def subir(self, carpeta_id: str, nombre: str, origen: BinaryIO, tamano: int, *, clave: str) -> Item:
        """109:RF-9: subida reanudable a la carpeta, sin pisar un fichero con el mismo nombre."""
        if self.buscar_nombre(carpeta_id, nombre) is not None:
            raise YaExiste(f'En la carpeta de destino ya hay un «{nombre}»; no se pisa.')
        r = self.t.pedir('POST', SUBIDA, params={'uploadType': 'resumable', 'supportsAllDrives': 'true'},
                         json={'name': nombre, 'parents': [carpeta_id], 'appProperties': {'csg_clave': clave}},
                         cabeceras={'X-Upload-Content-Length': str(tamano)})
        sesion = self.t.comprobar(r.headers.get('Location') or '')
        hecho, cortes = 0, 0
        while True:
            origen.seek(hecho)
            trozo = origen.read(self.bloque)
            fin = hecho + len(trozo) - 1
            rango = f'bytes {hecho}-{fin}/{tamano}' if trozo else f'bytes */{tamano}'
            try:
                r = self.t.pedir('PUT', sesion, data=trozo, cabeceras={'Content-Range': rango}, aceptar=(308,))
            except SinConexion:
                cortes += 1
                if cortes > 3:
                    raise
                hecho = self._estado_subida(sesion, tamano)
                continue
            if r.status_code in (200, 201):
                return self._item(r.json())
            hecho = self._hecho(r)

    def _estado_subida(self, sesion: str, tamano: int) -> int:
        r = self.t.pedir('PUT', sesion, data=b'', cabeceras={'Content-Range': f'bytes */{tamano}'}, aceptar=(308,))
        return self._hecho(r)

    @staticmethod
    def _hecho(r) -> int:
        rango = r.headers.get('Range') or ''
        return int(rango.rsplit('-', 1)[1]) + 1 if rango else 0

    def conceder_lectura(self, item_id: str, destinatarios: list[str]) -> list[dict]:
        """109:RF-10: solo lectura, a cada destinatario nombrado, con el aviso del propio Drive."""
        salida = []
        for correo in destinatarios:
            d = self.t.json('POST', f'{API}/files/{quote(item_id, safe="")}/permissions',
                            params={'sendNotificationEmail': 'true', 'supportsAllDrives': 'true'},
                            json={'role': 'reader', 'type': 'user', 'emailAddress': correo})
            salida.append({'destinatario': correo, 'id_remoto': str(d.get('id') or ''), 'rol': 'lectura'})
        return salida

    def enlace_publico(self, item_id: str) -> dict:
        """109:RF-11: «cualquiera con el enlace», solo si el operador lo autorizó en ese envío."""
        d = self.t.json('POST', f'{API}/files/{quote(item_id, safe="")}/permissions',
                        params={'supportsAllDrives': 'true'}, json={'role': 'reader', 'type': 'anyone'})
        return {'destinatario': 'cualquiera con el enlace', 'id_remoto': str(d.get('id') or ''), 'rol': 'lectura',
                'enlace': f'https://drive.google.com/file/d/{quote(item_id, safe="")}/view'}
