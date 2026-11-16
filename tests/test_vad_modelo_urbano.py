"""Spec 108 T14, primera parte (VAD-A5U): las incoherencias del Anexo 5 del TdR, resueltas como decidió 28.

Valores sintéticos sorteados; el registro real de ``config/vad`` y ``config/normativa``. Ninguna cifra del TdR se escribe
en las pruebas: se leen del registro.
"""
from __future__ import annotations

import ast
import json
import math
import random
import shutil
from pathlib import Path

import pytest

from convertersmartgrid.pide_economia import frc
from convertersmartgrid import registro_normativo as rn
from convertersmartgrid.registro_normativo import cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad import modelo_urbano as mu
from convertersmartgrid.vad.formulas import evaluar

RAIZ = Path(__file__).resolve().parents[1]
VAD = RAIZ / 'config' / 'vad'
NORMATIVA = RAIZ / 'config' / 'normativa'
SEMILLAS = (20261115, 644573672)


@pytest.fixture
def reg():
    return cargar_registro(VAD, NORMATIVA)


def _formulas(reg, clave):
    return reg.regla(clave).regla.valor['formulas']


def _editado(tmp_path, cambio):
    vad, norm = tmp_path / 'vad', tmp_path / 'normativa'
    shutil.copytree(VAD, vad)
    shutil.copytree(NORMATIVA, norm)
    for f in vad.glob('*.json'):
        datos = json.loads(f.read_text(encoding='utf-8'))
        if cambio(datos):
            f.write_text(json.dumps(datos, ensure_ascii=False), encoding='utf-8')
    return cargar_registro(vad, norm)


def _zona(semilla):
    rng = random.Random(semilla)
    return {'PTR_INICIAL': rng.choice((250.0, 400.0, 630.0)), 'Fu_MTBT': rng.uniform(0.6, 0.9),
            'N_CLIENTES': rng.uniform(0, 3), 'P_CLIENTES': rng.uniform(5, 30), 'COS_fi': rng.uniform(0.85, 0.98),
            'AP_D': rng.uniform(5, 40), 'delta_BT': rng.uniform(5, 40), 'FP_DIS': rng.uniform(0.9, 1.0),
            'FD_BT': rng.uniform(1.0, 1.5), 'FD_CT': rng.uniform(1.0, 1.4), 'Aj': rng.uniform(1.0, 1.2),
            'NCLMTI': rng.uniform(0, 2)}


