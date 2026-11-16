"""107 T19 (delta20, orden del auditor 28): las celdas sombreadas de los formatos de la Norma Tarifas (RCD
217-2013-OS/CD), que la plantilla manda dejar vacías («(3) Las celdas sombreadas no deben ser llenadas», F-302).

El lector común (calamine) no da los rellenos de un .xls: se leen con xlrd (``formatting_info``) de los libros
OFICIALES del rar (``leer_rellenos``), y se cotejan con el mapa derivado de la carpeta de fuentes (``sombreadas/``:
``GRISES_217.json`` y ``COLORES_217_mapa.json`` del apoyo (cc), frentes «z6_cotejo_resto» y «z10_colores_217», con su
SHA256SUMS). Si no casan, el generador se para (``cotejar``).
Cada formato lleva ``no_llenar``: sus celdas por fila de la plantilla (``{"22": ["H", "I", …]}``, como ``celdas``),
su motivo (la nota del formato que lo manda, si la tiene; si no, «celda sombreada en el libro oficial»), el relleno y
la procedencia. Una celda sombreada con texto en la transcripción, o un mapa de otro libro, paran el generador.
El F-101 lleva como motivo el literal de su nota (2) (A25), por orden del auditor 28. Los rellenos de color que no son
gris (cabeceras de F-305, F-306, F-401, F-510 y F-522) van como observación (``colores``), SIN efecto en el llenado:
ninguna nota del formato ni de la norma dice que no se llenen.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fuentes import comprobar

#: sha256 de ``GRISES_217.json`` (apoyo (cc), frente «z6_cotejo_resto», en su SHA256SUMS.txt).
GRISES_SHA = '731601968d1b4b4ccef8eba0a32ad46f5d571f2e63a524bd8d6c44c976fc143b'
MOTIVO_GENERAL = 'celda sombreada en el libro oficial'
_CELDA = re.compile(r'^([A-Z]+)(\d+)$')
_RELLENO = {'(192, 192, 192)': 'gris 192', '(0, 0, 0)': 'negro'}
#: Formatos cuya nota dice por qué no se llenan sus celdas sombreadas: el motivo es su texto literal (orden de 28).
MOTIVO_POR_NOTA = {'F-101': 'A25'}
EFECTO_COLORES = ('ninguno: ninguna nota del formato ni de la norma (RCD 217-2013) dice que no se llenen; observación '
                  '(apoyo (cc), frente «z10_colores_217»; regla del auditor 28)')


class MapaSombreadasError(SystemExit):
    """El mapa de celdas sombreadas no casa con la transcripción: el generador se para."""


def cargar_grises(ruta: Path | str, sha: str = GRISES_SHA) -> dict:
    """El mapa por hoja, después de comprobar su sha256 (``fuentes.comprobar``)."""
    return json.loads(comprobar(ruta, sha).read_text(encoding='utf-8'))


def _orden(letra: str) -> tuple[int, str]:
    return len(letra), letra


def _letra(j: int) -> str:
    s, j = '', j + 1
    while j:
        j, r = divmod(j - 1, 26)
        s = chr(65 + r) + s
    return s


def leer_rellenos(libro: Path | str) -> dict:
    """Por hoja del libro oficial: sus celdas sombreadas (gris o negro), sus rellenos y sus celdas de color (que no es
    gris ni blanco), leídos con xlrd (``formatting_info``). Solo lee: nunca abre el libro con Excel ni lo escribe."""
    import xlrd
    wb = xlrd.open_workbook(str(libro), formatting_info=True)
    salida = {}
    for sh in wb.sheets():
        grises, rgb, colores = [], set(), {}
        for i in range(sh.nrows):
            for j in range(sh.ncols):
                fondo = wb.xf_list[sh.cell_xf_index(i, j)].background
                if fondo.fill_pattern == 0:
                    continue
                color = wb.colour_map.get(fondo.pattern_colour_index)
                if not color:
                    continue
                celda = f'{_letra(j)}{i + 1}'
                if color[0] == color[1] == color[2] and color[0] < 240:
                    grises.append(celda)
                    rgb.add(str(tuple(color)))
                elif tuple(color) != (255, 255, 255):
                    colores[celda] = str(tuple(color))
        salida[sh.name] = {'hoja': sh.name, 'libro': Path(libro).name, 'celdas_grises': grises,
                           'rgb': sorted(rgb), 'colores': colores}
    return salida


def cotejar(leidos: dict, grises: dict, colores: dict) -> None:
    """Los rellenos leídos de los libros oficiales tienen que ser los del mapa derivado, hoja por hoja (grises y
    colores); si no, el generador se para con la hoja y la diferencia."""
    derivado_colores = colores.get('formatos', colores)
    for hoja in sorted(set(leidos) | set(grises) | set(derivado_colores)):
        a = set((leidos.get(hoja) or {}).get('celdas_grises') or ())
        b = set((grises.get(hoja) or {}).get('celdas_grises') or ())
        if a != b:
            raise MapaSombreadasError(f'{hoja}: las celdas sombreadas del libro oficial no son las del mapa derivado '
                                      f'(solo en el libro {sorted(a - b)[:8]}, solo en el mapa {sorted(b - a)[:8]})')
        c = set((leidos.get(hoja) or {}).get('colores') or ())
        d = set((derivado_colores.get(hoja) or {}).get('celdas_color') or ())
        if c != d:
            raise MapaSombreadasError(f'{hoja}: las celdas de color del libro oficial no son las del mapa derivado '
                                      f'(solo en el libro {sorted(c - d)[:8]}, solo en el mapa {sorted(d - c)[:8]})')


def colores_del_formato(entrada: dict | None) -> dict | None:
    """La observación de los rellenos de color de un formato, por fila; ``None`` si no tiene."""
    colores = (entrada or {}).get('colores') or {}
    if not colores:
        return None
    filas: dict[str, list[str]] = {}
    for celda in colores:
        m = _CELDA.match(celda)
        filas.setdefault(m.group(2), []).append(m.group(1))
    return {'filas': {f: sorted(ls, key=_orden) for f, ls in filas.items()}, 'celdas': len(colores),
            'rellenos': sorted(set(colores.values())), 'efecto': EFECTO_COLORES}


def no_llenar(codigo: str, libro: str, literales: list[dict], entrada: dict | None, procedencia: str) -> dict:
    """``no_llenar`` del formato ``codigo`` (hoja del ``libro``) desde su ``entrada`` del mapa de rellenos.

    ``literales``: las filas transcritas (``{'fila', 'celdas'}``). Sin entrada para la hoja, error: no se supone que
    un formato no tiene sombreadas."""
    if entrada is None:
        raise MapaSombreadasError(f'{libro}:{codigo}: el mapa de celdas sombreadas no trae la hoja')
    if entrada.get('hoja') != codigo or Path(str(entrada.get('libro'))).name != libro:
        raise MapaSombreadasError(f'{libro}:{codigo}: el mapa de celdas sombreadas es de otra hoja o de otro libro '
                                  f'({entrada.get("libro")}:{entrada.get("hoja")})')
    texto = {(f['fila'], letra): v for f in literales for letra, v in f['celdas'].items()}
    filas: dict[str, list[str]] = {}
    for celda in entrada.get('celdas_grises') or ():
        m = _CELDA.match(celda)
        if m is None:
            raise MapaSombreadasError(f'{libro}:{codigo}: celda sombreada mal escrita en el mapa: {celda!r}')
        letra, fila = m.group(1), int(m.group(2))
        if (fila, letra) in texto:
            raise MapaSombreadasError(f'{libro}:{codigo}!{celda}: sombreada y con texto en la transcripción '
                                      f'({texto[(fila, letra)]!r}); una celda que no se llena no es un rótulo')
        filas.setdefault(str(fila), []).append(letra)
    salida: dict = {'filas': {f: sorted(set(ls), key=_orden) for f, ls in filas.items()},
                    'celdas': sum(len(set(ls)) for ls in filas.values()), 'procedencia': procedencia}
    if not filas:
        return salida
    nota = next(((f['fila'], letra, v) for f in literales for letra, v in f['celdas'].items()
                 if 'sombread' in v.lower()), None)
    if codigo in MOTIVO_POR_NOTA:
        m = _CELDA.match(MOTIVO_POR_NOTA[codigo])
        literal = texto.get((int(m.group(2)), m.group(1)))
        if not literal:
            raise MapaSombreadasError(f'{libro}:{codigo}!{MOTIVO_POR_NOTA[codigo]}: la nota que da el motivo de sus '
                                      'celdas sombreadas no está en la transcripción')
        nota = (int(m.group(2)), m.group(1), literal)
    if nota is not None:
        salida['motivo'] = nota[2]
        salida['nota'] = f'{nota[1]}{nota[0]}'
    else:
        salida['motivo'] = MOTIVO_GENERAL
    salida['relleno'] = sorted(_RELLENO.get(str(r), f'color {r}') for r in entrada.get('rgb') or ())
    return salida
