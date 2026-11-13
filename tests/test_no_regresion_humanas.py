"""Spec 069, T12: puerta de no regresión sobre las órdenes humanas frente al modelo en uso (069:RF-38 a RF-40).

El 2026-11-12 se promovió reg-75fdd605 con 0 fallos de puertas: en las 43 órdenes humanas acertaba 0,744
(32 de 43) frente a 0,953 (41 de 43) del que sustituyó, prov-8fd8a405. Con menos de 200 humanas decide el
examen del maestro (085:RF-19) y las humanas solo se informaban; la comparación con el modelo en uso era
por familia en la sellada. La puerta compara los dos modelos sobre los mismos ejemplos (McNemar exacto).
"""
from __future__ import annotations

import pytest
from scipy.stats import binomtest

from convertersmartgrid.asistente import destilacion_integral as di


class _Modelo:
    """Acierta la tarea en los índices de ``aciertos``; en los demás responde otra."""

    def __init__(self, filas, aciertos, version='doble'):
        self.version = version
        self.respuestas = {f['texto']: (f['tarea'] if i in aciertos else 'estado') for i, f in enumerate(filas)}

    def predecir(self, texto):
        return {'tarea': self.respuestas[texto], 'confianza': .99, 'datos': {}}


def _humanas(n=43):
    return [{'texto': f'flujo de AB{100 + i}', 'tarea': 'flujo', 'datos': []} for i in range(n)]


def _promovible():
    """Las demás puertas en regla, como las pasó reg-75fdd605 (0 fallos)."""
    buena = {'acierto_tarea': .985, 'plan_igual': .96, 'cobertura': .6}
    return ({'sinteticas': buena, 'maestro': buena, 'humanas': None}, {'acierto_tarea': .87},
            {'sinteticas': {'acierto_tarea': .83}}, {'ejemplos': 206, 'rechazada': 1.0, 'se_cuela': 0.0})


def test_069_rf38_el_caso_de_reg_75fdd605_sale_rechazado():
    """069:RF-38, 069:RF-39 — 43 humanas, el modelo en uso acierta 41 (0,953) y el candidato 32 (0,744) sobre
    los mismos ejemplos: la caída es significativa y la decisión sale RECHAZADO, aunque decida el maestro."""
    filas = _humanas()
    en_uso = _Modelo(filas, set(range(41)), 'prov-8fd8a405')
    candidato = _Modelo(filas, set(range(32)))
    assert round(sum(di.aciertos_de_tarea(en_uso, filas)) / 43, 3) == .953
    assert round(sum(di.aciertos_de_tarea(candidato, filas)) / 43, 3) == .744
    puerta = di.puerta_no_regresion(di.aciertos_de_tarea(candidato, filas), di.aciertos_de_tarea(en_uso, filas))
    assert (puerta['empeora'], puerta['mejora'], puerta['ejemplos']) == (9, 0, 43)
    assert puerta['bloquea'] and puerta['p_valor'] < di.ALFA_NO_REGRESION
    assert abs(puerta['p_valor'] - binomtest(9, 9, .5, alternative='greater').pvalue) < 1e-12
    selectiva, sinteticas, medidas, rechazo = _promovible()
    # Sin la puerta, el agujero: el mismo candidato pasaba.
    assert di.decidir_selectiva(selectiva, 'maestro', sinteticas, medidas, rechazo)['status'] == 'PROMOVIDO'
    d = di.decidir_selectiva(selectiva, 'maestro', sinteticas, medidas, rechazo, no_regresion=puerta)
    assert d['status'] == 'RECHAZADO' and not d['gates']['approved']
    assert any('McNemar' in f and '41' in f and '32' in f for f in d['fallos']), d['fallos']
    assert d['no_regresion'] == puerta


def test_069_rf38_con_discordantes_en_los_dos_sentidos_tambien_bloquea():
    """069:RF-38 — los mismos 0,953 y 0,744, con dos órdenes que solo acierta el candidato (11 contra 2)."""
    filas = _humanas()
    en_uso = set(range(41))
    candidato = set(range(30)) | {41, 42}
    puerta = di.puerta_no_regresion(di.aciertos_de_tarea(_Modelo(filas, candidato), filas),
                                    di.aciertos_de_tarea(_Modelo(filas, en_uso), filas))
    assert (puerta['empeora'], puerta['mejora']) == (11, 2) and puerta['bloquea']
    assert abs(puerta['p_valor'] - binomtest(11, 13, .5, alternative='greater').pvalue) < 1e-12


def test_069_rf38_una_diferencia_pequena_no_significativa_no_bloquea():
    """069:RF-38 — una orden menos (41 frente a 40 de 43) no es una regresión demostrable: no bloquea."""
    filas = _humanas()
    puerta = di.puerta_no_regresion(di.aciertos_de_tarea(_Modelo(filas, set(range(40))), filas),
                                    di.aciertos_de_tarea(_Modelo(filas, set(range(41))), filas))
    assert (puerta['empeora'], puerta['mejora']) == (1, 0) and puerta['p_valor'] == .5 and not puerta['bloquea']
    selectiva, sinteticas, medidas, rechazo = _promovible()
    d = di.decidir_selectiva(selectiva, 'maestro', sinteticas, medidas, rechazo, no_regresion=puerta)
    assert d['status'] == 'PROMOVIDO', d['fallos']


def test_069_rf40_sin_modelo_en_uso_no_aplica_y_si_no_se_pudo_medir_bloquea():
    """069:RF-40 — sin modelo en uso no hay de qué regresar; si lo hay y no se pudo medir, no se aprueba;
    los dos modelos se comparan sobre los mismos ejemplos o no se comparan."""
    filas = _humanas(5)
    candidato = di.aciertos_de_tarea(_Modelo(filas, {0, 1}), filas)
    assert di.puerta_no_regresion(candidato, None)['aplica'] is False
    assert not di.puerta_no_regresion(candidato, None)['bloquea']
    error = di.puerta_no_regresion(candidato, None, error_referencia='out of memory')
    assert error['bloquea'] and 'out of memory' in error['motivo']
    assert not di.puerta_no_regresion([], [])['bloquea']
    with pytest.raises(ValueError, match='mismos ejemplos'):
        di.puerta_no_regresion(candidato, candidato[:-1])


def test_069_rf39_la_puerta_sale_de_las_humanas_y_del_modelo_en_uso(monkeypatch):
    """069:RF-39 — la medida del modelo en uso guarda su acierto por orden humana, y la puerta del flujo
    compara con él al candidato que mide las humanas, sobre las mismas órdenes."""
    from convertersmartgrid.asistente import transformer as tr

    filas = _humanas()
    monkeypatch.setattr(tr, 'cargar', lambda *a, **k: _Modelo(filas, set(range(41)), 'prov-8fd8a405'))
    en_uso = di._medir_en_uso(filas, filas, None)
    assert en_uso['version'] == 'prov-8fd8a405' and sum(en_uso['aciertos_humanas']) == 41
    puerta = di.no_regresion_humanas(_Modelo(filas, set(range(32))), filas, en_uso)
    assert puerta['bloquea'] and (puerta['empeora'], puerta['mejora']) == (9, 0)
    assert puerta['referencia'] == 'prov-8fd8a405'
    assert not di.no_regresion_humanas(_Modelo(filas, set(range(41))), filas, en_uso)['bloquea']
    assert di.no_regresion_humanas(_Modelo(filas, set()), filas, {'error': 'no abre'})['bloquea']
    assert di.no_regresion_humanas(_Modelo(filas, set()), filas, None)['aplica'] is False
