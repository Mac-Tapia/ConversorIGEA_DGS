"""Motor común para llenar un formato desde su plantilla transcrita y su mapeo declarado (107-T19b).

El mapeo campo → celda vive en ``config/pit_mapeo_formatos.json``: por formato, las celdas de cabecera y los bloques
(fila de la primera línea de datos, su marca y, si la hay, la fila de total), con la fila y la letra del rótulo de
cada columna. Antes de llenar se comprueba que cada rótulo y cada marca siguen en la plantilla transcrita del
registro: si la norma cambia la plantilla, el error lo dice en lugar de llenar la columna equivocada.

Nada queda vacío en silencio: una celda sin dato lleva su motivo; un bloque sin filas, su hueco con la causa; y una
columna de la plantilla que el mapeo no cubre se nombra como hueco. Si un bloque trae más filas que las de ejemplo
de la plantilla, se dice cuántas hay que insertar (``filas_a_insertar``) y las posiciones ya cuentan con ellas; para
los bloques se dice además dónde (``insertar_en``: hoja, fila y cuántas, en orden de arriba abajo), que es lo que usa
el libro de la entrega para insertarlas antes de escribir (107-P10b).

Celdas sombreadas (delta20): las que la plantilla manda dejar vacías (``no_llenar`` de la transcripción; en el F-302,
«(3) Las celdas sombreadas no deben ser llenadas») salen vacías a propósito, sin motivo de hueco, con ``no_llenar`` y
su causa en la traza. Si la fuente trae un valor para una de ellas, no se escribe y va a ``avisos`` con el formato y
la celda. Se reconocen por su posición en la plantilla, antes de insertar filas: una fila insertada repite la última
fila de ejemplo de su bloque, y un miembro de grupo añadido repite el último de la plantilla.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit import PitError

__all__ = ['ESQUEMA_MAPEO', 'MAPEO', 'cargar_mapeo', 'celdas_de_formato']

ESQUEMA_MAPEO = 'pit_mapeo_formatos_v1'
MAPEO = Path(__file__).resolve().parents[4] / 'config' / 'pit_mapeo_formatos.json'
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
    # Una celda cuyo texto lleva una llamada a nota en superíndice («Total Sistema 1» + «(2)», F-101 A8) se compara por
    # su rótulo, sin la llamada (``llamadas`` de la transcripción, delta17); los exponentes (r², mm²) quedan literales.
    celdas = {}
    for f in filas:
        llamadas = f.get('llamadas') or {}
        for letra, t in f['celdas'].items():
            celdas[(f['fila'], letra)] = str(llamadas[letra]['rotulo']) if letra in llamadas else str(t)
    return celdas, rv


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
    columna = str(bloque.get('columna_marca', 'A'))  # F-124: la marca «Grupo 1» va en la columna D
    filas = sorted({f for f, letra in celdas if letra == columna and f > inicio})
    for f in filas:
        texto = celdas[(f, columna)].strip()
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


def _anios_de_serie_filas(b: Mapping[str, Any], horizonte: int | None) -> range:
    """Los años de una serie en filas: los que declara el mapeo (``desde`` y ``hasta``, p. ej. la historia del −20 al 0
    de F-104 y F-105, que la plantilla trae escritos) o, si no los declara, del 0 al horizonte de la norma."""
    serie = b['serie_filas']
    if 'desde' in serie:
        return range(int(serie['desde']), int(serie['hasta']) + 1)
    return range(int(horizonte or 0) + 1)


def _comprobar_serie_filas(codigo: str, plantilla: Mapping[tuple[int, str], str], b: Mapping[str, Any],
                           horizonte: int | None) -> None:
    """Serie en filas: desde ``fila_marca``, una fila por año con el año en ``serie_filas.columna``."""
    columna = str(b['serie_filas'].get('columna', 'A'))
    for k, anio in enumerate(_anios_de_serie_filas(b, horizonte)):
        fila = int(b['fila_marca']) + k
        if plantilla.get((fila, columna), '').strip() != str(anio):
            raise PitError(f'{codigo}: la norma pide {horizonte} años y la plantilla no trae el año {anio} en '
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
    insertar_en: list[dict[str, Any]] = []
    for c in definicion.get('cabecera', ()):
        fila, letra, texto = c['rotulo']
        _comprobar(codigo, plantilla, fila, letra, texto)
        valor = (datos.get('cabecera') or {}).get(c['campo'])
        traza = {**base, 'campo': c['campo'], 'calculo': 'dato de la fuente'}
        if valor is None:
            traza['motivo'] = ((datos.get('_motivos_cabecera') or {}).get(c['campo'])
                               or f'la fuente no trae «{c["campo"]}»')
        celdas.append({'id': f'{codigo}!cabecera:{c["campo"]}', 'cuadro': codigo, 'bloque': 'cabecera', 'fila': 0,
                       'campo': c['campo'], 'columna': texto, 'celda': f'{codigo}!{c["celda"]}', 'valor': valor,
                       'traza': traza})
        celdas[-1]['_plantilla'] = _posicion(str(c['celda']))
    desplazamiento = 0
    horizonte = None
    for definido in definicion.get('bloques', ()):
        if ('serie_columnas' in definido or 'serie_filas' in definido) and horizonte is None:
            horizonte = horizonte_de_la_norma(registro, fecha)
        b: dict[str, Any] = {**definido, 'columnas': _columnas_del_bloque(codigo, plantilla, definido, horizonte)}
        _comprobar(codigo, plantilla, int(b['fila_marca']), str(b.get('columna_marca', 'A')), str(b['marca']))
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
        # Una serie en filas trae en la plantilla una fila por año (comprobadas arriba): esas son sus filas de ejemplo.
        capacidad = len(_anios_de_serie_filas(b, horizonte)) if 'serie_filas' in b else _capacidad(plantilla, b)
        primera = int(b['fila_marca']) + desplazamiento
        if len(filas) > capacidad:
            insertar[b['bloque']] = len(filas) - capacidad
            # Tras la última fila de ejemplo, ya desplazada por los bloques de arriba: así se insertan en ese orden.
            insertar_en.append({'hoja': codigo, 'bloque': b['bloque'], 'fila': primera + capacidad,
                                'filas': len(filas) - capacidad})
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
                celdas[-1]['_plantilla'] = (int(b['fila_marca']) + min(i, capacidad) - 1, col['letra'])
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
                celdas[-1]['_plantilla'] = (int(b['fila_total']), col['letra'])
        desplazamiento += extra
    grupos_a_insertar: dict[str, int] = {}
    for g in definicion.get('grupos', ()):
        desplazamiento = _llenar_grupo(codigo, plantilla, g, datos, base, celdas, huecos, insertar, grupos_a_insertar,
                                       desplazamiento)
    avisos = _aplicar_no_llenar(codigo, rv, celdas)
    return {'codigo': codigo, 'celdas': celdas, 'huecos': huecos, 'filas_a_insertar': insertar,
            'insertar_en': insertar_en, 'grupos_a_insertar': grupos_a_insertar, 'regla': regla,
            'avisos': avisos}


def _posicion(celda: str) -> tuple[int, str]:
    """«B4» → (4, 'B'): la posición de una celda en la plantilla."""
    letra = ''.join(ch for ch in celda if ch.isalpha())
    return int(''.join(ch for ch in celda if ch.isdigit())), letra


def _aplicar_no_llenar(codigo: str, rv: Any, celdas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las celdas en una posición sombreada de la plantilla quedan vacías a propósito: sin valor, sin motivo de
    hueco y con ``no_llenar``; un valor que traía la fuente para ellas no se escribe y se devuelve como aviso. Quita
    la posición en la plantilla (``_plantilla``) que anotó el llenado."""
    valor = rv.regla.valor if isinstance(rv.regla.valor, Mapping) else {}
    nl = valor.get('no_llenar') or {}
    sombreadas = {(int(f), letra) for f, letras in (nl.get('filas') or {}).items() for letra in letras}
    motivo = str(nl.get('motivo') or 'celda sombreada en el libro oficial')
    avisos: list[dict[str, Any]] = []
    for c in celdas:
        posicion = c.pop('_plantilla', None)
        if posicion is None or posicion not in sombreadas:
            continue
        en_plantilla = f'{posicion[1]}{posicion[0]}'
        if c['valor'] is not None:
            avisos.append({'formato': codigo, 'celda': c['celda'], 'celda_plantilla': en_plantilla,
                           'campo': c['campo'], 'valor': c['valor'],
                           'aviso': f'{codigo}!{en_plantilla} es una celda sombreada ({motivo}): el valor de la '
                                    'fuente no se escribe'})
        c['valor'] = None
        c['no_llenar'] = True
        c['traza'].pop('motivo', None)
        c['traza']['no_llenar'] = motivo
    return avisos


