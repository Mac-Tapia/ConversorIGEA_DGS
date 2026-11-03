"""Spec 073: el número de bancos lo define la tensión en las ventanas de valle.

Usuario, 2026-11-02: «eso lo debe definir las demandas en ventanas de valle donde podría ocurrir
sobretensiones». Curvas sorteadas, sin tamaños ni nombres fijos; la red del oráculo es la de
``test_optimizacion_oraculo``; DIgSILENT, el doble ``fake_pf``.
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from convertersmartgrid import valle as vl

INICIO = datetime(2026, 3, 1)
PASO = timedelta(minutes=15)


def _forma(t: datetime) -> float:
    """Una forma diaria: de madrugada baja, de tarde alta."""
    return 0.65 + 0.35 * math.sin(2 * math.pi * (t.hour + t.minute / 60 - 9) / 24)


def _curva(rng: random.Random, dias: int, *, kw=None, fp=0.97, por_dia=None):
    """Curva de 15 minutos con ruido y una demanda distinta cada día."""
    kw = kw if kw is not None else rng.uniform(800, 9000)
    por_dia = por_dia or [rng.uniform(0.75, 1.0) for _ in range(dias)]
    out = []
    for d in range(dias):
        for i in range(96):
            t = INICIO + timedelta(days=d) + i * PASO
            p = kw * _forma(t) * por_dia[d] * rng.uniform(0.98, 1.02)
            out.append((t, p, p * math.tan(math.acos(fp))))
    return out


def _bruto_minimo(curvas):
    """El mínimo por recorrido directo, para contrastar."""
    por: dict = {}
    for c in curvas:
        for t, kw, q in c:
            a, b = por.get(t, (0.0, 0.0))
            por[t] = (a + kw, b + q)
    return min(por, key=lambda t: (math.hypot(*por[t]), t)), por


def _bruta_ventana(por, n):
    dias: dict = {}
    for t, (kw, q) in por.items():
        dias.setdefault(t.date(), []).append(math.hypot(kw, q))
    orden = sorted(dias)
    mejor = None
    for i in range(len(orden) - n + 1):
        trozo = [x for d in orden[i:i + n] for x in dias[d]]
        media = sum(trozo) / len(trozo)
        if mejor is None or media < mejor[0] - 1e-12:
            mejor = (media, orden[i], orden[i + n - 1])
    return mejor


@pytest.mark.parametrize('semilla', range(6))
def test_ventana_instante_minimo_con_su_kw_y_kvar(semilla):
    """073:RF-1, 073:RF-4, 073:RF-9 — el instante de menor kVA, con kW y kVAR de ese instante,
    igual al del recorrido directo; la suma de los medidores, vectorial; misma entrada, mismo valle."""
    rng = random.Random(semilla)
    dias = rng.randint(5, 20)
    medidores = {f'M{i}': _curva(rng, dias) for i in range(rng.randint(1, 4))}
    v = vl.valle_de_alcance('alimentador', medidores, vl.Ajustes())
    t, por = _bruto_minimo(medidores.values())
    assert v.comprobado and v.instante['fecha'] == t
    assert v.instante['kw'] == pytest.approx(por[t][0]) and v.instante['kvar'] == pytest.approx(por[t][1])
    assert v.instante['kva'] == pytest.approx(math.hypot(*por[t]))
    desordenadas = {k: rng.sample(c, len(c)) for k, c in medidores.items()}
    assert vl.valle_de_alcance('alimentador', desordenadas, vl.Ajustes()) == v


def test_ventana_suma_vectorial_con_kvar_de_signo_contrario():
    """073:RF-4 — con la Q de un medidor capacitiva, el kVA no es la suma de los kVA de cada uno."""
    t = INICIO
    a = [(t + i * PASO, 100.0 + i, 80.0) for i in range(96 * 3)]
    b = [(t + i * PASO, 100.0 + i, -80.0) for i in range(96 * 3)]
    v = vl.valle_de_alcance('set', {'T1': a, 'T2': b}, vl.Ajustes())
    assert v.instante['kvar'] == pytest.approx(0.0)
    assert v.instante['kva'] == pytest.approx(v.instante['kw'])
    assert v.alcance == 'set'


@pytest.mark.parametrize('semilla', range(6))
def test_ventana_de_n_dias_contiguos(semilla):
    """073:RF-2 — los N días contiguos de menor demanda media, con el instante mínimo dentro; N sorteado."""
    rng = random.Random(semilla)
    dias = rng.randint(10, 40)
    n = rng.randint(2, 7)
    curva = _curva(rng, dias)
    v = vl.valle_de_alcance('sistema', {'B': curva}, vl.Ajustes(dias_ventana=n))
    _t, por = _bruto_minimo([curva])
    media, desde, hasta = _bruta_ventana(por, n)
    assert v.ventana['desde'] == desde and v.ventana['hasta'] == hasta and v.ventana['dias'] == n
    assert v.ventana['kva'] == pytest.approx(media)
    dentro = [t for t in por if desde <= t.date() <= hasta]
    menor = min(dentro, key=lambda t: (math.hypot(*por[t]), t))
    assert v.ventana['instante']['fecha'] == menor


def test_ventana_sin_dias_en_el_perfil_usa_el_instante_y_lo_dice():
    """073:RF-3 — sin ``valle.dias_ventana``, el instante mínimo y el aviso; sin cifra en el código."""
    v = vl.valle_de_alcance('alimentador', {'M': _curva(random.Random(3), 9)}, vl.ajustes_de({}))
    assert v.ventana is None and v.instante is not None
    assert any('dias_ventana' in a for a in v.avisos)
    assert vl.ajustes_de({'valle': {'dias_ventana': 5}}).dias_ventana == 5
    assert vl.ajustes_de({}).dias_ventana is None


def test_ventana_un_hueco_de_un_medidor_no_es_valle():
    """073:RF-5 — un medidor sin ese registro bajaría la suma: ese instante no cuenta."""
    rng = random.Random(4)
    a, b = _curva(rng, 10, kw=1000.0), _curva(rng, 10, kw=1000.0)
    t_real = _bruto_minimo([a, b])[0]
    # Al mediodía del día 5 a «b» le faltan registros: sin la regla, «a» sola sería el mínimo.
    hueco = {INICIO + timedelta(days=5, hours=12) + i * PASO for i in range(3)}
    b = [x for x in b if x[0] not in hueco]
    v = vl.valle_de_alcance('alimentador', {'A': a, 'B': b}, vl.Ajustes())
    assert v.instante['fecha'] == t_real and v.instante['fecha'] not in hueco
    assert v.apartados['hueco']['registros'] == len(hueco)


@pytest.mark.parametrize('motivo', ['cero', 'signo', 'congelado', 'duplicado', 'franja', 'aislada'])
def test_ventana_dato_dudoso_no_define_el_minimo(motivo):
    """073:RF-6 — un cero, un signo contrario, un medidor congelado, un duplicado que no cuadra, una
    salida de servicio o un disparo de un registro se apartan con su motivo y no son el valle."""
    rng = random.Random(11)
    curva = _curva(rng, 15, kw=2000.0)
    limpio = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    dia = 7
    i0 = next(i for i, x in enumerate(curva) if x[0] == INICIO + timedelta(days=dia, hours=11))
    if motivo == 'cero':
        curva[i0] = (curva[i0][0], 0.0, 0.0)
    elif motivo == 'signo':
        curva[i0] = (curva[i0][0], -curva[i0][1], curva[i0][2])
    elif motivo == 'congelado':
        valor = 0.4 * curva[i0][1]
        for j in range(12):
            curva[i0 + j] = (curva[i0 + j][0], valor, 0.1 * valor)
    elif motivo == 'duplicado':
        curva.insert(i0 + 1, (curva[i0][0], 1.0, 0.1))
    elif motivo == 'franja':
        # Una salida de servicio de horas: residuales que no llegan a cero.
        for j in range(16):
            curva[i0 + j] = (curva[i0 + j][0], 12.0 + j, 1.0)
    elif motivo == 'aislada':
        curva[i0] = (curva[i0][0], 0.45 * curva[i0][1], 0.45 * curva[i0][2])
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.instante['fecha'] == limpio.instante['fecha'], v.apartados
    assert v.apartados[motivo]['registros'] >= 1
    assert v.apartados[motivo]['motivo']


def test_ventana_el_valle_real_de_cada_noche_no_se_aparta():
    """073:RF-6 — la noche baja todas las noches: su franja también baja, y no es una salida."""
    rng = random.Random(21)
    curva = [(t, kw * (0.15 if 2 <= t.hour < 5 else 1.0), q * (0.15 if 2 <= t.hour < 5 else 1.0))
             for t, kw, q in _curva(rng, 12, kw=3000.0)]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert 2 <= v.instante['fecha'].hour < 5
    assert 'franja' not in v.apartados and 'aislada' not in v.apartados


def test_ventana_convencion_de_signo_al_reves_no_es_error():
    """073:RF-6 — un medidor que exporta en negativo se toma con el signo de su mediana."""
    curva = [(t, -kw, q) for t, kw, q in _curva(random.Random(5), 8, kw=1000.0)]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.comprobado and v.instante['kw'] > 0 and 'signo' not in v.apartados


def test_ventana_un_dia_sin_cobertura_corta_la_ventana():
    """073:RF-7 — una ventana no salta un día sin datos ni lo cuenta."""
    rng = random.Random(31)
    por_dia = [1.0] * 12
    por_dia[3] = por_dia[4] = por_dia[6] = 0.5       # los más bajos, con un hueco en medio
    curva = _curva(rng, 12, kw=1000.0, por_dia=por_dia)
    roto = INICIO.date() + timedelta(days=5)
    curva = [x for x in curva if x[0].date() != roto]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes(dias_ventana=3))
    assert not v.ventana['desde'] <= roto <= v.ventana['hasta']
    # Con el día 5 entero bastaría la ventana del 3 al 6; sin él, otra.
    assert (v.ventana['desde'], v.ventana['hasta']) != (INICIO.date() + timedelta(days=4), INICIO.date() + timedelta(days=6))


def test_ventana_no_hay_n_dias_contiguos_lo_dice():
    """073:RF-7 — sin N días contiguos con cobertura, sin ventana y con el motivo; queda el instante."""
    v = vl.valle_de_alcance('alimentador', {'M': _curva(random.Random(8), 4)}, vl.Ajustes(dias_ventana=9))
    assert v.ventana is None and v.comprobado
    assert any('9 días' in a for a in v.avisos)


def test_ventana_medidor_con_pocos_registros_sale_de_la_suma_y_se_dice():
    """073:RF-8 — Chincha, julio de 2026: 801 de 2 976 registros de una barra de 8 kW dejaban sin
    instantes a todas; ese medidor sale y se nombra."""
    rng = random.Random(41)
    bueno = _curva(rng, 20, kw=5000.0)
    malo = rng.sample(_curva(rng, 20, kw=8.0), 400)
    v = vl.valle_de_alcance('sistema', {'BUENO': bueno, 'MALO': malo}, vl.Ajustes())
    assert v.excluidos == ['MALO'] and any('MALO' in a for a in v.avisos)
    assert v.instante['fecha'] == _bruto_minimo([bueno])[0]


def test_ventana_sin_ningun_instante_valido_no_revienta():
    """073:RF-10 — sin instante válido, el valle sin comprobar con su motivo."""
    curva = [(INICIO + i * PASO, 0.0, 0.0) for i in range(96 * 3)]
    for entrada in ({'M': curva}, {'M': []}, {}):
        v = vl.valle_de_alcance('alimentador', entrada, vl.Ajustes())
        assert not v.comprobado and v.instante is None and v.motivo


def test_ventana_por_periodo():
    """073:RF-2 — con ``periodo`` (025:RF-7), solo los registros de ese mes o año."""
    curva = _curva(random.Random(2), 60)
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes(), periodo='2026-04')
    assert v.instante['fecha'].month == 4


def test_ventana_kvar_ausente_se_dice():
    """073:RF-4 — un medidor sin kVAR da el valle en kW, dicho; un dato sin Q no se inventa."""
    curva = [(t, kw, None) for t, kw, _q in _curva(random.Random(6), 5, kw=700.0)]
    v = vl.valle_de_alcance('alimentador', {'M': curva}, vl.Ajustes())
    assert v.comprobado and v.instante['kvar'] is None
    assert v.instante['kva'] == pytest.approx(v.instante['kw'])
    assert any('kVAR' in a for a in v.avisos)


def test_ventana_lee_con_los_lectores_de_demanda_medida(tmp_path):
    """073:RF-11 — el valle de un libro de cabecera, por ``demanda_medida.maximas``."""
    openpyxl = pytest.importorskip('openpyxl')
    curva = _curva(random.Random(9), 6, kw=1500.0)
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = 'MED1'
    hoja.append(['Local Time', 'kW', 'kVAR', 'kVA'])
    for t, kw, q in curva:
        hoja.append([t, kw, q, math.hypot(kw, q)])
    ruta = tmp_path / 'cabecera.xlsx'
    libro.save(ruta)
    curvas, avisos = vl.curvas_medidas([ruta], [('F1', 'MED1')])
    assert avisos == [] and len(curvas['MED1']) == len(curva)
    v = vl.valle_de_alcance('alimentador', curvas, vl.Ajustes())
    assert v.instante['fecha'] == _bruto_minimo([curva])[0]
    vacio, avisos = vl.curvas_medidas([ruta], [('F1', 'NO_ESTA')])
    assert vacio == {} and any('NO_ESTA' in a for a in avisos)


REAL = os.environ.get('CSG_DEMANDA_DIR', '').strip()


@pytest.mark.skipif(not REAL or not Path(REAL).is_dir(), reason='CSG_DEMANDA_DIR no apunta a la carpeta de la distribuidora')
def test_ventana_real_con_la_medicion_de_la_distribuidora():
    """073:RF-6, 073:RF-11 — con medición real, el valle no es un cero y lo apartado se nombra; no se
    guarda ni se copia nada de esos datos."""
    from convertersmartgrid import demanda_medida as dm

    def sub(prefijo):
        return next(p for p in Path(REAL).iterdir() if p.is_dir() and p.name.startswith(prefijo))

    meds = dm.leer_medidores(next(sub('1.').iterdir()))
    pares = [(a, dm.medidores_de(meds, a)[0]) for a in dict.fromkeys(m.alimentador for m in meds)
             if dm.medidores_de(meds, a)][:3]
    curvas, _avisos = vl.curvas_medidas([sub('2.')], pares)
    assert curvas
    vistos = 0
    for medidor, curva in curvas.items():
        v = vl.valle_de_alcance('alimentador', {medidor: curva}, vl.Ajustes(dias_ventana=7))
        if v.comprobado:
            vistos += 1
            assert v.instante['kva'] > 0
    assert vistos


def test_ventana_universal_sin_cifras_de_una_empresa():
    """073:RF-34 — el módulo no lleva nombres de empresa ni tamaños de banco, y dos perfiles dan dos
    ventanas distintas sobre la misma medición."""
    texto = Path(vl.__file__).read_text(encoding='utf-8').lower()
    for prohibido in ('electro', 'dunas', 'epsg', '450', '300 kvar'):
        assert prohibido not in texto, prohibido
    curva = _curva(random.Random(13), 30)
    a = vl.valle_de_alcance('alimentador', {'M': curva}, vl.ajustes_de({'valle': {'dias_ventana': 2}}))
    b = vl.valle_de_alcance('alimentador', {'M': curva}, vl.ajustes_de({'valle': {'dias_ventana': 9}}))
    assert a.ventana['dias'] == 2 and b.ventana['dias'] == 9
    with pytest.raises(vl.ValleError):
        vl.ajustes_de({'valle': {'dias_ventana': 0}})


# =========================================================================== escalera y oráculo
from convertersmartgrid import escalera_optima as eo  # noqa: E402
from convertersmartgrid import optimizacion_oraculo as oo  # noqa: E402
from test_optimizacion_oraculo import NUEVA, TIPOS, _exacto, _grafo, _id, _p  # noqa: E402


def _banco(n: int, kvar: float = 450.0, barra: str = 'B') -> dict:
    return {'clase': 'condensador', 'barra': barra, 'q_kvar': kvar * n, 'escalones': n}


def _puntos(factor_p: float, factor_q: float | None = None, factor_nuevas: float = 0.0) -> dict:
    """Un punto de valle como los da ``puntos_de_valle``."""
    return {'comprobado': True, 'motivo': '', 'avisos': [], 'pronostico': None,
            'puntos': [{'etiqueta': 'instante mínimo', 'fecha': '2026-03-08 03:15:00', 'kw': 100.0, 'kvar': 30.0,
                        'kva': 104.4, 'factor_p': factor_p, 'factor_q': factor_p if factor_q is None else factor_q,
                        'factor_nuevas': factor_nuevas, 'factores': {'F1': factor_p}, 'origen': 'medicion'}]}


def _red_con_margen():
    """Red donde la máxima aguanta dos bancos y el valle no: X alta y carga pequeña."""
    nueva = {**NUEVA, 'p_mw': 0.1, 'q_mvar': 0.02}
    return oo.Oraculo(_grafo(r=2.0, x=3.0, nueva_mw=0.1), [nueva], tipos=TIPOS)


def _fila(nombre, e, costo=100.0, escalones=('bancos',)):
    return {'nombre': nombre, 'escalones': escalones, 'costo': {'costo_anual': costo}, **e}


def test_sobretension_en_valle_se_cuela_por_la_fraccion():
    """073:RF-17, 073:RF-18 — el caso «la máxima cumple con bancos y el valle no». Sin el valle, la
    fracción de sorteos deja pasar el único instante de demanda baja y la variante se elige; con él, no."""
    ora, p = _red_con_margen(), _p(tension_max_pu=1.04)
    obras = [_banco(2)]
    factores = [1.0] * 19 + [0.05]                       # un instante de valle entre veinte sorteos
    sin_valle = ora.evaluar(obras, 1, p, factores)
    assert sin_valle['maxima'] and sin_valle['fraccion'] >= p.cumplimiento        # se cuela
    assert eo.elegir([_fila('2 bancos', sin_valle)], p)['elegida'] == '2 bancos'
    con_valle = ora.evaluar(obras, 1, p, factores, valle=_puntos(0.05))
    assert con_valle['maxima'] and con_valle['fraccion'] >= p.cumplimiento        # la máxima sigue cumpliendo
    assert con_valle['valle'] is False and con_valle['valle_u_max'] > p.tension_max_pu
    assert con_valle['valle_nodo'] == 'B' and con_valle['valle_fecha'] == '2026-03-08 03:15:00'
    r = eo.elegir([_fila('2 bancos', con_valle)], p)
    assert r['elegida'] is None and 'sin_confirmar_sorteos' not in r
    assert 'en valle' in r['tabla'][0]['motivo'] and '073:RF-17' in r['tabla'][0]['motivo']


def test_escalera_elegir_no_compensa_con_la_regla_de_la_maxima():
    """073:RF-18 — 063:RF-33 elige lo que cumple con la máxima aunque los sorteos no lo confirmen;
    lo que no cumple en valle no entra ahí, y la escalera sube al escalón siguiente."""
    p = _p()
    malo = {'maxima': True, 'fraccion': 0.5, 'valle': False, 'valle_motivos': ['B sube']}
    assert eo.elegir([_fila('banco', malo)], p)['elegida'] is None
    terna = {'maxima': True, 'fraccion': 1.0, 'valle': True}
    r = eo.elegir([_fila('banco', {**malo, 'fraccion': 1.0}), _fila('terna', terna, 900.0, ('terna',))], p)
    assert r['elegida'] == 'terna'
    assert r['aviso_valle'] and 'banco' in r['aviso_valle'] and 'por pasos' in r['aviso_valle']   # 073:RF-20, 073:RF-27


def test_escalera_sin_valle_no_bloquea_y_queda_marcada():
    """073:RF-24, 073:RF-31 — sin medición nada se bloquea, pero la variante dice «no comprobado en
    valle», también la elegida."""
    p = _p()
    r = eo.elegir([_fila('banco', {'maxima': True, 'fraccion': 1.0})], p)
    assert r['elegida'] == 'banco' and r['sin_comprobar_valle'] is True
    assert 'no comprobado en valle' in r['tabla'][0]['motivo']
    sin_bancos = eo.elegir([_fila('terna', {'maxima': True, 'fraccion': 1.0}, escalones=('terna',))], p)
    assert 'sin_comprobar_valle' not in sin_bancos


@pytest.mark.parametrize('semilla', range(5))
def test_escalera_modulos_como_el_flujo_exacto(semilla):
    """073:RF-19, 073:RF-34 — el número de módulos es el mayor que no pasa del límite superior en el
    flujo exacto, con tamaño de banco, red y límite sorteados: ninguna cifra en el código."""
    rng = random.Random(semilla)
    kvar = rng.choice([150.0, 300.0, 450.0, 600.0])
    x = rng.uniform(1.0, 4.0)
    hi = rng.uniform(1.01, 1.06)
    ora = oo.Oraculo(_grafo(r=1.0, x=x, nueva_mw=0.0), [], tipos=TIPOS)
    p = _p(tension_max_pu=hi, tolerancia_pu=0.0)
    r = oo.modulos_en_valle(ora, ['B'], kvar, _puntos(1.0), p)
    g, b = _grafo(r=1.0, x=x, nueva_mw=0.0), _id('B', 'ElmTerm')
    esperado = 0
    while _exacto(g, b, extra_q_mvar=kvar * (esperado + 1) / 1000) <= hi:
        esperado += 1
    assert r['modulos'] == esperado and r['comprobado'] and not r['por_tope']
    assert r['u_max'] is None or r['u_max'] <= hi + 1e-9


def test_escalera_modulos_con_tope_del_perfil_y_sin_efecto_no_cuelgan():
    """073:RF-19 — con ``escalera.modulos_max`` el tope es el suyo; sin efecto del banco, para y lo dice."""
    ora = oo.Oraculo(_grafo(nueva_mw=0.0), [], tipos=TIPOS)
    p = _p(tension_max_pu=5.0)
    r = oo.modulos_en_valle(ora, ['B'], 150.0, _puntos(1.0), p, tope=3)
    assert r['modulos'] == 3 and r['por_tope']
    sin_efecto = oo.modulos_en_valle(ora, ['NO_ESTA'], 150.0, _puntos(1.0), p)
    assert sin_efecto['modulos'] == 0 and sin_efecto['aviso']
    nada = oo.modulos_en_valle(ora, ['B'], 150.0, {'comprobado': False, 'puntos': [], 'motivo': 'sin medición'}, p)
    assert nada['modulos'] is None and not nada['comprobado'] and nada['motivo'] == 'sin medición'


def _troncal():
    return [{'nombre': f'T{i}', 'largo_m': 1000.0, 'corriente_a': 50.0} for i in range(3)]


CARGA = [{'barra': 'B', 'existe': True, 'indice_troncal': 2}]


@pytest.mark.parametrize('n', [0, 1, 3, 5])
def test_escalera_variantes_de_1_al_tope_mas_una_de_evidencia(n):
    """073:RF-19, 073:RF-20 — se prueban de 1 a N módulos, y N + 1 solo, sin combinar, para ver que el
    valle lo rechaza; el módulo es el de la tensión; N es el del valle, no una cifra."""
    p = _p(con_regulador=False)
    vs, avisos = eo.variantes('F1', 22.9, _troncal(), CARGA, [], p, banco_kvar=450, modulos_valle=n)
    bancos = [v for v in vs if v.escalones == ('bancos',)]
    assert [o['escalones'] for v in bancos for o in v.obras] == list(range(1, n + 2))
    assert all(o['q_kvar'] == 450 * o['escalones'] for v in bancos for o in v.obras)
    assert [v.solo_evidencia for v in bancos] == [False] * n + [True]
    combinadas = [v for v in vs if 'bancos' in v.escalones and len(v.escalones) > 1]
    assert all(o['escalones'] <= n for v in combinadas for o in v.obras if o['clase'] == 'condensador')
    assert bool(combinadas) == bool(n)
    assert any(f'{n} módulos' in a or 'ningún módulo' in a for a in avisos)
    # Sin consigna: el banco por pasos existe como obra, pero la escalera no lo genera (073:RF-27).
    assert not any(o.get('consigna_pu') for v in vs for o in v.obras if o['clase'] == 'condensador')


def test_escalera_con_tope_del_perfil_no_prueba_de_mas():
    """073:RF-19 — si el número lo limita ``escalera.modulos_max``, no se prueba uno más."""
    vs, _ = eo.variantes('F1', 22.9, _troncal(), CARGA, [], _p(con_regulador=False), banco_kvar=450, modulos_valle=2,
                         evidencia=False)
    assert [o['escalones'] for v in vs if v.escalones == ('bancos',) for o in v.obras] == [1, 2]


def test_escalera_sin_valle_los_modulos_del_perfil_o_la_regla_anterior():
    """073:RF-24 — sin valle, ``escalera.modulos_max`` o los de antes, sin bloquear."""
    def modulos(p):
        vs, _ = eo.variantes('F1', 10.0, _troncal(), CARGA, [], p, banco_kvar=300)
        return [o['escalones'] for v in vs if v.escalones == ('bancos',) for o in v.obras]
    assert modulos(_p(con_regulador=False)) == list(range(1, eo.MODULOS_SIN_VALLE + 1))
    assert modulos(_p(con_regulador=False, modulos_max=4)) == [1, 2, 3, 4]
    perfil = {'escalera': {'cumplimiento': 0.9, 'sorteos': 3, 'tolerancia_pu': 0.01, 'tolerancia_carga_pct': 1,
                           'modulos_max': 6},
              'planificacion': {'tasa_regulada': 0.1, 'vida_util_anios': 20},
              'estudios': {'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100}}
    assert eo.parametros(perfil).modulos_max == 6
    del perfil['escalera']['modulos_max']
    assert eo.parametros(perfil).modulos_max is None


def test_escalera_el_kvar_de_valle_con_su_propio_factor():
    """073:RF-22 — el kW y el kVAR del registro, cada uno con su factor: un valle capacitivo no es la
    máxima a escala. El resultado es el del flujo del grafo con esas potencias."""
    g = _grafo(nueva_mw=0.0)
    ora = oo.Oraculo(g, [], tipos=TIPOS)
    b = _id('B', 'ElmTerm')
    m = ora.medir([], 0, 0.3, factor_q=-0.2)
    hecho = {'nodos': {n: {**d, 'p_mw': d['p_mw'] * 0.3, 'q_mvar': d['q_mvar'] * -0.2} for n, d in g['nodos'].items()},
             'ramas': g['ramas']}
    assert m.u['B'] == pytest.approx(_exacto(hecho, b), abs=1e-9)
    assert ora.medir([], 0, 0.3).u['B'] == pytest.approx(ora.medir([], 0, 0.3, factor_q=0.3).u['B'], abs=1e-12)


def test_escalera_las_cargas_nuevas_en_valle_por_su_factor():
    """073:RF-23 — por defecto apagadas: el banco sigue conectado y de ellas no hay medición. El perfil
    puede dar otro factor, y con carga nueva encendida la tensión baja."""
    ora = _red_con_margen()
    apagada = ora.medir([], 1, 0.05, factor_nuevas=0.0).u['B']
    igual = ora.medir([], 0, 0.05).u['B']
    encendida = ora.medir([], 1, 0.05, factor_nuevas=1.0).u['B']
    assert apagada == pytest.approx(igual, abs=1e-12) and encendida < apagada
    assert vl.ajustes_de({}).factor_cargas_nuevas == 0.0
    assert vl.ajustes_de({'valle': {'factor_cargas_nuevas': 0.4}}).factor_cargas_nuevas == 0.4


def _espacio_valle():
    return oo.Espacio('F1', barras=['B'], banco_kvar=450.0, modulos_max=6,
                      tramos=[{'nombre': 'T1', 'largo_m': 2000.0}, {'nombre': 'T2', 'largo_m': 2000.0}], secciones=[])


def test_escalera_busqueda_de_k_y_eleccion_con_el_valle():
    """073:RF-17, 073:RF-21 — buscar_k y elegir_para_k juzgan también en valle: lo que solo cabe con
    bancos que el valle rechaza no se da por bueno, y la tabla dice la tensión de cada una."""
    pytest.importorskip('optuna')
    # Con la máxima hacen falta dos bancos o una terna; el valle solo admite uno.
    p = _p(tension_max_pu=1.01)
    valle = _puntos(0.2)
    nueva = [{**NUEVA, 'alimentador': 'F1'}]
    ora = oo.Oraculo(_grafo(), nueva, tipos=TIPOS)
    assert oo.modulos_en_valle(ora, ['B'], 450.0, valle, p)['modulos'] == 1
    bancos = [eo.Variante(f'{n} bancos', ('bancos',), [{**_banco(n), 'alimentador': 'F1'}], {'bancos': float(n)})
              for n in (1, 2)]
    terna = eo.Variante('terna', ('terna',), [{'clase': 'terna', 'alimentador': 'F1', 'tramos': ['T1', 'T2']}],
                        {'terna': 4.0})
    alim = oo.Alimentador('F1', [*bancos, terna], lambda v, _k: sum({'bancos': 10.0, 'terna': 500.0}[e] for e in v.escalones),
                          _espacio_valle())
    assert ora.evaluar(bancos[1].obras, 1, p, alimentador='F1')['maxima']        # sin valle, valdría
    assert oo.buscar_k(ora, [oo.Alimentador('F1', bancos, alim.costo)], p)[0] == 1
    assert oo.buscar_k(ora, [oo.Alimentador('F1', bancos, alim.costo)], p, valle=valle)[0] == 0
    r = oo.elegir_para_k(ora, [alim], 1, p, valle=valle, evaluaciones_bayes=30, permutaciones=4, semilla=1)['F1']
    assert r['elegida'] == 'terna'
    filas = {t['nombre']: t for t in r['tabla']}
    assert filas['2 bancos']['valle'] is False and filas['2 bancos']['maxima']
    assert filas['1 bancos']['valle'] is True and filas['1 bancos']['valle_u_max'] <= p.tension_max_pu

    # Ni la bayesiana ni el frente de Pareto dan una combinación con más bancos de los que aguanta.
    def _bancos_de(nombre):
        return next((int(t.split('×')[0]) for t in nombre.split(' + ') if '×' in t), 0)
    assert r['bayesiana']['variante'] is None or _bancos_de(r['bayesiana']['variante']) <= 1
    assert all(_bancos_de(f['variante']) <= 1 for f in r['pareto']['frente'])
    assert r['shapley'] is not None


def test_escalera_puntos_con_el_factor_de_cada_uno():
    """073:RF-22 — de la medición a los puntos: factor de P y de Q sobre la máxima, por alimentador y
    del conjunto; el mínimo de la ventana entra solo si es otro instante."""
    rng = random.Random(77)
    a, b = _curva(rng, 25, kw=1000.0), _curva(rng, 25, kw=3000.0)
    maximas = {'MA': {'alimentador': 'F1', 'kw': 1200.0, 'kvar': 300.0},
               'MB': {'alimentador': 'F2', 'kw': 3500.0, 'kvar': 800.0}}
    aj = vl.Ajustes(dias_ventana=3, factor_cargas_nuevas=0.25)
    v = vl.valle_de_alcance('alimentador', {'MA': a, 'MB': b}, aj)
    r = vl.puntos_de_valle(v, maximas, aj)
    assert r['comprobado'] and r['puntos'][0]['etiqueta'] == 'instante mínimo'
    pt = r['puntos'][0]
    assert pt['factor_p'] == pytest.approx(v.instante['kw'] / 4700.0)
    assert pt['factor_q'] == pytest.approx(v.instante['kvar'] / 1100.0)
    por = v.instante['por_medidor']
    assert pt['factores'] == {'F1': pytest.approx(por['MA'][0] / 1200.0), 'F2': pytest.approx(por['MB'][0] / 3500.0)}
    assert pt['factor_nuevas'] == 0.25 and pt['origen'] == 'medicion'
    assert isinstance(pt['fecha'], str)
    fechas = [x['fecha'] for x in r['puntos']]
    assert len(set(fechas)) == len(fechas)
    if v.ventana['instante']['fecha'] != v.instante['fecha']:
        assert len(r['puntos']) == 2 and r['puntos'][1]['etiqueta'].startswith('mínimo de la ventana')
    else:
        assert len(r['puntos']) == 1
    import json
    json.dumps(r)                                        # viaja en el plan del guion


def test_informe_frase_con_nodo_y_fecha_o_no_comprobado():
    """073:RF-30, 073:RF-31 — la tensión máxima en valle con su nodo y su fecha; sin medición, «no
    comprobado en valle» con el motivo, y nunca la palabra «cumple»."""
    bien = vl.frase_valle({'valle': True, 'valle_u_max': 1.0432, 'valle_nodo': 'B7', 'valle_fecha': '2026-03-08 03:15:00'})
    assert bien == 'tensión máxima en valle de 1,043 p.u. en B7 el 2026-03-08 03:15:00'
    mal = vl.frase_valle({'valle': False, 'valle_u_max': 1.07, 'valle_nodo': 'B7', 'valle_fecha': 'x'})
    assert '1,070' in mal and 'sobrepasa' in mal
    for fila in (None, {}, {'valle': None}, {'valle': None, 'valle_sin_comprobar': 'sin medición'}):
        frase = vl.frase_valle(fila)
        assert frase.startswith('no comprobado en valle') and 'cumple' not in frase
    assert 'sin medición' in vl.frase_valle({'valle_sin_comprobar': 'sin medición'})


def test_escalera_puntos_sin_medicion_o_sin_la_maxima():
    """073:RF-24 — sin valle medido o sin la máxima para comparar, sin puntos y con el motivo."""
    aj = vl.Ajustes()
    nada = vl.puntos_de_valle(vl.Valle(alcance='set', motivo='sin medición'), {}, aj)
    assert not nada['comprobado'] and nada['puntos'] == [] and nada['motivo'] == 'sin medición'
    v = vl.valle_de_alcance('set', {'M': _curva(random.Random(3), 5)}, aj)
    sin_max = vl.puntos_de_valle(v, {'M': {'alimentador': 'F', 'kw': None, 'kvar': None}}, aj)
    assert not sin_max['comprobado'] and sin_max['puntos'] == [] and 'máxima' in sin_max['motivo']
