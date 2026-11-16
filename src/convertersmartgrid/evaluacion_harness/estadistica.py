"""Estadística común de la evaluación final (044:RF-12): un solo sitio para los contrastes de todos los bloques.

Antes de la 1.0 cada evaluación traía su cuenta: Wilson en el intérprete (069:RF-37), McNemar escrito a mano en la puerta
de no regresión (069:RF-38), Holm en el RAG (047) y bootstrap en cuatro módulos; Diebold-Mariano, Wilcoxon con biserial,
TOST, Bland-Altman, kappa y alfa no estaban en ninguno (plan de la evaluación final, §0.6). Para que la tesis y el informe
de la versión digan lo mismo, cada bloque toma sus contrastes de aquí, y cada función se prueba contra un valor publicado
(``tests/test_evaluacion_estadistica.py``). Solo usa la biblioteca estándar y, dentro de las funciones que necesitan la
distribución t, scipy: importar el módulo no carga nada pesado.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence
from statistics import NormalDist, fmean

#: Nivel de confianza por defecto de los intervalos.
CONFIANZA = 0.95


def _z(confianza: float) -> float:
    return NormalDist().inv_cdf(1 - (1 - confianza) / 2)


def _finitos(valores: Sequence[float], nombre: str) -> list[float]:
    salida = [float(v) for v in valores]
    if not all(math.isfinite(v) for v in salida):
        raise ValueError(f'{nombre}: hay valores no finitos')
    return salida


def _pares(a: Sequence[float], b: Sequence[float], minimo: int = 2) -> list[float]:
    a, b = _finitos(a, 'a'), _finitos(b, 'b')
    if len(a) != len(b):
        raise ValueError(f'la comparación es pareada: {len(a)} frente a {len(b)} observaciones')
    if len(a) < minimo:
        raise ValueError(f'hacen falta al menos {minimo} pares; hay {len(a)}')
    return [x - y for x, y in zip(a, b)]


# --- Proporciones y comparaciones múltiples -------------------------------------------------------------------

def intervalo_wilson(aciertos: int, n: int, *, confianza: float = CONFIANZA,
                     z: float | None = None) -> tuple[float, float]:
    """Intervalo de Wilson (1927) de una proporción; el de ``statsmodels proportion_confint(method='wilson')``.

    069:RF-37 lo usa con z = 1,96 para el límite inferior del acierto. Sin observaciones, el intervalo es [0, 1].
    """
    if n <= 0:
        return 0.0, 1.0
    if not 0 <= aciertos <= n:
        raise ValueError(f'aciertos fuera de rango: {aciertos} de {n}')
    z = _z(confianza) if z is None else z
    p = aciertos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    radio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centro - radio), min(1.0, centro + radio)


def ajustar_holm(p_values: Mapping[str, float]) -> dict[str, float]:
    """Ajuste de Holm (1979) para comparaciones múltiples predefinidas, como ``multipletests(method='holm')``."""
    orden = sorted(p_values, key=lambda k: p_values[k])
    ajustados: dict[str, float] = {}
    anterior = 0.0
    m = len(orden)
    for i, clave in enumerate(orden):
        valor = min(1.0, (m - i) * float(p_values[clave]))
        anterior = max(anterior, valor)
        ajustados[clave] = anterior
    return ajustados


def mcnemar_exacta(b: int, c: int, *, alternativa: str = 'dos_colas') -> float:
    """McNemar exacto: de las ``b + c`` discordantes, ``b`` sigue una binomial de p = 0,5 si los dos son iguales.

    ``alternativa='mayor'`` da P(X >= b), el ``binomtest(b, b + c, 0.5, alternative='greater')`` de scipy; la de dos
    colas suma las probabilidades no mayores que la observada, como ``binomtest`` por defecto.
    """
    n = b + c
    if b < 0 or c < 0:
        raise ValueError('recuentos negativos')
    if n == 0:
        return 1.0
    prob = [math.comb(n, k) / 2 ** n for k in range(n + 1)]
    if alternativa == 'mayor':
        return min(1.0, sum(prob[b:]))
    if alternativa == 'menor':
        return min(1.0, sum(prob[:b + 1]))
    if alternativa != 'dos_colas':
        raise ValueError(f'alternativa desconocida: {alternativa}')
    observada = prob[b] * (1 + 1e-7)
    return min(1.0, sum(p for p in prob if p <= observada))


# --- Pronósticos: Diebold-Mariano ---------------------------------------------------------------------------

def varianza_hac_media(serie: Sequence[float], retardos: int, *, nucleo: str = 'bartlett') -> float:
    """Varianza HAC de la media de ``serie``: (γ0 + 2 Σ w_j γ_j) / n, con autocovarianzas de divisor n.

    ``bartlett`` es la de Newey y West (1987), w_j = 1 - j/(L+1), siempre no negativa; ``uniforme`` (w_j = 1) es la del
    artículo original de Diebold y Mariano (1995) con h-1 retardos. Coincide con ``statsmodels`` OLS sobre una constante
    con ``cov_type='HAC'`` y ``use_correction=False``.
    """
    x = _finitos(serie, 'serie')
    n = len(x)
    if n < 2 or retardos < 0 or retardos >= n:
        raise ValueError(f'serie de {n} puntos con {retardos} retardos')
    media = fmean(x)
    d = [v - media for v in x]

    def gamma(j: int) -> float:
        return sum(d[t] * d[t - j] for t in range(j, n)) / n

    if nucleo == 'bartlett':
        pesos = [1 - j / (retardos + 1) for j in range(1, retardos + 1)]
    elif nucleo == 'uniforme':
        pesos = [1.0] * retardos
    else:
        raise ValueError(f'núcleo desconocido: {nucleo}')
    return (gamma(0) + 2 * sum(w * gamma(j) for j, w in enumerate(pesos, start=1))) / n


def diebold_mariano(perdidas_a: Sequence[float], perdidas_b: Sequence[float], *, horizonte: int = 1,
                    nucleo: str = 'uniforme', alternativa: str = 'dos_colas') -> dict:
    """Diebold-Mariano (JBES 13:253, 1995) con la corrección de Harvey, Leybourne y Newbold (IJF 13:281, 1997).

    d_t = pérdida de A - pérdida de B sobre las mismas fechas; DM = d̄ / sqrt(V̂), con V̂ la varianza HAC de d̄ con h-1
    retardos; DM* = DM · sqrt((n + 1 - 2h + h(h-1)/n) / n) se contrasta con una t de n-1 grados de libertad. Con h = 1
    es el t pareado. Si el núcleo uniforme da una varianza no positiva (puede pasar con h > 1), se usa Bartlett y se dice.
    ``alternativa='menor'`` contrasta que A pierde menos que B.
    """
    from scipy import stats

    d = _pares(perdidas_a, perdidas_b, minimo=3)
    n, h = len(d), int(horizonte)
    if h < 1 or h >= n:
        raise ValueError(f'horizonte {h} con {n} pares')
    usado = nucleo
    var = varianza_hac_media(d, h - 1, nucleo=nucleo)
    if var <= 0 and nucleo == 'uniforme':
        usado, var = 'bartlett', varianza_hac_media(d, h - 1, nucleo='bartlett')
    media = fmean(d)
    if var <= 0:
        return {'status': 'SIN_VARIANZA', 'n': n, 'horizonte': h, 'media_diferencia': media,
                'prueba': 'diebold_mariano_hln'}
    dm = media / math.sqrt(var)
    estadistico = dm * math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    gl = n - 1
    if alternativa == 'dos_colas':
        p = 2 * stats.t.sf(abs(estadistico), gl)
    elif alternativa == 'menor':
        p = stats.t.cdf(estadistico, gl)
    elif alternativa == 'mayor':
        p = stats.t.sf(estadistico, gl)
    else:
        raise ValueError(f'alternativa desconocida: {alternativa}')
    return {'status': 'OK', 'prueba': 'diebold_mariano_hln', 'n': n, 'horizonte': h, 'gl': gl, 'nucleo': usado,
            'media_diferencia': media, 'estadistico_dm': dm, 'estadistico': estadistico, 'p': float(min(1.0, p)),
            'alternativa': alternativa}


# --- Pares: Wilcoxon, TOST y Bland-Altman ---------------------------------------------------------------------

def wilcoxon_pareado(a: Sequence[float], b: Sequence[float], *, alternativa: str = 'two-sided') -> dict:
    """Wilcoxon de rangos con signo (scipy) y la correlación biserial de rangos (T+ - T-)/(T+ + T-) de Kerby (2014).

    Los pares sin diferencia se descartan (``zero_method='wilcox'``), igual en el p y en la biserial.
    """
    from scipy import stats

    d = [x for x in _pares(a, b) if x != 0]
    if len(d) < 1:
        return {'status': 'BLOQUEADO_POR_DATOS', 'n': 0, 'prueba': 'wilcoxon_pareado'}
    orden = sorted(range(len(d)), key=lambda i: abs(d[i]))
    rangos = [0.0] * len(d)
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and abs(d[orden[j + 1]]) == abs(d[orden[i]]):
            j += 1
        for k in range(i, j + 1):
            rangos[orden[k]] = (i + j + 2) / 2
        i = j + 1
    t_mas = sum(r for r, x in zip(rangos, d) if x > 0)
    t_menos = sum(r for r, x in zip(rangos, d) if x < 0)
    p = float(stats.wilcoxon(d, alternative=alternativa).pvalue)
    return {'status': 'OK', 'prueba': 'wilcoxon_pareado', 'n': len(d), 't_mas': t_mas, 't_menos': t_menos,
            'p': p, 'rango_biserial': (t_mas - t_menos) / (t_mas + t_menos)}


def tost_pareado(a: Sequence[float], b: Sequence[float], inferior: float, superior: float, *,
                 alfa: float = 0.05) -> dict:
    """Equivalencia por dos pruebas t unilaterales (Schuirmann 1987), como ``statsmodels ttost_paired``.

    Hay equivalencia si la diferencia media está con significación dentro de (inferior, superior); el IC de
    1 - 2α que lo acompaña es el que se publica (Lakens 2017).
    """
    from scipy import stats

    if not inferior < superior:
        raise ValueError('el margen de equivalencia pide inferior < superior')
    d = _pares(a, b)
    n = len(d)
    media = fmean(d)
    ee = math.sqrt(sum((x - media) ** 2 for x in d) / (n - 1) / n)
    gl = n - 1
    if ee == 0:
        dentro = inferior < media < superior
        return {'status': 'OK', 'prueba': 'tost_pareado', 'n': n, 'media_diferencia': media, 'p': 0.0 if dentro else 1.0,
                'equivalente': dentro, 'margen': [inferior, superior], 'ic90': [media, media]}
    t_inf, t_sup = (media - inferior) / ee, (media - superior) / ee
    p_inf, p_sup = float(stats.t.sf(t_inf, gl)), float(stats.t.cdf(t_sup, gl))
    p = max(p_inf, p_sup)
    radio = float(stats.t.ppf(1 - alfa, gl)) * ee
    return {'status': 'OK', 'prueba': 'tost_pareado', 'n': n, 'gl': gl, 'media_diferencia': media,
            't_inf': t_inf, 'p_inf': p_inf, 't_sup': t_sup, 'p_sup': p_sup, 'p': p, 'alfa': alfa,
            'equivalente': p < alfa, 'margen': [inferior, superior], 'ic90': [media - radio, media + radio]}


def bland_altman(a: Sequence[float], b: Sequence[float], *, k: float = 1.96,
                 confianza: float = CONFIANZA) -> dict:
    """Sesgo y límites de acuerdo de Bland y Altman (Lancet 1986), con sus IC.

    EE del sesgo s/√n y de cada límite √(3s²/n), con t de n-1 grados de libertad (Bland y Altman 1986 y 1999). El
    artículo usa k = 2; aquí 1,96 por defecto.
    """
    from scipy import stats

    d = _pares(a, b, minimo=3)
    n = len(d)
    sesgo = fmean(d)
    de = math.sqrt(sum((x - sesgo) ** 2 for x in d) / (n - 1))
    t = float(stats.t.ppf(1 - (1 - confianza) / 2, n - 1))
    ee_sesgo, ee_lim = de / math.sqrt(n), math.sqrt(3 * de * de / n)
    lim_inf, lim_sup = sesgo - k * de, sesgo + k * de
    return {'prueba': 'bland_altman', 'n': n, 'k': k, 'sesgo': sesgo, 'de': de, 'lim_inf': lim_inf,
            'lim_sup': lim_sup, 'ic95_sesgo': [sesgo - t * ee_sesgo, sesgo + t * ee_sesgo],
            'ic95_lim_inf': [lim_inf - t * ee_lim, lim_inf + t * ee_lim],
            'ic95_lim_sup': [lim_sup - t * ee_lim, lim_sup + t * ee_lim], 'confianza': confianza}


# --- Acuerdo entre evaluadores --------------------------------------------------------------------------------

def kappa_cohen(evaluador_a: Sequence[Hashable], evaluador_b: Sequence[Hashable]) -> float:
    """Kappa de Cohen (1960): (p_o - p_e)/(1 - p_e), como ``sklearn.metrics.cohen_kappa_score`` sin pesos."""
    if len(evaluador_a) != len(evaluador_b) or not evaluador_a:
        raise ValueError('kappa pide las mismas unidades, al menos una')
    n = len(evaluador_a)
    po = sum(x == y for x, y in zip(evaluador_a, evaluador_b)) / n
    ca, cb = Counter(evaluador_a), Counter(evaluador_b)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def alfa_krippendorff(datos: Sequence[Sequence[float | Hashable | None]], *, nivel: str = 'nominal') -> float:
    """Alfa de Krippendorff con la matriz de coincidencias (Krippendorff 2011); filas = evaluadores, columnas = unidades.

    ``None`` (o NaN) es un valor que falta; las unidades con menos de dos valores no cuentan. Niveles ``nominal`` e
    ``intervalo``, como el paquete ``krippendorff``.
    """
    if nivel == 'nominal':
        def delta(x, y): return 0.0 if x == y else 1.0
    elif nivel == 'intervalo':
        def delta(x, y): return (float(x) - float(y)) ** 2
    else:
        raise ValueError(f'nivel desconocido: {nivel}')

    def falta(v) -> bool:
        return v is None or (isinstance(v, float) and math.isnan(v))

    unidades = len(datos[0]) if datos else 0
    if any(len(fila) != unidades for fila in datos):
        raise ValueError('todas las filas de evaluadores llevan las mismas unidades')
    coincidencias: dict[tuple, float] = defaultdict(float)
    for u in range(unidades):
        valores = [fila[u] for fila in datos if not falta(fila[u])]
        m = len(valores)
        if m < 2:
            continue
        for i, x in enumerate(valores):
            for j, y in enumerate(valores):
                if i != j:
                    coincidencias[(x, y)] += 1 / (m - 1)
    marginal: dict = defaultdict(float)
    for (x, _), o in coincidencias.items():
        marginal[x] += o
    total = sum(marginal.values())
    if total <= 1:
        raise ValueError('sin unidades con dos valores')
    observado = sum(o * delta(x, y) for (x, y), o in coincidencias.items()) / total
    esperado = sum(marginal[x] * marginal[y] * delta(x, y) for x in marginal for y in marginal) / (total * (total - 1))
    return 1.0 if esperado == 0 else 1 - observado / esperado


# --- Remuestreo -----------------------------------------------------------------------------------------------

def bootstrap_agrupado(valores: Sequence[float], grupos: Sequence[Hashable], *,
                       estadistico: Callable[[Sequence[float]], float] = fmean, remuestras: int = 2000,
                       confianza: float = CONFIANZA, semilla: int = 0, min_grupos: int = 2) -> dict:
    """Bootstrap percentil que remuestrea grupos enteros (Field y Welsh 2007; Davison y Hinkley 1997, §3.8).

    Las filas de una misma familia, red o pregunta no son independientes: remuestrearlas sueltas estrecha el IC. Se
    sortean grupos con reposición y el estadístico se calcula sobre todas sus filas. Semilla fija: reproducible.
    """
    x = _finitos(valores, 'valores')
    if len(x) != len(grupos):
        raise ValueError('cada valor lleva su grupo')
    por_grupo: dict = defaultdict(list)
    for v, g in zip(x, grupos):
        por_grupo[g].append(v)
    claves = sorted(por_grupo, key=repr)
    salida = {'prueba': 'bootstrap_agrupado', 'n': len(x), 'grupos': len(claves), 'remuestras': remuestras,
              'semilla': semilla, 'confianza': confianza}
    if len(claves) < min_grupos:
        return {**salida, 'status': 'BLOQUEADO_POR_DATOS', 'valor': estadistico(x) if x else None}
    rnd = random.Random(semilla)
    muestras = sorted(estadistico([v for g in rnd.choices(claves, k=len(claves)) for v in por_grupo[g]])
                      for _ in range(remuestras))
    a = (1 - confianza) / 2
    return {**salida, 'status': 'OK', 'valor': estadistico(x),
            'ic95': [muestras[int(a * (remuestras - 1))], muestras[math.ceil((1 - a) * (remuestras - 1))]]}
