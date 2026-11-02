"""Etiquetas del maestro sobre textos reales del operador, fuera de git (spec 068).

El currículo decía «ejecuta el flujo de potencia» y el operador escribe «has el flujo de...»: el
candidato se quedó en el 51 % de la prueba sellada. Los textos reales están en el almacén local, nunca
aquí (P9), y este módulo solo los lee, los valida y dice cuándo un texto es la misma frase que otro.

Son plata de un solo maestro: enseñan al alumno, pero no son órdenes humanas ni cuentan para 027:RF-19.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import random
import re
from typing import Any

from .sinteticos import CORTESIAS, Ejemplo, normalizar
from .tareas import TAREAS

CALIDAD = 'silver_maestro_texto_real'
#: Por debajo el maestro duda: la etiqueta se ofrece al operador, pero no enseña al modelo.
CONFIANZA_MINIMA = .7
NINGUNA = 'ninguna'
SUBCARPETA = 'maestro_real'

_SIN_PALABRA = re.compile(r'[^\w]+')
_PALABRA = re.compile(r'\w+')

#: Sustituciones vistas en los mensajes reales del operador (2026-11-02): palabras que se le cruzan.
_FRECUENTES: dict[str, tuple[str, ...]] = {
    'haz': ('has', 'as', 'hax'), 'hazme': ('hasme', 'asme'), 'hay': ('ay',), 'hacer': ('ahcer', 'hcer'), 'hace': ('ahce',),
    'que': ('q', 'qe', 'qeu', 'uqe'), 'por': ('pro',), 'para': ('pra', 'apra', 'par'), 'los': ('lso',), 'las': ('lsa', 'als'),
    'del': ('dle',), 'con': ('cno',), 'una': ('uan',), 'como': ('cmo', 'coo', 'comso'), 'de': ('d',), 'el': ('le',), 'la': ('al', 'lña'),
    'ahora': ('aora', 'ahroa', 'ahoar', 'haora'), 'archivo': ('arachivo', 'archvio', 'arhivo', 'achivo', 'arcahivo'),
    'electrico': ('eletrico', 'electirco', 'elecrtico'), 'alimentador': ('alimnetador', 'aliemntador', 'alimentadro', 'aliematdor', 'alimetador'),
    'alimentadores': ('aliematdores', 'alimnetadores', 'alimentadroes', 'alimetadores', 'aleimatdores'),
    'calibra': ('calbra', 'caliba', 'caliabra'), 'calibracion': ('calibarcion', 'caliabracion', 'calaibracion'),
    'recalibra': ('recalibar',), 'proyecto': ('proyeto', 'poryecto', 'proyecot', 'poeyecto', 'proeycto'), 'proyectos': ('proyectso', 'poryectos', 'proyetos'),
    'sistema': ('sitema', 'sistem', 'sisitema', 'sisetam', 'sietam', 'siteam', 'sisteam'),
    'informe': ('infrome', 'infome', 'inforem', 'infmore', 'infmroe', 'indorme'), 'mediciones': ('mediones', 'medicones', 'medioens'),
    'corre': ('core', 'corer'), 'carga': ('crga', 'cagra', 'carag', 'caraga', 'crag'), 'cargas': ('crgas', 'cagras', 'carags', 'caragas'), 'nueva': ('neuva',),
    'nuevas': ('neuvas',), 'nuevo': ('neuvo',), 'nuevos': ('neuvso',), 'revisa': ('reivsa', 'revsia', 'ervsia'), 'entrena': ('entren', 'enterna', 'enetrna'),
    'ejecuta': ('ejecta', 'ejcuta', 'ejecuat', 'jecuta'), 'estudio': ('etudio', 'esutdio', 'estusio'), 'estudios': ('etudios', 'esutdios', 'estusios', 'estsuio'),
    'flujo': ('fluj', 'fljo'), 'digsilent': ('disgsilent', 'digslient', 'digsielnt', 'digsielent', 'disgsielent'), 'todos': ('tdos', 'tdoso'), 'todo': ('tdo',),
    'verifica': ('verfica', 'verfiac', 'verifca', 'vericar'), 'corrige': ('corrije', 'corrgi', 'corrgie', 'corije'), 'completa': ('comeplta', 'compelta', 'comeplat'),
    'actualiza': ('actauliza', 'actuliza', 'cataulizar'), 'implementa': ('implemeta', 'impmeneta', 'impemeta'), 'tension': ('tesnion', 'tesion', 'tensiosn', 'tsnsion'),
    'conversion': ('conevrsion', 'coenversion', 'covnersion'), 'esta': ('esat', 'etsa'), 'este': ('eset', 'etse'), 'datos': ('datso', 'adtso', 'dtos'),
    'obras': ('obars', 'orbas'), 'bancos': ('bancso',), 'transferencia': ('tranferencia', 'transfrencia', 'tranfrencia'), 'seccion': ('secion', 'seccino', 'secieon'),
    'prueba': ('preuba', 'prueab'), 'pruebas': ('preubas', 'prubeas', 'peubas'), 'avance': ('avnace',), 'optimiza': ('optmiza',), 'optimizacion': ('optmizacion',),
    'factibilidad': ('factbilidad', 'factibilida'), 'caso': ('cso', 'acso'), 'simula': ('simaula',), 'gemelo': ('egemelo',),
}
_VECINAS = {'a': 'sq', 'e': 'wr', 'i': 'uo', 'o': 'ip', 'u': 'yi', 's': 'ad', 'r': 'et', 'n': 'bm', 't': 'ry', 'l': 'kñ',
            'c': 'xs', 'z': 's', 'v': 'b', 'b': 'v'}


def clave_texto(texto: str) -> str:
    """El texto sin tildes, mayúsculas, signos ni espacios de más: lo mismo para el modelo."""
    return ' '.join(_SIN_PALABRA.sub(' ', normalizar(str(texto))).split())


def firma_familia(texto: str, datos: Sequence) -> str:
    """La frase con sus datos enmascarados y sin cortesías: «convierte AB101» es «convierte CD202»."""
    trozos, cursor = [], 0
    for a, b, tipo in sorted((tuple(d) for d in datos), key=lambda d: d[0]):
        trozos += [clave_texto(texto[cursor:a]), f'dato{tipo}']
        cursor = b
    trozos.append(clave_texto(texto[cursor:]))
    firma = ' '.join(t for t in trozos if t)
    # Las cortesías las pone el generador al azar: sin quitarlas, una familia pasaría por otra.
    for cortesia in CORTESIAS:
        if firma.startswith(cortesia + ' '):
            return firma[len(cortesia) + 1:]
    return firma


def datos_a_spans(texto: str, datos: Mapping[str, Sequence[str]]) -> list[list]:
    """Cada valor con su posición en el texto; un valor que no está es un dato inventado."""
    base, spans = normalizar(texto), []
    for tipo, valores in sorted((datos or {}).items()):
        for valor in valores:
            buscado, desde = normalizar(str(valor)), 0
            while True:
                i = base.find(buscado, desde) if buscado else -1
                if i < 0:
                    raise ValueError(f'dato ausente del texto: {tipo}')
                if not any(a < i + len(buscado) and i < b for a, b, _t in spans):
                    break
                desde = i + 1
            spans.append([i, i + len(buscado), tipo])
    return sorted(spans)


def leer_etiquetas(raiz: Path | str | None = None, *, minimo: float = CONFIANZA_MINIMA) -> tuple[list[dict[str, Any]], Counter]:
    """Las etiquetas válidas con ``confianza >= minimo`` y la cuenta de lo que se apartó, y por qué."""
    if raiz is None:
        from . import almacen
        raiz = almacen.raiz()
    ruta = Path(raiz) / SUBCARPETA / 'etiquetas.jsonl'
    filas, cuenta = [], Counter()
    if not ruta.is_file():
        return filas, cuenta
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        if not linea.strip():
            continue
        try:
            f = json.loads(linea)
            texto, tarea, confianza = str(f['texto']), f['tarea'], float(f['confianza'])
        except (ValueError, KeyError, TypeError):
            cuenta['ilegibles'] += 1
            continue
        if f.get('quality') != CALIDAD:
            # Este fichero es plata: un «gold_human» aquí sería confirmar en nombre del operador.
            cuenta['rechazadas_calidad'] += 1
        elif tarea == NINGUNA:
            cuenta['ninguna'] += 1
        elif tarea not in TAREAS:
            cuenta['rechazadas_tarea'] += 1
        else:
            admitidos = {d.tipo for d in TAREAS[tarea].datos}
            datos = f.get('datos') or {}
            try:
                if not set(datos) <= admitidos:
                    raise ValueError('tipo ajeno a la tarea')
                spans = datos_a_spans(texto, datos)
            except (ValueError, TypeError, AttributeError):
                cuenta['rechazadas_datos'] += 1
                continue
            if confianza < CONFIANZA_MINIMA:
                cuenta['dudosas'] += 1
            if confianza >= minimo:
                cuenta['validas'] += confianza >= CONFIANZA_MINIMA
                filas.append({**f, 'texto': texto, 'spans': spans})
    return filas, cuenta


def _errata(palabra: str, rnd: random.Random, prob: float) -> str:
    if rnd.random() >= prob:
        return palabra
    frecuentes = _FRECUENTES.get(normalizar(palabra))
    if frecuentes and rnd.random() < .7:
        return rnd.choice(frecuentes)
    if len(palabra) < 4:
        return palabra
    i = rnd.randrange(1, len(palabra) - 1)
    op = rnd.randrange(4)
    if op == 0:
        return palabra[:i] + palabra[i + 1:]                                   # se come una letra
    if op == 1:
        return palabra[:i] + palabra[i] + palabra[i:]                          # dobla una tecla
    if op == 2 and i + 1 < len(palabra):
        return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]     # cruza dos letras
    vecina = _VECINAS.get(palabra[i].lower())
    return palabra[:i] + rnd.choice(vecina) + palabra[i + 1:] if vecina else palabra[:i] + palabra[i + 1:]


def _corrimientos(trozo: str, rnd: random.Random, prob: float) -> str:
    """El espacio corrido de los mensajes reales: «d etension», «s epeuden», «loq ue»."""
    letras = list(trozo)
    for i in range(1, len(letras) - 1):
        if letras[i] == ' ' and letras[i - 1] != ' ' and letras[i + 1] != ' ' and rnd.random() < prob:
            letras[i], letras[i + 1] = letras[i + 1], letras[i]
    return ''.join(letras)


def con_erratas(ejemplo: Ejemplo, rnd: random.Random, prob: float = .3) -> Ejemplo:
    """Una variante con las erratas del operador; los datos quedan intactos, en su nuevo sitio.

    No se toca ``sinteticos._ruido``: de él sale la huella de las 200 órdenes fijas (027:RF-65).
    """
    def alterado(trozo: str) -> str:
        return _corrimientos(_PALABRA.sub(lambda m: _errata(m.group(), rnd, prob), trozo), rnd, prob / 6)

    texto, datos, cursor = '', [], 0
    for a, b, tipo in sorted(ejemplo.datos, key=lambda d: d[0]):
        texto += alterado(ejemplo.texto[cursor:a])
        datos.append((len(texto), len(texto) + b - a, tipo))
        texto += ejemplo.texto[a:b]
        cursor = b
    texto += alterado(ejemplo.texto[cursor:])
    return Ejemplo(texto, ejemplo.tarea, datos)