def _a(z):
    return z['PTR_INICIAL'] * z['Fu_MTBT'] - z['N_CLIENTES'] * z['P_CLIENTES'] / z['COS_fi']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tri_area_en_forma_cerrada_en_la_mad(reg, semilla):
    """108:RF-6 — decisión (1) de 28: T = A·FP_DIS/(1000·δ_BT·FD_BT) en la MAD, con residuo ≤ 1e-9 en R_BT y en
    TRI_AREA, y NTRI de la fórmula del registro con esa T."""
    z = _zona(semilla)
    sol = mu.resolver_tri_area(z, reg, 'mad')
    assert not sol.huecos, sol.huecos
    esperado = _a(z) * z['FP_DIS'] / (1000 * z['delta_BT'] * z['FD_BT'])
    assert sol.tri_area == pytest.approx(esperado, rel=1e-12)
    assert sol.residuo_r_bt is not None and sol.residuo_r_bt <= 1e-9 * max(1, sol.r_bt)
    assert sol.residuo_tri_area is not None and sol.residuo_tri_area <= 1e-9
    f = _formulas(reg, 'vad.anexo5.mad.bt_inicial')
    r_bt = evaluar(f['R_BT'], {**z, 'TRI_AREA': sol.tri_area})
    assert sol.r_bt == pytest.approx(r_bt)
    assert evaluar(_formulas(reg, 'vad.anexo5.mad.ntri_ncti')['TRI_AREA'], {'R_BT': r_bt}) == pytest.approx(sol.tri_area)
    ntri = evaluar(_formulas(reg, 'vad.anexo5.mad.ntri_ncti')['NTRI'],
                   {**{k: z[k] for k in ('delta_BT', 'FD_CT', 'Aj', 'FP_DIS', 'PTR_INICIAL', 'Fu_MTBT', 'N_CLIENTES',
                                         'P_CLIENTES', 'COS_fi', 'AP_D')}, 'TRI_AREA': sol.tri_area})
    assert sol.ntri == pytest.approx(ntri)
    assert any('forma cerrada' in a for a in sol.avisos)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_tri_area_en_forma_cerrada_en_el_resto(reg, semilla):
    """108:RF-6 — la misma resolución con la R_BT del resto (sin «− AP_D/1000»): T = A/(1000·δ_BT·FD_BT/FP_DIS + AP_D)."""
    z = _zona(semilla)
    sol = mu.resolver_tri_area(z, reg, 'resto')
    assert not sol.huecos, sol.huecos
    esperado = _a(z) / (1000 * z['delta_BT'] * z['FD_BT'] / z['FP_DIS'] + z['AP_D'])
    assert sol.tri_area == pytest.approx(esperado, rel=1e-12)
    assert sol.residuo_r_bt is not None and sol.residuo_r_bt <= 1e-9 * max(1, sol.r_bt)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_el_residuo_sustituye_t_en_las_formulas_transcritas_de_cada_rama(reg, semilla):
    """108:RF-6 — c3 (v2, e): T se sustituye en las fórmulas R_BT y TRI_AREA TRANSCRITAS de la rama (las del registro,
    evaluadas aquí con el intérprete, sin forma derivada). En la MAD la forma de c3, T = A·FP/(1000·δ·FD), y la
    propia son la misma y cumplen el residuo ≤ 1e-9; en el resto la de c3 NO lo cumple (su R_BT no lleva el
    «− AP_D/1000» que la cancela) y la propia sí."""
    z = _zona(semilla)
    assert z['AP_D'] > 0
    tri = _formulas(reg, 'vad.anexo5.mad.ntri_ncti')['TRI_AREA']
    t_c3 = _a(z) * z['FP_DIS'] / (1000 * z['delta_BT'] * z['FD_BT'])

    def residuo(t, rama):
        r_bt = evaluar(_formulas(reg, f'vad.anexo5.{rama}.bt_inicial')['R_BT'], {**z, 'TRI_AREA': t})
        return abs(evaluar(tri, {'R_BT': r_bt}) - t)
    mad = mu.resolver_tri_area(z, reg, 'mad')
    resto = mu.resolver_tri_area(z, reg, 'resto')
    assert mad.tri_area is not None and resto.tri_area is not None, (mad.huecos, resto.huecos)
    assert residuo(t_c3, 'mad') <= 1e-9 and residuo(mad.tri_area, 'mad') <= 1e-9
    assert mad.tri_area == pytest.approx(t_c3, rel=1e-12)
    assert residuo(resto.tri_area, 'resto') <= 1e-9
    assert residuo(t_c3, 'resto') > 1e-6 * t_c3
    for rama, t in (('mad', t_c3), ('resto', resto.tri_area)):
        _, r1, r2 = mu.residuos(t, z, reg, rama)
        assert r1 <= 1e-9 and r2 <= 1e-9
    _, r1, _ = mu.residuos(t_c3, z, reg, 'resto')
    assert r1 > 1e-6 * t_c3


def test_sin_solucion_es_un_hueco_nombrado(reg):
    """108:RF-6 — A ≤ 0 o el denominador de R_BT ≤ 0: hueco nombrado, sin cifra."""
    z = _zona(SEMILLAS[0])
    sin_potencia = {**z, 'N_CLIENTES': 100.0, 'P_CLIENTES': 100.0}
    sol = mu.resolver_tri_area(sin_potencia, reg, 'mad')
    assert sol.tri_area is None and sol.ntri is None and any('A =' in h for h in sol.huecos)
    sin_densidad = {**z, 'delta_BT': 0.001, 'AP_D': 500.0}
    sol = mu.resolver_tri_area(sin_densidad, reg, 'mad')
    assert sol.tri_area is None and any('denominador' in h for h in sol.huecos)


