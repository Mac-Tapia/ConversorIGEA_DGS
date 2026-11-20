"""086:RF-122 (amplía 022:RF-88): la SET de cada central térmica (CT…) del libro, elegida entre todas las de la
estructura, y las que no entran en la máxima por barra.

- El servidor da todas las SET con sus alimentadores; la web pone primero las de los alimentadores analizados.
- Una central va a la barra de la SET que elige el operador, aunque el libro diga otra.
- Una central cuya SET no tiene ninguno de los alimentadores analizados no entra, y se dice por qué (sin «(s)»).
- La que está en el tramo de un alimentador se mide con él (RF-88) y no se toca.
Estructura y medidores sintéticos sorteados; ningún dato de una empresa.
"""
from __future__ import annotations

import random

from convertersmartgrid.aplicacion import demanda_medida as dm
from convertersmartgrid.dominio.estructura import estructura_de_dict

SEMILLA = random.SystemRandom().randrange(1, 2 ** 31)


def _estructura(n_sets: int):
    sets = [{'codigo': f'SET {i}', 'nombre': f'Ese{i}', 'siglas': [f'S{i}'], 'alimentadores': [f'S{i}1{j:02d}' for j in range(1, 3)]}
            for i in range(1, n_sets + 1)]
    return estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': sets}]})


def _centrales_en_su_set():
    assert hasattr(dm, 'centrales_en_su_set'), 'falta centrales_en_su_set (086:RF-122)'
    return dm.centrales_en_su_set


def test_086_rf122_la_central_va_a_la_set_que_elige_el_operador():
    """086:RF-122 — el libro la pone en una SET sin alimentadores analizados; el operador elige la de los analizados y
    la central entra en esa barra."""
    rng = random.Random(SEMILLA)
    n = rng.randint(3, 6)
    e = _estructura(n)
    ajena, propia = rng.sample(range(1, n + 1), 2)
    analizados = [f'S{propia}101']
    ms = [dm.MedidorBarra('CT_X', 10.0, f'S{ajena}', True, 1), dm.MedidorBarra(f'B-S{propia}T1', 10.0, f'S{propia}', False, 2)]
    centrales = _centrales_en_su_set()
    sin_elegir, avisos = centrales(e, ms, analizados, {})
    assert [m.medidor for m in sin_elegir] == [f'B-S{propia}T1'], SEMILLA
    rotulo = e.sets[f'SET {ajena}'].rotulo
    assert avisos == [f'CT_X: su SET ({rotulo}) no tiene ninguno de los alimentadores analizados; no entra.'], avisos
    elegida, avisos = centrales(e, ms, analizados, {'CT_X': f'SET {propia}'})
    assert avisos == [] and [m.medidor for m in elegida] == ['CT_X', f'B-S{propia}T1'], SEMILLA
    barras, _ = dm.barras_de_calibracion(e, elegida, analizados, {analizados[0]: 10.0})
    barra = next((b for b in barras if b.set_codigo == f'SET {propia}'), None)
    assert barra is not None and barra.centrales == ['CT_X'], SEMILLA


def test_086_rf122_una_set_desconocida_no_cambia_nada_y_la_del_tramo_no_se_toca():
    """086:RF-122 — una SET que no es de la estructura deja la del libro; la central en el tramo de un alimentador
    (022:RF-88) se queda aunque su SET no sea de los analizados."""
    e = _estructura(3)
    ms = [dm.MedidorBarra('CT_A', 10.0, 'S1', True, 1), dm.MedidorBarra('CT_B', 22.9, 'S3', True, 2)]
    salida, avisos = _centrales_en_su_set()(e, ms, ['S1101'], {'CT_A': 'SET 99'}, {'CT_B': 'S1101'})
    assert [m.medidor for m in salida] == ['CT_A', 'CT_B'] and avisos == []
    assert salida[0].siglas == 'S1'


def test_086_rf122_el_servidor_da_todas_las_set_con_sus_alimentadores(monkeypatch):
    """086:RF-122 — la lista de centrales trae todas las SET de la estructura, en orden de número, con sus alimentadores."""
    from convertersmartgrid.presentacion.web import services

    rng = random.Random(SEMILLA)
    n = rng.randint(2, 12)
    e = _estructura(n)
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: e)
    monkeypatch.setattr(services, '_demanda_ruta', lambda _ws, _t: 'libro.xlsx')
    monkeypatch.setattr(dm, 'leer_medidores_de_barra', lambda _r, _a: [dm.MedidorBarra('CT_X', 10.0, 'S1', True, 1)])
    r = services.demanda_centrales_de_barra(object())
    assert 'sets' in r, 'el servidor no da la lista de SET'
    assert [s['codigo'] for s in r['sets']] == [f'SET {i}' for i in range(1, n + 1)], SEMILLA
    assert r['sets'][0]['alimentadores'] == ['S1101', 'S1102'] and r['centrales'][0]['set'] == 'SET 1'


def test_086_rf123_la_grafica_de_curvas_pone_la_etiqueta_de_cada_maxima():
    """086:RF-123 — con varias curvas de cabecera, cada máxima lleva su etiqueta (alimentador, kW y fecha), repartidas
    para no taparse; la prueba de su reparto, con 200 casos sorteados, está en frontend/test/etiquetasMaxima.test.mjs."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    curva = (raiz / 'features' / 'powerfactory' / 'CurvaCabecera.tsx').read_text(encoding='utf-8')
    graficos = (raiz / 'shared' / 'graficos.ts').read_text(encoding='utf-8')
    assert 'export function separarEtiquetas(' in graficos, 'falta el reparto de las etiquetas'
    assert 'separarEtiquetas(' in curva and 'g.etiquetas.map((e) =>' in curva
    assert '${t.etiqueta} · ${fmtNum(t.kwMax, 1)} kW · ${diaHora(t.fm)}' in curva


def test_086_rf126_el_informe_avisa_de_instantes_que_no_ocurrieron_juntos():
    """086:RF-126 (amplía 028:RF-27, RF-28) — con la máxima de cada alimentador, el informe de la calibración dice la
    fecha y hora de cada uno y avisa, sin bloquear, de que no ocurrieron juntas; con un solo instante, nada."""
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / 'tools' / 'ajuste_cabecera_pf.py'
    texto = ruta.read_text(encoding='utf-8')
    assert 'def aviso_de_instantes(' in texto, 'el guion no avisa de los instantes distintos'
    espacio: dict = {}
    inicio = texto.index('def aviso_de_instantes(')
    exec(texto[inicio:texto.index('\ndef ', inicio + 10)], espacio)
    aviso = espacio['aviso_de_instantes']
    rng = random.Random(SEMILLA)
    a, b = f'Q{rng.randint(100, 899)}', f'R{rng.randint(100, 899)}'
    t = aviso({a: '2026-07-03 19:15:00', b: '2026-07-11 20:00:00'})
    assert f'{a} el 2026-07-03 19:15:00' in t and f'{b} el 2026-07-11 20:00:00' in t and 'no ocurrieron juntos' in t
    assert aviso({a: '2026-07-03 19:15:00', b: '2026-07-03 19:15:00'}) == '' and aviso({a: None}) == ''
    assert '(s)' not in t and importlib.util is not None
    assert "inf['avisos'].append(aviso_instantes)" in texto
