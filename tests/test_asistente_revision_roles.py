"""047:RF-5 / RF-6 / RF-7 — revisión local, con dictámenes y sin autoridad nativa."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.aplicacion.asistente.revision_roles import revisar_propuesta


def paquete(tmp_path):
    fuente = tmp_path / 'fuente.txt'
    fuente.write_text('evidencia verificable', encoding='utf-8')
    import hashlib
    contexto = SimpleNamespace(project='P1', source_fingerprint='abc')
    evidencia = {'e1': {'archivo': str(fuente), 'sha256': hashlib.sha256(fuente.read_bytes()).hexdigest(),
                        'proyecto': 'P1', 'fuente': 'abc'}}
    return contexto, evidencia


def revisor(rol, propuesta, evidencia, contexto, ronda):
    return {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [], 'contradicciones': []}


def test_critico_sin_evidencia_no_aprueba(tmp_path):
    """047:RF-5 / 047:RF-6 — coincidencia de cuatro roles sin fuente no aprueba."""
    contexto, _ = paquete(tmp_path)
    r = revisar_propuesta({}, {}, contexto=contexto, revisor=revisor)
    assert not r['aprobada'] and not r['autoriza_ejecucion']
    assert {d['rol'] for d in r['dictamenes']} == {'fuentes', 'fisica', 'coste', 'riesgo'}
    assert all(d['decision'] == 'bloqueada' for d in r['dictamenes'])


def test_revisores_con_evidencia_y_restricciones_verificadas(tmp_path):
    """047:RF-5 / 047:RF-6 — dictámenes separados y huella compartida."""
    contexto, evidencia = paquete(tmp_path)
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia,
                          contexto=contexto, revisor=revisor)
    assert r['aprobada'] and not r['autoriza_ejecucion']
    assert len({d['entrada_sha256'] for d in r['dictamenes']}) == 1
    assert all(d['evidencia_ids'] == ['e1'] for d in r['dictamenes'])


def test_desacuerdo_fisico_bloquea(tmp_path):
    """047:RF-6 — consenso textual nunca sustituye la restricción determinista."""
    contexto, evidencia = paquete(tmp_path)
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': False}}, evidencia,
                          contexto=contexto, revisor=revisor)
    assert not r['aprobada'] and 'restricciones' in r['motivo']


def test_dos_rondas_y_cancelacion(tmp_path):
    """047:RF-7 — tope real, cancelación entre intervenciones y sin ruta de escritura."""
    contexto, evidencia = paquete(tmp_path)
    llamadas = []
    def indeciso(*args):
        llamadas.append(args[0])
        return {'decision': 'revisar', 'evidencia_ids': ['e1'], 'incertidumbres': ['falta contraste'],
                'contradicciones': []}
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=indeciso, max_rondas=2)
    assert len(llamadas) == 8 and r['rondas'] == 2 and not r['aprobada']
    llamadas.clear()
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=indeciso,
                          cancelado=lambda: len(llamadas) >= 1)
    assert len(llamadas) == 1 and r['cancelada'] and not r['aprobada']
    with pytest.raises(ValueError, match='rondas'):
        revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=3)


def test_evidencia_alterada_no_aprueba(tmp_path):
    """047:RF-6 — el identificador nominal no basta, se relee el archivo y su hash."""
    contexto, evidencia = paquete(tmp_path)
    from pathlib import Path
    Path(evidencia['e1']['archivo']).write_text('alterada', encoding='utf-8')
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=revisor)
    assert not r['aprobada']


def test_evidencia_sin_proyecto_ni_fuente_no_acredita(tmp_path):
    """047:RF-6 — None coincidía con un registro que no nombra proyecto: sin contexto no hay evidencia válida."""
    contexto, evidencia = paquete(tmp_path)
    contexto = SimpleNamespace(project=None, source_fingerprint=None)
    evidencia['e1'].update(proyecto=None, fuente=None)
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia, contexto=contexto, revisor=revisor)
    assert not r['aprobada'] and all(d['decision'] == 'bloqueada' for d in r['dictamenes'])


def test_la_segunda_ronda_ve_los_dictamenes_de_la_primera(tmp_path):
    """047:RF-7 — con la misma entrada y temperatura 0, repetiría cada dictamen; la huella no cambia."""
    contexto, evidencia = paquete(tmp_path)
    vistos = {1: [], 2: []}
    def rol(rol, propuesta, evidencia, contexto, ronda):
        vistos[ronda].append(propuesta.get('dictamenes_ronda_anterior'))
        return {'decision': 'revisar', 'evidencia_ids': ['e1'], 'incertidumbres': [f'duda de {rol}'], 'contradicciones': []}
    r = revisar_propuesta({}, evidencia, contexto=contexto, revisor=rol)
    assert vistos[1] == [None] * 4
    assert all({d['rol'] for d in v} == {'fuentes', 'fisica', 'coste', 'riesgo'} for v in vistos[2])
    assert vistos[2][0][0]['incertidumbres'] == ['duda de fuentes']
    assert len({d['entrada_sha256'] for d in r['dictamenes']}) == 1
    assert 'dictamenes_ronda_anterior' not in r['propuesta_final']


def test_propuesta_final_y_dictamen_trazable(tmp_path):
    """047:RF-5 — queda lo revisado y, por rol: evidencia, incertidumbres, contradicciones, ronda y huella."""
    contexto, evidencia = paquete(tmp_path)
    r = revisar_propuesta({'accion': 'x', 'restricciones_deterministas': {'fisica': True}}, evidencia,
                          contexto=contexto, revisor=revisor)
    assert r['propuesta_final']['accion'] == 'x'
    assert all({'rol', 'ronda', 'evidencia_ids', 'incertidumbres', 'contradicciones', 'entrada_sha256'} <= set(d)
               for d in r['dictamenes'])


def _cliente(respuesta, peticiones):
    import io
    import json
    from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
    def abrir(peticion, timeout):
        peticiones.append((peticion.full_url, json.loads(peticion.data)))
        return io.BytesIO(json.dumps(respuesta).encode())
    return ClienteOllama(abrir=abrir)


def _dictamen_llm(contenido):
    import json
    return {'message': {'content': json.dumps(contenido)}, 'prompt_eval_count': 100, 'eval_count': 10}


FAVORABLE = {'decision': 'favorable', 'evidencia_ids': ['e1'], 'incertidumbres': [], 'contradicciones': []}


def test_roles_no_escriben(tmp_path, monkeypatch):
    """047:RF-7 / 047:RF-10 — sin herramientas, sin cliente de escritura ni acceso a DIgSILENT: solo el chat local."""
    import ast
    from convertersmartgrid.aplicacion.asistente import almacen, revision_roles
    from convertersmartgrid.aplicacion.asistente.revision_roles import revisor_ollama
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))
    importados = set()
    for nodo in ast.walk(ast.parse(Path(revision_roles.__file__).read_text(encoding='utf-8'))):
        if isinstance(nodo, ast.Import):
            importados |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom):
            importados |= {nodo.module or ''} | {a.name for a in nodo.names}
    assert not importados & {'ejecutor', 'requests', 'urllib', 'powerfactory', 'pf_arnes', 'subprocess', 'services', 'httpx'}
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia, contexto=contexto,
                      revisor=revisor_ollama(_cliente(_dictamen_llm(FAVORABLE), peticiones)))
    assert len(peticiones) == 4 and all(url.endswith('/api/chat') and 'tools' not in c for url, c in peticiones)
    assert not almacen.leer('equipo_acciones')


def test_cada_rol_tiene_su_encargo_y_el_esquema_es_el_del_validador(tmp_path):
    """047:RF-5 — cada rol recibe lo suyo, y lo que se pide a Ollama es lo que se valida."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import esquema_dictamen, revisor_ollama
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    revisar_propuesta({}, evidencia, contexto=contexto, revisor=revisor_ollama(_cliente(_dictamen_llm(FAVORABLE), peticiones)))
    sistemas = [c['messages'][0]['content'] for _u, c in peticiones]
    assert len(set(sistemas)) == 4
    assert all(c['format'] == esquema_dictamen() for _u, c in peticiones)
    assert set(esquema_dictamen()['required']) == set(FAVORABLE)
    assert esquema_dictamen()['properties']['decision']['enum'] == ['favorable', 'bloqueada', 'revisar']


