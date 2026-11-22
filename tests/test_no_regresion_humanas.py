"""Spec 069, T12: puerta de no regresión sobre las órdenes humanas frente al modelo en uso (069:RF-38 a RF-40).

El 2026-11-12 se promovió reg-75fdd605 con 0 fallos de puertas: en las 43 órdenes humanas acertaba 0,744
(32 de 43) frente a 0,953 (41 de 43) del que sustituyó, prov-8fd8a405. Con menos de 200 humanas decide el
examen del maestro (085:RF-19) y las humanas solo se informaban; la comparación con el modelo en uso era
por familia en la sellada. La puerta compara los dos modelos sobre los mismos ejemplos (McNemar exacto).

Auditoría del 2026-11-13 (c7, sobre 3a02ea17): aquel 0,953 era una medida dentro de muestra. prov-8fd8a405 entrenó
con 29 de esas 43 humanas (``confirmadas_que_entrenan`` 29, ``humanas_modelo_final.independiente`` falso en su
metrics.json), y ``_medir_en_uso`` lo medía con ``tr.cargar()`` sobre ellas mismas, mientras el candidato se medía
fuera de grupo. Su propia medida fuera de grupo, la guardada, es 31 de 43 (0,721): el candidato de 32 no empeora.
Lo que compara la puerta sale ahora del mismo conjunto de humanas y, para los dos modelos, fuera de muestra (069:RF-39).
"""
from __future__ import annotations

import json

import pytest
from scipy.stats import binomtest

from convertersmartgrid.aplicacion.asistente import destilacion_integral as di


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


def test_069_rf38_una_caida_de_41_a_32_sale_rechazada():
    """069:RF-38 — la aritmética de la puerta con las cifras que se compararon el 2026-11-12: 41 (0,953) frente a 32
    (0,744) sobre los mismos ejemplos es una caída significativa y sale RECHAZADO, aunque decida el maestro.

    Solo la cuenta: el 41 de prov-8fd8a405 era dentro de muestra, y el flujo ya no lo compara (ver
    ``test_069_rf39_el_modelo_en_uso_se_mide_fuera_de_muestra``)."""
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


def _registro(tmp_path, monkeypatch, candidato_id, metrics, dataset=None):
    """Un registro del asistente con un solo candidato, como el de ``output/web/_asistente/model_registry``."""
    carpeta = tmp_path / 'almacen' / 'model_registry' / 'transformer' / 'candidates' / candidato_id
    carpeta.mkdir(parents=True)
    (carpeta / 'metrics.json').write_text(json.dumps(metrics), encoding='utf-8')
    if dataset is not None:
        (carpeta / 'dataset_manifest.json').write_text(json.dumps(dataset), encoding='utf-8')
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'almacen'))


def _en_uso(monkeypatch, filas, aciertos, version):
    from convertersmartgrid.aplicacion.asistente import transformer as tr

    monkeypatch.setattr(tr, 'cargar', lambda *a, **k: _Modelo(filas, aciertos, version))


#: Las cifras de prov-8fd8a405 en su metrics.json real (leído el 2026-11-13, sin tocarlo).
_PROV_8FD8A405 = {'validacion_cruzada': {'confirmadas_que_entrenan': 29, 'confirmadas_que_no_entrenan': 14, 'medida': True,
                                         'humanas_fuera_de_grupo': {'acierto_tarea': 31 / 43, 'f1_datos': .75, 'ejemplos': 43},
                                         'humanas_modelo_final': {'acierto_tarea': 41 / 43, 'ejemplos': 43,
                                                                  'independiente': False, 'decide': False}},
                  'humanas': {'acierto_tarea': 31 / 43, 'f1_datos': .75, 'ejemplos': 43}}


