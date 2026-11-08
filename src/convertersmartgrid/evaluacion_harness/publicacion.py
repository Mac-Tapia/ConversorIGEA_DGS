"""JSON estricto, publicación atómica y relectura por huella, sin cargas de modelos."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contratos import canonico, huella


def _pares(pares):
    resultado = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError('clave JSON duplicada: '+clave)
        resultado[clave] = valor
    return resultado


def _constante(valor):
    raise ValueError('constante JSON no finita: '+valor)


def leer_json(ruta: Path):
    dato = json.loads(Path(ruta).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=_pares, parse_constant=_constante)
    canonico(dato)  # También rechaza exponentes desbordados como 1e999.
    return dato


def leer_informe(ruta: Path) -> dict:
    sobre = leer_json(ruta)
    if (not isinstance(sobre, dict) or sobre.get('esquema') != 'csg-harness-publicacion-v1'
            or not isinstance(sobre.get('contenido'), dict)
            or sobre.get('sha256') != huella(sobre['contenido'])):
        raise ValueError('informe sin sobre íntegro o con huella modificada')
    return sobre['contenido']


def publicar(ruta: Path, informe: dict) -> str:
    if not isinstance(informe, dict):
        raise TypeError('informe debe ser un objeto')
    digest = huella(informe)
    datos = canonico({'esquema': 'csg-harness-publicacion-v1', 'contenido': informe, 'sha256': digest})
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    anterior = destino.read_bytes() if destino.exists() else None
    descriptor, nombre = tempfile.mkstemp(prefix=destino.name+'.', suffix='.tmp', dir=destino.parent)
    tmp = Path(nombre)
    reemplazado = False
    try:
        with os.fdopen(descriptor, 'wb') as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        if leer_informe(tmp) != informe:
            raise ValueError('relectura previa no coincide')
        os.replace(tmp, destino)
        reemplazado = True
        if leer_informe(destino) != informe:
            raise ValueError('relectura publicada no coincide')
    except Exception:
        if reemplazado:
            # Requiere un escritor por ruta. Esta comprobación detecta cambios
            # observados, pero no constituye un compare-and-swap del filesystem.
            if destino.read_bytes() != datos:
                raise OSError('readback falló y el destino cambió concurrentemente; no se sobrescribe')
            if anterior is None:
                destino.unlink()
            else:
                descriptor_rollback, nombre_rollback = tempfile.mkstemp(
                    prefix=destino.name+'.rollback.', suffix='.tmp', dir=destino.parent)
                rollback = Path(nombre_rollback)
                with os.fdopen(descriptor_rollback, 'wb') as f:
                    f.write(anterior)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.replace(rollback, destino)
                except OSError as exc:
                    # Conservar bytes previos recuperables si el propio disco impide restaurar.
                    raise OSError('rollback pendiente; informe previo conservado en '+str(rollback)) from exc
                if destino.read_bytes() != anterior:
                    raise OSError('rollback no pudo verificarse')
        raise
    finally:
        tmp.unlink(missing_ok=True)
    return digest
