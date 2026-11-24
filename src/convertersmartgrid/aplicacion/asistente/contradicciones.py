"""047:RF-48 a RF-56, RF-75 a RF-83: qué contradicción de un dictamen de revisión cuenta, decidido por el código y no por el LLM.

Una contradicción es ``{campo, valor_propuesta, valor_evidencia, fuente, base}``. Cuenta solo si sus dos valores son
distintos con la unidad normalizada, están en la propuesta y en la fuente citada y se refieren a la misma base (total o
por unidad). Lo que se descarta queda con su motivo. Sin LLM ni E/S: solo texto y cifras.
"""
from __future__ import annotations

from copy import deepcopy
import itertools
import math
import re
import unicodedata

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
#: 047:RF-98, RF-100: el nombre de un elemento de la red («V-3318», «A140», «Q7»), sin guion, para comparar el de la
#: acción o el del campo con el de la evidencia. Una sola definición para todas las comprobaciones que lo usan.
_ELEMENTO = re.compile(r'\b[a-z]{1,4}-?\d{1,6}\b')


def _elementos(texto: str) -> set[str]:
    return {i.replace('-', '') for i in _ELEMENTO.findall(_normal(texto))}
_VERSUS = re.compile(r'\s+(?:vs\.?|versus|frente a)\s+', re.IGNORECASE)
#: 047:RF-55: lo que sigue a una cifra que es por unidad y no un total.
#: 047:RF-92: con el 047i (2026-11-23), «185 dólares la unidad» y «12.500 USD por equipo» se leían como totales y el
#: código daba por malo el coste de propuestas sanas; son formas corrientes de un precio unitario.
_POR_UNIDAD = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?(?:por\s+(?:unidad|kil[oó]metro|km|metro|poste|cada|equipo|pieza|juego|'
                         r'elemento|aparato)\b|c/u\b|(?:la|cada)\s+(?:unidad|pieza)\b|cada\s+un[oa]\b|unitari[oa]|'
                         r'/\s*(?:km|u|m|unidad)\b)')


def _normal(texto) -> str:
    texto = str(texto)
    for espacio in (' ', ' ', ' '):
        texto = texto.replace(espacio, ' ')
    return ' '.join(texto.split()).casefold()


def _moneda(texto: str) -> str | None:
    if re.search(r'us\$|\busd\b|\$(?!\{)|d[oó]lares', texto):
        return 'usd'
    if re.search(r'(?<![a-z])s/|\bsoles\b', texto):
        return 'pen'
    return None


def _limpio(texto) -> str:
    """El texto con las marcas del modelo quitadas: «/^3$/i», «_3_», «>», «≈», «k340», y sin identificadores."""
    t = _normal(texto)
    t = re.sub(r'/\^([^/]*?)\$?/[a-z]*', r' \1 ', t)
    t = re.sub(r'\$\{([^}]*)\}', r' \1 ', t)            # «${61}», una plantilla
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


#: 047:RF-75: una cuenta admite + − × · x / y paréntesis; las palabras y las unidades («USD/km») no cuentan.
_OPERADORES = '+-×·*/()'
_PALABRA = re.compile(r'[a-záéíóúñ%$²μω.]*[a-záéíóúñ%$²μω](?:/[a-záéíóúñ]+)?')
#: Tope de lecturas de una cuenta con cifras ambiguas (cada «12.400» tiene dos).
_MAX_LECTURAS = 64


def _fichas(texto: str):
    """Las fichas de una cuenta: cifras (con sus lecturas) y operadores; ``None`` si queda algo que no lo es."""
    t = texto.split('=', 1)[0]
    if re.search(r'\d/\d', t):      # «22,9/0,40 kV» es una relación, no una división
        return None
    t = re.sub(r'(?<=[\d)\s])x(?=[\s\d(])', '×', t).replace('−', '-').replace('–', '-')
    t = re.sub(r'[;:]|(?<!\d)[.,]|[.,](?!\d)', ' ', _PALABRA.sub(' ', t))
    fichas, i = [], 0
    while i < len(t):
        if t[i].isspace():
            i += 1
        elif t[i] in _OPERADORES:
            fichas.append(t[i] if t[i] not in '×·' else '*')
            i += 1
        else:
            m = _NUM.match(t, i)
            lecturas = _candidatos(m[0].lstrip('+-')) if m and m[0][:1] not in '+-' else None
            if not lecturas:
                return None
            fichas.append(lecturas)
            i = m.end()
    return fichas


def evaluar_cuenta(texto: str):
    """047:RF-75 — (lecturas del resultado, lecturas de cada operando) de una cuenta como «14 × (52 + 3) / 2».

    Analizador propio por descenso recursivo (nunca ``eval``): ``None`` si no es una cuenta con al menos un operador
    entre dos cifras, si queda algo que no se entiende o si divide por cero.
    """
    fichas = _fichas(_limpio(texto))
    if not fichas or not any(isinstance(f, str) and f not in '()' for f in fichas) or \
            sum(isinstance(f, set) for f in fichas) < 2:
        return None
    operandos, pos = [], [0]

    def ver():
        return fichas[pos[0]] if pos[0] < len(fichas) else None

    def combinar(a, b, op):
        salida = set()
        for x, y in itertools.islice(itertools.product(a, b), _MAX_LECTURAS):
            if op == '/' and y == 0:
                raise ZeroDivisionError
            salida.add(x + y if op == '+' else x - y if op == '-' else x * y if op == '*' else x / y)
        return salida

    def factor():
        f = ver()
        if f == '-':
            pos[0] += 1
            return {-v for v in factor()}
        if f == '(':
            pos[0] += 1
            v = suma()
            if ver() != ')':
                raise ValueError
            pos[0] += 1
            return v
        if isinstance(f, set):
            pos[0] += 1
            operandos.append(f)
            return f
        raise ValueError

    def producto():
        v = factor()
        while ver() in ('*', '/'):
            op = ver()
            pos[0] += 1
            v = combinar(v, factor(), op)
        return v

    def suma():
        v = producto()
        while ver() in ('+', '-'):
            op = ver()
            pos[0] += 1
            v = combinar(v, producto(), op)
        return v

    try:
        resultado = suma()
    except (ValueError, ZeroDivisionError):
        return None
    if pos[0] != len(fichas):
        return None
    return resultado, operandos


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
    cuenta = evaluar_cuenta(t)
    if cuenta is not None:
        lecturas, operandos = cuenta
        return _Lectura(lecturas, None, True, operandos, t)
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


#: 047:RF-76: lo que sigue a una cifra que es un precio por kilómetro, y el total explícito de una obra.
#: 047:RF-92: «9.000 USD el kilómetro» (047i) también es un precio por km.
_POR_KM = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?(?:(?:por|el|cada)\s+(?:cada\s+)?(?:kil[oó]metro|km)\b|/\s*km\b)')
_EN_TOTAL = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?en\s+total\b')
#: Un campo de la propuesta que es una magnitud, no una cantidad de piezas.
_MAGNITUD_DE_CAMPO = re.compile(r'(?:_(?:pct|pu|a|kw|kva|kvar|mw|mva|usd|ohm|km|h|kv|v|m)$)|^(?:coste|costo)|_final|carga')


#: 047:RF-96: unidades de una magnitud física que siguen a una cifra de la acción («150 kvar», «250 kva»).
_UNIDAD_FISICA = re.compile(r'(?:k|m)?(?:va|var|vars|w|v|vac|vdc)|kvar|kvars|amperios?|voltios?|vatios?|metros?|'
                            r'kil[oó]metros?|mil[ií]metros?|ohmios?|hertz|grados?')


def _tipo_de_cifra(texto: str, fin: int) -> str:
    resto = texto[fin:fin + 60]
    return 'km' if _POR_KM.match(resto) else 'unidad' if _POR_UNIDAD.match(resto) else 'total'


def _tipo_por_unidad(valor, texto) -> str | None:
    """047:RF-76: «km» o «unidad» si la cifra del valor va seguida, en él o en la fuente, de su marca («por unidad»,
    «c/u», «/km», «por kilómetro»); ``None`` si nada lo dice. La base que declara el dictamen solo se guarda."""
    lectura = _leer(valor)
    if lectura is None or lectura.cuenta:
        return None
    propio = _limpio(valor)
    for _l, _u, fin in _cifras(propio):
        if _tipo_de_cifra(propio, fin) != 'total':
            return _tipo_de_cifra(propio, fin)
    if texto is None:
        return None
    t = _limpio(texto)
    tipos = {_tipo_de_cifra(t, fin) for lecturas, _u, fin in _cifras(t)
             if any(_cerca(x, y, 1e-9) for x in lecturas for y in lectura.lecturas)}
    return tipos.pop() if len(tipos) == 1 and tipos != {'total'} else None


def _raiz(palabra: str) -> str:
    sin_tildes = ''.join(c for c in unicodedata.normalize('NFKD', palabra.casefold()) if not unicodedata.combining(c))
    return sin_tildes[:5]


def _tema(palabra: str) -> str:
    """047:RF-99: el tema léxico de un infinitivo o de su sustantivo («podar» y «poda» → «pod»; «trabajar» y «trabajo»
    → «trabaj»), sin tildes: sin la terminación del infinitivo, ni la vocal final ni el plural del sustantivo."""
    t = ''.join(c for c in unicodedata.normalize('NFKD', palabra.casefold()) if not unicodedata.combining(c))
    return re.sub(r'(?:ar|er|ir)$|(?:[aoe]s?)$', '', t)


def _raices(texto: str) -> set[str]:
    return {_raiz(p) for p in re.findall(r'[a-záéíóúñ]{4,}', _IDENTIFICADOR.sub(' ', _normal(texto)))}


def cantidad_anclada(propuesta, texto) -> float | None:
    """047:RF-76: las piezas de la propuesta de las que habla ``texto`` («Poste de concreto… c/u» y ``postes: 6``, o
    «reemplazar 6 postes»); ``None`` si no hay ninguna o hay varias distintas."""
    if not isinstance(propuesta, dict) or texto is None:
        return None
    contexto = _raices(texto)
    valores = set()
    for clave, valor in propuesta.items():
        if (isinstance(valor, int) and not isinstance(valor, bool) and valor > 0
                and not _MAGNITUD_DE_CAMPO.search(clave) and {_raiz(p) for p in clave.split('_') if len(p) >= 4} & contexto):
            valores.add(float(valor))
    accion = propuesta.get(ACCION)
    if isinstance(accion, str):
        for m in re.finditer(r'(?<![\w.,])(\d+)\s+([a-záéíóúñ]{4,})', _normal(accion)):
            # 047:RF-96: «3 bancos … de 150 kvar»: 150 es una magnitud, no 150 piezas.
            if _raiz(m[2]) in contexto and not _UNIDAD_FISICA.fullmatch(m[2]):
                valores.add(float(m[1]))
    if not valores:
        # 047:RF-92: con el 047i, «Analizador de calidad… USD 2.200 cada uno» y ``medidores: 4``: el fragmento no nombra
        # la pieza con la palabra del campo. Si la propuesta tiene una sola cantidad de piezas, el precio unitario es suyo.
        piezas = {float(v) for k, v in propuesta.items() if k != ACCION and isinstance(v, int) and not isinstance(v, bool)
                  and v > 0 and not _MAGNITUD_DE_CAMPO.search(k) and _es_cantidad(k)}
        return piezas.pop() if len(piezas) == 1 else None
    return valores.pop() if len(valores) == 1 else None


def longitud_anclada(propuesta) -> float | None:
    """047:RF-76: los kilómetros de la propuesta (un campo ``*_km`` o «2,5 km» en la acción), si son unos solos."""
    if not isinstance(propuesta, dict):
        return None
    valores = {float(v) for k, v in propuesta.items()
               if k.endswith('_km') and isinstance(v, (int, float)) and not isinstance(v, bool)}
    accion = propuesta.get(ACCION)
    if isinstance(accion, str):
        for m in re.finditer(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*km\b', _normal(accion)):
            lecturas = _candidatos(m[1])
            if len(lecturas) == 1:
                valores |= lecturas
    return valores.pop() if len(valores) == 1 else None


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


#: 047:RF-56: la acción es lo que se revisa (RF-46); su texto frente al de una evidencia no es una contradicción.
ACCION = 'accion'


def _clave(campo) -> str:
    return str(campo).rpartition(':')[2].strip()


def _del_campo(campo, propuesta):
    """047:RF-54: el valor que la propuesta da a ese campo, si lo nombra («e1: carga_pct» nombra «carga_pct»)."""
    if not isinstance(propuesta, dict):
        return None
    clave = _clave(campo)
    if clave == ACCION:
        return None
    valor = propuesta.get(clave)
    return valor if isinstance(valor, (str, int, float)) and not isinstance(valor, bool) else None


def _texto_de_fuentes(fuente, evidencia):
    """047:RF-78: el fragmento de la fuente citada, o de las varias («e1 e2», «e1, e2»); (texto o None, error o None)."""
    if fuente is None:
        fragmentos = [r.get('fragmento') for r in evidencia.values()
                      if isinstance(r, dict) and isinstance(r.get('fragmento'), str)]
        return (' ; '.join(fragmentos) if fragmentos else None), None
    ids = [fuente] if fuente in evidencia else re.findall(r'[A-Za-z]+\d+', fuente)
    if not ids or any(not isinstance(evidencia.get(i), dict) for i in ids):
        return None, f'no fundada: {fuente!r} no es una evidencia del paquete'
    fragmentos = [evidencia[i].get('fragmento') for i in ids]
    if any(not isinstance(f, str) for f in fragmentos):
        return None, None
    return ' ; '.join(fragmentos), None


def _solo_cifra(valor) -> bool:
    """047:RF-83: el valor es una cifra con su unidad y, como mucho, dos palabras más («450 kvar», «2 aisladores»),
    no una frase que trae de paso una cifra («trabajar en caliente en el tramo T210 para cambiar 2 aisladores»)."""
    if _leer(valor) is None:
        return False
    resto = _NUM.sub(' ', _limpio(valor))
    palabras = [p for p in re.findall(r'[a-záéíóúñ%$²μω.]+', resto) if p.strip('.') and p.strip('.') not in _UNIDADES]
    return len(palabras) <= 2


def _motivo(campo, valor_p, valor_e, fuente, propuesta, evidencia, comprobados=()) -> tuple[str | None, dict]:
    """Por qué no cuenta (o ``None`` si cuenta) y lo que el código calculó (RF-49, RF-53, RF-55, RF-56, RF-75, RF-76,
    RF-79, RF-83)."""
    motivo, calculo = _motivo_por_valores(campo, valor_p, valor_e, fuente, propuesta, evidencia)
    if motivo is None and _clave(campo) in comprobados:
        # 047:RF-79: con el 047f, el modelo comparaba el coste total con cada partida («18900» frente a «16.400»); el
        # código ya sumó las partidas de la evidencia y cuadran, así que para ese campo decide su cuenta.
        return f'el código comprobó {_clave(campo)} con la evidencia y cuadra', calculo
    return motivo, calculo


def _motivo_por_valores(campo, valor_p, valor_e, fuente, propuesta, evidencia) -> tuple[str | None, dict]:
    if _clave(campo) == ACCION and not (_solo_cifra(valor_p) and _solo_cifra(valor_e)):
        return 'la acción no es un dato: solo cuenta una cifra suya distinta de la de la evidencia', {}
    if propuesta is not None and _del_campo(campo, propuesta) is None and not _aparece(valor_p, texto_de(propuesta)):
        return f'no fundada: «{valor_p}» no está en la propuesta', {}
    accion = propuesta.get(ACCION) if isinstance(propuesta, dict) else None
    if (_del_campo(campo, propuesta) is None and isinstance(valor_p, str) and not re.search(r'\d', valor_p)
            and isinstance(accion, str) and _repite_la_accion(_normal(valor_p), accion)):
        # 047:RF-86: con el 047g, «conductor de enlace» (palabras de la acción, sin cifra ni elemento) se enfrentaba
        # a la descripción del conductor en la evidencia; eso no es un dato de la propuesta (RF-56).
        return 'repite la acción que se revisa: no es un dato', {}
    texto = None
    if evidencia is not None:
        texto, error = _texto_de_fuentes(fuente, evidencia)
        if error:
            return error, {}
        # Sin el texto de la fuente no se puede comprobar: la contradicción se mantiene (conservador).
        # Una cuenta («14 × 52») puede tomar la cantidad de la propuesta y el precio de la fuente (RF-75).
        lectura = _leer(valor_e)
        donde = texto if texto is None or lectura is None or not lectura.cuenta or propuesta is None else (
            f'{texto} ; {texto_de(propuesta)}')
        if donde is not None and not _aparece(valor_e, donde):
            return f'no fundada: «{valor_e}» no está en {fuente or "la evidencia"}', {}
    magnitud = _magnitud_de_la_evidencia(campo, valor_p, valor_e, texto)
    if magnitud:
        return f'magnitudes distintas: {_clave(campo)} es una cantidad y la evidencia da {magnitud}', {}
    base_p = _base_de_campo(campo)
    tipo = _tipo_por_unidad(valor_e, texto)
    if tipo and base_p == 'total':
        # 047:RF-76: un precio por unidad o por km se pasa a total con la cantidad anclada, en vez de descartarse.
        factor = longitud_anclada(propuesta) if tipo == 'km' else cantidad_anclada(propuesta, texto)
        if factor is None:
            return f'bases distintas: propuesta total, evidencia por {tipo}, sin cantidad anclada', {}
        lectura = _leer(valor_e)
        totales = {v * factor for v in lectura.lecturas}
        referencia = _leer(valor_p)
        cerca_de = next(iter(referencia.lecturas)) if referencia else 0.0
        calculo = {'valor_evidencia_total': min(totales, key=lambda v: abs(v - cerca_de)),
                   'calculo': f'{factor:g} × {valor_e}'}
        if any(valores_coinciden(valor_p, v) for v in totales):
            return f'valores iguales tras convertir: {calculo["calculo"]}', calculo
        return None, calculo
    if base_p == 'unidad' and tipo is None and _leer(valor_e) is not None and not _leer(valor_e).cuenta:
        return 'bases distintas: propuesta por unidad, evidencia total', {}
    if valores_coinciden(valor_p, valor_e):
        return f'valores iguales: «{valor_p}» y «{valor_e}»', {}
    return None, {}


#: 047:RF-87: raíces de las palabras de un campo que dicen su magnitud aunque no lleve la unidad en el nombre.
_RAICES_DE_MAGNITUD = ('longi', 'dista', 'largo', 'tensi', 'volta', 'corri', 'poten', 'energ', 'secci', 'tiemp',
                       'durac', 'imped', 'carga', 'cosen', 'facto', 'coste', 'costo', 'preci', 'impor', 'monto')


def _magnitud_de_la_evidencia(campo, valor_p, valor_e, texto) -> str | None:
    """047:RF-87: la magnitud de la cifra de la evidencia si el campo es una cantidad de elementos y ella no lo es.

    Con el 047g, el LLM enfrentaba una cantidad de picas con los metros de cada pica. Un campo es una cantidad si su
    nombre no lleva unidad ni una palabra de magnitud y su valor es un entero sin unidad; la unidad de la evidencia es
    la de su valor o, si viene sin unidad («3»), la de esa cifra en el texto de la fuente.
    """
    partes = [x for x in re.split(r'[_\W]+', _normal(_clave(campo))) if x]
    if not partes or any(x in _UNIDADES for x in partes) or any(x.startswith(_RAICES_DE_MAGNITUD) for x in partes):
        return None
    lp = _leer(valor_p)
    if lp is None or lp.unidad is not None or lp.cuenta or not all(float(v).is_integer() for v in lp.lecturas):
        return None
    le = _leer(valor_e)
    if le is None or le.cuenta:
        return None
    unidad = le.unidad
    if unidad is None and texto:
        unidades = {u for c, u, _f in _cifras(_limpio(texto)) if c & le.lecturas}
        unidad = unidades.pop() if len(unidades) == 1 else None
    magnitud = _UNIDADES.get(unidad)
    return magnitud[0] if magnitud else None


def filtrar_incertidumbres(incertidumbres, propuesta=None, comprobados=()) -> tuple[list, list[dict]]:
    """047:RF-80, RF-85 y RF-86 — las incertidumbres que cuentan y las descartadas, con su motivo.

    Con el 047f, un rol dejó «buzones» como incertidumbre cuando la acción dice «construir 2 buzones»: la acción es lo
    que se revisa (RF-46) y fija esa cantidad. Solo se descarta una incertidumbre que es únicamente el nombre de un
    campo de la propuesta cuyo valor está en la acción; si el valor solo está en una evidencia, se mantiene, porque la
    evidencia puede ser de otro elemento.
    """
    quedan, descartadas = [], []
    accion = propuesta.get(ACCION) if isinstance(propuesta, dict) else None
    for texto in incertidumbres:
        clave = _normal(texto).strip(' `"\'«».:')
        valor = _del_campo(clave, propuesta) if clave and ' ' not in clave else None
        if valor is not None and isinstance(accion, str) and _aparece(valor, accion):
            descartadas.append({'entrada': texto, 'motivo': f'la acción fija {clave} ({valor}): no es una incertidumbre'})
        elif clave and clave in comprobados:
            # 047:RF-85: con el 047g, el LLM dejaba «coste_usd» como duda en propuestas sanas cuyo coste el código ya
            # había calculado con la evidencia y cuadraba (RF-77); la contradicción sobre ese campo ya se descartaba.
            descartadas.append({'entrada': texto,
                                'motivo': f'el código comprobó {clave} con la evidencia y cuadra: no es una incertidumbre'})
        elif isinstance(accion, str) and _repite_la_accion(clave, accion):
            # 047:RF-86: con el 047g, un rol copiaba la acción entera como incertidumbre; la acción es lo que se revisa
            # (RF-46), así que repetirla no dice qué falta saber.
            descartadas.append({'entrada': texto, 'motivo': 'repite la acción que se revisa: no es una incertidumbre'})
        else:
            quedan.append(texto)
    return quedan, descartadas


def _repite_la_accion(texto: str, accion: str) -> bool:
    """047:RF-86: la duda es la acción, o un trozo suyo de tres palabras o más, sin nada más."""
    palabras = re.findall(r'\w+', texto)
    return len(palabras) >= 3 and ' '.join(palabras) in ' '.join(re.findall(r'\w+', _normal(accion)))


def filtrar_contradicciones(entradas, propuesta=None, evidencia=None, comprobados=()) -> tuple[list, list[dict]]:
    """047:RF-48 a RF-83 — las contradicciones que cuentan y las descartadas, con su motivo.

    Con ``propuesta`` y ``evidencia`` comprueba además que cada valor esté donde dice; si el campo es de la propuesta,
    su valor es el de la propuesta. Una entrada en texto libre (formato anterior) se interpreta como «X vs Y» y, si no
    se puede, se mantiene. Una entrada con otra forma lanza ``ValueError``: el dictamen no es válido. ``comprobados``
    son los campos que el código ya comprobó con la evidencia y cuadran (RF-79).
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
            motivo, _calculo = _motivo(campo, valor_p, valor_e, None, propuesta, evidencia, comprobados)
            (descartadas.append({'entrada': entrada, 'motivo': motivo}) if motivo else quedan.append(entrada))
            continue
        if not _valida(entrada):
            raise ValueError('contradicción sin campo, valor_propuesta, valor_evidencia y fuente válidos')
        entrada = deepcopy(entrada)
        propio = _del_campo(entrada['campo'], propuesta)
        if propio is not None and not valores_coinciden(propio, entrada['valor_propuesta']):
            entrada['valor_propuesta_devuelto'] = entrada['valor_propuesta']
            entrada['valor_propuesta'] = propio
        motivo, calculo = _motivo(entrada['campo'], entrada['valor_propuesta'], entrada['valor_evidencia'],
                                  str(entrada['fuente']), propuesta, evidencia, comprobados)
        entrada.update(calculo)
        (descartadas.append({'entrada': entrada, 'motivo': motivo}) if motivo else quedan.append(entrada))
    return quedan, descartadas


#: 047:RF-77: un importe en dólares de un fragmento: «14 500 USD», «US$ 52», «$6,950», «USD 14.250».
_IMPORTE = re.compile(r'(?:(?P<pre>us\$|usd|\$)\s*)?(?<![\d.,])(?P<num>\d{1,3}(?: \d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*)'
                      r'(?!\d)(?(pre)|\s*(?:usd|us\$|d[oó]lares)\b)')
CAMPOS_DE_COSTE = ('coste_usd', 'costo_usd')


def _partidas_de(importes: list[tuple[set, str]]) -> list[tuple[set, str]]:
    """Las partidas de un fragmento: si un importe es la suma de los demás («12 × 900 USD c/u: 10 800 USD»), es su
    total y cuenta solo él; si no, cuentan todos."""
    if len(importes) < 2:
        return importes
    for i, (lecturas, texto) in enumerate(importes):
        resto = [p[0] for j, p in enumerate(importes) if j != i]
        sumas = {sum(c) for c in itertools.islice(itertools.product(*resto), _MAX_LECTURAS)}
        if any(_cerca(x, y, TOLERANCIA_RELATIVA) for x in lecturas for y in sumas):
            return [(lecturas, f'{texto}, total de sus partidas')]
    return importes


#: 047:RF-95: «… por banco», «… cada reconectador»: el precio va por la pieza que se nombra tras «por» o «cada».
_POR_PIEZA = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?(?:por|cada)\s+(?:(?:el|la|un|una)\s+)?([a-záéíóúñ]{4,})\b')


def _por_lo_contado(resto: str, propuesta) -> float | None:
    """047:RF-95, RF-96 — si la cifra va «por» o «cada» una pieza que la acción cuenta («2 bancos»), esa cantidad.

    Con el 047l, «US$ 8 800 por banco» y «instalar 2 bancos…» se leía como un total de 8 800 frente a 17 600; la lista
    fija de palabras de RF-76 («por unidad», «por equipo»…) no puede traer cada pieza de una red. Con el 047m, «USD 2 600
    por banco» y «montar 3 bancos … de 150 kvar» no se comprobaba: la cantidad es la de la pieza nombrada, no otra cifra.
    """
    m = _POR_PIEZA.match(resto)
    accion = propuesta.get(ACCION) if isinstance(propuesta, dict) else None
    if not m or not isinstance(accion, str):
        return None
    cantidades = {float(x[1]) for x in re.finditer(r'(?<![\w.,])(\d+)\s+([a-záéíóúñ]{4,})', _normal(accion))
                  if _raiz(x[2]) == _raiz(m[1])}
    return cantidades.pop() if len(cantidades) == 1 else None


#: 047:RF-102: la evidencia que dice que algo no tiene coste.
_SIN_COSTE = re.compile(r'\bsin\s+(?:ning[uú]n\s+)?(?:gasto|coste|costo|materiales|compra|costo\s+de\s+obra)\b|'
                        r'\bno\s+(?:necesita|requiere|tiene|lleva)\s+(?:ning[uú]n\s+)?(?:materiales|coste|costo|gasto)\b')


def comprobar_coste(propuesta, evidencia) -> list[dict]:
    """047:RF-77 — el coste de la propuesta frente al que sale de la evidencia, calculado sin el LLM.

    Con un único total explícito («… en total»), ese; si no, la suma de las partidas: cada importe total, cada precio
    por unidad por la cantidad anclada y cada precio por km por la longitud anclada. Si falta una cantidad, hay varios
    totales explícitos o la propuesta no tiene ``coste_usd`` numérico, no comprueba nada (lista vacía).
    """
    if not isinstance(propuesta, dict) or not isinstance(evidencia, dict):
        return []
    campo = next((c for c in CAMPOS_DE_COSTE if c in propuesta), None)
    coste = propuesta.get(campo) if campo else None
    if not isinstance(coste, (int, float)) or isinstance(coste, bool):
        return []
    importes = []
    for fuente, registro in evidencia.items():
        fragmento = registro.get('fragmento') if isinstance(registro, dict) else None
        if not isinstance(fragmento, str):
            continue
        t = _IDENTIFICADOR.sub(lambda m: ' ' * len(m[0]), _normal(fragmento))
        for m in _IMPORTE.finditer(t):
            lecturas = _candidatos(m['num'])
            if not lecturas:
                continue
            tipo = 'en_total' if _EN_TOTAL.match(t[m.end():m.end() + 40]) else _tipo_de_cifra(t, m.end())
            piezas = _por_lo_contado(t[m.end():m.end() + 60], propuesta) if tipo in ('total', 'unidad') else None
            if piezas is not None:
                tipo = f'pieza:{piezas:g}'
            importes.append((fuente, m['num'], lecturas, tipo, fragmento))
    if not importes:
        # 047:RF-102: un coste 0 lo respalda la evidencia que dice que no lo hay («sin materiales», «sin costo», «la
        # maniobra no necesita materiales»); sin eso queda sin comprobar, como cualquier coste sin importe.
        sin_coste = next((f for f, r in evidencia.items() if isinstance(r, dict) and isinstance(r.get('fragmento'), str)
                          and _SIN_COSTE.search(_normal(r['fragmento']))), None)
        if coste == 0 and sin_coste is not None:
            return [{'campo': campo, 'valor_propuesta': coste, 'valor_calculado': 0.0,
                     'calculo': f'{sin_coste} dice que no tiene coste', 'fuentes': [sin_coste], 'coincide': True,
                     'origen': 'codigo'}]
        return []
    totales = [i for i in importes if i[3] == 'en_total']
    if len(totales) > 1:
        return []
    if totales:
        fuente, cifra, lecturas, _t, _f = totales[0]
        partes = [(lecturas, f'{cifra} ({fuente}, en total)')]
    else:
        partes = []
        for fuente in dict.fromkeys(i[0] for i in importes):
            del_fragmento = []
            for _f, cifra, lecturas, tipo, fragmento in (i for i in importes if i[0] == fuente):
                if tipo == 'total':
                    del_fragmento.append((lecturas, f'{cifra} ({fuente})'))
                    continue
                factor = (float(tipo[6:]) if tipo.startswith('pieza:') else longitud_anclada(propuesta) if tipo == 'km'
                          else cantidad_anclada(propuesta, fragmento))
                if factor is None:
                    return []
                base = 'unidad' if tipo.startswith('pieza:') else tipo
                del_fragmento.append(({v * factor for v in lecturas}, f'{factor:g} × {cifra} ({fuente}, por {base})'))
            partes.extend(_partidas_de(del_fragmento))
    esperados = {sum(c) for c in itertools.islice(itertools.product(*(p[0] for p in partes)), _MAX_LECTURAS)}
    cercano = min(esperados, key=lambda v: abs(v - coste))
    return [{'campo': campo, 'valor_propuesta': coste, 'valor_calculado': round(cercano, 6),
             'calculo': ' + '.join(p[1] for p in partes), 'fuentes': sorted({i[0] for i in importes}),
             'coincide': any(_cerca(float(coste), v, TOLERANCIA_RELATIVA) for v in esperados), 'origen': 'codigo'}]


#: 047:RF-88: frases de la evidencia que prohíben algo.
#: 047:RF-93: con el 047j (2026-11-23), «las reglas de seguridad no permiten trabajar … sin puesta a tierra» no se leía
#: como prohibición; «no permite(n)», «no autoriza(n)», «no admite(n)», «queda prohibido», «está vedado», «en ningún caso»
#: y «jamás» también lo son.
_PROHIBE = re.compile(r'\b(?:proh[ií]b\w*|no se permite|no est[aá] permitid[oa]|est[aá] proh[ií]bid[oa]|no debe|no se debe|'
                      r'no puede|no se puede|nunca se|no (?:se )?permit\w*|no (?:se )?autoriz\w*|no (?:se )?admit\w*|'
                      r'quedan? proh[ií]bid\w*|est[aá]n? vedad\w*|en ning[uú]n caso|jam[aá]s|'
                      # 047:RF-94: con el 047k (2026-11-24), «ninguna cuadrilla está autorizada a maniobrar con carga…»
                      # no se leía: una negación («ningún», «nadie», «no») con un participio de permiso también prohíbe.
                      r'(?:ning[uú]n[oa]?|nadie)\b[^.;:]{0,60}?\b(?:est[aá]n?|quedan?|es|son|se encuentran?)\s+'
                      r'(?:autorizad|habilitad|facultad|permitid|acreditad)\w*|'
                      r'no\s+(?:est[aá]n?|quedan?|es|son|se encuentran?)\s+(?:autorizad|habilitad|facultad|acreditad)\w*)\b')
#: 047:RF-93: lo prohibido es hacerlo «sin» algo; la acción que lo hace con ello no está prohibida.
_SIN = re.compile(r'\bsin\s+(?:(?:el|la|los|las|su|sus)\s+)?([a-záéíóúñ]{3,})')
#: 047:RF-97: una obligación previa («la norma exige X antes de reponer…», «se debe X antes de…»). Los sistemas de
#: cumplimiento normativo clasifican cada frase por su modalidad (obligación, permiso, prohibición) con sus disparadores
#: (ComplianceNLP, arXiv 2604.23585; LEXDEMOD); aquí falta la obligación: con el 047m, el modelo aprobó en los dos modos
#: «reponer el fusible sin revisar antes la causa» frente a «exige … despejar la causa … antes de reponer».
_OBLIGA = re.compile(r'\b(?:exigen?|requieren?|obligan?|es obligatori[oa]|son obligatori[oa]s|se debe|deben?|tienen? que|'
                     r'hay que|ha de|han de|es necesario|es imprescindible)\b')
_ANTES_DE = re.compile(r'\bantes\s+de\s+([a-záéíóúñ]{2,}(?:ar|er|ir))(?:lo|la|los|las|le|les|se)?\b')
#: Un infinitivo, con un pronombre pegado o no («abrirlo», «trabajar»).
_INFINITIVO = re.compile(r'\b([a-záéíóúñ]{2,}(?:ar|er|ir))(?:lo|la|los|las|le|les|se)?\b')


#: 047:RF-89: una cifra de la evidencia que es un límite o una norma no respalda el dato de la propuesta.
_LIMITE = re.compile(r'\b(?:l[ií]mite|admisible|norma|m[aá]ximo permitido|m[ií]nimo permitido|tolerancia)\b')


def _en_un_fragmento(valor, evidencia) -> str | None:
    """047:RF-89: la fuente cuyo fragmento trae ``valor`` fuera de una cláusula de límite, o None."""
    for fuente, registro in evidencia.items():
        fragmento = registro.get('fragmento') if isinstance(registro, dict) else None
        if not isinstance(fragmento, str):
            continue
        for clausula in re.split(r'[;:]\s+|,\s+(?=[a-záéíóúñ])', fragmento):
            if not _LIMITE.search(_normal(clausula)) and _aparece(valor, clausula):
                return fuente
    return None


def _es_cantidad(campo: str) -> bool:
    partes = [x for x in re.split(r'[_\W]+', _normal(campo)) if x]
    return bool(partes) and not any(x in _UNIDADES for x in partes) and not any(
        x.startswith(_RAICES_DE_MAGNITUD) for x in partes)


def comprobar_datos(propuesta, evidencia) -> list[dict]:
    """047:RF-89 — los datos de la propuesta que el código respalda sin el LLM.

    Con el 047h (2026-11-23), en propuestas sanas el LLM dudaba de «cargabilidad_final_pct» (63 % en la evidencia),
    enfrentaba «tension_final_pu» 0,99 con el 1,03 del valle del mismo fragmento y pedía «cuántos reconectadores hacen
    falta» cuando la acción dice 2. Un dato cuenta como respaldado si es una cantidad de elementos que la acción fija o
    si su cifra está en un fragmento, fuera de una cláusula de límite o de norma. Lo que no se respalda así no se
    comprueba aquí (lo sigue revisando el LLM): faltar en la evidencia no es una contradicción.
    """
    if not isinstance(propuesta, dict) or not isinstance(evidencia, dict):
        return []
    accion = propuesta.get(ACCION) if isinstance(propuesta.get(ACCION), str) else ''
    salida = []
    for campo, valor in propuesta.items():
        if campo in (ACCION, *CAMPOS_DE_COSTE) or isinstance(valor, bool) or not isinstance(valor, (int, float)):
            continue
        if _es_cantidad(campo) and float(valor).is_integer() and _aparece(valor, accion):
            salida.append({'campo': campo, 'valor_propuesta': valor, 'valor_calculado': valor,
                           'calculo': 'la acción fija la cantidad', 'fuentes': [], 'coincide': True, 'origen': 'codigo'})
            continue
        fuente = _en_un_fragmento(valor, evidencia)
        if fuente is not None:
            salida.append({'campo': campo, 'valor_propuesta': valor, 'valor_calculado': valor,
                           'calculo': f'la cifra está en {fuente}', 'fuentes': [fuente], 'coincide': True,
                           'origen': 'codigo'})
    return salida


def comprobar_magnitudes(propuesta, evidencia) -> list[dict]:
    """047:RF-98, RF-101 — los resultados físicos de la propuesta que la evidencia contradice o que nada respalda.

    Aparte de ``comprobar_datos`` (lo que la evidencia respalda): aquí solo hay lo que no cuadra. Solo con evidencia en
    texto: si ningún fragmento trae texto (un fichero con su huella), el código no puede leerla y no decide nada.
    """
    if not isinstance(propuesta, dict) or not isinstance(evidencia, dict):
        return []
    if not any(isinstance(r, dict) and isinstance(r.get('fragmento'), str) and r['fragmento'].strip()
               for r in evidencia.values()):
        return []
    accion = propuesta.get(ACCION) if isinstance(propuesta.get(ACCION), str) else ''
    respaldados = {c['campo'] for c in comprobar_datos(propuesta, evidencia)}
    salida = []
    for campo, valor in propuesta.items():
        if (campo in (ACCION, *CAMPOS_DE_COSTE) or campo in respaldados or isinstance(valor, bool)
                or not isinstance(valor, (int, float))):
            continue
        distinto = _magnitud_del_elemento(campo, valor, evidencia, accion)
        if distinto is not None:
            salida.append({'campo': campo, 'valor_propuesta': valor, 'valor_calculado': distinto[1],
                           'calculo': f'{distinto[0]} da {distinto[1]:g} {distinto[2]} para el mismo elemento',
                           'fuentes': [distinto[0]], 'coincide': False, 'origen': 'codigo'})
            continue
        # 047:RF-101: con el 047, «reduccion_perdidas_kw: 120» no estaba en ninguna evidencia y el modelo lo aprobó. Un
        # resultado físico que nada respalda ni contradice no se aprueba: queda sin fuente y lo ve el operador.
        if re.search(r'_(?:kw|kva|kvar|mw|mva|pu|pct|porcentaje|a|ka|kv)$', campo.casefold()) and not _es_cantidad(campo):
            salida.append({'campo': campo, 'valor_propuesta': valor, 'valor_calculado': None,
                           'calculo': 'ningún fragmento de la evidencia da este resultado', 'fuentes': [],
                           'coincide': False, 'origen': 'codigo'})
    return salida


#: 047:RF-98: una cláusula que empieza por un límite o por lo exigido («límite 100 %», «el mínimo exigido es 0,95 pu»,
#: «capacidad del conductor de 35 mm² 125 A») no es el dato del elemento.
_CLAUSULA_LIMITE = re.compile(r'\s*(?:(?:el|la|los|las|su)\s+)?(?:l[ií]mite|admisible|norma|m[aá]xim[oa]\s+(?:permitid|admisible|exigid)|'
                              r'm[ií]nim[oa]\s+(?:permitid|admisible|exigid)|m[ií]nimo exigido|tolerancia|capacidad|'
                              r'(?<=el |la )m[ií]nim[oa]\s+(?:es|son|de)|(?<=el |la )m[aá]xim[oa]\s+(?:es|son|de))\b')
#: 047:RF-98: la unidad de un campo por su sufijo, el patrón de su cifra en la evidencia y el factor a la unidad del campo.
_UNIDADES_DE_CAMPO = (
    (re.compile(r'_(?:pct|porcentaje)$'), r'(\d+(?:[.,]\d+)?)\s*%', {'': 1.0}, '%'),
    (re.compile(r'_pu$'), r'(\d+[.,]\d+)\s*p\.?\s?u\b', {'': 1.0}, 'pu'),
    (re.compile(r'_ka$'), r'(\d+(?:[.,]\d+)?)\s*(k)a\b', {'k': 1.0}, 'kA'),
    (re.compile(r'_a$'), r'(\d+(?:[.,]\d+)?)\s*()a\b', {'': 1.0}, 'A'),
    (re.compile(r'_kw$'), r'(\d+(?:[.,]\d+)?)\s*([km])w\b', {'k': 1.0, 'm': 1000.0}, 'kW'),
    (re.compile(r'_kva$'), r'(\d+(?:[.,]\d+)?)\s*([km])va\b', {'k': 1.0, 'm': 1000.0}, 'kVA'),
    (re.compile(r'_mw$'), r'(\d+(?:[.,]\d+)?)\s*([km])w\b', {'m': 1.0, 'k': 0.001}, 'MW'),
    (re.compile(r'^usuarios'), r'(\d{1,3}(?:[ .]\d{3})*|\d+)\s*()usuarios\b', {'': 1.0}, 'usuarios'),
)


def _magnitud_del_elemento(campo: str, valor, evidencia, accion: str = '') -> tuple[str, float, str] | None:
    """047:RF-98 — la cifra que la evidencia da al mismo elemento en la unidad del campo, si es otra.

    Con el 047m, «carga_v3318_pct: 64» frente a «la SED V-3318 de 50 kVA trabaja al 141 %», y «cargabilidad_k619_pct:
    79» frente a «la cabecera del K619 llega al 112 %»: el modelo aprobó los dos en ambos modos. Vale para %, pu, kA, A,
    kW, kVA, MW y usuarios. El elemento es el que nombra el campo o, si no nombra ninguno, el de la acción. Solo decide si
    el fragmento nombra ese elemento y, fuera de las cláusulas de límite, da una única cifra de esa unidad.
    """
    regla = next((r for r in _UNIDADES_DE_CAMPO if r[0].search(campo.casefold())), None)
    if regla is None:
        return None
    _sufijo, patron, factores, unidad = regla
    propios = {p for p in campo.casefold().split('_') if re.fullmatch(r'[a-z]+\d+', p)}
    if not propios:
        propios = _elementos(accion)
    if not propios:
        return None
    for fuente, registro in evidencia.items():
        fragmento = registro.get('fragmento') if isinstance(registro, dict) else None
        if not isinstance(fragmento, str):
            continue
        t = _normal(fragmento)
        if not propios & _elementos(t):
            continue
        clausulas = [c for c in re.split(r'[;:]\s+|,\s+', t) if not _CLAUSULA_LIMITE.match(c)]
        cifras = set()
        for cl in clausulas:
            for m in re.finditer(patron, cl):
                numero = m[1].replace(' ', '').replace('.', '') if unidad == 'usuarios' else m[1].replace(',', '.')
                prefijo = m[2] if m.lastindex and m.lastindex >= 2 else ''
                if prefijo in factores:
                    cifras.add(round(float(numero) * factores[prefijo], 9))
        if len(cifras) == 1:
            otra = cifras.pop()
            if not _cerca(float(valor), otra, TOLERANCIA_RELATIVA):
                return fuente, otra, unidad
    return None


def _prefijo(identificador: str) -> str:
    return re.match(r'[a-záéíóúñ]+', identificador)[0]


def comprobar_elementos(propuesta, evidencia) -> list[dict]:
    """047:RF-90 — la evidencia que es de otro elemento del mismo tipo que el de la acción, hallada sin el LLM.

    Con el 047h, la medición de la SED S-2209 respaldaba subir el tap de la S-2290; el LLM no lo vio y la revisión solo
    se bloqueó por una duda sin relación. Cuenta si un fragmento nombra un elemento con el mismo prefijo que uno de la
    acción («s-2209» frente a «s-2290») y no nombra ninguno de la acción con ese prefijo. Queda como no coincidente.
    """
    if not isinstance(propuesta, dict) or not isinstance(evidencia, dict) or not isinstance(propuesta.get(ACCION), str):
        return []
    propios = set(_IDENTIFICADOR.findall(_normal(propuesta[ACCION])))
    prefijos = {_prefijo(i) for i in propios}
    salida = []
    for fuente, registro in evidencia.items():
        fragmento = registro.get('fragmento') if isinstance(registro, dict) else None
        if not isinstance(fragmento, str):
            continue
        nombrados = set(_IDENTIFICADOR.findall(_normal(fragmento)))
        for prefijo in sorted(prefijos):
            ajenos = sorted(i for i in nombrados - propios if _prefijo(i) == prefijo)
            if ajenos and not any(_prefijo(i) == prefijo for i in nombrados & propios):
                salida.append({'campo': ACCION, 'valor_propuesta': propuesta[ACCION],
                               'valor_calculado': fragmento.strip(),
                               'calculo': f'{fuente} es de {", ".join(ajenos)}, no del elemento de la acción',
                               'fuentes': [fuente], 'coincide': False, 'origen': 'codigo'})
                break
    return salida


def comprobar_prohibiciones(propuesta, evidencia) -> list[dict]:
    """047:RF-88 — la acción que una evidencia prohíbe, hallada por el código y sin el LLM.

    Con el 047g, en el modo equipo ningún rol vio que el procedimiento prohibía la maniobra de la acción, aunque el
    encargo lo pide (RF-82). Cuenta si una frase de la evidencia prohíbe un verbo (en infinitivo, con pronombre o no) y
    la acción lleva ese mismo verbo; queda en ``comprobaciones_del_codigo`` como no coincidente, así que la revisión no
    se aprueba. Una prohibición de otro verbo no cuenta.
    """
    if not isinstance(propuesta, dict) or not isinstance(evidencia, dict):
        return []
    accion = propuesta.get(ACCION)
    if not isinstance(accion, str):
        return []
    verbos = {_raiz(m[1]) for m in _INFINITIVO.finditer(_normal(accion))}
    salida = []
    for fuente, registro in evidencia.items():
        fragmento = registro.get('fragmento') if isinstance(registro, dict) else None
        if not isinstance(fragmento, str):
            continue
        for frase in re.split(r'(?<=[.;])\s+', fragmento):
            m = _PROHIBE.search(_normal(frase))
            if not m:
                continue
            prohibido = _normal(frase)[m.end():]
            comunes = verbos & {_raiz(x[1]) for x in _INFINITIVO.finditer(prohibido)}
            # 047:RF-99: «prohíbe el trabajo en caliente»: lo prohibido es el sustantivo del verbo de la acción.
            # El tema léxico, no las 5 primeras letras: «la poda» y «podar» comparten «pod-».
            nombre = re.match(r'\s*(?:(?:el|la|los|las|un|una|todo|toda|cualquier)\s+)?([a-záéíóúñ]{4,})', prohibido)
            temas = {_tema(m[1]) for m in _INFINITIVO.finditer(_normal(accion))}
            if nombre and len(_tema(nombre[1])) >= 3 and _tema(nombre[1]) in temas:
                comunes = comunes | {_tema(nombre[1])}
            sin = _SIN.search(prohibido)
            if comunes and sin and not re.search(r'\bsin\s+(?:(?:el|la|los|las|su|sus)\s+)?' + re.escape(sin[1]), _normal(accion)):
                # 047:RF-93: «no se permite trabajar sin puesta a tierra» no prohíbe trabajar con ella.
                continue
            if comunes:
                salida.append({'campo': ACCION, 'valor_propuesta': accion, 'valor_calculado': frase.strip(),
                               'calculo': f'{fuente} prohíbe lo que la acción hace ({", ".join(sorted(comunes))}…)',
                               'fuentes': [fuente], 'coincide': False, 'origen': 'codigo'})
                break
        else:
            sin_salvaguarda = _salvaguarda_ausente(fragmento, accion) or _agente_no_autorizado(fragmento, accion)
            if sin_salvaguarda:
                salida.append({'campo': ACCION, 'valor_propuesta': accion, 'valor_calculado': sin_salvaguarda,
                               'calculo': f'{fuente} dice que al elemento que la acción maniobra le falta una salvaguarda',
                               'fuentes': [fuente], 'coincide': False, 'origen': 'codigo'})
                continue
            superado = _limite_superado(fragmento, accion)
            if superado:
                salida.append({'campo': ACCION, 'valor_propuesta': accion, 'valor_calculado': superado[0],
                               'calculo': f'{fuente} pone un límite de {superado[1]:g} {superado[3]} y la acción llega a '
                                          f'{superado[2]:g} {superado[3]}', 'fuentes': [fuente], 'coincide': False,
                               'origen': 'codigo'})
                continue
            incumplida = _obligacion_previa_incumplida(fragmento, accion, verbos)
            if incumplida:
                salida.append({'campo': ACCION, 'valor_propuesta': accion, 'valor_calculado': incumplida[0],
                               'calculo': f'{fuente} exige {incumplida[1]} antes de lo que la acción hace, y la acción lo '
                                          f'hace sin ello', 'fuentes': [fuente], 'coincide': False, 'origen': 'codigo'})
    return salida


#: 047:RF-100: lo que protege una maniobra o un corte y la evidencia dice que falta («sin seccionador ni interruptor»,
#: «sin enlace con otro alimentador», «queda sin enlace de respaldo», «sin grupo electrógeno»).
_SIN_SALVAGUARDA = re.compile(r'\bsin\s+(?:(?:un|una|el|la|ning[uú]n[oa]?)\s+)?(?:enlace|respaldo|seccionador|interruptor|'
                              r'reconectador|protecci[oó]n|grupo\s+electr[oó]geno|generaci[oó]n\s+propia|puesta\s+a\s+tierra|'
                              r'transferencia|alimentaci[oó]n\s+alternativa)\b')
#: 047:RF-100: verbos de maniobra, corte o trabajo sobre la red.
_MANIOBRA = re.compile(r'\b(?:abr\w*|cerr\w*|transfer\w*|traspas\w*|desenergiz\w*|cort\w*|interrump\w*|desconect\w*|'
                       r'manio\w*|aisl\w*|trabaj\w*|reemplaz\w*|cambi\w*)\b')


#: 047:RF-100: un permiso restringido a un agente («solo el centro de control puede ordenar la apertura…»): para los
#: demás es una prohibición (modalidad PERMISSION con su agente, como en LEXDEMOD).
_SOLO_AGENTE = re.compile(r'\b(?:solo|s[oó]lo|[uú]nicamente|exclusivamente)\s+(?:(?:el|la|los|las)\s+)?(.{3,60}?)\s+'
                          r'(?:puede|pueden|podr[aá]n?|est[aá]n?\s+(?:autorizad|habilitad|facultad)\w*(?:\s+(?:a|para))?)\s+([^.;]{3,120})')
_VACIAS = {'de', 'del', 'la', 'las', 'los', 'el', 'en', 'con', 'por', 'para', 'que', 'una', 'uno', 'unos', 'unas', 'sus', 'ordenar'}


def _palabras(texto: str) -> set[str]:
    return {_tema(p) for p in re.findall(r'[a-záéíóúñ]{4,}', texto)} - {_tema(v) for v in _VACIAS}


def _agente_no_autorizado(fragmento: str, accion: str) -> str | None:
    """047:RF-100 — la frase que solo permite algo a un agente, si la acción trata de lo mismo y no la hace ese agente.

    Con el 047l, «solo el centro de control puede ordenar la apertura de los reconectadores» frente a «que la cuadrilla de
    campo abra el reconectador R-215»: lo permitido y la acción comparten su objeto (el reconectador) y la acción no nombra
    al agente autorizado. Si la acción lo nombra, o no comparte nada con lo permitido, no decide.
    """
    propia = _normal(accion)
    de_la_accion = _palabras(propia)
    for frase in re.split(r'(?<=[.;])\s+', fragmento):
        m = _SOLO_AGENTE.search(_normal(frase))
        if not m:
            continue
        agente, permitido = _palabras(m[1]), _palabras(m[2])
        if agente and permitido & de_la_accion and not agente & de_la_accion:
            return frase.strip()
    return None


def _salvaguarda_ausente(fragmento: str, accion: str) -> str | None:
    """047:RF-100 — la frase que dice que al elemento que la acción maniobra le falta una salvaguarda.

    Con el 047b, «el nodo N45 es un empalme de conductores, sin seccionador ni interruptor» frente a «transferir el ramal
    R4 … abriendo y cerrando en el nodo N45»; con el 047d, «aguas abajo de S40 quedan 1 350 usuarios, sin enlace con otro
    alimentador» frente a «abrir el seccionador S40 durante 3 h». Cuenta si la frase nombra un elemento de la acción y la
    acción lo maniobra, lo corta o trabaja en él; no aprueba sola: lo ve el operador.
    """
    propia = _normal(accion)
    if not _MANIOBRA.search(propia):
        return None
    propios = _elementos(propia)
    for frase in re.split(r'(?<=[.;])\s+', fragmento):
        t = _normal(frase)
        if _SIN_SALVAGUARDA.search(t) and propios & _elementos(t):
            return frase.strip()
    return None


#: 047:RF-99: una cantidad con su unidad, llevada a una unidad base por magnitud: el tiempo a minutos, la corriente a
#: amperios, la potencia a kW o kVA. Una sola lectura para todas las cotas, en lugar de una regla por redacción: con el
#: 047n, «el contrato admite como máximo 2 horas de corte» se escapaba a las dos formas que había.
_CANTIDAD = re.compile(r'(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(horas?|h|minutos?|min|ka|a|kw|mw|kva|mva|kv|%|pu|k)(?![\w])')
_BASE = {'hora': ('min', 60.0), 'horas': ('min', 60.0), 'h': ('min', 60.0), 'minuto': ('min', 1.0),
         'minutos': ('min', 1.0), 'min': ('min', 1.0), 'ka': ('A', 1000.0), 'a': ('A', 1.0), 'kw': ('kW', 1.0),
         'mw': ('kW', 1000.0), 'kva': ('kVA', 1.0), 'mva': ('kVA', 1000.0), 'kv': ('kV', 1.0), '%': ('%', 1.0),
         'pu': ('pu', 1.0), 'k': ('K', 1.0)}
#: 047:RF-99: lo que pone una cota superior o inferior justo antes de la cantidad, se escriba como se escriba.
_COTA_SUPERIOR = re.compile(
    r'\b(?:como\s+m[aá]ximo|(?:un\s+)?m[aá]ximo\s+de|a\s+lo\s+sumo|no\s+m[aá]s\s+de|no\s+mayor\s+(?:de|que|a)|tope\s+de|'
    r'(?:un\s+)?l[ií]mite\s+de|hasta\s+un\s+m[aá]ximo\s+de|'
    r'no\s+(?:puede|pueden|debe|deben|podr[aá]n?|debe\s+de)\s+(?:pasar\s+de|superar|exceder|sobrepasar|ser\s+mayor\s+(?:que|de)|durar\s+m[aá]s\s+de))'
    r'\s+(?:(?:en|de|a|el|la|los|las|un|una)\s+){0,2}$')
_COTA_INFERIOR = re.compile(
    r'\b(?:como\s+m[ií]nimo|(?:un\s+)?m[ií]nimo\s+de|al\s+menos|no\s+menos\s+de|no\s+inferior\s+(?:a|de)|'
    r'no\s+(?:puede|pueden|debe|deben|podr[aá]n?)\s+(?:bajar\s+de|ser\s+menor\s+(?:que|de)))\s+(?:(?:en|de|a|el|la|los|las|un|una)\s+){0,2}$')
#: «con un fusible mayor de 40 K … se pierde la coordinación»: una cota que la evidencia da por su consecuencia.
_COTA_POR_CONSECUENCIA = re.compile(r'\b(?:mayor(?:es)?|m[aá]s|superior(?:es)?)\s+(?:de|que|a)\s+$')
_CONSECUENCIA = re.compile(r'\b(?:se\s+pierde|pierde|se\s+abre|abre|dispara|falla|se\s+da[nñ]a|no\s+coordina|no\s+cumple)\b')


def _cantidades(texto: str) -> list[tuple[float, str, int, int]]:
    """Las cantidades de un texto normalizado: (valor en la unidad base, unidad base, inicio, fin)."""
    salida = []
    for m in _CANTIDAD.finditer(texto):
        base, factor = _BASE[m[2]]
        salida.append((float(m[1].replace(',', '.')) * factor, base, m.start(), m.end()))
    return salida


def _cotas(frase: str) -> list[tuple[str, float, str]]:
    """047:RF-99 — las cotas de una frase: («max» o «min», valor en la unidad base, unidad base)."""
    t = _normal(frase)
    cotas = []
    for valor, base, inicio, fin in _cantidades(t):
        antes = t[max(0, inicio - 60):inicio]
        if _COTA_SUPERIOR.search(antes) or (_COTA_POR_CONSECUENCIA.search(antes) and _CONSECUENCIA.search(t[fin:])):
            cotas.append(('max', valor, base))
        elif _COTA_INFERIOR.search(antes):
            cotas.append(('min', valor, base))
    return cotas


def _limite_superado(fragmento: str, accion: str) -> tuple[str, float, float, str] | None:
    """047:RF-99 — la frase que pone una cota cuantitativa y la cifra de la acción, en su unidad, que la incumple.

    Con el 047b, «su interrupción programada no puede pasar de 1 h» frente a «… desenergizado durante 6 h»; con el 047c,
    «con un fusible mayor de 40 K en D12 se pierde la coordinación» frente a «de 25 K a 65 K»; con el 047n, «admite como
    máximo 2 horas de corte» frente a «durante 4 horas». Las unidades se llevan a una base (2 h son 120 min). Para una
    cota superior cuenta la mayor cifra de la acción en esa magnitud y para una inferior la menor; si la acción no tiene
    esa magnitud, no decide.
    """
    propias = _cantidades(_normal(accion))
    for frase in re.split(r'(?<=[.;])\s+', fragmento):
        for sentido, limite, base in _cotas(frase):
            cifras = [v for v, b, _i, _f in propias if b == base]
            if not cifras:
                continue
            if sentido == 'max' and max(cifras) > limite * (1 + 1e-9):
                return frase.strip(), limite, max(cifras), base
            if sentido == 'min' and min(cifras) < limite * (1 - 1e-9):
                return frase.strip(), limite, min(cifras), base
    return None


def _obligacion_previa_incumplida(fragmento: str, accion: str, verbos: set[str]) -> tuple[str, str] | None:
    """047:RF-97 — la frase que exige algo antes del verbo de la acción, si la acción lo hace «sin» eso.

    Solo decide cuando la acción lleva el verbo guardado y dice «sin» algo que comparte una palabra con lo exigido
    («sin revisar antes la causa» frente a «despejar la causa … antes de reponer»). Si la acción no dice «sin», el
    código no da por incumplida la obligación: lo decide el revisor.
    """
    propia = _normal(accion)
    sin = re.search(r'\bsin\s+(.{3,80})', propia)
    if not sin:
        return None
    lo_que_falta = {_raiz(p) for p in re.findall(r'[a-záéíóúñ]{4,}', sin[1])} - {'antes', 'despu'}
    for frase in re.split(r'(?<=[.;])\s+', fragmento):
        t = _normal(frase)
        o = _OBLIGA.search(t)
        a = _ANTES_DE.search(t, o.end()) if o else None
        if not a or _raiz(a[1]) not in verbos:
            continue
        exigido = t[o.end():a.start()]
        if lo_que_falta & {_raiz(p) for p in re.findall(r'[a-záéíóúñ]{4,}', exigido)}:
            return frase.strip(), exigido.strip(' ,')
    return None
