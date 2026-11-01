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
from .contratos_salida import esquema_orden, validar_orden

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
    'No inventes datos que la orden no dice. '
    'Distingue preguntar como, por que o para que sirve (pregunta) de ordenar un calculo. '
    'Consultar proyectos conocidos es proyectos; volver a leer o actualizar desde PF es leer_proyectos. '
    'Convertir un sistema a DGS es convertir_sistema; sistema_completo ademas importa y calibra. '
    'Consultar lo disponible en el espacio es estado, no redactar un informe.')


class OllamaNoLocal(ValueError):
    """La dirección de Ollama no es de esta máquina: los datos no pueden salir (P9)."""


def _abrir_por_defecto(peticion, timeout):
    # P9: una configuración de proxy del sistema no debe sacar una orden local.
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(peticion, timeout=timeout)


class ClienteOllama:
    def __init__(self, url: str = URL_LOCAL, modelo: str = 'qwen2.5:3b', *, tiempo_max_s: float = 30.0,
                 abrir: Callable = _abrir_por_defecto, revisar_transformer: bool = False,
                 dos_etapas: bool = False, pensar: bool | None = None):
        host = urlparse(url).hostname or ''
        if host not in LOCALES:
            raise OllamaNoLocal(f'Ollama tiene que estar en esta máquina, no en {host!r} (P9).')
        self.url, self.modelo, self.tiempo_max_s, self._abrir = url.rstrip('/'), modelo, tiempo_max_s, abrir
        self.revisar_transformer = revisar_transformer
        self.dos_etapas = dos_etapas
        self.pensar = pensar

    def _pedir(self, ruta: str, cuerpo: dict | None = None) -> dict | None:
        if ruta == '/api/chat' and cuerpo is not None and self.pensar is not None:
            cuerpo = {**cuerpo, 'think': self.pensar}
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

    def interpretar(self, texto: str, *, temperatura: float = 0.0, semilla: int = 0,
                    contexto: Sequence[str] = ()) -> dict[str, Any] | None:
        """La tarea y los datos de la orden según el modelo, o ``None`` si no responde.

        Con ``temperatura`` mayor que cero y semillas distintas, cada llamada es un voto del
        maestro en la destilación (027:RF-56); para atender al operador, 0. ``contexto``: órdenes
        confirmadas parecidas y notas de fallos (027:RF-37, RF-39), antes de la orden.
        """
        if contexto:
            texto = 'Contexto de órdenes anteriores:\n' + '\n'.join(contexto) + f'\n\nOrden: {texto}'
        inicio = time.monotonic()
        formato = esquema_orden()
        sistema = _INSTRUCCIONES + '\nTareas: ' + json.dumps([
            {**t, 'ejemplo_entrenamiento': TAREAS[t['tarea']].plantillas[0]}
            for t in descripcion_para_modelo()], ensure_ascii=False)
        elegida = None
        if self.dos_etapas:
            esquema_intencion = {'type': 'object', 'additionalProperties': False,
                'properties': {'tarea': {'enum': [None, *sorted(TAREAS)]},
                    'confianza': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'razon': {'type': 'string'}},
                'required': ['tarea', 'confianza']}
            compactas = [{'tarea': t['tarea'], 'descripcion': t['descripcion'],
                         'ejemplo': TAREAS[t['tarea']].plantillas[0]} for t in descripcion_para_modelo()]
            r_intencion = self._pedir('/api/chat', {'model': self.modelo, 'stream': False,
                'format': esquema_intencion, 'keep_alive': RETENER,
                'options': {'temperature': temperatura, 'seed': semilla, 'num_predict': 256, 'num_ctx': 8192},
                'messages': [{'role': 'system', 'content':
                    'Clasifica la intención de una orden del operador del conversor de redes eléctricas. '
                    'Devuelve solo tarea, confianza y razon; no extraigas datos ni ejecutes acciones. '
                    'Si pide una explicación, es pregunta; si pide lo cargado en el espacio, es estado. '
                    'Leer TXT/MDB/VNR es cargar_fuente; actualizar proyectos en PF es leer_proyectos. '
                    'Distingue entrenar pesos del gemelo de capturar escenarios para aprendizaje. Tareas: ' +
                    json.dumps(compactas, ensure_ascii=False)}, {'role': 'user', 'content': texto}]})
            try:
                intencion = json.loads((r_intencion or {}).get('message', {}).get('content', ''))
                if not isinstance(intencion, dict) or set(intencion) - {'tarea', 'confianza', 'razon'}:
                    return None
                validada = validar_orden({**intencion, 'datos': {}})
            except (ValueError, TypeError, AttributeError):
                return None
            elegida = validada['tarea']
            if elegida is None or not TAREAS[elegida].datos:
                return {**validada, 'modelo': f'ollama:{self.modelo}', 'segundos': time.monotonic() - inicio}
            formato = next(r for r in formato['oneOf'] if r['properties']['tarea']['enum'] == [elegida])
            sistema = ('La tarea ya está fijada y no puedes cambiarla. Extrae solo los datos literales completos '
                'de la orden para esta tarea; no inventes los que falten. Omite los delimitadores «» de los valores. '
                'Devuelve tarea, datos y confianza. Tarea: ' + json.dumps(next(
                    t for t in descripcion_para_modelo() if t['tarea'] == elegida), ensure_ascii=False))
        r = self._pedir('/api/chat', {
            'model': self.modelo, 'stream': False, 'format': formato, 'keep_alive': RETENER,
            'options': {'temperature': temperatura, 'seed': semilla, 'num_predict': 512, 'num_ctx': 8192},
            'messages': [{'role': 'system', 'content': sistema},
                         {'role': 'user', 'content': texto}]})
        if r is None:
            return None
        try:
            respuesta = json.loads((r.get('message') or {}).get('content') or '')
        except ValueError:
            return None
        if not isinstance(respuesta, dict):
            return None
        try:
            respuesta = validar_orden(respuesta)
        except ValueError:
            return None
        if self.dos_etapas and respuesta['tarea'] != elegida:
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
        if self.dos_etapas:
            confianza = min(confianza, validada['confianza'])
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

    def liberar_gpu(self, *, solo_actual: bool = False) -> list[str]:
        """Descarga de la GPU los modelos que Ollama tenga cargados y devuelve cuáles eran.

        La GPU de 8 GB la comparten Ollama, la PINN y el Transformer: con llama3.1:8b cargado
        (unos 5 GB), entrenar el Transformer dio «CUDA error: out of memory» (2026-10-24).
        ``solo_actual=True`` conserva los modelos ajenos al cliente de este ensayo.
        """
        cargados = [m.get('name') for m in (self._pedir('/api/ps') or {}).get('models') or [] if m.get('name')]
        if solo_actual:
            cargados = [n for n in cargados if n in (self.modelo, self.modelo + ':latest')]
        for nombre in cargados:
            self._pedir('/api/generate', {'model': nombre, 'keep_alive': 0})
        return cargados


def liberar_gpu_para_entrenar() -> list[str]:
    """Antes de entrenar en la GPU, que Ollama suelte la memoria; sin Ollama no hace nada."""
    return ClienteOllama(tiempo_max_s=10.0).liberar_gpu()


def cliente_configurado(tiempo_max_s: float = 30.0) -> ClienteOllama:
    """El cliente con el modelo que eligió la medida (``tools/asistente_medir_ollama.py``)."""
    from . import almacen

    cfg = almacen.leer_json('ollama')
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ValueError('Configuración de Ollama inválida.')
    elegido = cfg.get('modelo', 'qwen2.5:3b')
    if not isinstance(elegido, str) or not elegido.strip():
        raise ValueError('Modelo de Ollama inválido.')
    revision, etapas, pensar = cfg.get('revisar_transformer', False), cfg.get('dos_etapas', False), cfg.get('pensar')
    if type(revision) is not bool or type(etapas) is not bool or (pensar is not None and type(pensar) is not bool):
        raise ValueError('Protocolo de revisión de Ollama inválido.')
    return ClienteOllama(modelo=elegido, tiempo_max_s=tiempo_max_s,
                         revisar_transformer=revision, dos_etapas=etapas, pensar=pensar)
