"""Ejemplos de órdenes para entrenar el Transformer antes de que el operador dé ninguna
(spec 026, RF-21).

Cada plantilla del catálogo se expande con sus variantes ``[a|b]`` y sus datos ``{tipo}``
rellenos con los nombres reales del espacio (alimentadores de la fuente, proyectos de
DIgSILENT, sistemas de la estructura). Sin nombres reales se inventan códigos con la forma
habitual (letras y dígitos): el modelo aprende la forma, no una empresa (P13).

Las órdenes reales llegan con erratas («complata la imepmenatycion», 2026-10-24): el ruido
cambia, borra, duplica o intercambia letras de las palabras de la plantilla, nunca de los
datos, para que las etiquetas de cada dato sigan en su sitio.
"""
from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .tareas import TAREAS

#: Subtipos de estudio por defecto (RF-16); el perfil los puede ampliar.
SUBTIPOS_ESTUDIO = ('alimentación de carga nueva', 'mejora de tensión', 'refuerzo de red',
                    'migración de tensión', 'transferencia', 'PIDE')

MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
         'octubre', 'noviembre', 'diciembre')

_TEXTOS = ('calibra el conversor una barra sin medidor', 'se convierten los trafomix',
           'funciona la escalera de obras', 'se elige el modelo de carga del gemelo',
           'el oráculo decide si un modelo pasa las puertas', 'se arma el dgs por sistema',
           'se verifica el caso base', 'se reconocen los txt por su contenido',
           'optimización evolutiva de bancos de condensadores', 'flujo de carga en python',
           'redes neuronales de grafos para sistemas eléctricos', 'estimación de estado con pinn',
           'informe de una carga nueva de 500 kW', 'mejora de tensión con bancos en la SED',
           'migración del alimentador a 22,9 kV', 'transferencia de carga entre alimentadores',
           'calibra una barra sin medidor', 'calcula las pérdidas del alimentador',
           # Con nombres de la red: una búsqueda con un alimentador se confundía con calibrar un
           # sistema (2026-10-24); se entiende como búsqueda y el filtro la bloquea. El nombre lo
           # pone el vocabulario del espacio o se inventa (P13).
           'caída de tensión en {a}', 'pérdidas de {a}', 'flujo de carga de {a} en python')

