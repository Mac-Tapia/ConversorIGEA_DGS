"""Tasas de falla y tiempos de reposición desde el histórico de interrupciones de la empresa
(spec 012, aclaración de RF-6, RF-8, RF-9, RF-12 y RF-62, 2026-11-14).

El usuario decidió (2026-11-14) que la confiabilidad se corra con el libro que la empresa ya
tiene: su registro de interrupciones en bruto, una fila por interrupción, y no un libro
resumido con las hojas de la plantilla. El caso real es una hoja de 7 967 interrupciones de
2020 a 2026 con 41 columnas; con él, ``datos_empresa.leer_libro`` daba cero tasas y cero
tiempos y pedía las hojas «Tasas de falla» y «Tiempos», así que la confiabilidad no corría.

Lo que se hace aquí, con la referencia que lo sostiene:

- Las columnas se reconocen por su contenido y por sinónimos, nunca por el nombre que les
  pone una empresa (constitución P13): fechas y horas de inicio y fin, duración, alimentador,
  causa, programada o no, tensión y clientes afectados. Una columna que falte se anota y se
  usa lo que haya.
- Se cuentan solo las interrupciones no programadas de media tensión (1 kV < U ≤ 36 kV, el
  intervalo de MT de la IEC 60038) de los alimentadores que tiene la red del espacio, y no
  las que nacen fuera de la red de la empresa (instalaciones del cliente, otra empresa,
  déficit de generación) ni las obras (mantenimiento, ampliación). Cada filtro dice cuántas
  filas quita.
- Sostenida es la interrupción de más de 5 minutos y momentánea la de 5 o menos, el corte
  de la IEEE Std 1366 (D. Shadle, «Understanding Distribution Reliability Metrics», T&D
  World, 2021-03-10: «By IEEE definition, that is an interruption of greater than five
  minutes»). Las sostenidas dan la tasa permanente y las momentáneas la transitoria.
- La tasa es la de servicio observada: interrupciones / (exposición × años), con la
  exposición en km para líneas y cables y en unidades para los demás elementos
  (Z. Wang, J. Pan, D. Lubkeman y R. E. Brown, US 7 272 516 B2, 2007, «Failure rate
  adjustment for electric power network reliability analysis»: «the Service Time Failure
  Rate, which is defined as the ratio of the total number of outages actually observed»
  entre la exposición en milla-año). Es el estimador de máxima verosimilitud de un proceso
  de Poisson, el modelo con el que I. Dobson y S. Ekisheva (arXiv:2208.06985, 2022-2023)
  describen las salidas y reposiciones a partir de los datos de una empresa.
- El tiempo de reparación r es la media de la duración hasta la reposición total de las
  sostenidas de cada clase; donde el registro distingue la primera reposición (por
  maniobra) de la total, la primera da el tiempo de localización y maniobra.

Una clase con exposición y ninguna falla en todo el periodo queda con λ = 0, que es lo que
dice el registro (la estimación de máxima verosimilitud con cero sucesos), y se anota con su
cota superior al 95 % (``COTA_CERO_95``, la regla del tres), porque λ = 0 es optimista. Sin red
del espacio (un proyecto de DIgSILENT sin convertir) no hay exposición: se dice ``FALTA_RED``. Sin
columna de causa no se puede asignar ninguna falla a una clase: no se deriva ninguna tasa,
en vez de dar ceros que parecerían una red sin fallas.
"""

from __future__ import annotations

import datetime as _dt
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..dominio.naming import feeder_short_name

#: IEEE Std 1366: sostenida, más de 5 minutos.
MOMENTANEA_MAX_H = 5 / 60
#: Media tensión según la IEC 60038: más de 1 kV y hasta 36 kV.
MT_KV = (1.0, 36.0)
#: Filas que se miran para encontrar la de los títulos: un libro en bruto puede traer
#: un título y líneas en blanco encima.
FILAS_CABECERA = 20
#: Con cero sucesos en una exposición E·T, la cota superior exacta al 95 % de una tasa de
#: Poisson es −ln(0,05)/(E·T) ≈ 3/(E·T): la «regla del tres» de J. A. Hanley y A.
#: Lippman-Hand, «If nothing goes wrong, is everything all right? Interpreting zero
#: numerators», JAMA 249(13):1743-1745, 1983 (citada así por T. B. Newman, JAMA
#: 274(13):1013, 1995: con 0 sucesos en N, el límite superior del 95 % es «approximately 3/N»).
COTA_CERO_95 = -math.log(0.05)
#: Lo que falta, en una frase, cuando el histórico se reconoce y el espacio no tiene red
#: convertida (un proyecto de DIgSILENT sin convertir, 015:RF-70): sin esto la confiabilidad
#: pedía la hoja «Tasas de falla», que el operador no tiene porque su libro es el histórico.
#: 012:RF-87 y RF-88 (2026-11-14): la exposición se lee entonces del proyecto de DIgSILENT al
#: aplicar el libro (regla «convertido o no»), y la frase lo dice.
FALTA_RED = ('la longitud de las líneas y los cables y el número de transformadores y barras de la red, '
             'que se leen del proyecto de DIgSILENT al aplicar el libro de la empresa a sus alimentadores')
#: 012:RF-89: con la exposición ya leída, ninguna interrupción cae en una clase de elemento de un
#: alimentador de la red. No se dan tasas (RF-33: nada de ceros que parezcan una red sin fallas).
SIN_TASAS = ('las tasas de falla, que el histórico de interrupciones no da con la exposición de la red: '
             'ninguna interrupción se asigna a una clase de elemento de un alimentador de la red; revise '
             'la columna de causa y la de alimentador del histórico')
