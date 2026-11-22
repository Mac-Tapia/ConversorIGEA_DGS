"""072:RF-53 a RF-57 — las puertas del modelo de redacción del PIDE, sin GPU y con nombres ficticios (072:RF-20).

El modelo de redacción se examina con las particiones selladas de selección y prueba de su propio corpus: su pérdida
por token no sube frente a la base NF4, ninguna salida deja un nombre, un código o una cifra que no estén en su entrada,
y la prueba sellada del intérprete de órdenes solo cuenta si se quiere usar como intérprete. La medida en CUDA se
sustituye por un doble; la real la lanza la cola de GPU.
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
CATALOGO = {'empresa': ['Electro Ficticia'], 'sede': ['Villa Quimera'], 'instalacion': ['Laguna Azul']}
_TEMAS = ('la demanda', 'las pérdidas', 'la confiabilidad', 'los costos', 'el crecimiento', 'las obras',
          'la tensión', 'los criterios', 'la calidad', 'el horizonte')
_VERBOS = ('se describe', 'se resume', 'se justifica')


def _herramienta():
    spec = importlib.util.spec_from_file_location('asistente_qlora_072', RAIZ / 'tools/asistente_qlora.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert hasattr(modulo, '_evaluar'), 'asistente_qlora.py no tiene la orden evaluar del modelo de redacción'
    return modulo


def _api(*nombres):
    faltan = [n for n in nombres if not callable(getattr(cr, n, None))]
    assert not faltan, f'faltan las puertas del modelo de redacción: {faltan}'
    return [getattr(cr, n) for n in nombres]


@pytest.fixture
def sellado(tmp_path):
    """Diez documentos de tres párrafos, aprobados, sellados con el catálogo: hay selección y prueba."""
    carpeta = tmp_path / 'pide'
    carpeta.mkdir()
    frags = []
    for d, tema in enumerate(_TEMAS):
        for k, verbo in enumerate(_VERBOS):
            frags.append({'record_id': f'r{d}_{k}', 'empresa': 'Electro Ficticia', 'relative_path': f'PIDE X/{d}.docx',
                          'location': 'document', 'periodo': '2026',
                          'text': f'En la SET Laguna Azul {tema} {verbo} con 12 MW en el capítulo {k}.'})
    (carpeta / 'fragments.jsonl').write_text(''.join(json.dumps(f, ensure_ascii=False) + '\n' for f in frags),
                                             encoding='utf-8')
    for f in frags:
        cr.registrar_revision(carpeta / 'revision_redaccion.jsonl', f, revisor='revisor de prueba', origen='maestro',
                              aprobado=True, uso='redaccion', fecha='2026-11-21')
    dataset = tmp_path / 'sellado'
    meta = cr.sellar_corpus_redaccion(carpeta, dataset, catalogo=CATALOGO)
    assert meta['por_particion'].get('seleccion') and meta['por_particion'].get('prueba')
    catalogo = tmp_path / 'catalogo.json'
    catalogo.write_text(json.dumps(CATALOGO, ensure_ascii=False), encoding='utf-8')
    return dataset, catalogo, meta


def _adaptador(tmp_path):
    carpeta = tmp_path / 'qlora' / 'epoca_1' / 'final' / 'adaptador'
    carpeta.mkdir(parents=True)
    (carpeta / 'adapter_config.json').write_text('{}', encoding='utf-8')
    return carpeta


def _limpias(meta):
    return {p: ['El capítulo describe la demanda de ‹instalación› con ‹n› ‹n›.'] * meta['por_particion'][p]
            for p in ('seleccion', 'prueba')}


def _medida(meta, *, base=2.0, candidato=1.5, salidas=None):
    perdidas = {p: {'base': {'tokens': 40, 'suma': base * 40, 'por_token': base, 'ejemplos': 3},
                    'candidato': {'tokens': 40, 'suma': candidato * 40, 'por_token': candidato, 'ejemplos': 3}}
                for p in ('seleccion', 'prueba')}
    return {'perdidas': perdidas, 'salidas': _limpias(meta) if salidas is None else salidas,
            'adaptador': 'adaptador', 'checkpoint': {'epoca': 1}, 'base': {'id': 'base/fijada'}, 'device': 'cuda'}


@pytest.fixture
def sin_gpu(monkeypatch):
    from convertersmartgrid.aplicacion import trabajadores_ml
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    turnos = []

    def turno(nombre):
        turnos.append(nombre)
        return contextlib.nullcontext()

    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', turno)
    monkeypatch.setattr(llm_destilacion, 'ficha_base', lambda: {'id': 'base/fijada', 'revision': 'a' * 40})
    return turnos


def _poner_medida(monkeypatch, medir):
    """El doble de la medida en CUDA, sobre la función que examina al candidato."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    assert callable(getattr(llm_destilacion, 'medir_redaccion', None)), 'no hay medida del modelo de redacción'
    monkeypatch.setattr(llm_destilacion, 'medir_redaccion', medir)


