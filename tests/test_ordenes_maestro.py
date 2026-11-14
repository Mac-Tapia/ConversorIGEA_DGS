"""Spec 085 — órdenes del maestro con grupos apartados y la puerta de órdenes sin humanas suficientes.

Todo sintético: ninguna prueba lee el almacén real ni las órdenes del maestro (P9).
"""
from __future__ import annotations

import json
import random
import re

import pytest

from convertersmartgrid.asistente import destilacion_integral as di
from convertersmartgrid.asistente import ordenes_maestro as om
from convertersmartgrid.asistente.ajuste_condicionado import ACIERTO_REAL, F1_REAL, MIN_ORDENES_REALES
from convertersmartgrid.asistente.maestro_real import clave_texto

_MARCA = re.compile(r'\[\[(\w+):([^\]]+)\]\]')


def _orden(plantilla: str, tarea: str, forma: str = '', origen: str = 'maestro') -> dict:
    texto, datos, cursor = '', [], 0
    for m in _MARCA.finditer(plantilla):
        texto += plantilla[cursor:m.start()]
        datos.append([len(texto), len(texto) + len(m[2]), m[1]])
        texto += m[2]
        cursor = m.end()
    texto += plantilla[cursor:]
    return {'texto': texto, 'tarea': tarea, 'datos': datos, 'forma': forma or plantilla, 'autor': 'prueba', 'revision': 't',
            'origen': origen}


#: Ocho formas de una misma tarea, con palabras distintas para que no caigan en una familia.
FLUJO = ['corre el flujo de [[alimentadores:ZX901]]', 'oe calculame tensiones en [[alimentadores:ZX902]] porfa',
         'necesito cargabilidad del circuito [[alimentadores:ZX903]] ahorita', 'lanza potencia por [[alimentadores:ZX904]] en pf',
         'resuelve la red electrica [[alimentadores:ZX905]] nomas', 'quiero ver caidas sobre [[alimentadores:ZX906]] hoy',
         'haz correr digsi pal [[alimentadores:ZX907]] rapido', 'saca balance de carga del ramal [[alimentadores:ZX908]]']


def _escribir(tmp_path, filas):
    (tmp_path / om.ARCHIVO).write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in filas), encoding='utf-8')


def test_leer_valida_y_cuenta_los_rechazos(tmp_path):
    """085:RF-1 a RF-5 — origen, tarea, datos y obligatorios; nunca como humanas."""
    buena = _orden('convierte [[alimentadores:ZX901]]', 'convertir')
    _escribir(tmp_path, [buena, {**buena, 'origen': 'confirmado'}, {**buena, 'tarea': 'inventada'},
                         {**buena, 'datos': [[0, 999, 'alimentadores']]}, {**buena, 'datos': [[0, 4, 'sed']]},
                         {**buena, 'datos': []}, _orden('gracias, ya quedo', 'ninguna'), 'no es json'])
    filas, cuenta = om.leer(tmp_path)
    assert [f['tarea'] for f in filas] == ['convertir', 'ninguna']
    assert cuenta == {'validas': 2, 'rechazadas_origen': 1, 'rechazadas_tarea': 1, 'rechazadas_datos': 3, 'ilegibles': 1}
    assert all(f['origen'] == 'maestro' and 'quality' not in f for f in filas)


def test_reparto_aparta_el_cuarto_de_familias_por_tarea_y_no_depende_del_orden():
    """085:RF-6 a RF-9, 085:RF-12 — 25 % hacia arriba por tarea, por huella; con una familia, sin examen."""
    filas = [_orden(p, 'flujo') for p in FLUJO] + [_orden('convierte [[alimentadores:ZX901]]', 'convertir'),
                                                   _orden('gracias, ya quedo', 'ninguna')]
    examen, entrenar, estado = om.repartir(filas)
    assert estado['flujo'] == {'familias': 8, 'familias_examen': 2, 'estado': 'con_examen'}
    assert estado['convertir']['estado'] == 'sin_examen' and estado['estado']['familias'] == 0
    assert len(examen) == 2 and {r['tarea'] for r in examen} == {'flujo'}
    assert any(r['tarea'] == 'ninguna' for r in entrenar)
    revueltas = filas[:]
    random.Random(3).shuffle(revueltas)
    assert sorted(r['texto'] for r in om.repartir(revueltas)[0]) == sorted(r['texto'] for r in examen)


