"""Spec 026, T4: cliente del modelo local de Ollama, con un servidor falso."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from igea_dgs.asistente.ollama import ClienteOllama, OllamaNoLocal


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
    contenido = {'tarea': 'pide', 'datos': {'proyecto': 'CA101 13', 'alimentadores': ['CA101'], 'inventado': 'x'},
                 'confianza': 0.9, 'razon': 'pide el plan de inversiones'}
    abrir, pedidas = _servidor({'/api/chat': {'message': {'content': json.dumps(contenido)}}})
    r = ClienteOllama(abrir=abrir).interpretar('haz el plan de inversiones de CA101 13')
    assert r['tarea'] == 'pide' and r['confianza'] == 0.9 and r['modelo'].startswith('ollama:')
    assert r['datos']['proyecto'][0]['valor'] == 'CA101 13' and 'inventado' not in r['datos']
    cuerpo = pedidas[0][1]
    assert cuerpo['format'] == 'json' and 'pide' in cuerpo['messages'][0]['content'] and pedidas[0][2] == 30.0


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
    assert ClienteOllama(abrir=abrir).interpretar('borra todo')['tarea'] is None
    abrir, _ = _servidor({'/api/tags': {'models': [{'name': 'qwen2.5:3b'}]},
                          '/api/embed': {'embeddings': [[0.1, 0.2]]}})
    c = ClienteOllama(abrir=abrir)
    assert c.modelos() == ['qwen2.5:3b'] and c.embeddings(['hola']) == [[0.1, 0.2]]
