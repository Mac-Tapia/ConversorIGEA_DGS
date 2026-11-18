"""002:RF-3; 050:RF-1/2/3: contratos puros de observación, sin productores ni E/S."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ORDEN_MODELOS = ('transformer', 'clasificador', 'gru', 'pinn', 'evolutivos', 'embeddings', 'qlora')
TIPOS_INFORME = ('estudio', 'factibilidad')

ESQUEMA_INSTANTANEA = 'convertersmartgrid-learning-snapshot-v1'

ESQUEMA_INSTANTANEA_MULTIPROYECTO = 'convertersmartgrid-learning-snapshot-v2'

ESQUEMA_CICLO = 'convertersmartgrid-learning-cycle-v1'

ESQUEMA_CONJUNTO_V1 = 'convertersmartgrid-model-ensemble-v1'

ESQUEMA_CONJUNTO = 'convertersmartgrid-model-ensemble-v2'

ESQUEMA_CONTEXTO_CICLO = 'convertersmartgrid-learning-context-v1'

ESQUEMA_CONTEXTO_DOCUMENTAL = 'convertersmartgrid-documentary-context-v1'

ESQUEMA_CONTEXTO_MIXTO = 'convertersmartgrid-learning-context-v2'

ESQUEMA_INSTANTANEA_MIXTA = 'convertersmartgrid-learning-snapshot-v3'

ESQUEMA_PROCEDENCIA = 'convertersmartgrid-learning-provenance-v1'

ESQUEMA_PLAN = 'convertersmartgrid-learning-plan-v1'

ORIGENES = ('observado', 'simulado_nativo', 'redactado')

ETIQUETAS_FISICAS = ('medicion', 'motor_nativo')

ETIQUETAS = ETIQUETAS_FISICAS + ('operador', 'maestro', 'prediccion', 'llm')

FAMILIAS_FISICAS = frozenset({'gru', 'pinn'})

FASES = ('preparacion', 'entrenamiento', 'seleccion', 'evaluacion', 'publicacion', 'activacion',
         'aceptacion_nativa')

APORTES = ('interpretacion', 'pronostico', 'estimacion_fisica', 'alternativas', 'evidencia',
           'validacion_nativa')

HEX_SHA256 = re.compile(r'[0-9a-f]{64}')

class CicloBloqueado(ValueError):
    """050:RF-8: el ciclo no puede seguir; el conjunto aceptado no cambia."""

def contenido_canonico(valor: Any) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, default=str).encode('utf-8')

def huella(valor: Any) -> str:
    return hashlib.sha256(contenido_canonico(valor)).hexdigest()

def crear_observacion_id(contexto_hash: str, fuente_hash: str, registro_id: str, instante: str) -> str:
    """050:RF-2: la observación fuente conserva identidad entre familias y snapshots."""
    for nombre, valor in (('contexto_hash', contexto_hash), ('fuente_hash', fuente_hash)):
        if not isinstance(valor, str) or not HEX_SHA256.fullmatch(valor):
            raise CicloBloqueado(f'{nombre}: falta SHA-256 de procedencia')
    if not isinstance(registro_id, str) or not registro_id.strip():
        raise CicloBloqueado('registro_id: falta identidad de la observación fuente')
    try:
        if not isinstance(instante, str):
            raise ValueError('no es texto')
        fecha = datetime.fromisoformat(instante)
        if fecha.utcoffset() is None:
            raise ValueError('sin zona horaria')
        utc = fecha.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError, OverflowError) as exc:
        raise CicloBloqueado('instante: se exige fecha ISO-8601 con zona horaria explícita') from exc
    return huella({'schema': 'convertersmartgrid-observation-v1', 'contexto_hash': contexto_hash,
                    'fuente_hash': fuente_hash, 'registro_id': registro_id, 'instante': utc})

def ruta_de(instantanea: Mapping[str, Any], nombre: str) -> Path:
    """La copia congelada de una fuente, que es lo que las etapas leen (nunca el origen vivo)."""
    if nombre not in instantanea.get('archivos', {}):
        raise CicloBloqueado(f'{nombre}: no está en la instantánea')
    base = Path(instantanea['ruta']) / 'datos' / nombre
    # Una fuente de un fichero se entrega como fichero; una carpeta, como carpeta.
    if instantanea.get('tipos', {}).get(nombre) == 'fichero':
        return base / next(iter(instantanea['archivos'][nombre]))
    return base

def muestra_de_registro(instantanea: Mapping[str, Any], referencias: Mapping[str, Any],
                       fuente: str, registro: str, contenido: Any, *, familia: str,
                       particion: str, origen: str, etiqueta: str) -> Muestra:
    """050:RF-2/3: enlaza el registro leído con su observación fuente, sin inferencias."""
    tabla = referencias.get(fuente) if isinstance(referencias, Mapping) else None
    if not isinstance(tabla, Mapping):
        raise CicloBloqueado(f'{fuente}/{registro}: tabla de referencias ausente o inválida')
    referencia = tabla.get(registro)
    if not isinstance(referencia, Mapping):
        raise CicloBloqueado(f'{fuente}/{registro}: falta referencia de procedencia')
    if referencia.get('contenido_hash') != huella(contenido):
        raise CicloBloqueado(f'{fuente}/{registro}: contenido distinto de la referencia')
    contexto = referencia.get('contexto')
    fisicos = list(instantanea.get('contextos', {}).values())
    if not fisicos and 'contextos' not in instantanea:
        fisicos = [instantanea['contexto_hash']]
    documentales = list(instantanea.get('contextos_documentales', {}).values())
    if familia in FAMILIAS_FISICAS and contexto not in fisicos:
        raise CicloBloqueado(f'{fuente}/{registro}: falta contexto físico 043')
    if contexto not in [*fisicos, *documentales]:
        raise CicloBloqueado(f'{fuente}/{registro}: contexto no declarado')
    hashes = {h for archivos in instantanea['archivos'].values() for h in archivos.values()}
    if referencia.get('fuente_hash') not in hashes:
        raise CicloBloqueado(f'{fuente}/{registro}: fuente de observación sin custodia en la instantánea')
    identidad = crear_observacion_id(contexto, referencia.get('fuente_hash'),
        referencia.get('registro_id'), referencia.get('instante'))
    return Muestra(identidad, familia, instantanea['snapshot_id'], origen, etiqueta,
                   particion, contexto, registro)

@dataclass(frozen=True)
class Muestra:
    """050:RF-2: una muestra de una familia, atada a la instantánea y a su observación."""

    observacion_id: str
    familia: str
    snapshot_id: str
    origen: str
    etiqueta: str
    particion: str
    contexto: str = ''
    record_id: str = ''

    def __post_init__(self):
        if self.familia not in ORDEN_MODELOS:
            raise ValueError(f'familia desconocida: {self.familia}')
        if self.origen not in ORIGENES:
            raise ValueError(f'origen desconocido: {self.origen}')
        if self.etiqueta not in ETIQUETAS:
            raise ValueError(f'etiqueta desconocida: {self.etiqueta}')
        if self.particion not in ('entrenamiento', 'seleccion', 'calibracion', 'prueba'):
            raise ValueError(f'partición desconocida: {self.particion}')
        if not self.observacion_id or not HEX_SHA256.fullmatch(self.snapshot_id):
            raise ValueError('muestra sin observación o sin instantánea')
        if not self.record_id:
            object.__setattr__(self, 'record_id', huella([self.familia, self.observacion_id, self.particion]))
