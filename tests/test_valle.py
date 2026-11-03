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
