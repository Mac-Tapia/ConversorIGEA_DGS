"""Spec 026, RF-49: el asistente aprende de lo que el operador hace en la web y de lo que hace el programa.

Cada operación acabada del diario de operaciones (061), anonimizada, con su contexto y su resultado, pasa al corpus de
entrenamiento del planificador (nunca a una prueba sellada), se evalúa con casos que no vio antes de usarse (027:RF-18)
y no se promueve sola (027:RF-21, 061:RF-8). Datos sintéticos: ningún espacio, proyecto ni alimentador real.
"""
from __future__ import annotations

import importlib
import inspect
import json

import pytest

from apoyo import cargar_herramienta

#: Lo que identifica al espacio y al operador en el diario sintético: nada de esto puede llegar al corpus.
ESPACIO = 'espacio_demo_t23'
PRIVADOS = (ESPACIO, 'PROYECTO_DEMO_X', 'ALIM_DEMO_07', 'C:\\datos', 'huella_real_abc', 'corrida_demo_1',
            'error con ruta')


def _de():
    return importlib.import_module('convertersmartgrid.aplicacion.asistente.dataset_entrenamiento')


def _exige(modulo, *nombres):
    faltan = [n for n in nombres if not hasattr(modulo, n)]
    assert not faltan, f'falta en {modulo.__name__}: {faltan}'
    return [getattr(modulo, n) for n in nombres]


def _diario(web, espacio=ESPACIO, operaciones=()):
    from convertersmartgrid.aplicacion.asistente.observacion import RegistroOperaciones

    d = RegistroOperaciones(web / espacio / 'salida' / 'observacion' / 'operaciones.sqlite3', espacio)
    contexto = {'workspace_id': espacio, 'active_run_id': 'corrida_demo_1', 'source_mode': 'txt',
                'source_fingerprint': 'huella_real_abc', 'proyectos_registrados': {'PROYECTO_DEMO_X': 'C:\\datos\\pf'}}
    for i, (clase, estados) in enumerate(operaciones):
        for estado in estados:
            d.anotar({'id': f'job{i}', 'workspace_id': espacio, 'kind': clase, 'lane': 'engine', 'status': estado,
                      'created_at': 100 + i, 'title': f'{clase} ALIM_DEMO_07 en C:\\datos\\red.txt',
                      'error': 'error con ruta C:\\datos\\x' if estado == 'failed' else None,
                      'result': {'proyecto': 'PROYECTO_DEMO_X'} if estado == 'done' else None}, contexto)
    return d


def _acciones(registros):
    return [r for r in registros if r.tipo == 'accion_operador']