#: Origen de la exposición cuando el espacio tiene la red convertida.
ORIGEN_RED_DEL_ESPACIO = 'la red convertida del espacio'
#: 012:RF-90 (aclaración del 2026-11-14): sin un título que la nombre, la columna del alimentador es
#: la que contiene MÁS de esta fracción de los alimentadores de la red o del proyecto (cobertura,
#: mayoría estricta). No se exige que lo sean la mitad de las filas: un proyecto con 3 alimentadores
#: dentro del libro de toda la empresa tiene la mayoría de las filas de otros alimentadores.
COBERTURA_ALIMENTADOR = 0.5
#: Cardinalidad baja y columna llena: compite la columna con un valor en MÁS de esta fracción de
#: las filas (la del alimentador está en todas; una casi vacía no es ella) y con NO más valores
#: distintos que esta fracción de las filas (más es un identificador o un texto libre).
MAYORIA_ALIMENTADOR = 0.5
#: «Forma de alimentador» para el desempate: siglas seguidas de un número, la forma que
#: ``feeder_short_name`` reconoce para las siglas del perfil (022:RF-90).
_FORMA_ALIMENTADOR = re.compile(r'[A-Z]+\d')
#: 012, aclaración de RF-91 (2026-11-14, «siempre una solución»): sin cobertura, gana la ÚNICA columna
#: candidata en la que al menos esta fracción de los valores DISTINTOS tiene forma de alimentador y
#: alguno es un alimentador de la red o del proyecto.
FORMA_MINIMA = 0.8
#: Dónde están los alimentadores con que se compara la columna (012:RF-90).
DONDE_RED = 'de la red del espacio'
DONDE_PROYECTO = 'del proyecto'
#: Comienzo del aviso que dice qué columna es la del alimentador y por qué (012:RF-90).
AVISO_COLUMNA = 'Columna del alimentador'


def _norm(texto: Any) -> str:
    s = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^a-z0-9%/.]+', ' ', s.lower()).split())


# --------------------------------------------------------------------------- columnas
@dataclass(frozen=True)
class Concepto:
    clave: str
    titulo: str
    #: Cada alternativa es un grupo de raíces que tienen que estar todas en el título.
    sinonimos: tuple[tuple[str, ...], ...]
    #: Raíces que descartan la columna (la «duración final» no es la «duración»).
    excluye: tuple[str, ...] = ()
    contenido: str = 'texto'        # fecha, hora, duracion, numero, entero, texto, programada


CONCEPTOS = (
    Concepto('fecha_inicio', 'Fecha de inicio', (('fecha', 'inicio'), ('fecha', 'ini'), ('date', 'start'),
             ('start',), ('inicio',), ('fecha', 'desde')), ('fin', 'final', 'total', 'hora'), 'fecha'),
    Concepto('hora_inicio', 'Hora de inicio', (('hora', 'inicio'), ('hora', 'ini'), ('time', 'start'),
             ('hora', 'desde')), ('fin', 'final', 'total'), 'hora'),
    Concepto('fecha_fin', 'Fecha de fin', (('fecha', 'fin'), ('fecha', 'term'), ('fecha', 'repos'),
             ('date', 'end'), ('fecha', 'hasta'), ('end',)), ('total', 'hora'), 'fecha'),
    Concepto('hora_fin', 'Hora de fin', (('hora', 'fin'), ('hora', 'term'), ('hora', 'repos'), ('time', 'end'),
             ('hora', 'hasta')), ('total',), 'hora'),
    Concepto('fecha_fin_total', 'Fecha de fin total', (('fecha', 'fin', 'total'), ('fecha', 'repos', 'total'),
             ('date', 'end', 'total'),), ('hora',), 'fecha'),
    Concepto('hora_fin_total', 'Hora de fin total', (('hora', 'fin', 'total'), ('hora', 'repos', 'total'),
             ('time', 'end', 'total')), (), 'hora'),
    Concepto('duracion', 'Duración', (('durac',), ('duration',), ('tiempo', 'interrup')), ('final', 'total', 'saidi',
             'caidi'), 'duracion'),
    Concepto('duracion_total', 'Duración total', (('durac', 'final'), ('durac', 'total'), ('duration', 'total')),
             ('saidi', 'caidi'), 'duracion'),
    Concepto('alimentador', 'Alimentador', (('alimentador',), ('feeder',), ('circuito',), ('equipo', 'linea'),
             ('linea',), ('salida',)), ('usuarios', 'clientes', 'saifi', 'saidi', 'caidi', 'codigo sgd'), 'texto'),
    Concepto('causa', 'Causa', (('causa',), ('cause',), ('motivo',), ('origen',)), ('sub', 'cod'), 'texto'),
    Concepto('subcausa', 'Subcausa', (('sub', 'causa'), ('subcause',), ('sub', 'cause')), ('cod',), 'texto'),
    Concepto('programada', 'Programada o no', (('tipo',), ('programad',), ('clase',), ('naturaleza',),
             ('planned',), ('type',)), (), 'programada'),
    Concepto('tension', 'Tensión', (('tension',), ('kv',), ('voltage',), ('nivel', 'tension')), (), 'numero'),
    Concepto('clientes', 'Clientes afectados', (('usuarios', 'afectad'), ('clientes', 'afectad'),
             ('suministros', 'afectad'), ('customers',)), ('sistema', 'alimentador', 'saifi', 'eld'), 'entero'),
)
POR_CLAVE = {c.clave: c for c in CONCEPTOS}

_PROGRAMADA = ('programad', 'planificad', 'planned', 'scheduled', 'mantenimiento')
_NO_PROGRAMADA = ('imprevist', 'no programad', 'forzad', 'unplanned', 'fortuit', 'falla', 'emergencia')


def _encaja_titulo(titulo: str, c: Concepto) -> int:
    """0 si no; si sí, el número de raíces del sinónimo (el más específico gana)."""
    if any(e in titulo for e in c.excluye):
        return 0
    return max((len(s) for s in c.sinonimos if all(r in titulo for r in s)), default=0)


def _es_fecha(v) -> bool:
    return isinstance(v, (_dt.datetime, _dt.date)) and not isinstance(v, _dt.time)


