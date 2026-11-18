"""Las etiquetas de los datos de una orden y su decisión por palabra (026:RF-2, 069:RF-1).

Las comparten el Transformer letra a letra y el modelo sobre codificador preentrenado; aquí, para que uno no
tenga que importar al otro.
"""
from __future__ import annotations

from collections.abc import Callable
import re

from .sinteticos import normalizar
from .tareas import TIPOS_DATO

LARGO_MAX = 192
ETIQUETAS = ('O',) + tuple(f'{p}-{t}' for t in TIPOS_DATO for p in ('B', 'I'))

#: Palabras de unión que el etiquetado arrastra a los bordes de un dato («pisco con»,
#: «en IN111 del proyecto», 2026-10-24); dentro de una lista («IN111 y TA225») se quedan.
_UNION = {'de', 'del', 'en', 'con', 'para', 'la', 'el', 'los', 'las', 'y', 'a', 'al', 'proyecto',
          'alimentador', 'alimentadores', 'sistema', 'sed', 'desde', 'entre', 'por'}


def recortar_union(valor: str) -> str:
    palabras = valor.strip(' ,.;:¿?¡!"\'').split()
    while palabras and normalizar(palabras[0]).strip(',.') in _UNION:
        palabras.pop(0)
    while palabras and normalizar(palabras[-1]).strip(',.') in _UNION:
        palabras.pop()
    return ' '.join(palabras).strip(' ,.;:¿?¡!"\'')


def marcar_datos(texto: str, probabilidades, recortar: Callable[[str], str] = recortar_union) -> dict[str, list[dict]]:
    """Los datos, decididos por palabra: cada palabra toma el tipo que votan sus caracteres.

    Los datos son palabras enteras (IN111, «CA101 13», «julio de 2026»). Etiquetando
    carácter a carácter salían trozos como «C» y «101» de CA101 (F1 de 0,13 en la prueba
    fija, 2026-10-24); con el voto por palabra, el dato sale entero o no sale.
    """
    palabras = []
    for m in re.finditer(r'\S+', texto[:LARGO_MAX]):
        a, b = m.span()
        votos = probabilidades[a:b].sum(0)
        k = int(votos.argmax())
        nombre = ETIQUETAS[k]
        tipo = None if nombre == 'O' else nombre[2:]
        if tipo is not None:
            # El voto del tipo junta B e I; la confianza es la media de lo que no es O.
            idx = [i for i, e in enumerate(ETIQUETAS) if e[2:] == tipo]
            por_tipo = float(probabilidades[a:b][:, idx].sum(-1).mean())
            if por_tipo < 0.5:
                tipo = None
        palabras.append((a, b, tipo, float(1 - probabilidades[a:b][:, 0].mean()), nombre.startswith('B-')))
    out: dict[str, list[dict]] = {}
    actual = None
    for a, b, tipo, conf, empieza in palabras + [(len(texto), len(texto), None, 0.0, False)]:
        if actual is not None and (tipo != actual[2] or empieza):
            valor = recortar(texto[actual[0]:actual[1]])
            if valor:
                ini = texto.find(valor, actual[0])
                out.setdefault(actual[2], []).append({'valor': valor, 'inicio': ini, 'fin': ini + len(valor),
                                                      'confianza': sum(actual[3]) / len(actual[3])})
            actual = None
        if tipo is None:
            continue
        if actual is None:
            actual = [a, b, tipo, [conf]]
        else:
            actual[1] = b
            actual[3].append(conf)
    return out
