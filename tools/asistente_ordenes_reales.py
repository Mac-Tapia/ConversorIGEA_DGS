#!/usr/bin/env python
"""Reúne las órdenes reales del operador, las prepara para revisión e importa lo que él marque (spec 068).

    python tools/asistente_ordenes_reales.py extraer --almacen <almacén>
    python tools/asistente_ordenes_reales.py exportar --almacen <almacén>
    python tools/asistente_ordenes_reales.py importar --almacen <almacén>

`extraer` lee las sesiones de Claude Code y de Codex del proyecto y el registro de órdenes, y escribe
`<almacén>/maestro_real/textos.jsonl`. `exportar` crea `revision.xlsx` con lo que el maestro etiquetó en
`etiquetas.jsonl`. `importar` anota en `ejemplos.jsonl` solo las filas que el operador marcó: quien nunca marca
es el código. Estos ficheros llevan texto privado y datos de la distribuidora: nunca a git (P9). En pantalla
solo salen recuentos.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))

from convertersmartgrid.asistente.maestro_real import SUBCARPETA, NINGUNA, clave_texto, datos_a_spans, leer_etiquetas  # noqa: E402
from convertersmartgrid.asistente.tareas import TAREAS  # noqa: E402

LARGO_MIN, LARGO_MAX = 5, 400
COLUMNAS = ('texto', 'tarea propuesta', 'datos propuestos', '¿correcta? (s/n)', 'tarea correcta', 'confianza', 'id')
_SI, _NO = {'s', 'si', 'sí', 'y', 'yes'}, {'n', 'no'}
# Lo que el arnés escribe en nombre del usuario: no lo escribió él.
_AJENOS = ('[Request interrupted', 'Caveat:', 'This session is being continued', 'Base directory for this skill',
           'Stop hook feedback', '[Image', 'Tool loaded', 'Continue from where you left off', 'No response requested')
_ETIQUETA = re.compile(r'^<([\w:-]+)[^>]*>.*?</\1>\s*', re.S)
_IMPERATIVOS = set(
    'haz has hazme hasme corre ejecuta lanza convierte conviertelo genera crea calibra calibrame recalibra importa exporta '
    'carga cargar lee sube une junta verifica valida comprueba revisa evalua mide aplica integra agrega mete pon optimiza '
    'transfiere transfiereme pasa reentrena entrena simula reproduce redacta escribe elabora clasifica busca investiga '
    'muestra muestrame dame dime lista listar explica explicame prueba termina completa actualiza refresca recarga'.split())
_PREGUNTAS = {'que', 'como', 'cuantos', 'cuantas', 'cuanto', 'cual', 'cuales', 'donde', 'porque', 'quien', 'hay'}
_CORTESIA = {'por', 'favor', 'porfa', 'ahora', 'oye', 'ya', 'bien', 'ok', 'puedes', 'podrias', 'quiero', 'que', 'necesito', 'y', 'luego',
             'entonces', 'tambien', 'primero', 'me'}


def clase_de(texto: str) -> str:
    """``orden`` si arranca como una orden o una pregunta corta; ``charla`` si no. Solo orienta: no descarta."""
    palabras = clave_texto(texto).split()
    if len(palabras) < 2 or len(texto) > 220:
        return 'charla'
    resto = palabras[:]
    while resto and resto[0] in _CORTESIA and resto[0] not in _IMPERATIVOS:
        resto.pop(0)
    if resto and resto[0] in _IMPERATIVOS:
        return 'orden'
    return 'orden' if palabras[0] in _PREGUNTAS and len(palabras) <= 14 else 'charla'


def _limpio(texto: str) -> str | None:
    """El texto en una línea, o ``None`` si no lo escribió el usuario o no tiene largo de orden."""
    previo = None
    while previo != texto:                 # un mensaje puede traer la etiqueta del editor y luego la orden
        previo, texto = texto, _ETIQUETA.sub('', texto.strip())
    texto = ' '.join(texto.split())
    if not LARGO_MIN <= len(texto) <= LARGO_MAX or texto.startswith('<') or texto.startswith(_AJENOS):
        return None
    return texto


def _de_claude(fila: dict) -> list[str]:
    if fila.get('type') != 'user' or fila.get('isSidechain') or fila.get('isMeta') or fila.get('isCompactSummary'):
        return []
    contenido = (fila.get('message') or {}).get('content')
    if isinstance(contenido, str):
        return [contenido]
    if not isinstance(contenido, list) or any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in contenido):
        return []
    return [str(b.get('text') or '') for b in contenido if isinstance(b, dict) and b.get('type') == 'text']


def _lineas_json(ruta: Path, *, pista: str):
    """Línea a línea, sin cargar cada sesión: Codex guarda más de 500 MB y al equipo le falta memoria."""
    with open(ruta, encoding='utf-8', errors='replace') as h:
        for linea in h:
            if pista in linea:
                try:
                    fila = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(fila, dict):
                    yield fila


def _textos_claude(carpeta: Path):
    for ruta in sorted(carpeta.glob('*.jsonl')):
        for fila in _lineas_json(ruta, pista='"user"'):
            yield from _de_claude(fila)


def _sesion_de_codex_valida(meta: dict, raiz: str) -> bool:
    origen = meta.get('source')
    # Una sesión hija de Codex tiene por «usuario» al agente que la lanzó (66 sesiones, 2026-11-02).
    if meta.get('thread_source') == 'subagent' or (isinstance(origen, dict) and 'subagent' in origen):
        return False
    cwd = str(meta.get('cwd') or '').replace('\\', '/').rstrip('/').casefold()
    return cwd == raiz or cwd.startswith(raiz + '/')


def _textos_codex(carpeta: Path, raiz_proyecto: str):
    raiz = raiz_proyecto.replace('\\', '/').rstrip('/').casefold()
    for ruta in sorted(carpeta.rglob('*.jsonl')):
        with open(ruta, encoding='utf-8', errors='replace') as h:
            primera = h.readline()
        try:
            cabecera = json.loads(primera)
        except ValueError:
            continue
        if cabecera.get('type') != 'session_meta' or not _sesion_de_codex_valida(cabecera.get('payload') or {}, raiz):
            continue
        for fila in _lineas_json(ruta, pista='"user_message"'):
            carga = fila.get('payload') or {}
            if fila.get('type') == 'event_msg' and carga.get('type') == 'user_message':
                yield str(carga.get('message') or '')


def _textos_ordenes(almacen: Path):
    ruta = almacen / 'ordenes.jsonl'
    if ruta.is_file():
        for fila in _lineas_json(ruta, pista='texto'):
            yield str(fila.get('texto') or '')


def _publicar(ruta: Path, contenido: bytes) -> None:
    """Todo o nada: un corte deja el fichero anterior entero y ningún resto."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f'.{ruta.name}.{os.getpid()}.tmp')
    try:
        temporal.write_bytes(contenido)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def _raiz_principal(raiz: Path) -> Path:
    """El proyecto, también desde un worktree: las sesiones cuelgan de la carpeta principal."""
    partes = raiz.parts
    return Path(*partes[:partes.index('.worktrees')]) if '.worktrees' in partes else raiz


