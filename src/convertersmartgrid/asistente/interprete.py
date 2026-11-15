"""Intérprete híbrido de órdenes (spec 026, RF-2 a RF-4).

Primero el Transformer propio; si su confianza no llega al umbral, el modelo local de
Ollama; si ninguno llega, no se adivina: se devuelve sin tarea para preguntar al operador
(RF-4). Unas reglas fijas completan lo que tiene forma inequívoca (un periodo, una ruta),
sin depender de ningún modelo.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .maestro_real import NINGUNA
from .sinteticos import MESES, normalizar
from .contratos_salida import validar_orden
from .tareas import TAREAS, tarea_del_tipo_de_analisis

UMBRAL_TRANSFORMER = 0.85
UMBRAL_OLLAMA = 0.6
#: 075:RF-37: hasta qué lugar de las opciones del modelo se le cree a «esto no es una orden» cuando duda.
PUESTO_CHARLA = 2

_NUMEROS = {'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6, 'siete': 7, 'ocho': 8,
            'nueve': 9, 'diez': 10, 'quince': 15, 'veinte': 20, 'treinta': 30, 'cuarenta': 40, 'cincuenta': 50}


@dataclass
class Interpretacion:
    texto: str
    tarea: str | None
    confianza: float
    modelo: str
    datos: dict[str, list[dict]] = field(default_factory=dict)
    alternativas: list[tuple[str, float]] = field(default_factory=list)
    consultados: list[str] = field(default_factory=list)
    razon: str = ''


def periodo_de(texto: str) -> str | None:
    """«2026-07», «julio de 2026», «julio 2026», «el año 2025» o «2025» → AAAA-MM o AAAA."""
    t = normalizar(texto)
    m = re.search(r'\b(20\d{2})[-/](0?[1-9]|1[0-2])\b', t)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}'
    for i, mes in enumerate(MESES):
        m = re.search(rf'\b{mes}\s+(?:del?\s+)?(20\d{{2}})\b', t)
        if m:
            return f'{m.group(1)}-{i + 1:02d}'
    m = re.search(r'(?<![\w-])(20\d{2})(?![\w-])', t)
    return m.group(1) if m else None


def numero_de(texto: str) -> int | None:
    t = normalizar(texto)
    m = re.search(r'\b(\d{1,4})\b', t)
    if m:
        return int(m.group(1))
    for palabra, n in _NUMEROS.items():
        if re.search(rf'\b{palabra}\b', t):
            return n
    return None


_RUTA = re.compile(r'"([^"]+)"|([A-Za-z]:[\\/][^"]*?\.(?:xlsx|xls|csv|txt|mdb|bak)\b|[A-Za-z]:[\\/][^\s"]+)')


def ruta_de(texto: str) -> str | None:
    m = _RUTA.search(texto)
    return (m.group(1) or m.group(2)) if m else None


_NUM = r'(-?\d+(?:[.,]\d+)?)'
#: 070:RF-29: la ubicación de una carga nueva. «x 374207.83 y 8476517» daba la SED «374207.83» y la duda «8476517 no es
#: un alimentador», y «coordenadas 374207.83 8476517» no se leía (auditor, 2026-11-14, F3): son una ubicación.
_UTM = re.compile(r'\bx\s*[:=]?\s*' + _NUM + r'[\s,;]+(?:e\s+)?y\s*[:=]?\s*' + _NUM
                  + r'|\bcoordenadas?(?:\s+utm)?\s*[:=]?\s*(?:x\s*[:=]?\s*)?' + _NUM + r'[\s,;]+(?:e\s+)?(?:y\s*[:=]?\s*)?' + _NUM)
_LATLON = re.compile(r'\blat\w*\s*[:=]?\s*(-?\d+[.,]\d+)[\s,;]+lon\w*\s*[:=]?\s*(-?\d+[.,]\d+)')


def ubicacion_de(texto: str) -> dict[str, str] | None:
    """Las coordenadas que da la orden, tal como se escriben: ``{'x', 'y'}`` en UTM o ``{'lat', 'lon'}``."""
    t = normalizar(texto)
    if (m := _UTM.search(t)) is not None:
        x, y = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(4))
        return {'x': x, 'y': y}
    if (m := _LATLON.search(t)) is not None:
        return {'lat': m.group(1), 'lon': m.group(2)}
    return None


def _por_reglas(texto: str) -> dict[str, list[dict]]:
    datos: dict[str, list[dict]] = {}
    if (r := ruta_de(texto)) is not None:
        datos['ruta'] = [{'valor': r, 'confianza': 1.0, 'origen': 'regla'}]
    sin_ruta = texto.replace(r, ' ') if r else texto
    if (p := periodo_de(sin_ruta)) is not None:
        datos['periodo'] = [{'valor': p, 'confianza': 1.0, 'origen': 'regla'}]
    return datos


def _prediccion_valida(prediccion) -> bool:
    """047:RF-1: valida también predicciones de modelos locales cargados de disco."""
    try:
        # «ninguna» es una respuesta válida del modelo: para el contrato, una orden sin tarea (069:RF-15).
        tarea = None if prediccion['tarea'] == NINGUNA else prediccion['tarea']
        validar_orden({'tarea': tarea, 'confianza': prediccion['confianza'],
                       'datos': {t: [d['valor'] for d in valores]
                                 for t, valores in prediccion['datos'].items()}})
        return True
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


_PREGUNTA = re.compile(r'^\W*(como|que|por que|porque|cual|cuales|cuando|donde|explica|explicame)\b')


def _por_frase_literal(texto: str, transformer: Any) -> str | None:
    """La tarea que el modelo en uso no conoce y la orden nombra (067:RF-36). Sin esto, las tareas
    nuevas no se alcanzarían hasta que un candidato pase las puertas: el modelo en uso entendía
    «haz la escalera de …» como ``obras``, que aplica otra cosa. Una pregunta sobre ella no es una orden."""
    t = normalizar(texto)
    pregunta = '?' in texto or bool(_PREGUNTA.search(t))
    if not pregunta and (por_tipo := tarea_del_tipo_de_analisis(t)) is not None:
        # 072:RF-29: el corto o el largo plazo lo nombra la orden, sepa o no el modelo en uso qué tarea es.
        return por_tipo
    primera = next((tarea.nombre for tarea in TAREAS.values() if (not pregunta or tarea.literal_en_pregunta)
                    and any(re.search(f, t) for f in tarea.frases_literales)), None)
    # Solo la primera del catálogo: «si entra una carga … de punta a punta» es la evaluación de esa carga, que el
    # modelo conoce, y no el alimentador de punta a punta que viene después (auditor, 2026-11-14, F4). La que el
    # modelo conoce la decide él, y su frase solo si él duda (``interpretar``, F9).
    if primera == 'pregunta' and transformer is not None:
        # La forma de una pregunta no le quita la orden al modelo (070:RF-39): «por qué no converge el flujo» sigue
        # siendo suya. Su frase solo decide cuando el modelo duda (F7, F9), que es cuando se llama sin modelo.
        return None
    return primera if primera not in set(getattr(transformer, 'tareas', None) or ()) else None


#: 077:RF-70: con qué empieza una pregunta; es la lista de ``_PREGUNTA`` y las demás interrogativas.
_INTERROGATIVA = re.compile(r'^\W*(?:y\s+)?(como|que|por que|porque|cual|cuales|cuando|donde|quien|quienes|'
                            r'cuant[oa]s?|explica|explicame)\b')
#: 077:RF-70: con signos y sin interrogativa, solo cuenta si empieza por un verbo de consulta, nunca por una
#: petición («¿puedes convertir …?», «¿convierte …?»): una lista de lo que pregunta yerra por el lado de no desviar.
_CONSULTA = re.compile(r'^\W*(?:y\s+)?(hay|existe|existen|es|son|esta|estan|sirve|sirven|tiene|tienen|se)\b')
#: 077:RF-71: una ruta con separador que acaba en extensión; «kV/km», «y/o» o una fecha no la tienen.
_FICHERO = re.compile(r'(?:[\w.\-{}~]+[\\/])+[\w\-][\w.\-]*\.[A-Za-z][A-Za-z0-9]{0,5}(?![\w\\/])')
_SKILL = re.compile(r'\bskill\.md\b', re.IGNORECASE)
_SUBE = re.compile(r'\.\.[\\/]')
_API = re.compile(r'(?<![\w.\-])/api/[\w{}\-]')
_URL = re.compile(r'\w+://\S+')


def pregunta_al_proyecto(texto: str) -> bool:
    """Si la orden es una pregunta que nombra un fichero del árbol o una ruta de la API (077:RF-69 a RF-73).

    En la web real, el 2026-11-06, el Transformer provisional mandó «¿cómo se prueba la web según
    .claude/skills/…/SKILL.md?» a ``simular_calibracion`` (2 %) y «¿qué hay en ../../Windows/win.ini?» a ``episodios``:
    la lectura y el rechazo de RF-26 y RF-27 solo actúan dentro de ``pregunta``. Es forma, no modelo."""
    t = normalizar(texto)
    if not (_INTERROGATIVA.search(t) or (('?' in t or '¿' in t) and _CONSULTA.search(t))):
        return False
    # 077:RF-72: «¿cuál es la máxima de D:/…/libro.xlsx?» es una orden que se pide preguntando.
    if any(re.search(f, t) for tarea in TAREAS.values() if tarea.literal_en_pregunta and tarea.nombre != 'pregunta'
           for f in tarea.frases_literales):
        return False
    sin_url = _URL.sub(' ', texto)                       # una dirección web no es un fichero del árbol
    return any(p.search(sin_url) for p in (_FICHERO, _SKILL, _SUBE, _API))


def charla_cerca(modelo: Any, texto: str, confianza: float | None = None) -> bool:
    """Si el modelo tiene «ninguna» entre sus primeras opciones; el que no tiene esa clase no opina (075:RF-41).

    079:RF-55, RF-56: cuántas opciones son, y bajo qué confianza tampoco se consulta, lo trae el modelo; sin ello, la regla de la 075.
    """
    puesto = getattr(modelo, 'puesto_ninguna', None)
    lugar = puesto(texto) if callable(puesto) else None
    if type(lugar) is not int:
        return False
    tope, piso = getattr(modelo, 'puesto_charla', None), getattr(modelo, 'piso_charla', None)
    if lugar <= (tope if type(tope) is int else PUESTO_CHARLA):
        return True
    return type(piso) is float and type(confianza) is float and confianza < piso


def interpretar(texto: str, *, transformer: Any = None, ollama: Any = None,
                umbral: float = UMBRAL_TRANSFORMER, umbral_ollama: float = UMBRAL_OLLAMA,
                contexto: Sequence[str] = (), umbrales: Mapping[str, float] | None = None) -> Interpretacion:
    """La tarea y los datos de la orden, con quién la entendió (RF-7)."""
    texto = texto.strip()
    if pregunta_al_proyecto(texto):
        # 077:RF-69, RF-74: antes que ningún modelo y sin su umbral; sin trozo `texto`, la pregunta es el mensaje entero (069:RF-30).
        return Interpretacion(texto, 'pregunta', 1.0, 'forma', {}, [],
                              ['forma de pregunta: nombra un fichero del árbol o una ruta de la API'])
    consultados = []
    previa = None
    if transformer is not None:
        previa = transformer.predecir(texto)
        valida = _prediccion_valida(previa)
        version = previa.get('version') if isinstance(previa, Mapping) else None
        consultados.append(f"Transformer {version or ''}".strip() +
                           ('' if valida else ' (salida inválida)'))
        if not valida:
            previa = None
    if (literal := _por_frase_literal(texto, transformer)) is not None:
        # Los datos los sigue marcando el modelo si los ve; el plan los contrasta o los toma del texto.
        return _con_reglas(Interpretacion(texto, literal, 1.0, 'catalogo', dict((previa or {}).get('datos') or {}), [],
                                          [*consultados, f'frase literal de «{literal}»']))
    if previa is not None and previa['tarea'] == NINGUNA:
        # 069:RF-15: el modelo dice que esto no es una orden. La charla pasaba el umbral y proponía
        # tareas (62,6 % de los mensajes reales, 2026-11-02): ni se adivina ni se le pregunta a otro.
        return Interpretacion(texto, None, previa['confianza'], 'ninguno', {}, list(previa.get('alternativas') or []),
                              consultados, 'no parece una orden del catálogo')
    if transformer is not None:
        # 069:RF-26: el umbral calibrado del modelo, si lo trae, en vez del fijo; 027:RF-38: el de su tarea, si lo hay.
        calibrado = getattr(transformer, 'umbral', None)
        minimo = calibrado if type(calibrado) is float and umbral == UMBRAL_TRANSFORMER else umbral
        exigida = None if previa is None else (umbrales or {}).get(previa['tarea'], minimo)
        if (previa is not None and not getattr(ollama, 'revisar_transformer', False)
                and previa['confianza'] >= exigida):
            return _con_reglas(Interpretacion(texto, previa['tarea'], previa['confianza'], 'transformer',
                                              previa['datos'], previa.get('alternativas') or [], consultados))
        if previa is not None and (literal := _por_frase_literal(texto, None)) is not None:
            # 067:RF-36: con el modelo por debajo de su umbral, la frase literal del catálogo también decide en las tareas
            # que el modelo conoce. «cuántas sed tiene el QX511» se entendía sin el Transformer y no con él, que se
            # quedaba en 0,80 (auditor, 2026-11-14, F9). Con el modelo seguro, manda el modelo.
            return _con_reglas(Interpretacion(texto, literal, 1.0, 'catalogo', dict(previa.get('datos') or {}), [],
                                              [*consultados, f'frase literal de «{literal}»']))
        if (ollama is not None and previa is not None and previa['confianza'] < exigida
                and charla_cerca(transformer, texto, previa['confianza'])):
            # 075:RF-37: «muchas gracias» a secas cayó bajo el umbral y Ollama impuso `estado` con confianza 1,0
            # (web, 2026-11-02). El modelo ya dudaba de que fuera una orden: se le pregunta al operador, no a otro modelo.
            return Interpretacion(texto, None, previa['confianza'], 'ninguno', {},
                                  [(previa['tarea'], previa['confianza']), *(previa.get('alternativas') or [])],
                                  [*consultados, 'sin Ollama: el modelo duda de que sea una orden'],
                                  'puede que no sea una orden del catálogo')
    if ollama is not None:
        # 027:RF-37, RF-39: con órdenes parecidas y notas de fallos, si las hay.
        r = ollama.interpretar(texto, contexto=list(contexto)) if contexto else ollama.interpretar(texto)
        consultados.append(f'Ollama {ollama.modelo}' + ('' if r is not None else ' (no respondió)'))
        if r is not None and _prediccion_valida(r) and r.get('tarea') and r['confianza'] >= umbral_ollama:
            return _con_reglas(Interpretacion(texto, r['tarea'], r['confianza'], r['modelo'], r['datos'],
                                              [], consultados, r.get('razon') or ''))
    alternativas = []
    if previa is not None:
        alternativas = [(previa['tarea'], previa['confianza'])] + list(previa.get('alternativas') or [])
    return Interpretacion(texto, None, previa['confianza'] if previa else 0.0, 'ninguno', {}, alternativas,
                          consultados)


def _con_reglas(i: Interpretacion) -> Interpretacion:
    """Lo que tiene forma inequívoca manda sobre lo que marcó el modelo."""
    for tipo, valores in _por_reglas(i.texto).items():
        i.datos[tipo] = valores
    return i