def test_069_rf39_el_modelo_en_uso_se_mide_fuera_de_muestra(tmp_path, monkeypatch):
    """069:RF-39 — prov-8fd8a405 entrenó con 29 de las 43 humanas: ``tr.cargar()`` sobre ellas da 41 (dentro de muestra).
    Su medida fuera de grupo guardada es 31: el candidato con 32 fuera de grupo no empeora y no se bloquea, y la puerta
    dice que la comparación no es pareada porque el registro no guarda cuál acertó ni cuáles vio."""
    filas = _humanas()
    _registro(tmp_path, monkeypatch, '8fd8a405a322c80c' + '0' * 48, _PROV_8FD8A405)
    _en_uso(monkeypatch, filas, set(range(41)), 'prov-8fd8a405a322c80c')
    en_uso = di._medir_en_uso(filas, filas, None)
    puerta = di.no_regresion_humanas(_Modelo(filas, set(range(32))), filas, en_uso)
    assert not puerta['bloquea'], puerta['motivo']
    assert puerta['aplica'] and puerta.get('pareada') is False and puerta.get('origen_referencia') == 'agregada_fuera_de_grupo'
    assert (puerta['aciertos_referencia'], puerta['aciertos_candidato'], puerta['ejemplos']) == (31, 32, 43)
    assert '29' in puerta['motivo'] and 'sin parear' in puerta['motivo']
    # La primera frase del motivo, la que lee el informe de la decisión, dice que es la cota y que es conservadora.
    assert puerta['motivo'].startswith('referencia anterior a humanas_por_orden: cota conservadora')
    selectiva, sinteticas, medidas, rechazo = _promovible()
    decision = di.decidir_selectiva(selectiva, 'maestro', sinteticas, medidas, rechazo, no_regresion=puerta)
    assert decision['no_regresion']['motivo'].startswith('referencia anterior a humanas_por_orden: cota conservadora')
    # La medida dentro de muestra se sigue dando, marcada: no decide.
    assert en_uso['humanas']['acierto_tarea'] == 41 / 43 and en_uso['humanas']['dentro_de_muestra'] is True
    # La cota sin parear (el emparejamiento que más acusa al candidato) sigue bloqueando una caída real: 22 frente a 31.
    caida = di.no_regresion_humanas(_Modelo(filas, set(range(22))), filas, en_uso)
    assert caida['bloquea'] and (caida['empeora'], caida['mejora']) == (9, 0)
    assert abs(caida['p_valor'] - binomtest(9, 9, .5, alternative='greater').pvalue) < 1e-12
    # Y cuando bloquea, el fallo de la decisión lleva esa misma línea.
    rechazada = di.decidir_selectiva(selectiva, 'maestro', sinteticas, medidas, rechazo, no_regresion=caida)
    assert rechazada['status'] == 'RECHAZADO'
    assert any(f.startswith('no regresión en las humanas: referencia anterior a humanas_por_orden: cota conservadora')
               for f in rechazada['fallos']), rechazada['fallos']


def test_069_rf39_pareada_con_la_medida_guardada_y_en_la_interseccion(tmp_path, monkeypatch):
    """069:RF-39 — con su acierto por orden guardado, la referencia es esa, orden por orden; si las humanas de hoy no
    son las mismas, se compara en la intersección y se dice cuántas quedan."""
    filas = _humanas(45)
    guardadas = {di.clave_humana(f['texto']): i < 31 for i, f in enumerate(filas[:43])}
    _registro(tmp_path, monkeypatch, '75fdd605ab8dd4c6' + '0' * 48,
              {'humanas_por_orden': {'origen': 'fuera_de_grupo', 'aciertos': guardadas, 'vistas_al_entrenar': []}})
    _en_uso(monkeypatch, filas, set(range(45)), 'reg-75fdd605ab8dd4c6')
    en_uso = di._medir_en_uso(filas, filas, None)
    puerta = di.no_regresion_humanas(_Modelo(filas, set(range(32))), filas, en_uso)
    assert puerta.get('pareada') is True and puerta.get('origen_referencia') == 'fuera_de_grupo'
    assert (puerta['ejemplos'], puerta['humanas_de_hoy'], puerta['aciertos_referencia']) == (43, 45, 31)
    assert (puerta['empeora'], puerta['mejora']) == (0, 1) and not puerta['bloquea']
    assert '43 de las 45' in puerta['motivo']


def test_069_rf39_sin_medida_guardada_se_excluyen_las_que_vio(tmp_path, monkeypatch):
    """069:RF-39 — si el registro dice qué humanas vio y no cuál acertó, se mide con ``tr.cargar()`` solo en las otras."""
    filas = _humanas()
    vistas = [di.clave_humana(f['texto']) for f in filas[:29]]
    _registro(tmp_path, monkeypatch, 'abcdef0123456789' + '0' * 48,
              {'humanas_por_orden': {'origen': 'fuera_de_grupo', 'vistas_al_entrenar': vistas}})
    _en_uso(monkeypatch, filas, set(range(41)), 'reg-abcdef0123456789')
    en_uso = di._medir_en_uso(filas, filas, None)
    puerta = di.no_regresion_humanas(_Modelo(filas, set(range(32))), filas, en_uso)
    assert puerta.get('pareada') is True and puerta.get('origen_referencia') == 'sin_las_vistas'
    # De las 14 que no vio acierta 12 (de la 29 a la 40); el candidato, 3 (de la 29 a la 31).
    assert (puerta['ejemplos'], puerta['aciertos_referencia'], puerta['aciertos_candidato']) == (14, 12, 3)
    assert puerta['bloquea'] and '29' in puerta['motivo'] and '14 de las 43' in puerta['motivo']


