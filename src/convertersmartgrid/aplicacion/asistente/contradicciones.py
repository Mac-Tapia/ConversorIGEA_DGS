"""047:RF-48 a RF-56: qué contradicción de un dictamen de revisión cuenta, decidido por el código y no por el LLM.

Una contradicción es ``{campo, valor_propuesta, valor_evidencia, fuente, base}``. Cuenta solo si sus dos valores son
distintos con la unidad normalizada, están en la propuesta y en la fuente citada y se refieren a la misma base (total o
por unidad). Lo que se descarta queda con su motivo. Sin LLM ni E/S: solo texto y cifras.
"""
from __future__ import annotations

from copy import deepcopy
import itertools
import math
import re

#: 047:RF-48: los campos de cada contradicción, en el orden en que el esquema los pide; ``base`` (RF-55) es opcional
#: para el código, para seguir leyendo los dictámenes guardados antes.
CAMPOS_CONTRADICCION = ('campo', 'valor_propuesta', 'valor_evidencia', 'fuente')
BASES = ('total', 'unidad')
#: 047:RF-49: dos cifras de la misma magnitud son el mismo valor si difieren menos del 0,5 % de la mayor. Absorbe el
#: redondeo de una cifra impresa con tres significativas (62 frente a 62,3 % es un 0,48 %) y no esconde un error de
#: ingeniería: el menor de los defectos sembrados en los conjuntos de la T8 cambia la cifra en más de un 2 %.
TOLERANCIA_RELATIVA = 0.005
#: Unidad normalizada (minúsculas, sin punto final, ² como 2) → (magnitud, factor a la unidad base de la magnitud).
_UNIDADES = {
    '%': ('porcentaje', 1.0), 'pct': ('porcentaje', 1.0),
    'w': ('potencia activa', 1e-3), 'kw': ('potencia activa', 1.0), 'mw': ('potencia activa', 1e3),
    'var': ('potencia reactiva', 1e-3), 'kvar': ('potencia reactiva', 1.0), 'mvar': ('potencia reactiva', 1e3),
    'va': ('potencia aparente', 1e-3), 'kva': ('potencia aparente', 1.0), 'mva': ('potencia aparente', 1e3),
    'wh': ('energía', 1e-3), 'kwh': ('energía', 1.0), 'mwh': ('energía', 1e3), 'gwh': ('energía', 1e6),
    'a': ('corriente', 1.0), 'ka': ('corriente', 1e3),
    'v': ('tensión', 1e-3), 'kv': ('tensión', 1.0),
    'p.u': ('por unidad', 1.0), 'pu': ('por unidad', 1.0),
    'usd': ('usd', 1.0), 'us$': ('usd', 1.0), 'dólares': ('usd', 1.0), 'dolares': ('usd', 1.0),
    'pen': ('pen', 1.0), 'soles': ('pen', 1.0),
    'm': ('longitud', 1.0), 'km': ('longitud', 1e3),
    'mm2': ('sección', 1.0),
    'h': ('tiempo', 60.0), 'min': ('tiempo', 1.0),
    'ohm': ('impedancia', 1.0), 'ω': ('impedancia', 1.0), 'kohm': ('impedancia', 1e3),
}
#: 047:RF-52: una cifra con separador de miles «.», «,» o espacio, o con coma o punto decimal.
_NUM = re.compile(r'(?<![\d.,])[-+]?(?:\d{1,3}(?: \d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*)(?!\d)')
_UNIDAD_TRAS = re.compile(r'\s*(p\.\s*u\b\.?|%|[a-zμω²$]+(?:/[a-z]+)?)')
#: Un elemento de la red («A71», «S-702», «P412», «e2») no es una cifra del valor.
_IDENTIFICADOR = re.compile(r'(?<![\w])[a-záéíóúñ]+-?\d+\w*')
_VERSUS = re.compile(r'\s+(?:vs\.?|versus|frente a)\s+', re.IGNORECASE)
_PRODUCTO = re.compile(r'\s*(?:[×*·]|(?<=\s)x(?=\s))\s*')
#: 047:RF-55: lo que sigue a una cifra que es por unidad y no un total.
_POR_UNIDAD = re.compile(r'^\s*(?:[a-z$/.]+\s+){0,2}?(?:por\s+(?:unidad|kil[oó]metro|km|metro|poste|cada)\b|c/u\b|'
                         r'cada\s+un[oa]\b|unitari[oa]|/\s*(?:km|u|m|unidad)\b)')


