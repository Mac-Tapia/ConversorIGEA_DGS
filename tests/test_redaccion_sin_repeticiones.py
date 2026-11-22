"""072:RF-58 a RF-62 — lo que corrige el rechazo del primer modelo de redacción del PIDE, sin GPU y con nombres ficticios.

El 2026-11-21 el candidato bajó mucho la pérdida frente a la base, pero en un caso de prueba puso cifras y encadenó la
misma frase hasta su tope. Aquí: el prompt exige los marcadores, la decodificación penaliza repetir (al examinar y al
publicar), una salida que repite una frase se rechaza, el corpus no enseña frases repetidas y un sellado que crece
conserva las particiones del anterior y lo declara.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.asistente import corpus_redaccion as cr

RAIZ = Path(__file__).resolve().parents[1]
#: 072:RF-20: nombres inventados, casos de prueba del conversor.
CATALOGO = {'empresa': ['Electro Ficticia'], 'instalacion': ['Laguna Azul']}
_TEMAS = ('la demanda', 'las pérdidas', 'la confiabilidad', 'los costos', 'el crecimiento', 'las obras',
          'la tensión', 'los criterios', 'la calidad', 'el horizonte', 'las alternativas', 'la red')
#: La salida mala del 2026-11-21, con sus cifras ya ocultas: la misma frase encadenada.
BUCLE = ('Remodelación de la troncal y ramales en el tramo de ‹n› a ‹n›. por antigüedad del conductor con conductor '
         '‹código› en un tramo de ‹n›. por antigüedad del conductor con conductor ‹código› en un tramo de ‹n›.')
#: Una tabla aprobada: sus filas se parecen, pero ninguna se repite entera a continuación.
TABLA = ('| Media Tensión | Redes | Aéreas | km | ‹n› | ‹n›\n| Media Tensión | Redes | Subterráneas | km | ‹n› | ‹n›\n'
         '| Media Tensión | Equipos de protección | Reconectadores | u | ‹n› | ‹n›')


def _herramienta(nombre):
    spec = importlib.util.spec_from_file_location(f'h_{nombre}', RAIZ / f'tools/{nombre}.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _atributos(modulo, *nombres):
    faltan = [n for n in nombres if not hasattr(modulo, n)]
    assert not faltan, f'faltan {faltan} en {modulo.__name__}'
    return [getattr(modulo, n) for n in nombres]


_VERBOS = ('se describe', 'se resume', 'se justifica')


def _corpus(tmp_path, documentos, *, extra=(), aprobados=None):
    """``documentos`` documentos de tres párrafos, más los fragmentos de ``extra``; aprobados los de los primeros
    ``aprobados`` documentos (todos, si no se dice) y los de ``extra``."""
    carpeta = tmp_path / 'pide'
    carpeta.mkdir(exist_ok=True)
    frags = [{'record_id': f'r{d}_{k}', 'empresa': 'Electro Ficticia', 'relative_path': f'PIDE X/{d}.docx',
              'location': 'document', 'periodo': '2026',
              'text': f'En la SET Laguna Azul {_TEMAS[d]} {_VERBOS[k]} con 12 MW en el capítulo {k} y su anexo.'}
             for d in range(documentos) for k in range(3)]
    elegidos = [f for f in frags if int(f['record_id'][1:].split('_')[0]) < (documentos if aprobados is None
                                                                               else aprobados)]
    frags += list(extra)
    elegidos += list(extra)
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    registro = carpeta / 'revision_redaccion.jsonl'
    registro.unlink(missing_ok=True)
    for f in elegidos:
        cr.registrar_revision(registro, f, revisor='revisor de prueba', origen='maestro', aprobado=True,
                              uso='redaccion', fecha='2026-11-22')
    return carpeta


def test_el_prompt_exige_los_marcadores_y_lo_anterior_se_sigue_leyendo(tmp_path, monkeypatch):
    """072:RF-58 — el prompt sellado exige ‹n›, ‹código› y los nombres ocultos y prohíbe repetir; un corpus sellado con
    el prompt anterior se sigue leyendo, y uno con otro prompt no."""
    v1, sistemas = _atributos(cr, 'SISTEMA_REDACCION_V1', 'SISTEMAS_REDACCION')
    for marca in ('‹n›', '‹código›', '‹empresa›', '‹sede›', '‹instalación›'):
        assert marca in cr.SISTEMA_REDACCION, marca
    assert 'Nunca escribes dígitos' in cr.SISTEMA_REDACCION and 'No repites frases' in cr.SISTEMA_REDACCION
    assert sistemas == (cr.SISTEMA_REDACCION, v1) and v1 != cr.SISTEMA_REDACCION
    carpeta = _corpus(tmp_path, 10)
    meta = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'vigente', catalogo=CATALOGO)
    assert meta['sistema'] == cr.SISTEMA_REDACCION
    registros, _ = cr.leer_particion_redaccion(tmp_path / 'vigente', 'entrenamiento')
    assert all('‹n›' in r['respuesta'] and not any(ch.isdigit() for ch in r['respuesta']) for r in registros)
    monkeypatch.setattr(cr, 'SISTEMA_REDACCION', v1)
    cr.sellar_corpus_redaccion(carpeta, tmp_path / 'anterior', catalogo=CATALOGO)
    monkeypatch.setattr(cr, 'SISTEMA_REDACCION', 'Otro prompt cualquiera.')
    cr.sellar_corpus_redaccion(carpeta, tmp_path / 'otro', catalogo=CATALOGO)
    monkeypatch.undo()
    _registros, meta_v1 = cr.leer_particion_redaccion(tmp_path / 'anterior', 'entrenamiento')
    assert meta_v1['sistema'] == v1
    with pytest.raises(ValueError, match='prompt distinto'):
        cr.leer_particion_redaccion(tmp_path / 'otro', 'entrenamiento')


def test_una_salida_que_encadena_la_misma_frase_se_rechaza():
    """072:RF-60 — la frase encadenada del 2026-11-21 es «repetida»; las filas parecidas de una tabla, no."""
    frase_repetida, = _atributos(cr, 'frase_repetida')
    assert frase_repetida(BUCLE) is True
    assert frase_repetida(TABLA) is False
    assert frase_repetida('La demanda crece. La demanda crece.') is False   # menos de ocho palabras
    assert cr.revisar_salida('Redacta un párrafo de un informe PIDE, claro y formal.', BUCLE) == ['repetida']
    assert cr.revisar_salida(BUCLE, BUCLE) == []      # lo que repite la entrada no es del modelo


def test_el_corpus_sellado_no_ensena_frases_repetidas(tmp_path):
    """072:RF-61 — un texto aprobado que, con los códigos ocultos, repite seguida una frase no entra, y se cuenta."""
    _atributos(cr, 'frase_repetida')
    bucle = {'record_id': 'bucle', 'empresa': 'Electro Ficticia', 'relative_path': 'PIDE X/0.docx',
             'location': 'document', 'periodo': '2026',
             'text': ('ITEM | NOMBRE DE PROYECTO\n1 | Remodelación de troncal y ramales por antigüedad del alimentador '
                      'A101\n2 | Remodelación de troncal y ramales por antigüedad del alimentador A102')}
    carpeta = _corpus(tmp_path, 10, extra=[bucle])
    meta = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'sellado', catalogo=CATALOGO)
    filas = json.loads((tmp_path / 'sellado' / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    assert 'bucle' not in {f['fragmento'] for f in filas}
    assert meta.get('repetidas_omitidas') == 1 and meta.get('sin_repetidas') is True
    from convertersmartgrid.aplicacion.evaluacion_modelos import huella
    fila = dict(filas[0], respuesta=BUCLE)
    fila['record_id'] = huella({k: v for k, v in fila.items() if k != 'record_id'})
    nuevas = [fila, *filas[1:]]
    with pytest.raises(ValueError, match='frase repetida'):
        cr.validar_corpus_redaccion(nuevas, {**meta, 'dataset_hash': huella(nuevas)})


def test_un_sellado_que_crece_conserva_las_particiones_del_anterior(tmp_path):
    """072:RF-62 — con `anterior`, cada documento ya sellado conserva su partición, solo lo nuevo se reparte, y el
    manifiesto declara a qué sellado sustituye."""
    import inspect
    assert 'anterior' in inspect.signature(cr.sellar_corpus_redaccion).parameters,         'el sellado no admite el sellado al que sustituye'
    carpeta = _corpus(tmp_path, 12, aprobados=10)
    antes = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'v1', catalogo=CATALOGO)
    filas_antes = json.loads((tmp_path / 'v1' / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    parte_antes = {f['group_id']: f['particion'] for f in filas_antes}
    carpeta = _corpus(tmp_path, 12)
    despues = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'v2', catalogo=CATALOGO, anterior=tmp_path / 'v1')
    filas = json.loads((tmp_path / 'v2' / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    assert all(parte_antes[f['group_id']] == f['particion'] for f in filas if f['group_id'] in parte_antes)
    assert sum(despues['por_particion'].values()) == 36 > sum(antes['por_particion'].values())
    declarado = despues.get('sustituye_a') or {}
    assert declarado.get('dataset_hash_anterior') == antes['dataset_hash']
    assert declarado.get('documentos_conservados') == 10 and declarado.get('documentos_nuevos') == 2
    assert cr.repartir_documentos({'a': 5, 'b': 5}, {'a': 'prueba'}) == {'a': 'prueba', 'b': 'entrenamiento'}


def test_la_decodificacion_penaliza_repetir_al_examinar_y_al_publicar(tmp_path, monkeypatch):
    """072:RF-59 — Ollama redacta con penalización de repeticiones, el Modelfile del modelo de redacción la lleva y
    `llm_destilar.py publicar --redaccion` la pide."""
    from convertersmartgrid.aplicacion.asistente import llm_runtime
    from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
    decod, = _atributos(cr, 'DECODIFICACION')
    texto_modelfile, = _atributos(llm_runtime, 'texto_modelfile')
    assert decod['repeat_penalty'] > 1 and decod['repeat_last_n'] >= 64
    pedidas = []

    class _Respuesta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def abrir(peticion, timeout):
        pedidas.append(json.loads(peticion.data))
        return _Respuesta(json.dumps({'message': {'content': 'Un párrafo.'}}).encode())

    ClienteOllama(modelo='csg-alumno:prueba', abrir=abrir).redactar('S', 'Redacta.', semilla=3)
    assert pedidas[0]['options']['repeat_penalty'] == decod['repeat_penalty']
    assert pedidas[0]['options']['repeat_last_n'] == decod['repeat_last_n']
    modelfile = texto_modelfile(decod)
    assert modelfile.startswith('FROM ./alumno.Q4_K_M.gguf\nPARAMETER num_ctx 4096\n')
    assert f"PARAMETER repeat_penalty {decod['repeat_penalty']}" in modelfile
    assert texto_modelfile() == 'FROM ./alumno.Q4_K_M.gguf\nPARAMETER num_ctx 4096\n'
    with pytest.raises(ValueError):
        texto_modelfile({'SYSTEM malicioso': 1})
    llamadas = []
    monkeypatch.setattr(llm_runtime, 'publicar', lambda ck, destino, modelo, **k: llamadas.append(k) or {
        'publicado': True, 'activado': False, 'modelo': modelo, 'modelo_digest': 'd', 'sha256_gguf': 'h'})
    rc = _herramienta('llm_destilar').main(['publicar', '--checkpoint', str(tmp_path / 'ck'), '--destino',
                                            str(tmp_path / 'pub'), '--modelo', 'csg-alumno:prueba', '--redaccion'])
    assert rc == 0 and llamadas == [{'parametros': decod}]


def test_el_examen_decodifica_como_el_modelo_publicado(tmp_path, monkeypatch):
    """072:RF-59 — `asistente_qlora.py evaluar` redacta con la misma penalización con el adaptador y con Ollama."""
    from convertersmartgrid.aplicacion import trabajadores_ml
    from convertersmartgrid.aplicacion.asistente import llm_destilacion, ollama
    decod, no_repetir = _atributos(cr, 'DECODIFICACION', 'NO_REPETIR_NGRAMA')
    carpeta = _corpus(tmp_path, 10)
    meta = cr.sellar_corpus_redaccion(carpeta, tmp_path / 'sellado', catalogo=CATALOGO)
    (tmp_path / 'catalogo.json').write_text(json.dumps(CATALOGO, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', lambda _n: contextlib.nullcontext())
    monkeypatch.setattr(llm_destilacion, 'ficha_base', lambda: {'id': 'base/fijada', 'revision': 'a' * 40})
    muestreos, opciones = [], []

    def medir(ds, adaptador, **k):
        muestreos.append(k.get('muestreo'))
        perd = {'tokens': 9, 'suma': 9.0, 'por_token': 1.0, 'ejemplos': 3}
        return {'perdidas': {p: {'base': dict(perd, por_token=2.0), 'candidato': perd} for p in ('seleccion', 'prueba')},
                'salidas': {}, 'adaptador': str(adaptador), 'checkpoint': {}, 'base': {}, 'device': 'cuda'}

    class _Cliente:
        def __init__(self, modelo, **k):
            self.modelo = modelo

        def _pedir(self, ruta, cuerpo=None):
            return {'models': [{'name': self.modelo, 'digest': 'd'}]}

        def redactar(self, sistema, instruccion, **k):
            opciones.append(k)
            return 'La demanda de la ‹instalación› se describe en el capítulo.'

        def liberar_gpu(self, solo_actual=False):
            return []

    monkeypatch.setattr(llm_destilacion, 'medir_redaccion', medir)
    monkeypatch.setattr(ollama, 'ClienteOllama', _Cliente)
    adaptador = tmp_path / 'final' / 'adaptador'
    adaptador.mkdir(parents=True)
    (adaptador / 'adapter_config.json').write_text('{}', encoding='utf-8')
    rc = _herramienta('asistente_qlora').main(['evaluar', '--dataset', str(tmp_path / 'sellado'), '--salida',
                                               str(tmp_path / 'eval'), '--adaptador', str(adaptador),
                                               '--modelo-ollama', 'csg-alumno:prueba', '--catalogo',
                                               str(tmp_path / 'catalogo.json')])
    assert rc == 0
    assert muestreos == [{'temperature': decod['temperature'], 'top_p': decod['top_p'],
                          'repetition_penalty': decod['repeat_penalty'], 'no_repeat_ngram_size': no_repetir}]
    n = meta['por_particion']['seleccion'] + meta['por_particion']['prueba']
    assert len(opciones) == n and all(o['repeat_penalty'] == decod['repeat_penalty']
                                      and o['repeat_last_n'] == decod['repeat_last_n'] for o in opciones)
