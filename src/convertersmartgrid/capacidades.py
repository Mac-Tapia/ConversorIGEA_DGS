"""Equipos del archivo original frente a los de DIgSILENT (spec 015, RF-6, RF-7, RF-32 a RF-34).

La aceptación de CA101 del 2026-10-13 contaba transformadores pero no miraba su potencia,
y el operador tuvo que cambiar cuatro tipos a mano para que el flujo convergiera. Aquí se
lee, del DGS que se importó, lo que el modelo debe tener: la capacidad de cada
transformador y de cada línea, y el grupo de conexión y la tensión de baja de cada
transformador. Se compara por nombre con lo que la aceptación lee en DIgSILENT.

Qué se hace con cada diferencia lo fija la spec: sin capacidad, el «Caso base» no queda
verificado (RF-6, RF-10); una capacidad distinta es una corrección del operador y solo se
avisa (RF-11); el grupo o la tensión de baja distintos se corrigen con el valor del
archivo (RF-34), porque el archivo ya dice cuál es y ningún flujo debe pararse por eso.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .util import finite_or_none as _num

#: Tolerancia relativa al comparar capacidades y tensiones leídas de DIgSILENT con las del
#: DGS: PowerFactory relee en coma flotante simple (0,73 vuelve como 0,7300000190734863).
TOLERANCIA = 1e-4


@dataclass(frozen=True)
class Trafo:
    """Un ``ElmTr2``: capacidad total (MVA), tensión de baja (kV) y grupo (alta, baja, desfase)."""

    mva: float | None
    kv_baja: float | None
    grupo: tuple[Any, Any, Any]
    unidades: int = 1


@dataclass(frozen=True)
class Linea:
    """Un ``ElmLne``: corriente admisible total (kA)."""

    ka: float | None
    unidades: int = 1


def _entero(valor: Any, defecto: int = 1) -> int:
    x = _num(valor)
    return int(x) if x is not None and x > 0 else defecto


def _filas(tablas: dict, nombre: str) -> list[dict]:
    return list((tablas.get(nombre) or {}).get('rows_dict') or [])


def grupo_canonico(alta: Any, baja: Any, desfase: Any) -> tuple[Any, Any, Any]:
    """``('D', 'YN', 5)``: letras en mayúscula y desfase entero, o ``None`` si falta."""
    def letra(x):
        s = str(x or '').strip().upper()
        return s or None
    d = _num(desfase)
    return letra(alta), letra(baja), (int(round(d)) if d is not None else None)


def equipos_de_dgs(tablas: dict) -> dict[str, dict]:
    """``{'transformadores': {nombre: Trafo}, 'lineas': {nombre: Linea}}`` del DGS."""
    tipos_tr = {f['FID']: f for f in _filas(tablas, 'TypTr2')}
    tipos_ln = {f['FID']: f for f in _filas(tablas, 'TypLne')}
    trafos: dict[str, Trafo] = {}
    for f in _filas(tablas, 'ElmTr2'):
        tipo = tipos_tr.get(f.get('typ_id')) or {}
        u = _entero(f.get('ntnum'))
        strn = _num(tipo.get('strn'))
        trafos[f.get('loc_name', '')] = Trafo(
            strn * u if strn is not None else None, _num(tipo.get('utrn_l')),
            grupo_canonico(tipo.get('tr2cn_h'), tipo.get('tr2cn_l'), tipo.get('nt2ag')), u)
    lineas: dict[str, Linea] = {}
    for f in _filas(tablas, 'ElmLne'):
        tipo = tipos_ln.get(f.get('typ_id')) or {}
        u = _entero(f.get('nlnum'))
        ka = _corriente(tipo, f.get('inAir'))
        lineas[f.get('loc_name', '')] = Linea(ka * u if ka is not None else None, u)
    return {'transformadores': trafos, 'lineas': lineas}


def _corriente(tipo: dict, en_aire: Any) -> float | None:
    """``InomAir`` para una línea al aire si está definido; si no, ``sline``.

    En los DGS de CA101 ``InomAir`` viene a 0: la corriente es la de ``sline``.
    """
    aire = _num(tipo.get('InomAir'))
    if _entero(en_aire, 0) == 1 and aire:
        return aire
    return _num(tipo.get('sline'))


def _distinto(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is not b
    return not math.isclose(a, b, rel_tol=TOLERANCIA, abs_tol=1e-9)


def _sin_capacidad(valor: float | None) -> bool:
    return valor is None or valor <= 0


def comparar_equipos(archivo: dict[str, dict], leidos: dict[str, dict]) -> dict[str, list]:
    """Clasifica cada diferencia entre el archivo original y lo leído en DIgSILENT.

    - ``sin_capacidad``: transformador o línea sin capacidad en DIgSILENT (RF-6, bloquea).
    - ``capacidad_distinta``: capacidad definida pero distinta de la del archivo (RF-11,
      aviso).
    - ``a_corregir``: transformador con grupo o tensión de baja distintos de los del
      archivo, o sin ellos (RF-32 a RF-34).
    - ``no_en_archivo``: equipo que el archivo no trae; no hay con qué compararlo.
    """
    out: dict[str, list] = {'sin_capacidad': [], 'capacidad_distinta': [],
                            'a_corregir': [], 'no_en_archivo': []}
    esperados_tr = archivo.get('transformadores') or {}
    for nombre, tr in sorted((leidos.get('transformadores') or {}).items()):
        if _sin_capacidad(tr.mva):
            out['sin_capacidad'].append({'clase': 'ElmTr2', 'nombre': nombre})
        ref = esperados_tr.get(nombre)
        if ref is None:
            out['no_en_archivo'].append({'clase': 'ElmTr2', 'nombre': nombre})
            continue
        if not _sin_capacidad(tr.mva) and _distinto(tr.mva, ref.mva):
            out['capacidad_distinta'].append({'clase': 'ElmTr2', 'nombre': nombre,
                                              'magnitud': 'MVA', 'digsilent': tr.mva,
                                              'archivo': ref.mva})
        correccion: dict[str, Any] = {}
        if ref.kv_baja is not None and _distinto(tr.kv_baja, ref.kv_baja):
            correccion['kv_baja'] = {'digsilent': tr.kv_baja, 'archivo': ref.kv_baja}
        if any(x is not None for x in ref.grupo) and tuple(tr.grupo) != tuple(ref.grupo):
            correccion['grupo'] = {'digsilent': tuple(tr.grupo), 'archivo': tuple(ref.grupo)}
        if correccion:
            out['a_corregir'].append({'nombre': nombre, **correccion})
    esperadas_ln = archivo.get('lineas') or {}
    for nombre, ln in sorted((leidos.get('lineas') or {}).items()):
        if _sin_capacidad(ln.ka):
            out['sin_capacidad'].append({'clase': 'ElmLne', 'nombre': nombre})
            continue
        ref = esperadas_ln.get(nombre)
        if ref is None:
            out['no_en_archivo'].append({'clase': 'ElmLne', 'nombre': nombre})
        elif _distinto(ln.ka, ref.ka):
            out['capacidad_distinta'].append({'clase': 'ElmLne', 'nombre': nombre,
                                              'magnitud': 'kA', 'digsilent': ln.ka,
                                              'archivo': ref.ka})
    return out
