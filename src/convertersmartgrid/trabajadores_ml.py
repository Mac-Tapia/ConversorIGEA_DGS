"""043:RF-13: informes y guardia compartidos de los trabajadores locales."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile


def escribir_informe(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True,exist_ok=True)
    temporal=ruta.with_name(f'.{ruta.name}.{os.getpid()}.tmp')
    temporal.write_text(json.dumps(datos,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temporal.replace(ruta)


def sha_archivo(ruta: Path) -> str:
    with ruta.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def semillas_de(texto: str) -> tuple[int,...]:
    valores=tuple(int(v.strip()) for v in texto.split(',') if v.strip())
    if not valores or min(valores)<0 or len(set(valores))!=len(valores):
        raise ValueError('semillas unicas no negativas obligatorias')
    return valores


def fallo(exc: Exception) -> dict:
    from .training_coordinator import MemoriaMLInsuficiente
    datos=isinstance(exc,(ValueError,FileNotFoundError)) and not isinstance(exc,MemoriaMLInsuficiente)
    return {'status':'BLOQUEADO_POR_DATOS' if datos else 'ERROR_ENTORNO',
            'error':str(exc),'reason':str(exc),'training_completed':False,'entrenado':False,
            'promovido':False,'gates':{'approved':False}}


def leer_dataset_v2(dataset: Path) -> tuple[dict,dict]:
    if not dataset.is_dir():raise ValueError('no existe el dataset v2')
    manifest=json.loads((dataset/'manifest.json').read_text(encoding='utf-8'))
    partes={};grupos={};textos={};ids=set()
    for parte in ('train','validation','test'):
        f=dataset/(parte+'.jsonl')
        if sha_archivo(f)!=manifest['partitions'][parte]['sha256']:raise ValueError('particion v2 alterada')
        filas=[json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
        if len(filas)!=manifest['partitions'][parte]['count']:raise ValueError('conteo v2 inconsistente')
        for r in filas:
            if not r.get('group_id') or r.get('record_id') in ids:raise ValueError('registro v2 sin grupo o duplicado')
            ids.add(r['record_id'])
            for indice,valor in ((grupos,r['group_id']),(textos,' '.join(r['texto'].casefold().split()))):
                if valor in indice and indice[valor]!=parte:raise ValueError('fuga de grupo o texto v2')
                indice[valor]=parte
        partes[parte]=filas
    return partes,manifest


@contextmanager
def turno_gpu(nombre: str):
    """Un hijo hereda solo la guardia demostrablemente conservada por su padre."""
    from .training_coordinator import BloqueoGPU,_pid_vivo
    ruta=Path(os.environ.get('CSG_ML_GPU_LOCK') or str(Path(tempfile.gettempdir())/'convertersmartgrid-gpu.lock'))
    token=os.environ.get('CSG_GPU_PARENT_TOKEN')
    if token:
        estado=json.loads(ruta.read_text(encoding='utf-8'))
        import psutil
        # El redirector python.exe del venv Windows puede interponerse entre padre e hijo.
        ancestros={p.pid for p in psutil.Process().parents()}
        padre=estado.get('pid',0)
        if (padre not in ancestros or estado.get('token')!=token or not _pid_vivo(padre)):
            raise RuntimeError('guardia GPU heredada no corresponde al padre vivo')
        yield
    else:
        with BloqueoGPU(ruta,nombre):
            yield
