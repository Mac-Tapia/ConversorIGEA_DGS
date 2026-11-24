"""Los entregables del Estudio VAD: los Formatos A y B del anexo 2 en Excel con sus fórmulas, los mapas de densidad
del anexo 9 y el manifiesto de fuentes con sus huellas (108:RF-11, RF-9, RF-13).

**Formatos A y B** (T9). El informe del estudio incluye «los Formatos del Anexo N° 2 (Formatos A y Formatos B)»
(numeral 9 del anexo de los TdR registrado, copia de texto de sha256 48ea8cf4…, línea 3418): los de prefijo «A»
llevan la información de la empresa y los de prefijo «B», los mismos cuadros de la empresa modelo (líneas 2741-2745).
Las filas y las columnas salen del anexo 2 transcrito (``config/vad/anexo2_formatos.json``). Una celda calculada lleva
SIEMPRE su fórmula de Excel, traducida de la fórmula transcrita:

- de fila: «(16) = (11) + (12) + (13) - (14) - (15)» (A-VI), «A16 = A4 + … + A15» (los códigos entre A4 y A15, en el
  orden del formato) y «suma de las filas MT» (las filas de dato cuyo código empieza por «MT.»);
- de columna: un rótulo «(d) = (b)+(c)» (A-V) es la fórmula de esa columna en cada fila.

Una fórmula transcrita que no se puede traducir sin suponer algo («suma de los componentes»), o un total sin fórmula
transcrita, deja la celda vacía con su hueco nombrado: nunca se escribe un valor donde va una fórmula. Tampoco se
escribe una fórmula que apunta a una celda vacía. El TdR publica los formatos dentro del PDF del anexo, sin libro
Excel modelo; por eso el libro se escribe con openpyxl. :func:`comprobar_formatos` reabre el libro, comprueba que cada
celda calculada es una fórmula y la evalúa con el intérprete cerrado de :mod:`.formulas`: una referencia a una celda
vacía o de texto, una división entre cero o un valor de error (``libro_informe.ERRORES_DE_FORMULA``) se nombran.
Dos estados distintos, en la celda y en la hoja «Traza» del libro: «no aplica», cuando el formato oficial sombrea la
celda (se cita su página y sus líneas; la celda lo lleva escrito y en una suma es un término nulo), y el hueco, cuando
falta el dato (la celda queda vacía y la fórmula que lo usa no se escribe). Un dato traído en una celda calculada se
sustituye por su fórmula, y la traza guarda la celda, el valor original y la fórmula.

**Mapas de densidad** (T10). El anexo 9 fija las entidades, «los nombres de campo, orden y características» de cada
una (registro ``vad.anexo9.entidades``, líneas 8118-8353), no los nombres de carpetas ni de ficheros: cada entidad se
escribe en ``<carpeta>/<Entidad>.geojson`` con sus campos en el orden del anexo. Un campo que falta, otro tipo, un
texto más largo que su ancho o un número con más decimales se nombran como hueco y no se corrigen. Un campo
adicional pide «un diccionario de datos» (líneas 8120-8123): sin él, se nombra y no se escribe. Las coordenadas se
reproyectan sobre una copia con ``geography.make_transformer``, solo para el mapa: la entrada no cambia.

**Manifiesto de fuentes** (T10). Por cada fichero de entrada: su SHA-256, su tamaño, su versión y la entrada del
registro normativo que lo rige (clave, acto y huella de la regla). :func:`comprobar_manifiesto` recalcula las huellas.
"""
from __future__ import annotations

import copy
import math
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..geography import make_transformer
from ..libro_informe import ERRORES_DE_FORMULA
from ...dominio.registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from ...dominio.util import write_json_atomic
from ...aplicacion.vad import VadError
from ...aplicacion.vad.anexo2 import Campo, Formato, Formatos
from ...aplicacion.vad.formulas import FormulaError, evaluar
from ...dominio.util import sha256_file

PREFIJOS = ('A', 'B')
HOJA_INDICE = 'Índice'
_FILA_CABECERA = 5
_COL_DATOS = 4  # A: código, B: nombre, C: unidad; los datos desde la D
_REF_FILA = re.compile(r'\((\d+)\)')
_SUMA_PREFIJO = re.compile(r'^suma de las filas (\S+)$', re.IGNORECASE)
_ELIPSIS = re.compile(r'(\S+)\s*\+\s*(?:…|\.\.\.)\s*\+\s*(\S+)')
_COLUMNA_FORMULA = re.compile(r'^\((\w)\)\s*=\s*(.+)$')
_REF_COLUMNA = re.compile(r'\((\w)\)')
_CELDA = re.compile(r'\$?([A-Z]{1,3})\$?(\d+)')
_SUMA_EXCEL = re.compile(r'SUM\(([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)\)')


