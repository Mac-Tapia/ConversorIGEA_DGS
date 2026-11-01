"""047:RF-13, RF-16 a RF-18 — 200 propuestas no son tres observaciones humanas."""
import pytest
import io
import json


def _perfectas():
    from igea_dgs.asistente.propuestas_maestro import generar_propuestas
    from igea_dgs.asistente.tareas import TAREAS
    filas, _ = generar_propuestas()
    return {'ejemplos': 200, 'unicos': 200, 'tareas': 27, 'acierto_tarea': 1., 'f1_datos': 1.,
        'confirmaciones_conservadas': True, 'sin_fuga': True,
        'familias': {t: {'ejemplos': 8 if i < 11 else 7, 'acierto_tarea': 1., 'f1_datos': 1.}
                     for i,t in enumerate(sorted(TAREAS))},
        'casos': [{'record_id': r['record_id'], 'esperado': r['tarea'], 'obtenido': r['tarea'],
                   'correcto': True, 'vp': len(r['datos']), 'fp': 0, 'fn': 0, 'confirmacion': True} for r in filas]}


def test_generador_historico_entrega_200_textos_unicos():
    """047:RF-16 — 200 filas con siete duplicadas no cumplen 200 propuestas únicas."""
    from igea_dgs.asistente import ordenes_fijas
    from igea_dgs.evaluacion_modelos import texto_canonico
    filas = ordenes_fijas.generar({})
    assert len(filas) == len({texto_canonico(e.texto) for e in filas}) == 200


def test_repartir_no_admite_fuga_por_duplicados():
    """047:RF-16 — un reparto no presenta copias como observaciones independientes."""
    from igea_dgs.asistente import ordenes_fijas
    e = ordenes_fijas.generar({}, total=1)[0]
    with pytest.raises(ValueError, match='duplicad'):
        ordenes_fijas.repartir([e, e])


def test_propuestas_nuevas_completas_y_sin_fuga():
    """047:RF-16 — corpus fijo, etiquetado y con todas las tareas del catálogo."""
    from igea_dgs.asistente.propuestas_maestro import generar_propuestas
    from igea_dgs.asistente.tareas import TAREAS
    filas, meta = generar_propuestas()
    otras, meta2 = generar_propuestas()
    assert filas == otras and meta == meta2
    assert len(filas) == len({r['texto'] for r in filas}) == 200
    assert {r['tarea'] for r in filas} == set(TAREAS)
    assert all(r['quality'] == 'silver_teacher_verified' for r in filas)
    assert meta['humanas'] == 0
    for r in filas:
        tipos = {d[2] for d in r['datos']}
        assert {d.tipo for d in TAREAS[r['tarea']].datos if d.obligatorio} <= tipos


@pytest.mark.parametrize('cambio', ['etiqueta', 'span', 'origen'])
def test_auditoria_detecta_corrupcion_y_campo_ajeno(cambio):
    """047:RF-16: la integridad incluye anotaciones y procedencia."""
    from igea_dgs.asistente.aceptacion import auditar_propuestas
    from igea_dgs.asistente.propuestas_maestro import generar_propuestas
    from igea_dgs.evaluacion_modelos import huella
    filas, _ = generar_propuestas()
    if cambio == 'etiqueta':
        filas[0]['tarea'] = 'estado'
    elif cambio == 'span':
        filas[0]['datos'].append([0, 1, 'campo_inexistente'])
        filas[0]['record_id'] = huella({k:v for k,v in filas[0].items() if k != 'record_id'})
    else:
        filas[0]['origen'] = 'confirmado'
        filas[0]['record_id'] = huella({k:v for k,v in filas[0].items() if k != 'record_id'})
    assert not auditar_propuestas(filas)['valid']


def test_200_propuestas_pueden_cumplir_asistido_sin_fingir_200_humanas():
    """047:RF-13 / 047:RF-17 — las puertas se informan por alcance."""
    from igea_dgs.asistente.aceptacion import decidir_aceptacion
    m = _perfectas()
    r = decidir_aceptacion(m, {'ejemplos': 3, 'acierto_tarea': 1., 'f1_datos': 1.})
    assert r['asistida']['aprobada'] and r['humanas']['ejemplos'] == 3
    assert not r['autonoma']['aprobada'] and not r['electrica']['aprobada']


