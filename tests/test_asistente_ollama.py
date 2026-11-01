"""Spec 026, T4: cliente del modelo local de Ollama, con un servidor falso."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from convertersmartgrid.asistente.ollama import ClienteOllama, OllamaNoLocal


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _servidor(respuestas: dict):
    pedidas = []

    def abrir(peticion, timeout):
        ruta = peticion.full_url.split('11434')[1]
        pedidas.append((ruta, json.loads(peticion.data) if peticion.data else None, timeout))
        r = respuestas.get(ruta)
        if isinstance(r, Exception):
            raise r
        return _Respuesta(json.dumps(r).encode())

    return abrir, pedidas


def test_solo_en_esta_maquina():
    """026:RF-5 — el cliente rechaza cualquier dirección que no sea la propia (P9)."""
    with pytest.raises(OllamaNoLocal):
        ClienteOllama('http://192.168.1.20:11434')
    with pytest.raises(OllamaNoLocal):
        ClienteOllama('https://api.ejemplo.com')
    assert ClienteOllama('http://localhost:11434').url.startswith('http://localhost')


def test_interpreta_con_las_tareas_como_herramientas():
    """026:RF-3 — la orden va al modelo local con la lista de tareas; la respuesta JSON se
    convierte en tarea, datos y confianza, sin datos que la tarea no tiene."""
    contenido = {'tarea': 'pide', 'datos': {'proyecto': 'CA101 13', 'alimentadores': ['CA101']},
                 'confianza': 0.9, 'razon': 'pide el plan de inversiones'}
    abrir, pedidas = _servidor({'/api/chat': {'message': {'content': json.dumps(contenido)}}})
    r = ClienteOllama(abrir=abrir).interpretar('haz el plan de inversiones de CA101 13')
    assert r['tarea'] == 'pide' and r['confianza'] == 0.9 and r['modelo'].startswith('ollama:')
    assert r['datos']['proyecto'][0]['valor'] == 'CA101 13' and 'inventado' not in r['datos']
    cuerpo = pedidas[0][1]
    # 047:RF-1: la salida ahora queda acotada mediante JSON Schema.
    assert cuerpo['format']['type'] == 'object' and 'pide' in cuerpo['messages'][0]['content'] and pedidas[0][2] == 30.0


def test_suelta_la_gpu_antes_de_entrenar():
    """026:RF-20 / 026:RF-23 — antes de reentrenar, Ollama descarga sus modelos de la GPU que
    comparte con el Transformer y la PINN; sus consultas no los retienen 5 minutos."""
    abrir, pedidas = _servidor({'/api/ps': {'models': [{'name': 'llama3.1:8b'}]}, '/api/generate': {},
                                '/api/chat': {'message': {'content': '{}'}}})
    c = ClienteOllama(abrir=abrir)
    assert c.liberar_gpu() == ['llama3.1:8b']
    assert ('/api/generate', {'model': 'llama3.1:8b', 'keep_alive': 0}, 30.0) in pedidas
    c.interpretar('hola')
    assert pedidas[-1][1]['keep_alive'] == '60s'


def test_sin_respuesta_o_tarea_desconocida():
    """026:RF-3 / 026:RF-4 — si Ollama no responde o propone algo que no es una tarea, no se adivina."""
    abrir, _ = _servidor({'/api/chat': urllib.error.URLError('rechazada')})
    assert ClienteOllama(abrir=abrir).interpretar('lo que sea') is None
    abrir, _ = _servidor({'/api/chat': {'message': {'content': json.dumps({'tarea': 'borrar_todo'})}}})
    # 047:RF-1: se rechaza la respuesta entera si la tarea no existe.
    assert ClienteOllama(abrir=abrir).interpretar('borra todo') is None
    abrir, _ = _servidor({'/api/tags': {'models': [{'name': 'qwen2.5:3b'}]},
                          '/api/embed': {'embeddings': [[0.1, 0.2]]}})
    c = ClienteOllama(abrir=abrir)
    assert c.modelos() == ['qwen2.5:3b'] and c.embeddings(['hola']) == [[0.1, 0.2]]
def test_cliente_configurado_conserva_revision_y_dos_etapas(tmp_path, monkeypatch):
    """047:RF-18: el protocolo medido debe llegar al cliente que atiende en la web."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.ollama import cliente_configurado
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    almacen.guardar_json('ollama', {'modelo': 'candidato:local', 'revisar_transformer': True,
                                  'dos_etapas': True, 'pensar': False})
    c = cliente_configurado()
    assert c.modelo == 'candidato:local' and c.revisar_transformer and c.dos_etapas and c.pensar is False


@pytest.mark.parametrize('cfg', [[], {'modelo': 0}, {'dos_etapas': 'false'}])
def test_cliente_configurado_rechaza_protocolo_malformado(tmp_path, monkeypatch, cfg):
    """047:RF-18: un valor ambiguo no cambia silenciosamente el protocolo evaluado."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.ollama import cliente_configurado
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    almacen.guardar_json('ollama', cfg)
    with pytest.raises(ValueError):
        cliente_configurado()


def test_ensayo_no_descarga_modelos_ajenos_de_la_gpu():
    """043:RF-12 / 047:RF-18: liberar el ensayo no modifica otros modelos cargados."""
    from convertersmartgrid.asistente.ollama import ClienteOllama
    import io
    import json
    cuerpos = []
    def abrir(req, timeout):
        if req.data:
            cuerpos.append(json.loads(req.data))
            return io.BytesIO(b'{}')
        return io.BytesIO(json.dumps({'models': [{'name': 'ensayo:local'}, {'name': 'otro:local'}]}).encode())
    c = ClienteOllama(modelo='ensayo:local', abrir=abrir)
    assert c.liberar_gpu(solo_actual=True) == ['ensayo:local']
    assert cuerpos == [{'model': 'ensayo:local', 'keep_alive': 0}]
def test_alumno_llm_usa_el_mismo_prompt_del_ajuste():
    """047:RF-19: exportar pesos no habilita un prompt distinto del evaluado."""
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.asistente.llm_destilacion import sistema_alumno
    import json
    import io
    peticiones=[]
    def abrir(req, timeout):
        peticiones.append(json.loads(req.data))
        return io.BytesIO(json.dumps({'message':{'content':json.dumps(
            {'tarea':'cargar_fuente','datos':{},'confianza':.9})}}).encode())
    c=ClienteOllama(modelo='alumno:prueba',abrir=abrir,perfil_prompt='llm_destilado_v1')
    assert c.interpretar('carga la fuente')['tarea']=='cargar_fuente'
    assert peticiones[0]['messages'][0]['content']==sistema_alumno()