def test_presupuesto_de_revision_en_la_configuracion(tmp_path, monkeypatch):
    """047:RF-7 — el tiempo y los tokens salen de la configuración; un valor fuera de rango se dice, no se ignora."""
    from convertersmartgrid.aplicacion.asistente import almacen
    from convertersmartgrid.aplicacion.asistente.revision_roles import config_revision, revisor_ollama
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))
    # 047:RF-47: 1024 desde MEJ24; el tope de 512 podía cortar la respuesta del equipo.
    assert config_revision() == {'presupuesto_s': 60.0, 'num_predict': 1024}
    almacen.guardar_json('ollama', {'revision_presupuesto_s': 30, 'revision_tokens': 128})
    assert config_revision() == {'presupuesto_s': 30.0, 'num_predict': 128}
    almacen.guardar_json('ollama', {'revision_tokens': 0})
    with pytest.raises(ValueError, match='revision_tokens'):
        config_revision()
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    tokens = []
    revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1,
                      revisor=revisor_ollama(_cliente(_dictamen_llm(FAVORABLE), peticiones), num_predict=128,
                                             medir=lambda e, s: tokens.append((e, s))))
    assert {c['options']['num_predict'] for _u, c in peticiones} == {128}
    assert tokens == [(100, 10)] * 4


