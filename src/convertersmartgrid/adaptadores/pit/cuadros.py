"""Cuadros del expediente del PIT, desde su definición transcrita en el registro normativo (107:RF-9).

Las columnas de cada cuadro no están en el código: las da la regla ``pit.cuadro.*`` del registro, transcrita del
anexo que la fija, con el campo del programa que llena cada columna. Un cuadro que el registro no transcribe no se
inventa: el expediente da su tabla de trabajo y dice que el cuadro oficial no está transcrito.

Cada celda lleva su traza: la fuente (con su huella), el cálculo que la produjo, el motor y la regla con su estado.
Los cuadros se escriben en el libro modelo de la empresa con ``libro_informe.rellenar_con_excel``, el mismo
mecanismo de los informes, sin otro escritor de Excel.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..libro_informe import rellenar_con_excel
from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit import PitError

__all__ = ['celdas_de_cuadros', 'codigos_de_grupos', 'definiciones', 'formatos_aplicables', 'plan_de_cuadros',
           'plan_de_formatos', 'escribir_libro_de_cuadros']

PREFIJO = 'pit.cuadro.'
#: La regla que lista los formatos de una norma (``pit.formatos_217``, la de otra norma o periodo…): trae ``grupos``.
PREFIJO_LISTA = 'pit.formatos'
#: La plantilla transcrita de cada formato (aclaración de 107:RF-9).
PREFIJO_FORMATO = 'pit.formato.'
_CODIGO = re.compile(r'([A-Z]+)-(\d+)')
_REFERENCIA = re.compile(r"'?([^'!]+)'?!(\$?[A-Z]{1,3}\$?\d+)")


def codigos_de_grupos(grupos: Iterable[str]) -> list[str]:
    """Los códigos de los rangos que lista la norma («F-101 a F-124», «F-401»), en su orden y sin una lista fija."""
    codigos: list[str] = []
    for rango in grupos:
        partes = rango.split(' a ')
        extremos = [m for m in (_CODIGO.fullmatch(x.strip()) for x in partes) if m is not None]
        if not 1 <= len(partes) <= 2 or len(extremos) != len(partes):
            raise PitError(f'rango de formatos ilegible en el registro: {rango!r} (se espera «F-101 a F-124»)')
        prefijo, ancho = extremos[0].group(1), len(extremos[0].group(2))
        desde, hasta = int(extremos[0].group(2)), int(extremos[-1].group(2))
        if extremos[-1].group(1) != prefijo or hasta < desde:
            raise PitError(f'rango de formatos ilegible en el registro: {rango!r}')
        codigos += [f'{prefijo}-{n:0{ancho}d}' for n in range(desde, hasta + 1)]
    repetidos = sorted({c for c in codigos if codigos.count(c) > 1})
    if repetidos:
        raise PitError(f'formatos repetidos en los grupos del registro: {repetidos}')
    return codigos


def _regla_de_lista(registro: RegistroNormativo, fecha: str | None):
    candidatas = []
    for clave in sorted({r.clave for n in registro.normas.values() for r in n.reglas
                         if r.clave.startswith(PREFIJO_LISTA) and not r.clave.startswith(PREFIJO_FORMATO)}):
        try:
            rv = registro.regla(clave, fecha)
        except RegistroError:
            continue  # justificado: esa lista no está vigente en la fecha pedida; se prueba la siguiente
        if isinstance(rv.regla.valor, Mapping) and rv.regla.valor.get('grupos'):
            candidatas.append(rv)
    if not candidatas:
        raise PitError('ninguna norma vigente del registro lista los formatos (regla pit.formatos… con «grupos»): '
                       'sin ella no se emite una lista supuesta')
    return max(candidatas, key=lambda rv: (rv.norma.vigencia_desde, rv.norma.acto))


def formatos_aplicables(registro: RegistroNormativo, fecha: str | None = None) -> dict[str, Any]:
    """Los formatos que lista la norma vigente, cada uno transcrito (con su título, su hoja y su regla) o nombrado
    como no transcrito, sin inventar nada (aclaración de 107:RF-9)."""
    lista = _regla_de_lista(registro, fecha)
    formatos, no_transcritos = [], []
    for codigo in codigos_de_grupos(lista.regla.valor['grupos']):
        try:
            rv = registro.regla(PREFIJO_FORMATO + codigo, fecha)
        except RegistroError:
            rv = None  # justificado: un formato sin plantilla transcrita se nombra como no transcrito, abajo
        if rv is None or not isinstance(rv.regla.valor, Mapping) or not rv.regla.valor.get('filas'):
            formatos.append({'codigo': codigo, 'transcrito': False})
            no_transcritos.append(codigo)
            continue
        valor = rv.regla.valor
        formatos.append({'codigo': codigo, 'transcrito': True, 'titulo': valor.get('titulo', ''),
                         'hoja': valor.get('hoja') or codigo, 'libro': valor.get('libro', ''),
                         'regla': {'clave': rv.regla.clave, 'norma': rv.norma.acto, 'estado': rv.estado,
                                   'pagina': rv.regla.pagina, 'huella': rv.huella()}})
    return {'norma': lista.norma.acto, 'clave': lista.regla.clave, 'estado': lista.estado,
            'formatos': formatos, 'no_transcritos': no_transcritos}


def _formulas_de_vinculos(vinculos: Iterable[Mapping[str, str]], formatos: Mapping[str, Any] | None
                          ) -> list[dict[str, str]]:
    """Cada celda derivada, como fórmula hacia la celda de la que sale (``F-306!C8`` ← ``F-305!D12``)."""
    hojas = {f['codigo']: f for f in (formatos or {}).get('formatos', ())}
    formulas = []
    for v in vinculos:
        partes = {}
        for lado in ('celda', 'origen'):
            m = _REFERENCIA.fullmatch(v.get(lado) or '')
            if not m:
                raise PitError(f'vínculo con {lado} ilegible: {v.get(lado)!r} (se espera «F-305!D12»)')
            codigo = m.group(1)
            if codigo not in hojas:
                raise PitError(f'vínculo a {codigo}, que la norma vigente no lista')
            if not hojas[codigo]['transcrito']:
                raise PitError(f'vínculo a {codigo}, que el registro no transcribe')
            partes[lado] = (hojas[codigo]['hoja'], m.group(2))
        hoja, celda = partes['origen']
        formulas.append({'celda': f'{partes["celda"][0]}!{partes["celda"][1]}', 'formula': f"='{hoja}'!{celda}"})
    return formulas


def definiciones(registro: RegistroNormativo, fecha: str | None = None) -> dict[str, dict[str, Any]]:
    """Clave → definición del cuadro, con la regla de la que sale y su estado."""
    claves = sorted({r.clave for n in registro.normas.values() for r in n.reglas if r.clave.startswith(PREFIJO)})
    out = {}
    for clave in claves:
        rv = registro.regla(clave, fecha)
        valor = rv.regla.valor
        if not isinstance(valor, Mapping) or not valor.get('columnas'):
            raise PitError(f'{clave} ({rv.norma.acto}) no trae sus columnas transcritas')
        out[clave] = {**valor, 'regla': {'clave': clave, 'norma': rv.norma.acto, 'estado': rv.estado,
                                         'obligatoria': rv.obligatoria, 'articulo_o_anexo': rv.regla.articulo_o_anexo,
                                         'pagina': rv.regla.pagina, 'huella': rv.huella()}}
    return out


def celdas_de_cuadros(defs: Mapping[str, Mapping[str, Any]], filas: Mapping[str, Sequence[Mapping[str, Any]]]
                      ) -> list[dict[str, Any]]:
    """Las celdas de cada cuadro. ``filas``: tipo de fila (``altas``, ``bajas``…) → filas con sus campos y su traza.

    Cada fila trae ``campos`` (lo que llena las columnas) y ``traza`` (fuente, cálculo y motor); la celda añade la
    regla del cuadro. Un valor que no se puede dar (otra moneda, un dato que falta) queda vacío y su traza lo dice.
    """
    celdas = []
    for clave, d in sorted(defs.items()):
        for i, fila in enumerate(filas.get(str(d.get('filas') or '')) or (), start=1):
            campos = {**fila['campos'], 'numero': fila['campos'].get('numero', i)}
            for col in d['columnas']:
                valor = campos.get(col['campo'])
                traza = {**fila['traza'], 'regla': d['regla'], 'campo': col['campo']}
                if col.get('moneda') and valor is not None and campos.get('moneda') != col['moneda']:
                    traza['motivo'] = (f'el cuadro pide {col["moneda"]} y la inversión está en '
                                       f'{campos.get("moneda") or "una moneda no declarada"}: sin tipo de cambio')
                    valor = None
                elif valor is None:
                    traza['motivo'] = f'sin dato para «{col["nombre"]}»'
                celdas.append({'id': f'{clave}!{i}:{col["nombre"]}', 'cuadro': clave, 'fila': i,
                               'columna': col['nombre'], 'valor': valor, 'traza': traza})
    return celdas


def plan_de_cuadros(celdas: Sequence[Mapping[str, Any]], config: Mapping[str, Any], *, destino: Path,
                    formatos: Mapping[str, Any] | None = None, vinculos: Iterable[Mapping[str, str]] = ()
                    ) -> dict[str, Any]:
    """El plan para Excel con el formato de ``libro_informe``: cada cuadro desde la celda de su hoja en el perfil
    (``pit.libro_cuadros``: ``modelo`` y ``cuadros`` clave → ``{hoja, celda}``). Las celdas derivadas de otro formato
    (``vinculos``: ``celda`` ← ``origen``, entre formatos de ``formatos_aplicables``) van como fórmula vinculada."""
    from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, get_column_letter

    if not config.get('modelo'):
        raise PitError('pit.libro_cuadros.modelo: sin libro modelo no hay cuadros en Excel')
    formulas = _formulas_de_vinculos(vinculos, formatos)
    destinos = config.get('cuadros') or {}
    escribir, vaciar, huecos = [], [], []
    columnas: dict[str, list[str]] = {}
    for c in celdas:
        columnas.setdefault(c['cuadro'], [])
        if c['columna'] not in columnas[c['cuadro']]:
            columnas[c['cuadro']].append(c['columna'])
    for c in celdas:
        sitio = destinos.get(c['cuadro'])
        if not sitio:
            huecos.append(f'{c["cuadro"]} sin sitio en el libro (pit.libro_cuadros.cuadros)')
            continue
        letra, fila0 = coordinate_from_string(sitio['celda'])
        col = column_index_from_string(letra) + columnas[c['cuadro']].index(c['columna'])
        ref = f'{sitio["hoja"]}!{get_column_letter(col)}{fila0 + c["fila"] - 1}'
        if c['valor'] in (None, ''):
            vaciar.append(ref)
            huecos.append(c['id'])
        else:
            escribir.append({'celda': ref, 'valor': c['valor']})
    return {'modelo': str(Path(config['modelo']).resolve()), 'destino': str(Path(destino).resolve()),
            'borrar_hojas': [], 'sin_imagenes': [], 'vaciar': vaciar, 'escribir': escribir, 'formulas': formulas,
            'imagenes': [], 'ancho_imagen': 420.0, 'huecos': list(dict.fromkeys(huecos))}


def plan_de_formatos(resultados: Sequence[Mapping[str, Any]], *, modelo: Path, destino: Path) -> dict[str, Any]:
    """El plan para Excel con el formato de ``libro_informe`` desde los resultados de ``plantillas.celdas_de_formato``
    (107-P10b): cada celda en su referencia de la hoja de su formato (``F-002!A10``) y, antes de escribirlas, las filas
    que hay que insertar (``insertar_filas``, de ``insertar_en``, en su orden). ``modelo`` es una copia del libro
    oficial, nunca el original. Un formato con filas que insertar sin saber dónde (los grupos repetidos) es un error que
    lo nombra: escribir sin insertarlas pisaría las filas de abajo."""
    escribir, vaciar, huecos, insertar, fotos = [], [], [], [], []
    for r in resultados:
        fotos += [dict(i) for i in r.get('imagenes') or ()]   # F-123: el mapa de cada año en su hoja
        sitios = list(r.get('insertar_en') or ())
        sin_sitio = sorted(set(r.get('filas_a_insertar') or {}) - {i['bloque'] for i in sitios})
        sin_sitio += sorted(r.get('grupos_a_insertar') or {})
        if sin_sitio:
            raise PitError(f'{r.get("codigo")}: no se sabe dónde insertar las filas de {sin_sitio}; sin insertarlas no '
                           'se escribe el libro')
        if r.get('hojas_a_copiar'):
            # Un formato por sistema eléctrico (F-106, F-108) con más de un sistema: sus copias de hoja no existen en el
            # libro oficial y escribir en ellas fallaría o pisaría otra; se dice cuáles faltan.
            raise PitError(f'{r.get("codigo")}: hacen falta las hojas {[h["a"] for h in r["hojas_a_copiar"]]} (una por '
                           'sistema eléctrico) y el libro de la entrega aún no las crea; sin ellas no se escribe')
        insertar += [{'hoja': i['hoja'], 'fila': int(i['fila']), 'filas': int(i['filas'])} for i in sitios]
        for c in r.get('celdas') or ():
            if c['valor'] in (None, ''):
                vaciar.append(c['celda'])
                huecos.append(c['id'])
            else:
                escribir.append({'celda': c['celda'], 'valor': c['valor']})
    return {'modelo': str(Path(modelo).resolve()), 'destino': str(Path(destino).resolve()),
            'borrar_hojas': [], 'sin_imagenes': [], 'insertar_filas': insertar, 'vaciar': vaciar,
            'escribir': escribir, 'formulas': [], 'imagenes': fotos, 'ancho_imagen': 420.0,
            'huecos': list(dict.fromkeys(huecos))}


def escribir_libro_de_cuadros(celdas: Sequence[Mapping[str, Any]], config: Mapping[str, Any], *, destino: Path,
                              ejecutar: Callable[[str], Any] | None = None) -> tuple[Path | None, str]:
    """Los cuadros en el libro modelo, con Excel; sin Excel, el motivo (el expediente JSON sigue valiendo)."""
    return rellenar_con_excel(plan_de_cuadros(celdas, config, destino=destino), ejecutar=ejecutar)
