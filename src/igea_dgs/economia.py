"""Datos para la evaluación técnico-económica de PowerFactory (``ComTececo``).

PowerFactory calcula el valor actual neto (VAN) de una **estrategia de expansión**
definida con variaciones y etapas (manual PF 2024, cap. 43.2). Cada etapa lleva sus
datos económicos y la orden suma inversión, valor depreciado, coste de pérdidas, de
interrupciones y costes propios. Gana la estrategia con el VAN más **bajo**.

El lote de cargas ya crea una variación con su etapa por alimentador para las SED
nuevas. Este módulo pone precio a esa etapa con los costes unitarios del operador:

    inversión = Σ (coste fijo por SED + US$/kVA · kVA de placa + US$/km · km de derivación)

y prepara los parámetros de la orden. Las unidades son las que pide PowerFactory, leídas
de su API: la inversión, el valor original y el de desecho van en **miles de US$**; los
costes adicionales en miles de US$/año; la vida útil en años; el interés en %; las
pérdidas en US$/kWh.

No habla con PowerFactory: lo escribe ``tools/aplicar_lote_cargas.py``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

PUNTOS_ANUAL = 'anual'
PUNTOS_ETAPAS = 'etapas'
# Valor de ComTececo.CalcPoints para cada opción (fixedYears, byStages).
CALC_POINTS = {PUNTOS_ANUAL: 0, PUNTOS_ETAPAS: 1}


class EconomiaError(ValueError):
    """Un coste o parámetro no utilizable."""


@dataclass(frozen=True)
class CostosUnitarios:
    """Costes con los que se valora cada SED nueva, en US$."""

    sed_fijo_usd: float = 0.0            # obra civil, montaje, protección…
    trafo_usd_por_kva: float = 0.0
    linea_usd_por_km: float = 0.0
    vida_util_anios: int = 30            # transformadores: 30 años (manual PF, 43.2.1.2)
    valor_residual_pct: float = 0.0      # % del valor original al final de la vida útil
    om_pct_anual: float = 0.0            # operación y mantenimiento, % de la inversión al año

    def validar(self) -> None:
        for nombre in ('sed_fijo_usd', 'trafo_usd_por_kva', 'linea_usd_por_km'):
            if getattr(self, nombre) < 0:
                raise EconomiaError(f'{nombre} no puede ser negativo.')
        if not 1 <= self.vida_util_anios <= 100:
            raise EconomiaError('La vida útil debe estar entre 1 y 100 años.')
        for nombre in ('valor_residual_pct', 'om_pct_anual'):
            if not 0 <= getattr(self, nombre) <= 100:
                raise EconomiaError(f'{nombre} debe estar entre 0 y 100 %.')
        if not (self.sed_fijo_usd or self.trafo_usd_por_kva or self.linea_usd_por_km):
            raise EconomiaError('Indique al menos un coste: sin precios la inversión sería cero.')


@dataclass(frozen=True)
class ParametrosTec:
    """Parámetros de la orden ``ComTececo``."""

    inicio: int                          # año
    fin: int                             # año
    interes_pct: float = 12.0
    perdidas_usd_kwh: float = 0.0        # CostsLLoss: parte de las pérdidas que depende de la carga
    perdidas_vacio_usd_kwh: float = 0.0  # CostsnLLoss: la que no depende (hierro)
    puntos: str = PUNTOS_ANUAL

    def validar(self, anio_etapas: int | None = None) -> None:
        if self.inicio < 1970:
            # PowerFactory lo rechaza (ComTececo.eMinStart).
            raise EconomiaError('El año de inicio no puede ser anterior a 1970.')
        if self.fin < self.inicio:
            raise EconomiaError('El año final no puede ser anterior al de inicio.')
        if not 0 <= self.interes_pct <= 100:
            raise EconomiaError('La tasa de descuento debe estar entre 0 y 100 %.')
        if self.perdidas_usd_kwh < 0 or self.perdidas_vacio_usd_kwh < 0:
            raise EconomiaError('El coste de las pérdidas no puede ser negativo.')
        if self.puntos not in CALC_POINTS:
            raise EconomiaError(f'Puntos de cálculo: use {PUNTOS_ANUAL!r} o {PUNTOS_ETAPAS!r}.')
        if anio_etapas is not None and not self.inicio <= anio_etapas <= self.fin:
            # Solo cuentan las etapas activadas dentro del periodo (manual, 43.2.2.1):
            # fuera de él, el VAN saldría sin la inversión que se quiere evaluar.
            raise EconomiaError(
                f'Las etapas se activan en {anio_etapas}, fuera del periodo '
                f'{self.inicio}-{self.fin}: no entrarían en el cálculo.')

    def a_comtececo(self) -> dict[str, Any]:
        """Atributos de ``ComTececo``, con los nombres de la API de PF 2024."""
        return {
            'CalcPoints': CALC_POINTS[self.puntos],
            'Start': int(self.inicio),
            'End': int(self.fin),
            'InterestRate': float(self.interes_pct),
            'frm_Losses': 1,                 # evaluar pérdidas con flujo de carga
            'CostsLLoss': float(self.perdidas_usd_kwh),
            'CostsnLLoss': float(self.perdidas_vacio_usd_kwh),
            # Viene activada por defecto y exige un cálculo de fiabilidad enlazado
            # (pRel3); sin él la orden falla con «Since interruption costs are
            # selected…». Las interrupciones son otra fase: aquí se apagan.
            'frm_Interrupt': 0,
            'frm_LineOut': 0,
            'frm_SubOut': 0,
            'frm_UserCosts': 0,
            'frm_Tie': 0,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def datos_etapa(sed_nuevas: list[dict], costos: CostosUnitarios) -> dict[str, Any]:
    """Datos económicos de la etapa de un alimentador, desde su plan de creación.

    ``sed_nuevas`` son las entradas ``create`` de ``create_plan_to_payload``: cada una
    trae ``installed_kva`` y ``length_km``.
    """
    detalle = []
    total_usd = 0.0
    for spec in sed_nuevas:
        kva = float(spec.get('installed_kva') or 0.0)
        km = float(spec.get('length_km') or 0.0)
        usd = costos.sed_fijo_usd + costos.trafo_usd_por_kva * kva + costos.linea_usd_por_km * km
        total_usd += usd
        detalle.append({'sed_code': spec.get('sed_code'), 'kva': kva, 'km': km, 'usd': usd})
    inversion_k = total_usd / 1000.0
    return {
        'InvCosts': inversion_k,
        'OrigVal': inversion_k,
        'ScrVal': inversion_k * costos.valor_residual_pct / 100.0,
        'AddCosts': inversion_k * costos.om_pct_anual / 100.0,
        'LifeSpan': int(costos.vida_util_anios),
        'detalle': detalle,
    }