def test_069_rf39_la_que_no_entreno_con_humanas_y_la_que_no_consta(tmp_path, monkeypatch):
    """069:RF-39 — reg-75fdd605 no entrenó con ninguna humana (solo examinaban): su medida con ``tr.cargar()`` es fuera
    de muestra. Un modelo que no está en el registro no dice qué vio: se mide igual y se avisa."""
    filas = _humanas()
    _registro(tmp_path, monkeypatch, '75fdd605ab8dd4c6' + '0' * 48, {'humanas': {'acierto_tarea': 32 / 43, 'ejemplos': 43}},
              {'dataset': {'denominadores': {'entrenamiento': {'silver_teacher_verified': 10}, 'prueba': {'gold_human': 43}}}})
    _en_uso(monkeypatch, filas, set(range(32)), 'reg-75fdd605ab8dd4c6')
    puerta = di.no_regresion_humanas(_Modelo(filas, set(range(31))), filas, di._medir_en_uso(filas, filas, None))
    assert puerta.get('pareada') is True and puerta.get('origen_referencia') == 'sin_humanas_en_entrenamiento'
    assert (puerta['ejemplos'], puerta['aciertos_referencia']) == (43, 32) and not puerta['bloquea']
    _en_uso(monkeypatch, filas, set(range(41)), '20261024-150042-37ce')
    heredado = di.no_regresion_humanas(_Modelo(filas, set(range(32))), filas, di._medir_en_uso(filas, filas, None))
    assert heredado.get('origen_referencia') == 'no_consta' and 'no consta' in heredado['motivo'] and heredado['bloquea']


def test_069_rf40_sin_modelo_en_uso_o_sin_medirlo(tmp_path, monkeypatch):
    """069:RF-40 — sin modelo en uso no aplica; si no se pudo medir, no se aprueba."""
    filas = _humanas()
    assert di.no_regresion_humanas(_Modelo(filas, set()), filas, {'error': 'no abre'})['bloquea']
    assert di.no_regresion_humanas(_Modelo(filas, set()), filas, None)['aplica'] is False


def test_069_rf39_la_cota_sin_parear_es_conservadora():
    """069:RF-39 — con la diferencia d = b − c fija, el valor p de la McNemar exacta no baja al crecer los discordantes
    b + c, unilateral (el de la puerta) ni bilateral (Fagerland, Lydersen y Laake, 2013): la cota b = d, c = 0 que se usa
    sin pares da el más pequeño de todos los emparejamientos que dejan esos totales, y rechaza más, nunca menos.
    Con cifras sorteadas, contra SciPy."""
    import random

    azar = random.Random(20261114)
    for _ in range(300):
        d, c = azar.randint(1, 25), azar.randint(0, 60)
        uni = [binomtest(d + k, d + 2 * k, .5, alternative='greater').pvalue for k in (c, c + 1)]
        bi = [binomtest(d + k, d + 2 * k, .5).pvalue for k in (c, c + 1)]
        assert uni[0] <= uni[1] + 1e-12 and bi[0] <= bi[1] + 1e-12, (d, c)
    filas = _humanas()
    en_uso = {'version': 'prov-8fd8a405', 'humanas_honestas': {'origen': 'agregada_fuera_de_grupo', 'ejemplos': 43, 'vistas': 29}}
    for _ in range(200):
        k_r, k_c = azar.randint(0, 43), azar.randint(0, 43)
        en_uso['humanas_honestas']['aciertos'] = k_r
        cota = di.no_regresion_humanas(_Modelo(filas, set(range(k_c))), filas, en_uso)
        d = k_r - k_c
        if d <= 0:
            assert cota.get('p_valor') == 1. and not cota['bloquea']
            continue
        # Todo emparejamiento con esos totales: c de las 43 que solo acierta el candidato, b = d + c.
        posibles = []
        for c in range(0, min(k_c, 43 - k_r) + 1):
            referencia = [False] * c + [True] * (k_c - c) + [True] * (d + c) + [False] * (43 - k_c - d - c)
            posibles.append(di.puerta_no_regresion([True] * k_c + [False] * (43 - k_c), referencia))
        pareadas = [p for p in posibles if p['empeora'] - p['mejora'] == d]
        assert pareadas and 'p_valor' in cota and all('p_valor' in p for p in pareadas), 'la puerta da su valor p'
        assert all(cota['p_valor'] <= p['p_valor'] + 1e-12 for p in pareadas)
        assert cota['bloquea'] >= max(p['bloquea'] for p in pareadas)


# --- 069:RF-41: partición de las humanas por empresa, por fecha y por grupo de paráfrasis --------------------------------