def test_la_lectura_a_del_parentesis_de_ntri_y_la_b_se_detecta(reg, tmp_path):
    """108:RF-6 — decisión (2) de 28: vale la lectura (a) en las dos ramas; una lectura (b) en el registro se rechaza."""
    assert mu.comprobar_lectura_ntri(reg, 'mad') == 'a'
    assert mu.comprobar_lectura_ntri(reg, 'resto') == 'a'

    def lectura_b(datos):
        for r in datos.get('reglas') or ():
            if r['clave'] == 'vad.anexo5.mad.ntri_ncti':
                r['valor']['formulas']['NTRI'] = ('1000 * delta_BT * FD_CT * Aj / (FP_DIS * (PTR_INICIAL * Fu_MTBT - '
                                                  'N_CLIENTES * P_CLIENTES / COS_fi) - AP_D * TRI_AREA)')
                return True
        return False
    otro = _editado(tmp_path, lectura_b)
    with pytest.raises(VadError, match=r'lectura \(b\)'):
        mu.comprobar_lectura_ntri(otro, 'mad')
    with pytest.raises(VadError, match=r'lectura \(b\)'):
        mu.resolver_tri_area(_zona(SEMILLAS[1]), otro, 'mad')


def _tasa_lce(reg) -> float:
    """La tasa del art. 79 de la LCE tal como la lee el VAD: siguiendo la remisión de ``vad.tasa_actualizacion`` con el
    único resolvedor del registro (UNA-TASA)."""
    assert hasattr(rn, 'regla_remitida'), 'el registro no resuelve la remisión de vad.tasa_actualizacion'
    return rn.regla_remitida(reg, 'vad.tasa_actualizacion').valor


def test_la_tasa_i_remite_al_articulo_79_y_es_la_del_anexo_6(reg):
    """108:RF-6, 108:RF-9 — la «i» del Anexo 5 sale de la remisión del cap. 5 (líneas 1347-1350), que lleva a la tasa
    del art. 79 de la LCE (UNA-TASA: ``vad.tasa_actualizacion`` remite a ``pit.tasa_actualizacion``); FRC(i, 30) es el
    vad.frc del registro a 6 decimales y 1/FRC es el Kim del Anexo 6, con la función común pide_economia.frc."""
    t = mu.tasa_i(reg)
    assert t.tasa == _tasa_lce(reg)
    assert t.principal.regla.clave == 'pit.tasa_actualizacion' and t.principal.norma.acto == 'DL 25844', (
        f'la «i» del Anexo 5 no sale de la tasa de la LCE: sale de {t.principal.regla.clave}')
    assert t.remision.regla.lineas == '1347-1350' and 'artículo 79' in t.remision.regla.cita_literal
    assert round(frc(t.tasa, t.vida_util), 6) == reg.regla('vad.frc').regla.valor
    kim = reg.regla('vad.anexo6.equipos_mt.reconectadores').regla.valor['Kim']
    assert mu.factor_capitalizacion(reg) == pytest.approx(1 / frc(t.tasa, t.vida_util))
    assert abs(mu.factor_capitalizacion(reg) - kim) < 0.01      # el TdR escribe 8,05 por 8,055 (z28)


def test_los_simbolos_sin_definir_son_entradas_sin_valor_por_defecto(reg):
    """108:RF-6, 108:RF-13 — decisión (3) de 28: CCT_INICIAL, b, K_CT, cr, Ic y clientes_AT/MT, del perfil o hueco."""
    sin = mu.entradas({}, reg, 'mad')
    nombrados = {h.split(':')[0] for h in sin.huecos}
    assert nombrados == {'CCT_INICIAL', 'b', 'K_CT', 'cr', 'Ic', 'clientes_ATMT'}
    assert not sin.valores
    tabla = reg.regla('vad.anexo5.entradas_sin_definir').regla.valor
    perfil = {d['perfil']: float(k) for k, d in enumerate(tabla.values(), start=1)}
    con = mu.entradas(perfil, reg, 'mad')
    assert not con.huecos and set(con.valores) == nombrados
    assert {h.split(':')[0] for h in mu.entradas({}, reg, 'resto').huecos} == {'CCT_INICIAL', 'b', 'K_CT', 'cr'}


def test_los_dos_incrementos_del_5_se_suman_y_se_avisa_el_compuesto(reg):
    """108:RF-6 — decisión (3) de 28: ×(1 + a + b), y el aviso da ×(1 + a)(1 + b); las cifras, del registro."""
    v = reg.regla('vad.anexo5.mad.mt.derivaciones').regla.valor
    a, b = v['incremento_densidad_no_uniforme'], v['incremento_trazado']
    inc = mu.incremento_derivaciones(reg)
    assert inc.factor == pytest.approx(1 + a + b)
    assert inc.compuesto == pytest.approx((1 + a) * (1 + b))
    assert f'{1 + a + b:.4f}' in inc.aviso and f'{(1 + a) * (1 + b):.4f}' in inc.aviso
    assert mu.incremento_derivaciones(reg, 'resto').factor == pytest.approx(1 + a + b)


