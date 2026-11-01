"""Spec 053: el catálogo de fichas crece con cada código nuevo, sin tocar lo que ya tiene.

El catálogo se arma aquí con la forma del real (sus columnas) y fichas de N2XSY y AAAC; los
códigos nuevos son los que trajo Electro Oriente (2026-11-01).
"""
from __future__ import annotations

import math
import os
import random
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from igea_dgs import catalog as cat

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _fila(codigo, r1, x1, b1, amp, estado='ficha', fuente='Indeco (Nexans)'):
    d = dict.fromkeys(cat.COLUMNAS_CONDUCTOR, '')
    d.update({'codigo': codigo, 'material': cat.material_de_codigo(codigo),
              'seccion_mm2': cat.seccion_de_codigo(codigo), 'R1_modelo_ohm_km': r1 * 1.1,
              'R1_ficha_ohm_km': r1, 'X1_modelo_ohm_km': x1, 'R0_modelo_ohm_km': r1,
              'X0_modelo_ohm_km': x1, 'B1_modelo_uS_km': b1, 'ampacidad_modelo_A': amp,
              'estado': estado, 'fuente': fuente})
    return [d[c] for c in cat.COLUMNAS_CONDUCTOR]


def _catalogo(tmp_path: Path) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    aereos = wb.create_sheet('conductores_aereos')
    aereos.append(list(cat.COLUMNAS_CONDUCTOR))
    aereos.append(_fila('AA05003D', 0.6755, 0.4669, 3.154, 195.0))
    aereos.append(_fila('AA18503D', 0.1813, 0.3767, 4.354, 455.0))
    cables = wb.create_sheet('cables_subterraneos')
    cables.append(list(cat.COLUMNAS_CONDUCTOR))
    cables.append(_fila('N205003D', 0.387, 0.1513, 67.91, 225.0))
    cables.append(_fila('N212003D', 0.153, 0.1305, 95.62, 370.0))
    ruta = tmp_path / 'catalogo_parametros.xlsx'
    wb.save(ruta)
    return ruta


def _filas(ruta: Path, hoja: str) -> dict[str, dict]:
    ws = load_workbook(ruta, data_only=True)[hoja]
    valores = list(ws.iter_rows(values_only=True))
    return {v[0]: dict(zip(valores[0], v)) for v in valores[1:] if v and v[0]}


def test_crece_sin_tocar_lo_que_tiene(tmp_path):
    """053:RF-1, 053:RF-6, 053:RF-7 — una fila por código nuevo, en su hoja; las de antes,
    iguales; cada nueva dice su estado, su regla, su fuente y dónde apareció; sin fichero
    temporal al terminar; y otra vez con los mismos códigos no añade nada."""
    ruta = _catalogo(tmp_path)
    antes = {h: _filas(ruta, h) for h in ('conductores_aereos', 'cables_subterraneos')}
    nuevas = cat.ampliar_catalogo(ruta, ['AS05003G', 'AA05003D', 'N230003G', 'AS05003G'],
                                  origen='Empresa X (red.bak)', fecha='2026-11-01')
    assert [f['codigo'] for f in nuevas] == ['AS05003G', 'N230003G']
    aereos, cables = _filas(ruta, 'conductores_aereos'), _filas(ruta, 'cables_subterraneos')
    for hoja, filas in (('conductores_aereos', aereos), ('cables_subterraneos', cables)):
        assert all(filas[c] == f for c, f in antes[hoja].items()), 'una fila de antes cambió'
    assert 'AS05003G' in aereos and 'N230003G' in cables
    obs = aereos['AS05003G']['observaciones']
    assert '2026-11-01' in obs and 'Empresa X' in obs and 'N205003D' in obs and '053' in obs
    assert aereos['AS05003G']['estado'] == 'por_confirmar' and 'Deducido' in aereos['AS05003G']['fuente']
    assert not list(tmp_path.glob('*.tmp*'))
    assert cat.ampliar_catalogo(ruta, ['AS05003G', 'N230003G']) == []


