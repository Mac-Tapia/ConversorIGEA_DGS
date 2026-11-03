"""047:RF-5 / RF-6 / RF-7 — revisión local, con dictámenes y sin autoridad nativa."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid.asistente.revision_roles import revisar_propuesta


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
    from convertersmartgrid.asistente.ollama import ClienteOllama
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
    from convertersmartgrid.asistente import almacen, revision_roles
    from convertersmartgrid.asistente.revision_roles import revisor_ollama
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
    from convertersmartgrid.asistente.revision_roles import esquema_dictamen, revisor_ollama
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
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.revision_roles import config_revision, revisor_ollama
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'datos'))
    assert config_revision() == {'presupuesto_s': 60.0, 'num_predict': 512}
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
    from convertersmartgrid.asistente.revision_roles import comparar_revision
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
    from convertersmartgrid.asistente.revision_roles import comparar_revision
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
    from convertersmartgrid.asistente.revision_roles import comparar_revision, revisor_ollama
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
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.asistente.revision_roles import revisor_ollama
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
    from convertersmartgrid.asistente import revision_roles
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