def _evaluar(tmp_path, dataset, *extra):
    salida = tmp_path / 'evaluacion'
    rc = _herramienta().main(['evaluar', '--dataset', str(dataset), '--salida', str(salida), *extra])
    return rc, json.loads((salida / 'evaluacion_redaccion.json').read_text(encoding='utf-8'))


def test_aprobado_si_no_empeora_a_la_base_y_las_salidas_estan_limpias(tmp_path, sellado, sin_gpu, monkeypatch):
    """072:RF-53, RF-57 — con menos pérdida que la base y salidas sin nombres ni cifras: aprobado, sin promover."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    dataset, catalogo, meta = sellado
    llamadas = []

    def medir(ds, adaptador, **k):
        llamadas.append((Path(ds), Path(adaptador), tuple(k['partes']), k['generar'], sorted(k['lectores'])))
        return _medida(meta)

    _poner_medida(monkeypatch, medir)
    adaptador = _adaptador(tmp_path)
    rc, informe = _evaluar(tmp_path, dataset, '--adaptador', str(adaptador), '--catalogo', str(catalogo))
    assert rc == 0, informe.get('motivos') or informe.get('error')
    assert llamadas == [(dataset, adaptador, ('seleccion', 'prueba'), True, ['redaccion_pide'])]
    assert sin_gpu == ['evaluacion-redaccion-pide']
    assert informe['status'] == 'APROBADO' and informe['aprobado'] is True and informe['motivos'] == []
    assert informe['promovido'] is False and informe['activado'] is False
    assert informe['dataset_hash'] == meta['dataset_hash'] and informe['redactado_por'] == 'adaptador'
    sel = informe['particiones']['seleccion']
    assert sel['ejemplos'] == meta['por_particion']['seleccion'] and sel['salidas_con_fallo'] == []
    assert sel['perdida']['candidato']['perplejidad'] < sel['perdida']['base']['perplejidad']
    assert informe['interprete']['estado'] == 'no_aplica'
    assert informe['interprete']['activable_como_interprete'] is False


def test_rechazado_si_la_perdida_sube_frente_a_la_base(tmp_path, sellado, sin_gpu, monkeypatch):
    """072:RF-53 — una pérdida por token mayor que la de la base NF4 en la misma partición rechaza al candidato."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    dataset, catalogo, meta = sellado
    _poner_medida(monkeypatch, lambda *a, **k: _medida(meta, base=1.5, candidato=1.6))
    rc, informe = _evaluar(tmp_path, dataset, '--adaptador', str(_adaptador(tmp_path)), '--catalogo', str(catalogo))
    assert rc == 1 and informe['status'] == 'RECHAZADO' and informe['promovido'] is False
    assert any('pérdida por token sube' in m and m.startswith('seleccion') for m in informe['motivos'])
    assert any('pérdida por token sube' in m and m.startswith('prueba') for m in informe['motivos'])