def test_misma_familia_por_relacion_de_secciones(tmp_path):
    """053:RF-2 — la sección más cercana de la familia: R por Sref/S, X y B1 iguales, y la
    ampacidad por (S/Sref)^0,75."""
    rng = random.Random(SEMILLA)
    seccion = rng.choice([70, 95, 150, 240, 300, 400])
    codigo = f'N2{seccion * 10:04d}3G'
    filas = list(_filas(_catalogo(tmp_path), 'cables_subterraneos').values())
    d = cat.deducir_conductor(codigo, filas)
    ref = min((50.0, 120.0), key=lambda s: abs(math.log(s / seccion)))
    r_ref, x_ref, a_ref = (0.387, 0.1513, 225.0) if ref == 50.0 else (0.153, 0.1305, 370.0)
    assert d['R1_modelo_ohm_km'] == pytest.approx(r_ref * ref / seccion, rel=1e-5), SEMILLA
    assert d['X1_modelo_ohm_km'] == x_ref and d['estado'] == 'por_confirmar'
    assert d['ampacidad_modelo_A'] == pytest.approx(a_ref * (seccion / ref) ** 0.75, abs=0.1)


def test_aaac_con_su_ficha_universal(tmp_path):
    """053:RF-3 — un AAAC toma la R de la ficha universal del conversor y queda «derivado»."""
    filas = list(_filas(_catalogo(tmp_path), 'conductores_aereos').values())
    d = cat.deducir_conductor('AA24003G', filas)
    assert d['R1_ficha_ohm_km'] == pytest.approx(cat.aaac_r20_ohm_km(240.0))
    assert d['estado'] == 'derivado' and d['X1_modelo_ohm_km'] == pytest.approx(0.3767)
    assert cat.AAAC_FUENTE in d['fuente']


def test_autoportante_como_el_cable_xlpe_con_su_material(tmp_path):
    """053:RF-4 — autoportante de cobre: el N2XSY de su sección; de aluminio: la R por
    ρAl/ρCu (IEC 60228) y la ampacidad por √(ρCu/ρAl). AS050 queda en 0,634 Ω/km, cerca de
    los 0,641 de la norma para el aluminio de 50 mm²."""
    ruta = _catalogo(tmp_path)
    filas = list(_filas(ruta, 'cables_subterraneos').values())
    cobre = cat.deducir_conductor('CS05003G', filas)
    assert cobre['R1_modelo_ohm_km'] == pytest.approx(0.387) and cobre['X1_modelo_ohm_km'] == 0.1513
    al = cat.deducir_conductor('AS05003G', filas)
    rel = cat.RHO20_AL_OHM_MM2_M / cat.RHO20_CU_OHM_MM2_M
    assert al['R1_modelo_ohm_km'] == pytest.approx(0.387 * rel)
    assert al['R1_modelo_ohm_km'] == pytest.approx(0.641, rel=0.02)
    assert al['ampacidad_modelo_A'] == pytest.approx(225.0 / math.sqrt(rel), abs=0.1)
    assert al['B1_modelo_uS_km'] == pytest.approx(67.91)


def test_lo_que_no_se_deduce_queda_pendiente_y_se_dice(tmp_path):
    """053:RF-5 — sin familia ni equivalente, la fila va sin valores y pendiente de ficha."""
    ruta = _catalogo(tmp_path)
    (fila,) = cat.ampliar_catalogo(ruta, ['ZZ05003G'])
    assert fila['estado'] == 'por_confirmar' and 'Pendiente' in fila['fuente']
    assert fila.get('R1_modelo_ohm_km') is None and 'ZZ' in fila['observaciones']


def test_la_fuente_vnr_hace_crecer_el_catalogo_y_lo_usa(tmp_path):
    """053:RF-1, 053:RF-7, 053:RF-8 — la conversión VNR-GIS añade los códigos sin R y X al
    catálogo (uno, sin perfil de empresa) y los usa en la misma conversión."""
    from vnr_etl.models.canonical import CanonicalModel, ConductorType

    from igea_dgs.sources import vnr

    ruta = _catalogo(tmp_path)
    modelo = CanonicalModel()
    modelo.conductor_types += [ConductorType(conductor_code='AS05003G'),
                               ConductorType(conductor_code='AA05003D')]
    assert vnr.fichas_del_catalogo(modelo, ruta)['sin_ficha'] == 1
    ampliado = vnr.ampliar_con_lo_que_falta(modelo, origen='Empresa X', catalogo=ruta)
    assert [a['codigo'] for a in ampliado] == ['AS05003G']
    assert vnr.fichas_del_catalogo(modelo, ruta) == {'completados': 2, 'sin_ficha': 0}
    as050 = next(t for t in modelo.conductor_types if t.conductor_code == 'AS05003G')
    assert as050.r1_ohm_km == pytest.approx(0.387 * cat.RHO20_AL_OHM_MM2_M / cat.RHO20_CU_OHM_MM2_M)
    assert vnr.ampliar_con_lo_que_falta(modelo, catalogo=ruta) == [], 'nada más que añadir'