def test_026_la_accion_del_operador_llega_al_corpus_anonimizada_con_su_contexto_y_resultado(tmp_path):
    """026:RF-49, 061:RF-1 — cada operación acabada del diario entra en el corpus con lo de antes y cómo acabó; la viva
    no, y nada del espacio, los proyectos, los alimentadores, las rutas ni el error llega al corpus."""
    de = _de()
    assert 'raiz_web' in inspect.signature(de.construir_dataset).parameters, \
        'el corpus no lee el diario de operaciones: la acción del operador no llega al corpus'
    from convertersmartgrid.aplicacion.asistente.observacion import RegistroOperaciones
    assert hasattr(RegistroOperaciones, 'terminadas'), 'el diario no da sus operaciones acabadas'
    web = tmp_path / 'web'
    _diario(web, operaciones=[('convert', ('queued', 'running', 'done')),
                              ('pf_calibrar', ('queued', 'running', 'failed')),
                              ('asistente_indice', ('queued', 'done')),
                              ('pf_calibrar', ('queued', 'running'))])
    hecho = de.construir_dataset(tmp_path / '_asistente', tmp_path / 'gemelo', raiz_web=web)
    acciones = sorted(_acciones(hecho.registros), key=lambda r: r.provenance['creado'])
    assert [r.resultado['accion'] for r in acciones] == ['convert', 'pf_calibrar', 'asistente_indice']
    assert [r.resultado['resultado'] for r in acciones] == ['hecho', 'fallido', 'hecho']
    assert [r.resultado['anterior'] for r in acciones] == ['nada', 'convert hecho', 'pf_calibrar fallido']
    assert {r.resultado['fuente'] for r in acciones} == {'txt'}
    # Lo del operador es humano observado; lo que encola el propio asistente, del programa.
    assert [(r.quality, r.provenance['procedencia']) for r in acciones] == [
        ('gold_human', 'operador_web'), ('gold_human', 'operador_web'), ('silver_deterministic', 'programa')]
    assert all(r.provenance['origen'] == 'diario_operaciones_061' and r.verification for r in acciones)
    assert all(r.provenance['proyectos_registrados'] == 1 for r in acciones)
    assert len({r.provenance['espacio'] for r in acciones}) == 1
    texto = json.dumps([r.as_dict() for r in acciones], ensure_ascii=False)
    for privado in PRIVADOS:
        assert privado not in texto and privado.replace('\\', '\\\\') not in texto, privado
    assert not any(de.auditar_registro(r) for r in acciones)
    # Entran en las particiones, no en cuarentena, y el intérprete de órdenes no las toma por órdenes.
    from convertersmartgrid.aplicacion.asistente.tareas import TAREAS
    partes = de.particionar_dataset(hecho.registros)
    assert sum(len(_acciones(v)) for v in partes.values()) == 3
    assert all(r.tarea not in TAREAS for r in acciones)


def test_026_lo_aprendido_nunca_entra_en_una_prueba_sellada(tmp_path):
    """026:RF-49, 026:RF-44 — lo aprendido no tiene frases de las selladas, la cuenta lo delata si las tuviera, y una
    acción con el texto de una sellada va a cuarentena: entrena, nunca examina."""
    de = _de()
    from convertersmartgrid.aplicacion.asistente import fuga_evaluacion as fe
    _exige(fe, 'frases_selladas', 'fugas_de_lo_aprendido')
    (normalizar,) = _exige(de, 'normalizar_accion_operador')
    from convertersmartgrid.aplicacion.asistente import prueba_sellada_026 as s
    from convertersmartgrid.aplicacion.evaluacion_modelos import texto_canonico

    web = tmp_path / 'web'
    _diario(web, operaciones=[('convert', ('done',)), ('pf_calibrar', ('done',))])
    hecho = de.construir_dataset(tmp_path / '_asistente', tmp_path / 'gemelo', raiz_web=web)
    textos = [r.texto for r in _acciones(hecho.registros)]
    assert len(textos) == 2
    cero = fe.fugas_de_lo_aprendido(textos)
    assert set(cero) == {s.CONJUNTO, s.CONJUNTO_CONTROL, 'sellada_107_112'} and not any(cero.values())
    frase = next(iter(s.FRASES.values()))[0]
    assert fe.fugas_de_lo_aprendido([*textos, frase])[s.CONJUNTO] == 1
    fila = {'id': 'j', 'kind': 'convert', 'status': 'done', 'contexto': {'source_mode': 'txt'}}
    libre = normalizar(fila, espacio='e')
    assert libre.quality == 'gold_human'
    apartada = normalizar(fila, espacio='e', selladas=frozenset({texto_canonico(libre.texto)}))
    assert apartada.quality == 'quarantine' and 'sellada' in apartada.motivo
    assert not _acciones(de.particionar_dataset([apartada])['train'])


def _casos(normalizar, n, *, espacio, siguiente='pf_calibrar', resultado='done', desde=0):
    """``n`` parejas «convertir y luego ``siguiente``» de un espacio, cada operación con su id."""
    filas = []
    for i in range(desde, desde + n):
        filas.append(normalizar({'id': f'{espacio}-c{i}', 'kind': 'convert', 'status': 'done',
                                 'contexto': {'source_mode': 'txt'}}, espacio=espacio))
        filas.append(normalizar({'id': f'{espacio}-s{i}', 'kind': siguiente, 'status': resultado,
                                 'contexto': {'source_mode': 'txt'}}, espacio=espacio, anterior=('convert', 'hecho')))
    return filas