def _horas(v) -> float | None:
    """Una duración en horas: ``timedelta``, ``time`` (H:M) o texto «H:M[:S]»."""
    if isinstance(v, _dt.timedelta):
        return v.total_seconds() / 3600
    if isinstance(v, _dt.time):
        return v.hour + v.minute / 60 + v.second / 3600
    if isinstance(v, str):
        m = re.fullmatch(r'\s*(\d+):(\d{1,2})(?::(\d{1,2}))?\s*', v)
        if m:
            return int(m[1]) + int(m[2]) / 60 + int(m[3] or 0) / 3600
    return None


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _es_programada(v) -> bool | None:
    t = _norm(v)
    if not t:
        return None
    if any(p in t for p in _NO_PROGRAMADA):
        return False
    if any(p in t for p in _PROGRAMADA):
        return True
    return None


def _cumple_contenido(c: Concepto, valores: Sequence[Any]) -> bool:
    """¿El contenido de la columna es el del concepto? Basta el 80 % de lo no vacío."""
    vals = [v for v in valores if v not in (None, '')]
    if not vals:
        return False
    prueba = {
        'fecha': _es_fecha,
        'hora': lambda v: isinstance(v, _dt.time) or (isinstance(v, str) and _horas(v) is not None),
        'duracion': lambda v: _horas(v) is not None or (_num(v) is not None and _num(v) >= 0),
        'numero': lambda v: _num(v) is not None,
        'entero': lambda v: _num(v) is not None,
        'texto': lambda v: str(v).strip() != '',
        'programada': lambda v: _es_programada(v) is not None,
    }[c.contenido]
    return sum(1 for v in vals if prueba(v)) >= 0.8 * len(vals)


def clave_alimentador(valor: Any) -> str:
    """El nombre de un alimentador normalizado como en la web (``feeder_short_name``), en
    mayúsculas; vacío si la celda lo está (012:RF-90)."""
    texto = '' if valor is None else str(valor).strip()
    return feeder_short_name(texto).strip().upper() if texto else ''


def _normalizador():
    """``clave_alimentador`` con memoria para una lectura: un histórico repite cada valor."""
    memo: dict[Any, str] = {}

    def clave(v):
        if v not in memo:
            memo[v] = clave_alimentador(v)
        return memo[v]
    return clave


def _filas_con_datos(filas: Sequence[Sequence[Any]]) -> list[Sequence[Any]]:
    return [f for f in filas if any(v not in (None, '') for v in f)]


def frase_columna(eleccion: Mapping[str, Any], donde: str) -> str:
    """El aviso de la columna elegida y por qué (012:RF-90)."""
    if eleccion['por'] == 'titulo':
        return f"{AVISO_COLUMNA}: «{eleccion['titulo']}», por título."
    if eleccion['por'] == 'forma':
        return (f"{AVISO_COLUMNA}: «{eleccion['titulo']}», elegida por la forma de sus valores: "
                f"{eleccion['forma']} de {eleccion['distintos']} distintos; {eleccion['coinciden']} "
                f"alimentadores {donde} con interrupciones.")
    return (f"{AVISO_COLUMNA}: «{eleccion['titulo']}», por contenido: {eleccion['coinciden']} de "
            f"{eleccion['total']} alimentadores {donde} están en ella.")


def frase_sin_columna(titulos: Sequence[Any], donde: str) -> str:
    """El error cuando ninguna columna es la del alimentador, con los títulos encontrados (012:RF-90)."""
    nombres = ', '.join(f'«{t}»' for t in titulos if t not in (None, ''))
    return ('ninguna columna del histórico es la del alimentador: ningún título lo nombra, ninguna columna '
            f'llena contiene la mayoría de los alimentadores {donde} y no hay una única con forma de '
            f'alimentador; títulos encontrados: {nombres}; renombre la columna del alimentador como '
            '«Alimentador» y vuelva a subir el libro')


def elegir_por_contenido(titulos: Sequence[Any], valores: Mapping[int, Mapping[str, int]],
                         conocidos: set[str], filas: int, firmas: Mapping[int, Any],
                         donde: str) -> tuple[dict[str, Any] | None, str]:
    """012:RF-90: la columna del alimentador por su contenido, sin título que la nombre.

    ``valores``: por columna candidata, cuántas filas tienen cada valor ya normalizado
    (``clave_alimentador``); ``conocidos``: los alimentadores de la red o del proyecto, en un
    conjunto (sin recorrer la red por columna); ``filas``: las filas con datos del histórico.

    Compiten las columnas llenas (un valor en más de ``MAYORIA_ALIMENTADOR`` de las filas) y de
    cardinalidad baja (no más valores distintos que esa fracción de las filas). Gana la que
    contiene más alimentadores de ``conocidos``, si son más de ``COBERTURA_ALIMENTADOR`` de ellos
    (aclaración de RF-90). Si empatan, gana la de más filas con forma de alimentador
    (``_FORMA_ALIMENTADOR``); si siguen empatadas y dicen lo mismo (``firmas`` iguales), vale la
    primera, y si no, no se elige.

    Sin cobertura (aclaración de RF-91): gana la única candidata en la que al menos ``FORMA_MINIMA``
    de sus valores distintos tienen forma de alimentador y alguno está en ``conocidos``; con varias
    o ninguna, el error. Devuelve la elección o ``None`` y el error en una frase."""
    total = len(conocidos)
    cobertura = {i: len(conocidos & vals.keys()) for i, vals in valores.items()
                 if vals and len(vals) <= MAYORIA_ALIMENTADOR * filas
                 and sum(vals.values()) > MAYORIA_ALIMENTADOR * filas}
    validas = {i: n for i, n in cobertura.items() if total and n > COBERTURA_ALIMENTADOR * total}
    if not validas:
        por_forma = []
        for i, n in sorted(cobertura.items()):
            distintos = len(valores[i])
            forma = sum(1 for v in valores[i] if _FORMA_ALIMENTADOR.match(v))
            if n and forma >= FORMA_MINIMA * distintos - 1e-9:
                por_forma.append({'indice': i, 'titulo': str(titulos[i]), 'por': 'forma', 'forma': forma,
                                  'distintos': distintos, 'coinciden': n, 'total': total})
        if len(por_forma) == 1:
            return por_forma[0], ''
        return None, frase_sin_columna(titulos, donde)
    mejor = max(validas.values())
    empatadas = sorted(i for i, n in validas.items() if n == mejor)
    if len(empatadas) > 1:
        forma = {i: sum(n for v, n in valores[i].items() if _FORMA_ALIMENTADOR.match(v)) for i in empatadas}
        mas = max(forma.values())
        empatadas = [i for i in empatadas if forma[i] == mas]
    if any(firmas.get(i) != firmas.get(empatadas[0]) for i in empatadas[1:]):
        nombres = ', '.join(f'«{titulos[i]}»' for i in empatadas)
        return None, (f'varias columnas del histórico pueden ser la del alimentador, cada una con {mejor} de '
                      f'{total} alimentadores {donde} y cifras distintas: {nombres}; renombre la del '
                      'alimentador como «Alimentador» y vuelva a subir el libro')
    i = empatadas[0]
    return {'indice': i, 'titulo': str(titulos[i]), 'por': 'contenido', 'coinciden': mejor, 'total': total}, ''


