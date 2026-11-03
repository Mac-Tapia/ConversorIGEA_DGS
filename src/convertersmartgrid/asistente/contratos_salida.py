"""047:RF-1 / RF-2 / RF-10 — contrato local; la salida del LLM nunca ejecuta acciones."""
from __future__ import annotations

from collections.abc import Mapping
import json
import math
import copy
from pathlib import Path

from .sinteticos import normalizar
from .tareas import TAREAS


def esquema_orden(vocabulario: Mapping | None = None) -> dict:
    base = json.loads((Path(__file__).resolve().parents[1] /
                          'schemas/asistente_orden_v1.schema.json').read_text(encoding='utf-8'))
    ramas = []
    for tarea in [None, *sorted(TAREAS)]:
        rama = copy.deepcopy(base)
        rama['properties']['tarea'] = {'enum': [tarea]}
        nombres = ({d.nombre for d in TAREAS[tarea].datos} | {d.tipo for d in TAREAS[tarea].datos}) if tarea else set()
        propiedades = rama['properties']['datos']['properties']
        for n in sorted(nombres):
            valor = {'type': 'string'}
            if vocabulario and n in vocabulario and vocabulario[n]:
                valor['enum'] = list(vocabulario[n])
            propiedades[n] = {'anyOf': [valor, {'type': 'array', 'items': valor}]}
        ramas.append(rama)
    # llama.cpp no admite mezclar properties con oneOf en el mismo nodo.
    return {'$schema': base['$schema'], 'title': base['title'], 'type': 'object', 'oneOf': ramas}


def validar_orden(payload: Mapping, contexto=None, vocabulario: Mapping | None = None) -> dict:
    """Valida respuesta cruda; contexto/vocabulario, si se aportan, acotan entidades."""
    if not isinstance(payload, Mapping) or set(payload) - {'tarea', 'datos', 'confianza', 'razon'}:
        raise ValueError('campos de orden no admitidos')
    if not {'tarea', 'datos', 'confianza'} <= set(payload):
        raise ValueError('faltan campos obligatorios de la orden')
    tarea, datos, confianza = payload['tarea'], payload['datos'], payload['confianza']
    if tarea is not None and (not isinstance(tarea, str) or tarea not in TAREAS):
        raise ValueError('tarea desconocida')
    if type(confianza) not in (int, float) or not math.isfinite(confianza) or not 0 <= confianza <= 1:
        raise ValueError('confianza no finita o fuera de rango')
    if not isinstance(datos, Mapping) or (tarea is None and datos):
        raise ValueError('datos sin tarea válida')
    if not isinstance(payload.get('razon', ''), str):
        raise ValueError('razón debe ser texto')
    vocab = dict(vocabulario or {})
    if contexto is not None:
        vocab['alimentadores'] = list(contexto.feeders)
        vocab['proyecto'] = [contexto.project]
    salida = {}
    for nombre, valor in datos.items():
        definicion = TAREAS[tarea].dato(nombre) or next((d for d in TAREAS[tarea].datos if d.tipo == nombre), None)
        if definicion is None:
            raise ValueError(f'campo {nombre} no admitido por la tarea')
        valores = valor if isinstance(valor, list) else [valor]
        if any(not isinstance(v, str) or not v.strip() for v in valores):
            raise ValueError('entidad vacía o no textual')
        tipo = definicion.tipo
        if tipo in {'alimentadores', 'proyecto', 'sistema', 'set', 'sed', 'caso'} and tipo in vocab:
            permitidos = {normalizar(str(v)).strip() for v in vocab[tipo]}
            if not permitidos or any(normalizar(v).strip() not in permitidos for v in valores):
                raise ValueError(f'entidad fuera del contexto: {tipo}')
        salida[nombre] = list(valores) if isinstance(valor, list) else valores[0]
    return {'tarea': tarea, 'datos': salida, 'confianza': float(confianza),
            'razon': payload.get('razon', '')}