def _herramienta_comparar():
    import importlib.util
    ruta = Path(__file__).resolve().parents[1] / 'tools/asistente_comparar_revision.py'
    spec = importlib.util.spec_from_file_location('comparar_revision_047', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_comparacion_rol_unico_y_equipo_con_los_mismos_casos(tmp_path):
    """047:RF-5 — mismos casos, coste y errores; el revisor es de prueba: no acredita la calidad de ningún LLM."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)
    assert {c['defecto'] for c in casos} == herramienta.DEFECTOS
    por_propuesta = {c['propuesta']['accion']: c['defecto'] for c in casos}
    def fabrica(medir):
        def revisar(rol, propuesta, evidencia, contexto, ronda):
            medir(100, 10)
            defecto = por_propuesta[propuesta['accion']]
            # El único se deja el defecto de riesgo: se ve en su columna, y en la del equipo no.
            ve = defecto == rol or (rol == 'unico' and defecto not in (None, 'riesgo'))
            return {'decision': 'bloqueada' if ve else 'favorable', 'evidencia_ids': sorted(evidencia),
                    'incertidumbres': [], 'contradicciones': ['defecto'] if ve else []}
        return revisar
    r = comparar_revision(casos, fabrica)
    n, defectos = len(casos), sum(c['defecto'] is not None for c in casos)
    assert r['equipo']['detectados'] == defectos and r['equipo']['perdidos'] == 0
    assert r['rol_unico']['perdidos'] == sum(c['defecto'] == 'riesgo' for c in casos)
    assert r['equipo']['falsas_alarmas'] == 0 and r['rol_unico']['falsas_alarmas'] == 0
    assert r['equipo']['intervenciones'] == 4 * n and r['rol_unico']['intervenciones'] == n
    assert r['equipo']['tokens_entrada'] == 400 * n and r['rol_unico']['tokens_salida'] == 10 * n
    assert r['autoriza_ejecucion'] is False and r['aceptacion_cientifica'] is False


def test_un_revisor_que_no_responde_no_cuenta_como_deteccion(tmp_path):
    """047:RF-6 — nunca un OK falso: el fallo del LLM bloquea, pero se cuenta aparte y no como defecto hallado."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)
    def fabrica(medir):
        def revisar(*_a):
            raise TimeoutError('sin respuesta')
        return revisar
    r = comparar_revision(casos, fabrica, rondas=1)
    for modo in ('rol_unico', 'equipo'):
        assert r[modo]['sin_respuesta'] == len(casos) and r[modo]['detectados'] == 0 and r[modo]['falsas_alarmas'] == 0


def test_conjunto_de_la_comparacion_declarado_antes_de_medir(capsys):
    """047:RF-5 — la huella se fijó antes de medir, sin Ollama, y una edición del conjunto se rechaza."""
    import json
    herramienta = _herramienta_comparar()
    assert herramienta.main(['--solo-conjunto']) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida['casos'] > salida['con_defecto'] > 0 and salida['conjunto_sha256'] == herramienta.HUELLA
    herramienta.HUELLA = '0' * 64
    with pytest.raises(ValueError, match='cambió'):
        herramienta.leer_casos()


#: La forma de lo que devuelve /api/chat de Ollama 0.40 con un modelo que razona y sin ``think``, con las cifras de la
#: medición de qwen3:8b (unos 505 de 512 tokens). El informe no guardó el texto: la forma es de la API, no una captura.
RAZONA = {'model': 'qwen3:8b', 'created_at': '2026-11-03T12:00:00Z', 'done': True, 'done_reason': 'length',
          'message': {'role': 'assistant', 'content': '', 'thinking': 'Okay, the user wants me to review ' * 80},
          'prompt_eval_count': 740, 'eval_count': 512}
CORTADA = {**RAZONA, 'message': {'role': 'assistant', 'content': '{"decision": "bloqueada", "evidencia_ids": ["e1"], "incert'}}


@pytest.mark.parametrize('respuesta,frases', [
    (RAZONA, ['vacía', 'razonar', 'tope (512 tokens)']),
    (CORTADA, ['JSON no válido', 'tope (512 tokens)', 'inicio:', 'evidencia_ids']),
    ({**RAZONA, 'done_reason': 'stop', 'message': {'content': 'no es json'}}, ['JSON no válido', "'stop'", 'no es json']),
])
def test_respuesta_no_reconocida_guarda_el_motivo_en_el_informe(tmp_path, respuesta, frases):
    """047:RF-6 — la medición dijo «sin respuesta» en 23 de 24 sin dejar ver por qué; el informe guarda la causa."""
    import json
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision, revisor_ollama
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)[:2]
    r = comparar_revision(casos, lambda medir: revisor_ollama(_cliente(respuesta, []), medir=medir), rondas=1)
    fila = r['equipo']['por_caso'][0]
    assert fila['sin_respuesta'] and not fila['aprobada'] and len(fila['motivos']) == 4
    assert fila['motivos'][0].startswith('fuentes: ') and all(f in fila['motivos'][0] for f in frases)
    assert r['equipo']['detectados'] == 0 and r['equipo']['tokens_salida'] == 512 * 8
    assert sum(r['equipo']['motivos_sin_respuesta'].values()) == 8 and len(r['equipo']['motivos_sin_respuesta']) == 1
    assert 'inicio:' not in next(iter(r['equipo']['motivos_sin_respuesta']))
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize('pensar', [None, True, False])
def test_la_revision_pide_sin_razonar_sea_cual_sea_el_cliente(tmp_path, pensar):
    """047:RF-5 — el razonamiento gastaba el tope antes de escribir el dictamen; la configuración no lo reabre."""
    from convertersmartgrid.aplicacion.asistente.ollama import ClienteOllama
    from convertersmartgrid.aplicacion.asistente.revision_roles import revisor_ollama
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    cliente = _cliente(_dictamen_llm(FAVORABLE), peticiones)
    cliente.pensar = pensar
    assert isinstance(cliente, ClienteOllama)
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia, contexto=contexto,
                          revisor=revisor_ollama(cliente))
    assert r['aprobada'] and all(c['think'] is False for _u, c in peticiones)


