"""Publicacion secuencial del alumno local; no concede aceptacion ni activa pesos (047)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


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


def publicar(checkpoint: Path,destino: Path,modelo: str,*,log=print) -> dict:
    """Cada proceso termina y se verifica antes de iniciar el siguiente."""
    from .ollama import ClienteOllama
    checkpoint=checkpoint.resolve(); destino=destino.resolve()
    estado=verificar_checkpoint(checkpoint)
    from .llm_destilacion import ficha_base
    validar_base_checkpoint(estado,ficha_base())
    if destino.exists():
        raise ValueError('destino existente conservado')
    if not re.fullmatch(r'csg-alumno:[a-z0-9][a-z0-9._-]{2,100}',modelo):
        raise ValueError('tag nuevo debe usar el espacio csg-alumno:')
    cliente=ClienteOllama()
    tags=cliente._pedir('/api/tags')
    if tags is None or not isinstance(tags.get('models'),list):
        raise RuntimeError('no se puede consultar el inventario Ollama')
    if any(m.get('name')==modelo for m in tags['models']):
        raise ValueError('tag existente conservado')
    raiz=Path(__file__).resolve().parents[3]
    lock=json.loads((raiz/'docs/LLAMA_CPP_RUNTIME_LOCK.json').read_text(encoding='utf-8'))
    quant=raiz/lock['exe_relativo']
    if not quant.is_file() or sha256(quant)!=lock['sha256_quantize_exe']:
        raise ValueError('cuantizador no coincide con el binario fijado')
    upstream=json.loads((raiz/'docs/UPSTREAM_ALUMNO_LLM_LOCK.json').read_text(encoding='utf-8'))['repositorios'][0]
    repo=raiz/'external/upstream/llama_cpp'
    revision=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    cambios=subprocess.run(['git','-C',str(repo),'status','--porcelain'],capture_output=True,text=True,check=True).stdout.strip()
    if revision!=upstream['commit'] or cambios or sha256(repo/upstream['license_path'])!=upstream['license_sha256']:
        raise ValueError('conversor o licencia difiere de la revision fijada')
    destino.mkdir(parents=True)
    etapas=[]
    def ejecutar(nombre,args):
        log('publicacion: '+nombre,flush=True)
        with (destino/(nombre+'.log')).open('w',encoding='utf-8') as salida:
            r=subprocess.run(args,cwd=raiz,stdout=salida,stderr=subprocess.STDOUT)
        etapas.append({'etapa':nombre,'exit_code':r.returncode,'argv':[str(a) for a in args]})
        (destino/'etapas.json').write_text(json.dumps(etapas,indent=2),encoding='utf-8')
        if r.returncode:
            raise RuntimeError(f'{nombre} fallo con codigo {r.returncode}; ver log local')
    try:
        ejecutar('exportar',[sys.executable,'-X','utf8',str(raiz/'tools/llm_destilar.py'),'exportar',
            '--adaptador',str(checkpoint/'adaptador'),'--destino',str(destino/'fp16')])
        export=json.loads((destino/'fp16/exportacion.json').read_text(encoding='utf-8'))
        # El conversor no abre los pesos hasta que el exportador ha terminado.
        ejecutar('convertir',[sys.executable,'-X','utf8',str(repo/'convert_hf_to_gguf.py'),
            str(destino/'fp16'),'--outfile',str(destino/'alumno.f16.gguf'),'--outtype','f16'])
        temporal=destino/'alumno.Q4_K_M.gguf.incomplete'
        ejecutar('cuantizar',[str(quant),str(destino/'alumno.f16.gguf'),str(temporal),'Q4_K_M','4'])
        if temporal.stat().st_size<1024**3:
            raise ValueError('GGUF cuantizado incompleto')
        huella=sha256(temporal)
        gguf=destino/'alumno.Q4_K_M.gguf';temporal.replace(gguf)
        mf=destino/'Modelfile'
        mf.write_text('FROM ./alumno.Q4_K_M.gguf\nPARAMETER num_ctx 4096\n',encoding='utf-8')
        tags_finales=cliente._pedir('/api/tags')
        if tags_finales is None or any(m.get('name')==modelo for m in tags_finales.get('models',[])):
            raise ValueError('tag existente o inventario no disponible antes de importar')
        ejecutar('importar',['ollama','create',modelo,'--file',str(mf)])
        instalado=next((m for m in (cliente._pedir('/api/tags') or {}).get('models',[]) if m.get('name')==modelo),None)
        if not instalado or sha256(gguf)!=huella:
            raise ValueError('falta readback del modelo o el GGUF cambio')
        resultado={'publicado':True,'activado':False,'modelo':modelo,'modelo_digest':instalado['digest'],
            'sha256_gguf':huella,'checkpoint':str(checkpoint),'checkpoint_estado_sha256':sha256(checkpoint/'estado.json'),
            'configuracion':estado['configuracion'],'exportacion':export,'etapas':etapas}
        (destino/'runtime.json').write_text(json.dumps(resultado,indent=2),encoding='utf-8')
        return resultado
    except Exception as exc:
        (destino/'error.json').write_text(json.dumps({'publicado':False,'activado':False,'error':str(exc),
            'modelo':modelo,'etapas':etapas},indent=2),encoding='utf-8')
        raise