def test_te_sale_de_la_funcion_de_perdidas_comun(reg, tmp_path):
    """108:RF-6, 108:RF-8 — Te del Anexo 5 = la función de pérdidas común (INF-FP); si el coeficiente común cambia y el
    Anexo 5 no, se nota."""
    for tu in (2500.0, 4380.0, 7000.0):
        te = mu.tiempo_equivalente(tu, reg)
        assert te == pytest.approx(evaluar(_formulas(reg, 'vad.anexo5.mad.perdidas')['Te'], {'Tu': tu}))

    def mutar(datos):
        for r in datos.get('reglas') or ():
            if r['clave'] == 'vad.anexo4.factor_perdidas_empirico':
                r['valor']['coef_lineal'] = r['valor']['coef_lineal'] + 0.01
                return True
        return False
    with pytest.raises(VadError, match='función de pérdidas común'):
        mu.tiempo_equivalente(4380.0, _editado(tmp_path, mutar))


def test_las_perdidas_de_mt_con_los_factores_de_1000_y_su_prueba_de_unidades(reg):
    """108:RF-6 — decisión (3) de 28: con L_RADIAL en m, r en ohm/km, la corriente en kA y ce en USD/kWh, cp_MT coincide
    con el cálculo en unidades SI hecho a mano (W·h → kWh)."""
    v = {'Pif': 25.0, 'Fu_ATMT': 0.8, 'U_NOMINAL_MT': 10.0, 'CS': 6.0, 'L_RADIAL': 3600.0, 'r': 0.25, 'Te': 3000.0,
         'ce': 0.08, 'Kp_MT': 9.5, 'fF_MT': 1.02, 'fA_MT': 1.01, 'fS_MT': 1.03, 'fC_MT': 1.04}
    usd, aviso = mu.perdidas_mt(v, reg)
    i_a = v['Pif'] * 1e6 * v['Fu_ATMT'] / (math.sqrt(3) * v['U_NOMINAL_MT'] * 1e3 * v['CS'])
    wh = 3 * i_a ** 2 * (v['r'] / 1000) * (v['L_RADIAL'] / 2) * v['Te']
    a_mano = wh / 1000 * v['ce'] * v['Kp_MT'] * v['fF_MT'] * v['fA_MT'] * v['fS_MT'] * v['fC_MT']
    assert usd == pytest.approx(a_mano, rel=1e-12)
    assert 'kWh' in aviso and 'km' in aviso


def test_las_dos_l_radial_son_magnitudes_distintas(reg):
    """108:RF-6 — L_RADIAL [m] (b.) y L_RADIAL_km2 [m/km2] (a.1) conviven con nombres distintos en el registro."""
    geo = _formulas(reg, 'vad.anexo5.mad.mt.geometria')
    perd = _formulas(reg, 'vad.anexo5.mad.perdidas')
    v = {'Frg': 1.2, 'R': 900.0, 'CS': 6.0}
    assert evaluar(geo['L_RADIAL'], v) == pytest.approx(v['Frg'] * v['R'])
    assert evaluar(perd['L_RADIAL_km2'], v) == pytest.approx(v['Frg'] * v['CS'] / (math.pi * v['R']) * 1e6)
    assert 'L_RADIAL' not in perd and perd['Leq'] == 'L_RADIAL / 2'


def test_ninguna_cifra_del_tdr_esta_en_el_codigo(reg):
    """108:RF-13 — las cifras del Anexo 5 y la tasa viven en el registro: ningún literal de modelo_urbano.py es una."""
    v = reg.regla('vad.anexo5.mad.mt.derivaciones').regla.valor
    cifras = {v['incremento_densidad_no_uniforme'], v['incremento_trazado'], _tasa_lce(reg),
              reg.regla('vad.frc').regla.valor, reg.regla('vad.anexo5.mad.mt.geometria').regla.valor['Frg']}
    arbol = ast.parse(Path(mu.__file__).read_text(encoding='utf-8'))
    literales = {n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant)
                 and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}
    assert not (literales & cifras), literales & cifras
    assert 30 not in literales