def test_el_presupuesto_agotado_tambien_se_dice(tmp_path):
    """047:RF-6 — una revisión que se queda sin tiempo no cuenta como hallazgo, y el informe lo dice."""
    from convertersmartgrid.aplicacion.asistente import revision_roles
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)[:1]
    real = revision_roles.revisar_propuesta
    def agotada(*a, **k):
        return {**real(*a, **k), 'presupuesto_agotado': True, 'aprobada': False}
    revision_roles.revisar_propuesta = agotada
    try:
        def fabrica(medir):
            return lambda rol, p, ev, ctx, ronda: {**FAVORABLE, 'evidencia_ids': sorted(ev)}
        fila = revision_roles.comparar_revision(casos, fabrica, rondas=1)['equipo']['por_caso'][0]
    finally:
        revision_roles.revisar_propuesta = real
    assert fila['sin_respuesta'] and fila['motivos'] == ['presupuesto de tiempo agotado']


def test_dictamen_que_no_aprueba_nombra_su_hallazgo(tmp_path):
    """047:RF-38 — qwen3:8b bloqueó 12 de 12 sin que el contrato le pidiera decir qué estaba mal (047 T8)."""
    contexto, evidencia = paquete(tmp_path)
    for decision in ('bloqueada', 'revisar'):
        vacio = {'decision': decision, 'evidencia_ids': ['e1'], 'incertidumbres': [], 'contradicciones': []}
        r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia, contexto=contexto,
                              max_rondas=1, revisor=lambda *_a, d=vacio: dict(d))
        assert not r['aprobada']
        assert all(d['fallo_revisor'] and 'sin hallazgo' in d['incertidumbres'][0] for d in r['dictamenes'])
    con_hallazgo = {'decision': 'bloqueada', 'evidencia_ids': ['e1'], 'incertidumbres': [],
                    'contradicciones': ['e1 da 0,95 p.u. y la propuesta 1,01']}
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia, contexto=contexto,
                          max_rondas=1, revisor=lambda *_a: dict(con_hallazgo))
    assert not r['aprobada'] and not any(d.get('fallo_revisor') for d in r['dictamenes'])