def test_reparto_deja_las_formas_casi_iguales_del_mismo_lado():
    """085:RF-6 — «corre el flujo» y «corre el fluj» son una familia: o examinan juntas o entrenan juntas."""
    filas = [_orden(p, 'flujo') for p in FLUJO] + [_orden(FLUJO[0].replace('flujo', 'fluj'), 'flujo')]
    examen, _entrenar, _ = om.repartir(filas)
    lado = {clave_texto(r['texto']) for r in examen}
    assert (clave_texto('corre el flujo de ZX901') in lado) == (clave_texto('corre el fluj de ZX901') in lado)


@pytest.fixture(scope='module')
def corpus():
    charla = ('gracias, ya quedo pe', 'mañana seguimos con la revision del informe', 'esa cifra no cuadra con lo que vi',
              'voy a almorzar y regreso en un rato', 'todavia no llegan los datos de la empresa', 'revisa bien antes de responder')
    maestro = [_orden(p, 'flujo') for p in FLUJO] + [_orden(t, 'ninguna') for t in charla]
    sin, meta_sin = di.preparar_corpus({}, [], por_familia=1)
    con, meta = di.preparar_corpus({}, [], por_familia=1, ordenes_maestro=maestro)
    return sin, meta_sin, con, meta, maestro


def test_corpus_examen_en_prueba_y_nada_del_examen_entrena(corpus):
    """085:RF-10, 085:RF-11, 085:RF-12, 085:RF-14, 085:RF-5 — el examen con su conjunto; el resto, con erratas, solo entrena."""
    _sin, _ms, con, meta, _m = corpus
    examen = [r for r in con if r.get('conjunto') == om.CONJUNTO]
    assert examen and all(r['particion'] == 'prueba' and r['quality'] != 'gold_human' for r in examen)
    claves = {clave_texto(r['texto']) for r in examen}
    entrena = [r for r in con if r['particion'] == 'entrenamiento']
    assert not claves & {clave_texto(r['texto']) for r in entrena}
    del_maestro = [r for r in entrena if r.get('origen') == 'maestro']
    assert any(r.get('aumentado') == 'erratas' for r in del_maestro)
    assert any(r['tarea'] == 'ninguna' for r in del_maestro)
    # La pasada de erratas del catálogo (068) no debe copiar las del maestro sin su origen: leer_corpus las rechazaba.
    assert not [r for r in entrena if r['tarea'] == 'ninguna' and r['quality'] == om.CALIDAD and r.get('origen') != 'maestro']
    assert meta['ordenes_maestro_085']['examen'] == len(examen) and meta['ordenes_maestro_085']['no_son_humanas'] is True
    assert meta['ordenes_humanas_independientes'] == 0


def test_corpus_deja_iguales_seleccion_calibracion_y_selladas(corpus):
    """085:RF-15 — lo que mide no cambia por añadir al maestro."""
    sin, meta_sin, con, meta, _m = corpus
    def medida(filas):
        return sorted(r['record_id'] for r in filas if r['particion'] in ('seleccion', 'calibracion')
                      or (r['particion'] == 'prueba' and r.get('conjunto') != om.CONJUNTO))
    assert medida(sin) == medida(con)
    for k in ('prueba_sellada', 'prueba_sellada_079', 'prueba_historica'):
        assert meta[k]['huella'] == meta_sin[k]['huella']