# =========================================================================================== Formatos A y B (T9)
class _SinTraduccion(Exception):
    """La fórmula transcrita no se traduce a Excel sin suponer algo."""


@dataclass(frozen=True)
class LibroFormatos:
    ruta: Path
    prefijo: str
    #: Formato → nombre de su hoja.
    hojas: Mapping[str, str]
    #: Hoja → celdas con su fórmula (lo que :func:`comprobar_formatos` exige).
    calculadas: Mapping[str, tuple[str, ...]]
    huecos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()
    #: Lo que pasó con cada celda que no es un dato normal: «no_aplica» (el formato oficial la sombrea), «hueco» (falta
    #: el dato o la fórmula no se puede escribir) y «sustituido» (traía un dato y va su fórmula). Va también en la hoja
    #: «Traza» del libro: hoja, celda, fila, columna, estado, valor original, fórmula y motivo o cita.
    traza: tuple[Mapping[str, Any], ...] = ()


HOJA_TRAZA = 'Traza'
NO_APLICA = 'no aplica'


def _hoja_de(formato: Formato, prefijo: str) -> str:
    if prefijo not in PREFIJOS:
        raise VadError(f'el prefijo de los formatos es A (empresa) o B (empresa modelo), no {prefijo!r}')
    return f'{prefijo}-{formato.id.split("-", 1)[1]}' if '-' in formato.id else f'{prefijo}-{formato.id}'


def _letra(n: int) -> str:
    from openpyxl.utils import get_column_letter
    return get_column_letter(n)


def _ids_entre(formato: Formato, desde: str, hasta: str) -> list[str]:
    ids = [c.id for c in formato.filas]
    if desde not in ids or hasta not in ids or ids.index(desde) > ids.index(hasta):
        raise _SinTraduccion(f'el rango {desde} … {hasta} no son filas del formato en ese orden')
    return [i for i in ids[ids.index(desde):ids.index(hasta) + 1]]


def expresion_de_fila(formato: Formato, campo: Campo) -> str:
    """La fórmula transcrita de una fila como expresión sobre otras filas: cada fila va entre «{» y «}»."""
    texto = (campo.formula or '').strip()
    m = _SUMA_PREFIJO.match(texto)
    if m:
        prefijo = m.group(1) + '.'
        filas = [c.id for c in formato.filas if c.tipo == 'dato' and c.id.startswith(prefijo)]
        if not filas:
            raise _SinTraduccion(f'«{texto}»: el formato no tiene filas de dato que empiecen por {prefijo!r}')
        return ' + '.join(f'{{{i}}}' for i in filas)
    izq, igual, der = texto.partition('=')
    if not igual or izq.strip() != campo.id:
        raise _SinTraduccion(f'«{texto}» no es una fórmula de la fila {campo.id} sobre otras filas')
    der = der.strip()
    ids = {c.id for c in formato.filas}
    while True:
        m = _ELIPSIS.search(der)
        if not m:
            break
        der = der[:m.start()] + '(' + ' + '.join(_ids_entre(formato, m.group(1), m.group(2))) + ')' + der[m.end():]
    if formato.filas and _REF_FILA.fullmatch(formato.filas[0].id or ''):
        salida = _REF_FILA.sub(lambda r: '{' + r.group(0) + '}', der)
    else:
        salida = re.sub(r'[A-Za-z][\w.]*', lambda r: '{' + r.group(0) + '}' if r.group(0) in ids else r.group(0), der)
    nombres = re.findall(r'\{([^}]+)\}', salida)
    resto = re.sub(r'\{[^}]+\}', '0', salida)
    if not nombres or set(nombres) - ids or re.search(r'[^\d\s+\-*/().]', resto):
        raise _SinTraduccion(f'«{texto}» nombra lo que no son filas del formato')
    return salida


