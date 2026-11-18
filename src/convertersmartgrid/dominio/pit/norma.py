"""Lo que la Norma Tarifas (RCD 217-2013-OS/CD) fija para el PIT y el código lee del registro, no de la entrada
(107:RF-20, T32).

- Los años de la programación de la demanda (art. 5.9.4: los años 1, 2, 3, 4, 5, 8 y 10 del horizonte) y el horizonte
  de la comparación de alternativas (art. 3.14: 10 años). El año 1 es el primero pedido; un año pedido que no es de la
  programación no se diagnostica, y los de la programación que faltan se avisan.
- El factor de potencia de las barras de MT de las SET (art. 12.1.8.c: 0,95) en la demanda que se reparte a ellas.
- El N-1 solo donde la norma lo exige (art. 12.3.1, en la 018-2018: la transmisión que atienda más de 30 MW): para cada
  elemento, su flujo en el caso base.
- El criterio de la comparación (5.9.3), el costo total (11.3), el método del COyM (17.2) y la fuente de la tasa (24.2)
  se leen y se citan; si el registro dice otro criterio que el que aplica el código, se avisa.

Sin una regla en el registro, el cálculo sigue como antes y lo dice: nada se inventa.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo, ReglaAmbigua

ANIOS = 'pit.anios_programacion_demanda'
HORIZONTE = 'pit.horizonte_alternativas_anios'
FACTOR_POTENCIA = 'pit.factor_potencia_barras_mt'
N1 = 'pit.n1_demanda_min_mw'
#: Las reglas de la comparación que el código aplica y el expediente cita (5.9.3, 11.3, 17.2 y 24.2).
CITADAS = ('pit.criterio_alternativas', 'pit.costo_total', 'pit.coym_metodo', 'pit.tasa_actualizacion_fuente')
#: El criterio que aplica ``alternativas.evaluar``: el mínimo valor presente de inversión, COyM y pérdidas.
CRITERIO_DEL_CODIGO = 'minimo_costo_total_inversion_coym_perdidas'


def valor(registro: RegistroNormativo | None, clave: str, fecha: str | None = None) -> Any:
    """El valor vigente de ``clave``, o ``None`` si el registro no la trae (una ambigua sube: RN-AMB)."""
    if registro is None:
        return None
    try:
        return registro.regla(clave, fecha).regla.valor
    except ReglaAmbigua:
        raise  # varias normas vigentes a la vez: no es una regla que falte (RN-AMB)
    except RegistroError:
        return None


def _falta(clave: str) -> str:
    return f'el registro no trae {clave}: se sigue con lo pedido y la norma no se comprueba'


def anios_de_programacion(registro: RegistroNormativo | None, pedidos: Iterable[int],
                          fecha: str | None = None) -> tuple[list[int], list[str]]:
    """Los años del diagnóstico según el art. 5.9.4, con el año 1 en el primero pedido: de lo pedido, los que son años
    de la programación. Los pedidos que no lo son quedan fuera y se avisan, y también los de la norma que no se pidieron."""
    pedidos = sorted({int(a) for a in pedidos})
    relativos = valor(registro, ANIOS, fecha)
    if not pedidos:
        return pedidos, []
    if not relativos:
        return pedidos, [_falta(ANIOS)] if registro is not None else []
    primero = pedidos[0]
    norma = [primero - 1 + int(k) for k in relativos]
    usados = [a for a in pedidos if a in norma]
    fuera = [a for a in pedidos if a not in norma]
    faltan = [a for a in norma if a not in pedidos]
    avisos = []
    if fuera:
        avisos.append(f'los años {fuera} no son de la programación de la norma (años {list(relativos)} del horizonte, '
                      f'art. 5.9.4 de la RCD 217-2013): no se diagnostican')
    if faltan:
        avisos.append(f'faltan los años {faltan} de la programación de la norma (art. 5.9.4 de la RCD 217-2013): '
                      'pídalos con su demanda proyectada')
    return usados, avisos


def anios_de_alternativas(registro: RegistroNormativo | None, anios: Sequence[int],
                          fecha: str | None = None) -> tuple[list[int], list[str]]:
    """Los años de la comparación de alternativas, dentro de su horizonte (art. 3.14); los de más allá se avisan."""
    anios = sorted(int(a) for a in anios)
    horizonte = valor(registro, HORIZONTE, fecha)
    if not anios or horizonte is None:
        return anios, [_falta(HORIZONTE)] if registro is not None and anios else []
    tope = anios[0] - 1 + int(horizonte)
    fuera = [a for a in anios if a > tope]
    dentro = [a for a in anios if a <= tope]
    if not fuera:
        return dentro, []
    return dentro, [f'los años {fuera} pasan del horizonte de las alternativas ({horizonte} años, art. 3.14 de la RCD '
                    f'217-2013): no entran en la comparación']


def factor_potencia(registro: RegistroNormativo | None, fecha: str | None = None) -> float | None:
    """El factor de potencia de las barras de MT de las SET (art. 12.1.8.c), o ``None`` sin la regla."""
    fp = valor(registro, FACTOR_POTENCIA, fecha)
    return float(fp) if fp is not None else None


def q_con_factor(p_mw: float, fp: float) -> float:
    """La Q (Mvar) de una P (MW) con factor de potencia ``fp`` inductivo."""
    return p_mw * math.tan(math.acos(fp))


def elementos_con_n1(registro: RegistroNormativo | None, flujos: Mapping[str, tuple[float, float]],
                     candidatos: Sequence[str], fecha: str | None = None) -> tuple[list[str], str]:
    """Los elementos cuyo N-1 exige la norma (art. 12.3.1: más de ``pit.n1_demanda_min_mw`` MW en el caso base), y un
    aviso con los que quedan fuera. Sin la regla, todos y el aviso lo dice."""
    minimo = valor(registro, N1, fecha)
    if minimo is None:
        return list(candidatos), _falta(N1) if registro is not None else ''
    exigen = [e for e in candidatos if abs(float((flujos.get(e) or (0.0, 0.0))[0])) > float(minimo)]
    fuera = len(candidatos) - len(exigen)
    aviso = (f'N-1 solo en los {len(exigen)} elementos que atienden más de {minimo} MW en el caso base (art. 12.3.1, '
             f'RCD 018-2018); {fuera} quedan fuera') if fuera else ''
    return exigen, aviso


def reglas_citadas(registro: RegistroNormativo | None, fecha: str | None = None) -> tuple[list[str], list[str]]:
    """Las reglas de la comparación que el registro trae (para citarlas) y los avisos: las que faltan y un criterio que
    no es el que aplica el código."""
    presentes, avisos = [], []
    for clave in CITADAS:
        if valor(registro, clave, fecha) is None:
            avisos.append(f'el registro no trae {clave}: la comparación no la cita')
        else:
            presentes.append(clave)
    criterio = valor(registro, 'pit.criterio_alternativas', fecha)
    if criterio is not None and criterio != CRITERIO_DEL_CODIGO:
        avisos.append(f'el registro dice el criterio {criterio!r} y el código ordena por {CRITERIO_DEL_CODIGO!r}: '
                      'revise la comparación')
    return presentes, avisos