def reconocer_columnas(titulos: Sequence[Any], filas: Sequence[Sequence[Any]],
                       alimentadores: Sequence[str] = (), eleccion: dict | None = None) -> dict[str, int]:
    """Índice de la columna de cada concepto que se reconoce, por su título y su contenido.

    El alimentador se reconoce por su título; si ninguno lo nombra y se conoce la red, por su
    contenido (``elegir_por_contenido``, 012:RF-90). ``eleccion`` recibe cuál se eligió y por
    qué, o el error.
    """
    norm = [_norm(t) for t in titulos]
    muestra = list(filas)

    def columna(i):
        return [f[i] if i < len(f) else None for f in muestra]

    usadas: set[int] = set()
    out: dict[str, int] = {}
    # Primero los más específicos: «fecha fin total» antes que «fecha fin».
    orden = sorted(CONCEPTOS, key=lambda c: -max(len(s) for s in c.sinonimos))
    for c in orden:
        candidatos = sorted(((_encaja_titulo(t, c), i) for i, t in enumerate(norm) if i not in usadas),
                            reverse=True)
        for peso, i in candidatos:
            if peso and _cumple_contenido(c, columna(i)):
                out[c.clave] = i
                usadas.add(i)
                break
    if 'programada' not in out:
        # Por contenido solo: la columna cuyos valores son «programada» o «imprevista».
        for i in range(len(norm)):
            if i not in usadas and _cumple_contenido(POR_CLAVE['programada'], columna(i)) and \
                    len({_norm(v) for v in columna(i) if v}) <= 6:
                out['programada'] = i
                usadas.add(i)
                break
    if 'alimentador' in out:
        if eleccion is not None:
            eleccion.update(indice=out['alimentador'], titulo=str(titulos[out['alimentador']]), por='titulo')
    elif alimentadores:
        clave = _normalizador()
        datos = _filas_con_datos(muestra)
        valores, firmas = {}, {}
        for i in range(len(norm)):
            if i in usadas:
                continue
            col = tuple(clave(f[i] if i < len(f) else None) for f in datos)
            valores[i] = Counter(v for v in col if v)
            firmas[i] = col
        elegida, error = elegir_por_contenido(titulos, valores, {clave_alimentador(a) for a in alimentadores},
                                              len(datos), firmas, DONDE_RED)
        if elegida:
            out['alimentador'] = elegida['indice']
        if eleccion is not None:
            eleccion.update(elegida or {'error': error})
    return out


def es_historico(columnas: Mapping[str, int]) -> bool:
    """Un histórico de interrupciones: inicio, cómo medir la duración y dónde ocurrió."""
    duracion = 'duracion' in columnas or 'fecha_fin' in columnas or 'duracion_total' in columnas
    return 'fecha_inicio' in columnas and duracion and ('alimentador' in columnas or 'causa' in columnas)


# --------------------------------------------------------------------------- clases
#: Qué elemento falló, por las palabras de la causa. Expresiones regulares sobre el texto
#: normalizado; una causa que nombra varias clases («Falla equipo (TC, TP, interruptor,
#: seccionador y/o transformador, etc)») no decide y se mira la siguiente.
_CLAVES_CLASE = (
    ('transformador', r'\btransformador|\btransformer|\btrafo'),
    ('cable', r'\bcable|subterran|underground|\bterminacion|\bmufa'),
    ('reconectador', r'\breconectador|\brecloser'),
    ('fusible', r'\bfusible|\bfuse\b'),
    ('seccionador', r'\bseccionador|cut ?out|sectionali[sz]er|disconnector'),
    ('interruptor', r'\binterruptor|\bbreaker'),
    ('barra', r'\bbarra\b|\bbarras\b|busbar'),
    ('linea', r'\blinea|\bconductor|\bvano|\baislador|\baves?\b|\barbol|\bviento|descargas? atmosf|\brayo|'
              r'\bestructura|\bposte|\bcruceta|\bvehicul|\bcometa|\bempalme|\bretenida|\bacercamiento|'
              r'\boverhead|\btree|\bbird|\blightning|\bpole\b'),
)
#: Causas que nacen fuera de la red de la empresa u obras: no son fallas de sus elementos.
_FUERA_DE_LA_RED = (
    ('instalación del cliente', r'utilizacion|sist\.? util'),
    ('red de otra empresa', r'otras? empresas?|externa'),
    ('generación', r'generacion|eracmf'),
    ('obra o mantenimiento', r'mantenimiento|expansion|reforzamiento|maintenance'),
)


def clase_de_causa(textos: Sequence[Any]) -> str | None:
    """La clase de elemento del primer texto que nombra una sola (subcausa antes que causa)."""
    for texto in textos:
        t = _norm(texto)
        if not t:
            continue
        clases = [c for c, patron in _CLAVES_CLASE if re.search(patron, t)]
        if len(clases) == 1:
            return clases[0]
    return None


def _fuera_de_la_red(textos: Sequence[Any]) -> str | None:
    t = ' '.join(_norm(x) for x in textos if x)
    return next((motivo for motivo, patron in _FUERA_DE_LA_RED if re.search(patron, t)), None)