def extraer(args) -> dict:
    principal = args.raiz_proyecto or str(_raiz_principal(RAIZ))
    # Claude Code nombra la carpeta de sesiones cambiando por guiones lo que no es letra o número.
    carpeta_claude = args.claude or Path.home() / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9-]', '-', principal.replace('\\', '/'))
    carpeta_codex = args.codex or Path.home() / '.codex' / 'sessions'
    reunidos: dict[str, dict] = {}
    leidos: Counter = Counter()
    for fuente, textos in (('claude', _textos_claude(Path(carpeta_claude))),
                           ('codex', _textos_codex(Path(carpeta_codex), principal)),
                           ('asistente', _textos_ordenes(args.almacen))):
        for bruto in textos:
            leidos[fuente] += 1
            texto = _limpio(bruto)
            clave = clave_texto(texto) if texto else ''
            if not clave:
                continue
            fila = reunidos.setdefault(clave, {'id': hashlib.sha256(clave.encode('utf-8')).hexdigest()[:16], 'texto': texto,
                                               'fuentes': [], 'veces': 0, 'clase': clase_de(texto)})
            fila['veces'] += 1
            if fuente not in fila['fuentes']:
                fila['fuentes'].append(fuente)
    filas = [reunidos[k] for k in sorted(reunidos)]
    _publicar(args.almacen / SUBCARPETA / 'textos.jsonl',
              ''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in filas).encode('utf-8'))
    return {'ok': True, 'mensajes_leidos': dict(leidos), 'textos_unicos': len(filas),
            'clases': dict(Counter(f['clase'] for f in filas)),
            'por_fuente': dict(Counter(x for f in filas for x in f['fuentes']))}


