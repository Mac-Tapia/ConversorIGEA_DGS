"""Servicio de la web para la evolución de los clientes fijos (spec 105).

Toma los libros que el operador ya asignó en «2.1 · Libros de medición» (105:RF-1), lanza el cálculo como trabajo
(RF-17), guarda el último resultado del espacio con sus curvas aparte y escribe el libro en la salida, desde donde se
archiva (RF-27, RF-30). Va en un módulo propio, fuera de ``services.py``, para no mezclarse con los cambios de otras
sesiones.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import numpy as np

from ..util import write_json_atomic
from .jobs import JobContext
from .requisitos import UserError
from .workspace import Workspace

#: Donde queda el último resultado del espacio: no es una salida para el operador, sino lo que lee el tablero.
CARPETA = 'clientes_fijos'
_cache_radiales: dict[tuple[str, int], list[str]] = {}
_cerrojo = threading.Lock()


def _carpeta(ws: Workspace) -> Path:
    return ws.root / CARPETA


def _meta(ws: Workspace, tipo: str) -> dict | None:
    meta = (ws.demanda or {}).get(tipo)
    return meta if meta and Path(str(meta.get('path', ''))).exists() else None


def _libro_suministros(ws: Workspace) -> Path:
    from ..demanda_medida import DemandaError, descubrir_libro_suministros
    from . import services

    meta = _meta(ws, 'suministros')
    if not meta or not services.hay_suministros(ws):
        raise UserError('Falta el libro de suministros en «2.1 · Libros de medición»: sin él no se sabe qué clientes '
                        'son de cada alimentador.')
    try:
        return descubrir_libro_suministros(Path(meta['path']), services.demanda_alias())
    except DemandaError as exc:
        raise UserError(str(exc)) from exc


def _libros_de_cabecera(ws: Workspace, desde: str, hasta: str) -> tuple[Path, ...]:
    """Los libros de cabecera de los años del rango (025:RF-8): uno de 2025 no da la máxima de 2026."""
    from ..demanda_medida import DemandaError
    from ..libros_por_anio import arbol_de_libros, libros_del_periodo

    meta = _meta(ws, 'cabecera')
    if not meta:
        return ()
    ruta = Path(meta['path'])
    if ruta.is_file():
        return (ruta,)
    try:
        arbol = arbol_de_libros(ruta)
        rutas: dict[Path, None] = {}
        for anio in range(int(desde[:4]), int(hasta[:4]) + 1):
            rutas.update((x.ruta, None) for x in libros_del_periodo(arbol, str(anio)))
        return tuple(rutas)
    except DemandaError:
        return ()


def fuentes(ws: Workspace, desde: str, hasta: str, *, con_cabecera: bool = True):
    """Los libros del espacio para la evolución, sin pedir rutas nuevas (105:RF-1)."""
    from ..evolucion_clientes import FuentesEvolucion
    from . import services

    clientes = _meta(ws, 'clientes')
    if not clientes:
        raise UserError('Falta el libro o la carpeta de clientes importantes en «2.1 · Libros de medición».')
    medidores = _meta(ws, 'medidores')
    return FuentesEvolucion(
        clientes=Path(clientes['path']), suministros=_libro_suministros(ws),
        patron=services.perfil_de(ws).patron_libro_clientes, asignaciones=clientes.get('asignaciones') or {},
        medidores=Path(medidores['path']) if medidores and con_cabecera else None,
        cabecera=_libros_de_cabecera(ws, desde, hasta) if con_cabecera else (),
        # 105:RF-34: con la red convertida cargada, la SED de cada cliente se busca en su alimentador.
        seds_red=services.propietarios_de_sed(ws) if getattr(ws, 'dataset', None) is not None else None)


def _radiales(libro: Path) -> list[str]:
    """Los alimentadores con clientes fijos del libro de suministros, leídos una vez por versión del libro."""
    from ..demanda_medida import leer_suministros

    clave = (str(libro), libro.stat().st_mtime_ns)
    with _cerrojo:
        if clave not in _cache_radiales:
            suministros, _a = leer_suministros(libro)
            _cache_radiales.clear()
            _cache_radiales[clave] = sorted({s.radial.strip() for s in suministros if s.radial and s.radial.strip()})
        return list(_cache_radiales[clave])


def _meses_con_libro(ws: Workspace) -> list[str]:
    meta = _meta(ws, 'clientes') or {}
    return sorted({str(x['mes']) for x in meta.get('catalogo') or [] if x.get('activo') and x.get('mes')})


def ultimo(ws: Workspace) -> dict | None:
    try:
        return json.loads((_carpeta(ws) / 'ultimo.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def estado(ws: Workspace) -> dict[str, Any]:
    """Lo que el tablero necesita para pedir y mostrar (105:RF-18): opciones y último resultado."""
    from ..archivo_informes import carpeta_archivo

    faltan, alimentadores = [], []
    if not _meta(ws, 'clientes'):
        faltan.append('el libro de clientes importantes')
    try:
        alimentadores = _radiales(_libro_suministros(ws))
    except UserError:
        faltan.append('el libro de suministros')
    except (OSError, ValueError) as exc:
        faltan.append(f'un libro de suministros legible ({exc})')
    archivo = carpeta_archivo()
    return {'alimentadores': alimentadores, 'meses': _meses_con_libro(ws), 'faltan': faltan,
            'cabecera': bool(_meta(ws, 'cabecera') and _meta(ws, 'medidores')),
            'archivo': archivo.as_posix() if archivo else None, 'resultado': ultimo(ws)}


def _guardar_series(carpeta: Path, series: dict) -> None:
    temporal = carpeta / '.series.tmp.npz'
    np.savez_compressed(temporal, **{f'{c}__{k}': v for c, (t, p, q) in series.items()
                                     for k, v in (('t', t.astype('datetime64[m]').astype('int64')), ('p', p), ('q', q))})
    temporal.replace(carpeta / 'series.npz')


def curva(ws: Workspace, codigo: str) -> dict[str, Any]:
    """La curva de 15 minutos de un cliente del último resultado (105:RF-18, RF-25)."""
    ruta = _carpeta(ws) / 'series.npz'
    if not ruta.is_file():
        raise UserError('Todavía no hay una evolución calculada en este espacio.')
    with np.load(ruta) as datos:
        if f'{codigo}__t' not in datos.files:
            raise UserError(f'{codigo} no está en la última evolución calculada.')
        t = datos[f'{codigo}__t'].astype('datetime64[m]')
        p, q = datos[f'{codigo}__p'], datos[f'{codigo}__q']
    return {'codigo': codigo, 'puntos': [
        [str(ti), float(pi), float(qi) if np.isfinite(qi) else None] for ti, pi, qi in zip(t, p, q)]}


def calcular(ws: Workspace, ctx: JobContext, alimentadores: list[str], desde: str, hasta: str, *,
             con_cabecera: bool = True) -> dict[str, Any]:
    """El trabajo: lee, calcula, escribe el libro en la salida y lo archiva (105:RF-17, RF-27, RF-30, RF-31)."""
    from ..archivo_informes import ArchivoError, archivar
    from ..demanda_medida import DemandaError
    from ..evolucion_clientes import ambito, calcular_evolucion, escribir_libro

    f = fuentes(ws, desde, hasta, con_cabecera=con_cabecera)
    ctx.log(f'Clientes fijos de {", ".join(alimentadores)}, de {desde} a {hasta}, según {f.suministros.name}.')

    def avance(i: int, n: int, libro: str) -> None:
        ctx.check_cancel()
        ctx.progress(i, n + 1, f'Leyendo {libro}')

    try:
        evolucion = calcular_evolucion(f, alimentadores, desde, hasta, avance=avance)
    except (DemandaError, ValueError) as exc:
        raise UserError(str(exc)) from exc
    ctx.check_cancel()
    datos = evolucion.datos
    for a in datos['avisos']:
        ctx.log(f"Aviso ({a['tipo']}): {a['texto']}")
    nombre = ambito(alimentadores)
    periodo = f'{desde}_a_{hasta}'
    ctx.progress(1, 1, 'Escribiendo el libro')
    rel = Path(CARPETA) / f'{nombre}_{periodo}' / f'{nombre}_clientes_fijos_{periodo}.xlsx'
    libro = escribir_libro(evolucion, ws.out_dir / rel)
    datos['libro'] = rel.as_posix()
    datos['archivo'] = {'ruta': None, 'aviso': None}
    try:
        archivado = archivar(libro, 'clientes_fijos', nombre, periodo)
        if archivado is not None:
            datos['archivo']['ruta'] = archivado.as_posix()
            ctx.log(f'Archivado en {archivado}.')
    except ArchivoError as exc:
        # 105:RF-31: el libro sigue en la salida del espacio; el archivo se reintenta en la próxima vez.
        datos['archivo']['aviso'] = str(exc)
        ctx.log(f'Aviso: {exc} El libro queda en «Resultados».')
    carpeta = _carpeta(ws)
    carpeta.mkdir(parents=True, exist_ok=True)
    _guardar_series(carpeta, evolucion.series)
    write_json_atomic(carpeta / 'ultimo.json', datos)
    ctx.log(f"Libro: {rel.as_posix()} ({len(datos['clientes'])} cliente(s)).")
    return {'libro': datos['libro'], 'clientes': len(datos['clientes']), 'archivo': datos['archivo'],
            'avisos': len(datos['avisos'])}