def expresion_de_columna(formato: Formato, columna: Campo) -> str | None:
    """La fórmula del rótulo de una columna («(d) = (b)+(c)») sobre otras columnas, o None si no la tiene."""
    m = _COLUMNA_FORMULA.match(columna.nombre.strip())
    if not m:
        return None
    por_letra = {}
    for c in formato.columnas:
        r = re.match(r'^\((\w)\)', c.nombre.strip())
        if r:
            por_letra[r.group(1)] = c.id
    def sustituir(r: re.Match) -> str:
        if r.group(1) not in por_letra:
            raise _SinTraduccion(f'la columna «{columna.nombre}» nombra la columna ({r.group(1)}), que no existe')
        return '{' + por_letra[r.group(1)] + '}'
    return _REF_COLUMNA.sub(sustituir, m.group(2).strip())


def _guardar_libro(libro: Any, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.csg-', suffix='.xlsx', dir=destino.parent)
    os.close(fd)
    try:
        libro.save(tmp)
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _bloques(formato: Formato, tabla: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    if formato.forma == 'larga':
        return [(' / '.join(f'{k}: {b.get("claves", {}).get(k, "")}' for k in formato.claves_de_fila),
                 b.get('filas') or {}) for b in (tabla.get('bloques') or ())]
    return [('', tabla.get('filas') or {})]


def escribir_formatos(formatos: Formatos, tablas: Mapping[str, Mapping[str, Any]], destino: Path | str, *,
                      prefijo: str = 'A', fuentes: Mapping[str, str] | None = None,
                      cita: Mapping[str, str] | None = None) -> LibroFormatos:
    """Escribe un libro con una hoja por formato transcrito del anexo 2 (prefijo A, la empresa; B, la empresa modelo).

    ``tablas`` tiene la forma de :func:`.anexo2.validar_tablas` (``{formato: {'filas': {fila: {columna: valor}}}}``,
    o ``bloques`` en la forma larga). ``fuentes`` dice de qué documento sale cada tabla (sin él, hueco). ``cita`` es la
    fuente de la transcripción del anexo 2 (``fuente`` de su JSON)."""
    from openpyxl import Workbook

    fuentes = dict(fuentes or {})
    extra = sorted(set(tablas) - {f.id for f in formatos.todos()})
    if extra:
        raise VadError(f'tablas que el anexo 2 transcrito no tiene: {", ".join(extra)}')
    cita_txt = (f'{(cita or {}).get("acto") or formatos.acto}, Anexo N° 2, líneas {(cita or {}).get("lineas", "")}, '
                f'texto sha256 {(cita or {}).get("sha256_texto", "")}').strip(', ')
    libro = Workbook()
    indice = libro.active
    indice.title = HOJA_INDICE
    indice.append(['Formato', 'Título', 'Estado', 'Hoja', 'Fuente de los datos', 'Huecos'])
    hojas: dict[str, str] = {}
    calculadas: dict[str, tuple[str, ...]] = {}
    huecos: list[str] = []
    avisos: list[str] = []
    traza: list[dict[str, Any]] = []
    for formato in formatos.todos():
        nombre = _hoja_de(formato, prefijo)
        hoja = libro.create_sheet(nombre)
        hojas[formato.id] = nombre
        hoja['A1'] = f'Formato {nombre}. {formato.titulo}'
        hoja['A2'] = f'Fuente: {cita_txt}; {formato.pagina}, líneas {formato.lineas}'
        propios: list[str] = []
        if not formato.transcrito:
            hoja['A4'] = f'Sin transcribir: {formato.motivo or "el formato no está transcrito"}'
            propios.append(f'{nombre}: formato sin transcribir ({formato.motivo})')
            huecos += propios
            indice.append([formato.id, formato.titulo, 'hueco', nombre, '', len(propios)])
            continue
        tabla = tablas.get(formato.id)
        if fuentes.get(formato.id, '').strip():
            hoja['A3'] = f'Datos: {fuentes[formato.id].strip()}'
        else:
            hoja['A3'] = 'Datos: sin fuente declarada'
            propios.append(f'{nombre}: los datos no dicen de qué documento salen')
        hoja.cell(_FILA_CABECERA, 1, 'Código')
        hoja.cell(_FILA_CABECERA, 2, 'Nombre')
        hoja.cell(_FILA_CABECERA, 3, 'Unidad')
        col_de = {c.id: _COL_DATOS + j for j, c in enumerate(formato.columnas)}
        for c in formato.columnas:
            hoja.cell(_FILA_CABECERA, col_de[c.id], c.nombre)
            hoja.cell(_FILA_CABECERA + 1, col_de[c.id], c.unidad)
        if tabla is None:
            hoja.cell(_FILA_CABECERA + 2, 1, 'Sin datos: el estudio no entrega esta tabla')
            propios.append(f'{nombre}: sin datos')
            huecos += propios
            indice.append([formato.id, formato.titulo, 'hueco', nombre, fuentes.get(formato.id, ''), len(propios)])
            continue
        texto = {c.id for c in formato.columnas if c.unidad == 'texto'}
        exp_col = {}
        for c in formato.columnas:
            try:
                e = expresion_de_columna(formato, c)
            except _SinTraduccion as exc:
                propios.append(f'{nombre}: {exc}')
                continue
            if e is not None:
                exp_col[c.id] = e
        exp_fila: dict[str, str | None] = {}
        for f in formato.filas:
            if f.tipo == 'grupo':
                continue
            if f.formula:
                try:
                    exp_fila[f.id] = expresion_de_fila(formato, f)
                except _SinTraduccion as exc:
                    exp_fila[f.id] = None
                    propios.append(f'{nombre}, fila {f.id}: la fórmula transcrita no se traduce a Excel: {exc}')
            elif f.tipo == 'total':
                exp_fila[f.id] = None
                propios.append(f'{nombre}, fila {f.id} «{f.nombre}»: total sin fórmula transcrita en el anexo 2; la '
                               'celda queda vacía')
        fila_n = _FILA_CABECERA + 2
        celdas_calc: list[str] = []
        for rotulo, filas in _bloques(formato, tabla):
            if rotulo:
                hoja.cell(fila_n, 1, rotulo)
                fila_n += 1
            fila_de = {}
            for f in formato.filas:
                fila_de[f.id] = fila_n
                fila_n += 1
            celda_de = {}
            for f in formato.filas:
                for c in formato.columnas:
                    celda_de[(f.id, c.id)] = f'{_letra(col_de[c.id])}{fila_de[f.id]}'
            escritas: dict[tuple[str, str], str] = {}  # celda → 'dato' | 'formula'
            no_aplica = {(f.id, c) for f in formato.filas for c in f.no_aplica}
            pendientes: list[tuple[Campo, Campo, str]] = []
            originales: dict[tuple[str, str], Any] = {}  # dato traído en una celda que va con su fórmula
            cita_na = (f'celda sombreada en gris («no aplica») en el formato oficial {formato.id} del anexo 2 '
                       f'({formato.pagina}, líneas {formato.lineas})')

            def anotar(f: Campo, c: Campo, estado: str, motivo: str, valor: Any = None, formula: str = '',
                       nombre: str = nombre, fila_de: dict = fila_de, col_de: dict = col_de) -> None:
                traza.append({'hoja': nombre, 'celda': f'{_letra(col_de[c.id])}{fila_de[f.id]}', 'fila': f.id,
                              'columna': c.id, 'estado': estado, 'valor_original': valor, 'formula': formula,
                              'motivo': motivo})
            for f in formato.filas:
                r = fila_de[f.id]
                hoja.cell(r, 1, f.id)
                hoja.cell(r, 2, f.nombre)
                hoja.cell(r, 3, f.unidad)
                if f.tipo == 'grupo':
                    continue
                datos = filas.get(f.id) or {}
                for c in formato.columnas:
                    lugar = f'{nombre}{" · " + rotulo if rotulo else ""}, fila {f.id}, columna {c.id}'
                    valor = datos.get(c.id)
                    if c.id in f.no_aplica:
                        # Estado «no aplica»: lo dice el formato oficial. La celda lo lleva escrito y en una suma es
                        # un término que no existe (0); no es un hueco.
                        hoja.cell(r, col_de[c.id], NO_APLICA)
                        anotar(f, c, 'no_aplica', cita_na, valor if valor not in (None, '') else None)
                        if valor not in (None, ''):
                            avisos.append(f'{lugar}: no aplica en el formato y trae {valor!r}; no se escribe')
                        continue
                    if f.id in exp_fila and c.id not in texto:
                        if valor not in (None, ''):
                            originales[(f.id, c.id)] = valor
                        if exp_fila[f.id] is not None:
                            pendientes.append((f, c, exp_fila[f.id].replace('{', '{F:')))
                        else:
                            anotar(f, c, 'hueco', 'la fila no tiene una fórmula transcrita que se pueda escribir',
                                   originales.get((f.id, c.id)))
                        continue
                    if c.id in exp_col:
                        if valor not in (None, ''):
                            originales[(f.id, c.id)] = valor
                        pendientes.append((f, c, exp_col[c.id].replace('{', '{C:')))
                        continue
                    if valor in (None, ''):
                        # Estado «hueco»: el formato pide el dato y no vino. La celda queda vacía y una fórmula que
                        # la usa no se escribe (un hueco no vale 0).
                        if f.obligatoria and c.obligatoria:
                            propios.append(f'{lugar}: sin valor; no se rellena')
                            anotar(f, c, 'hueco', 'sin valor; no se rellena')
                        continue
                    if c.id not in texto and (isinstance(valor, bool) or not isinstance(valor, (int, float))):
                        propios.append(f'{lugar}: {valor!r} no es un número')
                        continue
                    hoja.cell(r, col_de[c.id], valor)
                    escritas[(f.id, c.id)] = 'dato'
            # Las fórmulas, en el orden que haga falta: una fórmula solo se escribe si sus celdas ya están escritas.
            # En «{F:x}» x es una fila (misma columna); en «{C:x}», una columna (misma fila).
            def celda_ref(f: Campo, c: Campo, marca: str) -> tuple[str, str]:
                return (marca[2:], c.id) if marca.startswith('F:') else (f.id, marca[2:])

            while pendientes:
                avance = False
                for item in list(pendientes):
                    f, c, e = item
                    refs = [celda_ref(f, c, m) for m in re.findall(r'\{([^}]+)\}', e)]
                    # Una celda que el formato marca «no aplica» es un término que no existe: vale 0 en la fórmula
                    # (las fórmulas con no aplica del anexo 2 son sumas, como «(d) = (b)+(c)»). Un hueco, en cambio,
                    # deja la fórmula sin escribir.
                    if not all(x in escritas or x in no_aplica for x in refs):
                        continue
                    def sustituir(m: re.Match, f: Campo = f, c: Campo = c, na: set = no_aplica,
                                  cd: dict = celda_de) -> str:
                        ref = celda_ref(f, c, m.group(1))
                        return '0' if ref in na else cd[ref]
                    excel = '=' + re.sub(r'\{([^}]+)\}', sustituir, e).replace(' ', '')
                    hoja.cell(fila_de[f.id], col_de[c.id], excel)
                    escritas[(f.id, c.id)] = 'formula'
                    celdas_calc.append(celda_de[(f.id, c.id)])
                    if (f.id, c.id) in originales:
                        v0 = originales[(f.id, c.id)]
                        avisos.append(f'{nombre}{" · " + rotulo if rotulo else ""}, fila {f.id}, columna {c.id}, '
                                      f'celda {celda_de[(f.id, c.id)]}: el dato {v0!r} se sustituye por la fórmula '
                                      f'{excel}')
                        anotar(f, c, 'sustituido', 'celda calculada: va su fórmula, no el dato traído', v0, excel)
                    pendientes.remove(item)
                    avance = True
                if not avance:
                    break
            for f, c, e in pendientes:
                faltan = sorted({'/'.join(celda_ref(f, c, m)) for m in re.findall(r'\{([^}]+)\}', e)
                                 if celda_ref(f, c, m) not in escritas})
                propios.append(f'{nombre}{" · " + rotulo if rotulo else ""}, fila {f.id}, columna {c.id}: la fórmula '
                               f'no se escribe porque le faltan {", ".join(faltan)}')
                anotar(f, c, 'hueco', f'la fórmula no se escribe porque le faltan {", ".join(faltan)}',
                       originales.get((f.id, c.id)))
        calculadas[nombre] = tuple(celdas_calc)
        huecos += propios
        indice.append([formato.id, formato.titulo, 'con huecos' if propios else 'completo', nombre,
                       fuentes.get(formato.id, ''), len(propios)])
    hoja_traza = libro.create_sheet(HOJA_TRAZA)
    hoja_traza.append(['Hoja', 'Celda', 'Fila', 'Columna', 'Estado', 'Valor original', 'Fórmula', 'Motivo o cita'])
    for e in traza:
        hoja_traza.append([e['hoja'], e['celda'], e['fila'], e['columna'], e['estado'],
                           '' if e['valor_original'] is None else e['valor_original'], e['formula'], e['motivo']])
        # En la traza la fórmula se lee, no se calcula: va como texto.
        hoja_traza.cell(hoja_traza.max_row, 7).data_type = 's'
    destino = Path(destino)
    _guardar_libro(libro, destino)
    return LibroFormatos(destino, prefijo, hojas, calculadas, tuple(huecos), tuple(avisos), tuple(traza))


def valor_calculado(hoja: Any, ref: str, memo: dict[str, float] | None = None, pila: tuple[str, ...] = ()) -> float:
    """El valor de una celda de una hoja de openpyxl: un número, o su fórmula evaluada con el intérprete cerrado
    (sumas, restas, productos y cocientes de celdas, y ``SUM`` de una columna). Una celda vacía o de texto dentro de
    una fórmula, una división entre cero o una fórmula que no se lee son un :class:`FormulaError` con el error de Excel
    que daría (``#REF!``, ``#VALUE!``, ``#DIV/0!``, ``#NAME?``)."""
    memo = {} if memo is None else memo
    if ref in memo:
        return memo[ref]
    if ref in pila:
        raise FormulaError(f'referencia circular en {ref}')
    valor = hoja[ref].value
    if isinstance(valor, str) and valor.startswith('='):
        formula = valor[1:]

        def suma(m: re.Match) -> str:
            c1, f1, c2, f2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            if c1 != c2:
                raise FormulaError(f'{ref}: SUM de varias columnas no admitida')
            return '(' + '+'.join(f'{c1}{k}' for k in range(f1, f2 + 1)) + ')'
        formula = _SUMA_EXCEL.sub(suma, formula)
        refs = sorted(set(_CELDA.findall(formula)), key=lambda x: -len(x[0] + x[1]))
        variables = {}
        for col, fila in refs:
            variables[f'v_{col}{fila}'] = valor_calculado(hoja, f'{col}{fila}', memo, (*pila, ref))
        expr = _CELDA.sub(lambda m: f'v_{m.group(1)}{m.group(2)}', formula)
        try:
            resultado = evaluar(expr, variables)
        except FormulaError as exc:
            if 'cero' in str(exc):
                raise FormulaError(f'#DIV/0! en {ref}: {exc}') from exc
            raise FormulaError(f'#NAME? en {ref}: {exc}') from exc
        memo[ref] = resultado
        return resultado
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise FormulaError(f'#REF! en {pila[-1] if pila else ref}: apunta a {ref}, que está vacía')
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise FormulaError(f'#VALUE! en {pila[-1] if pila else ref}: {ref} no es un número ({valor!r})')
    memo[ref] = float(valor)
    return float(valor)


def comprobar_formatos(ruta: Path | str, libro_formatos: LibroFormatos) -> list[str]:
    """Reabre el libro: cada celda calculada es una fórmula, ninguna da un error de ``ERRORES_DE_FORMULA`` al
    evaluarla con sus celdas, y ninguna celda guarda el texto de un error. Devuelve los problemas, cada uno con su
    hoja y su celda (vacío si el libro está bien)."""
    from openpyxl import load_workbook

    libro = load_workbook(ruta)
    problemas: list[str] = []
    for nombre, celdas in libro_formatos.calculadas.items():
        if nombre not in libro.sheetnames:
            problemas.append(f'falta la hoja {nombre}')
            continue
        hoja = libro[nombre]
        memo: dict[str, float] = {}
        for ref in celdas:
            v = hoja[ref].value
            if not (isinstance(v, str) and v.startswith('=')):
                problemas.append(f'{nombre}!{ref}: celda calculada sin fórmula ({v!r})')
                continue
            try:
                valor_calculado(hoja, ref, memo)
            except FormulaError as exc:
                problemas.append(f'{nombre}!{ref}: {exc}')
    for hoja in libro.worksheets:
        for fila in hoja.iter_rows():
            for celda in fila:
                if isinstance(celda.value, str) and celda.value.strip() in ERRORES_DE_FORMULA:
                    problemas.append(f'{hoja.title}!{celda.coordinate}: {celda.value}')
    return problemas


# ================================================================================ Mapas de densidad (T10)
_GEOMETRIAS = {'punto': ('Point', 'MultiPoint'), 'poligono': ('Polygon', 'MultiPolygon'),
               'polilinea': ('LineString', 'MultiLineString')}


@dataclass(frozen=True)
class Mapas:
    carpeta: Path
    #: Entidad → fichero escrito.
    ficheros: Mapping[str, Path]
    huecos: tuple[str, ...] = ()
    regla: Mapping[str, str] = field(default_factory=dict)


def estructura_anexo9(registro: RegistroNormativo, fecha: str | None = None) -> tuple[list[dict[str, Any]], ReglaVigente]:
    """Las entidades del anexo 9 con sus campos en orden, del registro (``vad.anexo9.entidades``)."""
    try:
        rv = registro.regla('vad.anexo9.entidades', fecha)
    except RegistroError as exc:
        raise VadError(f'el registro no trae la estructura del anexo 9 (vad.anexo9.entidades): {exc}') from exc
    entidades = rv.regla.valor
    if not isinstance(entidades, list) or not entidades:
        raise VadError('vad.anexo9.entidades tiene que ser una lista no vacía de entidades con sus campos')
    for e in entidades:
        if not e.get('entidad') or e.get('geometria') not in _GEOMETRIAS or not e.get('campos'):
            raise VadError(f'una entidad del anexo 9 no trae nombre, geometría o campos: {e!r}')
    return entidades, rv


def _decimales(valor: float) -> int:
    texto = repr(float(valor))
    if 'e' in texto or 'E' in texto:
        return len(f'{valor:.15f}'.rstrip('0').split('.')[1]) if '.' in f'{valor:.15f}'.rstrip('0') else 0
    _, _, dec = texto.partition('.')
    return 0 if dec == '0' else len(dec)


def _revisar_campo(entidad: str, n: int, campo: Mapping[str, Any], valor: Any) -> str | None:
    lugar = f'{entidad}, registro {n}, campo {campo["nombre"]}'
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return f'{lugar}: sin valor; no se rellena'
    if campo['tipo'] == 'caracter':
        if not isinstance(valor, str):
            return f'{lugar}: el anexo 9 lo pide de tipo carácter y trae {valor!r}'
        if len(valor) > int(campo['ancho']):
            return f'{lugar}: {len(valor)} caracteres y el anexo 9 da un ancho de {campo["ancho"]}'
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return f'{lugar}: el anexo 9 lo pide numérico y trae {valor!r}'
    dec = int(campo['decimales'] or 0)
    if _decimales(valor) > dec:
        return f'{lugar}: {valor!r} tiene más de {dec} decimales'
    # Como en un campo numérico de dBase, el ancho cuenta el punto y los decimales; un valor menor que 1 no necesita el
    # 0 de la parte entera (N(5,4) admite .1234).
    enteros = len(str(int(abs(valor)))) if abs(valor) >= 1 else 0
    if enteros + (dec + 1 if dec else 0) + (1 if valor < 0 else 0) > int(campo['ancho']):
        return f'{lugar}: {valor!r} no cabe en un ancho de {campo["ancho"]} con {dec} decimales'
    return None


def _reproyectar(coordenadas: Any, transformar: Any) -> Any:
    if coordenadas and isinstance(coordenadas[0], (int, float)):
        x, y = transformar.transform(coordenadas[0], coordenadas[1])
        return [x, y, *coordenadas[2:]]
    return [_reproyectar(c, transformar) for c in coordenadas]


def escribir_mapas(registro: RegistroNormativo, capas: Mapping[str, Sequence[Mapping[str, Any]]],
                   carpeta: Path | str, *, crs_origen: str, crs_destino: str | None = None,
                   diccionario: Mapping[str, str] | None = None, fecha: str | None = None) -> Mapas:
    """Escribe cada entidad del anexo 9 en ``<carpeta>/<Entidad>.geojson``. ``capas``: entidad → registros
    ``{'propiedades': {campo: valor}, 'geometria': {type, coordinates}}``. ``crs_origen`` (del perfil) es obligatorio;
    con ``crs_destino`` las coordenadas se reproyectan sobre una copia. ``diccionario`` describe los campos
    adicionales (campo → descripción); sin él, un campo adicional se nombra y no se escribe."""
    if not str(crs_origen or '').strip():
        raise VadError('los mapas del anexo 9 necesitan el CRS de origen de la entrada (del perfil); no se supone')
    entidades, rv = estructura_anexo9(registro, fecha)
    por_nombre = {e['entidad']: e for e in entidades}
    ajenas = sorted(set(capas) - set(por_nombre))
    if ajenas:
        raise VadError(f'entidades que el anexo 9 no tiene: {", ".join(ajenas)}')
    transformar = make_transformer(crs_origen, crs_destino) if crs_destino and crs_destino != crs_origen else None
    carpeta = Path(carpeta)
    diccionario = dict(diccionario or {})
    ficheros: dict[str, Path] = {}
    huecos: list[str] = []
    for e in entidades:
        registros = capas.get(e['entidad'])
        if not registros:
            huecos.append(f'{e["entidad"]}: sin registros; el mapa no se escribe')
            continue
        nombres = [c['nombre'] for c in e['campos']]
        rasgos = []
        for n, reg in enumerate(registros, 1):
            props = dict(reg.get('propiedades') or {})
            geo = reg.get('geometria') or {}
            if geo.get('type') not in _GEOMETRIAS[e['geometria']]:
                raise VadError(f'{e["entidad"]}, registro {n}: la entidad es de tipo {e["geometria"]} y la geometría '
                               f'es {geo.get("type")!r}')
            salida = {}
            for c in e['campos']:
                problema = _revisar_campo(e['entidad'], n, c, props.get(c['nombre']))
                if problema:
                    huecos.append(problema)
                salida[c['nombre']] = props.get(c['nombre']) if problema is None else None
            for extra in [k for k in props if k not in nombres]:
                if diccionario.get(extra, '').strip():
                    salida[extra] = props[extra]
                else:
                    huecos.append(f'{e["entidad"]}, registro {n}: el campo adicional {extra!r} no está en el '
                                  'diccionario de datos; no se escribe')
            coords = copy.deepcopy(geo.get('coordinates'))
            if transformar is not None:
                coords = _reproyectar(coords, transformar)
            rasgos.append({'type': 'Feature', 'properties': salida,
                           'geometry': {'type': geo['type'], 'coordinates': coords}})
        ruta = carpeta / f'{e["entidad"]}.geojson'
        write_json_atomic(ruta, {'type': 'FeatureCollection', 'name': e['entidad'],
                                 'crs_csg': crs_destino or crs_origen, 'features': rasgos,
                                 'diccionario_de_datos': {k: v for k, v in diccionario.items()
                                                          if any(k in r['properties'] for r in rasgos)}})
        ficheros[e['entidad']] = ruta
    return Mapas(carpeta, ficheros, tuple(huecos), {'clave': rv.regla.clave, 'acto': rv.norma.acto,
                                                    'huella': rv.huella()})


# ================================================================================ Manifiesto de fuentes (T10)
# Auditoría D.2 (2026-11-24): la huella de un fichero es una sola, la de dominio/util; este nombre queda por quien lo llama.
huella_fichero = sha256_file


def manifiesto_fuentes(entradas: Mapping[str, Mapping[str, str]], registro: RegistroNormativo,
                       destino: Path | str, fecha: str | None = None) -> dict[str, Any]:
    """Escribe el manifiesto de las fuentes del estudio: por cada entrada (nombre → ``{ruta, version, regla}``), su
    SHA-256, su tamaño, su versión y la regla del registro que la rige, con su acto y su huella. Una entrada sin
    versión o sin regla registrada se rechaza: una fuente sin procedencia no entra en el estudio."""
    fuentes = []
    for nombre in sorted(entradas):
        e = entradas[nombre]
        ruta = Path(e.get('ruta') or '')
        if not ruta.is_file():
            raise VadError(f'la fuente {nombre} no existe: {ruta}')
        if not str(e.get('version') or '').strip():
            raise VadError(f'la fuente {nombre} no dice su versión')
        try:
            rv = registro.regla(str(e.get('regla') or ''), fecha)
        except RegistroError as exc:
            raise VadError(f'la fuente {nombre} no tiene su entrada en el registro normativo: {exc}') from exc
        fuentes.append({'nombre': nombre, 'ruta': str(ruta.resolve()), 'sha256': huella_fichero(ruta),
                        'bytes': ruta.stat().st_size, 'version': str(e['version']).strip(),
                        'registro': {'clave': rv.regla.clave, 'acto': rv.norma.acto, 'huella': rv.huella()}})
    datos = {'esquema': 'vad_manifiesto_fuentes_v1', 'fuentes': fuentes}
    write_json_atomic(Path(destino), datos)
    return datos


def comprobar_manifiesto(destino: Path | str) -> list[str]:
    """Recalcula la huella de cada fuente del manifiesto; devuelve las que faltan o cambiaron (vacío si cuadran)."""
    import json

    datos = json.loads(Path(destino).read_text(encoding='utf-8'))
    problemas = []
    for f in datos.get('fuentes') or ():
        ruta = Path(f['ruta'])
        if not ruta.is_file():
            problemas.append(f'{f["nombre"]}: falta el fichero {ruta}')
        elif huella_fichero(ruta) != f['sha256']:
            problemas.append(f'{f["nombre"]}: la huella cambió desde el manifiesto')
    return problemas
