"""061: diario de operaciones y custodia de informes, sin ejecutar ni promover modelos."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
import uuid
from typing import Any


def _json(valor: Any) -> str:
    return json.dumps(valor,ensure_ascii=False,sort_keys=True,default=str,allow_nan=False)


def resumen_operacion(trabajo: dict) -> dict:
    """El diario y la consulta comparten el mismo resumen sin certificar física."""
    resultado=trabajo.get('result')
    resumen={k:v for k,v in resultado.items() if isinstance(v,(str,int,float,bool,type(None)))} if isinstance(resultado,dict) else None
    return {**trabajo,'result':resumen,'aceptacion_nativa':None}


class RegistroOperaciones:
    """Estados persistentes separados por espacio; no conserva funciones ejecutables."""

    def __init__(self,ruta: Path,workspace_id: str):
        self.ruta=Path(ruta)
        self.workspace_id=workspace_id

    def anotar(self,trabajo: dict,contexto: dict) -> None:
        if trabajo.get('workspace_id')!=self.workspace_id:
            raise ValueError('trabajo de otro espacio')
        if not trabajo.get('id') or trabajo.get('status') not in ('queued','running','done','parcial','no_converge','failed','cancelled','interrumpido'):
            raise ValueError('estado de operación inválido')
        # El informe completo permanece en los entregables originales. Evita copiar
        # curvas grandes en cada avance; el monitor no certifica aceptación eléctrica.
        dato=resumen_operacion(trabajo)
        self.ruta.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.ruta,timeout=2)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS eventos (seq INTEGER PRIMARY KEY, espacio TEXT, job TEXT, instante REAL, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS trabajos (espacio TEXT, job TEXT, creado REAL, contexto TEXT, payload TEXT, seq INTEGER, PRIMARY KEY(espacio,job))')
            seq=db.execute('INSERT INTO eventos(espacio,job,instante,payload) VALUES(?,?,?,?)',
                (self.workspace_id,trabajo['id'],time.time(),_json(dato))).lastrowid
            db.execute('INSERT INTO trabajos VALUES(?,?,?,?,?,?) ON CONFLICT(espacio,job) DO UPDATE SET payload=excluded.payload,seq=excluded.seq',
                (self.workspace_id,trabajo['id'],trabajo.get('created_at') or time.time(),_json(contexto),_json(dato),seq))

    def leer(self,*,vivos: set[str],limite: int=50) -> list[dict]:
        if not 1<=limite<=200:raise ValueError('límite entre 1 y 200')
        if not self.ruta.is_file():return []
        with closing(sqlite3.connect(f'{self.ruta.resolve().as_uri()}?mode=ro',uri=True,timeout=2)) as db:
            filas=db.execute('SELECT job,contexto,payload,seq FROM trabajos WHERE espacio=? ORDER BY creado DESC,job DESC LIMIT ?',
                             (self.workspace_id,limite)).fetchall()
        salida=[]
        for job,contexto,payload,seq in filas:
            d=json.loads(payload)
            seguimiento=('en_sesion' if job in vivos else 'interrumpido'
                if d['status'] in ('queued','running') else 'historico')
            salida.append({**d,'contexto':json.loads(contexto),'seguimiento':seguimiento,'seq_registro':seq})
        return salida


#: 067:RF-1: lo que produce la propia web, que no es de ninguna familia de modelos.
FAMILIA_OPERACION='operacion_web'


def registrar_evidencia(raiz: Path,informe: Path,*,familia: str,etiqueta: str,
                        alcance: str='global_sin_asignacion_a_proyecto',origen: str|None=None) -> dict:
    """Incorpora una copia local identificada; no cambia RegistroModelo ni pesos."""
    from ..training_coordinator import ORDEN_MODELOS
    if familia not in ORDEN_MODELOS and familia!=FAMILIA_OPERACION:raise ValueError('familia de modelo desconocida')
    raw=Path(informe).read_bytes()
    if len(raw)>32*1024*1024:raise ValueError('informe mayor que 32MiB; use un resumen trazable')
    contenido=json.loads(raw)
    if not isinstance(contenido,dict):raise ValueError('el informe debe ser un objeto JSON')
    sha=hashlib.sha256(raw).hexdigest()
    base={'sha256':sha,'familia':familia,'etiqueta':etiqueta,'origen':origen or str(Path(informe).resolve()),
          'alcance':alcance}
    identidad=hashlib.sha256(_json(base).encode()).hexdigest()
    carpeta=Path(raiz)/'observacion/evidencias';carpeta.mkdir(parents=True,exist_ok=True)
    meta={**base,'id':identidad,
          'registrado':datetime.now().astimezone().isoformat(),'activacion_acreditada':False}
    datos=carpeta/f'{identidad}.json';manifiesto=carpeta/f'{identidad}.meta.json'
    if manifiesto.exists():
        existente=next(e for e in leer_evidencias(raiz) if e['id']==identidad)
        return {k:v for k,v in existente.items() if k!='informe'}
    # Escribir de forma exclusiva impide sustituir una evidencia ya incorporada.
    if datos.exists() and datos.read_bytes()!=raw:raise ValueError('copia de evidencia con integridad inválida')
    if not datos.exists():
        with datos.open('xb') as f:f.write(raw)
    with manifiesto.open('x',encoding='utf-8') as f:f.write(_json(meta))
    return meta


def leer_evidencias(raiz: Path) -> list[dict]:
    filas=[]
    for p in (Path(raiz)/'observacion/evidencias').glob('*.meta.json'):
        meta=json.loads(p.read_text(encoding='utf-8'))
        campos=('sha256','familia','etiqueta','origen','alcance')
        if not isinstance(meta,dict) or any(k not in meta for k in campos):
            raise ValueError('integridad del manifiesto de evidencia inválida')
        identidad=hashlib.sha256(_json({k:meta[k] for k in campos}).encode()).hexdigest()
        if identidad!=meta.get('id') or p.name!=f'{identidad}.meta.json':
            raise ValueError('integridad de identidad/procedencia de evidencia inválida')
        raw=p.with_name(p.name.replace('.meta.json','.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=meta.get('sha256'):
            raise ValueError('integridad de evidencia inválida')
        filas.append({**meta,'activacion_acreditada':False,'informe':json.loads(raw)})
    return sorted(filas,key=lambda f:f['registrado'],reverse=True)


def preparar_control(ruta: Path,identidad: dict,*,reiniciar: bool):
    """El checkpoint solo continúa dentro de la identidad que lo produjo."""
    from .orquestador import PuntoDeControl
    if reiniciar and ruta.is_file():
        copia=ruta.with_name(f'{ruta.stem}.anterior-{uuid.uuid4().hex}.json')
        shutil.copy2(ruta,copia)
        control=PuntoDeControl(ruta,{'etapas':{},'datos':{}})
    else:
        control=PuntoDeControl.abrir(ruta)
    anterior=control.estado.get('identidad')
    if control.estado['etapas'] and anterior!=identidad:
        raise ValueError('la identidad del punto de control no coincide; revise y reinicie explícitamente')
    control.estado['identidad']=identidad
    return control
