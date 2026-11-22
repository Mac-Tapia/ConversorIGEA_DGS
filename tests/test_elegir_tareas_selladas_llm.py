"""047:RF-60 y 047:RF-61: la elección del alumno y la apertura de la prueba miden contra las tareas del sellado.

El corpus v6 se selló con 27 tareas y el catálogo creció después: la elección pedía las familias del catálogo vigente y
daba «metricas de seleccion incompletas» con un informe completo para su corpus. Ahora manda el manifiesto sellado, y
las tareas que ese sellado no tiene se declaran en el informe, sin cerrar el hueco en silencio.
"""
import json

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.aplicacion.asistente import llm_destilacion as llm
from convertersmartgrid.aplicacion.asistente.tareas import TAREAS as CATALOGO_VIGENTE
from convertersmartgrid.aplicacion.evaluacion_modelos import huella

NO_CUBIERTAS = 'no_cubiertas_por_este_sellado'


@pytest.fixture
def sellado(tmp_path):
    """Un corpus sintético sellado con una sola tarea, «estado», en cada partición."""
    fuente = tmp_path / 'datos.txt'
    fuente.write_text('registro sintético', encoding='utf-8')
    evidencia = llm.custodiar(fuente, localizador='archivo completo')
    dataset = tmp_path / 'dataset'
    dataset.mkdir()
    filas, contextos = [], []
    for parte in llm.PARTICIONES:
        contextos.append({'source_fingerprint': 'origen-sintetico', 'network_id': parte, 'particion': parte,
                          'alimentador': parte, 'proyectos': [], 'sistema': None, 'seds': [], 'ruta': str(fuente),
                          'periodos': [], 'fuentes': {'red': evidencia}})
        registro = {'texto': 'estado de ' + parte, 'tarea': 'estado', 'datos': [], 'particion': parte,
                    'context_id': huella(['origen-sintetico', parte]), 'group_id': parte,
                    'quality': 'silver_teacher_real_source', 'fuentes': [evidencia]}
        registro['respuesta'] = llm.respuesta_maestro(registro)
        registro['record_id'] = huella(registro)
        filas.append(registro)
    (dataset / 'corpus.json').write_text(json.dumps(filas), encoding='utf-8')
    (dataset / 'contextos.json').write_text(json.dumps(contextos), encoding='utf-8')
    meta = {'schema_version': 2, 'dataset_hash': huella(filas), 'por_particion': {p: 1 for p in llm.PARTICIONES},
            'por_tarea': {p: {'estado': 1} for p in llm.PARTICIONES}}
    (dataset / 'dataset_manifest.json').write_text(json.dumps(meta), encoding='utf-8')
    destino = tmp_path / 'sellado'
    llm.sellar_particiones(dataset, destino)
    return destino


def _manifiesto(sellado):
    return json.loads((sellado / 'dataset_manifest.json').read_text(encoding='utf-8'))


def _informe(meta, familias, *, modelo='alumno:prueba', acierto=.75):
    return {'particion': 'seleccion', 'modelo': modelo, 'modelo_digest': 'digest-' + modelo,
            'dataset_hash': meta['dataset_hash'], 'prompt_hash': meta['prompt_hash'],
            'metricas': {'ejemplos': len(familias), 'acierto_tarea': acierto, 'f1_datos': .8,
                         'familias': {t: {'ejemplos': 1, 'acierto_tarea': acierto, 'f1_datos': .8} for t in familias}}}


def test_elige_con_las_tareas_del_sellado_y_declara_las_no_cubiertas(sellado):
    """047:RF-60: un informe completo para su sellado se elige aunque el catálogo vigente tenga más tareas."""
    meta = _manifiesto(sellado)
    assert set(CATALOGO_VIGENTE) - {'estado'}, 'el catálogo vigente tiene tareas que este sellado no tiene'
    eleccion = llm.elegir_version_llm([_informe(meta, ['estado'], modelo='a', acierto=.5),
                                       _informe(meta, ['estado'], modelo='b', acierto=.9)], manifiesto=meta)
    assert eleccion['modelo'] == 'b'
    assert eleccion.get('tareas_selladas') == ['estado']
    no_cubiertas = eleccion.get(NO_CUBIERTAS) or {}
    assert no_cubiertas.get('tareas') == sorted(set(CATALOGO_VIGENTE) - {'estado'})
    assert no_cubiertas.get('cuantas') == len(set(CATALOGO_VIGENTE) - {'estado'})


def test_informe_al_que_le_falta_o_sobra_una_tarea_sellada_se_rechaza_nombrandola(sellado):
    """047:RF-60: la comparación con el sellado no rebaja la exigencia: falta o sobra, y cuál."""
    meta = _manifiesto(sellado)
    with pytest.raises(ValueError, match='faltan: estado'):
        llm.elegir_version_llm([_informe(meta, [])], manifiesto=meta)
    with pytest.raises(ValueError, match='sobran: buscar_internet'):
        llm.elegir_version_llm([_informe(meta, ['estado', 'buscar_internet'])], manifiesto=meta)


