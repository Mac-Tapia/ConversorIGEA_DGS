"""Aceptación del PIDE y del largo plazo con lo publicado y custodiado (072 T11 y T13).

Por qué así (orden del usuario del 2026-11-19): «lo que no puede cerrar debe usar los archivos que descargaste de la
página de Osinergmin del PIT, en los entregables; lo que publique o no Osinergmin u otras entidades no debería ser una
limitación o exigencia para cierre». Dos cosas que esperaban a un tercero se cierran con lo que ya está descargado:

- **Base de módulos de transmisión (T13)**: se valora con la base PUBLICADA vigente (la que ya está en disco con su
  URL, fecha y huella). Una resolución posterior que sustituya la base no es requisito: cuando se descargue, entra como
  versión nueva por su huella (``base_vigente``), la anterior se conserva para la trazabilidad y lo valorado con ella
  queda marcado como de la versión anterior (memoria «ficheros reemplazables por periodo»).
- **Obra de una red real (T13)**: los formatos de inversión publicados de un PIT (F-301, líneas; F-302, subestaciones)
  ya traen obras reales con sus módulos y metrados. ``obra_desde_formatos_inversion`` los pasa a elementos de
  ``costos_fuentes.valorar_obra`` y conserva la cifra publicada de cada uno para compararla; lo que no tiene módulo
  (terreno, indirectos, gastos) queda como hueco nombrado, nunca sumado ni supuesto.
- **Dos entregables (T11)**: la estructura de los informes del conversor (los módulos de ``informes_planeamiento``)
  se compara con la de los entregables oficiales custodiados (sus títulos de capítulo), y el acta dice qué capítulo
  oficial cubre cada módulo y cuáles quedan como hueco nombrado. Los nombres y la forma de una empresa no se copian al
  código: los títulos se leen de su documento.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..aplicacion.costos_fuentes import CostosError, TablaCostos, valorar_obra
from ..aplicacion.demanda_medida import abrir_libro, filas_de_hoja
from ..dominio.util import cuenta, plural

__all__ = ['ORIGEN_ACTA', 'acta_de_estructura', 'base_vigente', 'comparar_valoracion',
           'obra_desde_formatos_inversion', 'titulos_de_docx']

#: Origen declarado de las actas que redacta el maestro en lugar del usuario (memoria «maestro hace de humano»).
ORIGEN_ACTA = 'maestro/revisor independiente'
#: Cuántas palabras significativas en común hacen que un módulo cubra un capítulo oficial (Jaccard).
UMBRAL_COBERTURA = 0.34
_MODULO = re.compile(r'^[A-Z]{2,3}-[A-Z0-9]')
_VACIAS = frozenset('a al de del el en la las lo los para por que se su sus un una y o e con sin'.split())


def _normal(v: Any) -> str:
    texto = unicodedata.normalize('NFKD', str(v or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'\(.*?\)', ' ', texto)).strip()


# --------------------------------------------------------------------------- base vigente por huella
def base_vigente(versiones: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """La versión vigente de una base publicada entre las descargadas, por su vigencia y su huella.

    Cada versión es su ``fuente.json``: ``resolucion``, ``sha256``, ``vigencia_desde`` (AAAA-MM-DD) y, si se quiere,
    ``fecha_descarga``. La misma huella dos veces es la misma versión; una huella nueva es una versión nueva aunque
    traiga la misma resolución. La más reciente por vigencia es la vigente; las demás se devuelven como anteriores."""
    por_huella: dict[str, Mapping[str, Any]] = {}
    for v in versiones:
        sha = str(v.get('sha256') or '').strip().lower()
        if not re.fullmatch(r'[0-9a-f]{64}', sha):
            raise CostosError(f'versión {v.get("resolucion")!r} sin huella sha256: no se puede versionar')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(v.get('vigencia_desde') or '')):
            raise CostosError(f'versión {v.get("resolucion")!r} sin vigencia_desde AAAA-MM-DD')
        por_huella.setdefault(sha, v)
    if not por_huella:
        raise CostosError('ninguna versión descargada de la base')
    orden = sorted(por_huella.values(), key=lambda v: (str(v['vigencia_desde']), str(v.get('fecha_descarga') or '')))
    vigente = orden[-1]
    return {'vigente': dict(vigente), 'anteriores': [dict(v) for v in orden[:-1]],
            'aviso': (f'base vigente: {vigente.get("resolucion")} (sha256 {str(vigente["sha256"])[:12]}…); '
                      + (f'{cuenta(len(orden) - 1, "versión anterior conservada", "versiones anteriores conservadas")}; lo valorado con '
                         f'{plural(len(orden) - 1, "ella", "ellas")} queda marcado'
                         if len(orden) > 1 else 'una sola versión descargada; la siguiente entra por su huella'))}


# --------------------------------------------------------------------------- obra publicada
def _hoja(libro: Any, prefijo: str, nombre: str, alternativa: str | None) -> list[str]:
    hojas = [h for h in libro.sheet_names if h.strip().startswith(prefijo)
             and (alternativa is None or h.strip().endswith(alternativa))]
    if not hojas:
        raise CostosError(f'{nombre}: sin hoja {prefijo}' + (f' de la {alternativa}' if alternativa else ''))
    return hojas


def _columnas(filas: list[list[Any]], rotulos: Mapping[str, str], nombre: str, hoja: str) -> tuple[int, dict[str, int]]:
    """La última fila de la cabecera (índice) y la columna de cada rótulo, buscados por contenido.

    Las cabeceras de los formatos de inversión ocupan dos filas («CÓDIGO» arriba y «ELEMENTO» abajo; «LONGITUD» y
    «(km)»): un rótulo vale en cualquiera de las dos, y gana el primero de la de arriba."""
    for n in range(min(20, len(filas))):
        pares = [[_normal(c) for c in f] for f in filas[n:n + 2]]
        col = {campo: next((i for fila in pares for i, x in enumerate(fila) if x.startswith(r)), -1)
               for campo, r in rotulos.items()}
        if all(i >= 0 for i in col.values()):
            return n + len(pares) - 1, col
    raise CostosError(f'{nombre}, {hoja}: sin la cabecera con {", ".join(rotulos.values())}')


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def obra_desde_formatos_inversion(ruta: Path | str, alternativa: str | None = None) -> dict[str, Any]:
    """Los elementos de una obra publicada en los formatos de inversión del PIT, listos para ``valorar_obra``.

    F-301 (líneas): cada tramo con código, su módulo, su longitud en km y su total publicado. F-302 (subestaciones):
    cada elemento con código, su módulo (una unidad) y su total publicado. ``alternativa`` elige las hojas que acaban
    en ese sufijo («Alt1»). Las filas con cifra y sin módulo (terreno, indirectos, gastos) son huecos nombrados."""
    ruta = Path(ruta)
    libro = abrir_libro(ruta)
    elementos, huecos = [], []
    for hoja in _hoja(libro, 'F-301', ruta.name, alternativa):
        filas = filas_de_hoja(libro, hoja)
        n, col = _columnas(filas, {'codigo': 'CODIGO', 'longitud': 'LONGITUD', 'modulo': 'MODULO', 'factor': 'FACTOR',
                                   'total': 'TOTAL'}, ruta.name, hoja)
        # «TOTAL» rotula también la fila de totales al pie; la columna del total es la de la cabecera.
        for k, f in enumerate(filas[n + 1:], n + 2):
            codigo, modulo = str(f[col['codigo']] or '').strip(), str(f[col['modulo']] or '').strip()
            if not codigo or _normal(f[0]).startswith('TOTAL'):
                continue
            if not _MODULO.match(modulo):
                huecos.append({'hoja': hoja, 'fila': k, 'elemento': codigo, 'motivo': f'sin módulo ({modulo!r})'})
                continue
            elementos.append({'elemento': codigo, 'ambito': 'transmision', 'codigo': modulo,
                              'cantidad': _num(f[col['longitud']]), 'unidad': 'km', 'hoja': hoja, 'fila': k,
                              'publicado': _num(f[col['total']]), 'factor_publicado': _num(f[col['factor']])})
    for hoja in _hoja(libro, 'F-302', ruta.name, alternativa):
        filas = filas_de_hoja(libro, hoja)
        n, col = _columnas(filas, {'elemento': 'ELEMENTO', 'descripcion': 'DESCRIPCION', 'modulo': 'MODULO',
                                   'basico': 'BASICO', 'auxiliares': 'SERVICIOS', 'total': 'TOTAL'}, ruta.name, hoja)
        # La cabecera del F-302 ocupa dos filas: el código del elemento va en la primera columna y el total al final.
        total = max(i for f in filas[n - 1:n + 1] for i, x in enumerate(_normal(c) for c in f) if x == 'TOTAL')
        for k, f in enumerate(filas[n + 1:], n + 2):
            codigo = str(f[col['elemento']] or '').strip() if col['elemento'] < len(f) else ''
            modulo = str(f[col['modulo']] or '').strip()
            descripcion = str(f[col['descripcion']] or '').strip()
            if codigo and _MODULO.match(modulo):
                elementos.append({'elemento': codigo, 'ambito': 'transmision', 'codigo': modulo, 'cantidad': 1.0,
                                  'unidad': 'u', 'hoja': hoja, 'fila': k, 'descripcion': descripcion,
                                  'publicado': _num(f[total]) if total < len(f) else None,
                                  # El costo básico (moneda extranjera, nacional, aluminio y cobre), sin los servicios
                                  # auxiliares, los comunes ni los indirectos que el total del elemento ya reparte.
                                  'publicado_basico': sum(_num(v) or 0.0 for v in f[col['basico']:col['auxiliares']])})
            elif descripcion and not codigo and any((_num(v) or 0) > 0 for v in f[col['modulo'] + 1:total]) \
                    and not _MODULO.match(modulo) and not _normal(descripcion).startswith(('TOTAL', 'SUB TOTAL')):
                huecos.append({'hoja': hoja, 'fila': k, 'elemento': descripcion,
                               'motivo': 'componente del formato sin módulo en la base: no se suma ni se supone'})
    return {'libro': ruta.name, 'alternativa': alternativa, 'elementos': elementos, 'huecos': huecos,
            'hojas_de_modulos': [h for h in libro.sheet_names if 'MODULOS' in _normal(h)]}


def _causas(e: Mapping[str, Any], conv: float | None, otras_bases: Sequence[str]) -> list[str]:
    """Por qué la cifra del conversor no es la publicada, con lo que el propio formato dice."""
    if conv is None:
        return ['sin costo en la base vigente: ver «sin_costo»']
    causas = []
    factor = e.get('factor_publicado')
    if factor is not None and not math.isclose(factor, 1.0):
        causas.append(f'el publicado aplica el factor de costo {factor:g} de su columna FACTOR; el conversor no aplica '
                      'factores que el estudio no declare con su sustento (072:RF-8)')
    if e.get('publicado_basico') is not None:
        causas.append('el total publicado del elemento reparte servicios auxiliares, costos comunes e indirectos; la '
                      'cifra comparable con el módulo es el costo básico (publicado_basico)')
    if otras_bases:
        causas.append(f'el libro publicado valora con su propia hoja de módulos ({", ".join(otras_bases)}); el conversor, '
                      'con la base vigente: la diferencia restante es de precios entre bases')
    return causas


def comparar_valoracion(obra: Mapping[str, Any], tabla: TablaCostos,
                        otras_bases: Sequence[str] = ()) -> dict[str, Any]:
    """La obra publicada valorada con la base vigente, elemento a elemento frente a la cifra publicada.

    ``otras_bases``: las hojas de módulos que trae el propio libro publicado (su base de precios), para nombrarlas en la
    causa de la diferencia."""
    valoracion = valorar_obra(obra['elementos'], {'transmision': tabla})
    por_elemento = {v['elemento']: v for v in valoracion['valorados']}
    filas = []
    for e in obra['elementos']:
        v = por_elemento.get(e['elemento'])
        conv = v['costo'] if v else None
        pub = e.get('publicado')
        factor = e.get('factor_publicado')
        comparable = e.get('publicado_basico')
        if comparable is None and pub is not None and factor:
            comparable = pub / factor
        filas.append({'elemento': e['elemento'], 'modulo': e['codigo'], 'cantidad': e['cantidad'],
                      'unidad': e['unidad'], 'hoja': e['hoja'], 'fila': e['fila'], 'publicado': pub,
                      'factor_publicado': factor, 'publicado_comparable': comparable,
                      'conversor': conv, 'diferencia': conv - pub if conv is not None and pub is not None else None,
                      'relacion_comparable': conv / comparable if conv is not None and comparable else None,
                      'causas': _causas(e, conv, otras_bases)})
    return {'base': {'resolucion': tabla.fuente.resolucion, 'sha256': tabla.fuente.huella,
                     'moneda': tabla.fuente.moneda, 'url': tabla.fuente.url},
            'total_por_moneda': valoracion['total_por_moneda'], 'completa': valoracion['completa'],
            'sin_costo': valoracion['sin_costo'], 'huecos_del_formato': obra['huecos'], 'elementos': filas,
            'total_publicado': sum(f['publicado'] or 0.0 for f in filas)}


# --------------------------------------------------------------------------- estructura de los entregables
def titulos_de_docx(ruta: Path | str, niveles: int = 1) -> list[dict[str, Any]]:
    """Los títulos de capítulo de un documento Word, en su orden.

    Con estilos de título («Heading n» o «Título n»), los ``niveles`` más altos que el documento USA (un informe
    numera sus capítulos con «Heading 2» y otro con «Heading 1»: el nivel no se supone). Sin estilos de título, los
    párrafos breves enteros en negrita, que es como escribe sus títulos el libro modelo del conversor."""
    import docx

    parrafos = [p for p in docx.Document(str(ruta)).paragraphs if p.text.strip()]
    con_nivel = []
    for p in parrafos:
        estilo = p.style.name if p.style is not None else ''
        m = re.match(r'(?:heading|t[ií]tulo)\s*(\d)', estilo.strip(), re.I)
        if m:
            con_nivel.append((int(m.group(1)), p.text.strip()))
    if con_nivel:
        usados = sorted({n for n, _ in con_nivel})[:max(1, niveles)]
        return [{'nivel': n, 'titulo': x} for n, x in con_nivel if n in usados]
    return [{'nivel': 1, 'titulo': p.text.strip()} for p in parrafos
            if len(p.text.strip()) <= 120 and p.runs and all(r.bold for r in p.runs if r.text.strip())]


def _palabras(texto: str) -> set[str]:
    # Singular y plural cuentan igual («Metodología» y «CRITERIOS Y METODOLOGÍAS»).
    palabras = {w for w in re.findall(r'[a-z]+', _normal(texto).lower()) if len(w) > 2 and w not in _VACIAS}
    return {w[:-2] if w.endswith('es') and len(w) > 5 else w[:-1] if w.endswith('s') and len(w) > 4 else w
            for w in palabras}


def acta_de_estructura(oficiales: Mapping[str, Sequence[Mapping[str, Any]]],
                       conversor: Mapping[str, Sequence[str]], *, revisor: str, fecha: str) -> dict[str, Any]:
    """Acta de la comparación de estructura: cada capítulo oficial con el módulo del conversor que lo cubre o su hueco.

    ``oficiales``: entregable → títulos del documento oficial (``titulos_de_docx``); ``conversor``: módulo → los títulos
    de su documento generado, el primero el del módulo. Un capítulo lo cubre el módulo cuyo título está entero en él, o
    el que tiene más palabras significativas en común con alguno de sus títulos (Jaccard ≥ ``UMBRAL_COBERTURA``); sin
    ninguno, queda como hueco nombrado."""
    if not str(revisor or '').strip():
        raise ValueError('el acta nombra a su revisor')
    capitulos, cubiertos = [], set()
    for entregable, titulos in oficiales.items():
        for t in titulos:
            p = _palabras(t['titulo'])
            mejor = (0.0, None, None)
            for modulo, propios in conversor.items():
                for n, propio in enumerate(propios):
                    q = _palabras(propio.split(':', 1)[-1] if n == 0 else propio)
                    # El título del módulo (el primero, sin «PIDE:» ni el nombre del entregable) cubre el capítulo
                    # que lo contiene entero: «DIAGNÓSTICO DE LOS SISTEMAS …» es el módulo «Diagnóstico».
                    j = 1.0 if n == 0 and q and q <= p else (len(p & q) / len(p | q) if p | q else 0.0)
                    if j > mejor[0]:
                        mejor = (j, modulo, propio)
            cubre = mejor[0] >= UMBRAL_COBERTURA
            if cubre:
                cubiertos.add(mejor[1])
            capitulos.append({'entregable': entregable, 'capitulo': t['titulo'], 'nivel': t['nivel'],
                              'modulo': mejor[1] if cubre else None, 'titulo_conversor': mejor[2] if cubre else None,
                              'similitud': round(mejor[0], 3),
                              'estado': 'cubierto' if cubre else 'hueco nombrado: el conversor no tiene esta sección'})
    return {'revisor': revisor, 'origen': ORIGEN_ACTA, 'fecha': fecha, 'umbral': UMBRAL_COBERTURA,
            'capitulos': capitulos, 'cubiertos': sum(c['modulo'] is not None for c in capitulos),
            'huecos': [c['capitulo'] for c in capitulos if c['modulo'] is None],
            'modulos_sin_capitulo': sorted(set(conversor) - cubiertos)}
