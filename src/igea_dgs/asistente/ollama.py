"""Cliente del modelo de lenguaje local de Ollama (spec 026, RF-3, RF-5, RF-17).

Cuando el Transformer duda, la orden se pasa a un modelo de Ollama de esta máquina con la
lista de tareas como herramientas, y responde en JSON. Nada sale de la máquina (P9): el
cliente rechaza cualquier dirección que no sea la propia. Si Ollama no está arrancado o
tarda más del tiempo máximo, la respuesta es ``None`` y el asistente pregunta al operador.

También da los embeddings del índice del proyecto (``nomic-embed-text``).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlparse

from .tareas import TAREAS, descripcion_para_modelo

URL_LOCAL = 'http://127.0.0.1:11434'
#: Cuánto retiene Ollama el modelo en la GPU tras responder: con sus 5 minutos por defecto, una
#: consulta dejaba 5 GB ocupados justo cuando la vigilancia lanzaba un reentrenamiento.
RETENER = '60s'
LOCALES = {'127.0.0.1', 'localhost', '::1'}
MODELO_EMBEDDINGS = 'nomic-embed-text'

_INSTRUCCIONES = (
    'Eres el intérprete de órdenes de un conversor de redes eléctricas a DIgSILENT. '
    'Elige UNA tarea de la lista y extrae sus datos tal como aparecen en la orden. '
    'Responde solo con JSON: {"tarea": nombre, "datos": {nombre_dato: valor}, "confianza": 0 a 1, '
    '"razon": frase corta}. Si la orden no encaja en ninguna tarea, usa "tarea": null. '
    'No inventes datos que la orden no dice.')


class OllamaNoLocal(ValueError):
    """La dirección de Ollama no es de esta máquina: los datos no pueden salir (P9)."""


def _abrir_por_defecto(peticion, timeout):
    return urllib.request.urlopen(peticion, timeout=timeout)


class ClienteOllama:
    def __init__(self, url: str = URL_LOCAL, modelo: str = 'qwen2.5:3b', *, tiempo_max_s: float = 30.0,
                 abrir: Callable = _abrir_por_defecto):
        host = urlparse(url).hostname or ''
        if host not in LOCALES:
            raise OllamaNoLocal(f'Ollama tiene que estar en esta máquina, no en {host!r} (P9).')
        self.url, self.modelo, self.tiempo_max_s, self._abrir = url.rstrip('/'), modelo, tiempo_max_s, abrir

    def _pedir(self, ruta: str, cuerpo: dict | None = None) -> dict | None:
        datos = json.dumps(cuerpo).encode('utf-8') if cuerpo is not None else None
        peticion = urllib.request.Request(self.url + ruta, data=datos,
                                          headers={'Content-Type': 'application/json'},
                                          method='POST' if datos is not None else 'GET')
        try:
            with self._abrir(peticion, self.tiempo_max_s) as r:
                return json.loads(r.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

    def modelos(self) -> list[str] | None:
        """Los modelos instalados, o ``None`` si Ollama no responde."""
        r = self._pedir('/api/tags')
        return None if r is None else [m.get('name', '') for m in r.get('models') or []]

    def interpretar(self, texto: str) -> dict[str, Any] | None:
        """La tarea y los datos de la orden según el modelo, o ``None`` si no responde."""
        inicio = time.monotonic()
        r = self._pedir('/api/chat', {
            'model': self.modelo, 'stream': False, 'format': 'json', 'keep_alive': RETENER,
            'options': {'temperature': 0, 'seed': 0},
            'messages': [{'role': 'system', 'content': _INSTRUCCIONES + '\nTareas: '
                          + json.dumps(descripcion_para_modelo(), ensure_ascii=False)},
                         {'role': 'user', 'content': texto}]})
        if r is None:
            return None
        try:
            respuesta = json.loads((r.get('message') or {}).get('content') or '')
        except ValueError:
            return None
        if not isinstance(respuesta, dict):
            return None
        tarea = respuesta.get('tarea')
        segundos = time.monotonic() - inicio
        if tarea not in TAREAS:
            return {'tarea': None, 'confianza': 0.0, 'datos': {}, 'modelo': f'ollama:{self.modelo}',
                    'razon': str(respuesta.get('razon') or ''), 'segundos': segundos}
        datos: dict[str, list[dict]] = {}
        for nombre, valor in (respuesta.get('datos') or {}).items():
            d = TAREAS[tarea].dato(nombre) or next((x for x in TAREAS[tarea].datos if x.tipo == nombre), None)
            if d is not None and valor not in (None, '', []):
                valores = valor if isinstance(valor, list) else [valor]
                datos.setdefault(d.tipo, []).extend({'valor': str(v), 'confianza': 0.5} for v in valores)
        try:
            confianza = max(0.0, min(1.0, float(respuesta.get('confianza') or 0.0)))
        except (TypeError, ValueError):
            confianza = 0.0
        return {'tarea': tarea, 'confianza': confianza, 'datos': datos, 'modelo': f'ollama:{self.modelo}',
                'razon': str(respuesta.get('razon') or ''), 'segundos': segundos}

    def responder(self, pregunta: str, contexto: Sequence[str]) -> str | None:
        """Una respuesta redactada solo con los trozos dados, citándolos por su número (RF-18)."""
        trozos = '\n'.join(f'[{i + 1}] {t}' for i, t in enumerate(contexto))
        r = self._pedir('/api/chat', {
            'model': self.modelo, 'stream': False, 'keep_alive': RETENER, 'options': {'temperature': 0, 'seed': 0},
            'messages': [{'role': 'system', 'content': (
                'Responde en español solo con la información de los trozos numerados, citando cada '
                'afirmación con su número entre corchetes. Si los trozos no lo dicen, responde '
                'exactamente: No lo sé.')},
                {'role': 'user', 'content': f'Trozos:\n{trozos}\n\nPregunta: {pregunta}'}]})
        return None if r is None else ((r.get('message') or {}).get('content') or '').strip() or None

    def embeddings(self, textos: Sequence[str], modelo: str = MODELO_EMBEDDINGS) -> list[list[float]] | None:
        r = self._pedir('/api/embed', {'model': modelo, 'input': list(textos), 'keep_alive': RETENER})
        return None if r is None else r.get('embeddings')

    def liberar_gpu(self) -> list[str]:
        """Descarga de la GPU los modelos que Ollama tenga cargados y devuelve cuáles eran.

        La GPU de 8 GB la comparten Ollama, la PINN y el Transformer: con llama3.1:8b cargado
        (unos 5 GB), entrenar el Transformer dio «CUDA error: out of memory» (2026-10-24).
        """
        cargados = [m.get('name') for m in (self._pedir('/api/ps') or {}).get('models') or [] if m.get('name')]
        for nombre in cargados:
            self._pedir('/api/generate', {'model': nombre, 'keep_alive': 0})
        return cargados


def liberar_gpu_para_entrenar() -> list[str]:
    """Antes de entrenar en la GPU, que Ollama suelte la memoria; sin Ollama no hace nada."""
    return ClienteOllama(tiempo_max_s=10.0).liberar_gpu()


def cliente_configurado(tiempo_max_s: float = 30.0) -> ClienteOllama:
    """El cliente con el modelo que eligió la medida (``tools/asistente_medir_ollama.py``)."""
    from . import almacen

    elegido = (almacen.leer_json('ollama') or {}).get('modelo') or 'qwen2.5:3b'
    return ClienteOllama(modelo=elegido, tiempo_max_s=tiempo_max_s)