def test_026_lo_aprendido_se_evalua_antes_de_usarse_y_no_se_promueve_solo():
    """026:RF-49, 027:RF-18, 027:RF-21, 061:RF-8 — el candidato sale medido con lo que no vio y sin promover; sin
    promover no propone nada, lo promueve el operador solo si pasó sus puertas, y tocado después de medirlo no vale."""
    de = _de()
    normalizar, evaluar, promover, propuesta = _exige(
        de, 'normalizar_accion_operador', 'evaluar_acciones_aprendidas', 'promover_acciones_aprendidas',
        'propuesta_aprendida')
    aprende = _casos(normalizar, 8, espacio='a')
    examina = _casos(normalizar, 6, espacio='b')
    candidato = evaluar(aprende, examina)
    assert candidato['promovido'] is False and candidato['puertas']['superadas'] is True
    assert candidato['evaluacion']['casos'] == 12 and candidato['evaluacion']['acierto'] >= de.ACIERTO_MINIMO_ACCIONES
    assert ['txt', 'convert hecho', 'pf_calibrar'] in candidato['tabla']
    assert propuesta(candidato, fuente='txt', anterior='convert hecho') is None, 'propone sin que nadie lo promueva'
    with pytest.raises(ValueError, match='operador'):
        promover(candidato, confirmado_por='')
    promovido = promover(candidato, confirmado_por='operador')
    p = propuesta(promovido, fuente='txt', anterior='convert hecho')
    assert p['accion'] == 'pf_calibrar' and p['confirma_el_operador'] is True and '12 casos' in p['motivo']
    assert propuesta(promovido, fuente='mdb', anterior='convert hecho') is None
    # Tocado después de medirlo, no se usa ni se promueve.
    tocado = {**promovido, 'tabla': [['txt', 'convert hecho', 'borrar_espacio']]}
    assert propuesta(tocado, fuente='txt', anterior='convert hecho') is None
    with pytest.raises(ValueError, match='evaluarse'):
        promover(tocado, confirmado_por='operador')
    # Con pocos casos que no vio, las puertas no pasan y el operador no puede promoverlo.
    pocos = evaluar(aprende, _casos(normalizar, 1, espacio='c'))
    assert not pocos['puertas']['superadas'] and 'faltan casos' in pocos['puertas']['fallos'][0]
    with pytest.raises(ValueError, match='puertas'):
        promover(pocos, confirmado_por='operador')
    # Lo que evalúa no puede ser lo que aprende.
    with pytest.raises(ValueError, match='comparte'):
        evaluar(aprende, aprende[:4])


def test_026_un_paso_que_siempre_falla_no_se_aprende_para_proponerlo():
    """026:RF-49 — el resultado cuenta: lo que el operador lanzó y falló resta, y no se propone."""
    de = _de()
    normalizar, evaluar = _exige(de, 'normalizar_accion_operador', 'evaluar_acciones_aprendidas')
    aprende = (_casos(normalizar, 4, espacio='a', siguiente='pf_obras', resultado='failed')
               + _casos(normalizar, 1, espacio='a', siguiente='pf_obras', desde=10))
    candidato = evaluar(aprende, _casos(normalizar, 6, espacio='b', siguiente='pf_obras'))
    assert not any(fila[2] == 'pf_obras' for fila in candidato['tabla'])
    # Acierta el «convertir» del principio, nunca el paso que falla: no llega a la puerta.
    assert candidato['evaluacion']['aciertos'] == 6 and not candidato['puertas']['superadas']


