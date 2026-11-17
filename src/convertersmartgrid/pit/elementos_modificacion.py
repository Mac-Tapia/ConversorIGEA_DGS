"""Los elementos que las modificaciones del PIT agregan, reprograman, eliminan o dan de baja, casados por huella con la
red del usuario (107 T3, PIT-ANON-ELEMENTOS).

El registro público (``config/normativa``) no guarda nombres de empresas, SET ni líneas: cada elemento lleva la huella
de su titular y de su instalación (``titular_huella``, ``instalacion_huella``; la forma de 076:RF-6 con la sal de
086:RF-33, ``dominio.huellas_terminos``) y, si su descripción nombra algo, la descripción con ``{1}``, ``{2}``… y las
huellas de esos nombres (``referencias_huella``). Los nombres en claro van en la lista local, fuera de git:

- carpeta: la variable ``CSG_NORMATIVA_ELEMENTOS`` o, sin ella, ``config/normativa_local/`` (en ``.gitignore``);
- cada fichero ``*.json``: ``{"esquema": "normativa_elementos_local_v1", "nombres": ["…", "…"]}``, solo la lista de
  nombres; la huella de cada uno se calcula al leerlo, con la misma función, así que no hay otra tabla que mantener.

Sin lista local el PIT funciona igual: casa los nombres de la red del usuario (sus SET y su titular, que se convierten
en huella al leerse) con las del registro, y muestra «elemento <huella>» donde iría el nombre.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..dominio.huellas_terminos import huella, normalizar
from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError

__all__ = ['CLAVE_ELEMENTOS', 'ESQUEMA_LISTA', 'VARIABLE_LISTA', 'carpeta_lista_local', 'elementos_de_las_modificaciones',
           'leer_lista_local', 'mostrar']

CLAVE_ELEMENTOS = 'pit.modificacion_2025_2029.elementos'
ESQUEMA_LISTA = 'normativa_elementos_local_v1'
VARIABLE_LISTA = 'CSG_NORMATIVA_ELEMENTOS'
_RAIZ = Path(__file__).resolve().parents[3]
#: Prefijos de tipo que un nombre de la red puede traer o no («SET Norte» y «Norte» son la misma instalación).
_PREFIJOS = ('set ', 'se ', 'subestacion ')


def carpeta_lista_local() -> Path:
    return Path(os.environ.get(VARIABLE_LISTA) or _RAIZ / 'config' / 'normativa_local')


def leer_lista_local(carpeta: Path | str | None = None) -> dict[str, str]:
    """Huella → nombre en claro, de la lista local (vacía si no hay carpeta). Un fichero que no tiene la forma se
    rechaza con su nombre: una lista mal escrita no debe dejar en silencio los nombres sin mostrar."""
    raiz = Path(carpeta) if carpeta is not None else carpeta_lista_local()
    nombres: dict[str, str] = {}
    if not raiz.is_dir():
        return nombres
    for ruta in sorted(raiz.glob('*.json')):
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise PitError(f'lista local {ruta.name}: no se puede leer ({exc})') from exc
        if not isinstance(datos, dict) or datos.get('esquema') != ESQUEMA_LISTA or not isinstance(datos.get('nombres'), list):
            raise PitError(f'lista local {ruta.name}: no es {ESQUEMA_LISTA} con su lista «nombres»')
        for n in datos['nombres']:
            if isinstance(n, str) and n.strip():
                nombres[huella(n)] = n.strip()
    return nombres


def mostrar(h: str | None, lista: Mapping[str, str]) -> str | None:
    """El nombre en claro si la lista local lo trae; si no, «elemento <huella>»."""
    if not h:
        return None
    return lista.get(h) or f'elemento {h}'


def _huellas_de_la_red(nombres: Iterable[str]) -> set[str]:
    """Las huellas de los nombres de la red, con y sin su prefijo de tipo («SET »)."""
    salida: set[str] = set()
    for n in nombres:
        plano = normalizar(n)
        if not plano:
            continue
        salida.add(huella(plano))
        for p in _PREFIJOS:
            if plano.startswith(p):
                salida.add(huella(plano[len(p):]))
            else:
                salida.add(huella(p + plano))
    return salida


def _descripcion(e: Mapping[str, Any], lista: Mapping[str, str]) -> str:
    texto = str(e.get('elemento') or '')
    refs = list(e.get('referencias_huella') or ())
    return re.sub(r'\{(\d+)\}', lambda m: mostrar(refs[int(m.group(1)) - 1], lista) or m.group(0)
                  if 0 < int(m.group(1)) <= len(refs) else m.group(0), texto)


def elementos_de_las_modificaciones(registro: RegistroNormativo, fecha: str | None = None, *,
                                    sets: Iterable[str] = (), titulares: Iterable[str] = (),
                                    lista: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Cada elemento de las modificaciones vigentes del PIT, con su acto, área, cuadro, año y descripción; el titular y
    la instalación como los muestra la lista local (o «elemento <huella>»); y si casa con la red del usuario
    (``sets``: los nombres de sus SET; ``titulares``: su sigla o razón social)."""
    lista = leer_lista_local() if lista is None else lista
    de_la_red, del_titular = _huellas_de_la_red(sets), {huella(t) for t in titulares if normalizar(t)}
    try:
        vigentes = registro.reglas_vigentes(CLAVE_ELEMENTOS, fecha)
    except RegistroError:
        return []
    salida = []
    for v in vigentes:
        valor = v.regla.valor if isinstance(v.regla.valor, Mapping) else {}
        for cuadro, filas in (valor.get('cuadros') or {}).items():
            for e in filas:
                if 'titular' in e or 'instalacion' in e:
                    raise PitError(f'{v.norma.acto}: un elemento trae el nombre en claro; el registro guarda su huella')
                hi, ht = e.get('instalacion_huella'), e.get('titular_huella')
                salida.append({'acto': v.norma.acto, 'area': valor.get('area'), 'informe': valor.get('informe'),
                               'cuadro': cuadro, 'anio': e.get('anio'), 'elemento': _descripcion(e, lista),
                               'titular': mostrar(ht, lista), 'instalacion': mostrar(hi, lista),
                               'instalacion_tipo': e.get('instalacion_tipo'), 'titular_huella': ht,
                               'instalacion_huella': hi,
                               'en_la_red': bool(hi and hi in de_la_red), 'del_titular': bool(ht and ht in del_titular)})
    return salida