def test_bloquear_sin_hallazgo_no_cuenta_como_deteccion(tmp_path):
    """047:RF-38 — «6 de 6 defectos hallados» no lo era si el mismo dictamen vacío bloqueaba también los sanos."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)
    def fabrica(medir):
        return lambda rol, p, ev, ctx, ronda: {'decision': 'bloqueada', 'evidencia_ids': sorted(ev),
                                               'incertidumbres': [], 'contradicciones': []}
    r = comparar_revision(casos, fabrica, rondas=1)
    # 047:RF-103 (2026-11-24): donde el código ya halló el defecto, el bloqueo vacío lleva ese hallazgo: la detección es
    # del código, como cuenta la medida con «comprobaciones_fallidas». El bloqueo vacío sigue sin hallar nada por sí
    # mismo: los demás quedan sin respuesta y ningún sano se cuenta como falsa alarma.
    from convertersmartgrid.aplicacion.asistente import contradicciones as C
    def halla_el_codigo(c):
        return any(not x['coincide'] for f in (C.comprobar_coste, C.comprobar_datos, C.comprobar_prohibiciones,
                                                C.comprobar_elementos, C.comprobar_magnitudes)
                   for x in f(c['propuesta'], c['evidencia']))
    del_codigo = sum(halla_el_codigo(c) for c in casos)
    assert all(c['defecto'] is not None for c in casos if halla_el_codigo(c)), 'el código alarma en un sano'
    for modo in ('rol_unico', 'equipo'):
        assert r[modo]['detectados'] == del_codigo and r[modo]['sin_respuesta'] == len(casos) - del_codigo
        assert r[modo]['falsas_alarmas'] == 0
        assert all('sin hallazgo' in m for m in r[modo]['motivos_sin_respuesta'])


def test_el_revisor_solo_ve_la_propuesta_y_los_fragmentos(tmp_path):
    """047:RF-39 — el proyecto y el fichero de cada caso se llamaban «sano-…» o «defecto-…», y viajaban al LLM."""
    import json
    from convertersmartgrid.aplicacion.asistente.revision_roles import revisor_ollama
    herramienta = _herramienta_comparar()
    nombres = [c['id'] for c in herramienta.leer_casos()]
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)
    for caso in casos:
        assert not any(n in caso['contexto'].project for n in nombres)
        assert not any(n in Path(v['archivo']).name for v in caso['evidencia'].values() for n in nombres)
    caso = casos[0]
    peticiones = []
    revisar_propuesta(caso['propuesta'], caso['evidencia'], contexto=caso['contexto'], max_rondas=1,
                      revisor=revisor_ollama(_cliente(_dictamen_llm(FAVORABLE), peticiones)))
    assert len(peticiones) == 4
    for _u, cuerpo in peticiones:
        usuario = json.loads(cuerpo['messages'][1]['content'])
        assert set(usuario) == {'propuesta', 'evidencia', 'ronda'}
        assert all(set(v) == {'localizador', 'fragmento'} for v in usuario['evidencia'].values())
        texto = json.dumps(cuerpo, ensure_ascii=False)
        assert caso['contexto'].project not in texto and not any(n in texto for n in nombres)
        assert not any(json.dumps(v['archivo'])[1:-1] in texto for v in caso['evidencia'].values())


def test_el_dictamen_escribe_sus_hallazgos_antes_de_decidir(tmp_path):
    """047:RF-40 — sin razonar, la decisión era el primer campo: se elegía antes de comparar nada con la evidencia."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import esquema_dictamen, revisor_ollama
    orden = list(esquema_dictamen()['properties'])
    assert orden[-1] == 'decision' and orden.index('contradicciones') < orden.index('decision')
    assert esquema_dictamen()['required'] == orden
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1,
                      revisor=revisor_ollama(_cliente(_dictamen_llm(FAVORABLE), peticiones)))
    for _u, cuerpo in peticiones:
        assert list(cuerpo['format']['properties']) == orden
        sistema = cuerpo['messages'][0]['content']
        # La regla de decisión, igual para todos los roles: favorable cuando no se halla nada.
        assert 'favorable si las dos están vacías' in sistema
        # Lo que empujaba a bloquear siempre: «no apruebes la física» y el riesgo de que la propuesta «falle».
        assert 'No apruebes' not in sistema and 'o falla' not in sistema


