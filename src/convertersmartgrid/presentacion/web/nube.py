"""Vínculos con la nube y sus versiones (109:RF-7, RF-8, RF-17).

``<espacio>/nube/vinculos.json`` dice, por cada casilla o libro importado de la nube, de qué fichero remoto viene, qué
revisión se importó y qué copia usa. Comprobar las versiones es un trabajo: lee solo los metadatos, y sin conexión
(o con la salida apagada) cada vínculo dice que no se pudo comprobar, sin tocar nada (RF-17). La versión nueva se trae
como otra copia, se compara con la vigente y entra solo con la confirmación del operador (RF-8): la copia anterior no
se borra nunca, y los estudios, datasets y calibraciones hechos con ella conservan su huella.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from ...adaptadores.entrada.nube import Copia, leer_ficha
from ...adaptadores.nube.proveedor import ErrorNube
from ...dominio.salidas_red import SalidaApagada
from ...dominio.util import publicar_duradero

VINCULOS = 'vinculos.json'
_TEXTO = frozenset({'.txt', '.csv', '.json', '.xml', '.dat'})
_cerrojo = threading.Lock()


def carpeta_nube(ws) -> Path:
    return Path(ws.root) / 'nube'


def carpeta_copias(ws) -> Path:
    """Las copias fijas de lo importado: ``<espacio>/nube/copias/<sha256>/`` (109:RF-3)."""
    return carpeta_nube(ws) / 'copias'


def carpeta_recibos(ws) -> Path:
    """Los recibos de publicar y compartir del espacio (109:RF-12)."""
    return carpeta_nube(ws) / 'recibos'


def carpeta_paquetes(ws) -> Path:
    """Los paquetes cerrados con su manifiesto, listos para publicar (109:RF-9)."""
    return carpeta_nube(ws) / 'paquetes'


def _ahora() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def leer_vinculos(ws) -> dict[str, dict]:
    try:
        datos = json.loads((carpeta_nube(ws) / VINCULOS).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _guardar(ws, vinculos: dict[str, dict]) -> None:
    publicar_duradero(carpeta_nube(ws) / VINCULOS, json.dumps(vinculos, ensure_ascii=False, indent=1, sort_keys=True))


def id_vinculo(destino: dict) -> str:
    return hashlib.sha256(json.dumps(destino, sort_keys=True).encode('utf-8')).hexdigest()[:16]


def _copia_publica(ws, copia: Copia) -> dict:
    f = copia.ficha
    return {'copia': copia.carpeta.relative_to(Path(ws.root)).as_posix(), 'nombre': f['nombre'], 'sha256': f['sha256'],
            'tamano': f['tamano'], 'revision': f['revision'], 'formato_origen': f['formato_origen'],
            'formato_exportado': f['formato_exportado'], 'importado': f['importado']}


def registrar_vinculo(ws, destino: dict, copia: Copia) -> dict:
    """La casilla o el libro ``destino`` usa ahora ``copia``; lo anterior queda en el historial."""
    vid = id_vinculo(destino)
    with _cerrojo:
        vinculos = leer_vinculos(ws)
        previo = vinculos.get(vid)
        historial = list((previo or {}).get('historial') or [])
        if previo and previo.get('vigente'):
            historial.append(previo['vigente'])
        vinculos[vid] = {'id': vid, 'destino': destino, 'proveedor': copia.ficha['proveedor'],
                         'item_id': copia.ficha['id'], 'nombre_remoto': copia.ficha['nombre_remoto'],
                         'vigente': _copia_publica(ws, copia), 'historial': historial, 'estado': 'al_dia',
                         'comprobado': _ahora(), 'motivo': None, 'nueva': None, 'candidata': None}
        _guardar(ws, vinculos)
    return vinculos[vid]


def vinculo(ws, vid: str) -> dict:
    v = leer_vinculos(ws).get(vid)
    if v is None:
        raise KeyError(vid)
    return v


def _actualizar(ws, vid: str, **cambios) -> dict:
    with _cerrojo:
        vinculos = leer_vinculos(ws)
        vinculos[vid] = {**vinculos[vid], **cambios}
        _guardar(ws, vinculos)
        return vinculos[vid]


def comprobar_versiones(ws, abrir_proveedor, ctx=None) -> dict:
    """109:RF-7, RF-17: por cada vínculo, si hay una revisión nueva; sin conexión, «no se pudo comprobar»."""
    vinculos = leer_vinculos(ws)
    resumen = {'nuevas': 0, 'al_dia': 0, 'sin_comprobar': 0}
    for indice, (vid, v) in enumerate(sorted(vinculos.items())):
        if ctx is not None:
            ctx.check_cancel()
            ctx.progress(indice + 1, len(vinculos), v['nombre_remoto'])
        try:
            meta = abrir_proveedor(v['proveedor']).metadatos(v['item_id'])
        except (ErrorNube, SalidaApagada) as exc:
            _actualizar(ws, vid, estado='sin_comprobar', comprobado=_ahora(),
                        motivo=f'No se pudo comprobar si hay una versión nueva: {exc}')
            resumen['sin_comprobar'] += 1
            continue
        if meta.revision != v['vigente']['revision']:
            _actualizar(ws, vid, estado='nueva', comprobado=_ahora(), motivo=None,
                        nueva={'revision': meta.revision, 'tamano': meta.tamano, 'modificado': meta.modificado})
            resumen['nuevas'] += 1
        else:
            _actualizar(ws, vid, estado='al_dia', comprobado=_ahora(), motivo=None, nueva=None)
            resumen['al_dia'] += 1
    return resumen


def comparar(anterior: Path, nueva: Path) -> dict:
    """Lo que cambia de una copia a otra: tamaño, huella y, en los de texto, líneas añadidas y quitadas."""
    fa, fb = leer_ficha(anterior), leer_ficha(nueva)
    salida = {'anterior': {'tamano': fa['tamano'], 'sha256': fa['sha256'], 'revision': fa['revision'],
                           'modificado': fa.get('modificado_remoto')},
              'nueva': {'tamano': fb['tamano'], 'sha256': fb['sha256'], 'revision': fb['revision'],
                        'modificado': fb.get('modificado_remoto')},
              'iguales': fa['sha256'] == fb['sha256']}
    if Path(fb['nombre']).suffix.lower() in _TEXTO:
        def lineas(carpeta: Path, ficha: dict) -> dict[str, int]:
            cuenta: dict[str, int] = {}
            with (carpeta / ficha['nombre']).open(encoding='utf-8', errors='replace') as fh:
                for linea in fh:
                    cuenta[linea] = cuenta.get(linea, 0) + 1
            return cuenta
        a, b = lineas(anterior, fa), lineas(nueva, fb)
        salida['lineas'] = {'anadidas': sum(max(0, n - a.get(k, 0)) for k, n in b.items()),
                            'quitadas': sum(max(0, n - b.get(k, 0)) for k, n in a.items())}
    return salida


def traer_nueva(ws, vid: str, importar_copia) -> dict:
    """109:RF-7: trae la versión nueva como otra copia (sin asignarla) y la compara con la vigente."""
    v = vinculo(ws, vid)
    copia = importar_copia(v['proveedor'], v['item_id'])
    anterior = Path(ws.root) / v['vigente']['copia']
    comparacion = comparar(anterior, copia.carpeta)
    _actualizar(ws, vid, candidata={**_copia_publica(ws, copia), 'comparacion': comparacion},
                estado='nueva' if not comparacion['iguales'] else 'al_dia')
    return {'vinculo': vid, 'comparacion': comparacion}


def aceptar(ws, vid: str, confirmar: bool, asignar) -> dict:
    """109:RF-8: la nueva entra solo con la confirmación; la anterior se conserva en el historial y en el disco."""
    if confirmar is not True:
        raise ValueError('La versión nueva solo entra con su confirmación.')
    v = vinculo(ws, vid)
    candidata = v.get('candidata')
    if not candidata:
        raise ValueError('Primero traiga la versión nueva y revise la comparación.')
    carpeta = Path(ws.root) / candidata['copia']
    ficha = leer_ficha(carpeta)
    copia = Copia(carpeta, carpeta / ficha['nombre'], ficha)
    asignar(v['destino'], copia)
    return registrar_vinculo(ws, v['destino'], copia)