def test_rechazado_si_una_salida_deja_un_nombre_un_codigo_o_una_cifra(tmp_path, sellado, sin_gpu, monkeypatch):
    """072:RF-54 — nombres del catálogo, códigos y cifras que la entrada no trae rechazan; el informe no los copia."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    dataset, catalogo, meta = sellado
    salidas = _limpias(meta)
    salidas['prueba'][0] = 'La sede de Villa Quimera atiende la demanda.'
    salidas['prueba'][1] = 'El alimentador A71 queda en servicio.'
    salidas['seleccion'][0] = 'La demanda llega a 37 MW en el horizonte.'
    _poner_medida(monkeypatch, lambda *a, **k: _medida(meta, salidas=salidas))
    rc, informe = _evaluar(tmp_path, dataset, '--adaptador', str(_adaptador(tmp_path)), '--catalogo', str(catalogo))
    assert rc == 1 and informe['aprobado'] is False
    prueba, sel = informe['particiones']['prueba'], informe['particiones']['seleccion']
    assert [f['motivos'] for f in prueba['salidas_con_fallo']] == [['nombre'], ['código']]
    assert [f['motivos'] for f in sel['salidas_con_fallo']] == [['cifra']]
    todo = json.dumps(informe, ensure_ascii=False)
    for prohibido in ('Villa Quimera', 'A71', '37 MW', 'Laguna Azul', 'Electro Ficticia'):
        assert prohibido not in todo, prohibido


def test_revisar_salida_admite_lo_que_trae_la_entrada():
    """072:RF-54 — una cifra o un código de la entrada no es inventado; uno que no trae, sí; vacía no vale."""
    revisar, = _api('revisar_salida')
    assert revisar('Resume los 12 MW del tramo T12.', 'El tramo T12 atiende 12 MW.') == []
    assert revisar('Resume los 12 MW del tramo T12.', 'El tramo T12 atiende 13 MW.') == ['cifra']
    assert revisar('Redacta un párrafo.', 'La SET Puerto Imaginario queda en servicio.') == ['nombre']
    assert revisar('Redacta un párrafo.', 'La razón social Compañía Inventada S.A. entrega el plan.') == ['nombre']
    assert revisar('Redacta un párrafo.', '  ') == ['vacía']
    assert revisar('Redacta un párrafo.', 'La ‹sede› atiende ‹n› ‹n› en la ‹instalación›.') == []


def test_sin_el_catalogo_del_sellado_no_se_examina(tmp_path, sellado, sin_gpu, monkeypatch):
    """072:RF-54 — revisar con otro catálogo que el del sellado dejaría pasar nombres: no se mide nada."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    dataset, _catalogo, meta = sellado
    _poner_medida(monkeypatch, lambda *a, **k: pytest.fail('no debe medir'))
    rc, informe = _evaluar(tmp_path, dataset, '--adaptador', str(_adaptador(tmp_path)))
    assert rc == 2 and 'catálogo' in informe['error'] and informe['promovido'] is False


def test_con_ollama_redacta_el_modelo_publicado_y_sin_adaptador_no_hay_perdida(tmp_path, sellado, sin_gpu,
                                                                                monkeypatch):
    """072:RF-55, RF-53 — el modelo de Ollama redacta con el prompt sellado; sin adaptador la pérdida no se mide y
    no se aprueba."""
    from convertersmartgrid.aplicacion.asistente import ollama
    dataset, catalogo, meta = sellado
    pedidas = []

    class _Cliente:
        def __init__(self, modelo, **k):
            self.modelo = modelo

        def _pedir(self, ruta, cuerpo=None):
            return {'models': [{'name': self.modelo, 'digest': 'd' * 12}]}

        def redactar(self, sistema, instruccion, *, semilla=0, **k):
            pedidas.append((sistema, instruccion, semilla))
            return 'La demanda de la ‹instalación› se describe en el capítulo.'

        def liberar_gpu(self, solo_actual=False):
            return [self.modelo]

    monkeypatch.setattr(ollama, 'ClienteOllama', _Cliente)
    rc, informe = _evaluar(tmp_path, dataset, '--modelo-ollama', 'csg-alumno:prueba-redaccion', '--catalogo',
                           str(catalogo))
    n = meta['por_particion']['seleccion'] + meta['por_particion']['prueba']
    assert len(pedidas) == n and {p[0] for p in pedidas} == {cr.SISTEMA_REDACCION}
    assert informe['ollama'] == {'modelo': 'csg-alumno:prueba-redaccion', 'digest': 'd' * 12}
    assert informe['redactado_por'] == 'ollama'
    assert rc == 1 and informe['particiones']['prueba']['salidas_con_fallo'] == []
    assert any('pérdida sin medir' in m for m in informe['motivos'])


