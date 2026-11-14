"""012:RF-73 a RF-82: las entradas que faltan a los estudios, cargadas desde la web y guardadas por proyecto.

Usuario, 2026-11-13: «todo tiene que ser cargado desde la web». El operador suelta un TXT, CSV,
PDF o una imagen en la entrada que le falta a un estudio de «4.2 Estudios»; la lectura (con OCR si
hace falta, que tarda) va como trabajo del motor y deja un **borrador** con las filas leídas; el
operador las ve en una tabla editable, corrige lo que el OCR leyó mal y «Guardar» valida y guarda.
Nada de lo leído cuenta para el catálogo hasta que se confirma: una cifra del OCR sin revisar no
puede convertir en «disponible» un cortocircuito.

Todo vive en la carpeta del espacio, por proyecto de DIgSILENT, como el libro de la empresa:
``<espacio>/entradas_estudios/<proyecto>/<entrada>.json`` lo confirmado, ``<entrada>.borrador.json``
lo leído sin confirmar y ``originales/`` los ficheros tal como se subieron, para saber de dónde salió
cada cifra.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from ..entradas_estudios import ESQUEMAS, EntradasError, cumplidas, esquemas_publicos, guardable, leer_entrada, texto_de
from ..util import nombre_seguro
from .api_contract import JobRespuesta

KIND = 'entradas_estudios'
#: Lo que se admite subir: texto, PDF e imágenes (usuario: «TXT o en imagen, JPG o similares»).
EXTENSIONES = ('.txt', '.csv', '.tsv', '.dat', '.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp')


class GuardarEntradaPeticion(BaseModel):
    """012:RF-77: las filas que el operador confirmó en la tabla, tal como las ve."""
    model_config = ConfigDict(extra='forbid')
    project: str = Field(min_length=1, max_length=256)
    filas: list[dict[str, Any]] = Field(max_length=200_000)


# --------------------------------------------------------------------------- almacén
def carpeta(ws, project: str) -> Path:
    """La carpeta de las entradas del proyecto dentro del espacio (RF-82)."""
    return Path(ws.root) / 'entradas_estudios' / nombre_seguro(project.strip(), defecto='PROYECTO')


def _leer(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else None
    except (OSError, ValueError):
        return None


def _escribir(ruta: Path, datos: dict) -> None:
    """Escritura atómica: una entrada a medias haría creer al catálogo que hay datos que no hay."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name, suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)


def guardadas(ws, project: str) -> dict[str, dict]:
    """Lo confirmado del proyecto, por entrada (RF-77, RF-82)."""
    if not project or not project.strip():
        return {}
    c = carpeta(ws, project)
    return {k: g for k in ESQUEMAS if (g := _leer(c / f'{k}.json')) is not None}


def entradas_cargadas(ws, project: str) -> set[str]:
    """Los ``Entrada.nombre`` que el catálogo da por cumplidos en el proyecto (RF-79)."""
    return cumplidas(guardadas(ws, project)) if ws is not None else set()


def registros_para_plan(ws, project: str) -> dict[str, dict]:
    """Lo que viaja en el plan de ``tools/estudios_pf.py``: el registro de cada entrada (RF-83, RF-84)."""
    return {k: {'registro': g['registro'], 'fichero': g.get('fichero'), 'confirmado': g.get('confirmado')}
            for k, g in guardadas(ws, project).items()}


def estado(ws, project: str) -> dict:
    """Esquemas, lo guardado y los borradores del proyecto, para la web (RF-75, RF-80)."""
    c = carpeta(ws, project) if project.strip() else None
    borradores = {k: b for k in ESQUEMAS if c is not None and (b := _leer(c / f'{k}.borrador.json')) is not None}
    resumen = {k: {'fichero': g.get('fichero'), 'confirmado': g.get('confirmado'), 'faltan': g.get('faltan') or [],
                   'completa': bool(g.get('completa')), 'filas': g.get('filas') or []}
               for k, g in guardadas(ws, project).items()}
    return {'project': project.strip(), 'esquemas': esquemas_publicos(), 'guardadas': resumen,
            'borradores': borradores, 'cumplidas': sorted(cumplidas(guardadas(ws, project)))}


def leer_ficheros(ws, project: str, clave: str, ficheros: list[tuple[Path, str]], ctx=None) -> dict:
    """Lee cada fichero, junta sus filas y deja el borrador (RF-74, RF-75, RF-76).

    Varias fotos de una misma tabla se suben juntas: sus filas se suman, y la cabecera se busca en
    cada una (el OCR de la segunda foto no trae la cabecera si no se fotografió).
    """
    if clave not in ESQUEMAS:
        raise ValueError(f'«{clave}» no es una entrada de los estudios.')
    c = carpeta(ws, project)
    originales = c / 'originales'
    originales.mkdir(parents=True, exist_ok=True)
    total = {'clave': clave, 'filas': [], 'errores': [], 'avisos': [], 'faltan': [], 'ficheros': [],
             'metodos': [], 'leido': datetime.now().isoformat(timespec='seconds')}
    cabecera_previa: str | None = None
    for i, (ruta, nombre) in enumerate(ficheros):
        if ctx is not None:
            ctx.check_cancel()
            ctx.progress(i, len(ficheros), nombre)
        sello = datetime.now().strftime('%Y%m%d-%H%M%S')
        copia = originales / f'{sello}_{nombre_seguro(Path(nombre).stem, defecto="fichero")}{Path(nombre).suffix.lower()}'
        shutil.copyfile(ruta, copia)
        texto, metodo, avisos = texto_de(copia)
        lec = leer_entrada(clave, texto, fichero=nombre, metodo=metodo, avisos=avisos)
        if lec.errores and cabecera_previa and any('ninguna fila tiene los nombres' in e for e in lec.errores):
            # La foto siguiente de la misma tabla: se lee con la cabecera de la anterior.
            lec = leer_entrada(clave, cabecera_previa + '\n' + texto, fichero=nombre, metodo=metodo, avisos=avisos)
        elif texto.strip() and not any('ninguna fila tiene los nombres' in e for e in lec.errores):
            cabecera_previa = next((ln for ln in texto.splitlines() if ln.strip() and not ln.lstrip().startswith('#')),
                                   None)
        if ctx is not None:
            ctx.log(f'{nombre}: {len(lec.filas)} fila(s) leídas por {metodo}'
                    + (f'; {len(lec.errores)} a revisar' if lec.errores else ''))
        total['filas'] += lec.filas
        total['avisos'] += lec.avisos
        total['ficheros'].append(copia.name)
        total['metodos'].append(metodo)
        total['columnas'] = lec.columnas
    from ..entradas_estudios import validar

    _registro, errores, falta = validar(clave, total['filas'])
    total['errores'], total['faltan'] = errores, falta
    _escribir(c / f'{clave}.borrador.json', total)
    return {'clave': clave, 'filas': len(total['filas']), 'errores': len(errores), 'faltan': falta}


