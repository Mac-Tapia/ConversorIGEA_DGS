"""Anexo 5 del TdR del VAD, modelo geométrico urbano: las incoherencias del original, resueltas como decidió 28
(spec 108, RF-6, RF-9, RF-13; tarjeta VAD-A5U, primera parte de la T14).

Las fórmulas viven en el registro (``config/vad/anexo5_urbano.json``, ``vad.anexo5.*``), en la sintaxis de
:mod:`.formulas`, y se evalúan con su intérprete cerrado. Lo que el TdR deja mal o sin decir se resuelve aquí, siempre
desde las fórmulas del registro y nunca con una cifra escrita en el código:

- **Ecuación circular** R_BT ↔ TRI_AREA ↔ NTRI (:func:`resolver_tri_area`). TRI_AREA = π·(R_BT/1000)² y R_BT depende
  de TRI_AREA. Como R_BT = 1000·√(E(T)/D) con E afín en T, la ecuación es lineal y tiene forma cerrada,
  T = π·E₀/(D − π·E₁) (en la MAD, T = A·FP_DIS/(1000·δ_BT·FD_BT)): se calcula con E₀, E₁ y D evaluados en las propias
  fórmulas del registro y se comprueba con el residuo de las dos (≤ 1e-9), sustituyendo T en las fórmulas
  TRANSCRITAS de esa rama, sin ninguna forma derivada (:func:`residuos`, c3, v2). En el resto la forma es
  T = A/(1000·δ_BT·FD_BT/FP_DIS + AP_D): la de la MAD no cumple allí el residuo, porque el resto no lleva el
  «− AP_D/1000» que en la MAD cancela el AP_D·T del numerador. Hueco nombrado si A ≤ 0, D ≤ 0, E(T) < 0
  o el denominador de NTRI ≤ 0.
- **El paréntesis de NTRI** (:func:`comprobar_lectura_ntri`): en la pág. 5-5 abre tres y cierra dos. Vale la lectura
  (a): el denominador es FP_DIS·E(T), con el MISMO corchete E que el numerador de R_BT (pág. 5-8, donde cierran). Una
  lectura (b) se detecta y se rechaza.
- **Los dos +5 %** (:func:`incremento_derivaciones`): se suman (×1,10) y el aviso da el compuesto (×1,1025).
- **Símbolos sin definir** (:func:`entradas`): CCT_INICIAL, b, K_CT, cr, Ic y clientes_AT/MT son entradas del perfil
  SIN valor por defecto (``vad.anexo5.entradas_sin_definir``); la que falta es un hueco nombrado, nunca 0.
- **La tasa «i»** (:func:`tasa_i`): el Anexo 5 no la define; ``vad.anexo5.tasa_i`` remite a ``vad.tasa_actualizacion``
  (cap. 5, art. 79 de la LCE). :func:`factor_capitalizacion` = 1/FRC(i, vida útil) con ``pide_economia.frc``, la misma
  función que da el FRC y el Kim del Anexo 6.
- **Los factores de 1000** (:func:`perdidas_mt`): Leq pasa de m a km y la energía de MWh a kWh, con su prueba.
- **Te** (:func:`tiempo_equivalente`): Te = H·fp(Tu/H) con la función de pérdidas común (``informes.factor_de_perdidas``,
  INF-FP), y se comprueba contra la fórmula Te del registro.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..informes import factor_de_perdidas
from ..pide_economia import frc
from ..registro_normativo import RegistroError, RegistroNormativo, ReglaVigente, regla_remitida
from . import VadError
from .formulas import FormulaError, evaluar

RAMAS = {'mad': 'vad.anexo5.mad', 'resto': 'vad.anexo5.resto'}
REGLA_TASA = 'vad.anexo5.tasa_i'
REGLA_SIN_DEFINIR = 'vad.anexo5.entradas_sin_definir'
#: La definición de TRI_AREA la da la MAD (lista de variables de NTRI) y vale también para el resto (z26b).
REGLA_TRI_AREA = 'vad.anexo5.mad.ntri_ncti'
#: Horas de un año de 365 días: las del calendario, la misma base de Tu y de Te.
HORAS_ANIO = 24 * 365
TOLERANCIA_RESIDUO = 1e-9


def _rama(rama: str) -> str:
    if rama not in RAMAS:
        raise VadError(f'rama del Anexo 5 {rama!r}; las ramas son {tuple(RAMAS)}')
    return RAMAS[rama]


def formulas_de(registro: RegistroNormativo, rama: str, fecha: str | None = None) -> dict[str, tuple[str, str]]:
    """Fórmula → (texto, clave de la regla) de la rama; TRI_AREA, de la MAD."""
    prefijo = _rama(rama) + '.'
    out: dict[str, tuple[str, str]] = {}
    claves = sorted({r.clave for n in registro.normas.values() for r in n.reglas if r.clave.startswith(prefijo)})
    for clave in claves + [REGLA_TRI_AREA]:
        valor = registro.regla(clave, fecha).regla.valor
        for nombre, texto in ((valor or {}).get('formulas') or {}).items() if isinstance(valor, Mapping) else ():
            out.setdefault(nombre, (texto, clave))
    if not out:
        raise VadError(f'el registro no trae las fórmulas del Anexo 5 ({prefijo}*)')
    return out


def _formula(formulas: Mapping[str, tuple[str, str]], nombre: str) -> str:
    if nombre not in formulas:
        raise VadError(f'el registro no trae la fórmula {nombre} del Anexo 5')
    return formulas[nombre][0]


# ------------------------------------------------------------------------------- R_BT, TRI_AREA y NTRI
def _sin_mayusculas(nodo: ast.AST) -> str:
    """El árbol de una expresión con los nombres en minúsculas: el TdR escribe COS_fi y cos_fi para lo mismo."""
    copia = ast.parse(ast.unparse(nodo), mode='eval')
    for n in ast.walk(copia):
        if isinstance(n, ast.Name):
            n.id = n.id.casefold()
    return ast.dump(copia)


def _partes_rbt(texto: str) -> tuple[ast.expr, ast.expr]:
    """R_BT = 1000 · (E / D) ** 0.5 → (E, D). Otra forma no es la del TdR registrado."""
    cuerpo = ast.parse(texto, mode='eval').body
    if (isinstance(cuerpo, ast.BinOp) and isinstance(cuerpo.op, ast.Mult) and isinstance(cuerpo.right, ast.BinOp)
            and isinstance(cuerpo.right.op, ast.Pow) and isinstance(cuerpo.right.left, ast.BinOp)
            and isinstance(cuerpo.right.left.op, ast.Div)):
        return cuerpo.right.left.left, cuerpo.right.left.right
    raise VadError(f'R_BT no tiene la forma 1000·(E/D)**0.5 del TdR registrado: {texto!r}')


def _partes_ntri(texto: str) -> tuple[ast.expr, ast.expr, ast.expr]:
    """NTRI = N / (FP · E') → (N, FP, E'): el denominador tiene que ser un producto de dos factores."""
    cuerpo = ast.parse(texto, mode='eval').body
    if (isinstance(cuerpo, ast.BinOp) and isinstance(cuerpo.op, ast.Div) and isinstance(cuerpo.right, ast.BinOp)
            and isinstance(cuerpo.right.op, ast.Mult)):
        return cuerpo.left, cuerpo.right.left, cuerpo.right.right
    raise VadError(f'el denominador de NTRI no es un producto FP_DIS·(…): lectura (b) del paréntesis, que no vale '
                   f'(lectura (a), págs. 5-5 y 5-8): {texto!r}')


def comprobar_lectura_ntri(registro: RegistroNormativo, rama: str, fecha: str | None = None) -> str:
    """'a' si el corchete del denominador de NTRI es el numerador de R_BT; si no, VadError que nombra la lectura (b)."""
    f = formulas_de(registro, rama, fecha)
    e_rbt, _ = _partes_rbt(_formula(f, 'R_BT'))
    _, fp, e_ntri = _partes_ntri(_formula(f, 'NTRI'))
    if _sin_mayusculas(e_ntri) != _sin_mayusculas(e_rbt):
        raise VadError('lectura (b) del paréntesis de NTRI: su corchete no es el numerador de R_BT (pág. 5-8). Vale '
                       f'la lectura (a), FP_DIS·(PTR·Fu − N·P/COS − AP_D·TRI_AREA): {ast.unparse(fp)} · '
                       f'{ast.unparse(e_ntri)}')
    return 'a'


@dataclass
class SolucionTriArea:
    tri_area: float | None
    r_bt: float | None
    ntri: float | None
    residuo_r_bt: float | None = None
    residuo_tri_area: float | None = None
    huecos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _valores(valores: Mapping[str, float]) -> dict[str, float]:
    """Los nombres del perfil, también en minúsculas: el TdR escribe COS_fi y cos_fi para el mismo factor."""
    out = dict(valores)
    for k, v in valores.items():
        out.setdefault(k.casefold(), v)
        out.setdefault(k.upper(), v)
    return out


def _eval(expr: str | ast.expr, valores: Mapping[str, float]) -> float:
    texto = expr if isinstance(expr, str) else ast.unparse(expr)
    nombres = {n.id for n in ast.walk(ast.parse(texto, mode='eval')) if isinstance(n, ast.Name)}
    v = _valores(valores)
    return evaluar(texto, {n: v[n] if n in v else v.get(n.casefold(), v.get(n.upper())) for n in nombres
                           if n in v or n.casefold() in v or n.upper() in v})


def residuos(t: float, valores: Mapping[str, float], registro: RegistroNormativo, rama: str,
             fecha: str | None = None) -> tuple[float, float, float]:
    """(R_BT, |TRI_AREA(R_BT(T)) − T|, |R_BT(TRI_AREA(R_BT(T))) − R_BT(T)|), con las fórmulas R_BT y TRI_AREA
    TRANSCRITAS en el registro para la rama: el punto fijo se comprueba en las dos, sin forma derivada."""
    f = formulas_de(registro, rama, fecha)
    r_bt = _eval(_formula(f, 'R_BT'), {**valores, 'TRI_AREA': t})
    t2 = _eval(_formula(f, 'TRI_AREA'), {'R_BT': r_bt})
    r_bt2 = _eval(_formula(f, 'R_BT'), {**valores, 'TRI_AREA': t2})
    return r_bt, abs(t2 - t), abs(r_bt2 - r_bt)


def resolver_tri_area(valores: Mapping[str, float], registro: RegistroNormativo, rama: str,
                      fecha: str | None = None) -> SolucionTriArea:
    """TRI_AREA, R_BT y NTRI de una zona, en forma cerrada (decisión (1) de 28), con sus residuos y sus huecos."""
    comprobar_lectura_ntri(registro, rama, fecha)
    f = formulas_de(registro, rama, fecha)
    e, d = _partes_rbt(_formula(f, 'R_BT'))
    sol = SolucionTriArea(None, None, None)
    try:
        e0 = _eval(e, {**valores, 'TRI_AREA': 0.0})
        e1 = _eval(e, {**valores, 'TRI_AREA': 1.0}) - e0
        den = _eval(d, valores)
        pi_area = _eval(_formula(f, 'TRI_AREA'), {'R_BT': 1000.0})        # π·(1000/1000)² = π, desde el registro
    except FormulaError as exc:
        sol.huecos.append(f'no se puede plantear la ecuación de TRI_AREA: {exc}')
        return sol
    if e0 <= 0:
        sol.huecos.append(f'A = PTR·Fu − N·P/COS = {e0:.6g} ≤ 0: el transformador no tiene potencia para la BT; sin '
                          'solución')
        return sol
    if den <= 0:
        sol.huecos.append(f'el denominador de R_BT es {den:.6g} ≤ 0: sin solución')
        return sol
    divisor = den - pi_area * e1
    if divisor <= 0:
        sol.huecos.append(f'D − π·E₁ = {divisor:.6g} ≤ 0: la ecuación de TRI_AREA no tiene solución positiva')
        return sol
    t = pi_area * e0 / divisor
    radicando = e0 + e1 * t
    if radicando < 0:
        sol.huecos.append(f'A − AP_D·TRI_AREA = {radicando:.6g} < 0: la raíz de R_BT no existe; sin solución')
        return sol
    v = {**valores, 'TRI_AREA': t}
    r_bt, sol.residuo_tri_area, sol.residuo_r_bt = residuos(t, valores, registro, rama, fecha)
    sol.tri_area, sol.r_bt = t, r_bt
    if (sol.residuo_tri_area > TOLERANCIA_RESIDUO * max(1.0, t)
            or sol.residuo_r_bt > TOLERANCIA_RESIDUO * max(1.0, r_bt)):
        sol.huecos.append(f'la forma cerrada no cumple las fórmulas del registro (residuos {sol.residuo_tri_area:.3g} y '
                          f'{sol.residuo_r_bt:.3g})')
        return sol
    _, n_fp, n_e = _partes_ntri(_formula(f, 'NTRI'))
    den_ntri = _eval(n_fp, v) * _eval(n_e, v)
    if den_ntri <= 0:
        sol.huecos.append(f'el denominador de NTRI es {den_ntri:.6g} ≤ 0: sin solución')
        return sol
    sol.ntri = _eval(_formula(f, 'NTRI'), v)
    sol.avisos.append('TRI_AREA en forma cerrada (interpretación aprobada por 28): el TdR la define con R_BT, que a su '
                      f'vez depende de TRI_AREA; residuos {sol.residuo_tri_area:.1e} y {sol.residuo_r_bt:.1e}; lectura '
                      '(a) del paréntesis de NTRI')
    return sol


# ------------------------------------------------------------------------------------- tasa i y entradas
@dataclass(frozen=True)
class TasaI:
    tasa: float
    vida_util: int
    remision: ReglaVigente
    principal: ReglaVigente


def tasa_i(registro: RegistroNormativo, fecha: str | None = None) -> TasaI:
    """La «i» del Anexo 5: ``vad.anexo5.tasa_i`` remite a ``vad.tasa_actualizacion``, que remite a la tasa del art. 79
    de la LCE (UNA-TASA). La cadena la sigue el registro (``registro_normativo.regla_remitida``), el único sitio que
    resuelve remisiones; la vida útil es un dato de la propia remisión del Anexo 5."""
    try:
        cadena = regla_remitida(registro, REGLA_TASA, fecha)
    except RegistroError as exc:
        raise VadError(f'el Anexo 5 usa la tasa «i» sin definirla y el registro no trae su remisión ({REGLA_TASA}) o la '
                       f'regla a la que remite: {exc}') from exc
    rem, principal = cadena.remision, cadena.principal
    if principal is rem:
        raise VadError(f'{REGLA_TASA} tiene que remitir a la regla de la tasa del art. 79 de la LCE')
    valor = principal.regla.valor
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise VadError(f'{REGLA_TASA} remite a {principal.regla.clave}, cuyo valor ({valor!r}) no es una tasa')
    datos = rem.regla.valor if isinstance(rem.regla.valor, Mapping) else {}
    if 'vida_util_anios' not in datos:
        raise VadError(f'{REGLA_TASA} no da la vida útil en años (vida_util_anios)')
    return TasaI(float(valor), int(datos['vida_util_anios']), rem, principal)


def factor_capitalizacion(registro: RegistroNormativo, fecha: str | None = None) -> float:
    """1/FRC(i, vida útil), con la función común ``pide_economia.frc``: el Kim del Anexo 6 (8,05 en el TdR)."""
    t = tasa_i(registro, fecha)
    return 1.0 / frc(t.tasa, t.vida_util)


@dataclass
class Entradas:
    valores: dict[str, float] = field(default_factory=dict)
    huecos: list[str] = field(default_factory=list)


def entradas(perfil: Mapping[str, float], registro: RegistroNormativo, rama: str,
             fecha: str | None = None) -> Entradas:
    """Los símbolos que el TdR no define, desde el perfil (``vad.anexo5.<x>``), sin valor por defecto."""
    prefijo = _rama(rama)
    try:
        regla = registro.regla(REGLA_SIN_DEFINIR, fecha)
    except RegistroError as exc:
        raise VadError(f'falta {REGLA_SIN_DEFINIR} del registro: {exc}') from exc
    out = Entradas()
    for simbolo, datos in sorted(regla.regla.valor.items()):
        if not any(c.startswith(prefijo + '.') for c in datos['aparece_en']):
            continue
        clave = datos['perfil']
        if clave in perfil and perfil[clave] is not None:
            out.valores[simbolo] = float(perfil[clave])
        else:
            out.huecos.append(f'{simbolo}: el Anexo 5 lo usa ({", ".join(datos["aparece_en"])}) sin definirlo y el '
                              f'perfil no da «{clave}»; sin valor por defecto, no se calcula lo que lo usa')
    return out


# --------------------------------------------------------------------------------------- incrementos y pérdidas
@dataclass(frozen=True)
class IncrementoLongitud:
    factor: float
    compuesto: float
    aviso: str


def incremento_derivaciones(registro: RegistroNormativo, rama: str = 'mad', fecha: str | None = None) -> IncrementoLongitud:
    """Los dos +5 % de la longitud de derivaciones MT, sumados (decisión (3) de 28); el aviso da el compuesto."""
    clave = 'vad.anexo5.mad.mt.derivaciones' if rama == 'mad' else 'vad.anexo5.resto.mt.inicial'
    _rama(rama)
    v = registro.regla(clave, fecha).regla.valor
    a, b = float(v['incremento_densidad_no_uniforme']), float(v['incremento_trazado'])
    suma, comp = 1.0 + a + b, (1.0 + a) * (1.0 + b)
    return IncrementoLongitud(suma, comp, f'los dos incrementos del TdR ({a:.0%} y {b:.0%}) se suman: ×{suma:.4f}; '
                                          f'compuestos darían ×{comp:.4f} ({clave})')


def tiempo_equivalente(tu: float, registro: RegistroNormativo, rama: str = 'mad', fecha: str | None = None) -> float:
    """Te [h/año] con la función de pérdidas común (INF-FP) y comprobado contra la fórmula Te del registro."""
    te = HORAS_ANIO * factor_de_perdidas(tu / HORAS_ANIO, registro, fecha)
    literal = evaluar(_formula(formulas_de(registro, rama, fecha), 'Te'), {'Tu': tu})
    if abs(te - literal) > TOLERANCIA_RESIDUO * max(1.0, abs(te)):
        raise VadError(f'el Te del Anexo 5 ({literal}) no es el de la función de pérdidas común ({te})')
    return te


def perdidas_mt(valores: Mapping[str, Any], registro: RegistroNormativo, rama: str = 'mad',
                fecha: str | None = None) -> tuple[float, str]:
    """cp_MT [USD/km2] con las unidades del TdR: L_RADIAL en m, r en ohm/km, la corriente por salida en kA, Te en h y
    ce en USD/kWh. La fórmula se evalúa tal como está en el registro, con Leq en km y la energía de MWh a kWh: los dos
    factores de 1000 que el TdR no escribe (decisión (3) de 28)."""
    f = formulas_de(registro, rama, fecha)
    v = dict(valores)
    i_ka = evaluar(_formula(f, 'I_SALIDA_MT_kA'), {k: v[k] for k in ('Pif', 'Fu_ATMT', 'U_NOMINAL_MT', 'CS')})
    leq_m = evaluar(_formula(f, 'Leq'), {'L_RADIAL': v['L_RADIAL']})
    v.update({'Leq': leq_m / 1000.0, 'I_ALIMENTADOR': i_ka})
    if 'Te' not in v:
        v['Te'] = tiempo_equivalente(float(v['Tu']), registro, rama, fecha)
    if 'Kp_MT' not in v:
        horizonte = int(registro.regla(_rama(rama) + '.futuro', fecha).regla.valor['horizonte_anios'])
        v['Kp_MT'] = evaluar(_formula(f, 'Kp_MT'), {'a': float(v['a']), 'i': tasa_i(registro, fecha).tasa,
                                                    'anio': [1.0] * horizonte})
    nombres = {n.id for n in ast.walk(ast.parse(_formula(f, 'cp_MT'), mode='eval')) if isinstance(n, ast.Name)}
    faltan = sorted(n for n in nombres if n not in v)
    if faltan:
        raise VadError(f'cp_MT necesita {faltan}')
    mwh = evaluar(_formula(f, 'cp_MT'), {n: v[n] for n in nombres})
    return mwh * 1000.0, ('cp_MT con Leq = L_RADIAL/2 pasado de m a km (r en ohm/km) y la energía (kA²·ohm·h = MWh) '
                          'pasada a kWh (ce en USD/kWh): factores de 1000 que el TdR no escribe')