_PREFIJOS = ('', '', '', 'por favor ', 'oye ', 'quiero que ', 'necesito que ', 'puedes ', 'ahora ')


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, con la misma longitud: las posiciones de los datos no se mueven."""
    out = []
    for c in texto:
        base = unicodedata.normalize('NFD', c)[0].lower()
        out.append(base if len(base) == 1 else c)
    return ''.join(out)


@dataclass
class Ejemplo:
    texto: str
    tarea: str
    datos: list[tuple[int, int, str]] = field(default_factory=list)   # (inicio, fin, tipo)

    def valor(self, tipo: str) -> list[str]:
        return [self.texto[a:b] for a, b, t in self.datos if t == tipo]


def _codigo(rnd: random.Random) -> str:
    letras = ''.join(rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(rnd.choice((2, 2, 3))))
    return f'{letras}{rnd.randint(100, 299)}'


def _inventados(rnd: random.Random, tipo: str) -> str:
    if tipo == 'alimentadores':
        return _codigo(rnd)
    if tipo == 'proyecto':
        return rnd.choice((f'{_codigo(rnd)} {rnd.randint(1, 20)}', f'{_codigo(rnd)}_{_codigo(rnd)}',
                           f'2026{rnd.randint(1000, 1231)}-{rnd.randint(100000, 235959)}_IGEA_{_codigo(rnd)}'))
    if tipo == 'sistema':
        return rnd.choice(('Norte', 'Sur', 'Centro', 'Costa', 'Valle', 'Sierra', 'Bahía', 'Llanura')) + \
            rnd.choice(('', '', ' Alto', ' Bajo'))
    if tipo == 'sed':
        return f'{rnd.choice(("SE", "E", "S"))}{rnd.randint(10000, 99999)}'
    if tipo == 'ruta':
        return rnd.choice(('D:\\datos\\cargas nuevas.xlsx', 'C:/proyectos/demanda', 'D:/entregas/2026/cargas.xlsx',
                           'referencia\\demanda'))
    return ''


def _valor(rnd: random.Random, tipo: str, vocab: Mapping[str, Sequence[str]]) -> str:
    """Un valor del tipo, real si el vocabulario lo trae, con las formas en que se escribe."""
    def uno(t: str) -> str:
        reales = list(vocab.get(t) or [])
        v = rnd.choice(reales) if reales and rnd.random() < 0.8 else _inventados(rnd, t)
        return v.lower() if rnd.random() < 0.25 else v

    if tipo == 'alimentadores':
        if rnd.random() < 0.08:
            return rnd.choice(('todos', 'todos los alimentadores'))
        n = rnd.choice((1, 1, 1, 2, 2, 3))
        nombres = [uno('alimentadores') for _ in range(n)]
        if n == 1:
            return nombres[0]
        return ', '.join(nombres[:-1]) + rnd.choice((' y ', ', ')) + nombres[-1]
    if tipo == 'periodo':
        anio = rnd.choice((2024, 2025, 2026, 2027))
        mes = rnd.randint(1, 12)
        return rnd.choice((f'{anio}-{mes:02d}', f'{MESES[mes - 1]} de {anio}', f'{MESES[mes - 1]} {anio}',
                           f'{anio}', f'el año {anio}'))
    if tipo == 'numero':
        return rnd.choice((str(rnd.randint(2, 60)), 'diez', 'veinte', 'cinco'))
    if tipo == 'subtipo':
        return rnd.choice(list(vocab.get('subtipo') or SUBTIPOS_ESTUDIO)).lower()
    if tipo == 'texto':
        return rnd.choice(list(vocab.get('texto') or _TEXTOS)).replace('{a}', uno('alimentadores'))
    return uno(tipo)


def _ruido(rnd: random.Random, palabra: str, prob: float) -> str:
    if len(palabra) < 4 or rnd.random() >= prob:
        return palabra
    i = rnd.randrange(1, len(palabra) - 2)
    op = rnd.randrange(4)
    if op == 0:
        return palabra[:i] + palabra[i + 1:]                                   # borra
    if op == 1:
        return palabra[:i] + palabra[i] + palabra[i:]                          # duplica
    if op == 2:
        return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]     # intercambia
    return palabra[:i] + rnd.choice('aeiounsrtl') + palabra[i + 1:]            # cambia


_TROZO = re.compile(r'\[([^\]]*)\]|\{(\w+)\}|([^\[{]+)')


def expandir(plantilla: str, tarea: str, rnd: random.Random, vocab: Mapping[str, Sequence[str]],
             ruido: float = 0.0) -> Ejemplo:
    """Una frase de la plantilla con sus variantes, sus datos y su ruido."""
    texto, datos = rnd.choice(_PREFIJOS), []
    for coincidencia in _TROZO.finditer(plantilla):
        alt, tipo, literal = coincidencia.groups()
        if tipo:
            v = _valor(rnd, tipo, vocab)
            if v:
                datos.append((len(texto), len(texto) + len(v), tipo))
                texto += v
            continue
        trozo = rnd.choice(alt.split('|')) if alt is not None else literal
        texto += ' '.join(_ruido(rnd, p, ruido) for p in trozo.split(' '))
    # Una variante vacía deja dos espacios seguidos: se quitan moviendo las posiciones.
    limpio, nuevo_de = [], {}
    for i, c in enumerate(texto):
        if c == ' ' and (not limpio or limpio[-1] == ' '):
            continue
        nuevo_de[i] = len(limpio)
        limpio.append(c)
    final = ''.join(limpio).rstrip()
    fuera = []
    for a, b, t in datos:
        na = nuevo_de.get(a)
        nb = nuevo_de.get(b - 1)
        if na is not None and nb is not None:
            fuera.append((na, nb + 1, t))
    return Ejemplo(final, tarea, [(a, b, t) for a, b, t in fuera if 0 <= a < b <= len(final)])


def generar(vocab: Mapping[str, Sequence[str]] | None = None, *, por_tarea: int = 150, semilla: int = 0,
            ruido: float = 0.12) -> list[Ejemplo]:
    """``por_tarea`` frases de cada tarea, deterministas con la semilla."""
    rnd = random.Random(semilla)
    vocab = vocab or {}
    out = []
    for nombre in sorted(TAREAS):
        t = TAREAS[nombre]
        for _ in range(por_tarea):
            out.append(expandir(rnd.choice(t.plantillas), nombre, rnd, vocab, ruido))
    rnd.shuffle(out)
    return out