def test_corpus_descarta_lo_que_coincide_con_lo_que_mide_y_es_determinista(corpus, tmp_path):
    """085:RF-13, 085:RF-16 — una orden igual a una de selección se descarta y se cuenta; mismo corpus, mismas entradas."""
    sin, _ms, con, meta, maestro = corpus
    sel = next(r for r in sin if r['particion'] == 'seleccion')
    choque = {**_orden('x', sel['tarea']), 'texto': sel['texto'], 'datos': sel['datos']}
    otra, meta2 = di.preparar_corpus({}, [], por_familia=1, ordenes_maestro=[*maestro, choque])
    assert meta2['ordenes_maestro_085']['descartadas_por_lo_que_mide'] == 1
    de_nuevo, meta3 = di.preparar_corpus({}, [], por_familia=1, ordenes_maestro=maestro)
    assert meta3['dataset_hash'] == meta['dataset_hash']
    di.guardar_corpus(tmp_path / 'c', con, meta)
    assert di.leer_corpus(tmp_path / 'c')[1]['dataset_hash'] == meta['dataset_hash']


def _medida(acierto, f1, n):
    return {'acierto_tarea': acierto, 'f1_datos': f1, 'ejemplos': n, 'familias': {}}


def test_puerta_decide_el_maestro_sin_200_humanas_y_lo_dice():
    """085:RF-19, 085:RF-20, 085:RF-22, 085:RF-23, 085:RF-24 — sin 200 humanas decide el examen del maestro; la humana se da y no decide."""
    sint = _medida(1., 1., 10)
    d = di.decidir_promocion(sint, _medida(.5, .5, 43), {}, None, maestro=_medida(.99, .97, 144), humanas_distintas=43)
    assert d['puerta_ordenes']['conjunto'] == 'maestro' and d['puerta_ordenes']['denominador'] == 144
    assert d['puerta_ordenes']['humanas_que_faltan'] == 157 and 'no son órdenes humanas' in d['puerta_ordenes']['motivo']
    assert not any('humana' in f for f in d['fallos']) and d['humanas_no_deciden']['acierto_tarea'] == .5
    assert d['confirmacion_obligatoria'] is True
    malo = di.decidir_promocion(sint, _medida(1., 1., 43), {}, None, maestro=_medida(.97, .97, 144), humanas_distintas=43)
    assert 'examen del maestro: acierto_tarea bajo puerta o inválido' in malo['fallos'] and malo['status'] != 'PROMOVIDO'
    assert (ACIERTO_REAL, F1_REAL, MIN_ORDENES_REALES, om.MIN_HUMANAS) == (.98, .95, 200, 200)


def test_puerta_con_200_humanas_deciden_ellas():
    """085:RF-21 — con 200 humanas distintas o más deciden las humanas; el maestro solo se informa."""
    d = di.decidir_promocion(_medida(1., 1., 10), _medida(.5, .5, 200), {}, None, maestro=_medida(1., 1., 144),
                             humanas_distintas=200)
    assert d['puerta_ordenes']['conjunto'] == 'humanas'
    assert 'prueba humana: acierto_tarea bajo puerta o inválido' in d['fallos']


def test_puerta_tres_cifras_separadas():
    """085:RF-17, 085:RF-18 — humanas, maestro y sintéticas, cada una con su denominador."""
    t = di.tres_cifras(_medida(.7, .8, 43), _medida(.9, .9, 144), _medida(.8, .7, 300))
    assert {k: v['ejemplos'] for k, v in t.items()} == {'humanas': 43, 'maestro': 144, 'sinteticas': 300}
    assert di.tres_cifras(None, None, None) == {'humanas': None, 'maestro': None, 'sinteticas': None}


