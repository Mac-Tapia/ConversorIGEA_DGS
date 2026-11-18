"""Qué fases le llegan a cada tramo y SED desde la cabecera (054:RF-9).

Sin dependencias: la usan el modelo común (TXT y MDB) y la fuente VNR-GIS, y el modelo no se puede importar desde
esa fuente sin cerrar un ciclo.
"""
from __future__ import annotations

from collections import deque


def fases_desde_la_cabecera(tramos, cabecera: str) -> tuple[dict[str, str], dict[str, str]]:
    """Las fases que le llegan a cada tramo y a cada nodo desde la cabecera (054:RF-9).

    ``tramos`` son ``(id, desde, hasta, letras)``. Devuelve ``(tramos cambiados, letras por nodo)``. El hijo con fases
    que no le llegan toma las del padre; el tramo que tiene más fases que su padre las devuelve aguas arriba hasta uno
    que ya las tenga. Un nodo sin camino a la cabecera no aparece: nadie puede decir qué le llega.
    """
    vecinos: dict[str, list[tuple[str, str]]] = {}
    fases: dict[str, str] = {}
    for tramo, desde, hasta, letras in tramos:
        fases[tramo] = letras
        vecinos.setdefault(desde, []).append((tramo, hasta))
        vecinos.setdefault(hasta, []).append((tramo, desde))
    originales = dict(fases)
    entrada: dict[str, tuple[str, str]] = {}          # nodo -> (nodo de arriba, tramo)
    orden: list[tuple[str, str]] = []
    vistos, cola = {cabecera}, deque([cabecera])
    while cola:
        n = cola.popleft()
        for tramo, otro in sorted(vecinos.get(n, ())):
            if otro not in vistos:
                vistos.add(otro)
                entrada[otro] = (n, tramo)
                orden.append((n, tramo))
                cola.append(otro)

    def en_nodo(n: str) -> str:
        return fases[entrada[n][1]] if n in entrada else 'ABC'

    for arriba, tramo in orden:
        propias, llegan = fases[tramo], en_nodo(arriba)
        if set(propias) <= set(llegan):
            continue
        if len(propias) > len(llegan):
            letras, n = set(propias), arriba
            while n in entrada and not letras <= set(en_nodo(n)):
                n, de_arriba = entrada[n]
                fases[de_arriba] = ''.join(f for f in 'ABC' if f in set(fases[de_arriba]) | letras)
        else:
            comunes = [f for f in llegan if f in propias]
            fases[tramo] = ''.join(sorted((comunes + [f for f in llegan if f not in comunes])[:len(propias)]))
    return ({t: f for t, f in fases.items() if f != originales[t]},
            {n: en_nodo(n) for n in vistos})


def fases_de_carga_que_llegan(propias: str, llegan: str) -> str:
    """Las fases de una SED según lo que llega a su nodo: no sube fases aguas arriba, el tramo manda (054:RF-9)."""
    return propias if set(propias) <= set(llegan) else llegan[:len(propias)]