def confirmar(ws, project: str, clave: str, filas: list[dict[str, Any]]) -> dict:
    """Valida las filas confirmadas y las guarda; un error en una celda no guarda nada (RF-77)."""
    if clave not in ESQUEMAS:
        raise ValueError(f'«{clave}» no es una entrada de los estudios.')
    g = guardable(clave, filas)
    c = carpeta(ws, project)
    borrador = _leer(c / f'{clave}.borrador.json') or {}
    g.update({'filas': [dict(f) for f in filas], 'fichero': ', '.join(borrador.get('ficheros') or []) or 'tabla de la web',
              'confirmado': datetime.now().isoformat(timespec='seconds'), 'project': project.strip()})
    with ws.lock:
        _escribir(c / f'{clave}.json', g)
        (c / f'{clave}.borrador.json').unlink(missing_ok=True)
    return estado(ws, project)


# --------------------------------------------------------------------------- rutas
def registrar_rutas_entradas(app: FastAPI, *, ws_or_404, submit,
                             guardar_subida: Callable[[Path, UploadFile], None]) -> None:
    """Monta las rutas con la cola y los espacios del único servidor (012:RF-73 a RF-82).

    ``guardar_subida`` es la del servidor (``_save_upload``): la misma cuota de subida que el resto.
    """
    ruta = '/api/workspaces/{wid}/pf/entradas-estudios'

    @app.get(ruta)
    def entradas_estado(wid: str, project: str = '') -> dict:
        """012:RF-75, RF-80: qué entradas hay, cuáles están guardadas y los borradores por confirmar."""
        return estado(ws_or_404(wid), project)

    @app.post(ruta + '/{clave}/leer', status_code=202, response_model=JobRespuesta, response_model_exclude_unset=True)
    def entradas_leer(wid: str, clave: str, project: str = Form(...), files: list[UploadFile] = File(...)) -> dict:
        """012:RF-74, RF-76: lee los ficheros en un trabajo del motor (el OCR tarda) y deja el borrador."""
        ws = ws_or_404(wid)
        if clave not in ESQUEMAS:
            raise HTTPException(404, f'«{clave}» no es una entrada de los estudios.')
        if not project.strip():
            raise HTTPException(400, 'Elija el proyecto de DIgSILENT de estos datos.')
        malos = [f.filename for f in files if Path(f.filename or '').suffix.lower() not in EXTENSIONES]
        if malos:
            raise HTTPException(400, 'Solo se leen TXT, CSV, PDF o imágenes (JPG, PNG…): ' + ', '.join(map(str, malos)) + '.')
        temporal = Path(tempfile.mkdtemp(prefix='csg-entradas-'))
        ficheros = []
        try:
            for i, f in enumerate(files):
                nombre = Path(f.filename or f'fichero{i}').name
                destino = temporal / f'{i}{Path(nombre).suffix.lower()}'
                guardar_subida(destino, f)
                ficheros.append((destino, nombre))
        except BaseException:
            shutil.rmtree(temporal, ignore_errors=True)
            raise

        def trabajo(ctx) -> dict:
            try:
                return leer_ficheros(ws, project, clave, ficheros, ctx)
            finally:
                shutil.rmtree(temporal, ignore_errors=True)

        titulo = f'Leer {ESQUEMAS[clave].titulo.lower()}: ' + ', '.join(n for _r, n in ficheros)
        return submit(ws, 'entradas_estudios', titulo, trabajo, lane='engine')

    @app.put(ruta + '/{clave}')
    def entradas_guardar(wid: str, clave: str, body: GuardarEntradaPeticion) -> dict:
        """012:RF-77: guarda lo confirmado; con una celda mala, 400 con cada fila y columna."""
        ws = ws_or_404(wid)
        if clave not in ESQUEMAS:
            raise HTTPException(404, f'«{clave}» no es una entrada de los estudios.')
        try:
            return confirmar(ws, body.project, clave, body.filas)
        except EntradasError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete(ruta + '/{clave}/borrador')
    def entradas_descartar(wid: str, clave: str, project: str) -> dict:
        """012:RF-75: descarta lo leído sin confirmar; lo guardado antes sigue."""
        ws = ws_or_404(wid)
        if clave not in ESQUEMAS:
            raise HTTPException(404, f'«{clave}» no es una entrada de los estudios.')
        (carpeta(ws, project) / f'{clave}.borrador.json').unlink(missing_ok=True)
        return estado(ws, project)
