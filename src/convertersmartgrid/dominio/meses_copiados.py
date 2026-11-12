"""Un libro mensual que repite otro mes, día a día (105:RF-13, RF-14; y para la spec 104).

``0426clientesImportantes.xlsb`` trae para abril los mismos valores que marzo en el mismo día y la misma hora: los cuatro
clientes de AL209 con los dos meses coinciden en el 100 % de los registros. Leído como medición, abril parecía un mes
igual a marzo y falseaba el crecimiento. Aquí no se abre ningún libro: solo se comparan series ``(t, P, Q)``, y así lo
usan la evolución de los clientes fijos y el reconocimiento de libros nuevos.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

#: Fracción de registros iguales a partir de la cual una serie repite el mes anterior.
UMBRAL_IGUALES = 0.95
#: Diferencia por debajo de la cual dos valores son el mismo dato copiado.
TOLERANCIA = 1e-6
#: Parejas mínimas (un día de 15 minutos) para comparar una serie: con menos, no se decide nada.
MINIMO_PAREJAS = 96
_QUINCE = np.timedelta64(15, 'm')


@dataclass(frozen=True)
class MesCopiado:
    mes: str                     # 'AAAA-MM' que repite
    de: str                      # 'AAAA-MM' repetido
    series: tuple[str, ...]      # las que lo repiten
    comparables: int             # las que tienen los dos meses


def mes_de_registro(t: np.ndarray) -> np.ndarray:
    """El mes de cada registro de 15 minutos: el de las 00:00 del día 1 cierra el mes anterior (105:RF-4)."""
    return (np.asarray(t, dtype='datetime64[m]') - _QUINCE).astype('datetime64[M]')


def _mes(texto: str) -> np.datetime64:
    return np.datetime64(texto, 'M')


def fraccion_repetida(t: np.ndarray, p: np.ndarray, q: np.ndarray | None, mes: str,
                      de: str | None = None) -> tuple[float, int] | None:
    """Fracción de registros de ``mes`` iguales a los del mismo día y hora de ``de`` (por defecto, el mes anterior).

    Devuelve ``(fracción, parejas)``, o ``None`` si hay menos de ``MINIMO_PAREJAS`` registros con su pareja. Un día que
    no existe en el otro mes (el 31) no cuenta. P y Q se comparan; una Q vacía en los dos lados es igual.
    """
    t = np.asarray(t, dtype='datetime64[m]')
    p = np.asarray(p, dtype=float)
    q = np.full(len(t), np.nan) if q is None else np.asarray(q, dtype=float)
    orden = np.argsort(t, kind='stable')
    t, p, q = t[orden], p[orden], q[orden]
    m, otro = _mes(mes), _mes(de) if de else _mes(mes) - 1
    del_mes = mes_de_registro(t) == m
    if not del_mes.any():
        return None
    ti = t[del_mes]
    # El mismo desfase desde el inicio de su mes natural, en el otro mes: el 00:00 del día 1 siguiente va con el día 1.
    inicio = ti.astype('datetime64[M]')
    desfase = ti - inicio.astype('datetime64[m]')
    destino_inicio = inicio + (otro - m)
    pareja = destino_inicio.astype('datetime64[m]') + desfase
    valido = pareja < (destino_inicio + 1).astype('datetime64[m]')
    j = np.searchsorted(t, pareja)
    hallado = valido & (j < len(t))
    hallado[hallado] = t[j[hallado]] == pareja[hallado]
    n = int(hallado.sum())
    if n < MINIMO_PAREJAS:
        return None
    pi, qi = p[del_mes][hallado], q[del_mes][hallado]
    po, qo = p[j[hallado]], q[j[hallado]]
    iguales_q = (np.abs(qi - qo) < TOLERANCIA) | (np.isnan(qi) & np.isnan(qo))
    iguales = (np.abs(pi - po) < TOLERANCIA) & iguales_q
    return float(iguales.mean()), n


def meses_copiados(series: Mapping[str, tuple[np.ndarray, np.ndarray, np.ndarray | None]],
                   meses: Sequence[str]) -> dict[str, MesCopiado]:
    """Los meses que repiten el anterior en más de la mitad de las series que tienen los dos (105:RF-13; la regla de la spec 104)."""
    salida: dict[str, MesCopiado] = {}
    for mes in sorted(set(meses)):
        de = str(_mes(mes) - 1)
        copiadas, comparables = [], 0
        for nombre, (t, p, q) in series.items():
            r = fraccion_repetida(t, p, q, mes, de)
            if r is None:
                continue
            comparables += 1
            if r[0] >= UMBRAL_IGUALES:
                copiadas.append(nombre)
        if comparables and len(copiadas) * 2 > comparables:
            salida[mes] = MesCopiado(mes, de, tuple(copiadas), comparables)
    return salida