# --------------------------------------------------------------------------- exposición
def exposicion_de_red(red: Any) -> dict[str, dict[str, float]]:
    """Exposición de cada alimentador de la red del espacio: km de línea aérea y de cable,
    transformadores de distribución (cargas) y barras (nodos).

    Vale para cualquier fuente: usa la estructura común del dataset (secciones, configuración
    de cada tramo con su longitud en metros, cargas y nodos). Un mapa ya hecho
    ``{alimentador: {clase: exposición}}`` pasa tal cual.
    """
    if red is None:
        return {}
    if isinstance(red, Mapping):
        return {str(k).strip().upper(): dict(v) for k, v in red.items()}
    out: dict[str, dict[str, float]] = {}
    cargas = getattr(red, 'customer_loads_by_feeder', {}) or {}
    for network_id, secciones in (getattr(red, 'feeders', {}) or {}).items():
        exp = {'linea': 0.0, 'cable': 0.0, 'transformador': 0.0, 'barra': 0.0}
        nodos: set[str] = set()
        for sid in secciones:
            cfg = red.line_configurations.get(sid) or {}
            km = (_num(cfg.get('Length')) or 0.0) / 1000.0
            exp['linea' if str(cfg.get('Overhead', '1')) == '1' else 'cable'] += km
            sec = red.sections.get(sid) or {}
            nodos.update(n for n in (sec.get('FromNodeID'), sec.get('ToNodeID')) if n)
        exp['transformador'] = float(len(cargas.get(network_id, ())))
        exp['barra'] = float(len(nodos))
        nombre = feeder_short_name(network_id).strip().upper()
        previo = out.get(nombre)
        out[nombre] = {k: exp[k] + (previo or {}).get(k, 0.0) for k in exp}
    return out


# --------------------------------------------------------------------------- derivación
def _momento(fecha, hora) -> _dt.datetime | None:
    if not _es_fecha(fecha):
        return None
    base = fecha if isinstance(fecha, _dt.datetime) else _dt.datetime.combine(fecha, _dt.time())
    if isinstance(hora, _dt.time):
        return _dt.datetime.combine(base.date(), hora)
    h = _horas(hora) if isinstance(hora, str) else None
    return base + _dt.timedelta(hours=h) if h is not None else base


def _factor_horas(titulo: Any) -> float | None:
    """Horas por unidad de una duración numérica, por su título; ``None`` si no lo dice."""
    t = _norm(titulo)
    if re.search(r'\bmin', t):
        return 1 / 60
    if re.search(r'\bseg|\bsec', t):
        return 1 / 3600
    if re.search(r'\bhoras?\b|\bh\b|\bhours?\b', t) and not re.search(r'\bh m\b', t):
        return 1.0
    return None


def _duracion_h(c: Mapping[str, int], fila, ini, fecha_k, hora_k, dur_k,
                factores: Mapping[str, float | None] | None = None) -> float | None:
    """La duración declarada si la hay; si no, fin − inicio.

    Una duración numérica solo vale si su título dice la unidad (minutos, horas): un número
    suelto podría ser cualquiera de las dos y daría reparaciones sesenta veces mayores.
    """
    if dur_k in c:
        v = _celda(fila, c[dur_k])
        h = _horas(v)
        if h is None and (factores or {}).get(dur_k) and _num(v) is not None:
            h = _num(v) * factores[dur_k]
        if h is not None:
            return h
    if fecha_k in c and ini is not None:
        fin = _momento(_celda(fila, c[fecha_k]), _celda(fila, c.get(hora_k, -1)))
        if fin is not None and fin >= ini:
            return (fin - ini).total_seconds() / 3600
    return None


def _celda(fila, i):
    return fila[i] if 0 <= i < len(fila) else None


