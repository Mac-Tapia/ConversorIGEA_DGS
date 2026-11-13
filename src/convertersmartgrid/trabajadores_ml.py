"""043:RF-13: informes y guardia compartidos de los trabajadores locales."""
from __future__ import annotations

from .runtime_paths import staging_publicacion

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path


def escribir_informe(ruta: Path, datos: dict) -> None:
    ruta.parent.mkdir(parents=True,exist_ok=True)
    with staging_publicacion(ruta) as temporal:
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


def entorno_hijo_gpu() -> dict[str, str]:
    """El entorno de un hijo que usa la GPU de este proceso.

    Con la guardia tomada aquí, un hijo sin el token la encuentra ocupada; es el caso de la
    reapertura en otro proceso de un candidato de pronóstico (046:RF-7).
    """
    from .training_coordinator import proceso_vivo, ruta_guardia_gpu
    entorno = dict(os.environ)
    ruta = ruta_guardia_gpu(entorno).resolve()
    entorno['CSG_ML_GPU_LOCK'] = str(ruta)
    if ruta.is_file():
        dueno = json.loads(ruta.read_text(encoding='utf-8'))
        if dueno.get('pid') == os.getpid() and proceso_vivo(dueno['pid'], creado=dueno.get('creado')):
            entorno['CSG_GPU_PARENT_TOKEN'] = dueno['token']
    return entorno


@contextmanager
def turno_gpu(nombre: str):
    """Un hijo hereda solo la guardia demostrablemente conservada por su padre."""
    from .training_coordinator import BloqueoGPU,proceso_vivo,ruta_guardia_gpu
    ruta=ruta_guardia_gpu()
    token=os.environ.get('CSG_GPU_PARENT_TOKEN')
    if token:
        estado=json.loads(ruta.read_text(encoding='utf-8'))
        import psutil
        # El redirector python.exe del venv Windows puede interponerse entre padre e hijo.
        ancestros={p.pid for p in psutil.Process().parents()}
        padre=estado.get('pid',0)
        if (padre not in ancestros or estado.get('token')!=token
                or not proceso_vivo(padre, creado=estado.get('creado'))):
            raise RuntimeError('guardia GPU heredada no corresponde al padre vivo')
        yield
    else:
        with BloqueoGPU(ruta,nombre):
            yield


#: Código de salida de pytest sin el turno de GPU en su plazo (106:RF-4). Los de pytest van del 0 al 5.
SALIDA_SIN_TURNO_GPU = 6


def quien_tiene_la_gpu(ruta: Path | str) -> str:
    """El dueño del turno en ``ruta``: proceso, orden y desde cuándo, o «nadie» (106:RF-3)."""
    try:
        dueno = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'nadie'
    if not isinstance(dueno, dict):
        return 'nadie'
    return f"PID {dueno.get('pid')} ({dueno.get('model')}, desde {dueno.get('started_at')})"


@contextmanager
def turno_gpu_con_plazo(nombre: str, *, ruta: Path | str | None = None, limite_s: float, pausa_s: float = 5.0,
                        avisar=None, aviso_cada_s: float = 60.0, reloj=None, dormir=None):
    """El turno de la GPU, esperando a que lo suelte otro, con plazo y diciendo quién lo tiene (106:RF-2, RF-3).

    2026-11-12: la puerta de un commit esperó 40 min en silencio al entrenamiento T7 (una prueba de módulo tomaba el
    turno real y lo pedía cada 5 s hasta 1 800 s), y nadie supo si estaba colgada. Cada ``aviso_cada_s`` se dice quién
    lo tiene; al vencer ``limite_s`` se lanza ``RuntimeError`` con ese dueño, sin dar nada por bueno.
    """
    import time

    from .training_coordinator import BloqueoGPU, ruta_guardia_gpu

    reloj = reloj or time.monotonic
    dormir = dormir or time.sleep
    ruta = Path(ruta) if ruta is not None else ruta_guardia_gpu()
    inicio = reloj()
    ultimo_aviso = None
    while True:
        bloqueo = BloqueoGPU(ruta, nombre)
        try:
            bloqueo.__enter__()
            break
        except RuntimeError as exc:
            if 'GPU ocupada' not in str(exc):
                raise
            transcurrido = reloj() - inicio
            if transcurrido >= limite_s:
                raise RuntimeError(f'GPU ocupada por {quien_tiene_la_gpu(ruta)} tras esperar {limite_s:.0f} s '
                                   f'({nombre}, 106:RF-3).') from None
            if avisar is not None and (ultimo_aviso is None or reloj() - ultimo_aviso >= aviso_cada_s):
                avisar(f'{nombre}: esperando la GPU, la tiene {quien_tiene_la_gpu(ruta)} '
                       f'({transcurrido:.0f} de {limite_s:.0f} s).')
                ultimo_aviso = reloj()
            dormir(pausa_s)
    try:
        yield bloqueo
    finally:
        bloqueo.__exit__(None, None, None)