def _normal(texto) -> str:
    texto = str(texto)
    for espacio in (' ', ' ', ' '):
        texto = texto.replace(espacio, ' ')
    return ' '.join(texto.split()).casefold()


def _moneda(texto: str) -> str | None:
    if re.search(r'us\$|\busd\b|\$|d[oó]lares', texto):
        return 'usd'
    if re.search(r'(?<![a-z])s/|\bsoles\b', texto):
        return 'pen'
    return None


def _limpio(texto) -> str:
    """El texto con las marcas del modelo quitadas: «/^3$/i», «_3_», «>», «≈», «k340», y sin identificadores."""
    t = _normal(texto)
    t = re.sub(r'/\^?([^/]*?)\$?/[a-z]*', r' \1 ', t)
    t = re.sub(r'(?<![a-záéíóúñ])k(?=\d)', ' ', t)
    t = _IDENTIFICADOR.sub(' ', t)
    t = re.sub(r'\bus\b', ' ', re.sub(r'[_^<>≈~≥≤|\\]|\$', ' ', t))
    return ' '.join(t.split())


def _candidatos(cifra: str) -> set[float]:
    """Las lecturas de una cifra: «12.400» o «1,250» pueden ser miles o decimales y tienen dos (RF-52)."""
    cifra = cifra.replace(' ', '')
    signo = -1.0 if cifra.startswith('-') else 1.0
    cifra = cifra.lstrip('+-')
    puntos, comas = cifra.count('.'), cifra.count(',')
    try:
        if puntos and comas:
            decimal = '.' if cifra.rfind('.') > cifra.rfind(',') else ','
            miles = ',' if decimal == '.' else '.'
            entero, _, fraccion = cifra.rpartition(decimal)
            if not re.fullmatch(rf'\d{{1,3}}(?:\{miles}\d{{3}})*', entero) or not fraccion.isdigit():
                return set()
            return {signo * float(entero.replace(miles, '') + '.' + fraccion)}
        if puntos + comas > 1:
            sep = '.' if puntos else ','
            if not re.fullmatch(rf'\d{{1,3}}(?:\{sep}\d{{3}})+', cifra):
                return set()
            return {signo * float(cifra.replace(sep, ''))}
        if puntos + comas == 1:
            entero, _, fraccion = cifra.replace(',', '.').partition('.')
            lecturas = {signo * float(f'{entero}.{fraccion}')}
            if len(fraccion) == 3 and 1 <= len(entero) <= 3 and entero != '0':
                lecturas.add(signo * float(entero + fraccion))
            return lecturas
        return {signo * float(cifra)}
    except ValueError:
        return set()


def _unidad(resto: str) -> str | None:
    m = _UNIDAD_TRAS.match(resto)
    if not m:
        return None
    unidad = re.sub(r'\s', '', m[1]).rstrip('.').replace('²', '2')
    return unidad if unidad in _UNIDADES else None


def _cifras(texto: str) -> list[tuple[set[float], str | None, int]]:
    """Cada cifra de un texto ya limpio, con sus lecturas, su unidad y dónde termina."""
    salida = []
    for m in _NUM.finditer(texto):
        lecturas = _candidatos(m[0])
        if lecturas:
            salida.append((lecturas, _unidad(texto[m.end():]), m.end()))
    return salida


class _Lectura:
    """Las lecturas de un valor, su unidad, si es una cuenta (``9 × 210``) y sus operandos."""
    __slots__ = ('lecturas', 'unidad', 'cuenta', 'operandos', 'texto')

    def __init__(self, lecturas, unidad, cuenta=False, operandos=(), texto=''):
        self.lecturas, self.unidad, self.cuenta, self.operandos, self.texto = (
            set(lecturas), unidad, cuenta, list(operandos), texto)


