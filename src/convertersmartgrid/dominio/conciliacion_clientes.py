"""Qué clientes son de un alimentador, conciliando las fuentes, y las cadenas de renumeración (105:RF-34 a RF-37).

Una sola fuente no basta: el libro de suministros dice el radial, el resumen de cada libro mensual de clientes dice su
alimentador y su SED, y la red convertida dice en qué alimentador está esa SED. Cada cliente queda con su veredicto. Nada
se asigna por parecido de nombre: solo por el código, con sus renumeraciones explícitas. Una renumeración que no está en
el libro de suministros (un código que desaparece y otro que aparece con el mismo CL o la misma SED) se propone y no se
aplica.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np

from .meses_copiados import mes_de_registro
from .numeros_medidos import clave_codigo


def clave_cliente(valor: Any) -> str:
    """El código de un cliente comparable entre fuentes (105:RF-35).

    Además de lo que ya iguala ``clave_codigo`` (ceros a la izquierda, espacios, número o texto), un «123000045.0»
    escrito como texto por Excel es el 123000045: sin esto quedaba en «1230000450».
    """
    if isinstance(valor, str) and re.fullmatch(r'\s*\d+\.0+\s*', valor):
        valor = valor.strip().split('.')[0]
    return clave_codigo(valor)


def cadenas_de_renumeracion(pares: Iterable[tuple[str, str]]) -> tuple[dict[str, str], list[str]]:
    """``{clave de cualquier código de la cadena: código final}`` y los avisos (105:RF-35).

    Sigue anterior → actual también encadenado (A → B y B → C dan A → C), y une los dos sentidos: un libro que trae el
    código nuevo y otro el antiguo caen en el mismo cliente. Una cadena que se bifurca o que vuelve sobre sí misma se
    dice, y se resuelve siempre igual: por el menor de sus códigos finales.
    """
    siguiente: dict[str, set[str]] = {}
    texto: dict[str, str] = {}
    for anterior, actual in pares:
        a, b = clave_cliente(anterior), clave_cliente(actual)
        if not a or not b:
            continue
        texto.setdefault(a, str(anterior).strip())
        texto.setdefault(b, str(actual).strip())
        if a != b:
            siguiente.setdefault(a, set()).add(b)
    # Componentes de los dos sentidos: todo lo enlazado es el mismo cliente.
    padre = {c: c for c in texto}

    def raiz(c: str) -> str:
        while padre[c] != c:
            padre[c] = padre[padre[c]]
            c = padre[c]
        return c

    for a, bs in siguiente.items():
        for b in bs:
            ra, rb = raiz(a), raiz(b)
            if ra != rb:
                padre[max(ra, rb)] = min(ra, rb)
    grupos: dict[str, list[str]] = {}
    for c in texto:
        grupos.setdefault(raiz(c), []).append(c)
    canon: dict[str, str] = {}
    avisos: list[str] = []
    for miembros in grupos.values():
        finales = sorted(c for c in miembros if not siguiente.get(c))
        if len(miembros) == 1:
            canon[miembros[0]] = texto[miembros[0]]
            continue
        if not finales:
            avisos.append('renumeración en ciclo: ' + ', '.join(sorted(texto[c] for c in miembros))
                          + f'; se usa {texto[min(miembros)]}')
            finales = [min(miembros)]
        elif len(finales) > 1:
            avisos.append('renumeración con varios códigos actuales: ' + ', '.join(texto[c] for c in finales)
                          + f'; se usa {texto[finales[0]]}')
        for c in miembros:
            canon[c] = texto[finales[0]]
    return canon, avisos


def veredicto(alimentador: str, sed: str, fuentes: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]:
    """El veredicto de un cliente con lo que dice cada fuente (105:RF-34).

    ``fuentes``: ``{nombre: {'alimentador': str | set | None, 'sed': str | None}}``; ``None`` si la fuente no lo trae.
    ``confirmado`` cuando dos o más dicen su alimentador y ninguna dice otro; ``discrepa`` si alguna dice otro
    alimentador u otra SED; ``una_fuente`` si solo una lo sabe.
    """
    ref_a, ref_s = clave_codigo(alimentador), clave_codigo(sed)
    acuerdan, difieren = [], []
    for nombre, f in fuentes.items():
        if not f:
            continue
        valor = f.get('alimentador')
        valores = {valor} if isinstance(valor, str) else set(valor or ())
        valores = {v for v in valores if v}
        if valores:
            if ref_a in {clave_codigo(v) for v in valores}:
                acuerdan.append(nombre)
            else:
                difieren.append(f"{nombre} dice {' o '.join(sorted(valores))}")
        s = f.get('sed')
        if s and ref_s and clave_codigo(s) != ref_s:
            difieren.append(f'{nombre} da la SED {s}')
    if difieren:
        estado = 'discrepa'
        texto = f'{alimentador} ({", ".join(acuerdan) or "ninguna fuente"}); ' + '; '.join(difieren)
    elif len(acuerdan) >= 2:
        estado, texto = 'confirmado', f'confirmado en {len(acuerdan)} fuentes: {", ".join(acuerdan)}'
    else:
        estado, texto = 'una_fuente', f'solo en una fuente: {", ".join(acuerdan) or "ninguna"}'
    return {'estado': estado, 'fuentes': len(acuerdan), 'acuerdan': acuerdan, 'texto': texto}


def posibles_renumeraciones(presencia: Mapping[str, Mapping[str, Mapping[str, str]]],
                            relevantes: set[str]) -> list[dict[str, str]]:
    """Códigos que desaparecen un mes y otro que aparece ese mismo mes con el mismo CL o la misma SED (105:RF-36).

    ``presencia``: ``{mes: {clave: {'codigo', 'cl', 'sed'}}}`` de los libros de clientes; ``relevantes``: las claves de
    los clientes de los alimentadores elegidos. Solo se propone: aplicarla es decisión de quien mantiene el libro de
    suministros.
    """
    meses = sorted(presencia)
    salida: list[dict[str, str]] = []
    for previo, mes in zip(meses, meses[1:]):
        antes, ahora = presencia[previo], presencia[mes]
        idos = [k for k in antes if k not in ahora]
        nuevos = [k for k in ahora if k not in antes]
        for k in sorted(idos):
            for n in sorted(nuevos):
                if k not in relevantes and n not in relevantes:
                    continue
                for campo, etiqueta in (('cl', 'CL'), ('sed', 'SED')):
                    a, b = antes[k].get(campo, ''), ahora[n].get(campo, '')
                    if a and b and clave_cliente(a) == clave_cliente(b):
                        salida.append({'desaparece': antes[k]['codigo'], 'aparece': ahora[n]['codigo'], 'mes': mes,
                                       'por': etiqueta, 'valor': a})
                        break
    return salida


def fijos_sobre_cabecera(t_fijos: Sequence, p_fijos: Sequence[float], t_cab: Sequence, p_cab: Sequence[float],
                         margen: float) -> dict[str, Any] | None:
    """Instantes en que la suma de los fijos supera la cabecera más el margen (105:RF-38): no puede ser."""
    cab = {t: p for t, p in zip(t_cab, p_cab)}
    peor, n, por_mes = None, 0, {}
    for t, p in zip(t_fijos, p_fijos):
        c = cab.get(t)
        if c is None:
            continue
        exceso = p - c * (1 + margen)
        if exceso > 0:
            n += 1
            mes = str(mes_de_registro(np.array([t]))[0])
            por_mes[mes] = por_mes.get(mes, 0) + 1
            if peor is None or exceso > peor[2]:
                peor = (t, p, exceso, c)
    if not n:
        return None
    return {'registros': n, 'instante': peor[0], 'fijos_kw': float(peor[1]), 'cabecera_kw': float(peor[3]),
            'por_mes': dict(sorted(por_mes.items()))}