def test_el_informe_guarda_cada_dictamen(tmp_path):
    """047:RF-41 — la medición de T8 no guardó qué dijo el modelo, y la causa de las falsas alarmas no se veía."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)[:1]
    def fabrica(medir):
        return lambda rol, p, ev, ctx, ronda: {'decision': 'bloqueada', 'evidencia_ids': sorted(ev),
                                               'incertidumbres': [], 'contradicciones': [f'{rol}: valor distinto']}
    fila = comparar_revision(casos, fabrica, rondas=1)['equipo']['por_caso'][0]
    assert [d['rol'] for d in fila['dictamenes']] == ['fuentes', 'fisica', 'coste', 'riesgo']
    assert fila['dictamenes'][0] == {'rol': 'fuentes', 'ronda': 1, 'decision': 'bloqueada',
                                     'evidencia_ids': sorted(casos[0]['evidencia']), 'incertidumbres': [],
                                     'contradicciones': ['fuentes: valor distinto']}


def _sistemas_por_ronda(tmp_path, propuesta, dictamen):
    """Lo que recibe cada rol en cada ronda, con un Ollama falso que siempre dice ``dictamen``."""
    import json
    from convertersmartgrid.aplicacion.asistente.revision_roles import revisor_ollama
    contexto, evidencia = paquete(tmp_path)
    peticiones = []
    r = revisar_propuesta(propuesta, evidencia, contexto=contexto,
                          revisor=revisor_ollama(_cliente(_dictamen_llm(dictamen), peticiones)))
    filas = [(json.loads(c['messages'][1]['content']), c['messages'][0]['content']) for _u, c in peticiones]
    return r, filas


REVISAR = {'decision': 'revisar', 'evidencia_ids': ['e1'], 'incertidumbres': ['coste_usd: ninguna evidencia lo da'],
           'contradicciones': []}


def test_con_algo_pendiente_la_decision_no_es_favorable(tmp_path):
    """047:RF-44 — MEJ24: con qwen3:8b, todas las «sin respuesta» del 047b eran dictámenes favorables con listas
    pendientes (1 en rol único y 7 en equipo), que RF-40 anula. El encargo de cada rol lo dice ahora explícitamente."""
    _r, filas = _sistemas_por_ronda(tmp_path, {'restricciones_deterministas': {'fisica': True}}, REVISAR)
    assert {u['ronda'] for u, _s in filas} == {1, 2}
    for _u, sistema in filas:
        assert 'favorable si las dos están vacías' in sistema
        assert 'nunca es favorable' in sistema and 'revisar (requiere revisión)' in sistema


def test_al_llm_no_van_las_restricciones_deterministas(tmp_path):
    """047:RF-45 — el LLM las tomaba por datos sin evidencia («contexto_vigente no está en ninguna evidencia») y daba
    falsas alarmas; las comprueba el código, que sigue bloqueando con ellas."""
    for valor, aprobada in ((True, True), (False, False)):
        r, filas = _sistemas_por_ronda(tmp_path, {'accion': 'a', 'coste_usd': 1,
                                                  'restricciones_deterministas': {'plan_completo': valor}}, FAVORABLE)
        assert r['aprobada'] is aprobada and filas
        for usuario, _s in filas:
            assert usuario['propuesta'] == {'accion': 'a', 'coste_usd': 1}
        assert r['propuesta_final']['restricciones_deterministas'] == {'plan_completo': valor}


def test_la_segunda_ronda_no_copia_los_dictamenes_de_otros(tmp_path):
    """047:RF-45 — en el equipo del 047b, los cuatro roles repetían en la segunda ronda las mismas incertidumbres,
    también las de fuera de su encargo; la segunda ronda dice que lo anterior no es evidencia ni se copia."""
    _r, filas = _sistemas_por_ronda(tmp_path, {'restricciones_deterministas': {'fisica': True}}, REVISAR)
    for usuario, sistema in filas:
        if usuario['ronda'] == 1:
            assert 'dictamenes_ronda_anterior' not in usuario['propuesta'] and 'se copian' not in sistema
        else:
            assert usuario['propuesta']['dictamenes_ronda_anterior']
            assert 'no son evidencia ni se copian' in sistema and 'tu encargo' in sistema


def test_encargo_mismo_elemento_mismo_valor_y_coste_total():
    """047:RF-46 — clases de error del 047b, sin sus casos: una evidencia de otro elemento daba por buena la propuesta,
    «9 500» frente a 9500 se tomaba por contradicción y «coincide» entraba en las listas."""
    from convertersmartgrid.aplicacion.asistente import revision_roles
    assert 'mismo elemento' in revision_roles._ENCARGO['fuentes']
    assert 'mismo elemento' in revision_roles._ENCARGO['unico']
    assert 'total' in revision_roles._ENCARGO['coste'] and 'total' in revision_roles._ENCARGO['unico']
    regla = revision_roles._REGLA
    assert 'otro formato' in regla and 'separador de miles' in regla
    assert '«coincide»' in regla and 'no es un dato' in regla


def test_dictamen_no_valido_guarda_lo_que_devolvio(tmp_path):
    """047:RF-47 — el informe del 047b solo decía «favorable con incertidumbres pendientes»: sin las listas que
    devolvió el modelo no se veía qué quedaba pendiente."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision
    contexto, evidencia = paquete(tmp_path)
    pendiente = {**FAVORABLE, 'incertidumbres': ['coste_usd: sin evidencia']}
    r = revisar_propuesta({'restricciones_deterministas': {'fisica': True}}, evidencia, contexto=contexto,
                          max_rondas=1, revisor=lambda *_a: dict(pendiente))
    assert not r['aprobada']
    for d in r['dictamenes']:
        assert d['fallo_revisor'] and d.get('devuelto') == {'decision': 'favorable', 'incertidumbres':
                                                       ['coste_usd: sin evidencia'], 'contradicciones': []}
    herramienta = _herramienta_comparar()
    # 047:RF-85 (2026-11-24): una duda sobre un campo que el código ya comprobó se descarta; el caso tiene que ser uno
    # cuyo coste el código no comprueba, o la duda «coste_usd: sin evidencia» no deja nada pendiente.
    from convertersmartgrid.aplicacion.asistente.contradicciones import comprobar_coste
    casos = [c for c in herramienta.materializar(herramienta.leer_casos(), tmp_path)
             if not any(x['coincide'] for x in comprobar_coste(c['propuesta'], c['evidencia']))][:1]
    assert casos, 'el conjunto no tiene un caso cuyo coste no compruebe el código'
    fila = comparar_revision(casos, lambda medir: (lambda rol, p, ev, ctx, ronda: {**pendiente,
                             'evidencia_ids': sorted(ev)}), rondas=1)['equipo']['por_caso'][0]
    assert fila['sin_respuesta'] and all((d.get('devuelto') or {}).get('incertidumbres') == ['coste_usd: sin evidencia']
                                         for d in fila['dictamenes'])
    # Un revisor que no devolvió ningún dictamen no tiene nada que guardar.
    r = revisar_propuesta({}, evidencia, contexto=contexto, max_rondas=1, revisor=lambda *_a: None)
    assert all('devuelto' not in d for d in r['dictamenes'])


