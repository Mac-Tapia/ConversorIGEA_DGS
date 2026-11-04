"""Comprobaciones de un checkpoint, comunes al entrenamiento y a la publicación (002:RF-4)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(p: Path) -> str:
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def validar_base_checkpoint(estado: dict, base: dict) -> None:
    if not estado.get('base') or estado['base'] != base:
        raise ValueError('base, revision o inventario de configuracion/tokenizador distintos del checkpoint')


def verificar_checkpoint(carpeta: Path, *, exigir_completo: bool = True) -> dict:
    estado=json.loads((carpeta/'estado.json').read_text(encoding='utf-8'))
    if exigir_completo and not estado.get('training_completed'):
        raise ValueError('checkpoint no completado')
    artefactos=estado.get('artefactos')
    if not isinstance(artefactos,dict) or not artefactos:
        raise ValueError('checkpoint sin hashes')
    raiz=carpeta.resolve()
    for nombre,huella in artefactos.items():
        archivo=(raiz/nombre).resolve()
        if not archivo.is_relative_to(raiz) or not archivo.is_file() or sha256(archivo)!=huella:
            raise ValueError('checkpoint alterado: '+nombre)
    requeridos={'adaptador/adapter_model.safetensors','adaptador/adapter_config.json','optimizador.pt'}
    if not requeridos.issubset(artefactos):
        raise ValueError('checkpoint incompleto')
    vistos, total = estado.get('ejemplos_vistos_epoca'), estado.get('registros_train')
    if (type(vistos) is not int or type(total) is not int or total < 1 or not 0 <= vistos <= total or
            estado.get('siguiente_indice') != vistos or
            (estado.get('training_completed') and vistos != total)):
        raise ValueError('corpus no completado')
    return estado