def _leer(valor) -> _Lectura | None:
    """047:RF-52: la cifra de un valor, también dentro de una frase («Cargabilidad máxima de A71 74 %» es 74 %)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return _Lectura({float(valor)}, None)
    bruto = _normal(valor)
    t = _limpio(valor)
    izquierda = t.split('=', 1)[0]
    for partes, operar in ((_PRODUCTO.split(izquierda), math.prod), (izquierda.split('+'), sum)):
        if len(partes) < 2:
            continue
        operandos = [_cifras(p) for p in partes]
        if all(len(o) == 1 for o in operandos):
            conjuntos = [o[0][0] for o in operandos]
            lecturas = {operar(c) for c in itertools.islice(itertools.product(*conjuntos), 64)}
            return _Lectura(lecturas, None, True, conjuntos, t)
    cifras = _cifras(t)
    if not cifras:
        return None
    distintas = {(frozenset(c), u) for c, u, _f in cifras}
    if len(distintas) > 1:
        return None
    lecturas, unidad, _fin = cifras[0]
    return _Lectura(lecturas, unidad or _moneda(bruto), texto=t)


def _escaladas(lecturas, unidad) -> set[tuple[str | None, float]]:
    magnitud = _UNIDADES.get(unidad)
    return {(magnitud[0], v * magnitud[1]) if magnitud else (None, v) for v in lecturas}


def _cerca(a: float, b: float, tolerancia: float) -> bool:
    return math.isclose(a, b, rel_tol=tolerancia, abs_tol=1e-9)


def valores_coinciden(propuesta, evidencia) -> bool:
    """047:RF-49 / RF-52 — si dos valores son el mismo, con la unidad normalizada y ``TOLERANCIA_RELATIVA``.

    Una cifra ambigua («12.400») coincide si una de sus lecturas es la del otro valor. Conservador: texto distinto,
    magnitudes distintas o un valor con varias cifras no coinciden, y la contradicción se mantiene. Un valor sin unidad
    toma la del otro: es un formato.
    """
    if _normal(propuesta) == _normal(evidencia):
        return True
    a, b = _leer(propuesta), _leer(evidencia)
    if a is None or b is None:
        return False
    if a.unidad and b.unidad and a.unidad != b.unidad:
        ea, eb = _escaladas(a.lecturas, a.unidad), _escaladas(b.lecturas, b.unidad)
        return any(ma == mb and ma is not None and _cerca(x, y, TOLERANCIA_RELATIVA)
                   for ma, x in ea for mb, y in eb)
    # Sin unidad en un lado: es la misma cifra, o la del otro en la unidad base de su magnitud («1250» y «1,25 MW»).
    if any(_cerca(x, y, TOLERANCIA_RELATIVA) for x in a.lecturas for y in b.lecturas):
        return True
    if (a.unidad is None) == (b.unidad is None):
        return False
    sin, con = (a, b) if a.unidad is None else (b, a)
    return any(_cerca(x, y, TOLERANCIA_RELATIVA) for x in sin.lecturas for _m, y in _escaladas(con.lecturas, con.unidad))


def _numeros_de(texto) -> set[float]:
    """Todas las lecturas de todas las cifras de un texto, también en la unidad base y separadas por espacios."""
    t = _limpio(texto)
    numeros = set()
    for lecturas, unidad, _fin in _cifras(t):
        numeros |= lecturas | {v for _m, v in _escaladas(lecturas, unidad)}
    for suelta in re.findall(r'\d+(?:[.,]\d+)?', t):
        numeros |= _candidatos(suelta)
    return numeros


def _aparece(valor, texto) -> bool:
    """047:RF-53: el valor está en el texto: su cifra (o, de una cuenta, cada operando), o su texto si no tiene cifra."""
    lectura = _leer(valor)
    if lectura is None:
        frase = _normal(valor)
        return bool(frase) and frase in _normal(texto)
    numeros = _numeros_de(texto)
    def esta(lecturas, unidad):
        return any(_cerca(v, n, 1e-9) for _m, v in _escaladas(lecturas, unidad) | {(None, x) for x in lecturas}
                   for n in numeros)
    if lectura.cuenta:
        return all(esta(o, None) for o in lectura.operandos)
    return esta(lectura.lecturas, lectura.unidad)


def cifras_sin_respaldo(texto, fuente) -> list[str]:
    """072:RF-54: las cifras de ``texto`` que no están en ``fuente``, leídas como en :func:`_aparece`.

    En una salida generada, una cifra que no trae su entrada es un valor inventado: el modelo de redacción aprendió con
    las cifras ocultas y no debe ponerlas. Una cifra ilegible tampoco tiene respaldo.
    """
    numeros = _numeros_de(fuente)
    fuera = []
    for m in _NUM.finditer(_limpio(texto)):
        lecturas = _candidatos(m[0])
        if not any(_cerca(v, n, 1e-9) for v in lecturas for n in numeros):
            fuera.append(m[0])
    return fuera


def _base_de_evidencia(valor, texto) -> str | None:
    """047:RF-55: «unidad» si la cifra va seguida de «por unidad», «por km», «c/u»…; «total» si es una cuenta
    («4 × 130»); ``None`` si el texto no lo dice, y entonces vale la base que declara el dictamen."""
    lectura = _leer(valor)
    if lectura is None:
        return None
    if lectura.cuenta:
        return 'total'
    propio = _limpio(valor)
    for lecturas, _u, fin in _cifras(propio):
        if _POR_UNIDAD.match(propio[fin:]):
            return 'unidad'
    if texto is None:
        return None
    t = _limpio(texto)
    bases = {('unidad' if _POR_UNIDAD.match(t[fin:fin + 60]) else 'total')
             for lecturas, _u, fin in _cifras(t)
             if any(_cerca(x, y, 1e-9) for x in lecturas for y in lectura.lecturas)}
    return 'unidad' if bases == {'unidad'} else None


def _base_de_campo(campo: str) -> str:
    return 'unidad' if re.search(r'unitari|por_unidad|por_km|_unidad\b|_u$', _normal(campo)) else 'total'


def texto_de(dato, excluir=('restricciones_deterministas', 'dictamenes_ronda_anterior')) -> str:
    """El texto de la propuesta en que se buscan sus valores (RF-53): sus claves y valores, sin lo que no es suyo."""
    if isinstance(dato, dict):
        return ' ; '.join(f'{k}: {texto_de(v, excluir)}' for k, v in dato.items() if k not in excluir)
    if isinstance(dato, (list, tuple)):
        return ' ; '.join(texto_de(v, excluir) for v in dato)
    return str(dato)


def _de_texto(texto: str) -> tuple[str, str, str] | None:
    """(campo, valor de la propuesta, valor de la evidencia) de una contradicción en texto libre «campo: X vs Y»."""
    partes = _VERSUS.split(re.sub(r'\([^()]*\)', ' ', texto))
    if len(partes) != 2:
        return None
    izquierda, derecha = partes
    campo, _, izquierda = izquierda.rpartition(':')
    if not izquierda.strip() or not derecha.strip():
        return None
    return campo.strip(), izquierda.strip(), derecha.strip()


def _valida(entrada) -> bool:
    claves = set(entrada) if isinstance(entrada, dict) else set()
    if claves not in (set(CAMPOS_CONTRADICCION), set(CAMPOS_CONTRADICCION) | {'base'}):
        return False
    if 'base' in entrada and entrada['base'] not in BASES:
        return False
    return not any(isinstance(v, bool) or not isinstance(v, (str, int, float)) or not str(v).strip()
                   or len(str(v)) > 2000 for v in entrada.values())


def _del_campo(campo, propuesta):
    """047:RF-54: el valor que la propuesta da a ese campo, si lo nombra («e1: carga_pct» nombra «carga_pct»)."""
    if not isinstance(propuesta, dict):
        return None
    clave = _clave(campo)
    if clave == ACCION:
        return None
    valor = propuesta.get(clave)
    return valor if isinstance(valor, (str, int, float)) and not isinstance(valor, bool) else None


#: 047:RF-56: la acción es lo que se revisa (RF-46); su texto frente al de una evidencia no es una contradicción.
ACCION = 'accion'


def _clave(campo) -> str:
    return str(campo).rpartition(':')[2].strip()


def _motivo(campo, valor_p, valor_e, fuente, base, propuesta, evidencia):
    """Por qué no cuenta, o ``None`` si cuenta (RF-49, RF-53, RF-55, RF-56)."""
    if _clave(campo) == ACCION and (_leer(valor_p) is None or _leer(valor_e) is None):
        return 'la acción no es un dato: solo cuenta una cifra suya distinta de la de la evidencia'
    if propuesta is not None and _del_campo(campo, propuesta) is None and not _aparece(valor_p, texto_de(propuesta)):
        return f'no fundada: «{valor_p}» no está en la propuesta'
    texto = None
    if evidencia is not None:
        if fuente is not None:
            registro = evidencia.get(fuente)
            if not isinstance(registro, dict):
                return f'no fundada: {fuente!r} no es una evidencia del paquete'
            texto = registro.get('fragmento') if isinstance(registro.get('fragmento'), str) else None
        else:
            fragmentos = [r.get('fragmento') for r in evidencia.values()
                          if isinstance(r, dict) and isinstance(r.get('fragmento'), str)]
            texto = ' ; '.join(fragmentos) if fragmentos else None
        # Sin el texto de la fuente no se puede comprobar: la contradicción se mantiene (conservador).
        # Una cuenta («9 × 210») puede tomar la cantidad de la propuesta y el precio de la fuente.
        lectura = _leer(valor_e)
        donde = texto if texto is None or lectura is None or not lectura.cuenta or propuesta is None else (
            f'{texto} ; {texto_de(propuesta)}')
        if donde is not None and not _aparece(valor_e, donde):
            return f'no fundada: «{valor_e}» no está en {fuente or "la evidencia"}'
    base_e = _base_de_evidencia(valor_e, texto) or base or 'total'
    base_p = _base_de_campo(campo)
    if base_e != base_p:
        return f'bases distintas: propuesta {base_p}, evidencia {base_e}'
    if valores_coinciden(valor_p, valor_e):
        return f'valores iguales: «{valor_p}» y «{valor_e}»'
    return None


def filtrar_contradicciones(entradas, propuesta=None, evidencia=None) -> tuple[list, list[dict]]:
    """047:RF-48 a RF-55 — las contradicciones que cuentan y las descartadas, con su motivo.

    Con ``propuesta`` y ``evidencia`` comprueba además que cada valor esté donde dice; si el campo es de la propuesta,
    su valor es el de la propuesta. Una entrada en texto libre (formato anterior) se interpreta como «X vs Y» y, si no
    se puede, se mantiene. Una entrada con otra forma lanza ``ValueError``: el dictamen no es válido.
    """
    quedan, descartadas = [], []
    for entrada in entradas:
        if isinstance(entrada, str):
            if not entrada or len(entrada) > 2000:
                raise ValueError('contradicción vacía o demasiado larga')
            leida = _de_texto(entrada)
            if leida is None:
                quedan.append(entrada)
                continue
            campo, valor_p, valor_e = leida
            valor_p = _del_campo(campo, propuesta) if _del_campo(campo, propuesta) is not None else valor_p
            motivo = _motivo(campo, valor_p, valor_e, None, None, propuesta, evidencia)
            (descartadas.append({'entrada': entrada, 'motivo': motivo}) if motivo else quedan.append(entrada))
            continue
        if not _valida(entrada):
            raise ValueError('contradicción sin campo, valor_propuesta, valor_evidencia y fuente válidos')
        entrada = deepcopy(entrada)
        propio = _del_campo(entrada['campo'], propuesta)
        if propio is not None and not valores_coinciden(propio, entrada['valor_propuesta']):
            entrada['valor_propuesta_devuelto'] = entrada['valor_propuesta']
            entrada['valor_propuesta'] = propio
        motivo = _motivo(entrada['campo'], entrada['valor_propuesta'], entrada['valor_evidencia'],
                         str(entrada['fuente']), entrada.get('base'), propuesta, evidencia)
        (descartadas.append({'entrada': entrada, 'motivo': motivo}) if motivo else quedan.append(entrada))
    return quedan, descartadas