@pytest.mark.parametrize('cambio', ['ausentes', 'truncados', 'duplicados', 'resumen_distinto'])
def test_resumen_sin_casos_completos_consistentes_no_aprueba(cambio):
    """047:RF-17: un resumen perfecto no oculta resultados omitidos o contradictorios."""
    from igea_dgs.asistente.aceptacion import decidir_aceptacion
    m = _perfectas()
    assert decidir_aceptacion(m, {})['asistida']['aprobada']
    if cambio == 'ausentes':
        del m['casos']
    elif cambio == 'truncados':
        m['casos'].pop()
    elif cambio == 'duplicados':
        m['casos'][-1] = m['casos'][0]
    else:
        m['casos'][0].update(correcto=False, obtenido=None)
    assert not decidir_aceptacion(m, {})['asistida']['aprobada']


def test_calidad_insuficiente_no_cumple_por_tener_200_filas():
    """047:RF-17 — cumplir el tamaño no rebaja las puertas de precisión."""
    from igea_dgs.asistente.aceptacion import decidir_aceptacion
    m = {'ejemplos': 200, 'unicos': 200, 'tareas': 27, 'acierto_tarea': .8, 'f1_datos': 1.,
         'confirmaciones_conservadas': True, 'sin_fuga': True}
    assert not decidir_aceptacion(m, {})['asistida']['aprobada']


def test_revisor_obligatorio_no_se_omite_por_confianza_del_alumno():
    """047:RF-18 — confianza alta no permite eludir el modo supervisado."""
    from igea_dgs.asistente.interprete import interpretar
    class Alumno:
        def predecir(self, texto):
            return {'tarea': 'estado', 'confianza': 1., 'datos': {}}
    class Revisor:
        modelo = 'local'
        revisar_transformer = True
        def interpretar(self, texto):
            return None
    assert interpretar('estado', transformer=Alumno(), ollama=Revisor()).tarea is None


def test_dos_etapas_separan_intencion_y_campos():
    """047:RF-18 — la extracción no reinterpreta la tarea ni inventa otro esquema."""
    from igea_dgs.asistente.ollama import ClienteOllama
    llamadas = []
    respuestas = [{'tarea': 'convertir', 'confianza': .99, 'razon': 'exportación'},
                  {'tarea': 'convertir', 'datos': {'alimentadores': ['AB101']}, 'confianza': .99}]
    def abrir(req, timeout):
        llamadas.append(json.loads(req.data))
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(respuestas[len(llamadas)-1])}}).encode())
    cliente = ClienteOllama(abrir=abrir, dos_etapas=True)
    r = cliente.interpretar('exporta AB101 a DGS')
    assert r['tarea'] == 'convertir' and len(llamadas) == 2
    assert llamadas[1]['format']['properties']['tarea']['enum'] == ['convertir']


def test_extraccion_no_aumenta_confianza_de_intencion():
    """047:RF-18: acertar campos no acredita una intencion de baja confianza."""
    from igea_dgs.asistente.ollama import ClienteOllama
    from igea_dgs.asistente.interprete import interpretar
    respuestas = iter([{'tarea': 'convertir', 'confianza': .1},
                      {'tarea': 'convertir', 'datos': {'alimentadores': ['AB101']}, 'confianza': .99}])
    def abrir(req, timeout):
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(next(respuestas))}}).encode())
    r = interpretar('exporta AB101', ollama=ClienteOllama(abrir=abrir, dos_etapas=True))
    assert r.tarea is None and r.confianza <= .1


def test_estado_separa_materializadas_y_eventos_reales(tmp_path, monkeypatch):
    """047:RF-16 / 047:RF-17 — dos contadores distintos evitan confundir propuestas y usos."""
    from igea_dgs.asistente import almacen
    from igea_dgs.asistente.aceptacion import estado_aceptacion
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path))
    for _ in range(5):
        almacen.anotar('ejemplos', {'texto': 'estado', 'tarea': 'estado', 'origen': 'confirmado'})
    r = estado_aceptacion()
    assert r['propuestas']['definidas'] == 200 and r['propuestas']['materializadas'] == 0
    assert r['humanas'] == {'eventos': 5, 'unicas': 1}