def test_tokens_de_cada_intervencion_y_las_que_llegan_al_tope(tmp_path):
    """047:RF-47 — el tope de 512 podía cortar al equipo: el informe dice el tope, la intervención más larga y cuántas
    llegaron al tope, para subirlo midiendo y no a ciegas."""
    from convertersmartgrid.aplicacion.asistente.revision_roles import comparar_revision
    herramienta = _herramienta_comparar()
    casos = herramienta.materializar(herramienta.leer_casos(), tmp_path)[:2]
    def fabrica(medir):
        largos = iter([100, 300, 1024, 50] * 4)
        def revisar(rol, p, ev, ctx, ronda):
            medir(10, next(largos))
            return {**FAVORABLE, 'evidencia_ids': sorted(ev)}
        return revisar
    import inspect
    assert 'tope' in inspect.signature(comparar_revision).parameters, 'la comparación no recibe el tope'
    r = comparar_revision(casos, fabrica, rondas=1, tope=1024)
    assert r['equipo']['tokens_tope'] == 1024 and r['equipo']['max_tokens_salida'] == 1024
    assert r['equipo']['en_tope'] == 2 and r['equipo']['intervenciones'] == 8
    sin_tope = comparar_revision(casos, fabrica, rondas=1)
    assert sin_tope['equipo']['tokens_tope'] is None and sin_tope['equipo']['en_tope'] is None
