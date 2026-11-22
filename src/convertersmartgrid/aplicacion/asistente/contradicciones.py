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
_VERSUS = re.compile(r'\s+(?:vs\.?|versus|frente a)\s+', re.IGNORECASE)
#: 047:RF-55: lo que sigue a una cifra que es por unidad y no un total.
_POR_UNIDAD = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?(?:por\s+(?:unidad|kil[oó]metro|km|metro|poste|cada)\b|c/u\b|'
                         r'cada\s+un[oa]\b|unitari[oa]|/\s*(?:km|u|m|unidad)\b)')


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
_POR_KM = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?(?:por\s+(?:kil[oó]metro|km)\b|/\s*km\b)')
_EN_TOTAL = re.compile(r'^\s*(?:[a-z$.]+\s*){0,2}?en\s+total\b')
#: Un campo de la propuesta que es una magnitud, no una cantidad de piezas.
_MAGNITUD_DE_CAMPO = re.compile(r'(?:_(?:pct|pu|a|kw|kva|kvar|mw|mva|usd|ohm|km|h|kv|v|m)$)|^(?:coste|costo)|_final|carga')


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
            if _raiz(m[2]) in contexto:
                valores.add(float(m[1]))
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


def _motivo(campo, valor_p, valor_e, fuente, propuesta, evidencia) -> tuple[str | None, dict]:
    """Por qué no cuenta (o ``None`` si cuenta) y lo que el código calculó (RF-49, RF-53, RF-55, RF-56, RF-75, RF-76)."""
    if _clave(campo) == ACCION and (_leer(valor_p) is None or _leer(valor_e) is None):
        return 'la acción no es un dato: solo cuenta una cifra suya distinta de la de la evidencia', {}
    if propuesta is not None and _del_campo(campo, propuesta) is None and not _aparece(valor_p, texto_de(propuesta)):
        return f'no fundada: «{valor_p}» no está en la propuesta', {}
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


def filtrar_contradicciones(entradas, propuesta=None, evidencia=None) -> tuple[list, list[dict]]:
    """047:RF-48 a RF-78 — las contradicciones que cuentan y las descartadas, con su motivo.

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
            motivo, _calculo = _motivo(campo, valor_p, valor_e, None, propuesta, evidencia)
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
                                  str(entrada['fuente']), propuesta, evidencia)
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
            importes.append((fuente, m['num'], lecturas, tipo, fragmento))
    if not importes:
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
                factor = longitud_anclada(propuesta) if tipo == 'km' else cantidad_anclada(propuesta, fragmento)
                if factor is None:
                    return []
                del_fragmento.append(({v * factor for v in lecturas}, f'{factor:g} × {cifra} ({fuente}, por {tipo})'))
            partes.extend(_partidas_de(del_fragmento))
    esperados = {sum(c) for c in itertools.islice(itertools.product(*(p[0] for p in partes)), _MAX_LECTURAS)}
    cercano = min(esperados, key=lambda v: abs(v - coste))
    return [{'campo': campo, 'valor_propuesta': coste, 'valor_calculado': round(cercano, 6),
             'calculo': ' + '.join(p[1] for p in partes), 'fuentes': sorted({i[0] for i in importes}),
             'coincide': any(_cerca(float(coste), v, TOLERANCIA_RELATIVA) for v in esperados), 'origen': 'codigo'}]