def derivar(titulos: Sequence[Any], filas: Sequence[Sequence[Any]], exposicion: Mapping[str, Mapping[str, float]],
            *, clases: Mapping[str, str], por_km: Sequence[str], tiempos_nombres: Mapping[str, str],
            hoja: str = '', primera_fila: int = 2,
            origen_exposicion: str = ORIGEN_RED_DEL_ESPACIO) -> dict[str, Any]:
    """Tasas por clase (en conjunto y por alimentador), tiempos y su procedencia.

    Las clases, las que van por km y los nombres de los tiempos los da ``datos_empresa``,
    que es quien llama: importarlos de allí cerraba un ciclo entre los dos módulos (test_capas).
    """
    CLASES, POR_KM, TIEMPOS = clases, por_km, tiempos_nombres

    exposicion = {clave_alimentador(k): v for k, v in exposicion.items()}
    eleccion: dict[str, Any] = {}
    c = reconocer_columnas(titulos, filas, tuple(exposicion), eleccion)
    clave = _normalizador()
    notas: list[str] = []
    faltan = [POR_CLAVE[k].titulo for k in ('programada', 'tension', 'causa', 'alimentador', 'clientes',
                                            'fecha_fin_total', 'duracion_total') if k not in c]
    factores = {k: _factor_horas(titulos[c[k]]) for k in ('duracion', 'duracion_total') if k in c}
    excluidas: dict[str, int] = defaultdict(int)
    # Cada interrupción que cuenta: (fila, alimentador, clase, duración total, primera reposición,
    # si se repuso en dos tiempos). La fila queda para contar por otra columna (012:RF-90).
    contadas: list[tuple[Sequence[Any], str, str, float, float | None, bool]] = []
    sin_clase = 0
    fechas: list[_dt.datetime] = []
    clientes = 0
    for fila in filas:
        if not any(v not in (None, '') for v in fila):
            continue
        ini = _momento(_celda(fila, c['fecha_inicio']), _celda(fila, c.get('hora_inicio', -1)))
        if ini is None:
            excluidas['sin fecha de inicio'] += 1
            continue
        fechas.append(ini)
        if 'programada' in c and _es_programada(_celda(fila, c['programada'])):
            excluidas['programada'] += 1
            continue
        if 'tension' in c:
            kv = _num(_celda(fila, c['tension']))
            if kv is not None and not (MT_KV[0] < kv <= MT_KV[1]):
                excluidas['fuera de media tensión'] += 1
                continue
        textos = [_celda(fila, c[k]) for k in ('subcausa', 'causa') if k in c]
        motivo = _fuera_de_la_red(textos)
        if motivo:
            excluidas[f'fuera de la red: {motivo}'] += 1
            continue
        alim = clave(_celda(fila, c['alimentador'])) if 'alimentador' in c else ''
        if exposicion and alim not in exposicion:
            excluidas['alimentador que no está en la red del espacio'] += 1
            continue
        h1 = _duracion_h(c, fila, ini, 'fecha_fin', 'hora_fin', 'duracion', factores)
        ht = _duracion_h(c, fila, ini, 'fecha_fin_total', 'hora_fin_total', 'duracion_total', factores)
        total = ht if ht is not None and (h1 is None or ht >= h1) else h1
        if total is None:
            excluidas['sin duración ni fin'] += 1
            continue
        clase = clase_de_causa(textos) if textos else None
        if clase is None:
            sin_clase += 1
            continue
        primera = total > MOMENTANEA_MAX_H and ht is not None and h1 is not None and ht > h1 + 1e-9
        clientes += int(_num(_celda(fila, c.get('clientes', -1))) or 0)
        contadas.append((fila, alim, clase, total, h1, primera))
    if not fechas:
        return {'reconocido': False, 'notas': ['El histórico no tiene ninguna fecha de inicio legible.']}
    desde, hasta = min(fechas), max(fechas)
    anios = (hasta - desde).total_seconds() / (365.25 * 86400)

    # Lo que el registro dice de cada alimentador y clase, ya sin exposición: con esto se
    # vuelven a sacar las tasas cuando la exposición llega después (012:RF-87, ``con_exposicion``).
    conteos, primeras_por = _agrupar((a, k, t, h1, p) for _f, a, k, t, h1, p in contadas)
    puede_clasificar = 'causa' in c or 'subcausa' in c
    notas_columnas = [f'No se reconoce la columna «{k}»: se usa lo que hay.' for k in faltan]
    cifras, _fuera = _cifras(conteos, primeras_por, exposicion, anios, puede_clasificar, CLASES, POR_KM,
                             TIEMPOS)
    # 012:RF-90: qué columna es la del alimentador y por qué; sin red y sin título que la nombre,
    # lo contado por cada columna candidata, para elegirla al aplicar el libro con el proyecto.
    columna_alim: dict[str, Any] = {}
    error_alim = ''
    if 'alimentador' in c:
        columna_alim = {k: v for k, v in eleccion.items() if k != 'indice'}
        nota_columna = frase_columna(eleccion, DONDE_RED)
    elif exposicion:
        error_alim = eleccion.get('error') or frase_sin_columna(titulos, DONDE_RED)
        nota_columna = error_alim[0].upper() + error_alim[1:] + '.'
    else:
        columna_alim = _candidatas(titulos, filas, set(c.values()), contadas, clave)
        nota_columna = (f'{AVISO_COLUMNA}: ningún título la nombra; se elegirá por su contenido, con los '
                        'alimentadores del proyecto, al aplicar el libro.')
    notas += cifras.pop('notas') + notas_columnas + [nota_columna]
    return {
        'reconocido': True, 'hoja': hoja, 'primera_fila': primera_fila,
        'columnas': {POR_CLAVE[k].titulo: str(titulos[i]) for k, i in sorted(c.items(), key=lambda x: x[1])},
        'periodo': {'desde': desde.date().isoformat(), 'hasta': hasta.date().isoformat(), 'anios': round(anios, 4)},
        'filas': len(fechas) + excluidas.get('sin fecha de inicio', 0), 'sin_clase': sin_clase,
        'excluidas': dict(sorted(excluidas.items())), 'clientes_afectados': clientes,
        'criterio': ('No programadas de media tensión (1 kV < U ≤ 36 kV) de los alimentadores de la red; '
                     'sostenida > 5 min (IEEE Std 1366) da la tasa permanente y momentánea ≤ 5 min la '
                     'transitoria; λ = interrupciones / (exposición × años); r = media de la duración hasta la '
                     'reposición total de las sostenidas.'),
        **cifras, 'notas': notas,
        **({'exposicion': resumen_exposicion(exposicion, origen_exposicion)} if exposicion else {}),
        **({'error_alimentador': error_alim} if error_alim else {}),
        'base': {'conteos': conteos, 'primeras': primeras_por, 'anios': anios,
                 'puede_clasificar': puede_clasificar, 'notas_columnas': notas_columnas,
                 'excluidas': dict(sorted(excluidas.items())), 'alimentador': columna_alim},
    }


def _agrupar(contadas) -> tuple[dict[str, dict[str, list[float]]], dict[str, list[float]]]:
    """Por alimentador y clase, ``[sostenidas, momentáneas, horas de las sostenidas]``, y por
    alimentador las primeras reposiciones ``[n, horas]``, de ``(alimentador, clase, duración
    total, primera reposición, repuesta en dos tiempos)``."""
    eventos: dict[tuple[str, str], list[float]] = defaultdict(list)
    primeras: dict[str, list[float]] = defaultdict(list)
    for a, clase, total, h1, primera in contadas:
        eventos[(a, clase)].append(total)
        if primera:
            primeras[a].append(h1)
    conteos: dict[str, dict[str, list[float]]] = {}
    for (a, clase), lista in sorted(eventos.items()):
        sost = [t for t in lista if t > MOMENTANEA_MAX_H]
        conteos.setdefault(a, {})[clase] = [len(sost), len(lista) - len(sost), sum(sost)]
    return conteos, {a: [len(v), sum(v)] for a, v in sorted(primeras.items())}


