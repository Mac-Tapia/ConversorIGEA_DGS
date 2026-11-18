"""Las Tablas de Resultados del Informe del Estudio en Excel (aclaración de 108:RF-11).

El TdR (numeral 9.1) lista las tablas resumen que se entregan en Excel. **Cuántas son y cómo se titulan sale del
registro** (``vad.tablas_resultados``: lista de ``{numero, titulo}``); el TdR del periodo 2026-2030 lista 16, pero el
código no lo sabe. Se escribe una hoja por tabla, en el orden del registro, con su título y su cita, las filas por
sistema eléctrico y una fila de total con fórmulas vivas (``=SUM``) en cada columna numérica, más una hoja «Índice».

Una tabla sin datos no se omite ni se deja vacía en silencio: su hoja dice «Sin datos» con el motivo y el índice la
marca como hueco. Un dato de una tabla que el registro no lista se rechaza. La escritura es atómica (P6).
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...dominio.registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from ...aplicacion.vad import VadError

HOJA_INDICE = 'Índice'
_FILA_CABECERA = 4


@dataclass(frozen=True)
class TablaDatos:
    """Los datos de una tabla: sus columnas y una fila por sistema eléctrico."""

    columnas: Sequence[str]
    #: Cada fila: ``{'sistema': <nombre>, <columna>: valor}``; un valor que falta queda como hueco nombrado.
    filas: Sequence[Mapping[str, Any]] = ()
    #: Por qué la tabla no trae filas (obligatorio si no las trae).
    motivo_sin_datos: str = ''


@dataclass(frozen=True)
class LibroResultados:
    ruta: Path
    #: Número de tabla → nombre de su hoja.
    hojas: Mapping[str, str]
    #: Tablas sin datos y celdas que faltan, cada una nombrada.
    huecos: tuple[str, ...] = ()
    regla: Mapping[str, str] = field(default_factory=dict)


def tablas_registradas(registro: RegistroNormativo, fecha: str | None = None) -> tuple[list[dict[str, str]],
                                                                                      ReglaVigente]:
    try:
        rv = registro.regla('vad.tablas_resultados', fecha)
    except RegistroError as exc:
        raise VadError(f'el registro no lista las Tablas de Resultados (vad.tablas_resultados): {exc}') from exc
    lista = rv.regla.valor
    if not isinstance(lista, list) or not lista:
        raise VadError('vad.tablas_resultados tiene que ser una lista no vacía de {numero, titulo}')
    for t in lista:
        if not isinstance(t, Mapping) or not all(isinstance(t.get(c), str) and t[c].strip() for c in ('numero',
                                                                                                    'titulo')):
            raise VadError(f'una Tabla de Resultados del registro no trae número y título: {t!r}')
    numeros = [t['numero'] for t in lista]
    if len(set(numeros)) != len(numeros):
        raise VadError(f'números de tabla repetidos en el registro: {numeros}')
    return [dict(t) for t in lista], rv


def _numero(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _validar(numero: str, datos: TablaDatos) -> None:
    if not isinstance(datos, TablaDatos):
        raise VadError(f'los datos de la tabla {numero} tienen que ser TablaDatos')
    columnas = list(datos.columnas)
    if not columnas or not all(isinstance(c, str) and c.strip() for c in columnas):
        raise VadError(f'la tabla {numero} necesita columnas con nombre')
    if len(set(columnas)) != len(columnas) or 'sistema' in columnas:
        raise VadError(f'la tabla {numero} repite columnas o usa «sistema» como columna: {columnas}')
    sistemas = []
    for fila in datos.filas:
        if not isinstance(fila, Mapping) or not str(fila.get('sistema') or '').strip():
            raise VadError(f'cada fila de la tabla {numero} necesita su sistema eléctrico: {fila!r}')
        extra = sorted(set(fila) - set(columnas) - {'sistema'})
        if extra:
            raise VadError(f'la tabla {numero}, sistema {fila["sistema"]}, trae columnas que no declara: {extra}')
        for c in columnas:
            v = fila.get(c)
            if v is not None and not _numero(v) and not isinstance(v, str):
                raise VadError(f'la tabla {numero}, sistema {fila["sistema"]}, columna {c}: valor no admitido {v!r}')
        sistemas.append(fila['sistema'])
    if len(set(sistemas)) != len(sistemas):
        raise VadError(f'la tabla {numero} repite sistemas eléctricos')
    if not datos.filas and not datos.motivo_sin_datos.strip():
        raise VadError(f'la tabla {numero} no trae filas ni dice por qué')


def _hoja(numero: str) -> str:
    nombre = f'Tabla {numero}'
    if len(nombre) > 31 or any(ch in nombre for ch in '[]:*?/\\'):
        raise VadError(f'el número de tabla {numero!r} no sirve de nombre de hoja de Excel')
    return nombre


def escribir_tablas(registro: RegistroNormativo, datos: Mapping[str, TablaDatos], destino: Path | str,
                    fecha: str | None = None) -> LibroResultados:
    """Escribe el libro en ``destino`` con una hoja por cada tabla del registro y devuelve sus huecos."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    tablas, rv = tablas_registradas(registro, fecha)
    registradas = {t['numero'] for t in tablas}
    extra = sorted(set(datos) - registradas)
    if extra:
        raise VadError(f'datos de tablas que el TdR registrado no lista: {", ".join(extra)}')
    for numero, d in datos.items():
        _validar(numero, d)
    cita = f'{rv.norma.acto}, {rv.regla.articulo_o_anexo}, líneas {rv.regla.lineas}'.strip(', ')
    libro = Workbook()
    indice = libro.active
    indice.title = HOJA_INDICE
    indice.append(['N°', 'Título', 'Estado', 'Hoja', 'Fuente'])
    hojas: dict[str, str] = {}
    huecos: list[str] = []
    for t in tablas:
        numero, titulo = t['numero'], t['titulo']
        nombre = _hoja(numero)
        hoja = libro.create_sheet(nombre)
        hojas[numero] = nombre
        hoja['A1'] = f'Tabla {numero}. {titulo}'
        hoja['A2'] = f'Fuente: {cita}'
        d = datos.get(numero)
        if d is None or not d.filas:
            motivo = (d.motivo_sin_datos if d is not None else 'el estudio no entrega sus datos')
            hoja.cell(_FILA_CABECERA, 1, f'Sin datos: {motivo}')
            huecos.append(f'Tabla {numero} ({titulo}): sin datos: {motivo}')
            indice.append([numero, titulo, 'hueco', nombre, cita])
            continue
        columnas = list(d.columnas)
        hoja.cell(_FILA_CABECERA, 1, 'Sistema eléctrico')
        for j, c in enumerate(columnas, 2):
            hoja.cell(_FILA_CABECERA, j, c)
        primera = _FILA_CABECERA + 1
        for i, fila in enumerate(d.filas, primera):
            hoja.cell(i, 1, fila['sistema'])
            for j, c in enumerate(columnas, 2):
                v = fila.get(c)
                if v is None:
                    huecos.append(f'Tabla {numero}, sistema {fila["sistema"]}, columna {c}: sin valor')
                    continue
                hoja.cell(i, j, v)
        ultima = primera + len(d.filas) - 1
        hoja.cell(ultima + 1, 1, 'Total')
        for j, c in enumerate(columnas, 2):
            if all(_numero(f.get(c)) for f in d.filas):
                letra = get_column_letter(j)
                hoja.cell(ultima + 1, j, f'=SUM({letra}{primera}:{letra}{ultima})')
        indice.append([numero, titulo, 'con datos', nombre, cita])
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.csg-', suffix='.xlsx', dir=destino.parent)
    os.close(fd)
    try:
        libro.save(tmp)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return LibroResultados(destino, hojas, tuple(huecos), {'clave': rv.regla.clave, 'acto': rv.norma.acto,
                                                           'huella': rv.huella()})