def test_clasificador_da_los_origenes_de_sus_informes(tmp_path, monkeypatch):
    """085:RF-25 — los informes etiquetados por el maestro se cuentan aparte de los del operador."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    from convertersmartgrid.asistente import almacen, clasificador
    for i in range(5):
        almacen.anotar('informes', {'texto': f'informe {i}', 'tipo': 'estudio', 'subtipo': 'PIDE',
                                    'origen': 'maestro' if i % 2 else 'corregido'})
    origenes = clasificador.origenes_de_informes()
    # 026:RF-33: qué informe va a prueba lo decide la huella de su grupo, no su posición; los orígenes se cuentan aparte.
    total = {o: origenes['entrenamiento'].get(o, 0) + origenes['prueba'].get(o, 0) for o in ('corregido', 'maestro')}
    assert total == {'corregido': 3, 'maestro': 2} and sum(origenes['prueba'].values()) == 1


# --- 097:RF-21, RF-22: ninguna orden que examina al intérprete en su entrenamiento ---------------------------------

def test_097_las_fugas_del_interprete_se_cuentan_sin_textos():
    """097:RF-21 — una orden de entrenamiento con el texto de una de prueba (con otra mayúscula o tilde) o de una humana
    cuenta; la salida son números, nunca los textos del operador."""
    from convertersmartgrid.asistente import fuga_evaluacion as fe

    filas = [{'texto': 'Calibra el alimentador QX511', 'particion': 'entrenamiento'},
             {'texto': 'calibra el alimentador qx511', 'particion': 'prueba', 'conjunto': om.CONJUNTO},
             {'texto': 'importa los txt', 'particion': 'calibracion'},
             {'texto': 'muéstrame el estado', 'particion': 'entrenamiento'}]
    cuenta = fe.fugas_del_interprete(filas, {'humanas': ['muestrame el estado', ''], 'reservados': ['hola']})
    assert cuenta == {'calibracion': 0, om.CONJUNTO: 1, 'humanas': 1, 'reservados': 0}
    assert all(isinstance(v, int) for v in cuenta.values())


def _almacen_real():
    import os
    from pathlib import Path

    ruta = os.environ.get('CSG_ASISTENTE_REAL', '').strip()
    return Path(ruta) if ruta and (Path(ruta) / 'ejemplos.jsonl').is_file() else None


@pytest.mark.skipif(_almacen_real() is None, reason='Defina CSG_ASISTENTE_REAL con la carpeta del asistente (ejemplos.jsonl)')
def test_097_el_interprete_no_entrena_con_lo_que_lo_examina(tmp_path, monkeypatch):
    """097:RF-21, 097:RF-22 — con el almacén real (órdenes humanas, del maestro, etiquetas y mensajes reservados), el corpus
    del intérprete no entrena con ninguna orden de selección, calibración, prueba, examen del maestro, humana, reservada ni
    de las pruebas selladas 070 y 079. Se copia el almacén: la prueba nunca escribe en el de la web."""
    import shutil

    from convertersmartgrid.asistente import almacen, prueba_sellada, prueba_sellada_079
    from convertersmartgrid.asistente import fuga_evaluacion as fe
    from convertersmartgrid.asistente.maestro_real import leer_etiquetas, leer_ninguna

    origen = _almacen_real()
    for nombre in ('ejemplos.jsonl', 'ordenes_maestro.jsonl', 'vocabulario.json'):
        if (origen / nombre).is_file():
            shutil.copy2(origen / nombre, tmp_path / nombre)
    if (origen / 'maestro_real').is_dir():
        shutil.copytree(origen / 'maestro_real', tmp_path / 'maestro_real', ignore=shutil.ignore_patterns('*.xlsx', '*.antes_*'))
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    humanas = almacen.leer('ejemplos')
    ninguna, reservados = leer_ninguna(almacen.raiz())
    filas, _ = di.preparar_corpus(almacen.leer_json('vocabulario') or {}, humanas,
                                  etiquetas_reales=leer_etiquetas(almacen.raiz())[0], ninguna=ninguna,
                                  ninguna_reservada=reservados, ordenes_maestro=om.leer(almacen.raiz())[0])
    cuenta = fe.fugas_del_interprete(filas, {
        'humanas': [str(h.get('texto') or '') for h in humanas], 'ninguna_reservada': reservados,
        'sellada_070': [r['texto'] for r in prueba_sellada.selladas()],
        'sellada_079': [r['texto'] for r in prueba_sellada_079.selladas()]})
    assert humanas and {'prueba', 'calibracion', 'seleccion'} <= {r['particion'] for r in filas}
    assert not any(cuenta.values()), cuenta
