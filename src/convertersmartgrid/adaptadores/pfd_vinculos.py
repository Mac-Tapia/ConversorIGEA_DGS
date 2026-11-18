"""Vínculos del proyecto de un ``.pfd`` con los ficheros de su expediente, por su contenido (spec 004, RF-109, RF-110).

El diagnóstico del ``.pfd`` (``tools/pfd_diagnostico.py``) da los nombres del proyecto: el proyecto, sus casos, sus
escenarios, sus variaciones y sus alimentadores; las SET las añade quien llama (el perfil o la red). Un fichero del
expediente (informe, libro, memoria) se vincula al proyecto solo si su **contenido** nombra alguno de ellos:

- se recorre la carpeta con el inventario y la extracción del dataset del PIDE (``pide_dataset``: PDF, Word, libros
  .xlsx/.xls con el lector común, CSV, texto…), sin abrir nada con Office;
- cada nombre se busca como palabra entera, sin distinguir mayúsculas ni tildes;
- cada vínculo lleva su evidencia: el fichero (con su huella), la hoja o la página, y el texto que lo nombra;
- el nombre del fichero no cuenta: un fichero que se llama como un caso y no lo nombra dentro no se vincula. Un fichero
  que no se puede leer (otro ``.pfd``, un plano en DWG) se dice aparte con su motivo, nunca se supone vinculado.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .pide_dataset import extraer_archivo, inventariar

__all__ = ['TIPOS', 'nombres_del_diagnostico', 'vincular']

TIPOS = ('proyecto', 'caso', 'escenario', 'variacion', 'alimentador', 'set')
#: Un nombre más corto casaría con cualquier texto (siglas, números de página): se dice y no se busca.
LARGO_MINIMO = 2
CONTEXTO = 60


def _plano(texto: str) -> str:
    """Minúsculas y sin tildes, carácter a carácter: las posiciones del texto plano son las del original."""
    return ''.join(unicodedata.normalize('NFD', c)[0] for c in str(texto)).lower()


def nombres_del_diagnostico(diagnostico: Mapping[str, Any], sets: Iterable[str] = ()) -> dict[str, set[str]]:
    """Los nombres del proyecto que vale buscar, desde un proyecto del JSON del diagnóstico (``informe['proyectos']``
    o el ``diag`` de ``diagnosticar``) y las SET que dé quien llama."""
    red = diagnostico.get('red') or {}
    alimentadores = set(red.get('alimentadores') or ())
    for r in red.get('redes') or ():
        alimentadores.update(r.get('alimentadores') or ())
    alimentadores.update(red.get('alimentadores_sin_red') or ())
    salida = {
        'proyecto': {diagnostico['proyecto']} if diagnostico.get('proyecto') else set(),
        'caso': {c['caso'] for c in diagnostico.get('casos') or () if c.get('caso')},
        'escenario': {e['escenario'] for e in diagnostico.get('escenarios') or () if e.get('escenario')},
        'variacion': {v['variacion'] for v in diagnostico.get('variaciones') or () if v.get('variacion')},
        'alimentador': {a for a in alimentadores if a},
        'set': {s for s in sets if s},
    }
    return {t: {str(n).strip() for n in v if str(n).strip()} for t, v in salida.items()}


def vincular(nombres: Mapping[str, Iterable[str]], carpeta: Path | str, *, empresa: str = '',
             contexto: int = CONTEXTO) -> dict[str, Any]:
    """Los vínculos de ``carpeta`` con los ``nombres`` (tipo → nombres), cada uno con su evidencia; los ficheros sin
    lectura con su motivo; y los nombres que ningún fichero nombra."""
    desconocidos = sorted(set(nombres) - set(TIPOS))
    if desconocidos:
        raise ValueError(f'tipos de nombre desconocidos: {", ".join(desconocidos)} (se admiten {", ".join(TIPOS)})')
    buscados: list[tuple[str, str, re.Pattern[str]]] = []
    cortos: list[str] = []
    for tipo in TIPOS:
        for nombre in sorted(set(nombres.get(tipo) or ())):
            if len(nombre) < LARGO_MINIMO:
                cortos.append(f'{tipo} «{nombre}»: demasiado corto para casarlo por contenido')
                continue
            buscados.append((tipo, nombre, re.compile(rf'(?<![0-9a-z]){re.escape(_plano(nombre))}(?![0-9a-z])')))
    raiz = Path(carpeta)
    vinculos: list[dict[str, Any]] = []
    ficheros: list[dict[str, Any]] = []
    for archivo in inventariar(raiz, empresa, None):
        extraido = extraer_archivo(archivo, raiz)
        ficha = {'fichero': archivo.relative_path, 'sha256': archivo.sha256, 'estado': extraido.status, 'vinculos': 0}
        if extraido.status != 'ok':
            ficha['motivo'] = '; '.join(extraido.warnings) or extraido.status
            ficheros.append(ficha)
            continue
        vistos: set[tuple[str, str, str, Any]] = set()
        for fragmento in extraido.fragments:
            texto = str(fragmento.get('text') or '')
            plano = _plano(texto)
            for tipo, nombre, patron in buscados:
                m = patron.search(plano)
                clave = (tipo, nombre, str(fragmento.get('location')), fragmento.get('part'))
                if m is None or clave in vistos:
                    continue
                vistos.add(clave)
                ini, fin = max(0, m.start() - contexto), min(len(texto), m.end() + contexto)
                vinculos.append({'tipo': tipo, 'nombre': nombre, 'fichero': archivo.relative_path,
                                 'sha256': archivo.sha256, 'ubicacion': fragmento.get('location'),
                                 'parte': fragmento.get('part'), 'texto': texto[ini:fin].strip()})
                ficha['vinculos'] += 1
        ficheros.append(ficha)
    hallados = {(v['tipo'], v['nombre']) for v in vinculos}
    sin_vinculo = [f'{t} «{n}»' for t, n, _p in buscados if (t, n) not in hallados]
    return {'vinculos': vinculos, 'ficheros': ficheros, 'sin_vinculo': sin_vinculo, 'avisos': cortos}
