"""Spec 020: regla de dimensionado de los transformadores de las SED fijas sobrecargadas."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from igea_dgs.perfil_empresa import transformadores_sed
from igea_dgs.trafos_sed import proponer, tabla_para

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def fichas():
    datos = json.loads((RAIZ / 'config' / 'perfiles' / 'electro_dunas.json')
                       .read_text(encoding='utf-8'))
    return transformadores_sed(datos)


@pytest.mark.parametrize('sed, kva_carga, kva, unidades', [
    ('SE30940', 3818.0101763463354, 630, 8),
    ('SE30480', 1299.755452346939, 630, 3),
    ('SE30642', 976.0115103061227, 630, 2),
    ('SE30424', 373.7713031632653, 500, 1),
])
def test_las_sed_de_pa217(fichas, sed, kva_carga, kva, unidades):
    """020:RF-6 / 020:RF-7 / 020:RF-8 — PA217 (22,9 kV, Tabla 7), 2026-10-16: lo que se hizo a
    mano en la T26 de la 015 sale de la regla."""
    p = proponer(kva_carga, 22.9, fichas['tablas'], fichas['umbral_carga_pct'])
    assert (p['kva'], p['unidades']) == (kva, unidades), sed
    assert 'Tabla 7' in p['norma'] and p['codigo'] == 'NTP370400'
    assert (p['po_w'], p['pc_w'], p['io_pct'], p['uk_pct']) == fichas['tablas'][1]['fichas'][kva]
    assert p['carga_pct_prevista'] == pytest.approx(100 * kva_carga / (kva * unidades))


def test_la_tabla_sale_de_la_tension_primaria(fichas):
    """020:RF-8 / 020:RF-11 — 10 kV va a la Tabla 6, 22,9 kV a la 7; fuera de todo rango, ninguna,
    y la propuesta dice la tensión."""
    tablas = fichas['tablas']
    assert 'Tabla 6' in tabla_para(tablas, 10.0)['norma']
    assert 'Tabla 6' in tabla_para(tablas, 17.5)['norma']
    assert 'Tabla 7' in tabla_para(tablas, 22.9)['norma']
    assert tabla_para(tablas, 60.0) is None
    p = proponer(500.0, 60.0, tablas, 80)
    assert p['kva'] is None and '60' in p['motivo']
    assert proponer(500.0, None, tablas, 80)['kva'] is None


def test_regla_minima_con_potencias_sorteadas(fichas):
    """020:RF-6 / 020:RF-7 — para cualquier demanda la carga prevista queda en el umbral o por
    debajo, y con la potencia anterior de la tabla (o una unidad menos) lo superaría."""
    rnd = random.Random(20261016)
    for _ in range(500):
        kv = rnd.choice([10.0, 13.2, 22.9, 33.0])
        umbral = rnd.choice([70, 80, 100])
        carga = rnd.uniform(1.0, 8000.0)
        tabla = tabla_para(fichas['tablas'], kv)
        p = proponer(carga, kv, fichas['tablas'], umbral)
        limite = umbral / 100.0
        assert carga <= limite * p['kva'] * p['unidades'] + 1e-9
        assert p['carga_pct_prevista'] <= umbral + 1e-9
        tamanos = sorted(tabla['fichas'])
        if p['unidades'] == 1:
            menores = [k for k in tamanos if k < p['kva']]
            assert not menores or carga > limite * menores[-1]
        else:
            assert p['kva'] == tamanos[-1]
            assert carga > limite * p['kva'] * (p['unidades'] - 1)


def test_sin_tablas_no_hay_propuesta():
    """020:RF-10 — sin tablas en el perfil, ninguna propuesta y el motivo lo dice."""
    p = proponer(500.0, 10.0, [], 80)
    assert p['kva'] is None and 'perfil' in p['motivo']


def test_nombre_del_tipo_propio_como_en_pa217():
    """020:RF-19 / 020:RF-21 — el nombre lleva potencia, norma, tensiones y grupo, y redondea
    los 22,899999618 kV con que DIgSILENT guarda 22,9: así sale el tipo creado en PA217."""
    from igea_dgs.trafos_sed import nombre_tipo

    assert (nombre_tipo(630, 'NTP370400', 22.899999618530273, 219.9999988079071, 'DYN5')
            == 'TR_630kVA_NTP370400_22.9-220V_DYN5')
    assert nombre_tipo(37.5, '', 10.0, 380.0, 'dyn11') == 'TR_37.5kVA_10-380V_DYN11'
