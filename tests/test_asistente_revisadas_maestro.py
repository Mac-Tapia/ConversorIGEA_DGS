"""047:RF-62 a RF-68 — las órdenes revisadas por el maestro deciden el ajuste mientras falten humanas, sin ser humanas.

Caso real (2026-11-21, bloque de GPU de la 043 T9): `decidir_ajuste` daba «bloqueada» con 3 de 200 órdenes humanas y la
etapa QLoRA se paraba sin decisión. El usuario, el 2026-11-19: la revisión la puede hacer un revisor marcado `maestro`.
Sin GPU, sin Ollama y sin el almacén real: todo en carpetas temporales.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.asistente import ajuste_condicionado as ac
from convertersmartgrid.aplicacion.asistente import ordenes_maestro as _om
from convertersmartgrid.aplicacion.asistente.ajuste_condicionado import decidir_ajuste, evaluar_puertas_reales
from convertersmartgrid.aplicacion.asistente.tareas import TAREAS

#: Lo nuevo se pide con aserciones: sin ello, el rojo es un fallo de la aserción, no un error de importación.
BASE_MAESTRO = 'maestro_revisadas'
CALIDAD_MAESTRO_REVISADA = 'gold_maestro_revisada'


def manifiesto_de_revisadas(revisadas, humanas):
    f = getattr(ac, 'manifiesto_de_revisadas', None)
    assert f is not None, 'ajuste_condicionado no da manifiesto_de_revisadas (047:RF-64)'
    return f(revisadas, humanas)


class _OM:
    """``ordenes_maestro`` con lo que la T12 le añade, pedido por aserción."""

    def __getattr__(self, nombre):
        valor = getattr(_om, nombre, None)
        assert valor is not None, f'ordenes_maestro no da {nombre} (047:RF-62, RF-63)'
        return valor


om = _OM()

RAIZ = Path(__file__).resolve().parents[1]


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(f'h_{nombre}', RAIZ / 'tools' / f'{nombre}.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def metricas(acierto=.99, f1=.97, ejemplos=200):
    return {'acierto_tarea': acierto, 'f1_datos': f1, 'ejemplos': ejemplos}


def revisadas(n=200, **extra):
    return {'ejemplos': n, 'unicos': n, 'sin_fuga': True, 'dataset_hash': 'c' * 64, 'origen': 'maestro',
            'sellado': True, **extra}


# --- RF-64 a RF-67: la decisión ------------------------------------------------------------------------------------------

@pytest.mark.parametrize('acierto,decision', [(.99, 'no_necesaria'), (.90, 'necesaria')])
def test_con_200_revisadas_y_3_humanas_decide_el_conjunto_del_maestro(acierto, decision):
    """047:RF-64 / 047:RF-65 — decide por sus cifras, con su base, y dice que no son humanas y cuántas faltan."""
    d = decidir_ajuste(metricas(acierto=acierto), manifiesto_de_revisadas(revisadas(), 3))
    assert d['decision'] == decision
    assert d['base'] == BASE_MAESTRO
    ev = d['evidencia']
    assert ev['ordenes_reales'] == 3 and ev['ordenes_maestro_revisadas'] == 200 and ev['humanas_que_faltan'] == 197
    texto = ' '.join(d['motivos'])
    assert 'maestro' in texto and 'no humanas' in texto and '197' in texto and 'c' * 64 in texto
    assert d['entrenado'] is False and d['promovido'] is False


@pytest.mark.parametrize('cambio,frase', [
    ({'n': 199}, '199 órdenes revisadas por el maestro'),
    ({'sellado': False}, 'sellado'),
    ({'origen': 'humano'}, 'origen'),
    ({'sin_fuga': False}, 'fuera del entrenamiento'),
    ({'dataset_hash': None}, 'huella'),
])
def test_el_conjunto_del_maestro_sin_sello_o_corto_se_bloquea(cambio, frase):
    """047:RF-66 — sin 200, sin sello, de otro origen, con fuga o sin huella no hay veredicto."""
    n = cambio.pop('n', 200)
    d = decidir_ajuste(metricas(ejemplos=n), manifiesto_de_revisadas(revisadas(n, **cambio), 3))
    assert d['decision'] == 'bloqueada' and any(frase in m for m in d['motivos']), d['motivos']


def test_con_200_humanas_deciden_las_humanas_y_no_el_maestro():
    """047:RF-66 — con 200 humanas o más, la base del maestro no decide."""
    d = decidir_ajuste(metricas(), manifiesto_de_revisadas(revisadas(), 200))
    assert d['decision'] == 'bloqueada' and any('deciden las humanas' in m for m in d['motivos'])


def test_mezclar_humanas_con_revisadas_no_vale():
    """047:RF-66 — el conjunto que decide es de una sola calidad."""
    m = manifiesto_de_revisadas(revisadas(), 3)
    m['calidades'] = {CALIDAD_MAESTRO_REVISADA: 200, 'gold_human': 3}
    p = evaluar_puertas_reales(metricas(ejemplos=203), m)
    assert not p['suficiente'] and any('gold_human' in f for f in p['faltas'])


def test_las_revisadas_nunca_pasan_por_humanas():
    """047:RF-67 — declaradas como humanas (sin la base del maestro) siguen sin contar."""
    d = decidir_ajuste(metricas(), {'calidades': {CALIDAD_MAESTRO_REVISADA: 200}, 'ordenes_reales_distintas': 200,
                                    'sin_fuga': True, 'dataset_hash': 'a' * 64})
    assert d['decision'] == 'bloqueada' and any(CALIDAD_MAESTRO_REVISADA in m for m in d['motivos'])


def _propuestas():
    nombres = sorted(TAREAS)
    casos = [{'record_id': f'{i:064x}', 'esperado': nombres[i % len(nombres)], 'obtenido': nombres[i % len(nombres)],
              'correcto': True, 'confirmacion': True, 'vp': 1, 'fp': 0, 'fn': 0} for i in range(200)]
    familias = {t: {'ejemplos': sum(c['esperado'] == t for c in casos), 'acierto_tarea': 1., 'f1_datos': 1.} for t in nombres}
    return {'ejemplos': 200, 'unicos': 200, 'tareas': len(nombres), 'acierto_tarea': 1., 'f1_datos': 1., 'familias': familias,
            'casos': casos, 'confirmaciones_conservadas': True, 'sin_fuga': True}


def test_la_aceptacion_publica_aparte_las_humanas_y_las_revisadas():
    """047:RF-65 / 047:RF-67 — decide el maestro; las 3 humanas se dan aparte y la autónoma sigue cerrada."""
    import inspect
    from convertersmartgrid.aplicacion.asistente.aceptacion import decidir_aceptacion
    assert 'maestro_revisadas' in inspect.signature(decidir_aceptacion).parameters, 'sin las revisadas (047:RF-65)'
    humanas = {'ejemplos': 3, 'unicos': 3, 'acierto_tarea': 1., 'f1_datos': 1.}
    r = decidir_aceptacion(_propuestas(), humanas, {**metricas(acierto=.9), **revisadas()})
    assert r['ajuste']['decision'] == 'necesaria' and r['ajuste']['base'] == BASE_MAESTRO
    assert r['puertas_humanas']['ordenes_reales'] == 3 and r['puertas_humanas']['suficiente'] is False
    assert r['humanas']['ejemplos'] == 3 and r['maestro_revisadas']['ejemplos'] == 200
    assert r['autonoma']['aprobada'] is False and '3 órdenes humanas' in r['autonoma']['motivo']
    sin = decidir_aceptacion(_propuestas(), humanas)
    assert sin['ajuste']['decision'] == 'bloqueada' and sin['ajuste']['base'] == 'humanas'


# --- RF-62, RF-63: registro y sello --------------------------------------------------------------------------------------

_VALORES = {'alimentadores': 'AB101', 'proyecto': 'Red Demo Norte', 'sistema': 'Costa Clara', 'sed': 'SED01001',
            'periodo': '2026-07', 'ruta': 'D:/ensayo/demanda_01.xlsx', 'numero': '10', 'subtipo': 'refuerzo de red',
            'set': 'SET Uno', 'estudio': 'flujo', 'alcance': 'sistema', 'texto': 'por qué no converge'}


def _orden(tarea, i=0, **extra):
    texto, datos = f'orden {i} para {tarea.replace("_", " ")}', []
    for d in TAREAS[tarea].datos:
        if d.obligatorio:
            valor = _VALORES[d.tipo]
            texto += ' con '
            datos.append([len(texto), len(texto) + len(valor), d.tipo])
            texto += valor
    fila = {'texto': texto, 'tarea': tarea, 'datos': datos, 'origen': 'maestro', 'autor': 'maestro-d8',
            'revisor': 'revisor-maestro', 'veredicto': 'aceptada', 'motivo': f'pide {tarea}; datos en el texto'}
    fila.update(extra)
    return fila


def _todas():
    return [_orden(t, i) for i, t in enumerate(sorted(TAREAS))]


def _almacen(tmp_path, humanas=(), maestro=()):
    a = tmp_path / 'almacen'
    a.mkdir()
    (a / 'ejemplos.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in humanas), encoding='utf-8')
    (a / om.ARCHIVO).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in maestro), encoding='utf-8')
    return a


def _revisar(tmp_path, almacen, filas, nombre='entrada.jsonl'):
    entrada = tmp_path / nombre
    entrada.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in filas), encoding='utf-8')
    h = _cargar('asistente_ordenes_reales')
    assert hasattr(h, 'revisar_maestro'), 'asistente_ordenes_reales no tiene revisar-maestro (047:RF-62)'
    args = argparse.Namespace(almacen=almacen, entrada=entrada)
    return h.revisar_maestro(args)


def test_registra_y_sella_las_revisadas_de_todas_las_tareas(tmp_path):
    """047:RF-62 — prueba sellada, calidad propia, origen maestro, con revisor y motivo; nunca entrena."""
    a = _almacen(tmp_path)
    r = _revisar(tmp_path, a, _todas())
    assert r['ok'] and r['selladas'] == len(TAREAS) and r['tareas'] == len(TAREAS)
    filas, manifiesto = om.leer_revisadas(a / om.SUBCARPETA_REVISADAS)
    assert len(filas) == len(TAREAS) and manifiesto['dataset_hash'] == r['dataset_hash']
    assert manifiesto['no_son_humanas'] is True and manifiesto['entrena'] is False
    for f in filas:
        assert f['quality'] == CALIDAD_MAESTRO_REVISADA and f['origen'] == 'maestro' and f['particion'] == 'prueba'
        assert f['conjunto'] == om.CONJUNTO_REVISADAS and f['revisor'] and f['motivo'] and f['del_maestro'] is True
    # Volver a registrar lo mismo no cambia nada.
    assert _revisar(tmp_path, a, _todas())['dataset_hash'] == r['dataset_hash']
    # Las que entrenan (085:RF-1) no leen el conjunto sellado.
    assert om.leer(a)[0] == []


@pytest.mark.parametrize('cambio,motivo', [
    ({'origen': 'confirmado'}, 'rechazadas_origen'),
    ({'motivo': ''}, 'rechazadas_sin_motivo'),
    ({'revisor': ''}, 'rechazadas_sin_motivo'),
    ({'tarea': 'tarea_que_no_existe'}, 'rechazadas_tarea'),
    ({'datos': [[0, 999, 'alimentadores']]}, 'rechazadas_datos'),
    ({'datos': []}, 'rechazadas_datos'),
    ({'veredicto': 'rechazada'}, 'rechazadas_por_el_revisor'),
])
def test_una_orden_mal_revisada_no_se_sella_y_se_cuenta(tmp_path, cambio, motivo):
    """047:RF-63 — la mala se cuenta por su motivo; sin ella falta una tarea y no se sella nada."""
    filas = _todas()
    i = next(n for n, f in enumerate(filas) if f['tarea'] == 'convertir')
    filas[i] = {**filas[i], **cambio}
    a = _almacen(tmp_path)
    r = _revisar(tmp_path, a, filas)
    assert r['cuenta'][motivo] == 1
    assert r['ok'] is False and 'tareas' in ' '.join(r['errores'])
    assert not (a / om.SUBCARPETA_REVISADAS).exists()


def test_texto_repetido_o_familia_que_entrena_no_se_sella(tmp_path):
    """047:RF-63 — ni repetida, ni en la familia de una humana o de una orden del maestro que entrena."""
    filas = _todas()
    filas.append({**filas[0], 'texto': filas[0]['texto'].upper()})
    conv = next(f for f in filas if f['tarea'] == 'convertir')
    humana = {'texto': conv['texto'].replace('AB101', 'CD202'), 'tarea': 'convertir',
              'datos': conv['datos'], 'origen': 'confirmado'}
    flujo = next(f for f in filas if f['tarea'] == 'flujo')
    del_maestro = {k: flujo[k] for k in ('texto', 'tarea', 'datos', 'origen')}
    a = _almacen(tmp_path, humanas=[humana], maestro=[{**del_maestro, 'autor': 'm', 'revision': 'r', 'forma': 'f'}])
    r = _revisar(tmp_path, a, filas)
    assert r['cuenta']['rechazadas_repetidas'] == 1
    assert r['cuenta']['rechazadas_familia_que_entrena'] == 2
    assert r['ok'] is False


def test_dos_preguntas_distintas_no_son_de_la_misma_familia(tmp_path):
    """047:RF-63 — el dato `texto` de una pregunta es el mensaje entero (069:RF-36): no se enmascara al comparar."""
    filas = _todas()
    i = next(n for n, f in enumerate(filas) if f['tarea'] == 'pregunta')
    texto = 'cómo elige el conversor la troncal'
    filas[i] = {**filas[i], 'texto': texto, 'datos': [[0, len(texto), 'texto']]}
    otra = 'por qué no converge un flujo de carga'
    a = _almacen(tmp_path, maestro=[{'texto': otra, 'tarea': 'pregunta', 'datos': [[0, len(otra), 'texto']],
                                     'origen': 'maestro', 'autor': 'm', 'revision': 'r', 'forma': 'f'}])
    r = _revisar(tmp_path, a, filas)
    assert r['ok'], r
    assert r['cuenta'].get('rechazadas_familia_que_entrena', 0) == 0


def test_no_sustituye_un_conjunto_sellado_distinto(tmp_path):
    """047:RF-63 — el sello no se pisa con otro contenido."""
    a = _almacen(tmp_path)
    assert _revisar(tmp_path, a, _todas())['ok']
    otras = _todas()
    otras[0] = {**otras[0], 'motivo': 'otro motivo'}
    r = _revisar(tmp_path, a, otras, 'otra.jsonl')
    assert r['ok'] is False and 'sellado' in ' '.join(r['errores'])


def test_un_sello_tocado_no_se_lee(tmp_path):
    """047:RF-68 — la evaluación no mide un conjunto cuyo contenido ya no es el sellado."""
    a = _almacen(tmp_path)
    _revisar(tmp_path, a, _todas())
    ruta = a / om.SUBCARPETA_REVISADAS / 'ordenes.jsonl'
    ruta.write_text(ruta.read_text(encoding='utf-8').replace('orden 0', 'orden cero'), encoding='utf-8')
    with pytest.raises(ValueError, match='sello'):
        om.leer_revisadas(a / om.SUBCARPETA_REVISADAS)


# --- RF-68: medida, decisión para el QLoRA y la campaña ------------------------------------------------------------------

def test_la_medida_del_conjunto_sellado_acredita_sello_y_fuga(tmp_path):
    """047:RF-68 — con su huella y sin fuga decide; si un texto está en el entrenamiento, no."""
    from convertersmartgrid.aplicacion.asistente import aceptacion
    medida_revisadas = getattr(aceptacion, 'medida_revisadas', None)
    assert medida_revisadas is not None, 'aceptacion no da medida_revisadas (047:RF-68)'
    a = _almacen(tmp_path)
    _revisar(tmp_path, a, _todas())
    filas, manifiesto = om.leer_revisadas(a / om.SUBCARPETA_REVISADAS)
    m = medida_revisadas(metricas(ejemplos=len(filas)), filas, manifiesto, set())
    assert m['sellado'] is True and m['origen'] == 'maestro' and m['sin_fuga'] is True
    assert m['dataset_hash'] == manifiesto['dataset_hash'] and m['unicos'] == len(filas)
    fuga = medida_revisadas(metricas(ejemplos=len(filas)), filas, manifiesto, {filas[0]['texto'].upper()})
    assert fuga['sin_fuga'] is False


def test_la_decision_del_maestro_abre_el_qlora_y_la_campana_la_pasa(tmp_path, monkeypatch):
    """047:RF-68 — `reentrenar_modelos.py run --qlora-decision` pasa el fichero a `asistente_qlora.py --decision`."""
    m = _cargar('reentrenar_modelos')
    vistos = []
    monkeypatch.setattr(m, '_subproceso', lambda cmd, reporte, nombre, **k: vistos.append(cmd) or {})
    decision = tmp_path / 'decision_ajuste.json'
    decision.write_text(json.dumps(decidir_ajuste(metricas(acierto=.9), manifiesto_de_revisadas(revisadas(), 3))),
                        encoding='utf-8')

    class Args(argparse.Namespace):
        def __getattr__(self, _nombre):          # lo que la etapa QLoRA no usa queda en None
            return None

    a = Args(llm_dataset=tmp_path / 'llm', qlora_decision=decision, semillas='11', dataset=tmp_path / 'ds',
             vocabulario=None)
    etapa = next(e for e in m._etapas(a, tmp_path / 'run') if e.name == 'qlora')
    etapa.run()
    assert vistos and '--decision' in vistos[-1], vistos
    assert vistos[-1][vistos[-1].index('--decision') + 1] == str(decision)
    assert json.loads(decision.read_text(encoding='utf-8'))['decision'] == 'necesaria'
    # La opción existe en la línea de órdenes de la campaña.
    assert '--qlora-decision' in (RAIZ / 'tools/reentrenar_modelos.py').read_text(encoding='utf-8')