def _candidatas(titulos: Sequence[Any], filas: Sequence[Sequence[Any]], usadas: set[int],
                contadas, clave) -> dict[str, Any]:
    """012:RF-90: sin red y sin título del alimentador, cada columna que podría serlo con lo que
    contaría si lo fuera; ``con_exposicion`` elige una con los alimentadores del proyecto.

    Solo se guardan las que podrían ganar en ``elegir_por_contenido``: llenas (un valor en más de
    la mitad de las filas) y de cardinalidad baja. Una columna con más valores distintos que la
    mitad de las filas es un identificador o un texto libre, y guardarla multiplicaría lo guardado
    por el número de filas."""
    datos = _filas_con_datos(filas)
    candidatas: dict[str, Any] = {}
    for i in range(len(titulos)):
        if i in usadas:
            continue
        valores = Counter(v for v in (clave(_celda(f, i)) for f in datos) if v)
        if not valores or len(valores) > MAYORIA_ALIMENTADOR * len(datos) \
                or sum(valores.values()) <= MAYORIA_ALIMENTADOR * len(datos):
            continue
        conteos, primeras = _agrupar((clave(_celda(f, i)), k, t, h1, p) for f, _a, k, t, h1, p in contadas)
        candidatas[str(i)] = {'valores': dict(valores), 'conteos': conteos, 'primeras': primeras}
    return {'por': None, 'titulos': ['' if t is None else str(t) for t in titulos], 'filas': len(datos),
            'candidatas': candidatas}


def _cifras(conteos: Mapping[str, Mapping[str, Sequence[float]]], primeras: Mapping[str, Sequence[float]],
            exposicion: Mapping[str, Mapping[str, float]], anios: float, puede_clasificar: bool,
            CLASES: Mapping[str, str], POR_KM: Sequence[str],
            TIEMPOS: Mapping[str, str]) -> tuple[dict[str, Any], int]:
    """Tasas, cifras por alimentador y tiempos a partir de lo contado por alimentador y clase
    (``[sostenidas, momentáneas, horas de las sostenidas]``) y de las primeras reposiciones
    (``[n, horas]``). Con exposición solo cuentan sus alimentadores, y se devuelve también
    cuántas interrupciones quedaron fuera por ser de otro. Lo usan ``derivar`` y
    ``con_exposicion``: las dos vías dan las mismas cifras (012:RF-87)."""
    notas: list[str] = []
    if exposicion:
        dentro = {a: v for a, v in conteos.items() if a in exposicion}
        fuera = int(sum(n[0] + n[1] for a, v in conteos.items() if a not in exposicion for n in v.values()))
        primeras = {a: v for a, v in primeras.items() if a in exposicion}
    else:
        dentro, fuera = dict(conteos), 0
    usadas = int(sum(n[0] + n[1] for v in dentro.values() for n in v.values()))
    alimentadores = sorted(exposicion) if exposicion else sorted(dentro)

    def cifra(n, exp):
        sost, mom, horas = int(n[0]), int(n[1]), float(n[2])
        d = {'sostenidas': sost, 'momentaneas': mom, 'exposicion': exp,
             'reparacion_h': (horas / sost) if sost else None}
        if exp and anios > 0:
            d['permanente'] = sost / (exp * anios)
            d['transitoria'] = mom / (exp * anios)
        return d

    tasas: dict[str, dict[str, Any]] = {}
    for clase in CLASES:
        tot = [sum(float(v[clase][i]) for v in dentro.values() if clase in v) for i in range(3)]
        n_ev = int(tot[0] + tot[1])
        exp = sum((exposicion.get(a) or {}).get(clase, 0.0) for a in alimentadores)
        d = cifra(tot, exp)
        unidad = 'km' if clase in POR_KM else 'unidades'
        if not puede_clasificar:
            continue
        if not exposicion:
            if n_ev:
                notas.append(f'{CLASES[clase]}: {n_ev} interrupciones, sin la red del espacio para '
                             'normalizarlas (falta la longitud o el número de elementos).')
            continue
        if not exp:
            if n_ev:
                notas.append(f'{CLASES[clase]}: {n_ev} interrupciones y la red no da su número de '
                             f'{unidad}: no se normaliza.')
            continue
        if anios <= 0:
            continue
        if not n_ev:
            # λ = 0 es la máxima verosimilitud, pero optimista: el informe no puede presentar
            # la clase como si nunca fallara. Con cero sucesos, el límite exacto de Poisson.
            d['cota_95'] = COTA_CERO_95 / (exp * anios)
            notas.append(f'{CLASES[clase]}: ninguna interrupción en {anios:.2f} años sobre {exp:.4g} {unidad}: '
                         f'λ = 0 y r = 0, lo que dice el registro; la cota superior al 95 % es '
                         f'{d["cota_95"]:.3g} por {"km" if clase in POR_KM else "unidad"} y año '
                         '(−ln 0,05 ≈ 3 entre exposición por años, la regla del tres).')
        tasas[clase] = {**d, 'reparacion_h': d['reparacion_h'] or 0.0}
    if exposicion and puede_clasificar and not usadas:
        # 012:RF-89: todo a cero diría que la red nunca falla; sin ninguna interrupción de sus
        # alimentadores, el histórico no dice nada de ella.
        tasas = {}
        notas.append('Ninguna interrupción del histórico es de un alimentador de la red: no se deriva '
                     'ninguna tasa.')
    por_alim: dict[str, dict[str, Any]] = {}
    for a in alimentadores:
        fila_a = {}
        for clase in CLASES:
            n = (dentro.get(a) or {}).get(clase) or (0, 0, 0.0)
            exp = (exposicion.get(a) or {}).get(clase, 0.0)
            if n[0] or n[1] or exp:
                fila_a[clase] = cifra(n, exp)
        if fila_a:
            por_alim[a] = fila_a
    if not puede_clasificar:
        notas.append('El histórico no tiene columna de causa: ninguna interrupción se puede asignar a una '
                     'clase de elemento y no se deriva ninguna tasa.')
    if not exposicion:
        notas.append('Falta la red del espacio: ' + FALTA_RED + '.')
    tiempos: dict[str, float] = {}
    n_prim = int(sum(v[0] for v in primeras.values()))
    if n_prim:
        tiempos = {'localizacion': 60 * sum(float(v[1]) for v in primeras.values()) / n_prim, 'manual': 0.0}
        notas.append(f'{TIEMPOS["localizacion"]}: media de la primera reposición de {n_prim} '
                     'interrupciones repuestas en dos tiempos. El registro no separa localización y maniobra: '
                     f'el total va en «{TIEMPOS["localizacion"]}» y «{TIEMPOS["manual"]}» queda en 0.')
    else:
        notas.append('El histórico no distingue la primera reposición de la total: no se derivan los tiempos de '
                     f'«{TIEMPOS["localizacion"]}» ni de «{TIEMPOS["manual"]}».')
    return {'usadas': usadas, 'tasas': tasas, 'por_alimentador': por_alim, 'tiempos_min': tiempos,
            'notas': notas}, fuera


