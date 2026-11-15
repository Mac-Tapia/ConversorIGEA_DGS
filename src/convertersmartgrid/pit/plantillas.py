"""Motor común para llenar un formato desde su plantilla transcrita y su mapeo declarado (107-T19b).

El mapeo campo → celda vive en ``config/pit_mapeo_formatos.json``: por formato, las celdas de cabecera y los bloques
(fila de la primera línea de datos, su marca y, si la hay, la fila de total), con la fila y la letra del rótulo de
cada columna. Antes de llenar se comprueba que cada rótulo y cada marca siguen en la plantilla transcrita del
registro: si la norma cambia la plantilla, el error lo dice en lugar de llenar la columna equivocada.

Nada queda vacío en silencio: una celda sin dato lleva su motivo; un bloque sin filas, su hueco con la causa; y una
columna de la plantilla que el mapeo no cubre se nombra como hueco. Si un bloque trae más filas que las de ejemplo
de la plantilla, se dice cuántas hay que insertar (``filas_a_insertar``) y las posiciones ya cuentan con ellas.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError

__all__ = ['ESQUEMA_MAPEO', 'MAPEO', 'cargar_mapeo', 'celdas_de_formato']

ESQUEMA_MAPEO = 'pit_mapeo_formatos_v1'
MAPEO = Path(__file__).resolve().parents[3] / 'config' / 'pit_mapeo_formatos.json'
MOTOR = 'pit.plantillas'
_PUNTOS = re.compile(r'^[.…\s]+$')


def cargar_mapeo(ruta: Path | str | None = None) -> dict[str, Any]:
    ruta = Path(ruta) if ruta is not None else MAPEO
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise PitError(f'no se puede leer el mapeo de formatos {ruta} ({exc})') from exc
    if not isinstance(datos, dict) or datos.get('esquema') != ESQUEMA_MAPEO or not isinstance(
            datos.get('formatos'), dict):
        raise PitError(f'{ruta} no es un mapeo de formatos ({ESQUEMA_MAPEO})')
    return datos


def _plantilla(registro: RegistroNormativo, codigo: str, fecha: str | None) -> tuple[dict[tuple[int, str], str], Any]:
    try:
        rv = registro.regla(f'pit.formato.{codigo}', fecha)
    except RegistroError as exc:
        raise PitError(f'{codigo}: su plantilla no está transcrita en el registro normativo ({exc})') from exc
    filas = rv.regla.valor.get('filas') if isinstance(rv.regla.valor, Mapping) else None
    if not filas:
        raise PitError(f'{codigo}: la regla pit.formato.{codigo} no trae las filas de su plantilla')
    return {(f['fila'], letra): str(t) for f in filas for letra, t in f['celdas'].items()}, rv


def _comprobar(codigo: str, celdas: Mapping[tuple[int, str], str], fila: int, letra: str, texto: str) -> None:
    hallado = celdas.get((fila, letra))
    if hallado is None or ' '.join(hallado.split()) != ' '.join(texto.split()):
        raise PitError(f'{codigo}: el mapeo espera «{texto}» en {letra}{fila} y la plantilla trae {hallado!r}; '
                       'la plantilla cambió y hay que revisar config/pit_mapeo_formatos.json')


def _capacidad(celdas: Mapping[tuple[int, str], str], bloque: Mapping[str, Any]) -> int:
    """Filas de ejemplo del bloque: desde la marca, las que siguen con la misma palabra inicial o con puntos."""
    inicio = int(bloque['fila_marca'])
    palabra = str(bloque['marca']).split()[0].lower()
    ultima = inicio
    filas = sorted({f for f, letra in celdas if letra == 'A' and f > inicio})
    for f in filas:
        texto = celdas[(f, 'A')].strip()
        if (texto.split() or [''])[0].lower() == palabra or _PUNTOS.match(texto):
            ultima = f
        else:
            break
    return ultima - inicio + 1


def horizonte_de_la_norma(registro: RegistroNormativo, fecha: str | None = None) -> int:
    """Años de la serie de demanda: la regla ``pit.horizonte_demanda_anios`` del registro, nunca un número del código."""
    try:
        return int(registro.regla('pit.horizonte_demanda_anios', fecha).regla.valor)
    except RegistroError as exc:
        raise PitError(f'falta la regla pit.horizonte_demanda_anios: sin ella no se sabe cuántos años lleva la serie '
                       f'({exc})') from exc


def _letra(n: int) -> str:
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _numero(letra: str) -> int:
    n = 0
    for ch in letra:
        n = n * 26 + ord(ch) - 64
    return n


def _columnas_del_bloque(codigo: str, plantilla: Mapping[tuple[int, str], str], b: Mapping[str, Any],
                         horizonte: int | None) -> list[dict[str, Any]]:
    """Las columnas fijas del bloque y, si trae ``serie_columnas``, una por año 0..horizonte: la columna ``desde`` es
    el año 0 (su rótulo, ``rotulo_cero``) y cada año i va i columnas a la derecha con el rótulo «i»."""
    columnas = [dict(c) for c in b.get('columnas', ())]
    serie = b.get('serie_columnas')
    if not serie:
        return columnas
    base = _numero(str(serie['desde']))
    fila = int(serie['fila_rotulo'])
    for i in range(int(horizonte or 0) + 1):
        letra = _letra(base + i)
        texto = str(serie['rotulo_cero']) if i == 0 else str(i)
        if (fila, letra) not in plantilla:
            raise PitError(f'{codigo}: la norma pide {horizonte} años y la plantilla no trae la columna del año {i} '
                           f'({letra}{fila}); revisar la plantilla o la regla del horizonte')
        columnas.append({'letra': letra, 'rotulo': [fila, letra, texto], 'campo': str(serie['campo']), 'indice': i})
    return columnas


def _comprobar_serie_filas(codigo: str, plantilla: Mapping[tuple[int, str], str], b: Mapping[str, Any],
                           horizonte: int | None) -> None:
    """Serie en filas: desde ``fila_marca``, una fila por año 0..horizonte con el año en ``serie_filas.columna``."""
    columna = str(b['serie_filas'].get('columna', 'A'))
    for i in range(int(horizonte or 0) + 1):
        fila = int(b['fila_marca']) + i
        if plantilla.get((fila, columna), '').strip() != str(i):
            raise PitError(f'{codigo}: la norma pide {horizonte} años y la plantilla no trae el año {i} en '
                           f'{columna}{fila} (trae {plantilla.get((fila, columna))!r})')


def _valor(fila: Mapping[str, Any], col: Mapping[str, Any]) -> Any:
    valor = fila.get(col['campo'])
    if 'indice' not in col or valor is None:
        return valor
    i = col['indice']
    if isinstance(valor, Mapping):
        return valor.get(i, valor.get(str(i)))
    return valor[i] if isinstance(valor, (list, tuple)) and i < len(valor) else None


def celdas_de_formato(registro: RegistroNormativo, codigo: str, datos: Mapping[str, Any],
                      mapeo: Mapping[str, Any] | None = None, fecha: str | None = None) -> dict[str, Any]:
    """Las celdas de ``codigo`` con su traza y sus huecos.

    ``datos``: ``fuente`` (``nombre`` y ``huella``), ``cabecera`` (campo → valor) y ``bloques`` (bloque → filas, cada
    una campo → valor, con ``_motivos``: campo → por qué falta).
    """
    fuente = datos.get('fuente') or {}
    if not str(fuente.get('nombre') or '').strip() or not str(fuente.get('huella') or '').strip():
        raise PitError(f'{codigo}: la fuente necesita su nombre y su huella (fuente={fuente!r})')
    mapeo = cargar_mapeo() if mapeo is None else mapeo
    definicion = mapeo['formatos'].get(codigo)
    if definicion is None:
        raise PitError(f'{codigo}: sin mapeo campo → celda en config/pit_mapeo_formatos.json')
    plantilla, rv = _plantilla(registro, codigo, fecha)
    regla = {'clave': rv.regla.clave, 'norma': rv.norma.acto, 'estado': rv.estado, 'pagina': rv.regla.pagina,
             'huella': rv.huella()}
    base = {'fuente': {'nombre': str(fuente['nombre']), 'huella': str(fuente['huella'])}, 'motor': MOTOR,
            'regla': regla}
    celdas: list[dict[str, Any]] = []
    huecos: list[dict[str, Any]] = []
    insertar: dict[str, int] = {}
    for c in definicion.get('cabecera', ()):
        fila, letra, texto = c['rotulo']
        _comprobar(codigo, plantilla, fila, letra, texto)
        valor = (datos.get('cabecera') or {}).get(c['campo'])
        traza = {**base, 'campo': c['campo'], 'calculo': 'dato de la fuente'}
        if valor is None:
            traza['motivo'] = f'la fuente no trae «{c["campo"]}»'
        celdas.append({'id': f'{codigo}!cabecera:{c["campo"]}', 'cuadro': codigo, 'bloque': 'cabecera', 'fila': 0,
                       'campo': c['campo'], 'columna': texto, 'celda': f'{codigo}!{c["celda"]}', 'valor': valor,
                       'traza': traza})
    desplazamiento = 0
    horizonte = None
    for definido in definicion['bloques']:
        if ('serie_columnas' in definido or 'serie_filas' in definido) and horizonte is None:
            horizonte = horizonte_de_la_norma(registro, fecha)
        b: dict[str, Any] = {**definido, 'columnas': _columnas_del_bloque(codigo, plantilla, definido, horizonte)}
        _comprobar(codigo, plantilla, int(b['fila_marca']), 'A', str(b['marca']))
        if 'serie_filas' in b:
            _comprobar_serie_filas(codigo, plantilla, b, horizonte)
        for col in b['columnas']:
            _comprobar(codigo, plantilla, *col['rotulo'])
        rotulos = {f for col in b['columnas'] for f in [col['rotulo'][0]]}
        cubiertas = {col['letra'] for col in b['columnas']}
        sin_campo = sorted({letra for (f, letra) in plantilla if f in rotulos} - cubiertas, key=lambda x: (len(x), x))
        if sin_campo:
            huecos.append({'bloque': b['bloque'], 'causa': f'columnas de la plantilla sin campo en el conversor: '
                                                          f'{", ".join(sin_campo)}', 'columnas': sin_campo})
        filas = list((datos.get('bloques') or {}).get(b['bloque']) or ())
        capacidad = _capacidad(plantilla, b)
        primera = int(b['fila_marca']) + desplazamiento
        if len(filas) > capacidad:
            insertar[b['bloque']] = len(filas) - capacidad
        causa = f'sin {b["bloque"]} en la fuente {fuente["nombre"]}'
        if not filas:
            huecos.append({'bloque': b['bloque'], 'causa': causa, 'fila_plantilla': primera})
        for i, fila in enumerate(filas or [None], start=1):
            motivos = (fila or {}).get('_motivos') or {}
            for col in b['columnas']:
                valor = None if fila is None else _valor(fila, col)
                traza = {**base, 'campo': col['campo'], 'anio': col.get('indice'),
                         'calculo': motivos.get(f'_calculo:{col["campo"]}')
                         or 'dato de la fuente'}
                if valor is None:
                    traza['motivo'] = causa if fila is None else (
                        motivos.get(col['campo']) or f'la fuente no trae «{col["campo"]}»')
                sufijo = f'[{col["indice"]}]' if 'indice' in col else ''
                celdas.append({'id': f'{codigo}!{b["bloque"]}:{i}:{col["campo"]}{sufijo}', 'cuadro': codigo,
                               'bloque': b['bloque'], 'fila': i, 'campo': col['campo'],
                               'columna': col['rotulo'][2], 'celda': f'{codigo}!{col["letra"]}{primera + i - 1}',
                               'valor': valor, 'traza': traza})
        extra = insertar.get(b['bloque'], 0)
        if b.get('fila_total'):
            _comprobar(codigo, plantilla, int(b['fila_total']), 'A', str(b['marca_total']))
            fila_total = int(b['fila_total']) + desplazamiento + extra
            for col in b['columnas'][1:]:
                numeros = [_valor(f, col) for f in filas]
                valor = sum(numeros) if filas and all(isinstance(x, (int, float)) for x in numeros) else None
                traza = {**base, 'campo': col['campo'], 'calculo': f'suma de la columna {col["letra"]}'}
                if valor is None:
                    traza['motivo'] = 'sin filas o con alguna fila sin dato: el total no se supone'
                celdas.append({'id': f'{codigo}!{b["bloque"]}:total:{col["campo"]}', 'cuadro': codigo,
                               'bloque': b['bloque'], 'fila': 'total', 'campo': col['campo'],
                               'columna': col['rotulo'][2], 'celda': f'{codigo}!{col["letra"]}{fila_total}',
                               'valor': valor, 'traza': traza})
        desplazamiento += extra
    return {'codigo': codigo, 'celdas': celdas, 'huecos': huecos, 'filas_a_insertar': insertar, 'regla': regla}
