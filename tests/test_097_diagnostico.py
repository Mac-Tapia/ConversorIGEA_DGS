"""097-DIAG — la abstención con dos señales por estratos (Bonferroni, Mondrian) y el orden de la respuesta con fusión
(097:RF-19, RF-11; tarjeta 097-DIAG). Señales y rankings sintéticos: sin GPU, sin el corpus y sin el sellado.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from convertersmartgrid.asistente import evaluacion_rag as er

RAIZ = Path(__file__).resolve().parents[1]


def _exige():
    """Lo nuevo de la tarjeta: su ausencia es la falla de la aserción, no un AttributeError."""
    faltan = [n for n in ('umbral_conforme', 'calibrar_dos_senales', 'ordenar', 'comparar_ordenes', 'medir_ordenes')
              if not hasattr(er, n)]
    assert not faltan, f'faltan en evaluacion_rag: {faltan} (097-DIAG)'


def test_097_diag_umbral_conforme_con_su_k_y_sin_muestra_suficiente():
    """097:RF-19 (097-DIAG) — el umbral es el k-ésimo valor de las sin respuesta, k = ⌈(n+1)(1−α)⌉; con α = 0,025 hacen
    falta 39 sin respuesta: con 38 no hay umbral."""
    _exige()
    valores = [float(i) for i in range(39)]
    assert er.umbral_conforme(valores, 0.025) == pytest.approx(38.0 + 1e-6)
    assert er.umbral_conforme(valores[:38], 0.025) is None
    assert er.umbral_conforme([], 0.05) is None


def _filas(rnd, n_dominio, n_fuera, n_con=60):
    filas = [{'grupo': f'd{i}', 'tipo': 'dominio', 'responde': False, 'codigo': False,
              'reranker': rnd.gauss(-3, 1), 'coseno': rnd.gauss(0.5, 0.05)} for i in range(n_dominio)]
    filas += [{'grupo': f'f{i}', 'tipo': 'fuera', 'responde': False, 'codigo': False,
               'reranker': rnd.gauss(-5, 1), 'coseno': rnd.gauss(0.3, 0.05)} for i in range(n_fuera)]
    filas += [{'grupo': f'c{i}', 'tipo': 'entregable', 'responde': True, 'codigo': False,
               'reranker': rnd.gauss(3, 1), 'coseno': rnd.gauss(0.75, 0.05)} for i in range(n_con)]
    return filas


def test_097_diag_dos_senales_por_estratos_con_bonferroni_y_la_mezcla_de_la_prueba():
    """097-DIAG (b, a1) — un umbral por señal y por estrato con α/2; vale el más alto de los estratos; la abstención en
    la calibración llega al objetivo en cada estrato, y con la mezcla de la prueba se da su intervalo esperado."""
    _exige()
    filas = _filas(random.Random(97), 190, 40)
    r = er.calibrar_dos_senales(filas, mezcla={'dominio': 25, 'fuera': 25}, remuestreos=300)
    assert r['faltan'] == [] and r['cobertura_teorica'] == pytest.approx(0.95)
    for s in er.SENALES_DOBLES:
        assert r['umbrales'][s] == max(r['umbrales_por_estrato'][e][s] for e in er.ESTRATOS_SIN_RESPUESTA)
    assert all(r['abstencion_en_calibracion'][e] >= 0.95 for e in er.ESTRATOS_SIN_RESPUESTA)
    assert r['conserva_en_calibracion'] > 0.8
    lo, hi = r['esperada_con_mezcla']['ic95']
    assert 0.9 <= lo <= hi <= 1.0 and r['esperada_con_mezcla']['mezcla'] == {'dominio': 25, 'fuera': 25}


def test_097_diag_un_estrato_con_menos_de_39_no_tiene_umbral_y_la_regla_se_abstiene_siempre():
    """097-DIAG (b) — con 25 «fuera» (la calibración actual), su estrato no tiene umbral: se dice cuál falta y la regla
    no responde a nada; nunca se baja el objetivo para que salga."""
    _exige()
    r = er.calibrar_dos_senales(_filas(random.Random(1), 90, 25))
    assert set(r['faltan']) == {'fuera:reranker', 'fuera:coseno'}
    assert r['umbrales'] == {'reranker': None, 'coseno': None} and r['conserva_en_calibracion'] == 0.0


def test_097_diag_ordenar_hibrido_reranker_rrf_y_top20():
    """097-DIAG (c) — «hibrido» deja el orden del híbrido; «reranker» toma el suyo; «top20» reordena solo los 20
    primeros; «rrf» funde los dos rangos con 1/(60+rango)."""
    _exige()
    candidatos = [{'id': i, 'texto': str(i)} for i in range(25)]
    puntuados = [{'id': i, 'texto': str(i), 'reranker': float(i)} for i in reversed(range(25))]
    assert [c['id'] for c in er.ordenar('hibrido', candidatos, puntuados)][:3] == [0, 1, 2]
    assert [c['id'] for c in er.ordenar('reranker', candidatos, puntuados)][:3] == [24, 23, 22]
    top = [c['id'] for c in er.ordenar('top20', candidatos, puntuados)]
    assert top[:3] == [19, 18, 17] and top[20:] == [20, 21, 22, 23, 24]
    rrf = er.ordenar('rrf', candidatos, puntuados)
    assert len(rrf) == 25 and {c['id'] for c in rrf} == set(range(25))
    with pytest.raises(ValueError, match='orden desconocido'):
        er.ordenar('otro', candidatos, puntuados)


def _medido(rr):
    return {'per_query': [{'group_id': f'q{i}', 'reciprocal_rank@10': v, 'recall@10': v} for i, v in enumerate(rr)]}


def test_097_diag_comparar_ordenes_elige_solo_si_mejora_con_su_ic_y_si_no_el_hibrido():
    """097-DIAG (c) — se elige el orden que sube el MRR@10 con su IC95 por encima de cero sin bajar el Recall@10; si
    ninguno lo hace, queda el híbrido: el reranker no entra en el orden."""
    _exige()
    base = [0.5] * 40
    mejor = _medido([0.9] * 40)
    peor = _medido([0.2] * 40)
    elegido = er.comparar_ordenes({'hibrido': _medido(base), 'reranker': peor, 'rrf': mejor, 'top20': _medido(base)})
    assert elegido['elegido'] == 'rrf'
    ninguno = er.comparar_ordenes({'hibrido': _medido(base), 'reranker': peor, 'rrf': _medido(base), 'top20': peor})
    assert ninguno['elegido'] == 'hibrido'


def test_097_diag_las_preguntas_nuevas_de_la_calibracion_tienen_su_forma_y_su_mezcla():
    """097-DIAG (a2) — el conjunto nuevo del maestro trae 100 sin respuesta con la mezcla de la 076 (por aspecto y por
    entregable) y 15 «fuera», con el esquema de las del maestro de la 077 y su búsqueda en el corpus anotada."""
    _exige()
    datos = json.loads((RAIZ / 'docs' / 'CONJUNTO_MAESTRO_CALIBRACION_097.json').read_text(encoding='utf-8'))
    filas = datos['preguntas']
    assert len(filas) == 100 and len(datos['fuera_calibracion']) == 15
    assert all(f['tipo'] == 'sin_respuesta' and f['origen'] == 'maestro' and f['fuentes'] == [] for f in filas)
    assert all('sin respuesta' in f['revision']['correccion'] for f in filas)
    aspectos = {}
    for f in filas:
        aspectos[f['aspecto']] = aspectos.get(f['aspecto'], 0) + 1
    assert aspectos == {'criterio': 29, 'dato_entrada': 27, 'limite': 19, 'formato': 11, 'metodologia': 6,
                        'requisito': 3, 'cuando_no_aplica': 3, 'que_hace': 2}
    assert len({f['pregunta'] for f in filas}) == 100