def _marcas_previas(ruta: Path) -> dict[str, tuple]:
    if not ruta.is_file():
        return {}
    import openpyxl
    libro = openpyxl.load_workbook(ruta, read_only=True)
    filas = libro.worksheets[0].iter_rows(values_only=True)
    cabecera = list(next(filas))
    i, m, t = cabecera.index('id'), cabecera.index(COLUMNAS[3]), cabecera.index(COLUMNAS[4])
    previas = {str(f[i]): (f[m], f[t]) for f in filas if f[i] and (f[m] not in (None, '') or f[t] not in (None, ''))}
    libro.close()
    return previas


def _datos_legibles(datos: dict) -> str:
    return '; '.join(f'{tipo}={valor}' for tipo, valores in sorted((datos or {}).items()) for valor in valores)


def exportar(args) -> dict:
    import openpyxl
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    etiquetas, cuenta = leer_etiquetas(args.almacen, minimo=0.)
    ruta = args.almacen / SUBCARPETA / 'revision.xlsx'
    previas = _marcas_previas(ruta)
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = 'Revisión'
    hoja.append(list(COLUMNAS))
    for celda in hoja[1]:
        celda.font = Font(bold=True)
        celda.fill = PatternFill('solid', fgColor='DDE6F0')
    for n, e in enumerate(sorted(etiquetas, key=lambda x: (x['tarea'], x['texto'])), start=2):
        marca, correcta = previas.get(str(e.get('id')), (None, None))
        texto = ILLEGAL_CHARACTERS_RE.sub('', e['texto'])
        for columna, valor in enumerate((texto, e['tarea'], _datos_legibles(e.get('datos')), marca, correcta,
                                         e['confianza'], str(e.get('id'))), start=1):
            celda = hoja.cell(n, columna)
            celda.value = valor
            if isinstance(valor, str):
                # Un mensaje que empiece por «=» es un mensaje: como fórmula se ejecutaría al abrir.
                celda.data_type = 's'
                celda.quotePrefix = valor[:1] in ('=', '+', '-', '@')
        hoja.cell(n, 1).alignment = Alignment(wrap_text=True, vertical='top')
    for letra, ancho in zip('ABCDEFG', (70, 24, 42, 16, 24, 10, 18), strict=True):
        hoja.column_dimensions[letra].width = ancho
    hoja.column_dimensions['G'].hidden = True
    hoja.freeze_panes = 'A2'
    hoja.auto_filter.ref = f'A1:G{max(hoja.max_row, 1)}'
    catalogo = libro.create_sheet('tareas')
    for i, tarea in enumerate([*sorted(TAREAS), NINGUNA], start=1):
        catalogo.cell(i, 1).value = tarea
    catalogo.sheet_state = 'hidden'
    si_no = DataValidation(type='list', formula1='"s,n"', allow_blank=True)
    tareas = DataValidation(type='list', formula1=f'tareas!$A$1:$A${len(TAREAS) + 1}', allow_blank=True)
    hoja.add_data_validation(si_no)
    hoja.add_data_validation(tareas)
    si_no.add(f'D2:D{max(hoja.max_row, 2)}')
    tareas.add(f'E2:E{max(hoja.max_row, 2)}')
    temporal = ruta.with_name(f'.{ruta.name}.{os.getpid()}.tmp')
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        libro.save(temporal)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)
    return {'ok': True, 'filas': len(etiquetas), 'marcas_conservadas': len(previas), 'descartadas_por_el_maestro': cuenta['ninguna'],
            'dudosas': cuenta['dudosas'], 'revision': str(ruta)}


def _firma_humana(fila: dict) -> tuple:
    texto = str(fila.get('texto') or '')
    return (fila.get('tarea'), sorted((str(d[2]), clave_texto(texto[d[0]:d[1]])) for d in fila.get('datos') or ()))


