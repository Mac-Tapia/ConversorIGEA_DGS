"""Datos para la evaluación técnico-económica de PowerFactory (``ComTececo``).

Las unidades y nombres de atributo se leyeron de la API de PF 2024: la etapa guarda
inversión, valor original y de desecho en kUSD, costes adicionales en kUSD/año y vida
útil en años; la orden, el interés en % y las pérdidas en US$/kWh.
"""

from __future__ import annotations

import pytest

from igea_dgs.economia import (
    CostosUnitarios,
    EconomiaError,
    ParametrosTec,
    datos_etapa,
)


def test_inversion_de_la_etapa_suma_cada_sed_en_kusd():
    costos = CostosUnitarios(sed_fijo_usd=2000, trafo_usd_por_kva=40, linea_usd_por_km=15000,
                             vida_util_anios=30, valor_residual_pct=10, om_pct_anual=2)
    sed = [{'sed_code': 'A', 'installed_kva': 100, 'length_km': 0.2},
           {'sed_code': 'B', 'installed_kva': 50, 'length_km': 0.0}]
    eco = datos_etapa(sed, costos)
    # A: 2000 + 4000 + 3000 = 9000 US$; B: 2000 + 2000 = 4000 US$
    assert eco['InvCosts'] == pytest.approx(13.0)
    assert eco['OrigVal'] == pytest.approx(13.0)
    assert eco['ScrVal'] == pytest.approx(1.3)
    assert eco['AddCosts'] == pytest.approx(0.26)
    assert eco['LifeSpan'] == 30
    assert [d['usd'] for d in eco['detalle']] == [pytest.approx(9000), pytest.approx(4000)]


def test_sin_ningun_precio_es_error():
    with pytest.raises(EconomiaError, match='al menos un coste'):
        CostosUnitarios().validar()


@pytest.mark.parametrize('campo,valor', [('trafo_usd_por_kva', -1), ('vida_util_anios', 0),
                                         ('valor_residual_pct', 120)])
def test_costes_fuera_de_rango(campo, valor):
    with pytest.raises(EconomiaError):
        CostosUnitarios(**{'trafo_usd_por_kva': 10, campo: valor}).validar()


def test_la_orden_apaga_las_interrupciones_que_vienen_activadas():
    """frm_Interrupt viene a 1 y exige un cálculo de fiabilidad enlazado (pRel3)."""
    attrs = ParametrosTec(inicio=2026, fin=2046, interes_pct=12, perdidas_usd_kwh=0.1).a_comtececo()
    assert attrs['frm_Interrupt'] == 0
    assert attrs['frm_Losses'] == 1                 # pérdidas por flujo de carga
    assert attrs['Start'] == 2026 and attrs['End'] == 2046
    assert attrs['InterestRate'] == 12.0 and attrs['CostsLLoss'] == 0.1
    assert attrs['CalcPoints'] == 0                 # una vez al año


def test_periodo_invalido():
    with pytest.raises(EconomiaError, match='1970'):
        ParametrosTec(inicio=1960, fin=2000).validar()
    with pytest.raises(EconomiaError, match='anterior al de inicio'):
        ParametrosTec(inicio=2030, fin=2026).validar()


def test_etapas_fuera_del_periodo_no_entrarian_en_el_van():
    with pytest.raises(EconomiaError, match='fuera del periodo'):
        ParametrosTec(inicio=2027, fin=2040).validar(anio_etapas=2026)