def resumen_exposicion(exposicion: Mapping[str, Mapping[str, float]], origen: str) -> dict[str, Any]:
    """De dónde salió la exposición, la de cada alimentador y la total por clase (012:RF-20, RF-88)."""
    por_alim = {str(a): {k: float(v) for k, v in d.items()} for a, d in sorted(exposicion.items())}
    totales: dict[str, float] = defaultdict(float)
    for d in por_alim.values():
        for k, v in d.items():
            totales[k] += v
    return {'origen': origen, 'alimentadores': por_alim, 'totales': dict(totales)}


def con_de(texto: Any) -> str:
    """«de» delante de ``texto``, contraído en «del» si empieza por «el » (086:RF-134).

    El origen de la exposición es «el proyecto de DIgSILENT «…»», y la frase decía «leída de el proyecto».
    """
    texto = str(texto or '')
    return f'del {texto[3:]}' if texto.startswith('el ') else f'de {texto}'


def frase_exposicion(resumen: Mapping[str, Any]) -> str:
    """La exposición en una frase, para los avisos del libro (012:RF-88)."""
    t = resumen.get('totales') or {}
    return (f"Exposición leída {con_de(resumen.get('origen'))}: {len(resumen.get('alimentadores') or {})} "
            f"alimentadores, {t.get('linea', 0.0):.3f} km de línea aérea, {t.get('cable', 0.0):.3f} km de "
            f"cable, {t.get('transformador', 0.0):.0f} transformadores y {t.get('barra', 0.0):.0f} barras.")


def con_exposicion(historico: Mapping[str, Any], exposicion: Mapping[str, Mapping[str, float]], *,
                   clases: Mapping[str, str], por_km: Sequence[str], tiempos_nombres: Mapping[str, str],
                   origen: str) -> dict[str, Any]:
    """El histórico ya leído, normalizado con una exposición que llega después (012:RF-87).

    En un espacio sin red convertida el histórico se lee sin exposición; al aplicar el libro, el
    guion lee la del proyecto de DIgSILENT y la pasa aquí. Con lo contado por alimentador y clase
    (``historico['base']``) salen las mismas tasas, tiempos y cotas que con la red convertida, sin
    volver a abrir el libro. Un histórico guardado sin ``base`` no se puede normalizar:
    ``ValueError`` con lo que hay que hacer.

    012:RF-90: si ningún título nombraba la columna del alimentador, se elige aquí por su
    contenido con los alimentadores del proyecto; si ninguna lo es, ``ValueError`` con los
    títulos encontrados, y no hay tasas.
    """
    base = historico.get('base')
    if not base:
        raise ValueError('el histórico se guardó sin sus cuentas por alimentador: vuelva a subir el libro')
    exposicion = {clave_alimentador(k): dict(v) for k, v in exposicion.items()}
    conteos, primeras = base['conteos'], base['primeras']
    columna = dict(base.get('alimentador') or {})
    columnas = dict(historico.get('columnas') or {})
    notas_columnas = list(base.get('notas_columnas') or ())
    nota_columna: list[str] = []
    if columna.get('candidatas') is not None and columna.get('por') is None:
        candidatas = {int(i): d for i, d in columna['candidatas'].items()}
        elegida, error = elegir_por_contenido(
            columna['titulos'], {i: d['valores'] for i, d in candidatas.items()}, set(exposicion),
            int(columna['filas']), {i: (d['conteos'], d['primeras']) for i, d in candidatas.items()},
            DONDE_PROYECTO)
        if elegida is None:
            raise ValueError(error)
        conteos, primeras = candidatas[elegida['indice']]['conteos'], candidatas[elegida['indice']]['primeras']
        columna = {k: v for k, v in elegida.items() if k != 'indice'}
        alimentador = POR_CLAVE['alimentador'].titulo
        columnas[alimentador] = elegida['titulo']
        notas_columnas = [n for n in notas_columnas if f'«{alimentador}»' not in n]
        nota_columna = [frase_columna(elegida, DONDE_PROYECTO)]
    elif columna.get('por'):
        nota_columna = [frase_columna(columna, DONDE_PROYECTO)]
    cifras, fuera = _cifras(conteos, primeras, exposicion, float(base['anios']),
                            bool(base['puede_clasificar']), clases, por_km, tiempos_nombres)
    excluidas = dict(base.get('excluidas') or {})
    if fuera:
        clave = 'alimentador que no está en la red del espacio'
        excluidas[clave] = excluidas.get(clave, 0) + fuera
    notas = cifras.pop('notas') + notas_columnas + nota_columna
    return {**historico, **cifras, 'columnas': columnas, 'excluidas': dict(sorted(excluidas.items())),
            'notas': notas, 'exposicion': resumen_exposicion(exposicion, origen),
            'base': {**base, 'conteos': conteos, 'primeras': primeras, 'notas_columnas': notas_columnas,
                     'alimentador': columna}}

def buscar_en_hoja(ws, exposicion: Mapping[str, Mapping[str, float]], **nombres: Any) -> dict[str, Any] | None:
    """El histórico de una hoja, o ``None`` si la hoja no es un histórico de interrupciones."""
    filas = [tuple(r) for r in ws.iter_rows(values_only=True)]
    alims = tuple(clave_alimentador(k) for k in exposicion)
    for n, titulos in enumerate(filas[:FILAS_CABECERA]):
        if sum(1 for t in titulos if t not in (None, '')) < 3:
            continue
        datos = filas[n + 1:]
        if es_historico(reconocer_columnas(titulos, datos, alims)):
            return derivar(titulos, datos, exposicion, hoja=ws.title, primera_fila=n + 2, **nombres)
    return None