def test_026_el_dataset_de_la_orden_trae_lo_aprendido_medido_y_sin_promover(tmp_path):
    """026:RF-49, 043:RF-14 — la orden que construye el dataset lee los diarios de los espacios y dice cómo salió lo
    aprendido, sin promoverlo."""
    guion = cargar_herramienta('construir_dataset_entrenamiento.py', 'construir_dataset_t23')
    web = tmp_path / 'web'
    asistente = web / '_asistente'
    asistente.mkdir(parents=True)
    _diario(web, operaciones=[('convert', ('done',)), ('pf_calibrar', ('done',))])
    informe = guion.construir(web, asistente, tmp_path / 'gemelo', tmp_path / 'dataset_nuevo')
    assert 'acciones_aprendidas' in informe, 'la orden del dataset no mide lo aprendido del operador'
    aprendidas = informe['acciones_aprendidas']
    assert aprendidas['promovido'] is False and aprendidas['puertas']['superadas'] is False
    filas = [json.loads(l) for parte in ('train', 'validation', 'test')
             for l in (tmp_path / 'dataset_nuevo' / f'{parte}.jsonl').read_text(encoding='utf-8').splitlines() if l]
    assert sum(f['tipo'] == 'accion_operador' for f in filas) == 2


# --------------------------------------------------------------------------- lo aprendido llega al operador (web)
def _candidato(de, *, pasa=True):
    """Un candidato medido y sin promover: con puertas superadas (12 casos que no vio) o sin ellas (2)."""
    normalizar = de.normalizar_accion_operador
    return de.evaluar_acciones_aprendidas(_casos(normalizar, 8, espacio='a'),
                                          _casos(normalizar, 6 if pasa else 1, espacio='b'))