def test_la_prueba_sellada_del_interprete_solo_cuenta_para_usarlo_como_interprete(tmp_path, sellado, sin_gpu,
                                                                                   monkeypatch):
    """072:RF-56 — con los informes de `llm_destilar.py evaluar --parte prueba`, un intérprete que baja no se activa
    como intérprete; la redacción se decide igual."""
    from convertersmartgrid.aplicacion.asistente import llm_destilacion
    puerta, = _api('puerta_interprete')
    dataset, catalogo, meta = sellado
    en_uso = {'particion': 'prueba', 'modelo': 'csg-alumno:en-uso', 'dataset_hash': 'h', 'prompt_hash': 'p',
              'metricas': {'acierto_tarea': 0.90, 'f1_datos': 0.80}}
    peor = dict(en_uso, modelo='csg-alumno:redaccion', metricas={'acierto_tarea': 0.85, 'f1_datos': 0.80})
    igual = dict(en_uso, modelo='csg-alumno:redaccion')
    assert puerta(igual, en_uso)['estado'] == 'aprobada' and puerta(igual, en_uso)['activable_como_interprete']
    assert puerta(peor, en_uso)['estado'] == 'rechazada' and 'acierto_tarea' in puerta(peor, en_uso)['motivo']
    assert puerta(dict(igual, dataset_hash='otro'), en_uso)['estado'] == 'rechazada'
    assert puerta(dict(igual, particion='seleccion'), en_uso)['estado'] == 'rechazada'
    assert puerta(igual, None)['estado'] == 'rechazada'
    assert puerta(None, None)['estado'] == 'no_aplica'
    _poner_medida(monkeypatch, lambda *a, **k: _medida(meta))
    rutas = []
    for nombre, datos in (('cand.json', peor), ('uso.json', en_uso)):
        rutas.append(tmp_path / nombre)
        rutas[-1].write_text(json.dumps(datos), encoding='utf-8')
    rc, informe = _evaluar(tmp_path, dataset, '--adaptador', str(_adaptador(tmp_path)), '--catalogo', str(catalogo),
                           '--informe-ordenes', str(rutas[0]), '--informe-ordenes-en-uso', str(rutas[1]))
    assert rc == 0 and informe['aprobado'] is True
    assert informe['interprete']['estado'] == 'rechazada'
    assert informe['interprete']['activable_como_interprete'] is False


def test_el_corpus_de_ordenes_se_examina_con_llm_destilar(tmp_path, sin_gpu):
    """072:RF-57 — `evaluar` es del corpus de redacción; uno de órdenes se remite a su propia evaluación."""
    dataset = tmp_path / 'ordenes'
    dataset.mkdir()
    (dataset / 'dataset_manifest.json').write_text(json.dumps({'schema_version': 2}), encoding='utf-8')
    rc, informe = _evaluar(tmp_path, dataset, '--adaptador', str(_adaptador(tmp_path)))
    assert rc == 2 and 'llm_destilar.py evaluar' in informe['error'] and informe['promovido'] is False


def test_medir_rechaza_un_adaptador_de_otro_corpus_antes_de_cargar_la_base(tmp_path, sellado, monkeypatch):
    """072:RF-55 — un adaptador entrenado con otro corpus o prompt no se examina con este: falla sin tocar la GPU."""
    from convertersmartgrid.aplicacion.asistente import llm_checkpoint, llm_destilacion
    assert callable(getattr(llm_destilacion, 'medir_redaccion', None)), 'no hay medida del modelo de redacción'
    dataset, _catalogo, meta = sellado
    monkeypatch.setattr(llm_destilacion, 'ficha_base', lambda: {'id': 'base/fijada', 'revision': 'a' * 40})
    estado = {'base': {'id': 'base/fijada', 'revision': 'a' * 40}, 'epoca': 1,
              'configuracion': {'dataset_hash': 'otro', 'prompt_hash': meta['prompt_hash']}}
    monkeypatch.setattr(llm_checkpoint, 'verificar_checkpoint', lambda carpeta, **k: estado)
    monkeypatch.setattr(llm_destilacion, '_base_local', lambda *a: pytest.fail('no debe cargar la base'))
    lectores = {cr.TIPO_CORPUS: cr.leer_particion_redaccion}
    with pytest.raises(ValueError, match='no se entrenó con este corpus'):
        llm_destilacion.medir_redaccion(dataset, _adaptador(tmp_path), lectores=lectores)
    registros, meta_sel, sistema = llm_destilacion.ejemplos_de_entrenamiento(dataset, lectores=lectores,
                                                                             parte='seleccion')
    assert sistema == cr.SISTEMA_REDACCION and {r['particion'] for r in registros} == {'seleccion'}


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ollama_redacta_con_el_prompt_sellado_y_su_semilla():
    """072:RF-55 — la conversación es la del ajuste: el prompt de sistema sellado y la instrucción, con su semilla."""
    from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
    pedidas = []

    def abrir(peticion, timeout):
        pedidas.append(json.loads(peticion.data))
        return _Respuesta(json.dumps({'message': {'content': ' Un párrafo. '}}).encode())

    cliente = ClienteOllama(modelo='csg-alumno:prueba', abrir=abrir)
    assert callable(getattr(cliente, 'redactar', None)), 'el cliente de Ollama no redacta con un prompt dado'
    assert cliente.redactar('SISTEMA', 'Redacta.', semilla=7) == 'Un párrafo.'
    [cuerpo] = pedidas
    assert cuerpo['messages'] == [{'role': 'system', 'content': 'SISTEMA'}, {'role': 'user', 'content': 'Redacta.'}]
    assert cuerpo['options']['seed'] == 7 and cuerpo['model'] == 'csg-alumno:prueba'