def test_api_expone_200_propuestas_sin_cargar_modelos(tmp_path, monkeypatch):
    """047:RF-16 / RF-17: custodia real por HTTP, sin inferencia ni escrituras nativas."""
    from fastapi.testclient import TestClient
    from igea_dgs.web.app import create_app
    from igea_dgs.asistente import almacen
    from igea_dgs.asistente.propuestas_maestro import generar_propuestas
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    filas, meta = generar_propuestas()
    (tmp_path / 'propuestas.json').write_text(json.dumps(filas), encoding='utf-8')
    (tmp_path / 'manifest.json').write_text(json.dumps(meta), encoding='utf-8')
    almacen.guardar_json('aceptacion_agente', {'corpus': str(tmp_path)})
    for _ in range(5):
        almacen.anotar('ejemplos', {'texto': 'estado', 'tarea': 'estado', 'origen': 'confirmado'})
    with TestClient(create_app(tmp_path / 'web')) as client:
        r = client.get('/api/asistente/aceptacion')
        assert r.status_code == 200
        d = r.json()
        assert d['propuestas']['materializadas'] == d['propuestas']['unicas'] == 200
        assert len(d['propuestas']['filas']) == 200
        assert d['humanas'] == {'eventos': 5, 'unicas': 1}
        assert d['evaluacion'] is None and not d['integral']
        registro = client.get('/api/asistente/registro').json()['conjunto_real'][0]
        assert registro['ordenes'] == 1 and registro['confirmacion_obligatoria']
        (tmp_path / 'resultado.json').write_text(json.dumps({'manifest': meta, 'metricas': []}), encoding='utf-8')
        almacen.guardar_json('aceptacion_agente', {'corpus': str(tmp_path), 'evaluacion': str(tmp_path / 'resultado.json')})
        d = client.get('/api/asistente/aceptacion').json()
        assert d['bloqueos'] and d['evaluacion'] is None and not d['integral']


def test_no_se_exigen_200_humanas_para_promocion_asistida_con_puertas():
    """047:RF-13 — se corrige la restricción adicional de la sesión anterior."""
    from igea_dgs.asistente.destilacion_integral import decidir_promocion
    from igea_dgs.asistente.tareas import TAREAS
    m = {'acierto_tarea': 1., 'f1_datos': 1., 'ejemplos': 200}
    familias = {t: m for t in TAREAS}
    r = decidir_promocion(m, {**m, 'ejemplos': 3}, familias, familias)
    assert r['status'] == 'PROMOVIDO' and r['alcance'] == 'asistido'
    assert r['ordenes_humanas'] == 3 and r['confirmacion_obligatoria']


def test_evaluador_rechaza_ram_insuficiente_antes_de_abrir_datos(tmp_path, monkeypatch, capsys):
    """043:RF-12 / 047:RF-17: no iniciar cargas sin los recursos requeridos."""
    import importlib.util
    from pathlib import Path
    import igea_dgs.training_coordinator as coordinador
    spec = importlib.util.spec_from_file_location('aceptar', Path(__file__).parents[1] / 'tools/aceptar_agente.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.setattr(coordinador, '_memoria_sistema', lambda: {'fisica_gib': 1., 'commit_gib': None})
    r = m.main(['seleccionar', '--dataset', str(tmp_path / 'datos'), '--destino', str(tmp_path / 'salida')])
    salida = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert r == 2 and 'Memoria insuficiente' in salida['error']
    assert list((tmp_path / 'salida').glob('error_*.json'))
    monkeypatch.setattr(coordinador, '_memoria_sistema', lambda: {'fisica_gib': 2., 'commit_gib': None})
    assert m.main(['seleccionar', '--dataset', str(tmp_path / 'datos'), '--destino', str(tmp_path / 'salida')]) == 2
    assert 'Memoria insuficiente' in json.loads(capsys.readouterr().out.splitlines()[-1])['error']


@pytest.mark.parametrize("valor", [float('nan'), float('inf'), -1., 1.1, True, None])
def test_metrica_invalida_nunca_aprueba(valor):
    """047:RF-17 — las puertas rechazan métricas no finitas, booleanas o fuera de rango."""
    from igea_dgs.asistente.aceptacion import decidir_aceptacion
    from igea_dgs.asistente.tareas import TAREAS
    m = {'ejemplos': 200, 'unicos': 200, 'tareas': 27, 'acierto_tarea': 1., 'f1_datos': 1.,
         'confirmaciones_conservadas': True, 'sin_fuga': True,
         'familias': {t: {'ejemplos': 8 if i < 11 else 7, 'acierto_tarea': 1., 'f1_datos': 1.}
                      for i, t in enumerate(sorted(TAREAS))}}
    m['familias'][next(iter(TAREAS))]['f1_datos'] = valor
    assert not decidir_aceptacion(m, {})['asistida']['aprobada']


@pytest.mark.parametrize('familias', [[], {'estado': None}, {'estado': {'ejemplos': True}}])
def test_evidencia_incompleta_no_rompe_ni_aprueba(familias):
    """047:RF-17 — un informe truncado produce rechazo explícito."""
    from igea_dgs.asistente.aceptacion import decidir_aceptacion
    assert not decidir_aceptacion({'familias': familias}, {})['asistida']['aprobada']