def _web(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    return TestClient(create_app(tmp_path / 'web'))


def _promover(c, huella=None):
    previa = c.post('/api/asistente/aprendido/previa')
    assert previa.status_code == 200, previa.text
    cuerpo = previa.json()
    return c.post('/api/asistente/aprendido/promover',
                  json={'huella': huella or cuerpo['candidato']['huella'], 'confirmacion': cuerpo['confirmacion']})


def test_026_rf49_el_dataset_deja_el_candidato_entero_en_el_almacen_sin_promover(tmp_path):
    """026:RF-49 — la orden del dataset guarda el candidato entero (tabla, evaluación, puertas y huella) en el almacén del
    asistente, sin promover, y nunca encima de uno promovido."""
    de = _de()
    (leer,) = _exige(de, 'leer_acciones_aprendidas')
    guion = cargar_herramienta('construir_dataset_entrenamiento.py', 'construir_dataset_rf49')
    web = tmp_path / 'web'
    asistente = web / '_asistente'
    asistente.mkdir(parents=True)
    _diario(web, operaciones=[('convert', ('done',)), ('pf_calibrar', ('done',))])
    informe = guion.construir(web, asistente, tmp_path / 'gemelo', tmp_path / 'dataset_1')
    guardado = leer(asistente)['candidato']
    assert guardado, 'el candidato no queda en el almacén del asistente: lo aprendido nunca llega al operador'
    assert {'tabla', 'evaluacion', 'puertas', 'huella'} <= set(guardado) and guardado['promovido'] is False
    assert guardado['huella'] == informe['acciones_aprendidas']['huella'] and de.acciones_intactas(guardado)
    assert leer(asistente)['en_uso'] is None, 'construir el dataset no pone nada en uso'
    # Uno promovido en el sitio del candidato no se pisa: el informe dice por qué.
    ruta = asistente / de.CARPETA_ACCIONES / 'candidato.json'
    ruta.write_text(json.dumps({**guardado, 'promovido': True}), encoding='utf-8')
    antes = ruta.read_bytes()
    otro = guion.construir(web, asistente, tmp_path / 'gemelo', tmp_path / 'dataset_2')
    assert otro['acciones_aprendidas']['guardado'] is None and 'promovid' in otro['acciones_aprendidas']['motivo']
    assert ruta.read_bytes() == antes


def test_026_rf49_promover_sin_pasar_las_puertas_falla_con_su_motivo(tmp_path, monkeypatch):
    """026:RF-49, 027:RF-21 — la web enseña el candidato con sus puertas; si no las pasó, no se puede promover y la
    promoción, aun confirmada, falla diciendo qué puerta no pasó."""
    de = _de()
    (guardar,) = _exige(de, 'guardar_candidato_acciones')
    with _web(tmp_path, monkeypatch) as c:
        vacio = c.get('/api/asistente/aprendido')
        assert vacio.status_code == 200, 'falta GET /api/asistente/aprendido'
        assert vacio.json()['candidato'] is None and vacio.json()['se_puede_promover'] is False
        guardar(tmp_path / 'asistente', _candidato(de, pasa=False))
        estado = c.get('/api/asistente/aprendido').json()
        assert estado['candidato']['puertas']['superadas'] is False and estado['se_puede_promover'] is False
        assert 'faltan casos' in estado['motivo']
        r = _promover(c)
        assert r.status_code == 409 and 'puertas' in r.json()['detail'] and 'faltan casos' in r.json()['detail']
        assert c.get('/api/asistente/aprendido').json()['en_uso'] is None


def test_026_rf49_con_puertas_y_confirmacion_queda_promovido_y_sin_ella_no(tmp_path, monkeypatch):
    """026:RF-49, 061:RF-8 — sin la confirmación de la previa (o con una ya usada, o con un programa) no se promueve;
    con puertas y confirmación queda promovido aparte, en uso, y el candidato sigue sin promover."""
    de = _de()
    (guardar, leer) = _exige(de, 'guardar_candidato_acciones', 'leer_acciones_aprendidas')
    candidato = _candidato(de)
    with _web(tmp_path, monkeypatch) as c:
        guardar(tmp_path / 'asistente', candidato)
        estado = c.get('/api/asistente/aprendido').json()
        assert estado['se_puede_promover'] is True and estado['motivo'] == ''
        sin = c.post('/api/asistente/aprendido/promover',
                     json={'huella': candidato['huella'], 'confirmacion': 'inventada'})
        assert sin.status_code == 409 and 'confirmación' in sin.json()['detail']
        programa = c.post('/api/asistente/aprendido/promover', headers={'Authorization': 'Bearer x'},
                          json={'huella': candidato['huella'], 'confirmacion': 'inventada'})
        assert programa.status_code == 403
        assert leer(tmp_path / 'asistente')['en_uso'] is None, 'se promovió sin la confirmación del operador'
        previa = c.post('/api/asistente/aprendido/previa').json()
        ok = c.post('/api/asistente/aprendido/promover',
                    json={'huella': candidato['huella'], 'confirmacion': previa['confirmacion']})
        assert ok.status_code == 200, ok.text
        assert ok.json()['en_uso']['promovido'] is True and ok.json()['en_uso']['intacto'] is True
        assert ok.json()['se_puede_promover'] is False and ok.json()['motivo'] == 'Ya está en uso.'
        otra = c.post('/api/asistente/aprendido/promover',
                      json={'huella': candidato['huella'], 'confirmacion': previa['confirmacion']})
        assert otra.status_code == 409, 'la confirmación vale una sola vez'
    guardado = leer(tmp_path / 'asistente')
    assert guardado['en_uso']['promovido_por'] and guardado['candidato']['promovido'] is False


def test_026_rf49_un_candidato_tocado_tras_medirse_no_se_promueve(tmp_path, monkeypatch):
    """026:RF-49 — si alguien toca la tabla después de medirla, la web lo enseña como tocado y la promoción, aun con la
    confirmación de la previa, falla con su motivo."""
    de = _de()
    (guardar,) = _exige(de, 'guardar_candidato_acciones')
    candidato = _candidato(de)
    with _web(tmp_path, monkeypatch) as c:
        ruta = guardar(tmp_path / 'asistente', candidato)
        previa = c.post('/api/asistente/aprendido/previa').json()
        ruta.write_text(json.dumps({**candidato, 'tabla': [['txt', 'convert hecho', 'borrar_espacio']]}),
                        encoding='utf-8')
        assert c.get('/api/asistente/aprendido').json()['candidato']['intacto'] is False
        r = c.post('/api/asistente/aprendido/promover',
                   json={'huella': candidato['huella'], 'confirmacion': previa['confirmacion']})
        assert r.status_code == 409 and 'evaluarse' in r.json()['detail']
        assert c.get('/api/asistente/aprendido').json()['en_uso'] is None


def _espacio_txt_con_diario(c, operaciones):
    from convertersmartgrid.aplicacion.asistente.observacion import RegistroOperaciones

    wid = c.post('/api/workspaces').json()['id']
    ws = c.app.state.store.get(wid)
    ws.loaded_source_mode = 'txt'
    diario = RegistroOperaciones(ws.out_dir / 'observacion' / 'operaciones.sqlite3', wid)
    for i, (clase, estado) in enumerate(operaciones):
        diario.anotar({'id': f'op{i}', 'workspace_id': wid, 'kind': clase, 'lane': 'engine', 'status': estado,
                       'created_at': 100 + i, 'title': clase}, {'workspace_id': wid, 'source_mode': 'txt'})
    return wid


def test_026_rf49_la_lista_del_proyecto_trae_lo_aprendido_solo_promovido_e_intacto(tmp_path, monkeypatch):
    """026:RF-49 — «para que la próxima vez la proponga él»: la lista del proyecto entero trae lo aprendido con su
    motivo solo cuando está promovido e intacto y el contexto del espacio (fuente y lo último acabado en su diario) es
    uno de los aprendidos; sin promover, en otro contexto o tocado no trae nada, y nunca lanza nada."""
    de = _de()
    (guardar,) = _exige(de, 'guardar_candidato_acciones')
    candidato = _candidato(de)
    cuerpo = {'sistema': 'Sistema sintético', 'periodo': '2026-07', 'reiniciar': True}
    with _web(tmp_path, monkeypatch) as c:
        wid = _espacio_txt_con_diario(c, [('convert', 'done')])

        def lista(espacio=wid):
            r = c.post(f'/api/workspaces/{espacio}/agente/proyecto/lista', json=cuerpo)
            assert r.status_code == 200, r.text
            return r.json()

        guardar(tmp_path / 'asistente', candidato)
        assert 'aprendido' not in lista(), 'propone lo aprendido sin que el operador lo promueva'
        assert _promover(c).status_code == 200
        aprendido = lista().get('aprendido')
        assert aprendido, 'lo promovido no llega a la lista del proyecto: el asistente no lo propone'
        assert aprendido['accion'] == 'pf_calibrar' and aprendido['confirma_el_operador'] is True
        assert '12 casos' in aprendido['motivo']
        assert not c.app.state.jobs.list(wid), 'proponer lo aprendido no lanza ningún trabajo'
        # Un espacio sin nada acabado propone lo que se aprendió para empezar; con otra fuente, nada aprendido.
        otro = c.post('/api/workspaces').json()['id']
        c.app.state.store.get(otro).loaded_source_mode = 'txt'
        assert lista(otro)['aprendido']['accion'] == 'convert'
        c.app.state.store.get(otro).loaded_source_mode = 'mdb'
        assert 'aprendido' not in lista(otro)
        # Tocado lo que está en uso, deja de proponer.
        en_uso = tmp_path / 'asistente' / de.CARPETA_ACCIONES / 'en_uso.json'
        tocado = json.loads(en_uso.read_text(encoding='utf-8'))
        tocado['tabla'] = [['txt', 'convert hecho', 'borrar_espacio']]
        en_uso.write_text(json.dumps(tocado), encoding='utf-8')
        assert 'aprendido' not in lista()