def _empieza(codigo: str, plantilla: Mapping[tuple[int, str], str], fila: int, letra: str, prefijo: str) -> None:
    hallado = plantilla.get((fila, letra))
    if not str(hallado or '').startswith(prefijo):
        raise PitError(f'{codigo}: la plantilla no tiene «{prefijo}…» en {letra}{fila} (tiene {hallado!r}); la plantilla '
                       'cambió y hay que revisar config/pit_mapeo_formatos.json')


def _llenar_grupo(codigo, plantilla, g, datos, base, celdas, huecos, insertar, grupos_a_insertar, desplazamiento):
    """Un grupo repetido de la plantilla (F-101: un bloque por sistema eléctrico). Cada miembro tiene su fila de
    cabecera (``marca_cabecera`` k), sus filas de datos y su fila de total (``marca_total`` k, solo con las columnas de
    ``total``). La plantilla trae unos huecos de ejemplo (``filas_cabecera`` y ``filas_total``); los miembros que
    sobran van después del último con el mismo periodo y se dice cuántos insertar, y las filas que no caben en un
    miembro también se dicen (``filas_a_insertar``) y desplazan lo que sigue."""
    cabeceras, totales = [int(x) for x in g['filas_cabecera']], [int(x) for x in g['filas_total']]
    for f in cabeceras:
        _empieza(codigo, plantilla, f, 'A', g['marca_cabecera'])
    for f in totales:
        _empieza(codigo, plantilla, f, 'A', g['marca_total'])
    for col in g['columnas']:
        _comprobar(codigo, plantilla, *col['rotulo'])
    periodo = cabeceras[1] - cabeceras[0] if len(cabeceras) > 1 else totales[0] - cabeceras[0] + 1
    capacidad = totales[0] - cabeceras[0] - 1
    miembros = list((datos.get('grupos') or {}).get(g['grupo']) or ())
    if not miembros:
        huecos.append({'bloque': g['grupo'], 'causa': f'sin {g["grupo"]} en la fuente {base["fuente"]["nombre"]}',
                       'fila_plantilla': cabeceras[0] + desplazamiento})
        return desplazamiento
    if len(miembros) > len(cabeceras):
        grupos_a_insertar[g['grupo']] = len(miembros) - len(cabeceras)
    for k, m in enumerate(miembros, start=1):
        cab = (cabeceras[k - 1] if k <= len(cabeceras) else cabeceras[-1] + periodo * (k - len(cabeceras))) + desplazamiento
        filas = list(m.get('filas') or ())
        nombre = f'{g["grupo"]}:{k}'
        extra = max(0, len(filas) - capacidad)
        if extra:
            insertar[nombre] = extra
        traza0 = {**base, 'grupo': g['grupo'], 'miembro': m.get('nombre')}
        celdas.append({'id': f'{codigo}!{nombre}:cabecera', 'cuadro': codigo, 'bloque': nombre, 'fila': 'cabecera',
                       'campo': 'cabecera', 'columna': g['marca_cabecera'], 'celda': f'{codigo}!A{cab}',
                       'valor': f'{g["marca_cabecera"]} {k}', 'traza': {**traza0, 'calculo': 'numeración del grupo'}})
        cab_plantilla = cabeceras[min(k, len(cabeceras)) - 1]
        total_plantilla = totales[min(k, len(totales)) - 1]
        celdas[-1]['_plantilla'] = (cab_plantilla, 'A')
        if not filas:
            huecos.append({'bloque': nombre, 'causa': f'{m.get("nombre")}: sin filas en la fuente', 'fila_plantilla': cab + 1})
        for i, fila in enumerate(filas, start=1):
            motivos = fila.get('_motivos') or {}
            for col in g['columnas']:
                valor = fila.get(col['campo'])
                traza = {**traza0, 'campo': col['campo'], 'calculo': motivos.get(f'_calculo:{col["campo"]}') or 'dato de la fuente'}
                if valor is None:
                    traza['motivo'] = motivos.get(col['campo']) or f'la fuente no trae «{col["campo"]}»'
                celdas.append({'id': f'{codigo}!{nombre}:{i}:{col["campo"]}', 'cuadro': codigo, 'bloque': nombre,
                               'fila': i, 'campo': col['campo'], 'columna': col['rotulo'][2],
                               'celda': f'{codigo}!{col["letra"]}{cab + i}', 'valor': valor, 'traza': traza})
                celdas[-1]['_plantilla'] = (cab_plantilla + min(i, capacidad), col['letra'])
        fila_total = cab + capacidad + 1 + extra
        celdas.append({'id': f'{codigo}!{nombre}:total:rotulo', 'cuadro': codigo, 'bloque': nombre, 'fila': 'total',
                       'campo': 'rotulo_total', 'columna': g['marca_total'], 'celda': f'{codigo}!A{fila_total}',
                       'valor': f'{g["marca_total"]} {k}', 'traza': {**traza0, 'calculo': 'numeración del grupo'}})
        celdas[-1]['_plantilla'] = (total_plantilla, 'A')
        tot = m.get('total') or {}
        for col in g.get('total', ()):
            valor = tot.get(col['campo'])
            traza = {**traza0, 'campo': col['campo'], 'calculo': tot.get(f'_calculo:{col["campo"]}') or 'dato de la fuente'}
            if valor is None:
                traza['motivo'] = tot.get(f'_motivo:{col["campo"]}') or f'la fuente no trae el total «{col["campo"]}»'
            celdas.append({'id': f'{codigo}!{nombre}:total:{col["campo"]}', 'cuadro': codigo, 'bloque': nombre,
                           'fila': 'total', 'campo': col['campo'], 'columna': col['campo'],
                           'celda': f'{codigo}!{col["letra"]}{fila_total}', 'valor': valor, 'traza': traza})
            celdas[-1]['_plantilla'] = (total_plantilla, col['letra'])
        desplazamiento += extra
    return desplazamiento