def test_sin_manifiesto_o_de_otro_sellado_no_se_elige(sellado):
    """047:RF-60: sin el manifiesto sellado, o con el de otro corpus o prompt, no hay elección."""
    meta = _manifiesto(sellado)
    with pytest.raises(ValueError, match='manifiesto sellado'):
        llm.elegir_version_llm([_informe(meta, ['estado'])])
    for clave in ('dataset_hash', 'prompt_hash'):
        with pytest.raises(ValueError, match='otro sellado'):
            llm.elegir_version_llm([_informe(meta, ['estado'])], manifiesto={**meta, clave: 'otro'})


class _ClienteFalso:
    """Ollama de mentira: solo lo que mira ``evaluar_version_llm`` antes y después de medir."""

    def __init__(self, *, modelo, **_):
        self.modelo = modelo

    def _pedir(self, ruta):
        return {'models': [{'name': self.modelo, 'digest': 'digest-' + self.modelo}]}

    def liberar_gpu(self, **_):
        return None


@pytest.fixture
def ollama_falso(monkeypatch):
    from convertersmartgrid.aplicacion.asistente import aceptacion, ollama
    monkeypatch.setattr(ollama, 'ClienteOllama', _ClienteFalso)
    monkeypatch.setattr(aceptacion, 'evaluar_ordenes', lambda registros, **_: {
        'ejemplos': len(registros), 'acierto_tarea': 1.0, 'f1_datos': 1.0,
        'familias': {'estado': {'ejemplos': len(registros), 'acierto_tarea': 1.0, 'f1_datos': 1.0}}})


def test_la_prueba_se_abre_con_la_eleccion_del_sellado_y_lo_declara(sellado, tmp_path, ollama_falso):
    """047:RF-61: la prueba se abre con la elección hecha sobre las tareas del sellado y su informe dice cuáles faltan."""
    meta = _manifiesto(sellado)
    eleccion = llm.elegir_version_llm([_informe(meta, ['estado'])], manifiesto=meta)
    archivo = tmp_path / 'seleccion.json'
    archivo.write_text(json.dumps(eleccion), encoding='utf-8')
    resultado = llm.evaluar_version_llm(sellado, 'alumno:prueba', parte='prueba', seleccion=archivo, log=lambda *a, **k: None)
    assert resultado['particion'] == 'prueba'
    assert resultado.get('tareas_selladas') == ['estado']
    assert (resultado.get(NO_CUBIERTAS) or {}).get('tareas') == sorted(set(CATALOGO_VIGENTE) - {'estado'})


def test_eleccion_sin_las_tareas_del_sellado_no_abre_la_prueba(sellado, tmp_path, ollama_falso):
    """047:RF-61: una elección que no dice con qué tareas se hizo, o con otras, no abre la prueba sellada."""
    meta = _manifiesto(sellado)
    eleccion = llm.elegir_version_llm([_informe(meta, ['estado'])], manifiesto=meta)
    for alterada in ({k: v for k, v in eleccion.items() if k != 'tareas_selladas'},
                     {**eleccion, 'tareas_selladas': ['estado', 'buscar_internet']}):
        archivo = tmp_path / 'seleccion.json'
        archivo.write_text(json.dumps(alterada), encoding='utf-8')
        with pytest.raises(ValueError, match='tareas del sellado'):
            llm.evaluar_version_llm(sellado, 'alumno:prueba', parte='prueba', seleccion=archivo,
                                    log=lambda *a, **k: None)


def test_orden_elegir_con_el_corpus_sellado(sellado, tmp_path, capsys):
    """047:RF-60: ``tools/llm_destilar.py elegir --dataset`` elige con el manifiesto del corpus y lo deja escrito."""
    meta = _manifiesto(sellado)
    informe = tmp_path / 'resultado.json'
    informe.write_text(json.dumps(_informe(meta, ['estado'])), encoding='utf-8')
    herramienta = cargar_herramienta('llm_destilar.py')
    destino = tmp_path / 'eleccion'
    assert herramienta.main(['elegir', '--informe', str(informe), '--dataset', str(sellado),
                             '--destino', str(destino)]) == 0
    salida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert salida['ok'] and salida.get('tareas_selladas') == 1
    assert salida.get('no_cubiertas') == len(set(CATALOGO_VIGENTE) - {'estado'})
    escrita = json.loads((destino / 'seleccion.json').read_text(encoding='utf-8'))
    assert escrita.get('tareas_selladas') == ['estado'] and NO_CUBIERTAS in escrita