def _humanas_etiquetadas(semilla: int):
    """Humanas sintéticas con su empresa, su fecha y su grupo; algunos grupos cruzan el corte y dos comparten texto."""
    import random
    from datetime import datetime, timedelta
    r = random.Random(semilla)
    inicio, filas = datetime(2026, 9, 1), []
    for e in ('E1', 'E2', 'E3'):
        for g in range(r.randint(8, 14)):
            grupo = f'{e}-g{g}'
            # Cada grupo tiene paráfrasis a los dos lados del corte (día 50): la partición por fecha debe separarlas
            # sin partir el grupo, y así ninguna parte se queda sin grupos por el sorteo.
            for k in range(r.randint(2, 4)):
                dia = r.randint(0, 40) if k % 2 == 0 else r.randint(60, 100)
                filas.append({'record_id': f'{grupo}-{k}', 'texto': f'orden {e} {g} variante {k}', 'tarea': 'estado',
                              'empresa': e, 'grupo': grupo, 'fecha': (inicio + timedelta(days=dia)).isoformat()})
    # Otro grupo con el mismo texto que la primera: es la misma petición y no se separa de ella.
    filas.append({**filas[0], 'record_id': 'repetida', 'grupo': 'E1-otro'})
    return filas, inicio + timedelta(days=50)


@pytest.mark.parametrize('semilla', range(200))
def test_069_rf41_las_humanas_se_parten_por_empresa_fecha_y_grupo_sin_cruzarse(semilla):
    """069:RF-41 — ninguna empresa retenida, fecha de prueba ni grupo de paráfrasis cae en dos particiones."""
    from datetime import datetime, timedelta
    from convertersmartgrid.aplicacion.asistente import validacion_cruzada as vc
    assert hasattr(vc, 'particionar_humanas'), 'falta validacion_cruzada.particionar_humanas'
    filas, corte = _humanas_etiquetadas(semilla)
    horizonte = timedelta(days=7)
    plan = vc.particionar_humanas(filas, corte=corte, horizonte=horizonte)
    por_id = {f['record_id']: f for f in filas}
    tipos = sorted(c.tipo for c in plan.cohortes)
    assert tipos == ['empresa', 'empresa', 'empresa', 'tiempo'], f'semilla {semilla}: {tipos}'
    for c in plan.cohortes:
        parte_de = {rid: p for p in ('entrenamiento', 'seleccion', 'calibracion', 'prueba')
                    for rid in getattr(c.particiones, p)}
        grupos: dict[str, set] = {}
        textos: dict[str, set] = {}
        for rid, p in parte_de.items():
            grupos.setdefault(por_id[rid]['grupo'], set()).add(p)
            textos.setdefault(por_id[rid]['texto'], set()).add(p)
        assert all(len(v) == 1 for v in grupos.values()), f'semilla {semilla}, {c.nombre}: un grupo en dos partes'
        assert all(len(v) == 1 for v in textos.values()), f'semilla {semilla}, {c.nombre}: un texto en dos partes'
        prueba = [por_id[rid] for rid, p in parte_de.items() if p == 'prueba']
        ajuste = [por_id[rid] for rid, p in parte_de.items() if p != 'prueba']
        assert prueba and ajuste, f'semilla {semilla}, {c.nombre}: sin prueba o sin ajuste'
        if c.tipo == 'empresa':
            assert {f['empresa'] for f in prueba} == {c.retenida}, f'semilla {semilla}, {c.nombre}'
            assert c.retenida not in {f['empresa'] for f in ajuste}, f'semilla {semilla}, {c.nombre}'
            assert len(prueba) == sum(f['empresa'] == c.retenida for f in filas), f'semilla {semilla}, {c.nombre}'
        else:
            assert min(datetime.fromisoformat(f['fecha']) for f in prueba) >= corte + horizonte, f'semilla {semilla}'
            assert max(datetime.fromisoformat(f['fecha']) for f in ajuste) < corte, f'semilla {semilla}'


def test_069_rf41_sin_empresa_fecha_o_grupo_no_se_parte_con_etiquetas_inventadas():
    """069:RF-41 — las humanas sin su empresa, su fecha o su grupo no se parten: se dice y no se deducen del texto."""
    from convertersmartgrid.aplicacion.asistente import validacion_cruzada as vc
    assert hasattr(vc, 'particionar_humanas'), 'falta validacion_cruzada.particionar_humanas'
    filas, corte = _humanas_etiquetadas(1)
    for campo in vc.CAMPOS_PARTICION:
        incompletas = [dict(f) for f in filas]
        incompletas[3].pop(campo)
        with pytest.raises(ValueError, match='1 orden humana llega sin su empresa, su fecha o su grupo'):
            vc.particionar_humanas(incompletas, corte=corte)