def importar(args) -> dict:
    import openpyxl
    ruta_excel = args.excel or args.almacen / SUBCARPETA / 'revision.xlsx'
    etiquetas = {str(e.get('id')): e for e in leer_etiquetas(args.almacen, minimo=0.)[0]}
    libro = openpyxl.load_workbook(ruta_excel, read_only=True)
    filas = libro.worksheets[0].iter_rows(values_only=True)
    cabecera = list(next(filas))
    if any(c not in cabecera for c in COLUMNAS):
        libro.close()
        return {'ok': False, 'errores': ['al libro le faltan columnas de la revisión']}
    i_id, i_m, i_t = cabecera.index('id'), cabecera.index(COLUMNAS[3]), cabecera.index(COLUMNAS[4])
    elegidas, errores, cuenta = [], [], Counter()
    for n, f in enumerate(filas, start=2):
        marca = str(f[i_m] if f[i_m] is not None else '').strip().casefold()
        correcta = str(f[i_t] if f[i_t] is not None else '').strip()
        if not marca:
            cuenta['sin_marca'] += 1
            continue
        etiqueta = etiquetas.get(str(f[i_id]))
        if etiqueta is None:
            errores.append(f'fila {n}: no corresponde a ninguna etiqueta')
        elif marca in _SI:
            elegidas.append(('confirmado', etiqueta, etiqueta['tarea'], etiqueta['spans']))
        elif marca not in _NO:
            errores.append(f'fila {n}: marca que no se entiende')
        elif correcta == NINGUNA or not correcta:
            cuenta['incorrectas_sin_tarea'] += 1
        elif correcta not in TAREAS:
            errores.append(f'fila {n}: tarea correcta que no existe')
        else:
            admitidos = {d.tipo for d in TAREAS[correcta].datos}
            datos = {k: v for k, v in (etiqueta.get('datos') or {}).items() if k in admitidos}
            elegidas.append(('corregido', etiqueta, correcta, datos_a_spans(etiqueta['texto'], datos)))
    libro.close()
    if errores:
        return {'ok': False, 'errores': errores, 'importadas': 0}
    destino = args.almacen / 'ejemplos.jsonl'
    original = destino.read_bytes() if destino.is_file() else b''
    existentes: dict[str, tuple] = {}
    for linea in original.decode('utf-8', errors='replace').splitlines():
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if isinstance(fila, dict) and fila.get('origen') in {'confirmado', 'corregido'}:
            existentes.setdefault(clave_texto(str(fila.get('texto') or '')), _firma_humana(fila))
    nuevas = []
    for origen, etiqueta, tarea, spans in elegidas:
        fila = {'fecha': datetime.now().astimezone().isoformat(timespec='seconds'), 'texto': etiqueta['texto'], 'tarea': tarea,
                'datos': spans, 'origen': origen, 'revision': SUBCARPETA}
        clave, firma = clave_texto(etiqueta['texto']), _firma_humana(fila)
        if clave not in existentes:
            existentes[clave] = firma
            nuevas.append(fila)
            cuenta[origen] += 1
        elif existentes[clave] == firma:
            cuenta['ya_estaban'] += 1
        else:
            # Dos etiquetas humanas distintas para un texto hacen fallar ``preparar_corpus``.
            cuenta['contradicen'] += 1
    if nuevas:
        previo = original if not original or original.endswith(b'\n') else original + b'\n'
        bloque = ''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in nuevas).encode('utf-8')
        # La web anota confirmaciones en este mismo fichero: si ha cambiado mientras tanto, no se pisa.
        if (destino.read_bytes() if destino.is_file() else b'') != original:
            return {'ok': False, 'errores': ['ejemplos.jsonl cambió mientras se importaba; vuelva a lanzar'], 'importadas': 0}
        _publicar(destino, previo + bloque)
    return {'ok': True, 'importadas': len(nuevas), 'confirmadas': cuenta['confirmado'], 'corregidas': cuenta['corregido'],
            'sin_marca': cuenta['sin_marca'], 'incorrectas_sin_tarea': cuenta['incorrectas_sin_tarea'],
            'ya_estaban': cuenta['ya_estaban'], 'contradicen': cuenta['contradicen']}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='accion', required=True)
    for nombre in ('extraer', 'exportar', 'importar'):
        s = sub.add_parser(nombre)
        s.add_argument('--almacen', type=Path, help='Almacén del asistente; por defecto, el de la web')
        if nombre == 'extraer':
            s.add_argument('--claude', type=Path, help='Carpeta de sesiones de Claude Code del proyecto')
            s.add_argument('--codex', type=Path, help='Carpeta de sesiones de Codex')
            s.add_argument('--raiz-proyecto', help='Ruta del proyecto, para reconocer sus sesiones')
        if nombre == 'importar':
            s.add_argument('--excel', type=Path, help='Libro marcado; por defecto, revision.xlsx del almacén')
    args = p.parse_args(argv)
    if args.almacen is None:
        from convertersmartgrid.asistente import almacen
        args.almacen = almacen.raiz()
    resultado = {'extraer': extraer, 'exportar': exportar, 'importar': importar}[args.accion](args)
    print(json.dumps(resultado, ensure_ascii=True))
    return 0 if resultado.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
